"""Hierarchical Navigable Small World graph, written by hand.

Reference: Malkov & Yashunin, "Efficient and robust approximate nearest neighbor search using
Hierarchical Navigable Small World graphs" (2016/2018). Algorithm numbers below refer to it.

The picture to keep in mind:

* Every element lives on layer 0. Each element also lives on layers 1..level, where ``level`` is
  drawn from a geometric-like distribution, so each layer holds roughly 1/M of the layer below.
* Upper layers are sparse "express lanes": long hops that get a search near the target quickly.
  Layer 0 is dense and does the precise local search.
* A search greedily walks down: on each upper layer it moves to the closest node it can find
  (``ef=1``), then on layer 0 it runs a wider best-first search (``ef_search``).

Storage layout (chosen for explainability, not raw speed):

* ``self._vectors``: one contiguous float32 matrix, row = label.
* ``self._links[label][layer]``: a Python list of neighbour labels on that layer.
"""

from __future__ import annotations

import heapq
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from vectorforge.core.distance import Metric, normalize_rows
from vectorforge.core.store import GrowableMatrix
from vectorforge.index.base import Allow, Index, LabelArray, SearchResult, empty_result

# (distance, label) pairs. Python's heapq is a min-heap; the max-heap of results stores
# (-distance, label) so that the *furthest* result sits at the top and can be evicted in O(log n).
Candidate = tuple[float, int]


class HNSWIndex(Index):
    kind = "hnsw"

    def __init__(
        self,
        dim: int,
        metric: Metric = "l2",
        *,
        M: int = 16,
        ef_construction: int = 200,
        ef_search: int = 50,
        heuristic: bool = True,
        keep_pruned: bool = False,
        seed: int = 0,
    ) -> None:
        super().__init__(dim, metric)
        if M < 2:
            raise ValueError("M must be at least 2")
        if ef_construction < 1 or ef_search < 1:
            raise ValueError("ef_construction and ef_search must be positive")
        self.M = M
        # Layer 0 holds every element and does the fine-grained search, so it gets twice the
        # degree budget. The paper found M_max0 = 2M to be a good default.
        self.M_max0 = 2 * M
        # mL = 1/ln(M) makes P(level >= l) = M^-l: each layer is ~M times smaller than the one
        # below, which is what gives the logarithmic number of hops.
        self.mL = 1.0 / math.log(M)
        self.ef_construction = ef_construction
        self.ef_search = ef_search
        self.heuristic = heuristic
        self.keep_pruned = keep_pruned
        self.seed = seed
        self._rng = np.random.default_rng(seed)

        self._vectors = GrowableMatrix(dim, np.float32)
        self._levels: list[int] = []
        self._links: list[list[list[int]]] = []
        self.entry_point: int | None = None
        self.max_level = -1
        self._dist_fn = self._make_distance_fn()

    # -- distances --------------------------------------------------------------------------
    def _make_distance_fn(
        self,
    ) -> Callable[[npt.NDArray[np.float32], list[int]], list[float]]:
        """Return dist(q, labels) -> list of floats, specialised per metric.

        This is the hot path: every hop of every search calls it once with a batch of
        neighbours. It skips the validation in ``core.distance`` (inputs were validated on entry)
        and returns a Python list because the caller immediately pushes items onto heaps.
        """
        if self.metric == "l2":

            def l2(q: npt.NDArray[np.float32], labels: list[int]) -> list[float]:
                diff = self._vectors.view()[labels] - q
                out: list[float] = np.einsum("ij,ij->i", diff, diff).tolist()
                return out

            return l2
        # Cosine vectors are stored unit-normalised (see _prepare), so cosine distance is
        # 1 - dot, and inner-product distance is -dot. Both reduce to one matrix-vector product.
        offset = 1.0 if self.metric == "cosine" else 0.0

        def dot(q: npt.NDArray[np.float32], labels: list[int]) -> list[float]:
            sims = self._vectors.view()[labels] @ q
            out: list[float] = (offset - sims).tolist()
            return out

        return dot

    def _prepare(self, vectors: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
        return normalize_rows(vectors) if self.metric == "cosine" else vectors

    def _pairwise(self, labels: list[int]) -> npt.NDArray[np.float32]:
        """Distance matrix among the given labels, in this index's metric."""
        sub = self._vectors.view()[labels]
        gram = sub @ sub.T
        if self.metric == "l2":
            sq = np.diag(gram)
            out: npt.NDArray[np.float32] = sq[:, None] + sq[None, :] - 2.0 * gram
            return out
        offset = 1.0 if self.metric == "cosine" else 0.0
        dots: npt.NDArray[np.float32] = (offset - gram).astype(np.float32)
        return dots

    # -- public accessors (used by tests, stats and the visualizer export) -------------------
    def __len__(self) -> int:
        return len(self._levels)

    def level_of(self, label: int) -> int:
        return self._levels[label]

    def neighbours(self, label: int, layer: int) -> list[int]:
        return self._links[label][layer]

    def neighbours_of(self, label: int) -> list[list[int]]:
        return self._links[label]

    def layer_size(self, layer: int) -> int:
        return sum(1 for lv in self._levels if lv >= layer)

    def vector(self, label: int) -> npt.NDArray[np.float32]:
        return np.asarray(self._vectors.row(label), dtype=np.float32)

    # -- level assignment --------------------------------------------------------------------
    def _random_level(self) -> int:
        # level = floor(-ln(U) * mL), U ~ uniform(0, 1]. Using 1 - random() keeps U away from 0,
        # where ln would be -inf.
        u = 1.0 - float(self._rng.random())
        return int(math.floor(-math.log(u) * self.mL))

    # -- Algorithm 2: SEARCH-LAYER -----------------------------------------------------------
    def _search_layer(
        self,
        q: npt.NDArray[np.float32],
        entry_points: list[int],
        ef: int,
        layer: int,
        admissible: Allow | None = None,
    ) -> list[Candidate]:
        """Best-first search on one layer. Returns up to ``ef`` (distance, label), nearest first.

        ``candidates`` is a min-heap: the closest unexpanded node is expanded next.
        ``results`` is a max-heap (negated distances) of the best ``ef`` admissible nodes found.

        When ``admissible`` is given (tombstones, metadata filters), rejected nodes are still
        expanded, so the walk can pass *through* them, but they never enter ``results``. That is
        the "filter during traversal" behaviour: the graph stays connected even when most nodes
        are filtered out.
        """
        visited = set(entry_points)
        ep_d = self._dist_fn(q, entry_points)
        candidates: list[Candidate] = list(zip(ep_d, entry_points, strict=True))
        heapq.heapify(candidates)
        results: list[Candidate] = [
            (-d, e) for d, e in candidates if admissible is None or admissible(e)
        ]
        heapq.heapify(results)
        while len(results) > ef:
            heapq.heappop(results)

        while candidates:
            d_c, c = heapq.heappop(candidates)
            worst = -results[0][0] if results else math.inf
            # Stop when the closest unexpanded candidate is further than the worst kept result:
            # nothing reachable through it can improve the result set (the paper's condition).
            # With a filter, keep going until the result set is full, otherwise a run of
            # rejected nodes near the query would end the search with too few results.
            if d_c > worst and (admissible is None or len(results) >= ef):
                break
            fresh = [n for n in self._links[c][layer] if n not in visited]
            if not fresh:
                continue
            visited.update(fresh)
            for d, n in zip(self._dist_fn(q, fresh), fresh, strict=True):
                worst = -results[0][0] if results else math.inf
                if len(results) < ef or d < worst:
                    heapq.heappush(candidates, (d, n))
                    if admissible is None or admissible(n):
                        heapq.heappush(results, (-d, n))
                        if len(results) > ef:
                            heapq.heappop(results)
        return sorted((-nd, n) for nd, n in results)

    # -- Algorithms 3 and 4: neighbour selection --------------------------------------------
    def _select_neighbours(self, candidates: list[Candidate], m: int) -> list[int]:
        """Choose at most ``m`` neighbours from (distance-to-base, label) pairs."""
        ordered = sorted(candidates)
        if not self.heuristic:
            # Algorithm 3: plain top-m by distance. Simple, but in clustered data all m links
            # can point into the same cluster, leaving no edge that leads out of it.
            return [label for _, label in ordered[:m]]
        return self._select_heuristic(ordered, m)

    def _select_heuristic(self, ordered: list[Candidate], m: int) -> list[int]:
        """Algorithm 4: keep a candidate only if it is closer to the base element than to every
        neighbour already selected.

        Why: if candidate e is closer to an already-selected neighbour r than to the base, the
        base can reach e cheaply via r, so a direct edge to e is redundant. Skipping it frees the
        slot for an edge in a *different direction*, which is what keeps the graph navigable
        across clusters. This is a relative neighbourhood graph approximation.
        """
        labels = [e for _, e in ordered]
        d_base = [d for d, _ in ordered]
        # One pairwise matrix among the candidates replaces a distance call per candidate.
        # c is at most ef_construction (or M_max0 + 1 when shrinking), so c x c stays small.
        pair = self._pairwise(labels)
        sel_idx: list[int] = []
        discarded: list[int] = []
        for i, e in enumerate(labels):
            if len(sel_idx) >= m:
                break
            if sel_idx and bool((pair[i, sel_idx] < d_base[i]).any()):
                discarded.append(e)
                continue
            sel_idx.append(i)
        selected = [labels[i] for i in sel_idx]
        if self.keep_pruned:
            # Optional (paper's keepPrunedConnections): top up to m with the nearest discarded,
            # trading a little diversity for a fixed degree.
            selected.extend(discarded[: m - len(selected)])
        return selected

    # -- Algorithm 1: INSERT -----------------------------------------------------------------
    def add(self, vectors: npt.ArrayLike) -> LabelArray:
        arr = self._prepare(self._check_vectors(vectors))
        start = len(self)
        for row in arr:
            self._insert(row)
        return np.arange(start, start + arr.shape[0], dtype=np.int64)

    def _insert(self, q: npt.NDArray[np.float32]) -> int:
        label = self._vectors.append(q[None, :])
        level = self._random_level()
        self._levels.append(level)
        self._links.append([[] for _ in range(level + 1)])

        if self.entry_point is None:
            self.entry_point, self.max_level = label, level
            return label

        # Phase 1: greedy descent with ef=1 through the layers above the new element's level.
        # These layers only steer us to a good starting point; no links are made there.
        ep = [self.entry_point]
        for layer in range(self.max_level, level, -1):
            ep = [self._search_layer(q, ep, 1, layer)[0][1]]

        # Phase 2: on each layer the new element belongs to, find ef_construction candidates,
        # pick neighbours, link both ways, and repair any neighbour that now has too many links.
        for layer in range(min(level, self.max_level), -1, -1):
            found = self._search_layer(q, ep, self.ef_construction, layer)
            chosen = self._select_neighbours(found, self.M)
            self._links[label][layer] = list(chosen)
            cap = self.M_max0 if layer == 0 else self.M
            for e in chosen:
                self._links[e][layer].append(label)
                if len(self._links[e][layer]) > cap:
                    self._shrink(e, layer, cap)
            # The candidates found here are good entry points for the next layer down.
            ep = [n for _, n in found]

        if level > self.max_level:
            # The entry point must always sit on the top layer, otherwise searches would start
            # below some of the express lanes.
            self.entry_point, self.max_level = label, level
        return label

    def _shrink(self, e: int, layer: int, cap: int) -> None:
        """Re-select e's neighbours with the same rule used at insertion, then drop the edges it
        no longer keeps *in both directions*.

        Keeping links symmetric means "u lists v" always implies "v lists u", so any edge a
        search follows can also be walked back. hnswlib leaves one-way edges here; we trade a
        few edges for an invariant that is easy to check and reason about.
        """
        current = self._links[e][layer]
        scored = list(zip(self._dist_fn(self.vector(e), current), current, strict=True))
        keep = self._select_neighbours(scored, cap)
        keep_set = set(keep)
        dropped = [n for n in current if n not in keep_set]
        # Symmetric removal could leave a node with no edges at all on this layer, making it
        # unreachable. Such nodes keep their edge to e; room is made by evicting e's furthest
        # kept neighbours that have edges to spare.
        orphans = [n for n in dropped if len(self._links[n][layer]) <= 1]
        if orphans:
            orphan_set = set(orphans)
            dropped = [n for n in dropped if n not in orphan_set]
            dist = dict((n, d) for d, n in scored)
            for n in sorted(keep, key=lambda x: -dist[x]):
                if len(keep) + len(orphans) <= cap:
                    break
                if len(self._links[n][layer]) > 1:
                    keep.remove(n)
                    dropped.append(n)
            keep.extend(orphans)
        for n in dropped:
            self._links[n][layer].remove(e)
        self._links[e][layer] = keep

    # -- deletion ----------------------------------------------------------------------------
    def delete(self, label: int) -> None:
        """Tombstone only. The node keeps its vector and every edge; searches walk through it
        but never return it.

        Why not remove it from the graph: the node is a bridge. Its neighbours reach each other
        (and whole regions of the graph) through it. Cutting its edges can disconnect parts of
        layer 0 or leave an upper-layer region with no way down, and nothing in the insert
        algorithm repairs that. Correct hard deletion needs a local re-wiring step (reconnect
        each former neighbour via the selection heuristic) and, if the node is the entry point,
        a new entry point on the top layer. That is expensive and easy to get subtly wrong, so
        the standard practice (hnswlib, FAISS) is tombstones plus periodic rebuilds.
        """
        super().delete(label)

    # -- Algorithm 5: K-NN-SEARCH ------------------------------------------------------------
    def search(
        self, query: npt.ArrayLike, k: int, *, allow: Allow | None = None, **params: Any
    ) -> SearchResult:
        q = self._check_query(query, k)
        requested = params.get("ef_search")
        ef = self.ef_search if requested is None else int(requested)
        if ef < 1:
            raise ValueError("ef_search must be positive")
        if self.entry_point is None:
            return empty_result()
        q = self._prepare(q[None, :])[0]

        admissible: Allow | None = None
        if self._deleted or allow is not None:
            deleted = self._deleted

            def admissible(label: int) -> bool:
                return label not in deleted and (allow is None or allow(label))

        ep = [self.entry_point]
        for layer in range(self.max_level, 0, -1):
            ep = [self._search_layer(q, ep, 1, layer)[0][1]]
        # ef below k could never return k results, so the effective breadth is max(ef, k).
        found = self._search_layer(q, ep, max(ef, k), 0, admissible)[:k]
        if not found:
            return empty_result()
        return SearchResult(
            np.array([n for _, n in found], dtype=np.int64),
            np.array([d for d, _ in found], dtype=np.float32),
        )

    def search_trace(self, query: npt.ArrayLike, ef: int) -> list[dict[str, Any]]:
        """Per-layer record of what a search touched (used to export visualizer fixtures)."""
        q = self._prepare(self._check_query(query, 1)[None, :])[0]
        if self.entry_point is None:
            return []
        trace = []
        ep = [self.entry_point]
        for layer in range(self.max_level, -1, -1):
            width = ef if layer == 0 else 1
            found = self._search_layer(q, ep, width, layer)
            trace.append({"layer": layer, "entry": ep, "found": [n for _, n in found]})
            ep = [found[0][1]]
        return trace

    # -- stats and persistence ---------------------------------------------------------------
    def edge_count(self) -> int:
        return sum(len(nbrs) for node in self._links for nbrs in node)

    def memory_bytes(self) -> int:
        # Compact-layout size: float32 vectors + 4 bytes per directed edge + one level byte per
        # node. Python's list-of-lists representation uses several times more than this; the
        # benchmark reports measured process RSS separately so neither number hides the other.
        return self._vectors.nbytes() + 4 * self.edge_count() + len(self)

    def stats(self) -> dict[str, Any]:
        s = super().stats()
        s.update(
            {
                "params": {
                    "M": self.M,
                    "ef_construction": self.ef_construction,
                    "ef_search": self.ef_search,
                    "heuristic": self.heuristic,
                },
                "max_level": self.max_level,
                "edges": self.edge_count(),
                "layer_sizes": [self.layer_size(lv) for lv in range(self.max_level + 1)],
            }
        )
        return s

    def save(self, path: Path, include_vectors: bool = True) -> None:
        """Graph as CSR-style int32 arrays: for each node, for each of its layers, the count
        followed by the neighbour labels. Compact, and loads without pickling.

        A collection passes ``include_vectors=False``: its segments already hold the vectors,
        and a second copy would double checkpoint size for nothing."""
        flat: list[int] = []
        offsets = np.zeros(len(self) + 1, dtype=np.int64)
        for node, layers in enumerate(self._links):
            for nbrs in layers:
                flat.append(len(nbrs))
                flat.extend(nbrs)
            offsets[node + 1] = len(flat)
        self._write_header(
            path,
            {
                "M": self.M,
                "ef_construction": self.ef_construction,
                "ef_search": self.ef_search,
                "heuristic": self.heuristic,
                "keep_pruned": self.keep_pruned,
                "seed": self.seed,
                "entry_point": self.entry_point,
                "max_level": self.max_level,
                "rng_state": self._rng.bit_generator.state,
            },
        )
        if include_vectors:
            np.save(path / "vectors.npy", np.asarray(self._vectors.view(), dtype=np.float32))
        np.save(path / "levels.npy", np.array(self._levels, dtype=np.int16))
        np.save(path / "links.npy", np.array(flat, dtype=np.int32))
        np.save(path / "offsets.npy", offsets)

    @classmethod
    def load(cls, path: Path, vectors: npt.NDArray[np.float32] | None = None) -> HNSWIndex:
        """Load a saved graph. ``vectors`` lets the collection supply rows from its segments
        instead of the copy saved alongside the graph."""
        h = cls._read_header(path, cls.kind)
        index = cls(
            h["dim"],
            h["metric"],
            M=h["M"],
            ef_construction=h["ef_construction"],
            ef_search=h["ef_search"],
            heuristic=h["heuristic"],
            keep_pruned=h["keep_pruned"],
            seed=h["seed"],
        )
        index._rng.bit_generator.state = h["rng_state"]
        levels = np.load(path / "levels.npy").tolist()
        flat = np.load(path / "links.npy").tolist()
        offsets = np.load(path / "offsets.npy").tolist()
        if vectors is not None:
            # Raw vectors from segments: apply the same preparation as add() (cosine -> unit).
            if len(vectors) < len(levels):
                raise ValueError("vector store is shorter than the saved graph")
            vecs = index._prepare(np.asarray(vectors[: len(levels)], dtype=np.float32))
        else:
            vecs = np.load(path / "vectors.npy")
        if len(levels):
            index._vectors.append(np.asarray(vecs, dtype=np.float32))
        index._levels = levels
        for node, level in enumerate(levels):
            pos = offsets[node]
            layers = []
            for _ in range(level + 1):
                count = flat[pos]
                layers.append(flat[pos + 1 : pos + 1 + count])
                pos += 1 + count
            index._links.append(layers)
        index.entry_point = h["entry_point"]
        index.max_level = h["max_level"]
        index._read_deleted(path)
        return index

    def export_graph(self) -> dict[str, Any]:
        """JSON-friendly dump for the site's visualizer fixture."""
        return {
            "levels": self._levels,
            "links": self._links,
            "entry_point": self.entry_point,
            "max_level": self.max_level,
            "params": json.loads(json.dumps(self.stats()["params"])),
        }
