# WU-CLI-INIT-01 S4 Scope-Correction Plan

## Gate metadata

- Work unit：`WU-CLI-INIT-01`
- Slice：`S4 — Managed whole-tree modes 与 repair`
- Gate：`scope-correction planning`
- Decision：`ready for plan review`
- 唯一目标边界：
  `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- 实现恢复基线：`cf72af5d`
- 当前基线已包含：
  - `53f6b7f6 gateflow: accept WU-CLI-INIT-01 S1`
  - `9e6cde82 gateflow: accept WU-CLI-INIT-01 S2`
  - `06ea49e0 gateflow: accept WU-CLI-INIT-01 S3`
- 本 artifact：
  `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-codex.md`
- 本 gate 只创建本文件；不修改生产代码、测试、其它 artifact，不提交。
- 下一入口：本计划的独立 plan review；评审前不得恢复 implementation。

## 1. 第一性原理裁决

### 1.1 动机成立，但原 S4 amendment 严重扩大了目标

Goal 中真实存在的 S4 缺口是：

1. PRESERVE 当前只补缺失 prompt，没有补
   `config_file_names()` 返回的五类根配置文件；
2. ordinary regular file 占据 `config` managed root 时，显式 OVERWRITE 必须能重建
   config 并保留 `.dayu`；
3. ordinary regular file 占据 `config` / `.dayu` managed roots 时，显式 RESET
   必须能清理旧 roots、重建 config 并保留 portfolio/non-init assets；
4. 需要用真实最终 tree 证明 PRESERVE、OVERWRITE、RESET 和普通
   incomplete/corrupt workspace 的业务结果；
5. 需要继续复用现有 transaction/rollback，并验证失败后原业务状态恢复。

Goal 没有要求解决并发文件系统 mutation，也没有要求扩大路径安全或 transaction
安全契约。原 S4 amendment 将 S2 的静态 shape 检查扩大为 TOCTOU、descriptor
pinning、逐层 fd-relative reader、ctime/nlink stable state、loader snapshot API、
typed filename manifest、descriptor-stable ordinary-file digest 和新的 fault/race
matrix。这些都不是 ordinary-file recovery 业务结果成立所必需的契约，用户已明确
裁决为 out of scope。

因此本次正确修复不是继续完成 partial implementation，而是先安全撤销其越界增量，
再只实现 PRESERVE 根配置补缺、ordinary-file roots 的最小 destructive recovery
分派与业务结果测试。

### 1.2 “ordinary incomplete/corrupt” 的精确含义

本计划中的 ordinary workspace 是现有 contract 已接受的 ordinary directory tree：

- incomplete：五类根配置或 package-owned prompt/init asset 缺失；
- corrupt：根配置文件仍是 ordinary regular file，但 JSON/schema 内容损坏；
- root-shape corrupt：ordinary regular file 占据 `config`，或在 RESET 中占据
  `.dayu`；
- 不包括 symlink、dangling symlink、FIFO/socket/device、Windows reparse 或非法
  lock identity。

前两类按适用 mode 恢复：

- 可无损补齐的缺失由 PRESERVE 恢复；
- 不能无损修复的 corrupt 内容由 PRESERVE 保持原内容并失败，再由显式
  OVERWRITE 或 RESET 重建；
- `config` ordinary file 只允许 OVERWRITE / RESET 修复；
- `.dayu` ordinary file 只允许 RESET 修复，OVERWRITE 继续拒绝。

symlink、reparse 与 special root 在所有 mode 继续沿现有 snapshot/lock contract
拒绝；只有上述 ordinary regular file 与显式 destructive mode 的精确组合扩大
path-shape ownership。

## 2. 直接代码证据与 semantic owner

| 业务语义 | 现有唯一 owner | 直接证据与本次决定 |
|---|---|---|
| 五类根配置文件名与顺序 | `dayu.runtime.config_loader.config_file_names()` | 当前已返回稳定 `tuple[str, ...]`，足以供 staging 顺序遍历；不需要 `NamedTuple` 或新 public type |
| PRESERVE staging 内容 | `dayu.cli.init_workspace._build_staged_config(...)` | 当前 HEAD 只调用 `_copy_missing_prompt_files(...)`，没有补五类根配置；唯一生产缺口改在这里 |
| 模型选择 owner 字段 | `apply_model_selection(...)` 与 `project_known_manifest_models(...)` | 继续在 staging 补缺后运行；不得让补缺 helper 重算或修改这些字段 |
| destructive repair intent | `dayu.cli.commands.init` 的已解析 `--overwrite` / `--reset` 与 `snapshot_managed_roots(...)` | lock 前后 snapshot 都显式传同一最小 repair intent；不从 CLI 自报 mode 或路径 shape 反推 |
| ordinary-file root 分类与 digest | `dayu.cli.init_workspace.snapshot_managed_roots(...)` | 只接受 mode-owned regular root；使用普通内容摘要参与既有 snapshot equality，不增加 pre/post descriptor stable-state contract |
| OVERWRITE 业务范围 | 现有 `_build_staged_config(...)`、`_roots_replaced_by_mode(...)` | 从当前 package config 重建整个 config；允许 config ordinary file 进入既有 backup/publication；`.dayu` 不在 replacement set且若为 ordinary file仍拒绝 |
| RESET 业务范围 | 现有 managed-root manifest 与 `_roots_replaced_by_mode(...)` | 允许 `.dayu` / config ordinary files 进入既有 backup/publication；旧 `.dayu` state 被清除，config/init-owned assets 从 package 重建；portfolio、assets 等非 managed roots 不被替换 |
| file-vs-directory backup cleanup | `dayu.cli.init_workspace._cleanup_private_path(...)` | 继续以既有 `PathIdentity.mode` 为真源；regular backup quarantine 后 `unlink`，directory 继续既有 `rmtree`；不新增 public type或第二套 helper |
| publication/rollback | 现有 `prepare_workspace_transaction(...)`、`publish_workspace_transaction(...)`、`_rollback_or_raise(...)` | backup record 和 rollback `os.replace` 原样复用；不新增 rollback branch/state 或 fault boundary |
| 静态 symlink/special 拒绝 | 现有 `snapshot_managed_roots(...)`、`_validate_ordinary_tree(...)` 和 S2 profile shape 检查 | 维持现状，不改成 copy-then-reject，不新增 race contract |
| lock path identity | `dayu.cli.commands.init._validate_lock_path(...)` 与 `dayu.runtime.filelock` | 现有测试已覆盖 symlink、dangling 与 directory lock；S4 不修改 |

## 3. 当前 7 个 dirty 文件的精确处置

当前 dirty code/test diff 为七个文件，均是尚未提交的 S4 partial implementation。
处置按“当前增量”而不是按“文件永远不可编辑”裁决。

| Dirty file | 当前增量处置 | Scope-correction 后允许的净变更 |
|---|---|---|
| `dayu/cli/commands/init.py` | **选择性撤销**：fd reader、descriptor state、ctime/nlink、close precedence、typed filename consumer 全部回到 HEAD；`_load_target_min_context_window(...)` 恢复 HEAD path-loader contract | 只保留/重写 lock 前后 `snapshot_managed_roots(...)` 的显式 repair intent 传递与一个私有 flags-to-intent helper |
| `dayu/runtime/config_loader.py` | **全部撤销**：`ConfigFileNames(NamedTuple)`、snapshot loader、bytes parser/public API 和为其抽取的投影全部回到 HEAD | 无 |
| `tests/cli/test_init_command.py` | **选择性撤销**：snapshot loader mock 迁移及所有 fd/capability/close/race tests 全部回到 HEAD | 只允许在既有 mode/调用测试中断言 OVERWRITE/RESET repair intent 传给 lock 前后 snapshot；不新增线程/syscall test |
| `tests/runtime/test_config_loader.py` | **全部撤销**：typed manifest 与 snapshot API tests 全部回到 HEAD | 无 |
| `tests/cli/test_init_smoke.py` | **选择性撤销**：不撤销 ordinary-file business scenario 本身，只删除任何超出最终业务 tree 的安全契约断言 | 保留/收敛当前 ordinary-root OVERWRITE/RESET smoke，并窄幅扩展既有四态 smoke 覆盖 missing/corrupt ordinary tree；不新增 fault/race smoke |
| `dayu/cli/init_workspace.py` | **选择性撤销**：撤销 descriptor stable state、ctime/nlink、typed backup tuple、额外 rollback改写及 copy-then-reject 行为 | 保留/重写 PRESERVE 根配置补缺、mode-owned regular-root snapshot/digest，以及基于既有 `PathIdentity.mode` 的最小 file-vs-directory cleanup 分派 |
| `tests/cli/test_init_workspace.py` | **选择性撤销**：撤销 copy-race/symlink 新预期、typed shape publicized signature 与新增 fault matrix | 保留/重写根配置逐项补缺、ordinary-file root mode matrix和一个 cleanup dispatch owner test；既有 rollback 测试只复用，不扩矩阵 |

以下未跟踪 S4 artifacts 不属于七个 dirty code/test 文件，本次 implementation
scope cleanup 不删除、不改写：

- `docs/reviews/wu-cli-init-01-s4-implementation-codex.md`
- `docs/reviews/wu-cli-init-01-s4-plan-amendment-2-codex.md`
- `docs/reviews/wu-cli-init-01-s4-plan-amendment-2-review-ds.md`
- `docs/reviews/wu-cli-init-01-s4-plan-amendment-2-review-mimo.md`

## 4. 最小 S4 业务缺口与精确实现

### 4.1 PRESERVE 补齐五类根配置

在 `dayu/cli/init_workspace.py` 内保留现有顺序：

1. `_validate_ordinary_tree(public_config, ...)` 继续在 copy 前拒绝 symlink、
   reparse 与 special；
2. `shutil.copytree(public_config, staged_config_root, symlinks=True)` 原样复制用户
   config tree；
3. 新增模块级私有 `_copy_missing_root_config_files(...)`；
4. 继续调用 `_copy_missing_prompt_files(...)`；
5. 回到既有 `prepare_workspace_transaction(...)`，只由
   `apply_model_selection(...)` 和 `project_known_manifest_models(...)` 修改各自
   owner 字段；
6. 继续执行现有完整 staging validation、publication 与 rollback。

`_copy_missing_root_config_files(...)` 的 exact contract：

- 只遍历现有 `config_file_names()`；
- destination 已存在时零改写，不解析、不合并、不格式化；
- destination 真正缺失时，从 `package_config_root / file_name` 复制；
- package source 继续用现有 no-follow identity/mode 规则要求 ordinary regular
  file；
- 不新增 filename type、位置索引、重复 filename literal或 loader API；
- 不处理 root config 的 symlink/special fallback，因为 public config tree 已由现有
  `_validate_ordinary_tree(...)` 在进入 staging 前拒绝；
- 不碰用户额外文件、未知目录或非 init-owned asset。

### 4.2 Init execution-profile loading 恢复 HEAD contract

ordinary-file managed-root repair 不需要改 execution-profile 读取 owner。必须把
`dayu/cli/commands/init.py` 的该调用链恢复为 HEAD：

- `_load_target_min_context_window(*, locked_mode, workspace_root)` 保持
  `workspace_root: Path` 入参；
- PRESERVE 继续构造 `workspace_root / "config"`，调用既有
  `ConfigLoader.load_execution_profiles(workspace_config_dir=...)`；
- FIRST / OVERWRITE / RESET 继续传 package-only `workspace_config_dir=None`；
- 恢复 `_EXECUTION_PROFILES_FILE_NAME` 与
  `_workspace_execution_profile_is_regular_file(...)` 的既有静态 no-follow shape
  拒绝；
- 删除 `errno` 与 init 对 `config_file_names` 的新增 import；
- 删除 fd reader 相关类：
  `_WorkspaceProfileDescriptorState`；
- 删除 fd reader 相关常量：
  `_CONFIG_ROOT_NAME`、`_WORKSPACE_PROFILE_READ_CHUNK_BYTES`、
  `_FD_RELATIVE_OPEN_SUPPORTED`；
- 删除 fd reader 相关 helpers：
  `_read_workspace_execution_profile_snapshot(...)`、
  `_workspace_profile_descriptor_state(...)`、
  `_close_workspace_profile_descriptors(...)`；
- 不调用 `ConfigLoader.load_execution_profiles_snapshot(...)`，不保留任何 bytes
  snapshot / close precedence contract。

### 4.3 Ordinary-file managed-root destructive recovery

仅增加使 Goal 业务结果成立的以下最小数据流：

1. `dayu.cli.commands.init` 把解析后的 flags 投影为
   `InitMode.OVERWRITE | InitMode.RESET | None`，在 lock 前与 lock 内两次调用
   `snapshot_managed_roots(...)` 时显式传入；
2. `snapshot_managed_roots(...)` 继续默认只接受 ordinary directory；仅当
   `repair_mode` 精确拥有该 root 时接受 ordinary regular file：
   - OVERWRITE：只接受 `config` regular file；
   - RESET：接受 `config` 与 `.dayu` regular files；
   - `.dayu` regular file + OVERWRITE、任一 regular root + 无 flag：拒绝；
3. regular file snapshot 继续产生 `ManagedRootSnapshot`，identity 使用现有
   no-follow `PathIdentity`；先用该 identity/mode 确认为 mode-owned ordinary
   regular file，再用与现有 tree digest 同级的普通读取累计 SHA-256；
4. 最终删除当前 partial implementation 的 `_descriptor_stable_state(...)`；
   regular digest 不做 pre/post `fstat`，不读取或比较 `st_ctime_ns` /
   `st_nlink`，不建立“稳定读取”新契约；并发 mutation 明确不在本 WU；
5. `_require_snapshot_unchanged(...)` 以 request mode 重取同一类 snapshot，继续复用
   既有 equality boundary；
6. publication 继续用现有 `os.replace(root, backup)`；`backup_records` 保持 HEAD
   的 3-tuple
   `tuple[ManagedRootSnapshot, Path, PathIdentity]`，不得增加 shape；
   `_rollback_or_raise(...)` 的签名、tuple unpacking 与 restore loop 对 HEAD
   无净 diff；
7. 只扩展 `_cleanup_private_path(...)` 的最终删除分派：
   - expected/actual/quarantine identity 仍走既有锁定；
   - 现有 cleanup 前置 `_require_ordinary_directory(...)` 必须在同一 owner 内调整：
     只接受 `expected_identity.mode` 派生出的 ordinary regular file 或 ordinary
     directory；不把这一放宽扩散到其它 directory-only caller；
   - symlink、Windows reparse、special 或 expected/actual identity/type不一致仍
     拒绝；
   - `expected_identity.mode` 为 regular file 时对 quarantine 执行 `os.unlink`；
   - 为 ordinary directory 时继续既有 capability gate + `shutil.rmtree`；
8. 不新增 `_PrivatePathShape` 或其它 shape protocol，不给 backup tuple 增加 shape，
   不修改 rollback loop；`_post_publication_cleanup(...)` 的签名及调用不传
   `expected_shape`；file-vs-directory 真源只由 `_cleanup_private_path(...)` 直接
   从既有 `expected_identity.mode` 派生。

### 4.4 PRESERVE 结果

必须证明：

- 五类根配置任一单独缺失时，都从当前 package source 补齐；
- 已存在的其它根配置在 staging copy/补缺边界 bytes 不变；
- 用户额外文件、用户 manifest 与非 owner 内容保留；
- 缺失 prompt/init-owned asset 继续按既有 helper 补齐；
- 最终只允许既有 model selection owner 更新 model records 与 16 个 known
  manifest 的 owner 字段；
- corrupt JSON/schema 不被补缺逻辑覆盖或修写；PRESERVE 失败、public tree 与
  `.dayu` 保持原 truth。

### 4.5 OVERWRITE 结果

必须证明：

- config 从当前 package config + 本次 model projection whole-tree 重建；
- config ordinary file 可由显式 OVERWRITE 进入既有 backup/publication 并恢复为
  ordinary directory tree；
- config 内用户 sentinel、extra file/dir 与 corrupt bytes 消失；
- `.dayu` 内容、identity/digest 保留；
- `.dayu` ordinary file 仍拒绝，OVERWRITE 不扩大其 owner；
- portfolio、assets 与其它非 init-owned roots 保留；
- 最终 config 可由真实 `ConfigLoader` 加载。

### 4.6 RESET 结果

必须证明：

- config / `.dayu` ordinary files 可由显式 RESET 进入既有
  backup/publication/cleanup；
- 旧 `.dayu` state 或 ordinary-file sentinel 被移除，不在 init 中伪造新的
  runtime state；
- config 与其中 package/init-owned assets 从当前 package source 重建；
- portfolio、assets 与其它非 managed/non-init assets 的内容和 identity 保留；
- corrupt ordinary config 可恢复为真实可加载 config；
- reset No/Enter、EOF、SIGINT 语义继续由 S2 已接受测试拥有，本 S4 不重测状态机。

### 4.7 Rollback 结果

不修改 `_rollback_or_raise(...)`、backup record 或 fault injection seam。regular
file 与 directory 都由同一个现有 backup record 和 restore loop 恢复。直接复用并
运行现有 tests：

- `test_publication_replace_failure_rolls_back_original_config`
- `test_publication_replace_fault_matrix_restores_snapshot`
- `test_reset_each_root_backup_fault_restores_both_roots`
- `test_posix_publication_sync_fault_rolls_back`
- `test_posix_rollback_sync_fault_reports_durability_and_current_truth`

验收只看既有 transaction 在失败后恢复的 public snapshot/digest/identity 和 truthful
retained state；不新增 fault boundary，不新增 rollback mechanism。

## 5. Path-safety 边界

本 S4 对 symlink、special 与 lock 只维持现有拒绝：

- managed root / nested symlink、dangling symlink、FIFO、socket、device、
  Windows reparse：继续由现有 snapshot/tree validation 拒绝；
- execution profile final path 的静态 symlink/dangling/directory/FIFO：继续由
  S2 已提交的 no-follow shape check 拒绝；
- `.dayu-init.lock` 的 symlink、dangling 与 directory identity：继续由现有
  `_validate_lock_path(...)` 拒绝。

明确不新增：

- 并发文件系统竞态或 TOCTOU contract；
- descriptor pinning、fd-relative reader、`O_NONBLOCK` reader；
- `st_ctime_ns` / `st_nlink` stable state；
- race barrier、threading Event、sleep/retry 或 syscall fault matrix；
- loader snapshot/bytes API；
- typed filename manifest；
- `_PrivatePathShape`、typed backup shape、backup tuple expansion 或第二套 cleanup
  helper；
- descriptor-stable regular-file digest；
- transaction、backup、publication 或 rollback state-machine 改写；
- 超出既有 identity/quarantine 后 `unlink` vs `rmtree` 所需的 cleanup 安全契约。

## 6. Implementation slices

### S4-SC1 — 安全撤销 out-of-scope partial diff

- Objective：把七个 dirty 文件恢复到 S1–S3 已提交基线，且不碰其它 dirty/untracked
  artifact。
- Allowed files：仅第 3 节列出的七个 dirty code/test 文件。
- Exact changes：
  1. 两个“全部撤销”文件逐文件回到 `HEAD=cf72af5d`；
  2. 五个“选择性撤销”文件先回到同一 HEAD；
  3. 不用 `git checkout`、`git restore`、`git reset` 或整树覆盖；
  4. 不修改本计划和其它 review artifacts。
- Completion signal：
  - 两个 full-revert 文件对 HEAD 无 diff；
  - 五个 selective 文件也先达到无 diff，之后才进入 S4-SC2；
  - S1–S3 committed files/behavior 原样保留。

### S4-SC2 — PRESERVE 补缺与 ordinary-file root recovery

- Objective：关闭五类根配置缺失与显式 destructive ordinary-file recovery 两个
  Goal gap，并证明复用既有 mode/rollback 的业务结果。
- Allowed production files：
  - `dayu/cli/commands/init.py`
  - `dayu/cli/init_workspace.py`
- Allowed test files：
  - `tests/cli/test_init_command.py`
  - `tests/cli/test_init_workspace.py`
  - `tests/cli/test_init_smoke.py`
- Exact production changes：
  - 在 `_build_staged_config(...)` 的 PRESERVE 分支增加一次根配置补缺调用；
  - 新增一个模块级私有补缺 helper；
  - `commands/init.py` 只新增 flags-to-repair-intent helper，并在两次 snapshot 调用
    下传；
  - `_load_target_min_context_window(...)` 及 execution-profile loader 调用恢复
    §4.2 的 HEAD path-loader contract，移除全部 fd reader类/常量/helpers；
  - `snapshot_managed_roots(...)` 只新增可选 repair intent和 mode-owned regular-file
    root 分类；
  - 删除 `_descriptor_stable_state(...)`；regular-file digest只复用现有 no-follow
    identity/mode 验证并普通读取 SHA-256，不做 pre/post `fstat`，不读
    ctime/nlink；
  - `_require_snapshot_unchanged(...)` 以 request mode 重取；
  - `_cleanup_private_path(...)` 在同一 owner 内把 directory-only 前置调整为只接受
    expected ordinary regular file或ordinary directory，再直接按既有
    `expected_identity.mode` 分派 `os.unlink` / 既有 `shutil.rmtree`；
  - `backup_records` 保持 HEAD 3-tuple，`_rollback_or_raise(...)` signature/unpacking
    无净 diff，`_post_publication_cleanup(...)` 不传 shape；
  - publication loop、public export 与 ConfigLoader contract 不变。
- Exact tests：
  1. `tests/cli/test_init_workspace.py` 参数化五个 `config_file_names()`：
     每次只删除一个，断言缺失文件等于 package bytes、其它已存在文件在 staging
     边界 bytes 不变；
  2. 保留/收敛 ordinary-file root mode matrix：
     无 flag 拒绝；OVERWRITE 修复 config regular file并保留 `.dayu`；
     OVERWRITE 拒绝 `.dayu` regular file；RESET 修复 config / `.dayu` regular
     files并保留 portfolio/assets；
  3. 一个 cleanup owner test只证明相同 helper 对 regular backup 用 unlink、
     directory继续 rmtree；不注入新 fault；
  4. 扩展/新增一个普通 corrupt-content mode 结果测试：
     PRESERVE 对 malformed ordinary JSON 零 publication并保留原 tree；
     OVERWRITE 重建 config 且保留 `.dayu`；RESET 清旧 `.dayu`、重建 config，
     保留 portfolio/assets；
  5. 运行而不扩展第 4.7 节既有 rollback tests；
  6. `tests/cli/test_init_command.py` 只更新既有 snapshot mock/call assertions，
     证明 lock 前后收到相同 repair intent；
  7. 窄幅扩展既有
     `test_posix_real_four_state_config_scene_and_reset_sentinels`：
     用一个代表性根配置缺失证明真实 PRESERVE 补缺；用一个 ordinary corrupt
     config 证明显式 OVERWRITE 恢复；继续断言 RESET 与非 init-owned sentinels；
  8. 保留/收敛当前
     `test_posix_real_ordinary_root_overwrite_reset_matrix`，只断言最终 tree、`.dayu`
     ownership与可加载 config；
  9. 不新增 fault/race matrix，不新增 descriptor/syscall/threading test。
- Completion signal：
  - 净生产 diff 只有补缺、repair intent、regular-root snapshot/digest与最小 cleanup
    delete dispatch；
  - 净测试 diff只覆盖上述业务结果和一次无 fault 的 owner dispatch；
  - 两个 full-revert 文件对 HEAD 保持无 diff。

## 7. 使用 `apply_patch` 安全撤销 partial diff

implementation 必须用小步、逐文件 `apply_patch`，不能用会覆盖整棵工作树的 git
恢复命令。

固定流程：

1. 再确认 `git rev-parse HEAD` 为 `cf72af5d...`，并保存
   `git status --short` 与七文件 `git diff --stat`；
2. 对每个 full-revert 文件：
   - 用 `git diff -- <file>` 取得当前尚未提交增量；
   - 用 `git show HEAD:<file>` 只作为只读基线；
   - 通过 `apply_patch` 写入该文件的精确 inverse hunks；
   - 立即运行 `git diff --exit-code HEAD -- <file>`；
3. 对以下五个 selective 文件：
   - `dayu/cli/commands/init.py`
   - `dayu/cli/init_workspace.py`
   - `tests/cli/test_init_command.py`
   - `tests/cli/test_init_workspace.py`
   - `tests/cli/test_init_smoke.py`
   - 同样先用 inverse hunks 完整恢复到 HEAD；
   - 立即验证单文件对 HEAD 无 diff；
   - 再用新的、独立 `apply_patch` 只加入 S4-SC2 的最小 hunk；
4. 每个 patch 后运行 `git diff --check -- <file>`；
5. 确认五个 selective 文件的净 diff 只包含 §6 S4-SC2 明确允许的最小 hunks；
6. 最终确认以下两个 revert-only 文件对 HEAD 无 diff：
   - `dayu/runtime/config_loader.py`
   - `tests/runtime/test_config_loader.py`
7. 不删除、不覆盖任何 untracked review artifact；不 stage、不 commit。

该方法以包含 S1–S3 的 HEAD 为逐文件真源，只反转当前未提交 S4 hunks，因此不会撤销
S1–S3，也不会把其它 artifact 混入 scope。

Controller 驳回 DS 关于 `apply_patch` 可用性的 finding：Codex 内置
`apply_patch` 已由当前执行环境定义，本计划继续直接使用该工具；不得改成 shell
重定向、`cat`、Python 写文件或其它绕过方式。

## 8. Exact allowed files

plan review 接受后，implementation 的允许范围只有：

- revert-only、最终必须无净 diff：
  - `dayu/runtime/config_loader.py`
  - `tests/runtime/test_config_loader.py`
- 最小净实现/测试 diff：
  - `dayu/cli/commands/init.py`
  - `dayu/cli/init_workspace.py`
  - `tests/cli/test_init_command.py`
  - `tests/cli/test_init_workspace.py`
  - `tests/cli/test_init_smoke.py`
- Gateflow 记录：
  - `docs/reviews/wu-cli-init-01-s4-implementation-codex.md`

其它生产、测试、config、README、oracle 与 review artifact 全部禁止修改。若实现发现
必须修改其它 owner，立即 STOP 回到 plan review，不自行扩 scope。

## 9. Validation

所有命令先执行：

```bash
source .venv/bin/activate
```

### 9.1 Scope cleanup

```bash
git diff --exit-code HEAD -- \
  dayu/runtime/config_loader.py \
  tests/runtime/test_config_loader.py

git diff --check
```

预期：两个 revert-only 文件无 diff；剩余净 diff 只允许出现在 §8 列出的五个
最小实现/测试文件和 implementation artifact。

### 9.2 Focused tests

```bash
pytest tests/cli/test_init_workspace.py tests/cli/test_init_smoke.py -q
```

关键断言：

- 五类根配置逐项 PRESERVE 补缺；
- 已有用户内容保留；
- overwrite 重建 config 且 `.dayu` 不变；
- reset 清旧 `.dayu`、重建 config/init-owned assets、保留
  portfolio/non-init assets；
- ordinary corrupt state 由适用 destructive mode 恢复；
- 既有 rollback tests 恢复原 snapshot；
- 既有 symlink/special 拒绝不回归。

### 9.3 S1–S3 regression

```bash
pytest tests/cli/test_init_command.py tests/runtime/test_config_loader.py -q
```

预期：S2 profile source/静态 shape 与 S3 package defaults 全部保持，不依赖被撤销的
snapshot API 或 typed manifest。

### 9.4 Coverage、typing 与静态检查

```bash
coverage erase
coverage run -m pytest \
  tests/cli/test_init_workspace.py \
  tests/cli/test_init_smoke.py
coverage report --include='dayu/cli/init_workspace.py'

python -m pyright dayu/ tests/ utils/

python -m ruff check \
  dayu/cli/init_workspace.py \
  tests/cli/test_init_workspace.py \
  tests/cli/test_init_smoke.py

git diff --check
git status --short
```

验收条件：

- focused/regression tests 全绿；
- `dayu/cli/init_workspace.py` 单文件 coverage `>= 80%`；
- full pyright `0 errors`，无新增或扩散；
- ruff 与 diff check 通过；
- 工作树没有 out-of-scope code/test diff；
- 不以 `result.mode` 单独判定成功，必须以 bytes/digest/identity/tree 结果判定。

## 10. README decision

本 S4 只兑现 Goal 已冻结的 PRESERVE/mode 行为，README 的统一用户说明仍由 accepted
plan S6 负责。本 slice 不修改 README。implementation artifact 必须记录已检查
README 触发条件；若目标 README 的自身约束要求立即同步，则 STOP 回 plan review，
不能私自扩大本 slice allowed files。

## 11. 风险、非目标与停止条件

### 11.1 Blocking open questions

None。用户已明确裁决：

- 无并发文件系统竞态、TOCTOU、descriptor pinning、ctime/nlink 需求；
- 无增强 transaction 或新 rollback 机制需求；
- rollback 只表示复用现有机制并验证业务结果；
- symlink/special/非法 lock 只维持现有拒绝。

### 11.2 Residual risks

- 外部进程并发修改 workspace：`out of scope by explicit user decision`。
- ordinary-file managed root repair：`in-scope business result`；OVERWRITE 只修
  config，RESET 修 config / `.dayu`，按 §4.2 的最小分派完成。
- Windows reparse 的真实平台能力：沿用现有 S1–S3/S4 baseline 测试与 CI owner，
  本次不增加新契约。
- 现有 transaction fault coverage：由既有 tests 持续覆盖，不新增 matrix。

### 11.3 Stop conditions

出现任一情况立即停止并回 plan review：

1. PRESERVE 根配置补缺必须修改 ConfigLoader public contract；
2. 必须新增或改写 transaction / backup / publication / rollback state machine；
3. 必须新增 fd、descriptor、race、TOCTOU 或 metadata drift contract；
4. file-vs-directory cleanup 无法只复用既有 identity/quarantine helper并作最小
   unlink/rmtree 分派；
5. 必须改变 S2 已提交的 profile/lock 静态拒绝；
6. ordinary repair 必须扩大为 symlink、reparse 或 special-file recovery；
7. 发现七文件中有不属于当前 S4 partial implementation 的用户增量。

## 12. Completion report format

S4 implementation artifact 必须明确报告：

- 撤销了哪些 out-of-scope partial hunks；
- 最终净 changed files；
- PRESERVE 补缺与 mode 业务结果；
- 复用的现有 rollback tests 及结果；
- focused tests、S1–S3 regression、coverage、full pyright、ruff、diff check；
- README decision；
- remaining risks 及分类；
- completion signal；
- 下一入口：S4 code review。

## 13. Planning completion

- Goal boundary：已按唯一 goal artifact重新核对。
- 当前 diff：已核对七个 dirty code/test files。
- 原 plan 与 S4 amendments：已读取；其中 filesystem race、loader snapshot、
  typed manifest、descriptor-stable read 与新增 transaction/rollback state machine
  被本次用户裁决否定；mode-owned ordinary-file recovery 保留为 Goal business
  result。
- 最小生产 gap：PRESERVE 补齐五类根配置，以及 OVERWRITE/RESET 按 owner 修复
  ordinary-file managed roots。
- Implementation strategy：先以 `apply_patch` 精确清除 out-of-scope hunks，再加入
  PRESERVE 补缺、repair intent、ordinary-root snapshot/digest与最小
  file-vs-directory cleanup 分派及对应业务测试。
- Overdesign check：不新增 API、type、state machine、transaction mechanism、
  rollback mechanism、fault/race matrix 或 filesystem abstraction。
- Decision：`ready for plan review`。
- Current gate / next entry point：独立 plan review；本 artifact 完成后停止等待评审。
