# WU-TOOLS-01-F01-03 Slice 1 Fix - Codex

## Scope

- 只修复 Controller 已接受的 Slice 1 code review findings。
- 未修改 `docs/host/issues-implementation-control.md`。
- 未修改 OLD SEC/CN/HK downloader 或 OLD pipeline workflow。
- 未引入 upload awaiting tool、Host wait adapter、真实 production upload runner 或 SEC/CN/HK workflow。

## Fixes

1. MIMO-S1：更新 `dayu.fins.ingestion_runtime` 模块 docstring，明确本模块承载 download / preprocess / upload job foundation，并明确不实现真实网络下载、真实 upload workflow、Host wait adapter、tool provider 或 CLI。
2. MIMO-S2：更新 `FinsIngestionJobRecord` docstring，将 `operation_kind` 说明为下载、预处理或上传，并将 `source` / `source_kind` 描述调整为 upload shape 可自解释的语义。
3. DS-S1：为 `FinsIngestionJobStore` 增加 `save_cancelled_if_active(job_id, *, finished_at)` 协议；`FsFinsIngestionJobStore` 在同一个 file lock 内读取当前 record，若当前已是终态则原样返回，否则写入 `CANCELLED` 并设置 `cancellation_requested=True`；`_save_cancelled` 改为调用该原子语义。测试 fake store 同步实现相同语义。
4. DS-S2：`_validate_upload_source_kind` 对 `FinsUploadFilingRequest` 与 `FinsUploadMaterialRequest` 显式分支校验，尾部使用 `typing.assert_never` 作为类型检查可感知的穷尽保护；`_normalize_upload_request` 同步采用显式 union 收口。

## Tests

- 新增 `test_save_cancelled_does_not_overwrite_current_terminal_record`，使用 production `FsFinsIngestionJobStore` 证明当 store 当前 record 已为 `SUCCEEDED` 终态时，`_save_cancelled` 不会用旧 active record 覆盖为 `CANCELLED`。

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - 结果：`36 passed`
  - 备注：存在 3 条既有 `edgar` deprecation warnings。
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过。

## README

- 已按触发规则读取 `dayu/fins/README.md` 与 `tests/README.md` 的 Agent 更新约束。
- 本次变更没有改变 README 面向开发者说明的 capability、架构边界、测试分层或运行方式；只是补齐 ingestion runtime 内部原子终态语义、docstring 与现有测试文件内的回归覆盖，因此不需要更新 README。

## Residual Risk

- 本次仅修 durable job foundation 的取消终态守护与 upload request union 穷尽性；真实 upload workflow、awaiting tool、Host wait adapter、physical cancel / revoke 仍按 Controller adjudication 归属后续 Slice 或既有 owner。
