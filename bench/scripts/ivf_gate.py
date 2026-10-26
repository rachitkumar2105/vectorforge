"""Phase 3 gate numbers: IVF recall vs nprobe, float32 vs int8, and the memory saving."""

import numpy as np

from vectorforge.core.quantize import ScalarQuantizer
from vectorforge.index.flat import FlatIndex
from vectorforge.index.ivf import IVFIndex
from vectorforge.metrics import recall_at_k


def clustered(n: int, dim: int, centers: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    means = rng.standard_normal((centers, dim)) * 3
    return (means[rng.integers(0, centers, n)] + rng.standard_normal((n, dim))).astype(np.float32)


def main() -> None:
    base = clustered(50_000, 64, centers=200, seed=1)
    queries = clustered(200, 64, centers=200, seed=2)
    flat = FlatIndex(dim=64)
    flat.add(base)
    truth = flat.search_batch(queries, k=10)
    indexes = {q: IVFIndex(dim=64, nlist=128, quantization=q, seed=0) for q in ("none", "int8")}
    for idx in indexes.values():
        idx.add(base)
    print("nprobe  recall@10 float32  recall@10 int8")
    for nprobe in (1, 2, 4, 8, 16, 32, 64, 128):
        row = []
        for idx in indexes.values():
            found = np.stack([idx.search(q, k=10, nprobe=nprobe).labels for q in queries])
            row.append(recall_at_k(found, truth, 10))
        print(f"{nprobe:<7} {row[0]:<18.4f} {row[1]:.4f}")
    f32, i8 = indexes["none"].memory_bytes(), indexes["int8"].memory_bytes()
    print(f"index memory: float32 {f32} B, int8 {i8} B, ratio {f32 / i8:.2f}x")
    sq = ScalarQuantizer.fit(base)
    raw = base.nbytes
    codes = sq.encode(base).nbytes + sq.nbytes()
    print(f"vector storage only: float32 {raw} B, int8 {codes} B, ratio {raw / codes:.2f}x")
    err = np.abs(sq.decode(sq.encode(base)) - base)
    bound = sq.max_abs_error().max()
    print(f"max abs reconstruction error {err.max():.5f}, bound max(step/2) {bound:.5f}")


if __name__ == "__main__":
    main()
