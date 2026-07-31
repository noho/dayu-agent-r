# WU-CLI-INIT-01 S2 Code Review Adjudication

## Gate metadata

- Gate：`code review`
- Work unit：`WU-CLI-INIT-01`
- Slice：`S2 — Model family owner 与 init interaction state machine`
- Base：`53f6b7f6`
- implementation artifact：
  `docs/reviews/wu-cli-init-01-s2-implementation-codex.md`
- review artifacts：
  - `docs/reviews/code-review-20260730-152220.md`（AgentMiMo）
  - `docs/reviews/code-review-20260730-152426.md`（AgentDS）
- Artifact path：
  `docs/reviews/wu-cli-init-01-s2-code-review-adjudication-controller.md`
- decision：`fix-required`

## Findings adjudication

### S2-MIMO-001 — `_confirm_reset` stale raises docstring

- status：`accepted`
- severity：低
- 理由：实现已让非法 yes/no 原步骤重试，EOF 才抛
  `CliInitOperationError`；docstring 仍承诺 `CliInitUsageError`，违反项目中文完整
  docstring 与真实 contract 一致性要求。
- fix：更新异常说明；不改运行时行为。

### S2-CTRL-001 — PRESERVE workspace profile 未建立 no-follow regular-file 边界

- status：`accepted`
- severity：中
- 入口：`dayu.cli.commands.init._load_target_min_context_window(...)`。
- 输入场景：
  - `workspace/config/execution_profiles.json` 是指向 workspace 外部 regular file 的
    symlink；
  - 或是 dangling symlink / directory / special file。
- 实际分支：
  - `Path.exists()` 与 `ConfigLoader._load_layered_config_file(...)` 都 follow
    symlink；
  - ordinary symlink 会被直接读取；
  - dangling symlink 的 `exists()` 为 False，会被当成“workspace file missing”而
    静默采用 package layer。
- 预期行为：R03 只允许真实缺失采用 package layer；任何已占据该路径的非 ordinary
  regular file 都是非法 workspace profile，应在首个 model/secret prompt 前
  fail closed，提示 `--overwrite`，不得读取链接目标或 fallback。
- 直接证据：
  - 当前实现以
    `(workspace_config_dir / _EXECUTION_PROFILES_FILE_NAME).exists()` 分类；
  - ConfigLoader layering 同样以 `workspace_path.exists()` 决定是否 overlay；
  - `Path.exists()` 对 dangling symlink 返回 False，对普通 symlink 跟随目标。
- fix：
  - 在 CLI 直接上游用 no-follow stat/lstat 区分 absent 与 ordinary regular；
  - absent 才允许 typed loader 的 package layering；
  - symlink、dangling、directory、FIFO/其它 special 都在 loader 前抛 value-free
    `CliInitOperationError`，提示 `--overwrite`；
  - 测试断言 loader/model/secret/transaction 未发生、外部 symlink target 未读取或
    修改、零 managed publication；
  - 不在下游 ConfigLoader 结果上猜测 shape，不增加 fallback。
- 修复边界：本 finding 处理稳定静态 shape；并发外部进程在 stat 与 read 之间主动换
  path 的完全 TOCTOU 消除需要 ConfigLoader 的 fd/no-follow read contract，超出 S2
  approved files，归入 S4 no-follow transaction/path-safety slice。

### S2-MIMO-002 — profile 存在性检查与加载之间 TOCTOU

- status：`部分修复`
- severity：低
- 裁决：reviewer 以“init lock 内不可触发”为由接受并不充分，因为 init lock 不约束
  普通编辑器或其它进程。但在 S2 不扩展 ConfigLoader fd-based read public contract。
  当前 slice 修复静态 symlink/special 误分类；完全 race-free no-follow read 由 S4
  approved path-safety 工作覆盖。
- residual classification：`covered by later approved slice`。

### S2-MIMO-003 — Ollama template default 低于 minimum

- status：`rejected-with-reason`
- severity：低
- 理由：accepted plan 明确要求保留 Ollama template default，并让低于 target
  minimum 的默认或显式输入在 context 原步骤报错/retry。当前实现与测试精确满足；
  改成 `max(template, minimum)` 会改变已接受交互 oracle，不能作为 code review
  cleanup 偷改。

### S2-DS residual — execution profile 文件名重复

- status：`deferred-with-owner`
- 理由：ConfigLoader 是配置文件名 owner；当前 CLI adapter 的重复私有常量只用于
  upstream shape classification。S4 会以 `config_file_names()` 和 managed-file
  manifest 统一 no-follow shape 检查，届时删除 adapter 重复。
- residual classification：`covered by later approved slice`。

### S2-DS residual — 非数值 port

- status：`证据失效`
- 理由：Python 3.11 的 `urlsplit(...).port` 对非数值 port 与越界 port 均抛
  `ValueError`；`validate_dynamic_endpoint(...)` 已捕获并转为
  `InitCatalogError`。不存在“返回 None 后跳过”的分支。

## Fix acceptance criteria

1. 只修改 S2 approved files/tests 与 fix artifact。
2. 修复 stale docstring。
3. PRESERVE workspace profile 静态路径必须 no-follow 分类；只有真实 absent 能用
   package layer。
4. symlink、dangling、directory、special cases 有 owner-level tests，且发生在任何
   model/secret/transaction/publication 之前。
5. focused tests、coverage、pyright、ruff、`git diff --check` 通过。
6. AgentMiMo 与 AgentDS 对 fix 做独立 re-review，accepted findings 均为`已修复`后
   才能接受 S2 commit。

## Next entry point

AgentCodex 执行 S2 fix；不得进入 S3。

## Final re-review

- `docs/reviews/code-review-20260730-153912.md`（AgentMiMo）：无新 finding。
- `docs/reviews/code-review-20260730-153933.md`（AgentDS）：无新 finding。
- `S2-MIMO-001`：`已修复`。
- `S2-CTRL-001`：`已修复`。
- `S2-MIMO-002`：`部分修复`；静态 shape 已修复，完整 TOCTOU residual
  `covered by later approved slice`（S4）。
- `S2-MIMO-003`：`rejected-with-reason`，证据保持有效。
- 重复配置文件名 residual：`covered by later approved slice`（S4）。
- blocking open questions：无。
- unclassified residual risks：无。

Controller validation：

- focused tests：`120 passed`。
- affected-scope pyright：`0 errors, 0 warnings, 0 informations`。
- affected-scope ruff：`All checks passed!`。
- `git diff --check`：通过。

Final gate decision：

- code review：`pass`
- fix：`pass`
- re-review：`pass`
- next entry point：`accepted slice commit`
