@AGENTS.md

Project-specific notes for Claude Code:

- Activate the shared venv: `source ~/.venvs/vectorforge/Scripts/activate` (Windows Git Bash) or
  `source ~/.venvs/vectorforge/bin/activate` (Linux/macOS).
- Engine tests: `cd engine && pytest --cov=vectorforge`.
- Site: `cd web && pnpm dev`.
- Impeccable UI hooks are disabled for this repo (`.claude/settings.json`); see `docs/DECISIONS.md`.
