# Phase 12.1 Slice 1 Re-review Controller Adjudication 2026-05-21

## Inputs

- Fix addendum: `docs/reviews/phase12-1-slice1-implementation-codex-20260521.md`
- MiMo re-review: `docs/reviews/phase12-1-slice1-rereview-mimo-20260521.md`
- DS re-review: `docs/reviews/phase12-1-slice1-rereview-ds-20260521.md`
- Prior adjudication: `docs/reviews/phase12-1-slice1-code-review-controller-adjudication-20260521.md`

## Verdict

Slice 1 fix accepted. Both independent re-reviews returned PASS and confirmed the accepted findings were fixed without introducing new blockers.

## Confirmed Fixes

- MiMo F-1 / DS F1: `_command_context_budget_fields_from_open_host_options` now preserves explicit `ContextBudgetPolicy.context_window_size` instead of falling back to the internal default when policy is present.
- MiMo F-2: `_CommandContextBudgetFields` no longer carries stale internal `hard_threshold_tokens` / `minimum_protection_tokens` fields.

## Rejected / Deferred Findings

- DS F2 remains rejected for Slice 1. `MemoryProjectionPolicy.policy_ref` was not added, consistent with the controller adjudication.
- DS F3 remains deferred to Slice 2 / Slice 4. ToolRuntime truncation defaults were not replaced in this fix.

## Validation

Controller local rerun before re-review:

- `pytest tests/host/test_open_host_runtime.py::test_command_options_reflect_explicit_context_budget_policy -q`: 1 passed
- `pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py -q`: 75 passed
- `pytest tests/host/test_public_open_host_options.py tests/host/test_phase6_toolruntime_integration.py -q`: 8 passed
- `python -m pyright dayu/host dayu/contracts tests/host`: 0 errors
- `git diff --check`: clean

## Next Gate

Proceed to Phase 12.1 Slice 1 accepted local commit bookkeeping, then Slice 2 implementation through `$init-agents` routing.
