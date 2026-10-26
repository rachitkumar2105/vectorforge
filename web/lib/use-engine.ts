"use client";

import { useSyncExternalStore } from "react";

import { createEngineMonitor, type MonitorSnapshot, type PingResult } from "@/lib/engine-monitor";

// One monitor per page, shared by the status pill (which starts it) and the search demo (which
// reads it). Only the live search section depends on the engine; nothing else waits on it.

async function ping(): Promise<PingResult> {
  const res = await fetch("/api/engine-health", { cache: "no-store" });
  if (!res.ok) return "down";
  const body = (await res.json()) as { engine?: PingResult };
  return body.engine ?? "down";
}

const monitor = createEngineMonitor({
  ping,
  now: () => performance.now(),
  schedule: (fn, ms) => window.setTimeout(fn, ms),
  cancel: (h) => window.clearTimeout(h as number),
});

let wired = false;

/** Start polling once, and pause it while the tab is hidden (resume on visibility or focus). */
export function startEngineMonitor() {
  if (wired) return;
  wired = true;
  const sync = () => (document.visibilityState === "hidden" ? monitor.pause() : monitor.resume());
  document.addEventListener("visibilitychange", sync);
  window.addEventListener("focus", () => monitor.resume());
  if (document.visibilityState === "hidden") monitor.pause();
  monitor.start();
}

export const engineMonitor = monitor;

const SERVER_SNAPSHOT: MonitorSnapshot = { state: "checking", elapsedMs: 0, pillVisible: true };

export function useEngine(): MonitorSnapshot {
  return useSyncExternalStore(monitor.subscribe, monitor.get, () => SERVER_SNAPSHOT);
}

/** Just the state, for components that should not re-render on every counter tick. */
export function useEngineState(): MonitorSnapshot["state"] {
  return useSyncExternalStore(
    monitor.subscribe,
    () => monitor.get().state,
    () => SERVER_SNAPSHOT.state,
  );
}
