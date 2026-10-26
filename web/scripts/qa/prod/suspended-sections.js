// Generated from web/scripts/qa by swapping the base URL for production; see DEMO-REPORT.md.
// Screenshot each section at desktop and phone widths for design review.
async (page) => {
  await page.bringToFront(); // background tabs get no animation frames
  await page.emulateMedia({ reducedMotion: "no-preference" }); // sessions keep emulation between runs
  const out = [];
  for (const w of [1440, 375]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.goto("https://vectorforge-olive.vercel.app/", { waitUntil: "networkidle" });
    for (const id of ["benchmarks", "demo", "architecture", "limits"]) {
      const s = page.locator(`#${id}`);
      await s.scrollIntoViewIfNeeded();
      if (id === "demo") {
        await page.getByRole("button", { name: "send an email" }).click();
        await page.waitForTimeout(1200);
      }
      await page.waitForTimeout(900);
      await s.screenshot({ path: `docs/demo/prod/suspended/w${w}-${id}.jpg`, type: "jpeg", quality: 55 });
      out.push(`${w}-${id}`);
    }
    const o = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    out.push(`overflow@${w}=${o}`);
  }
  return out.join(" ");
}
