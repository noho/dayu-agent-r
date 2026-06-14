# WU-CLI-01 / CLI-01-S3 Implementation Review — AgentMiMo

## Gate

- Review agent: AgentMiMo
- Review target: CLI-01-S3 prompt implementation (uncommitted changes)
- Review scope: `dayu/cli/commands/prompt.py`, `dayu/cli/host_context.py`, `dayu/cli/output.py`, `dayu/cli/arg_parsing.py`, `dayu/cli/main.py`, `dayu/service/entrypoint_runtime.py`, `tests/cli/test_prompt_command.py`, `tests/service/test_entrypoint_runtime_prompt_path.py`, `tests/cli/test_arg_parsing.py`, `docs/host/ui-implementation-control.md`, `dayu/service/README.md`, `tests/README.md`
- Design source: `docs/host/wu-cli-01-cli-entrypoint-plan.md` (accepted plan)
- Implementation report: `docs/reviews/wu-cli-01-s3-implementation-codex.md`
- 总控复核声明：S3 目标是迁移旧 prompt 的用户可见业务语义并适配 Host public contracts/API，不是迁移旧代码实现。

## 裁决标准回顾

本轮审查按照用户指定的六项标准执行：

1. prompt 是否只通过 ConfigLoader -> ScenePrepare -> ToolsDiscovery -> Service assembly -> Host public API。
2. CLI / Service 边界是否清晰。
3. `--ticker` / `--label` / `--model-name` / execution overrides / unsupported legacy flags 的映射是否符合 accepted plan。
4. SIGINT cancel 语义。
5. S2 新增 `on_run_accepted` hook 是否破坏 watcher attach-before-submit、terminal observation、caller-owned timeout contract。
6. tests/README/pyright/AGENTS 约束。

## 审查结果：Pass

六项标准全部通过，无 blocker 或 severity warning。

---

## 逐项审查详情

### 1. prompt 是否只通过 ConfigLoader -> ScenePrepare -> ToolsDiscovery -> Service assembly -> Host public API

**结论：Pass。**

- `prompt.py:231-246`：`prepare_entrypoint_runtime(EntrypointRuntimeRequest(...))` 完成 ConfigLoader -> ScenePrepare -> ToolsDiscovery -> Service assembly 全链路。CLI 只传 `workspace_root`、`package_config_root`、`explicit_config_dir`、`scene_id`、`context_slot_values`、`assembly_overrides`、`env`；不直接构造 `AgentRunRequest`，不读取 Host durable internals，不访问 Fins storage。
- `prompt.py:247`：`open_host(runtime.host_assembly.options)` 使用 Service assembly 输出的 `OpenHostOptions`，不自行拼装 Host opener 参数。
- `prompt.py:344-363`：`submit_entrypoint_turn_and_wait(...)` 通过 Service helper 提交，使用 `EntrypointTurnRequest` typed DTO，不直接构造 `SubmitFollowupRequest`。
- `prompt.py:381-397`：SIGINT cancel 路径使用 `cancel_entrypoint_run_and_wait(...)` + `EntrypointCancelRequest` typed DTO，不直接调用 `host.cancel_run()`。
- `host_context.py` 全文：只构造 `HostCallContext` / `OperationContext` DTO 和 CLI-local 幂等 id，不调用 Host 方法。

**证据**：`prompt.py` 无 `from dayu.engine import ...`、无 `from dayu.host.durable_... import ...`、无 `from dayu.fins.storage import ...`。

### 2. CLI / Service 边界是否清晰

**结论：Pass。**

- CLI 模块（`prompt.py`、`output.py`、`host_context.py`、`arg_parsing.py`、`main.py`）的职责：
  - `arg_parsing.py`：参数定义、解析、类型校验。
  - `prompt.py`：CLI 参数到 Service/Host public DTO 转换、SIGINT handler 安装/移除、`asyncio.run` 同步桥接、exit code 映射。
  - `host_context.py`：CLI-local `HostCallContext`、幂等 id 构造。
  - `output.py`：终端文本输出、exit code 映射。
  - `main.py`：命令注册与分发。
- Service 模块（`entrypoint_runtime.py`）的职责：
  - runtime assembly 编排。
  - Session ensure/create、submit、cancel、terminal observation。
  - 不解析 CLI 参数、不安装 signal handler、不写 stdout/stderr。
- 验证：未来 WeChat/GUI adapter 可复用 `prepare_entrypoint_runtime`、`ensure_or_create_entrypoint_session`、`submit_entrypoint_turn_and_wait`、`cancel_entrypoint_run_and_wait`，只需替换 `open_host` call 与输出渲染。

### 3. 参数映射是否符合 accepted plan

**结论：Pass。**

| 参数 | 映射 | 符合 plan |
|---|---|---|
| positional `prompt` | `EntrypointTurnRequest.user_prompt`，空白由 `_non_empty_prompt` 校验返回 exit 2 | ✓ |
| `--ticker` | `context_slot_values["fins_default_subject"]`；未传时 `DEFAULT_FINS_SUBJECT = "未指定具体公司"` | ✓ |
| `--label` | `prompt_slot_key(label)` -> `cli.prompt.<label>` Host slot key；未传时 `create_session(bind_slot=False)` | ✓ |
| `--model-name` | `ServiceAssemblyOverrides.model_id` | ✓ |
| `--temperature`, `--tool-timeout-seconds`, `--max-iterations`, `--fallback-mode`, `--fallback-prompt`, `--max-consecutive-failed-tool-batches` | `ServiceRunOverrides` 对应字段 | ✓ |
| unsupported flags (`--thinking`, `--web-provider`, `--debug-sse`, `--debug-tool-delta`, `--debug-sse-sample-rate`, `--debug-sse-throttle-sec`, `--enable-tool-trace`, `--tool-trace-dir`, `--max-duplicate-tool-calls`, `--duplicate-tool-hint-prompt`, `--doc-limits-json`, `--fins-limits-json`) | `_raise_for_unsupported_execution_options` 统一 fail fast，exit 2 | ✓ |

### 4. SIGINT cancel 语义

**结论：Pass。**

- **Run accepted 前 SIGINT**：`_submit_prompt_turn_handling_sigint` 中 `sigint_task` 先于 `submit_task` 完成 → `submit_task.cancel()` → `accepted_run.run_id is None` → return `None` → `run_prompt_command` 返回 `EXIT_KEYBOARD_INTERRUPT` (130)。不发 Host cancel request。测试 `test_prompt_sigint_before_run_id_returns_local_interrupt` 覆盖。
- **Run accepted 后 SIGINT**：`submit_task` 先完成（`on_run_accepted` 已记录 `run_id`）→ SIGINT 触发 `sigint_task` 完成 → `submit_task.cancel()` → `accepted_run.run_id is not None` → 构造 `EntrypointCancelRequest(context, run_id, client_request_id, reason="cli_sigint", mode=CancelMode.GRACEFUL)` → `cancel_entrypoint_run_and_wait(...)` → 等待同一 Run terminal。测试 `test_prompt_sigint_after_run_id_cancels_host_run` 覆盖。
- **幂等 id 复用**：`prompt_cancel_client_request_id(invocation, turn_index, run_id)` 基于 `invocation_id + turn_index + run_id + reason` 构造，同一 Run 重复 cancel 复用同一 id。测试断言 `cancel_request.client_request_id.endswith(":turn-1:run-run-1:cancel:cli_sigint")`。
- **重复 SIGINT 不重复 cancel**：第一次 SIGINT 后 `sigint_task` 被 cancel，`_submit_prompt_turn_handling_sigint` 已进入 cancel 路径。第二次 SIGINT 由 `loop.add_signal_handler` 捕获（handler 仍 active），但 `sigint_task` 已不存在 → `KeyboardInterrupt` 在下个 `await` 点抛出 → `run_prompt_command` 外层 `except KeyboardInterrupt` 返回 130。不产生第二个 cancel request。
- **`_PromptSigintMonitor.install()` 使用 `loop.add_signal_handler`**：在 asyncio 事件循环中正确安装 signal handler，避免 `signal.signal()` 的 "signal only works in main thread" 限制。`close()` 在 finally 中恢复。

### 5. `on_run_accepted` hook 是否破坏 S2 contract

**结论：Pass。**

- `entrypoint_runtime.py:419-421`：`on_run_accepted` callback 在 `submit_followup` 返回后、`_wait_for_terminal` 开始前同步调用。
- **watcher attach-before-submit contract**：`submit_entrypoint_turn_and_wait` 内部在 `submit_followup` 前已调用 `_attach_watcher(host, request.session_id)`（line 402）。callback 不影响 watcher attach 顺序。
- **terminal observation contract**：callback 是纯同步通知（`Callable[[str], None]`），不修改 watcher、不修改 queue、不修改 terminal observation state。`_wait_for_terminal` 在 callback 之后立即启动。
- **caller-owned timeout contract**：callback 不引入内部 timeout，不阻塞，不持有异步资源。Service helper 仍不持有内部 timeout，调用方控制等待生命周期。
- **调用方使用方式**：`prompt.py:338` 中 `_AcceptedRunState.record` 作为 callback 传入，只做 `self.run_id = run_id` 赋值。SIGINT handler 通过 `accepted_run.run_id` 读取，正确实现了 UI adapter 在等待终态期间发起 typed cancel 的设计意图。
- 测试 `test_submit_entrypoint_turn_reports_accepted_run_id` 覆盖 callback 通知语义。

### 6. tests/README/pyright/AGENTS 约束

**结论：Pass（附观察项）。**

- **pyright**：`0 errors, 0 warnings, 0 informations`。
- **测试全部通过**：62 passed, 3 edgar deprecation warnings。
- **覆盖率**：总 95%。`arg_parsing.py` 100%，`prompt.py` 91%，`host_context.py` 98%，`output.py` 80%。所有文件 >= 80% 目标。
- **中文 docstring**：所有新增函数、类、模块均提供完整中文 docstring，包含参数、返回值、异常。
- **无 `object` / `Any` / `hasattr` / `getattr` 逃逸**：全部使用精确类型签名。
- **无兼容 wrapper / re-export**：无兼容性代码。
- **无魔法字符串**：`DEFAULT_FINS_SUBJECT`、`DEFAULT_BASE_USER`、`CONTEXT_SLOT_FINS_DEFAULT_SUBJECT`、`CONTEXT_SLOT_BASE_USER`、`PROMPT_TURN_INDEX`、`CLI_SIGINT_REASON` 等均提取为 `Final` 常量。`_PROMPT_OPERATION_CREATE_SESSION` 等操作短名也提取为常量。
- **README 更新**：`tests/README.md` 更新 CLI 测试当前事实；`dayu/service/README.md` 补充 accepted-run callback 边界事实。均符合触发规则。

## 观察项（非 blocker）

### O1. `output.py` 覆盖率 80% — 未覆盖 LOST / CANCELLED / missing-final-answer 分支

`output.py:45-46`（SUCCEEDED 但 `final_answer is None`）、`50-54`（CANCELLED）、`56-57`（LOST）三个分支未被测试直接覆盖。当前通过 `test_prompt_terminal_failed_outputs_error` 和 `test_prompt_command_outputs_fast_live_terminal_and_converts_requests` 覆盖了 SUCCEEDED 和 FAILED 路径。

**建议**：非 blocker，未来 slice 补充 `render_prompt_terminal_result` 的 CANCELLED、LOST、missing-final-answer 单元测试即可。

### O2. `host_context.py:230` 未覆盖 — `_require_positive_turn_index` 的 `ValueError` 分支

`_require_positive_turn_index(value < 1)` 未被测试直接命中。当前调用方 `prompt.py` 固定传 `PROMPT_TURN_INDEX = 1`。

**建议**：非 blocker，可由 `host_context.py` 的独立单元测试覆盖。

### O3. 第二次 SIGINT 行为：cancel wait 期间 SIGINT -> KeyboardInterrupt -> 130

当用户在 `cancel_entrypoint_run_and_wait` 等待 terminal 期间发送第二次 SIGINT 时，`_PromptSigintMonitor.notify()` 仍然 active（`install()` 在 `_submit_prompt_turn_handling_sigint` finally 中 `close()`），count 递增，但无 `sigint_task` 监听。最终 `KeyboardInterrupt` 在下个 `await` 点抛出，由 `run_prompt_command` 外层 `except KeyboardInterrupt` 返回 130。

这是 intentional behavior（用户二次 Ctrl-C = 立即退出），符合 accepted plan 的"重复 SIGINT 不重复 cancel"要求。但当前测试未显式覆盖此路径。

**建议**：非 blocker，可在后续 slice 中补充集成测试覆盖。

### O4. `prompt_slot_key` 中 `_require_non_empty_text` 已 strip，后续 `.strip()` 冗余

`host_context.py:86-87`：`_require_non_empty_text` 内部已调用 `.strip()` 并校验非空，`prompt_slot_key` 再调用一次 `.strip()` 是冗余操作。

**建议**：非 blocker，纯代码整洁问题。

### O5. `output.py` import 顺序

`output.py:9`：`import sys` 在 `from typing import TextIO` 之后，不符合 isort 标准库优先约定。

**建议**：非 blocker，纯代码风格。

---

## 实际检查的验证命令

1. `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_arg_parsing.py tests/service/test_entrypoint_runtime.py -q` — **62 passed, 3 warnings**
2. `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_arg_parsing.py --cov=dayu.cli.commands.prompt --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov-report=term-missing -q` — **41 passed, 总覆盖率 95%**
3. `source .venv/bin/activate && python -m pyright dayu/cli/commands/prompt.py dayu/cli/host_context.py dayu/cli/output.py dayu/cli/arg_parsing.py dayu/cli/main.py dayu/service/entrypoint_runtime.py` — **0 errors, 0 warnings, 0 informations**
4. `git diff --check` — **clean**
5. 手动代码审查：逐文件通读全部新增/修改文件，对照 accepted plan 六项标准。
