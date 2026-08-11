# WU-CLI-DOWNLOAD-01 Slice 4 Implementation

- 基线：`afde13dfeeb50f18bb35364ee15d8dcd23a7bcc2`
- 时间：`2026-08-10 08:57:24 +08:00`
- 结论：implementation / validation PASS，停在 MiMo / DS 双路 code review 入口。
- Git：未 commit、未 push、未创建或修改 PR。

## 1. Scope / allowlist

实际修改 production 文件：

- `dayu/fins/downloaders/sec_downloader.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_download_persistence.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_sc13_filtering.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/storage/source_integrity.py`（新增）
- `dayu/fins/storage/__init__.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_source_document_core.py`

实际修改 tests：`test_sec_downloader.py`、`test_sec_pipeline_download.py`、`test_sec_pipeline_download_stream.py`、`test_cn_download_workflow.py`、`test_fins_storage_atomicity.py`、`test_fins_storage_provider.py`。临时脚本只位于 `workspace/tmp/wu_cli_download_01_slice4_static_gate.py`。

以上均在 effective allowlist 内。除本 artifact 外，没有修改 README、base plan、v1/v2 amendment、evidence/review artifacts、Oracle/registry、真实 CLI/provider、Host/Engine 或 PR 190。

## 2. 逐需求实现

### Storage concurrency / integrity

- `_fs_storage_infra.py:450,480,1261-1280` 实现 per-ticker `Condition` reservation；后 writer等待统一 release/`notify_all`，不再 fail-fast。
- 正常 writer在 `_fs_storage_infra.py:1512` blocking acquire且无业务 timeout；recovery在 `:1877` 保持 `blocking=False` try-lock。
- commit/rollback/begin failure/exception统一消费 file lock与local reservation并notify；publication guard只覆盖短 validation/swap。
- `SourceIntegrityStatus` 封闭为 `MISSING / COMPLETE / REPAIR_REQUIRED`；physical missing、size mismatch、digest mismatch使用typed reasons。
- Protocol `repository_protocols.py:575-642`、wrapper `fs_source_document_repository.py:511-588`、core `_fs_source_document_core.py:427-566` 同步实现 published、staged、whole-ticker inventory。
- whole-tree inventory在一个 publication guard内覆盖 filing+material；malformed sha256由 `_fs_source_document_core.py:636-641` 按 strict结构错误处理，不进入repair fallback，validator未放宽。
- pure preflight区分 clean、唯一selected repair、multiple、unselected/material、selected-rejected；全部错误原因typed且path-free。

### SEC transport / Phase A-B / rejection

- `SecDownloader.prefetch_files_stream` 只产生模块私有 discriminated variants：started、non-empty immutable bytes、304 skipped、failure；无 batch/repository/store callback。
- `materialize_prefetched_event` 是 private prefetch到 `DownloaderEvent`/store callback的唯一 materializer。
- `download_files_stream` 只组合 shared prefetch core + materializer；`download_files` 聚合前者。无 replay/prepared callable/fake capability/compat seam。
- SEC Phase A在 `sec_download_filing_workflow.py:230-266`；`COMPLETE + overwrite=False` 零target HTTP。repair在 `:480-483` 强制 `allow_not_modified=False`，与request overwrite独立。
- prefetch完整返回后才在 `:492` begin；`:494` staged classification是首个target operation。identity变化先rollback并丢弃旧payload，最多三轮；`overwrite=True`不被latest COMPLETE转成skip。
- rejected persistence在 `sec_download_persistence.py:226` 完整prefetch，`:237` begin，`:247` materialize；artifact+`registry_after` 使用同一真实batch。
- prefetch返回后/begin前cancel、200/304/empty/failure、shared-core integration与async-generator `aclose()` finalization均有owner test。

### SEC whole-tree / SC13 / 6-K

- `sec_sc13_filtering.py:40-87` 使用accepted、rejected-with-artifact、registry-only、already-registered variants；selection无batch/persistence/registry mutation。
- decision cache以exact accession为key，并在 `sec_sc13_filtering.py:496-501` 校验cached filing accession identity；生命周期仅为单次top workflow。
- `sec_download_workflow.py:560-595` 完成最终accepted/rejected partition、whole-tree preflight与stable repair-first。
- repair terminal成功后在 `:685-691` 再做whole-tree preflight，随后才在 `:695-707` 进入company/deferred rejection publication。
- company batch在 `:814-826`；SC13 artifact+registry使用persistence batch，listing/transport失败才按既有policy走 `:863-877` registry-only durable unit；无无条件尾部maintenance batch。
- selected repair 6-K若Phase A policy拒绝，在rejected persistence前抛 `SELECTED_REJECTED_REPAIR_REQUIRED`，source/company/artifact/registry全部保持old。

### CN repair-first

- `cn_download_workflow.py:211-236` 在company mutation前完成selection、whole-tree preflight与stable repair-first；post-repair clean gate为 `:326-345`。
- company identity复用 `ticker_to_company_id` owner，provider company id独立保存。
- `cn_download_filing_workflow.py:164-199` Phase A `COMPLETE + overwrite=False` 零PDF/Docling I/O；PDF `:107/216`、Docling `:302` 均在 begin `:563` 前。
- `REPAIR_REQUIRED` 仅在新PDF SHA与旧meta一致时锁外复用旧Docling bytes；publication仍用assets batch完整重写PDF+Docling tree。删除了Phase A完整态短路后已不可达的metadata-only skip分支。
- begin后的首个target operation是 staged classification `:566`；identity变化/latest policy skip先rollback，三轮耗尽抛typed revision conflict。
- repair transport/Docling失败由single-filing真实失败终态唯一投影；top workflow直接中止，old target/company保持不变。
- no-filing+corruption在company前以 `UNSELECTED_REPAIR_REQUIRED` fail closed；clean no-filing仍提交company。

## 3. Durable / race 矩阵

| 场景 | 结果 |
|---|---|
| selected size/digest/physical missing | SEC/CN unconditional repair；strict materialized snapshot可读后才允许company/rejection |
| multiple corruption | mutation前 `MULTIPLE_REPAIR_REQUIRED`，全部old |
| unselected/material/no-filing corruption | mutation前 `UNSELECTED_REPAIR_REQUIRED`，全部old |
| selected-then-rejected 6-K | persistence前 `SELECTED_REJECTED_REPAIR_REQUIRED`，全部old |
| SC13 artifact成功 | artifact+registry同一batch完整发布 |
| SC13 artifact transport失败 | repair/company gate后仅registry-only durable unit |
| repair transport/conversion失败 | filing owner失败终态并中止；target/company/rejection old |
| cancel after prefetch/before begin | begin/materializer/commit/rollback均0 |
| same-target双overwrite | 两者成功；后writer丢弃旧prefetch、重新获取，最终last-writer |
| different-target同ticker | B从latest staging复制A，最终A/B union |
| malformed sha256 | strict结构错误，不调用repair/provider |

## 4. Inventory / call graph

Production独立 `SourceDocumentRepositoryProtocol` implementer只有 `FsSourceDocumentRepository`（`fs_source_document_repository.py:221`），委托 `_FsSourceDocumentCore`。test implementer均继承wrapper：`_CountingSourceRepository`（read runtime/provider各一）、`_RevisionProbeRepository`、`_SpyUploadSourceRepository`、`_BatchIdentityCnSourceRepository`、`_SpySourceRepository`。full pyright确认没有漏实现、fake default或compat shim。

`DownloadFilesStream`完整枚举：production prefetch/materializer/stream/aggregate定义与组合在 `sec_downloader.py:1548,1673,1743,1773,1786,1816`；production prefetch消费者仅 `sec_download_filing_workflow.py:480` 与 `sec_download_persistence.py:226`；tests中真实stream消费点位于 `test_sec_downloader.py:863,921,994,1247,1325,1402,1491,2276,2343`，其余命中为typed fake定义。

人工展开（结合rg/AST/pyright/barrier，不声称形式化reachability proof）：

- 普通SEC：top preflight `sec_download_workflow.py:560-595` → Phase A `sec_download_filing_workflow.py:230` → prefetch `:480` → begin/staged `:492-494` → materialize `:569` → commit `:725`。
- SEC rejected：prefetch `sec_download_persistence.py:226` → cancel gate → begin `:237` → materialize `:247` → artifact+registry → commit `:300`；batch内无transport。
- SEC repair-first：target terminal `sec_download_workflow.py:650-684` → post inventory `:685-691` → company/deferred mutations `:695-707`。
- CN：PDF/Docling锁外 → begin/staged `cn_download_filing_workflow.py:563-566` → reset/store/upsert → commit `:679`。
- company：SEC `sec_download_workflow.py:814-826`、CN `cn_download_workflow.py:400-435`，均只从whole-tree gate后可达。
- unified release：`_fs_storage_infra.py:1261-1280,1328-1329`。

## 5. Validation commands / results

全部命令先执行 `source .venv/bin/activate`；以下均exit 0。

- Owner storage：`pytest -q tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py --disable-warnings` → `254 passed, 3 warnings in 26.36s`。
- Affected coverage union：`coverage run -m pytest tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_runtime.py tests/fins/test_cn_download_workflow.py tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_processor_read_consistency.py tests/fins/test_docling_upload_service.py -q --disable-warnings` → `592 passed, 3 warnings in 38.51s`。
- Base §9 aggregate原命令（21个文件，从 `tests/cli/test_arg_parsing.py` 至 `tests/fins/test_docling_upload_service.py`）→ `1387 passed, 3 warnings in 43.96s`。
- 10次deterministic repeat原命令（SEC pipeline、stream、CN workflow、storage atomicity）→ 最终代码态第1–10轮各 `326 passed`，约16.09–16.18s。
- process/recovery subset另跑10次（cross-process blocking、recovery nonblocking、same-core notify、independent-core blocking）→ 每轮 `4 passed`，约1.81–1.89s。
- `python workspace/tmp/wu_cli_download_01_slice4_static_gate.py` → `PASS: Slice 4 AST/static syntax gates（非形式化 reachability proof）`。
- `python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- `python -m ruff check <22 changed Python/static files>` → `All checks passed!`。
- `python -m ruff format --check <22 changed Python/static files>` → `22 files already formatted`。
- `python -m compileall -q dayu tests`、两条 `python -m json.tool ... >/dev/null`、`git diff --check` → 全部exit 0。

静态脚本 SHA-256：`38e1e1d5827eb81bb5ffd7d75dd434e83d0037ff049a7fd1dfb8fab32181481f`。测试使用Event/Barrier/Pipe与bounded test deadline；没有sleep猜时序或production timing hook。3条warning均为第三方`edgar` deprecation warning。

## 6. Per-production-file coverage

同一affected coverage data逐个执行 `coverage report --include=<file> --fail-under=80`：

| File | Coverage |
|---|---:|
| `downloaders/sec_downloader.py` | 92% |
| `pipelines/cn_download_filing_workflow.py` | 85% |
| `pipelines/cn_download_workflow.py` | 87% |
| `pipelines/sec_download_filing_workflow.py` | 84% |
| `pipelines/sec_download_persistence.py` | 80% |
| `pipelines/sec_download_source_upsert.py` | 97% |
| `pipelines/sec_download_workflow.py` | 86% |
| `pipelines/sec_pipeline.py` | 84% |
| `pipelines/sec_sc13_filtering.py` | 82% |
| `storage/__init__.py` | 100% |
| `storage/_fs_source_document_core.py` | 84% |
| `storage/_fs_storage_infra.py` | 87% |
| `storage/fs_source_document_repository.py` | 97% |
| `storage/repository_protocols.py` | 100% |
| `storage/source_integrity.py` | 88% |

15/15实际修改production文件均达到 `>=80%`。

## 7. 陈旧 pytest PID 4270

- 只读复核：PPID `62192`、elapsed `01:55:55`，命令为 `.venv/bin/pytest -q tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py`。
- 裁决：早期仍含fail-fast expectation的测试运行遗留，明显悬挂；不计入任何PASS、测试数或耗时。
- 在FINAL_REPEAT结束后仅向精确PID `4270`发送`TERM`；随后 `ps -p 4270`为空。
- 清理后原两文件针对性回归为 `254 passed in 26.36s`；最终 `ps` 未发现pytest进程。

## 8. Residual risk / next gate

- AST不能形式化证明Python动态调用图；可信证据由完整rg inventory、AST、full pyright、人工逐路径与deterministic barriers共同构成。
- `sec_download_persistence.py` coverage恰为80%，已满足硬门；code review应继续重点检查304/partial failure/rollback/cancel与artifact+registry atomicity。
- 未执行真实provider/真实CLI/Oracle/registry mutation，属于明确forbidden boundary。
- README按总控要求留到四slices后的docs closeout；临时static脚本位于gitignored `workspace/tmp/`，不进入commit。

当前停止在原 MiMo / DS 双路 code review 入口；review与总控裁决前不commit、不push、不创建PR。
