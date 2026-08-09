# PR 190 F20 RR4 plan review裁决（2026-08-08）

## 冻结输入与二值结论

- plan：`docs/gateflow/pr-190-f20-plan-20260808.md`，RR4 target SHA-256
  `afb34d790c8773fa01e764a218b82554c790ff76bab96a0739f862cb294c7094`。
- fix：`docs/gateflow/pr-190-f20-plan-review-fix-20260808.md`，RR4 target SHA-256
  `ba54e241a7f7a8d3e118965f2c72edfca78a51c935a2480266adcb351f80936f`。
- binding goal：`docs/gateflow/pr-190-f20-goal-confirmation-20260808.md`，RR4 target SHA-256
  `14c18553cbb3b1ca0efb4c820476ac3bc913dd75c55ef2cc4d11f0bcdfd97c67`。
- AgentDS：`docs/reviews/plan-review-20260808-214120.md`，SHA-256
  `7e4bcd41c0d0bdcf3715bc689b1b8bb2ed673c90e397ba68cc561a85433bdb43`，结论`PASS`。
- AgentMiMo：`docs/reviews/plan-review-20260808-214233.md`，SHA-256
  `706c2e4a3a5bb786c4daa7282e2ba2dcde6d3c3745fa52c51f1f4cba5eeb1a9e`，结论`FAIL`。
- Controller gate verdict：`FAIL`；RR5双路独立`PASS`前不得实现、不得调用provider。

## F20-RR4-MIMO-001裁决：接受（高）

finding成立。RR4 plan与goal把三条不同owner边界合并成“accepted snapshot对应的下一ordinary boundary必须
`compact_soft_threshold`”，无法同时证明trigger、accepted replacement实际消费和不产生第三次operation的reconnect。

直接owner证据如下：

1. `dayu.host.context_budget._stage_pressure_action`规定`ordinary + soft`为`compact_soft_threshold`；
   `post_compact + normal/soft`为`allow_dispatch`，`post_compact + hard`为`block_hard_threshold`。
2. `dayu.host.dispatch._start_governed_after_compact`在accepted compact追平Memory后，以
   `ContextSizingStage.POST_COMPACT`重建完整candidate；allow路径提交独立manifest与budget fact后才启动Run/Attempt，hard路径在
   dispatch前fail closed。
3. `docs/host/design.md`对`ordinary`与`post_compact`的stage/action矩阵作出同一承诺。pre-compact ordinary fact因此只能证明
   compaction trigger，不能证明accepted replacement已进入实际dispatch candidate。
4. R4若仍保持两个proactive operations，则其reconnect ordinary action必须为`allow_dispatch`；若是
   `compact_soft_threshold`，Host会开始第三个operation，与R4成功predicate互斥。

## 唯一修订边界

计划与self-test必须拆成以下三个predicate，不新增产品、schema、wrapper或provider调用：

1. **trigger**：R2、R3各自唯一`stage=ordinary`的pre-compact budget/manifest/candidate，满足
   `soft <= predicted < hard`、action=`compact_soft_threshold`，并与request及同operation terminal exact linkage。不得声称该
   candidate已经包含accepted replacement。
2. **consumption**：每个accepted terminal后Memory catch-up形成的唯一`stage=post_compact` budget/manifest/candidate直接绑定
   accepted truth，满足`predicted < hard`、action=`allow_dispatch`，并与后续Run/Attempt/dispatch identity相等；hard只能按Host
   owner在dispatch前block并如实seal。
3. **reconnect**：R4的`stage=ordinary` candidate消费第二次accepted truth，action=`allow_dispatch`且operation count仍为2；若
   R4 soft-trigger第三operation，走既有`needs-more-evidence`分支。

corruption/self-test必须对ordinary/post_compact refs互换、以pre-compact digest冒充consumption、以R4 compact action冒充reconnect
逐项二值`FAIL`。binding goal已同步修订；AgentCodex只需在相同冻结scope内修订plan/fix，然后进入RR5双路独立复审。

## Scope与状态

- RR4中AgentDS确认的proof scheduler双ports、OS process-tree deny、parent-only audit hook、Fins storage owner、deadline union、clean
  seed、publication exact contract继续有效，不重新扩审或校准。
- 本裁决不修改accepted oracle/scenario/handbook，不替用户接受B2；F18/F19保持不可变。
- 当前provider状态：`provider_not_started`。
