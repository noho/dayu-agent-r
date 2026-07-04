# WU-TOOLS-CANCEL-01 S2C Fix

## Scope

- Work unit: WU-TOOLS-CANCEL-01
- Slice: S2C Fins read process-backed
- Gate: code review fix
- Source findings:
  - `docs/reviews/wu-tools-cancel-01-s2c-code-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-s2c-code-review-ds.md`

## Execution Note

AgentCodex started the narrow fix and completed the production-code edits plus the new test skeleton, but its pane did not finish after the 600s wait budget and produced no artifact. AgentController interrupted the stuck pane, completed the missing fixture helper, and ran validation.

## Changes

- Added process-backed spawned-child coverage for `get_financial_statement`, using a real temporary Fins workspace and a stored HTML 10-K primary document. This covers the `FinancialDataProcessor` process-boundary path through `ProcessBackedToolExecutionCapsule`.
- Updated `_FinsReadProcessTarget.__call__` generic failed envelope message to append the existing recovery hint via `Hint: ...`.
- Renamed the direct fallback cancellation helper to `_build_fins_read_cancelled_outcome` and documented that it intentionally does not read Host token reason, avoiding Host governance leakage into LLM-facing text.

## Validation

Passed:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py::test_fins_read_financial_statement_runs_in_spawned_child -q
source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py -q
source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q
source .venv/bin/activate && pyright
git diff --check
```

Observed:

- `test_fins_read_financial_statement_runs_in_spawned_child`: 1 passed, 3 third-party `edgar` deprecation warnings.
- `tests/fins/test_fins_storage_provider.py`: 31 passed, 3 third-party `edgar` deprecation warnings.
- `tests/host/test_toolruntime_executor.py`: 55 passed.
- `pyright`: 0 errors, 0 warnings, 0 informations.
- `git diff --check`: passed.

## Residual Risk

- `query_xbrl_facts` itself still is not executed in a spawned child with a real XBRL instance fixture. The fix covers the distinct `FinancialDataProcessor` process-boundary route with `get_financial_statement`; table and processor paths remain covered by existing S2C tests.
