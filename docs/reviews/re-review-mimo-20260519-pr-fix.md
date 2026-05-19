# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-p10-5-public-contract-freeze
- Base: main
- Output file: docs/reviews/re-review-mimo-20260519-pr-fix.md
- Included scope: dayu/host/llm_compaction.py, dayu/host/wait_adapter.py, dayu/host/admission.py, dayu/engine/agent.py, utils/smoke_host_public_multiturn.py, related tests (test_llm_compaction.py, test_wait_adapter_polling.py, test_agent_phase2.py, test_agent_phase3_tool_call.py, test_admission_queue.py, test_active_cancel_dispatch.py, test_command_handle.py, test_logging.py, test_open_host_runtime.py, test_phase5_local_execution_integration.py, test_phase7_waiting_integration.py, test_projection_read_model.py, test_public_cancel_session_runs.py, test_public_event_stream.py, test_public_run_api.py), README files (engine/host/tests), docs/reviews/controller-fix-20260519-pr-review-smoke.md
- Excluded scope: 公开 console scripts 指向不存在模块的问题（用户裁决 CLI/Web/GUI 未开始）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 逐项走读记录

以下是对 controller-fix artifact 中每项 Accepted Fixed 的逐条验证：

#### 1. finish_reason=length 拒绝

- **文件**: `dayu/host/llm_compaction.py:172-175`
- **证据**: `compact()` 在 `EngineRunOutcomeFinalAnswer` 分支内，紧接非 final 检查后，新增 `if outcome.finish_reason is FinishReason.LENGTH: raise LLMCompactionProposalError("compactor summary was truncated finish_reason=length")`。
- **验证**: 测试 `test_llm_context_compactor_rejects_truncated_final_output` 使用 `FinishReason.LENGTH` 构造 final answer，断言 `pytest.raises(LLMCompactionProposalError, match="truncated")`。测试覆盖完整。

#### 2. runner timeout

- **文件**: `dayu/host/llm_compaction.py:217-228`
- **证据**: `_run_agent_request` 新增 `timeout_seconds` 参数，内部用 `asyncio.wait_for(run_agent_and_wait(request), timeout=timeout_seconds)` 包装。调用处 `compact()` 传入 `self._runner_spec.default_timeout_seconds`。
- **验证**: `RunnerSpec.__post_init__` 校验 `default_timeout_seconds > 0`。测试 `test_llm_context_compactor_applies_runner_timeout` 用 0.01s timeout + 10s sleep 验证超时抛出 `TimeoutError`。路径正确。

#### 3. error_code 安全化

- **文件**: `dayu/host/llm_compaction.py:61,253-263`
- **证据**: `_SAFE_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")`。`_safe_error_code()` 对不符合正则的 error_code 返回 `"unknown_error"`。在 `_non_final_outcome_message` 中用于 `EngineRunOutcomeFailed` 分支。
- **验证**: 测试 `test_llm_context_compactor_sanitizes_failed_runner_outcome` 用 `error_code="api_key=error-secret"` 断言 `"error_code=unknown_error"` 且 `"error-secret" not in message`。覆盖完整。

#### 4. budget 估算

- **文件**: `dayu/host/llm_compaction.py:466-487`
- **证据**: `_budget_after_compact` 从 `max(0, estimate.estimated_input_tokens // 2)` 改为 `min(_estimate_summary_tokens(summary), estimate.hard_threshold_tokens - 1)`。`_estimate_summary_tokens` 使用 `max(1, (len(summary) + 3) // 4)` 字符启发。
- **验证**: 测试 `test_llm_context_compactor_maps_final_answer_to_candidate` 期望值从 50 改为 8（对应 32 字符摘要 / 4）。`min()` 保证值永远 < `hard_threshold_tokens`，不触发 compaction_operation 的硬阈值拒绝。语义从"输入一半"改为"摘要本身大小"，更贴近实际 compact 后占用，且受硬阈值 cap 保护。

#### 5. WaitPoller abandon 记忆有界

- **文件**: `dayu/host/wait_adapter.py:342-402`
- **证据**: 旧代码在 `_abandoned_cancelled_wait_ids` 上只增不减。新代码每轮 poll 构造新的 `retained_abandoned_cancelled_wait_ids`，只保留本轮仍可观察到的 CANCELLED 记录。abandon 成功的加入 retained；失败的不加入（下轮重试）。poll 结束后用 retained 替换旧集合。
- **验证**: 测试 `test_failed_cancelled_wait_abandon_is_retried_next_poll` 用始终抛 ValueError 的 adapter，断言两轮 poll 的 `adapter_errors` 均为 1、`abandoned` 均为 0、`adapter.abandoned` 记录两次尝试。集合有界性由"只保留当前 records 中 CANCELLED 且在旧集合中的 ID"保证。

#### 6. Engine threading.Lock 移除

- **文件**: `dayu/engine/agent.py:18,651-652,1065-1088`
- **证据**: `import threading` 和 `self._run_guard_lock: threading.Lock = threading.Lock()` 已删除。`_acquire_run_slot` 和 `_release_run_slot` 直接读写 `self._active_run_id`，不再用 `with self._run_guard_lock`。
- **验证**: `_AsyncAgent` 是单实例、单 run 的 async 组件。async 事件循环是单线程的，不需要 threading.Lock。同步锁在 async 上下文中还会阻塞事件循环。移除正确。

#### 7. runner close cancellation 资源释放

- **文件**: `dayu/engine/agent.py:930-934,2380-2405`
- **证据**: `_run_agent_loop` 的 finally 块改为 `try: await self._close_runner_once() finally: self._release_run_slot()`。`_close_runner_once` 中 `CancelledError` 被捕获、记录 warning 后 re-raise；`_closed` 标志仅在 `close()` 成功时（`else` 分支）设为 True。
- **验证**: 测试 `test_close_cancelled_error_releases_run_slot` 用 `raise_cancelled_on_close=True` 的 runner，断言 `CancelledError` 传播且 `agent._active_run_id is None`。`_closed` 不设为 True 时下次 close 会重试，但 `_release_run_slot` 已执行且 `_AsyncAgent` 是单 use 生命周期，无实际回归风险。

#### 8. inline message size guard 前置

- **文件**: `dayu/engine/agent.py:1108-1113`
- **证据**: `_run_runner_iteration` 在构造 `_IterationState` 之前执行 `_message_inline_size_failure(messages)` 检查，超限时直接 yield failed terminal 并 return。
- **验证**: 测试 `test_oversized_tool_message_fails_before_force_answer_runner_call` 覆盖 force-answer fallback 前的 guard。`runner.call_count == 1` 表明第二次 Runner 调用未发生。覆盖完整。

#### 9. 工具批执行前取消不登记 tool_call_id

- **文件**: `dayu/engine/agent.py:1585-1589`
- **证据**: `_execute_tool_batch` 中，`_is_cancelled()` 检查移到 `self._executed_tool_call_ids.add()` 之前。取消命中时 yield cancelled terminal 并 return，不登记本批 tool_call_id。
- **验证**: 测试 `test_cancel_before_tool_batch_does_not_register_tool_call_id` 断言 `agent._executed_tool_call_ids == set()`、`len(executor.requests) == 0`、terminal 为 `RUN_CANCELLED`。覆盖完整。

#### 10. HostInput 迁移

- **文件**: 12 个测试文件
- **证据**: 所有测试从 `from dayu.host import HostInput` 改为 `from dayu.host.api import HostInput`。`dayu/host/__init__.py` 不再导出 `HostInput`。
- **验证**: `HostInput` 定义在 `dayu.host.api`（line 1342），是公共 API 类型。不通过包根兼容 re-export 符合 public/internal 边界约束。

#### 11. admission queue wakeup warning

- **文件**: `dayu/host/admission.py:4292-4298`
- **证据**: `except RuntimeError` 改为 `except RuntimeError as exc`，新增 `_LOGGER.warning("host.admission.queue_promotion_wakeup_failed session_id=%s error_type=%s", session_id, type(exc).__name__)`。
- **验证**: 测试 `test_cancel_predispatch_starting_promotion_survives_queue_wakeup_failure` 用 `caplog.at_level(logging.WARNING)` 断言 warning 日志包含 `"host.admission.queue_promotion_wakeup_failed"` 和 session_id。

#### 12. README 同步

- **文件**: dayu/engine/README.md, dayu/host/README.md, tests/README.md
- **证据**: Engine README 更新取消提交边界描述（工具批执行前取消不登记 tool call id）、Runner close cancellation 透传描述。Host README 更新 compactor timeout 和 finish_reason=length 拒绝描述、WaitPoller abandon 重试描述。Tests README 更新测试覆盖描述。
- **验证**: 所有 README 变更只描述已实现的稳定行为，未写过程状态/未来计划/实现细节。

## Open Questions

- 无。

## Residual Risk

- `dayu/host/fake_compaction.py` 的 `_budget_after_compact` 仍使用旧的 `max(0, estimate.estimated_input_tokens // 2)` 估算，与 LLM compactor 的 `_estimate_summary_tokens` 语义不一致。controller-fix artifact 已将其标记为 deferred（不在本次 gate 的允许修改范围内）。若 fake compactor 在测试或开发中被广泛使用，预算估算差异可能导致测试与真实行为偏离。
- Engine `_close_runner_once` 的 `_closed` 标志在 close 失败（非取消）时不设为 True，下次调用会重试 close。当前 `_AsyncAgent` 是单 use 生命周期，实际不会发生二次 close，但若未来复用 Agent 实例需注意。
- `_estimate_summary_tokens` 使用 `len(text)` 字符计数 + `// 4` 启发式。对中文等多字节字符，实际 token 数可能高于估算（中文通常 1 字符 ≈ 1-2 token）。当前用例中 summary 长度受 compactor output 限制，实际影响有限。

## Conclusion

**PASS**。所有 Accepted Fixed 项均已正确实现，测试覆盖完整，未引入新的 correctness、stability 或 maintainability 回归。README 同步符合文档约束。Residual risk 均为低优先级、已知 deferred 项或理论边界。
