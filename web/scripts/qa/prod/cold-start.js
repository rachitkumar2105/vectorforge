// Natural Render cold start on production: run after the engine has had no traffic for more
// than 15 minutes, so the free instance is asleep. Records every pill text with its time, how
// the first search is answered while the engine wakes, and how the pill ends (live or asleep).
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
  const startedAt = new Date().toISOString();
  await p.goto("https://vectorforge-olive.vercel.app/#demo", { waitUntil: "domcontentloaded" });
  await p.waitForTimeout(4500);
  const textAt4s = await p.locator(".engine-pill [aria-live]").textContent();
  await p.locator("#demo").screenshot({ path: "docs/demo/prod/cold/waking.jpg", type: "jpeg", quality: 60 });

  await p.locator("#demo-q").fill("compress data");
  await p.keyboard.press("Enter");
  await p.waitForSelector("#demo [data-source]");
  const firstAnswer = await p.locator("#demo [data-source]").getAttribute("data-source");

  const end = await p.waitForFunction(() => {
    const t = document.querySelector(".engine-pill [aria-live]")?.textContent;
    return t === "engine live" || t === "engine asleep, showing saved results" ? t : false;
  }, null, { timeout: 120000 }).then((h) => h.jsonValue()).catch(() => "timeout");
  await p.locator("#demo").screenshot({ path: "docs/demo/prod/cold/end.jpg", type: "jpeg", quality: 60 });

  await p.locator("#demo-q").fill("send an email");
  await p.keyboard.press("Enter");
  await p.waitForTimeout(3000);
  const nextAnswer = await p.locator("#demo [data-source]").getAttribute("data-source");
  const seq = await p.evaluate(() => window.__pill);
  await p.close();
  return JSON.stringify({ startedAt, seq, textAt4s, firstAnswer, end, nextAnswer });
}
