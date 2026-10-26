import assert from "node:assert/strict";
import { test } from "node:test";

import { BodyTooLarge, readLimited } from "../lib/body-limit.ts";

const post = (body: BodyInit, headers: Record<string, string> = {}) =>
  new Request("http://localhost/api/search", { method: "POST", body, headers, duplex: "half" } as RequestInit);

test("reads a small body", async () => {
  assert.equal(await readLimited(post('{"query":"x"}'), 64), '{"query":"x"}');
});

test("rejects by declared Content-Length before reading", async () => {
  await assert.rejects(readLimited(post("x".repeat(10), { "content-length": "100000" }), 64), BodyTooLarge);
});

test("rejects a body that streams past the limit without a Content-Length", async () => {
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      for (let i = 0; i < 10; i++) c.enqueue(new Uint8Array(100));
      c.close();
    },
  });
  await assert.rejects(readLimited(post(stream), 512), BodyTooLarge);
});

test("empty body reads as empty string", async () => {
  assert.equal(await readLimited(new Request("http://localhost/", { method: "POST" }), 64), "");
});
