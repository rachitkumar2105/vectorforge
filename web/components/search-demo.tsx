"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useState } from "react";

import { IconSearch } from "@/components/icons";
import { fmtMs } from "@/lib/format";

type Hit = { id: string; title: string; module: string; summary: string; distance: number };
type Reply =
  | { source: "engine"; results: Hit[]; engineMs: number | null; totalMs: number }
  | { source: "snapshot"; reason: string; results: Hit[]; snapshotMs: number; totalMs: number; corpusSize: number }
  | { source: "none"; results: []; totalMs: number; note: string };

const PRESETS = ["read a file line by line", "compress data", "send an email", "parse a date from text", "random number", "wait for a thread"];

export function SearchDemo({ corpusSize }: { corpusSize: number }) {
  const [query, setQuery] = useState("");
  const [reply, setReply] = useState<Reply | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [roundTrip, setRoundTrip] = useState<number | null>(null);
  // Bumped per answer, so the result list re-keys on a new answer and not on every keystroke.
  const [answer, setAnswer] = useState(0);
  const reduce = useReducedMotion();

  async function run(q: string) {
    const text = q.trim();
    if (!text) return;
    setQuery(text);
    setBusy(true);
    setError(null);
    const t = performance.now();
    try {
      const res = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: text, k: 8 }),
      });
      const body = await res.json();
      setRoundTrip(performance.now() - t);
      if (!res.ok) {
        // Our own route's message (rate limit, validation); never an engine error string.
        setError(typeof body?.error?.message === "string" ? body.error.message : "Search failed.");
        setReply(null);
      } else {
        setReply(body as Reply);
        setAnswer((n) => n + 1);
      }
    } catch {
      setError("Network error. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

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
          <button type="submit" className="btn btn-primary" disabled={busy} aria-label="Search">
            <IconSearch />
          </button>
        </form>
        <div className="flex flex-wrap gap-2" aria-label="Example queries">
          {PRESETS.map((p) => (
            <button key={p} type="button" className="btn" onClick={() => void run(p)} disabled={busy}>
              {p}
            </button>
          ))}
        </div>
        <p className="text-step--1 leading-relaxed text-ink-dim">
          {`${corpusSize.toLocaleString("en-US")} docstrings from the Python standard library, embedded with SIF-weighted GloVe vectors. `}
          Word vectors, not a language model: matches are about shared vocabulary, and that is part of the demonstration.
        </p>
      </div>

      <div className="panel min-h-[22rem] p-4 md:p-5" aria-live="polite" aria-busy={busy}>
        <Status reply={reply} error={error} busy={busy} roundTrip={roundTrip} />
        {/* One keyed list per answer: the old list fades out, then the new one steps in. mode="wait"
            needs no injected <style> element, unlike "popLayout", which the nonce CSP would block. */}
        <AnimatePresence initial={false} mode="wait">
          <motion.ol
            key={answer}
            className="mt-4 flex flex-col"
            initial={false}
            exit={reduce ? undefined : { opacity: 0, transition: { duration: 0.15 } }}
          >
            {reply?.results.map((h, i) => (
              <motion.li
                key={h.id}
                initial={reduce ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: reduce ? 0 : i * 0.035, ease: [0.22, 1, 0.36, 1] }}
                className="border-t border-rule py-3 first:border-t-0"
              >
                <div className="flex items-baseline justify-between gap-4">
                  <span className="num break-all text-step--1 text-trace">{h.title}</span>
                  <span className="num shrink-0 text-step--1 text-ink-dim">{h.distance.toFixed(3)}</span>
                </div>
                <p className="mt-1 text-step--1 leading-relaxed text-ink">{h.summary}</p>
              </motion.li>
            ))}
          </motion.ol>
        </AnimatePresence>
      </div>
    </div>
  );
}

function Status({ reply, error, busy, roundTrip }: { reply: Reply | null; error: string | null; busy: boolean; roundTrip: number | null }) {
  if (busy) return <p className="font-mono text-step--1 text-ink-dim">Searching...</p>;
  if (error) return <p className="font-mono text-step--1 text-signal">{error}</p>;
  if (!reply) return <p className="font-mono text-step--1 text-ink-dim">Pick an example or type a task. Results show cosine distance.</p>;
  if (reply.source === "none") return <p className="font-mono text-step--1 text-ink-dim">None of those words are in the vocabulary. Try plainer English.</p>;
  const rt = roundTrip !== null ? `${fmtMs(roundTrip)} ms round trip` : "";
  if (reply.source === "engine") {
    return (
      <p className="font-mono text-step--1 text-ink-dim">
        <span className="text-trace">Live engine</span>
        {reply.engineMs !== null ? ` · ${fmtMs(reply.engineMs)} ms HNSW search on the server` : ""} · {rt}
      </p>
    );
  }
  return (
    <p className="font-mono text-step--1 leading-relaxed">
      <span className="text-signal">Engine {reply.reason === "engine_not_configured" ? "not connected" : "unreachable"}.</span>{" "}
      <span className="text-ink-dim">
        {`Served from the static snapshot: exact search over the same ${reply.corpusSize.toLocaleString("en-US")} embeddings inside the site's route handler (${fmtMs(reply.snapshotMs)} ms) · ${rt}`}
      </span>
    </p>
  );
}
