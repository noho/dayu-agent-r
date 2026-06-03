# WU-ENG-02 Slice 3 Code Review — AgentDS

## 审查范围与真源

- design_doc: `docs/host/design.md`
- control_doc: `docs/host/issues-implementation-control.md`
- plan: `docs/host/wu-eng-02-provider-request-identity-plan.md`
- implementation artifact: `docs/reviews/wu-eng-02-slice3-implementation-codex.md`

审查文件：
- `dayu/host/run_input.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/tool_trace.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_run_attempt_transitions.py`

## Verdict

**pass**

## Findings

### F1 — [LOW] `_close_worker_lifecycle` 中 `RunFailedData` 构造未显式传 `client_correlation_id`

- **文件**: `dayu/host/engine_ingest.py:2101-2111`
- **证据**: 
```python
# engine_ingest.py:2106-2111
data=RunFailedData(
    error_code=plan.reason,
    message=plan.reason,
    provider_request_id=None,
    recoverable=False,
),
```
`client_correlation_id` 未显式传递，依赖 dataclass 字段默认值 `None`。同一文件中其他地方（如 `_failed_plan`、`_unsupported_recovery_plan` 等）均显式传递 `client_correlation_id=None`。
- **影响**: 无运行时影响。该 `RunFailedData` 仅用于构造 `EngineEventCandidate` 的身份校验与重复检查，不参与 terminal payload 的构造。实际 terminal closeout 使用调用方传入的 `plan` 参数（该参数中的 `client_correlation_id` 已在调用方显式设置）。语义正确（lifecycle closeout 非 Runner 调用关联），但存在轻微一致性偏差。
- **建议**: 可选地显式补充 `client_correlation_id=None`，与其他 `RunFailedData` 构造点保持一致；不做强制要求。

### F2 — [INFO] `_TerminalPlan` 与 `TerminalCloseoutInput`/`ContextRecoveryCloseInput` 在 `client_correlation_id` 默认值策略上不一致

- **文件**: `dayu/host/engine_ingest.py:334` vs `dayu/host/durable/run_transition.py:387,425`
- **证据**:
  - `_TerminalPlan.client_correlation_id: str | None` — 无默认值，所有构造点必须显式传递。
  - `TerminalCloseoutInput.client_correlation_id: str | None = None` — 有默认值。
  - `ContextRecoveryCloseInput.client_correlation_id: str | None = None` — 有默认值。
- **影响**: 无运行时影响。所有当前调用点均显式传递了 `client_correlation_id`（包括 `TerminalCloseoutInput` 和 `ContextRecoveryCloseInput` 构造处）。设计上可解释：`_TerminalPlan` 是内部 plan 类型，无默认值强制调用方思考；`*CloseInput` 是 `run_transition` 模块公共接口，有默认值增加弹性。
- **建议**: 无需修改，记录供后续了解。

## 各审查维度详细分析

### 1. RunInputBuilder attempt_id/execution_id 投影

- `RunInputBuilder.build()` (`run_input.py:1677-1690`) 正确将 `attempt_snapshot.attempt_id` 和 `attempt_snapshot.execution_id` 传入 `AgentRunRequest`。
- `build_material_blocks()` 是独立的 material view helper，不构造 `AgentRunRequest`，不改变身份投影语义。
- 测试 (`test_run_input_builder.py:516-520`) 验证 `request.attempt_id == seeded.attempt_id` 和 `request.execution_id == seeded.execution_id`。

**结论**: 正确，无 gap。

### 2. LLMContextCompactor reactive/proactive identity 传递

- `_agent_request()` (`llm_compaction.py:264-284`) 透传 `request.attempt_id`/`request.execution_id` 到 `AgentRunRequest`。
- `CompactionRequest` 校验 (`compaction.py:805-809`) 对 REACTIVE 强制要求 `attempt_id` 和 `execution_id` 均为非空；PROACTIVE 允许均为 `None`。
- 测试 `test_llm_context_compactor_projects_reactive_identity` (`:926-956`) 验证 reactive 路径有值。
- 测试 `test_llm_context_compactor_projects_proactive_identity_none` (`:959-987`) 验证 proactive 路径为 `None`。

**结论**: 正确，覆盖充分。

### 3. Engine ingest client_correlation_id 写入覆盖度

审查覆盖了所有 `provider_request_id` 出现在的 provider-related 路径，确认 `client_correlation_id` 也已写入：

| 路径 | provider_request_id 来源 | client_correlation_id 来源 | 行号 |
|---|---|---|---|
| `RunFailedData` → `_run_failed_plan` → `TerminalCloseoutInput` | `data.provider_request_id` | `data.client_correlation_id` | `engine_ingest.py:3914-3924` |
| `RunFailedData` (recoverable) → diagnostic payload | `data.provider_request_id` | `data.client_correlation_id` | `engine_ingest.py:849-850` |
| `ContextCompactionRequestedData` → context recovery close | `data.provider_request_id` | `data.client_correlation_id` | `engine_ingest.py:1387-1388` |
| `ContextCompactionRequestedData` → compaction request payload | `data.provider_request_id` | `data.client_correlation_id` | `engine_ingest.py:1496,1503` |
| `ProviderProtocolErrorData` → diagnostic payload | `data.provider_request_id` | `data.client_correlation_id` | `engine_ingest.py:2419-2420` |
| `IterationCompletedData` → preview payload | `data.provider_request_id` | `data.client_correlation_id` | `engine_ingest.py:4219-4220` |
| `_close_worker_lifecycle` synthetic RunFailedData | `None` (hardcoded) | `None` (default) | `engine_ingest.py:2109` |
| usage projection signal | `None` (hardcoded, 非 EngineEvent) | 不适用 (UsageReportedData 无此字段) | `engine_ingest.py:2255` |

所有 provider-related 路径均已正确传播 `client_correlation_id`。lifecycle closeout 和 usage signal 是 Host internal 路径，不关联 Runner 调用，`None` 语义正确。

**未发现漏传或错误复用。**

### 4. TerminalCloseoutInput / ContextRecoveryCloseInput 新字段与校验

- `TerminalCloseoutInput.client_correlation_id` (`run_transition.py:387`) 和 `ContextRecoveryCloseInput.client_correlation_id` (`run_transition.py:425`) 均为 `str | None` 可选字段，有默认值 `None`。
- 校验使用与 `provider_request_id` 相同的 `_require_optional_non_empty_text` (`run_transition.py:5671-5673, 5314-5316`)，语义一致。
- terminal closeout payload 构造处 (`run_transition.py:4194, 4247`) 将 `client_correlation_id` 写入 EventLog payload。
- 测试 `test_failed_terminal_closeout_payload_includes_client_correlation_id` 验证 attempt 和 run payload 均包含该字段。

**结论**: 正确，语义与 `provider_request_id` 一致。

### 5. Tool Trace projection

- `client_correlation_id` 通过 `_optional_text()` 从 payload 提取 (`tool_trace.py:454`)，缺失/`None` 合法返回 `None`。
- 非文本值触发 `HostDurableError` (`tool_trace.py:921-923`)，与现有 Tool Trace payload validation 风格一致。
- 写入 `trace_summary_json` (`tool_trace.py:498, 566, 616, 793`) — 在三种 extract 路径（canonical / diagnostic / usage）中均一致。
- 写入 cold JSONL `fields` 顶层 (`tool_trace.py:711`)，便于直接检索诊断。
- 测试 `test_tool_trace_projection_includes_client_correlation_id` 验证 summary 与 cold JSONL 均包含。
- 测试 `test_tool_trace_projection_rejects_non_text_client_correlation_id` 验证非文本拒绝。
- 查询测试 (`test_tool_trace_queries.py`) 验证 `client_correlation_id` 出现在 hot row `trace_summary` 内。

**结论**: 实现正确，issue-70 analyzer 可通过 `trace_summary_json` 和 cold JSONL `trace_summary` 读取。missing/None 合法，非文本 Fail closed。

### 6. 架构与编码约束

- **DB schema**: 未新增 SQLite 表、列、索引或 migration。✓
- **分层**: 无反向依赖，Host → Engine 方向为字段透传。✓
- **兼容 wrapper**: 无。`CompactionRequest.attempt_id/execution_id` 已由 Slice 1 引入。✓
- **Any/object**: `client_correlation_id` 在所有声明位置均为 `str | None`。✓
- **魔法字符串**: 字段名 `"client_correlation_id"` 是 durable payload schema key，属于 schema 内字面量，CLAUE.md 允许。Tool Trace 侧定义为模块级常量 `_FIELD_CLIENT_CORRELATION_ID`。✓
- **engined_ingest.py 中 `cast` 与 `Mapping` 用法**: 均为已有模式，未新增 `cast` 绕过类型检查。✓

### 7. 测试覆盖

Plan 要求的测试覆盖：

| Plan 要求 | 覆盖状态 | 测试位置 |
|---|---|---|
| RunInputBuilder `AgentRunRequest.attempt_id/execution_id` 等于 snapshot 值 | ✓ | `test_run_input_builder.py:519-520` |
| Compactor reactive 有值 | ✓ | `test_llm_compaction.py:926-956` |
| Compactor proactive 为 None | ✓ | `test_llm_compaction.py:959-987` |
| Engine ingest provider diagnostic payload 含 `client_correlation_id` | ✓ | `test_engine_ingest_mapping.py:364` |
| Engine ingest terminal payload 含 `client_correlation_id` | ✓ | `test_engine_ingest_mapping.py:364-366` |
| Engine ingest context compaction payload 含 `client_correlation_id` | ✓ | `test_engine_ingest_mapping.py:451` |
| Engine ingest provider protocol error payload 含 `client_correlation_id` | ✓ | `test_engine_ingest_mapping.py:1576` |
| Engine ingest iteration completed preview 含 `client_correlation_id` | ✓ | `test_engine_ingest_mapping.py:1965-1992` |
| Tool Trace summary JSON / cold JSONL 含 `client_correlation_id` | ✓ | `test_tool_trace_projection.py:401-436` |
| Tool Trace non-text `client_correlation_id` 抛 `HostDurableError` | ✓ | `test_tool_trace_projection.py:439-462` |
| Terminal closeout payload 含 `client_correlation_id` | ✓ | `test_run_attempt_transitions.py:410-464` |

未覆盖路径（低影响）：
- `_close_worker_lifecycle` 合成 `RunFailedData` 的 `client_correlation_id=None` 默认行为无专门测试。该路径是 Host internal 生命周期收口，不关联 Runner 调用，且 `RunFailedData` 不进入 terminal payload（实际使用调用方传入的 `plan` 参数）。

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py \
  tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py tests/host/test_run_attempt_transitions.py \
  tests/host/test_llm_compaction.py -q
```
**结果**: `184 passed in 1.41s`

```bash
source .venv/bin/activate && pyright
```
**结果**: `0 errors, 0 warnings, 0 informations`

## Open Questions

none

## Residual Risks / Deferred Items

- Slice 4 (README 同步) 尚未执行，按 accepted plan 留待下个 slice。
- 全量测试未运行，仅运行了指定 Host 测试。远端 worker/proxy 真实传输路径未覆盖，但本 slice 不改变 wire protocol。
- issue-70 analyzer 是独立 work unit，本 WU 提供信号但不实现消费逻辑。

## Final Recommendation

通过。实现符合 plan 全部要求，无 blocking finding。建议进入 Slice 4（文档同步与最终验证）。
