# Host Phase 7 P7-S1 Fix Artifact

- fix scope: accepted S1-F1 / S1-F2 only
- adjudication: `docs/reviews/host-phase7-code-review-s1-controller-adjudication-20260516.md`
- status: completed
- date: 2026-05-16

## Fixed Findings

### S1-F1 - wait length constants duplicated

Fixed in `dayu/host/durable/schema.py`.

`schema.py` now imports wait length constants from `dayu.host.api` and no longer defines local duplicates. This keeps public dataclass validation constants and SQLite DDL `CHECK` limits on the same source.

### S1-F2 - orphan snapshot_digest DDL gap

Fixed in `dayu/host/durable/schema.py` and `tests/host/test_wait_record_state.py`.

`host_wait_records` snapshot group DDL now accepts only these shapes:

- no snapshot: `snapshot_ref IS NULL`, `snapshot_captured_at IS NULL`, and `snapshot_digest IS NULL`;
- snapshot present: `snapshot_ref IS NOT NULL` and `snapshot_captured_at IS NOT NULL`; `snapshot_digest` may be `NULL`.

Added a direct SQL DDL test proving orphan `snapshot_digest` is rejected when `snapshot_ref` and `snapshot_captured_at` are both `NULL`.

## Explicit Non-Fixes

- Did not add adapter key regex DDL checks; S1-F3 was rejected.
- Did not add a CAS_LOST race test; S1-F4 was deferred to P7-S4.
- Did not modify public API, state helpers, ToolRuntime, plan, design/control docs, commits, branches, PRs, or external state.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_wait_record_state.py -q`
  - result: `15 passed in 0.21s`
- `source .venv/bin/activate && python -m pyright dayu/host/durable/schema.py tests/host/test_durable_schema.py tests/host/test_wait_record_state.py`
  - result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - result: passed

## Residual Risk

No new residual risk introduced by this fix pass. Broader Phase 7 behavior remains owned by later slices.
