# WU-LIFE-03 Slice 1 Fix Artifact

## Scope

- Work unit: WU-LIFE-03 Active cancel watchdog and post-cancel timeout
- Gate: fix
- Slice: Slice 1 Durable Timeout Closeout Contract And Race Tests
- Agent: AgentCodex
- Date: 2026-07-04

## Changed Files

- `dayu/host/durable/run_transition.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_run_attempt_transitions.py`
- `docs/reviews/wu-life-03-slice1-fix-codex.md`

No fix changes were made outside the allowed production, test, and artifact files.

## Finding-by-finding Status

### S1-CR-F01: duplicated RUN_CANCELLING cancel request parser

Status: 已修复。

- Kept one parser implementation in `dayu/host/durable/run_transition.py` as private helper `_cancel_request_event_id_from_cancelling(...)`.
- Removed the duplicate implementation from `dayu/host/engine_ingest.py`.
- `engine_ingest.py` now imports and reuses the durable private helper, so cooperative active cancel and timeout closeout use the same extraction semantics.
- Removed the unclear `parse_utc_timestamp(event.occurred_at)` call from the parser. Timestamp normalization now happens only where timestamp payload is constructed.

### S1-CR-F02: timeout payload cancel_requested_at format consistency

Status: 已修复。

- `cancel_requested_at` is now produced by `format_utc_timestamp(parse_utc_timestamp(cancelling.occurred_at))`.
- The normalization intent is explicit in `_normalized_event_occurred_at(...)`.
- Invalid EventLog timestamp format raises `HostDurableError` instead of silently emitting an unnormalized payload timestamp.

### S1-CR-F03: optional diagnostic fields not tested with non-null values

Status: 已修复。

- Extended `test_active_cancel_timeout_closeout_writes_cancelled_terminal_facts`.
- The test now passes non-null `last_observed_worker_event_index=7` and `last_accepted_event_id="event-worker-delta-7"`.
- Both `ATTEMPT_CANCELLED` and `RUN_CANCELLED` timeout payloads assert those values.

### S1-CR-F04: malformed RUN_CANCELLING payload timeout path lacks direct test

Status: 已修复。

- Added `test_active_cancel_timeout_closeout_rejects_malformed_cancelling_payload`.
- The test creates a valid active cancelling state, appends a latest malformed `RUN_CANCELLING` fact missing `cancel_request_event_id`, then calls timeout closeout.
- The expected result is `INVALID_STATE`, with zero `ATTEMPT_CANCELLED` and zero `RUN_CANCELLED` timeout facts.

### S1-CR-F05: timeout self-replay lacks direct test

Status: 已修复。

- Extended `test_active_cancel_timeout_closeout_writes_cancelled_terminal_facts`.
- The test calls timeout closeout twice after the same active cancel.
- The second call returns idempotent `UPDATED` and terminal fact counts remain one `ATTEMPT_CANCELLED` and one `RUN_CANCELLED`.

## Tests Added / Updated

- Updated `tests/host/test_run_attempt_transitions.py::test_active_cancel_timeout_closeout_writes_cancelled_terminal_facts`
  - Non-null optional diagnostic fields are asserted on both timeout terminal payloads.
  - Same-timeout self-replay is asserted as idempotent `UPDATED` with no duplicate terminal facts.
- Added `tests/host/test_run_attempt_transitions.py::test_active_cancel_timeout_closeout_rejects_malformed_cancelling_payload`
  - Directly covers malformed latest `RUN_CANCELLING` payload on the timeout closeout path.

No changes were needed in `tests/host/test_engine_ingest_mapping.py` for the accepted fix findings.

## Validation

```bash
source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q
```

Result: passed, `123 passed in 1.25s`.

```bash
source .venv/bin/activate && pyright
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

Pyright also printed a tool-version notice: `there is a new pyright version available (v1.1.409 -> v1.1.411)`. This is not a project type-check failure.

```bash
source .venv/bin/activate && git diff --check
```

Result: passed, no output.

## README Decision

- `dayu/host/README.md` was checked. No update is needed because this fix does not change Host public API, public runtime assembly, stable state-machine documentation, or user-facing workflow.
- `tests/README.md` was checked. No update is needed because this fix adds focused Host transition coverage inside the existing test layer and does not introduce a new test layer, command, or maintenance rule.

## Residual Risks

- Provider/tool work may still continue physically after Host writes timeout `CANCELLED`. Owner/destination: WU-TOOLS-CANCEL-01.
- Background watchdog loop, startup ordering, recovery deferral, queued Run promotion after timeout, and public watch behavior remain outside Slice 1. Owner/destination: WU-LIFE-03 Slice 2.
- Watchdog caller handling for cross-transaction CAS-lost exceptions remains outside this fix. Owner/destination: WU-LIFE-03 Slice 2 watchdog integration.
- Timeout default value, scan interval tuning, and cross-instance UTC skew remain outside this fix. Owner/destination: Host lifecycle watchdog runtime under GitHub Issue #87.

## Stop Condition

No stop condition was hit.

- No files outside the allowed production/test/artifact set were modified by this fix.
- No schema migration was required.
- No full gateflow, review, commit, push, PR, watchdog loop, open_host startup ordering, or scheduler runtime work was performed.
