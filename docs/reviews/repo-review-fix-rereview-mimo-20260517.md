# Repo Review Fix Re-Review - AgentMiMo - 2026-05-17

## 范围

- gate：全仓 code review fix re-review gate。
- 输入：
  - `docs/reviews/repo-review-20260517-1635.md`（原始 review）
  - `docs/reviews/repo-review-20260517-1654.md`（第二轮 review）
  - `docs/reviews/repo-review-fix-agentcodex-20260517.md`（AgentCodex 修复报告）
- 审查对象：当前 workspace diff（未提交）。
- 本轮不修改代码、不 commit、不 push、不开 PR。

## 结论：PASS

user-deferred 项已正确排除，未发现新的 blocking 问题。

## 逐项复核

### 1. SSE provider error object 与 missing choices 是否以 protocol error + Done(ERROR) 收口；usage-only chunk 是否未被误杀

**验证结果：通过。**

直接代码证据：

- `sse_parser.py:328-346`：`_handle_chunk_object` 新增对顶层 `error` 字段的显式检查。检测到 `_ERROR_FIELD in parsed` 后立即 yield `RunnerProtocolErrorData(error_code="sse_provider_error")` + `RunnerDoneData(ERROR)`，并 `return` 终止当前 chunk 处理。`_provider_error_message` 从 `error` payload 中提取有界摘要（支持 string / dict `message` 子字段），兜底返回 `"SSE provider returned an error object"`。
- `sse_parser.py:350-381`：对既无有效 `choices`（非空 list）也无有效 `usage`（dict）的 chunk，yield `RunnerProtocolErrorData(error_code="sse_missing_choices")` + `RunnerDoneData(ERROR)`。
- usage-only chunk 路径：当 `has_valid_usage=True` 且 `has_valid_choices=False` 时，`sse_missing_choices` 分支不会触发（`not has_valid_choices and not has_valid_usage` 为 `False`），usage 处理逻辑正常执行。
- `test_sse_provider_error_object_emits_protocol_error`：验证 error object 产出 `PROTOCOL_ERROR` + `RUNNER_DONE(ERROR)`，error_code 为 `sse_provider_error`，message 提取正确。
- `test_sse_missing_choices_without_usage_emits_protocol_error`：验证无 choices 无 usage chunk 产出 `sse_missing_choices`。
- `test_sse_usage_only_chunk_does_not_protocol_error`：验证 usage-only chunk 不触发协议错误，仍产出 `RUNNER_USAGE_RECORDED`。

边界检查：error 检查在 choices/usage 检查之前执行，确保 error object 不会被错误地当作 usage-only chunk 处理。`_terminated` 标志在协议错误时被设置为 `True`，防止后续 `[DONE]` 触发额外 finalize。

### 2. 未知 finish_reason 的 warning 是否同时覆盖 SSE 和 non-stream，且不破坏既有 STOP 回落

**验证结果：通过。**

直接代码证据：

- `sse_parser.py:449-454`：`_handle_choice` 中 `_FINISH_REASON_MAP.get(finish_reason)` 返回 `None` 时（`else` 分支），记录 warning `sse.protocol_diagnostic code=unknown_finish_reason finish_reason=%s`。`STOP` 回落不受影响——`_resolve_finish_reason` 在 SSE 路径仍由 `_finalize_success` 中的 `self._finish_reason or FinishReason.STOP` 提供。
- `non_stream_parser.py:340-344`：`_resolve_finish_reason` 在 `mapped is None` 时记录 warning `non_stream.protocol_diagnostic code=unknown_finish_reason finish_reason=%s`，然后 `return FinishReason.STOP`。
- `test_sse_unknown_finish_reason_logs_diagnostic`：验证 `finish_reason="safety_stop"` 时 content completed 仍为 `STOP`，且 warning 日志包含 `unknown_finish_reason`。
- `test_non_stream_unknown_finish_reason_logs_diagnostic`：同上，覆盖 non-stream 路径。

两个 parser 的 warning 日志格式一致（`code=unknown_finish_reason finish_reason=%s`），便于 grep 运维排查。

### 3. Memory projection 接入 dispatch 后，no-tool 与 tool-enabled 都走 durable provider

**验证结果：通过。**

直接代码证据：

- `api.py:725-728`：`HostLocalExecutionOptions` 新增 `memory_projection_policy: MemoryProjectionPolicy`（default factory）与 `memory_projection_catchup_batch_size: int = 128`。
- `dispatch.py:784-787`：`_run_input_builder_for_dispatch` 在 tooling 判断之前创建 `DurableMemorySnapshotProvider(transaction_runner, memory_projection_policy)`。
- `dispatch.py:795`：no-tool 分支 `create_no_tool_run_input_builder(..., memory_snapshot_provider=memory_provider)`。
- `dispatch.py:836`：tool-enabled 分支 `create_tool_enabled_run_input_builder(..., memory_snapshot_provider=memory_provider)`。
- 两个 factory 均接收同一 `memory_provider` 实例，消除了 `NoopMemorySnapshotProvider` 默认回落。
- `test_scheduler_injects_durable_memory_for_no_tool_dispatch`：验证 no-tool dispatch 的 `AgentRunRequest.messages` 包含之前 session 的 user input 文本。
- `test_scheduler_uses_toolruntime_when_tooling_is_configured`（修改后）：验证 tool-enabled dispatch 同样注入 durable memory 且保留 ToolRuntime 接线。

### 4. Bounded catch-up / at-or-before snapshot 是否真正阻止同 Session queued future input 泄漏到当前 Attempt

**验证结果：通过。**

直接代码证据：

- `dispatch.py:860-881`：`_required_memory_event_sequence_for_dispatch` 读取 `attempt.started_event_sequence - 1` 作为 max cursor。
- `dispatch.py:839-858`：`_catch_up_memory_projection_before_worker` 在 `worker.accept()` 之前调用，传入 `max_event_sequence=required_cursor`。
- `projection.py:573-583`：`_process_next_event` 在读取下一条 EventLog row 后检查 `row.event_sequence > max_event_sequence`，超过时返回 `scanned=False, matched=False`，不推进 checkpoint。
- `durable/memory.py:286-332`：`read_latest_memory_snapshot_at_or_before` 使用 SQL `WHERE checkpoint_event_sequence <= ?` 确保只读取不超过指定 cursor 的 snapshot。
- `run_input.py:730-736`：`DurableMemorySnapshotProvider._load_durable_snapshot` 改用 `read_latest_memory_snapshot_at_or_before`，传入 `max_checkpoint_event_sequence=required_event_sequence`。
- `test_memory_provider_uses_latest_snapshot_before_required_cursor`：构造同 Session 三阶段场景（prior input → current run → future input），catch-up 带 `max_event_sequence`，断言 `"prior prompt should be visible"` 且 `"future prompt must not leak"` 不在 messages 中。
- `test_only_future_memory_snapshot_raises_missing_repair_required`（重命名自 `test_ahead_memory_snapshot_raises_repair_required`）：验证只有 future snapshot 时返回 `SNAPSHOT_MISSING` repair-required。

防御层完整：catch-up 阶段通过 `max_event_sequence` 限制不读取未来事件；snapshot 读取阶段通过 `<=` SQL 条件限制不读取未来 checkpoint。

### 5. MemoryProjectionRepairRequired 是否不会被错误记录为 worker startup timeout

**验证结果：通过。**

直接代码证据：

- `dispatch.py:112`：`_MEMORY_PROJECTION_REPAIR_REQUIRED_REASON = "memory_projection_repair_required"`，与 `_WORKER_STARTUP_TIMEOUT_REASON = "worker_startup_timeout"` 独立。
- `dispatch.py:706-726`：`MemoryProjectionRepairRequired` 被单独 `except` 捕获，调用 `_safe_closeout_worker_startup_timeout(record, reason=_MEMORY_PROJECTION_REPAIR_REQUIRED_REASON, original_error=exc)`。
- `dispatch.py:526,532,568,737`：所有原有 timeout/exception 路径均显式传入 `reason=_WORKER_STARTUP_TIMEOUT_REASON`。
- `_closeout_worker_startup_timeout` 方法签名已改为 `reason: str` 参数化，不再硬编码 `_WORKER_STARTUP_TIMEOUT_REASON`。
- `host/README.md` 更新明确说明："memory projection repair required 使用独立 closeout reason，不归类为 worker startup timeout"。

### 6. ToolCallRequest、ToolResultFailure、ToolCancelledReason、OperationContext 的校验是否类型和运行时都一致

**验证结果：通过。**

直接代码证据：

- `tool_call.py:75-90`：`ToolCallRequest.__post_init__` 校验 `tool_call_id.strip() != ""`、`name.strip() != ""`、`index_in_iteration >= 0`。
- `tool_result.py:71-82`：`ToolResultFailure.__post_init__` 校验 `error.strip() != ""`、`message.strip() != ""`。
- `tool_outcome.py:35-40`：`ToolCancelledReason: TypeAlias = Literal["approval_denied", "host_cancelled", "timeout"]`。
- `tool_outcome.py:42-50`：三个常量 `TOOL_CANCELLED_REASON_*` 声明为 `Final[ToolCancelledReason]`。
- `tool_outcome.py:112`：`ToolCancelledOutcome.reason` 类型从 `str` 收紧为 `ToolCancelledReason`。
- `api.py:912-923`：`OperationContext.__post_init__` 新增对 `business_object_type` 和 `scenario` 的 `_require_optional_non_empty` 校验。
- `__init__.py`：`ToolCancelledReason` 导出到 `__all__`。
- 测试覆盖：`test_tool_call_request_rejects_blank_id_or_name`、`test_tool_call_request_rejects_negative_index`、`test_failure_envelope_rejects_empty_error_or_message`、`test_cancelled_rejects_invalid_reason`（使用 `cast` 绕过静态类型以测试运行时）、`test_operation_context_rejects_empty_optional_text_fields`。

pyright 0 errors 确认 Literal 类型收紧不引入类型错误。`test_tool_outcome_exhaustive.py` 中 `cast(ToolCancelledReason, "not_a_real_reason")` 正确绕过静态检查以测试运行时 `__post_init__` 拒绝。

### 7. Lane lost token 唤醒、dispatch drain loop warning、RuntimeFileLock 非线程安全文档是否足够

**验证结果：通过。**

直接代码证据：

- `lane.py:894`：`_mark_token_lost` 末尾新增 `self._wake_waiters()`，与 `_mark_token_released`（`lane.py:739`）行为一致。
- `test_heartbeat_lost_claim_wakes_waiting_acquire`：验证 heartbeat lost token 后等待中的 acquire 立即被唤醒，不再依赖下一次 poll。
- `dispatch.py:493-512`：`_drain_loop` 用 `try/except` 包裹主循环，`CancelledError` 正确 re-raise，其它异常记录 warning（含 `host_handle_id`、`error_type`、`exc_info=True`）后静默退出。
- `test_drain_loop_logs_unexpected_exception`：注入 `RuntimeError` 异常，验证 warning 日志包含 `"dispatch drain loop stopped unexpectedly"`。
- `filelock.py:114-117`：`RuntimeFileLock` 类 docstring 明确标注 "同一个实例只承诺单线程 / 单控制流使用；多线程需要各自创建独立实例"。
- `filelock.py:146-148`：`acquire()` 方法 docstring 明确标注 "不提供同一 wrapper 实例内的线程安全 active token 跟踪"。

### 8. README / implementation-control 是否只同步当前事实，没有写未来设计

**验证结果：通过。**

直接代码证据：

- `dayu/engine/README.md`：更新段落描述 SSE error object、missing choices、usage-only chunk 和 unknown finish_reason 的**当前行为**，不包含"未来将会"或"计划中"表述。
- `dayu/host/README.md`：
  - 更新 `HostLocalExecutionOptions` 描述，补充 conversation memory policy。
  - 更新 RunInputBuilder 段落，描述 at-or-before snapshot 读取和本地 dispatch memory catch-up **当前行为**。
  - 更新 memory_repair 段落，说明 dispatch worker 启动路径同步 catch-up 和独立 memory repair closeout reason。
  - 更新 Phase 5 dispatch scheduler 段落，补充 drain loop warning、memory projection 接线和独立 closeout reason。
  - 从"未实现"列表删除 "production concrete memory catch-up port 注入"（因已实现）。
- `docs/host/implementation-control.md`：新增 "Engine Runner Factory 解耦追踪" 段落，记录用户 deferred 决议和后续触发条件，属于追踪事实而非未来设计。

## User-deferred 项确认

### 发布入口指向不存在的包（Finding 1 of repo-review-20260517-1635.md）

- AgentCodex 裁决：`user-deferred/no-change`。
- 复核：`git diff -- pyproject.toml README.md` 确认为空。本轮 diff 不触及这两个文件。
- 状态：正确排除，不 blocking。

### Engine Agent 硬编码 AsyncOpenAIRunner（Finding 02 of repo-review-20260517-1654.md）

- AgentCodex 裁决：`deferred/no-code-change`。
- 复核：`git diff -- dayu/engine/agent.py` 确认为空。`docs/host/implementation-control.md` 已新增追踪段落，记录 deferred 决议、触发条件和后续处理要求。
- 状态：正确排除，追踪已记录。

## 其它未修 / deferred 项确认

AgentCodex 报告中列出的其它 deferred 项（Runner usage-only retry、RECOVERING Run、cancel_active_wait_records_for_run TOCTOU、session cancel 幂等重放、Gemini provider 合约、RuntimeFileLock 线程安全加锁）均为合理裁决：

- 前次 re-review 已将 "已 yield 事件后不跨 attempt retry" 作为 pass 条件。
- RECOVERING 当前不可达（`run_transition.py` 零写入），schema 注释已标注 future-reserved。
- TOCTOU 和 session cancel 幂等涉及 contract 重设计，不适合局部补丁。
- RuntimeFileLock 已用 docstring 明确边界，未发现生产共享实例证据。

## 验证结果

- `pytest tests/contracts/test_package_exports.py tests/contracts/test_tool_call.py tests/contracts/test_tool_result_envelope.py tests/contracts/test_tool_outcome_exhaustive.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_non_stream_response.py tests/runtime/test_lane.py tests/host/test_public_contracts.py tests/host/test_dispatch_scheduler.py tests/host/test_run_input_builder.py -q`：**152 passed**。
- `pytest -q`：**979 passed**。
- `python -m pyright dayu tests`：**0 errors, 0 warnings, 0 informations**。
- `git diff --check`：**passed**。

以上验证结果与 AgentCodex 报告一致。
