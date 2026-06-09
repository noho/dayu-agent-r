# WU-TOOLS-01-F01-02 Slice 1 Re-Review

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | re-review after Slice 1 fix |
| slice | Slice 1 - Fins Awaiting Tools Token Bridge |
| fix artifact | `docs/reviews/wu-tools-01-f01-02-slice1-fix-codex.md` |
| original review artifact | `docs/reviews/wu-tools-01-f01-02-slice1-code-review-mimo.md` |
| controller adjudication | `docs/reviews/wu-tools-01-f01-02-slice1-code-review-controller-adjudication.md` |
| date | 2026-06-08 |
| reviewer | AgentMiMo |

## Scope

- 只验证 controller adjudication 中 accepted findings S1-F1 到 S1-F4 是否已修复。
- 不重新扩大到后续 slices。
- Allowed files：只写 expected re-review artifact。禁止修改代码、测试、README、控制文档。

## Finding Status

### S1-F1 `_create_queued_job` 死代码 — 已修复

**验证方法**：`rg "def _create_queued_job|_create_queued_job\(" dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`

**结果**：无匹配。方法已删除。

**git diff 确认**：`_create_queued_job` 已重命名为 `_create_queued_record_with_start_lock`，方法体从内含 `_start_lock` 改为由调用方持有锁。`start_download` 和 `start_preprocess` 现在直接在自己的 `with self._start_lock:` 块内调用 `_create_queued_record_with_start_lock`，并在此块内完成 checkpoint 和 submit。旧 wrapper 已完全移除，无新 wrapper 绕过 create/checkpoint/submit invariant。

**最终状态**：已修复。

### S1-F2 create 后 submit 前取消收口为 CANCELLED — 已修复

**验证方法**：读取 `dayu/fins/ingestion_runtime.py:1058-1059` (download) 和 `1115-1116` (preprocess)。

**结果**：

- download 路径（1058-1059）：`if _is_start_cancelled(cancellation_token): return _job_start_from_record(self._save_cancelled(start.record))`
- preprocess 路径（1115-1116）：同上结构。

`_save_cancelled` 方法（1841 行）通过 `job_store.save_job` 写入 `CANCELLED` 终态。分支不调用 `executor.submit`，不改变 Host/Engine contract。

**git diff 确认**：原代码 `request_cancel` 路径已替换为直接调用 `_save_cancelled`，job record 从 `QUEUED` 直接变为 `CANCELLED` 终态，不再是 `CANCELLING` 非终态。

**最终状态**：已修复。

### S1-F3 测试不再断言 `check_count == 2` — 已修复

**验证方法**：读取 `tests/fins/test_fins_ingestion_runtime.py` 中两个相关测试。

**download 测试**（564-580 行）：
```python
assert start.status is FinsIngestionJobStatus.CANCELLED
assert record.status is FinsIngestionJobStatus.CANCELLED
assert record.cancellation_requested
assert executor.operations == []
```

**preprocess 测试**（774-790 行）：同上结构。

两个测试均不再包含 `token.check_count == 2` 断言。行为断言对齐：CANCELLED job start、durable CANCELLED record、cancellation_requested=True、无 executor operations。

**最终状态**：已修复。

### S1-F4 `_CancelOnSecondCheckToken` 取消元数据一致性 — 已修复

**验证方法**：读取 `tests/fins/test_fins_ingestion_runtime.py:192-241`。

**结果**：

- `is_cancelled()` 在 `check_count >= 2` 时设置 `self._cancelled = True`（217-218 行）。
- `cancel_reason()` 检查 `self._cancelled`，返回 `"host-cancelled"` 或 `None`（228-230 行）。
- `requested_at()` 检查 `self._cancelled`，返回稳定 `datetime(2026, 6, 8, tzinfo=timezone.utc)` 或 `None`（239-241 行）。

一旦取消被观察（`_cancelled = True`），`cancel_reason()` 和 `requested_at()` 一致返回非 None 值。协议实现完整。

**最终状态**：已修复。

## README 验证

### `dayu/fins/README.md` — 已更新

- 432 行：`若命中取消则把 Fins job 收口为 cancelled 终态且不提交后台执行` — 使用 `cancelled` 终态描述。
- 381 行 wait adapter 映射：`queued / running / cancelling -> not ready` — `cancelling` 是后台 pipeline 主动取消的非终态，此处保留正确（不是 create-before-submit 分支的路径）。
- 460 行状态流：`cancelling -> cancelled` 仍是后台取消的典型路径，保留正确。

README 从 `CANCELLING` 非终态描述更新为 `cancelled` 终态描述，符合 fix artifact 记录，且符合 README `Agent更新约束【必须遵守】` 的职责边界。

### `tests/README.md` — 已更新

151 行：`download / preprocess 在 durable create 后、executor submit 前观察 cancellation token 并标记 job cancelled 且不提交后台操作` — 使用 `cancelled` 而非 `cancelling`。

## Validation 复核

fix artifact 记录的验证结果：

- `rg` 命令：无匹配（已复核确认）。
- pytest：`48 passed, 3 warnings in 2.01s`（已复核确认：`48 passed, 3 warnings in 1.96s`，warnings 为 edgar deprecation warnings）。
- pyright：`0 errors, 0 warnings, 0 informations`（已复核确认）。

验证结果可信。

## Residual Risks

controller adjudication 中的 S1-R1、S1-R2、S1-R3 均为已知 deferred / accepted limitation / out of scope，不属于本次 re-review 范围，状态不变。

## Conclusion

S1-F1 至 S1-F4 全部已修复。无 blocking 问题。

**Slice 1 可进入 accepted slice commit。**
