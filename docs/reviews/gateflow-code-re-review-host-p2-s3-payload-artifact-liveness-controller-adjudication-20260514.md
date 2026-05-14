# Gateflow Controller Adjudication: Host P2 S3 Code Re-Review

## Gate

- **gate name**: code-re-review adjudication
- **work unit**: Host Phase 2 Slice 3 Payload / Artifact / Liveness
- **branch**: `feat/host-phase2-durable-store-eventlog`
- **accepted Slice 2 commit**: `50ba2d7`
- **date**: 2026-05-14

## Inputs

- Implementation artifact: `docs/reviews/gateflow-implementation-host-p2-s3-payload-artifact-liveness-20260514.md`
- MiMo code review: `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-mimo-20260514.md`
- DS code review: `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-ds-20260514.md`
- Controller code-review adjudication: `docs/reviews/gateflow-code-review-host-p2-s3-payload-artifact-liveness-controller-adjudication-20260514.md`
- Fix artifact: `docs/reviews/gateflow-fix-host-p2-s3-payload-artifact-liveness-20260514.md`
- MiMo code re-review: `docs/reviews/gateflow-code-re-review-host-p2-s3-payload-artifact-liveness-mimo-20260514.md`
- DS code re-review: `docs/reviews/gateflow-code-re-review-host-p2-s3-payload-artifact-liveness-ds-20260514.md`

## Controller Decision

**PASS.** Slice 3 code re-review is accepted.

Both re-review artifacts verify that `S3-F1`, `S3-F2`, and `S3-F3` are fixed. No new correctness, stability, maintainability, typing, import-boundary, or scope finding remains.

## Accepted Finding Status

| Finding | Status |
|---|---|
| `S3-F1` duplicated durable scalar validation helpers | Fixed by `dayu.host.durable._validation`; no public export or compatibility facade introduced. |
| `S3-F2` missing negative `artifact_size_bytes` validation test | Fixed by direct `validate_artifact_ref` test. |
| `S3-F3` bytes payload silently ignored non-None `payload_json` | Fixed by rejecting BYTES + non-None `payload_json` before encoding, with focused transaction-path test. |

## Controller Validation

| Command | Result |
|---|---|
| `source .venv/bin/activate && pytest tests/host/test_payload_store.py tests/host/test_artifact_store.py tests/host/test_host_instance_liveness.py -q` | passed: `27 passed` |
| `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py tests/host/test_event_log_multiprocess.py -q` | passed: `20 passed` |
| `source .venv/bin/activate && pytest tests/host -q` | passed: `94 passed` |
| `source .venv/bin/activate && python -m pyright dayu/host tests/host` | passed: `0 errors, 0 warnings, 0 informations` |

## Residual Risks

- Artifact orphan cleanup remains deferred to the cleanup / diagnostics work unit as already accepted in the Phase 2 plan.
- `CRASHED_SUSPECTED` remains a schema / enum foundation value for later recovery and has no Phase 2 writer.
- `_validation.py` is private by module naming and not re-exported; future durable modules must reuse it instead of reintroducing local scalar helper copies.

## Gate Outcome

The code re-review gate is closed for Phase 2 Slice 3. The next controller action is to update `docs/host/implementation-control.md`, create the accepted Slice 3 commit, then start aggregate `$deepreview --base main` for the completed Phase 2 work unit.
