# Security checklist

Results of the `/security-audit` run on 2026-10-26 (read-only), followed by the fixes the author
approved. Each item: verdict and the evidence observed. A PASS means the control is implemented
and the evidence was seen; it does not mean the system is secure. Items marked "production" were
also checked against the deployed hosts on 2026-10-27 (see "Production checks" below).

## S1 to S20

| Item | Verdict | Evidence |
| --- | --- | --- |
| S1 SQL injection | N/A | No database or query language; storage is files (WAL, `.npy`, JSON). Collection names are regex-validated, which also blocks path traversal (`test_create_validation`). |
| S2 XSS | PASS | `grep -rnE "dangerouslySetInnerHTML\|innerHTML" web/app web/components web/lib`: nothing. ESLint `react/no-danger: error`. A `<script>` query returned as inert data. Page CSP uses a per-request nonce, no `unsafe-inline`; 0 inline `style=` attributes in the server HTML. |
| S3 CSRF | N/A | No cookie authentication anywhere: the engine uses an `X-API-Key` header and the site sets 0 cookies (`curl -D -`). |
| S4 File uploads | N/A | No file uploads. Payload limits: engine 4 MiB by Content-Length and streamed bytes, batch 1000, NaN/Infinity rejected (tests); demo route 2 KiB before parsing (`web/tests/body-limit.test.ts`, live check: 2 MB body -> 413 with and without chunking). |
| S5 BOLA/IDOR | N/A | No user-owned objects. The demo key is confined to the demo collection and no key gets 401 (`test_demo_key_is_read_only_and_scoped`, `test_missing_and_wrong_keys_are_401`). |
| S6 Rate limiting | FAIL, accepted | Token buckets per key for search and writes, failed-auth budget per address, demo-route bucket and a separate `/api/engine-health` bucket (1/s, burst 10), all with 429 + `Retry-After`. Not a shared store: accepted in writing in `docs/DECISIONS.md` D14 for a single-machine engine. |
| S7 JWT | N/A | Not used. |
| S8 API secrets server-side | PASS | Keys from environment only, hidden from `repr` (`test_from_env_parses_values`). `grep -rlE "VECTORFORGE_DEMO_KEY\|VECTORFORGE_ENGINE_URL\|X-API-Key" web/.next/static`: 0 files. Throwaway key appeared 0 times in the container's logs. |
| S9 Password hashing | N/A | No passwords. |
| S10 MFA | N/A | No accounts. |
| S11 CORS | PASS | Origins parsed and compared exactly; `*`, paths and `http://localhost.evil.com` refused at startup (`test_cors_origin_must_be_exact`); a non-listed origin's preflight gets no allow header. Production: a preflight from `https://vectorforge-olive.vercel.app` gets `access-control-allow-origin` for that exact origin; one from `https://evil.example` gets 400 and no allow header. |
| S12 No tokens in web storage | PASS | `grep -rnE "localStorage\|sessionStorage\|document\.cookie" web/app web/components web/lib`: nothing. The browser calls only same-origin `/api/search`. |
| S13 Server-side permissions | PASS | Deny by default: every collection route requires a key; writes, listing and `/metrics` require the admin key; the demo key also has a tighter search budget (`test_demo_key_cannot_request_expensive_searches`). |
| S14 Row-level security | N/A | No database. |
| S15 Webhooks | N/A | None. |
| S16 SSRF | PASS | Server-side fetches go only to the fixed `VECTORFORGE_ENGINE_URL` (`web/lib/engine.ts`: `/readyz` for the status pill, `/collections/demo/search` for live queries); no endpoint takes a URL from a request (grep over engine and web). |
| S17 Source maps | PASS | `productionBrowserSourceMaps: false`; `find web/.next/static -name "*.map"`: 0. Production: the three chunks referenced by `/` return 200 and their `.map` URLs return 403. |
| S18 Default credentials | PASS | No default key. `docker run vectorforge-engine:local` without a key exits with `ConfigError: VECTORFORGE_ADMIN_KEY is not set; refusing to start`. Keys under 32 chars, or a demo key equal to the admin key, are refused. |
| S19 Logs | PASS (engine) | JSON logs carry route template, status, latency and role only (`test_logs_contain_no_keys_vectors_or_metadata`); unhandled errors log the exception type only. The demo route logs nothing. Hosting-platform request logs are not checked. |
| S20 Dependencies | PASS | `pip-audit --skip-editable` and `pnpm audit`: "No known vulnerabilities found" after upgrading next 16.4.0 -> 16.4.3, black and pytest (DECISIONS D11). Tests after updating: Linux container run with pytest 9.1.1, 192 passed, coverage 95.14%; web build and tests pass on next 16.4.3. |

## Audit findings and outcome

| # | Finding | Severity | Outcome |
| --- | --- | --- | --- |
| 1 | Demo route parsed unbounded JSON before validating | Medium | Fixed: `web/lib/body-limit.ts`, 2 KiB cap, 413 |
| 2 | Rate limits in process memory | Medium | Accepted in writing (DECISIONS D14) |
| 3 | Demo key could request `ef_search` 10,000 and `k` 1,000 | Low | Fixed: demo caps k 20, ef_search 256, nprobe 64 (422) |
| 4 | Demo route trusted the first `X-Forwarded-For` entry | Low | Fixed: `web/lib/client-key.ts`, trusted only on Vercel or a named header |
| 5 | No backup plan for the engine volume | Low | Fixed in config and docs: Fly scheduled snapshots, `docs/OPERATIONS.md` (not run) |
| 6 | Malformed `VECTORFORGE_MAX_BODY_BYTES` raised a bare `ValueError` | Info | Fixed: `ConfigError` naming the variable |
| 7 | Data at rest is unencrypted on the volume | Info | Open: relies on platform volume encryption |
| 8 | Unused code | Info | Listed in DECISIONS D15, not deleted |
| 9 | black 26 would reformat one test file (CI) | CI | Fixed: formatting-only commit |

## Other checks

- **Git history:** gitleaks v8.24.3 (Docker) over all commits at audit time: 25 scanned, no leaks.
  `git log --all --name-only` shows no dataset or `.env` file ever committed.
- **Exposed files** on the production build: `/.env`, `/.env.local`, `/.git/config`, `/.git/HEAD`,
  `/package.json`, `/next.config.ts`, `/data/*` all 404.
- **Security headers** (local `next start`): pages send a nonce CSP without `unsafe-inline`, HSTS,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`,
  `X-Frame-Options: DENY`, COOP; API routes send `default-src 'none'` and `no-store`. The engine
  sends HSTS, CSP, nosniff and `no-store`; its API docs return 404 in production.
- **Debug off:** Next.js production build; engine `VECTORFORGE_ENV=production` in the image.
- **Container:** runs as uid 10001; no gcc, make, pip, pytest or faiss in the image; Docker health
  check reports healthy.
- **Database exposure:** N/A; the data directory is a volume inside the engine container and is
  never served.

## Production checks (2026-10-27, `curl` from this laptop)

- Site `https://vectorforge-olive.vercel.app/`: nonce CSP, HSTS (`max-age=63072000; includeSubDomains;
  preload`), nosniff, `Referrer-Policy: strict-origin-when-cross-origin`, Permissions-Policy,
  `X-Frame-Options: DENY`, COOP `same-origin`. `/.env` and `/.git/config`: 404.
- Client bundle: `VECTORFORGE_DEMO_KEY`, `onrender.com` and `X-API-Key` appear in 0 of the
  JavaScript chunks referenced by the home page HTML (lazily loaded chunks were not fetched).
- Engine `https://vectorforge-engine.onrender.com`: `/docs` 404 (production mode), `/collections`
  without a key 401, `/healthz` sends HSTS, `default-src 'none'` CSP, nosniff and `no-store`.
- Engine down: with the Render service suspended the site served the snapshot with 0 console
  errors and 0 CSP violations (DEMO-REPORT, Production).

## Re-audit of changes since the first audit (2026-10-27)

Scope: commits after f9bc438 (seed loader, Dockerfile and `render.yaml`, the engine-health
route, the search route's `mode`, the engine status monitor) and the deployed hosts.

| # | Finding | Severity | Outcome |
| --- | --- | --- | --- |
| R1 | Production engine CORS allowlist also allowed `http://localhost:3000` | Low | Fixed: Render value set to the production origin only; docs no longer suggest localhost for production |
| R2 | Demo rate limits are per Vercel instance (measured: 32 of 40 parallel requests allowed, burst 8) | Low | Accepted again with the measurement (DECISIONS D14); forged client-IP headers measured to give no advantage |
| R3 | `/api/engine-health` made one engine request per call | Low | Fixed: one shared ping per instance per second (`web/lib/coalesce.ts`, `web/tests/coalesce.test.ts`) |
| R4 | Engine base image not pinned | Info | Fixed: `python:3.12-slim@sha256:5b8b1421...` in `engine/Dockerfile` |
| R5 | `render.yaml` auto-deploys every push to `main`, and `main` has no branch protection (GitHub API `protected: false`) | Info | Listed only: branch protection requiring CI is a repository setting for the author |
| R6 | Behind Render's proxy all failed-auth attempts share one budget (`VECTORFORGE_CLIENT_IP_HEADER` unset) | Info | Listed only: tested, 9 bad keys then 429 while the site's valid demo key kept working; slows key guessing globally and cannot lock out a valid key |

Commands: gitleaks v8.24.3 over 66 commits, no leaks; `pip-audit --skip-editable` and
`pnpm audit --prod`, no known vulnerabilities; production probes with `curl` (CORS preflights,
parallel rate-limit bursts, bad-key bursts, 401/404/405 checks, headers); the 8 JavaScript
chunks referenced by the home page (588 KB) hold 0 occurrences of the key names, the engine
host or `sourceMappingURL`.

## Remaining risks

- Rate limits reset on restart and are per instance (accepted, D14).
- `VECTORFORGE_CLIENT_IP_HEADER` and `DEMO_TRUSTED_IP_HEADER` must only be set behind a proxy that
  overwrites the named header.
- Selective metadata filters scan every vector under the collection lock.
- Data at rest is not encrypted by the application.
- Two static keys, no rotation API.
- Only the checks listed under "Production checks" ran against the deployed hosts; Vercel's and
  Render's own request logs were not reviewed.
