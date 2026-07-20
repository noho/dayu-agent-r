# WU-SEMANTIC-OWNERSHIP-01 P3-B aggregate fix controller validation

## Scope

- Gate: aggregate fix controller validation.
- Finding: `P3-B-AGG-F01`.
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-b-aggregate-fix-codex.md`.

## Inspection

The Outbox JSON read parser now rejects empty and whitespace-only `finish_reason` with an Outbox-specific `HostDurableError`. Public dataclass validation remains intact, and no value conversion or compatibility branch was added. The two parameterized tests corrupt a real durable Outbox row and pass through the public read API.

## Validation

- Focused P3-B matrix: `77 passed`.
- Pyright: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: clean.
- Agent propagation regression: `305 passed`.

## Decision

- `P3-B-AGG-F01`: fixed, pending independent aggregate re-review.
- Blocking open question: none.
- Next gate: parallel aggregate re-review by AgentMiMo and AgentDS.
