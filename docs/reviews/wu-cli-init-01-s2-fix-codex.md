# WU-CLI-INIT-01 S2 Code Review Fix

## Gate metadata

- Gate：`code review -> fix`
- Work unit：`WU-CLI-INIT-01`
- Slice：`S2 — Model family owner 与 init interaction state machine`
- 日期：2026-07-30
- Base：`53f6b7f6`
- adjudication artifact：
  `docs/reviews/wu-cli-init-01-s2-code-review-adjudication-controller.md`
- Artifact path：
  `docs/reviews/wu-cli-init-01-s2-fix-codex.md`
- decision：`fix-complete-awaiting-re-review`

## Scope

本轮只修复裁决接受的两个 finding：

- `S2-MIMO-001`：`_confirm_reset(...)` 的 raises docstring 与真实确认 contract
  不一致。
- `S2-CTRL-001`：PRESERVE workspace `execution_profiles.json` 在进入
  `ConfigLoader` 前缺少 no-follow ordinary-file 分类。

未修改 `ConfigLoader`、S3、S4 transaction/path-safety、package defaults、
Service、README、accepted oracle 或 plan；未提交。

## Semantic owner decisions

- RESET confirmation 的异常 contract 由 `dayu.cli.commands.init` 的交互 owner
  承诺；`_confirm_reset(...)` 只记录 `_confirm(...)` 已实现的 EOF、SIGINT 与 I/O
  传播语义。
- 锁内 target mode 到 execution profile source 的选择与直接上游 shape 分类由
  `dayu.cli.commands.init._load_target_min_context_window(...)` 拥有。
  `ConfigLoader` 继续唯一拥有 JSON layering/schema/typed profile 解析；本轮不在
  loader 结果或下游消费者中反推路径 shape。
- no-follow 分类只承诺静态 shape：
  - `FileNotFoundError` 表示 workspace profile absent，允许现有 typed package
    layering；
  - `stat.S_ISREG(...)` 表示 ordinary regular file，允许现有 workspace typed load；
  - symlink、dangling symlink、directory、FIFO/其它 special mode 均在 loader 前
    以 value-free `CliInitOperationError` fail closed，并提示 `--overwrite`。

## Changed files

- `dayu/cli/commands/init.py`
- `tests/cli/test_init_command.py`
- `docs/reviews/wu-cli-init-01-s2-fix-codex.md`

## Implemented changes

1. 将 `_confirm_reset(...)` 的异常说明改为：
   - EOF 抛 `CliInitOperationError`；
   - `KeyboardInterrupt` 原样透传；
   - 输入或诊断 `OSError` 原样透传。
   运行时行为未修改。
2. 新增模块级 `_workspace_execution_profile_is_regular_file(...)`：
   - 使用 `os.stat(path, follow_symlinks=False)`；
   - 只把 `FileNotFoundError` 归为 absent；
   - 只接受 `stat.S_ISREG(...)`；
   - 非普通 shape 的错误文本不包含路径、目标、原始配置值或底层异常文本。
3. `_load_target_min_context_window(...)` 在构造 `ConfigLoader` 前调用上述 owner
   helper；非普通路径不能读取链接目标，也不能采用 package fallback。
4. 新增锁内 owner-level 对抗测试：先完成真实 unlocked/locked snapshot 复核，再把
   profile 路径替换为 ordinary symlink、dangling symlink、directory 或 FIFO，证明
   静态分类时：
   - `ConfigLoader` 未构造；
   - model selection 未发生；
   - secret plan/getpass 未发生；
   - transaction prepare 未发生；
   - publication 未发生；
   - 外部 symlink target 字节未读入诊断且未被修改；
   - 既存 `models.json`、durable sentinel 与 transaction-private root 保持。

## Finding status

### S2-MIMO-001

- status：`已修复`
- evidence：`_confirm_reset(...)` docstring 现在与 `_confirm(...)` 真实 EOF/interrupt/
  I/O contract 一致；无运行时改动。

### S2-CTRL-001

- status：`已修复`
- evidence：PRESERVE profile 静态路径在 ConfigLoader 前使用 no-follow stat 分类；
  absent/ordinary regular 与 symlink/dangling/directory/FIFO-special 的测试矩阵通过，
  非普通 shape 全部 value-free fail closed 并提示 `--overwrite`。

### S2-MIMO-002

- status：`部分修复`
- evidence：静态 symlink/special 误分类已消除。
- residual：stat 与 ConfigLoader read 之间被外部进程替换路径的完全 TOCTOU 仍需
  fd/no-follow read contract；按 controller 裁决归 S4。

## Validation

- focused tests：

  ```text
  source .venv/bin/activate
  pytest tests/runtime/test_assembly_helpers.py \
    tests/cli/test_init_catalog.py tests/cli/test_init_command.py -q
  ```

  结果：`120 passed`。

- 单文件 coverage：

  ```text
  coverage erase
  coverage run -m pytest tests/runtime/test_assembly_helpers.py \
    tests/cli/test_init_catalog.py tests/cli/test_init_command.py -q
  coverage report \
    --include='dayu/runtime/assembly.py,dayu/cli/init_catalog.py,dayu/cli/commands/init.py'
  ```

  结果：
  - `dayu/cli/commands/init.py`：`95%`
  - `dayu/cli/init_catalog.py`：`90%`
  - `dayu/runtime/assembly.py`：`92%`
  - 合计：`92%`

- affected-scope pyright：

  ```text
  python -m pyright dayu/runtime/assembly.py dayu/cli/init_catalog.py \
    dayu/cli/commands/init.py tests/runtime/test_assembly_helpers.py \
    tests/cli/test_init_catalog.py tests/cli/test_init_command.py
  ```

  结果：`0 errors, 0 warnings, 0 informations`。

- Ruff：

  ```text
  python -m ruff check dayu/runtime/assembly.py dayu/cli/init_catalog.py \
    dayu/cli/commands/init.py tests/runtime/test_assembly_helpers.py \
    tests/cli/test_init_catalog.py tests/cli/test_init_command.py
  ```

  结果：`All checks passed!`。

- `git diff --check`：通过。

## Docs decision

- README 不更新。测试仍属于现有 CLI init 四态与 fail-closed 测试层级，没有新增测试
  层级或运行方式；work-unit 级最终用户说明仍按 accepted plan 由 S6 统一同步。
- 本轮只新增 controller 要求的 fix artifact。

## Residual risks

- stat 成功后、ConfigLoader 真正读取前，外部进程仍可替换
  `execution_profiles.json`。完全消除需要让读取 owner 提供 fd-based/no-follow read
  contract，超出 S2 approved files。
  - classification：`covered by later approved slice`
  - owner/destination：WU-CLI-INIT-01 S4 no-follow transaction/path-safety。
- S3 package defaults 与 Service runtime family comparison 未修改。
  - classification：`covered by later approved slice`

## Completion

- Completion signal：`fix-complete`
- Next entry point：AgentMiMo / AgentDS 独立 S2 re-review。
- Commit：未创建。
