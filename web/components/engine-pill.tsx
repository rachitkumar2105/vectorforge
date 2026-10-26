"use client";

import { useEffect } from "react";

import { engineMonitor, startEngineMonitor, useEngine } from "@/lib/use-engine";
import type { EngineState } from "@/lib/engine-monitor";

const TEXT: Record<EngineState, string> = {
  checking: "checking engine",
  waking: "waking engine, about 45s",
  live: "engine live",
  unavailable: "engine asleep, showing saved results",
};

/**
 * Status of the hosted engine, inline in the live search section's header. Its box has a fixed
 * width and height at every breakpoint so nothing shifts as the text changes or as it fades.
 * The text always states the state; the dot is never the only signal.
 */
export function EnginePill() {
  const { state, elapsedMs, pillVisible } = useEngine();

  useEffect(() => startEngineMonitor(), []);

  // Drive the elapsed counter only while it is on screen.
  useEffect(() => {
    if (state !== "waking") return;
    const id = window.setInterval(() => engineMonitor.tick(), 1000);
    return () => window.clearInterval(id);
  }, [state]);

  const seconds = Math.floor(elapsedMs / 1000);
  return (
    <div className="h-9 w-full shrink-0 md:w-[22.5rem]">
      <div
        className="engine-pill flex h-9 w-full items-center gap-2.5 rounded-full border border-rule bg-panel px-3.5"
        data-visible={pillVisible ? "true" : "false"}
        aria-hidden={pillVisible ? undefined : true}
      >
        <span className="engine-dot shrink-0" data-state={state} aria-hidden="true" />
        <span className="min-w-0 flex-1 truncate font-mono text-step--1 text-ink">
          <span aria-live="polite">{TEXT[state]}</span>
          {/* The counter is not announced: the live region only speaks when the state changes. */}
          {state === "waking" ? (
            <span className="num text-ink-dim" aria-hidden="true">{` · ${seconds}s`}</span>
          ) : null}
        </span>
      </div>
    </div>
  );
}
