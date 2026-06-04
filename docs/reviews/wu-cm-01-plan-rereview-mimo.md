# WU-CM-01 Plan Re-Review — AgentMiMo

## Review Metadata

| 项目 | 值 |
|---|---|
| review timestamp | 2026-06-04T10:09:14+08:00 |
| reviewer | AgentMiMo |
| reviewed target | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| gate | plan re-review |
| design source | `docs/host/design.md` 第 24、25 章 |
| control source | `docs/host/issues-implementation-control.md` |
| previous reviews | `docs/reviews/wu-cm-01-plan-review-mimo.md`；`docs/reviews/wu-cm-01-plan-review-ds.md` |
| controller adjudication | `docs/reviews/wu-cm-01-plan-review-controller-adjudication.md` |
| fix report | `docs/reviews/wu-cm-01-plan-fix-codex.md` |

## Re-Review Posture

本次 re-review 的任务是逐条验证 controller 接受的 6 条 findings（PF-01 到 PF-06）是否已在 plan fix gate 中修复，是否仍有 blocking gap，以及是否引入新的 plan 风险。

## PF-01 到 PF-06 逐条验证

### PF-01: issue-80 / design 24.7 评测维度映射 — fixed

**原始问题**: Control doc 要求 plan 必须映射 #80 评测维度；plan 将其推迟到 Slice 6 implementation report。

**验证结果**: plan artifact 新增 `Issue-80 / Design 24.7 Evaluation Mapping` 小节（lines 40-62），包含 14 行映射表，逐条覆盖 design 24.7 的所有可断言场景。每个维度标记了 current scope covered（含 slice 编号和测试入口）、deferred-with-owner（含 owner issue）或 explicit non-goal（含原因）。直接满足 control_doc 第 371 行和第 400 行的验收信号。

**直接证据**: plan lines 40-62 的映射表与 design 24.7 line 2854 的 13 个场景逐一对齐；control_doc line 371-372 和 line 400 的要求被直接满足。

### PF-02: ConversationContinuityKind 全量处置与 minimum preserve 迁移 — fixed

**原始问题**: `MINIMUM_PRESERVE_ITEM` 到 `ReferenceContinuityItem` 迁移路径未指定；`ConversationContinuityKind` 其余成员处置不完整。

**验证结果**:
- Slice 1（lines 107-110）显式声明：`ConversationContinuityKind`、`ConversationContinuityItem`、`ConversationContinuityView` 整体删除，不作为 vNext snapshot 或 durable item kind 保留。
- `RAW_USER_TURN` / `RAW_ASSISTANT_TURN` / `ASSISTANT_CONCLUSION` 迁移为 Trace Memory selected recent window material，不作为独立 snapshot item 持久化。
- `EPISODE_SUMMARY` 由 Session Summary Memory 承接。
- `MINIMUM_PRESERVE_ITEM` 语义由 `ReferenceContinuityItem` 承接，旧 `MinimumPreserveReason` 不兼容读取，按 vNext 文本语义重新映射。
- Slice 2（line 147）明确全新 schema 删除旧 durable item kind，不做旧库兼容读取。

**直接证据**: plan lines 107-110, 147 与 design 24.5 line 2789 的 Trace Memory 定义一致；controller adjudication 的 fix 要求被完整满足。

### PF-03: vNext compact output candidate schema 与旧类型删除边界 — fixed

**原始问题**: vNext candidate schema 细节未完整引用；旧 compact candidate 类型删除边界不完整。

**验证结果**:
- Slice 1（line 113）明确 `ConversationCompactOutputVNext` candidate schema 以 `docs/host/design.md` 24.3 为唯一真源。
- Slice 1（lines 115-116）显式列出所有待删除旧类型：`EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`PreservationEvidence`、`PinnedPatchOperation`、`PinnedStringTupleFieldPatch`、`PinnedTextFieldPatch`、`MinimumPreserveReason`。
- Slice 1（line 116）列出所有待删除旧 `CompactQualityIssue` 枚举值。
- Slice 3（lines 190-196）完整列出所有 candidate 子结构，与 design 24.3 lines 2700-2735 逐一对齐。

**直接证据**: plan lines 113, 115-116, 190-196 与 design 24.3 candidate schema 完全对齐；controller adjudication 的 fix 要求被完整满足。

### PF-04: 旧 compact material block kind 到 vNext sections 映射 — fixed

**原始问题**: compact material section 映射规则未显式声明。

**验证结果**: Slice 3 新增旧 block kind 到 vNext section 映射表（lines 199-211），覆盖全部 9 种旧 `CompactMaterialBlockKind`：`PINNED_STATE`、`EVIDENCE_BACKED_FACT`、`WORKING_ASSUMPTION`、`OPEN_QUESTION`、`RAW_USER_TURN`、`RAW_ASSISTANT_TURN`、`EPISODE_SUMMARY`、`ACCEPTED_TOOL_EVIDENCE`、`CURRENT_INPUT_ANCHOR`。每种 block kind 的 vNext section 映射或删除处置均有明确说明。

**直接证据**: plan lines 199-211 的映射表与 design 24.3 的 compact input section 定义一致。

### PF-05: Context Governance quality checker 规则 — fixed

**原始问题**: quality checker 新验证规则未具体化。

**验证结果**:
- Slice 4（lines 241-248）补充 source label allowlist 规则，按 candidate 类型逐一列出允许引用的 section。
- `current_input_anchor.anchor_label` 不可引用规则已明确（line 247）。
- cross-section citation、stale label、unknown label、provenance mismatch 均 fail closed（line 248）。
- 旧 `check_compaction_candidate()` 入口变化已说明（line 249）：改为 vNext accept barrier 入口，不提供旧 `CompactionCandidate` overload。
- `CompactQualityIssue` vNext 枚举已列出至少包含 schema / label / provenance / candidate / budget 类拒绝原因，旧枚举必须删除（line 250）。

**直接证据**: plan lines 240-253 与 design 24.3 source label 规则、design 25 accept barrier 规则一致。

### PF-06: Slice 1-5 可编译性与 pyright 验证边界 — fixed

**原始问题**: sequential slices 的中间编译状态未处理。

**验证结果**: 新增 `Slice Verification Boundary` 小节（lines 80-90），明确：
- Slice 1-5 是整体迁移序列，不承诺每个中间 slice 结束后全量 pyright 通过。
- Slice 1-4 可做局部 code review 和 focused tests；全量 pyright 失败时必须列出失败是否只来自后续 slice 尚未迁移的旧引用。
- 最早 pyright 闭合点为 Slice 5 结束。
- Slice 6 完成后必须运行最终验证命令。
- 若 implementation gate 要求每个提交可编译，必须改写为更小的可编译闭环提交，不得通过 compatibility wrapper 保持表面可编译。

**直接证据**: plan lines 80-90 直接回应了 AgentDS Finding 3 和 AgentMiMo F005 的建议。

## Non-Blocking Open Questions 验证

controller adjudication 列出的 3 条非阻塞 open questions 均已在 plan fix 中解决：

| Open question | 处理状态 | plan 位置 |
|---|---|---|
| reactive multi-pass repair budget | addressed | Slice 4 line 252 明确共用 `max_compaction_attempts_per_operation` 总预算 |
| vNext diagnostics reason 迁移 | addressed | Slice 1 line 117 明确删除旧专属 reason，迁移为 vNext 语义 |
| prompt-local label opaque handle | addressed | Slice 3 line 189 明确 label 只作为 opaque handle |

## 新增 Finding 检查

### 无新增 blocking finding

plan fix 未引入新的 blocking gap。以下为低严重度观察项：

### NR-01-低-context_budget.py 不在 allowed modification list 但出现在 test matrix

- **位置**: Allowed Files / Modules Summary；Test Matrix
- **问题类型**: 过度耦合 / 契约缺失
- **当前写法**: Allowed modification list 包含 `dayu/host/context_policy.py`（仅当 policy 默认值需要对齐时修改），但不包含 `dayu/host/context_budget.py`。Test matrix 包含 `pytest tests/host/test_context_budget.py -q`。
- **反例/失败场景**: 若 `context_budget.py` 从 `memory.py` 导入的 `MemoryProjectionPolicy` 字段（如 `max_working_assumptions`）在 Slice 1 被删除，`context_budget.py` 会编译失败。Slice Verification Boundary 已声明中间状态允许编译失败，但 implementation agent 无法修改 `context_budget.py`（不在 allowed list）。
- **为什么有问题**: 这是低风险问题。`context_budget.py` 大概率不直接依赖 `MemoryProjectionPolicy` 的旧字段；若确实依赖，Slice 5 结束前必须恢复可编译，且 `context_policy.py` 在 allowed list 中可间接调整。Slice Verification Boundary 已覆盖此场景。
- **影响**: 低。implementation agent 可能在 Slice 5 发现需要将 `context_budget.py` 加入 allowed list。
- **建议改法**: 若 implementation agent 在 Slice 1 发现 `context_budget.py` 编译失败是因为旧字段引用，可在 Slice 1 或 Slice 5 中将 `context_budget.py` 加入 allowed list。不需要在 plan 中预先修改。
- **修复风险**: 低
- **严重程度**: 低

## Residual Risks

| ID | 风险 | 严重程度 | Owner / Destination |
|---|---|---|---|
| WU-CM-01-RR-1 | 完整 Conversation Memory eval benchmark | 低 | WU-CM-10 / GitHub Issue #80 |
| WU-CM-01-RR-2 | Cross-session User Profile Memory | 低 | WU-CM-11 / GitHub Issue #115 |
| WU-CM-01-RR-3 | Deep historical recall / semantic search | 低 | GitHub Issue #39 |
| WU-CM-01-RR-4 | Provider-specific tokenizer adapter | 低 | WU-CTX-01 / GitHub Issue #20 |
| WU-CM-01-RR-5 | Fins fact grounding integration | 低 | Fins integration work unit |
| WU-CM-01-RR-6 | Schema old DB upgrade | 低 | explicit non-goal，全新 schema 起库 |
| WU-CM-01-RR-7 | context_budget.py 可能需要加入 allowed list | 低 | implementation gate 按需处理 |

所有 residual risks 均有 owner / destination，符合 control_doc 的 "ready-to-open-draft-PR 前所有 tracking items 必须处于 closed / deferred-with-owner / transferred-to-issue" 要求。

## Final Re-Review Conclusion

**verdict: pass**

plan fix gate 已完整修复 controller 接受的全部 6 条 findings。逐条验证结果：

| Finding | 状态 |
|---|---|
| PF-01 issue-80 / design 24.7 评测维度映射 | fixed |
| PF-02 ConversationContinuityKind 全量处置与 minimum preserve 迁移 | fixed |
| PF-03 vNext compact output candidate schema 与旧类型删除边界 | fixed |
| PF-04 旧 compact material block kind 到 vNext sections 映射 | fixed |
| PF-05 Context Governance quality checker 规则 | fixed |
| PF-06 Slice 1-5 可编译性与 pyright 验证边界 | fixed |

新增 findings：0 条 blocking，1 条低严重度观察项（NR-01）。blocking open questions：0 条。residual risks 均有 owner。

plan artifact 已 code-generation-ready，可以进入 implementation gate。
