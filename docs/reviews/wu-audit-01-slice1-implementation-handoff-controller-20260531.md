# WU-AUDIT-01 Slice 1 Implementation Handoff

## Gate

- Workflow: phaseflow / gateflow
- Gate: implementation
- Work unit: WU-AUDIT-01 Purge Audit Cross-medium Orphan Reconciliation
- Slice: Slice 1 - durable purge 去掉 pre-commit completion audit
- Accepted plan: `docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`
- Design source: `docs/host/design.md`
- Control document: `docs/host/host-core-followup-implementation-control.md`

## Assignment

You are the implementation specialist for Slice 1 only. You are not alone in the codebase: do not revert or overwrite edits outside your assigned scope, and adapt to existing committed controller artifacts.

Do not commit, push, create PR, enter review gates, or edit control documents.

## Allowed Files

Primary allowed files:

- `dayu/host/durable/purge.py`
- `tests/host/test_purge_session.py`

Conditional allowed files if strictly needed for exports/tests:

- `tests/host/test_package_exports.py`

Do not edit:

- `dayu/host/audit.py`
- `dayu/host/command.py`
- `dayu/host/api.py`
- README files
- implementation-control documents

Those are later slices or controller-owned documents.

## Required Implementation

Implement only the Slice 1 scope from the accepted plan:

1. Add durable helpers in `dayu/host/durable/purge.py`:
   - `build_purge_tombstone_id(session_id: str, client_request_id: str, semantic_request_digest: str) -> str`
   - `build_purge_attempt_ref(tombstone_id: str) -> str`
   - `build_purge_tombstone_digest(tombstone: PurgeTombstoneRow) -> str`
2. Make existing private `_build_tombstone_id(...)` delegate to `build_purge_tombstone_id(...)`, or replace internal use safely.
3. Update `PurgeSessionDeleteRequest` to remove the audit recorder port and accept:
   - `started_audit_record_ref: str`
   - `started_audit_record_digest: str`
4. Update `_insert_tombstone_and_idempotency(...)` so durable purge no longer calls an audit recorder and instead writes the started audit ref/digest into `PurgeTombstoneRow.audit_record_ref/audit_record_digest`.
5. Update validation and Chinese docstrings for the durable-layer semantic change.
6. Update low-level durable purge tests in `tests/host/test_purge_session.py` for the new request shape and tombstone assertions.

## Non-goals

- Do not implement started/completed/failed JSONL builders.
- Do not change public purge command ordering.
- Do not add audit query/analyze/reconciliation APIs.
- Do not modify durable schema.
- Do not preserve old audit-recorder compatibility wrappers in durable code.

## Validation

Run:

```bash
source .venv/bin/activate && pytest tests/host/test_purge_session.py -q
source .venv/bin/activate && pyright
```

If full pyright is too slow or blocked, report the exact command and failure.

## Completion Report

Write an implementation artifact to:

`docs/reviews/wu-audit-01-slice1-implementation-codex-20260531.md`

Include:

- changed files
- implemented plan items
- tests/pyright run and result
- residual risks or uncovered areas
- confirmation that you did not touch out-of-scope files
