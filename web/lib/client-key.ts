// Which rate-limit bucket a demo request belongs to (audit finding 4).
//
// Forwarding headers are client-controlled unless a proxy we trust overwrites them. On Vercel
// the platform sets x-real-ip / x-forwarded-for itself, so they identify the client. Behind any
// other proxy the operator must name the header that proxy sets (DEMO_TRUSTED_IP_HEADER).
// Otherwise every request shares one bucket: stricter, but a forged header buys nothing.

type Env = Record<string, string | undefined>;

const SHARED = "shared";

function clean(value: string | null | undefined): string | null {
  const v = value?.split(",")[0]?.trim();
  return v && v.length <= 64 ? v : null;
}

export function clientKey(headers: Headers, env: Env = process.env): string {
  const named = env.DEMO_TRUSTED_IP_HEADER;
  if (named) return clean(headers.get(named)) ?? SHARED;
  if (env.VERCEL === "1") {
    return clean(headers.get("x-real-ip")) ?? clean(headers.get("x-forwarded-for")) ?? SHARED;
  }
  return SHARED;
}
