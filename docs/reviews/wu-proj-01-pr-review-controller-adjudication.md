# WU-PROJ-01 PR Review Controller Adjudication

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: PR review controller adjudication
- 日期: 2026-06-11
- PR: `https://github.com/noho/dayu-agent-r/pull/136`
- Controller: AgentController

## 输入

- AgentMiMo PR review: `docs/reviews/wu-proj-01-pr-review-mimo.md`
- AgentDS PR review: `docs/reviews/wu-proj-01-pr-review-ds.md`
- Draft PR: `https://github.com/noho/dayu-agent-r/pull/136`

## 裁决结论

`FAIL`。进入 PR review fix gate，由 AgentCodex 修复后重新 review。

## 直接验证

Controller 对 AgentDS 与 AgentMiMo 的冲突结论做了直接复验：

- 当前分支 `wu-proj-01` / HEAD `228c5e44`：
  - `python -m pytest tests/host/test_dispatch_scheduler.py::test_dispatch_lag_repair_rebuild_retry_does_not_fail_run tests/host/test_dispatch_scheduler.py::test_memory_lag_pre_dispatch_failure_does_not_enter_recovering tests/host/test_dispatch_scheduler.py::test_persistent_memory_lag_repair_failure_closes_starting_run --tb=short -q`
  - `3 failed`
- `main` worktree / HEAD `b8bcabd5`：
  - 同一命令
  - `3 passed`

因此 3 个 dispatch scheduler 测试失败是 PR 引入的测试回归，不是 `main` 预存失败。AgentMiMo 关于这 3 个测试为 main 预存失败的结论被直接证据驳回。

## Accepted Findings

| ID | 来源 | 裁决 | Fix scope |
|---|---|---|---|
| PR-F1 | AgentDS F1 | accepted | 更新 3 个旧 dispatch scheduler 测试，使其断言 WU-PROJ-01 新设计下 rebuild / catch-up 未覆盖 required cursor 时 fail-closed，不进入 recovery，且不继续旧的 retry dispatch。 |
| PR-F2 | AgentDS F2 | accepted | 修复 PR body validation 描述：不得把选择性过滤结果表述为完整受影响测试；fix 后必须报告完整受影响测试文件结果。 |

## Rejected / Nonblocking Findings

| 来源 | Finding | 裁决 |
|---|---|---|
| AgentMiMo F1 | 3 个 dispatch scheduler 测试为 main 预存失败 | rejected-with-evidence；controller 在 `main` worktree 直接复验同 3 个测试为 `3 passed`。 |
| AgentMiMo F2 | `_memory_projection_catchup_budget` unsupported purpose defensive branch 无直接测试 | rejected-as-nonblocking；aggregate deepreview 已裁决该分支为 defensive guard。 |

## Fix Gate 要求

AgentCodex fix gate 必须完成：

- 更新 `tests/host/test_dispatch_scheduler.py` 中以下 3 个测试：
  - `test_dispatch_lag_repair_rebuild_retry_does_not_fail_run`
  - `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering`
  - `test_persistent_memory_lag_repair_failure_closes_starting_run`
- 断言新设计行为：
  - rebuild / catch-up 没有达到 required cursor 时 fail-closed。
  - 不进入 `RECOVERING`，不创建 recovery Attempt。
  - 不继续旧的 retry dispatch 语义。
- 运行完整受影响测试文件：
  - `python -m pytest tests/host/test_compact_material.py tests/host/test_dispatch_scheduler.py tests/host/test_memory_repair.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_logging.py tests/host/test_open_host_runtime.py`
- 运行 `pyright`。
- 更新 PR body validation 文案，报告 fix 后完整受影响测试文件结果和 pyright 结果。
- 写 fix artifact：`docs/reviews/wu-proj-01-pr-review-fix-codex.md`。

## Residual Risk

此 fix 不改变 `WU-PROJ-01-S3-R1` 与 `WU-PROJ-01-S4-R1` 的 owner。它关闭的是 PR review 发现的旧测试断言不匹配问题；S3-R1 仍代表后续需要补独立 dispatch before-worker happy path 集成测试。
