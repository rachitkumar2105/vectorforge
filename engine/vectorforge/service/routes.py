"""HTTP endpoints. Handlers are plain ``def`` so FastAPI runs them in its worker thread pool:
index work is CPU-bound and would otherwise block the event loop."""

from __future__ import annotations

import time
from typing import Annotated, Any

import numpy as np
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import PlainTextResponse

from vectorforge.collection import (
    CollectionClosedError,
    FilterError,
    UpsertItem,
    VectorValidationError,
)
from vectorforge.service.database import CollectionNotFoundError, Database
from vectorforge.service.errors import ApiError
from vectorforge.service.schemas import (
    CollectionInfo,
    CollectionList,
    CreateCollection,
    SearchHit,
    SearchRequest,
    SearchResponse,
    UpsertRequest,
    UpsertResponse,
    VectorId,
)
from vectorforge.service.security import Principal, RateLimiter, Settings, identify

router = APIRouter()


def _settings(request: Request) -> Settings:
    s: Settings = request.app.state.settings
    return s


def _db(request: Request) -> Database:
    db: Database = request.app.state.db
    if not db.ready:
        raise ApiError(503, "not_ready", "service is starting or stopping")
    return db


def _client_ip(request: Request, settings: Settings) -> str:
    if settings.client_ip_header:
        forwarded = request.headers.get(settings.client_ip_header)
        if forwarded:
            return forwarded.strip()
    return request.client.host if request.client else "unknown"


def principal(request: Request, x_api_key: Annotated[str | None, Header()] = None) -> Principal:
    settings = _settings(request)
    limiter: RateLimiter = request.app.state.limiter
    who = identify(x_api_key, settings)
    if who is None:
        # Only failures spend from the per-address budget, and a valid key is never refused by
        # it. Otherwise everyone behind one proxy address could be locked out by a stranger.
        ip = _client_ip(request, settings)
        if limiter.take(ip, "auth_fail", settings.auth_fail_rate):
            wait = limiter.blocked(ip, "auth_fail", settings.auth_fail_rate)
            raise ApiError(
                429, "rate_limited", "too many failed attempts", {"Retry-After": str(wait)}
            )
        raise ApiError(401, "unauthorized", "missing or invalid API key")
    request.state.role = who.role
    return who


Caller = Annotated[Principal, Depends(principal)]
DB = Annotated[Database, Depends(_db)]


def _limit(request: Request, who: Principal, kind: str) -> None:
    settings = _settings(request)
    rate = settings.search_rate if kind == "search" else settings.write_rate
    wait = request.app.state.limiter.take(who.role, kind, rate)
    if wait:
        raise ApiError(
            429, "rate_limited", f"{kind} rate limit exceeded", {"Retry-After": str(wait)}
        )


def _require_admin(who: Principal) -> None:
    if who.role != "admin":
        raise ApiError(403, "forbidden", "this key is read-only")


def _require_read(request: Request, who: Principal, name: str) -> None:
    if not who.can_read(name, _settings(request).demo_collection):
        raise ApiError(403, "forbidden", "this key cannot access that collection")


def _info(raw: dict[str, Any]) -> CollectionInfo:
    return CollectionInfo(**{k: raw[k] for k in CollectionInfo.model_fields})


def _get(db: Database, name: str) -> Any:
    try:
        return db.get(name)
    except CollectionNotFoundError:
        raise ApiError(404, "not_found", "collection not found") from None


# The public demo key is read-only and anonymous, so it also gets a smaller search budget than
# the documented API limits: enough for any real demo query, far from the most expensive search.
DEMO_MAX_K = 20
DEMO_MAX_EF = 256
DEMO_MAX_NPROBE = 64


def _check_demo_limits(body: SearchRequest) -> None:
    caps = (("k", body.k, DEMO_MAX_K), ("ef_search", body.ef_search, DEMO_MAX_EF))
    for name, value, cap in (*caps, ("nprobe", body.nprobe, DEMO_MAX_NPROBE)):
        if value is not None and value > cap:
            raise ApiError(422, "validation_error", f"{name} is limited to {cap} for this key")


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> Response:
    if not request.app.state.db.ready:
        raise ApiError(503, "not_ready", "service is starting or stopping")
    return Response('{"status":"ready"}', media_type="application/json")


@router.post("/collections", status_code=201, response_model=CollectionInfo)
def create_collection(
    body: CreateCollection, request: Request, who: Caller, db: DB
) -> CollectionInfo:
    _require_admin(who)
    _limit(request, who, "write")
    params = body.index.params.model_dump()
    try:
        c = db.create(
            body.name,
            dim=body.dim,
            metric=body.metric,
            index_type=body.index.type,
            index_params=params,
        )
    except FileExistsError:
        raise ApiError(409, "conflict", "collection already exists") from None
    return _info(c.info())


@router.get("/collections", response_model=CollectionList)
def list_collections(who: Caller, db: DB) -> CollectionList:
    _require_admin(who)
    return CollectionList(collections=[_info(db.get(n).info()) for n in db.names()])


@router.get("/collections/{name}", response_model=CollectionInfo)
def get_collection(name: str, request: Request, who: Caller, db: DB) -> CollectionInfo:
    _require_read(request, who, name)
    return _info(_get(db, name).info())


@router.delete("/collections/{name}", status_code=204)
def drop_collection(name: str, request: Request, who: Caller, db: DB) -> Response:
    _require_admin(who)
    _limit(request, who, "write")
    try:
        db.drop(name)
    except CollectionNotFoundError:
        raise ApiError(404, "not_found", "collection not found") from None
    return Response(status_code=204)


@router.post("/collections/{name}/vectors", response_model=UpsertResponse)
def upsert(name: str, body: UpsertRequest, request: Request, who: Caller, db: DB) -> UpsertResponse:
    _require_admin(who)
    _limit(request, who, "write")
    c = _get(db, name)
    batch = [
        UpsertItem(v.id, np.asarray(v.values, dtype=np.float32), dict(v.metadata))
        for v in body.vectors
    ]
    try:
        n = c.upsert(batch)
    except VectorValidationError as exc:  # messages are ours: id, dimension, size
        raise ApiError(422, "validation_error", str(exc)) from None
    except CollectionClosedError:
        raise ApiError(404, "not_found", "collection not found") from None
    return UpsertResponse(upserted=n)


@router.post("/collections/{name}/search", response_model=SearchResponse)
def search(name: str, body: SearchRequest, request: Request, who: Caller, db: DB) -> SearchResponse:
    _require_read(request, who, name)
    _limit(request, who, "search")
    if who.role == "demo":
        _check_demo_limits(body)
    c = _get(db, name)
    if len(body.vector) != c.manifest.dim:
        raise ApiError(422, "validation_error", f"vector must have dimension {c.manifest.dim}")
    query = np.asarray(body.vector, dtype=np.float32)
    if not np.all(np.isfinite(query)):
        raise ApiError(422, "validation_error", "vector overflows float32")
    started = time.perf_counter()
    try:
        out = c.search(
            query,
            body.k,
            ef_search=body.ef_search,
            nprobe=body.nprobe,
            filter=body.filter,
            include_metadata=body.include_metadata,
        )
    except FilterError as exc:
        raise ApiError(422, "validation_error", str(exc)) from None
    except CollectionClosedError:
        raise ApiError(404, "not_found", "collection not found") from None
    took = (time.perf_counter() - started) * 1000
    return SearchResponse(
        results=[SearchHit(id=h.id, distance=h.distance, metadata=h.metadata) for h in out.hits],
        took_ms=round(took, 3),
        strategy=out.strategy,
    )


@router.delete("/collections/{name}/vectors/{vector_id}", status_code=204)
def delete_vector(
    name: str, vector_id: VectorId, request: Request, who: Caller, db: DB
) -> Response:
    _require_admin(who)
    _limit(request, who, "write")
    c = _get(db, name)
    try:
        c.delete(vector_id)
    except KeyError:
        raise ApiError(404, "not_found", "vector not found") from None
    return Response(status_code=204)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics(request: Request, who: Caller) -> PlainTextResponse:
    _require_admin(who)
    db: Database = request.app.state.db
    text = request.app.state.metrics.render(db.sizes(), _settings(request).bench_summary)
    return PlainTextResponse(text, media_type="text/plain; version=0.0.4")
