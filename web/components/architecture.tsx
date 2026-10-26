"use client";

import { useEffect, useRef, useState } from "react";

// Scroll-driven walkthrough: the diagram stays put and each step lights its part of the path.
// One idea per step. Paths draw with stroke-dashoffset; under reduced motion they just appear.

type Box = { id: string; x: number; y: number; label: string; sub: string };

const BOXES: Box[] = [
  { id: "req", x: 20, y: 40, label: "upsert", sub: "POST /vectors" },
  { id: "val", x: 190, y: 40, label: "validate", sub: "dim, finite, caps" },
  { id: "wal", x: 360, y: 40, label: "WAL", sub: "append + fsync" },
  { id: "seg", x: 530, y: 40, label: "segment", sub: "mmap rows" },
  { id: "idx", x: 700, y: 40, label: "index", sub: "HNSW links" },
  { id: "man", x: 530, y: 170, label: "manifest", sub: "atomic rename" },
  { id: "qry", x: 20, y: 300, label: "search", sub: "POST /search" },
  { id: "flt", x: 190, y: 300, label: "filter", sub: "compile predicate" },
  { id: "up", x: 360, y: 300, label: "upper layers", sub: "greedy, ef=1" },
  { id: "l0", x: 530, y: 300, label: "layer 0", sub: "best-first, ef_search" },
  { id: "out", x: 700, y: 300, label: "top-k", sub: "ids + metadata" },
];
const BW = 150;
const BH = 56;

const PATHS: Record<string, string> = {
  "req-val": "M170 68 H190",
  "val-wal": "M340 68 H360",
  "wal-seg": "M510 68 H530",
  "seg-idx": "M680 68 H700",
  "wal-man": "M435 96 V198 H530",
  "qry-flt": "M170 328 H190",
  "flt-up": "M340 328 H360",
  "up-l0": "M510 328 H530",
  "l0-out": "M680 328 H700",
  "idx-up": "M775 96 V230 H435 V300",
};

const STEPS = [
  { title: "Validate at the door", body: "Pydantic checks dimension, finiteness (no NaN or Infinity), id format, metadata size and batch size before anything touches disk. A bad batch is rejected whole.", boxes: ["req", "val"], paths: ["req-val"] },
  { title: "The WAL is the commit point", body: "Each vector becomes a length-prefixed, crc32-checked record. The batch is written and fsynced once. Only then does the request succeed, so an acknowledged write survives a crash.", boxes: ["val", "wal"], paths: ["val-wal"] },
  { title: "Rows land in segments", body: "Vectors go into fixed-size, memory-mapped segment files, one row per label. Segments are flushed at checkpoints; after a crash the WAL rewrites any row past the last checkpoint.", boxes: ["wal", "seg"], paths: ["wal-seg"] },
  { title: "The index links the new node", body: "HNSW draws a level, descends to it, picks neighbours with the diversity heuristic and links both ways. Deletes are tombstones, so the graph is never cut.", boxes: ["seg", "idx"], paths: ["seg-idx"] },
  { title: "Checkpoints swap atomically", body: "A snapshot is written under new names, then the manifest is replaced by rename. That rename is the single switch from old state to new. The WAL is emptied only after it.", boxes: ["wal", "man"], paths: ["wal-man"] },
  { title: "Search starts with the filter", body: "A metadata filter is compiled into a predicate. If it matches very few vectors, the engine skips the graph and scans just those, because graph recall collapses under selective filters.", boxes: ["qry", "flt"], paths: ["qry-flt"] },
  { title: "Express lanes first", body: "On each upper layer the search hops greedily to the closest node it can find. Few nodes, long edges: a handful of hops crosses the whole dataset.", boxes: ["flt", "up", "idx"], paths: ["flt-up", "idx-up"] },
  { title: "Layer 0 does the real work", body: "A best-first search keeps the ef_search closest nodes seen. Filtered-out and deleted nodes are walked through but never returned. The top k become the answer.", boxes: ["up", "l0", "out"], paths: ["up-l0", "l0-out"] },
];

export function Architecture() {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.step));
        }
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  const step = STEPS[active]!;
  const lit = new Set(step.boxes);
  const drawn = new Set(STEPS.slice(0, active + 1).flatMap((s) => s.paths));
  const current = new Set(step.paths);

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="sticky top-16 z-10 self-start bg-bg py-2 lg:top-24">
        <svg viewBox="0 0 870 380" className="panel block h-auto w-full p-2" role="img" aria-label={`Architecture diagram. Step ${active + 1} of ${STEPS.length}: ${step.title}.`}>
          <text x="20" y="24" className="fill-ink-dim font-mono text-[12px]">write path</text>
          <text x="20" y="284" className="fill-ink-dim font-mono text-[12px]">read path</text>
          {Object.entries(PATHS).map(([id, d]) => (
            <path
              key={id}
              d={d}
              pathLength={1}
              fill="none"
              stroke={current.has(id) ? "#35e0c2" : "#1e7f6f"}
              strokeWidth={current.has(id) ? 2 : 1.25}
              className="trace-draw"
              data-drawn={drawn.has(id) ? "true" : "false"}
            />
          ))}
          {BOXES.map((b) => {
            const on = lit.has(b.id);
            return (
              <g key={b.id} transform={`translate(${b.x} ${b.y})`}>
                <rect width={BW} height={BH} rx={2} fill="#0c1115" stroke={on ? "#35e0c2" : "#2a3842"} strokeWidth={on ? 1.5 : 1} />
                <text x={12} y={24} className={`font-mono text-[14px] ${on ? "fill-trace" : "fill-ink"}`}>{b.label}</text>
                <text x={12} y={43} className="fill-ink-dim font-mono text-[11px]">{b.sub}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <ol className="flex flex-col">
        {STEPS.map((s, i) => (
          <li
            key={s.title}
            ref={(el) => {
              refs.current[i] = el;
            }}
            data-step={i}
            className={`border-l py-10 pl-6 transition-colors duration-300 lg:min-h-[55vh] ${i === active ? "border-trace" : "border-rule"}`}
          >
            <p className="num text-step--1 text-ink-dim">{`${String(i + 1).padStart(2, "0")} / ${String(STEPS.length).padStart(2, "0")} · ${i < 5 ? "write" : "read"}`}</p>
            <h3 className="mt-2 text-step-1 font-medium">{s.title}</h3>
            <p className="mt-3 max-w-[34rem] text-ink-dim">{s.body}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
