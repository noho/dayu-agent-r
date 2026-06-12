# Code Review — WU-OBS-SIGNALS-01 / OBS-SIG-01

## Scope

- Mode: current changes（unstaged diff）
- Branch: `phaseflow/wu-obs-signals-p01-p04`
- Base: `main`
- Output file: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-code-review-ds.md`
- Included scope:
  - `dayu/host/engine_ingest.py` — `_append_projection_signal`、`_usage_observation_diagnostic`、`_usage_context_pressure_signal` 等
  - `dayu/host/tool_trace.py` — `_canonical_trace_summary_signals`、`_context_compaction_failed_pressure`、`_context_compaction_attempt_rejected_pressure`、`_context_compaction_request_payload`、`_required_bool`、常量
  - `tests/host/test_engine_ingest_mapping.py` — 5 个 usage projection 测试的 context_pressure 断言扩展
  - `tests/host/test_tool_trace_projection.py` — 2 个新增 compaction 压力派生测试
  - `docs/host/issues-implementation-control.md` — status bookkeeping
  - `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-implementation-codex.md` — implementation artifact
- Excluded scope:
  - 已提交但不在当前 diff 中的 OBS-SIG-00 变更
  - P02/P03/P04 实现（尚未开始）
  - `dayu/engine/`（未修改）
  - `dayu/host/tool_runtime.py`（未修改）
  - `dayu/host/context_budget.py`（未修改）
- Parallel review coverage: 无（scope 可控，主 reviewer 直接走读全部路径）

## Findings

### F1-待修复-低-`_usage_observation_diagnostic` 存在残留入参文档

- **入口/函数**: `EngineEventIngestor._usage_observation_diagnostic`
- **文件(行号)**: `dayu/host/engine_ingest.py:2718`
- **输入场景**: 无关输入触发；纯文档一致性问题。
- **实际分支**: 不适用。
- **预期行为**: 函数签名已移除 `transaction` 入参，docstring 应同步移除 `:param transaction: 当前 Host transaction。`。
- **实际行为**: docstring 中仍然保留 `:param transaction: 当前 Host transaction。` 行（`engine_ingest.py:2718`），但函数签名不再接受 `transaction` 参数。
- **直接证据**: `engine_ingest.py:2709-2714` 函数签名无 `transaction` 参数；`engine_ingest.py:2718` docstring 仍包含 `:param transaction: 当前 Host transaction。`。对比 diff 中 `_detect_terminal_duplicate`（行 806 删除）与 `_ingest_durable_candidate`（行 909 删除）正确移除了对应 docstring 参数行。
- **影响**: 文档误导后续维护者，可能使调用方误以为该函数仍需 transaction。不影响运行时正确性。
- **建议改法和验证点**: 删除 docstring 中 `:param transaction: 当前 Host transaction。` 行。验证：pyright 继续 0 errors，相关测试继续通过。
- **修复风险（低）**: 纯文档修改，无行为影响。
- **严重程度（低）**: 不影响 correctness/stability，仅影响 maintainability。

## Open Questions

无。

## Residual Risk

- **P02/P03/P04 尚未实现**：`tool_timing`、`failure_metadata`、`partial_tool_call_signal` 在 `_TraceSummarySignals` 中目前为 `None`，由后续 slice 填充。当前 OBS-SIG-01 未引入任何 P02/P03/P04 字段消费或 producer 代码，scope 隔离清晰。
- **compaction failed 缺少 request fact 时降级为 None**：当 `_context_compaction_request_payload` 中 `read_event_by_id` 找不到 request event 时，`policy_ref`、`estimator_digest`、`trigger_source`、`budget_reason` 全部返回 `None`。此降级行为符合 non-failing projection signal 约束，但缺少专门测试覆盖该降级路径。建议后续 slice 或 OBS-SIG-05 integration 补充此场景的测试。
- **`_required_bool` 未覆盖 payload 中 bool 字段缺失时的异常路径**：当前测试 fixture 均提供合法 bool，未测试 `retry_repair_budget_exhausted` 或 `repairable` 缺失时 `HostDurableError` 被正确抛出并由 `ProjectionRunner` 记录为 failure。该路径风险低，因为生产 payload builder 已保证这些必填字段存在（见 `context_events.py` 的 validator）。

## Completion Report

- **Artifact path**: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-01-code-review-ds.md`
- **Verdict**: **PASS**（1 个低严重度 finding，不阻塞 merge）
- **Finding count**: 1（低）
- **Blocking open questions**: 无
- **Validation result**:
  - `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_context_compact_events.py` → **116 passed in 0.94s**（与 implementation artifact 报告一致）
  - `pyright` → **0 errors, 0 warnings, 0 informations**（与 implementation artifact 报告一致）

### 重点审查确认

| 审查项 | 结论 | 证据 |
|---|---|---|
| 只实现 OBS-SIG-01/P01，未提前实现 P02/P03/P04 | ✅ PASS | diff 仅涉及 `context_pressure` 派生与复制；`tool_timing`/`failure_metadata`/`partial_tool_call_signal` 仅在 `_TraceSummarySignals` 占位，无 producer 实现 |
| USAGE_REPORTED.context_pressure 由 Engine ingest 使用 Host budget 产生 | ✅ PASS | `_usage_context_pressure_signal`（`engine_ingest.py:4091`）接收 `BudgetEstimate`，调用 `decide_context_budget`，序列化 Host budget 阈值字段 |
| Tool Trace 只复制，不重复计算 | ✅ PASS | `_extract_usage_trace` 通过 `_trace_summary_signals(payload)` 从 payload 读取 `context_pressure`，无 `decide_context_budget` 调用；compaction 派生仅从现有 payload 字段构造 |
| estimate_unavailable/usage_invalid/missing input 保持 non-failing | ✅ PASS | 所有对应测试断言 `RunStatus.RUNNING` / `AttemptStatus.RUNNING`，投影信号正常附加 |
| Compaction 压力 signal 只从现有 payload 字段派生 | ✅ PASS | `_context_compaction_failed_pressure` / `_context_compaction_attempt_rejected_pressure` 仅读取 `payload` 和 `request_payload`，不改变 context event builder |
| Engine 仍不理解 Host budget | ✅ PASS | 无 `dayu/engine/` 修改；`decide_context_budget` 只在 `engine_ingest.py`（Host 层）调用 |
| Tool Trace 仍是 projection，不是 durable truth | ✅ PASS | `_extract_usage_trace` → `EventClass.PROJECTION_SIGNAL`；compaction 派生在 projection 中产生，不回写 EventLog |
| 测试覆盖 usage observed/unavailable/invalid + compaction failed/rejected + hot/cold 同源 | ✅ PASS | 7 个测试覆盖所有状态与变体；compaction 测试断言 `_cold_trace_summary == row.trace_summary` |
| 类型签名、中文 docstring、无 Any/object、无兼容 seam | ✅ PASS（1 个 F1 docstring 遗漏） | 所有新增函数有完整类型签名和中文 docstring；无 Any/object；无兼容性代码 |
| pyright 0 errors | ✅ PASS | 验证通过 |
