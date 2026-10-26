// Generated from web/scripts/qa/pill/down.js for production with the Render service suspended.
// Run with the engine container stopped. A fake clock fast-forwards past the 90 s budget.
// Expect: the unavailable state persists, polling stops, searches answer from the labelled snapshot.
async (page) => {
  const p = await page.context().newPage();
    await p.bringToFront(); // background tabs get no animation frames
  await p.emulateMedia({ reducedMotion: "no-preference" });
  await p.setViewportSize({ width: 1440, height: 900 });
  await p.clock.install();
  let health = 0;
  p.on("request", (r) => {
    if (r.url().includes("/api/engine-health")) health++;
  });
  await p.goto("https://vectorforge-olive.vercel.app/#demo", { waitUntil: "domcontentloaded" });
  const seen = [];
  for (let i = 0; i < 40; i++) {
    await p.clock.fastForward(3000);
    await p.waitForTimeout(200);
    const txt = await p.locator(".engine-pill [aria-live]").textContent();
    if (seen[seen.length - 1] !== txt) seen.push(txt);
  }
  const finalText = await p.locator(".engine-pill [aria-live]").textContent();
  const dotState = await p.locator(".engine-dot").getAttribute("data-state");
  const pingsAtEnd = health;
  await p.clock.fastForward(60000);
  await p.waitForTimeout(500);
  const pingsLater = health;
  await p.locator("#demo-q").fill("random number");
  await p.keyboard.press("Enter");
  await p.waitForSelector("#demo [data-source]");
  const label = await p.locator("#demo [data-source]").innerText();
  // The fake clock also freezes animation frames: advance it so the result list can animate in.
  for (let i = 0; i < 10; i++) {
    await p.clock.runFor(200);
    await p.waitForTimeout(50);
  }
  const results = await p.locator("#demo ol li").count();
  await p.locator("#demo").screenshot({ path: "docs/demo/prod/suspended/unavailable.jpg", type: "jpeg", quality: 60 });
  await p.close();
  return JSON.stringify({ statesSeen: seen, finalText, dotState, pings: pingsAtEnd, pingsAfterAnotherMinute: pingsLater, label: label.slice(0, 70), results });
}
