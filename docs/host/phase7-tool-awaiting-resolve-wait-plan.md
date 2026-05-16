# Host Phase 7 Tool Awaiting / resolve_wait / Wait Adapter Plan

- **current gate**: Phase 7 handoff implementation-ready plan
- **work unit**: Tool Awaiting / `resolve_wait` / Wait Adapter
- **plan status**: implementation-ready
- **blocking question count**: 0
- **artifact path**: `docs/host/phase7-tool-awaiting-resolve-wait-plan.md`

本文档是 Gateflow-governed handoff plan。implementation agent 只能按本文档指定的 contract、文件边界、slice、测试和 stop condition 实施；不得重新设计 Host / Engine 分层、外部 callback 产品化入口、RemoteProxy 自治 resume、retry / replay、recovery dispatch、projection / tool trace read model 或业务工具发现机制。

## 1. Goal / Motivation / Non-goals

### 1.1 Goal

Phase 7 落地长事务工具等待的 Host canonical path：`ToolAwaitingOutcome` 由 ToolRuntime Host accept path 接收并创建 wait record，使 Run 进入 `WAITING`、当前 Attempt 进入 `SUSPENDED`；等待完成后所有 poll / callback / manual 来源统一调用短事务 `resolve_wait`，由 Host 关闭 wait record、写入等待结果事实，并按 outcome 创建 resume Attempt 或终态收口。

同时落地第一版 poll / manual adapter、`WAITING` cancel、late result diagnostic、run-local duplicate governance 跨 resume Attempt 复用，以及 Engine `tool_awaiting` / `run_suspended` 的 diagnostic / idempotent confirmation 边界。

### 1.2 Motivation Judgment

动机成立，严重性评估没有被高估。

Phase 6 已完成 ToolRuntime accept barrier 和 run-local duplicate governance，但当前 `ToolAwaitingOutcome` 仍被降级为 `unsupported_awaiting` governed error，`resolve_wait` 仍是 stable unsupported public function。若 Phase 7 不把 wait record、resolution CAS、late result diagnostic 和 resume Attempt 原子边界固定下来，implementation agent 会被迫自行决定等待结果是否可信、谁能让 Run 进入 `WAITING`、cancel 与 resolve 竞态谁赢、以及 Engine 事件能否反向拥有 Host 状态。这些都是 Host 强约束治理问题，必须在 plan gate 收敛。

### 1.3 Non-goals

Phase 7 不做以下事项：

- 不实现专属 HTTP callback endpoint、callback authentication、外部协议重放防护或外部系统专属 callback adapter；只保留 callback source 和 common `resolve_wait` pipeline contract。
- 不保证外部 job physical cancel / revoke；adapter 只能 best-effort cancel / revoke / abandon，不能影响 Host terminal correctness。
- 不实现 RemoteProxy / remote worker 自治 resume。
- 不实现 retry / replay / steer / recovery dispatch / watchdog hardening / orphan recovery。
- 不实现完整 tool trace projection、audit projection、read model 或 event stream projection；Phase 7 只写必要 EventLog canonical / diagnostic facts。
- 不修改 Engine contract，不让 Engine 选择 Host adapter，不让 Engine 读取 wait record。
- 不把 adapter object、callable、外部系统私有 payload 或无结构 metadata bag 写入 durable wait record。
- 不做旧库兼容读取、旧 schema migration、兼容 wrapper / facade / re-export。

## 2. Direct Evidence

- `docs/host/implementation-control.md` Phase 7 目标明确要求实现长事务等待进入 Host 的 canonical path、wait record、`resolve_wait`、poll / manual adapter 最小能力与 `WAITING` resume。
- `docs/host/implementation-control.md` Phase 7 进入条件明确 `ResolveWaitRequest.outcome_ref` 必须替换为强类型等待结果 envelope，至少区分 completed / failed / cancelled / lost。
- `docs/host/implementation-control.md` Phase 7 验证要求包含 wait record state machine、`resolve_wait` idempotency、late result rejection、cancel-vs-resolve first-committer-wins、poll adapter observes cancelled wait and stops / abandons observation、late diagnostic EventLog event。
- `docs/host/design.md` §20 明确 ToolRuntime Host accept path 是 awaiting canonical owner；Engine `tool_awaiting` / `run_suspended` 不能创建 wait record、不能把 Run 推入 `WAITING`、不能关闭 Attempt、不能追加第二份 awaiting canonical facts。
- `docs/host/design.md` §20 明确 wait record 是 Host durable state index，负责 active wait 查询、adapter observation 恢复、取消 CAS、resolution CAS 与 late result 拒绝；EventLog 仍是 canonical facts truth。
- `docs/host/design.md` §20 明确 `resolve_wait(wait_id, request) -> RunSnapshot`，request 必须携带 `source`、`idempotency_key`、`observed_at` 与强类型等待结果 envelope；`resolve_wait` 是短事务 command，不等待外部长事务完成。
- `docs/host/design.md` §20 明确 `resolve_wait` 幂等范围是 `(wait_id, idempotency_key)`；同 key 同 outcome 返回既有 refs，不追加第二份 canonical fact，不创建第二个 Attempt；同 key 不同 outcome 返回 `idempotency_conflict`。
- `docs/host/design.md` §20 / §22 明确 `cancelled` / `lost` wait record 的迟到 poll / callback / manual result 不得作为 `canonical_fact`，必须至少追加 `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event。
- `docs/host/design.md` §21 明确 resume 是同一 Run 内的新 Attempt，不恢复旧 Attempt，也不让旧模型进程继续执行；RunInputBuilder 必须从 EventLog canonical facts 重建 messages，并让同 Run duplicate governance 跨 Attempt 生效。
- `docs/host/design.md` §22 明确 `WAITING` Run 被取消时，Host append `CANCEL_REQUESTED`，CAS 标记该 Run 下所有 active `status=waiting` wait records 为 `cancelled`，append `RUN_CANCELLED`，不创建 resume Attempt。
- `docs/reviews/host-phase7-design-discussion-codex-20260516.md` 已确认 D1-D4：typed outcome envelope、typed durable wait record、callback 只预留 contract、`WAITING` cancel 后 late result 只能 diagnostic / tool trace。
- `docs/reviews/host-phase7-design-fix-re-review-controller-adjudication-20260516.md` 确认两路 re-review PASS，并要求本 plan 逐项覆盖 outcome envelope、`observed_at`、lost 区分、`adapter_key` 来源、typed refs、late diagnostic schema、cancel-vs-resolve、poll adapter cancelled behavior。
- 当前代码中 `dayu/host/api.py` 的 `ResolveWaitRequest` 仍含 `outcome_ref: str` 和 `observed_at: str`，必须按 Phase 7 public API text 改为 typed envelope 与明确时间类型。
- 当前代码中 `dayu/host/command.py` 的 `resolve_wait` 仍始终返回 `UNSUPPORTED_OPERATION`，不打开 transaction、不追加 EventLog、不写 idempotency record。
- 当前代码中 `dayu/host/tool_runtime.py` 的 `ToolAwaitingOutcome` 仍被 `_normalize_runtime_outcome` 降级为 `unsupported_awaiting` governed error。
- 当前代码中 `dayu/host/engine_ingest.py` 对 Engine `RUN_SUSPENDED` / `TOOL_AWAITING` 仍写 diagnostic 后把 Run 收口为 failed；Phase 7 后这两类 EngineEvent 只能作为已接受 refs 的 diagnostic / idempotent confirmation，不能拥有 waiting 状态迁移。
- 当前代码中 `dayu/host/durable/state.py` 已有 `RunStatus.WAITING`、`AttemptStatus.SUSPENDED` 和 `terminal_run_row` 对 `WAITING` 源状态的预留，但没有 wait record table、status codec 或 CAS helper。

## 3. Public / Internal Contract Decisions

### 3.1 Layer Boundary

Host 是等待治理 owner。ToolRuntime accept path 创建 wait record 和 `WAITING` truth；Engine 只能通过 `ToolExecutor` 观察 accepted ack，不能创建或恢复 Host wait state。Poller、callback handler、manual admin 入口都只能调用 `resolve_wait`，不得直接更新 Run / Attempt / EventLog / wait record terminal state。

`dayu.runtime` 不承载任何 Phase 7 业务语义。新增 wait record、adapter registry、resolution pipeline、WAITING cancel 均属于 `dayu.host`。

### 3.2 `ResolveWaitRequest` Typed Outcome Envelope

`ResolveWaitRequest.outcome_ref: str` 必须删除并替换为 `outcome: ResolveWaitOutcome`。`ResolveWaitOutcome` 是封闭联合，不使用 `Any` / `object` / dict bag：

- `ResolveWaitCompletedOutcome`
  - `result: ToolResultSuccess`
  - `payload_ref: HostPayloadRef | None`
- `ResolveWaitFailedOutcome`
  - `result: ToolResultFailure`
  - `payload_ref: HostPayloadRef | None`
- `ResolveWaitCancelledOutcome`
  - `result: ToolCancelledOutcome`
  - `payload_ref: HostPayloadRef | None`
- `ResolveWaitLostOutcome`
  - `reason_code: str`
  - `message: str`
  - `provider_status_ref: WaitProviderStatusRef | None`

`HostPayloadRef` 当前只存在于 `dayu.host.tool_runtime` 时，implementation 必须把该 dataclass 移入 `dayu.host.api`，并把 ToolRuntime 改为从 `dayu.host.api` 导入同一类型；禁止新增第二个语义相同的 payload ref 类型。`WaitProviderStatusRef` 是 Host public/internal typed ref，字段为 `adapter_key: WaitAdapterKey`、`status_ref: str`、`status_digest: str | None`，只引用 adapter 已持久化或可重读的状态摘要，不承载外部系统 payload。

`ResolveWaitRequest.context: HostCallContext` 必须保留，仍作为 mutating request 的调用上下文，参与权限、审计、EventLog actor/source/reason payload 和 public semantic digest。Phase 7 不允许为了简化 adapter API 删除 `context` 或把它放进 extra payload。

Outcome digest 由 Host 统一以 canonical JSON 计算，digest 输入必须包含 outcome kind、typed result fields、payload ref / provider status ref、source、observed_at、wait_id 和 idempotency key；不得只 hash `repr()` 或 adapter 私有字符串。

Outcome ref 互斥规则：

- completed / failed / cancelled outcome 可以携带 `payload_ref`，必须没有 `provider_status_ref`。
- lost outcome 可以携带 `provider_status_ref`，必须没有 `payload_ref`。
- digest 输入必须对每个可选 typed field 写入显式 `null` sentinel；例如 completed outcome 的 `provider_status_ref` 参与 digest 时必须为 `null`，lost outcome 的 `payload_ref` 参与 digest 时必须为 `null`。这样可避免“字段缺失”和“字段为空”生成同构 digest。
- digest 输入必须覆盖所有非空 typed fields：result payload、cancel reason/message/hint、lost reason/message、payload ref、provider status ref、source、observed_at、wait_id、idempotency key。

### 3.3 `observed_at` Type

`ResolveWaitRequest.observed_at` 改为 `datetime`，必须是 timezone-aware UTC datetime。公共 dataclass `__post_init__` 拒绝 naive datetime 和非 UTC datetime。持久化时使用现有 UTC timestamp formatter 转为文本。

不采用 `str + strict parse`，原因是 `ToolAwaitSpec.deadline` 与 `ToolAwaitSnapshot.captured_at` 已使用 `datetime`，继续使用 string 会把时间解析差异推给每个 adapter 和测试。

### 3.4 Adapter Reported Lost vs Host Wait Record `lost`

`ResolveWaitLostOutcome` 是 adapter-reported unable-to-confirm input，表示 adapter 当前无法确认外部 job 状态。`WaitRecordStatus.LOST` 是 Host durable terminal state，表示 Host policy 已放弃继续等待。

Phase 7 第一版固定策略：

- active wait 仍为 `waiting` 且收到 `ResolveWaitLostOutcome` 时，Host 在同一 `resolve_wait` transaction 内把 wait record CAS 到 `lost`，追加 tool lost terminal fact 与 `RUN_LOST`，Run 进入 `LOST`，不创建 resume Attempt。
- 如果实现需要把 adapter reported lost 当作可重试 not-ready 信号，必须停止并交回 controller；当前 design / control doc 没有授权长轮询或 reconcile policy。
- 已是 `cancelled` / `lost` 的 wait record 再收到任何 outcome，都不改变 terminal state，只写 `WAIT_LATE_RESULT_REJECTED` diagnostic。

`ResolveWaitCancelledOutcome` 是工具级取消结果，不等同于 Host wait record `cancelled`。active `waiting` 收到该 outcome 时，Host 将 wait record 置为 `resolved`，追加 `TOOL_RESULT_ACCEPTED` cancelled fact，并创建 resume Attempt，让模型消费工具级取消结果。`WaitRecordStatus.CANCELLED` 仅由 Host cancel Run / wait 产生。

### 3.5 Adapter Key Source

`adapter_key` 必须由 Host composition root / ToolRuntime / Host wait adapter registry 在 awaiting accept candidate 中提供，不能由 Engine 选择，不能从 Engine `tool_awaiting` / `run_suspended` 事件反推。

Phase 7 新增 Host-internal adapter binding：

- `WaitAdapterKey(value: str)`：非空、长度受限、只允许稳定 registry key。
- `WaitResumePolicy`: `POLL | CALLBACK | MANUAL`。
- `WaitAdapterBinding`: `adapter_key`、支持的 `ToolAwaitKind`、`resume_policy`、poll adapter 或 manual adapter contract。
- `WaitAdapterRegistry`: 根据 `tool_name`、`ToolAwaitSpec.await_kind`、Host tooling policy 和 optional tool policy 解析 binding。

ToolRuntime accept awaiting 时通过 registry 选择 binding 并写入 wait record。若没有 binding，返回 governed error / reject，不创建 wait record；不得让 Engine 或业务 payload 携带 adapter class path。

### 3.6 `snapshot_ref` / `external_job_id` Typed Ref Constraints

wait record 中的 refs 必须是 typed durable fields：

- `WaitSnapshotRef(snapshot_id: str, captured_at: datetime, snapshot_digest: str | None)`
  - 来源为 `ToolAwaitingOutcome.snapshot`。
  - 只保存 snapshot id、采集时间和可选 digest，不保存 snapshot payload。
  - 若 `snapshot` 为 `None`，`snapshot_ref` 为 `None`。
- `ExternalJobRef(adapter_key: WaitAdapterKey, external_job_id: str)`
  - `external_job_id` 非空、长度受限、只允许 adapter 可重读的稳定外部 job id 或等价 ref。
  - 对 `resume_policy=POLL` 必须非空；对 `MANUAL` / Phase 7 callback contract 可为空，但 wait record 必须仍有 `resume_token`。
  - 若 adapter 只能从 `ToolAwaitSpec.resume_token` 派生 external job id，派生逻辑必须位于 Host adapter binding，不得让 Engine 选择或解析 Host adapter。

`resume_token` 继续保存为 Host-owned opaque reference，不能当作 adapter object、授权凭据或可执行 payload。

### 3.6.1 String Length And Validation Constraints

Phase 7 固定以下字符串长度上限。dataclass validation 与 SQLite DDL `CHECK` 必须使用同一常量语义；DDL 使用 `length(field) BETWEEN 1 AND N` 表达非空上限，nullable 字段使用 `field IS NULL OR length(field) BETWEEN 1 AND N`。

| Field | Max length | Dataclass validation | DDL CHECK |
| --- | ---: | --- | --- |
| `wait_id` | 128 | non-empty text, length <= 128 | `length(wait_id) BETWEEN 1 AND 128` |
| `WaitAdapterKey.value` / `adapter_key` | 128 | non-empty text, length <= 128, allowed chars `[A-Za-z0-9_.:-]` | `length(adapter_key) BETWEEN 1 AND 128` |
| `tool_call_id` | 256 | reuse existing tool call validation, length <= 256 at wait boundary | `length(tool_call_id) BETWEEN 1 AND 256` |
| `tool_name` | 128 | reuse existing tool name validation, length <= 128 at wait boundary | `length(tool_name) BETWEEN 1 AND 128` |
| `resume_token` | 2048 | reuse `ToolAwaitSpec` max length | `length(resume_token) BETWEEN 1 AND 2048` |
| `snapshot_id` / `snapshot_ref` | 256 | nullable; non-empty length <= 256 when present | `snapshot_ref IS NULL OR length(snapshot_ref) BETWEEN 1 AND 256` |
| `external_job_id` | 512 | nullable except poll binding; non-empty length <= 512 when present | `external_job_id IS NULL OR length(external_job_id) BETWEEN 1 AND 512` |
| `WaitProviderStatusRef.status_ref` | 512 | nullable by containing ref; non-empty length <= 512 when present | diagnostic payload validation only; not stored in wait row |
| `accept_idempotency_key` / `resolve_idempotency_key` | 256 | non-empty length <= 256 when present | `length(accept_idempotency_key) BETWEEN 1 AND 256`; `resolve_idempotency_key IS NULL OR length(resolve_idempotency_key) BETWEEN 1 AND 256` |

If existing helper constants already define stricter limits for tool ids or idempotency keys, implementation must use the stricter existing limit and update this plan only through controller if that changes public behavior. It must not silently use a looser limit in code than DDL.

### 3.7 Wait Record Schema / Status / CAS

新增 `host_wait_records` durable table，并将 `HOST_SCHEMA_VERSION` bump 到新 fresh schema version。按项目规则只支持全新起库，不写旧库兼容读取或迁移。

最小 schema：

- `wait_id TEXT PRIMARY KEY`
- `session_id TEXT NOT NULL`
- `run_id TEXT NOT NULL`
- `attempt_id TEXT NOT NULL`
- `execution_id TEXT NOT NULL`
- `tool_call_id TEXT NOT NULL`
- `tool_name TEXT NOT NULL`
- `adapter_key TEXT NOT NULL`
- `await_kind TEXT NOT NULL`
- `resume_policy TEXT NOT NULL CHECK ('poll','callback','manual')`
- `resume_token TEXT NOT NULL`
- `snapshot_ref TEXT NULL`
- `snapshot_captured_at TEXT NULL`
- `snapshot_digest TEXT NULL`
- `external_job_id TEXT NULL`
- `accept_idempotency_key TEXT NOT NULL`
- `resolve_idempotency_key TEXT NULL`
- `resolve_semantic_digest TEXT NULL`
- `deadline_at TEXT NULL`
- `expires_at TEXT NULL`
- `status TEXT NOT NULL CHECK ('waiting','resolved','failed','cancelled','lost')`
- `created_event_id TEXT NOT NULL`
- `created_event_sequence INTEGER NOT NULL`
- `updated_event_id TEXT NOT NULL`
- `updated_event_sequence INTEGER NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `terminal_at TEXT NULL`

Indexes / invariants:

- Unique active wait per Run: partial unique index on `run_id` where `status = 'waiting'`。
- Query active poll waits: index on `(resume_policy, status, deadline_at, expires_at)`。
- Query by external job: index on `(adapter_key, external_job_id)` where `external_job_id IS NOT NULL`。
- FKs to `host_runs(run_id)`、`host_attempts(attempt_id)`、`event_log(event_id / event_sequence)` consistent with existing schema style.

Status semantics:

- `waiting`: Host 已接受 awaiting fact，Run.status = `WAITING`，Attempt.status = `SUSPENDED`。
- `resolved`: Host 已 durable accepted completed / cancelled result，并创建 resume Attempt。
- `failed`: 外部等待确认失败，Phase 7 第一版关闭 Run 为 `FAILED`，不创建 resume Attempt。
- `cancelled`: Host cancel Run / wait 后不再接受该 wait record 的结果作为 canonical fact。
- `lost`: Host policy 已放弃确认外部 job 状态，Run 进入 `LOST`。

Required CAS helpers in `dayu/host/durable/state.py` or a dedicated `dayu/host/durable/wait_state.py`:

- `insert_wait_record(transaction, row)`
- `read_wait_record_by_id(transaction, wait_id)`
- `read_active_wait_records_for_run(transaction, run_id)`
- `mark_wait_record_resolved_row(...)`
- `mark_wait_record_failed_row(...)`
- `mark_wait_record_cancelled_row(...)`
- `mark_wait_record_lost_row(...)`
- `cancel_active_wait_records_for_run(...)`

All terminal helpers must require `status='waiting'` in the `WHERE` clause and return typed mutation status `UPDATED | CAS_LOST | NOT_FOUND | INVALID_STATE`。

### 3.8 ToolAwaitingOutcome Accept Path

ToolRuntime must stop normalizing `ToolAwaitingOutcome` to `unsupported_awaiting` governed error. Awaiting accept is a distinct Host accept path, not a normal `TOOL_RESULT_ACCEPTED` completed/failed/cancelled fact.

Required path:

1. Dispatcher returns `ToolAwaitingOutcome(await_spec, snapshot)`。
2. ToolRuntime computes the same identity / duplicate / policy context as ordinary tools.
3. ToolRuntime calls Host awaiting accept port with `ToolAwaitingAcceptCandidate` containing session/run/attempt/execution identity、iteration id、tool call identity、tool identity digest、normalized arguments digest、policy decision、duplicate decision、await spec、snapshot ref、adapter binding、external job ref、accept idempotency key、semantic digest。
4. Host transaction validates current Run is `RUNNING` and current Attempt is `RUNNING` for the same execution.
5. Host appends `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` canonical facts.
6. Host inserts `host_wait_records` row with `status='waiting'`。
7. Host CAS updates Run.status to `WAITING` and terminal-closes Attempt.status to `SUSPENDED` using the `ATTEMPT_SUSPENDED` event refs.
8. Host records accept idempotency. Same accept key + same digest returns existing wait accepted ack and refs. Same key + different digest returns idempotency conflict.
9. ToolRuntime returns `ToolAwaitingOutcome` to Engine only after Host accepted ack. Ack-lost retry uses same accept idempotency key.

If accept rejects after business callable already started external job, ToolRuntime must return governed error and emit diagnostic refs; external job cleanup is best-effort adapter concern and does not change Host truth.

### 3.9 `resolve_wait` Pipeline

`resolve_wait(host, wait_id, request) -> RunSnapshot` becomes implemented and short-transactional.

Common pipeline:

1. Validate handle open、`wait_id`、request fields、`observed_at` UTC、outcome envelope。
2. Build `resolution_digest` for valid `waiting` resolution and `late_rejection_digest` for non-acceptable wait states. Both digests use canonical JSON and the mutual-exclusion/null-sentinel rules in §3.2.
3. In a write transaction, read wait record, Run and current Attempt before reading wait resolution idempotency. Status classification happens before idempotency replay.
4. If wait record missing, raise `NOT_FOUND` / `wait_not_found` detail。
5. If wait record status is `cancelled` / `lost` or owning Run is already terminal, this is not a valid resolution replay candidate. Go directly to the late rejection path in §3.10.1 using independent `wait_late_rejection` idempotency, then raise `HostApiErrorCode.INVALID_STATE` with typed detail carrying `wait_id`、`wait_status`、`rejection_reason` and diagnostic event ref。
6. If wait record status is `resolved` / `failed`, read `wait_resolution` idempotency only to allow same-key same-digest replay of the already committed result. Different `idempotency_key` or same key with different digest must raise `HostApiErrorCode.INVALID_STATE` / `IDEMPOTENCY_CONFLICT` respectively and must not append canonical facts, diagnostic late rejection events or create Attempt.
7. If wait record status is `waiting`, read existing idempotency record for scope `wait_resolution` / `wait_id` / `idempotency_key`。
8. If same idempotency key + same `resolution_digest` exists, return snapshot from durable state without appending events.
9. If same key + different digest exists, raise `HostApiErrorCode.IDEMPOTENCY_CONFLICT`。
10. If wait record status is `waiting`, perform first-committer-wins CAS and then:
   - completed: mark wait `resolved`, append `RESUME_REQUESTED`、`TOOL_RESULT_ACCEPTED` completed、`RUN_STARTED(start_reason=resume)`、new `ATTEMPT_STARTED`、new dispatch record, set Run `RUNNING` with current new Attempt.
   - cancelled tool outcome: mark wait `resolved`, append `RESUME_REQUESTED`、`TOOL_RESULT_ACCEPTED` cancelled、`RUN_STARTED(start_reason=resume)`、new `ATTEMPT_STARTED`、new dispatch record, set Run `RUNNING` with current new Attempt.
   - failed: mark wait `failed`, append `TOOL_RESULT_ACCEPTED` failed and `RUN_FAILED`, set Run `FAILED`, no resume Attempt.
   - lost: mark wait `lost`, append tool lost terminal fact and `RUN_LOST`, set Run `LOST`, no resume Attempt.
11. Record wait resolution idempotency with created event ref.
12. Return `RunSnapshot` from durable truth and wake dispatch scheduler only after transaction commit when a resume dispatch record was created.

`RunStartReason` must add `RESUME = "resume"` and tests must update closed enum assertions. If implementation can reuse existing direct-start helper only by lying with `INITIAL` or `QUEUE_PROMOTION`, stop; resume needs an explicit reason.

Required transition helper:

- Add `resume_run_from_waiting_in_transaction(...)` in `dayu/host/durable/run_transition.py`。
- Inputs: transaction, EventLog store, `wait_id`, source suspended `run_id` / `attempt_id`, new `attempt_id` / `execution_id` / `dispatch_record_id`, `RESUME_REQUESTED` event id, `TOOL_RESULT_ACCEPTED` event id, `RUN_STARTED` event id, `ATTEMPT_STARTED` event id, occurred_at, actor/source, resolution payload, worker kind / execution target。
- CAS preconditions: Run row exists with `status=WAITING` and `current_attempt_id` equal to the suspended Attempt; source Attempt row exists with `status=SUSPENDED`; wait record exists with `status=waiting`; no terminal Run refs are set; unique active wait invariant holds for the Run。
- Writes in one transaction: append `RESUME_REQUESTED` and wait-specific `TOOL_RESULT_ACCEPTED`; CAS wait record to `resolved`; append `RUN_STARTED` with `start_reason=resume`; insert new `STARTING` Attempt; update Run to `RUNNING`, `current_attempt_id=<new_attempt_id>`, `started_event_id=<RUN_STARTED>`; append `ATTEMPT_STARTED`; insert pending dispatch record.
- Return type: typed result carrying `StateMutationStatus`, updated `RunRow`, new `AttemptRow`, `DispatchRecordRow | None`, and event refs. CAS lost must roll back all appended events through the transaction boundary.
- Failed/lost terminal wait outcomes must use separate helpers `fail_run_from_waiting_in_transaction(...)` and `mark_run_lost_from_waiting_in_transaction(...)` or one typed helper with explicit terminal mode; they must not create dispatch records.

### 3.10 EventLog Facts

Phase 7 canonical event types:

- `TOOL_AWAITING`: awaiting accepted by Host ToolRuntime path.
- `RUN_WAITING`: Run entered `WAITING`。
- `ATTEMPT_SUSPENDED`: current Attempt terminal status is `SUSPENDED`。
- `RESUME_REQUESTED`: wait resolution accepted and Host will create a resume Attempt.
- `TOOL_RESULT_ACCEPTED`: completed / failed / cancelled / lost wait result accepted. Phase 7 must extend the existing P6 payload codec with the wait-specific fields below rather than creating a second weak event.
Lost outcome must use `TOOL_RESULT_ACCEPTED` with typed `ToolFactKind.LOST` / payload `tool_fact_kind='lost'` and an outcome digest derived from `ResolveWaitLostOutcome`。Do not introduce a parallel `TOOL_WAIT_LOST` event.

`TOOL_RESULT_ACCEPTED` wait resolution payload must extend the existing ordinary tool result payload rather than replacing it.

Ordinary fields retained from Phase 6:

- `tool_fact_id`
- `session_id`
- `run_id`
- `attempt_id`
- `execution_id`
- `iteration_id`
- `tool_call_id`
- `tool_name`
- `tool_schema_digest`
- `tool_identity_digest`
- `normalized_arguments_digest`
- `tool_fact_kind`
- `outcome_digest`
- `payload_digest`
- `payload_ref`
- `truncation`
- `duplicate_key`
- `duplicate_decision`
- `policy_decision`
- `tool_idempotency_key`
- `diagnostic_refs`
- `accepted_event_refs`

Wait-specific incremental fields required when the result comes from `resolve_wait`:

- `wait_id`
- `resolution_source`: `poll | callback | manual`
- `resolution_kind`: `completed | failed | cancelled | lost`
- `resolution_idempotency_key`
- `observed_at`
- `wait_record_status_before`
- `wait_record_status_after`
- `wait_created_event_ref`
- `wait_updated_event_ref`
- `adapter_key`
- `external_job_ref`
- `snapshot_ref`
- `provider_status_ref`
- `resume_attempt_id` for completed / cancelled tool outcomes; `null` for failed / lost.
- `resume_dispatch_record_id` for completed / cancelled tool outcomes; `null` for failed / lost.

`dayu/host/_event_payload.py` owns helper functions for these payloads: `tool_awaiting_payload(...)`、`run_waiting_payload(...)`、`attempt_suspended_payload(...)`、`resume_requested_payload(...)`、`tool_result_wait_resolution_payload(...)` and `wait_late_result_rejected_payload(...)`。These helpers must return typed JSON values using existing `JsonValue` aliases and must not accept untyped dict bags.

Phase 7 diagnostic event:

- `event_class = diagnostic`
- `event_type = WAIT_LATE_RESULT_REJECTED`
- `reason.reason_code` must be one of:
  - `wait_cancelled`
  - `wait_lost`
  - `wait_already_resolved`
  - `wait_already_failed`
  - `run_terminal`
  - `idempotency_conflict`
  - `invalid_wait_state`
- payload fields:
  - `wait_id`
  - `run_id`
  - `attempt_id`
  - `tool_call_id`
  - `tool_name`
  - `source`
  - `idempotency_key`
  - `observed_at`
  - `wait_status`
  - `rejection_reason`
  - `outcome_kind`
  - `outcome_digest`
  - `payload_ref`
  - `provider_status_ref`
  - `external_job_ref`
  - `adapter_key`

### 3.10.1 Late Rejection Idempotency

Late rejection uses an independent idempotency scope and never reuses `wait_resolution` records.

- `scope_kind = "wait_late_rejection"`
- `scope_id = wait_id`
- `idempotency_key = ResolveWaitRequest.idempotency_key`
- `semantic_input_digest = late_rejection_digest`
- `result_kind = "wait_late_rejection_diagnostic"`
- `result_ref = WAIT_LATE_RESULT_REJECTED event id`

Same key + same late digest returns existing diagnostic refs and raises/returns the same structured invalid-state result without appending another diagnostic event. Same key + different late digest returns idempotency conflict diagnostic / error and must not append unbounded diagnostic events. Late rejection is used for `cancelled` / `lost` wait records and terminal owning Run states. Already `resolved` / `failed` wait records with a different key are invalid-state resolution attempts and do not use late rejection idempotency unless the owning Run has separately become terminal outside the recorded wait resolution path.

### 3.11 `WAITING` Cancel And First-Committer-Wins

`cancel_run` and `cancel_session_runs` must support `WAITING` Run in Phase 7.

Integration anchors:

- `dayu/host/command.py`: `cancel_run(...)` and `cancel_session_runs(...)` continue to call admission service; no direct wait-table writes in public facade.
- `dayu/host/admission.py`: add WAITING branch inside `HostAdmissionService.cancel_run(...)` and `HostAdmissionService.cancel_session_runs(...)`。Both public paths must delegate to the same core operation object / helper, for example `_cancel_waiting_run_in_transaction(...)`, so session-scope cancel cannot drift from single-run cancel.
- `dayu/host/durable/run_transition.py`: add `cancel_waiting_run_in_transaction(...)` that appends events and calls wait-state CAS helpers.
- `dayu/host/durable/state.py` or `dayu/host/durable/wait_state.py`: `cancel_active_wait_records_for_run(...)` performs `UPDATE host_wait_records SET status='cancelled' ... WHERE run_id=? AND status='waiting'` and returns updated wait ids / refs count.
- After commit, admission result carries `WaitCancelNotification(run_id, wait_ids, adapter_keys, external_job_refs)` for poller / adapter best-effort abandon. If no poller runtime is attached, the notification is safely dropped; Host terminal correctness is already durable.

Cancel path for `WAITING`:

1. Public command validates idempotency exactly like existing cancel paths.
2. Write transaction reads Run `WAITING` and all active wait records for the Run.
3. CAS preconditions: Run row status is `WAITING`; Run has no terminal refs; current Attempt row exists and is `SUSPENDED`; at least one active wait record with `status='waiting'` exists for the Run.
4. Append `CANCEL_REQUESTED`。
5. CAS mark all active `status='waiting'` wait records for the Run to `cancelled`。
6. Append `RUN_CANCELLED` and set Run `CANCELLED`。
7. Do not create `ATTEMPT_CANCELLED` for the suspended Attempt; the Attempt is already terminal `SUSPENDED` from awaiting accept.
8. Commit. After commit, emit `WaitCancelNotification` to wait poller / adapter best-effort abandon path.

Race rule:

- `resolve_wait` commits first: wait becomes `resolved` / `failed` / `lost`; later cancel sees latest Run state and follows normal current-state behavior. Completed / cancelled tool outcome leading to resume means later cancel may cancel the new `RUNNING` / pre-dispatch resume Attempt through existing cancel path.
- cancel commits first: wait becomes `cancelled`, Run becomes `CANCELLED`; later `resolve_wait` cannot append canonical tool result or create Attempt, only writes `WAIT_LATE_RESULT_REJECTED` diagnostic.

Tests must model race deterministically by invoking the two transactions in controlled order; do not use sleep-based race tests.

### 3.12 Poll / Manual Adapter

Phase 7 adds minimal Host wait adapter runtime:

- `WaitPollAdapter` protocol observes `WaitRecordRow` and returns `WaitPollResult = NotReady | Ready(ResolveWaitOutcome) | Lost(ResolveWaitLostOutcome) | AdapterError`。
- `WaitPoller` first version is Host-runtime owned, not process-global. It is constructed by Host composition root with a `HostCommandHandle` / transaction runner, adapter registry and bounded poll policy. It starts when the owning Host handle / scheduler runtime starts and stops on handle close / scheduler close.
- Poller supports an explicit `poll_once()` / `drain_once()` method for deterministic tests. A background loop may call that method, but the loop must be cancellable and must not survive Host handle close.
- Restart recovery is limited to scanning durable active `resume_policy=POLL AND status='waiting'` wait records on poller start / tick. Full orphan recovery, worker recovery and RECOVERING dispatch remain Phase 11.
- Poller reads active poll waits in a short read transaction, releases the transaction, calls external adapter outside any Host transaction, then submits ready/lost outcomes through `resolve_wait` in a separate command transaction.
- Poller maintains an in-process in-flight set keyed by `wait_id` to avoid duplicate concurrent polls in the same process. Cross-process concurrency is governed by wait record CAS and `resolve_wait` idempotency; no durable poll lease is introduced in Phase 7.
- Poller must not hold EventLog appender or wait-state writer ports. Its only state-changing path is `resolve_wait` or the post-cancel best-effort adapter abandon hook.
- Poller reads active `resume_policy=POLL` wait records and calls adapter.
- On ready / lost, poller calls public/internal `resolve_wait` with `source=POLL` and a deterministic idempotency key derived from adapter key, wait id and external job id / provider status version.
- On not-ready, poller does not call `resolve_wait`。
- On adapter error, poller writes diagnostic only if existing diagnostic emitter is available; it must not mark wait failed unless adapter returns typed failed/lost outcome.
- If poller observes wait record `cancelled` before polling, it stops / abandons observation and may best-effort cancel/revoke external job through adapter. It must not call `resolve_wait` for cancelled records.
- If cancellation wins between poll read and resolve call, `resolve_wait` handles late rejection and writes `WAIT_LATE_RESULT_REJECTED`。

Manual adapter is a typed helper around `resolve_wait(source=MANUAL)` for tests/admin-controlled entry. Callback source is recognized by `WaitResolutionSource.CALLBACK` but no HTTP endpoint is implemented.

### 3.13 EngineEvent Awaiting / Suspended Boundary

Engine `tool_awaiting` / `run_suspended` remains diagnostic / idempotent only.

Phase 7 must update current Phase 5 behavior in `engine_ingest.py`:

- If Engine event carries refs matching an already accepted wait record / accepted awaiting events, append diagnostic or preview confirmation and return accepted/duplicate without changing Run / Attempt / wait record.
- If Engine event arrives without matching Host accepted wait refs for the current attempt, reject as diagnostic unsupported / stale; it still must not create wait record or push Run to `WAITING`。
- It must not fail a Run that has already been canonical accepted into `WAITING` by ToolRuntime just because Engine later emits `run_suspended` confirmation.
- Duplicate ingest of the same Engine event remains idempotent.
- No `TOOL_AWAITING` / `RUN_SUSPENDED` EngineEvent path may call `_close_terminal`, `terminal_closeout_in_transaction`, `terminal_run_row` or an equivalent terminal closeout helper.

Behavior matrix:

| Run status | Attempt / execution match | Accepted refs present and match wait record | Event type | Required behavior |
| --- | --- | --- | --- | --- |
| `WAITING` | yes, suspended Attempt / execution matches current wait | yes | `TOOL_AWAITING` | Append diagnostic / preview confirmation only; return accepted or duplicate; no state change. |
| `WAITING` | yes, suspended Attempt / execution matches current wait | yes | `RUN_SUSPENDED` | Append diagnostic / preview confirmation only; return accepted or duplicate; no state change. |
| `WAITING` | yes | no | `TOOL_AWAITING` | Append stale / missing-refs diagnostic; return rejected/accepted diagnostic according to existing ingest result style; no wait creation, no terminal closeout. |
| `WAITING` | yes | no | `RUN_SUSPENDED` | Append stale / missing-refs diagnostic; no wait creation, no terminal closeout. |
| `RUNNING` | yes, active Attempt / execution matches | yes | `TOOL_AWAITING` | Treat as idempotent confirmation only if refs point to an already committed awaiting accept that won concurrently; otherwise stale diagnostic. Never create wait record from EngineEvent. |
| `RUNNING` | yes, active Attempt / execution matches | yes | `RUN_SUSPENDED` | Same as above; no terminal closeout. |
| `RUNNING` | yes | no | `TOOL_AWAITING` / `RUN_SUSPENDED` | Diagnostic unsupported/stale reject; no `WAITING`, no `FAILED`, no terminal closeout. |
| `CANCELLING` / `CANCELLED` / `SUCCEEDED` / `FAILED` / `LOST` | any | any | `TOOL_AWAITING` / `RUN_SUSPENDED` | Diagnostic stale/late event; do not alter terminal/cancelling state; do not write wait record. |
| any non-terminal | no | any | `TOOL_AWAITING` / `RUN_SUSPENDED` | Existing stale execution diagnostic path; no wait record, no Run / Attempt status change. |

### 3.14 Run-local Duplicate Governance Across Resume Attempt

Resume Attempt is a new model request inside the same Run. The in-memory duplicate governance registry in `HostDispatchScheduler` must continue to key by `run_id` and must not clear the run-local duplicate index when the first Attempt suspends into `WAITING`。

Rules:

- Do not call `clear_run(run_id)` when awaiting accept suspends an Attempt.
- Do clear run-local duplicate memory when the Run reaches final terminal `SUCCEEDED` / `FAILED` / `CANCELLED` / `LOST`。
- Resume RunInputBuilder must include accepted wait result / tool facts / governance guidance in messages so a stateless model sees prior facts.
- If the resumed model repeats the same semantic tool call, existing run-local duplicate governance handles reuse / hint / require justification / hard stop.

## 4. Affected Files / Modules

Implementation may modify only files listed in the assigned slice. If a slice needs an unlisted file, stop and return to controller.

### 4.1 Production Files By Slice

- P7-S1:
  - `dayu/host/api.py`
  - `dayu/host/__init__.py`
  - `dayu/host/tool_runtime.py` only for `HostPayloadRef` import migration and `ToolFactKind.LOST` enum extension.
  - `dayu/host/durable/schema.py`
  - `dayu/host/durable/state.py`
  - `dayu/host/durable/__init__.py` only if new wait-state helpers are exported internally.
- P7-S2:
  - `dayu/host/waiting.py` new, for wait accept / resolution service if needed.
  - `dayu/host/wait_adapter.py` new, for adapter protocols / registry / typed refs if not kept in `waiting.py`.
  - `dayu/host/tool_runtime.py`
  - `dayu/host/durable/state.py`
  - `dayu/host/durable/run_transition.py`
  - `dayu/host/_event_payload.py`
- P7-S3:
  - `dayu/host/command.py`
  - `dayu/host/admission.py` only for post-resume dispatch wake result plumbing, not WAITING cancel.
  - `dayu/host/durable/run_transition.py`
  - `dayu/host/durable/state.py`
  - `dayu/host/waiting.py`
  - `dayu/host/_event_payload.py`
  - `dayu/host/dispatch.py` for wake dispatch and duplicate registry lifetime only.
  - `dayu/host/run_input.py` for resume message reconstruction only if current builder lacks accepted wait result context.
- P7-S4:
  - `dayu/host/wait_adapter.py`
  - `dayu/host/command.py`
  - `dayu/host/admission.py`
  - `dayu/host/durable/run_transition.py`
  - `dayu/host/durable/state.py`
  - `dayu/host/engine_ingest.py`
  - `dayu/host/waiting.py`
  - `dayu/host/_event_payload.py`
- P7-S5:
  - `dayu/host/README.md`
  - `dayu/README.md` only if public CLI / usage flow changes; expected not needed.
  - `tests/README.md` only if new test category or command convention is added; expected not needed.

### 4.2 Test Files By Slice

- P7-S1:
  - `tests/host/test_public_contracts.py`
  - `tests/host/test_import_boundary.py`
  - `tests/host/test_package_exports.py`
  - `tests/host/test_durable_schema.py`
  - `tests/host/test_state_schema.py`
  - `tests/host/test_wait_record_state.py` new.
- P7-S2:
  - `tests/host/test_wait_awaiting_accept.py` new.
  - `tests/host/test_toolruntime_executor.py`
  - `tests/host/test_toolruntime_accept_barrier.py`
  - `tests/host/test_phase7_waiting_integration.py` new.
- P7-S3:
  - `tests/host/test_resolve_wait_command.py` new.
  - `tests/host/test_run_attempt_transitions.py`
  - `tests/host/test_run_input_builder.py`
  - `tests/host/test_dispatch_scheduler.py`
  - `tests/host/test_phase7_waiting_integration.py`
- P7-S4:
  - `tests/host/test_wait_cancel_late_result.py` new.
  - `tests/host/test_wait_adapter_polling.py` new.
  - `tests/host/test_engine_ingest_mapping.py`
  - `tests/host/test_public_cancel_session_runs.py`
  - `tests/host/test_public_run_api.py`
- P7-S5:
  - Existing docs-related tests only if README examples are executable; otherwise no test file changes.

### 4.3 Forbidden Files / Modules

- `dayu/engine/` public contracts or implementation.
- `dayu/contracts/`。
- `dayu/fins/`, `dayu/service/`, `dayu/ui/`。
- Remote transport / wire protocol modules.
- Projection / memory / context / recovery / outbox / audit / tool trace read-model modules.
- Review artifacts except later Gateflow implementation / review artifacts.

## 5. Implementation Slices

### P7-S1 - Public Contracts And Durable Wait Record

- **objective**: Replace weak `ResolveWaitRequest.outcome_ref` with typed outcome envelope, add wait record schema / row codec / status machine / CAS helpers.
- **allowed files**: P7-S1 files only.
- **prerequisites**: Phase 7 design fix re-review PASS; current schema is fresh-bootstrap only.
- **exact changes**:
  - Add public dataclasses / enums in `dayu/host/api.py`: `ResolveWaitCompletedOutcome`、`ResolveWaitFailedOutcome`、`ResolveWaitCancelledOutcome`、`ResolveWaitLostOutcome`、`ResolveWaitOutcome` type alias、`WaitAdapterKey`、`WaitProviderStatusRef`、public `HostPayloadRef`。
  - Move current `HostPayloadRef` from `dayu.host.tool_runtime` to `dayu.host.api`; update `dayu/host/tool_runtime.py` imports to use `dayu.host.api.HostPayloadRef` and remove the local duplicate definition.
  - Add `ToolFactKind.LOST` in `dayu/host/tool_runtime.py` during this slice so later resolve slices can emit lost wait results without modifying unowned files.
  - Change `ResolveWaitRequest` to retain `context: HostCallContext` and use `idempotency_key`、`outcome`、`source`、`observed_at: datetime`。
  - Validate UTC-aware `observed_at` and outcome envelope field combinations.
  - Add constants for max lengths in §3.6.1 and use them in dataclass validation and DDL CHECK clauses.
  - Export new public types from `dayu/host/__init__.py` where they are part of public command request construction.
  - Add `WaitRecordStatus`、`WaitResumePolicy`、`WaitSnapshotRef`、`ExternalJobRef`、`WaitRecordRow` and serialize / deserialize helpers.
  - Add `host_wait_records` DDL, indexes and schema version bump.
  - Add insert/read/CAS helpers listed in §3.7.
  - Add `RunStartReason.RESUME` and codec tests.
- **non-goals**: no ToolRuntime behavior change, no `resolve_wait` implementation, no poller.
- **tests**:
  - `ResolveWaitRequest` rejects empty idempotency key, naive datetime, non-UTC datetime, invalid lost/provider ref combinations.
  - `ResolveWaitRequest.context` remains required and participates in dataclass construction.
  - `ResolveWaitRequest` no longer has `outcome_ref` in dataclass fields.
  - Lost outcome rejects `payload_ref`; non-lost outcomes reject `provider_status_ref`.
  - Max length validation and DDL CHECK reject overlong `adapter_key`、`snapshot_id`、`external_job_id`、provider status ref and idempotency keys.
  - Public enum/export tests include new outcome/ref types and `RunStartReason.RESUME` codec.
  - `ToolFactKind.LOST` is present before P7-S3.
  - Fresh schema creates `host_wait_records` and required indexes.
  - Insert/read wait record round trips all typed fields.
  - Unique active wait per Run blocks two `waiting` rows but allows terminal historical rows.
  - CAS helpers update only `waiting` rows and return `CAS_LOST` / `NOT_FOUND` / `INVALID_STATE` correctly.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_import_boundary.py tests/host/test_package_exports.py tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- **completion signal**: Public request and durable wait record can be constructed, validated and CAS-mutated without invoking ToolRuntime or dispatch.
- **stop condition**: If replacing `outcome_ref` requires compatibility wrapper for old request shape, stop; project rules require new contract, not compatibility.

### P7-S2 - ToolAwaiting Accept Path

- **objective**: Make ToolRuntime accept `ToolAwaitingOutcome` as canonical Host waiting fact and create `WAITING` / `SUSPENDED` durable state.
- **allowed files**: P7-S2 files only.
- **prerequisites**: P7-S1 complete.
- **exact changes**:
  - Add `ToolAwaitingAcceptCandidate`、`ToolAwaitingAcceptedAck`、`ToolAwaitingRejectedAck`、`ToolAwaitingAcceptTimedOut` and `ToolAwaitingAcceptResult`。
  - Add Host awaiting accept port / service using transaction runner, EventLog store and idempotency store.
  - Add adapter registry / binding selection. Binding is chosen by Host from tool name + await kind + Host policy; not from Engine event.
  - Derive `WaitSnapshotRef` from `ToolAwaitSnapshot`; derive `ExternalJobRef` through adapter binding when needed.
  - Add `_event_payload.py` helpers for `tool_awaiting_payload(...)`、`run_waiting_payload(...)` and `attempt_suspended_payload(...)`。
  - In ToolRuntime, remove `unsupported_awaiting` normalization for Phase 7 path. Awaiting outcome calls awaiting accept port with stable accept idempotency key.
  - Host transaction appends `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`、inserts wait record、sets Run `WAITING` and Attempt `SUSPENDED` atomically.
  - Same accept key + same digest returns existing ack refs. Same key + different digest rejects with idempotency conflict.
  - ToolRuntime returns `ToolAwaitingOutcome` to Engine only after accepted ack; rejected / timed out awaiting accept returns governed tool error and diagnostic refs.
  - Do not clear run-local duplicate governance registry when an Attempt suspends.
- **non-goals**: no `resolve_wait`, no cancel, no poller, no EngineEvent ownership.
- **tests**:
  - Awaiting business tool creates `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` and one active wait record.
  - Run becomes `WAITING`; Attempt becomes `SUSPENDED`; no `RUN_FAILED` is appended.
  - Accept retry with same key returns existing wait refs without duplicate facts.
  - Same accept key with different awaiting digest returns idempotency conflict.
  - Missing adapter binding rejects and does not create wait record.
  - Poll binding requires non-empty typed external job ref.
  - Existing ordinary completed / failed / cancelled ToolRuntime tests still pass.
  - Duplicate registry remains active for the Run after suspension.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host/test_wait_awaiting_accept.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- **completion signal**: A long-running tool can put a local Run into durable `WAITING` without Engine owning the transition.
- **stop condition**: If implementation needs Engine `tool_awaiting` event to create the wait record, stop; design makes ToolRuntime accept path the owner.

### P7-S3 - `resolve_wait` Command And Resume Attempt

- **objective**: Implement unified `resolve_wait` pipeline, idempotency, completed / cancelled resume, failed / lost closeout and dispatch wakeup.
- **allowed files**: P7-S3 files only.
- **prerequisites**: P7-S1 and P7-S2 complete.
- **exact changes**:
  - Replace `command.resolve_wait` unsupported body with handle-open validation and service call.
  - Add wait resolution idempotency scope `(wait_id, idempotency_key)` with semantic digest conflict detection.
  - Add `_event_payload.py` helpers for `resume_requested_payload(...)` and `tool_result_wait_resolution_payload(...)`。
  - Add `resume_run_from_waiting_in_transaction(...)` plus failed/lost waiting closeout helpers in `dayu/host/durable/run_transition.py` with CAS preconditions from §3.9.
  - Implement completed and tool-cancelled outcomes as `resolved` wait + `RESUME_REQUESTED` + `TOOL_RESULT_ACCEPTED` + `RUN_STARTED(start_reason=resume)` + new `ATTEMPT_STARTED` + dispatch record in one transaction.
  - Implement failed outcome as wait `failed` + `TOOL_RESULT_ACCEPTED` failed + `RUN_FAILED`; no resume Attempt.
  - Implement lost outcome as wait `lost` + tool lost terminal fact + `RUN_LOST`; no resume Attempt.
  - Wake dispatch scheduler after commit for resume dispatch records.
  - Ensure `RunInputBuilder` resume messages include accepted wait result / tool facts and necessary governance guidance from EventLog.
  - Ensure run-local duplicate registry is reused by new resume Attempt because key is `run_id`, not attempt id.
- **non-goals**: no cancel, no poller, no callback endpoint.
- **tests**:
  - `resolve_wait` completed outcome returns `RunSnapshot(status=RUNNING)` with new current Attempt and dispatch record.
  - Resume events are appended once and in expected order: `RESUME_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`RUN_STARTED`、`ATTEMPT_STARTED`。
  - `RUN_STARTED` reason is `resume`。
  - Same `(wait_id, idempotency_key)` + same outcome returns existing RunSnapshot and does not create second Attempt.
  - Same key + different outcome raises `IDEMPOTENCY_CONFLICT`。
  - Already `resolved` wait with a different `idempotency_key` returns `INVALID_STATE`, appends no canonical fact and creates no Attempt.
  - Already `failed` wait with a different `idempotency_key` returns `INVALID_STATE`, appends no canonical fact and creates no Attempt.
  - Failed outcome closes Run `FAILED` and does not create resume Attempt.
  - Lost outcome closes Run `LOST` and clearly distinguishes adapter reported lost from wait record terminal `lost`.
  - Tool-cancelled outcome resumes rather than marking wait record `cancelled`.
  - Resume RunInputBuilder includes accepted wait/tool facts; duplicate governance across resume Attempt reuses same run-local index.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py tests/host/test_run_attempt_transitions.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_phase7_waiting_integration.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- **completion signal**: `awaiting -> resolve_wait(completed) -> resumed local run` works through durable EventLog / wait record / dispatch without a second wait resolution.
- **stop condition**: If resume Attempt cannot be created atomically with wait record resolution using current state helpers, stop and return to controller; do not split into best-effort multi-transaction state.

### P7-S4 - WAITING Cancel, Late Result Diagnostic, Poll / Manual Adapter, EngineEvent Confirmation

- **objective**: Close the concurrency and adapter edges: `WAITING` cancel, late result rejection diagnostic, poll/manual adapters and Engine awaiting event diagnostic/idempotent behavior.
- **allowed files**: P7-S4 files only.
- **prerequisites**: P7-S1 through P7-S3 complete.
- **exact changes**:
  - Extend `cancel_run` / `cancel_session_runs` service path to support `WAITING` Run by cancelling active wait records and setting Run `CANCELLED`。
  - Implement the WAITING branch in `dayu/host/admission.py` and reuse the same core helper for single-run and session-scope cancel.
  - Add `cancel_waiting_run_in_transaction(...)` in `dayu/host/durable/run_transition.py` and `cancel_active_wait_records_for_run(...)` in wait state helpers.
  - Preserve existing queued / pre-dispatch / active-worker cancel behavior.
  - Implement `WAIT_LATE_RESULT_REJECTED` diagnostic event with schema and rejection reason enum from §3.10.
  - Implement independent `wait_late_rejection` idempotency scope from §3.10.1; do not use `wait_resolution` records for late diagnostics.
  - Ensure late result after `cancelled` / `lost` never appends canonical tool result and never creates resume Attempt.
  - Add minimal poller / adapter protocol. Poller only observes active `waiting` records and calls `resolve_wait` when adapter returns typed ready / lost outcome.
  - Poller stops / abandons observation when it sees wait record `cancelled`; optional external cancel/revoke is best-effort and ignored for Host correctness.
  - Add manual resolve helper or tests using public `resolve_wait(source=MANUAL)`。
  - Update EngineEvent ingest for `TOOL_AWAITING` / `RUN_SUSPENDED`: matching accepted refs become diagnostic / idempotent confirmation; missing refs do not create wait state and do not fail an already waiting Run.
- **non-goals**: no HTTP callback endpoint, no physical cancel guarantee, no recovery scanner.
- **tests**:
  - Cancel waiting Run marks all active waiting records `cancelled`, Run `CANCELLED`, no resume Attempt.
  - cancel first then resolve writes exactly one `WAIT_LATE_RESULT_REJECTED` diagnostic and no canonical tool result.
  - Same late rejection key + same digest returns existing diagnostic refs and appends no second diagnostic.
  - Same late rejection key + different digest returns idempotency conflict diagnostic / error and appends no unbounded diagnostics.
  - resolve first then cancel follows latest Run state and does not overwrite accepted result.
  - Late result diagnostic payload includes wait id, run id, source, idempotency key, observed_at, rejection reason, outcome digest and refs.
  - Poll adapter observes cancelled wait and stops / abandons without calling `resolve_wait`.
  - Poll adapter ready result calls `resolve_wait` and produces normal resume.
  - Manual source goes through same pipeline and idempotency.
  - Engine `tool_awaiting` / `run_suspended` after Host awaiting accept does not create a second wait record and does not fail the Run.
  - Engine awaiting event without accepted refs remains diagnostic / rejected and cannot push Run to `WAITING`.
  - Engine awaiting/suspended behavior matrix in §3.13 is covered for `WAITING` with refs, `WAITING` without refs, `RUNNING` without refs and terminal Run states.
  - Duplicate Engine awaiting ingest remains idempotent.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host/test_wait_cancel_late_result.py tests/host/test_wait_adapter_polling.py tests/host/test_engine_ingest_mapping.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_run_api.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- **completion signal**: `WAITING` cancel and late poll/manual/callback-style result obey first-committer-wins and preserve diagnostic evidence.
- **stop condition**: If deterministic late diagnostic idempotency conflicts with existing EventLog id strategy, stop for controller decision; do not allow unbounded duplicate diagnostics.

### P7-S5 - Integration, Docs, Gate Validation

- **objective**: Run full Phase 7 integration validation, update docs within README trigger rules and ensure no Phase 7 behavior drift.
- **allowed files**: P7-S5 files only.
- **prerequisites**: P7-S1 through P7-S4 complete.
- **exact changes**:
  - Add or complete integration tests for local awaiting tool -> WAITING -> manual/poll resolve -> resumed run.
  - Update `dayu/host/README.md` with current wait / resume semantics, `resolve_wait` request shape, Engine diagnostic boundary and non-goals.
  - Do not update `docs/host/design.md` or `docs/host/implementation-control.md` in implementation unless controller explicitly opens a control-doc update gate.
  - Update `dayu/README.md` only if public architecture or reading order changed; expected no change.
  - Update `tests/README.md` only if a new test category / command convention was introduced; expected no change.
- **non-goals**: no new features beyond closing validation/docs.
- **tests**:
  - Phase 7 integration test proves long transaction wait path and resume.
  - Existing Phase 6 ToolRuntime duplicate / truncation / accept barrier tests still pass.
  - Existing Host public API / cancel / dispatch suites still pass.
- **validation**:
  - `source .venv/bin/activate && pytest tests/host -q`
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `git diff --check`
- **completion signal**: Full Host suite and pyright pass; docs reflect current implemented behavior only.
- **stop condition**: If docs would need to describe future callback / recovery / remote behavior as if implemented, stop and leave that text out.

## 6. Validation Matrix

Implementation agents must run the slice-specific commands before reporting completion. After all slices:

```bash
source .venv/bin/activate && pytest tests/host -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
git diff --check
```

Expected assertions:

- No new or expanded pyright errors.
- No `Any` / `object` / untyped public signatures in new Phase 7 code.
- Single-file test coverage for new non-script modules should be >= 80% where coverage tooling is used by controller.
- `ResolveWaitRequest` no longer exposes `outcome_ref`。
- Awaiting accept creates exactly one active wait record per Run.
- `resolve_wait` completed / cancelled tool outcomes create exactly one resume Attempt per idempotent result.
- cancel-vs-resolve is first-committer-wins.
- Late results write diagnostic evidence and never write canonical tool result after cancellation/lost.
- Engine awaiting events cannot own Host waiting state.
- Run-local duplicate governance survives `WAITING -> resolve_wait -> resume` within the same Run.

## 7. Docs Decision

Current planning gate only writes this plan file.

During implementation, Phase 7 modifies `dayu/host/`, so `dayu/host/README.md` must be checked and updated if it does not match implemented wait / resume semantics. Root `README.md` is not expected to change unless implementation alters user-visible CLI or project-level workflow. `dayu/README.md` is not expected to change unless implementation changes layer boundaries or code reading order. `tests/README.md` is not expected to change unless new test maintenance conventions are introduced.

`docs/host/design.md` and `docs/host/implementation-control.md` are truth sources for this plan and must not be modified by implementation agents unless controller explicitly opens a separate control-doc update gate.

## 8. Review Gates

Plan review must check:

- Outcome envelope is concrete enough for code generation and fully replaces `outcome_ref`。
- `observed_at` choice is explicit and matches existing datetime contracts.
- Lost outcome vs wait record `lost` is not conflated.
- `adapter_key` source does not let Engine choose Host adapter.
- `snapshot_ref` / `external_job_id` are typed refs, not metadata bags.
- Wait record schema, status transitions and CAS helpers are implementable.
- `ToolAwaitingOutcome` accept path is owned by ToolRuntime Host accept path.
- `resolve_wait` idempotency and first-committer-wins are testable.
- `WAIT_LATE_RESULT_REJECTED` schema has reason enum and digest/refs.
- Engine events remain diagnostic / idempotent only.
- Slices are small and do not require implementation agent to re-design contracts.

Code review for each slice must prioritize correctness, concurrency, idempotency, state-machine drift, Host / Engine boundary violations, weak typing, untested failure paths and docs trigger compliance.

Aggregate deepreview before ready-to-open-draft-PR must use at least two independent reviewers per `phaseflow` rules. Controller must update `docs/host/implementation-control.md` only at the appropriate control-doc gate, not during implementation slices unless explicitly authorized.

## 9. Stop Conditions

Implementation agent must stop and report to controller if any of these occur:

- A required decision would change Engine public contracts or make Engine select Host adapter.
- Existing state helpers cannot support atomic wait resolution + EventLog + new Attempt + dispatch record in one transaction or equivalent atomic flow.
- A proposed fix needs old DB compatibility or migration logic.
- `ResolveWaitRequest` cannot replace `outcome_ref` without compatibility wrapper.
- Adapter registry cannot derive `adapter_key` / `external_job_id` from Host-owned config and typed await spec.
- Late diagnostic idempotency cannot be made bounded/deterministic.
- Poller implementation would require long blocking inside `resolve_wait`.
- WAITING cancel would require physical external job cancel for Host terminal correctness.
- A slice needs files outside its allowed file list.
- Validation failure cannot be explained as an existing unrelated failure.

## 10. Blocking Questions For Controller

无。

## 11. Residual Risks

- Callback productization remains deferred. Owner: later callback adapter work unit. Phase 7 only keeps `WaitResolutionSource.CALLBACK` and common pipeline contract.
- External job physical cancel / revoke is best-effort only. Owner: later adapter hardening / external integration work unit.
- Cross-process / restart duplicate governance remains limited by Phase 6 run-local in-memory semantics. Owner: later recovery / durable duplicate ledger work only if a future requirement accepts that complexity.
- Recovery scan for existing `WAITING` Runs after Host restart should restore adapter observation, but full recovery dispatch remains Phase 11 owner. Phase 7 may implement minimal poll active wait discovery only.
- Tool trace projection and audit read models are not implemented here. Owner: projection / tool trace / audit phases consuming EventLog diagnostic facts.

## 12. Completion Report Format

Each implementation / fix agent report must include:

- Gate and slice id.
- Changed files.
- Implemented plan items.
- Tests and pyright commands run, with pass/fail summary.
- Docs decision and changed README files, if any.
- Residual risks classified as fixed now, covered by later slice, deferred to later phase/work unit, tracked by existing issue, or requiring controller/user decision.
- Stop status: complete or stopped with reason.
