// Server-side engine client for the route handlers. The engine URL and the read-only demo key
// are server-only environment variables (no NEXT_PUBLIC_ prefix), read here and nowhere else.
// The URL is fixed configuration, never taken from a request, so no route can be pointed at
// another host (S16).

const ENGINE_URL = process.env.VECTORFORGE_ENGINE_URL?.replace(/\/$/, "");
const DEMO_KEY = process.env.VECTORFORGE_DEMO_KEY;

export const engineConfigured = () => Boolean(ENGINE_URL && DEMO_KEY);

/** A sleeping free-tier engine holds the request while it boots, so a timeout reads as "down"
 * and the browser keeps polling. 8 s stays inside Vercel Hobby's function time limit. */
export async function pingEngine(timeoutMs = 8000): Promise<"live" | "down" | "unconfigured"> {
  if (!engineConfigured()) return "unconfigured";
  try {
    const res = await fetch(`${ENGINE_URL}/readyz`, { signal: AbortSignal.timeout(timeoutMs), cache: "no-store" });
    return res.ok ? "live" : "down";
  } catch {
    return "down";
  }
}

export type EngineHit = { id: string; distance: number; metadata?: Record<string, unknown> };

/** Search the demo collection. Returns null on any failure; the caller falls back to the snapshot. */
export async function searchEngine(
  vector: Float32Array,
  k: number,
  timeoutMs = 4000,
): Promise<{ hits: EngineHit[]; tookMs: number | null } | null> {
  if (!engineConfigured()) return null;
  try {
    const res = await fetch(`${ENGINE_URL}/collections/demo/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": DEMO_KEY! },
      body: JSON.stringify({ vector: Array.from(vector), k, ef_search: 64, include_metadata: true }),
      signal: AbortSignal.timeout(timeoutMs),
      cache: "no-store",
    });
    if (!res.ok) return null;
    const payload = (await res.json()) as { results?: EngineHit[]; took_ms?: number };
    if (!Array.isArray(payload.results)) return null;
    return { hits: payload.results, tookMs: typeof payload.took_ms === "number" ? payload.took_ms : null };
  } catch {
    // Timeout or network failure. The error is not echoed to the client.
    return null;
  }
}
