# WU-CTX-01 Slice 1 Reactive Plan Amendment Handoff

## 0. Gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- gate：`Slice 1 second plan amendment`
- lane：`AgentCodex plan/fix`
- Controller truth：
  `docs/reviews/wu-ctx-01-slice-1-reactive-stop-controller-adjudication.md`
- decision：`complete / ready for dual plan re-review`
- implementation status：`not accepted`
- blocking questions：`None`
- next entry point：只交回Controller进入AgentMiMo / AgentDS双路
  `plan re-review`

本gate只修改`docs/host/design.md`、
`docs/reviews/wu-ctx-01-plan-codex.md`并新增本artifact。没有继续编辑partial
production/tests、Controller control doc、resume/stop/review artifacts；没有运行代码
测试、pyright或coverage，也没有commit、push或创建PR。

## 1. First-principles judgment

第二个blocker成立，但原implementation stop提出的“扩充recovering failure transition”
不是正确修复。

reactive accepted compact后的conservative estimate只是diagnostic sizing，不是能否
recovery dispatch的事实真源。设计§25已经把真实provider overflow指定为reactive
闭环信号；若estimate hard就追加failure，会把heuristic提升为lifecycle truth，并使同一
operation同时拥有accepted `CONTEXT_COMPACTED`与failed
`CONTEXT_COMPACTION_FAILED`。真正root cause是stage contract遗漏：proactive accepted
compact与reactive accepted compact被错误合并到`POST_COMPACT`。

语义owner因此冻结为：

- `dayu.host.context_budget`拥有closed stage、threshold pressure与12-cell action；
- `dayu.host.engine_ingest`拥有reactive accepted compact后的catch-up与recovery start
  transaction orchestration；
- `dayu.host.run_input`拥有complete candidate、manifest与actual request strict load；
- existing `run_transition.py`只继续拥有recovery start，以及真实compact failed后的
  recovering failure；本WU不扩充其public/durable semantics。

这是第一次amendment上增加第四stage和reactive ordering，不改变两个独立产品修改，
也不改变3 slices。

## 2. Direct production evidence

| evidence | observed truth | plan consequence |
| --- | --- | --- |
| `engine_ingest.py::_execute_reactive_compaction` | accepted branch在独立事务提交`CONTEXT_COMPACTED`并返回`_ReactiveRecoveryAccepted` | accepted fact是合法既成真源；后续失败不能把它改写为compact failed |
| `engine_ingest.py::_complete_reactive_recovery` | memory catch-up exception仅告警，之后仍调用recovery start | exact candidate前置条件未成立时必须停止start，保留`RECOVERING`供重试 |
| `engine_ingest.py::_StartReactiveRecoveryOperation` | 当前直接分配identities并调用recovery transition，没有candidate/manifest | candidate payload与manifest必须前移到同一start transaction、transition之前 |
| `dispatch.py::_build_frozen_run_input` / `run_input.py::load_prepared_runner_call_candidate` | worker按Attempt/execution查manifest并加载digest-verified candidate | actual request同源能力已存在；禁止新wakeup DTO和第二套request builder |
| `run_transition.py::start_recovery_run_with_starting_attempt_in_transaction` | caller提供新Attempt/execution/dispatch identities，transition在`RECOVERING`前置条件下创建start facts/rows | caller先用同一identities写manifest，再调用existing transition；文件零diff |
| `run_transition.py::FailRecoveringRunInput` | 必填`context_compaction_failed_event_id`，`RUN_FAILED` payload也承诺该ref | 只允许真实compact/fallback failure消费；accepted hard estimate不能复用 |
| `run_transition.py::lose_recovering_run_in_transaction` | `RUN_LOST`属于startup orphan/lifecycle recovery | context sizing与reactive accepted branch永不使用 |

根因来自同一逻辑/数据源，不是测试fixture或偶然失败：当前worker strict loader要求
pre-start manifest，而reactive start transaction没有写manifest；当前recovering failure
owner要求真实failed fact，而accepted compact hard estimate没有该事实。

## 3. Frozen 4-stage / 12-cell contract

`ContextSizingStage` closed values固定为：

```text
ORDINARY
POST_COMPACT
REACTIVE_POST_COMPACT
DISPATCH_FALLBACK
```

第四stage只用于以下conjunction：

```text
reactive trigger
+ accepted CONTEXT_COMPACTED committed
+ Conversation Memory reached that event sequence
+ Run is RECOVERING
+ source Attempt is terminal
+ recovery Attempt does not yet exist
+ complete candidate is available
```

pressure仍且只能由prediction与ratio-derived thresholds派生。action total function固定为：

| stage | normal | soft | hard |
| --- | --- | --- | --- |
| `ORDINARY` | allow dispatch | one proactive compact operation | block + unstarted terminal fail |
| `POST_COMPACT` | allow dispatch | allow dispatch | block + unstarted terminal fail |
| `DISPATCH_FALLBACK` | allow dispatch | allow dispatch | block + failure-policy terminal closeout |
| `REACTIVE_POST_COMPACT` | allow recovery dispatch | allow recovery dispatch | allow recovery dispatch |

`REACTIVE_POST_COMPACT` soft/hard不得改写为normal。hard反例的唯一合法结果是：

```text
pressure=hard_threshold_exceeded
budget_decision=ALLOW_DISPATCH
recovery Attempt created and dispatched
zero CONTEXT_COMPACTION_FAILED
zero RUN_FAILED
zero RUN_LOST
```

若该真实recovery dispatch再次overflow，在
`max_reactive_compactions_per_run`剩余预算内进入下一条existing reactive operation。
超过上限后才产生真实`CONTEXT_COMPACTION_FAILED`并可选tier 4/5；
`DISPATCH_FALLBACK` hard再由existing
`fail_recovering_run_in_transaction`消费该真实failed fact。不得进入`LOST`。

## 4. Candidate、manifest 与 recovery transaction

accepted branch ordering固定为：

```text
transaction A:
  append CONTEXT_COMPACTED
  commit

outside transaction:
  catch Conversation Memory up to exact CONTEXT_COMPACTED.event_sequence
  if target not reached: do not start, do not wake, keep RECOVERING

transaction B:
  re-read Run=RECOVERING and terminal source Attempt
  strict-load source Attempt manifest/candidate
  reuse its frozen policy/tool schemas/disable-tools/tool-execution-mode
  freeze identity-free complete candidate
  conservative sizing(stage=REACTIVE_POST_COMPACT)
  allocate one StartRecoveryRunInput identity set
  write prepared candidate payload
  append RUNNER_CALL_INPUT_ASSEMBLED bound to same attempt/execution
  Slice 2 only:
    append CONTEXT_BUDGET_EVALUATED(stage=reactive_post_compact)
  call existing start_recovery_run_with_starting_attempt_in_transaction
  append RUN_STARTED(start_reason=recovery)
  append ATTEMPT_STARTED and insert dispatch row
  commit

after commit:
  wake PendingDispatchRecord
  worker loads manifest by exact attempt/execution
  worker loads and verifies the same candidate
  build AgentRunRequest from that candidate
```

不得把candidate塞入`PendingDispatchRecord`、不得在worker二次assembly、不得先start再补
manifest。manifest strict sizing snapshot新增/接受closed
`sizing_stage=reactive_post_compact`；compactor proposal仍为not-applicable。
`PreparedRunnerCallCandidate`必须把`tool_execution_mode`纳入strict projection与
input digest；engine ingest通过`run_input.py`的transaction-local strict loader读取
source Attempt candidate并复用其frozen policy/tool inputs，禁止从当前local config
重选或复制manifest parsing。

transaction B的rollback语义固定为：

- start transition `NOT_FOUND|INVALID_STATE`或返回不完整/identity不一致rows：
  owner-local private rollback signal；`run_write`外收敛为本调用不wake；
- low-level CAS lost、candidate/manifest digest或durable integrity错误：
  existing `HostDurableError`传播；
- 两类路径都使transaction B新增candidate payload descriptor、manifest、Slice 2
  budget fact、Run/Attempt/dispatch rows全部rollback；
- transaction A的accepted compact保持；没有并发winner时Run保持`RECOVERING`并由
  reconciliation重试同一accepted outcome；有winner时只信任winner committed state，
  不做post-commit猜测或重复wake；
- 不得补写`CONTEXT_COMPACTION_FAILED`、`RUN_FAILED`或`RUN_LOST`。

同一Engine candidate replay/reconciliation必须读取deterministic committed outcome：
matching accepted compact且Run仍`RECOVERING`、无recovery Attempt时，重入上述exact
catch-up与transaction B，不再次调用compactor或追加accepted fact；matching recovery
Attempt已由并发winner创建时只duplicate ack、不重复wake；matching真实failed outcome
只恢复existing fallback/failure分支。

## 5. Schema and consumer audit

| owner/consumer | required amendment | slice |
| --- | --- | --- |
| `context_budget.py` | closed fourth stage；constructor/helper共同验证12-cell | 1 |
| `_runner_call_manifest.py` / manifest producers | strict sizing snapshot接受四stage；reactive manifest-before-start；unknown拒绝 | 1 |
| `run_input.py` | recovery complete candidate复用existing assembly owner；actual request按manifest/candidate digest pairing | 1 |
| `engine_ingest.py` | accepted/failed分支选择正确stage；exact catch-up、transaction ordering、rollback、wake | 1 |
| `dispatch.py` | existing actual request loader继续为唯一consumer；不增加reactive重组 | 1 |
| `context_events.py` / lifecycle closed set / durable schema | `CONTEXT_BUDGET_EVALUATED.sizing_stage`接受`reactive_post_compact` | 2 |
| `read_api.py` / Host public activity | 接受第四stage fact并投影既定七字段；hard pressure保持hard | 2 |
| Service typed mapper | 接受由第四stage产生的合法Host activity；不按hard pressure重算block | 2 |
| Tool Trace / generic projection / recovery / outbox / terminal consumers | manifest-before-start只改变全局sequence；exact lifecycle refs与terminal filter不变 | 1/2 regression |
| `run_transition.py` | zero diff；accepted调用start owner，真实failed fallback才调用fail owner | stop condition |

public DTO不新增stage或action字段；“接受第四stage”表示strict canonical parser与Host
projector不得拒绝该合法fact，且投影的pressure仍为真实soft/hard。内部
`budget_decision`继续由canonical fact保存，不由Service/UI推导。

## 6. Slice amendments

固定3 slices与依赖顺序不变。

### Slice 1

- 新增第四stage与12-cell constructor/helper tests；
- reactive accepted compact exact catch-up；
- recovery complete candidate + manifest-before-start；
- actual request strict consume同一candidate；
- start precondition/CAS/integrity rollback；
- committed accepted outcome的duplicate/replay可重入start且不重复compact/fact/wake；
- reactive hard allow、零矛盾terminal facts、真实next overflow bounded loop；
- 真实compact failed tier 4/5 hard继续走existing failure owner；
- `run_transition.py`零diff。

Slice 1仍只使用完整conservative fallback，不实现canonical budget fact/public
projection，也不实现anchor selection。

### Slice 2

- canonical `CONTEXT_BUDGET_EVALUATED` schema/stable identity接受第四stage；
- reactive manifest -> fact -> recovery start ordering；
- public projection接受该fact，保留hard pressure与allow decision同源关系；
- Service只typed pass-through，不重算action；
- 与Slice 1保持独立：即使所有method都是conservative，fact/public contract也完整。

### Slice 3

- anchor算法、signed delta与compatibility resolver保持独立；
- accepted compact使旧anchor失效；
- immediate `REACTIVE_POST_COMPACT`必须使用完整conservative fallback；
- 即使fallback prediction为hard，stage action仍allow recovery dispatch；
- provider无usage继续fallback，不失败Run。

两个独立产品修改仍为adaptive sizing与durable/public fact；compact
coverage、第四stage和recovery ordering都是Slice 1 foundation修正，不构成第三项产品
修改。

## 7. Required tests

Slice 1/2 implementation re-entry后必须新增或更新：

- 12-cell action与`ContextSizingResult.__post_init__`反例；
- stage选择：proactive accepted=`POST_COMPACT`、reactive accepted=
  `REACTIVE_POST_COMPACT`、真实failed tier 4/5=`DISPATCH_FALLBACK`；
- reactive normal/soft/hard都start recovery，soft/hard pressure不改写；
- reactive hard零`CONTEXT_COMPACTION_FAILED`、`RUN_FAILED`、`RUN_LOST`；
- manifest在`RUN_STARTED`前存在，绑定新Attempt/execution，worker load结果与sizing
  candidate digest完全相等；
- source Attempt candidate的policy/tool schemas/disable-tools/tool-execution-mode
  被精确复用；当前local config漂移不改变recovery candidate；
- memory catch-up未达目标时零start/wake；
- recovery start precondition miss与low-level CAS lost分别验证transaction B零孤立
  payload/manifest/fact/Attempt/dispatch；
- accepted compact在上述失败后仍存在；catch-up/no-winner fixture中Run仍
  `RECOVERING`且reconciliation可重试，并发winner fixture只接受winner committed
  state；
- replay matching accepted outcome重入catch-up/start但不再次调用compactor、不追加
  accepted fact；winner已start时只duplicate ack且不重复wake；
- real next overflow在剩余上限内创建下一reactive operation；
- 超限产生真实failed fact，tier 4/5 hard由existing fail transition收口；
- canonical fact/parser/Host projector/Service mapper接受第四stage，并投影hard
  pressure，不把它重算为block；
- `git diff --exit-code -- dayu/host/durable/run_transition.py`。

## 8. Stop conditions

恢复Slice 1后命中任一项必须立即停并交回Controller：

- 需要修改`dayu/host/durable/run_transition.py`或通用transaction runner；
- 无法在recovery Attempt start前冻结exact candidate与manifest；
- actual request无法通过existing strict loader消费同一candidate；
- catch-up失败仍必须start才能前进；
- reactive accepted hard必须写compact-failed/run-failed/run-lost才能收口；
- next real overflow无法复用existing bounded reactive loop；
- schema/public consumer必须新增兼容branch或下游重算才能接受第四stage；
- 任何当前slice allowlist外production修改。

`run_transition.py`非零diff是独立stop condition，不以测试通过抵消。

## 9. Static validation and scope proof

本gate只执行Markdown/scope/diff静态验证，不执行pytest、pyright、coverage或代码smoke。

### 9.1 Begin snapshot

开始时`git diff --numstat`：

```text
374	0	dayu/host/_runner_call_manifest.py
26	0	dayu/host/compact_payload.py
5	0	dayu/host/compaction_operation.py
642	37	dayu/host/context_budget.py
85	55	dayu/host/context_fallback.py
696	282	dayu/host/dispatch.py
2	1	dayu/host/durable/schema.py
678	99	dayu/host/engine_ingest.py
33	0	dayu/host/memory.py
3931	1603	dayu/host/run_input.py
3	3	docs/host/issues-implementation-control.md
111	0	tests/host/test_context_budget.py
48	0	tests/host/test_context_compact_events.py
244	59	tests/host/test_dispatch_scheduler.py
4	3	tests/host/test_durable_schema.py
104	26	tests/host/test_engine_ingest_mapping.py
158	1	tests/host/test_memory_projection.py
31	1	tests/host/test_runner_call_hot_payload_contract.py
4	4	tests/host/test_tool_trace_projection.py
16	1	tests/host/test_tool_trace_queries.py
```

开始时`docs/reviews/wu-ctx-01-slice-1-implementation-resume-codex.md`与
`docs/reviews/wu-ctx-01-slice-1-reactive-stop-controller-adjudication.md`为untracked；
本gate把它们视为既有只读artifact。`run_transition.py`开始时零diff。

### 9.2 End snapshot

结束时`git diff --numstat`：

```text
374	0	dayu/host/_runner_call_manifest.py
26	0	dayu/host/compact_payload.py
5	0	dayu/host/compaction_operation.py
642	37	dayu/host/context_budget.py
85	55	dayu/host/context_fallback.py
696	282	dayu/host/dispatch.py
2	1	dayu/host/durable/schema.py
678	99	dayu/host/engine_ingest.py
33	0	dayu/host/memory.py
3931	1603	dayu/host/run_input.py
17	8	docs/host/design.md
3	3	docs/host/issues-implementation-control.md
295	80	docs/reviews/wu-ctx-01-plan-codex.md
111	0	tests/host/test_context_budget.py
48	0	tests/host/test_context_compact_events.py
244	59	tests/host/test_dispatch_scheduler.py
4	3	tests/host/test_durable_schema.py
104	26	tests/host/test_engine_ingest_mapping.py
158	1	tests/host/test_memory_projection.py
31	1	tests/host/test_runner_call_hot_payload_contract.py
4	4	tests/host/test_tool_trace_projection.py
16	1	tests/host/test_tool_trace_queries.py
```

本untracked artifact的独立numstat为：

```text
382	0	docs/reviews/wu-ctx-01-slice-1-reactive-plan-amendment-codex.md
```

begin/end逐行对比证明所有partial production、tests与
`docs/host/issues-implementation-control.md`的numstat完全相同；只有本gate允许的
design、plan在结束snapshot新增diff，本artifact为新增文件。
`docs/reviews/wu-ctx-01-slice-1-implementation-resume-codex.md`与
`docs/reviews/wu-ctx-01-slice-1-reactive-stop-controller-adjudication.md`开始/结束均为
untracked，行数分别保持`256`与`145`，未被编辑。

### 9.3 Static audit result

- `git diff --check`：pass。
- `git diff --exit-code -- dayu/host/durable/run_transition.py`：pass，零diff。
- stale contract grep：旧九格矩阵、缺第四stage及旧三stage候选集合陈述在三份交付
  Markdown中零命中。
- implementation slice heading仅命中Slice 1/2/3各一次。
- Markdown fence计数均为偶数：design=`182`、plan=`56`、amendment=`14`。
- fourth-stage contract grep命中design/plan/amendment中的enum、12-cell、manifest、
  canonical fact/public consumer、reactive hard反例、next-overflow bounded loop与
  `run_transition.py`零diff stop condition。
- 未运行pytest、pyright、coverage、代码smoke、commit、push或PR。

## 10. Residual risks

| risk | classification / owner |
| --- | --- |
| 当前partial implementation尚缺第四stage与reactive candidate/manifest | resumed Slice 1 after dual plan re-review |
| catch-up failure后的reconciliation入口需按existing ingest replay证明 | Slice 1 owner tests；不得用terminal compensation |
| manifest stage字段与全部producer/consumer fixture切换范围较大 | Slice 1 strict schema/consumer audit |
| public projector可能把hard pressure误解释为block | Slice 2 fact/public projection tests |
| full focused suite、full pyright、coverage、README audit尚未完成 | resumed Slice 1 completion |

没有未分类residual risk，没有需要新增产品决策的blocking question。

## 11. Controller handoff

- amendment artifact：本文件
- plan artifact：`docs/reviews/wu-ctx-01-plan-codex.md`
- design truth：`docs/host/design.md` §25
- current decision：`ready for dual plan re-review`
- next：Controller派发AgentMiMo / AgentDS双路plan re-review
- forbidden next：直接恢复implementation、code review、commit、push或PR
