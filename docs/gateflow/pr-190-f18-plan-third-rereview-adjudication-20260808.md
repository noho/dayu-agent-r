# PR 190 F18 Third Plan Re-review Adjudication

## Gate decision

- Reviews：
  - `docs/reviews/plan-review-20260808-155504.md`（AgentDS，`fail`）；
  - `docs/reviews/plan-review-20260808-155519.md`（AgentMiMo，`fail`）。
- Controller verdict：`fail`；provider gate继续关闭，返回 AgentCodex 做第三次最小plan fix。
- 两路共同通过：floor=0/current anchor、B1 raw `execution_outcome=error`、monotonic 540*3+180、final-tree helper独占
  `secret-scan.json`、fresh fixed-profile再次`runner_candidate_invalid`全局停止。

## Accepted findings and direct owner evidence

### F18-TRRA-01 — budget decision误用了conservative estimate

- 接受 `F18-DS-3R-001` 与 `MIMO-F18-RR3-001` 主结论，严重程度`high`。
- Host pressure唯一消费`predicted_input_tokens`。Trial2 typed rows直接显示：initial ordinary seq5 predicted `9048`；同Run
  continuation可到`19174/20316`；首个post-tool ordinary seq125 predicted `20363`；seq139/153的prediction只有
  `19274/19707`，原plan的`20998`是conservative field。
- ratio `0.02`/threshold `20971`的旧band无效。候选ratio `0.018`由typed policy派生threshold `18874`，满足
  `9048 < 18874 < 20363`；同Runcontinuation即使越soft仍由五阶段矩阵`ALLOW_DISPATCH`。fresh stochastic值仍须原样观察，
  不声称精确ordinal保证。

### F18-TRRA-02 — FY2025同Run reactive snapshot不拥有新工具结果

- 接受 `F18-DS-3R-002` 与 `MIMO-F18-RR3-004`，严重程度`high/medium`。
- Reactive material view的delta终点是active Run的`USER_INPUT_ACCEPTED.event_sequence`排他边界；同Run后续
  `TOOL_RESULT_ACCEPTED`不能进入该snapshot。当前anchor也不能冒充canonical FY2025 evidence。
- 删除“FY2025 tool result后的reactive operation可作target”。任一reactive operation都是unexpected/non-covering并立即seal。

### F18-TRRA-03 — operation cap不是per-chain=2

- 接受 `F18-DS-3R-003` 与 `MIMO-F18-RR3-003`，严重程度`high`。
- typed policy只拥有每Run reactive cap；另有每Run/input最多一个proactive operation。最小fixed profile把
  `max_reactive_compactions_per_run`从2冻结为合法值1，降低但不伪称消除unexpected reactive上界。
- 三个正式Runs的硬operation上界是`1 + 2 + 2 = 5`：R1最多1 reactive；R2/R3各最多1 proactive+1 reactive；每operation
  最多5attempts，故正式链hard compactor-call上界25。replacement reconnect Run仍可能有1 proactive+1 reactive，故总hard为
  7 operations/35 calls。
  expected mandatory path仍只有baseline+target两operations/最多10 calls。任一reactive一经观察即seal，不继续dependent provider。

### F18-TRRA-04 — force-answer是额外Runner call

- 接受 `F18-DS-3R-004` 与 `MIMO-F18-RR3-002`，严重程度`high`。
- standard-256k固定`max_iterations=24`且`fallback_mode=force_answer`；Engine可在24个loop calls后再执行一次
  `_run_force_answer`，所以每Runhard上界25。

## Required third plan fix

1. 首opener固定floor=0、output caps 1 item/160 chars、soft ratio0.018、hard ratio0.5、reactive cap1、attempt cap5、
   ordinary policy24+force-answer；不得运行中突变。
2. R1只做真实FY2024 tool acquisition并成功终止。R2是FY2025 tool acquisition input，同时携带unsupported
   `21.7%/18.2%`；其pre-start ordinary boundary若自然触发baseline，source只允许包含completed FY2024 material，current R2
   仍是独立anchor。baseline必须accepted且恰有一个canonical FY2024 EvidenceFact。
3. baseline accepted后，同一R2经POST_COMPACT/CONTINUATION继续真实获取FY2025 evidence；这些stage在soft pressure下allow。
   R2任何reactive operation都不能覆盖target，立即seal。R2未触发baseline、baseline不accepted、未成功取得FY2025 provenance或
   terminal非succeeded均seal。
4. R3是唯一target no-tool Run；pre-start initial input必须直接含previous FY2024 atom、completed R2 FY2025 evidence、unsupported
   material与真实caps。若未触发、缺项或reactive出现均seal。accepted后replacement chain最多R4 fresh reconnect。
5. 每链正式阶段最多3 ordinary Runs，expected ordinary calls `10+7+1=18`；reconnect后`19`。按每Run25，hard分别
   `75/100`。每terminal仍核对cumulative expected checkpoint，超出即不启动下一Run。
6. expected compaction为2 operations/10calls；hard为正式阶段5/25、replacement reconnect后7/35。execution index分别记录
   proactive/reactive与attempt count；不得再把reactive-per-run字段投影成per-chain2。
7. wall/publication/global stop及B1/B2/readiness不变量保持。

## Next gate

AgentCodex修订同一plan与plan-fix artifact；随后AgentDS/AgentMiMo再次独立re-review。通过前不得implementation、commit或真实provider。
