# WU-TOOLS-01-F01 Slice S4 Implementation Artifact

## Gate / Scope

- Gate: implementation only.
- Work unit: `WU-TOOLS-01-F01`.
- Slice: `S4 - Download / Preprocess Awaiting Tool Providers`.
- Branch observed: `host-wu-tools-01-f01`.
- Scope boundary: only S4 was implemented. No code review, fix gate, re-review, commit, push, PR, Host / Engine / Service / ToolDiscovery contract change, CLI, status/cancel polling tool or real network downloader was entered.

## First-principles Judgment

The S4 motivation is valid. A production Fins Agent cannot keep ingestion enablement hidden behind the read provider after S1-S3 added a shared ingestion runtime. The correct minimal behavior is to expose download and preprocess as independent provider groups that adapt durable runtime job starts into `ToolAwaitingOutcome`, while keeping read tools read-only.

This is not a ToolDiscovery shape problem. `ToolsDiscoveryProviderOutput` already carries provider identity, source refs and tool definitions, and `ToolDefinition.callable` can return `ToolAwaitingOutcome`. S4 therefore does not need provider-specific wait adapter objects or Host/Engine contract changes.

## Direct Code Evidence

- `dayu/fins/service_runtime.py` already exposes `DefaultFinsRuntime.create(workspace_root=...)` and `get_ingestion_runtime()`.
- `dayu/fins/ingestion_runtime.py` already exposes `FinsIngestionRuntime.start_download(...)`, `start_preprocess(...)`, `FinsIngestionJobStart`, durable workspace-derived job store, and `FinsIngestionOperationKind`.
- Before S4, `dayu/fins/tools/provider.py` still parsed `include_ingestion_tools` and raised a fail-closed error, so ingestion could not be discovered through the target independent provider shape.
- `dayu/runtime/tools_discovery.py` already supports multiple explicit providers and reports distinct provider ids, spec ids, source refs and tool names.
- `dayu/contracts/tool_outcome.py` and `dayu/contracts/tool_await.py` already define `ToolAwaitingOutcome` with `ToolAwaitKind.EXTERNAL_JOB`, so tool callables can expose durable external jobs without blocking for completion.

## Changed Files / Key Design

- `dayu/fins/tools/provider.py`
  - Kept read provider focused on read tools.
  - Removed `include_ingestion_tools` parsing and fail-closed ingestion branch.
  - Promoted workspace-root parsing to `parse_fins_workspace_root_config(...)` for the independent Fins providers.

- `dayu/fins/tools/download_provider.py`
  - Added independent download provider with provider id `financial-download-tools`, version `fins-download-tools-provider-v1`, and source id `dayu.fins.tools.download_provider`.
  - Required explicit absolute `workspace_root`.
  - Call path: provider spec -> `DefaultFinsRuntime.create(...)` -> `get_ingestion_runtime()` -> download tool definition.

- `dayu/fins/tools/preprocess_provider.py`
  - Added independent preprocess provider with provider id `financial-preprocess-tools`, version `fins-preprocess-tools-provider-v1`, and source id `dayu.fins.tools.preprocess_provider`.
  - Required explicit absolute `workspace_root`.
  - Call path mirrors download provider.

- `dayu/fins/tools/download_tools.py`
  - Added `start_fins_download` tool definition.
  - Tool arguments are parsed into `FinsDownloadRequest`.
  - Callable calls `runtime.start_download(...)` and converts returned `FinsIngestionJobStart` to `ToolAwaitingOutcome` with `ToolAwaitKind.EXTERNAL_JOB`.
  - Argument or pre-awaiting startup errors are returned as `ToolFailedOutcome`.

- `dayu/fins/tools/preprocess_tools.py`
  - Added `start_fins_preprocess` tool definition.
  - Tool arguments are parsed into `FinsPreprocessRequest`.
  - Callable calls `runtime.start_preprocess(...)` and converts returned `FinsIngestionJobStart` to `ToolAwaitingOutcome` with `ToolAwaitKind.EXTERNAL_JOB`.
  - Argument or pre-awaiting startup errors are returned as `ToolFailedOutcome`.

- `dayu/fins/tools/__init__.py`
  - Kept `discover_tools` as the read provider entry.
  - Added explicit `discover_download_tools` and `discover_preprocess_tools` exports.

- `tests/fins/test_fins_ingestion_tools.py`
  - Added independent discovery tests for read, download and preprocess providers.
  - Asserted distinct provider ids, spec ids, source refs and tool names.
  - Asserted download/preprocess tool calls return `ToolAwaitingOutcome` with `EXTERNAL_JOB`.
  - Asserted provider-created runtime instances converge on the same workspace-derived job store by reading returned job ids through a fresh `DefaultFinsRuntime`.
  - Asserted invalid arguments return `ToolFailedOutcome` before job creation.
  - Asserted ingestion tool schemas do not expose Host internals, digest, cursor, raw job record wording or tool call ids.

- `tests/fins/test_fins_storage_provider.py`
  - Replaced old fail-closed ingestion test with a read-provider-only assertion: legacy `include_ingestion_tools=true` does not enable ingestion tools through the read provider.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_storage_provider.py tests/runtime/test_config_loader.py -q
```

Result: `56 passed, 3 warnings`.

Passed:

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

## README Sync Decision

- Updated `dayu/fins/README.md` because `dayu/fins/` changed and the previous stable statement said download/preprocess providers were not implemented.
- Updated `tests/README.md` because `tests/fins/` changed and the old testing description still described ingestion tools as fail-closed.
- No root README update was made because S4 adds provider-level runtime wiring only; it does not add CLI or user-facing command workflows.
- No `dayu/engine/README.md`, `dayu/host/README.md`, `dayu/config/README.md` or `dayu/README.md` update was needed because S4 did not change Engine/Host contracts, default config schema, layering, or Service assembly.

## Residual Risks / Blockers

- Host wait adapter / Service composition-root wiring is not implemented in S4 by scope. Download/preprocess tool callables correctly return `ToolAwaitingOutcome`, but Host acceptance still requires later wiring.
- Real SEC / CN / HK network download adapters remain out of scope. The runtime still returns unsupported-source terminal failure when no adapter is available.
- No status/cancel polling tools were added by design; wait/resume/cancel governance remains Host-owned.
- No blocker was hit. The stop condition did not trigger because `ToolsDiscovery` did not need to carry provider-specific wait adapter objects.
