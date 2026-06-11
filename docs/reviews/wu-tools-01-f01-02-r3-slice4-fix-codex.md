# WU-TOOLS-01-F01-02-R3 Slice 4 Fix

## Gate / Scope

- Gate: fix
- Slice: Slice 4, Legacy Adapter Deletion and Boundary Closeout
- Work unit: WU-TOOLS-01-F01-02-R3
- Accepted finding: S4-CR-01, from DS Finding 1
- Scope constraint: only `tests/tools/test_doc_tools_provider.py` and this fix artifact were modified.

## First-principles Judgment

S4-CR-01 is valid. Combined acceptance still scans current provider sources, so the deleted `doc_provider.py` scan did not leave the migration wholly uncovered. However, the Doc provider focused test is the narrower ownership boundary for Doc native provider behavior. Restoring the AST import scan there reduces regression risk without reintroducing retired adapter symbol references.

## Fix

- Updated `test_read_tools_expose_current_truncate_spec_and_no_old_imports` to read both `dayu/tools/doc_tools.py` and `dayu/tools/doc_provider.py`.
- Added `_imported_modules(...)` checks for `doc_provider.py` through the same OLD runtime module denylist:
  - `dayu.engine.tool_registry`
  - `dayu.engine.truncation_manager`
  - `dayu.engine.tool_result`
- Did not restore `_legacy_adapter`, `LegacyToolDeclarationCollector`, or `adapt_collected_tools` string assertions, preserving the Slice 4 zero-match requirement under `dayu` and `tests`.

## Validation

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py`
  - Result: 36 passed, 3 edgar deprecation warnings.
- `source .venv/bin/activate && pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py tests/tools/test_combined_tools_acceptance.py tests/host/test_import_boundary.py tests/service/test_import_boundary.py`
  - Result: 108 passed, 3 edgar deprecation warnings.
- `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed, no output.
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests`
  - Result: no matches.

## Residual Risk

- No production code was changed.
- No README update was needed because the fix only restores a focused test guard and records this fix gate.
