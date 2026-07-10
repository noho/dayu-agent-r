# WU-SEMANTIC-OWNERSHIP-01 P3-H S2 controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Slice: `S2 - Fins direct stream and wait visible-language owner`
- Accepted plan commit: `ba607309`
- Prior accepted S1 commit: `35be9dc3`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-h-s2-implementation-codex.md`

## Controller Result

Controller validation passes for S2 pending independent code review.

AgentCodex completed the planned implementation and controller validation added one boundary correction before review: process-local observation diagnostic messages such as `Observation was cancelled before activation.` and `Observation activation failed.` remain record diagnostics, but they no longer feed `FinsResultSummary.error_message`. The visible result summary now uses `direct_event_text.direct_failure_message(...)` defaults for those internal observation closeout paths.

## Changed Boundary

- `dayu/fins/direct_event_text.py` now owns Fins direct/wait visible text.
- `dayu/fins/ingestion_runtime.py` still owns direct execution facts, stage labels, status, result details, and observation state.
- `dayu/fins/ingestion/wait_adapter.py` still owns observation-to-wait outcome mapping, but consumes helper text for failed/cancelled outcome hint/message.
- `dayu/fins/direct_events.py` remains the contract-shape and validation owner for `FinsEvent`, `FinsProgress`, and `FinsResultSummary`.

## Validation Commands

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`
  - Result: `213 passed, 3 warnings`

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py --cov=dayu.fins.direct_event_text --cov-report=term-missing -q`
  - Result: `134 passed, 3 warnings`
  - `dayu/fins/direct_event_text.py`: `86%` coverage

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

- `git diff --check`
  - Result: passed

## Source Scans

- `rg -n "from dayu\\.fins\\.(ingestion_runtime|ingestion\\.wait_adapter|storage)|from dayu\\.host|from dayu\\.engine|FinsEvent|FinsResultSummary|FinsProgress|FinsIngestionRuntime|ToolResult|ToolCancelled|ResolveWait|WaitRecord|DefaultFinsRuntime|Any|object" dayu/fins/direct_event_text.py`
  - Result: no matches.

- `rg -n "error_message=.*Observation|fallback_message=.*Observation|hint=\\\"|message=\\\"Fins operation was cancelled before completion|请检查 Fins ingestion" dayu/fins/ingestion_runtime.py dayu/fins/ingestion/wait_adapter.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py`
  - Result: no matches.

- Broader observation diagnostic scan still finds `record.message = "Observation ..."` in `ingestion_runtime.py`; these are process-local observation diagnostics and are not fed to `FinsResultSummary.error_message` after the controller correction.

## README Decision

- `dayu/fins/README.md` was checked by AgentCodex. No update is required because the helper is an internal projection owner and does not change public Fins entrypoints or workflow.
- `tests/README.md` was checked by AgentCodex. No update is required because S2 updates existing Fins runtime / wait adapter assertions and does not add a new testing layer or stable test responsibility.

## Propagation Audit

- Direct progress: runtime produces typed stage and payload facts; `direct_progress_message(...)` selects visible progress text; `_direct_progress_event(...)` stores the same text in `FinsEvent.message`; Service/CLI direct consumers read that event.
- Direct result: runtime produces status, details, error kind, and sanitized fallback facts; `direct_result_title(...)` and `direct_failure_message(...)` select title/error text; `FinsResultSummary` stores the same values consumed by direct stream and observation snapshots.
- Observation/wait: process-local observation record messages remain diagnostics; terminal result summaries use helper-derived business text; wait adapter maps snapshot status to Host outcome and uses helper text for failed/cancelled hint/message.
- Job sidecar: legacy job lifecycle/audit messages remain in runtime and are not claimed as S2 direct-stream or wait-outcome fixes.

## Residual Risk

- Source-specific download adapter progress messages remain adapter-provided business inputs and pass through runtime. This is outside S2 because those messages are not runtime-owned generic direct/wait copy.
- Legacy job sidecar text remains in runtime by design. Moving it requires a later owner-boundary slice if evidence shows it is projected beyond job/audit sidecar.
- Real external Fins provider behavior was not exercised in S2; validation covers direct runtime, tools, Host wait polling/resolve, Service direct, and CLI direct paths with existing fixtures.
