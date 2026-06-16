# WU-CLI-FINS-OBS-01 Slice D Review Fix

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: D, Fins tool awaiting and wait adapter lightweight handle
- Gate: review fix
- Implementer: AgentCodex
- Date: 2026-06-16

## Review Inputs

- `docs/reviews/wu-cli-fins-obs-01-slice-d-review-mimo-20260616.md`
- `docs/reviews/wu-cli-fins-obs-01-slice-d-review-ds-20260616.md`

## Adjudication

Both reviews passed with no blocking findings.

Accepted low-cost follow-up:

- MiMo observation: `_FinsObservedOperationRecord` is intentionally mutable and all field reads / writes must stay under `_observation_lock`. The implementation already follows this rule, but the class docstring did not state the invariant.

Deferred observations:

- `asyncio.run()` in the sync wait adapter is acceptable for the current Host sync poller boundary. If Host poller becomes async, that future work unit should remove the sync bridge.
- The slow-poller bounded queue backpressure risk is deferred to a future production poller / backoff owner.
- README durable wording remains assigned to Slice E.
- Duplicate forbidden-fragment lists are non-blocking; current tests cover the leakage boundary.

## Fix

- Updated `_FinsObservedOperationRecord` docstring in `dayu/fins/ingestion_runtime.py` to state that all mutable field access and updates must be protected by the owning runtime's `_observation_lock`.

## Validation

```text
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_host_assembly.py -q
152 passed, 3 warnings

source .venv/bin/activate && pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

git diff --check
clean
```
