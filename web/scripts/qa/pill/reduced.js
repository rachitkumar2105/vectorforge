// Engine paused, reduced motion: the waking dot is static (no pulse); the text still states it.
async (page) => {
  const p = await page.context().newPage();
    await p.bringToFront(); // background tabs get no animation frames
  await p.emulateMedia({ reducedMotion: "reduce" });
  await p.setViewportSize({ width: 1440, height: 900 });
  await p.goto("http://localhost:3000/#demo", { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(4000);
  const dot = p.locator(".engine-dot");
  const r = {
    text: await p.locator(".engine-pill [aria-live]").textContent(),
    dotState: await dot.getAttribute("data-state"),
    animationName: await dot.evaluate((e) => getComputedStyle(e).animationName),
    transform: await dot.evaluate((e) => getComputedStyle(e).transform),
  };
  await p.locator("#demo").screenshot({ path: "docs/demo/pill/waking-reduced-motion.jpg", type: "jpeg", quality: 60 });
  await p.close();
  return JSON.stringify(r);
}
