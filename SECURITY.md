# Security checklist

Each item: verdict, evidence (command or test), and what was not verified. A PASS means the
control is implemented and the stated evidence was observed; it does not mean the system is
secure.

| Item | Verdict | Evidence |
| --- | --- | --- |
| S2 XSS | PASS | `grep -rnE "dangerouslySetInnerHTML\|innerHTML" web/app web/components web/lib` returns nothing; ESLint rule `react/no-danger: error` in `web/eslint.config.mjs`; engine strings (titles, summaries) are rendered as React text nodes only (`web/components/search-demo.tsx`). |
| S4 Uploads / payloads | PASS | Body cap 4 MiB by Content-Length and by streamed byte count (`BodySizeLimit`, tests `test_oversized_body_rejected_by_content_length`, `test_oversized_streamed_body_rejected`); batch cap 1000 (`test_batch_cap`); malformed arrays, nested metadata, NaN/Infinity/1e999 rejected with 422 (`test_upsert_rejects_malformed_input`, `test_upsert_rejects_nan_and_infinity`); WAL refuses records over 1 MiB (`test_oversized_wal_record_is_refused_before_ack`). Demo route caps query at 200 chars and k at 20. |
| S6 Rate limiting | PASS | Per-key token buckets for search (20/s, burst 40) and writes (5/s, burst 10) with 429 + `Retry-After` (`test_search_rate_limit_returns_429_with_retry_after`, `test_write_rate_limit_is_separate_bucket`); failed-auth budget per address that never blocks a valid key (`test_repeated_auth_failures_are_rate_limited`, `test_valid_key_not_locked_out_by_others_failures`); demo route bucket 1/s burst 8 per client (`web/tests/embed.test.ts`). Limits are in-memory per process (accepted, see limitations). |
| S8 API secrets | PASS | Keys read from env only (`Settings.from_env`); `repr(Settings)` hides them (`test_from_env_parses_values`); never logged (`test_logs_contain_no_keys_vectors_or_metadata`; live smoke test `grep -c <key> server.log` = 0); never in error bodies (`test_missing_and_wrong_keys_are_401`). |
| S11 CORS | PASS | Exact allowlist parsed per origin; wildcard, paths and `http://localhost.evil.com` rejected at startup (`test_rejects_weak_or_reused_keys_and_wildcard_cors`, `test_cors_origin_must_be_exact`); preflight from a non-listed origin gets no allow header (`test_security_headers_and_cors`). The production Vercel domain must be added to `VECTORFORGE_CORS_ORIGINS` at deploy (open item). |
| S12 Web storage | PASS | The site stores nothing in localStorage, sessionStorage or cookies (`grep -rn "localStorage\|sessionStorage\|document.cookie" web/app web/components web/lib` returns nothing). The browser calls only `/api/search`; the engine URL and demo key are server-only env vars without the `NEXT_PUBLIC_` prefix. |
| S13 Server-side permissions | PASS | Write endpoints, collection listing and `/metrics` require the admin key; the demo key can only read and search the demo collection (`test_demo_key_is_read_only_and_scoped`). |
| S16 SSRF | PASS | `grep -rnE "fetch\(\|urlopen\|urllib\.request\|requests\.\|httpx\.(get\|post\|Client)" engine/vectorforge web/app web/lib web/components web/proxy.ts` finds only the demo route's fetch to the fixed `VECTORFORGE_ENGINE_URL` and the client's fetch to the same-origin `/api/search`. No endpoint takes a URL from a request. |
| S17 Source maps | PASS (pending build check) | `productionBrowserSourceMaps: false` in `web/next.config.ts`; build output check recorded below. |
| S18 Default credentials | PASS | No default key anywhere; `Settings.from_env` raises `ConfigError` when `VECTORFORGE_ADMIN_KEY` is unset (`test_refuses_to_start_without_admin_key`); keys under 32 chars or a demo key equal to the admin key are refused. |
| S19 Logs | PASS | JSON logs carry method, route template, status, latency, caller role; never paths, bodies, ids, vectors, metadata or keys (`test_logs_contain_no_keys_vectors_or_metadata`). Unhandled errors log the exception type only and are caught before Starlette can print a traceback. |
| S20 Dependencies | PASS | `pip-audit --skip-editable` and `pnpm audit`: both "No known vulnerabilities found" after upgrading next 16.4.0 to 16.4.3 and black/pytest (DECISIONS D11). |

## Web security headers

Set in `web/next.config.ts` (all routes) and `web/proxy.ts` (pages, per-request nonce):
`Content-Security-Policy` with `script-src 'self' 'nonce-…' 'strict-dynamic'` and
`style-src 'self' 'nonce-…'` (no `unsafe-inline`, no `unsafe-eval` in production),
`Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`,
`Permissions-Policy`, `X-Frame-Options: DENY`. API routes get `default-src 'none'`.

## Other

- `.env.example` holds placeholders only; `.env` and `.env.*` are gitignored.
- Engine container runs as a non-root user with no build toolchain.
