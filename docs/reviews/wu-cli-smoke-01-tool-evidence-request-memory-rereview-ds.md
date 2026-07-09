# Issue #176 TOOL_RESULT_ACCEPTED Evidence Request Memory — AgentDS 针对性 Re-Review

- **Reviewer**: AgentDS (re-review)
- **Date**: 2026-07-09
- **Branch**: `phase/host-issues-control`
- **Scope**: 8 files changed（`dayu/host/durable/memory.py`, `dayu/host/evidence.py`, `dayu/host/memory.py`, `docs/host/design.md`, `tests/host/test_memory_projection.py`, `tests/host/test_toolruntime_accept_barrier.py`, `dayu/host/README.md`, `tests/README.md`）
- **Design doc 真源**: `docs/host/design.md`
- **总控文档**: `docs/host/issues-implementation-control.md`
- **验证结果**: 79 passed, pyright 0 errors

---

## 审查结论：PASS_WITH_FINDINGS

上一轮 MiMo/DS review 后的补修（run/attempt/execution 同源校验 + 两个新测试）正确实施，未引入回归。所有 findings 均为 LOW，不影响正确性。

前一轮 findings 状态：
- MiMo F1 (LOW, 同源校验缺 attempt/run) → **已修复**，现通过 `_same_run_attempt_execution` 全量校验 run/attempt/execution。
- DS F1 (LOW, `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 过度匹配) → **未修复**，继续站立。
- DS F2 (LOW, 缺少失败路径测试) → **部分修复**：新增 `requested_event_ref=None` 与 execution mismatch 测试，但 `read_event_by_id returns None` 及其他 6 个 fail-early 分支仍未覆盖。

---

## 1. 重点复核：run/attempt/execution 同源校验

### 1.1 实现复核 — PASS

`dayu/host/durable/memory.py:505-511` — `_tool_result_query_text` 校验链完整序列：

```python
if (
    request_row.session_id != result_row.session_id          # 同 session
    or not _same_run_attempt_execution(request_row, result_row)  # 同 run/attempt/execution
    or request_row.event_class != EventClass.CANONICAL_FACT     # 是 canonical fact
    or request_row.event_type != _EVENT_TYPE_TOOL_CALL_REQUESTED # 是 TOOL_CALL_REQUESTED
):
    return _LIMITED_TOOL_QUERY_TEXT
```

`dayu/host/durable/memory.py:528-540` — `_same_run_attempt_execution` 实现：

```python
def _same_run_attempt_execution(left: EventLogRow, right: EventLogRow) -> bool:
    return (
        left.run_id == right.run_id
        and left.attempt_id == right.attempt_id
        and left.execution_id == right.execution_id
    )
```

**评估**：
- 全量校验 6 个维度：session_id、run_id、attempt_id、execution_id、event_class、event_type，覆盖 request/result 行可能错配的全部来源。
- `_same_run_attempt_execution` 是纯等值比较，双方均为 None 时通过（测试夹具兼容），一方 None 另一方非 None 时拒绝（生产安全）。
- `result_row` 从 `_event_row_from_projection_event(event)` 构造，其 run_id/attempt_id/execution_id 来自 ProjectionEventView（即 EventLog 投影），与 `request_row`（通过 `read_event_by_id` 从 EventLog 直接读取）的字段来源一致——两者均从同一 EventLog 表读取，比较语义正确。
- 所有不匹配路径均返回 `_LIMITED_TOOL_QUERY_TEXT`（`"查询语义不可用；参数未安全展开。"`），不回退到 request query 读取。fail-safe 正确。

### 1.2 参数化测试覆盖 — PASS

`tests/host/test_memory_projection.py:1783-1844` — `test_projection_consumer_fails_safe_on_request_result_execution_mismatch`：

| 参数 | request_run_id | request_attempt_id | request_execution_id | 断言 |
|------|---------------|-------------------|---------------------|------|
| variant 1 | `"run-other"` | `_ATTEMPT_ID` | `_EXECUTION_ID` | limited text, query_text 不泄露 |
| variant 2 | `_RUN_ID` | `"attempt-other"` | `_EXECUTION_ID` | limited text, query_text 不泄露 |
| variant 3 | `_RUN_ID` | `_ATTEMPT_ID` | `"execution-other"` | limited text, query_text 不泄露 |

三个变体覆盖了 run/attempt/execution 各自独立错配的场景。每个测试均验证：
- `"查询语义不可用；参数未安全展开。"` 出现在 memory text 中
- 原始 `query_text` 不出现在 memory text 中
- request/result event id、tool call id 不出现在 memory text 中
- 错配的 `"run-other"` / `"attempt-other"` / `"execution-other"` 不出现在 memory text 中
- raw tool outcome 仍然正常投影（如 `'"total":0'`）

### 1.3 `requested_event_ref=None` 测试覆盖 — PASS

`tests/host/test_memory_projection.py:1847-1903` — `test_projection_consumer_fails_safe_when_requested_event_ref_missing`：

- result envelope 的 `tool_call_requested_event_ref=None`
- 事务中同时存在对应的 TOOL_CALL_REQUESTED row（未被引用）
- 断言：limited text 出现；request 中存在的 query_text 不泄露；event id / tool call id 不泄露
- 覆盖 `_tool_result_query_text` 的第一条 fail-early：`if requested_event_ref is None: return _LIMITED_TOOL_QUERY_TEXT`

---

## 2. 设计文档复核

### 2.1 TOOL_AWAITING 不可见 — PASS（无变化）

`docs/host/design.md:3062` 段落自上一轮 review 后未变化，持续正确。

### 2.2 Evidence 自解释边界 — PASS（无变化）

`docs/host/design.md:3075` 段落自上一轮 review 后未变化，持续正确。

### 2.3 与补修的一致性 — PASS

设计文档中 Evidence / Fact Memory 描述与补修代码一致：
- "不得暴露 `tool_call_id`、EventLog id、payload ref、artifact ref、digest、wait id、awaiting / poll / cancel 状态" — 所有 fail-safe 路径均返回 `_LIMITED_TOOL_QUERY_TEXT`，不含任何此类术语。
- "必要 request / query 语义用于让工具结果在下一轮可解释、可复用" — happy path 通过 `atoms.semantic_query_text` 提供业务可读语义；fallback 通过 `_safe_arguments_query_text` 提供有界安全参数摘要。

---

## 3. LLM-facing 文本合规性复核

### 3.1 三条路径的 LLM-facing 输出 — PASS

| 路径 | query_text 来源 | 示例 LLM-facing 文本 |
|------|----------------|---------------------|
| Happy path | `atoms.semantic_query_text` | `查询：读取 ticker=COIN 的财报列表` |
| 安全参数摘要 | `工具参数摘要：{"arguments":{"ticker":"MSFT"}}` | `查询：工具参数摘要：{"arguments":{"ticker":"MSFT"}}` |
| 低信号 fallback | `"查询语义不可用；参数未安全展开。"` | `查询：查询语义不可用；参数未安全展开。` |

三条路径均不含：event id、tool_call_id、payload ref、digest、sha256:、wait/awaiting/poll/cancel/abandoned。

### 3.2 禁止暴露项全量扫描 — PASS

对全部三条路径的 LLM-facing 文本做正则/子串扫描，确认以下禁止项均不出现：

- `event-` / `tool-call` → `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 阻止
- `sha256:` → `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 阻止
- `payload` / `artifact` → `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 阻止
- `wait-` / `awaiting` / `abandoned` / `poll` / `cancel` → `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 阻止
- `api_key` / `authorization` / `password` / `secret` / `token` → `redact_sensitive_json_fields` + `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 双层阻止
- 本地路径（`/...` / `~/...` / `C:\...`） → `_LOCAL_PATH_PREFIXES` / `_WINDOWS_PATH_MARKER` 阻止

---

## 4. Evidence envelope 完整性复核

### 4.1 Envelope 不携带 query 正文 — PASS（无变化）

`dayu/host/evidence.py:98-108` — `AcceptedEvidenceToolQuery` 字段集未变化：
- `tool_call_requested_event_ref: str | None`
- `normalized_arguments_digest: str`
- `semantic_input_digest: str`

`tests/host/test_toolruntime_accept_barrier.py:224` — `assert "query_text" not in tool_query_mapping` 持续通过。

### 4.2 Evidence envelope 回读数据流 — PASS（无变化）

```
TOOL_RESULT_ACCEPTED event
  → _tool_result_memory_payload_view()
    → accepted_evidence_envelope_from_payload(event.payload)   [digest 完整性校验]
    → event_payload_object_for_result_ref(...)                 [digest-checked result payload]
    → _tool_result_query_text(transaction, result_row, envelope)
      → envelope.tool_query.tool_call_requested_event_ref      [引用，非正文]
      → read_event_by_id(transaction, ref)                     [回读 request row]
      → 校验 session + run + attempt + execution + event_class + event_type
      → tool_call_request_atoms(transaction, request_row)      [digest-checked atoms]
      → 校验 tool_call_id + tool_name + normalized_arguments_digest
      → atoms.semantic_query_text ?? _safe_arguments_query_text(...)
```

数据流清晰，每步均有 digest 或枚举校验。

---

## 5. Findings

### Finding F1 (LOW, continuity) — `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 过度匹配

- **来源**: 上一轮 DS review F1，当前未修复。
- **文件/行号**: `dayu/host/durable/memory.py:107-123`
- **证据**: `"token"` fragment 匹配 `token_type`、`token_name`、`token_id`、`token_sale`、`tokenization` 等加密/权益工具分析中的合法参数名。`"cancel"` fragment 匹配 `cancellation_date`、`cancellation_policy`。`"poll"` fragment 匹配 `polling_interval`、`poll_result`。值文本中包含 `"token"` 子串同样会触发（如 `"token sale analysis"`）。
- **影响范围**: 仅影响 `semantic_query_text is None` 的 fallback 路径。大多数生产工具应提供 `semantic_query_text`，因此实际 blast radius 小。
- **建议**: 继续观察生产工具中 `semantic_query_text` 的覆盖率；若频繁落入 fallback，可考虑将 fragment 匹配改进为单词边界匹配或白名单豁免。

### Finding F2 (LOW, coverage) — `_tool_result_query_text` 部分 fail-early 分支未覆盖

- **来源**: 上一轮 DS review F2，部分修复。
- **文件/行号**: `dayu/host/durable/memory.py:508-524`
- **当前覆盖矩阵**:

| fail-early 分支 | 测试覆盖 | 状态 |
|-----------------|---------|------|
| `requested_event_ref is None` | `test_projection_consumer_fails_safe_when_requested_event_ref_missing` | ✅ |
| `read_event_by_id` returns None | — | ❌ |
| session mismatch | — | ❌ |
| run mismatch | `test_projection_consumer_fails_safe_on_request_result_execution_mismatch[run-other-...]` | ✅ |
| attempt mismatch | `test_projection_consumer_fails_safe_on_request_result_execution_mismatch[...-attempt-other-...]` | ✅ |
| execution mismatch | `test_projection_consumer_fails_safe_on_request_result_execution_mismatch[...-execution-other]` | ✅ |
| `event_class != CANONICAL_FACT` | — | ❌ |
| `event_type != TOOL_CALL_REQUESTED` | — | ❌ |
| `tool_call_request_atoms` raises | — | ❌ |
| `tool_call_id` mismatch | — | ❌ |
| `tool_name` mismatch | — | ❌ |
| `normalized_arguments_digest` mismatch | — | ❌ |

- **风险评估**: 所有未覆盖分支均返回 `_LIMITED_TOOL_QUERY_TEXT`（安全兜底），不存在泄漏风险。覆盖率 miss 不影响运行时正确性。
- **建议**: 不需要为覆盖率而增加 7 个独立测试；这些分支对应的是 durable store 损坏或 implementation bug 场景，不应在生产中出现。当前测试覆盖了最可能发生的入参错配路径（None ref、执行上下文错配）。可接受现状。

### Finding F3 (LOW, consistency) — 7 个 fail-early 分支可参数化合并

- **文件/行号**: `dayu/host/durable/memory.py:505-522`
- **证据**: `_tool_result_query_text` 中有 12 个 fail-early 分支，每个都返回相同的 `_LIMITED_TOOL_QUERY_TEXT`。7 个未覆盖的分支（session/event_class/event_type/atoms error/tool_call_id/tool_name/arguments_digest 不匹配）本质上是"引用指向了错误类型的 row"这一概念的变体。
- **建议**: 如需提升覆盖率，可考虑将回调逻辑包装为 `_validate_request_result_pairing(request_row, result_row, envelope) -> bool`，然后用一个参数化测试覆盖"任何校验失败 → limited text"的通用断言。这样既能覆盖 7 个未测试分支，又不增加 7 个独立测试函数。当前不影响正确性，可 deferred。

---

## 6. 架构约束复核（无变化）

| 约束 | 状态 | 与前一轮 diff |
|------|------|------------|
| `dayu.runtime` 不 import 上层 | PASS | 无变化 |
| 反向依赖 | PASS | 无变化 |
| 不复制 query_text 进 envelope | PASS | 无变化 |
| digest-checked payload resolution | PASS | 无变化 |
| 禁止魔法字符串 | PASS | 无变化 |
| request/result 同 session/run/attempt/execution | PASS | **新增校验** |

---

## 7. 附录 A：findings 汇总

| # | 严重性 | 来源 | 文件:行号 | 描述 | 状态 |
|---|--------|------|----------|------|------|
| F1 | LOW | DS 上轮 | `dayu/host/durable/memory.py:107-123` | `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 中 `"token"`/`"cancel"`/`"poll"` 对合法业务字段过度匹配 | 继续站立 |
| F2 | LOW | DS 上轮 | `dayu/host/durable/memory.py:508-524` | `read_event_by_id` returns None 等 7 个 fail-early 分支未覆盖 | 部分修复（4/12 分支已覆盖） |
| F3 | LOW | 本轮新增 | `dayu/host/durable/memory.py:505-522` | 7 个 fail-early 分支结构相似，可参数化合并测试 | 可 deferred |

---

## 8. 附录 B：补修前后对比

| 维度 | 上轮状态（MiMo + DS review） | 本轮补修后 |
|------|--------------------------|----------|
| 同源校验 | session + event_type + tool_call_id + tool_name + digest；缺 run/attempt/execution | + run/attempt/execution 全量校验 |
| 执行上下文错配测试 | 无 | 3 变体参数化（run/attempt/execution 各自错配） |
| None ref 测试 | 无 | `test_projection_consumer_fails_safe_when_requested_event_ref_missing` |
| LLM-facing 文本泄露 | 全部路径 fail-safe | 全部路径 fail-safe（补修未引入新泄漏路径） |
| 测试数 | 75 passed | 79 passed |
| pyright | 0 errors | 0 errors |

补修正确、完整、未引入回归。
