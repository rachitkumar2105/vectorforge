from pathlib import Path

import numpy as np
import pytest

from vectorforge.collection import Collection, FilterError, UpsertItem, compile_filter


def vec(i: int, dim: int = 8) -> np.ndarray:
    return np.random.default_rng(i).standard_normal(dim).astype(np.float32)


def items(start: int, stop: int, dim: int = 8) -> list[UpsertItem]:
    return [
        UpsertItem(f"v{i}", vec(i, dim), {"parity": "even" if i % 2 == 0 else "odd", "i": i})
        for i in range(start, stop)
    ]


@pytest.fixture(params=["hnsw", "ivf", "flat"])
def coll(request: pytest.FixtureRequest, tmp_path: Path) -> Collection:
    params = {"hnsw": {"M": 8, "ef_construction": 64}, "ivf": {"nlist": 4}, "flat": {}}
    c = Collection.create(
        tmp_path, "c1", dim=8, metric="l2", index_type=request.param,
        index_params=params[request.param], checkpoint_every=50,
    )
    yield c
    c.close()


def test_upsert_search_and_get(coll: Collection) -> None:
    coll.upsert(items(0, 120))
    assert coll.count == 120
    out = coll.search(vec(5), k=3, ef_search=64, nprobe=4)
    assert out.hits[0].id == "v5"
    assert out.hits[0].metadata == {"parity": "odd", "i": 5}
    v, meta = coll.get("v7")
    np.testing.assert_array_equal(v, vec(7))
    assert meta["i"] == 7


def test_reupsert_replaces_vector_and_metadata(coll: Collection) -> None:
    coll.upsert(items(0, 20))
    coll.upsert([UpsertItem("v3", vec(1000), {"new": True})])
    assert coll.count == 20
    out = coll.search(vec(1000), k=1, ef_search=64, nprobe=4)
    assert out.hits[0].id == "v3" and out.hits[0].metadata == {"new": True}
    # The old vector for v3 is tombstoned: v3 is no longer the nearest neighbour of vec(3), and
    # a k=20 search over the 20 live ids returns each id exactly once (no stale duplicate).
    assert coll.search(vec(3), k=1, ef_search=64, nprobe=4).hits[0].id != "v3"
    ids = [h.id for h in coll.search(vec(3), k=20, ef_search=64, nprobe=4).hits]
    assert len(ids) == len(set(ids))


def test_delete_tombstones(coll: Collection) -> None:
    coll.upsert(items(0, 30))
    coll.delete("v4")
    assert coll.count == 29 and coll.deleted_count == 1
    assert "v4" not in [h.id for h in coll.search(vec(4), k=10, ef_search=64, nprobe=4).hits]
    with pytest.raises(KeyError):
        coll.delete("v4")
    with pytest.raises(KeyError):
        coll.get("v4")


def test_filtered_search_only_returns_matches(coll: Collection) -> None:
    coll.upsert(items(0, 200))
    out = coll.search(vec(10), k=10, filter={"parity": "odd"}, ef_search=64, nprobe=4)
    assert len(out.hits) == 10
    assert all(h.metadata is not None and h.metadata["parity"] == "odd" for h in out.hits)
    assert out.strategy in ("graph", "ivf", "exact")


def test_selective_filter_falls_back_to_exact(coll: Collection) -> None:
    coll.upsert(items(0, 200))
    out = coll.search(vec(10), k=3, filter={"i": {"in": [7, 99, 150]}})
    assert out.strategy == "exact_filtered"
    assert sorted(h.id for h in out.hits) == ["v150", "v7", "v99"]


def test_filter_with_no_matches(coll: Collection) -> None:
    coll.upsert(items(0, 10))
    assert coll.search(vec(1), k=3, filter={"parity": "none"}).hits == []


def test_include_metadata_false(coll: Collection) -> None:
    coll.upsert(items(0, 10))
    assert coll.search(vec(1), k=1, include_metadata=False).hits[0].metadata is None


def test_close_and_reopen_returns_identical_results(coll: Collection) -> None:
    coll.upsert(items(0, 175))  # crosses checkpoint_every=50 several times
    coll.delete("v9")
    queries = [vec(10_000 + i) for i in range(10)]
    before = [coll.search(q, k=5, ef_search=32, nprobe=2) for q in queries]
    path = coll.path
    coll.close()
    reopened = Collection.open(path)
    after = [reopened.search(q, k=5, ef_search=32, nprobe=2) for q in queries]
    for a, b in zip(before, after, strict=True):
        assert [h.id for h in a.hits] == [h.id for h in b.hits]
        np.testing.assert_allclose([h.distance for h in a.hits], [h.distance for h in b.hits])
    assert reopened.count == 174 and reopened.deleted_count == 1
    reopened.close()


def test_reopen_without_clean_close_replays_wal(tmp_path: Path) -> None:
    c = Collection.create(tmp_path, "w", dim=8, metric="cosine", index_type="hnsw",
                          index_params={"M": 8}, checkpoint_every=1000)
    c.upsert(items(0, 40))
    c.delete("v1")
    # No close(): nothing was checkpointed, so everything must come back from the WAL.
    c._release_files()
    again = Collection.open(c.path)
    assert again.count == 39
    np.testing.assert_array_equal(again.get("v2")[0], vec(2))
    assert again.search(vec(2), k=1).hits[0].id == "v2"
    again.close()


def test_info_and_validation(tmp_path: Path) -> None:
    c = Collection.create(tmp_path, "info", dim=4, metric="ip", index_type="flat")
    info = c.info()
    assert info["name"] == "info" and info["dim"] == 4 and info["index"]["type"] == "flat"
    with pytest.raises(ValueError):
        c.upsert([UpsertItem("x", np.ones(5, dtype=np.float32), {})])
    with pytest.raises(ValueError):
        c.upsert([UpsertItem("x", np.array([np.inf, 0, 0, 0], dtype=np.float32), {})])
    with pytest.raises(FileExistsError):
        Collection.create(tmp_path, "info", dim=4, metric="ip", index_type="flat")
    with pytest.raises(ValueError):
        Collection.create(tmp_path, "bad", dim=4, metric="ip", index_type="annoy")
    c.close()


def test_drop_removes_files(tmp_path: Path) -> None:
    c = Collection.create(tmp_path, "gone", dim=4, metric="l2", index_type="hnsw")
    c.upsert([UpsertItem("a", np.ones(4, dtype=np.float32), {})])
    path = c.path
    c.drop()
    assert not path.exists()


def test_compile_filter() -> None:
    f = compile_filter({"lang": "en", "year": {"in": [2023, 2024]}})
    assert f({"lang": "en", "year": 2024})
    assert not f({"lang": "en", "year": 2022})
    assert not f({"year": 2024})
    assert not f(None)
    assert compile_filter(None) is None
    for bad in ({"a": {"gt": 1}}, {"a": [1, 2]}, {"a": {"in": "x"}}, {"": 1}):
        with pytest.raises(FilterError):
            compile_filter(bad)  # type: ignore[arg-type]
