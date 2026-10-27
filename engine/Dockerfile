# syntax=docker/dockerfile:1.7
# Build from the repository root:  docker build -f engine/Dockerfile -t vectorforge-engine .
# (The root .dockerignore limits the context to the engine package and the demo seed files.)
#
# Multi-stage. The final image holds the installed wheel, its runtime dependencies and a
# pre-built demo collection: no compilers, no pip, no tests, no benchmark datasets.

# Base image pinned by digest (re-audit R4): every Render deploy rebuilds the image, and a moving
# tag would pull a different, unreviewed base each time. To update: run
# `docker buildx imagetools inspect python:3.12-slim`, copy the index Digest into PYTHON_IMAGE,
# rebuild and rerun the image checks.
ARG PYTHON_IMAGE=python:3.12-slim@sha256:5b8b1421ccb6a525860a77863c049eab5847076cda34e030c75a80c58faf3f3c
FROM ${PYTHON_IMAGE} AS build
WORKDIR /src
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY engine/pyproject.toml engine/README.md ./
COPY engine/vectorforge ./vectorforge
RUN pip wheel --wheel-dir /wheels .

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    VECTORFORGE_ENV=production \
    VECTORFORGE_DATA_DIR=/app/data \
    VECTORFORGE_SEED_DIR=/app/seed \
    PORT=8000
RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin vectorforge
COPY --from=build /wheels /wheels
RUN pip install --no-index --find-links /wheels vectorforge \
 && rm -rf /wheels
# The demo corpus (committed sample data: 3,178 docstring embeddings) and a checkpointed
# collection built from it. Building the HNSW graph here, on the build machine, keeps cold
# starts to a snapshot load on small free-tier instances. Without a persistent disk the data
# dir is ephemeral: writes are lost on restart and the baked demo comes back.
COPY web/data/demo/seed.json web/data/demo/docs.json web/data/demo/docs.bin /app/seed/
RUN python -m vectorforge.service.seed --seed-dir /app/seed --data-dir /app/data \
 && chown -R vectorforge /app/data \
 && pip uninstall -y pip setuptools wheel || true
USER vectorforge
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8000'), timeout=2).status == 200 else 1)"
# No default key: the service exits at startup unless VECTORFORGE_ADMIN_KEY is set (S18).
CMD ["python", "-c", "from vectorforge.service.app import main; main()"]
