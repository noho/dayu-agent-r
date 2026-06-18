# WU-CLI-OUTPUT-CHANNELS Slice B Fix

## 背景

Controller 复跑 Slice B 相关测试时，旧用例
`test_prompt_command_uses_outbox_fallback_when_live_terminal_missing`
发生无限等待。

## Root Cause

这不是 `--detail/--no-detail` 实现导致的运行时缺陷，而是测试场景与当前
Host/Service 语义冲突：

- `submit_entrypoint_turn_and_wait()` 是在线、已 attach watcher 的路径。
- 正常 final answer 必须来自 Host event stream。
- Outbox 不是 prompt 在线读取 final answer 的通用接口。
- Submit 路径只在 watcher failure 后允许读取 Outbox terminal，避免把
  “Host 没有发 terminal event” 误当作可由 Outbox 猜测补齐的正常路径。

旧测试构造的是“watcher 没有 terminal，但 watcher 也没有失败”，却期待
Outbox fallback。这种输入下 Service 持续等待是正确行为。

## 修改

- CLI prompt fake watcher 增加 `_RaiseSignal` 与 `fail(...)`，可模拟 watcher
  drain 异常。
- 将用例改名为
  `test_prompt_command_uses_outbox_fallback_when_watcher_fails`。
- 用例输入改为 submit 后 watcher 明确抛出
  `RuntimeError("watch stream disconnected")`，再断言 prompt 经 Outbox
  fallback 输出 final answer。

## 验证

- `source .venv/bin/activate && pytest tests/cli/test_prompt_command.py::test_prompt_command_uses_outbox_fallback_when_watcher_fails -q`
  - 1 passed
- `source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py -q`
  - 81 passed, 3 warnings
- `source .venv/bin/activate && pyright dayu/cli/arg_parsing.py dayu/cli/commands/prompt.py tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py tests/cli/test_activity_renderer.py`
  - 0 errors
- `git diff --check`
  - clean

## Residual Risk

- 本修正没有改 Host/Engine public API/contracts。
- 默认 no-detail 仍不注册 activity renderer；final answer 正常路径仍依赖
  Host event stream。
