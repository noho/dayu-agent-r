# Code Review — WU-CLI-01 / CLI-01-S3 Prompt Implementation

## Scope

- **Mode**: current changes
- **Branch**: `phase/host-ui-implementation`
- **Base**: `main`（按 deepreview 默认）
- **Output file**: `docs/reviews/wu-cli-01-s3-implementation-review-ds.md`
- **Review date**: 2026-06-14
- **Included scope**:
  - `dayu/cli/commands/prompt.py`（新增）
  - `dayu/cli/host_context.py`（新增）
  - `dayu/cli/output.py`（新增）
  - `dayu/cli/arg_parsing.py`（修改）
  - `dayu/cli/main.py`（修改）
  - `dayu/service/entrypoint_runtime.py`（修改 — 仅 `on_run_accepted` callback）
  - `tests/cli/test_prompt_command.py`（新增）
  - `tests/service/test_entrypoint_runtime_prompt_path.py`（新增）
  - `tests/cli/test_arg_parsing.py`（修改 — placeholder 命令改为 `interactive`）
  - `tests/README.md`（修改）
  - `dayu/service/README.md`（修改）
  - `docs/host/ui-implementation-control.md`（修改 — 控制文档状态更新）
- **Excluded scope**: S1/S2 已合入代码、未修改的 `dayu/host/` / `dayu/engine/` / `dayu/fins/` 内部、旧 `dayu-agent` 仓库
- **裁决标准**: 本轮是迁移旧 `dayu-agent` prompt 的业务逻辑/用户可见语义，适配新 Host public contracts/API，不是迁移旧代码实现，不把旧实现一致性当作正确性

## 验证命令执行结果

```
# 测试
source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_arg_parsing.py tests/service/test_entrypoint_runtime.py -q
→ 62 passed, 3 edgar deprecation warnings（无关）

# 覆盖率
source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_arg_parsing.py --cov=dayu.cli.commands.prompt --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov-report=term-missing -q
→ 41 passed, 总覆盖率 95%（arg_parsing.py 100%, prompt.py 91%, host_context.py 98%, output.py 80%）

# pyright
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
→ 0 errors, 0 warnings, 0 informations
```

## Findings

### 1-未修复-低-`render_prompt_terminal_result` 的 CANCELLED/LOST/SUCCEEDED-without-answer 路径无直接测试覆盖

- **入口/函数**: `render_prompt_terminal_result`
- **文件(行号)**: `dayu/cli/output.py:26-59`（未覆盖行 45-46, 50-54, 56-57）
- **输入场景**: Host 返回 CANCELLED 终态、LOST 终态，或 SUCCEEDED 终态但 `final_answer=None`
- **实际分支**: `result.terminal_status is HostTerminalStatus.CANCELLED`、`is HostTerminalStatus.LOST`、或 `is HostTerminalStatus.SUCCEEDED` 且 `result.final_answer is None`
- **预期行为**: CANCELLED→输出取消原因到 stderr、返回 130；LOST→输出错误消息到 stderr、返回 1；SUCCEEDED 但无 final_answer→输出缺失提示到 stderr、返回 1
- **实际行为**: 分支逻辑正确，但未通过直接测试验证。现有 `test_prompt_sigint_after_run_id_cancels_host_run` 验证了 `EntrypointRunTerminalResult.terminal_status is CANCELLED` 但未调用 `render_prompt_terminal_result` 断言退出码和 stderr 内容
- **直接证据**: 覆盖率报告 `output.py` 行 45-46, 50-54, 56-57 标记为 Miss；测试 `test_prompt_terminal_failed_outputs_error` 覆盖了 FAILED 路径（行 58-59 已覆盖）但无对应 CANCELLED/LOST/无 final_answer 的输出验收测试
- **影响**: 低 — 渲染函数逻辑简单（纯 switch + print），分支由 enum dispatch 驱动，回归风险很小。但 LOST 和 SUCCEEDED-without-answer 是两个防御性分支，若 Host 行为异常时缺少输出验证，可能静默展示错误信息
- **建议改法和验证点**: 增加 2 个参数化测试：(a) 构造 `terminal_status=CANCELLED` 的 `EntrypointRunTerminalResult`，断言 `render_prompt_terminal_result` 返回 130、stderr 包含 cancel_reason；(b) 构造 `terminal_status=LOST` 的结果，断言返回 1、stderr 包含 error_message。SUCCEEDED-without-answer 的防御分支建议一并覆盖
- **修复风险（低）**: 纯测试补充，不改生产代码
- **严重程度（低）**: 不阻塞 merge，建议后续补齐

### 2-未修复-低-`_PromptSigintMonitor.install` 在非 SelectorEventLoop 环境静默降级

- **入口/函数**: `_PromptSigintMonitor.install`
- **文件(行号)**: `dayu/cli/commands/prompt.py:105-121`
- **输入场景**: 运行在 `ProactorEventLoop`（Windows）或不支持 `add_signal_handler` 的事件循环上
- **实际分支**: `loop.add_signal_handler(signal.SIGINT, self.notify)` 抛出 `NotImplementedError` 或 `RuntimeError` → 分支 `except (NotImplementedError, RuntimeError): self._installed = False; self._loop = None; return`
- **预期行为**: 文档说明"不支持 loop signal handler 时保留默认 KeyboardInterrupt 行为"，即回退到 Python 默认 SIGINT→KeyboardInterrupt
- **实际行为**: 降级生效。Run accepted 前 SIGINT 仍然走 `KeyboardInterrupt` → exit 130 语义正确。Run accepted 后 SIGINT 会触发 `KeyboardInterrupt` 而非 typed Host cancel，导致 Run 最终走 Host 端超时/LOST 而非 CANCELLED
- **直接证据**: `prompt.py:116-119`（`except` 分支）覆盖率 Miss，confirm 该路径只在 unsupported loop 环境触发；`_run_prompt_command_async:199-206`（`KeyboardInterrupt`/`Exception` 外 catch）同样 Miss
- **影响**: 低 — 当前目标平台（macOS/Linux）的默认 SelectorEventLoop 完全支持 `add_signal_handler`；Windows 非当前部署目标；即使触发，Host 端最终也会因 worker 失联而 LOST 收口，不会无限悬挂
- **建议改法和验证点**: 若未来有跨平台需求，可在 `_PromptSigintMonitor` 增加 `supports_typed_cancel: bool` 属性，供 CLI 在降级时向用户发出提示（如 stderr 输出"当前环境不支持运行中 typed cancel，Ctrl-C 将立即退出"）。当前不修改亦可接受
- **修复风险（低）**: 只增加诊断提示，不改控制流
- **严重程度（低）**: 不阻塞 merge

## 逐项裁决

### 1. Prompt 路径合规性 — Pass

CLI adapter (`prompt.py`) 的主链路：

```
CLI args → EntrypointRuntimeRequest → prepare_entrypoint_runtime()
  → resolve_runtime_locations → ConfigLoader.load → discover_service_tools
  → prepare_scene → compose_open_host_options
→ open_host(runtime.host_assembly.options)
→ ensure_or_create_entrypoint_session (Host.ensure_session / Host.create_session)
→ submit_entrypoint_turn_and_wait
  → compose_submit_followup_request_with_overrides
  → Host.submit_followup (submit 前已 attach watch_session_events)
  → _wait_for_terminal (live event / get_run / read_outbox_terminal_items)
→ render_prompt_terminal_result
```

- 无直接 `dayu.engine` import，无 Engine request 构造 ✅
- 无 Host durable/internal import ✅
- 无 `dayu.fins.storage` 访问 ✅
- Service assembly 通过 `prepare_entrypoint_runtime` 完成 ConfigLoader → ScenePrepare → ToolsDiscovery → compose_open_host_options 的完整编排 ✅

### 2. CLI / Service 边界 — Pass

- CLI (`prompt.py`, `output.py`, `host_context.py`) 负责：CLI 参数校验、构造 `EntrypointRuntimeRequest`/`HostCallContext`/`client_request_id`、SIGINT monitor 安装/拆除、stdout/stderr 输出、退出码映射 ✅
- Service (`entrypoint_runtime.py`) 不解析 CLI、不安装 signal handler、不写终端 ✅
- Service helper 的入参全部是 typed DTO（`EntrypointTurnRequest`、`EntrypointCancelRequest` 等），无 CLI 专有概念 ✅
- 未来 WeChat/GUI adapter 可复用完全相同的 Service helper 语义（只需提供自己的 context 构造和输出渲染） ✅

### 3. 参数映射 — Pass

| 参数 | 映射 | 符合 accepted plan |
|------|------|-------------------|
| `--ticker` | `context_slot_values["fins_default_subject"]`；未提供时 `"未指定具体公司"` | ✅ |
| `--label` | stable Host slot key `cli.prompt.<label>`；无 label 创建 fresh session | ✅ |
| `--model-name` | `ServiceAssemblyOverrides.model_id` | ✅ |
| `--temperature` | `ServiceRunOverrides.temperature` → `RunnerCallOptions.temperature` | ✅ |
| `--tool-timeout-seconds` | `ServiceRunOverrides.tool_execution_timeout_seconds` → `AgentPolicy` | ✅ |
| `--max-iterations` | `ServiceRunOverrides.max_iterations` → `AgentPolicy` | ✅ |
| `--fallback-mode` / `--fallback-prompt` | `ServiceRunOverrides.fallback_mode` / `fallback_prompt` → `AgentPolicy` | ✅ |
| `--max-consecutive-failed-tool-batches` | `ServiceRunOverrides.max_consecutive_failed_tool_batches` → `AgentPolicy` | ✅ |
| `--thinking` / `--no-thinking` | unsupported → fail fast exit 2 | ✅ intentional deviation |
| `--web-provider` | unsupported → fail fast exit 2 | ✅ intentional deviation |
| `--debug-sse` / `--debug-tool-delta` / `--debug-sse-sample-rate` / `--debug-sse-throttle-sec` | unsupported → fail fast exit 2 | ✅ intentional deviation |
| `--enable-tool-trace` / `--tool-trace-dir` | unsupported → fail fast exit 2 | ✅ intentional deviation |
| `--max-duplicate-tool-calls` / `--duplicate-tool-hint-prompt` | unsupported → fail fast exit 2 | ✅ intentional deviation |
| `--doc-limits-json` / `--fins-limits-json` | unsupported → fail fast exit 2 | ✅ intentional deviation |

验证：
- `test_prompt_command_rejects_unsupported_old_execution_flags` 参数化覆盖了 `--thinking`/`--web-provider`/`--enable-tool-trace`/`--doc-limits-json` ✅
- `test_prompt_command_reports_all_unsupported_old_execution_flags` 验证所有 unsupported flag 统一列入错误消息 ✅
- `test_prompt_command_outputs_fast_live_terminal_and_converts_requests` 验证了 `--ticker`→context slot、`--label`→slot key、`--model-name`→assembly_overrides、`--temperature`→runner_options ✅
- `test_prompt_command_without_ticker_uses_default_context_slots` 验证了缺省 ticker 行为 ✅

### 4. SIGINT cancel 语义 — Pass

- Run accepted 前 SIGINT：
  - `_PromptSigintMonitor` 安装 signal handler → `notify()` 设置 event → `sigint_task` (wait_next) 返回 → `submit_task` 被 cancel → `accepted_run.run_id is None` → 返回 `None` → `run_prompt_command` 返回 `EXIT_KEYBOARD_INTERRUPT (130)` ✅
  - 测试：`test_prompt_sigint_before_run_id_returns_local_interrupt` 使用 `_ImmediateSigintMonitor` + `_BlockingSubmitHost`，断言 `result is None` 且 `cancel_requests == []` ✅
- Run accepted 后 SIGINT：
  - `accepted_run.run_id` 已记录 → 调用 `cancel_entrypoint_run_and_wait` → 构造完整 `EntrypointCancelRequest(context, run_id, client_request_id, reason="cli_sigint", mode=CancelMode.GRACEFUL)` → `cancel_entrypoint_run_and_wait` 内部先 `get_run` 检查是否已终态，非终态时 attach watcher → `cancel_run` → wait terminal ✅
  - 退出码 130 ✅
  - 测试：`test_prompt_sigint_after_run_id_cancels_host_run` 使用 `_AutoSigintMonitor`，断言 `cancel_requests[0].reason == "cli_sigint"`、`CancelMode.GRACEFUL`、`client_request_id` 以 `:turn-1:run-run-1:cancel:cli_sigint` 结尾 ✅
- 重复 SIGINT 不重复 cancel：
  - `prompt_cancel_client_request_id` 固定基于 `(invocation_id, turn_index, run_id, CLI_SIGINT_REASON)` → 同一 Run 同一 turn 的重复 cancel 复用同一 `client_request_id` ✅
  - Host 端 `(run_id, client_request_id)` 幂等吸收重复 cancel ✅
  - 测试：`_AutoSigintMonitor` 触发两次 notify（line 391-393），但 `cancel_requests` 只有一个 ✅
- SIGINT monitor `wait_next` 使用 `observed_count` 做门槛检查（`while self.count <= observed_count`），防止遗漏安装前已到达的信号 ✅

### 5. `on_run_accepted` hook 设计 — Pass

- `submit_entrypoint_turn_and_wait` 新增的 `on_run_accepted` 参数是 `Callable[[str], None]`（同步回调），在 `submit_followup` 返回后、`_wait_for_terminal` 开始前同步调用 ✅
- watcher attach-before-submit 不变：`_attach_watcher` 仍在 `submit_followup` 前执行（`entrypoint_runtime.py:402`） ✅
- terminal observation 不变：`_wait_for_terminal` 的逻辑完全不变 ✅
- caller-owned timeout contract 不变：helper 文档明确"本 helper 不持有内部 timeout"；`on_run_accepted` 是同步回调不改变等待语义 ✅
- 测试：`test_submit_entrypoint_turn_reports_accepted_run_id` 验证了 callback 在 submit 后、返回前被调用且收到正确的 `accepted_run_id` ✅

### 6. 编码规范与 AGENTS 约束 — Pass

- **中文 docstring**：所有新增/修改函数、类、模块均有完整中文 docstring，包含 `:param`/`:returns`/`:raises` ✅
- **无 `Any`/`object` 逃逸**：在 `prompt.py`、`host_context.py`、`output.py` 中扫描，无 `Any`、`object` 类型声明。`host_context.py:218` 使用 `str.strip()` 返回 `str`，类型安全 ✅
- **无 `hasattr`/`getattr`**：仅 `prompt.py:131` 对 `_loop` 使用 `is not None` 检查（正常属性访问），无 `hasattr`/`getattr` 动态派发 ✅
- **无兼容性 wrapper**：新增文件不存在为兼容旧导入路径的 re-export 或透传 facade ✅
- **无魔法字符串**：关键字符串均定义为模块级 `Final` 常量：`DEFAULT_FINS_SUBJECT`、`DEFAULT_BASE_USER`、`CONTEXT_SLOT_FINS_DEFAULT_SUBJECT`、`CONTEXT_SLOT_BASE_USER`、`PROMPT_TURN_INDEX`、`CLI_PROMPT_SCENARIO`、`CLI_SIGINT_REASON`、`PROMPT_SESSION_SCOPE` 等 ✅
- **无禁止 import**：CLI 不 import `dayu.engine`，不 import Host durable/internal，不 import `dayu.fins.storage` ✅
- **pyright**：`0 errors, 0 warnings, 0 informations` ✅
- **覆盖率**：各文件均 ≥ 80%（prompt.py 91%, host_context.py 98%, output.py 80%, arg_parsing.py 100%） ✅
- **测试隔离**：CLI 测试使用 mocked Host public API（`_FakeHost`），不启动真实 Host/Fins 业务路径 ✅
- **tests/README.md** 更新：记录了 prompt 命令测试的当前事实 ✅
- **dayu/service/README.md** 更新：补充了 `on_run_accepted` callback 的边界事实 ✅

## 主路径走读

### 正常路径（fast live terminal）

1. `run_prompt_command(args)` → `asyncio.run(_run_prompt_command_async(args))` → `_raise_for_unsupported_execution_options(args)` → unsupported flags fail fast ✅
2. `_resolve_workspace_root` → path expanduser/resolve → `_resolve_explicit_config_dir` → 校验 containment ✅
3. `new_cli_invocation(command_name="prompt", scenario="prompt", ticker=..., display_user="本地 CLI 用户")` → 构造 `CliInvocation` with `invocation_id=uuid4().hex`, `correlation_id="dayu-cli:prompt:<invocation_id>"` ✅
4. `prepare_entrypoint_runtime(EntrypointRuntimeRequest(workspace_root, package_config_root, explicit_config_dir, scene_id="prompt", context_slot_values, assembly_overrides, env))` → ConfigLoader → ScenePrepare → ToolsDiscovery → compose_open_host_options → `EntrypointRuntimeResult` ✅
5. `open_host(runtime.host_assembly.options)` → `async with` → Host handle ✅
6. `_ensure_prompt_session`：无 label → `create_new=True, bind_slot=False`；有 label → `create_new=False, bind_slot=True, scope="cli.prompt", slot_key="cli.prompt.<label>"` ✅
7. `_submit_prompt_turn_handling_sigint`：
   - `_PromptSigintMonitor.install()` → `loop.add_signal_handler(SIGINT, monitor.notify)` ✅
   - `asyncio.create_task(submit_entrypoint_turn_and_wait(...))` + `asyncio.create_task(sigint_monitor.wait_next(...))` ✅
   - `asyncio.wait(FIRST_COMPLETED)` → submit wins → cancel sigint_task → return terminal ✅
8. `render_prompt_terminal_result(terminal)` → SUCCEEDED → print final answer to stdout → exit 0 ✅

### SIGINT 路径

- Before accepted：sigint_task wins → cancel submit_task → `accepted_run.run_id is None` → return None → exit 130 ✅
- After accepted：sigint_task wins → cancel submit_task → `accepted_run.run_id == "run-1"` → `cancel_entrypoint_run_and_wait` → `get_run("run-1")` → 非终态 → attach watcher → `cancel_run(run_id, CancelRunRequest(...))` → wait terminal → CANCELLED → exit 130 ✅

### Outbox fallback 路径

- `_FakeHost(submit_terminal=None, run_statuses=(SUCCEEDED,), outbox_item=_outbox_item())`
- `_wait_for_terminal` 内：watcher queue 空 → `get_run` 返回 `SUCCEEDED` → `_read_outbox_terminal` → `read_outbox_terminal_items` → 扫描 items 匹配 run_id → 返回 outbox terminal ✅
- 测试：`test_prompt_command_uses_outbox_fallback_when_live_terminal_missing` 断言 `exit_code == EXIT_SUCCESS`，`read_outbox_requests[0].after == OutboxTerminalCursor(event_sequence=0)`，`limit == 50` ✅

### 参数校验路径

- 空白 prompt → argparse `_non_empty_prompt` 抛出 `ArgumentTypeError` → exit 2 ✅
- 空白 label → `prompt_slot_key(" ")` → `_require_non_empty_text` 抛出 `ValueError` → `_ensure_prompt_session` 捕获 → `CliCommandUsageError` → exit 2 ✅
- config 逃逸 workspace → `_resolve_explicit_config_dir` 检测 `relative_to` 失败 → `CliCommandUsageError` → exit 2 ✅
- config 不是目录 → `_resolve_explicit_config_dir` 检测 `is_dir()` 失败 → `CliCommandUsageError` → exit 2 ✅
- 缺 required context slot → `ScenePrepareError("fins_default_subject")` → `test_prompt_runtime_rejects_missing_required_context_slot` 断言 ✅

## Adversarial Failure Pass

以下场景经过逐项排查，已确认有合理处理或已记录为 residual risk：

1. **空 prompt 文本** — `_non_empty_prompt` type validator → argparse exit 2 ✅
2. **缺必填 context slot** — `ScenePrepareError` → fail closed ✅
3. **submit_followup 返回前 SIGINT** — 本地 None → exit 130，不发 cancel ✅
4. **submit_followup 返回后、wait_terminal 开始前 SIGINT** — `on_run_accepted` 已同步设置 run_id → 走 cancel 路径 ✅
5. **cancel_run 时 Run 已终态** — `cancel_entrypoint_run_and_wait` 先 `get_run`，已终态时走 outbox fallback ✅
6. **cancel_run 失败（非终态）** — 再次 `get_run`，仍非终态则 re-raise `HostApiError` ✅
7. **重复 SIGINT** — 同一 `client_request_id` 复用，Host 端幂等吸收 ✅
8. **watcher drain 失败** — `_WatcherFailure` 记录到 queue，terminal observation 携带 `watcher_failure_message` 诊断字段 ✅
9. **outbox projection FAILED** — `EntrypointRuntimeError` → CLI exit 1 ✅
10. **outbox projection CAUGHT_UP 但无匹配 terminal** — `EntrypointRuntimeError`（contract violation） → CLI exit 1 ✅
11. **outbox projection LAGGED** — `_read_outbox_terminal` 返回 None → 继续 poll 循环 ✅
12. **SUCCEEDED 终态但 final_answer=None** — `render_prompt_terminal_result` 输出 fallback 消息到 stderr → exit 1 ✅
13. **Host 异常退出** — `async with open_host(...)` 确保 cleanup ✅
14. **环境不支持 signal handler** — 降级为 KeyboardInterrupt（Finding 2）⚠️ 低影响
15. **ServiceRunOverrides 构造时 ValueError** — 捕获为 `CliCommandUsageError` → exit 2 ✅

## Open Questions

无。当前实现语义与 accepted plan 一致，无需要进一步澄清的设计或契约歧义。

## Residual Risk

| 风险 | 影响 | 处置 |
|------|------|------|
| CANCELLED/LOST 输出路径无直接测试 | 低 — 渲染函数为简单 switch + print，回归风险极小 | 已在 Finding 1 记录 |
| 不支持 `add_signal_handler` 的事件循环环境（Windows ProactorEventLoop）下降级为 KeyboardInterrupt，Run accepted 后 SIGINT 不走 typed cancel | 低 — 非当前部署目标 | 已在 Finding 2 记录 |
| OS-level SIGINT 未测试（使用注入 monitor 而非真实 OS signal） | 低 — monitor 行为等价于 OS signal handler 的 Event 设置语义；`add_signal_handler` 的 OS 集成由 Python 标准库保证 | 可接受，后续 smoke 时可手动验证 |
| 真实 provider/LLM 执行未在 S3 中测试 | 按 S3 scope 预期 — 后续 smoke/集成测试覆盖 | 不阻塞 |
