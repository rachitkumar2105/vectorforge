"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

import type { BenchResult } from "@/lib/bench";

// The interactive sections are code-split and mounted when they come near the viewport or when
// the browser is first idle after load, whichever is sooner, so the first screen hydrates almost
// no JavaScript (Lighthouse mobile measured 740 ms of blocking time before this). Placeholders
// reserve height so nothing shifts.

const VisualizerImpl = dynamic(() => import("@/components/visualizer").then((m) => m.Visualizer), { ssr: false });
const BenchImpl = dynamic(() => import("@/components/bench-explorer").then((m) => m.BenchExplorer), { ssr: false });
const DemoImpl = dynamic(() => import("@/components/search-demo").then((m) => m.SearchDemo), { ssr: false });
const ArchitectureImpl = dynamic(() => import("@/components/architecture").then((m) => m.Architecture), { ssr: false });

const queue: (() => void)[] = [];
let draining = false;

// Safari has no requestIdleCallback; fall back to a plain timeout there.
function idle(cb: () => void) {
  if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(cb, { timeout: 6000 });
  else globalThis.setTimeout(cb, 1500);
}

function enqueue(mount: () => void) {
  queue.push(mount);
  if (draining) return;
  draining = true;
  const next = () => {
    const job = queue.shift();
    if (!job) {
      draining = false;
      return;
    }
    job();
    idle(next);
  };
  idle(next);
}

function WhenNear({ placeholder, children }: { placeholder: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setNear(true);
          io.disconnect();
        }
      },
      { rootMargin: "600px 0px" },
    );
    io.observe(el);
    // Also mount once the browser is idle after load, so keyboard users can Tab into every
    // section without scrolling first (an unmounted section has nothing focusable). Sections join
    // a queue and mount one per idle period, so no single task grows long.
    const start = () => enqueue(() => setNear(true));
    if (document.readyState === "complete") start();
    else window.addEventListener("load", start, { once: true });
    return () => {
      io.disconnect();
      window.removeEventListener("load", start);
    };
  }, []);
  return <div ref={ref}>{near ? children : <div className={`panel ${placeholder}`} aria-hidden="true" />}</div>;
}

export const LazyVisualizer = () => (
  <WhenNear placeholder="aspect-[3/4] md:aspect-[16/10]">
    <VisualizerImpl />
  </WhenNear>
);

export const LazyBench = ({ results }: { results: BenchResult[] }) => (
  <WhenNear placeholder="h-[640px]">
    <BenchImpl results={results} />
  </WhenNear>
);

export const LazyDemo = ({ corpusSize }: { corpusSize: number }) => (
  <WhenNear placeholder="h-[360px]">
    <DemoImpl corpusSize={corpusSize} />
  </WhenNear>
);

export const LazyArchitecture = () => (
  <WhenNear placeholder="h-[720px]">
    <ArchitectureImpl />
  </WhenNear>
);
