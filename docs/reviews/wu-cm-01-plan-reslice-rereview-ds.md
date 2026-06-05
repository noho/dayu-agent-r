# WU-CM-01 Plan Reslice Re-Review - AgentDS

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | plan reslice re-review |
| agent | AgentDS |
| branch | `phaseflow/wu-cm-01` |
| design source | `docs/host/design.md` 第 24 章 / 第 25 章 |
| control source | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| implementation blocker | `docs/reviews/wu-cm-01-implementation-codex.md` |
| reslice fix report | `docs/reviews/wu-cm-01-plan-reslice-fix-codex.md` |
| expected artifact | `docs/reviews/wu-cm-01-plan-reslice-rereview-ds.md` |

## Decision

**Verdict: pass-with-findings**

Plan 已成功从概念域 Slice 1-5 改写为 pyright-clean、可编译、可验证的纵向闭环 Slice A-E。所有 14 项 re-review 验证项均已确认。3 个 low-severity findings 不阻塞 implementation gate 进入，但建议在 Slice A 启动前澄清。

## Review Scope And Method

本 gate 是 plan reslice re-review，只复审 plan artifact 是否满足 reslice 要求。不修改生产代码、plan artifact、control_doc；不运行测试或 pyright；不 commit、push、PR、merge。

审查方法：
1. 逐项核对该 task 的 14 个验证维度。
2. 以 design doc 第 24/25 章为真源，交叉验证 plan 中的 contract、schema、quality checker 规则。
3. 以 direct code evidence 验证 plan 对当前代码状态的诊断是否准确。
4. 以 adversarial lens 压测 slice 边界、依赖关系、pyright-clean 可行性、退出信号完整性。

## Assumptions Tested

| # | Assumption | Evidence | Result |
|---|---|---|---|
| A1 | Plan 已删除旧 Slice 1-6 概念域拆分 | `rg -n "Slice [1-6]"` 无命中（fix report 已确认） | 成立 |
| A2 | Plan 不再允许中间全量 pyright 失败 | 每个 Slice A-E 均要求 `python -m pyright dayu/ tests/ utils/` 通过 | 成立 |
| A3 | Plan 的 vNext contract 与 design source 一致 | 对比 plan Slice A/B 与 design 24.3/24.4 | 成立 |
| A4 | Plan 的 issue-80 映射完整 | 逐行核对映射表，旧数字已替换为 A-E | 成立 |
| A5 | Plan 的 quality checker 规则迁移完整 | 对比 plan Slice A/B 与 design 24.3 source label / provenance 规则 | 成立 |
| A6 | 当前代码旧 contract 诊断准确 | `rg` 确认 203 处旧术语命中，0 处 vNext type 存在 | 成立 |

## Verification Checklist

逐条核对该 task 的 14 项验证要求：

### 1. Plan 已从概念域 Slice 1-5 改写为纵向闭环 Slice A-E

**Status: fixed**

Plan 的 `Implementation Slices` 章节已完全替换。旧 `Slice 1: Compact Contract Type Alignment` 到 `Slice 6: README / Doc Sync` 不再存在。新 Slice A-E 为：
- A: Compact Contract Closure
- B: Compact Operation And Event Closure
- C: Memory Durable And Projection Closure
- D: Prompt And Fallback Closure
- E: Public Smoke And Docs Closure

每个 slice 按"可运行路径闭合"组织，而非按"类型/持久化/parser/operation/prompt"概念域拆分。

### 2. 不再允许中间全量 pyright 失败

**Status: fixed**

Plan 的 `Slice Verification Boundary` 明确要求每个 slice 结束时 `python -m pyright dayu/ tests/ utils/` 不得新增或扩散错误。旧 plan 中允许 Slice 1-4 中间 pyright 失败的表述已删除。Pyright-clean 边界表进一步明确了每个 slice 的 pyright 规则。

### 3. 每个 slice 有 allowed files/modules

**Status: fixed**

| Slice | Allowed 文件数 | 覆盖范围 |
|---|---|---|
| A | 9 | compaction.py, compact_material.py, llm_compaction.py, context_governance.py, context_policy.py (条件), 4 个测试文件 |
| B | 15 | 上述 + compaction_operation.py, context_events.py, compact_payload.py, dispatch.py (条件), context_fallback.py (条件), 6 个测试文件 |
| C | 8+ | memory.py, durable/memory.py, memory_repair.py, compact_payload.py (条件), context_events.py (条件), 5+ 个测试文件 |
| D | 10 | run_input.py, compact_material.py (条件), context_fallback.py, dispatch.py (条件), 5 个测试文件 |
| E | 6+ | 3 个 smoke 脚本, dayu/host/README.md, tests/README.md, README.md (条件), 相关测试 |

### 4. 旧路径保留/删除边界

**Status: fixed**

每个 slice 均有 `旧路径保留 / 删除边界` 小节，明确：
- Slice A：旧 `stable_input`/`history_input`/`evidence_input` 可原样存在到 Slice B；不得新增 wrapper。
- Slice B：operation 切换到 vNext 后，旧 candidate merge / pinned patch / minimum preserve operation 逻辑必须删除。
- Slice C：切换到 vNext snapshot 后，`WorkingAssumptionView`/`PinnedStateView`/`ConversationContinuityKind` 等旧类型必须删除或迁移。
- Slice D：切换到 vNext 后，旧 stable block headers 必须删除。
- Slice E：README 不得保留旧术语作为新路径说明。

### 5. 禁止 compatibility wrapper/re-export/lazy import seam

**Status: fixed**

每个 slice 均有 `不得引入` 小节，明确禁止：
- Slice A：`EpisodeSummaryCandidate`/`PinnedStatePatchCandidate` 等旧类型的 vNext wrapper/facade/re-export；禁止 `hasattr`/`getattr`/`Any`/lazy import/extra payload 胶水。
- Slice B：`CONTEXT_COMPACTED` 旧字段 re-export、旧 payload facade、旧 candidate 到 vNext 的双向 adapter；禁止 lazy import seam、字符串字段探测、untyped event payload。
- Slice C：旧库兼容读取、旧字段 fallback codec、旧 item kind alias、compatibility wrapper/facade/re-export；禁止通过旧 snapshot shape 反向生成 vNext section 的 bridge helper。
- Slice D：旧 `goals`/`facts`/`questions_assumptions` renderer wrapper；禁止 provider-specific tokenizer adapter。

### 6. 每个 slice 有测试命令

**Status: fixed**

每个 slice 均有具体 `pytest` 命令，覆盖该 slice 的 affected tests。最终验证命令合并了所有核心测试路径。

### 7. 每个 slice 有 pyright 命令

**Status: fixed**

每个 slice 的测试命令后均跟随 `python -m pyright dayu/ tests/ utils/`。

### 8. 每个 slice 有退出信号

**Status: fixed**

每个 slice 的 `退出信号` 小节列出了具体可验证条件。例如 Slice A 的退出信号包括 vNext dataclass 可 JSON round-trip、fake compactor 产出 deterministic vNext candidate、label provenance mapping 有 fail-closed 测试、pyright 全量通过。

### 9. 每个 slice 有 residual risks

**Status: fixed**

每个 slice 的 `residual risks` 小节将未覆盖工作分类为 "covered by later approved slice" 或 "deferred-with-owner"，并标注 owner slice/issue。

### 10. Issue-80 映射

**Status: fixed**

`Issue-80 / Design 24.7 Evaluation Mapping` 表已保留，slice 列从旧数字（1-6）更新为 A-E。14 个评测维度均保留原有状态、测试入口和 deferred owner。补充了 `compact roll-forward` 行的 slice 映射（B, C, D, E）。

### 11. Continuity / minimum preserve

**Status: fixed**

Plan 在 Slice A 的迁移表中明确：
- `MINIMUM_PRESERVE_ITEM` 只以 `ReferenceContinuityItem` 形态保留局部承接语义。
- 旧 `MinimumPreserveReason.NEEDED_FOR_RECENT_REFERENCE` 等映射为 vNext `ReferenceContinuityCandidate.reason` 的 `local_reference`/`ordinal_reference`/`ellipsis_recovery`/`recent_state`。
- Slice C 中旧 `ConversationContinuityKind.MINIMUM_PRESERVE_ITEM` 不作为 durable item kind 保留。

### 12. vNext schema

**Status: fixed**

Plan 中的 vNext schema 描述与 design doc 第 24.3/24.4 章一致：
- `ConversationCompactInputVNext` 顶层字段（`previous_compacted_view`, `trace_material`, `evidence_material`, `answer_material`, `current_input_anchor`, `instruction`）与 design 24.3 一致。
- `ConversationCompactOutputVNext` 字段（`session_summary`, `evidence_backed_facts`, `answer_anchors`, `forward_intents`, `reference_continuity_items`, `diagnostics`）与 design 24.3 一致。
- `ConversationMemorySnapshotVNext` 六字段与 design 24.4 一致。Plan 省略了 `schema_version`/`session_id`/`source_event_cursor`/`latest_compaction_event_ref` 的管理字段，但明确以 design source 为唯一真源，implementation agent 应直接引用 design doc 的完整 schema。

### 13. Material mapping

**Status: fixed**

Plan Slice A 的 `旧路径保留 / 删除边界` 中包含了完整的旧 compact material block kind 到 vNext section 迁移表：
- `PINNED_STATE`/`WORKING_ASSUMPTION` → 删除
- `EVIDENCE_BACKED_FACT` → `previous_compacted_view.evidence_backed_facts`
- `OPEN_QUESTION` → accepted vNext forward intent 承接
- `RAW_USER_TURN` → `trace_material`（current input 只能进入 `current_input_anchor`）
- `RAW_ASSISTANT_TURN` → trace/answer 二选一
- `EPISODE_SUMMARY` → accepted vNext session summary 承接
- `ACCEPTED_TOOL_EVIDENCE` → `evidence_material`
- `CURRENT_INPUT_ANCHOR` → 不可引用

### 14. Quality checker 规则

**Status: fixed**

Plan Slice B 列出了完整的 vNext quality validation issues：
- schema invalid, unknown/stale/missing source label, cross-section label, current input anchor cited
- provenance mismatch, source boundary violation
- fact candidate invalid, answer anchor invalid, forward intent invalid, reference continuity invalid
- diagnostic invalid, budget reject

Source label allowlist 按 section 校验规则明确：fact → evidence labels, answer anchor → answer labels, forward intent/reference continuity → design 24.3 allowed sections, diagnostic → 同 section allowed labels, current input anchor → 始终不可引用。

## Findings

### F1 - Low - Slice A vNext 类型与旧类型同模块共存缺乏命名约定

- **位置**: Slice A 实现边界
- **问题类型**: 不可直接实施
- **当前写法**: Plan 要求 vNext dataclass 与旧 `CompactionCandidate`/`CompactMaterialPack` 等在同一 `compaction.py`/`compact_material.py`/`llm_compaction.py` 中共存，且禁止新增 bridge/wrapper。
- **反例/失败场景**: 若 vNext 类型使用与旧类型相似的名称（如 `CompactMaterialPackVNext`），或 vNext 类型的模块级 import 意外覆盖了旧类型的依赖，可能导致旧 production code 的类型解析静默变化，pyright 会报错但 root cause 不直观。
- **为什么有问题**: Plan 对共存策略只有禁止性约束（不得新增 wrapper），缺乏建设性指导（命名前缀、模块内分区注释、type alias 隔离规则）。Implementation agent 可能因命名选择不当而产生不必要的 pyright 摩擦。
- **直接证据**: Plan Slice A 说"引入 `ConversationCompactInputVNext` 与 `ConversationCompactOutputVNext` typed dataclass"，但未说明这些新类型与同模块中 `CompactMaterialPack`/`CompactionCandidate` 等旧类型的文件内组织方式。
- **影响**: 实施 Agent 可能在 Slice A 中花费额外时间解决自造的类型冲突，但不会导致结构性返工。
- **建议改法和验证点**: 在 Slice A 启动时，implementation agent 应先用 `rg` 列出所有同模块旧类型名称，确保 vNext 类型命名不与旧类型产生前缀/后缀混淆；建议 vNext 类型统一使用 `VNext` 后缀或集中放在模块底部带有明确分隔注释的区域。
- **修复风险**: 低
- **严重程度**: 低

### F2 - Low - `compaction_evidence.py` 未分配到具体 slice

- **位置**: Allowed Files / Modules Summary vs 各 Slice 的 allowed files
- **问题类型**: 切片过粗
- **当前写法**: `dayu/host/compaction_evidence.py` 出现在 `Allowed Files / Modules Summary`（第 417 行）但在 Slice A-E 各自的 allowed files 中均未列出。
- **反例/失败场景**: Implementation agent 在 Slice B（operation）中需要修改 evidence mapping 逻辑时，不确定 `compaction_evidence.py` 是否在允许范围内，可能过度保守跳过必要修改，或过度激进在未授权 slice 中修改。
- **为什么有问题**: Summary 和 per-slice lists 之间的不一致会造成 implementation gate 的 ambiguity。该文件当前包含 2 处旧术语命中（`rg` 确认），确实需要在某个 slice 中迁移。
- **直接证据**: `rg` 确认 `dayu/host/compaction_evidence.py` 存在且包含旧 contract 引用。Plan Slice A-E 的 allowed files 均未显式列出此文件，但 Summary 中列出。
- **影响**: 实施 Agent 需要额外判断该文件属于哪个 slice；最可能属于 Slice A（contract）或 Slice B（operation），不会导致结构性阻塞。
- **建议改法和验证点**: 明确 `compaction_evidence.py` 的 owner slice。按语义（evidence material mapping），建议归入 Slice A 或 B 的 allowed files，并注明条件（如"仅当 vNext evidence material mapping 需要"）。
- **修复风险**: 低
- **严重程度**: 低

### F3 - Low - Slice C "全新 schema 起库"下测试数据迁移成本未显式估计

- **位置**: Slice C 实现边界
- **问题类型**: 测试缺口
- **当前写法**: Plan 要求"按 schema 约束以全新 schema 起库处理；snapshot JSON 只写 vNext fields，旧 JSON key `pinned_state`、`working_assumptions`、`conversation_continuity` 必须 fail closed"。同时要求旧 durable item kind 删除且不做兼容读取。
- **反例/失败场景**: 现有测试（如 `test_memory_projection.py` 3,313 行、`test_durable_schema.py`）可能依赖旧 snapshot shape 的 test fixture/builder/helper。当 snapshot schema 完全替换后，这些 fixture 需要同步重写，工作量可能被低估。
- **为什么有问题**: Plan 的 Slice C 测试命令假设现有测试文件可以直接迁移，但如果 test fixture builder 大量引用旧字段名，重构测试本身可能成为 Slice C 的主要工作量。Plan 对此有提及（"tests 需要随实现边界迁移"），但未显式标注测试数据迁移的工作量风险。
- **直接证据**: Plan 的 code evidence 指出 `tests/host/test_memory_projection.py` 仍断言旧 `working_assumptions`、stable layer、history pool、minimum preserve 等语义，但未估计 fixture 重构范围。
- **影响**: Slice C 的实施时间可能被测试 fixture 重构显著拉长，但不影响最终交付质量。
- **建议改法和验证点**: Implementation agent 在 Slice C 启动前，先用 `rg` 统计测试文件中旧字段引用密度，评估 fixture 重构范围。若超过预期，可以在 implementation report 中记录并在不违反 pyright-clean 约束的前提下分步迁移测试。
- **修复风险**: 低
- **严重程度**: 低

## Open Questions

当前没有 blocking open questions。

Plan 自身的 Blocking Open Questions 声明仍然成立：若 implementation agent 在 Slice A、B 或 C 发现第 24/25 章无法唯一裁决某个 public contract、durable schema、EventLog payload 或状态机语义，应停止 implementation，回到 design source 更新。

## Residual Risks

| 风险 | 分类 | Owner | 说明 |
|---|---|---|---|
| 完整 Conversation Memory eval benchmark | deferred-with-owner | WU-CM-10 / GitHub Issue #80 | Plan 只提供可断言入口，不实现完整 benchmark |
| Cross-session User Profile Memory | deferred-with-owner | WU-CM-11 / GitHub Issue #115 | Plan 固定不混入 session memory 边界 |
| Deep historical recall / semantic search | deferred-with-owner | GitHub Issue #39 | 第一阶段不做 recall |
| Provider-specific tokenizer adapter | deferred-with-owner | 后续 Context Governance work unit | 保持 conservative estimator |
| Fins fact grounding integration | deferred-with-owner | Fins integration work unit | memory snapshot 不替代 Fins truth |
| Schema old DB upgrade | explicit non-goal | 无 | 全新 schema 起库，不兼容旧库 |
| Slice A 类型共存摩擦 (F1) | accepted-plan-residual | WU-CM-01 Slice A implementation | Implementation agent 需自行选择命名策略 |
| Slice C 测试 fixture 重构工作量 (F3) | accepted-plan-residual | WU-CM-01 Slice C implementation | Implementation agent 需在 Slice C 启动前评估 |

## Completion Status

**Verdict: pass-with-findings**

Plan reslice re-review gate 完成。Plan artifact 满足该 gate 的全部 14 项验证要求。3 个 low-severity findings 均不阻塞 implementation gate 进入。

按 stop condition，本 gate 停止于此 artifact。不进入 implementation、review、commit、push、PR 或 merge。
