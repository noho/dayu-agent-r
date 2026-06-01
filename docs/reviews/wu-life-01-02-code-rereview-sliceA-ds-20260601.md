# WU-LIFE-01 + WU-LIFE-02 Slice A Focused Re-Review

日期：2026-06-01
Reviewer：AgentDS
Controller：AgentController
Gate：code re-review slice A
Accepted findings 裁决：docs/reviews/wu-life-01-02-code-controller-adjudication-sliceA-20260601.md
Fix report：docs/reviews/wu-life-01-02-fix-sliceA-codex-20260601.md
原 code review：
- docs/reviews/wu-life-01-02-code-review-sliceA-mimo-20260601.md
- docs/reviews/wu-life-01-02-code-review-sliceA-ds-20260601.md
Review target：`tests/host/test_recovery_scan.py` 当前工作区未提交 diff（`git diff HEAD`）

## Re-Review Scope

仅逐项复核 controller accepted findings 的修复质量；同时确认无越界修改、生产代码修改、schema/EventLog/public API/state-machine/WAITING 语义变化。

## Finding 逐项复核

### A-MIMO-01 — run_read helper 修复

**修复状态**：已修复。

`_active_run_observation`（line 1296）使用 `transaction_runner.run_read(operation)` 执行纯读操作。该 helper 读取 Run、Attempt、dispatch record 及 EventLog event types，不产生任何 durable mutation，`run_read` 语义正确。

### A-MIMO-02 + A-DS-01 — 无关机械格式化 churn 回退

**修复状态**：已修复。

逐项验证原 review 指出的格式化 churn 点：

- `_seed_running_dispatching_run`（line 870）：保留原始多行函数签名与 `EventLogStore().append_event(...)` 调用风格。
- `_seed_unstarted_run`（line 940）：保留原始多行签名。
- `_create_accepted_input`（line 1030 附近）、`_create_queued_input`（line 1052）、`_create_running_input`（line 1083）：均保留原始多行签名与参数列表格式。
- `_append_recovery_started_event`（line 1340）、`_mark_run_status`（line 1320 附近）：保留原始格式。
- `_event_types`（line 1436）、`_event_type_count`（line 1449）、`_event_payload_by_type`（line 1482）：保留原始格式。
- 既有测试 assert 语句（`test_scan_cancelling_positive_orphan_loses_attempt_then_run` 等）：保留原始多行 assert 格式，未收为单行。
- `store.transaction_runner.run_write(verify)` 调用（line 676）：保留原始两行写法。

`git diff --stat` 输出为 `1 file changed, 556 insertions(+)`，0 deletions，diff 聚焦 Slice A 语义新增，无旧代码格式化 churn 残留。

### A-DS-02 — WAITING matrix coverage 精确拆分

**修复状态**：已修复。

`_RECOVERY_LIFECYCLE_PROOF_MATRIX` 中 WAITING 已拆为两行：

| scenario_id | coverage_classification |
|---|---|
| `waiting-diagnostic-only-low-level` | `existing` |
| `waiting-durable-read-diagnostic-only` | `new` |

`test_recovery_lifecycle_proof_matrix_covers_slice_a_rows`（line 452）中断言：
- `rows_by_id["waiting-diagnostic-only-low-level"].coverage_classification == _COVERAGE_EXISTING`
- `rows_by_id["waiting-durable-read-diagnostic-only"].coverage_classification == _COVERAGE_NEW`

拆分精确：low-level 行对应已有 `test_scan_waiting_uses_diagnostic_only_fallback` 增强（本次增加了 reason 断言和 `_assert_no_recovery_or_terminal_facts`）；durable-read 行对应新增 `test_scan_waiting_durable_read_state_remains_diagnostic_only`。

### A-DS-03 — missing current attempt/dispatch scanner 级直接测试

**修复状态**：已修复。

新增 `test_scan_running_missing_dispatch_record_is_inconclusive_without_mutation`（line 602）：
- 通过 `_delete_dispatch_record_for_attempt` 直接构造 RUNNING + 缺失 dispatch row 的 durable 缺口。
- 运行 `StartupRecoveryScanner.scan()` 后断言 `ORPHAN_INCONCLUSIVE` decision 与 `missing_current_attempt_or_dispatch` reason。
- 断言 Run status 仍为 `RUNNING`，dispatch record count 为 0，无 recovery/terminal facts。
- 测试 deterministic：使用固定 `_NOW` 时间戳、固定 `_policy()`，无 sleep/race。

Matrix row `running-missing-current-attempt-or-dispatch` 已改为 `_COVERAGE_NEW`，matrix 覆盖测试中断言该分类。

辅助 helper `_delete_dispatch_record_for_attempt`（line 841）使用 `run_write`（写操作），语义正确；具备中文 docstring 和严格类型。

### A-DS-04 — durable-read WAITING 测试名不再暗示 public API

**修复状态**：已修复。

- 测试名：`test_scan_waiting_durable_read_state_remains_diagnostic_only`（line 574），去掉 `public_visible`，改用 `durable_read`。
- Docstring："WAITING startup scan 后 durable read 仍保持等待诊断语义"，明确标注 durable read 路径。

## 越界修改检查

| 检查项 | 结果 |
|---|---|
| 仅修改 `tests/host/test_recovery_scan.py` | `git diff --stat` 确认 1 file changed |
| 无生产代码修改 | `git diff --name-only` 确认仅 tests 文件 |
| 无 schema 变更 | 无 `TABLE_*` DDL 修改，无新增 column/table |
| 无 EventLog event type 变更 | 无新增或修改 event type 字符串常量 |
| 无 Host public API 变更 | 无 `dayu/host/` 下文件修改 |
| 无 state-machine 变更 | Run/Attempt/Dispatch status 枚举与转换未修改 |
| 无 WAITING 语义变化 | WAITING 相关断言仅证明不写 recovery/terminal facts，不改变分类逻辑 |
| 无 plan/README/control doc 修改 | 确认仅 fix report 和 test 文件在 scope 内 |

## Conclusion: pass

全部 6 项 accepted findings 均已修复，修复实现精确对齐 controller 裁决要求。未发现新增越界修改、生产代码修改、schema/EventLog/public API/state-machine/WAITING 语义变化。

- Total accepted findings：6
- Fixed：6
- Unresolved：0
- New findings：0
