# WU-CTX-01 Plan Review Fix（AgentCodex）

## Gate metadata

- Work Unit：`WU-CTX-01 Usage-Anchored Adaptive Context Sizing`
- gate：`plan review fix`
- status：`complete`
- created_at：`2026-07-23 21:31:35 CST`
- plan：
  `docs/reviews/wu-ctx-01-plan-codex.md`
- finding裁决唯一真源：
  `docs/reviews/wu-ctx-01-plan-review-controller-adjudication.md`
- evidence inputs：
  - `docs/reviews/plan-review-20260723-211859.md`
  - `docs/reviews/plan-review-20260723-212146.md`
  - `docs/host/design.md` §25
  - `docs/host/issues-implementation-control.md`
  - 相关production/tests代码
- allowed writes核对：只原地修订plan并新建本artifact；未修改production、tests、
  README、control doc或其它artifact；未commit、push、建PR、merge、进入re-review或
  implementation。

## Fix summary

原plan保持两个独立修改与3个implementation slices：

1. Slice 1冻结complete candidate、estimator/manifest v2、allow后identity allocation /
   consumption、continuation frozen source与consumer ordering；
2. Slice 2在完全没有usage anchor时，独立交付conservative-only
   `CONTEXT_BUDGET_EVALUATED`、同事务ordering/idempotency与Host→Service typed
   projection；
3. Slice 3只接入provider-neutral successful ordinary anchor resolver和signed-delta
   算法。

未新增candidate table、provider adapter、completion state machine、兼容shim或UI。
`dayu/host/durable/run_transition.py`明确不修改；现有caller-owned
`StartGovernedRunInput`是同一identity被transition实际消费的直接接口。

## Finding final status

本节每个finding的“最终状态”只使用
`已修复/未修复/部分修复/证据失效`。

### DS-01

- 最终状态：`已修复`
- plan位置：§1.3、§5.1、§5.3、§8.2、§15。
- 修复：sizing只消费identity-free complete candidate且不依赖manifest；仅allow后在
  同一write transaction构造一次`StartGovernedRunInput`，manifest与start transition
  消费同一Attempt/execution identity。soft/hard candidate不写runner-call manifest，
  不分配durable Attempt/execution/dispatch identity。
- 直接证据：`dispatch.py::_run_pre_start_governance`当前先sizing后start；
  `run_transition.py::StartGovernedRunInput`由caller提供全部identity，现有transition
  原样写入Run/Attempt/dispatch rows。Controller接受DS-01并禁止candidate table/shim。

### CTRL-PR-001

- 最终状态：`已修复`
- plan位置：§2、§5.3、§7.1、§8.2、§14。
- 修复：明确不修改`dayu/host/durable/run_transition.py`；冻结
  `_new_governed_start_input(...) -> StartGovernedRunInput`与
  tagged `DispatchStartPlan` +
  `_commit_dispatch_candidate_in_transaction(...) -> PendingDispatchRecord` exact
  private call path，并把`tests/host/test_run_attempt_transitions.py`与dispatch owner
  tests列入allowed tests。
- 直接证据：现有`StartGovernedRunInput`已显式包含
  `attempt_id/execution_id/dispatch_record_id`及两个start event ids；
  `start_governed_run_with_starting_attempt_in_transaction`直接消费这些值，不在owner内
  重新生成identity。因此最小owner-boundary方案不需要修改durable transition。

### DS-02

- 最终状态：`已修复`
- plan位置：§5.6、§8.2、§8.3、§9.1、§14。
- 修复：选择唯一private exception rollback方案。precondition
  `NOT_FOUND|INVALID_STATE`在manifest/fact append后抛
  `_StartCandidateCasMissRollback`，`run_write` rollback，外层caller转为无dispatch；
  低层`CAS_LOST`沿现有`HostDurableError` rollback并传播。正常`UPDATED`才commit。
- 直接证据：`HostTransactionRunner.run_write`正常返回commit、异常rollback；
  current dispatch helper把非UPDATED普通返回`None`会commit；durable transition的
  `_require_run_mutation_updated`已把append后低层CAS failure转为
  `HostDurableError`。plan测试要求新transaction确认projection payload、manifest、
  fact、start facts、Attempt/dispatch rows全部零残留。

### DS-03

- 最终状态：`已修复`
- plan位置：§5.4、§6、§8.4、§9.1、§14。
- 修复：successful ordinary runner-call必须同时具备strict complete v2 manifest、
  exact accepted link、唯一合法paired usage与同identity/iteration的durable accepted
  `ITERATION_COMPLETED` preview，且finish reason为
  `stop|length|tool_calls`。Run/Attempt terminal不补completion；tool loop逐iteration
  判断，usage-before-failure、crash gap与terminal-without-completion均为barrier。
- 直接证据：`HostPreviewEventType.ITERATION_COMPLETED`与
  `engine_ingest._preview_payload`已durable保存attempt/execution、iteration与finish
  reason；它不是canonical completion truth。此方案复用existing durable evidence，
  不新增completion event/table/state machine。

### DS-04

- 最终状态：`已修复`
- plan位置：§5.1、§8.2、§9.1、§14。
- 修复：明确只保持estimator公式/常量和无usage conservative fallback语义，不承诺
  与旧`material_view.budget_fragments` subset逐值相等。新增complete-input范围扩大、
  strict-subset不低估、每个atom恰计一次及soft/hard threshold crossing验收。
- 直接证据：当前`dispatch.py::_run_pre_start_governance`只估算
  `material_view.budget_fragments`；complete candidate将覆盖system/scene、完整
  normalized messages、structured atoms、memory/compact/fallback与selected tool
  schemas。估算值安全增大是修复目标，不是兼容回归。

### DS-05

- 最终状态：`已修复`
- plan位置：§4、§5.4、§6.3、§8.4、§14。
- 修复：冻结
  `resolve_context_anchor(transaction: HostTransaction, event_log_store:
  EventLogStore, query: ContextAnchorQuery) -> ContextAnchorResolution`。全部keyset
  pages、compact boundary与anchor evidence在调用方同一个transaction snapshot读取；
  禁止内部开transaction、跨transaction分页、mutable singleton/cache或Service/UI
  durable访问。
- 直接证据：现有Host durable readers均接收显式`HostTransaction`，EventLog读取通过
  `EventLogStore` primitive；Controller已驳回跨transaction并发反例并要求consistent
  snapshot。

### DS-06

- 最终状态：`已修复`
- plan位置：§5.6、§8.3、§9.1、§14。
- 修复：Slice 2断言限定为“policy存在但usage缺失”时产生conservative fact/activity；
  policy缺失时不调用sizing、不产生fact/activity，保持既有
  allow-without-budget/no-budget governance path。
- 直接证据：当前`dispatch.py::_run_pre_start_governance`在policy为`None`时直接start，
  无threshold/window可形成合法sizing result；Controller明确要求保留该路径。

### DS-07

- 最终状态：`证据失效`
- plan位置：§5.7、§14。
- rejected-with-reason：Controller裁决原plan已要求Service对kind、estimate method、
  pressure做exhaustive closed-enum mapping并对未知值fail closed；固定私有helper名称
  不是public contract，也不需要implementation agent重新设计。未采纳额外命名要求。
- 直接证据：原plan及修订plan §5.7均冻结typed enums、逐字段复制和fail-closed
  invariant。

### DS-08

- 最终状态：`证据失效`
- plan位置：§5.2、§14。
- rejected-with-reason：`supports_stream_usage`改变是否发送
  `stream_options.include_usage`，属于request serialization semantics；digest变化只会
  保守失效并fallback，不等于按capability猜usage presence。未移出compatibility
  digest。
- 直接证据：`engine/runners/openai/payload.py`只用该flag改变request shape；
  pairing仍只看实际合法`USAGE_REPORTED` presence，符合design §25与Controller裁决。

### MIMO-001

- 最终状态：`已修复`
- plan位置：§2、§7.1、§7.3、§7.4、§8.2、§9.1、§14。
- 修复：完整列出所有直接production consumers/producers：
  `_runner_call_manifest.py`、`run_input.py`、`engine_ingest.py`、
  `compaction_operation.py`、`proactive_compaction.py`、`tool_trace.py`、
  `durable/tool_trace.py`、`lifecycle_events.py`、`durable/schema.py`，并审计
  `read_api` public stream及generic projection/recovery/terminal consumers。必要
  production/tests已扩入allowed scope。
- 直接证据：repository `rg`直接名称命中上述production文件；direct tests命中
  `test_run_input_builder.py`、`test_engine_ingest_mapping.py`、
  `test_dispatch_scheduler.py`、`test_lifecycle_events.py`、
  `test_tool_trace_projection.py`、`test_tool_trace_queries.py`。plan另补public watch、
  projection、recovery、transition与outbox ordering tests。

### MIMO-002

- 最终状态：`证据失效`
- plan位置：§5.4、§14。
- rejected-with-reason：PR #182已建立strict-native per-Session execution owner；
  resolver又被固定为单个Host transaction snapshot内完成全部scan。另一个scheduler在
  scan中提交同Session compact只在跨transaction分页时成立，而该实现已被明确禁止。
- 直接证据：Controller adjudication对MIMO-002的驳回理由；修订plan exact interface与
  stop condition禁止跨transaction scan。

### MIMO-003

- 最终状态：`已修复`
- plan位置：§5.3、§8.2、§8.4、§9.1、§14。
- 修复：continuation current projection唯一来自accepted
  `IterationStartedData.input_projection` descriptor；selected tool schema唯一来自
  同attempt首个complete pre-start manifest的descriptor；context policy与request
  semantics唯一来自该manifest strict sizing snapshot。四类来源任一crash缺失，按
  closed reason写`unavailable`并执行complete conservative fallback，禁止当前config
  重选。
- 直接证据：current `engine_ingest._limited_runner_call_manifest_body`会在projection
  可用时保存observed input，但`tool_schema_snapshot_refs=[]`，因此原plan确有source
  缺口；修订plan把首个complete manifest确定为唯一durable source。

### MIMO-004

- 最终状态：`证据失效`
- plan位置：§5.3、§14。
- rejected-with-reason：manifest`sizing_snapshot`只冻结conservative
  estimate/contract，不保存当前resolver后选的anchored/fallback method；
  `input_snapshot_digest`与manifest digest用途已分别定义。method变化不会要求重写
  manifest或改变manifest digest。
- 直接证据：plan §5.3 schema没有`estimate_method`字段；method只属于
  `ContextSizingResult`与`CONTEXT_BUDGET_EVALUATED`。

## Blocking questions

None。所有Controller accepted findings均已收敛，没有accepted finding处于
`未修复`或`部分修复`。

## Residual risks

- manifest v2与pre-start candidate refactor改动半径仍较大；由Slice 1 exact owner
  tests、§7.4 consumer audit及stop conditions承接。
- complete-input conservative estimate可能高于旧subset，并因此更早跨soft/hard
  threshold；这是安全性目标，必须用范围扩大/不低估/threshold crossing测试解释。
- schema v2只支持全新数据库；旧workspace不兼容是项目既有政策。
- live provider差异仍为non-blocking risk；owner是provider-neutral
  usage-present/usage-absent contract tests。

上述均已分类，无blocking residual risk。

## Validation

- `git diff --check -- docs/reviews/wu-ctx-01-plan-codex.md
  docs/reviews/wu-ctx-01-plan-fix-codex.md`：通过，无输出。
- 两文件当前均为未跟踪artifact；另分别执行
  `git diff --no-index --check /dev/null <file>`，只返回“存在内容差异”的expected
  exit code 1且无whitespace error输出。
- `git status --short --untracked-files=all`范围核对通过：fix前已有
  `docs/host/issues-implementation-control.md` modified，以及两路review、goal、
  adjudication和原plan untracked；fix后只额外出现
  `docs/reviews/wu-ctx-01-plan-fix-codex.md`，未出现production/tests/README/control
  doc/其它artifact的新写入。
- 不运行代码测试或pyright：本gate只修改Markdown，且用户required validation明确要求
  不运行代码测试/pyright。implementation plan仍保留每slice focused tests、coverage、
  full pyright、README audit与stop conditions。

## Completion

- status：`complete`
- accepted findings：`DS-01`、`CTRL-PR-001`、`DS-02`、`DS-03`、`DS-04`、
  `DS-05`、`DS-06`、`MIMO-001`、`MIMO-003`全部`已修复`
- rejected-with-reason：`DS-07`、`DS-08`、`MIMO-002`、`MIMO-004`保持Controller
  驳回；final status均为`证据失效`
- slice count：`3`，未改变
- independent modifications：usage-anchored algorithm；conservative-only也成立的
  canonical fact + Host→Service typed projection
- blocking questions：`None`
- next entry point：仅交还Controller；本Agent不进入re-review或implementation
