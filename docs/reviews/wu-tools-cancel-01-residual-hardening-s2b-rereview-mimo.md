# Code Re-Review — WU-TOOLS-CANCEL-01 S2B After AgentCodex Fix

## Scope

- Mode: targeted re-review
- Branch: `phase/wu-tools-cancel-01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-rereview-mimo.md`
- Included scope: `dayu/tools/web/web_playwright_backend.py`, `tests/tools/web/test_web_tools_provider.py`, `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-implementation-codex.md`
- Excluded scope: S1/S2A/S3/S4
- Parallel review coverage: 无

## Previous MiMo Findings Closure

### MiMo 01 — `asyncio.run()` 在 sync cleanup 路径中重复创建事件循环

**状态：已关闭。**

AgentCodex 引入 `_interrupt_playwright_process_sync` (`web_playwright_backend.py:476`) 作为 sync bridge。该函数：

1. 调用 `_thread_has_running_asyncio_loop()` 检查当前线程是否有 running event loop (`web_playwright_backend.py:434`)
2. 无 running loop 时直接 `asyncio.run(...)` (`web_playwright_backend.py:496`)
3. 有 running loop 时在短生命周期 helper thread 中运行 `asyncio.run(...)` (`web_playwright_backend.py:504-511`)，通过 `Queue` 回传结果或异常 (`web_playwright_backend.py:512-518`)

新增测试 `test_playwright_worker_process_cleanup_supports_running_event_loop` (`test_web_tools_provider.py:1642`) 验证从 async 上下文调用 cleanup 路径仍能正常工作。该测试通过 `asyncio.run(_terminate_process_inside_running_loop(process))` 模拟从 running event loop 中调用同步 cleanup 函数。

**验证**: helper thread 使用 `daemon=True`、`Queue(maxsize=1)`、`join()` 阻塞等待、异常通过 queue 原样传播。结构正确。

### MiMo 02 — 测试 timing assertion 使用了与生产不同的常量来源

**状态：已关闭。**

测试断言已改为使用 `web_playwright_backend._PW_PROCESS_TERMINATE_GRACE_SECONDS` (`test_web_tools_provider.py:1625-1630`)，与生产代码 `_terminate_playwright_process` 使用的 grace 常量 (`web_playwright_backend.py:567`) 同源。

## Previous DS Findings Closure

### DS 01 — `asyncio.run()` 在 sync 函数中为结构性脆弱点

**状态：已关闭。** 同 MiMo 01。sync bridge 解决了 running event loop 限制问题。

### DS 02 — Cleanup 诊断在生产中被静默丢弃

**状态：已关闭。**

`_terminate_playwright_process` 现在在每个 cleanup 阶段后调用 `_log_playwright_process_cleanup_stage` (`web_playwright_backend.py:569-572, 579-582`)。该函数以 `Log.debug` 级别记录 `reason`、`direct_signal_sent`、`group_signal_sent`、`exited`、`exitcode`、`elapsed_seconds`，不记录 URL/内容/headers (`web_playwright_backend.py:521-548`)。

测试 `test_playwright_worker_process_cleanup_kills_synthetic_nested_child_on_posix` 通过 `caplog` 验证日志输出 (`test_web_tools_provider.py:1621-1622`)：
```python
assert "reason=group_signaled" in caplog.text
assert "group_signal_sent=True" in caplog.text
```

**验证**: 日志记录点在 `_terminate_playwright_process` 内部而非调用方，比 DS 建议的方案更内聚——cleanup 诊断的产生和记录在同一函数内，调用方不需要关心日志。

### DS 03 — 测试 timing assertion 使用错误的参照 grace 值

**状态：已关闭。** 同 MiMo 02。

### DS 04 — 缺少 optional live browser cleanup smoke

**状态：已关闭。**

新增测试 `test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort` (`test_web_tools_provider.py:1685`)：

- 默认 skip，需 `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1` 环境变量显式开启
- POSIX-only，通过 `_live_playwright_chromium_available()` 探测 Chromium binary
- 使用 `_LiveBrowserLongRunningWorker` 启动真实 Chromium（`playwright.sync_api.sync_playwright`）
- 通过 `_process_table_from_ps()` / `_descendant_pids()` 观测进程树
- terminate 后验证 observed descendants 消失
- finally 块中 `_kill_remaining_pids()` 清理任何残存进程

实现 codex 报告 `DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest ...` 在当前环境通过。

## New Additions Review

### Sync bridge (`_interrupt_playwright_process_sync`)

**未发现新问题。**

- `_thread_has_running_asyncio_loop` 使用 `asyncio.get_running_loop()` (Python 3.7+)，正确检测 running loop
- helper thread 中 `asyncio.run()` 创建独立事件循环，与主线程隔离
- `Queue(maxsize=1)` 确保单结果语义；`helper_thread.join()` 阻塞直到 thread 结束
- `isinstance(message, BaseException)` 分支正确传播 helper thread 异常
- daemon thread 不影响主进程退出——但此处通过 `join()` 显式等待，daemon 属性仅是安全网

### Debug cleanup logging (`_log_playwright_process_cleanup_stage`)

**未发现新问题。**

- `Log.debug` 级别不影响生产性能
- 不记录 URL/内容/headers，符合 LLM-facing 文本约束
- 测试通过 `caplog` 验证日志内容，确保诊断信息确实被记录

### Manual live browser smoke

**未发现新问题。**

- 环境变量守卫 (`DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1`) 默认跳过，不影响 CI
- 多层 skip 逻辑（env var → POSIX → Chromium available → ps available）正确
- `_LiveBrowserLongRunningWorker` 中 `from playwright.sync_api import sync_playwright` 为子进程内 lazy import，不影响 pickle
- `_process_table_from_ps` 使用 `ps -axo pid=,ppid=`，timeout 2.0s，异常返回 None
- `_descendant_pids` 使用 BFS 遍历进程树，正确处理循环引用（`if pid in descendants: continue`）
- finally 块中 `_kill_remaining_pids` 确保测试不会泄漏 Chromium 子进程

## Open Questions

- 无。

## Residual Risk

- **真实 Chromium process tree cleanup 仍为环境依赖**: live smoke 通过 POSIX `ps` 观测进程树，依赖 `ps` 的 Chromium subprocess 可见性。某些 Chromium 版本或配置下子进程可能使用不同的进程树结构。实现 codex 已诚实记录此限制
- **PID/PGID reuse race**: S2A 已记录的 POSIX 信号限制，S2B 未扩大

## Conclusion

**PASS**

所有先前 findings（MiMo 01/02、DS 01/02/03/04）均已正确关闭。新增的 sync bridge、debug cleanup logging、manual live browser smoke 未引入新的 correctness/architecture/test 问题。S2B 可以进入 controller adjudication。
