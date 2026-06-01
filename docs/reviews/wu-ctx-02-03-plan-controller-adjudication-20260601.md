# WU-CTX-02 + WU-CTX-03 Plan Review Controller Adjudication

## 1. 裁决结论

Plan review gate 需要一次 plan fix，然后进入 focused re-review。

`AgentMiMo` 结论为 pass，无 blocking finding；`AgentDS` 结论为 pass，但提出 4 个 findings。基于 `docs/host/design.md` 的设计目标和第一性原理，当前 phase 的最佳实践是接受会影响 implementation handoff 清晰度和状态机边界的 findings，拒绝会把当前配置事实过度上升为长期约束的 finding。

## 2. Finding 裁决

| ID | 来源 | Finding | 裁决 | 理由 |
|---|---|---|---|---|
| DS-1 | docs/reviews/wu-ctx-02-03-plan-review-ds-20260601.md | Slice C fallback "最新 N 轮" ceiling 参数不完全由现有 policy 派生 | accepted | fallback selection 是 WU-CTX-02 的核心逻辑；plan 若不明确 N 的派生规则，implementation agent 可能引入任意内部常量或误以为必须新增 public policy 字段。应把 N 定义为预算驱动、确定性选择结果，而不是新的 public contract。 |
| DS-2 | docs/reviews/wu-ctx-02-03-plan-review-ds-20260601.md | Slice A 未验证 scene manifest 变更对其他 scene 的继承影响 | rejected-with-reason | 当前所有 scene manifest 的 `extends` 为空是配置事实，不是设计真源要求的长期契约；新增“不得继承 conversation_compaction”的防御性断言会把非目标变成配置架构约束，超出当前 WU success signal。 |
| DS-3 | docs/reviews/wu-ctx-02-03-plan-review-ds-20260601.md | Slice D durable/run_transition.py 修改边界依赖停止条件 | accepted | Reactive fallback 不应通过扩展 `RUN_STARTED` required payload 或 durable schema 来传递诊断；plan 应优先禁止修改 durable transition，除非先回 controller。 |
| DS-4 | docs/reviews/wu-ctx-02-03-plan-review-ds-20260601.md | Fallback budget re-estimate 使用 conservative estimator 的 block shape 兼容性未前置验证 | accepted | RR-CTX-PLAN-02 原本就是 needs-more-evidence；plan 应把 estimator 输入形状核对作为 Slice C 前置步骤和测试点，避免 implementation 时临时扩 scope。 |

## 3. Required Plan Fix

Plan fix 必须只修改 `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`，并新增 fix artifact `docs/reviews/wu-ctx-02-03-plan-fix-codex-20260601.md`。

必须修复：

- 明确 fallback "最新 N 轮"不是新的 public config，也不是任意魔法常量。N 应由 deterministic budget-driven selection 得出：先保留 current input anchor、required stable / compact represented context 和 `recent_raw_turns_floor` 下限，再按确定性 reverse chronological material block order 追加最近 raw turn blocks，直到下一 block 会超过 hard budget 或 material 耗尽。测试必须断言同一 input cursor / material list 输出稳定，且 selected raw turn 数量不少于 floor、不会超过预算可容纳结果。
- 收紧 Slice D 的 `durable/run_transition.py` 边界：默认不允许修改 `dayu/host/durable/run_transition.py` 或 `RUN_STARTED` required payload；reactive fallback 应优先在 `engine_ingest.py` / `run_input.py` / fallback provider 内部接线。如果实现发现必须修改 durable transition 或 required payload，必须停止回 controller。
- 在 Slice C 增加 estimator compatibility 前置核对：验证现有 conservative estimator 能接受 fallback-selected `message_fragments` 子集；若不兼容，只允许做最小 typed adapter，不改变估算算法、不新增 provider tokenizer、不新增 public policy field。测试覆盖 normal、empty stable input、over-budget 三类 fallback estimate。
- 将 DS-2 记录为 rejected finding，不要求 plan 增加 scene inheritance 防御测试；可保留“当前 WU 不改变 scene inheritance semantics”的 non-goal。

## 4. Re-review Scope

Focused re-review 只需复核 DS-1、DS-3、DS-4 是否已修复，以及 DS-2 是否未被误作为必修 scope 引入。

## 5. Blocking Open Questions

none

## 6. Focused Re-review Final Adjudication

Focused re-review artifacts:

- `docs/reviews/wu-ctx-02-03-plan-rereview-mimo-20260601.md`
- `docs/reviews/wu-ctx-02-03-plan-rereview-ds-20260601.md`

Final status:

| ID | Controller decision | Re-review status | Final adjudication |
|---|---|---|---|
| DS-1 | accepted | 已修复 | accepted finding closed；plan now defines fallback N as deterministic budget-driven selection output, not public config or magic constant. |
| DS-3 | accepted | 已修复 | accepted finding closed；plan now excludes default durable transition / `RUN_STARTED` required payload changes and has clear stop condition. |
| DS-4 | accepted | 已修复 | accepted finding closed；plan now requires estimator compatibility prerequisite and normal / empty stable input / over-budget estimate tests. |
| DS-2 | rejected-with-reason | 未引入 / 证据失效 | rejected finding remains excluded from mandatory scope; plan only records scene inheritance semantics as non-goal. |

Plan gate final conclusion: accepted. The plan is handoff-ready / code-generation-ready, with no blocking open questions.
