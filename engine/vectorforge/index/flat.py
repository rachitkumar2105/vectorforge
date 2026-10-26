"""Exact brute-force search. The ground truth for every recall number in this project."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from vectorforge.core.distance import Metric, distance_matrix, distances
from vectorforge.core.store import GrowableMatrix
from vectorforge.index.base import (
    Allow,
    Index,
    LabelArray,
    SearchResult,
    empty_result,
    topk_from_distances,
)


class FlatIndex(Index):
    kind = "flat"

    def __init__(self, dim: int, metric: Metric = "l2") -> None:
        super().__init__(dim, metric)
        self._vectors = GrowableMatrix(dim, np.float32)

    def __len__(self) -> int:
        return len(self._vectors)

    def add(self, vectors: npt.ArrayLike) -> LabelArray:
        arr = self._check_vectors(vectors)
        start = self._vectors.append(arr)
        return np.arange(start, start + arr.shape[0], dtype=np.int64)

    def vector(self, label: int) -> npt.NDArray[np.float32]:
        return np.asarray(self._vectors.row(label), dtype=np.float32)

    def matrix(self) -> npt.NDArray[np.float32]:
        return np.asarray(self._vectors.view(), dtype=np.float32)

    def _candidate_labels(self, allow: Allow | None) -> LabelArray | None:
        """Labels eligible for results, or None when every label is eligible (the fast path)."""
        if allow is None and not self._deleted:
            return None
        n = len(self)
        mask = np.ones(n, dtype=bool)
        if self._deleted:
            mask[np.fromiter(self._deleted, dtype=np.int64)] = False
        if allow is not None:
            mask &= np.fromiter((allow(i) for i in range(n)), dtype=bool, count=n)
        return np.flatnonzero(mask).astype(np.int64)

    def search(
        self, query: npt.ArrayLike, k: int, *, allow: Allow | None = None, **params: Any
    ) -> SearchResult:
        q = self._check_query(query, k)
        if len(self) == 0:
            return empty_result()
        labels = self._candidate_labels(allow)
        base = self.matrix()
        if labels is None:
            return topk_from_distances(
                distances(q, base, self.metric), np.arange(len(self), dtype=np.int64), k
            )
        if labels.size == 0:
            return empty_result()
        return topk_from_distances(distances(q, base[labels], self.metric), labels, k)

    def search_labels(self, query: npt.ArrayLike, k: int, labels: LabelArray) -> SearchResult:
        """Exact search restricted to an explicit label set (used for selective filters)."""
        q = self._check_query(query, k)
        if labels.size == 0:
            return empty_result()
        return topk_from_distances(distances(q, self.matrix()[labels], self.metric), labels, k)

    def search_batch(self, queries: npt.ArrayLike, k: int, chunk: int = 256) -> LabelArray:
        """Exact top-k labels for many queries; rows padded with -1 if k > len(self).

        Chunked so the (queries x base) distance matrix stays bounded in memory on SIFT-sized data.
        """
        qs = np.atleast_2d(np.asarray(queries, dtype=np.float32))
        out = np.full((qs.shape[0], k), -1, dtype=np.int64)
        base = self.matrix()
        all_labels = np.arange(len(self), dtype=np.int64)
        for s in range(0, qs.shape[0], chunk):
            block = distance_matrix(qs[s : s + chunk], base, self.metric)
            for i, row in enumerate(block):
                res = topk_from_distances(row, all_labels, k)
                out[s + i, : res.labels.size] = res.labels
        return out

    def memory_bytes(self) -> int:
        return self._vectors.nbytes()

    def save(self, path: Path) -> None:
        self._write_header(path, {})
        np.save(path / "vectors.npy", self.matrix())

    @classmethod
    def load(cls, path: Path) -> FlatIndex:
        header = cls._read_header(path, cls.kind)
        index = cls(header["dim"], header["metric"])
        vecs = np.load(path / "vectors.npy")
        if len(vecs):
            index._vectors.append(vecs)
        index._read_deleted(path)
        return index
