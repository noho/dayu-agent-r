# PR 190 F18 Plan Acceptance

## Gate decision

- Accepted plan：`docs/gateflow/pr-190-f18-plan-20260808.md`。
- Final independent reviews：
  - AgentMiMo `docs/reviews/plan-review-20260808-161615.md`：binary provider gate `PASS`，无material finding；
  - AgentDS `docs/reviews/plan-review-20260808-161920.md`：binary provider gate `PASS`，无material finding。
- Controller direct verification：`PASS`。
- Gateflow transition：`plan-review -> accepted-plan checkpoint -> implementation`。

## Accepted owner path

1. 完全fresh workspace从首opener固定同一constrained profile：MiMo、floor0、output caps 1 item/160 chars、soft ratio
   0.018、hard ratio0.5、reactive cap1、attempt cap5、24 loop calls加最多1 force-answer。
2. R1完成FY2024真实工具证据。R2的FY2025 acquisition current input在pre-start触发只含completed R1的baseline；current
   anchor保持独立。accepted后由同一Run的POST_COMPACT/CONTINUATION取得FY2025真实证据。
3. R3 pre-start是唯一target：previous FY2024 atom、completed R2 FY2025 evidence、unsupported用户材料与真实caps在同一
   immutable boundary。Reactive snapshot不拥有同Run新tool result，因此一律non-covering seal。
4. Expected ordinary/compactor cost为18(+1)/2 operations 10 calls；typed hard为ordinary 75/100、compactor正式5/25、
   含reconnect 7/35；wall为三链各540秒、finalization reserve180秒。
5. B1 immutable bundle只读；B2使用全新bundle/public/private root。B2在用户裁决前保持unadjudicated，overall non-ready。

## Fail-closed boundary

- 任一fresh fixed-profile链再次出现`runner_candidate_invalid`：停止整个B2并重开owner investigation。
- 任何non-trigger、reactive、material缺失、自然branch不符合role或budget/deadline耗尽：原样seal并写
  `needs-more-evidence`，不得调参、padding、重跑同workspace或伪造输出。
- 旧Trial2 seq327继续是`unresolved; original owner exception was not durably captured; no causal inference`，不作为B2
  mandatory前置，也不由fresh结果反推。

## Scope guard

不改产品迁就旧setup；不处理Issue 192、Fins schema、B1 cold analyzer；不使用DeepSeek/fake/mock；不读取、修改、stage或提交
`docs/reviews/plan-review-20260808-095346.md`。

Plan gate：`accepted`。下一入口：AgentCodex implementation；任何真实provider调用仍须在B1 implementation/review与fresh
pre-provider calibration通过后按accepted plan执行。
