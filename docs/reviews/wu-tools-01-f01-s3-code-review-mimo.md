# Code Review: WU-TOOLS-01-F01 Slice S3 - Download Runtime Pipeline

## Scope

- Mode: current changes
- Branch: host-wu-tools-01-f01
- Base: main
- Output file: docs/reviews/wu-tools-01-f01-s3-code-review-mimo.md
- Included scope: dayu/fins/ingestion_runtime.py, dayu/fins/service_runtime.py, tests/fins/test_fins_ingestion_runtime.py, dayu/fins/README.md, tests/README.md
- Excluded scope: docs/host/issues-implementation-control.md (controller bookkeeping background only)
- Parallel review coverage: 无

## Verdict

**pass-with-findings**

## Findings

### 1-未修复-低-测试导入私有实现细节

- **入口/函数**: `tests/fins/test_fins_ingestion_runtime.py::test_store_file_lock_closes_stream_when_flock_fails`
- **文件(行号)**: `tests/fins/test_fins_ingestion_runtime.py:40` (import), `tests/fins/test_fins_ingestion_runtime.py:801` (usage)
- **输入场景**: 测试文件锁失败时的行为
- **实际分支**: 测试直接导入并使用 `_StoreFileLock` 私有类
- **预期行为**: 测试应通过公共接口验证行为，或明确说明为何需要访问私有实现
- **实际行为**: 测试导入了 `_StoreFileLock`（以单下划线开头的私有类），并在测试中直接实例化该类
- **直接证据**: 第 40 行 `from dayu.fins.ingestion_runtime import ... _StoreFileLock`，第 801 行 `with _StoreFileLock(tmp_path / "jobs" / ".store.lock"):`
- **影响**: 低。这是一个边界条件测试，验证文件锁失败时的资源清理行为。虽然导入私有实现细节不是最佳实践，但该测试覆盖了一个重要的错误处理路径（flock 失败时关闭已打开的文件流），这个行为难以通过公共接口测试。
- **建议改法和验证点**: 可以考虑将 `_StoreFileLock` 提升为公共实现（移除下划线前缀）或在测试中添加注释说明为何需要访问私有实现。当前实现可以接受，因为测试覆盖了重要的资源清理边界条件。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Validation Notes

已运行验证命令：

```bash
source .venv/bin/activate && pyright dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py
```
结果：0 errors, 0 warnings, 0 informations

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -v --tb=short
```
结果：24 passed, 3 warnings (edgar deprecation warnings)

额外自查：
- `rg -n "\bAny\b|\bobject\b|hasattr\(|getattr\(" dayu/fins/ingestion_runtime.py dayu/fins/service_runtime.py` 无匹配
- 所有函数和类都有完整中文 docstring
- 无魔法字符串/数字（常量通过 `Final` 声明）
- 无反向依赖或兼容 facade

## S3 Requirements Checklist

### ✓ start_download 使用同一 job store/executor 和 S2 相同 terminalization 语义

**直接证据**:
- `ingestion_runtime.py:896-903`: `start_download` 调用 `self.executor.submit(...)` 提交后台 job
- `ingestion_runtime.py:1101-1121`: `_run_download_job` 使用与 `_run_preprocess_job` 相同的 terminalization 语义：
  - `_mark_job_running_or_cancelled(job_id)` - 标记为 running 或 cancelled
  - `_save_cancelled(latest)` - 保存 cancelled 终态
  - `_save_failed(...)` - 保存 failed 终态
  - `_save_succeeded(...)` - 保存 succeeded 终态
  - `_save_failed_from_exception(job_id, exc)` - 异常转 failed

### ✓ 通过 normalize_ticker(...) 后才 route adapter，adapter 接收 NormalizedTicker

**直接证据**:
- `ingestion_runtime.py:878`: `normalized = ticker_normalization.normalize_ticker(request.ticker)`
- `ingestion_runtime.py:1241-1246`: `adapter_request = FinsSourceDownloadAdapterRequest(normalized_ticker=normalized, ...)`
- `ingestion_runtime.py:236-252`: `FinsSourceDownloadAdapterRequest` 的 `normalized_ticker` 字段类型为 `NormalizedTicker`

### ✓ adapter protocol/request/response 是 Fins-owned typed shapes，不泄漏 raw provider payload

**直接证据**:
- `ingestion_runtime.py:271-287`: `FinsSourceDownloadAdapter(Protocol)` 定义了清晰的 adapter 协议
- `ingestion_runtime.py:150-164`: `FinsDownloadedFile` docstring 明确说明"content: 文件字节内容；只用于落盘，不进入 job record"
- `ingestion_runtime.py:168-178`: `FinsDownloadedSourceDocument` docstring 明确说明"meta: 业务元数据，不含 provider raw payload"
- `ingestion_runtime.py:191-213`: `FinsRejectedFilingDownloadArtifact` 是 Fins-owned typed shape
- `ingestion_runtime.py:255-268`: `FinsSourceDownloadAdapterResult` 包含 discovered_count, documents, rejected_artifacts, failed_count

### ✓ source/blob/rejected filing 写入全部经 dayu.fins.storage repository protocols/implementations

**直接证据**:
- `ingestion_runtime.py:1353`: `self.source_repository.create_source_document(create_request, document.source_kind)`
- `ingestion_runtime.py:1387-1393`: `self.blob_repository.store_file(...)` 通过 blob repository 写入文件
- `ingestion_runtime.py:1424-1477`: `self.filing_maintenance_repository.upsert_rejected_filing_artifact(...)` 通过 filing maintenance repository 写入 rejected artifact
- `ingestion_runtime.py:1502-1509`: `self.filing_maintenance_repository.store_rejected_filing_file(...)` 通过 repository 写入 rejected 文件

### ✓ 默认无 adapter 时是 explicit unsupported-source failed job，不假成功

**直接证据**:
- `ingestion_runtime.py:1305-1307`: `_select_download_adapter` 在找不到 adapter 时抛出 `_UnsupportedDownloadSourceError`
- `ingestion_runtime.py:1118-1119`: `_run_download_job` 捕获 `_UnsupportedDownloadSourceError` 并调用 `_save_download_unsupported(job_id, str(exc))`
- `ingestion_runtime.py:1751-1782`: `_save_download_unsupported` 保存 failed 终态，包含明确的错误消息

### ✓ repeated start / overwrite_existing skip/update 语义属于 runtime，provider 不自造 duplicate semantics

**直接证据**:
- `ingestion_runtime.py:1334-1338`: `_store_downloaded_document` 检查源文档是否存在，根据 `overwrite_existing` 参数决定跳过或重置
- `ingestion_runtime.py:1600-1601`: `_preprocess_one_document` 检查 processed 文档是否存在，根据 `rebuild_processed` 参数决定跳过
- 测试 `test_start_download_repeated_request_skips_existing_source_document` 和 `test_start_preprocess_skips_existing_processed_document_without_rebuild` 验证了这些行为

### ✓ 没有违反 S3 non-goals

**直接证据**:
- 未实现真实 SEC/CN/HK 网络下载 adapter（只有 fake adapter 用于测试）
- 未修改 Host/Engine/Service/tool provider
- 未添加 CLI
- 未添加 CI 配置

### ✓ 没有违反 AGENTS.md

**直接证据**:
- 无 `Any`、`object`、`hasattr`、`getattr` 使用
- 所有函数签名都有完整类型注解
- 所有函数和类都有完整中文 docstring
- 常量通过 `Final` 声明，无魔法字符串/数字
- 无反向依赖
- 无兼容 facade
- 无胶水 seam

### ✓ 测试覆盖 plan expected assertions

**直接证据**:
- 测试覆盖了 plan 中列出的所有关键场景：
  - cross-runtime shared workspace job store
  - download / preprocess queued job persistence
  - ticker normalization
  - fake download adapter 写入 source/blob 仓储
  - unsupported source failed terminal
  - repeated download 按 storage 语义跳过
  - rejected filing artifact 通过 maintenance 仓储保存
  - preprocess source -> processed pipeline
  - 已有 processed 跳过 / 重建
  - missing document failed terminal
  - unsupported processor not_supported summary
  - cancel transition
  - record leakage boundary
  - job store 原子写入失败清理
  - 文件锁失败关闭

### ✓ README 只同步稳定事实，没有未来计划或越界说明

**直接证据**:
- `dayu/fins/README.md` 描述了当前稳定事实，包括 download adapter protocol、storage write path 和 unsupported-source terminal failure
- `tests/README.md` 描述了当前测试覆盖范围
- 两个 README 都没有包含未来计划或越界说明

## Open Questions

无

## Residual Risk

1. **未实现真实网络下载 adapter**: 这是 S3 明确的 non-goal，但需要在后续 slice 中实现真实的 SEC/CN/HK adapter
2. **adapter registry 由 runtime 构造参数注入**: 生产 provider / wait adapter 暴露属于后续 S4
3. **下载 adapter response 仍需未来真实 adapter owner 保证不携带 provider raw payload**: runtime job record 只保存有界计数、document ids 与失败摘要

## Architecture Alignment

### Host Design Alignment

- ✓ Fins business logic stays outside Host; `dayu.fins` is the correct location for ingestion runtime
- ✓ `dayu.runtime` is not used for Fins business logic
- ✓ No changes to Host/Engine contracts

### Engine Design Alignment

- ✓ Engine only sees tool schemas, tool call requests and tool outcomes
- ✓ Financial document storage uses `dayu.fins.storage` repository protocols
- ✓ No changes to `ToolAwaitSpec`, `ToolAwaitingOutcome`, or Host wait record schema

### Storage Boundary

- ✓ All source documents, blob files, processed documents, and rejected filing artifacts use `dayu.fins.storage` repository protocols/implementations
- ✓ No direct `Path(".../filings")`, `Path(".../processed")`, glob or raw JSON writes outside storage repository internals
- ✓ Job store uses runtime-owned files for job governance state (not financial document content)
- ✓ Job store path is deterministic from `workspace_root`

## Summary

Slice S3 实现了 download runtime pipeline，符合所有 S3 requirements：

1. ✓ 使用同一 job store/executor 和 S2 相同 terminalization 语义
2. ✓ 通过 `normalize_ticker(...)` 后才 route adapter
3. ✓ adapter protocol/request/response 是 Fins-owned typed shapes
4. ✓ source/blob/rejected filing 写入全部经 `dayu.fins.storage` repository protocols
5. ✓ 默认无 adapter 时是 explicit unsupported-source failed job
6. ✓ repeated start / overwrite_existing skip/update 语义属于 runtime
7. ✓ 没有违反 S3 non-goals
8. ✓ 没有违反 AGENTS.md
9. ✓ 测试覆盖 plan expected assertions
10. ✓ README 只同步稳定事实

唯一 finding 是测试导入私有实现细节 `_StoreFileLock`，这是一个低严重程度问题，因为测试需要验证文件锁失败时的资源清理行为。

实现质量高，代码清晰，类型安全，文档完整，测试覆盖全面。建议通过此 code review gate。
