# Gateflow Implementation: Tool Executor Batch — Slice 1

- **Date**: 2026-05-12
- **Branch**: `host/phase_0_design`
- **Scope**: 把 `dayu.engine` 的 `ToolExecutor` 握手从 per-call 升级为单一
  per-batch 签名；同步迁移 Engine 内部数据形状、record dataclass 形状、
  Agent 状态机与覆盖测试；按 Controller 修正与再修正调整公共契约层的
  工具声明边界。

## 1. 范围与目标

- `dayu.contracts.ToolExecutor` 由 per-call 升级为 *单一* per-batch
  签名：`async def execute(self, request: BatchToolExecutionRequest) -> BatchToolExecutionOutcome`。
- `BatchToolExecutionRequest = (calls, context)`；
  `BatchToolExecutionOutcome = (records,)`，其中
  `records: tuple[BatchToolExecutionRecord, ...]`。
- 严格双射：`{call.tool_call_id for call in request.calls}` 必须等于
  `{record.tool_call_id for record in response.records}`，缺/多/重一律
  视为 `tool_batch_outcome_mismatch` 失败。
- 完成路径形状非 flatten，统一携带 batch 快照：
  - `AcceptedToolExecutionRecord(batch_snapshot, call, outcome)`
  - `AwaitingToolExecutionRecord(batch_snapshot, call, await_spec, snapshot)`
- `ToolExecutionOutcome` 联合 4 个 variant：`Completed` /
  `Failed` / `Awaiting` / `Cancelled`；`Cancelled` 属于已接受类，不归
  失败类。
- `TOOL_CALLS_BATCH_READY` 仅在 `_execute_tool_batch` 内部、输入侧预校验
  （duplicate / 已执行 id 检查）通过后、`ToolExecutor.execute` 调用前发射
  一次，不在 runner-event 分类时重复发射。post-executor bijection 校验
  失败时本批不再产生 `BATCH_DONE`，由 `RUN_FAILED` 终结，事件序列由
  Host observer 按 batch 终态自行收口。
- Engine 仍只接收 `tool_schemas` 与 `tool_executor`；`ToolDefinition` /
  `ToolBundle` / `ToolCallable` 不进入 Engine。

## 2. 公共契约变更

### 2.1 批式握手对象

- `BatchToolExecutionContext`：批式握手共享的运行期上下文，承载
  `run_id` / `session_id` / `iteration_id` / `timeout_seconds` /
  `cancellation_token` / `correlation_id`（形如
  `"{run_id}:{iteration_id}:tool_batch"`，仅作中性关联）。
- `BatchToolExecutionRequest(calls, context)`：是
  `ToolExecutor.execute` 的唯一入参。
- `BatchToolExecutionRecord(tool_call_id, outcome)`：批式 outcome 内部
  与 `calls` 一一对应的记录元素；不携带 batch_snapshot（snapshot 由
  Engine 在分类成 Accepted / Awaiting record 时统一注入）。
- `BatchToolExecutionOutcome(records)`：批式 outcome 容器。
- `ToolCancelledOutcome`：新增第 4 个 variant；附带受限
  `ALLOWED_TOOL_CANCELLED_REASONS = {timeout, approval_denied, host_cancelled}`
  常量集合。

### 2.2 ToolExecutor Protocol

`ToolExecutor` 收缩为唯一批式签名：

```python
@runtime_checkable
class ToolExecutor(Protocol):
    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome: ...
```

per-call helper（旧 `ToolExecutionRequest` / `ToolExecutionContext`）从
公共契约层完全移除；公共契约层不再提供任何 per-call 兼容 wrapper。

### 2.3 ToolDefinition / ToolBundle / @tool / ToolCallable

按 Controller 再修正的最终形状：

- `@tool(...)` 保持装饰器形态，由 Host / ToolRuntime 在工具函数现场
  声明 `ToolSchema` / 截断 / 展示 metadata / tags 与 *单工具*
  `ToolCallable`。
- `ToolCallable` 是单工具调用协议，形状固定：

  ```python
  @runtime_checkable
  class ToolCallable(Protocol):
      async def __call__(
          self,
          call: ToolCallRequest,
          context: BatchToolExecutionContext,
      ) -> ToolExecutionOutcome: ...
  ```

- `ToolDefinition` 字段：`name`、`schema`、`callable: ToolCallable`、
  `truncate`、`display`、`tags`；不再有 `executor` 字段。
- `ToolBundle.truncate_specs()` 与 `to_tool_schemas()` 保持纯投影
  helper。
- Engine 不消费 `ToolDefinition` / `ToolBundle` / `ToolCallable`；仍仅
  接收 `tool_schemas` 与 `tool_executor`。把一组 `ToolCallable` 包装为
  受治理的批式 `ToolExecutor` 是 Host / ToolRuntime 的职责。

## 3. Engine 内部数据形状

### 3.1 record dataclass

`dayu.engine.contracts.tool_records`：

```python
@dataclass(frozen=True, slots=True)
class AssistantToolCallBatchSnapshot:
    iteration_id: str
    tool_calls: tuple[ToolCallRequest, ...]
    content: str | None
    reasoning_content: str | None
    provider_request_id: str | None

@dataclass(frozen=True, slots=True)
class AcceptedToolExecutionRecord:
    batch_snapshot: AssistantToolCallBatchSnapshot
    call: ToolCallRequest
    outcome: AcceptedToolOutcome  # Completed | Failed | Cancelled

@dataclass(frozen=True, slots=True)
class AwaitingToolExecutionRecord:
    batch_snapshot: AssistantToolCallBatchSnapshot
    call: ToolCallRequest
    await_spec: ToolAwaitSpec
    snapshot: ToolAwaitSnapshot | None
```

Record 字段保持非 flatten；测试与 Agent 状态机一律通过
`record.call.tool_call_id` / `record.await_spec` / `record.snapshot`
访问，不暴露 flatten 别名。

### 3.2 Engine 事件 data 形状

- `ToolAwaitingData`：`iteration_id`、`record`。
- `RunSuspendedData`：`reason`、`resume_hint`、`accepted_records`、
  `awaiting_records`。
- `ToolCallsBatchDoneData`：`iteration_id`、`tool_call_ids`、
  `completed_count`、`failed_count`、`cancelled_count`。

## 4. Agent 状态机变化

### 4.1 单次 batch_ready emission

`TOOL_CALLS_BATCH_READY` 仅在 `_execute_tool_batch` 内部、输入侧预校验
（duplicate / 已执行 id 检查）通过后、`ToolExecutor.execute` 调用前发射
一次；runner-event 分类层不再重复发射。该事件语义为「batch 已构造完成
并即将提交执行」，不承诺 post-executor bijection 校验已通过；bijection
失败时本批以 `RUN_FAILED` 终结，不再有 `BATCH_DONE`。

### 4.2 Intra-batch duplicate tool_call_id 检测

在 `_execute_tool_batch` 内新增 `seen_in_batch: set[str]` 检测；同一批
内出现重复 `tool_call_id` 立即以 `duplicate_tool_call_id` 终结，不下发
到 `ToolExecutor.execute`：

```python
seen_in_batch: set[str] = set()
for call in decision.tool_calls:
    if (
        call.tool_call_id in self._executed_tool_call_ids
        or call.tool_call_id in seen_in_batch
    ):
        self._last_tool_batch_result = RunFailedData(
            error_code=_ERROR_DUPLICATE_TOOL_CALL_ID, ...
        )
        return
    seen_in_batch.add(call.tool_call_id)
```

### 4.3 Fail-closed 路径不下发到 executor

`tool_call_delta` 与 `tool_call_completed` 等 fail-closed 路径不再下发
到 `ToolExecutor`；对应测试断言 `ready_events == []`。

## 5. 测试与验证

### 5.1 焦点测试

```
pytest tests/contracts/test_tool_declaration.py \
       tests/contracts/test_package_exports.py \
       tests/engine/test_package_exports.py
pytest tests/contracts/test_tool_outcome_exhaustive.py \
       tests/engine/test_agent_phase2.py \
       tests/engine/test_agent_phase3_tool_call.py \
       tests/engine/runners/openai/test_streaming_capability_and_content_type.py
```

两组焦点测试全部通过。

### 5.2 全量套件

`pytest`：389 passed，0 failed。

### 5.3 pyright

`pyright`：0 errors, 0 warnings, 0 informations。

## 6. Controller 修正：record 非 flatten

Controller 早期纠偏指出：Engine record dataclass 必须携带完整
`call`，不得 flatten 出 `record.index_in_iteration` 等便捷别名。本 slice
按该纠偏改写 `tool_records.py` 与 phase2 / phase3 测试，全部用
`record.call.tool_call_id` 与 `record.await_spec` / `record.snapshot`
访问，无任何 flatten 字段残留。

## 7. Controller amendment: FunctionToolExecutor removal

Controller 在 slice 中段下达修正：从公共契约层移除任何执行绑定 helper。

- 移除 `dayu.contracts.tool_declaration.FunctionToolExecutor`（不保留
  默认执行器 / callable 适配器 / batch 内部执行策略）。
- 移除 `dayu.contracts.tool_declaration.ToolFunctionCallable` 旧别名。
- `dayu.contracts` 仅承载层间共享形状与协议：批式 request / outcome、
  record / outcome variant、`ToolExecutor` Protocol、`ToolCallable`
  Protocol、`ToolDefinition` / `ToolBundle` 纯元数据 + 单工具 callable
  容器、`@tool(...)` 装饰器。

`dayu.contracts.__all__` 同步更新为：

```python
__all__ = [
    "ALLOWED_TOOL_CANCELLED_REASONS",
    "BatchToolExecutionContext",
    "BatchToolExecutionOutcome",
    "BatchToolExecutionRecord",
    "BatchToolExecutionRequest",
    "CancellationToken",
    "GeminiToolCallState",
    "JsonValue",
    "TOOL_CANCELLED_REASON_APPROVAL_DENIED",
    "TOOL_CANCELLED_REASON_HOST_CANCELLED",
    "TOOL_CANCELLED_REASON_TIMEOUT",
    "ToolAwaitKind",
    "ToolAwaitSnapshot",
    "ToolAwaitSpec",
    "ToolAwaitingOutcome",
    "ToolBundle",
    "ToolCallProviderState",
    "ToolCallRequest",
    "ToolCallable",
    "ToolCancelledOutcome",
    "ToolCompletedOutcome",
    "ToolDefinition",
    "ToolDisplayInfo",
    "ToolExecutionOutcome",
    "ToolExecutor",
    "ToolFailedOutcome",
    "ToolFunctionSchema",
    "ToolParametersSchema",
    "ToolResultEnvelope",
    "ToolResultFailure",
    "ToolResultMeta",
    "ToolResultSuccess",
    "ToolSchema",
    "ToolTruncateSpec",
    "ToolTruncationStrategy",
    "tool",
]
```

### 7.1 Controller 再修正：保留 `@tool` 装饰器与 `ToolCallable`

Controller 紧接着补充修正：

- `@tool(...)` 必须保留为 *装饰器*，由 Host / ToolRuntime 在工具函数现场
  使用，不能退化为只产出 `ToolDefinition` 的工厂函数。
- 单工具调用协议命名为 `ToolCallable`，形状固定为
  `async (call: ToolCallRequest, context: BatchToolExecutionContext) -> ToolExecutionOutcome`。
- `ToolDefinition` 保留 `callable: ToolCallable` 字段，但 *不* 包含
  `executor` 字段；`FunctionToolExecutor` / `ToolFunctionCallable` 仍然
  完全移除。
- `@tool(...)` 返回 `Callable[[ToolCallable], ToolDefinition]`；被装饰
  的异步函数即 `ToolDefinition.callable`。
- 公共契约层不创建任何默认 executor / helper / adapter；把一组
  `ToolCallable` 装配成受治理的批式 `ToolExecutor` 仍是 Host /
  ToolRuntime 的职责。
- Engine 不消费 `ToolDefinition` / `ToolBundle` / `ToolCallable`，仍仅
  消费 `tool_schemas` 与 `tool_executor`。
- 测试断言 `definition.callable is _echo_tool`、`not hasattr(definition,
  "executor")`、`isinstance(definition.callable, ToolCallable)`；
  `dayu.contracts` 包导出加入 `ToolCallable`，移除
  `ToolFunctionCallable` / `FunctionToolExecutor`。

## 8. 风险与未覆盖项

- Host / ToolRuntime 把一组 `ToolCallable` 包装为受治理批式
  `ToolExecutor` 的实现尚未进入本 slice；本 slice 仅锁定公共契约形状与
  Engine 内部一致性。
- 兼容性 re-export / wrapper / facade 已全部移除；如发现仍残留任何
  per-call helper，应视为违反 Slice 1 的硬边界。

## 8.1 Cleanup: Runner docstring 去 `ToolExecutionContext`

`dayu/engine/contracts/runner.py::AsyncRunner.call` docstring 历史上提到
Runner 实现需要协作式观察 `ToolExecutionContext` / Agent 注入的
`CancellationToken`。`ToolExecutionContext` 已在公共契约层移除；Runner
也从未观察工具执行上下文。

按当前契约，docstring 已更新为：Runner 协作式观察由 Engine / Runner
调用边界注入的 `CancellationToken`（run / request 粒度，归 Agent 请求
所有），不观察工具执行上下文，也不参与工具批式握手。

验证：

```
pytest tests/engine/test_package_exports.py tests/engine/test_protocols_surface.py
# 5 passed
pyright
# 0 errors, 0 warnings, 0 informations
```

## 9. 验证清单

- [x] `pytest tests/contracts/test_tool_declaration.py
      tests/contracts/test_package_exports.py
      tests/engine/test_package_exports.py` 全部通过。
- [x] `pytest tests/contracts/test_tool_outcome_exhaustive.py
      tests/engine/test_agent_phase2.py
      tests/engine/test_agent_phase3_tool_call.py
      tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
      全部通过。
- [x] `pytest` 全量套件 389 passed。
- [x] `pyright` 0 errors / 0 warnings / 0 informations。
- [x] 本 slice 未提交，等待 Controller 后续 gate。
