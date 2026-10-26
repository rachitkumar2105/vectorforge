import { SiteFooter } from "@/components/site-footer";
import { SiteNav } from "@/components/site-nav";

export function LegalPage({ title, updated, children }: { title: string; updated: string; children: React.ReactNode }) {
  return (
    <>
      <SiteNav />
      <main id="main" className="container-instrument py-16 md:py-24">
        <article className="max-w-[44rem]">
          <p className="eyebrow">Draft</p>
          <h1 className="mt-3 text-step-3 font-semibold tracking-tight">{title}</h1>
          <p className="mt-4 border border-signal/60 p-4 text-step--1 text-ink">
            This is a draft written for a portfolio project. It is not legal advice and has not been reviewed by a lawyer.
          </p>
          <p className="num mt-4 text-step--1 text-ink-dim">{`Last updated ${updated}`}</p>
          <div className="mt-10 flex flex-col gap-6 text-ink-dim [&_h2]:mt-4 [&_h2]:text-step-1 [&_h2]:font-medium [&_h2]:text-ink">
            {children}
          </div>
        </article>
      </main>
      <SiteFooter />
    </>
  );
}
