# PR 190 F20 accepted plan（2026-08-08）

## Accepted revision

- binding goal：`docs/gateflow/pr-190-f20-goal-confirmation-20260808.md`，SHA-256
  `9e537fb663e647dccb702056316ad7a9a79c15a14149f8f222c76b289a9c67e0`。
- plan：`docs/gateflow/pr-190-f20-plan-20260808.md`，SHA-256
  `66074bc59b468c2614e14b7e6840a39b45d09aac9e4454dbff576550ac8b27f7`。
- plan-review fix：`docs/gateflow/pr-190-f20-plan-review-fix-20260808.md`，SHA-256
  `83fe517bd60534429abced41289203ec1bc78bc78db14b84cb57b84946a6f743`。
- RR6 AgentMiMo review：`docs/reviews/plan-review-20260808-220843.md`，SHA-256
  `457d63efcaf66a4d8d957f0e7eed75dc34e9e362759375c498cccc168c0f97fd`，二值`PASS`。
- RR6 AgentDS review：`docs/reviews/plan-review-20260808-220918.md`，SHA-256
  `74dcd5c79ff5137f8e09fb8558e2fe58781f7443137629f0bc249b740399998a`，二值`PASS`。

Controller直接复算上述byte SHA并确认两路review绑定同一revision、无material finding。F20 plan gate据此为`PASS`，该revision是唯一
accepted plan；此前各轮FAIL、finding与裁决继续作为不可覆盖的审计历史。

## Owner boundary retained

1. F19零次compaction的root cause是ordinary boundary材料/策略不足，不是产品缺陷；F20不修改产品语义。
2. provider-free proof只通过`HostDispatchScheduler.open`的同一`HostLocalExecutionOptions`注入deterministic ordinary factory与
   deterministic compactor两个真实typed port；两份Host owner ledger分别闭合。
3. proof process tree由OS deny-network owner覆盖；parent Python audit hook只拥有已核验事件的parent attempt ledger。正式MiMo链保持
   stock production CLI/default factory/production compactor，未经包装或request拦截。
4. R2/R3 pre-compact trigger只消费attempt-free canonical budget/request/terminal；proof-only完整candidate不得冒充Host runner
   manifest或进入formal schema。accepted后的`post_compact`与R4 allow继续要求真实Host manifest和完整dispatch identity。
5. 财报材料只经`dayu.fins.storage`仓储owner重验；直接文件读取诊断已作废，不是材料或overlap证据。

## Next gate and invariant

下一entry point为Slice 1：实现external provider-free proof、formal driver与publication self-tests，执行材料/storage/trigger/network/
publication preflight；actual tooling与proof artifact必须再经MiMo/DS独立双PASS后才允许创建formal provider deadline或调用MiMo。

当前provider状态为`provider_not_started`。B2保持`unadjudicated`，overall readiness保持`not ready`；本acceptance不修改accepted
oracle/scenario/handbook，不替用户裁决B2。
