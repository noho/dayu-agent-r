# WU-CTX-04 accepted plan 总控裁决

## Gate metadata

- Work unit：`WU-CTX-04`
- Gate：second plan re-review adjudication / accepted plan
- Accepted plan：`docs/reviews/wu-ctx-04-plan-codex.md`
- Second fix：`docs/reviews/wu-ctx-04-plan-re-review-fix-codex.md`
- Final re-review artifacts：
  - `docs/reviews/plan-review-20260722-120429.md`（AgentMiMo，`pass-with-risks`）
  - `docs/reviews/plan-review-20260722-120430.md`（AgentDS，`pass`）
- Controller decision：`pass`
- Blocking open questions：None

## Finding closure

- 前轮7组accepted requirements：`7/7 closed`，第二轮修订无回归。
- `PRR-001` Host close scheduler-before-unlock：`fixed`。Host close在持有全部RW mutex时完成scheduler mandatory quiescence、worker token/`on_cancel`传播、task/handle/lane清理与durable `STOPPED`，成功后才release；失败保持Host health/attachment `CLOSING`、mutex/record持有并允许重试。单attachment close不关闭scheduler或existing stable Attempt。
- `PRR-002` reactive caller scope：`fixed`。`engine_ingest.py`、`test_engine_ingest_mapping.py`与`test_compaction_cancellation_scope.py`已进入Slice 2封闭范围；reactive只机械适配request新schema与required first/max attempt range，既有count/overflow/recovery/fallback不变。
- 3-slice结构、Slice 2 attachment-only不可发布checkpoint、MIMO-003 deferred owner及全部rejected/evidence-invalid裁决均无漂移。

## Final new-finding adjudication

### MIMO second re-review NEW-001 — rejected-with-reason

plan的Slice 2 tests已经明确规定Host级mandatory cleanup/`STOPPED`异常注入后的完整可观察行为：close返回错误、Host health/attachment保持`CLOSING`、mutex busy、第二opener只能RO、`close_done`/`mark_closed`/`_close_cleanup_done`均不成功、重复close补完后才release。是否预先冻结测试函数名或内部barrier helper属于implementation detail，不是缺失的owner contract或验收信号；implementation review继续按这些断言验收。

### MIMO second re-review NEW-002 — evidence-invalid

`_ReactiveCompactPending.policy`当前类型为非可选`ContextBudgetPolicy`。`_start_reactive_context_recovery(...)`在`self._context_budget_policy is None`时直接走`_fail_reactive_recovery_without_request(...)`并返回，不会构造pending；只有已验证的non-null `policy`才进入`_ReactiveCompactPending(policy=policy)`。因此`pending.policy=None`不是可达状态。当前`_execute_reactive_compaction(...)`对`self._context_budget_policy`的`else 1`是事务外重新读取产生的冗余下游fallback，修订plan正确要求删除并只使用pending snapshot。

## Readiness and residual risks

- Plan状态：code-generation-ready / accepted。
- Implementation slices：3。
- Slice 1是contract-only，不公开半成品API。
- Slice 2只能以attachment/recovery/proactive/reactive机械适配联合completion signal接受，不得发布内部checkpoint。
- Slice 3独立完成execution-owner cancel与final integration。
- Windows backend环境验证、provider crash外部call非exactly-once、poll cadence、fresh schema边界继续保留既有owner。
- MIMO-003继续由AgentMiMo / AgentDS在Slice 2/3实际diff review中检查`dispatch.py`、`open_host.py`、`session_attachment.py`职责增长与semantic ownership drift。

## Completion status

- Plan review/fix/re-review state machine：complete。
- Final controller decision：`pass`。
- Accepted plan commit：pending at this artifact creation boundary；由总控创建后回填control doc。
- Next gate：implementation Slice 1 by AgentCodex。
