// Full keyboard Tab walk: every stop, its accessible name, and whether a focus outline is drawn.
async (page) => {
  await page.bringToFront(); // background tabs get no animation frames
  await page.emulateMedia({ reducedMotion: "no-preference" }); // sessions keep emulation between runs
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
  await page.waitForTimeout(3000); // let the idle-time mount of lazy sections happen, as for a real visitor
  const stops = [];
  for (let i = 0; i < 80; i++) {
    await page.keyboard.press("Tab");
    const s = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const cs = getComputedStyle(el);
      const name = (el.getAttribute("aria-label") || el.textContent || el.getAttribute("id") || "").trim().replace(/\s+/g, " ").slice(0, 60);
      return { tag: el.tagName.toLowerCase(), name, outline: cs.outlineStyle !== "none" && cs.outlineWidth !== "0px" };
    });
    if (!s) break;
    if (stops.length && stops[0].name === s.name && stops[0].tag === s.tag) break; // wrapped
    stops.push(s);
  }
  return JSON.stringify({ count: stops.length, withoutOutline: stops.filter((s) => !s.outline), stops });
}
