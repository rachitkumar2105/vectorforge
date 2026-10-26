// Query embedding for the semantic search demo. Mirrors bench/demo/build_demo.py exactly:
// SIF-weighted average of GloVe vectors, minus the corpus principal component, unit-normalised.
// Pure functions only; file loading lives in lib/demo-data.ts (server-only).

export type EmbedModel = {
  dim: number;
  index: Map<string, number>;
  vectors: Float32Array; // vocabulary x dim, dequantized
  weights: Float32Array;
  pc: Float32Array;
};

export function tokenize(text: string): string[] {
  const spaced = text
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .replaceAll("_", " ")
    .replaceAll(".", " ")
    .toLowerCase();
  return spaced.match(/[a-z]+/g) ?? [];
}

/** Inverse of vectorforge.core.quantize.ScalarQuantizer.encode: x = (code + 128) * step + min. */
export function dequantize(codes: Int8Array, dim: number, min: number[], step: number[]): Float32Array {
  const out = new Float32Array(codes.length);
  for (let i = 0; i < codes.length; i++) {
    const d = i % dim;
    out[i] = (codes[i]! + 128) * step[d]! + min[d]!;
  }
  return out;
}

export function embedQuery(model: EmbedModel, text: string): Float32Array | null {
  const ids = tokenize(text)
    .map((t) => model.index.get(t))
    .filter((i): i is number => i !== undefined);
  if (!ids.length) return null;
  const { dim, vectors, weights, pc } = model;
  const v = new Float32Array(dim);
  for (const id of ids) {
    const w = weights[id]!;
    for (let d = 0; d < dim; d++) v[d]! += (w * vectors[id * dim + d]!) / ids.length;
  }
  let proj = 0;
  for (let d = 0; d < dim; d++) proj += v[d]! * pc[d]!;
  let norm = 0;
  for (let d = 0; d < dim; d++) {
    v[d]! -= proj * pc[d]!;
    norm += v[d]! ** 2;
  }
  norm = Math.sqrt(norm);
  if (norm === 0) return null;
  for (let d = 0; d < dim; d++) v[d]! /= norm;
  return v;
}

/** Exact cosine search over unit vectors: the static-snapshot fallback when the engine is down. */
export function cosineTopK(docs: Float32Array, dim: number, q: Float32Array, k: number) {
  const n = docs.length / dim;
  const scored: { index: number; distance: number }[] = [];
  for (let i = 0; i < n; i++) {
    let dot = 0;
    for (let d = 0; d < dim; d++) dot += docs[i * dim + d]! * q[d]!;
    scored.push({ index: i, distance: 1 - dot });
  }
  return scored.sort((a, b) => a.distance - b.distance).slice(0, k);
}
