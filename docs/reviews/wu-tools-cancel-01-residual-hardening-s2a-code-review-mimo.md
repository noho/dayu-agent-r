# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-cancel-01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-code-review-mimo.md`
- Included scope: `dayu/runtime/interruptible_process.py`、`tests/runtime/test_interruptible_process.py`、`tests/README.md`、`docs/reviews/wu-tools-cancel-01-residual-hardening-s2a-implementation-codex.md`
- Excluded scope: S1/S2B/S3/S4 改动、Host/Engine/Service/UI/Fins 层
- Parallel review coverage: 无

## Findings

### S2A-F01-未修复-低-`interrupt_multiprocessing_process` 缺少未启动进程防护

- **入口/函数**: `interrupt_multiprocessing_process(process, *, signal_kind, grace_seconds)`
- **文件(行号)**: `dayu/runtime/interruptible_process.py:462`
- **输入场景**: 外部调用方传入未 `start()` 的 `multiprocessing.Process` 对象
- **实际分支**: `_resolve_safe_child_process_group(process.pid)` 访问 `process.pid`
- **预期行为**: 公共 API 应对未启动进程有明确错误或前置校验
- **实际行为**: `multiprocessing.Process.pid` 在进程未启动时（`_popen is None`）抛出 `ValueError`，该异常未被 `_resolve_safe_child_process_group` 捕获，向调用方泄漏为未文档化的 `ValueError`
- **直接证据**: `interruptible_process.py:462` 调用 `process.pid`；`multiprocessing.Process.pid` property 在 `_popen is None` 时抛 `ValueError`；`_resolve_safe_child_process_group` 只捕获 `ProcessLookupError` 和 `OSError`（行 518-531），不捕获 `ValueError`
- **影响**: 内部调用方（`InterruptibleProcessHandle.terminate/kill`）已通过 `_require_started()` 防护，不受影响。外部直接调用 `interrupt_multiprocessing_process` 的调用方（如 S2B Playwright raw process path）会收到未文档化的 `ValueError`
- **建议改法和验证点**: 在 `_resolve_safe_child_process_group` 入口或 `interrupt_multiprocessing_process` 入口添加对 `child_pid is None` 或 `ValueError` 的显式处理，返回 `CHILD_PID_UNAVAILABLE` 诊断；或在函数 docstring 中显式声明"进程必须已启动"前置条件
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### S2A-F02-未修复-低-`ProcessInterruptResult` docstring 缺少 `cleanup` 字段文档

- **入口/函数**: `ProcessInterruptResult` dataclass
- **文件(行号)**: `dayu/runtime/interruptible_process.py:215-225`
- **输入场景**: 阅读 API 文档或类型提示
- **实际分支**: docstring `:param` 列表
- **预期行为**: dataclass 所有字段均应有 `:param` 文档
- **实际行为**: docstring 记录了 `supported`、`exited`、`exitcode`、`elapsed_seconds` 四个字段，遗漏了 `cleanup: ProcessGroupCleanupResult` 字段
- **直接证据**: `interruptible_process.py:215-225` docstring 只有 4 个 `:param`；`interruptible_process.py:230` 定义了第 5 个字段 `cleanup`
- **影响**: 开发者查阅 API 时会遗漏 `cleanup` 字段的存在和用途
- **建议改法和验证点**: 在 `ProcessInterruptResult` docstring 中补充 `:param cleanup: 本次 direct child / process group cleanup 诊断。`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### S2A-F03-未修复-信息-`_resolve_safe_child_process_group` 成功路径 diagnostic reason 预设为 `GROUP_SIGNALED`

- **入口/函数**: `_resolve_safe_child_process_group(child_pid)`
- **文件(行号)**: `dayu/runtime/interruptible_process.py:564-574`
- **输入场景**: child pgid 安全且与当前/父进程组不同时
- **实际分支**: 行 564-574，`_SafeProcessGroupLookup` 返回 `reason=GROUP_SIGNALED`
- **预期行为**: diagnostic reason 应反映实际发生的操作
- **实际行为**: `_SafeProcessGroupLookup.diagnostic.reason` 被设为 `GROUP_SIGNALED`，但此时尚未发送任何 group signal。下游 `_cleanup_process_group_after_direct_signal`（行 627-669）会根据实际 `os.killpg` 结果更新 reason，所以最终返回给调用方的 `ProcessGroupCleanupResult.reason` 是正确的
- **直接证据**: 行 570 预设 `reason=GROUP_SIGNALED`；行 649-669 根据实际结果覆盖 reason
- **影响**: 无实际影响。中间 `_SafeProcessGroupLookup` 对象不会泄漏给外部调用方，最终 `ProcessGroupCleanupResult` 的 reason 正确反映实际操作
- **建议改法和验证点**: 可考虑将预设 reason 改为 `NOT_REQUESTED` 以语义一致，但当前实现的正确性不受影响
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 信息

## Open Questions

- 无

## Residual Risk

- `ProcessGroupCleanupReason` 枚举有 11 个成员，当前测试覆盖了 `UNSUPPORTED`、`PGID_UNAVAILABLE`、`PGID_MATCHES_CURRENT_PROCESS_GROUP`、`GROUP_SIGNALED`（通过 nested child 测试）4 个。`PGID_MATCHES_PARENT_PROCESS_GROUP`、`CHILD_ALREADY_EXITED`、`GROUP_SIGNAL_FAILED`、`CHILD_PID_UNAVAILABLE`、`CURRENT_PGID_UNAVAILABLE`、`PARENT_PGID_UNAVAILABLE`、`NOT_REQUESTED` 未被直接测试。其中 `NOT_REQUESTED` 由 `_process_group_cleanup_not_requested()` 默认值覆盖；其余路径在真实 POSIX 环境下难以确定性触发，可通过 monkeypatch 补充但优先级低。
- S2A 不覆盖 Windows 平台。`_PROCESS_GROUP_CLEANUP_SUPPORTED = os.name == "posix"` 在 Windows 上为 `False`，所有 cleanup 走 direct-child fallback 并返回 `UNSUPPORTED` 诊断。该行为已通过 `test_interruptible_process_group_reports_unsupported_when_not_available` 锁定。
- S2A 不覆盖 S2B Playwright raw `multiprocessing.Process` 路径复用 `interrupt_multiprocessing_process` 的集成验证，该验证由 S2B 负责。

## Review Conclusion

**PASS**

S2A 实现满足计划的所有要求：

1. **POSIX signal strategy**: 子进程通过 `os.setsid()` 进入独立 session/process group；cleanup 先 signal 直接子进程，再仅在 pgid 安全确认后 signal 子进程组；`_resolve_safe_child_process_group` 逐一检查 child pgid vs current/parent pgid，不安全时 fallback 到 direct-child。正确。

2. **`interrupt_multiprocessing_process` generic 设计**: 接受 `ProcessCleanupHandle` Protocol，不依赖 `InterruptibleProcessHandle` 具体实现，不引入上层依赖。可被 S2B Playwright raw process path 直接复用。

3. **Fallback/diagnostic 真实可观察**: `ProcessGroupCleanupResult` 通过 `reason` 枚举区分 `UNSUPPORTED`、`CHILD_PID_UNAVAILABLE`、`CHILD_ALREADY_EXITED`、`PGID_UNAVAILABLE`、`CURRENT_PGID_UNAVAILABLE`、`PARENT_PGID_UNAVAILABLE`、`PGID_MATCHES_CURRENT_PROCESS_GROUP`、`PGID_MATCHES_PARENT_PROCESS_GROUP`、`GROUP_SIGNAL_FAILED`、`GROUP_SIGNALED`。所有路径均不伪称 nested cleanup。

4. **Correctness/race**: child 已退出由 `ProcessLookupError` 捕获；pid reuse 被 `setsid()` + pgid check 阻止误 signal；`terminate` vs `kill` 由 `signal_kind` 参数区分；join grace 由 `grace_seconds` 控制；`close()` 对未启动进程安全跳过。

5. **Tests**: nested child smoke 通过 marker file 同步，deterministic；`finally` 块包含 force-kill cleanup 防止进程泄漏；12 个测试全部通过；pyright 0 errors。
