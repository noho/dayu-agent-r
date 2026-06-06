# WU-TOOLS-01 Slice S4 Re-Review Controller Adjudication

Gate: re-review adjudication
Work unit: WU-TOOLS-01
Slice: S4 - Fins Storage And Read Tools Provider
Controller: AgentController
Status: accepted for slice commit

## Inputs

- Fix artifact: `docs/reviews/wu-tools-01-slice4-fix-codex.md`
- AgentMiMo re-review: `docs/reviews/wu-tools-01-slice4-rereview-mimo.md`
- AgentDS re-review: `docs/reviews/wu-tools-01-slice4-rereview-ds.md`

## Decision

AgentMiMo and AgentDS both passed the accepted fix scope. S4 is accepted for final validation and slice commit.

## Accepted Fix Results

- A1: `tool_decorator.py` no longer uses `object` / `Any`; `_DecoratedToolReturn` marker Protocol is accepted as a declaration-stage return marker because runtime return validation/projection belongs to the adapter execution path.
- A2: `ToolArgumentError.arg_value` is back to `JsonValue | None`, with Fins query-list call sites projecting to `list[JsonValue]`.
- A3: Fins converter helpers use `ScalarInput` and no longer use `object` or `hasattr` as a type escape.
- A4: Fins read tool factories use `_ToolFactoryResult = tuple[str, LegacySyncToolCallable, ToolSchema]`; inner migrated tool signatures/bodies were not rewritten.
- A5: Unused imports, `_resolve_service` wording/signature, AST import-boundary tests, `include_read_tools=False` coverage, and README sync are complete.

## Deferred Residuals

The following remain deferred as previously adjudicated:

- Broad OLD Fins `Optional[...]` / `Any` style cleanup.
- Removing `register_fins_read_tools(timeout_budget=...)`.
- Full ToolRuntime accept-path execution for every Fins read tool.
- Processor / XBRL / financial-statement deep parity coverage.
- Fins ingestion migration, which requires a later waiting / awaiting semantics work unit.

## Validation Evidence

Controller re-ran after fix:

- `source .venv/bin/activate && pytest tests/fins tests/tools/test_legacy_tool_adapter.py tests/runtime/test_tools_discovery.py tests/runtime/test_config_loader.py` -> 75 passed, 3 edgar deprecation warnings
- `source .venv/bin/activate && pyright` -> 0 errors, 0 warnings
- `git diff --check` -> clean

No additional fix gate is required.
