# WU-TOOLS-CANCEL-01 Residual Hardening S1 Re-review - AgentMiMo

## Scope

- Mode: targeted re-review after AgentCodex code-review fix
- Branch: `phase/wu-tools-cancel-01`
- Base: `HEAD`（workspace 未提交改动）
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-rereview-mimo.md`
- Included scope: AgentCodex code-review fix 对 F01（close grace 硬编码）和 F02（Host 层非字符串 hint 测试）的修复
- Excluded scope: S1 初始实现的完整 re-review（已在初始 code review artifact 中覆盖）

## 之前 Findings 状态

### MiMo F01: InterruptibleProcessHandle.close() 硬编码 grace_seconds=0.2

**状态：已关闭。**

修复方式：
1. `InterruptibleProcessHandle.close()` 新增 `kill_grace_seconds` keyword-only 参数，默认值为 runtime-local 命名常量 `_DEFAULT_CLOSE_KILL_GRACE_SECONDS = 0.2`（`dayu/runtime/interruptible_process.py:240-243`）。
2. `close()` 内部调用 `_validate_grace_seconds(kill_grace_seconds)` 确保输入合法（`dayu/runtime/interruptible_process.py:256`）。
3. `ProcessBackedToolExecutionCapsule.close()` 显式传入 `self._interrupt_policy.kill_grace_seconds`（`dayu/host/tool_runtime.py:1877`），使 Host 层 close 路径使用 policy 值。
4. 测试验证：`test_process_backed_capsule_close_uses_interrupt_policy_kill_grace` 断言 capsule close 使用 policy 的 custom kill_grace_seconds（`tests/host/test_toolruntime_executor.py:1781-1800`）。
5. 测试验证：`test_interruptible_process_rejects_invalid_grace_seconds` 覆盖 `close(kill_grace_seconds=...)` 的 bool/negative/NaN/inf/-inf 拒绝（`tests/runtime/test_interruptible_process.py:137-139`）。

**直接证据**：`grep -n "grace_seconds=0.2" dayu/runtime/interruptible_process.py dayu/host/tool_runtime.py` 无命中。`grep -n "kill_grace_seconds" dayu/runtime/interruptible_process.py dayu/host/tool_runtime.py` 显示所有路径使用参数或 policy 值。

### MiMo F02: Host 层非字符串 hint 缺少专门测试

**状态：已关闭。**

修复方式：在 `test_process_backed_capsule_fail_closes_unsupported_envelopes` 的 parametrize 列表中新增用例：`{"status": "failed", "error_type": "err", "message": "msg", "hint": 123}` → `process_backed_tool_malformed_envelope`（`tests/host/test_toolruntime_executor.py:1755-1766`）。

**直接证据**：该测试直接覆盖 Host parser 对非字符串 hint 的 fail-closed 行为。

### AgentDS F01: close() 硬编码 grace 与 Host policy 不一致

**状态：已关闭。**

与 MiMo F01 相同 finding，已由同一修复关闭。`ProcessBackedToolExecutionCapsule.close()` 现在显式传入 `self._interrupt_policy.kill_grace_seconds`，使 close 路径的 grace 与 governed terminate/kill 路径一致。

## Fix 质量检查

### 1. Fix 是否引入 correctness 问题

- `InterruptibleProcessHandle.close()` 的 `kill_grace_seconds` 参数在 `_validate_grace_seconds(kill_grace_seconds)` 调用后才检查 `self._closed`。这意味着即使 handle 已关闭，非法输入仍会抛出异常。这是正确行为：fail-fast on invalid input, even for idempotent close。
- `ProcessBackedToolExecutionCapsule.close()` 传入 `self._interrupt_policy.kill_grace_seconds`。当 `interrupt_policy` 为 `None` 时，`__init__` 已将其替换为 `ProcessCapsuleInterruptPolicy()` 默认值，因此 `self._interrupt_policy` 始终非 `None`。
- 无 correctness 问题。

### 2. Fix 是否引入 architecture 问题

- `dayu.runtime.interruptible_process` 新增 `_DEFAULT_CLOSE_KILL_GRACE_SECONDS` 作为 runtime-local 默认值，不 import `dayu.host.tooling`。这是正确的分层：runtime 提供合理默认值，Host 层覆盖为 policy 值。
- `InterruptibleProcessHandle.close()` 的 `kill_grace_seconds` 参数是 keyword-only（`*` 后），不影响现有 `close()` 的无参调用签名兼容性。
- 无 architecture 问题。

### 3. Fix 是否引入 test 问题

- `_RecordingInterruptibleProcessHandle` 测试替身的 `close()` 签名与真实 `InterruptibleProcessHandle.close()` 一致（keyword-only `kill_grace_seconds`）。测试通过 `capsule._handle = cast(InterruptibleProcessHandle, handle)` 替换内部 handle，验证 capsule 层正确传递 policy 值。
- `_TEST_PROCESS_CLOSE_DEFAULT_GRACE_SECONDS = 1.0` 作为测试替身的默认值，与真实 runtime 默认值 `0.2` 不同，确保测试能区分"使用了默认值"和"使用了 policy 值"。
- `_CUSTOM_PROCESS_CLOSE_GRACE_SECONDS = 0.73` 是一个不会与任何默认值冲突的自定义值。
- 无 test 问题。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- 与初始 code review artifact 相同的 residual risks（S2A/S2B/S3 未实现部分），不重复列出。

## Conclusion

**PASS**

AgentCodex 的 code-review fix 正确关闭了 MiMo F01、MiMo F02 和 AgentDS F01。`InterruptibleProcessHandle.close()` 的 grace 现在通过参数化从 Host policy 值流入，硬编码 `0.2` 已替换为 runtime-local 命名常量作为默认值。Host 层 capsule close 显式传入 policy 的 `kill_grace_seconds`。非字符串 hint 在 Host 层有专门的 malformed 回归测试。Fix 未引入新的 correctness、architecture 或 test 问题。
