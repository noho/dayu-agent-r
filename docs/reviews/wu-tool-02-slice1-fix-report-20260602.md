# WU-TOOL-02 Slice 1 Fix Report

## Finding Status

- AgentMiMo Finding 01：已修复。
  - `_validate_tool_accept_duplicate_governance` 已对齐现有 `_validate_duplicate_fields` 语义。
  - `ToolAcceptDuplicateGovernance` 表达的任意非 `None` duplicate decision 都要求 `duplicate_scope` 与 `duplicate_decision_message`。
  - 只有 `REUSE`、`HINT`、`REQUIRE_JUSTIFICATION`、`HARD_STOP`、`DURABLE_MISSING` 要求 `duplicate_key`。
- AgentMiMo Finding 02：未处理，controller adjudication 已 reject。
- AgentMiMo Finding 03：未处理，controller adjudication 已 reject。
- AgentDS：无 findings。

## Changed Files

- `dayu/host/tool_runtime.py`
- `docs/reviews/wu-tool-02-slice1-fix-report-20260602.md`

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py`
  - 结果：通过，16 tests。
- `source .venv/bin/activate && pyright dayu/host/tool_runtime.py`
  - 结果：通过，0 errors，0 warnings，0 informations。

## Behavior Confirmation

- 新 helper 在 Slice 1 中仍未接入生产路径。
- 未迁移 producer。
- 未迁移 accept barrier consumer。
- 未修改 tests、README、配置、schema、plan 或总控文档。
- 未改变 EventLog payload、accepted evidence、duplicate governance 运行时行为、wait、memory、compaction 或 tool trace 行为。

## Residual Risks

- Slice 2 仍需将新结构接入 `ToolFactAcceptCandidate`，并原子迁移 producer / consumer / tests。
- 本次 fix 只对齐 Slice 1 未接入 helper 与当前 validator 的语义；新 helper 的直接测试仍按当前 slice scope 延后。
