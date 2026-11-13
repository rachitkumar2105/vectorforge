"use client";

import { useEngineState } from "@/lib/use-engine";
import type { EngineState } from "@/lib/engine-monitor";

const TEXT: Record<EngineState, string> = {
  checking: "checking the hosted engine",
  waking: "hosted engine waking from sleep",
  live: "hosted engine live",
  unavailable: "hosted engine asleep, demo uses the saved snapshot",
};

/**
 * One line under the hero readouts: the real state of the hosted engine, read from the page's
 * shared engine monitor (no extra polling), with a way into the live search.
 */
export function HeroLive() {
  const state = useEngineState();
  return (
    <p className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-rule pt-4 font-mono text-step--1">
      <span className="engine-dot shrink-0" data-state={state} aria-hidden="true" />
      <span className="text-ink" aria-live="polite">
        {TEXT[state]}
      </span>
      <a href="#demo" className="text-trace underline decoration-1 underline-offset-4 hover:decoration-2">
        run a real query
      </a>
    </p>
  );
}
