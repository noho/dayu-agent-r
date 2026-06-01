# WU-CTX-02 + WU-CTX-03 Focused Plan Re-review (MiMo)

## 1. Gate / Scope

- Gate: WU-CTX-02 + WU-CTX-03 focused plan re-review
- Re-review target: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`
- Fix artifact: `docs/reviews/wu-ctx-02-03-plan-fix-codex-20260601.md`
- Controller adjudication: `docs/reviews/wu-ctx-02-03-plan-controller-adjudication-20260601.md`
- Focused scope: DS-1、DS-3、DS-4 修复验证；DS-2 未引入验证

## 2. Per-finding Re-review

### DS-1-已修复-fallback 最新 N 轮由 deterministic budget-driven selection 得出

**验证依据：**

Plan Section 5（Public interface）新增关键段落：

> fallback "最新 N 轮"不是 public config，也不是可任意调整的内部魔法常量。N 是预算驱动选择算法的输出：在 hard budget 约束下，先固定必须保留的 anchor / stable / compact represented context / floor，再按确定性 reverse chronological material block 顺序尽可能追加最近 raw turn blocks，最终成功选中的 raw turn 数量即为本次 N。若必保留集合本身已超过 hard budget，则 fallback estimate 结果为 over-budget 并 fail closed，不通过降低 floor 偷偷 dispatch。

Plan Implementation Decisions 明确：

> selection algorithm 不接受 public N 配置、不定义任意 max-N 常量；它先固定 current input anchor、required stable / compact represented context 和 `recent_raw_turns_floor` 下限，再按确定性 reverse chronological material block order 追加最近 raw turn blocks，直到下一 block 会超过 hard budget 或 material 耗尽。

Slice C Invariants 覆盖三类行为断言：

- 确定性："selected block ids / digest 对相同 input cursor / material list 确定"
- Floor："selected raw turn 数量不少于 `recent_raw_turns_floor`，除非可用 material 本身不足"
- Hard budget："selection 不超过 hard budget 可容纳结果"

Slice C Tests 覆盖三类验证点：

- "fallback selection 单测断言同一 input cursor / material list 输出稳定、selected raw turn 数量不少于 floor、不会选择使 estimate 超过 hard budget 的下一 block"
- "fallback estimate 单测覆盖 normal、empty stable input、over-budget"

**验证结论：已修复。** Controller 裁决要求 DS-1 满足三个条件：(1) N 不是 public config；(2) N 不是任意魔法常量；(3) tests specify determinism、floor、hard-budget behavior。Plan 三条均满足。N 由预算驱动选择算法的运行时输出确定，非静态配置或常量；测试明确覆盖稳定性、floor 下限和 hard budget 约束。

---

### DS-3-已修复-Slice D 默认禁止 durable/run_transition.py 修改和 RUN_STARTED required payload 变更

**验证依据：**

Plan Section 4（Allowed production files）新增关键约束：

> 默认不允许修改 `dayu/host/durable/run_transition.py`、SQLite durable transition 结构或 `RUN_STARTED` required payload。reactive fallback 接线必须优先在 `dayu/host/engine_ingest.py`、`dayu/host/run_input.py` 与 fallback provider 内完成。若 implementation 发现不修改 durable transition 或 required payload 就无法实现，必须停止并交回 controller 裁决。

Slice D Allowed files/modules 明确排除：

> `dayu/host/context_fallback.py`、`dayu/host/run_input.py`、`dayu/host/engine_ingest.py`、`tests/host/test_engine_ingest_mapping.py`、`tests/host/test_dispatch_scheduler.py`。默认不允许修改 `dayu/host/durable/run_transition.py`。

Slice D Exact allowed changes 明确 reactive fallback 接线路径：

> 随后优先通过 `engine_ingest.py` 内部 recovery flow、`run_input.py` fallback provider 与现有 recovery start transition 创建新 Attempt

Slice D Exact allowed changes 明确禁止项：

> 不得新增或修改 `RUN_STARTED` required payload，不得修改 durable table schema。

Slice D Functions/classes/types 明确诊断传递方式：

> fallback diagnostic ref 通过 failed payload 与 fallback provider 关联，不通过扩展 `RUN_STARTED` required payload 传递。

Slice D Stop condition 双重覆盖：

> 若 recovery transition 必须把 `context_compacted_event_id` 伪造成 non-null 才能启动，停止；若实现必须修改 `dayu/host/durable/run_transition.py`、SQLite durable transition、`RUN_STARTED` payload validator required field 集合或 public typed payload required 字段，停止并交回 controller。

**验证结论：已修复。** Controller 裁决要求 DS-1 满足三个条件：(1) 默认不允许修改 durable transition 或 RUN_STARTED required payload；(2) reactive fallback 优先在 engine_ingest / run_input / fallback provider 内接线；(3) stop condition 明确。Plan 三条均满足。Slice D 的 allowed files 排除了 run_transition.py，exact allowed changes 指定了 engine_ingest + run_input + fallback provider 的接线路径，stop condition 覆盖了 durable schema、required payload 和 public typed payload 的越界场景。

---

### DS-4-已修复-Slice C 增加 estimator compatibility 前置核对

**验证依据：**

Slice C 新增 Prerequisite check 段落：

> 在接线 proactive dispatch 前，先用最小单元测试或现有 estimator 调用点验证 conservative estimator 能接受 fallback-selected `message_fragments` 子集；覆盖 normal、empty stable input、over-budget 三类 fallback estimate。若不兼容，只允许增加最小 typed adapter，不改估算算法、不新增 provider tokenizer、不新增 public policy field。

Implementation Decisions 明确前置要求：

> Slice C 开始 fallback dispatch 实现前必须先核对现有 conservative estimator 能接受 fallback-selected `message_fragments` 子集。fallback selection 生成后必须调用现有 conservative estimator，使用 selected material block text 与 current input anchor 作为 `BudgetEstimateInput.message_fragments`。预算通过才 dispatch；预算仍超 hard threshold fail closed。若 estimator 不兼容 selected subset shape，只允许增加最小 typed adapter 以转换输入形状，不改变估算算法、不新增 provider tokenizer、不新增 public policy field。

Slice C Tests/validation 覆盖三类估算路径：

> fallback estimate 单测覆盖 normal、empty stable input、over-budget

Residual risk RR-CTX-PLAN-02 更新为：

> Slice C 前置核对 conservative estimator 对 fallback-selected `message_fragments` 子集的兼容性；fallback 后强制重估；normal、empty stable input、over-budget 测试覆盖不 silent overflow。

**验证结论：已修复。** Controller 裁决要求 DS-4 满足三个条件：(1) estimator compatibility 作为 Slice C 前置步骤；(2) tests for normal、empty stable input、over-budget；(3) no provider tokenizer or public policy field。Plan 三条均满足。Prerequisite check 在 Slice C 顶部，明确要求 implementation 开始前先验证 estimator 兼容性；测试覆盖三类估算路径；不兼容时只允许最小 typed adapter，不引入 provider tokenizer 或 public policy field。

---

### DS-2-未引入-scene inheritance 防御未纳入必修 scope

**验证依据：**

Controller 裁决明确 DS-2 为 rejected-with-reason：

> 当前所有 scene manifest 的 `extends` 为空是配置事实，不是设计真源要求的长期契约；新增"不得继承 conversation_compaction"的防御性断言会把非目标变成配置架构约束，超出当前 WU success signal。

Plan Non-goals 新增一条（第 39 行）：

> 不改变 scene inheritance semantics；当前 WU 只要求 `conversation_compaction` scene default model 与默认 execution profile compactor model 对齐，不新增"不得继承 conversation_compaction"的配置约束或防御性测试。

检查项：
- Plan 未增加 scene inheritance 防御断言或必修测试
- Plan 未在 Slice A 或任何其他 slice 中加入 scene extends 断言
- Plan 仅在 Non-goals 中记录"不改变 scene inheritance semantics"
- Fix artifact 确认"未增加 scene inheritance 防御断言或必修测试"

**验证结论：未引入。** DS-2 作为 rejected finding 未被误引入必修 scope。Plan 仅在 Non-goals 中补充说明，未增加任何防御性断言或必修测试，符合 controller 裁决。

## 3. Final Status Summary

| Finding ID | 来源 | 裁决 | Re-review 状态 | 说明 |
|---|---|---|---|---|
| DS-1 | DS plan review | accepted | 已修复 | N 由预算驱动选择算法确定，非 public config 或魔法常量；tests 覆盖 determinism、floor、hard-budget |
| DS-3 | DS plan review | accepted | 已修复 | 默认禁止 durable/run_transition.py 修改和 RUN_STARTED required payload 变更；reactive fallback 优先在 engine_ingest / run_input / fallback provider 接线；stop condition 明确 |
| DS-4 | DS plan review | accepted | 已修复 | Slice C 增加 estimator compatibility 前置核对；tests 覆盖 normal、empty stable input、over-budget；无 provider tokenizer 或 public policy field |
| DS-2 | DS plan review | rejected | 未引入 | scene inheritance 防御未纳入必修 scope；仅在 Non-goals 补充说明 |

## 4. Conclusion

**结论：PASS** — 全部 accepted findings 已修复，rejected finding 未被引入。

Plan fix 对 DS-1、DS-3、DS-4 的修复均直接对齐 controller 裁决要求，plan 文本变更具体、可验证，implementation agent 可直接按修改后的 plan 执行。DS-2 按裁决仅在 Non-goals 中记录，未引入任何防御性断言或必修测试。

Focused re-review 无新增 findings，无 blocking questions。

---

- **Artifact path**: `docs/reviews/wu-ctx-02-03-plan-rereview-mimo-20260601.md`
- **Conclusion**: PASS
- **Unresolved count**: 0
- **Blocking questions**: none
