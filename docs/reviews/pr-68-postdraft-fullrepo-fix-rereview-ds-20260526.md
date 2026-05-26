# PR 68 Post-Draft Fullrepo Fix Re-Review

## Verdict: PASS

B1、B2 修复正确，回归测试充分，无新 blocking findings。

---

## Accepted Finding Status

### B1 — PASS — 标准 governed dispatch record 初始 owner 已修正

- **修复**: `_start_governed_in_transaction`（`dispatch.py:1260-1262`）将 `owner_host_instance_id=None` 改为 `self._host_instance_identity.host_instance_id`。
- **代码路径验证**: 通过 `_start_governed_for_test` → `_start_governed_in_transaction` → `start_governed_run_with_starting_attempt_in_transaction`，确认 dispatch record 在创建事务内即携带非空 owner。
- **回归测试**: `test_governed_start_sets_dispatch_owner_immediately`（`test_dispatch_scheduler.py:2584-2631`）使用 `host_instance_id="host-instance-governed-start"` 与 `host_handle_id="host-handle-governed-start"` 不同的配置，断言 dispatch record owner 非空、等于 `scheduler.host_instance_id`、不等于 handle id。
- **crash window 闭合**: 修复前事务提交后 owner=NULL → recovery `OrphanProofInconclusive`；修复后事务提交时 owner 已写入 → recovery 可正常追溯 orphan。

### B2 — PASS — WAITING_FOR_LANE / DISPATCHING owner 使用 instance id

- **修复**: `_mark_waiting_for_lane`（`dispatch.py:2116-2118`）和 `_mark_dispatching_after_recheck`（`dispatch.py:2175-2177`）将 `self._host_handle_id` 改为 `self._host_instance_identity.host_instance_id`。
- **代码路径验证**: 两处均通过 `mark_dispatch_waiting_for_lane_row` / `mark_dispatching_after_lane_row` 的 durable write transaction 写入正确的 owner 字段。
- **回归测试**: `test_dispatching_after_recheck_requires_waiting_for_lane`（`test_dispatch_scheduler.py:1776-1826`）使用 `host_instance_id="host-instance-dispatch-recheck"` 与 `host_handle_id="host-handle-dispatch-recheck"` 不同的配置，断言 WAITING_FOR_LANE row 和 DISPATCHING row 的 owner 都等于 `scheduler.host_instance_id` 且不等于 handle id；若仍传 handle id，durable CAS 会因 owner 不匹配而失败。
- **FK 一致性**: `host_instance_id` 字段语义真源统一为 `HostInstanceIdentity.host_instance_id`，不再依赖 handle id 与 instance id 的巧合相等。

---

## New Blocking Findings

无。

---

## Validation Reviewed

| 验证项 | 结果 |
|---|---|
| `pytest test_governed_start_sets_dispatch_owner_immediately` | PASS |
| `pytest test_dispatching_after_recheck_requires_waiting_for_lane` | PASS |
| `pytest tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py` | 95 passed |
| `pyright dayu/host/dispatch.py tests/host/test_dispatch_scheduler.py` | 0 errors, 0 warnings, 0 informations |

### 生命周期回归检查

- `HostDispatchScheduler.host_instance_id` property（`dispatch.py:773-779`）正确代理到 `self._host_instance_identity.host_instance_id`，语义单一。
- `_open_scheduler` 测试 helper（`test_dispatch_scheduler.py:3319-3400`）双路径设计清晰：无 `host_instance_identity` 时走默认 `HostDispatchScheduler.open()`；有 `host_instance_identity` 时预注册 host instance 后打开 scheduler。不影响已有测试的行为。
- `_start_governed_for_test`（`test_dispatch_scheduler.py:3953-3972`）直接调用 `scheduler._start_governed_in_transaction`，正确覆盖真实 governed start 路径。

### 预存失败（非本次 fix 引入）

`tests/runtime/test_scene_assets_migration.py::test_scene_manifest_agent_policy_carries_old_max_iterations_only` 因 PR 68 新增 smoke scene manifests 声明了 `agent_policy` 但测试 allowlist 未更新而失败。此为 MiMo review 的 finding B1，与本次 B1/B2 dispatch owner fix 无关。

---

## Controller Adjudication

- B3（governance FAILED 语义）不在本次 fix 范围，**已确认未处理**。无 `RunStatus.REJECTED` 新增，无 schema 变更。
- Reactive multi-pass shared attempt budget 语义未改动，**已确认**。

---

## Residual Risks

1. 未做真实进程 kill 的崩溃恢复集成测试。当前回归测试通过直接验证 crash window 的 durable 前置条件（dispatch record 创建时 owner 已存在）来间接覆盖，未在 OS 进程级验证 recovery scan 能正确 close orphan。
2. `test_scene_assets_migration` 预存失败需要在后续 fix 中处理（更新 allowlist 或移除 smoke scene 的 agent_policy 声明），不在本次 scope 内。
