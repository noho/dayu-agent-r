# WU-TOOLS-CANCEL-01 Residual Hardening S1 Re-Review - AgentDS

## Scope

- Mode: targeted re-review（after AgentCodex code-review fix）
- Branch: `phase/wu-tools-cancel-01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-rereview-ds.md`
- Included scope: fix for DS-01 low finding, fix for MiMo F01/F02, verification that no new correctness/architecture/test issues were introduced.
- Excluded scope: S2A/S2B/S3/S4（按计划未实现），S1 原实现中已 PASS 的链路（未重新走读）。
- Prior review artifacts referenced:
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-code-review-ds.md`（DS initial review）
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-code-review-mimo.md`（MiMo initial review）
  - `docs/reviews/wu-tools-cancel-01-residual-hardening-s1-implementation-codex.md`（Codex implementation + fix report）

## Findings Verification

### DS-01 / MiMo-F01: `InterruptibleProcessHandle.close()` 硬编码 `grace_seconds=0.2`

**状态：已关闭**

证据：

1. `dayu/runtime/interruptible_process.py:22`：新增模块级命名常量 `_DEFAULT_CLOSE_KILL_GRACE_SECONDS: Final[float] = 0.2`，不再使用裸字面量。
2. `dayu/runtime/interruptible_process.py:240-243`：`close()` 方法签名改为 `close(self, *, kill_grace_seconds: float = _DEFAULT_CLOSE_KILL_GRACE_SECONDS)`，接受可选的 keyword 参数，默认值来自命名常量。
3. `dayu/runtime/interruptible_process.py:258`：close 路径先调用 `_validate_grace_seconds(kill_grace_seconds)`，然后传入 `self.kill(grace_seconds=kill_grace_seconds)`——不再硬编码 `0.2` 字面量。
4. `dayu/host/tool_runtime.py:1876-1878`：`ProcessBackedToolExecutionCapsule.close()` 显式传入 `self._interrupt_policy.kill_grace_seconds`：
   ```python
   await self._handle.close(
       kill_grace_seconds=self._interrupt_policy.kill_grace_seconds
   )
   ```
5. `tests/host/test_toolruntime_executor.py:1784-1808`：新增 `test_process_backed_capsule_close_uses_interrupt_policy_kill_grace`，通过 `_RecordingInterruptibleProcessHandle` 记录 close 收到的 `kill_grace_seconds`，断言等于 `ProcessCapsuleInterruptPolicy` 的自定义值 `0.73`。
6. `tests/runtime/test_interruptible_process.py:117-142`：`test_interruptible_process_rejects_invalid_grace` 扩展参数化，`close(kill_grace_seconds=...)` 路径与 `terminate`/`kill` 路径一起覆盖 bool/negative/NaN/inf/-inf 拒绝。

**评估**：close() 路径的 grace 值现在有三种真源层次：
- **runtime 层直接调用**：默认 `_DEFAULT_CLOSE_KILL_GRACE_SECONDS`（`0.2`），best-effort，可被调用方覆盖。
- **Host capsule 调用**：显式传入 `ProcessCapsuleInterruptPolicy.kill_grace_seconds`，由 Host policy 治理。
- **验证层**：所有路径均通过 `_validate_grace_seconds` 校验，拒绝非法值。

两处默认值（`_DEFAULT_CLOSE_KILL_GRACE_SECONDS` 和 `ProcessCapsuleInterruptPolicy.kill_grace_seconds` 默认 `0.2`）数值仍然相同但属于不同层的独立 default——这是架构约束（runtime 不能 import Host）的合理结果，不再构成维护风险。close() 的 Host 调用路径已与 policy 单一定义的真源（`ProcessCapsuleInterruptPolicy`）绑定。

### MiMo-F02: Host 层非字符串 hint 映射缺少独立测试

**状态：已关闭**

证据：

1. `tests/host/test_toolruntime_executor.py:1758-1765`：在 `test_process_backed_capsule_fail_closes_unsupported_envelopes` 的 parametrize 中新增用例：
   ```python
   (
       {"status": "failed", "error_type": "err", "message": "msg", "hint": 123},
       "process_backed_tool_malformed_envelope",
   )
   ```
   该用例直接传入 `hint: 123`（整数），断言 Host 层将其映射为 `process_backed_tool_malformed_envelope` 错误。

**评估**：该用例覆盖了 contracts parser 的 hint 校验结果通过 `ProcessToolMalformedEnvelope` → `_tool_outcome_from_process_envelope` → `_malformed_process_envelope_outcome` 的完整 Host 层映射路径。即使 contracts parser 的 hint 校验将来被误改，Host 层测试也会通过 contracts parser 的返回类型变化触发回归。

## New Issue Check

按以下维度检查 fix 自身是否引入新问题：

### 1. Correctness

- `InterruptibleProcessHandle.close()` 新增 `_validate_grace_seconds(kill_grace_seconds)` 调用 → 与 `terminate`/`kill` 方法的校验一致，不改变现有语义。
- `close()` 默认参数 `_DEFAULT_CLOSE_KILL_GRACE_SECONDS = 0.2` 保持向后兼容——不传参数时行为与 fix 前完全一致。
- `ProcessBackedToolExecutionCapsule.close()` 现在传入 `self._interrupt_policy.kill_grace_seconds` → 若 policy 值为 0.5，close 等待时间从 0.2 变为 0.5，这是预期行为（best-effort cleanup 使用相同的 cleanup 时间预算）。

### 2. Architecture

- `dayu.runtime.interruptible_process`：仍不 import Host/Engine/Service/UI/Fins。`_DEFAULT_CLOSE_KILL_GRACE_SECONDS` 是 runtime-local 命名常量，不引用 Host policy。✅
- `dayu.host.tool_runtime`：不 import 具体工具。`ProcessCapsuleInterruptPolicy` 来自 `dayu.host.tooling`（同层 Host internal）。✅
- `dayu.contracts`：未修改。✅

### 3. Test Quality

- `test_process_backed_capsule_close_uses_interrupt_policy_kill_grace`：通过 monkey-patching `capsule._handle` 注入 `_RecordingInterruptibleProcessHandle` 来观察 close 的 grace 参数。这是测试内部替身，不泄漏到生产路径，可接受。但 `cast(InterruptibleProcessHandle, handle)` 的 cast 绕过了类型检查——这是因为 `_RecordingInterruptibleProcessHandle` 没有正式实现 `InterruptibleProcessHandle` 接口。作为测试内部实现，不影响生产类型安全。
- `test_interruptible_process_rejects_invalid_grace`：新增 close 路径的参数化覆盖，与 terminate/kill 使用相同的非法值集合，一致性良好。

### 4. 无新问题

未发现 fix 引入新的 correctness、architecture 或 test 缺陷。

## Open Questions

无。

## Residual Risk

- 同原 DS review 的 residual risk（S2A/S2B/S3 未实现，具体工具未迁移）——不在 re-review scope 内。
- `_RecordingInterruptibleProcessHandle` 的 `cast(InterruptibleProcessHandle, handle)` 是测试内部类型绕路，不会传播到生产代码，但若 `InterruptibleProcessHandle.close()` 签名再次变更，该测试可能静默失效（因为 cast 抑制了类型检查）。建议在 S4 或后续 slice 中考虑使用 Protocol 或 ABC 规范化测试 handle 接口。

## Conclusion

**PASS**

DS-01 和 MiMo-F01/F02 三个 finding 均已关闭。fix 正确地解决了 close() grace 硬编码问题（runtime 层提供可覆盖的命名默认，Host capsule 显式传入 policy 值），补全了 Host 层非字符串 hint 的 malformed 回归用例。无新增 correctness/architecture/test 问题。202 个相关测试通过，pyright 零错误。
