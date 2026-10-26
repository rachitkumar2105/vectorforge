# Twenty hard questions about VectorForge

Answers by the author. Numbers are from `bench/results/` (SIFT1M first 200,000 base vectors,
1,000 official queries, single thread, one query at a time) unless stated.

## 1. Why HNSW over IVF here, and when is the reverse true?

At equal recall HNSW does far less work per query. On SIFT-200k, HNSW reaches recall@10 0.9875 at
539 q/s (ef_search=80); IVF needs nprobe=32 for 0.9876 and manages 149 q/s. HNSW wins because its
cost grows roughly with log n hops times degree, while IVF scans whole cells, about n·nprobe/nlist
vectors. IVF wins when memory matters more than latency (no graph, just centroids and lists, and
it composes with quantization: our int8 IVF stores vectors in a quarter of the space), when the
index must be built fast (IVF trains in seconds, Python HNSW took 1,092 s here), when data is
appended in bulk, and on GPUs where scanning contiguous lists is cheap.

## 2. Walk me through HNSW insertion.

Draw a level `floor(-ln U · mL)` with `mL = 1/ln M`, so each layer holds about 1/M of the one below.
From the entry point at the top layer, greedily descend with ef=1 to the new node's level. Then on
each layer from its level down to 0: run `search_layer` with `ef_construction` to get candidates,
pick M neighbours with the heuristic, add links both ways, and if a neighbour now exceeds its cap
(2M on layer 0, M above) re-select its neighbours with the same heuristic. The candidates found on
one layer seed the next. If the new level beats the max level, the node becomes the entry point.

## 3. Explain the neighbour selection heuristic. Why is plain top-M worse?

Walk candidates nearest first; keep a candidate only if it is closer to the base node than to any
neighbour already kept. If it is closer to a kept neighbour, the base can reach it through that
neighbour, so a direct edge is redundant; the slot goes to an edge pointing somewhere new. Plain
top-M in clustered data spends all M edges inside the local cluster and leaves no road out, so
greedy search gets trapped. In our 10k Gaussian test the heuristic gave recall@10 0.977 vs 0.9515
for top-M at ef=50; the gap is larger on clustered data. The heuristic costs build time (43 s vs
28.5 s there) because it computes candidate-to-candidate distances.

## 4. Why is deletion tombstone-only?

A node is a bridge: its neighbours and whole regions reach each other through it. Removing it
can disconnect layer 0 or strand an upper layer with no way down, and the insertion algorithm
never repairs that. Proper hard delete needs local rewiring of every former neighbour plus a new
entry point if needed. Tombstones keep the graph intact: searches walk through deleted nodes and
just never return them. The cost is wasted hops, fixed by periodic rebuilds.

## 5. How does ef_search trade recall for latency?

It is the size of the result heap on layer 0, so it bounds how far the best-first search keeps
expanding. Measured on SIFT-200k: ef=10 gives recall@10 0.764 at 2,195 q/s; ef=40 gives 0.954 at
976 q/s; ef=120 gives 0.9955 at 316 q/s; ef=400 gives 0.9999 at 143 q/s. Recall saturates while
cost keeps growing roughly linearly in ef.

## 6. What does filtered search do to graph connectivity and recall?

We filter during traversal: rejected nodes are still expanded, so the walk can pass through them,
but they never enter the result set. With a permissive filter that costs little. With a selective
filter the matching nodes are a sparse subgraph; the search must wade through many non-matching
nodes and can stop in a region with no matches, so recall drops and latency rises. Below 5 percent
selectivity the collection skips the graph and scans just the matching vectors exactly.

## 7. Why is your implementation slower than FAISS, and by how much?

On SIFT-200k at the same recall, FAISS HNSW is TODO-NUM× faster on the same core. Each hop in
our code is Python: heap pushes, set lookups, and a NumPy call on a handful of vectors, where
call overhead dwarfs the arithmetic. FAISS runs that loop in C++, with SIMD distance kernels over
contiguous memory and prefetching. Same algorithm, same parameters; the constant factor is the
interpreter.

## 8. How does the WAL survive a torn write?

Each record is `length | crc32 | payload`. Replay reads records in order and stops at the first one
whose header is short, whose payload is short, whose length is out of range, or whose CRC fails,
then truncates the file there. A write is acknowledged only after fsync, so every acknowledged
record lies before any torn bytes: truncation can only drop data nobody was told was saved. The
crash test kills the writer mid-stream (with chunked writes to make torn tails likely) and checks
every acknowledged vector comes back byte for byte.

## 9. What breaks first at 100 million vectors?

Memory. 100M × 128 float32 is 51 GB of vectors before the graph; our Python list-of-lists graph
adds tens of bytes per edge, so hundreds of GB. Next, build time: at the measured ~5.5 ms per insert (200k in
1,092 s) a single thread needs about a week, and per-insert cost grows with log n. Then recovery: replaying a large WAL and loading a JSON state snapshot are
O(n) at startup. Fixes in order: compact int32 adjacency arrays, product quantization, a native
build, sharding.

## 10. Why fsync once per batch rather than per vector?

Group commit. fsync dominates write latency; one per request amortises it across up to 1,000
vectors while keeping the contract that a request is acknowledged only when all of it is durable.

## 11. What is the commit point of a checkpoint?

The atomic rename of `manifest.json`. New snapshot files are written under new names first; the
manifest swap switches state; only then are old files deleted and the WAL truncated. A crash
before the rename leaves the old manifest with the full WAL; after it, the new snapshot plus WAL
records that replay skips by LSN.

## 12. Why keep links symmetric when hnswlib does not?

It makes "every edge can be walked back" an invariant the tests can check, and it prevents
dangling one-way edges into regions that cannot link back. The cost is that pruning removes the
reverse edge too, so a node can lose degree; the orphan guard keeps at least one link per layer.

## 13. Why is IVF recall exactly 1.0 at nprobe == nlist?

Every list is scanned, so every vector is compared exactly: it degenerates to brute force. The
test asserts it, which also checks that every vector landed in exactly one list.

## 14. What does int8 quantization cost and save?

Per-dimension min/max, 256 levels: 4.00× smaller vector storage (12.8 MB to 3.2 MB on the 50k
gate set), with reconstruction error at most step/2 per dimension (measured max 0.05092 equals the
bound). Recall@10 at full probe fell from 1.0000 to 0.9645 on that set, because distances are
computed on reconstructed vectors, so near ties reorder.

## 15. How do you know the benchmark is honest?

Ground truth is our exact flat index, which matches SIFT's published ground truth exactly on a
sample. Both engines run on the same machine, same subset, same parameters, one thread, one query
at a time. Hardware, versions and the git commit are written into the result files, and one
command regenerates them. The site reads those files; nothing is typed in by hand.

## 16. Why single-threaded FAISS?

To compare per-query latency like for like with a single-threaded Python engine. Multi-threaded,
batched FAISS would be much faster again; the limitations section says so.

## 17. Why is layer 0's degree 2M?

Layer 0 holds every element and does the precise search, so it needs more connectivity; upper
layers only route. The paper found M_max0 = 2M a good default; higher wastes memory and hops.

## 18. Why mL = 1/ln(M)?

It makes P(level ≥ l) = M^-l, so each layer is about M times smaller. With roughly M neighbours per
node, each layer then shrinks the search space by about the same factor as one hop covers, which
gives logarithmic hop counts. The test checks that about 1/M of nodes reach level 1.

## 19. How is the API protected?

An admin key and a read-only demo key scoped to one collection, compared in constant time; the
service refuses to start without an admin key of at least 32 characters. Token buckets per key for
search and writes, plus a failed-auth budget per address that never blocks a valid key. Body size
and batch caps, NaN/Infinity rejected, errors that never echo input, logs without keys, vectors,
metadata or ids. The site's demo route holds the key server-side and is itself rate limited.

## 20. What would you build next?

Compact numpy adjacency arrays and a vectorised inner loop (or a small C extension) for a large
constant-factor speedup; an inverted metadata index for selective filters; background rebuilds to
reclaim tombstones; IVF retraining; and replication of the WAL to a follower for failover.
