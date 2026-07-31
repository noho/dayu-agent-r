# WU-CLI-INIT-01 S4 Scope-Correction Plan Re-review (DS)

## Metadata

- **Review target**: `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-codex.md`（修订版）
- **Goal boundary**: `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- **Reviewer**: AgentDS (Claude Code / DeepSeek)
- **Date**: 2026-07-30
- **HEAD baseline**: `cf72af5d`（已确认未变）
- **Previous review**: `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-review-ds.md`
- **Scope**: Focused rereview — 验证 Goal 合规、复核上一轮 findings 关闭状态

## 上一轮 Finding 关闭状态

### Finding #1 — apply_patch 工具依赖未定义 → CLOSED（Controller 裁决）

Plan §7 末尾已记录：

> Controller 驳回 DS 关于 `apply_patch` 可用性的 finding：Codex 内置 `apply_patch` 已由当前执行环境定义，本计划继续直接使用该工具；不得改成 shell 重定向、`cat`、Python 写文件或其它绕过方式。

证据充分，不再作为 finding。

### Finding #2 — _require_ordinary_directory 松弛未显式说明 → CLOSED（已修正）

Plan §4.3 第 7 点（旧 §4.2 第 7 点）新增显式描述：

> 现有 cleanup 前置 `_require_ordinary_directory(...)` 必须在同一 owner 内调整：只接受 `expected_identity.mode` 派生出的 ordinary regular file 或 ordinary directory；不把这一放宽扩散到其它 directory-only caller；

§6 S4-SC2 Exact production changes 也同步更新：

> `_cleanup_private_path(...)` 在同一 owner 内把 directory-only 前置调整为只接受 expected ordinary regular file或ordinary directory，再直接按既有 `expected_identity.mode` 分派 `os.unlink` / 既有 `shutil.rmtree`；

此外 §4.3 第 8 点还新增约束：

> `_post_publication_cleanup(...)` 的签名及调用不传 `expected_shape`；file-vs-directory 真源只由 `_cleanup_private_path(...)` 直接从既有 `expected_identity.mode` 派生。

前置校验松弛、最终删除分派、不扩散约束三者已完整覆盖。Closed。

## 修订版增量检查

### 新增 §4.2 — Init execution-profile loading 恢复 HEAD contract

本 section 精确列出需要从 `commands/init.py` 删除的 fd reader 基础设施：

- 类：`_WorkspaceProfileDescriptorState`
- 常量：`_CONFIG_ROOT_NAME`、`_WORKSPACE_PROFILE_READ_CHUNK_BYTES`、`_FD_RELATIVE_OPEN_SUPPORTED`
- helpers：`_read_workspace_execution_profile_snapshot(...)`、`_workspace_profile_descriptor_state(...)`、`_close_workspace_profile_descriptors(...)`
- import：`errno`、`config_file_names`（来自 config_loader 的新增 import）
- 调用：`ConfigLoader.load_execution_profiles_snapshot(...)`
- 恢复：`ConfigLoader.load_execution_profiles(workspace_config_dir=...)` 的 HEAD path-based 调用约定

**验证结论**：纯防御性 revert，不引入新语义。删除的正是 partial implementation 中与 loader snapshot/descriptor 相关的越界增量，与 Goal 的 "无 loader snapshot API" 裁决一致。没有新增风险。

### 修订版 Goal 合规复查

| Goal 要求 | Plan 位置 | 覆盖状态 |
|---|---|---|
| preserve 保留用户内容、补齐缺失 managed files，只更新模型选择 owner 字段 | §4.1, §4.4 | 覆盖 |
| overwrite 最终 config tree 与 package manifest + 模型投影一致，旧 sentinel 消失，`.dayu` 保留 | §4.3, §4.5 | 覆盖 |
| reset 默认 No；确认后 `.dayu` 与 init-owned roots 重建，portfolio 与非 init-owned assets 保留 | §4.3, §4.6 | 覆盖 |
| ordinary partial/corrupt state 可通过 preserve/overwrite/reset 恢复 | §1.2, §4.3, §4.4-4.6 | 覆盖 |
| symlink、special file、非法 lock identity 继续安全拒绝 | §5, §4.3 第 2 点 | 覆盖 |
| 复用现有 transaction/rollback | §4.7 | 覆盖 |
| 最终 tree 证明 | §4.4-4.7, §9.2 断言 | 覆盖 |

所有 Goal 定义的 S4 业务结果均已覆盖，无遗漏。

### 修订版 out-of-scope 排除复查

| 排除项 | Plan 位置 | 排除状态 |
|---|---|---|
| TOCTOU / 并发竞态 | §1.1, §5, §11.1, §11.3 #3 | 显式排除 |
| descriptor pinning / fd-relative reader | §5, §4.2（删除 fd reader）, §11.3 #3 | 显式排除 + 主动删除 |
| ctime/nlink stable state | §4.3 第 4 点, §5, §11.1 | 显式排除 |
| loader snapshot/bytes API | §3（config_loader.py 全部撤销）, §4.2（删除 load_execution_profiles_snapshot）, §5 | 显式排除 + 主动删除 |
| typed filename manifest | §3（config_loader.py 全部撤销）, §5 | 显式排除 |
| 新 transaction/rollback state machine | §4.7, §5, §11.1, §11.3 #2 | 显式排除 |
| _PrivatePathShape / typed backup shape | §4.3 第 8 点, §5 | 显式排除 |

所有 out-of-scope 项均被显式排除，且 §11.3 停止条件可阻止实现中重新引入。新增 §4.2 还主动删除了 partial implementation 中的 fd reader 基础设施。

### 修订版 cleanup dispatch 最小性复查

§4.3 第 7-8 点：

1. 真源：既有 `expected_identity.mode`（`PathIdentity.mode: int`，来自 `os.stat(..., follow_symlinks=False).st_mode`）
2. 前置调整：`_require_ordinary_directory(...)` 在同一 owner 内放宽为接受 ordinary regular file 或 ordinary directory
3. 删除分派：`stat.S_ISREG(mode)` → `os.unlink(quarantine)`, `stat.S_ISDIR(mode)` → 既有 `shutil.rmtree(quarantine)`
4. 不新增：`_PrivatePathShape`、typed backup shape、backup tuple expansion、第二套 cleanup helper
5. 不扩散：不把 directory-only 放宽传播到 `_cleanup_private_path` 以外的 caller
6. 不修改：`_rollback_or_raise(...)` signature/unpacking、`backup_records` 3-tuple

**验证结论**：cleanup dispatch 仍是最小必要扩展——仅基于已有 `PathIdentity.mode` 在同一函数内增加一个 `os.unlink` 分支，同时显式约束不向其他调用点扩散。

## Architecture Boundary Re-check

修订版新增 §4.2 引入了一个重要的边界澄清：execution-profile loading 的 owner 是 `commands/init.py` 中的 `_load_target_min_context_window` + `ConfigLoader.load_execution_profiles`，而不是新的 snapshot/bytes API。Plan 正确地要求删除 partial implementation 中跨过此边界的 fd reader 代码。

分层检查：

- `config_loader.py`：两个 full-revert 文件之一，净 diff 为零。ConfigLoader public contract 不变。 ✓
- `commands/init.py`：只增加 flags-to-repair-intent helper + 删除 fd reader + 恢复 HEAD path-loader。不新增 Engine/Host 依赖。 ✓
- `init_workspace.py`：只增加補缺 helper + regular-root snapshot + cleanup dispatch。不新增对上层或跨层依赖。 ✓
- 测试：只在既有 owner boundary 扩展断言，不新建 test harness。 ✓

## Overcoupling Re-check

修订版未引入新的耦合：

- repair intent 在 `commands/init.py` 生成、传给 `init_workspace.py` 的 `snapshot_managed_roots` 和 `_require_snapshot_unchanged`——这是标准参数传递，不是架构耦合。
- 補缺 helper 只读 `config_file_names()` 返回值，不依赖 ConfigLoader 内部实现。
- cleanup dispatch 只在 `_cleanup_private_path` 内部闭包处理，不向外暴露 shape。

## Overengineering Re-check

修订版新增内容均为删除（§4.2 删除 fd reader）或精确约束（§4.3 第 7-8 点强化边界），无新增 abstraction、type、protocol 或 generalization。§13 Overdesign check 结论不变。

## Open Questions

None。6 个 blocking questions 在 §11.1 已由用户裁决；两个上一轮 findings 已关闭。

## Residual Risks

| Risk | Classification | Status |
|---|---|---|
| 外部进程并发修改 workspace | Out of scope（用户裁决） | 不变 |
| Windows reparse 平台能力 | 沿用 S1–S3 baseline | 不变 |
| 现有 transaction fault coverage | 由既有 tests 持续覆盖 | 不变 |
| apply_patch 可用性 | Controller 已裁决（Codex 内置） | Closed |
| _require_ordinary_directory 松弛遗漏 | Plan 已显式说明 | Closed |

## Conclusion

**PASS**

修订版计划：

1. **上一轮两个 findings 均已关闭**：#1 由 Controller 裁决为环境内置工具并写入 §7；#2 在 §4.3 第 7 点和 §6 S4-SC2 中显式说明了 `_require_ordinary_directory` 的松弛范围与不扩散约束。
2. **Goal 合规不变**：所有 S4 业务结果（PRESERVE 补缺、OVERWRITE/RESET ordinary-file repair、最终 tree、rollback 复用）在修订版中仍然完整覆盖，无遗漏。
3. **Out-of-scope 排除不变且加强**：新增 §4.2 主动删除 partial implementation 的 fd reader 基础设施，进一步消除 loader snapshot/descriptor 代码残留。
4. **Cleanup dispatch 仍然最小**：基于既有 `PathIdentity.mode` 在同一 owner 内做 `os.unlink`/`shutil.rmtree` 分派，无新增 type/helper/shape protocol。
5. **新增 §4.2 纯防御性**：只删除越界代码、恢复 HEAD contract，不引入新语义或新风险。

未发现 material findings。Plan 可进入 implementation gate。
