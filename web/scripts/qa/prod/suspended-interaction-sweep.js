// Generated from web/scripts/qa by swapping the base URL for production; see DEMO-REPORT.md.
// Exercise every interactive control, twice, at desktop and phone widths, and count console
// errors/warnings and CSP violations. Repeat interactions catch exit/update paths a single
// pass misses (that is how the popLayout CSP bug was found).
async (page) => {
  const out = {};
  for (const [w, h] of [[1440, 900], [375, 812]]) {
    const p = await page.context().newPage();
    await p.bringToFront(); // background tabs get no animation frames
    await p.emulateMedia({ reducedMotion: "no-preference" });
    await p.setViewportSize({ width: w, height: h });
    const errors = [];
    p.on("console", (m) => { if (["error", "warning"].includes(m.type())) errors.push(m.text().slice(0, 100)); });
    p.on("pageerror", (e) => errors.push(`pageerror ${e.message.slice(0, 100)}`));
    await p.addInitScript(() => {
      window.__v = [];
      document.addEventListener("securitypolicyviolation", (e) => window.__v.push(e.violatedDirective));
    });
    await p.goto("https://vectorforge-olive.vercel.app/", { waitUntil: "networkidle" });
    await p.waitForTimeout(3500); // idle-time mounting of lazy sections
    if (w < 1024) {
      await p.getByLabel("Sections").click();
      await p.getByRole("link", { name: "Benchmarks" }).first().click();
      await p.waitForTimeout(800);
    }
    const viz = p.locator("#visualizer");
    await viz.scrollIntoViewIfNeeded();
    for (let i = 0; i < 2; i++) {
      await viz.locator('[role="group"] svg').last().click({ position: { x: 120, y: 120 } });
      await p.getByRole("button", { name: "Random query" }).click();
      await p.locator("#ef").fill(String(10 + i * 30));
      await p.getByRole("button", { name: "Reset to start" }).click();
      await p.getByRole("button", { name: "Step to next hop" }).click();
      await p.getByRole("button", { name: /Play|Replay|Pause/ }).click();
      await p.waitForTimeout(1200);
      await viz.focus();
      await p.keyboard.press("ArrowLeft");
      await p.keyboard.press("ArrowUp");
    }
    await p.locator("#benchmarks").scrollIntoViewIfNeeded();
    for (const name of [/GloVe/, /SIFT/, /GloVe/]) {
      await p.getByRole("button", { name }).click();
      await p.waitForTimeout(400);
    }
    if (w < 640) await p.locator("#benchmarks select").selectOption("faiss-hnsw");
    const chart = p.locator('#benchmarks svg[role="img"]');
    await chart.hover({ position: { x: 200, y: 120 } });
    await chart.focus();
    for (const k of ["ArrowRight", "ArrowRight", "ArrowDown", "ArrowLeft"]) await p.keyboard.press(k);
    const summary = p.locator("#benchmarks summary");
    await summary.click();
    await summary.click();
    await p.locator("#demo").scrollIntoViewIfNeeded();
    for (const q of ["random number", "compress data", "wait for a thread"]) {
      await p.getByRole("button", { name: q }).click();
      await p.waitForTimeout(900);
    }
    await p.locator("#demo-q").fill("zzqx qqzz");
    await p.keyboard.press("Enter");
    await p.waitForTimeout(800);
    await p.locator("#architecture").scrollIntoViewIfNeeded();
    for (let i = 0; i < 12; i++) {
      await p.mouse.wheel(0, 500);
      await p.waitForTimeout(100);
    }
    await p.setViewportSize({ width: w === 1440 ? 800 : 700, height: 900 }); // resize mid-session
    await p.waitForTimeout(600);
    await p.getByRole("link", { name: "Privacy" }).click();
    await p.waitForTimeout(800);
    await p.goBack();
    await p.waitForTimeout(800);
    out[w] = { errors: errors.length, sample: errors.slice(0, 3), csp: await p.evaluate(() => window.__v.length) };
    await p.close();
  }
  return JSON.stringify(out);
}
