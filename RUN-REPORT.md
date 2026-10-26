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
