"""Structured logs and a hand-written Prometheus text exposition.

Logging rule (S19): log the *shape* of a request (method, route template, status, latency, caller
role), never its contents. Route templates (``/collections/{name}/vectors/{vector_id}``) are logged
instead of raw paths because raw paths carry vector ids.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from pathlib import Path
from typing import Any

BUCKETS = (0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        out.update(getattr(record, "fields", {}))
        return json.dumps(out, separators=(",", ":"))


def configure_logging() -> None:
    root = logging.getLogger("vectorforge")
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.setLevel(logging.INFO)


def log_event(logger: logging.Logger, msg: str, **fields: Any) -> None:
    logger.info(msg, extra={"fields": fields})


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _labels(**labels: str) -> str:
    return "{" + ",".join(f'{k}="{_escape(v)}"' for k, v in labels.items()) + "}"


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._hist: dict[str, list[int]] = defaultdict(lambda: [0] * len(BUCKETS))
        self._hist_sum: dict[str, float] = defaultdict(float)
        self._hist_count: dict[str, int] = defaultdict(int)

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            self._requests[(method, route, status)] += 1
            counts = self._hist[route]
            for i, bound in enumerate(BUCKETS):
                if seconds <= bound:
                    counts[i] += 1
            self._hist_sum[route] += seconds
            self._hist_count[route] += 1

    def render(self, index_sizes: dict[str, tuple[int, int]], bench_summary: Path | None) -> str:
        lines = [
            "# HELP vectorforge_requests_total HTTP requests by method, route and status.",
            "# TYPE vectorforge_requests_total counter",
        ]
        with self._lock:
            for (method, route, status), n in sorted(self._requests.items()):
                lbl = _labels(method=method, route=route, status=str(status))
                lines.append(f"vectorforge_requests_total{lbl} {n}")
            lines += [
                "# HELP vectorforge_request_duration_seconds Request latency.",
                "# TYPE vectorforge_request_duration_seconds histogram",
            ]
            for route in sorted(self._hist):
                for bound, n in zip(BUCKETS, self._hist[route], strict=True):
                    lbl = _labels(route=route, le=repr(bound))
                    lines.append(f"vectorforge_request_duration_seconds_bucket{lbl} {n}")
                total = self._hist_count[route]
                lbl = _labels(route=route, le="+Inf")
                lines.append(f"vectorforge_request_duration_seconds_bucket{lbl} {total}")
                lines.append(
                    f"vectorforge_request_duration_seconds_sum{_labels(route=route)} "
                    f"{self._hist_sum[route]:.6f}"
                )
                lines.append(
                    f"vectorforge_request_duration_seconds_count{_labels(route=route)} {total}"
                )
        lines += [
            "# HELP vectorforge_index_vectors Live vectors per collection.",
            "# TYPE vectorforge_index_vectors gauge",
        ]
        for name, (count, _) in sorted(index_sizes.items()):
            lines.append(f"vectorforge_index_vectors{_labels(collection=name)} {count}")
        lines += [
            "# HELP vectorforge_index_deleted Tombstoned vectors per collection.",
            "# TYPE vectorforge_index_deleted gauge",
        ]
        for name, (_, deleted) in sorted(index_sizes.items()):
            lines.append(f"vectorforge_index_deleted{_labels(collection=name)} {deleted}")
        lines += _bench_lines(bench_summary)
        return "\n".join(lines) + "\n"


def _bench_lines(path: Path | None) -> list[str]:
    """Recall of the last benchmark run, read from bench/results/summary.json if configured."""
    if path is None or not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = [
            (str(r["dataset"]), str(r["index"]), float(r["recall_at_10"]))
            for r in data.get("headline", [])
        ]
    except (ValueError, KeyError, TypeError):
        return []
    lines = [
        "# HELP vectorforge_benchmark_recall_at_10 Recall@10 from the last benchmark run.",
        "# TYPE vectorforge_benchmark_recall_at_10 gauge",
    ]
    for dataset, index, recall in rows:
        lines.append(
            f"vectorforge_benchmark_recall_at_10{_labels(dataset=dataset, index=index)} {recall}"
        )
    return lines
