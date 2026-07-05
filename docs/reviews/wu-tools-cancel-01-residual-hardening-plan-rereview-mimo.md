# WU-TOOLS-CANCEL-01 Residual Hardening Plan Re-Review (MiMo)

## Reviewed Target

- **Updated plan**: `docs/host/wu-tools-cancel-01-residual-hardening-plan.md`
- **Fix artifact**: `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-fix-codex.md`
- **Prior review**: `docs/reviews/wu-tools-cancel-01-residual-hardening-plan-review-mimo.md`
- **Scope**: re-review only; confirm whether prior findings F01-F05 are fixed or acceptable.

## Prior Findings Status

### F01-MEDIUM-Playwright cleanup reuse vs mirror — **CLOSED (fixed)**

**Prior issue**: S2 used "reuse ... or mirror" as a disjunction, leaving an unresolved design decision.

**Fix applied**: The plan now has S2A and S2B as separate slices. S2A extracts shared process-group cleanup primitives to `dayu.runtime.interruptible_process`. S2B requires Playwright to call those shared primitives ("Replace Playwright raw process cleanup's direct terminate/kill helper with calls to the shared runtime process-group cleanup primitive. Do not duplicate logic in Web code."). The "or" is resolved: shared primitives, not mirror. Full migration to `InterruptibleProcessHandle` is explicitly not forced unless implementation evidence proves it necessary.

**Verification**: `plan.md:129` — "Extract/share minimal process-group cleanup primitives in `dayu.runtime.interruptible_process`. `InterruptibleProcessHandle` and the Playwright raw `multiprocessing.Process` path must call the same primitives; do not duplicate process-group logic in Web code and do not force a larger full migration to `InterruptibleProcessHandle` unless implementation evidence proves the raw path cannot safely use the shared primitive." `plan.md:223` — "Replace Playwright raw process cleanup's direct terminate/kill helper with calls to the shared runtime process-group cleanup primitive. Do not duplicate logic in Web code."

**Verdict**: ✓ Fixed. The directive is clear and actionable.

---

### F02-LOW-Grace policy defaults defer tuning — **CLOSED (fixed)**

**Prior issue**: Plan accepted 0.2/0.2 as defaults and deferred tuning without guidance.

**Fix applied**: Plan now states "Initial named defaults may preserve current behavior (`0.2` / `0.2`) only if S2A/S2B smoke timing validates them. S2B must measure or otherwise assert SIGTERM-to-exit behavior for the nested/Playwright smoke and adjust the named defaults upward if the current values are insufficient." S2B also includes: "S2B must measure or assert SIGTERM-to-exit timing for the synthetic nested worker path and use that evidence to validate or adjust `ProcessCapsuleInterruptPolicy` named defaults."

**Verification**: `plan.md:117` and `plan.md:227`.

**Verdict**: ✓ Fixed. Tuning is now tied to measurable evidence from S2B smoke timing.

---

### F03-LOW-`_validate_grace_seconds` doesn't validate NaN/infinity — **CLOSED (fixed)**

**Prior issue**: Plan's validation requirement was correct but S1 tests didn't explicitly enumerate rejection cases.

**Fix applied**: S1 tests now require: "explicitly including `bool`, negative values, `float('nan')`, `float('inf')`, and `float('-inf')`." Runtime grace validation tests cover the same cases. Final validation also checks: "Grace policy and runtime grace validation reject `bool`, negative values, NaN, `+inf`, and `-inf`."

**Verification**: `plan.md:118`, `plan.md:168`, `plan.md:169`, `plan.md:320`.

**Verdict**: ✓ Fixed. Explicit enumeration of all invalid input types.

---

### F04-LOW-`os.setsid` race window — **CLOSED (fixed)**

**Prior issue**: Plan didn't specify the signaling strategy for the race between parent signaling and child calling `os.setsid()`.

**Fix applied**: Plan now specifies: "POSIX signaling must avoid killing the parent process group. Signal the direct child PID first, then use process-group signaling only after confirming `os.getpgid(child_pid)` is available and differs from the current/parent process group. If pgid lookup fails, the child has exited, or the child pgid is unavailable/unchanged, fall back to direct-child cleanup and record the limitation in diagnostics/tests." S2A tests explicitly cover "fallback when pgid is unavailable, unchanged, or otherwise unsafe to signal as a group."

**Verification**: `plan.md:130`, `plan.md:192`, `plan.md:200`.

**Verdict**: ✓ Fixed. The signaling strategy is explicit and the fallback is tested.

---

### F05-LOW-S2 scope could be tightened — **CLOSED (fixed)**

**Prior issue**: S2 combined runtime process-group cleanup with Playwright cleanup smoke in a single slice.

**Fix applied**: S2 is now split into S2A (Runtime Process Group Cleanup Primitive) and S2B (Playwright Cleanup Smoke). S2B has explicit prerequisites ("S2A shared primitive exists, or S2A has explicitly classified process-group cleanup as unsupported/fallback on the current OS") and stop conditions ("If S2A process-group cleanup is unsupported or unsafe on the current OS, S2B must not claim nested Playwright cleanup").

**Verification**: `plan.md:178-205` (S2A), `plan.md:207-238` (S2B), `plan.md:326` (slice count justification).

**Verdict**: ✓ Fixed. S2A and S2B are properly separated with clear dependency and stop behavior.

---

## New Issues Check

No new material issues were introduced by the fix. Verified:

1. **Policy wiring path**: `plan.md:161` specifies `HostToolingOptions` -> `ToolRuntimeBuildRequest` -> `DefaultToolRuntimeFactory.create_tool_runtime(...)` -> `DeclaredToolExecutionCapsuleFactory.__init__(...)` -> `DeclaredToolExecutionCapsuleFactory.create_capsule(...)` -> `_declared_capsule_for_execution(...)` -> `ProcessBackedToolExecutionCapsule(...)`. This matches the actual code structure at `tool_runtime.py:3941`, `tool_runtime.py:1544`, `tool_runtime.py:1556`, `tool_runtime.py:1584`, `tool_runtime.py:1753`. ✓

2. **S2B Playwright migration boundary**: `plan.md:224` — "Keep Playwright's raw `multiprocessing.Process` path unless implementation proves a full migration to `InterruptibleProcessHandle` is necessary; if such migration becomes necessary, stop and update the plan/review artifact before widening S2B." This is an appropriate guardrail. ✓

3. **Chromium cleanup claim scope**: `plan.md:24` — "Real Chromium process tree cleanup is only claimed if a browser-binary-backed optional/manual smoke runs in the environment." Correctly limits claims. ✓

4. **Envelope constant grep scope**: `plan.md:267` — "prevent any local `_DOC_PROCESS_*`, `_FINS_PROCESS_*`, or `_WEB_PROCESS_*` envelope constants from reappearing after migration, not only `*_STATUS_FIELD`." Broadened from prior review. ✓

5. **`ProcessBackedToolTarget` docstring**: `plan.md:112` — "Update `ProcessBackedToolTarget.__call__` docstring so the public process target protocol documents the optional `hint` field in failed envelopes." New addition. ✓

6. **Hardcoded constant removal**: `plan.md:163` — "Remove `_PROCESS_CAPSULE_TERMINATE_GRACE_SECONDS` and `_PROCESS_CAPSULE_KILL_GRACE_SECONDS` from the active ToolRuntime code path." `plan.md:171` — "grep/assertion that ... are not present in the active ToolRuntime code path after migration." `plan.md:319` — validation assertion. ✓

## Verdict

**PASS**

All five prior findings are closed. No new material issues. The updated plan is code-generation-ready with clear directives, explicit stop conditions, and proper slice boundaries.

READY_FOR_CONTROLLER
Verdict: PASS
F01: closed (fixed)
F02: closed (fixed)
F03: closed (fixed)
F04: closed (fixed)
F05: closed (fixed)
New findings: 0
