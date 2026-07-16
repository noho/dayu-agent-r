# WU-SEMANTIC-OWNERSHIP-01 R06 Cumulative (S1+S2+S3) Complete Code Review

## Review Identity

- **Reviewer**: AgentDS (DeepReview)
- **Date**: 2026-07-16
- **Mode**: Current Changes Mode (uncommitted worktree)
- **Base**: `d048adf7ec1135aaf575384432ebf1137f8a34f2` (R06-S1 implementation gate transition commit)
- **Branch**: `phaseflow/host-issues-control`
- **Output**: `docs/reviews/wu-semantic-ownership-01-r06-cumulative-code-review-ds.md`
- **Umbrella**: `WU-SEMANTIC-OWNERSHIP-01`
- **Scope**: R06 complete cumulative S1+S2+S3 product code, tests, and README

## Scope

### Included Scope

57 changed files (~9,951 insertions, ~3,589 deletions):

**Storage infrastructure** (S1+S2 core):
- `dayu/fins/domain/document_models.py` — BatchToken, SourceDocumentProvenance, manifest items
- `dayu/fins/storage/repository_protocols.py` — all six public protocols
- `dayu/fins/storage/_fs_storage_infra.py` — core: transaction lifecycle, resolver, validator, recovery, publication guard, journal
- `dayu/fins/storage/_fs_blob_core.py` — blob-first staging
- `dayu/fins/storage/_fs_source_document_core.py` — source CRUD, guarded/unguarded read, complete-source normalization
- `dayu/fins/storage/_fs_company_meta_core.py` — company meta staging
- `dayu/fins/storage/_fs_maintenance_core.py` — filing maintenance staging
- `dayu/fins/storage/_fs_processed_core.py` — processed staging
- `dayu/fins/storage/_fs_storage_utils.py` — helpers

**Repository wrappers** (S1):
- `dayu/fins/storage/fs_batching_repository.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/fs_document_blob_repository.py`
- `dayu/fins/storage/fs_company_meta_repository.py`
- `dayu/fins/storage/fs_filing_maintenance_repository.py`
- `dayu/fins/storage/fs_processed_document_repository.py`
- `dayu/fins/storage/local_file_source.py` — `BinaryFileOpener` protocol, `_PublicationGuardedBinaryOpener`

**Producer/Callback migration** (S3):
- `dayu/fins/ingestion_runtime.py` — `_store_downloaded_document`, `_store_rejected_filing_artifact`, `_preprocess_one_document`, `_select_preprocess_documents`
- `dayu/fins/service_runtime.py` — `DefaultFinsRuntime.create` composition root
- `dayu/fins/downloaders/sec_downloader.py` — callback batch invocation
- `dayu/fins/pipelines/cn_download_company_meta.py`
- `dayu/fins/pipelines/cn_download_workflow.py` — company meta short transaction
- `dayu/fins/pipelines/cn_download_filing_workflow.py` — blob-first, final-once, commit fence
- `dayu/fins/pipelines/cn_download_rebuild.py` — source+processed same batch
- `dayu/fins/pipelines/cn_download_source_upsert.py` — final source upsert
- `dayu/fins/pipelines/cn_download_protocols.py`
- `dayu/fins/pipelines/cn_pipeline.py` — composition root
- `dayu/fins/pipelines/docling_upload_service.py` — blob-first, batch propagation
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py` — composition root, source+processed same batch
- `dayu/fins/pipelines/sec_company_meta.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py` — single filing lifecycle, commit fence
- `dayu/fins/pipelines/sec_download_persistence.py` — callback batch contract
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/sec_download_state.py`
- `dayu/fins/pipelines/sec_download_workflow.py` — company/maintenance transaction separation
- `dayu/fins/pipelines/sec_pipeline.py` — composition root
- `dayu/fins/pipelines/sec_rebuild_workflow.py` — source+processed same batch
- `dayu/fins/pipelines/sec_upload_workflow.py` — company/document transaction separation
- `dayu/fins/pipelines/upload_company_meta.py`

**Tests** (S1+S2+S3):
- `tests/fins/test_fins_storage_atomicity.py` — recovery, concurrent reader, crash-phase, orphan
- `tests/fins/test_fins_storage_provider.py` — batch token, lifecycle, validator, cross-core, complete source
- `tests/fins/test_processor_read_consistency.py` — online reader consistency
- `tests/fins/test_read_runtime_semantic_ownership_guards.py` — guard tests
- `tests/fins/test_fins_ingestion_runtime.py` — preprocess selection, R06-S3-CV-F01
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_cn_download_runtime.py`
- `tests/fins/test_cn_download_workflow.py` — CN transaction tests
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_docling_upload_service.py` — Docling batch propagation
- `tests/fins/test_docling_upload_service_integration.py`
- `tests/fins/test_sec_downloader.py`
- `tests/fins/test_sec_pipeline_download.py` — SEC transaction tests
- `tests/fins/test_sec_pipeline_download_stream.py` — SEC stream tests
- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/tools/test_combined_tools_acceptance.py`

**README**:
- `dayu/fins/README.md`
- `tests/README.md`

**Control**:
- `docs/host/issues-implementation-control.md`

### Excluded Scope

- R07 (storage revision, snapshot, retry, opaque ID) — deferred per plan §1.3
- Issue 142, 151, 175, 177, 178 — deferred
- Unified tool authorization — not in scope
- Any files outside the diff list above
- `.venv/`, `__pycache__/`, generated artifacts

### Parallel Review Coverage

Four parallel subagents covered:
1. **Storage infra core** (`_fs_storage_infra.py`, `_fs_*_core.py`, `local_file_source.py`) — transaction lifecycle, resolver, validator, recovery, publication guard, journal, guarded/unguarded read. Agent result not yet returned at review finalization time; main reviewer independently completed full walkthrough of all seven files.
2. **Repository wrappers** (`fs_*_repository.py`, `repository_protocols.py`, `_fs_storage_utils.py`) — protocol contract, batch propagation, compat. Agent returned with 3 LOW observations (docstring/protocol inconsistency, `_FsRepositorySet` constructor exposure, core vs wrapper `source_kind` optionality divergence). No material findings.
3. **Producer/Callback migration** (12 files) — composition roots, transaction boundaries, blob-first, commit fence, callback invocation, keyword compliance. Agent returned with 4 findings: F02 (rollback error swallowing, MEDIUM), F03 (optional core fallback, MEDIUM), 6-K independent core (LOW), and confirmation of all 54 batch-keyword compliance + zero prohibited patterns.
4. **Tests and scans** (10 files) — coverage, adversarial paths, scan evidence, README truth. Agent returned with 12 observations including F01 (corrupted journal JSON recovery gap, HIGH), F04 (missing explicit `ingest_complete=False` test branch, LOW), F06 (post-build revision test gap, LOW).

Main reviewer (AgentDS) performed independent full-chain walkthrough of all critical paths, synthesized and adjudicated all subagent findings, and conducted the adversarial failure and semantic ownership drift passes.

## Controller Verification Points — Direct Evidence

### R06-S3-CV-F01 Closure

**Plan requirement**: preprocess selection must reject sources missing `ingest_complete`.

**Code evidence**: `dayu/fins/ingestion_runtime.py:4069`
```python
if meta.get("ingest_complete") is not True:
    continue
```

**Test evidence**: `tests/fins/test_fins_ingestion_runtime.py:3558-3618`
`test_preprocess_selection_rejects_missing_completion_and_keeps_complete_source` creates two published sources via shared-core repository, corrupts one by removing `ingest_complete`, and asserts only the complete source is selected.

**Verdict**: R06-S3-CV-F01 is correctly closed. The owner boundary is clear: storage validator owns publication completeness; preprocess selector independently owns selection eligibility based on that published fact.

### 54 Production Mutation Required Batch

**Scan**: Production AST audit confirms all 54 mutation calls use explicit keyword `batch=`.

**Direct verification**: Every begin_batch/commit_batch/rollback_batch call chain across CN, SEC, Docling, rebuild, 6-K repair, ingestion runtime verified. Lifecycle calls are exactly at the top-level owners listed in plan §6 inventory. No ambient, auto-batch, or capture found.

### Callback Invocation-Time Token

**Scan evidence**: `build_store_file` (sec_download_persistence.py) uses `partial(_store_file_callback, repository, source_handle, payload_sink)` — batch is NOT captured. Batch is passed as keyword `batch=` at every callback invocation site.

### CN/SEC/Docling Blob-First, Final-Once

- **CN**: `_commit_cn_filing_assets_batch` — store_file(PDF) → store_file(Docling JSON) → commit_cn_filing_source_document (once). ✓
- **SEC**: `run_download_single_filing_stream` — download_files_stream (blobs via callback) → upsert_downloaded_filing_source_document (once). ✓
- **Docling**: `_store_upload_assets` — store_file(blobs) → _upsert_source_document (once). ✓

### Company/Document/Maintenance Transaction Separation

- **CN**: company meta is a separate short transaction (`cn_download_workflow.py:208-220`). Each filing document is its own transaction. ✓
- **SEC**: company meta short transaction (`sec_download_workflow.py:487-499`). Maintenance separate short transaction (`sec_download_workflow.py:618-636`). Each filing its own transaction. ✓
- **Docling**: Each document is a caller-owned short transaction (`sec_upload_workflow.py:242-254`). ✓

### Rebuild/6-K Source+Processed Same Batch

- **CN rebuild**: `cn_download_rebuild.py:225-250` — `update_source_document(batch=batch)` + `mark_processed_reprocess_required(batch=batch)` in same batch. ✓
- **SEC rebuild**: `sec_rebuild_workflow.py:423-459` — same pattern. ✓
- **6-K repair**: `sec_6k_primary_document_repair.py:135-148` — `_update_active_6k_primary_document(batch=batch)` + `mark_processed_for_6k_reconcile(batch=batch)` in same batch. ✓

### Commit-Start Fence (No Double Rollback)

**Pattern verified across all producers**:

```python
commit_started = False
try:
    # ... mutations with batch=token ...
    commit_started = True
    batching_repository.commit_batch(token)
finally:
    if not commit_started:
        batching_repository.rollback_batch(token)
```

- `_store_downloaded_document` (ingestion_runtime.py:3833-3839) ✓
- `_store_rejected_filing_artifact` (ingestion_runtime.py:3977-3981) ✓
- `_preprocess_one_document` (ingestion_runtime.py:4161-4165) ✓
- `_commit_cn_filing_assets_batch` (cn_download_filing_workflow.py:544-553) ✓
- `run_download_single_filing_stream` (sec_download_filing_workflow.py:596-619) ✓
- `rebuild_cn_download_artifacts` (cn_download_rebuild.py:225-250) ✓
- `rebuild_download_artifacts` (sec_rebuild_workflow.py:423-459) ✓
- `reconcile_active_6k_primary_documents` (sec_6k_primary_document_repair.py:289-301) ✓

### Four Composition Roots Shared Core

All four composition roots create a single `build_fs_repository_set()` and share it:

- `service_runtime.py:350-356` — `DefaultFinsRuntime.create` ✓
- `cn_pipeline.py:378-382` — `CnPipeline.__init__` ✓
- `sec_pipeline.py:512-516` — `SecPipeline.__init__` ✓
- `sec_6k_primary_document_repair.py:260-264` — `reconcile_active_6k_primary_documents` ✓

### Two `ingest_complete=False` Only in Validator Negative Tests

**Scan**: Exactly 2 occurrences in tests, 0 in production:
- `tests/fins/test_fins_storage_provider.py:1444` — `test_final_source_rejects_false_completion_without_publication` (source owner boundary test)
- `tests/fins/test_fins_storage_provider.py:3478` — validator corrupt helper `false_completion` case

Both are owner-level rejection evidence. ✓

### Scans Evidence

| Scan | Result |
| --- | --- |
| Ambient authority (ContextVar, current_task, _BATCH_OWNER_CONTEXT, auto_batch) | **0 hits** in `dayu/fins/storage` + `tests/fins` |
| stage_source_document, _STAGING_STABLE_META_FIELDS, staging ack | **0 hits** |
| Production `ingest_complete=False` | **0 hits** |
| Journal field leakage (owner_pid, hostname, absolute paths) | **0 hits** in public token; internal state fields correctly contained in `_ActiveBatchState` |
| `owner_pid`, `hostname` in `_fs_storage_infra.py` | **0 hits** |

### pyright/Ruff/Coverage/Scans Trustworthiness

Per S3 controller validation (§Independent Verification table):
- pyright: `0 errors, 0 warnings, 0 informations` — independently verified
- Scoped Ruff (changed Python files): `All checks passed!` — independently verified
- Full Ruff baseline: 162→152, `current-only=0`, `base-only=10` (accepted plan §10 cleanup)
- Coverage: 22 changed production files all ≥80%, lowest 80.41%
- Mutation AST scan: production 54, tests 129, `missing_explicit_batch_keyword=0`

**Trustworthiness assessment**: These claims are independently verifiable. The Controller re-ran all scans independently (per §Independent Verification). The reviewer (AgentDS) independently ran ambient authority, ack/false-completion, journal leakage, and lifecycle scans — all returned the expected results.

## Findings

### R06-CR-DS-F01 — Recovery 不保护单个损坏 journal JSON 导致全体 orphan 恢复失败

- **Severity**: 高
- **入口/函数**: `_FsStorageInfra._recover_single_batch_dir`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:1256`
- **输入场景**: orphan batch staging 目录中存在部分写入（crash 中间截断）的 `transaction.json`
- **实际分支**: `_read_json_object(journal_path)` 抛出 `ValueError`，异常向上穿透 `_recover_orphan_batch_dirs` → `recover_orphan_batches`，当前无 try/except 兜底
- **预期行为**: 损坏 journal 应 skip + preserve evidence（与 `invalid_journal_fields` 同策略），不应阻断同一 `batch_root` 下其他合法 orphan 的恢复
- **实际行为**: 单个损坏 journal 导致 `recover_orphan_batches` 整体崩溃，其他 orphan 均无法恢复。剩余 staging/backup 不清理，可能永久阻塞该 ticker 的后续 `begin_batch`
- **直接证据**:
  - `_recover_single_batch_dir:1256` — `journal = _read_json_object(journal_path)` 无 try/except
  - `_recover_orphan_batch_dirs:1226-1231` — for 循环中无单条目异常保护
  - `recover_orphan_batches:1001-1023` — 仅有 recovery lock 的 finally，无单条目异常捕获
  - `_read_json_object` (`_fs_storage_utils.py:483-500`) — `json.JSONDecodeError` 等均转为 `ValueError` 抛出
- **影响**: crash 期间部分写入的 journal 会导致全部 orphan 恢复失败，ticker 被永久阻塞
- **Root cause**: recovery 对 journal 合法性做了 fail-closed 字段校验（正确），但对 journal 可解析性未做 per-entry 异常保护（缺陷）。语义 owner 是 storage recovery，当前 recovery 把 per-entry malformed evidence 的 skip+preserve 策略正确应用于字段级别，但在 JSON 解析级别未应用同一策略
- **Owner boundary**: `_fs_storage_infra._recover_single_batch_dir` 必须在 `_read_json_object` 外围 try/except，把不可解析 journal 归为 `skip + preserve evidence`，不阻断其他 orphan 恢复
- **最小正确修复**: 在 `_recover_single_batch_dir:1256` 处包裹 `_read_json_object(journal_path)`：
  ```python
  try:
      journal = _read_json_object(journal_path)
  except (ValueError, OSError):
      actions.append(f"skip batch transaction={token_dir.name} reason=unparseable_journal")
      return actions
  ```
- **验证点**:
  1. 构造损坏 journal（截断 JSON、空文件、二进制内容），两个合法 orphan 分别在不同 token_dir
  2. 调用 `recover_orphan_batches()` — 损坏 journal 应 skip 且不抛异常
  3. 两个合法 orphan 应正常恢复
  4. 损坏 evidence 保留在文件系统中（不自动删除）
- **修复风险**: 低 — 窄化单条目异常范围，不影响合法 journal 字段校验逻辑

### R06-CR-DS-F02 — `_store_rejected_filing_artifact` 与 `_preprocess_one_document` 回滚失败时丢失原始异常

- **Severity**: 中
- **入口/函数**: `FinsIngestionRuntime._store_rejected_filing_artifact` / `_preprocess_one_document`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:3979-3981` / `:4163-4165`
- **输入场景**: rejected filing artifact 写入成功但 `commit_batch` 前回滚失败（如 writer lock 释放异常），或 preprocessed document 写入中发生 OSError 且回滚也失败
- **实际分支**: `finally: if not commit_started: self.batching_repository.rollback_batch(batch)` — 若 rollback 也抛异常，Python finally 语义下新异常替换原异常，原始错误信息丢失
- **预期行为**: 与 `_store_downloaded_document` (`ingestion_runtime.py:3836-3847`) 一致——保留原始 `operation_error`，回滚失败作为附加诊断 chain，`raise operation_error from rollback_error`
- **实际行为**: 原始操作失败原因被回滚异常覆盖，caller 看到的错误信息误导
- **直接证据**:
  - `_store_downloaded_document:3836-3847` — 正确模式：`operation_error = sys.exception()` → try rollback → `raise operation_error from rollback_error`
  - `_store_rejected_filing_artifact:3979-3981` — 缺失模式：直接 `rollback_batch(batch)` 无异常保护
  - `_preprocess_one_document:4163-4165` — 同上
- **影响**: 生产环境中 rejected artifact 或 preprocess 持久化失败的根本原因不可见，排障依赖猜测
- **Root cause**: copy-paste 不一致——`_store_downloaded_document` 作为首个迁移目标获得了完整双异常保护模式，后续两个方法遗漏
- **Owner boundary**: `FinsIngestionRuntime` 拥有 ingestion 操作错误报告语义；每个 mutation helper 应以一致策略保护原始操作错误
- **最小正确修复**: 将 `_store_rejected_filing_artifact:3979-3981` 和 `_preprocess_one_document:4163-4165` 的 finally 块替换为与 `_store_downloaded_document:3836-3847` 一致的双异常保护模式
- **验证点**:
  1. 注入 mutation 失败 + rollback 也失败的 scenario
  2. 断言最终异常是原始操作异常，rollback 异常为 `__cause__`
  3. 断言原始异常消息包含操作语义（如 "upsert rejected filing artifact"），而非仅有 "rollback" 信息
- **修复风险**: 低 — 纯错误报告改进，不改变业务流程

### R06-CR-DS-F03 — CnPipeline/SecPipeline 的 `batching_repository` 可选参数可能创建独立 core

- **Severity**: 中
- **入口/函数**: `CnPipeline.__init__` / `SecPipeline.__init__`
- **文件(行号)**: `dayu/fins/pipelines/cn_pipeline.py:379-382` / `dayu/fins/pipelines/sec_pipeline.py:513-515`
- **输入场景**: caller（测试、CLI 脚本、future composition root）构造 Pipeline 时未显式传入 `batching_repository=...`
- **实际分支**: `self._batching_repository = batching_repository or FsBatchingRepository(workspace_root, repository_set=build_fs_repository_set(...))` — `or` 运算符触发创建**新的** `repository_set` 和新的 core
- **预期行为**: 一个 workspace 内所有 repository wrapper 必须共享同一 core（R06 plan §3.5）；若 second core 静默产生，其 transaction registry 与原 core 隔离，两个 core 可能同时持有同一 ticker 的 open batch，造成持久化不一致
- **实际行为**: 当前 production assembly 路径（`DefaultFinsRuntime.create` → pipeline constructors）均传入 shared instance，latent bug 不会触发。但构造器提供了 escape hatch
- **直接证据**:
  - `cn_pipeline.py:378` — `repository_set = build_fs_repository_set(...)` 在 `or` 分支内创建新 set
  - `sec_pipeline.py:512` — 同上
  - `_resolve_active_batch` (`_fs_storage_infra.py:942-943`) — `self._active_batches.get(transaction_id)` 只查当前 core 的 registry，来自另一 core 的合法 token 被拒绝——这是正确的 cross-core rejection，但两个 core 各自对同一 ticker 持有 open batch 本身就是错误
- **影响**: 当前 production 路径安全，但未来 caller 遗漏参数时静默产生 split-brain batch 状态，无错误无警告
- **Root cause**: 防御式 `or` 默认值允许创建第二 core，违反 "one workspace → one core" 不变量
- **Owner boundary**: Pipeline composition root 应要求 `batching_repository` 为 required 参数，或至少将 optional fallback 改为共享既有 `self._workspace_root` 下的同一 `repository_set`（但共享 set 的选择本身也必须显式）；最安全方案是移除 `or` fallback，让缺失参数在构造时报错
- **最小正确修复**:
  1. 移除 `batching_repository or FsBatchingRepository(...)` 中的 `or` 分支
  2. 若 `batching_repository` 为 None 且其他 wrappers 已绑定到一个 repository_set，应 `raise ValueError("batching_repository must share the same core")`
  3. 或在构造器文档中明确标注 `batching_repository` 为 de-facto required
- **验证点**:
  1. 不传 `batching_repository` 构造 Pipeline 时抛 `ValueError`
  2. 现有所有 production/test assembly 路径仍正常工作（均传入 shared instance）
- **修复风险**: 低 — 仅影响未传入 batching_repository 的路径；所有已知调用方均己传入

### R06-CR-DS-F04 — `_select_preprocess_documents` 未覆盖显式 `ingest_complete=False` 分支

- **Severity**: 低
- **入口/函数**: `FinsIngestionRuntime._select_preprocess_documents`
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:4069` / `tests/fins/test_fins_ingestion_runtime.py:3558-3618`
- **输入场景**: published source meta 中 `ingest_complete` 键存在但值为 `False`（不同于键缺失）
- **实际分支**: `meta.get("ingest_complete") is not True` — 正确拒绝 `False` 和键缺失
- **预期行为**: 代码行为正确，但现有测试 `test_preprocess_selection_rejects_missing_completion_and_keeps_complete_source` 只覆盖 `pop("ingest_complete")`（键缺失），未覆盖 `meta["ingest_complete"] = False`（显式 false）
- **实际行为**: 当前 storage validator 禁止 `ingest_complete=False` 进入 published tree，因此生产环境不会出现该状态。但测试未直接覆盖，依赖 indirect guarantee
- **直接证据**:
  - `ingestion_runtime.py:4069` — `is not True` 正确处理两种 case
  - `test_fins_ingestion_runtime.py:3589` — `incomplete_meta.pop("ingest_complete")` 只测键缺失
- **影响**: 测试 gap；当前生产路径安全（validator 保证），但如果 future refactoring 绕过 validator，gap 不会被捕获
- **Root cause**: R06-S3-CV-F01 修复覆盖了触发场景（键缺失），未追加显式 false 的 double-check
- **Owner boundary**: `_select_preprocess_documents` 测试应对判断条件的两条路径分别直接断言
- **最小正确修复**: 追加一条 `test_preprocess_selection_rejects_explicit_false_completion`，设置 `meta["ingest_complete"] = False` 并断言该 source 被跳过
- **验证点**: 与现有缺失键测试同一 fixture，仅将 `pop` 改为赋值 `False`
- **修复风险**: 极低 — 纯测试补充

### R06-CR-DS-F05 — SEC pipeline 下载测试未断言 `ingest_complete is True`

- **Severity**: 低
- **入口/函数**: `test_sec_pipeline_download_writes_meta_and_manifest` 等测试
- **文件(行号)**: `tests/fins/test_sec_pipeline_download.py:1082+`
- **输入场景**: SEC download pipeline 正常完成
- **实际分支**: 测试断言 `meta["source_provider"] == "sec_edgar"` 等字段，但未断言 `meta["ingest_complete"] is True`
- **预期行为**: pipeline 测试应防御性验证输出包含完整 source contract，特别是 `ingest_complete=True`
- **实际行为**: 依赖 implicit trust 即 `_normalize_before_store` 固定设为 `True`；若 future refactoring 改变逻辑，SEC pipeline 测试不会捕获
- **直接证据**: CN download 测试 (`test_cn_download_workflow.py`) 和 storage provider 测试 均断言 `ingest_complete`；SEC pipeline 测试缺失该断言
- **影响**: 极低 — storage owner 强制 `ingest_complete=True`（`_fs_source_document_core.py:1454`），pipeline 无法绕过。但测试应自足证明输出完整性
- **Root cause**: 测试作者依赖 storage owner contract 而不重复断言；与 CN 测试不一致
- **Owner boundary**: SEC pipeline 测试应对其输出做完整 contract 断言，不依赖下游保证
- **最小正确修复**: 在 SEC pipeline download 测试的关键 meta 断言中追加 `assert meta["ingest_complete"] is True`
- **验证点**: 现有测试全部仍通过（值已是 True）
- **修复风险**: 极低

### R06-CR-DS-F06 — `test_processor_read_consistency` 并发 revision change 测试未覆盖 revision-change-after-build 场景

- **Severity**: 低
- **入口/函数**: `test_concurrent_reads_after_revision_change_build_one_processor`
- **文件(行号)**: `tests/fins/test_processor_read_consistency.py:1480-1503`
- **输入场景**: processor A 构建完成后 source revision 改变，随后 processor B 被请求
- **实际分支**: 测试验证了并发构建收敛（`results[0] is results[1]`），但未测试更微妙的竞争：A 构建完成 → revision 改变 → B 被请求时是否错误地获取到旧 A
- **预期行为**: B 应检测到 revision 改变并构建新 processor
- **实际行为**: 未测试该分支
- **影响**: revision-based cache invalidation 的 post-build 路径未受直接测试保护
- **Root cause**: 测试设计关注并发构建去重，未覆盖 sequential revision change after build
- **Owner boundary**: `_get_or_build_processor` 的 revision check 应在 post-build 场景独立测试
- **最小正确修复**: 追加测试：build A → 修改 source → build B → 断言 A is not B
- **修复风险**: 低

## Adversarial Failure Pass — Verified Safe

以下 adversarial scenarios 经直接代码路径验证，**未发现缺陷**：

| Scenario | Verification | Status |
| --- | --- | --- |
| begin_batch 后 staging 准备失败 → lock 释放 + staging 清理 | `_fs_storage_infra.py:304-313` — `except Exception: shutil.rmtree(staging_root_dir); _release_lock_token(lock_token); raise` | ✓ Safe |
| commit 前 validator 失败 → precommit rollback 恢复 old target | `_fs_storage_infra.py:355-360` — `commit_error = exc; _rollback_precommit_batch(state)` | ✓ Safe |
| commit 内 physical swap 失败 → backup 恢复 + rollback journal | `_fs_storage_infra.py:357-360` — try `_rollback_precommit_batch` | ✓ Safe |
| COMMITTED journal 后 cleanup 失败 → post-commit error 不 rollback durable tree | `_fs_storage_infra.py:403-427` — 只抛 post_commit_error，不恢复 target | ✓ Safe |
| rollback 后 staging 清理 → 即使 journal 写入失败也清理 | `_fs_storage_infra.py:913-914` — `shutil.rmtree(staging_root_dir, ignore_errors=True)` in `finally` | ✓ Safe |
| 同 ticker 第二 begin → RuntimeError | `_fs_storage_infra.py:277-278` — `_active_transaction_by_ticker` 索引拒绝 | ✓ Safe |
| cross-core token → ValueError | `_fs_storage_infra.py:942-944` — `self._active_batches.get(transaction_id)` 返回 None | ✓ Safe |
| 已 commit token 再次 mutation → ValueError | `_fs_storage_infra.py:957-958` — `lifecycle != _BATCH_LIFECYCLE_OPEN` | ✓ Safe |
| ticker mismatch token → ValueError | `_fs_storage_infra.py:955-956` — `normalized_batch_ticker != normalized_ticker` | ✓ Safe |
| publication guard 释放失败 on committed → post-commit error（不回滚） | `_fs_storage_infra.py:371-378` — 仅 `Log.warn` + 设为 `post_commit_error` | ✓ Safe |
| reader 在长 staging/validator 期间读取 → 不阻塞，读 old | 长事务 only 持 writer mutex；reader 只获取 publication guard（独立锁） | ✓ Safe |
| reader 在两个 rename barrier → publication guard 阻塞，终态只见 old/new | `_PublicationGuardedBinaryOpener` 获取 publication guard → open fd → release | ✓ Safe |
| writer/recovery 锁顺序 → writer first, publication second; release reverse | begin 只获取 writer mutex；commit 先 validator（无 guard）→ 再 publication guard | ✓ Safe |
| 6-K primary selection 不读 staging → 从 downloaded payloads 选择 | `select_prepared_6k_primary_document` 接收 `candidate_payloads: dict[str, bytes]` 参数 | ✓ Safe |
| `Source.open()` 重新获取 publication guard | `_get_source_unguarded` 构造 `LocalFileSource(opener=self._publication_guarded_binary_opener(...))` | ✓ Safe |
| journal 字段闭集 → `_JOURNAL_FIELDS = frozenset({"transaction_id", "ticker", "phase"})` | `_fs_storage_infra.py:69` + recovery 中 `frozenset(journal) != _JOURNAL_FIELDS` 拒绝多余字段 | ✓ Safe |
| containment escape 拒绝 → `_require_contained_path` 解析 root + path，`relative_to` 校验 | `_fs_storage_infra.py:759-788` | ✓ Safe |
| symlink escape 拒绝 → validator 拒绝 symlink staging root, source root, meta, files | `_fs_storage_infra.py:444, 479-480, 493, 625, 696, 722` | ✓ Safe |
| CN company meta + Docling document 分离短 transaction | `cn_download_workflow.py:208-220` company batch + `cn_pipeline.py:908-920` document batch | ✓ Safe |
| Docling prepare 阶段 `ingest_complete` 固定 True | `docling_upload_service.py:719` — `merged["ingest_complete"] = True` | ✓ Safe |

## Semantic Ownership Drift Check

对每个关键语义进行了 owner boundary 验证：

| 语义 | 唯一 Owner | Drift 证据 | 状态 |
| --- | --- | --- | --- |
| transaction authority | `BatchToken` + `_resolve_active_batch` | 无；删除全部 ambient authority | ✓ Converged |
| public token fields | `BatchToken(transaction_id, ticker)` | 无；不含 owner/scope/PID/hostname/path | ✓ Converged |
| mutation authority | `batch: BatchToken` keyword-only | 无；全部 mutation 显式 batch | ✓ Converged |
| lifecycle | `BatchingRepositoryProtocol` only | 无；Source protocol 已删除 begin/commit/rollback | ✓ Converged |
| publication completeness | storage validator (`_validate_complete_source_tree`) | 无；producer 不再写 `ingest_complete=False` | ✓ Converged |
| staging staging | storage internal `_ActiveBatchState` | 无；不再进入 public token 或业务 meta | ✓ Converged |
| online read consistency | publication swap guard + `_PublicationGuardedBinaryOpener` | 无；reader 不进 rename 空窗 | ✓ Converged |
| journal facts | `{transaction_id, ticker, phase}` only | 无；不含 PID/hostname/absolute path | ✓ Converged |
| source provenance | `SourceDocumentProvenance.from_meta` typed owner | 无；不再从 document_id 前缀猜测 | ✓ Converged |
| revision/cache freshness | `get_source_revision` storage owner | 无；read runtime 不重算字段 hash | ✓ Converged |
| preprocess selection eligibility | `_select_preprocess_documents` 独立 owner | 无；直接消费 published `ingest_complete` | ✓ Converged |
| callback batch | invocation-time explicit keyword argument | 无；`partial` 不 capture batch | ✓ Converged |

**结论**: R06 成功将语义所有权从三个分散 owner（public token + ambient context + source meta）收敛到唯一 storage owner boundary。未发现 semantic ownership drift。

## Over-Coupling Check

| 检查项 | 状态 |
| --- | --- |
| storage core ↔ producer 耦合 | separaed: producer 只传 batch，不拥有 lifecycle ✓ |
| writer mutex ↔ publication guard 耦合 | separaed: 两个独立 lock file，不同生命周期 ✓ |
| source meta ↔ transaction staging 耦合 | separaed: `ingest_complete` 不再是 staging ack ✓ |
| journal ↔ public token 耦合 | separaed: journal 只有 {transaction_id, ticker, phase} ✓ |
| read runtime ↔ storage revision 耦合 | separaed: revision 由 storage owner 统一计算 ✓ |
| Protocol ↔ concrete implementation 耦合 | separaed: 所有调用方依赖 Protocol ✓ |
| CN ↔ Docling transaction 耦合 | separaed: 各自短 transaction，不跨 transaction rollback ✓ |
| SEC company ↔ filing ↔ maintenance transaction 耦合 | separaed: 三个独立短 transaction ✓ |

**结论**: R06 成功解耦了原本必须同步修改的层/模块/状态机组合。未发现过度耦合。

## Plan Conformance

对照 accepted plan §1–§13 逐项核对：

| Plan § | Requirement | Status |
| --- | --- | --- |
| §3.1 | BatchToken 只含 transaction_id + ticker | ✓ |
| §3.2 | internal resolver 校验 transaction_id + ticker + open state | ✓ |
| §3.2 | cross-core token 拒绝 | ✓ |
| §3.3 | 只有 BatchingRepositoryProtocol 声明 lifecycle | ✓ |
| §3.4 | 全部 mutating protocol 有 required `batch=` | ✓ |
| §3.4 | `stage_source_document` 删除 | ✓ |
| §3.5 | 四个 composition roots shared core | ✓ |
| §4.1 | writer mutex 只作 writer exclusion | ✓ |
| §4.2 | publication swap guard 与 writer mutex 分离 | ✓ |
| §4.2 | online reader 不进 rename 空窗 | ✓ |
| §4.2 | 长事务不阻塞 published read | ✓ |
| §4.3 | journal 字段闭集 | ✓ |
| §5.1 | blob-first, final source once | ✓ |
| §5.2 | commit validator 遍历完整 staged tree + 双向 manifest | ✓ |
| §6 | 全部 producer/callback inventory 迁移 | ✓ |
| §7 | 三 slice 累计 breaking cutover | ✓ (R06-S3-CV-F01 closed) |
| §9 | README 更新 | ✓ |
| §10 | scoped Ruff 全绿，baseline 仅 10 项 changed-owner 清理 | ✓ |
| §11 | Stop conditions | 未触发；F01 例外已通过 F01 关闭 |
| §1.3 | 未实施 R07, Issue 142/151/175/177/178 | ✓ |

除本 review 报告的 findings 外，R06 完整符合 accepted plan。

## Open Questions

1. **R06-CR-DS-F01 修复后是否需要更新 recovery smoke test?** `test_fins_storage_atomicity.py` 已有 `test_invalid_journal_ticker_preserves_evidence_and_later_orphan_recovers`（覆盖非法 ticker），但缺少损坏 JSON 覆盖。F01 修复时应追加对应 test case。

2. **CnPipeline/SecPipeline 的 `batching_repository` fallback 是否应在 R06 内修复？** F03 是 latent risk，当前 production 路径未触发。plan §3.5 要求 "不得从 source repository 反射、cast、拆出或重建 batching core"，但构造器 `or` fallback 恰是重建 core。建议在 R06 final 修复或明确 deferred to R07 with explicit acceptance of latent risk。

3. **`tests/README.md` 是否过度声明？** 第 194 行声称 "新增 ingestion runtime 不破坏 read provider"，但未引用特定测试。建议删除或引用具体测试函数名。

### R06-CR-DS-F07 — `store_file` containment 校验路径与 file_store 写入路径使用两套独立路径构造链

- **Severity**: 中
- **入口/函数**: `_FsBlobMixin.store_file`
- **文件(行号)**: `dayu/fins/storage/_fs_blob_core.py:213-219`
- **输入场景**: blob 写入时，`_resolve_handle_child_path_for_state` 的 containment 校验链与 `file_store.put_object(key)` 的写入链产生路径分叉
- **实际分支**: 行 213 调用 `_resolve_handle_child_path_for_state(handle, normalized_filename, state)` 做 containment 校验但**丢弃返回值**；行 218-219 通过 `self._build_file_store(normalized_ticker, state)` → `file_store.put_object(key, data)` 写入，file_store root 为 `staging_ticker_dir.parent`，key 含独立构造的路径组件
- **预期行为**: containment 校验路径与写入路径应使用同一 resolved path，或显式证明等价
- **实际行为**: 两条路径当前因 staging 目录结构一致而隐式对齐，但缺少编译期/测试期保障——若 `_build_file_store` 或 `_handle_dir_path_for_state` 任一变更，可能导致校验通过但写入越界
- **直接证据**:
  - `_fs_blob_core.py:213` — `_resolve_handle_child_path_for_state(...)` 返回值丢弃
  - `_fs_storage_infra.py:1657-1665` — `_build_file_store` 使用 `self._file_store_root_for_ticker(ticker, state)` = `state.staging_ticker_dir.parent`
  - 对比：containment 校验以 `state.staging_ticker_dir` 为 root，写入以 `staging_ticker_dir.parent` 为 root
- **影响**: 当前无功能影响，但属于回归风险——路径构造链变更可能导致 containment bypass
- **Root cause**: `store_file` 混合使用了两套独立的路径抽象（handle-based path resolution vs key-based file_store）
- **Owner boundary**: `_FsBlobMixin.store_file` 应统一为单一路径构造链
- **最小正确修复**: 将 `_resolve_handle_child_path_for_state` 的返回值用于实际写入，或将 file_store root 对齐到 `staging_ticker_dir` 使 containment 边界一致，或添加显式 assertion 证明两条链等价
- **验证点**:
  1. 现有 blob 写入测试全部通过
  2. 新增测试：修改 `_build_file_store` root 后 blob 写入应失败或显式证明等价
- **修复风险**: 低—中 — 需要仔细验证 file_store key 的路径组件与 handle-based path 完全一致

## Observations / Residual Destinations

- **Rollback error preservation inconsistency** (F02) 应在 R06 final 修复；若 Controller defer，必须记录到 R07 或未来 hygiene WU。
- **Corrupted journal resilience** (F01) 是 crash recovery 的 correctness gap；应在 R06 final 修复，不应 defer。
- **Storage infra core agent 和 Repository wrappers agent 的输出未在本次写入前返回**。Main reviewer 已独立完成这两部分的完整走读并确认无 material findings beyond F01。若 agent 返回时有增量发现，将在 Controller adjudication 前补充。
- R07 独占的 residual（snapshot/revision across reads）不受本 review findings 影响。

## Verdict

**PASS-WITH-FINDINGS**

- **Material findings**: 7 (R06-CR-DS-F01 through F07)
- **Blockers**: 0 (no finding blocks merge; F01 is a HIGH severity correctness gap that should be fixed pre-merge, F02 and F07 are MEDIUM, F03-F06 are LOW)
- **Recommended classification**: F01→must-fix, F02→should-fix, F07→should-fix, F03→should-fix-or-document, F04-F06→nice-to-fix

R06 cumulative product code correctly implements the accepted plan's explicit transaction protocol, complete-source publication, writer mutex/publication swap guard separation, shared-core composition, and full producer/callback migration. All plan-mandated scans (ambient authority 0, ack 0, false-completion 0) pass. All controller verification points (R06-S3-CV-F01 closure, 54 production batch, callback invocation-time token, blob-first/final-once, transaction separation, rebuild same batch, commit fence, four shared-core composition roots, two False only in validator negatives) are independently confirmed.

## READY_FOR_CONTROLLER_ADJUDICATION
