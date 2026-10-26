"""Phase 2 gate numbers: recall@10 of HNSW vs flat on 10k random vectors (same setup as tests)."""

import time

import numpy as np

from vectorforge.index.flat import FlatIndex
from vectorforge.index.hnsw import HNSWIndex
from vectorforge.metrics import recall_at_k


def main() -> None:
    base = np.random.default_rng(5).standard_normal((10_000, 24)).astype(np.float32)
    queries = np.random.default_rng(6).standard_normal((200, 24)).astype(np.float32)
    for heuristic in (True, False):
        index = HNSWIndex(dim=24, seed=3, heuristic=heuristic)
        t0 = time.perf_counter()
        index.add(base)
        build = time.perf_counter() - t0
        flat = FlatIndex(dim=24)
        flat.add(base)
        truth = flat.search_batch(queries, k=10)
        name = "heuristic" if heuristic else "simple"
        print(
            f"{name}: build {build:.1f}s, edges {index.edge_count()}, max_level {index.max_level}"
        )
        for ef in (10, 50, 100, 200):
            found = np.stack([index.search(q, k=10, ef_search=ef).labels for q in queries])
            print(f"  ef_search={ef:<4} recall@10={recall_at_k(found, truth, 10):.4f}")


if __name__ == "__main__":
    main()
