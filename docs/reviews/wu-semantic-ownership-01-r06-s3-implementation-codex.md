# WU-SEMANTIC-OWNERSHIP-01 / R06-S3 implementation（Codex）

## 1. Gate 结论

状态：`READY_FOR_CONTROLLER_REVALIDATION`。

本次是同一 umbrella WU 的 R06-S3 breaking cutover implementation gate；用户已接受 goal、R06 plan 与 S1/S2 checkpoints，不是新 WU。实现停在当前累计工作树，未 stage、commit、push、创建 PR，也未修改 control/design/reviewer/controller artifacts。

S3 唯一目标已经闭合：所有 production mutation 都要求显式 keyword `batch=`，只有 top-level publication unit 拥有 begin/commit/rollback；真实 callback 在每次 invocation 显式接收同一 `BatchToken`；四个真实 composition root 首次装配 production `FsBatchingRepository` 并与 source/blob/processed/company/maintenance wrappers 共用同一 repository set/core；CN、SEC、Docling producer 使用 blob-first、一次 final complete-source publication，旧 acknowledgement、ambient/auto batch、stable re-entry 与 false completion producer 均已删除。

## 2. 第一性原理与直接调用图

### 2.1 动机成立

S2 后的 full pyright 108 项与 aggregate acknowledgement residual 不是独立 storage/read 缺陷，而是同一 breaking contract 尚未传播到真实 producer/callback/composition 的直接结果：producer 仍从 source facade 取得 lifecycle、mutation 缺 required `batch=`、callback 没有 invocation-time token、四个 composition root 没有 shared batching wrapper，部分 flow 仍先建立半完成 source 再写 blob。若在 adapter、fixture或单入口加 optional batch/facade，会形成第二 mutation authority，不能满足 accepted design。

代码直接调用图与 accepted plan §7.3 closed allowlist 一致，没有发现需要扩域的 production/test owner。唯一基于调用图收紧的旧 seam 是 SEC rejected persistence：真实 production composition 只传 `download_files_stream`，因此删除 optional legacy download fallback，改为 required exact stream protocol；未保留 compatibility branch。

### 2.2 四个真实 composition root

| Root | 直接装配 | shared-core 证明 |
| --- | --- | --- |
| `DefaultFinsRuntime.create` / `service_runtime.py` | 一次 `build_fs_repository_set`，创建 `FsBatchingRepository` 及 source/blob/processed/company/maintenance wrappers | 所有 wrappers 注入同一 `repository_set`；runtime public batch 开启后可由其它 wrapper mutation并共同 commit。 |
| `CnPipeline.__init__` | production default 首次创建 batching wrapper | CN source/blob/processed/company/maintenance 全部复用同一 set；download、upload、rebuild 从 pipeline batching owner 取得 token。 |
| `SecPipeline.__init__` | production default 首次创建 batching wrapper | SEC source/blob/processed/company/maintenance 全部复用同一 set；filing/rejection/cleanup/upload/rebuild 共用该 core。 |
| `reconcile_active_6k_primary_documents` | standalone 入口一次创建 set、batching/source/blob/processed | 每个 6-K 的 source primary 更新与 processed reprocess marker 使用同一 token；测试通过 fresh wrapper 读取共同 durable 结果。 |

测试注入 seam 不替代上述 production default composition。没有在测试、单一 CLI 入口或 compatibility factory 中伪造 shared core。

### 2.3 Callback authority

`StoreDownloadedFile` 的精确 contract 是 `(filename, stream, *, batch: BatchToken) -> FileObjectMeta`。`SecDownloader.download_files_stream(..., *, batch)` 在每次文件写入 invocation 都执行 `store_file(..., batch=batch)`；persistence builder只绑定 source identity/repository，不 capture token。`DownloadFilesStream` 同样要求 keyword-only batch，SEC normal filing、rejected filing 与 6-K flow 都由当前 top-level owner在调用点传入 token。不存在 ContextVar、task/thread identity、ambient owner、auto batch或隐藏 authority facade。

## 3. Authored paths

### 3.1 Production（22 个，精确等于 plan §7.3）

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/downloaders/sec_downloader.py`
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_company_meta.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py`
- `dayu/fins/pipelines/sec_company_meta.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_download_persistence.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_download_state.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_rebuild_workflow.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/upload_company_meta.py`

### 3.2 Tests（12 个有净 S3 diff，均在 §7.3 matrix）

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_docling_upload_service_integration.py`
- `tests/fins/test_sec_downloader.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/tools/test_combined_tools_acceptance.py`

完整 13-file producer matrix 还执行了未产生净 S3 diff 的 `tests/fins/test_sec_pipeline_upload_material_stream.py`。S1/S2 四个 storage/read tests 只保留累计 accepted required-signature fixture/complete-publication migration；本 gate 没有重写它们的 validator、authority、read、recovery product owner。Controller follow-up 要求的两个 `ingest_complete=False` rejection literal 已显式保留，没有改写成 `bool(0)`。

### 3.3 README 与 artifact

- `dayu/fins/README.md`
- `tests/README.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s3-implementation-codex.md`

根 `README.md`、`dayu/README.md`、`docs/fins/design.md` 无 diff。进入 S3 前已有的 S1/S2 storage/control/review dirty paths原样保留；本 gate未修改 control、design、reviewer或controller artifacts。

## 4. Transaction owner 表

| Publication unit | 唯一 lifecycle owner | 同 token mutation / 边界 |
| --- | --- | --- |
| Default ingestion source document | `FsFinsIngestionRuntime` 单文档 owner | reset（若覆盖）→全部 blobs→一次 final source create；commit前异常一次 rollback，commit调用开始后不回滚。 |
| Default ingestion rejected artifact | rejection persistence owner | rejected blobs/artifact/registry在短 batch 内；取消/失败在commit前一次 rollback。 |
| Default preprocess document | preprocess 单文档 owner | processed create/update在一个短 batch；每个文档独立。 |
| CN company meta | `run_cn_download_stream_impl` | company upsert单独短 transaction；不与 filing 跨 transaction rollback。 |
| CN/HK filing | `run_cn_download_single_filing_stream` | batch外下载/Docling convert；batch内 reset（若有）→PDF/Docling blobs→一次 final source→processed marker；PDF-SHA skip只在独立短 batch 更新一次完整 source/marker。 |
| CN upload company | `CnPipeline` upload composition | company meta独立 transaction。 |
| 每个 CN Docling upload document | `CnPipeline` top-level per-document owner | `DoclingUploadService` 只消费 token；reset/delete 或全部 blobs→一次 final source；一个文档失败不回滚已成功 company/其它 document。 |
| CN rebuild | `rebuild_cn_download_artifacts` 单 source owner | source final update与已有 processed `reprocess_required=True` 同一 token。 |
| SEC company meta | `run_download_stream_impl` | company upsert独立短 transaction。 |
| SEC normal/6-K filing | `run_download_single_filing_stream` | downloader invocation逐文件显式同 token；准备全部 file facts，6-K 在 final source前从捕获 payload选择 primary；最后一次 source create/update，并在需要时同 token标记 processed。 |
| SEC rejected filing | `persist_rejected_filing_artifact` | rejected blobs、artifact、registry同一短 transaction。 |
| SEC maintenance | `run_download_stream_impl` | stale cleanup是独立 publication unit，不与 company/filing共用 owner。 |
| SEC upload company | `sec_upload_workflow` | company meta独立 transaction。 |
| 每个 SEC Docling upload document | `sec_upload_workflow` top-level per-document owner | service helper只消费 token；blob-first、一次 final source，文档间不跨 transaction rollback。 |
| SEC rebuild | `rebuild_single_local_filing` | source final update与已有 processed marker同一 token。 |
| standalone 6-K reconcile | `reconcile_active_6k_primary_documents` 每 source owner | source primary update与 processed marker同一 token。 |

所有 owner tests 都断言 begin/commit/rollback count、helper/callback token equality、failure/cancel exactly-once rollback，以及 commit failure后的 caller rollback count为0。CN company/document、SEC company/filing/maintenance与Docling per-document boundaries均有独立 publication/失败隔离证据。

## 5. Producer publication contract

- `SourceHandle` 只表达 blob identity，不表达 mutation authority；所有 source/blob/processed/company/maintenance mutation 必须显式 `batch=`。
- 新文件路径先准备全部 blobs，再执行一次 final source create/update；commit前 published read仍 absent/old，commit后 meta/files/blob/primary/provenance/manifest共同可见。
- 覆盖路径可以在同一 batch reset旧目标，但不发布 `ingest_complete=False`，不调用 `stage_source_document`，不保留 stable re-entry或 false acknowledgement。
- SEC 6-K 不通过 published API读取尚未commit的 staging source；downloader只在本次 invocation向 payload sink提供候选 bytes，primary选择完成后才发布 final source。
- rebuild与6-K在同一 batch更新 source和已存在的 processed marker，避免新 source facts与旧 processed derived state分裂。
- preprocess selection不再用 `meta.get("ingest_complete", True)` 把缺失完成事实当作完成态；只接受 published meta显式 `is True`，没有 downstream completion fallback。
- mutation protocol没有 optional/default batch；SEC persistence没有 legacy downstream fallback；tests/fakes实现当前 public contract，没有 old facade/shim。

## 6. Tests 与 aggregate 验证

### 6.1 Accepted focused commands

| Gate | 精确 plan command结果 |
| --- | --- |
| §7.1 S1 | `134 passed, 64 deselected, 3 warnings in 3.57s` |
| §7.2 S2 | `91 passed, 144 deselected, 3 warnings in 2.98s` |
| §7.3 S3 13-file matrix | Controller validation fix 后为 `319 passed, 1 skipped, 3 warnings in 13.63s`；最终 coverage session同样为 `319 passed, 1 skipped`。 |

### 6.2 Full Fins + combined acceptance

命令：

```text
.venv/bin/python -m pytest -q tests/fins tests/tools/test_combined_tools_acceptance.py
```

Controller validation fix 后最终结果：`723 passed, 1 skipped, 3 warnings in 21.90s`。

三条 warning 均来自 `edgar` 依赖的既有 deprecated import，不是 R06 代码 warning。S3 matrix 的唯一 skip 是既有可选 Docling integration 环境门控。

### 6.3 Fresh filesystem crash/concurrent-reader smoke

从 `tests/fins/test_fins_storage_atomicity.py` 在 fresh `tmp_path` 运行 recovery phase、new-source absent recovery、长 staging/validator reader、两次 publication rename barrier、composed read/`LocalFileSource.open()` 自死锁保护：`10 passed, 97 deselected in 2.17s`。

S1 focused command还覆盖 minimal journal、跨 core/process lock、pre/post-commit failure与全部 orphan recovery phase；在线 reader只观察完整 old/new，未观察 missing/mixed。

## 7. S3逐文件 line coverage

同一完整 §7.3 producer matrix执行 `coverage run --branch`，再从 JSON 按 `(num_statements - missing_lines) / num_statements` 计算 statement line coverage；没有用 branch综合百分比、overall、omit或mock-only delegation冒充逐文件结果。

| File | Covered / statements | Line coverage |
| --- | ---: | ---: |
| `dayu/fins/ingestion_runtime.py` | 1526 / 1690 | 90.30% |
| `dayu/fins/service_runtime.py` | 90 / 106 | 84.91% |
| `dayu/fins/downloaders/sec_downloader.py` | 789 / 864 | 91.32% |
| `dayu/fins/pipelines/cn_download_protocols.py` | 40 / 40 | 100.00% |
| `dayu/fins/pipelines/cn_download_company_meta.py` | 26 / 28 | 92.86% |
| `dayu/fins/pipelines/cn_download_workflow.py` | 195 / 238 | 81.93% |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | 191 / 218 | 87.61% |
| `dayu/fins/pipelines/cn_download_rebuild.py` | 132 / 164 | 80.49% |
| `dayu/fins/pipelines/cn_download_source_upsert.py` | 73 / 78 | 93.59% |
| `dayu/fins/pipelines/cn_pipeline.py` | 274 / 326 | 84.05% |
| `dayu/fins/pipelines/docling_upload_service.py` | 313 / 372 | 84.14% |
| `dayu/fins/pipelines/sec_6k_primary_document_repair.py` | 148 / 181 | 81.77% |
| `dayu/fins/pipelines/sec_company_meta.py` | 42 / 45 | 93.33% |
| `dayu/fins/pipelines/sec_download_filing_workflow.py` | 127 / 147 | 86.39% |
| `dayu/fins/pipelines/sec_download_persistence.py` | 100 / 122 | 81.97% |
| `dayu/fins/pipelines/sec_download_source_upsert.py` | 39 / 39 | 100.00% |
| `dayu/fins/pipelines/sec_download_workflow.py` | 150 / 169 | 88.76% |
| `dayu/fins/pipelines/sec_download_state.py` | 119 / 148 | 80.41% |
| `dayu/fins/pipelines/sec_pipeline.py` | 332 / 379 | 87.60% |
| `dayu/fins/pipelines/sec_rebuild_workflow.py` | 111 / 131 | 84.73% |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 109 / 129 | 84.50% |
| `dayu/fins/pipelines/upload_company_meta.py` | 57 / 61 | 93.44% |

最低值为 `sec_download_state.py` 的 80.41%，22个文件全部 `>=80%`。

## 8. Typing 与 Ruff

### 8.1 Pyright

命令：`.venv/bin/pyright`。

最终结果：`0 errors, 0 warnings, 0 informations`。S2 checkpoint的 108 项 producer/callback/test propagation residual已在本 gate真实清零，没有 ignore、cast绕过或留给后续 finding。

### 8.2 Scoped Ruff

对 `git diff --name-only --diff-filter=ACMRT 9c07b88d -- '*.py'` 的全部累计 changed Python执行 Ruff：`All checks passed!`。

### 8.3 Full Ruff六字段/fingerprint

只读 current full命令 `.venv/bin/python -m ruff check dayu tests utils`：152项，分布 `E402=66, F401=72, F541=3, F821=1, F841=10`；changed owner/test命中0。

为避免只按数量比较，从 accepted base SHA `9c07b88d` 解包只读 tree并以同一配置生成 JSON。按 normalized path、rule、row、column、message fingerprint 比较：base=162，current=152，`current-only=0`，`base-only=10`。十条 base-only 精确等于 plan §10登记的十条 changed-file lint finding；其中两条 storage finding已由累计 S1/S2清除，其余七条 F401与一条 F841由S3清除。其余152条 path/rule/location/message与base完全一致，因此没有新增、扩散、节点漂移或指纹变化，也未清理无关文件。

## 9. §8.3 scans 与人工调用审计

### 9.1 Exact scans

| Scan | 结果 | 归属 |
| --- | ---: | --- |
| ambient authority | 0 | storage/tests无 ContextVar、task/thread identity、owner token context或auto batch。 |
| production acknowledgement/false completion | 0 | `dayu/fins` 无 stage source、stable staging fields、acknowledge source或 false-completion producer。 |
| aggregate acknowledgement/false completion | 2 | 仅 `test_fins_storage_provider.py:1444` 与 `:3478` 的 intentional rejection literal，见下节。 |
| lifecycle exact scan | 283（production 78） | production 3条是 batching wrapper到core；其余production命中全部属于§4 top-level owner；test命中是public owner contract与fixture setup/teardown。 |
| mutation exact scan | 183（production 54、tests 129） | AST逐个 call核对 `missing_explicit_batch_keyword=0`。 |
| optional/default batch signature | 0 | plan生产路径、repository protocols/wrappers中没有 batch default。 |
| journal locator scan | 128 | physical path命中只在 private `_ActiveBatchState`、storage内部恢复逻辑与owner tests；public token/journal payload不含 locator。 |

### 9.2 Controller follow-up：显式 false rejection literals

1. `test_final_source_rejects_false_completion_without_publication` 的 `meta["ingest_complete"] = False` 通过真实 public `create_source_document(..., batch=batch)` 进入 source mutation validator，断言 `ValueError("ingest_complete 必须为 true")`，随后 rollback并证明 published source absent。
2. `test_complete_source_validator_consumes_token_and_preserves_old[false_completion]` 在唯一 active staged tree中显式写 `meta["ingest_complete"] = False`，只调用真实 `commit_batch` validator，断言 commit拒绝、token已消费且old source/blob不变。

两条 literal 都只进入 owner-level rejection case，不是 producer、ack path、fixture completion或兼容输入。保留显式 `False` 是测试意图与 scan证据的一部分；没有用 `bool(0)` 掩盖。

### 9.3 Lifecycle/mutation人工归属

- lifecycle protocol只在 `BatchingRepositoryProtocol`，production wrapper只在 `FsBatchingRepository`；source/blob/processed/company/maintenance wrappers不暴露 lifecycle。
- §4表中的每个 production begin都有同 scope commit或precommit rollback；commit前的异常/取消只执行一次 rollback。CN filing使用 preserving-primary rollback helper；SEC filing在 commit前把 token保持open，进入commit前先移交/清空caller token；其它 owner将 commit放在 rollback try/finally之外或用 `commit_started` fence，commit调用开始后不二次 rollback。
- 54个 production mutation与129个test mutation逐个 AST核对都含显式 keyword `batch=`；pyright required signatures进一步证明 callback/fake/fixture没有漏传。
- helper/callback只传递 owner token，不调用 lifecycle；token ticker/cross-core/open-state仍由累计 S1 storage owner验证。

### 9.4 Journal/public token

`BatchToken` 精确只有 `transaction_id` 与 `ticker`。journal payload精确只有 `transaction_id/ticker/phase`；`owner_pid`、`hostname` 为0命中。`target_ticker_dir/staging_root_dir/staging_ticker_dir/backup_dir/journal_path` 只存在于 private `_ActiveBatchState`和 recovery owner/test，未进入 public token或journal JSON。

## 10. README 决策

已先完整读取两份 README 的 `Agent更新约束`，再按 plan §9更新 current truth：

- `dayu/fins/README.md`：写明 explicit `BatchToken`、batching-only lifecycle、required mutation batch、callback invocation-time token、shared core、published-only reads、blob-first、complete-source final-once、writer mutex、短 publication guard与crash recovery；删除旧 acknowledgement/ambient owner/staging-source叙述。
- `tests/README.md`：只记录当前 suite对 explicit authority、complete publication、rollback/commit fence、online rename barrier与fresh recovery的覆盖，不记录 gate/review过程。
- 根 README没有用户命令、安装、输出、workspace或排障变化；`dayu/README.md`没有分层变化；两者均无 diff。
- `docs/fins/design.md` owner决策未改变，无 diff。

## 11. 安全、不变量与非目标

下列既有安全机制保持：路径 component/containment校验、symlink/escape拒绝、SEC downloader DNS/peer校验、resource budget与下载限流、atomic file replace/fsync、writer/recovery process fencing、独立 publication lock、lock order、minimal journal、orphan recovery、primary error优先及post-commit cleanup语义。没有以 batching cutover为由删除或弱化任何机制。

本 gate没有进入 R07 snapshot/revision/opaque identity，没有实施 Issue 142/151/175/177/178，没有建立统一 tool authorization，没有修改 Host/Engine/UI分层或其它业务 owner。

## 12. Controller validation fix：R06-S3-CV-F01

状态：`已修复`。

### 12.1 Finding 与 owner判断

Controller指出 `_select_preprocess_documents` 已从 `meta.get("ingest_complete", True)` 收紧为 `meta.get("ingest_complete") is True`，但缺少“字段缺失即 fail closed”的直接 owner contract test。finding成立：storage validator拥有新 publication完整性，但 ingestion preprocess selection仍独立拥有“哪些 published source 可以进入预处理工作集”的选择语义，因此该新增分支必须在 `ingestion_runtime` owner test中固定。

### 12.2 Fix

只在既有 allowlist path `tests/fins/test_fins_ingestion_runtime.py` 新增一个测试 `test_preprocess_selection_rejects_missing_completion_and_keeps_complete_source`；production、storage validator、fixture helper、README与其它 tests均无 fix diff。

测试先通过真实 shared-core repository完整发布一个 10-K 与一个 10-Q source，确认二者 published meta原本都含显式 `ingest_complete=True`；随后仅在测试中删除 10-Q published `meta.json` 的该字段，模拟持久态损坏。测试通过真实 source repository读回一个显式完成 meta与一个字段缺失 meta，再直接调用 selection owner，断言结果精确只含完成态 10-K。没有构造兼容 fake/shim，没有放宽或绕过 commit validator，也没有启动 mutation transaction来混淆 selection证据。

### 12.3 Revalidation

| Validation | Result |
| --- | --- |
| finding owner test | `1 passed, 3 warnings in 0.79s` |
| 完整 §7.3 S3 matrix | `319 passed, 1 skipped, 3 warnings in 13.63s` |
| S3 coverage matrix | `319 passed, 1 skipped`；22 files全部 `>=80%` |
| coverage minimum | `sec_download_state.py` 119/148 = 80.41% |
| affected production coverage | `ingestion_runtime.py` 1526/1690 = 90.30% |
| aggregate Fins + combined acceptance | `723 passed, 1 skipped, 3 warnings in 21.90s` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| cumulative changed Python scoped Ruff | `All checks passed!` |

README触发复核：新增 test只补既有 preprocess selection fail-closed coverage，不改变 test suite职责或 production current contract，因此 `tests/README.md` 与 `dayu/fins/README.md` 不需追加 F01 过程叙述。

## 13. Residual

R06-S3 correctness residual：无。

明确保留给既有 owner且不影响本 gate correctness的后续范围只有：

- R07 独占的跨多次 read snapshot/revision/opaque identity、retry/cache contract；
- Issue 142/151/175/177/178 各自已登记 owner；
- 统一 tool authorization（本 gate明确非目标）。

full Ruff剩余152项是 base `9c07b88d` 可逐字段复现、且完全不命中 cumulative changed paths的既有 baseline，不是新增 S3 residual或豁免。当前工作树保持未提交，等待 Controller revalidation。
