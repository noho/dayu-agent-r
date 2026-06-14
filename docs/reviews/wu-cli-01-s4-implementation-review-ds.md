# Code Review

## Scope

- Mode: current changes (S4 uncommitted workspace changes relative to HEAD)
- Branch: `phase/host-ui-implementation`
- Review target: WU-CLI-01 / CLI-01-S4 interactive implementation
- Output file: `docs/reviews/wu-cli-01-s4-implementation-review-ds.md`
- Timestamp: 2026-06-14 16:11 CST
- Base: `main` (via committed S1–S3; S4 changes are unstaged workspace)
- Included scope:
  - `dayu/cli/commands/interactive.py` (new, 885 lines)
  - `dayu/cli/host_context.py` (modified, +interactive helpers)
  - `dayu/cli/output.py` (modified, +`render_interactive_terminal_result`)
  - `dayu/cli/arg_parsing.py` (modified, +`new_session` field on `ParsedCliArgs`)
  - `dayu/cli/main.py` (modified, registered interactive runner)
  - `tests/cli/test_interactive_command.py` (new, 19 tests)
  - `tests/service/test_entrypoint_runtime_interactive_path.py` (new, 3 tests)
  - `tests/README.md` (modified, updated coverage description)
  - `tests/cli/test_arg_parsing.py` (modified, changed placeholder test to `download`)
- Excluded scope: S1–S3 committed changes, S5–S7 not yet implemented, Fins commands
- Adjudication criterion: 本轮是迁移旧 dayu-agent interactive 的业务逻辑 / 用户可见语义，并适配新的 Host public contracts/API；不是迁移旧代码实现，不要以旧 interactive_ui.py 或旧 label registry 一致性作为正确性。

## Findings

### 1. 未修复-低-输入态 Ctrl-C 退出行为无明确测试覆盖

- **入口/函数**: `_run_interactive_repl` → `_read_user_input` → `run_interactive_command`
- **文件(行号)**: `dayu/cli/commands/interactive.py:409` 和 `dayu/cli/commands/interactive.py:251`
- **输入场景**: interactive 输入态（REPL 等待 `input()` 时）用户按下 Ctrl-C
- **实际分支**: `input()` 在输入态抛出 `KeyboardInterrupt`，穿透 `except EOFError`（line 410），向上传播经 `_run_interactive_repl` → `_run_interactive_command_async` → `run_interactive_command` 的 `except KeyboardInterrupt`（line 251）
- **预期行为**: Plan 要求"输入态 Ctrl-C：清空当前输入或退出当前 command，按实现测试固定"
- **实际行为**: 退出整个 interactive session，返回 130
- **直接证据**: `_read_user_input`（line 859–868）调用裸 `input(prompt)`，未捕获 `KeyboardInterrupt`；`run_interactive_command` line 251-252 捕获并返回 `EXIT_KEYBOARD_INTERRUPT (130)`。测试文件中无 `test_interactive_input_ctrl_c_exits_130` 或等价测试。
- **影响**: Plan 允许两种行为（清空/退出），当前实现选择"退出"是有效选择。无测试覆盖意味着后续改动可能无意中改变此行为。
- **建议改法和验证点**: 补一个测试：在 `_InputReader` 中让第二次 `__call__` 抛出 `KeyboardInterrupt`，通过 `capsys` / exit code 断言行为固定为 130 退出。
- **修复风险（低）**: 仅新增测试，不改生产代码。
- **严重程度（低）**:

### 2. 未修复-低-sigint_task 双重取消属代码异味

- **入口/函数**: `_submit_interactive_turn_handling_sigint` → `_finish_completed_submit_task` + finally block
- **文件(行号)**: `dayu/cli/commands/interactive.py:526` 和 `dayu/cli/commands/interactive.py:508`
- **输入场景**: submit_task 先于 sigint_task 完成（正常 fast terminal 路径）
- **实际分支**: `_finish_completed_submit_task`（line 526）执行 `sigint_task.cancel()` 并 await；然后 finally block（line 508–510）再次执行 `sigint_task.cancel()` 和 suppress-await
- **预期行为**: 只取消一次 sigint_task
- **实际行为**: 取消两次；`asyncio.Task.cancel()` 对已完成/已取消 task 是 no-op，所以行为正确但冗余
- **直接证据**: line 526: `sigint_task.cancel()`；line 508: `sigint_task.cancel()`（finally block 无条件执行）。同模式也出现在 `_wait_for_run_id_or_local_exit` 的 finally block（line 621–626）与分支内显式 cancel。
- **影响**: 无功能影响，但增加阅读负担——读者需确认双重取消在 asyncio 中的安全性。
- **建议改法和验证点**: 将 finally block 的 cancel 改为条件检查（如 `if not sigint_task.done(): sigint_task.cancel()`），或把显式 cancel 移出 then 分支，依赖 finally 统一清理。若保持现状，加一行注释说明 `cancel()` 对 completed/cancelled task 是 no-op。
- **修复风险（低）**: 纯清理性改动，asyncio task 生命周期不变。
- **严重程度（低）**:

## Open Questions

1. 输入态 Ctrl-C 行为是否需要做"清空当前输入行而不退出 session"？Plan 只说"按实现测试固定"，当前固定为退出 130。若未来 WeChat / GUI adapter 期望输入态取消不发 connect close，需改为更温和的处理。当前对 CLI 纯文本 REPL 可接受。

## Residual Risk

- **输入态 SIGINT 路径漏测**：Finding 1 已记录。无回归风险——行为由 `input()` 的 Python 默认信号语义直接决定，不受 interactive 内部状态机影响。
- **`_InteractiveSigintMonitor.install()` 在不支持 `add_signal_handler` 的平台上的行为**：当前实现 catch `NotImplementedError` / `RuntimeError` 后设 `_installed=False`，保持 `KeyboardInterrupt` 默认路径。在 Windows 上 `add_signal_handler` 不支持 SIGINT 会走此路径。此路径在测试中通过平台 skip 未覆盖。行为等价于无 monitor 安装（即所有 Ctrl-C 退化为 `KeyboardInterrupt` → exit 130），对 CLI REPL 用户体验降级但无数据一致性风险。
- **已提交 S1–S3 文件修改为 S4 interactive 新增常量/helper 的反向影响**：`host_context.py` 的 `_build_host_context` 重构保持 prompt 的原有语义（通过 `operation_kind` 参数化），且 prompt 既有测试全部通过（82 passed regression）。风险低。
- **`_optional_stripped_text` 在 `host_context.py`（line 319）和 `interactive.py`（line 830）中的重复模式**：两处均为 `_`-前缀模块私有函数，语义相同但各自独立。非兼容性 wrapper，不违反 AGENTS.md。未来若需要共享，可提升至 `dayu.runtime` 或 `dayu.cli` 公共 helper，但当前重复规模小（各 ~10 行）。
- **Coverage gaps**：`interactive.py` 覆盖率达 88%，未覆盖行主要为异常 fallback（`RuntimeError`、`KeyboardInterrupt`、`CliInteractiveUsageError`、路径校验失败分支）。已超过 80% 阈值。

## Verification Commands Executed

| # | Command | Result |
|---|---------|--------|
| 1 | `pytest tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py -q` | 84 passed |
| 2 | `pyright` | 0 errors, 0 warnings |
| 3 | `pytest tests/cli/test_interactive_command.py --cov=dayu.cli.commands.interactive --cov-report=term-missing -q` | 88% coverage |
| 4 | `grep -rn 'from dayu.engine\|import dayu.engine\|dayu.fins.storage' dayu/cli/commands/interactive.py` | No hits |
| 5 | `grep -rn 'HasAttr\|getattr\|: Any\b\|: object\b' dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py` | No hits |
| 6 | `grep -rn 'compat\|legacy\|old_\|_old' dayu/cli/commands/interactive.py dayu/cli/host_context.py dayu/cli/output.py` | No hits |
| 7 | Regression: `pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_host_assembly.py -q` | 82 passed |

## Adjudication Verdict per Review Criteria

### 1. Architecture boundary (Pass)

interactive 只通过以下路径触达 Host：

- `EntrypointRuntimeRequest(scene_id="interactive")` → `prepare_entrypoint_runtime()` (Service)
- `open_host(...)` (Host public)
- `ensure_or_create_entrypoint_session(...)` (Service helper → `Host.create_session` / `Host.ensure_session`)
- `submit_entrypoint_turn_and_wait(...)` (Service helper → `Host.watch_session_events` / `Host.submit_followup` / `Host.get_run` / `Host.read_outbox_terminal_items`)
- `cancel_entrypoint_run_and_wait(...)` (Service helper → `Host.get_run` / `Host.cancel_run` / `Host.read_outbox_terminal_items`)

无直接 `dayu.engine` import、无 `AgentRunRequest` 构造、无 Host durable/internal 访问、无 `dayu.fins.storage` 读取。✓

### 2. CLI / Service boundary (Pass)

CLI 层（`interactive.py`）只做：REPL 输入、signal handler 安装/卸载、stdout/stderr 输出、exit code 映射、HostCallContext / client_request_id 构造。

Service 层（`entrypoint_runtime.py`）提供可被 WeChat/GUI 复用的 `prepare_entrypoint_runtime`、`ensure_or_create_entrypoint_session`、`submit_entrypoint_turn_and_wait`、`cancel_entrypoint_run_and_wait`。Service helper 不 import CLI 模块、不读写 stdout/stderr、不装 signal handler。✓

### 3. Flag mapping (Pass)

| Flag | Mapping | Status |
|------|---------|--------|
| `--label` | `cli.interactive.<label>` → `ensure_session(scope="cli.interactive", slot_key=...)` | ✓ |
| `--new-session` | `create_session(bind_slot=True)` with process-local slot key | ✓ |
| `--ticker` | `context_slot_values["fins_default_subject"]`, default `"未指定具体公司"` | ✓ |
| `--model-name` | `ServiceAssemblyOverrides.model_id` | ✓ |
| `--temperature` / `--max-iterations` / etc. | `ServiceRunOverrides` | ✓ |
| `--thinking`, `--debug-sse`, `--enable-tool-trace`, etc. 12 unsupported flags | `CliInteractiveUsageError` → exit 2 | ✓ |

### 4. Multi-turn state machine (Pass)

两轮同 session、每轮独立 `HostCallContext.request_id`、每轮独立 `client_request_id`（含 `turn-{n}` 递增）。每轮通过 `submit_entrypoint_turn_and_wait` 内部 attach/close watcher，不跨轮复用 wait state。测试 `test_interactive_two_turns_use_same_session_and_independent_watchers` 和 `test_interactive_two_turns_have_independent_terminal_wait_state` 验证。✓

### 5. SIGINT cancel semantics (Pass)

- 运行态第一次 Ctrl-C：经 `_InteractiveSigintMonitor` notify → `_cancel_interactive_turn_after_first_sigint`，构造完整 `EntrypointCancelRequest` → `Host.cancel_run(run_id, CancelRunRequest(context=..., client_request_id=..., reason="cli_sigint", mode=CancelMode.GRACEFUL))`
- 运行态第二次 Ctrl-C：本地返回 `None` → `_run_interactive_repl` 返回 130
- 同轮 cancel `client_request_id` 包含 `turn-{n}:run-{run_id}:cancel:cli_sigint`，稳定复用
- 等待 run id 阶段若 `submit_task` 先完成/失败：通过 typed outcome (`_SubmitCompletedWhileWaitingForRunId` / 异常透明传) 正确处理，不误映射为 130。测试 `test_wait_for_run_id_returns_submit_terminal_when_submit_completes_first`、`test_wait_for_run_id_propagates_submit_failure_when_submit_fails_first` 验证。✓

### 6. Terminal policy (Pass)

| Terminal status | Behavior | Verified by |
|----------------|----------|-------------|
| `SUCCEEDED` | 输出 final answer → 回到输入态 | `test_interactive_two_turns_use_same_session_and_independent_watchers` |
| `FAILED` | 输出 error_message → 回到输入态 | `test_interactive_failed_and_cancelled_continue_until_eof` |
| `CANCELLED` | 输出 cancel_reason → 回到输入态 | `test_interactive_failed_and_cancelled_continue_until_eof` |
| `LOST` | 输出 lost 诊断 → exit 1 | `test_interactive_lost_is_fatal` |
| Service fatal / Host handle closed / outbox projection FAILED | exit 1 | 经 Service 层 `EntrypointRuntimeError` 传播 |

SUCCEEDED + final_answer is None 被作为防御性 fatal 处理（exit 1），符合 Host contract violation 应 fail closed 原则。✓

### 7. Code quality (Pass)

- 中文 docstring：所有函数/类均有完整中文 docstring，含参数、返回值、异常说明 ✓
- 无 `Any`/`object`/`hasattr`/`getattr` 逃逸：静态搜索确认 ✓
- 无兼容性 wrapper：无 compat/legacy 引用 ✓
- 无魔法字符串：operation names 等常量均以 `_INTERACTIVE_OPERATION_*` Final 变量声明 ✓
- pyright：0 errors, 0 warnings ✓
- 覆盖率：`interactive.py` 88% (≥ 80%) ✓
- README：按 AGENTS.md 触发规则更新了 `tests/README.md` ✓

## Conclusion

未发现实质性 blocker。实现严格遵循 S4 plan 的所有 contract 要求：架构边界清晰、CLI/Service 分离正确、SIGINT 语义完整（含等待 run id 期间 submit 先完成的 typed outcome 竞争处理）、terminal policy 准确、测试覆盖充分（22 个 S4 专属测试 + 82 个回归测试通过）、pyright 零报错。两个 low-severity finding 均为可后续清理项，不阻塞 merge。
