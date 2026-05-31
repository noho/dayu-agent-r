# Host Phase 3 Session / Run / Attempt 状态机与 Admission Plan

- **current gate**: Phase 3 plan
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **plan status**: plan-fix-applied-ready-for-re-review
- **blocking question count**: 0
- **artifact path**: `docs/host/phase3-session-run-attempt-admission-plan.md`

本文档是 handoff-ready 且 code-generation-ready 的实施计划。implementation agent 只能按本文档指定的 slice 和文件边界实施；不得重新设计 schema、状态迁移、幂等范围、CAS 语义、dispatch record 语义或测试范围。

## 1. Goal / Motivation / Success Signal / Direct Evidence

### Goal

在不启动 Engine、WorkerProxy、scheduler、lane 或 ToolRuntime 的前提下，实现 Host Phase 3 的 durable governance 状态机：

- Session 创建、slot 幂等确保、显式创建并可选重绑定、关闭。
- Run / Attempt durable state indexes。
- start_run 与 submit_followup(queue) admission。
- 同 Session durable queue，按 accepted `event_sequence` FIFO promotion。
- Attempt `STARTING` + minimal dispatch record `pending` startup truth。
- queued cancel 与 pre-dispatch starting cancel。
- 内部 terminal closeout helper，用于测试 Phase 3 闭环并供后续 EngineEvent ingest 复用。
- 所有 mutating transition 通过 EventLog canonical facts、state indexes、operation idempotency 与 CAS-style 条件更新在同一 SQLite write transaction 内完成。

### Motivation

动机成立。当前 Host durable foundation 已有 SQLite schema bootstrap、EventLog、idempotency、transaction runner、payload/artifact/liveness primitives，但还没有 Session / Run / Attempt 状态真源，也没有 admission / queue / promotion 约束。按设计，Host 架构是宿主强约束下的 `LLM in the loop`，同一 Session 同时最多一个 active Run；该不变量必须由 Host durable store 和 CAS 保护，不能依赖内存队列、Engine 行为或 UI / Service 先读后写。

### Success Signal

Phase 3 完成后，Host 在不调用 Engine 的情况下应满足：

- 并发 `ensure_session(scope, slot_key)` 返回同一 slot Session，调用方不可见孤儿 Session。
- 同一 Session 并发 start / follow-up 后，SQLite partial unique index 保证最多一个 active Run。
- active Run 存在时 follow-up queue 产生 durable `QUEUED` Run，释放 active slot 后只 promotion 一个 queued Run。
- queue promotion 顺序只由 queued Run 的 accepted `event_sequence` 决定。
- `(session_id, client_request_id)` 或 `(run_id, client_request_id)` 等幂等范围重复请求返回同一结果；同 key 不同 semantic digest 返回 `idempotency_conflict`。
- cancel queued 不创建 Attempt；cancel pre-dispatch starting 将 Attempt 和 dispatch record 收口为 cancelled，且不通知 WorkerProxy。
- terminal / cancel closeout 释放 active slot 后触发同 Session promotion check。
- 多进程测试证明 active invariant、slot unique、EventLog global sequence 和 first-committer-wins 竞态成立。
- `python -m pyright dayu/host tests/host` 通过，无新增或扩散类型错误。

### Direct Evidence

- `docs/host/design.md` §5 定义 Session 只有 `OPEN` / `CLOSED`，close 不 cancel、不删除、不清空历史；closed Session 拒绝新 Run / follow-up / steer，但允许读取和 cancel 已有 Run。
- `docs/host/design.md` §6 定义 `(scope, slot_key)` 唯一映射到当前 Session，`ensure_session` 由 slot 幂等，`create_session` 由 `client_request_id` 幂等，创建和 slot 绑定必须同事务。
- `docs/host/design.md` §7 / §8 定义 Run / Attempt 状态集合、终态和 `Run RUNNING + Attempt STARTING` 是合法组合。
- `docs/host/design.md` §9 定义同一 Session 同时最多一个 active Run，`QUEUED` Run 必须 durable accepted，queue FIFO 只按 accepted `event_sequence`。
- `docs/host/design.md` §9.1 定义 Phase 3 owned transition subset，并明确不包含 Engine dispatch、ToolRuntime、wait record、steer、retry / replay、context compaction 或 recovery。
- `docs/host/design.md` §10 定义 Phase 3 durable state / index contract：Session / slot / Run / Attempt / dispatch record 与 EventLog 同事务；active Run invariant 第一版优先用 SQLite partial unique index；fallback 只能回到 design discussion。
- `docs/host/design.md` §11 定义 Host public API 类型、HostCallContext、operation idempotency semantic contract 和错误分类。
- `docs/host/design.md` §22 定义 queued cancel 与 pre-dispatch starting cancel 语义。
- `docs/host/implementation-control.md` Phase 3 条目确认进入条件已满足、范围、非目标、关键设计问题、验证要求和后续依赖。
- `docs/reviews/gateflow-phase-design-re-review-host-p3-controller-adjudication-20260514.md` 确认 BQ1 / BQ2 / BQ3 / F1 均 fixed，Phase 3 design refinement gate passed，允许进入 plan gate。
- 当前代码事实：`dayu/host/api.py` 已有 Phase 1 public request / snapshot / status / error 类型；`dayu/host/durable/schema.py` 只创建 Phase 2 foundation tables；`event_log.py`、`idempotency.py`、`transaction.py` 已提供 transaction-scoped primitives；`tests/host` 已覆盖 durable foundation 与多进程 EventLog smoke。

## 2. Non-goals And Scope Boundary

### Explicit Non-goals

Phase 3 不做以下事项：

- 不做 Engine dispatch。
- 不做 dispatch scheduler。
- 不做 lane acquire。
- 不做 WorkerProxy。
- 不做 LocalProxy。
- 不做 RemoteProxy。
- 不做 EngineEvent ingest。
- 不做 ToolRuntime。
- 不做 wait record。
- 不做 `resolve_wait`。
- 不做 steer。
- 不做 retry / replay。
- 不做 context compaction。
- 不做 recovery scan。
- 不把 dispatch record 推进到 `dispatching`。
- 不 append `ATTEMPT_RUNNING`。
- 不启动 EngineWorker。
- 不实现 public API 全量 facade。
- 不实现 projection、audit、outbox、memory、tool trace 或 purge。
- 不修改 Engine/Fins/Service/UI/runtime，除非 plan review 后 controller 另行确认。

### Scope Boundary

- Phase 3 可以新增 Host 内部 state/admission modules，并可以修改 `dayu/host/durable/schema.py`、Host tests、`dayu/host/README.md`、`tests/README.md`。
- Phase 3 可以消费既有 `dayu.host.api` 类型，但默认不改变 `dayu.host.api` 公共 request / snapshot 类型。若 implementation 发现现有 public dataclass 不足以表达 Phase 3 internal service 输入，必须优先新增 Host 内部 dataclass，不得把内部 durable row 暴露到公共命名空间。
- Phase 3 的 command surface 是 Host 内部 transition/admission service，不是最终 public facade。Phase 4 owns public API command path facade、policy provider integration、request-to-service composition 和 public error envelope wiring。
- Phase 3 可提供 internal terminal closeout helper，只允许由测试和后续 EngineEvent ingest 调用；它不读取或解释 EngineEvent。
- Phase 3 的 after-commit behavior 只允许唤醒或同步触发同 Session queue promotion check，以及记录 pending dispatch diagnostic result。任何真实 dispatch、lane acquire 或 WorkerProxy side effect 都必须留给 Phase 5。

## 3. Affected Files / Modules

### Allowed Production Files

- `dayu/host/durable/schema.py`
  - bump `HOST_SCHEMA_VERSION` from `1` to `2`。
  - add table constants and DDL for Phase 3 state/index tables.
  - add partial unique index and FIFO queue index DDL.
  - keep fresh schema only; no compatibility migration.
- `dayu/host/durable/state.py` new module
  - owns row dataclasses, row codecs, typed status serialization, and low-level CRUD/CAS helpers for Session / slot / Run / Attempt / dispatch record.
  - depends only on `dayu.host.api` status enums, durable codec/validation/errors/schema/transaction, and stdlib.
- `dayu/host/durable/session_lifecycle.py` new module
  - owns `ensure_session`, `create_session`, `close_session` internal lifecycle service functions.
  - uses `EventLogStore`, `IdempotencyStore`, `state.py`, and transaction runner provided by caller.
- `dayu/host/durable/run_transition.py` new module
  - owns Run / Attempt transition helpers: create accepted queued/running run, create starting attempt and pending dispatch record, terminal closeout, cancel queued, cancel pre-dispatch starting.
- `dayu/host/admission.py` new module
  - owns internal admission service orchestration for start_run and submit_followup(queue), queue promotion, after-commit promotion/wakeup port, and internal result dataclasses.
  - does not import Engine, runtime lane, WorkerProxy, LocalProxy, RemoteProxy, Service, UI or Fins.
- `dayu/host/__init__.py`
  - only if a deliberately public Phase 3 internal service type must be exported. Default decision: do not modify.
- `dayu/host/api.py`
  - default decision: do not modify. Existing statuses, requests, snapshots and errors are sufficient for Phase 3 internal services. If plan review finds a missing public enum or error code, stop and route through controller before changing.
- `dayu/host/README.md`
  - update current Host durable/state facts after implementation.

### Allowed Test Files

- `tests/host/test_state_schema.py` new.
- `tests/host/test_session_lifecycle.py` new.
- `tests/host/test_run_attempt_transitions.py` new.
- `tests/host/test_admission_queue.py` new.
- `tests/host/test_admission_multiprocess.py` new.
- `tests/host/test_durable_schema.py` may be updated for schema version/table set expectations.
- `tests/host/test_import_boundary.py` and `tests/host/test_weak_typing_guard.py` may be updated only if new Host modules need to be covered.
- `tests/README.md` update after new Host test categories exist.

### Forbidden Unless Controller Confirms After Plan Review

- `dayu/engine/`
- `dayu/fins/`
- `dayu/service/`
- `dayu/ui/`
- `dayu/runtime/`
- Engine contract tests.
- Service/UI integration tests.
- CLI or render entry points.

## 4. Contract / Schema / State-machine / Public-interface Changes

### Schema Contract

`HOST_SCHEMA_VERSION` must become `2`. Fresh bootstrap creates Phase 2 foundation tables plus Phase 3 state/index tables. A DB with another `user_version` continues to fail with `HostSchemaMismatchError`; no migration, compatibility read, old schema fallback or legacy test is allowed.

#### `host_sessions`

Purpose: Session lifecycle truth.

Columns:

- `session_id TEXT PRIMARY KEY`
- `status TEXT NOT NULL CHECK (status IN ('open', 'closed'))`
- `metadata_json TEXT NOT NULL`
- `created_event_id TEXT NOT NULL`
- `created_event_sequence INTEGER NOT NULL`
- `closed_event_id TEXT NULL`
- `closed_event_sequence INTEGER NULL`
- `created_at TEXT NOT NULL`
- `closed_at TEXT NULL`

Constraints:

- `created_event_id` FK to `event_log(event_id)`.
- `created_event_sequence` FK to `event_log(event_sequence)`.
- `closed_event_id` / `closed_event_sequence` both null or both non-null.
- closed status requires `closed_at`, `closed_event_id`, `closed_event_sequence`.
- open status requires closed fields null.

#### `host_session_slots`

Purpose: current slot binding truth.

Columns:

- `scope TEXT NOT NULL`
- `slot_key TEXT NOT NULL`
- `session_id TEXT NOT NULL`
- `bound_event_id TEXT NOT NULL`
- `bound_event_sequence INTEGER NOT NULL`
- `metadata_json TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Constraints:

- primary key `(scope, slot_key)`.
- `session_id` FK to `host_sessions(session_id)`.
- `bound_event_id` / `bound_event_sequence` FK to EventLog.
- unique `(scope, slot_key)` is the durable idempotency truth for `ensure_session`.

#### `host_runs`

Purpose: Run lifecycle and queue truth.

Columns:

- `run_id TEXT PRIMARY KEY`
- `session_id TEXT NOT NULL`
- `status TEXT NOT NULL CHECK (status IN ('queued','running','waiting','cancelling','recovering','succeeded','failed','cancelled','lost'))`
- `client_request_id TEXT NOT NULL`
- `input_event_id TEXT NOT NULL`
- `input_event_sequence INTEGER NOT NULL`
- `accepted_event_id TEXT NOT NULL`
- `accepted_event_sequence INTEGER NOT NULL`
- `queued_event_id TEXT NULL`
- `queued_event_sequence INTEGER NULL`
- `started_event_id TEXT NULL`
- `started_event_sequence INTEGER NULL`
- `terminal_event_id TEXT NULL`
- `terminal_event_sequence INTEGER NULL`
- `current_attempt_id TEXT NULL`
- `source_run_id TEXT NULL`
- `source_run_relation TEXT NULL CHECK (source_run_relation IN ('retry','replay') OR source_run_relation IS NULL)`
- `execution_target TEXT NOT NULL`
- `queue_policy TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `terminal_at TEXT NULL`

Constraints:

- `session_id` FK to `host_sessions(session_id)`.
- event refs FK to `event_log`.
- `source_run_id` FK to `host_runs(run_id)`.
- queued status requires `queued_event_id` / `queued_event_sequence` and no `current_attempt_id`.
- running/waiting/cancelling/recovering may have `current_attempt_id` when an Attempt lifecycle exists; Phase 3 creates it for `RUNNING`.
- terminal statuses require terminal event refs and `terminal_at`.
- non-terminal statuses require terminal fields null.
- `source_run_id` and `source_run_relation` are both null or both non-null. Phase 3 writes null.

Indexes:

- `CREATE UNIQUE INDEX host_runs_one_active_per_session ON host_runs(session_id) WHERE status IN ('running','waiting','cancelling','recovering')`
- `CREATE INDEX host_runs_queue_fifo ON host_runs(session_id, accepted_event_sequence, run_id) WHERE status = 'queued'`
- `CREATE INDEX host_runs_session_status ON host_runs(session_id, status, accepted_event_sequence)`

Do not add `UNIQUE(session_id, client_request_id)` to `host_runs`. Operation idempotency is owned by `idempotency_records` with explicit `scope_kind`; a table-level unique index would silently conflate `start_run` and `submit_followup_queue` semantics.

Active Run invariant:

- The partial unique index on `(session_id)` for active statuses is mandatory.
- If implementation or review proves SQLite partial unique index cannot satisfy the project/test constraints, implementation must stop and return to design discussion. The fallback cannot be an implementation-agent choice.

Queue FIFO:

- queued Run order is `ORDER BY accepted_event_sequence ASC, run_id ASC`.
- `accepted_event_sequence` comes from the `RUN_ACCEPTED` event row, not from `RUN_QUEUED`, in-memory notification order or after-commit wakeup order.

#### `host_attempts`

Purpose: Attempt lifecycle truth.

Columns:

- `attempt_id TEXT PRIMARY KEY`
- `run_id TEXT NOT NULL`
- `execution_id TEXT NOT NULL UNIQUE`
- `status TEXT NOT NULL CHECK (status IN ('starting','running','succeeded','failed','cancelled','suspended','steered','lost'))`
- `started_event_id TEXT NOT NULL`
- `started_event_sequence INTEGER NOT NULL`
- `terminal_event_id TEXT NULL`
- `terminal_event_sequence INTEGER NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `terminal_at TEXT NULL`

Constraints:

- `run_id` FK to `host_runs(run_id)`.
- event refs FK to EventLog.
- terminal statuses require terminal event refs and `terminal_at`.
- non-terminal statuses require terminal fields null.
- old Attempt never resumes; new execution always gets a new `attempt_id` and new `execution_id`.

#### `host_attempt_dispatch_records`

Purpose: minimal dispatch record startup truth.

Phase 3 only supports statuses:

- `pending`
- `cancelled`

Columns:

- `dispatch_record_id TEXT PRIMARY KEY`
- `run_id TEXT NOT NULL`
- `attempt_id TEXT NOT NULL UNIQUE`
- `execution_id TEXT NOT NULL UNIQUE`
- `status TEXT NOT NULL CHECK (status IN ('pending','cancelled'))`
- `worker_kind TEXT NOT NULL CHECK (worker_kind IN ('local','remote'))`
- `execution_target TEXT NOT NULL`
- `owner_host_instance_id TEXT NULL`
- `created_event_id TEXT NOT NULL`
- `created_event_sequence INTEGER NOT NULL`
- `cancelled_event_id TEXT NULL`
- `cancelled_event_sequence INTEGER NULL`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `cancelled_at TEXT NULL`

Constraints:

- `run_id` FK to `host_runs(run_id)`.
- `attempt_id` FK to `host_attempts(attempt_id)`.
- `execution_id` FK to `host_attempts(execution_id)`.
- `owner_host_instance_id` nullable FK to `host_instances(host_instance_id)`.
- event refs FK to EventLog.
- pending status requires cancelled fields null.
- cancelled status requires cancelled event refs and `cancelled_at`.

Phase 3 must not add `dispatching`, `waiting_for_lane` or worker accepted states. If a future phase needs those states, that phase owns the schema decision.

### Canonical Event Types And Minimal Payloads

All events below use `EventClass.CANONICAL_FACT`, deterministic canonical JSON payloads, fixed UTC timestamps and explicit scope fields. Required state-machine fields must be structured payload fields, not metadata.

Phase 3 emits only these owned canonical event types:

- `SESSION_CREATED`
- `SESSION_CLOSED`
- `USER_INPUT_ACCEPTED`
- `RUN_ACCEPTED`
- `RUN_QUEUED`
- `RUN_STARTED`
- `ATTEMPT_STARTED`
- `CANCEL_REQUESTED`
- `ATTEMPT_CANCELLED`
- `RUN_CANCELLED`
- `ATTEMPT_SUCCEEDED`
- `ATTEMPT_FAILED`
- `ATTEMPT_LOST`
- `RUN_SUCCEEDED`
- `RUN_FAILED`
- `RUN_LOST`

`FOLLOWUP_QUEUED` exists in the broader canonical event collection, but Phase 3 must follow §9.1 transition truth: `submit_followup(queue)` appends `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_QUEUED` or `RUN_STARTED` / `ATTEMPT_STARTED`. Implementation must not add `FOLLOWUP_QUEUED` unless a plan review finding sends this back to controller/design discussion.

Minimal payload expectations:

- `SESSION_CREATED`
  - scope: `session_id`
  - payload: `session_id`, `metadata_digest`, `slot_scope`, `slot_key`, `created_by_operation`, `call_context_digest`
- `SESSION_CLOSED`
  - scope: `session_id`
  - payload: `session_id`, `reason`, `closed_by_operation`, `call_context_digest`
- `USER_INPUT_ACCEPTED`
  - scope: `session_id`, `run_id`, `client_request_id`
  - payload: `input_ref`, `input_digest`, `display_text`, `payload_ref`, `payload_digest`, `operation_kind` (`start_run` or `submit_followup_queue`), `call_context_digest`
- `RUN_ACCEPTED`
  - scope: `session_id`, `run_id`
  - payload: `run_id`, `client_request_id`, `input_event_id`, `input_event_sequence`, `execution_target`, `queue_policy`, `source_run_id`, `source_run_relation`
- `RUN_QUEUED`
  - scope: `session_id`, `run_id`
  - payload: `run_id`, `accepted_event_id`, `accepted_event_sequence`, `queue_reason`, `active_run_id`
- `RUN_STARTED`
  - scope: `session_id`, `run_id`
  - payload: `run_id`, `start_reason`, `accepted_event_id`, `accepted_event_sequence`, `attempt_id`, `dispatch_record_id`
  - allowed Phase 3 `start_reason`: `initial`, `queue_promotion`
- `ATTEMPT_STARTED`
  - scope: `session_id`, `run_id`, `attempt_id`, `execution_id`
  - payload: `attempt_id`, `execution_id`, `dispatch_record_id`, `worker_kind`, `execution_target`, `owner_host_instance_id`
- `CANCEL_REQUESTED`
  - scope: `session_id`, `run_id`
  - payload: `run_id`, `client_request_id`, `reason`, `mode`, `target_status_at_accept`, `call_context_digest`
- `ATTEMPT_CANCELLED`
  - scope: `session_id`, `run_id`, `attempt_id`, `execution_id`
  - payload: `attempt_id`, `execution_id`, `reason`, `cancel_request_event_id`, `dispatch_record_id`
- `RUN_CANCELLED`
  - scope: `session_id`, `run_id`
  - payload: `run_id`, `reason`, `cancel_request_event_id`, `terminal_attempt_id`, `terminal_attempt_event_id`
- `ATTEMPT_SUCCEEDED` / `ATTEMPT_FAILED` / `ATTEMPT_LOST`
  - scope: `session_id`, `run_id`, `attempt_id`, `execution_id`
  - payload: `attempt_id`, `execution_id`, `reason`, `terminal_summary_ref`, `terminal_summary_digest`
  - Phase 3 internal helper may write synthetic test terminal facts with `reason='phase3_internal_closeout'`; production EngineEvent mapping remains future scope.
- `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_LOST`
  - scope: `session_id`, `run_id`
  - payload: `run_id`, `terminal_attempt_id`, `attempt_terminal_event_id`, `terminal_summary_ref`, `terminal_summary_digest`, `reason`

### Idempotency Contract

Use existing `idempotency_records` primitive. Each operation must bind `scope_kind`, `scope_id`, `idempotency_key`, `semantic_input_digest`, `result_kind`, `result_ref`, and first canonical event ref.

Digest rules:

- Digest is deterministic canonical JSON using existing durable codec helpers.
- Digest includes operation name and operation-owned fields.
- Digest includes actor/source/authorization claims/operation context digest because these affect audit and governance interpretation.
- Digest excludes `HostCallContext.request_id` because it is a tracing id and may legitimately differ across retries.
- Required request fields must be explicit digest fields; no explicit parameter may be hidden in metadata or extra payload.
- `submit_followup_queue` receives `resolved_execution_target` as an explicit Phase 3 internal admission input, but this value is treated as a Host policy resolution output rather than a caller-owned request field. It is therefore not part of the `submit_followup_queue` semantic digest; the first accepted call persists the resolved target, and same-key retries return that existing Run even if a later resolver/default would produce a different target.

Per-operation contract:

| operation | scope_kind | scope_id | idempotency_key | semantic digest fields | result_kind | result_ref | first event ref |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `ensure_session` | none | none | none | none | none | none | `SESSION_CREATED` only when slot absent |
| `create_session` | `create_session` | `host` | `client_request_id` | bind_slot, scope, slot_key, metadata_digest, caller_semantic_digest | `session` | `session_id` | `SESSION_CREATED` |
| `close_session` | `close_session` | `session_id` | `client_request_id` | reason, caller_semantic_digest | `session` | `session_id` | `SESSION_CLOSED` |
| `start_run` | `start_run` | `session_id` | `client_request_id` | input_digest, execution_target, queue_policy, caller_semantic_digest | `run` | `run_id` | `USER_INPUT_ACCEPTED` when a new Run is created; null event ref when `queue_policy=attach_active` returns an already active Run |
| `submit_followup_queue` | `submit_followup_queue` | `session_id` | `client_request_id` | input_digest, behavior=`queue`, caller_semantic_digest; excludes resolved_execution_target by policy-output rule above | `run` | `run_id` | `USER_INPUT_ACCEPTED` for both active and no-active creation paths |
| `cancel_run` | `cancel_run` | `run_id` | `client_request_id` | reason, mode, caller_semantic_digest | `run` | `run_id` | `CANCEL_REQUESTED` |
| `internal_terminal_closeout` | none by default | none | none | none | none | none | Attempt terminal event |

`ensure_session` is intentionally protected by `host_session_slots` primary key, not an idempotency record, because different delivery attempts for the same `(scope, slot_key)` must return the existing bound Session and must not conflict on metadata differences.

`submit_followup_queue` has two idempotent creation paths under the same operation contract:

- active Run exists: append `USER_INPUT_ACCEPTED` / `RUN_ACCEPTED` / `RUN_QUEUED`, create a `QUEUED` Run, store `resolved_execution_target` in `host_runs.execution_target`, and record the idempotency result as that Run id with first event ref `USER_INPUT_ACCEPTED`.
- no active Run exists: append `USER_INPUT_ACCEPTED` / `RUN_ACCEPTED` / `RUN_STARTED(start_reason=initial)` / `ATTEMPT_STARTED`, create a `RUNNING` Run plus `STARTING` Attempt and pending dispatch record, store `resolved_execution_target` in `host_runs.execution_target`, and record the idempotency result as that Run id with first event ref `USER_INPUT_ACCEPTED`.

For both paths, a same-key same-digest retry must check idempotency before reading active state, return the same Run result, and append no second event set. A same-key different-digest retry returns `idempotency_conflict` and appends no new EventLog rows.

`internal_terminal_closeout` is not a public command. Tests may call it without idempotency. If a later production owner needs idempotent terminal ingest, that owner must define its own operation idempotency contract.

### CAS Preconditions And `rowcount=0` Handling

All state transitions must use conditional update statements. A `rowcount=0` result is not ignored.

Rules:

- `close_session`: `UPDATE host_sessions SET status='closed' ... WHERE session_id=? AND status='open'`.
  - loser rereads Session.
  - missing -> `not_found`.
  - already closed with same idempotency record -> return existing snapshot.
  - already closed without same idempotency -> `invalid_state`.
- direct admission to active `RUNNING`: insert Run as `RUNNING`; partial unique index enforces active invariant.
  - unique active collision -> reread active Run, retry admission as queue or return conflict depending policy.
  - do not downgrade to memory conflict.
- queue promotion: select earliest queued run by accepted `event_sequence`; `UPDATE host_runs SET status='running' ... WHERE run_id=? AND status='queued' AND NOT EXISTS(active run for same session)`.
  - `rowcount=0` -> reread session active/queued state and return `PromotionResult(promoted_run=None, reason='cas_lost_or_no_longer_eligible')`; no error for loser.
- cancel queued: `UPDATE host_runs SET status='cancelled' ... WHERE run_id=? AND status='queued'`.
  - loser rereads Run.
  - terminal already -> return latest snapshot if same cancel idempotency, otherwise `invalid_state`.
  - now running -> route to pre-dispatch cancel if Attempt STARTING and dispatch pending; otherwise return `invalid_state` in Phase 3 because dispatching/active worker cancel is future scope.
- cancel pre-dispatch starting: require Run `RUNNING`, current Attempt `STARTING`, dispatch record `pending`.
  - update dispatch record pending -> cancelled with `WHERE status='pending'`.
  - update Attempt starting -> cancelled with `WHERE status='starting'`.
  - update Run running -> cancelled with `WHERE status='running' AND current_attempt_id=?`.
  - any loser -> rollback, reread latest durable state, return conflict/invalid_state or latest idempotent result.
- terminal closeout: require Run active, current Attempt matches, Attempt `STARTING` or `RUNNING` depending caller mode.
  - Phase 3 helper only needs `STARTING` for local tests; accepting `RUNNING` is allowed only as future EngineEvent reuse if explicitly tested and documented.
  - updates Attempt terminal and Run terminal in one transaction.
  - loser rereads; terminal already -> return latest if matching terminal event exists, otherwise `invalid_state` / `conflict`.
- after terminal/cancel release: promotion check is a new short transaction after the releasing transaction commits. It must re-evaluate active invariant; it must not assume the previous transaction's snapshot is still current.

### Public Interface

No new user-facing public API facade is required in Phase 3. Existing `dayu.host.api` request / snapshot / status / error types remain the public contract surface.

Internal service result dataclasses may be added in `dayu.host.admission` and durable modules. They must be typed, frozen, slots dataclasses and must not leak durable row types through `dayu.host.__all__` unless controller approves a public API boundary change.

## 5. Implementation Decisions

### Module Ownership

- `dayu.host.durable.schema`: DDL and table/index constants only.
- `dayu.host.durable.state`: row codecs and low-level state/index operations only.
- `dayu.host.durable.session_lifecycle`: Session command semantics.
- `dayu.host.durable.run_transition`: Run / Attempt transition semantics.
- `dayu.host.admission`: admission orchestration and after-commit promotion/wakeup coordination.
- `tests/host`: behavioral proof at module boundaries and multi-process proof.

### Target Types

Add internal enums or constants only where existing public enums do not apply:

- `DispatchRecordStatus`: `PENDING`, `CANCELLED`.
- `WorkerKind`: `LOCAL`, `REMOTE`.
- `RunStartReason`: `INITIAL`, `QUEUE_PROMOTION`.
- `AdmissionPolicy`: `QUEUE`, `REJECT`, `ATTACH_ACTIVE` for start_run; submit_followup(queue) only uses queue behavior.
- `PromotionSkipReason`: `NO_QUEUED_RUN`, `ACTIVE_RUN_EXISTS`, `CAS_LOST_OR_NO_LONGER_ELIGIBLE`.

Add explicit internal admission input for follow-up queue:

- `SubmitFollowupQueueAdmissionInput` internal frozen dataclass with fields `request: SubmitFollowupRequest` and `resolved_execution_target: str`.
- `submit_followup_queue` must receive `SubmitFollowupQueueAdmissionInput`; the service validates `resolved_execution_target` as a non-empty string before opening a transaction.
- Phase 3 must not read `execution_target` from `SubmitFollowupRequest` metadata, `HostInput` metadata, payload JSON, `caller_semantic_digest` or any untyped extra payload.
- Phase 3 must not introduce a full Phase 4 policy provider. Phase 4 public command path later owns real policy resolution and passes the already normalized value to this internal service.
- Phase 3 tests use fixed explicit values for `resolved_execution_target`.

Add row dataclasses:

- `SessionRow`
- `SessionSlotRow`
- `RunRow`
- `AttemptRow`
- `DispatchRecordRow`

Add service result dataclasses:

- `SessionLifecycleResult`
- `RunAdmissionResult`
- `PromotionResult`
- `CancelRunResult`
- `TerminalCloseoutResult`
- `PendingDispatchRecord`

All dataclasses must include Chinese docstrings with parameters, return values and exceptions for functions/methods.

### Data Flow

`ensure_session`:

```text
validate scope/slot_key
-> BEGIN IMMEDIATE
-> read slot by PK
-> if exists: read bound session and return
-> generate session_id and SESSION_CREATED event_id
-> append SESSION_CREATED
-> insert host_sessions OPEN
-> insert host_session_slots
-> commit
-> return SessionSnapshot
```

`create_session(bind_slot=false)`:

```text
validate request/context
-> BEGIN IMMEDIATE
-> check idempotency record create_session/host/client_request_id
-> if same digest exists: read result session and return
-> append SESSION_CREATED
-> insert host_sessions OPEN
-> if bind_slot: upsert slot to new session
-> record idempotency result with first event ref
-> commit
-> return SessionSnapshot
```

`start_run`:

```text
validate request/context and Session OPEN
-> BEGIN IMMEDIATE
-> check idempotency start_run/session_id/client_request_id
-> if same digest exists: return current RunSnapshot for result_ref
-> append USER_INPUT_ACCEPTED
-> append RUN_ACCEPTED
-> if no active Run:
     append RUN_STARTED(start_reason=initial)
     insert host_runs RUNNING
     append ATTEMPT_STARTED
     insert host_attempts STARTING
     insert dispatch record pending
     update run.current_attempt_id
   else if queue_policy == queue:
     append RUN_QUEUED
     insert host_runs QUEUED
   else if queue_policy == reject:
     rollback as conflict without recording idempotency
   else if queue_policy == attach_active:
     record idempotency result result_kind=run/result_ref=active_run_id with null event ref
     commit without appending new canonical facts
-> record idempotency result run_id with USER_INPUT_ACCEPTED event ref
-> commit
-> after commit: no-op dispatch wakeup, optional promotion wakeup only when needed
-> return RunAdmissionResult
```

For `queue_policy=attach_active`, the final `record idempotency result ... USER_INPUT_ACCEPTED event ref` step is skipped because no new Run or canonical fact is created. Repeated same-digest calls return the originally attached active Run by idempotency result ref.

`submit_followup(queue)`:

```text
validate request/context, behavior == QUEUE, resolved_execution_target non-empty
-> BEGIN IMMEDIATE
-> check idempotency submit_followup_queue/session_id/client_request_id
-> if same digest exists: return current RunSnapshot for result_ref without re-resolving or re-appending events
-> validate Session OPEN
-> read active Run for the Session
-> append USER_INPUT_ACCEPTED
-> append RUN_ACCEPTED with execution_target=resolved_execution_target
-> if active exists:
     append RUN_QUEUED
     insert host_runs QUEUED with execution_target=resolved_execution_target
   else:
     append RUN_STARTED(start_reason=initial)
     insert host_runs RUNNING with execution_target=resolved_execution_target
     append ATTEMPT_STARTED
     insert host_attempts STARTING
     insert dispatch record pending
     update run.current_attempt_id
-> record idempotency result run_id with USER_INPUT_ACCEPTED event ref
-> commit
-> after commit: no-op dispatch wakeup when a pending dispatch record was created
-> return RunAdmissionResult
```

`submit_followup(queue)` always stores the explicit `resolved_execution_target` on `host_runs.execution_target` for the new Run, whether the Run is queued or immediately running. Queue promotion later reads the already stored `host_runs.execution_target`; it must not rerun policy resolution or copy from whatever Run is active at promotion time.

`promote_next_queued_run(session_id)`:

```text
BEGIN IMMEDIATE
-> if active Run exists: return skipped
-> select earliest QUEUED by accepted_event_sequence
-> if none: return skipped
-> append RUN_STARTED(start_reason=queue_promotion)
-> CAS update selected Run QUEUED -> RUNNING
-> append ATTEMPT_STARTED
-> insert Attempt STARTING
-> insert dispatch record pending
-> update run.current_attempt_id
-> commit
-> return PromotionResult(promoted_run_id, dispatch_record)
```

`cancel_run`:

```text
BEGIN IMMEDIATE
-> check idempotency cancel_run/run_id/client_request_id
-> append CANCEL_REQUESTED
-> if Run QUEUED:
     append RUN_CANCELLED
     CAS QUEUED -> CANCELLED
   else if Run RUNNING with current Attempt STARTING and dispatch pending:
     append ATTEMPT_CANCELLED
     append RUN_CANCELLED
     CAS dispatch pending -> cancelled
     CAS attempt STARTING -> CANCELLED
     CAS run RUNNING -> CANCELLED
   else if terminal:
     invalid_state unless same idempotency result exists
   else:
     invalid_state for Phase 3 unsupported states
-> record idempotency result
-> commit
-> after commit: if active slot released, run promotion check in a new transaction
```

`internal_terminal_closeout`:

```text
BEGIN IMMEDIATE
-> validate Run active and current Attempt matches
-> append concrete Attempt terminal event
-> append concrete Run terminal event
-> CAS Attempt -> terminal
-> CAS Run -> terminal
-> commit
-> after commit: run promotion check in a new transaction
```

### Error Semantics

Internal services should map durable/domain failures to existing `HostApiErrorCode` semantics at the boundary:

- missing Session/Run/Attempt -> `not_found`.
- closed Session for new input -> `invalid_state`.
- active Run with reject policy -> `conflict`.
- same idempotency key different digest -> `idempotency_conflict`.
- CAS loser caused by concurrent valid transition -> reread and return structured conflict/skip/current snapshot, never overwrite.
- SQLite busy retry exhausted -> durable error, not API conflict.
- unique active partial index collision -> reread state and retry/queue/return conflict according to operation policy.

### After-commit Promotion / Wakeup Strategy

- No Engine or dispatcher side effect in transaction.
- Transaction body returns `PendingDispatchRecord` values for diagnostic/test assertions.
- `HostPhase3WakeupPort` may be defined as a small Protocol with:
  - `notify_pending_dispatch(dispatch_record_id: str) -> None`
  - `notify_queue_may_progress(session_id: str) -> None`
- Default implementation is no-op.
- For terminal/cancel release, service registers an after-commit callback that invokes no-op wakeup and then controller-facing method may synchronously call `promote_next_queued_run` in a new transaction. Tests should verify rollback does not invoke callbacks.
- `notify_pending_dispatch` must not dispatch; it only creates an explicit Phase 5 scheduler attachment point.

### Diagnostic Behavior

- Phase 3 does not create diagnostic table.
- Late or unsupported state situations return structured errors or skip reasons.
- Test-only terminal helper marks payload `reason='phase3_internal_closeout'` so artifacts cannot be mistaken for EngineEvent ingest.
- CAS loser results must include enough snapshot ids/statuses for tests and later diagnostics: `session_id`, `run_id`, latest run status, latest attempt status when available, and skip/conflict reason.

## 6. Implementation Slices

### P3-S1 Schema And Row Codecs

- **objective**: add Phase 3 durable tables, indexes, schema version and typed row codecs without implementing command behavior.
- **allowed files/modules**:
  - `dayu/host/durable/schema.py`
  - `dayu/host/durable/state.py`
  - `tests/host/test_state_schema.py`
  - `tests/host/test_durable_schema.py`
- **dependencies**: Phase 2 durable foundation.
- **exact allowed changes**:
  - bump `HOST_SCHEMA_VERSION` to `2`.
  - add table constants for sessions, slots, runs, attempts, dispatch records.
  - add DDL and index DDL for tables above.
  - update bootstrap to execute DDL in FK-safe order.
  - add row dataclasses and row conversion helpers in `state.py`.
  - add typed serializers/deserializers for existing public status enums and new dispatch/worker/start reason enums.
- **implementation instructions**:
  - keep `schema.py` as DDL truth only; no command logic.
  - `state.py` helpers may read rows and encode/decode statuses, but must not append EventLog.
  - use existing `_validation` helpers; do not introduce `Any`, `object`, untyped dicts or untyped returns.
  - express active invariant as SQLite partial unique index exactly as specified.
  - express queue FIFO with index on `(session_id, accepted_event_sequence, run_id)` for queued status.
- **non-goals**:
  - no Session lifecycle command.
  - no admission.
  - no promotion.
  - no cancel.
  - no public API export.
- **tests / expected assertions**:
  - fresh DB creates foundation + Phase 3 tables.
  - `PRAGMA user_version` is `2`.
  - `host_runs_one_active_per_session` exists and is partial unique on active statuses.
  - inserting two active runs for one session fails with structured unique constraint.
  - inserting active runs for different sessions succeeds.
  - multiple queued runs for one session succeed.
  - dispatch record status check only allows `pending` / `cancelled`.
  - schema mismatch still fails structurally.
- **completion signal**:
  - schema tests pass and no future phase tables beyond Phase 3 are created.
- **stop condition**:
  - if partial unique index cannot be represented or tested, stop and return to controller/design discussion.

### P3-S2 Session And Slot Lifecycle

- **objective**: implement Session row lifecycle and slot binding semantics with EventLog and idempotency.
- **allowed files/modules**:
  - `dayu/host/durable/state.py`
  - `dayu/host/durable/session_lifecycle.py`
  - `tests/host/test_session_lifecycle.py`
- **dependencies**: P3-S1.
- **exact allowed changes**:
  - add low-level insert/read/update helpers for sessions and slots.
  - implement `ensure_session`.
  - implement `create_session`.
  - implement `close_session`.
  - add internal result dataclasses and snapshot conversion helpers.
- **implementation instructions**:
  - `ensure_session` must not use idempotency_records; slot PK is the idempotency truth.
  - `create_session` and `close_session` must use `IdempotencyStore` with contracts from section 4.
  - append `SESSION_CREATED` / `SESSION_CLOSED` and update state rows in the same transaction.
  - `create_session(bind_slot=true)` must atomically rebind slot to the new Session; old Session remains unchanged.
  - `close_session` must not cancel, delete, purge or modify existing Run rows.
  - duplicate same digest returns existing snapshot; different digest returns idempotency conflict.
- **non-goals**:
  - no start_run or follow-up.
  - no Run / Attempt rows.
  - no purge.
  - no cancel_session_runs.
- **tests / expected assertions**:
  - `ensure_session` creates open Session and slot when absent.
  - repeated `ensure_session` returns same Session even with different metadata.
  - concurrent same-slot `ensure_session` returns same Session and leaves exactly one bound Session visible.
  - `create_session(bind_slot=false)` with same client_request_id returns same Session.
  - `create_session(bind_slot=true)` creates new Session and updates slot; old Session remains readable/open.
  - idempotency conflict on changed create/close semantic digest.
  - close makes Session `CLOSED`, appends `SESSION_CLOSED`, and new close retry returns existing closed snapshot.
- **completion signal**:
  - lifecycle tests pass and EventLog rows/state rows are atomically consistent.
- **stop condition**:
  - if existing `SessionSnapshot` cannot represent needed returned state without public API changes, stop for controller decision.

### P3-S3 Run / Attempt Transition Primitives

- **objective**: implement reusable transition helpers for creating accepted Run, starting Attempt with pending dispatch, terminal closeout and CAS updates.
- **allowed files/modules**:
  - `dayu/host/durable/state.py`
  - `dayu/host/durable/run_transition.py`
  - `tests/host/test_run_attempt_transitions.py`
- **dependencies**: P3-S1, P3-S2.
- **exact allowed changes**:
  - add low-level Run/Attempt/dispatch row insert/read/update helpers.
  - add `create_queued_run_in_transaction`.
  - add `create_running_run_with_starting_attempt_in_transaction`.
  - add `promote_queued_run_in_transaction`.
  - add `terminal_closeout_in_transaction`.
  - add `cancel_queued_in_transaction`.
  - add `cancel_predispatch_starting_in_transaction`.
- **implementation instructions**:
  - each helper receives a `HostTransaction`, already generated ids, event append dependencies and typed request dataclasses.
  - helpers must append required events and update state rows in the same transaction.
  - no helper may open its own transaction.
  - no helper may call after-commit callbacks.
  - CAS helpers must return explicit result objects that distinguish `updated`, `cas_lost`, `not_found`, `invalid_state`.
  - terminal closeout helper must append concrete terminal event types, not generic `RUN_TERMINAL`.
- **non-goals**:
  - no policy/admission decision.
  - no queue scanning orchestration.
  - no WorkerProxy or EngineEvent mapping.
- **tests / expected assertions**:
  - creating running Run creates `RUN_ACCEPTED`, `RUN_STARTED`, `ATTEMPT_STARTED`, Run `RUNNING`, Attempt `STARTING`, dispatch `pending`.
  - creating queued Run creates `RUN_ACCEPTED`, `RUN_QUEUED`, Run `QUEUED`, no Attempt, no dispatch record.
  - terminal helper atomically closes Attempt and Run and stores terminal event refs.
  - CAS loser leaves existing latest state unchanged and returns loser reason.
  - dispatch pending -> cancelled updates dispatch, Attempt and Run atomically.
- **completion signal**:
  - transition tests cover each Phase 3 transition primitive and failure path.
- **stop condition**:
  - if required event payload fields cannot be generated deterministically from current inputs, stop for plan/controller fix.

### P3-S4 Admission And Queue Promotion

- **objective**: implement internal start_run and submit_followup(queue) admission service plus FIFO promotion.
- **allowed files/modules**:
  - `dayu/host/admission.py`
  - `dayu/host/durable/session_lifecycle.py` only if snapshot helpers need reuse.
  - `dayu/host/durable/run_transition.py`
  - `tests/host/test_admission_queue.py`
- **dependencies**: P3-S2, P3-S3.
- **exact allowed changes**:
  - add `HostAdmissionService` or module-level functions:
    - `start_run(...) -> RunAdmissionResult`
    - `submit_followup_queue(input: SubmitFollowupQueueAdmissionInput) -> RunAdmissionResult`
    - `promote_next_queued_run(...) -> PromotionResult`
  - add no-op wakeup port Protocol and test spy.
  - implement idempotency for start and follow-up queue.
  - implement `queue_policy` values exactly as `queue`, `reject`, and `attach_active`; unknown values raise request validation `ValueError` before opening a transaction.
- **implementation instructions**:
  - admission service receives a transaction runner, EventLogStore, IdempotencyStore, clock/id generator dependencies and optional wakeup port.
  - no global singleton, no module-level mutable store.
  - start_run and follow-up must validate Session is OPEN in the admission transaction.
  - follow-up queue must receive a normalized `resolved_execution_target` from its caller; it must validate it as non-empty before admission and must not infer it from request metadata, HostInput metadata, payload JSON or active Run state.
  - follow-up queue must persist `resolved_execution_target` to `host_runs.execution_target` for both `QUEUED` and `RUNNING` Runs; later queue promotion reuses this stored value.
  - follow-up queue idempotency digest excludes `resolved_execution_target`; same-key same-digest retries return the first persisted Run without appending events, even if the caller now passes a different resolved target.
  - active Run detection must query `host_runs` active statuses and rely on partial unique index for race protection.
  - direct start path must create Attempt STARTING and dispatch record pending but not dispatch.
  - follow-up queue with no active Run must append `USER_INPUT_ACCEPTED`, `RUN_ACCEPTED`, `RUN_STARTED(start_reason=initial)` and `ATTEMPT_STARTED` in the admission transaction before returning a running Run.
  - `reject` with active Run must append no EventLog row and create no idempotency record.
  - `attach_active` with active Run must append no EventLog row, create an idempotency record with null event ref, and return the active Run.
  - promotion must select only one queued Run and must use accepted `event_sequence` FIFO.
  - promotion with active Run returns skipped, not error.
- **non-goals**:
  - no steer behavior.
  - no retry/replay.
  - no wait/resume.
  - no scheduler.
  - no lane.
  - no Engine.
- **tests / expected assertions**:
  - start on open Session with no active creates running Run and pending dispatch record.
  - follow-up queue with active Run creates queued Run with no Attempt.
  - follow-up queue with active Run stores the supplied `resolved_execution_target` on the queued Run and does not copy the active Run target.
  - follow-up queue without active creates running Run, starting Attempt and pending dispatch record.
  - follow-up queue without active has exactly the four canonical facts `USER_INPUT_ACCEPTED`, `RUN_ACCEPTED`, `RUN_STARTED(start_reason=initial)` and `ATTEMPT_STARTED` for that Run, in EventLog order.
  - follow-up queue without active stores the supplied `resolved_execution_target` on `host_runs.execution_target`.
  - closed Session rejects new start/follow-up with invalid_state and no EventLog side effects.
  - duplicate idempotency returns same Run and does not append extra events for both active-created queued Run and no-active directly running Run paths.
  - duplicate idempotency with a different later `resolved_execution_target` but unchanged semantic digest returns the first Run and does not mutate `host_runs.execution_target`.
  - same idempotency key with changed input digest returns idempotency conflict.
  - promotion chooses earliest accepted event_sequence, not insertion helper order.
  - concurrent promotion attempts promote at most one Run.
- **completion signal**:
  - admission tests prove direct start, queue, FIFO promotion and idempotency.
- **stop condition**:
  - if `queue_policy` values are not sufficiently constrained by existing public API, use an internal enum and stop only if public request shape must change.

### P3-S5 Cancel And Terminal Closeout Orchestration

- **objective**: wire cancel queued / pre-dispatch starting and terminal closeout to release active slot and trigger promotion.
- **allowed files/modules**:
  - `dayu/host/admission.py`
  - `dayu/host/durable/run_transition.py`
  - `tests/host/test_admission_queue.py`
  - `tests/host/test_run_attempt_transitions.py`
- **dependencies**: P3-S4.
- **exact allowed changes**:
  - add admission-level `cancel_run(...) -> CancelRunResult`.
  - add admission-level `closeout_attempt_terminal(...) -> TerminalCloseoutResult`.
  - after successful cancel/terminal release, trigger `promote_next_queued_run` in a new transaction.
  - ensure idempotency record for cancel binds `CANCEL_REQUESTED` as first event ref.
- **implementation instructions**:
  - cancel queued must append `CANCEL_REQUESTED` + `RUN_CANCELLED`, update Run to `CANCELLED`, create no Attempt.
  - cancel pre-dispatch starting must append `CANCEL_REQUESTED` + `ATTEMPT_CANCELLED` + `RUN_CANCELLED`, set dispatch record cancelled, and not notify WorkerProxy.
  - terminal closeout helper must support success/failure/lost terminal facts; cancellation terminal is handled by cancel path.
  - after-commit promotion must run in a new short transaction and be robust to another process winning first.
  - unsupported states such as `WAITING`, `RECOVERING`, `CANCELLING`, dispatching or Attempt RUNNING return `invalid_state` in Phase 3.
- **non-goals**:
  - no active worker cancel propagation.
  - no wait cancellation.
  - no recovery cancellation.
  - no session-scope `cancel_session_runs` facade.
- **tests / expected assertions**:
  - cancel queued writes no Attempt and can be retried idempotently.
  - cancel pre-dispatch starting marks dispatch `cancelled`, Attempt `CANCELLED`, Run `CANCELLED`.
  - cancel terminal Run cannot rewrite terminal.
  - terminal closeout of active Run promotes exactly one queued Run after commit.
  - cancel active pre-dispatch promotes exactly one queued Run after commit.
  - rollback before commit does not invoke wakeup/promotion.
- **completion signal**:
  - cancel/terminal tests pass, including promotion after release.
- **stop condition**:
  - if implementation needs to represent `waiting_for_lane` to cancel pre-dispatch, stop; Phase 3 only owns `pending`.

### P3-S6 Multiprocess Tests And Documentation Sync

- **objective**: prove multi-process correctness and update README facts.
- **allowed files/modules**:
  - `tests/host/test_admission_multiprocess.py`
  - `dayu/host/README.md`
  - `tests/README.md`
- **dependencies**: P3-S1 through P3-S5.
- **exact allowed changes**:
  - add multi-process tests for slot, active invariant, idempotency, queue promotion and cancel/promotion races.
  - update Host README to state current Session / Run / Attempt admission implementation and remaining non-goals.
  - update tests README to include Host state/admission tests and new commands if added.
- **implementation instructions**:
  - use `multiprocessing.Process` pattern already present in `tests/host/test_event_log_multiprocess.py`.
  - each process opens its own Host durable store connection.
  - keep process counts modest to avoid flaky load tests; correctness over performance.
  - assertions must inspect durable rows and EventLog sequences after processes join.
- **non-goals**:
  - no performance benchmark.
  - no stress test requiring external services.
  - no PR/commit.
- **tests / expected assertions**:
  - same slot concurrent ensure returns one Session binding.
  - same Session concurrent start/follow-up creates at most one active Run.
  - duplicate `(session_id, client_request_id)` across processes returns one result; changed digest conflicts.
  - queued follow-ups are promoted FIFO by accepted event_sequence.
  - cancel queued vs promotion follows first-committer-wins.
  - EventLog `event_sequence` remains globally unique and increasing.
- **completion signal**:
  - all affected tests and pyright pass, README sync completed.
- **stop condition**:
  - if tests are flaky due to SQLite busy policy rather than state bug, tune test storage policy within existing options; if correctness remains ambiguous, stop for controller.

## 7. Tests And Validation Commands

Run in an activated Python 3.11 virtual environment:

```bash
source .venv/bin/activate
```

### Slice-scoped Commands

P3-S1:

```bash
pytest tests/host/test_state_schema.py tests/host/test_durable_schema.py -q
python -m pyright dayu/host tests/host
```

P3-S2:

```bash
pytest tests/host/test_session_lifecycle.py tests/host/test_state_schema.py -q
python -m pyright dayu/host tests/host
```

P3-S3:

```bash
pytest tests/host/test_run_attempt_transitions.py tests/host/test_session_lifecycle.py -q
python -m pyright dayu/host tests/host
```

P3-S4:

```bash
pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q
python -m pyright dayu/host tests/host
```

P3-S5:

```bash
pytest tests/host/test_admission_queue.py tests/host/test_run_attempt_transitions.py -q
python -m pyright dayu/host tests/host
```

P3-S6:

```bash
pytest tests/host/test_admission_multiprocess.py tests/host -q
python -m pyright dayu/host tests/host
```

### Full Phase Validation

```bash
pytest tests/host -q
python -m pyright dayu/host tests/host
python -m pyright dayu/ tests/ utils/
```

### Required Failure Paths

Tests must include negative assertions for:

- schema version mismatch.
- partial unique active Run violation.
- closed Session new input.
- idempotency same key different digest.
- CAS loser on promotion.
- cancel terminal cannot rewrite terminal.
- cancel unsupported state returns invalid_state.
- rollback prevents EventLog/state/index partial persistence.
- after-commit callback not called on rollback.

## 8. Documentation Update Decision

README trigger rules apply.

- `dayu/host/` production modules will change, so `dayu/host/README.md` must be updated after implementation.
  - Add current Session / slot / Run / Attempt / dispatch record / admission facts.
  - Keep it as Host development manual, not user guide.
  - Explicitly state remaining non-goals: Engine dispatch, scheduler, lane, WorkerProxy, EngineEvent ingest, ToolRuntime, wait/resolve, steer, retry/replay, recovery.
- `tests/` will gain new Host state/admission/multiprocess tests, so `tests/README.md` must be updated.
  - Add test category and commands.
  - Do not write future testing plans as completed facts.
- Root `README.md` is not triggered unless implementation changes CLI, render, project-level usage or config entry points. Current plan does not.
- `dayu/README.md` is not triggered unless implementation changes overall layering, composition or Host boundary. Current plan should not.
- `dayu/engine/README.md` / `dayu/fins/README.md` / `dayu/config/README.md` are not triggered.

## 9. Review Gates / Stop Conditions / Risks / Open Questions

### Review Gates

Plan review must verify:

- partial unique active Run invariant is explicit and not replaceable by implementation choice.
- schema tables have clear semantic owners and no future empty tables.
- event types and payloads are concrete enough to implement.
- idempotency scope/digest/result refs are fixed per operation.
- CAS `rowcount=0` handling is fixed per transition.
- slices are small, ordered and file-bounded.
- tests include unit, integration and multi-process correctness.
- non-goals prevent Engine/scheduler/lane/WorkerProxy leakage.

Each implementation slice must go through code review and re-review before the next slice begins.

### Stop Conditions

Implementation agent must stop and return to controller if:

- SQLite partial unique index does not satisfy implementation/test constraints.
- Existing public API types are insufficient and would require changing `dayu.host.api`.
- Event payload contract appears inconsistent with design truth and cannot be implemented without choosing a new event set.
- A transition needs Engine dispatch, scheduler, lane, WorkerProxy, LocalProxy, RemoteProxy or `ATTEMPT_RUNNING`.
- A transition needs wait record, resolve_wait, steer, retry/replay, context compaction or recovery.
- CAS loser semantics are ambiguous for a transition not covered by this plan.
- Multiprocess tests require broad timing assumptions instead of durable truth assertions.
- Any production change would touch Engine/Fins/Service/UI/runtime.

### Risks

- **R1 partial unique index portability**: accepted design requires SQLite partial unique index. If tests or SQLite behavior conflict, fallback must go back to design discussion.
- **R2 event set tension**: broader canonical event collection includes `FOLLOWUP_QUEUED`, while Phase 3 transition table does not require it. This plan follows §9.1 and forbids implementation-agent invention. Plan review should explicitly confirm.
- **R3 no public facade yet**: Phase 3 internal services may not be directly used by UI/Service until Phase 4 wires public command path. This is intentional and non-blocking.
- **R4 synthetic terminal helper**: test helper terminal facts must be clearly marked so they are not mistaken for EngineEvent ingest.
- **R5 multiprocess flakiness**: tests must assert durable invariants, not strict timing or fairness.

### Open Questions

Blocking open questions: none.

Non-blocking tracked assumptions:

- `FOLLOWUP_QUEUED` is not emitted by Phase 3 unless plan review/controller changes the decision; §9.1 is treated as the more specific transition truth.
- `cancel_session_runs` public facade is not implemented in Phase 3; later Phase 4 or a dedicated work unit may compose over single-run cancel after controller confirmation.
- `owner_host_instance_id` in dispatch record may be nullable in Phase 3 because no scheduler/worker ownership is established yet. Phase 5/11 may populate and interpret it; Phase 3 must not treat it as lease/fencing/takeover proof.

## 10. Implementation Completion Report Format

Each slice implementation artifact must use this format:

```markdown
# Host Phase 3 Implementation Report - <slice id>

- **work gate name**: implementation
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: <P3-Sn name>
- **approved plan path**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **changed files**:
  - ...
- **implemented plan items**:
  - ...
- **not implemented items and reason**:
  - ...
- **explicit non-goals respected**:
  - Engine dispatch: not touched
  - scheduler/lane/WorkerProxy/LocalProxy/RemoteProxy: not touched
  - EngineEvent ingest/ToolRuntime/wait/resolve_wait/steer/retry/replay/context compaction/recovery: not touched
- **validation commands and results**:
  - `...`: passed/failed with summary
- **documentation update decision and result**:
  - Host README: updated/not triggered with reason
  - tests README: updated/not triggered with reason
- **plan gaps or controller questions**:
  - none / list
- **residual risks and uncovered areas**:
  - risk: classification destination
- **completion signal**:
  - ...
- **stop condition status**:
  - no stop condition hit / stop condition hit with reason
- **artifact path**: `docs/reviews/...`
```

Final Phase 3 closeout must report:

- what changed.
- what was verified.
- documentation updated or explicitly not updated.
- accepted/deferred/rejected finding status.
- remaining risks and destination.
- next entry point, expected to be Phase 4 Host Public API Command Path or Phase 5 dispatch depending controller sequencing.
