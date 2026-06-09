# WU-TOOLS-01-F01-03 Slice 1 Follow-Up Re-Review - MiMo

## Scope

- Mode: current changes
- Branch: phase/wu-tools-01-f01-03
- Base: main
- Review target: CTRL-RR1 follow-up fix
- Timestamp: 20260609-113340

## CTRL-RR1 Re-Review

### 检查项 1：`_save_failed` 是否不再使用旧 record + save_job 直接写 FAILED

**状态：fixed**

**证据：**
- `ingestion_runtime.py:2339-2377`：`_save_failed` 现在调用 `self.job_store.save_failed_or_cancelled_if_active(record.job_id, ...)` 而非基于旧 record 构造 `FAILED` 后调用 `save_job`。
- 旧实现使用 `record` 参数构造终态后直接调用 `save_job`，新实现只取 `record.job_id`，终态决策委托给 job store 的原子方法。

### 检查项 2：是否新增 job-store-level atomic failed-or-cancelled terminalization

**状态：fixed**

**证据：**
- 协议定义：`ingestion_runtime.py:785-810`，`FinsIngestionJobStore` 协议新增 `save_failed_or_cancelled_if_active` 抽象方法。
- 生产实现：`ingestion_runtime.py:1116-1168`，`FsFinsIngestionJobStore.save_failed_or_cancelled_if_active` 实现完整。

### 检查项 3：FsFinsIngestionJobStore 在同一个 file_lock 内读取当前 record 后裁决

**状态：fixed**

**证据：**
- `ingestion_runtime.py:1145`：`with file_lock(self.root_dir / _LOCK_FILE_NAME):` 包裹整个读取-裁决-写入流程。
- 裁决逻辑：
  - `ingestion_runtime.py:1147-1148`：当前已终态则原样返回。
  - `ingestion_runtime.py:1149-1158`：当前 `cancellation_requested=True` 或 `status=CANCELLING` 则写入并返回 `CANCELLED`。
  - `ingestion_runtime.py:1159-1168`：否则写入 `FAILED`。

### 检查项 4：`_save_failed` 是否调用该原子方法

**状态：fixed**

**证据：**
- `ingestion_runtime.py:2372`：`return self.job_store.save_failed_or_cancelled_if_active(record.job_id, failure_summary=failure_summary, result_summary=final_result, finished_at=now)`

### 检查项 5：fake store 是否同步实现同一协议语义

**状态：fixed**

**证据：**
- `tests/fins/test_fins_ingestion_runtime.py:431-476`：`_ClaimRaceJobStore.save_failed_or_cancelled_if_active` 实现了相同的裁决逻辑：
  - 终态原样返回（行 455-456）
  - cancellation_requested 或 CANCELLING 写入 CANCELLED（行 457-466）
  - 否则写入 FAILED（行 467-476）

### 检查项 6：新测试是否使用 production store 证明 stale active record 不能覆盖当前 CANCELLING

**状态：fixed**

**证据：**
- `tests/fins/test_fins_ingestion_runtime.py:1232-1256`：`test_save_failed_uses_current_cancelling_record_instead_of_stale_active_record`
  - 使用 production `FsFinsIngestionJobStore`（通过 `_build_ingestion_runtime` 创建）
  - 先 `request_cancel` 把 store 当前 record 标成 `CANCELLING`（行 1241）
  - 传入 stale active record 调用 `_save_failed`（行 1243-1247）
  - 断言最终状态为 `CANCELLED`，不是 `FAILED`（行 1251-1252）
  - 断言 `result_summary == {}`、`failure_summary == {}`（行 1254-1255），证明 late failure 不覆盖取消时的空摘要

### 补充检查：`_save_failed_from_exception` 测试是否同步更新

**状态：fixed**

**证据：**
- `tests/fins/test_fins_ingestion_runtime.py:1606-1657`：`test_save_failed_from_exception_logs_secondary_job_store_failure` 现在 monkeypatch `save_failed_or_cancelled_if_active` 方法（行 1645-1649），继续覆盖失败收口二次落盘失败的诊断路径。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 本次 re-review 仅覆盖 CTRL-RR1 要求的 atomic failed-or-cancelled terminalization。
- 真实 upload workflow、Host wait adapter、awaiting tool 和物理取消 / revoke 仍不在 Slice 1 scope 内。

## Validation

| 验证项 | 结果 |
|---|---|
| `pytest tests/fins/test_fins_ingestion_runtime.py -q` | 37 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过 |

## Verdict

**fix-accepted**

CTRL-RR1 状态：**fixed**

0 blocking findings。
