# PR Review — WU-LIFE-03 PR #167 (AgentMiMo)

## Scope

- Mode: PR Review
- PR: #167 — "WU-LIFE-03: active cancel watchdog timeout closeout"
- Author: noho
- Head branch: `phase/host-engine-next`
- Base branch: `main`
- URL: https://github.com/noho/dayu-agent-r/pull/167
- State: OPEN, draft
- Output file: `docs/reviews/wu-life-03-pr-167-review-mimo.md`
- Review date: 2026-07-04

## PR Facts

- Diff stat: 43 files changed, +5541 / -43 lines
- Production code: 8 files (`api.py`, `command.py`, `dispatch.py`, `run_transition.py`, `engine_ingest.py`, `open_host.py`, `recovery.py`, `README.md`)
- Test code: 6 files (+1395 lines)
- Plan/doc artifacts: 1 plan doc, 1 design.md update, 1 control doc update, 27 review artifacts
- CI checks: `gh pr checks 167` reported "no checks reported on the branch" (consistent with prior WU PRs)

## PR Body Validation

### Issue Linkage

- PR body `Closes #91` — **correct**. Issue #91 is OPEN, scope is "Active Attempt cancel watchdog target" under #87 umbrella. PR implements the full #91 acceptance criteria.
- Residual owner `#87` — **correct**. #87 is the Host Lifecycle Watchdog / Supervisor umbrella. Watchdog scan optimization, timeout default tuning, and cross-instance clock skew are legitimate #87 follow-ups.
- Residual owner `WU-TOOLS-CANCEL-01` — **correct**. Provider/tool physical interrupt is explicitly out of scope per #91 non-goals and control doc.

### Validation Commands

PR body declares:

```
pytest tests/host/test_active_cancel_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_public_cancel_smoke.py tests/host/test_dispatch_scheduler.py tests/host/test_open_host_runtime.py tests/host/test_recovery_scan.py -q
pytest tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py -q
pyright
git diff --check
```

Controller verification:

- First test set: **142 passed** ✅
- Second test set: **123 passed** ✅
- pyright: **0 errors, 0 warnings, 0 informations** ✅
- `git diff --check`: **no output** ✅

### Control Doc Status

- `docs/host/issues-implementation-control.md` — WU-LIFE-03 status updated to `draft-PR-pass`, gate updated to `draft-PR-pass`, active work unit updated to `WU-LIFE-03`, next entry point updated to `WU-LIFE-03 / draft PR #167 review gate`. WU-WAIT-02 and WU-WAIT-03 marked `completed` with merge dates. **Consistent.**
- `docs/host/design.md` — Cancel section updated with watchdog timeout semantics, recovery section updated with `DEFERRED_TO_ACTIVE_CANCEL_WATCHDOG` decision. **Consistent with implementation.**

## Scope Boundary

PR diff against `main` contains only WU-LIFE-03 scope changes:

- Active cancel watchdog timeout closeout: `run_transition.py` (new `ActiveCancelTimeoutCloseoutInput` + `active_cancel_timeout_closeout_in_transaction`), `dispatch.py` (watchdog tick, loop, candidate scan, wakeup)
- Late terminal rejection: `engine_ingest.py` (`_late_rejection_reason` new CANCELLING branch)
- Recovery defer: `recovery.py` (`defer_accepted_cancel_to_watchdog`, `_has_accepted_cancel_fact`)
- Configuration: `api.py` (`active_cancel_timeout_seconds` on `OpenHostOptions` / `HostLocalExecutionOptions`)
- Wiring: `open_host.py` (startup tick, recovery defer flag, command handle wakeup port), `command.py` (`ActiveCancelWatchdogWakeupPort`, wakeup propagation)
- Consolidation: `_cancel_request_event_id_from_cancelling` moved from `engine_ingest.py` to `run_transition.py` (duplicate removed)
- Plan, design, control docs, README, review artifacts

**No unrelated work detected.** All changes serve the WU-LIFE-03 scope.

## Findings

未发现实质性问题。

以下为低风险观察项，均已在 prior slice review / aggregate deepreview 中被 controller 裁决：

### OBS-01: `_cancel_request_event_id_from_cancelling` 跨模块私有 import

- `engine_ingest.py` 通过 `from dayu.host.durable.run_transition import _cancel_request_event_id_from_cancelling` 导入私有符号。
- Controller 裁决: "Keep the helper internal to Host implementation and avoid adding a public export"，`_` 前缀阻止意外公开导出，符合裁决意图。非缺陷。

### OBS-02: `read_non_terminal_runs` 全表扫描

- Watchdog 每次 tick 调用 `read_non_terminal_runs(transaction)` 后 Python 过滤 `CANCELLING`。
- 非终态 Run 数量受 lane capacity 约束通常很小。已归属 #87 性能调优。非缺陷。

### OBS-03: `payload_json=None` theoretical boundary

- `_cancel_request_event_id_from_cancelling` 对 `EventLogRow` 的 `payload_json` 做 `json.loads`。若 `payload_json=None`（理论上 `append_event` 不允许），会抛 `TypeError`。
- Aggregate deepreview 裁决: accepted risk，`append_event` 强制 `payload_json` 非 `None`。非缺陷。

## Open Questions

无。

## Residual Risk

- Watchdog scan SQL optimization: owner #87
- Timeout default value production tuning: owner #87
- Cross-instance clock skew: owner #87
- Provider/tool physical interrupt: owner WU-TOOLS-CANCEL-01
- UI/Service E2E cancel recovery: owner WU-WAIT-04

## Conclusion

**PASS**

PR #167 完整承载 WU-LIFE-03 / #91 scope。PR body 的 `Closes #91`、residual owner #87 / WU-TOOLS-CANCEL-01 均准确。与 main 相比只有 WU-LIFE-03 范围内变更。control doc、design doc、README 均已同步。测试声明与实际一致（142 + 123 passed, pyright 0 errors, git diff --check clean）。无 PR 级别 blocker，无 correctness/blocking regression。
