// Generated from web/scripts/qa by swapping the base URL for production; see DEMO-REPORT.md.
// playwright-cli run-code --filename=web/scripts/qa/widths.js   (dev or prod server on :3000)
// Screenshots at the nine widths the spec requires, plus a horizontal-overflow check per width.
async (page) => {
  await page.bringToFront(); // background tabs get no animation frames
  await page.emulateMedia({ reducedMotion: "no-preference" }); // sessions keep emulation between runs
  const widths = [375, 414, 768, 1024, 1280, 1440, 1920, 2560, 3440];
  const out = [];
  for (const w of widths) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.goto("https://vectorforge-olive.vercel.app/", { waitUntil: "networkidle" });
    await page.waitForTimeout(600);
    const m = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      mainWidth: Math.round(document.querySelector(".container-instrument")?.getBoundingClientRect().width ?? 0),
    }));
    await page.screenshot({ path: `docs/demo/prod/w${w}-hero.jpg`, type: "jpeg", quality: 60 });
    await page.locator("#visualizer").scrollIntoViewIfNeeded();
    await page.waitForTimeout(800);
    await page.screenshot({ path: `docs/demo/prod/w${w}-visualizer.jpg`, type: "jpeg", quality: 60 });
    out.push({ width: w, overflow: m.scrollWidth > m.clientWidth, ...m });
  }
  return JSON.stringify(out);
}
