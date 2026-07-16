# WU-SEMANTIC-OWNERSHIP-01 R07-S2 累计 S1+S2 code re-review（AgentDS 第二路）

## 1. Gate 身份与基线

- **所属工作单元**: 既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`，内部 sub-WU `R07`。
- **当前 gate**: R07-S2 cumulative code review fix 后的 MiMo/DS 双路 re-review（第二路 DS）。
- **审查基线**: HEAD `386fef8d7a7ecbd977c455ca86bb8bab875d1a98` 上全部未提交累计 S1+S2 product/test/README changes，含 Codex fix 对 R07-S2-CR-F01 的修改。
- **权威输入**:
  - accepted plan: `docs/host/wu-semantic-ownership-01-r07-fins-storage-snapshot-opaque-identity-plan.md`（SHA-256 `ade7691846b9591fa27ece0bbf871b361761714436ff59e6b2c333cde137cac1`）
  - AgentMiMo 初审: `docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-mimo.md`
  - AgentDS 初审: `docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-ds.md`
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-controller-adjudication.md`
  - Codex fix artifact: `docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-fix-codex.md`
  - Controller fix validation: `docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-fix-controller-validation.md`
- **本 artifact 角色**: 只审查并写 re-review artifact；不修改生产代码、测试、README、plan、control，不 stage/commit/push/PR。
- **输出**: 本文即为唯一 artifact。

## 2. 审查方法

按 Controller adjudication 要求执行完整累计 S1+S2 re-review，重点覆盖：

1. R07-S2-CR-F01 是否真正关闭：protocol/private implementation 唯一拥有 context lifecycle；active primary + close secondary 保留同一 primary 且完整 graph path-free；无 primary 时 close error 正常传播；`Literal[False]` 不压制异常；显式 close 幂等/失败后可重试不回退。
2. preprocess、SEC fiscal、active 6-K 三个 consumer 都使用同一 lifecycle，无 local shim/fallback；preprocess close-before-commit/rollback、6-K mutation-after-close、fiscal best-effort/算法不变。
3. 完整复核 S1 findings 与 S2 CV-F01..03 仍关闭，opaque identity/revision/snapshot 同版/0-1-2 kind/security/containment/symlink/atomic/recovery/exception graph 无回退。
4. 无 S3/cache/borrow/read-runtime、R08+、Issue 142/151/175/177/178、统一 authorization 偷带。
5. 复核 tests、coverage、pyright/Ruff/diff/scans 和 README no-change 裁决。

每个 finding 含直接代码证据、严重度、owner、最小修复；区分 material / observation / deferred。

## 3. 独立验证矩阵

Controller 独立运行（本 re-review 复核确认）:

| 检查 | 结果 |
|---|---|
| 五文件累计 pytest | `401 passed, 3 warnings in 24.08s`（本 re-review 独立运行） |
| Full pyright | `0 errors, 0 warnings, 0 informations` |
| Scoped Ruff（15 production + 5 test） | `All checks passed!` |
| Full Ruff baseline | `152`（F401=72, E402=66, F841=10, F541=3, F821=1），未扩散 |
| `git diff --check` | PASS |
| Changed production file coverage | 全部 ≥ 80%（80.00%–100.00%），`_fs_source_snapshot.py` 90.20% |
| `/tmp/dayu-source-snapshot-*` 残留 | 0 |
| `.digest` / hash builder / SHA grammar 残留 | 0 |
| Consumer `snapshot.close()` / `sys.exc_info` / `_append_secondary_error_note` 残留 | 0 |
| S3/R08+/Issue/统一 authorization 偷带 | 0 |

## 4. R07-S2-CR-F01 关闭验证

### 4.1 Protocol owner 唯一拥有 context lifecycle

**证据**: `repository_protocols.py:87-125`

`SourceSnapshotProtocol` 定义了 `__enter__` → `SourceSnapshotProtocol` 与 `__exit__(exc_type, exc, traceback) → Literal[False]`。该协议是 storage 层暴露的唯一 resource lifecycle contract；consumer 不拥有异常优先级、secondary error 投影或 close fallback 规则。

**裁决**: ✅ protocol 唯一拥有 context lifecycle。

### 4.2 Active primary + close secondary 保留同一 primary 且完整 graph path-free

**证据**: `_fs_source_snapshot.py:318-352`

```python
def __exit__(self, exc_type, exc, traceback) -> Literal[False]:
    del exc_type, traceback
    try:
        self.close()
    except BaseException as close_error:
        if exc is None:
            raise
        _append_secondary_error_note(exc, close_error, action=_SNAPSHOT_CONTEXT_CLOSE_ACTION)
    return False
```

- `exc is not None`（有活动主异常）时：`close()` failure 只通过 `_append_secondary_error_note` 追加固定 `action="source snapshot lifecycle close failed"` + `error_type` + 可选 `errno`；raw close message、cause、context、traceback 与 locator 均不进入异常图。
- `return False` 明确不压制 lifecycle body 异常。

**测试证据**: `test_snapshot_context_preserves_active_primary_when_close_fails`（atomicity L4787-4877）：
- 断言顶层仍是同一个 `ValueError` 主异常 identity
- `_exception_graph_nodes(exc_info.value) == (primary_error,)` — 异常图仅含主异常一个节点
- `__notes__` 仅含固定格式 `"source snapshot lifecycle close failed: error_type=PermissionError errno=13"`
- 异常图 path-free（不含 workspace root、temp root name、raw close message）
- close 失败后 temp_root 保留，恢复 rmtree 后显式 `close()` 可重试成功

**裁决**: ✅ active primary 完整保留，secondary note path-free，重试合同保持。

### 4.3 无 primary 时 close error 正常传播

**证据**: `_fs_source_snapshot.py:342-343`

`exc is None`（无活动主异常）时：`close()` failure 直接 `raise`，不吞错。

**测试证据**: `test_snapshot_context_propagates_close_failure_without_active_primary`（atomicity L4880-4966）：
- 断言 `PermissionError` 为主异常传播
- `exc_info.value is not raw_close_error` — 传播的是 path-free 投影后的异常
- `exc_info.value.__context__ is None` — 无 raw close error context 泄漏
- 异常图 path-free（不含 workspace root、temp root name、raw close message）
- close 失败后 temp_root 保留，恢复后显式 `close()` 可重试成功

**裁决**: ✅ 无 primary 时 close failure 正常传播，不吞错，path-free。

### 4.4 `Literal[False]` 不压制异常

**证据**: `_fs_source_snapshot.py:352`

`return False` 是 `__exit__` 的唯一返回路径。Python context manager 协议规定 `__exit__` 返回 truthy 值才压制异常；返回 `False` 明确不压制。

**裁决**: ✅ `Literal[False]` 不压制 lifecycle body 异常。

### 4.5 显式 close 幂等/失败后可重试不回退

**证据**: `_fs_source_snapshot.py:161-182`

`_SnapshotResourceState.close()`:
- `closed = True` 先阻止后续读取（L177）
- `temp_root` 保留到 rmtree 成功后才清空（L178-182）
- rmtree 失败时 `temp_root` 保留，下次 close 可重试同一临时树

`__exit__` 不改变 `close()` 的既有 contract；`__exit__` 只新增 active-primary-aware 异常优先级。

**裁决**: ✅ 显式 close 幂等/失败后可重试不回退。

### 4.6 三个 consumer 全部使用同一 lifecycle

**证据**:

- `ingestion_runtime.py:4138-4194`: `with self.source_repository.read_source_snapshot(...) as snapshot:` — processor/section/table/processed 全部在 `with` 块内；`commit_started = True` 在 `with` 块退出后设置；`finally` 块中 `commit_started` 为 False 时 rollback。
- `sec_fiscal_fields.py:280-294`: `with snapshot:` — 提取 fiscal 字段在 `with` 块内；`read_source_snapshot` 异常由外层 `except Exception` 做 best-effort 吸收返回 `(None, None)`；lifecycle close failure 不被该 except 吞掉，按 owner 规则正常传播或附加 note。
- `sec_6k_primary_document_repair.py:109-134`: `with source_repository.read_source_snapshot(...) as snapshot:` — meta 读取、候选评估、选文决策全部在 `with` 块内；source mutation（`_update_active_6k_primary_document`）在 `with` 块退出后执行。

**Scan 证据**: 三个文件均无 `snapshot.close()`、`sys.exc_info` 或 `_append_secondary_error_note` 残留。

**裁决**: ✅ 三个 consumer 全部使用同一 owner lifecycle，无 local shim/fallback。

### 4.7 preprocess close-before-commit/rollback 顺序不变

**证据**: `ingestion_runtime.py:4135-4198`

```
begin_batch → [with snapshot: processor work] → commit_started=True → commit_batch
                                                                   ↓ (finally)
                                              commit_started=False → rollback
```

- `with` 块正常退出后 `commit_started = True` 才设置，然后 commit。
- `with` 块内异常（processor failure）→ `__exit__` 保留 primary + 附加 close note → `commit_started` 仍为 False → rollback。
- `with` 块正常退出但 close 失败 → `__exit__` raise close error → `commit_started` 仍为 False → rollback。
- commit 开始后（`commit_started = True`）→ finally 不执行 rollback；`commit_batch` 自身终态消费 capability。

**裁决**: ✅ close-before-commit/rollback 顺序不变。

### 4.8 6-K mutation-after-close 顺序不变

**证据**: `sec_6k_primary_document_repair.py:109-151`

`_update_active_6k_primary_document` 和 `mark_processed_for_6k_reconcile` 在 `with` 块退出后执行；caller-owned batch commit/rollback 语义不变。

**裁决**: ✅ 6-K mutation-after-close 顺序不变。

### 4.9 SEC fiscal best-effort/算法不变

**证据**: `sec_fiscal_fields.py:280-294`

- `read_source_snapshot` 异常由外层 `except Exception` 吸收返回 `(None, None)`（acquisition-only best-effort 边界不变）。
- `_build_download_local_file_map` 仍按 snapshot descriptor 声明的 exact business filename 建立 lowercase map。
- `_pick_download_xbrl_file` 仍沿用既有排序、suffix 优先级与 XML fallback 排除规则。
- 未引入 `has_xbrl_instance` 内容嗅探或新文件分类 schema。
- lifecycle close failure 不被 acquisition catch 吞掉（符合 owner 语义：已成功取得 snapshot 后的 close failure 是真实文件系统错误，不应被 best-effort 静默忽略）。

**裁决**: ✅ SEC fiscal best-effort/算法不变。close failure propagation 是 owner 语义的正确实施。

### 4.10 R07-S2-CR-F01 最终状态

**CLOSED**。7 项 sub-check 全部通过，无 material finding。

## 5. S1 Findings 关闭复核

### R07-S1-CR-F01 — destructive cleanup complete preflight — **保持关闭**

S2 新增的 snapshot 和 revision 逻辑不涉及 destructive cleanup 路径。`_read_source_snapshot` 是只读操作，不修改 published tree。

### R07-S1-CR-F02 — `begin_batch` primary-error preservation — **保持关闭**

S2 不修改 `begin_batch` 逻辑。R07-S2-CR-F01 的 context lifecycle 修复也不影响 batch 初始化。

### R07-S1-CR-F03（含 CR-CV-F01）— path-free filesystem error producer boundary — **保持关闭**

S2 新增代码（`_fs_source_snapshot.py`）完整复用 `_fs_storage_utils.py` 的 `_project_filesystem_error`、`_raise_path_free_error`、`_append_secondary_error_note` 投影链。无 raw path 泄漏。

**S1 全部 findings 保持关闭，无回退。**

## 6. S2 CV-F01..03 关闭复核

### R07-S2-CV-F01 — `_read_published_marker` guard release 三态 — **保持关闭**

`_fs_source_snapshot.py:1061-1127`: marker_error 为主 + release 次失败只附加 note；marker 成功 + release 失败 raise release；均成功返回 marker。CR-F01 fix 不修改该函数。

### R07-S2-CV-F02 — snapshot close() temp-root cleanup locator 保留 — **保持关闭**

`_fs_source_snapshot.py:161-182`: `closed=True` 先阻止读取，temp_root 保留到 rmtree 成功后清空。CR-F01 fix 的 `__exit__` 调用 `self.close()`，不改变该 contract。

### R07-S2-CV-F03 — initial fstat 主失败保留 — **保持关闭**

`_fs_source_snapshot.py:798-810`: fstat 失败为主，未登记 stream close 失败只追加 note。CR-F01 fix 不修改该路径。

**S2 CV-F01..03 全部保持关闭，无回退。**

## 7. S1 Rejected Findings 误实现复核

| Controller rejected finding | 当前状态 | 判定 |
|---|---|---|
| MIMO-F01: `fil_` 业务分类保留 | `_fs_maintenance_core.py` L742 仍保留 `startswith("fil_")` | ✅ |
| MIMO-F03: 不做 strip/normalization/blacklist | `_fs_identity.py` `_require_external_identity` 仅校验非空+UTF-8 | ✅ |
| MIMO-F04: 不新增 test file | 当前 test allowlist 无新增文件 | ✅ |
| MIMO-F05: `SourceDocumentRevision` 正当引入 | S2 因 `_source_revision_from_meta` 使用而引入 | ✅ |
| DS-F01: backup cross-validation 保留 | `_ticker_identity_from_candidate_key` 保留 target/backup 区分 | ✅ |
| DS-F02: enumeration fail-closed 保留 | `_list_external_identities` 对 corruption fail closed | ✅ |
| DS-F03: processed meta 存在性 owner | 以 meta_path 为准，非 directory existence | ✅ |
| DS-F05: optional guard for generic meta | 两处服务不同 typed owner | ✅ |
| DS-F06: 不用 exist_ok | `_ensure_identity_directory` 无 `exist_ok=True` | ✅ |
| DS-F07: deterministic missing locator | `_identity_directory_for_read` 确认 | ✅ |
| DS-F08: removeprefix producer 关系 | fixture 编码 SEC producer 业务关系 | ✅ |

**全部 11 项 rejected findings 未被误实现。**

## 8. Opaque Identity / Revision / Snapshot 完整性复核

### 8.1 Opaque identity mapping

- `_normalize_ticker` / `_normalize_document_id`（旧 path-component normalizer）scan: **0 残留**。
- `directory_name` / `lock_path.stem` / `child.name` 用于业务 identity 反推: **0 残留**（所有命中均为内部 descriptor 过滤、manifest 过滤或 `_parse_backup_directory_name` 解析——均不反推业务 identity）。
- 所有 ticker target/staging/backup/locks/recovery 路径使用 `_derive_storage_key` 与 identity descriptor。
- `cleanup_stale_filing_documents` 从 descriptor 恢复 external document id 后应用 `fil_` 业务判断。
- `DownloadRejectionRegistry` JSON key 保留 exact external document id。
- AST 审计: 无 raw external identity path join 残留。

**裁决: ✅ opaque identity mapping 完整，无回退。**

### 8.2 Persisted opaque revision

- `SourceDocumentRevision.digest` → `token` breaking rename: **已完成**，无 alias/property/双字段/compat shim。
- `_build_source_revision` / selected-field hash builder / SHA grammar: **0 残留**（scan 为空）。
- `_prepare_complete_source_meta` 在每次 source mutation 时生成 `uuid.uuid4().hex` 作为新 token，caller 提供的同名字段被 pop。
- `get_source_revision`（S2 checkpoint）只机械读取 persisted token 并构造 `SourceDocumentRevision(token=...)`。
- 测试 `test_published_revision_is_persisted_and_changes_only_with_source_publication` 验证跨 repository 实例 exact equality。
- 测试 `test_source_document_revision_accepts_nonempty_opaque_token_and_rejects_empty` 验证 frozen grammar。
- 测试 `test_rollback_and_non_source_batch_preserve_published_revision` 验证 rollback/non-source batch 不改变 revision。

**裁决: ✅ persisted opaque revision 完整，无回退。**

### 8.3 Snapshot 同版一致性

- `_acquire_snapshot_attempt_unguarded` 在一次 guard 内读取 identity/meta/provenance/revision/files/primary marker。
- `_build_published_marker` 包含 source_kind、revision、is_deleted、ticker descriptor bytes、document descriptor bytes。
- Post-copy 核对（L523-547）：marker exact equality 比较；不匹配时 discard + retry。
- 测试 `test_snapshot_descriptor_meta_provenance_primary_and_files_share_one_revision` 验证同版一致性。
- 测试 `test_snapshot_concurrent_ab_publication_never_mixes_files` 验证 A/B 不混合。
- 测试 `test_snapshot_transient_change_recovers_and_cleans_discarded_attempt` 验证瞬态变化恢复。
- 测试 `test_snapshot_sustained_change_raises_typed_consistency_failure_and_cleans_resources` 验证持续变化 typed failure。
- 测试 `test_snapshot_fd_copy_silent_mutation_is_corruption_without_revision_change` 验证静态 corruption 保持原分类。

**裁决: ✅ snapshot 同版一致性完整，无回退。**

### 8.4 Source kind 0/1/2 resolution

- `_resolve_snapshot_source_kind_unguarded`: 显式 source kind 验证存在；缺省时 0=FileNotFoundError, 1=use, 2=ValueError。
- 测试 `test_snapshot_explicit_source_kind_ignores_other_kind_with_same_document_id` 验证显式 source kind 不误判。

**裁决: ✅ source kind 0/1/2 resolution 完整，无回退。**

### 8.5 Security retained

| 机制 | 状态 | 证据 |
|---|---|---|
| filename/entry name 单路径组件拒绝 | **保留** | `_normalize_filename` 拒绝 separator/dot/dotdot/absolute/drive |
| local URI/object key containment | **保留并收紧** | URI 只含 private key + safe filename |
| path containment | **保留** | `_require_contained_regular_file` / `_require_contained_path` |
| symlink rejection | **保留并扩展** | descriptor、meta、manifest、business files、snapshot files 全部 fail closed |
| atomic JSON/file write | **保留** | identity descriptor 复用 `_write_json` |
| R06 writer mutex | **保留** | lock locator 改用 internal key |
| R06 publication guard | **保留** | snapshot attempt 短 guard + post-copy 短 guard |
| journal/recovery | **保留** | minimal fields 不变；descriptor 提供 round-trip |
| complete-source validator | **扩展** | 加入 identity descriptor + persisted revision 校验 |
| typed provenance/citation | **保留** | snapshot.provenance 与 meta 同源 |
| typed read errors | **保留** | consistency exhaustion → `SourceSnapshotConsistencyError` |
| tool/Host authorization | **不触碰** | diff 无 authorization 变更 |

**裁决: ✅ 全部安全机制保留，无回退。**

## 9. S3 / Deferred Scope 审计

以下为明确 deferred scope，**不是 S2 缺口**：

- `read_runtime.py` 的 `revision_before` / `revision_after` before/after equality 比较：仍存在（lines 2198/2230/2503/2558/2594），属于 S3 迁移范围。
- 独立 source meta cache（`_CachedSourceDocumentMeta`）与 processor cache（`_CachedProcessor`）：仍存在。
- `_resolve_source_kind` filing-first probing：仍存在。
- citation 仍独立调用 `get_source_document_provenance`。
- `ProcessorLRUCache.put` / `evict` / `clear` 尚未返回 displaced values。
- `DefaultFinsRuntime` / `_FinsReadProcessTarget` 尚未接通 close/resource cleanup。
- read_runtime.py 的两个 unused imports（`QueryDiagnosis`、`SEARCH_MODE_AUTO`）：S3 删除。
- Issue 142/151/175/177/178：未触碰。
- R08—R12：未触碰。
- 统一 tool authorization：未创建。

**裁决: ✅ S2 scope 边界清晰，无 scope creep。**

## 10. Adversarial Failure Pass

### 10.1 Context lifecycle 双失败

| 场景 | 测试 | 结果 |
|---|---|---|
| active primary + close secondary | `test_snapshot_context_preserves_active_primary_when_close_fails` | ✅ primary identity 保留，note path-free，重试合同保持 |
| no active primary + close primary | `test_snapshot_context_propagates_close_failure_without_active_primary` | ✅ close failure 正常传播，path-free，重试合同保持 |

### 10.2 S2 既有 adversarial 场景

| 场景 | 测试 | 结果 |
|---|---|---|
| A/B publication 不混合 | `test_snapshot_concurrent_ab_publication_never_mixes_files` | ✅ |
| 短暂变化恢复 | `test_snapshot_transient_change_recovers_and_cleans_discarded_attempt` | ✅ |
| 持续变化 typed failure | `test_snapshot_sustained_change_raises_typed_consistency_failure_and_cleans_resources` | ✅ |
| 静态 corruption 不伪装 | `test_snapshot_fd_copy_silent_mutation_is_corruption_without_revision_change` | ✅ |
| symlink/meta mismatch | `test_snapshot_rejects_symlink_containment_and_file_meta_mismatch` | ✅ |
| acquire primary + release secondary | `test_snapshot_acquire_primary_survives_guard_release_secondary_without_locator` | ✅ |
| release primary + FD close secondary | `test_snapshot_guard_release_primary_survives_fd_close_secondary_without_locator` | ✅ |
| marker primary + guard release secondary | `test_snapshot_marker_read_primary_survives_guard_release_secondary_without_locator` | ✅ |
| marker/copy primary + FD/temp secondary | `test_snapshot_marker_primary_survives_fd_and_temp_cleanup_failures` | ✅ |
| transient discard 双 cleanup | `test_snapshot_transient_discard_cleanup_preserves_first_failure_and_attempts_all` | ✅ |
| close failure → retry → idempotent | `test_snapshot_close_failure_retains_cleanup_root_for_concurrent_retry` | ✅ |
| initial fstat primary + stream close secondary | `test_snapshot_initial_fstat_primary_survives_stream_close_secondary` | ✅ |

全部 14 个 adversarial 场景通过，异常图均 path-free。

## 11. Semantic Ownership Drift 检查

**无新增漂移**:

- Context lifecycle（`__enter__`/`__exit__`）的唯一 owner 是 `SourceSnapshotProtocol` + `_FsSourceSnapshot`，在 storage 层。
- 双失败决策（active primary preservation / close failure propagation）由 storage `__exit__` 唯一拥有；consumer 不复制该逻辑。
- `_SNAPSHOT_CONTEXT_CLOSE_ACTION` 是 module-private `Final[str]`，不进入 public contract。
- 既有的 `_append_secondary_error_note` 投影链不变，仍是 `_fs_storage_utils.py` 的唯一 owner。
- `SourceDocumentRevision.token` 生成/读取/投影 owner 不变。
- Source kind resolution owner 不变。
- Snapshot descriptor/meta/provenance/revision/files/primary 采集 owner 不变。

**裁决: ✅ 无 semantic ownership drift。**

## 12. Observations

### OBS-1 — 低 — SEC fiscal close failure propagation 行为变化已文档化

`sec_fiscal_fields.py:280-294`: `read_source_snapshot` 的 `except Exception` 只包裹 acquisition，不包裹 `with` 块。当 `_extract_download_fiscal_from_snapshot` 正常返回且 `__exit__` 的 close 失败时，close failure 传播而不是被 best-effort 吞掉。这是 R07-S2-CR-F01 owner 语义的正确实施（已成功取得 snapshot 后的 close failure 是真实文件系统错误），但相比旧代码的行为有变化。Codex fix artifact 已明确记录此行为："已成功取得 snapshot 后的 lifecycle close failure 不被 acquisition catch 吞掉"。

**严重度**: 低（信息性，已文档化）。

**建议**: 无需修复。若未来发现 close failure 对 download 成功率造成实际影响，可考虑将 close 移入 try/except 但保留 primary-preservation（即 active-primary-aware 而非无条件 swallow）。当前 owner 语义优先。

### OBS-2 — 低 — `_fs_identity.py` 无直接单元测试

与 MiMo residual 一致：6 个函数的覆盖率来自集成测试间接路径（80.00%）。S1/S2 test allowlist 约束下未新增 test file。Controller 已裁决为 no-action。

### OBS-3 — 低 — `_fs_storage_utils.py` error projection 函数无直接单元测试

与 MiMo residual 一致：`_project_filesystem_error`、`_raise_path_free_error`、`_append_secondary_error_note` 的覆盖率来自上层集成路径（83.82%）。Controller 已裁决为 no-action。

## 13. Verdict

**VERDICT: PASS, 0 MATERIAL FINDINGS, 0 BLOCKERS**

- **R07-S2-CR-F01**: **CLOSED** — 7 项 sub-check 全部通过（protocol 唯一拥有 lifecycle、active primary 保留、无 primary 传播、`Literal[False]` 不压制、显式 close 幂等/可重试、三个 consumer 使用同一 lifecycle、preprocess/6-K/fiscal 顺序/算法不变）。
- **S1-CR-F01..03 / S1-CR-CV-F01**: 全部保持关闭，无回退。
- **S2-CV-F01..03**: 全部保持关闭，无回退。
- **Opaque identity mapping**: 完整，无 raw identity path join 残留。
- **Persisted opaque revision**: 完整，无 hash builder/SHA grammar 残留。
- **Snapshot 同版/0-1-2 kind/security/containment/symlink/atomic/recovery**: 全部保留，无回退。
- **Exception graph**: 完整 path-free，14 个 adversarial 场景全部通过。
- **Consumer lifecycle**: 三个 consumer 全部使用统一 owner lifecycle，无 local shim/fallback。
- **S3/Deferred scope**: 边界清晰，无 scope creep。
- **R08+/Issue 142/151/175/177/178/统一 authorization**: 0 偷带。
- **Tests**: 401 passed，owner-level，不断言实现细节。
- **Coverage**: 15 个 changed production files 全部 ≥ 80%（80.00%–100.00%）。
- **Static**: pyright 0 errors，scoped Ruff 0，full Ruff 152 未扩散，`git diff --check` pass。
- **Scans**: identity/revision/hash/LLM-facing/temp-root 全部 clean。
- **README**: no-change 裁决成立（本 fix 未改变已记录的稳定用户/业务 contract）。

### 13.1 下一 gate

本 re-review 完成，等待 Controller adjudication。Controller 需裁决本 artifact 与 AgentMiMo re-review artifact，确认 R07-S2 全部 findings 关闭后授权下一 gate。

---

**审查完成时间**: 2026-07-16
**审查 Agent**: AgentDS（第二路 re-review）
**目标**: Controller adjudication
