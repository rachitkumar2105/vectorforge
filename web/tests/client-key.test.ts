import assert from "node:assert/strict";
import { test } from "node:test";

import { clientKey } from "../lib/client-key.ts";

const h = (o: Record<string, string>) => new Headers(o);

test("forwarding headers are ignored unless the platform is trusted", () => {
  // Self-hosted with no trusted proxy: a forged header must not buy a fresh bucket.
  assert.equal(clientKey(h({ "x-forwarded-for": "1.2.3.4" }), {}), "shared");
  assert.equal(clientKey(h({ "x-forwarded-for": "5.6.7.8" }), {}), "shared");
});

test("on Vercel the platform-set client address is used", () => {
  assert.equal(clientKey(h({ "x-real-ip": "9.9.9.9", "x-forwarded-for": "1.1.1.1, 2.2.2.2" }), { VERCEL: "1" }), "9.9.9.9");
  assert.equal(clientKey(h({ "x-forwarded-for": "1.1.1.1, 2.2.2.2" }), { VERCEL: "1" }), "1.1.1.1");
  assert.equal(clientKey(h({}), { VERCEL: "1" }), "shared");
});

test("an operator can name the trusted header for another proxy", () => {
  const env = { DEMO_TRUSTED_IP_HEADER: "cf-connecting-ip" };
  assert.equal(clientKey(h({ "cf-connecting-ip": "7.7.7.7", "x-forwarded-for": "6.6.6.6" }), env), "7.7.7.7");
});

test("overlong or empty header values fall back to the shared bucket", () => {
  assert.equal(clientKey(h({ "x-real-ip": "x".repeat(200) }), { VERCEL: "1" }), "shared");
  assert.equal(clientKey(h({ "x-real-ip": "  " }), { VERCEL: "1" }), "shared");
});
