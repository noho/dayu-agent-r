# Phase 12.1 Slice 1 Re-review — AgentDS — 2026-05-21

## Verdict: PASS

All controller-accepted findings have been confirmed fixed. All rejected/deferred findings have been confirmed as NOT implemented in this slice. No new blockers introduced.

---

## Accepted Finding Confirmations

### DS F1 / MiMo F-1 — Fixed ✓

**Claim:** `_command_context_budget_fields_from_open_host_options` ignores explicit `ContextBudgetPolicy` and returns fallback values in both branches.

**Evidence (post-fix):**
- `dayu/host/open_host.py:585-598` — `if context_policy is None` branch returns `_INTERNAL_COMMAND_FALLBACK_CONTEXT_WINDOW_SIZE` (8192). The `else` branch (line 593-598) now returns `_CommandContextBudgetFields(context_window_size=context_policy.context_window_size, ...)`, reflecting the supplied policy.
- `dayu/host/open_host.py:601-616` — helper `_internal_reserved_output_tokens_for_policy` derives a positive reserved output smaller than context window, with explicit docstring noting this is an internal validation placeholder, not a ratio-first policy truth source.
- `tests/host/test_open_host_runtime.py:506-526` — `test_command_options_reflect_explicit_context_budget_policy` asserts `command_options.context_window_size == policy.context_window_size` (16384) and `command_options.local_execution.context_budget_policy is policy`.

**Confirmation:** Fixed. The non-None branch now correctly propagates `context_policy.context_window_size` into internal command options. The real `ContextBudgetPolicy` still reaches scheduler via `HostLocalExecutionOptions.context_budget_policy` (line 644).

### MiMo F-2 — Fixed ✓

**Claim:** `_CommandContextBudgetFields` keeps stale `hard_threshold_tokens` / `minimum_protection_tokens` that are always `None`.

**Evidence (post-fix):**
- `dayu/host/open_host.py:87-96` — `_CommandContextBudgetFields` now has only two fields: `context_window_size: int` and `reserved_output_tokens: int`. Stale `hard_threshold_tokens: int | None` and `minimum_protection_tokens: int | None` are removed.
- `dayu/host/open_host.py:564-565` — public `HostCommandHandleOptions` fields `context_budget_hard_threshold_tokens` and `context_budget_minimum_protection_tokens` are passed as `None` directly (those fields are frozen public surface, not internal).

**Confirmation:** Fixed. Stale internal fields removed without changing public option field names.

---

## Rejected/Deferred Finding Confirmations

### DS F2 (`MemoryProjectionPolicy.policy_ref`) — Rejected ✓

**Claim:** Rejected for current slice per controller adjudication.

**Evidence:**
- `grep policy_ref dayu/host/memory.py` returns no matches. `MemoryProjectionPolicy` has no `policy_ref` field.

**Confirmation:** Not implemented. As adjudicated.

### DS F3 (ToolRuntime truncation constants) — Deferred ✓

**Claim:** Deferred to Slice 2 / Slice 4 per controller adjudication.

**Evidence:**
- `dayu/host/tool_runtime.py:211-218` — `_DEFAULT_TRUNCATION_LIMITS_BY_STRATEGY` and `_DEFAULT_TRUNCATION_TTL_SECONDS` remain as local module-level constants.
- `dayu/host/tool_runtime.py:2193-2195` — Still consumed by `effective_tool_truncate_spec()` call in `EffectiveToolBundleBuilder`.

**Confirmation:** Unchanged. As adjudicated. No new blocker introduced.

---

## Validation Summary

Per controller local rerun (confirmed in fix addendum):

| Command | Result |
|---|---|
| `pytest tests/host/test_open_host_runtime.py::test_command_options_reflect_explicit_context_budget_policy -q` | 1 passed |
| `pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py -q` | 75 passed |
| `pytest tests/host/test_public_open_host_options.py tests/host/test_phase6_toolruntime_integration.py -q` | 8 passed |
| `pyright dayu/host dayu/contracts tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

## Changes In Fix Pass

| File | Change |
|---|---|
| `dayu/host/open_host.py` | `_CommandContextBudgetFields` reduced to 2 fields; `_command_context_budget_fields_from_open_host_options` non-None branch reflects `context_policy.context_window_size`; added `_internal_reserved_output_tokens_for_policy` helper |
| `tests/host/test_open_host_runtime.py` | Added `test_command_options_reflect_explicit_context_budget_policy` |
| `docs/reviews/phase12-1-slice1-implementation-codex-20260521.md` | Fix addendum section appended |

## Residual Risks

- **R1 (deferred):** `_DEFAULT_TRUNCATION_LIMITS_BY_STRATEGY` / `_DEFAULT_TRUNCATION_TTL_SECONDS` remain hardcoded. Owner: Slice 2/4.
- **R2 (rejected):** `MemoryProjectionPolicy.policy_ref` gap remains. Owner: future design discussion if needed.
- **No new residual risk** introduced by the fix pass.

## Review Stop

Re-review complete. No commits, pushes, PRs, or gates were started.
