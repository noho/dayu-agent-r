# WU-CLI-SMOKE-01 Display Semantics — AgentDS Adversarial Code Review

## 结论

**pass-with-required-fixes**

有一个 CRITICAL finding（`--thinking / --no-thinking` 是死参数，无任何展示或执行效果），必须在 merge 前修复。其余 `--detail` 相关实现、activity 清除逻辑、分层边界均正确。

---

## Review 上下文

- **范围**: WU-CLI-SMOKE-01 CLI display semantics 当前未提交 diff
- **基线**: `phase/host-issues-control`
- **参考文档**: `AGENTS.md`、`docs/host/design.md`、`docs/engine/design.md`、`docs/host/issues-implementation-control.md`、`docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`
- **用户意图**:
  - prompt 和 interactive 的 `--thinking/--no-thinking`、`--detail/--no-detail` 都是 CLI 展示层开关
  - 默认 `--thinking` 且默认 `--detail`
  - 运行中显示 thinking/detail；拿到 final answer 后清除运行态展示
  - `--thinking` 不得作为模型能力配置或执行期裁决
  - interactive 要补齐 `--detail/--no-detail` 并和 prompt 对齐

---

## 五大挑战逐一裁决

### 挑战 1: 是否只是改 help/parser 而没有实现清除运行态展示

**裁决: `--detail` 路径完整；`--thinking` 路径仅改了 help/parser。**

`--detail` 实现完整:
- `run_view.py:260-267` — `render_terminal_result()` 移除条件分支，始终写 stdout/stderr 用户通道，并复位 `self._mode = InteractiveRunViewMode.TRANSCRIPT`
- `run_view.py:326-331` — `new_interactive_run_view(show_activity=True)` 创建初始 activity mode 的 view
- `interactive.py:536` — `run_view=effective_run_view if detail else None` 正确控制 activity sink 注册

`--thinking` 仅改了 parser 表面:
- `arg_parsing.py:141` 类型从 `bool | None` 改为 `bool`，`arg_parsing.py:257` 默认从 `None` 改为 `True`
- `arg_parsing.py:688,695` help text 从"请求启用模型思考能力"改为"在终端显示运行态思考展示"
- `agent_entrypoint.py:238-263` 移除 `args.thinking` 的 unsupported 检查
- **但全代码库无任何代码消费 `args.thinking`** — 见 F01

### 挑战 2: prompt 默认 detail 是否会污染 stdout/log-file

**裁决: 不污染。**

- `activity.py:116` — `CliActivityRenderer.record()` 写 stderr: `print(..., file=self._stderr)`
- `prompt.py:291` — `render_prompt_terminal_result(terminal)` 写 stdout
- activity 通过 `print()` 直接输出，不走 Python `logging` 框架，不会写入 `--log-file`
- 测试 `test_prompt_default_detail_outputs_activity_and_keeps_final_answer_stdout` (`test_prompt_command.py:937`) 验证: `captured.out.strip() == "prompt answer"` 且 `"Activity:" in captured.err`
- 注意: `_new_detail_activity_renderer()` (`prompt.py:302-314`) 创建 `CliActivityRendererOptions(enabled=True)`，在非 TTY 下也输出 activity 到 stderr。这是有意设计（stderr 是诊断通道），但需确认非 TTY 场景（CI/pipe）的预期行为。

### 挑战 3: interactive activity mode 下 final answer 是否可见且不会把 activity 当最终 transcript

**裁决: 正确。**

- `run_view.py:265-266` — `render_terminal_result()` 始终写 stdout/stderr，不受 mode 影响
- `run_view.py:267` — 渲染后复位 `self._mode = InteractiveRunViewMode.TRANSCRIPT`
- `run_view.py:263-264` — transcript buffer 独立于 activity buffer（`self._activity_lines`）
- 测试 `test_run_view_activity_mode_outputs_terminal_and_returns_to_transcript` (`test_interactive_run_view.py:550`) 验证:
  - `assert stdout.getvalue() == "answer\n"` — final answer 可见
  - `assert view.mode is InteractiveRunViewMode.TRANSCRIPT` — 已回到 transcript
  - `assert "answer" not in stderr.getvalue()` — answer 不在 stderr

### 挑战 4: --thinking 是否仍有 unsupported 或执行配置副作用

**裁决: 无 unsupported 副作用，无执行配置副作用，但参数完全无效。**

- `agent_entrypoint.py:238-263` — `unsupported_execution_option_names()` 不再包含 `--thinking/--no-thinking` ✓
- `agent_entrypoint.py:266-298` — `service_run_overrides_from_args()` 不映射 `args.thinking` 到任何执行参数 ✓
- 但 `args.thinking` 根本未被任何代码消费 — 见 F01

### 挑战 5: README/tests 是否误导

**裁决: README 对 `--thinking` 的描述是误导的；tests 准确但未覆盖关键路径。**

- README.md 声称 "默认会显示运行态思考展示" 和 "`--thinking` / `--no-thinking` 只控制 CLI 终端展示" — 但根本没有 thinking 展示实现
- tests/README.md 描述准确反映了实际测试覆盖
- 测试缺少对 `--thinking` 展示效果的验证 — 见 F03

---

## Findings

### F01 [CRITICAL] `--thinking / --no-thinking` 是死参数 — 无任何展示或执行效果

- **文件**: `dayu/cli/arg_parsing.py:141,257,686-698`
- **证据**: 全代码库 `grep -rn 'args\.thinking\|\.thinking\b' dayu/ --include='*.py'` 仅命中 `arg_parsing.py:257` 的赋值语句。`args.thinking` 未被 `prompt.py`、`interactive.py`、`agent_entrypoint.py` 或任何其他模块消费。
- **根因**: 本 diff 将 `--thinking` 从"执行参数"改为"展示参数"——从 `unsupported_execution_option_names` 移除，改 help text，改默认值——但从未实现 thinking 展示逻辑。参数被 argparse 成功解析后即被丢弃。
- **影响**:
  - `dayu-cli prompt "hello" --thinking` 与 `dayu-cli prompt "hello" --no-thinking` 的终端输出完全一致
  - README.md 声称的 "运行态思考展示" 不存在
  - 用户无法通过这两个 flag 控制任何可见行为
- **修复方向**: 要么实现 thinking delta 的 CLI 渲染路径（需接入 EngineEvent `reasoning_delta` 的 Host projection），要么将 `--thinking/--no-thinking` 标记为 `unsupported` 并明确告知用户当前版本不支持 thinking 展示。推荐后者，因为 Codex 报告中也承认 "本次没有新增 Engine / Host raw reasoning projection"。

### F02 [HIGH] README 和 help text 对 `--thinking` 的描述与实现不符

- **文件**: `README.md:302,552-555,622-623`; `dayu/cli/arg_parsing.py:690,695`
- **证据**:
  - README.md:302: "控制是否在终端回显运行态思考展示；默认 `--thinking`" — 无实现
  - README.md:555: "默认会显示运行态思考展示和 activity stream" — thinking 部分无实现
  - README.md:575: "`--thinking` / `--no-thinking` 只控制 CLI 终端展示，不会改变模型配置或 provider 请求参数" — 前半句不实
  - `arg_parsing.py:690`: `help="在终端显示运行态思考展示。"` — 无实现
- **影响**: 用户文档承诺的功能不存在，构成文档欺诈。用户可能基于文档描述做决策，但实际行为与文档不符。
- **修复方向**: 随 F01 修复方向同步更新。若 F01 选择标记 unsupported，则 README 应说明 `--thinking/--no-thinking` 当前不可用；若 F01 选择实现 thinking rendering，则 README 可保持当前描述。

### F03 [MEDIUM] 缺少 `--thinking` 展示效果的端到端测试

- **文件**: `tests/cli/test_prompt_command.py`, `tests/cli/test_interactive_command.py`
- **证据**: 现有测试仅验证:
  - `test_prompt_thinking_flags_are_display_options_not_execution_overrides` (`test_prompt_command.py:1315`) — 验证不在 unsupported 集合
  - `test_interactive_thinking_flags_are_display_options_not_execution_overrides` (`test_interactive_command.py:1511`) — 同上
  - `test_prompt_detail_flags_are_orthogonal_to_log_level` (`test_arg_parsing.py:1080`) — 不涉及 thinking
- **缺失**: 无任何测试验证 `--thinking` vs `--no-thinking` 对终端输出（stdout/stderr）的实际影响。如果存在这样的测试，F01 会在实现阶段就被发现。
- **影响**: 测试覆盖缺口使 F01 逃逸到 code review 阶段。
- **修复方向**: F01 修复后，补齐对应测试: 若实现 thinking rendering，加测试验证 thinking delta 出现在 stderr；若标记 unsupported，加测试验证 `--thinking` 触发 usage error。

### F04 [LOW] interactive `--no-detail` 路径下 run_view 仍被创建但 activity sink 不注册

- **文件**: `dayu/cli/commands/interactive.py:509,536`
- **证据**:
  - Line 509: `effective_run_view = new_interactive_run_view(show_activity=detail) if run_view is None else run_view` — `detail=False` 时仍创建 `TerminalInteractiveRunView`
  - Line 536: `run_view=effective_run_view if detail else None` — 但不把 view 传给 submit 函数作为 activity sink
  - Line 541: `effective_run_view.render_terminal_result(terminal)` — view 仅用于渲染 terminal result
- **分析**: 行为正确但设计略冗余。`detail=False` 时 `effective_run_view` 的 `record_activity` 永远不会被调用（因为 activity sink 未注册），但 `render_terminal_result` 仍通过同一 view 实例渲染。这是有意设计（view 同时承担 terminal rendering 和 activity sinking 两个职责），不属于 bug，但值得在代码中加注释说明 "detail=False 时 view 仅用于 terminal rendering，不作为 activity sink"。
- **修复方向**: 可选，接受当前设计。如需改进，可在 `_run_interactive_repl` 方法 docstring 中补充说明。

### F05 [LOW] `_new_detail_activity_renderer()` 强制 `enabled=True`，在非 TTY 场景行为与默认构造不同

- **文件**: `dayu/cli/commands/prompt.py:302-314`; `dayu/cli/activity.py:70-73`
- **证据**:
  - `_new_detail_activity_renderer()` 创建 `CliActivityRendererOptions(enabled=True)` — 强制启用
  - 默认 `CliActivityRenderer()` 构造使用 `enabled=self._stderr.isatty()` — 按 TTY 自动判断
  - 这意味着 `--detail`（默认开启）在 pipe/redirect/CI 场景也会输出 activity 到 stderr
- **分析**: Codex 报告确认这是有意设计: "activity 在非 TTY 捕获流中会作为默认 detail 输出到 stderr"。但这个行为对 `--detail` vs `--no-detail` 的差异是合理的: `--detail` 显式要求显示 activity，不依赖 TTY 判断。
- **修复方向**: 无需修复。如需严谨，可在 `_new_detail_activity_renderer` 的 docstring 中说明 "显式 detail 模式不受 TTY 状态影响，始终输出"。

---

## 架构与分层检查

### 分层边界 ✓

- `args.thinking` 不进入 `service_run_overrides_from_args()` → 不泄漏到 Service/Host/Engine 层
- `args.detail` 仅在 CLI 层消费（`prompt.py`、`interactive.py`）→ 不跨层泄漏
- `run_view.py` 只消费 `EntrypointActivity` 和 `EntrypointRunTerminalResult` DTO → 不读 Host durable internals
- `activity.py` 只写 stderr → 不污染 stdout/log-file

### 项目指令合规

| 指令 | 状态 | 说明 |
|------|------|------|
| 禁止魔法数字/字符串 | ✓ | 无新增 |
| 函数 docstring | ✓ | 新增参数均有中文 docstring |
| 禁止 `Any` / 无类型签名 | ✓ | `detail: bool = True` 类型明确 |
| 禁止兼容性代码 | ✓ | 无兼容性 wrapper |
| 测试覆盖 | ⚠ | 见 F03 |
| pyright | ✓ | 报告 0 errors |
| README 同步 | ⚠ | 见 F02 |

---

## 未覆盖风险

1. **thinking delta 投影路径缺失**: 即使将来实现 `--thinking` 展示，也需要 Host 层将 Engine `reasoning_delta` 事件投影到 CLI-visible activity。当前 Host/Engine 设计真源支持 `reasoning_delta` 事件，但 CLI 到 Host 的 activity 管线是否已有 reasoning 类型需要确认。
2. **非 TTY interactive 场景**: `TerminalInteractiveRunView` 在非 TTY 下 `_enabled=False`，`render_terminal_result` 走 `self._closed` 分支直接渲染。这个路径的测试覆盖需要确认（当前 `test_interactive_run_view.py` 的测试均使用 StringIO，不涉及 TTY 检测）。
3. **`--thinking` 与 `--no-detail` 组合**: 两个参数独立但语义上可能存在用户困惑——如果用户同时传 `--thinking` 和 `--no-detail`，期望看到 thinking 但不看 activity，当前因 F01 两者都不可见。

---

## 验证摘要

- 代码走查: `dayu/cli/arg_parsing.py`, `dayu/cli/agent_entrypoint.py`, `dayu/cli/commands/prompt.py`, `dayu/cli/commands/interactive.py`, `dayu/cli/run_view.py`, `dayu/cli/activity.py`
- 全库 `args.thinking` 消费搜索: 0 处消费
- 全库 `service_run_overrides_from_args` 映射确认: thinking 不在映射中
- 测试文件检查: `tests/cli/test_arg_parsing.py`, `tests/cli/test_prompt_command.py`, `tests/cli/test_interactive_command.py`, `tests/cli/test_interactive_run_view.py`
- Codex 报告交叉验证: 风险段承认 "本次没有新增 Engine / Host raw reasoning projection"
