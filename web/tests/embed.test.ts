import assert from "node:assert/strict";
import { test } from "node:test";

import { cosineTopK, dequantize, embedQuery, tokenize, type EmbedModel } from "../lib/embed.ts";
import { TokenBucket } from "../lib/ratelimit.ts";

test("tokenize splits identifiers and lowercases", () => {
  assert.deepEqual(tokenize("Read_Text from TextIOWrapper!"), ["read", "text", "from", "text", "io", "wrapper"]);
  assert.deepEqual(tokenize("   "), []);
});

test("dequantize matches the Python scalar quantizer layout", () => {
  const codes = new Int8Array([-128, 127, 0, -1]);
  const out = dequantize(codes, 2, [0, 10], [1, 0.5]);
  assert.deepEqual(Array.from(out), [0, 10 + 255 * 0.5, 128, 10 + 127 * 0.5]);
});

const model: EmbedModel = {
  dim: 2,
  index: new Map([
    ["alpha", 0],
    ["beta", 1],
  ]),
  vectors: new Float32Array([1, 0, 0, 1]),
  weights: new Float32Array([1, 1]),
  pc: new Float32Array([0, 0]),
};

test("embedQuery averages known words and unit-normalises", () => {
  const v = embedQuery(model, "alpha beta gamma");
  assert.ok(v);
  assert.ok(Math.abs(v[0]! - Math.SQRT1_2) < 1e-6 && Math.abs(v[1]! - Math.SQRT1_2) < 1e-6);
  assert.equal(embedQuery(model, "gamma delta"), null);
});

test("cosineTopK ranks by dot product", () => {
  const docs = new Float32Array([1, 0, 0, 1, 0.7, 0.7]);
  const top = cosineTopK(docs, 2, new Float32Array([1, 0]), 2);
  assert.deepEqual(top.map((t) => t.index), [0, 2]);
  assert.ok(top[0]!.distance < top[1]!.distance);
});

test("token bucket allows a burst then refuses with a retry hint", () => {
  let now = 0;
  const bucket = new TokenBucket(1, 2, () => now);
  assert.equal(bucket.take("ip"), 0);
  assert.equal(bucket.take("ip"), 0);
  assert.ok(bucket.take("ip") > 0);
  now += 1000;
  assert.equal(bucket.take("ip"), 0);
  assert.equal(bucket.take("other"), 0);
});
