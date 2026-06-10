# WU-TOOLS-01-F01-02-R3 Slice 1 Implementation

## Work Unit / Slice / Gate

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: Slice 1, Doc Native Tools
- Gate: implementation
- Scope: only Doc tools; Web, Fins, Host, Engine, Service, ToolRuntime and legacy adapter are not modified.

## Changed Files

- `dayu/tools/doc_provider.py`
- `dayu/tools/doc_tools.py`
- `tests/tools/test_doc_tools_provider.py`
- `docs/reviews/wu-tools-01-f01-02-r3-slice1-implementation-codex.md`

## Implemented

- Replaced Doc provider legacy collector / adapter path with native `build_doc_tool_definitions(limits, allowed_roots)`.
- Kept provider id, version ref, source ref, config parsing, `allowed_paths` parsing and fail-closed empty output when no allowed roots are configured.
- Added native async `ToolCallable` implementations for:
  - `list_files`
  - `get_file_sections`
  - `search_files`
  - `read_file`
  - `read_file_section`
- Added one provider-level `asyncio.Lock` inside `build_doc_tool_definitions`; all five callables share it.
- Moved current callable boundary behavior into Doc native code:
  - `validate_and_project_arguments(...)`
  - `completed_outcome(...)`
  - `failed_outcome(...)`
  - `host_cancelled_outcome(...)`
- Kept provider-local path validation with explicit allowed roots, `must_exist=True`, fail-closed behavior, and no business function entry on invalid path.
- Preserved list/search return-path projection so `files[].path` and `matches[].file` can chain directly into read tools.
- Replaced legacy `ToolBusinessError(code="tool_cancelled")` cancellation path with `ToolBusinessCancelled` carried by a Doc-local cancellation signal and projected to `ToolCancelledOutcome(reason="host_cancelled")`.

## Schema Conclusion

- Tool names are unchanged.
- LLM-facing parameter names, required fields, defaults, descriptions, display names, tags and truncate specs are intended unchanged.
- No Host governance fields are exposed in Doc schemas: tests cover absence of `execution_context` and `cancellation_token`.
- Success and failure outcomes do not reintroduce OLD `ok/value` response envelopes.

## Cancellation Conclusion

- Pre-cancel checks for all five Doc tools now return `ToolCancelledOutcome` with reason `host_cancelled`.
- In-loop cancellation tests cover:
  - `search_files` stops after the first scanned file when cancellation is requested during iteration.
  - `read_file` stops after the first failed encoding when cancellation is requested before fallback encodings.
- No Doc native path uses `ToolFailedOutcome(error="tool_cancelled")`.

## Validation

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py`
  - Result: passed, 22 tests.
- `source .venv/bin/activate && pytest tests/tools/test_combined_tools_acceptance.py -k doc`
  - Result: passed, 1 selected / 7 deselected.
  - Notes: third-party `edgar` deprecation warnings only.
- `source .venv/bin/activate && pyright`
  - Result: passed, 0 errors.
- `git diff --check`
  - Result: passed.

## Docs Decision

- `tests/README.md` was checked because tests changed.
- No README update was made: this slice changed existing Doc provider tests but did not add a test layer, test command, or maintenance rule under the README update boundary.
- No Host / Engine / Fins / config README trigger applied.

## Residual Risks / Uncovered Areas

- Web and Fins read tools still depend on legacy adapter paths by design; they are out of Slice 1 scope.
- Legacy adapter deletion is intentionally deferred to later slices.
- Doc business IO remains cooperative cancellation only; no physical interruption of already-running blocking filesystem work is introduced in this slice.

## Stop Condition Status

- No Doc tool name, LLM-facing parameter schema, or return shape change was required.
- No public contract, ToolRuntime, Host, Engine, Service, Web, Fins, or legacy adapter change was required.
- Allowed paths semantics were preserved provider-locally without requiring a broader path helper.
