# WU-SEMANTIC-OWNERSHIP-01 / R07-S1 Code Review (AgentDS)

## Scope

- **Mode**: current changes (cumulative working tree review)
- **Branch**: `phaseflow/host-issues-control`
- **Base**: transition HEAD `386fef8d7a7ecbd977c455ca86bb8bab875d1a98`（`docs: enter R07 opaque identity implementation`）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r07-s1-code-review-ds.md`
- **Included scope**: 9 production files（plan §7.1 exact allowlist）+ 4 test files + 1 new file `_fs_identity.py`
- **Excluded scope**: plan/control/design/旧 review/README、S2/S3、R08+、deferred ISSUE、统一 authorization
- **Parallel review coverage**: 5 subagents covering (1) `_fs_identity.py`, (2) `_fs_storage_infra.py` path/lock/recovery, (3) `_fs_company_meta_core.py` + `_fs_maintenance_core.py`, (4) `_fs_source_document_core.py` + `_fs_processed_core.py` + `_fs_blob_core.py`, (5) 全量测试文件 coverage audit。主 reviewer 独立复核全部 evidence chain。
- **Reviewer**: AgentDS（第二路独立 adversarial review，补充 MiMo review）
- **Artifact only**: 仅写入本文；不修改 code/test/control/design/plan/其它 artifact

## Conclusion

**PASS-WITH-FINDINGS** — 8 个 finding，其中 3 个中 severity、5 个低 severity。descriptor 是唯一 round-trip truth 的架构正确；point/list/meta/manifest/registry/maintenance/recovery 全线完成 raw path inference 清零；`expected_storage_key` 所有 caller 绑定真实 locator；R06 四 phase/lock/primary-error/atomicity 语义保留；source/material/processed/rejected/blob meta/descriptor 双向 fail-closed 覆盖；Unicode/separator/drive/dot/dotdot opaque identity 全部 round-trip 通过 containment；`CompanyMetaInventoryEntry` breaking cutover 完整无兼容残留；S2/S3/R08+/deferred ISSUE/统一 authorization 零偷带。无 correctness blocker，3 个中 severity finding 均为边界条件下的局部防御不足；5 个低 severity finding 为测试覆盖缺口或契约精度问题。

---

## Findings

### R07-S1-DS-F01 — 未修复 — 中 — corrupt backup descriptor 污染 valid target 的 `_ticker_identity_from_candidate_key`

- **入口/函数**: `_FsStorageInfra._ticker_identity_from_candidate_key` → `scan_company_meta_inventory`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:2289-2315`
- **输入场景**: published target 目录存在且 descriptor 有效，但同一 private key 的 backup 目录（`<key>.bak.<txn>`）的 descriptor 损坏（如 JSON 为空对象 `{}`）。
- **实际分支**: 第 2289-2299 行收集 candidate_directories 包括 target 和 backup；第 2302-2309 行 set comprehension 对 ALL candidate 调 `_read_identity_descriptor`。backup descriptor 损坏时 `_read_identity_descriptor` 抛 `ValueError`，comprehension 内异常立即传播。
- **预期行为**: backup 损坏时不应阻止 valid target 的正常 inventory 投影。至少应区分"target 有效但 backup 损坏"与"target 和 backup 都不可用"。
- **实际行为**: backup descriptor 损坏导致整个 `_ticker_identity_from_candidate_key` 抛异常，被 `scan_company_meta_inventory:128` catch 后投影为 `ticker=None, status="invalid_meta"`。valid published target 在 inventory 中消失。
- **直接证据**:
  - 第 2289-2299 行：target 和 backup 都被加入 candidate_directories 且不做区分
  - 第 2302-2309 行：set comprehension 对所有 candidate 调用 `_read_identity_descriptor`，任一失败即全部失败
  - 第 128 行（company_meta_core）：`except (FileNotFoundError, ValueError, OSError)` catch 后统一产生 `invalid_meta`
  - 正常运维场景：commit_journal phase=`COMMITTED` 但 `cleanup batch` action 未执行（journal recovery 早于 backup cleanup），backup 仍存在但 descriptor 可能因磁盘错误损坏
- **影响**: company inventory 不完整；valid ticker 被隐藏为 corrupt；对依赖 inventory 的上游（如 `_build_company_alias_index`）产生连锁反应
- **建议改法和验证点**: 在 `_ticker_identity_from_candidate_key` 中区分 candidate 来源：target descriptor 读取失败才报 `FileNotFoundError`；backup descriptor 读取失败仅记录 warning 并排除该 backup candidate，不阻止 target 恢复。或至少先尝试 target-only descriptor 读取，失败时再 fallback 到 backup 交叉验证。
- **修复风险（低）**: 仅改变 candidate 收集/验证策略，不影响 descriptor 格式、key 派生或 storage contract
- **严重程度（中）**: 罕见但真实的运维场景（磁盘错误 vs 正常 published target）；有 workaround（手动删除损坏 backup）

### R07-S1-DS-F02 — 未修复 — 中 — `list_rejected_filing_artifacts` 从 per-artifact skip-warn 变为全量 fail-closed

- **入口/函数**: `_FsMaintenanceMixin.list_rejected_filing_artifacts`
- **文件(行号)**: `dayu/fins/storage/_fs_maintenance_core.py:387-410`
- **输入场景**: `.rejections/` 目录下有多个 rejected filing artifact，其中一个 descriptor 或 meta 损坏（如 descriptor 字段缺失、meta JSON 无法解析）
- **实际分支**: 第 399-408 行：先调 `_list_external_identities`（第 399-401 行），该函数在 corrupt descriptor 时 fail closed（`_fs_identity.py:305` 抛 `ValueError`）；然后在循环内对每个 identity 调 `_get_rejected_filing_artifact_unguarded`（第 402-408 行），其中 `from_meta_dict` 或 mismatch check 抛异常不被 catch
- **预期行为**: 与旧实现一致，跳过损坏条目并可选 log warning，继续列出其余 artifact
- **实际行为**: 一个损坏的 rejected artifact 阻止整个列表操作。`_list_external_identities` 的阶段即失败，或成功枚举后对第一个损坏 meta 的读取即失败
- **直接证据**:
  - 旧实现（已删除）：`try: result.append(...) except (FileNotFoundError, ValueError) as exc: Log.warn(...); continue`（每 artifact 独立 try/except）
  - 新实现：第 399-408 行无任何 per-artifact 异常处理
  - `_list_external_identities`（`_fs_identity.py:275-312`）：无 skip 选项，corrupt 即抛
- **影响**: rejected filing 列表功能脆弱；一个损坏条目可阻断所有 artifact 的读取；对依赖 `list_rejected_filing_artifacts` 的 ingestion status reporting 产生阻塞
- **建议改法和验证点**: 在 `list_rejected_filing_artifacts` 的循环中加入 per-artifact try/except（至少 catch `ValueError, FileNotFoundError`），恢复 skip-warn 语义；或为 `_list_external_identities` 增加 `skip_corrupt: bool = False` 参数
- **修复风险（低）**: 仅恢复循环内异常处理，不改 descriptor/meta contract
- **严重程度（中）**: 生产路径可用性退化；修复简单

### R07-S1-DS-F03 — 未修复 — 中 — `upsert_processed_document` 和 `delete_processed_document` 存在性检查从 directory 改为 meta，可能导致静默覆盖或 orphan 状态

- **入口/函数**: `_FsProcessedMixin.upsert_processed_document` / `delete_processed_document`
- **文件(行号)**: `dayu/fins/storage/_fs_processed_core.py:436-438`（upsert）、`dayu/fins/storage/_fs_processed_core.py:127-129`（delete）
- **输入场景**:
  - **upsert create**: processed directory 存在（含之前写入的文件）但 `tool_snapshot_meta.json` 被手动删除或写入失败未完成
  - **delete**: processed directory 存在但 meta 已被手动删除
- **实际分支**:
  - upsert: 第 436 行 `exists = meta_path.exists()` — meta 不存在 → `exists = False` → `is_create and exists` 为 False → 执行 `mkdir(parents=True, exist_ok=True)`（目录已存在无操作）→ 覆盖写入新 meta 和文件。旧文件静默残留
  - delete: 第 129 行 `if not meta_path.exists(): raise FileNotFoundError(...)` — 目录存在但 meta 不存在 → 抛异常，不删目录，不更新 manifest
- **预期行为**: 存在性应以 directory 完整状态（至少 meta 存在）为准，或对部分状态提供明确诊断
- **实际行为**: upsert create 在旧文件残留下静默覆盖（无 FileExistsError 保护）；delete 留下 orphan directory + manifest 条目不一致
- **直接证据**:
  - 第 436 行：`exists = meta_path.exists()` 替代了旧实现的 `processed_dir.exists()`
  - 第 129 行：delete 仅在 meta 不存在时抛 FileNotFoundError，不会继续删除 directory
  - 对比 source document upsert（`_fs_source_document_core.py:1407`）也使用 `meta_exists = meta_path.exists()`，一致性存在但风险相同
- **影响**: orphan 文件/目录累积；delete 失败后 manifest 与文件系统不一致；create 时旧文件可能被新 pipeline 错误消费
- **建议改法和验证点**: upsert is_create 时检查 directory 是否存在（而不仅是 meta）；或 is_create 时如果 directory 存在但 meta 不存在，先清 directory 或明确报错要求 manual cleanup；delete 时即使 meta 不存在也应删除 directory 和 manifest 条目（或至少提供 force 选项）
- **修复风险（中）**: 改变存在性判定可能影响所有现有的 create/update/delete 调用者
- **严重程度（中）**: 虽在正常操作中 unlikely（meta 由 atomic JSON write 产生），但 crash/disk-full 路径可能触发

### R07-S1-DS-F04 — 未修复 — 低 — `begin_batch` 异常处理器中 lock release 失败可掩盖 primary error

- **入口/函数**: `_FsStorageInfra.begin_batch`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:355-358`
- **输入场景**: copytree 或 descriptor 读取抛异常，随后 `_release_lock_token(lock_token)` 也抛异常（如 RuntimeFileLockError）
- **实际分支**: 第 357 行 `self._release_lock_token(lock_token)` 若抛异常，原始异常被设置为 `__context__`（Python 隐式 chaining），但 `raise` 在第 358 行不可达——lock release 异常成为 primary
- **预期行为**: primary error（copytree/descriptor 失败）应保持为 primary；lock release 失败作为 secondary note
- **实际行为**: copytree 失败原因被 lock release 异常替换，caller 看到 `RuntimeFileLockError` 而非真正的 root cause
- **直接证据**:
  - 第 355-358 行：flat `except Exception` 无 nested try/finally 保护
  - 对比 `_close_active_batch:1040-1053`：使用 `try/except Exception as release_error: if primary_error is None: raise; primary_error.add_note(...)` 正确保留 primary
- **影响**: 根因排查困难；lock release 错误（通常为次要）掩盖了真正的初始化失败原因
- **建议改法和验证点**: 将 `_release_lock_token` 调用放入 nested try/except，lock release 失败仅记录 note 到原始异常
- **修复风险（低）**: 仅改变异常处理顺序，不影响状态机
- **严重程度（低）**: 只影响错误诊断，不影响正确路径

### R07-S1-DS-F05 — 未修复 — 低 — `_get_source_meta_unguarded` 的 `ticker` 校验与 `_get_document_meta_unguarded` 不一致

- **入口/函数**: `_get_source_meta_unguarded` vs `_get_document_meta_unguarded`
- **文件(行号)**:
  - `dayu/fins/storage/_fs_source_document_core.py:593`（`_get_source_meta_unguarded`）
  - `dayu/fins/storage/_fs_source_document_core.py:523-524`（`_get_document_meta_unguarded`）
- **输入场景**: source document meta 中 `ticker` 键缺失（旧数据或 producer bug）
- **实际分支**:
  - `_get_document_meta_unguarded` 第 523-524 行：`meta_ticker = meta.get("ticker")` → `if meta_ticker is not None and meta_ticker != normalized_ticker` — 有 None guard，缺 ticker 不抛异常
  - `_get_source_meta_unguarded` 第 593 行：`meta.get("ticker") != external_ticker` — 无 None guard，`None != external_ticker` 为 True → 抛 ValueError
- **预期行为**: 两个 read path 对缺失 ticker 的处理应一致
- **实际行为**: source kind-specific `_get_source_meta_unguarded` 对缺失 ticker fail closed（拒绝所有不含 ticker 字段的 meta）；通用 `_get_document_meta_unguarded` 则宽容通过。同一 storage 的两个读路径行为分歧
- **直接证据**: 行号对比见上
- **影响**: 如果 producer 未在 meta 中写入 `ticker` 字段，`get_source_meta` 路径会失败而 `get_document_meta` 不会；可能影响 read runtime 中调用 `get_source_meta` 的路径
- **建议改法和验证点**: 统一两个路径的 ticker 校验策略：要么都加 None guard，要么都 fail closed。建议 fail closed（ticker 是必填字段）
- **修复风险（低）**: 仅修一个 `is not None` guard
- **严重程度（低）**: 在正常 producer 路径中 ticker 总是被写入（见 `_upsert_source_document:1428` 行 `merged_meta["ticker"] = ticker`），仅在 corrupt/legacy 数据时触发

### R07-S1-DS-F06 — 未修复 — 低 — `_ensure_identity_directory` 在并发创建时非真正幂等

- **入口/函数**: `_ensure_identity_directory`
- **文件(行号)**: `dayu/fins/storage/_fs_identity.py:155-162`
- **输入场景**: 两个线程/进程同时对同一 namespace/external_identity 调用 `_ensure_identity_directory`（如在 process-backed tool runtime 中）
- **实际分支**: 第 155 行检查通过 → 第 162 行 `directory.mkdir(parents=True)` 无 `exist_ok=True`。线程 A mkdir 成功 → 线程 B mkdir 抛 `FileExistsError`
- **预期行为**: 应幂等（docstring 第 128 行："创建或**幂等**验证 identity directory"）
- **实际行为**: 非幂等；失败线程收到裸 `FileExistsError`
- **直接证据**:
  - 第 128 行 docstring："创建或**幂等**验证"
  - 第 162 行：`directory.mkdir(parents=True)` 对比第 153 行 `root.mkdir(parents=True, exist_ok=True)`
- **影响**: 并发调用者看到非预期异常；不导致数据损坏（先成功的线程产生有效 directory+descriptor）
- **建议改法和验证点**: 为 `mkdir` 加 `exist_ok=True`，或 catch `FileExistsError` 后 re-read descriptor 并以一致时返回。注意：`exist_ok=True` 会接受指向外部目录的 symlink——需在 mkdir 后再次 `is_symlink` 检查
- **修复风险（低）**: 仅改变并发语义；对单线程调用者无影响
- **严重程度（低）**: 当前所有 production caller 都在 writer/publication lock 保护下调用，实际不会触发并发 race

### R07-S1-DS-F07 — 未修复 — 低 — `_identity_directory_for_read` 在目录不存在时返回未验证路径

- **入口/函数**: `_identity_directory_for_read`
- **文件(行号)**: `dayu/fins/storage/_fs_identity.py:266-272`
- **输入场景**: identity directory 尚不存在（如读取不存在的 document_id 前）。函数返回确定性路径。在返回后、caller 使用前，攻击者在文件系统上创建同名 symlink
- **实际分支**: 第 266 行条件为 False → 跳过 descriptor 校验 → 第 272 行返回未验证路径。caller（如 `_get_source_meta_unguarded:989`）随后检查 `meta_path.exists()`——但此时路径可能已被替换为 symlink
- **预期行为**: 路径在返回时至少应标记为"未验证"，或 caller 在首次使用前做最小验证
- **实际行为**: 未验证路径被 caller 直接使用；caller 的后续 `exists()`/`is_file()` 调用在 symlink 替换后返回误导结果
- **直接证据**:
  - 第 266 行：`if directory.exists() or directory.is_symlink():` — 仅在目录存在时验证
  - 第 272 行：直接返回未验证路径
  - caller 示例：`_fs_source_document_core.py:989` 使用返回路径后不做额外 toctou 保护
- **影响**: 需攻击者对 storage root 有写权限；有该权限时可做更破坏性操作，但此路径是 subtle 攻击面
- **建议改法和验证点**: 可记录为已知的 filesystem TOCTOU 限制（storage root 写权限等同于完全信任）；或在 docstring 注明"返回的路径在目录不存在时未经 descriptor 验证，caller 应自行防护"
- **修复风险（低）**: doc-only 修复即可
- **严重程度（低）**: 需本地文件系统写权限的攻击前提

### R07-S1-DS-F08 — 未修复 — 低 — SEC test fixture 固化 `document_id.removeprefix("fil_")` 模式

- **入口/函数**: `_seed_complete_sec_source` test helper
- **文件(行号)**: `tests/fins/test_sec_pipeline_download.py:1071`
- **输入场景**: 测试 fixture 构造 document 时使用 `internal_document_id=document_id.removeprefix("fil_")`
- **实际分支**: fixture 假设 `internal_document_id` 可从 `document_id` 通过字符串操作派生——这与 opaque identity 的 exact round-trip contract 不一致
- **预期行为**: `internal_document_id` 是独立业务值，不应从 external identity 派生
- **实际行为**: 测试固化了一个可能在新 contract 下不合法的行为模式；如果未来 producer 改变 internal_document_id 语义，这些测试不会检测到
- **直接证据**: 第 1071 行 `internal_document_id=document_id.removeprefix("fil_")`
- **影响**: 测试契约不精确；不对当前 S1 正确性产生直接影响
- **建议改法和验证点**: 为 internal_document_id 传入显式值而非从 document_id 派生
- **修复风险（低）**: 仅测试辅助函数改动
- **严重程度（低）**: test-fixture 固化，不影响 production 正确性

---

## 交叉验证：用户指定重点审查维度

### 1. descriptor 是否为唯一 round-trip truth ✓

**确认**：所有 point lookup（`_identity_directory_for_read`）、enumeration（`_list_external_identities`）、manifest（`_read_manifest` 外部 ticker 校验）、meta（双向 document_id/ticker 校验）、company inventory（`_ticker_identity_from_candidate_key` 读 target/backup descriptor）、maintenance cleanup（`_read_identity_descriptor` 恢复 external ID 后再执行 `fil_` 业务判断）、recovery（backup/target/staging descriptor 交叉验证）全部通过 descriptor 恢复 external identity。零 raw `child.name` 反推。

**唯一例外**（非 S1 scope）：`get_source_revision` 仍使用 `_build_source_revision(meta)` 的 field-hash 路径（S2 任务）。

### 2. point/list/meta/manifest/registry/maintenance/recovery 无 raw path inference ✓

**确认**：
- `_list_document_ids_unguarded`：改用 `_list_external_identities(root, namespace)`（descriptor 枚举）
- `_list_documents_unguarded`：增加 manifest ↔ descriptor 双向校验
- `list_rejected_filing_artifacts`：改用 `_list_external_identities`
- `scan_company_meta_inventory`：改用 `_published_ticker_candidate_keys` + `_ticker_identity_from_candidate_key`
- `cleanup_stale_filing_documents`：改用 `_read_identity_descriptor` + descriptor-verified path
- recovery `_recover_single_batch_dir`：通过 `_read_identity_descriptor(expected_storage_key=...)` 交叉验证
- All manifest read/write：外部 ticker/文档 ID exact match

### 3. expected_storage_key 所有 caller 绑定真实 target/backup locator ✓

**确认**：
- `_recover_single_batch_dir:1444-1445`：backup 用 `expected_storage_key=ticker_key`，target/staging 用 None
- `_recover_orphan_backups:1550-1554`：backup 用 `expected_storage_key=ticker_key`
- `_ticker_identity_from_candidate_key:2303-2306`：所有 candidate 用 `expected_storage_key=normalized_key`
- 链：`_parse_backup_directory_name` → key → `_read_identity_descriptor(expected_storage_key=key)` → 内部验证 `storage_key == _derive_storage_key(namespace, identity)`

### 4. R06 target/staging/backup/lock/recovery 四 phase ✓

**确认**：锁顺序保留（`begin_batch`：先 `_acquire_ticker_lock` 再 journal 再 copytree）；publication guard 语义保留（commit 期间获 guard，swap 后释放）；primary error 保留（`_close_active_batch` 的 nested try/except）；old/new atomicity 保留（`_replace_directory` 用 `os.replace`）。唯一退化见 F04。

### 5. source/material/processed/rejected/blob meta/descriptor 双向 fail-closed ✓

**确认**：所有 read path 在读取 meta 后校验 `document_id`/`ticker`/`source_kind` 字段与 descriptor 一致；write path 通过 `_ensure_identity_directory` 在首个 payload 前创建 descriptor；manifest 读取校验 `manifest["ticker"]` 与请求一致；`_list_documents_unguarded` 增加 manifest ↔ descriptor 双向校验。唯一问题见 F03（processed exist 检查）。

### 6. Unicode/separator/drive/dot/dotdot opaque identity 下 containment ✓

**确认**：identity channel 接受所有字符（`_require_external_identity` 只校验非空 UTF-8）；filename/entry/URI channel 继续通过 `_normalize_path_component` 拒绝 separator/dot/dotdot/drive/absolute；containment 保留（`_require_contained_path`、`_is_contained_recovery_path`）；symlink rejection 保留（descriptor、root、ticker 子目录、copy tree 全链路）。测试覆盖见节点 1/2/9。

### 7. company alias 与 storage identity 分权 ✓

**确认**：`_canonicalize_ticker_alias`（`_fs_storage_utils.py:56-73`）只用于 `_resolve_existing_ticker_by_company_alias`（company alias 查询）；storage 层的 ticker identity 通过 `_require_external_identity` 保持 exact 值（不 strip/不大小写折叠）。

### 8. CompanyMetaInventoryEntry breaking cutover 无兼容 ✓

**确认**：`directory_name: str` → `ticker: Optional[str]`，所有构造点（7 处）全量迁移为新字段名。无 compat alias/property/re-export。

### 9. 115-hit inventory 与 _remove_manifest_items ✓

**确认**：旧 115 hit 收敛至 8 hit（3 个 company alias pattern 重名 + 5 个 private backup parser）。`_remove_manifest_items` 改用 `_require_external_identity` 校验并 exact match manifest 中的 `document_id`（manifest 中存储 external ID）。`cleanup_stale_filing_documents` 先 descriptor 恢复 external ID 再执行 `fil_` 检查。

### 10. 是否偷带 S2/S3、R08+、Issue 或统一 authorization ✓

**确认**：零偷带。
- S2 revision token/snapshot API：未实施；`get_source_revision` 仍使用旧 field-hash 路径（S2 任务）
- S3 cache/read/citation：未触碰 read_runtime.py、cache.py 等
- R08—R12：未实施
- Issue 142/151/175/177/178：未实施
- 统一 authorization：未引入
- `_fs_source_snapshot.py`：未创建（S2 任务）

---

## Open Questions

1. **`_require_external_identity` 允许 `\x00` null byte** — 当前 identity validation 只做非空+UTF-8 检查。包含 null byte 的 identity 通过 `_derive_storage_key` 的 hash 处理没有问题（SHA-256 原生支持），但在下游日志/异常/JSON/UI 展示中可能被截断或产生意外行为。plan 中未明确 null byte 的处置。是否需要增加 "no control characters" 校验？
2. **超长 identity** — 文件系统路径组件长度限制（典型 255 字节）对 private key（67 字符 `id-` + 64 hex）无影响，但 external identity 自身无长度限制。超长 identity 在异常消息/JSON 序列化中可能产生问题。是否需要加长度上限？
3. **`_ensure_identity_directory` 的 `exist_ok` 缺失** — 见 F06。是否接受当前"caller 需序列化"的隐式契约，还是应改为真正的幂等实现？

---

## Residual Risk

| 风险 | 覆盖状态 | 残值 |
|---|---|---|
| `\x00` null byte identity 边界 | 零测试覆盖 | 低 — plan 为 S1 scope，identity validation 的精确边界可在后续 refine |
| `id-` 前缀的 universal non-leak 模式扫描 | 仅测试特定 private key 值，无非 regex 模式扫描 | 低 — 异常消息/输出路径已黑盒验证，但未来新增输出路径可能漏网 |
| Backup descriptor vs target descriptor 交叉验证 | 测试缺失 | 低 — recovery 路径已有 descriptor 校验，但 conflict 场景（两个 descriptor 声称不同 identity）未测试 |
| Opaque identity 在通用 CRUD/read runtime 路径 | 仅专项测试覆盖；~30 个通用测试只用 ASCII identity | 低 — 通用 fixture 的 ASCII identity 仍走同一 descriptor 路径，不会回归 |
| TOCTOU 在 identity directory 创建/读取路径 | 未测试 | 低 — 需本地文件系统写权限的前提，且 writer lock 序列化了大部分路径 |
| 测试文件 4 个 full-file 的 336 passed | 已验证（Codex 报告 + Controller 独立验证） | 无 — 336 passed |

---

## Controller adjudication

待 Controller 对以上 8 个 finding 逐项裁决（accepted/rejected-with-reason/deferred-with-owner/needs-more-evidence），然后与 MiMo review findings 合并，交由 AgentCodex 在同一 working tree 修复 accepted findings。
