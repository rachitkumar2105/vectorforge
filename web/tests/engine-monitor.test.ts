import assert from "node:assert/strict";
import { test } from "node:test";

import { BACKOFF_MS, BUDGET_MS, createEngineMonitor, nextDelay, type PingResult } from "../lib/engine-monitor.ts";

// A fake clock and scheduler: timers fire only when the test advances time.
function harness(answers: Array<{ result: PingResult; afterMs: number }>) {
  let now = 0;
  let seq = 0;
  const timers = new Map<number, { at: number; fn: () => void }>();
  const pings: number[] = [];
  const ping = () =>
    new Promise<PingResult>((resolve) => {
      const a = answers[Math.min(pings.length, answers.length - 1)]!;
      pings.push(now);
      const id = ++seq;
      timers.set(id, { at: now + a.afterMs, fn: () => resolve(a.result) });
    });
  const monitor = createEngineMonitor({
    ping,
    now: () => now,
    schedule: (fn, ms) => {
      const id = ++seq;
      timers.set(id, { at: now + ms, fn });
      return id;
    },
    cancel: (id) => void timers.delete(id as number),
  });
  async function advance(ms: number) {
    const end = now + ms;
    for (;;) {
      const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!due) break;
      timers.delete(due[0]);
      now = due[1].at;
      due[1].fn();
      await new Promise((r) => setImmediate(r)); // let promise callbacks run
    }
    now = end;
    await new Promise((r) => setImmediate(r));
  }
  return { monitor, advance, pings, timers };
}

test("backoff is 1s, 2s, 4s, 8s, then every 8s", () => {
  assert.deepEqual(BACKOFF_MS, [1000, 2000, 4000, 8000]);
  assert.deepEqual([0, 1, 2, 3, 4, 9].map(nextDelay), [1000, 2000, 4000, 8000, 8000, 8000]);
  assert.equal(BUDGET_MS, 90_000);
});

test("a warm engine goes checking -> live without ever showing waking", async () => {
  const h = harness([{ result: "live", afterMs: 300 }]);
  const seen: string[] = [];
  h.monitor.subscribe((s) => seen.push(s.state));
  h.monitor.start();
  assert.equal(h.monitor.get().state, "checking");
  await h.advance(300);
  assert.equal(h.monitor.get().state, "live");
  assert.ok(!seen.includes("waking"));
  assert.equal(h.monitor.get().pillVisible, true);
  await h.advance(2000); // hold for 2 s, then the pill fades
  assert.equal(h.monitor.get().pillVisible, false);
  assert.equal(h.monitor.get().state, "live");
});

test("a slow first ping shows waking after 2 s, then live", async () => {
  const h = harness([{ result: "live", afterMs: 30_000 }]);
  h.monitor.start();
  await h.advance(1999);
  assert.equal(h.monitor.get().state, "checking");
  await h.advance(1);
  assert.equal(h.monitor.get().state, "waking");
  await h.advance(28_000);
  assert.equal(h.monitor.get().state, "live");
});

test("retries follow the backoff schedule and give up after 90 s as unavailable", async () => {
  const h = harness([{ result: "down", afterMs: 100 }]);
  h.monitor.start();
  await h.advance(100);
  assert.equal(h.monitor.get().state, "checking");
  await h.advance(1900);
  assert.equal(h.monitor.get().state, "waking"); // no live answer within 2 s
  await h.advance(120_000);
  assert.equal(h.monitor.get().state, "unavailable");
  const gaps = h.pings.slice(1).map((t, i) => t - h.pings[i]!);
  // Each gap = previous ping's 100 ms answer + the backoff delay.
  assert.deepEqual(gaps.slice(0, 5), [1100, 2100, 4100, 8100, 8100]);
  assert.ok(h.pings.at(-1)! <= 90_000, `last ping at ${h.pings.at(-1)}`);
  const count = h.pings.length;
  await h.advance(60_000);
  assert.equal(h.pings.length, count, "unavailable persists: no more polling");
});

test("an unconfigured engine is unavailable immediately", async () => {
  const h = harness([{ result: "unconfigured", afterMs: 50 }]);
  h.monitor.start();
  await h.advance(50);
  assert.equal(h.monitor.get().state, "unavailable");
  assert.equal(h.pings.length, 1);
});

test("hidden tab pauses polling and the elapsed counter; focus resumes", async () => {
  const h = harness([{ result: "down", afterMs: 100 }]);
  h.monitor.start();
  await h.advance(3000);
  const before = h.pings.length;
  const elapsed = h.monitor.get().elapsedMs;
  h.monitor.pause();
  await h.advance(60_000);
  assert.equal(h.pings.length, before, "no pings while hidden");
  assert.equal(h.monitor.get().elapsedMs, elapsed, "elapsed does not count hidden time");
  h.monitor.resume();
  await h.advance(100);
  assert.equal(h.pings.length, before + 1, "resume pings straight away");
  assert.equal(h.monitor.get().state, "waking");
});

test("recheck after a failed live query starts a fresh cycle", async () => {
  const h = harness([
    { result: "live", afterMs: 100 },
    { result: "down", afterMs: 100 },
    { result: "live", afterMs: 100 },
  ]);
  h.monitor.start();
  await h.advance(3000);
  assert.equal(h.monitor.get().state, "live");
  h.monitor.recheck();
  assert.equal(h.monitor.get().state, "checking");
  await h.advance(5000);
  assert.equal(h.monitor.get().state, "live");
});
