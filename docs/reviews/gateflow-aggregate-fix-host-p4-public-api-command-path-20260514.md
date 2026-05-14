# Aggregate Fix: Host Phase 4 Public API / Command Path

- **Date**: 2026-05-14
- **Scope**: Phase 4 aggregate deepreview follow-up
- **Fix owner**: Controller
- **Source reviews**:
  - `docs/reviews/gateflow-aggregate-deepreview-host-p4-public-api-command-path-mimo-20260514.md`
  - `docs/reviews/gateflow-aggregate-deepreview-host-p4-public-api-command-path-ds-20260514.md`

## Accepted Fix

### P4-AGG-MIMO-F1

MiMo identified that `cancel_session_runs` already carried explicit Phase 5 / 7 / 11 owner reminders, while `cancel_run` only used a generic "later owner" phrasing.

Decision: accepted as a documentation hardening fix. This strengthens the user-requested follow-up reminder and avoids ambiguity for later phase owners without changing Phase 4 behavior.

Changes:

- `dayu/host/command.py`: expanded `cancel_run` docstring to state that dispatching / active worker cancel belongs to Phase 5, `WAITING` cancel belongs to Phase 7, and `RECOVERING` cancel belongs to Phase 11.
- `dayu/host/README.md`: expanded the public `cancel_run` description with the same Phase 5 / 7 / 11 ownership mapping.

## Deferred / Non-Issue Findings

- MiMo F2: `cancel_session_runs` no-promotion behavior is already covered by `active_run_id is None`; no production change required.
- MiMo F3: direct `WAITING` / `CANCELLING` / `RECOVERING` public cancel tests are deferred to the phases that can create those states.
- MiMo F4 / F5 / F6: accepted as informational.
- DS findings 1-5: accepted as informational or documented design limitations; no production change required.

## Validation

```
source .venv/bin/activate && pytest tests/host -q
201 passed

source .venv/bin/activate && python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations

git diff --check
passed
```

## Residual Risk

Phase 4 still intentionally implements only queued / pre-dispatch `STARTING` cancel. Later phases must complete full session-scope and per-run cancel coverage:

- Phase 5: dispatching / active worker cancel propagation.
- Phase 7: `WAITING` cancel and wait record cancellation.
- Phase 11: `RECOVERING` cancel and recovery dispatch cancellation.
