# P9.5 Plan Re-Review — AgentDS

## Gate

- **Work unit**: P9.5 Pre-P10 Cross-Repository Hardening PR plan re-review.
- **Review role**: AgentDS, review-only.
- **Re-reviewed artifact**: `docs/host/p9-5-pre-p10-hardening-plan.md` (post-fix).
- **Controller adjudication**: `docs/reviews/p9-5-plan-review-controller-adjudication-20260517.md`.
- **Original DS review**: `docs/reviews/p9-5-plan-review-ds-20260517.md`.
- **MiMo review**: `docs/reviews/p9-5-plan-review-mimo-20260517.md`.
- **Date**: 2026-05-17.

## Verdict

**PASS.** 所有 controller adjudication 中 accepted 的 findings（2 个 required fix + 10 个 non-blocking guidance）均已修复。Plan fix 未引入新的 blocker。

---

## Finding Verification

### Required Fixes (controller-adjudicated as blocking for plan acceptance)

#### DS F1: S14 `current_goal` first-write-wins — FIXED

Controller 要求：Define current code owner/path, write path, enforcement strategy, and targeted validation expectation.

| Requirement | Plan evidence | Status |
|---|---|---|
| Code owner | Line 324: `PinnedStateView.current_goal: str \| None` in `dayu/host/memory.py` | OK |
| Write path | Lines 325-326: memory projection via `build_conversation_memory_snapshot_from_events(...)` → `_pinned_state_with_user_input(...)` | OK |
| Enforcement strategy | Line 331: set `current_goal` only when previous `current_goal is None`, transaction-free pure projection; "Do not add DB uniqueness, CAS, state-machine transition, or schema history retention" | OK |
| Tests | Lines 330-331: multi-`USER_INPUT_ACCEPTED` snapshot test (first remains current_goal); inline delta repair preserves existing goal test | OK |
| Stop condition | Line 331: fix stays in `dayu/host/memory.py`, not moved to RunInputBuilder/durable/Context Governance/Service | OK |

#### DS F2: S14 `SessionContinuityProvider` parameters — FIXED

Controller 要求：Identify module/path, legacy parameter behavior, bypass mechanism, and remove-vs-tighten decision rule.

| Requirement | Plan evidence | Status |
|---|---|---|
| Module/path | Line 327: protocol `SessionContinuityProvider` in `dayu/host/run_input.py`; production impl `DurableSessionContinuityProvider` | OK |
| Bypass mechanism | Line 328: RunInputBuilder composition appends `*continuity.messages` after memory, bypassing `MemoryProjectionPolicy.history_pool_size_units` | OK |
| Decision rule | Line 332: remove is preferred; tighten only with direct non-history evidence (e.g., resume wait fact reconstruction) | OK |
| Tightening bounds | Line 333: tightened provider emits only bounded, non-history, current-run resume/system facts; no history count/raw turn/before-event/budget bypass parameters | OK |
| Legacy cleanup | Line 334: remove unused `read_run_input_continuity_events(...)` after confirming imports; no compatibility wrappers | OK |
| Stop condition | Line 347: stop if `SessionContinuityProvider` historical raw-turn path appears necessary; reassign to memory/P10 design | OK |

### Non-Blocking Guidance (all FIXED)

| Source | Finding | Plan evidence | Status |
|---|---|---|---|
| DS F3 | S10/S14 shared test file | Rule 7 (line 89): accumulated assertion rule; S10 line 264: keep fixtures stable; S14 line 338: preserve S10 assertions, report fixture refactors | OK |
| DS F4 | S15 log audit step | S15 line 354: "Audit existing Engine/Host log calls before adding new ones" with classification taxonomy | OK |
| DS F5 | S11 test-only private re-export | S11 line 278: prefer behavior tests; line 279: no test-only compat re-export; line 287: stop condition includes "test-only private re-export" | OK |
| MiMo F-01 | Slice dependencies | Rule 6 (line 88): full sequential order S0-S18; parallelization constraints; explicit S14→S10 and S16→S1/S3/S11/S14 dependency notes | OK |
| MiMo F-02 | S15 logger pattern | S15 line 355: follow existing module-level `logging.getLogger(__name__)`; no constructor-injected loggers | OK |
| MiMo F-03 | Duplicate of DS F1 | Covered by DS F1 fix | OK |
| MiMo F-04 | S6 test layering | S6 line 202: S5 owns DB CHECK; S6 owns Python mapping fail-closed; construct dataclass directly for mapping tests | OK |
| MiMo F-05 | Slice commit strategy | Rule 8 (line 90): high-risk slices separate commits; low-risk combine only by controller decision | OK |
| MiMo F-06 | S2 evidence standard | S2 line 134: direct evidence = failing test, code path contradiction, provider protocol fake/fixture, or official docs; theory-only out of scope | OK |
| MiMo F-07 | Pyright baseline | S0 lines 101-103: pre-S1 pyright run recorded as baseline; pre-existing errors classified; later slices must not introduce/expand/leave errors | OK |
| MiMo F-08 | S11 extraction granularity | S11 line 276: "Extract only if it removes real coupling or is needed to make S12/S16 changes localized. The listed owners are candidate groupings, not required new modules" | OK |

---

## New Blocker Check

逐项检查 plan fix 是否引入了新的架构、契约、状态机或 scope 问题：

### S14 `dayu/host/durable/event_log.py` 新增 allowed file

Plan fix 在 S14 allowed files (line 322) 中新增了 `dayu/host/durable/event_log.py`，标注 "only for unused legacy continuity reader cleanup"。该文件未出现在原始 plan 的全局 Affected Files 中。

- **判定**：这是 S14 澄清后的合理 scope 扩展。若 `read_run_input_continuity_events(...)` 位于 `event_log.py` 且需移除，S14 必须有权编辑该文件。约束 "only for unused legacy continuity reader cleanup" 与 S14 stop condition (line 347) 共同限制了 scope 不会扩大。
- **风险**：低。实施 agent 可能误删仍被其他 owner 使用的函数。但 S14 line 334 明确 "remove them or keep them only if another non-S14 owner directly uses them" 作为保护。
- **结论**：非 blocker。

### S14 函数名引用的准确性

Plan line 325 引用了 `build_conversation_memory_snapshot_from_events(...)` 和 `_pinned_state_with_user_input(...)` 作为 "Current direct repository evidence"。这些是代码级函数名。

- **判定**：Controller adjudication (line 61) 的 stop condition 明确 "The fix cannot identify current S14 code ownership from direct repository evidence" 才会停止。plan fix agent 已完成此发现并写入 plan。若实际代码中函数名与 plan 描述有偏差，属于实施 agent 在 S14 开始时需验证的 normal discovery，不是 plan defect。
- **结论**：非 blocker。

### 跨 finding 一致性

- DS F3 / S10+S14 shared test file：Rule 7 (全局)、S10 line 264、S14 line 338 三处一致。
- MiMo F-07 / pyright baseline：S0 记录 baseline，各 slice 的 "python -m pyright" targeted commands 均要求通过——与 baseline 规则一致。
- MiMo F-08 / S11 extraction 粒度：line 276 "not required new modules" 与 line 287 stop condition "test-only private re-export" 一致。

### 无新引入的 P10+ 语义

Plan fix 中 S14 所有变更保持在 P9 范围内：
- `current_goal` enforcement 明确 "Do not add DB uniqueness, CAS, state-machine transition, or schema history retention" (line 331)
- `SessionContinuityProvider` 明确不能保留 historical raw-turn path (line 347 stop condition)
- 无 Context Governance、compaction、recovery、remote、audit/trace/outbox 引入

---

## Residual Risk

以下 risk 在 plan fix 后仍存在，但已适当处置：

1. **S14 代码引用偏差**：plan 中引用的函数名（`build_conversation_memory_snapshot_from_events` 等）若与当前代码不完全一致，实施 agent 需在 S14 开始时自行对齐。风险低——plan 明确标注为 "Current direct repository evidence" 且每个函数附带了模块路径和语义描述。

2. **S14 `event_log.py` 编辑范围**：若 `read_run_input_continuity_events(...)` 的移除触及 EventLog 的其他 consumer，实施 agent 需按 stop condition 停止。Plan 的 "only if another non-S14 owner directly uses them" 保护充分。

3. **MiMo F-07 pyright baseline**：若 S0 记录的 baseline 错误数很大，后续 slice agent 可能因 "touched-file errors must be fixed" 而 scope creep。S0 的 "classify them as pre-existing" 和 "later slices must not introduce new errors, expand existing errors, or leave touched-file errors unfixed" 提供了清晰的边界。

---

## Conclusion

- **Accepted findings fixed**: 13/13（2 required + 11 non-blocking，含 MiMo F-03 与 DS F1 合并）。
- **New blockers**: 0。
- **Plan status**: `docs/host/p9-5-pre-p10-hardening-plan.md` 已满足 controller adjudication 的全部修复要求，可进入 accepted plan commit gate。
