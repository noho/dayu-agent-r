# WU-CLI-SMOKE-01 Runtime Display Controller Adjudication

## Scope

本 follow-up 收敛 `prompt` 与 `interactive` 的 `--detail` / `--thinking`
运行态清理逻辑，防止两个入口在 thinking guard、final 前清理、cancel
收口和二次中断提示上继续漂移。

## Implementation Summary

- 在 `dayu.cli.runtime_display` 中新增 `RuntimeActivityDisplay`、
  `RuntimeThinkingDisplay` 和 `RuntimeDisplayController`。
- `prompt` 与 `interactive` 复用 controller 管理：
  - activity-like 输出前先清 open thinking；
  - final answer 前先清 thinking，再清 activity / run view；
  - cancel 路径先 finish + close thinking；
  - 二次中断本地退出提示前清理 thinking；
  - display close lifecycle 幂等收口。
- `session resume` 现在注册并传递 `--detail` / `--no-detail`、
  `--thinking` / `--no-thinking` 到 prompt / interactive existing-session
  执行入口。
- 保留 prompt 与 interactive 的 session、REPL、startup reconnect、
  client request id、terminal result 渲染差异；未硬合并业务流程。

## Review Inputs

- Plan / boundary review: `docs/reviews/plan-review-20260708-145228.md`
- Implementation risk review: `docs/reviews/code-review-20260708-145545.md`
- AgentDS final re-review: all 5 actionable gaps closed, no residual blocker.
- AgentMiMo final re-review: no blocker; remaining notes are low关注 and accepted.

## Findings Adjudication

| Finding | 裁决 |
|---|---|
| duplicated prompt / interactive thinking cleanup | accepted-fixed |
| duplicated detail display parser registration | accepted-fixed |
| session resume accepted display flags but did not pass them onward | accepted-fixed |
| controller lifecycle lacked activity close symmetry | accepted-fixed |
| controller tests lacked None display scenarios | accepted-fixed |
| guard remained installed after thinking close | accepted-fixed |
| `InteractiveRunView.render_terminal_result()` still defensively calls `finish_runtime_display()` | accepted-as-idempotent; it is a low-risk defensive cleanup, with controller as the primary final-before-terminal cleanup path |

## Validation

- `pytest tests/cli/test_runtime_display.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_session_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_run_view.py tests/cli/test_thinking_renderer.py -q`
  - Result: `126 passed`, with existing third-party `edgar` deprecation warnings.
- `pytest tests/cli/test_runtime_display.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_run_view.py tests/cli/test_thinking_renderer.py --cov=dayu.cli.runtime_display --cov-report=term-missing -q`
  - Result: `32 passed`, `dayu/cli/runtime_display.py` coverage `96%`.
- `python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors`.
- `git diff --check`
  - Result: passed.

## Final Decision

Accepted. No required current fix remains.
