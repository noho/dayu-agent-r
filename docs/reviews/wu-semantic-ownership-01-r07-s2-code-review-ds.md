# WU-SEMANTIC-OWNERSHIP-01 R07-S2 第二路累计 S1+S2 code review（AgentDS）

## 1. Gate 身份与基线

- **所属工作单元**: 既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`，内部 sub-WU `R07`。
- **当前 gate**: R07-S2 implementation 的 MiMo/DS 双路 cumulative code review（第二路 DS）。
- **审查基线**: HEAD `386fef8d7a7ecbd977c455ca86bb8bab875d1a98` 上全部未提交累计 S1+S2 product/test/README changes。
- **权威输入**: 根 `AGENTS.md`、`docs/fins/design.md`、accepted plan（SHA-256 `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`）、S1 re-review artifacts、S2 implementation artifact、S2 Controller validation artifact。
- **审查范围**: 累计 S1+S2 组合行为；controller/control/review artifact 只作证据，不审查。
- **本 artifact 角色**: 只审查并写 review artifact；不修改生产代码、测试、README、plan、control，不 stage/commit/push/PR。

## 2. 审查方法

按 plan §10.2 要求执行完整累计 code review，覆盖七个重点领域：

1. S1 opaque external identity → internal key 的唯一 storage owner，所有 inventory/read/write/delete/recovery/cleanup 路径一致性
2. S2 persisted opaque revision exact equality、complete-source mutation 原子发布、light/full stable snapshot 的同版一致性、显式 source-kind 0/1/2 resolution、preprocess/SEC fiscal/active 6-K 单 snapshot 生命周期
3. Snapshot resource ownership、并发 close/retry、publication guard/FD/temp-root cleanup 的主次异常关系和完整 path-free exception graph；CV-F01..03 复核
4. containment/symlink/atomic/recovery/typed errors/security retained
5. S3 deferred scope 不得误报为 S2 缺口
6. README 当前事实、测试是否 owner-level
7. Adversarial failure pass、semantic ownership drift、过度耦合、race/resource leak、exception graph、安全保留与 scope audit

每个 finding 含严重度、直接代码证据、根因 owner、可执行最小修复；区分 material finding / observation / accepted deferred scope。

## 3. S1 既有 findings 回退检查

### 3.1 identity mapping 完整性

- `_normalize_ticker` / `_normalize_document_id` 已从所有 storage 文件删除，scan 结果为 0。
- `directory_name` / `lock_path.stem` / `child.name`（用于反推业务 identity）已从 storage 目录删除，scan 结果为 0。
- 所有 ticker target/staging/backup/locks/recovery 路径均使用 `_derive_storage_key` 与 identity descriptor，无 raw identity path join 残留。
- `_FsCompanyMetaMixin._published_ticker_directory_names` 已迁移为通过 descriptor 恢复 external ticker，lock-only 条目输出 typed status 且 business ticker 为 `None`，不投影 key/stem。
- `cleanup_stale_filing_documents` 已迁移：先从 descriptor 恢复 external document id，再对该 external id 执行 `fil_` 业务判断，不依赖 private key prefix/value。
- `DownloadRejectionRegistry` 的 JSON key 保留 exact external document id（不是路径，无 separator 拒绝），与 entry 内 `document_id` 双向校验。
- AST 审计：storage 目录内所有 `ticker` / `document_id` 出现在 `Path` `/` 或 `f-string` 的操作经逐项人工分类，均属 private key 操作、business payload/meta serialization 或 error text，无 raw external identity path join。

**结论：S1 所有 findings 保持关闭，无回归。**

### 3.2 S1 targeted tests 覆盖

S1 新增/替换的 owner-level 测试节点（`test_opaque_ticker_and_document_identity_round_trip_all_storage_namespaces`、`test_opaque_identity_round_trips_unicode_hierarchy_separator_drive_dot_and_dotdot`、`test_identity_mapping_detects_collision_corruption_and_business_meta_mismatch`、`test_company_inventory_never_projects_internal_storage_key`、`test_lock_only_company_inventory_has_no_business_ticker_or_internal_key`、`test_stale_filing_cleanup_uses_descriptor_external_id_in_opaque_layout`、`test_recovery_round_trips_opaque_ticker_without_path_name_inference`、`test_complete_validator_rejects_identity_descriptor_symlink_and_mismatch`、`test_filename_absolute_and_local_uri_attacks_remain_rejected_for_opaque_id_documents`、`test_preprocess_request_round_trips_hierarchical_document_id_through_storage`）均通过。

## 4. S2 Persisted Revision 审查

### 4.1 `SourceDocumentRevision` owner contract

- `SourceDocumentRevision.digest` → `token` breaking rename 已完成，无 alias、property、双字段或 compat shim。
- `__post_init__` 只校验 `token == ""` 拒绝，接受任意非空字符串。符合 plan "只承诺非空字符串的 exact opaque equality"。
- 旧 `.digest` scan 在生产代码与测试中均为 0 残留。
- `_build_source_revision` / selected-field hash builder / SHA grammar 已删除，scan 为 0。

**结论：revision model contract 正确实施。**

### 4.2 revision 生成与发布

- `_prepare_complete_source_meta`（`_fs_source_document_core.py:1507`）在 source create/update/replace/delete/restore 的最终 meta 中：
  - `normalized.pop(_SOURCE_REVISION_META_FIELD, None)` — 删除任何既有 token（防止 producer 注入）
  - `SourceDocumentProvenance.from_meta(normalized, source_kind)` — 校验 provenance 合法后
  - `normalized[_SOURCE_REVISION_META_FIELD] = uuid.uuid4().hex` — 生成新 token
- `_SOURCE_REVISION_META_FIELD = "_published_source_revision"` 为 storage 私有字段名，由 `_source_meta_without_revision` 从 business meta 中排除，不进入 consumer 可见的 `snapshot.source_meta`。
- Complete-source validator 在 `_validate_complete_source_directory`（`_fs_storage_infra.py:902`）调用 `_source_revision_from_meta(meta)` 确认 token 存在且为非空字符串。
- 四个 composition roots（`DefaultFinsRuntime.create`、`CnPipeline.__init__`、`SecPipeline.__init__`、standalone 6-K repair）均不传 revision 参数。

**结论：revision 生成与发布所有权单一，producer 不可注入。**

### 4.3 `get_source_revision` checkpoint

- `get_source_revision`（`_fs_source_document_core.py:483`）只机械读取 persisted token 并构造 `SourceDocumentRevision(token=...)`，不重算 hash。
- 该方法仍存在是为了支持 read_runtime.py 的 before/after equality（S3 将删除），符合 plan S2 checkpoint contract。
- 方法正确处理了 is_deleted 检查：deleted source 抛出 `FileNotFoundError`。

**结论：checkpoint 实现正确，S3 删除路径明确。**

### 4.4 revision 不变性

- processed/company/maintenance-only batch 不经过 `_prepare_complete_source_meta`，因此不改变 token。
- rollback 不提交 staging，published token 不变。
- 测试 `test_published_revision_is_persisted_and_changes_only_with_source_publication`、`test_rollback_and_non_source_batch_preserve_published_revision` 验证此行为。
- 测试 `test_source_document_revision_accepts_nonempty_opaque_token_and_rejects_empty` 验证 model 边界。

**结论：revision 不变性正确。**

## 5. S2 Snapshot 审查

### 5.1 snapshot API contract

- `read_source_snapshot(ticker, document_id, source_kind=None, *, materialize_files: bool)` 是唯一 storage-owned 一致读取入口。
- light snapshot（`materialize_files=False`）：在同一 publication guard 下返回 exact identity、source kind、meta、provenance、revision、files、primary filename，不暴露 published path 或 local URI。
- full snapshot（`materialize_files=True`）：从 guard 内打开的全部 regular file FDs 复制到 `tempfile.mkdtemp` 私有临时树；返回的 `Source.get_source()` / `get_primary_source()` 的 `materialize()` 只返回临时树路径。
- `SourceSnapshotProtocol` 是 typed protocol，具体实现类 `_FsSourceSnapshot` 保持 private。

**结论：snapshot API contract 正确实施。**

### 5.2 同版一致性

- `_acquire_snapshot_attempt_unguarded` 在一次 guard 内读取：identity/meta/provenance/revision/files/primary marker。
- `_build_published_marker` 包含：source_kind、revision、is_deleted、ticker descriptor bytes、document descriptor bytes。
- `_read_source_snapshot` 的 post-copy 核对（line 523-547）：
  - 再次获取短 publication guard
  - 读取当前 published marker（包含 revision + identity descriptors）
  - 与 attempt marker 做 exact equality 比较
  - 匹配时返回；不匹配时 discard attempt 并重试
- 测试 `test_snapshot_descriptor_meta_provenance_primary_and_files_share_one_revision` 验证同版一致性。

**结论：snapshot 同版一致性保证正确。**

### 5.3 source kind resolution (0/1/2)

- `_resolve_snapshot_source_kind_unguarded`：
  - 显式 source kind：验证 meta 存在，返回该 kind。
  - 缺省 source kind：调用 `_existing_snapshot_source_kinds_unguarded` 枚举 filing/material：
    - 0 个：`FileNotFoundError`
    - 1 个：返回该 kind
    - 2 个：`ValueError("source kind 不明确：filing 与 material 同时存在")`
- 显式 source kind 下，filing/material 同 document ID 共存不会误判：只有指定 kind 的 meta 被读取；post-copy marker 也只看该 kind。
- 测试 `test_snapshot_explicit_source_kind_ignores_other_kind_with_same_document_id` 验证此行为。

**结论：source kind resolution 正确。**

### 5.4 有界稳定读取

- `_STABLE_READ_ATTEMPT_LIMIT = 3`（module-private `Final[int]`），未在 public contract、README、test assertion 中暴露。
- 每次 attempt：acquire（guard 内读 FD）→create temp→copy→marker verify；marker 变化时 discard 重试。
- 持续变化：全部 attempt 耗尽后抛出 `SourceSnapshotConsistencyError`（不携带 path/key/revision）。
- 短暂变化恢复：测试 `test_snapshot_transient_change_recovers_and_cleans_discarded_attempt` 验证。
- 持续变化失败：测试 `test_snapshot_sustained_change_raises_typed_consistency_failure_and_cleans_resources` 验证。
- 静态 corruption：测试 `test_snapshot_fd_copy_silent_mutation_is_corruption_without_revision_change` 验证静默 inode/content/fstat 变化保持 corruption 分类，不伪装为 `source_changed`。

**结论：有界稳定读取正确实施，内部 attempt 次数未泄漏。**

### 5.5 snapshot resource 生命周期

- `_SnapshotResourceState` 持有 `temp_root`、`closed`、`lock`。
- `close()`：在锁内设置 `closed=True`，调用 `_remove_snapshot_temp_root`，仅在 rmtree 成功后设置 `temp_root=None`。
  - rmtree 失败：`closed` 保持 True（资源不可读），`temp_root` 保持原值（下次 close 可重试）。
  - rmtree 成功：`temp_root=None`，后续 close 为幂等 no-op。
- `require_open()` / `require_open_root()` 在锁内检查 `closed`，关闭后抛出 `RuntimeError`。
- 测试 `test_snapshot_close_failure_retains_cleanup_root_for_concurrent_retry` 验证：首次 rmtree 失败后资源不可读、temp root 保留、并发重试只完成一次真实删除、后续幂等。

**结论：snapshot resource 生命周期正确，CV-F02 修复有效。**

### 5.6 A/B publication 不混合

- 测试 `test_snapshot_concurrent_ab_publication_never_mixes_files`：真实 filesystem、真实 batch/atomic commit、A/B 各有至少两个关联文件、不同 primary/meta/provenance marker，snapshot 只能全 A 或全 B。

**结论：A/B publication 不混合已真实验证。**

## 6. Exception Graph 审查（含 CV-F01..03 复核）

### 6.1 `_acquire_snapshot_attempt` guard release（CV-F01 复核）

`_fs_source_snapshot.py:599-658`：
- acquire 成功但 release 失败 → release 为主异常，已取得的 FDs 通过 `_cleanup_snapshot_attempt` 关闭（FD close 再失败只追加 secondary note）
- acquire 失败且 release 也失败 → acquire 为主，release 通过 `_append_secondary_error_note` 追加 action/type/errno
- acquire 失败且 release 成功 → acquire 为主
- 状态非法（attempt=None 但无 error）→ `RuntimeError`

**CV-F01 状态：CLOSED。三态 primary-preservation 已正确实施。**

### 6.2 `_read_published_marker` guard release（CV-F01 复核）

`_fs_source_snapshot.py:1007-1073`：
- marker read 失败且 guard release 失败 → marker_error 为主，release 追加 secondary note
- marker read 成功但 guard release 失败 → release 为主（re-raise）
- marker read 失败但 guard release 成功 → marker_error 为主

**CV-F01 状态：CLOSED。不再有 raw `try/finally` 覆盖主因。**

### 6.3 Initial fstat + unregistered stream close（CV-F03 复核）

`_fs_source_snapshot.py:743-756`：
- `_read_stable_file_state(stream)` 失败 → fstat 为主
- stream.close() 也失败 → close 追加 secondary note（action/type/errno）
- stream 不加入 `open_files` 列表

**CV-F03 状态：CLOSED。fstat 主因保留，close failure 安全附加。**

### 6.4 `_cleanup_snapshot_attempt` 统一主次规则

`_fs_source_snapshot.py:1226-1282`：
- 既有 `primary_error` 时：FD close 失败和 temp-root remove 失败都只追加 secondary note
- 无 `primary_error` 时：首个 cleanup 失败成为 `cleanup_primary`，后续 cleanup 失败追加到 `cleanup_primary`
- `retain_temp_on_success`：仅在无任何 failure 时保留 temp_root

测试覆盖：
- `test_snapshot_acquire_primary_survives_guard_release_secondary_without_locator` — acquire 主 + release 次
- `test_snapshot_guard_release_primary_survives_fd_close_secondary_without_locator` — release 主 + FD close 次
- `test_snapshot_marker_read_primary_survives_guard_release_secondary_without_locator` — marker 主 + marker guard release 次
- `test_snapshot_marker_primary_survives_fd_and_temp_cleanup_failures` — marker/copy 主 + FD/temp 双 cleanup 次
- `test_snapshot_transient_discard_cleanup_preserves_first_failure_and_attempts_all` — transient discard 双 cleanup 次

所有测试均验证完整 exception graph path-free（无 workspace root、无 private key、无 temp path 泄露）。

**结论：exception graph primary-preservation 完整且 path-free。**

### 6.5 `_append_secondary_error_note` path-free 验证

`_fs_storage_utils.py:526-549`：
- 只包含 `action`（固定字符串）、`error_type`（class name）、可选 `errno`
- 不包含 secondary error message（可能含 path）
- 使用 `add_note()` 标准 API

**结论：secondary note 不泄露 locator。**

## 7. Consumer Migration 审查

### 7.1 preprocess（`ingestion_runtime.py:_preprocess_one_document`）

- 先 `begin_batch`，再 `read_source_snapshot(materialize_files=True)`
- processor/sections/tables 消费同一 snapshot
- `snapshot.close()` 在 inner finally
- commit 前 close；commit 前失败 → exactly-once rollback
- commit 开始后（`commit_started=True`）→ no secondary rollback

测试 `test_preprocess_snapshot_and_processed_publication_share_source_revision` 验证：
- source_meta/processed_meta/revision/processed publication 一致
- revision token 不进入 processed_meta JSON

**发现 R07-S2-DS-F01（见 §12.1）：snapshot.close() exception masking**

### 7.2 SEC fiscal（`sec_fiscal_fields.py`）

- `_extract_fiscal_from_snapshot` 取得一份 full snapshot
- `_build_download_local_file_map` 将全部 XBRL 文件映射到同一 snapshot 临时树
- `_pick_download_xbrl_file` 保持既有后缀优先级与 XML fallback 排除规则
- `finally: snapshot.close()` 保证清理
- 未引入 `has_xbrl_instance` 内容嗅探或新文件分类 schema

测试 `test_sec_fiscal_files_consume_one_storage_snapshot` 验证单 snapshot 生命周期。

**发现 R07-S2-DS-F01（见 §12.1）：同样存在于 SEC fiscal consumer**

### 7.3 active 6-K repair（`sec_6k_primary_document_repair.py`）

- 在 caller-owned batch 已持 writer mutex 前提下取得一份 full snapshot
- meta、候选 HTML 与 primary 评分来自同一 snapshot
- `finally: snapshot.close()`，关闭后才 stage mutation
- prepared prepublication payload 路径保持现有临时 payload owner

测试 `test_active_6k_candidate_assessment_consumes_one_storage_snapshot` 验证。

**发现 R07-S2-DS-F01（见 §12.1）：同样存在于 6-K consumer**

### 7.4 processor 不变性

- 所有 processor 类继续只接收标准 `Source`，不接 revision/provenance/path provider 参数
- processor registry 未修改
- `dayu/documents/processors/source_snapshot.py` 未修改

**结论：processor contract 不变，符合 plan §3.4。**

## 8. Security Retained 审查

| 机制 | 状态 | 证据 |
|---|---|---|
| filename / entry name 单路径组件拒绝 | **保留** | `_normalize_filename` 拒绝 separator/dot/dotdot/absolute/drive |
| local URI / object key containment | **保留并收紧** | URI 只含 private key + safe filename；`_local_path_from_uri` 验证 |
| path containment | **保留** | `_require_contained_regular_file` / `_require_contained_path` |
| symlink rejection | **保留并扩展** | ticker/doc descriptor、meta、manifest、business files、snapshot files 全部 fail closed |
| atomic JSON/file write | **保留** | identity descriptor 复用 `_write_json` |
| R06 writer mutex | **保留** | lock locator 改用 internal key，two external ids 不碰撞 |
| R06 publication guard | **保留** | snapshot attempt 短 guard + post-copy 短 guard；长 copy 不持 guard |
| journal/recovery | **保留** | minimal fields 不变；descriptor 提供 round-trip |
| complete-source validator | **扩展** | 已加入 identity descriptor + persisted revision 校验 |
| typed provenance/citation | **保留** | snapshot.provenance 与 meta 同源 |
| typed read errors | **保留** | consistency exhaustion → `SourceSnapshotConsistencyError`，不映射其它 I/O |
| tool/Host authorization | **不触碰** | diff 无 authorization 变更 |

**结论：所有安全机制保留，无回退。**

## 9. S3 Deferred Scope 审计

以下为明确 deferred scope，**不是 S2 缺口**：

- `read_runtime.py` 的 `revision_before` / `revision_after` before/after equality 比较：仍在代码中（lines 2198/2230/2503/2558/2594），属于 S3 迁移范围
- 独立 source meta cache（`_CachedSourceDocumentMeta`）与 processor cache（`_CachedProcessor`）：仍存在
- `_resolve_source_kind` filing-first probing：仍存在
- citation 仍独立调用 `get_source_document_provenance`
- `ProcessorLRUCache.put` / `evict` / `clear` 尚未返回 displaced values
- `DefaultFinsRuntime` / `_FinsReadProcessTarget` 尚未接通 close/resource cleanup
- read_runtime.py 的两个 unused imports（`QueryDiagnosis`、`SEARCH_MODE_AUTO`）：S3 删除
- Issue 142/151/175/177/178：未触碰
- R08—R12：未触碰
- 统一 tool authorization：未创建

**结论：S2 scope 边界清晰，无 scope creep。**

## 10. README 审查

### 10.1 `dayu/fins/README.md`

- Line 99：正确描述 persisted revision 的 opaque token contract，明确指出 producer 不能传入、non-source batch 不改变、`get_source_revision` 只机械读取
- Line 101：正确描述 `read_source_snapshot` 的 light/full snapshot contract、有界重取、typed consistency error、静态 corruption 保持原分类、close 幂等
- Line 103：**明确声明** read runtime 尚未消费 snapshot（"本节只承诺 storage revision/snapshot contract，不承诺 read cache/borrow 已消费该 contract"），防止误导
- Line 115：正确描述 opaque identity mapping 与 filename/path 规则分离
- Line 149/492/747：正确描述 read runtime 当前状态（仍保留 before/after revision、独立 cache、未持有 snapshot）
- 旧 SHA/hash/field-hash revision 描述已删除

### 10.2 `tests/README.md`

- Line 186（`tests/fins/` section）：正确描述 opaque mapping round-trip、descriptor fail-closed、persisted revision、snapshot 同版一致性、A/B/transient/sustained/corruption 分类、exception graph path-free、resource cleanup
- Line 130（`digest` section）：此处的 `sha256:<hex>` 是 `dayu.runtime` 层中立 UTF-8 文本 digest 工具的描述，与 source revision 完全无关。属于 `tests/runtime/` 节的内容，不是误报。

**结论：README 准确反映 S2 current contract，未提前宣称 S3 完成。**

## 11. 测试 Owner-Level 验证

### 11.1 测试覆盖矩阵

| 测试类别 | 文件 | 是否 owner-level |
|---|---|---|
| revision persist/change/rollback/preserve | `test_fins_storage_provider.py` | ✅ 断言 storage owner contract，不测试 token grammar |
| snapshot descriptor/meta/provenance/files/primary 同版 | `test_fins_storage_provider.py` | ✅ 断言完整的 typed snapshot 字段集合 |
| snapshot not found after delete/reset | `test_fins_storage_provider.py` | ✅ 断言 `FileNotFoundError` + token 不存在 |
| explicit source kind coexistence | `test_fins_storage_provider.py` | ✅ 断言 0/1/2 resolution |
| opaque token model boundary | `test_fins_storage_provider.py` | ✅ 断言非空 accept、空 reject，不断言格式 |
| A/B publication no mixing | `test_fins_storage_atomicity.py` | ✅ 真实 filesystem + batch commit |
| transient change recovery | `test_fins_storage_atomicity.py` | ✅ 不断言 attempt 次数 |
| sustained change typed failure | `test_fins_storage_atomicity.py` | ✅ 断言 `SourceSnapshotConsistencyError` + resource cleanup |
| symlink/meta mismatch rejection | `test_fins_storage_atomicity.py` | ✅ fail-closed 且非 `source_changed` |
| silent inode/content/fstat mutation | `test_fins_storage_atomicity.py` | ✅ corruption 分类保留 |
| exception graph primary preservation (acquire/release/marker/cleanup) | `test_fins_storage_atomicity.py` | ✅ 5 个测试覆盖全部双失败路径 + path-free 验证 |
| close failure → retry → idempotent | `test_fins_storage_atomicity.py` | ✅ 并发 retry 只完成一次删除 |
| preprocess snapshot lifecycle | `test_fins_ingestion_runtime.py` | ✅ 断言 revision 一致性 + token 不进 processed_meta |
| SEC fiscal single snapshot | `test_sec_pipeline_download.py` | ✅ 断言 single snapshot lifecycle |
| active 6-K single snapshot | `test_sec_pipeline_download.py` | ✅ 断言 single snapshot lifecycle |

### 11.2 测试质量

- 所有测试通过真实 filesystem + 真实 storage repositories，未用 fake `Source` 固化 storage policy
- Corruption/security 测试通过 monkeypatch 只做调度协调，不复制 production 算法
- 异常图验证使用递推 `__cause__`/`__context__`/`__notes__` 扫描，不依赖异常字符串匹配
- `_assert_exception_graph_path_free` 统一验证 forbidden locators（workspace root、private key、temp path）

**结论：测试为 owner-level，断言 contract 行为而非实现细节。**

## 12. Material Findings

### 12.1 R07-S2-DS-F01: Consumer close() exception masking（Medium）

**严重度**: Medium（batch safety 保留，仅错误诊断退化）

**位置**:
- `dayu/fins/ingestion_runtime.py:_preprocess_one_document` (line ~4195)
- `dayu/fins/pipelines/sec_fiscal_fields.py:_extract_fiscal_from_snapshot` (line ~296)
- `dayu/fins/pipelines/sec_6k_primary_document_repair.py:_reconcile_active_6k_primary_document` (line ~137)

**证据**: 三个 consumer 都使用 `finally: snapshot.close()` 模式：
```python
# ingestion_runtime.py
try:
    snapshot = self.source_repository.read_source_snapshot(...)
    try:
        source_meta = dict(snapshot.source_meta)
        # ... processor work (can raise ValueError, RuntimeError, OSError, ...)
    finally:
        snapshot.close()  # <-- if this raises, it masks the processor error
    commit_started = True
    ...
```

当 inner try block 抛出一个业务异常（如 processor failure），且 `snapshot.close()` 也失败（如 rmtree `PermissionError`）时，Python 的异常链接规则会让 close 异常成为主异常，原始业务异常退化为 `__context__`。大多数错误报告/日志只展示最外层异常，导致根因被隐藏。

**根因 owner**: Consumer 层的异常处理模式。Storage 层的 `_cleanup_snapshot_attempt` 已正确实现 primary-preservation，但 consumer 层未遵循同一模式。

**影响分析**:
- Batch safety 保留：`commit_started` 仍为 False，rollback 仍执行
- 错误诊断退化：processor failure 根因被 close failure 掩盖
- close() 实际失败概率极低（rmtree 在正常系统上几乎不会失败），但不可忽略

**可执行最小修复**:
在 consumer 的 finally 块中将 `snapshot.close()` 替换为 active-exception-aware 版本：
```python
finally:
    try:
        snapshot.close()
    except BaseException:
        # 若有活跃异常，close 失败只追加诊断；否则正常传播
        exc = sys.exc_info()[1]
        if exc is not None:
            _append_secondary_error_note(
                exc,
                sys.exc_info()[1],  # 实际应该是 close error
                action="preprocess snapshot close failed",
            )
        else:
            raise
```

或提取为 storage 提供的公共 helper，避免 consumer 重复实现 primary-preservation 逻辑。

**推荐**: 在当前 S2 gate 修复（三个文件，改动范围小），或在 S3 read runtime migration 中一并处理（此时 consumer 不再直接调用 close，而是由 cache/borrow 管理生命周期）。

## 13. Observations（无需修复，仅记录）

### 13.1 R07-S2-DS-O01: `uuid.uuid4().hex` as revision token

`_prepare_complete_source_meta` 使用 `uuid.uuid4().hex`（32 字符小写 hex）生成 revision token。该算法：
- 满足 plan "非空字符串 opaque equality" contract
- 确定性、namespace-separated（但 namespace 不在 token 内——由 storage locator 保证）
- Plan §12 明确保留未来调整 private key/revision 算法的权利（"只要 descriptor round-trip/opaque equality contract 不变，可在 fresh schema future work 调整"）
- 当前实现不把 grammar 承诺给 consumer/README/test

### 13.2 R07-S2-DS-O02: Light snapshot identity validation chain

Light snapshot（`materialize_files=False`）不调用 `_parse_snapshot_files`（不打开业务文件），但仍通过以下链路验证 identity：
1. `_resolve_snapshot_source_kind_unguarded` → `_source_meta_path_for_read` → `_identity_directory_for_read`（验证 document descriptor）
2. `_get_persisted_source_meta_unguarded`（读取并验证 meta）
3. `_source_revision_from_meta`（验证 token）
4. `SourceDocumentProvenance.from_meta`（验证 provenance）
5. `_build_published_marker`（读取 ticker + document descriptor bytes）

文档 identity descriptor 在 meta path 查找时已验证，ticker identity descriptor 在 marker 构造时已验证。验证链完整。

### 13.3 R07-S2-DS-O03: `_STABLE_READ_ATTEMPT_LIMIT` properly private

- 常量名以 `_` 开头，定义在私有模块 `_fs_source_snapshot.py`
- 未在 `__all__`、public protocol、README、tool schema 或 LLM-facing text 中暴露
- 测试不参数化或不断言 attempt 次数
- `SourceSnapshotConsistencyError` 的 message 不包含 attempt 数量

### 13.4 R07-S2-DS-O04: `_SnapshotFileSource` materialize() ignores suffix

`_SnapshotFileSource.materialize(suffix=None)` 的实现是 `del suffix; return self.state.require_open_root() / self.descriptor.name`。snapshot 文件已按业务文件名落盘在临时树中，不需要 suffix。但 `del suffix` 是显式信号，表明 suffix 被有意忽略而非遗忘。这是对 processor `materialize(suffix=...)` 接口的正确适配。

### 13.5 R07-S2-DS-O05: sec_fiscal_fields best-effort exception absorption

`_extract_fiscal_from_snapshot`（`sec_fiscal_fields.py:280`）在 snapshot read 失败时 catch `Exception` 并返回 `(None, None)`。这是 download path 的既有 best-effort 语义（fiscal fields 对下载成功率不是必需的）。该行为未被 R07 改变。符合 plan "不改 fiscal 推断算法"。

## 14. 综合验证结果

### 14.1 独立验证（基于 implementation artifact 证据）

| 验证项 | 结果 | 备注 |
|---|---|---|
| 五文件累计 pytest | 399 passed, 3 warnings | 三条 warning 为既有 `edgar` deprecated import |
| Full pyright | 0 errors, 0 warnings, 0 informations | — |
| Scoped Ruff（S2 allowlist） | All checks passed | — |
| Full Ruff baseline | 152（F401=72, E402=66, F841=10, F541=3, F821=1） | 未扩散 |
| `git diff --check` | Pass | — |
| Changed production file coverage | 全部 ≥ 80%（82.51%–100%） | `_fs_source_snapshot.py` 为 89.89% |
| Plan SHA-256 | 匹配 `ade76918...` | — |

### 14.2 Source scans

| Scan | 结果 |
|---|---|
| `_normalize_ticker` / `_normalize_document_id` storage residual | 0 |
| `directory_name` / `lock_path.stem` / `child.name` 业务反推 residual | 0 |
| 旧 `.digest`（source revision 上下文） | 0 |
| `_build_source_revision` / `sha256:<64hex>` / hash builder residual | 0 |
| `revision_before` / `revision_after`（production） | 仅 read_runtime.py（S3 deferred） |
| `get_source_meta` / `get_source_document_provenance` / `get_source` (read_runtime.py) | 仍存在（S3 deferred） |
| `.materialize()` in pipelines/processors | 仅 processor 内允许；pipeline raw repository materialize 为 0 |
| `_resolve_source_kind` filing-first probe | 仍存在（S3 deferred） |
| AST path-join audit | 全部命中为 private key 操作、business payload serialization 或 error text |

### 14.3 LLM-facing scan

- tool schema/description/result/citation 不暴露 `revision`、`storage_key`、`internal_key`、`local://`、`repo_batches`、`repo_backups`、`batch_locks`、absolute temp path
- `ErrorCode.SOURCE_CHANGED_DURING_READ` 保留既有 code 值，message/hint 不暴露 token/key/path
- Read runtime 和 citation 在 S3 迁移前仍有独立 repository reads，但这些不进入 LLM context

## 15. Adversarial Failure Pass 总结

| 场景 | 测试 | 结果 |
|---|---|---|
| A/B publication 不混合文件 | `test_snapshot_concurrent_ab_publication_never_mixes_files` | ✅ |
| 短暂变化恢复 + discard attempt cleanup | `test_snapshot_transient_change_recovers_and_cleans_discarded_attempt` | ✅ |
| 持续变化 typed failure + 全部资源清理 | `test_snapshot_sustained_change_raises_typed_consistency_failure_and_cleans_resources` | ✅ |
| 静态 corruption 不伪装为 source_changed | `test_snapshot_fd_copy_silent_mutation_is_corruption_without_revision_change` | ✅ |
| symlink/meta mismatch fail-closed | `test_snapshot_rejects_symlink_containment_and_file_meta_mismatch` | ✅ |
| acquire primary + release secondary | `test_snapshot_acquire_primary_survives_guard_release_secondary_without_locator` | ✅ |
| release primary + FD close secondary | `test_snapshot_guard_release_primary_survives_fd_close_secondary_without_locator` | ✅ |
| marker primary + guard release secondary | `test_snapshot_marker_read_primary_survives_guard_release_secondary_without_locator` | ✅ |
| marker/copy primary + FD/temp cleanup secondary | `test_snapshot_marker_primary_survives_fd_and_temp_cleanup_failures` | ✅ |
| transient discard 双 cleanup failure | `test_snapshot_transient_discard_cleanup_preserves_first_failure_and_attempts_all` | ✅ |
| close failure → retry → idempotent | `test_snapshot_close_failure_retains_cleanup_root_for_concurrent_retry` | ✅ |
| initial fstat primary + unregistered stream close secondary | `test_snapshot_initial_fstat_primary_survives_stream_close_secondary` | ✅ |

全部 exception graph 验证均 path-free（无 workspace root、private key、temp path 泄露）。

## 16. Verdict

**Verdict: PASS WITH 1 MATERIAL FINDING, 0 BLOCKERS**

- **Material findings**: 1（R07-S2-DS-F01，Medium，consumer close exception masking）
- **Blockers**: 0
- **S1 既有 findings**: 全部保持关闭
- **CV-F01..03**: 全部保持关闭
- **Deferred scope**: S3 边界清晰，无 scope creep 或误报
- **Security**: 所有机制保留，无回退
- **README**: 准确反映 S2 current contract
- **测试**: owner-level，不断言实现细节

### 16.1 R07-S2-DS-F01 裁决建议

该 finding 为 Medium severity，不构成 blocker。建议两个处置选项：

1. **在 S2 gate 修复**（推荐）：三个 consumer 文件的改动范围小（每个文件 ~5 行），修复后回归测试快速。符合 storage 层已建立的 primary-preservation 模式一致性。
2. **推迟到 S3**：S3 将把 consumer 的 `snapshot.close()` 调用移到 cache/borrow 生命周期内，届时一并处理。风险是 S2 到 S3 之间若发生 close 失败，错误诊断会退化。

无论选择哪个选项，该 finding 不得未经修复进入 R07 accepted implementation commit。

### 16.2 下一 gate

完成 MiMo 路 review 后，等待 Controller adjudication。Controller 裁决 R07-S2-DS-F01 的处置选项，并决定是否需要 AgentCodex fix + 双路 re-review。

---

**审查完成时间**: 2026-07-16
**审查 Agent**: AgentDS
**目标**: Controller adjudication
