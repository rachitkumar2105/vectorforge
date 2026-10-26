import math
from pathlib import Path

import numpy as np
import pytest

from vectorforge.core.distance import DimensionMismatchError
from vectorforge.index.flat import FlatIndex
from vectorforge.metrics import recall_at_k


def naive_topk(q: np.ndarray, base: np.ndarray, k: int, metric: str) -> list[int]:
    """Pure-Python reference: no NumPy vectorization, so it checks flat.py independently."""
    scored = []
    for i, row in enumerate(base):
        if metric == "l2":
            d = sum((float(a) - float(b)) ** 2 for a, b in zip(q, row, strict=True))
        elif metric == "ip":
            d = -sum(float(a) * float(b) for a, b in zip(q, row, strict=True))
        else:
            dot = sum(float(a) * float(b) for a, b in zip(q, row, strict=True))
            nq = math.sqrt(sum(float(a) ** 2 for a in q))
            nr = math.sqrt(sum(float(b) ** 2 for b in row))
            d = 1.0 - (dot / (nq * nr) if nq and nr else 0.0)
        scored.append((d, i))
    scored.sort()
    return [i for _, i in scored[:k]]


@pytest.mark.parametrize("metric", ["l2", "ip", "cosine"])
def test_flat_matches_naive_python_loop_on_1000_vectors(metric: str) -> None:
    rng = np.random.default_rng(42)
    base = rng.standard_normal((1000, 12)).astype(np.float32)
    index = FlatIndex(dim=12, metric=metric)  # type: ignore[arg-type]
    index.add(base)
    for q in rng.standard_normal((5, 12)).astype(np.float32):
        result = index.search(q, k=10)
        assert result.labels.tolist() == naive_topk(q, base, 10, metric)
        assert np.all(np.diff(result.distances) >= 0)


def test_flat_recall_against_itself_is_exactly_one() -> None:
    rng = np.random.default_rng(7)
    base = rng.standard_normal((2000, 32)).astype(np.float32)
    queries = rng.standard_normal((50, 32)).astype(np.float32)
    index = FlatIndex(dim=32, metric="l2")
    index.add(base)
    truth = index.search_batch(queries, k=10)
    found = np.stack([index.search(q, k=10).labels for q in queries])
    assert recall_at_k(found, truth, 10) == 1.0


def test_add_returns_dense_labels_and_len() -> None:
    index = FlatIndex(dim=2, metric="l2")
    first = index.add(np.ones((3, 2), dtype=np.float32))
    second = index.add(np.zeros((2, 2), dtype=np.float32))
    assert first.tolist() == [0, 1, 2]
    assert second.tolist() == [3, 4]
    assert len(index) == 5


def test_dimension_mismatch_on_add_and_search() -> None:
    index = FlatIndex(dim=4, metric="l2")
    with pytest.raises(DimensionMismatchError):
        index.add(np.ones((2, 3), dtype=np.float32))
    index.add(np.ones((2, 4), dtype=np.float32))
    with pytest.raises(DimensionMismatchError):
        index.search(np.ones(5, dtype=np.float32), k=1)


def test_k_larger_than_index_and_empty_index() -> None:
    index = FlatIndex(dim=2, metric="l2")
    assert index.search(np.zeros(2, dtype=np.float32), k=5).labels.size == 0
    index.add(np.array([[0, 0], [1, 1]], dtype=np.float32))
    res = index.search(np.zeros(2, dtype=np.float32), k=5)
    assert res.labels.tolist() == [0, 1]


def test_invalid_k_rejected() -> None:
    index = FlatIndex(dim=2, metric="l2")
    with pytest.raises(ValueError):
        index.search(np.zeros(2, dtype=np.float32), k=0)


def test_delete_and_allow_predicate_exclude_labels() -> None:
    index = FlatIndex(dim=1, metric="l2")
    index.add(np.array([[0.0], [1.0], [2.0], [3.0]], dtype=np.float32))
    index.delete(0)
    assert index.search(np.zeros(1, dtype=np.float32), k=2).labels.tolist() == [1, 2]
    res = index.search(np.zeros(1, dtype=np.float32), k=2, allow=lambda label: label % 2 == 1)
    assert res.labels.tolist() == [1, 3]
    assert index.stats()["deleted"] == 1
    with pytest.raises(KeyError):
        index.delete(99)


def test_rejects_non_finite_vectors() -> None:
    index = FlatIndex(dim=2, metric="l2")
    with pytest.raises(ValueError, match="finite"):
        index.add(np.array([[np.nan, 1.0]], dtype=np.float32))


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    base = rng.standard_normal((100, 8)).astype(np.float32)
    index = FlatIndex(dim=8, metric="cosine")
    index.add(base)
    index.delete(5)
    index.save(tmp_path / "flat")
    loaded = FlatIndex.load(tmp_path / "flat")
    q = rng.standard_normal(8).astype(np.float32)
    a, b = index.search(q, k=10), loaded.search(q, k=10)
    assert a.labels.tolist() == b.labels.tolist()
    np.testing.assert_allclose(a.distances, b.distances)
    assert loaded.stats()["deleted"] == 1


def test_recall_at_k_helper() -> None:
    truth = np.array([[1, 2, 3], [4, 5, 6]])
    found = np.array([[1, 2, 9], [6, 5, 4]])
    assert recall_at_k(found, truth, 3) == pytest.approx((2 + 3) / 6)
    assert recall_at_k(found, truth, 1) == pytest.approx(0.5)
