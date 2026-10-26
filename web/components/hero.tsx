import { HeroGraph } from "@/components/hero-graph";
import { IconArrowRight } from "@/components/icons";
import { headlineFor, headlines } from "@/lib/bench";
import { fmtInt, fmtMs, fmtQps } from "@/lib/format";

// Hero text renders immediately with no entrance animation; only the background graph moves.
export function Hero() {
  const h = headlineFor("sift") ?? headlines[0]!;
  const readouts = [
    { label: "recall@10", value: h.recall_at_10.toFixed(3), unit: "" },
    { label: "throughput", value: fmtQps(h.qps), unit: "q/s" },
    { label: "p50 latency", value: fmtMs(h.p50_ms), unit: "ms" },
    { label: "vs exact search", value: `${h.speedup_vs_flat.toFixed(1)}×`, unit: "faster" },
  ];
  return (
    <section id="top" className="relative overflow-hidden" aria-labelledby="hero-title">
      <HeroGraph />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-bg/40 via-bg/70 to-bg" aria-hidden="true" />
      <div className="container-instrument relative grid gap-12 pb-20 pt-16 md:pt-28 lg:grid-cols-[1.25fr_1fr] lg:items-end lg:pb-28">
        <div>
          <p className="eyebrow">Vector database, written from scratch</p>
          <h1 id="hero-title" className="mt-4 text-step-4 font-semibold leading-[1.02] tracking-tight">
            VectorForge
          </h1>
          <p className="mt-6 max-w-[38rem] text-step-1 leading-snug text-ink-dim">
            Hand-written HNSW and IVF indexes, a crash-safe write-ahead log and a query service in
            Python and NumPy, measured against FAISS on public datasets.
          </p>
          <div className="mt-10 flex flex-wrap gap-3">
            <a href="#visualizer" className="btn btn-primary">
              Watch a search descend
              <IconArrowRight />
            </a>
            <a href="#benchmarks" className="btn">
              Read the benchmark
            </a>
          </div>
        </div>

        <figure className="panel p-5 md:p-6" aria-labelledby="headline-caption">
          <figcaption id="headline-caption" className="flex items-baseline justify-between gap-4 border-b border-rule pb-3">
            <span className="eyebrow">Measured</span>
            <span className="num text-step--1 text-ink-dim">
              {h.dataset}, {fmtInt(h.n_base)} vectors
            </span>
          </figcaption>
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-5">
            {readouts.map((r) => (
              <div key={r.label}>
                <dt className="font-mono text-step--1 text-ink-dim">{r.label}</dt>
                <dd className="num mt-1 text-step-2 text-ink">
                  {r.value}
                  {r.unit ? <span className="ml-1 text-step--1 text-ink-dim">{r.unit}</span> : null}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-5 border-t border-rule pt-4 text-step--1 leading-relaxed text-ink-dim">
            HNSW at <span className="num text-ink">ef_search={h.ef_search}</span>, one query at a time on one core.{" "}
            {h.faiss_speedup ? (
              <>
                FAISS is <span className="num text-signal">{h.faiss_speedup}×</span> faster still at the same recall.
              </>
            ) : null}{" "}
            Source: <span className="num">bench/results/summary.json</span>.
          </p>
        </figure>
      </div>
    </section>
  );
}
