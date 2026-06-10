# WU-TOOLS-01-F01-02-R3 Slice 3 Fix - Codex

## Gate

- Work unit: WU-TOOLS-01-F01-02-R3
- Slice: Slice 3
- Gate: fix
- Scope: S3-CR-01 accepted finding only

## Accepted Finding

### S3-CR-01

Fins read native cancellation path 直接把 `CancellationToken.cancel_reason()` 拼进 LLM-facing `ToolCancelledOutcome.message`，深层 `FinsReadCancelledError.message` 也会拼接 token reason。`cancel_reason` 属于 Host 治理原因，不应由 Fins read 工具原样暴露给 LLM。

Decision: accepted。

## Fix

- `dayu/fins/tools/fins_tools.py`
  - `_cancelled_from_token` 不再读取 `cancellation_token.cancel_reason()`。
  - pre-cancel outcome 使用固定业务可读 message：`财报读取工具调用已被取消。`
  - 仍通过 `host_cancelled_outcome` 返回，`reason` 保持 `host_cancelled`。
- `dayu/fins/tools/read_runtime_helpers.py`
  - `raise_fins_cancelled` 不再读取或拼接 `cancellation_token.cancel_reason()`。
  - 深层取消继续抛出 `FinsReadCancelledError`，message 使用调用方提供的业务可读取消说明，hint 保持 `当前工具调用已停止；等待新的用户指令或后续调度。`
- `tests/fins/test_fins_storage_provider.py`
  - `_ManualCancellationToken` 支持注入测试取消 reason。
  - 新增 focused test 覆盖 pre-cancel 和深层搜索取消路径，取消 reason 包含 `run_id`、`session_id`、`correlation_id`、`payload_ref`、`digest`、`cancellation_token` 等 Host 治理标识。
  - 断言 `ToolCancelledOutcome.message` 和 `hint` 均不包含这些治理标识，且 `outcome.reason` 仍为 `host_cancelled`。

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py`
  - Result: passed, 22 passed, 3 warnings from edgar dependency deprecations.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -k cancellation`
  - Result: passed, 1 passed, 31 deselected, 3 warnings from edgar dependency deprecations.
- `source .venv/bin/activate && pyright`
  - Result: passed, 0 errors, 0 warnings, 0 informations. Pyright reported an available version update only.
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools|ToolBusinessError\\(.*tool_cancelled" dayu/fins/tools tests/fins/test_fins_storage_provider.py`
  - Result: passed, no matches.
- `git diff --check`
  - Result: passed, no whitespace errors.

## Docs Decision

No README update. The fix only changes Fins read cancellation projection internals and focused tests; it does not change documented Fins user behavior, public tool schema, storage contract, or layer boundaries. No Doc/Web changes were made beyond this required fix artifact.

## Residual Risk

- Residual risk: none identified for S3-CR-01.
- Uncovered areas: cancellation reason leakage outside the allowed Fins read files was not changed in this gate by scope constraint.

## Status

S3-CR-01: 已修复。
