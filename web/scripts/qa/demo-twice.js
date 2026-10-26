// Two searches in a row: the second replaces the first result list (exit animations run).
// Reports console errors and CSP violations, which a single search does not exercise.
async (page) => {
  const p = await page.context().newPage();
    await p.bringToFront(); // background tabs get no animation frames
  await p.emulateMedia({ reducedMotion: "no-preference" });
  const errors = [];
  p.on("console", (m) => { if (["error", "warning"].includes(m.type())) errors.push(m.text().slice(0, 90)); });
  await p.addInitScript(() => {
    window.__v = [];
    document.addEventListener("securitypolicyviolation", (e) => window.__v.push(`${e.violatedDirective} ${e.sample || ""}`));
  });
  await p.goto("http://localhost:3000/", { waitUntil: "networkidle" });
  await p.locator("#demo").scrollIntoViewIfNeeded();
  await p.getByRole("button", { name: "compress data" }).click();
  await p.waitForTimeout(1500);
  await p.getByRole("button", { name: "send an email" }).click();
  await p.waitForTimeout(1500);
  const violations = await p.evaluate(() => window.__v);
  const titles = await p.locator("#demo ol li .text-trace").allInnerTexts();
  await p.close();
  return JSON.stringify({ errors: errors.length, sample: errors[0] ?? null, violations: violations.length, firstResults: titles.slice(0, 2) });
}
