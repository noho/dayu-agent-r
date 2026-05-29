# Phase 13 Slice 1 Implementation Artifact

## Gate

Phase 13 implementation.

## Slice

Slice 1 LogAuditSink JSONL.

## Plan Path

`docs/host/phase13-audit-tool-trace-outbox-plan.md`

Controller adjudication:

`docs/reviews/phase13-plan-rereview-controller-adjudication-20260529.md`

## Allowed Files

- `dayu/host/audit.py`
- `dayu/host/durable/audit.py`
- `dayu/host/durable/schema.py`
- `dayu/host/open_host.py`
- `tests/host/test_audit_sink.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/phase13-slice1-implementation-codex-20260529.md`

## Changed Files

- `dayu/host/audit.py`
- `dayu/host/durable/audit.py`
- `dayu/host/durable/schema.py`
- `dayu/host/open_host.py`
- `tests/host/test_audit_sink.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/phase13-slice1-implementation-codex-20260529.md`

## Implemented Plan Items

- Added `LogAuditSinkOptions`, `LogAuditSink`, audit JSONL line builder, and catch-up helper.
- Set consumer id to `host.audit-log-jsonl`.
- Used `ProjectionEventFilter` for `canonical_fact` only; preview events are not consumed.
- Added sink-local `host_audit_sink_markers` table and durable helper. The table is only a retry/idempotency marker, not audit truth.
- Added `line_digest` to every JSONL line and covered the minimum audit fields from the accepted plan.
- File append failures surface through `ProjectionRunner`; checkpoint does not advance and projection failure is written.
- Bumped fresh Host schema from 10 to 11 and included the audit marker table in bootstrap.
- Derived default audit path from `artifact_root / "audit" / "host-audit.jsonl"` in `open_host`.
- Added close-time composite projection flush for memory + audit without adding `OpenHostOptions` fields.

## Validation

Commands run:

```bash
source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_durable_schema.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
```

Results:

- `pytest`: 22 passed.
- `pyright`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: passed.

## Docs Decision

README not updated. This slice added an internal Host projection sink and same-layer Host tests, with no public Host API, CLI, config entry, test layer, or test running convention change. The handoff also instructed not to modify README unless proven required.

## Plan Gaps

No blocking plan gaps.

Implementation note: `ProjectionEventView` does not expose EventLog actor/source/client request fields, so the audit builder reads the matching committed EventLog row by `event_id` inside the projection transaction. This stays within allowed files and still uses typed EventLog durable data, not raw EngineEvent or Service/UI state.

## Residual Risks

- Accepted plan residual: JSONL append and SQLite marker/checkpoint cannot be truly atomic across media. A crash after file append but before marker/checkpoint commit can leave a duplicate physical JSONL line for the same `event_id`; Host truth is unaffected.
- Audit close flush is internal projection work. It does not change command path success, EventLog append semantics, Run/Attempt state, terminal transaction, or `watch_session_events(...)`.
- Audit query UI, external audit system, purge tombstone audit record, purge cleanup, and retention matrix remain non-goals for later phases.

## Stop Status

No stop condition hit. No Engine, Service, UI, Fins, public options, command path, EventLog append semantics, Run/Attempt governance, terminal transaction, or live watch semantics were modified.
