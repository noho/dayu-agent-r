# WU-SEMANTIC-OWNERSHIP-01 P3-H S2 implementation - AgentCodex

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Slice: `S2 - Fins direct stream and wait visible-language owner`
- Gate: implementation
- Agent: AgentCodex
- Status: implementation complete; waiting for controller validation

## Owner Boundary

- Fact producer: `FinsIngestionRuntime` remains responsible for operation kind, stage, status, counts, payload, cancellation observation, and result/error classification.
- Wait adapter: `dayu.fins.ingestion.wait_adapter` remains responsible for observation status mapping, result meta, `payload_ref`, and Host wait outcome type selection.
- Visible-language owner: `dayu.fins.direct_event_text` now owns direct result titles, direct failure messages, runtime-owned direct progress messages, and Fins wait failed/cancelled message/hint.
- Contract owner unchanged: `dayu.fins.direct_events` still owns `FinsEvent`, `FinsProgress`, and `FinsResultSummary` shape and validation.

## Changed Files

- Added `dayu/fins/direct_event_text.py`.
- Updated `dayu/fins/ingestion_runtime.py`.
- Updated `dayu/fins/ingestion/wait_adapter.py`.
- Updated `tests/fins/test_fins_ingestion_runtime.py`.
- Updated `tests/fins/test_fins_ingestion_tools.py`.
- Added this artifact.

## Implementation Summary

- Added typed Fins text helper with the required APIs:
  - `direct_result_title(...)`
  - `direct_failure_message(...)`
  - `direct_progress_message(...)`
  - `wait_failed_hint()`
  - `wait_cancelled_message()`
  - `wait_cancelled_hint()`
- Added helper-owned specific direct failure message functions for current runtime failure paths:
  - download wrote no source documents
  - preprocess completed no requested documents
  - upload returned failed status
  - upload runtime unavailable
- Replaced direct-stream result title selection in `ingestion_runtime.py` with `direct_result_title(...)`.
- Replaced runtime-owned progress messages in direct/shared execution paths with `direct_progress_message(stage=...)`.
- Replaced direct failure message literals in direct result and shared observation result construction with helper-derived messages.
- Replaced `wait_adapter.py` failed/cancelled outcome visible text with helper calls.
- Left legacy job lifecycle sidecar messages in `ingestion_runtime.py` because they are durable job/audit sidecar text, not S2 direct stream or Host wait outcome projection.

## Tests And Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`
  - Result: `213 passed, 3 warnings`
  - Warnings: existing `edgar` deprecation warnings.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py --cov=dayu.fins.direct_event_text --cov-report=term-missing -q`
  - Result: `134 passed, 3 warnings`
  - `dayu/fins/direct_event_text.py`: `85%` coverage.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: pass.

## Source Scans

- `direct_event_text.py` prohibited import scan:
  - No hits for `FinsEvent`, `FinsResultSummary`, `FinsProgress`, `FinsIngestionRuntime`, Host outcome types, storage, job store, or wait adapter/runtime imports.
  - Only allowed typed enum import was present: `FinsErrorKind`, `FinsOperationKind`, `FinsResultStatus`.
- Fins direct/wait hardcoded visible-text scan over `ingestion_runtime.py` and `wait_adapter.py`:
  - No target direct/wait message literals remain.
  - Two hits were docstring-only `RuntimeError ... 执行失败时抛出` exception descriptions; they are not projected direct/wait copy.
- Job sidecar scan:
  - Retained expected `_append_job_event_warn(...)` / job lifecycle messages: `已记录取消请求`, `job 已进入队列`, `job 已开始执行`, `job 已取消`, `job 已成功完成`, `job 已失败`, `job 状态未终结`.
  - These were not counted as moved direct/wait copy.
- Helper usage scan:
  - `ingestion_runtime.py` uses `direct_progress_message(...)`, `direct_result_title(...)`, and `direct_failure_message(...)`.
  - `wait_adapter.py` uses `wait_failed_hint()`, `wait_cancelled_message()`, and `wait_cancelled_hint()`.

## README Decision

- Read `dayu/fins/README.md`: no update. The README already documents direct stream and wait adapter boundaries; `direct_event_text.py` is an internal projection helper and does not change public Fins entrypoints or stable caller workflow.
- Read `tests/README.md`: no update. Tests changed existing Fins runtime / wait adapter assertions and did not add a new test layer, command, or maintenance rule.

## Propagation Audit

- Direct progress path:
  - Runtime produces operation kind, stage, payload, document id, and count facts.
  - `direct_event_text.direct_progress_message(stage=...)` selects runtime-owned visible progress text.
  - `_direct_progress_event(...)` constructs `FinsEvent(PROGRESS)` with helper-derived message and existing typed progress facts.
  - Service/CLI direct stream consumes the same `FinsEvent` text; no second formatter was added.
- Direct result path:
  - Runtime produces status, details, error kind, and sanitized fallback failure fact.
  - `direct_event_text.direct_result_title(...)` and `direct_failure_message(...)` select title and error message.
  - `_emit_direct_result(...)` constructs `FinsResultSummary` and `FinsEvent(RESULT)` from the same helper-derived text.
  - Service/CLI/direct consumers see the same title/error message stored in the event summary.
- Observation/wait path:
  - Observation snapshot carries status/result/error facts.
  - Wait adapter maps typed snapshot status to Host resolve outcome type and result meta.
  - `direct_event_text.wait_failed_hint()`, `wait_cancelled_message()`, and `wait_cancelled_hint()` supply LLM-facing wait failed/cancelled text.
  - Resumed tool result receives helper text; adapter no longer owns hardcoded recovery prose.
- Job sidecar path:
  - Runtime job lifecycle/audit code still owns durable job sidecar messages.
  - Destination is legacy job event/audit sidecar, not direct stream or Host wait outcome for S2.
  - These retained messages were listed separately in scans and are not claimed as fixed direct/wait copy.

## Residual Risk

- Existing source-specific download adapter progress messages remain adapter-provided inputs and are still passed through by runtime; this is outside S2 because the adapter, not runtime, produces those business progress facts.
- Legacy job lifecycle sidecar text remains in runtime by design; future work should only move it if a later owner-boundary slice proves it is projected into LLM/user-visible output beyond legacy job/audit sidecar.
- Real external Fins provider behavior was not exercised in this slice; current validation covers direct runtime, tools, Host wait polling/resolve, Service direct, and CLI direct paths with existing fixtures.
