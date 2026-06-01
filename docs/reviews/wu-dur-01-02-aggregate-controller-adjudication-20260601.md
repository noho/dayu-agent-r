# WU-DUR-01 + WU-DUR-02 Aggregate Controller Adjudication

- **Gate**: aggregate deepreview adjudication
- **Controller**: AgentController
- **Date**: 2026-06-01
- **Design source**: `docs/host/design.md`
- **Control source**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Reviewer artifacts**:
  - `docs/reviews/wu-dur-01-02-aggregate-deepreview-mimo-20260601.md`
  - `docs/reviews/wu-dur-01-02-aggregate-deepreview-ds-20260601.md`

## Verdict

**FIX REQUIRED, doc-only.**

MiMo gives PASS with no blocking findings. DS gives PASS with findings and no correctness blockers. Controller accepts only the low-risk documentation/docstring cleanups for this gate and defers behavior-expanding or broader proof items with explicit owners.

## Accepted Fixes

### AGG-DOC-1: Host README durable bullet readability

- **Source**: DS HIGH-4, MEDIUM-3
- **Decision**: accepted for current gate
- **Required fix**: split the long `dayu/host/README.md` durable foundation bullet into readable wrapped content, and mention that secondary durable connections also run full current schema validation.
- **Reasoning**: this is a documentation-only maintainability improvement inside the README triggered by Host changes. It does not change public contracts or production behavior.

### AGG-DOC-2: Fresh bootstrap docstring precondition

- **Source**: DS MEDIUM-2
- **Decision**: accepted for current gate
- **Required fix**: update `_bootstrap_fresh_schema()` docstring to state that the connection is expected to be in autocommit mode (`isolation_level=None`) because the function opens its own explicit `BEGIN IMMEDIATE` transaction.
- **Reasoning**: all current call paths already satisfy the precondition through `_open_raw_connection()`. The fix only documents an existing invariant.

### AGG-DOC-3: WAL size missing-file diagnostic wording

- **Source**: DS LOW-2
- **Decision**: accepted for current gate
- **Required fix**: update `_read_wal_size_bytes()` docstring to state that a missing WAL file returns `0`, covering both nonexistent and SQLite-cleaned WAL files.
- **Reasoning**: no behavior change is needed; the current implementation is correct but the docstring can carry the diagnostic semantics.

## Deferred Or Closed Findings

### DS HIGH-1: concurrent fresh bootstrap TOCTOU

- **Decision**: closed by existing design and implementation
- **Reasoning**: `BEGIN IMMEDIATE` serializes writers, and retained `IF NOT EXISTS` DDL is an intentional fresh-bootstrap safety valve already accepted by the plan. DS also rates actual risk as low and identifies no corruption or half-initialization path.

### DS HIGH-2: projection checkpoint CAS synthetic test vs real race

- **Decision**: deferred-with-owner
- **Owner / destination**: WU-LIFE-01 recovery lifecycle proof, if checkpoint race proof becomes relevant there
- **Reasoning**: plan explicitly accepted deterministic synthetic stale-row testing for the CAS failure branch. Current tests prove rollback and persisted checkpoint invariants. A real multiprocess CAS race is broader proof, not a required fix for WU-DUR-02.

### DS HIGH-3: WAL checkpoint `db_path` / `connection` consistency validation

- **Decision**: deferred-with-owner
- **Owner / destination**: future Host maintenance hardening before production wiring of the checkpoint primitive
- **Reasoning**: the primitive is internal, diagnostic-only, not wired into hot paths or public maintenance API, and current tests pass a store-owned connection/path pair. Adding runtime validation now would broaden behavior without a current caller risk.

### DS MEDIUM-1: single-object schema validation error message

- **Decision**: deferred-with-owner
- **Owner / destination**: WU-LAYER-01 schema invariant hardening
- **Reasoning**: fail-fast messages satisfy current WU-DUR acceptance signals. Batch reporting is useful operational polish but not root-cause correctness.

### DS LOW-1: repeated test helpers

- **Decision**: deferred-with-owner
- **Owner / destination**: future test-maintenance cleanup
- **Reasoning**: helper duplication is limited to tests and does not affect production behavior or current gate acceptance. Extracting helpers now would add churn outside the durable behavior scope.

### DS OO-1: long read transaction governance scan

- **Decision**: deferred-with-owner
- **Owner / destination**: WU-LIFE-01 recovery lifecycle proof
- **Reasoning**: WU-DUR established SQLite read snapshot semantics and did not find a current production governance misuse. Lifecycle proof is the right owner for full path-by-path governance review.

### DS OO-2: schema constants synchronization knowledge

- **Decision**: closed
- **Reasoning**: DDL/table/index consistency tests are present and wired into `tests/README.md` durable foundation command. No additional production change is needed.

### DS OO-3: index name-only validation

- **Decision**: deferred-with-owner
- **Owner / destination**: WU-LAYER-01 schema invariant hardening
- **Reasoning**: plan explicitly scoped full DDL text/index definition validation out of WU-DUR. Current validation satisfies required table/index existence fail-closed behavior.

## Required Re-Review Scope

After the doc-only fix, request focused re-review from MiMo and DS for:

- `dayu/host/README.md`
- `dayu/host/durable/schema.py` docstring change
- `dayu/host/durable/maintenance.py` docstring change

The re-review should confirm the accepted fixes are complete and no behavior change was introduced.
