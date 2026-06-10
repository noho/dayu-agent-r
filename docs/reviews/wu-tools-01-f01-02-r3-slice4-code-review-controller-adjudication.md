# WU-TOOLS-01-F01-02-R3 Slice 4 Code Review Controller Adjudication

## Gate

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: Slice 4: Legacy Adapter Deletion
- Gate: code review adjudication
- Controller: AgentController

## Inputs

- Implementation artifact: `docs/reviews/wu-tools-01-f01-02-r3-slice4-implementation-codex.md`
- MiMo review: `docs/reviews/wu-tools-01-f01-02-r3-slice4-code-review-mimo.md`
- DS review: `docs/reviews/wu-tools-01-f01-02-r3-slice4-code-review-ds.md`

## Reviewer Results

- MiMo verdict: `PASS`
- DS verdict: `PASS`
- Blocking findings: none

## Accepted Findings

### S4-CR-01: Keep focused Doc provider import boundary coverage

- Source: DS Finding 1
- Severity: low
- File: `tests/tools/test_doc_tools_provider.py`
- Decision: accepted

Reasoning:

Slice 4 correctly removed `_legacy_adapter` symbol assertions from Doc provider tests to satisfy the final `rg` zero-match requirement across `dayu` and `tests`. However, that edit also removed the local source read for `dayu/tools/doc_provider.py`, leaving the focused Doc provider test to check only `doc_tools.py` for old Engine runtime imports. Combined acceptance still scans `doc_provider.py`, so this is not a correctness blocker, but keeping a focused Doc provider import-boundary assertion is a useful low-cost guard.

Required fix:

- Restore reading `dayu/tools/doc_provider.py` inside `test_read_tools_expose_current_truncate_spec_and_no_old_imports`.
- Run `_imported_modules(...)` on both `doc_tools.py` and `doc_provider.py`.
- Assert neither file imports `dayu.engine.tool_registry`, `dayu.engine.truncation_manager`, or `dayu.engine.tool_result`.
- Do not reintroduce `_legacy_adapter`, `LegacyToolDeclarationCollector`, or `adapt_collected_tools` string assertions.

## Rejected / Non-Actionable Findings

### MiMo Finding 1: `_native_tool_source_paths` does not scan Doc provider in combined acceptance

Decision: no fix required. Combined acceptance currently includes explicit `doc_provider.py` / `doc_tools.py` paths, and DS independently confirmed that coverage. The accepted fix keeps focused Doc provider coverage too.

### MiMo Finding 2: `dayu/fins/README.md` was updated though listed as conditional

Decision: no fix required. Slice 4 allowed README updates when triggered and necessary. The Fins README referenced the retired `register_fins_read_tools(...)` name and now accurately points to `build_fins_read_tool_definitions(...)`.

### DS Finding 2: Web local `ToolBusinessError` name may confuse future searches

Decision: no fix in Slice 4. This is a Web-domain local type, not a legacy adapter dependency or compatibility re-export. Renaming it would be unrelated cleanup and risks churn after Slice 2 acceptance.

## Controller Validation Before Fix

- `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py tests/host/test_import_boundary.py tests/service/test_import_boundary.py`: passed, 108 tests.
- `source .venv/bin/activate && pyright`: passed, 0 errors.
- `git diff --check`: passed.
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests`: no matches.

## Next Gate

Dispatch AgentCodex fix for `S4-CR-01`, then run focused re-review.
