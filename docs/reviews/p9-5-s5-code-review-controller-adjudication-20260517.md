# P9.5 S5 Code Review Controller Adjudication

## Gate

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR.
- Slice: S5 Schema CHECK Hardening.
- Implementation artifact: `docs/reviews/p9-5-s5-schema-check-hardening-implementation-20260517.md`.
- Review artifacts:
  - `docs/reviews/p9-5-s5-code-review-mimo-20260517.md`
  - `docs/reviews/p9-5-s5-code-review-ds-20260517.md`

## Controller Decision

S5 is accepted.

The two DDL changes are justified by direct evidence from current Python validation and durable primitives. They make SQLite reject states that current production APIs already reject, without encoding P10+ semantics, adding states, changing public contracts, or creating migration/compatibility logic. The `HOST_SCHEMA_VERSION` bump from 7 to 8 is required because fresh schema DDL changed.

## Findings Adjudication

### MiMo F1 — old CHECK allowed illegal states closed by new CHECK

- Severity: Info.
- Decision: Accepted as intended S5 outcome; no fix required.
- Rationale: This is the core S5 hardening. The new CHECK constraints align SQLite with `EventLogStore._validate_payload_reference` and `IdempotencyStore._validate_result_ref`.

### MiMo F2 — Python validation remains stricter than SQLite CHECK

- Severity: Info.
- Decision: Accepted as non-blocking; no fix required.
- Rationale: SQLite now owns structural invariants that are stable schema facts: paired refs and positive sequence. Python validation remains the correct owner for non-empty text and digest format checks, so this is not a schema gap.

### DS Review

- Blocking findings: 0.
- Non-blocking findings: 0.
- Decision: No required fix.

## Validation

Controller reran:

- `source .venv/bin/activate && pytest tests/host`
  - Result: 502 passed.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: clean.

## Accepted State

- Blocking findings: 0.
- Required fixes: 0.
- README decision: `dayu/host/README.md` and `tests/README.md` remain accurate; they do not pin schema version or describe the old weaker ref/digest pairing.
- S5 may proceed to accepted slice commit.
