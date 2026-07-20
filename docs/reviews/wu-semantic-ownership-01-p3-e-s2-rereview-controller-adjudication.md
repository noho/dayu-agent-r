# WU-SEMANTIC-OWNERSHIP-01 P3-E S2 Re-review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Slice: `S2 - Wait callback typed provider status ref and accepted status projection`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-fix-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-fix-controller-validation.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s2-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s2-rereview-ds.md`

## Controller Decision

Both independent re-reviews return `PASS`, with zero new material findings and zero blocking questions.

`P3-E-S2-CR-F01` is closed. P3-E S2 is accepted as complete.

## Closure Evidence

- `test_projection_missing_event_payload_maps_lost_with_diagnostic` directly covers `event_payload_unavailable -> LOST`.
- The test uses a valid payload descriptor with non-object JSON, so the failure occurs at the projection payload read/validation boundary rather than append-time foreign key validation.
- The test asserts both `AcceptedToolResultStatus.LOST` and the `event_payload_unavailable` diagnostic.
- Existing `result_payload_unavailable` coverage remains intact.

## Accepted S2 Status

S2 now satisfies all accepted plan requirements:

- Service callback endpoint rejects bare-string `provider_status_ref`.
- No fake `WaitAdapterKey("callback")` resolver remains.
- Accepted result projection does not reconstruct status from raw outcome.
- Payload unavailable maps to `LOST`.
- Typed status unavailable maps to `UNKNOWN + accepted_status_unavailable`.
- Read model, run input / evidence material, memory, and compact material do not reconstruct status from raw outcome.
- Missing result payload and missing EventLog payload are both directly covered.

## Residual Risk

- `UNKNOWN` currently uses the existing Read API severity policy. Any product-level distinction between unknown and failed/error remains a future display/projection policy decision and must not restore raw outcome fallback.
- S3 remains unimplemented and must continue under P3-E.

## Next Gate

Proceed to `WU-SEMANTIC-OWNERSHIP-01 P3-E S2 accepted implementation commit`, then `P3-E S3`.

