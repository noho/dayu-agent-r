# WU CLI Output Channels — Plan Review

**Review target**: `docs/reviews/wu-cli-output-channels-plan-20260617.md`  
**Work unit**: Dayu CLI 输出通道拆分  
**Review gate**: Gateflow Plan Review Gate  
**Reviewer**: AgentCodex (DS adversarial pass)  
**Date**: 2026-06-17  

## Reviewed Target and Scope

Plan proposes four slices:
- **Slice A**: 全局 `--log-file` 与日志 sink
- **Slice B**: `prompt --detail/--no-detail`
- **Slice C**: interactive TUI transcript/activity view 边界
- **Slice D**: 文档与验证收口

## Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|---------|
| A1 | 全局参数复用 `global_parent`，`--log-file` 可出现在 command 前后 | **Confirmed** — `arg_parsing.py:195-219` 已有此机制；测试 `test_parse_args_accepts_global_options_before_and_after_command`（line 443）验证 `--base` 前后位置 |
| A2 | CLI main 是日志装配真源，Fins direct 也经 main 分发 | **Confirmed** — `main.py:52-58` 注册所有 Fins direct commands 到同一 `COMMAND_RUNNERS`；`main.py:72-79` 在 dispatch 前统一配置日志 |
| A3 | `runtime_log` 的 `stream` 参数已支持 stream override | **Confirmed** — `log.py:99-127` `configure(stream=...)`；`log.py:144-183` `set_level_from_flags(stream=...)` |
| A4 | Service `on_activity` 回调已足够承载 CLI UI，无需 Host/Engine 新 API | **Confirmed** — `entrypoint_runtime.py:585-595` 接受 `on_activity` callback；`entrypoint_runtime.py:1068-1137` 只投影当前 run 的非终态 public activity |
| A5 | `_reset_marker_handlers` 只 remove 不 close | **Confirmed** — `log.py:263-273` 只调用 `target_logger.removeHandler(handler)`，不调用 `handler.close()` |
| A6 | prompt 当前总是创建默认 activity renderer | **Confirmed** — `prompt.py:283` 硬编码 `activity_renderer=new_cli_activity_renderer()` |
| A7 | interactive 当前每轮创建默认 stderr activity renderer | **Confirmed** — `interactive.py:515` 硬编码 `activity_renderer=new_cli_activity_renderer()` |
| A8 | Ctrl+T 当前语义为 toggle stderr activity 可见性 | **Confirmed** — `interactive.py:602-608` 调用 `renderer.toggle_visible()` |
| A9 | `InteractiveComposer` 协议已把 prompt_toolkit 隔离在 CLI 层 | **Confirmed** — `composer.py:21-33` 定义窄协议；`composer.py:63-96` 封装 `PromptSession` |
| A10 | Fins direct 诊断日志走 runtime log，用户输出走 `render_fins_direct_event` | **Confirmed** — `fins.py:293-297` 用 `runtime_log.log_verbose`；`fins.py:714-725` 用 `render_fins_direct_event` |

## Findings

### F1 — [High] interactive TUI running-state view 渲染机制在 prompt_toolkit 生命周期内无法自然承载

- **位置**: Slice C，Exact design 段落（plan line 289-309）
- **问题类型**: 架构边界 / 不可直接实施
- **当前写法**: plan 要求 "TTY prompt_toolkit implementation 维护 transcript/activity buffers 和 current view mode"，并 "复用现有 `composer.py` / `run_keys.py` / `activity.py`"
- **反例/失败场景**:

  当前 interactive 的执行循环由两个不同阶段组成：

  **阶段 1 — 输入态**：`PromptSession.prompt_async()` 全屏接管终端，prompt_toolkit 的 `Application` 正在运行。

  **阶段 2 — 运行态**：`asyncio.wait(submit_task, sigint_task, key_task)` 在标准 asyncio 事件循环中等待。此时 prompt_toolkit Application 已退出，终端回到行模式。activity 通过 `CliActivityRenderer` 直接写 stderr 行输出，不经过 prompt_toolkit。

  plan 要求 "activity/transcript view 由 prompt_toolkit/TUI 边界管理" 和 "快捷键可切换当前 view"，但这面临根本性冲突：**activity 的渲染发生在 prompt_toolkit Application 不活跃的阶段**。要在运行态持续渲染 TUI view（带 transcript/activity buffer 和 view toggle），必须让整个 execute loop 运行在 prompt_toolkit 的 Application 内部，即用 `Application.run_async()` 替代当前的 `PromptSession.prompt_async()` + `asyncio.wait()` 双阶段结构。

- **为什么有问题**: plan 声称 "只在 CLI 层增加必要 UI 状态"、"复用现有 composer.py / run_keys.py"，但这低估了所需的重构深度。要让 prompt_toolkit 管理运行态 view，需要：
  1. 把 `_submit_interactive_turn_handling_sigint` 中的 `asyncio.wait` 循环迁移到 prompt_toolkit Application 的 event loop 上下文内；
  2. 用 prompt_toolkit Layout/Window 系统渲染 transcript 和 activity buffers；
  3. 在 prompt_toolkit 内处理运行态按键（Ctrl+T/Esc），而非通过独立的 `TtyRunningKeyMonitor`（后者在 `termios.cbreak` 模式读 stdin，与 prompt_toolkit 的 stdin 处理冲突）。

  这不是 "复用"，而是重新设计 interactive 的执行模型。

- **直接证据**:
  - `composer.py:76-81`：`PromptToolkitInteractiveComposer` 只在 `read()` 时创建/使用 `PromptSession`，运行态不在其生命周期内
  - `interactive.py:506-517`：`_submit_interactive_turn_handling_sigint` 独立接收 `activity_renderer` 和 `key_monitor`，不经过 composer
  - `run_keys.py:95-180`：`TtyRunningKeyMonitor` 用 `termios.cbreak` + `select` + 后台线程在 prompt_toolkit 外部读取 stdin。若将其迁移到 prompt_toolkit 内部（通过 prompt_toolkit key bindings），就不再需要独立的 termios 管理；但若 prompt_toolkit Application 此时不活跃，就无法接收按键

- **影响**: 实施 Agent 发现必须大幅重构 interactive 执行模型或放弃 prompt_toolkit 管理运行态 view；若强行实现可能导致 "伪 TUI"（实际仍是 stderr 行输出加上 ANSI escape codes 模拟 view 切换，而非真正的 prompt_toolkit managed view）

- **建议改法和验证点**:

  **方案 A（推荐，最小变更）**：明确 Slice C 的 TUI 边界定义为 **非 prompt_toolkit** 的终端控制层。保留当前双阶段架构，只把 `CliActivityRenderer` 的 stderr 单行输出升级为：
  - 在 `CliActivityRenderer.record()` 中维护 transcript/activity 两个内存 buffers（带行号、分页）
  - `toggle_visible()` 切换时用 ANSI escape codes 清屏重绘当前 view
  - 不引入 prompt_toolkit Application 管理运行态

  此方案真正复用现有架构，只需改 `activity.py` 的渲染策略。

  **方案 B（完整 TUI）**：承诺 Slice C 的重构范围，明确 interactive 整个生命周期都迁移到 `prompt_toolkit.Application.run_async()` 内部。代价是大幅增加 Slice C 的复杂度和测试成本，需要 PTY 测试基础设施。若选此方案，Slice C 应拆分为独立 work unit。

  验证点：无论选哪个方案，必须先写出具体渲染伪代码并确认与 `TtyRunningKeyMonitor` 的 stdin 所有权不冲突。

- **修复风险**: 方案 A 低，方案 B 高
- **严重程度**: 高
- **裁决建议**: `needs-more-evidence` — 需要 plan 补充具体的 running-state view 渲染机制选型及与现有 stdin/key monitor 的交互设计

---

### F2 — [Medium] `main()` 中 `--log-file` 关闭后 handler 生命周期顺序未显式指定

- **位置**: Slice A，Exact changes 段落（plan line 208-219）
- **问题类型**: 状态机漏洞 / 不可直接实施
- **当前写法**: plan line 218 只写 "runner 完成后关闭 file stream，并避免 logger 残留关闭 stream handler"，但未给出 main 中恢复 stderr handler 与关闭文件的具体顺序
- **反例/失败场景**:

  ```python
  # main() 伪代码 —— 若按字面理解 plan：
  log_stream = open(args.log_file, "a")
  runtime_log.set_level_from_flags(..., stream=log_stream)
  exit_code = runner(args)
  log_stream.close()  # plan line 218: "runner 完成后关闭 file stream"

  # 此时 dayu namespace logger 仍持有 StreamHandler(log_stream)
  # 任何后续日志调用（如 atexit cleanup、测试 teardown、其他模块的 final log）
  # 会触发 ValueError: I/O operation on closed file
  ```

  在测试场景中尤其致命：测试夹具多次调用 `main()` 等价流程时，若两次调用之间 logger 残留指向已关闭文件的 handler，第二次调用的日志写入将静默失败或抛出异常。

- **为什么有问题**: plan 同时提到 "如改 `runtime.log._reset_marker_handlers`，remove marker handler 后调用 `handler.close()`"（line 219），但这个修改只在 `configure()` 被**再次调用**时才生效。若 main 不显式调用 `configure(stream=sys.stderr)` 后再关闭文件，则 logger 始终持有指向即将关闭文件的 handler。

- **直接证据**:
  - `log.py:124-127`：`configure()` → `_reset_marker_handlers()` → `addHandler(_build_marker_handler(level, effective_stream))` — 新 handler 持有传入的 stream
  - `log.py:263-273`：`_reset_marker_handlers` 当前只 `removeHandler`，不 `close()`
  - `main.py:72-79`：当前硬编码 `stream=sys.stderr`，无文件生命周期管理

- **影响**: 测试中残留关闭 stream handler 的 logger，导致后续测试写日志失败；生产环境中 atexit cleanup 可能触发 I/O 异常

- **建议改法和验证点**:
  1. 在 main 的成功路径和异常路径中都显式恢复日志 stream：
     ```python
     try:
         args = parse_cli_args(argv)
         log_stream = _open_log_file(args.log_file)  # None → sys.stderr
         runtime_log.set_level_from_flags(..., stream=log_stream)
         exit_code = runner(args)
     finally:
         if log_stream is not sys.stderr:
             # 先恢复 stderr handler（这会触发 _reset_marker_handlers
             # 移除并 close 文件 handler），再关闭文件
             runtime_log.configure(level=LogLevel.INFO, stream=sys.stderr)
             log_stream.close()
     ```
  2. 验证点：测试重复调用 main 等价流程后，后续日志仍可写入 stderr 而不抛异常

- **修复风险**: 低
- **严重程度**: 中
- **裁决建议**: `accepted` — 应在 Slice A 的 Exact changes 中显式补充上述 finally 逻辑

---

### F3 — [Medium] `_reset_marker_handlers` 调用 `handler.close()` 对 `sys.stderr` handler 的副作用未评估

- **位置**: Slice A，Exact changes 段落（plan line 219）及 Risks（plan line 415）
- **问题类型**: 并发恢复风险 / 契约缺失
- **当前写法**: "如改 `runtime.log._reset_marker_handlers`，remove marker handler 后调用 `handler.close()`"
- **反例/失败场景**:

  Python `logging.StreamHandler.close()` 的行为因版本而异：
  - Python < 3.9：`close()` 会调用 `self.stream.close()`，导致 `sys.stderr` 被关闭，后续所有 stderr 输出静默失败
  - Python ≥ 3.9：`close()` 不再调用 `stream.close()`，只 flush + set `self.stream = None`

  项目声明 Python 3.11（`CLAUDE.md`），所以版本差异风险低。但仍有边缘情况：
  - 若 `_reset_marker_handlers` 被非 `configure()` 路径调用（如测试 teardown helper），可能意外 close 指向 `sys.stderr` 的 handler
  - `StreamHandler.close()` 后设置 `self.stream = None`，若该 handler 被某处引用并后续尝试 emit，会抛 `AttributeError`

- **为什么有问题**: plan 将 close 逻辑放在 `_reset_marker_handlers`（低层通用 helper），而不是放在 `configure()`（高层装配入口）。`_reset_marker_handlers` 的语义是 "移除自有 marker handler"，加入 close 后变为 "移除并关闭自有 marker handler"。这个语义变化可能影响所有调用 `_reset_marker_handlers` 的路径，包括未来的测试 helper 或非 configure 调用方。

- **直接证据**:
  - `log.py:263-273`：`_reset_marker_handlers` 是模块级私有函数，当前只被 `configure()` 调用（line 124 和 line 131）
  - `log.py:248-260`：`_build_marker_handler` 使用 `logging.StreamHandler`，其 `close()` 行为依赖 CPython 版本

- **影响**: 生产环境低（Python 3.11 无此问题）；测试环境边缘风险（若有 helper 在非 configure 路径调用 `_reset_marker_handlers`）

- **建议改法和验证点**:
  1. 仅在 `configure()` 中调用 `handler.close()`（在 `_reset_marker_handlers` 返回后），而非修改 `_reset_marker_handlers` 本身。这保持 `_reset_marker_handlers` 的单一职责（remove），把 close 决策留给调用方。
  2. 或在 `_reset_marker_handlers` docstring 中显式声明 "调用后 handler 的 stream 可能已关闭，调用方必须确保不再引用这些 handler"。
  3. 验证点：新增 runtime log 测试 —— 对 `sys.stderr` 连续两次 `configure()` 后，stderr 仍可写入

- **修复风险**: 低
- **严重程度**: 中
- **裁决建议**: `accepted` — 接受 plan 方向，但建议 close 逻辑放在 `configure()` 而非 `_reset_marker_handlers`

---

### F4 — [Medium] prompt_toolkit TUI 单元测试策略缺失

- **位置**: Slice C，Tests 段落（plan line 311-325）
- **问题类型**: 测试缺口
- **当前写法**: plan 列出 "TUI unit test" 但未说明测试基础设施。测试断言包括 "record activity 后 activity buffer 增加一行"、"toggle view 在 transcript/activity 间切换"、"当前 view 为 activity 时只渲染 activity view"
- **反例/失败场景**:

  prompt_toolkit 组件通常需要 PTY（pseudo-terminal）环境运行。在 CI/headless 环境中，`isatty()` 返回 `False`，prompt_toolkit 可能拒绝创建 Application 或 `PromptSession`。现有测试通过 `InputReaderComposer`（非 TTY 路径）+ `NoopRunningKeyMonitor` 绕过 TTY 依赖。

  若 Slice C 引入了需要 prompt_toolkit Application/PTY 的 TUI 组件，则：
  - 单元测试需要在 PTY 中运行（需要 `pytest-asyncio` + PTY 支持或 mock prompt_toolkit 内部）
  - CI 环境若无 PTY，相关测试将被跳过，覆盖率降低

- **为什么有问题**: plan 的测试设计隐含假设 TUI controller 可在无 PTY 环境下测试。若最终方案（如 F1 的方案 B）需要完整 prompt_toolkit Application，则该测试策略不可行。

- **直接证据**:
  - 现有测试中，TTY 路径通过 `InteractiveComposer` 协议 + mock 绕过：`composer.py:159-162` —— `isatty()` 为 False 时走 `InputReaderComposer`
  - 现有测试中，运行态按键通过 `NoopRunningKeyMonitor` 绕过：`run_keys.py:250-253`
  - 项目无 pytest-prompt-toolkit、pexpect 或 PTY 测试依赖

- **影响**: 若 TUI 实现引入了 prompt_toolkit Application 依赖，CI 覆盖率下降；若选择方案 A（ANSI escape 方式），则本 finding 不成立

- **建议改法和验证点**:
  1. 先在 Slice C 的 Exact design 中选定渲染机制（F1 的方案 A 或 B），再据此决定测试策略
  2. 若选方案 A：TUI controller 单元测试可以纯内存 buffer 断言，不依赖 PTY
  3. 若选方案 B：需要引入 PTY 测试依赖（如 `pexpect` 或 `pytest-prompt`），且 CI 环境需要支持 PTY
  4. 验证点：确认至少一条 CI 路径可以执行 TUI 测试

- **修复风险**: 取决于最终方案
- **严重程度**: 中
- **裁决建议**: `needs-more-evidence` — 与 F1 联动，需在选定渲染机制后确认测试策略

---

### F5 — [Low] Fins direct 现有测试迁移策略不完整

- **位置**: Slice A，Tests 段落（plan line 222-228）
- **问题类型**: 测试缺口
- **当前写法**: plan 列出新增 Fins direct `--log-file` 测试，但说 "这些测试要迁移为'无 log-file 时仍 stderr；有 log-file 时写文件'"（plan line 72）。实际 test list 只有新增测试，未提及更新现有 `test_fins_direct_verbose_log_outputs_execution_skeleton`（tests/cli/test_fins_commands.py:442）等旧测试
- **反例/失败场景**:

  若只新增 `--log-file` 测试而不更新现有 `test_fins_direct_verbose_log_outputs_execution_skeleton`，旧测试仍断言 verbose 日志在 stderr 中。若实施时改了诊断日志默认行为（如 main 里 stream 传参方式变化），旧测试可能因非预期原因通过（日志恰好仍在 stderr）或因实现细节变化而失败。

  但更可能的是：`test_fins_direct_verbose_log_outputs_execution_skeleton` 当前使用 `caplog` 捕获日志（而非直接读 stderr），而 `caplog` 不受 `--log-file` stream override 影响（因为 caplog 在 pytest handler 层捕获，不经过 StreamHandler）。如果是这样，该测试无需修改，plan 的相关叙述属于过度谨慎。

- **为什么有问题**: plan 对旧测试受影响的判断不够精确。若 caplog 路径不受 stream override 影响，则无需"迁移"，只需新增 log-file 到文件的测试。

- **直接证据**: 需要确认 `test_fins_direct_verbose_log_outputs_execution_skeleton` 是否使用 caplog 或直接读 stderr。从名字推断是 caplog 路径（"log outputs" 而非 "stderr"），但需实施时确认。

- **影响**: 实施 Agent 可能误解为需要修改旧测试，引入不必要的工作量

- **建议改法和验证点**:
  1. 实施 Slice A 前，先读 `test_fins_direct_verbose_log_outputs_execution_skeleton` 确认其断言方式（caplog vs stderr）
  2. 若使用 caplog：只在 Slice A 新增 log-file 写文件测试，旧测试无需修改
  3. 更新 plan 的 affected tests 列表，精确区分"需新增"和"需更新"

- **修复风险**: 低
- **严重程度**: 低
- **裁决建议**: `accepted` — 实施时确认即可，非 plan 级别 blocker

---

### F6 — [Low] `--log-file` append 模式并发写入无保护

- **位置**: Slice A，implementation decisions 第 3 条（plan line 169-172）
- **问题类型**: 并发恢复风险
- **当前写法**: plan 选择 append + UTF-8，因为 "append 防止多次 invocation 共用同一路径时覆盖历史诊断"
- **反例/失败场景**:

  多个并发 `dayu-cli` 进程同时写同一个 `--log-file` 时，`StreamHandler` 的 `emit()` 不是原子的——多行日志记录可能交错。这不是数据损坏，但会导致日志不可读。考虑到诊断日志通常不需要事务性保证，这在实践中可能可接受。

- **为什么有问题**: 非阻塞但应 acknowledge。用户在 CI pipeline 中混合多个 dayu-cli 调用到一个 log file 时可能遇到交错日志。

- **直接证据**: `logging.StreamHandler.emit()` 不是线程/进程安全的；Python 的 logging 模块不提供进程级文件锁

- **影响**: 并发场景下日志行交错，但不丢数据；诊断用途可接受

- **建议改法和验证点**:
  1. plan 的 implementation decisions 中显式声明 "并发写同一文件不保证日志行原子性，属于已知限制"
  2. 或在 risks 中加入 "多进程并发写同一 log-file 可能导致日志行交错"
  3. 不需要加文件锁或 tee（plan 已明确不做此工程）

- **修复风险**: 低
- **严重程度**: 低
- **裁决建议**: `accepted` — 在 decisions 或 risks 中 acknowledge 即可

---

### F7 — [Low] `prompt --detail` 显式 enabled 与 `CliActivityRenderer` 构造函数契约未明确

- **位置**: Slice B，Exact changes 段落（plan line 250-259）
- **问题类型**: 契约缺失
- **当前写法**: plan line 257-258 说 "`args.detail` 为 `True`：创建显式 enabled renderer"，但未说明如何传递 `enabled=True`
- **反例/失败场景**:

  `CliActivityRenderer.__init__`（activity.py:55-80）接受 `options: CliActivityRendererOptions | None`。当 `options=None` 时，`enabled=self._stderr.isatty()`。若调用方只传 `visible=True` 而不传 `enabled=True`，非 TTY 环境下依然 disabled。

  正确的构造方式是 `CliActivityRenderer(options=CliActivityRendererOptions(visible=True, enabled=True))`。但 plan 未明确引用 `CliActivityRendererOptions`。

- **为什么有问题**: 实施 Agent 可能错误地只调用 `CliActivityRenderer()`（默认 `enabled=isatty()`），导致 `--detail` 在 CI 非 TTY 环境不生效，与 plan 的意图 "用户显式要求 detail 时应可在 CI/log 捕获中看到 activity"（plan line 181）冲突。

- **直接证据**:
  - `activity.py:70-76`：默认 options 时 `enabled=self._stderr.isatty()`
  - plan line 181："是否 TTY 不再是 detail 的唯一开关；用户显式要求 detail 时应可在 CI/log 捕获中看到 activity"

- **影响**: `--detail` 在非 TTY 环境可能不生效

- **建议改法和验证点**:
  1. Slice B 的 Exact changes 中显式写明：`CliActivityRenderer(options=CliActivityRendererOptions(visible=True, enabled=True))`
  2. 验证点：新增非 TTY test（pipe stdin），确认 `prompt "hello" --detail` 产生 activity 输出

- **修复风险**: 低
- **严重程度**: 低
- **裁决建议**: `accepted` — 实施时修正即可

---

## Architecture Boundary Review

Plan 正确识别了以下边界：

1. **CLI 层独占 UI 状态**：plan 声明 "只在 CLI 层增加必要 UI 状态，不把 UI 状态上抛到 Service / Host"（plan line 187）。这符合现有架构——`composer.py` 和 `run_keys.py` 已把 prompt_toolkit 和 termios 隔离在 CLI 层。

2. **Service `on_activity` 是正确边界**：plan 正确识别 Service 的 `on_activity` callback 已足够承载 CLI UI，不需要 Host/Engine 变更（plan line 156-158）。

3. **`runtime/log.py` 的修改范围受限**：plan 限制只改 handler close 生命周期，不改 level/public contract（plan line 94-95）。

**边界风险（已由 F1 覆盖）**：若 Slice C 的 prompt_toolkit TUI 实现需要改变 `TtyRunningKeyMonitor` 的 stdin 所有权模型（termios.cbreak vs prompt_toolkit 内部处理），则 `run_keys.py` 的边界可能需要重新设计。当前 plan 未识别此耦合。

## Overengineering Review

plan 的 overengineering 风险评估：

1. **窄协议可能过度**：plan line 291-298 定义的 `read/record_activity/render_terminal_result/toggle_view/render_cancel_requested/render_local_exit_after_cancel/close` 七方法协议中，`render_cancel_requested` 和 `render_local_exit_after_cancel` 已在 `CliActivityRenderer` 中存在（activity.py:134-154）。若最终方案（F1 方案 A）保留 `CliActivityRenderer`，则这些方法不需要复制到新协议。

2. **其他方面适度**：plan 明确拒绝引入 rich/textual、日志 sink registry、多 sink tee、Host/Engine contract 变更——这些都是正确的克制。

## Best-Practice Review

1. **默认 `--no-detail`**：符合 "默认安静" 的 CLI 最佳实践，正确。

2. **`--log-file` 与 `--log-level` 正交**：符合 Unix `--log-file` + `--log-level` 惯例，正确。

3. **append 模式、不自动创建父目录**：plan 的 append 理由（"防止覆盖历史诊断"）和不出创建父目录的理由（"避免因拼错路径静默创建"）都是合理的设计选择。

## Optimal-Solution Review

plan 选择的方案是 minimal change 方向：

- 复用 `global_parent`、`runtime_log` stream override、Service `on_activity`——正确
- 仅增 `ParsedCliArgs` 字段，不过度重构——正确
- 非 TTY fallback 保留现有行为——正确

有一个替代方案值得考虑：**`--log-file` 与 tee**。plan 选择 "不支持同时写 stderr 和 file"（plan line 176："不支持同时写 stderr 和 file，除非用户后续明确需要 tee"）。这在诊断场景中是合理的（避免重复输出），但用户在调试时可能希望同时看到终端日志和文件日志。这是合理的 deferred decision，不是 plan 缺陷。

## Open Questions

| # | Question | Severity | Suggested resolution |
|---|----------|----------|---------------------|
| Q1 | 见 F1：interactive running-state view 的实际渲染机制 | 高 | 选型 A 或 B，写出具体伪代码 |
| Q2 | 见 F4：TUI 测试在 CI 中的 PTY 依赖 | 中 | 与 F1 联动，确认测试策略 |
| Q3 | `--log-file` 文件名含空格或特殊字符的处理边界 | 低 | argparse `type=str` 天然处理；main 中 strip 后非空检查已覆盖（plan line 215 "校验 strip 后非空"） |
| Q4 | atexit / SIGTERM / SIGQUIT 退出时 log file flush 是否保证 | 低 | `StreamHandler` 默认不缓冲（`logging.NOTSET` 级别）；但 Python 进程异常退出时 handler 的 flush 不被调用——属于 Python logging 已知限制，不应由 plan 解决 |

## Residual Risks

| Risk | Severity | Suggested tracking |
|------|----------|-------------------|
| interactive TUI 实际渲染机制未选定（F1） | 高 | 在 Slice C 开始前做技术 spike，确认 prompt_toolkit Application 可行性或选定 ANSI 方案 |
| `prompt --detail` 非 TTY enabled 遗漏（F7） | 低 | 在 Slice B 完成时通过非 TTY test 验证 |
| 多进程并发写 log file 交错（F6） | 低 | 文档 acknowledge，无需额外工程 |
| `--log-file` 测试 teardown 中 handler 残留 | 低 | 在 Slice A 的 main 中实现 finally 恢复逻辑（F2）后自然解决 |

## Final Plan Review Conclusion

**Verdict: `pass-with-risks`**

Plan 的动机研判正确、scope boundary 清楚、Slice A/B 可直接实施。四个 Slice 按 risk 自然拆分，每片有独立可测结果。Host/Engine public API 判断保守且正确。

**但 Slice C（interactive TUI）有一个 high-severity unresolved design decision（F1）**：running-state view 的渲染机制与当前 prompt_toolkit 生命周期的冲突未被 plan 识别。这不应在 plan gate 解决（属于 Slice C 内部的设计选型），但必须在 Slice C 开始前通过技术 spike 收敛，否则 Slice C 的 implementation cost 估计和架构设计都不足。

另外两个 medium findings（F2 handler close 顺序、F4 测试策略）是实施细节级别——在当前 plan 中补充即可，无需 gate fail。

**建议**：
1. 接受 Slice A 和 Slice B，补充 F2/F3/F7 的修正到 plan Exact changes
2. Slice C 开始前，做 prompt_toolkit TUI 技术 spike（30-60 min），选型 A 或 B 并更新 plan，然后继续 gate
3. Slice C 若选方案 A，上述 risks 降级；若选方案 B，Slice C 应独立为单独 work unit
