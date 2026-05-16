# P7-S2 Fix - Tool Awaiting Accept Review Findings

## Scope

- Phase: Phase 7 P7-S2 `ToolRuntime Awaiting Accept Path`
- Inputs:
  - `docs/reviews/host-phase7-code-review-s2-mimo-20260516.md`
  - `docs/reviews/host-phase7-code-review-s2-ds-20260516.md`

## Fixes

- Added ToolRuntime tests for awaiting accept rejected ack and timeout mapping.
- Added ToolRuntime test for `POLL` binding without external job ref.
- Added ToolRuntime test that an accepted awaiting result stops later batch calls without invoking business callables.
- Added durable awaiting accept stale execution reject coverage.
- Documented why awaiting accepted does not update run-local duplicate accepted registry: awaiting is an intermediate wait state; resolved tool result facts are owned by the later `resolve_wait` path.
- Kept `_normalize_runtime_outcome` as a deliberate ordinary-outcome extension point and documented why awaiting is no longer handled there.
- Added `_AwaitingAcceptStateConflictError` so post-precondition state CAS conflict is converted to structured `ToolAwaitingRejectedAck(CAS_CONFLICT)` instead of leaking a generic durable exception.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_wait_awaiting_accept.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_accept_barrier.py -q`
  - 24 passed
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 0 errors
