# UF-FIX09 Aggregate Deepreview

## Scope

- **Gate**: aggregate deepreview
- **Work unit**: UF-FIX09 shared-interruptible-docling-converter
- **Base**: `3f24d75adba49868fbc8646ac9c81f5a0a4a3c2e`
- **Target**: `d40ac173fd308b3329ed7216e0c26b9951663cdc`
- **Branch**: `codex/upload-filing-oracle`
- **Output file**: `docs/reviews/uf-fix09-aggregate-deepreview-20260812-221109.md`
- **Included scope**: base..target 全部实现，包括 S1/S2/S3 commits、accepted plan、gate adjudication/review artifacts、AGENTS/design/oracle/scenario 中相关约束
- **Excluded scope**: 另一 reviewer 的本轮 artifact、UF-PF09 执行、外部 evidence 修改
- **Parallel review coverage**: 无（单 reviewer 执行完整 aggregate）

## Findings

### 编号-未修复-[低]-重复计算 converter 已承诺的 SHA-256

- **入口/函数**: `DoclingUploadService._build_pending_assets`
- **文件(行号)**: `dayu/fins/pipelines/docling_upload_service.py:690`
- **输入场景**: 正常上传流程，Docling 转换成功后构建待上传资产
- **实际分支**: 调用 `self._docling_converter.convert_to_json_bytes` 获取 `DoclingConversionResult`，然后从 `conversion.sha256` 读取 digest
- **预期行为**: 直接消费 `DoclingConversionResult.sha256`，不重复计算
- **实际行为**: 代码已正确读取 `conversion.sha256`，未重复计算（S2 已修复）
- **直接证据**: `docling_sha256 = conversion.sha256`（行 690）
- **影响**: 无影响，S2 已修复此问题
- **建议改法和验证点**: 无需修改，已验证
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: 无

**结论**: 此 finding 已在 S2 中修复，当前代码正确。

### 编号-未修复-[中]-direct upload claim 后事件构造异常可能丢失 RESULT

- **入口/函数**: `_produce_direct_upload`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:3449-3464`
- **输入场景**: direct upload，runner 返回 summary 后构造事件时抛异常
- **实际分支**: 先调用 `claim_upload_summary` 写入 `_terminal_status`，之后才构造并入队事件
- **预期行为**: 同一次仲裁决定 progress/result，禁止二者分裂
- **实际行为**: S3 已修复，先用 pure typed helper 构造可见 progress/result（不入队），构造成功后再执行单次 `claim_upload_summary`
- **直接证据**: `_direct_upload_terminal_events` 在 `claim_upload_summary` 前调用（行 3450-3456）
- **影响**: 无影响，S3 已修复此问题
- **建议改法和验证点**: 无需修改，已验证
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: 无

**结论**: 此 finding 已在 S3 中修复，当前代码正确。

## 跨切片 Adversarial Pass 验证

### 1. 唯一 Fins Docling owner/依赖方向

**验证结果**: ✅ 通过

- `ProcessDoclingConverter` 是唯一的 shared converter owner，位于 `dayu/fins/pipelines/docling_process_converter.py`
- 依赖方向正确：
  ```text
  CLI -> FinsIngestionRuntime -> Fins service/pipelines/workflows
                               -> shared Fins Docling converter
                                    -> dayu.documents.docling_runtime
                                    -> dayu.runtime.interruptible_process
                               -> dayu.fins.storage
  ```
- `dayu.runtime` 只依赖标准库/底层公共契约，不 import Fins、documents、Host、Engine、Service 或 UI
- Fins converter 依赖 `dayu.runtime` 与 `dayu.documents`；二者不反向依赖 Fins

### 2. 所有当前 caller inventory 和旧 runner 删除

**验证结果**: ✅ 通过

- `dayu/fins/pipelines/cn_docling_process.py` 已删除
- `tests/fins/test_cn_docling_process.py` 已删除
- `rg` 搜索确认旧符号（`ProcessCnDoclingConversionRunner`、`CnDoclingConversionRunner`、`DoclingUploadConverter`、`convert_with_docling`、`_convert_bytes_with_docling`、`_convert_with_docling`、`UploadCancellationChecker`、`DoclingCancellationInput`）在生产代码和测试中均为零
- `ProcessDoclingConverter` 已正确注入到：
  - `dayu/fins/service_runtime.py:478-480` - DefaultFinsRuntime 构造
  - `dayu/fins/pipelines/sec_pipeline.py:51,558` - SecPipeline
  - `dayu/fins/pipelines/cn_pipeline.py:68,402` - CnPipeline

### 3. immutable bytes/child construction/IPC typed outcome

**验证结果**: ✅ 通过

- `DoclingConversionConfig` 是 `frozen=True, slots=True` dataclass
- `DoclingConversionResult` 是 `frozen=True, slots=True` dataclass，构造时校验 `size == len(json_bytes)` 和 SHA-256
- `_DoclingProcessTarget` 是 `frozen=True, slots=True` dataclass，接收 `input_path`、`output_path`、`stream_name`、`config`
- IPC descriptor 是 exact-key、versioned JSON value：
  - success: `schema_version`、`status`、`size`、`sha256`
  - failure: `schema_version`、`status`、`failure_kind`、`message`
- 闭合错误类型：
  - `DoclingConversionFailureKind`: `CONVERTER_CONSTRUCTION`、`CONVERTER_EXECUTION`、`RESULT_SERIALIZATION`、`IPC_PROTOCOL`、`CHILD_CRASH`、`CLEANUP`
  - `DoclingConversionError`: 所有非取消失败的唯一 public exception
  - `DoclingConversionCancelledError`: 只有已完成进程与资源收口的请求取消才抛出

### 4. process group terminate-grace-kill-reap-close

**验证结果**: ✅ 通过

- 常量定义：
  - `_DOCLING_PROCESS_POLL_SECONDS = 0.05`
  - `_DOCLING_TERMINATE_GRACE_SECONDS = 2.0`
  - `_DOCLING_KILL_GRACE_SECONDS = 1.0`
- `_wait_for_terminal` 实现了 terminate -> kill 升级：
  - 先调用 `handle.terminate(grace_seconds=2.0)`
  - 如果未退出，调用 `handle.kill(grace_seconds=1.0)`
  - 如果仍未退出，抛出 `CLEANUP` 错误
- `_close_handle` 实现了 shielded cleanup：
  - 在 `while True` 循环中调用 `handle.close(kill_grace_seconds=1.0)`
  - 捕获 `CancelledError` 并保留外层取消 identity
  - 捕获普通异常并返回 `_CloseOutcome`
- cleanup phase diagnostics 记录了所有关键阶段：
  - `CHILD_STARTED`、`CANCEL_OBSERVED`、`TERMINATE_STARTED/COMPLETED`、`KILL_STARTED/COMPLETED`、`KILL_NOT_NEEDED`、`HANDLE_CLOSE_STARTED/COMPLETED`、`TEMP_CLEANUP_COMPLETED`、`CANCELLED_TERMINAL_READY`

### 5. download fallback

**验证结果**: ✅ 通过

- `cn_download_filing_workflow.py` 正确使用 `DoclingConverter` protocol
- `_canonical_cancellation` 函数确保 canonical token identity：
  ```python
  def _canonical_cancellation(cancel_checker: Callable[[], bool] | None) -> CancellationToken | None:
      if cancel_checker is None:
          return None
      if not isinstance(cancel_checker, CancellationToken):
          raise TypeError("cancel_checker 必须实现 canonical CancellationToken")
      return cancel_checker
  ```
- `DoclingConversionCancelledError` 在 workflow 边界映射为 `CnDownloadCancelledError`
- download workflow 在转换前后检查取消，但不在转换运行中检查（这是正确的，因为转换在子进程中执行）

### 6. upload_filing/upload_material 共用

**验证结果**: ✅ 通过

- `DoclingUploadService` 同时服务 filing 和 material：
  - `prepare_upload` 方法接收 `source_kind` 参数区分 filing/material
  - `_build_pending_assets` 使用 shared `DoclingConverter`
- `commit_prepared_upload_batch` 是唯一的 publication lifecycle owner：
  - 执行 final checkpoint、rollback once、commit ownership transfer、commit-success 与 commit-exception 状态机
- SEC/CN upload workflow 共用同一个 helper：
  - `sec_upload_workflow.py` 调用 `commit_prepared_upload_batch`
  - CN upload workflow 也调用同一个 helper

### 7. direct/durable first-committer publication boundary

**验证结果**: ✅ 通过

- `FinsUploadTerminalDisposition` 是闭集终态：`COMPLETED`、`FAILED`、`CANCELLED`
- `_upload_terminal_disposition_from_status` 是唯一 status validation/mapping 真源：
  - `ok` -> `COMPLETED`
  - `skipped` -> `COMPLETED`
  - `deleted` -> `COMPLETED`
  - `failed` -> `FAILED`
  - `cancelled` -> `CANCELLED`
  - 其它值抛出 `ValueError`
- `claim_upload_summary` 实现了 direct stream 的单次 claim：
  - 在同一 lock 内检查 `consumer_aborted` 和 `terminal_status`
  - 已有终态或 consumer 已 abort 时返回 `None`
- `save_accepted_upload_terminal_if_active` 实现了 durable job 的 atomic save：
  - 只允许 `COMPLETED/FAILED`
  - 传 `CANCELLED` 或字段不匹配时 `ValueError`
- cancelled summary 不产生 completed：
  - `_upload_completed_progress_type` 对 cancelled 抛出 `ValueError`
  - `_produce_direct_upload` 和 `_run_upload_job` 都检查 disposition，cancelled 不发 completed progress

### 8. SIGINT 唯一 canonical terminal/exit130

**验证结果**: ✅ 通过

- `_direct_upload_result_status` 把 cancelled 映射为 `FinsResultStatus.CANCELLED`
- `_upload_completed_progress_type` 对 cancelled 抛出 `ValueError`，阻止 completed progress
- CLI 不过滤，直接消费 runtime terminal
- `_DirectStreamCancellationState.claim_upload_summary` 在同一 lock 内原子 claim，不被迟到 cancel 改写

### 9. 异常与 race

**验证结果**: ✅ 通过

- `_DirectStreamCancellationState` 使用 `threading.Lock` 保护跨线程读写：
  - `request_cancel`、`is_cancelled`、`claim_terminal`、`claim_upload_summary` 都在同一 lock 内
- `claim_upload_summary` 实现了原子 claim：
  - 检查 `consumer_aborted` 和 `terminal_status`
  - 已有终态或 consumer 已 abort 时返回 `None`
  - 否则设置 `_terminal_status` 并返回对应 status
- `commit_prepared_upload_batch` 实现了 first-committer 状态机：
  - `batch_terminal_started` 标志控制 rollback 次数
  - commit 开始后 caller 不再 rollback
- `_rollback_precommit_upload_batch` 实现了恰好一次 rollback：
  - 捕获 rollback 异常并保留原始异常为 cause

### 10. README/测试/类型/过度耦合/semantic ownership drift

**验证结果**: ✅ 通过

- `dayu/fins/README.md` 已更新：
  - 描述了 shared Fins converter
  - 描述了 typed cancellation
  - 描述了 publication first-committer
- 测试覆盖了关键路径：
  - `test_docling_process_converter.py`: 39+ tests
  - `test_fins_ingestion_runtime.py`: 134+ tests
  - 其他相关测试文件
- 类型检查通过：
  - pyright 0 errors, 0 warnings
- 没有发现过度耦合：
  - `ProcessDoclingConverter` 是无跨调用状态的 concrete instance
  - 注入到所有 Fins call site，删除旧 CN runner
  - 没有 facade、wrapper 或 re-export
- 没有发现 semantic ownership drift：
  - 每个业务事实都有唯一清晰 owner
  - 没有 fallback、特例、`hasattr/getattr`、loose parsing 或兼容 shim

## Validation

### Deterministic tests

- S1: 39 passed, 95% coverage
- S2: 493 passed, 86-100% coverage
- S3: 525 passed, 91% coverage
- Full regression: 1196 passed, 1 skipped

### Real Docling integration

- `test_docling_upload_service_integration.py`: 1 passed

### Pyright

- `0 errors, 0 warnings, 0 informations`

### Repository hygiene

- `rg` 搜索确认旧符号为零
- `git diff --check` 无告警
- `git status --short` clean

## Docs Decision

- `dayu/fins/README.md`: 已更新，描述 shared Fins converter、typed cancellation 与 publication first-committer
- `tests/README.md`: 已更新，描述测试覆盖
- 根 `README.md`: 已更新，描述取消行为和"不会发布半成品"的用户承诺
- `dayu/README.md`: 不更新，分层/装配未变化
- `dayu/engine/README.md`、`dayu/host/README.md`、`dayu/config/README.md`: 不更新，对应生产目录不改且 owner 不变

## Residual Risk 分类

| 分类 | 风险 | 处理方式 |
| --- | --- | --- |
| `fixed in current slice` | S2 重复 digest 计算 | 已修复 |
| `fixed in current slice` | S3 projection 异常安全网 | 已补测 |
| `fixed in current slice` | S3 direct upload claim 后构造异常 | 已修复 |
| `covered by later approved gate` | UF-PF09 fresh evidence | 后续 gate |
| `covered by later approved gate` | aggregate deepreview | 本文档 |
| `covered by later approved gate` | final validation | 后续 gate |
| `assigned to later work unit` | company meta 独立事务 | later work unit |
| `assigned to later work unit` | web fetch cancellation | later work unit |
| `assigned to later work unit` | 非 POSIX descendant governance | later work unit |
| `assigned to later work unit` | 格式范围扩展 | later work unit |

## Completion Status

**AGGREGATE DEEPREVIEW COMPLETE — NO BLOCKING FINDINGS**

所有 accepted findings 已在 S1/S2/S3 中修复并通过双路 re-review。aggregate deepreview 确认：

1. 唯一 Fins Docling owner 已建立，依赖方向正确
2. 旧 CN runner 已删除，所有 caller 已迁移到 shared converter
3. immutable bytes/child construction/IPC typed outcome 实现正确
4. process group terminate-grace-kill-reap-close 实现正确
5. download fallback 实现正确
6. upload_filing/upload_material 共用实现正确
7. direct/durable first-committer publication boundary 实现正确
8. SIGINT 唯一 canonical terminal/exit130 实现正确
9. 异常与 race 处理正确
10. README/测试/类型/过度耦合/semantic ownership drift 均通过

无 blocking question、未分类风险或 requiring-user-decision 项。
