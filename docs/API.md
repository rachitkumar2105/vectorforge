# VectorForge: HTTP API

Base URL: the engine host. All bodies are JSON. Errors are `{"error": {"code": str, "message": str}}`
with no stack traces or internal paths.

## Authentication

Header `X-API-Key: <key>`.

| Key | Source | Can do |
| --- | --- | --- |
| Admin | `VECTORFORGE_ADMIN_KEY` (required, >= 32 chars; the service refuses to start without it) | everything |
| Demo | `VECTORFORGE_DEMO_KEY` (optional) | `GET /collections/{demo}`, `POST /collections/{demo}/search` only |

Missing or wrong key: `401`. Valid key without permission: `403`.

## Limits

| Limit | Value | Response |
| --- | --- | --- |
| Request body | 4 MiB (`VECTORFORGE_MAX_BODY_BYTES`) | `413` |
| Vectors per upsert | 1000 | `422` |
| Dimension | 1 to 4096 | `422` |
| `k` | 1 to 1000 | `422` |
| Metadata per vector | 4 KiB serialized, flat object, scalar values | `422` |
| Rate limit (per key) | token bucket: search 20/s burst 40, writes 5/s burst 10 | `429` + `Retry-After` |
| Demo key search budget | `k` <= 20, `ef_search` <= 256, `nprobe` <= 64 | `422` |

## Endpoints

### `POST /collections` (admin)

```json
{"name": "docs", "dim": 100, "metric": "cosine",
 "index": {"type": "hnsw", "params": {"M": 16, "ef_construction": 200}}}
```

`metric`: `l2` | `ip` | `cosine`. `index.type`: `hnsw` | `ivf` | `flat`.
IVF params: `nlist` (default 64), `quantization` (`none` | `int8`). Flat params: `quantization`.
Names match `^[a-z0-9][a-z0-9_-]{0,62}$`. `201` with the collection description; `409` if it exists.

### `GET /collections` (admin) -> `{"collections": [CollectionInfo, ...]}`

### `GET /collections/{name}` -> `CollectionInfo`

```json
{"name": "docs", "dim": 100, "metric": "cosine", "index": {"type": "hnsw", "params": {...}},
 "count": 3000, "deleted": 2}
```

### `DELETE /collections/{name}` (admin) -> `204`

### `POST /collections/{name}/vectors` (admin)

```json
{"vectors": [{"id": "doc-1", "values": [0.1, ...], "metadata": {"lang": "en"}}]}
```

Ids: 1 to 128 chars of `[A-Za-z0-9_.:-]`. Upsert semantics. Response `{"upserted": n}` after the
WAL fsync.

### `POST /collections/{name}/search`

```json
{"vector": [0.1, ...], "k": 10, "ef_search": 100, "nprobe": 8,
 "filter": {"lang": "en", "year": {"in": [2023, 2024]}}, "include_metadata": true}
```

Response:

```json
{"results": [{"id": "doc-1", "distance": 0.12, "metadata": {"lang": "en"}}],
 "took_ms": 1.84, "strategy": "graph"}
```

`strategy` is `graph`, `ivf`, `exact` or `exact_filtered` (selective filter fallback).

### `DELETE /collections/{name}/vectors/{id}` (admin) -> `204`, tombstone. `404` if unknown.

### `GET /healthz` -> `{"status": "ok"}` (no auth, process is alive)

### `GET /readyz` -> `{"status": "ready"}` once collections are loaded, else `503` (no auth)

### `GET /metrics` (admin) -> Prometheus text format

- `vectorforge_requests_total{method,route,status}`
- `vectorforge_request_duration_seconds` histogram `{route}`
- `vectorforge_index_vectors{collection}` and `vectorforge_index_deleted{collection}`
- `vectorforge_benchmark_recall_at_10{dataset,index}` from the last benchmark results file
