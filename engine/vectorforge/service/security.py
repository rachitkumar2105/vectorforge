"""Configuration, API-key authentication and token-bucket rate limiting."""

from __future__ import annotations

import hmac
import math
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

MIN_KEY_LENGTH = 32
Role = Literal["admin", "demo"]


class ConfigError(RuntimeError):
    """The service is misconfigured and must not start."""


LOCAL_HOSTS = ("localhost", "127.0.0.1")


def _exact_origin(origin: str) -> bool:
    """An exact allowlist entry: scheme://host[:port] and nothing else, no wildcard (S11).
    https for any host; plain http only for localhost, compared on the parsed hostname so that
    "http://localhost.evil.com" does not slip through a prefix check."""
    parts = urlsplit(origin)
    if "*" in origin or parts.path or parts.query or parts.fragment or not parts.hostname:
        return False
    if f"{parts.scheme}://{parts.netloc}" != origin:
        return False
    return parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in LOCAL_HOSTS)


@dataclass(frozen=True)
class Settings:
    admin_key: str = field(repr=False)
    data_dir: Path
    demo_key: str | None = field(default=None, repr=False)
    demo_collection: str = "demo"
    cors_origins: list[str] = field(default_factory=list)
    env: str = "development"
    max_body_bytes: int = 4 * 1024 * 1024
    # (tokens per second, burst capacity)
    search_rate: tuple[float, int] = (20.0, 40)
    write_rate: tuple[float, int] = (5.0, 10)
    auth_fail_rate: tuple[float, int] = (0.2, 10)
    # Header carrying the real client IP when behind a trusted proxy (e.g. "Fly-Client-IP").
    # Only set this when the engine is reachable solely through that proxy, which overwrites the
    # header; otherwise a client can forge it.
    client_ip_header: str | None = None
    bench_summary: Path | None = None

    def __post_init__(self) -> None:
        if not self.admin_key or len(self.admin_key) < MIN_KEY_LENGTH:
            raise ConfigError(
                f"VECTORFORGE_ADMIN_KEY must be set to at least {MIN_KEY_LENGTH} characters"
            )
        if self.demo_key is not None:
            if len(self.demo_key) < MIN_KEY_LENGTH:
                raise ConfigError(
                    f"VECTORFORGE_DEMO_KEY must be at least {MIN_KEY_LENGTH} characters"
                )
            if hmac.compare_digest(self.demo_key, self.admin_key):
                raise ConfigError("the demo key must differ from the admin key")
        for origin in self.cors_origins:
            if not _exact_origin(origin):
                raise ConfigError(
                    f"CORS origin {origin!r} is not an exact https or localhost origin"
                )
        if self.max_body_bytes < 1024:
            raise ConfigError("VECTORFORGE_MAX_BODY_BYTES must be at least 1024")

    @property
    def production(self) -> bool:
        return self.env == "production"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        admin_key = env.get("VECTORFORGE_ADMIN_KEY", "")
        if not admin_key:
            # No default key, ever (S18). Fail loudly at startup instead.
            raise ConfigError("VECTORFORGE_ADMIN_KEY is not set; refusing to start")
        origins = [
            o.strip() for o in env.get("VECTORFORGE_CORS_ORIGINS", "").split(",") if o.strip()
        ]
        summary = env.get("VECTORFORGE_BENCH_SUMMARY")
        return cls(
            admin_key=admin_key,
            demo_key=env.get("VECTORFORGE_DEMO_KEY") or None,
            demo_collection=env.get("VECTORFORGE_DEMO_COLLECTION", "demo"),
            data_dir=Path(env.get("VECTORFORGE_DATA_DIR", "./data")),
            cors_origins=origins,
            env=env.get("VECTORFORGE_ENV", "development"),
            max_body_bytes=int(env.get("VECTORFORGE_MAX_BODY_BYTES", str(4 * 1024 * 1024))),
            client_ip_header=env.get("VECTORFORGE_CLIENT_IP_HEADER") or None,
            bench_summary=Path(summary) if summary else None,
        )


@dataclass(frozen=True)
class Principal:
    """Who is calling. Holds the role only; the key itself is never stored past the check."""

    role: Role

    def can_read(self, collection: str, demo_collection: str) -> bool:
        return self.role == "admin" or collection == demo_collection


def identify(presented: str | None, settings: Settings) -> Principal | None:
    if not presented:
        return None
    # compare_digest takes time independent of where the strings differ, so response timing
    # does not leak how many leading characters of a guess were right.
    if hmac.compare_digest(presented.encode(), settings.admin_key.encode()):
        return Principal("admin")
    if settings.demo_key and hmac.compare_digest(presented.encode(), settings.demo_key.encode()):
        return Principal("demo")
    return None


class TokenBucket:
    """Classic token bucket: ``rate`` tokens/second refill, at most ``capacity`` stored.

    Allows short bursts up to ``capacity`` while capping the long-run rate at ``rate``.
    """

    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.updated = time.monotonic()

    def take(self) -> float:
        """Consume one token. Returns 0 on success, else seconds until a token is available."""
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0
        return (1.0 - self.tokens) / self.rate

    def peek_empty(self) -> float:
        """Seconds until a token is available, without consuming one (0 if one is there)."""
        now = time.monotonic()
        tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        return 0.0 if tokens >= 1.0 else (1.0 - tokens) / self.rate


class RateLimiter:
    """One bucket per (key, class). Buckets live in memory: a restart resets them, and multiple
    replicas would each enforce the limit separately (stated in the limitations)."""

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], TokenBucket] = {}
        self._lock = threading.Lock()

    def _bucket(self, key: str, kind: str, rate: tuple[float, int]) -> TokenBucket:
        b = self._buckets.get((key, kind))
        if b is None:
            if len(self._buckets) > 100_000:
                # Bound memory under a flood of distinct client IPs.
                self._buckets.clear()
            b = self._buckets[(key, kind)] = TokenBucket(*rate)
        return b

    def take(self, key: str, kind: str, rate: tuple[float, int]) -> int:
        """0 if allowed, else whole seconds for Retry-After (at least 1)."""
        with self._lock:
            wait = self._bucket(key, kind, rate).take()
        return 0 if wait == 0 else max(1, math.ceil(wait))

    def blocked(self, key: str, kind: str, rate: tuple[float, int]) -> int:
        with self._lock:
            wait = self._bucket(key, kind, rate).peek_empty()
        return 0 if wait == 0 else max(1, math.ceil(wait))
