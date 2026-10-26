// WCAG 2.x contrast ratios for the palette in docs/DESIGN.md. Run: node web/scripts/contrast.mjs
const bg = "#07090B";
const panel = "#0C1115";
const colours = { ink: "#E5ECEF", inkDim: "#93A3AC", trace: "#35E0C2", signal: "#F0A43A" };

function luminance(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

let ok = true;
for (const [name, hex] of Object.entries(colours)) {
  for (const [surface, s] of [["bg", bg], ["panel", panel]]) {
    const r = ratio(hex, s);
    if (r < 4.5) ok = false;
    console.log(`${name.padEnd(7)} ${hex} on ${surface.padEnd(5)} ${r.toFixed(2)}:1 ${r >= 4.5 ? "pass" : "FAIL"}`);
  }
}
process.exit(ok ? 0 : 1);
