# WU-TOOLS-01-F01 Slice S3 Fix Artifact

## 范围

- Gate: fix。
- Slice: S3 - Download Runtime Pipeline。
- 只修复 controller adjudication 接受的两个 finding：`F01-S3-001`、`F01-S3-002`。
- 未处理被拒绝的 MiMo private `_StoreFileLock` import finding。
- 未修改 Host / Engine / Service / tool provider、真实网络 downloader、CLI 或 control doc。
- 未执行 re-review、commit、push、PR 或后续 slice。

## 第一性原理判断

两个 accepted finding 动机成立。Fins ingestion job 是 durable governance state，Host 后续 wait/cancel 语义依赖终态可信；因此后台 runner 不能在取消请求已经进入 job store 后再把同一 job 覆盖为 `SUCCEEDED`。同理，`_mark_job_running_or_cancelled` 已经把 terminal record 作为合法返回值建模，调用方只识别 `CANCELLED` 会让 `SUCCEEDED` / `FAILED` 重新进入业务执行路径，破坏状态机闭包。

## 修复内容

### F01-S3-001

修复方式：

- 在 `FinsIngestionJobStore` 协议与 `FsFinsIngestionJobStore` 实现中新增 `save_succeeded_or_cancelled(...)`。
- 文件系统实现持有同一把 store lock 后读取当前 job record，并在该锁内完成终态裁决：
  - 当前已是终态：原样返回，不覆盖。
  - 当前存在 `cancellation_requested=True` 或状态为 `CANCELLING`：写入 `CANCELLED`。
  - 否则写入 `SUCCEEDED`。
- `_save_succeeded(...)` 改为调用上述共享终态裁决方法，download 与 preprocess 共用同一行为。

测试覆盖：

- 新增 `test_start_download_cancel_immediately_before_success_terminalization_writes_cancelled`，在 success terminalization 前插入 `request_cancel(...)`，证明最终状态为 `CANCELLED`，不会被覆盖成 `SUCCEEDED`。

### F01-S3-002

修复方式：

- `_run_download_job(...)` 与 `_run_preprocess_job(...)` 在 `_mark_job_running_or_cancelled(...)` 返回后，统一对任意 `_TERMINAL_STATUSES` 立即返回。
- 这样 `SUCCEEDED`、`FAILED`、`CANCELLED` 都不会再次进入 download/preprocess 业务执行路径。

测试覆盖：

- 新增 `test_runners_return_for_preterminalized_jobs_without_executing`：
  - download job 被预先写成 `SUCCEEDED` 后，fake adapter 未被调用。
  - preprocess job 被预先写成 `SUCCEEDED` 后，预处理执行函数未被调用。

## 验证结果

已运行：

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py
```

结果：37 passed，3 个 edgar 依赖 deprecation warnings。

已运行：

```bash
source .venv/bin/activate && pyright
```

结果：0 errors，0 warnings，0 informations。pyright 额外提示有新版本可用，不影响本次验证。

## README 同步判断

未更新 README。

原因：本次修复只改变 Fins ingestion runtime 内部 job 状态机的并发终态裁决与 runner 早退条件，没有改变用户命令、配置入口、稳定开发入口、adapter 业务契约或测试维护说明。当前 README 中没有需要同步的稳定说明。

## 剩余风险

- 取消发生在业务写入 source/blob/rejected artifact 之后、success terminalization 之前时，job 终态会正确记录为 `CANCELLED`，但本修复不回滚已经完成的仓储业务写入；这是当前 ingestion runtime 既有非事务性边界。
- 对 `FAILED` 终态写入与取消请求之间的竞态未扩展处理；本次 controller 只接受 success terminalization 覆盖 cancellation 与 terminal runner 重入两项 finding。
