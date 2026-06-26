#!/usr/bin/env bash
# Build a dev wheel and upload to UC Volume.
# Use this when you need a full clean install (e.g. after adding a new file).
# For widget/UI iteration, prefer upload_src.sh (no restartPython needed).
#
# Usage:
#   ./dev/upload_wheel.sh
#
# In your Databricks notebook:
#   %pip install /Volumes/ai_innovation_gold_dev/sdh/dev_wheels/dash_dq_dev.whl --force-reinstall -q
#   dbutils.library.restartPython()

set -e
cd "$(dirname "$0")/.."

TOKEN=$(awk '/^\[DEFAULT\]/{f=1} f && /^token/{print $3; exit}' ~/.databrickscfg)
HOST=$(awk '/^\[DEFAULT\]/{f=1} f && /^host/{print $3; exit}' ~/.databrickscfg)
DEST="$HOST/api/2.0/fs/files/Volumes/ai_innovation_gold_dev/sdh/dev_wheels/dash_dq_dev.whl"

echo "→ Building wheel..."
python3 -m hatch build -t wheel --clean 2>&1 | tail -3

WHEEL=$(ls dist/dash_dq-*.whl 2>/dev/null | sort -V | tail -1)
[ -z "$WHEEL" ] && echo "✗ No wheel found in dist/" && exit 1

echo "→ Uploading $WHEEL → dev_wheels volume..."
http_code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "$DEST" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @"$WHEEL")

if [ "$http_code" = "204" ] || [ "$http_code" = "200" ]; then
  echo "✓ Uploaded. In Databricks notebook:"
  echo ""
  echo "  %pip install /Volumes/ai_innovation_gold_dev/sdh/dev_wheels/dash_dq_dev.whl --force-reinstall -q"
  echo "  dbutils.library.restartPython()"
else
  echo "✗ Upload failed (HTTP $http_code)"
  exit 1
fi
