# WU CLI Output Channels Plan Review Fix

Gate: Plan Review Fix Gate
Work unit: Dayu CLI 输出通道拆分
Branch: `wu-cli-activity-01`
日期: 2026-06-17
执行者: AgentCodex

## scope

本次只修订 plan artifact，不实现代码。

修订目标：

- Plan artifact: `docs/reviews/wu-cli-output-channels-plan-20260617.md`
- MiMo review: `docs/reviews/wu-cli-output-channels-plan-review-mimo-20260617.md`
- DS review: `docs/reviews/wu-cli-output-channels-plan-review-ds-20260617.md`

用户裁决：

- 接受 MiMo F001/F002/F003/F004/F005。
- 接受 DS F1/F2/F3/F4/F5/F6/F7。

## fix summary

已修订 plan artifact，核心变化如下：

- Slice A 明确 `--log-file` 生命周期：`main()` 在 `finally` 中先恢复 dayu logger 到 stderr handler，再关闭文件 stream；异常路径必须覆盖。
- `dayu/runtime/log.py` 不再默认修改；如确需修改 handler close 行为，必须用精确测试证明不关闭 `sys.stderr`，且不留下已关闭 file handler。
- Slice B 明确非 TTY `--detail` 用 `CliActivityRendererOptions(visible=True, enabled=True)`，activity 仍是 UI activity sink，不进入 `--log-file`。
- Slice C 改为 code-generation-ready 的较小方案：CLI 层 `InteractiveRunView` / `ActivitySink` 窄协议 + 非 full-screen 终端 sink；运行态继续复用 `run_keys.py` Ctrl+T / Esc。
- Slice C 明确 Ctrl+T 新语义是 transcript/activity view switch，不再调用旧 `CliActivityRenderer.toggle_visible()`，不再输出 `Activity hidden: ...`。
- Full prompt_toolkit `Application.run_async()` 重构被标为后续独立 work unit 的 stop condition，不在本轮实现。
- Fins direct 测试策略改为先确认旧测试是 `caplog` 还是 stderr 捕获，再决定保留或迁移；新增 `--log-file` 文件 sink 测试是必须项。
- `--log-file` 多进程并发写同一文件的日志行交错风险已记录为接受限制，不在本轮加文件锁。

## findings status

| Finding | 裁决 | Fix status | Plan 修订点 |
|---|---|---|---|
| MiMo F001 `--log-file` handler 生命周期精确时序未定义 | accepted | 已修复 | Slice A exact changes 和 implementation decisions 明确 `finally` 中先恢复 stderr handler，再关闭 file stream；补异常路径测试 |
| MiMo F002 Slice C interactive TUI 改动范围过大 | accepted | 已修复 | Slice C 降级为 `InteractiveRunView` / `ActivitySink` + 非 full-screen sink；full prompt_toolkit Application 拆为后续 work unit |
| MiMo F003 Ctrl+T 语义升级缺少迁移路径 | accepted | 已修复 | contract 与 Slice C 明确 Ctrl+T 新语义，不再输出旧 `Activity hidden: ...` |
| MiMo F004 `--detail` 与 TTY `isatty()` 交互未明确 | accepted | 已修复 | Slice B 明确 `CliActivityRendererOptions(visible=True, enabled=True)`，非 TTY 显式 detail 也输出 activity |
| MiMo F005 `--log-file` 测试 mocking 策略未指定 | accepted | 已修复 | Slice A tests 明确 main spy、异常路径、Fins direct tmp_path 文件内容测试策略 |
| DS F1 prompt_toolkit 生命周期无法自然承载运行态 view | accepted | 已修复 | Slice C 不再声称 `PromptSession` 管理运行态；full Application 重构列为 stop condition / 后续 work unit |
| DS F2 `main()` log-file close 后 handler 顺序未显式指定 | accepted | 已修复 | Slice A exact changes 明确 open/reset/close 顺序和异常路径 |
| DS F3 `_reset_marker_handlers` 调用 close 可能影响 `sys.stderr` | accepted | 已修复 | runtime log 默认不改；如需改，必须有不关闭 `sys.stderr` 的精确 runtime 测试 |
| DS F4 prompt_toolkit TUI 单元测试策略缺失 | accepted | 已修复 | Slice C 改为非 full-screen sink，测试改为纯 run view buffer/unit 行为，不引入 PTY 依赖 |
| DS F5 Fins direct 现有测试迁移策略不完整 | accepted | 已修复 | Slice A tests 明确先确认 `caplog` vs stderr；按捕获方式选择保留旧测试或迁移 stderr 断言 |
| DS F6 `--log-file` append 并发写入无保护 | accepted | 已修复 | implementation decisions 与 risks 明确多进程同文件日志行可能交错，本轮不加锁 |
| DS F7 `prompt --detail` enabled 契约未明确 | accepted | 已修复 | Slice B exact changes 和 tests 明确 `CliActivityRendererOptions(visible=True, enabled=True)` 与非 TTY detail test |

## validation

本 gate 只修改 plan/review artifact，未实现代码，未运行 pytest 或 pyright。

已做文档级检查：

- 检查 plan 中不再残留旧的 `prompt_toolkit/TUI` 运行态承诺。
- 检查 plan 中保留的 `Activity hidden: ...` 仅作为“旧行为不得再输出”的测试断言。
- 检查 accepted findings 均有对应修订点。

## residual risks

| Risk | 分类 | 处理 |
|---|---|---|
| Slice C 非 full-screen sink 的 UX 可能不满足最终交互预期 | assigned to later work unit | 若必须 full prompt_toolkit `Application.run_async()`，本轮停止并拆后续 work unit |
| 多进程并发写同一 `--log-file` 可能交错 | covered by current plan | 作为已记录诊断日志限制接受，不加锁 |
| 实施阶段可能发现 runtime handler close 仍需修改 | covered by later approved slice | Slice A 要求精确 runtime 测试证明不关闭 `sys.stderr` |

## completion status

Plan review fix gate: completed for accepted findings.

Fix artifact path: `docs/reviews/wu-cli-output-channels-plan-fix-20260617.md`
