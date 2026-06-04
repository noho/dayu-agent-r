# WU-CM-01 Plan Review — AgentDS Adversarial Review

## Review Metadata

- **review target**: `docs/host/wu-cm-01-conversation-memory-plan.md`
- **design source**: `docs/host/design.md` 第 24 章 Conversation Memory、第 25 章 Context Governance
- **control source**: `docs/host/issues-implementation-control.md` WU-CM-01 / WU-CM-02 / WU-CM-03 / WU-CM-04 / WU-CM-10 / WU-CM-11
- **reviewer**: AgentDS (plan review gate)
- **review date**: 2026-06-04
- **verdict**: **pass-with-findings** (4 findings, 1 blocking)

---

## Scope and Posture

本次 review 严格按 adversarial 立场进行：不证明 plan 可行，而是尽力找出最强的、基于证据的理由说明 plan 还不应该交给 implementation agent。所有 finding 均基于 design doc、control doc、当前生产代码与测试事实的直接证据。

## Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|--------|
| A1 | Plan 的代码证据（第 40-52 行）准确反映了当前代码的旧 shape | **成立**。memory.py:813-841 确认 `ConversationMemorySnapshot` 含 `pinned_state`、`working_assumptions`、`conversation_continuity`；compaction.py:623-636 确认 `CompactMaterialPack` 使用 `stable_input`/`history_input`/`evidence_input`；llm_compaction.py 确认解析 `episode_summary_candidate`、`pinned_state_patch_candidate`、`minimum_preserve_item_candidates`；run_input.py:141-150 确认旧 memory render headers。 |
| A2 | 6 个 slice 的 sequencing 可以独立推进 | **部分成立**。Slice 1 契约变更会导致 Slice 2-5 的生产代码编译失败，直到对应 slice 也完成。详见 Finding 3。 |
| A3 | Plan 的 allowed files 列表覆盖了所有受影响模块 | **基本成立**，但 `dayu/host/context_budget.py` 在 test matrix 中引用却不在 allowed modification list 中。详见 Finding 5。 |
| A4 | Plan 已满足 control doc 对 plan artifact 的全部要求 | **不成立**。Control doc 要求 plan 必须枚举 #80 评测维度映射，plan 将其推迟到 Slice 6 implementation report。详见 Finding 1。 |
| A5 | Whole-candidate repair 策略在 reactive multi-pass 场景下行为明确 | **部分成立**。Plan Slice 4 只描述 single-pass repair，design doc 25 描述 multi-pass 场景但 plan 未交叉引用。详见 Finding 7。 |
| A6 | 旧类型删除边界完整 | **部分成立**。Plan 列出了核心旧类型但遗漏了 `EpisodeSummaryCandidate`、`PinnedStatePatchCandidate` 等。详见 Finding 2。 |

---

## Findings

### 1-未修复-高-#80-评测维度映射未嵌入-plan-artifact

- **位置**: Plan Slice 6 (第 242 行)；control doc WU-CM-01 验收信号 (第 399-400 行)
- **问题类型**: 不可直接实施 / 契约缺失
- **当前写法**: Plan Slice 6 说"在 implementation report 中将 #80 评测维度标记为 current scope covered、deferred-with-owner 或 explicit non-goal"，将 #80 映射推迟到实现阶段。Plan 自身只在 Residual Risks 粗略标记了 deferred-with-owner，未枚举具体维度。
- **反例/失败场景**: Implementation agent 按 plan 推进到 Slice 6 时才首次面对 #80 维度映射，若发现某个评测维度需要 Slice 1-5 的契约设计调整，返工成本极高。Control doc 明确要求"任何 WU-CM-01 design / plan 都必须说明 #80 的评测维度哪些由当前 scope 满足"——这是 plan gate 的前置条件，不是 implementation report 的后置产物。
- **为什么有问题**: Control doc 第 371 行、第 400 行将 #80 映射作为 plan 验收信号（"#81 的 design / plan 明确映射 #80 评测维度"），不是 implementation 验收信号。Design doc 24.7 已列举 WU-CM-01 应覆盖的可断言场景，但 plan 未逐条映射到具体 slice 和测试入口。
- **直接证据**:
  - Control doc line 371-372: "任何 WU-CM-01 design / plan 都必须说明 #80 的评测维度哪些由当前 scope 满足、哪些 deferred-with-owner、哪些是 explicit non-goal。若某个 #81 方案让 #80 的核心评测维度不可测试、不可审计或不可实现，必须先回到设计讨论修正。"
  - Control doc line 400: "#81 的 design / plan 明确映射 #80 评测维度：每个维度必须标记为 current scope satisfied、deferred-with-owner 或 explicit non-goal。"
  - Design doc 24.7 line 2854: 列举了 14 个可断言场景（empty compacted view、non-empty compacted view、post-compact delta、compact boundary、protected recent floor、deterministic bounded projection、provider context length fallback、invalid/missing/stale source label、schema invalid、provenance mismatch、partial candidate invalid、fallback 不生成高阶语义、compact roll-forward）。
  - Plan line 242: "在 implementation report 中将 #80 评测维度标记为..."
- **影响**: Implementation agent 可能在 Slice 1-5 做错契约设计，导致 Slice 6 发现无法满足 #80 某个评测维度，需要回退到 Slice 1 修改——这是 plan 不够 code-generation-ready 的直接表现。
- **建议改法和验证点**:
  1. 在 plan artifact 中新增一个独立小节，逐条列举 design doc 24.7 的可断言场景，映射到 plan 的 slice 编号和对应测试文件。
  2. 对每个维度标记：current scope covered（指明 slice + test）、deferred-with-owner（指明 owner issue）、explicit non-goal（说明原因）。
  3. 验证点：control doc 第 400 行的验收信号应能从该小节直接满足。
- **修复风险**: 低（纯 plan 文档补充，不涉及代码）
- **严重程度**: 高（blocking：control doc 强制要求 plan 做此映射）

---

### 2-未修复-中-旧-compact-candidate-类型删除边界不完整

- **位置**: Plan Slice 1 契约变更 (第 67-73 行)；Plan Allowed Files (第 263 行 `dayu/host/compaction.py`)
- **问题类型**: 不可直接实施 / 范围漂移
- **当前写法**: Plan 明确列出删除 `WorkingAssumptionView`、`PinnedStateView`、`ConversationContinuityKind.MINIMUM_PRESERVE_ITEM`、`MemoryIncludedReason.WORKING_ASSUMPTION`。但 `compaction.py` 中还存在 `EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`、`PinnedPatchOperation`、`PinnedStringTupleFieldPatch`、`PinnedTextFieldPatch`、`PreservationEvidence`、`CompactQualityIssue` 中 `PINNED_*`/`MINIMUM_PRESERVE_*`/`OPEN_QUESTIONS_*` 等旧枚举值——plan 对这些类型的处置是隐含的而非显式的。
- **反例/失败场景**: Implementation agent 删除了 `WorkingAssumptionView` / `PinnedStateView`，但留下 `PinnedStatePatchCandidate` 和 `EpisodeSummaryCandidate` 在 `compaction.py` 中未删除。后续 Slice 3 的 `llm_compaction.py` parser 迁移时，agent 不确定是否应继续解析这些旧 candidate 字段并映射到 vNext，还是直接删除。这会导致 Slice 1 和 Slice 3 之间的类型残留。
- **为什么有问题**: Plan 说"删除旧 WorkingAssumptionView、PinnedStateView"但没有说"删除 EpisodeSummaryCandidate、PinnedStatePatchCandidate、MinimumPreserveItemCandidate、PreservationEvidence"。这些类型与旧 LLM parser 紧密耦合（llm_compaction.py:413-453），如果不在 Slice 1 明确处置，Slice 3 的 parser 迁移将失去明确目标。
- **直接证据**:
  - compaction.py:1134 `class PinnedStatePatchCandidate`
  - compaction.py 定义 `EpisodeSummaryCandidate`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`、`PreservationEvidence`
  - llm_compaction.py:413-453 解析 `episode_summary_candidate`、`pinned_state_patch_candidate`、`minimum_preserve_item_candidates`
  - context_governance.py:27-60 quality checker 检查 `PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`PreservationEvidence`
- **影响**: Implementation agent 可能在 Slice 1 只做部分删除，留到 Slice 3 再做 parser 迁移时才发现遗漏类型，导致返工。最坏情况下旧类型作为 dead code 残留，与 vNext 类型并存造成混淆。
- **建议改法和验证点**:
  1. 在 plan Slice 1 "契约变更"中新增一个显式子节，列出 compaction.py 中所有待删除的旧类型和旧枚举值（含 `PinnedStatePatchCandidate`、`EpisodeSummaryCandidate`、`MinimumPreserveItemCandidate`、`MinimumPreserveReason`、`PreservationEvidence`、`PinnedPatchOperation`、`PinnedStringTupleFieldPatch`、`PinnedTextFieldPatch`）。
  2. 同时列出 `CompactQualityIssue` 中需要删除的旧枚举值（`PINNED_PATCH_*`、`PRESERVATION_EVIDENCE_*`、`MINIMUM_PRESERVE_*`、`OPEN_QUESTIONS_*`、`EVIDENCE_ANCHOR_NOT_RETAINED` 等）。
  3. 验证点：Slice 1 退出信号中增加"旧 candidate 类型、旧 quality issue 枚举值不再存在于 compaction.py"。
- **修复风险**: 低（纯 plan 文档补充）
- **严重程度**: 中（implementation agent 可自行推断但存在遗漏风险，建议修复后再进入 implementation）

---

### 3-未修复-中-sequential-slices-的中间编译状态未处理

- **位置**: Plan Implementation Slices (第 54-258 行)
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: Plan 将 6 个 slice 顺序排列。Slice 1 修改 `memory.py`、`compaction.py` 的 typed contract 后，Slice 2-5 的生产模块（`durable/memory.py`、`compact_material.py`、`llm_compaction.py`、`run_input.py` 等）仍 import 旧类型名，在 Slice 1 完成后、Slice 2-5 完成前会处于无法编译的状态。
- **反例/失败场景**: 
  1. Implementation agent 完成 Slice 1，运行 pyright → 大量报错（`ConversationMemorySnapshot` 不再有 `pinned_state` 字段，但 `durable/memory.py`、`compact_material.py`、`run_input.py` 仍访问它）。
  2. Agent 无法运行任何测试验证 Slice 1 的正确性，因为整个 Host 层已处于断裂状态。
  3. Agent 被迫将 Slice 1-5 合并为一次巨型提交，失去了 slice 的分步 review 价值。
- **为什么有问题**: Plan 的 slice 边界是按"概念域"划分（contract → durable → parser → governance → renderer → smoke），但没有按"编译单元闭合"划分。Implementation agent 无法在 Slice 1 完成后独立验证，必须推进到至少 Slice 5 才能恢复可编译状态。这违背了 code-generation-ready plan 的可增量实施要求。
- **直接证据**:
  - `dayu/host/durable/memory.py:51` 导入 `WorkingAssumptionView` —— Slice 1 删除此类型后编译失败
  - `dayu/host/run_input.py:107` 导入 `WorkingAssumptionView` —— 同上
  - `dayu/host/compact_material.py:1324-1394` 访问 `snapshot.pinned_state`、`snapshot.evidence_backed_facts`、`snapshot.working_assumptions` —— Slice 1 删除后编译失败
  - `dayu/host/context_governance.py:11-23` 导入 `PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`PreservationEvidence` —— Slice 1 删除后编译失败
- **影响**: Implementation agent 无法按 slice 独立验证，可能导致巨型提交或 slice 边界在实施中被破坏。Reviewer 也无法按 slice 做增量 review。
- **建议改法和验证点**:
  1. 方案 A（推荐）：明确声明 Slice 1-5 是"codebase 整体迁移"，中间状态不要求可编译、可测试。Slice 的划分目的是 review 关注点分离而非独立可验证的增量。在 plan 中显式说明这一约束。
  2. 方案 B：重新组织 slice 边界，使每个 slice 内部闭合。例如将 Slice 1-3 合并为"contract + durable + parser"的原子 slice，Slice 4-5 合并为"governance + renderer"的原子 slice。
  3. 无论选择哪个方案，plan 必须明确告知 implementation agent 哪个 slice 结束后可以运行 pyright、哪个不能。
- **修复风险**: 低（澄清 plan 约束，不改生产代码）
- **严重程度**: 中（不修复时 implementation agent 会面临困惑，但不会写出错误代码）

---

### 4-未修复-中-ConversationContinuityKind-枚举成员处置不完整

- **位置**: Plan Slice 1 (第 69-71 行)；设计真源 24.5 (第 2789 行)
- **问题类型**: 契约缺失
- **当前写法**: Plan 说"删除旧 WorkingAssumptionView、PinnedStateView 作为 snapshot 顶层语义的用途"，并引入 `ReferenceContinuityItem`。但 `ConversationContinuityKind` 枚举有五个成员：`RAW_USER_TURN`、`RAW_ASSISTANT_TURN`、`ASSISTANT_CONCLUSION`、`EPISODE_SUMMARY`、`MINIMUM_PRESERVE_ITEM`。Plan 只明确处置了 `MINIMUM_PRESERVE_ITEM`（→ reference continuity），对另外四个成员是删除还是迁移没有说明。
- **反例/失败场景**: Implementation agent 在 Slice 1 中保留了 `ConversationContinuityKind` 的 `RAW_USER_TURN`、`RAW_ASSISTANT_TURN`、`ASSISTANT_CONCLUSION`，但这些语义在 vNext 中应归入 Trace Memory 的 selected recent window，而非独立的 continuity item kind。如果 agent 保留它们，vNext snapshot 中会出现不属于五类语义模型的 item。如果 agent 删除它们，selected recent window 中的 user/assistant turn 如何表达可能不明确。
- **为什么有问题**: Design doc 24.5 明确 Trace Memory "负责对话连续性"，数据来源包括 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED.final_answer`，Reference continuity item 是 Trace Memory 下的受限 item type。旧 `RAW_USER_TURN` 等 continuity kind 实际上是 vNext selected recent window 的 material，不应再作为 durable snapshot item kind 存在。但 plan 没有明确这个映射。
- **直接证据**:
  - memory.py:192-199 `ConversationContinuityKind` 枚举
  - memory.py:499-569 `ConversationContinuityItem` dataclass
  - memory.py:571 `ConversationContinuityView` dataclass
  - durable/memory.py:652-653 写入 `snapshot.conversation_continuity.items`
  - design.md:2789 Trace Memory 定义
- **影响**: Implementation agent 可能保留不应存在的 item kind，导致 vNext snapshot schema 中有不属于五类语义模型的残留类型。后续 #80 eval 无法断言"snapshot 只包含五类语义"。
- **建议改法和验证点**:
  1. 在 plan Slice 1 契约变更中显式说明：`ConversationContinuityKind` 枚举整体删除（连同 `ConversationContinuityItem`、`ConversationContinuityView`），其承载的语义分散到：
     - RAW_USER_TURN / RAW_ASSISTANT_TURN / ASSISTANT_CONCLUSION → Trace Memory selected recent window material（不单独持久化为 snapshot item）
     - EPISODE_SUMMARY / MINIMUM_PRESERVE_ITEM → 不再作为独立 snapshot 字段，由 vNext `ReferenceContinuityItem.reason` 或 Session Summary 承接
  2. 验证点：Slice 2 退出信号增加"ConversationContinuityKind 不再作为 durable item kind 存在"。
- **修复风险**: 低
- **严重程度**: 中（不修复时可能产生 schema 残留，但 implementation agent 很可能从 design doc 24.4/24.5 自行推断）

---

## Open Questions

| # | Question | Context |
|---|---------|---------|
| OQ1 | Reactive multi-pass compact 中，每个 pass 的 whole-candidate repair 预算是共享 `max_compaction_attempts_per_operation` 还是每个 pass 独立？Design doc 25 说"每个 pass 的外部 LLM proposal 消耗 `max_compaction_attempts_per_operation` 预算"——这意味着所有 pass 共享同一个 attempt budget。但 plan Slice 4 只描述了 single-pass repair 行为，未覆盖 multi-pass 场景。需要在 plan 中补充说明或显式 defer。 |
| OQ2 | `ConversationMemorySnapshotVNext` 的 `diagnostics` 字段类型在 plan 中是 `MemoryProjectionDiagnostics`，但 design doc 24.4 写的是 `diagnostics: MemoryProjectionDiagnostics`（未展开内部结构）。当前 `MemoryDiagnostic` 的 `MemoryDiagnosticReason` 枚举包含 `MINIMUM_PRESERVE_ITEM_COVERED` 等旧值。vNext diagnostic reason 枚举是否需要重新定义？ |
| OQ3 | Design doc 24.2 要求"prompt-local label 是本次 LLM 调用内的 opaque citation handle"，且"第一阶段允许使用短 deterministic handle，例如 C1、H1、E1、S1、E1.1"。但 plan 未指定 label 格式约定——这是留给 implementation agent 自行决定的自由度，还是需要在 plan 中收敛？ |

---

## Residual Risks

| # | Risk | Owner | Mitigation |
|---|------|-------|-----------|
| R1 | 旧 durable snapshot 测试 fixture / smoke 数据库中有旧 schema 的 snapshot row，全新 schema 起库后这些 fixture 需要重建。如果 implementation agent 遗漏某个 fixture 更新，smoke 或集成测试可能报错。 | Implementation agent | Plan 已说明"按全新 schema 起库处理"，agent 应逐文件检查 fixture。 |
| R2 | `dayu/host/context_policy.py` 的 `ContextCompactionTriggerSource` 枚举和 policy 默认值可能需要跟随 vNext 调整，但 plan 只在 Slice 1 说"仅当现有 policy 默认值需要对齐 memory section cap / floor 时修改"——措辞不够明确。 | WU-CM-01 implementation | Review gate 应验证 context_policy.py 变更的必要性。 |
| R3 | Design doc 25 的 reactive multi-pass compact 是复杂的编排逻辑（material block batch processing），plan Slice 4 对其覆盖较浅（主要关注 single-pass repair/fallback）。实施风险后移。 | WU-CM-01 implementation + review gate | Implementation agent 在 Slice 4 发现 gap 时应回到 design source。 |
| R4 | `MemorySnapshotView`（run_input.py:212）是 RunInputBuilder 的内部 provider output dataclass，与 `ConversationMemorySnapshotVNext`（design doc 24.4）是不同的概念。Plan Slice 5 说要将 MemorySnapshotView 改为 vNext readable section view——两个类型可能被混淆。 | Implementation agent | 需仔细区分"snapshot typed schema"和"RunInputBuilder 内部消费 snapshot 后产出的 view"。 |

---

## Reviewed Files

- `docs/host/wu-cm-01-conversation-memory-plan.md` — plan artifact (全文)
- `docs/host/design.md` — 第 24 章 Conversation Memory (lines 2518-2856)、第 25 章 Context Governance (lines 2858-3017)
- `docs/host/issues-implementation-control.md` — WU-CM-01 (lines 365-407)、WU-CM-02 (lines 409-431)、WU-CM-03 (lines 433-452)、WU-CM-04 (lines 454-473)、WU-CM-10 (lines 1414+)、WU-CM-11 (lines 1449+)
- `dayu/host/memory.py` — lines 1-120, 192-291, 652-682, 813-911
- `dayu/host/compaction.py` — lines 1-120, 280-359, 623-722
- `dayu/host/run_input.py` — lines 1-150, 212-333
- `dayu/host/llm_compaction.py` — lines 1-60, 413-453, 597-618, 1254-1389
- `dayu/host/context_governance.py` — lines 1-60
- `dayu/host/compact_material.py` — lines 1324-1423
- `dayu/host/durable/memory.py` — lines 1-60, 640-789
- `tests/README.md` — 全文
- `tests/host/test_memory_projection.py` — 确认存在且含旧断言
- `tests/host/test_compaction_contract.py` — 确认存在且含旧断言
- Test file existence check — 验证 plan 引用的所有测试文件

---

## Conclusion

**Verdict: pass-with-findings**

Plan 的核心架构方向正确——将 Conversation Memory 收敛到五类 session semantic memory、用 vNext compact I/O contract 替代旧 stable/history/evidence 三层结构、实施 whole-candidate repair、保持 EventLog truth / memory snapshot read model 边界。与 design doc 第 24/25 章的对齐是实质性的。

4 个 finding 中，Finding 1（#80 评测维度映射未嵌入 plan artifact）是 blocking 级别的控制文档合规问题，必须在 plan 进入 implementation gate 前修复。Finding 2-4 是中等级别，建议修复以降低 implementation agent 的返工风险，但不强制阻塞。

修复 Finding 1 后（在 plan 中新增 #80 维度映射小节），plan 可进入 implementation gate。

Open questions 3 条、residual risks 4 条已记录，不构成 gate block。
