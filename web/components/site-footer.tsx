import Link from "next/link";

import { IconGithub, IconMark } from "@/components/icons";
import { AUTHOR, REPO_URL } from "@/lib/site";

export function SiteFooter() {
  return (
    <footer className="border-t border-rule">
      <div className="container-instrument flex flex-col gap-6 py-10 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2 font-mono text-step--1 text-ink-dim">
          <IconMark className="text-trace" />
          <span>{`VectorForge · built by ${AUTHOR}`}</span>
        </div>
        <ul className="flex flex-wrap gap-x-2 gap-y-1 font-mono text-step--1">
          <li>
            <a href={REPO_URL} className="link inline-flex min-h-11 items-center gap-2 px-2" rel="noopener noreferrer">
              <IconGithub /> GitHub
            </a>
          </li>
          <li>
            <Link href="/privacy" className="link inline-flex min-h-11 items-center px-2">
              Privacy
            </Link>
          </li>
          <li>
            <Link href="/terms" className="link inline-flex min-h-11 items-center px-2">
              Terms
            </Link>
          </li>
        </ul>
      </div>
    </footer>
  );
}
