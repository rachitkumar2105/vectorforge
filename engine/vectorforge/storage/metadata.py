"""Collection manifests: small JSON files replaced atomically.

``atomic_write_json`` writes to a temp file in the same directory, fsyncs it, then renames it
over the target. ``os.replace`` is atomic on POSIX and on Windows (same volume), so a reader
sees either the old manifest or the new one, never a half-written file.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

FORMAT_VERSION = 1


def atomic_write_json(path: Path, obj: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(obj, f, sort_keys=True, separators=(",", ":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    if sys.platform != "win32":  # pragma: no cover - exercised in Linux CI
        # fsync the directory so the rename itself survives power loss (POSIX only; Windows
        # cannot open a directory for fsync and its rename is journaled by NTFS).
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Manifest:
    name: str
    dim: int
    metric: str
    index_type: str
    index_params: dict[str, Any] = field(default_factory=dict)
    # Everything with lsn <= checkpoint_lsn is captured by the snapshot files named below.
    checkpoint_lsn: int = 0
    # Number of labels (rows in segments) covered by the snapshot.
    count: int = 0
    segment_capacity: int = 0
    index_dir: str | None = None
    state_file: str | None = None
    version: int = FORMAT_VERSION

    FILENAME = "manifest.json"

    def save(self, directory: Path) -> None:
        atomic_write_json(directory / self.FILENAME, asdict(self))

    @classmethod
    def load(cls, directory: Path) -> Manifest:
        data = read_json(directory / cls.FILENAME)
        if data.get("version") != FORMAT_VERSION:
            raise ValueError(f"unsupported manifest version {data.get('version')}")
        return cls(**data)
