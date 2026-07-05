# S2A Targeted Re-Review (AgentMiMo)

## Scope

- Mode: current changes (targeted re-review after AgentCodex fix)
- Branch: `phase/wu-tools-cancel-01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-rereview-mimo.md`
- Included scope: `dayu/runtime/interruptible_process.py`、`tests/runtime/test_interruptible_process.py`、AgentDS `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-code-review-ds.md`
- Excluded scope: S1/S2B/S3/S4、Host/Engine/Service/UI/Fins

## Finding Status

### S2A-F01（MiMo）：`interrupt_multiprocessing_process` 缺少未启动进程防护 → 已关闭

- **修复**: 新增 `_process_pid_or_none()` helper（行 518-528），捕获 `ValueError` 和 `OSError`，返回 `None`。`interrupt_multiprocessing_process` 在行 469 检查 `child_pid = _process_pid_or_none(process)`，`None` 时直接返回 `CHILD_PID_UNAVAILABLE` 诊断（行 470-484），不调用 signal 或 join。
- **验证**: 新测试 `test_interrupt_multiprocessing_process_reports_child_pid_unavailable_without_join` 用 `_FakeProcessCleanupHandle(pid_error=ValueError)` 覆盖此路径，断言 `reason=CHILD_PID_UNAVAILABLE`、`direct_signal_sent=False`、`not process.terminated`、`not process.killed`、`not process.joined`。

### S2A-F02（MiMo）：`ProcessInterruptResult` docstring 缺少 `cleanup` 字段 → 已关闭

- **修复**: 行 223 补充 `:param cleanup: 本次 direct child / process group cleanup 诊断。`

### S2A-F03（MiMo）：`_resolve_safe_child_process_group` 成功路径 diagnostic reason 预设为 `GROUP_SIGNALED` → 已关闭

- **修复**: 行 610 改为 `reason=ProcessGroupCleanupReason.NOT_REQUESTED`。下游 `_cleanup_process_group_after_direct_signal` 根据实际 `os.killpg` 结果更新 reason。语义一致。

### DS-01（AgentDS）：S2B handoff 漏说明 `setsid` 依赖 → 已关闭

- **修复**: `_enter_new_process_session_if_supported` 提升为 public `enter_new_process_session_if_supported`（行 502-515），返回 `bool`，加入 `__all__`（行 797）。`interrupt_multiprocessing_process` docstring（行 451-454）明确说明："调用方必须在子进程入口调用 `enter_new_process_session_if_supported()`，或完成等价的 POSIX session / process-group setup；否则本 helper 会安全回退为直接子进程 cleanup 诊断。"

### DS-02（AgentDS）：pgid 解析失败分支测试覆盖不足 → 已关闭

- **修复**: 新增 7 个测试覆盖 `CHILD_PID_UNAVAILABLE`、`CHILD_ALREADY_EXITED`、`CURRENT_PGID_UNAVAILABLE`、`PARENT_PGID_UNAVAILABLE`、`PGID_MATCHES_PARENT_PROCESS_GROUP`、`GROUP_SIGNAL_FAILED`、direct signal OSError 后仍 group signal + join。19 tests passed。

### DS-03（AgentDS）：`_signal_direct_process` 异常捕获范围不对称 → 已关闭

- **修复**: 行 660 扩展为 `except (ProcessLookupError, OSError): return False`，与 group signal 路径一致。

## `enter_new_process_session_if_supported()` Public Helper 审查

- **Misuse 风险**: 低。函数只做 `os.setsid()`，失败返回 `False`。调用方忽略返回值不会导致错误行为——fallback 路径（child pgid 匹配 current pgid）会安全回退到 direct-child cleanup。
- **Doc 足够性**: docstring 说明了返回值含义。`interrupt_multiprocessing_process` docstring 说明了何时需要调用。S2B 可从这两个 docstring 理解完整使用契约。
- **Export 合理性**: 合理。S2B Playwright worker target 需要调用此函数。`dayu.runtime` 层中立，不引入上层依赖。

## 新增 Branch Tests 审查

- **确定性**: 全部使用 `_FakeProcessCleanupHandle` + monkeypatch，不依赖真实子进程时序。
- **不过度 brittle**: 测试断言 cleanup result 的 `reason`、`direct_signal_sent`、`group_signal_sent`、`child_pgid` 等字段，不依赖内部实现细节（如 `_SafeProcessGroupLookup` 构造方式）。唯一保留的内部依赖是 `_FakeProcessCleanupHandle`（测试 helper，非生产代码）和 `_SafeProcessGroupLookup`（在 parametrized fallback 测试中使用）。
- **Cleanup**: `_FakeProcessCleanupHandle` 是 frozen dataclass 风格的 test double，行为明确，无副作用。

## Fix 是否引入新问题

未发现。具体检查：

- `_process_pid_or_none` 捕获 `ValueError` 和 `OSError`，与 `multiprocessing.Process.pid` 可能抛出的异常一致。
- `interrupt_multiprocessing_process` 的 `None` pid 早期返回路径跳过 signal 和 join——对未启动进程这是正确行为。
- `enter_new_process_session_if_supported` 从 `_enter_new_process_session_if_supported` 提升，行为不变，仅返回值从 `None` 改为 `bool`。
- `_signal_direct_process` 扩展 `except` 范围为 `(ProcessLookupError, OSError)`，不改变正常路径行为。
- `_resolve_safe_child_process_group` 成功路径 reason 从 `GROUP_SIGNALED` 改为 `NOT_REQUESTED`，下游覆盖逻辑不变。

## Conclusion

**PASS**

所有 3 个 MiMo findings（F01/F02/F03）和 3 个 DS findings（01/02/03）均已关闭。新增 `enter_new_process_session_if_supported()` public helper 设计合理、文档充分。7 个新 branch tests 确定性且不过度 brittle。Fix 未引入新 correctness/architecture/test 问题。19 tests passed，pyright 0 errors。
