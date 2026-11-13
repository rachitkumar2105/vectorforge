"use client";

import { useEffect, useRef, useState } from "react";

import { IconSearch } from "@/components/icons";
import { fmtMs } from "@/lib/format";
import { engineMonitor, useEngineState } from "@/lib/use-engine";

type Hit = { id: string; title: string; module: string; summary: string; distance: number };
type Reply =
  | { source: "engine"; results: Hit[]; engineMs: number | null; totalMs: number }
  | { source: "snapshot"; reason: string; results: Hit[]; snapshotMs: number; totalMs: number; corpusSize: number }
  | { source: "none"; results: []; totalMs: number; note: string };

/** One answered query, as measured: the browser's round trip plus the route's own timings. */
type Trace = { q: string; source: Reply["source"]; roundTrip: number; serverMs: number; searchMs: number | null };

const PRESETS = ["read a file line by line", "compress data", "send an email", "parse a date from text", "random number", "wait for a thread"];

// The route allows a burst of 8 and refills one search a second per visitor. Typing waits for a
// pause and never sends more than one automatic search per TYPE_GAP_MS, so it stays inside that.
const TYPE_IDLE_MS = 450;
const TYPE_GAP_MS = 1100;
const MIN_TYPED = 3;
const HISTORY = 14;

export function SearchDemo({ corpusSize }: { corpusSize: number }) {
  const [query, setQuery] = useState("");
  const [reply, setReply] = useState<Reply | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [traces, setTraces] = useState<Trace[]>([]);
  const [asYouType, setAsYouType] = useState(true);
  // Bumped per answer, so the result list re-keys on a new answer and not on every keystroke.
  const [answer, setAnswer] = useState(0);
  // Until the engine is confirmed live, answer from the snapshot: a cold start never blocks the
  // visitor. When it comes live, the next query goes live; input and results are left alone.
  // State only: the waking counter ticks every second and must not re-render the result list.
  const mode = useEngineState() === "live" ? "live" : "snapshot";
  const seq = useRef(0);
  const lastSent = useRef<{ at: number; q: string }>({ at: 0, q: "" });

  async function run(q: string) {
    const text = q.trim();
    if (!text) return;
    const mine = ++seq.current;
    lastSent.current = { at: performance.now(), q: text };
    setBusy(true);
    setError(null);
    const t = performance.now();
    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: text, k: 8, mode }),
      });
      const body = await res.json();
      const roundTrip = performance.now() - t;
      if (mine !== seq.current) return; // a newer query was sent while this one was in flight
      if (!res.ok) {
        // Our own route's message (rate limit, validation); never an engine error string.
        setError(typeof body?.error?.message === "string" ? body.error.message : "Search failed.");
        setReply(null);
      } else {
        const r = body as Reply;
        setReply(r);
        setAnswer((n) => n + 1);
        if (r.source !== "none") {
          const searchMs = r.source === "engine" ? r.engineMs : r.snapshotMs;
          setTraces((xs) => [...xs, { q: text, source: r.source, roundTrip, serverMs: r.totalMs, searchMs }].slice(-HISTORY));
        }
        // A live query that fell back means the engine went away (free tier sleeps when idle).
        if (mode === "live" && r.source === "snapshot") engineMonitor.recheck();
      }
    } catch {
      if (mine === seq.current) setError("Network error. Check your connection and try again.");
    } finally {
      if (mine === seq.current) setBusy(false);
    }
  }

  // Search as you type: after a pause, at most one automatic query per TYPE_GAP_MS.
  useEffect(() => {
    if (!asYouType) return;
    const text = query.trim();
    if (text.length < MIN_TYPED || text === lastSent.current.q) return;
    const sinceLast = performance.now() - lastSent.current.at;
    const wait = Math.max(TYPE_IDLE_MS, TYPE_GAP_MS - sinceLast);
    const id = window.setTimeout(() => void run(text), wait);
    return () => window.clearTimeout(id);
    // run reads the latest mode through closure on each render; re-arming on query is the point.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, asYouType]);

  const last = traces.at(-1) ?? null;
  const best = reply && reply.results.length > 0 ? reply.results[0]!.distance : 0;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
      <div className="flex flex-col gap-4">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void run(query);
          }}
        >
          <label htmlFor="demo-q" className="sr-only">
            Describe what you want the Python standard library to do
          </label>
          <input
            id="demo-q"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            maxLength={200}
            placeholder="describe a task, e.g. copy a directory tree"
            className="min-h-11 w-full min-w-0 border border-rule-strong bg-panel px-3 font-mono text-step--1 text-ink placeholder:text-ink-dim"
            autoComplete="off"
          />
          <button type="submit" className="btn btn-primary" aria-label="Search">
            <IconSearch />
          </button>
        </form>
        <label className="flex min-h-11 cursor-pointer items-center gap-3 font-mono text-step--1 text-ink-dim">
          <input
            type="checkbox"
            checked={asYouType}
            onChange={(e) => setAsYouType(e.target.checked)}
            className="h-4 w-4 accent-trace"
          />
          search as you type
          <span className="hidden text-ink-dim/80 sm:inline">(after a pause, within the rate limit)</span>
        </label>
        <div className="flex flex-wrap gap-2" aria-label="Example queries">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              className="btn"
              onClick={() => {
                setQuery(p);
                void run(p);
              }}
            >
              {p}
            </button>
          ))}
        </div>
        <p className="text-step--1 leading-relaxed text-ink-dim">
          {`${corpusSize.toLocaleString("en-US")} docstrings from the Python standard library, embedded with SIF-weighted GloVe vectors. `}
          Word vectors, not a language model: matches are about shared vocabulary, and that is part of the demonstration.
        </p>
        <LatencyStrip traces={traces} />
      </div>

      <div className="panel min-h-[22rem] p-4 md:p-5" aria-live="polite" aria-busy={busy}>
        <Status reply={reply} error={error} busy={busy} />
        {last && reply && reply.source !== "none" && !error ? <Waterfall t={last} /> : null}
        {/* One keyed list per answer: a new answer replaces the list and its items step in with a
            CSS animation (staggered by class, no inline styles, so the nonce CSP is satisfied).
            Re-keyed on a new answer, never on keystrokes. */}
        <ol key={answer} className="mt-4 flex flex-col">
          {reply?.results.map((h, i) => (
            <li key={h.id} className={`result-in result-in-${Math.min(i, 9)} border-t border-rule py-3 first:border-t-0`}>
              <div className="flex items-baseline justify-between gap-4">
                <span className="num break-all text-step--1 text-trace">{h.title}</span>
                <span className="flex shrink-0 items-center gap-3">
                  <SimilarityBar distance={h.distance} best={best} />
                  <span className="num w-12 text-right text-step--1 text-ink-dim">{h.distance.toFixed(3)}</span>
                </span>
              </div>
              <p className="mt-1 text-step--1 leading-relaxed text-ink">{h.summary}</p>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

/** Cosine similarity (1 - distance) as a bar; widths are SVG attributes, so the CSP allows them. */
function SimilarityBar({ distance, best }: { distance: number; best: number }) {
  const sim = Math.max(0, 1 - distance);
  const top = Math.max(1e-6, 1 - best);
  const w = Math.max(2, Math.min(64, (sim / top) * 64));
  return (
    <svg width="64" height="6" viewBox="0 0 64 6" aria-hidden className="hidden sm:block">
      <rect x="0" y="0" width="64" height="6" rx="3" className="fill-rule" />
      <rect x="0" y="0" width={w} height="6" rx="3" className="fill-trace grow-x" />
    </svg>
  );
}

/** Where the last answer's time went, from real measurements: browser, route and search. */
function Waterfall({ t }: { t: Trace }) {
  const search = t.searchMs ?? 0;
  const route = Math.max(0, t.serverMs - search);
  const network = Math.max(0, t.roundTrip - t.serverMs);
  const total = Math.max(1, network + route + search);
  const W = 300;
  const segs = [
    { key: "network", label: "network and platform", ms: network, cls: "fill-rule-strong" },
    { key: "route", label: "embed and route", ms: route, cls: "fill-trace-dim" },
    { key: "search", label: t.source === "engine" ? "HNSW search on the engine" : "exact search in the route", ms: search, cls: "fill-trace" },
  ];
  let x = 0;
  return (
    <figure className="mt-3">
      <svg viewBox={`0 0 ${W} 10`} preserveAspectRatio="none" className="h-2.5 w-full" role="img" aria-label={`Round trip ${fmtMs(t.roundTrip)} ms`}>
        {segs.map((s) => {
          const w = (s.ms / total) * W;
          const r = <rect key={s.key} x={x} y="0" width={Math.max(s.ms > 0 ? 1 : 0, w)} height="10" className={`${s.cls} grow-x`} />;
          x += w;
          return r;
        })}
      </svg>
      <figcaption className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[0.75rem] text-ink-dim">
        <span>
          round trip <span className="num text-ink">{fmtMs(t.roundTrip)} ms</span>
        </span>
        {segs.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5">
            <svg width="8" height="8" aria-hidden>
              <rect width="8" height="8" className={s.cls} />
            </svg>
            {s.label} <span className="num text-ink">{fmtMs(s.ms)} ms</span>
          </span>
        ))}
      </figcaption>
    </figure>
  );
}

/** The visitor's own queries this session: round trip per query, engine or snapshot. */
function LatencyStrip({ traces }: { traces: Trace[] }) {
  if (traces.length === 0) {
    return (
      <div className="panel p-4">
        <p className="eyebrow">your queries, this session</p>
        <p className="mt-2 font-mono text-step--1 text-ink-dim">Round-trip times appear here as you search.</p>
      </div>
    );
  }
  const H = 48;
  const BW = 14;
  const peak = Math.max(...traces.map((t) => t.roundTrip));
  const sorted = traces.map((t) => t.roundTrip).sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)]!;
  const live = traces.filter((t) => t.source === "engine").length;
  return (
    <div className="panel p-4">
      <div className="flex items-baseline justify-between gap-3">
        <p className="eyebrow">your queries, this session</p>
        <p className="num text-step--1 text-ink-dim">
          median <span className="text-ink">{fmtMs(median)} ms</span>
        </p>
      </div>
      <svg viewBox={`0 0 ${HISTORY * BW} ${H}`} className="mt-3 h-12 w-full" preserveAspectRatio="none" role="img" aria-label={`${traces.length} queries, median round trip ${fmtMs(median)} ms`}>
        <line x1="0" x2={HISTORY * BW} y1={H - 0.5} y2={H - 0.5} className="stroke-rule" />
        {traces.map((t, i) => {
          const h = Math.max(2, (t.roundTrip / peak) * (H - 4));
          return (
            <rect
              key={`${i}-${t.q}`}
              x={(HISTORY - traces.length + i) * BW + 2}
              y={H - h}
              width={BW - 4}
              height={h}
              rx="1.5"
              className={`${t.source === "engine" ? "fill-trace" : "fill-rule-strong"} grow-y`}
            >
              <title>{`${t.q}: ${fmtMs(t.roundTrip)} ms, ${t.source === "engine" ? "live engine" : "snapshot"}`}</title>
            </rect>
          );
        })}
      </svg>
      <p className="mt-2 font-mono text-[0.75rem] text-ink-dim">
        {traces.length} queries · {live} from the live engine · {traces.length - live} from the snapshot
      </p>
    </div>
  );
}

function Status({ reply, error, busy }: { reply: Reply | null; error: string | null; busy: boolean }) {
  if (busy && !reply) return <p className="font-mono text-step--1 text-ink-dim">Searching...</p>;
  if (error) return <p className="font-mono text-step--1 text-signal">{error}</p>;
  if (!reply) return <p className="font-mono text-step--1 text-ink-dim">Pick an example or type a task. Results show cosine distance.</p>;
  if (reply.source === "none") return <p className="font-mono text-step--1 text-ink-dim">None of those words are in the vocabulary. Try plainer English.</p>;
  const pending = busy ? <span className="text-ink-dim"> · searching</span> : null;
  if (reply.source === "engine") {
    return (
      <p className="font-mono text-step--1 text-ink-dim" data-source="engine">
        <span className="text-trace">Live engine results</span>
        {reply.engineMs !== null ? ` · ${fmtMs(reply.engineMs)} ms HNSW search on the server` : ""}
        {pending}
      </p>
    );
  }
  return (
    <p className="font-mono text-step--1 leading-relaxed" data-source="snapshot">
      <span className="text-signal">Saved snapshot results</span>
      <span className="text-ink-dim">
        {` · exact search over the same ${reply.corpusSize.toLocaleString("en-US")} embeddings in the site's route handler, not the live engine (${fmtMs(reply.snapshotMs)} ms)`}
      </span>
      {pending}
    </p>
  );
}
