# Code Re-Review

## Scope

- Mode: current changes
- Branch: `phase/wu-wait-03-issue-92`
- Base: `main`
- Output file: `docs/reviews/wu-wait-03-slice2-code-rereview-mimo.md`
- Included scope: WU-WAIT-03 / GitHub Issue #92 Slice 2 fix — 验证 controller accepted finding 是否已由 fix 关闭
- Excluded scope: 已由 controller 裁决为 informational / rejected 的 residual items 不在本轮 blocking findings 范围内
- Parallel review coverage: 无

## Review Focus

本轮 re-review 的唯一任务：验证 controller 在 `docs/reviews/wu-wait-03-slice2-code-review-controller-adjudication.md` 中 accepted 的 finding —— "cancel_observation(...) 非临时错误路径缺少直接测试覆盖" —— 是否已由 fix 关闭。

## Findings

未发现实质性问题。

### Accepted Finding Closure Verification

Controller accepted finding 要求：

> Add a focused Fins adapter test using `cancel_errors` with `FinsObservationPollErrorKind.PERMANENT_CORRUPT_HANDLE`; assert `WaitExternalJobLifecycleNoop(reason="observation_error:permanent_corrupt_handle")`, `cancelled_handles == (handle_id,)`, and `abandoned_handles == ()`.

**Fix 验证结果：已正确关闭。**

新增测试 `test_fins_wait_poll_adapter_abandon_cancel_non_transient_error_is_noop`（`tests/fins/test_fins_ingestion_tools.py`）覆盖了以下全部断言：

1. **`WaitExternalJobLifecycleNoop` 返回类型** — `assert isinstance(result, WaitExternalJobLifecycleNoop)` ✓
2. **reason 为 `observation_error:permanent_corrupt_handle`** — `assert result.reason == "observation_error:permanent_corrupt_handle"` ✓
3. **cancel 已尝试** — `assert runtime.cancelled_handles == (handle.handle_id,)` ✓
4. **abandon 未调用** — `assert runtime.abandoned_handles == ()` ✓

### Assertion Evidence Walkthrough

测试使用 `_FakeObservationRuntime(cancel_errors={handle_id: FinsObservationPollError(FinsObservationPollErrorKind.PERMANENT_CORRUPT_HANDLE, ...)})` 注入 cancel 阶段的稳定错误。生产代码 `FinsIngestionWaitPollAdapter.abandon_wait(...)` 在 `cancel_observation(...)` 抛出 `FinsObservationPollError` 且 `error_kind` 非 `TRANSIENT_UNAVAILABLE`、非 `PERMANENT_NOT_FOUND` 时，落入 `_observation_error_reason(exc.error_kind)` 返回 `WaitExternalJobLifecycleNoop(reason="observation_error:permanent_corrupt_handle")`。

关键代码路径验证（`dayu/fins/ingestion/wait_adapter.py`）：

- `_run_async_observation(self.runtime.cancel_observation(handle))` 抛出 `FinsObservationPollError(PERMANENT_CORRUPT_HANDLE, ...)` — `exc.error_kind is FinsObservationPollErrorKind.TRANSIENT_UNAVAILABLE` 为 False — `exc.error_kind is FinsObservationPollErrorKind.PERMANENT_NOT_FOUND` 为 False — 进入 `return WaitExternalJobLifecycleNoop(reason=_observation_error_reason(exc.error_kind))` — `_observation_error_reason` 返回 `"observation_error:permanent_corrupt_handle"` — 不再调用 `abandon_observation(...)`。

路径正确，断言完整。

### Side Observations (Non-blocking)

本轮 fix 未修改生产代码（`dayu/fins/ingestion/wait_adapter.py` 的变更属于 Slice 2 implementation，不在本轮 fix 范围内）。Fix 只新增了 `_FakeObservationRuntime` 的 `cancel_errors` / `abandon_errors` 字段和 4 个 focused regression test。

新增的 `cancel_errors` 和 `abandon_errors` 注入字段是测试夹具的自然扩展，与已有 `poll_errors` 注入模式一致，不引入测试框架设计风险。

## Verdict

- **Verdict**: `pass`
- **Blocking findings**: 0
- **Accepted finding closed**: 是 — cancel-side `PERMANENT_CORRUPT_HANDLE` regression test 已正确覆盖 controller accepted finding，断言完整匹配所要求的全部 4 个条件
- **Residual risk**: 无新增 residual risk。Controller adjudication 中已分类的 informational items（`_BlockingArtifactUploadRunner` timing、cancel 成功但 abandon 失败、cancel + abandon 双重取消请求）不在本轮 re-review 范围内

## Residual Risk

- 无新增 residual risk。
- Controller 裁决的 informational residual items 保持不变：provider lifecycle cleanup 仍是 best-effort；poller-disabled 部署仍依赖 durable Host cancellation truth。

## Validation

已验证（与 controller 要求一致）：

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q
# 126 passed, 3 warnings (edgar deprecation)

source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py tests/host/test_wait_cancel_late_result.py -q
# 35 passed

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations

git diff --check
# 通过，无输出
```
