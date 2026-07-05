# WU-TOOLS-CANCEL-01 Residual Hardening S2B Code Review — AgentDS

## Verdict

**PASS_WITH_FINDINGS** — 两个 MEDIUM findings 和一个 LOW finding 需要在 merge 前裁决或记录；无 BLOCK 级缺陷。

## Scope

- **Mode**: current changes (workspace uncommitted diff only)
- **Branch**: `phase/wu-tools-cancel-01`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-code-review-ds.md`
- **Included scope**:
  - `dayu/tools/web/web_playwright_backend.py` — S2B Playwright cleanup 实现
  - `tests/tools/web/test_web_tools_provider.py` — S2B 新增 synthetic nested child cleanup 测试
  - `tests/README.md` — Playwright raw worker cleanup 覆盖说明更新
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2b-implementation-codex.md` — Codex 实现报告
- **Excluded scope**: 已提交的 S1/S2A commits、S2B 前一轮 Doc process-backed（已 controller-accepted）、Web tools.py（本次未改动）、其他未修改文件
- **Context truth documents**: `docs/host/wu-tools-cancel-01-residual-hardening-plan.md`（S2B 章节）、`docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-controller-adjudication.md`、`dayu/runtime/interruptible_process.py`（S2A primitive）、`dayu/tools/web/web_tools.py`（Playwright fallback 调用链）、S2B implementation codex

## Execution Walkthrough

### 主链路：生产 Playwright cleanup

1. **`fetch_web_page`**（`web_tools.py:1255`，`async def`）→ `await _call_fetch_web_page(...)`（`web_tools.py:1420`，`async def`）
2. `_call_fetch_web_page` → `await asyncio.to_thread(_fetch_web_page_business, ...)`（`web_tools.py:1475`）— **整个 fetch 业务逻辑在 thread pool worker 线程中运行，该线程无 event loop** ✓
3. `_fetch_web_page_business`（`web_tools.py:1817`，sync）→ `_try_playwright_fallback`（`web_tools.py:866`，sync）→ `web_playwright_backend._fetch_and_convert_with_playwright`（sync）→ `_run_playwright_worker_process`（sync）
4. Playwright worker 子进程通过 `ctx.Process(target=_playwright_process_entry, ...)` 启动（`web_playwright_backend.py:539-544`）
5. **子进程入口** `_playwright_process_entry`（`web_playwright_backend.py:388`）→ 调用 `enter_new_process_session_if_supported()`（line 407）— **在 worker callable 执行前进入独立 POSIX session** ✓
6. 取消/超时时：`_terminate_playwright_process(process)` → `asyncio.run(interrupt_multiprocessing_process(process, signal_kind=TERMINATE, grace_seconds=1.0))` — **在 thread pool worker 线程中调用，无 running event loop，`asyncio.run()` 创建新 loop** ✓（但见 Finding 01）
7. `interrupt_multiprocessing_process`（S2A primitive）→ 向直接子进程发 SIGTERM → 安全解析子进程 pgid → 若 pgid 与当前/父进程组不同，则 `os.killpg(child_pgid, SIGTERM)` → `process.join(grace_seconds=1.0)` ✓
8. 若进程仍存活 → 第二阶段的 `interrupt_multiprocessing_process(process, signal_kind=KILL, grace_seconds=1.0)` ✓
9. **Finally 块**（`web_playwright_backend.py:581-584`）再次检查 `process.is_alive()` 并 cleanup → queue close/joint_thread ✓

### 关键判断点

- **`process.daemon = True`**（line 543）：安全网，父进程退出时 OS 会回收 daemon 子进程 ✓
- **queue close**（line 584）：在 finally 块中调用 `_close_playwright_result_queue`，close + join_thread 在 except-pass 包裹下执行 ✓
- **`enter_new_process_session_if_supported()` 位置**：在 `_playwright_process_entry` 开头（line 407），在 worker callable 执行和任何嵌套子进程启动之前 ✓
- **S2A 共享 primitive 复用**：Web backend 只通过 `interrupt_multiprocessing_process` + `enter_new_process_session_if_supported` 使用 runtime，不重复 process-group logic ✓

### Architecture boundary check

- `dayu.tools.web → dayu.runtime.interruptible_process`：tools → runtime 方向正确，runtime 是层中立基础设施 ✓
- 无 `dayu.tools.web → dayu.host` import ✓
- 无 `dayu.runtime → dayu.tools` reverse import ✓
- `dayu.tools.web` 不导入 Host/Engine/Service/UI/Fins ✓

## Findings

### 01-NEEDS_FIX-MEDIUM-`asyncio.run()`在sync函数中为结构性脆弱点

- **入口/函数**: `_terminate_playwright_process()`
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:446-461`
- **输入场景**: 任何从 running event loop 所在线程直接调用 `_terminate_playwright_process` 的路径
- **实际分支**: 函数体内 `asyncio.run(interrupt_multiprocessing_process(...))`（line 446-451 和 454-459）— 在 terminate 和 kill 两个阶段各调用一次
- **预期行为**: 函数应在任何合理的调用上下文中正常工作
- **实际行为**: 当前在生产中工作正常，因为唯一生产调用链经过 `asyncio.to_thread(_fetch_web_page_business, ...)`（`web_tools.py:1475`），该函数在 thread pool worker 线程中运行，无 running event loop。`asyncio.run()` 在该线程中成功创建新 event loop。但如果未来任何人：
  1. 重构 `_call_fetch_web_page` 移除 `asyncio.to_thread` 包装
  2. 新增一个从 async context 直接调用 `_terminate_playwright_process` 的路径
  3. 在 `@pytest.mark.asyncio` 测试中调用此函数

  则会触发 `RuntimeError: asyncio.run() cannot be called from a running event loop`。

  此外，`asyncio.run()` 每次调用创建并销毁一个全新的 event loop（terminate + kill 两个阶段最多创建 2 个 loop），虽然功能正确但浪费。

- **直接证据**:
  - `web_playwright_backend.py:446-451`: `cleanup["terminate"] = asyncio.run(interrupt_multiprocessing_process(...))` — 第一次 `asyncio.run()`
  - `web_playwright_backend.py:454-459`: `cleanup["kill"] = asyncio.run(interrupt_multiprocessing_process(...))` — 第二次 `asyncio.run()`
  - `interruptible_process.py:440`: `async def interrupt_multiprocessing_process(...)` — S2A primitive 是 async
  - `web_playwright_backend.py:433-440`: docstring 未提及调用上下文约束（"不得在有 running event loop 的线程中调用"）
  - `web_tools.py:1475`: `await asyncio.to_thread(_fetch_web_page_business, ...)` — 生产调用者使用 thread offloading，这是当前正确性的唯一保障
- **影响**: 结构性脆弱而非当前 bug。若未来调用上下文改变，会在运行时崩溃，且 cleanup 路径的失败可能导致 Playwright worker 进程泄漏。
- **建议改法和验证点**:
  1. **最小方案（本轮可接受）**：在 `_terminate_playwright_process` docstring 中明确声明调用约束："本函数内部使用 `asyncio.run()`，必须在无 running event loop 的线程中调用；生产路径当前通过 `asyncio.to_thread()` 保证此约束。"
  2. **更健壮的方案**：使用 `try/except RuntimeError` 包裹 `asyncio.run()`，捕获 "cannot be called from a running event loop" 错误后回退到 `loop.run_until_complete()` 或在新线程中执行
  3. **理想方案**：提供一个同步版本的 `interrupt_multiprocessing_process`（runtime 层），或让 Web backend 直接调用同步 primitive，避免 sync→async→sync 的往返
- **修复风险（低）**: 最小方案仅添加文档，零风险。方案 2/3 需要在 runtime 层或 Web backend 做结构性调整。
- **严重程度（中）**:

---

### 02-NEEDS_FIX-MEDIUM-Cleanup诊断在生产中被静默丢弃

- **入口/函数**: `_run_playwright_worker_process()`
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:550, 557, 583`
- **输入场景**: 任何触发 `_terminate_playwright_process` 的生产路径：取消、超时、finally 兜底
- **实际分支**: 三个调用点均丢弃 `_terminate_playwright_process` 的返回值（`_PlaywrightProcessCleanup` TypedDict），不做任何日志记录或诊断上报
- **预期行为**: 进程组 cleanup 诊断（`ProcessGroupCleanupResult`）包含 `reason`、`group_signal_sent`、`direct_signal_sent` 等关键字段，应在 debug 级别记录，以便在生产中排查进程组清理是否降级为 direct-child fallback
- **实际行为**: S2A primitive 返回了丰富的 cleanup 诊断，但生产代码完全不消费。如果某次部署中 `os.setsid()` 静默失败导致进程组清理不可用，或 pgid 匹配父进程组导致 group signal 被跳过，生产日志中没有任何线索
- **直接证据**:
  - `web_playwright_backend.py:550`: `_terminate_playwright_process(process)` — 取消路径丢弃返回值
  - `web_playwright_backend.py:557`: `_terminate_playwright_process(process)` — 超时路径丢弃返回值
  - `web_playwright_backend.py:583`: `_terminate_playwright_process(process)` — finally 路径丢弃返回值
  - `web_playwright_backend.py:433-440`: `_terminate_playwright_process` 返回 `_PlaywrightProcessCleanup` 有完整类型定义
  - 对比：`interruptible_process.py:216-232`: `ProcessInterruptResult` 的 `cleanup` 字段包含 `ProcessGroupCleanupResult`，但生产链路中没有消费这个字段的代码
- **影响**: 可观测性缺口。进程组清理在生产中退化为 direct-child fallback 时无法感知。不直接影响功能正确性（direct-child fallback 是安全行为），但让 S2A 的诊断能力在 Web 路径中被浪费。
- **建议改法和验证点**:
  1. 在 `_run_playwright_worker_process` 中捕获 `_terminate_playwright_process` 返回值，以 debug 级别记录 `cleanup["terminate"].cleanup.reason` 和 `cleanup["kill"].cleanup.reason`
  2. 或在 `_terminate_playwright_process` 内部直接记录 debug 日志（将日志记录内置到 cleanup 函数中）
- **修复风险（低）**: 纯日志补充，不影响行为
- **严重程度（中）**:

---

### 03-NEEDS_FIX-LOW-测试中的timing assertion使用错误的参照grace值

- **入口/函数**: `test_playwright_worker_process_cleanup_kills_synthetic_nested_child_on_posix`
- **文件(行号)**: `tests/tools/web/test_web_tools_provider.py:1585-1590`
- **输入场景**: synthetic nested child 对 SIGTERM 响应稍慢（但仍在 1.0s grace 内），CI 机器负载较高
- **实际分支**: 断言行
  ```python
  assert terminate_result.elapsed_seconds <= ProcessCapsuleInterruptPolicy().terminate_grace_seconds  # 0.2s
  assert cleanup_elapsed_seconds <= ProcessCapsuleInterruptPolicy().terminate_grace_seconds           # 0.2s
  ```
- **预期行为**: 应使用实际传给 primitive 的 grace 值（`_PW_PROCESS_TERMINATE_GRACE_SECONDS = 1.0`）做 functional correctness 判断；或单独用一个不依赖 grace 参数的测量来验证 policy defaults
- **实际行为**: `ProcessInterruptResult.elapsed_seconds` 包含 `process.join(grace_seconds=1.0)` 的等待时间。若 join 耗时接近 grace（例如进程对 SIGTERM 响应稍慢），`elapsed_seconds` 可能 > 0.2s 但 < 1.0s。断言会失败，但这不是功能缺陷——cleanup 在 1.0s grace 内完成是正确的行为。当前开发机上 synthetic child 在 ~0.002s 内退出，因此断言通过，但这是一个语义不正确的耦合。

  此外，`cleanup_elapsed_seconds` 还包含 `asyncio.run()` 的 event loop 创建/销毁开销。在负载较高的 CI 机器上，仅 `asyncio.run()` 开销就可能接近或超过 0.2s，导致本不相关的性能波动触发 false negative。

- **直接证据**:
  - `web_playwright_backend.py:316`: `_PW_PROCESS_TERMINATE_GRACE_SECONDS = 1.0` — 实际传给 primitive 的 grace
  - `web_playwright_backend.py:450`: `grace_seconds=_PW_PROCESS_TERMINATE_GRACE_SECONDS` — terminate 阶段使用 1.0s
  - `interruptible_process.py:492`: `await asyncio.to_thread(process.join, grace_seconds)` — elapsed 受 grace 值约束
  - `tests/tools/web/test_web_tools_provider.py:1585-1590`: 断言使用 0.2s 而非 1.0s
  - Implementation codex 测量: `terminate_elapsed_seconds=0.002388` — 当前环境通过，但不保证泛化
- **影响**: 低概率 flaky test。在 CI 机器负载高或 OS 信号调度慢时可能出现 false negative。不影响生产行为。
- **建议改法和验证点**:
  1. **首要**：将 `cleanup_elapsed_seconds` 的断言改为 `<= _PW_PROCESS_TERMINATE_GRACE_SECONDS`（1.0s），因为它测量的是 `_terminate_playwright_process` 的总 wall-clock 时间
  2. **次要**：将 plan 要求的"验证 policy defaults"改为一个独立的断言维度——例如测量从 SIGTERM 发送到子进程退出的实际时间（不含 join grace），与 `ProcessCapsuleInterruptPolicy().terminate_grace_seconds` 比较
  3. 或在测试注释中说明当前断言在 0.2s 内的前提（synthetic `sleep 60` 子进程对 SIGTERM 响应极快），并接受小概率 flaky risk
- **修复风险（低）**: 纯测试修改
- **严重程度（低）**:

---

### 04-NEEDS_FIX-LOW-缺少optional live browser cleanup smoke

- **入口/函数**: plan S2B "Exact changes" 第 5 条
- **文件(行号)**: 无对应实现（缺失项）
- **输入场景**: 环境中 Playwright Chromium binary 可用（implementation codex 确认 `playwright_chromium_launch=available`）
- **实际分支**: 未实现
- **预期行为**: plan 要求 "If real Playwright browser binaries are available, add an optional/manual/live smoke or skipped test that launches a real browser path and verifies no surviving Chromium subprocesses after cleanup."
- **实际行为**: implementation codex 说明 "No optional/manual live browser cleanup smoke was added in this slice." 理由是 "Existing Web smoke layering is oriented around functional fetch/render summary contracts."
- **直接证据**:
  - Plan residual hardening S2B lines 226-227: "If real Playwright browser binaries are available, add an optional/manual/live smoke or skipped test"
  - S2A controller adjudication residual risk: "S2B still owns Web raw process integration, Playwright synthetic cleanup smoke, and any optional/manual real browser evidence."
  - Implementation codex: `playwright_chromium_launch=available` 但未添加 live smoke
- **影响**: 真实 Chromium process tree cleanup 仍为环境依赖声明。S2B 只证明了 synthetic nested child（`subprocess.Popen` Python sleep 子进程）的 cleanup，未证明真实 Chromium 多进程树（browser process + GPU process + renderer processes + utility processes）的 cleanup。这是 plan 明确预见的 residual risk，但 plan 同时也要求一个 optional/skipped 测试来让环境能力显式化。
- **建议改法和验证点**:
  1. 添加 `@pytest.mark.skipif(not _chromium_available(), reason="chromium binary not available")` 标记的测试，启动真实 Playwright worker（使用 `_playwright_sync_worker`），terminate worker，用 `psutil` 或 `pgrep` 验证无幸存 Chromium 子进程
  2. 或在 implementation artifact 中明确记录：live browser smoke 为 S2B accepted residual，由后续 S4 validation 或独立 work unit 覆盖，并在 controller adjudication 中获得显式裁决
- **修复风险（低）**: 添加 skipped test 不影响 CI，仅在 browser binary 可用时运行
- **严重程度（低）**:

---

## Architecture / Design Notes

以下不是 findings，而是对 review 指令中五个重点审查维度的逐项确认：

### 1. Architecture：Web 依赖 runtime public primitive 是否合理

**确认结论**: 合理。`dayu.tools.web → dayu.runtime.interruptible_process` 方向正确，runtime 是层中立基础设施。Web backend 通过 `interrupt_multiprocessing_process` + `enter_new_process_session_if_supported` 复用 S2A 共享 primitive，未重复 process-group 逻辑。符合 plan "Do not duplicate process-group logic in Web code" 要求。

### 2. Async/sync boundary：`asyncio.run()` 在 running event loop 中是否失败

**确认结论**: 当前在生产中不失败。完整调用链为 `async fetch_web_page` → `await asyncio.to_thread(_fetch_web_page_business, ...)`（`web_tools.py:1475`）→ thread pool worker 线程 → `_terminate_playwright_process` → `asyncio.run(...)`。Worker 线程无 running event loop，`asyncio.run()` 创建新 loop 正常工作。

已在 Finding 01 中记录了结构性脆弱性和调用上下文约束未文档化的问题。

### 3. Process cleanup correctness

**确认结论**: 正确。terminate/kill 两阶段 sequencing 完整，queue close/joint_thread 在 finally + except-pass 保护下执行，daemon process 作为安全网。`enter_new_process_session_if_supported()` 在 worker callable 执行前调用，确保嵌套子进程进入独立 session。`interrupt_multiprocessing_process` 的 pgid 安全解析（与当前/父进程组比较）防止误伤父进程组。

一个细节：`_run_playwright_worker_process` 的 finally 块（line 582-583）在 cancel/timeout 路径已调用过 `_terminate_playwright_process` 后再次检查 `process.is_alive()`。如果进程在第一次 cleanup 后退出了，第二次检查返回 False，不会重复 cleanup。这是正确的幂等行为。

### 4. Test quality

**确认结论**: 
- `_SyntheticNestedPlaywrightWorker`：`@dataclass(frozen=True, slots=True)` 无字段 → slots 为空 tuple → pickle round-trip 安全 ✓
- PID file sync：poll 间隔 0.02s，timeout 3.0s → 对进程启动足够慷慨 ✓
- Skip/fallback logic：覆盖所有 S2A `ProcessGroupCleanupReason` 枚举值，在不支持或 pgid 不安全时正确 skip ✓
- 已在 Finding 03 中记录了 timing assertion 的参照值问题

### 5. Handoff/residual risk

**确认结论**: 真实 Chromium cleanup 未被断言是 plan 明确预见的 residual risk。S2B 的 synthetic nested child 测试证明了 S2A primitive 集成正确，但不证明真实浏览器多进程树的 cleanup。已在 Finding 04 中记录了 missing optional live smoke。

## Open Questions

1. **S2B grace value 1.0s vs policy default 0.2s**：`_PW_PROCESS_TERMINATE_GRACE_SECONDS = 1.0` 远大于 `ProcessCapsuleInterruptPolicy` 默认的 `0.2s`。这是因为 Playwright 子进程可能正在做浏览器 I/O，需要更长的 graceful shutdown 时间。这个差异是合理的，但 plan 要求 S2B "validate or adjust ProcessCapsuleInterruptPolicy named defaults"——1.0s 的实际需求是否意味着 policy defaults (0.2s) 对 Web/Playwright 场景不合适？还是 Playwright cleanup 的 1.0s 是一个不同的语义（工具内部 cleanup grace vs Host 级 policy）？

2. **`asyncio.run()` 是否值得专门提供 sync wrapper**：如果未来更多的 raw process cleanup 调用方需要 sync→async 桥接，是否应该在 `dayu.runtime.interruptible_process` 中提供一个同步版本的 `interrupt_multiprocessing_process`（内部使用 `asyncio.run()` 或 `loop.run_until_complete()`），由 runtime 层统一管理这个边界，而非让每个调用方各自处理？

## Residual Risk

1. **真实 Chromium process tree cleanup 未证明**: synthetic nested child（`subprocess.Popen` Python sleep 进程）的 cleanup 行为与真实 Chromium 多进程树（browser + GPU + renderer + utility）可能不同。Chromium 子进程可能对 SIGTERM 有不同的响应行为（如优雅关闭、状态持久化等）。此风险已在 plan 中记录为环境依赖，S2B synthetic evidence 是其最佳代理证明。

2. **`asyncio.run()` 在 `_terminate_playwright_process` 中的脆弱性**: 已在 Finding 01 详述。当前生产路径安全，但缺乏调用上下文约束的文档或运行时防护。

3. **Cleanup 诊断可观测性缺口**: 已在 Finding 02 详述。进程组清理降级在生产中不可见。

4. **PID/PGID reuse race**: 这是 S2A 已记录的 POSIX 信号限制。S2B 不引入新的 race surface，但也不缓解已有风险。

5. **Windows 完全不支持进程组 cleanup**: `_PROCESS_GROUP_CLEANUP_SUPPORTED = os.name == "posix"` → Windows 上 `enter_new_process_session_if_supported()` 返回 `False` → `interrupt_multiprocessing_process` 的 pgid 解析返回 `UNSUPPORTED` → 仅 direct-child cleanup。这在 runtime primitive 和测试 skip 逻辑中均有正确处理。S2B 在 Windows 上只能做 direct-child fallback，不声称进程组清理能力。
