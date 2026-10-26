"""Append-only write-ahead log with a length prefix and crc32 per record.

On-disk record::

    +-----------+-----------+------------------------------------------------+
    | length u32| crc32 u32 | payload (length bytes)                         |
    +-----------+-----------+------------------------------------------------+
    payload = lsn u64 | op u8 | id_len u16 | id utf-8
              [| dim u32 | dim x f32 | meta_len u32 | meta json]   (upserts only)

Why both a length and a CRC: the length tells replay where the next record starts; the CRC tells
it whether the bytes it just read are the bytes that were written. A crash mid-append leaves a
*torn tail*: a header with no payload, or a short payload, or a payload whose CRC fails. Replay
stops at the first record that fails any check and truncates the file there.

Why truncating is safe: a write is acknowledged only after ``fsync`` returns, so every
acknowledged record is complete on disk and lies *before* any torn bytes. Only unacknowledged
data is ever discarded. A CRC failure in the middle of the log (bit rot, not a torn write) is
handled the same way: everything from that record on is untrusted and dropped. Replaying past it
could apply an operation whose predecessor was lost, which is worse than stopping.
"""

from __future__ import annotations

import enum
import json
import os
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np
import numpy.typing as npt

HEADER = "<II"  # length, crc32
HEADER_SIZE = struct.calcsize(HEADER)
# A corrupt length field could ask for gigabytes. No legitimate record is near this size
# (4096 dims x 4 bytes + 4 KiB metadata), so anything larger is corruption.
MAX_RECORD_BYTES = 1 << 20


class RecordTooLargeError(ValueError):
    """A record would exceed MAX_RECORD_BYTES. Refused before anything is written, because
    replay treats an over-long length prefix as corruption and would drop it after the ack."""


class Op(enum.IntEnum):
    UPSERT = 1
    DELETE = 2


@dataclass
class WalRecord:
    lsn: int
    op: Op
    ident: str
    vector: npt.NDArray[np.float32] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def encode(self) -> bytes:
        ident = self.ident.encode("utf-8")
        parts = [struct.pack("<QBH", self.lsn, int(self.op), len(ident)), ident]
        if self.op is Op.UPSERT:
            assert self.vector is not None
            vec = np.ascontiguousarray(self.vector, dtype="<f4")
            meta = json.dumps(self.metadata, separators=(",", ":"), sort_keys=True).encode()
            parts += [
                struct.pack("<I", vec.shape[0]),
                vec.tobytes(),
                struct.pack("<I", len(meta)),
                meta,
            ]
        payload = b"".join(parts)
        if len(payload) > MAX_RECORD_BYTES:
            raise RecordTooLargeError(f"WAL record too large ({len(payload)} bytes)")
        return struct.pack(HEADER, len(payload), zlib.crc32(payload)) + payload

    @classmethod
    def decode(cls, payload: bytes) -> WalRecord:
        lsn, op, id_len = struct.unpack_from("<QBH", payload, 0)
        pos = struct.calcsize("<QBH")
        ident = payload[pos : pos + id_len].decode("utf-8")
        pos += id_len
        if Op(op) is Op.DELETE:
            return cls(lsn=lsn, op=Op.DELETE, ident=ident)
        (dim,) = struct.unpack_from("<I", payload, pos)
        pos += 4
        vector = np.frombuffer(payload, dtype="<f4", count=dim, offset=pos).astype(np.float32)
        pos += 4 * dim
        (meta_len,) = struct.unpack_from("<I", payload, pos)
        pos += 4
        metadata = json.loads(payload[pos : pos + meta_len].decode("utf-8"))
        return cls(lsn=lsn, op=Op.UPSERT, ident=ident, vector=vector, metadata=metadata)


@dataclass(frozen=True)
class ReplayReport:
    valid_bytes: int
    truncated_bytes: int
    reason: str | None


class WriteAheadLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: BinaryIO = path.open("ab")

    def append(self, records: list[WalRecord]) -> None:
        """Write a batch, then fsync once (group commit). Returns only when durable."""
        self._file.write(b"".join(r.encode() for r in records))
        self._file.flush()
        os.fsync(self._file.fileno())

    def truncate(self) -> None:
        """Empty the log. Called after a checkpoint has made every record redundant."""
        self._file.truncate(0)
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    @staticmethod
    def replay(path: Path) -> tuple[list[WalRecord], ReplayReport]:
        if not path.exists():
            return [], ReplayReport(0, 0, None)
        size = path.stat().st_size
        records: list[WalRecord] = []
        pos, reason = 0, None
        # Stream record by record: memory stays bounded by one record, not the whole log.
        with path.open("rb") as f:
            while pos < size:
                header = f.read(HEADER_SIZE)
                if len(header) < HEADER_SIZE:
                    reason = "torn header"
                    break
                length, crc = struct.unpack(HEADER, header)
                if length == 0 or length > MAX_RECORD_BYTES:
                    reason = "length out of range"
                    break
                payload = f.read(length)
                if len(payload) < length:
                    reason = "torn payload"
                    break
                if zlib.crc32(payload) != crc:
                    reason = "crc mismatch"
                    break
                try:
                    records.append(WalRecord.decode(payload))
                except (struct.error, ValueError, UnicodeDecodeError):
                    # CRC matched but the content does not parse: a writer bug, not a torn write.
                    reason = "undecodable record"
                    break
                pos += HEADER_SIZE + length
        truncated = size - pos
        if truncated:
            # Cut the bad tail so the next append starts at a record boundary. Without this, new
            # records would sit behind garbage and be unreachable on the next replay.
            with path.open("r+b") as f:
                f.truncate(pos)
                f.flush()
                os.fsync(f.fileno())
        return records, ReplayReport(pos, truncated, reason)
