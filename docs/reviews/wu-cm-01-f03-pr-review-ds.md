# Code Review — PR 125

## Scope

- Mode: PR review
- PR: [#125](https://github.com/noho/dayu-agent-r/pull/125)
- Repository: noho/dayu-agent-r
- Title: `phaseflow: close out WU-CM-01-F04 and narrow final answer continuity`
- Author: noho
- Head branch: `phaseflow/wu-cm-01-f04-closeout`
- Base branch: `main`
- Output file: `docs/reviews/wu-cm-01-f03-pr-review-ds.md`
- Review timestamp: 20260606-223314
- Included scope:
  - `dayu/host/terminal_summary_payload.py` — assistant continuity payload field reader contract
  - `dayu/host/_terminal_answer.py` — transaction-aware continuity resolver (new)
  - `dayu/host/run_input.py` — inline delta hydration + dead code deletion
  - `dayu/host/durable/memory.py` — durable projection hydration
  - `dayu/host/memory.py` — `_selected_assistant_item` null-guard + ref-fallback removal
  - `dayu/host/compaction_evidence.py` — compaction history material source narrowing
  - `dayu/host/README.md` — stable implementation doc sync
  - `tests/host/test_terminal_summary_payload.py` — payload helper unit tests
  - `tests/host/test_memory_projection.py` — memory projection integration tests
  - `tests/host/test_run_input_builder.py` — inline delta integration tests
  - `tests/host/test_compaction_operation.py` — compaction integration tests
  - `tests/host/test_compact_material.py` — compact material mapping tests
  - `docs/host/issues-implementation-control.md` — control doc state update
  - `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md` — accepted plan (new)
  - `docs/reviews/wu-cm-01-f03-*` — review artifacts chain (new)
  - `docs/reviews/wu-cm-01-f04-final-closeout-controller.md` — F04 closeout (new)
- Excluded scope: F04 closeout code (documentation-only, no production code changes)
- Parallel review coverage: 无（本 review 由 AgentDS 独立执行，整合前置 MiMo/DS code review、aggregate deepreview 与 controller 裁决结论，并独立复核全部代码路径与 hard constraint 验证点）
- CI/checks: no checks reported on `phaseflow/wu-cm-01-f04-closeout` branch（controller 已独立验证 197 tests pass + pyright 0 errors）

## 前置 Artifact 链

| Artifact | 角色 | 裁决 |
|---|---|---|
| `docs/reviews/wu-cm-01-f03-code-review-mimo.md` | MiMo code review | pass, 0 findings |
| `docs/reviews/wu-cm-01-f03-code-review-ds.md` | DS code review | pass, 0 findings |
| `docs/reviews/wu-cm-01-f03-code-review-controller-adjudication.md` | Controller 裁决 | accepted |
| `docs/reviews/wu-cm-01-f03-aggregate-deepreview-mimo.md` | MiMo aggregate deepreview | pass, 0 findings |
| `docs/reviews/wu-cm-01-f03-aggregate-deepreview-ds.md` | DS aggregate deepreview | pass, 0 findings |
| `docs/reviews/wu-cm-01-f03-aggregate-deepreview-controller-adjudication.md` | Controller 裁决 | accepted |
| `docs/reviews/wu-cm-01-f03-draft-pr-readiness-controller.md` | Controller draft PR readiness | ready |
| `docs/reviews/wu-cm-01-f04-final-closeout-controller.md` | F04 closeout | passed |

## 独立验证方法

本 reviewer 执行以下独立验证：

1. 完整 diff (`gh pr diff 125`) 走读，覆盖所有 6 个 production 模块 + 5 个 test 文件。
2. 逐文件读取 `_terminal_answer.py`、`terminal_summary_payload.py`、`memory.py` 关键函数、`run_input.py` 关键函数、`durable/memory.py` 关键函数、`compaction_evidence.py` 关键函数。
3. 针对 6 条 hard constraint 逐条执行 grep 验证：旧 helper/enum 残留、`STRICT_ALLOW_EMPTY` 残留、dead code 链残留、旧常量残留、`_optional_str` 残留。
4. 对 `summary_text` 残留执行逐文件语义分类，区分 Session Summary Memory 路径、evidence/user display_text fallback 路径与 assistant final answer 路径。
5. 核对 PR body、control doc、README、review artifacts 与 branch 间的 consistency。

## Hard Constraint 逐项验证

### 1. LLM-facing Trace / Answer material 只接受 `final_answer` 或 digest-checked terminal summary artifact `content`

**全部四条 production 路径均已验证：**

| 调用路径 | 文件(行号) | 使用的 helper | 输入来源 |
|---|---|---|---|
| assistant selected recent window | `memory.py:1625-1628` | `assistant_final_answer_text_from_run_payload`（只读 `final_answer`） | 已 hydrate transient payload |
| durable projection hydration | `durable/memory.py:224-243` | `assistant_final_answer_continuity_text`（`final_answer` → digest-checked artifact `content`） | 原始 RUN payload + transaction |
| inline delta projection hydration | `run_input.py:3019-3036` | `assistant_final_answer_continuity_text`（同上） | 原始 RUN payload + transaction |
| compaction history material | `compaction_evidence.py:417-421` | `assistant_final_answer_continuity_text`（同上） | 原始 RUN payload + transaction |

所有路径均满足约束。无任何路径读取 `summary_text`、nested `summary` 或裸 `RUN_SUCCEEDED.content`。

### 2. `summary_text` 和 nested `summary` 不作为 assistant final answer fallback

**代码证据：**
- `terminal_summary_payload.py:37-38` — `assistant_final_answer_text_from_run_payload` 只调用 `_text_field(payload, field_name=_PAYLOAD_FIELD_FINAL_ANSWER, ...)` 即 `"final_answer"`。不包含 `content`、`summary_text`、`summary`。
- `terminal_summary_payload.py:53-54` — `terminal_summary_content_text_from_payload` 只调用 `_text_field(payload, field_name=_PAYLOAD_FIELD_CONTENT, ...)`。仅在 digest-checked resolver 中被调用。
- 旧 `assistant_summary_from_payload()` 及其 `final_answer → content → summary_text → nested summary` 搜索链已物理删除。
- `_PAYLOAD_FIELD_SUMMARY` 和 `_PAYLOAD_FIELD_SUMMARY_TEXT` 常量已从 `terminal_summary_payload.py` 删除。

**测试证据：**
- `test_run_payload_summary_fields_are_not_final_answer_sources` — 直接断言 `content`/`summary_text`/nested `summary` 均不被 `assistant_final_answer_text_from_run_payload` 读取。
- `test_terminal_summary_payload_summary_fields_are_not_content_sources` — 断言 artifact 侧同样行为。

### 3. `RUN_SUCCEEDED.content`、payload ref、digest、event id 不作为 assistant final answer fallback

**代码证据：**
- `_terminal_answer.py:32-33` docstring 明确声明排除项。
- `_terminal_answer.py:55-56` — `terminal_summary_ref` 或 `terminal_summary_digest` 任一缺失时返回 `None`，不会用单个 descriptor 触发不完整 lookup。
- `_terminal_answer.py:63-66` — artifact 解析后只调用 `terminal_summary_content_text_from_payload` 读 `content`，不读其他字段。
- `memory.py:1629-1630` — `_selected_assistant_item` 无 text 时返回 `None`（已删除 `_ref_summary_text(event)` fallback）。
- `memory.py:1241-1243` — `project_conversation_memory_event` 在 `None` 时跳过 item，不注入 ref/digest/event_id。
- `run_input.py` 和 `durable/memory.py` 中的 `_PAYLOAD_FIELD_CONTENT`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST` 常量已删除。hydration 合并目标为 `_PAYLOAD_FIELD_FINAL_ANSWER`（即 `"final_answer"`），不是 `"content"`。

**测试证据：**
- `test_run_succeeded_summary_only_does_not_materialize_assistant_window` — summary-only 不生成 assistant item。
- `test_run_succeeded_payload_refs_do_not_materialize_assistant_window` — ref/digest-only 不生成 assistant item。

### 4. Session Summary Memory 只来自 accepted compact `session_summary`

**代码证据：**
- `memory.py:1690-1721` — `_session_summary_from_accepted_event` 未被修改，仍只从 `accepted_candidate.session_summary.summary_text` 读取。
- 该函数只在 `event.event_type == _EVENT_TYPE_CONTEXT_COMPACTED` 时被调用。

**测试证据：**
- `test_accepted_compact_materializes_vnext_memory_sections` — 断言 `session_summary_memory.summary_text` 来自 compact session_summary。
- `test_run_succeeded_summary_only_does_not_materialize_assistant_window` — 同时负向断言 `RUN_SUCCEEDED.summary_text` 不生成 session summary。

### 5. 无 compatibility alias/wrapper/re-export

**grep 验证：**
- `rg -n "assistant_summary_from_payload|PayloadSummaryTextPolicy" dayu tests` → **无匹配**
- `rg -n "STRICT_ALLOW_EMPTY" dayu tests` → **无匹配**
- `rg -n "_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event" dayu/host/run_input.py` → **无匹配**
- `rg -n "_optional_str" dayu/host/durable/memory.py` → **无匹配**

**导出验证：**
- `terminal_summary_payload.py:__all__` 只导出 `PayloadTextReadPolicy`、`assistant_final_answer_text_from_run_payload`、`terminal_summary_content_text_from_payload`。
- `_terminal_answer.py:__all__` 只导出 `assistant_final_answer_continuity_text`。
- 两个模块均不在 `dayu/host/__init__.py` 中暴露（验证：`__init__.py` 无对应 import）。

### 6. PR body、control doc、README、artifacts 与 branch 一致性

**PR body vs branch：**
- PR title: `phaseflow: close out WU-CM-01-F04 and narrow final answer continuity`
- Head branch: `phaseflow/wu-cm-01-f04-closeout` — 一致。
- PR description 准确描述了 WU-CM-01-F03 的全部 6 条 hard constraint。

**Control doc (`docs/host/issues-implementation-control.md`)：**
- WU-CM-01-F03 状态: `draft-pr-open` — 正确反映当前 gate。
- WU-CM-01-F03 draft PR 链接: `#125` — 一致。
- WU-CM-01-F04 状态: `completed` — 正确反映已完成 closeout。
- `WU-TOOLS-01-S6-R1` residual risk 已从 active table 移除 — 一致。
- Phase gate 字段已从 `draft-PR-pass` 更新为 `PR review` — 正确反映当前 gate。

**`dayu/host/README.md`：**
- 第 296 行替换为精确当前语义："terminal answer continuity 的稳定语义是：RunInputBuilder、memory projection 和 compaction evidence 只把 `RUN_SUCCEEDED.final_answer`，或经 `terminal_summary_ref` / `terminal_summary_digest` 校验后的 terminal summary artifact `content`，作为 assistant final answer / conclusion continuity。"
- 无过程状态、未来计划、旧术语残留。

**Controller validation baseline（独立复核）：**
- `rg "assistant_summary_from_payload|PayloadSummaryTextPolicy" dayu tests` → 无匹配 ✓
- `rg "STRICT_ALLOW_EMPTY|_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event" dayu tests` → 无匹配 ✓
- `rg "_PAYLOAD_FIELD_CONTENT|_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF|_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST" dayu/host/run_input.py` → 无匹配 ✓
- `rg "_optional_str" dayu/host/durable/memory.py` → 无匹配 ✓
- `rg "_PAYLOAD_FIELD_SUMMARY|_PAYLOAD_FIELD_SUMMARY_TEXT" dayu/host/terminal_summary_payload.py` → 无匹配 ✓

---

## 逐路径 Adversarial Failure Pass

### Source Fallback Regression

**检查项：是否存在代码路径仍把 `summary_text` 作为 assistant final answer fallback？**

逐文件走读 `summary_text` 在所有受影响 production 模块中的残留：

| 文件 | 残留 `summary_text` 用途 | 是否 assistant final answer 路径？ |
|---|---|---|
| `run_input.py:150,2282,2284,3200,3217` | Session Summary prompt 渲染 | 否 |
| `memory.py:76,510,517,530,1138,1704,1716,2353,2368` | Session Summary Memory 类型/物化/序列化 | 否 |
| `memory.py:1656,2912` | `_ref_summary_text` — evidence/user display_text fallback | 否 |
| `durable/memory.py:623,753,776` | Session Summary Memory snapshot 持久化 | 否 |
| `compaction_evidence.py` | 无 `summary_text` 残留 | — |

**结论：所有 `summary_text` 残留均属于 Session Summary Memory、evidence fallback 或 user input display_text fallback 路径。无一用于 assistant final answer continuity。**

### Import Boundary

- `terminal_summary_payload.py` — 纯 field reader，无 transaction/storage 依赖。依赖链：`JsonValue`（contracts）、`HostDurableError`（errors）。无 import cycle 风险。
- `_terminal_answer.py` — transaction-aware resolver。依赖 `durable.transaction`、`payload_resolution`、`terminal_summary_payload`。`durable.transaction` 和 `payload_resolution` 不从 `_terminal_answer` 或 `terminal_summary_payload` 导入。无循环依赖。
- 消费方均为 Host 内部模块，无 Host 外部 import。
- `_` 前缀命名符合 Python 私有模块约定，不在 `__init__.py` 暴露。

### Direct Projection Hydration

`_selected_assistant_item`（`memory.py:1616-1641`）只读 inline `final_answer`，不解析 terminal artifact。当前所有生产 caller 在调用 `project_conversation_memory_event` 前已通过 `_payload_with_assistant_final_answer` 完成 hydration：
- Durable projection 路径：`durable/memory.py:_memory_projection_event_from_view` → `_payload_with_assistant_final_answer` → `project_conversation_memory_event`
- Inline delta 路径：`run_input.py:_memory_projection_event_from_row` → `_payload_with_assistant_final_answer` → `project_conversation_memory_event`

若未来出现非 hydration caller，manifestation 为 assistant item 缺失（fail-safe），不会注入错误文本。

### `STRICT_ALLOW_EMPTY` → `STRICT_NON_EMPTY` 迁移

旧 code（`durable/memory.py`）在 early-return guard 使用 `STRICT_ALLOW_EMPTY`：空白 `final_answer` 被视为有效，阻止 terminal artifact lookup。新 code 使用 `STRICT_NON_EMPTY`：空白 `final_answer` 视为缺失，继续尝试 terminal artifact `content` hydration。符合 plan 决策 #2。

### Dead Code 物理删除完整性

已确认物理删除：
- `_successful_run_continuity_messages`（原 `run_input.py` ~3463 行）
- `_successful_run_message_pair`（原 `run_input.py` ~3510 行）
- `_continuity_message_from_event`（原 `run_input.py` ~3409 行）
- `assistant_summary_from_payload`（`terminal_summary_payload.py`）
- `PayloadSummaryTextPolicy` / `STRICT_ALLOW_EMPTY`（`terminal_summary_payload.py`）
- `_summary_text_field`（`terminal_summary_payload.py`）
- `_PAYLOAD_FIELD_SUMMARY` / `_PAYLOAD_FIELD_SUMMARY_TEXT`（`terminal_summary_payload.py`）
- `_PAYLOAD_FIELD_CONTENT`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST`（`run_input.py`、`durable/memory.py`）
- `_optional_str`（`durable/memory.py`）

grep 全部确认无残留。

### State Machine

本次变更不修改 Host 状态机、不新增 event type、不修改 terminal closeout 流程。`RUN_SUCCEEDED` payload 写入侧（`durable/run_transition.py`）未修改。只修改读取侧（memory projection + run input builder + compaction evidence）。

### Architecture / Overcoupling

- `terminal_summary_payload.py` 是纯 field reader → 职责收敛。
- `_terminal_answer.py` 是 transaction-aware resolver → 依赖方向正确（下层 durable → 上层 module）。
- `run_input.py` 和 `durable/memory.py` 各有独立的 `_payload_with_assistant_final_answer`，差异仅在一行 payload 提取方式（`row.payload` vs `event.payload`），属轻量重复，无 over-abstraction。

---

## Findings

未发现实质性问题。

本 reviewer 独立走读了全部 6 个 production 模块、5 个 test 文件、PR diff、control doc 和 README，并针对 6 条 hard constraint 逐条执行了 grep 验证、代码路径追踪和 adversarial failure pass。所有 hard constraint 均被验证满足。

前置 MiMo 和 DS code review、aggregate deepreview 均 verdict pass with 0 findings。Controller 裁决 accepted。本 PR review 独立复核后确认无遗漏的 blocking 或 new finding。

---

## Open Questions

无。

---

## Residual Risk

以下 residual risk 已在前置 review 中识别并记录，本 review 独立确认其为低风险项，不引入新的 active residual risk：

1. **Direct projection path 无 transaction 访问**（`memory.py:1616-1630`）：`_selected_assistant_item` 只读 inline `final_answer`，不解析 terminal artifact。所有当前生产 caller 在调用前已完成 hydration。若未来新增非 hydration caller，terminal artifact `content` 会丢失。Manifestation 为 assistant item 缺失（fail-safe），不会注入错误文本。

2. **`_payload_with_assistant_final_answer` 代码重复**（`run_input.py:3005-3036` 与 `durable/memory.py:213-243`）：两处逻辑完全相同，仅 payload 提取方式不同。当前差异仅一行，属轻量重复，不构成维护风险。若未来该逻辑继续增长，应考虑提取共享 helper。

3. **`_optional_descriptor_text` 的 strict error 路径无直接单元测试**（`_terminal_answer.py:69-87`）：`terminal_summary_ref` / `terminal_summary_digest` 为非字符串类型时抛出 `HostDurableError`。测试仅通过 `assistant_final_answer_continuity_text` 集成调用间接覆盖。风险极低 — descriptor 由 Host 写入，损坏概率极低。

4. **CI checks 未报告**：GitHub 对 `phaseflow/wu-cm-01-f04-closeout` branch 未返回 check 结果。Controller 已独立验证 `197 passed` + `pyright 0 errors`，覆盖范围与 CI 预期一致。此 gap 不阻止 draft PR pass，但建议在 merge 前确认 CI pipeline 对该 branch 正常触发。

---

## Verdict

**draft-PR-pass** — 0 blocking findings，0 non-blocking findings。

WU-CM-01-F03 实现忠实执行了 accepted plan 的全部 5 项决策与 5 个 slice。assistant final answer continuity 已完全收窄至 `RUN_SUCCEEDED.final_answer` 与 digest-checked terminal summary artifact `content`。`summary_text`、nested `summary`、裸 `RUN_SUCCEEDED.content`、payload ref、digest 与 event id 不再作为 assistant final answer fallback 来源。Session Summary Memory 仍只来自 accepted compact `session_summary`。旧 helper、旧 enum、`STRICT_ALLOW_EMPTY` 策略与 dead code 链已物理删除且 grep 确认无残留。PR body、control doc、README 与 artifacts 一致。
