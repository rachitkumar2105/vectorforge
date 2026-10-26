# FINAL-AUDIT

State of VectorForge on branch `build/v1`, 2026-10-26. Every number below comes from a command
recorded next to it or in the linked report. Nothing has been pushed or deployed: both need the
author's approval and accounts. This audit does not claim the system is secure.

## Phase gates

| Phase | Gate | Status | Evidence |
| --- | --- | --- | --- |
| 0 Foundation | CI green on an empty-but-valid repo | Passed | GitHub Actions green on `main` (run #4); see Coverage below. |
| 1 Distance + flat | flat recall 1.0 vs itself; tests pass | Passed | `test_flat_recall_against_itself_is_exactly_one`; flat matches published SIFT ground truth exactly on 20 queries. |
| 2 HNSW | invariants hold; recall@10 > 0.95 at ef_search=100 on 10k | Passed | `python bench/scripts/hnsw_gate.py`: **0.9970**; invariants tested on 5,000 inserts. |
| 3 IVF + int8 | recall rises with nprobe; 1.0 at nprobe == nlist; memory measured | Passed | `python bench/scripts/ivf_gate.py`: recall 1.0 at full probe; int8 storage **4.00x** smaller, recall@10 0.9645 at full probe. |
| 4 Persistence | crash recovery passes repeatedly (10 times) | Passed | crash module run 10 times: `10 passed` each time (100 hard-kill/reopen runs); 4/30 kills left torn WAL tails, all recovered. Also passes under Linux SIGKILL in the container run. |
| 5 Query service | coverage > 85% on engine; CI green; push | Passed | `pytest --cov=vectorforge`: **199 passed, 95.19%**, locally and in GitHub Actions; pushed to github.com/rachitkumar2105/vectorforge. |
| 6 Security | `/security-audit` run and report committed; FAILs fixed or accepted | Passed | `SECURITY.md`; findings 1, 3, 4, 5, 6, 9 fixed in separate commits; S6 accepted in writing (DECISIONS D14). |
| 7 Benchmark | results from a real run; HNSW dominates flat at equal recall | Passed | `python bench/run_bench.py` (log `bench/results/run.log`); `dominates_flat: true` on both datasets. |
| 8 Site | nine widths, reduced motion, Tab walk, console clean, Lighthouse >= 90 mobile | Passed with one re-measurement pending | `DEMO-REPORT.md`. Lighthouse 93 to 97 performance, 100 accessibility over five runs on the pre-audit-fix build; the post-fix rerun was invalidated by unrelated CPU load and is pending. |
| 9 Deploy | production URL, demo end to end, site survives engine stopped | **Pending your account steps** | Target changed to free tiers (DECISIONS D16): engine on Render free (`render.yaml`, image pre-builds the demo index from the committed seed; ready in 37 s at 0.1 CPU / 512 MB), site on Vercel Hobby. Rehearsed locally: live search, sleeping engine (paused container), engine down (stopped container) all verified (`DEMO-REPORT.md`). Steps and env vars: `docs/DEPLOY.md`. |
| 10 Final audit | this file and `docs/INTERVIEW.md` | Done | this file; `docs/INTERVIEW.md` (20 questions). |

## Security checklist (full table and evidence in `SECURITY.md`)

| Item | Verdict | | Item | Verdict |
| --- | --- | --- | --- | --- |
| S1 SQL injection | N/A (no database) | | S11 CORS | PASS |
| S2 XSS | PASS | | S12 No tokens in web storage | PASS |
| S3 CSRF | N/A (no cookie auth) | | S13 Server-side permissions | PASS |
| S4 Uploads | N/A (no files); payload caps PASS | | S14 Row-level security | N/A |
| S5 BOLA/IDOR | N/A (no user objects) | | S15 Webhooks | N/A |
| S6 Rate limiting | FAIL, accepted in writing (D14) | | S16 SSRF | PASS |
| S7 JWT | N/A | | S17 Source maps | PASS (local build) |
| S8 Secrets server-side | PASS | | S18 Default credentials | PASS |
| S9 Passwords | N/A | | S19 Logs | PASS (engine) |
| S10 MFA | N/A | | S20 Dependencies | PASS |

gitleaks v8.24.3 over the full history: 39 commits, no leaks. `pip-audit` and `pnpm audit`: no
known vulnerabilities.

## Coverage

- CI: GitHub Actions run #4 on `main` at afb4fc9 (https://github.com/rachitkumar2105/vectorforge/actions/runs/40304566096): **success**. engine 3m39s (ANN import guard, ruff, black, mypy, pytest `199 passed`, coverage 95.19%, pip-audit); web 35s (lint, typecheck, `node --test` 20 tests, build, `pnpm audit --prod`); secrets 16s (gitleaks, full history). Runs #1 and #2 failed on an invalid workflow expression (`hashFiles` in a job-level `if`), fixed in afb4fc9.

- Engine: `cd engine && pytest --cov=vectorforge` -> **199 passed, total coverage 95.19%** (gate 85%).
  Same suite in a `python:3.12-slim` Linux container: 192 passed, 95.14% (before the 7 audit
  regression tests were added).
- Web: `pnpm test` (node:test) -> **20 passed** (browser HNSW invariants and recall, embedding
  parity with Python, rate limiter, body limit, client key). No coverage tool on the web side.

## Benchmark (single thread, one query at a time, 200,000 base vectors, 1,000 queries)

Fastest setting of each index with recall@10 >= 0.95, from `bench/results/*.json`.

**SIFT1M subset** (L2, 128-d), i7-1255U, Python 3.12.3, NumPy 2.5.4, FAISS 1.15.1:

| Index | Setting | Recall@10 | q/s | p50 ms | Build | Memory |
| --- | --- | --- | --- | --- | --- | --- |
| VectorForge flat (exact) | exact | 1.0000 | 22.8 | 43.364 | 0.07 s | 102.4 MB |
| VectorForge HNSW | ef_search=40 | 0.9540 | 976.4 | 0.929 | 1091.6 s | 179.7 MB |
| VectorForge IVF-Flat | nprobe=32 | 0.9876 | 148.8 | 6.557 | 57.6 s | 104.3 MB |
| VectorForge IVF + int8 | nprobe=32 | 0.9766 | 85.2 | 11.097 | 57.8 s | 27.5 MB |
| FAISS IndexHNSWFlat | ef_search=40 | 0.9595 | 9307.2 | 0.105 | 80.7 s | 131.3 MB |
| FAISS IndexIVFFlat | nprobe=32 | 0.9861 | 2014.9 | 0.477 | 2.5 s | 104.3 MB |

**GloVe-100d subset** (cosine):

| Index | Setting | Recall@10 | q/s | p50 ms | Build | Memory |
| --- | --- | --- | --- | --- | --- | --- |
| VectorForge flat (exact) | exact | 1.0000 | 27.9 | 35.218 | 0.08 s | 80.0 MB |
| VectorForge HNSW | ef_search=120 | 0.9590 | 167.1 | 5.711 | 2319.4 s | 162.8 MB |
| VectorForge IVF-Flat | nprobe=64 | 0.9816 | 48.5 | 19.751 | 95.1 s | 81.8 MB |
| VectorForge IVF + int8 | nprobe=64 | 0.9690 | 42.3 | 22.484 | 66.4 s | 21.8 MB |
| FAISS IndexHNSWFlat | ef_search=120 | 0.9699 | 2103.6 | 0.425 | 113.6 s | 108.9 MB |
| FAISS IndexIVFFlat | nprobe=32 | 0.9610 | 1641.1 | 0.521 | 2.2 s | 81.8 MB |

At matched recall FAISS HNSW is **9.5x** faster on SIFT and **12.6x** on GloVe
(`bench/results/summary.json`). VectorForge HNSW beats exact search by 42.8x (SIFT) and 6.0x
(GloVe) at recall@10 >= 0.95. Memory: VectorForge HNSW is measured with `sys.getsizeof` over its
Python structures; FAISS is its serialized index size. Regenerate everything with
`python bench/datasets/download.py all && python bench/run_bench.py` (about 70 minutes here).

## Repository size

`git ls-files` content: **170 files, 7.83 MB**; packed history 5.38 MiB (`git count-objects -vH`).
The largest tracked file is the demo vocabulary (`web/data/demo/vocab.bin`, 2.9 MB). The working
tree also holds gitignored, regenerable directories (`web/node_modules`, `web/.next`,
`engine/.mypy_cache` at 22 MB), so a literal `du -sh --exclude=.git .` exceeds 25 MB; the
repository content does not. No dataset, index or `.env` file has ever been committed.

## Verified (command or test)

- Engine gate: `ruff check`, `black --check`, `mypy` (strict), `pytest --cov` -> 199 passed, 95.19%.
- Linux: same gate inside `python:3.12-slim` -> 192 passed, 95.14%, crash test under SIGKILL.
- Benchmark: `python bench/run_bench.py`, log committed.
- Engine image: `docker build` (89.4 MB); refuses to start without a key; runs as uid 10001; no
  compiler, pip, pytest or faiss inside; health check healthy; key absent from logs.
- Site: `pnpm lint`, `pnpm typecheck`, `pnpm test` (20), `pnpm build`; browser checks in
  `DEMO-REPORT.md`; local end-to-end demo with the engine up and down.
- Security: `SECURITY.md` (gitleaks, audits, greps, header checks, tests).

## Not verified or assumed

- **Deployment (Phase 9):** no Fly/Railway app, no Vercel project, no custom domain, no uptime
  check, no preview deployments, no HTTPS check, no `fly volumes` snapshot or restore drill.
- **Lighthouse on the final build:** pending a rerun on an idle machine (see DEMO-REPORT).
- **60 fps:** not profiled with a frame trace.
- **Other browsers and real phones:** Chrome via Playwright only.
- **Power-loss durability:** relies on the OS honouring fsync; a process kill cannot test it.
- **Platform header behaviour:** that Vercel overwrites `x-real-ip` / `x-forwarded-for`.
- **Legal pages:** drafts, labelled as such; not reviewed by a lawyer.
- **`/vc-*` and design skills from the spec:** most were not loaded (DECISIONS D6); the built-in
  code review and `/security-audit` were run; `design-taste-frontend` is not installed here.

## Known limitations

Stated on the site's limitations section and in `docs/INTERVIEW.md`: slower than FAISS by the
measured factors above; single machine, no replication; one lock per collection; indexes must fit
in RAM; tombstones are never compacted; selective filters scan payloads in Python; IVF trains once;
benchmark is a 200k subset on one core; demo embeddings are bag-of-words GloVe; two static keys
are the whole auth model; rate limits are per process (accepted, D14); data at rest is not
encrypted by the application.

## Open items before calling it launched

1. Done: repository created, `build/v1` merged into `main`, pushed, CI green (run #4).
2. Deploy the engine (Fly config in `engine/fly.toml`), set `VECTORFORGE_ADMIN_KEY` and
   `VECTORFORGE_DEMO_KEY` as platform secrets, seed the demo with `bench/demo/seed_engine.py`.
3. Deploy the site to Vercel with `VECTORFORGE_ENGINE_URL` and `VECTORFORGE_DEMO_KEY` as
   server-side variables; add the production origin to `VECTORFORGE_CORS_ORIGINS`.
4. Connect a custom domain and set `NEXT_PUBLIC_SITE_URL` and `NEXT_PUBLIC_REPO_URL`.
5. Add an uptime check on `/healthz`; run the restore drill in `docs/OPERATIONS.md`.
6. Rerun Lighthouse (five runs) and the QA scripts against the production URL.
7. Have the privacy and terms drafts reviewed (Claude cannot give legal sign-off).
