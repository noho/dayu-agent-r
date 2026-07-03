# WU-WAIT-03 Aggregate Deepreview

## Scope

- Mode: current changes
- Branch: `phase/wu-wait-03-issue-92`
- Base: `main`
- Output file: `docs/reviews/wu-wait-03-aggregate-deepreview-ds.md`
- Included scope: `main...HEAD` diff (commits `6be72997`, `4e661cee`, `04fadb84`) + unstaged `docs/host/issues-implementation-control.md` gate status update
- Excluded scope: review artifacts under `docs/reviews/wu-wait-03-*` (already adjudicated by controller)
- Parallel review coverage: 无，本 review 由单一 reviewer 沿全部关键路径逐行走读
- Design sources consulted:
  - `docs/host/design.md` (分层边界、Host 治理真源)
  - `docs/engine/design.md` (Engine 不拥有 wait record)
  - `docs/host/issues-implementation-control.md` (work unit 状态)
  - `docs/host/wu-wait-03-external-job-lifecycle-plan.md` (实现计划真源)

## Verdict

**未发现 blocking finding。** 实现严格遵循 plan，state machine 无回归，分层边界干净，测试覆盖充分。2 个 non-blocking findings 为 observability 边缘情况和 forward-looking enum 未测试。

Blocking findings count: **0**

## Findings

### 1-未修复-低-unsupported/noop terminal marker 写入时 adapter 诊断原因未持久化

- **入口/函数**: `WaitPoller._abandon_cancelled_wait()` → `_MarkWaitRecordAbandonedOperation`
- **文件(行号)**: `dayu/host/wait_adapter.py:1005-1018`
- **输入场景**: adapter 返回 `WaitExternalJobLifecycleUnsupported(reason="provider_unsupported")` 或 `WaitExternalJobLifecycleNoop(reason="observation_missing")`，且 durable CAS 写入成功
- **实际分支**: `_last_outcome_for_lifecycle_result()` 将 typed result 映射为 `ABANDON_UNSUPPORTED` / `ABANDON_NOOP`，但 `lifecycle_result` 中的具体 reason 字符串在映射后被丢弃；`_MarkWaitRecordAbandonedOperation` 将 `poll_last_error_code` 和 `poll_last_error_message` 写为 NULL
- **预期行为**: 按 plan，terminal marker 写入后 adapter-specific reason 不进入 durable 列；只有 outcome enum 值被持久化。这是计划内的取舍
- **实际行为**: durable wait row 中只能看到 `poll_last_outcome = 'abandon_unsupported'` 或 `'abandon_noop'`，无法区分具体原因（例如是哪个 provider 不支持、是 observation_missing 还是 invalid_observation_handle 还是 observation_error:permanent_corrupt_handle）
- **直接证据**: `dayu/host/wait_adapter.py:1005` — `last_outcome = _last_outcome_for_lifecycle_result(lifecycle_result)` 之后 `lifecycle_result` 变量不再使用；`dayu/host/durable/state.py:2245-2247` — abandon success CAS 将 `poll_last_error_code` 和 `poll_last_error_message` 写为 NULL
- **影响**: 运维排障时若需区分同是 `ABANDON_NOOP` 的 wait 具体原因（如 `observation_missing` vs `observation_error:permanent_corrupt_handle`），须 cross-reference adapter log，无法仅从 durable DB 查询区分。不造成 correctness 问题
- **建议改法和验证点**: 如未来运营需要，可在 `WaitRecordRow` 或 abandon success CAS 中增加 `poll_last_error_code` 写入（如 `"lifecycle_noop:observation_missing"`），但当前 plan 明确不新增 durable 列。可在后续 work unit 评估是否需要此 diagnostic 精度
- **修复风险**: 低（仅涉及 durable diagnostic 字段语义，不改变状态机）
- **严重程度**: 低

### 2-未修复-低-`WaitExternalJobLifecycleAction.CANCEL` 和 `REVOKE` 已定义但无 adapter 实现和测试

- **入口/函数**: `WaitExternalJobLifecycleAction` enum 定义
- **文件(行号)**: `dayu/host/wait_adapter.py:77-82`
- **输入场景**: 未来 provider-specific adapter 返回 `WaitExternalJobLifecycleApplied(action=CANCEL)` 或 `(action=REVOKE)`
- **实际分支**: 当前所有 adapter（Fins + 测试 fake）只返回 `action=ABANDON`；`_last_outcome_for_lifecycle_result()` 中 `CANCEL` 和 `REVOKE` 都会映射为 `ABANDONED`（与 `ABANDON` 相同）
- **预期行为**: plan 明确说明 "Current Fins adapter returns ABANDON"，CANCEL/REVOKE 是 forward-looking 词汇
- **实际行为**: `_last_outcome_for_lifecycle_result()` 对 `CANCEL`、`REVOKE`、`ABANDON` 三种 action 都返回 `ABANDONED`（`dayu/host/wait_adapter.py:1366-1367`），即三种 action 在 durable 层不可区分
- **直接证据**: `dayu/host/wait_adapter.py:1366-1367` — 三个 `isinstance` 分支都映射为 `WaitPollLastOutcome.ABANDONED`
- **影响**: 当有 adapter 实现 `CANCEL` 或 `REVOKE` 时，`poll_last_outcome` 仍为 `ABANDONED`，无法区分具体 action 类型。但这属于尚未发生的 future work，当前无实际影响
- **建议改法和验证点**: 如果未来需要区分 CANCEL/REVOKE/ABANDON 的 durable 语义，可以：a) 拆分 `ABANDONED` 为三个 outcome 值；b) 将 action 写入新的 durable 列。当前实现已为这些语义预留了 enum 值，属于合理的 forward-compatible 设计
- **修复风险**: 低（当前无 adapter 使用 CANCEL/REVOKE，无回归风险）
- **严重程度**: 低

## Open Questions

1. 是否需要为 unsupported/noop terminal marker 在 durable 层保留 adapter-specific reason？（当前 plan 决定不保留，但运维排障体验可能需要在后续 work unit 评估）
2. `WaitExternalJobLifecycleAction.CANCEL` 和 `REVOKE` 在 durable 层是否应与 `ABANDON` 区分？（当前都映射为 `ABANDONED`，如未来有 adapter 实现 CANCEL/REVOKE，可能需要在 durable outcome 中体现区分）

## Residual Risk

1. **Provider-specific physical cancel/revoke 未测试**：当前无 adapter 实现 `CANCEL` 或 `REVOKE` action，对应的 Host poller 路径（`_last_outcome_for_lifecycle_result` 对 CANCEL/REVOKE 的处理）仅通过现有 ABANDON 测试间接覆盖。Owner: 后续 provider-specific adapter 实现者（GitHub Issue #92 / #87）。

2. **Poller-disabled 部署不执行 lifecycle 动作**：当 `WaitPollerRuntimePolicy.enabled=False` 时，cancelled wait 的 external job lifecycle 不会被执行。Host Run 取消仍正确，但 provider 侧资源（如 Fins observation handle）不会被释放。Owner: Service/composition 部署和 WU-WAIT-04 production-grade E2E smoke。

3. **Running Fins operation 只在 checkpoint 响应取消**：`test_abandon_submitted_observation_cancels_and_keeps_storage_artifacts` 证明 cooperative cancellation 仅在下一次 `cancellation_checker()` 调用时生效（`runner.cancellation_checks == (True,)`）。如果 blocking I/O 在 checkpoint 之间耗时过长，observation 释放可能延迟。Owner: Fins provider/runtime owners。

4. **Unstaged `docs/host/issues-implementation-control.md` 变更**：当前 gate status 更新（`accepted-slice` → `aggregate-deepreview`）仅在 working tree，未 commit。该变更是本 review 的前置元数据更新，不涉及代码行为。

5. **未覆盖的 defensive code path**：`_last_outcome_for_lifecycle_result()` 的 `TypeError` raise 分支（`dayu/host/wait_adapter.py:1372`）在当前类型系统下不可达（输入类型为封闭联合），无测试覆盖。这是 defensive coding，不需要测试。

## Review Coverage Summary

### 已覆盖的关键路径（沿真实代码逐行走读）

| 路径 | 入口 | 验证方式 |
|---|---|---|
| Host cancel command path 不调用 adapter | `dayu/host/admission.py:_cancel_waiting()` | 代码走读确认 command path 只调 `cancel_waiting_run_in_transaction`，不调 `abandon_wait` |
| Wait record `waiting → cancelled` transition | `dayu/host/durable/run_transition.py:cancel_waiting_run_in_transaction()` | 代码走读确认 CAS 在同一 transaction 内完成，payload 不含 provider lifecycle result |
| Poller cancelled wait → applied terminal | `dayu/host/wait_adapter.py:_abandon_cancelled_wait()` | 测试 `test_cancelled_poll_wait_is_abandoned_once_without_resolve` |
| Poller cancelled wait → unsupported terminal | 同上 | 测试 `test_cancelled_poll_wait_unsupported_marks_terminal_without_resolve` |
| Poller cancelled wait → noop terminal | 同上 | 测试 `test_cancelled_poll_wait_noop_marks_terminal_without_resolve` |
| Poller cancelled wait → exception retry | 同上 | 测试 `test_failed_cancelled_wait_abandon_is_retried_next_poll` |
| Poller cancelled wait → missing adapter backoff | 同上 | 测试 `test_cancelled_poll_wait_missing_adapter_stays_retryable` |
| Poller abandon CAS conflict → retryable | 同上 | 测试 `test_abandon_cas_conflict_leaves_cancelled_wait_retryable` |
| Poller unsupported/noop CAS conflict → retryable | 同上 | 测试 `test_terminal_abandon_cas_conflict_leaves_cancelled_wait_retryable` (parametrized) |
| Close gate during abandon → terminal marker still written | 同上 | 测试 `test_cancelled_abandon_success_marks_abandoned_when_close_gate_closes` |
| Adapter exception isolation per wait record | 同上 | 测试 `test_adapter_non_runtime_exception_isolated_per_wait_record` |
| Fins abandon: valid handle → ABANDON applied | `dayu/fins/ingestion/wait_adapter.py:abandon_wait()` | 测试 `test_fins_wait_poll_adapter_abandon_cancels_and_cleans_observation` |
| Fins abandon: corrupt token → noop | 同上 | 测试 `test_fins_wait_poll_adapter_abandon_corrupt_token_is_noop` |
| Fins abandon: missing observation → noop | 同上 | 测试 `test_fins_wait_poll_adapter_abandon_missing_observation_is_noop` |
| Fins abandon: LOST snapshot → noop | 同上 | 测试 `test_fins_wait_poll_adapter_abandon_lost_snapshot_is_noop` |
| Fins abandon: non-transient abandon error → noop | 同上 | 测试 `test_fins_wait_poll_adapter_abandon_non_transient_error_is_noop` |
| Fins abandon: non-transient cancel error → noop | 同上 | 测试 `test_fins_wait_poll_adapter_abandon_cancel_non_transient_error_is_noop` |
| Fins abandon: transient unavailable → re-raise | 同上 | 测试 `test_fins_wait_poll_adapter_abandon_transient_unavailable_re_raises` |
| Fins runtime: prepared observation abandon before activation | `dayu/fins/ingestion_runtime.py` | 测试 `test_abandon_cancelled_prepared_observation_releases_handle_before_activation` |
| Fins runtime: submitted observation abandon keeps artifacts | 同上 | 测试 `test_abandon_submitted_observation_cancels_and_keeps_storage_artifacts` |
| Schema version bump + CHECK constraint | `dayu/host/durable/schema.py` | 测试 `test_host_schema_version_is_query_index_version` + `test_wait_record_table_and_indexes_are_created` |
| Codec roundtrip for new outcome values | `dayu/host/durable/state.py` | 测试 `test_wait_poll_terminal_outcome_codecs_roundtrip_new_values` |
| Abandon marker CAS with parametrized outcome | 同上 | 测试 `test_poll_abandon_success_marks_row_and_clears_claim` (parametrized) |
| Late result after cancel still rejected | `dayu/host/admission.py:resolve_wait()` | 已有测试 `test_late_result_after_cancel_writes_bounded_diagnostic`（未在本 WU 修改） |
| resolve_wait NOT called from abandon path | `dayu/host/wait_adapter.py:_abandon_cancelled_wait()` | 测试中使用 `_NoResolveResolver` 断言的 unsupported/noop 测试 |
| LLM-facing text: Fins observation handle ID 未泄漏 | `dayu/fins/ingestion/wait_adapter.py:_ABANDON_APPLIED_MESSAGE` | 测试 `assert "finsobs_" not in result.message` |
| Typed lifecycle result → durable outcome mapping | `dayu/host/wait_adapter.py:_last_outcome_for_lifecycle_result()` | 通过所有 abandon 测试的 outcome 断言间接覆盖 |
| adapter test fakes 更新为 typed return | `tests/host/test_wait_adapter_polling.py`, `tests/host/test_wait_poller_runtime.py`, `tests/host/test_open_host_runtime.py` | 所有 fake adapter 的 `abandon_wait` 签名已更新 |
| `__all__` exports 完整 | `dayu/host/wait_adapter.py:1541-1570` | 代码走读确认新类型全部导出 |
| Fins `__init__` re-export | `dayu/fins/ingestion/` | 不需要 re-export — Fins adapter 类型从 Host import |

### 分层边界检查

| 检查项 | 结论 |
|---|---|
| Host → Engine 反向依赖 | 无 |
| Fins → Host 依赖方向 | 正确：Fins adapter import Host typed contract |
| `dayu.runtime` 越界 | 未修改 |
| Host durable state 被 Fins 直接写入 | 否，Fins adapter 只通过 Host poller 间接影响 durable state |
| Engine public contract 变更 | 无 |
| cancel command path 中调用 provider I/O | 否，plan 明确禁止且代码未违反 |

### 未覆盖区域

- `WaitExternalJobLifecycleAction.CANCEL` / `REVOKE` 的 adapter 实现和端到端测试（无 adapter 实现这些 action）
- `_last_outcome_for_lifecycle_result()` 的 `TypeError` defensive raise 分支
- Poller loop fatal exception recovery 场景中 cancelled wait lifecycle 行为（Fins adapter 抛非 `FinsObservationPollError` 异常时的 converge 行为）
- `_ABANDON_APPLIED_MESSAGE` 精确内容断言（仅断言了不含 `finsobs_` 前缀，未断言完整消息内容）
