# WU-SEMANTIC-OWNERSHIP-01 / R06 Completion Handoff — AgentCodex

## 1. Gate 身份、状态与写边界

- **umbrella WU**：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- **internal remediation sub-WU**：R06 Fins 显式 transaction 与 complete-source publication；不是新 WU，不是 R07。
- **当前 gate**：R06 completion handoff artifact-only gate。
- **状态**：R06 final implementation tree 已由双路完整 re-review 与 Controller 接受并形成 accepted implementation commit；本 artifact 已完成，等待 Controller validation。
- **本 gate 唯一写入**：`docs/reviews/wu-semantic-ownership-01-r06-completion-codex.md`。
- **既有有意状态**：`docs/host/issues-implementation-control.md` 在本 gate 开始前已有 Controller 修改，记录 `R06 completion handoff`、accepted implementation commit 与下一入口；本 gate 未覆盖、回滚或改写该状态。
- **明确未做**：未修改 product、tests、README、design、control 或任何既有 artifact；未重跑已接受的产品测试矩阵；未 stage、commit、push、创建或修改 PR；未进入 R07 plan/implementation，也未进入 Issue 142/151/175/177/178 或统一 tool authorization。

第一性原理判断仍成立：旧实现同时以 public token、ambient task/thread identity 与 source incomplete acknowledgement 表达同一个 transaction authority / staging fact，且两次 rename 的在线空窗不能由 crash recovery 事后补救。R06 的正确 owner 是 `dayu.fins.storage`：显式 capability、active registry、complete-source validator、writer mutex、短 publication guard、journal/recovery 与 published read/open 必须在同一 storage boundary 闭合；当前 accepted tree 已在该边界完成修复，不需要下游 fallback、兼容 shim 或 R07 提前实现。

## 2. Accepted SHA、transition base 与提交关系

| fact | exact SHA | 核验结果 |
| --- | --- | --- |
| R06 accepted plan commit | `0d802220fd1ca4ec67addc85915df27becc9b594` | commit subject `docs: accept R06 Fins transaction remediation plan`；父提交 `9c07b88d9e855f19f0b828f671022119cc5599a1` |
| accepted plan content SHA-256 | `ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43` | 从 accepted plan commit 中的 plan 文件直接计算；与最终 plan re-review Controller 记录一致 |
| R06 transition base | `d048adf7ec1135aaf575384432ebf1137f8a34f2` | R06-S1 implementation gate transition commit |
| R06 accepted implementation commit | `4f417e916043ac981d86e113702e010699017ad9` | commit subject `fins: accept R06 transaction remediation`；父提交与 merge-base 均精确为 transition base `d048adf7...` |
| accepted implementation tree | `4a7df7583fd2e836bfdf9d07f7486d583596e75f` | `d048adf7... -> 4f417e91...` 为单一 88-file exact-scope transaction，`16729 insertions / 3614 deletions` |

Accepted plan commit 的 plan/evidence/control 闭集为：

- `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`
- `docs/reviews/wu-semantic-ownership-01-r06-plan-entry-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-rereview-controller-adjudication.md`
- 当时同步的 `docs/host/issues-implementation-control.md` 状态。

## 3. Accepted implementation commit 最终 allowlist

以下清单直接来自 `git diff --name-status d048adf7... 4f417e91...`，不是根据 plan 文件名推测。

### 3.1 Production：38 files

- `dayu/fins/domain/document_models.py`
- `dayu/fins/downloaders/sec_downloader.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/cn_download_company_meta.py`
- `dayu/fins/pipelines/cn_download_filing_workflow.py`
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_download_rebuild.py`
- `dayu/fins/pipelines/cn_download_source_upsert.py`
- `dayu/fins/pipelines/cn_download_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py`
- `dayu/fins/pipelines/sec_company_meta.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_download_persistence.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/sec_download_state.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_rebuild_workflow.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/upload_company_meta.py`
- `dayu/fins/service_runtime.py`
- `dayu/fins/storage/_fs_blob_core.py`
- `dayu/fins/storage/_fs_company_meta_core.py`
- `dayu/fins/storage/_fs_maintenance_core.py`
- `dayu/fins/storage/_fs_processed_core.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/storage/_fs_storage_infra.py`
- `dayu/fins/storage/_fs_storage_utils.py`
- `dayu/fins/storage/fs_batching_repository.py`
- `dayu/fins/storage/fs_company_meta_repository.py`
- `dayu/fins/storage/fs_document_blob_repository.py`
- `dayu/fins/storage/fs_filing_maintenance_repository.py`
- `dayu/fins/storage/fs_processed_document_repository.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/local_file_source.py`
- `dayu/fins/storage/repository_protocols.py`

### 3.2 Tests：16 files

- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_docling_upload_service_integration.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_storage_atomicity.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- `tests/fins/test_sec_downloader.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/tools/test_combined_tools_acceptance.py`

### 3.3 README：2 files

- `dayu/fins/README.md`
- `tests/README.md`

### 3.4 Implementation/review/fix/validation artifacts：31 files

- `docs/reviews/wu-semantic-ownership-01-r06-s1-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-validation-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-code-review-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s2-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s2-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s2-code-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s2-code-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s2-code-rereview-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s3-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r06-s3-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-fix-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-rereview-ds.md`
- `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-rereview-controller-adjudication.md`

### 3.5 Control state：1 file

- `docs/host/issues-implementation-control.md`：accepted implementation commit 中同步了最终 R06 evidence；commit 后 Controller 又有意把 gate 推进到 completion handoff并记录真实 commit SHA。该 post-commit dirty state不属于 product contract，本 gate原样保留。

总计：`38 production + 16 tests + 2 README + 31 artifacts + 1 control = 88 files`；其它 path 为零。

## 4. 最终 public transaction contract

### 4.1 `BatchToken` public shape

`dayu.fins.domain.document_models.BatchToken` 的 public shape 精确为：

```text
transaction_id: str
ticker: str
```

- `transaction_id` 是 storage 生成、格式不承诺的 opaque bearer identity；opaque 不表示字段对 holder 隐藏。
- token 不包含 owner token/scope、task/thread、PID、hostname、时间、Path、lock、phase、staging/target/backup/journal locator。
- authority 不来自 dataclass object identity或字段 grammar，而来自当前 shared core 的 active registry：unknown/altered/closed/ticker-mismatch/cross-core token 均在同一 resolver fail closed；合法 token 可显式转交 helper、child task 或 thread。

### 4.2 Lifecycle 唯一 owner

只有 `BatchingRepositoryProtocol` 声明：

```text
begin_batch(ticker: str) -> BatchToken
commit_batch(batch: BatchToken) -> None
rollback_batch(batch: BatchToken) -> None
recover_orphan_batches(*, dry_run: bool = False) -> tuple[str, ...]
```

`SourceDocumentRepositoryProtocol` 不再声明或 facade-forward lifecycle。`commit_batch` 调用开始后由 storage 消费 capability；caller 不二次 rollback。普通 pre-commit operation/cancellation rollback exactly once；operation 与 rollback 双失败时 operation/cancellation 保持 primary，rollback 成为 cause。

### 4.3 所有 public mutation required-batch signatures

下表是最终闭集；每个 `batch` 都是 keyword-only、required、non-optional且无默认值。

| protocol | final mutating signature |
| --- | --- |
| `CompanyMetaRepositoryProtocol` | `upsert_company_meta(meta: CompanyMeta, *, batch: BatchToken) -> None` |
| `SourceDocumentRepositoryProtocol` | `create_source_document(req: SourceDocumentUpsertRequest, source_kind: SourceKind, *, batch: BatchToken) -> DocumentHandle` |
|  | `update_source_document(req: SourceDocumentUpsertRequest, source_kind: SourceKind, *, batch: BatchToken) -> DocumentHandle` |
|  | `delete_source_document(req: SourceDocumentStateChangeRequest, *, batch: BatchToken) -> None` |
|  | `reset_source_document(ticker: str, document_id: str, source_kind: SourceKind, *, batch: BatchToken) -> None` |
|  | `restore_source_document(req: SourceDocumentStateChangeRequest, *, batch: BatchToken) -> DocumentHandle` |
|  | `replace_source_meta(ticker: str, document_id: str, source_kind: SourceKind, meta: DocumentMeta, *, batch: BatchToken) -> None` |
| `ProcessedDocumentRepositoryProtocol` | `create_processed(req: ProcessedCreateRequest, *, batch: BatchToken) -> DocumentHandle` |
|  | `update_processed(req: ProcessedUpdateRequest, *, batch: BatchToken) -> DocumentHandle` |
|  | `delete_processed(req: ProcessedDeleteRequest, *, batch: BatchToken) -> None` |
|  | `clear_processed_documents(ticker: str, *, batch: BatchToken) -> None` |
|  | `mark_processed_reprocess_required(ticker: str, document_id: str, required: bool, *, batch: BatchToken) -> None` |
| `DocumentBlobRepositoryProtocol` | `delete_entry(handle: SourceHandle | ProcessedHandle, name: str, *, batch: BatchToken) -> None` |
|  | `store_file(handle: SourceHandle | ProcessedHandle, filename: str, data: BinaryIO, *, batch: BatchToken, content_type: str | None = None, metadata: dict[str, str] | None = None) -> FileObjectMeta` |
| `FilingMaintenanceRepositoryProtocol` | `clear_filing_documents(ticker: str, *, batch: BatchToken) -> None` |
|  | `save_download_rejection_registry(ticker: str, registry: DownloadRejectionRegistry, *, batch: BatchToken) -> None` |
|  | `store_rejected_filing_file(ticker: str, document_id: str, filename: str, data: BinaryIO, *, batch: BatchToken, content_type: str | None = None, metadata: dict[str, str] | None = None) -> FileObjectMeta` |
|  | `upsert_rejected_filing_artifact(req: RejectedFilingArtifactUpsertRequest, *, batch: BatchToken) -> RejectedFilingArtifact` |
|  | `cleanup_stale_filing_documents(ticker: str, *, batch: BatchToken, active_form_types: set[str], valid_document_ids: set[str]) -> int` |

唯一 transaction-internal public read 是：

```text
has_staged_filing_xbrl_instance(ticker: str, document_id: str, *, batch: BatchToken) -> bool
```

其它 public reads 只读 published tree，不接受 optional batch，不因 caller 是 active writer 而路由 staging。

### 4.4 已删除的 authority / acknowledgement contracts

以下语义已从 production owner 与 producer/callback 调用链删除：

- `_BATCH_OWNER_CONTEXT`、`ContextVar`、`asyncio.current_task()`、thread identity、`owner_token`、`owner_scope_id` 与 caller-stack/ambient authority。
- `_execute_with_auto_batch()`、无 token 自动 begin/commit、active caller 自动加入 transaction。
- Source repository 的 begin/commit/rollback facade 与 compatibility forwarding。
- `stage_source_document()`、`_STAGING_STABLE_META_FIELDS`、stable re-entry、preliminary source create、source-meta staging acknowledgement。
- producer 写 `ingest_complete=false`、空 files/primary后再 final update 的流程。
- blob write 必须先读取 source incomplete meta 的前置条件。
- callback capture/bind batch；SEC downloader/persistence callback 的 batch 在每次 invocation 以 required keyword显式传入。

`ingest_complete=True` 仍是 completed published source 的业务事实；最终 production 中 `False` 为零，两个 `False` literal 只存在于 storage validator negative owner tests，不能解释为兼容输入或 staging 状态。

## 5. Shared-core composition 与真实 publication owners

四个 production composition root 精确为：

```text
DefaultFinsRuntime.create              dayu/fins/service_runtime.py
CnPipeline                            dayu/fins/pipelines/cn_pipeline.py
SecPipeline                           dayu/fins/pipelines/sec_pipeline.py
standalone 6-K reconcile              dayu/fins/pipelines/sec_6k_primary_document_repair.py
```

每个 root 只创建一个 `_FsRepositorySet`，并从同一 set/core 装配 `FsBatchingRepository` 与 source/blob/processed/company/maintenance wrappers。没有从 source facade 反射、cast、拆出或重建 batching core；来自另一 core 的 token 即使 workspace/ticker 相同也被 resolver拒绝。

真实 publication-unit 边界：

- ingestion download/rejected artifact/preprocess：各自 top-level helper拥有 begin/commit/rollback；helper/callback显式消费同 token。
- CN/SEC company meta：各自是短 transaction；每个 filing/document另有独立短 transaction；远端 discovery/下载/Docling不被错误包进 whole-ticker transaction。
- Docling upload：`DoclingUploadService` 只消费 caller batch；company meta成功而单 document失败是分离、可重试 publication，不跨 transaction rollback。
- SEC maintenance registry + stale cleanup：同一 maintenance transaction；rejected artifact、rebuild与 6-K repair各在其 owner内终结 capability。
- rebuild/6-K 的 source update与 processed reprocess marker使用同一 batch；SEC staged XBRL判断只走 required-batch staged read。

## 6. Complete-source publication、journal、recovery 与 reader contract

### 6.1 Blob-first / final-once 与 validator

- producer可直接用 `SourceHandle(ticker, document_id, source_kind)` 在 open transaction staging先写 blob；handle只表达 identity，`batch` 才是 authority。
- CN、SEC、Docling均在 blob准备完后只执行一次 final source create/update/replace；没有 preliminary/incomplete source业务记录。
- `commit_batch` 在取得 publication guard或触碰 published target前，固定遍历**完整 staged ticker tree**；不维护 touched identities/set，也不把 validation复制给 producer、reader或fixture。
- validator至少校验：source目录/meta identity；`ingest_complete is True`；typed ingest method/provider provenance；非空、无重复 files manifest；name/URI/size/sha与 contained、non-symlink regular file一致；`primary_document` 非空且精确命中manifest/物理文件；source↔physical files与 filing/material source↔manifest双向一致。
- validator不从 processed/company/maintenance consumers反推source完整性；这些 mutation只要求位于同一 staging ticker tree。
- 缺 meta、空/重复/dangling files、缺失或错配 primary、非法 provenance、false completion、manifest单边项、symlink/escape 均在 target rename前 fail closed；storage消费 token并保留 old/absent published state。

### 6.2 Writer mutex 与 publication swap guard

- `batch_locks/<ticker>.lock`：跨进程 writer transaction/ticker mutex，从 begin 持有到 commit/rollback终态，只排除同 ticker第二 writer；持锁不授予 mutation authority，也不阻塞 published reader。
- `batch_locks/<ticker>.publication.lock`：独立、按 ticker分片的跨进程短 guard，只覆盖 commit/recovery会触碰 target/backup/staging 的物理切换/失败恢复，以及一次 published meta/list/bytes I/O或 `LocalFileSource.open()` 的 fd open。
- 唯一锁序：writer/recovery mutex先，publication guard后；释放反序。published reader只取 publication guard，不反向获取 writer mutex。
- public read outer entry只取一次 guard并委托 private unguarded helper；没有 ambient“已持锁”标记、public-to-public重入或兼容参数。
- Fins `LocalFileSource` 使用 storage-owned delayed opener：`Source.open()` 获取 guard，fd成功打开或失败后释放；成功 fd固定于 old或new文件，后续读取不长期持锁。

### 6.3 Journal、commit point 与 recovery

- journal payload精确为 `{transaction_id, ticker, phase}`；不含 PID、hostname、时间、绝对路径、lock或物理 locator。
- phase保留 `started`、`backed_up_target`、`swapped_target`、`committed`、`rolled_back`。
- `COMMITTED` journal是唯一 commit point；`SWAPPED_TARGET` 即使物理 rename已完成仍是 pre-commit rollback state。首次发布在 `SWAPPED_TARGET` crash 后恢复为 absent，是 accepted contract，不得提前视为 committed。
- recovery从固定 roots与受控 identity重建路径，重新做 ticker、containment、symlink、phase与字段闭集校验；先 writer mutex、物理恢复短窗再 publication guard。
- invalid ticker、非法字段或不可解析 journal 均 fail closed并保留 evidence；不可解析 JSON只捕获当前 entry 的 `ValueError`，同轮后续合法 orphan继续恢复；真实 `OSError`不被吞掉。
- atomic JSON、file-store atomic replace、directory rename与 parent-directory fsync保留。COMMITTED后的 cleanup/publication/writer release failure不回滚 durable new truth；primary/secondary error precedence由 storage owner稳定表达。

### 6.4 Online old/new 与 crash-phase test contract

Accepted evidence覆盖三类不能互相替代的测试：

1. **long staging / validator**：writer只持长 writer mutex；独立 process/core published reader及时完成并只读完整 old，证明长下载、Docling、staging与validator没有误持publication guard。
2. **two rename barriers**：分别停在 `target -> backup` 与 `staging -> target` 真实 barrier；reader在真实 publication-lock acquire seam发同步信号，parent以同一锁 non-blocking contention证明 writer确实持 guard。reader不能提前返回 missing/half，释放后只见完整 old/new。
3. **crash phases**：fresh `tmp_path`、真实 filesystem与 child hard exit覆盖 started/backed-up/swapped/committed/cleanup-before-finish及 old-absent new source；fresh repository recovery 后只能是完整 old、完整 new，或 precommit首次发布的 absent，不能是混合/半 source。

S3 accepted smoke 对 recovery phase、new-source absent、长 staging/validator、两次 rename、composed read与 delayed open记录 `10 passed, 97 deselected`。累计 fix 又把 rename test收紧到真实 reader acquire seam；最终 direct accepted owner cases为 `11 passed`，不再依赖 `poll(0.25)`、startup-ready或 sleep碰运气。

R06只保证一次 published read/open old-or-new；跨多个 repository calls或 processor lifetime的同版本 snapshot由R07独占，见§10。

## 7. Accepted validation evidence（本 completion gate 未重跑）

以下结果来自已接受的 implementation/controller/fix/re-review artifacts与保留的 coverage JSON；本 artifact gate只做只读一致性核验。

### 7.1 Direct / focused / aggregate tests

| evidence | final accepted result |
| --- | --- |
| cumulative `R06-CR-F01..F04` direct owner cases | `11 passed, 3 warnings` |
| S1 final focused owner matrix after cumulative fix | `137 passed, 64 deselected, 3 warnings` |
| S2 exact focused matrix | `91 passed, 147 deselected, 3 warnings` |
| S3 final producer/callback matrix after cumulative fix | `325 passed, 1 skipped, 3 warnings` |
| full affected `tests/fins` + combined tools acceptance | `732 passed, 1 skipped, 3 warnings` |
| final MiMo/DS re-review independent aggregate | MiMo owner subsets pass；DS复现 `732 passed, 1 skipped, 3 warnings` |

唯一 skip是既有可选 Docling integration环境门控；三条 warning来自既有 `edgar` dependency deprecation，不是R06新增/扩散。

### 7.2 Final 38-file production line coverage

最终 accepted aggregate coverage JSON按 `covered_lines / num_statements` 逐文件核验；全部 `>=80%`，没有用overall、branch综合值、omit、pragma或mock-only delegation替代。

| production file | covered/statements | line coverage |
| --- | ---: | ---: |
| `dayu/fins/domain/document_models.py` | `417/434` | `96.08%` |
| `dayu/fins/downloaders/sec_downloader.py` | `789/864` | `91.32%` |
| `dayu/fins/ingestion_runtime.py` | `1535/1693` | `90.67%` |
| `dayu/fins/pipelines/cn_download_company_meta.py` | `26/28` | `92.86%` |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | `191/218` | `87.61%` |
| `dayu/fins/pipelines/cn_download_protocols.py` | `40/40` | `100.00%` |
| `dayu/fins/pipelines/cn_download_rebuild.py` | `132/164` | `80.49%` |
| `dayu/fins/pipelines/cn_download_source_upsert.py` | `73/78` | `93.59%` |
| `dayu/fins/pipelines/cn_download_workflow.py` | `195/238` | `81.93%` |
| `dayu/fins/pipelines/cn_pipeline.py` | `274/326` | `84.05%` |
| `dayu/fins/pipelines/docling_upload_service.py` | `313/372` | `84.14%` |
| `dayu/fins/pipelines/sec_6k_primary_document_repair.py` | `148/181` | `81.77%` |
| `dayu/fins/pipelines/sec_company_meta.py` | `42/45` | `93.33%` |
| `dayu/fins/pipelines/sec_download_filing_workflow.py` | `127/147` | `86.39%` |
| `dayu/fins/pipelines/sec_download_persistence.py` | `100/122` | `81.97%` |
| `dayu/fins/pipelines/sec_download_source_upsert.py` | `39/39` | `100.00%` |
| `dayu/fins/pipelines/sec_download_state.py` | `119/148` | `80.41%` |
| `dayu/fins/pipelines/sec_download_workflow.py` | `150/169` | `88.76%` |
| `dayu/fins/pipelines/sec_pipeline.py` | `332/379` | `87.60%` |
| `dayu/fins/pipelines/sec_rebuild_workflow.py` | `125/138` | `90.58%` |
| `dayu/fins/pipelines/sec_upload_workflow.py` | `109/129` | `84.50%` |
| `dayu/fins/pipelines/upload_company_meta.py` | `57/61` | `93.44%` |
| `dayu/fins/service_runtime.py` | `91/106` | `85.85%` |
| `dayu/fins/storage/_fs_blob_core.py` | `59/64` | `92.19%` |
| `dayu/fins/storage/_fs_company_meta_core.py` | `115/119` | `96.64%` |
| `dayu/fins/storage/_fs_maintenance_core.py` | `140/148` | `94.59%` |
| `dayu/fins/storage/_fs_processed_core.py` | `109/116` | `93.97%` |
| `dayu/fins/storage/_fs_source_document_core.py` | `340/397` | `85.64%` |
| `dayu/fins/storage/_fs_storage_infra.py` | `733/817` | `89.72%` |
| `dayu/fins/storage/_fs_storage_utils.py` | `163/184` | `88.59%` |
| `dayu/fins/storage/fs_batching_repository.py` | `17/18` | `94.44%` |
| `dayu/fins/storage/fs_company_meta_repository.py` | `18/18` | `100.00%` |
| `dayu/fins/storage/fs_document_blob_repository.py` | `20/20` | `100.00%` |
| `dayu/fins/storage/fs_filing_maintenance_repository.py` | `29/29` | `100.00%` |
| `dayu/fins/storage/fs_processed_document_repository.py` | `26/26` | `100.00%` |
| `dayu/fins/storage/fs_source_document_repository.py` | `74/77` | `96.10%` |
| `dayu/fins/storage/local_file_source.py` | `20/20` | `100.00%` |
| `dayu/fins/storage/repository_protocols.py` | `59/59` | `100.00%` |

最低为 `sec_download_state.py 80.41%`，没有低于门槛的 changed production file。

### 7.3 Pyright、Ruff、AST/source/diff scans

| validation | final accepted result |
| --- | --- |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| cumulative changed-Python scoped Ruff | `All checks passed!` |
| full Ruff count/rules | base `162`；current `152`：`E402=66, F401=72, F541=3, F821=1, F841=10` |
| full Ruff delta | `current-only=0`；`base-only=10`，十项精确等于 accepted plan §10 changed-owner旧 finding清理 |
| full Ruff normalized fingerprint | base SHA-256 `94945899fc586cb898354da872ba4e2d9d720920ebc6edfdb8142a4a08c7adaa`；current SHA-256 `5671e8ecabff71c05d5b30a557a0297c19014e0193a1cba2351a0c19cdb0ed23` |
| mutation AST | production `54`、tests `129`、`missing_explicit_batch_keyword=0` |
| ambient authority | `0` |
| production acknowledgement / false completion | `0`；test-only validator negatives `2` |
| optional/default batch | `0` |
| journal process facts | `owner_pid/hostname=0`；physical locator仅private state/recovery/tests |
| obsolete F04 sync | `poll(0.25)`、old startup `ready`、concrete-repository private-set reflection均 `0` |
| deferred-scope scan | cumulative fix未引入revision/snapshot/bounded retry/unified authorization/force-release |
| accepted implementation scope | exact `88` paths；allowlist外 `0` |
| accepted commit staged diff check | commit前 `git diff --check` pass；AgentDS原review artifact的纯格式 trailing whitespace已在commit前移除 |

Lifecycle textual scan最终为 `283`；production命中只属于 batching wrapper/core lifecycle与§5列出的top-level owners。mutation不是靠文本计数宣称正确，而是逐call AST确认required keyword。

### 7.4 README decision

- `dayu/fins/README.md`：已更新为current truth，说明 explicit `BatchToken`、batching-only lifecycle、required mutation batch、callback invocation-time token、shared core、published-only reads、blob-first/final-once、writer mutex、短 publication guard与crash recovery；旧ambient/ack/staging-source叙述删除。
- `tests/README.md`：已更新测试职责，只记录explicit authority、complete publication、rollback/commit fence、online rename barrier与fresh recovery，不记录gate过程。
- 根 `README.md`：无安装、初始化、CLI/Web/WeChat入口、命令参数、输出、日志、workspace或用户工作流变化；无diff。
- `dayu/README.md`：`UI -> Service -> Host -> Engine` 分层与装配关系未变；无diff。
- `docs/fins/design.md`：stable owner truth未变；无diff。
- cumulative fix只增强既有contract错误分支和test seam，没有触发追加README/design改动。

## 8. R06 finding 最终 ledger

### 8.1 Plan review / re-review

| finding/group | final disposition |
| --- | --- |
| `R06-PF-01` 独立跨进程短 publication guard | **accepted / CLOSED** |
| `R06-PF-02` `materialize()` residual交给R07，R06不发明新contract | **accepted / CLOSED** |
| `R06-PF-03` callback invocation-time required batch | **accepted / CLOSED** |
| `R06-PF-04` full staged-tree validator + bidirectional manifest | **accepted / CLOSED** |
| `R06-PF-05` S1即删除implicit/ambient authority | **accepted / CLOSED** |
| `R06-PF-06` CN company与Docling document分离短transaction | **accepted / CLOSED** |
| `R06-PF-07` 四个roots新装配shared-core `FsBatchingRepository` | **accepted / CLOSED** |
| `R06-PF-08` 三slice累计reviewability、无magic行数/中间accepted commit | **accepted / CLOSED** |
| 仅进程内publication lock；ambient/reentrant held marker；R06改造`materialize()`；禁止非authority `partial`；固定约1500行gate | **rejected，均未实施** |
| MiMo `R06-REREVIEW-001..003` | **no-action**；accepted plan已覆盖 |
| DS `R06-REREVIEW-R01` public-read inventory | **no-action**；plan已有全称contract |
| DS `R06-REREVIEW-R02` standalone 6-K再加同义迁移句 | **rejected-as-new-finding**；plan已精确规定 |
| DS `R06-REREVIEW-R03` 两个`LocalFileSource`预防性注释/补丁 | **rejected-as-current-finding**；无生产re-wrap证据 |

Plan最终：8 accepted closed、current accepted 0、product question 0、blocker 0。

### 8.2 R06-S1

| finding/group | final disposition |
| --- | --- |
| `R06-S1-VF-01` malformed recovery ticker阻断同轮恢复 | **accepted / CLOSED**；invalid evidence保留，后续合法orphan继续 |
| `R06-S1-VF-02` touched contract中文Args/Returns/Raises不完整 | **accepted / CLOSED**；15个S1 production owner AST gap为0 |
| `R06-S1-VF-03` writer release覆盖commit/rollback primary | **accepted / CLOSED**；primary identity保留 |
| `R06-S1-VF-04` COMMITTED publication-release failure静默成功 | **accepted / CLOSED**；durable truth不回滚，post-commit error显式返回 |
| `R06-S1-CR-F01` maintenance read缺private unguarded helper | **accepted / CLOSED** |
| `R06-S1-CR-F02` processed meta docstring虚构fallback | **accepted-deduplicated / CLOSED**；DS F01/F03同root cause |
| `R06-S1-CR-F03` reprocess marker core返回`bool`漂移 | **accepted / CLOSED**；protocol/wrapper/core统一`None` |
| MiMo O-02 | **later approved slice**；S2 ack contract当时的intentional residual，最终S2/S3已删除 |
| MiMo O-03/O-04 | **no-fix observation**；窄private state/path仅服务owner failure injection |
| MiMo O-05/O-06 | **no-fix observation**；既有failure injection/Event barrier有直接验证目的 |
| MiMo O-07/O-08 | **no-fix observation**；不为test maintenance抽新framework |
| MiMo O-09 | **rejected-as-finding/no-action**；无当前guard release缺陷证据 |
| DS sequencing residual 1/2 | **covered by S2/S3**；最终均关闭 |
| DS `previous_primary: Any` residual | **rejected/out-of-scope**；既有未触及JSON boundary，无当前授权 |

S1最终：`VF-01..04`与`CR-F01..03`全部closed；new accepted 0、blocker 0、无中间commit。

### 8.3 R06-S2

| finding/group | final disposition |
| --- | --- |
| `R06-S2-CR-F01` explicit primary mismatch仍猜first file | **accepted / CLOSED**；唯一helper miss/mismatch返回`None` |
| DS O-02 `ProcessedManifestItem` helper建议 | **rejected-as-finding/no-action**；无correctness/ownership drift证据 |
| DS O-03/O-05 private state/path injection | **no-action**；必要owner test seam，不建立public API |
| DS O-04 recovery journal read时序 | **rejected-as-finding/no-action**；无直接failure证据 |
| MiMo validator未覆盖分支 | **informational residual/no-action**；既有22格与owner matrix满足gate |
| full pyright 108、producer ack与旧README中间态 | **covered by S3**；最终分别降为0、production scan 0、README已更新 |

S2最终：`R06-S2-CR-F01` closed，new material finding 0、blocker 0、无中间commit。

### 8.4 R06-S3

| finding/group | final disposition |
| --- | --- |
| `R06-S3-CV-F01` preprocess selection缺失`ingest_complete` direct test | **accepted / CLOSED**；真实shared-core complete sources后损坏一个published meta，selection fail closed |
| 其它Controller validation finding | **none** |
| S3独立slice code review finding | **none**；按accepted plan直接进入完整S1+S2+S3 cumulative review |

### 8.5 Cumulative S1+S2+S3 — AgentMiMo原始16项

| original finding | final Controller disposition |
| --- | --- |
| `R06-CR-MIMO-F01` journal phase ordering / post-swap data loss | **REJECTED — non-defect**；`SWAPPED_TARGET`是pre-commit rollback state |
| `R06-CR-MIMO-F02` SEC rebuild取消不rollback | **accepted into `R06-CR-F02` / CLOSED** |
| `R06-CR-MIMO-F03` publication guard release force-release建议 | **REJECTED — unsafe remedy / retained operational residual** |
| `R06-CR-MIMO-F04` ingestion rollback primary不一致 | **accepted into `R06-CR-F03` / CLOSED** |
| `R06-CR-MIMO-F05` public token字段违反opaque | **REJECTED — contradicts accepted plan**；opaque不等于hidden |
| `R06-CR-MIMO-F06` BatchToken应加format validation | **REJECTED — non-defect**；authority由registry验证，不承诺grammar |
| `R06-CR-MIMO-F07` processed manifest raw fields | **REJECTED — pre-existing/out-of-scope** |
| `R06-CR-MIMO-F08` `DocumentSummary` source_kind default | **REJECTED — pre-existing/out-of-scope** |
| `R06-CR-MIMO-F09` rejected artifact list partial warning | **REJECTED — pre-existing/out-of-scope** |
| `R06-CR-MIMO-F10` processed staging helper写入顺序 | **REJECTED — non-defect/pre-existing**；transaction rollback拥有原子性 |
| `R06-CR-MIMO-F11` validator扩到processed/company/maintenance | **REJECTED — contradicts accepted plan/overdesign** |
| `R06-CR-MIMO-F12` storage强制历史blob-first顺序 | **REJECTED — overdesign**；commit完整性不需第二套touched/order state |
| `R06-CR-MIMO-F13` rename reader test可能vacuous pass | **accepted into `R06-CR-F04` / CLOSED** |
| `R06-CR-MIMO-F14` composed-read test实际顺序 | **REJECTED — test intent misread** |
| `R06-CR-MIMO-F15` SEC adapter private property | **REJECTED — non-material**；passthrough property会形成无语义facade |
| `R06-CR-MIMO-F16` SEC rebuild rollback双失败 | **accepted into `R06-CR-F02` / CLOSED** |

### 8.6 Cumulative S1+S2+S3 — AgentDS原始7项

| original finding | final Controller disposition |
| --- | --- |
| `R06-CR-DS-F01` malformed journal阻断其它orphan | **accepted into `R06-CR-F01` / CLOSED** |
| `R06-CR-DS-F02` ingestion rollback丢operation primary | **accepted into `R06-CR-F03` / CLOSED** |
| `R06-CR-DS-F03` pipeline optional batching重建core | **REJECTED — composition-root misread**；pipeline本身是合法default root |
| `R06-CR-DS-F04` preprocess显式false测试 | **REJECTED — duplicate impossible-state test** |
| `R06-CR-DS-F05` SEC pipeline重复断言completion | **REJECTED — downstream duplicate assertion** |
| `R06-CR-DS-F06` revision-change-after-build测试 | **DEFERRED — R07 unique owner** |
| old `R06-CR-DS-F07` FileStore/local path双构造链 | **REJECTED by final Controller adjudication**；default local key/root与contained path精确等价，FileStore collaborator拥有自身containment，无reachable divergence/bypass证据 |

### 8.7 Cumulative accepted groups final closure

| accepted group | final state |
| --- | --- |
| `R06-CR-F01` per-entry unparseable journal isolation | **CLOSED** |
| `R06-CR-F02` SEC rebuild cancellation + rollback dual-failure | **CLOSED** |
| `R06-CR-F03` ingestion operation-primary preservation | **CLOSED** |
| `R06-CR-F04` deterministic real publication-acquire synchronization | **CLOSED** |

累计最终 ledger：`R06-CR-F01..F04`、`R06-S1-CR-F01..03`、`R06-S2-CR-F01`、`R06-S3-CV-F01` 共 `9 closed / 0 open / 0 blocker`；S1较早的 `VF-01..04` 也全部closed。原MiMo/DS每一项均已有final disposition，没有遗漏、`needs-more-evidence`或未分类finding。

## 9. Retained security/safety 与明确未实现范围

### 9.1 Retained behavior

- **containment / identity**：ticker、source kind、document ID、filename与recovery path继续由storage normalizer/contained-path owner校验；absolute、`.`/`..`、separator、drive/UNC与root escape继续fail closed。R06没有实现R07 opaque external-ID mapping，也没有删除现有containment。
- **symlink**：transaction/recovery/staging/source/meta/blob/manifest path的symlink escape继续拒绝；validator只接受contained non-symlink regular files。
- **DNS/peer与Web egress**：现有Web network-policy、DNS pin/peer proof、redirect/egress enforcement保持原样；R06未修改或削弱。这些不是R06新实现的authorization。
- **resource budgets**：现有Web response/DOM/diagnostic budgets、Doc output limits与其它resource protections保持；R06未删除、重算或扩展这些owner。
- **atomic write/fsync**：atomic JSON、file-store atomic replace、directory rename与parent-directory fsync保留；commit point、journal与failure restore同源。
- **process fencing/cancellation**：既有process late-publication fencing、ToolRuntime accept barrier、Fins cancellation checks保持；R06只修显式storage transaction与producer传播，不实现Issue 175 process isolation。
- **locks**：writer transaction mutex、独立publication guard、global recovery/ticker writer lock与其固定顺序保持；物理lock不授予mutation authority。禁止删除lock file或伪造force-release。
- **local permission/config**：Doc `allowed_paths`、Web policy config等既有局部权限/安全机制保持有效；没有把它们误称为统一authorization。

### 9.2 Explicit non-implementation

- **统一 tool authorization**：未实现Host principal/run/attempt permission model、resource scope、policy DSL、capability token或sandbox；Topic 9仍由未来独立设计拥有。
- **R07**：未实现跨read snapshot handle、revision contract变更、bounded retry、cache新contract、selector/generation layout、opaque ID mapping或storage-key grammar。
- **Issue 142**：未实现workspace migration framework。
- **Issue 151**：未实现write/assets surface。
- **Issue 175**：未实现Fins Docling child-process isolation/kill escalation。
- **Issue 177**：未实现Doc producer到TruncationManager/fetch-more remainder的完整wiring。
- **Issue 178**：未实现Web storage-state lifecycle。
- 未实现旧schema migration/compatibility、callback transport、R08-R11或R07 plan/implementation。

## 10. Residual、唯一 owner/destination 与下一入口

| residual | final classification | unique owner / destination |
| --- | --- | --- |
| 跨多个repository calls或processor lifetime的同版本snapshot/revision；裸`Path`延迟/多次读取可能跨版本 | accepted R06 residual；不削弱一次published read/open old-or-new | **R07 independent plan gate**。直接consumer为8个production文件/9个调用点：`bs_processor.py`、`docling_processor.py`两处、`markdown_processor.py`、`sec_processor.py`、`bs_report_form_common.py`、`bs_six_k_processor.py`、`source_text.py`、`sec_fiscal_fields.py`；`source_snapshot.py`只从一次`Source.open()`复制稳定spool，不是第9个独立裸路径consumer |
| publication lock release syscall极低概率失败时，活进程可能继续持kernel fd lock | retained operational residual；unsafe force-release已rejected | **`dayu.runtime.filelock` / process termination**；Fins recovery不得删除marker、切新inode或伪造release |
| 三条`edgar` deprecation warnings | 既有外部依赖warning，不是R06新增 | **外部dependency升级/维护owner**；不阻塞R06 completion |
| 一个可选Docling integration skip | 既有环境门控，不是correctness waiver | **Docling integration environment/test owner**；不阻塞R06 completion |

没有未分类 residual、open accepted finding、blocking product question或需要新issue/user decision的当前R06事实。R07的opaque-ID mapping/retry/cache等仍是明确non-scope，不能借completion residual提前冻结方案。

严格下一顺序只有：

```text
Controller validation of this completion artifact
  -> exact-scope local completion-state commit
  -> R07 independent plan gate
```

- Controller validation前不得改control、开始R07或创建completion commit。
- completion-state commit只能包含本artifact、Controller completion validation与Controller同步control state；真实exact scope由Controller在该gate裁决。
- commit后只能进入R07**独立 plan gate**；不能跳过plan review/fix/re-review，也不能把本handoff解释为R07 implementation授权。
- push、PR与umbrella final closeout均不是当前入口。

## 11. Completion author 自检

- 已读取并核对 `AGENTS.md`、overdesign Controller discussion、`docs/fins/design.md`、accepted R06 plan（尤其§12）、当前control中的R06 completion状态、完整cumulative review/fix/re-review/Controller链，以及S1/S2/S3 implementation/validation/review最终状态。
- accepted plan SHA、plan内容hash、transition base、accepted implementation SHA、parent/merge-base、88-file exact allowlist与tree scope均由Git对象直接核验。
- public token、19个mutation signatures、唯一staged read、deleted ambient/auto-batch/ack semantics、四个shared-core roots、validator/publication/recovery/reader contract均与accepted code和evidence交叉一致。
- direct/aggregate tests、38-file coverage、pyright、scoped/full Ruff fingerprint、AST/source scans、README decision与finding ledger均来自accepted evidence；本gate未重跑产品测试矩阵。
- current Controller control diff保持原样；本gate唯一新增path是本artifact。
- 本artifact完成后的whitespace、scope、status与`git diff --check`结果由本gate最后只读核验记录。

## READY_FOR_CONTROLLER_VALIDATION
