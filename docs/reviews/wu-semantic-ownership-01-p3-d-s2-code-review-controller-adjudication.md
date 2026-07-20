# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S2 Code Review Controller Adjudication

## Inputs

- MiMo review: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-code-review-mimo.md`
- DS review: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-code-review-ds.md`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p3-d-s2-controller-validation.md`

## Findings

### P3-D-S2-CR-F01 - accepted - Read API must distinguish fatal protocol error activity from non-fatal provider diagnostic

- Merged from: MiMo `S2-CR-01` and DS finding 1.
- Correct owner boundary: Host Read API projection owns Service/UI-facing activity semantics. It must not force consumers to infer fatal vs non-fatal provider semantics from a shared `HostActivityKind.PROVIDER_DIAGNOSTIC` plus status convention.
- Decision: accepted.
- Fix direction:
  - Add an explicit `HostActivityKind.PROVIDER_PROTOCOL_ERROR` for fatal `PROVIDER_PROTOCOL_ERROR` activity.
  - Keep non-fatal `PROVIDER_DIAGNOSTIC` on `HostActivityKind.PROVIDER_DIAGNOSTIC`.
  - Use existing `HostActivityStatus.INFO` for non-fatal provider diagnostic instead of `COMPLETED`.
  - Update Host activity tests and public contract exports/docs if needed.
- Validation required: focused Host activity projection tests, S2 required Host test group, pyright, `git diff --check`.

### P3-D-S2-CR-F02 - accepted - context overflow `detection=None` path needs explicit regression coverage

- Merged from: MiMo `S2-CR-02`.
- Correct owner boundary: Agent owns Runner HTTP error to Engine event projection. A typed `CONTEXT_LENGTH_EXCEEDED` without detection provenance should produce only `context_compaction_requested`, not a provider diagnostic.
- Decision: accepted.
- Fix direction:
  - Add an Agent test where `RunnerHTTPErrorData(error_code=CONTEXT_LENGTH_EXCEEDED, context_overflow_detection=None)` yields `CONTEXT_COMPACTION_REQUESTED` and no `PROVIDER_DIAGNOSTIC`.
- Validation required: focused Agent phase2 tests, S2 required Engine test group, pyright, `git diff --check`.

### P3-D-S2-CR-F03 - rejected-with-reason - Tool Trace `provider_error_ref` event-type branch is not a current defect

- Source: DS finding 2.
- Decision: rejected-with-reason.
- Reason: the reviewed code intentionally distinguishes the two currently supported events in `_extract_diagnostic_trace`: fatal `PROVIDER_PROTOCOL_ERROR` keeps `provider_error_ref`; non-fatal `PROVIDER_DIAGNOSTIC` clears it. Generalizing future `EventClass.DIAGNOSTIC` events to the non-fatal behavior would be a new contract decision, not a current S2 root-cause defect. The finding has no current triggering input that produces incorrect state or projection.
- Destination: if a future diagnostic event type is added, its Tool Trace provider-error-ref semantics must be reviewed with that new event's owner boundary.

## Residual Risk

- S3 typed Engine error-code contract remains out of S2 scope.
- Broader unrelated Host dispatch / resolve_wait / process-backed runtime failures remain out of S2 scope.
