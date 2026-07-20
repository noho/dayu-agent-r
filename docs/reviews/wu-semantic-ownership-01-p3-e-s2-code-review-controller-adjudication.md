# WU-SEMANTIC-OWNERSHIP-01 P3-E S2 Code Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Slice: `S2 - Wait callback typed provider status ref and accepted status projection`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-s2-controller-validation.md`
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-e-s2-code-review-ds.md`

## Controller Decision

Both reviewers returned `PASS` with zero material findings. The implementation satisfies the core S2 production contract.

However, the controller accepts one test-closure fix from MiMo's residual risk because it maps directly to an explicit S2 plan acceptance criterion: missing EventLog payload and missing result payload must both be tested as `LOST` with their expected diagnostics.

## Accepted Fix

### P3-E-S2-CR-F01 - Accepted - Directly test `event_payload_unavailable -> LOST`

- Source: AgentMiMo residual risk; controller plan-conformance audit.
- Severity: Low.
- Owner boundary: Host accepted-result projection owns unavailable payload diagnostics and `LOST` mapping.
- Direct evidence:
  - `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md` S2 test plan requires missing event payload and missing result payload tests.
  - Current tests cover `result_payload_unavailable`.
  - Current tests do not directly assert `event_payload_unavailable`.
- Required fix:
  - Add a focused projection test where the `TOOL_RESULT_ACCEPTED` EventLog payload itself is unavailable.
  - Assert `projection.status is AcceptedToolResultStatus.LOST`.
  - Assert `event_payload_unavailable` is present in `projection.diagnostic_reasons`.
  - Keep existing `result_payload_unavailable` coverage unchanged.
- Acceptance signal:
  - `pytest tests/host/test_accepted_result_projection.py -q` passes.
  - The broader S2 validation matrix remains green.

## Accepted PASS Items

The following S2 contract points are accepted as correct and do not require fixes:

- Service callback endpoint rejects bare-string `provider_status_ref`.
- No `WaitAdapterKey("callback")` fake resolver remains in the Service callback mapper.
- `_status_from_raw_outcome` and raw outcome status reconstruction are removed.
- Typed status unavailable maps to `UNKNOWN + accepted_status_unavailable`.
- Result payload unavailable maps to `LOST + result_payload_unavailable`.
- Consumers do not reconstruct accepted status from raw outcome.
- `tests/README.md` update is within its stated scope.

## Next Gate

Run an S2 fix gate for `P3-E-S2-CR-F01`, followed by controller validation and independent re-review.

