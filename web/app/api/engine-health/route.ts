import { NextResponse } from "next/server";

import { clientKey } from "@/lib/client-key";
import { pingEngine } from "@/lib/engine";
import { TokenBucket } from "@/lib/ratelimit";

// Readiness probe for the live search section's status pill. Each call also wakes a sleeping
// free-tier engine, because any request to it starts the boot.
export const runtime = "nodejs";
export const maxDuration = 10;

// The browser polls on a 1-2-4-8 s backoff; this allows that comfortably with a few tabs open.
const limiter = new TokenBucket(1, 10);

export async function GET(req: Request) {
  const wait = limiter.take(clientKey(req.headers));
  if (wait) {
    return NextResponse.json(
      { error: { code: "rate_limited", message: "Too many checks." } },
      { status: 429, headers: { "Retry-After": String(wait) } },
    );
  }
  return NextResponse.json({ engine: await pingEngine() });
}
