# Gateflow Implementation Artifact: Host Phase 2 Slice 1 Durable Schema / Transaction

## Gate

- work gate name: `implementation`
- work-unit: Host Phase 2 Durable Store / EventLog / Payload Foundation
- assigned slice id: Slice 1 - SQLite Schema Convention / Fresh DB Bootstrap / Transaction Runner
- approved plan path: `docs/host/phase2-durable-store-eventlog-plan.md`
- accepted plan commit: `83c6ad6`
- controller decision artifact: `docs/reviews/gateflow-implementation-decision-host-p2-s1-sqlite-payload-table-name-20260514.md`

## Assigned Scope

Allowed production files:

- `dayu/host/durable/__init__.py`
- `dayu/host/durable/errors.py`
- `dayu/host/durable/codec.py`
- `dayu/host/durable/options.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/connection.py`
- `dayu/host/durable/transaction.py`

Allowed tests:

- `tests/host/test_durable_schema.py`
- `tests/host/test_durable_transaction.py`

Controller-approved follow-up change:

- `docs/host/phase2-durable-store-eventlog-plan.md` updated to replace invalid physical table name `sqlite_payloads` with `host_sqlite_payloads`.

## Explicit Non-Goals Observed

- 未实现 Slice 2 EventLog append / reader / idempotency behavior。
- 未实现 Slice 3 payload descriptor / artifact helper / host instance liveness behavior。
- 未实现 Session / Run / Attempt tables、状态机、admission、queue、CAS transition。
- 未实现 Host command path、Engine dispatch、Projection、Memory、ToolRuntime、Remote、Recovery classifier、lease / fencing / takeover。
- 未修改 `dayu/runtime`、`dayu/engine`、`dayu/fins`、`dayu/service`、`dayu/ui`。
- 未修改 `docs/host/design.md` 或 `docs/host/implementation-control.md`。

## Changed Files

- `docs/host/phase2-durable-store-eventlog-plan.md`
- `dayu/host/durable/__init__.py`
- `dayu/host/durable/errors.py`
- `dayu/host/durable/codec.py`
- `dayu/host/durable/options.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/connection.py`
- `dayu/host/durable/transaction.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_durable_transaction.py`
- `docs/reviews/gateflow-implementation-host-p2-s1-durable-schema-transaction-20260514.md`

## Controller Decision Applied

The initial implementation found that SQLite rejects user-created objects using the reserved `sqlite_` prefix. The controller decision artifact accepted this as a plan schema table-name bug and directed Slice 1 to rename the physical table from `sqlite_payloads` to `host_sqlite_payloads`.

Applied result:

- Physical table constant now uses `host_sqlite_payloads`.
- `payload_descriptors.sqlite_payload_id` still references that table's `payload_id`.
- Descriptor kind `sqlite_payload`, field name `sqlite_payload_id`, and typed semantics remain unchanged.
- No Slice 2 / Slice 3 payload behavior was added.

## Plan Items Implemented

- Added Host durable internal package skeleton without exporting from `dayu.host` package root.
- Added Host durable error taxonomy for Slice 1 and declared Phase 2 durable errors.
- Added canonical JSON, fixed UTC microsecond `Z` timestamp, bytes digest and JSON digest helpers.
- Added `HostSQLiteStoragePolicy`, `PayloadStoragePolicy`, `HostDurableStoreOptions`.
- Added `HostDurableStore` and `open_host_durable_store`.
- Added schema constants and DDL for all Phase 2 foundation tables, with physical payload table `host_sqlite_payloads`.
- Added bootstrap / schema validation entry points with `PRAGMA user_version=1`.
- Added SQLite connection setup with parent directory creation, WAL, `foreign_keys=ON` and configured `busy_timeout`.
- Added typed `HostTransaction`, `HostTransactionRunner`, `HostTransactionOperation`, `AfterCommitCallback`, `SQLiteScalar`, `SQLParameters`, `HostRow`, `HostExecuteResult`.
- Added `BEGIN IMMEDIATE` write transaction semantics, finite busy / locked retry, rollback on failure, after-commit callbacks after successful commit only, and durable commit preservation when after-commit fails.
- Added tests covering schema bootstrap, PRAGMA, table constraints, future table absence, transaction commit / rollback / after-commit, busy retry, non-retryable errors and codec helpers.

## Validation Commands And Results

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py -q
```

Result: passed, `15 passed`.

Command:

```bash
source .venv/bin/activate && pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

Result: passed, `7 passed`.

Command:

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

## Documentation Decision

- Updated `docs/host/phase2-durable-store-eventlog-plan.md` only because the controller decision explicitly required the approved plan DDL / FK / test references to use `host_sqlite_payloads`.
- No README was updated. The Slice 1 handoff did not include README files, and no user-facing command, package overview, or documented Host public API changed.

## Plan Gaps Or Controller Issues

- Resolved: invalid SQLite physical table name `sqlite_payloads` fixed through controller decision artifact.
- No remaining Slice 1 plan gap identified.
- No additional controller decision needed for this slice.

## Uncovered Areas And Residual Risk Classification

- EventLog append/read and idempotency behavior: accepted as covered by later Slice 2 in the approved plan.
- Payload descriptor helper, local artifact helper, and host instance liveness behavior: accepted as covered by later Slice 3 in the approved plan.
- Multi-process EventLog append smoke: accepted as covered by later Slice 2 in the approved plan.
- README sync: not updated for this slice; no current user-facing API or command changed.
- Residual risk level for Slice 1: low. The remaining uncovered areas are intentional future-slice scope, not current-slice defects.

## Completion Signal

Met.

- Slice 1 tests pass.
- Host package export / import boundary / weak typing guard tests pass.
- `python -m pyright dayu/host tests/host` passes.
- Host durable modules do not import `dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui`。
- The schema bootstrap creates foundation tables only and does not create Session / Run / Attempt / wait / projection / outbox / memory / purge tables.

## Stop Condition Status

- Did not require adding Session / Run / Attempt tables.
- Did not require moving transaction runner to `dayu.runtime`.
- Busy / locked classification uses SQLite error code attributes and does not broadly guess from exception messages.
- Pyright did not require `Any` / `object` or untyped signatures.
- No active stop condition remains for Slice 1.

## Artifact Path

`docs/reviews/gateflow-implementation-host-p2-s1-durable-schema-transaction-20260514.md`
