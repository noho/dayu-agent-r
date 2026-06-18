# PR Re-Review — WU-CLI-ACTIVITY-01 (PR #149)

## Scope

- Mode: PR re-review
- PR: [#149](https://github.com/noho/dayu-agent-r/pull/149)
- Fix commit: `4cacda95`
- Fix artifact: `docs/reviews/wu-cli-activity-01-pr-review-fix-codex-20260618.md`
- Prior review: `docs/reviews/wu-cli-activity-01-pr-review-mimo-20260618.md`
- Output file: `docs/reviews/wu-cli-activity-01-pr-rereview-mimo-20260618.md`

## Verification Results

### 1. `_cancel_and_await_task` 重复抽取 → ✅ PASS

- 旧定义已从 `prompt.py:566` 和 `interactive.py:646` 完全移除
- 新公共函数 `cancel_and_await_task` 定义于 `dayu/cli/agent_entrypoint.py:116-130`，含完整中文 docstring
- 已添加到 `agent_entrypoint.py` 的 `__all__` 导出
- `prompt.py` 和 `interactive.py` 均改为 `from dayu.cli.agent_entrypoint import cancel_and_await_task`
- `_TaskResult` TypeVar 移至 `agent_entrypoint.py:28`，从两处 command 模块移除
- `grep -rn "_cancel_and_await_task" dayu/cli/` 无残留私有定义

### 2. README 记录 `--detail`/`--no-detail` → ✅ PASS

- `README.md` 全局参数表新增 `--detail` / `--no-detail` 行（prompt 命令）
- `prompt` 命令专属参数表新增 `--detail` / `--no-detail` 行
- 命令示例新增 `dayu-cli prompt "..." --detail`
- 命令说明新增"默认不显示运行态 activity stream"说明
- 4 处新增，覆盖全局参数、命令参数、示例、说明

### 3. PR body scope 更新 → ✅ PASS

PR body 已更新，包含全部变更范围：
- ✅ Activity stream (Host → Service → CLI)
- ✅ CLI output-channel cleanup (`--log-file`, `--detail`/`--no-detail`)
- ✅ Fins direct download progress
- ✅ Existing-session startup semantics (prompt one-shot / interactive backfill/reconnect)
- ✅ Follow-up EventLog/projection hardening (delta 不持久化, filter-aware read, 无 budget)
- ✅ RunInputBuilder inline repair 对齐
- ✅ Known non-blocking residual (main 上 pre-existing smoke failures)

### 4. Pre-existing smoke failures 归档 → ✅ PASS

`docs/host/issues-implementation-control.md` 新增：
- Residual risk 表新增 `WU-CLI-ACTIVITY-01-PR-R1`，状态 `deferred-with-owner`，owner 为 "Future Host public multiturn / memory smoke stabilization WU"
- 描述明确说明两个 smoke test 在 `main` 分支同样失败，不属于 WU-CLI-ACTIVITY-01 引入
- 下一步 entry point 更新为 "focused PR re-review, then update PR body and close out draft PR gate"

### 5. Tests / Pyright → ✅ PASS

| 检查项 | 结果 |
|---|---|
| Host tests (13 files) | 348 passed ✅ |
| Service/CLI tests (8 files) | 114 passed, 3 warnings (edgar deprecation) ✅ |
| Pyright | 0 errors, 0 warnings ✅ |

## Residual Risk

无。Fix artifact 声明的 "PR body scope update is pending until after push" 已在本次 re-review 时通过 `gh pr view` 确认 PR body 已实际更新。

## Conclusion

**PASS。** PR review 的 3 项 finding 全部正确修复：

1. ✅ `_cancel_and_await_task` 抽取到 `dayu.cli.agent_entrypoint`，无残留重复
2. ✅ `README.md` 完整记录 `--detail`/`--no-detail`（全局参数、命令参数、示例、说明）
3. ✅ PR body scope 已包含全部变更范围（activity stream、fins progress、CLI 参数、interactive resume、follow-up hardening）

DS 发现的 main 上 pre-existing smoke failures 已在 control doc 归档为 `WU-CLI-ACTIVITY-01-PR-R1`。Tests 462 passed, pyright 0 errors。

无阻断 finding。PR 可以 merge。
