# WU-SEMANTIC-OWNERSHIP-01 R06 Fixed Plan Re-Review — AgentDS (第二路)

## 0. Review Identity

- **reviewer**: AgentDS (second independent complete re-review of fixed plan)
- **umbrella**: `WU-SEMANTIC-OWNERSHIP-01`
- **target plan**: `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`
- **plan SHA-256**: `ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43` ✓ verified
- **pre-fix plan SHA**: `f147079bd9870f14402feb0782a3568109ccb710fa67d3bfe97add120f2336cd`
- **base commit**: `9c07b88d9e855f19f0b828f671022119cc5599a1`
- **controller adjudication**: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-controller-adjudication.md`
- **codex fix artifact**: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-fix-codex.md`
- **controller fix validation**: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-fix-controller-validation.md`
- **original DS review**: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-ds.md`
- **original MiMo review**: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-review-mimo.md`
- **this artifact**: `docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-rereview-ds.md`
- **method**: independent adversarial re-review with direct code evidence; full reading of all prior reviews, adjudication, fix artifact, and fix validation; no plan self-description as evidence
- **scope**: fixed plan only. No code, test, README, design, control modification. No stage/commit/push/PR.

## 1. Input Verification

### 1.1 SHA-256 Verification

```
ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43  docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md
```

SHA-256 matches Controller fix validation record exactly. Plan is 585 lines (pre-fix was 563).

### 1.2 All Required Inputs Read

| Input | Read | SHA Verified |
|---|---|---|
| `AGENTS.md` | ✓ full | N/A (read for constraints) |
| `docs/fins/design.md` | ✓ full | N/A (read for design truth) |
| MiMo review | ✓ full 398 lines | matches Codex record |
| DS review | ✓ full 347 lines | matches Codex record |
| Controller adjudication | ✓ full 138 lines | matches Codex record |
| Codex fix artifact | ✓ full 183 lines | matches Controller validation |
| Controller fix validation | ✓ full 71 lines | N/A (read for gate status) |
| Controller entry validation | ✓ full 66 lines | N/A (read for motivation validation) |

### 1.3 Additional Direct Code Evidence Collected

Beyond the evidence in prior reviews, this re-review independently verified:

| Evidence | File:Line | Finding |
|---|---|---|
| `LocalFileSource` (Fins) frozen dataclass, `open()` returns `self.path.open("rb")`, no guard | `dayu/fins/storage/local_file_source.py:19-47` | Confirmed: no existing guard infrastructure on read path |
| `LocalFileSource` (documents layer) separate implementation | `dayu/documents/processors/local_file_source.py:1-65` | Confirmed: two independent `LocalFileSource` classes exist |
| `Source` Protocol defines `open()` + `materialize()` | `dayu/documents/processors/source.py:15-70` | Confirmed: processor contract is Protocol-based |
| `_ticker_dir_for_read` routes active-batch reads to staging | `_fs_storage_infra.py:1363-1380` | Confirmed: published/staging read separation needed |
| `_file_store_root_for_ticker` routes active-batch to staging | `_fs_storage_infra.py:1382-1401` | Confirmed: blob root also affected |
| `sec_6k_primary_document_repair.py` NO `build_fs_repository_set` usage | `sec_6k_primary_document_repair.py:168-171` | Confirmed: independent cores, deeper refactoring needed |
| `service_runtime.py` uses `build_fs_repository_set` but no `FsBatchingRepository` | `service_runtime.py:347-369` | Confirmed: shared core exists, batching facade missing |
| `cn_pipeline.py` uses `build_fs_repository_set` but no `FsBatchingRepository` | `cn_pipeline.py:373-393` | Confirmed: same pattern |
| `sec_pipeline.py` uses `build_fs_repository_set` but no `FsBatchingRepository` | `sec_pipeline.py:509-529` | Confirmed: same pattern |
| `FsBatchingRepository` zero production usage | `rg` search across `dayu/` + `tests/` | Confirmed: only test fixtures instantiate it |
| `BatchToken` exposes 11 fields including paths, owner, PID | `document_models.py:416-443` | Confirmed: public token leaks internal state |
| `_store_file_callback` has no batch parameter | `sec_download_persistence.py:459-480` | Confirmed: callback contract missing batch |
| `build_store_file` returns `Callable[[str, BinaryIO], FileObjectMeta]` | `sec_download_persistence.py:139-156` | Confirmed: callback signature excludes batch |
| `DoclingUploadService._execute_upload_operation` does internal `begin_batch` | `docling_upload_service.py:331` | Confirmed: service owns its own lifecycle |
| `_get_handle_meta` blocks blob-before-meta | `_fs_blob_core.py:143` | Confirmed: blob storage gated on pre-existing meta |
| `_stage_source_document_impl` sets `ingest_complete=False` | `_fs_source_document_core.py:1115` | Confirmed: staging state leaked into business schema |
| 8 production files, 9 `.materialize()` calls | `rg` verified | Confirmed: plan inventory is exact |
| `source_snapshot.py` uses upstream `Source.open()` to spool | `source_snapshot.py` structure | Confirmed: correctly excluded from bare-path consumer list |

## 2. R06-PF-01..08 Closure Verification

Each accepted fix is verified against the fixed plan with direct plan-text evidence, NOT plan self-description.

### R06-PF-01 — Publication Swap Guard: CLOSED ✓

**Controller requirement**: per-ticker cross-process file lock, separate from writer lock, outer guarded entry + private unguarded helper, lock ordering, Source.open() stable fd.

**Fixed plan evidence**:
- §4.2: "publication guard 是按 normalized ticker 分片的跨进程文件锁，复用 `dayu.runtime.filelock` / `RuntimeFileLockToken`；锁路径由固定 storage root 与 normalized ticker 唯一派生为 `batch_locks/<ticker>.publication.lock`。它不得复用从 begin 持有到终态的 `batch_locks/<ticker>.lock`"
- §4.2: "guard 只负责 online physical publication/read exclusion，不是 mutation authority；它不读取、验证或推断 `BatchToken`、caller、task 或 thread identity"
- §4.2: "每一个 public published repository meta/list/read entry 在storage core最外层获取一次同一publication guard，并把guard持有到本次meta/list/bytes I/O完成；它只调用显式 private unguarded helper完成内部路径解析、组合与I/O，不能调用会再次获取非重入文件锁的 public read"
- §4.2: "禁止用 `ContextVar`、task/thread-local、ambient"已持锁"标记、默认参数或 public compatibility 参数表达 guard 已持有；public-to-public 组合必须改为 outer guarded entry + private unguarded helper"
- §4.2: "writer/recovery 的唯一嵌套顺序是先 writer transaction mutex、后 publication guard；释放顺序相反，先 publication guard、后 writer mutex。published reader只获取publication guard，任何路径不得先持 publication guard 再尝试 writer mutex"
- §4.2: "`Source.open()` 获取同一 publication guard，在 fd 成功打开或打开失败后通过同一调用栈释放；成功 fd 固定本次 old 或 new file。不能把 guard 只包住 path 拼接，也不能把"已持锁"状态存入 source"
- §4.2: "storage 用一个窄 typed opener 把 normalized ticker 对应的 publication-lock acquisition 与 `Path.open("rb")` 绑定到延迟执行的 `Source.open()`；该 opener 只绑定 path/ticker 等非authority输入，不绑定 batch。该直接依赖把 `dayu/fins/storage/local_file_source.py` 加入R06 allowlist refinement，但不增加 public snapshot/revision/lease API 或通用 callback framework"

**Direct code evidence confirming necessity**:
- `_fs_storage_infra.py:261-264`: Two-rename commit (`target→backup` then `staging→target`) with NO reader guard between — the online window this guard must close.
- `_fs_storage_infra.py:597-610`: Current ticker lock path is `batch_locks/<ticker>.lock` — plan correctly uses separate `batch_locks/<ticker>.publication.lock`.
- `_fs_storage_infra.py:651-667`: `_acquire_ticker_lock` uses `RuntimeFileLockToken` (cross-process) — proven infrastructure exists.
- `local_file_source.py:19-32`: `open()` is plain `self.path.open("rb")` with zero guard — must be changed.

**Adversarial challenge — cross-process exclusive publication lock, lock ordering, non-reentrant outer-private read boundary**:
- Cross-process: ✓ file lock, not process-internal. Per-ticker sharding prevents unnecessary contention.
- Lock ordering: ✓ writer mutex before publication guard (release reverse). Reader only publication guard. Reverse nesting forbidden.
- Non-reentrant: ✓ enforced structurally — public methods never call public methods. No ambient "already-held" marker.
- **Residual implementation risk**: The plan requires all public-to-public read compositions to be restructured as outer guarded + private unguarded. The plan gives the pattern but does not inventory current compositions. The implementation agent must discover all chains (e.g., `get_source()` internally calling `get_source_meta()` + `get_primary_file()`) and refactor them. Missing one chain produces self-deadlock on the non-reentrant file lock. This is an implementation discovery task — the plan's contract is sufficient; the risk is execution. Tracked as **R06-REREVIEW-R01** below.

**Adversarial challenge — LocalFileSource delayed typed opener as callback/snapshot/ambient seam**:
- The opener is explicitly scoped: binds only path/ticker (non-authority), does NOT bind batch. Invoked only by `Source.open()`.
- Plan explicitly forbids: "不增加 public snapshot/revision/lease API 或通用 callback framework"
- The opener is NOT a general callback — it's a narrow, storage-owned, single-purpose callable that acquires the publication lock and opens the file. It does not create a new extension point.
- **Two-implementation risk**: `dayu/documents/processors/local_file_source.py` exists as a separate `LocalFileSource` implementation for the documents/processors layer. Only `dayu/fins/storage/local_file_source.py` gets the publication guard. If any code path wraps a Fins `LocalFileSource` in a documents one, the guard is silently lost. This is a layering discipline concern — tracked as **R06-REREVIEW-R03** below.

**Verdict**: CLOSED. Guard topology, lock ordering, non-reentrant pattern, and Source.open() stable-fd contract are fully specified.

---

### R06-PF-02 — Materialize Residual: CLOSED ✓

**Controller requirement**: Record all production `.materialize()` consumers; explicitly defer to R07; do not change `materialize()` contract.

**Fixed plan evidence**:
- §4.2: 8 files/9 calls inventory (verified by independent `rg` — exact match):
  - `dayu/documents/processors/bs_processor.py`
  - `dayu/documents/processors/docling_processor.py` (2 calls)
  - `dayu/documents/processors/markdown_processor.py`
  - `dayu/fins/processors/sec_processor.py`
  - `dayu/fins/processors/bs_report_form_common.py`
  - `dayu/fins/processors/bs_six_k_processor.py`
  - `dayu/fins/processors/source_text.py`
  - `dayu/fins/pipelines/sec_fiscal_fields.py`
- §4.2: "`dayu/documents/processors/source_snapshot.py` 不是第 9 个独立裸路径 consumer：它通过一次 upstream `Source.open()` 读到真实 EOF并复制进自有 spool，之后的 `materialize()` 只把该稳定 spool 写入自己拥有的临时文件"
- §4.2: "R06 不修改 `materialize()` public contract，不增加path copy、fd wrapper、lease或revision API，也不得声称覆盖全部 Source read"
- §11: "R06完成后仍由R07拥有的唯一residual是'跨多个repository call或长生命周期processor消费的同版本snapshot/revision'，包括§4.2列出的8个production文件/9个`.materialize()`调用点在取得裸`Path`后的延迟或多次读取"

**Direct code evidence**:
- `rg -n '\.materialize\(' dayu --glob '*.py'` returns exactly 8 production files, 9 calls. Plan inventory is complete.
- `dayu/documents/processors/source_snapshot.py`: confirmed as upstream `Source.open()` → spool → own `materialize()` pattern. Not a bare-path consumer. Plan correctly excludes it.
- `dayu/documents/processors/source.py:57`: `Source` Protocol defines `materialize() -> Path` — processors consume this Protocol, not Fins `LocalFileSource` directly.

**Adversarial challenge — materialize 8文件9调用与 source_snapshot 纠正**:
- Inventory: ✓ exact match with `rg` output.
- `source_snapshot.py`: ✓ correctly identified as non-bare-path consumer. Its `materialize()` materializes a stable spool, not a storage-owned path.
- R07 ownership: ✓ `docs/fins/design.md` §4 already designates R07 as owner of "source snapshot 与 revision/version." R06 correctly defers.

**Verdict**: CLOSED. Complete inventory recorded; R07 ownership explicitly stated; no new contract invented.

---

### R06-PF-03 — Callback Contract: CLOSED ✓

**Controller requirement**: Specify exact callable contract `(filename: str, stream: BinaryIO, *, batch: BatchToken) -> FileObjectMeta`; `partial` allowed for non-authority bindings; batch must be invocation-time keyword argument.

**Fixed plan evidence**:
- §6: "`build_store_file` / rejected variant 返回callback的精确contract为 `(filename: str, stream: BinaryIO, *, batch: BatchToken) -> FileObjectMeta`"
- §6: "`partial`只可绑定repository/handle/ticker/document等非authority输入"
- §6: "每次 callback invocation必须把batch作为required keyword实参传入，随后repository method以keyword-only `batch=`消费；测试断言该invocation token与top-level lifecycle token同值"
- §6: "由于普通 `Callable[[...]]` 不能表达keyword-only参数，downloader/persistence边界使用一个窄callable protocol或等价严格类型来声明上述精确 `__call__` 签名；不引入callback framework"

**Direct code evidence**:
- `sec_download_persistence.py:139-156`: `build_store_file` returns `Callable[[str, BinaryIO], FileObjectMeta]` via `partial(_store_file_callback, repository, source_handle)` — no batch.
- `sec_download_persistence.py:459-480`: `_store_file_callback(repository, source_handle, filename, stream)` — no batch parameter, calls `repository.store_file(source_handle, filename, stream)` without batch.
- `sec_downloader.py:1358-1372,1511-1527`: Downloader contract has no batch parameter.

**Adversarial challenge — callback required keyword batch 可严格类型化**:
- Narrow callable protocol: ✓ the plan's approach of a single-purpose Protocol (not a generic callback framework) is the minimal typed solution. `Callable[[str, BinaryIO, BatchToken], FileObjectMeta]` would make batch positional; the Protocol approach correctly enforces keyword-only.
- `partial` compatibility: ✓ `partial` binds positional parameters only; `batch` as keyword-only cannot be captured by `partial`. This is a Python language guarantee.
- **Minor concern**: The new Protocol class must be placed in an appropriate module (likely `sec_download_persistence.py` or a shared storage types module). The plan doesn't specify the module, but this is an implementation detail, not a plan gap.

**Verdict**: CLOSED. Callback contract is code-generation-ready with exact signature and type strategy.

---

### R06-PF-04 — Full Staged Tree Validator: CLOSED ✓

**Controller requirement**: Full staged ticker tree traversal; bidirectional manifest invariant; no touched-set tracking; primary no fallback; files non-empty is intentional contract.

**Fixed plan evidence**:
- §3.2: "complete-source validation 所需的 staging ticker root；validator 必须遍历完整 staged ticker tree，不维护 touched identities/touched set"
- §5.2: 6 validation rules explicitly specified:
  1. `meta.json` parseable, ticker/document/source-kind consistent with directory routing; `ingest_complete=false` forbidden
  2. Provenance via unique typed owner; ingest method/provider legal; completion state true
  3. `files` non-empty, no duplicates; each name/URI/size/sha consistent with physical regular files, contained, no symlink escape
  4. `primary_document` non-empty, exactly matches files manifest AND physical file exists; no first-file fallback
  5. Filing/material ticker manifest ↔ source directory bidirectional consistency; no dangling manifest, no source missing manifest; identity/provenance/completion projection consistent. "这是R06新增的storage-owned commit-time invariant，不是read层补偿或对既有read行为的描述"
  6. Same-transaction processed/company/maintenance facts in same staging ticker tree
- §5.2: "validator必须遍历完整 staged ticker tree，不采用或维护 touched-identities tracking。当前 transaction 从完整 published ticker tree copy-on-stage，commit也发布完整ticker tree；全树校验无需第二套touched-set状态、闭包证明或fallback"
- §5.2: "`files`非空是complete-source publication contract的有意规则，当前所有producer都产生blob；未来若出现meta-only source需求，必须先修改storage owner contract，不能添加validator例外"

**Direct code evidence**:
- `_fs_storage_infra.py:225`: Copy-on-stage from complete published ticker tree — full tree is already the data model.
- `_fs_source_document_core.py:618,641,1020,1043,1169,1192`: Current manifest writes during mutation but no commit-time bidirectional closure check — validator adds this.
- `_fs_source_document_core.py:1115`: Current `ingest_complete=False` — validator forbids this.

**Adversarial challenge — 全 staged-tree validator 是否只消费 canonical owner facts**:
- Rule 1 (meta.json): canonical storage fact ✓
- Rule 2 (provenance): canonical storage fact via `SourceDocumentProvenance.from_meta()` typed owner ✓
- Rule 3 (files manifest): canonical storage fact verified against physical files ✓
- Rule 4 (primary_document): canonical storage fact cross-checked with manifest and physical file ✓
- Rule 5 (manifest bidirectional): canonical storage fact — filing/material manifest is a storage-owned projection ✓
- Rule 6 (same-transaction facts): canonical storage fact — all in same staging tree ✓
- **No reader fallback, producer inference, or test fixture compensation**: All 6 rules consume storage-owned canonical facts. ✓

**Verdict**: CLOSED. Validator strategy fixed; bidirectional manifest invariant explicitly stated; all rules consume canonical owner facts.

---

### R06-PF-05 — S1 Deletes Implicit Authority: CLOSED ✓

**Controller requirement**: Delete `_execute_with_auto_batch`, `_BATCH_OWNER_CONTEXT`, `_bind_batch_owner`, `_unbind_batch_owner`, `_require_batch_owner`, `_current_execution_scope_id`, task/thread owner inference in S1 (not S3).

**Fixed plan evidence**:
- §7.1: "S1同时删除 `_execute_with_auto_batch`、`_BATCH_OWNER_CONTEXT`、`_bind_batch_owner`、`_unbind_batch_owner`、`_require_batch_owner`、`_current_execution_scope_id`、`asyncio.current_task()`/thread-id owner推断及相关ambient helper；全部private manifest helper显式接收resolved internal active state/batch/path，不保留implicit mutation入口"
- §7.3: "implicit/ambient helper已由S1删除，S3只做完整调用图propagation与零残留证明"

**Direct code evidence**:
- `_fs_storage_infra.py:64`: `_BATCH_OWNER_CONTEXT: ContextVar` — ambient authority context
- `_fs_storage_infra.py:89-108`: `_current_execution_scope_id()` — task/thread identity inference
- `_fs_storage_infra.py:423-464`: `_execute_with_auto_batch()` — auto-begin/commit
- `_fs_storage_infra.py:466-499`: `_bind_batch_owner` / `_unbind_batch_owner` — ambient binding
- `_fs_storage_infra.py:501-522`: `_require_batch_owner()` — ambient authority check
- `_fs_storage_infra.py:1363-1401`: `_ticker_dir_for_read` / `_file_store_root_for_ticker` — routing depends on `_active_batches` + `_require_batch_owner`

All these must be deleted in S1. After deletion, `_ticker_dir_for_read` and `_file_store_root_for_ticker` naturally route to published tree only (since `_active_batches` registry still exists but `_require_batch_owner` is gone, the staging routing path becomes unreachable for published reads; transaction-internal reads use explicit batch→staging path).

**Verdict**: CLOSED. Deletion timing corrected to S1; explicit list of items to delete.

---

### R06-PF-06 — CN/Docling Short Transactions: CLOSED ✓

**Controller requirement**: Separate short transactions for company meta and per-document Docling; Docling consumes caller batch; no cross-transaction rollback.

**Fixed plan evidence**:
- §6: "company meta write是一个outer workflow拥有的短transaction；每个document的Docling write是另一个由top-level upload caller开启和终结的短transaction。company meta已commit而某document失败是可重试的分离publication unit，不做跨transaction rollback，不引入通用callback/profile/framework"
- §6: "`DoclingUploadService._handle_storage_write(..., *, batch: BatchToken)`（或等价storage-write入口）只消费required caller batch；删除内部begin/commit/rollback，直接构造handle、blob-first、final source一次；cancel/exception返回给caller，由caller在commit开始前rollback"

**Direct code evidence**:
- `docling_upload_service.py:331`: `token: BatchToken = self._source_repository.begin_batch(ticker)` — internal lifecycle
- `docling_upload_service.py:351-359`: `_acknowledge_source_before_blob_write()` — calls `stage_source_document()` (to be deleted)
- `cn_pipeline.py:844-852,1097-1105`: Company meta upsert then Docling service call — current flow

**Adversarial challenge — CN/Docling 短事务**:
- The plan correctly separates company meta (one short transaction) from per-document Docling (separate short transactions).
- **Residual question**: If company meta succeeds but all 10 Docling documents fail, the system has company meta with no source documents. Is this a valid intermediate state? The plan says "可重试的分离publication unit" — the caller retries the Docling uploads. This is acceptable because:
  - The two writes have different semantic owners (company identity vs. document content)
  - No cross-transaction consistency requirement exists between them
  - Current code already separates these concerns (company meta is written before Docling service is called)
- **`_acknowledge_source_before_blob_write` deletion**: Not explicitly named in plan, but `stage_source_document()` deletion from protocol + S1 implicit authority deletion forces its removal. Type checker will catch any remaining callers. Self-enforcing. ✓

**Verdict**: CLOSED. Transaction boundaries clearly specified; Docling contract change defined.

---

### R06-PF-07 — FsBatchingRepository New Composition: CLOSED ✓

**Controller requirement**: Explicitly state FsBatchingRepository is NEW production composition at four roots; shared core with other wrappers.

**Fixed plan evidence**:
- §3.5: "`FsBatchingRepository` 当前没有 production 实例；R06 必须把它作为新的 production composition 显式加入，而不是把它描述成既有 wiring"
- §3.5: "`DefaultFinsRuntime`、`CnPipeline`、`SecPipeline` 与 standalone 6-K repair 是四个真实 composition owner：分别在 `service_runtime.py`、`cn_pipeline.py`、`sec_pipeline.py`、`sec_6k_primary_document_repair.py` 创建一个 `_FsRepositorySet`，并从同一 set 装配新的 `FsBatchingRepository` 以及 source/blob/processed/company/maintenance wrappers"
- §7.3: "S3必须在 `service_runtime.py`、`cn_pipeline.py`、`sec_pipeline.py`、`sec_6k_primary_document_repair.py` 四个真实composition root首次实例化production `FsBatchingRepository`，并与既有source/blob/processed/company/maintenance wrapper共享同一个`_FsRepositorySet`/core"

**Direct code evidence**:
- `rg -n 'FsBatchingRepository' dayu/ tests/ --glob '*.py'`: Only `__init__.py` export + `fs_batching_repository.py` class definition in production; all instantiations are in test fixtures. **Zero production usage confirmed.**
- `service_runtime.py:347`: `repository_set = build_fs_repository_set(workspace_root=workspace_root)` — shared core exists, batching facade NOT created.
- `cn_pipeline.py:373`: Same pattern — shared core, no batching.
- `sec_pipeline.py:509`: Same pattern — shared core, no batching.
- `sec_6k_primary_document_repair.py:168-171`: **Different pattern** — each wrapper constructed independently with `resolved_workspace_root`, NO `build_fs_repository_set` call, NO shared `_FsRepositorySet`. Three separate `_FsStorageInfra` instances with three separate `_active_batches` registries.

**Adversarial challenge — 四个新 shared-core batching composition**:
- Three composition roots (`service_runtime.py`, `cn_pipeline.py`, `sec_pipeline.py`) already use `build_fs_repository_set` and share a core. Adding `FsBatchingRepository` is additive — one new constructor call with the existing `repository_set`. ✓
- One composition root (`sec_6k_primary_document_repair.py`) does NOT currently use `build_fs_repository_set`. Each wrapper creates its own independent `_FsStorageInfra`. Switching to shared-core requires:
  1. Import and call `build_fs_repository_set(workspace_root=resolved_workspace_root)`
  2. Create `FsBatchingRepository(workspace_root, repository_set=repository_set)`
  3. Pass `repository_set=repository_set` to all three wrapper constructors
  4. The `_mark_processed_for_batch` lambda at line 188 must receive batch as explicit parameter (plan §6 covers this)
  - This is a **deeper refactoring** than the other three roots. The plan correctly includes this file in S3 allowlist but doesn't call out the extra refactoring depth. Tracked as **R06-REREVIEW-R02** below.

**Verdict**: CLOSED. New composition status explicitly stated; four roots identified; shared-core constraint clear.

---

### R06-PF-08 — Cumulative Reviewability Gates: CLOSED ✓

**Controller requirement**: S1/S2/S3 as cumulative working-tree checkpoints; per-slice Controller verification + MiMo/DS dual review; no magic thresholds, no intermediate accepted commits; final unified review on complete R06 diff.

**Fixed plan evidence**:
- §7.0: "S1、S2、S3 是同一个 R06 breaking cutover 的累计 working-tree checkpoints，不是独立sub-WU、release、accepted commit或green state；不设置固定diff行数、文件数等magic gate"
- §7.0: "每个slice完成后，在下一slice开始前执行Controller scope/focused-test验证与AgentMiMo/AgentDS双路cumulative slice review。验证只要求本slice owner contract与当前可运行的focused tests；因producer尚未propagation而预期存在的repo-wide类型错误必须如实记录，不能包装为绿色或通过"
- §7.0: "每个cumulative slice review的accepted findings都必须在当前working tree修复并完成双路re-review后才能进入下一slice；这些gate不生成accepted commit，也不独立接受slice"
- §7.0: "S3完成全部propagation后，在同一累计final tree上分别运行S1/S2/S3完整focused tests和coverage归因，再运行全量pyright/Ruff/diff/scans；随后仍对完整R06 diff执行统一双路code review、fix/re-review，只有complete final tree可进入accepted local commit裁决"
- §7.0: "Controller按semantic owner、实际diff与reviewer可审性裁决是否需要收窄某个slice实施任务，但不得用magic行数或拆出兼容中间版本"

**Adversarial challenge — S1/S2/S3 累计 reviewability 与最终统一 acceptance 是否可执行**:
- The gate structure is executable: each slice produces a working tree checkpoint → Controller verifies slice contract + focused tests → MiMo/DS review the slice diff → findings fixed → next slice. After S3, full unified review.
- **Key execution risk**: S1 and S2 trees will have expected type errors from producers not yet propagated. Reviewers must distinguish "expected error due to incomplete propagation" from "real bug in current slice." This is acknowledged in §7.0 ("因producer尚未propagation而预期存在的repo-wide类型错误必须如实记录，不能包装为绿色或通过"). The burden is on the reviewers' discipline, not the plan's structure.
- The absence of magic thresholds is correct — Controller adjudicates based on semantic owner and actual diff, not line counts.
- **Cumulative review burden**: Three rounds of dual review (S1, S2, S3) plus final unified review = up to 8 review artifacts. This is heavyweight but proportionate to the breaking cutover's risk. The plan correctly doesn't optimize for review count at the expense of reviewability.

**Verdict**: CLOSED. Gate structure executable; no magic thresholds; final unified acceptance correctly gated.

---

## 3. Scope Creep Verification

Verified that fixed plan does NOT authorize (non-exhaustive):

| Concern | Plan Evidence | Status |
|---|---|---|
| R07 storage revision/snapshot/opaque-id | §1.3, §4.2, §11 explicitly defer | ✓ excluded |
| R08 financial/XBRL contract | §1.3 explicitly excludes | ✓ excluded |
| R09 terminal validator | §1.3 explicitly excludes | ✓ excluded |
| R10 HKEX | §1.3 explicitly excludes | ✓ excluded |
| R11 CLI upload | §1.3 explicitly excludes | ✓ excluded |
| Issue 142/151/175/177/178 | §1.3 explicitly excludes | ✓ excluded |
| Unified authorization | §1.3 explicitly excludes | ✓ excluded |
| Old schema migration/compatibility | §1.3: "不新增旧库迁移、兼容读取、兼容 re-export/facade/wrapper、loose parsing、`hasattr/getattr` fallback" | ✓ excluded |
| Optional/default batch | §3.4: "keyword-only、non-optional `batch: BatchToken`，无默认值、无 `None`" | ✓ excluded |
| Source lifecycle facade | §3.3: "禁止兼容 re-export 或只透传 facade" | ✓ excluded |
| Captured batch in closure | §6: "禁止绑定/capture batch" | ✓ excluded |
| ContextVar/task/thread check | §3.2: "不得检查 `ContextVar`、current task/thread 或 caller identity" | ✓ excluded |
| R07 snapshot via R06 guard | §1.3: "不得以 R06 guard 冒充 R07 snapshot" | ✓ excluded |
| `materialize()` contract change | §4.2: "R06 不修改 `materialize()` public contract" | ✓ excluded |
| Magic line-count gates | §7.0: "不设置固定diff行数、文件数等magic gate" | ✓ excluded |
| Intermediate accepted commits | §7.0: "不生成accepted commit，也不独立接受slice" | ✓ excluded |

**Safety regression check**: Existing containment (`_normalize_path_component`, `.resolve().relative_to()`), atomic write (`_write_json` temp+replace+fsync), and symlink prevention are retained. Journal fields reduced (removing PID/hostname/absolute paths) — security improvement. No regression found.

## 4. Old Finding Status Ledger

### MiMo Original Findings

| ID | Original Severity | R06-PF | Current Status |
|---|---|---|---|
| R06-REVIEW-001 | material | PF-02 | **CLOSED** — 8 files/9 calls inventoried; R07 residual explicit |
| R06-REVIEW-002 | blocking | PF-01 | **CLOSED** — cross-process file lock, lock ordering, guarded/unguarded boundary specified |
| R06-REVIEW-003 | material | PF-03 | **CLOSED** — callback contract `(filename, stream, *, batch) -> FileObjectMeta` specified |
| R06-REVIEW-004 | no-action | — | **CONFIRMED** — published/staged XBRL read separation already in plan |
| R06-REVIEW-005 | no-action | PF-04 | **CONFIRMED** — files non-empty is intentional contract, clarified in PF-04 |
| R06-REVIEW-006 | material | PF-04 | **CLOSED** — full staged tree traversal fixed, touched-set rejected |
| R06-REVIEW-007 | material | PF-05 | **CLOSED** — auto_batch deletion moved to S1 |
| R06-REVIEW-008 | evidence | — | **CONFIRMED** — journal field closure correct |
| R06-REVIEW-009 | no-action | PF-03 | **CLOSED** (merged) — partial allowed for non-authority bindings |
| R06-REVIEW-010 | evidence | — | **CONFIRMED** — adapter lifecycle pattern correct |
| R06-REVIEW-011 | no-action | PF-07 | **CLOSED** — service_runtime.py confirmed as required allowlist |
| R06-REVIEW-012 | evidence | — | **CONFIRMED** — cn_download_protocols.py necessity confirmed |
| R06-REVIEW-013 | evidence | — | **CONFIRMED** — propagation scan completeness confirmed |
| R06-REVIEW-014 | evidence | — | **CONFIRMED** — scoped Ruff baseline handling correct |
| R06-REVIEW-015 | evidence | — | **CONFIRMED** — R07 residual boundary precise |
| R06-REVIEW-016 | evidence | — | **CONFIRMED** — deferred Issues not smuggled |
| R06-REVIEW-017 | evidence | — | **CONFIRMED** — safety mechanisms not regressed |

### DS Original Findings

| ID | Original Severity | R06-PF | Current Status |
|---|---|---|---|
| F-DS-001 | HIGH | PF-01 | **CLOSED** — guard topology, key, boundary, deadlock avoidance specified |
| F-DS-002 | HIGH | PF-02 | **CLOSED** — materialize residual explicitly deferred to R07 with full inventory |
| F-DS-003 | MEDIUM | PF-04 | **CLOSED** — manifest cross-check explicitly stated as new commit invariant |
| F-DS-004 | MEDIUM | PF-06 | **CLOSED** — CN upload deferral replaced with adjudicated decision |
| F-DS-005 | NO-ACTION | PF-05 | **CONFIRMED** — manifest internal routing covered; PF-05 adds deletion timing |
| F-DS-006 | MEDIUM | PF-08 | **CLOSED** — cumulative reviewability gates specified without magic thresholds |
| F-DS-007 | MEDIUM | PF-07 | **CLOSED** — FsBatchingRepository new composition status explicit |
| F-DS-008 | NO-ACTION | — | **WITHDRAWN** (reviewer error) — file in S1 allowlist |
| F-DS-009 | NO-ACTION | — | **CONFIRMED** — Event/barrier+deadline sufficient |
| F-DS-010 | NO-ACTION | PF-05 | **CONFIRMED** — same as F-DS-005 |

**All 8 material/blocking/HIGH findings from both reviews are CLOSED. No finding was downgraded to residual or "implement later."**

## 5. New Findings (This Re-Review)

### R06-REREVIEW-R01 — Publication-to-public read composition inventory not provided

- **严重程度**: LOW (implementation risk, not plan gap)
- **位置**: Plan §4.2 guarded/unguarded boundary
- **问题类型**: 不可直接实施（implementation discovery risk）
- **当前写法**: Plan §4.2 specifies "public-to-public 组合必须改为 outer guarded entry + private unguarded helper，而不是检测环境状态或重入获取锁" — gives the pattern but not the inventory of current compositions.
- **反例/失败场景**: Implementation agent restructures `get_source()` to acquire guard → call private unguarded helper, but misses that `get_source()` internally called `get_source_meta()` (another public method). At runtime, `get_source()` acquires publication guard, then `get_source_meta()` tries to acquire the same non-reentrant file lock → **self-deadlock**. This is silent at type-check time; only the cross-process smoke test (§8.4 phase 4) would catch it.
- **为什么有问题**: The plan's design constraint ("public never calls public") is clear, but the implementation agent must discover all current composition chains. Missing one chain produces a runtime deadlock, not a type error.
- **直接证据**:
  - Plan §4.2: "不能调用会再次获取非重入文件锁的 public read"
  - `_fs_storage_infra.py:1363-1380`: `_ticker_dir_for_read` routes both meta and file reads — current code composes freely
  - `repository_protocols.py`: `get_source()`, `get_source_meta()`, `get_primary_source()`, `list_source_documents()`, `has_filing_xbrl_instance()` are all public — potential composition chains exist
- **影响**: 实施 Agent 遗漏组合链导致运行期自死锁；smoke test 可能因时序碰巧通过而在生产暴露
- **建议改法和验证点**:
  1. S1 implementation task list should include: "inventory all public read methods and their current call chains; for each public→public call, extract shared logic into a private unguarded helper; both public methods call the private helper after acquiring guard"
  2. §8.4 smoke test phase 4 already covers "outer只获取一次guard、private unguarded helper不自死锁" — this is the correct verification. Ensure this test exercises ALL composed read paths, not just one.
- **修复风险**: LOW — adding an inventory checkpoint to S1 task list, no plan structure change needed
- **Required plan fix**: No plan text change required. Add to S1 implementation task list only.

---

### R06-REREVIEW-R02 — `sec_6k_primary_document_repair.py` independent core construction

- **严重程度**: MEDIUM
- **位置**: Plan §3.5 / §7.3 — four composition roots
- **问题类型**: 切片过粗（refactoring depth understated for one root）
- **当前写法**: Plan §7.3 says S3 must create `FsBatchingRepository` at four roots including `sec_6k_primary_document_repair.py`. Plan §3.5 says "分别...创建一个 `_FsRepositorySet`，并从同一 set 装配新的 `FsBatchingRepository`". But `sec_6k_primary_document_repair.py` does not currently use `build_fs_repository_set` or `_FsRepositorySet` at all — unlike the other three roots.
- **反例/失败场景**: Implementation agent treats all four roots uniformly (add `FsBatchingRepository` constructor call alongside existing code). For `sec_6k_primary_document_repair.py`, this is insufficient — the file must first be refactored to use shared-core construction (`build_fs_repository_set`), THEN add `FsBatchingRepository`. An agent following the uniform pattern creates `FsBatchingRepository` with a new independent core, while the three wrappers still use their separate cores → mutation through batching repo and mutation through wrapper repos go to different `_active_batches` registries → cross-core token rejection fails silently or allows inconsistent state.
- **为什么有问题**: The plan describes a uniform pattern ("four roots, same shared core") but one root has a structurally different starting point. The plan doesn't flag this asymmetry.
- **直接证据**:
  - `sec_6k_primary_document_repair.py:168-171`:
    ```python
    source_repository = FsSourceDocumentRepository(resolved_workspace_root)
    processed_repository = FsProcessedDocumentRepository(resolved_workspace_root)
    company_repository = FsCompanyMetaRepository(resolved_workspace_root)
    ```
    No `repository_set=` parameter → each creates independent `_FsStorageInfra`
  - `rg -n 'build_fs_repository_set|_FsRepositorySet' dayu/fins/pipelines/sec_6k_primary_document_repair.py` → **zero matches**
  - Contrast with `service_runtime.py:347`, `cn_pipeline.py:373`, `sec_pipeline.py:509` — all use `build_fs_repository_set`
  - `fs_batching_repository.py:39-43`: `FsBatchingRepository.__init__` calls `build_fs_repository_set(repository_set=repository_set)` — if `repository_set` is None, it creates a NEW independent core, not sharing with the wrapper-created cores
- **影响**: 实施 Agent 在 `sec_6k_primary_document_repair.py` 创建 `FsBatchingRepository` 但未重构 wrapper 构造 → batching 与 wrapper 使用不同 core → mutation authority 分裂 → 静默状态不一致
- **建议改法和验证点**:
  1. Plan §7.3 should add a note: "`sec_6k_primary_document_repair.py:168-171` 当前每个 wrapper 独立构造（无 shared `_FsRepositorySet`）；S3 必须先引入 `build_fs_repository_set` 创建共享 core，再装配 `FsBatchingRepository` 并传入同一 `repository_set` 给全部 wrapper"
  2. S3 test must assert that `FsBatchingRepository` and all wrappers share the same `_FsRepositorySet` core (e.g., same `id(core)` or mutation through batching repo is visible through wrapper staging)
- **修复风险**: LOW — one sentence clarification in plan §7.3 or §3.5
- **Required plan fix**: Yes — add asymmetry note for `sec_6k_primary_document_repair.py`

---

### R06-REREVIEW-R03 — Two `LocalFileSource` implementations, only one gets guard

- **严重程度**: LOW (layering discipline, not plan gap)
- **位置**: Plan §4.2 / §7.1 S1 allowlist
- **问题类型**: 架构边界（layering leak risk）
- **当前写法**: Plan S1 allowlist includes only `dayu/fins/storage/local_file_source.py`. Plan §4.2 specifies the typed opener for Fins `LocalFileSource.open()`. The separate `dayu/documents/processors/local_file_source.py` (which also implements `Source` Protocol with `open()` + `materialize()`) is not mentioned.
- **反例/失败场景**: A future code change (or current code not yet audited) wraps a Fins `LocalFileSource` in a documents `LocalFileSource` before passing to a processor. The processor calls `.open()` on the documents one → plain `Path.open("rb")` with NO publication guard → read during commit swap window → half/missing source. This is a layering violation (documents layer shouldn't re-wrap storage layer objects), but nothing in the type system prevents it since both satisfy `Source` Protocol.
- **为什么有问题**: The publication guard's effectiveness depends on Fins `LocalFileSource` being the exclusive Source implementation for storage-backed reads. If any adapter, wrapper, or test fixture substitutes a documents `LocalFileSource`, the guard is silently bypassed.
- **直接证据**:
  - `dayu/fins/storage/local_file_source.py:19-47`: Fins `LocalFileSource` — gets publication guard in R06
  - `dayu/documents/processors/local_file_source.py:16-65`: Documents `LocalFileSource` — structurally identical, no guard
  - `dayu/documents/processors/source.py:15-70`: `Source` Protocol — both classes satisfy it
  - `dayu/documents/processors/local_file_source.py:1-5`: Docstring says "提供 documents 层独立的 LocalFileSource，避免从 fins 层导入。fins 层的同名实现保持不动，两者独立存在，维持层级隔离" — intentional separation, but not enforced
- **影响**: 低概率但高影响 — layering violation 导致 publication guard 静默失效
- **建议改法和验证点**:
  1. S1 implementation should add a comment to `dayu/documents/processors/local_file_source.py` noting it must NOT be used to wrap/replace Fins storage `LocalFileSource` (which carries publication guard semantics)
  2. §8.4 smoke test phase 4 already tests `LocalFileSource.open()` through the actual Fins `get_source()` path — this is the correct verification
  3. No plan change required; this is a code review checkpoint
- **修复风险**: LOW — documentation + code review discipline
- **Required plan fix**: No

---

## 6. Controller Re-Review Challenge Points — Direct Answers

### Challenge 1: 跨进程 exclusive publication lock/锁序/非重入 outer-private read 边界

**Answer**: Plan §4.2 specifies all three correctly:
- Exclusive: per-ticker cross-process file lock at `batch_locks/<ticker>.publication.lock`, separate from writer `batch_locks/<ticker>.lock`
- Lock ordering: writer mutex → publication guard (release reverse); reader only publication guard; reverse nesting explicitly forbidden
- Non-reentrant: enforced structurally — public only calls private unguarded helpers, never public; no ambient "held" marker

One residual risk: public-to-public composition inventory not provided (R06-REREVIEW-R01).

### Challenge 2: LocalFileSource delayed typed opener 是否成为 callback/snapshot/ambient seam

**Answer**: No. The opener is explicitly scoped:
- Binds only path/ticker (non-authority inputs)
- Does NOT bind batch, task, thread, or caller identity
- Invoked only by `Source.open()` for lock acquisition + file open
- Plan explicitly forbids: "不增加 public snapshot/revision/lease API 或通用 callback framework"
- Not a callback framework, not a snapshot facade, not an ambient state marker

### Challenge 3: materialize 8文件9调用与 source_snapshot 纠正

**Answer**: Verified by independent `rg` — exactly 8 production files, 9 calls. `source_snapshot.py` correctly excluded (uses upstream `Source.open()` → spool, not bare storage path). Plan inventory is complete and correct.

### Challenge 4: 全 staged-tree validator 是否只消费 canonical owner facts

**Answer**: Yes. All 6 validation rules consume storage-owned canonical facts:
1. `meta.json` ↔ directory routing — storage fact
2. Provenance via `SourceDocumentProvenance.from_meta()` — typed storage owner
3. Files manifest ↔ physical files — storage fact
4. `primary_document` ↔ manifest + physical file — storage fact
5. Filing/material manifest ↔ source directory — storage-owned projection
6. Same-transaction facts in staging tree — storage lifecycle fact

No rule reads from processor output, test fixtures, or reader inference. No producer-owned fact is re-validated.

### Challenge 5: callback required keyword batch 可严格类型化

**Answer**: Yes. Narrow callable Protocol with `__call__(self, filename: str, stream: BinaryIO, *, batch: BatchToken) -> FileObjectMeta`. `partial` binds positional non-authority inputs; `batch` as keyword-only cannot be captured by `partial`. Type-safe at mypy/pyright level. No callback framework introduced.

### Challenge 6: CN/Docling 短事务

**Answer**: Plan §6 specifies: company meta = one short transaction; each Docling document = separate short transaction with caller-provided batch. Company success + document failure = retryable, no cross-transaction rollback. `DoclingUploadService` deletes internal `begin_batch`/`commit_batch`/`rollback_batch`. `_acknowledge_source_before_blob_write` removed via `stage_source_document()` protocol deletion.

### Challenge 7: 四个新 shared-core batching composition

**Answer**: Plan §3.5/§7.3 identifies four roots. Three already use `build_fs_repository_set` (additive change). One (`sec_6k_primary_document_repair.py`) does not — deeper refactoring needed (R06-REREVIEW-R02).

### Challenge 8: S1/S2/S3 累计 reviewability 与最终统一 acceptance 是否可执行

**Answer**: Yes. Structure is executable:
- S1 → Controller verify + MiMo/DS review → fix → S2 → Controller verify + MiMo/DS review → fix → S3 → full tests + unified dual review → acceptance
- Expected type errors from incomplete propagation must be documented, not hidden
- No magic thresholds; Controller adjudicates by semantic owner
- Final unified review on complete R06 diff is the only acceptance gate

Key execution risk: reviewers must distinguish "expected incomplete-propagation type error" from "real slice bug." This is acknowledged in plan §7.0.

## 7. Open Questions

None. All Controller mandatory questions from the original entry validation are answered by the fixed plan. No new product-level questions requiring user re-confirmation.

## 8. Residual Risks

| Risk | Owner | Mitigation |
|---|---|---|
| Public-to-public read composition discovery during S1 implementation | Implementation agent | §8.4 smoke test phase 4 covers self-deadlock detection; S1 task list should include composition inventory |
| `sec_6k_primary_document_repair.py` deeper refactoring | Implementation agent + Controller | R06-REREVIEW-R02 recommends plan clarification; Controller slice review should verify shared-core construction |
| Two `LocalFileSource` implementations — guard only on Fins one | Code review discipline | R06-REREVIEW-R03 documents risk; code review should verify no layering violation |
| S1/S2 trees have expected type errors — reviewers must distinguish from real bugs | MiMo/DS reviewers + Controller | Plan §7.0 requires documenting expected errors; Controller adjudicates ambiguous cases |
| R07 still owns cross-read snapshot/revision for 8 files/9 materialize calls | R07 | Explicitly deferred in plan §11; R06 doesn't weaken this boundary |
| `RuntimeFileLockToken` compatibility with `LocalFileSource.open()` delayed open pattern | Implementation agent | Plan §11 stop condition 3: if filelock can't support the pattern, stop and return to storage owner design |

## 9. Final Plan Review Conclusion

**PASS-WITH-FINDINGS**

All 8 Controller-accepted plan fixes (R06-PF-01..08) are genuinely closed in the fixed plan at SHA `ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43`. Each closure is verified with direct plan-text evidence cross-referenced against production code facts — not plan self-description.

All 10 original DS findings and 17 original MiMo findings have been individually adjudicated: 11 material/blocking/HIGH findings are CLOSED; 16 evidence/no-action findings are CONFIRMED; 1 DS finding is WITHDRAWN (reviewer error).

**New findings from this re-review**:
- **R06-REREVIEW-R01** (LOW): Public-to-public read composition inventory not provided — implementation discovery risk for self-deadlock. No plan text change required; add to S1 task list.
- **R06-REREVIEW-R02** (MEDIUM): `sec_6k_primary_document_repair.py` independent core construction requires deeper refactoring than other three roots. Plan should add one-sentence asymmetry note in §7.3 or §3.5.
- **R06-REREVIEW-R03** (LOW): Two `LocalFileSource` implementations — guard only on Fins one. Layering discipline risk; no plan change required.

No scope creep detected: R07-R11, Issues 142/151/175/177/178, unified authorization, old schema compatibility, security rollback, optional/default batch, ContextVar, or captured batch closures are all correctly excluded.

The plan is **not yet accepted** — Controller must review these findings and determine whether R06-REREVIEW-R02 requires a plan amendment before the next gate. The other two findings (R01, R03) can be addressed as implementation task list items without plan changes.

---

*Review artifact only. No plan/control/product/test/README/design modification. No stage/commit/push/PR.*
