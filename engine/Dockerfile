# syntax=docker/dockerfile:1.7
# Multi-stage build. The final image holds the installed wheel and its runtime dependencies
# only: no compilers, no pip cache, no tests, no datasets, no bench code.

FROM python:3.12-slim AS build
WORKDIR /src
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY pyproject.toml ./
COPY vectorforge ./vectorforge
# The README is referenced by pyproject; a stub keeps the build context to engine/ only.
RUN echo "VectorForge engine" > /README.md \
 && pip wheel --wheel-dir /wheels .

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    VECTORFORGE_ENV=production VECTORFORGE_DATA_DIR=/data PORT=8000
RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin vectorforge \
 && mkdir /data && chown vectorforge /data
COPY --from=build /wheels /wheels
RUN pip install --no-index --find-links /wheels vectorforge \
 && rm -rf /wheels \
 && pip uninstall -y pip setuptools wheel || true
USER vectorforge
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2).status == 200 else 1)"
# No default key: the service exits at startup unless VECTORFORGE_ADMIN_KEY is set (S18).
CMD ["python", "-c", "from vectorforge.service.app import main; main()"]
