import type { Metadata } from "next";
import { connection } from "next/server";

import { LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Terms (draft) · VectorForge" };

export default async function Terms() {
  await connection();
  return (
    <LegalPage title="Terms of use" updated="26 October 2026">
      <h2>The service</h2>
      <p>
        This site and its search demo are provided as a demonstration, free of charge, as they are, with no promise
        of availability, accuracy or fitness for any purpose. The demo may be slow, rate limited, or unavailable.
      </p>
      <h2>Acceptable use</h2>
      <p>
        Do not attempt to overload, probe for vulnerabilities in, or bypass the rate limits of the site or the engine,
        and do not submit personal or sensitive information in search queries.
      </p>
      <h2>Content</h2>
      <p>
        The demo corpus is made of docstrings from the Python standard library, used under the Python Software
        Foundation licence. Word vectors are from the GloVe project (Stanford NLP). Benchmark data comes from the
        public SIFT1M (INRIA TEXMEX) and GloVe datasets.
      </p>
      <h2>Liability</h2>
      <p>To the extent the law allows, the author is not liable for any loss arising from use of this site.</p>
      <h2>Changes</h2>
      <p>These terms may change. The date above shows the latest revision.</p>
    </LegalPage>
  );
}
