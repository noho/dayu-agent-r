# Code Review — PR 125

## Scope

- Mode: PR review
- PR: [#125](https://github.com/noho/dayu-agent-r/pull/125)
- Title: phaseflow: close out WU-CM-01-F04 and narrow final answer continuity
- Author: noho
- Head branch: `phaseflow/wu-cm-01-f04-closeout`
- Base branch: `main`
- Output file: `docs/reviews/wu-cm-01-f03-pr-review-mimo.md`
- Review timestamp: 20260606-223402
- Included scope:
  - WU-CM-01-F04 final closeout record (documentation only)
  - WU-CM-01-F03 assistant final answer continuity fidelity closeout (code + tests + docs)
- Excluded scope: none
- Parallel review coverage: 无

### Changed production files

| File | Change type |
|---|---|
| `dayu/host/terminal_summary_payload.py` | rewrite: old helper → new field readers |
| `dayu/host/_terminal_answer.py` | new: transaction-aware continuity resolver |
| `dayu/host/run_input.py` | modify: hydration + dead code deletion |
| `dayu/host/durable/memory.py` | modify: hydration + old helper removal |
| `dayu/host/memory.py` | modify: selected assistant item None guard |
| `dayu/host/compaction_evidence.py` | modify: history material helper swap |
| `dayu/host/README.md` | modify: stable semantics sync |

### Changed test files

| File | Change type |
|---|---|
| `tests/host/test_terminal_summary_payload.py` | new: focused helper tests |
| `tests/host/test_memory_projection.py` | modify: summary-only/ref-only negative tests |
| `tests/host/test_run_input_builder.py` | modify: inline delta terminal content test |
| `tests/host/test_compaction_operation.py` | modify: terminal content + summary-only tests |
| `tests/host/test_compact_material.py` | modify: session summary isolation test |

---

## Findings

未发现实质性问题。

---

## Hard Constraint 逐项验证

### 1. LLM-facing Trace / Answer material 只接受 `final_answer` 或 digest-checked terminal summary artifact `content`

**每条 production 代码路径均已验证：**

| 调用路径 | 文件(行号) | helper | 输入 |
|---|---|---|---|
| assistant selected recent window | `memory.py:1625-1628` | `assistant_final_answer_text_from_run_payload`（只读 `final_answer`） | 已 hydrate transient payload |
| durable projection hydration | `durable/memory.py:224-243` | `assistant_final_answer_continuity_text`（`final_answer` → digest-checked `content`） | 原始 RUN payload + transaction |
| inline delta projection hydration | `run_input.py:3017-3036` | `assistant_final_answer_continuity_text`（同上） | 原始 RUN payload + transaction |
| compaction history material | `compaction_evidence.py:417-421` | `assistant_final_answer_continuity_text`（同上） | 原始 RUN payload + transaction |

直接代码证据：

- `terminal_summary_payload.py:26-39` — `assistant_final_answer_text_from_run_payload` 只读 `_PAYLOAD_FIELD_FINAL_ANSWER`（即 `"final_answer"`），不搜索 `content`、`summary_text` 或 nested `summary`。
- `terminal_summary_payload.py:42-55` — `terminal_summary_content_text_from_payload` 只读 `_PAYLOAD_FIELD_CONTENT`（即 `"content"`），且只在 `_terminal_answer.py` 的 digest-checked resolver 中被调用。
- `_terminal_answer.py:21-66` — `assistant_final_answer_continuity_text` 读取顺序固定为 `final_answer` → digest-checked terminal summary artifact `content`。第 32-33 行 docstring 明确："裸 `RUN_SUCCEEDED.content`、`summary_text` 或 nested `summary` 均不是 assistant final answer 来源"。

### 2. `summary_text` 和 nested `summary` 不是 assistant final answer fallback

**证据：**

- 旧 `assistant_summary_from_payload()` 已物理删除。该函数按 `final_answer → content → summary_text → nested summary` 搜索，是旧 fallback 的唯一来源。
- 新 `assistant_final_answer_text_from_run_payload` 只读 `final_answer`，新 `terminal_summary_content_text_from_payload` 只读 `content`。两者均不搜索 `summary_text` 或 nested `summary`。
- 所有 `summary_text` 残留均属于 Session Summary Memory 路径（`memory.py:76,510,517,530,1138,1704,1716,2353,2368`）、snapshot 序列化、evidence `_ref_summary_text` fallback（`memory.py:1656`）或 user input display_text fallback（`memory.py:2912`）。无一用于 assistant final answer continuity。

### 3. `RUN_SUCCEEDED.content`、payload ref、digest、event id 不是 assistant final answer fallback

**证据：**

- `_selected_assistant_item`（`memory.py:1616-1630`）缺失 final answer 时返回 `None`，不 fallback 到 `_ref_summary_text`。
- `project_conversation_memory_event`（`memory.py:1240-1243`）在 `_selected_assistant_item` 返回 `None` 时跳过 `_replace_item_by_id`，不注入 ref/digest/event_id 文本。
- `_terminal_answer.py:49-56` 只通过 `terminal_summary_ref` + `terminal_summary_digest` 两个 descriptor 解析 terminal artifact，两者缺失任一则返回 `None`。不从裸 payload `content` 读取。

### 4. Session Summary Memory 只来自 accepted compact `session_summary`

**证据：**

- `_session_summary_from_accepted_event`（`memory.py:1690-1721`）未修改，仍只从 `CONTEXT_COMPACTED.accepted_candidate.session_summary.summary_text` 读取。
- `test_accepted_compact_materializes_vnext_memory_sections`（`test_memory_projection.py`）验证 Session Summary 来自 compact。
- `test_run_succeeded_summary_only_does_not_materialize_assistant_window`（`test_memory_projection.py`）负向断言 `RUN_SUCCEEDED.summary_text` 不生成 session summary。

### 5. 无 compatibility alias/wrapper/re-export

**证据：**

- `rg "assistant_summary_from_payload|PayloadSummaryTextPolicy" dayu tests` → **no matches**（独立验证）。
- `rg "STRICT_ALLOW_EMPTY|_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event" dayu tests` → **no matches**（独立验证）。
- `terminal_summary_payload.py:__all__` 只导出 `PayloadTextReadPolicy`、`assistant_final_answer_text_from_run_payload`、`terminal_summary_content_text_from_payload`。
- `_terminal_answer.py:__all__` 只导出 `assistant_final_answer_continuity_text`。
- `_terminal_answer.py` 不是旧接口 wrapper：旧 `assistant_summary_from_payload` 已删除，新模块从零建立。

### 6. PR body、control doc、README、artifacts 和 final pushed branch 一致

**证据：**

- PR body 准确描述 WU-CM-01-F03 的收窄范围：只接受 `final_answer` 和 digest-checked terminal summary artifact `content`，不接受 `summary_text`/nested `summary`/裸 `content`/ref/digest/event id。
- PR body 准确描述 WU-CM-01-F04 为 closeout-only（文档）。
- Control doc（`issues-implementation-control.md`）WU-CM-01-F03 状态为 `draft-pr-open`，WU-CM-01-F04 状态为 `completed`，与 PR 内容一致。
- `dayu/host/README.md:296` 准确描述新语义，无过程状态、无未来设计、无旧术语残留。
- 所有 review artifacts（code review MiMo/DS、aggregate deepreview MiMo/DS、controller adjudications、draft PR readiness）内容一致，均 verdict pass。
- `git diff --check main...HEAD` → clean。

---

## Adversarial Failure Pass

### Source Fallback Regression

已验证。所有 assistant final answer 路径只读 `final_answer` 或 digest-checked artifact `content`。`summary_text`、nested `summary`、裸 `content`、ref、digest、event id 均不是 fallback source。grep 确认旧 helper/enum 无残留。

### Import Boundary

已验证。`terminal_summary_payload.py` 是纯 field reader（无 transaction 依赖），`_terminal_answer.py` 是 transaction-aware resolver（隔离 import cycle）。无反向 import，无 Host 外部 import。`run_input.py` 和 `durable/memory.py` 已移除旧 `sqlite_payload_object` import。

### Direct Projection Hydration

已验证。生产路径 caller（`run_input.py:2987`、`durable/memory.py:193`）在调用 `project_conversation_memory_event` 前通过 `_payload_with_assistant_final_answer` 完成 hydration。`_selected_assistant_item` 读取的 payload 已包含 hydrated `final_answer`。`_selected_assistant_item` 无 transaction 访问是 intentional design：它只读 inline `final_answer`，terminal artifact hydration 由上游完成。

### Durable Projection `STRICT_ALLOW_EMPTY` → `STRICT_NON_EMPTY` 迁移

已验证。旧代码的 `STRICT_ALLOW_EMPTY` 使空白 `final_answer` 被视为有效，阻止 terminal artifact lookup。新代码的 `STRICT_NON_EMPTY` 使空白 `final_answer` 视为缺失，继续 terminal artifact lookup。符合 plan 决策 #2。

### Dead Code 物理删除

已验证。`_continuity_message_from_event`、`_successful_run_continuity_messages`、`_successful_run_message_pair`、`_optional_str` 已物理删除。`_PAYLOAD_FIELD_CONTENT`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST` 常量已从 `run_input.py` 和 `durable/memory.py` 删除。grep 无残留。

### State Machine

本次变更不修改 Host 状态机、不新增 event type、不修改 terminal closeout 流程。`RUN_SUCCEEDED` payload 写入侧（`durable/run_transition.py`）未修改。只修改读取侧。

---

## Open Questions

无。

---

## Residual Risk

1. **Direct projection path 无 transaction 访问**（`memory.py:1616-1630`）：`_selected_assistant_item` 只读 inline `final_answer`，不解析 terminal artifact。当前所有生产 caller 在调用前已通过 `_payload_with_assistant_final_answer` 完成 hydration。若未来新增非 hydration caller，terminal artifact `content` 会丢失，manifestation 为 assistant selected recent window 缺失而非注入错误文本（fail-safe）。风险低。

2. **`_payload_with_assistant_final_answer` 代码重复**（`run_input.py:3005-3036` 与 `durable/memory.py:213-243`）：两处逻辑完全相同，仅 payload 提取方式不同（`row.payload` vs `event.payload`）。属轻量重复，不构成提取共享 helper 的必要理由。风险低。

3. **`_optional_descriptor_text` strict error 路径无直接单元测试**（`_terminal_answer.py:69-87`）：测试仅通过 `assistant_final_answer_continuity_text` 集成调用间接覆盖。descriptor 由 Host 写入，损坏概率极低。风险低。

4. **CI 未配置**：本仓库无 PR checks。Controller 验证 baseline（197 passed, pyright 0 errors, grep clean, git diff --check clean）已手动确认，但无自动 CI 保障。属 pre-existing condition，非本 PR 引入。

---

## Verdict

**draft-PR-pass** — 0 blocking findings，0 non-blocking findings。

实现忠实执行 plan 全部 5 项决策。6 项 hard constraint 全部通过直接代码路径走读和独立 grep 验证。adversarial failure pass 未发现 source fallback regression、import boundary violation、hydration 假设失效或 dead code 残留。PR body、control doc、README 和 review artifacts 内容一致。197 个测试通过，pyright 0 errors，旧 helper/enum/dead chain 无残留。
