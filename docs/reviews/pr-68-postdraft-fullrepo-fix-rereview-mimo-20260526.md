# PR 68 Post-Draft Fullrepo Fix Re-Review

## Verdict: PASS

B1/B2 已修复，无新 blocking findings。

---

## Accepted Finding Status

### B1 - PASS - 标准 governed dispatch record 初始 owner 为 NULL

- **修复验证**: `dayu/host/dispatch.py:1260-1262` 现在写入 `self._host_instance_identity.host_instance_id`，不再是 `None`。
- **测试验证**: `test_governed_start_sets_dispatch_owner_immediately` 使用 `host_handle_id="host-handle-governed-start"` 与 `host_instance_id="host-instance-governed-start"`（刻意不同），断言：
  - `dispatch_record.owner_host_instance_id == scheduler.host_instance_id`
  - `dispatch_record.owner_host_instance_id is not None`
  - `dispatch_record.owner_host_instance_id != "host-handle-governed-start"`
- **修复前行为**: `owner_host_instance_id=None` → 第一条断言失败。
- **crash window 消除**: dispatch record 创建事务提交后 owner 已存在，recovery scan 不再返回 `OrphanProofInconclusive`。

### B2 - PASS - WAITING_FOR_LANE / DISPATCHING owner 使用 handle id

- **修复验证**:
  - `dayu/host/dispatch.py:2116-2118` (`_mark_waiting_for_lane`): `owner_host_instance_id=self._host_instance_identity.host_instance_id`
  - `dayu/host/dispatch.py:2175-2177` (`_mark_dispatching_after_recheck`): `owner_host_instance_id=self._host_instance_identity.host_instance_id`
- **测试验证**: `test_dispatching_after_recheck_requires_waiting_for_lane` 使用 `host_handle_id="host-handle-dispatch-recheck"` 与 `host_instance_id="host-instance-dispatch-recheck"`（刻意不同），断言 WAITING_FOR_LANE 和 DISPATCHING 两行的 `owner_host_instance_id` 均等于 instance id 且不等于 handle id。
- **修复前行为**: 两处均写入 `self._host_handle_id` → `owner_host_instance_id == "host-handle-dispatch-recheck"` → 第三条断言失败。

---

## New Blocking Findings

无。

---

## Validation Reviewed

| 检查项 | 结果 |
|---|---|
| B1 生产代码路径 | `_start_governed_in_transaction` 在 `StartGovernedRunInput` 构造时写入 instance id，非 None |
| B2 生产代码路径 | `_mark_waiting_for_lane` 与 `_mark_dispatching_after_recheck` 均使用 `self._host_instance_identity.host_instance_id` |
| 测试 handle id ≠ instance id | 两个测试均使用不同字符串，断言两者不等 |
| 测试修复前会失败 | B1: owner=None → 断言 `== instance_id` 失败；B2: owner=handle_id → 断言 `!= handle_id` 失败 |
| host_instances FK 一致性 | `_new_dispatch_host_instance_identity` 仍用 `host_handle_id` 作为 `host_instance_id`（`dispatch.py:3577`），生产环境两者相等，FK 无冲突 |
| 新增测试 helper | `_start_governed_for_test`（`test_dispatch_scheduler.py:3953`）直接调用 `_start_governed_in_transaction`，无额外逻辑 |
| `_open_scheduler` 扩展 | 新增 `host_instance_identity` 可选参数（`test_dispatch_scheduler.py:3335`），不影响现有调用方 |
| 回归测试 | 95 passed（dispatch_scheduler + recovery_dispatch + recovery_scan + run_attempt_transitions） |
| B3 未被误触 | 未新增 `RunStatus.REJECTED`，未修改 governance FAILED 语义 |
| Reactive multi-pass budget | 未修改 `max_compaction_attempts_per_operation` 语义 |

---

## Residual Risks

1. **无真实进程 kill 集成测试**: 当前测试验证 crash window 的 durable 前置条件已消失（owner 在事务提交时即存在），但未做 `SIGKILL` 后 recovery scan 端到端验证。风险低：owner 非 NULL 的前置条件已保证 recovery 路径可正确分类 orphan。

2. **生产环境 handle id = instance id**: `_new_dispatch_host_instance_identity`（`dispatch.py:3577`）仍用 `host_handle_id` 作为 `host_instance_id`，当前修复在生产环境为语义纠正（从错误引用改为正确引用），无功能差异。若未来两者分离（如 UUID-based instance id），修复已就绪。
