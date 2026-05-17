# Re-Review Fix — AgentDS — 2026-05-17

## Gate

全仓 code review fix re-review gate。复核 AgentCodex 对以下 review 输入的修复：
- `docs/reviews/repo-review-20260517-1635.md`
- `docs/reviews/repo-review-20260517-1654.md`
- `docs/reviews/repo-review-fix-agentcodex-20260517.md`

## 复核方法

- 逐项阅读 workspace diff（29 files changed, +882/-61），针对每个修复项按原始 finding 的复现场景、预期行为与实际行为进行独立代码证据核验。
- 独立运行 `pytest -q`（979 passed）与 `python -m pyright dayu tests`（0 errors）确认 AgentCodex 验证声明。
- 对以下重点路径做了独立逐行逻辑复核：
  - `dayu/engine/runners/openai/sse_parser.py` — SSE error object / missing choices / unknown finish_reason warning
  - `dayu/engine/runners/openai/non_stream_parser.py` — non-stream unknown finish_reason warning
  - `dayu/host/dispatch.py` — memory projection catch-up 接线、repair closeout reason、drain loop warning
  - `dayu/host/projection.py` — max_event_sequence bounded scan
  - `dayu/host/memory_repair.py` — catch_up_conversation_memory_projection max_event_sequence 透传
  - `dayu/host/durable/memory.py` — read_latest_memory_snapshot_at_or_before 的 at-or-before SQL 语义
  - `dayu/host/run_input.py` — DurableMemorySnapshotProvider cursor 边界与 repair 路径
  - `dayu/host/api.py` — HostLocalExecutionOptions memory 字段、OperationContext 校验
  - `dayu/contracts/tool_call.py` — ToolCallRequest.__post_init__
  - `dayu/contracts/tool_outcome.py` — ToolCancelledReason Literal
  - `dayu/contracts/tool_result.py` — ToolResultFailure.__post_init__
  - `dayu/runtime/lane.py` — _mark_token_lost wake
  - `dayu/runtime/filelock.py` — 非线程安全文档
  - `dayu/engine/README.md` / `dayu/host/README.md` / `docs/host/implementation-control.md`

## 逐项复核

### 1. SSE provider error object / missing choices（原始 Finding #2 of 1635）

**修复位置**: `dayu/engine/runners/openai/sse_parser.py:62-65, 120-134, 328-380`

**复核结果**: PASS。

- `_ERROR_FIELD = "error"` 识别优先级高于 choices/usage 检查（`_handle_chunk_object:328`）：`error` 字段存在时直接产出 `RunnerProtocolErrorData(error_code="sse_provider_error")` + `RunnerDoneData(ERROR)` 并 return。
- 缺失 choices + 缺失有效 usage 的组合（`not has_valid_choices and not has_valid_usage` at line 354）产出 `sse_missing_choices` 协议错误 + `RunnerDoneData(ERROR)`。
- usage-only chunk（`has_valid_usage = True`）不触发 missing choices 分支，合法通过。
- `_provider_error_message` 安全提取错误摘要：str 错误直接使用，dict 错误提取 `message` 字段，无消息时使用中性 fallback。
- `_finalize_success` 在 `self._terminated and finish_reason == ERROR` 时直接 return（line 578-579），不产出 content completed / done stop。
- 测试覆盖：`tests/engine/runners/openai/test_protocol_error.py`（SSE error object、missing choices no-usage、usage-only chunk）。

**无新问题**。

### 2. 未知 finish_reason 诊断（原始 Finding #7 of 1635）

**修复位置**: `dayu/engine/runners/openai/sse_parser.py:444-454`、`dayu/engine/runners/openai/non_stream_parser.py:340-343`

**复核结果**: PASS。

- **SSE 路径**: `_handle_choice` 中 `_FINISH_REASON_MAP.get(finish_reason)` 返回 `None` 时记录 `sse.protocol_diagnostic code=unknown_finish_reason` warning，不设置 `self._finish_reason`。`_finalize_success` 随后在 `self._finish_reason is None` 时默认 `STOP`。
- **Non-stream 路径**: `_resolve_finish_reason` 中 `_FINISH_REASON_MAP.get(raw)` 返回 `None` 时记录 `non_stream.protocol_diagnostic code=unknown_finish_reason` warning，然后 `return FinishReason.STOP`。
- 两条路径均保留既有 STOP 回落，同时增加诊断 trace。
- 测试覆盖：`tests/engine/runners/openai/test_protocol_error.py`（SSE unknown finish reason）、`tests/engine/runners/openai/test_non_stream_response.py`（non-stream unknown finish reason）。

**无新问题**。

### 3. Conversation Memory projection 接入本地 dispatch（原始 Finding #3 of 1635）

**修复位置**: `dayu/host/api.py:703-726, 799-801`、`dayu/host/dispatch.py:695-696, 773-837, 839-879`、`dayu/host/memory.py:623-642`

**复核结果**: PASS。

- `HostLocalExecutionOptions` 新增 `memory_projection_policy: MemoryProjectionPolicy`（含 `default_memory_projection_policy` factory）与 `memory_projection_catchup_batch_size: int`。
- dispatch `_start_worker` 在 worker accept 前调用 `_catch_up_memory_projection_before_worker`（line 695），使用 `max_event_sequence = attempt.started_event_sequence - 1`。
- `_run_input_builder_for_dispatch` 创建单一 `DurableMemorySnapshotProvider` 实例（line 784-787），同时注入 no-tool 分支（line 792-796）与 tool-enabled 分支（line 832-837）。
- 默认 policy 由 `default_memory_projection_policy()` 从常量提供，不会为 None。
- `MemoryProjectionRepairRequired` 使用独立 closeout reason `"memory_projection_repair_required"`（line 112, 718），不与 `"worker_startup_timeout"`（line 111）混淆。
- catch-up 调用本身不检查返回值的 `repair_required` 字段，但下游 `DurableMemorySnapshotProvider.load_memory_snapshot` 会显式检测 snapshot 缺失/损坏/超阈值滞后并抛出 `MemoryProjectionRepairRequired`，形成 defense in depth。
- 测试覆盖：`tests/host/test_dispatch_scheduler.py`（no-tool dispatch durable memory、tool-enabled dispatch durable memory with ToolRuntime wiring）、`tests/host/test_run_input_builder.py`（future input not leak）。

**无新问题**。

### 4. Bounded catch-up / at-or-before snapshot 阻止 future input 泄漏

**修复位置**: `dayu/host/dispatch.py:860-879`、`dayu/host/projection.py:410-432, 542-583`、`dayu/host/durable/memory.py:286-330`、`dayu/host/run_input.py:1392-1403`

**复核结果**: PASS。

- dispatch `_required_memory_event_sequence_for_dispatch` 返回 `attempt.started_event_sequence - 1`，作为 catch-up 与 provider 读取的上界。
- Projection runner `_process_next_event`（projection.py:573-583）：`row.event_sequence > max_event_sequence` 时返回空 step（`scanned=False`，不推进 checkpoint），不把该 event 投影到 snapshot。
- Durable `read_latest_memory_snapshot_at_or_before` SQL（durable/memory.py:317）：`checkpoint_event_sequence <= max_checkpoint_event_sequence`，确保不会被 ahead-of-cursor snapshot 污染。
- Provider `_required_memory_event_sequence`（run_input.py:1400）：同样 `attempt.started_event_sequence - 1`。
- 测试覆盖：`tests/host/test_run_input_builder.py`（同 Session future input 不泄漏）。

**已知局限**（与 AgentCodex 残余风险一致）：snapshot 表当前只保留 latest snapshot per session/consumer/policy。若其他 composition root 在 dispatch 前主动把 memory consumer catch-up 到超过当前 Attempt cursor 的位置，旧 snapshot 会被覆盖，`read_latest_memory_snapshot_at_or_before` 可能返回 None（因为符合条件的 snapshot 不存在）。当前无其他 composition root 会做越界 catch-up，故此局限不构成线网问题。

**无新问题**。

### 5. MemoryProjectionRepairRequired 不被误分类为 worker startup timeout

**修复位置**: `dayu/host/dispatch.py:112, 706-723`

**复核结果**: PASS。

- `_start_worker` try 块内第一个 `except MemoryProjectionRepairRequired`（line 706）拦截 memory repair，使用 `_MEMORY_PROJECTION_REPAIR_REQUIRED_REASON` closeout。
- TimeoutError（line 724）与 generic Exception（line 734）各自使用 `_WORKER_STARTUP_TIMEOUT_REASON`。
- `_safe_closeout_worker_startup_timeout` 接受显式 `reason` 参数，两个关闭原因完全隔离。

**无新问题**。

### 6. Contracts 构造期校验与静态类型

**修复位置**: `dayu/contracts/tool_call.py:74-89`、`dayu/contracts/tool_result.py:71-81`、`dayu/contracts/tool_outcome.py:35-39, 112, 117-134`、`dayu/contracts/__init__.py:63, 103`、`dayu/host/api.py:896-925`

**复核结果**: PASS。

- `ToolCallRequest.__post_init__`: 拒绝空/纯空白 `tool_call_id`、空/纯空白 `name`、负 `index_in_iteration`。
- `ToolResultFailure.__post_init__`: 拒绝空/纯空白 `error` 和 `message`。
- `ToolCancelledOutcome.reason` 类型改为 `ToolCancelledReason = Literal["approval_denied", "host_cancelled", "timeout"]`；三个模块级常量改为 `Final[ToolCancelledReason]`；`__post_init__` 保留运行时校验；pyright 对非法字符串报错。
- `OperationContext.__post_init__`: 补充 `business_object_type` 和 `scenario` 的 `_require_optional_non_empty` 调用，与 `business_object_id`/`correlation_id` 一致。
- 测试覆盖：`tests/contracts/test_tool_call.py`、`tests/contracts/test_tool_result_envelope.py`、`tests/contracts/test_tool_outcome_exhaustive.py`、`tests/contracts/test_package_exports.py`、`tests/host/test_public_contracts.py`。

**无新问题**。

### 7. Lane lost token 唤醒

**修复位置**: `dayu/runtime/lane.py:894`

**复核结果**: PASS。

- `_mark_token_lost` 末尾新增 `self._wake_waiters()`，与 `_mark_token_released`（lane.py:739）保持一致。
- 测试覆盖：`tests/runtime/test_lane.py`。

**无新问题**。

### 8. Dispatch drain loop 异常日志

**修复位置**: `dayu/host/dispatch.py:493-509`

**复核结果**: PASS。

- `_drain_loop` 新增 try/except：`asyncio.CancelledError` 透传，其他 Exception 记录 warning 含 `host_handle_id` 和 `error_type`（`exc_info=True`）。
- `wake_dispatch` 原本的 `self._drain_task.done()` 检测 + 重建 task 机制不变，drain loop 异常退出后可被下一次 wakeup 恢复。
- 测试覆盖：`tests/host/test_dispatch_scheduler.py`。

**无新问题**。

### 9. RuntimeFileLock 非线程安全文档

**修复位置**: `dayu/runtime/filelock.py:146-147`

**复核结果**: PASS。

- `acquire()` docstring 明确："本方法不提供同一 wrapper 实例内的线程安全 active token 跟踪；多线程调用方应为每个线程创建独立 wrapper 实例。"
- 当前生产代码无共享同一 `RuntimeFileLock` 实例的证据，文档约束足够。

**无新问题**。

### 10. README / implementation-control 同步

**复核结果**: PASS。

- `dayu/engine/README.md`：同步 SSE provider error、missing choices、usage-only chunk、未知 finish_reason diagnostic 的当前行为。描述为事实陈述，无未来设计。
- `dayu/host/README.md`：同步 memory projection 接入 dispatch、bounded catch-up 语义、local execution options 新增 memory policy 字段、drain loop 异常日志、memory repair closeout reason。描述为事实陈述。
- `docs/host/implementation-control.md`：新增 "Engine Runner Factory 解耦追踪" 与 "Engine Context Compaction Event 语义前置" 追踪区条目，正确记录 deferred 决议。

**无新问题**。

### 11. User-deferred 项已正确排除

**复核结果**: PASS。

- 发布入口 / 用户命令：`git diff -- pyproject.toml README.md` 为空，未修改。
- Engine Agent 硬编码 AsyncOpenAIRunner：`git diff -- dayu/engine/agent.py` 为空，未修改。implementation-control 追踪条目已记录（`docs/host/implementation-control.md:1308-1319`）。
- 其余 deferred 项（runner retry 粒度、RECOVERING 状态、cancel wait TOCTOU、session cancel 多 worker 幂等、Gemini provider 合约）均未修改代码，在 AgentCodex fix report 中有明确裁决。

**无新问题**。

## 验证确认

独立运行验证：

- `source .venv/bin/activate && pytest -q` → **979 passed**
- `source .venv/bin/activate && python -m pyright dayu tests` → **0 errors, 0 warnings, 0 informations**
- `git diff --check` → passed（AgentCodex 报告，git diff --stat 确认无 conflict markers）

与 AgentCodex 声明一致。

## 结论

**PASS**。

所有原始 findings 中标记为"已修复"的项目均通过独立复核，无新增 blocking 问题。User-deferred 项（发布入口、Engine runner factory 解耦）已正确排除且分别记录在 implementation-control 追踪区。残余风险（snapshot 表单版本、cancel wait TOCTOU、session cancel multi-worker 幂等）已在 AgentCodex fix report 中正确识别并 deferred，不构成本轮 blocking。
