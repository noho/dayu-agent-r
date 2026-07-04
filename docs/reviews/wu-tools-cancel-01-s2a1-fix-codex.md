# WU-TOOLS-CANCEL-01 S2A1 Fix — Codex

## Scope

- Work unit: `WU-TOOLS-CANCEL-01`
- Slice: `S2A1 contract / declaration / digest`
- Trigger: code review advisory from `docs/reviews/wu-tools-cancel-01-s2a1-code-review-ds.md`

## Accepted Finding

Accepted DS F01 advisory: `utils/` contained three `ToolDefinition(...)` construction sites that relied on `ToolDefinition.execution`'s default factory instead of explicitly declaring execution capability.

Although the accepted plan required the mandatory scan over `dayu` and `tests`, explicitly migrating `utils` keeps all local direct construction sites aligned and removes future semantic drift risk.

## Fix

Added `execution=AsyncDirectToolExecutionCapability()` to:

- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`

No production dispatch, Host factory wiring, Doc/Fins/Web process-backed migration, Engine contract, durable schema, or runtime process helper changes were made.

## Validation

- `source .venv/bin/activate && pyright` -> passed, `0 errors`.
- `source .venv/bin/activate && pytest tests/contracts/test_tool_declaration.py tests/contracts/test_package_exports.py tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q` -> passed, `35 passed`.
- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/fins/test_fins_ingestion_tools.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_effective_bundle.py tests/host/test_tool_runtime_schema_projection.py -q` -> passed, `115 passed`, with existing third-party `edgar` deprecation warnings.
- `git diff --check` -> passed.
- Direct construction scan over `dayu`, `tests`, and `utils` -> passed; all `ToolDefinition(...)` blocks include `execution=`.
