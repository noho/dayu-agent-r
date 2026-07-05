# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-cancel-01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-code-review-mimo.md`
- Included scope: `dayu/tools/web/web_playwright_backend.py`, `tests/tools/web/test_web_tools_provider.py`, `tests/README.md`, `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-implementation-codex.md`
- Excluded scope: S1/S2A/S3/S4 改动不在本次 review 范围内
- Parallel review coverage: 无

## Findings

### 01-未修复-中-`asyncio.run()` 在 sync cleanup 路径中重复创建事件循环

- **入口/函数**: `_terminate_playwright_process` (`dayu/tools/web/web_playwright_backend.py:433`)
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:446, 454`
- **输入场景**: Playwright raw worker 进程存活、需要 terminate-then-kill 两阶段 cleanup
- **实际分支**: terminate 阶段调用 `asyncio.run(interrupt_multiprocessing_process(...))`，若进程仍存活，kill 阶段再次调用 `asyncio.run(...)`
- **预期行为**: cleanup 路径应可靠调用 `interrupt_multiprocessing_process` async primitive；当前 sync call path 不应引入未来调用上下文限制
- **实际行为**: 两次 `asyncio.run()` 各自创建并销毁独立事件循环。功能正确，但存在两个问题：(1) 如果未来 `_run_playwright_worker_process` 被从 async 上下文调用，`asyncio.run()` 会抛 `RuntimeError: asyncio.run() cannot be called from a running event loop`；(2) 重复创建事件循环的开销虽小但不必要
- **直接证据**: `web_playwright_backend.py:446` 和 `web_playwright_backend.py:454` 各调用一次 `asyncio.run(interrupt_multiprocessing_process(...))`；`interrupt_multiprocessing_process` 使用 `asyncio.to_thread(process.join, grace_seconds)` 做 bounded wait
- **影响**: 当前 sync call path（`_try_playwright_fallback` → `_fetch_and_convert_with_playwright` → `_run_playwright_worker_process` → `_terminate_playwright_process`）功能正确。但如果任何未来调用方从 async 上下文进入此路径，cleanup 会崩溃。这是一个 latent coupling：sync-only 约束不在类型系统中表达
- **建议改法和验证点**: 在 `_terminate_playwright_process` 内部用 `asyncio.get_event_loop().run_until_complete(...)` 替代 `asyncio.run()`，或抽取一个 sync wrapper 检查 `asyncio.get_running_loop()` 是否存在来决定使用哪个策略。最小改动：在函数 docstring 中显式记录 "本函数只能从非 async 上下文调用" 约束
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 02-未修复-低-测试 timing assertion 使用了与生产不同的常量来源

- **入口/函数**: `test_playwright_worker_process_cleanup_kills_synthetic_nested_child_on_posix` (`tests/tools/web/test_web_tools_provider.py:1530`)
- **文件(行号)**: `tests/tools/web/test_web_tools_provider.py:1585-1590`
- **输入场景**: synthetic nested child cleanup timing 验证
- **实际分支**: 测试断言 `terminate_result.elapsed_seconds <= ProcessCapsuleInterruptPolicy().terminate_grace_seconds`（默认 0.2s）和 `cleanup_elapsed_seconds <= ProcessCapsuleInterruptPolicy().terminate_grace_seconds`（默认 0.2s）
- **预期行为**: timing assertion 应与生产代码使用的 cleanup grace 常量对齐，确保断言验证的是生产行为而非巧合
- **实际行为**: 生产代码 `_terminate_playwright_process` 使用 `_PW_PROCESS_TERMINATE_GRACE_SECONDS = 1.0` 作为 grace_seconds，但测试断言使用 `ProcessCapsuleInterruptPolicy().terminate_grace_seconds = 0.2`。测试通过是因为 synthetic child 在 SIGTERM 后立即退出（实现 codex 报告 0.002s），远低于两个阈值。但如果将来生产 grace 调小到 0.1s 而 policy 默认不变，测试仍通过但不再验证生产阈值
- **直接证据**: `web_playwright_backend.py:316` 定义 `_PW_PROCESS_TERMINATE_GRACE_SECONDS = 1.0`；`web_playwright_backend.py:450` 使用该常量；`test_web_tools_provider.py:1585-1590` 断言使用 `ProcessCapsuleInterruptPolicy().terminate_grace_seconds`
- **影响**: 测试仍然有效（验证了 cleanup 完成且 elapsed 在合理范围内），但 assertion 与生产常量来源不同，削弱了 "timing 验证生产行为" 的证据力
- **建议改法和验证点**: 将测试中的 timing assertion 改为 `assert terminate_result.elapsed_seconds <= web_playwright_backend._PW_PROCESS_TERMINATE_GRACE_SECONDS`，或在测试中显式注释说明 "使用 policy 默认值作为宽松上界，生产 grace 为 1.0s"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

- **real Chromium process tree cleanup 未被 synthetic smoke 覆盖**: synthetic nested child 是 `subprocess.Popen(sys.executable, ["-c", "time.sleep(60)"])`，不涉及真实浏览器进程树。真实 Chromium 可能有多层嵌套子进程（browser process → renderer → GPU process），其 process-group 归属行为可能与 synthetic child 不同。实现 codex 和 tests/README.md 已诚实记录此限制。分类：按计划由 S4 或后续 optional/manual live browser smoke 覆盖
- **PID/PGID reuse race**: POSIX signal 层面的已知限制，S2A 已记录，S2B 未扩大
- **`asyncio.run()` sync-only 约束**: 见 Finding 01。当前调用链全部为 sync，但约束不在类型系统中表达
- **Windows 平台**: 测试在 `os.name != "posix"` 时 skip，`enter_new_process_session_if_supported()` 在非 POSIX 返回 False。Windows 上只能 claim direct-child fallback，nested cleanup 未验证。测试正确处理了这种情况

## Review Verification Summary

按用户要求的六个重点审查点逐项结论：

1. **Web raw worker child session setup**: ✅ `_playwright_process_entry` 在 L407 首行调用 `enter_new_process_session_if_supported()`，位于 worker callable 执行之前。Host/main process 不会调用此函数。与 S2A 的 `_run_process_target` 模式一致
2. **`_terminate_playwright_process` 复用 `interrupt_multiprocessing_process`**: ✅ 只调用共享 primitive，未复制 process-group logic。`asyncio.run()` 在当前 sync call path 安全（见 Finding 01 的 latent 风险）
3. **Cleanup diagnostic claim 准确性**: ✅ unsupported/unsafe 时测试 skip 而非 over-claim；`GROUP_SIGNALED` 时 nested PID 确实通过 `_wait_for_pid_absent` 验证消失
4. **Synthetic smoke deterministic**: ✅ 使用文件-backed PID 通信、polling 读取、explicit timeout、finally cleanup。timing assertion 合理（见 Finding 02 的常量来源差异）
5. **Live browser optional smoke**: 当前未添加，residual risk 已诚实记录，符合计划 "covered by later approved slice S4 or assigned to later work"
6. **Web process cold-start**: S2B 改动未触及 cold-start 逻辑，仅替换 cleanup helper。cold-start 仍为 performance-only，未削弱 cancellation robustness

## Conclusion

**PASS_WITH_FINDINGS**

S2B 实现正确完成了计划目标：Playwright raw worker cleanup 复用 S2A 共享 primitive，session setup 在正确位置，synthetic smoke deterministic 且 cleanup diagnostic claim 准确。两个 findings 均为中/低严重程度，不阻塞当前 slice commit。
