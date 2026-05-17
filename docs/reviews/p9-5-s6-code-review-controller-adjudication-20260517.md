# P9.5 S6 Code Review Controller Adjudication

## Gate

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR.
- Slice: S6 Read API Enum Mapping And Minimal Read Model Reset Contract.
- Implementation artifact: `docs/reviews/p9-5-s6-read-api-enum-reset-implementation-20260517.md`.
- Review artifact: `docs/reviews/p9-5-s6-code-review-mimo-20260517.md`.
- DS review status: unavailable. AgentDS was assigned S6 review, compacted into old S2 context, was interrupted, then received a narrowed S6-only prompt but still did not produce `docs/reviews/p9-5-s6-code-review-ds-20260517.md` within the allowed wait. Controller stops waiting to avoid blocking the phase indefinitely.

## Controller Decision

S6 is accepted.

The motivation is valid. Public read facades must not leak unknown durable enum values, `ValueError`, or projection-local state. The implementation adds private fail-closed mapping at the durable row to public view boundary, while preserving the design truth hierarchy: `get_run` and `get_session` still read durable Run / Session truth, and `stream_run_events` still reads EventLog truth.

## Findings Adjudication

### MiMo F1 — `isinstance` check plus enum construction is double defense

- Severity: Info.
- Decision: Accepted as intentional boundary hardening; no fix required.
- Rationale: Normal row codecs already deserialize to enum members. The explicit check protects direct dataclass construction, monkeypatched readers, and future codec drift before values reach public snapshots or event views.

### MiMo F2 — `_TIMELINE_ITEM_KINDS` must stay in sync with the projection consumer

- Severity: Info.
- Decision: Accepted as residual maintenance constraint; no fix required.
- Rationale: The set is the current closed minimal read model kind contract. If `MinimalReadModelProjectionConsumer` adds a kind without updating durable validation, writer tests fail closed instead of silently inserting an unsupported row. This is preferable to leaving the write path open.

### MiMo F3 — `_TERMINAL_RUN_STATUSES` must stay in sync with terminal Run statuses

- Severity: Info.
- Decision: Accepted as residual maintenance constraint; no fix required.
- Rationale: The set references `RunStatus` enum members rather than raw strings and is covered by terminal mapping tests. It intentionally rejects non-terminal statuses in `host_run_results`.

## Validation

Controller reran:

- `source .venv/bin/activate && pytest tests/host`
  - Result: 517 passed.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: clean.

## Accepted State

- Blocking findings: 0.
- Required fixes: 0.
- README decision: `dayu/host/README.md` was updated narrowly to reflect the current fixed single-consumer minimal read model ownership and reset/replay repair contract. `tests/README.md` remains accurate.
- S6 may proceed to accepted slice commit.
