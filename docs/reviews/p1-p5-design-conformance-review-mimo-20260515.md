# P1-P5 Design Conformance Review

## Scope

- Mode: all repository (P1-P5 full codebase conformance)
- Branch: feat/host-phase5-local-dispatch
- Base: main
- Reviewer: AgentMiMo
- Output file: docs/reviews/p1-p5-design-conformance-review-mimo-20260515.md
- Included scope: P1 public contracts & runtime, P2 durable store & EventLog, P3 session/run/attempt/admission, P4 public API command path, P5 RunInputBuilder/local dispatch/local proxy/engine ingest/cancel, cross-phase layering, production wiring, deferred phase readiness
- Excluded scope: Service / UI / Fins layers, Engine internal implementation, config module
- Historical artifacts reviewed: `docs/reviews/p5-design-conformance-review-mimo-20260515.md`, `docs/reviews/p5-design-conformance-review-controller-adjudication-20260515.md`

## Verdict: PASS

P1-P5 当前全仓代码实现与 `docs/host/design.md` 高度一致。8 个审查 lens 均未发现 blocking design deviation。0 个 blocking findings，2 个 non-blocking hardening items。

## Findings

### F1 `DEFAULT_ACTIVE_WORKER_REGISTRY` 是模块级 mutable singleton

- 文件: `dayu/host/dispatch.py:262`
- 严重性: **non-blocking hardening**
- 证据: `DEFAULT_ACTIVE_WORKER_REGISTRY = ActiveWorkerRegistry()` 是模块级可变单例。当前 `HostDispatchScheduler.__init__` 允许注入 `active_registry`，生产路径通过 `HostDispatchScheduler.open()` 使用默认值。`command.py` 中 `cancel_active_worker(message)` 直接调用该模块级单例。
- 影响: 多 handle 场景下（测试或未来多 Host instance）可能共享同一 registry，导致 cancel 传播跨 handle 边界。当前单 handle 生产路径不触发此问题。
- 建议: 后续 hardening 可将 `cancel_active_worker` 改为 handle-bound 方法，或在 `create_host_command_handle` 中注入 registry。

### F2 `HostApiErrorDetail` TypeAlias 只有一个成员

- 文件: `dayu/host/api.py:513`
- 严重性: **no issue / doc note**
- 证据: `HostApiErrorDetail: TypeAlias = SteerConflictDetail` 当前只有一个 union 成员。设计要求"后续新增错误 detail 时必须新增具体 typed detail"。
- 影响: 当前 Phase 1-5 不需要更多 detail 成员。TypeAlias 结构正确，后续扩展时加新成员即可。
- 无需修改。

## Non-blocking Design Drift

无。

## Evidence by Lens

### Lens 1: P1 公共契约与 runtime 边界

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| `dayu.runtime` 无反向 import | PASS | `tests/runtime/test_import_boundary.py` 扫描全部 `dayu/runtime/*.py`，禁止 `dayu.engine/host/service/ui/fins` |
| Host 公共类型在 `dayu.host.api` | PASS | `dayu/host/api.py` 定义全部 request/snapshot/status/error 类型 |
| `dayu.contracts` 只含层间契约 | PASS | 包含 `cancellation.py`、`json_value.py`、`tool_call.py`、`tool_executor.py`、`tool_outcome.py`、`tool_schema.py` |
| ToolBundle 只在 construction input | PASS | `tests/host/test_import_boundary.py:172-191` 验证所有 request dataclass 无 `business_tool_bundle` 字段 |
| `dayu.runtime.lane` 层中立 | PASS | `dayu/runtime/lane.py:1-7` docstring 明确不表达 Host truth；只 import `dayu.contracts.cancellation` |
| `dayu.runtime.filelock` 层中立 | PASS | `dayu/runtime/filelock.py:1-6` docstring 明确不表达 Host truth；第三方 `filelock` 只在此文件导入 |
| 无 `Any` 类型注解 | PASS | grep `dayu/host/**/*.py` 无 `Any` 匹配 |
| 无 `object` 类型注解 | PASS | grep 结果仅 docstring 中的 "JSON object" 等自然语言描述 |
| StrEnum 用于枚举 | PASS | `SessionStatus`/`RunStatus`/`AttemptStatus`/`FollowupBehavior`/`HostApiErrorCode`/`EventClass`/`DispatchRecordStatus`/`WorkerKind` 等全部继承 `StrEnum` |
| FrameworkToolPolicyView frozen dataclass | PASS | `dayu/host/tooling.py` 中 `FrameworkToolPolicyView` 使用 `@dataclass(frozen=True, slots=True)` |
| `ToolBundleSourceKind` 使用 StrEnum | PASS | `dayu/host/tooling.py` 中 `ToolBundleSourceKind(StrEnum)` |

### Lens 2: P2 durable store 与 EventLog

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| fresh schema bootstrap | PASS | `schema.py:490-513`：`user_version=0` 创建 schema 并设置 `PRAGMA user_version=3`；其它版本结构化失败 |
| 无兼容迁移 | PASS | `bootstrap_host_durable_store` 不包含 ALTER TABLE 或 migration logic |
| event_id UNIQUE | PASS | `schema.py:105`：`event_id TEXT NOT NULL UNIQUE` |
| event_sequence AUTOINCREMENT | PASS | `schema.py:104`：`event_sequence INTEGER PRIMARY KEY AUTOINCREMENT` |
| event_class CHECK 约束 | PASS | `schema.py:107-113`：`CHECK (event_class IN ('canonical_fact','preview','diagnostic','projection_signal'))` |
| event_type 必填 | PASS | `schema.py:119`：`event_type TEXT NOT NULL` |
| append-only 语义 | PASS | `event_log.py` 只提供 `append_event` 和 read 方法，无 update/delete |
| idempotency (scope_kind, scope_id, idempotency_key) PK | PASS | `schema.py:147`：`PRIMARY KEY(scope_kind, scope_id, idempotency_key)` |
| idempotency 绑定 semantic_input_digest | PASS | `idempotency.py:27-38`：`IdempotencyScope` + `semantic_input_digest` |
| BEGIN IMMEDIATE | PASS | `transaction.py:237`：`self._connection.execute("BEGIN IMMEDIATE")` |
| WAL mode | PASS | `transaction.py:307`：`connection.execute("PRAGMA journal_mode=WAL")` |
| busy_timeout | PASS | `transaction.py:302-305`：`PRAGMA busy_timeout={busy_timeout_ms}` |
| foreign_keys=ON | PASS | `transaction.py:306`：`connection.execute("PRAGMA foreign_keys=ON")` |
| after-commit 只在 commit 后执行 | PASS | `transaction.py:239,263`：`COMMIT` 在 `_run_after_commit` 之前 |
| payload_kind CHECK: sqlite_payload / artifact_ref | PASS | `schema.py:80`：`CHECK (payload_kind IN ('sqlite_payload', 'artifact_ref'))` |
| host instance liveness 无 lease/fencing | PASS | `liveness.py:1-5` docstring 明确"不实现 lease、fencing、takeover" |
| idempotency conflict 不 retry | PASS | `transaction.py:243-256`：只对 `_is_busy_or_locked` retry，`HostIdempotencyConflictError` 不在 retry 范围 |

### Lens 3: P3 session/run/attempt/admission

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| Session 状态集合完整 | PASS | `schema.py:170`：`CHECK (status IN ('open', 'closed'))` |
| Run 状态集合完整 | PASS | `schema.py:221-232`：9 个状态全部在 CHECK 约束中 |
| Attempt 状态集合完整 | PASS | `schema.py:301-310`：8 个状态全部在 CHECK 约束中 |
| active Run partial unique index | PASS | `schema.py:442-446`：`CREATE UNIQUE INDEX ... ON host_runs(session_id) WHERE status IN ('running','waiting','cancelling','recovering')` |
| queue FIFO by event_sequence | PASS | `schema.py:448`：`INDEX_HOST_RUNS_QUEUE_FIFO` 按 `session_id, accepted_event_sequence` |
| dispatch record 状态 CHECK | PASS | `schema.py:348-349`：`CHECK (status IN ('pending','waiting_for_lane','dispatching','cancelled'))` |
| dispatch record 不是 lease/owner | PASS | `state.py:50-56` docstring："不是 lease / fencing / owner truth"；`state.py:175-180`："active worker truth 只能由 ATTEMPT_RUNNING 与 Attempt row RUNNING 表达" |
| CAS-style transitions | PASS | `state.py` 使用 `UPDATE ... WHERE attempt_id=? AND status=?` + `rowcount` 检查 |
| terminal closeout 触发 promotion | PASS | `admission.py:584-593`：`closeout_attempt_terminal` 后调用 `_promote_after_release` |
| cancel queued 不创建 Attempt | PASS | `run_transition.py` 中 `cancel_queued_in_transaction` 只追加 CANCEL_REQUESTED + RUN_CANCELLED |
| cancel pre-dispatch 标记 dispatch cancelled | PASS | `run_transition.py` 中 `cancel_predispatch_starting_in_transaction` 标记 dispatch record cancelled |
| cancel active 进入 CANCELLING | PASS | `admission.py:2240-2250`：active running → CANCELLING + 向 worker 传播 |

### Lens 4: P4 public API command path

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| create_host_command_handle 同步 facade | PASS | `command.py:195-225`：同步函数，对 `local_execution` 非空 raise ValueError |
| HostApiError typed contract | PASS | `api.py:1581-1595`：`code: HostApiErrorCode, message: str, retryable: bool, detail: HostApiErrorDetail \| None` |
| detail 是 typed union | PASS | `api.py:513`：`HostApiErrorDetail: TypeAlias = SteerConflictDetail` |
| submit_followup(steer) → UNSUPPORTED_OPERATION | PASS | `command.py:335-340` |
| retry_run → UNSUPPORTED_OPERATION | PASS | `command.py:467` |
| replay_run → UNSUPPORTED_OPERATION | PASS | `command.py:484` |
| resolve_wait → UNSUPPORTED_OPERATION | PASS | `command.py:501` |
| purge_session → UNSUPPORTED_OPERATION | PASS | `command.py:520` |
| stream_run_events 全局 cursor | PASS | `read_api.py:59-85`：使用 `HostStreamCursor`，从 EventLog 全局 `event_sequence` 补读 |
| stream_run_events 不触发执行 | PASS | `read_api.py:47-56`：`get_run` 只读取 Run row，不 dispatch |
| HostCallContext 定义 | PASS | `api.py` 中 `HostCallContext` 含 actor/source/request_id/authorization_claims/operation_context |
| cancel_run 覆盖 queued/pre-dispatch/active | PASS | `command.py:361-450`：覆盖 queued、pre-dispatch STARTING、pre-accept dispatching、active worker |
| cancel_session_runs 对 WAITING/RECOVERING → UNSUPPORTED | PASS | `admission.py:1339-1347`：WAITING/RECOVERING targets 返回 `None`，触发 UNSUPPORTED_OPERATION |
| UNSUPPORTED_OPERATION 消息标注 phase owner | PASS | `command.py:338`："deferred beyond Phase 4"；`command.py:393`："later cancel owner phase" |

### Lens 5: P5 RunInputBuilder/local dispatch/local proxy/engine ingest/cancel

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| RunInputBuilder typed providers | PASS | `run_input.py` 定义 `CurrentRunFactProvider`/`SessionContinuityProvider`/`SceneParameterProvider`/`PolicySnapshotProvider` 等 Protocol |
| 不接收 untyped bag | PASS | `RunInputBuilder.__init__` 接收 8 个 typed provider 参数 |
| LocalProxy envelope 承载 Host identity | PASS | `engine_ingest.py:123-146`：`LocalEngineEnvelope` 含 session_id/run_id/attempt_id/execution_id/dispatch_record_id |
| EngineEvent 不含 Host identity | PASS | `engine_events.py:430-448`：`EngineEvent` 只含 occurred_at/session_id/run_id/type/data/metadata，无 attempt_id/execution_id/dispatch_record_id |
| EngineEventIngestor 从 envelope 读 Host identity | PASS | `engine_ingest.py` 中 `EngineEventCandidate` 包含 `envelope: LocalEngineEnvelope` + `engine_event: EngineEvent` |
| dispatch scheduler lane acquire → recheck | PASS | `dispatch.py:540-577`：`_mark_dispatching_after_recheck` 在 lane acquired 后读取最新 Run/Attempt/dispatch 状态做 recheck |
| ATTEMPT_RUNNING 由 worker accept 后 append | PASS | `dispatch.py` 中 `_accept_worker_running` 在 worker accept 成功后追加 ATTEMPT_RUNNING |
| cancel 传播通过 ActiveWorkerRegistry | PASS | `dispatch.py:137-206`：`ActiveWorkerRegistry` 的 `cancel()` 调用 `cancellation_token.request_cancel` + `handle.cancel` |
| dispatch scheduler close 释放 lane | PASS | `dispatch.py:431-449`：`close()` 最后调用 `self._lane_controller.close(reason="scheduler_close")` |
| NoToolExecutor 返回 ToolCancelledOutcome | PASS | `run_input.py:506-530`：frozen dataclass，`execute` 返回 `ToolCancelledOutcome` |
| NoopMemorySnapshotProvider 返回空 | PASS | `run_input.py:451-465`：frozen dataclass，返回空 snapshot |
| NoopCompactArtifactProvider 返回空 | PASS | `run_input.py:468-486`：frozen dataclass，返回空 snapshot |

### Lens 6: 跨 phase 分层

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| Host 不 import config/fins/service/ui | PASS | `tests/host/test_import_boundary.py:112-122`：扫描全部 `dayu/host/**/*.py` |
| runtime 不 import host/engine/service/ui/fins | PASS | `tests/runtime/test_import_boundary.py:77-87`：扫描全部 `dayu/runtime/**/*.py` |
| Engine 不 import Host | PASS | `tests/host/test_import_boundary.py:156-169`：扫描全部 `dayu/engine/**/*.py` |
| Host→Engine 只通过允许模块 | PASS | `tests/host/test_import_boundary.py:125-137`：只允许 `api.py/dispatch.py/engine_ingest.py/local_proxy.py/run_input.py` |
| dayu.runtime 不承载业务语义 | PASS | `lane.py` 和 `filelock.py` docstring 明确声明层中立 |
| 第三方 filelock 只在 runtime wrapper | PASS | `tests/runtime/test_import_boundary.py:117-130`：扫描全部 `dayu/**/*.py` 除 `filelock.py` |

### Lens 7: 生产接线

| 接线项 | 结果 | 证据 |
| --- | --- | --- |
| durable store bootstrap | PASS | `connection.py` → `schema.py:bootstrap_host_durable_store` |
| transaction runner | PASS | `transaction.py:HostTransactionRunner` 使用 BEGIN IMMEDIATE + WAL + busy_timeout |
| EventLogStore | PASS | `event_log.py:EventLogStore` 提供 append/read primitive |
| idempotency | PASS | `idempotency.py:IdempotencyStore` 在 transaction 内写入/读取 |
| command facade | PASS | `command.py:create_host_command_handle` 组装 durable_store + admission_service |
| admission service | PASS | `admission.py:create_host_admission_service` 装配 EventLogStore + IdempotencyStore + clock + id_factory + wakeup_port |
| dispatch scheduler | PASS | `dispatch.py:HostDispatchScheduler.open()` 装配 lane_controller + transaction_runner + event_log_store |
| lane DB | PASS | `dispatch.py:336-358`：独立 runtime lane DB 路径，不复用 Host durable store |
| LocalProxy | PASS | `local_proxy.py:DefaultLocalEngineWorkerFactory` 创建 `DefaultLocalEngineWorker` |
| EngineEventIngestor | PASS | `engine_ingest.py:EngineEventIngestor` 接收 transaction_runner + event_log_store + payload_store + wakeup_port |
| queue promotion | PASS | `admission.py:595-618`：`promote_next_queued_run` + `_wake_dispatch_if_needed` |

### Lens 8: 后续 phase 预留

| 后续 Phase | 推迟项 | 当前处理 | owner |
| --- | --- | --- | --- |
| P6 | ToolRuntime / fetch_more | `NoToolExecutor` 返回 `ToolCancelledOutcome` | Phase 6 |
| P7 | WAITING / resolve_wait | `admission.py:2209-2210` WAITING/RECOVERING cancel → `None` → UNSUPPORTED_OPERATION | Phase 7 |
| P8 | Memory snapshot | `NoopMemorySnapshotProvider` 返回空 | Phase 8 |
| P9 | Context Governance | RunInputBuilder 构造 no-tool request | Phase 9 |
| P10 | Compact artifact | `NoopCompactArtifactProvider` 返回空 | Phase 10 |
| P11 | Recovery / takeover | `command.py:563-568` purge → UNSUPPORTED_OPERATION | Phase 11/15 |
| P12 | RemoteProxy | `WorkerKind` 含 `REMOTE`，P5 只用 `LOCAL` | Phase 12+ |
| P15 | purge_session | `command.py:520` → UNSUPPORTED_OPERATION | Phase 15 |

所有 noop provider 均为 frozen dataclass，返回类型安全的空值，不引入运行时副作用。`UNSUPPORTED_OPERATION` 消息明确标注后续 phase owner。

## Production Wiring Risks

无阻塞性生产接线风险。上一轮 controller adjudication 标记的 C1/C2 非阻塞 items 仍在：

| Risk | 来源 | Blocking |
| --- | --- | --- |
| durable helper `accept_worker_running_in_transaction` payload 弱于 scheduler 生产路径 | Controller C1 | No |
| `mark_dispatching_after_lane_row` 底层 helper 能力宽于生产路径 | Controller C2 | No |
| `DEFAULT_ACTIVE_WORKER_REGISTRY` 模块级 singleton | F1 本轮 | No |

## Residual Risks

| 风险 | owner | Blocking |
| --- | --- | --- |
| module-level active worker registry 跨 handle 共享 | Host dispatch hardening | No |
| terminal closeout 后 queue promotion wakeup failure 影响 worker event task | Host dispatch lifecycle hardening | No |
| active cancel watchdog / stuck CANCELLING | Phase 11 lifecycle / recovery hardening | No |
| LocalProxy cancel() no-op 依赖 Engine runner 观察 cancellation token | Engine runner integration + Phase 11 | No |
| explicit scheduler + command handle 两段式装配需更清晰 async composition entry | Host lifecycle composition | No |

## Covered Key Paths

审查实际覆盖的关键路径：

1. `dayu/runtime/lane.py` + `filelock.py` → import boundary → 层中立约束
2. `dayu/host/api.py` → 公共类型定义 → StrEnum/frozen dataclass/typed error
3. `dayu/host/durable/schema.py` → DDL → fresh bootstrap → PRAGMA user_version → partial unique index
4. `dayu/host/durable/transaction.py` → BEGIN IMMEDIATE → WAL → busy_timeout → after-commit
5. `dayu/host/durable/event_log.py` → append-only → event_id UNIQUE → event_sequence AUTOINCREMENT
6. `dayu/host/durable/idempotency.py` → (scope_kind, scope_id, idempotency_key) PK → semantic digest
7. `dayu/host/durable/state.py` → CAS transitions → rowcount check → DispatchRecordStatus docstring
8. `dayu/host/durable/run_transition.py` → terminal closeout → cancel queued → cancel pre-dispatch → promotion
9. `dayu/host/admission.py` → start_run → submit_followup_queue → cancel_run → cancel_session_runs → promotion
10. `dayu/host/command.py` → create_host_command_handle → UNSUPPORTED_OPERATION paths → active cancel propagation
11. `dayu/host/read_api.py` → get_session → get_run → stream_run_events (global cursor)
12. `dayu/host/dispatch.py` → HostDispatchScheduler → lane acquire → recheck → dispatch → ATTEMPT_RUNNING → close
13. `dayu/host/local_proxy.py` → DefaultLocalEngineWorker → accept → events stream
14. `dayu/host/engine_ingest.py` → LocalEngineEnvelope → EngineEventCandidate → terminal mapping
15. `dayu/host/run_input.py` → typed providers → NoToolExecutor → NoopMemorySnapshotProvider → StaticPolicySnapshot
16. `tests/host/test_import_boundary.py` → Host/engine/runtime import boundary coverage
17. `tests/runtime/test_import_boundary.py` → runtime 反向依赖 + filelock import 隔离
