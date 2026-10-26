// Scroll the whole page like a reader and confirm every reveal fired (none left hidden).
async (page) => {
  await page.emulateMedia({ reducedMotion: "no-preference" }); // sessions keep emulation between runs
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
  // Lazy sections grow the page as they mount, so scroll until the bottom stops moving away.
  for (let i = 0; i < 400; i++) {
    await page.mouse.wheel(0, 400);
    await page.waitForTimeout(120);
    const atEnd = await page.evaluate(() => scrollY + innerHeight >= document.documentElement.scrollHeight - 2);
    if (atEnd) break;
  }
  await page.waitForTimeout(800);
  return JSON.stringify(await page.evaluate(() => ({
    reveals: document.querySelectorAll(".reveal").length,
    stillArmed: document.querySelectorAll('.reveal[data-state="armed"]').length,
  })));
}
