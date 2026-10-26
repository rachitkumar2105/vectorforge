import { connection } from "next/server";

import { Architecture } from "@/components/architecture";
import { BenchExplorer } from "@/components/bench-explorer";
import { Hero } from "@/components/hero";
import { Limitations } from "@/components/limitations";
import { Reveal } from "@/components/reveal";
import { SearchDemo } from "@/components/search-demo";
import { SiteFooter } from "@/components/site-footer";
import { SiteNav } from "@/components/site-nav";
import { Visualizer } from "@/components/visualizer";
import { headlineFor, headlines, results } from "@/lib/bench";
import { demoData } from "@/lib/demo-data";

function SectionHead({ id, eyebrow, title, children }: { id: string; eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <Reveal className="mb-10 max-w-[46rem] md:mb-14">
      <p className="eyebrow">{eyebrow}</p>
      <h2 id={`${id}-title`} className="mt-3 text-step-3 font-semibold leading-tight tracking-tight">
        {title}
      </h2>
      <div className="mt-4 text-ink-dim">{children}</div>
    </Reveal>
  );
}

export default async function Page() {
  // Rendered per request so the CSP nonce from proxy.ts can be applied to every script.
  await connection();
  const corpusSize = (await demoData()).docs.length;
  const headline = headlineFor("sift") ?? headlines[0]!;

  return (
    <>
      <SiteNav />
      <main id="main">
        <Hero />

        <section id="visualizer" className="section" aria-labelledby="visualizer-title">
          <div className="container-instrument">
            <SectionHead id="visualizer" eyebrow="01 · The index" title="Watch a search descend the graph">
              <p>
                This is a real HNSW graph, built in your browser by the same algorithm as the engine. Click the bottom
                layer to drop a query. The search hops greedily across the sparse upper layers, then widens to{" "}
                <span className="num text-ink">ef_search</span> candidates on layer 0. Raise ef and watch it look at more
                nodes and miss fewer true neighbours.
              </p>
            </SectionHead>
            <Visualizer />
          </div>
        </section>

        <section id="benchmarks" className="section" aria-labelledby="benchmarks-title">
          <div className="container-instrument">
            <SectionHead id="benchmarks" eyebrow="02 · The measurement" title="Recall against throughput, next to FAISS">
              <p>
                Each line sweeps one knob: <span className="num text-ink">ef_search</span> for HNSW,{" "}
                <span className="num text-ink">nprobe</span> for IVF. Up and to the right is better. FAISS runs with the
                same parameters on the same machine, one thread, one query at a time. It is faster, and the gap is shown,
                not hidden.
              </p>
            </SectionHead>
            <BenchExplorer results={results} />
          </div>
        </section>

        <section id="demo" className="section" aria-labelledby="demo-title">
          <div className="container-instrument">
            <SectionHead id="demo" eyebrow="03 · The service" title="Search the standard library by meaning">
              <p>
                Your query is embedded on the server and sent to the hosted engine through a rate-limited, read-only route.
                The browser never holds a key. If the engine is down, the page says so and answers from a static snapshot.
              </p>
            </SectionHead>
            <SearchDemo corpusSize={corpusSize} />
          </div>
        </section>

        <section id="architecture" className="section" aria-labelledby="architecture-title">
          <div className="container-instrument">
            <SectionHead id="architecture" eyebrow="04 · The machine" title="Write path, then read path">
              <p>Scroll through the steps. Each one is a single decision the engine makes, and why.</p>
            </SectionHead>
            <Architecture />
          </div>
        </section>

        <section id="limits" className="section" aria-labelledby="limits-title">
          <div className="container-instrument">
            <SectionHead id="limits" eyebrow="05 · The boundary" title="What VectorForge does not do">
              <p>Knowing where a system stops is part of building it. These are the edges, stated plainly.</p>
            </SectionHead>
            <Limitations headline={headline} />
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
