import { Reveal } from "@/components/reveal";
import type { Headline } from "@/lib/bench";

export function Limitations({ headline }: { headline: Headline }) {
  const items: { title: string; body: string }[] = [
    {
      title: "It is slower than FAISS, by a measured margin.",
      body: headline.faiss_speedup
        ? `On ${headline.dataset} at matched recall, FAISS answers ${headline.faiss_speedup}× more queries per second on the same core. Python pays interpreter overhead on every graph hop; FAISS runs SIMD kernels over contiguous C++ memory.`
        : "Python pays interpreter overhead on every graph hop; FAISS runs SIMD kernels over contiguous C++ memory.",
    },
    { title: "One machine, one process.", body: "No sharding, no replication, no failover. If the host dies, the service is down until it restarts and replays its log." },
    {
      title: "The hosted engine runs on a free tier that sleeps.",
      body: "It spins down after 15 minutes without traffic, and the first request after that waits for a cold start of about a minute. The search section shows this while it happens and answers from a saved snapshot meanwhile.",
    },
    {
      title: "The hosted demo is small, by design.",
      body: "The free instance has 512 MB of RAM, so it serves a 3,178-document corpus. The benchmark numbers on this page come from local runs on 200,000 vectors per dataset and are served from committed results, not from the hosted engine.",
    },
    {
      title: "The hosted engine has no persistent disk.",
      body: "Anything written to it is lost on restart. Its demo index is rebuilt from a committed seed corpus when the image is built, so every restart comes back with the same demo; nothing else survives.",
    },
    { title: "One lock per collection.", body: "Writes and searches on a collection are serialised. Under the GIL finer locking buys little, but it does mean a long batch insert blocks searches on that collection." },
    { title: "Everything must fit in memory.", body: "Indexes live in RAM; segments are memory-mapped for durability, not for out-of-core search. There is no disk-resident graph." },
    { title: "Deletes are tombstones, and nothing compacts them.", body: "Deleted vectors still occupy the graph and still cost hops. A periodic rebuild would reclaim them; it is not implemented." },
    { title: "Selective filters fall back to a scan.", body: "Filter predicates are evaluated per vector in Python. Below 5 percent selectivity the engine switches to exact search over the matches; there is no inverted metadata index." },
    { title: "IVF is trained once.", body: "Centroids are learned from the first batch large enough to train on. Data that drifts away from them loses recall; there is no retraining." },
    { title: "The benchmark is a subset, single-threaded.", body: `Numbers come from ${headline.n_base.toLocaleString("en-US")} base vectors per dataset, one query at a time on one core, for both engines. FAISS with batching and all cores would be much faster again.` },
    { title: "The demo understands words, not meaning.", body: "Its embeddings are averaged GloVe word vectors. Queries that share no vocabulary with a docstring will miss it, however related they are." },
    { title: "Two static keys are the whole auth model.", body: "An admin key and a read-only demo key, from environment variables. No users, no rotation API, no per-tenant isolation. Rate limits are per process." },
  ];
  return (
    <ul className="grid border-l border-t border-rule md:grid-cols-2">
      {items.map((it) => (
        <Reveal as="li" key={it.title} className="border-b border-r border-rule p-6 md:p-8">
          <h3 className="text-step-0 font-medium">{it.title}</h3>
          <p className="mt-2 text-step--1 leading-relaxed text-ink-dim">{it.body}</p>
        </Reveal>
      ))}
    </ul>
  );
}
