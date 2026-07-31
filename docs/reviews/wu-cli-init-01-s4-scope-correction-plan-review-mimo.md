# WU-CLI-INIT-01 S4 Scope-Correction Plan Review — MiMo

## Review target

- **Artifact**: `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-codex.md`
- **唯一目标边界**: `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- **Reviewer**: AgentMiMo
- **Date**: 2026-07-30

## Assumptions tested

1. Plan 是否仍含并发竞态/TOCTOU/descriptor/ctime/nlink/loader snapshot/新增事务或回滚状态机
2. 是否遗漏 Goal 明确的 preserve 补缺、overwrite/reset ordinary-file root repair 及最终 tree
3. 最小 file-vs-directory cleanup 分派是否只是现有机制必要扩展

## Findings

### 01-未修复-高-`_regular_file_digest` 使用 ctime/nlink descriptor stable state 与 §5 明确禁令冲突

- **位置**: §4.2 item 3 ("regular file content digest 只计算普通文件 bytes 的 SHA-256") vs §5 ("明确不新增：st_ctime_ns / st_nlink stable state")
- **问题类型**: 计划内部矛盾 / 不可直接实施
- **当前写法**: §4.2 item 3 声称 "regular-file content digest 不引入 ctime/nlink 或 pre/post stable state"，但当前 dirty diff 中 `_regular_file_digest` 的实现包含：
  ```python
  before_state = _descriptor_stable_state(before_stat)
  # ... read ...
  after_state = _descriptor_stable_state(os.fstat(descriptor))
  if after_state != before_state:
      raise InitWorkspaceError(...)
  ```
  其中 `_descriptor_stable_state` 返回 `(st_dev, st_ino, st_mode, st_nlink, st_size, st_mtime_ns, st_ctime_ns)` 元组。`_descriptor_stable_state` 函数本身也是 dirty 新增的。
- **反例/失败场景**: Implementation agent 按 §4.2 的字面描述保留当前 `_regular_file_digest` 实现（因为它"只计算普通文件 bytes 的 SHA-256"——digest 本身确实是 SHA-256），同时保留 ctime/nlink stable-state guard，直接违反 §5 的 "明确不新增" 列表。
- **为什么有问题**: §4.2 item 3 与 §5 存在直接矛盾。§4.2 说的是 digest 的目标行为（SHA-256），§5 说的是 digest 的实现手段限制（不比较 ctime/nlink）。当前实现两者都包含了。Implementation agent 需要明确指导：简化 `_regular_file_digest` 只做 identity check + SHA-256，移除 `_descriptor_stable_state` 函数。
- **直接证据**:
  - 当前 dirty `init_workspace.py` 行 1706–1778: `_regular_file_digest` 和 `_descriptor_stable_state`
  - Plan §5: "明确不新增：st_ctime_ns / st_nlink stable state"
  - Plan §4.2 item 3: "regular-file content digest 不引入 ctime/nlink 或 pre/post stable state"
- **影响**: 实现 agent 保留 ctime/nlink 检查 → 产出代码直接违反 §5 禁令 → plan review 验收不可通过
- **建议改法和验证点**:
  - §4.2 item 3 增加明确指导："`_regular_file_digest` 只做 `os.open` + identity verify（device/inode/mode）+ SHA-256 read + close；移除 `_descriptor_stable_state` 函数；不比较读前/读后 nlink/mtime/ctime"
  - §3 `init_workspace.py` 行增加："`_descriptor_stable_state` 函数随 `_regular_file_digest` 简化而移除"
  - 验证：grep 确认 `st_ctime_ns`、`st_nlink`、`_descriptor_stable_state` 不在最终净 diff 中
- **修复风险**: 低
- **严重程度**: 高

### 02-未修复-中-backup tuple 扩展为 4-tuple 与 "不修改 rollback loop" 和 "不给 backup tuple 增加 shape" 矛盾

- **位置**: §4.2 item 7-8 / §3 `init_workspace.py` 行 / §4.6
- **问题类型**: 计划内部矛盾 / 不可直接实施
- **当前写法**:
  - §4.2 item 7: "只扩展 `_cleanup_private_path(...)` 的最终删除分派：expected_identity.mode 为 regular file 时对 quarantine 执行 `os.unlink`"
  - §4.2 item 8: "不新增 `_PrivatePathShape` 或其它 shape protocol，不给 backup tuple 增加 shape，不修改 rollback loop"
  - §4.6: "不修改 `_rollback_or_raise(...)`、backup record 或 fault injection seam"
- **反例/失败场景**: 当前 dirty diff 中 backup_records 已从 `list[tuple[ManagedRootSnapshot, Path, PathIdentity]]` 扩展为 `list[tuple[ManagedRootSnapshot, Path, PathIdentity, _PrivatePathShape]]`，`_rollback_or_raise` 的 unpacking 也从 `for root_snapshot, backup_path, backup_identity` 变为 `for root_snapshot, backup_path, backup_identity, _backup_shape`。如果 implementation agent 按 §4.2 item 7 的要求添加 file-vs-directory dispatch，但同时按 item 8 不改 backup tuple 和 rollback loop，则需要在 `_post_publication_cleanup` / `_cleanup_private_path` 内部从 `expected_identity.mode` 直接派生 shape。但 plan 没有明确说明这个路径。
- **为什么有问题**: §4.2 item 7 要求 file-vs-directory dispatch，item 8 禁止修改 backup tuple 和 rollback loop。两者可以兼容（在 cleanup 内部从 identity.mode 派生），但 plan 没有明确指出这个实现路径。Implementation agent 可能选择扩展 backup tuple（当前 dirty diff 就是这样做的），从而违反 item 8。
- **直接证据**:
  - 当前 dirty `init_workspace.py`: backup_records 类型已改为4-tuple
  - Plan §4.2 item 8: "不给 backup tuple 增加 shape，不修改 rollback loop"
  - Plan §4.6: "不修改 `_rollback_or_raise(...)`、backup record"
- **影响**: 实现 agent 扩展 backup tuple → 违反 item 8 和 §4.6 → 或者尝试在不改 tuple 的情况下实现 dispatch 但不确定如何做
- **建议改法和验证点**:
  - §4.2 item 8 增加明确实现路径："file-vs-directory dispatch 只在 `_cleanup_private_path` 内部用 `stat.S_ISREG(expected_identity.mode)` 派生，不扩展 backup tuple，不修改 `_rollback_or_raise` unpacking"
  - §3 `init_workspace.py` 行增加："backup tuple 结构保持 HEAD 3-tuple；`_post_publication_cleanup` 不传 `expected_shape`"
  - 验证：`_rollback_or_raise` 对 HEAD 无净 diff；backup_records 类型声明保持 3-tuple
- **修复风险**: 低
- **严重程度**: 中

### 03-未修复-低-`_load_target_min_context_window` 签名变更未在 §3 选择性撤销列表中明确列出

- **位置**: §3 `dayu/cli/commands/init.py` 行
- **问题类型**: 不可直接实施
- **当前写法**: §3 对 `commands/init.py` 描述为 "选择性撤销：fd reader、descriptor state、ctime/nlink、close precedence、typed filename consumer 全部回到 HEAD"，但未明确列出 `_load_target_min_context_window` 函数的签名和实现变更。当前 dirty diff 将该函数从使用 `ConfigLoader.load_execution_profiles(workspace_config_dir=...)` 改为使用 `load_execution_profiles_snapshot(workspace_file_snapshot=...)`，并新增了 `_read_workspace_execution_profile_snapshot`、`_workspace_profile_descriptor_state`、`_close_workspace_profile_descriptors` 等 descriptor-stable reader 函数。
- **反例/失败场景**: Implementation agent 撤销 descriptor-stable reader 函数但保留 `_load_target_min_context_window` 的新签名，导致调用不存在的方法。
- **为什么有问题**: `_load_target_min_context_window` 的签名从 `workspace_root: Path` 变为 `workspace_identity: _WorkspaceRootIdentity`，内部从 `load_execution_profiles(workspace_config_dir=...)` 变为 `load_execution_profiles_snapshot(workspace_file_snapshot=...)`。这些变更与 fd reader / descriptor state 相关，应随其一起撤销，但 plan §3 的描述不够显式。
- **直接证据**:
  - HEAD `commands/init.py` `_load_target_min_context_window` 使用 `workspace_root: Path` 和 `load_execution_profiles`
  - 当前 dirty diff 使用 `workspace_identity` 和 `load_execution_profiles_snapshot`
  - §3 描述 "fd reader、descriptor state...全部回到 HEAD" 覆盖了这些变更但不够显式
- **影响**: 实现 agent 遗漏此函数的撤销 → 代码引用不存在的 API → 测试失败
- **建议改法和验证点**:
  - §3 `commands/init.py` 行增加："`_load_target_min_context_window` 签名和实现回到 HEAD（使用 `workspace_root: Path` + `load_execution_profiles`）；移除 `_read_workspace_execution_profile_snapshot`、`_workspace_profile_descriptor_state`、`_close_workspace_profile_descriptors`、`_FD_RELATIVE_OPEN_SUPPORTED`、`_WORKSPACE_PROFILE_READ_CHUNK_BYTES`、`_WorkspaceProfileDescriptorState`"
  - 验证：这些函数/常量/类对 HEAD 无 diff
- **修复风险**: 低
- **严重程度**: 低（从 "fd reader/descriptor state 回到 HEAD" 可推断，但显式列出更安全）

## Open questions

None。

## Residual risks

- 外部进程并发修改 workspace：`out of scope by explicit user decision`。与 plan §11.2 一致。
- Windows reparse 平台能力：沿用现有 S1–S3/S4 baseline 测试。与 plan §11.2 一致。
- `_copy_missing_root_config_files` 对 symlink 目标文件使用 `os.stat`（follows symlinks）：若用户用 symlink 替换了某个根配置文件，`os.stat` 不抛 `FileNotFoundError`，该文件不会被补缺覆盖。这是 plan 设计意图（只补"真正缺失"的文件），但实现 agent 需注意 `_validate_ordinary_tree` 的 root-level validation 不检查 staging tree 内的 symlink（因为 copytree 的 `symlinks=True` 会复制 symlink 本身）。

## Conclusion

**CHANGES_REQUESTED**

三个 finding 中，Finding 01 是计划内部的直接矛盾（§4.2 vs §5），会导致实现 agent 产出违反 §5 禁令的代码。Finding 02 是实现路径不明确，implementation agent 可能选择违反 "不给 backup tuple 增加 shape" 的路径。Finding 03 是可推断但不显式的撤销目标。

建议 Codex 修订 plan 后重新提交 review。
