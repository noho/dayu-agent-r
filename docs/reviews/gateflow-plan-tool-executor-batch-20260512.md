# ToolExecutor Batch Handshake Plan

## 1. Goal

将 `ToolExecutor.execute` 从单工具 bounded handshake 升级为批次 bounded handshake：

```python
async def execute(
    self,
    request: BatchToolExecutionRequest,
) -> BatchToolExecutionOutcome
```

方法名 `execute`、Engine 与 Host / ToolRuntime 的 bounded handshake 语义、`AgentPolicy.tool_execution_timeout_seconds` 的 timeout 真源不变。变化只在 handshake 单位：Engine 对一次 Runner 产生的 tool call batch 调用一次 `ToolExecutor.execute(...)`，不再在 Engine 内部逐个工具调用 executor。

本计划 handoff-ready。未发现必须回到 Controller 才能决定的阻塞问题。

## 2. Motivation / First-Principles Check

动机成立，且不是表面重命名。

当前 Runner 已经以 batch 形式向 Engine 提供工具调用，Engine 事件也已有 `tool_calls_batch_ready` / `tool_calls_batch_done`，但真正执行阶段仍在 `_execute_tool_batch` 内逐个构造 `ToolExecutionRequest` 并串行调用 `ToolExecutor.execute`。这导致 Host / ToolRuntime 无法在真实 batch 边界内统一做审批、限流、受控并发、长事务挂起、tool-level cancelled 和 batch 级资源治理。把 batch 治理放进 Host / ToolRuntime 更符合项目架构：Engine 只维持 LLM loop 和事件状态机，不拥有工具内部执行策略。

用户给定路径“不新增 `execute_batch`、不保留旧单工具 wrapper”也是合理的：双入口会制造两个公共真源，并迫使 Engine / Host 在长期内维护兼容语义。当前应按全新契约迁移。

## 3. Direct Evidence From Current Code

- `dayu/contracts/tool_executor.py:25`：`ToolExecutor.execute` 当前入参是 `ToolExecutionRequest`，返回 `ToolExecutionOutcome`，docstring 仍写“执行一次工具调用”。
- `dayu/contracts/tool_call.py:74-110`：`ToolExecutionContext` 当前含 `tool_call_id` / `index_in_iteration`，`ToolExecutionRequest` 只封装单个 `call`。
- `dayu/contracts/tool_outcome.py:23-57`：per-tool outcome 目前只有 completed / failed / awaiting 三态，没有 tool-level cancelled，也没有 batch outcome。
- `dayu/engine/agent.py:1345-1514`：`_execute_tool_batch` 名义上处理 batch，但内部 `for call in decision.tool_calls` 串行调用 `_execute_one_tool(...)`；遇到 awaiting 立即 `tool_awaiting` + `run_suspended`，后续工具不会进入同一 handshake。
- `dayu/engine/agent.py:1516-1567`：timeout / cancellation race 包裹的是单个 `ToolExecutionRequest`，`_call_tool_executor` 直接调用旧签名。
- `dayu/engine/contracts/engine_events.py:177-209`：`ToolResultAcceptedData` 只接受 completed / failed；`ToolCallsBatchDoneData` 只有 completed / failed counts。
- `dayu/engine/contracts/engine_events.py:212-225` 与 `dayu/engine/contracts/agent_run.py:147-164`：awaiting / suspended 只能承载单个 `await_spec` / `snapshot`。
- `dayu/engine/agent.py:1810-1833` 与 `dayu/engine/agent.py:2268-2277`：`run_suspended` 和 `run_agent_and_wait` 都只映射单个 awaiting fact。
- `dayu/contracts/tool_declaration.py:19-49`：工具声明 helper 仍以旧 `ToolExecutionRequest -> ToolExecutionOutcome` 作为 callable / executor 绑定，需要同步迁移，否则 pyright 会在公共契约层继续暴露旧接口。
- `tests/engine/test_agent_phase3_tool_call.py` 的 fake executor、timeout、awaiting、duplicate、late cancellation 等测试均围绕单工具 request 断言，需要整体迁移到 batch request / batch outcome。
- `docs/engine/design.md:216-303`、`dayu/engine/README.md`、`docs/host/tracking.md` 仍描述单工具 handshake 与单 awaiting suspended fact。

## 4. Non-Goals

- 不新增 `execute_batch`。
- 不保留旧 `ToolExecutor.execute(ToolExecutionRequest) -> ToolExecutionOutcome` wrapper。
- 不提供旧 `ToolExecutionRequest` / 单工具 execute 的兼容读取、兼容导出或兼容测试。
- **硬架构约束：Engine 对 batch 内部执行策略无感知。** Engine 只能对一次 Runner tool-call batch 调用一次 `ToolExecutor.execute(...)`；不得在 Engine 内拆分 batch、并发执行、串行执行、审批、限流或批准部分工具。batch 内部串行、并发、限流、审批、awaiting、tool-level cancellation 均由 Host / ToolRuntime / batch executor 决定。
- 不实现外部长事务恢复、轮询、后台 job 生命周期治理或 orphan cleanup。
- 不改变 Runner 协议，不让 Runner 依赖 ToolExecutor。
- 不引入 `Any` / `object` / extra payload / 魔法状态袋。
- 不把 Host / Service / UI / Fins 依赖引入 Engine 或 `dayu.runtime`。

## 5. Public Contract Changes

### 5.1 Naming Decisions

最终命名固定为：

- `BatchToolExecutionContext`
- `BatchToolExecutionRequest`
- `BatchToolExecutionRecord`
- `BatchToolExecutionOutcome`

不使用 `ToolExecutionBatchRequest`。原因：项目现有事件名已经是 `ToolCallsBatchReadyData` / `ToolCallsBatchDoneData`，但用户目标中的建议签名直接使用 `BatchToolExecutionRequest`。将 `Batch` 作为前缀可以一眼区分旧 single request，并减少实现时误用旧 `ToolExecutionRequest` 的机会。

### 5.2 `dayu.contracts.tool_call`

替换旧单工具执行 request/context：

```python
@dataclass(frozen=True, slots=True)
class BatchToolExecutionContext:
    """工具批次执行运行期上下文。"""

    run_id: str
    session_id: str
    iteration_id: str
    timeout_seconds: float | None
    cancellation_token: CancellationToken
    correlation_id: str | None
```

`correlation_id` 从旧 per-call 语义变为 per-batch 语义。Engine 构造的值固定为 `f"{run_id}:{iteration_id}:tool_batch"`，不包含 `tool_call_id`；需要 per-call 关联的 observer 必须基于 `BatchToolExecutionRecord.tool_call_id` 或 accepted / awaiting record 的 `call.tool_call_id` 自行拼接。

```python
@dataclass(frozen=True, slots=True)
class BatchToolExecutionRequest:
    """工具批次执行入参。"""

    calls: tuple[ToolCallRequest, ...]
    context: BatchToolExecutionContext
```

旧 `ToolExecutionContext` / `ToolExecutionRequest` 从 `__all__` 与包根导出中移除。单工具事实继续由 `ToolCallRequest.tool_call_id` / `index_in_iteration` 承载，避免 batch context 同时携带多个不成立的单工具字段。

### 5.3 `dayu.contracts.tool_outcome`

新增 tool-level cancelled 独立 outcome，不复用 `ToolResultFailure`：

```python
@dataclass(frozen=True, slots=True)
class ToolCancelledOutcome:
    """工具调用被工具层治理取消的终态。"""

    reason: str
    message: str
    hint: str | None
    meta: ToolResultMeta | None
```

决策理由：

- tool-level cancelled 表示 policy cancelled / remote job cancelled / tool-local cancelled，不等于 failed，也不等于 run-level cancellation。
- 复用 `ToolResultFailure` 会让失败计数、fallback 判断、LLM-facing projection 和 Host 诊断混淆。
- `reason` 是中性原因码，`message` 是人类可读描述，`hint` 保持与 failure 相似的可恢复提示能力，`meta` 复用 `ToolResultMeta`。

per-tool outcome 联合升级为：

```python
ToolExecutionOutcome: TypeAlias = (
    ToolCompletedOutcome
    | ToolFailedOutcome
    | ToolAwaitingOutcome
    | ToolCancelledOutcome
)
```

新增 batch record / outcome：

```python
@dataclass(frozen=True, slots=True)
class BatchToolExecutionRecord:
    """批次中单个工具调用的执行记录。"""

    tool_call_id: str
    outcome: ToolExecutionOutcome
```

```python
@dataclass(frozen=True, slots=True)
class BatchToolExecutionOutcome:
    """一次工具批次 handshake 的结果。"""

    records: tuple[BatchToolExecutionRecord, ...]
```

`BatchToolExecutionOutcome` 顶层不提供 `awaitings` 字段。awaiting / cancelled 都只作为 per-tool record 的 outcome 出现。

### 5.4 `ToolExecutor`

`dayu/contracts/tool_executor.py` 改为唯一 batch handshake：

```python
class ToolExecutor(Protocol):
    async def execute(
        self,
        request: BatchToolExecutionRequest,
    ) -> BatchToolExecutionOutcome: ...
```

docstring 必须明确：

- Engine 只发起一次 batch handshake。
- `request.context.timeout_seconds` 是 Engine 等待 batch outcome 的预算投影。
- Engine timeout / run cancellation 会取消承载 execute 的 coroutine task；ToolExecutor / ToolRuntime 必须协作处理 `asyncio.CancelledError`。
- batch 内部串行、并发、限流、审批、等待和工具级取消都属于 ToolExecutor / ToolRuntime。

### 5.5 `dayu.contracts.tool_declaration`

同步迁移公共 helper，禁止继续暴露旧 single request callable：

```python
ToolFunctionCallable = Callable[
    [BatchToolExecutionRequest],
    Awaitable[BatchToolExecutionOutcome],
]
```

`FunctionToolExecutor.execute(...)` 更新为 batch 签名。该 helper 不是旧接口兼容 wrapper；它只适配新的 batch callable。相关测试需要从旧 `_echo_tool(request: ToolExecutionRequest)` 改为返回 `BatchToolExecutionOutcome`。

### 5.6 Assistant Batch Snapshot and Engine Suspension Records

为降低耦合并让 batch snapshot / record 类型独立于 event data 与 run outcome 模块，新增 `dayu/engine/contracts/tool_records.py`，定义 Engine 对外事件 / terminal 共享的记录类型。该模块不声称修复既有 mutual import；当前目标是避免新增 suspended record 类型继续加重 `engine_events.py` 与 `agent_run.py` 的耦合。

```python
@dataclass(frozen=True, slots=True)
class AssistantToolCallBatchSnapshot:
    """一次 assistant tool-call 批次的可恢复快照。"""

    iteration_id: str
    assistant_content: str | None
    assistant_reasoning_content: str | None
    tool_calls: tuple[ToolCallRequest, ...]
```

该 snapshot 是 mixed-awaiting suspended terminal 的恢复真源：

- `assistant_content` 来自触发本批 tool calls 的 assistant message content。
- `assistant_reasoning_content` 来自同一 assistant message 的 reasoning content。
- `tool_calls` 保存完整 `ToolCallRequest` tuple；其中每个 call 的 `arguments`、`index_in_iteration`、`tool_call_id`、`name`、`provider_state` 都必须保留。
- `tool_calls` 顺序必须与 Engine 预校验和 emit `tool_call_requested` 使用的 batch 顺序一致。

记录类型必须携带完整 call identity，而不是只携带 `tool_call_id` / `name` / `index_in_iteration` 的拆散字段：

```python
@dataclass(frozen=True, slots=True)
class AcceptedToolExecutionRecord:
    """Engine 已接受的非 awaiting 工具结果记录。"""

    batch_snapshot: AssistantToolCallBatchSnapshot
    call: ToolCallRequest
    outcome: ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome
```

```python
@dataclass(frozen=True, slots=True)
class AwaitingToolExecutionRecord:
    """Engine 已接受的 awaiting 工具记录。"""

    batch_snapshot: AssistantToolCallBatchSnapshot
    call: ToolCallRequest
    await_spec: ToolAwaitSpec
    snapshot: ToolAwaitSnapshot | None
```

`ToolResultAcceptedData` 改为携带 `record: AcceptedToolExecutionRecord`。

`ToolAwaitingData` 改为携带 `record: AwaitingToolExecutionRecord`。

`RunSuspendedData` 与 `EngineRunOutcomeSuspended` 升级为：

```python
reason: str
resume_hint: RunResumeHint | None
accepted_records: tuple[AcceptedToolExecutionRecord, ...]
awaiting_records: tuple[AwaitingToolExecutionRecord, ...]
```

不再在 suspended terminal 上保留单个 `await_spec` / `snapshot` 字段。

`run_agent_and_wait` 完整消费 stream 后，直接把 terminal `RunSuspendedData.accepted_records` 和 `awaiting_records` 原样映射到 `EngineRunOutcomeSuspended`。这样在混合 batch 中，流式调用方可以从先前 `tool_result_accepted` / `tool_awaiting` 事件拿到事实，聚合调用方也能从 terminal outcome 拿到同源记录，保持 suspension 事实等价。

恢复语义固定为：调用方可以仅凭 `EngineRunOutcomeSuspended.accepted_records` / `awaiting_records` 中任一 record 的 `batch_snapshot` 重建 assistant tool-call roundtrip message；再用每个 record 的 `call` 和 `outcome` / `await_spec` 重建同一批次的 accepted 与 awaiting facts。若 record 之间的 `batch_snapshot` 不一致，属于 Engine bug，测试必须覆盖所有 terminal records 共享同一个 batch snapshot。

Engine 在本 work unit 中不提供公共 reconstruction helper。Engine 只暴露稳定的 snapshot / record data shapes；调用方自行从 `AssistantToolCallBatchSnapshot` 与 accepted / awaiting records 构造 `AssistantMessage` / `ToolMessage`。测试只能验证这些 shape 足够重建 assistant tool-call message，不得新增或导出公共 helper。

### 5.7 Explicit Public Contract Breaks

本 work unit 是 intentional public break，不提供兼容 wrapper、兼容 re-export 或旧字段别名。必须在实现、测试、文档和 completion report 中显式暴露以下破坏面：

- `ToolResultAcceptedData` 不再暴露平铺的 `iteration_id` / `tool_call_id` / `name` / `index_in_iteration` / `outcome` 字段；调用方改为读取 `event.data.record.call`、`event.data.record.outcome` 和 `event.data.record.batch_snapshot`。
- `ToolAwaitingData` 不再暴露平铺的 `tool_call_id` / `await_spec` / `snapshot` 字段；调用方改为读取 `event.data.record.call`、`event.data.record.await_spec`、`event.data.record.snapshot` 和 `event.data.record.batch_snapshot`。
- `RunSuspendedData` 不再暴露单个 `await_spec` / `snapshot`；调用方改为读取 `accepted_records` / `awaiting_records`。
- `EngineRunOutcomeSuspended` 不再暴露单个 `await_spec` / `snapshot`；调用方改为读取 `accepted_records` / `awaiting_records`，并通过 record 内的 `batch_snapshot` 恢复 assistant tool-call message。
- 旧 `ToolExecutionContext` / `ToolExecutionRequest` 从 `dayu.contracts.tool_call`、`dayu.contracts`、相关 package root 和测试导出白名单中移除。
- 旧单工具 `ToolExecutor.execute(ToolExecutionRequest) -> ToolExecutionOutcome` 公共签名消失；唯一入口是 batch request / batch outcome。
- `BatchToolExecutionContext.correlation_id` 从 per-call 变为 per-batch：该字段不再包含 `tool_call_id`。需要 per-call 关联的 observer 改用 record/call 的 `tool_call_id`。
- `ToolCallsBatchDoneData` 新增 `cancelled_count: int` 字段；调用方构造该 dataclass 时必须显式提供该计数。

### 5.8 Package Export Surface

实现时必须显式更新以下 package root，不允许遗漏或通过兼容 re-export 保留旧名字：

- `dayu/contracts/__init__.py`
  - 新增导出：`BatchToolExecutionContext`、`BatchToolExecutionRequest`、`BatchToolExecutionRecord`、`BatchToolExecutionOutcome`、`ToolCancelledOutcome`。
  - 移除导出：`ToolExecutionContext`、`ToolExecutionRequest`。
- `dayu/engine/contracts/__init__.py`
  - 新增导出：`AssistantToolCallBatchSnapshot`、`AcceptedToolExecutionRecord`、`AwaitingToolExecutionRecord`。
- `dayu/engine/__init__.py`
  - 从 `dayu.contracts` 路径 re-export：`BatchToolExecutionContext`、`BatchToolExecutionRequest`、`BatchToolExecutionRecord`、`BatchToolExecutionOutcome`、`ToolCancelledOutcome`。
  - 从 `dayu.engine.contracts` 路径 re-export：`AssistantToolCallBatchSnapshot`、`AcceptedToolExecutionRecord`、`AwaitingToolExecutionRecord`。
  - 移除 re-export：`ToolExecutionContext`、`ToolExecutionRequest`。

对应验证必须包含 `pytest tests/contracts/test_package_exports.py tests/engine/test_package_exports.py`，并用 grep 确认旧 single request/context 没有继续从 package root 暴露。

### 5.9 Engine Internal Accepted Record Semantics

`dayu/engine/agent.py` 内部 `_ToolOutcomeRecord` 必须随 `ToolCancelledOutcome` 迁移。实现时可以将其重命名为更准确的 `_AcceptedOutcomeRecord`，但内部 record 必须携带完整 `call: ToolCallRequest`，不能直接复用只含 `tool_call_id` 的公共 `BatchToolExecutionRecord`。

内部 accepted record 的 outcome union 固定为：

```python
ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome
```

语义要求：

- `ToolCancelledOutcome` 是 accepted fact，不是 failed fact，也不是 run-level cancellation。
- `_count_failed_tool_records` 只统计 `ToolFailedOutcome`。
- `_count_cancelled_tool_records` 单独统计 `ToolCancelledOutcome`。
- `_all_records_failed` 仅在 accepted records 非空且每个 outcome 都是 `ToolFailedOutcome` 时返回 `True`；all-cancelled 与 mixed failed+cancelled 都必须返回 `False`。
- `_project_tool_outcome_for_llm` 必须为 cancelled 输出稳定 JSON projection：`{"cancelled": true, "reason": "...", "message": "...", "hint": "..."}`，`hint is None` 时省略。
- `_inject_tool_messages` 对 completed / failed / cancelled 都注入 LLM-facing tool message；awaiting 不注入。

测试必须覆盖 all-cancelled、all-failed、mixed failed+cancelled 三种计数与 `_all_records_failed` 语义。

## 6. Engine State Transitions

### 6.1 No Awaiting In Batch

硬约束：Engine 对 batch 内部执行策略无感知，只调用一次 `ToolExecutor.execute`，不拆分、不并发、不审批、不限流。任何内部策略都必须在 Host / ToolRuntime / batch executor 内完成。

状态流：

1. Runner 产出完整 tool calls。
2. Agent 排序并预校验 tool call ids。
3. Agent 为每个 call emit `tool_call_requested`。
4. Agent 构造一个 `BatchToolExecutionRequest`，调用一次 `ToolExecutor.execute(...)`。
5. batch outcome 返回后，Agent 按原始 `decision.tool_calls` 顺序处理 records。
6. 对 completed / failed / cancelled emit `tool_result_accepted`。
7. emit `tool_calls_batch_done`，其中包含 accepted tool ids、`completed_count`、`failed_count`、`cancelled_count`。
8. 注入 assistant tool_calls 与对应 tool messages。
9. 继续下一轮 Runner，或按 max-iterations / failed-batch 策略 fallback。

`tool_calls_batch_done` 只在没有 awaiting record 时产出。

### 6.2 Batch Contains Awaiting

状态流：

1. Agent 同样先 emit 所有 `tool_call_requested`，并执行一次 batch handshake。
2. batch outcome 返回后，Agent 按原始 call 顺序先 emit completed / failed / cancelled 的 `tool_result_accepted`。
3. 再按原始 call 顺序 emit 每个 awaiting 的 `tool_awaiting`。
4. 关闭 Runner。
5. emit terminal `run_suspended`，`accepted_records` 包含同一 batch 中已接受的 completed / failed / cancelled，`awaiting_records` 包含所有 awaiting。
6. 不 emit `tool_calls_batch_done`，不向下一轮 Runner 注入 tool messages，不进入 fallback。

原因：存在 awaiting 时，本批工具 roundtrip 尚不能形成完整 LLM-facing tool message 组；恢复由调用方在新 run 中显式构造 messages。

### 6.3 Tool-Level Cancelled

`ToolCancelledOutcome` 是普通 per-tool accepted fact：

- emit `tool_result_accepted`。
- 无 awaiting 时注入 LLM-facing tool message。
- 不触发 `run_cancelled`。
- 不计入 `failed_count`，单独计入 `cancelled_count`。
- 不参与“连续全失败工具批次”判定；只有全部 accepted records 都是 `ToolFailedOutcome` 时才增加 `_consecutive_failed_tool_batches`。

LLM projection 建议：

```json
{"cancelled": true, "reason": "...", "message": "...", "hint": "..."}
```

`hint` 为 `None` 时省略。

## 7. Error and Race Semantics

- **run-level cancellation wins before batch outcome**：`await_or_cancel_or_timeout` 返回 `WaitCancelled` 时，Engine 收口 `run_cancelled`。
- **batch handshake timeout**：`WaitTimedOut` 收口不可恢复 `run_failed(tool_execution_timeout)`，保持现有错误码和 late cancel 不覆盖 timeout 的提交边界。
- **executor 普通异常**：转换为一个 `BatchToolExecutionOutcome`，为本次输入 batch 的每个 call 生成 `ToolFailedOutcome(error="tool_executor_exception")`，随后按普通 accepted facts 处理。这样不丢失 provider tool call 配对能力。
- **executor 抛 `asyncio.CancelledError` 且 token 已取消**：透传到 wait helper，收口 `run_cancelled`。
- **executor 抛 `asyncio.CancelledError` 但 token 未取消**：转换为每个 call 的 `ToolFailedOutcome(error="tool_executor_exception")`。
- **batch outcome records 与输入 calls 不构成严格双射**：新增不可恢复 `run_failed(tool_batch_outcome_mismatch)`。校验规则固定为 `len(records) == len(calls)`，每个输入 `tool_call_id` 必须且只能出现一次，不允许未知 id，不允许重复返回 id；即使 set equality 看似成立，只要存在 duplicate returned id 也必须 fatal。不尝试猜测缺失 call，也不注入不完整 tool messages。
- **duplicate tool_call_id**：在 batch execute 前预校验；发现当前 batch 内重复或 run 内已执行 id，收口 `run_failed(duplicate_tool_call_id)`，不调用 executor。
- **outcome 返回后 late cancellation**：completed / failed / cancelled 先 emit accepted facts；awaiting 先 emit awaiting facts 与 suspended；late cancellation 不覆盖已经返回的 batch facts。

## 8. Affected Files / Modules

### Contracts

- `dayu/contracts/tool_call.py`
- `dayu/contracts/tool_outcome.py`
- `dayu/contracts/tool_executor.py`
- `dayu/contracts/tool_declaration.py`
- `dayu/contracts/__init__.py`
- `dayu/engine/__init__.py`

### Engine Contracts

- `dayu/engine/contracts/tool_records.py`（新增）
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/__init__.py`

### Engine Runtime

- `dayu/engine/agent.py`

### Tests

- `tests/contracts/test_tool_outcome_exhaustive.py`
- `tests/contracts/test_tool_declaration.py`
- `tests/contracts/test_package_exports.py`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`

### Docs

- `dayu/engine/README.md`
- `docs/engine/design.md`
- `docs/host/tracking.md`

### Host / Service Discovery

Implementation planning and final validation must run:

```bash
rg "ToolExecutor|execute.*ToolExecutionRequest" dayu/host dayu/service
```

当前 plan-fix 证据（2026-05-12）：`dayu/host` 与 `dayu/service` 均不存在，所以本 work unit 不包含 Host code migration。如果 implementation-time discovery 仍然没有 Host / Service 文件，记录该命令因目录不存在返回的 stderr / exit code，并说明无需 Host 代码迁移，只新增或更新 `docs/host/tracking.md` 中 Host / ToolRuntime batch executor ownership 与 orphan cleanup 跟踪说明。如果该命令发现当前代码且 pyright 要求迁移，只做本 work unit 必需的最小修改；不要扩展成新的 Host 实现设计。

`tests/README.md` 只在测试分层、运行方式或维护规则变化时更新；本 work unit 只是迁移测试断言，不需要机械修改。根 `README.md` 不涉及用户安装 / CLI / trace / render 入口变化，不更新。

## 9. Implementation Slices

每个 slice 都是 pyright-green review checkpoint。不得提交或交付“pyright may fail until later slice”的中间状态。

Slice 1 保留为 vertical checkpoint，而不是拆成 contracts-only / engine-only 两个交付 slice。原因是本 work unit 禁止旧 single request/context 兼容 wrapper、facade 或 re-export；若把 contracts-only 作为独立交付点，要么 Engine 仍引用已删除旧类型导致 pyright-red，要么被迫引入临时兼容层。这里的第一性原理判断是：降低 handoff 风险必须靠更细的 implementation order、dependency batches、局部验证和明确 stop condition，而不是为了形式拆分制造兼容层。

Slice 1 内部必须按下面的 dependency batches 实施。dependency batch 是实现过程的审计边界，不是可交付 slice；最终只有 Slice 1 完成后才允许交付。实现 agent 应在每个 batch 后运行列出的检查，并在 completion report 中记录结果。

- **Batch 1A: additive contract shapes**：新增 batch request/context、batch outcome/record、`ToolCancelledOutcome`、Engine snapshot/record 类型；暂不删除旧 single request/context，暂不保留任何兼容 wrapper。检查：`pyright`；必要时运行 contracts package export 测试的更新中间态。
- **Batch 1B: public signature and export switch**：切换 `ToolExecutor`、`ToolFunctionCallable`、package roots 与 export tests；移除旧 single request/context 导出。检查：`pytest tests/contracts/test_tool_outcome_exhaustive.py tests/contracts/test_tool_declaration.py tests/contracts/test_package_exports.py` 与 `pyright`。
- **Batch 1C: Engine event/outcome and agent vertical migration**：迁移 Engine event data、run suspended outcome、`agent.py` batch handshake、内部 accepted record 语义、projection/injection/count helpers。检查：`pytest tests/engine/test_package_exports.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py` 与 `pyright`。
- **Batch 1D: touched runner test and repository cleanup**：迁移 remaining touched tests，运行 grep 清理旧 single request/context 使用。检查：完整 Slice 1 pytest 命令、`pyright`、`rg "ToolExecutionRequest|ToolExecutionContext|execute\\(self, request: ToolExecutionRequest"`。

### Slice 1: Vertical Batch Contract and Agent Migration

Files:

- `dayu/contracts/tool_call.py`
- `dayu/contracts/tool_outcome.py`
- `dayu/contracts/tool_executor.py`
- `dayu/contracts/tool_declaration.py`
- `dayu/contracts/__init__.py`
- `dayu/engine/contracts/tool_records.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/__init__.py`
- `dayu/engine/agent.py`
- `tests/contracts/test_tool_outcome_exhaustive.py`
- `tests/contracts/test_tool_declaration.py`
- `tests/contracts/test_package_exports.py`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- any remaining files found by `rg "ToolExecutionRequest|ToolExecutionContext|execute\\(self, request: ToolExecutionRequest"`

Steps:

1. Replace `ToolExecutionContext` / `ToolExecutionRequest` with `BatchToolExecutionContext` / `BatchToolExecutionRequest`.
2. Add `ToolCancelledOutcome`, `BatchToolExecutionRecord`, `BatchToolExecutionOutcome`.
3. Expand `ToolExecutionOutcome` to four per-tool variants.
4. Update `ToolExecutor.execute` protocol signature.
5. Update `ToolFunctionCallable` and `FunctionToolExecutor.execute(...)` to the batch request / batch outcome signature; this is a new batch helper, not a compatibility wrapper.
6. Add `AssistantToolCallBatchSnapshot`, `AcceptedToolExecutionRecord` and `AwaitingToolExecutionRecord`.
7. Change `ToolResultAcceptedData` to `record: AcceptedToolExecutionRecord`.
8. Change `ToolAwaitingData` to `record: AwaitingToolExecutionRecord`.
9. Add `cancelled_count` to `ToolCallsBatchDoneData`.
10. Change `RunSuspendedData` and `EngineRunOutcomeSuspended` to `accepted_records` / `awaiting_records`.
11. Export new batch and record types from package roots exactly as specified in §5.8:
    - `dayu/contracts/__init__.py` adds `BatchToolExecutionContext`、`BatchToolExecutionRequest`、`BatchToolExecutionRecord`、`BatchToolExecutionOutcome`、`ToolCancelledOutcome` and removes `ToolExecutionContext`、`ToolExecutionRequest`.
    - `dayu/engine/contracts/__init__.py` adds `AssistantToolCallBatchSnapshot`、`AcceptedToolExecutionRecord`、`AwaitingToolExecutionRecord`.
    - `dayu/engine/__init__.py` re-exports `AssistantToolCallBatchSnapshot`、`AcceptedToolExecutionRecord`、`AwaitingToolExecutionRecord`、`BatchToolExecutionContext`、`BatchToolExecutionRequest`、`BatchToolExecutionRecord`、`BatchToolExecutionOutcome`、`ToolCancelledOutcome` and removes `ToolExecutionContext`、`ToolExecutionRequest`.
12. Replace `dayu/engine/agent.py` imports from old request/context to batch request/context, batch outcome and new Engine record types.
13. Add a private helper to build `AssistantToolCallBatchSnapshot` from the triggering assistant output:
    - `iteration_id` from the current iteration.
    - `assistant_content` from the assistant message content that produced the tool calls.
    - `assistant_reasoning_content` from the assistant reasoning content that produced the tool calls.
    - `tool_calls` as the full ordered `tuple[ToolCallRequest, ...]`.
14. Add a private helper to build `BatchToolExecutionRequest`:
    - `calls = batch_snapshot.tool_calls`
    - context run/session/iteration from current run
    - context timeout from `AgentPolicy.tool_execution_timeout_seconds`
    - context cancellation token from request
    - context correlation id = `f"{run_id}:{iteration_id}:tool_batch"`
15. Prevalidate duplicate ids before emitting `tool_call_requested` or calling executor.
16. Emit `tool_call_requested` for every call in sorted batch order.
17. Replace single-call executor flow with one `_execute_tool_batch_handshake`, returning `WaitCompleted[BatchToolExecutionOutcome] | WaitCancelled | WaitTimedOut`.
18. Replace `_call_tool_executor` to call `tool_executor.execute(batch_request)`.
19. On ordinary exception or non-run cancellation, synthesize failed batch outcome for every input call.
20. Validate returned records with strict bijection:
    - `len(records) == len(calls)`
    - every input id appears exactly once
    - no unknown returned id
    - no duplicate returned id, fatal even if set equality would pass
21. Process records in input call order, not executor return order.
22. Build accepted / awaiting records with both `batch_snapshot` and full `call: ToolCallRequest`.
23. Emit accepted records first, then awaiting records.
24. If awaiting records exist, call new suspended helper with both record tuples; do not emit `tool_calls_batch_done`, do not inject tool messages, and do not call the next Runner.
25. If no awaiting records exist, emit `tool_calls_batch_done` with completed / failed / cancelled counts, set `_last_tool_batch_result`, inject tool messages, continue existing fallback logic.
26. Migrate internal accepted record semantics:
    - update `_ToolOutcomeRecord.outcome` to `ToolCompletedOutcome | ToolFailedOutcome | ToolCancelledOutcome` or rename it to an equivalent private accepted-record type carrying full `call`.
    - add / update cancelled count helper.
    - keep failed count limited to `ToolFailedOutcome`.
    - make `_all_records_failed` true only for non-empty all-failed accepted records; all-cancelled and mixed failed+cancelled return false.
    - update `_project_tool_outcome_for_llm`, `_tool_outcome_name` and `_inject_tool_messages` for cancelled projection/injection.
27. Update `run_agent_and_wait` suspended mapping to preserve `accepted_records` and `awaiting_records` exactly.
28. Add basic batch happy-path behavior tests in the first green implementation slice:
    - multiple tool calls produce exactly one executor call.
    - every input tool call produces an accepted or awaiting record as appropriate.
    - no-awaiting batch emits `tool_calls_batch_done` with completed / failed / cancelled counts.
29. Migrate all existing tests and fake executors touched by the removed old request/context exports so the repository is pyright-green at the end of this slice.

Validation:

- `source .venv/bin/activate && pytest tests/contracts/test_tool_outcome_exhaustive.py tests/contracts/test_tool_declaration.py tests/contracts/test_package_exports.py tests/engine/test_package_exports.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- `source .venv/bin/activate && pyright`
- `rg "ToolExecutor|execute.*ToolExecutionRequest" dayu/host dayu/service` and document whether Host / Service code exists.
- `rg "correlation_id" dayu tests docs` and document every remaining consumer of the per-batch correlation id.

Expected assertions:

- Batch executor receives exactly one `BatchToolExecutionRequest` for multiple tool calls.
- `BatchToolExecutionRequest.calls` preserves sorted `index_in_iteration` order.
- Every tool in a multi-tool batch produces exactly one accepted or awaiting record in the original call order.
- No-awaiting batch emits `tool_calls_batch_done` with correct `completed_count` / `failed_count` / `cancelled_count`.
- Event data shapes use `record`, and records carry `batch_snapshot` plus full `call`.
- `RunSuspendedData` and `EngineRunOutcomeSuspended` expose `accepted_records` / `awaiting_records`, not single awaiting fields.
- Old `ToolExecutionRequest` / `ToolExecutionContext` exports are absent.
- `ToolCancelledOutcome` is accepted but not failed: all-cancelled and mixed failed+cancelled do not satisfy `_all_records_failed`; all-failed does.

Stop condition:

- If this slice cannot pass pyright without reintroducing old single request/context compatibility, stop and return to Controller; do not create temporary compatibility facades.
- If migration produces more than 20 non-test production pyright errors after Batch 1B or later, stop and return to Controller with the error categories and affected modules.
- If pyright errors spread outside the files listed in §8, stop and return to Controller before broadening scope.
- If errors cannot be driven to zero without restoring old single request/context compatibility, stop and return to Controller.

### Slice 2: Batch Semantics and Edge-Case Hardening

Files:

- `dayu/engine/agent.py`
- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`

Steps:

1. Add strict mismatch tests and implementation fixes if Slice 1 only covered the happy path:
   - missing returned id fails with `tool_batch_outcome_mismatch`
   - unknown returned id fails with `tool_batch_outcome_mismatch`
   - duplicate returned id fails with `tool_batch_outcome_mismatch`, including cases where set equality could hide the duplicate
   - non-input return order is accepted but processed in input order
2. Add mixed batch tests:
   - completed + failed + cancelled batch emits accepted records then `tool_calls_batch_done`
   - completed + cancelled + awaiting emits accepted first, then all `tool_awaiting`, then `run_suspended`
   - awaiting batch does not inject messages, does not emit `tool_calls_batch_done`, and does not call the next Runner
3. Add `run_agent_and_wait` mixed-awaiting test that reconstructs the assistant tool-call message from `record.batch_snapshot`, including assistant content, assistant reasoning content, full `ToolCallRequest.arguments`, and `ToolCallRequest.provider_state`.
4. Add executor exception, timeout and cancellation regression assertions for the batch handshake.
5. Add public event/outcome shape assertions for `ToolResultAcceptedData.record`, `ToolAwaitingData.record`, `RunSuspendedData.accepted_records/awaiting_records`, and `EngineRunOutcomeSuspended.accepted_records/awaiting_records`.
6. Update any remaining tests discovered by `rg "await_spec|snapshot|tool_call_id" tests/engine` where the access is specifically to old event/outcome flat fields.

Validation:

- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- `source .venv/bin/activate && pyright`

### Slice 3: Documentation Sync

Files:

- `dayu/engine/README.md`
- `docs/engine/design.md`
- `docs/host/tracking.md`

Steps:

1. Update Engine docs from single tool handshake to batch handshake.
2. Document `BatchToolExecutionRequest`, `BatchToolExecutionOutcome`, per-tool records and `ToolCancelledOutcome`.
3. Document `AssistantToolCallBatchSnapshot` as the suspended mixed-awaiting resume snapshot.
4. Document mixed awaiting batch event order and suspended terminal shape.
5. Document public migration from old flat event/outcome fields to `record` / `accepted_records` / `awaiting_records`.
6. Document removal of old single request/context exports.
7. Document that Engine does not execute tools internally in parallel; Host / ToolRuntime owns internal batch strategy.
8. Update `docs/engine/design.md` state machine text / diagram so `SUSPENDED` originates from a batch outcome containing at least one awaiting record, not from a single `ToolAwaitingOutcome`; document that the terminal carries both `accepted_records` and `awaiting_records`.
9. Document that recovery callers can reconstruct the assistant tool-call message from any terminal record's `batch_snapshot`, but Engine does not provide a public reconstruction helper in this work unit.
10. Update Host tracking to mention batch executor ownership for approval, concurrency, rate limit, tool-level cancellation and orphan cleanup.
11. Remove old single `ToolExecutionRequest` / single awaiting wording from touched docs.

Validation:

- `source .venv/bin/activate && pytest tests/engine tests/contracts`
- `source .venv/bin/activate && pyright`
- Optional doc sanity: `rg "ToolExecutionRequest|ToolExecutionContext|single tool|单个|ToolExecutor returned ToolAwaitingOutcome" dayu/engine/README.md docs/engine/design.md docs/host/tracking.md`

Expected assertions:

- Documentation describes the current implemented API only; no future-design language.
- Public breakage is presented as migration guidance, not as a compatibility promise.

## 10. Test / Validation Matrix

Required final validation after all slices:

```bash
source .venv/bin/activate && pytest tests/contracts tests/engine
source .venv/bin/activate && pyright
```

Focused behavioral assertions:

- Multi-tool Runner batch causes exactly one `ToolExecutor.execute(BatchToolExecutionRequest)` call.
- Engine emits `tool_call_requested` for every call before batch execute.
- Batch request preserves sorted `index_in_iteration` order.
- Batch context carries run/session/iteration/timeout/cancellation/correlation_id, not per-tool id fields.
- Batch context `correlation_id` is per-batch and does not include `tool_call_id`; grep documents all remaining consumers.
- `AssistantToolCallBatchSnapshot` preserves iteration id, assistant content, assistant reasoning content, full `ToolCallRequest` tuple, `arguments` and `provider_state`.
- Completed / failed / cancelled records emit `tool_result_accepted` with `record.call` and `record.batch_snapshot`.
- `ToolCancelledOutcome` is not counted as failed and does not produce `run_cancelled`.
- No-awaiting batch emits `tool_calls_batch_done` with completed / failed / cancelled counts.
- Awaiting batch emits accepted records first, then all `tool_awaiting`, then `run_suspended`.
- Awaiting batch does not emit `tool_calls_batch_done`, does not inject messages, does not call next Runner.
- `RunSuspendedData` and `EngineRunOutcomeSuspended` include all accepted and awaiting records; no old single `await_spec` / `snapshot` fields remain.
- `run_agent_and_wait` mixed-awaiting outcome is sufficient to reconstruct the assistant tool-call message from `record.batch_snapshot`, including provider state.
- Timeout before batch outcome remains `run_failed(tool_execution_timeout)`.
- Run cancellation before batch outcome remains `run_cancelled`.
- Executor ordinary exception becomes per-call failed records.
- Missing returned id becomes `run_failed(tool_batch_outcome_mismatch)`.
- Unknown returned id becomes `run_failed(tool_batch_outcome_mismatch)`.
- Duplicate returned id becomes `run_failed(tool_batch_outcome_mismatch)`, including duplicate cases that set equality would hide.
- Non-input record order is accepted but processed in original input order.
- Public event shape assertions cover `ToolResultAcceptedData.record`, `ToolAwaitingData.record`, `RunSuspendedData.accepted_records/awaiting_records`, and `EngineRunOutcomeSuspended.accepted_records/awaiting_records`.
- Package exports contain new batch symbols and no old single request/context symbols.
- Package export tests explicitly cover `AssistantToolCallBatchSnapshot`、`AcceptedToolExecutionRecord`、`AwaitingToolExecutionRecord`、`BatchToolExecutionContext`、`BatchToolExecutionRequest`、`BatchToolExecutionRecord`、`BatchToolExecutionOutcome`、`ToolCancelledOutcome`.
- Host / Service discovery command has been run; absent Host / Service implementation is documented, or any pyright-required current code has been minimally migrated.

Coverage expectation:

- Modified production files should keep single-file coverage at or above 80% where coverage is measured.
- `dayu/render/` and `utils/` are not touched.

## 11. Docs Decision

Docs must be updated after tests pass, because this work changes current public behavior and Engine / Host boundary language.

Update:

- `dayu/engine/README.md` because `dayu/engine/` behavior and public Engine contract change.
- `docs/engine/design.md` because it currently documents the old single-tool handshake and single awaiting suspended fact.
- `docs/host/tracking.md` because Host / ToolRuntime gains explicit batch executor ownership for concurrency, approval, cancellation and orphan cleanup.

Docs must explicitly mention the public event/outcome migration from flat fields to `record` / `accepted_records` / `awaiting_records`, the new `AssistantToolCallBatchSnapshot`, the removal of old single request/context exports, and the `docs/engine/design.md` state-machine change: `SUSPENDED` now comes from a batch outcome with at least one awaiting record and terminal data simultaneously carries accepted and awaiting records.

Do not update:

- root `README.md` unless implementation discovers user-facing CLI / config / trace entry changes.
- `tests/README.md` unless test layering or run commands change.
- `dayu/README.md` unless implementation changes overall `UI -> Service -> Host -> Engine` layering or assembly boundaries. This plan does not.

## 12. Risks and Residual Risk Tracking

- **Risk: mixed awaiting batch resume needs more than awaiting facts.** Mitigation: every accepted / awaiting record carries full `call: ToolCallRequest` and an `AssistantToolCallBatchSnapshot` containing iteration id, assistant content, assistant reasoning content and full tool call tuple, so stream and wait callers can reconstruct the assistant tool-call roundtrip for later explicit resume.
- **Risk: ToolRuntime returns missing, unknown or duplicate records.** Mitigation: Engine validates strict bijection with `len(records) == len(calls)`, every input id exactly once, no unknown id and no duplicate returned id; mismatch fails closed with `tool_batch_outcome_mismatch`.
- **Risk: executor internal parallelism creates nondeterministic record order.** Mitigation: Engine processes returned records by original call order, not executor return order.
- **Risk: tool-level cancelled gets misclassified as run cancellation.** Mitigation: separate `ToolCancelledOutcome`; run cancellation is only `WaitCancelled` / cancellation token winning the batch handshake.
- **Risk: failed-batch policy changes subtly.** Mitigation: only all-`ToolFailedOutcome` batches increment consecutive failed counter; cancelled is tracked separately.
- **Residual risk: timeout after a batch executor has started external jobs may leave orphan work.** Tracking expectation: keep this documented as Host / ToolRuntime responsibility in `docs/host/tracking.md`; Engine cannot recover without returned awaiting records.
- **Residual risk: downstream app code importing old `ToolExecutionRequest` or reading old flat event/outcome fields breaks.** This is intentional under “no compatibility” constraint; implementation report and docs must call out old single request/context exports, `ToolResultAcceptedData` / `ToolAwaitingData` flat fields, `RunSuspendedData.await_spec/snapshot`, and `EngineRunOutcomeSuspended.await_spec/snapshot` as public contract breaks.

## 13. Completion Report Format

Implementation completion report must include:

- 改了什么：按 contracts / Engine state machine / tests / docs 分组说明。
- 验证了什么：列出实际运行的 pytest 命令与 pyright 结果。
- 风险或未覆盖项：尤其是 Host / ToolRuntime orphan cleanup、外部调用方旧导入破坏、旧平铺 event/outcome 字段破坏、是否仍有未迁移文档残留。
- Public contract break summary：明确列出 `ToolResultAcceptedData.record`、`ToolAwaitingData.record`、`RunSuspendedData.accepted_records/awaiting_records`、`EngineRunOutcomeSuspended.accepted_records/awaiting_records`、旧 single request/context exports 移除、`correlation_id` per-call 到 per-batch 的语义变化、`ToolCallsBatchDoneData.cancelled_count` 新增字段。
- Package export summary：明确列出新增/移除的 `dayu/contracts/__init__.py`、`dayu/engine/contracts/__init__.py`、`dayu/engine/__init__.py` 符号。
- Host / Service discovery summary：报告 `rg "ToolExecutor|execute.*ToolExecutionRequest" dayu/host dayu/service` 结果；若目录缺失或无实现，说明本 work unit 没有 Host code migration，只更新 Host tracking。
- 若有未完成项，明确是否阻塞 handoff。

## 14. Blocking Questions For Controller

无。
