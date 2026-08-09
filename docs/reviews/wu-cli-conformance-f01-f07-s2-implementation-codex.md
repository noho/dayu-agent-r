# WU-CLI-CONFORMANCE-F01-F07 S2 Implementation 记录（Codex）

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- PR：`190`
- Slice：`S2 / F02 — external editor`
- Gate：`implementation`
- Accepted S1 commit / entry HEAD：`a41526ecbf5c1d16c24a19114b0d0e21208d1dd0`
- 分支：`codex/interactive-oracle`
- 状态：`CODE-REVIEW FIX COMPLETE — next: S2 dual re-review`
- Artifact：`docs/reviews/wu-cli-conformance-f01-f07-s2-implementation-codex.md`

## Preflight、直接证据与 owner

实施前 `git status --short` 与 `git diff --cached --name-only` 均无输出，HEAD
精确为用户指定的 S1 accepted commit。F02 的直接证据与 accepted plan §4 已充分
收口，无 blocker：

- frozen `observed-behavior-pr190-closeout.md` SHA-256 为
  `6aa8c8c7430e979b95f3bd8551f44ae34432e5e55172231c296d634932aa712f`；
  其中 missing 显式 editor 错误进入系统 pico，证明当前实现违反“显式配置不
  fallback”。
- frozen `compaction-invalid-response-audit-pr190.md` SHA-256 为
  `fed1a2ae29baf2b59b3d16d90460661c563ae18233f93530b241645ada38fb61`，
  与 plan §0.1 固定值一致。
- 当前验证环境是 `prompt_toolkit 3.0.52`，项目声明仍为 `>=3.0.0`。直接核验的
  public signatures 为 `run_in_terminal(func, render_cli_done=False,
  in_executor=False) -> Awaitable[T]`、`Buffer.open_in_editor(
  validate_and_handle=False) -> asyncio.Task[None]` 与 public
  `Buffer.document` setter；实现不 pin 版本、不调用 private API。
- 唯一语义 owner 是 `dayu.cli.composer`：它拥有 editor 环境选择、本地草稿、
  cursor、History、错误投影、tempfile 和 async task lifecycle。screen projection、
  Service、Host、Engine 与测试替身都没有反推或重算该语义。

## Scope

实际 production/test 修改严格只有：

- `dayu/cli/composer.py`
- `tests/cli/test_interactive_composer.py`
- `tests/cli/test_interactive_command.py`

另新增本 gate 唯一允许 artifact。未修改 README、design、registry、Host、Service、
Engine、依赖声明或其它文件；未 stage、commit、push 或操作 PR。

## 实现决策与 contract

### 显式配置解析

- 增加 plan 固定的 typed `_EditorEnvironmentVariable`、
  `_ExplicitEditorCommand`、`_EditorConfigurationError` 与
  `_EditorProcessOutcome` contract。
- 以 key presence 而非 truthiness 决策：`VISUAL` key 存在即优先，失败时绝不尝试
  `EDITOR`；只有两个 key 都不存在才返回 public system fallback。
- 空白、`shlex.split` 非法/空 argv、missing、目录与 non-executable 都在 launch
  前形成稳定、actionable、脱敏的配置错误。含路径分隔符使用规范化 `Path`，其它
  命令使用 `shutil.which`；最终必须是可执行普通文件。

### CLI-owned explicit launcher

- 冻结 original public `Buffer.document`，以 `NamedTemporaryFile(delete=False)`
  建立 secure CLI-owned UTF-8 tempfile，并在所有 terminal path 的 `finally` 中
  删除。
- public `run_in_terminal(..., in_executor=True)` 执行 exact argv：resolved
  executable、原显式参数、唯一 tempfile 路径；`subprocess.run` 不使用 shell，
  不枚举候选、不 fallback。
- spawn `OSError` 只投影一次 actionable 脱敏错误；进程任意 nonzero 精确形成
  silent `CANCELLED`；两者都保留 original document。
- 只有 return code zero 才读取 raw bytes 并严格 UTF-8 decode，避免 text mode
  隐式改写 CRLF；CLI frozen rule 只移除至多一个末尾 LF。读取成功后仅通过 public
  `buffer.document = Document(...)` 一次原子回填；读取/解码失败保持原 document。
- 显式配置的 argv、底层异常正文、env 内容与 tempfile path 均不进入 diagnostic。

### fallback 与 async lifecycle

- 只有 `VISUAL`、`EDITOR` 两个 key 都不存在时，调用 public
  `Buffer.open_in_editor(validate_and_handle=False)`；CLI-owned launcher 此时零调用。
- composer 以强引用集合持有显式 editor task；done callback 消费 outcome/异常且
  只在 owner 处投影错误。`read_event` teardown 取消、等待并消费 pending task，
  tempfile 始终进入 cleanup；没有 unhandled-task traceback 或 pending-task warning。
- editor 动作本身从不产生 composer submit event；失败/cancel 后同一 REPL 继续，
  draft、cursor、History 不变，只有用户后续显式 Enter 才能创建 Run。

## Owner-level tests

`tests/cli/test_interactive_composer.py` 覆盖：

- typed `VISUAL` priority、`EDITOR` selection 与 truly-unset 三分支；显式空白不会
  降级到 `EDITOR` 或 system fallback。
- 空白、非法 quoting、missing、目录、nonexec 的 launch-before-failure 矩阵：
  `run_in_terminal`/fallback 零调用，document/cursor 保留，actionable 且无 traceback。
- unset 精确调用 public `open_in_editor(False)`，CLI launcher 零调用。
- zero exact argv、`in_executor=True`、secure tempfile cleanup、raw UTF-8/CRLF 保留、
  最多一个末尾 LF 删除与 public document 单次回填。
- spawn `OSError`、nonzero、invalid UTF-8 readback：分别为 actionable、silent cancel、
  actionable；均无 fallback、无敏感内容、保留 document 并清理 tempfile。
- EDITOR_PENDING teardown 取消并消费 task，清空强引用，删除仍存在的 tempfile，
  stderr 无 traceback。

`tests/cli/test_interactive_command.py` 使用真实
`PromptToolkitInteractiveComposer -> _drive_interactive_tty_repl` integration，参数化
missing、nonexec、spawn `OSError`、nonzero：

- Ctrl-X Ctrl-E 后先断言零 `SubmitFollowupRequest`、空 History；
- 原 `abc` 草稿的 cursor 位于 `c` 前，失败/cancel 后输入 `X` 并显式 Enter，唯一
  Run 的 prompt 精确为 `abXc`，证明 draft/cursor 保留；
- submit 后 History 精确为 `abXc`，随后 Ctrl-D 正常退出同一 REPL；
- actionable 三类含修复动作且无 traceback/secret，nonzero stderr 精确为空；
- public system fallback 安装“调用即失败” sentinel，显式矩阵全部零 fallback；
  process case 只调用一次 exact argv，tempfile 已删除。

## 验证结果

### Focused pytest 与单文件 coverage

```bash
source .venv/bin/activate
pytest tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py \
  --cov=dayu.cli.composer --cov-report=term-missing --cov-fail-under=80 -q
```

结果：`99 passed, 3 warnings in 8.16s`；三条 warning 均为 `edgar` 依赖的既有
deprecation warning。`dayu/cli/composer.py` 为 `356 statements / 33 missing / 91%`，
达到单文件 `>=80%` 要求。

### Focused pyright

```bash
source .venv/bin/activate
python -m pyright dayu/cli/composer.py \
  tests/cli/test_interactive_composer.py \
  tests/cli/test_interactive_command.py
```

结果：`0 errors, 0 warnings, 0 informations`。

额外运行全仓 `python -m pyright`，观察到两个位于本 slice allowlist 外的
S1 request-field residue：

- `utils/smoke_cli_init_provider_matrix.py:2386` 仍传
  `EntrypointRuntimeRequest.explicit_config_dir`；
- `utils/smoke_host_public_awaiting_entrypoint.py:808` 同样仍传该已删除参数。

这两个错误不来自 S2 diff，focused 三文件保持零错误；但原记录把它们称为
“existing debt / covered by later approved slice S8”不准确。直接比较 S1 accepted
commit `a41526ec` 及其 parent 可见：parent 的
`EntrypointRuntimeRequest` 仍声明 `explicit_config_dir`，S1 commit 删除该字段，
同时 S1 对上述两个 `utils` call site 没有 diff。因此它们是 **S1 引入的
cross-slice regression**，不是 existing debt，也不属于 S8 aggregate closure。
S2 仍严格不修改 `utils/`；S2 accepted 后、进入 S3 前须由独立 S1 corrective
fix/review/re-review/commit gate 机械删除两个旧 keyword，并以 full pyright 零错误
为 acceptance signal，禁止恢复兼容字段。

### 完整性、registry 与 source contract

- `git diff --check`：通过。
- `python -m json.tool docs/cli_ci_oracles.json`：通过。
- `python -m json.tool docs/cli_ci_scenarios.json`：通过。
- Registry SHA-256 保持：
  - `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
  - `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`
- `git diff --cached --name-only`：无输出，index 为空。
- artifact 写入前 `git status --short` 与 `git diff --name-only` 仅列三个允许的
  production/test path；artifact 写入后应精确再增加本文件。
- source contract scan：production 只有 public `run_in_terminal`、unset public
  `open_in_editor(False)` 与 public `buffer.document`；`_open_file_in_editor`、
  `shell=True`、private prompt_toolkit API 均零命中。

## Docs decision

accepted plan 将 README/design 同步固定在 S8。本 slice 没有改变 F02 scope 之外的
用户入口、分层关系或依赖声明，因此不提前修改 README/design；frozen registry 与
`docs/cli_ci.md` 保持只读。

## Residual risks 与未覆盖项

- `covered by later approved slice S8`：真实 PTY 下不同 editor 的 terminal
  suspend/resume、最终真实 CLI evidence 与 full-suite aggregate closure。
- `assigned to S1 corrective gate before S3`：两处 `utils` 旧
  `explicit_config_dir` keyword；它们是 S1 引入的 cross-slice regression，
  不得再分类为 existing debt 或 S8 工作。
- `covered by current owner invariant`：显式 argv 不经过 shell，配置错误、spawn、
  nonzero、readback 与 teardown 都只由同一 composer owner 产生/投影；screen
  projection 不是判断真源。
- 当前没有未分类的 S2 residual risk，没有发现需要扩大 production/test allowlist
  的 owner defect。

## Completion 与下一入口

S2 implementation 与 accepted code-review fix 已完成，代码、测试与 artifacts 均未
stage。当前按用户指令停止，不进入 commit、push 或 PR 操作。下一合法入口为
**S2 dual re-review**。

## Code-review fix 追加记录

总控 accepted `S2-C01`–`S2-C04` 已由 composer owner 收口：

- `S2-C01`：round trip 以显式 `primary_failure` 控制流状态保留任何正在传播的
  primary exception；`finally` 仍始终尝试 tempfile unlink，只有不存在 primary 时
  cleanup failure 才形成 `CLEANUP_FAILED`。未增加 rollback、重试或新 filesystem
  产品语义。
- `S2-C02`：`_open_explicit_editor` 在同步按键 call path 读取一次完整 public
  `Buffer.document`，并以必填 `original_document` 参数传入 async round trip；task
  首调度前的 buffer 变化不再污染 editor 输入 snapshot。
- `S2-C03`：复用 composer 既有 editor task set 作为唯一 `EDITOR_PENDING` 真源；
  set 非空时重复快捷键直接 no-op，显式与 unset public task 都占用同一 slot，完成或
  teardown 后释放，不新增第二状态机。
- `S2-C04`：`updated_text` 改为严格 `str`，删除不可达 `None` 分支。

新增 owner tests 覆盖 spawn/readback primary + cleanup 双故障、
`CancelledError` + cleanup 双故障、同步 `Document` snapshot，以及 pending 时重复
快捷键只有一个 round trip task、一个 process、一次 public buffer write。
integration contract 未改变，故未修改 `tests/cli/test_interactive_command.py` 的 fix
内容。Fix 细节、验证与 residual disposition 见
`docs/reviews/wu-cli-conformance-f01-f07-s2-fix-codex.md`。
