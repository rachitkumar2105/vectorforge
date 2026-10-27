// Share one call of `fn` between everyone who asks while it is in flight, and reuse its answer
// for `ttlMs` after it settles (re-audit R3). The status pill polls from every open tab, so
// without this each poll would cost a function run and an engine request of its own.
// Failures are not cached: the next caller retries.

export function coalesce<T>(fn: () => Promise<T>, ttlMs: number, now: () => number = Date.now) {
  let inflight: Promise<T> | null = null;
  let cached: { value: T; at: number } | null = null;

  return function shared(): Promise<T> {
    if (cached && now() - cached.at < ttlMs) return Promise.resolve(cached.value);
    if (inflight) return inflight;
    inflight = fn().then(
      (value) => {
        cached = { value, at: now() };
        inflight = null;
        return value;
      },
      (err: unknown) => {
        inflight = null;
        throw err;
      },
    );
    return inflight;
  };
}
