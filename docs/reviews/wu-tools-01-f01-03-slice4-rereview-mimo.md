# WU-TOOLS-01-F01-03 Slice 4 Fix Re-Review - AgentMiMo

**审查时间**: 20260609-183359
**审查范围**: Slice 4 fix 后 dirty changes，复审 AgentCodex 对 controller accepted findings 的修复
**审查基准**: controller adjudication `CTRL-S4-01` ~ `CTRL-S4-04`

## Verdict

**pass**

4 项 accepted findings 全部修复确认，无新增 finding，无 correctness/architecture/AGENTS violation。OLD upload 语义未改，upload 长事务边界未触碰，无越界依赖。

## Accepted Findings Status

### CTRL-S4-01: Update stale upload/runtime docstrings — **Fixed**

- `sec_pipeline.py:1-7` — 模块 docstring 已更新为 "SEC 下载/上传管线"，明确列出 "Slice 4 迁移的 production upload facade"，仅排除 "process、CLI、Host、tool/provider 装配"。
- `cn_pipeline.py:1-7` — 同上模式，"CN/HK 下载/上传管线"，upload 已列为 in-scope。
- `ingestion_runtime.py:1534-1539` — `start_upload` docstring 已移除 "Slice 1 默认不装配生产 upload runner"，改为 "通过 `DefaultFinsRuntime` 装配的 runtime 已提供 production SEC/CN/HK upload runner"。

### CTRL-S4-02: Remove private helper symbols from `docling_upload_service.__all__` — **Fixed**

- `docling_upload_service.py:1237-1254` — `__all__` 现仅含 16 个公共符号，零 `_` 前缀私有符号。
- 测试文件直接导入私有 helper（`_PendingFileAsset`, `_build_upload_source_fingerprint`, `_convert_bytes_with_docling` 等）是**预期行为**：controller adjudication 明确允许 "tests allowed to import private helpers directly where they intentionally test internals; direct import does not require `__all__`"。Python `__all__` 仅影响 `from module import *`，不影响直接 import。

### CTRL-S4-03: Remove dead `cast_upload_host` — **Fixed**

- `sec_upload_workflow.py` — `cast_upload_host` 函数定义、`__all__` 导出、`typing.cast` 专用 import 均已删除。
- `__all__` 现含 5 个公共符号：`SecUploadWorkflowHost`, `collect_upload_result_from_events`, `require_upload_result_mapping`, `run_upload_filing_stream`, `run_upload_material_stream`。
- `SecUploadWorkflowHost` 协议仍正常导出（line 39-79），stream 函数签名未变（lines 112-128, 290-309），`sec_pipeline.py` 调用点未受影响（lines 703, 840）。

### CTRL-S4-04: Clarify `DefaultFinsRuntime` pipeline instance split — **Fixed**

- `service_runtime.py:526-527` — 添加两行注释说明 split 原因："下载 adapter 保留 source-specific downloader defaults 与 adapter identity；upload runner 使用 production facade，但共享同一组 repository/job store。"
- 无行为重构，仅注释。

## 复核项

| 检查项 | 结果 |
|--------|------|
| OLD upload 语义未改 | PASS — auto/create/update/delete, skip/overwrite, fingerprint/version, ID 语义均保留 |
| upload 长事务边界未触碰 | PASS — start_upload 仍创建 durable job record，提交到 background executor，无 tool/provider/wait adapter |
| 无 upload tool/provider/wait adapter/CLI 越界 | PASS — 文件内零匹配 |
| 无 Host/Engine 反向依赖 | PASS — pipeline 文件内无 `dayu.host`/`dayu.engine` import；`Host` 引用仅限 intra-pipeline workflow host protocol |
| 无 Any/object 类型扩散 | PASS — 变更文件内零匹配 |
| 测试通过 | PASS — 58 passed, 1 skipped, 3 warnings |
| pyright | PASS — 0 errors |
| git diff --check | PASS |

## New Findings

无。

## Residual Risks

- Deferred findings（CTRL-S4-D1 upload failure-path test matrix, CTRL-S4-D2 progress helper literal consolidation）仍 deferred。
- crash recovery 仍由 Issue 129 / WAIT follow-ups 跟踪。

## 结论

可进入 controller adjudication。
