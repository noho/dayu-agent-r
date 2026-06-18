# WU-CLI-ACTIVITY-01 CLI Review Fix - Codex

## 修复项

- Blocking：修复 prompt 运行态第二次 `Ctrl+C` 缺少本地退出的问题。
  - 第一次本地取消请求后，prompt 现在发起 Host cancel，并等待 cancel terminal 或第二次 SIGINT。
  - cancel terminal 先到时返回 terminal result。
  - 第二次 `Ctrl+C` 先到时返回 `None`，上层保持 `EXIT_KEYBOARD_INTERRUPT` 语义，并通过 activity renderer 输出本地退出提示到 stderr。
  - `Esc` 仍只作为第一次取消请求，不增加 SIGINT 计数；之后第二次 `Ctrl+C` 仍可本地退出。
- 非阻塞：`CliActivityRenderer` 现在在每条通过 dedupe / sequence 校验的 activity 上保留最新标题，因此可见 activity 后切到 hidden 也能输出 hidden 状态提示。
- 非阻塞：`TtyRunningKeyMonitor.start()` 在线程启动失败且已经进入 cbreak 后会恢复原始 terminal 属性并清空内部启动状态。

## 测试

- 新增 prompt 回归：
  - 第二次 `Ctrl+C` 在 cancel terminal 前到达时本地退出并输出 local-exit activity。
  - cancel terminal 与第二次 `Ctrl+C` 竞争时 terminal-first。
- 新增 renderer 回归：
  - 可见 activity 后切到 hidden 输出最新 activity 标题。
- 新增 TTY monitor 回归：
  - `thread.start()` 失败后恢复 terminal 行为位。
- 更新 `tests/README.md` 的 CLI 测试覆盖说明。

## 验证

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py -q`
  - 结果：97 passed，3 个 edgar deprecation warnings。
- `source .venv/bin/activate && pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys --cov-fail-under=80 -q`
  - 结果：17 passed，整体覆盖率 89.53%；`dayu.cli.activity` 88%，`dayu.cli.composer` 94%，`dayu.cli.run_keys` 89%。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：0 errors, 0 warnings。

## 剩余风险

- `Esc` 仍按单字节处理；某些终端 escape sequence 以 ESC 开头，运行态下可能被当作 cancel。该行为延续前一轮实现，未扩展为 escape-sequence parser。
- prompt cancel 等待只监听第二次 SIGINT，不监听第二次 Esc 本地退出；这是为了保持“Esc 是第一次取消请求、Ctrl+C 计数决定本地退出”的裁决语义。
