# WU-DUR-01-02 Plan Review Controller Adjudication

## Gate

- Gate: plan review controller adjudication
- Work unit: WU-DUR-01 + WU-DUR-02
- Plan: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- Reviews:
  - `docs/reviews/wu-dur-01-02-plan-review-mimo-20260601.md`
  - `docs/reviews/wu-dur-01-02-plan-review-ds-20260601.md`

## Controller Decision Summary

Plan direction is accepted, but plan fix is required before implementation. Both reviewers agree the plan is narrow, tests-first, and aligned with the Host design target. Accepted fixes are limited to implementation-readiness clarifications; they do not change scope, add public API, add schema migration, or expand WU-DUR-02 beyond directly evidenced gaps.

## Finding Decisions

### MIMO-P1 - accepted

Decision: Accepted as a plan clarity fix.

Reason: Based on the design goal that current-version durable stores must fail closed instead of being silently repaired, the implementation plan must explicitly state that `_bootstrap_fresh_schema()` is the only path allowed to execute `HOST_DURABLE_DDL`; the `user_version == HOST_SCHEMA_VERSION` branch must execute validation only.

Required plan fix: Amend Slice 1 and Detailed Implementation Decisions to make the no-DDL current branch non-ambiguous.

### MIMO-P2 - accepted

Decision: Accepted as a plan clarity fix.

Reason: `HostDurableStore.connect()` opens secondary connections used by read/write paths. Full schema validation must be applied there too, otherwise the durable truth boundary can still be bypassed after the primary opener succeeds.

Required plan fix: Explicitly name `_open_configured_connection()` / `HostDurableStore.connect()` in Slice 1 as validation-only, no-bootstrap paths.

### MIMO-P3 and DS-P1 - accepted

Decision: Accepted as one combined plan fix.

Reason: Required index validation only closes the current-version missing-index risk if the required index set covers all existing durable index name constants. A consistency test is the lowest-cost way to prevent validation drift without escalating to full DDL text diff.

Required plan fix: Specify that `HOST_DURABLE_INDEXES` must include every existing `INDEX_*` durable index name constant, and require a test that parses `HOST_DURABLE_DDL` index names and compares the set with `HOST_DURABLE_INDEXES`.

### MIMO-P4 - accepted

Decision: Accepted as a plan clarity fix.

Reason: WAL checkpoint busy behavior is SQLite-environment-sensitive. The current phase needs observable diagnostic fields and failure handling, not a flaky assertion that `busy_pages > 0` is always produced.

Required plan fix: Mark the busy test as diagnostic-field observability and add optional unit-level coverage for a synthetic `busy_pages > 0` result only if it can be done without over-mocking SQLite correctness.

### DS non-blocking suggestion NBS-1 - accepted

Decision: Accepted as a plan clarity fix.

Reason: Double validation is not a correctness bug, but it creates an implementation ambiguity. The plan should name one validation owner path to reduce accidental duplicate work and unclear tests.

Required plan fix: Clarify whether `bootstrap_host_durable_store()` performs final validation or only bootstraps/dispatches, and where `open_host_durable_store()` performs validation.

### DS non-blocking suggestion NBS-2 - accepted

Decision: Accepted as a plan clarity fix.

Reason: Secondary connection paths must not execute bootstrap DDL. This directly supports the current-version no-repair design target.

Required plan fix: State that `_open_configured_connection()` never calls bootstrap and only runs PRAGMA setup plus full schema validation.

### DS non-blocking suggestion NBS-3 - accepted

Decision: Accepted as a test instruction clarification.

Reason: The read-stale proof must use two independent SQLite connections to the same DB. Naming `HostDurableStore` primary connection plus `store.connect()` prevents a false test that accidentally uses separate DBs or the same connection.

Required plan fix: Amend Slice 2 read-stale test instructions accordingly.

## Deferred / Rejected Items

- DDL text diff validation remains deferred to WU-LAYER-01. Current WU-DUR-01 scope is required table/index existence, not full schema invariant diff.
- WAL checkpoint production busy coverage beyond deterministic diagnostic observability remains deferred to future hardening if needed.
- Rollback failure remains out of scope for this work unit.
- Memory snapshot row CAS remains out of scope; memory CAS means memory snapshot plus projection checkpoint CAS only.

## Next Gate

Plan fix required, then plan re-review by MiMo and DS focused only on accepted fixes above.

## Stop Status

adjudication-complete
