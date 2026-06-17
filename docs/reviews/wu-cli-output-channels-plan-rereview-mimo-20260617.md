# Plan Re-Review: WU CLI Output Channels

- **Reviewer**: AgentMiMo
- **Plan artifact（修订后）**: `docs/reviews/wu-cli-output-channels-plan-20260617.md`
- **Fix artifact**: `docs/reviews/wu-cli-output-channels-plan-fix-20260617.md`
- **原始 review**: `docs/reviews/wu-cli-output-channels-plan-review-mimo-20260617.md`
- **Work unit**: Dayu CLI 输出通道拆分
- **Re-review date**: 2026-06-17

## Re-Review Method

逐一核对 MiMo review 中 5 个 accepted findings 和 DS review 中 7 个 accepted findings，对照修订后 plan artifact 的对应段落，判断 fix 是否真正落地到 plan 的 code-generation-ready 规格中。

## MiMo Findings Status

### F001 — `--log-file` handler 生命周期精确时序未定义 — 已修复

**核对点**：

1. **finally 块中的精确时序** → 已落地。Slice A Exact changes（plan lines 220-225）：
   - "若非空，校验 strip 后非空，用 append + UTF-8 打开 path，并记录 `opened_log_file = True`"
   - "`finally` 中若 `opened_log_file` 为 `True`，必须先把 dayu logger 恢复到 stderr handler，再关闭文件"
   - "先调用 `runtime_log.set_level_from_flags(..., stream=sys.stderr)`（保持当前 level flag）或等价 `runtime_log.configure(..., stream=sys.stderr)`，再调用 `log_stream.close()`"
   - "恢复 stderr 与关闭文件的顺序不可反转；关闭后不得让 dayu logger 继续持有该 file stream"

2. **不默认改 runtime.log** → 已落地。Plan lines 226-228：
   - "不默认修改 `dayu/runtime/log.py`"
   - "修改必须只表达'关闭 Dayu 自有 marker handler'这一精确语义，不把 close 隐藏进职责不清的 helper"
   - "新增 runtime 测试必须证明重复配置 stderr 后 `sys.stderr` 未被关闭"

3. **异常路径测试** → 已落地。Plan lines 234-236：
   - "runner 抛出异常或返回错误码后，`finally` 仍先恢复 dayu logger 到 stderr handler，再关闭文件"
   - "一次 `main(... --log-file <tmp> ...)` 失败后，下一次不带 `--log-file` 的日志写入 stderr 不抛 `ValueError`，且不写入已关闭文件"

4. **implementation decisions 一致** → 已落地。Plan lines 177-179：
   - "固定顺序：若使用了文件 stream，先调用 `runtime_log.set_level_from_flags(..., stream=sys.stderr)` ...再关闭文件 stream"
   - "不把 `handler.close()` 泛化到 `_reset_marker_handlers` 等语义不清的 helper"

**结论**：handler 生命周期的精确 open → configure → finally(restore stderr → close file) 序列已 code-generation-ready。异常路径有明确测试覆盖要求。

---

### F002 — Slice C interactive TUI 改动范围过大 — 已修复

**核对点**：

1. **scope 降级** → 已落地。Plan non-goals（line 42）新增：
   - "不在本 work unit 中把运行态迁入 prompt_toolkit `Application.run_async()`，也不让 `PromptSession` 管理运行态 view"
   - "若 full-screen prompt_toolkit Application 是必要条件，停止 Slice C 并拆为后续独立 work unit"

2. **协议精简** → 已落地。Slice C Exact design（lines 308-315）：
   - 从原 7 方法（含 `read()`）缩减为 6 方法，且不再复制输入态 `InteractiveComposer.read()`
   - 新增 `ActivitySink` 窄接口分离 activity 记录职责
   - 文件名从 `tui.py` 改为 `run_view.py`，语义更精确

3. **非 full-screen 限制** → 已落地。Plan line 325：
   - "不得引入 prompt_toolkit `Application.run_async()` 或 PTY 依赖"

4. **stop condition** → 已落地。Plan line 333：
   - "若实现发现非 full-screen sink 不能满足 requirement...立即停止 Slice C：该重构是后续独立 work unit"

5. **测试策略简化** → 已落地。Plan line 342 不再要求 PTY 测试：
   - "run view unit test：纯内存 buffer 断言"

**结论**：Slice C 从"完整 prompt_toolkit TUI"降级为"非 full-screen 终端 sink + 窄协议"，scope 显著收窄，stop condition 明确。

---

### F003 — Ctrl+T 语义升级缺少迁移路径 — 已修复

**核对点**：

1. **新语义明确** → 已落地。Contract（plan line 144）：
   - "新语义下 Ctrl+T 不再调用 `CliActivityRenderer.toggle_visible()`，不再打印旧的 `Activity hidden: ...` 行；它只切换当前运行态 view，不触发 cancel"

2. **Slice C 实现细节一致** → 已落地。Plan line 324：
   - "Ctrl+T 新语义是 `transcript` 与 `activity` view 互切；不调用旧 `CliActivityRenderer.toggle_visible()`，不输出 `Activity hidden: ...`"

3. **测试覆盖** → 已落地。Plan line 342：
   - "Ctrl+T view switch 不输出旧的 `Activity hidden: ...` 行"

**结论**：Ctrl+T 从 toggle-visibility 升级为 view-switch 的语义跃迁已明确规格，旧行为的废弃有测试断言覆盖。

---

### F004 — `--detail` 与 TTY `isatty()` 交互未明确 — 已修复

**核对点**：

1. **构造方式明确** → 已落地。Slice B Exact changes（plan line 274）：
   - "`args.detail` 为 `True`：创建 `CliActivityRenderer(options=CliActivityRendererOptions(visible=True, enabled=True))`"

2. **activity 不进 log-file** → 已落地。Implementation decisions（plan line 184）：
   - "activity 仍走 UI activity sink 并写现有 activity stderr 通道，不进入 `--log-file`"

3. **非 TTY detail test** → 已落地。Slice B Tests（plan line 284）：
   - "新增非 TTY detail test：显式 `--detail` 时即使 stderr 非 TTY，也通过 `CliActivityRendererOptions(visible=True, enabled=True)` 输出 activity"

**结论**：`--detail` 绕过 `isatty()` 的精确构造方式和测试覆盖已明确。

---

### F005 — `--log-file` 测试 mocking 策略未指定 — 已修复

**核对点**：

1. **main spy 测试策略** → 已落地。Slice A Tests（plan lines 233-236）：
   - "main spy test 增加 `log_file` 默认仍 `stream=sys.stderr` 的断言，并新增 log_file 版本断言传入 file stream"
   - "main 异常路径测试：runner 抛出异常或返回错误码后，finally 仍先恢复 dayu logger 到 stderr handler，再关闭文件"

2. **Fins direct 测试策略** → 已落地。Plan lines 237-243：
   - "先读取 `tests/cli/test_fins_commands.py:442-461`、`:481-505` 确认捕获方式"
   - "若旧测试使用 `caplog`，保留旧测试，只新增文件 sink 测试"
   - "若旧测试直接断言 stderr 诊断，补充'无 log-file 时仍 stderr'的断言"

3. **Fins direct 新测试** → 已落地。Plan lines 238-239：
   - "`download --ticker AAPL --verbose --log-file <tmp>`：stdout 有 `Fins progress`，stderr 不含 `Fins direct command start`，文件含 VERBOSE 诊断"

**结论**：测试策略从"未指定"升级为有明确 mock 路径、异常路径覆盖、caplog/stderr 判断逻辑的完整规格。

---

## DS Findings Status

### DS F1 — interactive TUI running-state view 渲染机制在 prompt_toolkit 生命周期内无法自然承载 — 已修复

**核对点**：

1. **非目标新增** → 已落地。Plan line 42 明确排除 `Application.run_async()`。
2. **PromptSession 不管理运行态** → 已落地。Plan line 101："不让 prompt_toolkit `PromptSession` 管理运行态"。
3. **Stop condition** → 已落地。Plan line 333。
4. **方案选择** → 已落地。修订后 plan 选择 DS F1 的方案 A（非 prompt_toolkit 终端控制层），不引入 Application。

**结论**：DS F1 的核心风险（prompt_toolkit 生命周期冲突）通过 scope 降级和 stop condition 完全规避。

---

### DS F2 — `main()` log-file close 后 handler 顺序未显式指定 — 已修复

与 MiMo F001 同一修复。Slice A Exact changes lines 220-225 和 implementation decisions lines 177-179 已明确 open/reset/close 顺序。

---

### DS F3 — `_reset_marker_handlers` 调用 `close` 可能影响 `sys.stderr` — 已修复

**核对点**：

1. **runtime.log 默认不改** → 已落地。Plan lines 226-228："不默认修改 `dayu/runtime/log.py`"。
2. **精确测试要求** → 已落地。Plan line 228："新增 runtime 测试必须证明重复配置 stderr 后 `sys.stderr` 未被关闭，并证明文件 handler reset 后不再写已关闭 stream"。
3. **close 语义限制** → 已落地。Plan line 227："修改必须只表达'关闭 Dayu 自有 marker handler'这一精确语义"。

**结论**：通过"默认不改 + 精确测试约束"规避了 DS F3 的 `sys.stderr` 被关闭风险。

---

### DS F4 — prompt_toolkit TUI 单元测试策略缺失 — 已修复

**核对点**：

1. **非 full-screen sink** → 已落地。Slice C 不再需要 prompt_toolkit Application。
2. **测试策略简化** → 已落地。Plan line 342："run view unit test" 断言均为纯内存 buffer 操作，不依赖 PTY。
3. **无 PTY 依赖** → 已落地。Plan line 325："不得引入 prompt_toolkit `Application.run_async()` 或 PTY 依赖"。

**结论**：通过降级为非 full-screen sink，测试不再需要 PTY 基础设施。

---

### DS F5 — Fins direct 现有测试迁移策略不完整 — 已修复

**核对点**：

1. **caplog vs stderr 判断** → 已落地。Plan lines 240-243："先读取...确认捕获方式。若旧测试使用 `caplog`，保留旧测试，只新增文件 sink 测试。若旧测试直接断言 stderr 诊断，补充...'有 log-file 时诊断进入文件'的断言"。
2. **first-principles evidence 补充** → 已落地。Plan line 73："实施 Slice A 前必须先确认这些断言是 `caplog` 还是 stderr 捕获"。

**结论**：测试迁移策略从"笼统迁移"升级为"先确认捕获方式再决定保留或迁移"。

---

### DS F6 — `--log-file` append 并发写入无保护 — 已修复

**核对点**：

1. **implementation decisions** → 已落地。Plan line 174："多个进程并发写同一个 `--log-file` 不保证日志行原子性，可能交错；这是本轮接受的诊断日志限制，不加文件锁或 tee"。
2. **risks** → 已落地。Plan line 442："多进程并发写同一个 `--log-file` 可能导致日志行交错；本轮不加进程级文件锁，作为诊断日志限制接受"。

**结论**：并发写入限制已在 decisions 和 risks 中明确 acknowledge。

---

### DS F7 — `prompt --detail` enabled 契约未明确 — 已修复

与 MiMo F004 同一修复。Slice B Exact changes line 274 和 Tests line 284 已明确 `CliActivityRendererOptions(visible=True, enabled=True)` 和非 TTY 测试。

---

## Residual Risks

| Risk | 严重程度 | 处理方式 |
|------|---------|---------|
| 非 full-screen sink 的 UX 可能不满足最终交互预期 | 中 | 明确 stop condition：若需 full prompt_toolkit Application，拆为后续独立 work unit |
| 多进程并发写同一 `--log-file` 日志行交错 | 低 | 已作为诊断日志限制接受，不加锁 |
| `run_view.py` 的 `toggle_view()` 具体渲染策略（分隔线/清屏重绘）未在 plan 中指定 | 低 | 属于实现细节，implementation agent 可在非 full-screen 约束内自行选择 |
| 实施阶段可能发现 runtime handler close 仍需修改 `dayu/runtime/log.py` | 低 | plan 要求精确测试证明不关闭 `sys.stderr`，有安全约束 |
| Slice C 的 `ActivitySink` 与现有 `CliActivityRenderer` 的职责边界可能需要微调 | 低 | plan 已明确 `CliActivityRenderer` 保留为 prompt/plain CLI activity sink，`ActivitySink` 是 interactive run view 专用 |

## Conclusion

**全部 12 个 accepted findings（MiMo F001-F005 + DS F1-F7）均已修复。**

修订后 plan 的关键改进：

1. **F001/F2/F3**：`--log-file` handler 生命周期从"未定义"升级为有精确 finally 时序、异常路径测试、runtime.log 默认不改的安全规格。
2. **F002/F1/F4**：Slice C 从"完整 prompt_toolkit TUI"降级为"非 full-screen 终端 sink + 窄协议"，scope 收窄约 60%，stop condition 明确。
3. **F003**：Ctrl+T 语义跃迁有明确新旧行为规格和测试断言。
4. **F004/F7**：`--detail` 绕过 `isatty()` 的构造方式和非 TTY 测试已明确。
5. **F005/F5**：测试策略从"未指定"升级为有 mock 路径和 caplog/stderr 判断逻辑。
6. **F6**：并发写入限制已 acknowledge。

Plan 现在可以进入 user confirmation 和 implementation 阶段。

**Re-review artifact path**: `docs/reviews/wu-cli-output-channels-plan-rereview-mimo-20260617.md`
