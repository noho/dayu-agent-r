# Code Re-Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f01-02-r1`
- Base: `6c930566` (implementation checkpoint)
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-rereview-mimo.md`
- Included scope:
  - `dayu/host/wait_adapter.py` — Host activation contract 与 registry
  - `dayu/host/tool_runtime.py` — ToolRuntimeExecutor activation 集成
  - `tests/host/test_toolruntime_executor.py` — activation 行为测试
- Excluded scope:
  - `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-ds.md` — 另一路 reviewer artifact，按指令忽略
  - `docs/host/issues-implementation-control.md` — 仅作状态上下文
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### CR-F01 验证：accepted ack 后、activation 前 cancellation 变 true 时 activation 不执行

- **修复正确性**：`_CancellingAwaitingAcceptPort.accept_tool_awaiting` 在返回 `ToolAwaitingAcceptedAck` 后、方法返回前，同步调用 `cancellation_token.cancel(...)` 翻转同一 token。`_accept_awaiting` 中 `_accept_awaiting_with_retry` 返回后，`_record_duplicate_awaiting_accepted` 执行完毕，到达 `if not context.cancellation_token.is_cancelled():`（`tool_runtime.py:2776`）时 token 已为已取消状态，activation 被跳过。
- **测试有效性**：`test_cancel_after_awaiting_accept_skips_activation` 断言 `cancellation_token.is_cancelled() == True`、`record.outcome` 仍为 `ToolAwaitingOutcome`（accepted ack 不受影响）、`activation_adapter.requests == []`（activation 未执行）。测试是确定性的——取消发生在同一同步调用帧内，无并发竞态依赖。
- **最小性**：仅新增一个 focused 测试、两个测试辅助类（`_MutableCancellationToken`、`_CancellingAwaitingAcceptPort`），不涉及生产代码变更。
- **结论**：CR-F01 修复正确且最小。

### CR-F02 验证：activation failure warning 不再泄漏 raw exception payload

- **修复正确性**：`_activate_accepted_wait_best_effort` 的 warning 日志（`tool_runtime.py:2836-2846`）已移除 `exc_info=True`，仅保留有界 metadata：`session_id`、`run_id`、`attempt_id`、`tool_name`、`adapter_key`、`error_type`（`exc.__class__.__name__`）。diagnostic message（`tool_runtime.py:2861-2863`）同样只含 `exc.__class__.__name__`。
- **测试有效性**：`test_awaiting_activation_failure_keeps_accepted_awaiting_outcome` 使用 `caplog` 断言 `"raw-provider-job-secret" not in caplog.text`，同时验证 warning log 仍包含 `RuntimeError`、`session_id`、`run_id`、`attempt_id`、`fake_tool`、`poll:fake-tool` 等有界 metadata。diagnostic message 同样断言不含 raw message。
- **边界确认**：`_emit_wait_activation_diagnostic_best_effort` 的 `except Exception` 分支（`tool_runtime.py:2867-2875`）仍保留 `exc_info=True`，但该路径捕获的是 diagnostic emitter 自身异常（非 adapter 异常），controller 裁决仅要求收紧 activation failure warning 路径，不涉及此 secondary path。行为正确。
- **accepted awaiting outcome 不被覆盖**：测试断言 `isinstance(record.outcome, ToolAwaitingOutcome)`，确认 activation 异常不影响返回给 Engine 的 outcome。
- **结论**：CR-F02 修复正确且最小。

### CR-F03 验证：WaitActivationRequest 空 tool_name / invalid await_spec ValueError 测试

- **修复正确性**：`WaitActivationRequest.__post_init__`（`wait_adapter.py:115-125`）对空 `tool_name`（`strip() == ""`）和非 `ToolAwaitSpec` 类型 `await_spec` 抛出 `ValueError`。两个新测试直接覆盖这两个分支。
- **测试有效性**：`test_wait_activation_request_rejects_empty_tool_name` 传入 `tool_name=" "`（空白），断言 `ValueError` 匹配 `"tool_name"`。`test_wait_activation_request_rejects_invalid_await_spec` 使用 `cast(ToolAwaitSpec, "invalid-await-spec")` 绕过类型检查，断言 `ValueError` 匹配 `"await_spec"`。
- **最小性**：纯测试补充，不扩展 runtime contract，不增加兼容逻辑。
- **结论**：CR-F03 修复正确且最小。

### 原 Slice 1 禁止 activation 路径复核

以下路径在 fix diff 中均有显式 `assert activation_adapter.requests == []` 断言：

| 路径 | 测试 | 断言 |
|------|------|------|
| pre-cancelled context | `test_tool_runtime_pre_cancelled_context_returns_governed_failure` | `activation_adapter.requests == []` |
| missing adapter binding | `test_awaiting_outcome_without_adapter_binding_is_governed_error` | `activation_adapter.requests == []` |
| missing external job ref | `test_poll_awaiting_without_external_job_ref_is_governed_error` | `activation_adapter.requests == []` |
| awaiting accept rejected | `test_awaiting_accept_rejected_returns_governed_error` | `activation_adapter.requests == []` |
| stale execution rejected | `test_stale_execution_awaiting_rejection_does_not_activate_wait`（新增） | `activation_adapter.requests == []` |
| awaiting accept timeout | `test_awaiting_accept_timeout_returns_governed_error` | `activation_adapter.requests == []` |
| retry exhaustion | `test_awaiting_accept_retry_exhaustion_emits_diagnostic_ref` | `activation_adapter.requests == []` |
| cancel-after-accept | `test_cancel_after_awaiting_accept_skips_activation`（新增） | `activation_adapter.requests == []` |
| activation failure | `test_awaiting_activation_failure_keeps_accepted_awaiting_outcome`（新增） | outcome 仍为 `ToolAwaitingOutcome` |

所有原 Slice 1 禁止 activation 路径仍成立。

### Architecture boundary / scope creep 复核

- 变更限定在 `dayu/host/wait_adapter.py`、`dayu/host/tool_runtime.py`、`tests/host/test_toolruntime_executor.py`，无 Engine/Fins/Service import 或实现泄漏。
- `WaitActivationAdapter` 是 Host 定义的单方法 Protocol，Fins 通过 `WaitActivationRegistry` 注入实现——符合依赖倒置。
- `WaitActivationRequest` 是 frozen dataclass，`__post_init__` 验证不扩展 runtime contract。
- 无过度设计：复用现有 `WaitAdapterKey`、construction-time wiring、`WaitPollAdapterRegistry` 模式。

### 测试验证

- `pytest tests/host/test_toolruntime_executor.py -q`：**37 passed in 0.29s**（fix 前 34 passed）。
- `pyright`：**0 errors, 0 warnings, 0 informations**。

## Open Questions

无。

## Residual Risk

- **`WaitActivationRegistry` 重复 key 拒绝未测试**：`WaitActivationRegistry.__init__` 中 `ValueError("duplicate wait activation adapter registration")` 分支未被测试。风险：低——该模式与 `WaitPollAdapterRegistry` 完全一致，后者已有生产路径覆盖。
- **`WaitActivationRegistry.resolve_adapter` 返回 `None` 未直接测试**：registry 有 adapter A 而 binding key 为 B 时 adapter 解析为 `None` 的路径未专门断言。风险：极低——此 guard 是 `_activate_accepted_wait_best_effort` 中 `if adapter is None: return` 的直接条件返回。
- **`_emit_wait_activation_diagnostic_best_effort` 仍使用 `exc_info=True`**：该路径捕获 diagnostic emitter 自身异常（非 adapter 异常），controller 裁决未要求修改。风险：极低——双故障场景，log 中 `wait_activation_diagnostic_failed` 可供电排障。
- **后续 slice 依赖点**：Fins prepare/activate two-phase runtime、Service wiring 注入 `WaitActivationRegistry`、activation idempotency、activation failure 后 observation terminal state 等行为由后续 approved slice 覆盖。

## Conclusion

**pass**

CR-F01、CR-F02、CR-F03 均被正确、最小地修复：

1. **CR-F01**：新增 `test_cancel_after_awaiting_accept_skips_activation`，通过 `_CancellingAwaitingAcceptPort` 在返回 accepted ack 后同步翻转 cancellation token，确定性覆盖 ack 后取消 interleaving。生产代码无变更。
2. **CR-F02**：移除 `_activate_accepted_wait_best_effort` 中 activation failure warning 的 `exc_info=True`，warning 只保留有界 metadata。测试通过 `caplog` 断言 raw provider-like message 不进入 warning log。diagnostic 路径同样有界。accepted awaiting outcome 不受影响。
3. **CR-F03**：新增 `test_wait_activation_request_rejects_empty_tool_name` 和 `test_wait_activation_request_rejects_invalid_await_spec`，直接覆盖 `__post_init__` 两个 `ValueError` 分支。不扩展 runtime contract。

37 tests passed，pyright 0 errors。未发现新 correctness/stability/maintainability 回归。
