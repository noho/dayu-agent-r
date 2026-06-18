# PR Re-Review — WU-CLI-ACTIVITY-01 (Fix Verification)

## Scope

- Mode: focused PR re-review
- PR: https://github.com/noho/dayu-agent-r/pull/149
- Fix commit: 4cacda95 (address PR review for WU-CLI-ACTIVITY-01)
- Fix artifact: `docs/reviews/wu-cli-activity-01-pr-review-fix-codex-20260618.md`
- Prior PR reviews:
  - `docs/reviews/wu-cli-activity-01-pr-review-ds-20260618.md`
  - `docs/reviews/wu-cli-activity-01-pr-review-mimo-20260618.md`
- Output file: `docs/reviews/wu-cli-activity-01-pr-rereview-ds-20260618.md`
- Included scope: `dayu/cli/agent_entrypoint.py`, `dayu/cli/commands/interactive.py`, `dayu/cli/commands/prompt.py`, `README.md`, `docs/host/issues-implementation-control.md`
- Excluded scope: all other files unchanged by this fix commit

## Conclusion

**PASS** — 无阻断 finding。五个 review 关注点全部确认修复。

## Verification Matrix

| # | 关注点 | 结果 | 直接证据 |
|---|--------|------|----------|
| 1 | `_cancel_and_await_task` 重复已消除 | ✅ PASS | `agent_entrypoint.py` 新增 public `cancel_and_await_task`，`prompt.py` 和 `interactive.py` 同时删除本地定义与 `_TaskResult` TypeVar，5 处调用点全部替换为 import；`grep -rn "def _cancel_and_await_task\|_cancel_and_await_task" dayu/cli/` 零命中 |
| 2 | README 已记录 `--detail`/`--no-detail` | ✅ PASS | 根 `README.md` 全局参数表（行 299）新增 `--detail / --no-detail` 行；prompt 命令参数表（行 540）新增加项、命令示例（行 560）、说明句（行 569） |
| 3 | PR body scope 已完整 | ✅ PASS | 更新后 PR body 包含 6 段 Summary：activity stream、output-channel cleanup（`--log-file`/`--detail`）、Fins download progress、interactive resume startup、follow-up hardening、inline repair；Known Non-Blocking Residual 节列出两处 pre-existing smoke failures 及 control doc 跟踪号 |
| 4 | DS pre-existing failures 已归档 | ✅ PASS | `docs/host/issues-implementation-control.md` 在 Residual Risk Registry 新增 `WU-CLI-ACTIVITY-01-PR-R1` 条目（行 207），将两处 `main` 上同样失败的 smoke 测试标记为 `deferred-with-owner` 并链接到 Future Host public multiturn / memory smoke stabilization WU |
| 5 | tests / pyright 可接受 | ✅ PASS | 206 passed（`test_prompt_command` + `test_interactive_command` + `test_activity_renderer` + `test_interactive_composer` + `test_run_keys` + entrypoint runtime 三文件 + Host 四文件）；pyright `dayu/ tests/ utils/` 0 errors, 0 warnings |

## Findings

未发现实质性问题。

## Detailed Trace

### Fix #1 — `cancel_and_await_task` 集中化

- **common location**: `dayu/cli/agent_entrypoint.py:116-127` — `async def cancel_and_await_task(task)` 含完整 docstring，在 `__all__` 导出
- **prompt.py** (减 24 行)：删除私有 `_cancel_and_await_task` 定义（原行 566-578）和 `_TaskResult` TypeVar（原行 88），2 处调用替换为 `cancel_and_await_task`（行 462, 573）
- **interactive.py** (减 29 行)：删除私有 `_cancel_and_await_task` 定义（原行 646-658）和 `_TaskResult` TypeVar（原行 101），3 处调用替换为 `cancel_and_await_task`（行 642-643, 736-737, 797）
- **导入**: 两处均从 `dayu.cli.agent_entrypoint` 导入 `cancel_and_await_task`

### Fix #2 — README `--detail`/`--no-detail`

- **全局参数表**: 在 `--thinking`/`--no-thinking` 下方新增行 `--detail / --no-detail`
- **prompt 命令参数**: 新增 `--detail / --no-detail` 行，默认不显示
- **命令示例**: 新增 `dayu-cli prompt "总结苹果最新财报中的主要风险" --detail`
- **说明**: 新增"默认不显示运行态 activity stream；如需查看工具调用、运行状态等过程信息，显式传 `--detail`"

### Fix #3 — PR body scope

- 更新后 PR body Summary 从 3 项扩展到 6 项，覆盖 activity stream、output-channel cleanup、Fins progress、interactive resume startup、follow-up hardening、inline repair
- 新增 "Known Non-Blocking Residual" 节记录两处 pre-existing smoke failures

### Fix #4 — control doc pre-existing failures

- `WU-CLI-ACTIVITY-01-PR-R1` 条目准确记录了两处测试在 `main` 上同样失败的事实，deferred 到 Future Host public multiturn / memory smoke stabilization WU
- WU-CLI-ACTIVITY-01 条目更新了 PR review 和 PR review fix 的 artifact 引用及 next entry point

### Fix #5 — tests / pyright

- 206 passed, 3 third-party edgar deprecation warnings（非项目代码）
- pyright 0 errors, 0 warnings, 0 informations

## Open Questions

无。

## Residual Risk

- 无新增 residual risk。原 PR review 中 DS 和 MiMo 记录的 residual risk（pre-existing smoke failures、PR 范围广阔、缺 CI checks）已在 PR body Known Non-Blocking Residual 节和 control doc `WU-CLI-ACTIVITY-01-PR-R1` 中归档。
