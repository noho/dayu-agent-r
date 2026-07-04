# WU-LIFE-04 Plan Review — AgentMiMo

Review target: `docs/host/wu-life-04-tool-execution-deadline-watchdog-plan.md`
Review date: 2026-07-04
Reviewer: AgentMiMo
Stance: adversarial

---

## Verdict: PASS WITH FINDINGS

Blocking findings: 0
Non-blocking findings: 3

The plan is code-generation-ready with minor recommended improvements.

---

## Finding 01 — Non-blocking: `HostLocalExecutionOptions` deletion vs replacement ambiguity

**Severity**: low
**Section**: §6 Public Contract / Schema / State-Machine Changes, §8 Slice 1
**Evidence**: `dayu/host/api.py:792` defines `HostLocalExecutionOptions.active_cancel_timeout_seconds: float | None = None`, used in `dayu/host/dispatch.py:1063,1083,2554` to gate watchdog behavior.

**Issue**: The plan says in §6 "Prefer deleting `HostLocalExecutionOptions.active_cancel_timeout_seconds` too. If a direct implementation blocker appears, it may be replaced by an internal non-public scheduler behavior flag." This leaves ambiguity for the implementation agent: what constitutes a "direct implementation blocker"? The code evidence shows dispatch.py uses `active_cancel_timeout_seconds is None` in three locations as a gating mechanism for the watchdog loop and tick. The plan should be more decisive.

**Recommendation**: Since the plan already commits to "no post-cancel time budget" and the watchdog will always run (not gated by timeout presence), the cleanest approach is to delete the field from `HostLocalExecutionOptions` and remove all `is None` guards in dispatch.py. The watchdog always starts, always ticks, and eligibility is no longer time-based. If the implementation agent finds a reason to keep a boolean "watchdog enabled" flag, it should be a new `bool` field with a clear name, not a leftover `float | None` repurposed as a toggle.

**Verdict candidate**: `accepted` — clarify in Slice 1 stop condition that `HostLocalExecutionOptions.active_cancel_timeout_seconds` must be deleted (not just made private), and any replacement must be a named boolean if needed.

---

## Finding 02 — Non-blocking: terminal reason rename scope underspecified

**Severity**: low
**Section**: §6 Public Contract / Schema / State-Machine Changes
**Evidence**: `dayu/host/durable/run_transition.py:875` defines `ActiveCancelTimeoutCloseoutInput` with `timeout_seconds` and `timed_out_at` fields. The plan says "Terminal reason should be reviewed. Preferred new reason is `active_cancel_watchdog_closeout`" but doesn't enumerate all locations where `active_cancel_timeout` as a reason string appears.

**Issue**: The plan correctly identifies the semantic rename, but the implementation agent needs to know the exact grep scope. The reason string `active_cancel_timeout` may appear in:
- `dispatch.py` closeout call site
- `run_transition.py` payload construction
- Test assertions in `test_active_cancel_dispatch.py`, `test_run_attempt_transitions.py`
- `test_engine_ingest_mapping.py` (grep confirmed it imports `ActiveCancelTimeoutCloseoutInput`)

**Recommendation**: Add to Slice 2 stop condition: `rg "active_cancel_timeout" dayu/host tests/host` returns no live reason string usage after implementation. The rename from `active_cancel_timeout` to `active_cancel_watchdog_closeout` (or equivalent) must cover the reason string in `RUN_CANCELLED` payload, the `ActiveCancelTimeoutCloseoutInput` class name (rename to `ActiveCancelWatchdogCloseoutInput`), and all test assertions.

**Verdict candidate**: `accepted` — add explicit grep stop condition for the reason string.

---

## Finding 03 — Non-blocking: `test_engine_ingest_mapping.py` not listed in allowed files

**Severity**: low
**Section**: §5 Affected Files / Modules
**Evidence**: `tests/host/test_engine_ingest_mapping.py:123` imports `ActiveCancelTimeoutCloseoutInput` and at line 2682 constructs one in a test fixture.

**Issue**: The plan's §5 lists allowed implementation files but does not include `tests/host/test_engine_ingest_mapping.py`. This file imports `ActiveCancelTimeoutCloseoutInput` which will be renamed. The implementation agent will hit a pyright/import error if this file is not updated.

**Recommendation**: Add `tests/host/test_engine_ingest_mapping.py` to §5 allowed files list (for import rename only, not new test coverage).

**Verdict candidate**: `accepted` — add to allowed files.

---

## Verification of Key Plan Claims

### Claim 1: Motivation is code-evidence-based and correctly scoped

**VERIFIED**. The plan correctly identifies:
- `dayu/host/api.py:57,1080` — `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS = 300.0` and `OpenHostOptions.active_cancel_timeout_seconds` default
- `dayu/host/dispatch.py:1102` — eligibility check `(now - candidate.cancel_requested_at).total_seconds() < timeout_seconds` confirms independent post-cancel budget
- `dayu/host/open_host.py:899` — startup recovery deferral depends on `active_cancel_timeout_seconds is not None`
- `dayu/host/durable/run_transition.py:875-906` — `ActiveCancelTimeoutCloseoutInput` carries `timeout_seconds` and `timed_out_at`

The plan correctly scopes out WU-TOOLS-CANCEL-01 physical interrupt: "实际中断工具线程、HTTP 请求、provider stream、子进程、process group、sandbox 或外部长事务仍归 WU-TOOLS-CANCEL-01."

### Claim 2: Host cannot know per-tool original deadline

**VERIFIED**. `dayu/host/dispatch.py` active-cancel candidate only has `run_id`, `session_id`, `attempt_id`, `cancel_requested_at`. Engine design §11 confirms `BatchToolExecutionContext.timeout_seconds` is runtime-local and not durable. No Host-visible per-tool start/deadline fact exists.

### Claim 3: No-extra-budget is the minimal correct approach

**VERIFIED**. Alternatives analyzed in §7 are correctly rejected:
- `cancel_requested_at + tool_execution_timeout_seconds` resets budget and can extend
- Attempt start time can close non-tool phases too early
- No post-cancel budget is the only option that cannot extend original deadline

### Claim 4: State machine impact is correctly bounded

**VERIFIED**. The plan correctly states:
- `RUNNING + active cancel -> CANCELLING` unchanged
- Terminal first-committer-wins unchanged
- Startup recovery will always defer `CANCELLING` with accepted cancel to watchdog (removing the `is not None` gate)
- Watchdog closeout still writes `ATTEMPT_CANCELLED` + `RUN_CANCELLED` and triggers queued promotion

### Claim 5: 2 slices is appropriate for this cleanup

**VERIFIED**. Per control doc Slice 切分原则: "小型同一语义 cleanup：1-3 个 implementation slices." This is a contract cleanup + behavior change across ~10 files with tight semantic coupling. 2 slices (design/contract + watchdog behavior) follows the "contract / config / composition slice" and "provider / behavior slice" pattern. Not mechanically split.

### Claim 6: README trigger coverage

**VERIFIED**. Plan correctly identifies:
- `docs/host/design.md` — required (cancel design semantics change)
- `dayu/host/README.md` — required (public contract change, confirmed grep shows line 568 references `active_cancel_timeout_seconds`)
- `tests/README.md` — check only
- Engine/Config README — not expected to change

### Claim 7: Residual risk owners are complete

**VERIFIED**. Plan §11 covers:
- Per-tool deadline observability → WU-TOOLS-CANCEL-01 or #87 child
- Physical interruption → WU-TOOLS-CANCEL-01
- Scan query optimization → #87 performance follow-up
- Clock skew → #87 diagnostics/audit follow-up
- Shared supervisor → #87 umbrella
- Diagnostic/audit hooks → #87 diagnostics/audit hooks follow-up

---

## Summary

The plan is **code-generation-ready**. All three findings are non-blocking improvements to stop condition precision and allowed file completeness. The core design decision (delete `active_cancel_timeout_seconds`, no-extra-budget closeout) is sound, correctly evidenced, and correctly scoped against WU-TOOLS-CANCEL-01.

**Findings count**: 3 (0 blocking, 3 non-blocking)
**Artifact path**: `docs/reviews/wu-life-04-plan-review-mimo.md`
