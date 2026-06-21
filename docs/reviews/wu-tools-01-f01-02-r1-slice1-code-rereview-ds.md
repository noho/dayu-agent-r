# Code Re-Review — WU-TOOLS-01-F01-02-R1 Slice 1

## Scope

- **Mode**: current changes (re-review of working tree fix diff against implementation checkpoint `6c930566`)
- **Branch**: `phase/wu-tools-01-f01-02-r1`
- **Reviewer**: AgentDS
- **Output file**: `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-rereview-ds.md`
- **Input artifacts**:
  - implementation: `docs/reviews/wu-tools-01-f01-02-r1-slice1-implementation-codex.md`
  - code review (AgentMiMo): `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-mimo.md`
  - code review (AgentDS): `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-ds.md`
  - controller adjudication: `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-controller-adjudication.md`
  - fix: `docs/reviews/wu-tools-01-f01-02-r1-slice1-fix-codex.md`
- **Re-review target**: controller accepted findings CR-F01, CR-F02, CR-F03 的修复正确性与最小性
- **Included scope**:
  - `dayu/host/tool_runtime.py` — activation failure warning 收紧、cancellation guard
  - `dayu/host/wait_adapter.py` — `WaitActivationRequest` defensive validation
  - `tests/host/test_toolruntime_executor.py` — 新增 focused regression tests
- **Excluded scope**:
  - CR-F04（deferred to Slice 2/3）
  - Slice 1 plan 重新挑战
  - Engine/Fins/Service 层代码

## Findings

未发现实质性问题。

## CR-F 逐项复核

### CR-F01: cancel-after-accept-before-activation 路径覆盖

**生产代码路径**（`dayu/host/tool_runtime.py:2763-2782`）：

```
accept_result = await self._accept_awaiting_with_retry(candidate)  # L2763
if isinstance(accept_result, ToolAwaitingAcceptedAck):              # L2764
    # ... record_duplicate_awaiting_accepted ...                      # L2768-2775
    if not context.cancellation_token.is_cancelled():                # L2776
        self._activate_accepted_wait_best_effort(...)                 # L2777
```

- `_accept_awaiting_with_retry` 内部调用 `awaiting_accept_port.accept_tool_awaiting(candidate)`，测试中的 `_CancellingAwaitingAcceptPort` 在该调用返回 `ToolAwaitingAcceptedAck` 后立即翻转同一个 `CancellationToken`。
- 控制流回到 `_accept_awaiting` 后，`record_duplicate_awaiting_accepted` 不重查取消状态，于 L2776 检查 `context.cancellation_token.is_cancelled()` → `True`，跳过 L2777 的 activation 调用。

**测试**（`tests/host/test_toolruntime_executor.py:1198-1223`）：

- `test_cancel_after_awaiting_accept_skips_activation` 使用 `_CancellingAwaitingAcceptPort`（L541-543: ack 后 `cancel("cancel-after-awaiting-accept")`）。
- 断言 `cancellation_token.is_cancelled()` 为 `True`（L1221），outcome 类型仍为 `ToolAwaitingOutcome`（L1222），`activation_adapter.requests == []`（L1223）。
- `_CancellingAwaitingAcceptPort` 与 executor 共享同一个 `_MutableCancellationToken`，确保是**同一个** token 被翻转。

**结论**：修复正确、最小，直接覆盖 accepted-ack 后 activation 前的取消 interleaving。测试不引入新的调度器、生命周期抽象或并发框架。

### CR-F02: activation failure warning 收紧

**生产代码变更**（`dayu/host/tool_runtime.py:2835-2847`）：

- L2836-2846 warning log **不再**包含 `exc_info=True`，仅记录有界 metadata：`session_id`、`run_id`、`attempt_id`、`tool_name`、`adapter_key`、`error_type`（`exc.__class__.__name__`）。
- Diagnostic 路径未变：`_emit_wait_activation_diagnostic_best_effort`（L2849-2875）仍只使用 `exc.__class__.__name__` 构造 diagnostic message，不包含 raw exception message。
- Diagnostic emitter 自身失败路径（L2867-2874）的 `exc_info=True` 保留不动——该路径处理的是 diagnostic emitter 故障，不属于本次 CR-F02 范围。

**测试**（`tests/host/test_toolruntime_executor.py:1227-1264`）：

- `test_awaiting_activation_failure_keeps_accepted_awaiting_outcome` 使用 `caplog` 断言：
  - `"raw-provider-job-secret" not in diagnostics.records[0].message`（L1257）——diagnostic 通道不泄漏
  - `"raw-provider-job-secret" not in caplog.text`（L1264）——warning log 通道不泄漏
  - `"RuntimeError" in diagnostics.records[0].message`（L1256）——异常类名仍在 diagnostic 中
  - `"RuntimeError" in caplog.text`（L1258）——异常类名仍在 log 中
  - Bounded metadata 均在 log 中（L1259-1263）：session_id、run_id、attempt_id、tool_name、adapter_key
- Outcome 仍为 `ToolAwaitingOutcome`（L1252）——accepted awaiting 不被覆盖

**结论**：修复正确、最小。warning log 不再通过 `exc_info=True` 或 raw exception message 泄漏 provider-like 消息；diagnostic 有界；accepted awaiting outcome 不被覆盖。

### CR-F03: WaitActivationRequest defensive validation 测试

**生产代码 validation**（`dayu/host/wait_adapter.py:115-125`）：

```python
def __post_init__(self) -> None:
    if self.tool_name.strip() == "":                           # L122
        raise ValueError("tool_name must be non-empty")
    if not isinstance(self.await_spec, ToolAwaitSpec):         # L124
        raise ValueError("await_spec must be ToolAwaitSpec")
```

**测试**（`tests/host/test_toolruntime_executor.py:1267-1286`）：

- `test_wait_activation_request_rejects_empty_tool_name`（L1267）：`tool_name=" "`（strip 后为空），断言 `ValueError` + `match="tool_name"`。
- `test_wait_activation_request_rejects_invalid_await_spec`（L1278）：`await_spec=cast(ToolAwaitSpec, "invalid-await-spec")`，断言 `ValueError` + `match="await_spec"`。
- 两个测试均不引入新 fixture、不扩展 runtime contract、不添加兼容逻辑。

**结论**：修复正确、最小。仅覆盖既有 defensive validation 分支，无 contract expansion。

### Slice 1 禁止 activation 路径完整性

全部拒绝/失败/取消路径的 activation 禁止行为保持完整，且均有 `activation_adapter.requests == []` 断言：

| 路径 | 测试函数（行号） | 断言 |
|------|-----------------|------|
| pre-cancelled context | `test_tool_runtime_pre_cancelled_context_returns_governed_failure` (L1106) | L1132: `== []` |
| accept rejected (idempotency) | `test_awaiting_accept_rejected_returns_governed_error` (L1396) | L1451: `== []` |
| stale execution rejection | `test_stale_execution_awaiting_rejection_does_not_activate_wait` (L1455) | L1510: `== []` |
| accept timeout | `test_awaiting_accept_timeout_returns_governed_error` (L1514) | L1570: `== []` |
| retry exhausted | `test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref` (L1574) | L1602: `== []` |
| missing adapter binding | `test_awaiting_outcome_without_adapter_binding_is_governed_error` (L1373) | L1392: `== []` |
| missing external job ref | `test_poll_awaiting_without_external_job_ref_is_governed_error` (L1623) | L1644: `== []` |
| sync timeout from accept port | `test_sync_timeout_error_from_awaiting_accept_port_is_not_caught` (L1606) | 直接 raise，不进入 `_accept_awaiting` |
| cancel after accept (CR-F01) | `test_cancel_after_awaiting_accept_skips_activation` (L1198) | L1223: `== []` |

重复 fanout 路径只触发 owner 一次 activation（`test_concurrent_duplicate_awaiting_fanout_does_not_start_second_job`，L1648，L1683: `len == 1`）。

### Scope creep / 过度设计检查

- **跨层 import**：无。`dayu/host/wait_adapter.py` 和 `dayu/host/tool_runtime.py` 的 import 限定在 `dayu.contracts`、`dayu.host.*`、`dayu.runtime.*`，不引入 `dayu.engine`、`dayu.fins`、`dayu.service`。
- **新增类型**：
  - `WaitActivationRequest`：frozen dataclass，3 字段 + `__post_init__`，与 `WaitAdapterBinding.__post_init__` 模式一致。
  - `WaitActivationAdapter`：单方法 Protocol，与 `WaitResolvePort`、`WaitPollClock` 等已有 Protocol 模式一致。
  - `WaitActivationAdapterRegistration`：frozen dataclass，2 字段，与 `WaitPollAdapterRegistration` 一致。
  - `WaitActivationRegistry`：dict-based registry + `resolve_adapter`，代码结构与 `WaitPollAdapterRegistry` 一致。
- **配置状态**：`wait_activation_registry=None` 时 `_wait_activation_registry is None → return` 直接 no-op，不改变现有行为。
- **LLM-facing contract**：无变更。activation diagnostic 仅进入 Host-internal `ToolTraceDiagnosticEmitter`，不附加到 `ToolAwaitingOutcome`。

## Open Questions

无。

## Residual Risk

1. **cancel-after-accept 并发竞态仅在单线程模拟下测试**：`_CancellingAwaitingAcceptPort` 在 `accept_tool_awaiting` 同步调用链中翻转 token，不模拟真实并发调度下的异步取消。当前 guard 逻辑简单（单 bool 检查），且 `_MutableCancellationToken` 本身不是线程安全实现——但在当前单线程 asyncio 模型下该限制不构成真实风险。若未来引入多线程调度需重新评估。

2. **CR-F04 deferred**：Fins adapter 访问 `ToolAwaitingAcceptedAck` 的治理字段（`wait_id`、`accepted_event_refs`、`idempotency_record_ref`）的泄漏风险由 Slice 2/3 的 Fins adapter 实现负责。当前 Slice 1 不裁决。

3. **`host.tool_runtime.wait_activation_diagnostic_failed` warning 仍保留 `exc_info=True`**：这是 diagnostic emitter 自身故障的日志路径（`tool_runtime.py:2874`），非 CR-F02 要求的 activation failure path。若需进一步收紧可独立评估。

4. **37 tests passed，pyright 0/0/0**。无类型错误、无测试失败。

## Conclusion

**Pass**。三个 controller accepted findings（CR-F01、CR-F02、CR-F03）均被正确、最小地修复：

- CR-F01：新增 focused test `test_cancel_after_awaiting_accept_skips_activation`，直接覆盖 accepted ack 后 activation 前取消 interleaving，断言 activation 不执行。
- CR-F02：移除 activation failure warning 的 `exc_info=True`，warning 仅保留有界 metadata；test 经 `caplog` 双向断言 diagnostic 和 log 均不含 raw provider exception message。
- CR-F03：新增两个 focused test 覆盖 `WaitActivationRequest` 空 `tool_name` 和非法 `await_spec` 的 `ValueError`。
- 原 Slice 1 全部禁止 activation 路径保持完整且持续有测试保护。
- 无 scope creep、无过度设计、无跨层 import、无 LLM-facing contract 泄漏。
