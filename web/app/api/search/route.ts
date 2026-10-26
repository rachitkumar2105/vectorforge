import { NextResponse, type NextRequest } from "next/server";

import { BodyTooLarge, readLimited } from "@/lib/body-limit";
import { clientKey } from "@/lib/client-key";
import { demoData } from "@/lib/demo-data";
import { cosineTopK, embedQuery } from "@/lib/embed";
import { searchEngine } from "@/lib/engine";
import { TokenBucket } from "@/lib/ratelimit";

// Read-only proxy for the public demo (S12, S13). The browser never sees the engine key or URL.
//
// mode "snapshot": answer from the precomputed embeddings with exact search in this handler.
//   The page uses it while the engine is checking, waking or unavailable, so visitors are never
//   blocked on a cold start.
// mode "live": ask the engine; on any failure, fall back to the snapshot and say so.

// A valid body is a 200-character query, a small integer and a mode: well under 2 KiB.
const MAX_BODY_BYTES = 2048;
const limiter = new TokenBucket(1, 8);

export const runtime = "nodejs";
export const maxDuration = 10;

type Hit = { id: string; title: string; module: string; summary: string; distance: number };

function bad(status: number, code: string, message: string, headers?: Record<string, string>) {
  return NextResponse.json({ error: { code, message } }, { status, headers });
}

const elapsed = (t: number) => Math.round((performance.now() - t) * 100) / 100;

export async function POST(req: NextRequest) {
  const started = performance.now();
  const wait = limiter.take(clientKey(req.headers));
  if (wait) return bad(429, "rate_limited", "Too many searches. Try again shortly.", { "Retry-After": String(wait) });

  let body: unknown;
  try {
    body = JSON.parse(await readLimited(req, MAX_BODY_BYTES));
  } catch (err) {
    if (err instanceof BodyTooLarge) return bad(413, "payload_too_large", "Request body is too large.");
    return bad(400, "bad_request", "Body must be JSON.");
  }
  const { query, k: kRaw = 8, mode = "live" } = (body ?? {}) as { query?: unknown; k?: unknown; mode?: unknown };
  if (typeof query !== "string" || query.trim().length < 1 || query.length > 200) {
    return bad(422, "validation_error", "query must be 1 to 200 characters.");
  }
  if (typeof kRaw !== "number" || !Number.isInteger(kRaw) || kRaw < 1 || kRaw > 20) {
    return bad(422, "validation_error", "k must be an integer from 1 to 20.");
  }
  if (mode !== "live" && mode !== "snapshot") {
    return bad(422, "validation_error", 'mode must be "live" or "snapshot".');
  }
  const k = kRaw;

  const data = await demoData();
  const vector = embedQuery(data.model, query);
  if (!vector) {
    return NextResponse.json({ source: "none", results: [], totalMs: elapsed(started), note: "no_known_words" });
  }

  if (mode === "live") {
    const live = await searchEngine(vector, k);
    if (live) {
      const results: Hit[] = live.hits.map((r) => ({
        id: String(r.id),
        title: String(r.metadata?.title ?? r.id),
        module: String(r.metadata?.module ?? ""),
        summary: String(r.metadata?.summary ?? ""),
        distance: Number(r.distance),
      }));
      return NextResponse.json({ source: "engine", results, engineMs: live.tookMs, totalMs: elapsed(started) });
    }
  }

  // Snapshot: exact cosine search over the same embeddings the engine holds.
  const t = performance.now();
  const top = cosineTopK(data.docVectors, data.dim, vector, k);
  const results: Hit[] = top.map(({ index, distance }) => ({ ...data.docs[index]!, distance }));
  return NextResponse.json({
    source: "snapshot",
    reason: mode === "snapshot" ? "requested" : "engine_unreachable",
    results,
    snapshotMs: elapsed(t),
    totalMs: elapsed(started),
    corpusSize: data.docs.length,
  });
}
