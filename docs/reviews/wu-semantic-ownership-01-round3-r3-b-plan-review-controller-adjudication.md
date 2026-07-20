# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B Plan Review Controller Adjudication

## 裁决范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-B`
- Plan artifact：`docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`
- Review artifacts：
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-ds.md`
- 设计真源：`docs/engine/design.md`、`docs/host/design.md`
- 控制真源：`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`

## 总体结论

R3-B plan 的目标、owner boundary、source finding 裁决和 3 个 implementation slices 成立，可以进入 plan-fix gate。两路 review 未提出 blocking question，也未要求改变 R3-B 的基本切分。

所有 review findings 均接受为 plan-fix 约束。它们不扩大 scope，不引入 Host 下游补救，不改变 `accepted=7 / narrowed=1 / rejected=2` 的 source finding 裁决。

## Finding 裁决

### PF-01 accepted — post-done cancellation rejection 必须显式测试

- 来源：AgentMiMo Finding 01
- 严重度：中
- 裁决：接受，必须修 plan。
- 理由：R3-B 的核心 owner correction 是 `RunnerDoneData` 作为单次 Runner iteration 的 typed commit fact。现有 plan 已要求迟到取消不得改写 done-derived terminal，但 allowed tests / concrete assertions 没有足够明确地要求 post-done cancellation rejection 反例。该测试缺口会让实现只覆盖 done 前取消，留下 commit boundary 回归风险。
- 修复要求：S1 concrete assertions 必须明确新增 post-done cancellation rejection matrix。至少覆盖 ordinary final、force-answer final、protocol/error done、tool-call done；done 前取消仍必须保持 `run_cancelled`。

### PF-02 accepted — finish_reason forcing scan 需要语义级 guard

- 来源：AgentMiMo Finding 02
- 严重度：低
- 裁决：接受，作为 validation plan 改进。
- 理由：精确变量名 scan 可被等价重构绕过。自动 scan 不能替代人工 review，但 plan 应给 reviewer 一个稳定的语义级 guard。
- 修复要求：S2 validation commands 增加对 `FinishReason.TOOL_CALLS` 的语义级 scan，并要求 review 人工确认每处赋值都来自 `_choice_policy` 或显式 fail-closed terminal-shape policy，不得由 parser 直接强制成功。

### PF-03 accepted — position routing 必须纳入 identity conflict rules

- 来源：AgentDS Finding 1
- 严重度：低
- 裁决：接受，必须修 plan。
- 理由：`ToolCallAggregator` 当前有 index、id、position 三种 routing signal。position routing 解析出的 index 必须受同一 conflict rules 约束，否则实现可能只修 native index / provider id 主路径，残留间接 merge。
- 修复要求：S2 identity conflict rules 明确任一 routing mechanism，包括 position routing，导致的 occupied target、same id/two indices、same index/two ids 或 remap merge 均 fatal。negative matrix 增加 position-routed conflict 反例。

### PF-04 accepted — runner exception candidate 必须统一 first-candidate helper

- 来源：AgentDS Finding 2
- 严重度：低
- 裁决：接受，必须修 plan。
- 理由：R3-B 已将 failure diagnostic owner 定为 `_IterationState` 的 first accepted failure candidate。runner exception 路径若保留直接赋值，会绕开同一 owner rule。
- 修复要求：S1 implementation decisions 明确所有 `failure_candidate` 写入，包括 runner generator exception，都必须通过 first-candidate helper。无先前 candidate 时 runner exception 仍可成为 terminal failure；已有 protocol/HTTP/context candidate 时不得覆盖。

### PF-05 accepted — 移除 Agent finish_reason fallback 时必须 fail closed

- 来源：AgentDS Finding 3
- 严重度：低
- 裁决：接受，必须修 plan。
- 理由：`Agent` 的 `or FinishReason.STOP` 是 parser omission 的下游补救。移除时不能留下 `None` 在 `_classify_iteration()` 中静默 fallthrough。
- 修复要求：S1 明确把 fallback 替换为 typed assertion 或 owner-level fail-closed diagnostic；不得继续默认 `STOP`，也不得让 `None` 进入无关分支。S2 完成后该断言或诊断路径应只作为 contract guard。

## 非目标与约束

- 不新增第四个 implementation slice。
- 不修改 rejected source findings：runner identity length-framed encoding 与 OpenAI error classifier structured-code-first fallback 维持 rejected-with-reason。
- 不增加 Host repair、compatibility flag、旧 dict arguments shim、provider capability profile 或通用 JSON Schema engine。
- plan-fix 只更新 plan artifact 和必要的 review artifact；不修改生产代码、测试、README。

## 下一 gate

AgentCodex 执行 plan-fix，更新 `docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md` 并产出 plan-fix artifact。完成后由 AgentMiMo / AgentDS 进行 plan re-review；re-review 通过后总控再接受 plan 并进入 implementation gate。
