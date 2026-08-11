# WU-CLI-DOWNLOAD-01 Slice 4 Deep Review — AgentMiMo

- 基线：`afde13dfeeb50f18bb35364ee15d8dcd23a7bcc2`
- 审查范围：当前未提交 diff（20 files, +3358/-1195）
- 审查维度：correctness、concurrency、atomicity、semantic ownership、typed integrity、SEC/CN Phase A/B、SC13 pure decisions、repair-first、cancel/failure、shared prefetch/materializer、测试真实性、allowlist/禁止兼容胶水
- 结论：**PASS**

---

## 1. 总结

实现正确地将 plan（base + v1 amendment + v2 amendment）转化为可验证行为增量。核心设计决策全部落地：

| 设计要求 | 实现证据 | 判定 |
|---|---|---|
| DL-F08 同 ticker 阻塞等待 | `_fs_storage_infra.py:1512` blocking=True + `:449` Condition reservation + `:1323-1329` unified release/notify | PASS |
| DL-F10 typed integrity classification | `source_integrity.py` 全模块 + Protocol/wrapper/core 三处同步实现 | PASS |
| Phase A/B identity-first | SEC `:494`/CN `:566` staged classify 为 begin 后首个 target operation | PASS |
| SC13 pure selection 无 side effect | `sec_sc13_filtering.py` 零调用 persist/batch/registry mutation | PASS |
| 修复优先于 company/rejection mutation | SEC `:560-595` whole-tree preflight → stable partition → repair → post-repair gate → company/deferred | PASS |
| 修复优先于 company mutation（CN） | `cn_download_workflow.py:219-236` selection → whole-tree preflight → repair-first → post-repair gate → company | PASS |
| 传输与 materialization 分离 | `prefetch_files_stream` → private variants → `materialize_prefetched_event` 单一 materializer | PASS |
| Rejected artifact prefetch 在 begin 前 | `sec_download_persistence.py:226` prefetch → `:237` begin | PASS |
| Artifact + registry 同 batch 原子发布 | `sec_download_persistence.py:247-300` materialize + registry save in same batch | PASS |
| No getattr/hasattr/compat/replay/prepared | `rg` 确认无此类模式 | PASS |
| 无 sleep 猜时序测试 | 新测试全部使用 Event/Barrier/Pipe + bounded deadline | PASS |
| Allowlist 守卫 | 实际修改 15 production + 6 test 文件，均在 effective allowlist 内 | PASS |

---

## 2. Storage Concurrency（DL-F08）

### 2.1 Per-ticker reservation + blocking writer

**直接证据**：`_fs_storage_infra.py:449-450` 定义 `threading.Condition()` 与 `_reserved_batch_tickers: set[str]`。`_reserve_batch_ticker`（`:1256-1263`）使用 `while` 循环 + `Condition.wait()` 阻塞等待同 ticker 的 reservation 或 active transaction。`_release_batch_ticker_reservation`（`:1276-1280`）discard + `notify_all`。

**判定**：正确。`while` 循环防止 spurious wakeup；同时检查 `_reserved_batch_tickers` 与 `_active_transaction_by_ticker` 覆盖"pre-registration"和"registered"两种同实例互斥状态。

### 2.2 Blocking cross-process writer lock

**直接证据**：`_fs_storage_infra.py:1512` 使用 `blocking=True` 调用 `_acquire_lock_token`。旧实现使用 `blocking=False` 并抛出 `RuntimeError`（"已存在跨进程活动 batch"），符合 DL-F08 要求"合法同 ticker writer 阻塞等待，不 fail-fast"。

**判定**：正确。

### 2.3 Recovery try-lock 保持 non-blocking

**直接证据**：`_fs_storage_infra.py:1877` 使用 `blocking=False`。recovery 是跨进程孤儿 batch 恢复，非正常业务 writer，保持非阻塞 skip 语义正确。

**判定**：正确。

### 2.4 Unified release/notify in `_close_active_batch`

**直接证据**：`_fs_storage_infra.py:1300-1329`。`_close_active_batch` 先释放跨进程 file lock（`:1305`），再在 `finally` 块内（`:1323-1329`）获取 `_batch_condition` 锁、清除 `_active_batches`、`_active_transaction_by_ticker`、`_reserved_batch_tickers` 并 `notify_all`。

**判定**：正确。所有 terminal 路径（commit、rollback、exception）统一通过 `_close_active_batch` 的 `finally` 释放本地状态并唤醒等待者。无遗漏的 release/notify 路径。

### 2.5 `begin_batch` 注册与 reservation 清理

**直接证据**：`_fs_storage_infra.py:480-577`。成功时 `else` 分支（`:571-576`）在 `_batch_condition` 锁内注册 active batch 并 discard reservation。失败时 `finally`（`:577`）调用 `_release_batch_ticker_reservation`。`registered` flag 防止双重释放。

**判定**：正确。

---

## 3. Storage Integrity（DL-F10）

### 3.1 Typed classification

**直接证据**：`source_integrity.py` 全模块。

- `SourceIntegrityStatus`：封闭为 `MISSING / COMPLETE / REPAIR_REQUIRED`。
- `SourceIntegrityReason`：`PHYSICAL_FILE_MISSING / SIZE_MISMATCH / DIGEST_MISMATCH`。
- `SourceIntegrityClassification.__post_init__`（`:49-75`）：严格校验 MISSING 无 revision/reasons、COMPLETE 无 reasons、REPAIR_REQUIRED 必有 reasons 且无重复。已存在 source 必须携带 revision。
- `has_same_source_publication_identity`（`:167-190`）：校验同一 target 后比较 `revision == revision`。

**判定**：正确。closed invariants 防止 god bag。

### 3.2 Whole-ticker inventory

**直接证据**：`_fs_source_document_core.py:508-555`（`list_source_integrity`）。单次 `_acquire_publication_guard` 内枚举 FILING + MATERIAL 的全部 document ID，调用 `_validate_published_source_manifest_unguarded` 校验 manifest 双向一致，再逐项调用 `_classify_source_integrity_unguarded`。返回按 `(source_kind.value, document_id)` 排序的 tuple。

**判定**：正确。单 guard 消除跨 publication 混合视图。

### 3.3 Malformed sha256 strict 结构错误

**直接证据**：`_fs_storage_infra.py:305-325`（`_require_canonical_sha256`）校验 `isinstance(value, str)`、`len(value) == 64`、`value == value.lower()`、`int(value, 16)`。`_fs_source_document_core.py:541-545` 调用该函数，结构非法直接抛 `ValueError`，不进入 repair classification。

**判定**：正确。符合 v1 amendment §6.1。

### 3.4 Preflight disposition

**直接证据**：`source_integrity.py:193-226`（`classify_source_integrity_preflight`）。纯函数，优先级：`REPAIR_REQUIRED > 1` → `MULTIPLE_REPAIR_REQUIRED`；`= 0` → `NoSourceRepairRequired`；`= 1` 且不在 accepted/rejected → `UNSELECTED_REPAIR_REQUIRED`；在 rejected → `SELECTED_REJECTED_REPAIR_REQUIRED`；在 accepted → `SelectedSourceRepairRequired`。

**判定**：正确。与 v2 amendment §5.2 完全一致。

### 3.5 Protocol/wrapper/core 同步

**直接证据**：
- `repository_protocols.py:572-642`：Protocol 定义三个方法。
- `fs_source_document_repository.py:508-588`：wrapper 委托 `self._repository_set.core`。
- `_fs_source_document_core.py:427-566`：core 实现。

**判定**：正确。无 `getattr`/`hasattr`/default/compat shim。

---

## 4. SEC Transport Separation

### 4.1 `prefetch_files_stream` — storage-neutral

**直接证据**：`sec_downloader.py:1545-1686`。签名无 `BatchToken`、`StoreDownloadedFile`、repository、callback。`allow_not_modified` 是 required transport 参数（True = conditional, False = unconditional），不是 request-level `overwrite` 的别名。yield 的是模块私有 discriminated variants：`_PrefetchStarted`、`_PrefetchedFile`（非空 immutable bytes）、`_PrefetchSkipped`（304）、`_PrefetchFailed`（path/contact-free）。

**判定**：正确。符合 v1 amendment §4.2。

### 4.2 `materialize_prefetched_event` — 唯一 materializer

**直接证据**：`sec_downloader.py:1688-1786`。单一实现将 prefetch variant 映射为 `DownloaderEvent`。`_PrefetchedFile` 调用 `store_file(name, stream, batch=batch)` 恰好一次；控制 variant 直接投影，不调用 callback。

**判定**：正确。`download_files_stream`（`:1788-1816`）组合 `prefetch_files_stream` + `materialize_prefetched_event`，无直接 HTTP 调用。

### 4.3 No replay/prepared/capability patterns

**直接证据**：`rg -n "prepared|replay|compat" dayu/fins/downloaders/sec_downloader.py dayu/fins/pipelines/sec_download_persistence.py` 无匹配。旧 `DownloadFilesStream` Protocol 已从 `sec_download_persistence.py` 删除。

**判定**：正确。符合 v1 amendment 删除 prepared callable/replay 设计。

---

## 5. SEC Phase A/B Identity-First

### 5.1 Phase A classify

**直接证据**：`sec_download_filing_workflow.py:230-266`。`classify_source_integrity` 返回 typed classification。`COMPLETE + overwrite=False` → `fast_skip_reason = "integrity_complete"` 且零 target HTTP。`MISSING` → `previous_meta = None`。`REPAIR_REQUIRED` → 正常进入后续阶段但 `allow_not_modified=False`。

**判定**：正确。

### 5.2 Phase A prefetch

**直接证据**：`sec_download_filing_workflow.py:480-488`。`prefetch_files_stream(allow_not_modified=False)` 在 `begin_batch`（`:492`）前完整消费。repair 强制 unconditional；显式 overwrite 同样 unconditional。

**判定**：正确。

### 5.3 Phase B staged classify 为首个 target operation

**直接证据**：`sec_download_filing_workflow.py:494`。`classify_staged_source_integrity(ticker, document_id, SourceKind.FILING, batch=token)` 在 `begin_batch`（`:492`）后立即调用，先于任何 store/upsert。

**判定**：正确。

### 5.4 Identity change → rollback + retry

**直接证据**：`sec_download_filing_workflow.py:500-528`。`has_same_source_publication_identity` 为 False → rollback → `_identity_round + 1 >= 3` 则抛 `SourceIntegrityRevisionConflictError`，否则递归重试。

**判定**：正确。

### 5.5 Phase B COMPLETE + overwrite=False → skip + rollback

**直接证据**：`sec_download_filing_workflow.py:529-549`。rollback batch → yield `FILING_COMPLETED(status="skipped", reason_code="integrity_complete")`。

**判定**：正确。不丢弃陈旧预取，直接 skip。

### 5.6 `reset_source_document` for REPAIR_REQUIRED / COMPLETE+overwrite

**直接证据**：`sec_download_filing_workflow.py:550-556`。`phase_b_integrity.status is not MISSING` → `reset_source_document` 清除旧 source，然后 `create_source=True`（`:703`）触发 create 而非 update。

**判定**：正确。

---

## 6. SC13 Pure Decisions

### 6.1 Typed decision variants

**直接证据**：`sec_sc13_filtering.py:40-87`。四个 frozen dataclass：`Sc13DirectionAccepted`、`Sc13DirectionRejectedWithArtifact`（携带 archive_cik、remote_files、source_fingerprint）、`Sc13DirectionRejectedRegistryOnly`（携带 diagnostic）、`Sc13DirectionRejectedAlreadyRegistered`。

**判定**：正确。互斥 variant，无 optional god bag。

### 6.2 Zero side effects during selection

**直接证据**：`rg -n "_persist_rejected_filing_artifact|begin_batch|commit_batch|rollback_batch|_record_rejection" dayu/fins/pipelines/sec_sc13_filtering.py` 输出为空。

`should_keep_sc13_direction`（`:466-562`）只返回 typed decision，不调用 persistence/batch/registry。`filter_sc13_by_direction`（`:425-461`）返回 `Sc13DirectionFilterResult(filings, rejections)`，rejections 按首次发现顺序去重。

**判定**：正确。符合 v2 amendment §5.3。

### 6.3 Decision cache with accession identity check

**直接证据**：`sec_sc13_filtering.py:510-512`。cache hit 时校验 `cached_result.filing.accession_number != filing.accession_number` → raise `ValueError`。

**判定**：正确。防缓存污染。

---

## 7. SEC Whole-Tree / Repair-First

### 7.1 Rejection collection after selection

**直接证据**：`sec_download_workflow.py:560-582`。从 `sc13_direction_cache` 收集 `Sc13RejectedDirectionDecision`；再用 `is_rejected(rejection_registry, document_id, overwrite)` 过滤已有 registry entry。两者合并为 `rejected_filing_id_set`。

**判定**：正确。

### 7.2 Whole-tree preflight before any mutation

**直接证据**：`sec_download_workflow.py:583-595`。`classify_source_integrity_preflight(host._source_repository.list_source_integrity(...))` 在 company batch、rejection batch 和任何 filing batch 之前调用。

**判定**：正确。

### 7.3 Stable partition of repair target

**直接证据**：`sec_download_workflow.py:592-595`。`sorted(filings, key=lambda item: (f"fil_{item.accession_number}" != repair_document_id,))` 将 repair target 排到首位。

**判定**：正确。其余 filing 保持相对顺序。

### 7.4 Company/deferred rejection after repair gate

**直接证据**：`sec_download_workflow.py:608-626`。`repair_document_id is None` 时直接 publish；否则等 repair target 完成后再 publish（`:681-708`）。

`_publish_sec_post_repair_mutations`（`:770-882`）先提交 company batch，再逐条处理 SC13 rejection intents：artifact 成功时 artifact+registry 同 batch；失败时 registry-only batch。

**判定**：正确。无无条件尾部 maintenance batch。

### 7.5 Repair failure → no company/rejection mutation

**直接证据**：`sec_download_workflow.py:682-684`。`filing_terminal_status == "failed"` → `break`，不进入 `_publish_sec_post_repair_mutations`。

**判定**：正确。company/rejection 保持 old。

### 7.6 Selected-then-rejected 6-K → typed fail closed

**直接证据**：`sec_download_filing_workflow.py:270-272`。`phase_a_integrity.status is REPAIR_REQUIRED` + `is_rejected(...)` → `raise SourceIntegrityPreflightError(SELECTED_REJECTED_REPAIR_REQUIRED)`。

**判定**：正确。不发布损坏的 rejected source。

---

## 8. CN Repair-First

### 8.1 Selection → whole-tree preflight → repair-first

**直接证据**：`cn_download_workflow.py:219-245`。`classify_source_integrity_preflight(host.source_repository.list_source_integrity(...))` 在 company batch 之前。repair target stable-partition 到首位。

**判定**：正确。

### 8.2 Company after post-repair gate

**直接证据**：`cn_download_workflow.py:248-260`。`repair_document_id is None` → `_publish_cn_company_after_repair`。否则等 repair target 完成后（`:319-345`）再 publish。

`_publish_cn_company_after_repair`（`:397-435`）是独立 helper，只在 clean gate 后调用。

**判定**：正确。

### 8.3 PDF/Docling 在 begin 前

**直接证据**：`cn_download_filing_workflow.py` 中 PDF 下载（`:107`）和 Docling 转换（`:302`）在 `_commit_cn_filing_assets_batch` 内的 `begin_batch`（`:563`）之前完成。

**判定**：正确。

### 8.4 Phase B identity-first

**直接证据**：`cn_download_filing_workflow.py:563-581`。`begin_batch` 后立即 `classify_staged_source_integrity`（`:566`）。identity change → rollback → `return "retry"`。COMPLETE + overwrite=False → `return "skip"`。

**判定**：正确。

### 8.5 三轮 churn

**直接证据**：`cn_download_filing_workflow.py:434-497`（`_retry_cn_filing_after_identity_change`）。递归调用 `run_cn_download_single_filing_stream`，`_identity_round + 1 >= 3` → `raise SourceIntegrityRevisionConflictError()`。

**判定**：正确。

---

## 9. Rejected Artifact Durable Unit

### 9.1 Prefetch before begin

**直接证据**：`sec_download_persistence.py:226-233`。`downloader.prefetch_files_stream(remote_files, allow_not_modified=not overwrite, ...)` 完整消费后，`:236` 取消检查点，`:237` `begin_batch`。

**判定**：正确。无 provider I/O 在 batch 内。

### 9.2 Artifact + registry 同 batch

**直接证据**：`sec_download_persistence.py:247-300`。materialize + `upsert_rejected_filing_artifact` + `save_download_rejection_registry` 均使用同一 `batch`。任一失败 → `rollback_batch`。

**判定**：正确。artifact 与 registry 不可分离。

### 9.3 `registry_after` 由 caller 构造

**直接证据**：`sec_download_workflow.py:820-832`。`_publish_sec_post_repair_mutations` 在调用 `_persist_rejected_filing_artifact` 前构造 `registry_after = dict(rejection_registry)` + `record_rejection(registry_after, ...)`。persistence 只消费，不自行构造。

**判定**：正确。registry 真值由 workflow owner 控制。

---

## 10. SEC/CN Filing Phase B 细节

### 10.1 `create_source=True` 语义

**直接证据**：`sec_download_filing_workflow.py:703`。`create_source=True` 硬编码。修复路径经过 `reset_source_document`（`:551`）清除旧 source 后 create 是正确的；MISSING 路径跳过 reset 但同样 create 也是正确的。

**观察**：这是一个轻微的语义耦合 — `create_source` 始终为 True，实际上 `create_source_document` 与 `update_source_document` 的分支逻辑被绕过了。但功能正确，因为 reset 后的 source 确实需要 create。

### 10.2 `_PrefetchedFile.content` 校验

**直接证据**：`sec_downloader.py:222-238`。`__post_init__` 校验 `isinstance(self.content, bytes)` 和 `not self.content` → raise。`frozen=True` + `slots=True` 防止属性重赋值。`bytes(payload)` 创建 immutable copy。

**判定**：正确。

---

## 11. CN 删除的 dead code

**直接证据**：`cn_download_filing_workflow.py` diff 删除了：
- `_resolve_fast_skip_result` — 被 `phase_a_integrity.status is COMPLETE and not overwrite` 替代。
- `_can_skip_by_pdf_sha` — 被 integrity-first 逻辑替代。
- `_read_file_entries` — 不再需要从 previous_meta 反推。
- `_read_required_text` / `_optional_text` — 不再需要。
- `_commit_cn_filing_metadata_batch` — 被统一的 `_commit_cn_filing_assets_batch` 的 retry/skip 返回值替代。

**判定**：正确。这些函数的语义已被 integrity-first 设计替代，删除是干净的。

---

## 12. 测试真实性

### 12.1 Deterministic synchronization

**直接证据**：`git diff HEAD -- tests/fins/... | grep "sleep"` 无新增 `sleep`。新测试使用 `threading.Event`（如 `BarrierPrefetchDownloader` 的 `second_prefetch_complete`/`first_source_committed`）、`multiprocessing.Event`、`Barrier`、`Pipe` 和 bounded test deadline。

**判定**：正确。无 timing-dependent 测试。

### 12.2 Coverage claims

**直接证据**：implementation artifact 列出 15/15 production 文件 >= 80%，最高 100%（`__init__.py`、`repository_protocols.py`），最低 80%（`sec_download_persistence.py`）。10 次 deterministic repeat 全部 `326 passed`。

**判定**：可信。

### 12.3 Key test scenarios

| 测试 | 覆盖的 plan 要求 |
|---|---|
| `test_sec_top_level_repairs_selected_corruption_before_company_mutation` | repair-first ordering, company after repair |
| `test_sec_top_level_unselected_corruption_fails_before_company_batch` | UNSELECTED_REPAIR_REQUIRED, zero mutation |
| `test_sec_same_target_overwrite_discards_stale_prefetch_and_last_writer_wins` | identity change → discard → retry → last-writer |
| `test_sec_different_target_overwrite_writers_publish_union` | different-target union |
| `test_rejected_prefetch_cancelled_before_begin_batch` | cancel after prefetch, zero begin/callback/commit |
| `test_sec_selected_repair_that_6k_policy_rejects_fails_before_mutation` | SELECTED_REJECTED_REPAIR_REQUIRED |
| `test_cross_process_writer_blocks_then_acquires_after_release` | blocking cross-process writer |
| `test_same_core_local_reservation_waits_then_notifies_on_release` | Condition-based local reservation |
| `test_recovery_try_lock_stays_nonblocking_while_writer_is_active` | recovery non-blocking skip |
| `test_source_integrity_classifies_published_staged_and_whole_tree` | classification + inventory |
| `test_source_integrity_preflight_fails_closed_for_multiple_and_unselected` | preflight disposition |

---

## 13. Allowlist 守卫

**直接证据**：implementation artifact §1 列出的 15 production + 6 test 文件均在 base + v1 + v2 effective allowlist 内。无 README、base plan、amendment、evidence/review artifact、Oracle/registry、Host/Engine 或 PR190 修改。

**判定**：PASS。

---

## 14. Residual Risks

| 风险 | 分类 | 说明 |
|---|---|---|
| OS/file lock 永久 I/O 卡死 | 已分类 platform residual | blocking writer 无业务 timeout，底层 I/O 卡死仍可能阻塞。属后续 storage reliability WU。 |
| Python 动态调用图不能形式化证明不可达 | 已接受 with controls | rg + AST + pyright + 人工 call-graph + deterministic barrier 共同举证。 |
| `sec_download_persistence.py` coverage 恰为 80% | 已满足硬门 | code review 应继续重点检查 304/partial failure/rollback/cancel。 |
| `create_source=True` 硬编码 | 轻微语义耦合 | 功能正确但绕过了 create/update 分支。非 blocker。 |

---

## 15. 结论

**PASS**。Slice 4 implementation 正确实现了 base plan §5.6 + v1 amendment + v2 amendment 的全部设计要求。storage concurrency 从 fail-fast 改为 blocking wait + unified notify；integrity classification 为 typed closed contract；Phase A/B identity-first 在 SEC/CN 均落地；SC13 selection 零 side effect；whole-tree preflight + repair-first 保证 company/rejection mutation 前 ticker tree 无 corruption；transport 与 materialization 分离；rejected artifact + registry 原子同 batch。测试使用 deterministic Event/Barrier，无 sleep 猜时序。allowlist 守卫无越界。

未发现 correctness、concurrency、atomicity 或 semantic ownership blocking finding。
