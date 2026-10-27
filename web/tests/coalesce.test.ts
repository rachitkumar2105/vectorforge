import assert from "node:assert/strict";
import { test } from "node:test";

import { coalesce } from "../lib/coalesce.ts";

function counter<T>(value: T) {
  let calls = 0;
  let release: (() => void) | undefined;
  const fn = () => {
    calls += 1;
    return new Promise<T>((resolve) => {
      release = () => resolve(value);
    });
  };
  return { fn, calls: () => calls, release: () => release?.() };
}

test("concurrent callers share one in-flight call", async () => {
  const c = counter("live");
  const ping = coalesce(c.fn, 1000, () => 0);
  const all = Promise.all([ping(), ping(), ping()]);
  c.release();
  assert.deepEqual(await all, ["live", "live", "live"]);
  assert.equal(c.calls(), 1);
});

test("a settled answer is reused until the window passes", async () => {
  let t = 0;
  const c = counter("down");
  const ping = coalesce(c.fn, 1000, () => t);
  const first = ping();
  c.release();
  await first;
  t = 999;
  assert.equal(await ping(), "down");
  assert.equal(c.calls(), 1);
  t = 1000;
  const again = ping();
  c.release();
  await again;
  assert.equal(c.calls(), 2);
});

test("a failure is not cached", async () => {
  let calls = 0;
  const ping = coalesce(async () => {
    calls += 1;
    if (calls === 1) throw new Error("boom");
    return "live";
  }, 1000, () => 0);
  await assert.rejects(ping());
  assert.equal(await ping(), "live");
  assert.equal(calls, 2);
});
