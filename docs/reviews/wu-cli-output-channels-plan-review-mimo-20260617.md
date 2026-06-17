# Plan Review: WU CLI Output Channels

- **Reviewer**: AgentMiMo
- **Plan artifact**: `docs/reviews/wu-cli-output-channels-plan-20260617.md`
- **Work unit**: Dayu CLI 输出通道拆分
- **Review date**: 2026-06-17
- **Design truth sources checked**:
  - `dayu/README.md` — 项目术语、架构、日志通道决策
  - `docs/design.md` — 日志与可观测性设计
  - `docs/host/design.md` — Host 架构真源
  - `docs/host/ui-implementation-control.md` — gateflow 控制文档
  - `dayu/runtime/log.py` — 日志装配实现
  - `dayu/cli/main.py` — CLI composition root
  - `dayu/cli/activity.py` — activity renderer
  - `dayu/cli/commands/prompt.py` — prompt command
  - `dayu/cli/commands/interactive.py` — interactive command
  - `dayu/cli/run_keys.py` — TTY 按键 monitor
  - `dayu/cli/arg_parsing.py` — 参数解析

## Summary

Plan 的动机成立、scope boundary 清晰、Host/Engine public API 边界守得住。但存在一个 high-severity 的实现规格缺口（`--log-file` handler 生命周期的精确时序未定义）和一个 medium-severity 的 scope risk（Slice C interactive TUI 改动范围超出 single-slice 合理边界）。plan 的 evidence-based 质量高，代码引用准确，但关键实现路径缺少足够的 code-generation-ready 规格。

## Assumptions Tested

1. `runtime_log.configure(stream=file)` 能直接接受文件流 → **成立**。`configure()` 的 `stream: TextIO | None` 签名确认。
2. `_reset_marker_handlers` 不 close handler → **成立**。`runtime/log.py:263-273` 只做 `removeHandler`，不调用 `handler.close()`。
3. `main.py` 的 `set_level_from_flags` 调用传 `debug=False` 等硬编码 → **成立但无害**。`--debug` 等通过 `action="store_const"` 映射到 `args.log_level`，所以 `set_level_from_flags` 只用 `log_level` 参数。
4. Service `on_activity` 回调已足够承载新 UI → **成立**。`entrypoint_runtime.py:585-595` 接受 `on_activity`，`1068-1163` 只投影 public activity。
5. `--log-file` 可通过 `global_parent` 实现 command 前后位置 → **成立**。现有 `--base` 使用相同机制且有测试证据。
6. Fins direct 的诊断与用户输出已经分离 → **成立**。`fins.py:293-320` 用 `runtime_log` 输出诊断，`output.py:202-248` 用 `render_fins_direct_event` 输出用户 progress/result。

## Findings

### F001-未修复-高-`--log-file` 文件 handler 生命周期精确时序未定义

- **位置**: `implementation decisions` 第 4 点；`Slice A` Exact changes 最后一段
- **问题类型**: 不可直接实施
- **当前写法**:
  - 第 4 点说"如果 main 使用 `with open(...)`，必须保证 logger 不持有关闭后的 file stream"，"优先在 `_reset_marker_handlers` remove 后 close 自有 marker handler"。
  - Slice A 说"runner 完成后关闭 file stream，并避免 logger 残留关闭 stream handler"。
  - 两处描述暗示不同实现路径：一处用 `with open(...)`（context manager），一处说 runner 完成后显式关闭。
- **反例/失败场景**:
  1. 若 main 用 `with open(...) as log_stream` 包裹 runner 调用，runner 正常返回或抛异常后文件自动关闭。但此时 logger 仍持有指向已关闭文件的 StreamHandler。后续任何 `logging.getLogger("dayu").error(...)` 调用（包括 Python logging shutdown 阶段的 `logging.shutdown()` 之前）会写入已关闭的 stream，触发 `ValueError: I/O operation on closed file`。
  2. 若 main 在 runner 返回后显式 `log_stream.close()`，同样的问题：logger handler 仍持有 closed stream。
  3. 若在关闭文件前调用 `runtime_log.configure(stream=sys.stderr)` 把 logger 重置回 stderr，这是安全的，但 plan 没有写这一步。
  4. 若只依赖 `_reset_marker_handlers` close handler，需要确保 close 发生在文件关闭之前，且后续没有代码路径再调用 `configure()` 指向已关闭的文件。
- **为什么有问题**: `runtime/log.py` 的 `configure()` 每次调用都会 `_reset_marker_handlers` 然后创建新 handler。如果 main 关闭文件后，有任何代码路径（包括 Python 解释器 shutdown 阶段的 logging cleanup）再次触发 `configure()`，会创建指向已关闭 stream 的 handler。plan 没有定义精确的 open/close/reset 序列，implementation agent 必须自行设计这个关键时序。
- **直接证据**:
  - `runtime/log.py:263-273`: `_reset_marker_handlers` 只 `removeHandler`，不 `close`。
  - `runtime/log.py:122-127`: `configure()` 无条件创建新 handler 绑定到 `effective_stream`。
  - `main.py:70-93`: main 的 try/except 结构，runner 调用在 try 块内。
- **影响**: implementation agent 可能实现一个在测试中通过但在生产 shutdown 阶段写已关闭文件的 handler；或者为了安全性过度复杂化 handler lifecycle 管理。
- **建议改法和验证点**:
  1. 明确 main 的实现策略：在 `try` 块前打开文件，`finally` 块中先 `runtime_log.configure(stream=sys.stderr)` 重置 logger 回 stderr，再关闭文件。不依赖 `_reset_marker_handlers` 的 close 行为。
  2. 或者：不在 main 中关闭文件（进程退出时 OS 自动回收），但需要评估这是否符合 CLI 资源管理最佳实践。
  3. 验证点：测试中模拟 runner 抛异常后，logger 不持有 closed stream handler。
- **修复风险（低/中/高）**: 中
- **严重程度（高）**: 实现 agent 必须自行设计 handler 生命周期时序，plan 不够 code-generation-ready。

### F002-未修复-中-Slice C interactive TUI 改动范围超出 single-slice 边界

- **位置**: `Slice C` 全节
- **问题类型**: 切片过粗
- **当前写法**: Slice C 要求：定义 CLI 层窄协议（6 个方法）、实现 TTY prompt_toolkit TUI controller（transcript/activity buffers、view mode）、实现非 TTY fallback、重写 interactive command 的 UI 交互逻辑、更新 Ctrl+T 语义、更新 3+ 个测试文件。
- **反例/失败场景**:
  1. Implementation agent 在实现 TUI controller 时发现 prompt_toolkit 的 layout/buffer 管理比预期复杂，被迫在 Slice C 内做多轮迭代，拖慢整个 work unit。
  2. TUI controller 的协议设计与现有 `InputComposer`、`CliActivityRenderer`、`RunningKeyMonitor` 的职责边界产生冲突，需要重构现有接口。
  3. 非 TTY fallback 与 TTY 路径的测试矩阵组合爆炸。
- **为什么有问题**: Slice A（日志文件）、Slice B（detail flag）各自只改 2-3 个文件、行为边界清晰。Slice C 要新建协议、新建 TUI controller 实现、改 interactive command、改 activity renderer 复用逻辑、改按键语义、新增/更新 3+ 测试文件。这是一个完整的 feature，不是一个 small slice。
- **直接证据**:
  - Slice C "Exact design" 列出 6 个协议方法 + TTY implementation 持有 3 类状态 + 非 TTY fallback + interactive command 重写 + 测试更新。
  - 对比 Slice A（改 3 文件 + 2-3 测试）和 Slice B（改 2 文件 + 2-3 测试），Slice C 的改动量和设计决策量显著更大。
- **影响**: Slice C 可能成为整个 work unit 的瓶颈；如果 TUI 设计在实现中需要调整，会反过来影响 Slice A/B 已完成的工作。
- **建议改法和验证点**:
  1. 拆分为 C1（协议定义 + 非 TTY fallback stub）和 C2（TTY prompt_toolkit 实现 + 集成测试）。
  2. 或者：Slice C 先只做"Ctrl+T 语义升级 + activity buffer 管理"，不引入完整的 prompt_toolkit layout。用简单的 print-based transcript/activity 交替渲染替代 full TUI。
  3. 验证点：每个子 slice 有独立 completion signal 和可运行测试。
- **修复风险（低/中/高）**: 中
- **严重程度（中）**: 不是 blocker，但会增加实现风险。

### F003-未修复-中-Ctrl+T 语义升级缺少迁移路径

- **位置**: `contract/schema/state changes` interactive TTY 快捷键；`Slice C` Exact design
- **问题类型**: 契约缺失
- **当前写法**: "复用现有 Ctrl+T 动作，但语义从'切换 stderr activity 可见性'升级为'切换 transcript / activity view'"。
- **反例/失败场景**:
  1. 现有用户依赖 Ctrl+T 的"toggle activity 可见性"语义：按一次隐藏 activity（显示 "Activity hidden: ..."），再按一次显示。新语义是"切换 view"：按一次切到 activity view（全屏 activity），再按一次切回 transcript view。这是不同的 UX 行为。
  2. 旧语义下，transcript 和 activity 同时可见（activity 以 stderr 行形式出现在 transcript 下方）。新语义下，同一时刻只显示一个 view。用户可能依赖"同时看到 transcript 和 activity"的行为。
  3. plan 没有说明旧的 `toggle_visible()` 行为是否保留（例如作为另一个快捷键）或完全废弃。
- **为什么有问题**: 这是一个用户可见的行为变更，plan 把它当作"复用"处理，但实际上是从 toggle-visibility 升级到 view-switching，是语义跃迁。
- **直接证据**:
  - `activity.py:118-132`: `toggle_visible()` 在隐藏时打印 "Activity hidden: ..."。
  - `interactive.py:604-606`: Ctrl+T 调用 `renderer.toggle_visible()`。
  - `run_keys.py:264-265`: Ctrl+T 映射到 `RunningKeyAction.TOGGLE_ACTIVITY`。
- **影响**: 实现 agent 可能不确定是否保留旧的 toggle-visible 行为，导致实现不一致。
- **建议改法和验证点**:
  1. 明确：Ctrl+T 在新语义下是 view switch，不再有 "Activity hidden" 提示。
  2. 如果需要保留旧行为，定义另一个快捷键或 `--detail` 模式下的特殊行为。
  3. 验证点：测试中确认 Ctrl+T 在 interactive TTY 模式下的精确行为（切换 view，不触发 cancel，不打印 "Activity hidden"）。
- **修复风险（低/中/高）**: 低
- **严重程度（中）**: 用户可见行为变更需要明确规格。

### F004-未修复-低-`--detail` 与 TTY `isatty()` 的交互未明确

- **位置**: `implementation decisions` 第 5 点
- **问题类型**: 契约缺失
- **当前写法**: "args.detail 为 True 时使用 CliActivityRenderer，且显式 enabled。是否 TTY 不再是 detail 的唯一开关；用户显式要求 detail 时应可在 CI/log 捕获中看到 activity。"
- **反例/失败场景**:
  1. 当前 `CliActivityRenderer.__init__` 在 `options is None` 时按 `self._stderr.isatty()` 决定 `enabled`。plan 说 `--detail` 时"显式 enabled"，但没说如何绕过 `isatty()` 检查。
  2. 实现 agent 可能创建 `CliActivityRendererOptions(visible=True, enabled=True)` 传入，但没确认 `enabled=True` 是否覆盖 `isatty()` 检查（当前代码确实覆盖，因为 `options is not None` 时跳过 `isatty()` 判断）。
  3. 如果 `--detail` 在非 TTY 下输出 activity，activity 会混入 stderr，可能被脚本捕获。plan 说"这是用户显式要求"，但没说清楚 activity 输出到 stderr 还是 stdout。
- **为什么有问题**: 小规格缺口，implementation agent 大概率能自行推断，但增加了歧义。
- **直接证据**: `activity.py:70-76`: `options is None` 时按 `isatty()` 决定；`options is not None` 时使用传入值。
- **影响**: 低。implementation agent 能从代码推断正确行为。
- **建议改法和验证点**: 在 plan 中补一句：`--detail` 时创建 `CliActivityRendererOptions(visible=True, enabled=True)`，activity 仍输出 stderr（与现有行为一致）。
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 纯规格补充。

### F005-未修复-低-`--log-file` 测试的 mocking 策略未指定

- **位置**: `Slice A` Tests
- **问题类型**: 测试缺口
- **当前写法**: "main spy test 增加 log_file 默认仍 stream=sys.stderr 的断言，并新增 log_file 版本断言传入 file stream。"
- **反例/失败场景**:
  1. 测试需要 mock `runtime_log.set_level_from_flags` 来验证 `stream` 参数。但 plan 没有说明是 spy `set_level_from_flags` 还是 spy `configure`，还是直接检查日志文件内容。
  2. 如果 spy `set_level_from_flags`，需要验证 `stream` 参数是文件对象而不是 `sys.stderr`。但文件对象的比较需要特殊处理（不能直接 `assert stream is open_file`）。
  3. Fins direct 测试说"stderr 不含 `Fins direct command start`，文件含 VERBOSE 诊断"。但当前 Fins direct 的诊断输出用的是 `runtime_log` 的 logger，不是直接 print。测试需要确认文件确实收到了 logger 输出。
- **为什么有问题**: 测试策略不明确，implementation agent 可能选择不同的 mocking 方式，导致测试行为不一致。
- **直接证据**: 当前 `test_fins_commands.py` 的诊断断言方式需要查看才能确认是否能直接迁移。
- **影响**: 低。测试最终能写出来，但可能需要 implementation agent 重新设计测试策略。
- **建议改法和验证点**: 补充说明：Fins direct 测试推荐用 tmp_path 创建临时日志文件，运行命令后检查文件内容包含预期诊断行。
- **修复风险（低/中/高）**: 低
- **严重程度（低）**: 不影响功能，只影响测试实现路径。

## Open Questions

无 blocking open question。

## Residual Risks

| Risk | 严重程度 | 建议追踪目标 |
|------|---------|------------|
| Slice C TUI 实现可能需要 prompt_toolkit layout 探索，超出预期工作量 | 中 | 实现阶段 gate review |
| `--log-file` 在 Python logging shutdown 阶段的行为需要实测验证 | 中 | 实现阶段测试 |
| Ctrl+T 语义升级的用户感知需要 UX 确认 | 低 | 用户确认阶段 |
| Fins direct `--log-file` 测试可能需要调整现有测试 fixture | 低 | 实现阶段 |

## Checklist

| Criterion | Status | Note |
|-----------|--------|------|
| 动机成立，未过度宣称 | PASS | root cause 分析准确 |
| Host/Engine public API 边界未被侵犯 | PASS | 明确声明不改 Host/Engine，Service `on_activity` 足够 |
| 场景选择合理 | PASS | 覆盖 prompt/interactive/Fins direct/init/session |
| 实现 slice 足够小且可独立验证 | PARTIAL | Slice A/B 合格，Slice C 过粗 |
| 代码引用准确 | PASS | 所有文件路径和行号经验证正确 |
| 测试计划覆盖 failure paths | PARTIAL | happy path 覆盖好，handler lifecycle failure path 和 logging shutdown 未覆盖 |
| README 更新决策正确 | PASS | 触发规则判断合理 |
| 验证命令完整 | PASS | pytest + pyright 命令齐全 |
| 无 Host/Engine contract 修改 | PASS | "预计不修改" 列表正确 |
| Fins direct 复用自然 | PASS | 诊断走 runtime_log，用户输出走 render_fins_direct_event，`--log-file` 只改前者 sink |
| Chinese docstrings 要求 | N/A | plan 层面不涉及 |
| 严格类型要求 | N/A | plan 层面不涉及 |

## Conclusion

**pass-with-risks**

Plan 可以进入 user confirmation，但需要在实现前解决或确认以下事项：

1. **F001（高）必须在实现前明确**：`--log-file` handler 生命周期的精确 open/close/reset 序列。建议采用"finally 块中先 reset logger 回 stderr 再关闭文件"的策略。
2. **F002（中）建议在实现前拆分**：Slice C 拆为 C1（协议 + 非 TTY）和 C2（TTY 实现），或降级为简单的 view toggle 而非 full TUI。
3. **F003（中）建议在实现前明确**：Ctrl+T 的精确新行为和旧行为是否保留。

F004、F005 为低严重度，implementation agent 可自行处理。

**Plan review artifact path**: `docs/reviews/wu-cli-output-channels-plan-review-mimo-20260617.md`
