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
