# Gateflow Implementation Artifact: Host P3-S1 Schema And Row Codecs

- **work gate name**: implementation
- **work-unit name**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice id**: P3-S1 Schema And Row Codecs
- **approved plan path**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **accepted plan commit**: `71ddcba`
- **artifact path**: `docs/reviews/gateflow-implementation-host-p3-s1-schema-row-codecs-20260514.md`

## Assigned Scope

- bump `HOST_SCHEMA_VERSION` to `2`.
- add Phase 3 table constants and DDL for sessions, slots, runs, attempts, attempt dispatch records.
- add active-run partial unique index and queued FIFO index.
- update bootstrap DDL order so foundation tables precede Phase 3 state tables and indexes.
- add `dayu/host/durable/state.py` row dataclasses, status serializers/deserializers, and `HostRow` conversion helpers.
- update slice tests in `tests/host/test_state_schema.py` and `tests/host/test_durable_schema.py`.

## Explicit Non-goals

- no Session lifecycle command.
- no admission.
- no promotion.
- no cancel.
- no public API export.
- no Engine dispatch / scheduler / lane / WorkerProxy / LocalProxy / RemoteProxy / EngineEvent ingest / ToolRuntime / wait / resolve_wait / steer / retry / replay / context compaction / recovery.
- no command behavior in `state.py`; it does not append EventLog.

## Allowed Files / Modules

- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_durable_schema.py`
- `dayu/host/README.md` was touched only under the handoff exception because one existing statement became directly false after schema/codec landed.
- this implementation artifact.

## Changed Files

- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py`
- `tests/host/test_state_schema.py`
- `tests/host/test_durable_schema.py`
- `dayu/host/README.md`
- `docs/reviews/gateflow-implementation-host-p3-s1-schema-row-codecs-20260514.md`

## Implemented Plan Items

- `HOST_SCHEMA_VERSION` is now `2`.
- Added constants for Phase 3 tables and indexes.
- Added DDL for `host_sessions`, `host_session_slots`, `host_runs`, `host_attempts`, and `host_attempt_dispatch_records`.
- Added `host_runs_one_active_per_session` partial unique index for active statuses: `running`, `waiting`, `cancelling`, `recovering`.
- Added `host_runs_queue_fifo` partial index on `(session_id, accepted_event_sequence, run_id)` for queued runs.
- Added `host_runs_session_status` index from the approved schema contract.
- Bootstrap now runs foundation DDL, Phase 3 state DDL, then Phase 3 indexes before setting `PRAGMA user_version=2`.
- Added row dataclasses: `SessionRow`, `SessionSlotRow`, `RunRow`, `AttemptRow`, `DispatchRecordRow`.
- Added internal enums and serializers/deserializers for `DispatchRecordStatus`, `WorkerKind`, and `RunStartReason`.
- Added serializers/deserializers for public `SessionStatus`, `RunStatus`, and `AttemptStatus`.
- Added typed `HostRow` conversion helpers for all Phase 3 state rows.
- Added tests for fresh DB table set, `user_version=2`, partial unique index shape, queued FIFO index shape, one-active invariant, queued multiplicity, dispatch status CHECK, schema mismatch, and row codecs.

## Not Implemented

- No lifecycle, admission, promotion, cancel, dispatch, public export, or command logic was implemented. Reason: explicit P3-S1 non-goals.
- No broad README synchronization was done. Reason: approved plan defers full documentation sync to P3-S6.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_state_schema.py tests/host/test_durable_schema.py -q`
  - result: passed, `14 passed in 0.13s`.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - result: passed, `0 errors, 0 warnings, 0 informations`.

## Documentation Update Decision / Result

- Full documentation sync remains deferred to P3-S6 per approved plan.
- Narrow exception applied: `dayu/host/README.md` had a durable foundation statement that no longer matched the schema/codec facts after P3-S1. It now states that Phase 3 state schema / row codec exists, while lifecycle command, admission, promotion, cancel, ToolRuntime, and Engine dispatch remain unimplemented.
- `tests/README.md` was not updated because the existing test overview remains accurate enough and full test documentation is owned by P3-S6.

## Plan Gaps / Controller Questions

- No blocking plan gaps found.
- No controller question is required for this slice.
- The SQLite partial unique index is representable and tested.
- pyright did not require unrelated broad fixes.

## Residual Risks / Uncovered Areas

- **covered by later slice in approved plan**: actual Session lifecycle commands and slot idempotency are owned by P3-S2.
- **covered by later slice in approved plan**: low-level Run / Attempt transition helpers and CAS updates are owned by P3-S3.
- **covered by later slice in approved plan**: admission, FIFO promotion, cancel, terminal closeout, and multiprocess race proofs are owned by P3-S4 through P3-S6.
- **fixed in current slice before review**: schema-level active Run invariant and dispatch record status domain are enforced by SQLite constraints and tested.
- **uncovered by current slice by design**: old DB migration and compatibility reads are intentionally absent; approved schema rule is fresh schema only.

## Completion Signal / Stop Condition Status

- P3-S1 completion signal met: schema tests pass, row codec tests pass, and no future Phase 3+ behavior was implemented.
- Stop conditions were not triggered.
- Implementation stops at current gate boundary; no review, fix, re-review, commit, push, or PR action was performed.
