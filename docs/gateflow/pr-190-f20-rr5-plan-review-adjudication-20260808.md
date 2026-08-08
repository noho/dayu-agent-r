# PR 190 F20 RR5 plan review裁决（2026-08-08）

## 冻结输入与二值结论

- plan：`docs/gateflow/pr-190-f20-plan-20260808.md`，RR5 target SHA-256
  `b0a9bb895d609afdced0da759003f67400312a3c28ef190fbf6eeffde9882a99`。
- fix：`docs/gateflow/pr-190-f20-plan-review-fix-20260808.md`，RR5 target SHA-256
  `5249957dcd6c88fb9c0b81874fc38fa9733432c2db181ccaf4cf921ffd00ede8`。
- binding goal：`docs/gateflow/pr-190-f20-goal-confirmation-20260808.md`，RR5 target SHA-256
  `94a66afd08cb664a7aa20fcb174e6416b9f0343f67298cb5ee4f7032843b02ad`。
- AgentMiMo：`docs/reviews/plan-review-20260808-215833.md`，SHA-256
  `2e5c11e8cc178c9009e700e06975dab1d6466de96bfb53e9f0c0e9cd2648262c`，结论`PASS`。
- AgentDS：`docs/reviews/plan-review-20260808-215803.md`，SHA-256
  `f704414a77d17d408e427bb9bd088e3437fa60ddee681da24108a86f25348a88`，结论`FAIL`。
- Controller gate verdict：`FAIL`；RR6双路独立`PASS`前不得实现、不得调用provider。

## F20-RR5-DS-001裁决：接受（高）

finding成立。RR5已正确区分`ordinary`trigger、`post_compact`consumption与R4 reconnect，但仍把allow-only runner-call manifest强加到
`ordinary + compact_soft_threshold`分支，要求了产品不会持久化的Host事实。

直接owner证据如下：

1. `dayu.host.dispatch`在ordinary sizing后，只有decision=`allow_dispatch`才调用
   `_commit_dispatch_candidate_in_transaction`。
2. compact/hard分支直接写`CONTEXT_BUDGET_EVALUATED`，其`attempt_id=None`、`execution_id=None`；compact随后进入proactive
   request/material/compactor路径，不调用runner manifest recorder。
3. `_commit_dispatch_candidate_in_transaction`才拥有完整sizing snapshot、
   `record_prepared_runner_call_candidate_in_transaction`、Attempt/execution/dispatch identity与Run start的原子提交，因此真实runner
   manifest只属于allow candidate。
4. canonical `ContextBudgetEvaluatedPayload`已经拥有trigger所需的candidate cursor、logical projection ref、input digest、stage、policy、
   estimator、prediction、threshold、pressure与action，但不承诺manifest kind、manifest ref/SHA、Attempt或execution。

这不是产品缺陷：被compact拦截的candidate不会成为runner call，当前F20 registry/goal也不要求其先生成runner manifest。正确的最小修订是
让formal trigger只消费实际存在的canonical budget/request/terminal truth；provider-free proof可从同一production candidate builder冻结
完整run-owned proof projection用于场景存在性审计，但必须通过input digest/ref与budget fact exact equality，且不得命名、发布或投影成
Host runner-call manifest。

## 唯一修订边界

1. R2/R3 pre-compact trigger contract改为唯一attempt-free canonical budget fact：cursor、logical candidate projection ref、input digest、
   stage=`ordinary`、soft/hard区间、action=`compact_soft_threshold`；加同Run的唯一compaction request与同operation terminal linkage。
2. 从formal/private/publication typed contract删除pre-compact manifest ref/SHA/kind/sizing snapshot要求。proof-only完整candidate projection
   使用独立closed variant/name，formal stock CLI不得引用它补证。
3. `post_compact`与R4均是allow candidate，继续要求真实Host runner manifest及Run/Attempt/execution/dispatch equality，不得退化。
4. corruption/self-test新增“为pre-compact compact branch伪造runner manifest”必须`FAIL`，并保留pre-compact digest冒充consumption、
   ordinary/post_compact ref互换及R4 compact冒充reconnect均`FAIL`。

## Scope与状态

- MiMo RR5确认的typed proof双端口、OS process-tree deny/parent audit、formal stock CLI、storage owner、deadline与publication其余契约继续
  有效，不重新扩审或校准。
- binding goal已同步修订；AgentCodex只修改同一plan/fix后进入RR6。
- 不修改产品、accepted oracle/scenario/handbook，不替用户接受B2；F18/F19保持不可变。
- 当前provider状态：`provider_not_started`。
