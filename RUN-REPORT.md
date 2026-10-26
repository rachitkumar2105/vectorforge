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
