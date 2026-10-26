// Run with the engine container paused; the shell unpauses it about 25 s later.
// Expect: checking -> waking (after 2 s) with a pulsing dot and a ticking counter; searches answer
// from the labelled snapshot with the input enabled; when the engine comes live the input and
// results are kept, the pill fades, and the next query goes live.
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
  await p.waitForTimeout(4500);
  const dot = p.locator(".engine-dot");
  const waking = {
    text: await p.locator(".engine-pill [aria-live]").textContent(),
    counter: await p.locator(".engine-pill .num").textContent(),
    dotAnimation: await dot.evaluate((e) => [getComputedStyle(e).animationName, getComputedStyle(e).animationDuration, getComputedStyle(e).animationTimingFunction].join(" ")),
  };
  await p.waitForTimeout(1200);
  waking.counterLater = await p.locator(".engine-pill .num").textContent();
  await p.locator("#demo").screenshot({ path: "docs/demo/pill/waking.jpg", type: "jpeg", quality: 60 });

  const input = p.locator("#demo-q");
  const inputEnabled = await input.isEnabled();
  await input.fill("compress data");
  await p.keyboard.press("Enter");
  await p.waitForSelector("#demo [data-source]");
  const labelWhileWaking = await p.locator("#demo [data-source]").getAttribute("data-source");
  // The result list animates in after the empty one exits; wait for it before reading.
  await p.waitForFunction(() => document.querySelectorAll("#demo ol li").length > 0);
  await p.waitForTimeout(600);
  const firstTitles = await p.locator("#demo ol li .text-trace").allInnerTexts();
  await p.locator("#demo").screenshot({ path: "docs/demo/pill/waking-snapshot-results.jpg", type: "jpeg", quality: 60 });

  await p.waitForFunction(() => {
    const el = document.querySelector(".engine-pill [aria-live]");
    return el && el.textContent === "engine live";
  }, null, { timeout: 90000 });
  const keptInput = await input.inputValue();
  const keptTitles = await p.locator("#demo ol li .text-trace").allInnerTexts();
  await p.waitForTimeout(2600);
  const pillVisibleAfterHold = await p.locator(".engine-pill").getAttribute("data-visible");

  await input.fill("send an email");
  await p.keyboard.press("Enter");
  await p.waitForFunction(() => {
    const el = document.querySelector("#demo [data-source]");
    return el && el.getAttribute("data-source") === "engine";
  }, null, { timeout: 15000 }).catch(() => {});
  const labelAfterLive = await p.locator("#demo [data-source]").getAttribute("data-source");
  const box1 = await offset();
  const seq = await p.evaluate(() => window.__pill);
  await p.close();
  return JSON.stringify({
    seq,
    waking,
    inputEnabled,
    labelWhileWaking,
    inputAndResultsKeptWhenLive: keptInput === "compress data" && keptTitles.length > 0 && keptTitles.join() === firstTitles.join(),
    keptInput,
    resultsBefore: firstTitles.length,
    resultsAfter: keptTitles.length,
    pillVisibleAfterHold,
    labelAfterLive,
    descMoved: box0 !== box1,
  });
}
