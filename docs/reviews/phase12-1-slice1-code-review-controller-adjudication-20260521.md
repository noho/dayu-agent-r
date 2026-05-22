# Phase 12.1 Slice 1 Code Review Controller Adjudication 2026-05-21

## Inputs

- Implementation artifact: `docs/reviews/phase12-1-slice1-implementation-codex-20260521.md`
- MiMo review: `docs/reviews/phase12-1-slice1-code-review-mimo-20260521.md`
- DS review: `docs/reviews/phase12-1-slice1-code-review-ds-20260521.md`
- Plan: `docs/host/phase12-1-runtime-assembly-correction-plan.md`
- Design truth: `docs/host/design.md`
- Control truth: `docs/host/implementation-control.md`

## Verdict

Slice 1 requires a narrow fix before acceptance. Both reviewers agree the main implementation satisfies the phase goals, but `open_host.py` contains an incorrect context-budget command-option mapping that should be fixed before later slices build on this boundary.

## Findings Adjudication

### Accepted For Current Fix

- MiMo F-1 / DS F1: `_command_context_budget_fields_from_open_host_options` ignores explicit `ContextBudgetPolicy` and returns fallback values in both branches. Accepted. The fix must make the non-`None` branch reflect the supplied policy, at minimum preserving `context_window_size`, without changing public option field names.
- MiMo F-2: `_CommandContextBudgetFields` keeps stale internal fields `hard_threshold_tokens` / `minimum_protection_tokens` that are always `None`. Accepted as part of the same fix if it can be removed without changing public fields; otherwise the implementation artifact must explain why the internal shape is still needed.

### Rejected For Current Fix

- DS F2: add `policy_ref` to `MemoryProjectionPolicy`. Rejected for this slice. `docs/host/design.md` requires `policy_ref` for `ContextBudgetPolicy`; it does not require memory projection policy refs. Adding it now would expand public contract beyond the accepted design.

### Deferred With Owner

- DS F3: ToolRuntime default truncation constants are temporary until config / assembly policy is wired. Deferred to Slice 2 / Slice 4. The implementation agents for those slices must replace the local defaults with `tool_truncation_policy` assembly inputs or explicitly record why a stable code default remains.
- DS F4-F7 and MiMo PASS notes are accepted as non-blocking observations; no current fix required.

## Required Fix Scope

Allowed files for the fix:

- `dayu/host/open_host.py`
- narrowly affected Host tests proving explicit `OpenHostOptions.context_budget_policy` is reflected in command option mapping
- `docs/reviews/phase12-1-slice1-implementation-codex-20260521.md` fix addendum

Stop condition:

- focused tests for affected open_host / public option mapping pass
- original Slice 1 validation commands still pass or failures are reported
- pyright remains clean for `dayu/host dayu/contracts tests/host`
- no commit / push / PR
