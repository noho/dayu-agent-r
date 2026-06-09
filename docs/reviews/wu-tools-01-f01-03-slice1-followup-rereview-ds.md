# WU-TOOLS-01-F01-03 Slice 1 Follow-Up Fix — DeepReview Re-Review (CTRL-RR1)

## Scope

- **Mode**: current changes (follow-up fix re-review)
- **Branch**: `phase/wu-tools-01-f01-03`
- **Artifact**: `docs/reviews/wu-tools-01-f01-03-slice1-followup-rereview-ds.md`
- **Reviewed scope**: 仅 CTRL-RR1 — `_save_failed` atomic current-state terminalization
- **Excluded scope**: 真实 upload workflow、Host wait adapter、awaiting tool、SEC/CN/HK 迁移、OLD downloader/pipeline
- **Validation**: pytest 37 passed; pyright 0 errors; git diff --check 通过

## Verdict

**pass** — CTRL-RR1: **fixed** — 0 blocking findings.

## CTRL-RR1 Checklist Verification

逐条沿代码路径走读验证：

### 1. `_save_failed` 不再使用旧 record + save_job 直接写 FAILED

**验证结果**: fixed.

`ingestion_runtime.py:2372` — `_save_failed` 现在调用 `self.job_store.save_failed_or_cancelled_if_active(record.job_id, failure_summary=..., result_summary=..., finished_at=...)`。`record` 参数仅用于传入 `record.job_id`，不再用于构造 FAILED record 后调用 `save_job`。

全文件 `save_job(` 调用搜索结果为空 — 运行时中再无通过 `save_job` 写入终态 record 的路径。

### 2. 新增 job-store-level atomic failed-or-cancelled terminalization

**验证结果**: fixed.

- **协议**: `FinsIngestionJobStore` Protocol 新增 `save_failed_or_cancelled_if_active` (`ingestion_runtime.py:785-810`)，文档完整覆盖参数、返回值与异常语义。

- **生产实现**: `FsFinsIngestionJobStore.save_failed_or_cancelled_if_active` (`ingestion_runtime.py:1116-1168`):
  - 入口先 `_assert_bounded_summary` 校验 `failure_summary` 和 `result_summary`。
  - 在同一个 `file_lock` 内 `_read_record_locked(job_id)` 读取当前 record。
  - 当前已是终态 (`_TERMINAL_STATUSES`): 原样返回。
  - 当前 `cancellation_requested=True` 或 `status=CANCELLING`: 写入并返回 `CANCELLED`，同时设置 `cancellation_requested=True`，**不**带入 `failure_summary` 或 `result_summary`。
  - 否则: 写入 `FAILED`，带入已校验的 `failure_summary` 和 `result_summary`。

裁决逻辑与 `save_cancelled_if_active` 和 `save_succeeded_or_cancelled` 一致，不 collapsing semantics。

### 3. `_save_failed` 调用该原子方法

**验证结果**: fixed.

- `_save_failed` (`ingestion_runtime.py:2372`): 调用 `self.job_store.save_failed_or_cancelled_if_active(...)`.
- `_save_download_unsupported` (`ingestion_runtime.py:2397`): 调用 `self._save_failed(record, ...)`，间接走原子路径。外层的 `read_job` + 终态检查是前置优化，不损正确性 — `save_failed_or_cancelled_if_active` 在锁内重新读取当前状态合规裁决。
- `_save_failed_from_exception` (`ingestion_runtime.py:2430`): 同模式，通过 `_save_failed` 走原子路径。

### 4. Fake store 同步实现同一协议语义

**验证结果**: fixed.

`_ClaimRaceJobStore.save_failed_or_cancelled_if_active` (`test_fins_ingestion_runtime.py:431-476`):

- 读取当前 record (`_require_record`)。
- 终态检查 → 原样返回。
- `cancellation_requested` 或 `CANCELLING` → 写入并返回 `CANCELLED`（不保存 failure/result summary）。
- 否则 → 写入并返回 `FAILED`（带入 failure_summary 和 result_summary）。

协议语义与 `FsFinsIngestionJobStore` 一致。fake store 不使用文件锁（内存操作无需文件锁），属于合理简化。

### 5. 新测试使用 production store 证明 stale active record 不能覆盖当前 CANCELLING

**验证结果**: fixed.

`test_save_failed_uses_current_cancelling_record_instead_of_stale_active_record` (`test_fins_ingestion_runtime.py:1232-1256`):

- 使用 `_build_ingestion_runtime(workspace_root, executor=executor)` 构建，底层使用 production `FsFinsIngestionJobStore`。
- 流程：`start_preprocess` → `request_cancel(job_id)` 写入 CANCELLING → 用 stale active record 调用 `_save_failed(start.record, message="late failure", result_summary={"processed_count": 1})`。
- 断言验证:
  - `cancelling.status is CANCELLING` — 取消已写入。
  - `saved.status is CANCELLED` — 返回 CANCELLED，不是 FAILED。
  - `reloaded.status is CANCELLED` — store 持久化为 CANCELLED。
  - `reloaded.cancellation_requested` — 取消标记保持。
  - `reloaded.result_summary == {}` — late failure 未覆盖。
  - `reloaded.failure_summary == {}` — late failure 未覆盖。
  - `reloaded.finished_at is not None` — 终态时间已落盘。

已有测试 `test_save_cancelled_does_not_overwrite_current_terminal_record` 继续通过，`save_cancelled_if_active` 未被修改。

`test_save_failed_from_exception_logs_secondary_job_store_failure` 已正确更新为 monkeypatch `save_failed_or_cancelled_if_active` 而非旧的 `save_job`，继续覆盖二次落盘失败诊断路径。

## Open Questions

无。

## Residual Risk

- `_save_failed` 仍接受 caller-provided `record` 参数（仅用于 `record.job_id`）。签名与 `_save_cancelled` 对称，若未来调用方误用 `record` 中其他字段需注意。当前所有调用方仅使用 `record.job_id`，且 `record` 参数有助于调用方显式传递当前观察到的 record 作为上下文，暂不构成 finding。
- 真实 upload workflow、Host wait adapter、awaiting tool 的取消传播与状态收口仍在 Slice 1 scope 外。
