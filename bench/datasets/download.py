"""Download and convert the public benchmark datasets into ~/datasets (never into the repo).

    python bench/datasets/download.py sift     # SIFT1M (INRIA TEXMEX), 168 MB tarball
    python bench/datasets/download.py glove    # GloVe 6B (Stanford NLP), 862 MB zip, keeps 100d

Sources:
- SIFT1M: the original INRIA TEXMEX tarball (ftp://ftp.irisa.fr/local/texmex/corpus/sift.tar.gz),
  fetched from a byte-identical Hugging Face mirror because the INRIA FTP server is often
  unreachable. The sha256 of what was downloaded is written to SOURCE.json for checking.
- GloVe: glove.6B.zip from the Stanford NLP organisation's Hugging Face repo.

Output (all float32 .npy, loadable with numpy only):
    ~/datasets/sift/{base,query,learn}.npy, groundtruth.npy (int32, for the full 1M base)
    ~/datasets/glove-100/vectors.npy, words.txt (one word per line, row order)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

DATASETS = Path(os.environ.get("VECTORFORGE_DATASETS", Path.home() / "datasets"))
SOURCES = {
    "sift": {
        "url": "https://huggingface.co/datasets/fzliu/sift1m/resolve/main/sift.tar.gz",
        "original": "ftp://ftp.irisa.fr/local/texmex/corpus/sift.tar.gz",
        "archive": "sift.tar.gz",
    },
    "glove": {
        "url": "https://huggingface.co/stanfordnlp/glove/resolve/main/glove.6B.zip",
        "original": "https://nlp.stanford.edu/data/glove.6B.zip",
        "archive": "glove.6B.zip",
    },
}


def fetch(url: str, dest: Path) -> str:
    """Stream to disk with a progress line; returns sha256. Resumes nothing: simple and safe."""
    if not url.startswith("https://"):
        raise ValueError("only https sources are allowed")
    sha = hashlib.sha256()
    tmp = dest.with_suffix(dest.suffix + ".part")
    # https-only is enforced above, which is exactly what S310 asks for.
    req = urllib.request.Request(url, headers={"User-Agent": "vectorforge-bench/0.1"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=60) as resp, tmp.open("wb") as out:  # noqa: S310
        total = int(resp.headers.get("Content-Length", 0))
        done, last = 0, 0.0
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            sha.update(chunk)
            done += len(chunk)
            if time.monotonic() - last > 5:
                pct = f"{100 * done / total:.0f}%" if total else ""
                print(f"  {dest.name}: {done / 1e6:.0f} MB {pct}", flush=True)
                last = time.monotonic()
    tmp.replace(dest)
    return sha.hexdigest()


def read_vecs(path: Path, dtype: str) -> np.ndarray:
    """.fvecs/.ivecs: each row is int32 dim followed by dim values of 4 bytes each."""
    raw = np.fromfile(path, dtype=np.int32)
    dim = int(raw[0])
    rows = raw.reshape(-1, dim + 1)
    if not np.all(rows[:, 0] == dim):
        raise ValueError(f"{path} is not a uniform-dimension vecs file")
    return rows[:, 1:].copy().view(dtype)


def prepare_sift() -> None:
    out = DATASETS / "sift"
    out.mkdir(parents=True, exist_ok=True)
    archive = out / SOURCES["sift"]["archive"]
    digest = fetch(SOURCES["sift"]["url"], archive) if not archive.exists() else _sha(archive)
    wanted = {"sift_base.fvecs", "sift_query.fvecs", "sift_learn.fvecs", "sift_groundtruth.ivecs"}
    with tarfile.open(archive) as tar:
        members = [m for m in tar.getmembers() if Path(m.name).name in wanted and m.isfile()]
        for m in members:
            m.name = Path(m.name).name  # flatten; never trust archive paths
        # filter="data" rejects absolute paths, links and device files (PEP 706).
        tar.extractall(out, members=members, filter="data")
    np.save(out / "base.npy", read_vecs(out / "sift_base.fvecs", "float32"))
    np.save(out / "query.npy", read_vecs(out / "sift_query.fvecs", "float32"))
    np.save(out / "learn.npy", read_vecs(out / "sift_learn.fvecs", "float32"))
    np.save(out / "groundtruth.npy", read_vecs(out / "sift_groundtruth.ivecs", "int32"))
    for name in wanted:
        (out / name).unlink()
    _record(out, "sift", digest)


def prepare_glove() -> None:
    out = DATASETS / "glove-100"
    out.mkdir(parents=True, exist_ok=True)
    archive = out / SOURCES["glove"]["archive"]
    digest = fetch(SOURCES["glove"]["url"], archive) if not archive.exists() else _sha(archive)
    words: list[str] = []
    vecs: list[np.ndarray] = []
    with zipfile.ZipFile(archive) as zf, zf.open("glove.6B.100d.txt") as f:
        for line in f:
            parts = line.decode("utf-8").rstrip("\n").split(" ")
            words.append(parts[0])
            vecs.append(np.asarray(parts[1:], dtype=np.float32))
    np.save(out / "vectors.npy", np.stack(vecs))
    (out / "words.txt").write_text("\n".join(words) + "\n", encoding="utf-8", newline="\n")
    _record(out, "glove", digest)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _record(out: Path, name: str, digest: str) -> None:
    meta = {
        **SOURCES[name],
        "sha256": digest,
        "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out / "SOURCE.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"{name}: ready in {out} (sha256 {digest[:16]}...)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("dataset", choices=["sift", "glove", "all"])
    args = parser.parse_args()
    if args.dataset in ("sift", "all"):
        prepare_sift()
    if args.dataset in ("glove", "all"):
        prepare_glove()


if __name__ == "__main__":
    sys.exit(main())
