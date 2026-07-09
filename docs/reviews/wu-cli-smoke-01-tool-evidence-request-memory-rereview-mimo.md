# Re-review: issue-176 TOOL_RESULT_ACCEPTED evidence request memory

**Reviewer**: MiMo
**Date**: 2026-07-09
**Scope**: 当前未提交 diff 中与 TOOL_RESULT_ACCEPTED evidence request memory 相关的变更
**Design source**: `docs/host/design.md`

---

## Completion Report: PASS

全部验证通过，无 findings。

---

## Review Checklist

### 1. docs/host/design.md — TOOL_AWAITING 不可见性声明

**结论: PASS**

`docs/host/design.md:3062` 新增：

> `TOOL_AWAITING` 是 Host / ToolRuntime 之间的等待治理事实，对模型不可见。`TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`、wait record、poll outcome、cancel / abandon lifecycle 等 Host / ToolRuntime 等待治理事实不得成为 Conversation Memory producer，也不得投影为 LLM-facing selected recent window、recent evidence、reference continuity 或 semantic memory item。

声明完整覆盖了 design review checklist 要求的所有 waiting lifecycle 事件类型。`docs/host/design.md:3074` 同步更新了 Evidence / Fact Memory 节，明确了 LLM-facing evidence 必须自解释、request/query 语义不得暴露内部治理字段。

### 2. dayu/host/durable/memory.py — envelope 回读 request atom

**结论: PASS**

- `_tool_result_memory_payload_view` (`memory.py:435-483`) 正确通过 `accepted_evidence_envelope_from_payload` 读取 envelope，然后用 `_tool_result_query_text` 回读对应 request atom。
- envelope 只提供 `tool_call_requested_event_ref`（不透明引用），不复制 query 正文。
- `evidence_query_text` 在 `_MemoryProjectionPayloadView` 中携带，最终传入 `MemoryProjectionEvent`，由 `memory.py:_selected_evidence_text` 消费。

### 3. request_row / result_row 同源校验

**结论: PASS**

`_tool_result_query_text` (`memory.py:486-525`) 的校验链完整：

| 校验步骤 | 行号 | 失败行为 |
|---|---|---|
| `requested_event_ref is None` | 500-501 | → `_LIMITED_TOOL_QUERY_TEXT` |
| `request_row is None` | 503-504 | → `_LIMITED_TOOL_QUERY_TEXT` |
| `session_id != result_row.session_id` | 505-506 | → `_LIMITED_TOOL_QUERY_TEXT` |
| `!_same_run_attempt_execution(request_row, result_row)` | 507 | → `_LIMITED_TOOL_QUERY_TEXT` |
| `event_class != CANONICAL_FACT` | 508 | → `_LIMITED_TOOL_QUERY_TEXT` |
| `event_type != TOOL_CALL_REQUESTED` | 509 | → `_LIMITED_TOOL_QUERY_TEXT` |
| `tool_call_request_atoms` 抛 HostDurableError | 514-515 | → `_LIMITED_TOOL_QUERY_TEXT` |
| `tool_call_id / tool_name / arguments_digest` 不匹配 | 517-522 | → `_LIMITED_TOOL_QUERY_TEXT` |

`_same_run_attempt_execution` (`memory.py:528-540`) 校验 `run_id`、`attempt_id`、`execution_id` 三字段全部一致。

### 4. fail-safe 不泄露内部治理信息

**结论: PASS**

- `_LIMITED_TOOL_QUERY_TEXT = "查询语义不可用；参数未安全展开。"` 是低信号文本，不含任何内部标识。
- `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` (`memory.py:107-123`) 过滤 `api_key`、`authorization`、`password`、`secret`、`token`、`sha256:`、`payload`、`artifact`、`event-`、`tool-call`、`wait-`、`awaiting`、`abandoned`、`poll`、`cancel`。
- `_text_contains_unsafe_reference` (`memory.py:582-594`) 额外过滤本地路径前缀。
- `_safe_arguments_query_text` (`memory.py:543-559`) 先 `redact_sensitive_json_fields`，再检查 unsafe text，再限 2048 bytes。
- evidence.py docstring (`evidence.py:4-5`) 明确："也不复制 request / query 正文"。
- test_toolruntime_accept_barrier.py:224 确认 `tool_query_mapping` 不含 `query_text` key。

### 5. 测试覆盖

**结论: PASS**

`tests/host/test_memory_projection.py` 新增测试：

| 测试函数 | 覆盖路径 |
|---|---|
| `test_accepted_tool_evidence_includes_query_and_raw_outcome_without_refs` | 正常路径：envelope + evidence_query_text → 自解释文本 |
| `test_accepted_tool_evidence_disambiguates_raw_result_with_request_query` | raw outcome 含义不完整时，query 语义提供消歧 |
| `test_projection_consumer_pairs_tool_result_with_requested_query` | 集成路径：durable store → projection runner → snapshot |
| `test_projection_consumer_uses_bounded_argument_summary_without_query` | 缺 semantic query → 安全参数摘要 |
| `test_projection_consumer_fails_safe_on_request_result_execution_mismatch` | parametrized: run/attempt/execution 错配 × 3 |
| `test_projection_consumer_fails_safe_when_requested_event_ref_missing` | envelope 缺 request ref |
| `test_projection_consumer_uses_limited_query_for_unsafe_argument_fallback` | unsafe 参数（api_key、本地路径）|

`tests/host/test_toolruntime_accept_barrier.py` 新增断言：

| 行号 | 断言 |
|---|---|
| 203-207 | envelope JSON 包含 `tool_query` mapping |
| 224 | `tool_query_mapping` 不含 `query_text` key |

全部 79 tests passed，pyright 0 errors。

---

## Findings

无。

---

## Verification

- `pytest tests/host/test_memory_projection.py tests/host/test_toolruntime_accept_barrier.py -q` → 79 passed
- `pyright dayu/host/durable/memory.py dayu/host/memory.py dayu/host/evidence.py` → 0 errors, 0 warnings
