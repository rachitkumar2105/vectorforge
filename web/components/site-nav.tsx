import Link from "next/link";

import { IconGithub, IconMark, IconMenu } from "@/components/icons";
import { REPO_URL } from "@/lib/site";

const LINKS = [
  { href: "/#visualizer", label: "Visualizer" },
  { href: "/#benchmarks", label: "Benchmarks" },
  { href: "/#demo", label: "Search demo" },
  { href: "/#architecture", label: "Architecture" },
  { href: "/#limits", label: "Limits" },
];

export function SiteNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-rule bg-bg">
      <nav aria-label="Primary" className="container-instrument flex h-16 items-center justify-between gap-4">
        <Link href="/" className="flex min-h-11 items-center gap-2 font-mono text-step--1 tracking-wide">
          <IconMark className="text-trace" />
          <span>VectorForge</span>
        </Link>
        <ul className="hidden items-center gap-1 md:flex">
          {LINKS.map((l) => (
            <li key={l.href}>
              <Link href={l.href} className="link inline-flex min-h-11 items-center px-3 font-mono text-step--1 no-underline hover:underline">
                {l.label}
              </Link>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-2">
          <a href={REPO_URL} className="btn" rel="noopener noreferrer">
            <IconGithub />
            <span className="hidden sm:inline">Source</span>
          </a>
          {/* No-JS disclosure menu for narrow screens. */}
          <details className="relative md:hidden">
            <summary className="btn list-none [&::-webkit-details-marker]:hidden" aria-label="Sections">
              <IconMenu />
            </summary>
            <ul className="panel absolute right-0 mt-2 w-56 p-2">
              {LINKS.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="flex min-h-11 items-center px-3 font-mono text-step--1">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </details>
        </div>
      </nav>
    </header>
  );
}
