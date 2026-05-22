# Phase 12.1 Slice 1 Re-Review — MiMo — 2026-05-21

## Gate

- Re-review scope: Accepted findings fix verification only.
- Controller adjudication: `docs/reviews/phase12-1-slice1-code-review-controller-adjudication-20260521.md`.
- Implementation artifact with fix addendum: `docs/reviews/phase12-1-slice1-implementation-codex-20260521.md`.
- Original review: `docs/reviews/phase12-1-slice1-code-review-mimo-20260521.md`.

## Verification

### MiMo F-1 [Medium] — CONFIRMED FIXED

**Original defect:** `_command_context_budget_fields_from_open_host_options` returned identical fallback `context_window_size=8192` in both the `context_policy is None` and `context_policy is not None` branches.

**Fix applied** (`dayu/host/open_host.py:589-598`):

- `context_policy is None` branch: returns fallback `_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE` — unchanged.
- `context_policy is not None` branch: now returns `_CommandContextBudgetFields(context_window_size=context_policy.context_window_size, ...)` — policy's window size is preserved.

**Derived reserved_output_tokens:** `_internal_reserved_output_tokens_for_policy(context_window_size)` returns `min(_INTERNAL_COMMAND_FALLBACK_RESERVED_OUTPUT_TOKENS, context_window_size - 1)`, guaranteeing `0 < reserved < context_window_size` as required by `_context_budget_policy_from_command_options` validation.

**Direct evidence:** `open_host.py:593-597` — the `return _CommandContextBudgetFields(context_window_size=context_policy.context_window_size, ...)` line uses the policy value, not the fallback constant.

**Focused test** (`test_open_host_runtime.py:506-525`): `test_command_options_reflect_explicit_context_budget_policy` creates a policy with `context_window_size=16384`, maps it through `_command_options_from_open_host_options`, and asserts:
- `command_options.context_window_size == policy.context_window_size` (16384, not 8192)
- `0 < command_options.reserved_output_tokens < policy.context_window_size`
- `command_options.local_execution.context_budget_policy is policy`

PASS.

### MiMo F-2 [Low] — CONFIRMED FIXED

**Original defect:** `_CommandContextBudgetFields` dataclass kept stale fields `hard_threshold_tokens: int | None` and `minimum_protection_tokens: int | None` that were always `None`.

**Fix applied** (`open_host.py:88-96`):

- `_CommandContextBudgetFields` reduced to `context_window_size: int` and `reserved_output_tokens: int` only.
- `_command_options_from_open_host_options` (line 564-565) passes `None` directly for `context_budget_hard_threshold_tokens` and `context_budget_minimum_protection_tokens` in the `HostCommandHandleOptions` constructor, bypassing the intermediate dataclass.
- Docstring updated to remove stale field descriptions.

**Public field names unchanged:** `HostCommandHandleOptions.context_budget_hard_threshold_tokens` and `context_budget_minimum_protection_tokens` field names remain intact in `api.py`. Only the internal mapping dataclass was simplified.

PASS.

### No new blocker introduced by the fix

**Diff scope:** Only `dayu/host/open_host.py` changed. No new imports, no new public surface, no new dependencies.

**New helper:** `_internal_reserved_output_tokens_for_policy` is a module-private pure function that returns `min(fallback, window - 1)`. No side effects, no external dependencies.

**Test validation (controller-reported):**
- Focused test: 1 passed
- Slice 1 policy/truncation tests: 75 passed
- Public open host / phase6 integration tests: 8 passed
- pyright `dayu/host dayu/contracts tests/host`: 0 errors
- `git diff --check`: clean

No new blocker found.

## Verdict

**PASS.** Both accepted findings (F-1, F-2) are confirmed fixed with direct code evidence. No new blocker introduced by the fix. Slice 1 is ready for acceptance.
