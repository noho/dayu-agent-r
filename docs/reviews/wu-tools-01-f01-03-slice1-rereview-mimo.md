# WU-TOOLS-01-F01-03 Slice 1 Re-Review

## Metadata

- Work unit: `WU-TOOLS-01-F01-03`
- Gate: Slice 1 fix re-review
- Branch: `phase/wu-tools-01-f01-03`
- Timestamp: 2026-06-09T11:22:00+08:00
- Reviewer: MiMo
- Controller pre-verification: 36 passed, pyright 0 errors, git diff --check passed

## Scope

- Re-review 目的：复核 Controller 已接受的 4 个 findings 是否修复。
- 审查文件：
  - `dayu/fins/ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `docs/reviews/wu-tools-01-f01-03-slice1-fix-codex.md`
- 只读参考：
  - `docs/reviews/wu-tools-01-f01-03-slice1-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-03-slice1-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-slice1-code-review-ds.md`
  - `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`

## Accepted Finding Status

### MIMO-S1: 模块 docstring — fixed

- **要求**: 更新模块 docstring，明确承载 download / preprocess / upload job foundation，仍明确不实现真实网络下载、真实 upload workflow、Host wait adapter、tool provider 或 CLI。
- **证据**: `ingestion_runtime.py:1-7` 模块 docstring 已改为：
  > "Fins 下载、预处理与上传运行时基础能力。本模块只承载 Fins 自有 ingestion job 的 typed 请求、结果摘要、持久化 job record、文件系统 job store、download / preprocess / upload job foundation 与运行时入口。它不实现真实网络下载、真实 upload workflow、Host wait adapter、tool provider 或 CLI。"
- **判断**: 正确覆盖 upload 能力描述，同时保留五个排除项。与 Controller 要求一致。

### MIMO-S2: FinsIngestionJobRecord docstring — fixed

- **要求**: `operation_kind` 描述更新为"下载、预处理或上传"，并核对 `source` / `source_kind` 描述是否包含 upload shape。
- **证据**: `ingestion_runtime.py:654-659`:
  - `operation_kind: 下载、预处理或上传。`
  - `source: 下载来源标识；预处理与上传任务为 ``None``。`
  - `source_kind: 源文档类型；预处理与上传任务用于区分 filing/material，下载任务为 ``None``。`
- **判断**: `operation_kind`、`source`、`source_kind` 三处 docstring 均已补齐 upload 语义，与当前代码中 upload record 的 `source=None`、`source_kind` 非空约束一致。

### DS-S1: _save_cancelled active-only atomic cancelled terminal — fixed

- **要求**: `_save_cancelled` 改为 active-only atomic cancelled terminal 语义，不能覆盖当前已终态 record；保留 start-boundary create-after-cancel 强制写 CANCELLED 的行为；测试直接覆盖已终态不被旧 active record 覆盖。
- **生产代码证据**:
  - `_save_cancelled` (`ingestion_runtime.py:2242-2256`) 改为调用 `self.job_store.save_cancelled_if_active(record.job_id, finished_at=now)`，不再直接调用 `save_job`。
  - `save_cancelled_if_active` 协议 (`ingestion_runtime.py:763-783`) 语义：仅当当前 job 非终态时原子保存 cancelled 终态；已是终态则原样返回。
  - `FsFinsIngestionJobStore.save_cancelled_if_active` 实现 (`ingestion_runtime.py:1053-1087`) 在 file lock 内读取当前 record，检查 `record.status in _TERMINAL_STATUSES`，终态直接返回，非终态才写入 CANCELLED。
- **测试证据**: `test_save_cancelled_does_not_overwrite_current_terminal_record` (`test_fins_ingestion_runtime.py:1158-1183`):
  - 创建 preprocess job → 手动将 store 中 record 设为 SUCCEEDED 终态 → 用旧 active record 调用 `_save_cancelled` → 断言返回和 store 中 record 仍为 SUCCEEDED、`cancellation_requested` 仍为 `False`、`result_summary` 仍为原始值。
  - 使用 production `FsFinsIngestionJobStore`（通过 `_build_ingestion_runtime`），不是 fake store。
- **start-boundary create-after-cancel 保留**: `start_download`/`start_preprocess`/`start_upload` 中 `_is_start_cancelled(cancellation_token)` → `_save_cancelled(start.record)` 路径不受影响，因为新建的 queued record 不是终态。
- **判断**: 完全满足 Controller DS-S1 要求。

### DS-S2: _validate_upload_source_kind / _normalize_upload_request 显式穷尽保护 — fixed

- **要求**: 对 `FinsUploadFilingRequest` 与 `FinsUploadMaterialRequest` 显式分支校验，尾部使用 `typing.assert_never` 作为类型检查可感知的穷尽保护。
- **证据**:
  - `_validate_upload_source_kind` (`ingestion_runtime.py:2707-2728`):
    ```python
    if isinstance(request, FinsUploadFilingRequest):
        ...
        return
    if isinstance(request, FinsUploadMaterialRequest):
        ...
        return
    assert_never(request)
    ```
  - `_normalize_upload_request` (`ingestion_runtime.py:2665-2684`):
    ```python
    if isinstance(request, FinsUploadFilingRequest):
        return replace(request, action=action)
    if isinstance(request, FinsUploadMaterialRequest):
        return replace(request, action=action)
    assert_never(request)
    ```
  - `assert_never` 从 `typing` 导入 (`ingestion_runtime.py:23`)。
- **pyright 验证**: Controller 已确认 0 errors。若未来向 `FinsUploadRequest` union 新增第三种类型，pyright 会在 `assert_never(request)` 处报错。
- **判断**: 完全满足 Controller DS-S2 要求。

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 本次 fix 只涉及 docstring、原子终态守护和类型穷尽保护，不改变运行时行为语义。
- Production upload runner、upload awaiting tool、Host wait adapter、physical cancel / revoke 仍按 Controller adjudication 归属后续 Slice。
- 测试从 35 条增加到 36 条，新增的 `test_save_cancelled_does_not_overwrite_current_terminal_record` 直接覆盖已终态不被覆盖的语义。

## Verdict

**fix-accepted**

4 个 accepted findings 全部 fixed。0 blocking findings。无新增 findings。
