# WU-DUR-01-02 Slice 1 Code Review Controller Adjudication

## Gate

- Gate: code review controller adjudication
- Work unit: WU-DUR-01 + WU-DUR-02
- Slice: Slice 1 - Bootstrap Atomicity And Current-schema Validation
- Implementation artifact: `docs/reviews/wu-dur-01-02-implementation-slice1-codex-20260601.md`
- Reviews:
  - `docs/reviews/wu-dur-01-02-code-review-slice1-mimo-20260601.md`
  - `docs/reviews/wu-dur-01-02-code-review-slice1-ds-20260601.md`

## Controller Decision Summary

Slice 1 implementation direction is accepted. MiMo found no substantive issue. DS found two low-severity test maintainability gaps. Both are accepted because they directly protect the new schema metadata validation boundary and can be fixed without changing production scope, public API, schema version, migration behavior, or later-slice responsibilities.

## Finding Decisions

### DS-C1 - accepted

Decision: Accepted.

Reason: The index consistency test is part of the accepted plan for preventing `HOST_DURABLE_INDEXES` drift. Making `IF NOT EXISTS` optional in the parser improves the test's defensive coverage while preserving the same current assertions.

Required fix: Relax the CREATE INDEX regex so it matches both `CREATE INDEX name` and `CREATE INDEX IF NOT EXISTS name`, including UNIQUE variants.

### DS-C2 - accepted

Decision: Accepted.

Reason: The same first-principles risk exists for required tables: validation depends on `HOST_DURABLE_TABLES`, so a DDL/table-list drift would weaken current-version fail-closed behavior. A table DDL consistency test is a narrow test-only guard, not a schema invariant platform expansion.

Required fix: Add a test that parses `HOST_DURABLE_DDL` `CREATE TABLE` names and asserts the set equals `HOST_DURABLE_TABLES`.

## Non-blocking Suggestions

- Opener-wrapped DDL failure coverage is not accepted for this slice. Existing tests already prove rollback and opener-level current-schema fail-closed behavior; opener wrapping is not part of the current risk signal.
- A `_bootstrap_fresh_schema` docstring precondition note about already configured PRAGMAs is allowed if the fix agent touches the same helper, but it is not required for gate pass.

## Next Gate

Fix required for DS-C1 and DS-C2, then focused re-review by MiMo and DS.

## Stop Status

adjudication-complete
