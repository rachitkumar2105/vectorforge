"""API contract tests, run through httpx via FastAPI's TestClient."""

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from vectorforge.service.app import create_app
from vectorforge.service.security import ConfigError, Settings

ADMIN = "a" * 40
DEMO = "d" * 40


def settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "admin_key": ADMIN,
        "demo_key": DEMO,
        "demo_collection": "demo",
        "data_dir": tmp_path,
        "cors_origins": ["http://localhost:3000"],
        "env": "test",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(settings(tmp_path))) as c:
        yield c


def admin() -> dict[str, str]:
    return {"X-API-Key": ADMIN}


def demo() -> dict[str, str]:
    return {"X-API-Key": DEMO}


def make(client: TestClient, name: str = "docs", dim: int = 4, index: str = "hnsw") -> None:
    params = {"hnsw": {"M": 8, "ef_construction": 32}, "ivf": {"nlist": 2}, "flat": {}}[index]
    r = client.post(
        "/collections",
        json={"name": name, "dim": dim, "metric": "l2", "index": {"type": index, "params": params}},
        headers=admin(),
    )
    assert r.status_code == 201, r.text


def vectors(n: int, dim: int = 4, start: int = 0) -> list[dict[str, object]]:
    rng = np.random.default_rng(start)
    return [
        {"id": f"v{i}", "values": rng.standard_normal(dim).tolist(), "metadata": {"g": i % 2}}
        for i in range(start, start + n)
    ]


# -- configuration ----------------------------------------------------------------------------


def test_refuses_to_start_without_admin_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="VECTORFORGE_ADMIN_KEY"):
        Settings.from_env({"VECTORFORGE_DATA_DIR": str(tmp_path)})


def test_rejects_weak_or_reused_keys_and_wildcard_cors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        settings(tmp_path, admin_key="short")
    with pytest.raises(ConfigError):
        settings(tmp_path, demo_key=ADMIN)
    with pytest.raises(ConfigError):
        settings(tmp_path, cors_origins=["*"])
    with pytest.raises(ConfigError):
        settings(tmp_path, cors_origins=["https://*.vercel.app"])


def test_from_env_parses_values(tmp_path: Path) -> None:
    s = Settings.from_env(
        {
            "VECTORFORGE_ADMIN_KEY": ADMIN,
            "VECTORFORGE_DEMO_KEY": DEMO,
            "VECTORFORGE_DATA_DIR": str(tmp_path),
            "VECTORFORGE_CORS_ORIGINS": "https://vectorforge.example, http://localhost:3000",
            "VECTORFORGE_ENV": "production",
            "VECTORFORGE_MAX_BODY_BYTES": "1024",
        }
    )
    assert s.cors_origins == ["https://vectorforge.example", "http://localhost:3000"]
    assert s.max_body_bytes == 1024 and s.env == "production"
    assert ADMIN not in repr(s) and DEMO not in repr(s)


# -- health -----------------------------------------------------------------------------------


def test_health_and_ready_need_no_key(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json() == {"status": "ready"}


# -- auth -------------------------------------------------------------------------------------


def test_missing_and_wrong_keys_are_401(client: TestClient) -> None:
    assert client.get("/collections").status_code == 401
    r = client.get("/collections", headers={"X-API-Key": "b" * 40})
    assert r.status_code == 401
    assert ADMIN not in r.text and "b" * 40 not in r.text


def test_demo_key_is_read_only_and_scoped(client: TestClient) -> None:
    make(client, "demo")
    make(client, "private")
    client.post("/collections/demo/vectors", json={"vectors": vectors(5)}, headers=admin())
    assert client.get("/collections/demo", headers=demo()).status_code == 200
    r = client.post(
        "/collections/demo/search", json={"vector": [0, 0, 0, 0], "k": 2}, headers=demo()
    )
    assert r.status_code == 200 and len(r.json()["results"]) == 2
    assert (
        client.post(
            "/collections/demo/vectors", json={"vectors": vectors(1)}, headers=demo()
        ).status_code
        == 403
    )
    assert client.delete("/collections/demo/vectors/v1", headers=demo()).status_code == 403
    assert client.delete("/collections/demo", headers=demo()).status_code == 403
    assert client.get("/collections", headers=demo()).status_code == 403
    assert client.get("/collections/private", headers=demo()).status_code == 403
    r = client.post(
        "/collections/private/search", json={"vector": [0, 0, 0, 0], "k": 1}, headers=demo()
    )
    assert r.status_code == 403
    assert client.get("/metrics", headers=demo()).status_code == 403


# -- collections ------------------------------------------------------------------------------


def test_collection_lifecycle(client: TestClient) -> None:
    make(client, "docs")
    r = client.get("/collections", headers=admin())
    assert [c["name"] for c in r.json()["collections"]] == ["docs"]
    info = client.get("/collections/docs", headers=admin()).json()
    assert info["dim"] == 4 and info["count"] == 0 and info["index"]["type"] == "hnsw"
    dup = client.post(
        "/collections",
        json={"name": "docs", "dim": 4, "metric": "l2", "index": {"type": "flat"}},
        headers=admin(),
    )
    assert dup.status_code == 409
    assert client.delete("/collections/docs", headers=admin()).status_code == 204
    assert client.get("/collections/docs", headers=admin()).status_code == 404
    assert client.delete("/collections/docs", headers=admin()).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Bad Name", "dim": 4, "metric": "l2", "index": {"type": "flat"}},
        {"name": "../escape", "dim": 4, "metric": "l2", "index": {"type": "flat"}},
        {"name": "ok", "dim": 0, "metric": "l2", "index": {"type": "flat"}},
        {"name": "ok", "dim": 5000, "metric": "l2", "index": {"type": "flat"}},
        {"name": "ok", "dim": 4, "metric": "hamming", "index": {"type": "flat"}},
        {"name": "ok", "dim": 4, "metric": "l2", "index": {"type": "annoy"}},
        {"name": "ok", "dim": 4, "metric": "l2", "index": {"type": "hnsw", "params": {"M": 1}}},
        {"name": "ok", "dim": 4, "metric": "l2", "index": {"type": "hnsw", "params": {"evil": 1}}},
        {"name": "ok", "dim": 4, "metric": "l2", "index": {"type": "ivf", "params": {"nlist": 0}}},
    ],
)
def test_create_validation(client: TestClient, body: dict[str, object]) -> None:
    r = client.post("/collections", json=body, headers=admin())
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_unknown_collection_is_404_everywhere(client: TestClient) -> None:
    assert client.get("/collections/nope", headers=admin()).status_code == 404
    assert (
        client.post(
            "/collections/nope/vectors", json={"vectors": vectors(1)}, headers=admin()
        ).status_code
        == 404
    )
    r = client.post(
        "/collections/nope/search", json={"vector": [0, 0, 0, 0], "k": 1}, headers=admin()
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.delete("/collections/nope/vectors/x", headers=admin()).status_code == 404


# -- vectors and search -----------------------------------------------------------------------


@pytest.mark.parametrize("index", ["hnsw", "ivf", "flat"])
def test_upsert_search_delete(client: TestClient, index: str) -> None:
    make(client, "docs", index=index)
    r = client.post("/collections/docs/vectors", json={"vectors": vectors(50)}, headers=admin())
    assert r.status_code == 200 and r.json() == {"upserted": 50}
    target = vectors(50)[7]["values"]
    r = client.post(
        "/collections/docs/search",
        json={"vector": target, "k": 3, "ef_search": 50, "nprobe": 2},
        headers=admin(),
    )
    body = r.json()
    assert r.status_code == 200
    assert body["results"][0]["id"] == "v7"
    assert body["results"][0]["metadata"] == {"g": 1}
    assert body["took_ms"] >= 0 and body["strategy"] in ("graph", "ivf", "exact")
    assert client.delete("/collections/docs/vectors/v7", headers=admin()).status_code == 204
    assert client.delete("/collections/docs/vectors/v7", headers=admin()).status_code == 404
    r = client.post("/collections/docs/search", json={"vector": target, "k": 3}, headers=admin())
    assert "v7" not in [h["id"] for h in r.json()["results"]]
    assert client.get("/collections/docs", headers=admin()).json()["deleted"] == 1


def test_filtered_search(client: TestClient) -> None:
    make(client, "docs")
    client.post("/collections/docs/vectors", json={"vectors": vectors(100)}, headers=admin())
    r = client.post(
        "/collections/docs/search",
        json={"vector": [0, 0, 0, 0], "k": 5, "filter": {"g": 0}, "include_metadata": True},
        headers=admin(),
    )
    assert r.status_code == 200
    assert all(h["metadata"]["g"] == 0 for h in r.json()["results"])
    bad = client.post(
        "/collections/docs/search",
        json={"vector": [0, 0, 0, 0], "k": 5, "filter": {"g": {"gt": 0}}},
        headers=admin(),
    )
    assert bad.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"vectors": []},
        {"vectors": "nope"},
        {"vectors": [{"id": "a", "values": "abc"}]},
        {"vectors": [{"id": "a", "values": [1, 2, "x", 4]}]},
        {"vectors": [{"id": "a", "values": [[1, 2], [3, 4]]}]},
        {"vectors": [{"id": "a b", "values": [1, 2, 3, 4]}]},
        {"vectors": [{"id": "", "values": [1, 2, 3, 4]}]},
        {"vectors": [{"id": "a", "values": [1, 2, 3]}]},
        {"vectors": [{"id": "a", "values": [1, 2, 3, 4], "metadata": {"n": {"deep": 1}}}]},
        {"vectors": [{"id": "a", "values": [1, 2, 3, 4], "metadata": {"s": "x" * 5000}}]},
        {"vectors": [{"id": "a", "values": [1, 2, 3, 4], "extra": 1}]},
    ],
)
def test_upsert_rejects_malformed_input(client: TestClient, payload: dict[str, object]) -> None:
    make(client, "docs")
    r = client.post("/collections/docs/vectors", json=payload, headers=admin())
    assert r.status_code == 422, r.text
    assert client.get("/collections/docs", headers=admin()).json()["count"] == 0


def test_upsert_rejects_nan_and_infinity(client: TestClient) -> None:
    make(client, "docs")
    for raw in (b"NaN", b"Infinity", b"-Infinity", b"1e999"):
        body = b'{"vectors":[{"id":"a","values":[1,2,3,' + raw + b"]}]}"
        r = client.post(
            "/collections/docs/vectors",
            content=body,
            headers={**admin(), "Content-Type": "application/json"},
        )
        assert r.status_code == 422, raw


def test_batch_cap(client: TestClient) -> None:
    make(client, "docs", dim=1)
    payload = {"vectors": [{"id": f"v{i}", "values": [float(i)]} for i in range(1001)]}
    r = client.post("/collections/docs/vectors", json=payload, headers=admin())
    assert r.status_code == 422


def test_malformed_json_is_rejected(client: TestClient) -> None:
    make(client, "docs")
    r = client.post(
        "/collections/docs/vectors",
        content=b'{"vectors": [',
        headers={**admin(), "Content-Type": "application/json"},
    )
    assert r.status_code == 422
    assert "Traceback" not in r.text


@pytest.mark.parametrize(
    "payload",
    [
        {"vector": [0, 0, 0, 0], "k": 0},
        {"vector": [0, 0, 0, 0], "k": 1001},
        {"vector": [0, 0, 0], "k": 1},
        {"vector": [0, 0, 0, 0], "k": 1, "ef_search": 0},
        {"vector": [0, 0, 0, 0], "k": 1, "nprobe": 0},
        {"vector": [], "k": 1},
    ],
)
def test_search_validation(client: TestClient, payload: dict[str, object]) -> None:
    make(client, "docs")
    r = client.post("/collections/docs/search", json=payload, headers=admin())
    assert r.status_code == 422


def test_validation_errors_do_not_echo_input(client: TestClient) -> None:
    make(client, "docs")
    secret_value = "metadata-secret-value-123"
    r = client.post(
        "/collections/docs/vectors",
        json={
            "vectors": [{"id": "a", "values": [1, 2, 3, 4], "metadata": {"s": {"x": secret_value}}}]
        },
        headers=admin(),
    )
    assert r.status_code == 422
    assert secret_value not in r.text


# -- payload size -----------------------------------------------------------------------------


def test_oversized_body_rejected_by_content_length(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, max_body_bytes=2048))) as c:
        make(c, "docs")
        r = c.post("/collections/docs/vectors", json={"vectors": vectors(100)}, headers=admin())
        assert r.status_code == 413
        assert r.json()["error"]["code"] == "payload_too_large"


def test_oversized_streamed_body_rejected(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, max_body_bytes=2048))) as c:
        make(c, "docs")
        payload = json.dumps({"vectors": vectors(100)}).encode()

        def chunks() -> Iterator[bytes]:
            for i in range(0, len(payload), 512):
                yield payload[i : i + 512]

        r = c.post(
            "/collections/docs/vectors",
            content=chunks(),
            headers={**admin(), "Content-Type": "application/json"},
        )
        assert r.status_code == 413


# -- rate limiting ----------------------------------------------------------------------------


def test_search_rate_limit_returns_429_with_retry_after(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, search_rate=(1.0, 3)))) as c:
        make(c, "docs")
        codes = [
            c.post(
                "/collections/docs/search", json={"vector": [0, 0, 0, 0], "k": 1}, headers=admin()
            ).status_code
            for _ in range(5)
        ]
        assert codes[:3] == [200, 200, 200]
        assert codes[3] == 429
        r = c.post(
            "/collections/docs/search", json={"vector": [0, 0, 0, 0], "k": 1}, headers=admin()
        )
        assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


def test_write_rate_limit_is_separate_bucket(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, write_rate=(0.5, 2)))) as c:
        make(c, "docs")  # create counts as a write
        r1 = c.post("/collections/docs/vectors", json={"vectors": vectors(1)}, headers=admin())
        r2 = c.post("/collections/docs/vectors", json={"vectors": vectors(1)}, headers=admin())
        assert (r1.status_code, r2.status_code) == (200, 429)
        assert (
            c.post(
                "/collections/docs/search", json={"vector": [0, 0, 0, 0], "k": 1}, headers=admin()
            ).status_code
            == 200
        )


def test_repeated_auth_failures_are_rate_limited(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, auth_fail_rate=(0.1, 3)))) as c:
        codes = [
            c.get("/collections", headers={"X-API-Key": "x" * 40}).status_code for _ in range(5)
        ]
        assert codes[:3] == [401, 401, 401] and codes[3] == 429


# -- metrics, errors, logs, headers -----------------------------------------------------------


def test_metrics_prometheus_format(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps({"headline": [{"dataset": "sift", "index": "hnsw", "recall_at_10": 0.97}]})
    )
    with TestClient(create_app(settings(tmp_path / "d", bench_summary=summary))) as c:
        make(c, "docs")
        c.post("/collections/docs/vectors", json={"vectors": vectors(10)}, headers=admin())
        c.post("/collections/docs/search", json={"vector": [0, 0, 0, 0], "k": 1}, headers=admin())
        assert c.get("/metrics").status_code == 401
        r = c.get("/metrics", headers=admin())
        text = r.text
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert (
        'vectorforge_requests_total{method="POST",route="/collections/{name}/search",status="200"} 1'
        in text
    )
    assert "# TYPE vectorforge_request_duration_seconds histogram" in text
    assert (
        'vectorforge_request_duration_seconds_bucket{route="/collections/{name}/search",le="+Inf"} 1'
        in text
    )
    assert 'vectorforge_index_vectors{collection="docs"} 10' in text
    assert 'vectorforge_benchmark_recall_at_10{dataset="sift",index="hnsw"} 0.97' in text


def test_internal_errors_are_generic(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    make(client, "docs")

    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("secret internal path C:/srv/data")

    monkeypatch.setattr("vectorforge.collection.Collection.search", boom)
    r = client.post(
        "/collections/docs/search", json={"vector": [0, 0, 0, 0], "k": 1}, headers=admin()
    )
    assert r.status_code == 500
    assert r.json() == {"error": {"code": "internal_error", "message": "internal error"}}
    assert "secret" not in r.text


def test_logs_contain_no_keys_vectors_or_metadata(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    make(client, "docs")
    item = {
        "id": "doc-1",
        "values": [0.123456, 0.654321, 0.111111, 0.999999],
        "metadata": {"t": "private-meta"},
    }
    client.post("/collections/docs/vectors", json={"vectors": [item]}, headers=admin())
    client.post(
        "/collections/docs/search", json={"vector": item["values"], "k": 1}, headers=admin()
    )
    client.get("/collections", headers={"X-API-Key": "w" * 40})
    logged = "\n".join(
        r.getMessage() + json.dumps(getattr(r, "fields", {})) for r in caplog.records
    )
    assert "request" in logged
    for forbidden in (ADMIN, "w" * 40, "private-meta", "0.123456", "doc-1"):
        assert forbidden not in logged


def test_security_headers_and_cors(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Cache-Control"] == "no-store"
    ok = client.options(
        "/collections",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    evil = client.options(
        "/collections",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in evil.headers


def test_docs_disabled_in_production(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, env="production"))) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404
    with TestClient(create_app(settings(tmp_path / "dev", env="development"))) as c:
        assert c.get("/openapi.json").status_code == 200


def test_data_survives_restart(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as c:
        make(c, "docs")
        c.post("/collections/docs/vectors", json={"vectors": vectors(20)}, headers=admin())
    with TestClient(create_app(settings(tmp_path))) as c:
        assert c.get("/collections/docs", headers=admin()).json()["count"] == 20
        r = c.post(
            "/collections/docs/search",
            json={"vector": vectors(20)[3]["values"], "k": 1},
            headers=admin(),
        )
        assert r.json()["results"][0]["id"] == "v3"
