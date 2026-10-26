// Typed access to the committed benchmark output. Every number the site shows about
// performance comes from these files, which `python bench/run_bench.py` writes.
import glove from "@/data/bench/glove.json";
import sift from "@/data/bench/sift.json";
import summary from "@/data/bench/summary.json";

export type BenchPoint = {
  param: number;
  recall_at_1: number;
  recall_at_10: number;
  qps: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
};

export type BenchSeries = {
  id: string;
  label: string;
  engine: "vectorforge" | "faiss";
  params: Record<string, unknown>;
  sweep: string | null;
  build_s: number;
  memory_bytes: number;
  memory_note: string;
  points: BenchPoint[];
};

export type BenchResult = {
  key: string;
  dataset: { name: string; subset: string; dim: number; metric: string; source: string };
  n_base: number;
  n_queries: number;
  dominates_flat: boolean;
  series: BenchSeries[];
  environment: {
    hardware: { cpu: string; logical_cores: number; ram_bytes: number; os: string; machine: string };
    versions: Record<string, string>;
    commit: string;
    command: string;
    started_at: string;
    threads: string;
  };
};

export type Headline = {
  dataset: string;
  dataset_key: string;
  ef_search: number;
  recall_at_10: number;
  qps: number;
  p50_ms: number;
  flat_qps: number;
  speedup_vs_flat: number;
  faiss_qps_at_same_recall: number | null;
  faiss_speedup: number | null;
  n_base: number;
};

export const results = [sift, glove] as unknown as BenchResult[];
export const headlines = (summary as unknown as { headline: Headline[] }).headline;
export const finishedAt = (summary as unknown as { finished_at: string }).finished_at;

export const REGENERATE = "python bench/datasets/download.py all && python bench/run_bench.py";

export function headlineFor(key: string): Headline | undefined {
  return headlines.find((h) => h.dataset_key === key);
}
