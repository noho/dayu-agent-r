# Phase 15 P15-S6 Implementation Artifact

- Gate: Phase 15 Slice P15-S6 Docs, Import Boundaries, Full Validation
- Role: AgentCodex implementation specialist
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- Scope: docs and test guard cleanup only; no purge behavior or production feature changes
- Stop status: complete

## Changed Files

- `dayu/host/README.md`
- `tests/README.md`
- `tests/host/test_import_boundary.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_weak_typing_guard.py`
- `docs/reviews/phase15-s6-implementation-codex-20260529.md`

## Implemented Plan Items

- Updated Host README current facts for implemented `purge_session`:
  - Service-facing entry points are `Host.purge_session(session_id, request)` and package-root command facade `purge_session(host, session_id, request)`.
  - Preconditions are closed Session, no active / queued / waiting / cancelling / recovering Run, and all Runs terminal.
  - Successful purge deletes local recoverable facts and derived local rows while preserving independent purge tombstone and purge idempotency record.
  - Read-after-purge does not reconstruct facts from tombstone, projection, audit, outbox, tool trace, or memory and uses existing `NOT_FOUND` semantics.
  - Append-only audit JSONL is retained; purge writes a tombstone audit record and stores its ref / digest in the tombstone.
  - Non-goals are remote / wire changes, new public error code, close / cancel / archive / memory forget / UI hide semantics, retention scheduler, periodic GC, DB vacuum, audit JSONL compaction / rotation, external audit delivery, and cold tool trace retention policy.
- Updated tests README only where current testing facts changed:
  - Purge public / command coverage now includes terminal-only preconditions, idempotency conflict, already-purged conflict, audit JSONL tombstone record, and read-after-purge `NOT_FOUND`.
  - Host import boundary and weak typing sections now explicitly mention `dayu.host.durable.purge` coverage.
- Added test guard coverage:
  - `tests/host/test_import_boundary.py` now explicitly asserts `dayu.host.durable.purge` stays a low-level durable Host owner and does not import upper layers, runtime, public command owner, audit owner, dispatch owner, opener, or recovery owner.
  - `tests/host/test_package_exports.py` now asserts internal purge durable helpers are not exposed from `dayu.host` package root or `__all__`.
  - `tests/host/test_weak_typing_guard.py` now explicitly confirms `durable/purge.py` is included in the weak typing scan.

## Doc Decisions

- Did not modify root `README.md`: P15-S6 did not change CLI, user workflow, trace/render entry, configuration, or project-level usage.
- Did not modify `dayu/README.md`: P15-S6 did not change layering, composition, or UI / Service / Host / Engine boundaries.
- Did not modify design or control docs: the assigned slice only required README current-fact sync and validation artifact.

## Validation

Focused guard sanity:

```text
source .venv/bin/activate && pytest tests/host/test_import_boundary.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q
.........................                                                [100%]
25 passed in 1.45s
```

Required focused P15 suite:

```text
source .venv/bin/activate && pytest tests/host/test_purge_session.py tests/host/test_durable_schema.py tests/host/test_command_handle.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py tests/host/test_audit_sink.py tests/host/test_projection_read_model.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_memory_projection.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_durable.py tests/host/test_open_host_runtime.py tests/host/test_import_boundary.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q
........................................................................ [ 31%]
........................................................................ [ 63%]
........................................................................ [ 95%]
...........                                                              [100%]
227 passed in 3.69s
```

Required pyright:

```text
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

## Residual Risks

- Fixed in current slice: README stale / incomplete purge facts, missing explicit `dayu.host.durable.purge` import-boundary coverage, missing explicit weak-typing scan coverage, and package-root leakage guard for purge durable helpers.
- Covered by existing validation: focused P15 purge behavior, schema, command/public read paths, audit sink, projections, outbox, open host runtime, import boundary, package exports, weak typing, and pyright.
- Deferred to later owner: remote / wire protocol, retention scheduler / periodic GC, DB vacuum, audit JSONL compaction / rotation, external audit delivery, heavy sink runner, and cold tool trace retention remain outside P15-S6 scope.
- Requiring Controller decision: none.
