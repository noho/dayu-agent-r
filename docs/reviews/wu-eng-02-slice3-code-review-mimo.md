# WU-ENG-02 Slice 3 Code Review — AgentMiMo

## Gate

- work unit: WU-ENG-02
- gate: slice-3-code-review
- reviewer: AgentMiMo
- artifact path: `docs/reviews/wu-eng-02-slice3-code-review-mimo.md`
- scope: Slice 3 Host projection / ingest / Tool Trace 诊断链路闭环

## Verdict

**pass-with-findings**

0 blocking findings. 2 non-blocking findings (1 Low, 1 Info).

## Findings

### F1 [LOW] — `_usage_reported` / `_usage_observation_diagnostic_digest` payload 不含 `client_correlation_id`

- **文件**: `dayu/host/engine_ingest.py:2246-2262`、`dayu/host/engine_ingest.py:3646-3658`
- **直接证据**: `_usage_reported` payload 硬编码 `"provider_request_id": None`，但未写入 `"client_correlation_id"`。同理 `_usage_observation_diagnostic_digest` payload 也硬编码 `"provider_request_id": None` 但无 `client_correlation_id`。
- **影响**: `UsageReportedData` Engine contract 不含 `client_correlation_id`，这些 payload 是 `PROJECTION_SIGNAL` 类型而非 provider diagnostic。当前实现符合 plan scope（"any existing payload that already writes `provider_request_id` from the affected EngineEvent"——此处 `provider_request_id` 是硬编码 `None`，非来自 EngineEvent data）。不影响 issue-70 analyzer 对 provider diagnostic 链路的消费。
- **建议**: 不阻塞。若未来 analyzer 需要 usage observation 也带 `client_correlation_id`，需先扩展 `UsageReportedData` Engine contract。可记录为 deferred item。

### F2 [INFO] — `client_correlation_id` 通过 dict spread 注入 `CONTEXT_COMPACTION_REQUESTED` payload，绕过 `validate_context_compaction_requested_payload`

- **文件**: `dayu/host/engine_ingest.py:1488-1503`
- **直接证据**: 代码使用 `{**build_context_compaction_requested_payload(...), "client_correlation_id": data.client_correlation_id}` 模式。`build_context_compaction_requested_payload`（`context_events.py:206`）不接受 `client_correlation_id` 参数，返回的 payload 也不含该字段。validator `validate_context_compaction_requested_payload`（`context_events.py:260`）不校验 `client_correlation_id`。
- **影响**: 当前正确——`client_correlation_id` 是一个附加可选字段，validator 校验的是 base payload 结构。但如果未来 validator 增加严格白名单（拒绝未知 key），该模式会断裂。
- **建议**: 不阻塞。当前实现可接受。若后续 `validate_context_compaction_requested_payload` 增加 strict key 校验，需同步将 `client_correlation_id` 纳入 builder。

## 审查范围逐项核对

### 1. RunInputBuilder attempt_id / execution_id 透传

| 检查项 | 结论 |
|--------|------|
| `RunInputBuilder.build()` 是否正确传 `attempt_id` / `execution_id` | PASS — `run_input.py:1680-1681` 直接从 `attempt_snapshot` 投影 |
| 非普通路径语义是否改变 | PASS — `build()` 仅在 ordinary dispatch 路径调用，不改变 compactor 路径 |

### 2. LLMContextCompactor reactive / proactive identity 传递

| 检查项 | 结论 |
|--------|------|
| reactive compaction 透传 `attempt_id` / `execution_id` | PASS — `llm_compaction.py:268-269` 从 `CompactionRequest` 透传 |
| proactive compaction 保持 `None` | PASS — `CompactionRequest` proactive 路径 `attempt_id=None, execution_id=None` |

### 3. Engine ingest `client_correlation_id` 写入覆盖

| Provider-related payload | 有 `provider_request_id` | 有 `client_correlation_id` | 结论 |
|--------------------------|--------------------------|---------------------------|------|
| provider protocol diagnostic | ✓ `data.provider_request_id` | ✓ `data.client_correlation_id` | PASS |
| context compaction requested (reactive) | ✓ `data.provider_request_id` | ✓ `data.client_correlation_id` (via dict spread) | PASS |
| recoverable run_failed diagnostic | ✓ `data.provider_request_id` | ✓ `data.client_correlation_id` | PASS |
| run_failed terminal summary / plan | ✓ `data.provider_request_id` | ✓ `data.client_correlation_id` | PASS |
| IterationCompleted preview | ✓ `data.provider_request_id` | ✓ `data.client_correlation_id` | PASS |
| `_final_answer_plan` (non-provider) | `None` (hardcoded) | `None` (hardcoded) | PASS — 非 provider 路径 |
| `_unsupported_recovery_plan` | `provider_request_id` (param) | `None` (hardcoded) | PASS — 无 EngineEvent context |
| `_unsupported_waiting_plan` | `None` | `None` | PASS — 非 provider 路径 |
| `_failed_lifecycle_plan` | `None` | `None` | PASS — 非 provider 路径 |
| `_lost_lifecycle_plan` | `None` | `None` | PASS — 非 provider 路径 |
| `_usage_reported` | `None` (hardcoded) | 未写入 | 见 F1 — 不阻塞 |
| `_usage_observation_diagnostic_digest` | `None` (hardcoded) | 未写入 | 见 F1 — 不阻塞 |

### 4. TerminalCloseoutInput / ContextRecoveryCloseInput 新字段

| 检查项 | 结论 |
|--------|------|
| `TerminalCloseoutInput.client_correlation_id` 类型 | `str | None = None`，与 `provider_request_id` 一致 |
| `_validate_terminal_input` 校验 | `_require_optional_non_empty_text`，与 `provider_request_id` 一致 |
| `ContextRecoveryCloseInput.client_correlation_id` 类型 | `str | None = None`，与 `provider_request_id` 一致 |
| `_validate_context_recovery_close_input` 校验 | `_require_optional_non_empty_text`，与 `provider_request_id` 一致 |
| `_attempt_terminal_payload` FAILED 路径 | 写入 `client_correlation_id` |
| `_run_terminal_payload` FAILED 路径 | 写入 `client_correlation_id` |
| `_context_recovery_attempt_failed_event_request` | 写入 `client_correlation_id` |
| `_run_recovering_event_request` | 写入 `client_correlation_id` |

### 5. Tool Trace projection

| 检查项 | 结论 |
|--------|------|
| `_optional_text` 处理缺失 `None` | PASS — `tool_trace.py:918-920`，`value is None` 返回 `None` |
| `_optional_text` 处理非文本 | PASS — `tool_trace.py:921-923`，`isinstance(value, str)` 校验，非文本抛 `HostDurableError` |
| `_extract_canonical_trace` 提取 | PASS — `tool_trace.py:454` |
| `_extract_diagnostic_trace` 提取 | PASS — `tool_trace.py:528` |
| `_extract_usage_trace` 提取 | PASS — `tool_trace.py:581` |
| `_trace_summary` 包含字段 | PASS — `tool_trace.py:793` |
| `_build_cold_line` 顶层包含 | PASS — `tool_trace.py:711` |
| `_build_cold_line` trace_summary 内含 | PASS — `tool_trace.py:723` (via `extracted.trace_summary`) |
| issue-70 analyzer 可消费 | PASS — summary JSON 与 cold JSONL 均暴露 `client_correlation_id` |

### 6. 架构 / 分层 / schema / 编码规范

| 检查项 | 结论 |
|--------|------|
| 分层违反 | 无 |
| 新增 DB schema（表/列/索引） | 无 |
| 兼容 wrapper | 无 |
| `Any` / `object` 使用 | 无 |
| 魔法字符串（非 schema） | 无 |
| 反向依赖 | 无 |

### 7. 测试覆盖

| Plan 要求的测试 | 状态 | 证据 |
|-----------------|------|------|
| RunInputBuilder `attempt_id/execution_id` 断言 | PASS | `test_run_input_builder.py:519-520` |
| Compactor reactive identity | PASS | `test_llm_compaction.py` `test_llm_context_compactor_projects_reactive_identity` |
| Compactor proactive identity None | PASS | `test_llm_compaction.py` `test_llm_context_compactor_projects_proactive_identity_none` |
| Engine ingest: provider diagnostic payload | PASS | `test_engine_ingest_mapping.py:1573` |
| Engine ingest: run_failed terminal payload | PASS | `test_engine_ingest_mapping.py:363, 365` |
| Engine ingest: context compaction requested | PASS | `test_engine_ingest_mapping.py:451` |
| Engine ingest: IterationCompleted preview | PASS | `test_engine_ingest_mapping.py:1965-1992` |
| Tool Trace summary 含 client_correlation_id | PASS | `test_tool_trace_projection.py:398-427` |
| Tool Trace non-text 拒绝 | PASS | `test_tool_trace_projection.py:430-465` |
| Tool Trace query rows 含 client_correlation_id | PASS | `test_tool_trace_queries.py:190-194, 246-254` |
| Terminal closeout payload 含 client_correlation_id | PASS | `test_run_attempt_transitions.py:410-465` |
| `ContextRecoveryCloseInput` 专用测试 | 缺失 | 无直接测试（validation 通过 run_transition.py 间接路径覆盖） |

## Validation Commands / Results

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_run_attempt_transitions.py tests/host/test_llm_compaction.py
# 184 passed in 1.36s
```

```bash
source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations
```

## Open Questions

**OQ1**: `UsageReportedData` 不含 `client_correlation_id`，usage observation payload 硬编码 `provider_request_id: None` 但不写入 `client_correlation_id`。若 issue-70 analyzer 需要在 usage observation 中也关联 client correlation，需扩展 Engine contract。当前不阻塞，建议记录为 deferred。

## Residual Risks / Deferred Items

1. **R1**: F1 — usage observation payload 不含 `client_correlation_id`。若 analyzer 需求，需扩展 `UsageReportedData` contract 并同步 payload。
2. **R2**: `ContextRecoveryCloseInput.client_correlation_id` 无专用单元测试（通过 engine_ingest reactive compaction 路径间接覆盖）。风险低——validation 函数与 `provider_request_id` 完全对称。
3. **R3**: control doc 中已记录的 deferred findings（WU-ENG-02-S1-R1: tool timeout `RunFailedData` correlation；WU-ENG-02-S1-R2: force-answer EngineEvent correlation 断言）应在 Slice 4 final validation 裁决。
4. **R4**: README sync 按 accepted plan 延迟到 Slice 4。

## Final Recommendation

**pass-with-findings**。0 条 blocking findings。2 条 non-blocking findings（F1 Low, F2 Info）。实现正确覆盖 plan Slice 3 全部要求：Host attempt/execution identity 进入 `AgentRunRequest`；EngineEvent `client_correlation_id` 进入所有 provider-related EventLog payload；Tool Trace summary JSON / cold JSONL 暴露 `client_correlation_id`。无新增 DB schema、无分层违反、无兼容 wrapper。验证 184 tests passed，pyright 0 errors。
