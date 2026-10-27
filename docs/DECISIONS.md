# Decisions log

Each entry: what was decided, why, and what it costs. Newest at the bottom.

## D1. Work on branch `build/v1`, not `main`

The spec says "work on main locally". The author's global rules say never work directly on
`main`/`master`. The global rule is the stricter of the two, so all work is on `build/v1`; merging
to `main` and pushing are left to the author's explicit approval.

## D2. Impeccable hooks disabled for this repo

The author's global `~/.claude/settings.json` runs Impeccable hooks on SessionStart, every
Edit/Write and Stop. The spec says these conflict with the engine phases, so
`.claude/settings.json` sets `"disableAllHooks": true` for this project only.

## D3. Dependencies (engine)

| Package | Why | Scope |
| --- | --- | --- |
| numpy | vector arithmetic (allowed by credibility rule 1) | runtime |
| fastapi, pydantic | HTTP service and validation (named by spec) | runtime |
| uvicorn | ASGI server to actually run FastAPI | runtime |
| pytest, pytest-cov, httpx | tests, coverage gate, API contract tests (spec) | dev |
| ruff, black, mypy, pre-commit | lint, format, types (spec Phase 0) | dev |
| pip-audit | dependency audit (spec S20) | dev |
| faiss-cpu | comparison baseline, imported only in `bench/` | bench |

Deliberately **not** added: `prometheus_client` (the text format is ~40 lines by hand),
`slowapi` (a token bucket is ~30 lines and easier to explain), `hypothesis` (seeded random
property tests are enough here), `psutil` (hardware info via `/proc` / `winreg`).

## D4. String ids externally, int labels internally

APIs accept string ids; collections map them to dense int labels. Dense labels let HNSW and
segments index arrays directly. Re-upsert = tombstone old label + new label, which keeps HNSW's
"no hard delete" rule intact.

## D5. One lock per collection

Search and writes on a collection are serialised by an `RLock`. With the GIL, finer locking would
add complexity for little throughput. Stated as a limitation.

## D6. vc-* and design skills

The spec lists `/vc-*` commands as the phase spine and `design-taste-frontend` as design authority.
`design-taste-frontend` is not installed on this machine. Docs were written directly against the
spec's own requirements; the visual direction is written down in `docs/DESIGN.md` from the spec's
Phase 8 brief.

## D7. Corrected test: `test_reupsert_replaces_vector_and_metadata`

The original assertion said `v3` must not appear in `hits[1:]` of a k=20 search over a
20-vector collection. That is wrong: after the re-upsert, `v3` is still a live id (with a new
vector), so a k=20 search over 20 live ids must include it. The intended property is that the
*old* vector is gone. The test now checks that `v3` is not the nearest neighbour of its old
vector and that no id appears twice. Changed in its own commit, before any engine fix.

## D8. Crash-recovery test harness corrections

Three problems in the first version of `test_crash_recovery.py`, all in the harness, none in
the property under test:

1. The writer printed `DEL i` after `ACK`, so a delete could be committed before the parent saw
   it. The parent then expected a deleted id to exist. Fix: one `ACK <last> <deleted>` line
   printed after both the upsert and the delete are durable.
2. The second writer restarted at id 0, re-upserting and re-deleting ids from the first run.
   Fix: it resumes after the last acknowledged id.
3. The writer passed HNSW parameters (`M`) to IVF. Fix: parameters per index type, with
   `nlist=4` so IVF auto-trains during the run.

Strengthened at the same time: a hard kill cannot interrupt a single in-kernel `write()`, so in
30 kills no torn tail appeared (`python bench/scripts/crash_stats.py` before the change: 30/30
clean). Half the runs now write WAL batches in 7-byte flushed chunks (fault injection in the
child process only, engine code untouched), and kills leave torn payloads that recovery must
discard (`crash_stats.py` after: 4/30 torn, 266 bytes discarded, no acknowledged write lost).

## D9. Code review after Phase 5 (built-in `/code-review`, high effort, engine/vectorforge)

Ten findings. Fixed: oversized WAL records refused before ack (`RecordTooLargeError`);
failed-auth budget only spent by failures and never blocks a valid key; CORS origins parsed and
compared exactly; upsert maps only `VectorValidationError` to 422; operations after drop raise
`CollectionClosedError` (404); HNSW degree cap enforced even when orphan repair cannot make room;
413s and preflights now pass through the observing middleware; WAL replay streams records.
Not changed: the client-IP header is trusted by design and documented as "set only behind a
proxy that overwrites it"; filtered search still scans payloads O(n) per query under the
collection lock (an inverted metadata index is out of scope; listed as a limitation).

## D10. Web dependencies

| Package | Version | Why |
| --- | --- | --- |
| next, react, react-dom | 16.4.3, 19.3.0 | App Router site (spec) |
| motion | 14.1.0 | animation layer named by the spec (`motion/react`) |
| @visx/{scale,shape,axis,grid,group} | 4.0.0 | charts; chosen over Recharts because visx renders plain SVG with no inline style attributes (compatible with a nonce CSP) and pulls in no state library |
| tailwindcss, @tailwindcss/postcss | 4.3.3 | styling (spec) |
| typescript | 5.9.3 | strict typing; 7.0 (native port) skipped as too new for Next's type-check integration |
| eslint, eslint-config-next | 9.39.1, 16.4.3 | lint; ESLint 10 is outside the peer range of eslint-config-next's plugins |

Rule followed: pin exact versions at least two weeks old, except where a security fix requires a
newer one. Web unit tests use Node's built-in `node:test` with type stripping, so there is no
test-runner dependency.

## D11. Security upgrades override the two-week rule

`pnpm audit` on next 16.4.0 reported two critical advisories (RCE in the image optimizer with
SVG; RCE in `use cache` returning typed arrays) and one high (Server Actions DoS), all fixed in
16.4.1. Upgraded to 16.4.3 (released 2026-10-23, three days before this decision). `pip-audit`
reported advisories in black 25.12.0 and pytest 8.4.2 (dev tools only, never in the image);
upgraded to black 26.10.1 and pytest 9.1.1. After the upgrades both audits report no known
vulnerabilities.

## D12. Benchmark subset and method

200,000 base vectors per dataset (the spec allows a documented subset): pure-Python HNSW
construction runs at roughly 5 ms per insert at 128 dimensions, so the full 1M base would take
over an hour per index on its own. Queries: SIFT's first 1,000 official queries; GloVe uses 1,000
held-out words (rows past the base, seed 0). Everything runs single-threaded, one query at a
time, FAISS included (`omp_set_num_threads(1)`), so latency compares like with like. The GloVe
file mirrored by Stanford NLP on Hugging Face has 400,001 rows; the last row is `<unk>` and is
excluded.

## D13. Demo embeddings without a model

The semantic demo uses SIF-weighted GloVe averages (Arora et al. 2017) rather than a neural
encoder: no PyTorch or model download, the same arithmetic runs in the Next.js route handler to
embed queries, and it reuses a benchmark dataset. Quality is word-overlap level, which the site
states.

## D14. Accepted risk: in-memory rate limits (security audit finding 2, S6)

Accepted by the author on 2026-10-26, in writing, for the current deployment shape.

- **What:** token buckets live in process memory, in the engine (`RateLimiter`) and in the demo
  route (`TokenBucket`). The audit checklist asks for a shared store.
- **Why it is acceptable now:** the engine runs as one Render free instance (it was one Fly
  machine when this was first accepted), so its per-key buckets are effectively global. The demo route is read-only, capped at 2 KiB
  bodies and `k <= 20`, and backed by the engine's own per-key limit and the demo key's tighter
  search budget, so a visitor spread across several Vercel instances gains little.
- **Residual risk:** buckets reset on restart (on Render free, after every sleep); each Vercel
  instance enforces its own demo budget.
- **Measured on production (re-audit R2, 2026-10-27):** 40 parallel `/api/search` requests
  (nominal burst 8 per client) got 32 x 200 and 8 x 429, so a burst spread over instances gets
  about four times the nominal budget. With a distinct forged `X-Forwarded-For` / `X-Real-IP` on
  each request: 35 x 200 and 5 x 429, no better than without, so forging the client address does
  not buy fresh buckets. Live searches past the engine's demo-key budget fall back to the
  snapshot. Re-accepted on these numbers.
- **Revisit when:** the engine runs more than one machine, or the demo sees abuse. Fix: a shared
  store (Redis / Vercel KV), which is a new dependency and needs approval first.

## D15. Unused code (security audit finding 8, listed only)

Not deleted, per the author's instruction. Candidates for removal:

| Symbol | Location | Note |
| --- | --- | --- |
| `HNSWIndex.search_trace` | `engine/vectorforge/index/hnsw.py:376` | was meant to export visualizer fixtures; the site builds its graph in the browser instead |
| `HNSWIndex.export_graph` | `engine/vectorforge/index/hnsw.py:492` | same |
| `FlatIndex.search_labels` | `engine/vectorforge/index/flat.py:72` | the collection's selective-filter path uses `Collection._exact` |
| `Index.is_deleted` | `engine/vectorforge/index/base.py:93` | no caller |
| `fmtRecall` | `web/lib/format.ts:9` | no caller |

## D16. Free hosting: Render (engine) and Vercel Hobby (site), demo index baked at build time

The author moved deployment to free tiers only: Render's free web service for the engine
(512 MB RAM, no persistent disk, sleeps after 15 minutes idle) and Vercel Hobby for the site.
Fly.io is no longer the target; `engine/fly.toml` is kept only as a documented alternative.

"Rebuild the index on startup from a committed seed corpus" was measured under Render's limits
with `docker run --cpus=0.1 --memory=512m`:
- rebuilding the 3,178-vector HNSW graph on boot: still not ready after 10 minutes, stopped;
- loading a checkpoint of the same index built from the same seed: ready in 37 s, 53 MB RSS.

So the rebuild happens during the image build (on Render's build machine, from
`web/data/demo/seed.json` + `docs.bin`), and every start loads that snapshot. Startup seeding
(`VECTORFORGE_SEED_DIR`) remains as the fallback when no snapshot exists. Writes to the hosted
engine are ephemeral; the README and the site's limitations section say so.

## D17. motion removed; CSS keyframes for the two entrance animations

Browser verification found that motion's opacity animations never applied under the strict nonce
CSP: search results stayed at opacity 0 (empty-looking result list) and the visualizer's
current-node ring stayed invisible, while motion's transform channel did animate. Both effects are
now plain CSS keyframes (opacity and transform only, staggered by class, no inline styles,
disabled under reduced motion), verified rendering at opacity 1. motion was then unused and was
removed from `web/package.json`. This departs from the spec's "motion/react as the animation
library layer"; the reason is a measured CSP incompatibility, and CSS covers every effect the site
uses.
