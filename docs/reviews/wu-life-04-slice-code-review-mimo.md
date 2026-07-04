# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-life-04-deadline-watchdog`
- Base: `59be8480` (accepted plan commit)
- Output file: `docs/reviews/wu-life-04-slice-code-review-mimo.md`
- Included scope: Slice 1 (design + public contract cleanup) + Slice 2 (watchdog no-extra-budget closeout) combined diff from `59be8480` to current workspace state.
- Excluded scope: Engine code, runtime assembly, execution profiles, config schema — unchanged per plan.
- Parallel review coverage: 无。

## Findings

未发现实质性问题。

以下为已审查的非 blocking 观察项，均不构成 correctness / stability / stability defect：

### 1-OBS-低-watchdog loop fatal exit 静默丢失

- **入口/函数**: `HostDispatchScheduler._active_cancel_watchdog_loop` (`dayu/host/dispatch.py:2549`)
- **文件(行号)**: `dayu/host/dispatch.py:2600-2607`
- **输入场景**: watchdog tick 抛出非 `CancelledError`、非预期异常（例如 durable store 不可恢复错误）。
- **实际分支**: 外层 `except Exception` 捕获后仅 `_LOGGER.error`，loop 静默退出。
- **预期行为**: 作为 always-enabled watchdog，fatal exit 应有更显式的故障信号（例如 metric、callback 或 re-raise）。
- **实际行为**: watchdog 静默退出，后续 cancel commit wakeup 不再被消费，仅靠 periodic fallback 无法恢复（因为 loop 已死）。
- **直接证据**: `dayu/host/dispatch.py:2600-2607`。
- **影响**: 极低概率场景。watchdog 静默退出后，accepted-cancel CANCELLING Run 只能依赖下一次 startup recovery 收口。不影响 correctness（startup recovery 仍能处理），但增加延迟。
- **建议改法和验证点**: 可在后续 Issue #87 follow-up 中考虑 watchdog 自重启或 fatal callback。当前实现已是 pre-existing 行为，本次改动未引入新风险。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **候选裁决**: deferred-with-owner (Issue #87 umbrella)

## Open Questions

无。

## Residual Risk

1. **Per-tool original deadline 不 Host-visible**: Host 无法精确知道当前运行工具调用的原始 deadline。当前方案通过不提供 post-cancel budget 来保证不延长 deadline，但无法做精确 per-tool deadline diagnostics。Owner: WU-TOOLS-CANCEL-01 / Issue #87。

2. **Physical interruption 未实现**: Host closeout 只表达 durable cancel 收口，不证明 provider/tool 物理停止。Owner: WU-TOOLS-CANCEL-01。

3. **Watchdog scan query 未优化**: 当前 `_read_active_cancel_watchdog_candidates` 仍全表扫描 `read_non_terminal_runs`。Owner: Issue #87 performance follow-up。

4. **Watchdog loop fatal exit 无自动恢复**: 如上观察项所述。Owner: Issue #87 umbrella。

## Verification Summary

| 验证项 | 结果 |
|---|---|
| `active_cancel_timeout_seconds` 从 `OpenHostOptions` 删除 | ✅ `rg` 无匹配 |
| `active_cancel_timeout_seconds` 从 `HostLocalExecutionOptions` 删除 | ✅ `rg` 无匹配 |
| 无 internal disable flag 或 timeout opt-out | ✅ `_start_active_cancel_watchdog_loop` 和 `wake_active_cancel_watchdog` 无条件门控 |
| watchdog 不再按 `cancel_requested_at + timeout_seconds` 延迟 | ✅ `tick_active_cancel_watchdog` 无 elapsed time 比较 |
| closeout helper/reason/signal/payload 使用 watchdog 语义 | ✅ `_ACTIVE_CANCEL_WATCHDOG_CLOSEOUT_REASON`、`active_cancel_watchdog_closeout`、payload 无 `timeout_seconds`/`timed_out_at` |
| candidate preconditions 严格 | ✅ CANCELLING Run + RUNNING Attempt + worker-accepted dispatch + linked CANCEL_REQUESTED |
| startup recovery 与 always-enabled watchdog 一致 | ✅ `defer_accepted_cancel_to_watchdog=True` 硬编码 |
| orphan CANCELLING without accepted cancel 不被错误 closeout | ✅ `_read_linked_cancel_requested_event` 返回 None 时 candidate 被跳过 |
| late terminal first-committer-wins | ✅ replay 和 precondition 检查保留 |
| queued promotion after closeout | ✅ 测试覆盖 |
| Engine `tool_execution_timeout_seconds` contract 不变 | ✅ 无 engine 代码/config 变更 |
| target tests pass | ✅ engine 44 passed, host 250 passed |
| pyright | ✅ 0 errors |
| `git diff --check` | ✅ passed |
| `rg "active_cancel_timeout_seconds"` 在 scope 内 | ✅ no matches |
| `rg "active_cancel_timeout\|timeout_seconds.*active"` 在 scope 内 | ✅ no matches |
| design.md 更新 | ✅ Cancel 和 startup recovery 章节重写 |
| README 更新 | ✅ cancel 和 startup recovery 段落同步 |
