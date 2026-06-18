# WU-CLI-ACTIVITY-01 CLI Fix - Codex

## 修复范围

- 在 CLI 层新增 `dayu.cli.run_keys`，提供运行态 TTY 按键 monitor：
  - `Ctrl+T` 映射为 activity 可见性切换。
  - `Esc` 映射为取消当前 Run。
  - 非 TTY 输入返回 no-op monitor，不改变管道 / CI 行为。
  - TTY 路径使用 cbreak 读取单字节输入，`close()` 中恢复终端模式并停止后台 reader。
- `prompt` 运行态等待现在同时监听 submit terminal、SIGINT 与运行态按键：
  - terminal 已到达时优先返回 terminal result。
  - `Ctrl+T` 只切换 renderer 可见性，不触发 Host cancel。
  - `Esc` 复用现有 Host cancel 收口路径，activity/control 提示仍写 stderr。
- `interactive` 每轮 Run 使用独立运行态按键 monitor：
  - `Esc` 等价于第一次本地取消请求，不增加 SIGINT 计数。
  - 第二次 `Ctrl+C` 本地退出语义继续由既有 SIGINT monitor 负责。
- 补充测试：
  - `tests/cli/test_run_keys.py` 覆盖 Ctrl+T / Esc 映射、非 TTY no-op、no-op cancellation、TTY pseudo-terminal 读取与终端模式恢复。
  - `tests/cli/test_prompt_command.py` 覆盖 prompt Ctrl+T 切换 visibility 且不 cancel、prompt Esc cancel。
  - `tests/cli/test_interactive_command.py` 覆盖 interactive Esc cancel。
  - `tests/README.md` 同步 CLI 测试覆盖说明。

## 验证

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py -q`
  - 结果：93 passed，3 个 edgar deprecation warnings。
- `source .venv/bin/activate && pytest tests/cli/test_activity_renderer.py tests/cli/test_interactive_composer.py tests/cli/test_run_keys.py --cov=dayu.cli.activity --cov=dayu.cli.composer --cov=dayu.cli.run_keys --cov-fail-under=80 -q`
  - 结果：15 passed，整体覆盖率 88.68%；`dayu.cli.run_keys` 覆盖率 88%。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：0 errors, 0 warnings。
- `git diff --check`
  - 结果：通过，无空白错误。

## 剩余风险

- `Esc` 使用单字节识别；某些终端方向键序列以 ESC 开头，运行态下可能被解释为 cancel。当前需求只要求 Esc cancel，未引入复杂 escape-sequence parser。
- cancel 阶段仍不消费 live activity callback；这保持了既有 Slice E 延后边界，未扩展 Host/Service API。
