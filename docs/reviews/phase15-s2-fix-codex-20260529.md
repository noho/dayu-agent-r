# Phase 15 P15-S2 Fix Artifact

## Gate / Scope

- Gate: Phase 15 S2 fix.
- Source reviews:
  - `docs/reviews/phase15-s2-code-review-ds-20260529.md`
  - `docs/reviews/phase15-s2-code-review-mimo-20260529.md`
  - `docs/reviews/phase15-s2-code-review-controller-adjudication-20260529.md`
- Fixed accepted findings only: S2-ADJ-001 through S2-ADJ-005.
- Rejected findings S2-REJ-001 / S2-REJ-002 were not implemented.

## Changed Files

- `dayu/host/durable/purge.py`
- `tests/host/test_purge_session.py`
- `docs/reviews/phase15-s2-fix-codex-20260529.md`

## Per-Finding Status

### S2-ADJ-001 — 已修复

- Added explicit purge projection reset allow-list:
  - `host.minimal-read-model`
  - `host.memory.session.v1`
  - `host.audit-log-jsonl`
  - `host.tool-trace`
  - `host.outbox-terminal`
- Checkpoint/failure rows are deleted only when both conditions hold:
  - referenced EventLog id belongs to target Session
  - `consumer_id` is in the allow-list
- If a non-allowed consumer checkpoint/failure references target EventLog, `HostDurableError` is raised before EventLog deletion.
- Added rollback tests for unsupported checkpoint and unsupported failure consumers.

### S2-ADJ-002 — 已修复

- `_build_purge_precondition_digest(...)` now reads target Run ids once and reuses the cached tuple for Attempt precondition rows.

### S2-ADJ-003 — 已修复

- Added missing top-level blank lines in `purge.py` and `test_purge_session.py`.

### S2-ADJ-004 — 已修复

- Non-terminal Run rejection test now asserts no tombstone is written after `PurgeSessionInvalidStateError`.

### S2-ADJ-005 — 已修复

- Seeded an idempotency record with scope kind outside `_SESSION_FACT_SCOPE_KINDS`.
- Main purge matrix test asserts that out-of-scope idempotency row is preserved after purge.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_purge_session.py tests/host/test_payload_store.py tests/host/test_projection_read_model.py tests/host/test_memory_projection.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_durable.py -q`
  - Result: `112 passed in 0.77s`.
- `source .venv/bin/activate && python -m pyright dayu/host/durable/purge.py dayu/host/durable/payload.py dayu/host/durable/read_model.py dayu/host/durable/memory.py dayu/host/durable/tool_trace.py dayu/host/durable/outbox.py dayu/host/durable/audit.py tests/host`
  - Result: `0 errors, 0 warnings, 0 informations`.

## Residual Risks

- Public command wiring, public error mapping, read-after-purge behavior, and audit JSONL append remain intentionally outside S2.
- Commit-after file cleanup still returns refs only; actual file deletion remains a later slice concern.
- Rejected test expansion items were not implemented per controller adjudication.

## New Blocking Questions

- None.
