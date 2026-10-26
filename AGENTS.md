# AGENTS.md

Rules for any coding agent (or human) working in this repository.

## Non-negotiable

1. **No secrets in code or logs.** API keys come from environment variables only. Never print,
   log, echo or commit a key. `.env` is gitignored; `.env.example` holds placeholders only.
2. **No new dependency without a record.** Any package added to `engine/pyproject.toml` or
   `web/package.json` gets an entry in `docs/DECISIONS.md` saying what it is for and why the
   standard library or an existing dependency was not enough.
3. **Tests are never edited to make them pass.** If a test is wrong, say why in the commit
   message and in `docs/DECISIONS.md`, then change it in a separate commit from the fix.
4. **pytest output is required before a phase is called done.** Paste the real output (command
   and summary line) into `RUN-REPORT.md`. No "should pass".
5. **Never fabricate numbers.** Every benchmark, coverage or size figure comes from a command
   that was actually run, and the command is recorded next to the number.
6. **The engine never imports faiss, hnswlib, annoy, scann or nmslib.** FAISS lives only in
   `bench/` as the comparison baseline. CI greps for this.

## Environment

- Python: one shared venv outside the repo at `~/.venvs/vectorforge`. Do not create `.venv/`.
- Node: `pnpm` only. Do not run `npm install` in `web/`.
- Datasets: `~/datasets/`. Never inside the repo.

## Workflow

- Tests first for logic, then implementation, then the phase gate, then `RUN-REPORT.md`.
- One commit per concern. Run `ruff`, `black --check` and `mypy` on `engine/vectorforge`
  before committing (pre-commit does this).
- Comments explain *why*, not *what*. The HNSW code in particular must be whiteboard-explainable.
- Reports separate `## Verified` from `## Not verified / assumed`.
