# A2 Host Liveness Lifecycle Hardening Fix

- **Date**: 2026-05-14
- **Branch**: `fix/host-phase-4`
- **Scope source**: `docs/reviews/repo-review-controller-adjudication-20260514.md` A2
- **Source findings**:
  - `docs/reviews/repo-review-20260514-1937.md` finding 01
  - `docs/reviews/repo-review-20260514-1937.md` finding 02
  - `docs/reviews/repo-review-20260514-1936.md` finding 6

## Motivation Check

A2 的动机成立。当前 Host recovery 尚未实现，因此这不是已经触发的 recovery bug；但 liveness row 会成为 Phase 11 recovery 输入，若现在允许 `STOPPED` / `CRASHED_SUSPECTED` 回退到活动状态，后续 recovery 会继承错误状态不变量。

直接证据来自 `dayu/host/durable/liveness.py` 原实现：

- `register_current_instance()` 对既有同身份 row 无条件写 `status = running`。
- `heartbeat_current_instance()` 也会写 `status = running`，且未校验 UPDATE rowcount。
- `_mark_current_instance_status()` 缺少来源状态守卫，`STOPPED -> STOPPING` 可被接受，且未校验 UPDATE rowcount。

## Implemented Changes

修改文件：

- `dayu/host/durable/errors.py`
- `dayu/host/durable/liveness.py`
- `tests/host/test_host_instance_liveness.py`

核心行为：

- 新增 `HostInstanceLifecycleConflictError`，用于区分身份冲突与 lifecycle 状态转移冲突。
- `register_current_instance()` 不再允许 `STOPPED` / `CRASHED_SUSPECTED` 同身份 row 回到 `RUNNING`。
- `heartbeat_current_instance()` 增加来源状态守卫和 rowcount 校验，避免终态 row 被 heartbeat 写回 `RUNNING`。
- `heartbeat_current_instance()` 只允许 `RUNNING` 来源状态，不能把 `STOPPING` 静默回退为 `RUNNING`；`register_current_instance()` 作为显式重注册路径仍保留 `STOPPING -> RUNNING`。
- `mark_current_instance_stopping()` 只允许 `RUNNING -> STOPPING`。
- `mark_current_instance_stopped()` 允许 `RUNNING -> STOPPED` 与 `STOPPING -> STOPPED`，保持当前 shutdown 标记语义。
- status mark 缺 row 的既有行为保持不变：`mark_current_instance_stopping()` / `mark_current_instance_stopped()` 在 row 不存在时返回 `None`。
- heartbeat 与 status mark UPDATE 均检查 `rowcount`；零命中后重新读取 durable row 并分类为：
  - 身份漂移：`HostInstanceIdentityConflictError`
  - lifecycle 来源状态不允许：`HostInstanceLifecycleConflictError`
  - row 消失：`HostInstanceNotRegisteredError`

## Tests Added

新增覆盖：

- `STOPPED` / `CRASHED_SUSPECTED` 不会被 `register_current_instance()` 或 `heartbeat_current_instance()` 回写为 `RUNNING`。
- `STOPPED` / `CRASHED_SUSPECTED` 不会被 `mark_current_instance_stopping()` 回退为 `STOPPING`，也不会被 `mark_current_instance_stopped()` 覆盖为 `STOPPED`。
- `STOPPING` 不会被自动 heartbeat 静默回退为 `RUNNING`。
- 显式 `register_current_instance()` 仍可将 `STOPPING` 同身份 row 恢复为 `RUNNING`。
- register identity precheck 通过后 UPDATE 零命中会暴露为结构化 `HostInstanceIdentityConflictError`。
- heartbeat identity precheck 通过后 UPDATE 零命中会暴露为结构化 `HostInstanceIdentityConflictError`。
- status mark identity precheck 通过后 UPDATE 零命中会暴露为结构化 `HostInstanceIdentityConflictError`。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_host_instance_liveness.py -q
```

结果：`16 passed`

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

结果：`0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

结果：通过，无 whitespace error。

## README Check

未更新 README。此次变更只收紧 Host liveness primitive 行为并新增聚焦测试，没有改变测试分层、测试运行方式、公共命令、配置入口或 README 职责范围内的稳定说明。

## Explicit Non-goals

本 work unit 未实现 recovery、lease / fencing、takeover、dispatch owner、Phase 11 recovery scan 或 crash classifier。
