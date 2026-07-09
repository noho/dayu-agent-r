# Semantic Ownership Code Review — Full Repository

## Scope

- **Mode**: All Repository (semantic ownership adversarial review)
- **Branch**: `phase/host-issues-control`
- **Base**: `main`
- **Output file**: `docs/reviews/fullrepo-semantic-ownership-review-mimo.md`
- **Review date**: 2026-07-09
- **Included scope**: `dayu/host/`, `dayu/engine/`, `dayu/runtime/`, `dayu/contracts/`, `tests/host/`, `tests/engine/`, `tests/runtime/`, `tests/contracts/`
- **Excluded scope**: `dayu/fins/`, `dayu/tools/`, `dayu/cli/`, `dayu/service/`, `dayu/documents/`, `utils/`, `workspace/`
- **Parallel review coverage**: 5 shards
  1. **Host durable truth** — `dayu/host/durable/` (event_log, state, run_transition, outbox, audit, memory, tool_trace, projection, read_model, payload, artifact, wait, idempotency, liveness, session_lifecycle, storage_lifecycle, connection, schema, codec, options, errors, maintenance, purge) + `dayu/host/dispatch.py`, `dayu/host/waiting.py`, `dayu/host/wait_adapter.py`, `dayu/host/recovery.py`, `dayu/host/recovery_process.py`, `dayu/host/outbox.py`
  2. **Host projections** — `dayu/host/memory.py`, `dayu/host/tool_trace.py`, `dayu/host/run_input.py`, `dayu/host/projection.py`, `dayu/host/read_model.py`, `dayu/host/read_api.py`, `dayu/host/terminal_payload.py`, `dayu/host/compact_*.py`, `dayu/host/compaction*.py`, `dayu/host/context_*.py`, `dayu/host/evidence.py`, `dayu/host/opaque_ref.py`, `dayu/host/payload_resolution.py`, `dayu/host/tool_runtime*.py`, `dayu/host/tooling.py`, `dayu/host/engine_ingest.py`
  3. **Engine** — `dayu/engine/agent.py`, `dayu/engine/_default_runner.py`, `dayu/engine/provider_extensions.py`, `dayu/engine/contracts/` 全部, `dayu/engine/runners/openai/` 全部, 交叉引用 `dayu/host/engine_ingest.py`
  4. **Runtime / contracts / layering** — `dayu/runtime/` 全部, `dayu/contracts/` 全部, import boundary 扫描
  5. **Tests / docs alignment** — `tests/host/` 40+ 测试文件, `tests/engine/`, `tests/runtime/`, `tests/contracts/` 关键测试, AGENTS.md

---

## Findings

### 01-High-finish_reason 双源竞争：SSE parser 产出两个冲突 finish_reason，Agent 静默选择非权威源

- **严重性**: High
- **出错语义**: `finish_reason` 是 LLM 完成原因的关键业务事实，决定 Agent 状态机走向（是否进入工具调用、是否触发 continuation、是否标记 degraded/filtered）。该事实当前有两个冲突来源，Agent 静默选择更早的、非权威的信号源。
- **直接证据**:
  - `dayu/engine/runners/openai/sse_parser.py:700-714` — `_finalize_success()` 在 tool_calls 存在时，`RunnerContentCompletedData` 携带 `self._finish_reason or FinishReason.STOP`（来自流式 chunk 的原始 `choice.finish_reason`），紧随其后的 `RunnerDoneData` 携带 `FinishReason.TOOL_CALLS`（parser 计算得出）。两者可能不一致。
  - `dayu/engine/agent.py:1449-1469` — `_consume_runner_event` 处理 `RunnerDoneData` 时，当 `state.finish_reason is not None and state.finish_reason is not data.finish_reason`，**静默选择 `state.finish_reason`**（即 `RunnerContentCompletedData` 的值），仅记 warning，无注释说明此选择的正确性依据。
  - `dayu/engine/agent.py:1569` — `_classify_iteration` 中 `finish_reason = state.finish_reason or FinishReason.STOP` 将可能错误的 finish_reason 传入 `_FinalDecision`。
  - `dayu/host/engine_ingest.py:4346` — `_final_answer_plan` 直接使用 `data.finish_reason.value` 写入 durable terminal closeout。Host 无法校验其正确性。
- **错误语义第一次进入系统的位置**: `sse_parser.py:700-714` — `_finalize_success()` 同时产出两个携带不同 finish_reason 的事件。
- **当前 owner boundary 被放错在哪里**: Agent `_consume_runner_event` 将 finish_reason 权威判断放在 RunnerEvent 消费阶段，且选择了更早的非权威信号源。
- **正确 owner boundary 应在哪里**: `RunnerDoneData` 是 Runner 对本次调用完成原因的最终裁定（authority signal）。Agent 应以 `RunnerDoneData.finish_reason` 为权威源，`RunnerContentCompletedData.finish_reason` 仅为中间态快照。
- **哪些下游消费者被迫补丁**: Host `engine_ingest.py:4346` 的 durable terminal closeout 直接消费该 finish_reason，无法校验正确性。
- **最佳修复方向**: (a) 从 `RunnerContentCompletedData` 移除 `finish_reason` 字段——该信号的语义是"正文完成"，finish_reason 属于 `RunnerDoneData` 的职责；或 (b) Agent 在 `RunnerDoneData` 到达时以 `data.finish_reason` 覆盖 `state.finish_reason`。方案 (a) 更彻底，消除双源。
- **推荐测试**: 构造 SSE 流：先发送 `choices[0].finish_reason="stop"` 的 chunk（携带 content），再发送 tool call delta，最后发送 `[DONE]`。验证 `FinalAnswerData.finish_reason` 与 `RunnerDoneData.finish_reason` 一致。
- **residual risk**: 非流式 parser（`non_stream_parser.py:337`）也在此字段上写入了 provider 原始 finish_reason，需同步移除。

---

### 02-High-Usage 信号在 Runner 边界不聚合、不携带 provider_request_id，Host 被迫写入不完整 durable fact

- **严重性**: High
- **出错语义**: `usage`（prompt_tokens / completion_tokens / total_tokens）是 per-provider-response 的关键业务事实。该事实的归属（哪次 provider response 产生的 usage）和完整性（是增量还是全量）在 Runner → Engine → Host 传播链上完全丢失。
- **直接证据**:
  - `dayu/engine/runners/openai/sse_parser.py:632-661` — `_handle_usage()` 直接 yield 每个 chunk 中的 usage 为独立的 `RunnerUsageRecordedData`，无聚合。若 provider 在多个 SSE chunk 中发送 usage（DeepSeek 等已知行为），Runner 会产出多个独立 usage 事件。
  - `dayu/engine/contracts/runner_events.py:133-145` — `RunnerUsageRecordedData` 无 `provider_request_id` 字段。
  - `dayu/engine/contracts/engine_events.py:322-335` — `UsageReportedData` 同样无 `provider_request_id`。
  - `dayu/host/engine_ingest.py:2878` — Host 写入 usage projection signal 时被迫硬编码 `"provider_request_id": None`。这是"下游补丁掩盖上游缺失"的直接证据。
- **错误语义第一次进入系统的位置**: `runner_events.py:133-145` — `RunnerUsageRecordedData` 契约设计时未包含 `provider_request_id`。
- **当前 owner boundary 被放错在哪里**: Runner 层将"从 provider 协议中提取 usage"与"归一化 usage 为最终快照"两个职责混为一谈。
- **正确 owner boundary 应在哪里**: Runner 应在流结束时聚合所有 usage chunk 为单个 `RunnerUsageRecordedData`，并携带 `provider_request_id`。
- **哪些下游消费者被迫补丁**: Host `engine_ingest.py:2878` 硬编码 `provider_request_id: None`；Host context budget 诊断只能基于不完整的 usage 数据估算上下文压力。
- **最佳修复方向**: (a) 在 `RunnerUsageRecordedData` 上增加 `provider_request_id: str | None` 字段；(b) SSE parser 在流结束时聚合所有 usage chunk 为单个事件；(c) Agent 消费时透传 `provider_request_id` 到 `UsageReportedData`。
- **推荐测试**: 构造包含两个 usage chunk 的 SSE 流（第一个 `prompt_tokens=100`，第二个 `prompt_tokens=200`），验证 Runner 只产出一个 `RunnerUsageRecordedData`，且 Host 收到的 `USAGE_REPORTED` event payload 中 `provider_request_id` 非 None。
- **residual risk**: 非流式路径（`non_stream_parser.py:340-362`）同样缺少 `provider_request_id`，需同步修复。

---

### 03-High-Tool request query text 被三个消费者独立 back-query，无共享 source-of-truth

- **严重性**: High
- **出错语义**: LLM-safe tool request query text（工具被问了什么）是同一业务事实，但通过三条独立的 back-query 路径各自重新验证 envelope identity 并解析 EventLog payload，没有共享的 source-of-truth。
- **直接证据**:
  - `dayu/host/tool_trace.py:1283-1334` — `_tool_request_summary_from_tool_result` 回读 request EventLog，解析 payload，重建 request summary，验证 identity。
  - `dayu/host/durable/memory.py:464-503` — `_tool_result_query_text` 回读 request EventLog via `tool_call_request_atoms`，提取 `semantic_query_text`。
  - `dayu/host/memory.py:1690-1706` — `_selected_evidence_text` 使用预解析的 `evidence_query_text`。
- **错误语义第一次进入系统的位置**: accepted evidence envelope（`evidence.py`）写入时不携带 resolved query text，仅携带 `tool_call_requested_event_ref` 作为 opaque pointer。
- **当前 owner boundary 被放错在哪里**: tool query text resolution 散布在三个消费者中，每个独立实现 back-query-then-validate 模式。
- **正确 owner boundary 应在哪里**: evidence envelope 或 `TOOL_RESULT_ACCEPTED` ingest 路径应在写入时解析并携带 LLM-safe query text 作为 typed field。
- **哪些下游消费者被迫补丁**: (1) `tool_trace.py` fallback 到 `_tool_request_limited_summary`，产出降级诊断输出；(2) `durable/memory.py` fallback 到 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`；(3) `memory.py` 同样 fallback。三者独立降级。
- **最佳修复方向**: 在 accepted evidence envelope 增加 `query_text` 可选 typed field，在 ingest 时从 `semantic_query_text` 或 bounded arguments summary 填充。消费者从 envelope field 读取，不再 back-query。
- **推荐测试**: 构造 `TOOL_RESULT_ACCEPTED` 事件，其 request EventLog 使用 descriptor-backed argument storage（非 inline）。验证 tool_trace、memory projection、run_input 三者产出相同 query text。
- **residual risk**: accepted evidence envelope 已提交到 EventLog，增加字段需要 schema migration 或新 envelope version。

---

### 04-High-终端事件类型常量在 11+ 模块中独立定义，无共享枚举

- **严重性**: High
- **出错语义**: `"RUN_SUCCEEDED"`, `"RUN_FAILED"`, `"RUN_CANCELLED"`, `"RUN_LOST"` 等 Host EventLog event_type 字符串是贯穿 durable state、projection、memory、outbox、audit、tool_trace、read_model 等子系统的核心业务事实。当前该事实没有单一 source-of-truth——11 个生产模块各自定义私有常量。
- **直接证据**:
  - `_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"` 独立定义于：`dayu/host/durable/run_transition.py:102`, `dayu/host/read_api.py:90`, `dayu/host/tool_trace.py:95`, `dayu/host/memory.py:74`, `dayu/host/compact_material.py:108`, `dayu/host/outbox.py:48`, `dayu/host/engine_ingest.py:229`, `dayu/host/read_model.py:48`, `dayu/host/durable/outbox.py:48`, `dayu/host/durable/memory.py:98`。
  - 测试文件也各自补偿：`test_run_attempt_transitions.py:3316-3326` 定义私有常量集；`test_engine_ingest_mapping.py` 全文使用裸字符串字面量（20+ 处）。
  - 对比 Engine 侧有干净的 `EngineEventType(StrEnum)` 集中于 `dayu/engine/contracts/engine_events.py:37`。
- **错误语义第一次进入系统的位置**: 无法确定——每个模块都是独立引入。`run_transition.py:89-106` 首次定义最完整的 16 个常量集，但以私有模块级常量暴露。
- **当前 owner boundary 被放错在哪里**: 每个消费模块各自定义业务常量，没有公共 owner。
- **正确 owner boundary 应在哪里**: 应在 `dayu/host/` 下建立公共 `HostEventType(StrEnum)` 模块，所有子模块导入使用。
- **哪些下游消费者被迫补丁**: 11 个生产模块各自维护副本；测试文件各自补偿。
- **最佳修复方向**: 抽取公共 `HostEventType` 枚举，所有生产模块和测试统一导入。任何模块的拼写错误当前只靠对应测试的字符串断言偶然发现。
- **推荐测试**: 新增 `test_host_event_type_contract.py`，穷举枚举成员值与 `RunStatus`/`AttemptStatus` 终态映射关系。
- **residual risk**: 当前所有副本值是否全部一致需逐一对比确认；迁移期间需防止新旧路径并存导致的语义分裂。

---

### 05-High-Engine 与 Runtime 的 fallback prompt 默认值语义分裂

- **严重性**: High
- **出错语义**: Agent fallback 时追加给 LLM 的用户消息是同一业务事实，但在 Engine 和 Runtime 两层各自独立定义了**不同文本**的默认值。
- **直接证据**:
  - `dayu/runtime/config_loader.py:41-43` — `_DEFAULT_FALLBACK_PROMPT = "请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。"`
  - `dayu/engine/contracts/agent_policy.py:29-31` — `_DEFAULT_FALLBACK_PROMPT = "请基于目前已经获得的上下文直接给出最终回答，不要再调用工具。"`
  - `dayu/engine/contracts/agent_policy.py:62` — `AgentPolicy` dataclass 将 engine 版作为 field default。
- **错误语义第一次进入系统的位置**: `dayu/engine/contracts/agent_policy.py:29` 定义了独立于 runtime config 的 fallback prompt 默认值。
- **当前 owner boundary 被放错在哪里**: Engine `AgentPolicy` dataclass 自行定义 fallback prompt 默认值，与 runtime `config_loader.py` 中 `execution_profiles.json` 解析出的 fallback prompt 是两条独立真源。
- **正确 owner boundary 应在哪里**: Fallback prompt 唯一真源应为 `execution_profiles.json`（由 runtime config_loader 解析）。Engine 不应持有独立默认值。
- **哪些下游消费者被迫补丁**: Host 层在构造 `AgentPolicyDefaults` 时使用 runtime 的 `default_fallback_prompt()` 隐式覆盖 engine 默认值——但这只是隐式纠正，不是契约保证。绕过 Host 直接构造 `AgentPolicy` 的路径（测试、未来 CLI 直连 Engine）会使用 engine 版本，产生不同 LLM 行为。
- **最佳修复方向**: 从 `AgentPolicy` dataclass 移除 `fallback_prompt` 和 `continuation_prompt` 的默认值（改为必填字段），迫使所有构造路径从 runtime config 真源获取。
- **推荐测试**: 构造 `AgentPolicy` 不传 `fallback_prompt` 时应抛 TypeError。
- **residual risk**: 同一模式是否存在于 `continuation_prompt` 需进一步确认。

---

### 06-Medium-Outbox `_TERMINAL_STATUSES` 与 `_TERMINAL_EVENT_TYPES` 语义不一致，触发无意义 catch-up

- **严重性**: Medium
- **出错语义**: "Outbox 终态集合"在 `dayu/host/durable/outbox.py` 中被两组常量从不同角度定义，且范围不一致。
- **直接证据**:
  - `dayu/host/durable/outbox.py:63-69` — `_TERMINAL_STATUSES = frozenset(("succeeded", "failed", "cancelled"))`，不含 `"lost"`。
  - `dayu/host/durable/outbox.py:71-76` — `_TERMINAL_EVENT_TYPES` 包含 `RUN_LOST`。
  - `dayu/host/durable/outbox.py:737-759` — `_latest_outbox_terminal_event_sequence` 用 `_TERMINAL_EVENT_TYPES` 计算 watermark。
- **错误语义第一次进入系统的位置**: `_latest_outbox_terminal_event_sequence` 用包含 `RUN_LOST` 的 event types 计算 watermark，但 `RUN_LOST` 永远不会写入 outbox item。
- **当前 owner boundary 被放错在哪里**: watermark 计算使用了比实际 item 写入更宽的事件类型集合。
- **正确 owner boundary 应在哪里**: watermark 计算应只使用实际会写入 outbox item 的事件类型（排除 `RUN_LOST`）。
- **哪些下游消费者被迫补丁**: `read_outbox_terminal_projection_state` 报告 `LAGGED` 状态，触发 catch-up，catch-up 中 `RUN_LOST` 被 SKIPPED，checkpoint 推进后 lag 消失——产生无意义的 catch-up 循环。
- **最佳修复方向**: `_latest_outbox_terminal_event_sequence` 的 SQL WHERE 条件排除 `RUN_LOST`，或在 `_TERMINAL_EVENT_TYPES` 中移除 `RUN_LOST` 并在 filter 中单独处理。
- **推荐测试**: 构造只有 `RUN_LOST` 终态事件的 session，验证 `read_outbox_terminal_projection_state` 返回 `CAUGHT_UP` 而非 `LAGGED`。
- **residual risk**: 功能正确（catch-up 会推进 checkpoint），但每次 `RUN_LOST` 事件都触发一次无产出的 catch-up 批次。

---

### 07-Medium-Tool result status 被 tool_trace 和 read_api 独立推导，无共享 contract

- **严重性**: Medium
- **出错语义**: "tool result status"（completed/failed/cancelled）是工具执行结果的业务事实，但通过不同 heuristic chain 在两个消费者中独立推导。
- **直接证据**:
  - `dayu/host/tool_trace.py:2008-2031` — `_tool_result_status` 尝试 `resolution_kind` → `tool_fact_kind` → `raw_outcome.kind` → `raw_outcome.result.ok` 四级 fallback。
  - `dayu/host/read_api.py:1385-1399` — `_tool_outcome_activity_state` 映射 `outcome_kind` text 到 activity status。
  - `dayu/host/read_api.py:1223-1237` — `_tool_result_accepted_activity` 读取 `outcome_kind`。
- **错误语义第一次进入系统的位置**: `TOOL_RESULT_ACCEPTED` payload 无单一 canonical "result status" field。`tool_fact_kind`、`resolution_kind`、`outcome_kind` 三个字段语义重叠，各消费者各取所需。
- **当前 owner boundary 被放错在哪里**: 无 typed contract 定义 "tool result status" 含义。
- **正确 owner boundary 应在哪里**: ingest 层应写入单一 canonical `result_status` enum field 到 `TOOL_RESULT_ACCEPTED` payload。
- **哪些下游消费者被迫补丁**: `tool_trace.py:2008-2031` 实现四级 fallback chain；`read_api.py:1223-1237` 读 `outcome_kind` 可能为 `None`。
- **最佳修复方向**: 在 `TOOL_RESULT_ACCEPTED` payload 增加 canonical `result_status` enum field，ingest 时填充，消费者只读该字段。
- **推荐测试**: 构造 payload 有 `tool_fact_kind: "completed"` 但无 `resolution_kind` 和 `outcome_kind`，验证两消费者推导出相同 status。
- **residual risk**: 已有事件无新字段，需 migration 策略。

---

### 08-Medium-Memory projection 消费者变异 EventLog payload 来 hydrate final-answer fallback

- **严重性**: Medium
- **出错语义**: Memory projection 消费 `RUN_SUCCEEDED` 事件时，变异 payload 插入 synthetic `final_answer` key，使得 memory projection 看到的 payload shape 与 EventLog committed 的不同。
- **直接证据**:
  - `dayu/host/durable/memory.py:395-410` — `_memory_projection_payload_view` 对 `RUN_SUCCEEDED` 调用 `assistant_final_answer_continuity_text`（读取 terminal artifact），然后变异 payload：`merged[_PAYLOAD_FIELD_FINAL_ANSWER] = final_answer`。
  - `dayu/host/read_api.py:898-961` — `_succeeded_host_event` 独立实现 terminal artifact 读取，绕过 `_terminal_answer.py` 的 resolution order。
  - `dayu/host/run_input.py` — `assistant_final_answer_text_from_run_payload` 只读 inline field，miss artifact fallback。
- **错误语义第一次进入系统的位置**: `RUN_SUCCEEDED` 事件写入时 final answer 文本存入 artifact 而非 inline payload，投影层被迫 back-query。
- **当前 owner boundary 被放错在哪里**: durable memory projection consumer 承担了 payload 变异和 final-answer 解析职责。
- **正确 owner boundary 应在哪里**: final-answer text resolution 应在 ingest 时完成，写入 `RUN_SUCCEEDED` payload 的 `final_answer` field。所有消费者从单一 committed fact 读取。
- **哪些下游消费者被迫补丁**: (1) `durable/memory.py` 执行 payload 变异；(2) `read_api.py` 独立实现 terminal artifact 读取；(3) `run_input.py` 只读 inline field miss fallback。
- **最佳修复方向**: 在 `engine_ingest.py` `_final_answer_plan` 时解析 final-answer text，写入 payload。消除所有下游 artifact back-query。
- **推荐测试**: 构造 `RUN_SUCCEEDED` payload 有 `final_answer: null` 但 terminal artifact 有 `content: "answer"`，验证所有消费者看到 `"answer"`。
- **residual risk**: terminal artifact content 很长时会增加 inline payload size，需验证 EventLog payload size limit。

---

### 09-Medium-Import boundary 测试遗漏相对导入跨包违规

- **严重性**: Medium
- **出错语义**: 三个 import boundary 测试的 `_imported_module_names` 只捕获绝对导入（`node.level == 0`），静默跳过相对导入。Python 相对导入 `from ..engine import something` 从 `dayu/host/submodule.py` 执行时会解析为 `dayu.engine.something`，跨越 host→engine 边界，但 boundary 测试不会捕获。
- **直接证据**:
  - `tests/contracts/test_import_boundary.py:43` — `if node.module is not None and node.level == 0` 条件。
  - `tests/engine/test_import_boundary.py:63` — 相同逻辑。
  - `tests/host/test_import_boundary.py:78` — 相同逻辑。
- **错误语义第一次进入系统的位置**: `tests/contracts/test_import_boundary.py:43` 首次定义该 AST 扫描模式，后续两个文件复制。
- **当前 owner boundary 被放错在哪里**: boundary 测试假设所有跨包导入都是绝对导入。
- **正确 owner boundary 应在哪里**: `_imported_module_names` 应同时处理相对导入——对 `node.level > 0` 的 `ImportFrom` 节点，根据当前文件路径解析为绝对模块名后再检查。
- **哪些下游消费者被迫补丁**: 无——覆盖盲区，当前代码库碰巧使用绝对导入，但无机制防止未来引入违规。
- **最佳修复方向**: 扩展 AST 扫描逻辑处理相对导入。或显式声明"相对导入由 pyright 覆盖"并验证配置。
- **推荐测试**: 构造合成 `from ..engine import something` 源码片段，验证 `_imported_module_names` 能捕获。
- **residual risk**: 当前代码库是否确实没有跨包相对导入需实际扫描确认。

---

### 10-Medium-RUN_CANCELLING payload 的 `cancel_request_event_id` 仅存于 JSON，durable state 无索引，且 loose parsing 吞掉所有错误

- **严重性**: Medium
- **出错语义**: "哪个 CANCEL_REQUESTED 事件触发了当前 CANCELLING Run" 是 durable state 级业务事实，但仅存储在 `RUN_CANCELLING` EventLog row 的 `payload_json` 中，`host_runs` 表无对应列。且读取时 loose parsing 吞掉所有解析错误。
- **直接证据**:
  - `dayu/host/durable/run_transition.py:6309-6327` — `_cancel_request_event_id_from_cancelling` 用 `json.loads` + `Mapping.get` 做 loose parsing，`JSONDecodeError` / 缺 key / 类型错误全部返回 `None`。
  - `dayu/host/durable/run_transition.py:2286-2291` — watchdog 调用方必须 back-query EventLog 并解析 payload。
  - `dayu/host/engine_ingest.py:1199` — engine ingest 同样必须 back-query 并解析 payload。
  - `dayu/host/durable/run_transition.py:2809-2816` — `request_active_attempt_cancel_in_transaction` 把 `cancel_request_event_id` 写入 `RUN_CANCELLING` payload 而非 durable state 列。
- **错误语义第一次进入系统的位置**: `run_transition.py:2809-2816` — 写入 payload 而非 state 列。
- **当前 owner boundary 被放错在哪里**: `cancel_request_event_id` 真源是 EventLog payload JSON，非 durable state index。解析失败的诊断责任被放在消费方。
- **正确 owner boundary 应在哪里**: (1) `host_runs` 表应有 `cancel_request_event_id` 列，`mark_run_cancelling_row` 时写入；(2) 写入时校验 payload 包含非空字段；(3) 读取时区分缺失与损坏。
- **哪些下游消费者被迫补丁**: watchdog `active_cancel_watchdog_closeout_in_transaction` 在 `cancel_request_event_id is None` 时返回 `INVALID_STATE`，导致 CANCELLING Run 无法被收口。
- **最佳修复方向**: `host_runs` 增加 `cancel_request_event_id` 列，watchdog/engine_ingest 直接从 RunRow 读取。
- **推荐测试**: 构造 CANCELLING Run，验证 `read_run_by_id` 返回的 RunRow 携带正确 `cancel_request_event_id`。
- **residual risk**: payload JSON 格式变更会导致 watchdog 静默返回 `INVALID_STATE`，CANCELLING Run 永远无法被收口。

---

### 11-Medium-Runtime `tool_call_projection` 硬编码 Host 治理语义的 LLM-facing 默认文本

- **严重性**: Medium
- **出错语义**: Runtime 层中立模块 `tool_call_projection.py` 的 `host_cancelled_outcome()` 将 Host 治理语义（"宿主取消"、"不要把本次取消视为业务失败"）硬编码为 LLM-facing 默认消息，违反 `dayu.runtime` 层中立约束。
- **直接证据**:
  - `dayu/runtime/tool_call_projection.py:39` — `_DEFAULT_HOST_CANCELLED_MESSAGE: Final[str] = "工具调用已被宿主取消。"`
  - `dayu/runtime/tool_call_projection.py:40` — `_DEFAULT_HOST_CANCELLED_HINT: Final[str] = "不要把本次取消视为业务失败；如仍需要结果，请在后续步骤重新发起请求。"`
  - `dayu/tools/doc_tools.py:2117` 和 `dayu/tools/web_tools.py:1381` 显式传入自定义消息绕过默认值——说明默认值语义归属有误。
- **错误语义第一次进入系统的位置**: `dayu/runtime/tool_call_projection.py:39-40`。
- **当前 owner boundary 被放错在哪里**: Runtime 层持有 Host 取消语义的 LLM-facing 文本。
- **正确 owner boundary 应在哪里**: `host_cancelled_outcome()` 的 `message` 和 `hint` 应改为必填（无默认值），迫使调用方从自身层级提供 LLM-facing 文本。
- **哪些下游消费者被迫补丁**: `doc_tools.py` 和 `web_tools.py` 都显式传入自定义 message/hint 来避免 runtime 默认值。
- **最佳修复方向**: 将 `host_cancelled_outcome()` 的 `message` 和 `hint` 参数改为必填。
- **推荐测试**: 调用 `host_cancelled_outcome()` 不传 message 应抛 TypeError。
- **residual risk**: `ToolBusinessCancelled`（同文件 :98）与 `host_cancelled_outcome()` 无结构化衔接，消费者需手动拆解字段。

---

### 12-Medium-Memory snapshot 构造 4 路径分散，pending digest 哨兵无防线，测试回避等价验证

- **严重性**: Medium
- **出错语义**: `ConversationMemorySnapshotVNext` 的构造、digest 计算和 section 内容在 4 个测试文件中用 4 种不同方式构造；`"pending"` digest 哨兵从未被验证为非法持久化状态；4 条 memory 读取路径无等价验证。
- **直接证据**:
  - `tests/host/test_run_input_builder.py:4118-4123` — 使用 `snapshot_digest="pending"` 哨兵 + `replace()` 计算真实 digest。
  - `tests/host/test_compact_material.py:3047-3052` — 同样模式。
  - `tests/host/test_memory_projection.py:2689` — 通过 `project_conversation_memory_event` 走生产投影路径。
  - `tests/host/test_durable_concurrency_matrix.py:811` — 通过 `build_empty_conversation_memory_snapshot` 生产 helper。
  - 4 条 memory 读取路径：`read_memory_snapshot`、`project_conversation_memory_event`、`DurableMemorySnapshotProvider.load_memory_snapshot`、`catch_up_conversation_memory_projection`——无等价测试。
- **错误语义第一次进入系统的位置**: `test_run_input_builder.py:4013` 首次引入 `snapshot_digest="pending"` 模式。
- **当前 owner boundary 被放错在哪里**: 每个测试文件自行构造 snapshot，没有统一 fixture factory；digest 校验未拒绝 `"pending"` 等非法 sentinel。
- **正确 owner boundary 应在哪里**: `calculate_memory_snapshot_digest` 应拒绝非法 sentinel；应有共享测试 fixture factory；应有跨路径等价测试。
- **哪些下游消费者被迫补丁**: `test_compact_material.py` 从不读 durable store；`test_dispatch_scheduler.py` 只校验 checkpoint 不校验 snapshot 内容；`test_run_input_builder.py` 只校验 LLM message 渲染。
- **最佳修复方向**: (1) `calculate_memory_snapshot_digest` 拒绝 `"pending"` 等非法值；(2) 建立共享测试 fixture factory；(3) 补充跨路径等价测试。
- **推荐测试**: 断言 `calculate_memory_snapshot_digest` 对 `snapshot_digest="pending"` 产出合法 digest（验证 sentinel 不会被持久化）；新增等价测试验证 4 条读取路径返回一致内容。
- **residual risk**: `MemoryProjectionPolicy` 参数在 4 个文件中差异显著（`evidence_fact_item_cap`: 4 vs 16；`answer_anchor_char_cap`: 1024 vs 2048），同一 snapshot 可能触发不同截断路径。

---

## Open Questions

1. **RunnerContentCompletedData.finish_reason 的下游消费面**: 方案 (a) 移除该字段需确认 `ContentCompleteData.finish_reason`（`engine_events.py:140-153`）的所有消费方。当前 Host `engine_ingest.py` 中 `_ingest_validated` 不消费该字段，影响面可控，但需全面扫描。
2. **continuation_prompt 是否存在同样的双源问题**: Engine `agent_policy.py` 中 `continuation_prompt` 默认值为英文，runtime config 中为中文配置项——需确认 Host assembly 层是否总是覆盖。
3. **当前代码库是否确实没有跨包相对导入**: import boundary 测试的盲区需实际扫描确认。pyright 是否覆盖此场景需验证配置。

## Residual Risk

1. **Engine shard**: finish_reason 和 usage 两个 High finding 涉及 Runner 契约变更，需全量回归测试（流式 + 非流式 + 多 provider）。
2. **Host durable shard**: `cancel_request_event_id` 列迁移需 schema migration；当前 watchdog 的 `INVALID_STATE` 返回在 payload 损坏时会导致 CANCELLING Run 永远无法收口。
3. **Projections shard**: final-answer text resolution 的 ingest-time 移动需验证所有消费者（memory、read_api、run_input、compact_material）在 artifact-backed 和 inline-backed 两种场景下的行为一致性。
4. **Runtime shard**: fallback prompt 双源问题的修复需同时处理 `fallback_prompt` 和 `continuation_prompt`，并检查所有 `AgentPolicy` 构造路径。
5. **Tests shard**: 11 个模块的 event_type 常量值是否全部一致需逐一对比确认；`"pending"` digest 哨兵是否已在某处被持久化需扫描 durable store。
6. **未覆盖区域**: `dayu/fins/`（财报分析工具层）、`dayu/tools/`（通用工具层）、`dayu/cli/`（CLI 层）、`dayu/service/`（服务层）、`dayu/documents/`（文档处理层）不在本次 review 范围内。

---

## Summary

| 严重性 | 数量 |
|--------|------|
| High   | 5    |
| Medium | 7    |
| Low    | 0    |
| **合计** | **12** |

### Top 3 Findings

1. **[01-High]** finish_reason 双源竞争：SSE parser 产出两个冲突 finish_reason，Agent 静默选择非权威源，直接影响 durable terminal closeout 正确性。
2. **[04-High]** 终端事件类型常量在 11+ 模块中独立定义，无共享枚举——新增终态事件类型需改 11 处，遗漏任何一处导致 silent 语义分裂。
3. **[03-High]** Tool request query text 被三个消费者独立 back-query，无共享 source-of-truth，三者独立降级。

### Verdict

Host/Engine/Runtime 主线存在 5 个 High 级语义所有权错位，核心模式是：**同一业务事实无单一 source-of-truth，各消费者独立推导或 back-query，导致语义分裂风险**。最紧迫的修复是 finish_reason 双源竞争（直接影响 durable state 正确性）和终端事件类型常量抽取（消除 11 处重复定义的维护风险）。
