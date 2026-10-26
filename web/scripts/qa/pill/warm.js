// Warm engine: checking -> live with no "waking" flash, the pill fades after 2 s, layout never moves.
// Run: playwright-cli --raw run-code --filename=web/scripts/qa/pill/warm.js  (engine running)
async (page) => {
  const p = await page.context().newPage();
    await p.bringToFront(); // background tabs get no animation frames
  await p.emulateMedia({ reducedMotion: "no-preference" });
  await p.setViewportSize({ width: 1440, height: 900 });
  await p.addInitScript(() => {
    window.__pill = [];
    const t0 = performance.now();
    new MutationObserver(() => {
      const el = document.querySelector(".engine-pill [aria-live]");
      const txt = el ? el.textContent : "";
      const last = window.__pill[window.__pill.length - 1];
      if (txt && (!last || last.text !== txt)) window.__pill.push({ t: Math.round(performance.now() - t0), text: txt });
    }).observe(document, { subtree: true, childList: true, characterData: true });
  });
  await p.goto("http://localhost:3000/#demo", { waitUntil: "domcontentloaded" });
  // Position of the description relative to its own section: unaffected by page scrolling, so
  // any change means the pill pushed the layout.
  const offset = () => p.evaluate(() => {
    const d = document.querySelector("#demo-title").parentElement.nextElementSibling.getBoundingClientRect();
    const s = document.querySelector("#demo").getBoundingClientRect();
    return [Math.round(d.top - s.top), Math.round(d.left - s.left)].join(",");
  });
  const box0 = await offset();
  await p.waitForTimeout(800);
  await p.locator("#demo").screenshot({ path: "docs/demo/pill/live.jpg", type: "jpeg", quality: 60 });
  await p.waitForTimeout(2600);
  const box1 = await offset();
  const visible = await p.locator(".engine-pill").getAttribute("data-visible");
  const opacity = await p.locator(".engine-pill").evaluate((e) => getComputedStyle(e).opacity);
  await p.locator("#demo").screenshot({ path: "docs/demo/pill/live-faded.jpg", type: "jpeg", quality: 60 });
  const seq = await p.evaluate(() => window.__pill);
  await p.close();
  return JSON.stringify({ seq, fadedVisibleAttr: visible, fadedOpacity: opacity, descMoved: box0 !== box1 });
}
