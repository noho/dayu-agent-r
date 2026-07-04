# WU-LIFE-03 Slice 1 Implementation Artifact

## Scope

- Work unit: WU-LIFE-03 Active cancel watchdog and post-cancel timeout
- Gate: implementation
- Slice: Slice 1 Durable Timeout Closeout Contract And Race Tests
- Agent: AgentCodex
- Date: 2026-07-04

## Changed Files

- `dayu/host/durable/run_transition.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_engine_ingest_mapping.py`

No files outside the Slice 1 allowed production/test set were modified.

## Implemented Behavior

- Added independent `ActiveCancelTimeoutCloseoutInput` and `active_cancel_timeout_closeout_in_transaction(...)`.
- Timeout closeout writes existing canonical terminal facts:
  - `ATTEMPT_CANCELLED`
  - `RUN_CANCELLED`
- Timeout closeout uses terminal reason `active_cancel_timeout`.
- Timeout payload includes:
  - `dispatch_record_id`
  - `cancel_request_event_id`
  - `run_cancelling_event_id`
  - `timeout_seconds`
  - `cancel_requested_at`
  - `timed_out_at`
  - `watchdog_owner`
  - `worker_lifecycle_signal`
  - optional `last_observed_worker_event_index`
  - optional `last_accepted_event_id`
- Timeout closeout does not require or write Engine `engine_event_ref`, `accepted_at`, or `finished_at`.
- Timeout closeout reuses existing row CAS helpers:
  - `cancel_running_attempt_row(...)`
  - `cancel_cancelling_run_row(...)`
- Timeout closeout looks up `dispatch_record_id` from the existing dispatch record by `attempt_id`.
- Timeout closeout fail-closes before appending terminal facts when:
  - Run is not `CANCELLING`;
  - Attempt is not current `RUNNING`;
  - accepted dispatch record refs are missing;
  - latest `RUN_CANCELLING` fact is missing;
  - `RUN_CANCELLING` payload is malformed or missing `cancel_request_event_id`.
- Ingest now rejects `final_answer` and `run_failed` after `RUN_CANCELLING` with diagnostic reason `late_terminal_after_active_cancel`, without writing success/failure terminal facts.
- Existing late terminal after timeout remains rejected as `terminal_already_closed`.
- Existing waiting confirmation behavior keeps late `run_suspended` / `tool_awaiting` after `RUN_CANCELLING` diagnostic-only and does not move Run to `WAITING`.

## Tests Added / Updated

- `tests/host/test_run_attempt_transitions.py`
  - `test_active_cancel_timeout_closeout_writes_cancelled_terminal_facts`
  - `test_active_cancel_timeout_closeout_requires_cancelling_run`
  - `test_active_cancel_timeout_closeout_first_committer_wins_after_cooperative_cancel`
  - `test_active_cancel_timeout_closeout_rejects_after_succeeded_terminal`
- `tests/host/test_engine_ingest_mapping.py`
  - `test_late_worker_terminal_after_timeout_is_rejected_as_terminal_closed`
  - `test_late_final_answer_after_run_cancelling_is_rejected_with_diagnostic`
  - `test_late_run_failed_after_run_cancelling_is_rejected_with_diagnostic`
  - `test_late_awaiting_after_cancel_does_not_move_to_waiting`

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q
```

Result: passed, `122 passed in 1.35s`.

```bash
source .venv/bin/activate && pyright
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

```bash
source .venv/bin/activate && git diff --check
```

Result: passed, no output.

## Docs / README Decision

- `dayu/host/README.md`: read and checked. No update needed because Slice 1 adds an internal durable helper and ingest race contract only; it does not add a public Host option, public command shape, public runtime loop, or user-facing workflow.
- `tests/README.md`: read and checked. No update needed because the existing Host test ownership already covers Run / Attempt transitions and EngineEvent ingest mapping; no new test layer or required validation entry point was introduced.
- Root `README.md`: no update needed because there is no user-visible CLI/Web/WeChat workflow, install/config, output channel, log location, or troubleshooting change.
- `docs/host/design.md` / `docs/engine/design.md`: no update in this slice. The accepted plan and existing design truth already choose `CANCELLED` over `LOST` for durable accepted post-cancel timeout; Slice 1 did not introduce public runtime option or watchdog loop wiring.

## Residual Risks

- Provider/tool work may continue physically after Host timeout terminal. Owner/destination: WU-TOOLS-CANCEL-01.
- Background watchdog loop, startup ordering, recovery deferral, queued Run promotion after timeout, and public watch behavior are not implemented in this slice. Owner/destination: WU-LIFE-03 Slice 2.
- Timeout default value and scan interval tuning are not handled in this slice. Owner/destination: Host lifecycle watchdog runtime under GitHub Issue #87.
- Cross-instance UTC skew can affect future watchdog eligibility timing. Owner/destination: Host lifecycle watchdog runtime tuning under GitHub Issue #87.

## Stop Conditions

No stop condition was hit.

- No durable schema/table/index migration was required.
- Current design was sufficient to choose `CANCELLED` rather than `LOST`.
- No files outside the allowed Slice 1 production/test set were touched.
- No review, commit, push, PR, watchdog loop, open_host startup ordering, or scheduler runtime loop work was performed.
