# WU-SEMANTIC-OWNERSHIP-01 R06-S2 累计 Code Review — 第二路 (DS)

## 1. 审查身份与范围

- **审查者**: AgentDS（第二路 cumulative reviewer）
- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01` / R06 / S2 cumulative code review
- **审查基线**: `d048adf7ec1135aaf575384432ebf1137f8a34f2` → 当前完整未暂存 working tree
- **累计 scope**: R06-S1 + R06-S2（同一 breaking cutover 的累计 checkpoint）
- **只允许写入本 artifact**: `docs/reviews/wu-semantic-ownership-01-r06-s2-code-review-ds.md`
- **不修改 product/test/control/design/他人 artifact**

### 1.1 裁决优先级（已完整读取并应用）

1. `AGENTS.md`
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
3. `docs/fins/design.md`
4. `docs/host/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan.md`（R06 plan）
5. `docs/reviews/wu-semantic-ownership-01-r06-s2-implementation-codex.md`（S2 implementation codex）
6. `docs/reviews/wu-semantic-ownership-01-r06-s2-controller-validation.md`（S2 controller validation）
7. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-mimo.md`（S1 MiMo re-review: PASS）
8. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-ds.md`（S1 DS re-review: PASS）
9. `docs/reviews/wu-semantic-ownership-01-r06-s1-code-rereview-controller-adjudication.md`（S1 controller adjudication: PASS）

### 1.2 审查方法

- 完整走读 15 个累计 S1 与 7 个 S2 authored production 文件的当前 working tree 状态
- 沿真实调用链逐行走读：blob write → resolve_active_batch → staging write；final source mutation → _prepare_complete_source_meta → manifest update；commit_batch → validator → publication guard → physical swap → journal
- 四个并行 subagent 专项深挖：validator/manifest projection、blob-first/batch authority、commit/recovery/rollback error paths、loose parsing/shim/boundary scan
- 主 reviewer 独立复核全部 subagent 结论、去重、沿代码路径验证证据链
- 独立运行 focused tests、scoped pyright、全量 pyright 分类审计、ambient authority/staging ack/loose parsing/compat 扫描
- 对 S1 已 accept 的全部 owner contract（opaque BatchToken、registry authority、lock order、read graph、journal、recovery、VF-01..04、containment）做回归验证，确保 S2 未回退

## 2. Verdict

**PASS — 1 material finding (Low), 0 blockers**

S2 cumulative tree 正确实现了 accepted R06 plan §5 的全部 complete-source single-publication contract：

- blob-first staging：`SourceHandle` blob write 不再需要预先 source meta
- final source mutation：唯一 owner boundary 强制 typed provenance 与 `ingest_complete=True`；删除 first-file primary fallback
- storage-owned commit validator：完整遍历 staged ticker tree，双向校验 source↔manifest、meta identity/provenance/completion、files non-empty/unique/physical/URI/size/sha256 双向一致、primary exact match，全部 fail-closed
- validator 在 publication guard 前运行，publication guard 只覆盖 physical swap 短窗
- S1 全部 owner contract（opaque token、registry authority、writer/publication lock 分离、read graph、journal、recovery、VF-01..04、containment）未被 S2 回退或放宽
- 累计 232 tests、scoped pyright 0、ambient authority 0、staging ack 0、loose parsing 0、compat 0

唯一 material finding 是 `_resolve_primary_uri` 中的 first-file fallback（Low severity，不影响存储正确性），其余均为 non-blocking observation。

## 3. S1 Accepted Findings Closure 回归

逐项验证 S1 全部 closed finding 未被 S2 回退：

| S1 Finding | S2 回归状态 | 直接证据 |
| --- | --- | --- |
| R06-S1-CR-F01 (maintenance unguarded read graph) | **CLOSED 保持** | `_fs_maintenance_core.py:401-411` outer guard + unguarded helper 未变更 |
| R06-S1-CR-F02 (processed meta 唯一读取 contract) | **CLOSED 保持** | `_fs_processed_core.py:184/227-230` 仍只读 `tool_snapshot_meta.json` |
| R06-S1-CR-F03 (reprocess marker 统一 None) | **CLOSED 保持** | `_fs_processed_core.py:234/260/289` 返回语义未变更 |
| S1 opaque BatchToken | **保持** | `document_models.py:414-424` 仍只含 `transaction_id` + `ticker` |
| S1 registry-only authority | **保持** | `_fs_storage_infra.py:919-959` `_resolve_active_batch` 未添加 ambient 检查 |
| S1 writer/publication lock 分离 | **保持** | 锁路径、锁序、短窗范围未变更 |
| S1 read graph (outer guard + private unguarded) | **保持** | AST public self-call scan: `[]`；全部 public read 保持 outer + private 模式 |
| S1 LocalFileSource delayed opener | **保持** | `_fs_storage_infra.py:96-120` `_PublicationGuardedBinaryOpener.__call__` 未变更 |
| S1 minimal journal | **保持** | `_JOURNAL_FIELDS` 仍为 `{transaction_id, ticker, phase}` |
| S1 VF-01..04 recovery/error precedence | **保持** | 全部对应代码路径经逐行走读确认未变更 |
| S1 containment/symlink | **保持** | `_normalize_path_component`、`_require_contained_path`、`_is_contained_recovery_path` 未变更 |

**结论**: S2 未回退或放宽任何 S1 accepted finding。

## 4. Findings

### R06-S2-CR-F01 — `_resolve_primary_uri` 的 first-file fallback 是未记录的静默猜测（低）

- **入口/函数**: `_resolve_primary_uri`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_utils.py:417`
- **输入场景**: 调用方提供了 `primary_name`（非空字符串），但该名称在 `file_payloads` 列表中没有任何条目的 `name` 匹配。
- **实际分支**: for 循环（line 412-416）遍历全部条目但无匹配 → 落入 line 417: `return str(file_payloads[0].get("uri"))`。
- **预期行为**: 函数应返回 `None`（表示未找到匹配 URI），或在调用方明确要求精确匹配时 fail closed。`_resolve_primary_uri` 的 docstring 只说 "若未找到返回 `None`"，但 line 417 永远会返回第一个文件的 URI，所以 docstring 描述与实现不一致。
- **实际行为**: 静默返回第一个文件的 URI，不报告未匹配。调用方收到一个名字不匹配但碰巧来自第一个文件的 URI。
- **直接证据**:
  - line 396: docstring 声明 `Returns: 主文件 URI；若未找到返回 None`。
  - line 412-416: for 循环仅当 `primary_name` 非空时按精确名称匹配。
  - line 417: `return str(file_payloads[0].get("uri"))` — 当 `primary_name` 非空但未匹配时，不返回 `None`，而返回第一条目的 URI。
  - line 417: 当 `primary_name` 为 `None` 时也落入同一条（line 412 的 `if primary_name:` 为 False 时跳过循环），此时 first-file fallback 是唯一路径，函数不可能返回 `None`。
- **影响**: 低。当前所有调用方已通过 `selected_primary_document is not None` 守卫后再调用 `_resolve_primary_uri`（`_fs_source_document_core.py:1339-1341` 和 `1416-1418`），且 `selected_primary_document` 值由 `_select_primary_document`（line 1714-1736 of `_fs_storage_infra.py`）产生——该函数只返回非空字符串。因此当前生产路径中，`primary_name` 必定为非空字符串且来自已校验的 meta。
  - 存储正确性不受影响：commit validator（`_fs_storage_infra.py:644-649`）独立校验 `primary_document` 字段必须精确命中 `files` 列表；`DocumentHandle.primary_file_uri` 只是调用方便利字段，不是 authoritative truth。
  - 但 pattern 本身是 semantic ownership 问题：函数在没有匹配信息时不应该猜测。docstring 与实现不一致；未来如有调用方依赖 `DocumentHandle.primary_file_uri` 做业务判断（而非 meta 的 `primary_document` 字段），静默 fallback 会掩盖错误。
- **建议改法和验证点**:
  - 修复 owner（`dayu/fins/storage/_fs_storage_utils.py`）：line 417 改为 `return None`，与 docstring 一致。
  - 调用方（`_fs_source_document_core.py:1339-1343` 和 `1416-1418`）：当 `_resolve_primary_uri` 返回 `None` 时，保留当前行为（`DocumentHandle.primary_file_uri = None`）。这是向后兼容的——当前 `DocumentHandle.primary_file_uri: Optional[str]` 已经接受 `None`。
  - 验证点：添加 owner test 证明 `_resolve_primary_uri` 在 `primary_name` 存在但不匹配任何文件时返回 `None`；在 `primary_name=None` 时也返回 `None`。
- **修复风险（低）**: 修改仅影响 `DocumentHandle.primary_file_uri` 字段值（从错误 URI 变为 `None`），不影响存储 meta、manifest 或 commit validator。当前生产者不依赖该字段做 publish 决策。
- **严重程度（低）**: docstring 与实现不一致；first-file fallback 是 AGENTS.md 禁止的「下游消费者猜测语义」模式，但当前存储正确性不受影响。

## 5. S2 Complete-Source Contract 逐项验证

以下每项均经直接代码走读、subagent 深挖与独立复核确认。

### 5.1 Blob-first staging — `SourceHandle` 不要求预先 meta

**PASS**

- `_fs_blob_core.py:214-215`: `isinstance(handle, ProcessedHandle)` 守卫 — `_get_handle_meta_for_state` 仅对 `ProcessedHandle` 调用。`SourceHandle` 直接跳过 meta 读取，进入 key 构建与 FileStore put。
- `_fs_blob_core.py:180`: `store_file(self, handle, filename, data, *, batch, ...)` — 只有 `_resolve_active_batch` 是入口校验，不做 `SourceHandle` meta 存在性检查。
- Processed blob 仍要求 meta：`_fs_blob_core.py:214-215` 与 `repository_protocols.py:801` docstring 一致。

### 5.2 Final source mutation 强制 typed provenance 与 true completion

**PASS**

- `_prepare_complete_source_meta` (`_fs_source_document_core.py:1424-1456`)：
  - line 1447: `meta.get("ingest_complete", True)` → 默认 True 是安全默认值
  - line 1448-1449: 显式 non-True 值（`False`、`None`、非 bool）→ `ValueError("final source ingest_complete 必须为 true")`
  - line 1454: `normalized["ingest_complete"] = True` — storage owner 硬编码完成态
  - line 1455: `SourceDocumentProvenance.from_meta(normalized, source_kind)` — typed provenance 校验；未知 ingest_method/provider 由 Enum 构造抛出 `ValueError`
- 三个入口（`_upsert_source_document:1319`、`_toggle_source_deleted:1392`、`replace_source_meta:695`）均经此单一函数收敛。

### 5.3 删除 first-file primary fallback

**PASS**

- `_select_primary_document` (`_fs_storage_infra.py:1714-1736`): 只接受 `explicit_primary`（优先）和 `previous_primary`（fallback）。若两者均非有效字符串，返回 `None`。不存在 `files[0]` fallback。
- Commit validator (`_fs_storage_infra.py:644-649`): 独立校验 `primary_document` 为非空字符串且精确命中 `file_names`。无 first-file 兜底。
- `setdefault(primary/completion)` / `files[0]` primary 选择扫描：0 命中。

### 5.4 Commit validator 完整遍历与双向校验

**PASS**

- 遍历：`_validate_complete_source_tree` → `_validate_complete_source_kind_tree` — 对 `SourceKind.FILING` 与 `SourceKind.MATERIAL` 分别枚举 `source_root.iterdir()` 所有子目录（`_fs_storage_infra.py:453-454, 492`）。无 touched-set 或缓存。
- 双向 manifest：`source_ids - manifest_ids`（line 520-523: "source 缺少 manifest 项目"）与 `manifest_ids - source_ids`（line 525-528: "manifest 存在 dangling source"）。
- Manifest 读取：`_read_complete_source_manifest`（line 549-592）校验 manifest 为 regular file、ticker 一致、documents 为数组、每条 document_id 为 canonical identity 且不重复。
- 排除逻辑：line 497-506 以 `child.name` 精确字符串匹配排除 `_download_rejections.json` 和 `.rejections` 目录，仅对 `SourceKind.FILING`。材料树无此排除。
- Source-free transaction：line 476-477 `if not source_root.exists() and not source_root.is_symlink(): return` — 允许无该 kind source 的 transaction。

### 5.5 Meta 完整性

**PASS**

- `_validate_complete_source_directory`（line 594-650）：校验 meta_path 存在且为 regular file；ticker/document_id/source_kind 与目录一致；`SourceDocumentProvenance.from_meta` 校验 ingest_method/provider；`ingest_complete` 非真拒绝；files 与 primary 同源。
- 每个失败格均有独立中文错误消息；无 catch-all 或 silent pass。

### 5.6 Files 双向物理一致性

**PASS**

- `_validate_complete_source_files`（line 652-732）：
  - files 非空数组 → 逐条 name 规范化 + 唯一性 + 非 `meta.json`
  - 每项 physical path containment + non-symlink regular file（`_require_contained_regular_file`）
  - URI 精确等于 `local://{ticker}/{source_dir}/{document_id}/{name}`
  - 存在 size → 与 `st_size` 比较；存在 sha256 → 流式 SHA-256 比较
  - 反向：遍历 source_dir 所有 child（排除 `meta.json`），要求 non-symlink regular file → `physical_file_names == file_names`

### 5.7 Manifest projection 同源

**PASS**

- `FilingManifestItem.from_source_meta`（`document_models.py:920-961`）：从 `SourceDocumentProvenance.from_meta` 投影 ingest_method、source_provider、ingest_complete
- `MaterialManifestItem.from_source_meta`（`document_models.py:1001-1039`）：同上模式
- Validator（`_fs_storage_infra.py:538-547`）：对每个 source 调用 `from_source_meta(meta).to_dict()` 与 manifest item 做 `!=` 精确相等比较
- 所有 source mutation 入口（upsert、replace、toggle deleted）均使用 `from_source_meta` → `_upsert_filing_manifest` / `_upsert_material_manifest`
- 不存在裸 `FilingManifestItem(...)` 或 `MaterialManifestItem(...)` 构造

### 5.8 Commit 顺序与可见性

**PASS**

- `commit_batch`（`_fs_storage_infra.py:337-427`）:
  1. lifecycle → `commit_started`（line 338）
  2. `_validate_complete_source_tree` — 不持 publication guard（line 345）
  3. `_acquire_publication_guard` — validator 通过后才获取（line 346）
  4. target→backup → journal BACKED_UP_TARGET（line 349-351）
  5. staging→target → journal SWAPPED_TARGET（line 352-353）
  6. journal COMMITTED（line 354）
  7. publication guard release（line 361-380）
  8. cleanup + close_active_batch

### 5.9 长 validator/rename window readers

**PASS**

- Validator 在 publication guard 外运行 → 长校验不阻塞 published reader
- 两个 rename barrier（target→backup、staging→target）在 publication guard 内
- S1 reader tests（`test_concurrent_published_read_ignores_long_writer_staging_and_sees_old`、`test_concurrent_reader_blocks_at_each_publication_rename_barrier`）继续通过

### 5.10 Commit error/rollback/recovery

**PASS**

- Validator 失败：outer `except`（line 381-386）→ `_rollback_precommit_batch` → 清理 staging、保留 old target → `_close_active_batch` 消费 token → raise commit_error
- Physical swap 失败：inner `except`（line 355-360）→ `_rollback_precommit_batch` → 从 backup 恢复 old → `_close_active_batch`
- COMMITTED 后 publication release 失败（line 371-378）：`post_commit_error` 不调 rollback → durable tree 不回滚
- VF-03：`_close_active_batch`（line 981-999）registry 先 pop（line 982），再释放 writer lock；release failure 在 primary_error 存在时只 add_note
- VF-04：COMMITTED 后 post_commit_error 成为 terminal error，COMMITTED tree 不变
- Rollback：只清理 staging（line 913 `shutil.rmtree(state.staging_root_dir)`），不触碰 target/backup，不获取 publication guard
- Recovery：先全局 recovery lock → 读取 journal → 非阻塞 ticker lock → 按 phase 恢复 → 仅在 physical swap 短窗获取 publication guard → 释放 publication guard → cleanup → 释放 writer lock
- VF-01 保持：invalid journal/backup ticker → skip + continue；仅捕获 `ValueError`

### 5.11 Containment/symlink/atomic/security

**PASS**

- 路径组件：`_normalize_path_component`（`_fs_storage_utils.py:30-53`）拒绝 `.`、`..`、`/`、`\`、绝对路径、Windows drive letter
- Containment：`_require_contained_path`（`_fs_storage_infra.py:759-788`）resolve 后 `relative_to` 校验；`_is_contained_recovery_path`（`_fs_storage_infra.py:162-190`）额外逐级 symlink 检查
- Blob store：五层防线 — component normalize → handle dir containment → handle dir symlink → child path containment → FileStore key containment
- Validator：每个 staged file 和 meta 均经 `_require_contained_regular_file` 或 `_require_contained_path` + symlink 拒绝
- Atomic write：`_write_json` 先 temp → fsync → `os.replace` → fsync parent
- Symlink 拒绝：全部关键路径（staging root、source root、每个 child entry、meta.json、每个业务文件）均显式 `is_symlink()` 检查

### 5.12 无 S3/R07/Issue 175/177 越界

**PASS**

- 无 snapshot/revision/selector/retry/lease：全仓 S2 owner 无 R07 功能实现
- 无 process isolation/Docling/subprocess 变更：Issue 175 延迟
- 无 TruncationManager/input budget 变更：Issue 177 延迟
- 无 storage-state lifecycle：Issue 178 延迟
- 无统一 authorization framework
- Full pyright 108 errors：全部精确归属 S3 producer/callback/test propagation（63 缺 required batch、27 已删除 lifecycle、4 已删除 stage_source_document、12 callback/override 缺 batch、2 旧 token_id）；changed owner 命中 0

### 5.13 S2 删除 ack/incomplete contract 证据

**PASS**

- `stage_source_document`: storage 层 0 命中（已从 protocol、core、wrapper、tests 完全删除）
- `_STAGING_STABLE_META_FIELDS`: 0 命中
- Staging acknowledgement/stable re-entry: 0 命中
- `ingest_complete=false/False`: storage 层 0 命中（仅 validator 拒绝显式 false、_prepare_complete_source_meta 拒绝显式 false 和 owner tests 断言拒绝）
- Aggregate ack scan 35 命中：14 条 deferred S3 producer、15 条 deferred S3 tests、4 条 README 旧叙述、2 条 fail-closed owner tests

## 6. Observations

以下为非 material finding，记录为技术债，不阻塞 S2 gate。

### O-01 — `_resolve_primary_uri` first-file fallback（对应 CR-F01）

已在 §4 详述。docstring 声明 `Returns: None 若未找到`，但 line 417 永远返回第一个文件的 URI。

### O-02 — `ProcessedManifestItem` 缺少 `from_*_meta` 工厂

`_fs_processed_core.py:415` 以裸 `ProcessedManifestItem(...)` 内联构造，而非通过 `from_processed_meta` 工厂。`FilingManifestItem` 与 `MaterialManifestItem` 均有 `from_source_meta`。这是架构不一致，但当前无 correctness 影响：processed manifest 字段全部在构造点显式设置，且 processed 没有对应的 "typed provenance completion" 校验层。

### O-03 — S1 Observations 继续适用

以下 S1 MiMo observations 在 S2 cumulative tree 中继续适用，无变更：

- O-03: 测试访问 `_ActiveBatchState` 私有字段（failure injection 需要）
- O-04: 测试通过 `_ActiveBatchState` 物理路径注入 failure（crash-phase/recovery 需要）
- O-05: monkeypatch 私有方法注入 failure
- O-06: 0.25s poll 辅助断言
- O-07: owner/AST guard 测试与实现耦合（error message string assertions）
- O-08: `_select_primary_document` 的 `previous_primary: Any`
- O-09: 无测试验证 guard release 后续 reader 不被旧 guard 阻塞

### O-04 — Recovery 在 journal 读取与 ticker lock 获取之间的时间间隙

`_recover_single_batch_dir`（`_fs_storage_infra.py:1249`）在获取 ticker-specific writer lock（line 1285）之前读取 journal。全局 recovery lock（line 1017）提供 recovery↔recovery 隔离，非阻塞 ticker lock 保护活跃 transaction，但 journal 数据的验证发生在获取该 ticker 互斥锁之前。当前并发场景下通过 recovery lock + 非阻塞 ticker lock gate 安全，但值得在审计追踪中记录。

## 7. 验证证据

| 证据类型 | 结果 |
| --- | --- |
| 四个累计 S1/S2 test 文件完整运行 | `232 passed, 3 warnings in 9.56s` |
| 3 条 warning 来源 | 第三方 `edgar` deprecated imports，非本 gate 新增 |
| Scoped pyright (15 S1 + 7 S2 production + 4 tests) | `0 errors, 0 warnings, 0 informations` |
| Full pyright | `108 errors`（全部 S3，changed owner 0） |
| Full Ruff | `160 errors`（baseline 不变，changed owner 0） |
| Ambient authority scan (ContextVar/task/thread/auto_batch) | `0` 命中 |
| Staging ack scan (stage_source_document/STAGING_STABLE_META_FIELDS/ack) | `0` 命中（storage 层） |
| Loose parsing scan (hasattr/getattr) | `0` 命中 |
| Compat scan | `0` 命中 |
| Fallback primary scan (files[0]/setdefault primary) | `0` 命中 |
| Public core read self-call AST | `[]` |
| `git diff --check` | pass |
| Staged diff | 空 |
| S2 authored production files = 7 | `document_models.py`, `repository_protocols.py`, `_fs_storage_infra.py`, `_fs_blob_core.py`, `_fs_source_document_core.py`, `fs_document_blob_repository.py`, `fs_source_document_repository.py`（全在 allowlist） |
| Coverage (逐文件 ≥ 80%) | verified by Controller: 82.62%-100% 全部达标 |

## 8. S1 Contract 回归验证

经主 reviewer 独立走读 + subagent 专项复核确认：S2 未回退 S1 全部 accepted owner contract。见 §3 逐项回归表。

## 9. R06 Plan Conformance

| Plan Section | 要求 | S2 状态 |
| --- | --- | --- |
| §5.1 blob-first staging | blob 写不要求 meta ack；producer 直接构造 identity handle | ✓ |
| §5.2 commit 前 validator | meta/files/primary/provenance/manifest 全量 fail-closed | ✓ |
| §5.2 validator 遍历完整 tree | 无 touched-set；双向 source↔manifest | ✓ |
| §5.2 ingest_complete=false 拒绝 | 显式 false 在 mutation boundary + validator 双重拒绝 | ✓ |
| §5.2 first-file primary fallback 删除 | 已删除 | ✓ |
| §5.3 唯一可见点 | validator 通过前 target 不变；commit 是唯一新可见点 | ✓ |
| §7.2 S2 allowlist | 7 production + 4 tests | 实际 authored = 7+4 ✓ |
| §7.2 focused tests | source/blob/incomplete/staging/commit/rollback/provenance/primary/manifest | 88 passed ✓ |
| §8.3 scans | ack 0（storage）、ambient 0、lifecycle 183、mutation 170 | 全部符合归属 ✓ |
| §10 baseline | full pyright 108 S3、full Ruff 160 不变 | 符合 ✓ |
| §11 stop conditions | 无越界 | 符合 ✓ |
| CR-F01..03 closure | S2 未回退 | 保持 CLOSED ✓ |

## 10. Open Questions

无。

## 11. Residual Risk

1. **S3 producer propagation**: full pyright 108 与 aggregate ack scan 35 是 S3 唯一已知传播风险。S3 cumulative tree 必须清零且 ack scan 在 producer 层归零。

2. **R07 snapshot/revision**: 8 个 production 文件/9 个 `.materialize()` 调用点在拿到裸 `Path` 后的延迟/多次读取没有 snapshot consistency（S1 residual，未变更）。R06 publication guard 只保证单次 read/open 的 old/new 完整性。

3. **README 旧叙述**: `dayu/fins/README.md` 和 `tests/README.md` 的旧 acknowledgement 描述保留到 S3 final cumulative tree 同步更新。

4. **O-04 recovery 时间间隙**: journal 在 ticker lock 前读取。当前通过全局 recovery lock + 非阻塞 ticker lock 安全，但长期应收敛为先 lock 后 verify 模式。

5. **CR-F01 _resolve_primary_uri**: first-file fallback 当前不影响存储正确性（validator 独立校验），但 pattern 是 semantic ownership 问题。S2 不阻塞，建议在 S3 或 cleanup pass 修复。

## 12. Final Ledger

| 类别 | 数量/状态 |
| --- | --- |
| material finding | **1** (R06-S2-CR-F01, Low) |
| blocker | **0** |
| S1 accepted findings closure | **全部 CLOSED 保持**（0 回退） |
| S2 authored production | **7**（全在 allowlist） |
| S2 authored tests | **4**（全在 allowlist） |
| Verdict | **PASS** |

**READY_FOR_CONTROLLER_ADJUDICATION**
