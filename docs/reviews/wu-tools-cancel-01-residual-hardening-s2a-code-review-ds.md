# WU-TOOLS-CANCEL-01 Residual Hardening S2A Code Review (AgentDS)

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-cancel-01`
- Base: `main` (uncommitted changes only)
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-code-review-ds.md`
- Review timestamp: 2026-07-05 15:18 CST
- Included scope:
  - `dayu/runtime/interruptible_process.py` (uncommitted diff + full file)
  - `tests/runtime/test_interruptible_process.py` (uncommitted diff + full file)
  - `tests/README.md` (uncommitted diff)
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-implementation-codex.md` (context)
- Excluded scope:
  - Committed S1 changes and prior S2 partial hardening (not in uncommitted diff)
  - Host `tool_runtime.py` (no S2A changes in uncommitted diff)
  - Playwright / Web code (S2B scope)
  - Fins / Doc tools (S3 scope)
- Truth sources:
  - `docs/host/wu-tools-cancel-01-residual-hardening-plan.md` S2A/S2B sections
  - `docs/host/issues-implementation-control.md`
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-implementation-codex.md`
- Parallel review coverage: 无（单人 review，未使用 subagent）

## Review Method Summary

1. 读取全部 uncommitted diff、完整源文件与上下文真源文档。
2. 沿真实执行路径逐行走读：`InterruptibleProcessHandle.terminate/kill` → `interrupt_multiprocessing_process` → `_resolve_safe_child_process_group` → `_signal_direct_process` → `_cleanup_process_group_after_direct_signal` → `ProcessInterruptResult`。
3. 检查 `_run_process_target` → `_enter_new_process_session_if_supported` 的 session 创建链路与 pgid 继承关系。
4. 对 `_resolve_safe_child_process_group` 的 9 条分支做全分支覆盖审查，验证每条分支的触发条件、诊断原因、`child_pgid` 安全语义。
5. 检查 `ProcessGroupCleanupResult` 各字段在正常路径、异常路径、早期返回路径下的一致性。
6. 执行 adversarial failure pass：signal race、pid/pgid recycle、setsid 失败、OSError 传播、测试残留子进程、monkeypatch 覆盖面。
7. 验证 `dayu.runtime` 层中立约束。
8. 运行 `pytest tests/runtime/test_interruptible_process.py -q`（12 passed）和 `pyright`（0 errors）确认实现声明。

## Findings

### 01-PASS_WITH_FINDINGS-中-S2B-handoff-setsid-not-part-of-shared-primitive

- **入口/函数**: `_enter_new_process_session_if_supported` → `_run_process_target` → `interrupt_multiprocessing_process`
- **文件(行号)**: `dayu/runtime/interruptible_process.py:428`（`_run_process_target` 调用 `setsid`），`dayu/runtime/interruptible_process.py:440-476`（`interrupt_multiprocessing_process` 不包含 `setsid` 调用）
- **输入场景**: S2B 使用 `interrupt_multiprocessing_process` 直接对 Playwright 的 raw `multiprocessing.Process` 做 process-group cleanup，但 Playwright worker 未调用 `setsid()`。
- **实际分支**: `_resolve_safe_child_process_group` 发现 `child_pgid == current_pgid`（:550-556），返回 `PGID_MATCHES_CURRENT_PROCESS_GROUP`，`child_pgid=None`，fallback 直接子进程 cleanup。
- **预期行为**: S2B 复用 shared primitive 后应能获得 process-group cleanup 能力（plan S2A:179-181: "InterruptibleProcessHandle and the Playwright raw multiprocessing.Process path must call the same primitives"）。
- **实际行为**: Process-group signal 永远不会被发送（`child_pgid=None`），`group_signal_sent` 始终为 `False`，S2B 只能获得 direct-child fallback。诊断正确反映此限制（`reason=PGID_MATCHES_CURRENT_PROCESS_GROUP`），但 S2B 实现者可能预期 "just works"。
- **直接证据**:
  - `_enter_new_process_session_if_supported`（:479-490）仅在 `_run_process_target`（:428）中被调用，后者仅被 `InterruptibleProcessHandle.__init__`（:268-271）消费。
  - `interrupt_multiprocessing_process`（:440-476）是 public API，但只做 signal + join，不做 session setup。
  - `_run_process_target` 是模块私有函数（:417），不在 `__all__` 中，S2B 不应直接调用。
  - Playwright 的 `_run_playwright_worker_process` 使用 raw `multiprocessing.Process`，不经过 `_run_process_target`。
- **影响**: S2B 即使正确调用 `interrupt_multiprocessing_process`，在 POSIX 上也永远无法获得 `group_signal_sent=True`。S2B 需要额外在 Playwright worker target 中调用 `os.setsid()`（或等价机制），但 plan 和 Codex handoff 报告均未明确此要求。
- **建议改法和验证点**:
  1. 在 `interrupt_multiprocessing_process` 的 docstring 中明确说明：调用方必须在子进程入口调用 `os.setsid()`（或复用 `_run_process_target`）才能获得 process-group cleanup 能力。
  2. 或在 S2A 中将 `_enter_new_process_session_if_supported` 提升为 public（`enter_new_process_session_if_supported`），供 S2B 在 Playwright worker 入口调用。
  3. S2B plan/implementation 中必须显式处理此依赖。
- **修复风险（低）**: 仅文档/契约澄清，不改动行为。
- **严重程度（中）**: 不影响 S2A 正确性，但会导致 S2B 无法实现 plan 声称的 "shared primitive gives process-group cleanup" 目标。诊断机制已安全兜底，不会误杀。

### 02-PASS_WITH_FINDINGS-中-real-pgid-resolution-failure-branches-not-tested-e2e

- **入口/函数**: `_resolve_safe_child_process_group`
- **文件(行号)**: `dayu/runtime/interruptible_process.py:493-574`
- **输入场景**: `os.getpgid(child_pid)` 抛出 `ProcessLookupError` 或 `OSError`；`os.getpgrp()` 抛出 `OSError`；`os.getpgid(os.getppid())` 抛出 `OSError`；`child_pgid == current_pgid` 或 `child_pgid == parent_pgid` 的真实 OS 场景。
- **实际分支**: 共 9 条 return 路径（:502-508 UNSUPPORTED，:509-515 CHILD_PID_UNAVAILABLE，:517-524 CHILD_ALREADY_EXITED，:525-531 PGID_UNAVAILABLE，:533-540 CURRENT_PGID_UNAVAILABLE，:542-549 PARENT_PGID_UNAVAILABLE，:550-556 PGID_MATCHES_CURRENT_PROCESS_GROUP，:557-563 PGID_MATCHES_PARENT_PROCESS_GROUP，:564-574 GROUP_SIGNALED）。
- **预期行为**: 每条分支的正确性应由测试验证——要么端到端触发真实 OS 条件，要么通过 monkeypatch 注入后验证下游 fallback 行为。
- **实际行为**: 仅有 `GROUP_SIGNALED` 路径（:564-574）通过 `test_interruptible_process_group_kills_nested_child_on_posix` 做端到端测试。`UNSUPPORTED` 路径通过 monkeypatch `_PROCESS_GROUP_CLEANUP_SUPPORTED` 测试。`PGID_UNAVAILABLE` 和 `PGID_MATCHES_CURRENT_PROCESS_GROUP` 通过 monkeypatch `_resolve_safe_child_process_group` 整体替换测试下游 fallback，但未测试真实 pgid 解析逻辑。剩余 5 条路径（CHILD_PID_UNAVAILABLE、CHILD_ALREADY_EXITED、CURRENT_PGID_UNAVAILABLE、PARENT_PGID_UNAVAILABLE、PGID_MATCHES_PARENT_PROCESS_GROUP）无任何直接或间接测试覆盖。
- **直接证据**:
  - `tests/runtime/test_interruptible_process.py:283-316`：仅覆盖 GROUP_SIGNALED 路径。
  - `tests/runtime/test_interruptible_process.py:319-342`：monkeypatch `_PROCESS_GROUP_CLEANUP_SUPPORTED` → UNSUPPORTED 路径。
  - `tests/runtime/test_interruptible_process.py:345-383`：parametrized monkeypatch `_resolve_safe_child_process_group` → PGID_UNAVAILABLE 和 PGID_MATCHES_CURRENT_PROCESS_GROUP，但替换的是整个解析函数，不测试真实 syscall 错误处理。
  - `tests/runtime/test_interruptible_process.py:189-231`：`_resolve_process_group_unavailable` 和 `_resolve_process_group_matches_current` 是测试夹具，构造 `_SafeProcessGroupLookup` 时不经过真实 `os.getpgid`/`os.getpgrp`/`os.getppid` 调用。
- **影响**: `_resolve_safe_child_process_group` 中的 `try/except OSError` 分支（:525-531、:533-540、:542-549）在真实 OS 异常下的行为未经验证。若未来重构引入错误（如错误地吞掉关键异常、错误地设置 `child_pgid`），现有测试不会捕获。
- **建议改法和验证点**:
  1. 至少为 `CHILD_PID_UNAVAILABLE`（`child_pid=None`）添加一个不依赖 monkeypatch 的测试：构造 `ProcessCleanupHandle` 的 mock/stub 使其 `pid` 返回 `None`，调用 `interrupt_multiprocessing_process`，断言 `reason=CHILD_PID_UNAVAILABLE`。
  2. `CHILD_ALREADY_EXITED` 可通过 spawn 一个立即退出的短命进程后立即调用 `interrupt_multiprocessing_process` 触发（需接受一定的时序不确定性）。
  3. `PGID_MATCHES_PARENT_PROCESS_GROUP` 与 `PGID_MATCHES_CURRENT_PROCESS_GROUP` 类似，仅需在 parametrized test 中增加一组 monkeypatch fixture。
  4. `CURRENT_PGID_UNAVAILABLE` / `PARENT_PGID_UNAVAILABLE` 属于极端 OS 异常路径，可显式记录为 deferred 不覆盖，但需在测试或 review artifact 中明确此决策。
- **修复风险（低）**: 补充测试不改变生产行为。
- **严重程度（中）**: 9 条分支中 5 条无任何覆盖。核心安全逻辑（pgid 比较、异常处理）的回归保护不足。

### 03-PASS_WITH_FINDINGS-低-_signal_direct_process-exception-scope-narrower-than-group-path

- **入口/函数**: `_signal_direct_process` vs `_cleanup_process_group_after_direct_signal`
- **文件(行号)**: `dayu/runtime/interruptible_process.py:606-624`（仅捕获 `ProcessLookupError`），`dayu/runtime/interruptible_process.py:627-669`（捕获 `ProcessLookupError` 和 `OSError`）
- **输入场景**: `multiprocessing.Process.terminate()` 或 `.kill()` 因非 `ProcessLookupError` 原因失败（例如进程被 init 收养后 `os.kill` 返回 `EPERM`）。
- **实际分支**: `_signal_direct_process:617-623` 的 `try/except` 仅捕获 `ProcessLookupError`；`OSError`（含 `PermissionError`）会穿透到 `interrupt_multiprocessing_process` 调用方。
- **预期行为**: 直接子进程 signal 失败应有统一收口，不应因异常类型不同而区别传播。
- **实际行为**: `ProcessLookupError` 被转为 `direct_signal_sent=False`；`OSError` 则作为未处理异常向上传播，中断 cleanup 流程——后续的 group signal 和 join 都不会执行。
- **直接证据**:
  - :617-623：`except ProcessLookupError: return False`，无 `except OSError`。
  - :648-663：group signal 路径同时捕获 `except ProcessLookupError` 和 `except OSError`。
  - `multiprocessing.Process.terminate()` 在 CPython 中最终调用 `os.kill(self.pid, signal.SIGTERM)`，可能抛出 `ProcessLookupError` 或 `OSError`。
- **影响**: 在极端场景（进程被 reparent 到 init 后权限变更），`terminate()`/`kill()` 的 `OSError` 会导致 `interrupt_multiprocessing_process` 整体失败，group signal 和 grace join 均被跳过。当前实际影响极低（正常 owned child process 不会触发此路径）。
- **建议改法和验证点**:
  1. 将 `except ProcessLookupError` 扩展为 `except (ProcessLookupError, OSError)`，与 group signal 路径保持一致。
  2. 或显式记录设计决策：直接子进程 signal 失败为 unexpected，应向上传播而非静默吸收。
- **修复风险（低）**: 扩展异常捕获范围不会改变正常路径行为。
- **严重程度（低）**: 触发条件极端罕见，当前实现已有 `ProcessLookupError` 覆盖最常见的 race-condition 场景。

## Open Questions

1. **`_enter_new_process_session_if_supported` 是否应提升为 public API？** 当前为模块私有，S2B 无法直接调用。若提升为 `enter_new_process_session_if_supported`，S2B 可在 Playwright worker target 入口调用它，避免重复实现。但这会扩大 `dayu.runtime` 的 public surface。建议在 S2B plan 中裁决。

2. **`_resolve_safe_child_process_group` 中 `parent_pgid = os.getpgid(os.getppid())` 的语义：** `os.getppid()` 返回当前进程的父进程 PID。在 `interrupt_multiprocessing_process` 的调用上下文中（asyncio event loop 线程），父进程是启动 Python 解释器的进程（如 shell 或 IDE）。`os.getpgid(os.getppid())` 获取的是父进程的进程组。如果父进程已在不同进程组（常见于 shell 作业控制），此检查能正确防止误杀。如果父进程与当前进程在同一进程组（如直接通过 `python script.py` 启动），`child_pgid == parent_pgid` 等价于 `child_pgid == current_pgid`，由前一个检查覆盖。语义正确，但建议在代码注释中说明此设计意图。

## Residual Risk

1. **PID/ PGID recycle race**：`_resolve_safe_child_process_group` 获取 `child_pgid` 与 `_cleanup_process_group_after_direct_signal` 调用 `os.killpg` 之间存在 TOCTOU 窗口。若子进程在此窗口内退出且其 pgid 被 OS 回收并分配给无关进程，`os.killpg` 会向错误进程组发送信号。此风险是 PID-based signaling 的固有局限，标准缓解手段（PID namespace、cgroup）超出本 slice 范围。当前实现已通过 `ProcessLookupError` catch 覆盖进程组已不存在的情况，但无法防御 pgid 复用。实际风险极低（窗口远小于 1ms，pgid 复用概率远低于 pid 复用）。

2. **`_enter_new_process_session_if_supported` 静默吞掉所有 `OSError`**：`os.setsid()` 失败时（如进程已是 session leader）返回而不报错。当前实现无法区分 "已是 session leader（安全，预期行为）" 和 "setsid 因其他原因失败（可能需要感知）"。建议在未来 platform hardening 中考虑记录 diagnostic log，但不改变 fallback 行为。

3. **`_resolve_process_group_matches_current` 测试夹具在非 POSIX 平台的 `child_pgid` 为 `None`**：`current_pgid = os.getpgrp() if os.name == "posix" else None`（:220）。此夹具仅在 POSIX 上提供有意义的 pgid。由于 unsupported 测试（`test_interruptible_process_group_reports_unsupported_when_not_available`）覆盖了非 POSIX 行为，此设计可接受。

4. **S2B 集成验证未在 S2A 中覆盖**：`interrupt_multiprocessing_process` 被 Host `tool_runtime.py` 间接消费（通过 `InterruptibleProcessHandle`），但 Host 当前不读取 `ProcessInterruptResult.cleanup` 字段。S2A 无法验证 `cleanup` 诊断在 Host 路径上的端到端可达性。此验证属于 S2B scope。

## Conclusion

**PASS_WITH_FINDINGS**

实现正确、安全、测试通过（12 passed）、pyright clean（0 errors）、架构边界完整（`dayu.runtime` 无反向依赖）。Process-group cleanup 的安全检查逻辑（pgid vs current/parent process group）完整且 fail-safe。诊断机制提供了足够的 observability 供 S2B 做 nested-cleanup claim 判断。

两个 medium findings 均不阻塞 merge：
- **01**（S2B handoff 漏说明 `setsid` 依赖）：S2B plan 中显式处理即可，不影响 S2A 代码正确性。
- **02**（pgid 解析失败分支测试覆盖不足）：补充测试可在后续 slice 或 targeted hardening 中完成，当前 monkeypatch 测试已验证 fallback 行为正确。

一个 low finding（异常捕获不对称）建议在后续 cleanup 中统一，不构成当前阻塞项。
