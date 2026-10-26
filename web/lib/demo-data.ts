import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { dequantize, type EmbedModel } from "@/lib/embed";

export type DemoDoc = { id: string; title: string; module: string; summary: string };

type VocabMeta = {
  dim: number;
  words: string[];
  weights: number[];
  vocab_quant: { min: number[]; step: number[] };
  docs_quant: { min: number[]; step: number[] };
  pc: number[];
  count: number;
};

export type DemoData = { model: EmbedModel; docs: DemoDoc[]; docVectors: Float32Array; dim: number };

let cached: Promise<DemoData> | null = null;

/** Loaded once per server instance; ~4 MB from web/data/demo (built by bench/demo/build_demo.py). */
export function demoData(): Promise<DemoData> {
  cached ??= load();
  return cached;
}

async function load(): Promise<DemoData> {
  const dir = join(process.cwd(), "data", "demo");
  const [metaRaw, vocabBin, docsRaw, docsBin] = await Promise.all([
    readFile(join(dir, "vocab.json"), "utf8"),
    readFile(join(dir, "vocab.bin")),
    readFile(join(dir, "docs.json"), "utf8"),
    readFile(join(dir, "docs.bin")),
  ]);
  const meta = JSON.parse(metaRaw) as VocabMeta;
  const docs = JSON.parse(docsRaw) as DemoDoc[];
  const asInt8 = (b: Buffer) => new Int8Array(b.buffer, b.byteOffset, b.byteLength);
  const model: EmbedModel = {
    dim: meta.dim,
    index: new Map(meta.words.map((w, i) => [w, i])),
    vectors: dequantize(asInt8(vocabBin), meta.dim, meta.vocab_quant.min, meta.vocab_quant.step),
    weights: Float32Array.from(meta.weights),
    pc: Float32Array.from(meta.pc),
  };
  const docVectors = dequantize(asInt8(docsBin), meta.dim, meta.docs_quant.min, meta.docs_quant.step);
  return { model, docs, docVectors, dim: meta.dim };
}
