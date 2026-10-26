"""Regression tests for the security-audit findings approved for fixing."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vectorforge.service.app import create_app
from vectorforge.service.security import ConfigError, Settings

ADMIN = "a" * 40
DEMO = "d" * 40


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(admin_key=ADMIN, demo_key=DEMO, data_dir=tmp_path)))


def seed(c: TestClient) -> None:
    c.post(
        "/collections",
        json={"name": "demo", "dim": 2, "metric": "l2", "index": {"type": "hnsw"}},
        headers={"X-API-Key": ADMIN},
    )
    c.post(
        "/collections/demo/vectors",
        json={"vectors": [{"id": f"v{i}", "values": [i, i]} for i in range(30)]},
        headers={"X-API-Key": ADMIN},
    )


# -- finding 3: the read-only demo key gets tighter search limits than the admin key ----------


@pytest.mark.parametrize(
    "extra",
    [{"k": 21}, {"ef_search": 257}, {"nprobe": 65}],
)
def test_demo_key_cannot_request_expensive_searches(tmp_path: Path, extra: dict[str, int]) -> None:
    with client(tmp_path) as c:
        seed(c)
        body = {"vector": [0, 0], "k": 5, **extra}
        r = c.post("/collections/demo/search", json=body, headers={"X-API-Key": DEMO})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "validation_error"
        # The admin key keeps the full documented limits.
        assert (
            c.post("/collections/demo/search", json=body, headers={"X-API-Key": ADMIN}).status_code
            == 200
        )


def test_demo_key_within_limits_still_works(tmp_path: Path) -> None:
    with client(tmp_path) as c:
        seed(c)
        body = {"vector": [0, 0], "k": 20, "ef_search": 256, "nprobe": 64}
        assert (
            c.post("/collections/demo/search", json=body, headers={"X-API-Key": DEMO}).status_code
            == 200
        )


# -- finding 6: malformed numeric settings are a configuration error, not a crash -------------


@pytest.mark.parametrize("value", ["lots", "4MB", ""])
def test_malformed_max_body_is_config_error(tmp_path: Path, value: str) -> None:
    env = {
        "VECTORFORGE_ADMIN_KEY": ADMIN,
        "VECTORFORGE_DATA_DIR": str(tmp_path),
        "VECTORFORGE_MAX_BODY_BYTES": value,
    }
    if value == "":
        # Empty means "use the default", which is valid.
        assert Settings.from_env(env).max_body_bytes == 4 * 1024 * 1024
        return
    with pytest.raises(ConfigError, match="VECTORFORGE_MAX_BODY_BYTES"):
        Settings.from_env(env)
