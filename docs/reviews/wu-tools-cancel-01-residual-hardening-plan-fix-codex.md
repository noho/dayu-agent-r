# WU-TOOLS-CANCEL-01 Residual Hardening Plan Fix

## Metadata

- Work unit: `WU-TOOLS-CANCEL-01 residual hardening reopen`
- Gate: plan-fix
- Updated plan: `docs/host/wu-tools-cancel-01-residual-hardening-plan.md`
- Reviewed artifacts:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-review-mimo.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-review-ds.md`
  - `docs/reviews/plan-review-20260705-141254.md`
- Scope: plan text fixes only. No production code implementation, no commit, no push, no PR update.

## Fix Summary

All controller-accepted review items were applied as plan text fixes.

| Item | Status | Plan update |
|---|---|---|
| Playwright cleanup direction | Fixed | Removed reuse-or-mirror ambiguity. S2 now requires shared process-group cleanup primitives in `dayu.runtime.interruptible_process`, callable by both `InterruptibleProcessHandle` and Playwright's raw process path, without duplicating logic or forcing full Playwright migration unless evidence proves it necessary. |
| Policy wiring path | Fixed | S1 now specifies the exact active call path: `HostToolingOptions` -> `ToolRuntimeBuildRequest` -> `DefaultToolRuntimeFactory.create_tool_runtime(...)` -> `DeclaredToolExecutionCapsuleFactory.__init__(...)` -> `DeclaredToolExecutionCapsuleFactory.create_capsule(...)` -> `_declared_capsule_for_execution(...)` -> `ProcessBackedToolExecutionCapsule(...)`. |
| Hardcoded grace constants validation | Fixed | S1 tests and final validation now require `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS` and `_PROCESS_CAPSULE_KILL_GRACE_SECONDS` to be removed from the active ToolRuntime code path. |
| Grace tuning clarity | Fixed | Plan now states the typed dataclass is the single source of default truth, missing config falls through to typed defaults, and S2B must validate or adjust named defaults using nested/Playwright smoke timing evidence. |
| NaN/inf/bool/negative validation | Fixed | Plan now explicitly requires rejection tests for `bool`, negative values, `float("nan")`, `float("inf")`, and `float("-inf")` in both policy validation and runtime grace validation. |
| POSIX signaling strategy | Fixed | Plan now requires direct child PID signaling first and process-group signaling only after confirming child pgid differs from current/parent pgid, with fallback when pgid is unavailable or unchanged. |
| Playwright smoke claim scope | Fixed | Success signal and S2B now limit deterministic smoke claims to synthetic nested-child cleanup; real Chromium cleanup is only claimed if optional/manual browser-backed smoke runs. |
| Envelope constant grep scope | Fixed | S3 now requires preventing any local `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, or `_WEB_PROCESS_*` envelope constants from reappearing, not only status field constants. |
| `ProcessBackedToolTarget` docstring | Fixed | S1 now explicitly requires updating the public process target protocol docstring with optional failed-envelope `hint`. |
| S2 scope split / stop behavior | Fixed | S2 was split into S2A runtime process-group primitive and S2B Playwright cleanup smoke, with explicit dependency and stop behavior when OS-specific runtime cleanup is unsupported or unsafe. |

## Residual Risks

- Real Chromium process tree cleanup remains environment-dependent unless the optional/manual browser-backed smoke can run in the implementation environment.
- AAPL XBRL fixture suitability remains an implementation-time validation item; the plan retains the stop condition against inventing facts or using network-dependent taxonomy resolution.
- Windows process-group behavior remains unsupported/fallback unless separately implemented and tested.

## Validation

Planned for this plan-fix gate:

```bash
git diff --check
git status --short
```

No code tests or pyright were run because this gate only updates plan/review documentation and does not modify production code.

## Completion Status

READY_FOR_CONTROLLER

Artifact: `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-fix-codex.md`

Updated plan: `docs/host/wu-tools-cancel-01-residual-hardening-plan.md`

Blocking open question: None
