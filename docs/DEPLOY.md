# Deploying VectorForge on free tiers

Engine on **Render** (free web service), site on **Vercel** (Hobby). No paid plan, no card.
Nothing here needs a password or key from anyone else: you create both services and set the
variables below yourself.

## 0. One value to generate first

The site talks to the engine with a read-only **demo key**. The same value goes in both places.
Generate it once, keep it out of chat and git:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## 1. Engine on Render (free)

1. Render dashboard → **New** → **Blueprint** → connect `rachitkumar2105/vectorforge`.
   Render reads `render.yaml`: one free Docker web service, `vectorforge-engine`, region
   Singapore, built from `engine/Dockerfile` with the repository root as context, health check
   `/readyz`.
2. When Render asks for the values marked `sync: false`, set:

| Variable | Value | Notes |
| --- | --- | --- |
| `VECTORFORGE_DEMO_KEY` | the value from step 0 | read-only, scoped to the demo collection |
| `VECTORFORGE_CORS_ORIGINS` | `https://<your-project>.vercel.app,http://localhost:3000` | exact origins, no wildcard; the browser never calls the engine directly, this is defence in depth |

   Set by the blueprint, nothing to do: `VECTORFORGE_ADMIN_KEY` (Render generates a random value;
   you never need it, because the demo is pre-built into the image), `VECTORFORGE_ENV=production`.
   Set by the Dockerfile: `VECTORFORGE_DATA_DIR=/app/data`, `VECTORFORGE_SEED_DIR=/app/seed`, `PORT`.
3. Wait for the first deploy. The build pre-builds the demo index from the committed seed corpus,
   which takes a few minutes. Then check, replacing the host:

```bash
curl https://vectorforge-engine.onrender.com/healthz     # {"status":"ok"}
curl https://vectorforge-engine.onrender.com/readyz      # {"status":"ready"}
```

What the free tier means (also stated on the site and in the README): 512 MB RAM, so the hosted
corpus is 3,178 vectors; no persistent disk, so the demo comes back from the image on every
restart and anything written to the engine is lost; sleeps after 15 minutes idle, about a minute
to wake.

## 2. Site on Vercel (Hobby)

Recommended: import the GitHub repository, which also gives a preview deployment for every pull
request.

1. Vercel dashboard → **Add New** → **Project** → import `rachitkumar2105/vectorforge`.
2. **Root Directory:** `web`. Framework preset: Next.js (detected). Leave install and build
   commands on their defaults (pnpm is detected from `pnpm-lock.yaml` and `packageManager`).
3. **Environment variables** (Settings → Environment Variables), for Production and Preview:

| Variable | Value | Exposure |
| --- | --- | --- |
| `VECTORFORGE_ENGINE_URL` | `https://vectorforge-engine.onrender.com` (your Render URL, no trailing slash) | server only |
| `VECTORFORGE_DEMO_KEY` | the value from step 0 | server only; mark it **Sensitive** |
| `NEXT_PUBLIC_SITE_URL` | `https://<your-project>.vercel.app` (later: your custom domain) | public |
| `NEXT_PUBLIC_REPO_URL` | `https://github.com/rachitkumar2105/vectorforge` | public |

   Do not prefix the engine URL or the key with `NEXT_PUBLIC_`: that would ship them to browsers.
   `VERCEL=1` is set by the platform; the demo route uses it to trust Vercel's client-IP header
   for rate limiting.
4. Deploy. Then add the production URL to `VECTORFORGE_CORS_ORIGINS` on Render if it differs from
   what you entered.

Alternative with the CLI (you ran `vercel login`): from `web/`, `vercel link`, set the variables
above with `vercel env add <NAME> production` (it prompts for the value, nothing is echoed), then
`vercel deploy --prod`.

## 3. Checks after deploy (I run these with Playwright once you share the URLs)

1. Production URL loads; console clean; no CSP violations.
2. Live search: the pill goes checking → live (or checking → waking → live after a cold start),
   and results are labelled "Live engine results".
3. **Engine suspended:** Render dashboard → the service → **Suspend**. Reload the site: hero,
   visualizer, benchmark charts and architecture render and work; the pill ends at
   "engine asleep, showing saved results"; searches return results labelled
   "Saved snapshot results". Then **Resume** the service.
4. Nine widths, reduced motion, Tab walk, Lighthouse mobile on the production URL.

## 4. Still open after this

- Custom domain (Vercel → Domains). Set `NEXT_PUBLIC_SITE_URL` and the Render CORS list to it.
- Uptime check: a free monitor (for example UptimeRobot) on `/healthz` would also keep the free
  engine awake around the clock; decide whether you want that, since the cold-start state exists
  precisely so the site works while it sleeps.
- The privacy and terms pages are drafts, not legal advice.
