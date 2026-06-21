# Host Phase 4 Public API Command Path Plan

- **current gate**: Phase 4 handoff implementation-ready plan
- **work unit**: Host Public API Command Path
- **plan status**: implementation-ready
- **blocking question count**: 0
- **artifact path**: `docs/host/phase4-public-api-command-path-plan.md`

本文档是 handoff-ready 且 code-generation-ready 的实施计划。implementation agent 只能按本文档指定的 slice、文件边界、公共契约和状态迁移实施；不得重新设计 Host public API、错误结构、EventLog cursor、cancel 子集语义或 deferred function 行为。

## 1. Goal / Motivation / Non-goals / Direct Evidence

### Goal

在不实现 Engine execution、ToolRuntime、Projection worker、Remote transport、wait adapter、destructive purge、full steer、retry / replay execution、active worker cancel、wait cancel 或 recovery cancel 的前提下，落地 Phase 4 Host public command path：

- Host command handle、factory options 与 command facet。
- `HostApiErrorCode.UNSUPPORTED_OPERATION`、受限 typed `HostApiError.detail` 与 `SteerConflictDetail`。
- `FollowupSnapshot.accepted_run_id` / `accepted_run_status`。
- EventLog-backed `stream_run_events`，使用全局 EventLog cursor truth，并暴露 public limit constants。
- public function facade：完整实现 Phase 1-3 可闭环函数；`cancel_session_runs` 只实现 queued / pre-dispatch `STARTING` 子集；其它后续能力返回 stable unsupported。

### Motivation

动机成立。Phase 3 已完成 durable state machine、admission 与 queued / pre-dispatch cancel 内部能力，但当前包根仍没有 public command facade，多入口调用方无法通过稳定函数式 API 操作 Host durable truth。Phase 4 要解决的是公共边界缺口，不是状态机重写。

问题严重性没有被高估：现有 `dayu.host.api.FollowupSnapshot` 仍无法表达 `submit_followup(queue)` 在无 active Run 时直接启动的新 `RUNNING` Run；`HostApiError` 仍缺少 typed detail；`HostApiErrorCode` 仍缺少 `UNSUPPORTED_OPERATION`；`stream_run_events` 尚无 public facade、limit 常量和过滤 cursor contract。这些都是 public contract 问题，不能留给 implementation agent 临场选择。

### Non-goals

Phase 4 不做以下事项：

- 不实现 Engine dispatch、scheduler、lane acquire、WorkerProxy / LocalProxy / RemoteProxy 或 `ATTEMPT_RUNNING`。
- 不实现 ToolRuntime、Tool fact accept、fetch_more、truncation 或工具治理。
- 不实现 Projection worker、audit、tool trace、outbox、memory projection 或 read-model catch-up。
- 不实现 wait adapter、wait record cancel、`resolve_wait` 结果治理或 external job cancel。
- 不实现 destructive `purge_session`、purge tombstone persistence 或 archive。
- 不实现 full steer Attempt switching、running/waiting Attempt stop、message rebuild 或 steer dispatch。
- 不实现 retry / replay execution。
- 不实现 dispatching / active worker cancel、`WAITING` cancel 或 `RECOVERING` cancel。
- 不修改 Engine / Fins / Service / UI / runtime，不新增反向依赖。
- 不把显式参数塞进 metadata / extra payload，不新增 god object、god dataclass、兼容 wrapper 或兼容 re-export。

### Direct Evidence

- `docs/host/implementation-control.md` Phase 4 条目将目标定义为函数式 Host command path、HostCallContext、OperationContext、幂等语义、snapshot 读取，以及 command path / background runtime facet 分离。
- `docs/host/implementation-control.md` Phase 4 范围明确完整实现 `ensure_session`、`create_session`、`get_session`、`close_session`、`start_run`、`submit_followup(queue)`、`get_run`、`stream_run_events`、queued / pre-dispatch `cancel_run`；`cancel_session_runs` 只覆盖 queued / pre-dispatch `STARTING`。
- `docs/host/implementation-control.md` 当前状态记录 Phase 4 design fix / write-back 已通过 AgentMiMo 与 AgentDS re-review，当前 gate 已进入 Phase 4 handoff implementation-ready plan gate。
- `docs/host/design.md` §10.1 定义 Host handle 是 composition root / handle，不是业务 God object；command path 与 background runtime supervisor 必须暴露不同 facet；mutating command 路径必须是 durable transaction -> EventLog / state index -> commit -> after-commit wakeup。
- `docs/host/design.md` §11 定义函数式公共接口集合和 Phase 4 public function behavior matrix；`submit_followup(steer)`、`retry_run`、`replay_run`、`resolve_wait`、`purge_session` 等为 stable unsupported / deferred。
- `docs/host/design.md` §11 明确 `FollowupSnapshot` 使用 `accepted_run_id` + `accepted_run_status`，queue 分支可为 `QUEUED` 或 `RUNNING`，`queued_run_id` 不能承载 running Run id。
- `docs/host/design.md` §11 明确 `HostApiError` 必须是 `code`、`message`、`retryable`、`detail?` 的受限 typed contract；第一版 detail 至少包含 `SteerConflictDetail`，禁止无结构 extra / payload / metadata god bag。
- `docs/host/design.md` §11 / §13 明确 `stream_run_events` 使用全局 EventLog `event_sequence` cursor truth；过滤后 empty result 也必须按扫描窗口推进 `next_cursor`。
- `docs/host/design.md` §22 明确 Phase 4 只实现 `cancel_session_runs` 的 queued / pre-dispatch `STARTING` 子集；dispatching / active worker、`WAITING`、`RECOVERING` cancel deferred 到 Phase 5 / 7 / 11。
- 当前代码事实：`dayu/host/api.py` 只定义公共类型，不实现 command path；`HostApiErrorCode` 缺少 `UNSUPPORTED_OPERATION`；`HostApiError` 缺少 typed detail；`FollowupSnapshot` 仍强制 queue 分支有 `queued_run_id`。
- 当前代码事实：`dayu/host/admission.py` 已有内部 `start_run`、`submit_followup_queue`、queued / pre-dispatch `cancel_run`、promotion 与 terminal closeout orchestration，但明确不实现 public facade、Engine dispatch、steer、retry、replay、wait 或 recovery。
- 当前代码事实：`dayu/host/durable/session_lifecycle.py` 已有 internal `ensure_session`、`create_session`、`close_session`；`dayu/host/durable/state.py` 已有 Session snapshot helper和 Run / Attempt / dispatch row readers；`dayu/host/durable/event_log.py` 已有 `read_events_after(cursor, limit)`。
- 当前代码事实：`dayu/host/README.md` 仍声明 Host command function 与 public facade 未实现；Phase 4 implementation 后必须同步。

## 2. Affected Files / Modules

### Production Files

- `dayu/host/api.py`
  - add public constants, refined public types, factory options, error detail union, function signatures if implementation chooses to colocate declarations.
  - update `__all__`.
- `dayu/host/__init__.py`
  - export Phase 4 public types, constants, handle factory and public command functions from package root.
- `dayu/host/command.py` new module
  - own concrete Host command handle, factory, lifecycle close, mutating public facade and stable unsupported functions.
- `dayu/host/read_api.py` new module
  - own public read facade helpers: `get_session`, `get_run`, `stream_run_events`, EventLog row -> `HostEventView`, row -> snapshot conversion.
- `dayu/host/admission.py`
  - add internal session-scope cancel orchestration for Phase 4 subset only.
  - do not export from package root.
- `dayu/host/durable/state.py`
  - add read helpers needed by public read / session-scope cancel: Run snapshot builder, non-terminal run listing, optional terminal summary extraction inputs if needed.
- `dayu/host/durable/event_log.py`
  - keep existing EventLog primitive as truth; add narrow reader only if `read_events_after` is insufficient for public stream implementation.
- `dayu/host/durable/transaction.py`
  - add typed read transaction support if read APIs would otherwise need to misuse `BEGIN IMMEDIATE` write transactions for pure reads.
- `dayu/host/README.md`
  - update current public command path, implemented / deferred function matrix, stream cursor contract and remaining non-goals.

### Test Files

- `tests/host/test_public_contracts.py`
  - update public enum / dataclass / error detail / constants validation.
- `tests/host/test_package_exports.py`
  - update package root and `dayu.host.api.__all__` expected exports.
- `tests/host/test_command_handle.py` new
  - cover factory options, handle lifecycle, command facet, no god-object public surface.
- `tests/host/test_public_session_api.py` new
  - cover `ensure_session`, `create_session`, `get_session`, `close_session`.
- `tests/host/test_public_run_api.py` new
  - cover `start_run`, `submit_followup(queue)`, `get_run`, `cancel_run`, public idempotency and conflicts.
- `tests/host/test_public_cancel_session_runs.py` new
  - cover Phase 4 session-scope cancel subset and unsupported deferred states.
- `tests/host/test_public_event_stream.py` new
  - cover EventLog-backed stream filtering, default/max limit and empty-result cursor advancement.
- Existing admission / durable tests under `tests/host/`
  - update only where public type shape changes require fixture updates.

## 3. Public Contract Changes

### Host Handle / Factory / Facet

Implementation must add a concrete public command handle that is opaque to callers but fully typed internally:

- `HostCommandHandle` concrete class or frozen dataclass in `dayu.host.command`.
- `HostCommandFacet` remains the narrow public Protocol, but must not be used as an excuse for `getattr` / `hasattr` dispatch. Public functions should accept the concrete `HostCommandHandle` unless the implementation proves a typed Protocol can expose required internal ports without leaking durable implementation.
- `create_host_command_handle(options: HostCommandHandleOptions) -> HostCommandHandle`.
- `close_host_command_handle(host: HostCommandHandle) -> None` or `HostCommandHandle.close() -> None`; choose one stable public lifecycle surface and test idempotent close.

`HostCommandHandleOptions` must be a typed public dataclass with explicit storage options. It must not be an untyped bag. Required fields:

- `host_handle_id: str | None`
- `db_path: pathlib.Path`
- `artifact_root: pathlib.Path`
- `create_parent_dirs: bool`
- `sqlite_busy_timeout_seconds: float`
- `sqlite_write_busy_retry_count: int`
- `sqlite_write_retry_initial_delay_seconds: float`
- `sqlite_write_retry_backoff_multiplier: float`
- `sqlite_write_retry_max_delay_seconds: float`
- `payload_inline_threshold_bytes: int`

Default values, if provided, must be module-level constants. Do not scatter numeric literals in method bodies. Factory maps this public options dataclass into internal `HostDurableStoreOptions`, `PayloadStoragePolicy` and `HostSQLiteStoragePolicy`.

The concrete handle may hold private references to `HostDurableStore`, `HostTransactionRunner`, `EventLogStore`, `IdempotencyStore` and `HostAdmissionService`. It must not expose these as public attributes and must not hold Service / UI / Engine / Fins dependencies.

### FollowupSnapshot

Replace the queue-only result shape with the design-fixed accepted-run shape:

- `accepted_input_ref: str`
- `behavior: FollowupBehavior`
- `accepted_run_id: str`
- `accepted_run_status: RunStatus`
- `current_cursor: HostStreamCursor`
- `queued_run_id: str | None`
- `target_run_id: str | None`

Validation rules:

- `accepted_input_ref` and `accepted_run_id` must be non-empty.
- For `behavior=QUEUE`, `target_run_id` must be `None`.
- For `behavior=QUEUE` and `accepted_run_status=QUEUED`, `queued_run_id` must equal `accepted_run_id`.
- For `behavior=QUEUE` and `accepted_run_status=RUNNING`, `queued_run_id` must be `None`.
- For `behavior=QUEUE`, Phase 4 must not allow `accepted_run_status` outside `QUEUED` / `RUNNING`.
- For `behavior=STEER`, Phase 4 normally returns `UNSUPPORTED_OPERATION` and does not produce a snapshot; validation may still allow future steer shape, but it must not require `queued_run_id`.

### HostApiErrorCode / HostApiError.detail

Add:

- `HostApiErrorCode.UNSUPPORTED_OPERATION = "unsupported_operation"`.
- `SteerConflictDetail` public frozen/slots dataclass:
  - `target_run_id: str`
  - `target_run_status: RunStatus | None`
  - `current_active_run_id: str | None`
  - `current_active_run_status: RunStatus | None`
- `HostApiErrorDetail` public type alias equal to the explicit union of detail dataclasses. First version: `SteerConflictDetail`.
- `HostApiError(..., detail: HostApiErrorDetail | None = None)`.

Rules:

- Do not add `extra`, `payload`, `metadata`, `dict[str, ...]` or JSON detail bag to `HostApiError`.
- Deferred functions must raise `HostApiError(code=HostApiErrorCode.UNSUPPORTED_OPERATION, retryable=False, detail=None)`.
- Steer conflict detail is frozen as public contract even though Phase 4 steer facade returns unsupported before full steer precondition evaluation.

### Stream Constants

Add and export public constants from `dayu.host.api` and package root:

- `HOST_EVENT_STREAM_DEFAULT_LIMIT = 100`
- `HOST_EVENT_STREAM_MAX_LIMIT = 1000`

`stream_run_events(host, run_id, cursor, limit=None)` semantics:

- `cursor` is a `HostStreamCursor`; `cursor.event_sequence` is the last consumed global EventLog sequence.
- `limit=None` uses `HOST_EVENT_STREAM_DEFAULT_LIMIT`.
- `limit` is the maximum number of global EventLog rows scanned in this call and therefore also an upper bound on returned events.
- `limit <= 0` or `limit > HOST_EVENT_STREAM_MAX_LIMIT` raises `HostApiError(INVALID_STATE, retryable=False)`.
- The function scans EventLog rows with `event_sequence > cursor.event_sequence`, filters to `row.run_id == run_id`, and maps rows to `HostEventView`.
- `next_cursor` is the maximum scanned global `event_sequence`; if no row was scanned, `next_cursor` equals input cursor.
- Empty filtered result still advances `next_cursor` when unrelated rows were scanned.
- It must not use projection checkpoint, session-local cursor, client sequence or in-memory subscription state as truth.

## 4. Public Function Behavior Matrix

| Function / path | Phase 4 behavior | Required result |
| --- | --- | --- |
| `ensure_session(host, request)` | 完整实现 | Calls internal session lifecycle and returns `SessionSnapshot`. |
| `create_session(host, request)` | 完整实现 | Calls internal lifecycle with public semantic digest and returns `SessionSnapshot`; idempotent replay returns current snapshot. |
| `get_session(host, session_id)` | 完整实现 | Reads durable Session truth and minimal Run indexes; no projection or execution. |
| `close_session(host, session_id, request)` | 完整实现 | Closes new input entry; does not cancel, purge or delete facts. |
| `start_run(host, request)` | 完整实现 Phase 1-3 admission | Supports `queue`, `reject`, `attach_active`; attach-active returns active `RunSnapshot` and appends no canonical attach fact. |
| `submit_followup(host, session_id, request)` with `QUEUE` | 完整实现 | Calls `submit_followup_queue`; returns `FollowupSnapshot(accepted_run_id, accepted_run_status)`. |
| `get_run(host, run_id)` | 完整实现 | Reads durable Run / current Attempt truth and returns `RunSnapshot`. |
| `stream_run_events(host, run_id, cursor, limit?)` | 完整实现 EventLog-backed read path | Uses global EventLog cursor truth and public limit constants. |
| `cancel_run(host, run_id, request)` queued | 完整实现 | `QUEUED -> CANCELLED`; no Attempt; returns `RunSnapshot`. |
| `cancel_run(host, run_id, request)` pre-dispatch `STARTING` | 完整实现 | `RUNNING/STARTING/pending dispatch -> CANCELLED`; no WorkerProxy; returns `RunSnapshot`; promotion may occur through existing admission behavior. |
| `cancel_session_runs(host, session_id, request)` | 子集实现 | In one session-scope operation cancels only queued and pre-dispatch `STARTING`; returns `SessionSnapshot`; unsupported active/wait/recovery states must not be silently ignored. |
| `submit_followup(host, session_id, request)` with `STEER` | stable unsupported / deferred | Raise `UNSUPPORTED_OPERATION`; no EventLog append, no Attempt switching. |
| `retry_run(host, run_id, request)` | stable unsupported / deferred | Raise `UNSUPPORTED_OPERATION`; request envelope remains stable. |
| `replay_run(host, run_id, request)` | stable unsupported / deferred | Raise `UNSUPPORTED_OPERATION`; request envelope remains stable. |
| `resolve_wait(host, wait_id, request)` | stable unsupported / deferred | Raise `UNSUPPORTED_OPERATION`; full wait governance belongs to Phase 7. |
| `purge_session(host, session_id, request)` | stable unsupported / deferred | Raise `UNSUPPORTED_OPERATION`; destructive cleanup belongs to Phase 15. |
| active dispatch cancel | stable unsupported / deferred | Do not fake active worker cancel; Phase 5 owns dispatching / WorkerProxy cancel propagation. |
| wait cancel | stable unsupported / deferred | Do not mutate wait records; Phase 7 owns `WAITING` closeout. |
| recovery cancel | stable unsupported / deferred | Do not mutate recovery state; Phase 11 owns `RECOVERING` cancel. |

## 5. Implementation Slices

### Slice P4-S1 Public Types, Error Detail, Handle Options And Constants

Objective:

- Freeze all Phase 4 public type changes before command implementation.

Allowed files/modules:

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_package_exports.py`
- `dayu/host/README.md` only if this slice is implemented alone and docs must note type contract changes.

Exact changes:

- Add `HostApiErrorCode.UNSUPPORTED_OPERATION`.
- Add `SteerConflictDetail` and `HostApiErrorDetail` typed alias.
- Add optional `detail` parameter/property to `HostApiError`.
- Replace `FollowupSnapshot` fields and validation with accepted-run shape.
- Add `HOST_EVENT_STREAM_DEFAULT_LIMIT` and `HOST_EVENT_STREAM_MAX_LIMIT`.
- Add `HostCommandHandleOptions` typed dataclass and validation helpers.
- Update `__all__` in `api.py` and package root exports.
- Keep all new signatures fully typed; no `Any`, `object`, untyped parameters or untyped returns.

State transitions:

- None. This slice must not open durable store or mutate EventLog / state rows.

Non-goals:

- No command facade.
- No durable store opening.
- No admission wiring.
- No deferred function implementation.

Tests:

- Enum values include `UNSUPPORTED_OPERATION`.
- `HostApiError` stores `detail=None` and `SteerConflictDetail` without unstructured payload.
- `FollowupSnapshot` accepts queue `QUEUED` and queue `RUNNING` shapes and rejects running Run in `queued_run_id`.
- Stream constants are exported and `DEFAULT <= MAX`.
- `HostCommandHandleOptions` rejects empty handle id when present, invalid paths and non-positive numeric options.
- Package exports match expected public symbols.

Validation commands:

```bash
source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_package_exports.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
```

Stop conditions:

- Stop if `HostApiError.detail` cannot be represented as an explicit typed union without an unstructured bag.
- Stop if `FollowupSnapshot` changes would require backward-compatible duplicate fields beyond the design-approved optional `queued_run_id`.

### Slice P4-S2 Session Public APIs And Snapshots

Objective:

- Add Host command handle/factory and public session facade functions.

Allowed files/modules:

- `dayu/host/command.py`
- `dayu/host/read_api.py`
- `dayu/host/api.py` only for missing type/docstring refinements discovered in S1 scope.
- `dayu/host/__init__.py`
- `dayu/host/durable/transaction.py` if adding read transaction support.
- `dayu/host/durable/state.py` for narrow snapshot/read helpers.
- `tests/host/test_command_handle.py`
- `tests/host/test_public_session_api.py`

Exact changes:

- Implement `HostCommandHandle` with private durable store and service dependencies.
- Implement `create_host_command_handle(options)` by mapping public options to internal durable options and opening `HostDurableStore`.
- Implement idempotent close.
- Implement public `ensure_session`, `create_session`, `get_session`, `close_session`.
- Compute public semantic digest in facade using canonical JSON over explicit request fields and context digest; do not include runtime-only objects or metadata bags.
- Add read transaction helper if needed so `get_session` does not use a write transaction for pure read.
- `get_session` reads `SessionRow`, current slot, active run id and queued run ids from durable truth.
- Not found Session returns `HostApiErrorCode.NOT_FOUND`.

State transitions:

- `ensure_session`: creates Session + slot if absent; existing slot returns existing Session.
- `create_session`: creates new Session and optional slot rebind; idempotent replay returns existing Session snapshot.
- `close_session`: `OPEN -> CLOSED`; does not cancel queued or active runs; idempotent replay returns current closed snapshot.
- `get_session`: no transition.

Non-goals:

- No Run admission.
- No EventLog stream.
- No purge implementation.
- No background supervisor facet beyond the narrow command handle identity.

Tests:

- Factory opens fresh DB and exposes only stable handle id publicly.
- Handle close is idempotent; calls after close fail predictably.
- `ensure_session` repeated calls return same `SessionSnapshot`.
- `create_session` idempotent replay returns same Session; same key different digest returns `IDEMPOTENCY_CONFLICT`.
- `close_session` is idempotent and does not remove existing Session.
- `get_session` returns `NOT_FOUND` for missing Session.
- Import boundary still excludes Engine / Fins / Service / UI.

Validation commands:

```bash
source .venv/bin/activate && pytest tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_session_lifecycle.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
```

Stop conditions:

- Stop if public handle needs to expose durable transaction runner, admission service, store connection or other internal mutable dependencies.
- Stop if session APIs require modifying `docs/host/design.md`; that means the design truth is insufficient.

### Slice P4-S3 Run Admission, Follow-up Queue, Cancel Run And Cancel Session Runs Subset

Objective:

- Wire Phase 3 internal admission into public run/follow-up/cancel facade and implement session-scope cancel subset.

Allowed files/modules:

- `dayu/host/command.py`
- `dayu/host/read_api.py`
- `dayu/host/admission.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py` only for narrow reusable helper extraction; do not change core transition semantics unless tests prove a root-cause bug.
- `tests/host/test_public_run_api.py`
- `tests/host/test_public_cancel_session_runs.py`
- Existing admission tests only for fixture updates.

Exact changes:

- Implement public `start_run(host, request) -> RunSnapshot`.
- Implement public `submit_followup(host, session_id, request) -> FollowupSnapshot`.
  - Validate `session_id` argument equals `request.session_id`; mismatch raises `HostApiErrorCode.INVALID_STATE`.
  - `behavior=QUEUE` calls `HostAdmissionService.submit_followup_queue`.
  - `behavior=STEER` raises `UNSUPPORTED_OPERATION` with `retryable=False`.
- Implement public `cancel_run(host, run_id, request) -> RunSnapshot`.
  - Let internal admission handle queued and pre-dispatch `STARTING`.
  - If internal admission reports unsupported status, map to `UNSUPPORTED_OPERATION` only when the status belongs to a deferred capability; keep true invalid preconditions as `INVALID_STATE`.
- Implement internal `cancel_session_runs` service method for Phase 4 subset.
  - Use idempotency scope `(operation="cancel_session_runs", scope_id=session_id, idempotency_key=request.client_request_id)`.
  - Semantic digest includes session id, request context digest, reason and mode; it must not include dynamic current run list.
  - In one write transaction, read all non-terminal runs for the session.
  - If any non-terminal Run is outside supported subset, raise `UNSUPPORTED_OPERATION` before appending any cancel facts.
  - Supported subset is:
    - `QUEUED` Run.
    - `RUNNING` Run whose current Attempt is `STARTING` and dispatch record is `PENDING`.
  - For each queued Run append `CANCEL_REQUESTED` + `RUN_CANCELLED` and set Run `CANCELLED`.
  - For each pre-dispatch starting Run append `CANCEL_REQUESTED` + `ATTEMPT_CANCELLED` + `RUN_CANCELLED`; set dispatch record `CANCELLED`, Attempt `CANCELLED`, Run `CANCELLED`.
  - Do not trigger queue promotion during session-scope cancel; the operation is cancelling the session's current non-terminal subset, not freeing a slot to start more work.
  - If no supported non-terminal Run exists, record session-scope idempotency with Session result ref and no created event.
  - Return current `SessionSnapshot`.
- Add `read_non_terminal_runs_for_session` and any needed dispatch / attempt reader helpers in `state.py`.

State transitions:

- `start_run` no active: Session `OPEN` -> new Run `RUNNING`, Attempt `STARTING`, dispatch record `PENDING`.
- `start_run` active + queue: new Run `QUEUED`.
- `start_run` active + reject: no mutation, `CONFLICT`.
- `start_run` active + attach_active: no canonical EventLog attach fact; returns active `RunSnapshot`; idempotency explains request.
- `submit_followup(queue)` active: new Run `QUEUED`; `FollowupSnapshot.accepted_run_status=QUEUED`, `queued_run_id=accepted_run_id`.
- `submit_followup(queue)` no active: new Run `RUNNING`; `FollowupSnapshot.accepted_run_status=RUNNING`, `queued_run_id=None`.
- `cancel_run` queued: `QUEUED -> CANCELLED`; no Attempt.
- `cancel_run` pre-dispatch starting: Run / Attempt / dispatch record all close to cancelled; no WorkerProxy.
- `cancel_session_runs` subset: batch applies the two supported cancel transitions; does not cancel dispatching active worker, `WAITING` or `RECOVERING`.

Non-goals:

- No Engine dispatch.
- No dispatching / active worker cancel propagation.
- No wait record cancel.
- No recovery cancel.
- No retry/replay/steer execution.
- No silent partial cancel when unsupported non-terminal Run exists.

Tests:

- `start_run` public facade returns `RunSnapshot` for direct running and attach-active.
- Public idempotency replay returns latest durable snapshot and does not append duplicate facts.
- Same idempotency key different semantic digest returns `IDEMPOTENCY_CONFLICT`.
- `submit_followup(queue)` with active returns `accepted_run_status=QUEUED`.
- `submit_followup(queue)` with no active returns `accepted_run_status=RUNNING` and does not fill `queued_run_id`.
- `submit_followup(steer)` returns `UNSUPPORTED_OPERATION`, no EventLog append.
- `cancel_run` queued and pre-dispatch starting return cancelled `RunSnapshot`.
- Public cancel / promotion race covers API-level first-committer-wins, not just internal durable tests.
- `cancel_session_runs` cancels multiple queued Runs plus one pre-dispatch active Run in the same Session.
- `cancel_session_runs` does not affect another Session.
- `cancel_session_runs` idempotent replay does not cancel new Runs accepted after the first operation with the same client_request_id.
- Unsupported non-terminal state returns `UNSUPPORTED_OPERATION` and leaves eligible queued Runs untouched, proving no partial mutation.

Validation commands:

```bash
source .venv/bin/activate && pytest tests/host/test_public_run_api.py tests/host/test_public_cancel_session_runs.py tests/host/test_admission_queue.py tests/host/test_admission_multiprocess.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
```

Stop conditions:

- Stop if implementing session-scope cancel requires active worker, wait record or recovery logic.
- Stop if existing low-level transition helpers cannot batch the supported subset without promotion side effects; report the root-cause gap to controller instead of adding ad hoc partial updates.
- Stop if unsupported states would be silently ignored or partially cancelled.

### Slice P4-S4 Read APIs, Event Stream And Deferred Facade Behavior

Objective:

- Complete public read APIs, EventLog stream cursor behavior and stable unsupported public functions.

Allowed files/modules:

- `dayu/host/read_api.py`
- `dayu/host/command.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/transaction.py`
- `tests/host/test_public_event_stream.py`
- `tests/host/test_public_run_api.py` for deferred function assertions if not already covered.
- `dayu/host/README.md`

Exact changes:

- Implement `get_run(host, run_id) -> RunSnapshot`.
  - Read durable Run row.
  - Read current Attempt id from Run row.
  - `event_cursor` is the max non-null EventLog sequence known on the Run row: terminal, started, queued, accepted, input.
  - `terminal_result_summary` is `None` for non-terminal; for terminal rows, derive from terminal event payload if summary refs exist, otherwise use status with `summary_ref=None` and `summary_digest=None`.
  - `outbox_summary` remains `None` in Phase 4 because outbox projection is not implemented.
- Implement `stream_run_events`.
  - Validate run exists first; missing run returns `NOT_FOUND`.
  - Use public constants and cursor rules from Section 3.
  - Map `EventLogRow` to `HostEventView` using event sequence, id, event type, session id, run id, payload ref and payload digest.
  - Do not expose policy decision JSON, reason JSON or full payload JSON through `HostEventView`.
- Implement stable unsupported functions:
  - `retry_run`
  - `replay_run`
  - `resolve_wait`
  - `purge_session`
  - any deferred branch not implemented in S3.
- Update package exports for public function names.
- Update Host README.

State transitions:

- `get_run`, `get_session`, `stream_run_events`: no transition.
- Deferred functions: no transition and no EventLog append.

Non-goals:

- No projection truth.
- No outbox projection.
- No purge tombstone table.
- No wait result accept.
- No retry / replay Run creation.
- No full steer.

Tests:

- `get_run` missing returns `NOT_FOUND`.
- `get_run` returns current status, current attempt id and event cursor for queued/running/cancelled Runs.
- `stream_run_events` returns only target Run events.
- `stream_run_events` with unrelated scanned events returns empty events and advanced `next_cursor`.
- `stream_run_events` with no scanned rows returns input cursor.
- `stream_run_events` rejects limit 0 and limit greater than `HOST_EVENT_STREAM_MAX_LIMIT`.
- `stream_run_events` default uses `HOST_EVENT_STREAM_DEFAULT_LIMIT`.
- Deferred functions raise `UNSUPPORTED_OPERATION`, `retryable=False`, `detail=None`, and append no EventLog rows.
- Host README documents implemented vs deferred functions without claiming final cancel semantics.

Validation commands:

```bash
source .venv/bin/activate && pytest tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
```

Stop conditions:

- Stop if `stream_run_events` needs projection checkpoint, memory state, outbox state or in-memory subscription position to satisfy tests.
- Stop if deferred functions need to write EventLog or idempotency records to appear stable.
- Stop if terminal summary cannot be derived without parsing untyped payload ad hoc; in that case return `TerminalResultSummary(status=..., summary_ref=None, summary_digest=None)` and document the Phase 4 limitation in Host README.

## 6. Cross-slice Invariants

- All modules and classes must have Chinese overview docstrings.
- All public and private functions added by implementation must have complete Chinese docstrings containing parameters, returns and exceptions.
- No new signature may use `Any`, `object`, untyped parameters or untyped returns.
- Do not use `hasattr` / `getattr` for handle dispatch; use concrete type or typed Protocol.
- Do not use lazy imports unless there is a documented import-cycle root cause.
- Do not add compatibility re-export / wrapper / facade.
- Do not create schema migration or old DB compatibility path; current project rule is fresh schema only unless explicitly requested.
- Do not introduce unstructured metadata, extra payload, dict bag or god builder.
- Do not make `dayu.runtime` carry Host governance, EventLog or business semantics.
- `dayu.host` must not import `dayu.engine`, `dayu.fins`, `dayu.service` or `dayu.ui`.

## 7. Documentation Decision

`dayu/host/README.md` must be updated because Phase 4 changes `dayu/host/` public API behavior and removes the current statement that Host command facade is unimplemented.

`dayu/README.md` is not required unless implementation changes the overall `UI -> Service -> Host -> Engine` boundary, construction topology visible to all developers, or package-level reading order. This plan does not require such a change.

Root `README.md` is not required because Phase 4 does not add CLI usage, render/trace user workflow, project installation/configuration steps or user-facing commands.

`tests/README.md` is not required unless implementation adds a new testing layer or changes the standard Host validation command. Adding more `tests/host/test_public_*.py` files under the existing Host test layer does not by itself require a README update.

## 8. Plan Risks / Open Questions

### Blocking Questions For Controller

None.

### Non-blocking Risks

- `HostCommandHandleOptions` duplicates some durable storage policy fields as public construction options. This is intentional for explicit public composition-root configuration. Implementation must map them to internal durable options in one place and avoid two divergent default sets.
- `stream_run_events.limit` is defined as scan-window size, not "number of returned target Run events". This is the only bounded way to satisfy the design requirement that empty filtered results can advance `next_cursor` without unbounded scans. If later product UX needs "return up to N target events", Phase 8 can add a read-model API without changing this EventLog truth contract.
- Terminal summary extraction is limited by current Run row shape. Phase 4 should derive summary refs from terminal event payload only if it can do so via structured JSON parsing with typed validation; otherwise return a status-only `TerminalResultSummary`.
- `cancel_session_runs` Phase 4 subset is intentionally not final session-scope cancel semantics. Phase 5 / 7 / 11 must complete dispatching active worker, `WAITING` and `RECOVERING` paths respectively.

## 9. Completion Report Format

Each implementation slice must report:

- changed files
- implemented plan items
- tests and pyright commands run with results
- docs updated or explicit docs decision
- residual risks classified as current slice / later slice / later phase / controller decision
- stop conditions encountered, if any

Final Phase 4 implementation closeout must explicitly state:

- what changed
- what was verified
- which README files were updated
- whether `cancel_session_runs` remains a subset and which owners complete it
- any residual risk or uncovered area
