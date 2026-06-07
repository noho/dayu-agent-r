# 聚合 Deepreview — WU-CM-01-F03 Assistant Final Answer Continuity Fidelity Closeout

## Scope

- Mode: current changes（aggregate deepreview）
- Branch: `phaseflow/wu-cm-01-f04-closeout`
- Base: `main`
- Work unit: WU-CM-01-F03
- Implementation commit: `a319edc8` host: narrow assistant final answer continuity
- Slice acceptance commit: `16a68ea4` phaseflow: record WU-CM-01-F03 slice acceptance
- Output file: `docs/reviews/wu-cm-01-f03-aggregate-deepreview-ds.md`
- Review timestamp: 20260606-221755

### Included scope

- `dayu/host/terminal_summary_payload.py` — payload 字段提取 helper contract
- `dayu/host/_terminal_answer.py` — transaction-aware continuity resolver
- `dayu/host/run_input.py` — inline delta `_payload_with_assistant_final_answer` 与 dead code 删除
- `dayu/host/durable/memory.py` — durable projection `_payload_with_assistant_final_answer`
- `dayu/host/memory.py` — `_selected_assistant_item` 与 `project_conversation_memory_event`
- `dayu/host/compaction_evidence.py` — `_assistant_history_materials`
- `dayu/host/README.md` — 稳定实现文档同步
- `tests/host/test_terminal_summary_payload.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_compact_material.py`

### Excluded scope

- WU-CM-01-F04 closeout 代码（仅检查与 F03 的交互风险）
- plan docs、plan review docs、control doc — 作为 context 阅读，不作为实现 review
- `docs/reviews/wu-cm-01-f03-implementation-codex.md` — 作为 implementation report 参考
- 前置 code review artifacts — 上下文输入，已纳入整合判断

### Parallel review coverage

无。本条 aggregate deepreview 由 AgentDS 单独执行，整合了前置 MiMo/DS code review 结论并独立复核全部代码路径。

### 已阅前置 artifacts

| Artifact | 角色 |
|---|---|
| `docs/reviews/wu-cm-01-f03-code-review-mimo.md` | 前置 code review（MiMo），verdict: pass, 0 findings |
| `docs/reviews/wu-cm-01-f03-code-review-ds.md` | 前置 code review（DS），verdict: pass, 0 findings |
| `docs/reviews/wu-cm-01-f03-code-review-controller-adjudication.md` | Controller 裁决，verdict: accepted |
| `docs/reviews/wu-cm-01-f03-implementation-codex.md` | Implementation report，verdict: ready |
| `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md` | 已接受 plan |

### F04 交互风险检查

WU-CM-01-F04 closeout 仅产生 `docs/reviews/wu-cm-01-f04-final-closeout-controller.md` 一个文档文件，不包含任何代码修改。与 F03 实现无交互风险。

---

## Hard Constraint 逐项验证

### 1. `final_answer` 或 digest-checked terminal summary artifact `content` 是唯一 assistant final answer continuity 来源

**每条 production 代码路径均已验证：**

| 调用路径 | 文件(行号) | helper | 输入 |
|---|---|---|---|
| assistant selected recent window | `memory.py:1625-1628` | `assistant_final_answer_text_from_run_payload`（只读 `final_answer`） | 已 hydrate transient payload |
| durable projection hydration | `durable/memory.py:224-253` | `assistant_final_answer_continuity_text`（`final_answer` → digest-checked `content`） | 原始 RUN payload + transaction |
| inline delta projection hydration | `run_input.py:3017-3036` | `assistant_final_answer_continuity_text`（同上） | 原始 RUN payload + transaction |
| compaction history material | `compaction_evidence.py:417-421` | `assistant_final_answer_continuity_text`（同上） | 原始 RUN payload + transaction |

所有路径均满足约束。无任何路径读取 `summary_text`、nested `summary`、裸 `RUN_SUCCEEDED.content`。

### 2. `summary_text` 和 nested `summary` 不是 assistant final answer fallback

**证据：**

- `terminal_summary_payload.py:26-39` `assistant_final_answer_text_from_run_payload` 只读 `_PAYLOAD_FIELD_FINAL_ANSWER = "final_answer"`。不含 `content`、`summary_text`、`summary`。
- `terminal_summary_payload.py:42-55` `terminal_summary_content_text_from_payload` 只读 `_PAYLOAD_FIELD_CONTENT = "content"`。不含 `summary_text`、`summary`。
- 旧的 `assistant_summary_from_payload()` 已物理删除，其 `final_answer → content → summary_text → nested summary` 搜索链不复存在。
- `test_run_payload_summary_fields_are_not_final_answer_sources`（`test_terminal_summary_payload.py:69-84`）直接断言 `content`/`summary_text`/nested `summary` 均不被读取。
- `test_terminal_summary_payload_summary_fields_are_not_content_sources`（`test_terminal_summary_payload.py:111-125`）断言 artifact 侧同样行为。

### 3. `RUN_SUCCEEDED.content`、payload ref、digest、event id 不是 assistant final answer fallback

**证据：**

- `_terminal_answer.py:32-33` docstring 明确："裸 `RUN_SUCCEEDED.content`、`summary_text` 或 nested `summary` 均不是 assistant final answer 来源"。
- `_terminal_answer.py:49-56` 只通过 `terminal_summary_ref` + `terminal_summary_digest` 两个 descriptor 解析 terminal artifact，两者缺失任一则返回 `None`。
- `_terminal_answer.py:63` 只调用 `terminal_summary_content_text_from_payload` 读 artifact `content`，不读取任何其他字段。
- `memory.py:1629-1630` `_selected_assistant_item` 无 text 时返回 `None`（无 `_ref_summary_text` fallback），`project_conversation_memory_event` 在 `None` 时跳过 item。
- `test_run_succeeded_summary_only_does_not_materialize_assistant_window`（`test_memory_projection.py:323-346`）与 `test_run_succeeded_payload_refs_do_not_materialize_assistant_window`（`test_memory_projection.py:349-365`）验证 summary-only 和 ref-only 均不生成 assistant item。

### 4. Session Summary Memory 只来自 accepted compact `session_summary`

**证据：**

- `memory.py:1690-1719` `_session_summary_from_accepted_event` 未修改，仍只从 `CONTEXT_COMPACTED.accepted_candidate.session_summary.summary_text` 读取。
- `memory.py:1712` 使用 `_PAYLOAD_FIELD_SUMMARY_TEXT = "summary_text"` 但上下文是 compact `session_summary` 嵌套路径，不是 `RUN_SUCCEEDED` payload。
- `test_accepted_compact_materializes_vnext_memory_sections`（`test_memory_projection.py:291-320`）验证 Session Summary 来自 compact。
- `test_run_succeeded_summary_only_does_not_materialize_assistant_window`（`test_memory_projection.py:323-346`）负向断言 `RUN_SUCCEEDED.summary_text` 不生成 session summary。

### 5. 无 compatibility alias/wrapper/re-export

**证据：**

- grep `assistant_summary_from_payload|PayloadSummaryTextPolicy` dayu + tests → **无匹配**。
- grep `STRICT_ALLOW_EMPTY|_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event` dayu + tests → **无匹配**。
- `terminal_summary_payload.py:__all__` 只导出 `PayloadTextReadPolicy`、`assistant_final_answer_text_from_run_payload`、`terminal_summary_content_text_from_payload`。
- `_terminal_answer.py:__all__` 只导出 `assistant_final_answer_continuity_text`。
- 两个模块均不在 `dayu/host/__init__.py` 中暴露。

### 6. README 只同步稳定实现文档

**证据：**

- `dayu/host/README.md:296` 替换为精确当前语义："terminal answer continuity 的稳定语义是：RunInputBuilder、memory projection 和 compaction evidence 只把 `RUN_SUCCEEDED.final_answer`，或经 `terminal_summary_ref` / `terminal_summary_digest` 校验后的 terminal summary artifact `content`，作为 assistant final answer / conclusion continuity"。
- 无过程状态、未来计划、旧术语残留。

---

## Controller Validation Baseline 复核

Controller 已执行并独立确认：

- `pytest tests/host/test_terminal_summary_payload.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_engine_ingest_mapping.py` → **197 passed**
- `pyright` → **0 errors, 0 warnings, 0 informations**
- grep old helper/enum/dead chain → **no matches**

本 aggregate reviewer 独立复核以上三条，结论一致。

---

## 逐路径 Adversarial Failure Pass

### Source Fallback Regression

**检查项：是否存在代码路径仍把 `summary_text` 作为 assistant final answer fallback？**

逐文件走读 `summary_text` 残留：

| 文件 | 残留 `summary_text` 行 | 用途 | 是否 assistant final answer 路径？ |
|---|---|---|---|
| `durable/memory.py:623,753,776` | `snapshot.session_summary_memory.summary_text` | Session Summary Memory snapshot 持久化 | 否 |
| `memory.py:76` | `_PAYLOAD_FIELD_SUMMARY_TEXT = "summary_text"` | 常量定义 | 否（仅用于 `_session_summary_from_accepted_event`） |
| `memory.py:510,517,530` | `SessionSummaryMemoryView.summary_text` 字段 | Session Summary Memory 类型定义 | 否 |
| `memory.py:1138,1704,1716` | session_summary 构造 | Session Summary 物化 | 否 |
| `memory.py:2353,2368` | snapshot JSON 序列化 | Session Summary 持久化 | 否 |
| `memory.py:1656` | `_ref_summary_text(event)` | Evidence item display_text fallback（`_selected_evidence_item`） | 否（evidence 路径） |
| `memory.py:2912` | `_ref_summary_text(event)` | User input display_text fallback（`_user_visible_text`） | 否（user 路径） |
| `run_input.py:150` | `_PAYLOAD_FIELD_SUMMARY_TEXT = "summary_text"` | 常量定义 | 否（仅用于 session summary 渲染） |
| `run_input.py:2282,2284` | `summary.summary_text` | Session Summary prompt 渲染 | 否 |
| `run_input.py:3200,3217` | `_optional_session_summary_text` | compact candidate session_summary 读取 | 否 |

**结论：所有 `summary_text` 残留均属于 Session Summary Memory 路径、evidence display_text fallback 路径或 user input display_text fallback 路径。无一用于 assistant final answer continuity。**

### Import Boundary

**检查项：`_terminal_answer.py` 是否为合规内部模块，无 import cycle，无公共暴露？**

- `_terminal_answer.py` 以 `_` 前缀命名，符合 Python 传统私有模块约定。
- 不在 `dayu/host/__init__.py` 中暴露。
- 导入链：`_terminal_answer → terminal_summary_payload`（纯 reader） + `durable.transaction`（底层核心） + `payload_resolution`（底层核心）。`terminal_summary_payload` 无 durable 依赖。`durable.transaction` 和 `payload_resolution` 不从 `_terminal_answer` 或 `terminal_summary_payload` 导入。无循环依赖。
- `__all__` 只导出单一 public function。
- 消费方仅限于 Host 内部：`run_input.py`、`durable/memory.py`、`compaction_evidence.py`。

**结论：`_terminal_answer.py` 是合理的内部模块，不是兼容 seam。**

### Direct Projection Hydration

**检查项：`_selected_assistant_item` 缺少 transaction 访问，是否导致 terminal artifact `content` 丢失？**

代码路径追踪：

1. **Durable projection 路径**：`durable/memory.py:_memory_projection_event_from_view` → `_payload_with_assistant_final_answer` 完成 hydration（terminal content → transient `final_answer`）→ `project_conversation_memory_event` → `_selected_assistant_item` 读取已 hydrated 的 `final_answer`。terminal content 不会丢失。

2. **Inline delta 路径**：`run_input.py:_memory_projection_event_from_row` → `_payload_with_assistant_final_answer` 完成 hydration → 同上。terminal content 不会丢失。

3. **直接 projection 路径（测试/非标准调用）**：若 caller 跳过 `_payload_with_assistant_final_answer` 直接调用 `project_conversation_memory_event`，`_selected_assistant_item` 只能读 inline `final_answer`，terminal artifact `content` 会丢失。但当前所有生产 caller 均已完成 prior hydration。

**结论：当前生产路径安全。已作为 residual risk 记录。**

### Test Coverage Gaps

**已覆盖：**

- final_answer 读取、空白 final_answer、disallowed summary fields
- terminal artifact content 读取、空白 content、disallowed summary fields
- strict vs lenient 类型校验、disallowed 字段不触发 strict error
- digest-checked resolver 端到端
- summary-only 不生成 assistant window
- ref/digest-only 不生成 assistant window
- durable projection hydration 端到端
- inline delta hydration 端到端
- compaction evidence terminal content collection
- compaction evidence summary-only ignore
- answer_material 不映射 session_summary
- Session Summary Memory 仍由 accepted compact 生产

**未覆盖（均为低风险项）：**

- `_optional_descriptor_text` 对非字符串 descriptor 的 strict error 路径在 `_terminal_answer.py:83-84` 直接定义，但测试仅通过 `assistant_final_answer_continuity_text` 的集成调用间接覆盖（依赖 `sqlite_payload_object` 内部行为），无直接单元测试。低风险 — descriptor 由 Host 写入，损坏概率极低。
- `terminal_summary_digest` 与 artifact 不匹配时的错误路径（`sqlite_payload_object` digest 校验失败）在 continuity resolver 层无专门测试。该行为由 `sqlite_payload_object` 自身保证，集成测试依赖其语义。低风险。

### Dead Code Physical Deletion

**已确认物理删除：**
- `_successful_run_continuity_messages`（run_input.py 原 ~3463 行附近）— 已删除
- `_successful_run_message_pair`（run_input.py 原 ~3510 行附近）— 已删除
- `_continuity_message_from_event`（run_input.py 原 ~3409 行附近）— 已删除
- `assistant_summary_from_payload`（terminal_summary_payload.py）— 已删除
- `PayloadSummaryTextPolicy` / `STRICT_ALLOW_EMPTY`（terminal_summary_payload.py）— 已删除
- `_summary_text_field`（terminal_summary_payload.py）— 已删除
- `_PAYLOAD_FIELD_SUMMARY` / `_PAYLOAD_FIELD_SUMMARY_TEXT`（terminal_summary_payload.py）— 已删除
- `_optional_str`（durable/memory.py）— 已删除

grep 全部确认无残留。

### Architecture / Overcoupling

**检查项：是否存在跨层耦合、反向依赖或模块职责越界？**

- `terminal_summary_payload.py` 是纯字段 reader，无 transaction、storage 依赖 → 职责收敛。
- `_terminal_answer.py` 是 transaction-aware resolver，依赖 `durable.transaction`、`payload_resolution`、`terminal_summary_payload` → 依赖方向正确（下层 durable → 上层 module）。
- `run_input.py` 和 `durable/memory.py` 各有独立的 `_payload_with_assistant_final_answer`，差异仅在一行 payload 提取方式。两处逻辑一致，属轻量重复，无 over-abstraction。

**结论：无过度耦合。**

### State Machine Check

本次变更不修改 Host 状态机、不新增 event type、不修改 terminal closeout 流程。`RUN_SUCCEEDED` payload 写入侧（`durable/run_transition.py`）未修改。只修改读取侧（memory projection + run input builder + compaction evidence）。

**结论：无状态机风险。**

---

## Findings

未发现实质性问题。

前置 MiMo 和 DS code review 均 verdict pass，0 findings。Controller 裁决 accepted。本 aggregate reviewer 独立走读全部代码路径和所有 hard constraint 验证点后，确认无遗漏的 blocking 或 new finding。

---

## Open Questions

无。

---

## Residual Risk

1. **Direct projection path 无 transaction 访问**（`memory.py:1616-1630`）：`_selected_assistant_item` 只读 inline `final_answer`，不解析 terminal artifact。虽然所有当前生产 caller 在调用 `project_conversation_memory_event` 前已完成 hydration（`_payload_with_assistant_final_answer`），但若未来新增非 hydration caller，terminal artifact `content` 会丢失。出现时 manifestation 为：assistant selected recent window 缺失而非注入错误文本（fail-safe）。建议在 `_selected_assistant_item` docstring 和 `project_conversation_memory_event` docstring 中加入 hydration 前置条件说明。

2. **`_payload_with_assistant_final_answer` 代码重复**（`run_input.py:3005-3036` 与 `durable/memory.py:210-253`）：两处逻辑完全相同，仅 payload 提取方式不同（`row.payload` vs `event.payload`）。当前上下文为两份 adapter 函数，不构成提取共享 helper 的必要理由（需要参数化不同的 input type）。若未来该逻辑进一步增长，应重新评估提取。

3. **`_optional_descriptor_text` 的 strict error 路径无直接单元测试**（`_terminal_answer.py:69-87`）：`terminal_summary_ref` / `terminal_summary_digest` 为非字符串类型时抛出 `HostDurableError`，测试仅通过 `assistant_final_answer_continuity_text` 集成调用间接覆盖。该路径依赖 `sqlite_payload_object` 的形参 digest 校验，风险极低但覆盖率反馈不精细。

---

## Verdict

**pass** — 0 blocking findings，0 non-blocking findings。

本 aggregate deepreview 独立复核了 WU-CM-01-F03 全部 6 条 hard constraint、完整 production 代码路径、全部 adversarial failure surface（source fallback regression、import boundary、direct projection hydration、test gaps、dead code deletion、architecture/overcoupling、state machine），并整合了前置 MiMo/DS code review 与 Controller 裁决。所有 hard constraint 均被验证满足，controller validation baseline（197 tests, pyright 0 errors, grep clean）经独立复核确认。F04 closeout 无代码修改，与 F03 无交互风险。

Residual risk 为已知项，均为低风险、fail-safe 窗口，已在前置 review 中识别并在本文档中重述。无需 fix gate。
