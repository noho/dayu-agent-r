# WU-SEMANTIC-OWNERSHIP-01 R06 plan review — AgentMiMo (第一路)

## 0. Review identity

- reviewer: AgentMiMo
- review type: adversarial plan review (第一路)
- immutable target: `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`
- expected SHA-256: `f147079bd9870f14402feb0782a3568109ccb710fa67d3bfe97add120f2336cd`
- Controller entry validation: `docs/reviews/wu-semantic-ownership-01-r06-plan-entry-controller-validation.md`
- base: `9c07b88d9e855f19f0b828f671022119cc5599a1`
- 本 artifact 只写 review 结论；不修改 plan / control / product / test / README，不 stage / commit / push / PR。

## 1. Review scope 与方法

完整读取以下文件并核对直接代码证据：

- `AGENTS.md`（项目约束）
- `docs/host/issues-implementation-control.md`（总控 baseline 机制，读取前 100 行确认职责）
- `docs/fins/design.md`（Fins 设计真源）
- plan artifact 全文（563 行）
- Controller entry validation 全文（66 行）
- 以下 production 代码的直接证据：
  - `dayu/fins/domain/document_models.py` — `BatchToken` 当前字段
  - `dayu/fins/storage/_fs_storage_infra.py` — `_BATCH_OWNER_CONTEXT`、`_require_batch_owner()`、`_execute_with_auto_batch()`、`_write_batch_journal()`、`commit_batch()` 两次 rename
  - `dayu/fins/storage/repository_protocols.py` — 当前 protocol 签名、`stage_source_document()` 存在
  - `dayu/fins/storage/_fs_blob_core.py` — `store_file()` 调用 `_get_handle_meta()` 前置校验
  - `dayu/fins/storage/_fs_source_document_core.py` — `_STAGING_STABLE_META_FIELDS`、`stage_source_document()`、`has_filing_xbrl_instance()`
  - `dayu/fins/storage/local_file_source.py` — `LocalFileSource.open()` / `materialize()` 无 guard
  - `dayu/fins/storage/_fs_repository_factory.py` — `_FsRepositorySet` 共享 core
  - `dayu/fins/storage/fs_batching_repository.py` — 委托到 `_repository_set.core`
  - `dayu/fins/pipelines/docling_upload_service.py` — 内部 `begin_batch` / `commit_batch`、`_acknowledge_source_before_blob_write()` 调用 `stage_source_document`
  - `dayu/fins/pipelines/sec_download_persistence.py` — `build_store_file()` 用 `partial` capture repository/handle、`_store_file_callback` 无 batch 参数
  - `dayu/fins/ingestion_runtime.py` — imports 确认 `BatchToken` 使用

## 2. Findings

### R06-REVIEW-001 — `LocalFileSource.materialize()` 的 residual 必须显式记录

**严重性**: material finding（R07 已有 owner，计划需显式记录）

**直接证据**:
- `local_file_source.py:34-47`: `materialize()` 返回 `self.path`（裸 `Path`），无 guard
- `local_file_source.py:19-32`: `open()` 返回 `self.path.open("rb")`，无 guard
- plan §4.2: "get_source() / get_primary_source() 返回的 Fins LocalFileSource 必须带 required storage-owned open guard：Source.open() 获取同一 publication swap guard，直到对应文件描述符成功打开后释放"
- 当前 `materialize()` 的 production consumers：
  - `processors/sec_processor.py:157`: `source_path = source.materialize(suffix=suffix)`
  - `processors/bs_report_form_common.py:129`: `self._source_path = source.materialize(suffix=".html")`
  - `processors/bs_six_k_processor.py:276`: `self._source_path: Path = source.materialize(suffix=".html")`
  - `processors/source_text.py:88`: `source_path = source.materialize(suffix=suffix)`
  - `pipelines/sec_fiscal_fields.py:349`: `local_path = source.materialize()`

**问题**:
计划只要求 `Source.open()` 获取 publication swap guard 直到 fd 打开。`materialize()` 返回裸 `Path`，消费者随后用 `Path.open()` 或其它方式读取——两次调用之间 guard 已释放。这些 processor / pipeline consumer 的实际文件访问不在 R06 guard 保护范围内。

这不是 R06 的设计缺陷——plan §1.3 / §11 已将"跨多次 repository call 或长生命周期 processor 消费的同版本 snapshot/revision"明确归为 R07 residual。但计划 §4.2 只提到 `Source.open()` 的 guard，没有显式记录 `materialize()` 的 5 处 production consumer 同样属于 R07 residual。

**所需 plan 修正**:
计划应在 §4.2 或 §11 中显式记录：`materialize()` 返回裸 Path 后的后续文件访问（当前 5 处 processor/pipeline consumer）是 R07 snapshot 的 deferred residual。R06 只保证 `Source.open()` 的单次 fd 稳定性。不给 R06 发明 fd-wrapper / path-copy 新 contract。

---

### R06-REVIEW-002 — publication swap guard 的多进程 owner 与实现机制未指定

**严重性**: blocking question

**直接证据**:
- `_fs_storage_infra.py:651-667`: `_acquire_ticker_lock()` 使用 `file_lock` 跨进程锁
- plan §4.1: "现有跨进程 ticker file lock 保留，但语义收窄为一件事"
- plan §4.2: "storage 必须在 writer transaction/ticker mutex 之外建立独立的 storage-owned publication swap guard protocol"

**问题**:
计划描述了 publication swap guard 的行为语义（commit/recovery 短窗内阻塞 reader），但没有指定其实现机制：
1. 如果 guard 是进程内锁（`asyncio.Lock` / `threading.Lock`），它无法保护多进程并发 reader
2. 如果 guard 是跨进程文件锁，它需要独立于 ticker lock 的锁文件
3. 当前代码只有 ticker lock 和 recovery lock，没有 publication swap guard 的锁

**反例**:
进程 A 做 commit（两次 rename），进程 B 的 published reader 在 rename 窗口内读取——如果 guard 只是进程内锁，进程 B 完全不受保护。

**所需 plan 修正**:
计划必须明确指定：
- publication swap guard 是进程内锁还是跨进程文件锁
- 如果是跨进程文件锁，锁文件路径是什么（不能复用 ticker lock，因为 writer 持有 ticker lock 的时间远长于 swap 短窗）
- 如果是进程内锁，必须声明多进程并发 reader 保护是 R07 / process isolation 的 residual

---

### R06-REVIEW-003 — callback 签名变化未明确指定

**严重性**: material finding

**直接证据**:
- `sec_download_persistence.py:139-156`: `build_store_file()` 返回 `partial(_store_file_callback, repository, source_handle)`，当前签名 `(filename, stream) -> FileObjectMeta`
- `sec_download_persistence.py:459-480`: `_store_file_callback` 无 batch 参数
- plan §6: "callback 签名显式包含 BatchToken；repository mutation 再以 keyword batch= 调用"
- plan §6: "downloader API 新增 required keyword batch，并在每次 callback invocation 显式传入"

**问题**:
计划说 callback 签名必须显式包含 BatchToken，但没有指定目标签名的具体形式。`functools.partial` 可以继续绑定 repository / handle，返回的 callable 的目标签名可以显式接受 `(filename, stream, *, batch: BatchToken)`——batch 在 invocation 时由 downloader 传入，不是 capture。计划只需写明 `_store_file_callback` 的目标签名即可。

**所需 plan 修正**:
计划应明确 `build_store_file` / `_store_file_callback` 的目标签名（如 `(filename: str, stream: BinaryIO, *, batch: BatchToken) -> FileObjectMeta`），以及 downloader 如何在每次 invocation 时以实参传入 batch。这不是实现细节——callback 签名是 downloader 和 persistence 之间的 contract。

---

### R06-REVIEW-004 — `has_staged_filing_xbrl_instance` vs `has_filing_xbrl_instance` — no-action confirmed clarification

**严重性**: no-action（plan §3.4 已明确，无需修正）

**直接证据**:
- `_fs_source_document_core.py:741-764`: `has_filing_xbrl_instance()` 使用 `_source_root_for_read()`，当前对 active batch owner 路由到 staging
- plan §3.4: "published `has_filing_xbrl_instance()` 继续只读 published tree"；"为它提供一个窄、显式、required-batch 的 transaction-internal read（计划名 `has_staged_filing_xbrl_instance`）"

**确认**:
plan §3.4 已经明确区分了两个 contract：`has_filing_xbrl_instance()` 只读 published，`has_staged_filing_xbrl_instance()` 是 required-batch 的 transaction-internal staging read。R06 删除 `_ticker_dir_for_read()` 的 staging 路由后，现有 `has_filing_xbrl_instance()` 自然变为只读 published；新增的 staged read 覆盖 SEC blob 落盘后的 XBRL 判断。contract 变化清晰，无需额外 plan 修正。

---

### R06-REVIEW-005 — complete-source validator 的 files 非空规则 — no-action（有意设计）

**严重性**: no-action（有意设计，无需修正）

**直接证据**:
- plan §5.2: "files 是非空、无重复业务文件名的完整 manifest"
- `_fs_source_document_core.py:964-1001`: `_stage_source_document_impl` 中 `ingest_complete=False` 时 files 可以为空
- `DoclingUploadService._acknowledge_source_before_blob_write` 传入 `file_entries=[]`

**问题**:
计划要求 validator 断言 files 非空。当前代码中 staging source 可以有空 files（`ingest_complete=False` 时）。R06 删除 staging ack 后，final source 必须有 files——这与"blob-first + final source 一次"一致。

但需要确认：是否存在合法的无 blob source（如纯文本 meta-only source）？如果存在，files 非空规则会错误拒绝。当前所有 producer 都写 blob，所以这不是当前问题，但计划应声明这是 storage contract 的有意设计，而非偶然。

**所需 plan 澄清**:
计划可以加一句："files 非空是 storage publication contract 的有意设计；当前所有 producer 都产生 blob，未来若有 meta-only source 需求，必须先更新 validator contract。"

---

### R06-REVIEW-006 — §5.2 validator 的 staged-tree vs touched-identities 策略未裁决

**严重性**: material finding

**直接证据**:
- plan §5.2: "validator 可验证全 staged tree，或用 internal touched identities 并同时验证相关 ticker manifest 闭包；选择必须保证未验证的 mutation 不可能进入 publish"

**问题**:
两种策略的正确性属性和性能特征差异很大：
- 全 staged tree：简单、完整，但可能验证无关文件
- touched identities：精确，但需要维护 touched set，且需要证明闭包完整性

计划把选择留给实现，但这是一个影响正确性证明的关键设计决策。如果选择 touched identities 但闭包不完整，未验证的 mutation 可能进入 publish。

**所需 plan 修正**:
计划应明确推荐一种策略（建议全 staged tree，因为更简单且 R06 不要求性能优化），或至少明确 touched-identities 策略的闭包完整性证明要求。

---

### R06-REVIEW-007 — `_execute_with_auto_batch` 的删除时机应为 S1 core cutover

**严重性**: material finding（plan 需明确）

**直接证据**:
- `_fs_storage_infra.py:423-464`: `_execute_with_auto_batch()` 自动 begin/commit
- `_fs_blob_core.py:85`、`_fs_source_document_core.py:247+`、`_fs_processed_core.py:49+`、`_fs_maintenance_core.py:86+`、`_fs_company_meta_core.py:143`: 所有 wrapper 通过 `_execute_with_auto_batch` 调用 core
- plan §3.4: 全部 mutating protocol 新增 keyword-only、non-optional `batch: BatchToken`
- plan §7.1: S1 改 storage protocol + wrapper 签名

**问题**:
S1 把 protocol 改为 required batch 后，wrapper 必须接收 batch 并直接传给 core。`_execute_with_auto_batch` 不再被 wrapper 调用——它在 S1 的 core cutover 中自然失效。计划 §7.3 说"S3 删除 implicit mutation"，但根据 S1 的 contract 变化，`_execute_with_auto_batch` 应在 S1 删除。

**所需 plan 修正**:
计划应明确 `_execute_with_auto_batch` 在 S1 的 storage core cutover 中删除（连同 `_bind_batch_owner` / `_unbind_batch_owner` / `_BATCH_OWNER_CONTEXT`），而非推迟到 S3。

---

### R06-REVIEW-008 — journal 字段闭集是否完整

**严重性**: evidence-valid observation（确认 plan 正确）

**直接证据**:
- `_fs_storage_infra.py:709-739`: `_write_batch_journal()` 写入 `token_id`, `owner_token`, `owner_scope_id`, `ticker`, `created_at`, `owner_pid`, `hostname`, `phase`, `target_dir`, `staging_root_dir`, `staging_ticker_dir`, `backup_dir`, `journal_path`, `ticker_lock_path`
- plan §4.3: journal 只保存 "opaque transaction identity; normalized ticker; phase; 相对且经过 containment 校验的 staging/target/backup locator"

**确认**:
当前 journal 暴露了 owner_token、owner_scope_id、PID、hostname、created_at、lock path 和绝对路径。计划正确识别了这些字段应被删除。recovery 只需要 transaction_id、ticker、phase 和相对 locator。

---

### R06-REVIEW-009 — `partial` capture 模式兼容 required batch（合并入 R06-REVIEW-003）

**严重性**: no-action（已合并入 R06-REVIEW-003）

**直接证据**:
- `sec_download_persistence.py:139-156`: `build_store_file` 返回 `partial(_store_file_callback, repository, source_handle)`
- `sec_download_persistence.py:459-480`: `_store_file_callback` 调用 `repository.store_file(source_handle, filename, stream)`

**确认**:
`functools.partial` 继续绑定 repository / handle 是正确的——这些是非 authority 输入。`_store_file_callback` 的目标签名只需新增 `*, batch: BatchToken`，batch 由 downloader 在每次 invocation 时以实参传入。不需要改 class 或 closure。具体签名 contract 见 R06-REVIEW-003。

---

### R06-REVIEW-010 — §6 inventory 中 `mark_downloaded_processed_rebuild_required` 的 batch 传播路径

**严重性**: evidence-valid observation（确认 plan 完整）

**直接证据**:
- plan §6: "adapter 为一次短 publication owner；函数显式接收 batch，不自行 begin"

**确认**:
这个条目说 adapter 接收 batch 而不自行 begin。这意味着调用者（workflow）负责 begin/commit，adapter 只消费 batch。这与 plan 的"唯一 top-level lifecycle owner"原则一致。

---

### R06-REVIEW-011 — `service_runtime.py` 是新增 batching composition 的 required allowlist

**严重性**: no-action（直接证据确认必要性，无需 plan 修正）

**直接证据**:
- `service_runtime.py:347`: `repository_set = build_fs_repository_set(workspace_root=workspace_root)` — 创建 shared `_FsRepositorySet`
- `service_runtime.py:350-369`: 把 `repository_set` 传给 `FsCompanyMetaRepository`、`FsSourceDocumentRepository`、`FsDocumentBlobRepository`、`FsFilingMaintenanceRepository`、`FsProcessedDocumentRepository`
- 当前没有创建 `FsBatchingRepository` — 缺少 batching facade 装配
- plan §3.5: "`DefaultFinsRuntime`、`CnPipeline`、`SecPipeline` 与 standalone 6-K repair 是 composition owner；它们显式装配 `BatchingRepositoryProtocol`"
- plan §7.3 说明: "不在 umbrella R06 closed row，但当前直接代码证明它们分别拥有真实 batching composition"

**确认**:
`DefaultFinsRuntime.create()` 是 production 的唯一 shared composition root。R06 要求显式装配 `FsBatchingRepository` 并传入同一 `repository_set`。这是 required allowlist refinement，不是 blocking question。

---

### R06-REVIEW-012 — §7.3 allowlist refinement 中 `cn_download_protocols.py` 的必要性

**严重性**: evidence-valid observation（确认必要性）

**直接证据**:
- plan §6: "run_cn_download_stream_impl → company meta；rebuild delegation → workflow 对 company meta 短 transaction 唯一负责"
- plan §7.3 说明: "当前直接代码证明它们分别拥有真实 batching composition、host protocol、download callback invocation"

**确认**:
CN download protocols 定义了 download workflow 的协议接口。如果 CN download workflow 的 callback 需要显式 batch，protocols 中的 callback 签名必须更新。这是必要的。

---

### R06-REVIEW-013 — §8.3 propagation scan 的完整性

**严重性**: evidence-valid observation（确认完整）

**直接证据**:
- plan §8.3 列出了 6 条 rg 命令
- 第一条覆盖 `ContextVar|_BATCH_OWNER_CONTEXT|owner_scope_id|owner_token|current_task|get_ident|thread.*ident|_execute_with_auto_batch|auto_batch`
- 第二条覆盖 `stage_source_document|_STAGING_STABLE_META_FIELDS|staging.*ack|acknowledge_source|ingest_complete.*false`

**确认**:
这些 scan 覆盖了所有旧 authority / ack 模式。第一条的 `ContextVar` 和 `_BATCH_OWNER_CONTEXT` 覆盖了 ambient identity。第二条的 `stage_source_document` 和 `ingest_complete.*false` 覆盖了 staging ack。这是完整的。

---

### R06-REVIEW-014 — §10 baseline 的 scoped Ruff 错误是否会在 R06 中自然消失

**严重性**: evidence-valid observation

**直接证据**:
- plan §10 列出 10 个 scoped Ruff 错误（F401 unused imports, F841 unused local）
- 其中 `ingestion_runtime.py:26:20` 是 `typing.TYPE_CHECKING imported but unused`
- `ingestion_runtime.py:2499:29` 是 `Local variable exc is assigned to but never used`

**确认**:
当 S3 修改 `ingestion_runtime.py` 的签名时，imports 会自然更新。这些错误很可能在 R06 实现中自然消失。计划说"实现触及这些文件时只做必要 lint hygiene"——这是正确的。

---

### R06-REVIEW-015 — R07 residual 边界是否精确

**严重性**: evidence-valid observation（确认 plan 正确）

**直接证据**:
- plan §1.3: "R06 的短时 publication swap guard 保证一次 published repository read/open 不落入 rename 空窗；跨多次 repository call、长生命周期 processor read 的同版本 snapshot 仍由 R07 独占"
- plan §11: "R06 完成后仍由 R07 拥有的唯一 residual 是'跨多个 repository call 或长生命周期 processor 消费的同版本 snapshot/revision'"

**确认**:
R06/R07 边界清晰：R06 保证单次 read/open 的 old/new 完整性，R07 保证多次 read 的版本一致性。计划没有偷带 R07。

---

### R06-REVIEW-016 — Issue 142/151/175/177/178 是否被偷带

**严重性**: evidence-valid observation（确认未偷带）

**直接证据**:
- plan §1.3: "不实施 Issue 142/151/175/177/178，不引入 process isolation、统一 authorization、callback transport 或旧 schema compatibility"

**确认**:
计划明确排除了这些 issue。R06 的 scope 收窄为显式 transaction + complete source publication。

---

### R06-REVIEW-017 — containment / symlink / atomic write 安全机制是否回退

**严重性**: evidence-valid observation（确认不回退）

**直接证据**:
- `_fs_storage_infra.py:973-994`: `_resolve_handle_child_path()` 做 containment 检查
- `_fs_storage_infra.py:293-315`: `_replace_directory()` 使用 `os.replace()` + `_fsync_directory()`
- plan §5.2: validator 验证 "contained 且无 symlink escape"

**确认**:
现有 containment 检查在 `_resolve_handle_child_path()` 中。计划的 validator 要求同样的 containment 校验。`os.replace()` 是原子操作。安全机制不回退。

---

## 3. Blocking questions 汇总

| ID | 问题 | 所需 Controller / plan 决策 |
| --- | --- | --- |
| R06-REVIEW-002 | publication swap guard 的多进程实现机制 | 指定进程内锁 vs 跨进程文件锁；若跨进程，指定锁文件路径 |

## 4. Material findings 汇总

| ID | 描述 |
| --- | --- |
| R06-REVIEW-001 | `materialize()` 的 5 处 production consumer 是 R07 deferred residual，计划需显式记录 |
| R06-REVIEW-003 | callback 签名变化未明确指定（含 R06-REVIEW-009 合并） |
| R06-REVIEW-006 | validator 的 staged-tree vs touched-identities 策略未裁决 |
| R06-REVIEW-007 | `_execute_with_auto_batch` 应在 S1 core cutover 删除，计划需明确 |

## 5. No-action / confirmed observations 汇总

| ID | 描述 |
| --- | --- |
| R06-REVIEW-004 | plan §3.4 已明确 published `has_filing_xbrl_instance` 只读 published，另增 required-batch staged read |
| R06-REVIEW-005 | files 非空规则是 storage publication contract 的有意设计（当前所有 producer 都产生 blob） |
| R06-REVIEW-009 | `partial` 继续绑定 repository/handle 是正确的，batch 由 invocation 传入（已合并入 003） |
| R06-REVIEW-011 | `service_runtime.py` 是 `DefaultFinsRuntime.create` 的 shared composition root，required allowlist |

## 6. Residual / deferred owners 确认

| residual | owner | 确认 |
| --- | --- | --- |
| 跨多次 repository call 的同版本 snapshot | R07 | plan §1.3 / §11 明确 |
| `materialize()` 后续文件访问的版本一致性 | R07 | plan §1.3 已归类；R06-REVIEW-001 要求计划显式记录 5 处 consumer |
| 多进程并发 reader 保护 | 取决于 R06-REVIEW-002 的裁决 | 若为进程内锁则归 R07 / process isolation |

## 7. Converged evidence 确认

以下 plan 声称经直接代码证据确认为正确：

1. **public `BatchToken` 暴露内部状态** — `document_models.py:416-443` 确认暴露 `owner_token`、`owner_scope_id`、物理路径
2. **`_BATCH_OWNER_CONTEXT` + `_require_batch_owner()` 是第二 authority** — `_fs_storage_infra.py:64-67, 501-522` 确认
3. **`_execute_with_auto_batch()` 允许无 token mutation** — `_fs_storage_infra.py:423-464` 确认
4. **`stage_source_document()` + `ingest_complete=false` 泄漏事务状态** — `_fs_source_document_core.py:1115` 确认
5. **`_get_handle_meta()` 要求 blob 前有 meta** — `_fs_blob_core.py:143` 确认
6. **commit 两次 rename 存在在线空窗** — `_fs_storage_infra.py:261-265` 确认
7. **DoclingUploadService 有内部 lifecycle** — `docling_upload_service.py:331, 403, 422` 确认
8. **`_store_file_callback` 无 batch 参数** — `sec_download_persistence.py:459-480` 确认
9. **journal 暴露 PID/hostname/绝对路径** — `_fs_storage_infra.py:723-739` 确认
10. **`_FsRepositorySet` 共享 core 模式存在** — `_fs_repository_factory.py:14-22` 确认

## 8. Controller mandatory questions 回答

### Q1: publication swap guard 如何避免嵌套 read 自死锁？

**回答**: 如果 guard 是 reentrant lock（如 `threading.RLock`），嵌套 read 不会死锁。如果 guard 是非 reentrant 文件锁，计划必须明确"guard 只存在于最外层 materialization"——即 `_ticker_dir_for_read()` 不获取 guard，只有最终的 `Source.open()` / meta read / blob bytes 获取。计划 §4.2 已说"每一个 published repository meta/list/read 必须在 storage core 获取同一 publication swap guard"——这意味着每次 read 都获取 guard，如果 read 嵌套（如 `get_source_meta` 内部调用 `list_files`），需要 reentrant 机制。**计划应指定 guard 为 reentrant 或明确嵌套边界。**

### Q2: `LocalFileSource.open()` 的 stable-fd 与 `materialize()` 的缺口？

**回答**: 见 R06-REVIEW-001。`materialize()` 返回裸 Path，5 处 production processor/pipeline consumer 的后续文件访问不在 R06 guard 内。plan §1.3 已将此类访问归为 R07 residual，但计划应显式记录这 5 处 consumer。R06 不需要发明 fd-wrapper / path-copy 新 contract。

### Q3: complete-source validator 的 staged-tree/manifest 闭包？

**回答**: 见 R06-REVIEW-006。全 staged tree 更简单且完整；touched-identities 需要闭包完整性证明。计划应推荐全 staged tree。

### Q4: CN/SEC upload + Docling transaction 边界是否 code-generation-ready？

**回答**: `DoclingUploadService._handle_storage_write()` 已有 `begin_batch` / `commit_batch`。R06 要求删除内部 lifecycle，改为消费 caller batch。这需要：
- `_handle_storage_write()` 新增 `batch: BatchToken` 参数
- 删除 `self._source_repository.begin_batch(ticker)` 和 `self._source_repository.commit_batch(token)`
- caller（upload workflow）负责 begin/commit

这在计划 §6 中有描述，但 `_handle_storage_write` 的签名变化没有显式写在 plan 中。**计划应在 inventory 表中明确 DoclingUploadService 的 API 变化。**

### Q5: S1/S2/S3 累计 breaking cutover 是否可执行？

**回答**: §7.0 明确 S1→S2→S3 按序生成代码，pyright 只在最终累计 tree 运行。这避免了中间绿色假设。但 R06-REVIEW-007 指出 `_execute_with_auto_batch` 应在 S1 删除而非 S3——这需要确认。

### Q6: 新增 allowlist 是否完整且最小？

**回答**: 全部 allowlist 条目均有直接调用链证据。`service_runtime.py` 经 R06-REVIEW-011 补齐证据后确认为 `DefaultFinsRuntime.create` 的 shared composition root（`service_runtime.py:347-369`），是 required allowlist。callback 签名 contract（R06-REVIEW-003）需要 plan 明确。

### Q7: baseline snapshot 是否只消费总控唯一机制？

**回答**: plan §10 明确"本plan只复用 docs/host/issues-implementation-control.md 的唯一 baseline 机制"。scoped Ruff 错误表有完整的六字段。确认正确。

## 9. Verdict

**PASS-WITH-FINDINGS**

计划的核心设计（显式 BatchToken、required batch、writer mutex / publication swap guard 分离、complete-source validator、blob-first staging、三 slice 累计 cutover）经直接代码证据验证，root cause 判定正确，semantic owner 分配清晰。

存在 1 个 blocking question、4 个 material findings 和 4 个 no-action / confirmed observations。其中 R06-REVIEW-002（swap guard 多进程实现机制）是唯一 blocking question；R06-REVIEW-001（materialize residual 显式记录）、R06-REVIEW-003（callback 签名 contract）和 R06-REVIEW-007（auto_batch S1 删除）需要 plan 补充明确设计决策，不能留给"实现时再裁决"。
