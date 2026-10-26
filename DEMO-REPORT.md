# DEMO-REPORT: showcase site, verified in a real browser

All checks ran against the **production build** (`pnpm build && pnpm start`, Next.js 16.4.3) on
`http://localhost:3000`, driven by `playwright-cli` 0.1.22 (Chrome). The scripts live in
`web/scripts/qa/` and the raw outputs and screenshots in `docs/demo/`. Rerun any check with:

```bash
bash web/scripts/qa/restart.sh                               # build + start on :3000
playwright-cli open http://localhost:3000
playwright-cli --raw run-code --filename=web/scripts/qa/widths.js
```

Nothing is deployed, so none of this is verified on Vercel or Fly.

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

## Not verified / assumed

- **Lighthouse after the security-audit fixes.** A rerun on the final build was attempted while
  unrelated containers on this machine (`kafkabench-kafka1..3`, `quirky_wilson`) held the CPU at
  97 percent; it scored 79 / 69 / 65 with blocking time climbing per run. Those runs measure the
  machine, not the page, and were not kept. The audit fixes touched only the demo route and the
  result-list animation, which load after first paint, so no change is expected, but this is not
  re-measured. Rerun the five-run command on an idle machine.
- **60 fps.** Not profiled with a frame-timing trace; the visualizer and hero graph were checked
  visually and by Lighthouse main-thread metrics only.
- **Real devices and other browsers.** Only Chrome via Playwright, with emulated viewports;
  no Safari or Firefox, no physical phone.
- **Deployed site.** No Vercel deployment, custom domain or HTTPS check exists yet.
