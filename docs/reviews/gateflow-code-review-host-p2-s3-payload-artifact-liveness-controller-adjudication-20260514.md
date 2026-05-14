# Gateflow Controller Adjudication: Host P2 S3 Code Review

## Gate

- **gate name**: code-review adjudication
- **work unit**: Host Phase 2 Slice 3 Payload / Artifact / Liveness
- **branch**: `feat/host-phase2-durable-store-eventlog`
- **accepted Slice 2 commit**: `50ba2d7`
- **date**: 2026-05-14

## Inputs

- Implementation artifact: `docs/reviews/gateflow-implementation-host-p2-s3-payload-artifact-liveness-20260514.md`
- MiMo review: `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-mimo-20260514.md`
- DS review: `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-ds-20260514.md`
- Controller validation:
  - Slice 3 tests: `25 passed`
  - durable schema / transaction tests: `15 passed`
  - EventLog / idempotency / multiprocess tests: `20 passed`
  - Host tests: `92 passed`
  - runtime boundary regressions: `29 passed`
  - `python -m pyright dayu/host tests/host`: `0 errors`
  - `python -m pyright dayu/ tests/ utils/`: `0 errors`

## Reviewer Conclusions

- MiMo: `PASS` with 1 low-severity maintainability finding.
- DS: `PASS` with 2 low-severity findings.

No reviewer reported a blocking correctness or stability finding.

## Controller-Accepted Findings

### `S3-F1` - accepted - low - durable scalar validation helpers are duplicated

MiMo and DS both found duplicated scalar validation helpers across durable modules. The finding is accepted because the project hard constraint says repeated logic must be extracted, and Slice 3 expanded an already visible duplication pattern.

Controller scope refinement: fix the root duplication across all current durable modules that define the same helper family, including `event_log.py`, `idempotency.py`, `payload.py`, and `liveness.py`. A private durable helper module is acceptable because it removes real duplication and stays inside `dayu.host.durable`; it must not become a public re-export or compatibility facade.

### `S3-F2` - accepted - low - `validate_artifact_ref` negative size branch lacks a direct test

DS found that `artifact_size_bytes < 0` is defensive validation but currently untested. The finding is accepted because the fix is a single direct test and improves coverage of a public internal validation helper.

### `S3-F3` - accepted - medium - bytes payload silently ignores non-None `payload_json`

Controller found an additional input-contract asymmetry in `SQLitePayloadWriteRequest` validation. For `CANONICAL_JSON`, the implementation rejects extra `payload_bytes`; for `BYTES`, it requires `payload_bytes` but does not reject an explicit non-None `payload_json`, which is then silently ignored by `_encode_sqlite_payload`.

This is a real contract bug: callers can provide an explicit field and lose it without error. Fix by rejecting non-None `payload_json` when `payload_format is SQLitePayloadFormat.BYTES`, with a focused test.

## Not Accepted / Deferred Observations

- Artifact directory fsync crash window is filesystem semantics and already mitigated with best-practice fsync; no code fix requested.
- `CRASHED_SUSPECTED` is schema / enum foundation for later recovery and intentionally has no writer in Phase 2; no current fix requested.
- Artifact orphan cleanup remains deferred to the cleanup / diagnostics work unit per approved plan.

## Required Fix Scope

Allowed files for the fix:

- `dayu/host/durable/_validation.py` or an equivalent private durable helper module.
- `dayu/host/durable/event_log.py`
- `dayu/host/durable/idempotency.py`
- `dayu/host/durable/payload.py`
- `dayu/host/durable/liveness.py`
- `tests/host/test_payload_store.py`
- `tests/host/test_artifact_store.py`
- `docs/reviews/gateflow-fix-host-p2-s3-payload-artifact-liveness-20260514.md`

README update is not required unless the fix changes documented behavior beyond internal validation detail.

## Required Validation

- `source .venv/bin/activate && pytest tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_host_instance_liveness.py -q`
- `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py tests/host/test_event_log_multiprocess.py -q`
- `source .venv/bin/activate && pytest tests/host -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`

## Gate Outcome

The code review gate does not advance to accepted slice commit yet. Proceed to fix gate for `S3-F1` through `S3-F3`, then run code re-review.
