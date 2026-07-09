# WU-CLI-SMOKE-01 Display Semantics — AgentMiMo Re-review

## 结论

**pass**

本轮改动完整闭环了上一轮 DS 的 CRITICAL finding（F01: `--thinking/--no-thinking` 是死参数）。REASONING_DELTA 从 Engine → Host PREVIEW row → HostThinkingView → Service EntrypointThinking → CLI thinking renderer 的完整链路已实现，且 `--thinking` / `--no-thinking` 确实产生可观测的输出差异。Host/Service/CLI 分层边界正确，thinking 不污染 final answer、activity、outbox 或 transcript。测试覆盖了关键行为差异。

## Review Scope

- **Mode**: Current Changes Mode，相对 `main` 的 workspace diff
- **Branch**: `phase/host-issues-control`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-cli-smoke-01-display-semantics-rereview-mimo.md`
- **Included scope**: 所有 staged/unstaged 改动 + 当前 branch 未 merge 的 committed changes
- **Parallel review coverage**: 无

## DS Required Findings 闭环验证

### DS F01 [CRITICAL] `--thinking/--no-thinking` 是死参数 — 已闭环

上一轮 DS 发现全代码库无任何代码消费 `args.thinking`。本轮改动建立了完整消费链路：

1. **Engine → Host**: `engine_ingest.py:897-901` — `REASONING_DELTA` 从 transient delta（丢弃）改为写入 PREVIEW EventLog row
2. **Host read API**: `read_api.py:1106-1120` — `_thinking_from_row()` 将 REASONING_DELTA row 投影为 `HostThinkingView`
3. **Host public contract**: `api.py:2649-2664` — 新增 `HostThinkingView` dataclass；`api.py:3061` — `HostEvent.thinking` 字段
4. **Host terminal guard**: `api.py:3116` — terminal event 禁止携带 thinking，防止污染 final answer
5. **Service layer**: `entrypoint_runtime.py:625-681` — `submit_entrypoint_turn_and_wait()` 接受 `on_thinking` callback；`entrypoint_runtime.py:1220-1239` — thinking 投影按 run_id/dedupe_key 过滤
6. **CLI layer**: `prompt.py:189,437` / `interactive.py:247,634` — `args.thinking` 控制是否注册 thinking renderer callback
7. **CLI renderer**: `thinking.py` — `CliThinkingRenderer` 输出 "Thinking: ..." 到 stderr，支持 dedupe 和 sequence 排序

**验证**: 测试 `test_prompt_thinking_flag_outputs_reasoning_delta_and_no_thinking_suppresses_it` 和 `test_interactive_thinking_flag_outputs_reasoning_delta_and_no_thinking_suppresses_it` 明确验证 `--thinking` 下 stderr 包含 "Thinking:" 前缀，`--no-thinking` 下不包含。两者 final answer stdout 输出一致。

### DS F02 [HIGH] README 与实现不符 — 已闭环

README 更新准确反映了新实现：
- `--thinking` / `--no-thinking` 默认 `--thinking`，描述为"控制是否在终端回显运行态思考展示"
- `--detail` / `--no-detail` 扩展到 interactive 子命令
- 新增说明："`--thinking` 和 `--detail` 都是 CLI 终端展示开关，不会启用或关闭模型侧思考能力"
- 命令示例已更新：`--thinking` → `--no-thinking`，`--detail` → `--no-detail`（展示关闭用法）

### DS F03 [MEDIUM] 缺少 thinking 展示效果端到端测试 — 已闭环

本轮新增测试：
- `tests/cli/test_thinking_renderer.py` — 3 个测试覆盖 enabled/disabled/dedupe+ordering
- `tests/cli/test_prompt_command.py::test_prompt_thinking_flag_outputs_reasoning_delta_and_no_thinking_suppresses_it`
- `tests/cli/test_interactive_command.py::test_interactive_thinking_flag_outputs_reasoning_delta_and_no_thinking_suppresses_it`
- `tests/host/test_engine_ingest_mapping.py::test_reasoning_delta_is_accepted_as_preview_for_live_display`
- `tests/service/test_entrypoint_runtime.py::test_submit_entrypoint_turn_emits_host_public_thinking`
- `tests/host/test_host_activity_event_projection.py` — 补充 thinking 投影断言

---

## Findings

### 01-未修复-低-interactive `detail=False` 时冗余创建 run_view

- **入口/函数**: `_run_interactive_repl()`
- **文件(行号)**: `dayu/cli/commands/interactive.py:523`
- **输入场景**: `dayu-cli interactive --no-detail`
- **实际分支**: `detail=False` → `show_activity=False` → 创建 `TerminalInteractiveRunView(options=None)` → 但 `run_view=effective_run_view if detail else None` 传 `None`
- **预期行为**: `detail=False` 时不应创建不会被使用的 run_view
- **实际行为**: run_view 被创建后未被使用，等待 GC 回收
- **直接证据**: `interactive.py:523` 创建 `effective_run_view`；`interactive.py:550` 传 `None` 给 submit
- **影响**: 无功能影响，轻微资源浪费
- **建议改法和验证点**: 可将创建逻辑改为 `effective_run_view = run_view if run_view is not None else (new_interactive_run_view(show_activity=detail) if detail else None)`；或在 docstring 中说明这是有意设计（view 同时承担 terminal rendering 职责）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **建议裁决**: accepted — 当前行为正确，只是轻微冗余

### 02-未修复-低-CliThinkingRenderer 单行截断 160 字符可能丢失关键推理上下文

- **入口/函数**: `format_cli_thinking_line()`
- **文件(行号)**: `dayu/cli/thinking.py:111`
- **输入场景**: 模型产生超长 thinking delta（>160 字符）
- **实际分支**: `_TEXT_MAX_CHARS = 160` → 超长文本被截断并加 "..." 后缀
- **预期行为**: 运行态单行展示截断是合理设计
- **实际行为**: 超过 160 字符的 thinking 文本被截断
- **直接证据**: `thinking.py:56` `_TEXT_MAX_CHARS: Final[int] = 160`；`thinking.py:119-121` 截断逻辑
- **影响**: 用户可能无法在终端看到完整推理过程；但 thinking 是运行态增量展示，非持久化记录，截断可接受
- **建议改法和验证点**: 当前设计合理。若需完整 thinking，可在 CLI UI adapter 中支持可展开的 thinking panel，但这属于 UI 增强而非 bug fix
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低
- **建议裁决**: accepted — 运行态展示截断是合理 tradeoff

---

## 分层边界检查

| 检查项 | 状态 | 说明 |
|--------|------|------|
| CLI → Service 依赖方向 | ✓ | CLI 只消费 `EntrypointThinking` DTO，不读 Host internals |
| Service → Host 依赖方向 | ✓ | Service 只消费 `HostEvent.thinking` / `HostThinkingView`，不读 EventLog |
| Host → Engine 依赖方向 | ✓ | Host ingest 消费 `EngineEvent` + `ReasoningDeltaData`，不向上泄漏 |
| thinking 不污染 final answer | ✓ | `_validate_host_event_terminal_payload` 禁止 terminal event 携带 thinking |
| thinking 不污染 activity | ✓ | `_activity_from_row` 对 REASONING_DELTA 返回 None；thinking 独立投影 |
| thinking 不污染 outbox | ✓ | thinking 是 PREVIEW class，不进入 outbox projection |
| thinking 不影响模型配置 | ✓ | `args.thinking` 不进入 `service_run_overrides_from_args()` |
| `HostThinkingView` 导出 | ✓ | 通过 `host/__init__.py` 和 `host/api.py` 的 `__all__` 正确导出 |

## 项目指令合规

| 指令 | 状态 | 说明 |
|------|------|------|
| 禁止魔法数字/字符串 | ✓ | `_TEXT_MAX_CHARS` 有命名常量 |
| 函数 docstring | ✓ | 所有新增函数/参数有中文 docstring |
| 禁止 `Any` / 无类型签名 | ✓ | 所有参数类型明确 |
| 禁止兼容性代码 | ✓ | 无兼容性 wrapper |
| 测试覆盖 | ✓ | thinking on/off 输出差异有端到端测试 |
| pyright | ✓ | Codex 报告 0 errors |

## Open Questions

- 无

## Residual Risk

1. **REASONING_DELTA PREVIEW row 累积量**: 如果模型产生大量 thinking delta，EventLog 中会累积大量 PREVIEW row。当前 ingest 无节流机制。但 PREVIEW row 生命周期短（Run 结束后不再被读取），且 `CliThinkingRenderer` 有 dedupe，实际风险低。
2. **非 TTY 场景 thinking 输出**: `CliThinkingRenderer` 默认 `options=None` 时按 `stderr.isatty()` 决定是否启用。但 `_new_thinking_renderer()` 强制 `enabled=True`，在 pipe/CI 场景也会输出 thinking 到 stderr。这与 `_new_detail_activity_renderer()` 行为一致，是有意设计。
3. **thinking 与 detail 独立性**: `--no-detail --thinking` 组合下，用户会看到 thinking 但不看 activity。这是合理行为，但 README 未明确说明此组合。
