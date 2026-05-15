# Gateflow Code Review: Host P5-S4 EngineEvent Ingest Mapping And Terminal Closeout

- **Gate**: Host Phase 5 P5-S4 code review
- **Reviewer**: AgentDS
- **Artifact**: `docs/reviews/gateflow-code-review-host-p5-s4-engine-event-ingest-ds-20260515.md`
- **Date**: 2026-05-15
- **Design source**: `docs/host/design.md` §13.4, §17, §22
- **Control doc**: `docs/host/implementation-control.md` gate P5-S4
- **Accepted plan**: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md` P5-S4, §3.1, §3.5, §3.6
- **Reviewed files**:
  - `dayu/host/engine_ingest.py`
  - `dayu/host/durable/event_log.py`
  - `dayu/host/durable/run_transition.py`
  - `dayu/host/durable/state.py`
  - `tests/host/test_engine_ingest_mapping.py`
  - `tests/host/test_phase5_local_execution_integration.py`

## Validation Results

| Check | Result |
| --- | --- |
| `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_phase5_local_execution_integration.py -q` | 10 passed |
| `python -m pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean, no whitespace issues |

## Blocking Findings

**0 blocking findings.**

## Non-Blocking Findings (3)

### NB-1: Test helper duplication between test files

Both `tests/host/test_engine_ingest_mapping.py` and `tests/host/test_phase5_local_execution_integration.py` define identical private helpers: `_NeverCancelledToken`, `_SeededRun`, `_statuses` (similar but not identical), `_payload`, `_options`, `_seed_active_run`. This is ~150 lines of duplicated test infrastructure. Not blocking — tests pass and exercise distinct concerns — but the duplicated seed logic will accumulate drift as schema evolves. Consider a shared `tests/host/conftest.py` or a `_test_helpers.py` module in a future cleanup slice.

**Severity**: low. **Action**: optional future cleanup; no code change required now.

### NB-2: No explicit test for terminal_already_closed late rejection

`_late_rejection_reason()` in `engine_ingest.py:1120` correctly rejects events when `run.terminal_event_id is not None or attempt.terminal_event_id is not None`. However, `test_stale_execution_id_is_rejected_diagnostic` only exercises the stale `execution_id` rejection path (`_REASON_STALE_EXECUTION_ID`). The `_REASON_TERMINAL_ALREADY_CLOSED` path is not explicitly tested. The mechanism is identical (same `_append_rejected_diagnostic` call, same `REJECTED` status), and the core invariant (no canonical facts on rejected events) is verified by the stale-execution test. The absence of a terminal-late test does not indicate a bug, but a targeted test would strengthen the evidence that duplicate-after-terminal is handled before state mutation.

**Severity**: low. **Action**: add a terminal-already-closed rejection test in a follow-up if time permits; not required for gate acceptance.

### NB-3: No explicit test for run_suspended/tool_awaiting diagnostic-then-failed paths

`_diagnostic_then_failed_waiting()` handles `run_suspended` and `tool_awaiting` by appending a diagnostic and closing to FAILED with `unsupported_later_owner=phase7`. This path is structurally identical to the `context_compaction_requested(recoverable)` path, which IS tested. The code path is exercised via the same `_close_terminal` / `_merge_diagnostic_and_closeout` mechanism. The absence of explicit `run_suspended`/`tool_awaiting` tests does not indicate a bug; however, these are explicitly listed in the plan as unsupported paths that "must" produce diagnostic + FAILED. A dedicated test would provide direct evidence.

**Severity**: low. **Action**: optional; can be added when unsupported path testing is expanded.

## Controlled Scope Expansion: `dayu/host/durable/state.py`

### Ruling: ACCEPTED — architecturally justified, minimal, preferable to alternative

The implementation artifact reports that `state.py` was not in the original P5-S4 allowed files and asks for controller/reviewer adjudication.

**Analysis**:

1. The two additions are `cancel_cancelling_run_row()` (Run CANCELLING → CANCELLED CAS) and `cancel_running_attempt_row()` (Attempt RUNNING → CANCELLED CAS). Together they total ~80 lines including docstrings.

2. These are durable row CAS mutations on the `host_runs` and `host_attempts` tables. The design doc (design.md §2, lines 43-56) explicitly assigns "EventLog / State Transition" as the "唯一负责" owner of canonical fact atomic updates to Run / Attempt indexes. State.py is already the established owner of all Run/Attempt row CAS helpers (`terminal_run_row`, `terminal_attempt_row`, `mark_attempt_running_row`, `mark_run_cancelling_row`, `cancel_queued_run_row`, `cancel_starting_attempt_row`, `cancel_running_run_row`, etc.).

3. Writing these SQL UPDATE statements directly in `run_transition.py` would bypass:
   - The `RunMutationResult` / `AttemptMutationResult` typed return envelope
   - The `_run_mutation_result_for_active()` / `_attempt_mutation_result_for_active()` CAS classification (UPDATED/CAS_LOST/NOT_FOUND/INVALID_STATE)
   - The single-owner, single-source-of-truth pattern already established across P5-S1 through P5-S3

4. The expansion is minimal: only two functions, both following the exact same patterns as existing state.py helpers. No new imports, no new table access patterns, no new result types.

5. `run_transition.py` correctly imports and calls these helpers through the typed `from dayu.host.durable.state import ...` boundary, maintaining the layered architecture: state.py owns row CAS, run_transition.py orchestrates multi-event append + multi-row CAS in transaction.

**Conclusion**: Writing these CAS operations in `run_transition.py` would be the inferior choice. The expansion to `state.py` is the correct root-cause fix. Scope expansion is accepted.

## Detailed Review By Area

### 1. Host-owned envelope identity; EngineEvent contract unchanged

`LocalEngineEnvelope` (engine_ingest.py:111) and `EngineEventCandidate` (engine_ingest.py:137) carry all Host identity fields (`session_id`, `run_id`, `attempt_id`, `execution_id`, `dispatch_record_id`, `worker_kind`, `execution_target`, `local_worker_id`, `cancellation_token`). `EngineEvent` is imported unchanged from `dayu.engine.contracts.engine_events`. No modification to Engine public contract. No `__all__` in `engine_ingest.py` (line 1794) exposes only Host-owned types. **PASS**.

### 2. Event ID derivation and duplicate candidate idempotency

Event ID derivation (`_event_id`, engine_ingest.py:1135) matches the plan formula exactly: `event-engine-` + `sha256_digest_json({execution_id, worker_event_index, event_class, event_type, sub_index}).removeprefix("sha256:")`.

Duplicate detection is implemented in two layers:
- `_duplicate_terminal_result()` (line 279): pre-ingest check computes expected terminal event IDs and reads existing rows. Returns DUPLICATE with existing events if all expected IDs exist.
- `_close_terminal()` (line 513) and `_close_active_cancel()` (line 616): post-terminal-summary-write check before state CAS.
- Duplicate check executes BEFORE `_late_rejection_reason()`, satisfying the plan requirement: "重复候选在迟 terminal 拒绝前识别，使 replay 返回既有结果而不添加 canonical fact".

`test_duplicate_candidate_returns_existing_result` verifies: first ingest returns ACCEPTED, second returns DUPLICATE with same event IDs, only 1 canonical event per type exists in EventLog. **PASS**.

### 3. Durable Run/Attempt/dispatch identity validation

`_validate_durable_context()` (line 479) reads Run, Attempt, and dispatch record via their typed readers from state.py. Validation checks:
- All three rows exist (not None)
- `run.session_id == envelope.session_id`
- `run.run_id == envelope.run_id`
- `attempt.run_id == envelope.run_id`
- `attempt.execution_id == envelope.execution_id`
- `dispatch_record.dispatch_record_id == envelope.dispatch_record_id`
- `dispatch_record.execution_id == envelope.execution_id`

`_validate_candidate_shape()` (line 1087) additionally validates:
- `worker_event_index > 0`
- `observed_at` is UTC aware via `_validate_observed_at()`
- Envelope and EngineEvent `session_id`/`run_id` agree
- `engine_event.occurred_at` is timezone-aware

Stale execution rejection: `test_stale_execution_id_is_rejected_diagnostic` confirms REJECTED status, DIAGNOSTIC event class, no canonical facts written, Run/Attempt status unchanged. **PASS**.

### 4. final_answer → ATTEMPT_SUCCEEDED + RUN_SUCCEEDED

`_final_answer_plan()` (line 1349) constructs `_TerminalPlan` with:
- `attempt_event_type=ATTEMPT_SUCCEEDED`, `run_event_type=RUN_SUCCEEDED`
- `attempt_status=SUCCEEDED`, `run_status=SUCCEEDED`
- `terminal_summary` containing `content`, `finish_reason`, `filtered`, `degraded`
- `finish_reason`, `filtered`, `degraded` set from `FinalAnswerData`

`_write_terminal_summary()` (line 1010) creates a `SQLitePayloadWriteRequest` with `payload-engine-terminal-{event_id}` ref, `application/json` media type, and `kind=engine_terminal_summary` metadata.

`terminal_closeout_in_transaction()` in run_transition.py writes the canonical events with payload containing `terminal_summary_ref`, `terminal_summary_digest`, `engine_event_ref`, `finish_reason`, `filtered`, `degraded`.

`test_final_answer_closes_attempt_and_run_with_phase5_payload` verifies all fields present and Run/Attempt statuses correctly transitioned. `test_duplicate_candidate_returns_existing_result` uses final_answer as the duplicate case. **PASS**.

### 5. run_failed false/true

- `run_failed(recoverable=False)`: Direct `_run_failed_plan()` → `_close_terminal()` with `ATTEMPT_FAILED` + `RUN_FAILED`, reason=`error_code`, `unsupported_later_owner=None`. Verified by `test_run_failed_recoverable_false_closes_failed`.
- `run_failed(recoverable=True)`: Appends DIAGNOSTIC with `unsupported_later_owner=phase10`, then `_run_failed_plan()` with `reason=unsupported_recovery_policy` → `_close_terminal()` with `sub_index_offset=1`. Results are merged via `_merge_diagnostic_and_closeout`. Verified by `test_run_failed_recoverable_true_is_diagnostic_then_failed` — Run status is FAILED, not RECOVERING. **PASS**.

### 6. context_compaction_requested budget_state=None

`_context_compaction_payload()` (line 1667) records `budget_state_present=data.budget_state is not None` as boolean, NOT by checking budget_state content. When `budget_state=None`, `budget_state_present=False`. The diagnostic is appended, then `_unsupported_recovery_plan()` → FAILED closeout. No protocol error raised for `None` budget_state.

Verified by `test_context_compaction_requested_accepts_none_budget_and_fails`: `budget_state_present is False`, Run → FAILED. **PASS**.

### 7. run_suspended/tool_awaiting unsupported paths

Both go through `_diagnostic_then_failed_waiting()` (line 711): diagnostic event → `_unsupported_waiting_plan()` → FAILED closeout with `unsupported_later_owner=phase7`. No WAITING state created. The code path is structurally identical to the tested context_compaction path. **PASS**.

### 8. usage_reported → projection_signal, no state side effect

`_append_projection_signal()` (line 834) creates `EventClass.PROJECTION_SIGNAL` with `event_type=USAGE_REPORTED`. Payload contains `attempt_id`, `execution_id`, `iteration_id`, `prompt_tokens`, `completion_tokens`, `total_tokens`. No Run/Attempt state mutation — `_single_event_result()` returns `terminal_closeout=False`.

Verified by `test_usage_reported_is_projection_signal_without_state_change`: event_class is PROJECTION_SIGNAL, Run remains RUNNING, Attempt remains RUNNING. **PASS**.

### 9. clean EOF without terminal → FAILED

`close_clean_eof()` (line 303) constructs a synthetic `RUN_FAILED` EngineEvent with `worker_event_index = last_observed_worker_event_index + 1`, runs through the full validate → duplicate-check → late-check → terminal-closeout pipeline, using `_failed_lifecycle_plan(reason=stream_ended_without_terminal)`.

Verified by `test_clean_eof_without_terminal_closes_failed`: event types are ATTEMPT_FAILED + RUN_FAILED, payload reason is `stream_ended_without_terminal`, Run → FAILED, Attempt → FAILED, wakeup triggered. **PASS**.

### 10. worker lost → LOST

`close_worker_lost()` (line 332) validates `worker_lifecycle_signal` non-empty and constructs `_lost_lifecycle_plan()` with all required fields: `worker_lifecycle_signal`, `stream_error_code`, `last_observed_worker_event_index`, `last_accepted_event_id`.

Verified by `test_stream_error_or_worker_crash_closes_lost`: event types are ATTEMPT_LOST + RUN_LOST, payload contains `worker_lost_before_terminal` reason, `worker_crash` signal, `broken_stream` error code, Run → LOST, Attempt → LOST. **PASS**.

### 11. run_cancelled after active cancel → CANCELLED

`_close_active_cancel()` (line 616):
1. Computes event IDs for ATTEMPT_CANCELLED + RUN_CANCELLED
2. Checks duplicate
3. Reads `RUN_CANCELLING` event via `read_latest_run_event_by_type` to recover `cancel_request_event_id`
4. Returns REJECTED with "run_cancelled_without_active_cancel" if no RUN_CANCELLING exists
5. Calls `active_cancel_closeout_in_transaction()` which validates: Run=CANCELLING, Attempt=RUNNING, dispatch has `worker_accept_event_id`
6. CAS: `cancel_running_attempt_row` (RUNNING→CANCELLED) and `cancel_cancelling_run_row` (CANCELLING→CANCELLED)

Verified by `test_run_cancelled_after_active_cancel_closes_cancelled`: event types correct, `cancel_request_event_id` matches the one from `CANCEL_REQUESTED`, Run → CANCELLED, Attempt → CANCELLED. **PASS**.

### 12. Terminal closeout queue promotion wakeup

Both `ingest()` (line 267) and `_close_worker_lifecycle()` (line 798) check `result.terminal_closeout and result.status == ACCEPTED`, then call `wakeup_port.wake_queue_promotion(session_id)` and return `promotion_triggered=True`.

The implementation artifact states that wakeup_port uses `NoopAdmissionWakeupPort` by default (no-op), but `_WakeupSpy` in integration tests records the call. `test_clean_eof_without_terminal_closes_failed` verifies `wakeup.promoted_session_ids == [seeded.session_id]`. **PASS**.

### 13. EventLog reader addition: read_latest_run_event_by_type

Added to `event_log.py` (line 501) as both a `EventLogStore` method and a module-level function. Queries `event_log` table with `WHERE run_id = ? AND event_type = ? ORDER BY event_sequence DESC LIMIT 1`. Only used by `_close_active_cancel` to read the `RUN_CANCELLING` event. Narrow scope, properly typed, Chinese docstring, validates inputs. **PASS**.

### 14. Project constraints check

| Constraint | Status |
| --- | --- |
| No `Any`/`object`/untyped public signatures | PASS — all public types fully typed |
| Chinese docstrings on all functions | PASS — all functions have Chinese docstrings with param/return/raises |
| No compatibility code | PASS — no re-exports, facades, or old-schema compatibility |
| No extra payload abuse | PASS — all data flows through typed dataclass fields |
| No `hasattr`/`getattr` abuse | PASS — none found |
| No unrelated formatting churn | PASS — diffs focused on P5-S4 scope only |
| No Engine contract modification | PASS — EngineEvent imported unchanged |
| No backward dependency | PASS — engine_ingest depends on host.durable, not vice versa |
| No RECOVERING created | PASS — all unsupported paths → FAILED |

### 15. Test assertion quality assessment

- `test_final_answer_*`: Verifies status (ACCEPTED), event types list, terminal_closeout, promotion_triggered, Run/Attempt statuses, payload fields including terminal_summary_ref/digest — good coverage.
- `test_run_failed_recoverable_false`: Verifies event types, error_code, recoverable, Run/Attempt statuses — adequate.
- `test_run_failed_recoverable_true`: Verifies event classes order (DIAGNOSTIC → CANONICAL_FACT → CANONICAL_FACT), unsupported_later_owner, Run status is FAILED not RECOVERING — good.
- `test_context_compaction_*`: Verifies diagnostic class, ATTEMPT_FAILED type, budget_state_present, Run → FAILED — adequate.
- `test_usage_reported_*`: Verifies PROJECTION_SIGNAL class, event_type, token counts, Run/Attempt remain RUNNING — good.
- `test_duplicate_candidate_*`: Verifies first=ACCEPTED, second=DUPLICATE, same event_ids, event count == 1 per type — good.
- `test_stale_execution_id_*`: Verifies REJECTED, DIAGNOSTIC, no canonical facts, Run/Attempt unchanged — good.
- `test_clean_eof_*`: Verifies FAILED, reason, statuses, wakeup recorded — good.
- `test_stream_error_*`: Verifies LOST, reason, worker_lifecycle_signal, statuses — good.
- `test_run_cancelled_*`: Verifies CANCELLED, cancel_request_event_id, statuses — good.

All assertions check durable state invariants (event types, event classes, Run/Attempt statuses, payload fields). The test assertions prove the state/event invariants declared by the plan. **PASS**.

## Architecture Conformance

- EngineEvent contract: unchanged, Host-agnostic. **Conformant**.
- Envelope identity: Host-owned `LocalEngineEnvelope` / `EngineEventCandidate`. **Conformant**.
- Event ID derivation: matches plan formula. **Conformant**.
- Canonical/preview/projection_signal/diagnostic classification: matches design §13.4 mappings. **Conformant**.
- Terminal closeout policy: matches design §17 table. **Conformant**.
- Cancel closeout: matches design §22 semantics (active cancel → CANCELLING → CANCELLED). **Conformant**.
- State ownership: row CAS in state.py, orchestration in run_transition.py, ingest classification in engine_ingest.py. **Conformant**.
- No cross-layer import violations. **Conformant**.

## Summary

| Category | Count |
| --- | --- |
| Blocking findings | 0 |
| Non-blocking findings | 3 (all low severity) |
| Controlled scope expansion | ACCEPTED (state.py justified) |
| Tests passed | 10/10 |
| pyright errors | 0 |
| Architecture conformance | PASS |
| Project constraints | PASS |

**Gate recommendation**: ACCEPT. P5-S4 implementation is complete per the accepted plan. No blocking issues found.
