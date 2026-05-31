# Phase 15 P15-S2 Implementation Artifact

## Gate / Scope

- Gate: Phase 15 implementation Slice P15-S2.
- Work unit: Retention / Purge / Production Hardening.
- Assigned slice: P15-S2 Delete Matrix Transaction Helper.
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md`.
- Accepted plan commit: `5fae495`.
- Accepted S1 commit: `f607655`.

## Changed Files

- `dayu/host/durable/purge.py`
- `tests/host/test_purge_session.py`
- `docs/reviews/phase15-s2-implementation-codex-20260529.md`

## Implemented Plan Items

- Added internal `purge_session_durable(...)` transaction helper with typed request/result and commit-after cleanup refs.
- Enforced purge preconditions from Session / Run / wait truth:
  - Session must exist unless matching tombstone replay applies.
  - Session must be `closed`.
  - Runs in `accepted`, `queued`, `running`, `waiting`, `cancelling`, `recovering` are rejected.
  - All Run rows must be terminal.
  - Active `waiting` wait records are rejected.
- Preserved tombstone/idempotency replay before reading deleted Session facts.
- Collected target EventLog, Run, Attempt, payload refs, precondition digest and deleted refs digest before deletion.
- Deleted rows in FK-safe order for audit markers, outbox, tool trace hot, memory, minimal read model, projection checkpoint/failure reset by target EventLog ids, old command idempotency records, waits, dispatch records, attempts, child-before-parent Runs, session slots, session row, EventLog rows, unreferenced payload descriptors and SQLite payload rows.
- Preserved other Session rows and shared payload descriptors.
- Returned `PurgeDeleteCounts`, `PurgeTombstoneRow`, `PurgeCommitCleanupRefs`; no slow file IO is performed in the transaction.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_purge_session.py tests/host/test_payload_store.py tests/host/test_projection_read_model.py tests/host/test_memory_projection.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_durable.py -q`
  - Result: `110 passed in 0.75s`.
- `source .venv/bin/activate && python -m pyright dayu/host/durable/purge.py dayu/host/durable/payload.py dayu/host/durable/read_model.py dayu/host/durable/memory.py dayu/host/durable/tool_trace.py dayu/host/durable/outbox.py dayu/host/durable/audit.py tests/host`
  - Result: `0 errors, 0 warnings, 0 informations`.

## Docs Decision

- No README updated in this slice.
- Reason: P15-S2 adds an internal durable transaction helper only; public `purge_session` remains unwired for S3, and README files are outside the allowed file list for this handoff.

## Residual Risks / Uncovered Areas

- Public command wiring, public error mapping, read-after-purge behavior and audit JSONL append are intentionally left to later P15 slices.
- Commit-after artifact file deletion is represented as cleanup refs only; actual file IO remains outside this transaction helper.
- Cold JSONL / external artifact broad GC remains a non-goal.

## Stop Status

- Completed without blocking questions.
- No evidence found that EventLog deletion requires deleting append-only audit JSONL or changing public API.
