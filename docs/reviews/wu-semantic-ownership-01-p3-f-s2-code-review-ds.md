# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-F S2

## Scope

- Mode: current changes (unstaged + uncommitted, since `42ea9c21`)
- Branch: `phaseflow/host-issues-control`
- Base commit: `42ea9c21` (P3-F S1 completion)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s2-code-review-ds.md`
- Included scope: 10 files (+843/-18)
- Excluded scope: untracked files per handoff
- Parallel review coverage: 无（单 reviewer 走读全部 S2 改动）

## Verdict

**PASS** — S2 正确实现了 plan 中定义的 blob acknowledgement 和 explicit staging source contract。blob repository 写入边界、upload staging、SEC stream/legacy staging、staging-to-completion stable field protection 均落在正确的 owner boundary。未发现 correctness 或 architecture defect。

---

## Findings

### 1-未修复-低-`run_download_single_filing_stream` 中 `source_handle` 立即被覆盖

- **入口/函数**: `run_download_single_filing_stream` (`dayu/fins/pipelines/sec_download_filing_workflow.py:412-419`)
- **文件(行号)**: `dayu/fins/pipelines/sec_download_filing_workflow.py:412`
- **输入场景**: 所有 SEC 单 filing 下载路径（stream + legacy）。
- **实际分支**: 行 412 构造 `SourceHandle(ticker=..., document_id=..., source_kind=SourceKind.FILING.value)`；行 419 立即用 `stage_downloaded_filing_source_document(...)` 的返回值覆盖同一变量。行 412 的赋值从未被读取。
- **预期行为**: 移除无效的首个赋值，或将其下移到 staging 调用之后仅作为 fallback。
- **实际行为**: 死代码赋值。不影响运行时 correctness——两处构造的 `SourceHandle` identity 相同——但增加了维护者的理解成本。
- **直接证据**: 
  - 行 412: `source_handle = SourceHandle(ticker=ticker, document_id=document_id, source_kind=SourceKind.FILING.value)` 
  - 行 419: `source_handle = stage_downloaded_filing_source_document(...)`
  - 行 440: `store_file=host._build_store_file(source_handle=source_handle)` — 使用行 419 的值
- **影响**: 仅代码可读性；无运行时影响。
- **建议改法和验证点**: 删除行 412-416 的首个 `source_handle` 赋值。验证：现有 SEC 测试全部通过。
- **修复风险（低）**: 改动一行，不影响行为。
- **严重程度（低）**:

## Owner Boundary Assessment

逐项对照 plan S2 要求的 owner boundary：

| 边界 | Owner | S2 实现 | 证据 |
| --- | --- | --- | --- |
| Blob 写入前 source meta 必须存在 | Blob repository | `store_file(SourceHandle, ...)` 在 `_build_store_key` / `put_object` 前调用 `_get_handle_meta(handle)` | `_fs_blob_core.py:144-145` |
| 拒绝不存在 source meta 的 blob 写入 | Blob repository | `_get_handle_meta` 在 meta_path 不存在时抛 `FileNotFoundError`；`put_object` 不会被调用 | `_fs_blob_core.py:144-145` + `_fs_storage_infra` 中 `_get_handle_meta` 实现 |
| Upload 在首个 blob 写入前 staging | Pipeline → Source repository | `_acknowledge_source_before_blob_write` → `stage_source_document` 在 `for asset in pending_assets` 循环之前 | `docling_upload_service.py:260-268` |
| SEC stream 在 downloader callback 前 staging | Pipeline → Source repository | `stage_downloaded_filing_source_document` 在 `download_stream_func(...)` 调用前 | `sec_download_filing_workflow.py:419-430` |
| SEC legacy 路径也在 downloader 前 staging | Pipeline → Source repository | 同上——`stage_downloaded_filing_source_document` 在 stream/legacy 分支前，两种路径均受保护 | `sec_download_filing_workflow.py:419`（分支前） |
| Staging-to-complete 稳定字段不可改写 | Source repository | `_staging_completion_stable_fields_match` 在 `_upsert_source_document` 中校验 | `_fs_source_document_core.py:781-786` |
| Completion 可补充 staging 时未知的 stable 字段 | Source repository | `_staging_completion_stable_fields_match` 中 `if not existing_has_value: continue` | `_fs_source_document_core.py:1116-1118` |
| Incomplete source 不进入 read/list | Read runtime (S1) | S2 测试验证 `_collect_source_documents_by_kind` 排除 `fil_incomplete` | `test_fins_storage_provider.py:1059-1061` |
| CN staging 不回归 | CN pipeline (S1 invariant) | CN workflow 测试通过，CN 的 `_build_base_meta` 通过 `FinsSourceProvider.from_storage_value` 校验 provider | Controller validation + `test_cn_download_workflow.py` |

## Propagation Audit

按 plan 要求逐层验证 source → blob → completion → read 的语义一致性：

1. **Producer**: SEC pipeline (`stage_downloaded_filing_source_document` + `_build_downloaded_filing_meta_payload`)、upload pipeline (`_acknowledge_source_before_blob_write` + `_build_upsert_meta`) — ✅ 均通过 source repository staging 写入 `ingest_complete=False` + 有效 `source_provider` / `ingest_method`。

2. **Blob write guard**: `FsDocumentBlobRepository.store_file(SourceHandle, ...)` — ✅ 在 `put_object` 前通过 `_get_handle_meta(handle)` 读取 source meta；meta 不存在时抛 `FileNotFoundError` 且不创建文件。`ProcessedHandle` 不受影响（无 isinstance guard）。

3. **Completion guard**: `_upsert_source_document` 在 is_create 遇到已有 incomplete staging 时允许继续（staging-to-complete），但通过 `_staging_completion_stable_fields_match` 禁止改写 staging 已声明的 stable 字段 — ✅。Mismatched `source_fingerprint` 在 `test_stage_source_document_lifecycle_and_blob_acknowledgement` 中被拒绝。

4. **Read projection**: S1 已实现的 `_build_citation` 拒绝 `ingest_complete=False` ；S2 测试验证 `_collect_source_documents_by_kind` 也排除 incomplete — ✅。

5. **LLM-facing output**: 无新增 citation 路径，未引入内部治理标识到 LLM 上下文 — ✅。

## Adversarial Failure Pass

- **`store_file(SourceHandle)` 前 source meta 被并发删除**: TOCTOU 窗口——`_get_handle_meta` 通过后、`put_object` 执行前 source meta 可能被另一进程删除。plan 已接受为 residual risk。✅ 已知 residual。
- **Staging 成功后进程崩溃（blob 未写入）**: 留下 `ingest_complete=False` + `files=[]` 的 staging meta。read runtime 排除该文档；后续重试可复用 staging。✅ 正确。
- **Upload final upsert 失败（`test_execute_upload_final_upsert_failure_keeps_acknowledged_staging`）**: 留下 incomplete staging + blob 文件。blob 在 acknowledged source 下，非 ownerless。✅ 正确。
- **SEC 下载失败后无 staging meta（`FailingStreamStubDownloader`）**: staging 在下载前写入，失败后 staging meta 存在（`ingest_complete=False`）；测试的 fallback 路径（`if failed_meta is None: manual staging`）对边缘情况做防御。✅ 正确。
- **Retry 复用匹配 incomplete staging 并完成（`test_failed_sec_download_leaves_incomplete_staging_and_retry_completes`）**: ✅ 正确。
- **Completion 稳定字段冲突**: `source_fingerprint` 从 `"fingerprint-v1"` 改为 `"fingerprint-v2"` 被 `_staging_completion_stable_fields_match` 拒绝。✅ 正确。
- **`_acknowledge_source_before_blob_write` 在 `previous_meta` 存在但 `ingest_complete` 缺失时**: 使用 `bool(previous_meta.get("ingest_complete", False))` → 进入 staging 分支 → `stage_source_document` 内 `SourceDocumentProvenance.from_meta(existing_meta)` 对缺失 `ingest_complete` 抛 `KeyError`（S1 fix）。fail-closed，但错误消息来自 repository 层而非 upload 层。边缘情况，正常路径不受影响。

## New Defect Scan

对 S2 新增/修改的全部生产代码逐行走读：

- **`_fs_blob_core.py:144-145`**: `isinstance(handle, SourceHandle)` 后调用 `_get_handle_meta(handle)` 在文件写入前。`ProcessedHandle` 不受影响。✅
- **`_acknowledge_source_before_blob_write`**: 在 `previous_meta is None or not ingest_complete` 时 staging；`staging_meta = dict(meta)` 避免修改上游 dict。✅
- **`stage_downloaded_filing_source_document`**: 在 `previous_meta` 存在且完成时返回直接构造的 `SourceHandle`（无需 staging）；否则通过 `_build_downloaded_filing_meta_payload` 构建 staging meta。✅
- **`_staging_completion_stable_fields_match`**: 只校验 staging 已声明（非空）的字段；允许 completion 补充 staging 时未知的字段。与 `_staging_stable_fields_match`（用于 staging 重入）语义不同但互补。✅
- **`_upsert_source_document` 中 `is_create and meta_exists` 分支**: 原逻辑抛 `FileExistsError`；S2 改为仅当 `ingest_complete=True` 时抛，incomplete 时允许继续（staging-to-complete）。✅
- **`_upsert_source_document` 中 `not is_create` 分支**: 新增 `previous_meta.get("ingest_complete") is False` 检测，捕获 update 路径的 staging-to-complete 场景。红线检查 `previous_provenance.ingest_complete` 与 `previous_meta.get("ingest_complete") is False` 结果一致（belt-and-suspenders）。✅

## Test Coverage

| 测试 | 覆盖场景 | 断言 |
| --- | --- | --- |
| `test_stage_source_document_lifecycle_and_blob_acknowledgement` | staging→blob→completion 全生命周期 | blob 拒绝 missing source；staging 幂等；completion stable 冲突拒绝；completed 后 staging 拒绝 |
| `test_execute_upload_stages_source_before_first_blob_write` | upload create staging 时序 | `stage` 事件先于 `store` 事件；blob 写入时 meta 为 incomplete |
| `test_execute_upload_final_upsert_failure_keeps_acknowledged_staging` | upload 失败后 blob 不 orphan | staging meta 保持 incomplete；blob 文件在 staging source 下可见 |
| `test_download_stream_stages_source_before_blob_write` | SEC stream staging 时序 | `stage` 事件先于 `store` 事件 |
| `test_download_legacy_path_stages_source_before_blob_write` | SEC legacy 路径 staging 时序 | `stage` 事件先于 `store` 事件 |
| `test_failed_sec_download_leaves_incomplete_staging_and_retry_completes` | SEC 失败→重试 全流程 | 失败后无 completed meta；重试复用 staging；completion 成功 |
| `test_read_runtime_citation_rejects_incomplete_source_meta` (updated) | read runtime 排除 incomplete | `_collect_source_documents_by_kind` 不包含 `fil_incomplete` |

## Open Questions

无。

## Residual Risk

- **TOCTOU race**: `_get_handle_meta` 与 `put_object` 之间 source meta 可能被并发删除。plan 已接受为 residual risk（当前 Host 单 storage assembly 运行）。
- **CN staging 对齐**: CN 路径的 `update_cn_staging_source_document` 和 completion 逻辑未在本次 S2 中大规模重构；CN workflow 测试通过，但 CN staging 与 `stage_source_document` 的完整语义对齐（特别是 completion stable field protection）可能在边缘场景下有差异。S2 测试覆盖了通用 `_upsert_source_document` 路径的 staging-to-completion 保护，CN 最终 commit 走同一代码路径。
- **Coverage 未测量**: pytest-cov 本地不可用（同 S1），66 测试通过 + pyright 零报错，但单文件覆盖率百分比未知。
- **Stale staging cleanup**: 下载失败后的 incomplete staging meta 无自动清理机制。plan 将物理清理标记为 P3-F 非必需项。
