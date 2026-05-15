# Host Phase 6 P6-S2 Code Review Controller Adjudication

- **gate**: Phase 6 P6-S2 code review adjudication
- **design source**: `docs/host/design.md`
- **control doc**: `docs/host/implementation-control.md`
- **approved plan**: `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md`
- **implementation artifact**: `docs/reviews/host-phase6-implementation-s2-accept-barrier-20260515.md`
- **review artifacts**:
  - `docs/reviews/host-phase6-code-review-s2-mimo-20260515.md`
  - `docs/reviews/host-phase6-code-review-s2-ds-20260515.md`
- **date**: 2026-05-15

## Verdict

**ACCEPTED WITH NON-BLOCKING TEST HARDENING APPLIED**

P6-S2 is accepted for checkpoint. The implementation establishes the Host accept barrier typed contract, default durable accept port, canonical tool EventLog facts, accept idempotency behavior, and EngineEvent preview boundary without adding durable tables or changing Engine / Remote contracts.

## Review Summary

### MiMo

- Verdict: PASS
- Findings: 0
- Validation: 34 targeted tests passed, pyright 0 errors, `git diff --check` clean

### DS

- Verdict: PASS
- Blocking findings: 0
- Non-blocking findings: 4
  - precondition rejection message/reason is diagnostically coarse
  - `FAILED` / `CANCELLED` / `GOVERNED_ERROR` accept path lacked direct tests
  - `ToolAcceptRetryPolicy` / `ToolFactAcceptTimedOut` guard tests were missing
  - `_tool_accept_event_plan` directly strips the `sha256:` prefix

## Adjudication

### DS Finding 1

**Deferred.**

The current behavior rejects inactive or invalid accept contexts and does not append tool facts, which satisfies P6-S2 correctness. The finding is about diagnostic precision for future ToolExecutor wrapper decisions. P6-S3 should revisit reject reason / message granularity when the wrapper consumes `ToolFactRejectedAck`.

### DS Finding 2

**Accepted and fixed in P6-S2.**

The accept path should have direct regression coverage for non-completed fact kinds. Added tests for `FAILED`, `CANCELLED`, `GOVERNED_ERROR`, and the guard that non-reuse facts must not carry prior reuse refs.

### DS Finding 3

**Accepted and fixed in P6-S2.**

Added construction guard tests for `ToolAcceptRetryPolicy` and `ToolFactAcceptTimedOut`.

### DS Finding 4

**Rejected as required P6-S2 fix.**

`sha256_digest_json` is the Host durable codec helper already used as a stable internal digest source. There is no existing public strip helper, and this is currently a single local event-id derivation site. If later slices need the same conversion in multiple places, it should be extracted into `dayu.host.durable.codec`.

## Final Validation

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_event_log_store.py tests/host/test_engine_ingest_mapping.py -q`
  - Result: **37 passed**
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: **0 errors, 0 warnings, 0 informations**
- `git diff --check`
  - Result: **passed, no output**

## Residual Risks

- `DefaultHostToolFactAcceptPort` is not yet called by the real ToolExecutor wrapper; P6-S3 owns that integration.
- `ToolFactAcceptTimedOut` and `ToolAcceptRetryPolicy` have typed contract and guards, but the bounded retry loop is still P6-S3 scope.
- `SCHEMA_MISMATCH`, `CAS_CONFLICT`, and `EXPLICIT_POLICY_REJECT` are stable reject reasons without P6-S2 trigger paths; later policy / snapshot wiring must add direct tests.
- Reject reason / message granularity for inactive execution context remains a P6-S3 hardening item.
