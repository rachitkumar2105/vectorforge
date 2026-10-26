"""A growable 2-D array with amortised O(1) appends."""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt


class GrowableMatrix:
    """Rows are appended into a pre-allocated buffer that doubles when full.

    ``np.vstack`` on every insert would copy the whole matrix each time (O(n^2) for n inserts).
    Doubling keeps total copying O(n) and lets ``view()`` return a zero-copy slice.
    """

    def __init__(self, dim: int, dtype: npt.DTypeLike = np.float32, capacity: int = 1024) -> None:
        self.dim = dim
        self._buf = np.zeros((max(capacity, 1), dim), dtype=dtype)
        self._n = 0

    def __len__(self) -> int:
        return self._n

    def append(self, rows: npt.NDArray[Any]) -> int:
        """Append rows; returns the index of the first appended row."""
        start = self._n
        need = self._n + rows.shape[0]
        if need > self._buf.shape[0]:
            new_cap = max(need, self._buf.shape[0] * 2)
            grown = np.zeros((new_cap, self.dim), dtype=self._buf.dtype)
            grown[: self._n] = self._buf[: self._n]
            self._buf = grown
        self._buf[self._n : need] = rows
        self._n = need
        return start

    def view(self) -> npt.NDArray[Any]:
        return self._buf[: self._n]

    def row(self, i: int) -> npt.NDArray[Any]:
        row: npt.NDArray[Any] = self._buf[i]
        return row

    def nbytes(self) -> int:
        # Report used rows, not spare capacity, so memory numbers are comparable across indexes.
        return int(self._n * self.dim * self._buf.dtype.itemsize)
