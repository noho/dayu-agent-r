# WU-CM-01 Plan Review — AgentMiMo

## Review Metadata

| 项目 | 值 |
|---|---|
| review timestamp | 2026-06-04T09:56:55+08:00 |
| reviewer | AgentMiMo |
| reviewed target | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| scope | WU-CM-01 Conversation Memory overall optimization plan gate |
| design source | `docs/host/design.md` 第 24 章 Conversation Memory、第 25 章 Context Governance |
| control source | `docs/host/issues-implementation-control.md` WU-CM-01 / WU-CM-02 / WU-CM-03 / WU-CM-04 / WU-CM-10 / WU-CM-11 |
| current gate | plan review |

## Review Posture

本 review 从第一性原理出发，adversarial 挑战 plan 是否 code-generation-ready。默认假设 plan 至少有一个重要问题，直到证据证明它足够可靠。

## Reviewed Files

- `docs/host/wu-cm-01-conversation-memory-plan.md`（plan artifact）
- `docs/host/design.md` 第 24、25 章（design source）
- `docs/host/issues-implementation-control.md`（control source）
- `dayu/host/memory.py`（直接证据验证）
- `dayu/host/compaction.py`（直接证据验证）
- `dayu/host/llm_compaction.py`（直接证据验证）
- `dayu/host/context_governance.py`（直接证据验证）
- `dayu/host/compact_material.py`（直接证据验证）
- `dayu/host/run_input.py`（直接证据验证）
- `dayu/host/durable/memory.py`（直接证据验证）

## Assumptions Tested

1. plan 的 direct code evidence 是否准确 — **全部确认**（详见下方 evidence audit）
2. plan 是否严格对齐 design_doc 第 24 / 25 章 — **基本对齐，存在 3 处具体缺口**
3. plan 是否遵守 control_doc 的 WU-CM-01 scope / 非目标 / 验收信号 — **遵守**
4. slice sequencing 是否合理 — **合理，但存在跨 slice 依赖风险**
5. schema / public contract 变更边界是否清晰 — **基本清晰，存在 1 处迁移路径缺口**
6. 不保留 working_assumptions / pinned_state 兼容 wrapper — **明确**
7. User Profile deferred owner — **明确**
8. issue-80 eval 映射 — **合理 deferred，但 plan 内可提前给出初步映射**

## Direct Code Evidence Audit

plan 声称的 8 项直接代码证据已通过 grep / read 验证：

| # | 声称 | 验证结果 |
|---|------|----------|
| 1 | `MemoryProjectionPolicy` 仍有 `max_working_assumptions`、`recent_raw_turns_floor`、`history_pool_*`、`stable_layer_*` | 确认：line 652-686 |
| 1 | `ConversationMemorySnapshot` 仍包含 `pinned_state`、`working_assumptions`、`conversation_continuity` | 确认：line 813-837 |
| 2 | `WorkingAssumptionView`、`PinnedStateView`、`MemoryIncludedReason.WORKING_ASSUMPTION`、`ConversationContinuityKind.MINIMUM_PRESERVE_ITEM` 存在 | 确认：line 177, 199, 359, 450 |
| 3 | `CompactMaterialPack` 顶层字段为 `stable_input`、`history_input`、`evidence_input` | 确认：compaction.py line 622-637 |
| 4 | LLM parser 解析为 `episode_summary_candidate`、`pinned_state_patch_candidate` 等旧 candidate | 确认：llm_compaction.py line 92-101, 400-416 |
| 5 | quality checker 围绕 pinned patch、minimum preserve、open questions retained | 确认：context_governance.py line 27-76 |
| 6 | `_stable_blocks_from_snapshot()` 渲染 `working_assumption=` | 确认：compact_material.py line 1324-1428 |
| 7 | memory render header 为旧 stable block headers | 确认：run_input.py line 141-148 |
| 8 | durable memory 仍写 `working_assumptions` item | 确认：durable/memory.py line 634-651 |
| 8 | durable memory 仍写旧 continuity item kind | 部分确认：旧 `verified_fact` 已被主动 reject（line 967-969），当前 `MINIMUM_PRESERVE_ITEM` 仍被写入 |

**结论**：plan 的 direct code evidence 准确、可验证。第 8 项的细微差别不影响 plan 动机成立性判断。

## Findings

### F001-未修复-高-MINIMUM_PRESERVE_ITEM 到 ReferenceContinuityItem 迁移路径未指定

- **位置**: Slice 1 "契约变更"、Slice 2 "schema / storage 边界"
- **问题类型**: 契约缺失
- **当前写法**: Slice 1 引入 `ReferenceContinuityItem` 和 `TraceMemoryView`，删除旧 `WorkingAssumptionView`、`PinnedStateView` 作为 snapshot 顶层语义。Slice 2 将 durable item kind 迁移为 `reference_continuity_item`、`evidence_backed_fact`、`recent_evidence_item`、`session_summary`、`answer_anchor`、`forward_intent`。但未说明旧 `ConversationContinuityKind.MINIMUM_PRESERVE_ITEM` 如何映射到新模型。
- **反例/失败场景**: implementation agent 在 Slice 1 删除旧 `ConversationContinuityView` 后，不知道旧 `MINIMUM_PRESERVE_ITEM` 应映射为 `ReferenceContinuityItem` 还是直接删除。旧 durable item rows 中的 `MINIMUM_PRESERVE_ITEM` kind 在 Slice 2 迁移时没有明确映射规则，可能导致 implementation agent 自行发明兼容读取路径或丢失 continuity 语义。
- **为什么有问题**: design_doc 24.5 章明确 `ReferenceContinuityItem` 是 Trace Memory 下的受限 item type，用于保存 compact 后仍需解析代词、序号等局部承接的最小上下文。旧 `MINIMUM_PRESERVE_ITEM` 的语义目标与之对齐，但 plan 未显式声明这一迁移关系。
- **直接证据**: design_doc 24.5 "Reference continuity item 是 Trace Memory 下的受限 item type"；control_doc WU-CM-04 "Minimum Preserve 保留为 bounded continuity item，不是事实真源"；代码中 `ConversationContinuityKind.MINIMUM_PRESERVE_ITEM` 仍被 durable/memory.py 写入（line 199, 652-653）。
- **影响**: implementation agent 可能在 Slice 1 删除旧 continuity 类型后遗漏迁移，或在 Slice 2 中为旧 item kind 保留兼容读取路径。
- **建议改法和验证点**: 在 Slice 1 契约变更中显式声明：`MINIMUM_PRESERVE_ITEM` 映射为 `ReferenceContinuityItem(reason="recent_state")`；旧 durable item kind `minimum_preserve_item` 在 Slice 2 迁移为 `reference_continuity_item`。验证点：旧 durable rows 能被新 snapshot codec 正确读取。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F002-未修复-高-vNext compact output parser 所需 schema 细节未在 plan 中完整引用

- **位置**: Slice 3 "契约变更" 第 5-6 点
- **问题类型**: 不可直接实施
- **当前写法**: plan 声称 "LLM parser 只接受 `schema_version="conversation_compact_output_v1"`，字段为 `session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`"，并列出 validation rules（未知 label、跨 section label、缺 source label、空文本、非法枚举、current input anchor 被引用全部 fail closed）。
- **反例/失败场景**: implementation agent 需要知道每个 candidate 的完整 field schema（类型、是否必填、char cap、枚举值列表、source label 允许集合）才能写 strict JSON parser。plan 只列了字段名和高层 validation rule，未引用 design_doc 24.3 章的完整 candidate schema（包括 `EvidenceBackedFactCandidate.evidence_kind` 枚举、`ForwardIntentCandidate.intent_type` / `status` 枚举、`ReferenceContinuityCandidate.reason` 枚举、`AnswerAnchorCandidate` 的嵌套结构）。implementation agent 可能需要反复回查 design doc，或遗漏某些字段约束。
- **为什么有问题**: plan 的目标是 code-generation-ready。strict JSON parser 的实现高度依赖完整 schema 定义；plan 应明确引用 design_doc 24.3 章的 candidate schema 作为 parser 实现的唯一真源，而不是在 plan 中部分复述。
- **直接证据**: design_doc 24.3 章包含完整的 `SessionSummaryCandidate`、`EvidenceBackedFactCandidate`、`AnswerAnchorCandidate`、`ForwardIntentCandidate`、`ReferenceContinuityCandidate`、`CompactCandidateDiagnostic` schema 定义（line 2700-2735），包括所有枚举值和嵌套结构。
- **影响**: implementation agent 可能遗漏枚举约束、嵌套结构或 char cap，导致 parser 不够严格或需要多次返工。
- **建议改法和验证点**: 在 Slice 3 契约变更中增加一句："candidate schema 以 design_doc 24.3 章为唯一真源，包括所有枚举值、嵌套结构、source label 允许集合与 char cap 约束。" 验证点：parser 能 reject 所有 design_doc 24.3 定义的非法 candidate 形态。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### F003-未修复-中-compact material section 映射规则未显式声明

- **位置**: Slice 3 "契约变更" 第 1 点
- **问题类型**: 契约缺失
- **当前写法**: plan 声称 "compact material pack 顶层 section 改为 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`、`instruction`"，但未说明旧 `CompactMaterialBlockKind` 枚举值如何映射到新 section。
- **反例/失败场景**: 当前代码中 `CompactMaterialBlockKind` 包含 `PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY`、`ACCEPTED_TOOL_EVIDENCE`、`USER_INPUT`、`ASSISTANT_FINAL_ANSWER`、`USER_VISIBLE_RUN_STATE` 等。implementation agent 需要知道哪些旧 block kind 映射到 `trace_material`、哪些映射到 `evidence_material`、哪些直接删除。没有显式映射表，implementation agent 可能在 `compact_material.py` 的重构中遗漏或错映射。
- **为什么有问题**: `compact_material.py` 是 Slice 3 的核心修改目标，旧 block-based 模型到新 section-based 模型的映射是实施的关键路径。
- **直接证据**: 代码中 `CompactMaterialBlockKind` 包含 8+ 种 block kind；design_doc 24.3 章定义了 5 种 input section + instruction。映射关系需要显式声明。
- **影响**: implementation agent 可能需要自行推断映射关系，增加返工风险。
- **建议改法和验证点**: 在 Slice 3 契约变更中增加映射表：`USER_INPUT` + `ASSISTANT_FINAL_ANSWER` + `USER_VISIBLE_RUN_STATE` -> `trace_material`；`ACCEPTED_TOOL_EVIDENCE` -> `evidence_material`；assistant final answer / conclusion -> `answer_material`；`PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY` -> 删除，语义由 vNext snapshot 五类 memory 承接。验证点：旧 block kind 不再出现在 vNext material pack 中。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F004-未修复-中-context governance quality checker 新验证规则未具体化

- **位置**: Slice 4 "契约变更" 第 1 点
- **问题类型**: 不可直接实施
- **当前写法**: plan 声称 "quality result 记录 vNext validation issues：schema invalid、unknown / stale / missing source label、cross-section label、provenance mismatch、source boundary violation、fact candidate invalid、answer anchor invalid、forward intent invalid、reference continuity invalid、budget reject"，但未列出具体验证函数签名或验证规则伪代码。
- **反例/失败场景**: 当前 `context_governance.py` 的 `check_compaction_candidate()` 围绕 `pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`open_questions_retained` 组织。vNext 的验证规则完全不同：需要检查 source label allowlist、cross-section citation、`current_input_anchor` 不可引用、`EvidenceBackedFactCandidate.evidence_kind` 枚举等。plan 未说明旧验证函数是删除还是重写，也未给出新验证函数的入口签名。
- **为什么有问题**: Slice 4 的核心就是 quality checker 迁移，但 plan 的具体化程度不如 Slice 1 / 2 / 3。implementation agent 可能需要从 design_doc 24.3 章重新推导完整验证逻辑。
- **直接证据**: design_doc 24.3 章定义了 source label allowlist 规则（"fact 只能引用 evidence labels，answer anchor 只能引用 answer labels"）、current_input_anchor 不可引用规则；context_governance.py 当前实现（line 27-76）围绕旧 candidate 结构。
- **影响**: quality checker 是 compact accept barrier 的核心，不具体化会导致 implementation agent 需要大量回查设计文档。
- **建议改法和验证点**: 在 Slice 4 契约变更中增加验证规则摘要，至少包括：(1) source label allowlist 映射表（fact -> evidence labels, answer anchor -> answer labels, forward intent / reference continuity -> allowed sections, current input anchor -> not citable）；(2) 旧 `check_compaction_candidate()` 函数签名的预期变化；(3) 新 `CompactQualityIssue` 枚举值列表。验证点：所有 design_doc 24.3 定义的非法 candidate 形态都能被 quality checker 拒绝。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### F005-未修复-低-Slice 依赖链可能导致跨 slice 返工

- **位置**: Implementation Slices 总体 sequencing
- **问题类型**: 过度耦合
- **当前写法**: 6 个 slice 按顺序实施：Slice 1 (typed contract) -> Slice 2 (durable store) -> Slice 3 (compact material + parser) -> Slice 4 (accept barrier + repair) -> Slice 5 (RunInputBuilder) -> Slice 6 (smoke + README)。
- **反例/失败场景**: Slice 1 定义的 `ConversationMemorySnapshotVNext` 和 `MemoryProjectionPolicy` 是所有后续 slice 的输入。如果 Slice 3 实施时发现 `ConversationCompactOutputVNext` 的某个 candidate 字段需要调整（例如 `EvidenceBackedFactCandidate` 需要额外的 `confidence` 字段），则 Slice 1 的 snapshot schema、Slice 2 的 durable item codec、Slice 4 的 quality checker 都需要同步修改。
- **为什么有问题**: 这是大型 schema migration 的固有风险，不是 plan 设计缺陷。但 plan 未显式声明 slice 间的 contract handoff 协议：如果后续 slice 发现前序 slice 的 contract 需要调整，是回 Slice 1 修改还是在当前 slice 做 local adaptation？
- **直接证据**: design_doc 24.3 章的 compact I/O contract 是 plan 所有 slice 的上游输入；plan 声称 "若 implementation agent 在 Slice 1 或 Slice 2 发现第 24 / 25 章无法唯一裁决某个 public contract，应停止 implementation，回到 design source 更新"。
- **影响**: 低概率但高成本。如果 contract 需要调整，可能需要回退多个 slice。
- **建议改法和验证点**: plan 已在 Blocking Open Questions 中声明了 "回到 design source 更新" 的原则，这已足够。建议在每个 slice 的退出信号中增加一条："若发现前序 slice 的 contract 需要调整，停止当前 slice 并回到 Slice 1 / design source 更新。" 验证点：每个 slice 完成后，后续 slice 能直接消费其交付物而无需回退。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

当前没有阻塞 code-generation-ready plan 的 open question。

1. **旧 `ConversationContinuityView` 删除后，旧 durable rows 的迁移策略是什么？** — F001 已覆盖，需要 plan 显式声明映射关系。不阻塞 plan 通过，但阻塞 Slice 2 实施。
2. **compact material 的 `previous_compacted_view` 在没有 accepted compact 时如何构造？** — design_doc 24.1 章已明确 "没有 accepted compact 时为空"，plan 也已覆盖。不需要额外裁决。
3. **`CONTEXT_COMPACTION_ATTEMPT_REJECTED` 是否需要在 Slice 4 中实现？** — design_doc 25 章已定义该事件的 payload 要求；plan Slice 4 的 "契约变更" 未显式列出该事件的 payload builder / validator 更新，但 test matrix 中 `test_context_compact_events.py` 已覆盖。implementation agent 应从 design_doc 推导。

## Residual Risks

| ID | 风险 | 严重程度 | Owner / Destination |
|---|---|---|---|
| WU-CM-01-RR-1 | 完整 Conversation Memory eval benchmark | 低 | WU-CM-10 / GitHub Issue #80 |
| WU-CM-01-RR-2 | Cross-session User Profile Memory | 低 | WU-CM-11 / GitHub Issue #115 |
| WU-CM-01-RR-3 | Deep historical recall / semantic search | 低 | GitHub Issue #39 |
| WU-CM-01-RR-4 | Provider-specific tokenizer adapter | 低 | WU-CTX-01 / GitHub Issue #20 |
| WU-CM-01-RR-5 | Fins fact grounding integration | 低 | Fins integration work unit |
| WU-CM-01-RR-6 | Schema old DB upgrade | 低 | explicit non-goal，全新 schema 起库 |

所有 residual risks 均已有 owner / destination，符合 control_doc 的 "ready-to-open-draft-PR 前所有 tracking items 必须处于 closed / deferred-with-owner / transferred-to-issue" 要求。

## Final Plan Review Conclusion

**verdict: pass-with-findings**

plan 整体 code-generation-ready 程度高，严格对齐 design_doc 第 24 / 25 章，遵守 control_doc 的 WU-CM-01 scope / 非目标 / 验收信号。direct code evidence 全部验证通过。6 个 slice 的切分合理，allowed files / modules、test matrix、README sync triggers 和 residual risks 均已明确。

5 条 findings 中：
- **0 条 blocking**：无 findings 阻塞 plan 通过。
- **2 条高严重度**（F001、F002）：需要在 implementation 前补充具体映射 / 引用，但不改变 plan 结构。
- **2 条中严重度**（F003、F004）：需要在 implementation 前补充映射表和验证规则摘要。
- **1 条低严重度**（F005）：slice 依赖链风险已有缓解原则。

建议在进入 implementation gate 前，将 F001-F004 的建议改法合入 plan artifact，然后直接进入 implementation。
