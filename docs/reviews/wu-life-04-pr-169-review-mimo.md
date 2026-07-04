# PR Review

## Scope

- Mode: PR Review
- PR: #169 — "WU-LIFE-04: tool deadline watchdog closeout"
- Author: noho
- Head branch: phase/wu-life-04-deadline-watchdog
- Base branch: main
- URL: https://github.com/noho/dayu-agent-r/pull/169
- State: OPEN (draft)
- Output file: `docs/reviews/wu-life-04-pr-169-review-mimo.md`
- Included scope: full `git diff main...HEAD` (37 files) + workspace uncommitted `docs/host/issues-implementation-control.md`
- Excluded scope: none
- Parallel review coverage: 无

## Review Method

PR Review Mode: 从 PR title/description 开始，检查 PR body、完整 diff、Issue closing linkage、与本地 control doc 一致性。

## PR Facts

- **Title**: WU-LIFE-04: tool deadline watchdog closeout
- **Body summary**: Removes public/internal active cancel timeout budget; converts watchdog to accepted-cancel no-extra-budget semantics; renames away from timeout terminology; updates design, README, tests, and artifacts.
- **Closing linkage**: `Closes #168` / `Related to #87`
- **Commits**: 4 gateflow commits (plan accept, implementation accept, deepreview accept, draft PR prepare)
- **Validation in PR body**: 44 engine tests passed, 250 host tests passed, pyright 0 errors, `git diff --check` passed, required grep checks returned no matches.

## Findings

未发现实质性问题。

### 详细审查结果

#### 1. PR Body 准确性

- `Closes #168` ✓ — 正确关闭 Issue #168（WU-LIFE-04 scope）
- `Related to #87` ✓ — 正确标记 #87 为 umbrella owner，未错误关闭
- Summary 准确描述了变更内容
- Validation 结果与本地验证一致
- Residual risks 正确归属 WU-TOOLS-CANCEL-01 和 Issue #87

#### 2. 代码变更完整性

| 检查项 | 状态 | 证据 |
|---|---|---|
| `OpenHostOptions.active_cancel_timeout_seconds` 已移除 | ✓ | PR diff: field、docstring、validation 均删除 |
| `HostLocalExecutionOptions.active_cancel_timeout_seconds` 已移除 | ✓ | PR diff: field、docstring、validation 均删除 |
| `_DEFAULT_ACTIVE_CANCEL_TIMEOUT_SECONDS` 已移除 | ✓ | PR diff: 常量删除 |
| `_require_optional_positive_finite_float` 已移除 | ✓ | PR diff: helper 函数删除 |
| Watchdog 不再检查 timeout 条件 | ✓ | `tick_active_cancel_watchdog` 中 `timeout_seconds` 检查已移除，所有 candidate 直接进入 eligible |
| Watchdog 始终启动（无 opt-out） | ✓ | `_start_active_cancel_watchdog_loop` 和 `wake_active_cancel_watchdog` 中 `active_cancel_timeout_seconds is None` 检查已移除 |
| 所有旧 timeout 命名已重命名 | ✓ | `ActiveCancelTimeoutCloseoutInput` → `ActiveCancelWatchdogCloseoutInput`；`active_cancel_timeout_closeout_in_transaction` → `active_cancel_watchdog_closeout_in_transaction`；`_EVENT_ID_ATTEMPT_CANCELLED_TIMEOUT_PREFIX` → `_EVENT_ID_ATTEMPT_CANCELLED_WATCHDOG_PREFIX`；`_ACTIVE_CANCEL_WORKER_LIFECYCLE_SIGNAL` 值改为 `"active_cancel_watchdog_closeout"` |
| Event payload 字段已更新 | ✓ | `timeout_seconds`/`timed_out_at` → `cancel_requested_at`/`closed_out_at` |
| Design doc 已更新 | ✓ | `docs/host/design.md` 中 watchdog 描述改为 accepted-cancel closeout supervisor |
| README 已更新 | ✓ | `dayu/host/README.md` 中 `OpenHostOptions` 描述和 cancel 机制描述已更新 |
| Tests 已更新 | ✓ | 6 个测试文件已更新，使用新命名和语义 |

#### 3. Grep 验证

```
rg "active_cancel_timeout_seconds" dayu/host tests/host docs/host/design.md dayu/host/README.md
→ NO_MATCHES
```

`active_cancel_timeout_seconds` 在代码和设计文档中已完全移除。仅在 `docs/host/issues-implementation-control.md` 的历史描述文本中出现（解释变更背景），这是正确的。

#### 4. Control Doc 一致性

- PR 中的 control doc 状态：`gate = ready-to-open-draft-PR`，`WU-LIFE-04 = ready-to-open-draft-PR`
- 本地未提交变更：`gate = PR review`，`WU-LIFE-04 = review`
- 这是预期的状态转换：PR review gate 完成后，controller 会更新 control doc 到 PR review 状态
- 本地未提交变更不是 blocker，是 gateflow 工作流的正常行为

#### 5. Issue Closing Linkage

- `Closes #168` ✓ — Issue #168 是 WU-LIFE-04 的直接 scope issue
- `Related to #87` ✓ — Issue #87 是 umbrella issue，PR body 中明确说明剩余风险归属 #87
- 未错误关闭 #87 ✓

#### 6. 与 Aggregate Deepreview 后最终代码一致性

PR diff 包含所有 aggregate deepreview artifacts：
- `docs/reviews/wu-life-04-aggregate-deepreview-mimo.md`
- `docs/reviews/wu-life-04-aggregate-deepreview-ds.md`
- `docs/reviews/wu-life-04-aggregate-deepreview-controller-adjudication.md`
- `docs/reviews/wu-life-04-aggregate-fix-codex.md`
- `docs/reviews/wu-life-04-aggregate-rereview-mimo.md`
- `docs/reviews/wu-life-04-aggregate-rereview-ds.md`
- `docs/reviews/wu-life-04-aggregate-rereview-controller-adjudication.md`

所有 accepted findings（AGG-F01 stale watchdog eligible docstring）已在 PR diff 中修复。

#### 7. 未提交/未推送变更

本地有一个未提交变更：`docs/host/issues-implementation-control.md` 的 gate 状态从 `ready-to-open-draft-PR` 更新为 `PR review`。这是 PR review gate 完成后的预期状态转换，不是必要的 PR 内容变更。不构成 blocker。

## Open Questions

无。

## Residual Risk

以下风险已正确归属，不构成本 PR blocker：

1. **Tool/provider 物理中断**: 归属 WU-TOOLS-CANCEL-01
2. **Watchdog scan query 优化**: 归属 Issue #87 follow-up
3. **Clock skew 诊断**: 归属 Issue #87 follow-up
4. **Diagnostics/audit hooks**: 归属 Issue #87 follow-up
5. **Shared supervisor 抽象**: 归属 Issue #87 follow-up
6. **Watchdog loop fatal exit 可运维性**: 归属 Issue #87 follow-up
7. **Per-tool deadline observability**: 归属 Issue #87 follow-up

## Review Conclusion

**Pass.** PR #169 review 通过。

- **Findings**: 0（未发现实质性问题）
- **Blocking open questions**: 无
- **PR body**: 准确，`Closes #168` 正确，未错误关闭 #87
- **Code changes**: 完整，包含所有 accepted artifacts
- **Tests**: 通过（44 engine + 250 host，pyright 0 errors）
- **Grep verification**: `active_cancel_timeout_seconds` 已从代码和设计文档中完全移除
- **Control doc**: 本地有预期的 gate 状态更新（不 blocker）
- **Residual risks**: 正确归属 WU-TOOLS-CANCEL-01 和 Issue #87

PR 可以从 draft 状态转为 ready for merge。
