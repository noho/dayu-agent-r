# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-code-review-s2-mimo-20260516.md
- Included scope:
  - `dayu/host/tool_runtime.py` — awaiting accept path, batch suspension, adapter registry wiring
  - `dayu/host/waiting.py` — new; `DefaultHostToolAwaitingAcceptPort`, idempotency, event plan, CAS
  - `dayu/host/wait_adapter.py` — new; `WaitAdapterBinding`, `WaitAdapterRegistry`, `WaitExternalJobRefSource`
  - `dayu/host/_event_payload.py` — P7-S2 additions: `tool_awaiting_payload`, `run_waiting_payload`, `attempt_suspended_payload`
  - `dayu/host/durable/state.py` — P7-S2 additions: `mark_run_waiting_row`, `mark_attempt_suspended_row`
  - `tests/host/test_wait_awaiting_accept.py` — new; integration tests for `DefaultHostToolAwaitingAcceptPort`
  - `tests/host/test_toolruntime_executor.py` — P7-S2 tests for `ToolRuntimeExecutor` awaiting path
- Excluded scope: P7-S1 files (previously reviewed, stable), resolve_wait path, poller/callback, docs
- Parallel review coverage: 无

## Findings

### S2-F1 未修复 中 - awaiting accept 失败路径缺少 tool_runtime 层集成测试

- **入口/函数**: `ToolRuntimeExecutor._accept_awaiting` / `_accept_awaiting_with_retry`
- **文件(行号)**: `dayu/host/tool_runtime.py:2419-2499`, `tests/host/test_toolruntime_executor.py:415-479`
- **输入场景**: `ToolAwaitingOutcome` 经 awaiting accept port 返回 `ToolAwaitingRejectedAck` 或 `ToolAwaitingAcceptTimedOut`
- **实际分支**: 第 2496-2499 行 `_awaiting_accept_failure_outcome(accept_result)` 将 rejected/timeout 转换为 `ToolFailedOutcome`
- **预期行为**: tool_runtime 层测试应覆盖 rejected（idempotency conflict / invalid_attempt / stale_execution / cas_conflict）和 timed-out 场景，验证返回的 governed error 含正确 error、reason_code 和 hint
- **实际行为**: `_AwaitingAcceptPort` fake（第 233-284 行）只返回 `ToolAwaitingAcceptedAck`；无测试构造 `ToolAwaitingRejectedAck` 或 `ToolAwaitingAcceptTimedOut`。`_awaiting_accept_failure_outcome` 映射逻辑（第 4895-4917 行）在 tool_runtime 层未被测试覆盖
- **直接证据**: `_AwaitingAcceptPort.accept_tool_awaiting` 第 244-284 行只返回 `ToolAwaitingAcceptedAck`；无 test helper 返回 rejected/timeout
- **影响**: 若 `_awaiting_accept_failure_outcome` 映射出错（如 hint 格式变更），tool_runtime 层测试不会发现
- **建议改法和验证点**: 新增测试：构造返回 `ToolAwaitingRejectedAck(reason_code=IDEMPOTENCY_CONFLICT)` 的 fake port，断言 `BatchToolExecutionRecord.outcome` 是 `ToolFailedOutcome` 且 error 为 `tool_awaiting_accept_rejected`、hint 包含 `idempotency_conflict`；同理构造 timeout 场景
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### S2-F2 未修复 中 - POLL binding external_job_ref 缺失路径缺少 tool_runtime 层测试

- **入口/函数**: `ToolRuntimeExecutor._accept_awaiting`
- **文件(行号)**: `dayu/host/tool_runtime.py:2466-2473`, `tests/host/test_toolruntime_executor.py`
- **输入场景**: `WaitAdapterBinding(resume_policy=POLL, external_job_ref_source=NONE)` + `ToolAwaitingOutcome` 无 resume_token
- **实际分支**: 第 2467-2473 行 `binding.resume_policy is WaitResumePolicy.POLL and external_job_ref is None` → 返回 `_awaiting_external_job_failure()`
- **预期行为**: 测试应覆盖 POLL binding 但 `external_job_ref` 为 None 的场景，验证返回 `ToolFailedOutcome` 且 error 为 `awaiting_external_job_missing`
- **实际行为**: 现有测试只覆盖"无 adapter binding"场景（`test_awaiting_outcome_without_adapter_binding_is_governed_error`）；`_wait_adapter_registry()` helper（第 692-708 行）使用 `RESUME_TOKEN` source，不会产生 None `external_job_ref`
- **直接证据**: 第 2466-2473 行有 early return；测试 helper 第 692-708 行只配置 `RESUME_TOKEN`
- **影响**: 该 early return 分支在 tool_runtime 层未被覆盖；若 `external_job_ref` 派生逻辑变更导致 POLL binding 返回 None，测试不会发现
- **建议改法和验证点**: 新增测试：配置 `WaitAdapterBinding(resume_policy=POLL, external_job_ref_source=NONE)` + `_AwaitingCallable` 返回无 resume_token 的 `ToolAwaitingOutcome`，断言 `ToolFailedOutcome` 且 hint 为 `awaiting_external_job_missing`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### S2-F3 未修复 低 - `_normalize_runtime_outcome` 退化为空透传

- **入口/函数**: `ToolRuntimeExecutor._normalize_runtime_outcome`
- **文件(行号)**: `dayu/host/tool_runtime.py:2632-2644`
- **输入场景**: 所有非 awaiting 的普通 completed/failed/cancelled outcome
- **实际分支**: `return outcome, policy_decision`
- **预期行为**: P6 中该函数将 `ToolAwaitingOutcome` 转换为 governed error；P7-S2 移除了该转换后，函数体退化为空透传
- **实际行为**: 函数直接返回输入，无任何归一化逻辑
- **直接证据**: 第 2632-2644 行仅 `return outcome, policy_decision`；调用点第 2326 行仍执行该函数
- **影响**: 无 correctness 风险；保留空函数作为 extension point 增加阅读负担
- **建议改法和验证点**: 可内联到调用点，或保留并在 docstring 中明确说明其为有意设计的 extension point
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### S2-F4 未修复 低 - awaiting accept 成功后 duplicate registry 未更新

- **入口/函数**: `ToolRuntimeExecutor._accept_awaiting`
- **文件(行号)**: `dayu/host/tool_runtime.py:2490-2495`
- **输入场景**: `ToolAwaitingOutcome` 经 awaiting accept 成功
- **实际分支**: 第 2491 行 `del duplicate_request`，不调用 `_record_duplicate_accepted`
- **预期行为**: 与普通 accept 路径（第 2352-2358 行 `_record_duplicate_accepted`）对比
- **实际行为**: `del duplicate_request` 显式丢弃 duplicate 请求，不写入 run-local duplicate index
- **直接证据**: 第 2491 行 `del duplicate_request`；普通路径第 2352-2358 行调用 `_record_duplicate_accepted`
- **影响**: 同一 tool_call 再次进入时 duplicate governance 不会命中 prior awaiting outcome，但 idempotency scope（`attempt_id:tool_call_id`）会在 `_accept_in_transaction` 中拦截重复写入。功能正确，但与普通路径行为不对称
- **建议改法和验证点**: 添加行内注释说明为何 awaiting path 不更新 duplicate registry（awaiting 是中间态而非终态）
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无

## Residual Risk

1. **precondition 失败路径无测试覆盖**: `waiting.py:_invalid_awaiting_precondition` 返回 `INVALID_ATTEMPT` / `STALE_EXECUTION` 的路径在 `test_wait_awaiting_accept.py` 和 `test_toolruntime_executor.py` 中均未覆盖。需要测试 Run 非 RUNNING、Attempt 非 RUNNING、dispatch record 非 DISPATCHING、execution_id 不匹配等场景。
2. **CAS 失败路径无测试覆盖**: `mark_run_waiting_row` 或 `mark_attempt_suspended_row` 返回 `CAS_LOST` 导致 `HostDurableError("tool awaiting accept state CAS failed")` 的路径无测试。P7-S1 review 已将 CAS_LOST race test deferred 到 P7-S4。
3. **`DefaultHostToolAwaitingAcceptPort` replay 异常路径**: `_accepted_ack_from_existing` 在 idempotency record 存在但事件缺失时 raise `RuntimeError`（第 688 行），该路径无测试覆盖。理论上不应发生（idempotency record 与 events 在同一 transaction 内原子写入），但属于防御性代码缺口。
