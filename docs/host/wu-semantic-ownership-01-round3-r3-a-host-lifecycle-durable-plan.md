# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A Host 生命周期与 Durable 真源实施计划

## Gate、状态与范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-A`
- 当前角色：AgentCodex，职责为 `plan / implement / fix`
- 当前 gate：plan fix after MiMo/DS plan review；本 artifact 完成后停止，等待双路 plan re-review，不进入 implementation
- 风险级别：`production-high`
- 语义边界：Host lifecycle / admission / dispatch / wait / durable state owner，以及被 Host 使用的层中立 runtime cleanup owner
- 计划状态：`ready-for-plan-rereview`
- 计划切片数：8
- 禁止动作：不 commit、不 push、不创建 PR、不 merge，不进入 R3-B / R3-C / R3-D / R3-E

本计划只处理 controller 已接受的 R3-A finding。R3-F 已完成的 CLI、Config、Packaging、Public Documentation 与 finite-number contract 保持为当前验证基线；除了 DR-007 要求把 `session list/purge` 接到新的 Host admin opener 外，不重复修改 R3-F 的 CLI 参数、输出格式、配置 overlay、依赖或根 README 契约。

## 输入真源与优先级

实施与裁决按以下顺序解释；代码的当前直接证据用于确认问题是否仍存在，但不得覆盖已经明确的设计边界：

1. `AGENTS.md`
2. `docs/host/design.md`
3. `docs/engine/design.md`
4. `docs/host/issues-implementation-control.md`
5. `docs/phaseflow-umbrella-optimization-control.md`
6. `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md`
7. canonical ledger：`docs/reviews/repo-review-20260712-093647.md`
8. additional evidence：
   - `docs/reviews/repo-review-20260712-085921.md`
   - `docs/reviews/repo-review-20260712-085930.md`
   - `docs/reviews/repo-review-20260712-090033.md`
   - `docs/reviews/repo-review-20260712-091126.md`

`docs/phaseflow-umbrella-optimization-control.md` 把 durable state machine / lifecycle 修改列为 High Risk，并建议 production work unit 使用少量、可独立验证的切片。本文不按 finding 或文件机械拆分，而按语义 owner、故障注入方式和 review 专长拆分。

## R3-F 后基线

- 当前分支为 `phaseflow/host-issues-control`。本 plan-fix 开始时，目标计划和三份 plan-review 输入为本 gate 已知未跟踪 artifact；不得据此宣称 workspace clean，也不得改动它们之外的既有文件。
- `docs/host/issues-implementation-control.md` 已记录 R3-F final closeout：默认 pytest `3930 passed, 3 skipped, 5 deselected`，全量 pyright 为 0 error；R3-F 只把 runner-call stress 明确留给 R3-A。
- 当前重新运行：

  ```bash
  source .venv/bin/activate
  pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
  ```

  结果为 `4 passed, 1 failed`。失败仍是 `test_sustained_watch_slow_consumer_reconnect_stress`，第 12 个合法输入在 provider accept 前因 `RUNNER_CALL_INPUT_ASSEMBLED` canonical payload 超过 inline limit 失败，只接受了 11/12。该证据直接确认 DR-006 未被 R3-F 改变。
- R3-F 已强化 runtime 数值 finite validation，但没有改变 `InterruptibleProcessHandle.start/close` 或 `LaneController.close` 的 lifecycle commit 顺序；DR-017、DR-029 仍存在。
- 本轮不得改 `dayu/config/`、package constraints、根 CLI parser、interactive ticker、upload argv contract 或根 README 中已完成的 R3-F 内容。

## 第一性原理复核

### Controller accepted findings

| Finding | 当前直接代码证据 | 当前裁决 | 唯一语义 owner |
| --- | --- | --- | --- |
| DR-006 | `dayu/host/run_input.py::_runner_call_manifest_hot_payload()`、`dayu/host/engine_ingest.py::_runner_call_manifest_hot_payload()` 和 `dayu/host/compaction_operation.py` 都把逐消息 `projector_metadata_summary` 再复制进 hot EventLog payload；metadata id 含 message index，消息越多 payload 线性增长。完整 stress 当前仍以 11/12 复现。 | `accepted`，未收窄。固定上界 hot atoms 与完整 descriptor 必须由一个 shared runner-call hot contract 产生；Tool Trace 从 descriptor 按需解析。 | `dayu.host` runner-call manifest/hot projection owner；EventLog 只持固定 atoms。 |
| DR-007 | `dayu/cli/commands/session.py::_run_session_command_async()` 对 list/purge 先调用 `_prepare_session_runtime()`，再 `open_host()`；Service 准备会做 scene、tool discovery 和 runner secret 解析，`open_host.__aenter__()` 会启动 scheduler、watchdog、recovery 和 poller。 | `accepted`，未收窄。不能用 fake runner、dummy secret 或 CLI 直读 SQLite；必须有 typed admin opener。 | Host public opener contract；Service 只做 storage/admin assembly；CLI 只选 opener。 |
| DR-008 | `DefaultHostResolveWaitService._resolve_in_transaction()` 在 `WaitBoundaryDecisionKind.EXPIRED` 时只 `_reject_late_result()`；`WaitPoller._release_expired_or_invalid_boundary()` 只 release/backoff，wait 与 Run 仍为 `WAITING`。 | `accepted`。deadline 是 Host 已确认的期限失败，终态定为 `WaitRecordStatus.FAILED + RunStatus.FAILED`，不是 `LOST`。 | Host wait state machine 与同事务 terminal transition。 |
| DR-009 | `HostDispatchScheduler._drain_loop()` 在 durable retry exhausted 时把自身 `_closed=True`；`_PublicHostHandle._closed` 不变。`wake_queue_promotion()` 对 closed scheduler 静默 return，public admission 仍可 commit。 | `accepted`。durable retry exhaustion 按 transient 重试；真正 fatal 通过共享 health/admission gate fail-close。 | Host execution health gate，统一约束 public execution admission 与 scheduler fatal transition。 |
| DR-010 | `sqlite_payload_object()` 只比 caller digest 与 descriptor digest，SQL 只取 `payload_json`，不核对 row digest/size 或实际 bytes；`effective_execution_snapshot_from_json()` 忽略 `policy_snapshot_digest`，也不重算 `policy_snapshot_ref`。 | `accepted`，未收窄。所有 JSON payload consumer 使用同一 durable integrity resolver；execution config 自身重算。 | `dayu.host.durable` payload integrity owner；effective execution projection owner。 |
| DR-011 | `_PublicHostHandle` 的 async 方法直接调用同步 command/read facade；`HostTransactionRunner` 使用同步 SQLite 和 `time.sleep` busy retry。外部连接持写锁时会冻结调用方 event loop。 | `accepted`。public async Host/Admin durable 调用进入单线程、connection-owned actor；禁止把同一 connection 零散 `to_thread`。 | Host public async composition boundary。 |
| DR-012 | `WaitPollerSupervisor.close()` 允许 `close_drain_timeout_seconds=None` 的无界 `join()`；有 timeout 时第一次 join 超时后仍第二次无界 `join()`。 | `accepted`，风险证据收窄：当前 `_OpenHostWaitPollerFactory` 已让 poller round 在线程内创建并关闭私有 durable handle，因此 detach 不再持有 execution command handle；但 Host close 无界等待仍真实存在。 | Host wait observation budget、poller supervisor state 与 `open_host` shutdown order。 |
| DR-017 | `InterruptibleProcessHandle.start()` 在 `Process.start()` 前写 `_started=True`，当前该字段同时承担 start-attempt 并发 gate 与成功状态；`close()` 在 kill/join/process/queue cleanup 前写 `_closed=True`，任一后续步骤失败或 caller cancellation 都会让第二次 close 永久短路，尤其会跳过 queue feeder cleanup。 | `accepted-narrowed`。保留 start/close 的并发 gate；同一 handle 的 `Process.start()` 异常一律不可重试，必须进入可重复 close 的 cleanup 路径。partial cleanup 与 caller cancellation 不能毒化后续 close；不强制五状态重写。 | `dayu.runtime.interruptible_process` lifecycle / resource cleanup owner。 |
| DR-025 | `LLMContextCompactor.run_prepared_compactor_proposal()` timeout 后向 request token 调 `request_cancel()`；reactive path 传入真实 `_HostCancellationToken`，下一 proposal attempt 立即观察到父 Run 已取消。 | `accepted`，未收窄。每个 proposal attempt 使用 linked child token，timeout 只写 child。 | Host compaction operation 的 attempt cancellation scope。 |
| DR-029 | `LaneController.close()` 会先逐个尝试 release；即使某个 release 失败且 failed token 仍留在 `_held_tokens`，仍在抛首错前写 `_close_completed=True`，导致第二次 close 直接返回。问题是 release-failure-after-attempted-release，不是 release-before-attempt。 | `accepted-narrowed`。保留 `_closed=True` 对新 acquire / 并发 close 的保护；成功 token 移除、失败 token 保留，只有 heartbeat 已停止且 held token 为空才 commit completed，后续 close 只重试剩余 token。 | `dayu.runtime.lane.LaneController` close completion owner。 |

### MiMo / DS R3-A confirmations

| Confirmation | 当前直接代码证据 | 本计划处理 |
| --- | --- | --- |
| dispatch retry exhaustion self-closes scheduler | `_drain_loop()` 捕获 `HostTransactionRetryExhaustedError` 后 close pending queue、设置 `_closed`、cancel workers。 | S3：改为按 scheduler poll interval 退避并重试，durable pending record 保持真源；不把 retry exhaustion 当 fatal。 |
| watchdog wakeup drop | `_active_cancel_watchdog_queue = asyncio.Queue(maxsize=1)`；`QueueFull` 被静默 `pass`。 | S5：使用 level-triggered `asyncio.Event`；tick 前 clear，tick 期间的新 wake 不会丢。 |
| proactive compaction TOCTOU | proactive 已使用 `_DurableRunCancellationToken`，比 review 时的“完全无 token”更强；但 `_prepare_compactor_proposal()` 记录 manifest 后直接调用 provider，二者之间没有第二次 cancellation check。 | `accepted-narrowed`，S7：manifest commit 后、provider call 前再次检查同一个 attempt token；不跨 LLM 调用持事务。 |
| recovery single huge transaction | `StartupRecoveryScanner.scan()` 在一个 `run_write()` 中遍历 `read_non_terminal_runs(transaction)` 的全部结果。 | S4：固定 watermark + keyset page，每批独立 write transaction。 |
| cancel_run deferred race | `cancel_run()` 写事务抛 `INVALID_STATE` 后调用 `_is_deferred_cancel_state()` 再开 read transaction；并发状态可变。 | S5：把同一状态快照下的 unsupported 分类放入 `_CancelRunOperation`，删除 post-write read。 |
| compact_material wrong ref fallback | `_accepted_tool_evidence_delta_blocks()` 在 request ref 缺失时把 `TOOL_RESULT_ACCEPTED row.event_id` 填进 `tool_call_event_ref`。 | S1：provenance fail-closed；绝不伪造 `TOOL_CALL_REQUESTED` ref。 |
| Fins wait adapter reverse dependency | `dayu/fins/ingestion/wait_adapter.py` 当前仍直接 import `dayu.host.api`、`dayu.host.durable.state`、`dayu.host.wait_adapter`。 | controller 已裁决为 R3-D/R3-A boundary split。本轮S6完成Host-owned bounded adapter contract，不改`dayu/fins/`；删除该反向依赖的Fins/Service搬迁半边明确保留给R3-D，不把它伪装成R3-A已修复。 |

除最后一项 controller 已明确的跨 sub-WU split 外，上述 accepted finding 当前都由直接代码或当前 stress 证明仍存在；没有 finding 因 R3-F 而失效。

## 语义所有权与禁止的补救方式

| 业务事实 / 状态 | 唯一 owner | 合法消费者 | 禁止实现 |
| --- | --- | --- | --- |
| runner-call hot payload shape 与上界 | shared Host runner-call hot contract | ordinary、continuation、compactor producer；EventLog；Tool Trace | 三个 producer 各自复制 summary；在 EventLog append 失败后截断/fallback。 |
| descriptor ref/digest/size/content 一致性 | shared durable JSON payload resolver | terminal、outbox、evidence、Tool Trace、recovery、RunInput | 每个 consumer 只比部分字段；篡改时返回空值或旧字段。 |
| effective execution config digest/ref | `_execution_config_projection` | admission、dispatch、replay | dispatch 下游忽略 digest，或用默认 runner/policy 补救。 |
| execution Host 与 admin Host 的能力集合 | `dayu.host.api` opener/handle contract | Service composition、CLI caller | admin 命令打开 full Host；dummy worker/secret；CLI 直读数据库。 |
| async durable connection/thread ownership | Host durable actor | public `Host`、`HostAdmin` | 对同一 connection 零散 `asyncio.to_thread`；async facade 直接跑 sync SQLite。 |
| scheduler health 与 new-work admission | Host execution health gate | public execution admission、scheduler critical tasks | public handle 与 scheduler 各持无关 bool；admission 前无锁 check；closed wake 静默丢弃。 |
| wait deadline terminal outcome | wait state machine | direct resolve、callback、poller、queue promotion | poller release/backoff；callback 层单点 terminal fallback。 |
| wait adapter call/close budget | wait poller supervisor | sync provider adapter | timeout 后继续无界 join；关闭主 store 后让线程继续持其 authority。 |
| proposal timeout cancellation | compaction attempt child token | LLM compactor、Engine cancellation observer | 向 parent Run token写 timeout；下一 attempt 复用已 timeout token。 |
| process/lane close completion | 各自 runtime lifecycle / resource cleanup owner | Host worker/lane shutdown | 把并发 gate 当 completion；partial cleanup/release 后永久短路；在 Host 调用点补清理。 |

## 已冻结的实现契约

### 1. Runner-call hot atoms 与 durable descriptor integrity

1. 新建私有 `dayu/host/_runner_call_manifest.py`，定义 typed `RunnerCallHotAtoms` 与唯一 `runner_call_hot_payload()`。`run_input.py`、`engine_ingest.py`、`compaction_operation.py` 三个 producer 只提供 typed atoms，不再各自实现 hot JSON builder。
2. hot payload 只允许固定上界字段：session/run/attempt/execution identity、runner-call index/kind/trigger、可选 iteration identity、manifest ref/digest/schema、validation status、message count、role/input digest、可选 projection descriptor ref/digest/size，以及固定 shape diagnostic。`projector_metadata_summary` 与任何逐消息数组都不得进入 EventLog hot payload。
3. 完整逐消息 `messages` 与 `projector_metadata` 只存在 manifest descriptor。descriptor 中每个 `ProjectorMetadata` 固定包含：`projector_metadata_id: str`、`projector_id: closed enum`、`projector_schema_version: str`、`projector_digest: sha256 digest`、`purpose: closed enum`、`source_contract_refs: tuple[HostInternalRef, ...]`。`run_input.py` 与 `engine_ingest.py` 从现有 typed projector metadata 直接填充这六项；`compaction_operation.py` 必须把旧 `metadata_id` 归一为 `projector_metadata_id`，并从 compactor manifest/projector contract 显式填充 `projector_schema_version` 与 `source_contract_refs`，不得用默认版本或缺字段 fallback。Tool Trace query 只可从已校验 descriptor 投影五字段业务摘要（id、projector、schema version、digest、purpose）；不得从 hot payload 或 raw string 反推，完整 `source_contract_refs` 仍留在 descriptor。
4. 新建 `dayu/host/durable/payload_resolution.py` 作为 JSON descriptor 完整性 owner。SQLite JSON 必须同时满足：requested ref = descriptor ref、caller expected digest = descriptor digest、row digest = descriptor digest、row size = descriptor size、canonical bytes 实际 digest/size 相等、row format 为 `canonical_json`、解析后仍为 object；同时拒绝 descriptor 指向不存在或错误 payload id。Artifact 路径复用 `read_artifact_bytes()` 的 containment/digest/size 校验，并验证 UTF-8 与 canonical JSON digest。
5. `dayu/host/payload_resolution.py` 与 `dayu/host/durable/tool_trace.py` 都委托该 owner；删除各自只读取 `payload_json` 的不完整 SQLite resolver。不存在旧数据 compatibility branch。
6. `effective_execution_snapshot_from_json()` 必须重算 `sha256(config)`，同时校验 `policy_snapshot_digest` 与 `policy_snapshot_ref == "policy:" + digest` 后才反序列化 runner/policy。
7. accepted evidence envelope 声称存在但 `tool_call_requested_event_ref` 缺失、目标不存在或 event type/identity 不匹配时，compact material 构造抛 `HostDurableError`；不再用 result event id 代替 call event id。
8. S1 任何代码编辑前执行只读 schema feasibility pre-check：核对 `dayu/host/durable/schema.py` 的 `host_sqlite_payloads` 同时含 `payload_format/payload_json/payload_size_bytes/payload_digest`，`payload_descriptors` 同时含 `payload_ref/payload_kind/payload_digest/payload_size_bytes/sqlite_payload_id`，并核对 resolver 可在同一 transaction join/read 两行。当前代码直接证据已证明这些列存在，因此本计划裁决 S1 不需要 DDL/user_version 变更；实施前重跑若发现任一列或 join identity 缺失，必须在零代码修改状态停止并回到 plan review，禁止顺手 migration 或降级校验。

### 2. Admin opener 与 public durable actor / async boundary

1. 在 `dayu.host.api` 新增 `OpenHostAdminOptions`、`HostAdmin` 与 `open_host_admin(options)`。`OpenHostAdminOptions` 只含 durable DB、artifact、directory-create、SQLite retry 与 payload threshold 字段；不含 lane、worker、runner、tool、scene、compactor 或 wait poller。admin opener 只启动 durable actor，不注册 host instance、不 recovery、不 scheduler、不 lane、不 poller。
2. `Host` 与 `HostAdmin` 是两个独立 Protocol，不继承、不互相扩展，也不保留 compatibility wrapper。execution `Host` 保留 execution、单对象 read、outbox、cancel 与 watch 能力并移除 list/purge/storage-admin；`HostAdmin` 只暴露 `get_session`、`list_sessions`、`purge_session`、`report_storage_usage`、`run_storage_maintenance`、`close`。二者可以复用 owner 内部的 module-level command/read function，但不能通过 Protocol 继承泄漏 admin capability。
3. 新建私有 `_HostDurableActor` 与私有 method-generic `_HostDurableInvoker` Protocol。调用签名固定为 `invoke(operation: Callable[[HostCommandHandle], T]) -> Awaitable[T]`、`close() -> Awaitable[None]`，其中 `T` 为具体返回类型；禁止 `Any`、`object`、无类型 lambda 或 command bag。public handle 只提交 module-level callable 或 `functools.partial`。
4. actor 的唯一 `ThreadPoolExecutor(max_workers=1)` worker thread 负责创建、使用和关闭一个私有 `HostCommandHandle` 及其 `HostDurableStore/sqlite3.Connection`；handle/connection 永不离开该线程。初始化 future 成功后才允许 invoke；初始化失败关闭已创建资源并让 opener 失败。所有 invoke 按 executor 提交顺序串行。
5. execution opener 明确拥有两套 connection：opener event-loop thread 通过 `open_host_durable_store()` 创建 scheduler/projection/recovery 使用的 scheduler-owned store；actor worker thread用同一 typed durable options 另建 actor-owned command store。scheduler 只接收 scheduler-owned `transaction_runner`，actor 只接收 actor-owned `HostCommandHandle`，二者都由既有 opener 配置启用 WAL、foreign keys、busy timeout 和同一 finite retry policy，但不共享 connection/transaction runner。admin opener只有 actor-owned store。
6. actor after-commit scheduler wake 使用 `_ThreadsafeSchedulerWakeupPort`：非 opener thread 通过 `loop.call_soon_threadsafe()` 投递只操作 scheduler 的同步 callback，并等待 typed `concurrent.futures.Future` 的成功/异常；同步等待发生在 actor thread，用于让一次 public command 的完成语义包含 wake，不阻塞 event loop。active worker cancel 使用独立 `_ThreadsafeActiveWorkerCancelPort`，把 registry cancel、cancellation token 写入与 `LocalWorkerHandle.on_cancel()` 全部投递回 opener loop；actor thread 不直接操作 asyncio Queue/Event/Task 或 worker hook。
7. `invoke()` 通过 `run_in_executor()` 返回 awaitable；取消 awaiter不能取消已提交的同步 command。普通 read/admin caller cancellation 可立即传播但 actor 仍按序收口；S3 new-work admission caller cancellation 必须在同一 admission lease 内 shield 并等待 actor transaction及 after-commit wake 完成，再重新抛 `CancelledError`，防止 commit 后提前释放 lease。actor connection 的 `time.sleep()` busy retry只占 actor worker；event loop ticker必须继续。retry exhausted 作为 typed command error返回，不在 actor层无限重试，也不改 scheduler health。
8. `Host` 的所有 async command/read 与 watch 的每轮 durable polling都经 actor；watch loop 的 sleep/iteration仍在 opener loop。startup recovery 在 actor-owned command path 上执行并返回 immutable recovery actions/pending wakes；S4 负责其分页语义。不得用散落 `asyncio.to_thread()` 搬运同一 handle/connection。
9. execution close order固定为：public gate进入 CLOSING并拒绝新 invoke；bounded close wait poller；等待已进入 actor的 command及其 bridge wake收口；关闭 scheduler/active workers；用 scheduler-owned store 完成 projection flush；在 actor worker关闭 command handle；确认 worker future结束后关闭 executor；最后关闭 scheduler-owned store。admin close 只执行 gate、drain、actor-thread handle close、executor shutdown。任一步失败仍尽力执行后续 owner cleanup，首错传播；不得在 scheduler 已关闭后仍允许 actor bridge wake。
10. `dayu/service/host_admin.py` 只解析 runtime locations、typed config 与 host-runtime durable storage 字段；不得调用 ScenePrepare、tool discovery、model selection、runner secret resolution。`session list/purge` 使用它与 `open_host_admin()`；resume 按 label 查找时先用短生命周期 admin handle解析唯一 session id，再打开 execution Host，直接 session id 不需要 list。CLI 参数、stdout/stderr、exit code 与 list/purge 行为保持不变。

### 3. Scheduler health、admission lease、retry 与 idempotent replay

1. 新增 `HostApiErrorCode.UNAVAILABLE`、typed `HostUnavailableDetail(component, reason_code)` 与 `HostExecutionHealthGate`。错误固定 `retryable=True` 且不泄漏原始异常消息；gate 状态为 `STARTING -> READY -> UNAVAILABLE -> CLOSING -> CLOSED`，只有 actor、startup recovery、scheduler critical tasks 都成功后进入 READY。
2. new-work admission（internal start、submit queue/steer、retry、replay）必须在 opener event loop 持有同一个 async admission lease，覆盖 READY check、actor transaction、commit 后 thread-safe scheduler wake 及 actor future收口。fatal transition也取得同一 lease；只有两种合法排序：admission先持 lease则 commit+wake 完成后 fatal，fatal先持 lease则 new-work不进入 actor。read/cancel/close不被 UNAVAILABLE 阻断，但仍受 public close gate约束。
3. heartbeat、drain、promotion 与其它 scheduler critical task 的非预期退出通过统一 supervisor 调 `report_fatal(component, reason_code)`；closed scheduler 的 dispatch/promotion/watchdog wake 抛 typed internal unavailable，禁止静默 return。critical task异常到 typed fatal 的映射另有 unit test；fatal/admission竞态测试直接调用同一 `report_fatal()` owner方法注入，避免依赖偶然 task timing。
4. `HostTransactionRetryExhaustedError` 是 transient：drain record保持 durable pending，按 `dispatch_poll_interval_seconds` 退避后重新 reconciliation，不关闭 scheduler、不 cancel active workers、不进入 UNAVAILABLE。只有 invariant/non-retryable critical exit进入 UNAVAILABLE。
5. idempotent admission replay 在 actor transaction内从 existing Run/Attempt/dispatch真源重新派生 wake decision：pending dispatch重投递、pre-start governance重唤醒；不得因 `idempotent_replay=True` 跳过全部 wake。

### 4. Startup recovery keyset batching

1. recovery 使用 `(accepted_event_sequence, run_id)` keyset cursor，启动时在短 read transaction 固定 upper watermark和单个 `policy.now`；默认 batch size 使用 module-level typed常量64，不使用 offset或一次性全量 reader。
2. 每批在 actor-owned command handle上运行一个独立 write transaction，CAS分类/transition后 commit并返回 immutable recovery actions；opener loop只在该批commit后执行对应 wake，再推进cursor。新接受且超过watermark的Run留给下一次scan/scheduler，不进入本轮。
3. 第N批失败不回滚已提交批次；重跑从 durable truth重新建立watermark/cursor，依赖现有CAS/idempotency得到与单批扫描相同的terminal/dispatch/wake集合，不缓存内存offset。全部批次和pending wake成功后health gate才可READY；startup invariant失败必须让open失败或进入UNAVAILABLE，不能带着半健康handle对外。

### 5. Active-cancel watchdog 与 deferred cancel classification

1. active-cancel watchdog wake从 `asyncio.Queue(maxsize=1)` 改为level-triggered `asyncio.Event`。loop在每次tick前clear；tick执行期间到来的wake保持set并触发下一轮，periodic scan只作恢复保障，不能成为低延迟正确性的唯一来源。
2. deferred cancel分类进入 `_CancelRunOperation` 的同一 write transaction，基于同一Run/Attempt/dispatch snapshot返回typed classification；删除 `_is_deferred_cancel_state()` 及post-write read。支持状态集合不在本轮扩张。
3. actor thread仅调用S2的active-cancel bridge；watchdog event和worker hook始终由opener loop操作。watchdog critical task异常仍走S3 health gate，但本slice只改变cancel owner内部wake/classification，不重新设计health state machine。

### 6. Wait expiry、adapter budget 与 shutdown

1. 新增 Host-internal `ExpireWaitInput(wait_id, observed_at, actor, source)` 与 typed `ExpireWaitResult(transition, queue_promotion_session_id, idempotent_replay)`。`_expire_wait_in_transaction(transaction, input)` 必须接收调用方已打开的 `HostTransaction`，不创建嵌套transaction、不调用public `resolve_wait()`；它在同一snapshot重读Wait/Run/Attempt并以CAS first-committer-wins。
2. helper从module-level reason/message常量构造现有 `ResolveWaitFailedOutcome(result=ToolResultFailure(ok=False, error="wait_deadline_expired", message=<业务可读期限说明>, hint=None, meta=None), payload_ref=None)`，复用 `_wait_resolution_payload_plan()`、稳定event-id plan与 `WaitingRunTerminalInput`，再调用 `fail_run_from_waiting_in_transaction()`。expiry幂等key/digest只从wait id、durable deadline与固定reason派生，不从poll/callback来源或迟到outcome派生。
3. helper成功时在调用方同一write transaction完成 `TOOL_RESULT_ACCEPTED` failure fact、`RUN_FAILED`、Wait `FAILED`、suspended Attempt保持terminal、session active-slot release；返回promotion session id。wait已由result/cancel/其它terminal抢先提交时返回typed no-op/replay，不改写事实。direct/callback的observed_at已过deadline时先调用helper，再在同一transaction写 `WAIT_LATE_RESULT_REJECTED`；commit后的projection catch-up和promotion wake必须在向caller抛late error前完成。
4. poller对EXPIRED调用同一helper，不再release/backoff；INVALID time boundary仍fail-closed为durable error/backoff，不能猜terminal语义。FAILED、LOST、Host Run-cancel与expiry只要实际释放active slot，都经同一promotion wake owner；`ResolveWaitCancelledOutcome`仍按工具结果恢复Run，不因类型名误判slot release。
5. `WaitPollerRuntimePolicy` 新增finite-positive `adapter_call_timeout_seconds`（默认常量30秒）、finite-positive `close_drain_timeout_seconds`（默认5秒且不允许`None`）与positive `max_outstanding_adapter_calls`。测试可把三者缩小，但production默认均用module-level常量。
6. sync `poll_wait()`/`abandon_wait()` 由Host-owned bounded observation runner执行。每次调用创建只持adapter、immutable `WaitRecordRow` snapshot、observation token与`Queue(maxsize=1)`的daemon thread；thread不持store、transaction、command handle、resolver或scheduler port。registry用lock追踪所有live token/thread，live数量达到policy cap时不再spawn并返回typed capacity diagnostic/backoff。
7. observation token有 `ACTIVE -> INVALIDATED -> FINISHED` gate。正常返回/精确普通异常只能通过registry `publish(token, typed_result)`；publish在同一lock下同时验证token仍ACTIVE且supervisor generation未关闭，再`put_nowait`。timeout或supervisor close先INVALIDATE，再把wait收口；迟到publish只返回dropped并由thread finally标FINISHED/移除引用，绝不调用resolver或访问任何durable authority。poll timeout以 `wait_observation_timeout` 把Wait/Run收为LOST；cancelled abandon timeout写 `wait_abandon_timeout` close marker与diagnostic后停止重试，但不宣称外部job已取消。
8. supervisor close设置global close generation并INVALIDATE全部live token，只使用一个shared monotonic deadline：先bounded join poller loop，再对registry snapshot做best-effort bounded joins；不得把预算乘以thread数。只要poller loop或任一tracked observation thread仍live，status保持CLOSING且thread refs保留，close返回；最后一个thread finally移除后才转STOPPED。后续close可再次使用新的一次bounded budget，任何一次都不得无界join或虚假STOPPED。
9. open_host可在supervisor返回CLOSING后继续按S2顺序关闭scheduler/actor/store，因为所有live observation token已失效且thread没有Host authority。provider协作式cancel和Fins adapter搬迁仍属于controller指定R3-D半边；本轮不编辑`dayu/fins/`。

### 7. Compaction cancellation scope

1. 每个 proposal attempt 创建新的 `_CompactionAttemptCancellationToken(parent)`。读取消时先看parent；`request_cancel(compactor_proposal_timeout)`只写child-local state。
2. LLM compactor timeout仍尝试中止当前Engine call，但不得改变parent Run token。repair/retry使用下一个全新child；父token未取消时可继续。
3. parent在任意时刻取消时，所有child立即观察parent reason/requested_at；operation以cancellation_requested收口，不能被child timeout reason覆盖。
4. `_prepare_compactor_proposal()` 在manifest recorder返回后、`run_prepared_compactor_proposal()`前检查本attempt token。proactive durable token因此会重新读取Run/session/input cursor；失效时provider call count必须为0。
5. 不在LLM/provider await期间持SQLite transaction，不改Engine read-only `CancellationToken` contract，不把Host writable token加入`dayu.contracts`。

### 8. Layer-neutral runtime partial cleanup completion

1. 不强制把 `InterruptibleProcessHandle` 重写为 `NEW/STARTING/RUNNING/CLOSING/CLOSED` 五状态。保留start-attempt与close-started并发gate，但将“已开始close”和“全部resource cleanup完成”分开表达；只有后者允许幂等return。
2. `Process.start()`成功后记录start-completed；任何`start()`异常都保留start-attempt gate，同一handle一律不可再次start，也不依赖`pid is None`/`is_alive() is False`猜测“从未启动”。调用方若要重试必须先close该handle并创建新实例；close对pre-spawn与可能post-spawn两类失败都执行documented API可支持的best-effort process cleanup，queue cleanup必须进入finally路径。
3. close使用一个private async lock和单个被`asyncio.shield()`等待的cleanup task来保留并发保护；caller cancellation只取消caller wait，cleanup task继续。每个process/queue步骤只在成功后记录completed；task失败时第二次close基于步骤记录补齐未完成步骤，不重复已完成的破坏性操作。queue close/feeder cleanup即使kill/join/process.close失败也必须尝试；所有等待使用finite budget或明确cancel-join diagnostic，不做无界`join_thread()`。
4. `LaneController.close()` 保留 `_closed=True` 作为拒绝新acquire和唤醒waiter的gate，并用single-flight close task/lock避免并发release。首次非空close reason保持真源；heartbeat停止只做一次。逐token尝试release，成功token从`_held_tokens`删除、失败token保留；release error后`_close_completed`保持false并抛首个typed `RuntimeLaneError`，第二次close只重试remaining token。
5. lane只有在heartbeat已停止、close task无未处理error且`_held_tokens`为空时才写`_close_completed=True`。caller cancellation不覆盖cleanup结果；并发close共享同一次attempt结果。不得捕获`BaseException`，不得在Host调用点补做runtime cleanup，也不得让`dayu.runtime` import Host/Engine/Service/UI/Fins。

## Slice 数量与合并裁决

本计划使用 8 个 implementation slices，超过 control doc 的“超过 5 必须举证”阈值。额外 gate 成本是有意承担的：旧单一 S2 同时包含全新 connection-owned actor、public Protocol 拆分、health state machine、fatal/admission race、startup recovery cursor、watchdog level trigger 与 cancel transaction classification；这些 concern 具有不同 semantic owner、故障注入、回滚半径和 reviewer 专项知识。一次实现/审查无法稳定承载，且 actor、health、recovery、cancel 任一竞态失败都会掩盖其它 owner。新增 3 个 gate 相比旧 5-slice 方案会增加 implementation artifact、双路 review、controller 裁决、验证复跑和 accepted commit 成本，但该固定成本低于在一个 production-high 并发 slice 中定位跨线程/事务/恢复/取消组合故障的风险。

8 个 slice 都是行为闭环而不是按文件或 finding 机械拆分：

1. S1 关闭 durable bytes/provenance/size owner，验证 schema pre-check、tamper matrix、4KiB上界与Tool Trace reconstruction。
2. S2 关闭 admin opener capability与public async durable connection/thread owner；交付独立Protocol、actor connection ownership、bridge和close order，现有scheduler行为可继续工作，不留下只有类型没有路径的半成品。
3. S3 在S2稳定actor/bridge之上关闭execution health与new-work admission原子边界；fatal race、retry exhaustion与idempotent replay使用同一health/wake oracle。
4. S4 只关闭startup recovery keyset/watermark/transaction owner；cursor稳定性与batch replay failure matrix不与health竞态混审。
5. S5 只关闭active-cancel watchdog wake与cancel snapshot classification；二者共享cancel governance owner和同一command/dispatch validation matrix，但不包含recovery cursor。
6. S6 关闭wait terminal与bounded observation/shutdown owner；核心是result/cancel/expiry first-commit及stuck adapter lifecycle。
7. S7 关闭compaction attempt cancellation scope；它与wait虽都有timeout，但token可写面、terminal oracle和provider-call barrier不同。
8. S8 关闭层中立runtime partial cleanup completion；process与lane共享single-flight cleanup/retry review，但各自用独立测试文件定位，且不得引入Host反向依赖。

禁止合并关系：S2不能与S3合并，因为connection/thread ownership错误与health state machine错误需要独立回滚；S3不能与S4合并，因为fatal lease correctness不依赖recovery cursor；S4不能与S5合并，因为recovery batching和cancel classification正是review已确认的不同owner/failure matrix；S6不能与S7合并；S8不能塞入任一Host slice。S1也不能与S2合并，否则runner payload stress的失败定位会被opener并发改动淹没。S8内部process/lane保留同slice，是因为二者都只修改`dayu.runtime` cleanup completion，不共享业务状态，拆开只会增加gate而不降低当前review风险。

依赖顺序固定为：

```text
S1 durable/provenance
  -> S2 admin opener/public durable actor
  -> S3 scheduler health/admission/retry/replay
  -> S4 startup recovery batching
  -> S5 active-cancel watchdog/classification
  -> S6 wait terminal/bounded observation/shutdown
  -> S7 compaction attempt cancellation
  -> S8 runtime partial cleanup
  -> integrated production-high validation
```

每个slice完成focused validation与adversarial per-slice review后才进入下一slice；不得积累8个slice后一次性调试。S2交付actor/bridge后S3才能把lease覆盖到actor+wake，S3交付health gate后S4才能以“全部recovery批次成功才READY”为handoff，S2/S3交付active cancel bridge与critical-task supervisor后S5才能只修改cancel owner。

## Slice S1：Durable Integrity 与 Bounded Runner-call Provenance

### 目标与 finding

- 修复 DR-006、DR-010。
- 修复 compact material wrong `tool_call_event_ref` confirmation。
- 让当前唯一失败的 production stress 恢复通过，并建立 12/300 message owner-level regression。

### Non-goals

- 不改 scheduler lifecycle、Host opener、wait、Engine provider 或 context budget policy。
- 不提高 EventLog inline limit，不在 append error 后截断，不保留旧 hot payload兼容读取。
- 不改变 LLM-facing prompt 内容；只改变 durable provenance 存放与解析位置。

### Allowed production files/modules

- 新增 `dayu/host/_runner_call_manifest.py`
- 新增 `dayu/host/durable/payload_resolution.py`
- `dayu/host/run_input.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/compaction_operation.py`（仅 runner-call manifest/hot producer 部分）
- `dayu/host/tool_trace.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/durable/payload.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/_execution_config_projection.py`
- `dayu/host/compact_material.py`
- `dayu/host/__init__.py`（仅新 shared contract 确需 package export 时；默认不 export 私有 owner）

任何 schema table/version 变更不在 allowed list。当前只读证据已确认现有两张payload表具备完整ref/digest/size/content join所需列；若实施前pre-check观察到代码漂移，必须在任何S1代码编辑前停止并回到plan review，不能顺手migration。

### 实施前 schema feasibility pre-check

在S1 implementation agent取得文件所有权后、第一次`apply_patch`前，必须执行并在implementation artifact记录：

```bash
rg -n 'host_sqlite_payloads|payload_format|payload_json|payload_size_bytes|payload_digest' dayu/host/durable/schema.py
rg -n 'payload_descriptors|payload_ref|payload_kind|payload_size_bytes|payload_digest|sqlite_payload_id' dayu/host/durable/schema.py
rg -n 'SELECT payload_json|TABLE_SQLITE_PAYLOADS|read_payload_descriptor' dayu/host/payload_resolution.py dayu/host/durable/tool_trace.py
```

预期直接证据：`host_sqlite_payloads` row保存format/json/row size/row digest；`payload_descriptors` row保存ref/kind/descriptor size/descriptor digest/sqlite payload id；resolver能按descriptor id读取同一SQLite row。前两项缺任一列或无法在同一transaction核对identity时，stop status必须是`blocked-return-to-plan-review-before-code-edit`；当前plan不授权DDL、user_version、migration或部分校验fallback。

### Allowed tests/docs

- `tests/host/test_payload_store.py`
- `tests/host/test_effective_execution_config.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_compact_material.py`
- `tests/host/test_terminal_payload.py`
- `tests/host/test_outbox_projection.py`
- `tests/host/test_host_production_stress.py`
- 可新增 `tests/host/test_runner_call_hot_payload_contract.py`
- 可新增 `tests/host/test_durable_payload_integrity.py`
- `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`

### 必须测试的反例

1. ordinary、continuation、compactor 三个 producer 对 0/1/12/300 messages 产生同一 hot schema；hot payload size 不随 message count 线性增长，并小于 4096 bytes；hot payload不存在`projector_metadata_summary`。
2. 三个producer的full manifest都产出相同六字段`ProjectorMetadata` descriptor shape；compactor输入证明旧`metadata_id`被归一为`projector_metadata_id`且显式带`projector_schema_version/source_contract_refs`。300-message manifest可由ref/digest解析；Tool Trace query恢复每个五字段summary view，EventLog/Tool Trace hot row不复制数组。
3. 分别篡改 SQLite `payload_json`、row digest、row size、descriptor digest/size/ref、artifact bytes，terminal/outbox/evidence/Tool Trace consumer 全部 fail closed。
4. effective config 分别篡改 config、digest、ref，dispatch snapshot parser 全部抛 `HostDurableError`。
5. accepted evidence 缺 request ref、ref 指向 result event、identity mismatch 都 fail closed；正确 request ref 保持。
6. 当前 full production stress 5 项全部通过，accepted count 为 12。

### 验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_payload_store.py tests/host/test_effective_execution_config.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_compact_material.py tests/host/test_terminal_payload.py tests/host/test_outbox_projection.py tests/host/test_runner_call_hot_payload_contract.py tests/host/test_durable_payload_integrity.py -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
python -m pyright dayu/host/ tests/host/
rg -n 'projector_metadata_summary' dayu/host/run_input.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/tool_trace.py
rg -n 'projector_metadata_id|projector_schema_version|source_contract_refs' dayu/host/_runner_call_manifest.py dayu/host/run_input.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/tool_trace.py
rg -n 'tool_call_event_ref = row\.event_id' dayu/host/compact_material.py
git diff --check
```

source scan 期望：三个producer不再构造hot `projector_metadata_summary`；若`tool_trace.py`保留summary命名，只能命中descriptor query projection，不得命中hot-row写入。六字段descriptor owner与三个producer均有typed字段命中；compact fallback scan无结果。若full manifest的合法`projector_metadata`被误删，测试必须失败。

### Review focus

- canonical bytes、JSON digest 与 row/descriptor/caller 四方是否真正同源。
- Tool Trace 是否只是延迟解析 descriptor，而不是从 raw event 字符串重算业务事实。
- 12-message stress 的原始错误 taxonomy 是否不再被 payload failure触发；不得仅放大 limit。
- 新 shared module 是否是唯一 owner，而非第四份 helper。

### Stop condition

schema pre-check必须先证明无需schema变更；focused tests、完整production stress、targeted pyright与source scans全绿；任一tamper被consumer接受、三个producer的descriptor shape不一致或任一producer仍写无界hot array时停止，不进入S2。schema pre-check失败必须在零代码修改状态返回plan review。

## Slice S2：Host Admin 与 Public Durable Actor / Async Boundary

### 目标与 finding

- 修复 DR-007、DR-011。
- 交付 execution/admin opener capability separation、public durable actor、独立scheduler/actor connection ownership、event-loop bridge与close order，作为S3-S5的稳定handoff。

### Non-goals

- 不改 CLI parser、配置 schema/overlay、session 输出格式或 R3-F README。
- 不引入通用async SQLite driver，不把scheduler整体迁移到另一event loop。
- 本slice不实现health state machine、admission lease、recovery batching、watchdog event或cancel classification；这些分别由S3-S5关闭。
- 不扩展deferred cancel所支持的Run状态，不实现Engine/Fins lifecycle。
- 不让 admin opener执行 recovery、projection catch-up、lane 或 worker side effect。

### Allowed production files/modules

- `dayu/host/api.py`
- `dayu/host/open_host.py`
- 新增 `dayu/host/_durable_actor.py`
- `dayu/host/command.py`
- `dayu/host/dispatch.py`（仅active worker cancel typed port与event-loop bridge所需边界，不改scheduler state machine）
- `dayu/host/read_api.py`
- `dayu/host/storage_maintenance.py`
- `dayu/host/__init__.py`
- 新增 `dayu/service/host_admin.py`
- `dayu/service/__init__.py`
- `dayu/cli/commands/session.py`（仅 opener routing；禁止参数/输出变化）

### Allowed tests/docs

- `tests/host/test_open_host_runtime.py`
- `tests/host/test_public_open_host_options.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_submit_followup_public_contract.py`
- `tests/host/test_command_handle.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_public_event_stream.py`
- `tests/host/test_purge_session.py`
- `tests/host/test_storage_usage_report.py`
- `tests/host/test_storage_maintenance.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`
- `tests/service/test_host_assembly.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/cli/test_session_command.py`
- 可新增 `tests/host/test_public_host_admin.py`
- 可新增 `tests/host/test_durable_actor.py`
- 可新增 `tests/service/test_host_admin.py`
- `docs/host/design.md`、`dayu/host/README.md`、`dayu/README.md`、`tests/README.md`

### 必须测试的反例

1. 真实Service + CLI list/purge在model API key全部缺失时成功；seed ACCEPTED/QUEUED/RECOVERING Run前后Run/EventLog/host-instance/lane/worker call count完全不变。
2. `open_host_admin`构造图没有scheduler、recovery、wait poller、lane、worker、scene/tool/model secret；admin handle无execution method。
3. execution `Host`与`HostAdmin`是无继承关系的独立Protocol；前者不暴露list/purge/storage admin，后者不暴露execution/cancel/watch；package export/compile tests禁止compatibility wrapper。
4. actor fixture记录thread id并打开真实SQLite：command handle、store、connection的create/use/close全部在同一个actor worker thread；scheduler store connection identity不同但两者PRAGMA/policy一致，任何live connection都不跨thread。
5. 外部connection `BEGIN IMMEDIATE`持锁，public `ensure_session/submit/read/watch`在actor中busy retry时，用`asyncio.Event`驱动的ticker/barrier证明同event loop持续前进；释放锁后command完成，禁止用sleep计数作为唯一oracle。
6. actor中command已经开始后cancel caller：底层future继续到commit/rollback和after-commit wake，actor可继续下一调用；并发calls按提交顺序完成。S3另验证new-work lease在caller cancellation期间不提前释放。
7. scheduler wake与active worker cancel从actor thread发起时，recording bridge断言callback、`LocalWorkerHandle.on_cancel()`和asyncio primitive访问都发生在opener loop thread；bridge异常返回原caller，不被actor吞掉。
8. execution close在一个actor command/wake被barrier阻塞时启动：close不先关scheduler，释放barrier后command+wake收口，再按scheduler→projection→actor handle→executor→scheduler store顺序关闭；admin close只关闭actor链，重复close幂等且无worker thread残留。

### 验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_public_host_admin.py tests/host/test_durable_actor.py tests/host/test_open_host_runtime.py tests/host/test_public_open_host_options.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py tests/host/test_submit_followup_public_contract.py tests/host/test_command_handle.py tests/host/test_dispatch_scheduler.py tests/host/test_active_cancel_dispatch.py tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py tests/host/test_purge_session.py tests/host/test_storage_usage_report.py tests/host/test_storage_maintenance.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/service/test_host_admin.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py tests/cli/test_session_command.py -q
python -m pyright dayu/host/ dayu/service/ dayu/cli/commands/session.py tests/host/ tests/service/ tests/cli/test_session_command.py
rg -n 'open_host_admin|open_host\(' dayu/cli/commands/session.py
rg -n 'asyncio\.to_thread\([^)]*(ensure_session|submit_followup|get_run|list_sessions|purge_session)|self\._command_handle' dayu/host/open_host.py
rg -n 'ThreadPoolExecutor|max_workers=1|Callable\[\[HostCommandHandle\], T\]|call_soon_threadsafe|Future\[' dayu/host/_durable_actor.py dayu/host/open_host.py
git diff --check
```

source scan期望：session list/purge明确使用admin opener，resume execution仍使用`open_host`；public handle不再直接持同步command handle或对其散落`to_thread`；actor typing、single worker与两个event-loop bridge有明确命中。若source scan命中合法close阶段`to_thread`，review必须逐项证明它不搬运actor connection。

### Review focus

- actor 是否真正拥有 connection/thread/close，而非表面 `to_thread`。
- actor callable是否method-generic且没有`Any/object`；command handle、scheduler store和actor store是否由各自owner创建/关闭。
- active cancel/wakeup是否回到正确event loop，caller cancellation、busy retry和bridge同步等待是否可能提前释放或deadlock。
- close是否先drain actor bridge再关scheduler，admin opener是否产生execution side effect；CLI fake是否掩盖真实secret/recovery路径。
- 本slice不得顺手实现S3-S5的health/recovery/cancel行为。

### Stop condition

真实admin integration、Protocol拆分、actor thread/connection ownership、event-loop lock probe、bridge与close-order tests全绿；若admin启动execution、connection跨thread、event loop ticker无法由确定性barrier推进、或scheduler关闭后仍可能收到actor wake，则停止，不进入S3。

## Slice S3：Scheduler Health、Admission Lease、Retry 与 Idempotent Replay

### 目标与 finding

- 修复DR-009。
- 修复dispatch retry exhaustion self-close confirmation，并关闭idempotent admission replay丢wake路径。
- 在S2 actor/bridge之上建立public admission与scheduler fatal共享的单一lifecycle truth。

### Non-goals

- 不修改startup recovery分页（S4）、watchdog level trigger或cancel classification（S5）。
- 不把scheduler整体迁移到actor thread或另一event loop，不引入通用supervisor framework。
- 不改变read/cancel业务语义，不扩张retry/replay允许状态。

### Allowed production files/modules

- 新增 `dayu/host/_execution_health.py`
- `dayu/host/api.py`
- `dayu/host/open_host.py`
- `dayu/host/admission.py`
- `dayu/host/command.py`
- `dayu/host/dispatch.py`
- `dayu/host/__init__.py`

S2的`_durable_actor.py`、Service/CLI文件不在本slice allowed list；若health contract要求改变actor callable/connection owner，必须停止并回到plan review。

### Allowed tests/docs

- 可新增 `tests/host/test_scheduler_health.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_submit_followup_public_contract.py`
- `tests/host/test_public_retry_replay.py`
- `tests/host/test_command_handle.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_admission_multiprocess.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`
- `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`

### Deterministic fatal/admission race mechanics

测试不得用`sleep`、重复stress或期望“恰好撞中窗口”。owner-level fixture使用真实temporary durable DB、S2真实actor，以及仅存在于tests中的typed `_BarrierDurableInvoker`（实现S2私有invoker Protocol并委托真实actor）；wrapper在public admission已经取得lease、但尚未把operation交给actor时设置`actor_entered: asyncio.Event`并等待`actor_release: asyncio.Event`。recording wake port通过真实thread-safe bridge接收`PendingDispatchRecord`，记录`wake_entered`、完整run/attempt/dispatch identity和单调顺序，然后委托真实/fake scheduler wake；它不替代durable command。

admission-first脚本固定为：

1. 启动public `submit_followup`，等待`actor_entered`；该同步点证明同一task已持admission lease但尚未commit。
2. 启动fatal coroutine；coroutine先设置`fatal_started`，随后直接调用health owner的`report_fatal(component="dispatch", reason_code="injected_critical_exit")`。主test等待`fatal_started`；由于coroutine在同一turn继续运行到被lease阻塞后才让出，fatal此时确定已排在lease后。
3. 设置`actor_release`。真实actor执行transaction；若commit成功，thread-safe bridge必须先设置`wake_entered`，public admission才可释放lease。然后fatal取得lease并进入UNAVAILABLE。
4. await两个task，不使用time-based polling。通过独立短read/admin handle断言恰好一个accepted Run、对应Attempt/dispatch真源存在且identity与recorded wake一致；wake count恰好1且顺序早于fatal commit；随后新client_request_id返回typed retryable UNAVAILABLE且没有新增Run/Attempt/dispatch/wake。

fatal-first脚本直接await同一个`report_fatal()`完成后立即并发启动public submit/read/cancel：submit不得进入barrier actor（`actor_entered`保持unset），durable DB不存在该client_request_id的Run/Attempt/dispatch且wake count=0；read/cancel仍按各自业务状态工作。另有caller-cancellation变体：在`actor_entered`后cancel submit awaiter，再启动fatal、释放actor；caller最终收到`CancelledError`，但若actor已commit则matching wake必须先完成，fatal才能commit，仍禁止accepted+zero-wake。

critical-task fatal injection另用一个精确fake critical coroutine抛固定异常，断言supervisor只把`component/reason_code`送入同一个`report_fatal()`；race test本身直接调用owner方法，不依赖task异常时序。

### 必须测试的反例

1. open/startup未完成时gate为STARTING，new-work拒绝；全部critical组件成功后才READY。
2. heartbeat/drain/promotion critical task精确异常映射为typed fatal，gate进入UNAVAILABLE；原始异常文本不进入public detail。
3. 按上述admission-first barrier，durable accepted与matching wake同在fatal之前；无accepted+zero-wake。
4. 按上述fatal-first顺序，submit不进入actor、无durable row且无wake；read/cancel/close仍可执行。
5. caller cancellation变体仍保持commit+wake/无commit二者之一，lease不因awaiter取消提前释放。
6. `HostTransactionRetryExhaustedError`一次后scheduler仍READY，pending record按poll interval重新reconcile并最终dispatch；不close worker、不标stopped、不报告fatal。
7. closed/unavailable scheduler的promotion/dispatch/watchdog wake抛typed internal unavailable，不静默return。
8. idempotent replay对pending dispatch和pre-start governance分别从durable snapshot重新派生一次matching wake；terminal/已取消record不误wake。

### 验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_scheduler_health.py tests/host/test_open_host_runtime.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py tests/host/test_submit_followup_public_contract.py tests/host/test_public_retry_replay.py tests/host/test_command_handle.py tests/host/test_dispatch_scheduler.py tests/host/test_admission_multiprocess.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q
python -m pyright dayu/host/ tests/host/
rg -n 'HostExecutionHealthGate|STARTING|READY|UNAVAILABLE|CLOSING|CLOSED|report_fatal' dayu/host/_execution_health.py dayu/host/open_host.py dayu/host/dispatch.py
rg -n 'idempotent_replay|wake_dispatch|wake_queue_promotion|HostTransactionRetryExhaustedError' dayu/host/admission.py dayu/host/command.py dayu/host/dispatch.py
rg -n 'if .*_closed.*return|Queue\(maxsize=1\)' dayu/host/dispatch.py dayu/host/open_host.py
git diff --check
```

source scan期望：health状态与fatal入口只有一个owner；retry exhausted分支不设置scheduler closed/cancel workers；idempotent replay命中可解释wake derivation。`_closed`命中只能是internal close gate，不得作为publichealth真源；watchdog queue命中留给S5并在artifact分类，不能在S3顺手修改。

### Review focus

- lease是否真实覆盖health check、actor future、commit after-callback与wake完成；caller cancellation是否破坏覆盖范围。
- deterministic fixture是否只控制时序而未fake durable结果，durable/wake identity断言是否来自同一真源。
- critical task fatal、transient SQLite retry和normal close是否被错误合并。
- idempotent replay是否从Run/Attempt/dispatch snapshot派生，而非用bool shortcut。

### Stop condition

deterministic admission-first、fatal-first、caller-cancellation三个脚本及retry/replay matrix全绿；任何sleep/probabilistic race oracle、public accepted+zero-wake、fatal后仍进入actor、或retry exhaustion使scheduler自闭时停止，不进入S4。

## Slice S4：Startup Recovery Keyset Batching

### 目标与 finding

- 修复recovery single huge transaction confirmation。
- 让startup recovery在S2 actor与S3 STARTING/READY gate之间按bounded batch完成，不改变既有orphan/recovery业务分类。

### Non-goals

- 不修改positive orphan proof、Run/Attempt状态集合、recovery上限或accepted-cancel分类。
- 不修改health lease、watchdog、cancel command或public API。
- 不使用offset pagination，不让projection/read model成为recovery真源。

### Allowed production files/modules

- `dayu/host/recovery.py`
- `dayu/host/open_host.py`（仅startup batch orchestration与READY handoff）
- `dayu/host/durable/state.py`（仅新增owner-level keyset/watermark reader）

### Allowed tests/docs

- `tests/host/test_recovery_scan.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_admission_multiprocess.py`
- `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`

### 必须测试的反例

1. batch size=2、至少5个nonterminal Run：每个write transaction最多处理2行，cursor严格按`(accepted_event_sequence, run_id)`递增，无duplicate/missing action。
2. scan开始后插入高于fixed upper watermark的新Run：本轮不处理，下一次scan处理；同sequence不同run id仍稳定排序。
3. fixed `policy.now`在所有batch一致；跨batch时钟推进不改变同一scan分类。
4. 每批commit后才wake，transaction rollback或第2批失败不产生该批wake；第1批已提交facts保持。
5. 第2批失败后完整重跑，CAS/idempotency得到与单批baseline相同terminal/dispatch/wake identity，不依赖内存offset。
6. accepted-cancel `CANCELLING`仍defer watchdog；WAITING/QUEUED/ACCEPTED分类保持设计真源，不因分页漂移。
7. 任一batch/invariant失败时opener不进入READY；已提交pending work可由下一healthy opener恢复。

### 验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_multiprocess.py tests/host/test_open_host_runtime.py tests/host/test_admission_multiprocess.py -q
python -m pyright dayu/host/recovery.py dayu/host/open_host.py dayu/host/durable/state.py tests/host/
rg -n 'read_non_terminal_runs\(|OFFSET|fetchall\(' dayu/host/recovery.py dayu/host/durable/state.py
rg -n 'accepted_event_sequence|upper_watermark|cursor|batch_size|policy_now' dayu/host/recovery.py dayu/host/durable/state.py
git diff --check
```

source scan期望：recovery不再调用全量reader或offset；keyset、watermark、batch size和fixed policy time有唯一typed owner。`fetchall`若命中只能读取单个bounded page，review必须核对LIMIT。

### Review focus

- cursor/watermark是否来自governance truth，是否处理同sequence tie-break。
- batch commit、wake与READY顺序是否明确，失败重跑是否只依赖durable CAS/idempotency。
- 是否借分页顺手改写orphan/cancel业务分类。

### Stop condition

bounded transaction、concurrent insert、batch failure/replay与READY handoff tests全绿；任何全量transaction、offset、duplicate/missing action、rollback batch wake或失败后READY时停止，不进入S5。

## Slice S5：Active-cancel Watchdog 与 Transaction-local Classification

### 目标与 finding

- 修复watchdog wakeup drop confirmation。
- 修复cancel_run deferred race confirmation。
- 保持S3 health与S4 recovery契约不变，只关闭cancel governance owner。

### Non-goals

- 不扩张cancel支持状态、不改变用户cancel terminal taxonomy或physical provider cancellation。
- 不修改recovery cursor、health state machine、actor connection或wait adapter。
- periodic scan只作恢复保障，不用缩短poll interval掩盖丢wake。

### Allowed production files/modules

- `dayu/host/command.py`
- `dayu/host/dispatch.py`
- `dayu/host/admission.py`（仅cancel释放slot后的既有promotion handoff确需调整时）

### Allowed tests/docs

- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_public_run_api.py`
- `tests/host/test_admission_multiprocess.py`
- `tests/host/test_open_host_runtime.py`
- `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`

### 必须测试的反例

1. watchdog tick在barrier中阻塞时发送第2次wake：第1轮clear后event重新set，释放barrier必有第2轮，不依赖periodic timeout。
2. 多个并发wake可合并为level signal但不能丢失tick期间的新事实；event clear/set顺序由`asyncio.Event`断言，不用sleep。
3. watchdog task非预期异常仍通过S3 supervisor报告typed fatal；正常close/cancel不误报fatal。
4. actor thread触发active cancel时，S2 bridge证明event set、token写入和`LocalWorkerHandle.on_cancel()`都在opener loop执行。
5. `_CancelRunOperation`在同一write transaction返回supported/deferred/terminal/conflict classification；transaction spy证明command异常路径没有第二次read transaction。
6. 多进程barrier在write snapshot前后改变Run/Attempt/dispatch状态，返回错误码只对应获锁transaction snapshot，不被post-write新状态改写。
7. cancel释放active slot后promotion wake与durable classification一致；idempotent/terminal loser不重复wake。

### 验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_active_cancel_dispatch.py tests/host/test_dispatch_scheduler.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py tests/host/test_admission_multiprocess.py tests/host/test_open_host_runtime.py -q
python -m pyright dayu/host/command.py dayu/host/dispatch.py dayu/host/admission.py tests/host/
rg -n '_is_deferred_cancel_state|Queue\(maxsize=1\)|except asyncio\.QueueFull' dayu/host/command.py dayu/host/dispatch.py
rg -n 'asyncio\.Event|wake_active_cancel_watchdog|_CancelRunOperation' dayu/host/command.py dayu/host/dispatch.py
git diff --check
```

source scan期望：deferred post-write reader、bounded watchdog queue与QueueFull吞wake均无结果；level event与transaction-local classification有明确命中。

### Review focus

- event clear/set是否真正level-triggered，是否会busy-loop或在tick窗口丢wake。
- cancel分类是否由一次write snapshot拥有，是否保留现有支持集合和error taxonomy。
- actor bridge、health fatal与cancel owner之间是否出现反向调用/deadlock。

### Stop condition

deterministic second-wake、transaction spy、多进程snapshot race与promotion tests全绿；任何QueueFull吞wake、post-write read、错误码来自新snapshot或watchdog异常未进入S3 health时停止，不进入S6。

## Slice S6：Wait Expiry、Bounded Observation 与 Host Shutdown

### 目标与 finding

- 修复 DR-008、DR-012。
- 完成 wait adapter reverse-dependency adjudication 的 R3-A Host contract 半边；R3-D 搬迁半边不越界实施。

### Non-goals

- 不修改 `dayu/fins/`、Fins observation runtime 或 provider I/O 实现。
- 不把 deadline expiry解释为 LOST；不接受 deadline 后 provider success。
- 不新增 shell/CLI/config行为，不重写整个 wait schema。

### Allowed production files/modules

- `dayu/host/api.py`（仅 wait policy/result contract）
- `dayu/host/waiting.py`
- `dayu/host/wait_adapter.py`
- 新增 `dayu/host/_wait_observation.py`
- `dayu/host/command.py`
- `dayu/host/open_host.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/state.py`
- `dayu/host/__init__.py`

`dayu/fins/`、`dayu/service/fins_direct.py` 与 Engine 文件不在 allowed list。

### Allowed tests/docs

- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_wait_callback.py`
- `tests/host/test_wait_adapter_polling.py`
- `tests/host/test_wait_poller_runtime.py`
- 可新增 `tests/host/test_wait_observation_runner.py`
- `tests/host/test_wait_cancel_late_result.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_public_open_host_options.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_package_exports.py`
- 可新增 `tests/host/test_wait_expiry_closeout.py`
- `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`

### 必须测试的反例

1. 直接调用`_expire_wait_in_transaction()`的owner test传入已有`HostTransaction`，transaction spy证明helper不打开nested transaction/public resolver；构造的现有`ResolveWaitFailedOutcome`固定`error=wait_deadline_expired`、业务message、`hint/meta/payload_ref=None`，稳定idempotency不依赖source。
2. poller首次看到deadline已过：provider call count=0；Wait/Attempt/Run及两个terminal facts同transaction进入FAILED，active slot释放，下一QUEUED Run只在commit后promotion。
3. direct/callback result的`observed_at`已过deadline：同一transaction先commit expiry再写late rejection；caller虽收到INVALID_STATE，projection/promotion已完成。
4. result/cancel/expiry三方多进程barrier race：恰好一个terminal event/ref，Run/Wait/Attempt一致；result先提交时expiry typed no-op，expiry先提交时late source只diagnostic/idempotent。
5. deadline前completed/failed/lost保持现有语义；INVALID boundary不被误判为expiry；`ResolveWaitCancelledOutcome`仍resume而不误释放slot。
6. fake `poll_wait()`永不返回：adapter timeout可由test policy缩小；Host将wait收为LOST，poller loop继续/close有界，observation token先INVALIDATED，late adapter result不能publish或写durable。
7. fake `poll_wait()`在timeout后由barrier返回READY：thread只得到`publish=False`，registry eventually FINISHED；Run仍LOST且没有`TOOL_RESULT_ACCEPTED`/resume/wake。
8. `max_outstanding_adapter_calls=1`且第一个adapter永久阻塞：第二个wait不spawn新thread，得到capacity diagnostic/backoff；live thread count始终1，释放第一个后registry清零并可观察下一wait。
9. fake `abandon_wait()`永不返回：cancelled wait写timeout diagnostic/abandon close marker，不重复创建观察线程，不宣称external cancel成功，Host close有界。
10. supervisor close时一个poller loop和两个observation threads受不同barrier阻塞：只使用一个shared deadline，elapsed不随thread数倍增；status=CLOSING、refs保留、主store/actor可关闭。逐个释放后最后一个finally才置STOPPED，第二次close幂等。
11. `close_drain_timeout_seconds=None`、non-finite/non-positive budget与non-positive outstanding cap都在policy owner拒绝。

### 验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_wait_expiry_closeout.py tests/host/test_wait_observation_runner.py tests/host/test_resolve_wait_command.py tests/host/test_wait_callback.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py tests/host/test_phase7_waiting_integration.py tests/host/test_public_open_host_options.py tests/host/test_open_host_runtime.py tests/host/test_package_exports.py -q
python -m pyright dayu/host/ tests/host/
rg -n 'thread\.join\(\)|close_drain_timeout_seconds: float \| None|join_thread\(\)' dayu/host/wait_adapter.py dayu/host/_wait_observation.py
rg -n '_release_expired_or_invalid_boundary|WAIT_EXPIRED' dayu/host/wait_adapter.py dayu/host/waiting.py
rg -n 'ExpireWaitInput|_expire_wait_in_transaction|ResolveWaitFailedOutcome|fail_run_from_waiting_in_transaction' dayu/host/waiting.py dayu/host/wait_adapter.py dayu/host/durable/run_transition.py
rg -n 'max_outstanding_adapter_calls|ACTIVE|INVALIDATED|FINISHED|publish' dayu/host/_wait_observation.py dayu/host/wait_adapter.py
git diff --name-only -- dayu/fins/
git diff --check
```

source scan期望：无无参thread join、无可选close timeout、无queue feeder无界join；旧expired release helper不存在，common expiry owner从poll/direct路径均有命中；observation cap/token gate有唯一owner；`dayu/fins/` diff为空。

### Review focus

- FAILED 与 LOST 的分类是否基于“deadline 已确认”与“观察不可确认”两种不同事实。
- late error 是否发生在 commit/promotion 后，避免“显示拒绝但 durable仍 WAITING”。
- expiry helper是否只消费caller-provided transaction、复用现有failed transition/payload planner，且幂等identity不被外部source污染。
- daemon invocation thread是否只持adapter/immutable snapshot/token/result queue；token invalidation与publish是否同锁，是否存在late result use-after-close。
- outstanding cap与shared close deadline是否真正有界；supervisor CLOSING/STOPPED是否反映poller及所有tracked thread真实状态。
- R3-D reverse dependency residual 是否明确，没有 compatibility adapter偷渡。

### Stop condition

expiry helper contract/terminal matrix、多进程first-commit race、late-result gate、outstanding cap、stuck poll/abandon与boundedHost close全部通过；任何Wait仍可无限WAITING、late thread仍可publish/接触store、tracked thread无上限、close预算按thread倍增、存在无界join或`dayu/fins/`被修改时停止，不进入S7。

## Slice S7：Compaction Attempt Cancellation 与 Pre-call Recheck

### 目标与 finding

- 修复 DR-025。
- 修复 proactive compaction TOCTOU confirmation 的当前窄化版本。

### Non-goals

- 不改 compaction schema、quality policy、memory语义、Engine provider timeout分类。
- 不把 writable cancellation加入 Engine/contracts公共协议。
- 不处理 R3-B provider 或 R3-E document/web上下文。

### Allowed production files/modules

- `dayu/host/compaction_operation.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/dispatch.py`（仅 proactive token wiring/recheck）
- `dayu/host/engine_ingest.py`（仅 reactive compaction调用参数确需迁移时）

### Allowed tests/docs

- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/fake_cancellation.py`
- 可新增 `tests/host/test_compaction_cancellation_scope.py`
- `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`

### 必须测试的反例

1. `max_attempts=2`：attempt 1 timeout，attempt 2返回合法 proposal；runner call count=2，parent token未取消，result accepted。
2. attempt 1 timeout、repair前 parent取消：attempt 2 provider不调用，最终 rejection reason使用 parent cancel，不使用 timeout。
3. provider运行中 parent取消：child立即观察相同 reason/requested_at；外层 caller cancellation仍按现有结构化路径传播。
4. recorder hook 在 manifest写完后改变 durable Run status/input cursor：pre-call check命中，provider call count=0，manifest ref保留用于diagnostic。
5. 正常 proactive path fresh token 不增加额外 event/schema，不在 transaction内 await provider。

### 验证命令

```bash
source .venv/bin/activate
pytest tests/host/test_compaction_cancellation_scope.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py -q
python -m pyright dayu/host/compaction_operation.py dayu/host/llm_compaction.py dayu/host/dispatch.py dayu/host/engine_ingest.py tests/host/
rg -n '_signal_timeout_cancellation|request_cancel\(' dayu/host/llm_compaction.py dayu/host/compaction_operation.py
git diff --name-only -- dayu/engine/
git diff --check
```

source scan 由 review 确认 timeout 写入对象只能是 attempt child；`dayu/engine/` diff必须为空。

### Review focus

- parent/child precedence、每 attempt新实例与 requested_at是否一致。
- timeout、outer task cancellation、parent Host cancellation是否被错误合并。
- manifest记录与provider call之间是否有真实第二次 durable check，而不是调用前早检查。
- 是否出现跨 LLM transaction 或下游 fallback。

### Stop condition

timeout-to-success、parent cancel和manifest-to-provider竞态全部通过，parent token不被proposal timeout污染，Engine diff为空；否则停止，不进入S8。

## Slice S8：Layer-neutral Runtime Partial Cleanup Completion

### 目标与 finding

- 修复 DR-017、DR-029。
- DR-017按partial start/cleanup poisoning处理；DR-029按release已尝试但失败token仍存在时错误commit completed处理，不再声称release前commit。
- 保持 `dayu.runtime` 层中立，不引入 Host/Engine/Service/Fins import。

### Non-goals

- 不重构 runtime God file、不统一全仓 close接口、不清理无关 Any/docstring/style。
- 不改变 Lane capacity/TTL算法或 process业务结果协议。
- 不强制五状态重写，不允许同一process handle在`Process.start()`异常后重试；调用方重试必须新建handle。
- 不在 Host 下游捕获并吞掉 runtime cleanup error。

### Allowed production files/modules

- `dayu/runtime/interruptible_process.py`
- `dayu/runtime/lane.py`
- `dayu/runtime/__init__.py`（仅确需导出新 public typed 状态时；默认状态保持私有）

### Allowed tests/docs

- `tests/runtime/test_interruptible_process.py`
- `tests/runtime/test_lane.py`
- `tests/runtime/test_lane_multiprocess.py`
- `tests/runtime/test_import_boundary.py`
- `tests/host/test_dispatch_scheduler.py`（只验证调用方传播，不改 Host production）
- `tests/host/test_open_host_runtime.py`（只验证 close integration）
- `tests/README.md`

### 必须测试的反例

1. fake `Process.start()`在确定pre-spawn点抛异常：同一handle第二次start仍拒绝；close执行process-valid cleanup与queue close/join，随后新建handle可成功start。不得把原handle恢复为NEW。
2. fake `Process.start()`在模拟child/pid已建立后抛异常：同一handle不可重试；close能kill/join/process.close并完成queue cleanup，不留下orphan。test不以`is_alive=False`作为允许重试证据。
3. kill、process join、process close分别抛transient exception：后续queue.close与feeder cleanup仍由finally尝试；完成步骤有记录，第二次close只补未完成步骤，最终无live process/feeder thread。
4. close在kill、process join/close、queue close/join checkpoint遭caller cancellation：single cleanup task继续；第二个caller共享/等待同一task或在失败后重试，不能并发执行两套破坏性cleanup。
5. 两个并发process close caller只执行一套cleanup，得到相同成功或同一个typed failure；`_closed`只阻断新操作，只有cleanup-completed才允许后续close直接return。
6. Lane持2个token，其中1个首次release失败：两个release都被尝试，成功token已删除、failed token保留、`_close_completed=false`；第二次close只重试failed token并completed=true。这明确验证release-failure-after-attempted-release。
7. Lane并发close/caller cancellation/heartbeat error：不接收新acquire，首次reason稳定，heartbeat只停止一次，所有token最终release；partial exception不被吞且不提前completed。
8. runtime import scan仍无`dayu.engine/host/service/ui/fins`，Host调用方只传播cleanup error、不实现补偿cleanup。

### 验证命令

```bash
source .venv/bin/activate
pytest tests/runtime/test_interruptible_process.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py tests/runtime/test_import_boundary.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py -q
python -m pyright dayu/runtime/ tests/runtime/ tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py
rg -n '_started|_closed|cleanup|join_thread|cancel_join_thread' dayu/runtime/interruptible_process.py
rg -n '_close_completed = True|_held_tokens|close_task|close_lock' dayu/runtime/lane.py
rg -n 'dayu\.(engine|host|service|ui|fins)' dayu/runtime
git diff --check
```

source scan不是单独正确性证明：process的start/close gate可以在副作用前设置，但不得被当作cleanup completion；`_close_completed=True`只能位于“heartbeat stopped + held_tokens empty + no error”分支。review必须读上下文并核对partial-step tests。

### Review focus

- start/close并发gate与resource completion是否分离；是否错误地为同一handle恢复start重试。
- shielded task 是否可能丢失异常、泄漏 task或让close虚假成功。
- process任一步失败后queue feeder cleanup是否仍执行，process/queue join是否全部有界；是否错误捕获BaseException。
- Lane成功/失败token tracking与并发close锁序。
- runtime import boundary与无Host专用reason/type渗入。

### Stop condition

process pre/post-spawn start failure、每个cleanup checkpoint、queue feeder cleanup、lane partial release/concurrent close与runtime import tests全绿；任何同handle start retry、并发gate被误作completion、第二次close不能补清理、failed token被completed短路或存在无界join时停止。

## R3-A accepted finding / confirmation traceability

下表是implementation与review的最小覆盖账本。任何行都不得被省略、合并成“相关测试已过”或推迟到其它R3 sub-WU；唯一允许保留给后续owner的是controller已裁决的Fins wait-adapter reverse dependency之R3-D搬迁半边。

| Accepted finding / confirmation | Slice / owner closure | Required tests | Required source scan | Slice stop evidence |
| --- | --- | --- | --- | --- |
| DR-006 runner-call hot payload unbounded | S1 shared hot atoms + descriptor | 0/1/12/300 producer matrix、production stress 12/12 | producer `projector_metadata_summary` 与shared atom scan | hot payload <4096且不随message count线性增长，否则S1 stop |
| DR-010 descriptor content/digest split | S1 durable resolver + execution config projection | schema pre-check、SQLite/artifact tamper matrix、config ref/digest tamper | schema digest/size columns、所有consumer委托shared resolver | 任一tamper被接受或pre-check缺列即S1 stop |
| compact_material wrong call ref fallback | S1 compact provenance owner | missing/wrong-type/identity-mismatch request ref | `tool_call_event_ref = row.event_id`无命中 | 任一伪造ref被接受即S1 stop |
| DR-007 admin command opens execution Host | S2 independent HostAdmin/opener | no-secret real Service+CLI list/purge、zero execution side effects | CLI `open_host_admin/open_host`路由与Protocol export scan | admin启动scheduler/recovery/lane/worker即S2 stop |
| DR-011 async Host blocks event loop | S2 connection-owned actor | external `BEGIN IMMEDIATE` + Event barrier ticker、thread identity、caller cancel/close | public direct sync handle/散落`to_thread`无命中；actor typing/worker命中 | ticker不能确定推进、connection跨thread或close乱序即S2 stop |
| DR-009 scheduler fatal not propagated | S3 health/admission owner | deterministic admission-first/fatal-first/caller-cancel race | single health owner、closed-wake/public `_closed` scan | accepted+zero-wake、fatal后actor admission即S3 stop |
| dispatch retry exhaustion self-closes | S3 scheduler transient reconciliation | one-shot retry exhaustion后最终dispatch | retry branch不得设置closed/cancel workers | retry导致UNAVAILABLE/worker close即S3 stop |
| idempotent admission replay skips wake | S3 admission replay derivation | pending dispatch/pre-start replay matching wake | `idempotent_replay`与wake derivation scan | pending durable work replay无wake即S3 stop |
| recovery single huge transaction | S4 recovery scanner | batch=2、fixed watermark/time、mid-batch failure/replay | full reader/OFFSET无命中，keyset/LIMIT命中 | unbounded tx、duplicate/missing/wrong wake即S4 stop |
| watchdog wakeup drop | S5 active-cancel watchdog | tick barrier内second wake必有second tick | Queue(maxsize=1)/QueueFull无命中，Event命中 | tick窗口丢wake或依赖periodic timeout即S5 stop |
| cancel_run deferred race | S5 cancel command transaction owner | transaction spy、多进程snapshot race | `_is_deferred_cancel_state`与post-write read无命中 | classification来自第二snapshot即S5 stop |
| DR-008 expired wait remains WAITING | S6 wait expiry owner | helper contract、poll/direct/callback、result/cancel/expiry race | common expire helper与existing failed transition调用链 | 任一expired Wait仍WAITING或terminal facts分裂即S6 stop |
| DR-012 wait adapter can hang close | S6 bounded observation/supervisor | stuck poll/abandon、late publish、cap=1、shared close deadline | optional timeout/无参join/无界join无命中；token gate/cap命中 | close无界、thread无上限、late durable write即S6 stop |
| Fins wait-adapter reverse dependency split | S6只交付R3-A Host bounded contract | Host adapter Protocol/close tests | `git diff --name-only -- dayu/fins/`为空 | 修改Fins或声称R3-D搬迁已完成即S6 stop |
| DR-025 compactor timeout contaminates parent | S7 attempt child token | timeout→repair success、parent cancel precedence | timeout `request_cancel`只命中child owner | parent token被proposal timeout写入即S7 stop |
| proactive compaction TOCTOU | S7 manifest-to-provider recheck | recorder后改变durable snapshot，provider count=0 | prepare/recorder/pre-call token check | stale snapshot仍调用provider即S7 stop |
| DR-017 process partial start/cleanup poisoning | S8 interruptible process cleanup owner | pre/post-spawn start failure、每步partial failure/cancel、queue feeder、concurrent close | start/close gate、cleanup/join scan | 同handle重试、queue泄漏、第二close不能补齐即S8 stop |
| DR-029 lane completion after failed release | S8 LaneController close owner | two-token one-release-fails、second retry、concurrent cancel/heartbeat | `_close_completed`与`_held_tokens`上下文scan | failed token仍在却completed或无法retry即S8 stop |

## Integrated production-high validation

8个slice都通过自己的stop condition后，执行一次集成验证。命令必须在仓库根目录、激活`.venv`后运行并完整记录到implementation artifact：

```bash
source .venv/bin/activate
pytest tests/host tests/runtime tests/service tests/cli/test_session_command.py -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest -q
python -m pyright dayu/ tests/ utils/
git diff --name-only -- dayu/config/ dayu/engine/ dayu/fins/
git diff --check
```

预期结果：

- focused Host/runtime/service/session CLI tests 全绿。
- production stress 5/5 通过，不再记录为 R3-A dependency。
- 默认 pytest 全绿；若出现与本轮无关的新失败，必须用直接堆栈与 baseline registry分类，禁止修改其它 sub-WU owner。
- pyright 0 error；不得新增、扩散或 suppression。
- `dayu/config/`、`dayu/engine/`、`dayu/fins/` diff为空。
- `git diff --check` 通过。

另做以下 owner-level source audit，并在 implementation artifact 记录命中清单：

```bash
rg -n 'except BaseException|thread\.join\(\)|time\.sleep\(' dayu/host dayu/runtime
rg -n 'projector_metadata_summary|_is_deferred_cancel_state|Queue\(maxsize=1\)' dayu/host
rg -n 'self\._command_handle|asyncio\.to_thread\([^)]*(ensure_session|submit_followup|get_run|list_sessions|purge_session)' dayu/host/open_host.py
rg -n 'read_non_terminal_runs\(|OFFSET|max_outstanding_adapter_calls|INVALIDATED|HostExecutionHealthGate' dayu/host
rg -n 'from dayu\.(engine|host|service|ui|fins)|import dayu\.(engine|host|service|ui|fins)' dayu/runtime
```

命中并不一律等于失败；每个命中必须证明位于合法 owner。新增 `except BaseException`、wait supervisor无界 join、producer hot summary、deferred post-read或runtime反向依赖一律阻断 closeout。

## README 与设计文档 decision

- `docs/host/design.md`：必须更新。新增 admin opener、public durable actor、scheduler health/admission gate、wait expiry FAILED contract、bounded poller close、runner-call fixed hot atoms与descriptor integrity。
- `dayu/host/README.md`：必须按其 Agent 更新约束，在对应 slice 落地后只描述已实现 contract，不写 work-unit流水账或未来计划。
- `dayu/README.md`：必须更新 execution/admin Host 与 Service assembly 的跨包边界；只写总揽级关系。
- `tests/README.md`：必须更新新增 owner-level测试层级与显式 production stress 命令/预期；不写逐文件实现流水账。
- 根 `README.md`：不更新。session list/purge 参数、输出和用户工作流不变，变化仅是内部不再启动执行面；不命中最终用户手册新增行为。
- `dayu/config/README.md`、`dayu/engine/README.md`、`dayu/fins/README.md`：不更新，因为对应 production package 不在本轮修改范围。
- 若实施中出现会改变上述 decision 的直接证据，必须先停止当前 slice并回到 plan review，不能机械同步 README。

## 明确不合并修复的边界

- DR-006 不能通过增大 inline limit、压缩 JSON、stress-only fixture或 provider startup timeout fallback修。
- DR-007 不能通过设置 fake secret、no-op worker、CLI 直读SQLite或保留 execution Host上的admin compatibility methods修。
- DR-008 不能只在 poller改status；所有terminal fact必须经 common wait state machine同事务产生。
- DR-009 不能只在 admission前读 `_closed`；必须有覆盖transaction+wake的lease。
- DR-010 不能在terminal/outbox/evidence各加digest fallback；必须共享durable resolver。
- DR-011 不能把同一 SQLite connection随机传给 `asyncio.to_thread`。
- DR-012 不能第一次 join超时后继续第二次无界 join，也不能虚假标STOPPED。
- DR-017不能把start异常后的同一handle恢复为可重试，也不能只靠五状态名替代partial resource cleanup；DR-029不能在failed token仍held时标completed。二者都不能catch-and-log或在Host调用点重复cleanup。
- DR-025 不能在第二次attempt前清空parent token；parent是Run cancel真源，proposal timeout只能写child。

## Residual risks 与 owner

1. `dayu/fins/ingestion/wait_adapter.py` 的 Host反向依赖在本轮后仍可能存在；这是 controller 明确的 R3-D/R3-A boundary split。R3-A交付 Host bounded contract，R3-D负责将具体 Fins-to-Host adapter移到 Service/上层并清除 import；R3-A不得越界修改。
2. bounded sync adapter timeout后，provider daemon thread可能仍运行到进程退出。它受outstanding cap追踪、token已INVALIDATED、不持Host durable authority，且Wait会FAILED/LOST后停止重复poll；provider协作式cancel由R3-D half继续消除。若线程仍能写Host store或绕过cap，S6不得closeout。
3. DR-011 本轮消除 public Host/Admin command/read/watch与startup recovery对调用方event loop的同步SQLite阻塞；scheduler open/close及runtime内部短transaction仍由scheduler event-loop owner执行，并受现有finite busy/retry policy约束。若集成lock probe证明scheduler-owned transaction本身可造成不可接受的heartbeat freeze，必须登记新的R3-A residual/plan review，不能临时把connection跨线程。
4. fresh-schema政策意味着S1遇到既有tampered descriptor会fail closed，不提供兼容读取。部署前坏数据审计属于运维动作，不在代码fallback。
5. health gate在fatal后拒绝新work，但已commit durable pending work依赖下次healthy opener/recovery继续；public error必须明确retryable，不能宣称该Run已执行。

## 每个 slice 的 completion report 模板

implementation artifact 对每个 slice 必须记录：

1. 实际修改文件，逐项映射到 allowed list。
2. finding 状态：`fixed`、`accepted-narrowed-fixed`、`deferred-with-owner`；不得省略 controller confirmation。
3. owner contract 与禁止fallback source scan结果。
4. focused tests、stress、targeted/full pyright、default pytest、`git diff --check` 的原始摘要。
5. README decision 与实际更新文件。
6. residual risk、触发证据、明确 owner/sub-WU。

任何需要修改 R3-B/R3-C/R3-D/R3-E production file、改变R3-F public CLI/config contract、加入compatibility wrapper或放宽测试oracle的情况，都视为本计划阻断条件，必须停止并交回controller裁决。

## 本 plan gate 的 stop condition

本文已完成accepted finding直接证据复核、plan-review correction、owner裁决、8个可独立验证slice、逐项traceability，以及每个slice的目标/non-goals/allowed files/tests/pyright/source scan/review focus/stop condition和集成validation/README/residual decision。当前状态为`ready-for-plan-rereview`；只完成plan-fix，不进入实现、不修改control doc、不commit。
