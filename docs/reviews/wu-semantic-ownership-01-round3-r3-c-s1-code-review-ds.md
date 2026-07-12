# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S1

## Artifact Metadata

- Review type: adversarial deep code review (current changes mode)
- Target slice: `S1 Storage Identity, Commit Point, And Local Durability`
- Branch: `phaseflow/host-issues-control`
- Base: `main` (via uncommitted workspace diff)
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-ds.md`
- Timestamp: 2026-07-13T00:05:06+08:00
- Risk profile: production-high
- Status: pass

## Scope

### Included

5 modified production files（均在 accepted plan S1 allowed file scope 内）：

- `dayu/fins/storage/_fs_storage_utils.py` — single-component validator, object-key validator, local URI containment, `_write_json` temp cleanup
- `dayu/fins/storage/_fs_storage_infra.py` — `commit_batch` rewrite, `_replace_directory`/`_remove_directory`/`_rollback_precommit_batch`/`_cleanup_committed_batch` helpers, orphan recovery 语义反转
- `dayu/fins/storage/_fs_blob_core.py` — `store_file()` unified handle existence check, filename normalization reuse
- `dayu/fins/storage/local_file_store.py` — UUID temp, file fsync, atomic replace, finally cleanup, object-key validation in all public methods
- `dayu/fins/storage/repository_protocols.py` — docstring-only contract clarification（protocol 方法集合不变）

1 个 new test file（plan S1 allowed）：

- `tests/fins/test_fins_storage_atomicity.py` — 71 个 owner-level 测试

0 个 modified test files（`test_fins_storage_provider.py` 未修改，其 47 个既有测试作为 regression matrix 继续通过）。

### Excluded

- S2/S3 production files（upload/download workflow, CN/HK temp contract, Host/Service wait adapter）— 未修改
- `tests/fins/test_fins_storage_provider.py` — 未修改，不作为本次 diff 审查
- README、design docs、control docs — 按 `R3-C-PF-09` 延后到全部 slice land 后同步

### Sources of truth consulted

- `AGENTS.md` — 语义所有权、分层架构、编码硬约束
- `docs/host/design.md` — Host/Fins 边界、wait adapter contract
- `docs/engine/design.md` — Engine contract 边界
- `docs/host/issues-implementation-control.md` — plan 要求与验证矩阵
- `docs/phaseflow-umbrella-optimization-control.md` — production-high slice 约束
- Accepted plan: `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-controller-validation.md`
- Plan re-review: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-plan-rereview-ds.md`

## Review Walkthrough

以下按 plan 要求的 7 个重点维度逐一走读，每项给出走读路径、关键状态转换和结论。

### 1. Storage Identity — single-component / object-key / local URI ownership

**走读路径**：

1. `_normalize_path_component()` (`_fs_storage_utils.py:30-53`) 是唯一 single-component 真源。校验链：trim → 判空 → 拒绝 `.` / `..` → 拒绝 `/` / `\` → 拒绝 `Path.is_absolute()` / `PureWindowsPath.drive`。
2. `_normalize_ticker()` (:56-74) — `try_normalize_ticker` canonical 与 fallback `strip().upper()` 都经过 `_normalize_path_component`。
3. `_normalize_entry_name()` (:104-117) — 直接 delegate 到 `_normalize_path_component`。
4. `_normalize_document_id()` (:120-133) — 直接 delegate。
5. `_normalize_filename()` (:136-149) — 直接 delegate，供 `_fs_blob_core.store_file()` 调用。
6. `_normalize_object_key()` (:152-179) — 多组件 key 校验：拒绝空 key、leading slash、反斜杠、空 segment，每个 segment 经 `_normalize_path_component` 校验后 `/` 拼接。
7. `_local_path_from_uri()` (:250-279) — `local://` 解析 → `_normalize_object_key` → `portfolio_root.resolve()` → `path.relative_to(normalized_root)` containment check。
8. `LocalFileStore._resolve_normalized_key()` (`local_file_store.py:203-219`) — 复用同一 containment 模式（`self._root not in path.parents and path != self._root`）。

**关键断言**：
- 所有 identity owner（ticker/document/entry/filename）都经过同一 `_normalize_path_component` 真源，无各自独立实现。
- object key 和 local URI 都复用 `_normalize_object_key`，无各自解释。
- `local://` URI containment 使用 `path.relative_to()` 硬校验，symlink escape 测试覆盖（`test_local_uri_owner_rejects_symlink_escape`、`test_local_file_store_rejects_symlink_key_escape`）。

**结论**：✅ Identity ownership 正确收敛到 `_fs_storage_utils`，不存在多真源或 caller-side fallback。

### 2. Source/Processed handle existence

**走读路径**：

`store_file()` (`_fs_blob_core.py:142-143`)：

```python
normalized_filename = _normalize_filename(filename)
self._get_handle_meta(handle)
```

- 旧代码：只对 `SourceHandle` 调用 `_get_handle_meta()`，`ProcessedHandle` 不经存在性校验直接构造 key。
- 新代码：先规范化 filename，再对两类 handle **无条件**调用 `_get_handle_meta()`，之后才构造 key → `FileStore.put_object()`。

**关键断言**：
- `test_store_file_requires_source_or_processed_meta_before_file_store_call` — 两类 handle 均 spy `FileStore.put_object()` 调用次数为 0，异常类型为 `FileNotFoundError`。

**结论**：✅ 两类 handle existence check 统一，不存在 ProcessedHandle bypass。

### 3. commit_batch — COMMITTED 唯一提交点

**走读路径**：

`commit_batch()` (`_fs_storage_infra.py:259-291`)：

```text
if old target exists → _replace_directory(target_dir, backup_dir)  # atomic rename
_write_batch_journal(BACKED_UP_TARGET)     # journal via _write_json (atomic + dir sync)
_replace_directory(staging_dir, target_dir) # atomic rename
_write_batch_journal(SWAPPED_TARGET)
_invalidate_company_meta_caches()
_write_batch_journal(COMMITTED)            # ← 唯一 commit point
→ on success: _cleanup_committed_batch()   # best-effort backup/staging cleanup
→ on exception: _rollback_precommit_batch() # undo pre-commit state
finally: pop token, unbind owner, release lock
```

关键变化对比旧代码：
- 旧：`swap → delete backup → write COMMITTED`（窗口：backup 已删除但 COMMITTED 未写，crash 后 recovery 误判为已提交）
- 新：`swap → write COMMITTED → cleanup backup`（COMMITTED 在 backup cleanup 之前，crash 后 recovery 正确判定未提交/已提交）

`_write_batch_journal()` (:707-737) 调用 `_write_json(token.journal_path, payload)`。`_write_json` 的完整链：`unique temp → file flush/fsync → os.replace → parent-directory fsync → finally temp unlink`。因此 COMMITTED journal 继承了完整的 atomic JSON + dir sync 模式，满足 plan `R3-C-PF-10` 要求。

**关键断言**：
- `test_committed_journal_write_syncs_parent_directory` (:640-703) — spy `_fsync_directory` 确认 COMMITTED journal 写入后 journal parent directory 在 synced_paths 中。
- `test_commit_critical_directory_renames_sync_both_parents` (:706-749) — spy `_fsync_directory` 确认 target/backup/staging parent 均在关键 rename 后被刷新。

**结论**：✅ COMMITTED 是唯一提交点，journal 使用完整 atomic JSON + dir sync 模式。pre-commit cleanup 移到 COMMITTED 之后。

### 4. SWAPPED_TARGET before COMMITTED recovery 语义反转

**走读路径**：

Orphan recovery (`_fs_storage_infra.py:811-840`)：

```python
if phase == _PHASE_COMMITTED:
    # preserve new target, delete backup if exists
elif phase in {_PHASE_BACKED_UP_TARGET, _PHASE_SWAPPED_TARGET}:
    # remove uncommitted target (move to staging or delete)
    # restore backup if exists
```

关键语义对比：
- 旧代码（diff 删除部分）：`PHASE_SWAPPED_TARGET + backup.exists() + target.exists()` → 删除 backup（当作已提交）
- 新代码：`PHASE_SWAPPED_TARGET` → 删除/撤回 new target → 恢复 backup（当作未提交）

这是 plan `R3-C-PF-04` 要求的显式行为反转。

**关键断言**：
- `test_orphan_recovery_follows_journal_commit_point` (:528-554) — parametrize STARTED/BACKED_UP/SWAPPED/COMMITTED，只有 COMMITTED 保留 "new"，其余恢复 "old"。
- `test_swapped_target_recovery_without_old_target_deletes_new_target` (:557-581) — 原状态不存在时 SWAPPED_TARGET 删除 new target 且 target 保持不存在。

**结论**：✅ SWAPPED_TARGET recovery 语义已正确反转，crash-between-swap-and-COMMITTED 测试覆盖。

### 5. commit+rollback 双错误传播

**走读路径**：

`commit_batch()` exception handler (:268-285)：

```python
except Exception as commit_error:
    rollback_error: Exception | None = None
    try:
        self._rollback_precommit_batch(token)
    except Exception as exc:
        rollback_error = exc
    self._invalidate_company_meta_caches()
    if rollback_error is not None:
        commit_error.add_note("commit_batch rollback failed; journal/backup/staging recovery evidence retained")
        Log.warn(...)
        raise commit_error from rollback_error   # primary=commit_error, __cause__=rollback_error
    Log.warn(...)
    raise                                         # rollback succeeded, re-raise original commit_error
```

关键传播形状：
- primary exception = 原 commit error
- `__cause__` = rollback error
- `add_note()` 标记 evidence retained
- journal/backup/staging 物理证据不清理

**关键断言**：
- `test_commit_and_rollback_failure_preserve_primary_cause_and_recovery_evidence` (:452-525)：
  - `exc_info.value is commit_error`（primary）
  - `exc_info.value.__cause__ is rollback_error`
  - `"recovery evidence retained"` in `__notes__`
  - `token.journal_path.exists()` / `token.backup_dir.exists()` / `token.staging_root_dir.exists()`
  - `token.target_ticker_dir` 有 "new" 内容（rollback 失败后保留，供 recovery）

**结论**：✅ 双错误传播形状与 plan `R3-C-PF-05` 完全一致，测试按异常对象身份断言 primary/`__cause__`/note/evidence。

### 6. LocalFileStore — unique temp / fsync / replace / cleanup

**走读路径**：

`put_object()` (`local_file_store.py:66-95`)：

```text
_normalize_object_key(key) → _resolve_normalized_key → mkdir parent
temp_path = .{name}.{uuid4().hex}.tmp     # UUID 避免 .part 冲突
try:
    write chunks → stream.flush() → os.fsync(file_fd)
    os.replace(temp_path, path)            # 原子替换
    _fsync_directory(path.parent)          # 目录元数据刷新
finally:
    temp_path.unlink(missing_ok=True)      # 异常清理
```

关键变化：
- 旧：固定 `.part` 名 → 同 key 并发冲突风险；无 fsync；无 finally temp cleanup
- 新：UUID temp → 同目录唯一 → 无 `.part` 冲突；file fsync → replace → dir sync；finally temp cleanup

**关键断言**：
- `test_local_file_store_put_orders_file_sync_replace_and_directory_sync` (:752-846) — spy `os.fsync`/`os.replace`/`_fsync_directory` 确认顺序：`file_fsync → replace → directory_sync`，两次 put 使用不同 UUID temp，sha256 不同。
- `test_local_file_store_put_failure_preserves_old_object_and_cleans_temp` (:849-885) — parametrize fsync/replace 失败，断言旧 object 内容不变，无 `.tmp` 残留。

**结论**：✅ 满足 plan 的 UUID temp、fsync-before-replace、replace-before-dir-sync、exception temp cleanup 全部 contract。

### 7. 测试覆盖 plan required assertions

**覆盖矩阵**（对照 plan S1 Required assertions 行 258-268）：

| Plan required assertion | 测试覆盖 |
|---|---|
| 参数化非法 component 矩阵（空/空白/`.`/`..`/`a/b`/`a\b`） | `test_single_component_owners_reject_invalid_values` (:58-81) — 4 normalizers × 7 values |
| absolute/leading-slash/`..` segment/backslash/empty segment object key 和越界 `local://` URI 全部 fail closed | `test_local_file_store_rejects_invalid_object_keys_without_external_writes` (:84-115)、`test_local_uri_owner_rejects_invalid_keys` (:117-146) |
| Source/Processed 不存在时 store 均失败，FileStore 调用 0 次 | `test_store_file_requires_source_or_processed_meta_before_file_store_call` (:198-266) |
| valid dot/hyphen ticker 与普通文件名 round-trip | `test_valid_dot_hyphen_identity_and_object_key_round_trip` (:173-195) |
| 每 phase pre-commit 失败：旧 target 恢复/保持不存在，token 关闭，无 staging | `test_each_precommit_failure_restores_original_observable_state` (:350-449) — 5 points × (old_exists/not) = 9 cases |
| orphan recovery: STARTED/BACKED/SWAPPED 回滚，COMMITTED 保留 target | `test_orphan_recovery_follows_journal_commit_point` (:528-554) — 4 phases |
| crash-between-swap-and-COMMITTED 语义反转 | `test_swapped_target_recovery_without_old_target_deletes_new_target` (:557-581) — 原状态不存在时 new target 删除 |
| commit+rollback 双失败: primary/`__cause__`/note/evidence | `test_commit_and_rollback_failure_preserve_primary_cause_and_recovery_evidence` (:452-525) |
| post-commit cleanup 失败不改变成功返回 | `test_postcommit_cleanup_failure_returns_success_and_recovery_cleans_evidence` (:584-637) |
| object write 失败清 temp 且旧 object 不变 | `test_local_file_store_put_failure_preserves_old_object_and_cleans_temp` (:849-885) |
| COMMITTED journal parent-directory sync | `test_committed_journal_write_syncs_parent_directory` (:640-703) |
| 关键 rename parent sync | `test_commit_critical_directory_renames_sync_both_parents` (:706-749) |

所有 plan required assertions 均有对应测试，且测试使用真实 filesystem state（临时目录内容、文件存在性）而非仅 mock 调用次数断言。

**结论**：✅ 71 个测试覆盖全部 plan required assertions，使用 owner-level seam（按 phase/path 的 `_replace_directory` 和 `_write_batch_journal` monkeypatch），符合 plan `R3-C-PF-07` 要求。

---

## Additional Review Dimensions

### pyright / docstring / README

- **pyright**: `0 errors, 0 warnings, 0 informations`（controller validation 确认）
- **docstring**: 所有新增函数（`_normalize_path_component`、`_normalize_filename`、`_normalize_object_key`、`_replace_directory`、`_remove_directory`、`_rollback_precommit_batch`、`_cleanup_committed_batch`、`_resolve_normalized_key`、`_build_normalized_uri`）均提供完整中文 docstring，含 Args/Returns/Raises。既有函数 docstring 同步更新反映新行为。
- **README**: 按 `R3-C-PF-09` 正确延后到全部三个 slice land 后。S1 不提前修改 README。✅

### Fins→Host import boundary

- `rg -n 'from dayu\.host|import dayu\.host' dayu/fins --glob '*.py'` 仅命中既有 `wait_adapter.py`（S3 将处理）。S1 未新增 Fins→Host import。✅

### Tool-security exclusion

- `rg -n 'allowlist|file.authority|symlink.safe|SSRF|byte.budget|security.schema|tool.security'` 在 S1 生产代码和测试中零命中。
- symlink containment 测试（`test_local_uri_owner_rejects_symlink_escape`、`test_local_file_store_rejects_symlink_key_escape`）是 storage identity 测试，验证 `local://` URI 和 object key 在 storage root 内的路径 containment，不是 upload source authority 或远端 egress policy。
- 无 LLM-facing prompt/schema/tool schema 修改。
- ✅ 工具安全边界干净，无 scope creep。

### 既有 regression

- `pytest tests/fins -q`：`491 passed, 1 skipped, 3 warnings`。skip 和 warnings 均为既有环境/依赖行为（`edgar` deprecated modules），非 S1 引入。
- `pytest tests/fins/test_fins_storage_atomicity.py tests/fins/test_fins_storage_provider.py -q`：`118 passed, 3 warnings`。

---

## Findings

未发现实质性问题。

经过以下路径的逐行走读，未发现 correctness、stability、contract ownership 或 regression 风险：

- `_normalize_path_component` 的完整校验链（空/`.`/`..`/分隔符/绝对路径/Windows 盘符）
- 所有 identity owner 到同一真源的收敛
- `_normalize_object_key` 的多组件分段校验与 `/` 拼接
- `_local_path_from_uri` 的 `path.relative_to()` 硬 containment
- `store_file()` 的 Source/Processed 统一 handle existence check
- `commit_batch` 的完整状态机转换（BACKED_UP → SWAPPED → COMMITTED → cleanup）
- `_rollback_precommit_batch` 的 target→staging 撤回、backup 恢复、ROLLED_BACK journal、staging 清理
- `_cleanup_committed_batch` 的 best-effort cleanup 与异常不改变已提交状态
- orphan recovery 中 `SWAPPED_TARGET` 的语义反转（撤回 new target → 恢复 backup）
- dual error 的 `raise commit_error from rollback_error` + `add_note` + evidence retention
- `LocalFileStore.put_object` 的 UUID temp → file fsync → atomic replace → dir sync → finally cleanup
- `_write_json` 的 finally temp unlink（`missing_ok=True`），消除 replace 成功后误删正式文件的担忧（`os.replace` 原子重命名后 temp_path 不再存在）
- `_replace_directory` 的 `os.replace`（同 filesystem 原子 rename）+ source/target parent fsync
- 所有 71 个测试对真实 filesystem state 的断言

---

## Open Questions

无。

---

## Residual Risk

| Risk | Classification | Owner / destination |
| --- | --- | --- |
| `rollback_batch` (caller-initiated) 仍使用裸 `shutil.rmtree` 而非 `_remove_directory`，不刷新 parent directory | accepted — `rollback_batch` 丢弃的是未提交 staging，不是 commit 持久化关键路径；plan 仅对 commit path 要求 journal/rename dirsync | 当前实现；若后续要求统一 dirsync 可改 `_remove_directory` |
| directory fsync 在不支持平台为 best-effort | accepted — 复用既有 `_fsync_directory` best-effort 策略 | Fins filesystem backend portability WU |
| S2/S3 的 token lifecycle、CN/HK temp contract、wait adapter 迁移 | covered by later approved slices | R3-C S2 / R3-C S3 |

---

## Final Review Conclusion

**Status: pass**

**Findings count: 0**

**Blocking questions: 0**

S1 实现严格遵循 accepted plan 的所有 contract：
- single-component/object-key/local URI identity 正确收敛到 `_fs_storage_utils` 单一真源
- Source/Processed handle existence 统一校验
- COMMITTED 是唯一提交点，journal 使用完整 atomic JSON + dir sync
- SWAPPED_TARGET recovery 语义已正确反转
- 双错误传播使用 `raise commit_error from rollback_error` + `add_note` + evidence retention
- LocalFileStore 使用 UUID temp、file fsync、atomic replace、dir sync、finally cleanup
- 71 个 owner-level 测试覆盖全部 plan required assertions，使用真实 filesystem state 断言
- pyright 零错误、docstring 完整、README 按 PF-09 延后
- 工具安全边界干净，无 scope creep

实现已满足 code-generation-ready 的 S1 标准，可进入 per-slice review adjudication。
