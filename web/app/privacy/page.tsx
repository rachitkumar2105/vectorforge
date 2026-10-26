import type { Metadata } from "next";
import { connection } from "next/server";

import { LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Privacy (draft) · VectorForge" };

export default async function Privacy() {
  await connection();
  return (
    <LegalPage title="Privacy policy" updated="26 October 2026">
      <h2>What this site is</h2>
      <p>
        A portfolio project by Rachit Kumar Singh that demonstrates a vector database. It has no accounts, no
        sign-up and no newsletter.
      </p>
      <h2>What is collected</h2>
      <p>
        When you use the search demo, the text you type is sent to this site&apos;s server, turned into a vector, and
        the vector is sent to the VectorForge engine to find matching documents. The text and the vector are used only
        to answer that request. They are not stored by this site or by the engine.
      </p>
      <p>
        The hosting providers (Vercel for the site, and the provider hosting the engine) keep standard request logs,
        such as IP address, time, path and response status, for security and operations. The engine&apos;s own logs
        record the shape of each request (route, status, latency) and never the query, the vector or any key.
      </p>
      <h2>Cookies and tracking</h2>
      <p>This site sets no cookies and runs no analytics, advertising or third-party scripts.</p>
      <h2>Rate limiting</h2>
      <p>
        To prevent abuse, the demo counts requests per IP address in server memory for a few seconds. The count is
        not written anywhere and disappears when the server restarts.
      </p>
      <h2>Contact</h2>
      <p>Questions about this policy can be raised through the project&apos;s GitHub repository.</p>
    </LegalPage>
  );
}
