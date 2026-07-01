# WU-WAIT-02 Slice 1 Implementation - Codex

## Slice

- Work unit: `WU-WAIT-02` / GitHub Issue #90
- Slice: Slice 1 - Durable Poll Claim And Backoff Primitive
- Status: implementation complete; no code review / fix / commit / push / PR performed.

## Changed Files

- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `dayu/host/wait_adapter.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_wait_record_state.py`
- `tests/host/test_wait_adapter_polling.py`
- `docs/reviews/wu-wait-02-slice1-implementation-codex.md`

`tests/host/test_state_schema.py` was read as required and left unchanged because it does not construct or decode wait records.

## Behavior Implemented

- Incremented `HOST_SCHEMA_VERSION` to 17 for fresh schema.
- Added wait-row-owned poll claim, retry/backoff diagnostic, next-observe, and durable abandon marker columns to `host_wait_records`.
- Added schema checks for all-or-none claim fields, non-negative backoff, bounded claim / owner ids, allowed poll outcome values, and `poll_abandoned_at` only on cancelled waits.
- Updated active poll index shape to include `poll_next_observe_at`, `poll_claim_expires_at`, and stable ordering fields.
- Extended `WaitRecordRow` decoding, insert validation, typed outcome codec, and defaults for new poll fields.
- Added durable helpers:
  - `claim_wait_record_for_poll(...)`
  - `release_wait_record_poll_claim(...)`
  - `mark_wait_record_poll_abandoned(...)`
- Claim acquisition uses a write transaction and a single `UPDATE ... WHERE` that repeats eligibility and claim-expiry predicates before assigning claim fields. A prior candidate read never authorizes adapter work.
- Release and abandon helpers require matching `poll_claim_id`; stale claim release cannot clear a newer claim.
- Resolved / failed / lost wait terminal mutation clears poll claim fields and resets next-observe/backoff.
- `WaitPoller.poll_once()` is now claim-aware:
  - claims before adapter calls;
  - calls adapters outside Host transaction;
  - releases with durable backoff for not-ready, adapter error, missing adapter, resolve error, and abandon failure;
  - records missing adapter as retryable metadata without `resolve_wait`;
  - marks cancelled abandon success durably with `poll_abandoned_at`;
  - treats abandon CAS conflict as skipped/conflict and leaves cancelled wait retryable;
  - keeps ready/lost results on the existing `resolve_wait` path;
  - keeps `_poll_idempotency_key(...)` unchanged.

## Validation

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py tests/host/test_wait_adapter_polling.py -q
```

Result:

```text
102 passed in 1.01s
```

Command:

```bash
source .venv/bin/activate && pyright
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Command:

```bash
git diff --check
```

Result: passed with no output.

## Docs Decision

Read `dayu/host/README.md` Agent 更新约束 and `tests/README.md`.

Decision: no README update for Slice 1. This slice changes internal Host durable poll claim/backoff primitives and focused tests only; it does not change public Host handle methods, user-facing CLI / workflow behavior, package architecture boundaries, or the documented test directory structure. The accepted plan also marked docs updates as out of scope for Slice 1.

## Residual Risks

- Shared durable backoff can reach max delay faster after repeated crash / claim-expiry / takeover cycles. Classification: accepted plan residual. Owner: WU-WAIT-02 Slice 1 behavior owner. Destination: bounded by `poll_backoff_attempt` and max-delay policy; future tuning belongs to Slice 2/runtime policy if operator controls are needed.
- `claim_wait_record_for_poll(...)` still performs a candidate id read before the atomic update. Classification: implementation note, not correctness blocker. Owner: Host durable state. Destination: the adapter path only receives a row after `UPDATE ... WHERE` succeeds, so the read is not an authorization source; reviewers should verify this invariant.
- Backoff policy constants are minimal Slice 1 defaults, not construction-time runtime policy. Classification: deferred by plan. Owner: WU-WAIT-02 Slice 2. Destination: production supervisor/runtime policy wiring.
- Missing adapter remains indefinite retry with capped backoff and durable metadata, not terminal provider-failure policy. Classification: accepted plan residual. Owner: WU-WAIT-03 or future provider lifecycle work if terminal provider-failure semantics are required.

## Stop Conditions

- Wait-row extension can express stale claim CAS safely; no stop.
- Terminal wait mutations can clear claim fields without weakening existing resolve/idempotency tests; no stop.
- A separate claim table was not necessary; no stop.
- README/design source changes were not required for correctness; no stop.
- Pyright/type constraints did not require `Any`, `object`, or untyped signatures; no stop.
