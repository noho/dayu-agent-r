# WU-CM-01 Plan Fix Report - AgentCodex

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | plan fix |
| agent | AgentCodex |
| design source | `docs/host/design.md` 第 24 章 / 第 25 章 |
| control source | `docs/host/issues-implementation-control.md` |
| plan artifact | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| controller adjudication | `docs/reviews/wu-cm-01-plan-review-controller-adjudication.md` |

## Fix Summary

本 fix gate 只修订 plan artifact，并新增本报告；未修改生产代码、tests、README、control doc，未 commit / push / PR，未进入其它 gate。

修改的 plan 小节：

- `Issue-80 / Design 24.7 Evaluation Mapping`：新增独立映射小节。
- `Slice Verification Boundary`：新增 Slice 1-5 中间可编译性 / pyright 验证边界。
- `Slice 1 - Typed Contract And Policy Replacement`：补充旧 continuity、minimum preserve、vNext compact output schema、旧 candidate / quality issue / diagnostic reason 迁移规则。
- `Slice 2 - Durable Snapshot Store And Projection Migration`：补充全新 schema 删除旧 durable item kind 与不做旧库兼容读取。
- `Slice 3 - Compact Material VNext And LLM Parser`：补充 vNext parser schema、prompt-local label opaque 约束、旧 material block kind 到 vNext section 映射表。
- `Slice 4 - Accept Barrier, Whole-Candidate Repair, And Fallback Governance`：补充 vNext quality checker 规则、source label allowlist、旧 checker 入口变化、reactive multi-pass repair budget。
- `Slice 6 - Public Smokes, README Sync, And Issue-80 Mapping`：改为复核 plan 内 #80 映射，不再把映射推迟到 implementation report。

## Accepted Findings

| Finding | 状态 | 处理位置 |
|---|---|---|
| PF-01 issue-80 / design 24.7 评测维度映射 | fixed | 新增 `Issue-80 / Design 24.7 Evaluation Mapping`，逐条标记 current scope covered / deferred-with-owner / explicit non-goal，并给出 slice 与测试入口。 |
| PF-02 `ConversationContinuityKind` 全量处置与 minimum preserve 迁移 | fixed | Slice 1 补充旧 continuity kind 全量处置；Slice 2 补充全新 schema 删除旧 durable item kind，不写旧库兼容读取。 |
| PF-03 vNext compact output candidate schema 与旧类型删除边界 | fixed | Slice 1 / Slice 3 明确 design 24.3 是唯一真源，并列出旧 candidate、patch、preservation evidence、minimum preserve reason 与旧 quality issue 删除边界。 |
| PF-04 旧 compact material block kind 到 vNext sections 映射 | fixed | Slice 3 新增映射表，覆盖 pinned、fact、working assumption、open question、raw user / assistant、episode summary、accepted tool evidence、current input anchor。 |
| PF-05 Context Governance quality checker 规则 | fixed | Slice 4 补充 source label allowlist、current input anchor not citable、cross-section citation、provenance mismatch、vNext quality issue migration 与旧 `check_compaction_candidate` 入口变化。 |
| PF-06 Slice 1-5 可编译性 / pyright 验证边界 | fixed | 新增 `Slice Verification Boundary`，明确 Slice 1-5 是整体迁移序列，中间不承诺全量 pyright，最早生产代码 pyright 闭合点为 Slice 5，最终全量验证在 Slice 6 后。 |

## Open Questions Reduction

| Open question | 处理状态 | 说明 |
|---|---|---|
| reactive multi-pass compact repair budget / scope | addressed | Slice 4 明确 reactive multi-pass 与 whole-candidate repair 共用一次 operation 的 `max_compaction_attempts_per_operation` 总预算，并禁止中间 pass partial compact。 |
| vNext diagnostics reason 迁移 | addressed | Slice 1 明确删除 minimum preserve / pinned / working assumption 专属 diagnostic reason，并迁移到 vNext reference continuity / generic diagnostic 语义。 |
| prompt-local label opaque handle | addressed | Slice 3 明确 label 只作为 opaque handle，不承载业务类型、顺序、优先级、时间或 durable identity 语义。 |

## Validation

本 gate 按要求不运行测试、不运行 pyright。已执行只读核对：

- 读取 controller adjudication、两份 plan review、design 24 / 25、control doc WU-CM-01 / WU-CM-10。
- 用 `rg` 核对 plan 中 #80、旧 continuity、旧 candidate、旧 checker 入口等相关残留。

## Residual Risk

当前 accepted findings 均已处理。剩余风险是 implementation gate 需要严格按 plan 执行并在 Slice 5 / Slice 6 跑受影响测试与 pyright；本 fix gate 未验证代码可编译性。
