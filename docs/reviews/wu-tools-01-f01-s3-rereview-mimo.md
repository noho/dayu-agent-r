# WU-TOOLS-01-F01 Slice S3 Re-Review

## Gate Metadata

- Gate: re-review (fix verification)。
- Work unit: `WU-TOOLS-01-F01`。
- Slice: `S3 - Download Runtime Pipeline`。
- Branch: `host-wu-tools-01-f01`。
- Inputs:
  - `docs/reviews/wu-tools-01-f01-s3-fix-codex.md`
  - `docs/reviews/wu-tools-01-f01-s3-code-review-controller-adjudication.md`
  - `dayu/fins/ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`

## Verdict

**pass**

## Accepted Finding Status

### F01-S3-001 - fixed

- 问题：`_run_download_job` 和 `_run_preprocess_job` 在 `_execute_*_request` 返回后先 `read_job` 检查取消，再调用 `_save_succeeded`；两次操作不在同一锁内，cancel 请求可在间隙到达并被 SUCCEEDED 覆盖。
- 修复方式：
  - 在 `FinsIngestionJobStore` 协议（行 522-544）与 `FsFinsIngestionJobStore` 实现（行 709-756）中新增 `save_succeeded_or_cancelled(...)`。
  - 实现持有 `_StoreFileLock` 后先 `_read_record_locked`，在同一锁内裁决：已是终态则原样返回；`cancellation_requested=True` 或 `status is CANCELLING` 则写入 `CANCELLED`；否则写入 `SUCCEEDED`。
  - `_save_succeeded`（行 1724-1749）改为委托 `save_succeeded_or_cancelled`，download 和 preprocess 共用同一终态裁决。
- 代码证据：
  - `ingestion_runtime.py:709-756` — `save_succeeded_or_cancelled` 实现，锁内读取 + 裁决 + 写入。
  - `ingestion_runtime.py:1745` — `_save_succeeded` 委托 `save_succeeded_or_cancelled`。
  - `ingestion_runtime.py:1149`（preprocess）、`ingestion_runtime.py:1190`（download）— 两者均通过 `_save_succeeded` 进入原子终态裁决。
- 测试证据：
  - `test_start_download_cancel_immediately_before_success_terminalization_writes_cancelled`（行 654-712）：monkeypatch `save_succeeded_or_cancelled` 在真实裁决前插入 `request_cancel`，断言终态为 `CANCELLED` 且 `result_summary == {}`。

### F01-S3-002 - fixed

- 问题：`_mark_job_running_or_cancelled` 返回任意 `_TERMINAL_STATUSES` 记录时，调用方仅对 `CANCELLED` 做早退，`SUCCEEDED` / `FAILED` 记录会重新进入业务执行路径。
- 修复方式：
  - `_run_download_job`（行 1176）和 `_run_preprocess_job`（行 1128）在 `_mark_job_running_or_cancelled` 返回后，统一对 `record.status in _TERMINAL_STATUSES` 立即 `return`。
- 代码证据：
  - `ingestion_runtime.py:1128-1129` — preprocess runner 对任意终态早退。
  - `ingestion_runtime.py:1176-1177` — download runner 对任意终态早退。
- 测试证据：
  - `test_runners_return_for_preterminalized_jobs_without_executing`（行 714-786）：将 download 和 preprocess job 预先写为 `SUCCEEDED`，断言 `download_adapter.requests == []`（adapter 未被调用）和 `preprocess_execute_calls == 0`（预处理未执行）。

## New Findings

none。

复核范围仅限两个 accepted finding 的修复是否完成且未引入新的 correctness/stability 问题。修复实现干净：`save_succeeded_or_cancelled` 协议与实现签名一致，锁内裁决逻辑完整覆盖三种分支（已终态 / 取消中 / 正常成功），runner 早退条件统一覆盖完整 `_TERMINAL_STATUSES`。测试对 TOCTOU 竞态和 pre-terminalized 重入均做了 focused 覆盖。

## Validation Notes

已运行：

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -v
# 结果：26 passed，3 个 edgar 依赖 deprecation warnings。
```

```bash
source .venv/bin/activate && pyright
# 结果：0 errors，0 warnings，0 informations。
pyright 额外提示有新版本可用（v1.1.409 -> v1.1.410），不影响本次验证。
```

## Blocking Open Questions

none。
