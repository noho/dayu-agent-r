# Round3 R3-C Aggregate Deepreview

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `7b24b070` (accepted plan commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-aggregate-deepreview-mimo.md`
- Review date: 2026-07-13
- Review range: `7b24b070..HEAD`，覆盖 R3-C S1、S2、S3 全部生产代码、测试、README 与 control docs

### Included scope

62 files changed, +7202 / -1349 lines。按 owner boundary 分四个 review slice：

| Slice | Production files | Test files | Reviewer |
|---|---|---|---|
| S1 Storage Identity / Commit / Durability | `_fs_storage_utils.py`, `_fs_storage_infra.py`, `_fs_blob_core.py`, `local_file_store.py`, `repository_protocols.py` | `test_fins_storage_atomicity.py`, `test_fins_storage_provider.py` | Subagent S1 |
| S2 Ingestion Atomicity / Temp-Less Assets | `docling_upload_service.py`, `ingestion_runtime.py`, `cn_download_filing_workflow.py`, `cn_download_models.py`, `cn_download_protocols.py`, `cn_download_source_upsert.py`, `cninfo_downloader.py`, `hkexnews_downloader.py` | `test_docling_upload_service.py`, `test_fins_ingestion_runtime.py`, `test_cn_download_workflow.py`, `test_cn_download_runtime.py`, `test_cn_pipeline.py`, `test_cninfo_downloader.py`, `test_hkexnews_downloader.py` | Subagent S2 |
| S3 Host Wait Adapter / Service Glue | `wait_adapter.py`, `fins_wait_adapter.py` (new), `host_assembly.py` | `test_fins_wait_adapter.py` (new), `test_fins_ingestion_tools.py`, `test_fins_ingestion_runtime.py`, `test_fins_storage_provider.py`, `test_wait_adapter_polling.py`, `test_wait_poller_runtime.py`, `test_wait_observation_runner.py`, `test_open_host_runtime.py`, `test_host_assembly.py`, `test_import_boundary.py` | Subagent S3 |
| Tests & Docs | N/A | 全部 S1/S2/S3 测试 + README + control doc | Subagent Tests |

### Excluded scope

- `docs/reviews/` 下的 implementation、code review、controller adjudication artifacts（review 过程产物，非生产代码）
- `utils/smoke_host_public_awaiting_entrypoint.py`（smoke 脚本，按 CLAUDE.md 无覆盖率要求）
- `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`（plan artifact，非代码）

### Parallel review coverage

四个 subagent 各自独立审查指定范围，主 reviewer 整合结论。无冲突发现。

---

## Findings

未发现实质性问题。

所有四个 review slice 均返回 pass，无 correctness、semantic ownership、contract 或 test gap 级别的 findings。

### S1 — Storage Identity, Commit Point, And Local Durability: PASS

逐项审查结果：

1. **`_normalize_ticker()` fallback 经过 single-component validator** — PASS
   - `dayu/fins/storage/_fs_storage_utils.py:56-74`：canonical 和 fallback 两条路径均通过 `_normalize_path_component()` 校验，拒绝 empty、`.`、`..`、`/`、`\`、绝对路径、Windows drive letter。

2. **`_validate_component()` / `_validate_object_key()` 覆盖** — PASS
   - `_normalize_path_component` (line 30-53)：拒绝空、`.`、`..`、`/`、`\`、`Path.is_absolute()`、`PureWindowsPath().drive`。
   - `_normalize_object_key` (line 152-179)：拒绝空、leading `/`、`\`、empty segment、`..` segment，每个 segment 通过 `_normalize_path_component`。
   - 测试覆盖：`""`、`"   "`、`"."`、`".."`、`"a/b"`、`"a\\b"`、`"C:"` 覆盖单组件；`""`、`"/absolute"`、`"a//b"`、`"a/../b"`、`"a\\b"`、`"C:/b"` 覆盖多组件。

3. **`local://` URI 解析约束回 `portfolio_root`** — PASS
   - `dayu/fins/storage/_fs_storage_utils.py:250-279`：解析后 `_normalize_object_key` + `path.relative_to(normalized_root)` containment check。
   - 测试 `test_local_uri_owner_rejects_symlink_escape` 验证 symlink escape 被拒绝。

4. **`store_file()` Source/Processed handle 统一 existence check** — PASS
   - `dayu/fins/storage/_fs_blob_core.py:142-143`：`_get_handle_meta(handle)` 无 isinstance 条件分支，两类 handle 不存在时均抛 `FileNotFoundError`。
   - 测试确认 `put_keys == []`（FileStore 未被调用）。

5. **`commit_batch()` commit point：COMMITTED 是唯一 commit point** — PASS
   - `dayu/fins/storage/_fs_storage_infra.py:259-291`：状态机 `BACKED_UP_TARGET -> SWAPPED_TARGET -> COMMITTED`，每步写 journal。
   - `_rollback_precommit_batch` (line 334-358)：SWAPPED_TARGET 无 COMMITTED 时删除 new target、恢复 backup（行为反转 R3-C-PF-04）。

6. **`recover_orphan_batches()` 恢复语义** — PASS
   - STARTED：清理 staging，不操作 target/backup。
   - BACKED_UP_TARGET：删除未提交 target，恢复 backup。
   - SWAPPED_TARGET：删除未提交 target，恢复 backup（与旧行为相反）。
   - COMMITTED：保留 target，删除 backup。

7. **commit + rollback 双重失败传播形状 (R3-C-PF-05)** — PASS
   - `dayu/fins/storage/_fs_storage_infra.py:268-285`：`raise commit_error from rollback_error` + `add_note("recovery evidence retained")`。
   - 测试断言 `exc_info.value is commit_error`、`exc_info.value.__cause__ is rollback_error`、journal/backup 保留。

8. **`LocalFileStore.put_object()` unique temp / fsync / atomic replace / dir sync** — PASS
   - `dayu/fins/storage/local_file_store.py:66-87`：UUID temp → write loop → `flush()` + `os.fsync()` → `os.replace()` → `_fsync_directory(parent)` → `finally: temp.unlink(missing_ok=True)`。

9. **Journal COMMITTED 使用 atomic JSON + file fsync + directory sync (R3-C-PF-10)** — PASS
   - `_write_json` (line 524-551)：unique temp → fsync → replace → dir sync。测试验证 `token.journal_path.parent in committed_sync_paths`。

### S2 — Single-Document Ingestion Atomicity And Temp-Less CN/HK Assets: PASS

逐项审查结果：

1. **upload non-delete mutation 无条件使用一个 caller-owned document batch** — PASS
   - `docling_upload_service.py:331`：`begin_batch(ticker)` 无条件调用。`_acknowledge_source_before_blob_write` 通过 `_execute_with_auto_batch` 检测已有 active batch piggyback，不创建新 batch。

2. **token lifecycle 正确** — PASS
   - 三处实现（upload、generic download、CN/HK workflow）均遵循：`commit_started = True` 在 `commit_batch()` 调用之前设置。commit failure 后 finally 不执行 rollback（`commit_started` 已为 True），storage 层内部处理 pre-commit rollback。

3. **CN/HK asset 改为 pdf_bytes，消除 tempfile** — PASS
   - `cn_download_models.py`：`pdf_path: Path` → `pdf_bytes: bytes`。
   - `cninfo_downloader.py` / `hkexnews_downloader.py`：移除 `tempfile`/`NamedTemporaryFile`，直接返回 `pdf_bytes=payload`。
   - `cn_download_filing_workflow.py`：删除 `_unlink_temp_pdf`、`_find_file_meta`、`_should_reset_before_download`。

4. **network/convert 放 batch 外，mutations 收束到无 yield/await 的 batch 段** — PASS
   - `_commit_cn_filing_assets_batch` (line 404-568) 和 `_commit_cn_filing_metadata_batch` (line 571-659)：纯同步函数，内部无 yield/await。PDF 下载和 Docling 转换在 batch helper 调用之前完成。

5. **取消/exception/generator close 在 commit 前不得留下变更** — PASS
   - `_raise_if_cancelled` 抛出 `CnDownloadCancelledError`，finally 块 `rollback_batch` 清理 staging。
   - processed marker 通过 piggyback 到同一 source batch，随 rollback 一并撤销。
   - async generator 只在 yield 点可被 close，此时不持有任何 batch。无 temp 文件。

6. **commit 成功后 terminal event 才发出** — PASS
   - `FILING_COMPLETED` 在 `_commit_cn_filing_assets_batch` / `_commit_cn_filing_metadata_batch` 返回后才 yield。

### S3 — Host Adapter Snapshot And Service-Owned Fins Wait Glue: PASS

逐项审查结果：

1. **`WaitAdapterSnapshot` frozen/slots，字段严格为三** — PASS
   - `dayu/host/wait_adapter.py:237-264`：`@dataclass(frozen=True, slots=True)`，字段 `tool_name: str`、`resume_token: str`、`created_at: datetime`。`__post_init__` 校验非空、长度、timezone-aware。

2. **snapshot projection 使用 Host `parse_utc_timestamp()`** — PASS
   - `dayu/host/wait_adapter.py:2257-2276`：`_adapter_snapshot_from_wait_record` 调用 `parse_utc_timestamp(record.created_at)`。

3. **`WaitAdapterSnapshotProjectionError` fail-closed 路径** — PASS
   - `dayu/host/wait_adapter.py:233-234`：`class WaitAdapterSnapshotProjectionError(ValueError)`。
   - 投影函数在 `except (TypeError, ValueError)` 中包装为该 error。

4. **poll/abandon 在 adapter 调用前捕获 projection error** — PASS
   - poll 路径 (line 1082-1091)：捕获 → `ADAPTER_ERROR` → `_release_with_backoff`。
   - abandon 路径 (line 1335-1349)：捕获 → `ABANDON_ERROR`。
   - adapter 不会收到非法数据。

5. **Service adapter 只接收 snapshot** — PASS
   - `dayu/service/fins_wait_adapter.py`：`poll_wait(self, snapshot: WaitAdapterSnapshot)` 和 `abandon_wait(self, snapshot: WaitAdapterSnapshot)`。无 `WaitRecordRow` 依赖。

6. **旧 Fins wait_adapter.py 已删除** — PASS
   - `git diff --diff-filter=D` 确认删除。

7. **Fins -> Host import scan 清零** — PASS
   - `grep -rn "from dayu.host" dayu/fins/ --include="*.py"` 无匹配。

8. **行为等价性** — PASS
   - `PENDING/RUNNING` → `NotReady`；`SUCCEEDED` → `Ready(Completed)`；`FAILED` → `Ready(Failed)`；`CANCELLED` → `Ready(Cancelled)`；`LOST` → `Lost`。映射与旧行为等价。
   - 行为改进：旧 adapter 对非法 timestamp 静默回退为 `now()`；新 adapter 由 Host fail-closed 拒绝投影。

### Tests — PASS

逐项审查结果：

1. **test_fins_storage_atomicity.py (S1)**：SWAPPED_TARGET 行为反转 (R3-C-PF-04) 有 `test_swapped_target_recovery_without_old_target_deletes_new_target` 覆盖；commit+rollback 双失败 (R3-C-PF-05) 有 `test_commit_and_rollback_failure_preserve_primary_cause_and_recovery_evidence` 覆盖；非法 component 矩阵有参数化测试覆盖。

2. **test_docling_upload_service.py (S2)**：旧"final upsert 失败保留 incomplete meta"语义已重写为 `test_execute_upload_create_final_failure_leaves_document_absent`（断言 source/blob 全部不可见）和 `test_execute_upload_update_failure_keeps_previous_document`（断言旧文档不变）。双失败测试覆盖 primary + cause。

3. **test_cn_download_workflow.py (S2)**：取消测试已从"保留 staging"迁移到"旧状态/absence 不变"。batch identity spy 断言单一 caller-owned token。CancelledError 断言触发一次 rollback。

4. **test_fins_wait_adapter.py (S3)**：`test_wait_adapter_receives_minimal_host_snapshot` 断言 snapshot 只有三个字段。空/超长 resume token 和非法 timestamp 有参数化测试。

5. **test_import_boundary.py (S3)**：Fins->Host 特判已删除。`SERVICE_FORBIDDEN_PREFIXES` 继续包含 `dayu.host.durable`。

### README / Control Docs — PASS

1. **docs/host/issues-implementation-control.md**：R3-C gate 记录三个 slice 已 accepted（S1 `6e9ad77e`、S2 `272575e4`、S3 `9ef24a68`），next gate 是 `R3-C aggregate validation / deepreview`。无 stale owner 或 stale next gate。

2. **dayu/fins/README.md**：移除 wait adapter Host import 例外，改为 `Service Fins wait adapter assembly`。storage identity、per-document atomic mutation、temp-less CN/HK asset 已记录。

3. **dayu/service/README.md**：新增 `fins_wait_adapter` 入口，边界约束明确。

4. **tests/README.md**：同步更新，覆盖新增测试文件。

---

## Open Questions

无。

---

## Residual Risk

| Risk / uncovered area | Classification | Owner / destination |
|---|---|---|
| S1 `test_orphan_recovery_follows_journal_commit_point` 只测试 `old_target_exists=True`，`old_target_exists=False` 变体未覆盖所有 phase | test gap, non-blocking | S1 orphan recovery test enhancement（不阻塞 aggregate acceptance） |
| S1 SWAPPED_TARGET recovery `staging_dir.exists()` 分支（line 833-834）未被直接测试 | test gap, non-blocking；结构正确（已 path trace） | S1 recovery test enhancement |
| S3 `fins_wait_adapter.py` 导入 `FinsErrorKind` 和 `FinsResultStatus` 但生产代码未使用 | pre-existing，从旧 module 平移 | 不在 R3-C scope |
| OS/hardware 在 rollback rename 本身失败时可能留下需 recovery 的物理目录 | covered by S1 recovery contract | `dayu.fins.storage` orphan recovery |
| Directory fsync 在不支持的 platform 上只能 best-effort | assigned to later WU | Fins filesystem backend portability WU |
| 已成功提交的前一 document 不因后续 document 失败回滚 | accepted non-goal | multi-document transaction 只有新业务需求时另开 WU |
| CN/HK Docling 同步第三方转换在线程内不能强制中断 | tracked by existing deferred finding | future process/subprocess isolation WU |
| Tool-security 四项（upload allowlist、URL provenance、byte budget、LLM schema） | assigned to later work unit | 见 plan Tool-Security Deferred Items |

所有当前 R3-C residual 均已分类；没有未分类 residual。

---

## Verification Summary

| Check | Result |
|---|---|
| S1 focused tests | 130 passed |
| S2 focused tests | 194 passed |
| S3 focused tests | 326 passed |
| Full Fins regression | 519 passed, 1 skipped |
| pyright | 0 errors |
| Fins->Host import scan | 0 matches |
| Temp/PDF path scan | 0 matches in production/pipeline code |
| LLM-facing schema diff (`git diff -- dayu/config/prompts dayu/fins/tools`) | empty (no changes) |
| git diff --check | clean |

---

## Conclusion

**R3-C aggregate deepreview pass。**

三个 implementation slice（S1 Storage Identity / Commit Point / Local Durability，S2 Single-Document Ingestion Atomicity / Temp-Less CN/HK Assets，S3 Host Adapter Snapshot / Service-Owned Fins Wait Glue）均完整闭环：

1. **S1 storage identity / commit point / local durability owner**：identity 校验在 `_fs_storage_utils`，commit state machine 在 `_FsStorageInfra`，put 原子性在 `LocalFileStore`，handle existence check 在 `_FsBlobMixin.store_file()`。COMMITTED 是唯一 commit point；SWAPPED_TARGET 无 COMMITTED 时行为已反转（删除 new target 恢复 backup）；commit + rollback 双重失败通过 `raise commit_error from rollback_error` 传播。无 caller/downstream 补偿 storage truth。

2. **S2 upload / generic download / CN/HK single-filing atomicity**：只有 caller-owned active batch 和 storage-owned commit point。commit failure 后无二次 rollback。CN/HK asset 完全 bytes contract，无 temp handoff / pdf_path 兼容。

3. **S3 Host wait adapter snapshot 与 Service-owned Fins wait glue**：Fins -> Host 反向依赖已删除，无兼容 shim。Host 只向 adapter 投影最小 typed snapshot（tool_name, resume_token, created_at）。

4. **Tests** 断言 owner-level contract，不把旧 fixture/fake/Host durable shape 固化到 Fins 层。

5. **README / control docs** 只记录已落地边界，无 stale owner 或 stale next gate。

6. **工具安全** 四项（upload allowlist、URL provenance、byte budget、LLM schema）保持 deferred，未在 R3-C 实现或测试中落地。
