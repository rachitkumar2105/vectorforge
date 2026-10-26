"""Pydantic request and response models. All limits from docs/API.md live here."""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
)

MAX_DIM = 4096
MAX_BATCH = 1000
MAX_K = 1000
MAX_METADATA_BYTES = 4096
MAX_METADATA_KEYS = 32

# strict=True: reject "1.5" strings and booleans; allow_inf_nan=False: reject NaN and +/-inf,
# which Python's json module happily parses and which would poison every distance computation.
Component = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Vector = Annotated[list[Component], Field(min_length=1, max_length=MAX_DIM)]
Scalar = StrictStr | StrictInt | StrictFloat | StrictBool
VectorId = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]
CollectionName = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HNSWParams(Strict):
    M: int = Field(16, ge=2, le=128)
    ef_construction: int = Field(200, ge=1, le=2000)
    ef_search: int = Field(50, ge=1, le=10_000)
    heuristic: bool = True
    seed: int = Field(0, ge=0)


class IVFParams(Strict):
    nlist: int = Field(64, ge=1, le=65_536)
    nprobe: int = Field(8, ge=1, le=65_536)
    quantization: Literal["none", "int8"] = "none"
    seed: int = Field(0, ge=0)


class FlatParams(Strict):
    pass


class HNSWSpec(Strict):
    type: Literal["hnsw"]
    params: HNSWParams = Field(default_factory=HNSWParams)


class IVFSpec(Strict):
    type: Literal["ivf"]
    params: IVFParams = Field(default_factory=IVFParams)


class FlatSpec(Strict):
    type: Literal["flat"]
    params: FlatParams = Field(default_factory=FlatParams)


IndexSpec = Annotated[HNSWSpec | IVFSpec | FlatSpec, Field(discriminator="type")]


class CreateCollection(Strict):
    name: CollectionName
    dim: int = Field(ge=1, le=MAX_DIM)
    metric: Literal["l2", "ip", "cosine"]
    index: IndexSpec


class VectorItem(Strict):
    id: VectorId
    values: Vector
    metadata: dict[str, Scalar] = Field(default_factory=dict, max_length=MAX_METADATA_KEYS)

    @field_validator("metadata")
    @classmethod
    def metadata_size(cls, v: dict[str, Scalar]) -> dict[str, Scalar]:
        for key in v:
            if not 1 <= len(key) <= 64:
                raise ValueError("metadata keys must be 1 to 64 characters")
        if len(json.dumps(v, separators=(",", ":")).encode()) > MAX_METADATA_BYTES:
            raise ValueError(f"metadata exceeds {MAX_METADATA_BYTES} bytes")
        return v


class UpsertRequest(Strict):
    vectors: list[VectorItem] = Field(min_length=1, max_length=MAX_BATCH)


class SearchRequest(Strict):
    vector: Vector
    k: int = Field(10, ge=1, le=MAX_K)
    ef_search: int | None = Field(None, ge=1, le=10_000)
    nprobe: int | None = Field(None, ge=1, le=65_536)
    filter: dict[str, Any] | None = Field(None, max_length=16)
    include_metadata: bool = True


class SearchHit(BaseModel):
    id: str
    distance: float
    metadata: dict[str, Any] | None = None


class SearchResponse(BaseModel):
    results: list[SearchHit]
    took_ms: float
    strategy: str


class CollectionInfo(BaseModel):
    name: str
    dim: int
    metric: str
    index: dict[str, Any]
    count: int
    deleted: int


class CollectionList(BaseModel):
    collections: list[CollectionInfo]


class UpsertResponse(BaseModel):
    upserted: int
