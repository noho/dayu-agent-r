# WU-TOOLS-CANCEL-01 S2A1 Implementation Report

## Gate

- Work unit: `WU-TOOLS-CANCEL-01`
- Slice: `S2A1 contract / declaration / digest`
- Agent: `AgentCodex`
- Status: `ready for code review`

## Scope Implemented

- Added `dayu.contracts.tool_execution` as the typed execution capability truth:
  - `ToolExecutionMode`
  - `AsyncDirectToolExecutionCapability`
  - `ThreadBackedToolExecutionCapability` with `Literal[False]` guard
  - `ProcessBackedToolExecutionCapability`
  - `ProcessBackedToolContext`
  - `ProcessBackedToolTarget`
  - `ProcessBackedToolTargetFactory`
- Extended `ToolDefinition` with typed `execution`.
  - Default is `AsyncDirectToolExecutionCapability()`.
  - `tool(...)` accepts explicit `execution` and defaults to async direct when omitted.
  - All direct `ToolDefinition(` sites in `dayu` and `tests` scanned by the required command were migrated to explicit `execution=...`.
- Updated `ToolsDiscovery` digest projection:
  - `async_direct`: `{"mode": "async_direct", "request_abort_capable": bool}`
  - `thread_backed`: `{"mode": "thread_backed", "production_safe_non_cooperative_cancel": false}`
  - `process_backed`: `{"mode": "process_backed"}`
  - Process target factory identity is not hashed.
- Updated focused tests for declaration defaults, explicit capability, thread guard, process-backed pickle round-trip, and digest behavior.

## ToolDefinition Construction Scan

Required scan command:

```bash
rg -n "ToolDefinition\(" dayu tests
```

Migrated production sites:

- `dayu/contracts/tool_declaration.py`
- `dayu/tools/doc_tools.py`
- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/upload_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/host/tool_runtime.py`

Migrated test/helper sites:

- `tests/contracts/test_tool_declaration.py`
- `tests/runtime/test_tools_discovery.py`
- `tests/runtime/test_tools_discovery_digest.py`
- `tests/service/test_host_assembly.py`
- `tests/host/test_toolruntime_effective_bundle.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_phase6_toolruntime_integration.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_tooling_options.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/public_smoke_support.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- `tests/host/test_tool_runtime_schema_projection.py`
- `tests/host/test_toolruntime_diagnostics.py`
- `tests/host/test_per_run_tool_selection.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- `tests/tools/web/test_smoke_web_ci.py`
- `tests/tools/web/test_diagnose_web_access.py`

No scanned `dayu` / `tests` construction site was intentionally left unmigrated.

## Explicit Non-Goals Preserved

- Did not implement S2A2 declaration-backed Host capsule factory wiring.
- Did not change production dispatch capsule selection.
- Did not migrate Doc, Fins read, or Web tools to process-backed execution.
- Did not modify Engine public request, event, runner, or durable schema contracts.
- Did not modify `dayu.runtime.interruptible_process`.
- Did not add Host tool-name branches or business imports into Host internals.
- Did not make `dayu.runtime` import Host, Engine, Service, UI, or Fins.

## Validation

Commands run:

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_declaration.py tests/contracts/test_package_exports.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q
```

Result: `35 passed`.

```bash
source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/fins/test_fins_ingestion_tools.py -q
```

Result: `90 passed`, with third-party `edgar` deprecation warnings only.

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_tool_runtime_schema_projection.py -q
```

Result: `25 passed`.

```bash
source .venv/bin/activate && pytest tests/contracts -q && pytest tests/runtime/test_import_boundary.py -q
```

Result: `70 passed` and `11 passed`.

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

Combined focused rerun:

```bash
source .venv/bin/activate && pytest tests/contracts/test_tool_declaration.py tests/contracts/test_package_exports.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_ingestion_tools.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_tool_runtime_schema_projection.py -q
```

Result: `150 passed`, with third-party `edgar` deprecation warnings only.

```bash
git diff --check
```

Result: passed.

## README Decision

- Updated `tests/README.md` because tests under `tests/` gained new tool declaration execution capability coverage.
- Updated `dayu/README.md` because the public `dayu.contracts` tool declaration contract now includes `ToolExecutionCapability`.
- Checked `dayu/host/README.md`: no update required. The Host change only marks the framework `fetch_more` declaration as default async direct; it does not change implemented Host public behavior or stable developer interface.
- Checked `dayu/fins/README.md`: no update required. Fins download/upload/preprocess tools retain existing awaiting behavior; only their public tool declaration now carries the default execution capability.

## Residual Risks

- S2A1 only declares capability and digest semantics. Host production capsule selection still waits for S2A2.
- `process_backed` target factory identity intentionally does not enter digest; this matches the plan but S2A2 must ensure Host mapping tests cover completed, failed, and malformed JSON envelopes.
- Doc/Fins/Web process-backed migration is intentionally not covered here and remains assigned to later approved slices.

## Completion Signal

S2A1 implementation is ready for code review.
