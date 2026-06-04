# WU-CM-01 Plan Re-Review — AgentDS

## Review Metadata

| 项目 | 值 |
|---|---|
| review timestamp | 2026-06-04T10:10:49+08:00 |
| reviewer | AgentDS (plan re-review gate) |
| reviewed target | `docs/host/wu-cm-01-conversation-memory-plan.md` (post-fix) |
| scope | WU-CM-01 Conversation Memory overall optimization plan gate |
| design source | `docs/host/design.md` 第 24 章 Conversation Memory、第 25 章 Context Governance |
| control source | `docs/host/issues-implementation-control.md` |
| previous reviews | `docs/reviews/wu-cm-01-plan-review-mimo.md`; `docs/reviews/wu-cm-01-plan-review-ds.md` |
| controller adjudication | `docs/reviews/wu-cm-01-plan-review-controller-adjudication.md` |
| fix report | `docs/reviews/wu-cm-01-plan-fix-codex.md` |
| current gate | plan re-review |

## Review Posture

本次 re-review 的目标不是重新评估整个 plan，而是验证 controller adjudication 中 accepted 的 6 条 findings (PF-01 到 PF-06) 是否已在 plan artifact 中完成修复，是否存在未被前序 review 覆盖的新风险，以及 plan 是否满足用户指定的重点验证项。

## Reviewed Files

- `docs/host/wu-cm-01-conversation-memory-plan.md` — plan artifact (post-fix，全文 443 行)
- `docs/host/design.md` — 第 24 章 (lines 2518-2857)、第 25 章 (lines 2858-3017)
- `docs/host/issues-implementation-control.md` — WU-CM-01 条目 (lines 365-409)
- `docs/reviews/wu-cm-01-plan-review-mimo.md` — AgentMiMo 初审
- `docs/reviews/wu-cm-01-plan-review-ds.md` — AgentDS 初审
- `docs/reviews/wu-cm-01-plan-review-controller-adjudication.md` — Controller 裁决
- `docs/reviews/wu-cm-01-plan-fix-codex.md` — AgentCodex fix report

## Accepted Finding Fix Verification

### PF-01: Issue-80 / Design 24.7 评测维度映射

**裁决要求**: 在 plan artifact 中新增独立小节，逐条映射 design 24.7 的可断言场景，标记 current scope covered / deferred-with-owner / explicit non-goal，并写明 slice 与测试入口。

**验证结果: FIXED**

Plan 新增 `Issue-80 / Design 24.7 Evaluation Mapping` 小节 (lines 40-62)，包含完整的映射表：

- 15 个评测维度逐条映射，每个维度标注状态、归属 Slice、测试入口、说明。
- `current scope covered` 维度 (14 个) 均绑定到具体 slice (1-5) 和具体测试文件。
- `deferred-with-owner` 维度 (3 个) 均指明 owner issue (WU-CM-10/#80, WU-CM-11/#115, #39)。
- `explicit non-goal` 维度 (1 个: LongMemEval/PersonaMem) 说明原因。
- 与 design 24.7 (lines 2854-2856) 列举的 13+ 个可断言场景完全对应。

**补充验证**: 对照 control doc line 400 的验收信号要求 "每个维度必须标记为 current scope satisfied、deferred-with-owner 或 explicit non-goal"，plan 映射表完全满足。

### PF-02: ConversationContinuityKind 全量处置与 Minimum Preserve 迁移

**裁决要求**: 补充 ConversationContinuityKind 全量处置，RAW_USER_TURN / RAW_ASSISTANT_TURN / ASSISTANT_CONCLUSION 作为 selected recent window material；EPISODE_SUMMARY 由 Session Summary Memory 承接；MINIMUM_PRESERVE_ITEM 由 ReferenceContinuityItem 承接；旧 durable item kind 在全新 schema 中删除，不写旧库兼容读取。

**验证结果: FIXED**

Plan Slice 1 (lines 107-110) 明确：

- 删除旧 `ConversationContinuityKind`、`ConversationContinuityItem`、`ConversationContinuityView` 整体枚举/view 语义。
- `RAW_USER_TURN` / `RAW_ASSISTANT_TURN` / `ASSISTANT_CONCLUSION` → Trace Memory selected recent window material，不作为独立 snapshot item 持久化。
- `EPISODE_SUMMARY` → Session Summary Memory 承接，只能来自 accepted `session_summary` roll-forward view。
- `MINIMUM_PRESERVE_ITEM` → `ReferenceContinuityItem` 承接，旧 `MinimumPreserveReason` 值 "不兼容读取"，按 vNext 文本语义重新映射为 `local_reference` / `ordinal_reference` / `ellipsis_recovery` / `recent_state`。

Plan Slice 2 (lines 147-148) 补充全新 schema 删除旧 durable item kind 列表 (`raw_user_turn`、`raw_assistant_turn`、`assistant_conclusion`、`episode_summary`、`minimum_preserve_item`、`working_assumption`、`pinned_state`)。

**补充验证**: 与 WU-CM-04 (control doc lines 456-475) 的裁决一致——minimum preserve 是 bounded continuity item，不是事实真源。

### PF-03: vNext Compact Output Candidate Schema 与旧类型删除边界

**裁决要求**: 补充 vNext compact output candidate schema 以 design 24.3 为唯一真源；列出待删除旧类型和旧枚举值。

**验证结果: FIXED**

Plan Slice 1 (lines 113-118) 明确列出所有待删除旧类型：
- `EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`PreservationEvidence`
- `PinnedPatchOperation`、`PinnedStringTupleFieldPatch`、`PinnedTextFieldPatch`、`MinimumPreserveReason`
- 旧 `CompactQualityIssue` 中 pinned/preserve/open question 相关枚举值

Plan Slice 3 (lines 190-196) 完整定义 vNext candidate schema：
- `SessionSummaryCandidate(summary_text, source_labels)`
- `EvidenceBackedFactCandidate(claim_text, evidence_labels, evidence_kind, source_labels?)` with `evidence_kind` enum
- `AnswerAnchorCandidate(anchor_title, anchor_items, answer_source_labels)` with `AnswerAnchorChild(display_text, ordinal?)`
- `ForwardIntentCandidate(intent_type, text, status, source_labels)` with `intent_type` and `status` enums
- `ReferenceContinuityCandidate(text, reason, source_labels)` with `reason` enum
- `CompactCandidateDiagnostic(code, text, source_labels?)`

**补充验证**: 与 design doc 24.3 (lines 2700-2735) 的 candidate schema 逐字段比对，枚举值、嵌套结构、nullable/list 规则完全一致。

Plan Slice 4 (lines 249-251) 明确旧 `check_compaction_candidate(request, candidate)` 入口改为 vNext accept barrier，签名为 `check_compaction_candidate(request: CompactionRequestVNext, candidate: ConversationCompactOutputVNext) -> CompactQualityResult`，不提供旧 overload。

### PF-04: 旧 Compact Material Block Kind 到 vNext Sections 映射

**裁决要求**: 在 Slice 3 中补充旧 block kind 到 vNext sections 的映射表，明确哪些旧 block kind 删除。

**验证结果: FIXED**

Plan Slice 3 (lines 199-211) 包含完整映射表：

| 旧 `CompactMaterialBlockKind` | vNext section / 处置 | 说明 |
|---|---|---|
| `PINNED_STATE` | 删除 | 合法语义由 vNext summary/fact/anchor/intent 承接 |
| `EVIDENCE_BACKED_FACT` | `previous_compacted_view` | 仅限来自 latest accepted compacted view 的 vNext projection |
| `WORKING_ASSUMPTION` | 删除 | 不是 vNext session memory category |
| `OPEN_QUESTION` | `previous_compacted_view.forward_intents` 或 删除 | 仅 accepted vNext ForwardIntentCandidate(intent_type="open_question") |
| `RAW_USER_TURN` | `trace_material` | 当前用户输入必须进入 current_input_anchor，不重复出现 |
| `RAW_ASSISTANT_TURN` | `trace_material` 或 `answer_material` | 同一 canonical content 不得同时进入两个 section |
| `EPISODE_SUMMARY` | `previous_compacted_view.session_summary` 或 删除 | 仅 accepted vNext session_summary roll-forward view |
| `ACCEPTED_TOOL_EVIDENCE` | `evidence_material` | 只渲染可读 tool/query/response/source text 与 evidence label |
| `CURRENT_INPUT_ANCHOR` | `current_input_anchor` | readable but not citable |

**补充验证**: 映射规则与 design doc 25 的 material data block section 映射 (lines 2935-2941) 一致——一对一映射，不允许同一 canonical content 同时进入两个 LLM-facing section。

### PF-05: Context Governance Quality Checker 规则

**裁决要求**: 在 Slice 4 中补充 source label allowlist、current input anchor not citable、cross-section citation、provenance mismatch、quality issue 枚举迁移、旧 check_compaction_candidate 入口变化。

**验证结果: FIXED**

Plan Slice 4 (lines 240-254) 包含详细规则：

Source label allowlist 逐 candidate 类型定义 (lines 242-248)：
- `SessionSummaryCandidate.source_labels`: 可引用 previous_compacted_view、trace_material、evidence_material、answer_material 中存在的 labels
- `EvidenceBackedFactCandidate.evidence_labels`: 只能引用 evidence_material labels
- `EvidenceBackedFactCandidate.source_labels` (可选): 也只能是同一 fact 可解释所需的 allowed labels
- `AnswerAnchorCandidate.answer_source_labels`: 只能引用 answer_material labels
- `ForwardIntentCandidate.source_labels`: 可引用 trace_material、answer_material 或 previous_compacted_view.forward_intents/session_summary 对应 labels；不得引用 evidence label
- `ReferenceContinuityCandidate.source_labels`: 可引用 trace_material、answer_material 或 previous_compacted_view.reference_continuity_items 对应 labels
- `CompactCandidateDiagnostic.source_labels`: 只能引用与诊断对象同 section 的 allowed labels
- `current_input_anchor.anchor_label`: 始终不可引用（跨所有 candidate 类型）

Fail-closed 规则 (lines 248-249)：cross-section citation、label 到 provenance 映射不一致、label digest/source boundary 不匹配、stale label、unknown label、缺少必需 source label 全部 fail closed。

旧入口变化 (lines 249-250)：旧 `check_compaction_candidate(request, candidate)` 改为 vNext accept barrier，签名为 `check_compaction_candidate(request: CompactionRequestVNext, candidate: ConversationCompactOutputVNext) -> CompactQualityResult`。

vNext quality issue 枚举 (lines 250-251)：至少包含 schema/label/provenance/candidate/budget 类拒绝原因。

**代码生成就绪评估**: 上述规则可直接翻译为 validator 函数。每个 candidate 类型有明确的 allowed label set、明确的 reject 条件、明确的 fail-closed 行为。Implementation agent 不需要自行推断验证逻辑。

### PF-06: Slice 1-5 可编译性与 Pyright 验证边界

**裁决要求**: 明确 Slice 1-5 是否必须保持 pyright 可通过，若中间不可编译需说明允许条件和最早验证点。

**验证结果: FIXED**

Plan 新增 `Slice Verification Boundary` 小节 (lines 80-90)，明确：

- Slice 1-5 是同一 plan 下的整体 schema/contract 迁移序列，按概念域拆分供 review 聚焦，不承诺每个中间 slice 结束后整个 `dayu/host` 都可通过 pyright。
- 中间不可编译的原因：Slice 1 删除旧 typed contract 后，后续 slice 的 imports/field access 会短暂引用已删除符号。
- 最早恢复点：Slice 5 结束时 typed contract、durable projection、compact material/parser、accept barrier 与 RunInputBuilder 已闭合。
- 最终全量验证：Slice 6 完成后运行 `python -m pyright dayu/ tests/ utils/`。
- Implementation report 要求：若全量 pyright 在 Slice 1-4 失败，report 必须列出失败是否只来自后续 slice 尚未迁移的旧引用，不得掩盖新增无关类型错误。
- 替代方案提示：若 implementation gate 要求每个提交都可编译，必须改写为更小的可编译闭环提交。

## 用户指定重点验证项

### 1. issue-80 / design 24.7 映射已在 plan artifact 内完成

**通过。** `Issue-80 / Design 24.7 Evaluation Mapping` 小节 (lines 40-62) 包含 15 行映射表，逐条标注状态、slice、测试入口、deferred owner。与 design 24.7 (line 2854) 列举的可断言场景逐一对应。

### 2. ConversationContinuityKind / minimum preserve 迁移与全新 schema 无兼容读取边界明确

**通过。** Slice 1 (lines 107-110) 全量处置 5 个旧 continuity kind；Slice 2 (lines 147-148) 明确全新 schema 删除 7 种旧 durable item kind；旧 MinimumPreserveReason 显式标注 "不兼容读取" (line 110)。无旧库兼容读取路径。

### 3. vNext compact schema 与旧 candidate / old quality issue 删除边界明确

**通过。** Slice 1 (lines 113-118) 列出全部待删除旧类型和旧枚举值；Slice 3 (lines 190-196) 完整定义 vNext candidate schema，与 design 24.3 一致；Slice 4 (lines 250-251) 明确旧 quality issue 专属枚举删除。

### 4. material block 到 vNext section 映射完整

**通过。** Slice 3 (lines 199-211) 映射表覆盖全部 9 种旧 `CompactMaterialBlockKind`，每行标注 vNext section 或删除处置及说明。与 design doc 25 的 material data block section 映射规则一致。

### 5. quality checker / source label allowlist / current input anchor not citable 规则足够 code-generation-ready

**通过。** Slice 4 (lines 240-254) 的规则可直接翻译为 validator 实现：
- 每个 candidate 类型有明确的 allowed label set（如 "只能引用 evidence_material labels"）
- 每个 candidate 类型有明确的 reject 条件（如 "不得引用 current_input_anchor.anchor_label"）
- 全局 fail-closed 规则覆盖 cross-section citation、stale/unknown/missing label、provenance mismatch
- 旧到新入口签名变化明确

### 6. Slice 1-5 可编译性与 pyright 验证边界明确

**通过。** `Slice Verification Boundary` 小节 (lines 80-90) 明确：中间 slice 不承诺全量 pyright、最早恢复点为 Slice 5、最终验证在 Slice 6、implementation report 的失败申报要求、替代的可编译闭环方案。

## New Findings

### NF-01-新增-低-EvidenceBackedFactCandidate.source_labels 的 allowed label 可解释性边界略模糊

- **位置**: Plan Slice 4 line 243
- **问题类型**: 不可直接实施（轻微）
- **当前写法**: "可选 `source_labels` 若存在，也只能是同一 fact 可解释所需的 allowed labels，不能把 user input、assistant answer、summary、anchor 或 intent 冒充 evidence。"
- **反例/失败场景**: Implementation agent 在为 EvidenceBackedFactCandidate.source_labels 编写 validator 时，"同一 fact 可解释所需"是一个语义判断，而不是机械可检查的 label set 约束。agent 可能不确定 source_labels 是否只允许 evidence_material labels，还是允许 trace_material 中与 evidence 直接相关的行（例如用户说"用工具 X 查 Y"的 user input）。
- **为什么有问题**: 与 evidence_labels 的硬约束（"只能引用 evidence_material labels"）相比，source_labels 的约束表述偏软。design doc 24.3 (line 2737) 对 EvidenceBackedFactCandidate 的整体约束是"只能引用 evidence material labels"，可以解读为同时约束 evidence_labels 和 source_labels。
- **直接证据**: Plan line 243 vs design doc line 2737。
- **影响**: Implementation agent 可能需要回查 design doc 或做额外判断，但不会导致错误实现（最坏情况是 source_labels 也限制为 evidence_material labels，这是安全的）。
- **建议改法和验证点**: 将 source_labels 约束改为 "source_labels 若存在，也只能引用 evidence_material 中存在的 labels"。或者在 implementation gate 中由 agent 按 design 24.3 的 "只能引用 evidence material labels" 统一约束即可，无需修改 plan。
- **严重程度**: 低

### NF-02-新增-低-ForwardIntentCandidate 的"不得自动触发工具"约束不是 accept barrier 可机械检查项

- **位置**: Plan Slice 4 line 245
- **问题类型**: 契约缺失（轻微）
- **当前写法**: "ForwardIntentCandidate.source_labels 可引用 trace_material、answer_material 或 previous_compacted_view.forward_intents / session_summary 对应 labels；不得引用 evidence label 来制造待办事实，也不得自动触发工具。"
- **反例/失败场景**: "不得引用 evidence label" 是 label-level 的机械检查，accept barrier 可验证。但 "不得自动触发工具" 是系统行为约束——它要求 Host 不把 ForwardIntent 的内容作为工具调用计划或自动执行。这个约束不在 accept barrier 的 label validator 职责范围内，而是在 Context Governance 编排层和 RunInputBuilder 渲染层。
- **为什么有问题**: 该约束放在 Slice 4 accept barrier 的 source label allowlist 上下文中，可能让 implementation agent 误以为 accept barrier 需要检查 "会不会触发工具"。实际上 accept barrier 只检查 label 合法性；"不自动触发工具" 是编排层的 design constraint。
- **直接证据**: Plan line 245；design doc 24.5 line 2797: "Forward Intent Memory 保存待澄清问题、未完成任务、下一步任务状态等前瞻意图。它不是真实世界事实，也不直接驱动工具执行"。
- **影响**: Implementation agent 可能在 accept barrier 中尝试实现不应该在此层实现的检查。但 plan 已经明确 accept barrier 的职责是 label/provenance/candidate 校验，不会引发结构性错误。
- **建议改法和验证点**: 不需要修改 plan。Implementation agent 应将 "不自动触发工具" 理解为编排层约束，不作为 accept barrier 的 validator 规则。
- **严重程度**: 低

## Open Questions

| # | Question | Context | Status |
|---|---------|---------|--------|
| OQ1 (carry-over) | Reactive multi-pass compact 的具体实现范围——WU-CM-01 是否完整实现 multi-pass？ | Plan Slice 4 lines 252-253 明确了 multi-pass 与 whole-candidate repair 共用 operation-level budget，并禁止 partial compact。但 multi-pass 的 material block batch processing 编排细节（分段策略、中间 pass 的 transient artifact 管理）留给 implementation agent 从 design doc 25 推导。 | 不阻塞 plan。Design doc 25 (lines 2952-2964) 提供了足够详细的 multi-pass 规范。 |
| OQ2 (carry-over) | vNext `MemoryProjectionDiagnostics` 的完整 reason 枚举值列表 | Plan Slice 1 lines 117-118 说明了删除旧 reason、迁移 minimum preserve reason、可保留或重命名的 reason 必须只表达 vNext 语义。但未给出最终的完整 reason 枚举列表。 | 不阻塞 plan。Implementation agent 可从 vNext 五类语义推导出完整的 diagnostic reason set。 |
| OQ3 (new) | `SessionSummaryCandidate.source_labels` 的 allowed label set 非常宽（previous_compacted_view、trace_material、evidence_material、answer_material 中的所有 labels），这是否会降低 summary 质量或引入 noise？ | Plan Slice 4 line 242 允许 SessionSummaryCandidate 引用几乎所有 section 的 labels。Design doc 24.3 line 2696 没有对 summary source_labels 做 section 限制。 | 不阻塞 plan。这是 design doc 层面的设计选择，plan 正确反映了 design doc 的意图。若后续 eval 发现 summary quality 问题，应在 WU-CM-10/#80 中跟踪。 |

## Residual Risks

| # | Risk | Severity | Owner |
|---|------|----------|-------|
| WU-CM-01-RR-1 | 完整 Conversation Memory eval benchmark | 低 | WU-CM-10 / GitHub Issue #80 |
| WU-CM-01-RR-2 | Cross-session User Profile Memory | 低 | WU-CM-11 / GitHub Issue #115 |
| WU-CM-01-RR-3 | Deep historical recall / semantic search | 低 | GitHub Issue #39 |
| WU-CM-01-RR-4 | Provider-specific tokenizer adapter | 低 | WU-CTX-01 / GitHub Issue #20 |
| WU-CM-01-RR-5 | Fins fact grounding integration | 低 | Fins integration work unit |
| WU-CM-01-RR-6 | Schema old DB upgrade | 低 | explicit non-goal，全新 schema 起库 |
| WU-CM-01-RR-7 (new) | Implementation agent 在 Slice 1-4 的中间不可编译状态下可能遗漏跨 slice 的类型不一致——例如 Slice 1 定义的 vNext dataclass 字段名与 Slice 3 parser 使用的字段名不匹配 | 低 | Implementation gate 的 Slice 5 pyright 验证 + code review gate |
| WU-CM-01-RR-8 (new) | Plan 的 Slice Verification Boundary 允许中间状态不可编译，若 implementation agent 不严格遵守 "不得通过 compatibility wrapper 保持表面可编译" 的约束，可能引入兼容性代码 | 低 | Implementation gate + review gate 应检查是否出现 compatibility wrapper |

## Finding Summary

| Finding ID | 来源 | 修复状态 | 说明 |
|---|---|---|---|
| PF-01 | AgentDS F1 | **FIXED** | Issue-80 / design 24.7 评测维度映射已嵌入 plan artifact |
| PF-02 | AgentMiMo F001 / AgentDS F4 | **FIXED** | ConversationContinuityKind 全量处置 + minimum preserve 迁移 + 全新 schema 无兼容读取 |
| PF-03 | AgentMiMo F002 / AgentDS F2 | **FIXED** | vNext candidate schema + 旧类型/旧 quality issue 删除边界 |
| PF-04 | AgentMiMo F003 | **FIXED** | 旧 material block kind → vNext section 映射表 |
| PF-05 | AgentMiMo F004 | **FIXED** | Source label allowlist + current input anchor not citable + quality checker 规则 |
| PF-06 | AgentDS F3 / AgentMiMo F005 | **FIXED** | Slice 1-5 可编译性/pyright 验证边界 |
| NF-01 | 本次 re-review | **新增** | EvidenceBackedFactCandidate.source_labels allowed label 可解释性边界略模糊（低） |
| NF-02 | 本次 re-review | **新增** | ForwardIntentCandidate "不自动触发工具"约束不在 accept barrier 层（低） |

## Blocking Open Questions

当前没有阻塞 plan 进入 implementation gate 的 open question。

PF-01 到 PF-06 全部修复完成。NF-01 和 NF-02 为低严重度，不阻塞 plan 通过——implementation agent 在实现时可以从 design doc 24.3 和 24.5 自行解决这两个轻微歧义。

## Final Plan Re-Review Conclusion

**Verdict: PASS**

Plan 的 6 条 accepted findings 全部完成修复，fix 质量高。新增的 Issue-80/Design 24.7 Evaluation Mapping、Slice Verification Boundary、material block mapping table、source label allowlist 规则均为实质性补充，使 plan 达到 code-generation-ready 标准。

所有用户指定的重点验证项（issue-80 映射、ContinuityKind/migration 边界、vNext schema/旧类型删除边界、material block mapping、quality checker 规则、slice 可编译性边界）均已确认通过。

2 条新增 finding (NF-01, NF-02) 为低严重度，不阻塞 plan。2 条新增 residual risk (RR-7, RR-8) 已有明确的 downstream gate owner。

Plan 可以进入 implementation gate。
