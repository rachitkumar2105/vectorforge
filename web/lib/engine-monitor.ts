// Engine readiness for the live search section. Pure logic with injected timers, so the exact
// schedule is unit tested (tests/engine-monitor.test.ts) and the React side stays thin.
//
//   checking ──(live within 2 s)──────────────▶ live ──(2 s)──▶ pill fades, state stays live
//      │
//      └─(no live answer within 2 s)──▶ waking ──(live)──▶ live
//                                          │
//                                          └─(90 s of retries)──▶ unavailable (persists)
//   unconfigured engine ─────────────────────────────────────────▶ unavailable
//
// Retries back off 1 s, 2 s, 4 s, 8 s, then every 8 s, within a 90 s budget of *visible* time:
// a hidden tab pauses polling and the elapsed counter, and resumes on focus.

export type EngineState = "checking" | "waking" | "live" | "unavailable";
export type PingResult = "live" | "down" | "unconfigured";
export type MonitorSnapshot = { state: EngineState; elapsedMs: number; pillVisible: boolean };

export const BACKOFF_MS = [1000, 2000, 4000, 8000] as const;
export const BUDGET_MS = 90_000;
export const WAKING_AFTER_MS = 2000;
export const LIVE_HOLD_MS = 2000;

export const nextDelay = (attempt: number) => BACKOFF_MS[Math.min(attempt, BACKOFF_MS.length - 1)]!;

type Handle = unknown;
type Deps = {
  ping: () => Promise<PingResult>;
  now: () => number;
  schedule: (fn: () => void, ms: number) => Handle;
  cancel: (h: Handle) => void;
};

export function createEngineMonitor(deps: Deps) {
  let snap: MonitorSnapshot = { state: "checking", elapsedMs: 0, pillVisible: true };
  const listeners = new Set<(s: MonitorSnapshot) => void>();
  let cycle = 0; // bumps on (re)start so stale ping answers are ignored
  let attempt = 0;
  let activeMs = 0; // visible time spent in this cycle
  let activeSince: number | null = null;
  let paused = false;
  let started = false;
  let pendingRetry = false;
  let retryTimer: Handle | null = null;
  let wakingTimer: Handle | null = null;
  let fadeTimer: Handle | null = null;

  const elapsed = () => activeMs + (activeSince === null ? 0 : deps.now() - activeSince);

  function set(patch: Partial<MonitorSnapshot>) {
    snap = { ...snap, ...patch, elapsedMs: elapsed() };
    listeners.forEach((l) => l(snap));
  }

  function clearTimers() {
    for (const t of [retryTimer, wakingTimer, fadeTimer]) if (t !== null) deps.cancel(t);
    retryTimer = wakingTimer = fadeTimer = null;
  }

  function ping() {
    const mine = cycle;
    deps.ping().then(
      (r) => mine === cycle && onAnswer(r),
      () => mine === cycle && onAnswer("down"),
    );
  }

  function onAnswer(r: PingResult) {
    if (r === "live") {
      clearTimers();
      set({ state: "live", pillVisible: true });
      fadeTimer = deps.schedule(() => set({ pillVisible: false }), LIVE_HOLD_MS);
      return;
    }
    if (r === "unconfigured") {
      clearTimers();
      set({ state: "unavailable", pillVisible: true });
      return;
    }
    scheduleRetry();
  }

  function scheduleRetry() {
    if (paused) {
      pendingRetry = true; // ping again as soon as the tab is visible
      return;
    }
    const delay = nextDelay(attempt++);
    if (elapsed() + delay > BUDGET_MS) {
      clearTimers();
      set({ state: "unavailable", pillVisible: true });
      return;
    }
    retryTimer = deps.schedule(() => {
      retryTimer = null;
      ping();
    }, delay);
  }

  function begin() {
    cycle++;
    clearTimers();
    attempt = 0;
    activeMs = 0;
    pendingRetry = false;
    activeSince = paused ? null : deps.now();
    set({ state: "checking", pillVisible: true });
    // Only a slow engine earns the "waking" state: a warm one answers well inside 2 s.
    wakingTimer = deps.schedule(() => {
      wakingTimer = null;
      if (snap.state === "checking") set({ state: "waking" });
    }, WAKING_AFTER_MS);
    ping();
  }

  return {
    start() {
      if (started) return;
      started = true;
      begin();
    },
    /** A live query failed: the engine may have gone back to sleep. */
    recheck() {
      if (snap.state === "live" || snap.state === "unavailable") begin();
    },
    pause() {
      if (paused) return;
      paused = true;
      if (activeSince !== null) activeMs += deps.now() - activeSince;
      activeSince = null;
      if (retryTimer !== null) {
        deps.cancel(retryTimer);
        retryTimer = null;
        pendingRetry = true;
      }
    },
    resume() {
      if (!paused) return;
      paused = false;
      activeSince = deps.now();
      if (pendingRetry && (snap.state === "checking" || snap.state === "waking")) {
        pendingRetry = false;
        ping();
      }
      set({});
    },
    tick() {
      set({});
    },
    get: () => snap,
    subscribe(fn: (s: MonitorSnapshot) => void) {
      listeners.add(fn);
      return () => void listeners.delete(fn);
    },
  };
}

export type EngineMonitor = ReturnType<typeof createEngineMonitor>;
