# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f01-02-r1`
- Base: `6c930566` (implementation checkpoint commit)
- Output file: `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-mimo.md`
- Included scope:
  - `dayu/host/wait_adapter.py` — Host activation contract 与 registry
  - `dayu/host/tool_runtime.py` — ToolRuntimeExecutor activation 集成
  - `tests/host/test_toolruntime_executor.py` — activation 行为测试
- Excluded scope:
  - `docs/host/issues-implementation-control.md` — 仅作状态上下文
  - `docs/reviews/wu-tools-01-f01-02-r1-slice1-implementation-codex.md` — Codex implementation artifact，不纳入 findings
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **`wait_activation_registry=None` 且 awaiting path 正常配置时的无 activation 行为未被显式测试。** 当前测试覆盖了 `wait_adapter_registry=None`（返回 governed error）和 `wait_activation_registry` 已配置（正常 activation），但未覆盖 `wait_adapter_registry` 已配置 + `wait_activation_registry=None` 的组合。实现代码在 `_activate_accepted_wait_best_effort` 第一行 `if self._wait_activation_registry is None: return` 正确处理了此路径，行为是 no-op。风险低，但建议后续补充一个显式测试断言此组合下 `ToolAwaitingOutcome` 正常返回且无 activation 调用。

- **`_SpyWaitActivationAdapter` 未显式声明 `WaitActivationAdapter` Protocol conformance。** 测试通过 duck typing 兼容 Protocol，当前可行。若 `WaitActivationAdapter` Protocol 将来增加方法，测试 adapter 不会静态报错。风险极低。

- **`exc_info=True` 在 `_activate_accepted_wait_best_effort` 的 warning 日志中包含完整 traceback。** 这是 Host 内部日志，不投影给 LLM 或用户，符合当前设计。但若 activation adapter 的 traceback 包含 provider 内部状态，日志收集系统需确保访问控制。风险低，属于运维关注项。

- **后续 slice 依赖点：** Fins prepare/activate two-phase runtime、Service wiring 注入 `WaitActivationRegistry`、activation idempotency、activation failure 后 observation terminal state 等行为由后续 approved slice 覆盖，不在本 slice review 范围内。

## Conclusion

**pass**

实现严格满足 review 重点要求：

1. **activation 只在 Host durable accepted wait ack 之后执行。** `_accept_awaiting` 中 activation 调用位于 `if isinstance(accept_result, ToolAwaitingAcceptedAck)` 分支内，且被 `context.cancellation_token.is_cancelled()` 守卫。rejected/timeout/missing binding/missing external job/pre-cancel/fanout waiter/stale execution 等路径均不触发 activation。

2. **activation 异常只产生有界诊断，不泄漏 raw provider/job message。** `_activate_accepted_wait_best_effort` 捕获所有异常，diagnostic message 只包含 `exc.__class__.__name__`，不包含异常消息体。`_emit_wait_activation_diagnostic_best_effort` 对 diagnostic emitter 自身异常也做了二次捕获。accepted awaiting outcome 不受影响。

3. **Host 接口设计最小化、可测试。** `WaitActivationAdapter` 是单方法 Protocol，`WaitActivationRequest` 是 frozen dataclass with `__post_init__` validation。Registry 复用 `WaitAdapterKey`，construction-time wiring，无 Engine/LLM-facing contract 泄漏。

4. **无 Engine/Fins/Service scope creep。** 变更限定在 `dayu/host/wait_adapter.py` 和 `dayu/host/tool_runtime.py`，无跨层 import。

5. **测试真正证明上述行为。** 覆盖 accepted、rejected、timeout、retry exhausted、missing binding、missing external job ref、pre-cancelled context、duplicate awaiting fanout waiter、stale execution rejected 和 activation exception 路径，共 34 tests passed。
