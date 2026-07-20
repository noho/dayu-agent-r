# WU-SEMANTIC-OWNERSHIP-01 P3-A aggregate fix - Controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-A`.
- Gate: aggregate fix controller validation.
- Accepted findings: `P3-A-AGG-F01`, `P3-A-AGG-F02`.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-aggregate-fix-codex.md`.
- Validation date: 2026-07-10.

## First-principles judgment

The findings are real. `START_BLOCKING_RUN_STATUSES` owns the set of Run statuses that occupy or block the active slot, but `_read_active_run_id` and four start-transition `NOT EXISTS` guards independently copied the current five members. That duplication could make durable reads, snapshot projection, and write admission disagree when the owner set evolves.

The fix is located at the consumer boundary immediately downstream of the owner: all five SQL consumers now obtain placeholders and serialized parameters from `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`. No downstream display exception, compatibility wrapper, second status tuple, or schema change was introduced.

## Independent inspection

- `_read_active_run_id` consumes the owner-generated clause and parameters, matching `read_active_run_for_session`.
- `promote_queued_run_row`, `start_unstarted_run_row`, `resume_waiting_run_row`, and `start_recovering_run_row` consume the same owner-generated material in their active-run guards.
- `state.py` contains no remaining `status IN (?, ?, ?, ?, ?)` copy.
- The two new tests use real SQLite behavior and temporarily replace the owner set with `{QUEUED}`. They prove both read/snapshot agreement and all four write guards' dynamic consumption, while retaining the unblocked `UPDATED -> RUNNING` path.
- `docs/cli_ci.md` is unrelated and remains untouched and unstaged.

## Validation

```text
source .venv/bin/activate && pytest \
  tests/host/test_state_schema.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_public_run_api.py \
  tests/host/test_recovery_dispatch.py \
  tests/host/test_active_cancel_dispatch.py \
  tests/host/test_lifecycle_events.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_public_cancel_session_runs.py \
  tests/host/test_phase5_local_execution_integration.py \
  tests/host/test_dispatch_scheduler.py -q
337 passed in 3.65s
```

```text
source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations
```

```text
git diff --check
clean
```

Source scans:

- `run_status_in_clause(START_BLOCKING_RUN_STATUSES)`: six total consumers, including the existing public read plus all five aggregate-fix targets.
- `status IN (?, ?, ?, ?, ?)` in `dayu/host/durable/state.py`: zero matches.

## Propagation audit

```text
RunStatus + durable terminal rules
  -> NON_TERMINAL_RUN_STATUSES
  -> START_BLOCKING_RUN_STATUSES
  -> serialized_run_status_values / run_status_in_clause
  -> public active read + snapshot active_run_id
  -> four start-transition CAS guards
  -> durable Run status and public Session projection
```

The same owner material now governs read, write admission, persistence transition, and user-visible Session projection. This change does not alter EventLog facts, memory, trace, prompts, tool schemas, or other LLM-facing text.

## Decision

- `P3-A-AGG-F01`: fixed, pending independent re-review.
- `P3-A-AGG-F02`: fixed, pending independent re-review.
- Deferred `P3-A-AGG-F03` remains owned by P3-J and is not reopened here.
- Blocking open question: none.
- Next gate: parallel aggregate re-review by AgentMiMo and AgentDS.
