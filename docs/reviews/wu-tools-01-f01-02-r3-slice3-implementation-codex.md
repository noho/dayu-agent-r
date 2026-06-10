# WU-TOOLS-01-F01-02-R3 Slice 3 Implementation Artifact

## Gate / Scope

- Gate: implementation
- Slice: Slice 3: Fins Read Native Tools
- Implementer: Codex
- Scope: only Fins read provider, Fins read tools, Fins read runtime error/cancellation types, Fins storage provider tests.
- Non-goals honored: did not delete `dayu.tools._legacy_adapter`; did not implement Slice 4; did not implement WU-TOOLS-01-F08; did not change Fins storage or read runtime public contract.

## First-principles Judgment

The slice motivation is valid. The behavior bug is not in Fins storage: legacy read tools raised cancellation as a business failure, and the legacy adapter projected that into `ToolFailedOutcome(error="tool_cancelled")`. Native Fins read callables are the correct boundary for fixing this because `ToolCancelledOutcome(reason="host_cancelled")` is already part of the current tool outcome contract.

## Changed Files

- `dayu/fins/tools/provider.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/tools/search_engine.py`
- `tests/fins/test_fins_storage_provider.py`

## Implementation Summary

- Replaced the provider legacy collector/adaptation path with `build_fins_read_tool_definitions(read_runtime, limits)`.
- Kept provider behavior: `include_read_tools=false` returns empty definitions without parsing `workspace_root`; enabled read tools still require a non-empty absolute `workspace_root`.
- Kept storage boundary: provider still constructs read runtime through `DefaultFinsRuntime.create(workspace_root=...).get_read_runtime(...)`.
- Built nine native read `ToolDefinition`s in the required order:
  `list_documents`, `get_document_sections`, `read_section`, `search_document`, `list_tables`, `get_table`, `get_page_content`, `get_financial_statement`, `query_xbrl_facts`.
- Added one `asyncio.Lock()` inside the builder and shared it across all nine callables, preserving per-provider serialization.
- Replaced legacy `ToolArgumentError` / `ToolBusinessError` usage in Fins read runtime/search helpers with Fins-local typed errors:
  `FinsReadArgumentError`, `FinsReadBusinessError`, `FinsReadCancelledError`.
- Native callables now map:
  - schema/argument failures to `ToolFailedOutcome(error="invalid_argument")`;
  - Fins business failures to failed outcome with existing business error code/message/hint;
  - Host cancellation to `ToolCancelledOutcome(reason="host_cancelled")`;
  - unexpected exceptions to `execution_error`.
- Search diagnostics are still stripped before returning `search_document` to the LLM-facing result.

## Tests / Coverage Changes

- Migrated Fins storage provider helper from legacy collector/adapted definitions to native `build_fins_read_tool_definitions`.
- Updated six cancellation tests to assert `ToolCancelledOutcome`, `reason=host_cancelled`, and basic meta fields.
- Added source assertion covering Fins read provider/tools/runtime/search/test helper no longer depending on the retired adapter path.
- Added same-provider concurrency test proving two read tools do not concurrently enter read runtime business methods.

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py`
  - Result: passed, 21 tests.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -k cancellation`
  - Result: passed, 1 selected test.
- `source .venv/bin/activate && pyright`
  - Result: passed, 0 errors.
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools|ToolBusinessError\\(.*tool_cancelled" dayu/fins/tools tests/fins/test_fins_storage_provider.py`
  - Result: no matches.
- `git diff --check`
  - Result: passed.

## README Decision

- Checked `dayu/fins/README.md` Agent update constraints and `tests/README.md` update boundary.
- No README update made: this slice changes implementation path from legacy adapter to native current definitions, but does not change documented Fins package capabilities, storage boundary, read tool list, provider behavior, test layer taxonomy, or maintenance rules.

## Residual Risks

- No unclassified residual risk for Slice 3.
- Legacy adapter deletion remains covered by later approved Slice 4.
- Summary params from the retired decorator had no field in current `ToolDefinition`; current Doc/Web native slices already use the same current declaration surface. No new public contract was introduced to preserve adapter-only metadata.

## Completion Status

Slice 3 implementation is complete and ready for code review. No commit was created.

