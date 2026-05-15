# P1-P5 Design Conformance Review

## Scope

- Mode: Design conformance review (P1-P5 vs `docs/host/design.md`)
- Branch: `feat/host-phase5-local-dispatch`
- Review date: 2026-05-15
- Reviewer: AgentDS
- Output file: `docs/reviews/p1-p5-design-conformance-review-ds-20260515.md`
- Included scope: All P1-P5 implemented code across `dayu/host/`, `dayu/runtime/`, `dayu/engine/contracts/`, `dayu/engine/agent.py`
- Reference design: `docs/host/design.md` (真源)
- Reference control: `docs/host/implementation-control.md` (实现范围线索)
- Historical artifacts reviewed: `docs/reviews/p5-design-conformance-review-ds-20260515.md`, `docs/reviews/p5-design-conformance-review-controller-adjudication-20260515.md`

## Verdict

**PASS** — 无阻塞性设计偏离。P1-P5 当前全部代码实现与 `docs/host/design.md` 一致。分层边界清洁；Engine 不反向 import Host；`dayu.runtime` 层中立；Host 强约束 Agent/AsyncAgent/AsyncOpenAIRunner 生命周期与取消治理；dispatch record 未被误建成 owner/lease；后续 phase 能力未被提前硬编码。

## Coverage Summary

| # | 审查区域 | 结论 | 关键证据 |
|---|---------|------|---------|
| 1 | P1 公共契约与 runtime 边界 | PASS | 所有公共类型完整；`dayu.runtime` 零反向 import；无 Any/object 逃逸 |
| 2 | P2 durable store 与 EventLog | PASS | fresh schema (HOST_SCHEMA_VERSION=3)；event_sequence 全局单调；event_id 唯一；idempotency 正确 |
| 3 | P3 session/run/attempt/admission | PASS | active run partial unique index；CAS helpers 完整；session lifecycle 正确 |
| 4 | P4 public API command path | PASS | 完整 facade；unsupported operations 正确 gated；idempotency 正确 |
| 5 | P5 RunInputBuilder/local dispatch | PASS | 8 providers (4 real + 4 noop)；Host 拥有 lifecycle；EngineEvent 清洁 |
| 6 | 跨 phase 分层 | PASS | UI→Service→Host→Engine；Engine 零 Host import；runtime 层中立 |
| 7 | 生产接线 | PASS | 所有关键路径接到设计路径上 |
| 8 | 后续 phase 预留 | PASS | deferred owner 清晰；noop/stub/fail-fast 行为正确 |

## Detailed Findings

### 1. P1 — 公共契约与 Runtime 边界

#### 1.1 公共类型完整性 (PASS)

**`dayu/host/api.py`** — 所有设计要求的公共类型均已实现：

| 类型 | 文件:行号 | 形式 |
|------|----------|------|
| `HostCallContext` | api.py:589 | `@dataclass(frozen=True, slots=True)` |
| `OperationContext` | api.py:517 | `@dataclass(frozen=True, slots=True)` |
| `RunStatus` | api.py:162 | `StrEnum` (9 状态) |
| `AttemptStatus` | api.py:180 | `StrEnum` (8 状态) |
| `SessionStatus` | api.py:149 | `StrEnum` (OPEN/CLOSED) |
| `CancelMode` | api.py:208 | `StrEnum` (GRACEFUL) |
| `StartRunRequest` | api.py:984 | `@dataclass(frozen=True, slots=True)` |
| `RunSnapshot` | api.py:1357 | `@dataclass(frozen=True, slots=True)` |
| `SessionSnapshot` | api.py:1317 | `@dataclass(frozen=True, slots=True)` |
| `AttemptDispatchSnapshot` | api.py:240 | `@dataclass(frozen=True, slots=True)` |
| `HostEventStream` | api.py:1568 | `@dataclass(frozen=True, slots=True)` |
| `HostApiError` | api.py:1581 | `Exception` 子类 |
| `HostApiErrorCode` | api.py:465 | `StrEnum` (含 UNSUPPORTED_OPERATION) |

**`dayu/host/tooling.py`** — ToolBundle construction input 类型完整：

| 类型 | tooling.py:行号 |
|------|----------------|
| `ToolBundleSourceKind` | 23 (`StrEnum`) |
| `FrameworkToolName` | 36 (`StrEnum`, 含 FETCH_MORE) |
| `ToolBundleSourceRef` | 43 (`@dataclass(frozen=True, slots=True)`) |
| `HostToolingOptions` | 121 (`@dataclass(frozen=True, slots=True)`) |
| `FrameworkToolPolicyView` | 77 (`@dataclass(frozen=True, slots=True)`) |

#### 1.2 Runtime 边界 (PASS)

**`dayu/runtime/lane.py`** — 第一版实现与设计 §3.1 一致：
- `LaneConfig` (lane.py:66)、`SQLiteLaneCoordinatorConfig` (lane.py:145)、`LaneOwner` (lane.py:114)、`LaneController` (lane.py:343)、`LaneClaimToken` (lane.py:181)、`LaneAcquireOutcome` (lane.py:282)
- claim_id 为不可猜测随机 id (lane.py:598)
- 可取消 acquire；timeout 返回 `LaneAcquireTimedOut`；cancellation 优先于 timeout
- `LaneController.close()` 取消 pending acquire 并 best-effort release tokens
- stale claim cleanup 在 acquire 事务中执行 (lane.py:573)
- 独立 runtime SQLite lane DB，不复用 Host durable store

**`dayu/runtime/filelock.py`** — 与设计 §3.2 一致：
- `RuntimeFileLockOptions` (filelock.py:37)、`RuntimeFileLock` (filelock.py:111)、`RuntimeFileLockToken` (filelock.py:64)
- 同步 wrapper；第三方 `filelock.FileLock` 仅由 `dayu.runtime.filelock` import
- timeout error wrapping；幂等 release；parent directory creation

#### 1.3 无 Any/object/无类型签名逃逸 (PASS)

- `dayu/host/api.py`: 零 `Any`/`object` 作为类型签名；仅 docstring 中出现 `None` 描述
- `dayu/host/tooling.py`: 零 `Any`/`object`
- `dayu/runtime/lane.py`: 零 `Any`/`object`
- `dayu/runtime/filelock.py`: 零 `Any`/`object`
- `dayu/runtime/cancellation.py:287`: `_AnyTaskResult = TypeVar("_AnyTaskResult")` 为标准泛型 TypeVar 模式，非类型逃逸

#### 1.4 dayu.runtime 反向 import 检查 (PASS)

- `dayu/runtime/` 下所有 `.py` 文件零 `from dayu.engine` / `from dayu.host` / `from dayu.service` / `from dayu.ui` / `from dayu.fins` import
- 仅允许的跨包依赖：`dayu.contracts.cancellation.CancellationToken`（lane.py:24, cancellation.py:44）
- `dayu/runtime/__init__.py:10-12` docstring 明确记录了此约束

### 2. P2 — Durable Store 与 EventLog

#### 2.1 Fresh Schema (PASS)

- `HOST_SCHEMA_VERSION = 3` (schema.py:14)
- `bootstrap_host_durable_store()` (schema.py:490) 仅接受 version=0（全新）或 version=3（当前）；其他版本报 `HostSchemaMismatchError`
- 文档注释明确："不做兼容读取或迁移" (schema.py:497)
- 5 张 foundation tables + 5 张 Phase 3 state tables + 3 个索引全部通过 `CREATE TABLE IF NOT EXISTS` 创建

#### 2.2 EventLog Schema (PASS)

- `event_sequence INTEGER PRIMARY KEY AUTOINCREMENT` (schema.py:104) — 全局单调
- `event_id TEXT NOT NULL UNIQUE` (schema.py:105) — 全局唯一
- `event_class TEXT NOT NULL CHECK (event_class IN ('canonical_fact', 'preview', 'diagnostic', 'projection_signal'))` (schema.py:107-113)
- 外键 `payload_ref REFERENCES payload_descriptors(payload_ref)` (schema.py:131)
- CHECK 约束 `payload_ref IS NULL OR payload_digest IS NOT NULL` (schema.py:132)

#### 2.3 EventLog Append/Read 语义 (PASS)

- `append_event()` (event_log.py:265): 在调用方事务内执行；event_id 重复检测；相同 event_id + 相同 body → 幂等返回 `inserted=False`；相同 event_id + 不同 body → `HostEventIdentityConflictError`
- `read_events_after()` (event_log.py:390): `WHERE event_sequence > ? ORDER BY event_sequence ASC LIMIT ?` — 全局 cursor 分页

#### 2.4 Idempotency Primitive (PASS)

- `(scope_kind, scope_id, idempotency_key)` 三元素复合主键 (schema.py:147)
- 同 key + 同 digest → 幂等返回既有结果 (idempotency.py:148-153)
- 同 key + 不同 digest → `HostIdempotencyConflictError`
- `IdempotencyRecord` 保存 `semantic_input_digest`, `result_kind`, `result_ref`, `created_event_id`, `created_event_sequence`

#### 2.5 Transaction Runner (PASS)

- `HostTransactionRunner.run_write()` (transaction.py:212): `BEGIN IMMEDIATE`；指数退避重试仅针对 busy/locked；唯一约束/外键/CAS precondition failed 不重试
- `configure_connection_pragmas()` (transaction.py:291): `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout`
- `AfterCommitCallback` (transaction.py:38): 仅在 commit 成功后执行

#### 2.6 Host Instance Liveness (PASS)

- `HostInstanceStatus` (liveness.py:33): `RUNNING`, `STOPPING`, `STOPPED`, `CRASHED_SUSPECTED`
- `register_current_instance()` (liveness.py:179), `heartbeat_current_instance()` (liveness.py:254)
- 生命周期状态机：仅 `RUNNING` → `STOPPING` → `STOPPED` 或 `CRASHED_SUSPECTED`
- Phase 2 仅实现 register/heartbeat/read；不实现 positive orphan proof classifier（属于 Phase 11）

#### 2.7 Payload Foundation (PASS)

- `PayloadKind` (payload.py:41): `SQLITE_PAYLOAD`, `ARTIFACT_REF`
- `PayloadDescriptor` (payload.py:89): `payload_ref`, `payload_kind`, `payload_digest`, `payload_size_bytes`, ...
- 大 payload 走 artifact 路径：先 durable 写入 artifact root，digest verify，atomic rename，再在 SQLite transaction 中写 descriptor

### 3. P3 — Session/Run/Attempt 与 Admission

#### 3.1 Active Run Invariant (PASS)

- 部分唯一索引 (schema.py:442-446):
  ```sql
  CREATE UNIQUE INDEX IF NOT EXISTS host_runs_one_active_per_session
  ON host_runs(session_id)
  WHERE status IN ('running', 'waiting', 'cancelling', 'recovering')
  ```
- SQLite 内核级保证每 Session 至多一个 active Run
- 应用层 `promote_queued_run_row` (state.py:1454-1460) 额外使用 `NOT EXISTS` 子查询做 defense-in-depth

#### 3.2 DispatchRecordStatus 枚举 (PASS)

- `PENDING`, `WAITING_FOR_LANE`, `DISPATCHING`, `CANCELLED` (state.py:58-61)
- 4 状态 CHECK 约束 (schema.py:380-439)：每个状态强制正确的字段存在/缺失模式
- `DispatchRecordRow` docstring (state.py:52-55) 明确声明不是 lease/fencing

#### 3.3 CAS Helpers (PASS)

所有关键 CAS 辅助函数均已实现：

| Helper | state.py 行号 | 前置条件 |
|--------|-------------|---------|
| `promote_queued_run_row` | 1410-1485 | status=QUEUED + NOT EXISTS active |
| `cancel_queued_run_row` | 1488-1541 | status=QUEUED |
| `cancel_running_run_row` | 1544-1603 | status=RUNNING + current_attempt_id |
| `cancel_cancelling_run_row` | 1606-1667 | status=CANCELLING |
| `mark_run_cancelling_row` | 1669-1717 | RUNNING → CANCELLING |
| `terminal_run_row` | 1720-1789 | RUNNING/WAITING → terminal |
| `cancel_starting_attempt_row` | 1856-1909 | status=STARTING |
| `cancel_running_attempt_row` | 1912-1967 | status=RUNNING |
| `mark_attempt_running_row` | 1970-2013 | STARTING → RUNNING |
| `terminal_attempt_row` | 1792-1853 | STARTING/RUNNING → terminal |
| `mark_dispatch_worker_accepted_row` | 2174-2228 | status=DISPATCHING |
| `cancel_starting_dispatch_record_row` | 2231-2316 | PENDING/WAITING_FOR_LANE/DISPATCHING |

所有 helper 使用 `rowcount=0` 判定 CAS 失败，不无条件覆盖最新状态。

#### 3.4 Session Lifecycle (PASS)

- `ensure_session()` (session_lifecycle.py:95): `(scope, slot_key)` 幂等映射；并发重复调用由唯一约束保护，输方重新读取 winning binding
- `create_session()` (session_lifecycle.py:113): `client_request_id` 幂等
- `close_session()` (session_lifecycle.py:142): 仅关闭新输入入口，不 cancel、不终止已有 Run
  - **设计确认**: 设计 §5 明确 "close_session 只关闭 Session 的新输入入口，不取消、不终止、不删除已有 Run"，因此 close_session 不检查 active Run 是正确的设计行为

#### 3.5 Admission Service (PASS)

- `HostAdmissionService.start_run()` (admission.py:413): 检查 active Run → REJECT/QUEUE/ATTACH_ACTIVE 三向策略分发
- `AdmissionWakeupPort` Protocol (admission.py:145-162): `wake_dispatch` + `wake_queue_promotion`
- Queue promotion: FIFO 按 accepted `event_sequence` 排序；CAS 保护；仅无 active Run 时推进

#### 3.6 Run Transition Functions (PASS)

所有关键 transition 函数均已实现 (run_transition.py)：

| 函数 | 行号 |
|------|------|
| `create_queued_run_in_transaction` | 451 |
| `create_running_run_with_starting_attempt_in_transaction` | 511 |
| `promote_queued_run_in_transaction` | 590 |
| `terminal_closeout_in_transaction` | 672 |
| `active_cancel_closeout_in_transaction` | 751 |
| `accept_worker_running_in_transaction` | 833 |
| `cancel_queued_in_transaction` | 902 |
| `cancel_predispatch_starting_in_transaction` | 964 |
| `request_active_attempt_cancel_in_transaction` | 1077 |

#### 3.7 cancel_session_runs WAITING/RECOVERING 检查 (PASS)

- `_session_cancel_target_for_run` (admission.py:2191-2250): 第 2209 行对 `WAITING`/`RECOVERING` 返回 `None`
- `_read_supported_targets_or_raise` (admission.py:1325-1349): target 为 `None` 时抛出 `UNSUPPORTED_OPERATION`
- WAITING/RECOVERING 无 partial mutation — 确认符合设计

### 4. P4 — Public API Command Path

#### 4.1 Command Facade (PASS)

`dayu/host/command.py` — 所有公共 facade 函数完整：

| 函数 | command.py 行号 | 状态 |
|------|----------------|------|
| `ensure_session` | 228 | 完整实现 |
| `create_session` | 243 | 完整实现 |
| `close_session` | 268 | 完整实现 |
| `start_run` | 294 | 完整实现 |
| `submit_followup` | 311 | 完整实现 (queue)；steer → UNSUPPORTED |
| `cancel_run` | 361 | 完整实现 (queued + pre-dispatch starting) |
| `cancel_session_runs` | 412 | 子集实现 (queued + pre-dispatch starting) |
| `retry_run` | 453 | UNSUPPORTED_OPERATION (line 467) |
| `replay_run` | 469 | UNSUPPORTED_OPERATION (line 484) |
| `resolve_wait` | 487 | UNSUPPORTED_OPERATION (line 501) |
| `purge_session` | 504 | UNSUPPORTED_OPERATION (line 520) |

#### 4.2 HostCommandHandle (PASS)

- `create_host_command_handle()` (command.py:195-225): 拒绝 `local_execution` (line 207-211)，指导显式 open `HostDispatchScheduler`
- 这是刻意的生命周期边界 — `create_host_command_handle` 是同步 facade，不隐式持有 async scheduler lifecycle

#### 4.3 Active Cancel Propagation (PASS)

- `_propagate_active_cancel_targets` (command.py:814-825): post-commit 遍历 `ActiveCancelMessage` 并调用 `cancel_active_worker`
- `ActiveCancelMessage` (dispatch.py:108-120): 携带 `run_id`, `attempt_id`, `execution_id`, `reason`

#### 4.4 公共导出清洁 (PASS)

- `dayu/host/__init__.py` `__all__` (line 83-152): 72 个符号
- 不导出 durable 内部类型 (`HostTransaction`, `EventLogRow`, `HostDurableError` 等)
- 不导出 dispatch 内部类型 (`ActiveCancelMessage`, `cancel_active_worker`)
- 不导出 admission 内部类型 (`AdmissionWakeupPort`)

### 5. P5 — RunInputBuilder 与 Local Dispatch

#### 5.1 RunInputBuilder Provider Set (PASS)

- 8 个 typed providers (run_input.py:624-713): 4 real + 4 noop
  - Real: `DurableCurrentRunFactProvider`, `DurableSessionContinuityProvider`, `DefaultSceneParameterProvider`, `StaticPolicySnapshotProvider`
  - Noop: `NoopMemorySnapshotProvider`, `NoopCompactArtifactProvider`, `NoopToolSchemaSnapshotProvider`, `NoToolExecutorProvider`

#### 5.2 Messages 构造从 EventLog Facts (PASS)

- `DurableCurrentRunFactProvider` (run_input.py:300-392): 从 EventLog 读取 `USER_INPUT_ACCEPTED`，不读取 UI 临时文本
- Session continuity (run_input.py:861-961): 从 `read_run_input_continuity_events` 读取 EventLog，投影 `UserMessage` + `AssistantMessage` pair
- 所有 provider 只读 durable facts；不访问 UI/Service 临时状态或全局配置

#### 5.3 EngineEvent 契约清洁 (PASS)

- `EngineEvent` (engine_events.py:429-448): 字段为 `occurred_at`, `session_id`, `run_id`, `type`, `data`, `metadata`
- **零** `attempt_id`, `execution_id`, `dispatch_record_id` — 符合设计 §17
- Host identity 由 `LocalEngineEnvelope` (engine_ingest.py:123-146) 承载: `session_id`, `run_id`, `attempt_id`, `execution_id`, `dispatch_record_id`, `worker_kind`, `execution_target`, `local_worker_id`

#### 5.4 Dispatch Scheduler (PASS)

- `HostDispatchScheduler.open()` (dispatch.py:318-370): 创建 `LaneController`，注册 host instance，配置 lane configs
- `HostDispatchScheduler.close()` (dispatch.py:431-449): 取消 active workers，close lane controller
- `_dispatch_one()` (dispatch.py:465-508): pending → waiting_for_lane → lane acquire → durable recheck → dispatching → pre-accept recheck → start worker
- Lane token release 仅在 scheduler/worker finally (dispatch.py:916-923): finally 中 `_safe_release_lane_token`

#### 5.5 Host 拥有 Agent/AsyncAgent/AsyncOpenAIRunner 生命周期 (PASS)

- `_start_worker` (dispatch.py:601): 调用 `worker_factory.create_worker(snapshot)` → `worker.accept(snapshot, request)`
- `DefaultLocalEngineWorker.accept()` (local_proxy.py:40-59): 创建 `_DefaultLocalWorkerHandle`
- `_DefaultLocalWorkerHandle.events()` (local_proxy.py:92-103): 惰性调用 `run_agent_messages(self._request)` (dayu/engine/agent.py)
- Host 通过 dispatch scheduler → LocalProxy → Engine 入口间接拥有整个 Agent/AsyncOpenAIRunner 生命周期
- Cancel 传播通过 `ActiveWorkerRegistry` → `CancellationToken` → Engine 的 run-local cancellation token

#### 5.6 EngineEvent Ingest 映射 (PASS)

| EngineEvent | Host EventLog 映射 | engine_ingest.py 行号 |
|-------------|-------------------|---------------------|
| `final_answer` | `ATTEMPT_SUCCEEDED` + `RUN_SUCCEEDED` | 388-395 |
| `run_failed` (non-recoverable) | `ATTEMPT_FAILED` + `RUN_FAILED` | 423-427 |
| `run_failed` (recoverable) | diagnostic + `ATTEMPT_FAILED` + `RUN_FAILED` | 396-422 |
| `run_cancelled` | `ATTEMPT_CANCELLED` + `RUN_CANCELLED` | 428-431 |
| `tool_awaiting` / `run_suspended` | diagnostic + `ATTEMPT_FAILED` + `RUN_FAILED` (unsupported_waiting_path, owner=phase7) | 717-745 |
| `context_compaction_requested` | diagnostic + `ATTEMPT_FAILED` + `RUN_FAILED` (unsupported_recovery_policy, owner=phase10) | 432-449 |
| `usage_reported` | `PROJECTION_SIGNAL` (event_type=USAGE_REPORTED) | 466-470 |

#### 5.7 Terminal Closeout Policy (PASS)

| 场景 | Attempt | Run | dispatch.py / engine_ingest.py 行号 |
|------|---------|-----|----------------------------------|
| Clean EOF 无 terminal event | FAILED | FAILED | engine_ingest.py stream_ended_without_terminal |
| Worker crash/stream error | LOST | LOST | engine_ingest.py worker_lost_before_terminal |
| Worker startup failed/rejected | FAILED | FAILED | dispatch.py:500-508 |
| Pre-call recheck 失败 | 不新增 | 不新增 | dispatch.py:496-498 |

#### 5.8 Queue Promotion Wakeup (PASS)

- `_with_terminal_promotion_retry` (engine_ingest.py:810-832): terminal closeout 后调用 `wakeup_port.wake_queue_promotion(session_id)`
- `wake_queue_promotion` (dispatch.py:386-399): 创建 admission service 并 promote
- Scheduler 作为 `AdmissionWakeupPort` 传入 `EngineEventIngestor` (dispatch.py:858)

### 6. Cross-Phase Layering

#### 6.1 依赖方向 (PASS)

- **Engine → Host**: 零 import (全量 dayu/engine/ 搜索确认)
- **Host → Service/UI/Fins**: 零 import (全量 dayu/host/ 搜索确认)
- **dayu.runtime → Engine/Host/Service/UI/Fins**: 零 import
- **dayu.contracts → Engine/Host/Service/UI/Fins**: 零 import

#### 6.2 Host → Engine 依赖 (PASS, 仅在允许路径)

- `dayu/host/api.py`: import `dayu.engine.contracts.agent_policy`, `agent_run`, `engine_events`, `runner_spec` — 仅类型
- `dayu/host/engine_ingest.py`: import `dayu.engine.contracts.engine_events` — 仅类型
- `dayu/host/run_input.py`: import `dayu.engine.contracts.*` — 仅类型
- `dayu/host/local_proxy.py`: import `dayu.engine.run_agent_messages` — 执行入口
- 以上均为设计允许的下行依赖路径

#### 6.3 dayu.runtime 无业务语义 (PASS)

- `dayu/runtime/lane.py`: 仅资源容量协调，不表达 Session/Run/Attempt owner
- `dayu/runtime/filelock.py`: 仅文件互斥 wrapper，不表达 Host durable truth
- 零 Host/Engine/财报业务语义 leak

#### 6.4 财报文档路径 (N/A)

- `dayu/fins/` 包尚未实现；无财报文档存取路径需要检查
- 当前代码库中无直接财报文件 I/O 操作

### 7. Production Wiring

| # | 接线项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | Durable store bootstrap + transaction runner | PASS | schema.py:490 + transaction.py:190 |
| 2 | EventLogStore append/read | PASS | event_log.py:265/390 |
| 3 | Idempotency store | PASS | idempotency.py:127/189 |
| 4 | Command facade → admission → transition | PASS | command.py→admission.py→run_transition.py |
| 5 | Admission → queue promotion | PASS | admission.py→run_transition.py:590 |
| 6 | Dispatch scheduler → lane → LocalProxy | PASS | dispatch.py:465-508 |
| 7 | LocalProxy → Engine (run_agent_messages) | PASS | local_proxy.py:92→engine/agent.py |
| 8 | EngineEventIngestor → terminal closeout | PASS | engine_ingest.py:388-470 |
| 9 | Terminal closeout → queue promotion wakeup | PASS | engine_ingest.py:810→dispatch.py:386 |
| 10 | Active cancel → worker propagation | PASS | command.py:814→dispatch.py:265 |
| 11 | Lane DB 独立于 Host durable DB | PASS | lane.py coordinator 独立 SQLite 文件 |
| 12 | Host instance liveness register/heartbeat | PASS | liveness.py:179/254 |

### 8. Future Phase Readiness

逐项检查 P6+ 能力是否未被提前错误实现：

| # | 后续能力 | P5 状态 | Owner | 证据 |
|---|---------|---------|-------|------|
| 1 | ToolRuntime/fetch_more | 未实现 | Phase 6 | NoToolExecutor (run_input.py:506-531) 返回 ToolCancelledOutcome |
| 2 | WAITING/resolve_wait | 未实现 | Phase 7 | tool_awaiting → diagnostic + FAILED，reason=unsupported_waiting_path (engine_ingest.py:717) |
| 3 | Memory projection | 未实现 | Phase 9 | NoopMemorySnapshotProvider (run_input.py:451-465) 返回空 stable layer |
| 4 | Context Governance/Compaction | 未实现 | Phase 10 | context_compaction → diagnostic + FAILED，reason=unsupported_recovery_policy (engine_ingest.py:432) |
| 5 | Recovery/takeover | 未实现 | Phase 11 | clean EOF → FAILED；worker crash → LOST；不创建 RECOVERING |
| 6 | RemoteProxy | 未实现 | Phase 14 | 仅 LocalProxy；WorkerKind.REMOTE 枚举存在但生产路径未使用 |
| 7 | Observer/Sink/Projection | 未实现 | Phase 8/13 | usage_reported → projection_signal，无 projection worker |
| 8 | retry/replay/steer/resolve_wait | stable unsupported | 各后续 phase | command.py:453-520 返回 UNSUPPORTED_OPERATION |
| 9 | purge_session | stable unsupported | Phase 15 | command.py:504-520 返回 UNSUPPORTED_OPERATION |
| 10 | ToolsDiscovery/ScenePrepare | border defined | Phase 12 | tooling.py 仅定义 import boundary；无具体实现 |

**结论**: 无提前硬编码的后续 phase 能力。所有 deferred 项均有明确 owner (phase6-15)，stub/noop/fail-fast 行为正确。

### 9. Non-blocking Findings

#### 9-NB-1: durable helper `accept_worker_running_in_transaction` ATTEMPT_RUNNING payload 弱于 scheduler 生产路径

- **来源**: 上轮 AgentDS Finding 1 + Controller C1
- **当前状态**: 未修复，但非阻塞
- **证据**:
  - 生产路径 `HostDispatchScheduler._accept_worker_running` (dispatch.py) 通过 scheduler 内部 `_attempt_running_event_request` 构建完整 payload
  - durable helper `accept_worker_running_in_transaction` (run_transition.py:833-899) 通过 `_attempt_running_event_request` (run_transition.py:1465-1506) 构建 payload，缺少 `local_worker_id`, `worker_accepted_at`, `lane_name`, `lane_claim_id` 字段
  - 当前生产 scheduler 未调用 durable helper 版本的 `accept_worker_running_in_transaction`
- **影响**: 不破坏 P5 生产接线与治理真源。同名 canonical fact 在不同 helper 路径上诊断字段不一致；后续维护者若误用 durable helper 可能写出弱诊断 `ATTEMPT_RUNNING`
- **严重程度**: non-blocking hardening
- **Owner**: Host durable transition hardening

#### 9-NB-2: `mark_dispatching_after_lane_row` 能力宽于生产 scheduler 路径

- **来源**: 上轮 AgentCodex Finding 2 + Controller C2
- **当前状态**: 未修复，但非阻塞
- **证据**: `mark_dispatching_after_lane_row` (state.py) 允许 `PENDING` 或 `WAITING_FOR_LANE` 进入 `DISPATCHING`；生产 scheduler 仅使用 `WAITING_FOR_LANE → DISPATCHING` 路径
- **影响**: 当前生产路径不偏离 design。底层 helper 对未来调用方暴露更宽能力
- **严重程度**: non-blocking hardening
- **Owner**: Host durable API tightening

#### 9-NB-3: compact artifact message slot 位置与 plan 摘要顺序不完全一致

- **来源**: 上轮 AgentDS Finding 2 + Controller C3
- **当前状态**: 已裁决为 non-blocking
- **证据**: run_input.py:693 `*compact.messages` 位于 memory 与 continuity 之间；Phase 5 plan 摘要未列出该 noop slot
- **影响**: P5 compact provider 为 noop，运行时无实际影响
- **严重程度**: non-blocking doc clarification
- **Owner**: Phase 10 / RunInputBuilder doc cleanup

### 10. Residual Risks

| # | 风险 | Owner | Blocking |
|---|------|-------|----------|
| 1 | durable helper `accept_worker_running_in_transaction` payload diagnostics 弱于 scheduler 生产路径 | Host durable transition hardening | No |
| 2 | `mark_dispatching_after_lane_row` 底层 helper 能力宽于生产路径 | Host durable API tightening | No |
| 3 | 多进程 orphan proof 未实现 | Phase 11 | No |
| 4 | active cancel 超时 watchdog 未实现 | Phase 11 | No |
| 5 | 真实 provider/network smoke 未测试 | 集成环境 | No |
| 6 | cancel_session_runs RECOVERING 测试缺口 | P5 自身 | No |
| 7 | durable recheck CAS loser 测试缺口 | P5 自身 | No |
| 8 | Usage projection worker/audit sink 未实现 | Phase 13 | No |
| 9 | terminal closeout 后 queue promotion wakeup failure 影响 worker event task 诊断 | Host dispatch lifecycle hardening | No |

## Architecture Boundary Verification

| # | 检查项 | 结果 | 证据 |
|---|--------|------|------|
| 1 | EngineEvent 不含 Host identity | PASS | engine_events.py:429-448 — 零 attempt_id/execution_id/dispatch_record_id |
| 2 | UI→Service→Host→Engine 依赖方向 | PASS | 零反向 import |
| 3 | dayu.runtime 层中立 | PASS | 零 import from engine/host/service/ui/fins |
| 4 | Host __init__.py 导出清洁 | PASS | 仅公共类型与 facade；零 durable 内部类型泄露 |
| 5 | Dispatch record 非 lease/fencing | PASS | state.py:52-55 docstring 明确声明；所有 CAS helper 只做状态迁移 |
| 6 | LocalProxy envelope 承载 Host identity | PASS | engine_ingest.py:123-146 `LocalEngineEnvelope` 包含 session_id/run_id/attempt_id/execution_id/dispatch_record_id |
| 7 | RunInputBuilder 只读 durable facts | PASS | 所有 provider 从 EventLog/Run/Attempt 行读取 |
| 8 | Host 不 import fins/service/ui | PASS | 全量 import 检查零违规 |
| 9 | Engine 不 import Host | PASS | 全量 import 检查零违规 |
| 10 | 财报文档路径走 dayu.fins.storage | N/A | dayu/fins/ 包尚未实现 |

## Evidence by File/Line

| 文件 | 关键行号 | 审查结论 |
|------|---------|---------|
| dayu/host/api.py | 149, 162, 180, 208, 240, 465, 517, 589, 699, 984, 1317, 1357, 1568, 1581 | 公共类型完整 |
| dayu/host/tooling.py | 23, 36, 43, 77, 104, 121 | ToolBundle construction input 完整 |
| dayu/runtime/lane.py | 66, 114, 145, 181, 282, 343, 573 | LaneController 实现与设计一致 |
| dayu/runtime/filelock.py | 37, 64, 111, 201 | FileLock wrapper 与设计一致 |
| dayu/host/durable/schema.py | 14, 104-105, 107-113, 131-132, 136-151, 153-165, 167-439, 442-446, 490, 497 | HOST_SCHEMA_VERSION=3；fresh schema；DDL 完整 |
| dayu/host/durable/event_log.py | 56, 69, 111, 159, 171, 265, 390 | EventLog append/read 语义正确 |
| dayu/host/durable/idempotency.py | 28, 42, 58, 83, 127, 189 | 幂等 primitive 正确 |
| dayu/host/durable/transaction.py | 38, 125, 190, 212, 266, 291 | BEGIN IMMEDIATE；WAL；busy retry |
| dayu/host/durable/liveness.py | 33, 59, 75, 96, 179, 254 | Host instance liveness 正确 |
| dayu/host/durable/payload.py | 41, 48, 89, 130 | Payload foundation 正确 |
| dayu/host/durable/state.py | 50-61, 64-68, 87-205, 762-816, 1410-1485, 1488-2316 | DispatchRecordStatus；CAS helpers |
| dayu/host/durable/run_transition.py | 91-414, 451, 511, 590, 672, 751, 833, 902, 964, 1077, 1465 | Transition inputs + functions |
| dayu/host/durable/session_lifecycle.py | 95, 113, 142, 360 | Session lifecycle 正确 |
| dayu/host/admission.py | 145-162, 394, 413, 526, 621, 665, 1238, 2191, 2209 | Admission + cancel_session_runs |
| dayu/host/command.py | 92, 195, 207, 228, 243, 268, 294, 311, 335, 361, 412, 453, 469, 487, 504, 814 | Command facade 完整 |
| dayu/host/dispatch.py | 108-120, 137, 265, 318, 386, 431, 465, 601, 827, 916 | Dispatch scheduler + worker lifecycle |
| dayu/host/local_proxy.py | 26, 40, 92, 105 | LocalProxy/EngineWorker |
| dayu/host/engine_ingest.py | 123, 217, 388, 423, 428, 432, 450, 466, 717, 810 | EngineEvent ingest 映射 |
| dayu/host/run_input.py | 300, 451, 506, 624, 661, 688 | RunInputBuilder + 8 providers |
| dayu/engine/contracts/engine_events.py | 33, 56-425, 429, 451 | EngineEvent 清洁 |
| dayu/engine/agent.py | run_agent_messages | Engine 执行入口 |
| dayu/host/__init__.py | 83-152 | 公共导出清洁 |

## Conclusion

P1-P5 全部代码实现与 `docs/host/design.md` 一致。0 blocking design deviations。3 non-blocking findings (全部来自上轮已记录项)。9 residual risks 均有 owner。所有分层边界清洁。Host 对 Agent/AsyncAgent/AsyncOpenAIRunner 生命周期与取消治理保持强约束。EngineEvent 契约保持清洁。后续 phase 能力未被提前硬编码。

**可进入下一 phase 或 PR review。**
