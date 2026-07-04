# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-wait-03-issue-92`
- Base: `main`
- Output file: `docs/reviews/wu-wait-03-slice2-code-review-mimo.md`
- Included scope: WU-WAIT-03 Slice 2 implementation files
  - `dayu/fins/ingestion/wait_adapter.py`（Fins adapter mapping）
  - `tests/fins/test_fins_ingestion_tools.py`（Fins adapter tests）
  - `tests/fins/test_fins_ingestion_runtime.py`（Fins runtime observation tests）
  - `docs/reviews/wu-wait-03-slice2-implementation-codex.md`（implementation artifact）
- Excluded scope: `docs/host/issues-implementation-control.md`（controller bookkeeping，非实现缺陷）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## 逐项 Review 证据

### 1. abandon_wait 返回 WaitExternalJobLifecycleResult

- **文件**: `dayu/fins/ingestion/wait_adapter.py:150-189`
- **证据**: 方法签名 `def abandon_wait(self, wait_record: WaitRecordRow) -> WaitExternalJobLifecycleResult`。返回类型 `WaitExternalJobLifecycleResult` 从 `dayu/host/wait_adapter.py:149-154` 导入，是 `WaitExternalJobLifecycleApplied | WaitExternalJobLifecycleUnsupported | WaitExternalJobLifecycleNoop` 的封闭联合。
- **结论**: 关闭 Slice 1 deferred finding。✅

### 2. valid handle: cancel → abandon → ABANDON applied

- **文件**: `dayu/fins/ingestion/wait_adapter.py:169-179`
- **证据**:
  1. `snapshot = _run_async_observation(self.runtime.cancel_observation(handle))` — 先取消
  2. `if snapshot.status is FinsObservationStatus.LOST: return Noop(...)` — LOST 检查
  3. `_run_async_observation(self.runtime.abandon_observation(handle))` — 释放本地 handle
  4. `return WaitExternalJobLifecycleApplied(action=WaitExternalJobLifecycleAction.ABANDON, message=_ABANDON_APPLIED_MESSAGE)` — 返回 ABANDON
- **泄漏检查**: `_ABANDON_APPLIED_MESSAGE` 是常量 `"Fins observation cancellation was requested and local observation tracking was released."`，不包含 Host wait id、adapter key、tool call id 或 observation handle id。✅
- **测试**: `test_fins_wait_poll_adapter_abandon_cancels_and_cleans_observation` 验证 `result.action is ABANDON`、`"finsobs_" not in result.message`。✅

### 3. corrupt token → Noop(reason="invalid_observation_handle")

- **文件**: `dayu/fins/ingestion/wait_adapter.py:164-168`
- **证据**: `_handle_from_wait_record` 对无法解析的 token 返回 `None`，直接返回 `Noop(reason=_ABANDON_REASON_INVALID_OBSERVATION_HANDLE)`。
- **测试**: `test_fins_wait_poll_adapter_abandon_corrupt_token_is_noop` 验证 `result.reason == "invalid_observation_handle"` 且 `cancelled_handles == ()`。✅

### 4. missing observation → Noop(reason="observation_missing")

- **文件**: `dayu/fins/ingestion/wait_adapter.py:170-174`（LOST snapshot）及 `183-186`（PERMANENT_NOT_FOUND exception）
- **证据**:
  - LOST snapshot path: `cancel_observation` 返回 snapshot 后检查 `snapshot.status is LOST`。
  - PERMANENT_NOT_FOUND path: `cancel_observation` 抛出 `PERMANENT_NOT_FOUND` 异常，被 catch 块捕获映射。
- **测试**: `test_fins_wait_poll_adapter_abandon_missing_observation_is_noop`（runtime 无 snapshot）和 `test_fins_wait_poll_adapter_abandon_lost_snapshot_is_noop`（LOST snapshot）。✅

### 5. non-transient observation error → Noop(reason="observation_error:<error_kind>")

- **文件**: `dayu/fins/ingestion/wait_adapter.py:187-189`
- **证据**: `except FinsObservationPollError` 块中，非 `TRANSIENT_UNAVAILABLE`、非 `PERMANENT_NOT_FOUND` 的错误通过 `_observation_error_reason(exc.error_kind)` 映射为 `"observation_error:<error_kind.value>"`。
- **error_kind 枚举**: `FinsObservationPollErrorKind` 有 `TRANSIENT_UNAVAILABLE`、`PERMANENT_NOT_FOUND`、`PERMANENT_CORRUPT_HANDLE` 三个成员。`PERMANENT_CORRUPT_HANDLE` 走此路径，产生 `"observation_error:permanent_corrupt_handle"`。
- **测试**: `test_fins_wait_poll_adapter_abandon_non_transient_error_is_noop` 使用 `PERMANENT_CORRUPT_HANDLE` 验证 `result.reason == "observation_error:permanent_corrupt_handle"`。✅

### 6. TRANSIENT_UNAVAILABLE → re-raise

- **文件**: `dayu/fins/ingestion/wait_adapter.py:181-182`
- **证据**: `if exc.error_kind is FinsObservationPollErrorKind.TRANSIENT_UNAVAILABLE: raise` — 优先级最高，在其他错误映射之前。
- **测试**: `test_fins_wait_poll_adapter_abandon_transient_unavailable_re_raises` 验证 `pytest.raises(FinsObservationPollError)` 且 `error_kind is TRANSIENT_UNAVAILABLE`。Host poller 重试语义由 `tests/host/test_wait_adapter_polling.py` 覆盖。✅

### 7. prepared observation cancel + abandon 防 submit

- **文件**: `tests/fins/test_fins_ingestion_runtime.py:2218-2238`
- **证据**: `test_abandon_cancelled_prepared_observation_releases_handle_before_activation` — prepare → cancel → abandon → activate → poll。断言 `polled.status is LOST` 且 `executor.operations == []`，证明 activation 后不会提交 executor。✅

### 8. running/submitted observation abandon → cooperative cancel + 保留 artifacts

- **文件**: `tests/fins/test_fins_ingestion_runtime.py:2241-2287`
- **证据**: `test_abandon_submitted_observation_cancels_and_keeps_storage_artifacts` — 使用 `_BlockingArtifactUploadRunner` 写入源文档后阻塞，abandon 触发 `cancellation_checker()` 返回 `True`，验证已写入仓储产物 `source_meta["ingest_method"] == "upload"` 仍然存在。✅

### 9. 未误改 Fins durable job schema / Host contract / Engine/Service/UI/runtime/config/prompt/tool schema

- **证据**:
  - `dayu/fins/ingestion/wait_adapter.py` 只新增 import `WaitExternalJobLifecycleAction/Applied/Noop/Result`，修改 `abandon_wait` 返回类型和实现，新增 `_observation_error_reason` 辅助函数和常量。不触及 Fins durable job schema。
  - `dayu/host/wait_adapter.py` 和 `dayu/host/durable/state.py` 的 diff 为空（未在本次 diff 中修改），属于 Slice 1 已完成的变更。
  - 无 tool schema、prompt、config 变更。
- **结论**: ✅

### 10. pyright 验证

- **证据**: `pyright` 输出 `0 errors, 0 warnings, 0 informations`。✅

### 11. 测试执行

- **证据**: `pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q` 输出 `160 passed, 3 warnings`。✅

### 12. README/docs 触发决策

- **证据**: implementation artifact 记录已读取 `dayu/fins/README.md` 和 `tests/README.md` 的 Agent 更新约束。本次变更在 Fins wait adapter 既有边界内做 Host lifecycle result mapping，不改变 Fins package 稳定对外入口或架构边界；测试只在既有文件补覆盖，不新增测试层级。不更新 README 合理。✅

## Open Questions

无。

## Residual Risk

- `cancel_observation` 返回非 LOST snapshot 后 `abandon_observation` 抛出 `PERMANENT_NOT_FOUND` 的路径未被 Fins adapter 测试直接覆盖。当前实现会走 catch 块映射为 `observation_missing`，行为正确，但缺少直接测试证据。风险低，因为该路径受 catch 块统一保护。
- `_BlockingArtifactUploadRunner` 使用 `threading.Event` 和 `Thread` 做并发协作取消测试，存在极小概率的 timing flakiness。当前 timeout 设置为 1.0s，对本地测试足够。

## Verdict

**Accept。** Slice 2 实现完全符合 plan 要求，无 blocking findings。0 个 blocking findings。2 个低风险 residual items。
