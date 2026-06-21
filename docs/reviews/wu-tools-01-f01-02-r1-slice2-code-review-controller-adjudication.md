# WU-TOOLS-01-F01-02-R1 Slice 2 Code Review Controller Adjudication

## Scope

- work unit: `WU-TOOLS-01-F01-02-R1`
- slice: Slice 2 `Fins prepare / activate two-phase runtime and tools`
- gate: code review
- base checkpoint: `2634f361`
- accepted Slice 1 commit: `e10f2e99`
- implementation artifact: `docs/reviews/wu-tools-01-f01-02-r1-slice2-implementation-codex.md`
- review artifacts:
  - `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r1-slice2-code-review-ds.md`

## Review Summary

- AgentMiMo conclusion: `pass`; no substantive findings.
- AgentDS conclusion: `pass`; two low-severity findings, no blockers.
- Controller conclusion: Slice 2 implementation is correct, but should take one minimal code-review fix pass before accepted slice commit.

## Adjudication

### S2-CR-F01 accepted: cancellation result should apply the same safe-message boundary

Current cancellation message is hardcoded and safe, but `_observation_cancelled_result(...)` does not apply `_safe_observation_message(...)` while failure paths do. Because cancellation result material can be observed through the existing wait adapter, keeping the same safe-message boundary is the better production default.

Required fix:

- Ensure `_observation_cancelled_result(...)` or its sole call path applies `_safe_observation_message(...)`.
- Keep the current user-facing meaning stable; do not introduce new public error text, schema, or compatibility behavior.
- Add or update a focused assertion only if needed to prove the boundary.

### S2-CR-F02 accepted: activation registry builder validation-only intent should be explicit

`build_fins_wait_activation_registry(...)` calls `_deterministic_tool_names(tool_names)` for validation but discards the sorted return value because activation uses one adapter key for all Fins tools. The behavior is correct, but the code intent should be explicit before Slice 3 assembly work consumes this builder.

Required fix:

- Make the validation-only intent clear with a small helper rename or concise code comment.
- Do not change registry behavior and do not introduce per-tool activation registrations.

## Deferred / Residual Risks

- Slice 3 must verify production assembly uses consistent Fins runtime instances for awaiting tool runtime, poll adapter, and activation adapter.
- Process-local prepared observation TTL remains intentionally out of scope for this WU slice; Host governance and later WAIT hardening own production expiry behavior.
- Multi-thread double activation and running-producer re-activation are low-risk regression gaps; the lock plus `submitted` flag is directly covered by current sequential and cancel/activate tests.

## Next Gate

Enter Slice 2 code-review fix gate for AgentCodex. The fix must stay limited to S2-CR-F01 and S2-CR-F02, then rerun Fins focused tests and pyright.
