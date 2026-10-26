import math
from collections import deque
from pathlib import Path

import numpy as np
import pytest

from vectorforge.core.distance import DimensionMismatchError
from vectorforge.index.flat import FlatIndex
from vectorforge.index.hnsw import HNSWIndex
from vectorforge.metrics import recall_at_k


def gaussian(n: int, dim: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal((n, dim)).astype(np.float32)


@pytest.fixture(scope="module")
def built_5000() -> HNSWIndex:
    index = HNSWIndex(dim=16, metric="l2", M=8, ef_construction=64, seed=1)
    index.add(gaussian(5000, 16, seed=11))
    return index


@pytest.fixture(scope="module")
def recall_10k() -> tuple[HNSWIndex, np.ndarray, np.ndarray]:
    """The Phase 2 gate setup: 10k random vectors, default M=16 and ef_construction=200."""
    base = gaussian(10_000, 24, seed=5)
    queries = gaussian(200, 24, seed=6)
    index = HNSWIndex(dim=24, metric="l2", seed=3)
    index.add(base)
    flat = FlatIndex(dim=24, metric="l2")
    flat.add(base)
    return index, queries, flat.search_batch(queries, k=10)


# -- graph invariants -------------------------------------------------------------------------


def test_links_are_bidirectional(built_5000: HNSWIndex) -> None:
    g = built_5000
    for node in range(len(g)):
        for layer, neighbours in enumerate(g.neighbours_of(node)):
            for other in neighbours:
                assert node in g.neighbours(other, layer), (node, other, layer)


def test_no_node_exceeds_max_degree(built_5000: HNSWIndex) -> None:
    g = built_5000
    for node in range(len(g)):
        for layer, neighbours in enumerate(g.neighbours_of(node)):
            cap = g.M_max0 if layer == 0 else g.M
            assert len(neighbours) <= cap
            assert len(set(neighbours)) == len(neighbours), "duplicate edge"
            assert node not in neighbours, "self loop"


def test_layer_zero_contains_every_id(built_5000: HNSWIndex) -> None:
    g = built_5000
    assert g.layer_size(0) == len(g) == 5000
    for node in range(len(g)):
        assert g.level_of(node) >= 0
        assert len(g.neighbours_of(node)) == g.level_of(node) + 1


def test_entry_point_is_at_maximum_level(built_5000: HNSWIndex) -> None:
    g = built_5000
    levels = [g.level_of(i) for i in range(len(g))]
    assert g.entry_point is not None
    assert g.level_of(g.entry_point) == g.max_level == max(levels)


def test_upper_layers_are_nested(built_5000: HNSWIndex) -> None:
    # A node present at layer L must be present at every layer below it.
    g = built_5000
    for layer in range(1, g.max_level + 1):
        assert g.layer_size(layer) <= g.layer_size(layer - 1)


def test_layer_zero_is_connected_from_entry_point(built_5000: HNSWIndex) -> None:
    g = built_5000
    assert g.entry_point is not None
    seen = {g.entry_point}
    frontier = deque([g.entry_point])
    while frontier:
        for nxt in g.neighbours(frontier.popleft(), 0):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    assert len(seen) == len(g)


def test_level_distribution_matches_ml() -> None:
    # P(level >= 1) = exp(-1/mL) = 1/M. With M=16 and 20k draws, expect about 1250.
    index = HNSWIndex(dim=2, M=16, seed=0)
    levels = [index._random_level() for _ in range(20_000)]
    frac = sum(1 for lv in levels if lv >= 1) / len(levels)
    assert math.isclose(frac, 1 / 16, rel_tol=0.15)


# -- recall -----------------------------------------------------------------------------------


@pytest.mark.slow
def test_recall_at_10_above_095_at_ef_100(recall_10k: tuple[HNSWIndex, np.ndarray, np.ndarray]) -> None:
    index, queries, truth = recall_10k
    found = np.stack([index.search(q, k=10, ef_search=100).labels for q in queries])
    assert recall_at_k(found, truth, 10) > 0.95


@pytest.mark.slow
def test_recall_rises_monotonically_with_ef(recall_10k: tuple[HNSWIndex, np.ndarray, np.ndarray]) -> None:
    index, queries, truth = recall_10k
    recalls = []
    for ef in (10, 50, 100, 200):
        found = np.stack([index.search(q, k=10, ef_search=ef).labels for q in queries])
        recalls.append(recall_at_k(found, truth, 10))
    assert recalls == sorted(recalls), recalls
    assert recalls[-1] > recalls[0]


@pytest.mark.parametrize("metric", ["ip", "cosine"])
def test_recall_for_other_metrics(metric: str) -> None:
    base = gaussian(2000, 16, seed=8)
    queries = gaussian(50, 16, seed=9)
    index = HNSWIndex(dim=16, metric=metric, M=12, ef_construction=100, seed=2)  # type: ignore[arg-type]
    index.add(base)
    flat = FlatIndex(dim=16, metric=metric)  # type: ignore[arg-type]
    flat.add(base)
    found = np.stack([index.search(q, k=10, ef_search=100).labels for q in queries])
    assert recall_at_k(found, flat.search_batch(queries, k=10), 10) > 0.9


def test_simple_selection_is_switchable_and_valid() -> None:
    base = gaussian(2000, 16, seed=4)
    simple = HNSWIndex(dim=16, M=8, ef_construction=64, heuristic=False, seed=1)
    simple.add(base)
    assert simple.heuristic is False
    for node in range(len(simple)):
        for layer, nb in enumerate(simple.neighbours_of(node)):
            assert len(nb) <= (simple.M_max0 if layer == 0 else simple.M)
    q = gaussian(1, 16, seed=99)[0]
    assert simple.search(q, k=5).labels.size == 5


# -- edge cases -------------------------------------------------------------------------------


def test_empty_index_returns_nothing() -> None:
    index = HNSWIndex(dim=3)
    assert index.search(np.zeros(3, dtype=np.float32), k=5).labels.size == 0
    assert index.entry_point is None


def test_single_vector() -> None:
    index = HNSWIndex(dim=3)
    index.add(np.array([[1.0, 2.0, 3.0]], dtype=np.float32))
    res = index.search(np.zeros(3, dtype=np.float32), k=10)
    assert res.labels.tolist() == [0]
    assert res.distances[0] == pytest.approx(14.0)


def test_duplicate_vectors() -> None:
    index = HNSWIndex(dim=4, M=4, ef_construction=16, seed=0)
    dup = np.ones((50, 4), dtype=np.float32)
    index.add(dup)
    index.add(np.zeros((1, 4), dtype=np.float32))
    res = index.search(np.ones(4, dtype=np.float32), k=10, ef_search=60)
    assert res.labels.size == 10
    assert np.all(res.distances == 0.0)
    assert 50 not in res.labels.tolist()


def test_all_deleted_returns_nothing() -> None:
    index = HNSWIndex(dim=4, M=4, seed=0)
    index.add(gaussian(30, 4, seed=1))
    for label in range(30):
        index.delete(label)
    assert index.search(np.zeros(4, dtype=np.float32), k=5).labels.size == 0


def test_deleted_nodes_are_filtered_but_graph_stays_intact() -> None:
    base = gaussian(500, 8, seed=2)
    index = HNSWIndex(dim=8, M=8, ef_construction=64, seed=0)
    index.add(base)
    edges_before = sum(len(n) for node in range(500) for n in index.neighbours_of(node))
    q = base[10]
    assert index.search(q, k=1).labels.tolist() == [10]
    index.delete(10)
    res = index.search(q, k=5)
    assert 10 not in res.labels.tolist()
    assert res.labels.size == 5
    edges_after = sum(len(n) for node in range(500) for n in index.neighbours_of(node))
    assert edges_before == edges_after


def test_allow_predicate_applies_during_traversal() -> None:
    base = gaussian(1000, 8, seed=3)
    index = HNSWIndex(dim=8, M=8, ef_construction=64, seed=0)
    index.add(base)
    res = index.search(base[0], k=10, ef_search=100, allow=lambda label: label % 3 == 0)
    assert res.labels.size == 10
    assert all(label % 3 == 0 for label in res.labels.tolist())


def test_k_larger_than_index() -> None:
    index = HNSWIndex(dim=2, seed=0)
    index.add(gaussian(5, 2, seed=0))
    assert sorted(index.search(np.zeros(2, dtype=np.float32), k=50).labels.tolist()) == list(range(5))


def test_dimension_mismatch() -> None:
    index = HNSWIndex(dim=4)
    with pytest.raises(DimensionMismatchError):
        index.add(np.ones((2, 5), dtype=np.float32))
    index.add(np.ones((1, 4), dtype=np.float32))
    with pytest.raises(DimensionMismatchError):
        index.search(np.ones(3, dtype=np.float32), k=1)


def test_invalid_parameters() -> None:
    with pytest.raises(ValueError):
        HNSWIndex(dim=4, M=1)
    with pytest.raises(ValueError):
        HNSWIndex(dim=4, ef_construction=0)
    index = HNSWIndex(dim=4)
    index.add(np.ones((1, 4), dtype=np.float32))
    with pytest.raises(ValueError):
        index.search(np.ones(4, dtype=np.float32), k=1, ef_search=0)


# -- determinism and persistence --------------------------------------------------------------


def test_deterministic_under_fixed_seed() -> None:
    base = gaussian(800, 8, seed=12)
    a = HNSWIndex(dim=8, M=8, ef_construction=50, seed=42)
    b = HNSWIndex(dim=8, M=8, ef_construction=50, seed=42)
    a.add(base)
    b.add(base)
    assert a.entry_point == b.entry_point
    for node in range(800):
        assert a.neighbours_of(node) == b.neighbours_of(node)
    q = gaussian(1, 8, seed=13)[0]
    assert a.search(q, k=10).labels.tolist() == b.search(q, k=10).labels.tolist()


def test_different_seed_gives_different_graph() -> None:
    base = gaussian(800, 8, seed=12)
    a = HNSWIndex(dim=8, M=8, ef_construction=50, seed=1)
    b = HNSWIndex(dim=8, M=8, ef_construction=50, seed=2)
    a.add(base)
    b.add(base)
    assert [a.level_of(i) for i in range(800)] != [b.level_of(i) for i in range(800)]


def test_save_load_returns_identical_results(tmp_path: Path) -> None:
    base = gaussian(1500, 12, seed=21)
    index = HNSWIndex(dim=12, metric="cosine", M=8, ef_construction=64, seed=7)
    index.add(base)
    index.delete(3)
    index.save(tmp_path / "hnsw")
    loaded = HNSWIndex.load(tmp_path / "hnsw")
    for q in gaussian(20, 12, seed=22):
        a, b = index.search(q, k=10, ef_search=40), loaded.search(q, k=10, ef_search=40)
        assert a.labels.tolist() == b.labels.tolist()
        np.testing.assert_allclose(a.distances, b.distances)
    # Continuing to insert after a reload must stay deterministic too (RNG state is persisted).
    more = gaussian(10, 12, seed=23)
    index.add(more)
    loaded.add(more)
    assert [index.level_of(i) for i in range(1510)] == [loaded.level_of(i) for i in range(1510)]


def test_stats_reports_graph_shape(built_5000: HNSWIndex) -> None:
    s = built_5000.stats()
    assert s["type"] == "hnsw" and s["count"] == 5000
    assert s["params"]["M"] == 8
    assert s["max_level"] == built_5000.max_level
    assert s["memory_bytes"] > 5000 * 16 * 4
    assert s["edges"] > 0
