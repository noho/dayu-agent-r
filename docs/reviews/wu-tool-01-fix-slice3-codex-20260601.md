# WU-TOOL-01 Slice 3 Fix Artifact

## Changed Files

- `tests/host/test_toolruntime_diagnostics.py`
- `docs/reviews/wu-tool-01-fix-slice3-codex-20260601.md`

Note: `dayu/host/tool_runtime.py` 在 fix loop 中被恢复到 accepted behavior；最终 `git diff HEAD -- dayu/host/tool_runtime.py` 无净变更。CR3-1 通过当前文件内容关闭，而不是通过新增最终 diff 关闭。

## CR3-1 Closure

- `_diagnostic_refs_for_duplicate()` 已改回要求并发射 `duplicate_decision.diagnostic_message`。
- duplicate diagnostic record 的 message 重新遵守 approved plan 7.11，使用 `DuplicateGovernancePolicy.messages.attempt_scope_diagnostic`，不再误用 duplicate action message。

## CR3-2 Closure

- `test_candidate_and_ack_carry_duplicate_diagnostic_refs` 现在分别配置：
  - `hard_stop` action message；
  - `attempt_scope_diagnostic` diagnostic message。
- 测试断言：
  - `policy_decision.message` 使用 `hard_stop` action message；
  - governed failure outcome message 使用 `hard_stop` action message；
  - `diagnostics.records[0].message` 使用 `attempt_scope_diagnostic` diagnostic message。

## Tests Run

- `source .venv/bin/activate && python -m pytest tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_toolruntime_duplicate_governance.py`
  - Result: `52 passed`

## Pyright

- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`

## Residual Risks

- 本 fix loop 只处理 accepted blocking findings CR3-1 / CR3-2，未扩展处理其它 review 建议。
- `ToolTraceDiagnosticRecord` 仍不携带结构化 metadata；机器可读 duplicate scope 仍由 `TOOL_CALL_GOVERNED.payload.duplicate_scope` 与 tool trace summary 表达。
