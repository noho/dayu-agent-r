# Phase 13 Slice 2 Implementation Report

## Gate

Phase 13 implementation。

## Slice

Slice 2 Tool Trace Hot JSON / Cold JSONL。

## Plan Path

`docs/host/phase13-audit-tool-trace-outbox-plan.md`

Schema clarification: `docs/reviews/phase13-schema-version-controller-clarification-20260529.md`

## Allowed Files

- `dayu/host/tool_trace.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/durable/schema.py`
- `dayu/host/open_host.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/phase13-slice2-implementation-codex-20260529.md`

## Changed Files

- `dayu/host/tool_trace.py`
- `dayu/host/durable/tool_trace.py`
- `dayu/host/durable/schema.py`
- `dayu/host/open_host.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/phase13-slice2-implementation-codex-20260529.md`

## Implemented Plan Items

- Added `ToolTraceSinkOptions`, `ToolTraceProjectionConsumer`, cold JSONL line writer, catch-up helper, and consumer id `host.tool-trace`.
- Added durable `host_tool_trace_hot` projection table, indexes, row codec, idempotent insert, and internal query helpers by run, tool call id, provider request id, and diagnostic ref.
- Bumped Host durable schema from 11 to 12 for fresh schema bootstrap; no compatibility migration or old-store compatibility path was added.
- Wired Tool Trace catch-up into `open_host` close projection flush using default path `artifact_root / "tool-trace" / "tool-trace-cold.jsonl"` without adding public `OpenHostOptions` fields.
- Implemented typed whitelist extraction for named canonical, diagnostic, and usage projection signal events. `ENGINE_EVENT_DIAGNOSTIC` is only projected when current typed payload exposes `provider_request_id`; otherwise it is skipped instead of treating arbitrary diagnostic payload as trace data.
- Hot rows and cold lines carry event/session/run/attempt/execution identity. Operation context refs/digest are stored in hot `trace_summary_json` and cold JSONL when present.
- Cold JSONL or hot row failure stays inside projection runner failure handling and does not alter Host governance truth.

## Validation

Commands run:

```bash
source .venv/bin/activate && pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_durable_schema.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
```

Results:

- `pytest`: `25 passed in 0.36s`
- `pyright`: `0 errors, 0 warnings, 0 informations`
- `git diff --check`: passed with no output

## Docs Decision

README was not updated. This slice adds internal Host projection/storage/query helpers and no public Host API, CLI, config, or user workflow change. The slice handoff also explicitly says not to modify README unless required; no such requirement was found.

## Plan Gaps

- Current committed `ENGINE_EVENT_DIAGNOSTIC` payloads do not expose a typed `engine_event_type` field. The implementation therefore does not infer engine event type from arbitrary diagnostic payload; it only admits those diagnostics when `provider_request_id` is present. This still covers the provider diagnostic query requirement without requiring Engine or ToolRuntime contract changes.
- `USAGE_REPORTED` exists as `projection_signal` in current code, not `canonical_fact`. The projection consumes the current typed EventLog class rather than inventing a compatibility path.

## Residual Risks

- Cross-medium exactly-once remains non-goal: SQLite hot row/checkpoint and cold JSONL append cannot be made atomic across media. A crash after cold append but before transaction commit can physically duplicate a cold JSONL event line on retry. Host truth is unaffected; analyze consumers must de-duplicate by `event_id`.
- Tool Trace is diagnostic projection only. Loss, lag, or corruption of hot/cold trace affects diagnostics and query completeness only; it must not be used for recovery, resume, memory, or Run state migration.
- Diagnostic whitelist remains intentionally narrow. Diagnostics without typed provider/tool refs are skipped until a later contract explicitly exposes the needed fields.

## Stop Status

No stop condition was hit. Slice 2 implementation is complete for code review; no commit, push, PR, README update, or out-of-scope file modification was performed.
