# WU-CLI-01 CLI-01-S4 Implementation Report

## Gate

- Work unit: WU-CLI-01
- Slice: CLI-01-S4, Interactive command using the same Service session semantics
- Gate: implementation
- Agent: Codex
- Date: 2026-06-14
- Status: implemented, not committed

## Scope Judgment

本 slice 的动机成立：`interactive` 已在 parser 中暴露，但此前仍由占位 runner 处理，无法通过 Service assembly 与 Host public API 完成多轮会话。按设计真源，CLI 只能作为 UI adapter；本实现没有迁移旧 `interactive_ui.py` 或旧 label registry，也没有直接构造 Engine request、访问 Host durable/internal 或读取 Fins storage。

## Changed Files

- `dayu/cli/commands/interactive.py`
  - 新增 `dayu-cli interactive` REPL。
  - 使用 `EntrypointRuntimeRequest(scene_id="interactive")` 准备 runtime。
  - 通过 `open_host(...)`、`ensure_or_create_entrypoint_session(...)`、`submit_entrypoint_turn_and_wait(...)`、`cancel_entrypoint_run_and_wait(...)` 完成 session、turn、terminal observation 与 cancel。
  - 支持 `--ticker` 填充 `fins_default_subject`，默认 `"未指定具体公司"`；`base_user` 固定 `"本地 CLI 用户"`。
  - `--label` 使用 `cli.interactive.<label>` slot；无 label 时创建当前进程 session；`--new-session` 调 `create_session(bind_slot=True)`。
  - 每轮生成新的 `HostCallContext.request_id` 与 submit `client_request_id`；同一轮 cancel 使用稳定 `run_id` 相关 `client_request_id`。
  - 终端 UI 只展示提示、final answer、错误与取消状态。
  - Controller pre-review blocker fix: `_wait_for_run_id_or_local_exit(...)` 改为返回 typed outcome；等待 run id 阶段若 `submit_task` 先完成，会 `await submit_task` 返回 terminal 或透传异常，不再把 Host/API fatal 或已完成 terminal 误映射为本地 130。
  - S4 review low-fix: 运行态 SIGINT 收口改为统一 task cleanup helper，移除 `sigint_task` / `second_sigint_task` 分支与 `finally` 的重复 cancel / await，语义保持不变。
- `dayu/cli/host_context.py`
  - 新增 interactive 的 scenario、scope、slot key、Host context、create / submit / cancel client request id helper。
  - 抽出通用 `_build_host_context(...)`，保留 prompt 既有语义。
- `dayu/cli/output.py`
  - 新增 `render_interactive_terminal_result(...)`：`SUCCEEDED` 输出答案继续，`FAILED` / `CANCELLED` 输出状态继续，`LOST` 返回 fatal 失败。
- `dayu/cli/arg_parsing.py`
  - 为 `ParsedCliArgs` 补齐 `new_session: bool` 类型字段。
- `dayu/cli/main.py`
  - 注册 interactive runner。
  - 更新模块 docstring，移除 S1 过时描述，明确 main 只做 parser、dispatch 和顶层退出码映射，具体业务由命令模块经 Service 边界执行。
- `tests/cli/test_interactive_command.py`
  - 覆盖 label/new-session binding、默认 context slot、两轮同 session、每轮 watcher attach/close、fast terminal、FAILED/CANCELLED/LOST 策略、运行态 SIGINT cancel、第二次 SIGINT 本地 130、unsupported flags 与显式 config 错误。
  - 覆盖等待 run id 阶段 `submit_task` 先返回 SUCCEEDED terminal 与先抛 RuntimeError/Host-style fatal 的路径，防止回归为本地 130。
  - S4 review low-fix: 补充输入态 Ctrl-C 测试，固定为退出当前 command 返回 130，且不发 submit / cancel。
- `tests/service/test_entrypoint_runtime_interactive_path.py`
  - 覆盖真实 `interactive.json` required slots 与连续两轮独立 terminal wait state。

## Allowed Files Deviations

- `dayu/cli/main.py`
  - 理由：不注册 `COMMAND_INTERACTIVE` runner 时，`dayu-cli interactive` 仍会进入 S1 占位 runner，S4 无法形成可执行闭环。
- `tests/cli/test_arg_parsing.py`
  - 理由：interactive runner 注册后，原“interactive 仍为占位 runner”的 S1 测试事实失效；测试目标改为仍未实施的 `download`。
- `tests/README.md`
  - 理由：AGENTS.md 触发规则要求修改 `tests/` 后检查并按需更新。该 README 明确要求测试事实变化时同步；本轮新增 interactive CLI / Service path 覆盖，属于需要更新的测试事实。

## Validation

- Coverage / affected CLI tests:

```bash
source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py --cov=dayu.cli.commands.interactive --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov=dayu.cli.main --cov-report=term-missing -q
```

Result: 64 passed. 单文件覆盖率：`interactive.py` 88%，`host_context.py` 99%，`output.py` 83%，`arg_parsing.py` 100%，`main.py` 94%。

- Regression / S2-S3 affected tests:

```bash
source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_host_assembly.py -q
```

Result: 82 passed.

- Type check:

```bash
source .venv/bin/activate && pyright
```

Result: 0 errors, 0 warnings.

- Whitespace check:

```bash
git diff --check
```

Result: passed.

上述 pytest 命令均出现 edgar 依赖 deprecation warnings；不是本 slice 引入的失败。

## README Decision

已读取 `tests/README.md` 顶部职责约束。由于本轮新增 `tests/cli/test_interactive_command.py` 与 `tests/service/test_entrypoint_runtime_interactive_path.py`，并改变 `tests/cli/test_arg_parsing.py` 的占位 runner 事实，已更新 `tests/README.md` 中 CLI 与 Service 测试覆盖说明。

未更新其它 README：本轮未修改 `dayu/engine/`、`dayu/host/`、`dayu/fins/`、`dayu/config/`，也未改变项目分层关系或装配边界；`dayu/cli/` 当前没有 AGENTS.md 中列出的 README 触发项。

## Self Review

- 未发现 Engine 直接导入或 `AgentRunRequest` 构造路径。
- 未发现 Host durable/internal 访问路径；Host 操作通过 Service helper 与 Host public DTO。
- 未发现 Fins storage 直接读取路径。
- 未迁移旧 `interactive_ui.py` 或旧 label registry。
- 终端策略与 S4 要求一致：`SUCCEEDED` / `FAILED` / `CANCELLED` 回到输入态，`LOST` 与 Service fatal error 退出 1。
- Controller pre-review blocker 已修复：等待 run id 阶段 submit 先完成不再被压缩为 `None`；terminal 原样返回，异常向上透传。
- S4 review low findings 已修复：输入态 Ctrl-C 已固定为本地 130 且不发 submit / cancel；运行态 SIGINT task cleanup 已集中处理，避免重复 cancel / await 代码异味。

## Residual Risks

- Fixed in current slice: interactive command 从占位 runner 迁移为 Service/Host public path；session binding、两轮会话、terminal wait、SIGINT cancel、真实 `interactive.json` slots 已覆盖。
- Covered by later approved slice: Fins direct command runner 仍为 not-implemented，由 CLI-01-S5 / S6 处理。
- Deferred with owner: 旧 CLI debug / trace / thinking / duplicate-governance 等无 Host public per-run typed contract 的 flags 继续 fail fast，沿用 WU-CLI-01-RR-03 / RR-05 的后续 owner 裁决。

## Completion

S4 implementation gate 代码与测试已完成，未 commit、未 push、未开 PR。
