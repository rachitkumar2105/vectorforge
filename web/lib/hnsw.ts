// A small HNSW for the visualizer: the same algorithm as engine/vectorforge/index/hnsw.py
// (geometric layer assignment, heuristic neighbour selection, symmetric shrink, greedy
// descent with ef=1, best-first search on layer 0), on 2-D points, recording every step so
// the page can replay the search. Real logic, not a canned animation.

export type Point = { x: number; y: number };

export type Graph = {
  points: Point[];
  levels: number[];
  links: number[][][]; // links[node][layer] = neighbour ids
  entry: number;
  maxLevel: number;
  M: number;
};

export type TraceEvent =
  | { kind: "enter"; layer: number; node: number }
  | { kind: "visit"; layer: number; node: number; from: number }
  | { kind: "expand"; layer: number; node: number; frontier: number[]; best: number[] }
  | { kind: "result"; layer: 0; nodes: number[] };

type Cand = [distance: number, node: number];

/** Deterministic PRNG (mulberry32), so every visitor sees the same graph. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Clustered points in the unit square: clusters make the neighbour heuristic visible. */
export function makeDataset(n: number, seed: number): Point[] {
  const rand = mulberry32(seed);
  const centres = Array.from({ length: 7 }, () => ({ x: 0.12 + rand() * 0.76, y: 0.12 + rand() * 0.76 }));
  const pts: Point[] = [];
  for (let i = 0; i < n; i++) {
    if (rand() < 0.25) {
      pts.push({ x: 0.03 + rand() * 0.94, y: 0.03 + rand() * 0.94 });
      continue;
    }
    const c = centres[Math.floor(rand() * centres.length)]!;
    // Box-Muller for a Gaussian blob around the centre.
    const r = Math.sqrt(-2 * Math.log(1 - rand())) * 0.06;
    const t = 2 * Math.PI * rand();
    pts.push({ x: clamp(c.x + r * Math.cos(t)), y: clamp(c.y + r * Math.sin(t)) });
  }
  return pts;
}

const clamp = (v: number) => Math.min(0.98, Math.max(0.02, v));

const d2 = (a: Point, b: Point) => (a.x - b.x) ** 2 + (a.y - b.y) ** 2;

// Minimal binary heap keyed on distance. `sign` = 1 gives a min-heap, -1 a max-heap.
class Heap {
  private items: Cand[] = [];
  private readonly sign: 1 | -1;
  constructor(sign: 1 | -1) {
    this.sign = sign;
  }
  get size() {
    return this.items.length;
  }
  peek(): Cand | undefined {
    return this.items[0];
  }
  toArray(): Cand[] {
    return [...this.items];
  }
  push(c: Cand) {
    const a = this.items;
    a.push(c);
    let i = a.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (this.sign * (a[i]![0] - a[p]![0]) >= 0) break;
      [a[i], a[p]] = [a[p]!, a[i]!];
      i = p;
    }
  }
  pop(): Cand | undefined {
    const a = this.items;
    const top = a[0];
    const last = a.pop();
    if (a.length && last) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1;
        const r = l + 1;
        let m = i;
        if (l < a.length && this.sign * (a[l]![0] - a[m]![0]) < 0) m = l;
        if (r < a.length && this.sign * (a[r]![0] - a[m]![0]) < 0) m = r;
        if (m === i) break;
        [a[i], a[m]] = [a[m]!, a[i]!];
        i = m;
      }
    }
    return top;
  }
}

function searchLayer(
  g: Graph,
  q: Point,
  entries: number[],
  ef: number,
  layer: number,
  trace?: TraceEvent[],
): Cand[] {
  const visited = new Set(entries);
  const candidates = new Heap(1);
  const results = new Heap(-1);
  for (const e of entries) {
    const d = d2(q, g.points[e]!);
    candidates.push([d, e]);
    results.push([d, e]);
  }
  while (candidates.size) {
    const [dc, c] = candidates.pop()!;
    // Paper's stop rule: the closest unexpanded node is further than our worst result.
    if (dc > results.peek()![0]) break;
    trace?.push({
      kind: "expand",
      layer,
      node: c,
      frontier: candidates.toArray().map(([, n]) => n),
      best: results.toArray().map(([, n]) => n),
    });
    for (const n of g.links[c]![layer]!) {
      if (visited.has(n)) continue;
      visited.add(n);
      const d = d2(q, g.points[n]!);
      trace?.push({ kind: "visit", layer, node: n, from: c });
      if (results.size < ef || d < results.peek()![0]) {
        candidates.push([d, n]);
        results.push([d, n]);
        if (results.size > ef) results.pop();
      }
    }
  }
  return results.toArray().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
}

// Heuristic selection (paper Algorithm 4): keep a candidate only if it is closer to the base
// than to every neighbour already kept, so links spread out in different directions.
function selectNeighbours(g: Graph, ordered: Cand[], m: number): number[] {
  const kept: number[] = [];
  for (const [d, e] of ordered) {
    if (kept.length >= m) break;
    const pe = g.points[e]!;
    if (kept.every((s) => d < d2(pe, g.points[s]!))) kept.push(e);
  }
  return kept;
}

function shrink(g: Graph, e: number, layer: number, cap: number) {
  const pe = g.points[e]!;
  const current = g.links[e]![layer]!;
  const scored = current.map((n) => [d2(pe, g.points[n]!), n] as Cand).sort((a, b) => a[0] - b[0]);
  let keep = selectNeighbours(g, scored, cap);
  const keepSet = new Set(keep);
  // Drop edges in both directions, but never leave a node with no edge on this layer.
  const dropped = current.filter((n) => !keepSet.has(n));
  const orphans = dropped.filter((n) => g.links[n]![layer]!.length <= 1);
  keep = [...keep, ...orphans].slice(0, cap);
  const finalSet = new Set(keep);
  for (const n of current) {
    if (!finalSet.has(n)) {
      const back = g.links[n]![layer]!;
      back.splice(back.indexOf(e), 1);
    }
  }
  g.links[e]![layer] = keep;
}

export function buildGraph(
  points: Point[],
  opts: { M: number; efConstruction: number; seed: number },
): Graph {
  const rand = mulberry32(opts.seed);
  const mL = 1 / Math.log(opts.M);
  const g: Graph = { points, levels: [], links: [], entry: -1, maxLevel: -1, M: opts.M };
  points.forEach((q, label) => {
    const level = Math.floor(-Math.log(1 - rand()) * mL);
    g.levels.push(level);
    g.links.push(Array.from({ length: level + 1 }, () => []));
    if (g.entry < 0) {
      g.entry = label;
      g.maxLevel = level;
      return;
    }
    let ep = [g.entry];
    for (let layer = g.maxLevel; layer > level; layer--) ep = [searchLayer(g, q, ep, 1, layer)[0]![1]];
    for (let layer = Math.min(level, g.maxLevel); layer >= 0; layer--) {
      const found = searchLayer(g, q, ep, opts.efConstruction, layer);
      const chosen = selectNeighbours(g, found, opts.M);
      g.links[label]![layer] = [...chosen];
      const cap = layer === 0 ? 2 * opts.M : opts.M;
      for (const e of chosen) {
        g.links[e]![layer]!.push(label);
        if (g.links[e]![layer]!.length > cap) shrink(g, e, layer, cap);
      }
      ep = found.map(([, n]) => n);
    }
    if (level > g.maxLevel) {
      g.entry = label;
      g.maxLevel = level;
    }
  });
  return g;
}

/** Search with a full trace: greedy ef=1 descent, then ef-wide search on layer 0. */
export function searchTrace(g: Graph, q: Point, k: number, ef: number) {
  const events: TraceEvent[] = [];
  if (g.entry < 0) {
    events.push({ kind: "result", layer: 0, nodes: [] });
    return { events, results: [] as number[] };
  }
  let ep = [g.entry];
  for (let layer = g.maxLevel; layer >= 0; layer--) {
    events.push({ kind: "enter", layer, node: ep[0]! });
    const width = layer === 0 ? Math.max(ef, k) : 1;
    const found = searchLayer(g, q, ep, width, layer, events);
    if (layer === 0) {
      const results = found.slice(0, k).map(([, n]) => n);
      events.push({ kind: "result", layer: 0, nodes: results });
      return { events, results };
    }
    ep = [found[0]![1]];
  }
  /* c8 ignore next */
  return { events, results: [] as number[] };
}

export function exactKnn(points: Point[], q: Point, k: number): number[] {
  return points
    .map((p, i) => [d2(q, p), i] as Cand)
    .sort((a, b) => a[0] - b[0] || a[1] - b[1])
    .slice(0, k)
    .map(([, i]) => i);
}
