"""IVF-Flat: an inverted file index over k-means centroids, written by hand.

Idea: cluster the data into ``nlist`` cells with k-means. Each vector is stored only in the list
of its nearest centroid. A query compares itself to the ``nlist`` centroids, then scans only the
``nprobe`` nearest lists. Work per query drops from n to roughly n * nprobe / nlist.

The recall loss comes from boundary effects: a true neighbour can sit just across the border of
a cell that was not probed. Raising nprobe probes more neighbouring cells; at nprobe == nlist
every list is scanned and the search is exact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from vectorforge.core.distance import Metric, distance_matrix, distances, normalize_rows
from vectorforge.core.quantize import ScalarQuantizer
from vectorforge.core.store import GrowableMatrix
from vectorforge.index.base import (
    Allow,
    Index,
    LabelArray,
    SearchResult,
    empty_result,
    topk_from_distances,
)

Quantization = Literal["none", "int8"]

# FAISS's default cap: more than 256 training points per centroid barely moves the centroids
# but costs proportionally more time.
MAX_POINTS_PER_CENTROID = 256
# Auto-train once this many points per list are buffered. FAISS warns below 39; 16 lets small
# collections switch to IVF sooner. For real data, call train() on a representative sample.
MIN_POINTS_PER_CENTROID = 16


def kmeans(
    x: npt.NDArray[np.float32], k: int, *, max_iter: int, seed: int
) -> npt.NDArray[np.float32]:
    """Lloyd's algorithm with k-means++ seeding and a fixed iteration cap. L2 geometry."""
    n = x.shape[0]
    if not 1 <= k <= n:
        raise ValueError(f"k must be between 1 and the number of points ({n}), got {k}")
    rng = np.random.default_rng(seed)

    # k-means++: pick each new centre with probability proportional to its squared distance from
    # the nearest centre chosen so far. Spreading the seeds out avoids the classic failure where
    # two seeds land in one cluster and another cluster gets none.
    centroids = np.empty((k, x.shape[1]), dtype=np.float32)
    centroids[0] = x[rng.integers(n)]
    closest = distances(centroids[0], x, "l2").astype(np.float64)
    for i in range(1, k):
        total = closest.sum()
        if total <= 0:
            # Every point coincides with a chosen centre (duplicates). Any point will do.
            pick = int(rng.integers(n))
        else:
            pick = int(rng.choice(n, p=closest / total))
        centroids[i] = x[pick]
        closest = np.minimum(closest, distances(centroids[i], x, "l2"))

    for _ in range(max_iter):
        assign = np.argmin(distance_matrix(x, centroids, "l2"), axis=1)
        counts = np.bincount(assign, minlength=k)
        sums = np.zeros_like(centroids, dtype=np.float64)
        np.add.at(sums, assign, x)
        new = centroids.copy()
        nonempty = counts > 0
        new[nonempty] = (sums[nonempty] / counts[nonempty, None]).astype(np.float32)
        # An empty cluster keeps its old centre; it may pick up points next iteration. Moving it
        # to a random point would make results depend on iteration order for no real benefit.
        if np.allclose(new, centroids):
            break
        centroids = new
    return centroids


class IVFIndex(Index):
    kind = "ivf"

    def __init__(
        self,
        dim: int,
        metric: Metric = "l2",
        *,
        nlist: int = 64,
        nprobe: int = 8,
        quantization: Quantization = "none",
        max_iter: int = 25,
        seed: int = 0,
    ) -> None:
        super().__init__(dim, metric)
        if nlist < 1 or nprobe < 1:
            raise ValueError("nlist and nprobe must be positive")
        if quantization not in ("none", "int8"):
            raise ValueError("quantization must be 'none' or 'int8'")
        self.nlist = nlist
        self.nprobe = nprobe
        self.quantization: Quantization = quantization
        self.max_iter = max_iter
        self.seed = seed

        self.centroids: npt.NDArray[np.float32] | None = None
        self.quantizer: ScalarQuantizer | None = None
        store_dtype = np.int8 if quantization == "int8" else np.float32
        self._list_vectors = [GrowableMatrix(dim, store_dtype, capacity=16) for _ in range(nlist)]
        self._list_labels: list[list[int]] = [[] for _ in range(nlist)]
        # label -> (list number, row inside that list), so vector(label) is O(1).
        self._where: list[tuple[int, int]] = []
        # Before training there are no cells; vectors wait here and are searched exhaustively.
        self._pending = GrowableMatrix(dim, np.float32)

    @property
    def is_trained(self) -> bool:
        return self.centroids is not None

    def __len__(self) -> int:
        return len(self._where) + len(self._pending)

    def _prepare(self, x: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
        # Cosine is computed on unit vectors, so cluster unit vectors too.
        return normalize_rows(x) if self.metric == "cosine" else x

    def _coarse_metric(self) -> Metric:
        # Inner product cells are probed by inner product (as FAISS does); l2 and normalised
        # cosine are probed by Euclidean distance, which ranks unit vectors like cosine does.
        return "ip" if self.metric == "ip" else "l2"

    # -- training ------------------------------------------------------------------------------
    def train(self, x: npt.ArrayLike) -> None:
        arr = self._prepare(self._check_vectors(x))
        if arr.shape[0] < self.nlist:
            raise ValueError(f"need at least nlist={self.nlist} training vectors")
        cap = self.nlist * MAX_POINTS_PER_CENTROID
        if arr.shape[0] > cap:
            pick = np.random.default_rng(self.seed).choice(arr.shape[0], cap, replace=False)
            arr = arr[np.sort(pick)]
        self.centroids = kmeans(arr, self.nlist, max_iter=self.max_iter, seed=self.seed)
        if self.quantization == "int8":
            self.quantizer = ScalarQuantizer.fit(arr)
        pending = np.asarray(self._pending.view(), dtype=np.float32).copy()
        self._pending = GrowableMatrix(self.dim, np.float32)
        if len(pending):
            self._assign(pending)

    def _assign(self, arr: npt.NDArray[np.float32]) -> None:
        assert self.centroids is not None
        cells = np.argmin(distance_matrix(arr, self.centroids, self._coarse_metric()), axis=1)
        stored: npt.NDArray[Any] = arr
        if self.quantizer is not None:
            stored = self.quantizer.encode(arr)
        for row, cell in zip(stored, cells.tolist(), strict=True):
            pos = self._list_vectors[cell].append(row[None, :])
            self._list_labels[cell].append(len(self._where))
            self._where.append((cell, pos))

    def add(self, vectors: npt.ArrayLike) -> LabelArray:
        arr = self._prepare(self._check_vectors(vectors))
        start = len(self)
        if self.is_trained:
            self._assign(arr)
        else:
            self._pending.append(arr)
            if len(self._pending) >= max(self.nlist * MIN_POINTS_PER_CENTROID, self.nlist):
                self.train(np.asarray(self._pending.view(), dtype=np.float32).copy())
        return np.arange(start, start + arr.shape[0], dtype=np.int64)

    # -- search --------------------------------------------------------------------------------
    def _decoded(self, cell: int) -> npt.NDArray[np.float32]:
        raw = self._list_vectors[cell].view()
        if self.quantizer is not None:
            return self.quantizer.decode(raw)
        return np.asarray(raw, dtype=np.float32)

    def vector(self, label: int) -> npt.NDArray[np.float32]:
        if not self.is_trained:
            return np.asarray(self._pending.row(label), dtype=np.float32)
        cell, pos = self._where[label]
        row = self._list_vectors[cell].row(pos)[None, :]
        if self.quantizer is not None:
            decoded: npt.NDArray[np.float32] = self.quantizer.decode(row)[0]
            return decoded
        return np.asarray(row[0], dtype=np.float32)

    def search(
        self, query: npt.ArrayLike, k: int, *, allow: Allow | None = None, **params: Any
    ) -> SearchResult:
        q = self._check_query(query, k)
        requested = params.get("nprobe")
        nprobe = self.nprobe if requested is None else int(requested)
        if nprobe < 1:
            raise ValueError("nprobe must be positive")
        if len(self) == 0:
            return empty_result()
        q = self._prepare(q[None, :])[0]

        if self.centroids is None:
            mat = np.asarray(self._pending.view(), dtype=np.float32)
            labels = np.arange(len(self), dtype=np.int64)
            dists = distances(q, mat, self.metric)
        else:
            order = np.argsort(distances(q, self.centroids, self._coarse_metric()), kind="stable")
            cells = [c for c in order[: min(nprobe, self.nlist)].tolist() if self._list_labels[c]]
            if not cells:
                return empty_result()
            mat = np.concatenate([self._decoded(c) for c in cells])
            labels = np.concatenate(
                [np.asarray(self._list_labels[c], dtype=np.int64) for c in cells]
            )
            dists = distances(q, mat, self.metric)

        if self._deleted or allow is not None:
            keep = np.fromiter(
                (
                    lab not in self._deleted and (allow is None or allow(lab))
                    for lab in labels.tolist()
                ),
                dtype=bool,
                count=labels.size,
            )
            labels, dists = labels[keep], dists[keep]
        return topk_from_distances(dists, labels, k)

    # -- stats and persistence -----------------------------------------------------------------
    def list_sizes(self) -> list[int]:
        return [len(lbls) for lbls in self._list_labels]

    def memory_bytes(self) -> int:
        vecs = sum(m.nbytes() for m in self._list_vectors) + self._pending.nbytes()
        cents = 0 if self.centroids is None else int(self.centroids.nbytes)
        quant = 0 if self.quantizer is None else self.quantizer.nbytes()
        # 8 bytes per stored label (int64 id list), as a compact layout would need.
        return vecs + cents + quant + 8 * len(self._where)

    def stats(self) -> dict[str, Any]:
        s = super().stats()
        sizes = self.list_sizes()
        s.update(
            {
                "params": {
                    "nlist": self.nlist,
                    "nprobe": self.nprobe,
                    "quantization": self.quantization,
                },
                "trained": self.is_trained,
                "list_size_max": max(sizes) if self.is_trained else 0,
                "list_size_min": min(sizes) if self.is_trained else 0,
            }
        )
        return s

    def save(self, path: Path) -> None:
        self._write_header(
            path,
            {
                "nlist": self.nlist,
                "nprobe": self.nprobe,
                "quantization": self.quantization,
                "max_iter": self.max_iter,
                "seed": self.seed,
                "trained": self.is_trained,
            },
        )
        if self.centroids is None:
            np.save(path / "pending.npy", np.asarray(self._pending.view(), dtype=np.float32))
            return
        np.save(path / "centroids.npy", self.centroids)
        if self.quantizer is not None:
            np.save(path / "sq_min.npy", self.quantizer.vmin)
            np.save(path / "sq_step.npy", self.quantizer.step)
        # Rows in label order plus each label's cell: enough to rebuild the lists exactly.
        cells = np.array([c for c, _ in self._where], dtype=np.int32)
        stored_dtype = np.int8 if self.quantizer is not None else np.float32
        rows = np.zeros((len(self._where), self.dim), dtype=stored_dtype)
        for label, (cell, pos) in enumerate(self._where):
            rows[label] = self._list_vectors[cell].row(pos)
        np.save(path / "cells.npy", cells)
        np.save(path / "rows.npy", rows)
        (path / "list_sizes.json").write_text(json.dumps(self.list_sizes()), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> IVFIndex:
        h = cls._read_header(path, cls.kind)
        index = cls(
            h["dim"],
            h["metric"],
            nlist=h["nlist"],
            nprobe=h["nprobe"],
            quantization=h["quantization"],
            max_iter=h["max_iter"],
            seed=h["seed"],
        )
        if not h["trained"]:
            pending = np.load(path / "pending.npy")
            if len(pending):
                index._pending.append(pending)
        else:
            index.centroids = np.load(path / "centroids.npy")
            if h["quantization"] == "int8":
                index.quantizer = ScalarQuantizer(
                    np.load(path / "sq_min.npy"), np.load(path / "sq_step.npy")
                )
            cells = np.load(path / "cells.npy").tolist()
            rows = np.load(path / "rows.npy")
            for label, cell in enumerate(cells):
                pos = index._list_vectors[cell].append(rows[label][None, :])
                index._list_labels[cell].append(label)
                index._where.append((cell, pos))
        index._read_deleted(path)
        return index
