# Final Re-Review: TOOL_RESULT_ACCEPTED Evidence Request Memory

**裁决约束**: Conversation Memory projection 不得从 raw tool arguments 合成 LLM-facing request/query 语义；query 语义生产真源只能是 digest-checked TOOL_CALL_REQUESTED.semantic_query_text。semantic_query_text 缺失时必须低信号降级，不得使用 ad hoc substring blacklist、redaction fallback、工具参数摘要等生产逻辑。

**审查范围**: 当前未提交 diff（phase/host-issues-control 分支）
**审查日期**: 2026-07-09
**审查模型**: MiMo

---

## 1. durable/memory.py _tool_result_query_text 实现

**检查项**: 是否已删除 `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` / `_safe_arguments_query_text` / redaction import / 工具参数摘要 fallback

**结论**: ✅ PASS

- `grep` 确认 `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS`、`_safe_arguments_query_text`、`redaction`、`_REDACT`、`blacklist`、`import re` 在 `dayu/host/durable/memory.py` 和 `dayu/host/memory.py` 中均无匹配。
- `_tool_result_query_text` 返回路径只两条:
  - `atoms.semantic_query_text is not None` → 返回 `atoms.semantic_query_text`
  - 所有其它路径 → 返回 `_LIMITED_TOOL_QUERY_TEXT`（"查询语义不可用；参数未安全展开。"）
- 不存在任何从 `arguments_json`、`arguments_inline_json`、工具参数字段或 envelope 内部字段合成 query 文本的代码路径。

## 2. request/result 同源校验完整性

**检查项**: session/run/attempt/execution/event_class/event_type/tool_call_id/tool_name/normalized_arguments_digest

**结论**: ✅ PASS

`_tool_result_query_text` 依次校验：

| # | 校验点 | 失败行为 |
|---|--------|----------|
| 1 | `envelope.tool_query.tool_call_requested_event_ref` 存在 | → `_LIMITED_TOOL_QUERY_TEXT` |
| 2 | `read_event_by_id` 找到 request row | → `_LIMITED_TOOL_QUERY_TEXT` |
| 3 | `session_id` 一致 | → `_LIMITED_TOOL_QUERY_TEXT` |
| 4 | `run_id` / `attempt_id` / `execution_id` 三元组一致（`_same_run_attempt_execution`） | → `_LIMITED_TOOL_QUERY_TEXT` |
| 5 | `event_class == CANONICAL_FACT` | → `_LIMITED_TOOL_QUERY_TEXT` |
| 6 | `event_type == TOOL_CALL_REQUESTED` | → `_LIMITED_TOOL_QUERY_TEXT` |
| 7 | `tool_call_request_atoms` 可解析 | → `_LIMITED_TOOL_QUERY_TEXT` |
| 8 | `atoms.tool_call_id == envelope.tool_call_id` | → `_LIMITED_TOOL_QUERY_TEXT` |
| 9 | `atoms.tool_name == envelope.tool_name` | → `_LIMITED_TOOL_QUERY_TEXT` |
| 10 | `atoms.normalized_arguments_digest == envelope.tool_query.normalized_arguments_digest` | → `_LIMITED_TOOL_QUERY_TEXT` |

任一校验失败均返回低信号文本，不暴露 request row 内容、event id、arguments 或 digest。

## 3. 测试覆盖

**检查项**: happy path / semantic_query_text absent / 全部 fail-early 代表路径 / TOOL_AWAITING 等价性

**结论**: ✅ PASS（87 tests passed，0.67s）

### 3.1 Happy path — 回读 semantic_query_text

- `test_projection_consumer_pairs_tool_result_with_requested_query`（L1782）: durable projection 从 request row 回读 query 语义 "读取 ticker=COIN 的财报列表"，assert 含该文本、工具名、raw outcome，不含 tool_call_id / event_id / sha256: / payload / artifact / wait / awaiting 等。
- `test_accepted_tool_evidence_includes_query_and_raw_outcome_without_refs`（L1166）: 直接 memory consumer 通过 `evidence_query_text` 参数注入 query "查询 DAYU 的业务事实"，assert 含该文本、工具名、raw outcome，不含 event id / tool_call_id / payload ref / sha256:。
- `test_accepted_tool_evidence_disambiguates_raw_result_with_request_query`（L1239）: raw outcome 含义不完整（`{"total":0,"documents":[]}`）时，query 语义 "读取 ticker=COIN 的财报列表" 必须出现在 memory 文本中。

### 3.2 semantic_query_text absent 时低信号且不泄露 arguments

- `test_projection_consumer_uses_limited_query_without_semantic_query`（L1855）: request payload 的 `semantic_query_text=None`，assert memory 含 "查询语义不可用；参数未安全展开。"、raw outcome `"total":1`，不含 "MSFT" / "arguments" / "ticker" / event_id / tool_call_id / sha256:。
- `test_projection_consumer_uses_limited_query_for_unsafe_argument_fallback`（L2129）: arguments 含 `api_key=sk-live-secret`、`input_path=/Users/leo/private/report.pdf`、`ticker=COIN`，assert memory 含低信号文本、raw outcome，不含 secret / local_path / "arguments" / "api_key" / "input_path" / "ticker" / "COIN" / event_id / tool_call_id。

### 3.3 全部 fail-early 代表路径低信号

- `test_projection_consumer_fails_safe_on_request_result_execution_mismatch`（L1926，parametrize×3）: run_id / attempt_id / execution_id 分别错配，assert 含低信号文本、raw outcome，不含原始 query / event_id / tool_call_id / 错配的 id。
- `test_projection_consumer_fails_safe_when_requested_event_ref_missing`（L1996）: envelope 缺少 request ref，assert 含低信号文本，不含原始 query / event_id / tool_call_id。
- `test_projection_consumer_fails_safe_for_request_query_source_mismatch`（L2100，parametrize×8）: 覆盖 requested-event-row-missing / request-session-mismatch / request-event-class-not-canonical / request-event-type-mismatch / request-atoms-unreadable / tool-call-id-mismatch / tool-name-mismatch / arguments-digest-mismatch 八个分支，全部 assert 含低信号文本、raw outcome，不含原始 query / event_id / tool_call_id / sha256:。

### 3.4 TOOL_AWAITING 等价性未破坏

- `test_tool_awaiting_does_not_project_llm_facing_memory`（L684）: assert selected window 只含 user item，不含 "等待" / "awaiting" / tool_name / arguments。
- `test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics`（L735）: assert 有无 TOOL_AWAITING 时 LLM-facing memory text view 完全一致。
- `test_conversation_memory_consumer_uses_shared_projection_event_filter`（L2203）: assert event filter 不含 TOOL_AWAITING。

### 3.5 Accept barrier test 补充

- `test_tool_result_accepted_payload_carries_accepted_evidence_envelope`（test_toolruntime_accept_barrier.py L200）: 新增 assert `"query_text" not in tool_query_mapping`，确认 envelope tool_query 不复制 query 正文。

## 4. 文档一致性

**检查项**: docs/host/design.md / dayu/host/README.md / tests/README.md 是否与最新裁决冲突

**结论**: ✅ PASS

- **docs/host/design.md** 新增段落: "TOOL_AWAITING 是 Host / ToolRuntime 之间的等待治理事实，对模型不可见……不得成为 Conversation Memory producer，也不得投影为 LLM-facing……"。Evidence / Fact Memory 段落修改为: "LLM-facing evidence material 必须自解释……它不是 TOOL_CALL_REQUESTED 原事件、原始参数或内部治理字段的原样回放，也不得暴露 tool_call_id、EventLog id、payload ref、artifact ref、digest、wait id、awaiting / poll / cancel 状态或 Python 类型名"。与裁决一致。
- **dayu/host/README.md** 修改 TOOL_RESULT_ACCEPTED 描述为: "生成 self-explaining readable evidence item……从该 request atom 回读 LLM-safe request / query 文本……不暴露 tool call id、EventLog id、payload / artifact ref、digest、wait / poll / cancel lifecycle 或实现类型名"。与裁决一致。
- **tests/README.md** 修改 memory projection 描述为: "TOOL_RESULT_ACCEPTED evidence item 通过对应 request atom 取得 LLM-safe request / query 语义……ambiguous raw result 不丢查询意图"。与裁决一致。
- 三份文档均无 "从 raw arguments 合成语义"、"substring blacklist"、"redaction fallback" 或 "工具参数摘要" 的表述。

---

## 验证结果

| 项目 | 结果 |
|------|------|
| `pytest tests/host/test_memory_projection.py tests/host/test_toolruntime_accept_barrier.py -q` | ✅ 87 passed, 0.67s |
| `pyright dayu/host/durable/memory.py dayu/host/memory.py dayu/host/evidence.py` | ✅ 0 errors, 0 warnings, 0 informations |

---

## Completion Report: PASS

**Findings**: 无。

**审查确认**:
1. `_tool_result_query_text` 只返回 `atoms.semantic_query_text` 或 `_LIMITED_TOOL_QUERY_TEXT`，无任何从 raw arguments 合成 query 的路径。
2. request/result 同源校验覆盖 session/run/attempt/execution/event_class/event_type/tool_call_id/tool_name/normalized_arguments_digest 共 10 个校验点。
3. 测试覆盖 happy path、semantic_query_text absent、全部 13 个 fail-early 代表路径、TOOL_AWAITING 等价性。
4. 三份文档与最新裁决一致，无冲突。
