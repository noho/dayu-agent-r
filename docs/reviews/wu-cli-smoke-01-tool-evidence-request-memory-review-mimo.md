# Issue #176 TOOL_RESULT_ACCEPTED Evidence Request Memory — Code Review

- **Reviewer**: AgentMiMo
- **Date**: 2026-07-08
- **Branch**: `phase/host-issues-control`
- **Scope**: 8 files changed, +696 / -33
- **Verdict**: **PASS_WITH_FINDINGS**

---

## 维度 1：design.md 是否正确表达 TOOL_AWAITING 不可见与 evidence 自解释边界

### 结论：PASS

**证据**：

1. `docs/host/design.md` 新增段落：
   > `TOOL_AWAITING` 是 Host / ToolRuntime 之间的等待治理事实，对模型不可见。`TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`、wait record、poll outcome、cancel / abandon lifecycle 等 Host / ToolRuntime 等待治理事实不得成为 Conversation Memory producer，也不得投影为 LLM-facing selected recent window、recent evidence、reference continuity 或 semantic memory item。

2. `docs/host/design.md` 修改 Evidence / Fact Memory 段落：
   > LLM-facing evidence material 必须自解释，只包含可读 tool、必要 request / query 语义、response、source text 与 prompt-local opaque label。必要 request / query 语义用于让工具结果在下一轮可解释、可复用……它不是 `TOOL_CALL_REQUESTED` 原事件、原始参数或内部治理字段的原样回放，也不得暴露 `tool_call_id`、EventLog id、payload ref、artifact ref、digest、wait id、awaiting / poll / cancel 状态或 Python 类型名。

**评估**：design.md 正确表达了两个核心约束：(1) TOOL_AWAITING 对模型不可见；(2) evidence 必须自解释但不暴露内部治理字段。

---

## 维度 2：是否通过 request atom 回读，而非复制 query 正文进 envelope

### 结论：PASS

**证据**：

1. `dayu/host/evidence.py:98-108` — `AcceptedEvidenceToolQuery` 只有三个字段：
   - `tool_call_requested_event_ref: str | None`（引用，非正文）
   - `normalized_arguments_digest: str`（digest，非正文）
   - `semantic_input_digest: str`（digest，非正文）

   无 `query_text`、`arguments_text` 或任何正文字段。

2. `tests/host/test_toolruntime_accept_barrier.py:224` — 断言 `"query_text" not in tool_query_mapping`，确认 envelope 不携带 query 正文。

3. `dayu/host/durable/memory.py:486-524` — `_tool_result_query_text` 在投影时通过 `read_event_by_id(transaction, requested_event_ref)` 回读 TOOL_CALL_REQUESTED row，再调用 `tool_call_request_atoms(transaction, request_row)` 读取 `semantic_query_text` 或 `arguments_json`。query 语义在投影时从 request atom 实时读取，不在 envelope 中复制。

**数据流**：
```
TOOL_RESULT_ACCEPTED envelope
  → tool_call_requested_event_ref (引用)
  → read_event_by_id(transaction, ref) (回读 request row)
  → tool_call_request_atoms(transaction, row) (解析 request atom)
  → atoms.semantic_query_text 或 _safe_arguments_query_text(atoms.arguments_json)
```

---

## 维度 3：同源校验是否充分

### 结论：PASS_WITH_FINDINGS

**当前校验** (`dayu/host/durable/memory.py:505-521`)：

| 校验项 | 是否校验 | 证据 |
|--------|---------|------|
| session_id | ✅ | line 506: `request_row.session_id != result_row.session_id` |
| event_class | ✅ | line 507: `request_row.event_class != EventClass.CANONICAL_FACT` |
| event_type | ✅ | line 508: `request_row.event_type != _EVENT_TYPE_TOOL_CALL_REQUESTED` |
| tool_call_id | ✅ | line 516: `atoms.tool_call_id != envelope.tool_call_id` |
| tool_name | ✅ | line 517: `atoms.tool_name != envelope.tool_name` |
| normalized_arguments_digest | ✅ | line 518-519: `atoms.normalized_arguments_digest != envelope.tool_query.normalized_arguments_digest` |
| attempt_id | ❌ | — |
| execution_id | ❌ | — |
| run_id | ❌ | — |

#### Finding F1: 同源校验缺少 attempt_id / run_id

- **严重性**: LOW
- **文件**: `dayu/host/durable/memory.py:505-521`
- **证据**: `_tool_result_query_text` 校验了 session_id、event_class、event_type、tool_call_id、tool_name、normalized_arguments_digest，但未校验 attempt_id 或 run_id。
- **风险分析**: tool_call_id 由 Engine 生成，在同一 session 内唯一。TOOL_CALL_REQUESTED 和 TOOL_RESULT_ACCEPTED 在同一 attempt 内写入，tool_call_id + tool_name + normalized_arguments_digest 三元组已提供强绑定。即使同一 session 不同 run 中出现相同 tool_call_id（正常操作中不会发生），normalized_arguments_digest 也会因参数不同而不同。实际误匹配概率极低。
- **建议**: 当前校验在实践中充分。如需更严格，可补充 `request_row.run_id != result_row.run_id` 检查，但非必须。

---

## 维度 4：fallback 参数摘要是否泄露敏感信息

### 结论：PASS

**安全防线层次**：

1. **第一层：`redact_sensitive_json_fields`** (`dayu/runtime/json_redaction.py`) — 对 key 命中 `api_key`、`password`、`secret`、`token` 的字段值替换为 `<redacted>`。

2. **第二层：`_json_value_contains_unsafe_text`** (`dayu/host/durable/memory.py:546-563`) — 递归检查 key 和 value，命中 `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 或本地路径时返回 `True`，触发 fallback 到 `_LIMITED_TOOL_QUERY_TEXT`。

3. **第三层：`_text_contains_unsafe_reference`** (`dayu/host/durable/memory.py:566-578`) — 检查文本是否以 `/` 或 `~/` 开头（本地路径）、是否含 `:\\`（Windows 路径）、是否含任何 unsafe fragment。

**`_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 覆盖**：

| 类别 | fragments | 评估 |
|------|-----------|------|
| 敏感凭据 | `api_key`, `authorization`, `password`, `secret`, `token` | ✅ 覆盖常见凭据 key |
| 内部 digest | `sha256:` | ✅ |
| 内部治理 | `payload`, `artifact`, `event-`, `tool-call`, `wait-`, `awaiting`, `abandoned`, `poll`, `cancel` | ✅ 覆盖 Host 内部引用形态 |
| 本地路径 | `/`, `~/`, `:\\` | ✅ 覆盖 Unix/Windows 路径 |

**大小限制**：`_MAX_ARGUMENT_QUERY_TEXT_BYTES = 2048`，超限回退到低信号文本。

**评估**：安全防线覆盖合理。`redact_sensitive_json_fields` 处理 key 级脱敏，`_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 处理 value 级和 key 级的内部引用检测。两层互补，无明显泄漏路径。

---

## 维度 5：LLM-facing 文本是否符合 AGENTS 约束

### 结论：PASS

**当前文本格式** (`dayu/host/memory.py:1724-1730`)：

```
工具：{tool_name}
查询：{query_text}
结果：{response_text}
```

**tool_name 使用 schema name**：`envelope.tool_name` 是工具 schema name（如 `list_documents`、`start_fins_download`），不是 display name。

**评估**：
- AGENTS.md 禁止使用"内部模块名、历史迁移名"，但允许 tool schema name。工具 schema name 是 LLM 调用工具时使用的标识符，模型已知此名称。
- display name 是 UI 层概念，不同 UI 可能有不同 display name，不适合作为 LLM-facing 证据的稳定标识。
- `查询：{query_text}` 来自 `atoms.semantic_query_text`（业务可读语义）或 `_safe_arguments_query_text`（安全参数摘要），不含内部治理字段。
- `结果：{response_text}` 来自 `raw_tool_outcome`，是工具原始响应。

**无违反 AGENTS.md LLM-facing 文本约束的情况**。

---

## 维度 6：测试覆盖

### 结论：PASS

| 场景 | 测试 | 文件:行号 |
|------|------|----------|
| ambiguous result 带 query 语义 | `test_accepted_tool_evidence_disambiguates_raw_result_with_request_query` | test_memory_projection.py:1092 |
| request atom 回读（durable store） | `test_projection_consumer_pairs_tool_result_with_requested_query` | test_memory_projection.py:1631 |
| unsafe fallback | `test_projection_consumer_uses_limited_query_for_unsafe_argument_fallback` | test_memory_projection.py:1767 |
| TOOL_AWAITING 不进 memory | `test_tool_awaiting_does_not_project_llm_facing_memory` | test_memory_projection.py:360 |
| 有无 TOOL_AWAITING 等价性 | `test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics` | test_memory_projection.py:411 |
| envelope 不携带 query_text | `test_tool_result_accepted_payload_carries_accepted_evidence_envelope` | test_toolruntime_accept_barrier.py:224 |
| semantic query 有值时优先使用 | `test_projection_consumer_pairs_tool_result_with_requested_query` | test_memory_projection.py:1631 |
| semantic query 无值时 fallback 到参数摘要 | `test_projection_consumer_uses_bounded_argument_summary_without_query` | test_memory_projection.py:1703 |
| raw outcome + query 格式正确 | `test_accepted_tool_evidence_includes_query_and_raw_outcome_without_refs` | test_memory_projection.py:1015 |
| forbidden fragments 不出现 | 多个测试均有 `forbidden_fragments` 断言 | — |

**测试质量**：
- `test_projection_consumer_pairs_tool_result_with_requested_query` 使用真实 durable store + `ProjectionRunner`，验证端到端 request atom 回读路径。
- `test_projection_consumer_uses_limited_query_for_unsafe_argument_fallback` 验证 `api_key`、本地路径均不泄漏。
- `test_accepted_tool_evidence_disambiguates_raw_result_with_request_query` 验证 `{"total": 0, "documents": []}` 这类含义不完整的 raw outcome 在有 query 语义时变得可解释。

---

## Findings 汇总

| ID | 严重性 | 维度 | 文件:行号 | 描述 |
|----|--------|------|----------|------|
| F1 | LOW | 同源校验 | `dayu/host/durable/memory.py:505-521` | `_tool_result_query_text` 未校验 attempt_id / run_id；tool_call_id + tool_name + normalized_arguments_digest 三元组已提供强绑定，实际误匹配概率极低 |

---

## 结论

**PASS_WITH_FINDINGS**

实现正确解决了 Issue #176 的核心需求：

1. **TOOL_AWAITING 对模型不可见** — 从 design.md、durable filter、memory projection 常量/分支/helper 四个层面彻底确认。
2. **evidence 自解释** — `TOOL_RESULT_ACCEPTED` evidence item 通过 envelope 中的 `tool_call_requested_event_ref` 引用回读 TOOL_CALL_REQUESTED request atom，取得 `semantic_query_text` 或安全参数摘要，与 `raw_tool_outcome` 合并为自解释文本。
3. **不复制 query 正文进 envelope** — envelope 只携带引用和 digest，query 语义在投影时实时读取。
4. **安全 fallback** — 两层防线（redact + unsafe fragments）覆盖敏感凭据、内部引用、本地路径；大小限制 2048 bytes。
5. **LLM-facing 文本合规** — 使用 tool schema name（模型已知标识符），不含内部治理字段。

一个 LOW 级 finding（同源校验缺 attempt/run），不影响正确性。
