# WU CLI Output Channels Slice B Implementation

Gate: Implementation
Work unit: Dayu CLI 输出通道拆分
Slice: B - `prompt --detail/--no-detail`
Branch: `wu-cli-activity-01`
日期: 2026-06-17
执行者: AgentCodex

## Scope

本 slice 只实现 prompt command 的 activity detail gate，不做 interactive run view，不修改 Host / Engine public API 或 durable schema。

实际修改文件：

- `dayu/cli/arg_parsing.py`
- `dayu/cli/commands/prompt.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_prompt_command.py`
- `tests/README.md`

## Decisions

- `ParsedCliArgs` 新增 `detail: bool`，默认值为 `False`。
- `prompt` command 新增 mutually exclusive `--detail` / `--no-detail`，默认 no-detail。
- prompt 默认不创建 `CliActivityRenderer`，因此不会向 Service helper 注册 `on_activity` 输出回调。
- `--detail` 显式创建 `CliActivityRenderer(options=CliActivityRendererOptions(visible=True, enabled=True))`，绕过默认 TTY gate；非 TTY 捕获流也会输出 activity。
- `--debug` / `--verbose` 不打开 detail；`--detail` 不改变 `log_level`。
- activity 继续作为 CLI UI 输出写 stderr，不进入 `--log-file` 诊断日志文件。
- `_submit_prompt_turn_handling_sigint` 的 cancel activity 提示保持原边界：只有 renderer 存在时才输出。

## Tests

新增或更新断言：

- prompt help 包含 `--detail` / `--no-detail`。
- `parse_cli_args(("prompt", "hello")).detail is False`。
- `prompt --detail` / `prompt --no-detail` 解析为预期 bool。
- `--debug` / `--verbose` 与 `--detail` 的解析互不隐式联动。
- `--detail` 与 `--no-detail` 互斥。
- prompt 默认即使收到 fake Host activity event 也不输出 `Activity:`。
- `prompt --detail` 在非 TTY pytest 捕获流下输出 activity，final answer 仍只写 stdout。
- `prompt --verbose` / `--debug` 收到 activity event 时不显示 activity。
- `prompt --detail --log-file <path>` 的 activity 只写 stderr，不写入日志文件。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py -q
```

结果：

- `81 passed, 3 warnings`
- warnings 来自第三方 `edgar` deprecation warning，非本 slice 引入。

已运行：

```bash
source .venv/bin/activate && python -m pyright dayu/cli/arg_parsing.py dayu/cli/commands/prompt.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py
```

结果：

- `0 errors, 0 warnings, 0 informations`

已运行：

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：

- `0 errors, 0 warnings, 0 informations`

已运行：

```bash
git diff --check
```

结果：

- 无 whitespace error。

## Docs Decision

- 已按触发规则更新 `tests/README.md`，仅同步 `tests/cli` 当前测试覆盖事实。
- 未更新 `dayu/README.md`：本 slice 不改变分层关系、装配方式或 runtime logging 边界，`--log-file` 已属于 Slice A。
- 未更新其它 README：本 slice 不触及对应目录职责。

## Residual Risks

- fixed in current slice：prompt 默认 no-detail、显式 detail、非 TTY detail、日志 flag 正交性、activity 不进入 `--log-file` 已由测试覆盖。
- covered by later approved slice：interactive transcript/activity view、Ctrl+T view toggle 属于 Slice C，本 slice 未实现。
- assigned to later work unit：无。
- tracked by existing issue：无。
- requiring new issue or explicit user decision：无。

Completion status: Slice B implementation complete; no blocking open question.

Artifact path: `docs/reviews/wu-cli-output-channels-slice-b-implementation-20260617.md`
