# VectorForge

A vector database written from first principles, benchmarked honestly against FAISS, with a
showcase site.

- **Engine** (`engine/`): Python + NumPy. Hand-written HNSW (heuristic and simple neighbour
  selection, tombstone deletes, filtered traversal), IVF-Flat (k-means++), per-dimension int8
  scalar quantization, memory-mapped segments, a crc32-checked write-ahead log with torn-tail
  recovery, atomic manifests, and a FastAPI service with API keys, token-bucket rate limits and
  Prometheus metrics. No ANN library is imported by the engine.
- **Benchmark** (`bench/`): SIFT1M and GloVe-100d (public), ground truth by exact search,
  ef_search / nprobe sweeps, FAISS `IndexHNSWFlat` / `IndexIVFFlat` as the baseline, results in
  `bench/results/*.json`.
- **Site** (`web/`): Next.js. An in-browser HNSW visualizer, the benchmark explorer, a live
  semantic search demo with a static fallback, an architecture walkthrough and a limitations
  section.

The point is not to beat FAISS (it does not). The point is a correct implementation, measured
rigorously, with the gap explained.

## Quick start

```bash
# One shared venv outside the repo (never .venv/ inside it)
python -m venv ~/.venvs/vectorforge
source ~/.venvs/vectorforge/bin/activate        # Linux/macOS
source ~/.venvs/vectorforge/Scripts/activate    # Windows Git Bash
pip install -e "engine[dev,bench]"

# Tests (coverage gate 85%)
cd engine && pytest --cov=vectorforge

# Run the engine
export VECTORFORGE_ADMIN_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
python -c "from vectorforge.service.app import main; main()"
```

## Regenerate every number on the site

```bash
python bench/datasets/download.py all   # SIFT1M + GloVe into ~/datasets (about 1 GB)
python bench/run_bench.py               # writes bench/results/*.json (about 1 hour, single thread)
python bench/demo/build_demo.py         # demo corpus embeddings into web/data/demo
```

## Site

```bash
cd web
pnpm install            # pnpm only; uses the global content-addressed store
pnpm dev                # copies bench/results into web/data/bench, then starts Next.js
```

Server-only environment for the demo route: `VECTORFORGE_ENGINE_URL`, `VECTORFORGE_DEMO_KEY`.
Without them the demo answers from the static snapshot and says so.

## Hosting (free tiers) and their limits

- **Engine:** Render free web service, from `render.yaml` and `engine/Dockerfile`.
  - **512 MB RAM.** The hosted demo corpus is 3,178 vectors (Python standard-library docstrings).
    Full benchmark numbers come from local runs and are served as committed JSON from
    `bench/results`, never from the hosted engine.
  - **No persistent disk.** The demo index is rebuilt from the committed seed corpus
    (`web/data/demo/seed.json`) when the image is built and baked into it; every restart starts
    from that snapshot. Measured at 0.1 CPU / 512 MB: ready in 37 s using 53 MB. Rebuilding the
    graph on boot instead took more than 10 minutes there, so it is not done at startup. Anything
    written to the hosted engine is lost on restart.
  - **Sleeps after 15 minutes idle.** The next request waits for a cold start of about a minute.
    The site's search section shows a status pill (checking, waking, live, unavailable) and
    answers from a saved snapshot until the engine is live.
- **Site:** Vercel Hobby. Everything except live search (hero, visualizer, benchmark charts,
  architecture) is static or client-side and works with the engine completely down.
- Deployment steps and the exact environment variables: `docs/DEPLOY.md`.

## Layout

```
engine/vectorforge/core      distance functions, int8 quantization
engine/vectorforge/index     flat, hnsw, ivf
engine/vectorforge/storage   segments, WAL, manifests
engine/vectorforge/service   FastAPI app, routes, schemas, security
engine/vectorforge/collection.py
bench/                       dataset scripts, run_bench.py, results/
web/                         Next.js showcase
docs/                        PRD, ARCHITECTURE, API, DESIGN, DECISIONS, INTERVIEW
```

Reports: `RUN-REPORT.md` (phase log), `SECURITY.md`, `DEMO-REPORT.md`, `FINAL-AUDIT.md`.
