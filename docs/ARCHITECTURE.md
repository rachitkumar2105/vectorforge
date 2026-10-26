# VectorForge: Architecture

## System view

```
 Browser ──HTTPS──> Next.js on Vercel ──HTTPS + demo key──> VectorForge engine (Docker, Fly/Railway)
   │                  │  /api/search route handler           │  FastAPI service
   │                  │  (embeds query, rate limits,          │  Database -> Collection
   │                  │   falls back to snapshot)             │     ├─ Index (HNSW | IVF | Flat)
   │                  └─ static bench/results/*.json          │     ├─ SegmentStore (mmap vectors)
   └─ HNSW visualizer runs entirely client-side               │     ├─ WAL (crc32 records)
                                                              │     └─ Manifest (atomic JSON)
```

The browser never talks to the engine directly and never holds a key. The site reads benchmark
results as static JSON at build time, so it renders fully with the engine offline.

## Engine layers

| Layer | Module | Responsibility |
| --- | --- | --- |
| Math | `core/distance.py` | L2 squared, inner product, cosine distance; one query against a matrix, vectorized |
| Math | `core/quantize.py` | Per-dimension int8 scalar quantization with stored min/max |
| Index | `index/base.py` | `Index` ABC: `add`, `search`, `delete`, `save`, `load`, `stats` |
| Index | `index/flat.py` | Exact brute force; the ground truth for every recall number |
| Index | `index/hnsw.py` | Hierarchical Navigable Small World graph, written by hand |
| Index | `index/ivf.py` | IVF-Flat: k-means++ centroids, inverted lists, `nprobe` probing |
| Storage | `storage/segment.py` | Fixed-capacity, append-only, memory-mapped vector files |
| Storage | `storage/wal.py` | Length-prefixed, crc32-checked operation log; torn-tail truncation |
| Storage | `storage/metadata.py` | Collection manifest, written to a temp file and atomically renamed |
| Domain | `collection.py` | Maps external string ids to internal labels, applies WAL, filters, checkpoints |
| Service | `service/*` | FastAPI app factory, routes, Pydantic schemas, API keys, token-bucket rate limits |

Distances are always "smaller is closer": inner product is returned negated and cosine as
`1 - cos`. This lets every index use one ordering rule.

## Write path

1. `POST /collections/{name}/vectors` validated by Pydantic (dimension, batch cap, finite floats).
2. `Collection.upsert` encodes one WAL record per vector, appends them, then `fsync`s once
   (group commit per request). **The request is acknowledged only after fsync returns.**
3. The vector is written to the active segment slot for its internal label.
4. The index inserts the label (HNSW links it into the graph; IVF appends to its list).
5. Re-upserting an existing id tombstones the old label and inserts a new one.
6. Every `checkpoint_every` operations (and on clean shutdown) a checkpoint runs: segments flushed,
   index graph saved, payload snapshot saved, manifest atomically replaced with the checkpoint
   LSN, then the WAL is rotated.

## Read path

1. `POST /collections/{name}/search` with `k`, optional `ef_search` / `nprobe`, optional filter.
2. The filter is compiled into a predicate over internal labels.
3. HNSW: greedy descent with `ef=1` through upper layers, then best-first `search_layer` at layer 0.
   Tombstoned and filtered-out nodes are still traversed (they keep the graph connected) but are
   never admitted to the result set. If the filter is very selective the collection switches to an
   exact scan of the matching labels instead, because graph traversal recall collapses there.
4. Results are mapped back to external ids plus metadata.

## Recovery

On open: read manifest -> load index snapshot (graph) and payload snapshot -> load segment vectors
-> replay WAL records with `lsn > checkpoint_lsn`. A record whose length prefix or crc32 does not
check out ends replay; the file is truncated at the last good offset. Because acknowledgement
happens only after fsync, any record that was acknowledged is complete on disk, so truncation only
ever drops unacknowledged bytes.

## Concurrency model

One re-entrant lock per collection serialises writes and searches. Python's GIL means parallel
HNSW search would gain little; the lock keeps the graph consistent without fine-grained locking.
This is a deliberate simplicity trade-off, documented in the limitations.

## Deployment

- Engine: multi-stage Docker image (wheel built in a builder stage, slim runtime, non-root user),
  `/healthz` and `/readyz` wired to the platform health checks, admin key as a platform secret.
- Site: Vercel. The engine URL and demo key are server-only env vars used inside route handlers.
