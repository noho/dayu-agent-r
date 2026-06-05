# WU-TOOLS-01 Slice S2 Implementation

Gate: implementation  
Work unit: WU-TOOLS-01  
Slice: S2 Tool Adapter And Typed Provider Config  
Agent: AgentCodex  
Branch: phaseflow/wu-tools-01  
Plan artifact: docs/host/wu-tools-01-migration-plan.md  
Implementation artifact: docs/reviews/wu-tools-01-slice2-implementation-codex.md

## Scope Judgment

S2 的问题真实存在：当前 `ToolsDiscoveryProviderSpec` 已有 `config` 字段，但 `ConfigLoader` 与 `dayu.service.host_assembly` 没有把 provider config 传过去；同时 OLD 可靠工具是同步函数 + registry 声明，current contract 是 async `ToolCallable` + `ToolDefinition`。根因是声明 / 执行契约不一致，不是 Host / Engine 公共契约缺失。

本 slice 没有修改 `ToolDefinition`、`ToolRuntime` 或 Engine 工具执行协议。实现只落在 `dayu.tools._legacy_adapter`、runtime config pass-through、Service mapping、默认 disabled provider config 示例和对应测试 / README。

## Files Changed

- Added `dayu/tools/__init__.py`
- Added `dayu/tools/_legacy_adapter/__init__.py`
- Added `dayu/tools/_legacy_adapter/tool_contracts.py`
- Added `dayu/tools/_legacy_adapter/tool_decorator.py`
- Added `dayu/tools/_legacy_adapter/argument_validator.py`
- Added `dayu/tools/_legacy_adapter/exceptions.py`
- Added `dayu/tools/_legacy_adapter/tool_errors.py`
- Added `dayu/tools/_legacy_adapter/registry_collector.py`
- Added `dayu/tools/_legacy_adapter/definition_adapter.py`
- Modified `dayu/runtime/config_loader.py`
- Modified `dayu/service/host_assembly.py`
- Modified `dayu/config/tool_discovery.json`
- Modified `tests/runtime/test_config_loader.py`
- Modified `tests/service/test_host_assembly.py`
- Added `tests/tools/test_legacy_tool_adapter.py`
- Modified `dayu/config/README.md`
- Modified `dayu/README.md`
- Modified `tests/README.md`

## Import-Closure Inventory

OLD helper source inspected under `/Users/leo/workspace/dayu-agent` before adding adapter files:

| OLD helper | Classification | Reason |
|---|---|---|
| `dayu/engine/tools/base.py` | included | Declaration metadata behavior was needed: build tool schema, attach tags, truncate, file path params, execution context param name, display name and summary params. Reimplemented narrowly in `tool_decorator.py` using current `ToolSchema` / `ToolTruncateSpec`; no OLD registry execution copied. |
| `dayu/engine/tool_contracts.py` | included-with-rewrite | `DupCallSpec` metadata is retained internally because OLD ingestion declarations reference it later. OLD `ToolTruncateSpec` was not copied; OLD truncate mappings are converted to current `dayu.contracts.tool_schema.ToolTruncateSpec`. |
| `dayu/engine/argument_validator.py` | excluded-with-reason | OLD validator returns OLD `build_error` envelopes and imports `dayu.engine.tool_result`. S2 implemented a current-outcome validator in `dayu.tools._legacy_adapter.argument_validator` instead. |
| `dayu/engine/exceptions.py` | included-minimal | Only adapter-local `ConfigError`, `ToolArgumentError` and `FileAccessError` equivalents were needed. OLD Engine exception hierarchy and registry execution errors were not copied. |
| `dayu/engine/tool_errors.py` | included-minimal | Only `ToolBusinessError` business failure shape was needed for exception projection. Weak `Any` extra payload shape was not copied. |
| `dayu/engine/tool_registry.py` | excluded-with-reason | Explicitly forbidden. Collector is not OLD registry and owns no execution, trusted path whitelist, truncation or `fetch_more`. |
| `dayu/engine/truncation_manager.py` | excluded-with-reason | Explicitly forbidden. Current Host ToolRuntime remains truncation owner. |
| `dayu/engine/tool_result.py` / `project_for_llm` | excluded-with-reason | Explicitly forbidden. Adapter projects raw returns and exceptions directly to current `ToolCompletedOutcome` / `ToolFailedOutcome`. |
| OLD registry `fetch_more` implementation | excluded-with-reason | Explicitly forbidden. `adapt_collected_tools` filters reserved `fetch_more`; current ToolRuntime owns framework `fetch_more`. |
| `dayu/engine/tools/utils_tools.py` | excluded-with-reason | Discovered as OLD tool helper, but no Doc/Fins/Web business tools are migrated in S2. |
| OLD `dayu.log` helper | excluded-with-reason | S2 adapter does not need OLD logging compatibility. |

No blocker was found. No copied helper required OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, OLD truncate / fetch-more projection, Host / Engine runtime state, or OLD UI files.

## Implementation Notes

- `LegacyToolDeclarationCollector` exposes only `register(...)`, `register_allowed_paths(...)` and `collected_tools()`. `register_allowed_paths(...)` records call facts only; it performs no validation and is not consumed as path safety evidence.
- `tool_decorator.py` stores declaration metadata on migrated functions and builds current `ToolSchema`. It does not expose compatibility imports from OLD paths.
- `definition_adapter.py` implements `ToolPathValidationPolicy`, `ProjectedLegacyCall`, `LegacyToolConcurrencyPolicy`, argument projection, return / exception projection, and sync-to-async current callable adaptation.
- Input projection rejects unknown / missing / invalid arguments before calling migrated functions, supports defaults, integer coercion from integral JSON numbers, arrays, enums and numeric / size bounds.
- Path validation is explicit and fail-closed through `ToolPathValidationPolicy`; disallowed paths return `permission_denied`, missing paths return `file_not_found`.
- OLD ok/value envelopes are unwrapped. OLD truncation, continuation hints and fetch-more projection fields are not carried into current success values.
- OLD truncate mapping is declaration-time only and produces current `ToolTruncateSpec`; OLD `ToolTruncateSpec` is not a runtime contract.
- Default execution serializes per tool around `asyncio.to_thread`; provider-wide serialization is available through shared lock selection in `adapt_collected_tools`.
- `ToolDiscoveryProviderConfig.config` is stored as layer-neutral `Mapping[str, JsonValue]`, defaulting to `{}` when absent or `null`. ConfigLoader does not interpret Doc / Fins / Web semantics.
- `dayu/config/tool_discovery.json` now includes disabled Fins / Doc / Web provider records with valid provider-owned config examples. Disabled providers are not imported by `ToolsDiscovery`.

## Migration Principle Compliance

- No Doc/Fins/Web business tools were migrated in S2.
- No durable schema was changed.
- No current `ToolDefinition`, `ToolCallable`, `ToolRuntime`, `ToolExecutor` or Engine contract was changed.
- No OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, or OLD truncate / fetch-more projection owner was imported or instantiated.
- Adapter modules import current `dayu.contracts` only for tool contracts and remain outside Host / Engine.
- Provider config remains raw JSON at ConfigLoader and Service assembly boundaries.

## Validation

Commands run:

```bash
source .venv/bin/activate && pytest tests/tools/test_legacy_tool_adapter.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/runtime/test_tools_discovery.py
```

Result: 89 passed.

```bash
source .venv/bin/activate && pyright
```

Result: 0 errors, 0 warnings, 0 informations.

Validation notes:

- The first full target pytest run exposed that `config` had accidentally been required by exact-field validation; fixed so the field is optional and defaults to `{}`.
- The same target command also exposed an existing stale Service test assertion that expected an old English compactor prompt substring while current prompt assets are Chinese. Updated the assertion to stable current prompt signals (`compaction_request` and strict JSON output requirement) without production changes.

## README / Doc Sync Decision

- Updated `dayu/config/README.md` because `tool_discovery.json` provider schema gained optional `config`.
- Updated `dayu/README.md` because `dayu.tools` is now a stable package in the developer reading order and boundary overview.
- Updated `tests/README.md` because `tests/tools/` is a new test layer.
- Root `README.md` was not updated because no user-facing command, CLI workflow, trace/render entry or installation path changed.

## Residual Risks

- WU-TOOLS-01-R1 path safety adapter: covered by current slice at adapter contract level; provider-specific Doc fail-closed path whitelist remains covered by later approved S3.
- WU-TOOLS-01-R2 typed config adapter: ConfigLoader -> Service -> `ToolsDiscoveryProviderSpec.config` is fixed in current slice; Doc/Fins/Web provider-owned parsing remains covered by later approved S3/S4/S5.
- WU-TOOLS-01-R3 ToolDiscovery / ToolRuntime adapter: sync callable to async current callable is covered in current slice; combined ToolRuntime accept path remains covered by later approved provider/integration slices.
- WU-TOOLS-01-R4 truncation / fetch_more ownership: current slice covers declaration conversion and reserved `fetch_more` filtering; concrete migrated truncating tools remain covered by S3/S4/S5.
- WU-TOOLS-01-R5 input / response projection: adapter-level projection and outcome mapping are covered in current slice; provider-specific representative tool calls remain covered by S3/S4/S5.

No unclassified residual risk remains for S2 implementation.

## Completion Status

S2 implementation complete. Changes are left uncommitted as requested. No commit, push, PR, review, fix or re-review gate was entered.
