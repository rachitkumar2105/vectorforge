// Per-client token bucket for the public demo route. In-memory, so each serverless instance
// enforces its own budget; the engine's per-key bucket is the hard limit behind it.

export class TokenBucket {
  private buckets = new Map<string, { tokens: number; at: number }>();

  private readonly ratePerSecond: number;
  private readonly capacity: number;
  private readonly now: () => number;

  constructor(ratePerSecond: number, capacity: number, now: () => number = Date.now) {
    this.ratePerSecond = ratePerSecond;
    this.capacity = capacity;
    this.now = now;
  }

  /** 0 if allowed, otherwise whole seconds until a token is available. */
  take(key: string): number {
    const t = this.now();
    if (this.buckets.size > 10_000) this.buckets.clear(); // bound memory under a flood
    const b = this.buckets.get(key) ?? { tokens: this.capacity, at: t };
    b.tokens = Math.min(this.capacity, b.tokens + ((t - b.at) / 1000) * this.ratePerSecond);
    b.at = t;
    this.buckets.set(key, b);
    if (b.tokens >= 1) {
      b.tokens -= 1;
      return 0;
    }
    return Math.max(1, Math.ceil((1 - b.tokens) / this.ratePerSecond));
  }
}
