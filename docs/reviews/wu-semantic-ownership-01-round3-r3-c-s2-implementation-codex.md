# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S2 Implementation Report

- status: pass
- slice: S2 — Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets
- prerequisite: S1 accepted commit `6e9ad77e`
- implementation owner: AgentCodex
- commit: 未创建；按要求停在 workspace changes

## 实施动机与 owner 结论

本 slice 的问题成立：upload、generic download 与 CN/HK download 在 S1 前后的旧 caller 代码仍存在“部分路径才开 batch”“operation error 与 commit error 共用 token 清空技巧”“CN/HK 在异步 generator 的多个 yield/await 之间逐步写 staging/blob/final meta”三类 owner 漂移。它们会使 caller 无法兑现“单文档 mutation 要么全部可见、要么保持旧状态/absence”的承诺。

本次没有把 rollback 或补偿删除放到下游 adapter。唯一 owner 分工如下：

- storage owner 继续拥有 token、`COMMITTED` commit point、pre-commit recovery 与 commit 后 cleanup 语义；S2 caller 从调用 `commit_batch()` 开始即放弃 token 所有权。
- upload、generic download 与 CN/HK single-filing caller 各自拥有 operation 边界，并只在 commit 尚未开始时 rollback。
- `DownloadedReportAsset` 类型 owner 位于 `cn_download_models.py`，直接承诺 `pdf_bytes`；downloader 不再通过临时路径交接所有权。
- `commit_cn_filing_source_document()` 只负责 caller batch 内的 final meta 与 processed marker staging，不创建第二个 commit owner。

## 生产代码改动

### Upload 与 generic download caller batch

- `dayu/fins/pipelines/docling_upload_service.py`
  - 所有 non-delete create/update/overwrite mutation 无条件开启一个 caller-owned document batch。
  - 文件读取、校验与 Docling conversion 仍在 batch 外完成。
  - `_acknowledge_source_before_blob_write()`、所有 blob、final meta 位于同一 batch。
  - `_acknowledge_source_before_blob_write()` contract 明确只复用 active batch，不 begin/commit/rollback。
  - operation exception、取消结果和同步 cancellation 在 commit 前通过 `finally` rollback；commit 调用开始后不再 caller rollback。
  - operation 与 rollback 双失败时为 primary exception 增加 recovery-evidence note，并以 rollback error 为 cause 重新抛出 primary。
- `dayu/fins/ingestion_runtime.py`
  - generic downloaded document 的 reset/source/blob/processed mutation 保持在一个 caller batch。
  - 使用相同的 operation/commit token 生命周期；commit failure 不触发 invalid-token 二次 rollback。

### CN/HK 单 filing 原子提交

- `dayu/fins/pipelines/cn_download_filing_workflow.py`
  - network download、既有 blob 复用读取、Docling conversion 与所有 progress yield 均位于 batch 外。
  - normal path 在一个同步、无 `yield`/`await` 的 commit 段中完成 reset、ack、PDF blob、Docling blob、final source meta、processed marker 和唯一 commit。
  - PDF-SHA skip path 也在 caller-owned batch 内调用 final helper 并唯一 commit。
  - operation exception、`asyncio.CancelledError` 与 CN cancellation 在 commit 前 rollback；commit failure 不 caller rollback。
  - generator 在 pre-commit progress yield 被 inner/outer close 时尚未持有 token，因此不留下 partial document。
- `dayu/fins/pipelines/cn_download_source_upsert.py`
  - 仅补充 helper contract：必须在 caller active batch 内执行，不能 begin/commit/rollback。

### Temp-less asset contract

- `dayu/fins/pipelines/cn_download_models.py`
  - `DownloadedReportAsset.pdf_path: Path` 改为 `pdf_bytes: bytes`，未提供兼容 property。
- `dayu/fins/pipelines/cn_download_protocols.py`
  - discovery/downloader protocol 明确直接返回已校验 PDF bytes。
- `dayu/fins/downloaders/cninfo_downloader.py`
- `dayu/fins/downloaders/hkexnews_downloader.py`
  - 保持既有 HTTP request、URL、redirect、TLS、`response.content` 读取与 PDF 校验逻辑不变。
  - 删除 `tempfile`、临时目录、临时路径写入与 unlink handoff；直接构造 bytes asset。

## 测试覆盖

修改仅发生在计划允许的 S2 test files。新增或迁移的 owner-level assertions 覆盖：

- upload create final failure 后 source/blob absence；update 与 overwrite final failure 后旧 meta/blob 不变。
- upload ack、original/docling blob、final meta 使用同一 token，且只有 caller 一次 commit。
- upload commit failure 不 caller rollback；operation 与 rollback 双失败保留 primary/note/cause。
- generic download create failure保持 absence；overwrite failure 保持旧目标和非目标文档；commit failure 不 caller rollback。
- CN/HK replacement 的 reset → ack → PDF blob → Docling blob → final meta → processed marker → commit 使用同一 token。
- CN/HK PDF-SHA skip 的 final helper 使用一个 caller batch。
- CN/HK replacement final failure 恢复旧 source 与旧 blobs；success 后 final source、新 blobs 与 processed marker 同时可见。
- CN/HK PDF download 与 Docling conversion exception 均发生在 batch 外并保持 document absence。
- active batch 内同步抛出的 `asyncio.CancelledError` rollback 恰好一次。
- CN/HK commit failure不 caller rollback，也不投影 filing success。
- inner 与 outer generator close 发生在 pre-commit yield 时不创建 partial document。
- CNInfo/HKEX `pdf_bytes`、SHA-256 与 `content_length` 一致；相关 fixtures/constructors 均迁移到 bytes contract。

## 验证结果

### 限定测试

```text
pytest tests/fins/test_docling_upload_service.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_pipeline.py tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py -q
194 passed, 3 warnings in 5.01s
```

warnings 均为现有 `edgar` 依赖 deprecation warnings，与本 slice 无关。

### 全量类型检查

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### Diff check

```text
git diff --check
pass
```

### Plan contract scans

```text
rg -n "NamedTemporaryFile|dayu_cn_downloads|dayu_hk_downloads|pdf_path" dayu/fins/downloaders dayu/fins/pipelines tests/fins
```

无命中。

```text
rg -n '\bDownloadedReportAsset\b|\.pdf_path\b|pdf_path[[:space:]]*[:=]' dayu/fins tests --glob '*.py'
```

仅命中合法类型定义、imports、返回类型和说明文本；无 `.pdf_path`、`pdf_path:` 或 `pdf_path=` 命中。

```text
rg -n 'DownloadedReportAsset[[:space:]]*\(' dayu/fins tests --glob '*.py'
```

命中 2 个 production constructor 与 4 个 test fixture constructor；逐项检查均传入 `pdf_bytes=`。

## README 决策

- `dayu/fins/README.md`: 本 slice 触及 Fins 内部 atomicity 与 asset contract，通常会触发职责检查；但 accepted plan 的 PF-09 强制规定 doc sync 只能在 S1、S2、S3 全部 production slices land 后执行。本次按用户明确范围不修改，并留待 S3 完成后的统一 doc sync。
- `tests/README.md`: 新增测试仍位于既有 `tests/fins/` 层级，测试运行方式与维护规则未变化，不满足该 README 的更新边界，因此不修改。
- 根 README、design 与 control docs：没有用户可见入口、分层关系或 control 状态变更，且当前 slice 明确禁止修改。

## 未覆盖风险

- Docling conversion 仍通过线程执行同步第三方代码，线程执行中不能强制中断；本 slice 的保证是 conversion 在 batch 外，因此延迟取消不会产生 partial storage state。
- `DownloadedReportAsset` 现在以内存 bytes 交接。远端下载 byte budget 属于明确延期的 tool-security WU，本 slice 未引入上限或读取策略。
- commit point、orphan recovery 与 post-commit cleanup 的 durable correctness 继续由已 accepted S1 storage tests 和 owner contract承担；S2 只验证 caller 不越权补偿或二次 rollback。

## 工具安全未实施

本 S2 未实现任何工具安全项，也未修改 LLM-facing 文本/schema。以下项目仍明确 deferred：

- upload allowlist、user-file authority、explicit file authority 与 symlink-safe upload source policy；
- URL、TLS、redirect、SSRF 与 provenance policy；
- remote download byte-budget policy；
- LLM-facing upload/download security schema、prompt 或 tool schema 变化。

本次仅删除 CN/HK 临时 PDF handoff；`local://` 或 storage identity 不被扩展为 upload/file authority 安全策略。
