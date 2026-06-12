# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-obs-signals-p01-p04`
- Base: `main`
- Output file: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-code-review-mimo.md`
- Included scope:
  - `dayu/host/engine_ingest.py` — `_append_projection_signal`、`_usage_observation_diagnostic`、`_usage_context_pressure_signal` 及相关重构
  - `dayu/host/tool_trace.py` — `_extract_tool_trace`、`_extract_canonical_trace`、`_canonical_trace_summary_signals`、`_context_compaction_failed_pressure`、`_context_compaction_attempt_rejected_pressure`、`_context_compaction_request_payload`、`_required_bool` 及相关常量
  - `tests/host/test_engine_ingest_mapping.py` — usage context_pressure 断言新增
  - `tests/host/test_tool_trace_projection.py` — compaction failed/rejected context_pressure 投影测试新增
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-implementation-codex.md` — 实现 artifact
  - `docs/host/issues-implementation-control.md` — status bookkeeping
- Excluded scope: P02/P03/P04 实现、analyzer、schema migration、Engine public contract 变更
- Parallel review coverage: 无

## Findings

### 1-未修复-中-docstring 移除违反参数文档约束

- **入口/函数**: `EngineEventIngestor._duplicate_terminal_result` 与 `EngineEventIngestor._ingest_validated`
- **文件(行号)**: `dayu/host/engine_ingest.py` diff lines 15-22, 23-30（对应原始行号 ~804, ~907）
- **输入场景**: 任何读取这两个函数 docstring 的开发者或工具
- **实际分支**: docstring 中 `:param transaction: 当前 Host transaction。` 被移除
- **预期行为**: AGENTS.md 要求"函数必须提供完整中文 docstring，至少包含参数、返回值、异常"。`transaction` 参数仍存在于函数签名中（`self, transaction: HostTransaction, context: _ValidatedCandidate`），docstring 应保留其说明
- **实际行为**: `:param transaction:` 行被删除，但函数签名未变，导致 docstring 不再覆盖所有参数
- **直接证据**: diff 中 `_duplicate_terminal_result` 的 docstring 从三行（`:param transaction:` + `:param context:` + `:returns:`）变为两行（`:param context:` + `:returns:`），`_ingest_validated` 同理。函数签名仍为 `def _duplicate_terminal_result(self, transaction: HostTransaction, context: _ValidatedCandidate)` 和 `def _ingest_validated(self, transaction: HostTransaction, context: _ValidatedCandidate)`
- **影响**: 违反编码硬约束；对维护者而言参数含义不明确
- **建议改法和验证点**: 恢复两个 docstring 中的 `:param transaction: 当前 Host transaction。` 行。验证 pyright 和测试不受影响
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Open Questions

- 无

## Residual Risk

- `tool_timing`、`failure_metadata`、`partial_tool_call_signal` 仍为 OBS-SIG-00 的占位/copy 路径，等待 P02/P03/P04 填充。这是 approved plan 内的已知 residual risk，不属于本 slice 缺陷。
- 聚合类能力（compact counts、pressure trend summaries）属于后续 analyzer 工作单元，不在本 slice 范围内。

## Scope Creep Assessment

实现严格限定在 OBS-SIG-01/P01：

- `engine_ingest.py` 只新增 `_usage_context_pressure_signal` 函数和三个模块级常量，以及在 `_append_projection_signal` 中调用它
- `tool_trace.py` 只新增 compaction failed/rejected 的 `context_pressure` 派生逻辑和 `_required_bool` helper
- 未引入 P02（`tool_timing`）、P03（`failure_metadata`）、P04（`partial_tool_call_signal`）的任何生产路径变更
- 未修改 Engine public contract、SQLite schema、ToolRuntime 执行语义或状态机

## Architecture Alignment

| 设计约束 | 验证结果 |
|---|---|
| Engine 不理解 Host budget | ✓ `decide_context_budget` 调用仅在 `engine_ingest.py`（Host 层），Engine event data 不含 budget 阈值 |
| Tool Trace 是 projection，不是 durable truth | ✓ `context_pressure` 从 EventLog payload 派生，不持久化独立状态 |
| USAGE_REPORTED.context_pressure 由 Host budget policy / BudgetEstimate / decide_context_budget 产生 | ✓ `_usage_context_pressure_signal` 复用已有的 `estimate` 和 `decide_context_budget`，不重复预算计算 |
| estimate_unavailable / usage_invalid / missing input 保持 non-failing | ✓ `estimate=None` 时 `budget_decision="unknown"`，token 字段为 `null`，不 raise |
| compaction failed/rejected 的 context_pressure 只从现有 payload fields 派生 | ✓ `_context_compaction_failed_pressure` 读取 failed payload + request payload；`_context_compaction_attempt_rejected_pressure` 只读 rejected payload；均未修改 context event builders |

## Test Coverage Assessment

| 场景 | 测试 | 状态 |
|---|---|---|
| usage observed + context pressure | `test_usage_reported_is_projection_signal_without_state_change` | ✓ 新增 20 行断言 |
| usage without policy (estimate_unavailable) | `test_usage_reported_without_policy_keeps_projection_non_failing` | ✓ 新增 12 行断言 |
| missing input event (estimate_unavailable) | `test_usage_reported_missing_input_event_keeps_projection_non_failing` | ✓ 新增 3 行断言 |
| unreadable input event (estimate_unavailable) | `test_usage_reported_unreadable_input_event_keeps_projection_non_failing` | ✓ 新增 3 行断言 |
| invalid tokens (usage_invalid) | `test_usage_reported_invalid_tokens_keeps_projection_non_failing` | ✓ 新增 6 行断言 |
| compaction failed context_pressure | `test_tool_trace_derives_context_pressure_from_compaction_failed_payload` | ✓ 新增完整测试 |
| compaction attempt rejected context_pressure | `test_tool_trace_derives_context_pressure_from_compaction_rejected_payload` | ✓ 新增完整测试 |
| hot/cold 同源 | 上述两个 Tool Trace 测试均断言 `_cold_trace_summary(cold_lines, N) == row.trace_summary` | ✓ |

## Validation

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_context_compact_events.py`: **116 passed in 0.93s**
- `source .venv/bin/activate && pyright`: **0 errors, 0 warnings, 0 informations**

## Verdict

**Pass（附 1 项 finding）**

实现正确、范围精确、测试充分。唯一的实质性 finding 是 docstring 参数文档移除（severity: 中），修复风险低，不阻塞功能正确性。
