# Code Review — WU-TOOLS-01-F01-02-R1 Slice 1

## Scope

- **Mode**: current changes (working tree diff against implementation checkpoint `6c930566`)
- **Branch**: `phase/wu-tools-01-f01-02-r1`
- **Base checkpoint**: `6c930566` (implementation gate entry)
- **Accepted plan commit**: `478f5f77`
- **Output file**: `docs/reviews/wu-tools-01-f01-02-r1-slice1-code-review-ds.md`
- **Reviewer**: AgentDS
- **Included scope**:
  - `dayu/host/wait_adapter.py` — 新增 `WaitActivationRequest`、`WaitActivationAdapter`、`WaitActivationAdapterRegistration`、`WaitActivationRegistry`
  - `dayu/host/tool_runtime.py` — 扩展 `ToolRuntimeBuildRequest` 与 `ToolRuntimeExecutor`，注入 `wait_activation_registry`，新增 `_activate_accepted_wait_best_effort` 与 `_emit_wait_activation_diagnostic_best_effort`
  - `tests/host/test_toolruntime_executor.py` — 新增 spy adapter、activation registry fixture，注入到全部 awaiting 相关测试并追加 activation 断言
  - `docs/host/issues-implementation-control.md` — gate 状态推进（仅作上下文，不作为 implementation finding 目标）
- **Excluded scope**:
  - `docs/reviews/wu-tools-01-f01-02-r1-slice1-implementation-codex.md`（另一路 reviewer artifact，按指令忽略）
  - 已提交的 plan/doc checkpoint（`478f5f77`、`6c930566`）
  - Slice 2/3 Fins prepare/activate、Service wiring（不在当前 workspace diff 中）
- **Parallel review coverage**: 无，本次为单人 review。

## Findings

### 1. 未修复-低-cancel-after-accept-before-activation 路径无直接测试覆盖

- **入口/函数**: `ToolRuntimeExecutor._accept_awaiting` → `_activate_accepted_wait_best_effort`
- **文件(行号)**: `dayu/host/tool_runtime.py:2776`
- **输入场景**: `_accept_awaiting_with_retry(candidate)` 返回 `ToolAwaitingAcceptedAck` 后，但在执行 `context.cancellation_token.is_cancelled()` 检查前，并发 cancellation 使 token 变为已取消。
- **实际分支**: `if not context.cancellation_token.is_cancelled():` 为 `False`，跳过 activation。
- **预期行为**: 不执行 activation——当前代码行为正确。
- **实际行为**: 行为正确，但该防御分支无测试直接覆盖。
- **直接证据**:
  - `tool_runtime.py:2776`: `if not context.cancellation_token.is_cancelled():` 是 accepted ack 路径中 activation 的唯一门禁。
  - 现有 `test_tool_runtime_pre_cancelled_context_returns_governed_failure` (line 1033) 测试的是 callable 执行前取消——此时 `_dispatch_tool_call_with_bounds` 返回 `ToolFailedOutcome` 而非 `ToolAwaitingOutcome`，根本不会进入 `_accept_awaiting`。
  - 取消发生在 accept ack 之后、activation 之前的并发竞态路径没有对应测试。
- **影响**: 该 guard 逻辑正确性未被测试直接证明。若未来重构误删或绕过了此检查（例如把 activation 调用移到 `is_cancelled()` 检查之前），测试不会发现。
- **建议改法和验证点**: 考虑增加测试：使用可编程 token（能在 accept ack 返回后、activation 调用前被取消），断言 activation 不执行。若当前测试 harness 难以构造此并发场景，可在 plan residual risk 中记录该缺口，不作为 Slice 1 阻塞项。
- **修复风险（低）**: 纯测试补充，不涉及生产代码变更。
- **严重程度（低）**: 生产代码行为正确，guard 逻辑简单直白；缺失的是并发 race 路径的回归保护。

### 2. 未修复-低-`exc_info=True` 记录完整 traceback 到日志

- **入口/函数**: `ToolRuntimeExecutor._activate_accepted_wait_best_effort`
- **文件(行号)**: `dayu/host/tool_runtime.py:2836-2847`
- **输入场景**: activation adapter 抛出异常，且异常消息包含 raw provider/job 内部信息（如 `RuntimeError("raw-provider-job-secret")`）。
- **实际分支**: `except Exception as exc:` 捕获异常，执行 `_LOGGER.warning(... exc_info=True ...)`。
- **预期行为**: LLM-facing 诊断有界（仅含异常类名），日志作为非 LLM-facing 通道可接受更多细节，但 `exc_info=True` 会将完整异常链（包括可能含敏感数据的消息）写入日志。
- **实际行为**: 诊断 emitter 的消息是 `"wait activation adapter failed after accepted wait: RuntimeError"`——有界且正确。但日志中 `exc_info=True` 附加了完整 traceback 和异常消息，若 adapter 异常消息包含 raw provider/job 内部信息，这些信息会出现在日志中。
- **直接证据**:
  - `tool_runtime.py:2846`: `exc_info=True` 在第 2846 行，将完整异常信息传递给 Python logging 框架。
  - 测试 `test_awaiting_activation_failure_keeps_accepted_awaiting_outcome` (line 1122) 验证 diagnostic message 不含 `"raw-provider-job-secret"`——但这只覆盖 diagnostic 通道，不覆盖日志通道。
- **影响**: 若 adapter 异常消息含敏感信息，日志文件可能泄漏。但日志并非 LLM-facing 通道，且 `exc_info` 是标准的 Python 排障实践。影响有限。
- **建议改法和验证点**: 按项目自身对日志敏感度的要求判断是否需要减弱日志内容。若需保守处理，可改为仅 log `error_type=%s` 而不传 `exc_info=True`，或由 adapter 契约要求异常消息本身不携带 raw 内容。当前实现与同文件中 `_record_duplicate_durable_missing_best_effort` (line 2493-2503) 的日志策略一致。
- **修复风险（低）**: 仅调整日志参数，不影响业务行为。
- **严重程度（低）**: 日志通道非 LLM-facing；与现有代码模式一致；adapter 契约可约束异常消息内容。

### 3. 未修复-低-`WaitActivationRequest.__post_init__` 验证未单独测试

- **入口/函数**: `WaitActivationRequest.__post_init__`
- **文件(行号)**: `dayu/host/wait_adapter.py:115-125`
- **输入场景**: 构造 `WaitActivationRequest` 时传入空 `tool_name` 或非 `ToolAwaitSpec` 类型的 `await_spec`。
- **实际分支**: `__post_init__` 中 `if self.tool_name.strip() == ""` 或 `if not isinstance(self.await_spec, ToolAwaitSpec)` 为真，抛出 `ValueError`。
- **预期行为**: 抛出 `ValueError`。
- **实际行为**: 行为正确（抛出 `ValueError`），但该验证逻辑未被单元测试覆盖。
- **直接证据**:
  - `wait_adapter.py:119-125`: 两个 `ValueError` 分支无对应测试。
  - 在实际调用链中（`tool_runtime.py:2828-2832`），`tool_name` 来自 `call.name`（始终非空），`await_spec` 来自 `awaiting_outcome.await_spec`（始终为 `ToolAwaitSpec`），因此这些防御检查在正常路径不会触发。
  - 若构造错误导致 `ValueError`，会被 `_activate_accepted_wait_best_effort` 的 `except Exception` 捕获，被记录为 "activation failure"——与 adapter 异常混为一谈。
- **影响**: 防御性验证的测试缺口。若构造错误被误归类为 activation adapter 异常，diagnostic 消息 `"wait activation adapter failed after accepted wait: ValueError"` 会误导排障方向，但不会影响业务正确性（accepted awaiting outcome 仍正常返回）。
- **建议改法和验证点**: 可增加两行参数化测试：`WaitActivationRequest(tool_name="  ", ...)` 和 `WaitActivationRequest(tool_name="x", await_spec="not_a_spec", ...)` 断言 `ValueError`。也可以在接受当前测试覆盖级别，因为实际调用链不会触发这些分支。
- **修复风险（低）**: 纯测试补充。
- **严重程度（低）**: 防御性代码，生产路径不会触发；与同文件中 `WaitAdapterBinding.__post_init__` 保持一致的验证模式。

## Open Questions

- **`ToolAwaitingAcceptedAck` 经 `WaitActivationRequest` 传递给 Fins activation adapter 是否构成跨层信息泄漏？** 当前设计：`WaitActivationAdapter` 是 Host 定义在 `dayu.host.wait_adapter` 的 Protocol，Fins 通过 `WaitActivationRegistry` 注入实现。`ToolAwaitingAcceptedAck` 是 Host waiting 层的内部类型，通过 `TYPE_CHECKING` 保护避免循环导入。这符合依赖倒置——Host 定义接口，Fins 实现。但 `ToolAwaitingAcceptedAck` 包含 Host 治理内部字段（`wait_id`、`accepted_event_refs`、`idempotency_record_ref`），Fins adapter 获得这些字段的访问权。需确认 Slice 2 的 Fins adapter 实现不会将这些治理标识泄漏到 observation 记录或 LLM-facing 输出。当前 Slice 1 不做裁决——adapter 在 Slice 1 中只以测试 spy 存在。

## Residual Risk

1. **cancel-after-accept-before-activation 并发竞态未测试**（见 Finding 1）。风险：极低——guard 逻辑简单，且当前测试 harness 构造此场景成本高。
2. **`WaitActivationRegistry` 重复 key 拒绝未测试**：`WaitActivationRegistry.__init__` 中 `ValueError("duplicate wait activation adapter registration")` 分支未被测试。风险：低——该模式与 `WaitPollAdapterRegistry` 完全一致，后者已有生产路径覆盖。
3. **`WaitActivationRegistry.resolve_adapter` 返回 `None` 未直接测试**：该路径在 `_activate_accepted_wait_best_effort` 中由 `if adapter is None: return` 处理（`tool_runtime.py:2826-2827`）。行为正确，但无专门测试断言 registry 有 adapter A 而 binding key 为 B 时 adapter 解析为 `None` 且不崩溃。风险：极低——此 guard 是直接的条件返回。
4. **Slice 1 没有 production wiring**：`wait_activation_registry` 在 `DefaultToolRuntimeFactory` 中透传，但 `HostToolingOptions`、`dayu/host/dispatch.py`、`dayu/service/host_assembly.py` 尚未注入实际 registry——这是 Slice 3 的范围。当前所有测试均通过 fixture 注入。未配置时系统降级为 no-op（`_wait_activation_registry is None` → 直接返回）。风险：无——符合 Slice 1 设计。
5. **`ToolTraceDiagnosticEmitter.emit` 失败时 activation 异常被静默吞下**：`_emit_wait_activation_diagnostic_best_effort` 的 `except Exception` 仅写 log。若 adapter 抛出异常且 diagnostic emitter 也抛出异常，activation 失败既无 diagnostic 也无异常传播。风险：极低——双故障场景；log 中 `wait_activation_diagnostic_failed` 可供电排障。

## Conclusion

**Pass**。Slice 1 实现正确且测试充分：

- **Activation 仅在 Host durable accepted wait ack 之后执行**：代码路径唯一入口为 `_accept_awaiting` 中 `isinstance(accept_result, ToolAwaitingAcceptedAck)` 分支（`tool_runtime.py:2764`），且有 `context.cancellation_token.is_cancelled()` 二次门禁（`tool_runtime.py:2776`）。
- **拒绝/超时/缺失 binding/缺失 external job ref/pre-cancel/fanout waiter/stale execution 路径均不 activation**：每条路径均有测试断言 `activation_adapter.requests == []`。
- **Activation 异常产生有界诊断，不覆盖 accepted awaiting**：diagnostic message 仅含 `exc.__class__.__name__`；测试验证 raw 异常消息不进入 diagnostic（`test_awaiting_activation_failure_keeps_accepted_awaiting_outcome`）。
- **Host 接口最小化、可测试、无过度设计**：新增 `WaitActivationAdapter` Protocol + `WaitActivationRegistry` + `WaitActivationRequest` frozen dataclass，复用现有 `WaitAdapterKey`；与 `WaitPollAdapterRegistry` 模式一致。
- **无 Engine/Fins/Service scope creep**：全部变更在 `dayu/host/` 和 `tests/host/` 内。
- **无 LLM-facing contract 泄漏**：activation diagnostic 仅进入 Host-internal `ToolTraceDiagnosticEmitter`，不附加到返回给 Engine 的 `ToolAwaitingOutcome`。

34 个 Host 测试通过，pyright 0 错误。3 个 findings 均为低严重度（2 个测试缺口 + 1 个日志粒度注意点），无阻断项。
