# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S1 Code Review

## Scope

- Mode: current changes (uncommitted S1 diff)
- Branch: `phaseflow/host-issues-control`
- Base: working tree diff (unstaged)
- Reviewer: AgentMiMo
- Generated: `20260713-001020`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-mimo.md`

### Included scope

Production files (S1 allowed set):
- `dayu/fins/storage/_fs_storage_utils.py` — single-component/object-key/local-URI validators, `_write_json` temp cleanup
- `dayu/fins/storage/_fs_storage_infra.py` — commit_batch, rollback, orphan recovery, directory helpers
- `dayu/fins/storage/_fs_blob_core.py` — handle existence, filename normalization
- `dayu/fins/storage/local_file_store.py` — put_object atomicity, key normalization
- `dayu/fins/storage/repository_protocols.py` — docstring contract enrichment

Test files:
- `tests/fins/test_fins_storage_atomicity.py` — 71 new owner-level tests (new file)

Reference:
- `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-implementation-codex.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-controller-validation.md`
- Accepted plan: `docs/host/wu-semantic-ownership-01-round3-r3-c-fins-storage-atomicity-plan.md`

### Excluded scope

S2/S3 production files, upload/download workflows, Host/Service wait adapter, Engine, README, design/control docs, tool schema, prompts.

### Parallel review coverage

无。单人全量审查 S1 diff。

---

## Findings

### 001-未修复-低-`_replace_directory` 不防御性校验 target 是否已存在

- **入口/函数**: `_FsStorageInfra._replace_directory(source, target)`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_infra.py:293-313`
- **输入场景**: 任何调用者在 target 目录已存在时调用 `_replace_directory`
- **实际分支**: `_replace_directory` 直接调用 `os.replace(source, target)`，不检查 `target.exists()`
- **预期行为**: docstring 声明 `target` 为"尚不存在的目标目录"；若 target 已存在，函数应 fail closed
- **实际行为**: 在 POSIX 上，若 target 是文件会被静默覆盖；若 target 是非空目录，`os.replace` 抛 `OSError`；若 target 是空目录，行为取决于 OS。调用者违反 contract 时可能静默丢失数据
- **直接证据**: `dayu/fins/storage/_fs_storage_infra.py:310` — `os.replace(source, target)` 无前置 `target.exists()` 检查
- **影响**: 当前调用者均尊重 contract（target 不存在），实际无数据丢失风险。但作为 storage owner 的内部 helper，缺少防御性校验意味着未来调用者错误可能导致静默数据覆盖
- **建议改法和验证点**: 在 `os.replace` 前增加 `if target.exists(): raise OSError(f"replace 目标已存在: {target}")`。验证点：测试 `_replace_directory(target_exists=True)` 抛 `OSError`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-未修复-低-`_normalize_object_key` 未在测试文件中显式导入直接测试

- **入口/函数**: `_normalize_object_key(key)`
- **文件(行号)**: `dayu/fins/storage/_fs_storage_utils.py:140-166`
- **输入场景**: 测试验证对象 key 校验行为
- **实际分支**: 测试文件 `test_fins_storage_atomicity.py:40-46` 导入了 `_normalize_document_id`、`_normalize_entry_name`、`_normalize_filename`、`_normalize_ticker`，但未导入 `_normalize_object_key`
- **预期行为**: Plan 的 S1 Required assertions 要求验证"absolute/leading-slash、`..` segment、backslash、empty segment object key"；测试应显式覆盖 `_normalize_path_component` 和 `_normalize_object_key`
- **实际行为**: `_normalize_object_key` 通过 `test_local_file_store_rejects_invalid_object_keys_without_external_writes` 间接测试（经由 `LocalFileStore.put_object` 调用链）。`_normalize_path_component` 通过四种 normalizer 的参数化测试间接覆盖。功能覆盖完整，但无直接导入
- **直接证据**: `tests/fins/test_fins_storage_atomicity.py:40-46` — import list 无 `_normalize_object_key`；`:88-114` — 通过 `LocalFileStore.put_object` 间接测试
- **影响**: 功能覆盖无缺口。但直接导入测试可在 normalizer 重构时提供更精准的回归信号
- **建议改法和验证点**: 在测试文件 import 区增加 `from dayu.fins.storage._fs_storage_utils import _normalize_object_key`，可选增加一个直接参数化测试。验证点：import 存在且测试通过
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## Tool-Security Boundary Verification

独立验证 S1 未误加工具安全实现：

| 检查项 | 结果 |
|---|---|
| upload allowlist / explicit user-file authority / symlink-safe upload source policy | 未添加。`_local_path_from_uri` 和 `LocalFileStore` 的 symlink containment 是 storage identity 校验，不是 upload source authority |
| URL / TLS / redirect / SSRF provenance policy | 未添加。`rg -n 'allowlist\|symlink-safe\|SSRF\|byte-budget\|tool.schema\|TLS\|redirect' dayu/fins/storage/ tests/fins/test_fins_storage_atomicity.py` 无匹配 |
| remote download byte-budget policy | 未添加。S1 不涉及网络 I/O |
| LLM-facing security schema / prompt / tool schema changes | 未添加。S1 不修改 `dayu/config/prompts/`、tool schema 或 provider |

Storage `local://` containment 校验（`_local_path_from_uri` 的 `relative_to` 检查、`_resolve_normalized_key` 的越界检查）属于 storage identity 范畴，不构成 upload security 实现。

**结论**: S1 无工具安全 scope drift。

---

## Plan Compliance Summary

### S1 allowed file scope

5 个 production 文件均在 plan S1 allowed set 内。新增测试文件 `tests/fins/test_fins_storage_atomicity.py` 在 plan S1 allowed test files 内。`tests/fins/test_fins_storage_provider.py` 未修改。未触碰 S2/S3 文件。

### Single-component / object-key / local URI ownership

- `_normalize_path_component` 作为 single source of truth，ticker/document-id/entry-name/filename 四个 normalizer 均复用它
- `_normalize_object_key` 多组件 key 校验拒绝空 key、leading slash、backslash、empty segment、`..` segment
- `_local_path_from_uri` 复用 `_normalize_object_key` 并增加 `portfolio_root` containment check
- `LocalFileStore._resolve_normalized_key` 复用 `_normalize_object_key` 并增加 `root` containment check
- `_build_store_key_from_normalized_filename` 接受已校验 filename，不重复校验

### Source / Processed handle existence

`_FsBlobMixin.store_file()` 对两类 handle 无条件调用 `_get_handle_meta()` 确认存在，然后才构造 key 或调用 FileStore。测试 `test_store_file_requires_source_or_processed_meta_before_file_store_call` 断言 FileStore call count 为 0。

### commit_batch COMMITTED 唯一提交点

`commit_batch` 流程：backup → BACKED_UP_TARGET journal → staging→target rename → SWAPPED_TARGET journal → cache invalidate → COMMITTED journal。COMMITTED 是唯一 commit point。之后 `_cleanup_committed_batch` 做 best-effort backup/staging cleanup，失败只 log 不抛。测试 `test_postcommit_cleanup_failure_returns_success_and_recovery_cleans_evidence` 验证 cleanup failure 不影响成功返回。

### SWAPPED_TARGET before COMMITTED recovery 语义反转

Orphan recovery 对 `BACKED_UP_TARGET` / `SWAPPED_TARGET`：先移除未提交 target（移回 staging 或直接删除），再恢复 backup。与旧行为（保留 target、删除 backup）相反。测试 `test_orphan_recovery_follows_journal_commit_point` 和 `test_swapped_target_recovery_without_old_target_deletes_new_target` 覆盖 old-target-present 和 old-target-absent 两种场景。

### commit + rollback 双错误传播

`commit_batch` 的 `except` 块：先尝试 `_rollback_precommit_batch`；若 rollback 也失败，`commit_error.add_note("...recovery evidence retained")` 并 `raise commit_error from rollback_error`。测试 `test_commit_and_rollback_failure_preserve_primary_cause_and_recovery_evidence` 按对象身份断言 `exc_info.value is commit_error`、`exc_info.value.__cause__ is rollback_error`、note 包含 "recovery evidence retained"，且 journal/backup/staging 证据未被清理。

### Journal / rename dir sync

- `_replace_directory`：`os.replace` 后 `_fsync_directory(source_parent)`，不同 parent 时也 `_fsync_directory(target_parent)`
- `_write_json`：file fsync → `os.replace` → `_fsync_directory(path.parent)`，`finally` 清理 temp
- COMMITTED journal 写入复用 `_write_json` 的完整 atomic JSON + dir sync 模式
- 测试 `test_committed_journal_write_syncs_parent_directory` 和 `test_commit_critical_directory_renames_sync_both_parents` 通过 spy 断言 parent directory 被 sync

### LocalFileStore unique temp / fsync / replace / cleanup

- UUID temp file（`.{name}.{uuid}.tmp`）
- `stream.flush()` + `os.fsync(fileno())` 在 replace 前
- `os.replace(temp, path)` 原子替换
- `_fsync_directory(path.parent)` 在 replace 后
- `finally: temp_path.unlink(missing_ok=True)` 清理
- 测试 `test_local_file_store_put_orders_file_sync_replace_and_directory_sync` spy 断言 file_fsync → replace → directory_sync 顺序
- 测试 `test_local_file_store_put_failure_preserves_old_object_and_cleans_temp` 断言 fsync/replace 失败后旧 object 不变且 temp 已清理

### 测试覆盖 plan required assertions

| Plan required assertion | Test coverage |
|---|---|
| 非法 component 矩阵：`""`、空白、`.`、`..`、`a/b`、`a\\b` | `test_single_component_owners_reject_invalid_values` — 4 normalizer × 7 values = 28 cases |
| absolute/leading-slash、`..` segment、backslash、empty segment object key | `test_local_file_store_rejects_invalid_object_keys_without_external_writes` — 8 values |
| 越界 `local://` URI | `test_local_uri_owner_rejects_invalid_keys` — 7 values + `test_local_uri_owner_rejects_symlink_escape` |
| Source/Processed missing handle 时 FileStore call count 为 0 | `test_store_file_requires_source_or_processed_meta_before_file_store_call` — 2 handles |
| valid dot/hyphen ticker round-trip | `test_valid_dot_hyphen_identity_and_object_key_round_trip` |
| 每个 pre-commit phase failure 恢复 | `test_each_precommit_failure_restores_original_observable_state` — 5 phases × 2 states = 10 cases |
| SWAPPED_TARGET recovery 语义反转 | `test_orphan_recovery_follows_journal_commit_point` + `test_swapped_target_recovery_without_old_target_deletes_new_target` |
| commit + rollback 双错误对象身份 / note / `__cause__` / evidence | `test_commit_and_rollback_failure_preserve_primary_cause_and_recovery_evidence` |
| post-COMMITTED cleanup failure 成功返回 | `test_postcommit_cleanup_failure_returns_success_and_recovery_cleans_evidence` |
| COMMITTED journal parent directory sync | `test_committed_journal_write_syncs_parent_directory` |
| critical directory rename parent sync | `test_commit_critical_directory_renames_sync_both_parents` |
| LocalFileStore fsync/replace/dir-sync 顺序 | `test_local_file_store_put_orders_file_sync_replace_and_directory_sync` |
| LocalFileStore 失败保留旧 object + temp cleanup | `test_local_file_store_put_failure_preserves_old_object_and_cleans_temp` |
| LocalFileStore stat/list/delete/missing/symlink | `test_local_file_store_read_stat_list_delete_and_missing_contract` + `test_local_file_store_rejects_symlink_key_escape` |

### pyright / docstring / README 决策

- pyright: `0 errors, 0 warnings, 0 informations`（已验证）
- docstring: 所有新增/修改函数提供完整中文 docstring（Args/Returns/Raises）
- README: 延后至 S1+S2+S3 全部 land 后统一同步（符合 R3-C-PF-09）

---

## Open Questions

无。

## Residual Risk

| Risk | Classification | Owner / destination |
|---|---|---|
| `_replace_directory` 不防御性检查 target 已存在 | low — 当前调用者均遵守 contract | 可选增强，不阻塞 S1 |
| directory fsync 在不支持的 platform 采用 best-effort | accepted — 既有策略 | Fins filesystem backend portability WU |
| S2/S3 caller token lifecycle 与单 document mutation | covered by mandatory next slice | R3-C S2 |
| Fins -> Host reverse import relocation | covered by mandatory next slice | R3-C S3 |

---

## Final Code Review Conclusion

**Status: pass-with-risks**

S1 实现与 accepted plan 高度对齐：single-component validator 复用、handle existence check、COMMITTED 唯一提交点、SWAPPED_TARGET recovery 语义反转、commit+rollback 双错误传播、journal dir sync、LocalFileStore 原子落盘均已落地。71 个新增测试覆盖 plan 全部 required assertions，使用真实临时目录和 filesystem state 断言。pyright 零报错。无工具安全 scope drift。

两个低严重度 finding 均为可选增强，不阻塞 S1 进入 code review adjudication。

## Completion Report

- **status**: pass-with-risks
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-mimo.md`
- **findings count**: 2
- **blocking questions count**: 0
