"""Seed a collection from committed sample data at startup.

Hosts without a persistent disk (Render's free tier) lose the data directory on every restart.
With ``VECTORFORGE_SEED_DIR`` set, the engine rebuilds the demo collection from a seed manifest
on boot, so the public demo always works. If the collection already exists (a persistent data
directory), seeding is skipped and the stored data wins.

Seed directory layout (written by ``bench/demo/build_demo.py``)::

    seed.json   {"collection": {name, dim, metric, index}, "documents": "docs.json",
                 "vectors": "docs.bin", "count": n, "quant": {"min": [...], "step": [...]},
                 "metadata_fields": [...]}
    docs.json   [{"id": ..., <metadata fields>}, ...]
    docs.bin    n x dim int8 codes (per-dimension scalar quantization)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from vectorforge.collection import UpsertItem
from vectorforge.core.quantize import ScalarQuantizer
from vectorforge.service.database import CollectionNotFoundError, Database
from vectorforge.service.observability import log_event
from vectorforge.service.security import ConfigError

logger = logging.getLogger("vectorforge.seed")
BATCH = 500


def _load(seed_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], np.ndarray]:
    try:
        manifest: dict[str, Any] = json.loads((seed_dir / "seed.json").read_text(encoding="utf-8"))
        docs: list[dict[str, Any]] = json.loads(
            (seed_dir / manifest["documents"]).read_text(encoding="utf-8")
        )
        spec = manifest["collection"]
        dim, count = int(spec["dim"]), int(manifest["count"])
        codes = np.frombuffer((seed_dir / manifest["vectors"]).read_bytes(), dtype=np.int8)
        quant = ScalarQuantizer(
            np.asarray(manifest["quant"]["min"], dtype=np.float32),
            np.asarray(manifest["quant"]["step"], dtype=np.float32),
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ConfigError(f"seed data in {seed_dir} is missing or malformed") from exc
    if codes.size != count * dim or len(docs) != count or quant.dim != dim:
        raise ConfigError(
            f"seed data in {seed_dir} is inconsistent: manifest says {count} x {dim}, "
            f"found {codes.size} values and {len(docs)} documents"
        )
    return manifest, docs, quant.decode(codes.reshape(count, dim))


def apply_seed(db: Database, seed_dir: Path) -> None:
    manifest, docs, vectors = _load(seed_dir)
    spec = manifest["collection"]
    name = spec["name"]
    try:
        db.get(name)
        log_event(logger, "seed skipped", collection=name, reason="collection exists")
        return
    except CollectionNotFoundError:
        pass
    collection = db.create(
        name,
        dim=int(spec["dim"]),
        metric=spec["metric"],
        index_type=spec["index"]["type"],
        index_params=dict(spec["index"].get("params", {})),
    )
    fields = list(manifest.get("metadata_fields", []))
    for start in range(0, len(docs), BATCH):
        collection.upsert(
            [
                UpsertItem(
                    str(d["id"]),
                    vectors[i],
                    {f: d[f] for f in fields if f in d},
                )
                for i, d in enumerate(docs[start : start + BATCH], start=start)
            ]
        )
    log_event(logger, "seeded collection", collection=name, count=len(docs))
