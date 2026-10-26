import { buildGraph, makeDataset } from "@/lib/hnsw";

// Server-rendered background: a real HNSW graph (same builder as the visualizer), drawn as plain
// SVG. Edges draw once on load and each layer drifts slowly, all in CSS on stroke and transform,
// so it costs no JavaScript and never delays first paint.
const W = 1600;
const H = 900;
// 70 nodes: enough to read as a graph, few enough to keep the DOM and layout cost low on phones.
const points = makeDataset(70, 2024);
const graph = buildGraph(points, { M: 4, efConstruction: 24, seed: 11 });

type Edge = { a: number; b: number };

function edgesOn(layer: number): Edge[] {
  const out: Edge[] = [];
  graph.links.forEach((layers, a) => {
    for (const b of layers[layer] ?? []) if (a < b) out.push({ a, b });
  });
  return out;
}

const layerStyle = [
  { stroke: "#1b252c", node: "#2a3842", r: 2.2 },
  { stroke: "#1e4f48", node: "#1e7f6f", r: 3 },
  { stroke: "#2a9c88", node: "#35e0c2", r: 4 },
];

export function HeroGraph() {
  const layers = [0, 1, 2].filter((l) => l <= graph.maxLevel);
  return (
    <svg
      className="pointer-events-none absolute inset-0 h-full w-full"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      {layers.map((layer) => {
        const s = layerStyle[layer]!;
        const edges = edgesOn(layer);
        return (
          <g key={layer} className={`hero-layer-${layer}`}>
            {edges.map((e, i) => {
              const p = points[e.a]!;
              const q = points[e.b]!;
              return (
                <line
                  key={i}
                  className={`hero-edge hero-delay-${i % 6}`}
                  x1={p.x * W}
                  y1={p.y * H}
                  x2={q.x * W}
                  y2={q.y * H}
                  stroke={s.stroke}
                  strokeWidth={layer === 0 ? 1 : 1.25}
                  pathLength={1}
                />
              );
            })}
            {graph.levels.map((lv, i) =>
              lv >= layer ? (
                <circle key={i} cx={points[i]!.x * W} cy={points[i]!.y * H} r={s.r} fill={s.node} />
              ) : null,
            )}
          </g>
        );
      })}
    </svg>
  );
}
