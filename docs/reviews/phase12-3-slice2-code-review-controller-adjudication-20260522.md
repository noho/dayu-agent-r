# Phase 12.3 Slice 2 Code Review Controller Adjudication

- Gate: Phase 12.3 Slice 2 code review adjudication
- Controller: AgentController
- Implementation artifact: `docs/reviews/phase12-3-slice2-implementation-codex-20260522.md`
- Review artifacts:
  - `docs/reviews/phase12-3-slice2-code-review-mimo-20260522.md`
  - `docs/reviews/phase12-3-slice2-code-review-ds-20260522.md`

## Verdict

FIX REQUIRED.

两份独立 code review 均为 PASS，blocking finding count = 0；但 DS 提出的 3 个 advisory findings 均处在当前未提交 Slice 2 变更内，修复成本低，且能强化 Host usage observation 诊断边界。总控裁决为进入窄 fix pass 后再 re-review。

## Accepted Findings

### P12.3-S2-F1: Narrow usage observation estimate exception handling

Accepted as current narrow fix.

`_estimate_usage_observation_input` 当前使用 `except Exception` 降级为 `estimate_unavailable`。虽然该路径是 diagnostic-only 且 MiMo 认为非 blocker，但项目编码约束不鼓励吞掉真实编程错误。应收窄为当前调用链实际预期的异常类型，例如 `HostDurableError`、`TypeError`、`ValueError`。

### P12.3-S2-F2: Include iteration_id in usage observation digest

Accepted as current narrow fix.

`USAGE_REPORTED` payload 已包含 `iteration_id`，但 `UsageObservation` 与 digest payload 未纳入该字段。把 `iteration_id` 纳入 observation/digest 能让 diagnostic ref 更贴近单次 Engine usage event，消除同 attempt 多 iteration 下的理论碰撞窗口。该 helper 尚未 accepted，当前修复不会形成兼容负担。

### P12.3-S2-F3: Correct input event display text docstring

Accepted as current narrow fix.

`_display_text_from_input_event` 实际经由 EventLog payload helpers 抛出 `HostDurableError`，docstring 仍写 `ValueError`。该错误会误导 F1 的异常边界，应一并修正。

## Rejected Or Deferred Findings

None.

## Required Fix Scope

- Do not modify Engine production contracts or Engine agent loop.
- Do not add usage config override or provider request id source.
- Keep `USAGE_REPORTED` as `EventClass.PROJECTION_SIGNAL`.
- Add/adjust focused tests for `iteration_id` in observation digest if existing tests do not cover it.
- Update implementation artifact with a fix addendum and rerun Slice 2 validation commands.

## Next Gate

Route P12.3-S2-F1 / F2 / F3 to AgentCodex for a narrow fix, then run code re-review with AgentMiMo and AgentDS.
