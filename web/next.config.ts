import type { NextConfig } from "next";

// Headers that do not depend on a per-request nonce. The page CSP (with its nonce) is set in
// proxy.ts; API routes get a locked-down CSP here because they never serve HTML.
const securityHeaders = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
  },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // S17: never ship browser source maps in production (this is the default; stated explicitly).
  productionBrowserSourceMaps: false,
  reactStrictMode: true,
  // The search route reads the demo embeddings from disk at runtime; make sure they are bundled.
  outputFileTracingIncludes: { "/api/search": ["./data/demo/**"] },
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      {
        source: "/api/:path*",
        headers: [
          { key: "Content-Security-Policy", value: "default-src 'none'; frame-ancestors 'none'" },
          { key: "Cache-Control", value: "no-store" },
        ],
      },
    ];
  },
};

export default nextConfig;
