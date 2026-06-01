# WU-TOOL-01 Slice 3 Implementation Artifact

## 动机判断

Slice 3 动机成立：Slice 1/2 已把 duplicate governance 收敛为 attempt-local，但 durable diagnostic 与 tool trace 若不保存机器可读 `duplicate_scope`，排障时仍难以证明 duplicate 决策只来自当前 Attempt。当前 `TOOL_CALL_GOVERNED` payload 已包含 `duplicate_scope`，因此本 Slice 未重复扩大 EventLog payload，只补齐 trace/diagnostic/test 闭环。

## Changed Files

- `dayu/host/tool_runtime.py`
- `dayu/host/tool_trace.py`
- `tests/host/test_toolruntime_diagnostics.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `docs/reviews/wu-tool-01-implementation-slice3-codex-20260601.md`

## Implemented Items

- 确认 `TOOL_CALL_GOVERNED` 生产 payload 已写入 `duplicate_scope: {"kind": "attempt", "attempt_id": ...}`，未重复改写该路径。
- `tool_trace.py` 新增 `duplicate_scope` 常量、canonical extractor 参数与 summary 字段，`trace_summary["duplicate_scope"]` 会保留 governed duplicate 的 attempt scope。
- duplicate diagnostic ref 现在使用 typed duplicate decision message，保证配置化 duplicate message 同时出现在 policy decision、governed failure outcome 与 diagnostic record。
- accept barrier 测试断言 governed payload 的 `duplicate_scope.kind == "attempt"`，`attempt_id` 等于 candidate attempt，并用 same attempt-local accepted ack ref 证明 prior refs 来源。
- duplicate governed candidate 测试补充 `duplicate_scope` 断言；既有 validation 继续覆盖 prior refs、reason、message 与 decision kind 匹配。
- 未引入 durable duplicate ledger，未从 EventLog 重建 duplicate refs，未改 SQLite schema。

## Tests Run

- `source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_toolruntime_duplicate_governance.py`
  - Result: `52 passed`

## Pyright Result

- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`

## README Decision

本 Slice 不更新 README。按 approved plan 与本次用户指令，README sync 由 Slice 4 处理；本 Slice 只补齐 governed event / diagnostic / trace scope 的实现与测试闭环。

## Residual Risks

- `ToolTraceDiagnosticRecord` 仍只有 `reason_code` / `message`，没有结构化 metadata。为避免扩大 tool trace contract，机器可读 scope 继续以 `TOOL_CALL_GOVERNED.payload.duplicate_scope` 和 tool trace summary 为真源。
- 本 Slice 不处理 Slice 4 的 README 术语收口，也不审计未授权文件中的旧 wording。

## Stop Conditions

- 未命中需要停止的条件。
- 未发现需要通过新增 diagnostic metadata、durable duplicate ledger、EventLog 重建 duplicate refs 或 schema change 才能完成的情况。
