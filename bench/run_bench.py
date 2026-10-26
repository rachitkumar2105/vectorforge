"""VectorForge benchmark harness. Regenerates every number on the website.

    python bench/datasets/download.py all     # once
    python bench/run_bench.py                 # writes bench/results/*.json

What it does, per dataset:
1. Load a documented subset (first N base vectors; SIFT's official queries, GloVe held-out words).
2. Exact ground truth with the VectorForge flat index.
3. Build VectorForge HNSW, IVF and IVF+int8, and FAISS HNSWFlat / IVFFlat with matched params.
4. Sweep ef_search (HNSW) and nprobe (IVF); one query at a time, single thread, for everything,
   so the comparison is per-query latency on one core. FAISS is pinned to 1 OpenMP thread.
5. Record recall@1, recall@10, QPS, p50/p95/p99 latency, build time and memory, plus hardware
   and library versions.

FAISS is imported here and only here (credibility rule 1: never in engine/).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

import vectorforge
from vectorforge.core.distance import normalize_rows
from vectorforge.index.flat import FlatIndex
from vectorforge.index.hnsw import HNSWIndex
from vectorforge.index.ivf import IVFIndex
from vectorforge.metrics import recall_at_k

REPO = Path(__file__).resolve().parents[1]
DATASETS = Path(os.environ.get("VECTORFORGE_DATASETS", Path.home() / "datasets"))
EF_SWEEP = [10, 20, 40, 80, 120, 200, 400]
NPROBE_SWEEP = [1, 2, 4, 8, 16, 32, 64, 128]
HNSW_M, HNSW_EFC = 16, 200


@dataclass
class Point:
    param: int
    recall_at_1: float
    recall_at_10: float
    qps: float
    p50_ms: float
    p95_ms: float
    p99_ms: float


@dataclass
class Series:
    id: str
    label: str
    engine: str  # "vectorforge" | "faiss"
    params: dict[str, Any]
    sweep: str | None
    build_s: float
    memory_bytes: int
    memory_note: str
    rss_delta_bytes: int  # coarse; allocator reuse makes it unreliable
    points: list[Point] = field(default_factory=list)


# -- environment ----------------------------------------------------------------------------------


def rss_bytes() -> int:
    """Resident set size of this process, without psutil."""
    if sys.platform == "win32":

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        c = Counters()
        c.cb = ctypes.sizeof(c)
        handle = ctypes.windll.kernel32.GetCurrentProcess()  # type: ignore[attr-defined]
        ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(c), c.cb)  # type: ignore[attr-defined]
        return int(c.WorkingSetSize)
    with open("/proc/self/statm") as f:
        return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")


def hardware() -> dict[str, Any]:
    cpu = platform.processor()
    ram = 0
    if sys.platform == "win32":
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        )
        cpu = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()

        class MemStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        m = MemStatus()
        m.dwLength = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))  # type: ignore[attr-defined]
        ram = int(m.ullTotalPhys)
    else:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
        with open("/proc/meminfo") as f:
            ram = int(f.readline().split()[1]) * 1024
    return {
        "cpu": cpu,
        "logical_cores": os.cpu_count(),
        "ram_bytes": ram,
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
    }


def versions(faiss: Any) -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "faiss": getattr(faiss, "__version__", "unknown"),
        "vectorforge": vectorforge.__version__,
    }


def git_commit() -> str:
    try:
        out = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# -- datasets -------------------------------------------------------------------------------------


def load_dataset(name: str, n: int, nq: int) -> tuple[np.ndarray, np.ndarray, str, dict[str, Any]]:
    if name == "sift":
        base = np.load(DATASETS / "sift" / "base.npy", mmap_mode="r")
        queries = np.load(DATASETS / "sift" / "query.npy")[:nq]
        info = {
            "name": "SIFT1M",
            "subset": f"first {n:,} of 1,000,000 base vectors; first {nq:,} of the 10,000 official queries",
            "dim": 128,
            "metric": "l2",
            "source": json.loads((DATASETS / "sift" / "SOURCE.json").read_text())["original"],
        }
        return np.ascontiguousarray(base[:n], dtype=np.float32), queries, "l2", info
    if name == "glove":
        vecs = np.load(DATASETS / "glove-100" / "vectors.npy", mmap_mode="r")
        # The last row of this distribution is "<unk>"; exclude it. Rows are frequency-ordered,
        # so the base is the n most frequent words and queries are held-out, rarer words.
        usable = vecs.shape[0] - 1
        rng = np.random.default_rng(0)
        q_idx = np.sort(rng.choice(np.arange(n, usable), size=nq, replace=False))
        info = {
            "name": "GloVe-100d (6B tokens)",
            "subset": f"{n:,} most frequent of 400,000 words as base; {nq:,} random held-out words as queries (seed 0)",
            "dim": 100,
            "metric": "cosine",
            "source": json.loads((DATASETS / "glove-100" / "SOURCE.json").read_text())["original"],
        }
        return (
            np.ascontiguousarray(vecs[:n], dtype=np.float32),
            np.asarray(vecs[q_idx], dtype=np.float32),
            "cosine",
            info,
        )
    raise ValueError(name)


# -- measurement ----------------------------------------------------------------------------------


def measure(
    search: Callable[[np.ndarray], np.ndarray], queries: np.ndarray, truth: np.ndarray, param: int
) -> Point:
    for q in queries[:10]:  # warm caches and lazy allocations
        search(q)
    found = np.full((len(queries), 10), -1, dtype=np.int64)
    lat = np.empty(len(queries))
    t_all = time.perf_counter()
    for i, q in enumerate(queries):
        t = time.perf_counter()
        labels = search(q)
        lat[i] = time.perf_counter() - t
        found[i, : len(labels)] = labels[:10]
    total = time.perf_counter() - t_all
    return Point(
        param=param,
        recall_at_1=round(recall_at_k(found, truth, 1), 4),
        recall_at_10=round(recall_at_k(found, truth, 10), 4),
        qps=round(len(queries) / total, 1),
        p50_ms=round(float(np.percentile(lat, 50)) * 1000, 3),
        p95_ms=round(float(np.percentile(lat, 95)) * 1000, 3),
        p99_ms=round(float(np.percentile(lat, 99)) * 1000, 3),
    )


def python_bytes(index: HNSWIndex) -> int:
    """Actual in-memory size of the HNSW graph as Python holds it: the vector matrix plus every
    list object (sys.getsizeof counts the list header and its 8-byte pointers) plus one int
    object per label. Node ids are shared int objects, so they are counted once."""
    links = index._links
    total = index._vectors.nbytes() + sys.getsizeof(links) + sys.getsizeof(index._levels)
    for node in links:
        total += sys.getsizeof(node) + sum(sys.getsizeof(layer) for layer in node)
    return total + 28 * len(index)


def timed_build(build: Callable[[], Any]) -> tuple[Any, float, int]:
    before = rss_bytes()
    t = time.perf_counter()
    obj = build()
    return obj, time.perf_counter() - t, max(0, rss_bytes() - before)


def run_dataset(
    name: str, n: int, nq: int, nlist: int, faiss: Any, log: Callable[[str], None]
) -> dict[str, Any]:
    base, queries, metric, info = load_dataset(name, n, nq)
    log(f"[{name}] base {base.shape}, queries {queries.shape}, metric {metric}")
    flat_vf, flat_build, flat_rss = timed_build(lambda: _flat(base, metric))
    truth = flat_vf.search_batch(queries, k=10)
    series: list[Series] = []

    s = Series(
        "vf-flat",
        "VectorForge flat (exact)",
        "vectorforge",
        {},
        None,
        flat_build,
        flat_vf.memory_bytes(),
        "float32 vectors",
        flat_rss,
    )
    s.points.append(measure(lambda q: flat_vf.search(q, 10).labels, queries, truth, 0))
    series.append(s)
    log(f"[{name}] vf-flat {s.points[-1]}")

    hnsw, build_s, rss = timed_build(lambda: _vf_hnsw(base, metric, log))
    s = Series(
        "vf-hnsw",
        "VectorForge HNSW",
        "vectorforge",
        {"M": HNSW_M, "ef_construction": HNSW_EFC},
        "ef_search",
        build_s,
        python_bytes(hnsw),
        "measured with sys.getsizeof: float32 vectors + Python list-of-lists graph",
        rss,
    )
    s.params["compact_bytes"] = hnsw.memory_bytes()
    for ef in EF_SWEEP:
        s.points.append(
            measure(lambda q, ef=ef: hnsw.search(q, 10, ef_search=ef).labels, queries, truth, ef)
        )
        log(f"[{name}] vf-hnsw ef={ef} {s.points[-1]}")
    series.append(s)

    for quant in ("none", "int8"):
        ivf, build_s, rss = timed_build(lambda quant=quant: _vf_ivf(base, metric, nlist, quant))
        sid = "vf-ivf" if quant == "none" else "vf-ivf-int8"
        label = "VectorForge IVF-Flat" if quant == "none" else "VectorForge IVF + int8"
        s = Series(
            sid,
            label,
            "vectorforge",
            {"nlist": nlist, "quantization": quant},
            "nprobe",
            build_s,
            ivf.memory_bytes(),
            "vectors (float32 or int8 codes) + centroids + 8 B per id",
            rss,
        )
        for nprobe in NPROBE_SWEEP:
            s.points.append(
                measure(
                    lambda q, p=nprobe, ivf=ivf: ivf.search(q, 10, nprobe=p).labels,
                    queries,
                    truth,
                    nprobe,
                )
            )
            log(f"[{name}] {sid} nprobe={nprobe} {s.points[-1]}")
        series.append(s)

    # FAISS works on L2 or inner product; cosine = inner product on unit vectors.
    fb = normalize_rows(base) if metric == "cosine" else base
    fq = normalize_rows(queries) if metric == "cosine" else queries
    fmetric = faiss.METRIC_INNER_PRODUCT if metric == "cosine" else faiss.METRIC_L2

    def faiss_hnsw() -> Any:
        idx = faiss.IndexHNSWFlat(base.shape[1], HNSW_M, fmetric)
        idx.hnsw.efConstruction = HNSW_EFC
        idx.add(fb)
        return idx

    idx, build_s, rss = timed_build(faiss_hnsw)
    s = Series(
        "faiss-hnsw",
        "FAISS IndexHNSWFlat",
        "faiss",
        {"M": HNSW_M, "ef_construction": HNSW_EFC},
        "ef_search",
        build_s,
        len(faiss.serialize_index(idx)),
        "serialized index size",
        rss,
    )
    for ef in EF_SWEEP:
        idx.hnsw.efSearch = ef
        s.points.append(measure(lambda q: idx.search(q[None, :], 10)[1][0], fq, truth, ef))
        log(f"[{name}] faiss-hnsw ef={ef} {s.points[-1]}")
    series.append(s)

    def faiss_ivf() -> Any:
        coarse = faiss.IndexFlat(base.shape[1], fmetric)
        idx = faiss.IndexIVFFlat(coarse, base.shape[1], nlist, fmetric)
        idx.train(fb)
        idx.add(fb)
        return idx

    idx, build_s, rss = timed_build(faiss_ivf)
    s = Series(
        "faiss-ivf",
        "FAISS IndexIVFFlat",
        "faiss",
        {"nlist": nlist},
        "nprobe",
        build_s,
        len(faiss.serialize_index(idx)),
        "serialized index size",
        rss,
    )
    for nprobe in NPROBE_SWEEP:
        idx.nprobe = nprobe
        s.points.append(measure(lambda q: idx.search(q[None, :], 10)[1][0], fq, truth, nprobe))
        log(f"[{name}] faiss-ivf nprobe={nprobe} {s.points[-1]}")
    series.append(s)

    return {
        "dataset": info,
        "n_base": int(base.shape[0]),
        "n_queries": int(queries.shape[0]),
        "k": 10,
        "series": [asdict(x) for x in series],
    }


def _flat(base: np.ndarray, metric: str) -> FlatIndex:
    idx = FlatIndex(base.shape[1], metric)  # type: ignore[arg-type]
    idx.add(base)
    return idx


def _vf_hnsw(base: np.ndarray, metric: str, log: Callable[[str], None]) -> HNSWIndex:
    idx = HNSWIndex(base.shape[1], metric, M=HNSW_M, ef_construction=HNSW_EFC, seed=0)  # type: ignore[arg-type]
    step = max(1, len(base) // 10)
    t = time.perf_counter()
    for start in range(0, len(base), step):
        idx.add(base[start : start + step])
        log(
            f"    hnsw build {min(start + step, len(base)):,}/{len(base):,} ({time.perf_counter() - t:.0f}s)"
        )
    return idx


def _vf_ivf(base: np.ndarray, metric: str, nlist: int, quant: str) -> IVFIndex:
    idx = IVFIndex(base.shape[1], metric, nlist=nlist, quantization=quant, seed=0)  # type: ignore[arg-type]
    idx.train(base)
    idx.add(base)
    return idx


# -- summary --------------------------------------------------------------------------------------


def headline(result: dict[str, Any]) -> dict[str, Any]:
    """The number the site's hero shows: VectorForge HNSW's fastest setting with recall@10 >= 0.95,
    against exact search on the same machine. Computed, never hand-edited."""
    by_id = {s["id"]: s for s in result["series"]}
    flat_qps = by_id["vf-flat"]["points"][0]["qps"]
    good = [p for p in by_id["vf-hnsw"]["points"] if p["recall_at_10"] >= 0.95]
    best = (
        max(good, key=lambda p: p["qps"])
        if good
        else max(by_id["vf-hnsw"]["points"], key=lambda p: p["recall_at_10"])
    )
    faiss_pts = [
        p for p in by_id["faiss-hnsw"]["points"] if p["recall_at_10"] >= best["recall_at_10"]
    ]
    faiss_qps = max(p["qps"] for p in faiss_pts) if faiss_pts else None
    return {
        "dataset": result["dataset"]["name"],
        "dataset_key": result["key"],
        "index": "hnsw",
        "ef_search": best["param"],
        "recall_at_10": best["recall_at_10"],
        "qps": best["qps"],
        "p50_ms": best["p50_ms"],
        "flat_qps": flat_qps,
        "speedup_vs_flat": round(best["qps"] / flat_qps, 2),
        "faiss_qps_at_same_recall": faiss_qps,
        "faiss_speedup": round(faiss_qps / best["qps"], 1) if faiss_qps else None,
        "n_base": result["n_base"],
    }


def dominance(result: dict[str, Any]) -> bool:
    """Phase 7 gate. Flat is exact, so its "curve" is one point at recall 1.0. HNSW dominates it
    at equal recall when an HNSW setting reaches (near-)equal recall, >= 0.99, at higher QPS.
    Settings beyond that (e.g. ef=400) buy nothing and are allowed to be slower."""
    by_id = {s["id"]: s for s in result["series"]}
    flat_qps = by_id["vf-flat"]["points"][0]["qps"]
    return any(
        p["recall_at_10"] >= 0.99 and p["qps"] > flat_qps for p in by_id["vf-hnsw"]["points"]
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--datasets", nargs="+", default=["sift", "glove"], choices=["sift", "glove"])
    ap.add_argument("--n", type=int, default=200_000, help="base vectors per dataset")
    ap.add_argument("--queries", type=int, default=1000)
    ap.add_argument("--nlist", type=int, default=512)
    ap.add_argument("--out", type=Path, default=REPO / "bench" / "results")
    args = ap.parse_args()

    import faiss  # bench-only dependency

    faiss.omp_set_num_threads(1)
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def log(msg: str) -> None:
        print(msg, flush=True)

    command = "python bench/run_bench.py " + " ".join(sys.argv[1:])
    env = {
        "hardware": hardware(),
        "versions": versions(faiss),
        "commit": git_commit(),
        "command": command.strip(),
        "started_at": started,
        "threads": "single thread: one query at a time; FAISS pinned with omp_set_num_threads(1)",
    }
    headlines = []
    for name in args.datasets:
        result = run_dataset(name, args.n, args.queries, args.nlist, faiss, log)
        result["key"] = name
        result["environment"] = env
        result["dominates_flat"] = dominance(result)
        (args.out / f"{name}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        headlines.append(headline(result))
        log(f"[{name}] written; HNSW dominates flat: {result['dominates_flat']}")
    summary = {
        "headline": headlines,
        "environment": env,
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    log(json.dumps(headlines, indent=1))


if __name__ == "__main__":
    main()
