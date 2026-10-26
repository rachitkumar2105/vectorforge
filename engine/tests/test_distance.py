import numpy as np
import pytest

from vectorforge.core.distance import (
    DimensionMismatchError,
    cosine_similarity,
    distance_matrix,
    distances,
    inner_product,
    l2_squared,
)

Q = np.array([1.0, 0.0], dtype=np.float32)
X = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0], [3.0, 4.0]], dtype=np.float32)


def test_l2_squared_known_answer() -> None:
    np.testing.assert_allclose(l2_squared(Q, X), [0.0, 2.0, 4.0, 20.0])


def test_inner_product_known_answer() -> None:
    np.testing.assert_allclose(inner_product(Q, X), [1.0, 0.0, -1.0, 3.0])


def test_cosine_similarity_known_answer() -> None:
    np.testing.assert_allclose(cosine_similarity(Q, X), [1.0, 0.0, -1.0, 0.6], rtol=1e-6)


def test_distances_are_smaller_is_closer_for_every_metric() -> None:
    np.testing.assert_allclose(distances(Q, X, "l2"), [0.0, 2.0, 4.0, 20.0])
    # Inner product is negated so that the most similar vector has the smallest distance.
    np.testing.assert_allclose(distances(Q, X, "ip"), [-1.0, 0.0, 1.0, -3.0])
    np.testing.assert_allclose(distances(Q, X, "cosine"), [0.0, 1.0, 2.0, 0.4], rtol=1e-6)


def test_cosine_handles_zero_vectors_without_nan() -> None:
    zero = np.zeros(2, dtype=np.float32)
    with np.errstate(all="raise"):
        sims = cosine_similarity(zero, X)
        sims2 = cosine_similarity(Q, np.zeros((3, 2), dtype=np.float32))
    assert np.all(np.isfinite(sims)) and np.all(sims == 0.0)
    assert np.all(sims2 == 0.0)
    np.testing.assert_allclose(distances(zero, X, "cosine"), [1.0, 1.0, 1.0, 1.0])


def test_dimension_mismatch_raises_typed_error() -> None:
    with pytest.raises(DimensionMismatchError):
        l2_squared(np.zeros(3, dtype=np.float32), X)
    with pytest.raises(DimensionMismatchError):
        distance_matrix(np.zeros((2, 3), dtype=np.float32), X, "l2")
    # The typed error is still a ValueError, so generic handlers keep working.
    assert issubclass(DimensionMismatchError, ValueError)


def test_unknown_metric_raises() -> None:
    with pytest.raises(ValueError, match="metric"):
        distances(Q, X, "manhattan")  # type: ignore[arg-type]


@pytest.mark.parametrize("metric", ["l2", "ip", "cosine"])
def test_distance_matrix_matches_row_by_row(metric: str) -> None:
    rng = np.random.default_rng(0)
    queries = rng.standard_normal((7, 16)).astype(np.float32)
    base = rng.standard_normal((50, 16)).astype(np.float32)
    full = distance_matrix(queries, base, metric)  # type: ignore[arg-type]
    assert full.shape == (7, 50)
    for i, q in enumerate(queries):
        np.testing.assert_allclose(full[i], distances(q, base, metric), rtol=1e-4, atol=1e-4)  # type: ignore[arg-type]


def test_l2_matrix_is_never_negative() -> None:
    # ||q||^2 - 2 q.x + ||x||^2 can go slightly negative from float error when q == x.
    rng = np.random.default_rng(1)
    base = (rng.standard_normal((20, 64)) * 1000).astype(np.float32)
    full = distance_matrix(base, base, "l2")
    assert np.all(full >= 0.0)
