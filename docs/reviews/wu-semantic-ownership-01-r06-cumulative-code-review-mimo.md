# R06 Cumulative S1+S2+S3 Complete Code Review — AgentMiMo

## Scope

- **Mode**: Current Changes Mode (unstaged working tree relative to HEAD commit `d048adf7`)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `d048adf7` (HEAD, `docs: enter R06-S1 implementation gate`)
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-mimo.md`
- **Included scope**: 57 files (39 production, 16 test, 2 README, 1 docs control), +9951/-3589 lines
- **Excluded scope**: None — all unstaged changes reviewed
- **Parallel review coverage**: 6 subagents covered: storage infra/protocols, 5 core mixins, 6 repository facades, 15 pipelines, domain models/runtime/downloader, 8 test/README files. Uncovered: `sec_download_state.py` (14-line change, trivial state enum), `sec_company_meta.py` (24-line change, hardcoded market only), `upload_company_meta.py` (7-line change), `cn_download_company_meta.py` (6-line change).

## Plan And Design Alignment Verification

| Claimed R06 Requirement | Verified? | Evidence |
|---|---|---|
| 54 production mutation required `batch=` | ✅ | All 39 production files checked; every mutation method has `*, batch: BatchToken` keyword-only parameter |
| Callback invocation-time token | ✅ | `sec_downloader.download_files_stream` passes `batch=token` to each `store_file` call at invocation time |
| CN/SEC/Docling blob-first final-once | ✅ | All pipelines write blobs before source meta; single `commit_batch` at end |
| Company/document/maintenance transaction separation | ✅ | Separate `begin_batch`/`commit_batch` cycles for company, per-document, and maintenance |
| Rebuild/6-K source+processed same batch | ✅ | Both CN and SEC rebuild use single batch for `update_source_document` + `mark_processed_reprocess_required` |
| Commit starts → no second rollback | ✅ | `commit_started` flag pattern prevents double rollback |
| 4 composition roots shared core | ✅ | `cn_pipeline`, `sec_pipeline`, `docling_upload_service`, `ingestion_runtime` all create `FsBatchingRepository` from shared `_FsRepositorySet` |
| Two `False` for validator negative tests | ✅ | `test_fins_storage_provider.py:1408` and parametrized 22-case grid includes `"false_completion"` |
| S3-CV-F01 closed | ✅ | Direct preprocess selection owner test exists at `test_fins_storage_provider.py:1408` |
| tests/README truth | ✅ | README accurately describes test coverage; no discrepancies with actual test code |
| pyright 0 errors | ⚠️ | Claimed by S3 implementation artifact; not independently re-verified in this review |
| 723 tests passed | ⚠️ | Claimed by S3 implementation artifact; not independently re-run in this review |

## Findings

### R06-CR-MIMO-F01-未修复-严重-journal phase ordering causes post-swap data loss on first commit

- **入口/函数**: `commit_batch` → swap sequence
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:349-354`
- **输入场景**: 首次为某 ticker commit（无已发布数据），进程在 staging→target rename 成功后、`_PHASE_SWAPPED_TARGET` journal 写入前被 SIGKILL/OOM/断电
- **实际分支**: `_PHASE_BACKED_UP_TARGET` (line 351) 写入后，`_replace_directory` (line 352) 将 staging rename 为 target，然后进程崩溃
- **预期行为**: 已提交数据在 recovery 后应保留在 published tree 中
- **实际行为**: Recovery 看到 phase=`_PHASE_BACKED_UP_TARGET`、target 存在、staging 不存在、backup 不存在 → line 1330 `_replace_directory(target, staging)` 将已提交数据移回 staging → line 1358 `_remove_directory(token_dir)` 删除 staging → **数据永久丢失**
- **直接证据**:
  - line 352: `self._replace_directory(state.staging_ticker_dir, state.target_ticker_dir)` — swap 完成
  - line 353: `self._write_batch_journal(state, _PHASE_SWAPPED_TARGET)` — journal 在 swap 之后
  - line 1320-1330: recovery 对 `_PHASE_BACKED_UP_TARGET` 和 `_PHASE_SWAPPED_TARGET` 同等处理
  - line 1327-1330: `if staging_dir.exists(): remove target; else: replace target→staging`
  - line 1358: `self._remove_directory(token_dir)` — 删除 staging root
- **影响**: 首次 commit 场景下，已成功提交的数据在 crash recovery 后永久丢失。后续 commit 场景下，当前 batch 数据丢失但旧数据从 backup 恢复。
- **建议改法和验证点**: 将 `_PHASE_SWAPPED_TARGET` journal 写入移到物理 swap 之前（line 352 和 353 互换）。Recovery 对 `_PHASE_SWAPPED_TARGET` 的处理应为：如果 staging 不存在（swap 完成），直接进入 COMMITTED；如果 staging 存在（swap 未完成），执行 reverse swap。或者更简单地：以 staging 是否存在作为 swap 是否完成的唯一判据，不依赖 journal phase。
- **修复风险（低/中/高）**: 中 — 需要同步修改 journal 写入顺序和 recovery 逻辑
- **严重程度（低/中/高/严重）**: 严重

### R06-CR-MIMO-F02-未修复-高-SEC rebuild 用 except Exception 而非 BaseException 捕获导致 batch 泄漏

- **入口/函数**: `_rebuild_single_document` (SEC rebuild)
- **文件(行号)**: `dayu/fins/pipelines/sec_rebuild_workflow.py:445`
- **输入场景**: 用户在 SEC rebuild 执行 source/processed mutation 期间按 Ctrl+C 或进程收到 SIGTERM
- **实际分支**: `except Exception as exc:` 不捕获 `KeyboardInterrupt`/`SystemExit`
- **预期行为**: batch 应在任何异常（包括 BaseException）下被 rollback，与 CN rebuild (`cn_download_rebuild.py:247`) 行为一致
- **实际行为**: `KeyboardInterrupt` 跳过 `except Exception`，batch 不被 rollback，staging 数据泄漏为 orphan
- **直接证据**:
  - `sec_rebuild_workflow.py:445`: `except Exception as exc:`
  - `cn_download_rebuild.py:247`: `except BaseException:` — CN 对照正确
  - `sec_download_filing_workflow.py:617-619`: 使用 `finally` block — SEC download 对照正确
- **影响**: 取消/中断导致 staging orphan，需等待下次 `recover_orphan_batches` 清理
- **建议改法和验证点**: 改为 `except BaseException:` 或使用 `finally` block 模式（与 CN rebuild 一致）。验证：在 batch mutation 中注入 `KeyboardInterrupt`，确认 staging 被清理。
- **修复风险（低/中/高）**: 低 — 单行修改
- **严重程度（低/中/高/严重）**: 高

### R06-CR-MIMO-F03-未修复-高-publication guard 释放失败可永久死锁 ticker

- **入口/函数**: `commit_batch` → finally block → `_release_lock_token`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:362-380`
- **输入场景**: commit 成功后 `_release_lock_token(publication_token)` 抛出异常（如文件系统错误、权限问题）
- **实际分支**: `_release_lock_token` 抛出异常 → `post_commit_error = release_error` → raise → 但 OS 级 lock 可能未释放
- **预期行为**: publication guard 应有 force-release 兜底机制，或 `recover_orphan_batches` 应清理遗留 publication lock
- **实际行为**: `_close_active_batch` (line 425) 只处理 writer mutex，不处理 publication guard。`recover_orphan_batches` 也不尝试 force-release publication lock。后续 `commit_batch` 对同一 ticker 将在 `_acquire_publication_guard(blocking=True)` 上永久阻塞。
- **直接证据**:
  - line 362-364: `self._release_lock_token(publication_token)` 在 finally 中，但异常被 catch 后只记录/raise
  - line 425: `self._close_active_batch` 清理 `_active_batches` registry 和 writer mutex，不涉及 publication guard
  - `recover_orphan_batches` 无 publication lock 清理逻辑
- **影响**: ticker 级永久死锁，直到进程重启且手动清理 OS 级 lock file
- **建议改法和验证点**: 在 `_close_active_batch` 或 error path 中添加 publication guard force-release 兜底。或在 `recover_orphan_batches` 中添加 orphan publication lock 清理。验证：mock `_release_lock_token` 抛异常，确认 ticker 不被永久锁死。
- **修复风险（低/中/高）**: 中 — 需要评估 force-release 的安全性
- **严重程度（低/中/高/严重）**: 高

### R06-CR-MIMO-F04-未修复-ingestion_runtime 三处 rollback error handling 不一致

- **入口/函数**: `_store_downloaded_document`, `_preprocess_one_document`, `_store_rejected_filing_artifact`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:3835-3847` vs `:4161-4165` vs `:3977-3981`
- **输入场景**: batch mutation 失败后 rollback_batch 本身也抛异常
- **实际分支**: `_store_downloaded_document` 使用 `sys.exception()` 保留原始异常并链式传播 rollback 失败；`_preprocess_one_document` 和 `_store_rejected_filing_artifact` 使用 bare `rollback_batch` 调用，rollback 异常替换原始异常
- **预期行为**: 三处应统一使用 `sys.exception()` + rollback chaining 模式
- **实际行为**: 后两处 rollback 失败时丢失原始操作异常，调试困难
- **直接证据**:
  - `:3837`: `operation_error = sys.exception()` + `:3842-3846`: `raise operation_error from rollback_error`
  - `:4164-4165`: `self.batching_repository.rollback_batch(batch)` — bare call, no exception chaining
  - `:3980-3981`: 同上
- **影响**: preprocess 和 rejected-artifact 路径的 batch 失败调试困难
- **建议改法和验证点**: 将 `_preprocess_one_document` 和 `_store_rejected_filing_artifact` 的 rollback 改为与 `_store_downloaded_document` 一致的 `sys.exception()` 模式。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F05-未修复-BatchToken 公开字段违反不透明契约

- **入口/函数**: `BatchToken` dataclass
- **文件(行号)**: `dayu/fins/domain/document_models.py:414-425`
- **输入场景**: 任何持有 `BatchToken` 的代码可读取 `token.transaction_id` 和 `token.ticker`
- **实际分支**: `@dataclass(frozen=True)` 自动生成公开 `__init__`、`__repr__`、`__eq__`、`__hash__`
- **预期行为**: docstring 声明"不透明事务标识"，外部代码不应能访问内部字段
- **实际行为**: `transaction_id` 和 `ticker` 都是公开属性，`__repr__` 直接暴露内部结构
- **直接证据**: line 419: docstring "storage 生成的不透明事务标识"；line 423-424: `transaction_id: str` / `ticker: str` — 公开字段
- **影响**: 外部代码可 pattern-match on transaction_id 格式或用 `batch.ticker` 替代显式 ticker 参数，创建隐式耦合
- **建议改法和验证点**: 如需真正不透明，使用 `__slots__` + property 只暴露 token 给 storage 层验证用的 equality/hashing。或者接受当前设计，更新 docstring 移除"不透明"声明。
- **修复风险（低/中/高）**: 中 — 涉及所有消费 `batch.ticker` 的代码路径
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F06-未修复-BatchToken 缺少 __post_init__ 验证

- **入口/函数**: `BatchToken.__init__`
- **文件(行号)**: `dayu/fins/domain/document_models.py:414-425`
- **输入场景**: `BatchToken(transaction_id="", ticker="")` 或 `BatchToken(transaction_id="  ", ticker="  ")`
- **实际分支**: 无 `__post_init__`，空字符串和空白字符串被接受
- **预期行为**: 同文件其他 model（`DownloadRejectionEntry`、`SourceDocumentRevision`）都有 `__post_init__` 验证非空/格式
- **实际行为**: 无效 token 静默传播到 storage 层，产生远离根因的 cryptic 错误
- **直接证据**: line 414-425 无 `__post_init__`；同文件 `DownloadRejectionEntry.__post_init__` 验证所有字符串非空
- **影响**: 无效 token 传播到 `_resolve_active_batch` 时才报错，错误消息不指向根因
- **建议改法和验证点**: 添加 `__post_init__` 验证 `transaction_id` 和 `ticker` 非空且 strip 后非空。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F07-未修复-ProcessedManifestItem 字段从 raw merged_meta 派生无 storage-owner 验证

- **入口/函数**: `_upsert_processed` → `ProcessedManifestItem` 构造
- **文件(行号)**: `dayu/fins/storage/_fs_processed_core.py:420`
- **输入场景**: producer 传入错误/空的 `material_name`、`fiscal_year` 等字段
- **实际分支**: `material_name=merged_meta.get("material_name")` 直接从 raw meta 取值，无 storage-owner 校验
- **预期行为**: 与 source document 的 `SourceDocumentProvenance.from_meta` 类似，应有 processed-side 的 manifest field 校验
- **实际行为**: 错误值静默传播到 manifest → `list_documents` → `DocumentSummary` → UI/LLM
- **直接证据**: line 420: `material_name=merged_meta.get("material_name")`；对比 source 路径有 `SourceDocumentProvenance.from_meta` 校验
- **影响**: UI/LLM 展示错误的 material_name/fiscal_year 等
- **建议改法和验证点**: 添加 processed manifest field 校验（至少非空检查），或接受当前设计并记录 manifest 字段的 producer responsibility。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F08-未修复-DocumentSummary.from_dict 对缺失 source_kind 静默默认 filing

- **入口/函数**: `DocumentSummary.from_dict`
- **文件(行号)**: `dayu/fins/domain/document_models.py:847`
- **输入场景**: processed manifest item 缺失 `source_kind` 字段（上游 bug）
- **实际分支**: `source_kind=str(data.get("source_kind", "filing"))` — 默认 `"filing"`
- **预期行为**: 缺失必填字段应报错，不静默掩盖数据损坏
- **实际行为**: 所有缺失 `source_kind` 的 item 静默显示为 filing
- **直接证据**: line 847: `data.get("source_kind", "filing")` — 默认值
- **影响**: 数据损坏被静默掩盖，下游 `list_documents` 返回错误分类
- **建议改法和验证点**: 改为 `data["source_kind"]` 让 KeyError 暴露上游 bug，或使用 `data.get("source_kind")` + 非空校验。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F09-未修复-list_rejected_filing_artifacts 静默吞没损坏条目

- **入口/函数**: `list_rejected_filing_artifacts`
- **文件(行号)**: `dayu/fins/storage/_fs_maintenance_core.py:333-375`
- **输入场景**: rejection artifact 目录下的 `meta.json` 损坏或缺失
- **实际分支**: `except (FileNotFoundError, ValueError)` per entry — 跳过损坏条目，仅 log warning
- **预期行为**: 调用方应能得知结果不完整（partial result + warning），或损坏条目应 fail-closed
- **实际行为**: 返回 `list[RejectedFilingArtifact]`，无 side-channel 表示有条目被跳过
- **直接证据**: line 333-375: try/except per entry, log warning, continue；facade `fs_filing_maintenance_repository.py:200-218` 直接委托，无 partial-result 机制
- **影响**: 调用方比较 rejection count 与 download workflow count 时会得到不匹配且无解释
- **建议改法和验证点**: 返回类型改为 `(list, list[str])` tuple（结果 + 跳过条目警告），或添加 `skipped_count` 属性。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F10-未修复-_upsert_processed 写入顺序导致 partial staging 不可恢复

- **入口/函数**: `_upsert_processed`
- **文件(行号)**: `dayu/fins/storage/_fs_processed_core.py:378-410`
- **输入场景**: sections/tables 写入成功但 meta 写入失败（如 JSON 序列化错误）
- **实际分支**: line 378-383 写 sections/tables/financials → line 408 写 meta（可能失败）
- **预期行为**: staging 状态应一致——要么全部写入，要么全部不写
- **实际行为**: 目录存在（line 369 check）但 meta.json 不存在 → 后续 `update_processed` raise `FileNotFoundError`，`create_processed` raise `FileExistsError`，均不可恢复
- **直接证据**:
  - line 369: `if is_create and exists: raise FileExistsError`
  - line 371: `if not is_create and not exists: raise FileNotFoundError`
  - line 378-383: sections/tables 先写
  - line 408: meta 后写（可失败）
- **影响**: 中间写入失败导致 staging 进入不可恢复状态，只能 rollback_batch
- **建议改法和验证点**: 先写 meta（或写到临时文件再 rename），再写 sections/tables。或在 meta 写入前不创建目录。
- **修复风险（低/中/高）**: 低 — 调整写入顺序即可
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F11-未修复-complete-source validator 不校验 processed/company/rejection

- **入口/函数**: `_validate_complete_source_tree`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:429-454`
- **输入场景**: batch 创建了 processed documents 但对应的 source files 不完整
- **实际分支**: validator 只检查 source directory/manifest/files，不检查 processed/、company meta、rejections
- **预期行为**: "complete-source validator enforces all required data present before commit" 应覆盖所有 artifact 类型
- **实际行为**: 不一致的 processed documents（引用不存在的 source files）可通过 validator 进入 published tree
- **直接证据**: line 429-454: `_validate_complete_source_tree` 只校验 source kind tree
- **影响**: published tree 中 processed documents 与 source files 不一致（可通过 reprocessing 恢复）
- **建议改法和验证点**: 扩展 validator 范围，或在 docstring 中明确 validator 只覆盖 source completeness，processed consistency 由 reprocessing 保证。
- **修复风险（低/中/高）**: 低 — 取决于是否扩展 scope
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F12-未修复-blob-first staging ordering 仅靠调用方遵守，storage 层不强制

- **入口/函数**: storage 层 commit-time validation
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:429-732`
- **输入场景**: 调用方先写 source meta 后写 blob（违反 blob-first 设计约束）
- **实际分支**: commit-time validator 检查文件存在性，但不检查写入顺序
- **预期行为**: design constraint "blob-first staging" 应在 storage 层有 write-time 或 commit-time 强制
- **实际行为**: 只要 commit 时 meta 和 blob 都存在，validator 通过。顺序约束完全靠调用方。
- **直接证据**: `_validate_complete_source_files` (line 652-732) 只检查 files 存在、size、sha256，不检查写入时序
- **影响**: 无数据损坏（commit validator catch），但 defense-in-depth 缺口
- **建议改法和验证点**: 在 source meta upsert 时检查对应 blob 已存在于 staging，或接受当前设计并记录 blob-first 是 caller responsibility。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F13-未修复-concurrent reader barrier 测试依赖 timing 可能 vacuously pass

- **入口/函数**: `test_concurrent_reader_blocks_at_each_publication_rename_barrier`
- **文件(行号)**: `tests/fins/test_fins_storage_atomicity.py:2260`
- **输入场景**: CI 环境负载高或 macOS 热节流
- **实际分支**: `assert not parent_connection.poll(0.25)` — 250ms timing window
- **预期行为**: 测试应 deterministic 地证明 reader 被 barrier 阻塞
- **实际行为**: reader 可能在 250ms 内完成读取（在 guard acquire 前），测试 vacuously pass
- **直接证据**: line 2260: `poll(0.25)` — wall-clock timing 用于证明 absence of blocking
- **影响**: R06 关键 claim "concurrent reader blocks at publication rename barrier" 可能未被真正验证
- **建议改法和验证点**: reader 进程在进入 read path 后通过 Event/Barrier 信号通知 parent，parent 验证 reader 尚未返回数据后才释放 rename。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F14-未修复-composed read deadlock 测试实际是顺序执行

- **入口/函数**: `test_concurrent_composed_source_read_and_delayed_open_do_not_self_deadlock`
- **文件(行号)**: `tests/fins/test_fins_storage_atomicity.py:2313-2388`
- **输入场景**: 测试名声称"do not self deadlock"但 `ThreadPoolExecutor(max_workers=1)` 序列化执行
- **实际分支**: inner read 在 executor 中完成 → outer delayed open 在 main thread 中完成 — 顺序而非并发
- **预期行为**: 两个操作应同时 in-flight 以证明无死锁
- **实际行为**: 顺序执行只证明操作完成，不证明并发安全
- **直接证据**: `ThreadPoolExecutor(max_workers=1)` — max_workers=1 强制序列化
- **影响**: 测试对 deadlock-free property 给出虚假信心
- **建议改法和验证点**: 使用 `Event`/`Barrier` 确保两个操作同时 in-flight，或使用 `max_workers=2` + 同步屏障。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### R06-CR-MIMO-F15-未修复-SEC adapter 访问 pipeline 私有属性

- **入口/函数**: SEC pipeline rebuild adapter
- **文件(行号)**: `dayu/fins/pipelines/sec_pipeline.py:1827-1840`
- **输入场景**: pipeline 内部属性名变更
- **实际分支**: `self._pipeline._batching_repository` 和 `self._pipeline._processed_repository` 访问私有属性
- **预期行为**: 应使用 public properties（CN adapter 在 `cn_pipeline.py:1384-1397` 正确使用 `self._pipeline.batching_repository`）
- **实际行为**: SEC adapter 直接访问 `_batching_repository` 和 `_processed_repository`
- **直接证据**: `sec_pipeline.py:1828`: `self._pipeline._batching_repository` vs `cn_pipeline.py:1385`: `self._pipeline.batching_repository`
- **影响**: 脆弱耦合，内部属性重命名时静默 break
- **建议改法和验证点**: 改为使用 public properties。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### R06-CR-MIMO-F16-未修复-SEC rebuild rollback 失败掩盖原始异常

- **入口/函数**: `_rebuild_single_document` (SEC rebuild)
- **文件(行号)**: `dayu/fins/pipelines/sec_rebuild_workflow.py:445-458`
- **输入场景**: batch mutation 失败 + rollback_batch 本身也失败
- **实际分支**: `except Exception` → `rollback_batch(batch)` → return "failed" result；rollback 异常被 swallowed
- **预期行为**: rollback 失败应被记录且不应掩盖原始异常
- **实际行为**: rollback 异常被 swallowed，返回 "failed" result 仅包含原始错误信息，rollback 失败不可见
- **直接证据**: line 445-458: `rollback_batch` 在 except 内，异常被 swallowed，return "failed" dict
- **对比**: CN rebuild (`cn_download_rebuild.py:247-249`) re-raise 异常让 caller 处理
- **影响**: rollback 失败（如 disk full）被静默掩盖，batch 可能处于不确定状态
- **建议改法和验证点**: rollback 失败时应保留原始异常并记录 rollback 错误，参考 CN rebuild 的 re-raise 模式。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Blocking Questions

无。所有 findings 都有直接 file:line 证据和具体修复方向。

## Observations / Residual Destinations

1. **R07 materialize() guard gap**: `LocalFileSource.materialize()` 返回裸 Path，绕过 publication guard。这是设计权衡（path-based API 无法持有 guard），R07 应明确文档化 guard gap 或提供 alternative guarded-path API。
2. **reprocess_required 不可清除**: `mark_processed_reprocess_required` 只能设 True 不能设 False。reprocessing 完成后标记永久为 True。R07 应补充 clear 机制。
3. **form_type merge `or` 语义**: `_upsert_source_document` 的 `req.form_type or merged_meta.get("form_type")` 对 `None` 传入保留旧值。当前无调用方传 `None`，但 API 语义含糊。
4. **pre-existing `Any` 使用**: `document_models.py` 使用 `dict[str, Any]`，违反编码硬约束。pre-existing technical debt，非 R06 引入。
5. **Docling convert timeout 无测试**: CN/SEC workflow 无第三方 converter hang timeout 测试。已知限制，README 已记录。

## Review Verdict

**PASS-WITH-FINDINGS**

- **Material findings**: 16
- **Blockers**: 3 (F01 CRITICAL, F02 HIGH, F03 HIGH)
- **S1/S2 prior findings re-verification**: All previously closed findings (R06-S1-CR-F01..03, R06-S2-CR-F01) remain CLOSED in the cumulative tree.

### Severity Breakdown

| Severity | Count | IDs |
|---|---|---|
| 严重 | 1 | F01 |
| 高 | 2 | F02, F03 |
| 中 | 13 | F04-F14, F16 |
| 低 | 1 | F15 |

### Ready For

`READY_FOR_CONTROLLER_ADJUDICATION`

Controller 需裁决：
1. F01 (CRITICAL): journal phase ordering data loss — 是否 block R06 accepted commit
2. F02 (HIGH): SEC rebuild BaseException — 是否 block
3. F03 (HIGH): publication guard deadlock — 是否 block
4. F04-F16 (MEDIUM/LOW): 是否 accepted/rejected/deferred
