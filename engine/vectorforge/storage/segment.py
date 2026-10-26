"""Fixed-size, append-only, memory-mapped vector segments.

Vectors are stored by label: label L lives in segment ``L // capacity`` at row ``L % capacity``.
Each segment file is pre-allocated to its full size, so writing a row never changes the file
length and the OS can page rows in and out on demand.

Durability contract: segments are *not* the commit point. A row is durable once its WAL record
is fsynced; segments are flushed at checkpoint time. After a crash, rows above the manifest's
``count`` may hold garbage, and WAL replay rewrites them. That is why ``count`` comes from the
manifest on open rather than from the files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

SEGMENT_TARGET_BYTES = 32 * 1024 * 1024


class SegmentStore:
    def __init__(self, root: Path, dim: int, capacity: int | None = None, count: int = 0) -> None:
        self.root = root
        self.dim = dim
        self.capacity = capacity or max(1024, SEGMENT_TARGET_BYTES // (dim * 4))
        self.count = count
        root.mkdir(parents=True, exist_ok=True)
        self._maps: list[np.memmap[Any, np.dtype[np.float32]]] = []
        n_segments = -(-count // self.capacity)  # ceil division
        for i in range(n_segments):
            self._open_segment(i)

    def _segment_path(self, i: int) -> Path:
        return self.root / f"seg_{i:06d}.vec"

    def _open_segment(self, i: int) -> None:
        path = self._segment_path(i)
        size = self.capacity * self.dim * 4
        if not path.exists() or path.stat().st_size != size:
            with path.open("ab") as f:
                f.truncate(size)  # sparse, zero-filled pre-allocation
        self._maps.append(
            np.memmap(path, dtype=np.float32, mode="r+", shape=(self.capacity, self.dim))
        )

    def write(self, label: int, vector: npt.NDArray[np.float32]) -> None:
        """Write a row. Labels must arrive in order; rewriting an existing label is allowed so
        that WAL replay is idempotent."""
        if vector.shape != (self.dim,):
            raise ValueError(f"expected a vector of dimension {self.dim}")
        if label > self.count:
            raise ValueError("segments are append-only: labels must be written in order")
        seg, row = divmod(label, self.capacity)
        while seg >= len(self._maps):
            self._open_segment(len(self._maps))
        self._maps[seg][row] = vector
        self.count = max(self.count, label + 1)

    def read(self, labels: list[int]) -> npt.NDArray[np.float32]:
        out = np.empty((len(labels), self.dim), dtype=np.float32)
        for i, label in enumerate(labels):
            seg, row = divmod(label, self.capacity)
            out[i] = self._maps[seg][row]
        return out

    def read_all(self) -> npt.NDArray[np.float32]:
        """A contiguous in-RAM copy of rows [0, count). Copying (not viewing) means no numpy
        array keeps a segment file mapped, so files can be closed and deleted on Windows."""
        if self.count == 0:
            return np.empty((0, self.dim), dtype=np.float32)
        parts = []
        remaining = self.count
        for mm in self._maps:
            take = min(remaining, self.capacity)
            parts.append(np.array(mm[:take]))
            remaining -= take
            if remaining == 0:
                break
        return np.concatenate(parts)

    def flush(self) -> None:
        for mm in self._maps:
            mm.flush()

    def close(self) -> None:
        self.flush()
        # Dropping the references unmaps the files (needed before deleting them on Windows).
        self._maps.clear()
