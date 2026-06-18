# WU-CLI-ACTIVITY-01 CLI Slices C/D/E/F Code Review

## Scope

- Mode: current changes (unstaged diff + new untracked files)
- Branch: wu-cli-activity-01
- Base: main
- Output file: docs/reviews/code-review-wu-cli-activity-01-cli-ds-20260617-145226.md
- Review focus: slices C/D/E/F CLI implementation — TTY key handling, activity renderer, composer, running state machine
- Implementation artifact: docs/reviews/wu-cli-activity-01-cli-implementation-codex.md
- Plan: docs/host/host-issues/wu-cli-activity-01-activity-composer-plan.md
- Parallel review coverage: 4 个 subagent 并行覆盖 run_keys.py TTY 安全、interactive 运行态状态机、activity/composer 渲染与输入、类型/docstring/测试合规

### Included scope

| File | Status |
|---|---|
| dayu/cli/run_keys.py | new (untracked) |
| dayu/cli/activity.py | new (untracked) |
| dayu/cli/composer.py | new (untracked) |
| dayu/cli/commands/interactive.py | modified |
| dayu/cli/commands/prompt.py | modified |
| tests/cli/test_run_keys.py | new (untracked) |
| tests/cli/test_activity_renderer.py | new (untracked) |
| tests/cli/test_interactive_composer.py | new (untracked) |
| tests/cli/test_interactive_command.py | modified |
| tests/cli/test_prompt_command.py | modified |
| tests/README.md | modified |

### Excluded scope

- Slice A/B 已接受 commits 中的 Host/Service 层代码
- docs/reviews/ 下的 implementation/fix artifacts
- F-2（`cancel_entrypoint_run_and_wait on_activity`）已裁决延期到 Slice E

## Findings

### 1-未修复-中-`CliActivityRenderer._last_hidden_title` 在可见期间未设置导致首次隐藏时无状态提示

- **入口/函数**: `CliActivityRenderer.record` → `CliActivityRenderer.toggle_visible`
- **文件(行号)**: `dayu/cli/activity.py:113-115, 128-132`
- **输入场景**: renderer 以 `visible=True` 初始化，activity 正常输出到 stderr，随后用户按 Ctrl+T 切换到隐藏
- **实际分支**: `record()` 行 113: `if not self._visible:` — visible 期间此条件为 False，`_last_hidden_title` 保持 `None`。`toggle_visible()` 行 128: `self._last_hidden_title is not None` 检查失败，"Activity hidden" 消息不输出
- **预期行为**: Plan §7.3 规定 "隐藏时保留一行短状态"——切换隐藏时应输出当前被隐藏的 activity title
- **实际行为**: 首次从可见切换到隐藏时静默，用户无反馈；只有从隐藏状态再次记录 activity 后再切回隐藏时才显示 "Activity hidden"
- **直接证据**:
  - 行 113: `if not self._visible:` — `_last_hidden_title` 仅在 `_visible=False` 时写入
  - 行 128: `self._last_hidden_title is not None` — visible 期间从未写入，首次 toggle 不输出
  - `test_activity_renderer_hidden_keeps_terminal_area_clean`（test_activity_renderer.py:65-81）renderer 以 `visible=False` 初始化，不经过 visible→hidden 切换，漏测此路径
- **影响**: 用户按 Ctrl+T 隐藏 activity 时无反馈，不符合 plan "隐藏时保留一行短状态"
- **建议改法和验证点**: 将 `self._last_hidden_title = activity.title` 移到 `if not self._visible:` 守卫之前（行 113 上方），使 title 始终被追踪。添加测试：renderer 以 visible=True 启动 → 记录 activity → toggle 到 hidden → 验证 stderr 输出 "Activity hidden: 工具批次完成"
- **修复风险**: 低（单行移动，不影响其他路径）
- **严重程度**: 中

### 2-未修复-中-prompt 路径第二次 SIGINT 期间缺少本地退出机制

- **入口/函数**: `_cancel_prompt_turn_after_local_request` → `cancel_entrypoint_run_and_wait`
- **文件(行号)**: `dayu/cli/commands/prompt.py:448-471`
- **输入场景**: prompt 运行态下用户按 Esc/Ctrl+C 发起 cancel 后，cancel 尚未返回 terminal 时用户再次按 Ctrl+C
- **实际分支**: `_cancel_prompt_turn_after_local_request`（行 462）直接调用 `cancel_entrypoint_run_and_wait(...)`，该函数内部循环等待 terminal（`_wait_for_terminal` 行 726-745），不监测 `CliSigintMonitor` 的第二次 SIGINT
- **预期行为**: Plan §7.4 规定 "Ctrl+C：运行态第一次请求 cancel_run(...)；若 cancel 已发出但 terminal 未返回，第二次 Ctrl+C 立即本地退出 130"
- **实际行为**: 第二次 Ctrl+C 被 `CliSigintMonitor._handler` 吸收（计数器递增但无人消费），`cancel_entrypoint_run_and_wait` 继续阻塞等待 terminal，用户无法加速退出
- **直接证据**:
  - prompt.py 行 462: `return await cancel_entrypoint_run_and_wait(host, request=...)` — 无 `second_sigint_task` 或等价中断路径
  - 对比 interactive.py `_cancel_run_waiting_for_terminal_or_second_sigint` 行 696-718 — 正确构造 `second_sigint_task` + 双路 wait
  - entrypoint_runtime.py `_wait_for_terminal` 的 `await sleep()` 不被自定义 SIGINT handler 中断
- **影响**: prompt 单轮命令下 cancel 等待期间用户无法通过第二次 Ctrl+C 立即退出；cancel 通常快速完成，实际影响有限；interactive 路径已正确实现
- **建议改法和验证点**: 在 `_cancel_prompt_turn_after_local_request` 中增加第二次 SIGINT 监测——创建 `second_sigint_task` 与 `cancel_task` 并行 wait；或给 `cancel_entrypoint_run_and_wait` 增加可选的 `sigint_monitor` 参数。可归入 Slice E 收尾
- **修复风险**: 低（interactive 路径已有成熟模式可复用）
- **严重程度**: 中

### 3-未修复-中-`TtyRunningKeyMonitor.start()` 中 thread 启动失败后终端无法恢复

- **入口/函数**: `TtyRunningKeyMonitor.start()` → interactive.py/prompt.py `monitor.start()` 调用位置
- **文件(行号)**: `dayu/cli/run_keys.py:164-170`; `dayu/cli/commands/interactive.py:481`; `dayu/cli/commands/prompt.py:363`
- **输入场景**: `tty.setcbreak(fd)` 成功（行 156），终端已进入 cbreak 模式；随后 `self._thread.start()`（行 170）因系统资源耗尽抛出 `RuntimeError`
- **实际分支**: `RuntimeError` 不是 `OSError, ValueError, termios.error` 的子类，不被行 157 的 except 块捕获。异常向上传播到 interactive.py 行 481 / prompt.py 行 363——二者均在 `try/finally` 块之外调用 `monitor.start()`
- **预期行为**: 若 thread 启动失败，终端应恢复到原始模式
- **实际行为**: `self._fd` 和 `self._original_attrs` 已在行 161-162 设置（在 thread 创建之前），`close()` 有能力恢复——但 `monitor.start()` 在 `try/finally` 外，异常传播后 finally 不执行，`monitor.close()` 不会被调用。终端永久留在 cbreak 模式（echo 关闭、行规范关闭），用户必须手动执行 `reset` 或 `stty sane`
- **直接证据**:
  - run_keys.py 行 157: `except (OSError, ValueError, termios.error):` — 不覆盖 `RuntimeError`
  - run_keys.py 行 164: `self._started = True` — 在 thread 启动前置位，阻止重试
  - interactive.py 行 481 vs 509: `monitor.start()` 在 try 块之前
  - prompt.py 行 363 vs 391: 同模式
- **影响**: 极端场景下（系统线程资源耗尽）终端不可用；正常运行时 `Thread.start()` 不会失败（daemon thread + 单次调用），实际风险极低
- **建议改法和验证点**: 方案 A（推荐）：将 `monitor.start()` 移入 try/finally 保护范围。方案 B：在 `start()` 内部用 try/except 包裹 `self._thread.start()`，异常中恢复终端属性并复位 `_started`。添加 `close()` 在 `start()` 失败后的安全性测试
- **修复风险**: 低
- **严重程度**: 中（概率极低但影响高）

### 4-未修复-中-interactive 的 Ctrl+T 切换 activity 及第二次 SIGINT 本地退出消息缺乏测试覆盖

- **入口/函数**: `_submit_interactive_turn_handling_sigint` Ctrl+T 分支; `_cancel_run_waiting_for_terminal_or_second_sigint` 第二次 SIGINT 分支
- **文件(行号)**: `dayu/cli/commands/interactive.py:519-523, 713-714`
- **输入场景**: (a) 运行态用户按 Ctrl+T 切换 activity 可见性; (b) 第二次 SIGINT 时 renderer 非 None
- **实际分支**:
  - Ctrl+T: 行 519-523 — `TOGGLE_ACTIVITY` 调用 `renderer.toggle_visible()` 后创建新 `key_task` 并 `continue`
  - 第二次 SIGINT: 行 713-714 — `renderer.render_local_exit_after_cancel()` 输出 "Activity: cancelling; local process exiting"
- **预期行为**: 两个分支均应有测试覆盖
- **实际行为**: prompt 路径有 `test_prompt_ctrl_t_toggles_running_activity_without_cancel` 覆盖，但 **interactive 路径无任何测试注入 `TOGGLE_ACTIVITY` 的 key_monitor**。`test_interactive_second_sigint_exits_after_cancel_request` 未传入 `activity_renderer`，`render_local_exit_after_cancel()` 从未被调用
- **直接证据**:
  - `test_interactive_esc_requests_cancel_after_run_id` 使用 `CANCEL_RUN` 而非 `TOGGLE_ACTIVITY`
  - `test_interactive_second_sigint_exits_after_cancel_request` 不传 `activity_renderer`
  - `test_interactive_tty_activity_finishes_before_next_prompt` 走全 REPL 路径但 key_monitor 由 `new_running_key_monitor()` 在测试环境下返回 `NoopRunningKeyMonitor`
- **影响**: 两个代码分支的行为不可通过自动化测试验证
- **建议改法和验证点**: (a) 新增 interactive Ctrl+T toggle 测试：注入 `TOGGLE_ACTIVITY` + 延迟 terminal，验证 `renderer.visible` 翻转、cancel 未发起、monitor 生命周期正确; (b) 修改 `test_interactive_second_sigint_exits_after_cancel_request` 传入 `activity_renderer`，验证 stderr 包含 "local process exiting"
- **修复风险**: 低
- **严重程度**: 中

### 5-未修复-低-`_cancel_and_await_task` 与 `_AcceptedRunState` 在 interactive.py 和 prompt.py 中完全重复

- **入口/函数**: `_cancel_and_await_task`, `_AcceptedRunState`, `_TaskResult`
- **文件(行号)**: `dayu/cli/commands/interactive.py:88, 109-147, 554-566`; `dayu/cli/commands/prompt.py:85, 108-147, 474-485`
- **输入场景**: 代码维护——修改 task 取消语义或 accepted run 状态结构时需同步两处
- **实际分支**: N/A（代码结构问题）
- **预期行为**: CLAUDE.md 明确规定 "重复逻辑必须抽取"
- **实际行为**: 三个组件（`_TaskResult` TypeVar、`_AcceptedRunState` dataclass、`_cancel_and_await_task` 函数）在两个命令文件中字面逐字符一致
- **直接证据**: diff 中 interactive.py 和 prompt.py 各自独立定义了这三个组件
- **影响**: 维护负担，未来修改需同步两处，遗漏一处即产生行为不一致
- **建议改法和验证点**: 抽取到 `dayu/cli/commands/_turn_helpers.py` 或 `dayu/cli/agent_entrypoint.py`，两命令文件改为导入
- **修复风险**: 低（纯重构）
- **严重程度**: 低

### 6-未修复-低-`build_interactive_key_bindings` 使用嵌套函数

- **入口/函数**: `build_interactive_key_bindings`
- **文件(行号)**: `dayu/cli/composer.py:106-135`
- **输入场景**: N/A（结构问题）
- **实际分支**: 4 个嵌套函数通过 `@bindings.add` 装饰器注册
- **预期行为**: CLAUDE.md 规定 "禁止无必要的嵌套函数、嵌套类"
- **实际行为**: 虽然 prompt_toolkit 的 `@bindings.add` 装饰器模式需要闭包捕获 `bindings` 对象，但未在代码注释中说明此必要性
- **直接证据**: composer.py 行 106-135: 四个嵌套函数定义在 `build_interactive_key_bindings` 内部
- **影响**: 轻微违反编码约束，功能不受影响
- **建议改法和验证点**: 添加注释说明 prompt_toolkit API 要求使用闭包模式；或将每个 handler 提升为模块级私有函数（但会失去 `@bindings.add` 的便利性）
- **修复风险**: 低
- **严重程度**: 低

### 7-未修复-低-`_drain_available_watcher_items` docstring 未反映 callback 异常透传

- **入口/函数**: `_drain_available_watcher_items`
- **文件(行号)**: `dayu/service/entrypoint_runtime.py:762`
- **输入场景**: `on_activity` callback 抛异常
- **实际分支**: callback 异常从 `_emit_entrypoint_activity_from_host_event`（行 817）→ `_drain_available_watcher_items`（行 785-790）自然透传
- **预期行为**: docstring 应提及 callback 异常会透传
- **实际行为**: docstring 声明 `:raises Exception: 不主动抛出异常。`
- **直接证据**: 行 762 docstring；行 785-790 无 try/except 包裹 callback 调用
- **影响**: 仅文档可读性
- **修复风险**: 无
- **严重程度**: 低

## 逐项复审结论

### 1. run_keys.py TTY cbreak/thread/close/termios restore — 基本正确，存在一个低概率防御性缺口

- **cbreak 设置路径**: `isatty()` → `fileno()` → `tcgetattr` → `setcbreak`，每个失败路径在 `except (OSError, ValueError, termios.error)` 中正确处理（行 157-160）
- **后台线程**: daemon thread + `select.select` 轮询 + `call_soon_threadsafe` 投递——正确
- **关闭路径**: idempotent（`_closed` flag）+ `_stop_event.set()` + `thread.join(0.2s)` + `_restore_terminal_attrs`——正确
- **termios 恢复**: `_restore_terminal_attrs`（行 261-273）有独立 try/except
- **PTY 测试**: 验证了 lflag ECHO/ICANON/ISIG/IEXTEN 恢复一致性
- **已知缺口**: Finding 3（thread 启动失败后终端无法恢复）；`call_soon_threadsafe` 的 `RuntimeError` 未被后台线程捕获（行 229）——低风险，仅影响错误日志整洁度

结论：**核心 TTY 安全正确，Finding 3 为低概率防御性缺口**。

### 2. prompt/interactive 运行态状态机 — 核心正确

- **三路并发 wait**（`submit_task, sigint_task, key_task`）: 正确
- **terminal-first-wins**: `submit_task in done` → 直接返回，不发起 cancel
- **Ctrl+T toggle**: 旧 key_task 已 done → 创建新 key_task → continue —— 无 task leak
- **Esc cancel**: 传入初始 `observed_sigint_count` 作为第二次 SIGINT 基线——正确
- **第二次 SIGINT 本地退出**（interactive）: `_cancel_run_waiting_for_terminal_or_second_sigint` 双路 wait，cancel_task vs second_sigint_task——正确
- **资源清理 finally**: renderer.close() → monitor.close() → sigint_monitor.close() → cancel-and-await tasks——顺序正确
- **已知缺口**: Finding 2（prompt 第二次 SIGINT）、Finding 3（monitor.start() 保护范围）、Finding 4（测试覆盖缺口）

结论：**核心状态机逻辑正确，防御性和测试覆盖有改进空间**。

### 3. stdout/stderr 分离与 non-TTY 行为 — 正确

- 所有 activity 输出通过 `print(..., file=self._stderr)` 写 stderr
- `enabled` 默认 `self._stderr.isatty()`——non-TTY 自动禁用 live activity
- 所有输出路径检查 `self._enabled` 和 `self._closed`
- final answer 仍由现有 renderer 写 stdout——未修改
- dedupe key + event_sequence 双重过滤；每 turn 新建 renderer，state bounded

结论：**无问题**。

### 4. composer Ctrl+J/Ctrl+R/Ctrl+X Ctrl+E — 正确

- **Ctrl+J**: `buffer.insert_text("\n")`——在 `multiline=False` 下插入换行，Enter 提交
- **Ctrl+R**: `buffer.start_history_lines_completion()`——配合 `enable_history_search=True` + `InMemoryHistory`
- **Ctrl+C**: 非空 draft `buffer.reset()`，空 draft `event.app.exit(exception=KeyboardInterrupt)`——符合 plan
- **Ctrl+X Ctrl+E**: `open_in_editor(validate_and_handle=False)` + `Exception` 捕获输出到 stderr
- **`handle_sigint=False`**: 关闭 prompt_toolkit 默认 SIGINT 处理，由自定义 Ctrl+C binding 接管
- **TTY 检测**: `new_interactive_composer` → `isatty()` → 路由 `PromptToolkitInteractiveComposer` 或 `InputReaderComposer`
- **已知缺口**: Finding 6（嵌套函数）

结论：**功能正确可用**。

### 5. 类型/docstring/AGENTS 约束和测试覆盖 — 基本合规

- **类型**: 完整类型注解，pyright 0 errors
- **docstring**: 所有公开函数/类/模块完整中文 docstring
- **AGENTS 约束**: 无 `Any`/`object`/`hasattr`；无 God object；`__all__` 完整
- **架构边界**: CLI → Service DTO（方向正确）；`InteractiveComposer`/`RunningKeyMonitor` 为 Protocol；不 import Engine/Host 内部
- **测试**: 61 passed，90% 覆盖率
- **已知缺口**: Finding 4（测试覆盖缺口）、Finding 5（代码重复）、Finding 6（嵌套函数）、Finding 7（docstring）

结论：**合规，有可改进项**。

## Open Questions

- 无。

## Residual Risk

| 风险 | 严重度 | 说明 |
|---|---|---|
| prompt 第二次 SIGINT | 中 | Finding 2；建议 Slice E 收口 |
| `_last_hidden_title` bug | 中 | Finding 1；用户可见的 "Activity hidden" 提示缺失 |
| thread 启动失败终端恢复 | 中 | Finding 3；概率极低但影响高 |
| interactive Ctrl+T / 第二次 SIGINT 消息无测试 | 中 | Finding 4；行为正确但不可自动验证 |
| 代码重复 | 低 | Finding 5；`_cancel_and_await_task` / `_AcceptedRunState` |
| 嵌套函数 | 低 | Finding 6；prompt_toolkit API 惯例 |
| 手动 TTY smoke test | 低 | 实现 artifact 声明未进行真实终端手动测试 |
| 非 INFO severity 渲染未测试 | 低 | `_activity_line` 的 WARNING/ERROR 标签路径 |
| `_bounded_text` Unicode grapheme 截断 | 低 | 仅影响展示，CJK/ASCII 财务领域不触发 |
| `cancel_entrypoint_run_and_wait` 无 on_activity | 已知延期 | F-2，Slate E |

## 验证结果

- `pytest tests/cli/test_run_keys.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py -q`: **61 passed**, 3 warnings
- `pyright dayu/cli/ tests/cli/`: **0 errors, 0 warnings, 0 informations**
- Coverage: **90%** total (activity 93%, composer 94%, run_keys 90%, interactive 88%, prompt 91%)

## 复审结论

**非阻断**。Slices C/D/E/F CLI 实现核心正确：

- TTY cbreak/thread/close/termios restore 路径安全（存在低概率防御性缺口 Finding 3）
- 运行态三路并发状态机：Ctrl+T toggle、Esc cancel、Ctrl+C cancel、terminal-first-wins 均满足 plan（prompt 第二次 SIGINT 待收口 Finding 2）
- stdout/stderr 分离正确，non-TTY 默认不输出 live activity
- Composer Ctrl+J/Ctrl+R/Ctrl+X Ctrl+E 真实可用，prompt_toolkit 隔离良好
- 类型/docstring/AGENTS 约束合规

**4 个中等发现建议在 Slice E 或独立 fix 中修复：**

| # | 严重度 | 简述 |
|---|---|---|
| 1 | 中 | `_last_hidden_title` 在 visible 期间未设置，"Activity hidden" 消息缺失 |
| 2 | 中 | prompt 路径第二次 SIGINT 缺少本地退出 |
| 3 | 中 | `monitor.start()` 中 thread 启动失败后终端恢复缺口 |
| 4 | 中 | interactive Ctrl+T toggle 和第二次 SIGINT 消息缺少测试覆盖 |

3 个低严重度发现（代码重复、嵌套函数、docstring）可在后续顺手修正。
