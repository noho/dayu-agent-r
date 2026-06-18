# WU CLI Output Channels Plan

Gate: Plan Gate
Work unit: Dayu CLI 输出通道拆分
Branch: `wu-cli-activity-01`
日期: 2026-06-17
执行者: AgentCodex

## goal / motivation / success signal

目标：

- 新增全局 `--log-file <path>`，用于把 Dayu 诊断日志写入指定文件；该参数与 `--debug` / `--verbose` / `--info` / `--quiet` / `--log-level` 正交，只改变日志 sink，不改变日志 level。
- `--log-file` 必须像现有全局参数一样支持写在 command 前或 command 后，并覆盖 `prompt`、`interactive`、Session、init 和 Fins direct commands。
- `prompt` 增加 `--detail` / `--no-detail`，默认 `--no-detail`；只有 `--detail` 才显示 Agent activity stream。
- 把 activity stream 从“logging stderr 诊断”语义中拆出：activity 是用户运行态 UI 事件，不受日志 level 控制；日志是诊断，不承载 activity UI。
- `interactive` 的 activity / transcript view 进入 CLI 层运行态 UI 边界：先实现 `InteractiveRunView` / `ActivitySink` 窄协议与非 full-screen 终端 sink，并支持快捷键切换 transcript / activity view。
- 不修改 Host / Engine public API 或 contracts；如实现中发现必须修改，立即标为 blocker，不继续硬改。

动机判断：

- 问题真实存在。当前 CLI 已经把诊断日志和用户输出分离，但 activity 仍以 stderr 单行形式展示，用户很容易把它理解为日志；同时 `prompt` TTY 默认显示 activity，不符合“默认安静，只在 detail 模式显示运行态细节”的 CLI 预期。
- 严重性中等偏高。它影响 CLI 输出契约、脚本可组合性和交互体验，但已有 Service `on_activity` 回调足以承载新 UI，不需要触碰 Host / Engine。
- 用户指定路径基本成立，但不应把 `--log-file` 下沉到每个业务命令或 Fins Service；最佳实现点是 CLI composition root 与现有全局 parser parent。

成功信号：

- `dayu-cli --log-file /tmp/dayu.log prompt "..."` 与 `dayu-cli prompt "..." --log-file /tmp/dayu.log` 都解析成功，日志写入文件，stdout 仍只包含 final answer。
- `dayu-cli download --ticker AAPL --verbose --log-file /tmp/dayu.log` 把 Fins direct VERBOSE/DEBUG 诊断写入文件，Fins progress / summary 仍按现有 stdout/stderr 用户通道输出。
- `dayu-cli prompt "..."` 默认不显示 activity；`dayu-cli prompt "..." --detail` 才显示 activity。
- `--debug` / `--verbose` 不会打开 activity；`--detail` 不会提升日志级别。
- interactive TTY 路径的 activity 和 transcript 由 CLI 运行态 view/sink 管理，快捷键可切换当前 view；非 TTY 路径保持脚本友好的 stdout/stderr 行为。
- 受影响测试与 pyright 通过，README 决策完成。

## non-goals / scope

非目标：

- 不新增 Host / Engine public API、EventLog schema、Runner event contract、tool schema 或 durable schema。
- 不把 CLI direct Fins command 建模为 Host Run，也不引入 durable job、后台 job id 或 sidecar cursor。
- 不重写整体 CLI 框架，不引入 rich/textual 等新 TUI 框架；现有 prompt_toolkit 是 interactive 输入态依赖，优先复用。
- 不在本 work unit 中把运行态迁入 prompt_toolkit `Application.run_async()`，也不让 `PromptSession` 管理运行态 view；若 full-screen prompt_toolkit Application 是必要条件，停止 Slice C 并拆为后续独立 work unit。
- 不改变 final answer stdout 契约；prompt final answer 仍写 stdout，错误仍写 stderr。
- 不改变 Fins direct `FinsEvent` / `FinsResultSummary` 语义。
- 不为旧行为保留兼容开关；旧的“TTY prompt 默认显示 activity”会被新默认 `--no-detail` 替代。

Scope boundary：

- 允许修改 `dayu/cli/*`、`dayu/runtime/log.py` 中日志 handler 生命周期的小幅实现、相关 `tests/cli` / `tests/runtime` 测试和按触发规则需要更新的 README。
- 仅在确认 runtime log 现有 stream override 无法安全管理文件 handler 生命周期时，才修改 `dayu/runtime.log` 的内部 handler reset/close 行为；不新增上层业务语义到 runtime。
- Service `dayu.service.entrypoint_runtime` 只作为 evidence；当前计划不修改它。

## design document alignment

无独立 design document。计划依据为用户需求、AGENTS.md 约束和当前代码证据。

## first-principles judgment and direct code evidence

直接代码证据：

- 全局参数机制已经存在：`dayu/cli/arg_parsing.py:195-219` 构造 `global_parent` 并传给顶层 parser 和所有 subparser；`dayu/cli/arg_parsing.py:301-361` 注册 `--base`、`--config`、`--log-level`、`--debug`、`--verbose`、`--info`、`--quiet`。
- 参数可写在 command 前或后已有测试证据：`tests/cli/test_arg_parsing.py:443-461` 验证 `--base` 可出现在 command 前后。`--log-file` 应复用同一 parser parent，而不是在每个 command 中重复注册。
- CLI main 是日志装配真源：`dayu/cli/main.py:70-79` 在 dispatch runner 前调用 `runtime_log.set_level_from_flags(..., stream=sys.stderr)`。这是 `--log-file` 的正确接入点，因为 Fins direct command 也由同一个 main 分发：`dayu/cli/main.py:52-58`。
- runtime log 已支持 stream override：`dayu/runtime/log.py:99-127` 的 `configure(..., stream)` 把 marker handler 绑定到传入 stream；`dayu/runtime/log.py:144-183` 的 `set_level_from_flags(..., stream)` 解析 level 后调用 `configure`。
- runtime log 当前 reset marker handler 时只 remove，不 close：`dayu/runtime/log.py:263-273`。若 main 打开文件并在命令结束后关闭，必须防止 logger 继续持有关闭后的 file handler。
- prompt 当前总是创建默认 activity renderer：`dayu/cli/commands/prompt.py:275-285`；renderer 默认 TTY 可见：`dayu/cli/activity.py:69-76`。这与“默认 --no-detail”冲突。
- prompt activity 已通过 Service `on_activity` 回调进入 CLI：`dayu/cli/commands/prompt.py:378-401`，不需要 Host / Engine 新 API。
- interactive 当前每轮也直接创建默认 stderr activity renderer：`dayu/cli/commands/interactive.py:506-517`，运行态 Ctrl+T 只是调用 `renderer.toggle_visible()`：`dayu/cli/commands/interactive.py:602-608`。
- interactive 输入态 prompt_toolkit 边界已在 CLI 层：`dayu/cli/composer.py:1-5` 说明 Service / Host / Engine 不依赖 prompt_toolkit；`dayu/cli/composer.py:63-96` 封装 `PromptSession`；`dayu/cli/composer.py:99-141` 集中定义输入态 key bindings。
- 运行态按键监听已有 Ctrl+T / Esc 语义：`dayu/cli/run_keys.py:29-34` 定义 `TOGGLE_ACTIVITY` / `CANCEL_RUN`，`dayu/cli/run_keys.py:256-268` 将 Ctrl+T / Esc 映射到动作。计划应复用动作，不重新发明按键监听。
- Service activity DTO 已经是安全 UI 投影：`dayu/service/entrypoint_runtime.py:585-595` 接受 `on_activity`；`dayu/service/entrypoint_runtime.py:1068-1137` 只投影当前 run 的非终态 public activity；`dayu/service/entrypoint_runtime.py:1140-1163` 转换为 `EntrypointActivity`。这证明无需 Host / Engine contract change。
- Fins direct 当前诊断通过 runtime log，用户 progress/result 通过 `render_fins_direct_event`：`dayu/cli/commands/fins.py:293-320`、`dayu/cli/commands/fins.py:714-725`、`dayu/cli/output.py:202-248`。因此 `--log-file` 应只迁移诊断日志 sink，不迁移 Fins UI stream。
- Fins direct verbose/debug 现有测试位置为 `tests/cli/test_fins_commands.py:442-461`、`tests/cli/test_fins_commands.py:481-505`。实施 Slice A 前必须先确认这些断言是 `caplog` 还是 stderr 捕获：若是 `caplog`，旧测试不迁移，只新增 `--log-file` 文件内容测试；若直接断言 stderr，则更新为“无 log-file 时仍 stderr；有 log-file 时写文件”。
- prompt/interactive 已有“日志不污染 stdout”测试：`tests/cli/test_prompt_command.py:785-825`、`tests/cli/test_interactive_command.py:812-855`。新增行为要继续保持这些断言。

结论：

- work unit 成立。
- root cause 不是 Host / Engine 缺少事件，而是 CLI 输出 adapter 混用了 stderr 作为日志 sink 与运行态 activity UI sink，并且 activity 的默认可见性没有独立用户控制。
- 可在 CLI + runtime logging helper 生命周期内解决；当前没有 Host / Engine public API blocker。

## affected files

预计修改：

- `dayu/cli/arg_parsing.py`
  - `ParsedCliArgs` 增加 `log_file: str | None`、`detail: bool`。
  - 全局 parent 增加 `--log-file`。
  - `prompt` command 增加 mutually exclusive `--detail` / `--no-detail`。
- `dayu/cli/main.py`
  - 打开/关闭 log file stream。
  - 将日志 stream 传给 `runtime_log.set_level_from_flags`。
  - log-file 打开失败时返回 usage error 并写 stderr。
- `dayu/runtime/log.py`
  - 默认不改。仅当 `main()` 的 finally 恢复 stderr 后仍无法避免残留文件 handler 时，才做精确 handler 生命周期修正；不得把 `handler.close()` 泛化到语义不清的 helper。
- `dayu/cli/activity.py`
  - 保留 `CliActivityRenderer` 作为 prompt/plain CLI activity sink，但默认可见性不要作为 prompt 是否展示的唯一来源；由调用方通过 `--detail` 决定是否创建或启用。
  - 可增加纯格式化 helper export，供 interactive run view 复用同一有界展示文本，避免重复格式化逻辑。
- `dayu/cli/composer.py` 或新增 `dayu/cli/run_view.py`
  - 定义 CLI 层 `InteractiveRunView` / `ActivitySink` 窄协议与非 full-screen 终端 sink。
  - 管理 view mode、activity buffer、transcript buffer 和 Ctrl+T view toggle；不让 prompt_toolkit `PromptSession` 管理运行态。
- `dayu/cli/commands/prompt.py`
  - 根据 `args.detail` 决定是否传入 activity sink。
  - `--detail` 不改变日志 level。
- `dayu/cli/commands/interactive.py`
  - 不再直接创建 stderr `CliActivityRenderer` 作为 TTY UI。
  - 对 TTY 运行态使用 CLI run view 的 activity sink / transcript renderer / toggle action。
  - 非 TTY fallback 保持现有 stdout final answer，activity 默认不显示。
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_activity_renderer.py`
- `tests/cli/test_interactive_composer.py` 或新增 `tests/cli/test_interactive_run_view.py`
- `tests/cli/test_fins_commands.py`
- 可能修改 `tests/runtime/test_log.py`，仅当 `runtime.log` handler close 行为被改动。
- README：见 docs decision。

预计不修改：

- `dayu/host/**`
- `dayu/engine/**`
- `dayu/service/entrypoint_runtime.py`
- `dayu/fins/direct_events.py`
- durable schema、tool schema、prompt schema。

## contract/schema/state changes

CLI public interface changes：

- 新增全局 option：`--log-file <path>`。
  - 类型：非空路径字符串。
  - 默认：`None`，日志继续写 stderr。
  - 生效范围：所有 CLI command。
  - 位置：command 前或 command 后都合法。
  - level 正交：不改变 `args.log_level`；`--log-file --quiet` 仍只输出 error 级别日志到文件，`--log-file --verbose` 输出 verbose 及以上到文件。
  - 文件策略：以 append 模式、UTF-8 打开；父目录必须存在；打开失败返回 usage error。
- `prompt` 新增 mutually exclusive options：
  - `--detail`: 显示 activity stream。
  - `--no-detail`: 不显示 activity stream。
  - 默认：`--no-detail`，即 `args.detail is False`。
  - 与日志 flag 正交：`--debug` / `--verbose` 不打开 detail，`--detail` 不提升日志 level。
- interactive TTY 快捷键：
  - 复用现有 Ctrl+T 动作，但语义从“切换 stderr activity 可见性”升级为“切换 transcript / activity view”。
  - 新语义下 Ctrl+T 不再调用 `CliActivityRenderer.toggle_visible()`，不再打印旧的 `Activity hidden: ...` 行；它只切换当前运行态 view，不触发 cancel。
  - Esc 继续表示 cancel current run，不改变取消 contract。

Schema changes：

- 无 durable schema / DB schema / Host event schema / Engine event schema 变更。

State-machine changes：

- CLI 本地 UI state 新增 interactive run view mode：`transcript` / `activity`。
- prompt 本地 state 新增 detail gate：未启用时不注册 activity sink 或使用 disabled sink；启用时才消费并渲染 activity。
- Host run lifecycle、cancel lifecycle、Fins direct stream lifecycle 不变。

Public API blocker check：

- 当前证据显示 Service `on_activity` 已足够，Host public event 已携带 `activity`，Engine 不参与 CLI UI 展示。因此无 Host / Engine public API blocker。
- 若实现 interactive run view 时发现必须从 Host 读取 transcript 增量或 activity 历史，而 Service callback 不足，应停止并标 blocker；不得扩展 Host / Engine contract 来完成本 work unit。

## implementation decisions

1. `--log-file` 在 CLI main 处理，不下沉到 command。
   - 原因：日志装配已集中在 `dayu/cli/main.py`，Fins direct 也经 main 分发；下沉会造成每个 command 重复打开文件，破坏全局 option 语义。

2. `--log-file` 只改变 runtime log stream，不改变 stdout/stderr 用户通道。
   - prompt final answer、interactive transcript fallback、Fins progress/result 继续走原输出函数。
   - activity 不写入 log file，因为 activity 是 UI stream，不是诊断日志。

3. 文件打开策略用 append + UTF-8，父目录不存在时报 usage error。
   - append 防止多次 invocation 共用同一路径时覆盖历史诊断。
   - 不自动创建父目录，避免 CLI 因用户拼错路径而静默创建意外目录。
   - 多个进程并发写同一个 `--log-file` 不保证日志行原子性，可能交错；这是本轮接受的诊断日志限制，不加文件锁或 tee。

4. runtime log handler 生命周期只做必要修正。
   - `main()` 不依赖文件对象 context manager 自动关闭；它必须持有 `log_stream`，并在 `finally` 中按固定顺序清理。
   - 固定顺序：若使用了文件 stream，先调用 `runtime_log.set_level_from_flags(..., stream=sys.stderr)` 或等价 `runtime_log.configure(..., stream=sys.stderr)` 恢复 dayu logger 的 stderr handler，再关闭文件 stream。
   - 不把 `handler.close()` 泛化到 `_reset_marker_handlers` 等语义不清的 helper。若最终仍需改 `dayu/runtime/log.py`，必须有精确测试证明连续 reset 不会关闭 `sys.stderr`，且不会留下指向已关闭文件的 handler。
   - 不新增复杂 log sink registry，不支持同时写 stderr 和 file，除非用户后续明确需要 tee。

5. `prompt --detail` 显式控制 activity。
   - `args.detail is False` 时不传 `on_activity`，避免无意义地格式化/去重 activity。
   - `args.detail is True` 时创建 `CliActivityRenderer(options=CliActivityRendererOptions(visible=True, enabled=True))`，绕过默认 `isatty()` gate。activity 仍走 UI activity sink 并写现有 activity stderr 通道，不进入 `--log-file`。

6. interactive 的运行态 view 边界放在 CLI 层。
   - 不让 command 模块直接操控 prompt_toolkit 类型；command 只依赖窄协议，例如 `InteractiveRunView` / `ActivitySink`。
   - 本轮实现非 full-screen 终端 sink，维护 transcript/activity buffers 和 current view mode；运行态继续复用现有 `run_keys.py` 的 Ctrl+T / Esc 监听。
   - 不声称 `PromptSession` 能管理运行态。若需要 full prompt_toolkit `Application` 才能达成 UX，则 Slice C 停止并拆为后续独立 work unit。
   - 非 TTY fallback 继续使用 input reader + stdout/stderr 行输出，activity 默认不显示。

7. 不引入新框架或跨层抽象。
   - 复用现有 `composer.py` / `run_keys.py` / `activity.py`。
   - 只在 CLI 层增加必要 UI 状态，不把 UI 状态上抛到 Service / Host。

## small slices

### Slice A: 全局 `--log-file` 与日志 sink

Objective:

- 增加全局 `--log-file`，支持 command 前后位置，所有 command 共用。

Allowed files:

- `dayu/cli/arg_parsing.py`
- `dayu/cli/main.py`
- `dayu/runtime/log.py`（仅 handler close 必要修正）
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_fins_commands.py`
- `tests/runtime/test_log.py`（如 runtime handler close 行为改动）

Exact changes:

- `ParsedCliArgs` 增加 `log_file: str | None`。
- `_new_default_namespace()` 设置 `namespace.log_file = None`。
- `_build_global_arguments_parent()` 增加 `--log-file`，`default=argparse.SUPPRESS`。
- `main()` 在 parse 后、日志配置前：
  - 若 `args.log_file is None`，使用 `sys.stderr`。
  - 若非空，校验 strip 后非空，用 append + UTF-8 打开 path，并记录 `opened_log_file = True`。
  - 打开失败输出 `dayu-cli: --log-file: ...` 到 stderr 并返回 `EXIT_USAGE_ERROR`。
  - 在 runner 前调用 `runtime_log.set_level_from_flags(..., stream=log_stream)`。
  - runner 正常返回、抛出已捕获异常或抛出未预期异常时，都进入 `finally`。
  - `finally` 中若 `opened_log_file` 为 `True`，必须先把 dayu logger 恢复到 stderr handler，再关闭文件：先调用 `runtime_log.set_level_from_flags(..., stream=sys.stderr)`（保持当前 level flag）或等价 `runtime_log.configure(..., stream=sys.stderr)`，再调用 `log_stream.close()`。
  - 恢复 stderr 与关闭文件的顺序不可反转；关闭后不得让 dayu logger 继续持有该 file stream。
- 不默认修改 `dayu/runtime/log.py`。如果实现证明必须修改 runtime handler reset/close 行为：
  - 修改必须只表达“关闭 Dayu 自有 marker handler”这一精确语义，不把 close 隐藏进职责不清的 helper。
  - 新增 runtime 测试必须证明重复配置 stderr 后 `sys.stderr` 未被关闭，并证明文件 handler reset 后不再写已关闭 stream。

Tests:

- `test_parse_args_accepts_global_options_before_and_after_command` 增加 `--log-file` 前后位置断言。
- main spy test 增加 `log_file` 默认仍 `stream=sys.stderr` 的断言，并新增 log_file 版本断言传入 file stream。
- main 异常路径测试：
  - runner 抛出异常或返回错误码后，`finally` 仍先恢复 dayu logger 到 stderr handler，再关闭文件。
  - 一次 `main(... --log-file <tmp> ...)` 失败后，下一次不带 `--log-file` 的日志写入 stderr 不抛 `ValueError`，且不写入已关闭文件。
- Fins direct 新增：
  - `download --ticker AAPL --verbose --log-file <tmp>`：stdout 有 `Fins progress`，stderr 不含 `Fins direct command start`，文件含 VERBOSE 诊断。
  - `download --ticker AAPL --log-file <tmp>` 默认 info 不写 verbose 诊断，证明 sink 与 level 正交。
- Fins direct 旧测试处理策略：
  - 先读取 `tests/cli/test_fins_commands.py:442-461`、`:481-505` 确认捕获方式。
  - 若旧测试使用 `caplog`，保留旧测试，只新增文件 sink 测试。
  - 若旧测试直接断言 stderr 诊断，补充“无 log-file 时仍 stderr”的断言，并新增“有 log-file 时诊断进入文件”的断言。
- 如 handler close 修改，runtime 测试覆盖重复 configure 不泄漏、不写已关闭 stream，且不关闭 `sys.stderr`。

Completion signal:

- `--log-file` 解析、main 分发、Fins direct 写文件测试通过。
- 无 Host / Engine 文件变更。

### Slice B: `prompt --detail/--no-detail`

Objective:

- prompt 默认不显示 activity；显式 `--detail` 时显示 activity。

Allowed files:

- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/prompt.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_activity_renderer.py`（仅必要更新）

Exact changes:

- `ParsedCliArgs` 增加 `detail: bool`，默认 `False`。
- `_register_prompt_command()` 增加 mutually exclusive group：
  - `--detail`, `dest="detail"`, `action="store_true"`
  - `--no-detail`, `dest="detail"`, `action="store_false"`
  - 默认由 namespace 提供 `False`。
- prompt 执行路径创建 activity renderer 的逻辑改为：
  - `args.detail` 为 `False`：传 `activity_renderer=None`。
  - `args.detail` 为 `True`：创建 `CliActivityRenderer(options=CliActivityRendererOptions(visible=True, enabled=True))`。
- `_submit_prompt_turn_handling_sigint` 的 cancel activity 提示继续只在 renderer 存在时输出。

Tests:

- parser help 覆盖 prompt help 包含 `--detail` / `--no-detail`。
- parser default `parse_cli_args(("prompt", "hello")).detail is False`。
- `prompt --detail` 解析为 `True`，`prompt --no-detail` 解析为 `False`。
- 更新现有 `test_prompt_tty_activity_writes_stderr_and_final_answer_stays_stdout`：只有加 `--detail` 才断言 activity。
- 新增默认 no-detail test：即使 fake host 推送 activity，stderr 不含 `Activity:`，stdout 仍只有 final answer。
- 新增非 TTY detail test：显式 `--detail` 时即使 stderr 非 TTY，也通过 `CliActivityRendererOptions(visible=True, enabled=True)` 输出 activity；该 activity 仍属于 UI activity sink，不进入 `--log-file`。
- 新增正交性 test：`prompt --verbose` 不显示 activity，`prompt --detail` 不产生 verbose 诊断。

Completion signal:

- prompt 默认输出收敛，detail 行为明确。

### Slice C: interactive run view / activity sink 边界

Objective:

- interactive TTY 运行态用 CLI 层非 full-screen run view 管理 transcript/activity view，并用 Ctrl+T 切换 view；不再把 activity 当诊断日志流。此 slice 不让 `PromptSession` 管理运行态。

Allowed files:

- `dayu/cli/composer.py` 或新增 `dayu/cli/run_view.py`
- `dayu/cli/activity.py`
- `dayu/cli/commands/interactive.py`
- `tests/cli/test_interactive_composer.py` 或新增 `tests/cli/test_interactive_run_view.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_run_keys.py`（只在动作名/语义更新时）

Exact design:

- 定义 CLI 层窄协议。协议只覆盖运行态，不复制输入态 `InteractiveComposer.read()`：
  - `ActivitySink.record_activity(activity: EntrypointActivity) -> None`
  - `InteractiveRunView.activity_sink() -> ActivitySink`
  - `render_terminal_result(result: EntrypointRunTerminalResult) -> int`
  - `toggle_view() -> None`
  - `render_cancel_requested() -> None`
  - `render_local_exit_after_cancel() -> None`
  - `close() -> None`
- 非 full-screen TTY implementation 持有：
  - transcript lines：用户输入与 final answer / failure / cancelled 文本。
  - activity lines：复用 `dayu.cli.activity` 的有界 activity 格式化输出。
  - current view mode：`transcript` / `activity`。
  - output stream：继续使用用户 UI stderr/stdout 边界，不写入 `--log-file`。
- 渲染策略：
  - 默认 view 为 `transcript`，activity 到达时只记录到 activity buffer，不作为日志写入。
  - Ctrl+T 复用 `run_keys.py` 的 `RunningKeyAction.TOGGLE_ACTIVITY`，调用 `view.toggle_view()`。
  - Ctrl+T 新语义是 `transcript` 与 `activity` view 互切；不调用旧 `CliActivityRenderer.toggle_visible()`，不输出 `Activity hidden: ...`。
  - 非 full-screen sink 可用简单分隔线/当前 view 重绘表达 view 切换；不得引入 prompt_toolkit `Application.run_async()` 或 PTY 依赖。
- 非 TTY implementation 保持现有 input reader + terminal result stdout/stderr 输出；activity 默认不显示。
- `interactive.py` command 不直接创建 `CliActivityRenderer`：
  - `_run_interactive_loop_on_existing_session` 接收 `InteractiveRunView` 或 factory。
  - `submit_entrypoint_turn_and_wait(..., on_activity=view.activity_sink().record_activity)`。
  - `RunningKeyAction.TOGGLE_ACTIVITY` 时调用 `view.toggle_view()`。
  - terminal result 通过 `view.render_terminal_result(...)`，不在 command 里直接调用 output renderer。
- Esc cancel path 调用 UI cancel 提示方法，但不写 logging。
- 若实现发现非 full-screen sink 不能满足 requirement，且必须把运行态迁移到 full prompt_toolkit `Application`，立即停止 Slice C：该重构是后续独立 work unit，不在本轮扩大 scope。

Tests:

- run view unit test：
  - record activity 后 activity buffer 增加一行，transcript buffer 不变。
  - render terminal succeeded 后 transcript buffer 增加 answer。
  - toggle view 在 transcript/activity 间切换。
  - 当前 view 为 activity 时只渲染 activity view；切回 transcript 后 answer 可见。
  - Ctrl+T view switch 不输出旧的 `Activity hidden: ...` 行。
- command integration：
  - Ctrl+T 不触发 Host cancel，调用 UI toggle。
  - Esc 仍触发 Host cancel。
  - interactive TTY activity 不再通过 `CliActivityRenderer` stderr 单行测试表达；更新现有 `test_interactive_tty_activity_finishes_before_next_prompt` 为 run view 行为。
- 非 TTY regression：
  - 两轮 interactive final answers 仍写 stdout。
  - verbose/debug 诊断仍不污染 stdout。

Completion signal:

- interactive 的 activity/transcript 管理点从 command-level stderr renderer 移至 CLI run view / activity sink boundary。
- Running key cancel 行为无回归。

### Slice D: 文档与验证收口

Objective:

- 更新 README 决策，运行测试与 pyright，形成 completion report。

Allowed files:

- `tests/README.md`
- `dayu/README.md`（仅当跨包输出通道描述需要同步）
- 根 `README.md`（若用户手册中 CLI 参数示例需同步，先阅读目标段落约束；根 README 当前未见 Agent 更新约束，仍只做用户手册必要最小修改）

Exact changes:

- `tests/README.md`：更新 CLI 测试覆盖事实，加入 `--log-file`、`prompt --detail`、interactive transcript/activity view。
- `dayu/README.md`：若 `dayu.runtime.log` 段落仍写死“CLI composition root 显式使用 stderr 作为诊断通道”，需改为“默认 stderr，可由 CLI `--log-file` 显式改为文件 sink”，不扩写 CLI 用户手册。
- 根 README：若已有 CLI 参数清单/示例与新行为冲突，做最小同步；不写实现细节。

Validation:

- `source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py -q`
- 如新增 `tests/cli/test_interactive_run_view.py`，加入命令。
- 如改 `runtime.log`：`source .venv/bin/activate && pytest tests/runtime/test_log.py -q`
- 全量 CLI：`source .venv/bin/activate && pytest tests/cli -q`
- 类型检查：`source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`

Completion signal:

- README 决策完成。
- 受影响测试、CLI 测试、pyright 通过或失败有明确非本 work unit blocker 说明。

## tests / validation

必须新增或更新的断言：

- 参数解析：
  - `--log-file` 在 command 前后位置都被解析到同一字段。
  - `--log-file` 不改变 `log_level`。
  - `prompt --detail` / `prompt --no-detail` mutually exclusive，默认 no-detail。
- 日志文件：
  - 无 `--log-file` 时默认日志仍写 stderr。
  - 有 `--log-file` 时诊断日志写文件，不污染 stdout。
  - `--verbose --log-file` 写 verbose 诊断；仅 `--log-file` 不写 verbose 诊断。
  - Fins direct command 使用同一 `--log-file` 行为。
- prompt activity：
  - 默认不显示 activity。
  - `--detail` 显示 activity。
  - `--debug` / `--verbose` 不显示 activity。
  - `--detail` 不提升日志 level。
- interactive view：
  - Ctrl+T 切换 view，不 cancel。
  - Esc cancel 不受 view mode 影响。
  - `InteractiveRunView` 维护 transcript/activity 独立 buffers。
  - 非 TTY fallback 保持 stdout final answer 行为。
- 回归：
  - prompt/interactive verbose/debug 诊断不污染 stdout。
  - Fins direct progress/result 不进入 log file 断言范围，只保持用户通道输出。

建议命令：

```bash
source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py -q
source .venv/bin/activate && pytest tests/cli -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

如修改 `dayu/runtime/log.py`：

```bash
source .venv/bin/activate && pytest tests/runtime/test_log.py -q
```

## docs decision

- `tests/README.md`：需要更新。原因是本 work unit 会修改 `tests/cli` 覆盖事实；目标 README 明确只记录当前测试事实，新增/迁移测试覆盖后应同步。
- `dayu/README.md`：实施时需要检查并按需更新。当前 `dayu/README.md` 提到 `dayu.runtime.log` 默认写 stderr 且 CLI composition root 使用 stderr 诊断通道；新增 `--log-file` 后若这段不改会变成过时边界摘要。
- 根 `README.md`：实施时按用户手册必要性判断。若 CLI 选项章节列出 debug/verbose 或 interactive 控制键，应最小更新 `--log-file`、`prompt --detail` 和 interactive view toggle；若未命中则不机械同步。
- 不更新 `dayu/engine/README.md`、`dayu/host/README.md`、`dayu/fins/README.md`，因为本计划不改这些包的 public contract 或内部机制。

## risks / open questions

Risks:

- interactive full-screen prompt_toolkit 改动容易扩大。控制方式：本轮只抽 CLI 层窄 UI 协议和非 full-screen sink；若必须迁入 prompt_toolkit `Application`，拆为后续独立 work unit。
- `--log-file` handler 生命周期若处理不当，会在测试进程中留下指向关闭文件的 handler。控制方式：main `finally` 中先恢复 dayu logger 到 stderr handler，再关闭文件；只有在精确测试支撑下才改 runtime handler close 行为。
- `prompt --detail` 在非 TTY 下显式输出 activity 可能让脚本 stderr 变多，但这是用户显式要求；默认仍安静。
- 多进程并发写同一个 `--log-file` 可能导致日志行交错；本轮不加进程级文件锁，作为诊断日志限制接受。
- 现有测试对 activity stderr 有旧预期，需要迁移测试边界，不能为了保旧测试在生产代码里保留兼容 stderr path。

Open questions:

- 无 blocking open question。
- 非阻塞实现细节：`--log-file` append 还是 truncate。本计划选择 append；若产品希望每次覆盖，应在实现前明确改为 truncate。

Blocker rule:

- 如果 Slice C 发现没有 Host public event 足以构造 interactive activity view，或必须读取 Host durable internals / 改 Host public API，立即停止并标 blocker。
- 如果 Slice C 发现必须使用 full prompt_toolkit `Application.run_async()` 才能实现运行态 view，也立即停止并拆为后续 work unit，不在本轮扩大 scope。

## why this is not over-designed

- 方案使用现有真源：全局参数复用 `global_parent`，日志复用 `runtime_log` 的 stream override，activity 复用 Service `on_activity` DTO，快捷键复用 `run_keys.py`。
- 没有新增 Host / Engine contract、没有新增 durable schema、没有把 Fins direct 包装成 Host Run。
- CLI run view 边界只服务当前 interactive transcript/activity 切换需求，不引入通用 UI framework、插件系统、日志 sink registry 或多 sink tee。
- 切片按当前风险自然拆分：日志 sink、prompt detail、interactive run view、文档验证。每片都有独立可测结果。
- 新抽象只在 CLI UI adapter 层内存在，用于隔离运行态 view/sink 和 command 状态机；它承载真实复杂度，不是为了未来猜想预留 seam。

## completion report format

实现完成后最终报告必须包含：

- 改了什么：
  - `--log-file` 行为和文件策略。
  - `prompt --detail/--no-detail` 行为。
  - interactive transcript/activity view 和快捷键行为。
  - 是否修改了 runtime log handler 生命周期。
- 验证了什么：
  - 精确列出运行过的 pytest 命令。
  - 精确列出 pyright 命令。
  - 说明 README 更新结果。
- 未覆盖/风险：
  - 是否有未跑测试。
  - 是否有 TTY 手工验证缺口。
  - 是否存在 Host / Engine API blocker；若无，明确说明未修改 Host / Engine public API/contracts。

计划 artifact path: `docs/reviews/wu-cli-output-channels-plan-20260617.md`
