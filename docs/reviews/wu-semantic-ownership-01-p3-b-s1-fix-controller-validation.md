# WU-SEMANTIC-OWNERSHIP-01 P3-B S1 fix controller validation

## Scope

- Gate: S1 code-review fix controller validation.
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-s1-fix-codex.md`.
- Accepted findings: `P3-B-S1-CR-F01`, `P3-B-S1-CR-F02`.

## Inspection

- Outbox JSON public-read parsing now rejects empty/blank `content` itself with `HostDurableError`; `HostFinalAnswerView` retains its independent public-contract validation.
- The raw durable row test reaches the public API and verifies `HostApiError(INTERNAL_ERROR)` with the targeted durable cause.
- Non-text canonical `finish_reason` is covered at both Outbox projection and succeeded HostEvent read boundaries; neither path converts or ignores it.
- No owner, schema, metadata-source, memory, compact, run-input, or LLM-facing behavior changed.

## Validation

- P3-B focused matrix: `75 passed`.
- Pyright: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: clean.
- Agent propagation regression: `305 passed`.

## Decision

- `P3-B-S1-CR-F01`: fixed, pending independent re-review.
- `P3-B-S1-CR-F02`: fixed, pending independent re-review.
- Blocking open question: none.
- Next gate: parallel S1 code re-review by AgentMiMo and AgentDS.
