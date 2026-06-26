#!/usr/bin/env bash
# Hot-reload dev loop: upload source files to UC Volume (no pip, no restartPython).
#
# Usage:
#   ./dev/upload_src.sh
#
# In your Databricks notebook, first time:
#   import sys
#   sys.path.insert(0, '/Volumes/ai_innovation_gold_dev/sdh/dev_wheels/dashdq_src')
#   import dashdq
#   config = dashdq.configure(spark=spark)
#
# After every code change (no restartPython needed):
#   for m in [k for k in sys.modules if 'dashdq' in k]: del sys.modules[m]
#   import dashdq
#   dashdq.configure(spark=spark)

set -e
cd "$(dirname "$0")/.."

TOKEN=$(awk '/^\[DEFAULT\]/{f=1} f && /^token/{print $3; exit}' ~/.databrickscfg)
HOST=$(awk '/^\[DEFAULT\]/{f=1} f && /^host/{print $3; exit}' ~/.databrickscfg)
BASE="$HOST/api/2.0/fs/files/Volumes/ai_innovation_gold_dev/sdh/dev_wheels/dashdq_src/dashdq"

echo "→ Uploading dashdq/*.py to UC Volume..."
for f in dashdq/*.py; do
  fname=$(basename "$f")
  http_code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$BASE/$fname" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/octet-stream" \
    --data-binary @"$f")
  if [ "$http_code" = "204" ] || [ "$http_code" = "200" ]; then
    echo "  ✓ $fname"
  else
    echo "  ✗ $fname (HTTP $http_code)"
    exit 1
  fi
done

echo ""
echo "✓ Done in ~5 seconds. In Databricks notebook:"
echo ""
echo "  # First time:"
echo "  import sys"
echo "  sys.path.insert(0, '/Volumes/ai_innovation_gold_dev/sdh/dev_wheels/dashdq_src')"
echo "  import dashdq; dashdq.configure(spark=spark)"
echo ""
echo "  # After each change (no restart):"
echo "  for m in [k for k in sys.modules if 'dashdq' in k]: del sys.modules[m]"
echo "  import dashdq; dashdq.configure(spark=spark)"
