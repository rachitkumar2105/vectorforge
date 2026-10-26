"""Build the semantic-search demo corpus and its embeddings.

    python bench/demo/build_demo.py           # writes web/data/demo/*

Corpus: docstrings of functions, classes and methods in a fixed list of Python standard-library
modules (PSF licence). Source files are parsed with ``ast``; nothing is imported or executed.

Embedding: SIF (Arora, Liang, Ma 2017, "A Simple but Tough-to-Beat Baseline for Sentence
Embeddings"): a weighted average of GloVe-100d word vectors with weight a / (a + p(w)), then the
first principal component of the corpus is removed. No neural model, no new dependency, and the
same arithmetic is re-implemented in the site's route handler to embed a query.

Outputs (web/data/demo/):
    docs.json    [{id, title, module, summary}]
    docs.bin     int8 doc embeddings (per-dimension scalar quantization, see vocab.json "docs")
    vocab.json   words, SIF weights, quantizer ranges, principal component
    vocab.bin    int8 word vectors for the vocabulary
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import numpy as np

from vectorforge.core.quantize import ScalarQuantizer

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "web" / "data" / "demo"
GLOVE = Path.home() / "datasets" / "glove-100"
STDLIB = (
    Path(sys.base_prefix) / "Lib"
    if sys.platform == "win32"
    else Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
)

MODULES = [
    "abc",
    "argparse",
    "array",
    "ast",
    "asyncio/base_events",
    "asyncio/locks",
    "asyncio/queues",
    "asyncio/streams",
    "asyncio/tasks",
    "base64",
    "bisect",
    "bz2",
    "calendar",
    "codecs",
    "collections/__init__",
    "concurrent/futures/_base",
    "concurrent/futures/thread",
    "configparser",
    "contextlib",
    "copy",
    "csv",
    "dataclasses",
    "datetime",
    "decimal",
    "difflib",
    "email/message",
    "email/utils",
    "enum",
    "fnmatch",
    "fractions",
    "ftplib",
    "functools",
    "getopt",
    "gettext",
    "glob",
    "gzip",
    "hashlib",
    "heapq",
    "hmac",
    "html/__init__",
    "html/parser",
    "http/client",
    "http/cookies",
    "http/server",
    "imaplib",
    "inspect",
    "ipaddress",
    "json/__init__",
    "json/decoder",
    "json/encoder",
    "locale",
    "logging/__init__",
    "logging/handlers",
    "lzma",
    "mailbox",
    "mimetypes",
    "netrc",
    "numbers",
    "operator",
    "optparse",
    "os",
    "pathlib/__init__",
    "pathlib/_local",
    "pickle",
    "pkgutil",
    "platform",
    "plistlib",
    "poplib",
    "pprint",
    "queue",
    "quopri",
    "random",
    "re/__init__",
    "sched",
    "secrets",
    "selectors",
    "shelve",
    "shlex",
    "shutil",
    "smtplib",
    "socket",
    "socketserver",
    "sqlite3/__init__",
    "ssl",
    "statistics",
    "string",
    "subprocess",
    "tarfile",
    "tempfile",
    "textwrap",
    "threading",
    "timeit",
    "tokenize",
    "traceback",
    "types",
    "typing",
    "unittest/case",
    "urllib/parse",
    "urllib/request",
    "uuid",
    "warnings",
    "wave",
    "weakref",
    "xml/etree/ElementTree",
    "zipfile/__init__",
    "zipfile",
    "zoneinfo/_zoneinfo",
    "turtle",
    "tkinter/__init__",
    "multiprocessing/pool",
    "multiprocessing/process",
    "multiprocessing/connection",
    "xml/dom/minidom",
    "posixpath",
    "ntpath",
    "_collections_abc",
    "importlib/__init__",
    "importlib/metadata/__init__",
    "email/header",
    "email/parser",
    "email/policy",
    "asyncio/events",
    "asyncio/subprocess",
    "unittest/mock",
    "pdb",
    "cmd",
    "dis",
    "symtable",
    "tomllib/_parser",
    "doctest",
    "trace",
    "cProfile",
    "profile",
    "pstats",
    "codecs",
    "io",
    "_pyio",
    "nntplib",
    "telnetlib",
    "xmlrpc/client",
    "xmlrpc/server",
    "wsgiref/simple_server",
    "wsgiref/handlers",
    "urllib/robotparser",
    "graphlib",
    "filecmp",
    "fileinput",
    "linecache",
    "reprlib",
    "stat",
    "string/__init__",
    "colorsys",
    "imghdr",
    "sndhdr",
    "chunk",
    "aifc",
    "sunau",
    "binhex",
    "uu",
    "smtpd",
    "asyncore",
    "asynchat",
]

WORD = re.compile(r"[a-z]+")
SIF_A = 1e-3


def summary(doc: str) -> str:
    first = doc.strip().split("\n\n")[0]
    text = " ".join(first.split())
    return text if len(text) <= 280 else text[:277].rsplit(" ", 1)[0] + "..."


def collect() -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    seen: set[str] = set()
    for mod in MODULES:
        path = STDLIB / f"{mod}.py"
        if not path.exists():
            continue
        module = mod.replace("/__init__", "").replace("/", ".")
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node, prefix in _walk(tree, module):
            doc = ast.get_docstring(node)
            if not doc or node.name.startswith("_"):
                continue
            title = f"{prefix}.{node.name}"
            text = summary(doc)
            if title in seen or len(text) < 20:
                continue
            seen.add(title)
            docs.append({"id": f"d{len(docs)}", "title": title, "module": module, "summary": text})
    return docs


def _walk(tree: ast.Module, module: str):  # type: ignore[no-untyped-def]
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node, module
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            yield node, module
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef | ast.AsyncFunctionDef):
                    yield sub, f"{module}.{node.name}"


def tokens(text: str) -> list[str]:
    # Split identifiers on underscores and camelCase so "read_text" and "TextIOWrapper"
    # contribute "read", "text", "io", "wrapper".
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", text).replace("_", " ").replace(".", " ")
    return WORD.findall(spaced.lower())


def main() -> None:
    docs = collect()
    words = (GLOVE / "words.txt").read_text(encoding="utf-8").splitlines()
    vectors = np.load(GLOVE / "vectors.npy", mmap_mode="r")
    rank = {w: i + 1 for i, w in enumerate(words) if w.isalpha() and w.islower()}

    doc_tokens = [tokens(d["title"].split(".")[-1]) * 2 + tokens(d["summary"]) for d in docs]
    corpus_words = {t for toks in doc_tokens for t in toks if t in rank}
    vocab = sorted(
        corpus_words | {w for w, r in rank.items() if r <= 30_000}, key=lambda w: rank[w]
    )
    index = {w: i for i, w in enumerate(vocab)}
    vmat = np.stack([vectors[rank[w] - 1] for w in vocab]).astype(np.float32)
    # GloVe rows are frequency-ordered; Zipf's law turns rank into an estimated probability.
    harmonic = np.log(len(words)) + 0.5772
    weights = np.array(
        [SIF_A / (SIF_A + 1.0 / (rank[w] * harmonic)) for w in vocab], dtype=np.float32
    )

    def embed(toks: list[str]) -> np.ndarray:
        ids = [index[t] for t in toks if t in index]
        if not ids:
            return np.zeros(vmat.shape[1], dtype=np.float32)
        return (weights[ids, None] * vmat[ids]).sum(axis=0) / len(ids)

    raw = np.stack([embed(t) for t in doc_tokens])
    keep = np.linalg.norm(raw, axis=1) > 0
    docs = [d for d, k in zip(docs, keep, strict=True) if k]
    raw = raw[keep]
    for i, d in enumerate(docs):
        d["id"] = f"d{i}"
    # SIF step 2: remove the projection on the first principal component (the "common
    # discourse" direction that every sentence shares), then unit-normalise.
    _, _, vt = np.linalg.svd(raw - 0.0, full_matrices=False)
    pc = vt[0].astype(np.float32)
    emb = raw - np.outer(raw @ pc, pc)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)

    OUT.mkdir(parents=True, exist_ok=True)
    vq = ScalarQuantizer.fit(vmat)
    dq = ScalarQuantizer.fit(emb)
    (OUT / "vocab.bin").write_bytes(vq.encode(vmat).tobytes())
    (OUT / "docs.bin").write_bytes(dq.encode(emb).tobytes())
    meta = {
        "dim": int(vmat.shape[1]),
        "sif_a": SIF_A,
        "words": vocab,
        "weights": [round(float(w), 5) for w in weights],
        "vocab_quant": {"min": vq.vmin.round(6).tolist(), "step": vq.step.round(8).tolist()},
        "docs_quant": {"min": dq.vmin.round(6).tolist(), "step": dq.step.round(8).tolist()},
        "pc": pc.round(6).tolist(),
        "count": len(docs),
        "source": "Python "
        + sys.version.split()[0]
        + " standard library docstrings; GloVe 6B 100d",
    }
    (OUT / "vocab.json").write_text(
        json.dumps(meta, separators=(",", ":")), encoding="utf-8", newline="\n"
    )
    (OUT / "docs.json").write_text(
        json.dumps(docs, separators=(",", ":")), encoding="utf-8", newline="\n"
    )
    # Tiny file the page imports for the corpus size, so rendering never loads the 4 MB corpus.
    (OUT / "meta.json").write_text(json.dumps({"count": len(docs)}), encoding="utf-8", newline="\n")
    print(f"{len(docs)} documents, vocab {len(vocab)} words -> {OUT}")


if __name__ == "__main__":
    main()
