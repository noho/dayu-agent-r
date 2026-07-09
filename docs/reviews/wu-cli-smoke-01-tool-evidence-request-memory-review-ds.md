# WU-CLI-SMOKE-01 Tool Evidence Request Memory Review — AgentDS

## 审查结论：PASS_WITH_FINDINGS

修复方向与总控裁决一致。`TOOL_RESULT_ACCEPTED` evidence item 现在通过 `TOOL_CALL_REQUESTED` request atom 回读 LLM-safe query 语义，替代了原先仅依赖 raw tool outcome 的低语义 evidence。`TOOL_AWAITING` 保持不可见。所有 findings 均为 LOW（fallback 路径的过度保守匹配、缺失失败路径测试），不影响正确性。

75 passed，pyright 0 errors。

---

## 1. Design doc 复核（docs/host/design.md）

### 1.1 TOOL_AWAITING 不可见 — PASS

`docs/host/design.md:3062`：
> `TOOL_AWAITING` 是 Host / ToolRuntime 之间的等待治理事实，对模型不可见。`TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`、wait record、poll outcome、cancel / abandon lifecycle 等 Host / ToolRuntime 等待治理事实不得成为 Conversation Memory producer，也不得投影为 LLM-facing selected recent window、recent evidence、reference continuity 或 semantic memory item。

明确列出了不可进入 Memory 的事件类型和治理概念，与代码实现一致。

### 1.2 TOOL_RESULT_ACCEPTED evidence 自解释边界 — PASS

`docs/host/design.md:3075`：
> LLM-facing evidence material 必须自解释，只包含可读 tool、必要 request / query 语义、response、source text 与 prompt-local opaque label。必要 request / query 语义用于让工具结果在下一轮可解释、可复用……它不是 `TOOL_CALL_REQUESTED` 原事件、原始参数或内部治理字段的原样回放，也不得暴露 `tool_call_id`、EventLog id、payload ref、artifact ref、digest、wait id、awaiting / poll / cancel 状态或 Python 类型名。

清晰定义了 evidence 自解释的内容边界和禁止暴露的内部治理概念，与 `_accepted_evidence_readable_text` 的输出格式一致。

---

## 2. Durable memory 复核（dayu/host/durable/memory.py）

### 2.1 Request atom 回读架构 — PASS

**数据流**：
```
TOOL_RESULT_ACCEPTED event (含 envelope)
  → _memory_projection_payload_view()
    → _tool_result_memory_payload_view()
      → accepted_evidence_envelope_from_payload(event.payload)
      → event_payload_object_for_result_ref(...)           # digest-checked result payload
      → _tool_result_query_text(transaction, result_row, envelope)
        → envelope.tool_query.tool_call_requested_event_ref
        → read_event_by_id(transaction, requested_event_ref)
        → 校验 session_id / event_class / event_type
        → tool_call_request_atoms(transaction, request_row)  # digest-checked atoms
        → 校验 tool_call_id / tool_name / normalized_arguments_digest
        → atoms.semantic_query_text ?? _safe_arguments_query_text(...)
    → _MemoryProjectionPayloadView(payload, evidence_query_text)
  → MemoryProjectionEvent(..., evidence_query_text=payload_view.evidence_query_text)
  → project_conversation_memory_event()
    → _selected_evidence_text(event)
      → _accepted_evidence_readable_text(tool_name, query_text, response_text)
```

**关键设计点**：
- **不复制 query_text 进 envelope**：`dayu/host/evidence.py:3-4` 模块 docstring 明确声明"也不复制 request / query 正文"。`test_toolruntime_accept_barrier.py:224` 断言 `"query_text" not in tool_query_mapping`。
- **在 durable projection 层回读**：`_tool_result_query_text` 有 transaction 访问权，通过 `read_event_by_id` + `tool_call_request_atoms` 做 digest-checked 回读。
- **纯 memory projector 不接触 EventLog**：`MemoryProjectionEvent.evidence_query_text` 是已解析的字符串，`project_conversation_memory_event` 和 `_selected_evidence_text` 不需要 transaction 访问。

### 2.2 同源校验 — PASS

`dayu/host/durable/memory.py:509-521` — `_tool_result_query_text` 校验链：

| 校验项 | 实现 | 证据 |
|--------|------|------|
| `tool_call_requested_event_ref` 非空 | line 509-510 | `if requested_event_ref is None: return _LIMITED_TOOL_QUERY_TEXT` |
| request row 存在 | line 511-512 | `read_event_by_id(...)` returns None → limited text |
| 同 session | line 513-514 | `request_row.session_id != result_row.session_id` → limited text |
| request 是 CANONICAL_FACT | line 514 | `request_row.event_class != EventClass.CANONICAL_FACT` → limited text |
| request 是 TOOL_CALL_REQUESTED | line 515 | `request_row.event_type != _EVENT_TYPE_TOOL_CALL_REQUESTED` → limited text |
| atoms 解析成功 | line 516-518 | `tool_call_request_atoms(...)` raises → limited text |
| tool_call_id 一致 | line 519 | `atoms.tool_call_id != envelope.tool_call_id` → limited text |
| tool_name 一致 | line 520 | `atoms.tool_name != envelope.tool_name` → limited text |
| arguments digest 一致 | line 521-522 | `atoms.normalized_arguments_digest != envelope.tool_query.normalized_arguments_digest` → limited text |

**关于 attempt/execution/run 校验**：`tool_call_id` + `normalized_arguments_digest` + `session_id` 的组合提供了充分的请求同源性保证。同一 tool_call_id 在不同 attempt 中不会重现（tool_call_id 全局唯一），而 arguments_digest 和 session 校验防止跨 session 或伪冒引用。不强制校验 `attempt_id` / `execution_id` / `run_id` 不会引入不正确性——即使 request 来自不同 attempt，相同 tool_call_id + 相同 arguments 的 semantic query 语义等价。

### 2.3 Fallback 安全性 — PASS_WITH_FINDING

**双层防护**：
1. `redact_sensitive_json_fields(arguments_json)` — 脱敏 `api_key`、`password`、`secret`、`token` 字段值为 `<redacted>`
2. `_json_value_contains_unsafe_text(redacted_mapping)` — 检查脱敏后的 JSON 是否仍含内部引用

**第二层检查覆盖**：
- 敏感字段名残留（脱敏后 key 仍为 `api_key`）→ 被 `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 中的 `"api_key"` 捕获
- 本地路径（`/Users/...`, `~/...`, `C:\...`）→ `_LOCAL_PATH_PREFIXES` / `_WINDOWS_PATH_MARKER`
- 内部 ref 形态（`sha256:`, `event-`, `tool-call`, `wait-`, `payload`, `artifact`）
- 治理状态（`awaiting`, `abandoned`, `poll`, `cancel`）
- 长度上限：2048 bytes → 超过则返回 limited text

**测试覆盖**：
- `test_projection_consumer_uses_limited_query_for_unsafe_argument_fallback` — api_key + 本地路径 → limited text，secret 和 path 不泄露
- `test_projection_consumer_uses_bounded_argument_summary_without_query` — 安全参数 `{"ticker":"MSFT"}` → `工具参数摘要：{"arguments":{"ticker":"MSFT"}}`

#### Finding F1 (LOW) — `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 过度匹配合法业务字段

- **文件/行号**：`dayu/host/durable/memory.py:103-115`
- **证据**：`"token"` fragment 匹配 `token_name`、`token_type`、`token_id`、`tokenomics`、`erc20_token` 等加密/权益工具分析常见参数名。`"payload"` fragment 匹配 `payload_weight` 等字段。`"cancel"` fragment 匹配 `cancellation_date`、`cancellation_policy` 等字段。
- **影响**：仅影响 `semantic_query_text is None` 的 fallback 路径；过度匹配导致本可安全展开的参数被降级为 `"查询语义不可用；参数未安全展开。"`。对财报分析场景实际影响取决于工具是否提供 `semantic_query_text`。
- **建议**：可在代码注释中说明保守策略的取舍。若未来发现实际工具频繁落入此 fallback，可考虑将 `"token"` 限制为 `"api_token"` / `"access_token"` / `"bearer_token"` 等比 `"token"` 更精确的模式。

#### Finding F2 (LOW) — 缺少 request atom 读取失败路径的显式测试

- **文件/行号**：`dayu/host/durable/memory.py:508-524`（`_tool_result_query_text` 各 fail-early 分支）
- **证据**：当前测试覆盖 happy path（`test_projection_consumer_pairs_tool_result_with_requested_query`）和 unsafe fallback path。未覆盖 `requested_event_ref is None`、`read_event_by_id` 返回 None、session 不匹配、event type 不匹配、tool_call_id 不匹配、arguments digest 不匹配的 fail-safe 分支。
- **影响**：所有失败分支返回 `_LIMITED_TOOL_QUERY_TEXT`（安全兜底），即使未测试也不会泄漏。但覆盖率报告会显示 miss。
- **建议**：增加一个参数化测试覆盖至少 `requested_event_ref is None` 和 `read_event_by_id returns None` 两个路径。

---

## 3. LLM-facing 文本合规性复核

### 3.1 输出格式 — PASS

`dayu/host/memory.py:1696-1726` — `_accepted_evidence_readable_text`：
```
工具：{tool_name}
查询：{query_text}
结果：{response_text}
```

- `tool_name`：来自 schema 的 LLM-facing 工具名（如 `list_documents`），LLM 已在 tool call 上下文中见过此名称。
- `query_text`：来自 `atoms.semantic_query_text` 或 `_safe_arguments_query_text` 的 LLM-safe 业务可读文本。
- `response_text`：来自 `accepted_tool_raw_outcome_text_from_payload` 的 digest-checked tool outcome。

验证（Python 脚本扫描）：
- "工具参数摘要：" — 无内部术语泄漏
- "查询语义不可用；参数未安全展开。" — 无内部术语泄漏
- 完整 evidence 文本 — 不含 `event-`、`tool-call`、`sha256:`、`wait`、`awaiting`、`cancel`

### 3.2 tool_name 是否需要 display name — PASS

当前使用 schema `tool_name`（如 `list_documents`、`search_document`）。AGENTS.md LLM-facing 文本约束要求"不用代码类型名、内部模块名、历史迁移名或 Host 实现术语要求模型自行理解"。tool_name 是 LLM 已使用的工具名，不是内部模块名或实现术语。模型已知 `list_documents` 的含义。不需要 display name 映射。

### 3.3 evidence.py 模块 docstring — PASS

`dayu/host/evidence.py:3-4`：
> 信封描述 Host 可校验的事件、工具调用、digest 与不透明 refs；它不解析财报业务 source / locator 语义，也不复制 request / query 正文。

明确声明 envelope 不携带 query 正文。

---

## 4. 测试覆盖复核

### 4.1 覆盖矩阵

| 场景 | 测试 | 文件/行号 |
|------|------|-----------|
| ambiguous raw outcome → 带 query 语义 | `test_accepted_tool_evidence_disambiguates_raw_result_with_request_query` | `test_memory_projection.py:1087-1145` |
| request atom 回读（完整 durable store） | `test_projection_consumer_pairs_tool_result_with_requested_query` | `test_memory_projection.py:1634-1704` |
| 无 semantic_query_text → 安全参数摘要 | `test_projection_consumer_uses_bounded_argument_summary_without_query` | `test_memory_projection.py:1707-1763` |
| 无 semantic_query_text → unsafe 参数 fallback | `test_projection_consumer_uses_limited_query_for_unsafe_argument_fallback` | `test_memory_projection.py:1766-1835` |
| evidence 文本不含内部 ref | `test_accepted_tool_evidence_includes_query_and_raw_outcome_without_refs` | `test_memory_projection.py:1018-1084` |
| TOOL_AWAITING 不进入 memory filter | `test_conversation_memory_consumer_uses_shared_projection_event_filter` | `test_memory_projection.py:1836-1841` |
| TOOL_AWAITING 不产生 LLM-facing memory | `test_tool_awaiting_does_not_project_llm_facing_memory` | `test_memory_projection.py:360-408` |
| 有无 TOOL_AWAITING 的 memory 语义等价 | `test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics` | `test_memory_projection.py:411-472` |
| envelope 不携带 query_text | `test_tool_result_accepted_payload_carries_accepted_evidence_envelope` | `test_toolruntime_accept_barrier.py:224` |
| result preview 被拒绝 | `test_accepted_tool_evidence_rejects_result_preview` | `test_memory_projection.py:1206-1239` |

### 4.2 等价性测试保留 — PASS

`test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics`（上一轮 review 新增）未受本次变更影响，继续通过。验证有无 TOOL_AWAITING 的 memory role/text 视图完全一致。

---

## 5. README 复核

### 5.1 `dayu/host/README.md` — PASS

`dayu/host/README.md:659` — TOOL_RESULT_ACCEPTED 描述扩展为自解释 evidence，准确描述"从 request atom 回读 LLM-safe request/query 文本"和禁止暴露的概念列表。与代码实现一致。

### 5.2 `tests/README.md` — PASS

`tests/README.md:201` — 新增"自解释工具证据"表述和 request atom 回读语义。准确对应新增测试覆盖范围。

---

## 6. 架构约束复核

| 约束 | 状态 | 证据 |
|------|------|------|
| `dayu.runtime` 不 import 上层 | PASS | `dayu/runtime/json_redaction.py` 只依赖 `dayu.contracts.json_value` |
| 反向依赖 | PASS | evidence.py → durable/memory.py 方向正确 |
| 不复制 query_text 进 envelope | PASS | `test_toolruntime_accept_barrier.py:224` |
| digest-checked payload | PASS | `event_payload_object_for_result_ref` + `tool_call_request_atoms` |
| 禁止魔法字符串 | PASS | 全部常量均定义为模块级 `_CONSTANT` |

---

## 附录 A：findings 汇总

| # | 严重性 | 文件 | 描述 |
|---|--------|------|------|
| F1 | LOW | `dayu/host/durable/memory.py:103-115` | `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 中 `"token"`/`"payload"`/`"cancel"` 对合法业务字段过度匹配 |
| F2 | LOW | `dayu/host/durable/memory.py:508-524` | 缺少 request atom 读取失败路径（None ref、missing row、validation mismatch）显式测试 |

## 附录 B：与上轮 DS review 的关联

本次变更为 Issue #176 的独立修复，与上轮 `wu-cli-smoke-01-cancel-retry-regression` 共享 TOOL_AWAITING 不可见的基础设施（`_EVENT_TYPE_FILTER` 不含 TOOL_AWAITING、`project_conversation_memory_event` 不处理 TOOL_AWAITING），未破坏上轮修复。等价性测试继续通过。
