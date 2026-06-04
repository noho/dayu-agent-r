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
| empty compacted view | current scope covered | D, E | `tests/host/test_run_input_builder.py`、`tests/host/test_public_open_host_multiturn_smoke.py` | 无 accepted compact 时只渲染 selected recent window 与 current input。 |
| non-empty compacted view | current scope covered | C, D | `tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py` | accepted compact output 物化为五类 memory section 后进入 RunInputBuilder。 |
| post-compact delta | current scope covered | A, C, D | `tests/host/test_compact_material.py`、`tests/host/test_run_input_builder.py` | latest compact cursor 之后的新 material 继续按 bounded recent window 注入。 |
| compact boundary | current scope covered | A, B, C, D | `tests/host/test_compact_material.py`、`tests/host/test_compaction_operation.py`、`tests/host/test_run_input_builder.py` | previous compacted view、post-compact delta 与 current input anchor 边界可审计。 |
| protected recent floor | current scope covered | A, C, D | `tests/host/test_compact_material.py`、`tests/host/test_run_input_builder.py` | policy 提供 floor / cap，保证“刚才”“第二点”等短链路承接。 |
| deterministic bounded projection | current scope covered | C | `tests/host/test_memory_projection.py`、`tests/host/test_durable_schema.py` | snapshot 是 EventLog read model，policy digest、cursor 与 item cap 可断言。 |
| provider context length fallback | current scope covered | B, D | `tests/host/test_dispatch_scheduler.py`、`tests/host/test_recovery_dispatch.py`、`tests/host/test_run_input_builder.py` | proactive / reactive fallback 只构造 deterministic recent-window input，不物化 high-order memory。 |
| invalid / missing / stale source label | current scope covered | A, B | `tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py` | parser 与 accept barrier fail closed；current input anchor label 不可引用。 |
| schema invalid | current scope covered | A, B | `tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_context_compact_events.py` | strict JSON 与 event payload validator 只接受 vNext schema。 |
| provenance mismatch | current scope covered | A, B | `tests/host/test_compaction_contract.py`、`tests/host/test_llm_compaction.py`、`tests/host/test_compaction_operation.py` | prompt-local label 必须映射回 Host internal provenance，且不能跨 section 使用。 |
| partial candidate invalid | current scope covered | B | `tests/host/test_compaction_operation.py`、`tests/host/test_context_compact_events.py` | 任一 candidate invalid 时 whole-candidate repair；不得 partial materialize。 |
| fallback 不生成高阶语义 | current scope covered | B, C, D | `tests/host/test_memory_projection.py`、`tests/host/test_dispatch_scheduler.py`、`tests/host/test_run_input_builder.py` | fallback 不写 `CONTEXT_COMPACTED`、不写 compact artifact、不生成 summary / fact / anchor / intent / reference continuity。 |
| compact roll-forward | current scope covered | B, C, D, E | `tests/host/test_memory_projection.py`、`tests/host/test_compact_material.py`、`tests/host/test_public_compact_smoke.py` | 第二次及后续 compact 使用 latest accepted compacted view，不重新展开已覆盖旧 raw history。 |
| 完整 Conversation Memory eval benchmark | deferred-with-owner | E | GitHub Issue #80 / WU-CM-10 | WU-CM-01 提供可断言入口和 smoke，不实现完整 offline benchmark、指标聚合或 eval runner。 |
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

WU-CM-01 的 implementation slices 必须是可编译、可验证、pyright-clean 的纵向闭环。每个 slice 结束时都必须满足：

- `source .venv/bin/activate` 后运行该 slice 受影响测试并通过。
- `source .venv/bin/activate` 后运行 `python -m pyright dayu/ tests/ utils/`，不得新增或扩散错误。
- 本 slice 已切换到 vNext 的生产路径，其 production consumers 与测试必须同步迁移。
- 未切换的旧路径可以原样存在到它的 owner slice；不得新增 bridge wrapper、compatibility facade、旧字段 re-export、旧库兼容读取或 lazy import seam。
- 如果某个 slice 发现 vNext contract 需要改变，停止当前 slice，回到 design source / plan 修正；禁止在实现中发明局部兼容分支。

这些 slice 不再按“类型、持久化、parser、operation、prompt”概念域单独拆分，而按每条可运行路径闭合。目标是让任一 accepted slice commit 都能被 review、pytest 与 pyright 独立验证。

### Slice A - Compact Contract Closure

目标：先在 compactor request / material / parser / accept barrier 的局部闭环内建立 vNext compact I/O，旧 production operation 暂不切换。此 slice 只允许新增未接线或局部接线的 vNext compact contract，并用 contract tests 验证；不得删除仍被旧 operation、memory projection 或 RunInputBuilder 使用的旧 production contract。

allowed files/modules：

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/context_policy.py`，仅当 vNext compact policy cap / floor 需要同源默认值
- `tests/host/test_compaction_contract.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compact_material.py`
- `tests/host/fake_compaction.py`

实现边界：

- 引入 `ConversationCompactInputVNext` 与 `ConversationCompactOutputVNext` typed dataclass，顶层字段按 design 24.3 固定为 `previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`、`instruction` 与 `session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`。
- candidate schema 以 `docs/host/design.md` 24.3 为唯一真源：`schema_version="conversation_compact_output_v1"`；candidate 子结构、枚举、nullable / list 规则、source label 允许集合与 char cap 不从旧 parser 或 issue body 推断。
- compact material vNext section 必须维护 prompt-local label 到 Host internal provenance 的内部映射；LLM-readable material 不得暴露 durable refs、event id、digest、artifact refs 或 policy internals。
- `current_input_anchor` readable but not citable；其 label 不属于任何 candidate allowed source label set。
- parser / contract validator 必须 fail closed：未知 label、stale label、跨 section label、缺必需 source label、空文本、非法枚举、current input anchor 被引用都拒绝。
- `check_compaction_candidate` 可以新增 vNext 专用入口或内部 helper，但不得提供旧 `CompactionCandidate` overload，也不得解析 `pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preservation_evidence` 或旧 open question 字段。
- `CompactQualityIssue` 可以新增 vNext issue set；旧 pinned / minimum preserve / open question / preservation evidence 专属 issue 在旧 production path 未切换前可原样保留，但不得作为 vNext issue 的兼容别名。

旧路径保留 / 删除边界：

- 旧 `stable_input`、`history_input`、`evidence_input`、旧 `CompactionCandidate` 与旧 quality issue 可为尚未切换的 production operation 原样存在到 Slice B；Slice A 不得新增 wrapper 把 vNext 转回旧 candidate，也不得新增 re-export 让旧字段伪装成 vNext 字段。
- 旧 compact material block kind 到 vNext section 的迁移表在 Slice A 固定为实施规则：`PINNED_STATE` / `WORKING_ASSUMPTION` 删除；`EVIDENCE_BACKED_FACT` 只可进入 `previous_compacted_view.evidence_backed_facts`；`OPEN_QUESTION` 只可由 accepted vNext forward intent 承接；`RAW_USER_TURN` 进入 `trace_material`，但 current input 必须只进入 `current_input_anchor`；`RAW_ASSISTANT_TURN` 在 trace / answer 二选一；`EPISODE_SUMMARY` 只由 accepted vNext session summary 承接；`ACCEPTED_TOOL_EVIDENCE` 进入 `evidence_material`；`CURRENT_INPUT_ANCHOR` 不可引用。
- `MinimumPreserveReason.NEEDED_FOR_RECENT_REFERENCE` / `NEEDED_FOR_ORDERED_ITEM_REFERENCE` / `NEEDED_FOR_LOCAL_FOLLOWUP` 不做兼容读取；其业务语义在 vNext 中重新映射为 `ReferenceContinuityCandidate.reason` 的 `local_reference` / `ordinal_reference` / `ellipsis_recovery` / `recent_state`。

不得引入：

- `EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`PreservationEvidence`、`PinnedPatchOperation`、`PinnedStringTupleFieldPatch`、`PinnedTextFieldPatch`、`MinimumPreserveReason` 的 vNext wrapper、facade 或 re-export。
- 通过 `hasattr` / `getattr`、无类型 `dict[str, object]`、`Any`、lazy import 或 extra payload 暂存显式字段来跨越旧 / 新 contract。

测试命令：

```bash
source .venv/bin/activate
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py -q
python -m pyright dayu/ tests/ utils/
```

退出信号：

- vNext compact input/output dataclass 可由 tests 直接构造并通过 JSON round-trip / strict parse。
- fake compactor 能产出 deterministic vNext candidate，覆盖 fact、answer anchor、forward intent、reference continuity happy path。
- label provenance mapping、current input anchor not citable、cross-section label 与 stale label 均有 fail-closed 测试。
- pyright 全量通过，且旧 production operation 仍按旧 path 可编译，不通过 bridge 使用 vNext。

residual risks：

- operation event payload、repair budget、memory projection 与 RunInputBuilder 尚未切换；分类为 covered by later approved slice，owner 分别是 Slice B、C、D。
- 完整 Conversation Memory eval benchmark 仍 deferred-with-owner，owner 是 WU-CM-10 / GitHub Issue #80。

### Slice B - Compact Operation And Event Closure

目标：把生产 compaction operation、event payload、compact payload helper、fake compactor 和 operation tests 同步切换到 vNext candidate，删除旧 candidate merge / pinned patch / minimum preserve operation 逻辑，确保 accepted / rejected / failed compaction 都是 vNext 事件闭环。

allowed files/modules：

- `dayu/host/compaction.py`
- `dayu/host/compact_material.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `dayu/host/compact_payload.py`
- `dayu/host/dispatch.py`，仅限 proactive / reactive compaction operation 编排
- `dayu/host/context_fallback.py`，仅限 compaction failure 后 recent-window fallback view
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/_context_compaction_assertions.py`
- `tests/host/fake_compaction.py`

实现边界：

- `ContextCompactor`、operation attempt result、quality gate、attempt rejected diagnostic、`CONTEXT_COMPACTED` 与 `CONTEXT_COMPACTION_FAILED` payload 全部使用 vNext compact output。
- `CONTEXT_COMPACTED` payload 至少记录 operation id、accepted attempt number、accepted candidate digest、compact artifact ref、prompt-local label mapping refs、source boundary refs、accepted evidence mapping refs、quality check result、budget after compact 与 projection signal。
- quality result 记录 vNext validation issues：schema invalid、unknown source label、stale source label、missing source label、cross-section label、current input anchor cited、provenance mismatch、source boundary violation、fact candidate invalid、answer anchor invalid、forward intent invalid、reference continuity invalid、diagnostic invalid、budget reject。
- source label allowlist 必须按 section 校验：fact 只能引用 evidence labels；answer anchor 只能引用 answer labels；forward intent / reference continuity 只能引用 design 24.3 允许 section；diagnostic label 只能引用诊断对象同 section 的 allowed labels；current input anchor 始终不可引用。
- reactive multi-pass compact 与 whole-candidate repair 共用一次 operation 的 `max_compaction_attempts_per_operation` 总预算；预算包含第一次 proposal、每个 material block pass proposal 和 semantic repair attempts。
- repair attempt 必须 whole-candidate re-proposal；Host 可提供多个 Host-neutral invalid reasons，但不得要求 patch，不合并旧 proposal valid fields。
- retry budget 耗尽只写最终 `CONTEXT_COMPACTION_FAILED`；不得写 `CONTEXT_COMPACTED`，不得让 memory projection 消费 rejected candidate。
- fallback 不是 compact success：不写 compact artifact，不 materialize memory snapshot，不生成 summary / fact / anchor / intent / reference continuity；proactive fallback 不让 Run 进入 `RECOVERING`，reactive fallback 使用新 Attempt / execution id 且不得写 `RUN_LOST`。

旧路径保留 / 删除边界：

- 一旦 operation 切换到 vNext，必须删除或迁移 operation path 中旧 `pinned_state_patch_candidate`、`minimum_preserve_item_candidates`、`preserved_*`、`preservation_evidence`、旧 candidate merge 与旧 payload validator；不得保留旧字段作为事件兼容入口。
- 尚未切换的 memory snapshot / durable item / RunInputBuilder 旧字段可原样存在到 Slice C / D；Slice B 不得新增 payload wrapper 或 projection shim 来把 vNext compact event 写回旧 memory shape。
- fallback recent-window view 只能影响本次 dispatch 输入选择；不得写 memory snapshot 或旧 compact artifact。

不得引入：

- `CONTEXT_COMPACTED` 旧字段 re-export、旧 payload facade、旧 candidate 到 vNext 的双向 adapter。
- 为保持 pyright 通过而新增的 lazy import seam、字符串字段探测、`extra` payload 字段或 untyped event payload。

测试命令：

```bash
source .venv/bin/activate
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py -q
python -m pyright dayu/ tests/ utils/
```

退出信号：

- accepted compact、attempt rejected、repair exhausted 与 fallback failure event 都使用 vNext payload 并通过 validator。
- fact-only invalid 与 non-fact invalid 都触发同一 fail closed / whole-candidate repair 策略，不 partial materialize。
- operation-level attempt number、candidate digest、quality issues 与 budget accounting 有测试断言。
- pyright 全量通过，且 operation production consumers 不再引用旧 compact candidate 字段。

residual risks：

- vNext compact event 已提交但 memory durable/projection 尚未消费；分类为 covered by later approved slice，owner 是 Slice C。
- ordinary prompt assembly 与 public smoke 尚未完成；分类为 covered by later approved slice，owner 是 Slice D / E。

### Slice C - Memory Durable And Projection Closure

目标：把 `ConversationMemorySnapshot`、durable memory rows、projection catch-up / rebuild 和 memory tests 同步迁移到 vNext，使 accepted vNext compact event 能 materialize 五类 session memory，fallback / rejected compact 不生成高阶 memory。

allowed files/modules：

- `dayu/host/memory.py`
- `dayu/host/durable/memory.py`
- `dayu/host/memory_repair.py`
- `dayu/host/compact_payload.py`，仅当 projection payload reader 需要 vNext typed helper
- `dayu/host/context_events.py`，仅当 projection event reader 需要 vNext payload type
- `tests/host/test_memory_projection.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_projection_checkpoint.py`
- `tests/host/test_durable_concurrency_matrix.py`
- `tests/host/test_memory_repair.py`，若该文件存在或 repair request / snapshot cursor 类型变化

实现边界：

- 新增 / 替换 `ConversationMemorySnapshotVNext`，字段为 `trace_memory`、`evidence_fact_memory`、`session_summary_memory`、`answer_anchor_memory`、`forward_intent_memory`、`diagnostics`。
- 引入五类 view / item dataclass：`ReferenceContinuityItem`、`EvidenceBackedFact`、`RecentEvidenceReadableItem`、`SessionSummaryMemoryView`、`AnswerAnchor`、`ForwardIntent`。
- `MemoryProjectionPolicy` 改为 per-semantic bounded policy：summary char cap、evidence fact cap / floor、answer anchor cap、forward intent cap、reference continuity cap / floor、selected recent window cap / floor、inline delta repair limits；policy digest 不含 `max_working_assumptions`、`history_pool_*`、`stable_layer_*`。
- 按 schema 约束以全新 schema 起库处理；snapshot JSON 只写 vNext fields，旧 JSON key `pinned_state`、`working_assumptions`、`conversation_continuity` 必须 fail closed。
- hot table `item_kind` 若需要变化，直接迁移为 vNext item kind：`reference_continuity_item`、`evidence_backed_fact`、`recent_evidence_item`、`session_summary`、`answer_anchor`、`forward_intent`。
- compact 前 projection 只能形成 selected recent window 可读材料，不自动生成 session summary、answer anchor、forward intent 或 evidence-backed facts。
- accepted `CONTEXT_COMPACTED` 后，projection 从 accepted vNext payload / artifact materialize 五类 memory；invalid / rejected / failed compaction event 不进入 memory projection。
- accepted evidence 存在但无合法 fact candidate 时只记录 diagnostic，不合成 fallback fact；assistant final answer、用户输入、summary、anchor、reference continuity、User Profile、Forward Intent 都不能升级成 evidence-backed fact。
- snapshot 与 projection checkpoint 必须同一 durable transaction 提交；checkpoint 不得先于 snapshot。

旧路径保留 / 删除边界：

- 一旦 `memory.py` 和 `durable/memory.py` 切换到 vNext，必须同步迁移其所有 production consumers 和 tests；不得保留 `WorkingAssumptionView`、`PinnedStateView`、`ConversationContinuityKind`、`ConversationContinuityItem`、`ConversationContinuityView` 作为 snapshot 顶层语义或 durable item kind。
- 全新 schema 删除旧 durable item kind：`raw_user_turn`、`raw_assistant_turn`、`assistant_conclusion`、`episode_summary`、`minimum_preserve_item`、`working_assumption`、`pinned_state`。旧库 row 不做兼容读取；旧语义只在新实现的数据生产规则中迁移到 vNext memory section。
- `RAW_USER_TURN`、`RAW_ASSISTANT_TURN`、`ASSISTANT_CONCLUSION` 迁移为 Trace Memory selected recent window material，不作为独立 snapshot item 持久化；`EPISODE_SUMMARY` 只能由 accepted `session_summary` roll-forward view 承接；`MINIMUM_PRESERVE_ITEM` 只以 `ReferenceContinuityItem` 形态保留局部承接语义。
- `MemoryProjectionDiagnostics` 不保留 pinned / working assumption / minimum preserve 专属 reason；可保留或重命名的 reason 只能表达 snapshot missing / damaged / lag、unsupported event、budget limit、inline delta repair、fact candidate invalid / superseded、reference continuity covered 等 vNext 语义。

不得引入：

- 旧库兼容读取、旧字段 fallback codec、旧 item kind alias、compatibility wrapper / facade / re-export。
- 通过旧 snapshot shape 反向生成 vNext section 的 bridge helper。

测试命令：

```bash
source .venv/bin/activate
pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_durable_concurrency_matrix.py -q
pytest tests/host/test_memory_repair.py -q
python -m pyright dayu/ tests/ utils/
```

若 `tests/host/test_memory_repair.py` 不存在，则在 implementation report 中说明，并以 `tests/host/test_memory_projection.py` 中 repair / rebuild cases 覆盖。

退出信号：

- durable store 读写 vNext snapshot 和 vNext items，旧 snapshot key fail closed。
- projection consumer 能从 EventLog 重建同一 snapshot digest，并断言 checkpoint atomicity。
- fallback、rejected compact、failed compact 不 materialize summary / fact / anchor / intent / reference continuity。
- pyright 全量通过，且 memory production consumers 不再引用旧 snapshot fields。

residual risks：

- RunInputBuilder prompt assembly 尚未渲染 vNext snapshot；分类为 covered by later approved slice，owner 是 Slice D。
- public smoke / README 尚未完成；分类为 covered by later approved slice，owner 是 Slice E。

### Slice D - Prompt And Fallback Closure

目标：把普通 Agent request messages、fallback input view、dispatch 接线和 RunInputBuilder tests 同步迁移到 vNext snapshot / post-compact delta / current input 固定顺序，保证 fallback 只渲染 bounded recent window 与 current input。

allowed files/modules：

- `dayu/host/run_input.py`
- `dayu/host/compact_material.py`，仅限共享 ordinary material / selected recent window helper
- `dayu/host/context_fallback.py`
- `dayu/host/dispatch.py`，仅限调用 RunInputBuilder 所需的 memory / fallback view 参数
- `tests/host/test_run_input_builder.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_public_open_host_multiturn_smoke.py`
- `tests/host/test_public_tool_wiring_smoke.py`，仅当 accepted evidence material prompt 行为变化

实现边界：

- `MemorySnapshotView` 改为 vNext readable section view，记录 snapshot cursor、policy digest、diagnostics、represented evidence refs。
- prompt assembly 固定顺序：system / scene、Session Summary、Evidence / Fact、Answer Anchor、Forward Intent、Trace reference continuity、selected recent window、current input、replay / retry / steer / resume guidance、tool schema / policy。
- no accepted compacted view：只渲染 selected recent window 和 current input。
- accepted compacted view：渲染五类 memory section + selected recent window after compact boundary + current input。
- compact failed fallback：只渲染 fallback selected recent window 和 current input，不渲染 accepted compacted view、高阶 memory section、失败 proposal、fallback diagnostic 或 Host internal state。
- 第一阶段不做 runtime token estimator 逐 section 裁剪；section 在 projection / assembly 前由 cap / floor bounded。
- memory snapshot lag 仍触发 catch-up / rebuild / repair path；不得把 Run 推入 `RECOVERING`。

旧路径保留 / 删除边界：

- 一旦 RunInputBuilder 切换到 vNext，必须删除旧 stable block headers：`Memory user goals and constraints`、`Memory confirmed subjects and methodology`、`Memory open questions and working assumptions`、`Memory minimum preserve continuity`、`Memory episode summaries`。
- 不得在 RunInputBuilder 中保留旧 `goals` / `facts` / `questions_assumptions` renderer wrapper；旧字段不应通过 prompt adapter 或 extra payload 进入 final messages。
- 未涉及的 public API、scheduler、Engine / Service / UI 边界保持不变。

不得引入：

- provider-specific tokenizer adapter、runtime 逐 section 裁剪、recall / search / vector / reranker / recall tool。
- 失败 Attempt provider payload 的复用路径或 fallback materialization 到 memory snapshot 的桥接路径。

测试命令：

```bash
source .venv/bin/activate
pytest tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py -q
python -m pyright dayu/ tests/ utils/
```

如果 accepted evidence material prompt 行为变化，同 slice 追加：

```bash
source .venv/bin/activate
pytest tests/host/test_public_tool_wiring_smoke.py -q
python -m pyright dayu/ tests/ utils/
```

退出信号：

- final messages 能从 vNext durable facts、snapshot、post-compact delta 和 current input 重建。
- empty compacted view、non-empty compacted view、post-compact delta、compact boundary、fallback no high-order memory 均由 RunInputBuilder tests 覆盖。
- fallback 路径只有 bounded recent window 和 current input，且不会写 `CONTEXT_COMPACTED`、compact artifact 或 memory snapshot。
- pyright 全量通过，且 prompt production path 不再引用旧 stable memory block shape。

residual risks：

- public smoke 脚本、README 同步和最终 issue-80 映射复核尚未完成；分类为 covered by later approved slice，owner 是 Slice E。

### Slice E - Public Smoke And Docs Closure

目标：完成 Host public path smoke、README 同步、旧术语清理和 residual risk owner 标注，不扩大到完整 eval benchmark。

allowed files/modules：

- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`
- `dayu/host/README.md`
- `tests/README.md`
- `README.md`，仅当 smoke 命令或 public workflow 发生变化
- 相关 `tests/host/*` smoke / support 文件

实现边界：

- smoke 必须走 Host public path，不绕过 public API、scheduler、context governance 或 memory projection。
- 复核本 plan 的 `Issue-80 / Design 24.7 Evaluation Mapping` 小节与最终实现一致；若 implementation 发现某个 current scope covered 项无法满足，必须回到 plan / design 修正，不得只在 implementation report 中降级。
- README 只写当前代码已落地事实，不写路线图；Host README 记录 vNext Conversation Memory / Context Governance 稳定边界，tests README 记录新增 / 迁移后的测试事实和命令。
- 根目录 `README.md` 只在项目级使用方式、配置入口、CLI、trace/render 入口或 smoke 命令变化时更新。

旧路径保留 / 删除边界：

- public smoke 与 README 不得保留旧 `working_assumptions`、`pinned_state`、stable layer、history pool、minimum preserve 术语作为新实现路径说明。
- 若残留旧术语仅用于历史 artifact 路径或未切换后续 work unit，必须在 implementation report 中列 owner；不得在 README 中新旧术语并存。

不得引入：

- eval benchmark runner、metrics aggregation、LongMemEval / PersonaMem adapter。
- User Profile durable store、cross-session profile contract、deep historical recall / semantic search / vector recall / reranker / recall tool。

测试命令：

```bash
source .venv/bin/activate
pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_compact_smoke.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py -q
python utils/smoke_host_public_conversation_memory.py
python utils/smoke_host_public_conversation_memory_scenarios.py
python utils/smoke_host_public_multiturn.py
pytest tests/host -q
python -m pyright dayu/ tests/ utils/
```

退出信号：

- public smoke 全部通过。
- `dayu/host/README.md` 与 `tests/README.md` 按 AGENTS 职责同步，根 README 仅在触发条件成立时同步。
- 本 plan 的 issue-80 / design 24.7 映射仍成立；完整 eval benchmark、User Profile Memory、deep historical recall 等 residual risks 均有 owner / destination。
- pyright 全量通过，且没有新增或扩散类型错误。

residual risks：

- 完整 Conversation Memory eval benchmark：deferred-with-owner，WU-CM-10 / GitHub Issue #80。
- Cross-session User Profile Memory：deferred-with-owner，WU-CM-11 / GitHub Issue #115。
- Deep historical recall / semantic search / vector recall / reranker / recall tool：deferred-with-owner，GitHub Issue #39。
- Provider-specific tokenizer adapter：deferred-with-owner，后续 Context Governance 精确预算 work unit。
- Fins fact grounding integration：deferred-with-owner，Fins integration work unit。

## Allowed Files / Modules Summary

Implementation gate 可以按 slice 修改：

- `dayu/host/memory.py`
- `dayu/host/run_input.py`
- `dayu/host/compaction.py`
- `dayu/host/context_governance.py`
- `dayu/host/context_policy.py`，仅当 slice 需要对齐 vNext compact / memory policy cap / floor
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
- `README.md`，仅当 smoke 命令或 public workflow 发生变化

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

当前没有阻塞 code-generation-ready plan 的 open question。若 implementation agent 在 Slice A、B 或 C 发现第 24 / 25 章无法唯一裁决某个 public contract、durable schema、EventLog payload 或状态机语义，应停止 implementation，回到 design source 更新，而不是在生产代码里自行发明兼容路径。
