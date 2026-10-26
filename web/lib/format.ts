export const fmtInt = (n: number) => Math.round(n).toLocaleString("en-US");

export function fmtQps(n: number): string {
  if (n >= 10_000) return `${(n / 1000).toFixed(1)}k`;
  if (n >= 1000) return `${(n / 1000).toFixed(2)}k`;
  return n.toFixed(n < 100 ? 1 : 0);
}

export const fmtRecall = (r: number) => r.toFixed(3);

export function fmtBytes(b: number): string {
  if (b >= 1e9) return `${(b / 1e9).toFixed(2)} GB`;
  if (b >= 1e6) return `${(b / 1e6).toFixed(1)} MB`;
  return `${(b / 1e3).toFixed(0)} kB`;
}

export const fmtMs = (ms: number) => (ms < 1 ? ms.toFixed(3) : ms < 10 ? ms.toFixed(2) : ms.toFixed(1));

/** Axis ticks: 20, 500, 2k, 10k. */
export const fmtTick = (v: number) => (v >= 1000 ? `${+(v / 1000).toPrecision(3)}k` : `${+v.toPrecision(3)}`);
