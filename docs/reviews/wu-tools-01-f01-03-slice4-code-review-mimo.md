# WU-TOOLS-01-F01-03 Slice 4 Code Review - AgentMiMo

**审查时间**: 20260609-182011
**审查范围**: Slice 4 production upload runtime implementation (dirty changes)
**审查基准**: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`, `docs/host/issues-implementation-control.md`, `docs/reviews/wu-tools-01-f01-03-slice4-implementation-codex.md`

## Verdict

**pass-with-findings**

无 blocking finding；3 个 medium/low severity findings 需要后续清理。OLD upload 语义保留正确，runtime lifecycle 分离正确，upload 长事务边界正确，storage/ticker 边界正确。

## Findings

### Finding 1: `docling_upload_service.py` `__all__` 暴露 10 个私有符号

**严重程度**: High
**文件**: `dayu/fins/pipelines/docling_upload_service.py:1237-1264`

`__all__` 包含 10 个下划线前缀的私有符号：

```
"_PendingFileAsset",              # 内部 dataclass
"_build_upload_source_fingerprint",
"_can_skip_upload",
"_convert_bytes_with_docling",    # 默认 Docling 转换器
"_increment_document_version",
"_normalize_ticker",              # 与 ticker_normalization 重复
"_pick_primary_docling_file",
"_resolve_document_version",
"_resolve_upsert_mode",
"_validate_source_files",
```

其中 7 个（`_can_skip_upload`, `_increment_document_version`, `_normalize_ticker`, `_pick_primary_docling_file`, `_resolve_document_version`, `_resolve_upsert_mode`, `_validate_source_files`）**无任何外部消费者**，仅为潜在测试便利而暴露。仅 3 个被测试直接导入（`_PendingFileAsset`, `_build_upload_source_fingerprint`, `_convert_bytes_with_docling`）。

**AGENTS 违反**: "无私有符号无必要 re-export"。`_normalize_ticker` 与 `dayu.fins.ticker_normalization` 重复，暴露后会混淆调用方选择。`_convert_bytes_with_docling` 暴露内部实现，允许绕过 `DoclingUploadService`。

**建议**: 从 `__all__` 移除全部 10 个私有符号；测试通过模块路径直接导入（`from dayu.fins.pipelines.docling_upload_service import _PendingFileAsset`）。

---

### Finding 2: `cast_upload_host` 是死代码

**严重程度**: Medium
**文件**: `dayu/fins/pipelines/sec_upload_workflow.py:539-557`

`cast_upload_host` 是一个 no-op identity cast 函数，导出在 `__all__` 中但**全仓库无任何调用点**。`SecPipeline` 通过结构化子类型满足 `SecUploadWorkflowHost` 协议，无需显式 cast。

```python
def cast_upload_host(host: SecUploadWorkflowHost) -> SecUploadWorkflowHost:
    return cast(SecUploadWorkflowHost, host)
```

**AGENTS 违反**: "无胶水 seam；无无用 helper"。

**建议**: 从模块和 `__all__` 中移除。

---

### Finding 3: 模块 docstring 过期

**严重程度**: Low
**文件**:
- `dayu/fins/pipelines/sec_pipeline.py:1-6`
- `dayu/fins/pipelines/cn_pipeline.py:1-6`
- `dayu/fins/ingestion_runtime.py:1537`

两个 pipeline 模块的 docstring 仍声称 "上传、process、CLI 和 Host 集成不在本 Slice 内"，但 Slice 4 已迁移 upload 方法。`ingestion_runtime.py` 的 `start_upload` docstring 仍说 "Slice 1 默认不装配生产 upload runner"，但 Slice 4 已装配。

**建议**: 更新 docstring 反映当前状态。

---

## 审查通过项

### 1. OLD upload 语义保留

- auto/create/update/delete 语义通过 `resolve_upload_action` 保留
- skip/overwrite 逻辑通过 `_can_skip_upload` 和 `reset_upload_target_for_overwrite` 保留
- source fingerprint/version 通过 `_build_upload_source_fingerprint` 和 `_increment_document_version` 保留
- SEC/CN filing/material IDs 通过 `build_sec_filing_ids`/`build_cn_filing_ids`/`build_material_ids` 保留
- Docling conversion 通过 `DoclingUploadService` 保留
- file event/result mapping 通过 `upload_filing_events.py`/`upload_material_events.py`/`upload_progress_helpers.py` 保留

### 2. Runtime lifecycle 分离

- `FinsIngestionRuntime` 只管 job lifecycle（创建 durable queued record，提交 runner，写终态）
- `ProductionFinsUploadRunner` 是纯 handoff adapter，不嵌入业务规则
- upload business rules 在 pipeline 层（`SecPipeline`/`CnPipeline`）和 service 层（`DoclingUploadService`）

### 3. Upload 长事务边界

- `start_upload` 创建 durable job record，提交到 background executor
- cooperative cancellation 通过 `UploadCancellationChecker` 传递
- Slice 5 才做 tool/provider/wait adapter——本 slice 无越界

### 4. Storage 边界

- 所有 source document 操作通过 `SourceDocumentRepositoryProtocol`
- 所有 blob 操作通过 `DocumentBlobRepositoryProtocol`
- 公司元数据通过 `CompanyMetaRepositoryProtocol`
- 无直接文件系统写入（`file_path.read_bytes()` 仅读取用户上传输入，可接受）

### 5. Ticker 边界

- 所有 ticker 归一化通过 `dayu.fins.ticker_normalization`
- 无模块自行实现 ticker 解析

### 6. Host/Engine 反向依赖

- `dayu.fins.pipelines/` 零 import from `dayu.host`/`dayu.engine`
- 反向依赖仅存在于 `dayu/fins/ingestion/wait_adapter.py`（设计如此，适配层）

### 7. AGENTS 编码约束

- 无 `Any`/`object` 类型
- 所有函数/类有中文 docstring
- `ProductionFinsUploadRunner` 使用 `@dataclass(frozen=True)`

### 8. README 准确性

- `dayu/fins/README.md` 准确声明 "direct runtime job contract 与 production runner，不暴露 upload tool provider，也不绑定 Host wait adapter"
- 未声称 upload tool/provider 已可用

### 9. 测试覆盖

- 6 个测试文件覆盖 service 行为、集成、stream event lifecycle、runtime job lifecycle
- Docling 集成测试通过环境变量开关（`DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`）

## Open Questions

无。

## Residual Risks

1. **Docling `__all__` 私有符号泄漏**: 7 个无外部消费者的私有符号暴露在公共 API 中，需清理。
2. **`cast_upload_host` 死代码**: 需移除。
3. **模块 docstring 过期**: 3 处 docstring 需更新。
4. **crash recovery**: daemon-thread upload job 的 crash recovery 和 partial artifact 清理仍由 Issue 129 / WAIT follow-ups 跟踪。
5. **upload tool/provider/wait adapter**: 延迟到 Slice 5。

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| pytest 指定矩阵 | 58 passed, 1 skipped, 3 warnings |
| pyright | 0 errors |
| git diff --check | 通过 |
| type/boundary scan | 无匹配 |
| Host/Engine 反向依赖 | 仅 `dayu/fins/ingestion/wait_adapter.py`（设计如此） |
| upload tool/provider 越界 | 无 |
| Any/object 类型 | 无 |
