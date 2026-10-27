# DEMO-REPORT: showcase site, verified in a real browser

All checks ran against the **production build** (`pnpm build && pnpm start`, Next.js 16.4.3) on
`http://localhost:3000`, driven by `playwright-cli` 0.1.22 (Chrome). The scripts live in
`web/scripts/qa/` and the raw outputs and screenshots in `docs/demo/`. Rerun any check with:

```bash
bash web/scripts/qa/restart.sh                               # build + start on :3000
playwright-cli open http://localhost:3000
playwright-cli --raw run-code --filename=web/scripts/qa/widths.js
```

The same checks were then repeated on the deployed site, once with the engine up and once with
the Render service suspended: see **Production** below. The `prod/` copies of the scripts differ
only in the base URL.

## Verified

### Nine widths (`widths.js`, output `docs/demo/qa-widths.json`)

| Width | Horizontal overflow | Content column | Screenshots |
| --- | --- | --- | --- |
| 375 | none | 375 | `w375-hero.jpg`, `w375-visualizer.jpg` |
| 414 | none | 414 | `w414-hero.jpg`, `w414-visualizer.jpg` |
| 768 | none | 768 | `w768-hero.jpg`, `w768-visualizer.jpg` |
| 1024 | none | 1024 | `w1024-hero.jpg`, `w1024-visualizer.jpg` |
| 1280 | none | 1280 | `w1280-hero.jpg`, `w1280-visualizer.jpg` |
| 1440 | none | 1360 (max) | `w1440-*.jpg` (hero, visualizer, benchmarks, demo, architecture, limits) |
| 1920 | none | 1360 (max) | `w1920-hero.jpg`, `w1920-visualizer.jpg` |
| 2560 | none | 1360 (max) | `w2560-hero.jpg`, `w2560-visualizer.jpg` |
| 3440 | none | 1360 (max) | `w3440-hero.jpg`, `w3440-visualizer.jpg` |

`scrollWidth == clientWidth` at every width. Above 1440 the content column stays at 1360 px and
only the hero graph runs full-bleed. Phone-width section shots: `w375-{benchmarks,demo,architecture,limits}.jpg`.
The first pass found an overflow at 768 px (780 > 768, the nav links); fixed by switching
to the menu below 1024 px, then re-verified.

### Reduced motion (`reduced-motion.js`, output `qa-reduced-motion.json`, `reduced-motion-visualizer.jpg`)

With `prefers-reduced-motion: reduce` emulated:
- hero graph `animation-duration` computes to `1e-05s` (decorative motion off);
- the visualizer shows no Play button, shows the note "playback is manual: use Step", and offers
  Step / Jump / Reset / Random;
- two Step presses moved the readout from `layer 3, 0 expansions, 1 distance` to
  `layer 2, 1 expansion, 3 distances` (manual step-through works).

### Keyboard (`tab-walk.js`, output `qa-tab-walk.json`)

A full Tab walk reaches **30 stops** in order: skip link, nav (6), Source, hero buttons (2),
visualizer stage, ef slider and its 3 enabled buttons, dataset toggles (2), chart, data-table
disclosure, search input and button, 6 example queries, footer (3). **Every stop draws a visible
focus outline** (`withoutOutline: []`). Arrow keys move the visualizer query and walk chart points.
After lazy loading was added, the walk briefly dropped to 18 stops (sections not yet mounted were
unreachable by keyboard); fixed by mounting sections at idle time, then re-verified at 30.

### Console and CSP

- `console.js`: load, click the visualizer, set ef, switch dataset, run a demo query, scroll the
  architecture, open /privacy: **0 errors, 0 warnings, 0 CSP violations**.
- `demo-twice.js`: two searches in a row. This found **16 CSP violations** from motion's
  `AnimatePresence mode="popLayout"`, which injects a `<style>` element the nonce CSP blocks.
  Fixed (keyed list with `mode="wait"`), re-run: **0 errors, 0 violations**.
- `interaction-sweep.js`: every control used twice at 1440 and 375 (visualizer clicks, random
  query, ef slider, reset, step, play, arrow keys; dataset toggles, series select, chart hover and
  keys, data table open/close; three demo queries plus an unknown-word query; architecture scroll;
  mid-session resize; privacy and back): **0 errors and 0 CSP violations at both widths**.
- `scroll-reveal.js`: scrolling the whole page leaves **0 of 15** reveal elements hidden.

### Lighthouse, mobile emulation (`docs/demo/lighthouse/summary.json`)

`pnpm dlx lighthouse@12.8.2 http://localhost:3000/ --form-factor=mobile`, five consecutive runs
on the build at commit 2ddf88e (full report of run 1 kept in `home-mobile-run1.json`):

| Run | Performance | Accessibility | Best practices | SEO | LCP | TBT | CLS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 95 | 100 | 100 | 100 | 2.6 s | 180 ms | 0 |
| 2 | 97 | 100 | 100 | 100 | 2.5 s | 90 ms | 0 |
| 3 | 93 | 100 | 100 | 100 | 2.6 s | 230 ms | 0 |
| 4 | 96 | 100 | 100 | 100 | 2.5 s | 130 ms | 0 |
| 5 | 97 | 100 | 100 | 100 | 2.5 s | 110 ms | 0 |

The first measurement scored performance 77 (TBT 740 ms: every section hydrated at load) and
accessibility 97 (an icon link without a name). Code-splitting the interactive sections, mounting
them near the viewport or one per idle period, thinning the hero graph, and naming the link got
it to the numbers above.

### Demo, end to end against a real engine (local)

Engine container (`vectorforge-engine:local`, throwaway keys, never printed) seeded with
`bench/demo/seed_engine.py` (3,178 documents, all batches 200). The site, started with the
server-only `VECTORFORGE_ENGINE_URL` and `VECTORFORGE_DEMO_KEY`, answered "read a file line by
line" as **"Live engine · 9.73 ms HNSW search on the server · 40.1 ms round trip"**
(`demo-live-engine.jpg`). With the engine container stopped, the same page answered
**"Engine unreachable. Served from the static snapshot: exact search over the same 3,178
embeddings inside the site's route handler"** with no console error (`demo-engine-down.jpg`).
After restarting the container the collection still held 3,178 vectors (recovered from disk),
and the admin key appeared 0 times in the engine's logs.

### Server output

- 0 inline `style=` attributes in the server HTML; CSP, HSTS, nosniff, Referrer-Policy,
  Permissions-Policy, X-Frame-Options and COOP on every page (see SECURITY.md).
- `/privacy` and `/terms` render with a "Draft, not legal advice" notice; favicon `app/icon.svg`.

### Engine status pill (live search section only): scripts in `web/scripts/qa/pill/`, results in `docs/demo/pill/`

Run with `bash web/scripts/qa/run-all.sh` against the production build wired to a local engine
container (`engine/Dockerfile`); a paused container stands in for a sleeping Render instance and a
stopped one for an unavailable engine.

| Check | Result |
| --- | --- |
| Warm engine (`warm.js`) | checking at 15 ms, engine live at 329 ms, never "waking"; pill faded to opacity 0 after the 2 s hold; section layout did not move |
| Sleeping engine (`waking.js`) | checking, then waking at 2.3 s; counter ticking ("· 4s", "· 5s"); dot `engine-pulse 1.6s cubic-bezier(0.45, 0, 0.25, 1)`; input enabled; query answered from the snapshot and labelled; engine live at 24 s with the input ("compress data") and all 8 results kept; next query labelled live engine; no layout shift |
| Reduced motion (`reduced.js`) | waking dot `animation-name: none`, `transform: none`; text still "waking engine, about 45s" |
| Hidden tab (`hidden.js`) | 0 health pings during 20 s hidden, counter frozen at 11 s; 1 ping within 1.5 s of becoming visible |
| Engine down (`down.js`, fake clock) | checking, waking, then "engine asleep, showing saved results" (persists); polling stopped at 12 pings (no more after another simulated minute); search returned 8 results labelled "Saved snapshot results" |
| Reserved width (`fit.js`) | all four state texts fit at all nine widths; pill box 343 px at 375, 382 px at 414, 360 px from 768 up; box never resized |
| Engine down, whole page | console clean, 0 CSP violations, interaction sweep 0 errors at 375 and 1440; nine widths without overflow (screenshots taken with the engine stopped) |
| Lighthouse, engine down (`lighthouse/summary-engine-down.json`) | performance 93 and 92, accessibility/best practices/SEO 100, FCP 0.9 to 1.0 s, CLS 0 (one run hit a Lighthouse trace error); CPU was 30 to 50 percent busy with unrelated work |

Bugs these runs found and fixed: result list stuck empty after the engine-state change (exit
animation never completing), result items and the visualizer ring stuck at opacity 0 (motion's
opacity animations under the nonce CSP; replaced with CSS keyframes, motion removed), pill text
truncated at 1440, grey block flashing behind unrevealed limitation items.

### Production: https://vectorforge-olive.vercel.app with the engine on https://vectorforge-engine.onrender.com

Scripts in `web/scripts/qa/prod/`, results in `docs/demo/prod/` (engine up) and
`docs/demo/prod/suspended/` (engine suspended), driven by `playwright-cli` against the live URL.

Engine up (2026-10-26):

| Check | Result |
| --- | --- |
| Pill, warm engine (`pill-warm.json`) | checking at 12 ms, engine live at 780 ms, faded to opacity 0, section did not move |
| Pill fit (`pill-fit.json`) | 343 px at 375, 382 px at 414, 360 px from 768 up, box never moved, no overflow |
| Live search (`console.json`) | "Live engine results · 1.80 ms HNSW search on the server · 638.6 ms round trip" |
| Console and CSP (`console.json`, `demo-twice.json`) | 0 messages, 0 CSP violations |
| Interaction sweep (`interaction-sweep.json`) | 0 errors, 0 CSP at 375 and 1440 |
| Tab walk (`tab-walk.json`) | 30 stops, every one with a visible outline |
| Scroll reveals (`scroll-reveal.json`) | 18 reveals, 0 left hidden |
| Reduced motion (`reduced-motion.json`) | hero animation 1e-05s, no Play button, manual Step works |
| Nine widths (`widths.json`, `w*-*.jpg`) | no horizontal overflow at any width |
| Headers (`curl -sI`) | nonce CSP, HSTS with preload, nosniff, Referrer-Policy, Permissions-Policy, X-Frame-Options DENY, COOP |

Lighthouse mobile, `pnpm dlx lighthouse@12.8.2 https://vectorforge-olive.vercel.app/
--form-factor=mobile` five times (`lighthouse-summary.json`), laptop CPU 30 to 45 percent busy
with unrelated work:

| Run | Performance | Accessibility | Best practices | SEO | LCP | TBT | CLS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 88 | 100 | 100 | 100 | 2.4 s | 400 ms | 0 |
| 2 | 88 | 100 | 100 | 100 | 2.4 s | 350 ms | 0 |
| 3 | 96 | 100 | 100 | 100 | 2.3 s | 170 ms | 0 |
| 4 | 94 | 100 | 100 | 100 | 2.2 s | 230 ms | 0 |
| 5 | 96 | 100 | 100 | 100 | 2.2 s | 190 ms | 0 |

Median performance 94. The two 88s have the highest blocking time and ran first, while the other
work was busiest; this is the measured spread, not a cleaned-up number.

Engine suspended (2026-10-27): service suspended from the Render dashboard; engine `/healthz`
returned 503 and `/api/engine-health` returned `{"engine":"down"}` before the runs.

| Check | Result |
| --- | --- |
| Pill (`suspended-pill-down.json`, `unavailable.jpg`) | checking, waking, then "engine asleep, showing saved results" with dot state `unavailable`; 7 health pings, still 7 after another minute (polling stopped) |
| Search | 8 results labelled "Saved snapshot results · exact search over the same 3,178 embeddings in the site's route handler, not the live engine" |
| Console and CSP (`suspended-console.json`) | 0 messages, 0 CSP violations |
| Interaction sweep (`suspended-interaction-sweep.json`) | 0 errors, 0 CSP at 375 and 1440 |
| Nine widths (`suspended-widths.json`, `w*-*.jpg`) | no horizontal overflow; hero, visualizer, benchmarks and architecture render with the engine off |
| Sections (`suspended-sections.json`) | benchmarks, demo, architecture and limits captured at 1440 and 375, overflow 0 |

The service was then resumed from the dashboard: `/healthz` 200 on the second poll (under 30 s
after the click), `/readyz` `{"status":"ready"}`, `/api/engine-health` `{"engine":"live"}`, and a
POST to `/api/search` came back with `"source":"engine"`.

Natural cold start (2026-10-27, `web/scripts/qa/prod/cold-start.js`, `docs/demo/prod/cold/`):
no request reached the engine from 00:34 to 00:53 UTC, past Render's 15-minute idle limit, then
the script opened the site:

| Check | Result |
| --- | --- |
| Pill sequence | checking at 11 ms, "waking engine, about 45s" at 2.6 s, "engine live" at 24.5 s (warm engine: live at 780 ms) |
| First search while waking | answered from the labelled snapshot |
| Next search after live | answered by the engine |

The 24.5 s wake is one measurement; Render's own figure is "about a minute", which the pill's
90 s budget covers.

## Not verified / assumed

- **Lighthouse on an idle machine.** The production runs above (median 94, two runs at 88) and
  the engine-down local runs (93, 92) all ran with unrelated work on the CPU. An earlier local
  attempt at 97 percent CPU (79 / 69 / 65) was discarded. A hosted run was attempted on
  2026-10-27: the PageSpeed Insights API answered "Quota exceeded" (no API key) and
  pagespeed.web.dev stayed on "Running analysis". No run on an idle machine or from a hosted
  Lighthouse service exists for the final build.
- **60 fps.** Not profiled with a frame-timing trace; the visualizer and hero graph were checked
  visually and by Lighthouse main-thread metrics only.
- **Real devices and other browsers.** Only Chrome via Playwright, with emulated viewports;
  no Safari or Firefox, no physical phone.
- **Cold-start spread.** One natural wake was timed (24.5 s); the variance across wakes is not
  measured.
- **Custom domain.** The site runs on the `vercel.app` subdomain only.
