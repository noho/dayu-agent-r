# WU-CM-01 Conversation Memory Overall Optimization Plan

## Gate Scope

本文件是 WU-CM-01 的 plan gate artifact。当前 gate 只产出 code-generation-ready implementation plan，不修改生产代码、不运行测试、不创建 commit / push / PR，不进入 review、implementation 或 fix gate。

- work unit：WU-CM-01 Conversation Memory overall optimization。
- 类型：issue-backed feature / umbrella implementation entry point。
- issue owner / destination：GitHub Issue #81。
- design source：`docs/host/design.md` 第 24 章 Conversation Memory 与第 25 章 Context Governance。
- control source：`docs/host/issues-implementation-control.md` 的 WU-CM-01、WU-CM-02、WU-CM-03、WU-CM-04、WU-CM-10、WU-CM-11 条目。
- expected artifact path：`docs/host/wu-cm-01-conversation-memory-plan.md`。

## First-Principles Goal Confirmation

动机成立。Host 是“宿主强约束下的 LLM in the loop”，因此 memory 必须是可重建、可审计、bounded 的 EventLog read model；它不能变成事实真源，也不能用预算策略名冒充语义模型。当前代码仍把 `pinned_state`、`working_assumptions`、`history_pool`、`stable_layer`、`minimum_preserve` 等旧 shape 混在 projection、compact material 与 RunInputBuilder 中，这会让 memory 语义、prompt assembly、compact accept barrier 和 fallback 治理互相污染。

严重性为高。该问题不只是字段命名过期，而是契约不一致：design source 已明确五类 session semantic memory、vNext compact input/output、snapshot vNext、固定 prompt assembly 顺序和 whole-candidate repair；生产代码仍按旧 stable memory blocks 和旧 compact contract 组织输入输出。若继续局部修补，后续 #80 eval、#115 User Profile Memory、#39 recall / search 和 Fins fact boundary 都会缺少稳定断言入口。

成功信号：

- Conversation Memory contract 收敛到五类 session semantic memory：Trace、Evidence / Fact、Session Summary、Answer Anchor、Forward Intent。
- `working_assumptions` / `pinned_state` 不作为兼容 wrapper 或独立 session memory 保留；旧字段从 schema、snapshot codec、durable item、projection、compact material、RunInputBuilder 和 tests 中同步迁移。
- `ConversationCompactInputVNext` 使用 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`、`instruction`，不再使用 `stable_input` / `history_input` / `evidence_input` 作为顶层 mental model。
- `ConversationCompactOutputVNext` 只接受 session summary、evidence-backed fact candidates、answer anchors、forward intents、reference continuity items、diagnostics。
- RunInputBuilder 按第 24.6 章固定顺序渲染 memory section，并保证 fallback 只渲染 bounded recent window 与 current input，不物化高阶 memory。
- compact repair 采用 whole-candidate retry；任何 invalid candidate 都不得 partial materialize，也不得写 `CONTEXT_COMPACTED`。
- Host README 和 tests README 只同步已落地的稳定事实，不写未来能力。

非目标：

- 不把 issue-81 body 当作 implementation plan。
- 不做 prompt-conditioned recall、semantic search、vector recall、LLM reranker 或 recall tool；owner 是 GitHub Issue #39。
- 不实现跨 session User Profile Memory；owner 是 WU-CM-11 / GitHub Issue #115。
- 不实现完整 eval benchmark；owner 是 WU-CM-10 / GitHub Issue #80。
- 不保留 `working_assumptions` / `pinned_state` 兼容 wrapper、facade 或 re-export。
- 不让 memory snapshot 成为 EventLog、artifacts 或 accepted evidence 的事实真源。
- 不做 provider-specific tokenizer adapter，也不把 usage observation 变成 dispatch 前 budget truth。

## Issue-80 / Design 24.7 Evaluation Mapping

本小节是 WU-CM-01 plan gate 的验收映射。GitHub Issue #80 / WU-CM-10 是完整 eval benchmark 的 deferred owner；WU-CM-01 当前 scope 只负责让 design 24.7 的核心场景在 contract、projection、prompt assembly、context governance 与 public smoke 中具备可断言入口。

| 评测维度 / 可断言场景 | 状态 | Slice | 测试入口 / 验证入口 | 说明 |
|---|---|---:|---|---|
| empty compacted view | current scope covered | 5 | `tests/host/test_run_input_builder.py`、`tests/host/test_public_open_host_multiturn_smoke.py` | 无 accepted compact 时只渲染 selected recent window 与 current input。 |
| non-empty compacted view | current scope covered | 2, 5 | `tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py` | accepted compact output 物化为五类 memory section 后进入 RunInputBuilder。 |
| post-compact delta | current scope covered | 3, 5 | `tests/host/test_compact_material.py`、`tests/host/test_run_input_builder.py` | latest compact cursor 之后的新 material 继续按 bounded recent window 注入。 |
| compact boundary | current scope covered | 3, 4, 5 | `tests/host/test_compact_material.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_run_input_builder.py` | previous compacted view、post-compact delta 与 current input anchor 边界可审计。 |
| protected recent floor | current scope covered | 1, 3, 5 | `tests/host/test_compact_material.py`、`tests/host/test_run_input_builder.py` | policy 提供 floor / cap，保证“刚才”“第二点”等短链路承接。 |
| deterministic bounded projection | current scope covered | 1, 2 | `tests/host/test_memory_projection.py`、`tests/host/test_durable_schema.py` | snapshot 是 EventLog read model，policy digest、cursor 与 item cap 可断言。 |
| provider context length fallback | current scope covered | 4, 5 | `tests/host/test_dispatch_scheduler.py`、`tests/host/test_recovery_dispatch.py`、`tests/host/test_run_input_builder.py` | proactive / reactive fallback 只构造 deterministic recent-window input，不物化 high-order memory。 |
| invalid / missing / stale source label | current scope covered | 1, 3, 4 | `tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py` | parser 与 accept barrier fail closed；current input anchor label 不可引用。 |
| schema invalid | current scope covered | 1, 3, 4 | `tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_context_compact_events.py` | strict JSON 与 event payload validator 只接受 vNext schema。 |
| provenance mismatch | current scope covered | 3, 4 | `tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py` | prompt-local label 必须映射回 Host internal provenance，且不能跨 section 使用。 |
| partial candidate invalid | current scope covered | 4 | `tests/host/test_compaction_operation.py`、`tests/host/test_context_compact_events.py` | 任一 candidate invalid 时 whole-candidate repair；不得 partial materialize。 |
| fallback 不生成高阶语义 | current scope covered | 2, 4, 5 | `tests/host/test_memory_projection.py`、`tests/host/test_dispatch_scheduler.py`、`tests/host/test_run_input_builder.py` | fallback 不写 `CONTEXT_COMPACTED`、不写 compact artifact、不生成 summary / fact / anchor / intent / reference continuity。 |
| compact roll-forward | current scope covered | 2, 3, 5 | `tests/host/test_memory_projection.py`、`tests/host/test_compact_material.py`、`tests/host/test_public_compact_smoke.py` | 第二次及后续 compact 使用 latest accepted compacted view，不重新展开已覆盖旧 raw history。 |
| 完整 Conversation Memory eval benchmark | deferred-with-owner | 6 | GitHub Issue #80 / WU-CM-10 | WU-CM-01 提供可断言入口和 smoke，不实现完整 offline benchmark、指标聚合或 eval runner。 |
| cross-session User Profile / dynamic profile eval | deferred-with-owner | - | GitHub Issue #115 / WU-CM-11；GitHub Issue #80 | WU-CM-01 只固定 User Profile 不进入 session Conversation Memory snapshot。 |
| deep historical recall / semantic search eval | deferred-with-owner | - | GitHub Issue #39；GitHub Issue #80 | 第一阶段不做 prompt-conditioned recall、vector recall、LLM reranker 或 recall tool。 |
| LongMemEval / PersonaMem 原始任务集适配 | explicit non-goal | - | 无 | Dayu eval 以财报分析、证据链、answer anchor、context governance 为真源，不直接绑定外部通用聊天任务集。 |

## Direct Code Evidence

直接证据来自当前代码，而不是 issue body：

- `dayu/host/memory.py` 的 `MemoryProjectionPolicy` 仍有 `max_working_assumptions`、`recent_raw_turns_floor`、`history_pool_*`、`stable_layer_*`；`ConversationMemorySnapshot` 仍包含 `pinned_state`、`evidence_backed_facts`、`working_assumptions`、`conversation_continuity`，与第 24.4 章 `ConversationMemorySnapshotVNext` 不一致。
- `dayu/host/memory.py` 仍定义 `WorkingAssumptionView`、`PinnedStateView`、`MemoryIncludedReason.WORKING_ASSUMPTION`、`ConversationContinuityKind.MINIMUM_PRESERVE_ITEM`，并在 projection 中限制 / 物化这些旧语义。
- `dayu/host/durable/memory.py` 写 snapshot item 时仍写 `working_assumptions` 和旧 continuity item kind；snapshot JSON codec 仍读取 / 写入旧字段。
- `dayu/host/compaction.py` 的 `CompactMaterialPack` 顶层字段仍是 `stable_input`、`history_input`、`evidence_input`、`current_input_anchor`；`CompactMaterialSection` / `CompactMaterialBlockKind` 仍包含 `PINNED_STATE`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`EPISODE_SUMMARY`、`ACCEPTED_TOOL_EVIDENCE` 等旧分类。
- `dayu/host/llm_compaction.py` 仍把 LLM proposal 解析为 `episode_summary_candidate`、`pinned_state_patch_candidate`、`evidence_backed_fact_candidates`、`minimum_preserve_item_candidates`、`preserved_*`；这不是 `ConversationCompactOutputVNext`。
- `dayu/host/context_governance.py` 的 quality checker 仍围绕 pinned patch、minimum preserve、open questions retained 和 preservation evidence 运行，缺少 vNext source-label section allowlist、answer anchor、forward intent、reference continuity item 校验。
- `dayu/host/compact_material.py` 的 `_stable_blocks_from_snapshot()` 从 snapshot 构造 goals、facts、questions_assumptions 三类 stable blocks，并渲染 `working_assumption=`；这与第 24.6 章固定 prompt assembly section 不一致。
- `dayu/host/run_input.py` 的 memory render header 仍是 `Memory user goals and constraints`、`Memory confirmed subjects and methodology`、`Memory evidence-backed facts`、`Memory open questions and working assumptions`、`Memory minimum preserve continuity`、`Memory episode summaries`。
- `tests/host/test_memory_projection.py`、`tests/host/test_compaction_contract.py`、`tests/host/test_compact_material.py`、`tests/host/test_run_input_builder.py`、`tests/README.md` 仍断言旧 `working_assumptions`、stable layer、history pool、minimum preserve 等语义，需要随实现边界迁移。

## Implementation Slices

### Slice Verification Boundary

Slice 1-5 是同一 plan 下的整体 schema / contract 迁移序列，按概念域拆分供 implementation 与 review 聚焦，不承诺每个中间 slice 结束后整个 `dayu/host` 都可通过 pyright。原因是 Slice 1 删除旧 typed contract 后，`durable/memory.py`、`compact_material.py`、`llm_compaction.py`、`context_governance.py`、`run_input.py` 等后续 slice 的 imports / field access 会短暂引用已删除符号。

实施约束如下：

- Slice 1-4 结束后可以做局部 code review、类型定义审查和针对已迁移模块的 focused tests；若全量 pyright 失败，implementation report 必须列出失败是否只来自后续 slice 尚未迁移的旧引用，不得掩盖新增无关类型错误。
- 最早必须恢复 `dayu/host` 生产代码 pyright 可通过的验证点是 Slice 5 结束；此时 typed contract、durable projection、compact material / parser、accept barrier 与 RunInputBuilder 已闭合。
- Slice 6 完成测试、smoke 与 README 同步后，必须运行最终验证命令中的受影响测试与 `python -m pyright dayu/ tests/ utils/`。
- 若 implementation gate 要求每个提交都可编译，则必须把 Slice 1-5 改写为更小的可编译闭环提交；不得通过 compatibility wrapper、旧字段 re-export 或 lazy import 保持表面可编译。
- 若任一 slice 发现前序 contract 需要改变，停止当前 slice，回到 design source / Slice 1 更新真源契约；禁止在当前 slice 做 local adaptation 或兼容分支。

### Slice 1 - Typed Contract And Policy Replacement

目的：先把 Conversation Memory 和 compact I/O 的 typed contract 改到 vNext，给后续 projection、parser、renderer 提供唯一真源。

允许修改的生产模块：

- `dayu/host/memory.py`
- `dayu/host/compaction.py`
- `dayu/host/context_policy.py`，仅当现有 policy 默认值需要对齐 memory section cap / floor 时修改

契约变更：

- 新增 / 替换 `ConversationMemorySnapshotVNext`，字段为 `trace_memory`、`evidence_fact_memory`、`session_summary_memory`、`answer_anchor_memory`、`forward_intent_memory`、`diagnostics`。
- 引入五类 view / item dataclass：`ReferenceContinuityItem`、`EvidenceBackedFact`、`RecentEvidenceReadableItem`、`SessionSummaryMemoryView`、`AnswerAnchor`、`ForwardIntent`。
- 删除旧 `WorkingAssumptionView`、`PinnedStateView` 作为 snapshot 顶层语义的用途；不得保留同名 compatibility wrapper。
- 删除旧 `ConversationContinuityKind`、`ConversationContinuityItem`、`ConversationContinuityView` 整体枚举 / view 语义，不把它们作为 vNext snapshot 或 durable item kind 保留：
  - `RAW_USER_TURN`、`RAW_ASSISTANT_TURN`、`ASSISTANT_CONCLUSION` 迁移为 Trace Memory selected recent window material；它们可被 prompt / compact material 选择，但不作为独立 snapshot item 持久化。
  - `EPISODE_SUMMARY` 由 Session Summary Memory 承接，只能来自 accepted `session_summary` roll-forward view。
  - `MINIMUM_PRESERVE_ITEM` 的语义由 Trace Memory 下的 `ReferenceContinuityItem` 承接；旧 `MinimumPreserveReason.NEEDED_FOR_RECENT_REFERENCE` / `NEEDED_FOR_ORDERED_ITEM_REFERENCE` / `NEEDED_FOR_LOCAL_FOLLOWUP` 不兼容读取，实施时按 vNext 文本语义重新映射为 `ReferenceContinuityItem.reason` 的 `local_reference` / `ordinal_reference` / `ellipsis_recovery` / `recent_state`。
- 将 `MemoryProjectionPolicy` 改为 per-semantic bounded policy：summary char cap、evidence fact cap / floor、answer anchor cap、forward intent cap、reference continuity cap / floor、selected recent window cap / floor、inline delta repair limits。
- 新增 / 替换 `ConversationCompactInputVNext` 与 `ConversationCompactOutputVNext` typed dataclass，顶层字段按 design source 固定。
- `ConversationCompactOutputVNext` candidate schema 以 `docs/host/design.md` 24.3 为唯一真源：`schema_version="conversation_compact_output_v1"`，顶层字段只允许 `session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`；candidate 子结构、枚举、nullable / list 规则、source label 允许集合与 char cap 均不得从旧 parser 或 issue body 推断。
- compact candidate enum / validator 必须表达 source label section 规则：fact 只能引用 evidence labels，answer anchor 只能引用 answer labels，forward intent / reference continuity 只能引用允许 section，current input anchor label 不可引用。
- 删除旧 compact candidate / patch / evidence 类型，不做 wrapper 或 re-export：`EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`PreservationEvidence`、`PinnedPatchOperation`、`PinnedStringTupleFieldPatch`、`PinnedTextFieldPatch`、`MinimumPreserveReason`。
- 删除旧 `CompactQualityIssue` 中服务旧 pinned / preserve / open question contract 的枚举值：`PRESERVATION_EVIDENCE_MISSING`、`EVIDENCE_ANCHOR_NOT_RETAINED`、`PINNED_PATCH_TRI_STATE_INVALID`、`PINNED_PATCH_EVIDENCE_REF_MISSING`、`MINIMUM_PRESERVE_ITEM_CANDIDATE_INVALID`、`OPEN_QUESTIONS_MISSING`、`SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT`、`EVIDENCE_LABELS_MISSING`；替换为 Slice 4 的 vNext issue set。
- `MemoryProjectionDiagnostics` vNext 不能保留 minimum preserve 专属 reason；旧 `MINIMUM_PRESERVE_ITEM_COVERED` 迁移为 reference continuity 预算 / 覆盖语义的 vNext reason，旧 pinned / working assumption 专属 diagnostic 不得保留。可保留或重命名的 reason 必须只表达 vNext 语义：snapshot missing / damaged / lag、unsupported event、budget limit、inline delta repair、fact candidate invalid / superseded、reference continuity covered。

测试：

- 更新 `tests/host/test_memory_projection.py`：snapshot dataclass validation、digest、JSON round-trip、policy digest、旧 key fail-closed。
- 更新 `tests/host/test_compaction_contract.py`：vNext input/output dataclass、source label allowlist、current input anchor not citable、enum / non-empty / char cap validation。
- 更新 `tests/host/fake_compaction.py`：fake compactor 产出 vNext candidate。
- 删除或迁移旧 `working_assumptions`、`pinned_state_patch_candidate`、`minimum_preserve_item_candidates` 断言。

退出信号：

- 类型层不再暴露旧 snapshot shape 给新实现路径。
- policy digest 不含 `max_working_assumptions`、`history_pool_*`、`stable_layer_*`。
- vNext dataclass 能被 tests 直接构造并覆盖非法 source label。
- `ConversationContinuityKind`、旧 compact candidate 类型、旧 pinned / preserve / open question quality issue 枚举不再存在于新的 typed contract。

### Slice 2 - Durable Snapshot Store And Projection Migration

目的：让 durable memory snapshot / item rows 和 projection consumer 消费 vNext canonical compact event，不再写旧 working assumption / pinned state item。

允许修改的生产模块：

- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/host/memory_repair.py`，仅当 catch-up / rebuild 类型签名需要跟随 snapshot vNext

schema / storage 边界：

- 按项目 schema 约束以全新 schema 起库处理，不写旧库兼容读取或兼容测试。
- 若 hot table 的 `item_kind` CHECK 列表需要变化，直接迁移为 vNext item kind：`reference_continuity_item`、`evidence_backed_fact`、`recent_evidence_item`、`session_summary`、`answer_anchor`、`forward_intent`。
- 全新 schema 删除旧 durable item kind：`raw_user_turn`、`raw_assistant_turn`、`assistant_conclusion`、`episode_summary`、`minimum_preserve_item`、`working_assumption`、`pinned_state`。旧库 row 不做兼容读取；旧语义只在新实现的数据生产规则中迁移到 vNext memory section。
- snapshot JSON 只写 vNext 字段；旧 JSON key `pinned_state`、`working_assumptions`、`conversation_continuity` 必须 fail closed。
- snapshot 与 projection checkpoint 仍必须同一 durable transaction 提交；checkpoint 不得先于 snapshot。

实现要求：

- compact 前 projection 只能形成 selected recent window 可读材料，不自动生成 session summary、answer anchor、forward intent 或 evidence-backed facts。
- accepted `CONTEXT_COMPACTED` 后，projection 从 accepted compact payload / artifact materialize 五类 memory。
- invalid / rejected / failed compaction event 不进入 memory projection；fallback 不 materialize snapshot 高阶 item。
- accepted evidence 存在但无合法 fact candidate 时只记录 diagnostic，不合成 fallback fact。
- assistant final answer、用户输入、summary、anchor、reference continuity、User Profile、Forward Intent 都不能升级成 evidence-backed fact。

测试：

- 更新 `tests/host/test_memory_projection.py`：durable snapshot + checkpoint atomicity、snapshot row codec、item rows、projection catch-up / rebuild、fallback no-materialization、accepted compact roll-forward、多次 compact latest view。
- 更新 `tests/host/test_durable_schema.py`，如果 schema CHECK / table shape 变化。
- 更新 `tests/host/test_durable_concurrency_matrix.py`，如果 memory snapshot + checkpoint CAS shape 变化。
- 更新 `tests/host/test_memory_repair.py`，如果 repair request / snapshot cursor 类型变化。

退出信号：

- durable store 读写 vNext snapshot 和 vNext items。
- 旧 `working_assumption` item kind 不再由 projection 写入。
- 旧 `ConversationContinuityKind` 不再作为 durable item kind 或 snapshot field 存在；minimum preserve 语义只以 `ReferenceContinuityItem` 的 vNext item 形态出现。
- projection consumer 能从 EventLog 重建同一 snapshot digest。

### Slice 3 - Compact Material VNext And LLM Parser

目的：把 compactor 输入、prompt-local label mapping、strict JSON parser 和 material selection 迁移到 `ConversationCompactInputVNext` / `ConversationCompactOutputVNext`。

允许修改的生产模块：

- `dayu/host/compact_material.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/compaction_evidence.py`，仅当 evidence readable item 需要调整
- `dayu/host/compact_payload.py`，仅当 compact payload helper 仍引用旧 candidate key

契约变更：

- compact material pack 顶层 section 改为 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`、`instruction`。
- `previous_compacted_view` 只来自 latest accepted compacted view 的业务可读 projection，不包含 raw compact artifact JSON。
- `current_input_anchor` readable but not citable；同一 current user payload 不得重复进入 trace material。
- 维护 prompt-local label 到 canonical provenance 的内部映射，禁止把 durable refs / digest / event id 作为 LLM-readable 主体。label 格式只允许作为 opaque handle；`C1`、`E1`、`E1.1` 等短 deterministic label 不承载业务类型、顺序、优先级、时间或 durable identity 语义，validator / tests 只能验证 label 可映射回 provenance，不能按 label 名称推断事实含义。
- LLM parser 只接受 `schema_version="conversation_compact_output_v1"`，字段为 `session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`。candidate schema 以 design 24.3 为唯一真源，包括：
  - `SessionSummaryCandidate(summary_text, source_labels)`。
  - `EvidenceBackedFactCandidate(claim_text, evidence_labels, evidence_kind, source_labels?)`，`evidence_kind` 只允许 `tool_result`、`tool_source_text`、`accepted_evidence_material`。
  - `AnswerAnchorCandidate(anchor_title, anchor_items, answer_source_labels)` 与 `AnswerAnchorChild(display_text, ordinal?)`。
  - `ForwardIntentCandidate(intent_type, text, status, source_labels)`，`intent_type` 只允许 `open_question`、`pending_clarification`、`pending_user_visible_task`、`next_step_note`，`status` 只允许 `open`、`blocked`、`superseded`。
  - `ReferenceContinuityCandidate(text, reason, source_labels)`，`reason` 只允许 `local_reference`、`ordinal_reference`、`ellipsis_recovery`、`recent_state`。
  - `CompactCandidateDiagnostic(code, text, source_labels?)`。
- parser 对未知 label、跨 section label、缺 source label、空文本、非法枚举、current input anchor 被引用全部 fail closed。

旧 compact material block kind 到 vNext section 的迁移表：

| 旧 `CompactMaterialBlockKind` | vNext section / 处置 | 说明 |
|---|---|---|
| `PINNED_STATE` | 删除 | 不再作为 compact material；合法目标 / 约束 / 状态语义必须由 accepted vNext summary、fact、answer anchor 或 forward intent 承接。 |
| `EVIDENCE_BACKED_FACT` | `previous_compacted_view.evidence_backed_facts` | 仅当它来自 latest accepted compacted view 的 vNext projection；不得作为 raw evidence material 重复渲染。 |
| `WORKING_ASSUMPTION` | 删除 | `working_assumptions` 不是 vNext session memory category。 |
| `OPEN_QUESTION` | `previous_compacted_view.forward_intents` 或删除 | 只有 accepted vNext `ForwardIntentCandidate(intent_type="open_question")` 可进入 previous compacted view；旧 open question block kind 删除。 |
| `RAW_USER_TURN` | `trace_material` | 当前用户输入必须进入 `current_input_anchor`，不得再作为 `trace_material` 重复出现。 |
| `RAW_ASSISTANT_TURN` | `trace_material` 或 `answer_material` | 作为对话连续性时进 `trace_material`；作为 answer anchor source 的 final answer / conclusion 进 `answer_material`；同一 canonical content 不得同时进入两个 section。 |
| `EPISODE_SUMMARY` | `previous_compacted_view.session_summary` 或删除 | 只有 accepted vNext `session_summary` roll-forward view 可进入 previous compacted view；旧 episode summary block kind 删除。 |
| `ACCEPTED_TOOL_EVIDENCE` | `evidence_material` | 只渲染 accepted tool evidence 的可读 tool / query / response / source text 与 prompt-local evidence label。 |
| `CURRENT_INPUT_ANCHOR` | `current_input_anchor` | readable but not citable；其 label 不属于任何 candidate allowed source label set。 |

测试：

- 更新 `tests/host/test_compact_material.py`：vNext material sections、one-section-per-canonical-content、current input 去重、selected recent floor、evidence fact floor、snapshot cursor lag repair-required、already represented old raw turns 不重复展开。
- 更新 `tests/host/test_llm_compaction.py`：strict JSON vNext parser、invalid label / stale label / current anchor citation、answer anchor / forward intent / reference continuity parsing、失败摘要脱敏。
- 更新 `tests/host/test_compaction_contract.py`：label provenance mapping 和 llm_json 不泄漏 durable refs。
- 更新 `tests/host/fake_compaction.py`：按 vNext material 生成 deterministic candidate。

退出信号：

- compactor request material JSON 和 parser 输出都使用 vNext schema。
- 旧 `stable_input`、`history_input`、`evidence_input` 不再作为 compactor typed contract 顶层字段。
- fake compactor 能覆盖 fact、answer anchor、forward intent、reference continuity 的 happy path。

### Slice 4 - Accept Barrier, Whole-Candidate Repair, And Fallback Governance

目的：把 quality checker 与 compaction operation 的 retry / failure / fallback 行为对齐 design source，确保 invalid candidate 不被 partial materialize。

允许修改的生产模块：

- `dayu/host/context_governance.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`，仅当 payload builder / validator 需要 vNext字段
- `dayu/host/dispatch.py`，仅限 proactive / reactive operation 编排与 fallback 输入选择
- `dayu/host/context_fallback.py`，仅限 recent-window fallback view 语义对齐

契约变更：

- quality result 记录 vNext validation issues：schema invalid、unknown source label、stale source label、missing source label、cross-section label、current input anchor cited、provenance mismatch、source boundary violation、fact candidate invalid、answer anchor invalid、forward intent invalid、reference continuity invalid、diagnostic invalid、budget reject。
- source label allowlist 必须按 section 校验：
  - `SessionSummaryCandidate.source_labels` 可引用 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material` 中存在的 labels，但不得引用 `current_input_anchor.anchor_label`。
  - `EvidenceBackedFactCandidate.evidence_labels` 只能引用 `evidence_material` labels；可选 `source_labels` 若存在，也只能是同一 fact 可解释所需的 allowed labels，不能把 user input、assistant answer、summary、anchor 或 intent 冒充 evidence。
  - `AnswerAnchorCandidate.answer_source_labels` 只能引用 `answer_material` labels。
  - `ForwardIntentCandidate.source_labels` 可引用 `trace_material`、`answer_material` 或 `previous_compacted_view.forward_intents` / `session_summary` 对应 labels；不得引用 evidence label 来制造待办事实，也不得自动触发工具。
  - `ReferenceContinuityCandidate.source_labels` 可引用 `trace_material`、`answer_material` 或 `previous_compacted_view.reference_continuity_items` 对应 labels，只能保存局部指代所需最小文本。
  - `CompactCandidateDiagnostic.source_labels` 若存在，只能引用与诊断对象同 section 的 allowed labels；`current_input_anchor.anchor_label` 始终不可引用。
- cross-section citation、label 到 Host internal provenance 映射不一致、label digest / source boundary 不匹配、stale label、unknown label、缺少必需 source label 均 fail closed；不得用 label 前缀、序号或字符串格式推断业务 section。
- 旧 `check_compaction_candidate(request, candidate)` 入口改为 vNext accept barrier 入口，等价签名为 `check_compaction_candidate(request: CompactionRequestVNext, candidate: ConversationCompactOutputVNext) -> CompactQualityResult`；不提供旧 `CompactionCandidate` overload，不解析 `pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preservation_evidence` 或旧 open question 字段。
- `CompactQualityIssue` vNext 枚举以 accept barrier 规则为真源，至少包含 schema / label / provenance / candidate / budget 类拒绝原因；旧 pinned / minimum preserve / open question / preservation evidence 专属 issue 必须删除，不能作为新 issue 的兼容别名。
- repair attempt 必须 whole-candidate re-proposal；Host 可以提供多个 Host-neutral invalid reasons，但不得要求 patch，不合并旧 proposal valid fields。
- reactive multi-pass compact 与 whole-candidate repair 共用一次 operation 的 `max_compaction_attempts_per_operation` 总预算，预算包含第一次 proposal、每个 material block pass proposal 和 semantic repair attempts。WU-CM-01 Slice 4 覆盖 operation-level budget accounting、attempt rejected diagnostic、失败后单个最终 `CONTEXT_COMPACTION_FAILED` 与 partial compact 禁止；不得把中间 pass 产物提交为孤立 `CONTEXT_COMPACTED`。
- retry budget 耗尽只写最终 `CONTEXT_COMPACTION_FAILED`；不得写 `CONTEXT_COMPACTED`，不得让 memory projection 消费 rejected candidate。
- fallback 不是 compact success：不写 compact artifact，不 materialize memory snapshot，不生成 summary / fact / anchor / intent / reference continuity。
- proactive fallback 不让 Run 进入 `RECOVERING`；reactive fallback 使用新 Attempt / execution id，仍不得写 `RUN_LOST`。

测试：

- 更新 `tests/host/test_compaction_operation.py`：多个 invalid reasons 触发一次 whole-candidate repair、rejected candidate 不被部分采用、repair exhausted fail closed、accepted attempt number / candidate digest。
- 更新 `tests/host/test_context_compact_events.py`：vNext `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` payload builder / validator。
- 更新 `tests/host/test_dispatch_scheduler.py`：proactive / reactive compact failure recent-window fallback、over-budget fail closed、不写 `CONTEXT_COMPACTED`、不写 `RUN_LOST`。
- 更新 `tests/host/test_recovery_dispatch.py`：reactive compact recovery attempt identity。
- 更新 `tests/host/_context_compaction_assertions.py`：共享断言迁移到 vNext。

退出信号：

- fact-only invalid 与 non-fact invalid 都触发同一 fail closed / whole-candidate repair 策略。
- source label allowlist、current input anchor not citable、cross-section citation、provenance mismatch 与 vNext quality issue migration 均由 accept barrier 测试覆盖。
- fallback 路径只有 bounded recent window 和 current input，且有 failure diagnostic。
- Context Governance 仍只是 orchestrator，不直接写 memory snapshot。

### Slice 5 - RunInputBuilder Prompt Assembly VNext

目的：让普通 Agent request messages 按第 24.6 章固定顺序从 vNext snapshot、post-compact delta 和 current input 重建。

允许修改的生产模块：

- `dayu/host/run_input.py`
- `dayu/host/compact_material.py`，仅限共享 ordinary material / selected recent window helper
- `dayu/host/dispatch.py`，仅限调用 RunInputBuilder 所需的 memory / fallback view 参数

契约变更：

- `MemorySnapshotView` 改为 vNext readable section view，记录 snapshot cursor、policy digest、diagnostics、represented evidence refs。
- prompt assembly 固定顺序：system / scene、Session Summary、Evidence / Fact、Answer Anchor、Forward Intent、Trace reference continuity、selected recent window、current input、replay / retry / steer / resume guidance、tool schema / policy。
- no accepted compacted view：只渲染 selected recent window 和 current input。
- compact failed fallback：只渲染 fallback selected recent window 和 current input。
- accepted compacted view：渲染五类 memory section + selected recent window after compact boundary + current input。
- 第一阶段不做 runtime token estimator 逐 section 裁剪；section 在 projection / assembly 前由 cap / floor bounded。

测试：

- 更新 `tests/host/test_run_input_builder.py`：empty compacted view、non-empty compacted view、post-compact delta、compact boundary、fixed section order、fallback no high-order memory、memory snapshot repair-required。
- 更新 `tests/host/test_public_compact_smoke.py`：public opener proactive compact 后 memory 注入链路、fallback recent-window rendering。
- 更新 `tests/host/test_public_open_host_multiturn_smoke.py`：普通多轮 continuity。
- 更新 `tests/host/test_public_tool_wiring_smoke.py`，如果 accepted evidence material prompt 行为变化。

退出信号：

- RunInputBuilder 不再输出 goals / facts / questions_assumptions 旧 stable block headers。
- memory snapshot lag 仍触发 catch-up / rebuild / repair path，不把 Run 推入 `RECOVERING`。
- final messages 能从 durable facts、snapshot 和 current input 重建，不复用失败 Attempt provider payload。

### Slice 6 - Public Smokes, README Sync, And Issue-80 Mapping

目的：完成外部可见验收、文档同步和 residual risk owner 标注，不扩大到完整 eval benchmark。

允许修改的文件：

- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`
- `dayu/host/README.md`
- `tests/README.md`
- 相关 `tests/host/*` smoke / support 文件

要求：

- smoke 仍走 Host public path，不绕过 public API 或 scheduler。
- README 只写当前代码已落地事实，不写路线图；Host README 记录 vNext Conversation Memory / Context Governance 稳定边界，tests README 记录新增 / 迁移后的测试事实和命令。
- 复核本 plan 的 `Issue-80 / Design 24.7 Evaluation Mapping` 小节与最终实现一致；若 implementation 发现某个 current scope covered 项无法满足，必须回到 plan / design 修正，不得只在 implementation report 中降级。

测试：

- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`
- `tests/host/test_public_open_host_multiturn_smoke.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_memory_projection.py`

退出信号：

- public smoke 全部通过。
- README 与当前实现一致，旧术语清理完成。
- residual risks 均有 owner / destination。

## Allowed Files / Modules Summary

Implementation gate 可以按 slice 修改：

- `dayu/host/memory.py`
- `dayu/host/run_input.py`
- `dayu/host/compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/compact_material.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/dispatch.py`
- `dayu/host/durable/memory.py`
- `dayu/host/context_events.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_fallback.py`
- `dayu/host/memory_repair.py`
- `dayu/host/compaction_evidence.py`
- `dayu/host/compact_payload.py`
- `tests/host/*` 中与 memory、compact、context governance、RunInputBuilder、public smoke 直接相关的测试文件
- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`
- `dayu/host/README.md`
- `tests/README.md`

禁止修改或新增：

- `dayu.service`、`dayu.ui`、`dayu.fins`、`dayu.engine`，除非后续 gate 发现设计真源必须先变更并经用户确认。
- recall / search / vector / reranker / recall tool 相关实现。
- User Profile durable store 或跨 session profile contract。
- 为旧字段保留的 compatibility wrapper、facade、re-export 或旧库兼容读取。

## Test Matrix

核心 contract / projection：

- `pytest tests/host/test_memory_projection.py -q`
- `pytest tests/host/test_compaction_contract.py -q`
- `pytest tests/host/test_context_compact_events.py -q`
- `pytest tests/host/test_compact_material.py -q`
- `pytest tests/host/test_llm_compaction.py -q`
- `pytest tests/host/test_context_governance.py -q`，若该文件不存在则以 `tests/host/test_compaction_contract.py` 和 `tests/host/test_compaction_operation.py` 覆盖 quality checker。

operation / dispatch / recovery：

- `pytest tests/host/test_compaction_operation.py -q`
- `pytest tests/host/test_dispatch_scheduler.py -q`
- `pytest tests/host/test_recovery_dispatch.py -q`
- `pytest tests/host/test_run_input_builder.py -q`
- `pytest tests/host/test_context_budget.py -q`
- `pytest tests/host/test_context_policy.py -q`

durable / schema：

- `pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_durable_concurrency_matrix.py -q`
- `pytest tests/host/test_memory_repair.py -q`，若文件不存在则以 `tests/host/test_memory_projection.py` 中 repair / rebuild cases 覆盖。

public smoke / integration：

- `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q`
- `python utils/smoke_host_public_conversation_memory.py`
- `python utils/smoke_host_public_conversation_memory_scenarios.py`
- `python utils/smoke_host_public_multiturn.py`

README / guard：

- `pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
- `pytest tests/host/test_package_exports.py -q`，仅当 public exports 变化。
- `pytest tests/host -q` 作为 Host 全量回归。

最终验证命令：

```bash
source .venv/bin/activate
pytest tests/host/test_memory_projection.py tests/host/test_compaction_contract.py tests/host/test_compact_material.py tests/host/test_llm_compaction.py tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q
python utils/smoke_host_public_conversation_memory.py
python utils/smoke_host_public_conversation_memory_scenarios.py
python utils/smoke_host_public_multiturn.py
pytest tests/host -q
python -m pyright dayu/ tests/ utils/
```

本 plan gate 不运行上述命令；implementation / fix gate 必须运行受影响测试与 pyright。

## README / Doc Sync Triggers

- 修改 `dayu/host/`：必须检查并按职责更新 `dayu/host/README.md`。只写已落地的 Host Conversation Memory / Context Governance 契约、执行路径、状态边界和扩展点，不写未来 eval 或 recall 能力。
- 修改 `tests/`：必须检查并按职责更新 `tests/README.md`。只同步当前测试分层、运行命令和维护规则。
- 修改 `utils/smoke_host_public_*`：如果用户手册中的 smoke 命令或 public workflow 发生变化，再更新根目录 `README.md`；若只是脚本内部断言迁移，不更新根 README。
- 不更新 `dayu/README.md`，除非 implementation 实际改变 `UI -> Service -> Host -> Engine` 分层关系或装配边界。
- 不更新 `dayu/fins/README.md`，因为 WU-CM-01 不改变 Fins storage 或财报事实真源。

## Residual Risks And Owners

- 完整 Conversation Memory eval benchmark：deferred-with-owner，WU-CM-10 / GitHub Issue #80。WU-CM-01 只保证可断言入口和初步 smoke，不实现完整 benchmark。
- Cross-session User Profile Memory：deferred-with-owner，WU-CM-11 / GitHub Issue #115。WU-CM-01 只固定不混入 session memory 的边界。
- Deep historical recall / semantic search / vector recall / reranker / recall tool：deferred-with-owner，GitHub Issue #39。
- Provider-specific tokenizer adapter：deferred-with-owner，后续 Context Governance 精确预算 work unit。WU-CM-01 保持 conservative estimator。
- Fins fact grounding integration：deferred-with-owner，Fins integration work unit。WU-CM-01 保证 memory snapshot 不替代 accepted evidence / artifacts / Fins storage truth。
- Schema old DB upgrade：explicit non-goal。按仓库 schema 约束，本 work unit 以全新 schema 起库，不写旧库兼容读取。

## Blocking Open Questions

当前没有阻塞 code-generation-ready plan 的 open question。若 implementation agent 在 Slice 1 或 Slice 2 发现第 24 / 25 章无法唯一裁决某个 public contract、durable schema、EventLog payload 或状态机语义，应停止 implementation，回到 design source 更新，而不是在生产代码里自行发明兼容路径。
