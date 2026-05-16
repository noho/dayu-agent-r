# P7-S2 Code Re-Review Controller Adjudication

## Scope

- Phase: Phase 7 `Tool Awaiting / resolve_wait / Wait Adapter`
- Slice: P7-S2 `ToolRuntime Awaiting Accept Path`
- Gate: code re-review after fix pass
- Branch: `feat/host-phase7-tool-awaiting-resolve-wait`
- Inputs:
  - `docs/reviews/host-phase7-implementation-s2-tool-awaiting-accept-20260516.md`
  - `docs/reviews/host-phase7-code-review-s2-mimo-20260516.md`
  - `docs/reviews/host-phase7-code-review-s2-ds-20260516.md`
  - `docs/reviews/host-phase7-fix-s2-tool-awaiting-accept-20260516.md`
  - `docs/reviews/host-phase7-code-re-review-s2-mimo-20260516.md`
  - `docs/reviews/host-phase7-code-re-review-s2-ds-20260516.md`

## Verdict

PASS.

P7-S2 accepted code review findings are closed. No blocking finding remains.

## Finding Disposition

| Finding | Source | Prior disposition | Re-review status | Controller disposition |
| --- | --- | --- | --- | --- |
| Awaiting rejected / timeout ToolRuntime tests missing | MiMo S2-F1 | accepted | fixed | closed |
| POLL binding missing external job ref test missing | MiMo S2-F2 | accepted | fixed | closed |
| `_normalize_runtime_outcome` no-op readability | MiMo S2-F3 | accepted-low | fixed | closed |
| Awaiting accepted duplicate registry asymmetry unclear | MiMo S2-F4 | accepted-low | fixed | closed |
| CAS conflict leaked generic durable error | DS S2-F1 | accepted-low | fixed | closed |
| Awaiting precondition reject test gap | DS S2-F2 | accepted-low | improved | closed with residual hardening |

## Evidence

- `tests/host/test_toolruntime_executor.py` now covers awaiting accepted ack, missing adapter binding, rejected ack, timeout, missing external job ref, and batch stop behavior.
- `tests/host/test_wait_awaiting_accept.py` now covers durable awaiting accept success, idempotency replay, idempotency conflict, and stale execution rejection.
- `dayu/host/waiting.py` uses `_AwaitingAcceptStateConflictError` to convert post-precondition state CAS conflict into structured `ToolAwaitingRejectedAck(CAS_CONFLICT)`.
- `dayu/host/tool_runtime.py` documents why awaiting accepted does not update duplicate accepted registry and why `_normalize_runtime_outcome` is retained as an ordinary-outcome extension point.
- MiMo re-review verdict: PASS.
- DS re-review verdict: PASS.

## Residual Risk

- Additional `INVALID_ATTEMPT` sub-branch tests can be added if awaiting precondition logic is refactored. Current S2 coverage includes stale execution and the primary success / replay / conflict paths.
- `resolve_wait`, WAITING cancel, poller / callback and EngineEvent confirmation behavior remain explicitly out of P7-S2 scope and are owned by later slices.

## Decision

P7-S2 code gate is accepted after final local validation.
