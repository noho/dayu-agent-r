# WU-CM-01 Plan Reslice Re-Review - AgentMiMo

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | plan reslice re-review |
| agent | AgentMiMo |
| branch | `phaseflow/wu-cm-01` |
| design source | `docs/host/design.md` 第 24 章 / 第 25 章 |
| control source | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| implementation blocker | `docs/reviews/wu-cm-01-implementation-codex.md` |
| reslice fix report | `docs/reviews/wu-cm-01-plan-reslice-fix-codex.md` |
| artifact | `docs/reviews/wu-cm-01-plan-reslice-rereview-mimo.md` |

## Review Scope

复审 plan 是否已从概念域 Slice 1-5 改写为 pyright-clean、可编译、可验证的纵向闭环 Slice A-E；确认不再允许中间全量 pyright 失败；确认每个 slice 有 allowed files/modules、旧路径保留/删除边界、禁止 compatibility wrapper/re-export/lazy import seam、测试命令、pyright 命令、退出信号和 residual risks；确认 issue-80 映射、continuity/minimum preserve、vNext schema、material mapping、quality checker 规则没有丢失。

## Assumptions Tested

1. Slice A-E 是否构成纵向闭环，而非概念域拆分。
2. 每个 slice 是否要求 pyright-clean，不再允许中间全量失败。
3. 每个 slice 的 allowed files / modules 是否明确且可验证。
4. 旧路径保留 / 删除边界是否明确。
5. 禁止 compatibility wrapper / re-export / lazy import seam 是否在每个 slice 中显式约束。
6. 测试命令、pyright 命令、退出信号、residual risks 是否完整。
7. Issue-80 / design 24.7 映射表是否完整保留。
8. continuity / minimum preserve 到 reference continuity 的迁移规则是否保留。
9. vNext compact I/O schema、snapshot schema 是否与 design 24.3 / 24.4 一致。
10. 旧 material block kind 到 vNext section 的映射规则是否保留。
11. quality checker source label / provenance / whole-candidate repair 规则是否保留。
12. 实施 blocker 报告的建议是否被完整采纳。

## Findings

### 01-已修复-[严重]-概念域 Slice 改写为纵向闭环 Slice

- **位置**: Implementation Slices 章节
- **问题类型**: 不可直接实施
- **当前写法**: 已将原概念域 Slice 1-5 改写为 Slice A (Compact Contract Closure)、Slice B (Compact Operation And Event Closure)、Slice C (Memory Durable And Projection Closure)、Slice D (Prompt And Fallback Closure)、Slice E (Public Smoke And Docs Closure)。
- **反例/失败场景**: 原 Slice 1-5 按"类型、持久化、parser、operation、prompt"概念域拆分，导致必须同源切换的契约、持久化、projection、parser、accept barrier、operation state 与 RunInputBuilder 被拆到不同 slice，任何局部删除旧 contract 都会让后续未迁移模块产生类型错误。
- **为什么有问题**: 与 AGENTS 的修改后验证要求和用户本 gate 明确要求的每 slice pyright-clean 冲突。
- **直接证据**: implementation blocker `docs/reviews/wu-cm-01-implementation-codex.md` 的 Direct Evidence 章节列出了 27,011 行代码、8 个核心生产文件的旧 contract 贯穿证据。
- **影响**: implementation agent 无法在一个上下文中形成可验证闭环。
- **建议改法和验证点**: 已按 blocker 建议改写为纵向闭环 Slice A-E。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 严重。

### 02-已修复-[严重]-中间全量 pyright 失败

- **位置**: Slice Verification Boundary 章节
- **问题类型**: 不可直接实施
- **当前写法**: Slice Verification Boundary 明确要求每个 slice 结束时 `python -m pyright dayu/ tests/ utils/` 不得新增或扩散错误；plan 不再残留允许 Slice 1-4 中间全量 pyright 失败的表述。
- **反例/失败场景**: 若允许中间全量 pyright 失败，implementation agent 无法在每个 slice 独立验证类型正确性。
- **为什么有问题**: 与 AGENTS 的 pyright 硬约束和用户明确要求冲突。
- **直接证据**: reslice fix report 验证 `rg -n "Slice [1-6]|pyright 失败|不承诺|最早必须恢复|全量 pyright 失败"` 无命中。
- **影响**: 类型错误在 slice 间累积，review 无法独立验证。
- **建议改法和验证点**: 已在 Slice Verification Boundary 和每个 slice 的 pyright 命令中明确。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 严重。

### 03-已修复-[高]-每个 slice 缺少 allowed files / modules

- **位置**: Slice A-E 各自的 allowed files/modules 章节
- **问题类型**: 不可直接实施
- **当前写法**: 每个 slice 均列出具体的 allowed files/modules，并标注条件性允许（如 `context_policy.py` 仅当 vNext compact policy cap/floor 需要同源默认值）。
- **反例/失败场景**: implementation agent 不知道哪些文件可以修改，可能越界修改或遗漏必需文件。
- **为什么有问题**: 无法形成可验证的实施边界。
- **直接证据**: Slice A 列出 9 个文件、Slice B 列出 16 个文件、Slice C 列出 10 个文件、Slice D 列出 9 个文件、Slice E 列出 7 个文件/目录。
- **影响**: 实施 agent 跑偏。
- **建议改法和验证点**: 已逐 slice 补齐。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。

### 04-已修复-[高]-旧路径保留/删除边界缺失

- **位置**: Slice A-E 各自的"旧路径保留/删除边界"章节
- **问题类型**: 架构边界
- **当前写法**: 每个 slice 均有明确的旧路径保留/删除边界，例如 Slice A 明确旧 `stable_input`、`history_input`、`evidence_input`、旧 `CompactionCandidate` 可为尚未切换的 production operation 原样存在到 Slice B。
- **反例/失败场景**: 若旧路径边界不清，implementation agent 可能过早删除仍被后续 slice 使用的旧 contract，或过晚删除导致新旧并存。
- **为什么有问题**: 违反"未切换的旧路径可以原样存在到它的 owner slice"原则。
- **直接证据**: 每个 slice 均有详细的保留/删除边界说明。
- **影响**: 状态不一致、类型错误。
- **建议改法和验证点**: 已逐 slice 补齐。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。

### 05-已修复-[高]-禁止 compatibility wrapper / re-export / lazy import seam 缺失

- **位置**: Slice A-E 各自的"不得引入"章节
- **问题类型**: 最佳实践偏离
- **当前写法**: 每个 slice 均有明确的"不得引入"章节，列出禁止的 compatibility wrapper、re-export、lazy import seam、`hasattr`/`getattr` 探测、`Any`、untyped payload 等。
- **反例/失败场景**: implementation agent 可能为了保持 pyright 通过而新增兼容层。
- **为什么有问题**: 违反 AGENTS 禁止兼容 wrapper 与旧字段 re-export 的约束。
- **直接证据**: Slice A 不得引入列表包含 12 项禁止项。
- **影响**: 旧新 contract 并存，语义污染。
- **建议改法和验证点**: 已逐 slice 补齐。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。

### 06-已修复-[中]-测试命令、pyright 命令、退出信号、residual risks 缺失

- **位置**: Slice A-E 各自的测试命令、pyright 命令、退出信号、residual risks 章节
- **问题类型**: 不可直接实施
- **当前写法**: 每个 slice 均有完整的测试命令（含 `source .venv/bin/activate`）、`python -m pyright dayu/ tests/ utils/` 命令、明确的退出信号和 residual risks 表。
- **反例/失败场景**: implementation agent 不知道如何验证、何时停止。
- **为什么有问题**: 无法形成可验证的实施闭环。
- **直接证据**: 每个 slice 均有上述四个要素。
- **影响**: 验证不可靠。
- **建议改法和验证点**: 已逐 slice 补齐。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。

### 07-已修复-[高]-Issue-80 / design 24.7 映射表丢失

- **位置**: Issue-80 / Design 24.7 Evaluation Mapping 章节
- **问题类型**: 契约缺失
- **当前写法**: 完整保留 16 个评测维度映射表，slice 列已从旧数字更新为 A-E。
- **反例/失败场景**: 若映射表丢失，WU-CM-01 的验收标准无法对齐 GitHub Issue #80。
- **为什么有问题**: 与 control doc 的验收信号要求冲突。
- **直接证据**: 映射表包含 empty compacted view、non-empty compacted view、post-compact delta、compact boundary、protected recent floor、deterministic bounded projection、provider context length fallback、invalid/missing/stale source label、schema invalid、provenance mismatch、partial candidate invalid、fallback 不生成高阶语义、compact roll-forward 等 13 个 current scope covered 项，以及 3 个 deferred-with-owner 项和 1 个 explicit non-goal 项。
- **影响**: 验收标准缺失。
- **建议改法和验证点**: 已保留并更新 slice 列。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。

### 08-已修复-[高]-continuity / minimum preserve 迁移规则丢失

- **位置**: Slice A 的"旧路径保留/删除边界"章节
- **问题类型**: 契约缺失
- **当前写法**: 明确 `MinimumPreserveReason.NEEDED_FOR_RECENT_REFERENCE` / `NEEDED_FOR_ORDERED_ITEM_REFERENCE` / `NEEDED_FOR_LOCAL_FOLLOWUP` 不做兼容读取，其业务语义在 vNext 中重新映射为 `ReferenceContinuityCandidate.reason` 的 `local_reference` / `ordinal_reference` / `ellipsis_recovery` / `recent_state`。
- **反例/失败场景**: 若迁移规则丢失，旧 minimum preserve 语义无法正确映射到 vNext reference continuity。
- **为什么有问题**: 与 design 24.5 的 Trace Memory reference continuity 定义冲突。
- **直接证据**: design 24.5 定义 `ReferenceContinuityCandidate.reason` 为 `local_reference` | `ordinal_reference` | `ellipsis_recovery` | `recent_state`。
- **影响**: 语义断裂。
- **建议改法和验证点**: 已在 Slice A 保留。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。

### 09-已修复-[高]-vNext schema 定义丢失

- **位置**: Slice A (compact I/O)、Slice C (snapshot) 的实现边界章节
- **问题类型**: 契约缺失
- **当前写法**:
  - Slice A 固定 `ConversationCompactInputVNext` 字段为 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`、`instruction`；`ConversationCompactOutputVNext` 字段为 `session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`；`schema_version="conversation_compact_output_v1"`。
  - Slice C 固定 `ConversationMemorySnapshotVNext` 字段为 `trace_memory`、`evidence_fact_memory`、`session_summary_memory`、`answer_anchor_memory`、`forward_intent_memory`、`diagnostics`。
- **反例/失败场景**: 若 schema 定义丢失，implementation agent 可能从旧代码推断字段。
- **为什么有问题**: 与 design 24.3 / 24.4 冲突。
- **直接证据**: design 24.3 和 24.4 的 schema 定义与 plan 一致。
- **影响**: 类型错误、语义不一致。
- **建议改法和验证点**: 已在 Slice A 和 Slice C 保留。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。

### 10-已修复-[高]-旧 material block kind 到 vNext section 映射丢失

- **位置**: Slice A 的"旧路径保留/删除边界"章节
- **问题类型**: 契约缺失
- **当前写法**: 完整映射表：`PINNED_STATE` / `WORKING_ASSUMPTION` 删除；`EVIDENCE_BACKED_FACT` 进入 `evidence_backed_facts`；`OPEN_QUESTION` 由 forward intent 承接；`RAW_USER_TURN` 进入 `trace_material`；`RAW_ASSISTANT_TURN` 在 trace/answer 二选一；`EPISODE_SUMMARY` 由 session summary 承接；`ACCEPTED_TOOL_EVIDENCE` 进入 `evidence_material`；`CURRENT_INPUT_ANCHOR` 不可引用。
- **反例/失败场景**: 若映射丢失，旧 material 无法正确迁移到 vNext section。
- **为什么有问题**: 实施 agent 需要明确的迁移规则。
- **直接证据**: 映射表完整且与 design 24.3 / 24.5 一致。
- **影响**: 迁移错误。
- **建议改法和验证点**: 已在 Slice A 保留。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。

### 11-已修复-[高]-quality checker 规则丢失

- **位置**: Slice A 和 Slice B 的实现边界章节
- **问题类型**: 契约缺失
- **当前写法**:
  - Slice A: parser / contract validator 必须 fail closed；source label 允许集合、current input anchor not citable、cross-section label、stale label 均有说明。
  - Slice B: source label allowlist 按 section 校验；quality result 记录 vNext validation issues；repair attempt 必须 whole-candidate re-proposal。
- **反例/失败场景**: 若 quality checker 规则丢失，accept barrier 无法正确校验 candidate。
- **为什么有问题**: 与 design 25 的 Context Governance 要求冲突。
- **直接证据**: design 25 明确 source label allowlist、provenance、whole-candidate repair 规则。
- **影响**: 非法 candidate 被接受。
- **建议改法和验证点**: 已在 Slice A 和 Slice B 保留。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 高。

## Open Questions

当前没有 blocking open questions。

plan 明确要求：若 implementation 在 Slice A、B 或 C 发现第 24/25 章无法唯一裁决 public contract、durable schema、EventLog payload 或状态机语义，应停止 implementation，回到 design source / plan 修正，而不是在生产代码里新增兼容路径。

## Residual Risks

| 风险 | 分类 | Owner / Destination | 说明 |
|---|---|---|---|
| Conversation Memory vNext 尚未实现 | covered by later approved slice | WU-CM-01 implementation | 本 gate 只做 plan re-review；后续必须按 Slice A-E 实施并逐 slice 验证。 |
| 完整 Conversation Memory eval benchmark | deferred-with-owner | WU-CM-10 / GitHub Issue #80 | plan 保留可断言入口，不实现完整 eval runner。 |
| Cross-session User Profile Memory | deferred-with-owner | WU-CM-11 / GitHub Issue #115 | WU-CM-01 只固定不混入 session memory 的边界。 |
| Deep historical recall / semantic search | deferred-with-owner | GitHub Issue #39 | 当前 vNext session memory 不实现 recall / search / reranker。 |
| Provider-specific tokenizer adapter | deferred-with-owner | 后续 Context Governance 精确预算 work unit | WU-CM-01 保持 deterministic bounded policy。 |
| Fins fact grounding integration | deferred-with-owner | Fins integration work unit | memory snapshot 不替代 accepted evidence / artifacts / Fins storage truth。 |

## Verification Summary

| 验证项 | 状态 |
|---|---|
| 概念域 Slice 1-5 -> 纵向闭环 Slice A-E | fixed |
| 不再允许中间全量 pyright 失败 | fixed |
| 每个 slice 有 allowed files/modules | fixed |
| 旧路径保留/删除边界 | fixed |
| 禁止 compatibility wrapper/re-export/lazy import seam | fixed |
| 测试命令 | fixed |
| pyright 命令 | fixed |
| 退出信号 | fixed |
| residual risks | fixed |
| issue-80 映射表 | fixed |
| continuity/minimum preserve 迁移规则 | fixed |
| vNext compact I/O schema | fixed |
| vNext snapshot schema | fixed |
| 旧 material block kind 到 vNext section 映射 | fixed |
| quality checker source label / provenance / repair 规则 | fixed |
| 实施 blocker 建议完整采纳 | fixed |

## Cross-check With Design Source

已将 plan 的 Slice A-E 与 `docs/host/design.md` 第 24 章 (Conversation Memory) 和第 25 章 (Context Governance) 逐项核对：

- **24.3 vNext Compact I/O Contract**: plan Slice A 的 `ConversationCompactInputVNext` 和 `ConversationCompactOutputVNext` 字段与 design 24.3 一致。
- **24.4 Snapshot Typed Schema**: plan Slice C 的 `ConversationMemorySnapshotVNext` 字段与 design 24.4 一致。
- **24.5 五类 Session Semantic Memory**: plan 的五类 memory (Trace、Evidence/Fact、Session Summary、Answer Anchor、Forward Intent) 与 design 24.5 一致。
- **24.6 Prompt Assembly**: plan Slice D 的 section 顺序与 design 24.6 一致。
- **24.7 测试与评测边界**: plan 的 Issue-80 映射表覆盖 design 24.7 要求的所有可断言场景。
- **25. Context Governance**: plan Slice B 的 quality checker、source label allowlist、whole-candidate repair、reactive multi-pass compact 与 design 25 一致。
- **candidate schema**: plan Slice A 的 candidate 子结构 (`SessionSummaryCandidate`、`EvidenceBackedFactCandidate`、`AnswerAnchorCandidate`、`ForwardIntentCandidate`、`ReferenceContinuityCandidate`、`CompactCandidateDiagnostic`) 与 design 24.3 一致。
- **current_input_anchor not citable**: plan Slice A 明确 `current_input_anchor` readable but not citable，与 design 24.3 一致。
- **rollback compact semantics**: plan Slice B 明确 fallback 不是 compact success，不写 `CONTEXT_COMPACTED`，不 materialize memory snapshot，与 design 25 一致。

## Final Plan Review Conclusion

**verdict: pass**

plan 已从概念域 Slice 1-5 成功改写为 pyright-clean、可编译、可验证的纵向闭环 Slice A-E。所有 16 项验证项均标记为 fixed。无 blocking open questions。Issue-80 映射、continuity/minimum preserve、vNext schema、material mapping、quality checker 规则均完整保留。实施 blocker 报告的建议已被完整采纳。plan 已 code-generation-ready，可交由 implementation agent 按 Slice A-E 顺序逐 slice 实施。
