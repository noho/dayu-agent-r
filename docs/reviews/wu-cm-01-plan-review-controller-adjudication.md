# WU-CM-01 Plan Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | plan review adjudication |
| design source | `docs/host/design.md` 第 24 章 / 第 25 章 |
| control source | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| review artifacts | `docs/reviews/wu-cm-01-plan-review-mimo.md`; `docs/reviews/wu-cm-01-plan-review-ds.md` |

## Verdict

Plan review gate 结论为 `pass-with-findings`，但存在 1 条 blocking finding，必须进入 plan fix gate。

## Finding Adjudication

| ID | 来源 | 裁决 | 当前 phase 最佳实践理由 | Fix 要求 |
|---|---|---|---|---|
| PF-01 | AgentDS F1 | accepted | `control_doc` 明确要求 WU-CM-01 plan 必须映射 issue-80 / WU-CM-10 评测维度，不能推迟到 implementation report；这是 plan gate 验收信号。 | 在 plan artifact 中新增独立小节，逐条映射 `docs/host/design.md` 24.7 的可断言场景与 GitHub issue-80 评测维度，标记 current scope covered / deferred-with-owner / explicit non-goal，并写明 slice 与测试入口。 |
| PF-02 | AgentMiMo F001 / AgentDS F4 | accepted | WU-CM-04 已裁决 minimum preserve 是 bounded continuity item，不是事实真源；vNext 必须明确其语义迁移到 Trace Memory 的 reference continuity 边界，且不得引入旧库兼容读取。 | 补充 `ConversationContinuityKind` 全量处置：RAW_USER_TURN / RAW_ASSISTANT_TURN / ASSISTANT_CONCLUSION 作为 selected recent window material；EPISODE_SUMMARY 由 Session Summary Memory 承接；MINIMUM_PRESERVE_ITEM 语义由 `ReferenceContinuityItem` 承接；旧 durable item kind 在全新 schema 中删除，不写旧库兼容读取。 |
| PF-03 | AgentMiMo F002 / AgentDS F2 | accepted | strict compact parser 是 WU-CM-01 的核心 contract；plan 必须能直接指导删除旧 candidate 类型并实现 vNext schema。 | 补充 vNext compact output candidate schema 以 design 24.3 为唯一真源；列出待删除旧类型和旧枚举值，包括 `EpisodeSummaryCandidate`、`PinnedStatePatchCandidate`、`MinimumPreserveItemCandidate`、`PreservationEvidence`、旧 pinned / preserve / open question quality issues。 |
| PF-04 | AgentMiMo F003 | accepted | 旧 compact material block 到 vNext section 的迁移是 Slice 3 的主要实施路径，不能交给实现 Agent 自行推断。 | 在 Slice 3 中补充旧 block kind 到 vNext sections 的映射表，并明确哪些旧 block kind 删除。 |
| PF-05 | AgentMiMo F004 | accepted | Context Governance accept barrier 是 Host 强约束核心；quality checker 规则必须和 design 24.3 / 25 同源。 | 在 Slice 4 中补充 source label allowlist、current input anchor not citable、cross-section citation、provenance mismatch、quality issue 枚举迁移、旧 `check_compaction_candidate` 入口变化。 |
| PF-06 | AgentDS F3 / AgentMiMo F005 | accepted | 当前 plan 的 slice 是概念域拆分，但 Slice 1 改 contract 后会导致后续模块暂时无法编译；不澄清会误导 implementation gate 的验证边界。 | 明确 Slice 1-5 是同一 plan 下的迁移序列；每个 slice 需要说明是否必须保持 pyright 可通过。若要求每个 slice 都可 review，则 implementation plan 必须采用可编译闭环 slice 或说明中间不可编译状态的允许条件和最早验证点。 |

## Non-Blocking Open Questions

以下问题不阻塞 plan fix，但 fix artifact 应尽量在 plan 中降低歧义：

- reactive multi-pass compact 的 whole-candidate repair budget 与 plan Slice 4 的关系：若 WU-CM-01 不完整实现 multi-pass，应明确 deferred owner；若实现，则列入 Slice 4 验证点。
- vNext `MemoryProjectionDiagnostics` 是否继续复用旧 diagnostic reason：plan 应要求删除旧 pinned / minimum preserve 专属 reason 或映射为 vNext diagnostic。
- prompt-local label 格式只允许作为 opaque handle，plan 不应把 label 命名规则变成业务语义。

## Next Gate

进入 `fix` gate，由 AgentCodex 修订 `docs/host/wu-cm-01-conversation-memory-plan.md`。禁止修改生产代码，禁止 commit / push / PR。
