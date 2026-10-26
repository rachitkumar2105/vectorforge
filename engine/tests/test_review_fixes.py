"""Regression tests for the Phase 5 code-review findings."""

from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from vectorforge.collection import (
    Collection,
    CollectionClosedError,
    UpsertItem,
    VectorValidationError,
)
from vectorforge.service.app import create_app
from vectorforge.service.security import ConfigError, Settings
from vectorforge.storage.wal import MAX_RECORD_BYTES, Op, WalRecord, WriteAheadLog

ADMIN = "a" * 40


def test_oversized_wal_record_is_refused_before_ack(tmp_path: Path) -> None:
    c = Collection.create(tmp_path, "big", dim=2, metric="l2", index_type="flat")
    huge = {"blob": "x" * (MAX_RECORD_BYTES + 10)}
    with pytest.raises(VectorValidationError):
        c.upsert([UpsertItem("a", np.ones(2, dtype=np.float32), huge)])
    c.upsert([UpsertItem("b", np.ones(2, dtype=np.float32), {})])
    c._release_files()
    again = Collection.open(c.path)
    assert again.count == 1 and again.replay_report.reason is None
    again.close()


def test_wal_encode_rejects_oversized_payload() -> None:
    rec = WalRecord(
        lsn=1,
        op=Op.UPSERT,
        ident="a",
        vector=np.ones(2, np.float32),
        metadata={"b": "x" * MAX_RECORD_BYTES},
    )
    with pytest.raises(ValueError, match="too large"):
        rec.encode()


def test_wal_replay_streams_many_records(tmp_path: Path) -> None:
    wal = WriteAheadLog(tmp_path / "w.log")
    wal.append([WalRecord(lsn=i, op=Op.DELETE, ident=f"i{i}") for i in range(1, 2001)])
    wal.close()
    records, report = WriteAheadLog.replay(tmp_path / "w.log")
    assert len(records) == 2000 and report.truncated_bytes == 0


def test_operations_after_drop_raise_closed(tmp_path: Path) -> None:
    c = Collection.create(tmp_path, "gone", dim=2, metric="l2", index_type="flat")
    c.upsert([UpsertItem("a", np.ones(2, dtype=np.float32), {})])
    c.drop()
    with pytest.raises(CollectionClosedError):
        c.search(np.ones(2, dtype=np.float32), k=1)
    with pytest.raises(CollectionClosedError):
        c.upsert([UpsertItem("b", np.ones(2, dtype=np.float32), {})])
    with pytest.raises(CollectionClosedError):
        c.get("a")


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost.evil.com",
        "http://127.0.0.1.attacker.net",
        "https://ok.example/path",
        "ftp://localhost",
        "http://example.com",
        "https://",
    ],
)
def test_cors_origin_must_be_exact(tmp_path: Path, origin: str) -> None:
    with pytest.raises(ConfigError):
        Settings(admin_key=ADMIN, data_dir=tmp_path, cors_origins=[origin])


def test_cors_accepts_exact_origins(tmp_path: Path) -> None:
    s = Settings(
        admin_key=ADMIN,
        data_dir=tmp_path,
        cors_origins=[
            "https://vectorforge.vercel.app",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
    )
    assert len(s.cors_origins) == 3


def test_valid_key_not_locked_out_by_others_failures(tmp_path: Path) -> None:
    app = create_app(Settings(admin_key=ADMIN, data_dir=tmp_path, auth_fail_rate=(0.01, 2)))
    with TestClient(app) as c:
        for _ in range(5):
            c.get("/collections", headers={"X-API-Key": "z" * 40})
        assert c.get("/collections", headers={"X-API-Key": ADMIN}).status_code == 200
        assert c.get("/collections", headers={"X-API-Key": "z" * 40}).status_code == 429


def test_413_and_preflight_carry_security_headers_and_metrics(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            admin_key=ADMIN,
            data_dir=tmp_path,
            max_body_bytes=1024,
            cors_origins=["http://localhost:3000"],
        )
    )
    with TestClient(app) as c:
        r = c.post(
            "/collections",
            content=b"x" * 5000,
            headers={"X-API-Key": ADMIN, "Content-Type": "application/json"},
        )
        assert r.status_code == 413 and r.headers["X-Content-Type-Options"] == "nosniff"
        pre = c.options(
            "/collections",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
        )
        assert pre.headers["X-Content-Type-Options"] == "nosniff"
        text = c.get("/metrics", headers={"X-API-Key": ADMIN}).text
        assert 'status="413"' in text
