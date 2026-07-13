# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-code-review-mimo.md`
- Included scope: S2 allowed production/test files（`dayu/fins/domain/document_models.py`、`dayu/fins/storage/*`、`dayu/fins/processors/source_text.py`、SEC form processors、`dayu/fins/pipelines/sec_6k_rules.py`、`dayu/fins/tools/cache.py`、`dayu/fins/tools/read_runtime.py`、`dayu/fins/tools/read_runtime_helpers.py`、`dayu/fins/tools/error_contract.py`、`dayu/fins/tools/fins_tools.py`、`tests/fins/test_processor_read_consistency.py`、`tests/fins/test_fins_storage_provider.py`、`tests/fins/test_sec_pipeline_download.py`）；implementation artifact、controller validation。
- Excluded scope: S1/S3、Host/Engine、R3-E、tool-security、prompt/schema files。
- Parallel review coverage: 无。

## Findings

### 1-未修复-低-_get_or_create_processor 中 FinsSourceDecodeError catch 为死代码

- **入口/函数**: `FinsReadRuntime._get_or_create_processor()` (`dayu/fins/tools/read_runtime.py:2607-2618`)
- **文件(行号)**: `dayu/fins/tools/read_runtime.py:2613`
- **输入场景**: 任意 source 解码失败的 processor 构建路径。
- **实际分支**: `_create_processor()` 在其内部（`:2695-2707`）已经捕获 `FinsSourceDecodeError` 并包装为 `FinsReadBusinessError(ErrorCode.SOURCE_DECODE_FAILED, ...)` 抛出。因此 `_get_or_create_processor` 中的 `except FinsSourceDecodeError` 分支永远不会执行。
- **预期行为**: `_get_or_create_processor` 应只捕获 `_create_processor` 真实可能抛出的异常类型；不保留已被下游包装消除的异常类型。
- **实际行为**: `except FinsSourceDecodeError as exc: raise FinsReadBusinessError(...)` 分支是死代码。
- **直接证据**: `_create_processor():2695-2707` 的 try/except 已将 `FinsSourceDecodeError` 转为 `FinsReadBusinessError`；`_get_or_create_processor():2613` 捕获的 `FinsSourceDecodeError` 永远不会到达。
- **影响**: 维护性。未来修改者可能误认为此 catch 承担实际职责，或在 `_create_processor` 内部修改后忘记同步删除此死分支。
- **建议改法和验证点**: 删除 `_get_or_create_processor():2613-2618` 的 `except FinsSourceDecodeError` 分支。`FinsReadBusinessError` 已由 `_create_processor` 正确抛出，上层 `_invoke_fins_read_business` / `_execute_fins_read_business_value` 会捕获并投影为 tool failure。验证：`pytest tests/fins/test_processor_read_consistency.py::test_read_runtime_maps_invalid_utf8_to_source_decode_failure` 继续通过。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低。

## Open Questions

无。

## Residual Risk

- `errors="ignore"` 在 `dayu/fins/downloaders/sec_downloader.py`（lines 568, 2342, 2392）仍有 3 处匹配。分类：downloader-side auxiliary adapter，不在 S2 source decoder owner 路径内，S2 实现 artifact 已明确记录。
- `content_type` 字段纳入 `SourceDocumentRevision` 计算但不在 Accepted plan 原始列表中。分类：implementation artifact 已记录直接代码证据（storage 用它产生 `Source.media_type`，registry 用 `media_type` 选择 processor），偏差合理。
- `_create_processor` 中新增的 `is_deleted` / `ingest_complete` pre-check（`:2688-2692`）不在 Accepted plan S2 Exact Allowed Changes 中。分类：reasonable defensive addition，不影响 S2 核心 contract。
