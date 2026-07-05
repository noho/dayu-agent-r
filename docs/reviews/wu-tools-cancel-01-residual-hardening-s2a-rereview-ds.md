# WU-TOOLS-CANCEL-01 Residual Hardening S2A Code Re-Review (AgentDS)

## Scope

- Mode: targeted re-review after AgentCodex fix
- Branch: `phase/wu-tools-cancel-01`
- Base: `main` (uncommitted changes against HEAD)
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-rereview-ds.md`
- Review timestamp: 2026-07-05 15:28 CST
- Included scope:
  - `dayu/runtime/interruptible_process.py` (full file, post-fix)
  - `tests/runtime/test_interruptible_process.py` (full file, post-fix)
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-code-review-ds.md` (previous DS review基线)
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-code-review-mimo.md` (MiMo review基线)
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-implementation-codex.md` (Codex fix report — 无独立的 fix artifact，fix 直接在 implementation 文件中)
- Excluded scope: committed S1/S2 partial hardening 改动、Host/Engine/Service/UI/Fins 层、S2B/S3/S4 scope
- Parallel review coverage: 无

## Previous Finding Closure Verification

### DS Finding 01（中 — S2B handoff 漏说明 `setsid` 依赖）

**状态：CLOSED**

变更证据：
- `_enter_new_process_session_if_supported` → `enter_new_process_session_if_supported()`（:502-515），提升为 public API，返回 `bool`，加入 `__all__`（:796）。
- `interrupt_multiprocessing_process` docstring（:446-454）新增显式说明："若调用方需要清理子进程启动的嵌套进程，子进程入口必须在启动嵌套进程前调用 ``enter_new_process_session_if_supported()``，或完成等价的 POSIX session / process-group setup；否则本 helper 会安全回退为直接子进程 cleanup 诊断。"
- `interrupt_multiprocessing_process` docstring（:456-457）同时说明了未启动/PID 不可用时的行为。

验证：S2B 调用方现在有两个清晰选择：(a) 在 worker target 中调用 `enter_new_process_session_if_supported()` 获得 process-group cleanup；(b) 不调用则安全 fallback 到 direct-child-only。public API + docstring 已自足说明前置条件，无需阅读 `_run_process_target` 私有实现。**关闭。**

### DS Finding 02（中 — real pgid resolution failure branches not tested e2e）

**状态：CLOSED**

变更证据 — 新增 7 个测试覆盖此前未覆盖的 5 条路径：

| 测试 | 覆盖的 reason 路径 | 测试方式 |
|------|--------------------|---------|
| `test_interrupt_multiprocessing_process_reports_child_pid_unavailable_without_join` (:604-628) | `CHILD_PID_UNAVAILABLE` | `_FakeProcessCleanupHandle` + `pid_error=ValueError`，不 monkeypatch syscall |
| `test_interrupt_multiprocessing_process_reports_child_already_exited` (:631-663) | `CHILD_ALREADY_EXITED` | monkeypatch `os.getpgid` → `_GetPgidRaisesProcessLookup` |
| `test_interrupt_multiprocessing_process_reports_current_pgid_unavailable` (:666-707) | `CURRENT_PGID_UNAVAILABLE` | monkeypatch `os.getpgrp` → `_raise_current_pgid_unavailable` |
| `test_interrupt_multiprocessing_process_reports_parent_pgid_unavailable` (:709-752) | `PARENT_PGID_UNAVAILABLE` | monkeypatch `os.getpgid` → `_ParentGetPgidRaises` |
| `test_interrupt_multiprocessing_process_reports_parent_pgid_match` (:754-803) | `PGID_MATCHES_PARENT_PROCESS_GROUP` | monkeypatch `os.getpgid` → `_FixedGetPgid`（child_pgid == parent_pgid） |
| `test_interrupt_multiprocessing_process_reports_group_signal_failed` (:805-858) | `GROUP_SIGNAL_FAILED` | monkeypatch `os.killpg` → `_KillpgRaisesOSError` |
| `test_interrupt_multiprocessing_process_direct_signal_oserror_still_joins_and_signals_group` (:860-916) | `GROUP_SIGNALED`（direct signal OSError 后 group signal 仍成功） | `_FakeProcessCleanupHandle(signal_error=OSError(...))` + `_KillpgRecorder` |

新测试基础设施：
- `_FakeProcessCleanupHandle`（:132-221）— 完整实现 `ProcessCleanupHandle` Protocol，支持可配置的 pid_value、pid_error、signal_error、alive、exitcode，以及 terminate/kill/join 调用追踪。
- `_FixedGetPgid`（:224-240）— 按 PID 分发返回不同 pgid 的 callable。
- `_ParentGetPgidRaises`（:243-259）— 子 PID 返回 pgid，父 PID 抛 OSError。
- `_GetPgidRaisesProcessLookup`（:262-273）— 始终抛 ProcessLookupError。
- `_KillpgRecorder`（:276-299）— 记录 `os.killpg` 调用参数。
- `_KillpgRaisesOSError`（:302-314）— 始终抛 OSError。
- 固定测试常量 `_TEST_CHILD_PID`/`_TEST_PARENT_PID`/`_TEST_CURRENT_PGID`/`_TEST_CHILD_PGID`/`_TEST_PARENT_PGID`（:33-37）替代原先直接使用 `os.getpgrp()` 的测试夹具，消除测试对运行时进程组状态的依赖。

验证：`_resolve_safe_child_process_group` 的 9 条 return 路径现均有至少一个测试覆盖。**关闭。**

### DS Finding 03（低 — `_signal_direct_process` exception scope narrower than group path）

**状态：CLOSED**

变更证据：
- `_signal_direct_process`（:660）从 `except ProcessLookupError` 扩展为 `except (ProcessLookupError, OSError)`，与 `_cleanup_process_group_after_direct_signal`（:688-700）一致。
- 新增测试 `test_interrupt_multiprocessing_process_direct_signal_oserror_still_joins_and_signals_group`（:860-916）验证 OSError 时：direct_signal_sent=False、group signal 仍执行、join 仍执行。

验证：异常处理现已对称，OSError 不会穿透到调用方。**关闭。**

### MiMo S2A-F01（低 — `interrupt_multiprocessing_process` 缺少未启动进程防护）

**状态：CLOSED**

变更证据：
- 新增 `_process_pid_or_none(process)`（:518-528），捕获 `ValueError` 和 `OSError`，返回 `int | None`。
- `interrupt_multiprocessing_process`（:469-484）在调用 `_resolve_safe_child_process_group` 之前先通过 `_process_pid_or_none` 读取 PID。若 PID 为 None，直接返回 `CHILD_PID_UNAVAILABLE` 诊断，**不调用 signal 或 join**。
- 新增测试 `test_interrupt_multiprocessing_process_reports_child_pid_unavailable_without_join`（:604-628）验证：`reason=CHILD_PID_UNAVAILABLE`、`direct_signal_sent=False`、`group_signal_sent=False`、`process.terminated=False`、`process.killed=False`、`process.joined=False`。

验证：未启动进程不再泄漏 `ValueError`，而是返回结构化诊断。`_FakeProcessCleanupHandle` 测试既覆盖了 `ValueError` 路径也覆盖了 `OSError` 路径（通过 `pid_error` 参数）。**关闭。**

### MiMo S2A-F02（低 — `ProcessInterruptResult` docstring 缺少 `cleanup` 字段文档）

**状态：CLOSED**

变更证据：
- `ProcessInterruptResult` docstring（:223）新增 `:param cleanup: 本次 direct child / process group cleanup 诊断。`

验证：所有 5 个字段现在均有 `:param` 文档。**关闭。**

### MiMo S2A-F03（信息 — `_resolve_safe_child_process_group` 成功路径 diagnostic reason 预设为 `GROUP_SIGNALED`）

**状态：CLOSED**

变更证据：
- `_resolve_safe_child_process_group` 安全 pgid 路径（:610）的 baseline reason 从 `GROUP_SIGNALED` 改为 `NOT_REQUESTED`。
- 实际 group signal 是否发送由 `_cleanup_process_group_after_direct_signal` 决定——成功时覆盖为 `GROUP_SIGNALED`（:706），失败时覆盖为 `CHILD_ALREADY_EXITED`（:693）或 `GROUP_SIGNAL_FAILED`（:700）。

验证：baseline reason 现在语义一致——"尚未请求 group signal"。最终 reason 仍正确反映实际操作。**关闭。**

## New Changes Review

### `enter_new_process_session_if_supported()` public API

- **位置**: `dayu/runtime/interruptible_process.py:502-515`
- **签名**: `def enter_new_process_session_if_supported() -> bool`
- **行为**:
  - 非 POSIX → 返回 `False`
  - POSIX → 调用 `os.setsid()`；成功返回 `True`；`OSError`（如已是 session leader）返回 `False`
- **docstring**: 清晰说明了返回值语义和调用场景。
- **`__all__`**: 已在 :796 导出。
- **调用方**: `_run_process_target`（:428）不捕获返回值（best-effort）；S2B 可在 Playwright worker target 入口调用。
- **架构合规**: 仅依赖 `os` 标准库模块，无上层依赖。✅
- **Misuse 风险评估**: 函数名和 docstring 明确说明用于"子进程入口"。若误在父进程调用，`setsid()` 会使父进程脱离控制终端——但这是 POSIX `setsid()` 的标准行为，且 docstring 已明确调用场景。**风险低。**

### `_process_pid_or_none()` helper

- **位置**: `dayu/runtime/interruptible_process.py:518-528`
- **行为**: 捕获 `ValueError`（`multiprocessing.Process.pid` 在 `_popen is None` 时抛出）和 `OSError`（防御性，Protocol 的其它实现可能抛出），返回 `int | None`。
- **调用方**: 仅 `interrupt_multiprocessing_process`（:469）。
- **正确性**: `ValueError` 覆盖了 `multiprocessing.Process` 的实际异常；`OSError` 是对 Protocol 实现的防御。✅

### `interrupt_multiprocessing_process` early return for pid=None

- **位置**: `dayu/runtime/interruptible_process.py:470-484`
- **行为**: 当 `_process_pid_or_none` 返回 `None` 时，**不调用** `_signal_direct_process`、`_cleanup_process_group_after_direct_signal`、`process.join`。直接返回 `ProcessInterruptResult`，`exited=not process.is_alive()`。
- **正确性**: 未启动的 `multiprocessing.Process.is_alive()` 返回 `False`，因此 `exited=True`——与 `InterruptibleProcessHandle.terminate/kill` 的早期返回语义一致。✅
- **边界**: `_validate_grace_seconds`（:467）在 pid 检查之前调用，保证 grace 校验仍生效。✅

### `_resolve_safe_child_process_group` dead branch

- **位置**: `dayu/runtime/interruptible_process.py:547-553`
- **观察**: `child_pid is None` 分支在 `_resolve_safe_child_process_group` 中仍然存在，但当前唯一调用方（`interrupt_multiprocessing_process`:485）已通过 `_process_pid_or_none` + early return 保证传入的 `child_pid` 永远是 `int`。此分支在当前 call path 上不可达。
- **评估**: 6 行防御代码，不影响正确性。若未来有其它内部调用方直接调用 `_resolve_safe_child_process_group(None)`，此分支提供了安全兜底。**不作为 finding**，仅记录为可选的后续 cleanup。
- **严重程度**: 不适用（非 finding）。

### Test quality assessment

- **确定性**: 新增 7 个测试全部使用 monkeypatch 注入固定 PID/PGID 常量（:33-37）或 `_FakeProcessCleanupHandle`，不依赖真实 OS 进程状态。每个测试路径是确定性的，不会 flaky。
- **残留子进程**: 仅 `test_interruptible_process_group_kills_nested_child_on_posix` 启动真实子进程，其 `finally` 块（:531-534）保留了 `_force_kill_pid` 兜底清理。其余测试使用 `_FakeProcessCleanupHandle`，无真实子进程。
- **`_FakeProcessCleanupHandle`**: 完整实现 `ProcessCleanupHandle` Protocol，支持 terminate/kill/join 调用追踪（`terminated`/`killed`/`joined` 属性）和可配置异常注入（`pid_error`/`signal_error`）。这是测试该 Protocol 的正确方式——不依赖 `multiprocessing.Process` 的具体实现细节。
- **Brittleness**: monkeypatch 目标是 `interruptible_process.os.getpgid` 等模块级属性引用，使用 `raising=False` 确保 setattr 不因属性缺失而失败。这是标准 pytest monkeypatch 模式，不 brittle。
- **未覆盖项**: `_resolve_safe_child_process_group` 中的 `child_pid is None` 分支（:547-553）在当前 call path 上不可达，无测试覆盖。这是上述 dead branch 的另一面——无测试因为它不可达。若未来代码重构使此分支重新可达，测试防护缺失是 residual risk。

### Architecture / export check

- `__all__` 新增 7 个符号（:790-797）：`ProcessCleanupSignal`、`ProcessCleanupHandle`、`ProcessGroupCleanupReason`、`ProcessGroupCleanupResult`、`enter_new_process_session_if_supported`、`interrupt_multiprocessing_process`，加上原有的 `ProcessInterruptResult`（已有）。
- 无反向依赖：`grep -rn "from dayu\.\(engine\|host\|service\|ui\|fins\)" dayu/runtime/` 返回空。✅
- Host `tool_runtime.py` 不导入任何新增 S2A 符号，仍通过 `InterruptibleProcessHandle` 间接使用。✅

## Findings

未发现实质性问题。

前次 DS review 的 3 个 findings（01/02/03）与 MiMo review 的 3 个 findings（S2A-F01/F02/F03）全部关闭。fix 引入的变更——`enter_new_process_session_if_supported()` public API、`_process_pid_or_none()` helper、`interrupt_multiprocessing_process` early return、新测试基础设施、docstring 修复——均正确且不引入新问题。

## Open Questions

- 无

## Residual Risk

1. **`_resolve_safe_child_process_group` 中 `child_pid is None` 分支（:547-553）为 dead code**：当前唯一调用方 `interrupt_multiprocessing_process` 已通过 `_process_pid_or_none` + early return 保证传入 PID 永远非 None。6 行防御代码不影响正确性，但若未来重构使此分支重新可达，需补充测试。建议后续 cleanup 中决定是移除 dead branch 并收紧签名为 `child_pid: int`，还是保留防御并添加一个直接调用 `_resolve_safe_child_process_group(None)` 的单元测试。

2. **`enter_new_process_session_if_supported()` 的 misuse 风险**：若误在父进程（而非子进程）中调用，`os.setsid()` 会使父进程脱离控制终端。当前 docstring 已明确说明调用场景（"让当前子进程进入独立 session"），`interrupt_multiprocessing_process` 的 docstring 也说明了正确用法。此风险由调用方负责，`dayu.runtime` 层面无法在运行时检测调用上下文。S2B implementation review 应确认 Playwright worker 在正确的位置调用此函数。

3. **S2B 集成验证**: S2A 不覆盖 `interrupt_multiprocessing_process` 与 `enter_new_process_session_if_supported` 在 Playwright raw `multiprocessing.Process` 路径上的集成验证。此验证属于 S2B scope。

## Conclusion

**PASS**

6 个前次 review findings 全部关闭。fix 新增 7 个确定性测试（总测试数 12 → 19），所有 `_resolve_safe_child_process_group` 分支现均有覆盖。public API（`enter_new_process_session_if_supported`、`interrupt_multiprocessing_process`）docstring 完整，export 范围合理，层中立约束保持。`pyright` 0 errors，`pytest` 19 passed。
