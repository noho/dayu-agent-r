# PR 68 Post-Draft Fullrepo Fix

## Scope

- **Gate**: post-draft fullrepo fix
- **Role**: fix agent
- **Source review artifact**: `docs/reviews/pr-68-postdraft-fullrepo-review-ds-20260526.md`
- **Accepted findings fixed**: DS Finding B1, DS Finding B2
- **Explicit non-goals**: 未处理 B3；未修改 compaction attempt budget 语义；未提交、未推送、未创建 PR。

## Root Cause And Evidence

### Finding B1 - 已修复 - 标准 governed dispatch record 初始 owner 为 NULL

- **根因**: `HostDispatchScheduler._start_governed_in_transaction` 创建标准 governed dispatch record 时，把 `StartGovernedRunInput.owner_host_instance_id` 写成 `None`。dispatch record 创建事务提交后、进入 `_mark_waiting_for_lane` 前如果进程崩溃，recovery 只能看到 `PENDING` dispatch record 且 owner 缺失，无法证明 orphan 归属。
- **修复前直接证据**: `dayu/host/dispatch.py` 的 `_start_governed_in_transaction` 在构造 `StartGovernedRunInput` 时传入 `owner_host_instance_id=None`。
- **修复后直接证据**: `dayu/host/dispatch.py:1260-1262` 现在写入 `self._host_instance_identity.host_instance_id`。
- **回归证据**: `tests/host/test_dispatch_scheduler.py:2584-2631` 新增 `test_governed_start_sets_dispatch_owner_immediately`，用不同的 `host_handle_id` 与 `host_instance_id` 执行 governed start 后，断言 dispatch record owner 非空、等于 scheduler instance id、且不等于 handle id。

### Finding B2 - 已修复 - WAITING_FOR_LANE / DISPATCHING owner 使用 handle id

- **根因**: `_mark_waiting_for_lane` 与 `_mark_dispatching_after_recheck` 把 `owner_host_instance_id` 写成 `self._host_handle_id`。当前默认构造里 handle id 与 instance id 巧合相同，但 owner 字段的 durable FK 与 recovery 语义真源是 `host_instance_id`。
- **修复前直接证据**: `dayu/host/dispatch.py` 的两个 mark path 调用 durable helper 时传入 `owner_host_instance_id=self._host_handle_id`。
- **修复后直接证据**: `dayu/host/dispatch.py:2116-2118` 与 `dayu/host/dispatch.py:2175-2177` 现在写入 `self._host_instance_identity.host_instance_id`。
- **回归证据**: `tests/host/test_dispatch_scheduler.py:1776-1824` 扩展 `test_dispatching_after_recheck_requires_waiting_for_lane`，用不同的 handle id 与 instance id 验证 WAITING_FOR_LANE 和 DISPATCHING row owner 都等于 scheduler instance id，且不等于 handle id；若 dispatching path 仍传 handle id，durable CAS 会因为 owner 不匹配而失败。

## Files Changed

- `dayu/host/dispatch.py`
- `tests/host/test_dispatch_scheduler.py`
- `docs/reviews/pr-68-postdraft-fullrepo-fix-codex-20260526.md`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py::test_governed_start_sets_dispatch_owner_immediately tests/host/test_dispatch_scheduler.py::test_dispatching_after_recheck_requires_waiting_for_lane -q`
  - Result: `2 passed in 0.92s`
- `source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py -q`
  - Result: `95 passed in 3.40s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

## README Decision

未更新 `dayu/host/README.md`。本次变更只修正 Host 内部 dispatch owner identity 的写入时机与字段来源，没有改变 Host 对外接口、公共契约、状态机说明、事件流或开发者扩展入口。

## Residual Risks

- 未做真实进程 kill 的崩溃恢复集成测试；当前回归测试直接验证 crash window 的 durable 前置条件已经消失，即标准 dispatch record 创建事务提交后 owner 已存在。
- B3 已按 controller adjudication 明确不在本次修复范围内；未新增 `RunStatus.REJECTED`，未做 schema 变更。
- Reactive multi-pass sharing 的 `max_compaction_attempts_per_operation` 语义未改动。
