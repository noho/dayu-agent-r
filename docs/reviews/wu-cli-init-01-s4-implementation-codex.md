# WU-CLI-INIT-01 S4 Implementation

## Gate metadata

- Gate：`implementation`
- Work unit：`WU-CLI-INIT-01`
- Slice：`S4 — Managed whole-tree modes 与 repair`
- 唯一目标边界：
  `docs/reviews/wu-cli-init-01-goal-confirmation-controller.md`
- Accepted scope plan：
  `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-codex.md`
- Plan adjudication：
  `docs/reviews/wu-cli-init-01-s4-scope-correction-plan-adjudication-controller.md`
- S1–S3 代码恢复基线：`cf72af5db284e60f0d75d4a7654e3b066b728255`
- 执行时 branch HEAD：
  `b0ff027d6f613e219f17e55008838bfac822be86`
  （相对 `cf72af5d` 只新增已提交的 S4 scope-correction review artifacts）
- 状态：`PASS — implementation complete`
- commit：未创建；用户明确要求不提交
- Artifact path：
  `docs/reviews/wu-cli-init-01-s4-implementation-codex.md`
- 下一入口：`S4 code review`

## 第一性原理与 owner 裁决

动机成立。直接代码证据确认：

1. PRESERVE staging 的 owner
   `dayu.cli.init_workspace._build_staged_config(...)` 只补缺失 prompts，没有补
   `config_file_names()` 的五类根配置；
2. managed-root snapshot 默认只接受 ordinary directory，导致显式 OVERWRITE /
   RESET 无法接管 ordinary regular file 占据的精确 managed root；
3. 现有 publication 已用 `os.replace` 把 root 移入 backup，现有 rollback record
   与 restore loop 同时适用于 file/directory；真实缺口仅是 snapshot admission 和
   success cleanup 的 `unlink` / `rmtree` 分派；
4. 因此不需要新增 transaction、backup、publication、rollback state machine，
   也不需要 descriptor/race/metadata contract。

语义 owner 保持不变：

- CLI destructive flags -> repair intent：
  `dayu.cli.commands.init`；
- managed-root identity/content snapshot、PRESERVE staging、private cleanup：
  `dayu.cli.init_workspace`；
- 五类根配置名称：
  既有 `dayu.runtime.config_loader.config_file_names()`；
- 模型字段投影：
  既有 `apply_model_selection(...)` /
  `project_known_manifest_models(...)`；
- publication/rollback：
  既有 transaction owner，未改写。

## Baseline restoration

按 accepted plan，先对以下七个 partial code/test files 逐文件执行：

1. 只读取得当前文件相对 `cf72af5d` 的 diff；
2. 通过 Codex 内置 `apply_patch` 写入精确 inverse hunks；
3. 每个文件立即运行
   `git diff --exit-code cf72af5d -- <file>`；
4. 每个文件立即运行 `git diff --check -- <file>`。

七个文件均先达到单文件零 diff：

- `dayu/cli/commands/init.py`
- `dayu/cli/init_workspace.py`
- `dayu/runtime/config_loader.py`
- `tests/cli/test_init_command.py`
- `tests/cli/test_init_workspace.py`
- `tests/cli/test_init_smoke.py`
- `tests/runtime/test_config_loader.py`

没有使用 `git restore`、`git checkout`、`git reset`、shell 重定向、`cat` 或
Python 写文件。没有修改或删除其它 untracked amendment artifacts。

最终以下两个 revert-only 文件继续对 `cf72af5d` 保持零 diff：

- `dayu/runtime/config_loader.py`
- `tests/runtime/test_config_loader.py`

已删除且未保留的 out-of-scope partial design：

- fd-relative reader / descriptor pinning；
- ConfigLoader snapshot/bytes loader；
- typed filename manifest；
- `_WorkspaceProfileDescriptorState` / `_PrivatePathShape`；
- descriptor stable state、`st_ctime_ns`、`st_nlink`；
- race/fault matrix 与新的 transaction/rollback contract。

## Exact implementation diff

最终 tracked code/test diff 只有五个 accepted files：

```text
dayu/cli/commands/init.py        |  22 ++++
dayu/cli/init_workspace.py       | 145 +++++++++++++++++++--
tests/cli/test_init_command.py   |  21 +++
tests/cli/test_init_smoke.py     |  73 +++++++++++
tests/cli/test_init_workspace.py | 274 ++++++++++++++++++++++++++++++++++++++-
5 files changed, 522 insertions(+), 13 deletions(-)
```

### `dayu/cli/commands/init.py`

- 新增单一私有 `_requested_repair_mode(...)`，只把 flags 投影为
  `InitMode.OVERWRITE | InitMode.RESET | None`；
- lock 前与 lock 内两次 `snapshot_managed_roots(...)` 显式传入同一 repair
  intent；
- `_load_target_min_context_window(...)` 保持 `cf72af5d` 的 path-based
  `ConfigLoader.load_execution_profiles(...)` contract，无 snapshot loader 或 fd
  reader。

### `dayu/cli/init_workspace.py`

- PRESERVE copy 后、prompt 补缺前调用
  `_copy_missing_root_config_files(...)`，只补 `config_file_names()` 中缺失项；
- 已存在根配置 bytes 不由补缺 helper 修改，corrupt existing file 不被覆盖；
- `snapshot_managed_roots(...)` 只按显式 repair intent 接受：
  - OVERWRITE：`config` ordinary regular file；
  - RESET：`config` / `.dayu` ordinary regular files；
  - 无 intent 或 OVERWRITE 下 `.dayu` regular file：继续拒绝；
- regular-file snapshot 使用既有 no-follow `PathIdentity` 分类后进行普通 SHA-256
  内容读取；没有 pre/post descriptor state、ctime/nlink 或竞态承诺；
- `_require_snapshot_unchanged(...)` 以 request 的 destructive mode 重取相同类型
  snapshot；
- `_cleanup_private_path(...)` 在 identity/quarantine 不变量保持不变的前提下，
  直接以既有 `expected_identity.mode` 为真源：
  regular file 用 `os.unlink`，directory 继续既有 capability gate +
  `shutil.rmtree`；
- `backup_records` 保持 HEAD 3-tuple；
  `_rollback_or_raise(...)` signature、tuple unpacking、restore loop 无净 diff；
  `_post_publication_cleanup(...)` 未增加 shape 参数。

### Tests

- 五类 `config_file_names()` 逐项证明 PRESERVE staging 补缺并保持其它根配置
  bytes；
- command 四态测试证明 lock 前后 snapshot 收到同一 repair intent；
- owner 级 ordinary-root matrix 证明无 flag 拒绝、OVERWRITE 只接管 config、
  RESET 接管 config/.dayu；
- cleanup owner test证明 regular file 走 unlink、directory 继续走 rmtree；
- malformed ordinary config 证明 PRESERVE 零发布并保留原 truth，OVERWRITE /
  RESET 可恢复；
- 真实 POSIX smoke 扩展：
  - PRESERVE 补一个代表性根配置；
  - OVERWRITE 恢复 corrupt ordinary config；
  - OVERWRITE 恢复 config ordinary file并保留 `.dayu`；
  - RESET 恢复 config/.dayu ordinary files并保留 portfolio/assets；
  - 最终 config 由真实 ConfigLoader、Service discovery 与 scene preparation
    重载。

## Validation

所有 Python 命令均先执行 `source .venv/bin/activate`。

### Focused

```text
pytest tests/cli/test_init_workspace.py tests/cli/test_init_smoke.py -q
128 passed, 5 skipped, 3 warnings in 25.49s
```

5 个 skip 为当前 Darwin 上既有平台条件 skip。Focused suite 包含并通过 accepted
plan 指定的既有 rollback owners：

- `test_publication_replace_failure_rolls_back_original_config`
- `test_publication_replace_fault_matrix_restores_snapshot`
- `test_reset_each_root_backup_fault_restores_both_roots`
- `test_posix_publication_sync_fault_rolls_back`
- `test_posix_rollback_sync_fault_reports_durability_and_current_truth`

### S1–S3 regression

```text
pytest tests/cli/test_init_command.py tests/runtime/test_config_loader.py -q
176 passed, 3 warnings in 2.89s
```

这证明恢复后的 profile source/static shape 与 ConfigLoader public contract 不依赖被
撤销的 snapshot API 或 typed filename manifest。

### Coverage

```text
coverage erase
coverage run -m pytest \
  tests/cli/test_init_workspace.py \
  tests/cli/test_init_smoke.py
coverage report --include='dayu/cli/init_workspace.py'
```

结果：

```text
128 passed, 5 skipped, 3 warnings
dayu/cli/init_workspace.py  588 statements  77 missed  87%
```

单文件 coverage `87%`，通过 `>= 80%` 目标。

### Typing / lint / diff

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

python -m ruff check \
  dayu/cli/init_workspace.py \
  tests/cli/test_init_workspace.py \
  tests/cli/test_init_smoke.py
All checks passed!

git diff --check
PASS
```

最终 scope checks：

- `dayu/runtime/config_loader.py` 对 `cf72af5d` 零 diff；
- `tests/runtime/test_config_loader.py` 对 `cf72af5d` 零 diff；
- tracked diff 仅五个 accepted code/test files；
- `backup_records` / `_rollback_or_raise(...)` /
  `_post_publication_cleanup(...)` 没有 scope-correction 禁止的 shape/state diff；
- 其它 untracked amendment artifacts 原样保留；
- 未 stage、未 commit。

## README decision

已读取并检查根 `README.md` 的 `Agent更新约束【必须遵守】` 与
`tests/README.md` 的职责：

- 本 S4 的 PRESERVE 根配置补缺会使根 README 当前“只补 prompt”的用户文案需要
  最终同步；
- accepted plan 已明确由 S6 统一更新用户说明，本 slice 的 exact allowed files
  禁止修改 README，因此本次不扩大 scope；
- tests 没有新增测试层级或新的全局运行方式，`tests/README.md` 无需本 slice
  更新。

## Residual risks / uncovered areas

1. 外部进程并发 mutation / TOCTOU：
   - 不属于 accepted S4 contract，用户已明确否决本 WU 引入该契约；
   - classification：`requiring new issue or explicit user decision`，只有未来重新
     接受该目标时才进入新 work unit。
2. Windows ordinary-file publication 的真实平台 smoke：
   - 当前本地为 Darwin，Windows 条件测试未在本机执行；
   - classification：`tracked by existing issue`，跨平台 CI owner 为 GitHub
     Issue `#184`；本次未扩大 Windows/reparse contract。
3. 根 README 的最终用户文案同步：
   - classification：`covered by later approved slice`；
   - owner：`WU-CLI-INIT-01 S6`。

没有未分类 residual risk，没有 blocking open question。

## Completion

- completion：`PASS`
- stop-condition audit：
  - 未新增或改写 transaction/rollback state machine；
  - 未新增 fd/descriptor/race/ctime/nlink contract；
  - 未扩大 symlink/reparse/special-file recovery；
  - ordinary-file cleanup 仅复用既有 identity/quarantine helper并作
    unlink/rmtree 最小分派。
- current gate：S4 implementation 完成
- next entry point：`S4 code review`
- commit：按用户要求未创建
