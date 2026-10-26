import Link from "next/link";

import { SiteFooter } from "@/components/site-footer";
import { SiteNav } from "@/components/site-nav";

export default function NotFound() {
  return (
    <>
      <SiteNav />
      <main id="main" className="container-instrument py-24">
        <p className="eyebrow">404</p>
        <h1 className="mt-3 text-step-3 font-semibold">No vector at this address</h1>
        <p className="mt-4 text-ink-dim">
          The page you asked for does not exist. <Link href="/" className="link">Back to the console</Link>.
        </p>
      </main>
      <SiteFooter />
    </>
  );
}
