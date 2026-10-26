// Engine paused: hiding the tab stops polling and freezes the counter; showing it resumes at once.
async (page) => {
  const p = await page.context().newPage();
    await p.bringToFront(); // background tabs get no animation frames
  await p.setViewportSize({ width: 1280, height: 900 });
  let health = 0;
  p.on("request", (r) => {
    if (r.url().includes("/api/engine-health")) health++;
  });
  await p.goto("http://localhost:3000/#demo", { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(12000);
  const setVis = (state) =>
    p.evaluate((s) => {
      Object.defineProperty(document, "visibilityState", { configurable: true, get: () => s });
      document.dispatchEvent(new Event("visibilitychange"));
    }, state);
  await setVis("hidden");
  await p.waitForTimeout(9000); // let any in-flight ping (8 s server timeout) settle
  const atHide = health;
  const counterAtHide = await p.locator(".engine-pill .num").textContent();
  await p.waitForTimeout(20000);
  const whileHidden = health - atHide;
  const counterAfterHidden = await p.locator(".engine-pill .num").textContent();
  await setVis("visible");
  await p.waitForTimeout(1500);
  const afterShow = health - atHide;
  await p.close();
  return JSON.stringify({ pingsWhileHidden20s: whileHidden, pingsWithin1500msOfShow: afterShow, counterAtHide, counterAfterHidden });
}
