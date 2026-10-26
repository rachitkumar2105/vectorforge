"""A collection ties an index to durable storage and to per-vector metadata.

Directory layout::

    <root>/<name>/
        manifest.json          atomic; names the current snapshot and its checkpoint LSN
        wal.log                operations after the checkpoint
        segments/seg_*.vec     raw vectors by label (memory-mapped)
        index-<lsn>/           index snapshot taken at that checkpoint
        state-<lsn>.json       id <-> label map and metadata at that checkpoint

Write path: validate -> WAL append + fsync -> apply (segment, index, maps) -> maybe checkpoint.
Recovery:   manifest -> snapshot -> replay WAL records with lsn > checkpoint_lsn.
"""

from __future__ import annotations

import re
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from vectorforge.core.distance import Metric, check_metric, distances
from vectorforge.index.base import Allow, Index, SearchResult, topk_from_distances
from vectorforge.index.flat import FlatIndex
from vectorforge.index.hnsw import HNSWIndex
from vectorforge.index.ivf import IVFIndex
from vectorforge.storage.metadata import Manifest, atomic_write_json, read_json
from vectorforge.storage.segment import SegmentStore
from vectorforge.storage.wal import Op, RecordTooLargeError, WalRecord, WriteAheadLog

INDEX_TYPES = ("hnsw", "ivf", "flat")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
Scalar = str | int | float | bool
Payload = dict[str, Any]

# Below this fraction of matching vectors, graph traversal spends almost all its time walking
# through non-matching nodes and can stall in regions with no matches, so recall collapses. An
# exact scan over just the matches is both faster and exact there.
EXACT_FILTER_FRACTION = 0.05


class FilterError(ValueError):
    """The metadata filter is malformed."""


class VectorValidationError(ValueError):
    """An upserted item is invalid (dimension, non-finite values, record too large)."""


class CollectionClosedError(KeyError):
    """The collection was closed or dropped while a caller still held a reference to it."""


@dataclass(frozen=True)
class UpsertItem:
    id: str
    vector: npt.NDArray[np.float32]
    metadata: Payload


@dataclass(frozen=True)
class Hit:
    id: str
    distance: float
    metadata: Payload | None


@dataclass(frozen=True)
class SearchOutput:
    hits: list[Hit]
    strategy: str


def compile_filter(spec: dict[str, Any] | None) -> Callable[[Payload | None], bool] | None:
    """Compile ``{"field": value, "other": {"in": [v1, v2]}}`` into a predicate (AND of terms).

    Deliberately tiny: equality and set membership on scalar fields. Enough for the demo and for
    explaining filtered HNSW; a richer language is out of scope.
    """
    if spec is None:
        return None
    terms: list[tuple[str, frozenset[Scalar]]] = []
    for key, cond in spec.items():
        if not isinstance(key, str) or not key:
            raise FilterError("filter keys must be non-empty strings")
        if isinstance(cond, dict):
            if set(cond) != {"in"} or not isinstance(cond["in"], list):
                raise FilterError(f"filter on {key!r}: only {{'in': [..]}} is supported")
            values = cond["in"]
        elif isinstance(cond, str | int | float | bool):
            values = [cond]
        else:
            raise FilterError(f"filter on {key!r} must be a scalar or {{'in': [..]}}")
        if not all(isinstance(v, str | int | float | bool) for v in values):
            raise FilterError(f"filter on {key!r}: values must be scalars")
        terms.append((key, frozenset(values)))

    def predicate(payload: Payload | None) -> bool:
        if payload is None:
            return False
        return all(key in payload and payload[key] in allowed for key, allowed in terms)

    return predicate


def _new_index(dim: int, metric: Metric, index_type: str, params: dict[str, Any]) -> Index:
    if index_type == "hnsw":
        return HNSWIndex(dim, metric, **params)
    if index_type == "ivf":
        return IVFIndex(dim, metric, **params)
    if index_type == "flat":
        return FlatIndex(dim, metric)
    raise ValueError(f"unknown index type {index_type!r}; expected one of {INDEX_TYPES}")


class Collection:
    def __init__(self, path: Path, manifest: Manifest, checkpoint_every: int) -> None:
        self.path = path
        self.manifest = manifest
        self.checkpoint_every = checkpoint_every
        self.metric: Metric = check_metric(manifest.metric)
        self._lock = threading.RLock()
        self._closed = False
        self._ids: dict[str, int] = {}
        self._label_ids: list[str | None] = []
        self._payloads: list[Payload | None] = []
        self._lsn = manifest.checkpoint_lsn
        self._since_checkpoint = 0
        self.segments = SegmentStore(
            path / "segments", manifest.dim, manifest.segment_capacity or None, manifest.count
        )
        self.index = self._load_snapshot()
        self.wal_path = path / "wal.log"
        self.replay_report = self._replay()
        self.wal = WriteAheadLog(self.wal_path)

    # -- lifecycle -------------------------------------------------------------------------
    @classmethod
    def create(
        cls,
        root: Path,
        name: str,
        *,
        dim: int,
        metric: str,
        index_type: str,
        index_params: dict[str, Any] | None = None,
        checkpoint_every: int = 10_000,
    ) -> Collection:
        if not NAME_RE.match(name):
            raise ValueError("invalid collection name")
        params = dict(index_params or {})
        # Build once to validate type, metric and params before touching the disk.
        _new_index(dim, check_metric(metric), index_type, params)
        path = root / name
        if (path / Manifest.FILENAME).exists():
            raise FileExistsError(name)
        path.mkdir(parents=True, exist_ok=True)
        manifest = Manifest(
            name=name, dim=dim, metric=metric, index_type=index_type, index_params=params
        )
        manifest.segment_capacity = SegmentStore(path / "segments", dim).capacity
        # The manifest is written last: a directory without one is an aborted create.
        manifest.save(path)
        return cls(path, manifest, checkpoint_every)

    @classmethod
    def open(cls, path: Path, checkpoint_every: int = 10_000) -> Collection:
        return cls(path, Manifest.load(path), checkpoint_every)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            if self._since_checkpoint:
                self.checkpoint()
            self._release_files()
            self._closed = True

    def _check_open(self) -> None:
        # Requests take a reference before acquiring the lock, so a concurrent drop can win the
        # race. They must fail cleanly instead of touching closed files.
        if self._closed:
            raise CollectionClosedError(self.manifest.name)

    def _release_files(self) -> None:
        self.wal.close()
        self.segments.close()

    def drop(self) -> None:
        with self._lock:
            self._closed = True
            self._release_files()
            shutil.rmtree(self.path)

    # -- recovery --------------------------------------------------------------------------
    def _load_snapshot(self) -> Index:
        m = self.manifest
        metric = self.metric
        if m.state_file is None:
            return _new_index(m.dim, metric, m.index_type, m.index_params)
        state = read_json(self.path / m.state_file)
        self._label_ids = state["label_ids"]
        self._payloads = state["payloads"]
        self._ids = {i: label for label, i in enumerate(self._label_ids) if i is not None}
        if m.index_type == "flat":
            # Flat has no structure beyond the vectors, so it is rebuilt from segments.
            flat = FlatIndex(m.dim, metric)
            if m.count:
                flat.add(self.segments.read_all())
            for label, ident in enumerate(self._label_ids):
                if ident is None:
                    flat.delete(label)
            return flat
        assert m.index_dir is not None
        if m.index_type == "hnsw":
            return HNSWIndex.load(self.path / m.index_dir, vectors=self.segments.read_all())
        return IVFIndex.load(self.path / m.index_dir)

    def _replay(self) -> Any:
        records, report = WriteAheadLog.replay(self.wal_path)
        for rec in records:
            # Records at or below the checkpoint are already in the snapshot. They exist only if
            # the process died between writing the manifest and truncating the WAL.
            if rec.lsn <= self.manifest.checkpoint_lsn:
                continue
            self._apply(rec)
            self._lsn = rec.lsn
            self._since_checkpoint += 1
        return report

    # -- writes ----------------------------------------------------------------------------
    def _validate(self, item: UpsertItem) -> npt.NDArray[np.float32]:
        v = np.asarray(item.vector, dtype=np.float32).reshape(-1)
        if v.shape[0] != self.manifest.dim:
            raise VectorValidationError(
                f"vector {item.id!r} has dimension {v.shape[0]}, expected {self.manifest.dim}"
            )
        if not np.all(np.isfinite(v)):
            raise VectorValidationError(f"vector {item.id!r} contains non-finite values")
        return v

    def upsert(self, items: list[UpsertItem]) -> int:
        vectors = [self._validate(it) for it in items]  # reject the whole batch before logging
        with self._lock:
            self._check_open()
            records = [
                WalRecord(
                    lsn=self._lsn + i, op=Op.UPSERT, ident=it.id, vector=v, metadata=it.metadata
                )
                for i, (it, v) in enumerate(zip(items, vectors, strict=True), start=1)
            ]
            try:
                self.wal.append(records)  # durable from here on
            except RecordTooLargeError as exc:
                raise VectorValidationError(str(exc)) from None
            # Advance the LSN only once the batch is on disk, so a refused batch leaves no gap.
            self._lsn += len(records)
            for rec in records:
                self._apply(rec)
            self._after_write(len(records))
        return len(items)

    def delete(self, ident: str) -> None:
        with self._lock:
            self._check_open()
            if ident not in self._ids:
                raise KeyError(ident)
            self._lsn += 1
            rec = WalRecord(lsn=self._lsn, op=Op.DELETE, ident=ident)
            self.wal.append([rec])
            self._apply(rec)
            self._after_write(1)

    def _apply(self, rec: WalRecord) -> None:
        old = self._ids.pop(rec.ident, None)
        if old is not None:
            # Re-upsert or delete: tombstone the old label. Labels are never reused, which keeps
            # HNSW's no-hard-delete rule and keeps segments append-only.
            self.index.delete(old)
            self._label_ids[old] = None
            self._payloads[old] = None
        if rec.op is Op.DELETE:
            return
        assert rec.vector is not None
        # One vector at a time, in LSN order: replay then reproduces the exact same labels, the
        # same HNSW levels (seeded RNG) and the same IVF training point as the original run.
        label = int(self.index.add(rec.vector[None, :])[0])
        self.segments.write(label, rec.vector)
        self._label_ids.append(rec.ident)
        self._payloads.append(rec.metadata)
        self._ids[rec.ident] = label

    def _after_write(self, n: int) -> None:
        self._since_checkpoint += n
        if self._since_checkpoint >= self.checkpoint_every:
            self.checkpoint()

    def checkpoint(self) -> None:
        """Snapshot everything up to the current LSN, then empty the WAL.

        Order matters. New snapshot files are written under new names first; the manifest swap
        is the single atomic commit point; old files and the WAL are cleaned up only after it.
        A crash at any step leaves either the old manifest (old snapshot + full WAL) or the new
        one (new snapshot + WAL records it will skip by LSN).
        """
        with self._lock:
            lsn = self._lsn
            self.segments.flush()
            index_dir = f"index-{lsn}"
            state_file = f"state-{lsn}.json"
            if self.manifest.index_type == "hnsw":
                assert isinstance(self.index, HNSWIndex)
                self.index.save(self.path / index_dir, include_vectors=False)
            elif self.manifest.index_type == "ivf":
                self.index.save(self.path / index_dir)
            atomic_write_json(
                self.path / state_file,
                {"label_ids": self._label_ids, "payloads": self._payloads},
            )
            old_index, old_state = self.manifest.index_dir, self.manifest.state_file
            self.manifest.checkpoint_lsn = lsn
            self.manifest.count = len(self._label_ids)
            self.manifest.index_dir = index_dir if self.manifest.index_type != "flat" else None
            self.manifest.state_file = state_file
            self.manifest.save(self.path)
            if old_index and old_index != index_dir:
                shutil.rmtree(self.path / old_index, ignore_errors=True)
            if old_state and old_state != state_file:
                (self.path / old_state).unlink(missing_ok=True)
            self.wal.truncate()
            self._since_checkpoint = 0

    # -- reads -----------------------------------------------------------------------------
    @property
    def count(self) -> int:
        return len(self._ids)

    @property
    def deleted_count(self) -> int:
        return len(self._label_ids) - len(self._ids)

    def get(self, ident: str) -> tuple[npt.NDArray[np.float32], Payload]:
        with self._lock:
            self._check_open()
            label = self._ids[ident]
            payload = self._payloads[label]
            assert payload is not None
            return self.segments.read([label])[0], payload

    def search(
        self,
        vector: npt.ArrayLike,
        k: int,
        *,
        ef_search: int | None = None,
        nprobe: int | None = None,
        filter: dict[str, Any] | None = None,
        include_metadata: bool = True,
    ) -> SearchOutput:
        predicate = compile_filter(filter)
        q = np.asarray(vector, dtype=np.float32).reshape(-1)
        with self._lock:
            self._check_open()
            strategy = {"hnsw": "graph", "ivf": "ivf", "flat": "exact"}[self.manifest.index_type]
            allow: Allow | None = None
            if predicate is not None:
                matches = [
                    label
                    for label, p in enumerate(self._payloads)
                    if p is not None and predicate(p)
                ]
                if not matches:
                    return SearchOutput([], "exact_filtered")
                if len(matches) <= max(k, EXACT_FILTER_FRACTION * len(self._label_ids)):
                    return self._wrap(
                        self._exact(q, k, matches), "exact_filtered", include_metadata
                    )
                allowed = set(matches)
                allow = allowed.__contains__
            result = self.index.search(q, k, allow=allow, ef_search=ef_search, nprobe=nprobe)
            return self._wrap(result, strategy, include_metadata)

    def _exact(self, q: npt.NDArray[np.float32], k: int, labels: list[int]) -> SearchResult:
        if q.shape[0] != self.manifest.dim:
            raise ValueError("query dimension does not match the collection")
        mat = self.segments.read(labels)
        return topk_from_distances(
            distances(q, mat, self.metric), np.asarray(labels, dtype=np.int64), k
        )

    def _wrap(self, result: SearchResult, strategy: str, include_metadata: bool) -> SearchOutput:
        hits = []
        for label, dist in zip(result.labels.tolist(), result.distances.tolist(), strict=True):
            ident = self._label_ids[label]
            if ident is None:  # pragma: no cover - indexes already exclude tombstones
                continue
            hits.append(
                Hit(ident, float(dist), self._payloads[label] if include_metadata else None)
            )
        return SearchOutput(hits, strategy)

    def info(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.manifest.name,
                "dim": self.manifest.dim,
                "metric": self.manifest.metric,
                "index": {"type": self.manifest.index_type, "params": self.manifest.index_params},
                "count": self.count,
                "deleted": self.deleted_count,
                "memory_bytes": self.index.memory_bytes(),
            }
