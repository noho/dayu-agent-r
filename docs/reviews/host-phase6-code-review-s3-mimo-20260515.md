# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-phase-6-toolruntime`
- Base: `main`
- Output file: `docs/reviews/host-phase6-code-review-s3-mimo-20260515.md`
- Included scope: P6-S3 workspace diff — `dayu/host/tool_runtime.py`（新增约 1000 行 executor wrapper / policy / retry / helper）、`dayu/host/README.md`、`tests/README.md`、`tests/host/test_toolruntime_executor.py`、`tests/host/test_phase6_toolruntime_integration.py`、`docs/reviews/host-phase6-implementation-s3-executor-wrapper-20260515.md`
- Excluded scope: P6-S1 / P6-S2 committed changes（`run_input.py`、`tool_runtime.py` accept barrier、durable primitives 等）已在 branch 上但不在 workspace diff 范围内
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对审查重点的逐项证据总结：

### 1. accepted ack 后才返回 raw result

`ToolRuntimeExecutor._execute_one`（`tool_runtime.py:1265`）的执行流为：policy check → dispatch → normalize awaiting → truncation → construct accept candidate → accept retry → **只有 `ToolFactAcceptedAck` 时才返回 `accepted_outcome`**。

直接证据：`tool_runtime.py:1314-1318`：
```python
if isinstance(accept_result, ToolFactAcceptedAck):
    return BatchToolExecutionRecord(
        tool_call_id=call.tool_call_id,
        outcome=accepted_outcome,
    )
```

非 accepted ack 走 `_accept_failure_outcome`（`tool_runtime.py:1319-1323`），返回的是全新构造的 `ToolFailedOutcome`，不包含原始业务结果。

### 2. rejected / timeout 不泄漏 raw result

`_accept_failure_outcome`（`tool_runtime.py:2703-2722`）对 `ToolFactRejectedAck` 只返回 `error="tool_accept_rejected"` + `message=result.message` + `hint=reason_code`；对 `ToolFactAcceptTimedOut` 只返回 `error="tool_accept_timeout"` + `message="tool fact accept ack timed out"`。两路径均不包含原始业务 callable 返回值。

测试 `test_accept_rejected_does_not_expose_raw_fake_result` 和 `test_accept_timeout_bounded_retry_returns_governed_error` 断言原始 payload `"must-not-leak"` / `"timeout-raw"` 不出现在 governed error 的 message 中。✓

### 3. side-effect / paid 缺 idempotency key 不调用 callable

`DefaultToolRuntimePolicyPort.decide_tool_call`（`tool_runtime.py:916-938`）在 `_tool_idempotency_key` 返回 `None` 且 `side_effect_kind` 为 `SIDE_EFFECT` / `PAID` 时，直接返回 `GOVERNED_ERROR` 决策。此时 `_execute_one` 的 `policy_decision.kind is not ALLOW` 分支在 dispatch 之前拦截（`tool_runtime.py:1286-1287`），callable 不会被调用。

测试 `test_side_effect_tool_missing_idempotency_key_never_calls_callable` 断言 `callable_.call_count == 0`。✓

### 4. awaiting 只变 governed_error 且不 WAITING

`_normalize_runtime_outcome`（`tool_runtime.py:1325-1350`）检测到 `ToolAwaitingOutcome` 后：
- 发出诊断引用
- 构造 `GOVERNED_ERROR` 决策，reason_code = `"unsupported_awaiting"`
- 返回 `_governed_failure_outcome(governed_decision)`

结果进入 accept path 时 `_tool_fact_kind`（`tool_runtime.py:2517`）因 `policy_decision.kind is GOVERNED_ERROR` 直接返回 `ToolFactKind.GOVERNED_ERROR`。不创建 wait record，不进入 `WAITING`。

defense-in-depth：`_tool_fact_kind` 对未归一化的 `ToolAwaitingOutcome` 抛出 `TypeError`（`tool_runtime.py:2537`），`_tool_outcome_json` 同理（`tool_runtime.py:2638`）。

测试 `test_awaiting_outcome_becomes_governed_error_candidate` 断言 `tool_fact_kind is GOVERNED_ERROR`、`record.outcome` 为 `ToolFailedOutcome`、`hint == "unsupported_awaiting"`。✓

### 5. replay / no-tool defense

`_request_context_matches_scope`（`tool_runtime.py:2392-2406`）校验 `context.session_id == scope.session_id and context.run_id == scope.run_id`。`ToolRuntimeExecutionScope.allow_tool_calls=False` 时 `DefaultToolRuntimePolicyPort` 返回 `GOVERNED_ERROR`。

测试 `test_no_tool_scope_rejects_model_tool_call` 断言 `callable_.call_count == 0`、`reason_code == "tool_call_not_allowed_in_scope"`。✓

### 6. mixed batch

`ToolRuntimeExecutor.execute`（`tool_runtime.py:1251-1263`）对 `request.calls` 逐个 `_execute_one`，每个 call 的 policy / dispatch / accept 独立处理。测试 `test_batch_mixed_accept_outcomes_keep_accepted_visible` 覆盖 accepted + rejected + timeout 三种 outcome 共存于同一批次，断言第一个 `ToolCompletedOutcome` 可见、第二三个为 `ToolFailedOutcome`。✓

### 7. 不越界实现 fetch_more / duplicate / Remote

- `NoopTruncationPort`（`tool_runtime.py:845-869`）直接返回原 outcome，不截断
- `PassThroughDuplicateGovernance`（`tool_runtime.py:872-901`）始终返回 `ALLOW`，不做 duplicate 检测
- 无 Remote transport 代码
- `ToolRuntimeExecutor` 不导入 `dayu.fins`、不扫描业务工具

✓

### 8. 类型纪律

- 所有新增类、函数均有完整中文 docstring 和类型签名
- 无 `Any`、`object`、无类型参数
- Protocol 定义（`ToolDispatcher`、`ToolRuntimePolicyPort`、`TruncationPort`、`DuplicateGovernancePort`）与实现类签名一致
- pyright 0 errors, 0 warnings, 0 informations ✓

### 9. 测试质量

- `test_toolruntime_executor.py`：7 个测试覆盖 accepted ack、rejected ack、timeout retry、side-effect guard、awaiting guard、no-tool defense、mixed batch
- `test_phase6_toolruntime_integration.py`：1 个端到端测试覆盖 Engine → ToolRuntime → Host accept → Engine continuation，断言 durable EventLog 事件序列（TOOL_CALL_REQUESTED → TOOL_CALL_GOVERNED → TOOL_RESULT_ACCEPTED）和 Run / Attempt 终态
- 覆盖了 happy path 和主要 failure paths ✓

### 10. README 只写当前事实

`dayu/host/README.md` diff 更新了 ToolRuntime boundary 描述，准确反映 P6-S3 已实现的 executor wrapper、accept barrier、rejected/timeout 行为、side-effect guard、awaiting unsupported boundary，以及明确列出的未实现项。`tests/README.md` 同步更新了测试覆盖范围描述。不写未来设计。✓

## Open Questions

### dispatch.py / local_proxy.py 未修改 — blocking 还是 deferred acceptable？

**plan 要求**：`phase6-toolruntime-truncation-fetch-more-plan.md:381-385` P6-S3 allowed files 列出 `dayu/host/dispatch.py`（"only for wiring ToolRuntime into local dispatch request construction"）和 `dayu/host/local_proxy.py`（"only for passing the ToolExecutor supplied by RunInputBuilder"）。plan exact changes（第 514 行）写："Wire local dispatch / RunInputBuilder to use ToolRuntime executor for tool-enabled Attempts."

**当前事实**：
- `dispatch.py` 和 `local_proxy.py` 在整个 branch 上均无修改（`git diff main...HEAD --name-only` 不包含这两个文件）。
- `run_input.py` 已在 branch 上完成 tool-enabled 支持（`ToolExecutionMode`、`ToolRuntimeHandleProvider`、`ToolRuntimeSchemaSnapshotProvider`、`ToolRuntimeExecutorProvider`、`create_tool_enabled_run_input_builder`、`_validate_tool_enabled_snapshot`），但这些是 P6-S1/P6-S2 的 committed changes，不在 P6-S3 workspace diff 中。
- 集成测试 `test_phase6_toolruntime_integration.py` 直接使用 `create_tool_enabled_run_input_builder` 构造 tool-enabled request，绕过了真实 `HostDispatchScheduler`。

**判断：deferred acceptable，非 blocking**。

理由：
1. P6-S3 的 completion signal 是 "End-to-end local fake business tool path runs Engine -> ToolExecutor -> ToolRuntime -> Host accept -> Engine continuation"。集成测试已证明此路径可用。
2. RunInputBuilder 的 tool-enabled 工厂（`create_tool_enabled_run_input_builder`）已就绪，tool schema 和 executor 来自同一个 `ToolRuntimeHandle` 的 invariant 已通过 `_validate_tool_enabled_snapshot` 验证。
3. 真实 `HostDispatchScheduler` 使用 tool-enabled RunInputBuilder 是 composition root 装配问题，不改变 ToolRuntimeExecutor 的行为正确性。
4. 当前真实 Host dispatch 路径仍是 no-tool，但这不是 P6-S3 executor wrapper 的 regression — 它是 P6-S3 之前就存在的状态。
5. dispatch.py / local_proxy.py 的 wiring 可在后续 phase（或 P6-S4/P6-S5）中安全完成，不破坏已有 contract。

## Residual Risk

- P6-S3 duplicate governance 是 pass-through allow stub，完整 duplicate matrix 由 P6-S5 接管。
- P6-S3 truncation port 是 no-op；结果截断、cursor 与 `fetch_more` 由 P6-S4 接管。
- `ToolRuntimePolicyView` 默认所有未注册工具为 `READ_ONLY`，若构造时遗漏 side-effect 工具注册，该工具将被静默当作 read-only 处理，绕过 idempotency key 要求。这是配置层面风险，非 P6-S3 代码缺陷。
- `_accept_with_retry` 只捕获 `TimeoutError`；其它异常（如 SQLite 错误）会向上传播。这是正确行为（数据库错误应 crash 而非静默吞没），但调用方需处理。
- 真实 `HostDispatchScheduler` 仍使用 no-tool RunInputBuilder，tool-enabled 路径仅在集成测试中验证。
