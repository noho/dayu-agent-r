# WU-CLI-01 / CLI-01-S3 Implementation Report

## Gate

- Work unit: `WU-CLI-01`
- Slice: `CLI-01-S3`
- Scope: Prompt command through Service assembly and Host public API
- Agent: Codex
- Status: implemented locally; no commit, no push, no PR

## First-Principles Judgment

S3 的动机成立。当前 CLI skeleton 只提供 parser / placeholder，`prompt` 还不能通过 `ConfigLoader -> ScenePrepare -> ToolsDiscovery -> Service assembly -> Host public API` 完成 one-shot Run。若在 CLI 内直接拼 Engine request 或读取 Host durable state，会破坏 `UI -> Service -> Host -> Engine` 分层；本实现只把 CLI 参数转换为 Service / Host public typed inputs，并复用 S2 的 entrypoint runtime helper。

## Changed Files

- `dayu/cli/commands/prompt.py`
  - 新增 `dayu-cli prompt` runner。
  - positional prompt 作为本轮 user prompt，空白 prompt 由 argparse 返回 2。
  - `--ticker` 映射到 `fins_default_subject`；未传时使用 `未指定具体公司`。
  - `base_user` 固定为 `本地 CLI 用户`。
  - `--label` 映射为 stable Host slot key `cli.prompt.<label>`，未使用旧 label registry。
  - `--model-name` 映射为 `ServiceAssemblyOverrides.model_id`。
  - 可映射执行项映射为 `ServiceRunOverrides`；unsupported 旧执行项 fail fast，exit 2。
  - 输出 final answer；FAILED / LOST 输出 Host terminal error message 并 exit 1；CANCELLED exit 130。
  - 运行中 SIGINT：Run accepted 前本地 exit 130；Run accepted 后构造 `EntrypointCancelRequest` / `CancelRunRequest(context, client_request_id, reason="cli_sigint", mode=CancelMode.GRACEFUL)`，等待 terminal，exit 130；重复 SIGINT 不产生第二个 cancel request。
- `dayu/cli/host_context.py`
  - 新增 CLI-local `HostCallContext`、operation context、slot key、submit/create/cancel `client_request_id` 构造 helper。
- `dayu/cli/output.py`
  - 新增 prompt terminal result 与 CLI error 输出 helper。
- `dayu/cli/arg_parsing.py`
  - 为 `ParsedCliArgs` 补充 prompt runner 读取的 typed 字段。
  - positional prompt 增加非空校验。
- `dayu/cli/main.py`
  - 注册 `prompt` runner，其它命令保持 placeholder。
- `dayu/service/entrypoint_runtime.py`
  - `submit_entrypoint_turn_and_wait(...)` 增加可选 `on_run_accepted` callback，用于 UI adapter 在 terminal wait 期间拿到 `accepted_run_id` 并发起 typed cancel。
- `tests/cli/test_prompt_command.py`
  - 覆盖参数转换、slot key、unsupported flags、fast terminal、outbox fallback、FAILED 输出、SIGINT before / after accepted、cancel request 字段与 repeated SIGINT 不重复 cancel。
- `tests/service/test_entrypoint_runtime_prompt_path.py`
  - 使用真实 `prompt.json` 验证 required context slots、默认工具选择和 accepted-run callback。
- `tests/cli/test_arg_parsing.py`
  - 将 placeholder runner 断言改为仍未实现的 `interactive`。
- `tests/README.md`
  - 更新 CLI 测试当前事实。
- `dayu/service/README.md`
  - 补充 entrypoint runtime accepted-run callback 的当前边界事实。

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_arg_parsing.py tests/service/test_entrypoint_runtime.py -q`
  - Result: `62 passed`, 3 条 edgar deprecation warnings。
- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_arg_parsing.py --cov=dayu.cli.commands.prompt --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov-report=term-missing -q`
  - Result: `41 passed`, 3 条 edgar deprecation warnings。
  - File coverage: `arg_parsing.py 100%`, `prompt.py 91%`, `host_context.py 98%`, `output.py 80%`。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`。
- `git diff --check`
  - Result: clean。

## README Decision

- `tests/README.md`: updated. Tests changed from parser / placeholder-only CLI coverage to include prompt adapter behavior through Service helper and mocked Host public API.
- `dayu/service/README.md`: updated. `entrypoint_runtime.submit_entrypoint_turn_and_wait(...)` now has caller-visible accepted-run callback semantics needed for prompt SIGINT cancel.
- `dayu/README.md`: checked. No update needed because the existing cross-layer summary already describes UI through Service assembly, Host public API, terminal observation and cancel helper at the right abstraction level.
- `dayu/host/README.md`, `dayu/engine/README.md`, `dayu/fins/README.md`, `dayu/config/README.md`: not triggered; S3 did not modify those packages or their public boundaries.

## Residual Risks / Uncovered Areas

- Real provider execution is not run in this slice. Tests use real ConfigLoader / ScenePrepare / ToolsDiscovery / Service assembly and a mocked Host public handle, matching S3 scope.
- The explicit SIGINT handler path is covered via injected monitor tests, not by sending an OS-level signal to the process.
- S4 interactive and S5-S7 Fins/init remain intentionally unimplemented.
