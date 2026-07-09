# WU-CLI-SMOKE-01 Display Semantics — AgentMiMo Implementation Review

## 结论

**pass**

本次变更正确对齐用户意图：`--thinking/--no-thinking` 和 `--detail/--no-detail` 都是 CLI 终端展示层开关，不污染 Service/Host/Engine/Fins 执行契约。interactive 已补齐 `--detail/--no-detail` 并与 prompt 对齐。默认 `--thinking` 且默认 `--detail`。运行态展示与 final answer 输出边界清晰。测试覆盖充分，pyright 通过。

## Review Scope

- `README.md` — 参数表格、命令示例、说明文字
- `dayu/cli/arg_parsing.py` — CLI parser 默认值、参数注册
- `dayu/cli/agent_entrypoint.py` — unsupported execution option 过滤
- `dayu/cli/commands/prompt.py` — prompt detail 默认值
- `dayu/cli/commands/interactive.py` — interactive detail 参数传递
- `dayu/cli/run_view.py` — run view initial mode、terminal result 输出行为
- `tests/cli/test_arg_parsing.py` — parser 测试
- `tests/cli/test_prompt_command.py` — prompt 命令测试
- `tests/cli/test_interactive_command.py` — interactive 命令测试
- `tests/cli/test_interactive_run_view.py` — run view 独立测试
- `tests/README.md` — 测试覆盖描述

## 设计真源核对

- `docs/host/design.md` — Host 是 Session/Run/Attempt 治理真源；CLI 是 UI adapter 层
- `docs/engine/design.md` — Engine 不读取配置、不理解 CLI 展示语义
- `docs/host/issues-implementation-control.md` — WU-CLI-SMOKE-01 scope 定义

## Findings

### F01: `default=argparse.SUPPRESS` 与默认 namespace 交互正确 [informational]

**文件**: `dayu/cli/arg_parsing.py:139-148` (interactive detail 注册), `dayu/cli/arg_parsing.py:688-699` (thinking 注册)

`_new_default_namespace()` 设置 `namespace.detail = True` 和 `namespace.thinking = True`。`argparse.SUPPRESS` 的语义是：若用户未提供参数，parser 不会覆盖 namespace 中已有值。因此最终 `args.detail` 和 `args.thinking` 在用户不指定时保持默认 `True`，用户指定 `--no-detail` 或 `--no-thinking` 时为 `False`。这是正确的设计，避免了 argparse 默认值覆盖 namespace 预设值的问题。

### F02: `render_terminal_result` 始终输出 final answer 到 stdout/stderr [accepted]

**文件**: `dayu/cli/run_view.py:265-267`

原实现：
```python
if not self._enabled or self._mode is InteractiveRunViewMode.TRANSCRIPT:
    _write_lines(stdout_lines, self._stdout)
    _write_lines(stderr_lines, self._stderr)
```

新实现：
```python
_write_lines(stdout_lines, self._stdout)
_write_lines(stderr_lines, self._stderr)
self._mode = InteractiveRunViewMode.TRANSCRIPT
```

变更语义：无论当前处于 activity 还是 transcript mode，terminal result 始终写入 stdout/stderr 用户通道，然后切回 transcript mode。这正确实现了用户意图："拿到 final answer 后清除运行态展示，不把 thinking/detail 残留在最终 transcript"。

在 activity mode 下，用户会先看到 activity 实时输出到 stderr，然后 final answer 输出到 stdout，mode 自动回到 transcript。这是合理的行为：activity 是运行态中间过程，final answer 是用户真正需要的结果。

### F03: interactive `detail=False` 时 run_view=None 跳过 activity 注册 [accepted]

**文件**: `dayu/cli/commands/interactive.py:538`

```python
run_view=effective_run_view if detail else None,
```

当 `--no-detail` 时，`detail=False`，`run_view=None` 传给下游，activity callback 不被注册，final answer 仍通过独立路径输出。这与 prompt 命令的 `--no-detail` 行为一致。

### F04: interactive run_view 创建逻辑正确 [accepted]

**文件**: `dayu/cli/commands/interactive.py:508`

```python
effective_run_view = new_interactive_run_view(show_activity=detail) if run_view is None else run_view
```

当 `detail=True` 时，`show_activity=True`，`new_interactive_run_view` 创建带 `initial_mode=ACTIVITY` 的 options，run view 从 activity mode 开始。当 `detail=False` 时，`show_activity=False`，options 为 `None`，run view 从 transcript mode 开始。

但注意：此行之后，`run_view=effective_run_view if detail else None` 在 `detail=False` 时传 `None`，所以 `effective_run_view` 虽然被创建了，但不会被使用。这是一个轻微的冗余创建，但不影响正确性——`effective_run_view` 在 `detail=False` 时会被 GC 回收。

**严重性**: low，non-blocking。

### F05: thinking 参数从 execution option 移除正确 [accepted]

**文件**: `dayu/cli/agent_entrypoint.py:238-239` (已删除)

原实现：
```python
if args.thinking is not None:
    names.append("--thinking/--no-thinking")
```

已删除。`--thinking/--no-thinking` 不再进入 `unsupported_execution_option_names` 返回的拒绝集合。这正确对齐了设计意图：thinking 是 CLI 展示开关，不是模型能力配置或执行期裁决。

测试 `test_interactive_thinking_flags_are_display_options_not_execution_overrides` 和 `test_prompt_thinking_flags_are_display_options_not_execution_overrides` 验证了这一点。

### F06: README 更新完整且语义一致 [accepted]

**文件**: `README.md:299-622`

- 参数表格：`--thinking` 描述改为"运行态思考展示"，`--detail` 扩展到 `interactive`，默认值更新 ✓
- 命令示例：`--thinking` 改为 `--no-thinking`，`--detail` 改为 `--no-detail` ✓
- 说明文字：新增"CLI 终端展示开关"约束说明 ✓
- interactive 参数表格：新增 `--detail/--no-detail` ✓
- interactive 说明：更新默认行为描述 ✓

### F07: tests/README.md 同步更新 [accepted]

**文件**: `tests/README.md:91-350`

测试覆盖描述已同步更新，反映新的默认行为和 `--thinking` 展示语义。

## 架构边界验证

### CLI → Service/Host/Engine 边界

- `thinking` 参数只在 CLI 层使用，不传入 Service request ✓
- `detail` 参数只在 CLI run_view 中使用，不传入 Host/Engine ✓
- `unsupported_execution_option_names()` 移除 thinking 检查，不污染执行期裁决 ✓
- CLI run_view 是纯 UI adapter，不读取 Host durable internals ✓

### 默认值变更影响

- `detail` 默认从 `False` 改为 `True`：prompt 和 interactive 默认显示 activity ✓
- `thinking` 默认从 `None` 改为 `True`：prompt 和 interactive 默认显示思考展示 ✓
- 这两个变更只影响 CLI 终端输出，不影响模型配置或 Host 执行 ✓

## 测试覆盖评估

| 测试文件 | 变更 | 覆盖 |
|---------|------|------|
| `test_arg_parsing.py` | 默认值、detail flag 正交性、interactive detail 互斥 | ✓ |
| `test_prompt_command.py` | 默认 detail 输出 activity、`--no-detail` 抑制、thinking 展示语义 | ✓ |
| `test_interactive_command.py` | `--no-detail` 行为、thinking 展示语义 | ✓ |
| `test_interactive_run_view.py` | activity mode terminal 输出、初始 activity mode | ✓ |

测试覆盖充分，符合 AGENTS 测试与验证约束。

## 验证可信度

- Codex 报告：focused tests 128 passed, pyright 0 errors, `git diff --check` pass
- Reviewer 独立验证：diff 审查确认实现与设计意图一致
- 无新增 pyright 错误、无架构边界违反、无执行契约污染

## Residual Risk

- 无 blocking residual risk。
- F04 的冗余 run_view 创建是极低风险的代码整洁问题，不影响正确性。
