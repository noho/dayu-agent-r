# WU-SEMANTIC-OWNERSHIP-01 P1-B Fix Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-B`
- Gate: fix controller validation
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-b-fix-codex.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-p1-b-code-review-controller-adjudication.md`
- Result: pass to fix re-review.

## Accepted Finding Closure

- `P1B-CODE-ACCEPTED-F01`: closed. Watchdog helper docstrings now describe typed `RunRow.cancel_request_event_id` with same-Run `CANCEL_REQUESTED` validation, not `RUN_CANCELLING` payload parsing.
- `P1B-CODE-ACCEPTED-F02`: closed. Added schema/state regression proving `CANCELLING` / `CANCELLED` rows without `cancel_request_event_id` fail SQLite CHECK.
- `P1B-CODE-ACCEPTED-F03`: closed. Implementation artifact now records intentional `tool_trace.py` expansion to the shared Host lifecycle event set.
- `P1B-CODE-ACCEPTED-F04`: closed. `cancel_cancelling_run_row` docstring now documents typed link preservation from `CANCELLING` to `CANCELLED`.

## Owner Boundary Check

The fix remains inside accepted owner boundaries:

- Durable transition documentation for watchdog payload builders.
- Durable schema/state regression tests for the fresh-schema CHECK invariant.
- Implementation review artifact for propagation documentation.
- Durable state mutator docstring for `CANCELLING -> CANCELLED` link preservation.

No runtime compatibility path, downstream special case, or rejected non-cancelled-link invariant was introduced.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py` -> 73 passed.
- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py tests/host/test_recovery_scan.py tests/host/test_outbox_durable.py` -> 147 passed.
- `source .venv/bin/activate && pyright` -> 0 errors, 0 warnings, 0 informations.
- `git diff --check` -> passed.

## Decision

Proceed to P1-B fix re-review with AgentMiMo and AgentDS. P1-B remains unaccepted until re-review is adjudicated.
