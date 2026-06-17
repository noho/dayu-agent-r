# WU-CLI-ACTIVITY-01 Slice A implementation artifact

## Gate / scope

- Gate: implementation Slice A.
- Agent: AgentCodex.
- Scope: Host public activity event contract only.
- Non-goals kept: no Engine / Service / CLI changes; no durable schema migration; no EventLog canonical fact semantic change; no Host / Engine state-machine change.

## Changed files

- `dayu/host/api.py`
- `dayu/host/read_api.py`
- `dayu/host/admission.py`
- `dayu/host/__init__.py`
- `tests/host/test_public_host_event.py`
- `tests/host/test_public_open_host_options.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_context_compact_events.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-cli-activity-01-slice-a-implementation-codex.md`

`dayu/host/__init__.py` was touched only because Slice A required public exports for the new Host public activity types; the package export tests lock that boundary.

## Implementation decisions

- Added `HostActivityKind`, `HostActivityStatus`, `HostActivitySeverity`, `HostActivityCounts`, and `HostActivityView` as frozen slots public API types with Chinese docstrings and validation.
- Extended `HostEvent` with `event_class`, `event_type`, and `activity`. `event_class` reuses the existing `HostEventClass`; `event_type` is copied directly from the EventLog row. Terminal payload validation remains strict.
- Kept non-terminal lifecycle classification as `HostEventKind.PROGRESS`; detailed display semantics now live in `HostActivityView`.
- Implemented read-side activity projection as an allowlist in `dayu/host/read_api.py`.
- `CONTENT_DELTA` and `REASONING_DELTA` preserve public identity but always project `activity=None`.
- Unknown non-terminal events preserve `event_class` / `event_type` and project `activity=None`.
- For non-terminal activity payload corruption, projection degrades to `activity=None` while preserving event identity. Terminal events still use existing strict validation.
- Admission now freezes `effective_tool_display_names` inside `USER_INPUT_ACCEPTED.effective_tool_set` from selected `ToolDefinition.display.name`. Tools without display metadata are omitted from the mapping; read projection falls back to stable `tool_name`.
- This is a payload shape extension only. No durable schema migration or old-library compatibility reader was added.

## Tests / validation

- `source .venv/bin/activate && pytest tests/host/test_public_host_event.py tests/host/test_public_open_host_options.py tests/host/test_package_exports.py tests/host/test_host_activity_event_projection.py tests/host/test_watch_session_events.py tests/host/test_context_compact_events.py -q`
  - Result: 71 passed.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: 0 errors, 0 warnings.
- `git diff --check`
  - Result: clean.

## Docs decision

- Updated `dayu/host/README.md` because Host public `HostEvent` and activity view contract changed.
- Updated `tests/README.md` because Host event / admission test coverage changed.
- Checked `dayu/README.md`; no update needed because the overall cross-package architecture and dependency direction did not change.

## Residual risks

- Covered by later approved slice: Service / CLI do not consume `HostEvent.activity` yet; that belongs to Slice B and later CLI slices.
- Covered by later approved slice: exact CLI rendering wording, dedupe behavior, and stderr / TTY policy are not implemented in Slice A.
- Current slice accepted risk: activity titles and summaries are intentionally minimal Host-owned display semantics. Future UI copy changes should occur through Service / CLI projection rather than exposing raw EventLog payloads.

## Completion status

Slice A implementation is complete and ready for code review gate. No commit, push, PR, or review gate was performed.
