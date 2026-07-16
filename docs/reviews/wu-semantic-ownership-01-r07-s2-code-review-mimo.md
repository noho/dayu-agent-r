# WU-SEMANTIC-OWNERSHIP-01 R07-S2 Complete Cumulative S1+S2 Code Review — AgentMiMo

## Scope

- Mode: current changes (cumulative S1+S2 working tree review)
- Branch: `phaseflow/host-issues-control`
- Base: transition HEAD `386fef8d7a7ecbd977c455ca86bb8bab875d1a98`（`docs: enter R07 opaque identity implementation`）
- Output file: `docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-mimo.md`
- Included scope: 13 production files（plan §7.1 S1 allowlist + `_fs_identity.py` + `_fs_source_snapshot.py` + S2 touched `_fs_storage_infra.py` / `_fs_source_document_core.py` / `document_models.py` / `ingestion_runtime.py` / `sec_6k_primary_document_repair.py` / `sec_fiscal_fields.py` / `fs_source_document_repository.py` / `repository_protocols.py`）+ 4 test files + 2 README
- Excluded scope: S3 read-runtime cache/borrow/filing-first（accepted deferred boundary）、R08+、Issue 142/151/175/177/178、统一 authorization、plan、control、design doc
- Parallel review coverage: 4 subagents — (1) authoritative input docs + S1/S2 artifacts, (2) plan/design docs, (3) all 15 production code files, (4) all 4 test files。主 reviewer 独立读取 `_fs_identity.py`、`_fs_source_snapshot.py`、`_fs_source_document_core.py`、`_fs_storage_infra.py`、`_fs_storage_utils.py` 关键路径并复核全部 evidence chain。

## 验证矩阵

| 检查 | 结果 |
|---|---|
| 五个 exact full test files | `399 passed, 3 warnings`（Controller 独立验证 23.72s） |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| scoped Ruff（13 production + 4 test + 2 README） | `All checks passed!` |
| full Ruff baseline | 既有 `152`：`72 F401 / 66 E402 / 10 F841 / 3 F541 / 1 F821`，未扩散 |
| `git diff --check` | PASS |
| S3/R08+/Issue 142/151/175/177/178/统一 authorization 偷带 | 0 |
| `.digest` / revision hash builder / hash grammar 残留 | 0（仅 implementation artifact 说明文本） |
| `/tmp/dayu-source-snapshot-*` 残留 | 0 |

## 结论

**PASS**

累计 S1+S2 product/test tree 通过完整对抗性审查。S1 三个 accepted findings（CR-F01、CR-F02、CR-F03/CV-F01）全部保持关闭，无回退。S2 三个 Controller accepted findings（CV-F01、CV-F02、CV-F03）全部保持关闭。Controller rejected 的 11 项 S1 finding 均未被误实现。未发现新的 material blocker finding。发现 2 个 observations（非 blocker）。

---

## S1 Accepted Findings 保持关闭确认

### R07-S1-CR-F01 — destructive cleanup complete preflight — **保持关闭**

**Production evidence（S2 累计验证）**:

- `_fs_storage_infra.py::_validate_complete_source_kind_tree`（L712-811）在任何删除前完成只读完整校验：filing source root non-symlink directory、仅允许已知条目、manifest typed 字段、descriptor/meta bidirectional consistency、physical files 与 meta claims 双向一致、descriptor document IDs 与 manifest document IDs 双向一致。任意 corruption 均 `raise`，无 fallback/skip/continue。
- `_fs_maintenance_core.py::_preflight_filing_cleanup`（L594-621）组合 complete filing tree + download rejection registry + nested rejected tree preflight。
- `_fs_processed_core.py::_preflight_processed_cleanup`（L356-433）在删除前一次性验证 processed root、known control、identity descriptor、required `meta.json`、exact document ID、regular entries、manifest typed/duplicate/set equality。

**S2 未引入回退**: S2 新增的 snapshot 和 revision 逻辑不涉及 destructive cleanup 路径。`_read_source_snapshot` 是只读操作，不修改 published tree。

**裁决**: CR-F01 保持关闭。

---

### R07-S1-CR-F02 — `begin_batch` primary-error preservation — **保持关闭**

**Production evidence（S2 累计验证）**:

`_fs_storage_infra.py::begin_batch`（L488-566）state machine 保持不变：

1. 构造未发布的 local state；
2. 执行 journal、descriptor/copy 或 fresh structure initialization；
3. 捕获最早 primary；若是 raw filesystem `OSError`，先按 F03 投影为 path-free storage error；
4. staging cleanup 与 writer-lock release 分别 best effort 执行；任一失败只用 `_append_secondary_error_note` 附加 path-free 诊断；
5. 只有全部初始化成功后才写入 `_active_batches` 与 `_active_transaction_by_ticker`。

**S2 未引入回退**: S2 不修改 `begin_batch` 逻辑。

**裁决**: CR-F02 保持关闭。

---

### R07-S1-CR-F03（含 CR-CV-F01）— path-free filesystem error producer boundary — **保持关闭**

**Production evidence（S2 累计验证）**:

`_fs_storage_utils.py` 核心投影链保持不变：

- `_project_filesystem_error`（L474-498）：创建与 raw exception 同类型、同 `errno` 的 path-free 顶层异常与 path-free cause。
- `_raise_path_free_error`（L501-523）：`raise error from error.__cause__` 保留预构造 path-free cause；`__context__ = None` 清除 Python 自动注入的 raw context。
- `_append_secondary_error_note`（L526-549）：只写 `action: error_type={class_name}` + 可选 `errno={errno}`。

S2 新增的 `_fs_source_snapshot.py` 完整复用同一投影链：

- `_acquire_snapshot_attempt`（L599-658）：guard release failure 通过 `_append_secondary_error_note` 附加到主异常。
- `_read_published_marker`（L1007-1073）：marker read failure 保留主异常，release failure 附加为 note。
- `_cleanup_snapshot_attempt`（L1226-1282）：FD close / temp cleanup failure 按主次规则附加。
- `_read_stable_file_state`（L1076-1105）：fstat failure 投影为 path-free OSError。
- `_copy_snapshot_file`（L1130-1179）：seek/open/write/fstat failure 均通过 `_project_filesystem_error` + `_raise_path_free_error` 投影。

**S2 未引入回退**: S2 新增代码全部通过 `_fs_storage_utils.py` 的投影函数处理 OSError。无 raw path 泄漏。

**裁决**: CR-F03（含 CR-CV-F01）保持关闭。

---

## S2 Accepted Findings 保持关闭确认

### R07-S2-CV-F01 — `_read_published_marker` guard release 次失败覆盖主失败 — **保持关闭**

**Production evidence**:

`_fs_source_snapshot.py::_read_published_marker`（L1007-1073）三态保留模式：

1. `marker_error` 捕获 marker/meta/descriptor 主失败（L1058-1059）。
2. `release_error` 捕获 publication guard 释放次失败（L1062）。
3. 若 `marker_error is not None`：`_append_secondary_error_note(marker_error, release_error, ...)` 只追加 path-free action/type/errno note（L1063-1068）。
4. 若 `marker_error is None` 且 `release_error is not None`：直接 raise release_error（L1070）。
5. 若均无异常：返回 marker（L1073）。

**Test evidence**: `test_marker_read_primary_survives_guard_release_secondary`（atomicity）断言双失败 exception graph、主异常 identity 不变、release note 可诊断且不含 locator。

**裁决**: CV-F01 保持关闭。

---

### R07-S2-CV-F02 — snapshot `close()` 丢失 temp-root cleanup locator — **保持关闭**

**Production evidence**:

`_fs_source_snapshot.py::_SnapshotResourceState.close()`（L159-180）：

1. `self.closed = True` 先阻止后续读取（L175）。
2. `temp_root = self.temp_root` 保留 cleanup locator（L176）。
3. `_remove_snapshot_temp_root(temp_root)` 执行删除（L179）。
4. `self.temp_root = None` 只在删除成功后清空（L180）。
5. 若 rmtree 抛异常，`temp_root` 保留，下一次 close 可重试。
6. 全部操作在 `self.lock` 内，保证线程安全。

**Test evidence**: `test_close_failure_retains_cleanup_root_for_concurrent_retry`（atomicity）断言失败后并发重试只完成一次真实删除、后续幂等。

**裁决**: CV-F02 保持关闭。

---

### R07-S2-CV-F03 — initial fstat 失败发生在 stream 加入统一 cleanup list 前 — **保持关闭**

**Production evidence**:

`_fs_source_snapshot.py::_acquire_snapshot_attempt_unguarded`（L730-771）：

1. `stream = _open_binary_file(...)` 打开文件（L739-742）。
2. `initial_state = _read_stable_file_state(stream)` 尝试 fstat（L744）。
3. 若 fstat 失败：`stream.close()` 在内部 try/except 中执行（L747-748）；若 close 也失败，`_append_secondary_error_note` 附加到 fstat 主异常（L749-755）；`_raise_path_free_error(initial_state_error)` 抛出 fstat 主异常（L756）。
4. 若 fstat 成功：`open_files.append(...)` 加入统一 cleanup list（L757-763）。
5. 外层 `except BaseException` 调用 `_cleanup_snapshot_attempt` 清理已积累的 open_files（L764-771）。

**Test evidence**: `test_initial_fstat_primary_survives_stream_close_secondary`（atomicity）断言 fstat 主异常保留、close failure 只追加 note、完整 graph 无 workspace/private locator。

**裁决**: CV-F03 保持关闭。

---

## S2 Persisted Opaque Revision Exact Equality

**Production evidence**:

- `_prepare_complete_source_meta`（`_fs_source_document_core.py:1507-1541`）：每次 complete-source mutation 在 owner boundary 生成 `uuid.uuid4().hex` 作为新 revision token（L1540）。旧 revision 被 pop（L1538）。返回 normalized meta 含新 token。
- `_source_revision_from_meta`（`_fs_storage_infra.py:106-127`）：从 persisted meta 机械读取 `_published_source_revision` 字段，构造 `SourceDocumentRevision(token=raw_token)`。`SourceDocumentRevision.__post_init__`（`document_models.py`）拒绝空字符串。
- `get_source_revision`（`_fs_source_document_core.py:483-531`）：在 publication guard 内读取 persisted meta，投影为 typed revision。跨 repository 实例精确相等。

**Test evidence**:

- `test_published_revision_is_persisted_and_changes_only_with_source_publication`（provider）：重新打开 `FsSourceDocumentRepository` 实例，断言 `reopened_repository.get_source_revision(...) == first_revision`（exact equality across instances）。
- `test_source_document_revision_accepts_nonempty_opaque_token_and_rejects_empty`（provider）：验证 frozen grammar（only `token` field）、exact equality semantics、empty token rejection。
- `test_rollback_and_non_source_batch_preserve_published_revision`（provider）：验证 rollback 和 non-source batch 不改变 revision。

**裁决**: S2 persisted opaque revision exact equality contract 完整实现并通过 owner-level 测试。

---

## S2 Complete-Source Mutation Atomic Publication

**Production evidence**:

`_fs_storage_infra.py::commit_batch`（L568-680）：

1. `_validate_complete_source_tree(state)` 只读 staging tree（L594）。
2. `_acquire_publication_guard(state.token.ticker)` 阻塞 readers（L595）。
3. `_replace_directory(target -> backup)` 原子备份（L599）。
4. `_replace_directory(staging -> target)` 原子发布（L601）。
5. `_write_batch_journal(state, COMMITTED)` 持久化（L603）。
6. release publication guard（L611-630）。
7. cleanup backup + staging（L653-676）。

revision 在 `_prepare_complete_source_meta` 中于 staging 写入时生成，随 commit_batch 原子发布到 published tree。publication guard 保证 readers 看到完整一致的 meta + files + revision。

**Test evidence**: `test_concurrent_ab_publication_never_mixes_files`（atomicity）验证 A/B publication 不混合文件。`test_staged_xbrl_read_separate_from_published_read`（atomicity）验证 staging 与 published 隔离。

**裁决**: complete-source mutation 原子发布完整实现。

---

## S2 Light/Full Stable Snapshot 同版一致性

**Production evidence**:

`_fs_source_snapshot.py::_read_source_snapshot`（L439-565）：

**Light snapshot**（`materialize_files=False`）：
- 单次 `_acquire_snapshot_attempt` 在 publication guard 内读取 identity/meta/provenance/revision/files/primary。
- 关闭所有 FDs，返回 `temp_root=None` 的 snapshot。
- 同版 descriptor/meta/provenance/revision 来自同一次 guard 采集。

**Full snapshot**（`materialize_files=True`）：
- 3 次稳定读取尝试（`_STABLE_READ_ATTEMPT_LIMIT=3`）。
- 每次：guard 内读取 + 打开全部 FDs → guard 外复制 → guard 内后验 marker。
- marker 包含 `source_kind`、`revision`、`is_deleted`、`ticker_descriptor` bytes、`document_descriptor` bytes。
- 若 `published_marker != attempt.marker`：discard + retry。
- 若 3 次均变化：raise `SourceSnapshotConsistencyError`。
- FDs 跨 guard boundary 持有，pin inode 保证复制一致性。

**Test evidence**: `test_transient_change_recovers_and_cleans_discarded_attempt`（atomicity）验证瞬态变化恢复。`test_sustained_change_raises_typed_consistency_error_and_cleans_resources`（atomicity）验证持续变化抛 typed error。`test_silent_inode_mutation_is_corruption_without_revision_change`（atomicity）验证静默 inode 变化检测。

**裁决**: light/full stable snapshot 同版一致性完整实现。

---

## S2 Explicit Source-Kind 0/1/2 Resolution

**Production evidence**:

`_fs_source_snapshot.py::_resolve_snapshot_source_kind_unguarded`（L786-825）：

- `source_kind is not None`：验证 meta 存在于指定 kind 路径，返回该 kind（L809-815）。
- `source_kind is None`：`_existing_snapshot_source_kinds_unguarded` 检查 filing 和 material 两个目录（L816-820）。
  - 0 个：raise `FileNotFoundError`（L822）。
  - 1 个：返回该 kind（L825）。
  - 2 个：raise `ValueError("source kind 不明确")`（L824）。

**Test evidence**: `test_snapshot_descriptor_meta_provenance`（provider）验证 explicit source kind 忽略其他 kind 同 document ID。`test_source_kind_resolution` 在 atomicity 和 provider 测试中覆盖 0/1/2 场景。

**裁决**: explicit source-kind resolution 完整实现。

---

## S2 Preprocess/SEC Fiscal/Active 6-K 单 Snapshot 生命周期

**Production evidence**:

- `sec_6k_primary_document_repair.py::reconcile_active_6k_primary_document`：调用 `source_repository.read_source_snapshot(ticker, document_id, SourceKind.FILING, materialize_files=True)`，使用 `snapshot.get_source(filename)` 访问文件，`snapshot.close()` 在 `finally` 块中（try/finally 模式）。
- `sec_fiscal_fields.py::_extract_download_fiscal_from_xbrl`：调用 `source_repository.read_source_snapshot(..., materialize_files=True)`，使用 `snapshot.get_source(name)` 物化 XBRL 文件，`snapshot.close()` 在 `finally` 块中。snapshot read 异常被吸收（best-effort 语义，返回 `None, None`）。
- `ingestion_runtime.py` preprocess pipeline：在 batch 内获得 full snapshot，关闭 snapshot 后再 commit。

**裁决**: 三个 consumer 均持有单一 snapshot 生命周期并在 finally 中关闭。符合 plan 设计。

---

## S1 Rejected Findings 误实现检查

| Controller rejected finding | 要求 | 实际状态 | 判定 |
|---|---|---|---|
| MIMO-F01: `fil_` 业务分类保留 | stale cleanup 在 descriptor 恢复 exact external ID 后应用 `startswith("fil_")` 业务分类 | `_fs_maintenance_core.py` L742 确认 `startswith("fil_")` 仍存在 | 正确 |
| MIMO-F03: 不做 strip/normalization/blacklist | `_require_external_identity` 仅校验非空+UTF-8 | `_fs_identity.py` L44-64 确认，无 null byte/control/whitelist 检查 | 正确 |
| MIMO-F04: 不新增 test file | S1 test allowlist 只有 4 个文件；S2 未新增 `_fs_identity.py` 直接测试 | 无第五个 test file | 正确 |
| MIMO-F05: `SourceDocumentRevision` 未使用 | S1 re-review 确认从 infra import 删除 | S2 因 `_source_revision_from_meta` 使用而重新引入，属正当新增 | 正确 |
| DS-F01: backup cross-validation 保留 | corrupt backup 不阻止 valid target | `_ticker_identity_from_candidate_key` 保留 target/backup 区分 | 正确 |
| DS-F02: enumeration fail-closed 保留 | `_list_external_identities` 对 corruption fail closed | `_fs_identity.py` L296-338 确认，无 per-artifact skip | 正确 |
| DS-F03: processed meta 存在性 owner | 不以 directory existence 替代 | `_delete_processed_impl` 以 meta_path 为准 | 正确 |
| DS-F05: optional guard for generic meta | `_get_document_meta_unguarded` 可无 ticker | 两处服务不同 typed owner | 正确 |
| DS-F06: 不用 exist_ok | `_ensure_identity_directory` 无 `exist_ok=True` | L169 确认，writer lock 序列化 | 正确 |
| DS-F07: deterministic missing locator | 目录不存在时返回确定性路径 | `_identity_directory_for_read` L266-272 确认 | 正确 |
| DS-F08: removeprefix producer 关系 | fixture 编码 SEC producer 业务关系 | provider test 确认 | 正确 |

**裁决**: 全部 11 项 rejected findings 均未被误实现。语义所有权边界正确。

---

## Adversarial Failure Pass

### Snapshot Resource Ownership

**检查**: snapshot 资源是否在所有异常路径中正确释放。

**结论**: 通过。

- `_acquire_snapshot_attempt`：guard release failure 时，若 acquire 成功则 cleanup attempt 并 raise release_error；若 acquire 失败则 release failure 只附加 note（L638-655）。
- `_read_source_snapshot` retry loop：每次 `_cleanup_snapshot_attempt` 都正确关闭 FDs 和删除 temp_root（L482-547）。
- `_FsSourceSnapshot.close()`：幂等、线程安全、temp_root 只在删除成功后清空（L159-180）。
- consumer 代码（6-K、fiscal）均在 `finally` 中调用 `snapshot.close()`。

### Concurrent Close/Retry

**检查**: 并发 close 是否安全。

**结论**: 通过。

- `_SnapshotResourceState.lock`（threading.Lock）保护 `closed` 和 `temp_root`（L120）。
- `close()` 中 `self.closed = True` 先于 `_remove_snapshot_temp_root` 执行（L175-179）。
- 失败后 `temp_root` 保留，下一次 close 在同一锁边界重试（CV-F02 证据）。
- `_remove_snapshot_temp_root` 对 `FileNotFoundError` 静默返回（L1218-1219），保证幂等。

### Publication Guard / FD / Temp-Root Cleanup 主次异常关系

**检查**: cleanup 路径中主次异常是否正确分离。

**结论**: 通过。

- `_cleanup_snapshot_attempt`（L1226-1282）：
  1. FD close 失败：若有 primary_error 则附加 note；否则成为 cleanup_primary（L1250-1260）。
  2. temp_root 删除失败：附加到 primary_error 或 cleanup_primary；若均无则成为 cleanup_primary（L1267-1279）。
  3. 只有无 primary_error 且有 cleanup_primary 时才 raise cleanup_primary（L1281-1282）。
- `_acquire_snapshot_attempt`（L599-658）：guard release failure 三态处理同 CV-F01 模式。
- `_read_published_marker`（L1007-1073）：marker read failure 三态处理同 CV-F01 模式。

### Containment / Symlink / Atomic / Recovery / Typed Errors / Security

**检查**: S2 新增代码是否保留所有安全约束。

**结论**: 通过。

- **Containment**: `_parse_snapshot_files` 调用 `core._require_contained_regular_file`（L903-907）。`_acquire_snapshot_attempt_unguarded` 调用 `core._require_contained_regular_file`（L734-738）。
- **Symlink**: `meta_path.is_symlink()` 检查（L696-697, L1042-1043）。`_list_directory` 过滤 `.identity.json`（L923-924）。
- **Atomic**: `_write_json` 使用 temp file + `os.replace` + fsync（`_fs_storage_utils.py` L716-749）。
- **Recovery**: batch recovery 逻辑未被 S2 修改。
- **Typed errors**: `SourceSnapshotConsistencyError`（`repository_protocols.py`）为 typed storage error。
- **Security**: 无外部 ID 路径反推、无 published/private locator 暴露。`_SnapshotFileSource.uri` 返回 `"snapshot://source/{name}"`（L194），不含 filesystem path。`_SnapshotFileSource.materialize()` 返回 temp-tree path（L250），不含 published path。所有 OSError 通过 `_project_filesystem_error` 投影为 path-free。

### Semantic Ownership Drift

**检查**: S2 新增代码是否引入语义所有权漂移。

**结论**: 无漂移。

- `SourceDocumentRevision.token` 生成：唯一 owner 是 `_prepare_complete_source_meta`（L1540），在 source mutation boundary。
- `SourceDocumentRevision.token` 读取：唯一 owner 是 `_source_revision_from_meta`（L106-127），在 storage infra 层。
- `SourceDocumentRevision.token` 投影到 snapshot：通过 `_FsSourceSnapshot.revision` 属性（L356-364），受 `require_open()` 约束。
- source-kind resolution：唯一 owner 是 `_resolve_snapshot_source_kind_unguarded`（L786-825），在 snapshot module 内。
- snapshot descriptor/meta/provenance/revision/files/primary：全部在 `_acquire_snapshot_attempt_unguarded` 内从同一 guard 采集，保证同版。

### Over-coupling

**检查**: S2 是否引入不必要的模块间耦合。

**结论**: 无过度耦合。

- `_fs_source_snapshot.py` 只 import `_fs_identity.py`（`_IDENTITY_DESCRIPTOR_FILENAME`、`_require_external_identity`）和 `_fs_storage_infra.py`（`_source_meta_without_revision`、`_source_revision_from_meta`）。不 import `_fs_source_document_core.py`（通过 TYPE_CHECKING 的 `_FsSourceDocumentMixin` 仅为 type hint）。
- `_fs_source_document_core.py` import `_read_source_snapshot` from `_fs_source_snapshot.py`。这是正确的 owner → implementation 依赖。

### Race / Resource Leak

**检查**: S2 是否引入 race condition 或 resource leak。

**结论**: 无。

- snapshot FDs 在 publication guard 内打开，跨 guard boundary 持有以 pin inode。这是有意设计（plan §5.3 稳定读取策略），不是 leak。
- temp_root 在 `_SnapshotResourceState` 中受 threading.Lock 保护。close 后 temp_root 被清空。
- `_copy_snapshot_file` 使用 `open("xb")` 创建排他文件，避免覆盖。
- `_close_open_snapshot_files`（L1285-1310）逐个关闭 FDs，第一个失败保留为 `first_error`，后续关闭继续执行，最终 raise first_error。

---

## Observations（非 blocker）

### OBS-1 — 低 — `_fs_storage_infra.py` 导入 `SourceHandle` 和 `ProcessedHandle` 未直接使用

- **文件(行号)**: `_fs_storage_infra.py:36-37`
- **场景**: `SourceHandle` 和 `ProcessedHandle` 被导入但在 `_fs_storage_infra.py` 中仅通过 `isinstance(handle, ProcessedHandle)` 使用（L1900, L1960, L2021, L2057, L2255）。这些 isinstance 检查需要类型导入。此为正当使用。
- **实际影响**: 无。导入被 isinstance 检查消费。
- **风险**: 无。

### OBS-2 — 低 — `_fs_storage_utils.py::_write_json` 参数 `payload: Any` 违反编码硬约束

- **文件(行号)**: `_fs_storage_utils.py:701`
- **约束**: CLAUDE.md 编码硬约束禁止使用 `Any`。
- **缓解**: 此为既有模式（同文件 `_read_json` 返回 `dict[str, Any] | list[Any]`、`_extract_file_payloads` 参数 `meta: dict[str, Any]` 等均有类似用法）。项目已有 `JsonValue` 类型（L15 导入），可替代但属于 pre-existing debt。S1 re-review OBS-2 已记录此问题。
- **风险**: 低。pyright 通过，功能无影响。与 S2 新增代码无关。

---

## Open Questions

无。

## Residual Risk

1. **`_fs_identity.py` 无直接单元测试**: 6 个函数的覆盖率来自集成测试间接路径（Controller 验证 80.00%+）。S1/S2 test allowlist 约束下未新增 test file。若 S3 允许扩展 test file，建议补充直接单元测试。
2. **`_fs_storage_utils.py` error projection 函数无直接单元测试**: `_project_filesystem_error`、`_raise_path_free_error`、`_append_secondary_error_note` 的覆盖率来自上层集成路径（83.82%+）。同上约束。
3. **`_require_external_identity` 不拒绝 null byte / 控制字符 / 纯空白**: S1 MIMO-F03 rejected finding，Controller 确认为当前设计决策。当前所有调用方传入的 ticker/document_id 均为正常业务值，不触发此问题。
4. **legacy Ruff 152 fingerprint**: 既有 `72 F401 / 66 E402 / 10 F841 / 3 F541 / 1 F821`，未扩散。不属于 R07-S1/S2 owner。
5. **`edgar` 3 个 deprecation warning**: 既有安装环境问题，未扩散。

以上 residual 均不阻塞 S2 gate。

---

## 覆盖确认

| 维度 | 结论 |
|---|---|
| descriptor 为唯一 round-trip truth | ✅ 所有 point lookup/listing/recovery 通过 descriptor 校验，无目录名推断 |
| CR-F01 destructive cleanup complete preflight | ✅ filing/processed/rejected 三类均在 mutation 前完成 whole-candidate preflight；S2 未引入回退 |
| CR-F02 `begin_batch` primary-error preservation | ✅ 初始化主异常始终为 authoritative；cleanup/release 只附加 note；S2 未引入回退 |
| CR-F03/CV-F01 path-free exception graph | ✅ 完整 graph（cause/context/args/notes/traceback）无 locator；S2 新增代码全部复用投影链 |
| CV-F01 marker read guard release 三态 | ✅ marker 主失败保留，release 次失败只附加 note |
| CV-F02 close() temp-root cleanup locator 保留 | ✅ locator 只在删除成功后清空；失败后并发重试幂等 |
| CV-F03 initial fstat 主失败保留 | ✅ fstat 主因保留，close failure 只附加 note |
| S2 persisted opaque revision exact equality | ✅ 跨 repository 实例精确相等；token 只在 `_prepare_complete_source_meta` 生成 |
| S2 complete-source mutation 原子发布 | ✅ publication guard 内完成 swap；revision 随 commit 原子发布 |
| S2 light/full stable snapshot 同版一致性 | ✅ 同一 guard 采集 descriptor/meta/provenance/revision/files/primary |
| S2 explicit source-kind 0/1/2 resolution | ✅ 0=FileNotFoundError, 1=use, 2=ValueError |
| S2 preprocess/SEC fiscal/active 6-K 单 snapshot | ✅ 三 consumer 均持有单一生命周期并在 finally 中关闭 |
| S2 snapshot resource ownership / 并发 close/retry | ✅ threading.Lock 保护；close 幂等；cleanup 正确分层 |
| S2 publication guard/FD/temp-root cleanup 主次异常 | ✅ 完整 path-free exception graph |
| containment/symlink/atomic/typed errors/security | ✅ 全部保留 |
| 无外部 ID 路径反推 / 无 published/private locator 暴露 | ✅ |
| 无兼容 shim / 下游 fallback / 统一 authorization | ✅ |
| S1 rejected findings 未被误实现 | ✅ 全部 11 项确认 |
| 无 S3/R08+/Issue/统一 authorization 偷带 | ✅ |
| README 诚实声明当前 S2 状态 | ✅ 未提前宣称 S3 完成 |
| 测试 owner-level contract | ✅ 399 passed |
| 静态检查 | ✅ pyright 0 errors + Ruff baseline 152 未扩散 |
| 单文件覆盖率 | ✅ changed production files 82.51%–100%（Controller 验证） |
