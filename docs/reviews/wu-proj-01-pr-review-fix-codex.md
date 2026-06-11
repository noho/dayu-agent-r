# WU-PROJ-01 PR Review Fix — AgentCodex

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: PR review fix gate
- 日期: 2026-06-11
- PR: `https://github.com/noho/dayu-agent-r/pull/136`
- 修复人: AgentCodex

## Preflight

| 检查项 | 结果 |
|---|---|
| 当前分支 | `wu-proj-01` |
| 工作树初始状态 | clean |

## 动机判断

PR-F1 动机成立。`docs/host/design.md` 明确 ordinary dispatch 前 Conversation Memory projection 未覆盖 required EventLog cursor 时，Host 必须执行 bounded catch-up / rebuild；若仍失败或未达到目标 cursor，应产生结构化 diagnostic 并按 pre-dispatch failure / retry / defer 策略收口。这不是 Run crash recovery，不得把 Run 推入 `RECOVERING`，也不得让 dispatch hot path 无上限同步补账。

因此 3 个旧 dispatch scheduler 测试继续期待 rebuild 未追到 required cursor 后仍创建 worker、继续旧 retry dispatch 或保持 Run `RUNNING`，与 WU-PROJ-01 新设计不一致。修复应更新测试断言，不应回退生产实现。

PR-F2 动机成立。PR body 原 validation 只列出选择性过滤结果，没有报告完整受影响测试文件集合，容易让 reviewer 误以为所有受影响测试文件完整通过。fix 后必须用完整文件集合结果更新 PR body。

## 改动摘要

- 更新 `tests/host/test_dispatch_scheduler.py` 中 memory projection lag repair 相关断言：
  - rebuild / catch-up 未达到 `required_event_sequence` 时返回 `timed_out`，不 dispatch worker。
  - builder 不进入第二次旧 retry dispatch，worker factory 不创建 worker。
  - Run / Attempt fail-closed 为 `FAILED`，dispatch record 被取消。
  - 不写 `RUN_RECOVERING`，不创建 recovery Attempt。
  - 直接断言 `dispatch.memory_projection.repair_not_reached` diagnostic 日志。
- 将旧语义测试名 `test_dispatch_lag_repair_rebuild_retry_does_not_fail_run` 改为 `test_dispatch_lag_repair_rebuild_not_reached_fails_closed`，避免测试名继续表达已废弃行为。
- 未修改生产代码。

## 验证结果

完整受影响测试文件集合：

```bash
source .venv/bin/activate && python -m pytest tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_logging.py tests/host/test_open_host_runtime.py
```

结果：`185 passed in 2.08s`。

目标回归测试：

```bash
source .venv/bin/activate && python -m pytest tests/host/test_dispatch_scheduler.py::test_dispatch_lag_repair_rebuild_not_reached_fails_closed tests/host/test_dispatch_scheduler.py::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering tests/host/test_dispatch_scheduler.py::test_persistent_memory_lag_repair_failure_closes_starting_run --tb=short -q
```

结果：`3 passed in 0.44s`。

类型检查：

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

Diff whitespace 检查：

```bash
git diff --check
```

结果：通过，无输出。

## PR Body 更新说明

已用 `gh pr edit 136` 更新 PR body validation，明确报告完整受影响测试文件集合 `185 passed` 和 pyright `0 errors, 0 warnings, 0 informations`，并将旧选择性过滤结果标注为历史 review context，避免把 `-k` 子集表述为完整通过。

## README / 控制文档

- `tests/README.md` 已按触发规则检查；本次只迁移既有测试断言，不新增测试层级、运行方式或维护规则，因此无需更新。
- `docs/host/issues-implementation-control.md` 仅记录 fix completed / validation passed，未擅自推进到 re-review 或 pass。

## 剩余风险

- 本 fix 只关闭 PR-F1 / PR-F2，不改变 `WU-PROJ-01-S3-R1` 与 `WU-PROJ-01-S4-R1` 的 deferred owner。
- 当前验证覆盖 PR review 要求的完整受影响 Host 测试文件集合与 pyright；未运行全仓库 pytest。
