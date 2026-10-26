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
