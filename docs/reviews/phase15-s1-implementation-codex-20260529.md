# Phase 15 P15-S1 Implementation Artifact

## Gate

- Work unit: Phase 15 retention purge production hardening
- Current gate: Phase 15 implementation Slice P15-S1
- Slice: Purge Tombstone Schema And Durable Primitives
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- Accepted plan commit: `5fae495`
- Controller status commit: `76fde73`

## Scope

- Implemented only durable schema and primitive helpers for purge tombstone replay.
- Did not implement public `purge_session` command behavior.
- Did not delete Session / Run / EventLog facts.
- Did not write audit JSONL.
- Did not commit, push, create PR, or enter another slice.

## Changed Files

- `dayu/host/durable/schema.py`
- `dayu/host/durable/purge.py`
- `tests/host/test_durable_schema.py`
- `tests/host/test_purge_session.py`
- `docs/reviews/phase15-s1-implementation-codex-20260529.md`

## Implemented Plan Items

- Bumped `HOST_SCHEMA_VERSION` from `13` to `14`.
- Added `host_purge_tombstones` table constant, DDL, governance table set membership, and unique `session_id` index.
- Kept `host_purge_tombstones` independent from deleted facts: no FK to `event_log` or `host_sessions`.
- Added durable purge primitives:
  - `PurgeTombstoneRow`
  - `PurgeDeleteCounts`
  - `PurgePreconditionSnapshot`
  - `PurgeReplayDecisionKind`
  - `PurgeReplayDecision`
- Added helpers:
  - `read_purge_tombstone_by_session_id`
  - `read_purge_tombstone_by_id`
  - `insert_purge_tombstone`
  - `build_purge_semantic_digest`
  - `build_deleted_counts_digest`
  - `record_or_read_purge_idempotency`
- Reused `IdempotencyStore` for purge replay rows with `created_event_id = NULL` and `created_event_sequence = NULL`.
- Covered tombstone-present / idempotency-missing replay and conflict decisions:
  - same key and same digest replays from tombstone;
  - same key and different digest returns idempotency conflict decision;
  - different key returns already-purged conflict decision.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_purge_session.py -q
```

Result: `26 passed in 0.38s`.

Passed:

```bash
source .venv/bin/activate && python -m pyright dayu/host/durable/purge.py tests/host/test_purge_session.py
```

Result: `0 errors, 0 warnings, 0 informations`.

Additional guard passed:

```bash
source .venv/bin/activate && pytest tests/host/test_weak_typing_guard.py -q
```

Result: `1 passed in 0.51s`.

Additional diff hygiene:

```bash
git diff --check
```

Result: passed.

## Docs Decision

- No README changed.
- `dayu/host/README.md` still says public `purge_session` is structured unsupported. That remains true in P15-S1 because this slice only adds durable primitives and does not connect the public command path.
- `tests/README.md` already describes durable schema / idempotency coverage at category level and does not need a single-test-file listing update for this internal primitive slice.

## Residual Risks And Uncovered Areas

- Public `purge_session` command path remains unsupported by design; owned by later P15 slices.
- Delete matrix, precondition enforcement, payload/projection/outbox/tool trace cleanup, and audit JSONL purge line are not implemented in this slice; owned by later P15 slices.
- `PurgePreconditionSnapshot` is only a typed carrier in this slice. The actual precondition snapshot reader and precondition digest builder are intentionally deferred to the delete-matrix slice.

## Stop Status

- P15-S1 implementation complete.
- No Blocking Questions For Controller.
