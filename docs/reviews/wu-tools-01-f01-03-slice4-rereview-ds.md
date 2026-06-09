# WU-TOOLS-01-F01-03 Slice 4 Fix Re-Review — AgentDS

## Scope

- **Mode**: current changes (fix re-review)
- **Branch**: `phase/wu-tools-01-f01-03`
- **Base**: main
- **Output file**: `docs/reviews/wu-tools-01-f01-03-slice4-rereview-ds.md`
- **Reviewed scope**: 仅 Slice 4 fix gate 涉及的 CTRL-S4-01 至 CTRL-S4-04 accepted findings
- **Excluded scope**: deferred findings (CTRL-S4-D1/D2), upload tool/provider/wait adapter/CLI/Host/Engine
- **Source documents**:
  - `docs/reviews/wu-tools-01-f01-03-slice4-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-03-slice4-fix-codex.md`

## Verdict

**pass** — 全部 4 个 CTRL-S4 accepted findings 均已 fixed；0 blocking findings；0 new findings。

---

## CTRL-S4 Finding Status

### CTRL-S4-01: 更新 stale docstrings

**Status: fixed**

- **文件**:
  - `dayu/fins/pipelines/sec_pipeline.py:1-7`
  - `dayu/fins/pipelines/cn_pipeline.py:1-7`
  - `dayu/fins/ingestion_runtime.py:1533-1539`
- **验证证据**:
  1. `sec_pipeline.py:1-6`: 模块 docstring 更新为 "SEC 下载/上传管线...本模块承载 OLD SEC pipeline 的下载面与 Slice 4 迁移的 production upload facade：download、download_stream、上传 filing/material、下载过滤..."，"process、CLI、Host、tool/provider 装配不在本 Slice 内"（明确区分已实现与排除项）
  2. `cn_pipeline.py:1-6`: 模块 docstring 更新为 "CN/HK 下载/上传管线...本模块承载 OLD CN/HK pipeline 的下载面与 Slice 4 迁移的 production upload facade：download、download_stream、上传 filing/material、下载候选过滤..."，"process、CLI、Host、tool/provider 装配不在本 Slice 内"
  3. `ingestion_runtime.py:1533-1539`: `start_upload` docstring 更新为 "本方法只负责创建 durable queued record 并提交上传 runner 边界。直接创建的 runtime 若未传入 runner 仍会以不支持结束；通过 DefaultFinsRuntime 装配的 runtime 已提供 production SEC/CN/HK upload runner。process、CLI、Host、tool/provider 装配不在 Slice 4 内。"
  4. 行为未变

### CTRL-S4-02: 移除 `docling_upload_service.__all__` 中私有 helper 符号

**Status: fixed**

- **文件**: `dayu/fins/pipelines/docling_upload_service.py:1237-1254`
- **验证证据**:
  1. `__all__` 现在仅包含 17 个公开符号：`DOCLING_FILE_SUFFIX`, `DoclingUploadConverter`, `DoclingUploadService`, `SUPPORTED_UPLOAD_SUFFIXES`, `UPLOAD_ACTIONS`, `UploadFileEventPayload`, `UploadFileEventType`, `UploadOperationResult`, `build_cn_filing_ids`, `build_material_ids`, `build_sec_filing_ids`, `derive_report_kind`, `normalize_cn_fiscal_period`, `reset_upload_target_for_overwrite`, `resolve_upload_action`, `validate_material_upload_ids`
  2. 已移除的 10 个 `_` 前缀符号：`_PendingFileAsset`, `_build_upload_source_fingerprint`, `_can_skip_upload`, `_convert_bytes_with_docling`, `_increment_document_version`, `_normalize_ticker`, `_pick_primary_docling_file`, `_resolve_document_version`, `_resolve_upsert_mode`, `_validate_source_files`
  3. 验证脚本 `awk '/__all__ = \[/...' | rg '"_'` 无匹配——确认 no `_`-prefixed symbols in `__all__`
  4. helper 名称未改，测试仍可直接导入

### CTRL-S4-03: 删除 dead `cast_upload_host`

**Status: fixed**

- **文件**: `dayu/fins/pipelines/sec_upload_workflow.py`
- **验证证据**:
  1. `rg 'cast_upload_host' --type py` 全代码库无匹配——函数定义、`__all__` 条目及 `typing.cast` 导入均已删除
  2. `sec_upload_workflow.py:__all__` 不再包含 `cast_upload_host`
  3. `SecUploadWorkflowHost` protocol 与 stream 函数行为未变

### CTRL-S4-04: 注释说明 `DefaultFinsRuntime` pipeline 实例分离

**Status: fixed**

- **文件**: `dayu/fins/service_runtime.py:526-527`
- **验证证据**:
  1. Line 526-527 新增注释: "下载 adapter 保留 source-specific downloader defaults 与 adapter identity；upload runner 使用 production facade，但共享同一组 repository/job store。"
  2. 注释位置紧邻 `sec_upload_pipeline = SecPipeline(...)` 与 `cn_upload_pipeline = CnPipeline(...)` 构造之前，准确说明分离意图
  3. pipeline 构造逻辑未做重构（符合 fix scope）

---

## 无新增 Findings

- targeted type scan (`Any`/`object`): 0 matches in touched production files
- boundary scan (Host/Engine/UI/CLI/tool/provider): 0 matches
- `docling_upload_service.__all__` private export scan: 0 matches
- dead helper scan (`cast_upload_host`): 0 matches
- OLD upload 语义未改
- upload long transaction 边界未被触碰

## 验证摘要

| 检查项 | 结果 |
|---|---|
| pytest (6 测试文件) | 58 passed, 1 skipped, 3 warnings (仅 edgartools deprecation) |
| pyright | 0 errors, 0 warnings, 0 informations |
| git diff --check | passed |
| `__all__` 私有 `_` 符号残留 | 0 |
| `cast_upload_host` 残留 | 0 |
| `Any`/type `object` 扩散 | 0 |
| Host/Engine/tool/provider 越界 | 0 |

## Residual Risk

- deferred findings (CTRL-S4-D1/D2) 未在本次 fix gate 处理，残留风险与原 Slice 4 reviews 一致。
