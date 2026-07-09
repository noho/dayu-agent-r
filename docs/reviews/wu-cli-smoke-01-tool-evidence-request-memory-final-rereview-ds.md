# Final Rereview: WU-CLI-SMOKE-01 TOOL_RESULT_ACCEPTED Evidence Request Memory

**审查类型**: 针对性 final re-review（DeepSeek）
**审查日期**: 2026-07-09
**审查范围**: issue-176 TOOL_RESULT_ACCEPTED evidence request memory 未提交 diff
**裁决基准**: 2026-07-09 总控裁决

## 裁决摘要

> Conversation Memory projection 不得从 raw tool arguments 合成 LLM-facing request/query 语义；query 语义生产真源只能是 digest-checked `TOOL_CALL_REQUESTED.semantic_query_text`。`semantic_query_text` 缺失时必须低信号降级，不得使用 ad hoc substring blacklist、redaction fallback、工具参数摘要等生产逻辑。

## 审查结论：PASS

**验证结果**: 87 tests passed, pyright 0 errors/0 warnings/0 informations

---

## 审查条目 1：`dayu/host/durable/memory.py` — 禁止代码删除确认

| 检查项 | 状态 | 证据 |
|--------|------|------|
| `_UNSAFE_ARGUMENT_TEXT_FRAGMENTS` 已删除/不存在 | PASS | 全仓 grep 无匹配 |
| `_safe_arguments_query_text` 已删除/不存在 | PASS | 全仓 grep 无匹配 |
| `redaction import` 未进入 durable/memory.py | PASS | 文件 import 列表中无 redaction 相关导入 |
| 工具参数摘要 fallback 逻辑不存在 | PASS | `_tool_result_query_text` 只有两条返回路径 |
| `_tool_result_query_text` 只返回 `atoms.semantic_query_text` 或 `_LIMITED_TOOL_QUERY_TEXT` | PASS | `durable/memory.py:501-503` |

**`_tool_result_query_text` 返回路径分析**（`durable/memory.py:464-503`）:

1. `requested_event_ref is None` → `_LIMITED_TOOL_QUERY_TEXT`
2. `read_event_by_id` 返回 `None` → `_LIMITED_TOOL_QUERY_TEXT`
3. session/run/attempt/execution/event_class/event_type 任一不匹配 → `_LIMITED_TOOL_QUERY_TEXT`
4. `tool_call_request_atoms` 抛 `HostDurableError` → `_LIMITED_TOOL_QUERY_TEXT`
5. tool_call_id/tool_name/normalized_arguments_digest 任一不匹配 → `_LIMITED_TOOL_QUERY_TEXT`
6. `atoms.semantic_query_text is not None` → `atoms.semantic_query_text`（唯一成功路径）
7. `atoms.semantic_query_text is None` → `_LIMITED_TOOL_QUERY_TEXT`

**无 fallthrough 到参数摘要、redaction 或其他合成逻辑。**

---

## 审查条目 2：request/result 同源校验完整性

`_tool_result_query_text` 中的校验链（`durable/memory.py:483-500`）：

| 校验维度 | 实现 | 位置 |
|----------|------|------|
| session_id | `request_row.session_id != result_row.session_id` | L484 |
| run_id | `_same_run_attempt_execution()` | L485 |
| attempt_id | `_same_run_attempt_execution()` | L485 |
| execution_id | `_same_run_attempt_execution()` | L485 |
| event_class | `request_row.event_class != EventClass.CANONICAL_FACT` | L486 |
| event_type | `request_row.event_type != _EVENT_TYPE_TOOL_CALL_REQUESTED` | L487 |
| tool_call_id | `atoms.tool_call_id != envelope.tool_call_id` | L495 |
| tool_name | `atoms.tool_name != envelope.tool_name` | L496 |
| normalized_arguments_digest | `atoms.normalized_arguments_digest != envelope.tool_query.normalized_arguments_digest` | L497-498 |

**结论：PASS** — 九维度校验完整，任一失败均降级到 `_LIMITED_TOOL_QUERY_TEXT`。

---

## 审查条目 3：`tests/host/test_memory_projection.py` 测试覆盖

| 测试场景 | 测试名称 | 行号 | 状态 |
|----------|----------|------|------|
| happy path 回读 semantic_query_text | `test_projection_consumer_pairs_tool_result_with_requested_query` | 1782 | PASS |
| semantic_query_text absent → 低信号，不泄露 arguments | `test_projection_consumer_uses_limited_query_without_semantic_query` | 1855 | PASS |
| request row missing → 低信号 | parametrized `append_request=False` | 2058 | PASS |
| session mismatch → 低信号 | parametrized `request_session_id="session-other"` | 2063 | PASS |
| event_class 非 CANONICAL_FACT → 低信号 | parametrized `request_event_class=EventClass.DIAGNOSTIC` | 2067 | PASS |
| event_type 非 TOOL_CALL_REQUESTED → 低信号 | parametrized `request_event_type="TOOL_CALL_GOVERNED"` | 2072 | PASS |
| request atoms 不可读 → 低信号 | parametrized `request_payload_kind=_REQUEST_PAYLOAD_KIND_INVALID` | 2075 | PASS |
| tool_call_id mismatch → 低信号 | parametrized `envelope_tool_call_id` mismatch | 2082 | PASS |
| tool_name mismatch → 低信号 | parametrized `envelope_tool_name` mismatch | 2087 | PASS |
| arguments digest mismatch → 低信号 | parametrized `envelope_arguments_digest` mismatch | 2091 | PASS |
| run/attempt/execution mismatch（3 参数化） | `test_projection_consumer_fails_safe_on_request_result_execution_mismatch` | 1926 | PASS |
| request ref missing → 低信号 | `test_projection_consumer_fails_safe_when_requested_event_ref_missing` | 1996 | PASS |
| unsafe arguments 不泄露（secret/path/ticker） | `test_projection_consumer_uses_limited_query_for_unsafe_argument_fallback` | 2129 | PASS |
| TOOL_AWAITING 不投影 LLM-facing memory | `test_tool_awaiting_does_not_project_llm_facing_memory` | 684 | PASS |
| TOOL_AWAITING 等价性未破坏 | `test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics` | 735 | PASS |

**结论：PASS** — 全覆盖 happy path、全部 fail-early 代表路径低信号、semantic_query_text absent 时不泄露 arguments、TOOL_AWAITING 等价性未破坏。

---

## 审查条目 4：docs 冲突检查

| 文档 | 结论 | 说明 |
|------|------|------|
| `docs/host/design.md` | PASS | L1568 描述"可以退回到 bounded arguments projection **或**业务中性'工具参数不可读'说明"——允许两种路径，当前代码选择后者，不冲突 |
| `dayu/host/README.md` | PASS | 无 semantic_query/ad hoc/argument fallback 相关冲突内容 |
| `tests/README.md` | PASS | 无冲突内容 |

---

## 附加发现（非阻塞）

### 1. `_LIMITED_TOOL_QUERY_TEXT` 与 `_ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 重复定义

两个常量值相同（`"查询语义不可用；参数未安全展开。"`），分别定义在：
- `dayu/host/durable/memory.py:103` — `_LIMITED_TOOL_QUERY_TEXT`
- `dayu/host/memory.py:102` — `_ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`

**严重度**: LOW。两处各有独立上下文（durable projection adapter vs projection logic），当前不构成漂移风险。若未来修改低信号文案，需同时修改两处。

### 2. `docs/host/design.md` L1568 "bounded arguments projection" 措辞

设计文档 L1568 仍描述"可以退回到 bounded arguments projection"作为 compact evidence projection 的一个可选路径。当前裁决将此路径从 Conversation Memory projection 中排除，但设计文档的 compact evidence projection 上下文可能指代不同组件。建议后续 phase 明确区分并更新措辞。

**严重度**: LOW。当前实现不依赖该措辞，且设计文档以"或"形式给出两种可选路径，代码选择了合规路径。

---

## 验证记录

```
$ pytest tests/host/test_memory_projection.py tests/host/test_toolruntime_accept_barrier.py -q
87 passed in 0.66s

$ pyright dayu/host/durable/memory.py dayu/host/memory.py tests/host/test_memory_projection.py tests/host/test_toolruntime_accept_barrier.py
0 errors, 0 warnings, 0 informations
```

---

## 最终裁决

**PASS** — 当前未提交 diff 完全符合裁决要求。无阻塞性 finding。
