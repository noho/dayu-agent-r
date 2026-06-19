# WU-CM-12 Plan Review Adjudication

## Scope

- gate: plan review adjudication
- work unit: WU-CM-12 Conversation Memory design refinement and implementation drift repair
- plan: `docs/host/host-issues/wu-cm-12-conversation-memory-drift-plan.md`
- reviews:
  - `docs/reviews/plan-review-20260618-135627.md`
  - `docs/reviews/plan-review-20260618-135902.md`

本裁决只处理 plan review findings，不修改 plan。由于 `docs/reviews/plan-review-20260618-135627.md` 给出 `fail` 且包含一个高严重度状态机 finding，plan gate 当前不通过，必须进入 plan fix。

## Decisions

| Finding | Decision | Rationale |
|---|---|---|
| DS F1: S4 tier 1-3 recovery loop 缺少 cancellation / stale-state 观测机制 | accepted | `docs/host/design.md` 明确 proactive compaction 必须使用 durable Run 状态观察 token，stale / cancelled / session closed / execution replaced / cursor mismatch 不是可 repair 错误。plan 只写 commit 前 recheck，不足以指导 implementation。 |
| DS F2: S2 fallback selected caps 与 budget estimator loop 集成方式未指定 | accepted | plan 写了 floor wins over caps，但没有固定 floor、fallback item/char cap、hard budget estimator 三方优先级；implementation Agent 仍需自行设计 selector 语义。 |
| DS F3: selected-id/source-ref provenance drift 测试策略不够 adversarial | accepted | selected id 存在检查已有，plan fix 必须要求 deliberately mismatched fixtures 覆盖 current input ref、selected source refs、fallback digest / material view mismatch 等 fail-closed 路径。 |
| DS F4: section-aware degrade 禁止动作测试缺少具体 fixture 设计 | accepted | no truncation / no rewrite 不能靠短文本 happy path 证明；plan fix 必须要求长文本 byte-exact keep/drop、summary exact-match / drop 等 adversarial fixture。 |
| DS F5: S2 缺少 eligible raw turn block 缺少 run_id 时不应静默丢弃的测试 | accepted | `turn_group_id` 是本 WU 的核心保护边界。eligible raw block 缺少 run id 时不得被 `None` 分组静默跳过，plan fix 必须指定 diagnostic / fail-closed 或 source-path fix 的验收方式。 |
| MiMo 01: tier 2 section-aware degrade within-section 排序字段未由 plan 选定且缺少排序确定性测试 | accepted | 与 design re-review 的 handoff 要求一致。plan fix 必须明确排序字段和方向，例如 EventLog sequence descending、material order、stable block id tie-break，并加入 deterministic ordering assertion。 |
| MiMo 02: tier 1/2/3 各 tier 缺少独立行为测试 | accepted | 与 DS F4 / S4 test gap 同源但覆盖面不同。plan fix 必须要求每个 tier 独立触发场景和各自 assemble 语义断言。 |
| MiMo 03: S1 范围跨三个模块 | rejected-with-reason | 该 finding 自身承认变更内聚且属于架构现实。S1 同时触碰 material block shape、memory projection 和 run input rendering，是因为同一 LLM-facing policy owner 漂移跨这些现有模块；拆分会制造更细但更脆的 slice 依赖。保留为 implementation 注意点，不要求 plan fix。 |
| MiMo 04: selected-id/source-ref provenance guard 未覆盖 turn-group 内一致性 | accepted | 与 DS F3 互补。plan fix 必须在 S3 增加 turn_group_id consistency / protected group consistency guard 和 deliberately mixed-turn-group fixture。 |
| MiMo 05: S1/S2 未显式处理 durable payload 损坏场景 | accepted | 与 DS F5 和 fail-closed design truth 相关。plan fix 必须在 S1/S2 error handling 和 tests 中说明 payload / artifact 损坏不能生成不可信 LLM-facing material。 |

## Required Plan Fix

AgentCodex 必须只修改 `docs/host/host-issues/wu-cm-12-conversation-memory-drift-plan.md`，补齐：

- S4 每次 tier attempt 前、proposal 返回后、commit 前的 durable Run state / input cursor / cancellation / stale-state 检查和测试。
- S2 fallback selection 的 floor、fallback item cap、fallback char cap、hard budget estimator 优先级。
- S3 selected-id/source-ref/fallback digest/material view mismatch、current input ref mismatch、mixed turn group 的 adversarial fail-closed fixtures。
- S4 tier 1、tier 2、tier 3 的独立触发场景与独立 assertions。
- S4 degrade 禁止动作的长文本 byte-exact keep/drop、summary exact-match / drop、no new summary / no new memory fixtures。
- S2 missing `run_id` / missing `turn_group_id` 对 eligible raw turn block 的 diagnostic / fail-closed / source path repair expectation。
- S1/S2 durable payload / artifact corruption handling expectation。

## Gate Decision

Plan review gate status: fail.

Next gate: plan fix by AgentCodex, followed by focused plan re-review by AgentMiMo and AgentDS.
