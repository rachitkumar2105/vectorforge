#!/usr/bin/env bash
# Rebuild the site and (re)start the production server on :3000 for browser QA.
set -euo pipefail
cd "$(dirname "$0")/../.."
powershell -c "Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | % { Stop-Process -Id \$_.OwningProcess -Force }" || true
pnpm build > /dev/null
(pnpm start -p 3000 > "${TMPDIR:-/tmp}/vf-web.log" 2>&1 &)
until curl -s -o /dev/null http://localhost:3000/terms; do :; done
echo "server up"
