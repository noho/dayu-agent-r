# WU-CLI-INIT-01 S4 Code Review

## Scope

- Mode: current changes
- Branch: `ci/pr-179-first-ci-readiness`
- Base: `cf72af5d` (S1–S3 committed baseline)
- Output file: `docs/reviews/wu-cli-init-01-s4-code-review-mimo.md`
- Included scope: 5 tracked code/test diff files + implementation artifact
- Excluded scope: 3 untracked amendment-2 artifacts (per explicit instruction)
- Parallel review coverage: 无

## Reviewed files

| File | Lines changed | Verdict |
|---|---|---|
| `dayu/cli/commands/init.py` | +22 | PASS |
| `dayu/cli/init_workspace.py` | +145/-13 | PASS |
| `tests/cli/test_init_command.py` | +21 | PASS |
| `tests/cli/test_init_workspace.py` | +274/-3 | PASS |
| `tests/cli/test_init_smoke.py` | +73 | PASS |
| `dayu/runtime/config_loader.py` | 0 (revert-only) | PASS — zero diff confirmed |
| `tests/runtime/test_config_loader.py` | 0 (revert-only) | PASS — zero diff confirmed |

## Findings

未发现实质性问题。

以下为逐维度的 evidence-based 审查结论：

### 1. Correctness

**`_requested_repair_mode()` (`init.py:402-415`)**
- 精确投影 `reset=True` → `InitMode.RESET`，`overwrite=True` → `InitMode.OVERWRITE`，否则 `None`。
- RESET > OVERWRITE precedence 与 `determine_init_mode()` 一致。
- 两次 `snapshot_managed_roots()` 调用（lock 前 L128-132、lock 内 L154-158）均传入同一 `repair_mode`。

**`snapshot_managed_roots()` repair_mode 入口校验 (`init_workspace.py:300-305`)**
- `repair_mode not in (None, InitMode.OVERWRITE, InitMode.RESET)` 直接拒绝非法值。
- 对应测试 `test_ordinary_file_roots_follow_explicit_mode_ownership` 的 no-flag 分支覆盖此路径。

**Ordinary-file root ownership 分派 (`init_workspace.py:346-375`)**
- `RESET` 接受 `config` 和 `.dayu` regular file。
- `OVERWRITE` 只接受 `config` regular file。
- `.dayu` regular file + `OVERWRITE` 被拒绝。
- 无 flag 时任何 regular file 被拒绝。
- 以上均由 `test_ordinary_file_roots_follow_explicit_mode_ownership` 的 4 个分支直接覆盖。

**`_copy_missing_root_config_files()` (`init_workspace.py:922-957`)**
- 遍历 `config_file_names()` 五类根配置。
- `destination.exists() or destination.is_symlink()` 跳过已存在项（含 dangling symlink）。
- 缺失时从 package source 复制，source 必须是 ordinary regular file。
- Windows reparse 额外拒绝。
- 对应测试 `test_preserve_staging_copies_each_missing_root_config_only` 参数化 5 个文件名，逐项删除并断言 bytes equality。

**`_require_snapshot_unchanged()` (`init_workspace.py:827-835`)**
- `repair_mode` 传入与 request.mode 一致：`OVERWRITE`/`RESET` 时透传，否则 `None`。
- 确保 lock 前后 snapshot 使用相同的 ordinary-file admission 规则。

### 2. Semantic Owner

| 语义 | Owner | 验证 |
|---|---|---|
| Destructive flags → repair intent | `_requested_repair_mode()` in `commands/init` | 正确 |
| Managed-root snapshot admission | `snapshot_managed_roots()` | 正确 |
| PRESERVE staging 补缺 | `_copy_missing_root_config_files()` in `init_workspace` | 正确 |
| Regular-file content digest | `_regular_file_digest()` | 正确 |
| Cleanup unlink vs rmtree | `_cleanup_private_path()` | 正确 |
| Transaction/rollback | 既有 `_rollback_or_raise()` | 未修改 |

各语义均在正确 owner boundary 实现，无下游 fallback 或重复计算。

### 3. PRESERVE 已有内容是否真保留

- `_copy_missing_root_config_files()` 在 `_build_staged_config()` 的 PRESERVE 分支中，位于 `shutil.copytree()` 之后、`_copy_missing_prompt_files()` 之前调用。
- `copytree(symlinks=True)` 原样复制用户 config tree。
- 补缺 helper 只处理 `destination.exists() or destination.is_symlink()` 为 False 的情况。
- 测试 `test_preserve_staging_copies_each_missing_root_config_only` 断言其它 4 个文件的 bytes 不变。
- Smoke `test_posix_real_four_state_config_scene_and_reset_sentinels` 断言 `user_file`、`user_manifest` 在 PRESERVE 后 bytes 不变。

### 4. OVERWRITE/RESET ordinary-root ownership

- OVERWRITE：`config` ordinary file → 被接受进入 backup/publication → 重建为 directory tree；`.dayu` identity 保留。
- RESET：`config` + `.dayu` ordinary files → 被接受进入 backup/publication/cleanup → `.dayu` 被移除，config 重建；portfolio/assets 保留。
- 测试覆盖：
  - `test_ordinary_file_roots_follow_explicit_mode_ownership`：4 分支 mode matrix。
  - `test_corrupt_ordinary_config_requires_explicit_destructive_mode`：PRESERVE 失败、OVERWRITE/RESET 恢复。
  - Smoke `test_posix_real_ordinary_root_overwrite_reset_matrix`：真实 CLI 全链路。

### 5. Cleanup identity

- `_cleanup_private_path()` 在 identity check 通过后，对 `expected_identity.mode` 分派：
  - `S_ISREG` → `os.unlink(quarantine)`。
  - 否则 → `shutil.rmtree(quarantine)`（POSIX fd-safe capability gate）。
- Windows reparse 额外拒绝。
- 测试 `test_cleanup_dispatches_regular_file_to_unlink_and_directory_to_rmtree` 直接断言 `unlink` 被调用 1 次、`rmtree` 未被调用。

### 6. Rollback loop 无漂移

- `_rollback_or_raise()` 签名、tuple unpacking、restore loop 对 HEAD 无净 diff。
- `backup_records` 保持 3-tuple `tuple[ManagedRootSnapshot, Path, PathIdentity]`。
- `_post_publication_cleanup()` 未增加 `expected_shape` 参数。
- 既有 5 个 rollback tests 全部通过（implementation artifact 记录）。

### 7. Out-of-scope 竞态/loader 代码零残留

- `dayu/runtime/config_loader.py` 对 HEAD 零 diff（已确认）。
- `tests/runtime/test_config_loader.py` 对 HEAD 零 diff（已确认）。
- 无 fd reader、descriptor state、`_WorkspaceProfileDescriptorState`、`_PrivatePathShape`、`st_ctime_ns`、`st_nlink`、typed filename manifest、ConfigLoader snapshot API 残留。
- `init.py` 不 import `errno`、`config_file_names` 或任何 S4 撤销的符号。

### 8. 测试断言真实 tree 而非自报

- `test_preserve_staging_copies_each_missing_root_config_only`：断言 `(staged_config_root / missing_file_name).read_bytes()`。
- `test_ordinary_file_roots_follow_explicit_mode_ownership`：断言 `ConfigLoader().load()`、`_path_identity()`、`portfolio_sentinel.read_text()`。
- `test_corrupt_ordinary_config_requires_explicit_destructive_mode`：断言 `ConfigLoader().load()`、`snapshot_managed_roots()` equality。
- `test_cleanup_dispatches_regular_file_to_unlink_and_directory_to_rmtree`：断言 `unlink.call_count`、`rmtree.call_count`。
- Smoke tests：断言 `_validate_published_config()`（真实 ConfigLoader + Service discovery + scene preparation）、`_path_identity()`、`_tree_digest()`。

无测试依赖 `result.mode` 单独判定成功。

## Open Questions

无。

## Residual Risk

1. **Windows ordinary-file publication 真实平台 smoke**：当前本地 Darwin，Windows 条件测试未在本机执行。分类：`tracked by existing issue`（#184）。
2. **并发文件系统 mutation / TOCTOU**：不属于 accepted S4 contract。分类：`requiring new issue or explicit user decision`。
3. **根 README 用户文案同步**：PRESERVE 根配置补缺使"只补 prompt"文案需更新。分类：`covered by later approved slice`（S6）。

## Conclusion

**PASS**

净生产 diff 只有补缺、repair intent、regular-root snapshot/digest 与最小 cleanup delete dispatch。净测试 diff 只覆盖上述业务结果和一次无 fault 的 owner dispatch。两个 revert-only 文件对 HEAD 零 diff。focused tests、S1–S3 regression、pyright 全部通过。实现完全符合 accepted scope plan。
