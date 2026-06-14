# WU-CLI-01 / CLI-01-S4 Implementation Re-Review Controller Adjudication

## 裁决

Pass。

S4 review gate 接受的两个 low findings 均已关闭；controller pre-review blocker 仍保持关闭，未发现 low-fix 引入新的架构、类型或测试问题。

## Re-Review 输入

- Updated implementation report: `docs/reviews/wu-cli-01-s4-implementation-codex.md`
- AgentMiMo re-review: `docs/reviews/wu-cli-01-s4-implementation-rereview-mimo.md`
- AgentDS re-review: `docs/reviews/wu-cli-01-s4-implementation-rereview-ds.md`

## Closed Findings

- S4-IMPL-F01：输入态 Ctrl-C 行为已由 `test_interactive_input_keyboard_interrupt_exits_without_run_requests` 固定为退出当前 command、返回 130，且不发 submit / cancel。
- S4-IMPL-F02：运行态 SIGINT task cleanup 已通过 `_cancel_and_await_task(...)` 集中处理，移除分支与 finally 重复 cancel / await 的代码异味，语义保持不变。
- Controller pre-review blocker：等待 run id 阶段 submit task 先完成时返回 terminal；submit task 先失败时透传异常；不再误映射为本地 130。

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_interactive_command.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py --cov=dayu.cli.commands.interactive --cov=dayu.cli.host_context --cov=dayu.cli.output --cov=dayu.cli.arg_parsing --cov=dayu.cli.main --cov-report=term-missing -q`：64 passed；`interactive.py` 88%，`host_context.py` 99%，`output.py` 83%，`arg_parsing.py` 100%，`main.py` 94%。
- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_host_assembly.py -q`：82 passed。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

## 下一步

接受 CLI-01-S4 implementation。进入 CLI-01-S5 implementation gate。
