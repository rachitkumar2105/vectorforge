#!/usr/bin/env bash
# Full browser QA against a local production build wired to a local engine container.
#
# Prerequisites (local only, never production keys):
#   - an engine container named vf-render built from engine/Dockerfile, publishing 8000 on 18100
#   - the site running via scripts/qa/restart.sh with VECTORFORGE_ENGINE_URL=http://localhost:18100
#   - playwright-cli open http://localhost:3000   (started from the repository root)
# Run from the repository root:  bash web/scripts/qa/run-all.sh
# Results land in docs/demo/ (JSON) and docs/demo/**/*.jpg (screenshots).
set -uo pipefail
cd "$(dirname "$0")/../../.."
OUT=docs/demo
run() { playwright-cli --raw run-code --filename="web/scripts/qa/$1.js" 2>&1 | tail -1 > "$OUT/$2.json"; echo "$2: $(head -c 160 "$OUT/$2.json")"; }
ready() { until curl -sf localhost:18100/readyz >/dev/null; do sleep 0.5; done; }

docker start vf-render >/dev/null; ready
echo "--- engine live"
run console qa-console
run demo-twice qa-demo-twice
run interaction-sweep qa-interaction-sweep
run tab-walk qa-tab-walk
run scroll-reveal qa-scroll-reveal
run reduced-motion qa-reduced-motion
run pill/warm pill/warm

echo "--- engine paused (sleeping), unpaused after 25 s"
docker pause vf-render >/dev/null
(sleep 25; docker unpause vf-render >/dev/null) &
run pill/waking pill/waking
wait
docker pause vf-render >/dev/null
run pill/reduced pill/reduced
run pill/hidden pill/hidden
docker unpause vf-render >/dev/null

echo "--- engine stopped"
docker stop vf-render >/dev/null
run pill/down pill/down
run pill/fit pill/fit
run widths qa-widths
run sections qa-sections
run console qa-console-engine-down
run interaction-sweep qa-interaction-sweep-engine-down
echo "done"
