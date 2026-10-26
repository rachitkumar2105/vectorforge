import json
import struct
from pathlib import Path

import numpy as np
import pytest

from vectorforge.storage.metadata import Manifest, atomic_write_json, read_json
from vectorforge.storage.segment import SegmentStore
from vectorforge.storage.wal import (
    HEADER,
    MAX_RECORD_BYTES,
    Op,
    WalRecord,
    WriteAheadLog,
)

# -- segments ---------------------------------------------------------------------------------


def test_segment_append_and_read_across_segment_boundary(tmp_path: Path) -> None:
    store = SegmentStore(tmp_path, dim=3, capacity=4)
    rows = np.arange(30, dtype=np.float32).reshape(10, 3)
    for label, row in enumerate(rows):
        store.write(label, row)
    assert store.count == 10
    assert len(list(tmp_path.glob("seg_*.vec"))) == 3
    np.testing.assert_array_equal(store.read_all(), rows)
    np.testing.assert_array_equal(store.read([7, 1]), rows[[7, 1]])
    store.flush()
    store.close()


def test_segment_reopen_trusts_only_the_given_count(tmp_path: Path) -> None:
    store = SegmentStore(tmp_path, dim=2, capacity=8)
    for label in range(5):
        store.write(label, np.full(2, label, dtype=np.float32))
    store.flush()
    store.close()
    reopened = SegmentStore(tmp_path, dim=2, capacity=8, count=3)
    assert reopened.count == 3
    np.testing.assert_array_equal(reopened.read_all()[:, 0], [0, 1, 2])
    # Replay may rewrite a slot at or below count (idempotent), but never skip ahead.
    reopened.write(3, np.full(2, 9, dtype=np.float32))
    reopened.write(3, np.full(2, 8, dtype=np.float32))
    with pytest.raises(ValueError, match="append-only"):
        reopened.write(10, np.zeros(2, dtype=np.float32))
    reopened.close()


def test_segment_rejects_wrong_dimension(tmp_path: Path) -> None:
    store = SegmentStore(tmp_path, dim=2, capacity=4)
    with pytest.raises(ValueError):
        store.write(0, np.zeros(3, dtype=np.float32))
    store.close()


def test_segment_default_capacity_targets_32_mib(tmp_path: Path) -> None:
    store = SegmentStore(tmp_path, dim=128)
    assert store.capacity == 32 * 1024 * 1024 // (128 * 4)
    assert store.read_all().shape == (0, 128)
    store.close()


# -- WAL --------------------------------------------------------------------------------------


def upsert(lsn: int, ident: str = "a", dim: int = 4) -> WalRecord:
    vec = np.arange(dim, dtype=np.float32) + lsn
    return WalRecord(lsn=lsn, op=Op.UPSERT, ident=ident, vector=vec, metadata={"n": lsn})


def test_wal_round_trip(tmp_path: Path) -> None:
    wal = WriteAheadLog(tmp_path / "wal.log")
    wal.append([upsert(1), upsert(2, "b")])
    wal.append([WalRecord(lsn=3, op=Op.DELETE, ident="a")])
    wal.close()
    records, report = WriteAheadLog.replay(tmp_path / "wal.log")
    assert [r.lsn for r in records] == [1, 2, 3]
    assert records[1].ident == "b" and records[1].metadata == {"n": 2}
    np.testing.assert_array_equal(records[0].vector, np.arange(4, dtype=np.float32) + 1)
    assert records[2].op is Op.DELETE and records[2].vector is None
    assert report.truncated_bytes == 0


def test_wal_replay_of_missing_file_is_empty(tmp_path: Path) -> None:
    records, report = WriteAheadLog.replay(tmp_path / "nope.log")
    assert records == [] and report.valid_bytes == 0


@pytest.mark.parametrize("cut", [1, 5, 8, 12, -1])
def test_torn_tail_is_discarded_and_truncated(tmp_path: Path, cut: int) -> None:
    path = tmp_path / "wal.log"
    wal = WriteAheadLog(path)
    wal.append([upsert(1), upsert(2)])
    good = path.stat().st_size
    wal.append([upsert(3)])
    wal.close()
    full = path.stat().st_size
    # Simulate a crash part-way through writing record 3: keep only `cut` bytes of it.
    keep = good + (cut if cut > 0 else (full - good) - 1)
    with path.open("r+b") as f:
        f.truncate(keep)
    records, report = WriteAheadLog.replay(path)
    assert [r.lsn for r in records] == [1, 2]
    assert report.truncated_bytes == keep - good
    assert path.stat().st_size == good, "torn tail must be cut off so new appends start clean"


def test_crc_mismatch_rejects_record(tmp_path: Path) -> None:
    path = tmp_path / "wal.log"
    wal = WriteAheadLog(path)
    wal.append([upsert(1)])
    good = path.stat().st_size
    wal.append([upsert(2)])
    wal.close()
    data = bytearray(path.read_bytes())
    data[-3] ^= 0xFF  # flip bits inside record 2's payload
    path.write_bytes(bytes(data))
    records, report = WriteAheadLog.replay(path)
    assert [r.lsn for r in records] == [1]
    assert report.reason == "crc mismatch"
    assert path.stat().st_size == good


def test_absurd_length_prefix_is_treated_as_corruption(tmp_path: Path) -> None:
    path = tmp_path / "wal.log"
    wal = WriteAheadLog(path)
    wal.append([upsert(1)])
    wal.close()
    with path.open("ab") as f:
        f.write(struct.pack(HEADER, MAX_RECORD_BYTES + 1, 0) + b"x" * 16)
    records, report = WriteAheadLog.replay(path)
    assert [r.lsn for r in records] == [1]
    assert report.reason == "length out of range"


def test_appends_after_recovery_are_readable(tmp_path: Path) -> None:
    path = tmp_path / "wal.log"
    wal = WriteAheadLog(path)
    wal.append([upsert(1)])
    wal.close()
    with path.open("ab") as f:
        f.write(b"\x10\x00")  # torn header
    WriteAheadLog.replay(path)
    wal = WriteAheadLog(path)
    wal.append([upsert(2)])
    wal.truncate()
    wal.append([upsert(3)])
    wal.close()
    records, _ = WriteAheadLog.replay(path)
    assert [r.lsn for r in records] == [3]


def test_unicode_ids_and_metadata_survive(tmp_path: Path) -> None:
    path = tmp_path / "wal.log"
    wal = WriteAheadLog(path)
    rec = WalRecord(lsn=1, op=Op.UPSERT, ident="doc:é", vector=np.ones(2, np.float32),
                    metadata={"title": "naïve café"})
    wal.append([rec])
    wal.close()
    records, _ = WriteAheadLog.replay(path)
    assert records[0].ident == "doc:é" and records[0].metadata == {"title": "naïve café"}


# -- manifest ---------------------------------------------------------------------------------


def test_atomic_write_replaces_and_leaves_no_temp_file(tmp_path: Path) -> None:
    target = tmp_path / "manifest.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})
    assert read_json(target) == {"v": 2}
    assert [p.name for p in tmp_path.iterdir()] == ["manifest.json"]


def test_interrupted_write_keeps_previous_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "manifest.json"
    atomic_write_json(target, {"v": 1})

    def boom(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("vectorforge.storage.metadata.os.replace", boom)
    with pytest.raises(OSError):
        atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text()) == {"v": 1}


def test_manifest_round_trip(tmp_path: Path) -> None:
    m = Manifest(name="docs", dim=8, metric="cosine", index_type="hnsw", index_params={"M": 8})
    m.checkpoint_lsn = 42
    m.count = 7
    m.save(tmp_path)
    loaded = Manifest.load(tmp_path)
    assert loaded == m
    with pytest.raises(FileNotFoundError):
        Manifest.load(tmp_path / "missing")
