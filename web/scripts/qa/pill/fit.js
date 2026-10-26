// Does every pill text fit its reserved box at all nine widths? Writes each state's text into the
// pill (DOM only, for measurement) and checks the truncating span does not overflow.
async (page) => {
  const texts = [
    "checking engine",
    "waking engine, about 45s · 88s",
    "engine live",
    "engine asleep, showing saved results",
  ];
  const out = [];
  for (const w of [375, 414, 768, 1024, 1280, 1440, 1920, 2560, 3440]) {
    const p = await page.context().newPage();
    await p.bringToFront(); // background tabs get no animation frames
    await p.setViewportSize({ width: w, height: 900 });
    await p.goto("http://localhost:3000/", { waitUntil: "networkidle" });
    const r = await p.evaluate((ts) => {
      const box = document.querySelector(".engine-pill").parentElement;
      const outer = document.querySelector(".engine-pill .truncate");
      const live = outer.querySelector("[aria-live]");
      const counter = live.nextElementSibling;
      if (counter) counter.remove();
      const before = box.getBoundingClientRect();
      const overflow = ts.filter((t) => {
        live.textContent = t;
        return outer.scrollWidth > outer.clientWidth;
      });
      const after = box.getBoundingClientRect();
      return { pillWidth: Math.round(before.width), boxMoved: before.width !== after.width || before.height !== after.height, overflow };
    }, texts);
    out.push({ width: w, ...r });
    await p.close();
  }
  return JSON.stringify(out);
}
