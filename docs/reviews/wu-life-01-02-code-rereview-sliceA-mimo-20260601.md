# WU-LIFE-01 + WU-LIFE-02 Slice A Code Re-Review

日期：2026-06-01
Reviewer：AgentMiMo
Role：focused re-review
Gate：code re-review slice A
Controller：AgentController
Accepted findings 裁决：`docs/reviews/wu-life-01-02-code-controller-adjudication-sliceA-20260601.md`
Fix report：`docs/reviews/wu-life-01-02-fix-sliceA-codex-20260601.md`
原 code review：
- `docs/reviews/wu-life-01-02-code-review-sliceA-mimo-20260601.md`
- `docs/reviews/wu-life-01-02-code-review-sliceA-ds-20260601.md`
Review target：当前工作区未提交 diff（`tests/host/test_recovery_scan.py`）

## Conclusion: pass

全部 6 项 accepted findings 已修复，0 项残留。无新增越界修改、生产代码修改、schema/EventLog/public API/state-machine/WAITING 语义变化。

## Accepted Findings 复核

### A-MIMO-01 — `run_read` 修复

**裁决要求**：`_active_run_observation` 纯读 helper 应使用 `run_read`，避免在测试 helper 中表达写意图。

**复核结果**：fixed。`test_recovery_scan.py:1296` 使用 `return transaction_runner.run_read(operation)`。同文件 `_event_type_count`（line 1479）同样使用 `run_read`，语义一致。

---

### A-MIMO-02 — 无关机械格式化 churn 回退

**裁决要求**：回退旧代码上的无关机械 reflow，只保留必要代码变更。

**复核结果**：fixed。当前 diff 仅包含语义新增：新 import（`AttemptStatus`、`TABLE_HOST_ATTEMPT_DISPATCH_RECORDS`、`read_attempt_by_id`、`read_dispatch_record_by_attempt_id`）、新常量（`_REASON_*`、`_COVERAGE_*`）、新 dataclass（`_RecoveryLifecycleMatrixRow`、`_ActiveRunObservation`、`_PidLiveNoIdentityProbe`、`_PidProbeErrorProbe`）、新测试函数（6 个）、新 helper（`_delete_dispatch_record_for_attempt`、`_mark_owner_heartbeat`、`_active_run_observation`、`_assert_no_recovery_or_terminal_facts`）。未发现对既有函数签名、assert 语句、链式调用格式的无关 reflow。

---

### A-DS-01 — 格式化 churn 回退（同 A-MIMO-02）

**裁决要求**：回退无关格式化 churn，保持 review diff 聚焦。

**复核结果**：fixed。与 A-MIMO-02 复核结论一致。最终 diff 聚焦 Slice A matrix、tests、helpers 的语义新增。

---

### A-DS-02 — WAITING matrix 精确拆分

**裁决要求**：WAITING matrix row 需要拆分 low-level existing 与 durable-read new，或等价地精确表达现有覆盖增强和新增 durable-read 覆盖。

**复核结果**：fixed。matrix 已拆为两行：

| scenario_id | coverage_classification | 说明 |
|---|---|---|
| `waiting-diagnostic-only-low-level` | `_COVERAGE_EXISTING` | 对应既有 `test_scan_waiting_uses_diagnostic_only_fallback` |
| `waiting-durable-read-diagnostic-only` | `_COVERAGE_NEW` | 对应新增 `test_scan_waiting_durable_read_state_remains_diagnostic_only` |

`test_recovery_lifecycle_proof_matrix_covers_slice_a_rows`（line 478-479）断言两行分类正确。

---

### A-DS-03 — `running-missing-current-attempt-or-dispatch` deterministic scanner 测试

**裁决要求**：应补轻量 deterministic scanner test，或改为 new 并在本 slice 内完成该 new coverage。

**复核结果**：fixed。两处修改：

1. matrix row（line 184）：`coverage_classification=_COVERAGE_NEW`（从 `_COVERAGE_EXISTING` 改为 `_COVERAGE_NEW`）。
2. 新增 `test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation`（line 602-630）：通过 `_delete_dispatch_record_for_attempt` 删除 dispatch row 构造 RUNNING + 缺失 dispatch 的 deterministic 场景，断言 `ORPHAN_INCONCLUSIVE`、reason 为 `_REASON_MISSING_CURRENT_ATTEMPT_OR_DISPATCH`、Run 状态不变、dispatch row 数为 0、无 recovery/terminal facts。

`test_recovery_lifecycle_proof_matrix_covers_slice_a_rows`（line 480）断言该行 classification 为 `_COVERAGE_NEW`。

---

### A-DS-04 — durable-read WAITING 测试名/docstring 不再暗示 public API

**裁决要求**：改名为明确 durable 语义的名称，或在名称和 docstring 中消除误导。

**复核结果**：fixed。测试名从 `test_scan_waiting_public_visible_durable_state_remains_diagnostic_only` 改为 `test_scan_waiting_durable_read_state_remains_diagnostic_only`（line 574）。docstring（line 577）为 "WAITING startup scan 后 durable read 仍保持等待诊断语义"，不再暗示 public API 路径。

---

## 边界检查

| 边界 | 状态 | 证据 |
|---|---|---|
| 生产代码修改 | 未修改 ✓ | diff 仅含 `tests/host/test_recovery_scan.py` |
| Durable schema | 未变更 ✓ | 无 schema 文件修改 |
| EventLog event type | 未变更 ✓ | 无新 event type 定义 |
| Host public API | 未变更 ✓ | 无 `dayu/host/api.py` 修改 |
| Run / Attempt state machine | 未变更 ✓ | 无状态转换逻辑修改 |
| WAITING durable semantics | 未变更 ✓ | 无 WAITING 语义变更 |
| 测试验证命令 | 通过 ✓ | fix report 声明 33 passed, pyright 0 errors |

## 新增越界修改检查

未发现。所有变更均在 controller 授权的 fix scope（`tests/host/test_recovery_scan.py`）内。新增 import 仅用于测试 helper（`AttemptStatus` 用于 `_ActiveRunObservation` 字段类型、`TABLE_HOST_ATTEMPT_DISPATCH_RECORDS` 用于 `_delete_dispatch_record_for_attempt`、`read_attempt_by_id`/`read_dispatch_record_by_attempt_id` 用于 `_active_run_observation`）。

## Blocking Open Questions

none
