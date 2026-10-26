"use client";

import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridColumns, GridRows } from "@visx/grid";
import { Group } from "@visx/group";
import { scaleLinear, scaleLog } from "@visx/scale";
import { LinePath } from "@visx/shape";
import { useEffect, useMemo, useRef, useState } from "react";

import { useInView } from "@/components/reveal";
import type { BenchResult, BenchSeries } from "@/lib/bench";
import { fmtBytes, fmtMs, fmtQps, fmtTick } from "@/lib/format";
import { useMediaQuery } from "@/lib/use-media-query";

const STYLE: Record<string, { stroke: string; dash?: string; width: number }> = {
  "vf-hnsw": { stroke: "#35e0c2", width: 2.25 },
  "vf-ivf": { stroke: "#35e0c2", dash: "7 5", width: 1.75 },
  "vf-ivf-int8": { stroke: "#1e9f8a", dash: "2 4", width: 1.75 },
  "vf-flat": { stroke: "#e5ecef", width: 2 },
  "faiss-hnsw": { stroke: "#f0a43a", width: 2.25 },
  "faiss-ivf": { stroke: "#f0a43a", dash: "7 5", width: 1.75 },
};

type Sel = { series: string; index: number };

export function BenchExplorer({ results }: { results: BenchResult[] }) {
  const [key, setKey] = useState(results[0]!.key);
  const data = results.find((r) => r.key === key)!;
  const narrow = !useMediaQuery("(min-width: 640px)");
  const [single, setSingle] = useState("vf-hnsw");
  const [sel, setSel] = useState<Sel>({ series: "vf-hnsw", index: 3 });
  const [ref, seen] = useInView<HTMLDivElement>();

  const shown = narrow ? data.series.filter((s) => s.id === single || s.id === "vf-flat") : data.series;
  const selected = data.series.find((s) => s.id === sel.series);
  const point = selected?.points[Math.min(sel.index, selected.points.length - 1)];

  return (
    <div className="grid min-w-0 gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Dataset" className="flex gap-2">
          {results.map((r) => (
            <button key={r.key} type="button" className="btn" aria-pressed={r.key === key} onClick={() => setKey(r.key)}>
              {r.dataset.name}
            </button>
          ))}
        </div>
        {narrow ? (
          <label className="flex items-center gap-2 font-mono text-step--1 text-ink-dim">
            Series
            <select
              className="btn bg-panel"
              value={single}
              onChange={(e) => {
                setSingle(e.target.value);
                setSel({ series: e.target.value, index: 0 });
              }}
            >
              {data.series
                .filter((s) => s.id !== "vf-flat")
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
            </select>
          </label>
        ) : null}
      </div>

      <div ref={ref} className="panel min-w-0 p-3 md:p-5">
        <Chart data={data} shown={shown} sel={sel} onSelect={setSel} drawn={seen} />
        <Readout series={selected} point={point} />
        {!narrow ? <Legend series={data.series} /> : null}
      </div>

      <Details data={data} />
    </div>
  );
}

function Chart({
  data,
  shown,
  sel,
  onSelect,
  drawn,
}: {
  data: BenchResult;
  shown: BenchSeries[];
  sel: Sel;
  onSelect: (s: Sel) => void;
  drawn: boolean;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e!.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const height = Math.max(280, Math.min(520, Math.round(width * 0.58)));
  const margin = { top: 30, right: 16, bottom: 48, left: 56 };
  const innerW = Math.max(0, width - margin.left - margin.right);
  const innerH = height - margin.top - margin.bottom;

  const all = data.series.flatMap((s) => s.points);
  const minRecall = Math.max(0, Math.floor(Math.min(...all.map((p) => p.recall_at_10)) * 20) / 20);
  const x = useMemo(() => scaleLinear({ domain: [minRecall, 1], range: [0, innerW] }), [minRecall, innerW]);
  const qps = all.map((p) => p.qps);
  const y = useMemo(
    () => scaleLog({ domain: [Math.min(...qps) / 1.6, Math.max(...qps) * 1.6], range: [innerH, 0] }),
    // qps derives from data; recompute when the dataset or size changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, innerH],
  );

  // Log-axis ticks at 1, 2 and 5 times powers of ten (powers of ten only when narrow), so the
  // labels never pile up the way automatic log ticks do between 1k and 9k.
  const yTicks = useMemo(() => {
    const [lo, hi] = y.domain() as [number, number];
    const steps = innerW < 420 ? [1] : [1, 2, 5];
    const out: number[] = [];
    for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) {
      for (const m of steps) {
        const v = m * 10 ** e;
        if (v >= lo && v <= hi) out.push(v);
      }
    }
    return out;
  }, [y, innerW]);

  // Arrow keys walk the selected series; tab order reaches the chart once.
  const onKey = (e: React.KeyboardEvent) => {
    const order = shown.filter((s) => s.id !== "vf-flat").map((s) => s.id);
    const series = data.series.find((s) => s.id === sel.series);
    if (!series) return;
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const d = e.key === "ArrowRight" ? 1 : -1;
      onSelect({ series: sel.series, index: Math.max(0, Math.min(series.points.length - 1, sel.index + d)) });
    } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      e.preventDefault();
      const i = order.indexOf(sel.series);
      const next = order[(i + (e.key === "ArrowDown" ? 1 : order.length - 1)) % order.length]!;
      onSelect({ series: next, index: 0 });
    }
  };

  const nearest = (clientX: number, clientY: number, svg: SVGSVGElement) => {
    const r = svg.getBoundingClientRect();
    const px = clientX - r.left - margin.left;
    const py = clientY - r.top - margin.top;
    let best: Sel | null = null;
    let bestD = Infinity;
    for (const s of shown) {
      s.points.forEach((p, i) => {
        const d = (x(p.recall_at_10) - px) ** 2 + (y(p.qps) - py) ** 2;
        if (d < bestD) {
          bestD = d;
          best = { series: s.id, index: i };
        }
      });
    }
    if (best && bestD < 40 ** 2) onSelect(best);
  };

  const flat = data.series.find((s) => s.id === "vf-flat")?.points[0];

  return (
    <div ref={box} className="w-full min-w-0 overflow-hidden">
      {width > 0 ? (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`Recall at 10 against queries per second, log scale, for ${data.dataset.name}. Full data in the table below.`}
          tabIndex={0}
          onKeyDown={onKey}
          onPointerMove={(e) => nearest(e.clientX, e.clientY, e.currentTarget)}
          onPointerDown={(e) => nearest(e.clientX, e.clientY, e.currentTarget)}
          className="block touch-pan-y"
        >
          <Group left={margin.left} top={margin.top}>
            <GridRows scale={y} width={innerW} stroke="#1b252c" tickValues={yTicks} />
            <text x={-margin.left + 4} y={-14} className="fill-ink-dim font-mono text-[12px]">
              queries / second (log scale)
            </text>
            <GridColumns scale={x} height={innerH} stroke="#1b252c" numTicks={6} />
            {flat ? (
              <line x1={0} x2={innerW} y1={y(flat.qps)} y2={y(flat.qps)} stroke="#93a3ac" strokeDasharray="3 5" strokeWidth={1} />
            ) : null}
            {shown.map((s) => {
              const st = STYLE[s.id] ?? { stroke: "#e5ecef", width: 1.5 };
              const pts = [...s.points].sort((a, b) => a.recall_at_10 - b.recall_at_10);
              return (
                <g key={s.id}>
                  {pts.length > 1 ? (
                    <LinePath
                      data={pts}
                      x={(p) => x(p.recall_at_10)}
                      y={(p) => y(p.qps)}
                      stroke={st.stroke}
                      strokeWidth={st.width}
                      strokeDasharray={st.dash}
                      fill="none"
                    />
                  ) : null}
                  {s.points.map((p, i) => {
                    const active = sel.series === s.id && sel.index === i;
                    return (
                      <circle
                        key={i}
                        cx={x(p.recall_at_10)}
                        cy={y(p.qps)}
                        r={active ? 6 : s.id === "vf-flat" ? 5 : 3}
                        fill={active ? st.stroke : "#07090b"}
                        stroke={st.stroke}
                        strokeWidth={1.5}
                        className={drawn ? "opacity-100 transition-opacity duration-500" : "opacity-0"}
                      />
                    );
                  })}
                </g>
              );
            })}
            {/* Draw-in mask: a panel that slides off to the right once the chart is in view. */}
            <rect
              x={0}
              y={0}
              width={innerW + 2}
              height={innerH}
              fill="#0c1115"
              className={`origin-right transition-transform duration-700 ease-out motion-reduce:hidden ${drawn ? "scale-x-0" : "scale-x-100"}`}
            />
            <AxisLeft
              scale={y}
              tickValues={yTicks}
              stroke="#2a3842"
              tickStroke="#2a3842"
              tickFormat={(v) => fmtTick(Number(v))}
              tickLabelProps={{ fill: "#93a3ac", fontSize: 12, fontFamily: "var(--font-geist-mono)", textAnchor: "end", dx: -4, dy: 4 }}
            />
            <AxisBottom
              top={innerH}
              scale={x}
              numTicks={6}
              stroke="#2a3842"
              tickStroke="#2a3842"
              tickFormat={(v) => Number(v).toFixed(2)}
              tickLabelProps={{ fill: "#93a3ac", fontSize: 12, fontFamily: "var(--font-geist-mono)", textAnchor: "middle" }}
              label="recall@10"
              labelProps={{ fill: "#93a3ac", fontSize: 12, fontFamily: "var(--font-geist-mono)", textAnchor: "middle" }}
              labelOffset={16}
            />
          </Group>
        </svg>
      ) : (
        <div className="h-[280px]" />
      )}
    </div>
  );
}

function Readout({ series, point }: { series?: BenchSeries; point?: BenchSeries["points"][number] }) {
  if (!series || !point) return null;
  const param = series.sweep ? `${series.sweep}=${point.param}` : "exact";
  return (
    <div className="mt-4 grid grid-cols-2 gap-3 border-t border-rule pt-4 font-mono text-step--1 sm:grid-cols-3 lg:grid-cols-6" aria-live="polite">
      <Cell label="series" value={series.label} wide />
      <Cell label="setting" value={param} />
      <Cell label="recall@10" value={point.recall_at_10.toFixed(4)} />
      <Cell label="q/s" value={fmtQps(point.qps)} />
      <Cell label="p50 / p99 ms" value={`${fmtMs(point.p50_ms)} / ${fmtMs(point.p99_ms)}`} />
    </div>
  );
}

function Cell({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className={wide ? "col-span-2" : ""}>
      <div className="text-ink-dim">{label}</div>
      <div className="num mt-0.5 text-ink">{value}</div>
    </div>
  );
}

function Legend({ series }: { series: BenchSeries[] }) {
  return (
    <ul className="mt-4 flex flex-wrap gap-x-6 gap-y-2 font-mono text-step--1 text-ink-dim">
      {series.map((s) => {
        const st = STYLE[s.id] ?? { stroke: "#e5ecef", width: 1.5 };
        return (
          <li key={s.id} className="flex items-center gap-2">
            <svg width="28" height="10" aria-hidden="true">
              <line x1="0" y1="5" x2="28" y2="5" stroke={st.stroke} strokeWidth={st.width} strokeDasharray={st.dash} />
            </svg>
            {s.label}
          </li>
        );
      })}
      <li className="flex items-center gap-2">
        <svg width="28" height="10" aria-hidden="true">
          <line x1="0" y1="5" x2="28" y2="5" stroke="#93a3ac" strokeDasharray="3 5" />
        </svg>
        exact-search throughput
      </li>
    </ul>
  );
}

function Details({ data }: { data: BenchResult }) {
  // The full table is ~60 rows; build it only when someone opens it.
  const [tableOpen, setTableOpen] = useState(false);
  const env = data.environment;
  const vf = data.series.find((s) => s.id === "vf-hnsw");
  const fh = data.series.find((s) => s.id === "faiss-hnsw");
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="panel p-4 md:p-5">
        <h3 className="eyebrow">Setup</h3>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-step--1">
          <dt className="text-ink-dim">dataset</dt>
          <dd>{data.dataset.subset}</dd>
          <dt className="text-ink-dim">cpu</dt>
          <dd className="num">{`${env.hardware.cpu}, ${env.hardware.logical_cores} logical cores`}</dd>
          <dt className="text-ink-dim">ram</dt>
          <dd className="num">{fmtBytes(env.hardware.ram_bytes)}</dd>
          <dt className="text-ink-dim">os</dt>
          <dd className="num">{env.hardware.os}</dd>
          <dt className="text-ink-dim">versions</dt>
          <dd className="num">{Object.entries(env.versions).map(([k, v]) => `${k} ${v}`).join(", ")}</dd>
          <dt className="text-ink-dim">threads</dt>
          <dd>{env.threads}</dd>
          <dt className="text-ink-dim">commit</dt>
          <dd className="num">{env.commit}</dd>
        </dl>
        <p className="mt-4 text-step--1 text-ink-dim">Regenerate every number on this page:</p>
        <pre className="num mt-2 overflow-x-auto border border-rule bg-bg p-3 text-step--1">
          <code>python bench/datasets/download.py all{"\n"}python bench/run_bench.py</code>
        </pre>
      </div>
      <div className="panel p-4 md:p-5">
        <h3 className="eyebrow">Build cost</h3>
        <table className="mt-3 w-full text-left text-step--1">
          <thead className="text-ink-dim">
            <tr>
              <th className="py-1 font-normal">index</th>
              <th className="py-1 text-right font-normal">build</th>
              <th className="py-1 text-right font-normal">memory</th>
            </tr>
          </thead>
          <tbody className="num">
            {data.series.map((s) => (
              <tr key={s.id} className="border-t border-rule">
                <td className="py-1.5 font-sans">{s.label}</td>
                <td className="py-1.5 text-right">{s.build_s < 1 ? `${(s.build_s * 1000).toFixed(0)} ms` : `${s.build_s.toFixed(1)} s`}</td>
                <td className="py-1.5 text-right">{fmtBytes(s.memory_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-4 text-step--1 leading-relaxed text-ink-dim">
          {vf && fh
            ? `HNSW build: VectorForge ${vf.build_s.toFixed(0)} s, FAISS ${fh.build_s.toFixed(1)} s with the same M and ef_construction. `
            : null}
          The gap is the Python interpreter: every hop pays for heap operations and a NumPy call on a handful of
          vectors, where FAISS runs a tight C++ loop with SIMD distance kernels over contiguous memory.
          {data.dominates_flat ? " HNSW still beats exact search at recall@10 of 0.99 or better." : ""}
        </p>
      </div>
      <details className="panel p-4 md:p-5 lg:col-span-2" onToggle={(e) => setTableOpen(e.currentTarget.open)}>
        <summary className="flex min-h-11 cursor-pointer items-center font-mono text-step--1">Data table (every point in the chart)</summary>
        {tableOpen ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-step--1">
            <caption className="sr-only">{`Benchmark points for ${data.dataset.name}`}</caption>
            <thead className="text-ink-dim">
              <tr>
                {["series", "setting", "recall@1", "recall@10", "q/s", "p50 ms", "p95 ms", "p99 ms"].map((h) => (
                  <th key={h} className="py-1 pr-3 font-normal">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="num">
              {data.series.flatMap((s) =>
                s.points.map((p) => (
                  <tr key={`${s.id}-${p.param}`} className="border-t border-rule">
                    <td className="py-1 pr-3 font-sans">{s.label}</td>
                    <td className="py-1 pr-3">{s.sweep ? `${s.sweep}=${p.param}` : "exact"}</td>
                    <td className="py-1 pr-3">{p.recall_at_1.toFixed(4)}</td>
                    <td className="py-1 pr-3">{p.recall_at_10.toFixed(4)}</td>
                    <td className="py-1 pr-3">{p.qps.toFixed(1)}</td>
                    <td className="py-1 pr-3">{fmtMs(p.p50_ms)}</td>
                    <td className="py-1 pr-3">{fmtMs(p.p95_ms)}</td>
                    <td className="py-1 pr-3">{fmtMs(p.p99_ms)}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
        ) : null}
      </details>
    </div>
  );
}
