"""Distance functions, vectorized over a matrix of base vectors.

Convention used everywhere in VectorForge: a *distance* is "smaller is closer". Inner product is
a similarity, so ``distances(..., "ip")`` returns its negation, and cosine distance is
``1 - cosine_similarity``. Indexes only ever need one ordering rule because of this.
"""

from __future__ import annotations

from typing import Literal, get_args

import numpy as np
import numpy.typing as npt

Metric = Literal["l2", "ip", "cosine"]
METRICS: tuple[str, ...] = get_args(Metric)

FloatArray = npt.NDArray[np.float32]


class DimensionMismatchError(ValueError):
    """A vector's dimension does not match the index or the other operand."""


def check_metric(metric: str) -> Metric:
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}; expected one of {METRICS}")
    return metric  # type: ignore[return-value]


def _check_pair(q: npt.ArrayLike, base: npt.ArrayLike) -> tuple[FloatArray, FloatArray]:
    qa = np.asarray(q, dtype=np.float32)
    ba = np.asarray(base, dtype=np.float32)
    if ba.ndim != 2:
        raise ValueError("base must be a 2-D matrix")
    if qa.shape[-1] != ba.shape[1]:
        raise DimensionMismatchError(f"dimension {qa.shape[-1]} does not match {ba.shape[1]}")
    return qa, ba


def l2_squared(q: npt.ArrayLike, base: npt.ArrayLike) -> FloatArray:
    """Squared Euclidean distance from ``q`` to every row of ``base``.

    Squared, not rooted: sqrt is monotonic, so it never changes a ranking, and skipping it saves
    work on every comparison in the graph search.
    """
    qa, ba = _check_pair(q, base)
    diff = ba - qa
    # einsum computes the row-wise dot of diff with itself without materialising diff**2.
    out: FloatArray = np.einsum("ij,ij->i", diff, diff)
    return out


def inner_product(q: npt.ArrayLike, base: npt.ArrayLike) -> FloatArray:
    qa, ba = _check_pair(q, base)
    return ba @ qa


def _safe_norms(m: FloatArray) -> FloatArray:
    norms = np.linalg.norm(m, axis=-1)
    # A zero vector has no direction. Dividing by 1 instead of 0 makes its similarity to
    # anything exactly 0 (its dot product is 0), which is the conventional answer.
    return np.where(norms == 0.0, np.float32(1.0), norms).astype(np.float32)


def cosine_similarity(q: npt.ArrayLike, base: npt.ArrayLike) -> FloatArray:
    qa, ba = _check_pair(q, base)
    dots = ba @ qa
    return (dots / (_safe_norms(ba) * _safe_norms(qa))).astype(np.float32)


def distances(q: npt.ArrayLike, base: npt.ArrayLike, metric: Metric) -> FloatArray:
    """Smaller-is-closer distance from one query to every row of ``base``."""
    check_metric(metric)
    if metric == "l2":
        return l2_squared(q, base)
    if metric == "ip":
        return -inner_product(q, base)
    return (1.0 - cosine_similarity(q, base)).astype(np.float32)


def distance_matrix(queries: npt.ArrayLike, base: npt.ArrayLike, metric: Metric) -> FloatArray:
    """All-pairs distances, shape ``(len(queries), len(base))``.

    Used for ground truth and k-means, where many queries hit the same base matrix. It turns the
    work into one matrix multiply (BLAS) instead of a Python loop over queries.
    """
    check_metric(metric)
    qa = np.atleast_2d(np.asarray(queries, dtype=np.float32))
    _, ba = _check_pair(qa, base)
    dots = qa @ ba.T
    if metric == "ip":
        return -dots
    if metric == "cosine":
        sims = dots / np.outer(_safe_norms(qa), _safe_norms(ba))
        return (1.0 - sims).astype(np.float32)
    # ||q - x||^2 = ||q||^2 - 2 q.x + ||x||^2. Cancellation can produce tiny negatives when
    # q == x, so clamp at zero to keep the "distance >= 0" invariant.
    q_sq: FloatArray = np.einsum("ij,ij->i", qa, qa)
    b_sq: FloatArray = np.einsum("ij,ij->i", ba, ba)
    sq = q_sq[:, None] - 2.0 * dots + b_sq[None, :]
    return np.maximum(sq, 0.0).astype(np.float32)


def normalize_rows(m: npt.ArrayLike) -> FloatArray:
    """Unit-normalise rows; zero rows stay zero."""
    arr = np.atleast_2d(np.asarray(m, dtype=np.float32))
    return (arr / _safe_norms(arr)[:, None]).astype(np.float32)
