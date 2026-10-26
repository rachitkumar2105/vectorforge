from pathlib import Path

import numpy as np
import pytest

from vectorforge.core.distance import DimensionMismatchError
from vectorforge.core.quantize import ScalarQuantizer
from vectorforge.index.flat import FlatIndex
from vectorforge.index.ivf import IVFIndex, kmeans
from vectorforge.metrics import recall_at_k


def clustered(n: int, dim: int, centers: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    means = rng.standard_normal((centers, dim)) * 5
    assign = rng.integers(0, centers, n)
    return (means[assign] + rng.standard_normal((n, dim))).astype(np.float32)


@pytest.fixture(scope="module")
def ivf_setup() -> tuple[IVFIndex, np.ndarray, np.ndarray]:
    base = clustered(8000, 16, centers=40, seed=1)
    queries = clustered(100, 16, centers=40, seed=2)
    index = IVFIndex(dim=16, metric="l2", nlist=32, seed=0)
    index.add(base)
    flat = FlatIndex(dim=16)
    flat.add(base)
    return index, queries, flat.search_batch(queries, k=10)


# -- quantization -----------------------------------------------------------------------------


def test_quantizer_round_trip_error_within_half_step() -> None:
    x = np.random.default_rng(0).standard_normal((2000, 32)).astype(np.float32) * 3
    sq = ScalarQuantizer.fit(x)
    codes = sq.encode(x)
    assert codes.dtype == np.int8
    err = np.abs(sq.decode(codes) - x)
    # Documented bound: half a quantization step per dimension, plus float32 rounding slack.
    bound = sq.max_abs_error() + 1e-5
    assert np.all(err <= bound[None, :])


def test_quantizer_clips_out_of_range_values() -> None:
    sq = ScalarQuantizer.fit(np.array([[0.0, 0.0], [1.0, 2.0]], dtype=np.float32))
    out = sq.decode(sq.encode(np.array([[5.0, -5.0]], dtype=np.float32)))
    np.testing.assert_allclose(out, [[1.0, 0.0]], atol=1e-6)


def test_quantizer_constant_dimension_is_exact() -> None:
    x = np.ones((10, 3), dtype=np.float32)
    x[:, 1] = np.arange(10)
    sq = ScalarQuantizer.fit(x)
    out = sq.decode(sq.encode(x))
    np.testing.assert_allclose(out[:, 0], 1.0)
    np.testing.assert_allclose(out[:, 2], 1.0)


def test_quantizer_memory_saving_is_about_4x() -> None:
    x = np.random.default_rng(1).standard_normal((10_000, 128)).astype(np.float32)
    sq = ScalarQuantizer.fit(x)
    codes = sq.encode(x)
    ratio = x.nbytes / (codes.nbytes + sq.nbytes())
    assert 3.9 < ratio <= 4.0


def test_quantizer_rejects_empty_fit() -> None:
    with pytest.raises(ValueError):
        ScalarQuantizer.fit(np.empty((0, 4), dtype=np.float32))


# -- k-means ----------------------------------------------------------------------------------


def test_kmeans_recovers_well_separated_clusters() -> None:
    rng = np.random.default_rng(3)
    means = np.array([[0, 0], [100, 0], [0, 100], [100, 100]], dtype=np.float32)
    x = np.concatenate([m + rng.standard_normal((200, 2)).astype(np.float32) for m in means])
    centroids = kmeans(x, 4, max_iter=20, seed=0)
    for m in means:
        assert np.min(np.linalg.norm(centroids - m, axis=1)) < 1.0


def test_kmeans_is_deterministic_and_handles_k_equal_n() -> None:
    x = np.random.default_rng(4).standard_normal((50, 3)).astype(np.float32)
    a = kmeans(x, 5, max_iter=10, seed=7)
    b = kmeans(x, 5, max_iter=10, seed=7)
    np.testing.assert_array_equal(a, b)
    assert kmeans(x, 50, max_iter=3, seed=0).shape == (50, 3)
    with pytest.raises(ValueError):
        kmeans(x, 51, max_iter=3, seed=0)


def test_kmeans_with_duplicate_points_has_no_nan() -> None:
    x = np.ones((30, 2), dtype=np.float32)
    x[:3] = 0.0
    c = kmeans(x, 4, max_iter=10, seed=0)
    assert np.all(np.isfinite(c))


# -- IVF --------------------------------------------------------------------------------------


def test_recall_rises_with_nprobe(ivf_setup: tuple[IVFIndex, np.ndarray, np.ndarray]) -> None:
    index, queries, truth = ivf_setup
    recalls = []
    for nprobe in (1, 2, 4, 8, 16, 32):
        found = np.stack([index.search(q, k=10, nprobe=nprobe).labels for q in queries])
        recalls.append(recall_at_k(found, truth, 10))
    assert recalls == sorted(recalls), recalls
    assert recalls[0] < recalls[-1]


def test_nprobe_equal_nlist_is_exhaustive(
    ivf_setup: tuple[IVFIndex, np.ndarray, np.ndarray],
) -> None:
    index, queries, truth = ivf_setup
    found = np.stack([index.search(q, k=10, nprobe=index.nlist).labels for q in queries])
    assert recall_at_k(found, truth, 10) == 1.0


def test_every_vector_lands_in_exactly_one_list(
    ivf_setup: tuple[IVFIndex, np.ndarray, np.ndarray],
) -> None:
    index, _, _ = ivf_setup
    sizes = index.list_sizes()
    assert len(sizes) == index.nlist
    assert sum(sizes) == len(index) == 8000


def test_untrained_index_searches_exactly_then_trains_automatically() -> None:
    base = np.random.default_rng(5).standard_normal((300, 8)).astype(np.float32)
    index = IVFIndex(dim=8, nlist=16, seed=0)
    index.add(base[:100])
    assert not index.is_trained
    flat = FlatIndex(dim=8)
    flat.add(base[:100])
    q = base[0]
    assert index.search(q, k=5).labels.tolist() == flat.search(q, k=5).labels.tolist()
    index.add(base[100:])
    assert index.is_trained  # 300 >= train threshold (16 * 16)
    assert sum(index.list_sizes()) == 300
    np.testing.assert_allclose(index.vector(150), base[150])


def test_explicit_train_and_add_after_training() -> None:
    base = np.random.default_rng(6).standard_normal((500, 8)).astype(np.float32)
    index = IVFIndex(dim=8, nlist=8, seed=0)
    index.train(base)
    index.add(base)
    index.add(base[:10])
    assert len(index) == 510
    with pytest.raises(ValueError):
        index.train(base[:4])


@pytest.mark.parametrize("metric", ["ip", "cosine"])
def test_other_metrics_exhaustive_probe_is_exact(metric: str) -> None:
    base = np.random.default_rng(7).standard_normal((1000, 8)).astype(np.float32)
    index = IVFIndex(dim=8, metric=metric, nlist=8, seed=0)  # type: ignore[arg-type]
    index.add(base)
    flat = FlatIndex(dim=8, metric=metric)  # type: ignore[arg-type]
    flat.add(base)
    for q in base[:10]:
        assert index.search(q, k=5, nprobe=8).labels.tolist() == flat.search(q, k=5).labels.tolist()


def test_int8_ivf_costs_little_recall_and_saves_memory(
    ivf_setup: tuple[IVFIndex, np.ndarray, np.ndarray],
) -> None:
    full, queries, truth = ivf_setup
    base = clustered(8000, 16, centers=40, seed=1)
    sq = IVFIndex(dim=16, metric="l2", nlist=32, quantization="int8", seed=0)
    sq.add(base)
    found = np.stack([sq.search(q, k=10, nprobe=32).labels for q in queries])
    assert recall_at_k(found, truth, 10) > 0.9
    assert full.memory_bytes() / sq.memory_bytes() > 2.5


def test_delete_and_allow(ivf_setup: tuple[IVFIndex, np.ndarray, np.ndarray]) -> None:
    base = clustered(2000, 8, centers=10, seed=9)
    index = IVFIndex(dim=8, nlist=8, seed=0)
    index.add(base)
    assert index.search(base[3], k=1, nprobe=8).labels.tolist() == [3]
    index.delete(3)
    assert 3 not in index.search(base[3], k=5, nprobe=8).labels.tolist()
    res = index.search(base[3], k=5, nprobe=8, allow=lambda label: label < 100)
    assert all(label < 100 for label in res.labels.tolist())


def test_ivf_validation() -> None:
    with pytest.raises(ValueError):
        IVFIndex(dim=4, nlist=0)
    with pytest.raises(ValueError):
        IVFIndex(dim=4, quantization="pq")  # type: ignore[arg-type]
    index = IVFIndex(dim=4, nlist=2)
    with pytest.raises(DimensionMismatchError):
        index.add(np.ones((3, 5), dtype=np.float32))
    assert index.search(np.ones(4, dtype=np.float32), k=3).labels.size == 0
    index.add(np.random.default_rng(0).standard_normal((100, 4)).astype(np.float32))
    with pytest.raises(ValueError):
        index.search(np.ones(4, dtype=np.float32), k=3, nprobe=0)


@pytest.mark.parametrize("quantization", ["none", "int8"])
def test_ivf_save_load_roundtrip(tmp_path: Path, quantization: str) -> None:
    base = clustered(1500, 8, centers=10, seed=10)
    index = IVFIndex(dim=8, nlist=8, quantization=quantization, seed=0)  # type: ignore[arg-type]
    index.add(base)
    index.delete(1)
    index.save(tmp_path / "ivf")
    loaded = IVFIndex.load(tmp_path / "ivf")
    for q in base[:10]:
        a, b = index.search(q, k=5, nprobe=3), loaded.search(q, k=5, nprobe=3)
        assert a.labels.tolist() == b.labels.tolist()
        np.testing.assert_allclose(a.distances, b.distances, rtol=1e-6)
    assert loaded.stats()["params"]["quantization"] == quantization


def test_ivf_save_load_untrained(tmp_path: Path) -> None:
    index = IVFIndex(dim=4, nlist=64)
    index.add(np.ones((5, 4), dtype=np.float32))
    index.save(tmp_path / "ivf")
    loaded = IVFIndex.load(tmp_path / "ivf")
    assert not loaded.is_trained and len(loaded) == 5
