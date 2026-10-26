"""Startup seeding: hosts without a persistent disk (Render free) rebuild the demo collection
from committed sample data every time the engine boots."""

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from vectorforge.core.quantize import ScalarQuantizer
from vectorforge.service.app import create_app
from vectorforge.service.security import ConfigError, Settings

ADMIN = "a" * 40
DEMO = "d" * 40


def write_seed(
    root: Path, n: int = 40, dim: int = 8, count_override: int | None = None
) -> np.ndarray:
    rng = np.random.default_rng(0)
    vecs = rng.standard_normal((n, dim)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    q = ScalarQuantizer.fit(vecs)
    (root / "docs.bin").write_bytes(q.encode(vecs).tobytes())
    docs = [
        {"id": f"d{i}", "title": f"title {i}", "module": "m", "summary": f"summary {i}"}
        for i in range(n)
    ]
    (root / "docs.json").write_text(json.dumps(docs))
    manifest = {
        "collection": {
            "name": "demo",
            "dim": dim,
            "metric": "cosine",
            "index": {"type": "hnsw", "params": {"M": 8, "ef_construction": 64}},
        },
        "documents": "docs.json",
        "vectors": "docs.bin",
        "count": count_override if count_override is not None else n,
        "quant": {"min": q.vmin.tolist(), "step": q.step.tolist()},
        "metadata_fields": ["title", "module", "summary"],
    }
    (root / "seed.json").write_text(json.dumps(manifest))
    return q.decode(q.encode(vecs))


def settings(data: Path, seed: Path | None) -> Settings:
    return Settings(admin_key=ADMIN, demo_key=DEMO, data_dir=data, seed_dir=seed)


def test_seeds_demo_collection_on_startup(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    vecs = write_seed(seed)
    with TestClient(create_app(settings(tmp_path / "data", seed))) as c:
        assert c.get("/readyz").status_code == 200
        info = c.get("/collections/demo", headers={"X-API-Key": DEMO}).json()
        assert info["count"] == 40 and info["dim"] == 8 and info["metric"] == "cosine"
        r = c.post(
            "/collections/demo/search",
            json={"vector": vecs[7].tolist(), "k": 1},
            headers={"X-API-Key": DEMO},
        )
        hit = r.json()["results"][0]
        assert hit["id"] == "d7"
        assert hit["metadata"] == {"title": "title 7", "module": "m", "summary": "summary 7"}


def test_seeding_is_skipped_when_collection_exists(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    write_seed(seed)
    data = tmp_path / "data"
    with TestClient(create_app(settings(data, seed))) as c:
        c.delete("/collections/demo/vectors/d0", headers={"X-API-Key": ADMIN})
    # A persistent data dir survives the restart: the existing collection is kept as is.
    with TestClient(create_app(settings(data, seed))) as c:
        info = c.get("/collections/demo", headers={"X-API-Key": ADMIN}).json()
        assert info["count"] == 39 and info["deleted"] == 1


def test_no_seed_dir_means_no_seeding(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path / "data", None))) as c:
        assert c.get("/collections", headers={"X-API-Key": ADMIN}).json() == {"collections": []}


def test_malformed_seed_refuses_to_start(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    write_seed(seed, count_override=41)  # manifest claims more vectors than the file holds
    with (
        pytest.raises(ConfigError, match="seed"),
        TestClient(create_app(settings(tmp_path / "data", seed))),
    ):
        pass


def test_missing_seed_manifest_refuses_to_start(tmp_path: Path) -> None:
    with (
        pytest.raises(ConfigError, match="seed"),
        TestClient(create_app(settings(tmp_path / "data", tmp_path / "nowhere"))),
    ):
        pass


def test_seed_dir_from_env(tmp_path: Path) -> None:
    s = Settings.from_env(
        {
            "VECTORFORGE_ADMIN_KEY": ADMIN,
            "VECTORFORGE_DATA_DIR": str(tmp_path),
            "VECTORFORGE_SEED_DIR": str(tmp_path / "s"),
        }
    )
    assert s.seed_dir == tmp_path / "s"
    assert Settings.from_env({"VECTORFORGE_ADMIN_KEY": ADMIN}).seed_dir is None


def test_prebuilt_data_dir_loads_without_reseeding(tmp_path: Path) -> None:
    # Build time (Dockerfile): seed into a data dir and checkpoint it. Run time: the engine loads
    # that snapshot instead of rebuilding the graph, which matters on a 0.1-CPU free instance.
    from vectorforge.service.seed import build_data_dir

    seed = tmp_path / "seed"
    seed.mkdir()
    vecs = write_seed(seed)
    data = tmp_path / "baked"
    assert build_data_dir(seed, data) == 40
    assert (data / "demo" / "manifest.json").exists()
    with TestClient(create_app(settings(data, seed))) as c:
        info = c.get("/collections/demo", headers={"X-API-Key": DEMO}).json()
        assert info["count"] == 40
        r = c.post(
            "/collections/demo/search",
            json={"vector": vecs[3].tolist(), "k": 1},
            headers={"X-API-Key": DEMO},
        )
        assert r.json()["results"][0]["id"] == "d3"
