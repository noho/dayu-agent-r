# Code Review — WU-CLI-INIT-01 S4

## Scope

- Mode: current changes
- Branch: `ci/pr-179-first-ci-readiness`
- Base: `main` (S1–S3 已提交基线 `cf72af5d`)
- Output file: `docs/reviews/wu-cli-init-01-s4-code-review-ds.md`
- Accepted scope plan: `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-codex.md`
- Goal boundary: `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- Implementation artifact: `docs/reviews/wu-cli-init-01-s4-implementation-codex.md`
- Review timestamp: 2026-07-30T18:00:49+08:00
- Included scope (5 tracked diffs):
  - `dayu/cli/commands/init.py`
  - `dayu/cli/init_workspace.py`
  - `tests/cli/test_init_command.py`
  - `tests/cli/test_init_workspace.py`
  - `tests/cli/test_init_smoke.py`
- Excluded scope:
  - 3 untracked amendment-2 artifacts（按用户明确要求忽略且不修改）
  - `dayu/runtime/config_loader.py`、`tests/runtime/test_config_loader.py`（revert-only，已确认零 diff）
  - MiMo review（按用户要求不读取）
- Parallel review coverage: 无

## Verification Summary

| 检查项 | 结果 |
|---|---|
| revert-only files (`config_loader.py` / `test_config_loader.py`) 零 diff | `git diff --exit-code HEAD` → exit 0 ✅ |
| fd reader / `_WorkspaceProfileDescriptorState` 残留 | 零残留 ✅ |
| `_descriptor_stable_state` / `st_ctime_ns` / `st_nlink` 残留 | 零残留 ✅ |
| `_PrivatePathShape` / typed filename manifest 残留 | 零残留 ✅ |
| snapshot/bytes loader API 残留 | 零残留 ✅ |
| `errno` import in init.py | 不存在 ✅ |
| `config_file_names` import in init.py | 不存在 ✅ |
| `backup_records` 3-tuple 保持不变 | `tuple[ManagedRootSnapshot, Path, PathIdentity]` ✅ |
| `_rollback_or_raise` signature/net diff | 无净 diff ✅ |
| `_post_publication_cleanup` 无 `expected_shape` 参数 | 签名未变 ✅ |
| `_roots_replaced_by_mode` 无修改 | HEAD 行为 ✅ |
| symlink/special/lock 拒绝 contract | 维持现有拒绝，未扩大 ✅ |

## Findings

未发现实质性问题。

### 逐合约验证

以下按用户指定的 8 个重点审项逐一报告 evidence 与结论。

#### 1. Correctness（整体正确性）

**PRESERVE 补缺链路**（`init_workspace.py:866-873`）：
- `_build_staged_config` 在 PRESERVE 分支中先 `copytree` 用户 tree，再调用 `_copy_missing_root_config_files`，最后调用 `_copy_missing_prompt_files`。
- `_copy_missing_root_config_files`（`init_workspace.py:922-957`）遍历 `config_file_names()`，仅当 `destination.exists() or destination.is_symlink()` 时跳过，对真正缺失项从 package source 做 `shutil.copy2`。
- 已存在文件 zero-touch（line 940: `continue`）。
- 链路顺序保证 model selection owner（`apply_model_selection` / `project_known_manifest_models`）在补缺完成后运行，只修改自己 owner 字段。

**OVERWRITE/RESET ordinary-file root recovery**（`init_workspace.py:346-375`）：
- `snapshot_managed_roots` 在 `stat.S_ISREG(identity.mode)` 时按 `repair_mode` 精确分派：RESET 接受两者，OVERWRITE 只接受 `config`。
- `regular_file_owned_by_mode` 布尔表达式（line 347-352）逻辑正确：RESET 短路求值为 True；OVERWRITE 仅在 `root_name == _CONFIG_ROOT_NAME` 时为 True。
- Regular file 的 Windows reparse 仍被拒绝（line 359-366）。
- 非 owned regular file 以 `"path must be an ordinary directory"` 拒绝，error message 语义准确。

**Cleanup identity dispatch**（`init_workspace.py:1389-1461`）：
- identity check（`actual_identity != expected_identity`）在类型分派之前执行（line 1383-1388），保证 `actual_identity == expected_identity` 时 `expected_identity.mode` 即 actual mode。
- Regular file 路径：检查 Windows reparse → quarantine → unlink；directory 路径：`_require_ordinary_directory` → quarantine → capability gate → rmtree。
- Unlink 失败（包括 `KeyboardInterrupt`）以 typed `InitWorkspaceError` 上报，携带 quarantine retained path（line 1453-1460）。

**Repair mode 有效性**（`init.py:402-415` / `init_workspace.py:301-305`）：
- `_requested_repair_mode` 的正确性：`reset > overwrite > None`，与 `determine_init_mode` 的 `RESET > OVERWRITE > config existence` 一致。
- `snapshot_managed_roots` 入口校验 `repair_mode not in (None, InitMode.OVERWRITE, InitMode.RESET)`，拒绝 `FIRST`/`PRESERVE` 等非法传入。

#### 2. Semantic owner（语义所有权）

每个业务事实的 owner 未漂移：

| 事实 | Owner | 本次是否遵守 |
|---|---|---|
| 五类根配置文件名 | `dayu.runtime.config_loader.config_file_names()` | 仅消费，不重复定义 ✅ |
| CLI destructive flags → repair intent | `dayu.cli.commands.init._requested_repair_mode` | 新增单一投影函数 ✅ |
| Managed-root snapshot admission | `dayu.cli.init_workspace.snapshot_managed_roots` | 在既有 owner 内新增 regular file 分支 ✅ |
| PRESERVE staging 内容 | `dayu.cli.init_workspace._build_staged_config` | 在既有 owner 内插入补缺调用 ✅ |
| 模型字段投影 | `apply_model_selection` / `project_known_manifest_models` | 未修改，补缺 helper 不碰这些字段 ✅ |
| Publication/rollback | 既有 `publish_workspace_transaction` / `_rollback_or_raise` | 未修改 ✅ |
| File-vs-directory cleanup 分派 | `_cleanup_private_path` 以 `expected_identity.mode` 为真源 | 直接派生，不新增 type/shape ✅ |
| Execution profile loading | `_load_target_min_context_window` 保持 path-loader contract | 未引入 snapshot/fd reader ✅ |

没有发现 fallback、特例、`hasattr`/`getattr`、loose parsing、重复计算或下游补偿上游 contract 的语义漂移。

#### 3. PRESERVE 已有内容是否真保留

证据链：

1. `_build_staged_config` PRESERVE 分支先 `shutil.copytree(public_config, staged_config_root, symlinks=True)`（line 864-868），完整复制用户 config tree。
2. `_copy_missing_root_config_files` 仅当 `destination.exists() or destination.is_symlink()` 为 False 时才写入（line 940）；已存在文件 bytes 完全不被读取或修改。
3. `_copy_missing_prompt_files` 同样仅补缺失项。
4. 测试 `test_preserve_staging_copies_each_missing_root_config_only` 对五个 `config_file_names()` 逐项证明：缺失文件被补齐、其它根配置 bytes 不变（`test_init_workspace.py:386-421`）。
5. 真实 POSIX smoke `test_posix_real_four_state_config_scene_and_reset_sentinels` 通过完整 CLI 证明：`user_file`、`user_manifest` 在 PRESERVE 后内容不变，缺失的 `tool_discovery.json` 和 `fact_rules.md` 从 package source 补齐（`test_init_smoke.py:1426-1434`）。

结论：PRESERVE 保留所有已有用户内容，仅补真正缺失的 managed config 文件。

#### 4. OVERWRITE/RESET ordinary-root ownership

**OVERWRITE**（`init_workspace.py:347-352`）：
- 只接受 `config` regular file（`repair_mode is InitMode.OVERWRITE and root_name == _CONFIG_ROOT_NAME`）。
- `.dayu` regular file + OVERWRITE 被拒绝：测试 `test_ordinary_file_roots_follow_explicit_mode_ownership` line 467-475 证明。
- OVERWRITE 后 config 从 package whole-tree 重建，`.dayu` 内容/identity 保留：测试 line 456-465 证明。

**RESET**（`init_workspace.py:347-348`）：
- 接受 `config` 和 `.dayu` regular files（`repair_mode is InitMode.RESET` 直接通过）。
- RESET 后旧 `.dayu` 被清除、config 从 package 重建、portfolio/assets 保留：测试 line 498-517 证明。

**无 flag**：
- Ordinary regular file 无 repair intent 时被拒绝：测试 line 435-439 证明。

真实 POSIX smoke `test_posix_real_ordinary_root_overwrite_reset_matrix` 通过完整 CLI 子进程证明上述全部（`test_init_smoke.py:1478-1542`）。

#### 5. Cleanup identity（file-vs-directory 分派正确性）

`_cleanup_private_path`（`init_workspace.py:1352-1484`）的分派逻辑：

1. Identity 复核（line 1383-1388）：`actual_identity != expected_identity` 时 raise，保证后续 `expected_identity.mode` 即 actual mode。
2. 类型分派（line 1389-1405）：`stat.S_ISREG(expected_identity.mode)` 时走 regular file 分支（仅检查 Windows reparse），否则走 directory 分支（调用 `_require_ordinary_directory`）。
3. 删除分派（line 1452-1461）：`stat.S_ISREG(expected_identity.mode)` → `os.unlink(quarantine)`；else → capability gate + `shutil.rmtree(quarantine)`。
4. `os.unlink` 和 `shutil.rmtree` 的失败均以 typed `InitWorkspaceError` 上报，携带准确的 retained_path。

测试 `test_cleanup_dispatches_regular_file_to_unlink_and_directory_to_rmtree`（`test_init_workspace.py:591-646`）通过 Mock 包装真实 `os.unlink` 与 `shutil.rmtree` 证明：
- Regular file → unlink 被调用、rmtree 未被调用。
- Directory → rmtree 被调用。
- 两者最终均不存在。

边界情况检查：
- 若 `expected_identity.mode` 既非 regular file 也非 directory（如 FIFO/socket），`_require_ordinary_directory` 会拒绝 → ✅。
- Symlink 已在 `_path_identity` 层面被 `os.stat(path, follow_symlinks=False)` 捕获 → ✅。

#### 6. Rollback loop 无漂移

逐项对比 `cf72af5d` HEAD 与当前 working tree：

| 元素 | HEAD | 当前 | 漂移？ |
|---|---|---|---|
| `backup_records` 类型 | `list[tuple[ManagedRootSnapshot, Path, PathIdentity]]` | 同左 | 无 ✅ |
| backup record append | `(root_snapshot, backup_path, backup_identity)` | 同左 | 无 ✅ |
| `_rollback_or_raise` 签名 | `(prepared, *, backup_records, published_config)` | 同左 | 无 ✅ |
| rollback restore loop | `for root_snapshot, backup_path, backup_identity in reversed(backup_records): os.replace(backup_path, root_snapshot.path)` | 同左 | 无 ✅ |
| `_roots_replaced_by_mode` | RESET → all roots, else → config only | 同左 | 无 ✅ |
| `_post_publication_cleanup` 签名 | 无 `expected_shape` | 同左 | 无 ✅ |
| rollback stage prefix | `f"rollback_{exc.stage}"` | 同左 | 无 ✅ |

既有 rollback tests 全部通过（implementation artifact 记录）：
- `test_publication_replace_failure_rolls_back_original_config`
- `test_publication_replace_fault_matrix_restores_snapshot`
- `test_reset_each_root_backup_fault_restores_both_roots`
- `test_posix_publication_sync_fault_rolls_back`
- `test_posix_rollback_sync_fault_reports_durability_and_current_truth`

结论：rollback loop 对 HEAD 无净 diff；regular file backup 与 directory backup 走同一个 `os.replace` → `_rollback_or_raise` → `os.replace` 恢复路径，无新增 branch/state。

#### 7. Out-of-scope 竞态/loader 代码零残留

按 scope-correction plan §4.2、§5 的禁止清单逐项 grep：

- `_CONFIG_ROOT_NAME` in `init.py`：不存在
- `_WORKSPACE_PROFILE_READ_CHUNK_BYTES`：不存在
- `_FD_RELATIVE_OPEN_SUPPORTED`：不存在
- `_WorkspaceProfileDescriptorState`：不存在
- `_read_workspace_execution_profile_snapshot`：不存在
- `_workspace_profile_descriptor_state`：不存在
- `_close_workspace_profile_descriptors`：不存在
- `ConfigLoader.load_execution_profiles_snapshot`：不存在
- `_descriptor_stable_state`：不存在
- `st_ctime_ns` / `st_nlink`：不存在（整个 codebase 无引用）
- `_PrivatePathShape`：不存在
- typed filename manifest（`ConfigFileNames` NamedTuple）：不存在（`config_loader.py` 已 revert 到 HEAD）
- snapshot/bytes loader API：不存在
- `errno` in `init.py` imports：不存在
- `config_file_names` in `init.py` imports：不存在
- race barrier / threading Event / sleep-retry：不存在
- `_regular_file_digest` 实现（`init_workspace.py:1669-1681`）：普通 `path.open("rb")` + chunked read + SHA-256，无 fstat/ctime/nlink/descriptor pinning → ✅ 符合 plan。

结论：out-of-scope 代码零残留。

#### 8. 测试断言真实 tree 而非自报 mode

逐测试验证断言类型：

| 测试 | 断言方式 |
|---|---|
| `test_preserve_staging_copies_each_missing_root_config_only` | `read_bytes()` 比对 package source ✅ |
| `test_ordinary_file_roots_follow_explicit_mode_ownership` | `is_dir()` + `ConfigLoader().load()` + `read_text()` + `_path_identity()` ✅ |
| `test_corrupt_ordinary_config_requires_explicit_destructive_mode` | `snapshot_managed_roots()` equality + `ConfigLoader().load()` + `read_text()` + `_path_identity()` ✅ |
| `test_cleanup_dispatches_regular_file_to_unlink_and_directory_to_rmtree` | `unlink.call_count` + `rmtree.assert_not_called()` + `not private_file.exists()` ✅ |
| `test_posix_real_four_state_config_scene_and_reset_sentinels` | `read_text()` + `read_bytes()` + `_validate_published_config()` + `_tree_digest()` + `_path_identity()` ✅ |
| `test_posix_real_ordinary_root_overwrite_reset_matrix` | `is_dir()` + `read_text()` + `_path_identity()` + `_validate_published_config()` ✅ |
| `test_locked_target_mode_loads_typed_profile_once_and_passes_minimum` | `snapshot.call_args_list` 断言 repair_mode 传递 ✅ |

无一测试仅依赖 `result.mode` 或 CLI 自报字符串判定成功。

## Open Questions

无。

## Residual Risk

1. **外部进程并发 mutation / TOCTOU**：用户已明确裁决为本 WU out of scope。Classification: `requires new work unit with explicit user decision`。
2. **Windows ordinary-file publication 真实平台 smoke**：当前 Darwin 环境无法执行 Windows 条件测试。跨平台 CI owner 为 `#184`。Classification: `tracked by existing issue`。
3. **根 README 用户文案同步**：由 accepted plan S6 负责。Classification: `covered by later approved slice`。
4. **`_copy_missing_root_config_files` 的 `destination.is_symlink()` 检查**：由于 public config tree 已由 `_validate_ordinary_tree` 拒绝 symlink，该检查在当前流程中总是 False。它作为 defensive check 不产生错误行为，但若未来 copytree 行为变化，该防御可能掩盖 staging tree 被外部污染的 root cause。Classification: `low-severity maintainability note`，不需要当前修改。

## Conclusion

**PASS** — 5 个 tracked diff 全部符合 accepted scope-correction plan 的精确合约。实现 clean、semantic owner 正确、PRESERVE 已有内容真实保留、OVERWRITE/RESET ordinary-root ownership 精确分派、cleanup identity 以 `expected_identity.mode` 为真源、rollback loop 无漂移、out-of-scope 竞态/loader 代码零残留、所有测试断言真实 tree 而非自报 mode。未发现 correctness、stability 或 maintainability 的 material finding。
