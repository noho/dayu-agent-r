# WU-CTX-01 Slice 1 first-call producer 定向计划复审 Controller 最终裁决

## 1. Gate metadata

- work unit：`WU-CTX-01`
- gate：Slice 1 first-call producer plan fix / directed re-review
- plan：`docs/reviews/wu-ctx-01-plan-codex.md`
- amendment handoff：
  `docs/reviews/wu-ctx-01-slice-1-first-call-producer-plan-amendment-codex.md`
- 前置 Controller 裁决：
  `docs/reviews/wu-ctx-01-slice-1-first-call-producer-plan-review-controller-adjudication.md`
- MiMo re-review：`docs/reviews/plan-review-20260724-021259.md`
- DS re-review：`docs/reviews/plan-review-20260724-021306.md`
- design truth：`docs/host/design.md` §25

## 2. 最终结论

decision：`pass`。

MiMo 与 DS 两路定向复审均为 `pass`。Controller 复核 production 直接证据、
修订后的 exact interfaces、failure matrix、production/test allowlist 与三 slice
边界后，接受本轮 plan fix。第三次 stop 的四项 blocking finding 全部闭合：

1. source policy 先从 source Run 当前 exact input fact strict 重建，source loader
   不再依赖 candidate 内只保存的 ref/digest，循环依赖消除；
2. wait continuation 闭集只有 completed/cancelled；failed/lost 保持原 terminal
   owner并且零 manifest、零 new Attempt、零 pending dispatch；
3. legacy direct queue promotion 从 admission method 到 durable transition、state
   mutation、专属类型/helper/tests 整条删除；scheduler ordinary governance 是
   queued Run 唯一 start owner，terminal/recovery wake 只负责唤醒；
4. Slice 1 只冻结 candidate/conservative sizing atoms，Slice 2 追加 new fact 且
   不复用 source fact identity，Slice 3 才启用 usage anchor；usage 缺失继续使用同一
   complete-candidate conservative estimator，不劣于当前算法。

因此 plan 已达到 code-generation-ready；允许创建 protected plan amendment commit，
随后恢复 AgentCodex 的 Slice 1 implementation。

## 3. 定向 finding disposition

| finding | final disposition | Controller 证据与约束 |
| --- | --- | --- |
| CTRL-PR-01 failed wait eligibility | **fixed / closed** | production `waiting.py` 只有 completed/cancelled 调用 resume；plan 已给 failed/lost 零 continuation artifact 反例。 |
| CTRL-PR-02 source policy strict-load循环 | **fixed / closed** | call graph 固定为 `RunRow.input_event_id -> USER_INPUT_ACCEPTED.effective_execution_config -> shared strict parser -> PolicySnapshot -> strict source loader`；worker只额外核对 caller policy。 |
| CTRL-PR-03 direct promotion bypass | **fixed / closed** | 删除范围包含 admission method/operation、durable transition、state mutation、request/result/skip类型、专属 validation/event/row helpers、imports/exports/tests；`run_transition.py`文件级零diff承诺已撤销。 |
| CTRL-PR-04 slice/fact/anchor混淆 | **fixed / closed** | design与plan均明确 Slice 1 atoms、Slice 2 new fact identity、Slice 3 anchor；两个用户指定产品修改保持独立。 |
| DS-PR-001 exhaustive stage | **fixed / closed** | 5-stage/15-cell必须显式穷举，unknown fail closed，不允许default fall-through。 |
| DS-PR-002 continuity refs | **fixed / closed** | `source_refs`必填、无默认值，production/tests全部construction site显式迁移。 |
| DS-PR-003 promotion粒度 | **fixed / closed** | 合并到CTRL-PR-03；scheduler queued ordinary owner与wake-only均已冻结。 |
| DS-PR-004 allowlist重复 | **fixed / closed** | focused清单已去重；full `pytest tests/host -q`仍是Slice 1完成门禁。 |
| DS-PR-006 wait projection | **fixed / closed** | planned/committed path共用accepted-result strict core，RunInput只消费typed projection。 |
| DS-PR-008 source helper | **fixed / closed** | source helper是existing worker candidate loader的strict超集。 |
| MiMo-03 steer parse时序 | **fixed / closed** | 同一transaction append后直接strict parse刚写入event payload，不依赖commit后回读或current config。 |
| MiMo-04 wait identity | **fixed / closed** | planned `event_plan.tool_result_event_id`必须逐字成为committed row id，owner test比较messages/source refs/candidate digest。 |

Controller 上轮 rejected 的 DS-PR-005、DS-PR-007、DS-PR-009 保持 rejected，不重新打开。

## 4. DS re-review 两项低风险观察裁决

### DS-PR-RE-001 `__init__.py` promotion re-export

disposition：`reject / factually not applicable`。

Controller 对当前 production 执行
`rg "PromoteQueuedRunInput|PromotionResult|PromotionSkipReason|promote_queued_run"
dayu/host/__init__.py dayu/host/**/__init__.py` 为零命中。当前没有 promotion
re-export需要在Slice 1删除；`dayu/host/__init__.py`进入Slice 2 allowlist是为了新增
context-usage public types，不是promotion cleanup。无需扩大Slice 1 allowlist。

### DS-PR-RE-002 私有 `_promotion_*` helper未逐名列出

disposition：`accept as implementation checklist / non-blocking`。

plan已经要求删除所有仅服务direct promotion的validation/event/row helpers，并要求
production/test零残留审计。逐个私有函数名不构成新的语义设计。AgentCodex实现时必须
用引用审计覆盖 `_promotion_*`、`_validate_promote_input`及相关imports，禁止留下dead
production code；该要求纳入Slice 1 code review，不重新打开plan gate。

## 5. Implementation resume constraints

恢复Slice 1时：

1. 先保护本轮plan amendment docs commit，partial production/tests不得混入；
2. AgentCodex只按Slice 1 allowlist修复现有partial implementation；
3. `CONTEXT_BUDGET_EVALUATED`和usage-anchored estimate algorithm继续保持独立：
   Slice 1不写fact，Slice 2实现fact/public projection，Slice 3才实现anchor；
4. provider usage缺失、非法、歧义或lineage不可证明时，必须回退当前完整candidate的
   既有conservative estimator，禁止display-text/subset弱化；
5. 完成后必须运行focused tests、full Host、full pyright、每个changed production
   file line coverage `>=80%`、README trigger audit与static zero-residual audits；
6. 在implementation review通过前，当前partial production/tests继续标记为
   `not accepted`。

## 6. Next gate

`Slice 1 implementation / resume AgentCodex`。
