# WU-OBS-SIGNALS-01 / OBS-SIG-01 Fix Re-Review (AgentMiMo)

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-01` / P01 context pressure signal
- Gate: fix re-review
- Fix artifact: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-code-review-controller-adjudication.md`
- Reviewed files:
  - `dayu/host/engine_ingest.py` — 三处 docstring fix
  - `dayu/host/tool_trace.py` — OBS-SIG-01 implementation diff（不含 fix 变更）
  - `tests/host/test_engine_ingest_mapping.py` — context_pressure 断言
  - `tests/host/test_tool_trace_projection.py` — compaction pressure 测试

## Accepted Findings Recheck

### MIMO-F1: `_duplicate_terminal_result` 与 `_ingest_validated` 缺失 `transaction` 参数文档

- Controller adjudication: accepted，要求恢复 `:param transaction: 当前 Host transaction。`
- Fix applied: AgentCodex 报告已恢复
- Recheck result: **已修复** ✅
  - `_duplicate_terminal_result`（`engine_ingest.py:809`）docstring 包含 `:param transaction: 当前 Host transaction。`
  - `_ingest_validated`（`engine_ingest.py:913`）docstring 包含 `:param transaction: 当前 Host transaction。`
  - 函数签名未变，仍为 `def _duplicate_terminal_result(self, transaction: HostTransaction, context: _ValidatedCandidate)` 和 `def _ingest_validated(self, transaction: HostTransaction, context: _ValidatedCandidate)`

### DS-F1: `_usage_observation_diagnostic` 残留 `transaction` 参数文档

- Controller adjudication: accepted，要求删除 stale `:param transaction: 当前 Host transaction。`
- Fix applied: AgentCodex 报告已删除
- Recheck result: **已修复** ✅
  - `_usage_observation_diagnostic`（`engine_ingest.py:2711-2724`）docstring 只包含 `:param context:`、`:param data:`、`:param estimate:`、`:param returns:`，无 `:param transaction:` 残留
  - 函数签名（`engine_ingest.py:2711-2717`）只接受 keyword-only `context`、`data`、`estimate`，与 docstring 一致

## New Findings

无。

## Residual Risk

- P02（`tool_timing`）、P03（`failure_metadata`）、P04（`partial_tool_call_signal`）仍为占位/copy 路径，等待后续 slice 填充。这是 controller adjudication 确认的已知 residual risk，不属于 OBS-SIG-01 缺陷。
- DS residual notes（compaction request fact 缺失降级路径、`_required_bool` 缺失字段异常路径）未被 controller 接受为 blocking findings，可在 OBS-SIG-05 integration 或 analyzer coverage 中补充。

## Validation

- AgentCodex 报告：`pytest` 116 passed，`pyright` 0 errors
- 本地独立验证：
  - `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_context_compact_events.py` → **116 passed in 0.93s** ✅
  - `source .venv/bin/activate && pyright` → **0 errors, 0 warnings, 0 informations** ✅
- 本地验证结果与 AgentCodex 报告一致。

## Scope Creep Assessment

Fix 只涉及三处 docstring 修改，不涉及：
- 函数签名变更
- 函数体逻辑变更
- 测试变更
- 新增文件
- Engine public contract 变更

整体 OBS-SIG-01 diff（含 implementation + fix）仍严格限定在 P01 context pressure signal 范围内：
- `engine_ingest.py` 只新增 `_usage_context_pressure_signal` 和三个模块级常量
- `tool_trace.py` 只新增 compaction failed/rejected 的 context_pressure 派生逻辑和 `_required_bool` helper
- 未引入 P02/P03/P04 的任何生产路径变更
- 未修改 Engine public contract、SQLite schema、ToolRuntime 执行语义或状态机

## Verdict

**PASS**

两项 accepted findings 均已正确修复，fix 只改必要文档一致性，未改变行为逻辑或扩大 scope。整体 OBS-SIG-01 diff 满足 P01 范围约束。本地独立验证与 AgentCodex 报告一致。
