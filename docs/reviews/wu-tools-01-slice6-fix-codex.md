# WU-TOOLS-01 Slice S6 Fix

Gate: fix
Work unit: WU-TOOLS-01
Slice: S6 - Combined Discovery / ToolRuntime Acceptance / Docs Closure
Agent: AgentCodex
Status: fix complete; stopped before review / re-review / commit / push / PR

## Fix Scope

Controller accepted finding A1 only. This fix updates `tests/host/test_import_boundary.py` and the matching `tests/README.md` description. No Host production code was changed.

## Changes

- `test_fetch_more_token_stays_inside_toolruntime_owner_modules`
  - Kept `fetch_more` ownership restricted to ToolRuntime / tooling owner files.
  - Added a narrow defensive allowlist for:
    - `tools/_legacy_adapter/__init__.py`
    - `tools/_legacy_adapter/definition_adapter.py`
    - `tools/_legacy_adapter/registry_collector.py`
  - Added explicit scan for OLD fetch-more projection tokens:
    - `fetch_more_args`
    - `project_for_llm`
    - `continuation_hint`
  - Business providers remain outside the allowlist, so provider-side `fetch_more` exposure is still rejected.
- `test_host_engine_imports_stay_on_allowed_boundary_modules`
  - Added `compaction_operation.py` to the Host -> Engine contract boundary allowlist because current accepted code imports Engine contract modules there.
- `tests/README.md`
  - Updated Host import-boundary description to match the current test contract.

## External Blockers Not Fixed

The following 11 broad Host failures remain external blockers / separate Host follow-up. They were intentionally not changed in this S6 fix:

- Proactive compaction tests failing with missing proposal manifest ref.
- One-system-message envelope assertion mismatches in effective execution config tests.
- Wait / resume tests expecting old `"Accepted wait result fact:"` text.

These are outside the accepted A1 fix and outside the narrow S6 fix scope.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py tests/tools/test_combined_tools_acceptance.py`
  - 21 passed, 3 third-party `edgar` deprecation warnings.
- `source .venv/bin/activate && pytest tests/tools/test_combined_tools_acceptance.py`
  - 8 passed, 3 third-party `edgar` deprecation warnings.
- `source .venv/bin/activate && pyright`
  - 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Passed; no whitespace errors.
