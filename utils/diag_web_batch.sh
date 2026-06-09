#!/usr/bin/env bash
set -euo pipefail

URL_FILE="${1:?用法: $0 <URL文件> [额外参数...]}"
shift

OUTPUT_ROOT="workspace/output/web_diagnostics"
STATE_DIR="${OUTPUT_ROOT}/storage_states"
BATCH_OUTPUT_DIR="${OUTPUT_ROOT}/batch_$(date +%Y%m%d%H%M%S)"

mkdir -p "${OUTPUT_ROOT}"
mkdir -p "${STATE_DIR}"
mkdir -p "${BATCH_OUTPUT_DIR}"

# 本脚本是手工显式触发的 live/browser 诊断入口。
python -m utils.diagnose_web_access \
  --url-file "${URL_FILE}" \
  --headed \
  --playwright-channel chrome \
  --manual-wait-seconds 30 \
  --storage-state-dir "${STATE_DIR}" \
  --batch-output-dir "${BATCH_OUTPUT_DIR}" \
  "$@"
