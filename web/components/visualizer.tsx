"use client";

import { motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { IconEnd, IconPause, IconPlay, IconReset, IconShuffle, IconStep } from "@/components/icons";
import { buildGraph, exactKnn, makeDataset, mulberry32, searchTrace, type Graph, type Point, type TraceEvent } from "@/lib/hnsw";
import { useMediaQuery } from "@/lib/use-media-query";

const K = 5;
const TICK_MS = 40;
const TARGET_TICKS = 110; // whole playback lands in roughly 4.5 s whatever the ef

// -- replaying the trace ---------------------------------------------------------------------

type Frame = {
  layer: number;
  current: number | null;
  frontier: Set<number>;
  best: Set<number>;
  visited: Map<number, Set<number>>; // layer -> nodes whose distance was computed
  hops: { layer: number; from: number; to: number }[];
  entries: { layer: number; node: number }[];
  results: number[] | null;
  distanceCalls: number;
  expansions: number;
};

function replay(events: TraceEvent[], upto: number): Frame {
  const f: Frame = {
    layer: -1,
    current: null,
    frontier: new Set(),
    best: new Set(),
    visited: new Map(),
    hops: [],
    entries: [],
    results: null,
    distanceCalls: 0,
    expansions: 0,
  };
  for (let i = 0; i <= upto && i < events.length; i++) {
    const e = events[i]!;
    if (e.kind === "enter") {
      f.layer = e.layer;
      f.entries.push({ layer: e.layer, node: e.node });
      f.visited.set(e.layer, new Set([e.node]));
      f.current = e.node;
      f.frontier = new Set();
      f.best = new Set([e.node]);
      f.distanceCalls += 1;
    } else if (e.kind === "visit") {
      f.visited.get(e.layer)?.add(e.node);
      f.hops.push({ layer: e.layer, from: e.from, to: e.node });
      f.distanceCalls += 1;
    } else if (e.kind === "expand") {
      f.current = e.node;
      f.frontier = new Set(e.frontier);
      f.best = new Set(e.best);
      f.expansions += 1;
    } else {
      f.results = e.nodes;
      f.current = null;
      f.frontier = new Set();
    }
  }
  return f;
}

/** Index of the next "meaningful" event: an expansion, a layer change or the result. */
function nextStop(events: TraceEvent[], from: number): number {
  for (let i = from + 1; i < events.length; i++) {
    if (events[i]!.kind !== "visit") return i;
  }
  return events.length - 1;
}

// -- component -------------------------------------------------------------------------------

export function Visualizer() {
  // false during server render and hydration, true once on the client: the stage depends on
  // viewport size and motion preference, which the server cannot know.
  const mounted = useSyncExternalStore(noopSubscribe, () => true, () => false);
  const wide = useMediaQuery("(min-width: 768px)");
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");

  if (!mounted) {
    // Same footprint as the real stage, so nothing shifts when it mounts.
    return <div className="panel aspect-[3/4] w-full md:aspect-[16/10]" aria-hidden="true" />;
  }
  return <Stage key={wide ? "wide" : "narrow"} wide={wide} reduced={reduced} />;
}

function Stage({ wide, reduced }: { wide: boolean; reduced: boolean }) {
  // Fewer nodes on phones: the layers stack vertically and each panel is small.
  const graph = useMemo(() => {
    const pts = makeDataset(wide ? 240 : 110, 41);
    return buildGraph(pts, { M: 5, efConstruction: 32, seed: 7 });
  }, [wide]);
  const [query, setQuery] = useState<Point>({ x: 0.64, y: 0.4 });
  const [ef, setEf] = useState(16);
  const trace = useMemo(() => searchTrace(graph, query, K, ef), [graph, query, ef]);
  const truth = useMemo(() => exactKnn(graph.points, query, K), [graph, query]);
  const events = trace.events;
  const [step, setStep] = useState(reduced ? 0 : events.length - 1);
  const [playing, setPlaying] = useState(false);
  const frame = useMemo(() => replay(events, step), [events, step]);
  const done = step >= events.length - 1;
  const rng = useRef(mulberry32(5));

  // A new query or ef restarts playback (or jumps straight to the answer if motion is reduced).
  const restart = useCallback(() => {
    setStep(0);
    setPlaying(!reduced);
  }, [reduced]);
  const firstRun = useRef(true);
  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    restart();
  }, [trace, restart]);

  useEffect(() => {
    if (!playing) return;
    const per = Math.max(1, Math.ceil(events.length / TARGET_TICKS));
    const id = window.setInterval(() => {
      setStep((s) => {
        const n = Math.min(events.length - 1, s + per);
        if (n >= events.length - 1) setPlaying(false);
        return n;
      });
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [playing, events.length]);

  const place = (p: Point) => setQuery({ x: clamp01(p.x), y: clamp01(p.y) });
  const onKey = (e: React.KeyboardEvent) => {
    const d = 0.04;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-d, 0],
      ArrowRight: [d, 0],
      ArrowUp: [0, -d],
      ArrowDown: [0, d],
    };
    const m = moves[e.key];
    if (m) {
      e.preventDefault();
      place({ x: query.x + m[0], y: query.y + m[1] });
    }
  };

  const found = frame.results ?? [];
  const hits = found.filter((n) => truth.includes(n)).length;
  const layerLabel = frame.layer < 0 ? "starting" : `layer ${frame.layer}`;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div
        className="panel relative overflow-hidden"
        role="group"
        aria-label="HNSW search visualizer. Click or tap the bottom layer to place a query; arrow keys move it."
        tabIndex={0}
        onKeyDown={onKey}
      >
        {wide ? (
          <PerspectiveStage graph={graph} frame={frame} query={query} truth={done ? truth : []} reduced={reduced} onPlace={place} />
        ) : (
          <StackedStage graph={graph} frame={frame} query={query} truth={done ? truth : []} onPlace={place} />
        )}
      </div>

      <aside className="flex flex-col gap-5" aria-label="Search controls and readout">
        <div className="panel p-4">
          <label htmlFor="ef" className="flex items-baseline justify-between font-mono text-step--1 text-ink-dim">
            <span>ef_search (breadth on layer 0)</span>
            <span className="num text-step-0 text-trace">{ef}</span>
          </label>
          <input
            id="ef"
            type="range"
            min={1}
            max={64}
            value={ef}
            onChange={(e) => setEf(Number(e.target.value))}
            className="mt-2 w-full"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            {!reduced ? (
              <button type="button" className="btn" onClick={() => (done ? restart() : setPlaying((p) => !p))} aria-label={playing ? "Pause" : done ? "Replay" : "Play"}>
                {playing ? <IconPause /> : <IconPlay />}
                <span>{playing ? "Pause" : done ? "Replay" : "Play"}</span>
              </button>
            ) : null}
            <button type="button" className="btn" onClick={() => { setPlaying(false); setStep((s) => nextStop(events, s)); }} disabled={done} aria-label="Step to next hop">
              <IconStep />
              <span>Step</span>
            </button>
            <button type="button" className="btn" onClick={() => { setPlaying(false); setStep(events.length - 1); }} disabled={done} aria-label="Jump to result">
              <IconEnd />
            </button>
            <button type="button" className="btn" onClick={() => { setPlaying(false); setStep(0); }} aria-label="Reset to start">
              <IconReset />
            </button>
            <button type="button" className="btn" onClick={() => place({ x: 0.08 + rng.current() * 0.84, y: 0.08 + rng.current() * 0.84 })} aria-label="Random query">
              <IconShuffle />
            </button>
          </div>
          {reduced ? (
            <p className="mt-3 text-step--1 text-ink-dim">Reduced motion is on, so playback is manual: use Step.</p>
          ) : null}
        </div>

        <div className="panel p-4" aria-live="polite">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 font-mono text-step--1">
            <dt className="text-ink-dim">position</dt>
            <dd className="num text-right">{done ? "result" : layerLabel}</dd>
            <dt className="text-ink-dim">expansions</dt>
            <dd className="num text-right">{frame.expansions}</dd>
            <dt className="text-ink-dim">distances computed</dt>
            <dd className="num text-right">{frame.distanceCalls}</dd>
            <dt className="text-ink-dim">exact search needs</dt>
            <dd className="num text-right">{graph.points.length}</dd>
            <dt className="text-ink-dim">top-{K} matched</dt>
            <dd className="num text-right">{done ? `${hits} / ${K}` : "..."}</dd>
          </dl>
        </div>

        <Legend />
      </aside>
    </div>
  );
}

const noopSubscribe = () => () => {};

const clamp01 = (v: number) => Math.min(0.98, Math.max(0.02, v));

function Legend() {
  const items = [
    { swatch: <circle cx="8" cy="8" r="4" fill="#2a3842" />, label: "node" },
    { swatch: <circle cx="8" cy="8" r="4" fill="#1e7f6f" />, label: "distance computed" },
    { swatch: <circle cx="8" cy="8" r="5" fill="none" stroke="#35e0c2" strokeWidth="1.5" />, label: "in the best-ef set" },
    { swatch: <circle cx="8" cy="8" r="5" fill="#35e0c2" />, label: "being expanded / result" },
    { swatch: <circle cx="8" cy="8" r="5.5" fill="none" stroke="#f0a43a" strokeWidth="1.5" strokeDasharray="2 2" />, label: "exact top-k missed" },
    { swatch: <path d="M2 8h12M8 2v12" stroke="#e5ecef" strokeWidth="1.5" />, label: "query" },
  ];
  return (
    <ul className="grid grid-cols-2 gap-x-3 gap-y-2 font-mono text-step--1 text-ink-dim">
      {items.map((it) => (
        <li key={it.label} className="flex items-center gap-2">
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            {it.swatch}
          </svg>
          {it.label}
        </li>
      ))}
    </ul>
  );
}

// -- drawing ---------------------------------------------------------------------------------

type StageProps = {
  graph: Graph;
  frame: Frame;
  query: Point;
  truth: number[];
  onPlace: (p: Point) => void;
};

function nodeFill(graph: Graph, frame: Frame, layer: number, n: number): string {
  if (frame.results?.includes(n) && layer === 0) return "#35e0c2";
  if (frame.current === n && frame.layer === layer) return "#35e0c2";
  if (frame.visited.get(layer)?.has(n)) return "#1e7f6f";
  return layer === 0 ? "#2a3842" : "#3a4a55";
}

function toSvg(svg: SVGSVGElement, e: React.MouseEvent): { x: number; y: number } | null {
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
  return { x: p.x, y: p.y };
}

// Wide layout: layers drawn as sheared planes stacked upward, an oblique projection that reads as
// depth without 3-D transforms (and keeps click mapping exact: it is an invertible affine map).
const VW = 1000;
const PW = 640; // plane width
const PH = 150; // plane depth (foreshortened)
const SHEAR = 190;
const LEFT = 70;
const GAP = 46;

function PerspectiveStage({ graph, frame, query, truth, reduced, onPlace }: StageProps & { reduced: boolean }) {
  const layers = Array.from({ length: graph.maxLevel + 1 }, (_, i) => i);
  const VH = 40 + layers.length * (PH + GAP);
  const base = (layer: number) => VH - 30 - layer * (PH + GAP); // near edge of each plane
  const proj = (p: Point, layer: number) => ({
    x: LEFT + p.x * PW + (1 - p.y) * SHEAR,
    y: base(layer) - (1 - p.y) * PH,
  });
  const ref = useRef<SVGSVGElement>(null);

  const click = (e: React.MouseEvent) => {
    if (!ref.current) return;
    const s = toSvg(ref.current, e);
    if (!s) return;
    const y = 1 - (base(0) - s.y) / PH;
    const x = (s.x - LEFT - (1 - y) * SHEAR) / PW;
    if (x >= -0.05 && x <= 1.05 && y >= -0.05 && y <= 1.05) onPlace({ x, y });
  };

  return (
    <svg ref={ref} viewBox={`0 0 ${VW} ${VH}`} className="block h-auto w-full cursor-crosshair" onClick={click} role="img" aria-label={describe(frame, graph)}>
      {layers.map((layer) => {
        const corners = [
          { x: 0, y: 0 },
          { x: 1, y: 0 },
          { x: 1, y: 1 },
          { x: 0, y: 1 },
        ].map((c) => proj(c, layer));
        const active = frame.layer === layer && !frame.results;
        return (
          <g key={layer}>
            <polygon
              points={corners.map((c) => `${c.x},${c.y}`).join(" ")}
              fill={layer === 0 ? "#0a0f12" : "#090d10"}
              stroke={active ? "#35e0c2" : "#1b252c"}
              strokeWidth={active ? 1.5 : 1}
            />
            <text x={corners[3]!.x - 14} y={corners[3]!.y + 4} textAnchor="end" className="fill-ink-dim font-mono text-[13px]">
              {`L${layer}`}
            </text>
            <text x={corners[3]!.x - 14} y={corners[3]!.y + 20} textAnchor="end" className="fill-ink-dim font-mono text-[11px]">
              {`${graph.levels.filter((lv) => lv >= layer).length} nodes`}
            </text>
            <LayerEdges graph={graph} layer={layer} proj={proj} />
            <Hops frame={frame} layer={layer} graph={graph} proj={proj} />
            <LayerNodes graph={graph} frame={frame} layer={layer} truth={truth} proj={proj} reduced={reduced} />
            <Crosshair at={proj(query, layer)} bright={layer === 0} />
          </g>
        );
      })}
      {/* Descent: the best node of each layer becomes the entry of the layer below. */}
      {frame.entries.slice(1).map((e, i) => {
        const a = proj(graph.points[e.node]!, e.layer + 1);
        const b = proj(graph.points[e.node]!, e.layer);
        return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#35e0c2" strokeWidth="1.5" strokeDasharray="4 4" />;
      })}
    </svg>
  );
}

type Proj = (p: Point, layer: number) => { x: number; y: number };

function LayerEdges({ graph, layer, proj }: { graph: Graph; layer: number; proj: Proj }) {
  const lines = useMemo(() => {
    const out: { a: { x: number; y: number }; b: { x: number; y: number } }[] = [];
    graph.links.forEach((ls, a) => {
      for (const b of ls[layer] ?? []) if (a < b) out.push({ a: proj(graph.points[a]!, layer), b: proj(graph.points[b]!, layer) });
    });
    return out;
    // proj is stable per layout; graph identity covers the data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, layer]);
  return (
    <g stroke="#16232a" strokeWidth="1">
      {lines.map((l, i) => (
        <line key={i} x1={l.a.x} y1={l.a.y} x2={l.b.x} y2={l.b.y} />
      ))}
    </g>
  );
}

function Hops({ frame, layer, graph, proj }: { frame: Frame; layer: number; graph: Graph; proj: Proj }) {
  return (
    <g stroke="#1e7f6f" strokeWidth="1.25">
      {frame.hops
        .filter((h) => h.layer === layer)
        .map((h, i) => {
          const a = proj(graph.points[h.from]!, layer);
          const b = proj(graph.points[h.to]!, layer);
          return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} />;
        })}
    </g>
  );
}

function LayerNodes({ graph, frame, layer, truth, proj, reduced }: { graph: Graph; frame: Frame; layer: number; truth: number[]; proj: Proj; reduced: boolean }) {
  const r = layer === 0 ? 3.2 : 4;
  return (
    <g>
      {graph.levels.map((lv, n) => {
        if (lv < layer) return null;
        const p = proj(graph.points[n]!, layer);
        const inBest = frame.best.has(n) && frame.layer === layer;
        const missed = layer === 0 && truth.includes(n) && !frame.results?.includes(n);
        return (
          <g key={n}>
            <circle cx={p.x} cy={p.y} r={r} fill={nodeFill(graph, frame, layer, n)} />
            {inBest ? <circle cx={p.x} cy={p.y} r={r + 3} fill="none" stroke="#35e0c2" strokeWidth="1.25" /> : null}
            {missed ? <circle cx={p.x} cy={p.y} r={r + 4} fill="none" stroke="#f0a43a" strokeWidth="1.5" strokeDasharray="2 2" /> : null}
          </g>
        );
      })}
      {frame.current !== null && frame.layer === layer ? (
        <motion.circle
          key={`${layer}-${frame.current}`}
          cx={proj(graph.points[frame.current]!, layer).x}
          cy={proj(graph.points[frame.current]!, layer).y}
          r={r + 7}
          fill="none"
          stroke="#35e0c2"
          strokeWidth="1.5"
          initial={reduced ? false : { scale: 0.4, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        />
      ) : null}
    </g>
  );
}

function Crosshair({ at, bright }: { at: { x: number; y: number }; bright: boolean }) {
  const c = bright ? "#e5ecef" : "#93a3ac";
  return (
    <g stroke={c} strokeWidth={bright ? 1.75 : 1} opacity={bright ? 1 : 0.6}>
      <line x1={at.x - 9} y1={at.y} x2={at.x + 9} y2={at.y} />
      <line x1={at.x} y1={at.y - 9} x2={at.x} y2={at.y + 9} />
    </g>
  );
}

// Narrow layout: a genuine phone layout, not a shrunk canvas. Each layer is its own square
// panel, stacked top layer first, so the descent reads top to bottom as you scroll.
function StackedStage({ graph, frame, query, truth, onPlace }: StageProps) {
  const layers = Array.from({ length: graph.maxLevel + 1 }, (_, i) => graph.maxLevel - i);
  return (
    <div className="flex flex-col gap-3 p-3">
      {layers.map((layer) => (
        <StackedLayer key={layer} graph={graph} frame={frame} query={query} truth={truth} layer={layer} onPlace={layer === 0 ? onPlace : undefined} />
      ))}
    </div>
  );
}

function StackedLayer({ graph, frame, query, truth, layer, onPlace }: Omit<StageProps, "onPlace"> & { layer: number; onPlace?: (p: Point) => void }) {
  const S = 300;
  const proj: Proj = (p) => ({ x: 10 + p.x * (S - 20), y: 10 + p.y * (S - 20) });
  const ref = useRef<SVGSVGElement>(null);
  const active = frame.layer === layer && !frame.results;
  const click = (e: React.MouseEvent) => {
    if (!onPlace || !ref.current) return;
    const s = toSvg(ref.current, e);
    if (s) onPlace({ x: (s.x - 10) / (S - 20), y: (s.y - 10) / (S - 20) });
  };
  return (
    <figure className={`border ${active ? "border-trace" : "border-rule"}`}>
      <figcaption className="flex justify-between border-b border-rule px-3 py-2 font-mono text-step--1 text-ink-dim">
        <span>{`layer ${layer}`}</span>
        <span className="num">{`${graph.levels.filter((lv) => lv >= layer).length} nodes${layer === 0 ? " · tap to query" : ""}`}</span>
      </figcaption>
      <svg ref={ref} viewBox={`0 0 ${S} ${S}`} className={`block h-auto w-full ${onPlace ? "cursor-crosshair" : ""}`} onClick={click} aria-hidden={layer !== 0}>
        <LayerEdges graph={graph} layer={layer} proj={proj} />
        <Hops frame={frame} layer={layer} graph={graph} proj={proj} />
        <LayerNodes graph={graph} frame={frame} layer={layer} truth={truth} proj={proj} reduced />
        <Crosshair at={proj(query, layer)} bright={layer === 0} />
      </svg>
    </figure>
  );
}

function describe(frame: Frame, graph: Graph): string {
  if (frame.results) return `Search finished: ${frame.results.length} results after ${frame.distanceCalls} distance computations out of ${graph.points.length} nodes.`;
  if (frame.layer < 0) return "Search not started.";
  return `Searching layer ${frame.layer} of ${graph.maxLevel}; ${frame.distanceCalls} distances computed so far.`;
}
