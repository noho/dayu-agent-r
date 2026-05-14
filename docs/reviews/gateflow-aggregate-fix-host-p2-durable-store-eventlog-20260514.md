# Gateflow Aggregate Fix: Host P2 Durable Store / EventLog / Payload Foundation

## Scope

- **work gate**: aggregate deepreview fix
- **work unit**: Host Phase 2 Durable Store / EventLog / Payload Foundation
- **date**: 2026-05-14
- **source review artifacts**:
  - `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-mimo-20260514.md`
  - `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-ds-20260514.md`
  - `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`
- **controller-accepted findings**: `AGG-F1` through `AGG-F7`
- **explicit non-goals honored**:
  - Did not swallow artifact directory fsync failures.
  - Did not change stopping -> running liveness behavior.
  - Did not require canonical_json `payload_json` to be non-`None`.
  - Did not modify public exports, Engine/Fins/Service/UI/runtime, or design docs.
  - Did not commit.

## Per-Finding Status

### AGG-F1 - fixed

`dayu/host/durable/_validation.py` now checks runtime type before calling string methods in `require_non_empty_text`. Non-string runtime input raises `HostDurableError` with the existing `"field must be non-empty"` message. Valid strings, empty strings, and whitespace strings preserve prior behavior and messages.

Tests added in `tests/host/test_durable_validation.py`.

### AGG-F2 - fixed

`dayu/host/durable/idempotency.py` now enforces `created_event_id` and `created_event_sequence` as a pair: both set or both unset. One-sided references fail before SQLite write with `HostDurableError`.

Tests added in `tests/host/test_idempotency_store.py` for id-only and sequence-only cases. The missing EventLog FK test was adjusted to provide both fields so it still verifies SQLite FK classification.

### AGG-F3 - fixed

`dayu/host/durable/transaction.py` now classifies `SQLITE_CONSTRAINT_CHECK` explicitly and returns `HostDurableError("Host durable CHECK constraint failed")`.

Test added in `tests/host/test_durable_transaction.py` using a direct CHECK violation.

### AGG-F4 - fixed

`HostTransactionRunner.run_write` now uses an internal infinite retry loop with retry exhaustion handled inside the busy/locked branch. The unreachable fallback retry-exhausted raise after the loop was removed.

Existing busy retry tests still verify finite exhaustion and attempt count.

### AGG-F5 - fixed

`dayu/host/durable/connection.py` now uses `_close_connection_best_effort` during open/setup/bootstrap failure cleanup so close-time `sqlite3.Error` cannot replace the original initialization error.

Test added in `tests/host/test_durable_connection.py` with a SQLite connection subclass whose `close()` raises.

### AGG-F6 - fixed

`dayu/host/durable/artifact.py` removed the redundant `_ensure_parent_dir_contained` call in `write_artifact_bytes`. The remaining containment path is `_contained_final_path(...)`, which still calls `_ensure_parent_dir_contained(...)` before parent directory creation, and existing symlink traversal protection tests pass.

No directory fsync behavior was changed.

### AGG-F7 - fixed

`dayu/host/durable/liveness.py` now treats `boot_id` as conflicting only when both durable row and current identity have non-`None` values and those values differ. `pid` and `process_start_token` remain strict.

Tests added in `tests/host/test_host_instance_liveness.py` for `None -> value`, `value -> None`, and mismatched non-empty boot ids.

## Changed Files

- `dayu/host/durable/_validation.py`
- `dayu/host/durable/idempotency.py`
- `dayu/host/durable/transaction.py`
- `dayu/host/durable/connection.py`
- `dayu/host/durable/artifact.py`
- `dayu/host/durable/liveness.py`
- `tests/host/test_durable_validation.py`
- `tests/host/test_durable_connection.py`
- `tests/host/test_durable_transaction.py`
- `tests/host/test_idempotency_store.py`
- `tests/host/test_host_instance_liveness.py`
- `docs/reviews/gateflow-aggregate-fix-host-p2-durable-store-eventlog-20260514.md`

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_durable_validation.py tests/host/test_durable_connection.py tests/host/test_durable_transaction.py tests/host/test_idempotency_store.py tests/host/test_host_instance_liveness.py tests/host/test_artifact_store.py -q`
  - Result: `42 passed in 0.19s`
- `source .venv/bin/activate && pytest tests/host -q`
  - Result: `101 passed in 0.77s`
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_lane.py tests/runtime/test_filelock.py -q`
  - Result: `29 passed in 0.66s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

## README Decision

README files were not modified. The fixes are internal Host durable correctness and diagnostic changes, with no public API, CLI, configuration, documented workflow, or architecture boundary change. The existing broad commands in `tests/README.md` (`pytest tests/host -q` and full pyright commands) remain accurate.

## Source Artifact Status Update

The DS source review finding titles were not edited because the user constrained writable review output to this aggregate fix artifact. Final status mapping is recorded here instead:

- DS finding 1 -> `AGG-F1`: fixed
- DS finding 2 -> `AGG-F2`: fixed
- DS finding 4 -> `AGG-F3`: fixed
- DS finding 5 -> `AGG-F4`: fixed
- DS finding 6 -> `AGG-F5`: fixed
- DS finding 7 -> `AGG-F6`: fixed
- DS finding 8 -> `AGG-F7`: fixed

## Open Questions

None.

## Residual Risks / Uncovered Areas

- Connection cleanup masking is covered at the best-effort helper boundary with a close-failing SQLite subclass; full bootstrap-path monkeypatch coverage was not added because the helper is the new single cleanup mechanism and required validation passed.
- Artifact orphan cleanup, artifact directory fsync policy, stopping -> running liveness behavior, and canonical JSON `None` payload semantics remain intentionally out of scope per controller adjudication.

## Completion Signal

All controller-accepted findings `AGG-F1` through `AGG-F7` are fixed. No accepted finding remains unfixed.
