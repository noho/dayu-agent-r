# Code Review — WU-CM-01-F03 Implementation

## Scope

- Mode: current changes
- Branch: phaseflow/wu-cm-01-f04-closeout
- Base: main
- Output file: docs/reviews/wu-cm-01-f03-code-review-ds.md
- Included scope:
  - `dayu/host/terminal_summary_payload.py`
  - `dayu/host/_terminal_answer.py`
  - `dayu/host/run_input.py`
  - `dayu/host/durable/memory.py`
  - `dayu/host/memory.py`
  - `dayu/host/compaction_evidence.py`
  - `dayu/host/README.md`
  - `tests/host/test_terminal_summary_payload.py`
  - `tests/host/test_memory_projection.py`
  - `tests/host/test_run_input_builder.py`
  - `tests/host/test_compaction_operation.py`
  - `tests/host/test_compact_material.py`
  - `docs/reviews/wu-cm-01-f03-implementation-codex.md` (implementation report, read-only)
- Excluded scope: plan docs, plan review docs, control doc — read for context, not reviewed as implementation
- Parallel review coverage: 无（全程走读单一主 reviewer）

## Findings

未发现实质性问题。

### 逐项 hard constraint 验证

**1. assistant final answer continuity 来源收窄**

所有 assistant final answer / conclusion continuity 路径已收窄到两个合法来源：

- `RUN_SUCCEEDED.final_answer`（非空字符串）
- digest-checked terminal summary artifact `content`

证据：

- `terminal_summary_payload.py:26-39` `assistant_final_answer_text_from_run_payload` 只读 `final_answer` 字段。（`_PAYLOAD_FIELD_FINAL_ANSWER = "final_answer"`，无 `content`、`summary_text` 搜索。）
- `terminal_summary_payload.py:42-55` `terminal_summary_content_text_from_payload` 只读 artifact `content` 字段。（`_PAYLOAD_FIELD_CONTENT = "content"`，无 `summary_text`、`summary` 搜索。）
- `_terminal_answer.py:21-66` `assistant_final_answer_continuity_text` 读取顺序：先 `final_answer`，再通过 `terminal_summary_ref` + `terminal_summary_digest` 校验后读 artifact `content`。第 32-33 行 docstring 明确："裸 `RUN_SUCCEEDED.content`、`summary_text` 或 nested `summary` 均不是 assistant final answer 来源"。
- `memory.py:1616-1630` `_selected_assistant_item` 只调用 `assistant_final_answer_text_from_run_payload`（纯 field reader，只读 `final_answer`），缺失时 return None；旧 `_ref_summary_text(event)` fallback 已删除。
- `compaction_evidence.py:414-424` `_assistant_history_materials` 通过 `assistant_final_answer_continuity_text` 获取文本，无时返回空 tuple。
- `run_input.py` 和 `durable/memory.py` 的 `_payload_with_assistant_final_answer` 中，early-return guard 只检查 `assistant_final_answer_text_from_run_payload`（即只检查 `final_answer` 字段），不检查 `content`/`summary_text`。

`run_input.py`、`durable/memory.py`、`compaction_evidence.py` 全文 `rg summary_text` 残留项均属于 accepted compact session_summary 读取路径或 snapshot 渲染路径，无一用于 assistant final answer continuity。

**2. terminal artifact `content` 只在 digest-checked resolver 后进入 transient `final_answer`**

- `_terminal_answer.py:49-66` 要求 `terminal_summary_ref` 与 `terminal_summary_digest` 均非空才调用 `sqlite_payload_object(transaction, payload_ref=..., payload_digest=..., payload_label="terminal summary")` 解析并校验 artifact。任一 descriptor 缺失时返回 None。
- `durable/memory.py:224-253` `_payload_with_assistant_final_answer` 将 `assistant_final_answer_continuity_text` 返回的文本合并到 transient payload 的 `final_answer` 字段（`merged[_PAYLOAD_FIELD_FINAL_ANSWER] = final_answer`），不是 `content` 字段。
- `run_input.py:3017-3029` 同逻辑。
- `_terminal_answer.py:63-66` artifact 解析后只通过 `terminal_summary_content_text_from_payload` 读 `content` 字段，不读 `summary_text`。

**3. Session Summary Memory 不变**

- `memory.py:1695-1721` `_session_summary_from_accepted_event` 只从 `accepted_candidate.session_summary.summary_text` 读取。该路径 untouched。
- 测试 `test_memory_projection.py:291-320` `test_accepted_compact_materializes_vnext_memory_sections` 断言 `session_summary_memory.summary_text == "用户关注收入增速和毛利率变化。"`，确认仍来自 compact session_summary。
- 测试 `test_memory_projection.py:323-346` 同时断言 `RUN_SUCCEEDED.summary_text` 不生成 assistant selected item 且不生成 session summary。

**4. `_terminal_answer.py` 边界合理**

- 模块职责单一：`terminal_summary_payload.py` 为纯 field reader（无 transaction 依赖），`_terminal_answer.py` 为 transaction-aware resolver（依赖 `payload_resolution` → `durable.transaction`）。
- import cycle fallback 实现：plan 在 doc line 295 已预期该 import cycle，实现按 plan 执行。
- 消费方均为 Host 内部模块：`run_input.py`、`durable/memory.py`、`compaction_evidence.py`、`tests/host/test_terminal_summary_payload.py`。无 Host 外部 import。
- 非 compatibility seam：旧 `assistant_summary_from_payload` 已删除，新模块是从零建立的稳定边界，不是旧接口的 wrapper。

**5. 测试覆盖 hard constraint 与 regression**

新增/迁移测试验证：

| 测试 | 文件 | 覆盖 |
|---|---|---|
| `test_run_payload_final_answer_is_read` | test_terminal_summary_payload.py:45 | final_answer 可读 |
| `test_blank_run_payload_final_answer_is_missing` | test_terminal_summary_payload.py:57 | 空白 final_answer = None |
| `test_run_payload_summary_fields_are_not_final_answer_sources` | test_terminal_summary_payload.py:69 | content/summary_text/nested summary 不读 |
| `test_terminal_summary_payload_content_is_read` | test_terminal_summary_payload.py:87 | artifact content 可读 |
| `test_blank_terminal_summary_content_is_missing` | test_terminal_summary_payload.py:99 | 空白 artifact content = None |
| `test_terminal_summary_payload_summary_fields_are_not_content_sources` | test_terminal_summary_payload.py:111 | artifact summary_text/nested 不读 |
| `test_allowed_non_string_field_strict_raises_and_lenient_returns_none` | test_terminal_summary_payload.py:128 | strict vs lenient 类型校验 |
| `test_disallowed_summary_text_type_does_not_trigger_strict_error` | test_terminal_summary_payload.py:159 | disallowed 字段类型非法不抛错 |
| `test_continuity_resolver_reads_digest_checked_terminal_content` | test_terminal_summary_payload.py:178 | digest-checked resolver 端到端 |
| `test_run_succeeded_summary_only_does_not_materialize_assistant_window` | test_memory_projection.py:323 | summary-only = 无 assistant item |
| `test_run_succeeded_payload_refs_do_not_materialize_assistant_window` | test_memory_projection.py:349 | ref/digest 不泄漏 |
| `test_projection_consumer_hydrates_terminal_content_as_final_answer` | test_memory_projection.py:367 | durable 路径 hydrated terminal content |
| `test_inline_delta_uses_terminal_content_and_ignores_summary_fallback` | test_run_input_builder.py:919 | inline delta 使用 terminal content |
| `test_compaction_request_evidence_inputs_collect_terminal_content` | test_compaction_operation.py:645 | compaction 路径 terminal content |
| `test_compaction_request_evidence_inputs_ignore_summary_only_run_succeeded` | test_compaction_operation.py:711 | summary-only = 空 history material |
| `test_conversation_compact_input_vnext_does_not_map_session_summary_to_answer` | test_compact_material.py:589 | session_summary 不进 answer_material |

197 个测试通过，pyright 0 errors，旧 helper/enum/dead chain grep 无残留。

**6. README 只同步稳定实现**

`dayu/host/README.md:296` 替换为精确的当前语义描述，无过程状态、未来设计或旧术语残留。

## Open Questions

无。

## Residual Risk

- `dayu/host/memory.py` 中 `_selected_assistant_item`（直接 projection 路径）只读 inline `final_answer`，不通过 `assistant_final_answer_continuity_text` 解析 terminal artifact content。这是因为该路径无 `HostTransaction` 引用。当前所有生产路径的 caller（durable projection consumer、inline delta runner）在调用 `project_conversation_memory_event` 前已通过 `_payload_with_assistant_final_answer` 完成 hydration，故此限制不会在生产路径触发。若未来出现新的非 hydration caller，需确保其也执行 prior hydration 或迁移为 transaction-aware 路径。
- `_payload_with_assistant_final_answer` 在 `run_input.py` 与 `durable/memory.py` 中存在两份近似实现（分别操作 `EventLogRow` 与 `ProjectionEventView`）。当前差异仅在一行 payload 提取方式，属轻量重复，不构成维护风险。若未来该逻辑继续增长，应考虑提取共享 helper（需处理不同 input type）。

## Verdict

**pass** — 0 blocking findings，0 non-blocking findings。实现忠实执行 plan 全部 5 项决策与 5 个 slice，用户 hard constraint 全部覆盖，测试充分，pyright 清洁，dead code 已物理删除，README 对齐当前实现。
