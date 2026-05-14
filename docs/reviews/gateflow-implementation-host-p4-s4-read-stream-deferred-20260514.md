# Host P4-S4 Read Stream Deferred Implementation

## Scope

- Slice: P4-S4 Read APIs, Event Stream And Deferred Facade Behavior.
- Design truth: `docs/host/design.md`.
- Plan truth: `docs/host/phase4-public-api-command-path-plan.md`.
- Baseline: P4-S3 accepted slice commit `af61fe9`.

## Implemented

- Added public `get_run(host, run_id)` backed by durable Run row truth.
- Added public `stream_run_events(host, run_id, cursor, limit=None)` backed by global EventLog cursor truth.
- Added stable unsupported public functions: `retry_run`, `replay_run`, `resolve_wait`, `purge_session`.
- Updated package root exports for new public functions.
- Updated Host README for read API, stream cursor behavior, deferred functions, and Phase 4 terminal summary limitation.

## Invariants Checked

- `stream_run_events` validates target Run existence before validating limit or scanning EventLog.
- `stream_run_events` uses global `event_sequence` only; no projection checkpoint, memory state, outbox state, subscription position, session cursor, or client sequence is used.
- Empty filtered stream results still advance `next_cursor` when unrelated EventLog rows were scanned.
- Deferred public functions raise `UNSUPPORTED_OPERATION`, `retryable=False`, `detail=None`, and do not write EventLog or idempotency records.
- Terminal summary currently uses status-only fallback because Phase 4 has no typed terminal payload decoder and does not parse untyped payload JSON ad hoc.

## Review Fix Follow-up

- Accepted MiMo blocking finding and DS medium finding: missing Run must return `NOT_FOUND` even when `limit` is invalid.
- Moved public limit resolution into the read transaction after durable Run existence check.
- Added regression coverage for missing Run with `limit=0`, `limit=-1`, and `limit > HOST_EVENT_STREAM_MAX_LIMIT`.
- Preserved `INVALID_STATE` for invalid limits when the target Run exists.
- Addressed DS low finding by making the default limit test assert the actual max scanned `event_sequence` from EventLog rows instead of assuming cursor continuity.

## Validation

Local validation passed:

```bash
source .venv/bin/activate && pytest tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
```
