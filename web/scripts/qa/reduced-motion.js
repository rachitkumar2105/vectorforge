// Reduced motion: decorative animation off, visualizer manual (no Play button, Step present).
async (page) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("http://localhost:3000/", { waitUntil: "networkidle" });
  await page.locator("#visualizer").scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  const r = await page.evaluate(() => {
    const layer = document.querySelector(".hero-layer-0");
    const cs = layer ? getComputedStyle(layer) : null;
    const buttons = [...document.querySelectorAll("#visualizer button")].map((b) => b.getAttribute("aria-label"));
    return {
      matches: matchMedia("(prefers-reduced-motion: reduce)").matches,
      heroAnimationDuration: cs?.animationDuration,
      heroAnimationIterations: cs?.animationIterationCount,
      visualizerButtons: buttons,
      hasPlay: buttons.includes("Play") || buttons.includes("Replay"),
      manualNote: document.querySelector("#visualizer")?.textContent?.includes("playback is manual") ?? false,
    };
  });
  const before = await page.locator("#visualizer [aria-live]").first().innerText();
  await page.getByRole("button", { name: "Reset to start" }).click();
  await page.getByRole("button", { name: "Step to next hop" }).click();
  await page.getByRole("button", { name: "Step to next hop" }).click();
  const after = await page.locator("#visualizer [aria-live]").first().innerText();
  await page.screenshot({ path: "docs/demo/reduced-motion-visualizer.jpg", type: "jpeg", quality: 60 });
  return JSON.stringify({ ...r, readoutBefore: before, readoutAfterTwoSteps: after });
}
