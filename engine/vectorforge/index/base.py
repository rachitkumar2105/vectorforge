"""The contract every index implements."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import numpy as np
import numpy.typing as npt

from vectorforge.core.distance import DimensionMismatchError, Metric, check_metric

# A predicate over internal labels. Used for tombstones-plus-metadata filtering during search.
Allow = Callable[[int], bool]

LabelArray = npt.NDArray[np.int64]

T = TypeVar("T", bound="Index")


@dataclass(frozen=True)
class SearchResult:
    labels: LabelArray
    distances: npt.NDArray[np.float32]


def empty_result() -> SearchResult:
    return SearchResult(np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float32))


class Index(ABC):
    """Base class: dense integer labels, tombstone deletes, directory-based persistence.

    Labels are assigned by the index in insertion order (0, 1, 2, ...). Dense labels let every
    index store vectors in a plain array and use the label as the row number.
    """

    kind: str = "base"

    def __init__(self, dim: int, metric: Metric) -> None:
        if not isinstance(dim, int) or dim < 1:
            raise ValueError("dim must be a positive integer")
        self.dim = dim
        self.metric: Metric = check_metric(metric)
        self._deleted: set[int] = set()

    # -- validation helpers ---------------------------------------------------------------
    def _check_vectors(self, vectors: npt.ArrayLike) -> npt.NDArray[np.float32]:
        arr = np.atleast_2d(np.asarray(vectors, dtype=np.float32))
        if arr.ndim != 2 or arr.shape[1] != self.dim:
            raise DimensionMismatchError(
                f"expected vectors of dimension {self.dim}, got shape {arr.shape}"
            )
        if not np.all(np.isfinite(arr)):
            raise ValueError("vectors must contain only finite values")
        return arr

    def _check_query(self, query: npt.ArrayLike, k: int) -> npt.NDArray[np.float32]:
        if not isinstance(k, int) or k < 1:
            raise ValueError("k must be a positive integer")
        q = np.asarray(query, dtype=np.float32).reshape(-1)
        if q.shape[0] != self.dim:
            raise DimensionMismatchError(f"expected query of dimension {self.dim}, got {q.shape}")
        if not np.all(np.isfinite(q)):
            raise ValueError("query must contain only finite values")
        return q

    # -- the contract ---------------------------------------------------------------------
    @abstractmethod
    def add(self, vectors: npt.ArrayLike) -> LabelArray: ...

    @abstractmethod
    def search(
        self, query: npt.ArrayLike, k: int, *, allow: Allow | None = None, **params: Any
    ) -> SearchResult: ...

    @abstractmethod
    def __len__(self) -> int: ...

    @abstractmethod
    def vector(self, label: int) -> npt.NDArray[np.float32]: ...

    def delete(self, label: int) -> None:
        """Tombstone a label: it stays in the structure but never appears in results."""
        if not 0 <= label < len(self):
            raise KeyError(label)
        self._deleted.add(int(label))

    def is_deleted(self, label: int) -> bool:
        return label in self._deleted

    @property
    def deleted_count(self) -> int:
        return len(self._deleted)

    def stats(self) -> dict[str, Any]:
        return {
            "type": self.kind,
            "dim": self.dim,
            "metric": self.metric,
            "count": len(self),
            "deleted": len(self._deleted),
            "memory_bytes": self.memory_bytes(),
        }

    @abstractmethod
    def memory_bytes(self) -> int:
        """Approximate resident bytes of the index's own data structures."""

    # -- persistence ----------------------------------------------------------------------
    @abstractmethod
    def save(self, path: Path) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls: type[T], path: Path) -> T: ...

    def _write_header(self, path: Path, extra: dict[str, Any]) -> None:
        path.mkdir(parents=True, exist_ok=True)
        header = {"kind": self.kind, "dim": self.dim, "metric": self.metric, **extra}
        (path / "header.json").write_text(json.dumps(header, sort_keys=True), encoding="utf-8")
        np.save(path / "deleted.npy", np.array(sorted(self._deleted), dtype=np.int64))

    @staticmethod
    def _read_header(path: Path, kind: str) -> dict[str, Any]:
        header: dict[str, Any] = json.loads((path / "header.json").read_text(encoding="utf-8"))
        if header.get("kind") != kind:
            raise ValueError(f"{path} holds a {header.get('kind')!r} index, not {kind!r}")
        return header

    def _read_deleted(self, path: Path) -> None:
        self._deleted = {int(x) for x in np.load(path / "deleted.npy")}


def topk_from_distances(dists: npt.NDArray[np.float32], labels: LabelArray, k: int) -> SearchResult:
    """Top-k of a distance vector in ascending order, ties broken by label for determinism."""
    if dists.size == 0:
        return empty_result()
    k = min(k, dists.size)
    if k < dists.size:
        # argpartition is O(n); a full sort would be O(n log n) for no benefit.
        part = np.argpartition(dists, k - 1)[:k]
    else:
        part = np.arange(dists.size)
    order = np.lexsort((labels[part], dists[part]))
    sel = part[order]
    return SearchResult(labels[sel].astype(np.int64), dists[sel].astype(np.float32))
