# Phase 12 Aggregate Fix Codex 20260521

## Gate

Phase 12 aggregate fix.

## Source Finding

`docs/reviews/phase12-aggregate-controller-validation-finding-20260521.md`

## Accepted Finding

`tests/contracts/test_package_exports.py::test_contracts_all_matches_expected_set`
reported `ToolBundleSourceKind` and `ToolBundleSourceRef` as extra exports.

## Root Cause

Phase 12 moved canonical `ToolBundle` source reference ownership into
`dayu.contracts`, and `dayu/contracts/__init__.py` intentionally exports
`ToolBundleSourceKind` and `ToolBundleSourceRef`. The contracts package export
whitelist test was not updated with the same public contract boundary.

## Fix

Updated `EXPECTED_EXPORTS` in
`tests/contracts/test_package_exports.py` to include:

- `ToolBundleSourceKind`
- `ToolBundleSourceRef`

No production exports were removed. No compatibility wrappers, facades, or
re-export-only shims were added.

## Changed Files

- `tests/contracts/test_package_exports.py`
- `docs/reviews/phase12-aggregate-fix-codex-20260521.md`

## Validation

- `source .venv/bin/activate && pytest tests/contracts tests/engine/test_config_models.py tests/host/test_tooling_options.py tests/host/test_package_exports.py -q`
  passed: `69 passed in 0.84s`.
- `source .venv/bin/activate && pytest tests/runtime -q`
  passed: `174 passed in 3.86s`.
- `source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/host tests/contracts tests/runtime tests/host tests/engine/test_config_models.py`
  passed: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  passed.

## Residual Risk

No new residual risk identified. The change only synchronizes the test
whitelist with the already intentional contracts package public exports.
