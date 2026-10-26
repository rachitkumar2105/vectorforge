// Generated from web/scripts/qa by swapping the base URL for production; see DEMO-REPORT.md.
// Load, interact with every section, and report console errors/warnings and CSP violations.
async (page) => {
  await page.bringToFront(); // background tabs get no animation frames
  await page.emulateMedia({ reducedMotion: "no-preference" }); // sessions keep emulation between runs
  const msgs = [];
  page.on("console", (m) => { if (["error", "warning"].includes(m.type())) msgs.push(`${m.type()}: ${m.text()}`); });
  page.on("pageerror", (e) => msgs.push(`pageerror: ${e.message}`));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("https://vectorforge-olive.vercel.app/", { waitUntil: "networkidle" });
  await page.evaluate(() => {
    window.__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => window.__csp.push(`${e.violatedDirective} ${e.blockedURI}`));
  });
  await page.locator("#visualizer svg").first().click({ position: { x: 300, y: 420 } });
  await page.waitForTimeout(1500);
  await page.locator("#ef").fill("40");
  await page.locator("#benchmarks").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: /GloVe/ }).click();
  await page.locator("#demo").scrollIntoViewIfNeeded();
  await page.getByRole("button", { name: "compress data" }).click();
  await page.waitForTimeout(1500);
  const status = await page.locator("#demo .panel[aria-live]").innerText();
  await page.locator("#architecture").scrollIntoViewIfNeeded();
  await page.mouse.wheel(0, 3000);
  await page.waitForTimeout(800);
  await page.goto("https://vectorforge-olive.vercel.app/privacy", { waitUntil: "networkidle" });
  const csp = await page.evaluate(() => window.__csp ?? []);
  return JSON.stringify({ messages: msgs, cspViolationsAfterInteraction: csp, demoStatus: status.slice(0, 300) });
}
