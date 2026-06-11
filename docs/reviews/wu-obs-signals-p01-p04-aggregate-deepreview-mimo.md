# WU-OBS-SIGNALS-01 Aggregate Deep Review — AgentMiMo

**审查范围**：`phaseflow/wu-obs-signals-p01-p04` 相对 `main` 的完整差异
**审查日期**：2026-06-11
**审查人**：AgentMiMo
**设计真源**：`docs/host/design.md`、`docs/engine/design.md`、`docs/host/wu-obs-signals-p01-p04-plan.md`
**总控**：`docs/host/issues-implementation-control.md`

---

## Verdict: PASS

---

## Coverage Notes

本次审查覆盖以下关键路径：

### 生产代码
- `dayu/host/tool_runtime.py`（+371 行）：ToolAcceptResult 扩展、timing/failure signal 生产、candidate 校验、payload 写入、validation helpers
- `dayu/host/tool_trace.py`（+712 行）：TraceSummarySignals carrier、四类 signal 的 consumer-side 校验、canonical/diagnostic/usage 三条提取路径、bounded text 校验、partial tool-call summary 校验、compaction failed/rejected context_pressure 派生
- `dayu/host/engine_ingest.py`（+186 行）：USAGE_REPORTED context_pressure signal、PROVIDER_PROTOCOL_ERROR failure_metadata + partial_tool_call_signal 生产

### 测试代码
- `tests/host/test_toolruntime_accept_barrier.py`（+97 行）：failed/cancelled/governed_error 三种 fact kind 的 timing + failure_metadata payload 断言
- `tests/host/test_toolruntime_executor.py`（+208 行）：executor 级别 timing from ToolResultMeta 测试
- `tests/host/test_tool_trace_projection.py`（+877 行）：四类 signal 的 projection 正路径、malformed signal 拒绝、compaction failed/rejected context_pressure 派生、null signal 跳过
- `tests/host/test_tool_trace_queries.py`（+155 行）：run/tool_call/diagnostic/provider 四条查询路径 signal 保持
- `tests/host/test_engine_ingest_mapping.py`（+172 行）：provider protocol error partial_tool_call_signal 测试
- `tests/host/test_phase6_toolruntime_integration.py`（+89 行）：toolruntime accept 后 payload 携带 duration

### 设计文档与控制
- `docs/host/wu-obs-signals-p01-p04-plan.md`：四类 signal schema、non-goal、stop condition、data flow
- `docs/host/issues-implementation-control.md`：WU-OBS-SIGNALS-01 status、gate requirement、residual risk table
- `docs/host/README.md`：tool trace 信号投影说明更新
- `tests/README.md`：测试覆盖范围更新

---

## P01: context_pressure 只来自 Host budget/usage 和 context compact payload

### 审查结论：PASS

**证据**：

1. **USAGE_REPORTED 路径**（`engine_ingest.py:4109-4176`）：`_usage_context_pressure_signal` 只消费 `BudgetEstimate`（Host budget owner 已产出）和 `decide_context_budget` 结果，不重新实现阈值计算。`budget_decision` 来自 `decide_context_budget(estimate).value`，`overage_reason` 来自 `estimate.overage_reason.value`。token 字段来自 `data`（Engine usage data）和 `diagnostic`（Host observation diagnostic）。不引入治理副作用。

2. **CONTEXT_COMPACTION_FAILED 路径**（`tool_trace.py:966-1008`）：`_context_compaction_failed_pressure` 从既有 compaction failed canonical payload 派生，读取 `operation_id`、`budget_after_attempted_compact`、`fallback_action`、`fallback_policy_decision`、`retry_repair_budget_exhausted`。通过 `_context_compaction_request_payload` 追溯 request payload 获取 `policy_ref`、`estimator_digest`、`trigger_source`、`budget_reason`。只读取 EventLog，不写入。

3. **CONTEXT_COMPACTION_ATTEMPT_REJECTED 路径**（`tool_trace.py:1011-1034`）：`_context_compaction_attempt_rejected_pressure` 从 attempt rejected canonical payload 派生，读取 `operation_id`、`budget_after_attempted_compact`、`next_policy_decision`、`failure_category`、`repairable`。

**关键验证**：
- 三条路径均不修改 Run/Attempt 状态
- `context_pressure` 是 `USAGE_REPORTED` projection_signal 的附加字段，projection_signal 不能反向驱动治理（design.md §13）
- 不从 Engine 查询 budget，Engine 不理解 Host context budget policy（design.md §15）

---

## P02: tool_timing 只来自 ToolResultMeta.duration_ms

### 审查结论：PASS

**证据**：

1. **生产者**（`tool_runtime.py:6061-6090`）：`_tool_timing_from_meta` 唯一输入为 `ToolResultMeta | None`。当 meta 存在时，`duration_ms = int((meta.finished_at - meta.started_at) // _ONE_MILLISECOND)`，`started_at`/`finished_at` 使用 `.isoformat()`。当 meta 为 None 时，status 为 `missing_tool_result_meta`，所有 timing 字段为 null。

2. **来源限定**（`tool_runtime.py:6041-6059`）：`_tool_result_meta` 从 typed outcome 提取 meta：
   - `ToolCompletedOutcome` → `outcome.result.meta`
   - `ToolFailedOutcome` → `outcome.result.meta`
   - `ToolCancelledOutcome` → `outcome.meta`
   - `ToolAwaitingOutcome` → TypeError

3. **不污染 ToolRuntime 治理语义**：`tool_timing` 是 `ToolAcceptResult` 的附加 dataclass 字段，不参与 accept barrier、duplicate governance、policy decision 或 state transition。写入 payload 时（`tool_runtime.py:3831-3832`）与 `accepted_evidence_envelope` 平行，不影响已有字段。

**关键验证**：
- `_validate_tool_timing_signal`（`tool_runtime.py:4390-4432`）严格校验 schema_version、status、duration_ms 非负、duration_source 为 `tool_result_meta`
- consumer-side `_optional_tool_timing_signal`（`tool_trace.py:1043-1072`）重复校验，确保 malformed payload 被拒绝
- 测试覆盖 `available` 和 `missing_tool_result_meta` 两种 status

---

## P03: failure_metadata 是 closed union，来源只限 typed outcome / Engine data / context payload

### 审查结论：PASS

**证据**：

1. **ToolRuntime 生产者**（`tool_runtime.py:6091-6150`）：`_failure_metadata_from_outcome` 按 outcome 类型分支：
   - `ToolCompletedOutcome` → `None`
   - `ToolFailedOutcome` → `failure_kind="tool_failed"`，含 `error_code`、`repair_hint`（bounded text）、`diagnostic_refs`
   - `ToolCancelledOutcome` → `failure_kind="tool_cancelled"`，含 `cancel_reason`、`cancel_message`（bounded text）、`cancel_hint`（bounded text）、`diagnostic_refs`
   - `ToolPolicyDecisionKind != ALLOW` → `failure_kind="policy_blocked"`，含 `policy_decision_kind`、`policy_block_reason`、`diagnostic_refs`

2. **EngineIngest 生产者**（`engine_ingest.py:5947-5973`）：`_provider_protocol_failure_metadata` → `failure_kind="provider_protocol_error"`，含 `provider_error_code`、`diagnostic_refs`（raw_payload_ref + provider_request_id）

3. **ToolTrace consumer 派生**（`tool_trace.py:1091-1165`）：
   - `_context_compaction_attempt_rejected_failure_metadata` → `failure_kind="context_compaction_attempt_rejected"`
   - `_context_compaction_failed_failure_metadata` → `failure_kind="context_compaction_failed"`

4. **闭集验证**（`tool_trace.py:155-175`）：`_FAILURE_METADATA_ALLOWED_KINDS = frozenset({tool_failed, tool_cancelled, policy_blocked, provider_protocol_error, context_compaction_attempt_rejected, context_compaction_failed})`。`_optional_failure_metadata_signal` 拒绝不在 frozenset 中的 failure_kind。

5. **Bounded text 规则**（`tool_runtime.py:6187-6210`）：`_bounded_failure_text` 对非 null 原文截取前 512 字符，计算 full original UTF-8 sha256 digest，设置 `truncated=True` 当 `len(value) > 512`。consumer-side `_validate_bounded_text_field`（`tool_trace.py:1193-1228`）重复校验三字段组合一致性。

**关键验证**：
- 六种 failure_kind 与 plan 设计完全一致
- 每种变体的 signal_source 校验（`_require_failure_source`）确保 source 与 kind 一一对应
- 测试覆盖 malformed signal 拒绝（schema_version 错误、signal_source 不匹配、repair_hint 超限等）

---

## P04: partial_tool_call_signal 只来自 Engine bounded PartialToolCallSummary

### 审查结论：PASS

**证据**：

1. **Engine contract 预存在**：`dayu/engine/contracts/partial_tool_call.py` 是 commit `d478aca4` 引入的既有 Engine 公共契约。`PartialToolCallSummary` 是 frozen dataclass，字段为 `tool_call_index`、`tool_call_id`（bounded）、`name_fragment`（bounded）、`arguments_byte_size`、`arguments_sha256`。不含 raw arguments。

2. **生产者**（`engine_ingest.py:5975-6031`）：`_provider_protocol_partial_tool_call_signal` 序列化 `PartialToolCallSummary` 元组。`_partial_tool_call_summary_payload` 直接映射字段，`arguments_present = summary.arguments_sha256 is not None`。不读取 raw args。

3. **Consumer 校验**（`tool_trace.py:1139-1190`）：`_optional_partial_tool_call_signal` 校验 schema_version、signal_source 为 `PROVIDER_PROTOCOL_ERROR`、partial_tool_call_count 与 partial_tool_calls 数组长度一致、summary_status 与 count 一致性。`_validate_partial_tool_call_summary` 校验 tool_call_index ≥ 0、arguments_byte_size ≥ 0、arguments_sha256 为裸 64 位小写 hex（`_is_bare_sha256_hex`）、arguments_present 与 sha256 一致性。

4. **无 raw args 泄漏**：signal 中只有 `arguments_byte_size`（int）和 `arguments_sha256`（digest），不含 raw arguments payload。`raw_payload_present` 标志仅指示 Host 是否存储了 raw payload descriptor（通过 `raw_descriptor`），不包含 args 内容。

**关键验证**：
- P04 不改变 Engine 公共 contract（只消费既有的 `PartialToolCallSummary`）
- `_is_bare_sha256_hex` 确保 digest 格式正确（64 位小写 hex，与 Engine `sha256_digest` 前缀格式不同）
- 测试覆盖 `summary_status="none"` 和 `"present"` 两种状态、count mismatch、invalid sha256

---

## OBS-SIG-05: Query helper 集成测试证明四类信号在四条查询路径中保持

### 审查结论：PASS

**证据**（`tests/host/test_tool_trace_queries.py:204-333`）：

`test_query_helpers_return_rows_ordered_by_event_sequence` 构造了一个包含四类 signal 的完整 EventLog 集合：
- `event-1`：TOOL_CALL_REQUESTED（无 signal）
- `event-2`：TOOL_RESULT_ACCEPTED（携带 context_pressure + tool_timing + failure_metadata）
- `event-3`：RUN_FAILED（携带 partial_tool_call_signal）

通过 `catch_up_tool_trace_projection` 投影后，验证四条查询路径：

| 查询路径 | 验证内容 |
|---|---|
| `read_tool_trace_by_run` | event-2 的 trace_summary 保留 context_pressure、tool_timing、failure_metadata；event-3 保留 partial_tool_call_signal |
| `find_tool_trace_by_tool_call_id` | 同上，signal 在 by_tool_call 路径中保持 |
| `find_tool_trace_by_diagnostic_ref` | event-2 的 trace_summary 保留 context_pressure、tool_timing、failure_metadata |
| `find_tool_trace_by_provider_request_id` | event-3 的 trace_summary 保留 partial_tool_call_signal |

`test_provider_request_id_terminal_diagnostic_query` 额外验证了 provider_request_id 查询的 terminal diagnostic chain 中 partial_tool_call_signal 完整保持。

**关键验证**：
- 四类 signal field 与 `_ALL_SIGNAL_FIELDS` 常量完全对齐
- `assert set(_ALL_SIGNAL_FIELDS) == set(signal_objects)` 确保测试覆盖了所有 signal 类型

---

## Engine contract/schema、ToolRuntime、analyzer 过度扩展或层级反向依赖

### 审查结论：PASS

**证据**：

1. **Engine 公共 contract 未改变**：本分支只新增 `from dayu.engine.contracts.partial_tool_call import PartialToolCallSummary` 导入（`engine_ingest.py:52`），该模块是 commit `d478aca4` 引入的既有 Engine 契约。未新增、修改或删除任何 Engine 公共类型。

2. **EventLog payload 变更是纯 additive**：
   - `USAGE_REPORTED` projection_signal：新增 `context_pressure` 可选字段
   - `TOOL_RESULT_ACCEPTED` canonical fact：新增 `tool_timing` 和 `failure_metadata` 字段
   - `PROVIDER_PROTOCOL_ERROR` diagnostic：新增 `partial_tool_call_signal` 和 `failure_metadata` 字段
   - 不删除、不修改任何既有字段

3. **无反向依赖**：
   - `tool_trace.py` 不导入 `engine_ingest.py` 或 `tool_runtime.py`
   - `tool_runtime.py` 不导入 `engine_ingest.py` 或 `tool_trace.py`
   - `engine_ingest.py` 不导入 `tool_runtime.py` 或 `tool_trace.py`
   - 三者共同依赖 `dayu.engine.contracts`（Engine→Host 正向消费方向）和 `dayu.contracts`（公共契约）

4. **ToolRuntime 无过度扩展**：`tool_timing` 和 `failure_metadata` 是 `ToolAcceptResult` 的 dataclass 字段，不影响 accept barrier、duplicate governance、policy decision、state transition 或 execution 语义。`_validate_tool_accept_result` 新增校验但不改变已有校验逻辑。

5. **无 analyzer 实现**：本 WU 明确不实现 WU-OBS-00 analyzer body（plan non-goal）。

---

## Hot/cold summary 等价、状态转移副作用非治理依据、README 更新触发

### 审查结论：PASS

**证据**：

1. **Hot/cold summary 等价**：`_trace_summary`（`tool_trace.py:1136-1227`）通过 `signals.present_items()` 将非空 signal 追加到 summary dict。Cold JSONL 写入使用同一个 summary dict。Hot row 存储的 `trace_summary_json` 与 cold JSONL 的 `trace_summary` 来源相同。

2. **状态转移副作用非治理依据**：四类 signal 写入的 payload 类型：
   - `context_pressure`：projection_signal（`USAGE_REPORTED`）→ 不是 canonical_fact，不驱动状态转移
   - `tool_timing`：canonical_fact（`TOOL_RESULT_ACCEPTED`）→ 是附加字段，不影响 accept barrier 决策
   - `failure_metadata`：canonical_fact + diagnostic → 是附加字段，不改变 Run/Attempt 状态机
   - `partial_tool_call_signal`：diagnostic（`PROVIDER_PROTOCOL_ERROR`）→ 不是 canonical_fact

3. **README 更新触发合规**：
   - `dayu/host/README.md`：因 `dayu/host/` 修改触发，更新 tool trace 投影说明（+1 行），符合职责范围
   - `tests/README.md`：因 `tests/` 修改触发，更新 Tool Trace correlation 覆盖说明（+1 行），符合职责范围
   - 无其他 README 需要更新（不涉及 `dayu/engine/`、`dayu/fins/`、`dayu/config/`、`dayu/` 根目录变更）

---

## Pyright/tests 充分性与剩余风险归属

### 审查结论：PASS

**证据**：

1. **Pyright**：`dayu/host/tool_trace.py`、`dayu/host/tool_runtime.py`、`dayu/host/engine_ingest.py` → 0 errors, 0 warnings, 0 informations。

2. **Tests**：160 affected Host tests passed（`test_tool_trace_projection.py` 33 passed, `test_tool_trace_queries.py` 3 passed, `test_toolruntime_accept_barrier.py` 19 passed, `test_toolruntime_executor.py` 61 passed, `test_engine_ingest_mapping.py` 39 passed, `test_phase6_toolruntime_integration.py` 5 passed）。

3. **测试覆盖维度**：
   - signal 生产正路径（all 4 types）
   - signal consumer 校验（schema/source/status/field validation）
   - malformed signal 拒绝（12 parametrized rejection cases）
   - compaction failed/rejected context_pressure 派生
   - bounded text 一致性（null/non-null/truncated 三种状态）
   - partial tool-call summary 一致性（count/status/sha256/present）
   - query helper 四条路径 signal 保持
   - hot/cold projection 等价
   - idempotency（重复 accept 不改变 signal）

4. **剩余风险（已有 WU-OBS-00 归属）**：
   - WU-OBS-00 analyzer body 尚未实现，四类 signal 的消费端分析逻辑待后续 WU 实现
   - `failure_metadata` 中 `provider_protocol_error` 和 `context_compaction_*` 变体的 analyzer 消费路径待验证
   - `partial_tool_call_signal` 的 `arguments_sha256` 跨 provider session 比对逻辑待 analyzer 实现
   - 以上风险均已在 `docs/host/issues-implementation-control.md` residual risk table 中记录并归属 WU-OBS-00

---

## Findings: None

本次审查未发现需要修复的缺陷。四类 signal 的实现严格遵循 plan 设计，不引入治理副作用，不扩展 Engine 公共 contract，不产生反向依赖，bounded text 规则正确，closed union 完整，测试覆盖充分。
