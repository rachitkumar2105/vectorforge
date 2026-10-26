"""Per-dimension int8 scalar quantization.

Each dimension d gets its own range [min_d, max_d], learned from training data, split into 256
evenly spaced levels. A float x is stored as the nearest level index, shifted into int8.

Error bound (for values inside the training range): ``|x - decode(encode(x))| <= step_d / 2``
where ``step_d = (max_d - min_d) / 255``. Values outside the range are clipped to it, so their
error is the clipping distance plus at most half a step.

Memory: 1 byte per dimension instead of 4, plus 8 bytes per dimension for min and step. For any
realistic n this is a 4x saving on vector storage.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

_LEVELS = 255  # 256 codes -> 255 intervals between the lowest and highest level
_SHIFT = 128  # uint8 [0, 255] -> int8 [-128, 127]


@dataclass(frozen=True)
class ScalarQuantizer:
    vmin: npt.NDArray[np.float32]
    step: npt.NDArray[np.float32]

    @classmethod
    def fit(cls, x: npt.ArrayLike) -> ScalarQuantizer:
        arr = np.atleast_2d(np.asarray(x, dtype=np.float32))
        if arr.shape[0] == 0:
            raise ValueError("cannot fit a quantizer on zero vectors")
        vmin = arr.min(axis=0)
        span = arr.max(axis=0) - vmin
        # A constant dimension has span 0. Any positive step works there because every value
        # encodes to code 0 and decodes back to vmin exactly; 1.0 avoids dividing by zero.
        step = np.where(span > 0, span / _LEVELS, np.float32(1.0)).astype(np.float32)
        return cls(vmin.astype(np.float32), step)

    @property
    def dim(self) -> int:
        return int(self.vmin.shape[0])

    def encode(self, x: npt.ArrayLike) -> npt.NDArray[np.int8]:
        arr = np.atleast_2d(np.asarray(x, dtype=np.float32))
        levels = np.rint((arr - self.vmin) / self.step)
        return (np.clip(levels, 0, _LEVELS) - _SHIFT).astype(np.int8)

    def decode(self, codes: npt.NDArray[np.int8]) -> npt.NDArray[np.float32]:
        levels = codes.astype(np.float32) + _SHIFT
        out: npt.NDArray[np.float32] = (levels * self.step + self.vmin).astype(np.float32)
        return out

    def max_abs_error(self) -> npt.NDArray[np.float32]:
        """Per-dimension worst-case reconstruction error for in-range values."""
        return (self.step / 2).astype(np.float32)

    def nbytes(self) -> int:
        return int(self.vmin.nbytes + self.step.nbytes)
