# Phase 13 Slice 2 Code Review

## Gate

Phase 13 Slice 2 code review。

## Review Target

- 当前分支 `feat/phase-13-audit-trace-outbox` 未提交 diff（`git diff HEAD` + untracked files）。
- Implementation artifact：`docs/reviews/phase13-slice2-implementation-codex-20260529.md`。

## Accepted Plan

`docs/host/phase13-audit-tool-trace-outbox-plan.md`

## Schema Clarification

`docs/reviews/phase13-schema-version-controller-clarification-20260529.md`

## Allowed Slice 2 Files

- `dayu/host/tool_trace.py`（untracked）
- `dayu/host/durable/tool_trace.py`（untracked）
- `dayu/host/durable/schema.py`（modified）
- `dayu/host/open_host.py`（modified）
- `tests/host/test_tool_trace_projection.py`（untracked）
- `tests/host/test_tool_trace_queries.py`（untracked）
- `tests/host/test_durable_schema.py`（modified）
- `docs/reviews/phase13-slice2-implementation-codex-20260529.md`（untracked）
- `docs/host/implementation-control.md`（仅 gate status 更新）

## Validation

- `pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_durable_schema.py -q`：25 passed in 0.37s。
- `pyright dayu/host/tool_trace.py dayu/host/durable/tool_trace.py dayu/host/durable/schema.py dayu/host/open_host.py`：0 errors, 0 warnings, 0 informations。
- `git diff --check`：passed。

## Review Checklist

### 1. Tool Trace 只消费 committed EventLog / typed projection input

**PASS。** `ToolTraceProjectionConsumer.apply_event()` 接收 `ProjectionEventView`（typed projection event view），通过 `read_event_by_id()` 读取 committed EventLog row。不读取 raw EngineEvent。`_extract_tool_trace()` 按 `event_class` 分派到 `_extract_canonical_trace` / `_extract_diagnostic_trace` / `_extract_usage_trace`，全部基于 typed payload 字段抽取，不使用任意 diagnostic payload 兜底。

Evidence：`dayu/host/tool_trace.py:285-330`（apply_event），`dayu/host/tool_trace.py:409-423`（_extract_tool_trace 分派）。

### 2. Diagnostic whitelist 足够窄，缺少 provider/tool refs 时跳过

**PASS。** `ENGINE_EVENT_DIAGNOSTIC` 仅在 `provider_request_id is not None` 时投影（`dayu/host/tool_trace.py:507-510`）。`PROVIDER_PROTOCOL_ERROR` 和 `USAGE_REPORTED` 作为命名白名单事件消费。不消费任意 diagnostic event。缺少 refs 时返回 `None` 跳过，不猜测。

Evidence：`dayu/host/tool_trace.py:497-543`（_extract_diagnostic_trace），`dayu/host/tool_trace.py:546-589`（_extract_usage_trace）。

### 3. Hot SQLite row 与 cold JSONL 只作为 diagnostic projection

**PASS。** 模块 docstring 明确声明 "Tool Trace 只用于诊断查询，不参与 Host durable truth、恢复、resume、memory 或 Run 状态迁移"（`dayu/host/tool_trace.py:1-6`）。Hot row 和 cold line 不写入 EventLog、Run/Attempt state 或 terminal transaction。

### 4. Cold writer / hot row failure 只走 projection failure

**PASS。** `_append_line()` 抛出的 `OSError` 由 `ProjectionRunner` 捕获并记录 projection failure。测试 `test_cold_writer_failure_records_projection_failure_without_checkpoint` 验证 cold JSONL 写失败后 checkpoint 保持为 0、failure row 已记录、hot row 未写入（因 failure 在同一事务中）。

Evidence：`tests/host/test_tool_trace_projection.py:280-331`。

### 5. Query helpers internal、typed、分页语义明确

**PASS。** 四个查询 helper（`read_tool_trace_by_run`、`find_tool_trace_by_tool_call_id`、`find_tool_trace_by_provider_request_id`、`find_tool_trace_by_diagnostic_ref`）均定义在 `dayu/host/durable/tool_trace.py`，未在 `dayu/host/tool_trace.py` 的 `__all__` 中导出。返回 `ToolTraceQueryPage`（frozen/slots dataclass），按 `event_sequence ASC` 分页，`limit` 有模块级上限 `TOOL_TRACE_QUERY_MAX_LIMIT=500`。

Evidence：`dayu/host/durable/tool_trace.py:260-366`（query helpers），`dayu/host/durable/tool_trace.py:112-123`（ToolTraceQueryPage）。

### 6. open_host 未新增 OpenHostOptions public fields

**PASS。** `_tool_trace_sink_options_from_open_host_options()` 从既有 `options.artifact_root` 派生默认 cold JSONL 路径，不新增 `OpenHostOptions` 字段。`_PublicHostHandle` 未新增 public 方法。Composite projection catch-up port 在 close 时顺序执行 memory + audit + tool trace。

Evidence：`dayu/host/open_host.py:869-885`（_tool_trace_sink_options_from_open_host_options），`dayu/host/open_host.py:558-570`（composite port 装配）。

### 7. Schema bump 11 → 12 fresh-schema consistent

**PASS。** `HOST_SCHEMA_VERSION = 12`（`dayu/host/durable/schema.py:26`），与 schema clarification 文档一致。`TOOL_TRACE_PROJECTION_TABLES` 和 `TOOL_TRACE_PROJECTION_DDL` 正确包含 `host_tool_trace_hot`。`bootstrap_host_durable_store()` 仅接受 version 0（fresh）或当前 version，不做兼容迁移。测试 `test_host_schema_version_is_phase13_tool_trace_version` 验证 version == 12。测试 `test_tool_trace_hot_table_and_indexes_are_created` 验证 table 和 5 个 index 均已创建。

Evidence：`dayu/host/durable/schema.py:26`，`tests/host/test_durable_schema.py:285-288`，`tests/host/test_durable_schema.py:716-739`。

### 8. 中文 docstring、严格类型、无 object/Any

**PASS。** 全部新增公共函数、类、模块均提供中文 docstring。所有 dataclass 使用 `frozen=True, slots=True`。签名无 `object`、`Any`、无类型参数。无 `getattr`/`hasattr` 逃避类型。常量使用模块级命名常量，无魔法字符串扩散。

---

## Findings

### 01-未修复-低-PROVIDER_PROTOCOL_ERROR 无 ref 时仍生成稀疏 hot row

**Evidence：** `dayu/host/tool_trace.py:497-543`。`_extract_diagnostic_trace()` 对 `PROVIDER_PROTOCOL_ERROR` 不检查 `provider_request_id` 是否存在（仅对 `ENGINE_EVENT_DIAGNOSTIC` 做此检查）。当 `PROVIDER_PROTOCOL_ERROR` 的 payload 不含 `provider_request_id`、`raw_payload_ref`、`raw_payload_digest` 时，仍返回 `_ToolTraceExtract` 全 `None` refs 的 trace，生成稀疏 hot row。

**Impact：** 稀疏 hot row 不含任何诊断引用，几乎无法用于 provider/tool 排错链查询，占用 hot projection 空间。不影响 Host truth 或 command path。

**Required change：** 可选。若 `PROVIDER_PROTOCOL_ERROR` 的 payload 预期总是携带 `provider_request_id` 或 `raw_payload_ref`，当前实现可接受。若存在无 ref 的 protocol error 事件，建议在 `_extract_diagnostic_trace` 中对 `PROVIDER_PROTOCOL_ERROR` 也检查至少一个 ref 存在，否则返回 `None` 跳过。此为低优先级改进，不阻塞 review。

### 02-未修复-低-cold line policy_decision 为原始 JSON 字符串而非 parsed object

**Evidence：** `dayu/host/tool_trace.py:692`。`_build_cold_line()` 将 `event_row.policy_decision_json`（`str | None`，原始 EventLog JSON 文本）直接作为 `_FIELD_POLICY_DECISION` 值放入 cold line fields dict。经 `canonical_json_dumps()` 序列化后，cold JSONL 中该字段为 `"policy_decision": "{\"decision\":\"accepted\"}"`（JSON 内嵌 JSON string），而非 `"policy_decision": {"decision": "accepted"}`（parsed JSON object）。

Hot row 的 `policy_decision_json` 列也是原始 JSON 文本（`str | None`），但 hot trace summary 中的 `policy_decision` 是 parsed JSON object（`dayu/host/tool_trace.py:762`）。Hot row 与 cold line 的 policy decision 存储格式一致（均为原始 JSON text），但 cold line 的 JSONL 消费者需要二次解析。

**Impact：** Cold JSONL 消费者读取 `policy_decision` 时需先 JSON parse string 再访问内部字段，与 trace summary 中的 parsed object 格式不一致。不影响 Host truth。

**Required change：** 可选。若 cold line 设计意图是保留 EventLog 原始格式，当前实现一致。若期望 cold line 字段与 trace summary 对齐，应 `json.loads(event_row.policy_decision_json)` 后再放入 fields dict。此为低优先级，不阻塞 review。

### 03-未修复-低-diagnostic event 测试覆盖可扩展

**Evidence：** `tests/host/test_tool_trace_projection.py`。当前测试覆盖 `TOOL_CALL_REQUESTED`、`TOOL_CALL_GOVERNED`、`TOOL_RESULT_ACCEPTED` 投影与 cold writer failure、rebuild、默认路径。`tests/host/test_tool_trace_queries.py` 覆盖 run/tool_call/provider/diagnostic 查询与 terminal diagnostic chain。但未覆盖：
- `ENGINE_EVENT_DIAGNOSTIC` 无 `provider_request_id` 时跳过的行为。
- `PROVIDER_PROTOCOL_ERROR` 投影。
- `USAGE_REPORTED` 投影。
- `CONTEXT_COMPACTION_*` 系列事件投影。

**Impact：** 白名单事件的投影路径部分未被测试覆盖，未来 payload contract 变更可能未被测试捕获。

**Required change：** 建议补充 `ENGINE_EVENT_DIAGNOSTIC` 无 provider_request_id 跳过测试、`PROVIDER_PROTOCOL_ERROR` 投影测试、`USAGE_REPORTED` 投影测试。此为测试完整性改进，不阻塞 review。

---

## Verdict

**PASS。** 无 blocking findings。3 个低优先级 findings 均为可选改进，不影响 Host truth、command path 或 projection 正确性。

Implementation 正确实现了 plan 中 Slice 2 的全部要求：
- Tool Trace 只消费 committed EventLog 命名白名单事件。
- Diagnostic whitelist 足够窄，ENGINE_EVENT_DIAGNOSTIC 无 provider_request_id 时跳过。
- Hot row / cold line 只作为 diagnostic projection，不成为 Host truth。
- Cold writer failure 只走 projection failure，不推进 checkpoint。
- Query helpers 内部、typed、分页语义明确。
- open_host 未新增 public fields，未改变 command path。
- Schema 11 → 12 fresh-schema consistent，测试覆盖 table/index/version。
- 中文 docstring、严格类型、无 object/Any、无魔法字符串。
