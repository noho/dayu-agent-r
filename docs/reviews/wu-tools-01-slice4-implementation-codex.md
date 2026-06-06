# WU-TOOLS-01 Slice S4 Implementation

Gate: implementation
Work unit: WU-TOOLS-01
Slice: S4 - Fins Storage And Read Tools Provider
Agent: AgentCodex
Status: implementation complete; stopped before review / fix / re-review / commit / push / PR

## Implementation Summary

- Migrated the Fins read-tool closure under `dayu/fins/`: domain models, filesystem storage repositories, processors, read service, read tool declarations, limits, search helpers, result types, ticker normalization and XBRL file discovery.
- Added `dayu.fins.service_runtime.DefaultFinsRuntime` for read tools provider assembly from an explicit absolute `workspace_root`.
- Added `dayu.fins.tools.provider.discover_tools`, returning current `ToolDefinition` values through the existing `_legacy_adapter`.
- Kept `financial-tools` disabled by default and changed its default `workspace_root` to `null`; enabling the provider requires a workspace overlay with an absolute path.
- Added `tests/fins/` covering storage fixture list/read, provider discovery, ToolRuntime accept path, input projection, response projection, truncation declarations, ingestion fail-closed and import boundaries.
- Updated `dayu/fins/README.md`, `dayu/config/README.md` and `tests/README.md`.

## Import Closure Inventory

Included:

| OLD scope | Current location | Reason |
|---|---|---|
| `dayu/fins/domain/*.py` | `dayu/fins/domain/` | Storage and read service model contracts. |
| `dayu/fins/storage/*.py` | `dayu/fins/storage/` | Required repository protocols and filesystem implementation; all document access flows through this boundary. |
| `dayu/fins/processors/*.py` | `dayu/fins/processors/` | Required by `build_fins_processor_registry()` and read service processor routing. |
| `dayu/fins/tools/fins_tools.py` | `dayu/fins/tools/fins_tools.py` | Read tool declaration factories; read tool function bodies preserved. |
| `dayu/fins/tools/service.py` | `dayu/fins/tools/service.py` | `FinsToolService` read business logic. |
| `dayu/fins/tools/service_helpers.py` | `dayu/fins/tools/service_helpers.py` | Read service normalization and payload helpers. |
| `dayu/fins/tools/search_engine.py` / `search_models.py` / `bm25f_scorer.py` / `section_semantic.py` / `cache.py` | same package | Search and processor cache closure for read tools. |
| `dayu/fins/tools/result_types.py` / `fins_limits.py` | same package | Read tool result and limits contracts. |
| `dayu/fins/_converters.py` / `ticker_normalization.py` / `xbrl_file_discovery.py` | same package | Read service, storage and processor helper closure. |
| OLD `dayu/file_lock.py` helper | `dayu/fins/_file_lock.py` | Storage-internal file lock helper needed by filesystem repositories; not exposed as a compatibility top-level re-export. |

Excluded with reason:

| OLD scope | Reason |
|---|---|
| `dayu/fins/tools/ingestion_tools.py` | Ingestion is background start/status/cancel polling; excluded and documented in `docs/reviews/wu-tools-01-s4-ingestion-blocker-codex.md`. |
| `dayu/fins/ingestion/**` | Required only for ingestion job manager and pipeline backend; excluded from read-provider closure. |
| `dayu/fins/pipelines/**` and `downloaders/**` | Download/upload/process paths only; not needed for read tools and would import ingestion semantics. |
| `dayu/fins/cli_support.py`, `cli_formatters.py`, scoring/diagnostic scripts, rescue/retriage scripts | CLI/diagnostic utilities, not provider read path. |
| OLD `dayu/engine/tool_registry.py` | Not migrated; declarations collected by `dayu.tools._legacy_adapter.registry_collector`. |
| OLD `dayu/engine/tool_contracts.ToolTruncateSpec` | Not migrated; declarations use current `dayu.contracts.tool_schema.ToolTruncateSpec`. |
| OLD `TruncationManager`, OLD `fetch_more`, OLD truncate/fetch-more projection | Not migrated; current Host ToolRuntime owns truncation and framework `fetch_more`. |
| OLD `dayu.contracts.fins`, `toolset_registrar`, runtime command CLI contracts | Not required by read tools; command/ingestion runtime excluded from S4. |

Blocker:

- Fins ingestion tools require current awaiting / wait-adapter semantics; see blocker artifact.

## Read vs Ingestion Decision

Read tools are included because their OLD declaration functions synchronously call `FinsToolService`, which reads company/source/processed documents through storage repository protocols and returns JSON-compatible business results.

Ingestion tools are excluded because OLD start tools return queued/running job snapshots while daemon worker threads continue work. That cannot be truthfully mapped to current single-call completed/failed outcomes.

## Migration Principle Compliance

- Read tool function signatures and function bodies are preserved.
- Business logic in `FinsToolService`, storage repositories and processors is migrated rather than rewritten.
- Declaration-site changes are limited to import/package adaptation, current `ToolTruncateSpec` enum arguments, removal of OLD `continuation_hint`, and `tags` sequence normalization.
- `DefaultFinsRuntime` is a read-only runtime adapter because OLD full runtime imports command contracts and ingestion/pipeline code outside S4 scope. This deviation is necessary to satisfy provider requirements without migrating blocked ingestion semantics.
- `register_fins_ingestion_tools` is not migrated in S4; read declarations remain available through `register_fins_read_tools`.
- OLD LLM-facing search hints that explicitly instructed `fetch_more` were rewritten to current next actions (`read_section` or narrower query) so S4 does not migrate OLD fetch-more projection semantics.

## Storage Boundary Proof

- `DefaultFinsRuntime.create()` constructs `FsCompanyMetaRepository`, `FsSourceDocumentRepository` and `FsProcessedDocumentRepository` from `build_fs_repository_set(workspace_root=...)`.
- `FinsToolService.__init__` accepts `CompanyMetaRepositoryProtocol`, `SourceDocumentRepositoryProtocol` and `ProcessedDocumentRepositoryProtocol`.
- Tests write fixture data through repository public APIs and execute read tools against that workspace.
- Fins import-boundary tests confirm no Fins module imports Host, Service, UI or Engine.

## Typed Config Parsing

- `workspace_root` must be a non-empty absolute path. Relative paths fail; no cwd/env fallback is used.
- `include_read_tools` defaults to `true`.
- `include_ingestion_tools` defaults to `false`; `true` raises fail-closed `ValueError`.
- `limits` is parsed into `FinsToolLimits` with positive-integer validation.

## Input / Response Projection Decisions

- Provider uses existing `_legacy_adapter` argument projection before entering migrated functions.
- Simple matching calls such as `get_document_sections(ticker, document_id)` pass through successfully.
- Representative array/scalar projection is covered by `search_document` with `queries=[...]` and by failure when `query` and `queries` are both supplied.
- Success values are current `ToolCompletedOutcome.result.value` without OLD `ok/value` nesting.
- Failures from adapter validation or OLD business exceptions project to current `ToolFailedOutcome`.

## ToolTruncateSpec Mapping

- Fins read tools declare current `dayu.contracts.tool_schema.ToolTruncateSpec`.
- OLD string strategies are mapped to `ToolTruncationStrategy.LIST_ITEMS` or `ToolTruncationStrategy.TEXT_CHARS`.
- OLD `continuation_hint` fields are not carried forward.
- Current ToolRuntime owns actual truncation and framework `fetch_more`.

## Validation

- `source .venv/bin/activate && pytest tests/fins -q`
  - Result: 10 passed.
- `source .venv/bin/activate && pytest tests/fins tests/tools/test_legacy_tool_adapter.py tests/runtime/test_tools_discovery.py`
  - Result: 34 passed.
- `source .venv/bin/activate && pytest tests/fins tests/tools/test_legacy_tool_adapter.py tests/runtime/test_tools_discovery.py tests/runtime/test_config_loader.py`
  - Result: 74 passed.
- `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## README Sync

- `dayu/fins/README.md`: added Fins boundary, read path, provider, ingestion status and extension constraints.
- `dayu/config/README.md`: documented `financial-tools` provider defaults, absolute workspace root requirement, limits and ingestion fail-closed behavior.
- `tests/README.md`: added `tests/fins` layer and fixture policy.

## Residual Risks

- fixed in current slice: Fins read tools discover and execute through current ToolsDiscovery/ToolRuntime; storage fixture uses repository APIs; current outcomes and truncate declarations are tested.
- assigned to later work unit: Fins ingestion tools require awaiting / wait-adapter semantics before migration.
- covered by later approved slice: Web tools provider remains outside S4.
- tracked by existing issue: WU-TOOLS-01 aggregate review should re-check migrated Fins import closure and provider semantics across all slices.

## Completion Status

Implementation complete for Slice S4. This pass stops before review / fix / re-review / commit / push / PR, as requested.
