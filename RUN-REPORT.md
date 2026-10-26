# RUN-REPORT

Phase-by-phase log. Every claim below lists the command that produced it. Environment for local
runs: Windows 11, Python 3.12.3 in `~/.venvs/vectorforge`, 12 logical cores, 15.7 GB RAM.

## Phase 0: Foundation

### Verified
- Local run of the CI steps on the skeleton (`cd engine && ruff check vectorforge tests ../bench && black --check vectorforge tests ../bench && mypy && pytest --cov=vectorforge --cov-fail-under=85`):
  ruff "All checks passed!", black unchanged, mypy "Success: no issues found in 5 source files",
  `1 passed`, coverage 100.00%.

### Not verified / assumed
- GitHub Actions has not run: the repo has no remote yet (push needs the author's approval).
  The gate "CI green" is verified only as the same commands passing locally.

## Phase 1: Distance functions and flat index

### Verified
- `cd engine && pytest --cov=vectorforge -q`: `24 passed in 0.81s`, total coverage 91.09%.
- `test_flat_recall_against_itself_is_exactly_one`: recall@10 of flat vs its own batch ground
  truth on 2000x32 random vectors is exactly 1.0.
- `test_flat_matches_naive_python_loop_on_1000_vectors` for l2, ip and cosine.
- `ruff check`, `black --check`, `mypy` (strict): clean.

### Not verified / assumed
- Nothing assumed for this phase.

## Phase 2: HNSW

### Verified
- `cd engine && pytest --cov=vectorforge -q`: `49 passed in 117.03s`, total coverage 92.88%
  (hnsw.py 93%).
- Graph invariants on 5000 inserts (M=8, ef_construction=64): bidirectional links, degree caps
  (M_max0 = 2M on layer 0, M above), layer 0 holds every id, entry point at max level, nested
  layers, layer 0 connected from the entry point. Tests in `engine/tests/test_hnsw.py`.
- Gate numbers from `python bench/scripts/hnsw_gate.py` (10k x 24-d Gaussian, 200 queries,
  M=16, ef_construction=200, seed 3):

  | ef_search | recall@10 heuristic | recall@10 simple top-M |
  | --- | --- | --- |
  | 10 | 0.6700 | 0.6690 |
  | 50 | 0.9770 | 0.9515 |
  | 100 | **0.9970** | 0.9925 |
  | 200 | 0.9995 | 0.9985 |

  Build time: heuristic 43.0 s, simple 28.5 s (pure Python, single thread).
- Recall is monotonic in ef_search; determinism under a fixed seed; save/load gives identical
  results and identical levels for later inserts (RNG state persisted).

### Not verified / assumed
- The heuristic vs simple gap is small on isotropic Gaussian data. The paper's claim that the
  heuristic matters most on clustered data is not yet measured here; the Phase 7 benchmark on
  SIFT/GloVe is where that shows up.

## Phase 3: IVF and int8 quantization

### Verified
- `cd engine && pytest --cov=vectorforge -q`: `70 passed in 119.09s`, total coverage 93.78%.
- `test_nprobe_equal_nlist_is_exhaustive`: recall@10 = 1.0 at nprobe == nlist (8000 clustered
  vectors, nlist=32). `test_recall_rises_with_nprobe`: non-decreasing over nprobe 1..32.
- `test_quantizer_round_trip_error_within_half_step`: every element within step/2 (+1e-5).
- Gate numbers from `python bench/scripts/ivf_gate.py` (50k x 64-d, 200 Gaussian clusters,
  200 queries, nlist=128):

  | nprobe | recall@10 float32 | recall@10 int8 |
  | --- | --- | --- |
  | 1 | 0.3160 | 0.3125 |
  | 4 | 0.6110 | 0.6015 |
  | 8 | 0.8265 | 0.8075 |
  | 16 | 0.9650 | 0.9355 |
  | 32 | 0.9995 | 0.9640 |
  | 128 | 1.0000 | 0.9645 |

  Memory: vector storage 12,800,000 B float32 vs 3,200,512 B int8 (**4.00x**); whole index
  13,232,768 B vs 3,633,280 B (3.64x; centroids and label lists are not compressed).
  Max reconstruction error 0.05092, equal to the documented bound max(step/2) = 0.05092.
  **Recall cost of int8: about 3.5 points of recall@10 at full probe (1.0000 -> 0.9645).**

### Not verified / assumed
- The int8 ranges are learned from the training sample (up to 256 x nlist points). Data drifting
  outside that range is clipped; the cost of that is not measured here.

## Phase 4: Persistence, WAL and crash recovery

### Verified
- `cd engine && pytest --cov=vectorforge -q`: `126 passed in 152.36s`, total coverage 95.28%
  (wal.py 98%, segment.py 99%, collection.py 97%).
- Gate, crash recovery 10 times: `for i in $(seq 1 10); do pytest tests/test_crash_recovery.py -q; done`
  printed `10 passed` ten times (100 runs, each with two hard-kill/reopen cycles, hnsw/flat/ivf).
- Torn writes really happen under the chunked-write fault injection:
  `python ../bench/scripts/crash_stats.py` -> `30 kills: {'clean tail': 26, 'torn payload': 4};
  total torn bytes discarded 266`, with no acknowledged write lost.
- Unit tests cut the WAL at every boundary class (torn header, torn payload, CRC flip, absurd
  length) and check truncation to the last good record.
- Saved and reloaded collections return identical ids and distances
  (`test_close_and_reopen_returns_identical_results`, all three index types).

### Not verified / assumed
- Power-loss durability (fsync reaching stable storage) cannot be tested by killing a process;
  it relies on the OS honouring `fsync`. On Windows, directory fsync after rename is skipped (NTFS
  journals the rename); on Linux it is performed but only exercised in CI, not locally.
- Kill signal on this machine is `TerminateProcess` (Windows `Popen.kill()`); SIGKILL proper is
  what Linux CI would use. Both are uncatchable hard kills.

## Phase 5: Query service

### Verified
- `cd engine && pytest --cov=vectorforge -q`: `179 passed, 1 warning in 158.13s`, total coverage
  **95.17%** (gate is 85%). The warning is Starlette's deprecation notice about `httpx` in its
  TestClient, not a test problem.
- 53 API contract tests (`tests/test_service.py`) via httpx/TestClient: auth (401/403, demo key
  scope), validation (422 for malformed arrays, NaN/Infinity/1e999, bad ids, nested or oversized
  metadata, batch > 1000, k/ef/nprobe bounds), 413 by Content-Length and by streamed chunks,
  404 on unknown collections, 429 + Retry-After, Prometheus output, generic 500s, logs free of
  keys/vectors/metadata/ids, CORS allowlist, docs off in production, restart persistence.
- Live smoke test against uvicorn on port 8765 with a throwaway key: healthz, readyz, 401 without
  key, create, upsert, search all returned the expected JSON; `grep -c <key> server.log` -> `0`.

### Not verified / assumed
- GitHub push and CI run: not done; pushing needs the author's approval and a remote.
