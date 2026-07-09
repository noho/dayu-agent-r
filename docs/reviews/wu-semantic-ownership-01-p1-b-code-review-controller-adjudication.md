# WU-SEMANTIC-OWNERSHIP-01 P1-B Code Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-B`
- Gate: code review adjudication
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p1-b-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p1-b-controller-validation.md`
- AgentMiMo review: `docs/reviews/code-review-20260709-181830-p1-b-mimo.md`
- AgentDS review: `docs/reviews/code-review-20260709-p1-b-ds.md`

## Review Results

- AgentMiMo: `pass-with-risks`, three low-severity findings.
- AgentDS: `pass-with-risks`, five non-blocking findings / notes.

No reviewer found a blocking correctness defect in the core P1-B implementation.

## Controller Decision

Decision: `fix-required`.

P1-B cannot be accepted until accepted findings below are fixed and re-reviewed.

## Accepted Findings

### P1B-CODE-ACCEPTED-F01 — Watchdog helper docstrings still describe payload parsing

- Sources: `P1B-CODE-MIMO-F03`, `P1B-CODE-DS-F01`
- Severity: low
- Owner boundary: `dayu/host/durable/run_transition.py` durable transition helper docstrings.
- Decision: accepted.
- Required fix: update `_active_watchdog_attempt_cancelled_event_request`, `_active_watchdog_run_cancelled_event_request`, and `_active_watchdog_cancelled_payload` docstrings so `cancel_request_event_id` is described as coming from the typed Run row cancel link validated against same-Run `CANCEL_REQUESTED`, not from `RUN_CANCELLING` payload parsing.

### P1B-CODE-ACCEPTED-F02 — SQLite CHECK defense lacks an explicit regression test

- Sources: `P1B-CODE-DS-F02`
- Severity: low
- Owner boundary: Host durable schema invariant tests.
- Decision: accepted.
- Required fix: add a focused test proving a fresh-schema `host_runs` row with `status='cancelling'` or `status='cancelled'` and `cancel_request_event_id=NULL` is rejected by SQLite integrity constraints.

### P1B-CODE-ACCEPTED-F03 — Tool trace lifecycle event filter expansion is not recorded in the implementation artifact

- Sources: `P1B-CODE-DS-F04`
- Severity: info
- Owner boundary: implementation artifact / propagation audit.
- Decision: accepted.
- Required fix: update `docs/reviews/wu-semantic-ownership-01-p1-b-implementation-codex.md` to explicitly record that `tool_trace.py` now observes the shared Host lifecycle event set, expanding from the previous local subset to full Host lifecycle events as a deliberate P1-B semantic convergence.

### P1B-CODE-ACCEPTED-F04 — `cancel_cancelling_run_row` relies on existing typed link without documenting that invariant

- Sources: `P1B-CODE-DS-F05`
- Severity: info
- Owner boundary: Host durable state mutator documentation.
- Decision: accepted.
- Required fix: update `cancel_cancelling_run_row` docstring to state that `cancel_request_event_id` is fixed when the Run enters `CANCELLING`, the schema guarantees it is present for `CANCELLING`, and this mutator preserves that link when closing to `CANCELLED`.

## Rejected / Deferred Findings

### P1B-CODE-MIMO-F01 / P1B-CODE-MIMO-F02 — Non-cancelled terminal Runs must reject or clear cancel links

- Decision: rejected as stated.
- Reason: the finding assumes `cancel_request_event_id` is valid only for `CANCELLED`. The accepted P1-B plan explicitly allows a Run that accepted active cancel and ultimately becomes `LOST` to retain the link as diagnostic correlation, while forbidding projections from interpreting that lost terminal as a public outbox cancel item. Therefore a stricter DB invariant requiring non-cancelled terminal rows to have `cancel_request_event_id IS NULL` would contradict the plan and over-constrain valid diagnostic state.
- Narrow accepted portion: the implementation should document the `CANCELLING -> CANCELLED` preservation invariant, covered by `P1B-CODE-ACCEPTED-F04`.

### P1B-CODE-DS-F03 — `read_api.py` mixes `HostRunEventType` with private non-terminal constants

- Decision: deferred.
- Reason: P1-B plan section 5.1 explicitly limits non-terminal lifecycle constant migration to touched consumers where required by terminal/read-model/tool-trace/outbox semantics. This is a consistency cleanup, not a P1-B correctness finding.
- Follow-up owner: a later lifecycle constant convergence sub WU, if scheduled.

## Required Fix Validation

After fixes:

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py`
- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py tests/host/test_recovery_scan.py tests/host/test_outbox_durable.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Then reroute AgentMiMo and AgentDS for P1-B fix re-review.
