# WU-TOOLS-01-F01-03 Slice 5 Implementation - AgentCodex

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Slice: `Slice 5: Upload Awaiting Tool, Provider, Wait Adapter, And Service Assembly`
- Objective: expose production upload as an awaiting Fins tool and bind it to existing Host wait-resume assembly.
- Non-goals preserved: no OLD upload business rule rewrite, no upload workflow copy in tool/provider, no Host wait schema change, no CLI/CI, no GitHub Issue update, no download/preprocess behavior change.

## What Changed

- Added `dayu/fins/tools/upload_tools.py`:
  - `UPLOAD_TOOL_NAME = "start_fins_upload"`.
  - `FinsUploadToolCallable`.
  - `build_fins_upload_tool(...)`.
  - Typed upload argument parser for filing/material requests.
  - Provider-configured local path allowlist and non-empty file validation before durable job creation.
- Added `dayu/fins/tools/upload_provider.py`:
  - provider id `financial-upload-tools`.
  - source id `dayu.fins.tools.upload_provider`.
  - parses absolute `workspace_root` and non-empty absolute `allowed_upload_roots`.
  - constructs `DefaultFinsRuntime.get_ingestion_runtime()` and delegates to `build_fins_upload_tool(...)`.
- Extended `dayu/fins/tools/_ingestion_tool_helpers.py` with typed integer argument readers used by upload parsing.
- Extended `dayu/fins/ingestion/wait_adapter.py`:
  - `FINS_UPLOAD_AWAITING_TOOL_NAME`.
  - `FINS_SUPPORTED_AWAITING_TOOL_NAMES` now includes download, preprocess, and upload.
- Extended `dayu/fins/ingestion/__init__.py` so the existing Fins ingestion assembly boundary exports the upload awaiting tool name together with download/preprocess names.
- Extended `dayu/service/host_assembly.py` recognition:
  - provider id `financial-upload-tools`.
  - import path `dayu.fins.tools.upload_provider:discover_tools`.
  - source id `dayu.fins.tools.upload_provider`.
  - existing workspace consistency and duplicate binding checks now cover upload.
- Added disabled default provider config in `dayu/config/tool_discovery.json`.
- Updated tests in:
  - `tests/fins/test_fins_ingestion_tools.py`
  - `tests/service/test_host_assembly.py`
- Updated README facts in:
  - `dayu/fins/README.md`
  - `dayu/config/README.md`
  - `tests/README.md`
  - `dayu/README.md`

## Data Flow

`ToolsDiscovery -> upload_provider.discover_tools -> DefaultFinsRuntime.get_ingestion_runtime -> build_fins_upload_tool -> ToolRuntime executes callable -> FinsIngestionRuntime.start_upload -> ToolAwaitingOutcome -> FinsIngestionWaitPollAdapter poll/abandon`

The tool/provider layer only parses arguments, validates local upload path boundaries, calls shared runtime start, and maps start errors to current tool outcomes. SEC/CN/HK upload action, Docling conversion, source document create/update/delete/skip/overwrite, company meta, and source/blob writes remain behind the Slice 4 production upload runner and migrated pipeline/service code.

## Invariants

- `start_fins_upload` returns `ToolAwaitingOutcome` after durable Fins job creation; it does not wait for upload conversion or storage writes.
- Argument and path errors return `ToolFailedOutcome` before job creation.
- Start cancellation returns `ToolCancelledOutcome`.
- `OSError` during job creation returns `fins_upload_start_failed`.
- Unexpected start exceptions return `fins_upload_start_failed`.
- Upload provider fails closed when enabled without absolute `workspace_root` or without non-empty absolute `allowed_upload_roots`.
- Upload files must be non-empty strings, expanded/resolved, existing files, and inside an allowed upload root.
- `auto` / `create` / `update` require non-empty `files`; `delete` rejects `files`.
- Tool schema does not expose Host/EventLog/wait-id/tool-call/digest/cursor/raw job path/internal governance terms.
- Service assembly binds download/preprocess/upload Fins awaiting tools through the existing wait adapter registry and fails before `open_host` on workspace mismatch or duplicate upload binding.

## README Decision

- `dayu/fins/README.md`: updated because upload awaiting provider and wait adapter binding are now implemented facts.
- `dayu/config/README.md`: updated because default `financial-upload-tools` provider config landed.
- `tests/README.md`: updated because tests now cover upload provider/tool/assembly paths.
- `dayu/README.md`: updated because the top-level Fins and tool/wait-resume summary now includes upload awaiting capability.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py -q`
  - AgentCodex result before Controller补充空文件校验: `72 passed, 3 warnings`
  - Controller result after补充空文件校验: `73 passed, 3 warnings`
  - Warnings: existing `edgar` deprecation warnings.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed.
- Targeted weak typing scan over touched Slice 5 production/test files:
  - `rg -n "from typing import .*Any|\bAny\b|: object\b|-> object\b|\bobject\s*\]" ...`
  - Result: no matches.
- Boundary scan:
  - Fins upload tool/provider/helper files contain no `dayu.host`, `dayu.engine`, `dayu.ui`, `dayu.service`, or `dayu.cli` imports.
  - Service assembly does not import concrete Fins tool provider modules; it only recognizes provider id/import-path/source-id strings and imports the wait adapter assembly boundary.
- Tool schema scan:
  - download/preprocess/upload schemas contain no `Host`, `EventLog`, `wait_id`, `tool_call_id`, `digest`, `cursor`, `raw job path`, `raw job record`, or `internal governance` terms.

## Residual Risks / Blockers

- No blocker.
- Broader upload runtime failure-path matrix remains outside this Slice, as previously deferred.
- Crash recovery and prepare/activate hardening for long Fins jobs remain tracked by existing WAIT / Issue 129 follow-up scope; this Slice does not introduce a private Host-like state machine.
- Real upload conversion behavior remains owned by Slice 4 production runner and migrated OLD workflow; Slice 5 only exposes the awaiting start path.

## Completion

- Upload awaiting tool/provider implemented: yes.
- Controller补充了 empty upload file must fail before durable job creation 的实现与测试: yes.
- Host wait adapter assembly binding implemented: yes.
- Default config provider added disabled: yes.
- Validation complete: yes.
- Commit created: no.
