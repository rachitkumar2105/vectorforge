import { NextResponse, type NextRequest } from "next/server";

import { BodyTooLarge, readLimited } from "@/lib/body-limit";
import { demoData } from "@/lib/demo-data";
import { cosineTopK, embedQuery } from "@/lib/embed";
import { TokenBucket } from "@/lib/ratelimit";

// Read-only proxy for the public demo (S12, S13). The browser never sees an engine key or URL:
// both are server-only env vars read here. The engine URL is fixed configuration, never taken
// from the request, so this route cannot be pointed at another host (S16).
const ENGINE_URL = process.env.VECTORFORGE_ENGINE_URL;
const DEMO_KEY = process.env.VECTORFORGE_DEMO_KEY;
const ENGINE_TIMEOUT_MS = 2500;
// A valid body is a 200-character query and a small integer: well under 2 KiB.
const MAX_BODY_BYTES = 2048;
const limiter = new TokenBucket(1, 8);

export const runtime = "nodejs";

type Hit = { id: string; title: string; module: string; summary: string; distance: number };

function clientKey(req: NextRequest): string {
  // On Vercel the platform sets x-forwarded-for; its first entry is the client.
  return req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "local";
}

function bad(status: number, code: string, message: string, headers?: Record<string, string>) {
  return NextResponse.json({ error: { code, message } }, { status, headers });
}

export async function POST(req: NextRequest) {
  const started = performance.now();
  const wait = limiter.take(clientKey(req));
  if (wait) return bad(429, "rate_limited", "Too many searches. Try again shortly.", { "Retry-After": String(wait) });

  let body: unknown;
  try {
    body = JSON.parse(await readLimited(req, MAX_BODY_BYTES));
  } catch (err) {
    if (err instanceof BodyTooLarge) return bad(413, "payload_too_large", "Request body is too large.");
    return bad(400, "bad_request", "Body must be JSON.");
  }
  const query = (body as { query?: unknown })?.query;
  const kRaw = (body as { k?: unknown })?.k ?? 8;
  if (typeof query !== "string" || query.trim().length < 1 || query.length > 200) {
    return bad(422, "validation_error", "query must be 1 to 200 characters.");
  }
  if (typeof kRaw !== "number" || !Number.isInteger(kRaw) || kRaw < 1 || kRaw > 20) {
    return bad(422, "validation_error", "k must be an integer from 1 to 20.");
  }
  const k = kRaw;

  const data = await demoData();
  const vector = embedQuery(data.model, query);
  if (!vector) {
    return NextResponse.json({ source: "none", results: [], totalMs: elapsed(started), note: "no_known_words" });
  }

  if (ENGINE_URL && DEMO_KEY) {
    try {
      const res = await fetch(`${ENGINE_URL.replace(/\/$/, "")}/collections/demo/search`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": DEMO_KEY },
        body: JSON.stringify({ vector: Array.from(vector), k, ef_search: 64, include_metadata: true }),
        signal: AbortSignal.timeout(ENGINE_TIMEOUT_MS),
        cache: "no-store",
      });
      if (res.ok) {
        const payload = (await res.json()) as {
          results?: { id: string; distance: number; metadata?: Record<string, unknown> }[];
          took_ms?: number;
        };
        if (Array.isArray(payload.results)) {
          const results: Hit[] = payload.results.map((r) => ({
            id: String(r.id),
            title: String(r.metadata?.title ?? r.id),
            module: String(r.metadata?.module ?? ""),
            summary: String(r.metadata?.summary ?? ""),
            distance: Number(r.distance),
          }));
          return NextResponse.json({
            source: "engine",
            results,
            engineMs: typeof payload.took_ms === "number" ? payload.took_ms : null,
            totalMs: elapsed(started),
          });
        }
      }
    } catch {
      // Timeout or network failure: fall through to the snapshot. The error is not echoed.
    }
  }

  // Graceful degradation: exact cosine search over the same embeddings, in this route handler.
  const t = performance.now();
  const top = cosineTopK(data.docVectors, data.dim, vector, k);
  const results: Hit[] = top.map(({ index, distance }) => ({ ...data.docs[index]!, distance }));
  return NextResponse.json({
    source: "snapshot",
    reason: ENGINE_URL && DEMO_KEY ? "engine_unreachable" : "engine_not_configured",
    results,
    snapshotMs: elapsed(t),
    totalMs: elapsed(started),
    corpusSize: data.docs.length,
  });
}

const elapsed = (t: number) => Math.round((performance.now() - t) * 100) / 100;
