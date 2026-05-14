# Gateflow Code Re-Review: Host P3-S1 Schema And Row Codecs

- **review gate name**: P3-S1 code re-review
- **reviewed target**: P3S1-MIMO-001 fix（controller-accepted finding）
- **source review artifact**: `docs/reviews/gateflow-code-review-host-p3-s1-schema-row-codecs-mimo-20260514.md`
- **controller adjudication**: `docs/reviews/gateflow-code-review-host-p3-s1-schema-row-codecs-controller-adjudication-20260514.md`
- **fix artifact**: `docs/reviews/gateflow-fix-host-p3-s1-schema-row-codecs-20260514.md`
- **reviewer**: mimo

## P3S1-MIMO-001 Re-Review

### Finding 最终状态

**已修复。**

### Fix 验证

controller 要求：增加测试，验证同一 Session 可同时存在 active Run 与 terminal Run，不触发 `host_runs_one_active_per_session` partial unique index。覆盖 `SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST` 四个 terminal status。

实际变更（`tests/host/test_state_schema.py`）：

1. 新增模块级常量 `_TERMINAL_RUN_STATUSES`（line 46-51），包含 `SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST`。
2. 新增测试 `test_same_session_active_and_terminal_runs_succeed`（line 220-259），使用 `@pytest.mark.parametrize("terminal_status", _TERMINAL_RUN_STATUSES)` 参数化，对每个 terminal status 插入同一 Session 的一个 RUNNING active Run 和一个 terminal Run，断言该 Session 下 Run 总数为 2。
3. `_insert_run_tx` helper（line 643-748）被更新：新增 `terminal_event_id`/`terminal_sequence`/`terminal_at` 逻辑分支（line 688-696），当 `status in _TERMINAL_RUN_STATUSES` 时创建 terminal event row 并填充 terminal fields，满足 schema CHECK 约束。

测试覆盖完整性：

- `SUCCEEDED` — `test_same_session_active_and_terminal_runs_succeed[succeeded]` PASSED
- `FAILED` — `test_same_session_active_and_terminal_runs_succeed[failed]` PASSED
- `CANCELLED` — `test_same_session_active_and_terminal_runs_succeed[cancelled]` PASSED
- `LOST` — `test_same_session_active_and_terminal_runs_succeed[lost]` PASSED

验证结果：`18 passed in 0.14s`（原 14 项 + 新增 4 项参数化），pyright 无新增错误。

### Source Title Update

- `P3S1-MIMO-001`：source review artifact finding title 已从 `未修复` 更新为 `已修复`；controller decision status 已从 `pending-controller-decision` 更新为 `accepted → 已修复`。

### P3S1-MIMO-002 确认

controller 裁决为 `rejected-with-reason`。source review artifact 中 P3S1-MIMO-002 的 controller decision status 已更新为 `rejected-with-reason`。本 re-review 不修改该 finding 的 `未修复` title，因为 controller 裁决不要求修复。

### 新 blocker / risk

无。fix 变更仅限测试文件，无生产代码变更，无新增风险。

## Artifact Path

`docs/reviews/gateflow-code-re-review-host-p3-s1-schema-row-codecs-mimo-20260514.md`

## Summary

- **P3S1-MIMO-001 final status**: 已修复
- **blocking finding 数量**: 0
- **是否建议 accepted slice commit**: 是
