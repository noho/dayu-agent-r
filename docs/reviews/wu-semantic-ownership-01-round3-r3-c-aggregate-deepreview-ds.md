# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C Aggregate Deepreview

## Scope

- Mode: current changes (aggregate deepreview)
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-C`
- Branch: `phaseflow/host-issues-control`
- Base: `7b24b070` (accepted plan commit)
- HEAD: `ec8d5175` (Record R3-C S3 accepted commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-aggregate-deepreview-ds.md`
- Included scope: Full diff `7b24b070..HEAD` — S1, S2, S3 production, test, README, and control bookkeeping changes (62 files, 7202 insertions, 1349 deletions)
- Excluded scope: Pre-existing unchanged code outside diff; pre-existing `edgar` deprecation warnings; tool-security deferred items (explicitly excluded by plan Non-Goals)
- Parallel review coverage: 无

### Reviewed Documents

- `AGENTS.md`
- `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`
- `docs/host/issues-implementation-control.md` (R3-C gate section)
- `docs/phaseflow-umbrella-optimization-control.md` (risk classification and slice constraints)
- S1/S2/S3 controller validation artifacts (3 files)
- S1/S2/S3 code review artifacts (MiMo, DS, adjudication — 12 files)
- S1/S2/S3 implementation artifacts (3 files)
- S1/S2/S3 rereview artifacts (6 files)

### Reviewed Production Files

All production files in the diff were read in full:

- `dayu/fins/storage/_fs_storage_utils.py` (S1)
- `dayu/fins/storage/_fs_storage_infra.py` (S1)
- `dayu/fins/storage/_fs_blob_core.py` (S1)
- `dayu/fins/storage/local_file_store.py` (S1)
- `dayu/fins/storage/repository_protocols.py` (S1)
- `dayu/fins/pipelines/docling_upload_service.py` (S2)
- `dayu/fins/ingestion_runtime.py` (S2 — `_store_downloaded_document` and token lifecycle relevant sections)
- `dayu/fins/pipelines/cn_download_filing_workflow.py` (S2)
- `dayu/fins/pipelines/cn_download_models.py` (S2)
- `dayu/fins/pipelines/cn_download_protocols.py` (S2)
- `dayu/fins/pipelines/cn_download_source_upsert.py` (S2)
- `dayu/fins/downloaders/cninfo_downloader.py` (S2)
- `dayu/fins/downloaders/hkexnews_downloader.py` (S2)
- `dayu/host/wait_adapter.py` (S3)
- `dayu/service/fins_wait_adapter.py` (S3 — new module)
- `dayu/service/host_assembly.py` (S3)

### Reviewed Test Files

- `tests/fins/test_fins_storage_atomicity.py` (S1 — new file, 1196 lines)
- `tests/fins/test_cn_download_workflow.py` (S2 — `_BatchIdentityCnSourceRepository` spy, batch identity assertions)
- `tests/fins/test_docling_upload_service.py` (S2)
- `tests/service/test_fins_wait_adapter.py` (S3 — new file, 797 lines)
- `tests/service/test_import_boundary.py` (S3)
- `tests/service/test_host_assembly.py` (S3)
- `tests/fins/test_fins_ingestion_tools.py` (S3)

### Reviewed README/Control Files

- `dayu/fins/README.md`
- `dayu/README.md`
- `dayu/host/README.md`
- `dayu/service/README.md`
- `tests/README.md`

## Findings

未发现实质性问题。

以下是对六个重点审查维度的逐项检查结果：

### S1 — Storage Identity / Commit Point / Local Durability

1. **Single-component validator** (`_fs_storage_utils.py:30-53`): `_normalize_path_component()` 是所有 ticker/document_id/entry_name/filename 归一化的唯一真源。四个公共入口（`_normalize_ticker`、`_normalize_document_id`、`_normalize_entry_name`、`_normalize_filename`）均直接委托到它。校验覆盖：空值、`.`/`..`、包含 `/` 或 `\`、绝对路径/盘符表达。**通过。**

2. **Object key validator** (`_fs_storage_utils.py:152-179`): `_normalize_object_key()` 按 `/` 拆分后逐段调用 `_normalize_path_component()`，并额外拒绝 leading slash、反斜杠、空 segment。`_local_path_from_uri()` (`:250-279`) 解析 `local://` URI 后通过 `path.relative_to(normalized_root)` 强制 containment。**通过。**

3. **Handle existence check** (`_fs_blob_core.py:142-147`): `store_file()` 现在对 SourceHandle 和 ProcessedHandle 均无条件调用 `_get_handle_meta(handle)`，在构造 file store key 之前校验 handle 对应的 meta.json 存在且可读。ProcessedHandle 不存在时抛 `FileNotFoundError`，不会创建目录或写入 blob。**通过。**

4. **Commit point** (`_fs_storage_infra.py:237-291`): `commit_batch()` 的状态序列为 `BACKED_UP_TARGET` → `SWAPPED_TARGET` → `COMMITTED`。`COMMITTED` journal 是唯一 commit point。该点之前的异常触发 `_rollback_precommit_batch()` (`:334-358`)，将 new target 撤回、backup 恢复；该点之后的 cleanup 失败只记录 diagnostic 并保留 recovery evidence，不将已提交状态伪装成失败。**通过。**

5. **Commit/rollback 双错误传播** (`_fs_storage_infra.py:275-283`): commit error 是 primary exception，rollback error 通过 `raise commit_error from rollback_error` 链入 `__cause__`，并用 `add_note()` 标注 recovery evidence 已保留。符合 `R3-C-PF-05` 契约。**通过。**

6. **目录原子替换** (`_fs_storage_infra.py:293-315`): `_replace_directory()` 使用 `os.replace()`（同文件系统原子 rename），替换后刷新 source/target 父目录。不使用 `shutil.move()`。**通过。**

7. **Journal 原子写入** (`_fs_storage_utils.py:524-551`, `_fs_storage_infra.py:709-739`): `_write_json()` 使用 same-directory unique temp → file flush/fsync → atomic replace → directory fsync。`_write_batch_journal()` 委托到 `_write_json()`，因此 `COMMITTED` journal 与所有 phase journal 都经过完整原子路径。符合 `R3-C-PF-10`。**通过。**

8. **Orphan recovery** (`_fs_storage_infra.py:540-905`): `_recover_single_batch_dir()` (`:777-861`) 对 `SWAPPED_TARGET` 且无 `COMMITTED` 的 case 执行：删除 new target（若 staging 尚存则先移动回去保留证据），恢复 backup。这与 plan 要求的 `R3-C-PF-04` 语义反转一致——不再像旧代码那样保留 new target、删除 backup。`STARTED`/`BACKED_UP_TARGET` 也正确回滚。`COMMITTED` case 只清理 backup。**通过。**

9. **LocalFileStore 落盘** (`local_file_store.py:42-95`): `put_object()` 使用 UUID temp file → chunked write → file flush/fsync → atomic replace → directory fsync → temp cleanup。digest/size 来自实际写入 bytes。写入/fsync/replace 任一失败时清理 temp 并透传原异常。**通过。**

10. **闭合性检查**: 无 caller/downstream 侧通过 fallback、特例、重算、loose parsing 或兼容 shim 补偿 storage truth 的证据。所有 identity/commit/durability 语义归 storage owner。**通过。**

### S2 — Upload / Download / CN-HK Single-Filing Atomicity

1. **Upload 文档级批次** (`docling_upload_service.py:330-430`): 所有非 delete mutation（create/update/overwrite）在一个 caller-owned batch 内完成。转换/文件校验在 batch 外。`_acknowledge_source_before_blob_write()` (`:524-581`) 的 docstring 明确声明"只复用当前 shared storage core 的活动 batch；不创建、不提交、不回滚 batch"。**通过。**

2. **Token 生命周期** (`docling_upload_service.py:331-430`): `commit_started = False` → batch 内 mutation → `commit_started = True` → `commit_batch(token)`。`finally` 块仅在 `not commit_started` 时 `rollback_batch(token)`。从 `commit_batch()` 调用起 token 归 storage owner，caller 不再回滚。operation/rollback 双错误通过 `raise operation_error from rollback_error` 传播。符合 `R3-C-PF-02`、`R3-C-PF-03`。**通过。**

3. **Generic download 文档级批次** (`ingestion_runtime.py:3748-3825`): `_store_downloaded_document()` 使用相同的 `commit_started` 模式。单个 batch 内包含：reset（overwrite 时）→ create_source_document → blob writes → update_source_document（带 file metas）→ processed reprocess 标记 → commit。**通过。**

4. **CN/HK filing 批次** (`cn_download_filing_workflow.py:404-568`): `_commit_cn_filing_assets_batch()` 和 `_commit_cn_filing_metadata_batch()` (`:571-659`) 均使用相同的 `commit_started`/`finally` rollback 模式。网络下载、Docling 转换、进度 `yield` 在 batch 外完成。`_rollback_cn_batch_preserving_primary()` (`:662-693`) 提供一致的 rollback/error-chaining helper。**通过。**

5. **`commit_cn_filing_source_document()` 定位** (`cn_download_source_upsert.py:191-268`): 函数 docstring 明确声明为 stage-only helper，在 caller batch 内执行 final meta 与 processed marker，不开启、提交或回滚 batch。fast-skip (`:246-262`) 与 normal-convert (`:536-552`) 两个 call site 均处于同一个 caller batch。符合 `R3-C-PF-01`。**通过。**

6. **CN/HK temp PDF 消除**: `DownloadedReportAsset` (`cn_download_models.py:232-251`) 的 `pdf_path: Path` 已替换为 `pdf_bytes: bytes`。CNInfo downloader (`cninfo_downloader.py:300-340`) 和 HKEX downloader (`hkexnews_downloader.py:307-338`) 不再使用 `tempfile`、`NamedTemporaryFile` 或 `delete=False`，直接返回 `DownloadedReportAsset(pdf_bytes=payload, ...)`。workflow 直接消费 `asset.pdf_bytes`，不再有 `_unlink_temp_pdf()` 或 path read/unlink 分支。全仓扫描 `NamedTemporaryFile|dayu_cn_downloads|dayu_hk_downloads|pdf_path` 在生产与测试代码中零匹配。符合 `R3-C-PF-06`。**通过。**

7. **字节契约**: CN/HK downloader 的 HTTP client 已有 `response.content` 在内存中；改为 `pdf_bytes` 消除了额外的 temp 磁盘往返和 cleanup seam，不改变 URL/TLS/redirect/retry 行为，不新增 remote byte budget。**通过。**

8. **闭合性检查**: 所有 caller 的 batch 内不含 `await`/`yield`；`commit_batch()` 返回后无 caller-side rollback；取消/异常/generator close 路径不会遗留 partial source/blob/processed 状态。测试 spy（`_BatchIdentityCnSourceRepository`）验证了 reset → ack → PDF blob → Docling blob → final meta → processed marker 全部使用同一个 active token。**通过。**

### S3 — Host Adapter Snapshot / Service-Owned Fins Wait Glue

1. **Host snapshot 定义** (`wait_adapter.py:237-265`): `WaitAdapterSnapshot` 是 frozen/slots dataclass，字段严格限定为 `tool_name: str`、`resume_token: str`、`created_at: datetime`。无 wait_id、status、deadline、row mutator 或 durable module 类型泄露。**通过。**

2. **Host projection** (`wait_adapter.py:2257-2276`): `_adapter_snapshot_from_wait_record()` 使用 Host 的 `parse_utc_timestamp()` 将 `WaitRecordRow.created_at: str` 转为 timezone-aware UTC `datetime`。resume token 通过 `_validate_adapter_snapshot_resume_token()` (`:2279-2290`) 做 trim-判空和长度校验。非法 token 或 timestamp 统一抛 `WaitAdapterSnapshotProjectionError` 并以原校验异常为 `__cause__`。**通过。**

3. **Poller 错误路由** (`wait_adapter.py:1082-1092`): snapshot projection 失败时 poller 进入 `ADAPTER_ERROR` + backoff 路径，adapter 不被调用。后续 `abandon_cancelled_wait` 同理 (`:1335-1349`)。Service 侧没有 parser/default-now/token 容错分支。符合 `R3-C-PF-08`。**通过。**

4. **Service adapter 边界** (`dayu/service/fins_wait_adapter.py`): 该模块 import `dayu.host.api` (public API types: `ResolveWait*Outcome`, `WaitAdapterKey`) 和 `dayu.host.wait_adapter` (public adapter types: `WaitAdapterSnapshot`, `WaitPollResult`, etc.)，但**不** import `dayu.host.durable`。adapter 只读取 snapshot 的三个字段，不访问 wait id、status、deadline 或 durable store。**通过。**

5. **Fins → Host import 消除**: 全仓扫描 `rg -n '(^|[[:space:]])(from|import)[[:space:]]+dayu\.host' dayu/fins --glob '*.py'` 返回零匹配。旧 `dayu/fins/ingestion/wait_adapter.py` 已删除，无兼容 re-export、wrapper、facade 或 lazy import。**通过。**

6. **Service 装配** (`host_assembly.py:29-36`): 从同层 `dayu.service.fins_wait_adapter` import builder 函数，不穿透到 Fins storage 或 Host durable。Service import boundary test (`tests/service/test_import_boundary.py`) 维持 `dayu.host.durable` 禁止规则，只对明确的 Fins observation/direct-event/tool-name imports 放行。**通过。**

7. **行为等价性**: `WaitActivationRequest`、Host wait state machine、registry shape、adapter key (`poll:fins-ingestion`)、tool names、poll result mapping 与 LLM-facing result 文本未变。S3 controller validation 的 focused test matrix（326 passed）覆盖了 poll/activation/abandon/boundary 全部路径。**通过。**

8. **闭合性检查**: Fins 无 Host import，Service adapter 不 import Host durable internals。host_assembly 从同层 module import。existing wait/poll/activation behavior 矩阵通过。符合 plan `F5` 和 Non-Goals 全部约束。**通过。**

### Tests — Owner-Level Contract Assertions

1. **S1 `test_fins_storage_atomicity.py`** (1196 行，新文件): 直接测试 storage owner 的 identity validator、object key owner、local URI containment（含 symlink escape）、commit phase failure injection（backup_rename/backed_journal/staging_rename/swapped_journal/committed_journal 五个注入点）、orphan recovery（含 `SWAPPED_TARGET` 无 `COMMITTED` 的反转 case）、double-failure primary/`__cause__` 链、LocalFileStore 原子落盘。使用真实 tmp_path 和 owner-level seam injection（monkeypatch `_replace_directory`/`_write_batch_journal`），不依赖 call-count mock。**通过。**

2. **S2 `test_cn_download_workflow.py`**: 使用 `_BatchIdentityCnSourceRepository` spy（继承 `FsSourceDocumentRepository`）记录 batch identity 和 phase 顺序，断言 reset → ack → PDF blob → Docling blob → final meta → processed marker 均在同一个 caller-owned active batch 内完成。测试覆盖 success、cancel after conversion、commit failure、fast skip、PDF-SHA skip 路径。使用 `_PDF_BYTES` 和 `_DOCLING_BYTES` 常量，无 temp file 依赖。**通过。**

3. **S2 `test_docling_upload_service.py`**: 断言 create 失败后 source/blob 均不存在、overwrite/update 失败后旧 meta/blob 完全不变。不再固化"final upsert 失败后保留 incomplete staging"的旧行为。**通过。**

4. **S3 `tests/service/test_fins_wait_adapter.py`** (797 行，新文件): 测试 Service adapter 的 binding 构造、poll result 映射（PENDING/RUNNING→not_ready, SUCCEEDED→completed, FAILED→failed, CANCELLED→cancelled, LOST→lost）、activation flow、abandon lifecycle。adapter fake 只收到 `WaitAdapterSnapshot` 三个允许字段，不包含 wait_id/status/deadline/row mutator。**通过。**

5. **Fins 层测试**: `test_fins_ingestion_tools.py` 和 `test_fins_ingestion_runtime.py` 不再 import Host/Service wait adapter contract。**通过。**

6. **闭合性检查**: 无旧 fixture/fake/Host durable shape 固化到 Fins 层的证据。测试断言跟随实现边界迁移到 owner-level contract。**通过。**

### README / Control Docs

1. **`dayu/fins/README.md`**: 架构图更新为 "Service Fins wait adapter assembly"，删除了 Fins wait-adapter Host import 例外。记录了 storage single-component/object-key、per-document atomic mutation、temp-less CN/HK downloaded asset 与 Service-owned adapter assembly 的当前落地事实。**通过。**

2. **`dayu/README.md`**: 跨包边界描述更新为 "Service-owned wait adapter"，不写 WU 过程。**通过。**

3. **`dayu/host/README.md`** (4 行变更): 记录了 Host poller 向 external adapter 只投影 minimal `WaitAdapterSnapshot`，durable row/claim/backoff 仍为 Host 内部真源。**通过。**

4. **`dayu/service/README.md`** (6 行变更): 记录了 `dayu.service.fins_wait_adapter` 作为 Fins observation 到 Host typed adapter registry 的 approved composition seam。**通过。**

5. **`tests/README.md`** (8 行变更): 将 Fins wait adapter registry/mapping 测试从 `tests/fins` 迁到 `tests/service`，补充了 storage commit/ingestion atomicity/temp-less cancellation 矩阵说明。**通过。**

6. **Control docs**: `docs/host/issues-implementation-control.md` 和 `docs/phaseflow-umbrella-optimization-control.md` 按 plan 规定仅由 controller 更新 gate 状态/artifact，implementation agent 未修改。当前 R3-C gate 状态与 S1/S2/S3 accepted commits 一致。**通过。**

7. **闭合性检查**: 无 stale owner 引用、无 stale next gate 描述。READM 只记录已落地边界，不写 WU 过程或未来计划。**通过。**

### Tool-Security Scope Exclusion

1. **Upload allowlist/file authority/symlink-safe upload source policy**: S1 的 symlink containment 测试 (`test_fins_storage_atomicity.py:196-220`) 测试的是 `local://` object key 在 storage root 下的 containment——这是 storage identity 行为，不是 tool security。`docling_upload_service.py` 的 `_validate_source_files()` (`:796-820`) 只校验文件存在、普通文件、suffix，未新增 allowlist/authority 逻辑。**通过（deferred，未实现）。**

2. **URL/TLS/redirect/SSRF provenance**: CN/HK downloader 的 HTTP 请求行为未改变（URL、redirect、TLS、retry 逻辑不变）。仅将已存在于内存中的 `response.content` 直接交给 `DownloadedReportAsset.pdf_bytes`，删除 temp I/O seam。**通过（deferred，未实现）。**

3. **Remote byte budget**: 未新增 download byte cap、streaming limit 或 response allocation policy。**通过（deferred，未实现）。**

4. **LLM-facing security schema/prompt/tool schema**: `git diff -- dayu/config/prompts dayu/fins/tools dayu/config/tool_discovery.json` 确认无变更。tool name/description/parameter schema/error wording/prompt 均未修改。**通过（deferred，未实现）。**

5. **闭合性检查**: 全部 4 项 deferred tool-security items 在 R3-C 中保持 `assigned to later work unit` 状态，未以"顺手加校验"的形式进入实现。storage local URI symlink containment 正确分类为 storage identity。**通过。**

## Adversarial Failure Pass Summary

对以下高风险面执行了逐路径走读，未发现新增缺陷：

| 风险面 | 走读路径 | 结论 |
| --- | --- | --- |
| commit phase 注入 | `commit_batch` 五个 phase 各注入一次失败 → pre-commit rollback → target/backup/staging/journal 物理状态验证 | 通过 |
| commit+rollback 双错误 | commit error + rollback error 同时发生 → primary/`__cause__`/note 传播 → recovery evidence 保留 | 通过 |
| crash recovery | `SWAPPED_TARGET` 无 `COMMITTED` → new target 删除、backup 恢复（语义反转） | 通过 |
| cancel during batch | CN/HK filing `cancel_checker` 在 batch 内各阶段边界命中 → `CnDownloadCancelledError` → `finally` rollback → 旧状态/absence 不变 | 通过 |
| generator close | CN/HK workflow 的 `aclose()` / task cancel 在 commit 前命中 → batch rollback → 无 partial document、无 temp PDF | 通过 |
| upload create failure | blob write / final upsert / commit 任一点失败 → source absent、blob absent、processed 不变 | 通过 |
| upload overwrite failure | reset 后、blob write / final upsert / commit 任一点失败 → old source meta 与 old blobs 不变 | 通过 |
| generic download failure | source/blob/processed/commit 任一点失败 → document absent、processed 不变 | 通过 |
| snapshot projection failure | 空/超长 resume token 或非法 timestamp → `WaitAdapterSnapshotProjectionError` → adapter 不被调用 → ADAPTER_ERROR backoff | 通过 |
| abandon error routing | `WaitAdapterSnapshotProjectionError` at abandon → ABANDON_ERROR backoff；adapter 异常 → 按 TRANSIENT/PERMANENT 分类路由 | 通过 |
| handle existence | SourceHandle/ProcessedHandle 不存在 → `store_file()` 抛 `FileNotFoundError` → `FileStore` 未被调用、target key 未创建 | 通过 |
| object key traversal | 非法 key（空、绝对路径、`..` 段、反斜杠、空段）→ `LocalFileStore.put_object()` 抛 `ValueError` → workspace 外无文件变化 | 通过 |
| local URI containment | symlink escape → `path.relative_to()` 失败 → `ValueError` → 不做 basename fallback | 通过 |

## Open Questions

无。

## Residual Risk

| Risk | Classification | Owner / Destination |
| --- | --- | --- |
| OS/hardware 在 rollback rename 本身失败时可能暂时留下需 recovery 的物理目录 | Covered by S1 recovery contract；若恢复证据也不可读则需 explicit user decision | `dayu.fins.storage` orphan recovery |
| Directory fsync 在不支持的 platform 上只能 best-effort | Assigned to later WU | Fins filesystem backend portability |
| 已成功提交的前一 document 不会因后续 document 失败回滚 | Accepted non-goal | Multi-document transaction WU |
| CN/HK Docling 同步第三方转换在线程内不能强制中断 | Tracked by existing deferred finding | Future process/subprocess isolation WU |
| Tool-security 四项 | Assigned to later WU | 独立 tool-security WU |
| `_execute_with_auto_batch` 的 rollback 错误传播未使用 `raise ... from rollback_error` 链（仅用 `add_note`） | Pre-existing，不在 R3-C scope | 非 document-mutation 路径（manifest upsert、entry delete），low risk |
| `docling_upload_service.py` 有独立 `_normalize_ticker` 实现（`:999-1018`）不调用 storage owner 的 single-component validator | Pre-existing，storage owner 的 `_normalize_ticker` 是最终 gate | 未来可考虑合并 consumer-side normalizer，lower priority |

## Review Conclusion

**PASS** — 在全部六个重点审查维度上均未发现 correctness、semantic ownership、contract 或 test gap 缺陷。R3-C S1/S2/S3 的 implementation 与 plan 的 contract decisions（包括 `R3-C-PF-01` 到 `R3-C-PF-10` 全部 plan flag）一致。Storage identity/commit/recovery owner 闭环完整，无 caller/downstream 补偿。Upload/download/CN-HK single-document atomicity 使用 caller-owned active batch + storage-owned commit point 的统一模式。CN/HK asset 契约已从 temp PDF path handoff 迁移到 `pdf_bytes`。Fins→Host 反向依赖已删除，Service wait adapter 只使用 Host public snapshot/outcome contract。Tests 断言 owner-level contract，不固化旧 fixture/behavior。READM 记录已落地边界，无 stale owner。工具安全 deferred items 保持 excluded。
