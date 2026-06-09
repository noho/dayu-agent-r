# WU-TOOLS-01-F01-03 Slice 1 Fix Re-Review

## Scope

- Mode: re-review of Slice 1 fix (current changes)
- Branch: `phase/wu-tools-01-f01-03`
- Reviewed files:
  - `dayu/fins/ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
- Reference artifacts:
  - Controller adjudication: `docs/reviews/wu-tools-01-f01-03-slice1-code-review-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-tools-01-f01-03-slice1-fix-codex.md`
  - Accepted plan: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- Review scope: 仅复核 4 个 accepted findings，不扩大审查范围
- Parallel review coverage: 无

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`: 36 passed
- `source .venv/bin/activate && pyright`: 0 errors, 0 warnings, 0 informations
- `git diff --check`: 通过

## Findings

### Finding 1 (MIMO-S1): 模块 docstring — fixed

- **入口/函数**: `dayu.fins.ingestion_runtime` 模块 docstring
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1-7`
- **审查结果**: 模块 docstring 已更新为 `"Fins 下载、预处理与上传运行时基础能力"`，明确列出 download / preprocess / upload job foundation，并在第二段显式声明"不实现真实网络下载、真实 upload workflow、Host wait adapter、tool provider 或 CLI"。与 adjudication 要求一致。
- **状态**: **fixed**

### Finding 2 (MIMO-S2): FinsIngestionJobRecord docstring — fixed

- **入口/函数**: `FinsIngestionJobRecord` dataclass docstring
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:649-669`
- **审查结果**: `operation_kind` 已更新为"下载、预处理或上传"。`source` 已说明"预处理与上传任务为 ``None``"。`source_kind` 已说明"预处理与上传任务用于区分 filing/material，下载任务为 ``None``"。三者组合完整自解释 upload shape 语义。与 adjudication 要求一致。
- **状态**: **fixed**

### Finding 3 (DS-S1): _save_cancelled active-only atomic cancelled terminal — fixed

- **入口/函数**: `FinsIngestionJobStore.save_cancelled_if_active` (协议), `FsFinsIngestionJobStore.save_cancelled_if_active` (实现), `FinsIngestionRuntime._save_cancelled` (调用方)
- **文件(行号)**:
  - 协议: `ingestion_runtime.py:763-783`
  - 实现: `ingestion_runtime.py:1053-1087`
  - 调用方: `ingestion_runtime.py:2242-2256`
  - 测试: `test_fins_ingestion_runtime.py:1158-1182`
- **审查结果**:
  - 协议 `save_cancelled_if_active(job_id, *, finished_at)` 语义为"仅当当前 job 非终态时原子保存 cancelled 终态"，文档完整。
  - `FsFinsIngestionJobStore` 实现在同一 file lock 内先读取当前 record：若已终态则原样返回；否则写入 `CANCELLED` 并设置 `cancellation_requested=True`。原子性由 file lock 保证。
  - `_save_cancelled` 改为调用 `self.job_store.save_cancelled_if_active(record.job_id, finished_at=now)`，仅使用 `record.job_id` 定位 store 中的当前状态，不传递旧 `record` 的其他字段。
  - start 边界 create-after-cancel 场景保持不变：`start.record` 刚创建为 `QUEUED` 非终态，`save_cancelled_if_active` 会正常写入 `CANCELLED`。
  - 测试 `test_save_cancelled_does_not_overwrite_current_terminal_record` 使用 production `FsFinsIngestionJobStore`，先将 record 通过 `save_job` 写入 `SUCCEEDED` 终态，再以旧 `QUEUED` record 调用 `_save_cancelled`，断言 store 中仍为 `SUCCEEDED` 且 `result_summary` sentinel 未丢失。
  - 测试 fake store `_ClaimRaceJobStore` 同步实现了 `save_cancelled_if_active` 的相同语义。
- **状态**: **fixed**

### Finding 4 (DS-S2): _validate_upload_source_kind / _normalize_upload_request 穷尽 union — fixed

- **入口/函数**: `_validate_upload_source_kind`, `_normalize_upload_request`
- **文件(行号)**:
  - `_validate_upload_source_kind`: `ingestion_runtime.py:2707-2728`
  - `_normalize_upload_request`: `ingestion_runtime.py:2665-2684`
- **审查结果**:
  - `_validate_upload_source_kind` 对 `FinsUploadFilingRequest` 和 `FinsUploadMaterialRequest` 分别做显式 `isinstance` 分支校验，各自验证对应 `SourceKind` 匹配性，尾部使用 `typing.assert_never(request)` 作为穷尽保护。
  - `_normalize_upload_request` 同样对两个类型分别做显式 `isinstance` 分支处理，尾部使用 `typing.assert_never(request)` 收口。
  - `assert_never` 来自 `typing`（第 23 行 import），在 `FinsUploadRequest = FinsUploadFilingRequest | FinsUploadMaterialRequest`（第 403 行）的 union 上提供类型检查可感知的穷尽保护：未来若新增 union 成员，pyright 会在 `assert_never` 处报类型错误。
  - pyright 验证通过，0 errors。
- **状态**: **fixed**

## Verdict

**pass**

- 4/4 accepted findings 均已修复。
- 0 blocking findings。
- 无新增 findings。

## Open Questions

无。

## Residual Risk

- 本次仅复核 Slice 1 fix 的 4 个 accepted findings。`_save_failed` 仍使用 `save_job` 直接写终态而非带终态守护的原子方法，但在当前 `_run_*_job` 的调用模式下（先读 latest → 判取消 → `_save_cancelled` 或 `_save_failed`），`_save_failed` 只在 job 未被取消时调用，不涉及本次 review 要求的 cancelled 终态覆盖问题。后续 Slice 若引入新的 failed 写入路径，可能需要独立的终态守护。
- 真实 upload workflow、Host wait adapter、tool provider、CLI 均不在 Slice 1 scope，相关缺口按 Controller adjudication 归属后续 Slice。
