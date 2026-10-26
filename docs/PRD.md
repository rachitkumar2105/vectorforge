# VectorForge: Product Requirements

## Problem

Most "I built a vector database" portfolio projects wrap FAISS or hnswlib. They show API
plumbing, not understanding. VectorForge exists to show that the author can implement
approximate nearest neighbour (ANN) search, persistence and a query service from first
principles, and measure the result honestly against the industry baseline.

## Users

| User | Need |
| --- | --- |
| Interviewer / senior engineer | Read the HNSW code, check the benchmark is reproducible, probe the trade-offs |
| Author | Whiteboard HNSW insertion, explain WAL recovery, defend design choices |
| Site visitor | See ANN search working, interactively, with real numbers |

## Goals

1. Hand-written HNSW, IVF-Flat, flat baseline and int8 scalar quantization in Python + NumPy.
2. Durable collections: memory-mapped segments, a CRC-checked write-ahead log, atomic manifests,
   crash recovery that loses no acknowledged write.
3. A FastAPI query service with API-key auth, rate limiting, filtered search and Prometheus metrics.
4. A benchmark harness on public datasets (SIFT, GloVe-100d) against FAISS, regenerable with one
   command, reporting recall, QPS, latency percentiles, build time and memory.
5. A showcase site: interactive HNSW visualizer running real search logic in the browser, a
   benchmark explorer, a live semantic search demo with graceful fallback, an architecture
   walkthrough and an honest limitations section.

## Non-goals

Distributed sharding, a SQL layer, GPU kernels, multi-tenancy, billing. Beating FAISS on speed.

## Success criteria

- HNSW recall@10 > 0.95 at `ef_search=100` on 10k vectors; graph invariants hold after 5000 inserts.
- IVF recall is 1.0 at `nprobe == nlist`; recall rises with `nprobe`.
- Crash recovery test passes 10 runs in a row.
- Engine test coverage > 85 percent.
- Every number on the site traces to `bench/results/*.json` produced by `bench/run_bench.py`.
- Site: Lighthouse performance and accessibility >= 90 (mobile), console clean, verified at nine widths.

## Constraints

- Engine may use NumPy for arithmetic; index algorithms are written by hand.
- Python venv shared at `~/.venvs/vectorforge`; Node via pnpm; datasets in `~/datasets/`.
- Repo under 25 MB excluding `.git`.
