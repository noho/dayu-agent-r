# Gateflow Controller Adjudication: Host P2 Aggregate Re-Review

## Scope

- Work unit: Host Phase 2 Durable Store / EventLog / Payload Foundation
- Gate: aggregate re-review after controller-accepted aggregate deepreview fixes
- Date: 2026-05-14
- Base: `main`
- Branch: `feat/host-phase2-durable-store-eventlog`

## Source Artifacts

- Aggregate deepreview:
  - `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-mimo-20260514.md`
  - `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-ds-20260514.md`
- Controller aggregate adjudication:
  - `docs/reviews/gateflow-aggregate-deepreview-host-p2-durable-store-eventlog-controller-adjudication-20260514.md`
- Aggregate fix:
  - `docs/reviews/gateflow-aggregate-fix-host-p2-durable-store-eventlog-20260514.md`
- Aggregate re-review:
  - `docs/reviews/gateflow-aggregate-re-review-host-p2-durable-store-eventlog-mimo-20260514.md`
  - `docs/reviews/gateflow-aggregate-re-review-host-p2-durable-store-eventlog-ds-20260514.md`

## Controller Decision

Conclusion: PASS.

AgentMiMo and AgentDS independently re-reviewed the aggregate fix and both concluded that all controller-accepted findings `AGG-F1` through `AGG-F7` are fixed. Both reviewers also confirmed that controller-rejected `AGG-R1` was not accidentally implemented: artifact directory fsync failures still raise structured `HostArtifactWriteError` and are not swallowed.

No new accepted finding remains.

## Finding Status

- `AGG-F1`: fixed. `require_non_empty_text` now raises `HostDurableError` for non-string runtime input before calling string methods.
- `AGG-F2`: fixed. idempotency created EventLog references require `created_event_id` and `created_event_sequence` to be both set or both unset.
- `AGG-F3`: fixed. SQLite `SQLITE_CONSTRAINT_CHECK` is classified explicitly.
- `AGG-F4`: fixed. `HostTransactionRunner.run_write` no longer contains the unreachable retry-exhausted fallback after the loop.
- `AGG-F5`: fixed. SQLite connection cleanup during initialization failure uses best-effort close and does not mask the original setup/bootstrap error.
- `AGG-F6`: fixed. redundant artifact parent containment validation was removed without weakening traversal protection.
- `AGG-F7`: fixed. liveness `boot_id` identity comparison tolerates `None` on either side and still rejects mismatched non-`None` values; `pid` and `process_start_token` remain strict.
- `AGG-R1`: rejected and intentionally not implemented. Directory fsync failures continue to surface as durable write errors.

## Validation Evidence

Controller reran:

- `source .venv/bin/activate && pytest tests/host -q`: 101 passed.
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_lane.py tests/runtime/test_filelock.py -q`: 29 passed.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`: 0 errors.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: 0 errors.

AgentMiMo reran:

- `pytest tests/host -q`: 101 passed.
- runtime import/lane/filelock tests: 29 passed.
- `pyright dayu/host tests/host`: 0 errors.
- `pyright dayu/ tests/ utils/`: 0 errors.

AgentDS reran:

- `pytest tests/host -q`: 101 passed.
- runtime import/lane/filelock tests: 29 passed.
- `pyright dayu/host tests/host`: 0 errors.
- `pyright dayu/ tests/ utils/`: 0 errors.

## Documentation Decision

No README update is required for the aggregate fix itself. The fix changes internal Host durable correctness and diagnostics only; it does not change public API, CLI usage, configuration, documented workflow, or architecture boundaries. `docs/host/implementation-control.md` is updated to record aggregate review, fix, re-review, residual risks, and final gate state.

## Residual Risks / Deferred Items

- Artifact orphan cleanup remains deferred to a later cleanup / diagnostics work unit. Phase 2 guarantees orphan files after rollback are not accepted durable facts.
- Phase 2 `host_instances` liveness rows are not lease, fencing, owner, takeover, or positive orphan proof; recovery / lifecycle phases must not reinterpret them that way.
- `heartbeat_current_instance` / repeated `register_current_instance` can move the same current instance row from `stopping` back to `running`; later lifecycle work must revisit this before assigning stronger semantics.
- `SQLitePayloadWriteRequest.payload_json=None` in `canonical_json` format remains valid JSON `null`; if later command/path construction wants to forbid implicit null, that tightening belongs at the higher construction boundary.
- Directory fsync failures intentionally remain visible durable write errors; they are not swallowed for platform compatibility.

## Gate Decision

Proceed to accepted deepreview commit.

After the accepted deepreview commit is created, Host Phase 2 is ready-to-create-PR. Creating or pushing a PR remains outside the automatic local Gateflow boundary and requires explicit user authorization.
