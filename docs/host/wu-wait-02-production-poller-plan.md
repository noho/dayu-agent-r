# WU-WAIT-02 Production Poller Loop / Backoff / Fencing / Retry Plan

## Gate / Work Unit

- Gate: `plan`
- Work unit: `WU-WAIT-02`
- GitHub issue: `#90`
- Type: issue-backed Host production hardening / bug-fix-feature
- Expected artifact: `docs/host/wu-wait-02-production-poller-plan.md`
- Scope owner: Host Tool Awaiting / wait poller runtime

## Goal / Motivation / Success Signal

### Goal

Implement a production Host wait poller runtime around the existing single-round `WaitPoller.poll_once()` semantics:

- background loop with explicit start / stop / close lifecycle;
- durable in-flight claim / fencing so multiple pollers do not concurrently observe or resolve the same wait record;
- bounded per-wait backoff for not-ready, adapter errors, missing adapters, resolve failures, and cancelled-wait abandon failures;
- clean shutdown behavior that stops new polling, cancels sleep promptly, and drains already-entered work without writing user-cancel facts;
- diagnostics that explain poller status and retry decisions without turning runtime internals into business facts.

### Motivation

The current code already has the correctness core for a single synchronous poll round, but it is not production-ready:

- it has no background loop, so production `open_host(...)` cannot recover `WAITING` runs by polling after startup;
- it has no durable claim, so multiple pollers or multiple Host processes can call the same external adapter concurrently;
- it has no shared backoff state, so repeated not-ready or transient failures can tight-loop, especially with multiple pollers;
- it has no close integration, so shutdown cannot reason about sleep cancellation or in-flight adapter calls;
- cancelled wait abandon is remembered only in one poller instance memory, so another process or restart can repeat it immediately.

### Success Signal

- `open_host(...)` can optionally start a wait poller background runtime when construction-time poll adapters and poller policy are configured.
- A `WAITING` run with `resume_policy=poll` is resolved only through `resolve_wait`; ready / lost outcomes create the same durable resume / terminal facts as manual or callback resolution.
- Two pollers cannot concurrently hold an active poll claim for the same eligible wait record.
- If a claim holder crashes or closes mid-poll, another poller can retry after bounded claim expiry without treating expiry as proof that the old adapter stopped.
- Repeated not-ready, missing adapter, adapter exception, resolve exception, and abandon exception are throttled by a Host-owned backoff policy with finite maximum delay.
- Host close stops poller sleep immediately and prevents new adapter calls. Results observed after close has started are not submitted to `resolve_wait`; the wait remains retryable by a later opener.
- Existing focused Host wait tests, new durable claim/backoff tests, new loop lifecycle tests, affected public `open_host` tests, and pyright pass.

## Non-Goals / Scope Boundary

- Do not implement HTTP callback auth / replay; that belongs to WU-WAIT-01.
- Do not implement external job physical cancel / revoke / abandon as a full provider lifecycle; that belongs to WU-WAIT-03.
- Do not implement UI / Service production-grade awaiting E2E smoke; that belongs to WU-WAIT-04.
- Do not turn the poller into a generic scheduler, watcher, UI event iterator, lifecycle supervisor, distributed lease, or Attempt takeover system.
- Do not change the Engine awaiting public model. Engine still does not poll, store wait records, or resume old Agent / Runner instances.
- Do not let poller diagnostics become financial facts, user-visible conclusions, or Run / Attempt ownership truth.
- Do not add EventLog diagnostic events for ordinary poll loop health, claim conflicts, or backoff decisions. Existing late-result EventLog diagnostics from `resolve_wait` remain unchanged.

## Design Document Alignment

Direct alignment points:

- `docs/host/design.md` says `resolve_wait` is idempotent by `(wait_id, idempotency_key)`, and wait resolution must go through the common Host command path.
- `docs/host/design.md` says `poll`, `callback`, and `manual` are only result-discovery adapters. They must not directly append canonical EventLog facts or update Run / Attempt terminal state.
- `docs/host/design.md` says wait record is Host durable state for active wait query, adapter observation recovery, cancellation CAS, resolution CAS, and late result rejection.
- `docs/host/design.md` says `cancel_run` and `resolve_wait` race by first committed transaction, and late results for cancelled / lost waits must not become canonical tool facts.
- `docs/host/design.md` says `WAITING` runs stay `WAITING` during startup recovery; recovery only restores adapter observation and must not create an Attempt until `resolve_wait`.
- `docs/host/design.md` explicitly rejects heavy lease / fencing systems and old Attempt takeover.
- `docs/engine/design.md` says Engine does not wait for external long transactions, does not poll jobs, does not persist wait records, and does not keep recoverable in-memory Agent / Runner state.

This plan keeps those boundaries: the poller only observes wait records and external jobs, then calls `resolve_wait`; durable claim/backoff fields only govern poll observation eligibility and do not authorize Run / Attempt ownership.

## First-Principles Judgment And Direct Code Evidence

### Judgment

The work unit is valid and not overestimated. The correctness core already exists for a single poll round, but production operation needs loop lifecycle, shared throttling, and cross-process duplicate suppression. These are not cosmetic concerns: without durable claim/backoff, multi-process pollers can concurrently call the same external job and can retry immediately after not-ready or transient failures.

The minimal correct primitive is to extend the wait record durable row with poll observation state. A separate poll claim table is unnecessary because the claim has one owner at a time and is semantically subordinate to one wait record. Runtime-only memory is insufficient because it does not coordinate multiple Host processes.

### Direct Evidence

- `dayu/host/wait_adapter.py` defines `WaitPoller.poll_once()` as a synchronous single-round primitive. It reads all active poll/cancelled wait records, calls adapters outside Host transactions, submits ready/lost via `resolve_wait`, does nothing for not-ready, and isolates adapter / resolve exceptions per wait.
- `WaitPollOnceResult` currently reports only `observed`, `not_ready`, `resolved`, `lost`, `abandoned`, and `adapter_errors`; it has no claimed / skipped / backoff / lifecycle diagnostics.
- `WaitPoller` stores `_abandoned_cancelled_wait_ids` in memory, so abandon-once behavior is not durable across process restart or multiple poller instances.
- `dayu/host/durable/state.py` has `read_wait_records_for_poll_observation(...)`, but it selects every `resume_policy=poll` row in `waiting` or `cancelled` status without claim, expiry, or next-observe gating.
- `host_wait_records` in `dayu/host/durable/schema.py` has wait identity, external job ref, resolve idempotency, deadline / expiry, and terminal fields, but no poll claim or poll backoff fields.
- `DefaultHostResolveWaitService.resolve_wait(...)` in `dayu/host/waiting.py` already handles committed-state idempotency, same-key replay, different-outcome conflict, terminal wait replay, cancelled / lost late-result rejection, and durable diagnostic for late results.
- `dayu/host/open_host.py` has an async public Host handle and closes scheduler / projection / durable store, but it does not construct or close a wait poller runtime.
- `HostToolingOptions` already carries `wait_adapter_registry` and `wait_activation_registry` for ToolRuntime awaiting accept / activation, but it does not carry a poll adapter registry for background polling.
- `tests/host/test_wait_adapter_polling.py` covers ready, not-ready, lost, cancelled abandon once, missing adapter, adapter exception isolation, resolve exception isolation, and abandon retry. It does not cover durable claim conflicts, claim expiry, cross-poller backoff, supervisor lifecycle, open_host integration, or shutdown.
- `tests/host/test_resolve_wait_command.py` covers resume state transitions and idempotency semantics, including same key replay and different outcome conflict.

## Affected Files / Modules

Implementation is expected to touch only Host-owned modules and focused tests:

- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/wait_adapter.py`
- `dayu/host/tooling.py`
- `dayu/host/api.py`
- `dayu/host/open_host.py`
- `dayu/host/command.py` only if a small internal resolver or command-handle helper is needed; prefer avoiding changes here.
- `tests/host/test_wait_record_state.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_wait_adapter_polling.py`
- new focused test file `tests/host/test_wait_poller_runtime.py` if lifecycle tests are clearer outside the single-round polling tests.
- `tests/host/test_open_host_runtime.py` or another existing open-host integration test file for construction / close behavior.

Docs to check or update after implementation:

- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`

Do not touch Engine code for this work unit.

## Contract / Schema / State-Machine / Public Interface Changes

### Durable Schema

Extend `host_wait_records` with poller-owned observation fields:

- `poll_claim_id TEXT NULL`
- `poll_claim_owner_id TEXT NULL`
- `poll_claimed_at TEXT NULL`
- `poll_claim_expires_at TEXT NULL`
- `poll_next_observe_at TEXT NULL`
- `poll_backoff_attempts INTEGER NOT NULL DEFAULT 0`
- `poll_last_observed_at TEXT NULL`
- `poll_last_outcome TEXT NULL`
- `poll_last_error_code TEXT NULL`
- `poll_abandoned_at TEXT NULL`

Schema checks:

- claim fields must be all-null or all-present for `poll_claim_id`, `poll_claim_owner_id`, `poll_claimed_at`, and `poll_claim_expires_at`.
- `poll_backoff_attempts >= 0`.
- timestamp fields use existing UTC ISO-8601 `Z` convention.
- `poll_last_outcome` allowed values are a small Host-owned enum such as `not_ready`, `adapter_error`, `missing_adapter`, `resolve_error`, `abandon_error`, `abandoned`, `resolved`, `lost`, `shutdown_skipped`.
- `poll_abandoned_at` is only allowed for `status='cancelled'`.

Indexes:

- Replace or adjust `INDEX_HOST_WAIT_RECORDS_ACTIVE_POLL` so eligible lookup can filter by `resume_policy`, `status`, `poll_abandoned_at`, `poll_next_observe_at`, and claim expiry.
- Do not add a separate poll claim table unless implementation proves SQLite partial-index or update-CAS constraints cannot express the single active claim invariant. Current evidence does not support a separate table.

Schema version:

- Increment `HOST_SCHEMA_VERSION`.
- Treat this as fresh-schema only per project rules; do not add old DB compatibility reads or migration tests.

### Durable State Helpers

Add typed helpers in `dayu/host/durable/state.py`:

- `claim_wait_records_for_poll_observation(transaction, *, owner_id, claim_id_factory, now, claim_ttl_seconds, limit) -> tuple[WaitPollClaimedRecord, ...]`
- `release_wait_poll_claim_with_backoff(transaction, *, wait_id, claim_id, next_observe_at, backoff_attempts, last_observed_at, last_outcome, last_error_code) -> WaitRecordMutationResult`
- `release_wait_poll_claim_after_shutdown(transaction, *, wait_id, claim_id, observed_at) -> WaitRecordMutationResult`
- `mark_cancelled_wait_poll_abandoned(transaction, *, wait_id, claim_id, abandoned_at) -> WaitRecordMutationResult`

If a dedicated `WaitPollClaimedRecord` is unnecessary, `WaitRecordRow` may include the new fields directly. Prefer direct row extension unless tests show a narrower type reduces confusion.

Required CAS invariants:

- A claim can be acquired only when the wait is poll-eligible and either unclaimed or the existing claim is expired at `now`.
- Claim release / backoff / abandoned marking must match `(wait_id, poll_claim_id)`.
- A stale owner must not clear a newer claim.
- Terminal wait record transitions in `resolve_wait` must clear poll claim fields so terminal rows are not left with active in-flight diagnostics.
- Cancelled wait rows with `poll_abandoned_at IS NOT NULL` must not be returned for further abandon.
- Claim acquisition must be a single atomic write operation, or an equivalent single-row write primitive, where eligibility checks and claim-field updates happen in the same statement. A separate read result must never authorize an adapter call.

### Public / Construction Interface

Add Host construction-time options, not per-run knobs:

- Add `WaitPollerRuntimePolicy` as a typed dataclass in Host API or wait adapter module, then expose it through `OpenHostOptions`.
- Fields:
  - `enabled: bool`
  - `poll_interval_seconds: float`
  - `claim_ttl_seconds: float`
  - `claim_batch_size: int`
  - `backoff_initial_delay_seconds: float`
  - `backoff_multiplier: float`
  - `backoff_max_delay_seconds: float`
  - `close_drain_timeout_seconds: float | None`
- Add `wait_poller_policy: WaitPollerRuntimePolicy | None = None` to `OpenHostOptions`.
- Add `wait_poll_adapter_registry: WaitPollAdapterRegistry | None = None` to `HostToolingOptions`.

Policy rules:

- `None` disables the production poller and preserves current no-poller behavior.
- `enabled=False` is valid and disables the poller while still validating the policy object.
- Enabling the poller without a `wait_poll_adapter_registry` is a construction error, because production polling would otherwise spin on missing adapters.
- All numeric policy values must be positive except `close_drain_timeout_seconds`, which may be `None` for no timeout or positive when set.
- `claim_ttl_seconds` must be greater than the maximum expected single adapter observation budget if the deployment wants strict duplicate suppression. It is still not a lease.

Do not add a new public Host method for diagnostics in this work unit. Supervisor diagnostics are runtime read view / logs and test-visible internal state.

### State Machine

No new Run / Attempt state is introduced.

Existing state transitions remain:

- `WAITING + resolve_wait -> RUNNING + new resume Attempt`
- `WAITING + cancel_run -> CANCELLED`
- `WAITING + poll not-ready -> WAITING`
- `WAITING + poll adapter error -> WAITING`
- `WAITING + poll resolve transient failure -> WAITING`
- `CANCELLED + poll abandon success -> CANCELLED` with `poll_abandoned_at` set

The poll claim is not a Run state, Attempt state, dispatch state, lease, or takeover grant. It is a durable observation guard scoped to one wait record.

### Resolve Retry / Idempotency

Keep `_poll_idempotency_key(wait_record)` stable and based only on `source=poll` and `wait_id`.

Reasoning:

- If `resolve_wait` commits but the poller crashes before observing success, a later poll with the same key and same outcome replays the committed result.
- If two pollers race after claim expiry and produce different outcomes, `resolve_wait` rejects the second outcome through existing idempotency / terminal-state rules.
- If a transient exception happens before commit, retrying with the same key re-executes the resolution chain.
- The poller must not generate a new key per attempt; doing so would allow double-resolution attempts and would weaken the existing command contract.

## Implementation Decisions

### Claim / Fencing Placement

Decision: extend the `host_wait_records` durable row with minimal poll claim and backoff fields.

Why:

- The claim belongs to wait observation, and wait record already owns adapter observation recovery.
- There is exactly one active poll claim per wait, so a separate claim table adds lifecycle surface without a separate semantic owner.
- SQLite CAS on the wait row can express acquire, release, expiry takeover, and stale release prevention.
- The implementation avoids a generic lease subsystem and avoids cross-cutting scheduler ownership.

Why this is not lease / Attempt takeover:

- Claim expiry only makes the wait eligible for another observation. It does not prove the old adapter call stopped.
- A claim holder cannot mutate Run / Attempt directly; ready / lost still goes through `resolve_wait`.
- The claim does not carry worker ownership, execution ownership, or recovery authority.
- It does not change dispatch records, host instance liveness, positive orphan proof, or `ATTEMPT_LOST` semantics.

### Poll Loop Lifecycle

Add a Host-owned `WaitPollerSupervisor` in `dayu/host/wait_adapter.py` unless the file becomes too large; if so, create `dayu/host/wait_poller.py` and keep adapter contracts in `wait_adapter.py`.

Required API:

- `@classmethod async open(...) -> WaitPollerSupervisor`
- `async close() -> None`
- `async drain_once_for_test() -> WaitPollOnceResult`
- `diagnostics_snapshot() -> WaitPollerDiagnosticsSnapshot`

Lifecycle:

- `open_host.__aenter__` constructs the supervisor after durable store, scheduler, recovery scan, and command handle are available.
- Startup recovery keeps `WAITING` runs in place; poller startup is the mechanism that resumes adapter observation.
- `open_host` close order becomes:
  1. close public gate;
  2. close wait poller supervisor so it cannot create new resume Attempts during shutdown;
  3. close scheduler / active workers;
  4. projection catch-up;
  5. close durable store.
- If `open_host` construction fails after supervisor creation, cleanup must close supervisor before durable store close.

Sleep cancellation:

- The loop must wait on an `asyncio.Event` or cancellable sleep, not only `asyncio.sleep(...)`.
- `close()` sets the closed flag and wakes sleep immediately.
- No new claim or adapter call may start after close begins.

In-flight adapter boundary:

- Adapter calls are synchronous today. Keep the adapter protocol synchronous for this WU to avoid changing existing tool/adapter contracts.
- The supervisor may run a poll round in the event-loop task only if the claim batch is small and adapter calls are expected short; otherwise it may use `asyncio.to_thread` internally.
- Regardless of execution strategy, after close begins the poller must recheck a lifecycle gate before calling `resolve_wait` or `abandon_wait` side effects. If the gate is closed after an adapter returns, release the claim with `shutdown_skipped` and leave the wait eligible for a later opener.
- If close begins while `resolve_wait` has already entered the command path, let that command finish under normal transaction semantics.

Close drain:

- `close()` waits for the current poll round to finish.
- If `close_drain_timeout_seconds` is set and the current poll round does not finish in time, treat the timeout as an operator-visibility threshold, not as permission to detach the poller from the Host close sequence.
- After the timeout fires, `close()` logs a structured error with the current diagnostics snapshot, keeps the close gate closed, continues waiting for the in-flight poll task or worker thread to finish, and does not return while that task/thread can still touch the durable store.
- Because `open_host` closes the durable store only after `poller.close()` returns, this rule prevents durable store close while a background poll path can still run SQL. If a synchronous adapter never returns, Host close may remain blocked; this is the explicit safety tradeoff for keeping the existing synchronous adapter contract.
- Tests must cover normal drain and sleep cancellation. A hard-kill of arbitrary synchronous adapter code is out of scope because Python cannot safely kill a running sync function.

Exception reporting:

- Poll loop unexpected exceptions are logged with `host_handle_id`, `owner_id`, `error_type`, and current diagnostics counters.
- Adapter and resolve exceptions remain per-wait isolated.
- A fatal loop exception exits the supervisor loop and is visible through `diagnostics_snapshot().status`.

### Backoff Policy

Owner: Host wait poller runtime.

Storage:

- Per-wait durable fields on `host_wait_records` store `poll_next_observe_at`, `poll_backoff_attempts`, `poll_last_observed_at`, `poll_last_outcome`, and `poll_last_error_code`.
- Supervisor-level aggregate counters live only in memory diagnostics.

Retry rhythm:

- On first retryable not-ready or failure, delay is `backoff_initial_delay_seconds`.
- On repeated retryable outcomes, delay is `min(initial * multiplier ** attempts, max_delay)`.
- `poll_backoff_attempts` is shared per wait record across poller instances. Repeated process crash / claim-expiry / takeover cycles can make a wait reach `backoff_max_delay_seconds` faster than a per-process counter would, but the delay is bounded by `backoff_max_delay_seconds` and the shared state intentionally prevents process restarts from resetting a failing wait into a tight loop.
- On success terminal resolve, no further polling occurs.
- On cancelled abandon success, set `poll_abandoned_at` and no further polling occurs.
- On shutdown skipped, clear claim and set `poll_next_observe_at` to `now` or a minimal policy delay; prefer `now` so a later opener can resume promptly.
- Missing adapter remains a retryable poller configuration/runtime error in this WU. It uses capped-delay indefinite retry rather than terminalizing the wait, because this work unit cannot prove whether the adapter is permanently invalid or temporarily absent during deployment. The poller must record `missing_adapter` in wait-row last outcome/error fields and increment runtime diagnostics so operators can repair registration or handle the wait through a later owner.

No magic numbers:

- Defaults live in one policy constructor / default function.
- Tests inject small policy values.
- Loop idle interval uses `poll_interval_seconds`; backoff delay is per wait.

### Diagnostics Decision

Use runtime read view / logs / result summaries, not new EventLog diagnostics.

Diagnostic surfaces:

- Extend `WaitPollOnceResult` or add `WaitPollBatchResult` fields: `claimed`, `claim_conflicts`, `backoff_skipped`, `shutdown_skipped`, `resolve_errors`, `abandon_errors`, `missing_adapters`.
- Add `WaitPollerDiagnosticsSnapshot` with `status`, `last_started_at`, `last_stopped_at`, `last_poll_at`, `last_error_type`, `total_rounds`, `total_claimed`, `total_resolved`, `total_lost`, `total_adapter_errors`, `total_resolve_errors`, `total_claim_conflicts`, `total_shutdown_skipped`.
- Log structured messages at debug/info/warning levels. Do not log tool result payload values.

Why not EventLog:

- Claim conflicts and backoff decisions are runtime operation diagnostics, not business facts or canonical Run / Attempt transitions.
- Adding EventLog diagnostic events for ordinary poll health would require a design-source change and projection decisions that are not necessary for issue #90.
- Existing `WAIT_LATE_RESULT_REJECTED` EventLog diagnostic remains the durable trace for rejected late results because that is already part of wait resolution correctness.

## Implementation Slices

The plan uses 3 slices. This follows the control document default for medium Host durable/runtime work and keeps each slice independently reviewable:

- Slice 1 closes the durable correctness primitive.
- Slice 2 closes the single-process poller behavior and lifecycle primitive.
- Slice 3 closes production composition with `open_host` and docs.

Fewer than 3 slices would mix schema/CAS correctness, async runtime lifecycle, and public opener integration in one review loop. More than 3 slices would create gate cost without a separate semantic boundary.

### Slice 1: Durable Poll Claim And Backoff Primitive

Objective:

- Add wait-record-owned durable poll claim, backoff, and abandoned markers.
- Make single-round polling claim-aware and safe under multiple poller instances.

Allowed files/modules:

- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/wait_adapter.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_wait_record_state.py`
- `tests/host/test_wait_adapter_polling.py`

Prerequisites:

- Existing `WaitPoller.poll_once()` tests pass before the slice.
- Existing resolve_wait idempotency behavior remains unchanged.

Exact changes:

- Increment `HOST_SCHEMA_VERSION`.
- Add poll claim/backoff columns and checks to `host_wait_records`.
- Extend `WaitRecordRow` decoding, validation, insert, and schema tests for new fields.
- Replace `read_wait_records_for_poll_observation(...)` call path with claim acquisition:
  - claim only eligible `waiting` poll rows and cancelled poll rows without `poll_abandoned_at`;
  - skip rows whose `poll_next_observe_at` is in the future;
  - allow takeover only when `poll_claim_expires_at <= now`;
  - set claim fields by an atomic `UPDATE ... WHERE` / equivalent write statement where poll eligibility and claim-field assignment happen in the same statement;
  - treat `rowcount == 0` or no returned row as a claim conflict, skip the adapter call, increment claim-conflict diagnostics, continue to another wait, and do not run release logic for a claim that was never acquired.
- Implement `claim_batch_size` as repeated single-row claim attempts up to `limit`, or as per-row isolated CAS attempts inside one write transaction. Successful row claims are returned independently; the batch is not all-or-nothing.
- Add release helpers that require matching `poll_claim_id`.
- Update `_mark_wait_record_terminal_row` or the equivalent terminal wait mutation to set `poll_claim_id=NULL`, `poll_claim_owner_id=NULL`, `poll_claimed_at=NULL`, and `poll_claim_expires_at=NULL` on resolved / failed / lost terminal transitions.
- Update `WaitPoller.poll_once()` to:
  - claim before adapter calls;
  - release with backoff after not-ready / adapter error / missing adapter / resolve error / abandon failure;
  - mark cancelled abandon success durably;
  - keep adapter calls outside Host transaction;
  - keep ready/lost on `resolve_wait`.
- Keep `_poll_idempotency_key(...)` unchanged.

Data flow / state transitions:

```text
atomic claim write:
     UPDATE host_wait_records
     SET poll_claim_id / owner / claimed_at / expires_at
     WHERE wait is poll-eligible and unclaimed-or-expired
  -> claimed row returned
  -> adapter call outside Host transaction
  -> not-ready or retryable error:
       CAS release same claim and set next_observe/backoff diagnostic
  -> ready or lost:
       call resolve_wait(wait_id, poll-idempotency-key)
       resolve_wait terminal mutation clears poll claim fields
  -> cancelled:
       adapter.abandon_wait(...)
       CAS set poll_abandoned_at and clear claim
  -> claim CAS rowcount 0:
       skip adapter call and do not release
```

Error handling:

- Missing adapter is a retryable poller error with capped-delay indefinite backoff; it must not call `resolve_wait`, must update wait-row last outcome/error metadata, and must increment runtime diagnostics for operator visibility.
- Adapter exception is isolated to that wait and releases the claim with backoff.
- Resolve exception is isolated to that wait and releases the claim with backoff unless durable re-read proves the wait is already terminal.
- Stale claim release returns CAS conflict and must not clear a newer claim.
- Claim acquisition `rowcount == 0` means another poller won the claim or the row became ineligible. Treat it as a claim conflict: skip adapter work, increment diagnostics, and never release a claim id that was not acquired.
- Abandon CAS `rowcount == 0` means the row changed status, another path already handled it, or a newer claim exists. Treat it as skipped/conflict, do not assume abandon success, do not mark `poll_abandoned_at`, and rely on a later eligible round if the wait is still cancelled.

Invariants:

- Adapter calls never occur inside a Host SQLite transaction.
- At most one unexpired poll claim exists per wait record because the claim lives on the row.
- `resolve_wait` remains the only path that writes resume / terminal canonical facts for ready or lost outcomes.
- The same poll idempotency key is reused for every poll resolution attempt for the same wait.
- Backoff state is a retry/diagnostic hint, not business truth and not recovery proof.

Tests:

- Add schema tests for new columns, checks, indexes, and schema version.
- Add state tests:
  - claim eligible waiting row;
  - skip future `poll_next_observe_at`;
  - skip unexpired claim;
  - acquire expired claim;
  - stale release cannot clear newer claim;
  - cancelled row with `poll_abandoned_at` is not eligible;
  - terminal wait transition clears `poll_claim_id`, `poll_claim_owner_id`, `poll_claimed_at`, and `poll_claim_expires_at`.
- Update polling tests:
  - two poller instances: second does not call adapter while first claim is active;
  - claim acquisition conflict increments diagnostics and does not call adapter or release an unacquired claim;
  - expired claim allows retry;
  - not-ready sets durable backoff and next round skips until due;
  - resolve failure releases with backoff and later retry uses the same idempotency key;
  - missing adapter records retryable `missing_adapter` diagnostics and capped backoff without terminalizing the wait;
  - abandon CAS conflict is treated as skipped and leaves later cancelled retry possible;
  - abandon success is durable and suppresses later abandon by a new poller instance.

Validation commands:

```bash
source .venv/bin/activate
pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_wait_adapter_polling.py
pyright
```

Expected assertions:

- Focused tests pass.
- Pyright reports no new or expanded errors.
- No production path uses a separate claim table or runtime-only claim state.

Stop condition:

- Stop if wait-row extension cannot express stale claim CAS safely.
- Stop if `resolve_wait` terminal updates cannot clear claim fields without weakening existing idempotency tests.
- Stop if a separate claim table becomes necessary; that changes the plan decision and needs controller review.

### Slice 2: Backoff-Aware Poller Supervisor And Lifecycle

Objective:

- Add the production background loop and lifecycle around the claim-aware poller.
- Make sleep cancellation, close drain, runtime diagnostics, and in-flight boundaries testable without `open_host` integration.

Allowed files/modules:

- `dayu/host/wait_adapter.py`
- optional new `dayu/host/wait_poller.py` if supervisor code would make `wait_adapter.py` too large
- `dayu/host/api.py`
- `tests/host/test_wait_adapter_polling.py`
- optional new `tests/host/test_wait_poller_runtime.py`

Prerequisites:

- Slice 1 accepted and claim-aware `WaitPoller.poll_once()` works directly.

Exact changes:

- Add `WaitPollerRuntimePolicy` with validated positive fields:
  - `poll_interval_seconds`
  - `claim_ttl_seconds`
  - `claim_batch_size`
  - `backoff_initial_delay_seconds`
  - `backoff_multiplier`
  - `backoff_max_delay_seconds`
  - `close_drain_timeout_seconds`
- Add centralized backoff calculation helper; do not scatter numeric defaults.
- Add `WaitPollerSupervisor` with:
  - `open(...)`;
  - `close()`;
  - `drain_once_for_test()`;
  - `diagnostics_snapshot()`.
- Add a lifecycle gate checked:
  - before claiming;
  - after adapter observation and before `resolve_wait`;
  - before cancelled `abandon_wait`;
  - before the next sleep.
- Add diagnostics dataclasses for loop status and cumulative counters.

Data flow / state transitions:

```text
supervisor.open
  -> start background task
  -> loop:
       wait until not closed
       poller.poll_once(policy batch/claim/backoff inputs)
       update runtime diagnostics
       cancellable sleep(policy.poll_interval_seconds)
  -> close:
       set closed gate
       wake sleep
       wait for current round to drain
       prevent post-close resolve/abandon side effects
```

Error handling:

- Per-wait adapter / resolve errors stay inside `poll_once()` and update wait backoff.
- Unexpected loop-level exceptions are logged and recorded in diagnostics, then the loop exits with status `failed`.
- `close()` is idempotent.
- If close begins after adapter returns but before `resolve_wait`, skip resolve, release the claim as `shutdown_skipped`, and let a later opener retry.
- If close begins after `resolve_wait` entered the command path, let the command finish.
- If `close_drain_timeout_seconds` fires, `close()` records/logs the timeout and continues waiting until the running poll task/thread is stopped; it must not return while the poller can still access the durable store.

Invariants:

- No new adapter call starts after the supervisor close gate is set.
- Close does not write `CANCEL_REQUESTED`, `RUN_CANCELLED`, `RUN_FAILED`, or any user-intent canonical fact.
- Supervisor diagnostics do not drive recovery decisions.
- The supervisor does not own scheduler wakeup beyond what `resolve_wait` already triggers.

Tests:

- `drain_once_for_test()` can process one ready wait and one not-ready wait with injected tiny policy.
- Background loop polls repeatedly but respects durable backoff.
- `close()` wakes an idle sleeping loop promptly.
- `close()` is idempotent.
- Close before resolve skips result submission and leaves wait retryable.
- Close drain timeout records/logs a timeout and still prevents durable store close until the in-flight poll path has actually stopped.
- Unexpected loop exception moves diagnostics to failed state without corrupting durable wait state.

Validation commands:

```bash
source .venv/bin/activate
pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py
pyright
```

Expected assertions:

- Lifecycle tests pass deterministically with injected policy and clock.
- No test depends on wall-clock long sleeps.
- Pyright reports no new or expanded errors.

Stop condition:

- Stop if synchronous adapter calls make bounded close impossible without changing the adapter protocol.
- Stop if supervisor needs to call private `open_host` internals rather than typed ports.
- Stop if diagnostics require EventLog changes; that would need design-source update before implementation.

### Slice 3: `open_host` Integration, Public Construction Wiring, Docs, And Final Validation

Objective:

- Connect the production wait poller supervisor into `open_host(...)`.
- Add construction-time poll adapter registry wiring and final documentation updates.

Allowed files/modules:

- `dayu/host/tooling.py`
- `dayu/host/api.py`
- `dayu/host/open_host.py`
- `dayu/host/wait_adapter.py` or `dayu/host/wait_poller.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_public_lifecycle_smoke.py` only if existing open-host lifecycle coverage is the better fit
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`

Prerequisites:

- Slice 1 and Slice 2 accepted.
- Direct supervisor tests cover lifecycle before composition wiring.

Exact changes:

- Add `wait_poll_adapter_registry` to `HostToolingOptions`.
- Add `wait_poller_policy` to `OpenHostOptions`; default `None` keeps existing behavior.
- Convert public opener options into supervisor construction only inside `open_host`.
- Construct the supervisor after `HostCommandHandle` exists and before returning `_PublicHostHandle`.
- Store supervisor in `_PublicHostHandle` and close it before scheduler close.
- In open failure cleanup, close supervisor before scheduler/durable store cleanup if it was created.
- If `wait_poller_policy` is enabled but no poll adapter registry is provided, fail fast during opener construction with a typed configuration error.

Data flow / state transitions:

```text
open_host(options)
  -> durable store
  -> scheduler
  -> startup recovery scan leaves WAITING runs in place
  -> command handle
  -> wait poller supervisor when enabled
  -> public handle

wait poller ready/lost
  -> internal resolver wrapper
  -> command resolve_wait(...)
  -> existing after-commit scheduler wakeup
```

Error handling:

- Opener construction failure closes supervisor, scheduler, projections, and durable store in that order.
- Public handle close closes poller before scheduler so shutdown does not create new resume Attempts after dispatch runtime starts stopping.
- Missing poll adapter registry with enabled policy is a construction-time error, not a loop warning.

Invariants:

- `open_host` remains the composition root; Service does not control poll loop or scheduler wakeups.
- Host public methods still fail fast after close.
- Poller integration does not add Service-facing wait APIs.
- Existing no-poller open_host tests continue to work because default policy is disabled.

Tests:

- Opening with `wait_poller_policy=None` does not create a poller and preserves existing behavior.
- Opening with enabled policy and missing `wait_poll_adapter_registry` fails fast.
- Opening with enabled policy and registered adapter resolves a seeded waiting poll row through the background loop.
- Closing an open host with enabled poller closes poller before scheduler and does not write user cancel facts.
- Open failure cleanup closes a created poller before durable store close.

Validation commands:

```bash
source .venv/bin/activate
pytest tests/host/test_open_host_runtime.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_resolve_wait_command.py
pytest tests/host/test_public_lifecycle_smoke.py
pyright
git diff --check
```

Expected assertions:

- Focused Host runtime tests pass.
- Existing resolve_wait tests still pass.
- Public lifecycle smoke still passes or any failure is directly attributable and fixed in-slice.
- Pyright reports no new or expanded errors.
- `git diff --check` has no output.

Stop condition:

- Stop if `open_host` cannot close poller before scheduler without broad lifecycle redesign.
- Stop if adding construction options creates large unrelated test churn that indicates the option boundary is wrong.
- Stop if README/design updates reveal a mismatch with Host design-source boundaries.

## Docs Decision

During implementation:

- Check and likely update `docs/host/design.md` because durable wait record schema gains poll claim/backoff fields and lifecycle semantics. The update should be minimal and should not introduce EventLog diagnostics for ordinary poller health.
- Check and likely update `dayu/host/README.md` because `dayu/host/` production behavior and construction-time wait poller wiring change. Read its `Agent更新约束` before editing.
- Check and likely update `tests/README.md` because new Host wait poller runtime tests will be added. Read its update constraints before editing.
- Do not update root `README.md` unless implementation changes user-visible CLI/Web/WeChat workflows, install steps, command parameters, log locations, or workspace files. This plan does not require that.
- Do not update `docs/engine/design.md`; Engine contract is unchanged.
- Do not update `dayu/README.md` unless implementation changes UI / Service / Host / Agent boundary text. This plan keeps the boundary unchanged.

This plan gate itself only creates this artifact and intentionally does not modify README or design sources.

## Risks / Open Questions

### Blocking Open Questions

None.

### Residual Risks

- Synchronous adapter calls cannot be forcibly killed by Python. Owner: WU-WAIT-02 implementation Slice 2. Destination: lifecycle tests and documentation of adapter bounded-call expectation.
- Durable backoff resets only when implementation explicitly does so. Owner: WU-WAIT-02 Slice 1. Destination: state tests for success / abandon / shutdown transitions.
- Missing adapter uses capped-delay indefinite retry and does not terminalize waits in this WU to avoid false terminalization during deployment/configuration gaps. Owner: WU-WAIT-02 Slice 1. Destination: wait-row `poll_last_outcome` / runtime diagnostics for operator visibility; future owner WU-WAIT-03 or provider lifecycle work if terminal provider-failure policy is needed.
- Shared per-wait backoff can reach maximum delay faster after repeated crash / claim-expiry / takeover cycles. Owner: WU-WAIT-02 Slice 1. Destination: bounded by `backoff_max_delay_seconds` and documented as intentional shared-throttling behavior.
- Multi-process tests may be expensive. Owner: WU-WAIT-02 implementation/review. Destination: at minimum durable CAS unit tests; add a focused multiprocess test only if single-process CAS tests cannot prove the invariant.
- Full external job revoke/cancel is still not guaranteed. Owner: WU-WAIT-03.
- UI / Service production-grade awaiting E2E smoke remains out of scope. Owner: WU-WAIT-04.

## Why This Is Not Over-Designed

- The claim is stored on the wait row, not in a generic lease service or scheduler framework.
- There is no new Run / Attempt state and no Engine API change.
- The poller still delegates all real state transition work to `resolve_wait`.
- Backoff is one small Host-owned policy with injected defaults, not a generic retry framework.
- Diagnostics are runtime/log/read-view only, avoiding new EventLog or projection systems for ordinary loop health.
- Three slices map to real dependency boundaries: durable CAS primitive, runtime lifecycle, and composition/docs. There are no module-count slices.

## Completion Report Format

Implementation agents should close each slice with:

```text
Slice: <id/name>
Changed files:
- <paths>
Behavior implemented:
- <short bullets>
Validation:
- <commands and results>
Docs:
- <checked/updated docs>
Residual risks:
- <classified risks and owner/destination>
Stop conditions hit:
- <none or details>
```

Final work-unit closeout should report:

```text
Artifact path: docs/host/wu-wait-02-production-poller-plan.md
Plan verdict: code-generation-ready
Recommended slice count: 3
Blocking open questions: none
Files modified outside plan artifact during plan gate: none
```
