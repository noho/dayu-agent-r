# PR 141 fix gate - Codex

## Gate

- gate: PR review fix
- work unit: WU-CLI-01
- PR: https://github.com/noho/dayu-agent-r/pull/141
- scope: 只修复 controller accepted findings PR-RV-F01 与 PR-RV-F03
- stop condition: 完成本地修复、验证与本 artifact 后停止；不做 PR comment、merge、mark ready、push 或 re-review

## 目标与动机判断

PR-RV-F01 动机成立。`prompt` 与 `interactive` 同属 Agent entrypoint CLI adapter，重复实现 workspace root 解析、显式 config dir 解析、可选/必填文本校验、ServiceRunOverrides 映射、unsupported legacy option 检测和 SIGINT monitor 基础逻辑，会让后续 CLI/Host public contract 修正双写，违反项目“重复逻辑必须抽取”的约束。

PR-RV-F03 动机成立。`_normalize_system_exit_code` 没有 `ValueError` 抛出路径，原 docstring 的 `:raises ValueError:` 会误导调用方。

PR-RV-F02 已由 controller 裁决为 `deferred-with-owner`，本轮未处理。

## 修改内容

- 新增 `dayu/cli/agent_entrypoint.py`，在 CLI UI adapter 层内抽取 Agent entrypoint 共享 helper：
  - `CliSigintMonitor`
  - `resolve_workspace_root`
  - `resolve_explicit_config_dir`
  - `optional_stripped_text`
  - `require_cli_text`
  - `unsupported_execution_option_names`
  - `service_run_overrides_from_args`
  - `package_config_root`
- `dayu/cli/commands/prompt.py` 改为复用共享 helper，保留 prompt 自身 Session、submit、cancel 与 terminal observation 控制流。
- `dayu/cli/commands/interactive.py` 改为复用共享 helper，保留 interactive 自身 REPL、双 SIGINT、本地退出与 Host cancel 控制流。
- `dayu/cli/main.py` 修正 `_normalize_system_exit_code` docstring，不再声称可能抛出 `ValueError`。
- `tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py` 更新测试引用，直接覆盖共享 `CliSigintMonitor` 和 `package_config_root`。

## 未修改内容

- 未处理 PR-RV-F02。
- 未触碰 `dayu/cli/commands/fins.py` 或 init command；Fins direct 与 init 的既有 helper 未纳入本轮重构。
- 未修改 Service、runtime、Host、Engine、Fins storage 或 Host public API。
- 未改变 prompt / interactive 用户可见行为、exit code、cancel 语义或 unsupported flag fail-fast 行为。

## README 决策

本轮修改了 `tests/`，已检查 `tests/README.md`。该 README 只要求新增测试层级或测试职责变化时同步；本轮只是既有 CLI 测试跟随 helper 迁移，没有新增测试层级、运行方式或测试职责，因此不更新 README。

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q`
  - 结果：62 passed，3 个第三方 `edgar` deprecation warnings。
- `source .venv/bin/activate && pytest tests/cli -q`
  - 结果：94 passed，3 个第三方 `edgar` deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：0 errors, 0 warnings, 0 informations；pyright 提示有新版本可用。
- `git diff --check`
  - 结果：通过，无输出。

## 未覆盖项与 residual risks

- PR-RV-F02 保持 deferred-with-owner，归入既有 `WU-CLI-01-RR-06` 后续 signal / cancel adapter work。
- `WU-CLI-01-RR-01` 至 `WU-CLI-01-RR-10` 仍按 controller adjudication 保持已有 owner / destination。
- 本轮没有执行 PR re-review、没有查询/评论 GitHub PR、没有 push。

## Completion status

- PR-RV-F01: fixed locally.
- PR-RV-F03: fixed locally.
- PR-RV-F02: not handled by scope decision.
- artifact path: `docs/reviews/pr-141-fix-codex.md`
