# Host Phase 8 P8-S1 Implementation Artifact

- **Gate**: P8-S1 implementation
- **Work unit**: Projection Core / Host Event Stream / Minimal Read Model
- **Slice**: P8-S1 Projection Runner / Checkpoint / Typed Consumer Contracts
- **Branch**: `feat/host-phase8-projection-core-event-stream`
- **Approved plan commit**: `b85fd8e`
- **Truth plan**: `docs/host/phase8-projection-core-event-stream-plan.md`
- **Status**: implementation complete; stopped before review / commit / PR gate

## Scope And Non-Goals

Implemented only S1:

- Added projection checkpoint / failure schema and durable store.
- Added typed projection consumer contracts and `ProjectionRunner`.
- Added event filter logic, typed payload parsing from `EventLogRow`, checkpoint / failure invariants, tests, and boundary guards.

Intentionally not implemented:

- RunResult projection.
- Session timeline projection.
- Host event stream fanout or read API changes.
- Audit / Tool Trace / Outbox sinks.
- command path, admission, waiting, dispatch, Engine, runtime, service, UI, fins changes.

## Changed Files

Production:

- `dayu/host/durable/schema.py`
- `dayu/host/durable/projection.py`
- `dayu/host/projection.py`

Tests / docs:

- `tests/host/test_durable_schema.py`
- `tests/host/test_projection_checkpoint.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_import_boundary.py`
- `tests/README.md`

## Implemented Plan Items

- Bumped fresh Host durable schema version from `4` to `5`.
- Added `host_projection_checkpoints` and `host_projection_failures`.
- Confirmed `event_log(event_sequence)` is `INTEGER PRIMARY KEY AUTOINCREMENT`, which satisfies SQLite FK parent key rules; added schema test that creates a FK probe and rejects an invalid reference.
- Added checkpoint row codec / helpers:
  - missing checkpoint initializes to cursor `0`;
  - forward advance persists event sequence, event id, success timestamp;
  - backward / repeated advance is rejected.
- Added failure row codec / helpers:
  - write / update failure row;
  - increment `failure_count`;
  - clear failure after later success.
- Added typed projection contract:
  - `ProjectionConsumerId`
  - `ProjectionEventClassFilter`
  - `ProjectionEventFilter`
  - `ProjectionEventView`
  - `ProjectionApplyStatus`
  - `ProjectionApplyResult`
  - `ProjectionConsumer`
  - `ProjectionRunner`
- Added per-class filter logic where each `EventClass` owns its own `event_types` rule.
- Added `ProjectionEventView` builder from `EventLogRow` using `dayu.host._event_payload.payload_object`.
- `ProjectionRunner` receives an injected `HostTransactionRunner`; it does not open SQLite connections and does not import or call public command facade.
- Runner applies consumer writes and checkpoint advance in the same `HostTransactionRunner.run_write()` transaction.
- Consumer failure rolls back consumer writes, records projection-local failure in a separate transaction, and does not advance checkpoint.
- Duplicate apply result advances checkpoint as successful replay defense.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

Result: `28 passed in 0.63s`

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

Result: `0 errors, 0 warnings, 0 informations`

Passed:

```bash
git diff --check
```

Result: no whitespace errors.

## Docs Decision

Updated `tests/README.md` because this slice added factual Host projection checkpoint / runner tests and a focused command for the S1 validation set.

Did not update root `README.md`, `dayu/README.md`, or `dayu/host/README.md` because S1 only adds internal projection core contracts and schema; it does not change public user commands, layer assembly, event stream read API, or Host developer manual facts that are already documented as current user-facing behavior.

## Plan Gaps / Deviations

- No blocking plan gap found.
- Checkpoint table does not FK `checkpoint_event_sequence` directly because cursor `0` is a valid initial checkpoint and cannot reference `event_log`. It uses the planned `checkpoint_event_id` FK plus CHECK invariant for non-zero cursor identity. The required `event_log(event_sequence)` FK parent-key stop check is covered by a schema probe test for later Phase 8 tables that do FK event sequences.
- Runner processes rows one at a time in separate `run_write()` transactions. This preserves the required invariant that each consumer projection write and corresponding checkpoint advance commit atomically together, and avoids rolling back earlier successful rows when a later row fails.

## Residual Risks

- **Covered by later slice**: RunResult / Session timeline idempotent read model consumers and repair helper remain P8-S3 scope.
- **Covered by later slice**: `stream_run_events` cursor truth independence from projection checkpoint / failure remains P8-S2 scope.
- **Covered by later phase/work unit**: automatic after-commit wakeup, Memory, Recovery, Audit, Tool Trace, and Outbox integration remain explicitly outside S1.
- **Current slice residual risk**: no known uncovered S1 invariant after the validation commands above.

## Completion Signal

P8-S1 implementation is complete and ready for code review. No commit, push, PR creation, or review gate was started.
