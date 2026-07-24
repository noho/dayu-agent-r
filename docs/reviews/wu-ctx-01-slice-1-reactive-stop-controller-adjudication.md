# WU-CTX-01 Slice 1 Reactive Recovery Stop Controller Adjudication

## 0. Gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- gate：`implementation / Slice 1 second stop`
- Controller：AgentController
- implementation evidence：
  `docs/reviews/wu-ctx-01-slice-1-implementation-resume-codex.md`
- decision：`accepted blocker / reopen plan`
- partial implementation status：`not accepted`
- blocking questions：`None`
- next entry point：AgentCodex只修订 reactive sizing stage/action 的design/plan，随后双路
  plan re-review

## 1. First-principles judgment

AgentCodex正确命中 stop condition，但其提出的“扩充
`dayu/host/durable/run_transition.py`，新增不依赖
`CONTEXT_COMPACTION_FAILED` 的 `RECOVERING -> FAILED` transition”不是最佳修复路径。

直接设计真源已经规定：

- reactive path 不把 compact 后估算值当作能否重新 dispatch 的真源；
- quality accepted compact 后应通过真实 recovery dispatch / 再次 Engine overflow闭环；
- `CONTEXT_COMPACTION_FAILED` 只能表示真实 compact/fallback failure；
- `RECOVERING -> FAILED` 的现有 typed transition正确绑定真实
  `CONTEXT_COMPACTION_FAILED`；
- `LOST` 只属于 orphan / lifecycle recovery，不得冒充 context hard。

因此 reactive accepted compact 的 conservative estimate 即使达到 hard，也不能新建一条
“估算 hard 导致 recovery failure”的 lifecycle truth。这样做会把保守 heuristic提升为
reactive dispatch真源，并与既有 design §25 reactive contract冲突。

真正 root cause 是第一次 plan amendment 的 stage/action matrix 只区分
`ordinary / post_compact / dispatch_fallback`，错误地把 proactive post-compact 与
reactive accepted post-compact 合并为同一 stage。二者 pressure 派生相同，但 action
owner不同：

- proactive post-compact仍受 hard fail-closed治理；
- reactive accepted post-compact必须让真实recovery dispatch决定是否仍 overflow。

这是 plan/design contract 漏项，不是 durable transition owner缺失。

## 2. Controller-frozen semantic correction

### 2.1 Sizing stages

`ContextSizingStage` 增加第四个closed value：

```text
REACTIVE_POST_COMPACT
```

它只表示 reactive Engine overflow operation 已提交 accepted
`CONTEXT_COMPACTED`、memory projection 已按该 boundary追平、准备创建 recovery Attempt
的 complete candidate。它不用于 proactive compact、compact failed fallback、ordinary
call、continuation或compactor proposal。

### 2.2 Pressure/action total function

pressure仍只由prediction与thresholds派生，不因stage改写。action扩为12-cell：

| stage | normal | soft | hard |
| --- | --- | --- | --- |
| `ORDINARY` | allow dispatch | one proactive compact operation | block + unstarted terminal fail |
| `POST_COMPACT` | allow dispatch | allow dispatch | block + unstarted terminal fail |
| `DISPATCH_FALLBACK` | allow dispatch | allow dispatch | block + failure-policy terminal closeout |
| `REACTIVE_POST_COMPACT` | allow recovery dispatch | allow recovery dispatch | allow recovery dispatch |

`REACTIVE_POST_COMPACT` 的soft/hard pressure必须如实保留；allow不是把pressure改写为
normal。若真实recovery dispatch再次overflow，仍进入既有
`max_reactive_compactions_per_run`有界状态机；不得启动proactive operation，也不得把本次
估算作为calibration sample。

### 2.3 Durable/lifecycle owner

- 不修改 `dayu/host/durable/run_transition.py`。
- accepted compact recovery继续复用
  `start_recovery_run_with_starting_attempt_in_transaction`，但在创建Attempt前必须先从
  complete exact candidate产生`REACTIVE_POST_COMPACT` sizing result与manifest，并让actual
  recovery request消费同一frozen candidate。
- reactive compact真实失败且dispatch fallback仍为hard时，现有
  `fail_recovering_run_in_transaction`继续消费真实
  `CONTEXT_COMPACTION_FAILED`，语义保持合法。
- accepted compact之后不得追加矛盾`CONTEXT_COMPACTION_FAILED`，不得新增context-hard
  recovering failure transition，不得使用`RUN_LOST`。

### 2.4 Slice boundary

- Slice 1：建立第四stage、complete candidate/manifest与recovery start/actual request同源；
  仍只使用conservative fallback。
- Slice 2：独立的`CONTEXT_BUDGET_EVALUATED` fact/public projection也必须接受
  `REACTIVE_POST_COMPACT`，并记录真实soft/hard pressure + allow decision。
- Slice 3：usage anchor算法保持独立；accepted compact仍使旧anchor失效，
  `REACTIVE_POST_COMPACT`立即使用完整conservative fallback。provider无usage仍不失败。

两项产品修改独立性和3 slices均不改变。

## 3. Required plan/test amendment

AgentCodex必须只修订：

- `docs/host/design.md`
- `docs/reviews/wu-ctx-01-plan-codex.md`
- 新 amendment artifact

必须同步：

- 3-stage / 9-cell文字全部改为4-stage / 12-cell；
- `ContextSizingStage` schema/manifest/canonical fact/public consumer audit；
- Engine ingest reactive candidate freeze、manifest-before-recovery-start、actual request
  digest pairing与CAS rollback；
- accepted compact与failed fallback两个reactive分支的stage选择；
- 12-cell constructor/action tests；
- reactive hard仍start recovery、保留hard pressure、零
  `CONTEXT_COMPACTION_FAILED`/`RUN_FAILED`/`RUN_LOST`反例；
- real overflow可在既有上限内开始下一条reactive operation；
- recovery Attempt在start前已有exact manifest，worker不再因缺manifest fail closed；
- `run_transition.py`继续零diff。

partial production/tests在plan amendment与双路re-review通过前不得继续修改。

## 4. Rejected alternatives

| alternative | disposition | reason |
| --- | --- | --- |
| 新增generic `RECOVERING -> FAILED` context-hard transition | `rejected` | 把conservative estimate提升为reactive dispatch真源，违反existing reactive design；还会扩大durable public contract |
| accepted compact id塞入`context_compaction_failed_event_id` | `rejected` | 字段语义造假 |
| accepted后追加`CONTEXT_COMPACTION_FAILED` | `rejected` | 同一operation产生矛盾terminal facts |
| Engine ingest直接写terminal row/event | `rejected` | 绕过lifecycle owner |
| 用`RUN_LOST`收口 | `rejected` | orphan/lifecycle语义漂移 |
| reactive path不构造exact candidate/manifest/sizing | `rejected` | 违反complete candidate与direct pairing目标；只允许action不由heuristic阻断 |

## 5. Residual risks

| risk | classification / owner |
| --- | --- |
| 现有partial implementation仍按3-stage helper，尚未完成reactive freeze/manifest | resumed Slice 1 after accepted amendment |
| Engine ingest recovery start CAS rollback与零孤立manifest尚未验证 | Slice 1 owner tests |
| reactive hard allow可能被错误投影为normal | Slice 1/2 12-cell与public fact tests |
| full focused suite、full pyright、coverage、README audit尚未完成 | resumed Slice 1 completion |

没有未分类 residual risk，没有需要用户新增产品决策的blocking question。
