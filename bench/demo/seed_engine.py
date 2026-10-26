"""Load the demo corpus into a running engine as the "demo" collection.

    VECTORFORGE_URL=https://engine.example VECTORFORGE_ADMIN_KEY=... python bench/demo/seed_engine.py

The key is read from the environment only and never printed.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

DEMO = Path(__file__).resolve().parents[2] / "web" / "data" / "demo"


def load() -> tuple[list[dict[str, str]], np.ndarray]:
    docs = json.loads((DEMO / "docs.json").read_text(encoding="utf-8"))
    meta = json.loads((DEMO / "vocab.json").read_text(encoding="utf-8"))
    codes = np.frombuffer((DEMO / "docs.bin").read_bytes(), dtype=np.int8).reshape(
        len(docs), meta["dim"]
    )
    q = meta["docs_quant"]
    emb = (codes.astype(np.float32) + 128) * np.asarray(q["step"], np.float32) + np.asarray(
        q["min"], np.float32
    )
    return docs, emb


def call(base: str, key: str, method: str, path: str, body: object | None = None) -> int:
    if not base.startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise SystemExit("VECTORFORGE_URL must be https (or localhost)")
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(  # noqa: S310 - scheme checked above
        base.rstrip("/") + path,
        data=data,
        method=method,
        headers={"X-API-Key": key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def main() -> None:
    base = os.environ.get("VECTORFORGE_URL", "")
    key = os.environ.get("VECTORFORGE_ADMIN_KEY", "")
    if not base or not key:
        raise SystemExit("set VECTORFORGE_URL and VECTORFORGE_ADMIN_KEY")
    docs, emb = load()
    status = call(
        base,
        key,
        "POST",
        "/collections",
        {
            "name": "demo",
            "dim": int(emb.shape[1]),
            "metric": "cosine",
            "index": {"type": "hnsw", "params": {"M": 16, "ef_construction": 200}},
        },
    )
    print(f"create demo: {status}")
    if status not in (201, 409):
        sys.exit(1)
    for start in range(0, len(docs), 500):
        batch = [
            {
                "id": d["id"],
                "values": emb[i].tolist(),
                "metadata": {"title": d["title"], "module": d["module"], "summary": d["summary"]},
            }
            for i, d in enumerate(docs[start : start + 500], start=start)
        ]
        status = call(base, key, "POST", "/collections/demo/vectors", {"vectors": batch})
        print(f"upsert {start}-{start + len(batch) - 1}: {status}")
        if status != 200:
            sys.exit(1)


if __name__ == "__main__":
    main()
