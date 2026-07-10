# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S2 Re-Review Controller Adjudication

## Inputs

- MiMo re-review: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-rereview-mimo.md`
- DS re-review: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-rereview-ds.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-fix-codex.md`
- Controller fix validation: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-fix-controller-validation.md`

## Decision

- `P3-D-S2-CR-F01`: fixed.
- `P3-D-S2-CR-F02`: fixed.
- `P3-D-S2-CR-F03`: remains rejected-with-reason; no fix required.
- New material findings: none.
- Gate decision: S2 re-review pass; ready for accepted slice commit.

## Evidence

### P3-D-S2-CR-F01

- Fatal provider protocol error activity now uses `HostActivityKind.PROVIDER_PROTOCOL_ERROR` with `HostActivityStatus.FAILED`.
- Non-fatal provider diagnostic activity remains `HostActivityKind.PROVIDER_DIAGNOSTIC` and now uses `HostActivityStatus.INFO`.
- Service entrypoint maps `HostActivityKind.PROVIDER_PROTOCOL_ERROR` to `EntrypointActivityKind.PROVIDER_PROTOCOL_ERROR`.
- Tests assert Host fatal kind/status, Host non-fatal kind/status, and Service fatal kind/status.

### P3-D-S2-CR-F02

- `tests/engine/test_agent_phase2.py` includes `test_context_overflow_without_detection_emits_only_compaction_request`.
- The test constructs `RunnerHTTPErrorData(error_code=CONTEXT_LENGTH_EXCEEDED, context_overflow_detection=None)`.
- It asserts the stream includes `CONTEXT_COMPACTION_REQUESTED` and excludes `PROVIDER_DIAGNOSTIC`.

## Residual Risk

- S3 typed Engine error-code contract remains out of S2 scope.
- DS noted that Service has direct fatal provider protocol error activity regression coverage and Host has direct non-fatal provider diagnostic activity coverage, while Service non-fatal diagnostic end-to-end coverage is indirect through the explicit mapping branch and generic activity callback tests. Controller records this as non-blocking because no current semantic mismatch, weakened assertion, or failing projection path is evidenced.
