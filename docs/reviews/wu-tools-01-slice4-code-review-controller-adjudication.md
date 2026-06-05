# WU-TOOLS-01 Slice S4 Code Review Controller Adjudication

Gate: code review adjudication
Work unit: WU-TOOLS-01
Slice: S4 - Fins Storage And Read Tools Provider
Controller: AgentController
Status: fix required

## Inputs

- AgentMiMo review: `docs/reviews/wu-tools-01-slice4-code-review-mimo.md`
- AgentDS review: `docs/reviews/wu-tools-01-slice4-code-review-ds.md`
- Controller validation:
  - `source .venv/bin/activate && pytest tests/fins tests/tools/test_legacy_tool_adapter.py tests/runtime/test_tools_discovery.py tests/runtime/test_config_loader.py` -> 74 passed, 3 edgar deprecation warnings
  - `source .venv/bin/activate && pyright` -> 0 errors
  - `git diff --check` -> clean

## Accepted Findings

### A1. New adapter signatures must not use `object`

Accepted from AgentDS and reinforced by Controller.

`dayu/tools/_legacy_adapter/tool_decorator.py` changed the decorator signature to `Callable[P, object]`. The root cause is real: Fins read tools return precise typed result dictionaries that are not assignable to the current `JsonValue` alias. However, AGENTS.md explicitly prohibits `object`, and this case has a better typed solution.

Required fix:

- Replace the decorator return typing with a `TypeVar`-based generic, for example `R = TypeVar("R")` and `Callable[[Callable[P, R]], LegacySyncToolCallable]`.
- Keep the internal cast to `LegacySyncToolCallable` if needed.
- Do not use `Any` or `object` in the new adapter signature.

### A2. `ToolArgumentError.arg_value` should not be widened to `object`

Accepted from AgentDS.

`dayu/tools/_legacy_adapter/exceptions.py` widened `arg_value` from `JsonValue | None` to `object | None`. S4 evidence does not require this. Current tool arguments enter from JSON call arguments and can stay `JsonValue | None`.

Required fix:

- Restore `arg_value: JsonValue | None`.
- Keep pyright green.

### A3. New Fins converter helpers must avoid `object` signatures

Accepted with scope narrowed from AgentDS F2.

`dayu/fins/_converters.py` is adapter/helper code introduced in the migrated package. It can express accepted scalar inputs with a local union type instead of `object`.

Required fix:

- Define a precise local scalar input alias such as `ScalarInput = str | int | float | bool | bytes | bytearray | SupportsInt | None`, or a more precise equivalent that pyright accepts.
- Replace the four `value: object` signatures with that alias.
- Avoid `hasattr` as a type escape hatch if the alias makes it unnecessary.

### A4. Fins tool factory return types should be precise

Accepted from AgentMiMo F1.

The nine `_create_*_tool` functions in `dayu/fins/tools/fins_tools.py` return `tuple[str, Any, Any]`, but the values are the collected tool name, decorated callable and current `ToolSchema`.

Required fix:

- Add a private alias such as `_ToolFactoryResult = tuple[str, LegacySyncToolCallable, ToolSchema]`.
- Import the precise symbols from current contracts / adapter.
- Update all factory return annotations to the alias.
- Do not rewrite inner tool business function signatures or bodies.

### A5. Small correctness/readability fixes that do not alter migration behavior

Accepted from AgentMiMo F3/F4/F5 and part of F2.

Required fix:

- Remove unused imports in `dayu/fins/service_runtime.py`.
- Fix `_resolve_service` docstring so it no longer says it can create a service.
- If changing `_resolve_service` to `service: FinsToolService` is pyright-clean and does not affect OLD business signatures, do it; otherwise leave the signature and only fix the docstring.
- Convert `tests/fins/test_fins_storage_provider.py` import-boundary checks from substring scanning to AST import scanning.
- Add a focused `include_read_tools=False` provider test.

## Deferred Or Rejected Findings

- Broadly rewriting migrated OLD Fins `Optional[...]` annotations is rejected for S4. Those are migrated OLD function signatures and should not be mechanically rewritten for style.
- Removing `timeout_budget` from `register_fins_read_tools(...)` is rejected. This parameter exists in OLD read registration and is currently an ignored legacy registration parameter, similar to S3 Doc registration. Keeping it is consistent with the migration principle.
- Requiring every Fins read tool to execute through ToolRuntime accept path is rejected as a blocker. The S4 plan requires `list_documents` and one read/search tool through current ToolRuntime; current tests cover `list_documents` and `search_document` through ToolRuntime plus a direct provider-definition call for `get_document_sections`.
- Processor depth, unsupported financial statement/XBRL paths, and limits boundary combinations are deferred to later WU-TOOLS aggregate review or targeted parity tests.

## Required Fix Gate

Dispatch AgentCodex for a narrow fix. After fix, run:

- `source .venv/bin/activate && pytest tests/fins tests/tools/test_legacy_tool_adapter.py tests/runtime/test_tools_discovery.py tests/runtime/test_config_loader.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`

Then dispatch AgentMiMo and AgentDS re-review on accepted findings only.
