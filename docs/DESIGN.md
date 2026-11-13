# VectorForge site: design direction

## Concept: the observatory console

The page is an instrument, not a pitch. It reads like the front panel of a precision device:
a dark field, phosphor traces, calibrated scales, every reading labelled with its unit and its
source. Data is the primary visual. Copy is short, declarative and measured. Nothing on the page
claims more than a number in `bench/results/` supports.

**Signature interaction:** the HNSW descent. A real HNSW graph, built in the browser, shown as
stacked layers. Click (or tap) anywhere on the base plane to drop a query; the search walks down
the layers one hop at a time, and the candidate frontier, visited set and final top-k light up
in sequence. An `ef_search` slider changes the breadth live.

## Palette

Warm neutrals and terracotta, one light theme (changed 2026-11-13 at the author's request,
replacing the dark observatory palette): a cream page, charcoal ink, and dusty terracotta as the
single accent. It should feel physical and curated, like a printed technical journal. FAISS keeps
its own series colour, a neutral slate, so terracotta stays the only accent.

| Token | Hex | Use | Contrast on `--bg` / `--panel` |
| --- | --- | --- | --- |
| `--bg` | `#FDFCF8` | page (off-white cream) | |
| `--panel` | `#FAF7F1` | panels | |
| `--rule` | `#E7E0D2` | hairlines, grids | |
| `--rule-strong` | `#C9BEAA` | axes, nodes, outlines at rest | |
| `--ink` | `#1F2328` | body text (charcoal) | 15.39:1 / 14.77:1 |
| `--ink-dim` | `#5E636B` | secondary text, labels | 5.89:1 / 5.65:1 |
| `--trace` | `#B85042` | the accent (terracotta): VectorForge, focus ring, active state | 4.80:1 / 4.61:1 |
| `--trace-dim` | `#DE9A88` | visited nodes, inactive traces | (decorative) |
| `--signal` | `#4A5058` | FAISS series and warnings only (slate) | 7.93:1 / 7.61:1 |

Contrast ratios are WCAG relative-luminance ratios, computed by `web/scripts/contrast.mjs` (run
it to re-check after any change). The panel tone was lightened from a first `#F6F2E9` because
terracotta measured 4.41:1 on it.

Banned, from the spec and the author's rules: purple gradients, rainbow CTAs, glassmorphism and
backdrop blur, emoji icons, stock or AI photos, testimonials, user counters, "made with" badges,
cursor-follow effects, hover background-fill shifts, em dashes in copy.

## Type

- **Geist** for headings and prose; **Geist Mono** for every number, unit, parameter and code
  token, with `font-variant-numeric: tabular-nums` so columns align.
- Both self-hosted at build time by `next/font` (no runtime font request, CSP stays `'self'`).
- Fluid scale, all `clamp()`:
  - `--step--1: clamp(0.80rem, 0.78rem + 0.10vw, 0.875rem)`
  - `--step-0: clamp(1rem, 0.96rem + 0.20vw, 1.125rem)`
  - `--step-1: clamp(1.2rem, 1.1rem + 0.5vw, 1.5rem)`
  - `--step-2: clamp(1.5rem, 1.3rem + 1vw, 2.125rem)`
  - `--step-3: clamp(2rem, 1.6rem + 2vw, 3.25rem)`
  - `--step-4: clamp(2.6rem, 1.9rem + 3.4vw, 5rem)`

## Layout

- Content column max 1360px, centred, 16px gutters on phones, 32px from 768px.
- Background elements (hero graph) are full-bleed; text never is.
- Section rhythm: 8px base grid; section padding `clamp(4rem, 3rem + 5vw, 9rem)`.
- Panels: 1px `--rule` border, 2px radius, no shadows. Depth comes from borders, not blur.

## Motion

- Easing: `--ease-out: cubic-bezier(0.22, 1, 0.36, 1)`; `--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1)`.
- UI feedback 150 to 250 ms; reveals 500 to 700 ms; nothing over 800 ms.
- Transform, opacity and SVG stroke only.
- One signature effect per section: hero graph drift; visualizer descent; chart traces drawing
  in; search results stepping in; architecture paths drawing as you scroll; limitations items
  revealing; footer none.
- No entrance animation on hero text; first paint never waits on JS.
- `prefers-reduced-motion: reduce`: all decorative motion off, the visualizer becomes manual
  step-through, chart traces appear complete.

## Icons

Inline SVG, 24px grid, 1.5px stroke, round caps and joins, `currentColor`. Defined once in
`web/components/icons.tsx`.
