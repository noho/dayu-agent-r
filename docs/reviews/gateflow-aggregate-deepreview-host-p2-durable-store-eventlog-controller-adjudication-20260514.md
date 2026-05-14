# Gateflow Controller Adjudication: Host P2 Aggregate Deepreview

## Gate

- **gate name**: aggregate deepreview adjudication
- **work unit**: Host Phase 2 Durable Store / EventLog / Payload Foundation
- **branch**: `feat/host-phase2-durable-store-eventlog`
- **base**: `main`
- **date**: 2026-05-14

## Inputs

- MiMo aggregate deepreview: `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-mimo-20260514.md`
- DS aggregate deepreview: `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-ds-20260514.md`
- Accepted local commits:
  - plan: `83c6ad6`
  - Slice 1: `be5dbdc`
  - Slice 2: `50ba2d7`
  - Slice 3: `7bbce64`

## Reviewer Conclusions

- MiMo: `PASS`, no accepted finding; two low-risk observations.
- DS: `PASS`, 8 findings: 3 medium, 5 low.

## Controller Decision

Aggregate deepreview **does not advance to accepted deepreview commit yet**. Seven DS findings are accepted for local fix. One DS finding is rejected for current fix because it is speculative on this platform and the proposed fix would weaken durability semantics.

## Accepted Findings

### `AGG-F1` - accepted - medium - `_validation.require_non_empty_text` should fail structurally for non-text runtime input

The helper is typed as `str`, but Python runtime callers can still pass `None` or other values. Because this helper is now shared across durable modules, it should fail with `HostDurableError` rather than a raw `AttributeError`. Fix with a runtime `isinstance(value, str)` guard while preserving existing valid string behavior and error messages for empty / whitespace strings.

### `AGG-F2` - accepted - medium - idempotency created event id and sequence must be paired

`IdempotencyResultRef.created_event_id` and `created_event_sequence` are optional as a pair. Allowing only one side produces a partial EventLog reference that downstream cursor-based readers cannot consume reliably. Fix by requiring both fields to be set or both unset; add tests for each one-sided case.

### `AGG-F3` - accepted - low - SQLite CHECK constraint classification is generic

CHECK constraint failures currently fall through to generic `HostDurableError`. Add explicit classification for `SQLITE_CONSTRAINT_CHECK` with a diagnostic message and test it through a direct CHECK violation.

### `AGG-F4` - accepted - low - unreachable transaction retry exhausted raise

The fallback raise after the `run_write` retry loop is unreachable under current loop structure. Remove it or refactor to avoid dead code.

### `AGG-F5` - accepted - low - connection close during open failure can mask original error

Wrap cleanup `connection.close()` in best-effort handling so an initialization error is not replaced by close-time failure.

### `AGG-F6` - accepted - low - redundant artifact containment check

`write_artifact_bytes` calls the same parent containment check twice before creating parent directories. Remove the redundant call while preserving the containment check that protects symlink traversal.

### `AGG-F7` - accepted - low - liveness boot_id optionality can over-constrain same-process identity

`boot_id` is optional. If one side is `None`, identity comparison should not reject the same `host_instance_id + pid + process_start_token`. Keep conflict when both boot ids are non-None and different; add tests for `None -> value` tolerance and value mismatch rejection.

## Rejected / Deferred Observations

### `AGG-R1` - rejected for current fix - artifact directory fsync on macOS

DS flagged that directory `fsync` can fail on some macOS / filesystem combinations and proposed swallowing the error. Controller rejects this as a current finding:

- Local artifact tests already execute successfully on the current Darwin environment, so the claimed systemic failure is not reproduced.
- Directory fsync is part of the accepted durable publish ordering. Silently ignoring fsync errors would weaken durability guarantees and hide real I/O failures.
- If a future supported filesystem proves incompatible, handle it with an explicit platform/filesystem policy and tests rather than downgrading errors opportunistically.

## Existing MiMo Observations

- `heartbeat_current_instance` and repeated `register_current_instance` can move the current host instance row from `stopping` back to `running`.
  - Not accepted for current fix. This is current Phase 2 tested behavior and has no recovery consumer yet. Track for later lifecycle / recovery phases.
- `SQLitePayloadWriteRequest.payload_json=None` in `CANONICAL_JSON` mode persists JSON `null`.
  - Not accepted for current fix. `JsonValue` includes `None`, JSON null is valid canonical JSON, and no current caller depends on omission semantics.

## Required Fix Scope

Allowed files:

- `dayu/host/durable/_validation.py`
- `dayu/host/durable/idempotency.py`
- `dayu/host/durable/transaction.py`
- `dayu/host/durable/connection.py`
- `dayu/host/durable/artifact.py`
- `dayu/host/durable/liveness.py`
- relevant tests under `tests/host/`
- `docs/reviews/gateflow-aggregate-fix-host-p2-durable-store-eventlog-20260514.md`

Do not change design docs, public package exports, Engine/Fins/Service/UI/runtime, or README unless the fix changes documented current behavior.

## Required Validation

- `source .venv/bin/activate && pytest tests/host -q`
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_lane.py tests/runtime/test_filelock.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`

## Gate Outcome

Proceed to aggregate fix gate for `AGG-F1` through `AGG-F7`, then run aggregate re-review.
