#!/usr/bin/env bash
set -euo pipefail

URL="${1:?用法: $0 <URL> [额外参数...]}"
shift

OUTPUT_ROOT="workspace/output/web_diagnostics"
STATE_DIR="${OUTPUT_ROOT}/storage_states"
TIMESTAMP="$(date +%Y%m%d%H%M%S)"

mkdir -p "${OUTPUT_ROOT}"
mkdir -p "${STATE_DIR}"

# 本脚本是手工显式触发的 live/browser 诊断入口。
python -m utils.diagnose_web_access \
  --url "${URL}" \
  --headed \
  --playwright-channel chrome \
  --manual-wait-seconds 30 \
  --storage-state-dir "${STATE_DIR}" \
  --output "${OUTPUT_ROOT}/diagnose_web_access_${TIMESTAMP}.json" \
  "$@"
