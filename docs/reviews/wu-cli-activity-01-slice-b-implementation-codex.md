# WU-CLI-ACTIVITY-01 Slice B implementation artifact

## Gate / scope

- Gate: implementation Slice B.
- Agent: AgentCodex.
- Scope: Service activity callback consumes Host public activity.
- Non-goals kept: no CLI renderer/composer, no prompt/interactive key handling, no Host durable internals, no EventLog payload parsing, no ToolBundle / Tool Trace access, no Host / Engine API changes.

## Changed files

- `dayu/service/entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime.py`
- `docs/reviews/wu-cli-activity-01-slice-b-implementation-codex.md`

Pre-existing unrelated local change observed and left untouched:

- `docs/host/issues-implementation-control.md`

## Implementation decisions

- Added typed Service DTOs: `EntrypointActivityKind`, `EntrypointActivityStatus`, `EntrypointActivitySeverity`, `EntrypointActivityCounts`, `EntrypointActivity`, and `EntrypointActivityCallback`.
- Extended `submit_entrypoint_turn_and_wait(...)` with optional `on_activity`, defaulting to `None`, so existing callers remain valid.
- `_drain_available_watcher_items(...)` now forwards only non-terminal `HostEvent.activity` through a Service projection helper.
- Service activity identity fields come from public `HostEvent.run_id`, `HostEvent.event_sequence`, and `HostEvent.dedupe_key`; display fields come from `HostEvent.activity`.
- `HostEvent.event_class` and `HostEvent.event_type` are not used for Service UI branching.
- Generic Host progress without `activity` is suppressed.
- Activity callback is deduped by activity dedupe key.
- Watcher drain failure now emits one bounded `WATCHER_DIAGNOSTIC` activity when a callback is provided, while preserving existing terminal outbox fallback behavior and watcher failure terminal diagnostics.
- Session-wide live events are filtered by the accepted run id before activity callback, preventing unrelated same-session run activity from reaching the current turn.

## Tests / validation

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py -q`
  - Result: 30 passed, 3 existing third-party edgar deprecation warnings.
- `source .venv/bin/activate && python -m pyright dayu/service tests/service`
  - Result: 0 errors, 0 warnings, 0 informations. Pyright reported a newer version is available.
- `git diff --check`
  - Result: clean.

## README decision

- Read `tests/README.md`; it has no dedicated Agent update constraint and already describes Service entrypoint runtime tests. The new tests extend the same category, so no README change was needed.
- Read `dayu/service/README.md`; it describes entrypoint runtime terminal observation and Service public boundary. Slice B adds a callback parameter but does not change CLI behavior yet, and `dayu/service/README.md` is not listed as an AGENTS trigger. No README change was made.

## Residual risks

- CLI still does not render activity; that belongs to later slices.
- No TTY / non-TTY renderer behavior was validated in this slice.
- Callback exceptions are not swallowed, matching existing `on_run_accepted` behavior. A later renderer slice should keep renderer callbacks simple and deterministic.
