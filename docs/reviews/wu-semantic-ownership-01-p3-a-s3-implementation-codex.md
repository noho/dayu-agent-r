# WU-SEMANTIC-OWNERSHIP-01 P3-A S3 implementation

## Gate / scope

- Gate：implementation only。
- Slice：P3-A / S3，Host lifecycle closeout and lifecycle predicates。
- Status：completed。
- 未执行：code review、control doc 修改、commit、push、PR、下一 gate。
- 实施范围仅包含批准的 `engine_ingest.py`、`durable/state.py`、`command.py`、对应 Host tests、`dayu/host/README.md` 与本 artifact；未进入 P3-B final answer / outbox continuity。

## 动机与 owner-boundary decision

直接代码证据确认三个问题真实存在：

1. `EngineEventIngestor._close_worker_lifecycle` 原先构造 `EngineEvent(type=RUN_FAILED)`，把 Host worker EOF/crash 伪装成 Engine 输入事实。
2. late rejection 原先读取 `RunRow.terminal_event_id` / `AttemptRow.terminal_event_id` 判断 lifecycle 是否关闭，而 durable status 才是终态真值；nullable refs 只属于 row consistency。
3. `command.py` 原先直接组合 dispatch status 与三个 worker-accepted nullable refs，重建 durable dispatch 语义。

Owner boundary 裁决：

- Engine-origin terminal：首次事实仍由真实 `EngineEvent` 产生；Host 校验并通过 `EngineEventCandidate` 投影到 canonical terminal facts。
- worker EOF/crash：首次事实由 Host worker lifecycle signal 产生；Host ingest 使用 `_HostLifecycleCloseoutCandidate`，不构造 EngineEvent。
- terminal closed：`RunStatus` / `AttemptStatus` 与 `durable.state.is_terminal_*` 是判断真源；terminal refs 只由 durable row codec / schema 校验一致性。
- pre-worker direct cancel：`DispatchRecordRow` 及其组合规则由 `durable.state.is_dispatch_record_direct_cancelable` 拥有；command 只消费 predicate。

设计 stop condition 已核对：`docs/host/design.md` 明确带 accepted cancel facts 的 `CANCELLING` Run 由 active-cancel watchdog 收口为 `CANCELLED`，worker lifecycle / startup recovery 不先写 `RUN_LOST`，因此未触发 design truth blocker。

## Changed files

- `dayu/host/engine_ingest.py`
  - 新增强类型 `_HostLifecycleSource`、`_HostLifecycleCloseoutCandidate` 与已校验 context。
  - Engine-origin 与 Host-lifecycle-origin 分别执行 durable identity validation、duplicate detection、late rejection 与 closeout routing。
  - worker clean EOF / lost 使用 `event-host-lifecycle-<digest>`；identity material 包含固定 kind、session/run/attempt/execution、worker event index、event class/type、sub-index、lifecycle source 与 plan reason。
  - Host lifecycle terminal payload 使用独立 payload namespace、`host.worker_lifecycle` source 与 `host-lifecycle:...` 治理来源标签；canonical terminal payload不再写伪造 `engine_event_ref`。
  - `CANCELLING` 下 worker clean EOF / lost 只写 `HOST_LIFECYCLE_DIAGNOSTIC`，不写 FAILED / LOST terminal facts。
  - 真实 Engine `RUN_FAILED` 即使 error code 文本等于 `worker_lost_before_terminal`，仍保持 Engine-origin FAILED 语义，不被重解释为 Host LOST。
  - late rejection 改用 `is_terminal_run_status` / `is_terminal_attempt_status`；保留 `WAITING` + `SUSPENDED` 的 Engine waiting confirmation exception。
- `dayu/host/durable/state.py`
  - 新增 `is_dispatch_record_direct_cancelable(record: DispatchRecordRow) -> bool`，统一拥有 PENDING、WAITING_FOR_LANE、pre-worker DISPATCHING 判定。
- `dayu/host/command.py`
  - 删除本地 `_is_direct_cancelable_dispatch_record` 与 worker-accepted nullable refs 重建，改为消费 durable owner helper。
- `tests/host/test_engine_ingest_mapping.py`
  - 覆盖 Host lifecycle clean EOF/lost id namespace、source、payload ref、无伪造 Engine 语义、duplicate、真实 Engine failure 路由、status truth 与 active-cancel decision table。
- `tests/host/test_active_cancel_dispatch.py`
  - 覆盖 direct-cancel predicate 的 pending、waiting-for-lane、dispatching pre/post worker accepted 与 cancelled。
- `dayu/host/README.md`
  - 同步稳定开发边界：worker lifecycle 与 EngineEvent 是两条 typed path；active cancel 下 lifecycle signal 是 Host diagnostic，watchdog 保持 terminal owner。
- `docs/reviews/wu-semantic-ownership-01-p3-a-s3-implementation-codex.md`
  - 本 implementation artifact。

## Tests / validation

- 必跑矩阵：

```text
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_active_cancel_dispatch.py tests/host/test_recovery_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_run_attempt_transitions.py -q
161 passed in 1.88s
```

- 直接受影响 lifecycle / scheduler 补充验证：

```text
pytest tests/host/test_phase5_local_execution_integration.py tests/host/test_dispatch_scheduler.py -q
88 passed in 1.83s
```

- durable terminal row shape owner 补充验证：

```text
pytest tests/host/test_state_schema.py -q
47 passed in 0.50s
```

- 首轮变更测试：`test_engine_ingest_mapping.py` + `test_active_cancel_dispatch.py`，`97 passed in 1.47s`。
- pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- untracked artifact 另以 `git diff --no-index --check /dev/null <artifact>` 校验；无 whitespace error 输出（命令因存在预期新增 diff 返回 1）。

Source scans：

- synthetic Engine lifecycle：`rg "EngineEvent\\(|type=EngineEventType\\.RUN_FAILED|RunFailedData\\(" dayu/host/engine_ingest.py` 无匹配；模块只消费 `RunFailedData` 类型，不构造 synthetic EngineEvent。
- direct-cancel duplicate predicate：command 中仅剩 owner helper import / call；worker accepted nullable refs 的组合只位于 `durable.state.is_dispatch_record_direct_cancelable` 与 durable row / CAS owner 代码。
- terminal nullable-ref routing：两个 late rejection helper 只调用 `is_terminal_run_status` / `is_terminal_attempt_status`；不读取 terminal refs。其它 `terminal_event_id` 使用点属于 terminal transaction / reactive precondition，不参与 late routing。
- terminal event producer duplicate：`rg "_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)" dayu/host/durable/run_transition.py dayu/host/engine_ingest.py` 无匹配。

## README decision

- `dayu/host/README.md`：更新。其 Agent 约束允许记录当前已实现且稳定的 Host 架构边界；原文直接描述 EngineEvent ingest、worker lifecycle、cancel/watchdog，本次 typed source boundary 与 active-cancel routing 确实改变该稳定说明。
- `tests/README.md`：不更新。新增断言仍属于现有 `tests/host/` Engine ingest、durable state 与 cancel 状态机类别；没有新增测试层级、运行方式或维护规则。

## Propagation audit

### Run terminal event type

`RunStatus` / `HostRunEventType` owner helper -> Engine-origin 或 Host lifecycle closeout plan -> `terminal_closeout_in_transaction` -> EventLog concrete `RUN_SUCCEEDED/FAILED/CANCELLED/LOST` -> 同事务 `host_runs.status` -> read model / HostEvent / memory 等既有消费者。

S3 未复制 terminal event string mapping；producer source scan无重复常量。Host lifecycle path 与 Engine path都调用同一个 durable terminal transaction，因此 EventLog event type 与 Run row status 同事务同源。用户/LLM 可见消费者仍从 committed terminal fact / status 派生，不读取 lifecycle candidate、host lifecycle ref 或 synthetic Engine input。

### Attempt terminal event type

`AttemptStatus` / closeout-supported Attempt event helper -> typed closeout plan -> `terminal_closeout_in_transaction` -> EventLog concrete Attempt terminal fact -> 同事务 `host_attempts.status` -> recovery / cancel / diagnostic consumers。

worker EOF/crash 只改变 candidate identity/source，不新增 Attempt event mapping；required 与补充测试覆盖 FAILED / LOST / CANCELLED 及 transition 行为。

### Run / Attempt status predicate

durable row rules -> `TERMINAL_RUN_STATUSES` / `TERMINAL_ATTEMPT_STATUSES` -> `is_terminal_run_status` / `is_terminal_attempt_status` -> Engine / Host lifecycle late rejection。terminal refs 继续只由 row codec/schema验证；`test_state_schema.py` 证明 non-terminal + terminal refs 与 terminal + missing refs 均 fail closed，predicate 单测另外证明即使传入 status-terminal / refs-missing 的异常 typed context，late routing 仍由 status 判 terminal。

### Worker lifecycle closeout

worker clean EOF/crash -> `_HostLifecycleCloseoutCandidate` -> `event-host-lifecycle-` ids + `host.worker_lifecycle` source -> duplicate / late checks -> shared durable terminal transaction -> EventLog Attempt/Run terminal facts + status rows -> existing projection catch-up。

测试确认 Host lifecycle ids 与 `event-engine-` 不重合，terminal canonical payload没有 `engine_event_ref` / `engine_event_type`，descriptor 只保存明确 `host_lifecycle_ref`；真实 Engine `RUN_FAILED` 仍走 `event-engine-` 与 `engine:...:run_failed` ref。active cancel 下只写 Host diagnostic，watchdog / cancel transition 保持 terminal owner。

### Late event rejection

durable Run / Attempt status -> owner predicates -> Engine rejected diagnostic 或 Host lifecycle diagnostic；Engine waiting confirmation 的 `WAITING` / `SUSPENDED` exception 保持。nullable refs 不参与 routing。active-cancel table覆盖 Engine final answer、Engine run_failed、Host clean EOF、Host worker lost；四种输入都不写错误 success/failure/lost terminal fact。

### Direct cancelability

dispatch row -> `durable.state.is_dispatch_record_direct_cancelable` -> command pre-dispatch cancel branch -> existing transition transaction写 Attempt/Run CANCELLED facts。command source不再读取 worker accepted nullable refs。owner helper与 public cancel / recovery tests覆盖完整状态表。

### Diagnostic / projection / user / LLM consistency

- canonical lifecycle terminal：EventLog 与 Run / Attempt row由同一 transaction提交；projection只消费 committed facts。
- Host lifecycle diagnostic：`event_class=diagnostic`、`event_type=HOST_LIFECYCLE_DIAGNOSTIC`、source/ref 都明确为 Host lifecycle，不伪装财报事实、Engine terminal 或用户 cancel。
- user-visible terminal：继续由 concrete Host terminal event与 durable status投影；active-cancel lifecycle diagnostic不产生用户可见 failure/lost terminal。
- LLM-facing memory / prompt：本 slice没有新增 lifecycle material producer；Host lifecycle ref、event id、dispatch/status diagnostics不进入 LLM-facing material。

## Residual risks / uncovered areas

- `event-host-lifecycle-` 是有意的新 identity namespace；旧 synthetic Engine lifecycle ids 不做兼容读取或 alias。按项目 fresh-schema / no-compatibility 约束，该项属于本 slice 已裁决 non-goal，不是未分类 blocker。
- 未执行专门的多进程“Engine terminal 与 Host lifecycle terminal 同时提交”stress case；正确性仍由 EventLog unique identity、terminal CAS 与 first-committer-wins transaction保证。现有单进程 duplicate / late / scheduler integration 已覆盖主要路径；若需要更强跨进程 adversarial coverage，owner 是后续 production stress / EventLog hardening work，分类为 assigned to later work unit。
- 非 terminal EventLog 常量仍未统一 owner 化，按 approved plan 分类为 assigned to later P3-J / EventLog schema hardening。
- P3-B final answer / outbox continuity 未触碰，分类为 covered by later approved slice/work unit。

## Completion

- status: completed
- slice: S3
- blocking open question: none
- artifact path: `docs/reviews/wu-semantic-ownership-01-p3-a-s3-implementation-codex.md`
- next action: stop after implementation artifact；等待 controller 进入独立 code review gate。
