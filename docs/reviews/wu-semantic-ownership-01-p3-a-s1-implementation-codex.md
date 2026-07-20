# WU-SEMANTIC-OWNERSHIP-01 P3-A S1 Implementation - AgentCodex

## Status

completed

Slice: S1 - Lifecycle/status owner helpers

Scope honored: only S1 owner helpers and owner tests were implemented. S2/S3 consumer migration, worker lifecycle closeout, code review, commit, push, and next-gate work were not performed.

## Changed Files

- `dayu/host/lifecycle_events.py`
- `dayu/host/durable/state.py`
- `tests/host/test_lifecycle_events.py`
- `tests/host/test_state_schema.py`
- `docs/reviews/wu-semantic-ownership-01-p3-a-s1-implementation-codex.md`

## Implementation Summary

- Added `HostAttemptEventType`, `HOST_ATTEMPT_TERMINAL_EVENT_TYPES`, `attempt_terminal_event_type_for_status(...)`, and `attempt_event_type_values(...)` in `dayu.host.lifecycle_events`.
- Added `run_terminal_event_type_for_status(...)` in `dayu.host.lifecycle_events`.
- Kept run event value projection typed to `tuple[HostRunEventType, ...]`; attempt projection uses the separate `tuple[HostAttemptEventType, ...]` helper. No `Any`, `object`, broad enum bag, overload, or TypeVar escape was introduced.
- Mapped all current durable Attempt terminal statuses to canonical Attempt event types: `SUCCEEDED`, `FAILED`, `CANCELLED`, `SUSPENDED`, `STEERED`, and `LOST`. `STARTING` and `RUNNING` fail fast.
- Promoted Attempt terminal status truth to public `TERMINAL_ATTEMPT_STATUSES`.
- Added `START_BLOCKING_RUN_STATUSES`, `is_terminal_run_status(...)`, `is_terminal_attempt_status(...)`, `serialized_run_status_values(...)`, and `run_status_in_clause(...)` in `dayu.host.durable.state`.
- Replaced same-file private terminal checks with the new public state predicates so row-shape validation consumes the same owner helpers.

## SM-7 Pre-S1 Verification

Command:

```bash
rg "FollowupSnapshot|accepted_run_status|RunStatus\.RECOVERING" dayu/host dayu/service dayu/cli
```

Result: found no production `FollowupSnapshot(...)` construction that directly passes `RunStatus.RECOVERING`. Production construction points are in `dayu/host/command.py`, and `accepted_run_status` is sourced from `result.run.status`. Other matches are recovery/admission/ingest status handling or the `FollowupSnapshot.__post_init__` guard itself. SM-7 remains needs-more-evidence / not in S1 scope; no durable rule was added.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_lifecycle_events.py tests/host/test_state_schema.py -q`
  - passed: `54 passed in 0.63s`
- `source .venv/bin/activate && python -c "from dayu.host.lifecycle_events import HostRunEventType, HostAttemptEventType, run_terminal_event_type_for_status, attempt_terminal_event_type_for_status; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"`
  - passed: `import-ok`
- `source .venv/bin/activate && pyright`
  - passed: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## README Decision

Inspected:

- `dayu/host/README.md`
- `tests/README.md`

Decision: no README update.

Rationale:

- `dayu/host/README.md` Agent update constraints limit it to stable package architecture, public contract, major execution paths, and state-machine guidance. S1 only adds internal owner helpers and tests; it does not change public Host behavior, durable schema, EventLog semantics, public API, lifecycle state machine, or documented execution path.
- `tests/README.md` already documents `tests/host/` as the Host public/internal durable foundation and state-machine test layer. The new `tests/host/test_lifecycle_events.py` is an owner-level Host test inside the existing layer, not a new test category or command class.

## Propagation Audit

- Run terminal event type:
  - Truth path for S1: `RunStatus` terminal statuses -> `run_terminal_event_type_for_status(...)` -> `HostRunEventType` -> `event_type_values(...)`.
  - Owner tests assert the four supported Run terminal statuses map exactly to `HOST_RUN_TERMINAL_EVENT_TYPES`, and all non-terminal Run statuses fail fast.
  - S1 does not yet migrate durable transition or ingest producers; that remains S2.

- Attempt terminal event type:
  - Truth path for S1: `AttemptStatus` terminal statuses -> `attempt_terminal_event_type_for_status(...)` -> `HostAttemptEventType` -> `attempt_event_type_values(...)`.
  - Owner tests assert all current durable Attempt terminal statuses map exactly to `HOST_ATTEMPT_TERMINAL_EVENT_TYPES`; `STARTING` and `RUNNING` fail fast.
  - S1 does not yet migrate terminal closeout producers; that remains S2/S3.

- Run status predicates and SQL values:
  - Truth path for S1: `_row_rules.TERMINAL_RUN_STATUS_VALUES` -> `TERMINAL_RUN_STATUSES` -> `NON_TERMINAL_RUN_STATUSES` / `START_BLOCKING_RUN_STATUSES` / `is_terminal_run_status(...)` / `serialized_run_status_values(...)` / `run_status_in_clause(...)`.
  - Owner tests assert terminal status derivation, non-terminal derivation, exact start-blocking membership, empty SQL helper fail-fast, placeholder count, and parameter serialization.
  - Existing row-shape validation in `state.py` now consumes `is_terminal_run_status(...)`.

- Attempt status predicates:
  - Truth path for S1: `_row_rules.TERMINAL_ATTEMPT_STATUS_VALUES` -> `TERMINAL_ATTEMPT_STATUSES` -> `is_terminal_attempt_status(...)`.
  - Owner tests assert derivation and predicate behavior for every `AttemptStatus`.
  - Existing Attempt row-shape validation in `state.py` now consumes `is_terminal_attempt_status(...)`.

- Durable state / EventLog / projection consistency:
  - S1 introduces source-of-truth helpers but intentionally does not alter durable schema, EventLog event semantics, production terminal closeout, read models, memory, audit, UI, or LLM-facing projection behavior.
  - No "display correct but durable wrong" or "trace correct but memory wrong" path is introduced because no downstream projection path was changed.

## Residual Risks / Next Slice Handoff

- S2 must migrate existing terminal event/status consumers in `run_transition.py`, `engine_ingest.py`, `admission.py`, `read_model.py`, and SQL read helpers to consume these S1 helpers.
- S2 must run the mandatory terminal `_EVENT_TYPE_(RUN|ATTEMPT)_(SUCCEEDED|FAILED|CANCELLED|LOST)` source scan and SQL/query-plan validation described in the accepted plan.
- S3 still owns worker lifecycle closeout identity, late rejection predicate migration, active-cancel decision table, and dispatch direct-cancelability owner helper.
- Non-terminal Host EventLog constants remain outside P3-A S1 scope and are residual input for later EventLog schema hardening, as recorded in the plan.
