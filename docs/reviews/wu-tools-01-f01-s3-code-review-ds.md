# Code Review — WU-TOOLS-01-F01 Slice S3

## Verdict

**pass-with-findings**

## Scope

- **Mode**: current changes
- **Branch**: host-wu-tools-01-f01
- **Base**: main (ffea26b8 是 S2 accepted commit，本 review 覆盖 Slice S3 相对于 main 的未合并改动)
- **Output file**: docs/reviews/wu-tools-01-f01-s3-code-review-ds.md
- **Included scope**:
  - `dayu/fins/ingestion_runtime.py` — download runtime pipeline（`start_download`、adapter protocol、storage write、terminalization）
  - `dayu/fins/service_runtime.py` — DefaultFinsRuntime 装配 ingestion runtime
  - `tests/fins/test_fins_ingestion_runtime.py` — download runtime 测试
  - `dayu/fins/README.md` — ingestion 状态同步
  - `tests/README.md` — ingestion runtime 测试覆盖说明同步
- **Excluded scope**:
  - `docs/host/issues-implementation-control.md` — 仅作为 controller bookkeeping 背景，不做实现 bug 检查
  - plan doc、design doc、prior review artifacts — 作为 design truth 源引用，不 review 其内容
- **Parallel review coverage**: 无。全部由主 reviewer 逐行走读。

## Validation Notes

已运行：

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q
# 结果：24 passed, 3 warnings（edgar deprecation，与 S3 无关）

source .venv/bin/activate && python -m pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py tests/fins/test_fins_ingestion_runtime.py
# 结果：0 errors, 0 warnings, 0 informations
```

手动逐行走读了 `ingestion_runtime.py`（2550 行）、`service_runtime.py`、测试文件（1065 行）、storage protocols、ticker_normalization 与 document_models 的相关部分。

## Findings

### 1-pass-with-findings-[中]-终态写入与取消检查之间存在 TOCTOU，可静默覆盖并发取消请求

- **入口/函数**: `FinsIngestionRuntime._run_download_job`、`FinsIngestionRuntime._run_preprocess_job` → `_save_succeeded`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1106-1117`（download）、`:1058-1076`（preprocess）
- **输入场景**: 下载或预处理后台 job 在执行完所有文档处理后、写入 SUCCEEDED 终态前，另一个线程（或同一进程的其他控制路径）通过 `request_cancel` 发出取消请求。
- **实际分支**: `_execute_download_request` / `_execute_preprocess_request` 内部的 per-item 取消检查循环已结束（最后一次 `read_job` 确认未取消），不再做取消检查。外层 `_run_*_job` 在 `_execute_*_request` 返回后再次 `read_job`（行 1106 / 1058）做最后一次取消判断，但随后调用 `_save_succeeded` 时（行 1117 / 1076），lock 仅包裹 `save_job` 内部的读写，不覆盖外层的"判断是否应进入成功"与"执行成功写入"之间的间隙。
- **预期行为**: 如果 job 已被标记取消，不应以 SUCCEEDED 覆盖。
- **实际行为**: 若取消请求恰好在 `read_job`（确认未取消）之后、`_save_succeeded` 获取锁之前到达，`_save_succeeded` 会以 `SUCCEEDED` + `cancellation_requested=False` 覆盖 `CANCELLING` 状态，使取消请求静默丢失。
- **直接证据**:
  - `ingestion_runtime.py:1106` — `latest = self.job_store.read_job(job_id)` 不持有锁
  - `ingestion_runtime.py:1107-1109` — 取消检查基于上述无锁读取
  - `ingestion_runtime.py:1117` — `self._save_succeeded(latest, ...)` 调用 `save_job`，锁仅在其内部获取（`FsFinsIngestionJobStore.save_job:678`），不再重复检查取消状态
  - `ingestion_runtime.py:1651-1681` — `_save_succeeded` 无条件写入 `SUCCEEDED` + `cancellation_requested=False`，不检查传入 record 的当前状态
- **影响**: 取消请求被静默忽略；外部调用方看到 SUCCEEDED 而非 CANCELLED。在实际部署中，如果 Host wait adapter 轮询 job 状态，会错误地认为 job 已完成，触发错误的 resume 路径。
- **建议改法和验证点**:
  1. 将取消检查合并到 `_save_succeeded` / `_save_failed` 内部：在获取 job store lock 后重新读取 record 并检查 `cancellation_requested`，若已标记取消则转为 cancelled。
  2. 或者在 `_run_*_job` 中把 `read_job` + 状态判断 + `save_job` 包装成一个原子操作（例如在 job store 增加 `save_if_not_cancelled` 语义方法）。
  3. 验证：构造时序测试——在 `_save_succeeded` 执行前注入取消请求，断言终态为 CANCELLED。
- **修复风险（低）**: 只需在 `_save_succeeded` 开头增加一次 `read_job` + 取消检查，或增加 `save_if_not_cancelling` 方法。不改变公开 API。
- **严重程度（中）**: 真实 TOCTOU race，虽窗口窄，但后果是取消被静默吞掉。download 和 preprocess 两条路径同受影响。

### 2-pass-with-findings-[中]-_mark_job_running_or_cancelled 返回终态 SUCCEEDED/FAILED 时未兜底，调用方会继续执行

- **入口/函数**: `FinsIngestionRuntime._run_download_job`、`FinsIngestionRuntime._run_preprocess_job`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1102-1105`（download）、`:1054-1056`（preprocess）、`:1138-1151`（`_mark_job_running_or_cancelled`）
- **输入场景**: `_mark_job_running_or_cancelled` 读到 job 已处于 `SUCCEEDED` 或 `FAILED` 终态（例如因外部直接操作 job store、或 future code path 在 `_create_queued_job` 与 executor dispatch 之间引入了其他状态变更）。
- **实际分支**: `_mark_job_running_or_cancelled:1141-1142` — `if record.status in _TERMINAL_STATUSES: return record`，返回终态 record 但不改变它。调用方 `_run_download_job:1103` / `_run_preprocess_job:1055` 仅检查 `record.status is FinsIngestionJobStatus.CANCELLED`，对 `SUCCEEDED` 或 `FAILED` record 不返回，继续进入 `_execute_download_request` / `_execute_preprocess_request`，会重复写入 storage。
- **预期行为**: 已终态的 job 不应重新执行。
- **实际行为**: SUCCEEDED 或 FAILED 的 job 会被再次推进执行，可能导致重复下载、重复写入 source/blob/processed 仓储。
- **直接证据**:
  - `ingestion_runtime.py:1141` — `if record.status in _TERMINAL_STATUSES: return record`
  - `ingestion_runtime.py:1103` — `if record.status is FinsIngestionJobStatus.CANCELLED: return` 仅捕获 CANCELLED，不捕获 SUCCEEDED / FAILED
  - `ingestion_runtime.py:1055` — preprocess 路径相同缺陷
- **影响**: 当前通过公开 API 不可达（`_create_queued_job` 创建 QUEUED，`request_cancel` 只能转到 CANCELLING）。但防御模式不完整：如果 future 代码或异常路径引入了其他终态转换，会导致数据重复。属于 maintainability / future regression risk。
- **建议改法和验证点**:
  1. 将检查条件改为 `if record.status in _TERMINAL_STATUSES: return`，覆盖全部三种终态。
  2. 或改用 `if record.status is not FinsIngestionJobStatus.RUNNING: return`。
  3. 验证：构造一个已处于 SUCCEEDED 终态的 job，调用 `_run_download_job`，断言立即返回且未执行任何 storage 写入。
- **修复风险（低）**: 将 `is CANCELLED` 改为 `in _TERMINAL_STATUSES`，一行改动，语义更严格。不影响当前可达路径。
- **严重程度（中）**: 当前不可达但防御不完整，是未来回归的脆弱点。

## Open Questions

- 无。

## Residual Risk

- **S3 non-goal 范围内的 adapter 延迟取消**: 当前 `adapter.download(adapter_request)` 是同步调用。如果真实 SEC/CN/HK adapter 下载耗时数分钟，job 在 adapter 执行期间无法响应取消（per-item 取消检查只在 adapter 返回后生效）。这是 S3 明确 non-goal（无真实网络 adapter），但真实 adapter owner 需要注意这一设计约束。
- **adapter 响应大小无上限**: `_execute_download_request` 不加限制地迭代 adapter 返回的全部 documents 和 rejected_artifacts。当真实 adapter 返回大量文档时，job 可能长时间占用线程且 job record status 始终为 RUNNING。当前无真实 adapter 因此无实际风险。
- **test 中 `_wait_terminal` 的 5s 超时**: `tests/fins/test_fins_ingestion_runtime.py:938` 使用 `time.monotonic() + 5.0` 做轮询等待。在极端慢的 CI 环境下可能不稳定（flaky），但当前测试使用 daemon thread executor 且无真实 I/O，5s 足够。
- **`DocumentMeta = dict[str, Any]`**: `dayu/fins/domain/document_models.py:23` 定义 `DocumentMeta` 包含 `Any`。`ingestion_runtime.py` 的 `_download_document_meta`、`_optional_text_from_meta`、`_build_processed_meta` 等函数消费/返回此类型。这是 pre-existing 类型弱点，非 S3 引入；S3 代码对 `meta.get()` 返回值做了显式 `str()` 转换，未扩散弱类型。
