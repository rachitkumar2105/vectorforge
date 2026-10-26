"""Evaluation helpers shared by tests and the benchmark harness."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt


def recall_at_k(found: npt.ArrayLike, truth: npt.ArrayLike, k: int) -> float:
    """Mean fraction of the true top-k that appears in the returned top-k.

    ``found`` and ``truth`` are ``(n_queries, >= k)`` label matrices. Rows of ``found`` may be
    padded with -1 when an index returned fewer than k results.
    """
    f = np.asarray(found)[:, :k]
    t = np.asarray(truth)[:, :k]
    hits = sum(len(set(fr.tolist()) & set(tr.tolist())) for fr, tr in zip(f, t, strict=True))
    return hits / float(t.shape[0] * k)
