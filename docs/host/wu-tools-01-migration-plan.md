# WU-TOOLS-01 Migration Plan

Gate: plan  
Work unit: WU-TOOLS-01  
Type: migration / cross-layer tool contract work unit  
Status: ready for plan re-review

## Goal / Motivation / Success Signal

Goal: migrate the reliable OLD Doc tools, Fins tools and Web tools into `dayu-agent-r` as one work unit, with one shared document foundation owner and current `ToolsDiscovery` / `ToolRuntime` integration.

Motivation: the work unit is real and should stay single. OLD Doc tools, Fins and Web tools all depend on the OLD `engine/processors/*` document chain and `dayu/docling_runtime.py`. Splitting issue-82 / issue-97 / issue-98 would duplicate processor placement, Docling runtime ownership, provider adapters, and tests.

Success signal:

- `ToolsDiscovery` can explicitly discover Doc / Fins / Web providers and return one `ToolBundle`.
- Host-owned `ToolRuntime` executes representative migrated tools through current async `ToolCallable` and accept barrier.
- Engine only consumes `tool_schemas` and `ToolExecutor`; Engine does not import `ToolDefinition`, tools, Fins, Web, Doc tools or storage.
- Fins document access goes through `dayu.fins.storage` repositories only.
- OLD class / function signatures and OLD function bodies are not modified; only imports, package location, and outer adapters / providers / assembly code change.
- Deterministic tests cover shared processors, Doc tools, Fins storage / provider path, Web URL safety / fetch-search adapter path, `ToolsDiscovery`, `ToolRuntime` accept path, import boundaries and pyright.

## First-Principles Judgment

The correct migration shape is not “rewrite tools for the new architecture”. The old tools already encode domain behavior: document sectioning, table refs, Docling JSON behavior, financial statement routing, SEC/CN filing storage, search ranking, URL safety, fetch fallback and diagnostics. Rewriting those behaviors would increase risk and create new unverified semantics.

The root mismatch is architectural, not business logic:

- OLD registered sync functions in a `ToolRegistry`.
- NEW exposes async single-tool `ToolCallable` values inside `ToolDefinition`.
- OLD `ToolRegistry` owned registration, path whitelist, argument validation, truncation, `fetch_more`, error envelopes and execution.
- NEW `ToolRuntime` owns batch execution, truncation, `fetch_more`, duplicate governance, awaiting and Host accept barrier.

Therefore implementation should migrate OLD business code unchanged and build a narrow adapter boundary that:

- collects OLD decorated functions and schemas;
- converts OLD schema / truncate metadata to current contracts;
- executes OLD sync callables from an async `ToolCallable`;
- maps OLD tool result envelopes to current `ToolCompletedOutcome` / `ToolFailedOutcome`;
- keeps path safety and config parsing outside migrated Doc tool functions;
- does not migrate OLD registry execution, OLD truncation manager, or OLD `fetch_more`.

This is not over-designed because it adds one adapter surface for the one real contract mismatch and avoids three separate Doc/Fins/Web rewrites.

## Direct Code Evidence Inspected

Current `dayu-agent-r` evidence:

- `dayu/runtime/tools_discovery.py`: `ToolsDiscovery` only resolves explicit provider callables or package entry points, calls provider specs, aggregates `ToolDefinition`, rejects duplicate/reserved tool names, and returns `ToolBundle` plus source refs.
- `dayu/contracts/tool_declaration.py`: `ToolDefinition` contains `schema`, async single-tool `ToolCallable`, optional `truncate`, display and tags; `ToolCallable.__call__` is async and receives `ToolCallRequest` plus `BatchToolExecutionContext`.
- `dayu/contracts/tool_executor.py`: Engine calls only `ToolExecutor.execute(BatchToolExecutionRequest)`.
- `dayu/host/tool_runtime.py`: `DefaultToolRuntimeFactory` builds an effective bundle, injects framework `fetch_more` only when the current truncation manager is enabled, dispatches `definition.callable`, applies ToolRuntime truncation, then writes `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` through accept barrier.
- `dayu/engine/agent.py`: successful tool results expose `ToolResultSuccess.value` directly to the LLM; an adapter must not return the OLD `{"ok": true, "value": ...}` envelope as the new value.
- `dayu/runtime/config_loader.py` and `dayu/service/host_assembly.py`: config currently parses tool provider identity and location but drops provider `config` when building `ToolsDiscoveryProviderSpec`.
- `dayu/config/tool_discovery.json`: default `financial-tools` provider points to `dayu.fins.tools:discover_tools`, is disabled and has no provider config.
- `dayu` currently has no `dayu/fins`, no `dayu/documents`, and no migrated Doc/Web tools.

OLD source evidence:

- `/Users/leo/workspace/dayu-agent/dayu/engine/tool_registry.py`: OLD registry owns `register_allowed_paths`, fail-closed path validation for `file_path_params`, argument validation, sync execution, OLD truncation and OLD `fetch_more`.
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/doc_tools.py`: `register_doc_tools(registry, limits=None, allowed_paths=None, allow_file_write=False, allowed_write_paths=None, timeout_budget=None)` registers `list_files`, `get_file_sections`, `search_files`, `read_file`, `read_file_section`; functions declare `file_path_params` but do not manually validate paths.
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/base.py`: OLD `@tool` stores schema, tags, truncate, dup-call, display, summary params and `file_path_params` on the function.
- `/Users/leo/workspace/dayu-agent/dayu/contracts/tool_configs.py`: OLD `DocToolLimits`, `FinsToolLimits`, `WebToolsConfig` and builders exist.
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_tools.py` and `web_*.py`: actual Web tools are `search_web` / `fetch_web_page`, with URL safety, provider selection, timeout budget, Playwright fallback, challenge detection and Docling conversion dependencies.
- `/Users/leo/workspace/dayu-agent/dayu/fins`: Fins service, storage, processors, pipelines, downloaders and tools exist under this package; Fins processors import OLD `dayu.engine.processors.*`.
- `/Users/leo/workspace/dayu-agent/dayu/fins/storage/repository_protocols.py`: Fins repository protocols are the storage boundary.
- `/Users/leo/workspace/dayu-agent/dayu/docling_runtime.py`: Docling runtime has backend/device fallback and is shared by Fins and Web conversion paths.
- `/Users/leo/workspace/dayu-agent/dayu/web`: inspected as OLD UI / FastAPI / Streamlit files only; excluded from Web tools migration.

## Non-Goals / Scope Boundary

Non-goals:

- No implementation in this gate.
- No commit, push or PR.
- No migration of OLD `/Users/leo/workspace/dayu-agent/dayu/web` UI files.
- No rewrite of Doc / Fins / Web business behavior.
- No modification of migrated OLD class / function signatures.
- No modification of migrated OLD function bodies.
- No Host scan/import of concrete business tool implementations.
- No Engine import of tool implementations, `ToolDefinition`, `dayu.fins`, `dayu.documents`, Web tools, Doc tools or storage.
- No Fins document access from Host, Engine, runtime or Web/Doc tools.
- No hidden cwd/env fallback for business tool roots, path whitelist or network policy.
- No schema compatibility with old DB/config unless explicitly required later.

Scope:

- Move shared document processors and Docling runtime to one package.
- Move Doc tools, Fins, and Web tools from OLD source scopes.
- Add adapter/provider/assembly code required to map OLD reliable sync tools to current async tool contract.
- Add typed provider config support needed by these providers.
- Add focused tests and README updates required by AGENTS.md trigger rules during implementation.

## Design Document Alignment

Host boundary:

- Host remains the governance truth for lifecycle, ToolRuntime execution, truncation, duplicate governance, awaiting, accepted facts and Tool Trace.
- Host receives an already discovered `ToolBundle` through construction-time assembly. It does not scan modules or import Doc/Fins/Web implementations.
- Tool results enter Host accept barrier as current `ToolExecutionOutcome` values.

Engine boundary:

- Engine only receives `tool_schemas` and `ToolExecutor` from Host. It does not consume `ToolDefinition`, provider config, storage or tool implementations.
- Engine must not regain OLD `ToolRegistry`, processors or tools.

ToolsDiscovery:

- `dayu.runtime.tools_discovery` stays layer-neutral. It carries provider `config` as JSON through existing `ToolsDiscoveryProviderSpec.config`, but it must not interpret Doc/Fins/Web semantics.
- Providers live outside `dayu.runtime` and return `ToolsDiscoveryProviderOutput`.

ToolRuntime:

- ToolRuntime remains the owner of batch execution, current truncation and `fetch_more`.
- Migrated providers must not expose OLD registry `fetch_more` as a business tool because current discovery reserves that name.
- Migrated tools that need truncation must declare current `dayu.contracts.tool_schema.ToolTruncateSpec`. The adapter only collects and forwards current `ToolTruncateSpec` metadata.
- OLD `ToolRegistry`, OLD `TruncationManager` and OLD `fetch_more` business implementation must not be migrated.

`dayu.runtime`:

- No shared document foundation code goes into `dayu.runtime`; document parsing and Docling conversion are not generic runtime primitives.
- `dayu.runtime` must not import `dayu.fins`, Web tools, Doc tools, Host, Engine or Service.

`dayu.fins.storage`:

- Fins storage protocols and filesystem implementations migrate under `dayu.fins.storage`.
- Fins tools and services access financial documents only through these repositories.
- Shared `Source` and processor types should live in shared document foundations, so storage can depend on document foundation types without depending on Engine.

## Package Placement Decisions

Shared document foundations:

- Place under `dayu/documents/`.
- Include migrated OLD `engine/processors/*` under `dayu/documents/processors/`.
- Include migrated OLD `docling_runtime.py` as `dayu/documents/docling_runtime.py`.
- Reason: these are document-domain foundations reused by Doc tools, Fins and Web tools. They are not Engine state machine code and not generic runtime infrastructure.

Doc tools:

- Place migrated Doc tool implementation under `dayu/tools/doc_tools.py`.
- Place provider under `dayu/tools/doc_provider.py`.
- Reason: Doc tools are business tool implementations outside Host/Engine. The provider is the current ToolDiscovery integration point.

Web tools:

- Place migrated Web implementation under `dayu/tools/web/`:
  - `web_tools.py`
  - `web_fetch_orchestrator.py`
  - `web_search_providers.py`
  - `web_challenge_detection.py`
  - `web_http_encoding.py`
  - `web_http_session.py`
  - `web_playwright_backend.py`
  - `web_recovery.py`
- Place provider under `dayu/tools/web/provider.py` and package callable `dayu.tools.web:discover_tools`.
- Reason: Web tools are not UI. OLD `/dayu/web` is excluded.

Fins:

- Place migrated OLD `/dayu/fins` under current `dayu/fins`.
- Keep storage under `dayu/fins/storage`.
- Add provider callable `dayu.fins.tools:discover_tools` or `dayu.fins.tools.provider:discover_tools`.
- Reason: Fins is the financial domain package; Host/Engine do not depend on it, but ToolsDiscovery can import it only through explicit provider configuration at assembly time.

Adapter:

- Place OLD-to-NEW adapter under `dayu/tools/_legacy_adapter/`.
- This package contains only declaration-time helpers needed by migrated tool declarations:
  - `tool_decorator.py`: replacement `tool(...)` decorator that stores metadata on the function.
  - `tool_contracts.py`: current `ToolTruncateSpec` / `ToolTruncationStrategy` imports plus `DupCallSpec` only when import-closure inventory finds migrated declarations that still reference duplicate-call metadata; it must not define or copy OLD `ToolTruncateSpec`.
  - `argument_validator.py`, `exceptions.py`, `tool_errors.py`: only the minimal helper/error code needed by adapter input and response projection.
  - `registry_collector.py`: declaration collector described in S2.
  - `definition_adapter.py`: current `ToolDefinition` adapter described in S2.
- Any additional OLD helper file is forbidden until an implementation slice writes an import-closure inventory classifying it as included, excluded-with-reason, or blocker.
- The new registry collector exists only to collect decorated tool functions, schema metadata, tags, display metadata, summary params, path-param labels and current truncate declarations. It must not copy OLD `ToolRegistry` execution, OLD `TruncationManager`, OLD `fetch_more`, path whitelist enforcement, or OLD truncate / fetch-more projection behavior.
- It must not be exported from `dayu.engine`, `dayu.host`, `dayu.runtime` or `dayu.contracts`.
- It must not be a compatibility re-export of old import paths. Migrated imports point to the new adapter package explicitly.

This respects `UI -> Service -> Host -> Engine` because concrete tools sit outside Engine and enter Host only through Service/runtime assembly. `dayu.runtime` remains layer-neutral.

## Contract / Schema / State / Public Interface Changes

No durable Host schema change.

No Engine public interface change.

No Host public command/request/response dataclass change.

No `ToolDefinition` / `ToolCallable` shape change.

Required config and assembly changes:

- Add `config: Mapping[str, JsonValue]` to `ToolDiscoveryProviderConfig`.
- Update `ConfigLoader` `tool_discovery.providers.*` parser to accept an optional `config` JSON object, default `{}`.
- Update `dayu/service/host_assembly.py::_tool_discovery_specs` to pass `provider_config.config` into `ToolsDiscoveryProviderSpec.config`.
- Update config tests and service assembly tests to assert provider config survives into `ToolsDiscoveryProviderSpec`.

Provider config typed parsing stays provider-owned:

- Doc provider parses `DocToolLimits` and path whitelist from `spec.config`.
- Fins provider parses `FinsToolLimits`, workspace root, read/ingestion enablement and processor cache size from `spec.config`.
- Web provider parses `WebToolsConfig` from `spec.config`.
- ConfigLoader only validates JSON shape, not business semantics.

Input projection:

- Each provider/tool adapter must explicitly decide whether `ToolCallRequest.arguments` can be passed directly as keyword arguments to the migrated function, or whether projection/coercion/validation is required first.
- Projection/coercion/validation belongs to adapter/provider code and must run before calling the migrated OLD function.
- Adapter/provider code must not modify OLD function signatures or OLD function bodies to make argument shapes fit.
- The shared projection API is `project_tool_call_arguments(declaration: CollectedLegacyTool, call: ToolCallRequest, path_policy: ToolPathValidationPolicy | None) -> ProjectedLegacyCall | ToolFailedOutcome`.
- `ProjectedLegacyCall.keyword_arguments` is the exact keyword mapping passed to the migrated function. Adapter-owned execution context injection, when declared by `execution_context_param_name`, is added after JSON argument projection and must not be read from `ToolCallRequest.arguments`.
- Direct pass-through is allowed only when all of the following are true: schema field names match callable parameter names, required fields are present, no path parameter is declared, no enum/range/array/scalar coercion is required, no execution-context injection is required, and JSON value types already match the migrated function’s expected primitive/container shape.
- Coercion/validation is required when schema defaults, optional arrays, numeric bounds, enums, path normalization, string normalization, unknown-field rejection, or execution-context injection are needed. Projection failures return `ToolFailedOutcome(ToolResultFailure(ok=False, error="invalid_argument", ...))` and the migrated function is not called.
- Provider slices must test at least one representative call where arguments pass directly and one call where adapter projection/coercion/validation is required, if such a tool exists in that provider.

Tool result mapping:

- OLD successful envelope maps to current `ToolCompletedOutcome(ToolResultSuccess(value=<LLM-facing projected value>))`.
- OLD failure envelope maps to current `ToolFailedOutcome(ToolResultFailure(error, message, hint))`.
- Adapter output projection must be implemented directly for current outcomes. OLD `project_for_llm`, OLD truncation projection and OLD `fetch_more` output must not be migrated or reused.
- Every migrated function return value must be projected to a current `ToolCompletedOutcome` or `ToolFailedOutcome`.
- `ToolResultSuccess.value` must be LLM-readable and must not contain the OLD `ok/value` envelope as an extra nesting layer.
- The shared response API is:
  - `project_legacy_return(tool_name: str, raw_value: JsonValue, started_at: datetime, finished_at: datetime) -> ToolCompletedOutcome | ToolFailedOutcome`
  - `project_legacy_exception(tool_name: str, error: Exception, started_at: datetime, finished_at: datetime) -> ToolFailedOutcome`
- Plain dict/list/string/number/bool/null returns become `ToolCompletedOutcome` with the value unchanged, subject only to JSON compatibility validation.
- OLD `{"ok": True, "value": ...}` envelopes are unwrapped to the `value` payload. OLD `truncation`, `continuation_hint`, `fetch_more_args` or projection-only fields are not carried as current runtime truncation state.
- OLD `{"ok": False, "error": "...", "message": "...", "hint": "..."}` envelopes become `ToolFailedOutcome` with the same error/message/hint where present.
- OLD `ToolBusinessError` maps to `ToolFailedOutcome` using the business error code/message/hint. OLD `ToolArgumentError` and adapter validation failures map to `error="invalid_argument"`. Path validation failures map to `error="permission_denied"`. Missing files map to `error="file_not_found"`. Unexpected exceptions map to `error="execution_error"` with a safe message/hint.
- Provider slices must test response projection for representative success and failure paths.

Truncation declaration:

- Migrated tools that need truncation must declare truncation using current `dayu.contracts.tool_schema.ToolTruncateSpec`.
- Migrated imports must point truncate declarations to current `dayu.contracts.tool_schema.ToolTruncateSpec` and `ToolTruncationStrategy`.
- The adapter declaration helper accepts only `ToolTruncateSpec | None`, and the stored metadata must be `ToolTruncateSpec | None` from the current contracts module.
- Migrated declaration-site edits are allowed to replace OLD string strategies such as `"text_chars"` with current `ToolTruncationStrategy.TEXT_CHARS`. This is a declaration import/argument rewrite, not a function signature or function body change.
- Do not copy OLD `ToolTruncateSpec` as a runtime contract or as a declaration compatibility class.
- Do not use OLD truncation metadata as an execution owner. After declaration translation, current Host ToolRuntime owns truncation and `FrameworkToolName.FETCH_MORE`.
- Mapping rules for OLD Doc/Fins/Web truncate declarations:
  - OLD `enabled=False` or missing truncate -> current `None`.
  - OLD `enabled=True` -> current `ToolTruncateSpec(enabled=True, ...)`.
  - OLD `strategy="text_chars"` -> current `ToolTruncationStrategy.TEXT_CHARS`; required limit key remains `max_chars`.
  - OLD `strategy="text_lines"` -> current `ToolTruncationStrategy.TEXT_LINES`; required limit key remains `max_lines`.
  - OLD `strategy="list_items"` -> current `ToolTruncationStrategy.LIST_ITEMS`; required limit key remains `max_items`.
  - OLD `strategy="binary_bytes"` -> current `ToolTruncationStrategy.BINARY_BYTES`; required limit key remains `max_bytes`.
  - OLD `limits` are copied only if the single key matches the current strategy limit key and the value is a positive integer.
  - OLD `target_field` maps to current `target_field`; current `field_path` is `None` unless a migrated declaration explicitly uses current `field_path`.
  - Current `ttl_seconds` is `None`; Host runtime policy supplies effective TTL.
  - OLD `continuation_hint` is not part of current `ToolTruncateSpec` and must not be used to recreate OLD fetch-more or projection behavior.
- Tests must prove migrated declarations import/use current `ToolTruncateSpec`, and no OLD `ToolTruncateSpec`, OLD `TruncationManager`, OLD `fetch_more`, or OLD truncate/fetch-more projection is imported or used.

Path safety:

- Doc tools do not own path safety after migration.
- The Doc provider / adapter must require an explicit path whitelist for any Doc provider with tools enabled.
- The adapter must enforce fail-closed path validation before calling OLD Doc function bodies.
- `file_path_params` metadata is collected from migrated `@tool(...)` declarations and consumed by provider/adapter path validation.
- The declaration collector must not treat `register_allowed_paths(...)` as OLD path enforcement. If the method exists to keep unmodified OLD registration functions callable, it only records declaration-time metadata and performs no whitelist validation.
- Do not pass path whitelist through `register_doc_tools(... allowed_paths=...)`; call that signature with `allowed_paths=None` and let the outer provider / adapter enforce paths through `ToolPathValidationPolicy`.
- Failed path validation returns current `ToolFailedOutcome(ToolResultFailure(ok=False, error="permission_denied", message=..., hint=...))` before the migrated Doc function body is called.

## Exact OLD Source Scope

Must migrate / inspect:

- `/Users/leo/workspace/dayu-agent/dayu/fins/**`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/doc_tools.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/web_*.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/processors/*`
- `/Users/leo/workspace/dayu-agent/dayu/docling_runtime.py`

Support OLD helpers that are allowed only after import-closure inventory classifies them as required adapter dependencies:

- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/base.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tool_contracts.py` only as a reference for metadata translation; do not copy OLD `ToolTruncateSpec` as a runtime contract.
- `/Users/leo/workspace/dayu-agent/dayu/engine/argument_validator.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/exceptions.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/tool_errors.py`
- OLD logging helper only as a private adapter dependency if migrated OLD code still calls `Log.*`; do not add top-level `dayu.log` compatibility.
- `/Users/leo/workspace/dayu-agent/dayu/engine/tools/utils_tools.py` and any other discovered OLD helper must be classified by import-closure inventory before copy.

Import-closure inventory rule:

- Before S1, S3, S4 and S5 copy old files, the implementation agent must run an import-closure inventory for the files in that slice.
- The inventory artifact can live in the slice implementation report and must list each OLD helper as `included`, `excluded-with-reason`, or `blocker`.
- Do not guess final helper scope in this plan. A helper that is not classified must not be copied.
- If an import closure requires OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, OLD truncate/fetch-more projection, Host/Engine runtime state, or OLD UI files, stop and write a blocker instead of widening scope silently.

Explicitly excluded:

- `/Users/leo/workspace/dayu-agent/dayu/web/**` except for exclusion evidence in docs/review notes. These are OLD UI / FastAPI / Streamlit entrypoints, not Web tools.
- `/Users/leo/workspace/dayu-agent/dayu/engine/tool_registry.py` as an execution implementation.
- `/Users/leo/workspace/dayu-agent/dayu/engine/truncation_manager.py`.
- OLD registry `fetch_more` implementation.
- OLD `dayu.engine.tool_result.project_for_llm` / truncation projection implementation.
- OLD `ToolTruncateSpec` as a runtime contract.

## Implementation Decisions

1. Use provider-local adapters, not Host or Engine changes, for OLD sync registry tools.
2. Convert OLD decorated functions to current `ToolDefinition`; do not expose OLD registry itself to Host.
3. Build current async `ToolCallable` wrappers with `asyncio.to_thread` for blocking sync OLD tool calls, guarded by an explicit concurrency policy.
4. Use current ToolRuntime as the only truncation owner. Convert OLD truncate metadata to current `ToolTruncateSpec`; do not migrate or call OLD registry truncation / OLD `TruncationManager`.
5. Exclude OLD `fetch_more` from business bundle; current ToolRuntime injects `FrameworkToolName.FETCH_MORE`.
6. Keep OLD business function signatures and bodies unchanged. Allowed edits in moved OLD files are import paths, package names, module-level integration imports, and declaration-site truncate strategy rewrites from OLD strings to current `ToolTruncationStrategy` enum members.
7. New adapter/provider/config code must use precise typed signatures and Chinese docstrings.
8. Migrated OLD files retain OLD signatures only where the migration constraint forbids signature edits; adapters and new code must not add new weak typing.
9. Tool providers fail fast on invalid config. They do not silently default workspace roots, path whitelists or network safety to cwd/env.
10. Fins provider starts with read tools. Ingestion tools are included only after direct evidence proves each tool synchronously returns completed/failed results that map to current outcomes without job polling, callback, external wait, or `ToolAwaitingOutcome` semantics; otherwise S4 writes `docs/reviews/wu-tools-01-s4-ingestion-blocker-codex.md`.
11. Input and response projection are adapter/provider responsibilities. `ToolCallRequest.arguments` pass directly only after the provider documents that names/types match the migrated function; otherwise adapter/provider code must project/coerce/validate before invocation. Return values must always become current outcomes with LLM-readable `ToolResultSuccess.value` / `ToolResultFailure`.
12. Default old sync callable execution is serialized per tool name with an adapter-owned `asyncio.Lock` around `asyncio.to_thread`. A provider chooses provider-wide serialization for known shared mutable state. Concurrent execution is allowed only after direct code evidence and a concurrent ToolRuntime test prove the specific callable is safe.

## Slices

### Slice S1: Shared Document Foundations

Objective: establish one shared document processing and Docling runtime owner outside Engine.

Allowed files/modules:

- Add `dayu/documents/__init__.py`
- Add `dayu/documents/docling_runtime.py`
- Add `dayu/documents/processors/*.py` from OLD `engine/processors/*`
- Add `tests/documents/`
- Update `tests/runtime/test_import_boundary.py`, `tests/engine/contracts/test_import_boundary.py` or equivalent import-boundary tests
- Update `dayu/README.md` if adding `dayu.documents` as a stable package
- Update `dayu/engine/README.md` only if it currently claims document processors live in Engine

Exact allowed changes:

- Copy OLD processors and Docling runtime.
- Adjust imports from `dayu.engine.processors.*` to `dayu.documents.processors.*`.
- Adjust logging imports to stdlib logging or a private adapter-local helper only when needed for moved OLD code to run; do not add top-level `dayu.log`.
- Keep processor class/function signatures and function bodies unchanged except import/package references.
- Add lightweight deterministic fixtures for Markdown, HTML and Docling JSON processor behavior.

Non-goals:

- No Doc/Fins/Web provider.
- No ToolDefinition adapter.
- No Host/Engine changes.
- No Fins storage.

Tests / validation:

- `source .venv/bin/activate && pytest tests/documents tests/runtime/test_import_boundary.py tests/engine/contracts/test_import_boundary.py`
- `source .venv/bin/activate && pyright`

Expected assertions:

- `dayu.documents` imports no Host / Engine / Service / UI / Fins.
- Engine import-boundary tests still prove no `dayu.fins` or tool implementation import.
- Processor fixtures produce expected sections, tables/search snippets or Docling JSON structure.

Stop condition:

- Stop if shared processors require importing Host/Engine runtime state or concrete tools.
- Stop if preserving OLD processor signatures creates pyright failures that cannot be solved by import/package adjustment.

Docs / README decision:

- Update `dayu/README.md` because a new shared package affects code reading order and stable boundaries.
- Update `dayu/engine/README.md` only if its current text becomes false.

### Slice S2: Tool Adapter And Typed Provider Config

Objective: create the narrow OLD registry-to-current ToolDefinition adapter and allow provider config to reach providers.

Allowed files/modules:

- Add `dayu/tools/__init__.py`
- Add `dayu/tools/_legacy_adapter/__init__.py`
- Add `dayu/tools/_legacy_adapter/tool_contracts.py`
- Add `dayu/tools/_legacy_adapter/tool_decorator.py`
- Add `dayu/tools/_legacy_adapter/argument_validator.py`
- Add `dayu/tools/_legacy_adapter/exceptions.py`
- Add `dayu/tools/_legacy_adapter/tool_errors.py`
- Add `dayu/tools/_legacy_adapter/registry_collector.py`
- Add `dayu/tools/_legacy_adapter/definition_adapter.py`
- Modify `dayu/runtime/config_loader.py`
- Modify `dayu/service/host_assembly.py`
- Modify `dayu/config/tool_discovery.json` only to add disabled provider records and `config` examples that remain valid defaults
- Add/update `tests/runtime/test_config_loader.py`
- Add/update `tests/service/test_host_assembly.py`
- Add `tests/tools/test_legacy_tool_adapter.py`
- Add/update import-boundary tests for `dayu.tools`

Exact allowed changes:

- Copy only OLD metadata helper contracts classified by import-closure inventory as needed by OLD `@tool` declarations into `_legacy_adapter`; do not expose them as public compatibility imports.
- Implement a new minimal declaration collector. This collector is not OLD `ToolRegistry` and must not copy OLD execution, truncation manager, path whitelist enforcement or `fetch_more`.
- Implement path-safe argument validation and execution in adapter code.
- Implement explicit input projection from `ToolCallRequest.arguments` to migrated function keyword arguments. Direct pass-through is allowed only when schema field names match the migrated function parameters and no coercion/path normalization is required; otherwise adapter/provider code must project/coerce/validate before invocation.
- Implement raw return / exception to current outcome conversion. If a migrated function still returns an OLD-style envelope, unwrap it in adapter code; do not migrate OLD `project_for_llm`.
- Implement OLD schema to current `ToolSchema` conversion.
- Implement OLD truncate declaration metadata to current `ToolTruncateSpec` conversion at declaration time. Do not copy OLD `ToolTruncateSpec` as a runtime contract and do not treat OLD metadata as an execution owner.
- Do not copy or call OLD registry truncation manager in the current adapter execution path.
- Do not migrate OLD `fetch_more`; reserved framework `fetch_more` remains current ToolRuntime-owned.
- Add `config` to `ToolDiscoveryProviderConfig` and pass it into `ToolsDiscoveryProviderSpec`.

Adapter API contract:

- `registry_collector.py` defines `LegacyToolKeywordValue = JsonValue | BatchToolExecutionContext | None` so adapter-owned execution context injection has an explicit non-JSON type and does not enter `ToolCallRequest.arguments`.
- `registry_collector.py` defines `LegacySyncToolCallable` as a protocol for migrated synchronous tool functions:
  - `def __call__(self, **keyword_arguments: LegacyToolKeywordValue) -> JsonValue`
  - It is used only as a callable reference; the adapter invokes it only after input projection succeeds.
- `registry_collector.py` defines `CollectedLegacyTool`:
  - `name: str`
  - `callable: LegacySyncToolCallable`
  - `schema: ToolSchema`
  - `tags: tuple[str, ...]`
  - `truncate: ToolTruncateSpec | None`
  - `file_path_params: tuple[str, ...]`
  - `execution_context_param_name: str | None`
  - `display_name: str | None`
  - `summary_params: tuple[str, ...] | None`
- `registry_collector.py` defines `LegacyToolDeclarationCollector` with:
  - `def register(self, name: str, func: LegacySyncToolCallable, schema: ToolSchema) -> None`
  - `def register_allowed_paths(self, paths: Sequence[Path]) -> None`
  - `def collected_tools(self) -> tuple[CollectedLegacyTool, ...]`
- `LegacyToolDeclarationCollector.register_allowed_paths(...)` exists only so unmodified OLD registration functions remain callable when a branch is accidentally reached. It records no trusted whitelist, performs no path validation, and must not be consumed as path safety evidence. Providers still call Doc registration with `allowed_paths=None`.
- The collector output consumed by S3/S4/S5 provider slices is exactly `tuple[CollectedLegacyTool, ...]`.
- `definition_adapter.py` defines `ToolPathValidationPolicy`:
  - `allowed_roots: tuple[Path, ...]`
  - `file_path_params: tuple[str, ...]`
  - `must_exist: bool`
- `definition_adapter.py` defines `ProjectedLegacyCall`:
  - `keyword_arguments: Mapping[str, JsonValue]`
- `definition_adapter.py` defines `LegacyToolConcurrencyPolicy` with explicit values `serial_per_tool`, `serial_per_provider`, and `concurrent_after_evidence`.
- `definition_adapter.py` defines:
  - `def project_tool_call_arguments(declaration: CollectedLegacyTool, call: ToolCallRequest, path_policy: ToolPathValidationPolicy | None) -> ProjectedLegacyCall | ToolFailedOutcome`
  - `def project_legacy_return(tool_name: str, raw_value: JsonValue, started_at: datetime, finished_at: datetime) -> ToolCompletedOutcome | ToolFailedOutcome`
  - `def project_legacy_exception(tool_name: str, error: Exception, started_at: datetime, finished_at: datetime) -> ToolFailedOutcome`
  - `def adapt_collected_tool(declaration: CollectedLegacyTool, path_policy: ToolPathValidationPolicy | None, concurrency_policy: LegacyToolConcurrencyPolicy) -> ToolDefinition`
  - `def adapt_collected_tools(declarations: Sequence[CollectedLegacyTool], path_policy_by_tool: Mapping[str, ToolPathValidationPolicy], concurrency_policy_by_tool: Mapping[str, LegacyToolConcurrencyPolicy]) -> tuple[ToolDefinition, ...]`
- `adapt_collected_tool(...)` output is a current `ToolDefinition` whose `callable` is an async current `ToolCallable`. Provider slices must return these current `ToolDefinition` values in `ToolsDiscoveryProviderOutput.definitions`.
- The adapter uses current `ToolDisplayInfo` and current tags metadata from `CollectedLegacyTool`; it must not emit OLD schema, OLD result envelope, or OLD registry objects.

Non-goals:

- No Doc/Fins/Web business tools yet.
- No durable schema.
- No ToolRuntime behavior change.
- No `ToolDefinition` contract change.

Tests / validation:

- `source .venv/bin/activate && pytest tests/tools/test_legacy_tool_adapter.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/runtime/test_tools_discovery.py`
- `source .venv/bin/activate && pyright`

Expected assertions:

- Provider config survives ConfigLoader -> Service assembly -> `ToolsDiscoveryProviderSpec.config`.
- Sync OLD-style callable becomes async current `ToolCallable`.
- Adapter tests cover direct argument pass-through and required input projection/coercion/validation.
- Adapter tests prove projection failures return `ToolFailedOutcome` and do not call the migrated function.
- Success projects without OLD `ok/value` nesting.
- Failure maps to `ToolFailedOutcome`.
- OLD successful and failed `ok/value` envelopes are projected to current outcomes without carrying OLD projection/truncation/fetch-more fields.
- OLD `fetch_more` is not emitted as business tool.
- Current `ToolTruncateSpec` is present when OLD metadata declares truncation; mapping covers `text_chars`, `text_lines`, `list_items`, `binary_bytes`, matching limit keys, `target_field`, `field_path=None`, `ttl_seconds=None`, and discarded OLD `continuation_hint`.
- No OLD `ToolTruncateSpec` is imported, copied or used as runtime contract.
- No adapter module imports or instantiates OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, or OLD truncate/fetch-more projection.
- Default per-tool serialization is tested by concurrent adapter calls proving the same migrated callable is not entered concurrently.

Stop condition:

- Stop if adapter requires changing current `ToolDefinition` / `ToolRuntime` public contract.
- Stop if provider config requires ConfigLoader to interpret business semantics.
- Stop if preserving unmodified OLD registration functions requires copying OLD `ToolRegistry` execution/path/truncation/fetch-more semantics.

Docs / README decision:

- Update `dayu/config/README.md` because `tool_discovery.json` schema gains provider `config`.
- Update `dayu/README.md` only if user-facing config examples change.
- Update `dayu/README.md` if `dayu.tools` becomes part of developer reading order.

### Slice S3: Doc Tools Provider

Objective: migrate OLD Doc tools and expose them through `ToolsDiscovery` without making Doc tool functions own path safety.

Allowed files/modules:

- Add `dayu/tools/doc_tools.py`
- Add `dayu/tools/doc_provider.py`
- Add/update `dayu/config/tool_discovery.json` disabled `doc-tools` provider
- Add `tests/tools/test_doc_tools_provider.py`
- Add deterministic fixtures under `tests/fixtures/documents/` or `tests/tools/fixtures/`
- Update `dayu/config/README.md` if provider config examples are added
- Update `tests/README.md` if adding new tool test conventions

Exact allowed changes:

- Copy OLD `engine/tools/doc_tools.py` to `dayu/tools/doc_tools.py`.
- Adjust imports to `dayu.documents.processors`, `dayu.tools._legacy_adapter` and current config location.
- Before copying, complete an import-closure inventory for `doc_tools.py`; classify `utils_tools.py` and every discovered OLD helper as included, excluded-with-reason, or blocker.
- Preserve `register_doc_tools(...)` signature.
- Preserve inner tool function signatures and bodies.
- Provider parses `DocToolLimits` from `spec.config["limits"]`.
- Provider parses explicit path whitelist from `spec.config["allowed_paths"]`.
- Provider fails closed when enabled without any allowed path.
- Provider / adapter registers path whitelist externally, then calls `register_doc_tools(..., allowed_paths=None, allow_file_write=False, allowed_write_paths=None, timeout_budget=None)`.
- Doc input projection decision: path arguments (`directory`, `file_path`) must be projected through outer whitelist validation and normalized to the allowed absolute path before calling the migrated function; non-path arguments pass directly only after adapter validation/coercion against the tool schema.
- Doc response projection decision: raw dict/list/string returns become current `ToolCompletedOutcome` with LLM-readable `ToolResultSuccess.value`; exceptions and adapter validation failures become current `ToolFailedOutcome`.
- Doc truncation decision: `read_file` and `read_file_section` truncate declarations must be translated to current `ToolTruncateSpec` at declaration time; current ToolRuntime owns execution-time truncation and `fetch_more`.
- Provider returns `ToolsDiscoveryProviderOutput` with source refs and current `ToolDefinition` values for `list_files`, `get_file_sections`, `search_files`, `read_file`, `read_file_section`.

Non-goals:

- No write-file Doc tools.
- No path safety logic inside migrated Doc tool functions.
- No Web/Fins migration.
- No live Docling heavyweight test if deterministic Docling JSON fixture is sufficient.

Tests / validation:

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/documents`
- `source .venv/bin/activate && pyright`

Expected assertions:

- Provider discovers exactly five Doc tools.
- Missing path whitelist fails before tool execution.
- A disallowed path returns current failed outcome.
- Tests prove Doc function bodies are not responsible for path safety by using a spy/fixture callable or call counter: failed path validation returns `ToolFailedOutcome` before the migrated function body is entered.
- Tests prove `file_path_params` metadata is collected from old decorators and used by provider/adapter path validation.
- Tests prove `LegacyToolDeclarationCollector.register_allowed_paths(...)` is not used as the trusted enforcement source for Doc tools.
- Path arguments are projected to validated allowed paths before migrated Doc function invocation; invalid/non-coercible arguments fail in adapter/provider code.
- Representative success and failure responses project to current outcomes without OLD `ok/value` nesting.
- Markdown and Docling JSON fixtures support section listing/search/read paths.
- No OLD `fetch_more` business tool appears.
- `read_file` and `read_file_section` expose current `ToolTruncateSpec`; no OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, or OLD truncate/fetch-more projection is imported or used.
- Current ToolRuntime can execute at least one Doc tool through accept barrier in an integration-style test.

Stop condition:

- Stop if path whitelist can only be enforced by modifying migrated Doc tool function bodies or signatures.
- Stop if Doc import closure requires OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, OLD truncate/fetch-more projection, or unclassified OLD helper files.

Docs / README decision:

- Update `dayu/config/README.md` for Doc provider config.
- Update `tests/README.md` if fixture/test structure adds a new convention.

Residual closure:

- Closes WU-TOOLS-01-R1 for Doc tools by placing path whitelist / fail-closed behavior in provider/adapter.
- Closes WU-TOOLS-01-R4 for Doc tools by requiring current `ToolTruncateSpec` metadata only and prohibiting OLD truncation / OLD `fetch_more`.
- Closes Doc part of WU-TOOLS-01-R5 by testing path input projection, schema validation/coercion and response projection.

### Slice S4: Fins Storage And Read Tools Provider

Objective: migrate Fins storage, services, processors and read tools so financial document access goes through `dayu.fins.storage` and tools enter Host via `ToolsDiscovery`.

Allowed files/modules:

- Add `dayu/fins/**` from OLD source scope
- Modify migrated Fins imports to `dayu.documents.processors.*` and `dayu.tools._legacy_adapter.*`
- Add `dayu/fins/tools/provider.py` or `discover_tools` in `dayu/fins/tools/__init__.py`
- Add/update disabled `financial-tools` provider config in `dayu/config/tool_discovery.json`
- Add `tests/fins/`
- Add/update import-boundary tests
- Update `dayu/fins/README.md`
- Update `dayu/config/README.md` if Fins provider config example changes
- Update `tests/README.md` if adding Fins fixtures

Exact allowed changes:

- Copy OLD `/dayu/fins` files.
- Before copying, complete an import-closure inventory for Fins storage, read tools, service/runtime, processors and tool helper imports; classify every discovered OLD helper as included, excluded-with-reason, or blocker.
- Adjust imports away from OLD Engine processors and OLD tool helper paths.
- Preserve Fins business class/function signatures and function bodies.
- Keep `dayu.fins.storage` repository protocols and filesystem implementations as storage truth.
- Provider parses:
  - `workspace_root` as explicit absolute or explicitly resolvable configured path;
  - `limits` into `FinsToolLimits`;
  - `include_read_tools` default true;
  - `include_ingestion_tools` default false unless explicitly enabled.
- Provider builds `DefaultFinsRuntime` from configured workspace root and registers read tools through the legacy adapter.
- Provider must not use Host / Service objects or EventLog to build Fins service.
- Fins input projection decision: for read tools, `ToolCallRequest.arguments` pass directly only where schema field names and JSON types match the migrated function parameters; adapter/provider must validate/coerce optional arrays, integers and strings before invocation. Ticker/document identity normalization remains inside migrated Fins service code and must not be moved into Host/Engine.
- Fins response projection decision: typed result dicts become current `ToolCompletedOutcome` with LLM-readable `ToolResultSuccess.value`; `ToolArgumentError`, `ToolBusinessError`, missing documents and adapter validation failures become current `ToolFailedOutcome`.
- Fins truncation decision: list/text/table result limits declared by OLD metadata must be translated to current `ToolTruncateSpec` at declaration time; current ToolRuntime owns execution-time truncation and `fetch_more`.
- Conservative default: migrate read tools first. Ingestion tools are included only when direct code evidence proves synchronous completed/failed mapping with no job polling, callback, external wait, or `ToolAwaitingOutcome` requirement.
- If ingestion cannot be included, write `docs/reviews/wu-tools-01-s4-ingestion-blocker-codex.md`.
- The blocker artifact must contain affected tools, direct evidence, why completed/failed mapping is insufficient, required wait/awaiting semantics, proposed owner/destination, and whether a later wait-adapter work unit is needed.

Non-goals:

- No Host direct Fins storage access.
- No rewrite of Fins business logic, processors, pipelines or storage schema.
- No live SEC/HKEX/CN network tests.
- No new Service workflow for multi-run ingestion.

Tests / validation:

- `source .venv/bin/activate && pytest tests/fins tests/tools/test_legacy_tool_adapter.py tests/runtime/test_tools_discovery.py`
- `source .venv/bin/activate && pyright`

Expected assertions:

- Storage repository protocol and filesystem implementation can list/read deterministic fixture documents.
- Fins provider discovers read tools with `fins` tag.
- `list_documents` and one read/search tool execute through current `ToolRuntime` accept path using fixture workspace.
- Representative Fins input projection/coercion is tested for arrays/scalars where tool schemas require it; direct pass-through is tested for a matching simple call.
- Representative Fins success and failure responses project to current outcomes without OLD `ok/value` nesting.
- Truncating Fins tools expose current `ToolTruncateSpec`; no OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, or OLD truncate/fetch-more projection is imported or used.
- Fins imports do not introduce Host/Service/UI/runtime reverse dependencies.
- Engine still does not import Fins.

Stop condition:

- Stop if Fins read tools require bypassing `dayu.fins.storage`.
- Stop if OLD Fins migration requires changing business function/class signatures or function bodies.
- Stop and classify if ingestion tools require current `ToolAwaitingOutcome` / wait adapter design beyond this work unit.
- Stop and write `docs/reviews/wu-tools-01-s4-ingestion-blocker-codex.md` if ingestion behavior cannot be proven as synchronous completed/failed mapping.
- Stop if Fins import closure requires OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, OLD truncate/fetch-more projection, Host/Service objects, or unclassified OLD helper files.

Docs / README decision:

- Update `dayu/fins/README.md` because `dayu/fins/` changes.
- Update `dayu/config/README.md` for provider config.
- Update `tests/README.md` if adding Fins fixture convention.

Residual closure:

- Closes Fins part of WU-TOOLS-01-R2 and R3 by mapping typed limits/config and OLD sync registry tools through provider/adapter.
- Closes Fins part of WU-TOOLS-01-R4 by mapping OLD truncate metadata to current `ToolTruncateSpec` and leaving `fetch_more` to current ToolRuntime.
- Closes Fins part of WU-TOOLS-01-R5 by testing input projection/coercion and response projection.

### Slice S5: Web Tools Provider

Objective: migrate OLD Web tools implementation, excluding OLD UI, and expose `search_web` / `fetch_web_page` through current ToolDiscovery / ToolRuntime.

Allowed files/modules:

- Add `dayu/tools/web/__init__.py`
- Add `dayu/tools/web/web_tools.py`
- Add `dayu/tools/web/web_fetch_orchestrator.py`
- Add `dayu/tools/web/web_search_providers.py`
- Add `dayu/tools/web/web_challenge_detection.py`
- Add `dayu/tools/web/web_http_encoding.py`
- Add `dayu/tools/web/web_http_session.py`
- Add `dayu/tools/web/web_playwright_backend.py`
- Add `dayu/tools/web/web_recovery.py`
- Add `dayu/tools/web/provider.py`
- Add/update disabled `web-tools` provider config in `dayu/config/tool_discovery.json`
- Add `tests/tools/web/`
- Update `dayu/config/README.md` if provider config examples change
- Update `tests/README.md` if web fixture/mock convention is added

Exact allowed changes:

- Copy OLD `engine/tools/web_*.py` files listed above.
- Before copying, complete an import-closure inventory for Web tool files and helper imports; classify every discovered OLD helper as included, excluded-with-reason, or blocker.
- Adjust imports to `dayu.documents.processors.*` and `dayu.tools._legacy_adapter.*`.
- Preserve Web tool business function signatures and bodies.
- Provider parses `WebToolsConfig` from `spec.config`.
- Provider preserves private-network fail-closed default.
- Web input projection decision: `search_web` arguments pass directly only after adapter validation/coercion of optional `domains`, `recency_days` and `max_results`; `fetch_web_page.url` must be validated/coerced to a string and URL safety is enforced by migrated Web logic plus provider config. Adapter/provider code must reject non-coercible JSON before calling the migrated function.
- Web response projection decision: successful search/fetch dicts become current `ToolCompletedOutcome` with LLM-readable `ToolResultSuccess.value`; `ToolBusinessError`, URL safety rejection, timeout-like failures and adapter validation failures become current `ToolFailedOutcome`.
- Web truncation decision: `search_web` and `fetch_web_page` truncate declarations must be translated to current `ToolTruncateSpec` at declaration time; current ToolRuntime owns execution-time truncation and `fetch_more`.
- Provider returns `search_web` and `fetch_web_page` definitions.
- Tests use deterministic mocked requests/search provider/Playwright fallback, not live network.

Non-goals:

- No OLD `/dayu/web` UI migration.
- No new browser automation product feature.
- No rewrite of URL safety, private network filtering, search provider selection, challenge detection, Playwright fallback or diagnostic payloads.

Tests / validation:

- `source .venv/bin/activate && pytest tests/tools/web tests/tools/test_legacy_tool_adapter.py`
- `source .venv/bin/activate && pyright`

Expected assertions:

- Web provider discovers `search_web` and `fetch_web_page`.
- Private/local network URL is rejected unless config explicitly allows it.
- Fetch/search adapters return current completed/failed outcomes.
- Web input projection/coercion is tested for optional search arguments and invalid URL argument type.
- Representative Web success and failure responses project to current outcomes without OLD `ok/value` nesting.
- Truncation metadata attaches as current `ToolTruncateSpec`, not OLD registry truncation.
- No OLD `TruncationManager`, OLD `ToolRegistry` execution path or OLD `fetch_more` is imported by Web provider/adapter.
- OLD `/dayu/web` files are not present in migrated implementation scope.
- Web provider serialization policy is documented and tested if shared sessions/Playwright fallback are not proven concurrent-safe.

Stop condition:

- Stop if Web tools require importing UI modules.
- Stop if deterministic tests cannot cover core behavior without live network.
- Stop if Web import closure requires OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, OLD truncate/fetch-more projection, OLD UI files, or unclassified OLD helper files.

Docs / README decision:

- Update `dayu/config/README.md` for Web provider config.
- Update `tests/README.md` if adding web mock conventions.

Residual closure:

- Closes Web part of WU-TOOLS-01-R4 by mapping truncate metadata to current `ToolTruncateSpec` and leaving `fetch_more` to current ToolRuntime.
- Closes Web part of WU-TOOLS-01-R5 by testing input projection/coercion and response projection.

### Slice S6: Combined Discovery / ToolRuntime Acceptance / Docs Closure

Objective: prove all providers work together through current assembly and Host-owned ToolRuntime.

Allowed files/modules:

- Add/update integration tests under `tests/service/`, `tests/host/`, `tests/runtime/`, `tests/tools/`
- Update `dayu/config/tool_discovery.json`
- Update `README.md`, `dayu/README.md`, `dayu/config/README.md`, `dayu/host/README.md`, `dayu/engine/README.md`, `dayu/fins/README.md`, `tests/README.md` only where trigger rules and actual changes require it

Exact allowed changes:

- Add an integration fixture config enabling Doc, Fins and Web providers with deterministic roots/mocks.
- Assert `ToolsDiscovery` returns one bundle without duplicate names or reserved `fetch_more`.
- Assert all truncating migrated tools use current `ToolTruncateSpec`, and `FrameworkToolName.FETCH_MORE` remains current ToolRuntime-owned.
- Assert no migrated provider/adapter imports OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, or OLD truncate/fetch-more projection.
- Assert `compose_open_host_options` passes effective tool bundle to Host.
- Assert ToolRuntime executes one representative tool from each provider and accept barrier records accepted facts.
- Assert representative provider calls cover input projection/coercion where needed and response projection to current outcomes.
- Assert selected scene tool tags can select `doc`, `fins`, `web` tools if existing ScenePrepare tests support it.

Non-goals:

- No live model call.
- No live external network.
- No UI/CLI workflow implementation.

Tests / validation:

- `source .venv/bin/activate && pytest tests/runtime tests/service tests/tools tests/fins tests/host`
- `source .venv/bin/activate && pyright`

Expected assertions:

- No duplicate/reserved tool name failures.
- All truncating migrated tools expose current `ToolTruncateSpec`; current ToolRuntime owns `FrameworkToolName.FETCH_MORE`.
- No migrated provider/adapter imports OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more`, or OLD truncate/fetch-more projection.
- Representative provider calls cover direct input pass-through where safe and input projection/coercion/validation where needed.
- Representative provider success and failure responses project to current `ToolCompletedOutcome` / `ToolFailedOutcome` without OLD `ok/value` nesting.
- `ToolRuntimeHandle.tool_schemas` and executor originate from same effective bundle.
- Representative tool outcomes are accepted by Host.
- Concurrent ToolRuntime calls either pass under the declared concurrency policy or stop with a documented provider-specific concurrency blocker.
- Import-boundary tests still pass.
- README content matches final code.

Stop condition:

- Stop if integration requires Host public API changes not approved in this plan.
- Stop if any provider fails ToolRuntime accept integration at S6 combined level.
- Stop if any unclassified residual remains.

Docs / README decision:

- Apply AGENTS.md trigger rules exactly:
  - `dayu/fins/` changes -> update `dayu/fins/README.md`.
  - `dayu/config/` changes -> update `dayu/config/README.md`.
  - `tests/` changes -> update `tests/README.md` if conventions change.
  - New package / boundary changes -> update `dayu/README.md`.
  - `dayu/engine/README.md` only if Engine boundary wording becomes false.
  - `dayu/host/README.md` only if ToolRuntime/Host boundary wording changes; expected no Host boundary change.
  - Root `README.md` only if user-facing config/workflow examples change.

## Residuals / Risks / Owners

No unclassified residuals.

- WU-TOOLS-01-R1 path safety adapter: covered by S2 and S3. Owner: implementation agent. Destination: provider/adapter tests proving Doc path whitelist fail-closed without modifying Doc function bodies.
- WU-TOOLS-01-R2 typed config adapter: covered by S2, S3, S4, S5. Owner: implementation agent. Destination: ConfigLoader provider `config`, Service mapping, provider-owned typed parsing tests.
- WU-TOOLS-01-R3 ToolDiscovery / ToolRuntime adapter: covered by S2 and S6. Owner: implementation agent. Destination: legacy sync callable adapter, current async `ToolCallable`, and ToolRuntime accept path tests.
- WU-TOOLS-01-R4 truncation / fetch_more ownership: covered by S2, S3, S4, S5 and S6. Owner: implementation agent. Destination: adapter/provider tests proving OLD `ToolRegistry`, OLD `TruncationManager`, OLD `fetch_more` and OLD truncation projection are not migrated or used; migrated truncating tools expose only current `ToolTruncateSpec`, and current ToolRuntime owns `FrameworkToolName.FETCH_MORE`.
- WU-TOOLS-01-R5 query / arguments input projection and response projection adapter: covered by S2 plus provider slices S3/S4/S5 and combined S6 tests. Owner: implementation agent. Destination: adapter/provider tests proving `ToolCallRequest.arguments` are passed directly only when safe, projected/coerced/validated in adapter/provider code when needed, and migrated function returns/errors become current `ToolCompletedOutcome` / `ToolFailedOutcome` with LLM-readable `ToolResultSuccess.value`.
- Fins ingestion waiting semantics: classified as conditional within S4. Owner: implementation agent; destination: include only if completed/failed mapping works, otherwise write a review/blocker artifact for Controller to decide a later wait-adapter work unit.
- OLD code weak typing: classified as migration constraint risk. Owner: implementation agent; destination: preserve OLD signatures where required, keep new adapter/provider code precise, and run pyright. If pyright cannot pass without changing OLD signatures/bodies, stop and write blocker.
- Optional heavy dependencies / live services: classified as test strategy risk. Owner: implementation agent; destination: deterministic fixtures/mocks, no live network or heavyweight Docling requirement in required tests.

## Why This Plan Is Not Over-Designed

The plan adds only three architectural elements required by direct evidence:

1. `dayu.documents` because three migrated areas share processors and Docling runtime, and Engine/runtime are the wrong owners.
2. A private OLD-to-current tool adapter because OLD tools are sync registry functions and NEW tools are async `ToolCallable` definitions.
3. Provider config pass-through because current `ToolsDiscoveryProviderSpec` already has `config`, but ConfigLoader/Service currently drops it.

It does not add a new Host API, Engine API, tool scheduler, generic plugin system, UI workflow, storage abstraction beyond migrated Fins storage, or a second ToolRuntime.

## Completion Report Format For Implementation Gate

Implementation agents should report:

1. artifact path
2. slice id / status
3. direct evidence used
4. files changed
5. tests and pyright commands run with results
6. docs/README updates or explicit no-op decision
7. residual risks with owner/destination

## Plan Gate Validation

No production code, tests or README files were modified in this plan gate. No tests were run because this gate only writes the plan artifact and does not create helper code.
