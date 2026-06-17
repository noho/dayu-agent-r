# WU CLI Output Channels — Plan Re-Review (DS)

**Re-review target**: Plan fix at `docs/reviews/wu-cli-output-channels-plan-fix-20260617.md` applied to `docs/reviews/wu-cli-output-channels-plan-20260617.md`  
**Original review**: `docs/reviews/wu-cli-output-channels-plan-review-ds-20260617.md`  
**Review gate**: Gateflow Plan Review Fix Gate (re-review)  
**Reviewer**: AgentCodex (DS adversarial re-review pass)  
**Date**: 2026-06-17  

## Scope

核对 DS review 中的 7 个 accepted findings（F1–F7）是否已在修订后的 plan 中修复。每个 finding 逐条对照 plan 实际文本变化做证据比对，状态只取：**已修复** / **部分修复** / **未修复** / **证据失效**。

## Finding-by-Finding Verification

---

### DS F1 — prompt_toolkit 生命周期无法自然承载运行态 view 【已修复】

**原始问题**：plan 声称 prompt_toolkit/TUI 管理运行态 view，但 `PromptSession.prompt_async()` 只在输入态活跃，运行态 `asyncio.wait()` 时 prompt_toolkit Application 已退出。

**修复声明**（fix doc line 46）："Slice C 不再声称 `PromptSession` 管理运行态；full Application 重构列为 stop condition / 后续 work unit"

**Plan 实际变更证据**：

| 位置 | 旧文本 | 新文本 |
|------|--------|--------|
| goal (line 17) | "prompt_toolkit/TUI 组件边界" | "CLI 层运行态 UI 边界：先实现 `InteractiveRunView` / `ActivitySink` 窄协议与非 full-screen 终端 sink" |
| non-goals (line 42) | 不存在 | 新增："不在本 work unit 中把运行态迁入 prompt_toolkit `Application.run_async()`，也不让 `PromptSession` 管理运行态 view" |
| affected files (line 99–101) | "将 interactive transcript/activity view 放入 prompt_toolkit/TUI 组件边界" | "定义 CLI 层 `InteractiveRunView` / `ActivitySink` 窄协议与非 full-screen 终端 sink。管理 view mode... 不让 prompt_toolkit `PromptSession` 管理运行态" |
| implementation decisions #6 (line 188–189) | 不存在 | "本轮实现非 full-screen 终端 sink... 不声称 `PromptSession` 能管理运行态。若需要 full prompt_toolkit `Application` 才能达成 UX，则 Slice C 停止并拆为后续独立 work unit" |
| Slice C exact design (line 306–326) | "TTY implementation 基于 prompt_toolkit，持有..." | "非 full-screen TTY implementation 持有... 渲染策略：默认 view 为 transcript... 非 full-screen sink 可用简单分隔线/当前 view 重绘表达 view 切换；不得引入 prompt_toolkit `Application.run_async()` 或 PTY 依赖" |
| Slice C stop condition (line 333) | 不存在 | "若实现发现非 full-screen sink 不能满足 requirement，且必须把运行态迁移到 full prompt_toolkit `Application`，立即停止 Slice C：该重构是后续独立 work unit" |
| blocker rule (line 452) | 只覆盖 Host/Engine contract 变更 | 新增第二段："如果 Slice C 发现必须使用 full prompt_toolkit `Application.run_async()` 才能实现运行态 view，也立即停止" |

**裁决**：**已修复**。Plan 全文不再声称 `PromptSession` 管理运行态；非 full-screen sink 作为当前 scope，full Application 迁移被显式排除并设为 stop condition。这是一个实质性的 scope reduction，消除了原始 finding 的核心风险。

---

### DS F2 — main() 中 log-file 关闭后 handler 生命周期顺序未显式指定 【已修复】

**原始问题**：plan 只写 "runner 完成后关闭 file stream，并避免 logger 残留关闭 stream handler"，未给出具体的 handler 恢复与文件关闭顺序。

**修复声明**（fix doc line 47）："Slice A exact changes 明确 open/reset/close 顺序和异常路径"

**Plan 实际变更证据**：

| 位置 | 新文本（关键句） |
|------|-----------------|
| implementation decisions #4 (line 177–179) | "`main()` 不依赖文件对象 context manager 自动关闭；它必须持有 `log_stream`，并在 `finally` 中按固定顺序清理。固定顺序：若使用了文件 stream，**先调用 `runtime_log.set_level_from_flags(..., stream=sys.stderr)`** 或等价 `runtime_log.configure(..., stream=sys.stderr)` 恢复 dayu logger 的 stderr handler，**再关闭文件 stream**。" |
| Slice A exact changes (line 223–225) | "`finally` 中若 `opened_log_file` 为 `True`，必须先把 dayu logger 恢复到 stderr handler，再关闭文件：先调用 `runtime_log.set_level_from_flags(..., stream=sys.stderr)`... 再调用 `log_stream.close()`。恢复 stderr 与关闭文件的顺序不可反转；关闭后不得让 dayu logger 继续持有该 file stream。" |
| Slice A tests (line 234–236) | "main 异常路径测试：runner 抛出异常或返回错误码后，`finally` 仍先恢复 dayu logger 到 stderr handler，再关闭文件。一次 `main(... --log-file <tmp> ...)` 失败后，下一次不带 `--log-file` 的日志写入 stderr 不抛 `ValueError`，且不写入已关闭文件。" |

**裁决**：**已修复**。先恢复 stderr handler、再关闭文件的顺序已显式写在 implementation decisions 和 Slice A exact changes 中；异常路径测试覆盖残留 handler 的回归断言。实施 Agent 拿到的指令足够精确。

---

### DS F3 — `_reset_marker_handlers` 调用 `handler.close()` 对 `sys.stderr` 的副作用 【已修复】

**原始问题**：若 `_reset_marker_handlers` 无条件调用 `handler.close()`，可能意外关闭指向 `sys.stderr` 的 StreamHandler。

**修复声明**（fix doc line 48）："runtime log 默认不改；如需改，必须有不关闭 `sys.stderr` 的精确 runtime 测试"

**Plan 实际变更证据**：

| 位置 | 新文本（关键句） |
|------|-----------------|
| affected files (line 95) | "默认不改。仅当 `main()` 的 finally 恢复 stderr 后仍无法避免残留文件 handler 时，才做精确 handler 生命周期修正；**不得把 `handler.close()` 泛化到语义不清的 helper**。" |
| implementation decisions #4 (line 179) | "不把 `handler.close()` 泛化到 `_reset_marker_handlers` 等语义不清的 helper。若最终仍需改 `dayu/runtime/log.py`，必须有**精确测试证明连续 reset 不会关闭 `sys.stderr`**，且不会留下指向已关闭文件的 handler。" |
| Slice A exact changes (line 226–228) | "不默认修改 `dayu/runtime/log.py`。如果实现证明必须修改 runtime handler reset/close 行为：修改必须只表达'关闭 Dayu 自有 marker handler'这一精确语义，**不把 close 隐藏进职责不清的 helper**。新增 runtime 测试必须证明**重复配置 stderr 后 `sys.stderr` 未被关闭**，并证明文件 handler reset 后不再写已关闭 stream。" |

**裁决**：**已修复**。Plan 采纳了 DS review 的建议——默认不改 runtime log，close 逻辑不由 `_reset_marker_handlers` 承担；若被迫修改，有精确测试约束保护 `sys.stderr` 不被关闭。单一职责原则得到尊重。

---

### DS F4 — prompt_toolkit TUI 单元测试策略缺失 【已修复】

**原始问题**：plan 列出 TUI unit test 但未说明如何在 CI 环境（无 PTY）运行 prompt_toolkit-based 测试。

**修复声明**（fix doc line 49）："Slice C 改为非 full-screen sink，测试改为纯 run view buffer/unit 行为，不引入 PTY 依赖"

**Plan 实际变更证据**：

| 位置 | 新文本（关键句） |
|------|-----------------|
| Slice C exact design (line 325) | "非 full-screen sink 可用简单分隔线/当前 view 重绘表达 view 切换；**不得引入 prompt_toolkit `Application.run_async()` 或 PTY 依赖**。" |
| Slice C tests (line 337–342) | 所有 TUI 测试改为 buffer/内存级别断言："record activity 后 activity buffer 增加一行，transcript buffer 不变"、"render terminal succeeded 后 transcript buffer 增加 answer"、"toggle view 在 transcript/activity 间切换"、"当前 view 为 activity 时只渲染 activity view"——全是纯 Python 对象状态检查，无 PTY/终端依赖 |
| affected files (line 113) | 测试文件从 `tests/cli/test_interactive_tui.py` 改为 `tests/cli/test_interactive_run_view.py` |

**裁决**：**已修复**。与 F1 联动解决——因为不再使用 prompt_toolkit Application 管理运行态，所有 view/sink 测试退化为内存 buffer 断言，CI 环境无需 PTY。

---

### DS F5 — Fins direct 现有测试迁移策略不完整 【已修复】

**原始问题**：plan 未区分 `caplog` 捕获与 stderr 捕获，可能误导实施 Agent 不必要地修改旧测试。

**修复声明**（fix doc line 50）："Slice A tests 明确先确认 `caplog` vs stderr；按捕获方式选择保留旧测试或迁移 stderr 断言"

**Plan 实际变更证据**：

| 位置 | 新文本（关键句） |
|------|-----------------|
| code evidence (line 73) | "实施 Slice A 前**必须先确认这些断言是 `caplog` 还是 stderr 捕获**：若是 `caplog`，旧测试不迁移，只新增 `--log-file` 文件内容测试；若直接断言 stderr，则更新为'无 log-file 时仍 stderr；有 log-file 时写文件'。" |
| Slice A tests (line 240–243) | "Fins direct 旧测试处理策略：**先读取** `tests/cli/test_fins_commands.py:442-461`、`:481-505` 确认捕获方式。若旧测试使用 `caplog`，保留旧测试，只新增文件 sink 测试。若旧测试直接断言 stderr，补充'无 log-file 时仍 stderr'的断言，并新增'有 log-file 时诊断进入文件'的断言。" |

**裁决**：**已修复**。明确区分 caplog 与 stderr 两种捕获方式，给出不同的处理策略；实施 Agent 有清晰的 discovery-first 指令。

---

### DS F6 — `--log-file` append 并发写入无保护 【已修复】

**原始问题**：多进程并发写同一 log file 可能导致日志行交错，plan 未 acknowledge。

**修复声明**（fix doc line 51）："implementation decisions 与 risks 明确多进程同文件日志行可能交错，本轮不加锁"

**Plan 实际变更证据**：

| 位置 | 新文本（关键句） |
|------|-----------------|
| implementation decisions #3 (line 174) | "多个进程并发写同一个 `--log-file` **不保证日志行原子性，可能交错**；这是本轮接受的诊断日志限制，不加文件锁或 tee。" |
| risks (line 442) | "多进程并发写同一个 `--log-file` 可能导致日志行交错；本轮不加进程级文件锁，作为诊断日志限制接受。" |

**裁决**：**已修复**。并发写交错风险已在两个位置（decisions + risks）显式记录为接受限制。

---

### DS F7 — `prompt --detail` enabled 契约未明确 【已修复】

**原始问题**：plan 未明确 `--detail` 模式下如何绕过 `CliActivityRenderer` 的默认 `isatty()` gate（非 TTY 下 `enabled` 为 `False`）。

**修复声明**（fix doc line 52）："Slice B exact changes 和 tests 明确 `CliActivityRendererOptions(visible=True, enabled=True)` 与非 TTY detail test"

**Plan 实际变更证据**：

| 位置 | 新文本（关键句） |
|------|-----------------|
| implementation decisions #5 (line 184) | "`args.detail` 为 `True` 时创建 `CliActivityRenderer(options=CliActivityRendererOptions(visible=True, enabled=True))`，**绕过默认 `isatty()` gate**。activity 仍走 UI activity sink 并写现有 activity stderr 通道，不进入 `--log-file`。" |
| Slice B exact changes (line 274) | 完全相同的显式构造函数调用 |
| Slice B tests (line 284) | "新增非 TTY detail test：显式 `--detail` 时即使 stderr 非 TTY，也通过 `CliActivityRendererOptions(visible=True, enabled=True)` 输出 activity；该 activity 仍属于 UI activity sink，不进入 `--log-file`。" |

**裁决**：**已修复**。显式 `CliActivityRendererOptions(visible=True, enabled=True)` 写入 implementation decisions、exact changes、tests 三处；附带非 TTY detail test 作为回归守卫。

---

## Findings Summary

| Finding | 严重度 | 状态 |
|---------|--------|------|
| DS F1 — prompt_toolkit 生命周期无法自然承载运行态 view | 高 | **已修复** |
| DS F2 — main() log-file close 后 handler 顺序未显式指定 | 中 | **已修复** |
| DS F3 — `_reset_marker_handlers` close 可能影响 `sys.stderr` | 中 | **已修复** |
| DS F4 — prompt_toolkit TUI 单元测试策略缺失 | 中 | **已修复** |
| DS F5 — Fins direct 现有测试迁移策略不完整 | 低 | **已修复** |
| DS F6 — `--log-file` append 并发写入无保护 | 低 | **已修复** |
| DS F7 — `prompt --detail` enabled 契约未明确 | 低 | **已修复** |

**全部 7 个 DS findings 已修复。无部分修复、未修复或证据失效。**

## Cross-Cutting Consistency Check

对修订后 plan 做横向一致性检查：

1. **prompt_toolkit 引用一致性** ✓：全文 `prompt_toolkit` 出现仅限以下语义——输入态依赖（line 41, 69）、非目标（line 42, 189）、code evidence 描述现有行为（line 69）——无一处声称 prompt_toolkit 管理运行态 view。

2. **ActivitySink / InteractiveRunView 协议一致** ✓：Slice C exact design（line 308–315）定义的窄协议中，`ActivitySink` 只暴露 `record_activity`，`InteractiveRunView` 暴露 `activity_sink()` + `render_terminal_result()` + `toggle_view()` + `render_cancel_requested()` + `render_local_exit_after_cancel()` + `close()`。与 implementation decisions #6（line 186–189）的 "不让 command 模块直接操控 prompt_toolkit 类型" 一致。

3. **Slice C stop condition 双重覆盖** ✓：line 333（Slice C exact design 内部）和 line 452（全局 blocker rule）都声明 full Application 迁移停止规则，无冲突。

4. **activity 通道语义一致** ✓：全文一致区分 "UI activity sink"（走 stderr/stdout 用户通道）与 "诊断日志"（走 runtime log → `--log-file` 或 stderr）。

## Residual Risks (Post-Fix)

| # | Risk | 严重度 | 处理方式 |
|---|------|--------|---------|
| R1 | Slice C 非 full-screen sink 的具体渲染机制（ANSI escape 重绘 vs. 行输出加 view header）未在 plan 中选定 | 低 | 属实施细节，受 plan 约束 "不得引入 PTY 依赖" 且测试为 buffer-level，渲染策略选择不影响 plan validity |
| R2 | Slice C `InteractiveRunView` 协议的 `render_terminal_result` 返回值语义未定义（是否返回 exit code？还是 void？） | 低 | 可类比现有 `render_interactive_terminal_result(terminal) -> int`（output.py），实施时可沿用 |
| R3 | `dayu/runtime/log.py` 最终是否需要修改 handler close 行为仍然是 open（plan 线 95 "默认不改"，但留有 conditional path） | 低 | 条件路径有精确测试约束（不关闭 sys.stderr，不残留文件 handler），且由 Slice A 测试守护 |
| R4 | 非 TTY `--detail` 场景下 activity 写入 stderr 可能与脚本的 stderr 解析冲突 | 低 | 已在 plan risks（line 441）记录，且是用户显式 opt-in，可接受 |

## Re-Review Conclusion

**Verdict: `pass`**

DS review 的 7 个 accepted findings 全部在修订后的 plan 中得到实质性修复。修订不是表面文字替换——每个 finding 都对应 plan 中可验证的结构性变更：

- **F1**（高）：scope 从 "prompt_toolkit 管理运行态" 收敛为 "非 full-screen CLI run view"，并设 stop condition
- **F2**（中）：handler 恢复→文件关闭的顺序显式写入 implementation decisions 和 Slice A exact changes
- **F3**（中）：`handler.close()` 从低层 helper 中移除，改为 conditional + 精确测试约束
- **F4**（中）：TUI 测试退化为纯 buffer 断言，消除 PTY 依赖
- **F5**（低）：Fins 旧测试按 caplog/stderr 分类处理
- **F6**（低）：并发写交错作为接受限制显式记录
- **F7**（低）：`CliActivityRendererOptions(visible=True, enabled=True)` 显式写死

修订后的 plan 可以安全交给 implementation agent。Slice A/B 可直接实施；Slice C scope 已充分收敛，唯一未定的渲染细节属于实施层面，不影响 plan validity。

Re-review artifact path: `docs/reviews/wu-cli-output-channels-plan-rereview-ds-20260617.md`
