# WU-OBS-SIGNALS-01 OBS-SIG-03 Code Review

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-03 / P03 Structured Failure Metadata`
- Reviewer: AgentMiMo
- Gate: code review only; no production code modification, no commit, no push, no PR.

Review covers workspace changes on branch `phaseflow/wu-obs-signals-p01-p04` relative to `main`. Key files: `dayu/host/tool_runtime.py`, `dayu/host/engine_ingest.py`, `dayu/host/tool_trace.py`, `dayu/host/README.md`, `tests/README.md`, `tests/host/test_tool_trace_projection.py`, `tests/host/test_engine_ingest_mapping.py`, `tests/host/test_toolruntime_executor.py`, `tests/host/test_toolruntime_accept_barrier.py`.

## Findings

### F-01 PASS — Motivation / Root Cause 成立

failure_metadata 的六个 variant 全部来自 durable facts 或 typed outcomes，不是文本解析或猜测：

- `tool_failed`: `ToolResultFailure.error`（error_code）+ `ToolResultFailure.hint`（repair_hint）— typed outcome 字段。
- `tool_cancelled`: `ToolCancelledOutcome.reason` / `message` / `hint` — typed outcome 字段。
- `policy_blocked`: `ToolPolicyDecision.kind` / `reason_code` — typed governance 决策字段。
- `provider_protocol_error`: `ProviderProtocolErrorData.error_code` — Engine event data 字段。
- `context_compaction_attempt_rejected` / `context_compaction_failed`: 从现有 canonical payload 字段派生。

未发现任何文本解析、raw payload 猜测或间接信号推断。

### F-02 PASS — Closed union 完整且正确

`_FAILURE_METADATA_ALLOWED_KINDS`（`tool_trace.py:175-182`）与 plan 定义的六个 variant 完全一致：

```
tool_failed, tool_cancelled, policy_blocked,
provider_protocol_error, context_compaction_attempt_rejected, context_compaction_failed
```

每个 variant 的字段与 plan schema 对齐（逐字段核对无差异）。`_validate_failure_metadata_variant`（`tool_trace.py:1330-1389`）对每个 variant 执行独立的字段校验，未识别的 failure_kind 以 `HostDurableError` fail closed。

### F-03 PASS — ToolRuntime producer outcome mapping 正确

`_failure_metadata_from_outcome`（`tool_runtime.py:4179-4234`）：

| Outcome 类型 | failure_kind | 关键字段来源 |
|---|---|---|
| `ToolCompletedOutcome` | null | 成功时无 metadata |
| `ToolFailedOutcome` | `tool_failed` | `error_code` ← `outcome.result.error`; `repair_hint` ← `outcome.result.hint` |
| `ToolCancelledOutcome` | `tool_cancelled` | `cancel_reason` ← `outcome.reason`; `cancel_message` ← `outcome.message`; `cancel_hint` ← `outcome.hint` |
| Policy blocked（非 ALLOW） | `policy_blocked` | `policy_decision_kind` ← `policy_decision.kind.value`; `policy_block_reason` ← `policy_decision.reason_code` |

- Cancellation 不是 tool_failed：`_validate_candidate_failure_metadata` 对 `ToolFactKind.CANCELLED` 要求 `expected_kind="tool_cancelled"`（`tool_runtime.py:647-658`）。
- Successful 结果 `failure_metadata=null`：`_validate_candidate_failure_metadata` 对 `ToolFactKind.COMPLETED` 要求 `expected_kind=None` 且 metadata 必须为 null（`tool_runtime.py:639-643`）。
- `policy_block_reason` 只来自 `reason_code`，不来自 message 文本。

### F-04 PASS — Bounded text 实现正确

`_bounded_failure_text`（`tool_runtime.py:4326-4351`）：

- null 输入 → `(value=None, sha256_digest=None, truncated=False)` ✓
- ≤512 chars → `(value=原文, sha256=full UTF-8 digest, truncated=False)` ✓
- \>512 chars → `(value=原文[:512], sha256=full UTF-8 digest, truncated=True)` ✓
- sha256 计算：`hashlib.sha256(value.encode('utf-8')).hexdigest()`，带 `sha256:` 前缀 ✓
- 不保存 full tool failure message body（`repair_hint` ← `hint`，不是 `message`）✓

`_validate_bounded_text_fields`（`tool_runtime.py:4387-4412`）与 `_validate_bounded_text_field`（`tool_trace.py:1435-1463`）逻辑对称：

- null + (digest!=None or truncated) → reject ✓
- 非 null + 非 str → reject ✓
- len > 512 → reject ✓
- digest 非 sha256 → reject ✓
- truncated 非 bool → reject ✓

### F-05 PASS — Engine ingest provider_error_code 来源正确

`_provider_protocol_failure_metadata`（`engine_ingest.py:5943-5970`）：

- `provider_error_code` ← `data.error_code`（Engine event data 字段，不是 raw provider payload）✓
- 测试 `test_provider_protocol_error_is_diagnostic_without_state_change`（`test_engine_ingest_mapping.py:1838`）中 raw payload code 设为 `"raw_payload_code_must_not_win"` 而 event data code 为 `"invalid_stream"`，断言 metadata 中 `provider_error_code="invalid_stream"` ✓
- 未修改 Engine public contract ✓

### F-06 PASS — Tool Trace projection 只 copy/validate/derive

- `_trace_summary_signals`（`tool_trace.py:1295-1316`）从 payload 复制四类 signal object，不重新计算。
- `_optional_tool_timing_signal` / `_optional_failure_metadata_signal` 执行 closed-union 校验，malformed 字段以 `HostDurableError` fail closed。
- Context compaction failed/rejected metadata 从现有 payload 派生（`tool_trace.py:1190-1290`），不修改 context event builders。
- Hot/cold 同源：`_trace_summary` 返回同一 summary dict 写入 hot row 和 cold JSONL，测试验证 `_cold_trace_summary(cold_lines, i) == row.trace_summary`。

### F-07 PASS — 分层和 scope 守住

- 未修改 SQLite schema。
- 未修改 ToolExecutor scheduling。
- 未修改 ToolRuntime governance 语义（accept/duplicate/timeout 逻辑不变）。
- 未修改 Engine public contract。
- 未提前实现 P04/analyzer taxonomy。
- `test_context_compact_events.py` 无变更（context compaction metadata 的投影覆盖在 `test_tool_trace_projection.py` 中）。

### F-08 PASS — README 更新合规

- `dayu/host/README.md`：仅修改一句，添加 "并投影 context pressure、tool timing、failure metadata 等只读结构化 signal"。符合 host README Agent 更新约束（tool trace 信号投影属于当前 host 边界变更）。
- `tests/README.md`：更新 Tool Trace correlation 测试描述，添加 "context pressure / tool timing / failure metadata 结构化 signal"。符合 tests README 约束。
- 未写入过程状态或未来计划。

### F-09 PASS — AGENTS 编码约束合规

- 所有新增函数提供完整中文 docstring（参数、返回值、异常）✓
- 无 `Any` / `object` / 无类型参数 / 无类型返回值 ✓
- 无不合理魔法字符串（常量均通过 `_FAILURE_KIND_*` / `_TOOL_TIMING_*` / `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS` 等模块级常量引用）✓
- 无兼容性 seam / 无兼容性 re-export ✓
- 无 LLM-facing 语义泄漏（failure_metadata 是 Host 内部信号结构，不暴露给 LLM）✓
- `_BoundedFailureText` 是 frozen slots dataclass，不是 God object ✓

### F-10 PASS — 测试覆盖充分

测试矩阵：

| 维度 | 测试文件 | 覆盖内容 |
|---|---|---|
| Producer: tool_failed | `test_toolruntime_executor.py` | null/512/513 repair_hint、truncated、sha256 |
| Producer: tool_cancelled | `test_toolruntime_executor.py` | message+hint 组合、kind≠tool_failed |
| Producer: policy_blocked | `test_toolruntime_executor.py` | reason_code 来源、完整 metadata 断言 |
| Producer: successful=null | `test_toolruntime_accept_barrier.py` | `failure_metadata is None` |
| Projection: signal copy | `test_tool_trace_projection.py` | 四类 signal hot/cold 一致性 |
| Projection: tool_timing | `test_tool_trace_projection.py` | available / missing_tool_result_meta |
| Projection: failure_metadata | `test_tool_trace_projection.py` | tool_failed / tool_cancelled / policy_blocked |
| Projection: provider_protocol | `test_tool_trace_projection.py` | failure_kind、provider_error_code |
| Projection: compact failed | `test_tool_trace_projection.py` | context_pressure + failure_metadata 派生 |
| Projection: compact rejected | `test_tool_trace_projection.py` | context_pressure + failure_metadata 派生 |
| Projection: null/missing | `test_tool_trace_projection.py` | signal 不写入 summary |
| Projection: malformed | `test_tool_trace_projection.py` | closed-union fail closed |
| Projection: non-object | `test_tool_trace_projection.py` | signal 字段类型 fail closed |
| Engine ingest: context_pressure | `test_engine_ingest_mapping.py` | 阈值、decision、null 场景 |
| Engine ingest: provider failure | `test_engine_ingest_mapping.py` | error_code 来源、raw payload 不干扰 |
| Consumer impact | `test_toolruntime_accept_barrier.py` | 已有 consumers 容忍 additive fields |

验证结果：

```
149 passed in 1.11s
pyright: 0 errors, 0 warnings, 0 informations
```

## Open Questions

无阻塞性开放问题。

## Residual Risk

1. **Context compaction request payload 可能缺失**：`_context_compaction_request_payload` 通过 `operation_id` 查找 request fact，若 request 事件已被清理则返回 None，pressure signal 中 `policy_ref` / `estimator_digest` 等字段为 null。这是 graceful degradation 而非 failure，风险可控。

2. **`_BoundedFailureText` 对空字符串的处理**：空字符串 `""` 通过 `len(value) > 512` 检查，sha256 计算正常，`truncated=False`。这是合理行为，但 analyzer 消费时需注意空字符串与 null 的语义差异。

3. **Sub-millisecond duration 截断**：`duration_ms = int(timedelta // ONE_MILLISECOND)` 对 sub-millisecond 执行时间截断为 0ms。对于 LLM 工具调用场景，sub-millisecond 概率极低，风险可忽略。

## Scope Creep Assessment

无 scope creep。所有变更严格在 OBS-SIG-03 plan 定义的 allowed files/modules 内，未引入 P04 partial tool-call signal、analyzer taxonomy、新 SQLite schema 或 Engine contract 变更。

## Architecture Alignment

- 分层架构 `UI -> Service -> Host -> Engine` 未被违反。
- Producer（ToolRuntime / Engine ingest）→ EventLog → Projection consumer（Tool Trace）→ hot/cold summary 数据流与 plan 一致。
- Tool Trace 只做 copy / validate / derive，不反向驱动 Run / Attempt 状态。
- `dayu.runtime` 未被触及。

## Test Coverage Assessment

覆盖率充分。Producer 路径覆盖三个 failure kind 的 happy path 和边界；Projection 路径覆盖 copy、validate、derive 三个维度；Malformed 路径覆盖 closed-union fail closed；Consumer impact 覆盖 additive field 容忍性。无明显覆盖盲区。

## Validation

- `pytest tests/host/test_tool_trace_projection.py tests/host/test_engine_ingest_mapping.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py` → 149 passed
- `pyright` → 0 errors

## Verdict

**PASS**

实现与 plan 完全对齐，closed union 六个 variant 字段正确，bounded text 处理正确，producer/projection/derive 三层数据流一致，分层约束未被违反，测试覆盖充分，pyright 零错误。无 blocking findings。
