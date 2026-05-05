# Phase 3 EngineWorker ToolExecutor Tool Calling 闭环计划

本文档是 Phase 3 的实施计划。当前任务只更新计划文档，不实施代码、不提交 commit、不 push。

## 0. 动机与范围

Phase 3 动机成立。

直接证据：

- Phase 2 已落地 run-scoped Agent 骨架、RunnerEvent -> EngineEvent 提升、唯一 terminal、取消优先级和 Runner close。
- 当前 `AgentRunRequest` 已包含 `tool_schemas`、`tool_executor`、`cancellation_token`；`dayu.contracts` 已有 `ToolExecutionRequest`、`ToolExecutionOutcome`、`ToolCompletedOutcome`、`ToolFailedOutcome`、`ToolAwaitingOutcome`。
- Runner 已能把模型 tool call 归一为 `RunnerToolCallsCompletedData(tool_calls=tuple[ToolCallRequest, ...])`，且 Runner 不依赖 ToolExecutor。
- OLD `AsyncAgent` 的普通 tool calling 状态机可靠，是本 Phase 的强参考源。

Phase 3 要落地：

- 模型请求 tool call。
- Agent 构造 `ToolExecutionRequest`。
- Agent 调用 EngineWorker 替 Host 代持并提供的 `ToolExecutor.execute(request)`。
- Agent 接收 completed / failed outcome。
- Agent 产出工具相关 `EngineEvent`。
- Agent 注入 assistant tool_calls 与 LLM-facing tool messages。
- 下一轮 Runner 消费工具结果并收口 `final_answer` / `run_failed` / `run_cancelled`。

Phase 3 明确不做：

- 不实现 awaiting / `run_suspended`。
- 不实现远程 RPC、LocalProxy、RemoteProxy、RemoteStub。
- 不实现 EngineWorker 生产代码。
- 不实现 HostEvent / WorkerEvent。
- 不实现 Host ToolRegistry、ToolRuntime、工具注册、权限、审计、路径白名单、长事务等待。
- 不迁移 OLD Runner 执行工具职责。
- 不为 OLD 接口保留兼容 wrapper / facade / re-export。
- 不实现 context budget、continuation、conversation memory、trace store、transcript。
- 不处理 Issue #10 的 provider-specific reasoning patch；Phase 3 只保留 OLD 已验证的过渡 roundtrip 行为。

Phase 3 本次修订新增 blocking 项：

- LLM-facing tool result projection 必须按 OLD `project_for_llm()` 可靠语义实现，禁止把内部 `ToolResultEnvelope` 直接写入 `ToolMessage.content`。
- `max_iterations` 耗尽默认必须走 force-answer 降级收尾；只有 `fallback_mode=RAISE_ERROR` 才直接 `run_failed("max_iterations_exceeded")`。
- `FinalAnswerData.degraded` 必须覆盖 force-answer 与 content_filter 两类降级语义，不能只绑定 force-answer。
- 连续失败工具批次保护必须在 Phase 3 落地，不能后移到 Phase 5。

最新分层口径：

```text
UI -> Service -> Host -> Engine
```

`EngineWorker` 是 Host 的 capability，不是新的顶层业务层。Remote Agent 的含义是 `Engine + tools execute remotely`，不是远程 Engine 回调 Host 进程执行工具。

## 1. 阅读范围

### 1.1 本次必须阅读文档

- `/Users/leo/workspace/dayu-agent-r/docs/host/design.md`
- `/Users/leo/workspace/dayu-agent-r/docs/engine/design.md`
- `/Users/leo/workspace/dayu-agent-r/docs/engine/migration-plan.md`
- `/Users/leo/workspace/dayu-agent-r/docs/engine/phase3-plan.md`
- `/Users/leo/workspace/dayu-agent-r/docs/code_review.md`

### 1.2 计划沿用的 NEW 代码阅读范围

- `dayu/contracts/`
- `dayu/engine/contracts/`
- `dayu/engine/agent.py`
- `dayu/engine/runners/openai/`
- `dayu/runtime/`
- `utils/smoke_async_agent_providers.py`
- `tests/engine/test_agent_phase2.py`
- `tests/README.md`

### 1.3 OLD 强参考源

- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/README.md`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_agent.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner_utils.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner_call_paths.py`

OLD 强参考语义：

- tool call 后本轮不能直接 final answer。
- assistant tool_calls 与后续 tool messages 必须成组注入。
- 工具失败是普通工具结果，进入 LLM 上下文。
- 多个 tool call 按 index 稳定排序。
- provider_state 必须通过强类型字段在 tool roundtrip 中保留。
- Phase 3 暂按 OLD 已证明可行的行为，把本轮 `reasoning_content` 随 assistant tool_calls 写回；这只是过渡实现，不代表跨 provider 最优策略。
- 达到最大工具调用轮次后，默认进入 `force_answer` 降级收尾：追加 fallback prompt、临时禁用工具、再次调用 Runner，并产出 degraded final answer。
- 只有 `fallback_mode="raise_error"` 时，OLD 才在最大轮次耗尽后直接 error / fail。
- force-answer Runner 空内容时，OLD 使用 `force_answer_empty` 错误收口。
- `project_for_llm()` 是 LLM-facing tool message 投影强参考：成功 dict 展开、成功非 dict 包 `content`、失败只给 `error/message/hint`，不暴露内部 `ok/value` 信封。
- 空工具结果仍必须注入非空 tool message 占位，保证 assistant.tool_calls 与 tool messages 配对完整。
- 连续失败工具批次达到阈值后按 fallback mode 收口；默认阈值参考 OLD 为 2，成功批次会清零计数。
- content_filter 产出 `filtered=True, degraded=True` 的 final answer，不触发 continuation。
- 取消优先于 final / failed。
- Runner close 在 success / failure / cancellation 中执行。

OLD 不能迁移的旧边界：

- Runner 执行工具。
- `set_tools`。
- ToolRegistry / ToolRuntime 进入 Engine。
- ToolTraceRecorder / trace store 进入 Engine。
- OLD duplicate guard 对 `get_dup_call_spec`、display info、middleware 的依赖。
- OLD `AsyncAgent._run_loop` God function 结构。
- OLD string literal `fallback_mode` 边界；NEW 必须使用封闭 enum。
- `StreamEvent(data: Any, metadata: dict)` 弱类型边界。

## 2. EngineWorker 与 ToolExecutor 边界

### 2.1 正确口径

Phase 3 的正确边界是：

```text
Host 选择 / 控制 EngineWorker
EngineWorker 替 Host 代持并提供 ToolExecutor
Engine 调用 ToolExecutor protocol
```

说明：

- Host 是生命周期、取消、治理、工具策略、ToolRuntime / ToolRegistry 和执行环境选择的真源。
- ToolExecutor 不是 EngineWorker 的治理所有物。
- EngineWorker 只是替 Host 在选定执行环境中代持 ToolExecutor，并把 protocol handle 提供给 Engine。
- Engine 只消费 `AgentRunRequest`、`RunnerSpec`、`ToolExecutor` protocol、`CancellationToken` 等契约。
- Engine 不知道 LocalProxy、RemoteProxy、RemoteStub、RPC 或 ToolExecutor 的真实部署位置。

本文中若出现 “ToolExecutor 注入”，均指 “EngineWorker 替 Host 代持并通过 `AgentRunRequest.tool_executor` 提供给 Engine”，不是 Host 进程直接执行工具。

### 2.2 EngineWorker 第一版最小接口

EngineWorker 由 Host 侧实现，不在 Phase 3 落地到 Engine 生产代码。计划只需不阻碍该边界。

```python
class EngineWorker(Protocol):
    def run_agent_messages(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]: ...

    async def cancel(self, run_id: str) -> None: ...

    async def close(self) -> None: ...
```

注意：

- `AgentRunRequest` 已包含 `session_id`、`run_id`、`cancellation_token`，EngineWorker 方法签名不得重复展开这些参数。
- LocalProxy / LocalEngineWorker 可以直接传递本地 cancellation token。
- RemoteProxy 不能序列化 Python 进程内 cancellation token。
- RemoteStub 后续应创建 worker-local cancellation token，并把 `cancel(run_id)` 映射为远端取消信号。
- Phase 3 不实现 RemoteProxy / RemoteStub，只要求 Engine tool loop 不依赖本地进程对象语义之外的 `ToolExecutor` protocol。

### 2.3 Engine 禁止事项

Engine 不得：

- import Host / Service / UI。
- import ToolRegistry / ToolRuntime / tools。
- 从 ToolRegistry / ToolRuntime / 工具实现 / 配置文件发现或读取工具 schema。
- 注册工具。
- 执行权限、审计、路径白名单。
- 产生 HostEvent / WorkerEvent。
- 理解 LocalProxy / RemoteProxy / RemoteStub / RPC。

Engine 在 Phase 3 必须消费 `AgentRunRequest.tool_schemas` 这个由 Host / EngineWorker 提供的 schema 快照，并按 §3.2 规则原样传给 Runner；这不属于 schema 发现、注册或治理。

## 3. 需要改动的 Engine 范围

### 3.1 Contracts

Phase 3 必须先完成以下极小 contract 扩展，否则 `tool_call_requested` / `tool_result_accepted` 无法完整表达 Engine 语义真源：

- `ToolCallRequestedData.provider_state: ToolCallProviderState | None`
  - 理由：provider_state 会进入下一轮 assistant tool_calls，是 Engine tool roundtrip 显式事实，不能塞进 metadata。
- `ToolResultAcceptedData.index_in_iteration: int`
  - 理由：结果接受事件应独立表达排序事实，observer 不应回查前序事件。
- `FinalAnswerData.degraded: bool`
  - 当前代码无等价字段；Phase 3 必须补齐。
  - force-answer 产出 `final_answer(degraded=True)`。
  - content_filter 产出 `final_answer(filtered=True, degraded=True)`；这是 OLD 已验证可靠语义，不应把 degraded 只绑定到 force-answer。
  - 普通 stop / 正常 final answer 产出 `final_answer(degraded=False)`。
  - 若代码中存在 `EngineRunOutcomeFinalAnswer` 或等价 run 聚合结果，也必须同步增加 `degraded` 字段，避免事件和聚合结果语义漂移。
  - 理由：降级回答仍是 `final_answer` terminal，但必须与普通 final answer 可观察地区分，不能塞进 metadata。
- `AgentFallbackMode`
  - 当前代码无等价 enum；Phase 3 必须新增封闭枚举，例如 `FORCE_ANSWER` 与 `RAISE_ERROR`。
  - 理由：OLD 使用 `"force_answer"` / `"raise_error"` 字符串，NEW 不得迁移魔法字符串。
- `AgentPolicy.fallback_mode: AgentFallbackMode`
  - 当前代码无等价字段；Phase 3 必须补齐。
  - 默认语义为 `AgentFallbackMode.FORCE_ANSWER`。
  - 理由：最大工具调用轮次耗尽后的收口策略必须由 Engine policy 显式表达。
- `AgentPolicy.fallback_prompt: str`
  - 当前代码无等价字段；Phase 3 必须补齐。
  - 理由：force-answer 追加给模型的收尾提示是 Agent loop 显式输入，不能进入 metadata / extra payload，也不能硬编码在 loop 内部。
- `AgentPolicy.max_consecutive_failed_tool_batches: int`
  - 当前代码无等价字段；Phase 3 必须补齐。
  - 默认值参考 OLD 为 2。
  - 理由：连续失败工具批次保护是 Agent loop 的可靠性保险，属于 Phase 3 blocker，不是 Host ToolRegistry / ToolRuntime 治理，也不能后移到 Phase 5。

这些字段不是可选优化，也不是 metadata 载荷。实现前若发现无法扩展，应触发 §13 停止条件。

不新增：

- 不新增 HostEvent / WorkerEvent。
- 不新增 RPC / proxy / stub 契约到 Engine。
- 不把 ToolRegistry / ToolRuntime 类型放入 `dayu.engine.contracts`。
- 不把显式字段放入 metadata。

### 3.2 Agent loop

Phase 3 将 Phase 2 单轮无工具 `_run_once()` 扩展为多 iteration tool loop：

1. run 内复制 `request.messages` 为可追加消息序列。
2. 每轮生成 `iteration_id = f"{run_id}_iteration_{iteration_index + 1}"`。
3. 每轮开始前检查 cancellation。
4. 产出 `iteration_started`。
5. 调 `runner.call(messages, runner_options, effective_tools)`。
6. 消费 RunnerEvent。
7. 普通 content + done -> `final_answer` / `run_failed` / `run_cancelled`。
8. tool calls + done(TOOL_CALLS) -> 执行工具、注入消息、进入下一轮。
9. 普通工具预算耗尽后按 `agent_policy.fallback_mode` 进入 force-answer 或 raise-error 收口。

`effective_tools` 规则：

- `request.disable_tools=True` -> 空元组。
- `request.agent_policy.allow_tool_calls=False` -> 空元组。
- `runner.is_supports_tool_calling() is False` -> 空元组。
- 其它情况 -> `request.tool_schemas` 原样传给 Runner。

若工具被禁用或 Runner 不支持工具调用但仍收到 tool call，Agent 必须 fail closed，不调用 ToolExecutor。

`max_iterations` 规则：

- `agent_policy.max_iterations` 表示允许携带工具 schema 的普通 Runner 轮次预算。
- 当前允许的最后一轮 Runner 如果请求 tool call，该批 tool call 必须照常执行。
- completed / failed outcome 仍按普通路径注入 assistant tool_calls + tool messages。
- 工具结果注入后，如果已无下一轮普通工具预算，不再允许模型继续调用工具。
- 默认 `fallback_mode=FORCE_ANSWER`：追加 `fallback_prompt` 作为 `UserMessage`，复刻 OLD `_run_force_answer()` 的消息形态；以 `tools=()` 再调用 Runner，生成 `final_answer(degraded=True)`。
- `fallback_mode=RAISE_ERROR`：不再调用 Runner，收口 `run_failed("max_iterations_exceeded")`。
- force-answer Runner 未产生内容：收口 `run_failed("force_answer_empty")`。
- force-answer 前、Runner 流中、final 前均必须检查 cancellation；取消命中时产出唯一 `run_cancelled`。

force-answer 是 Engine Agent loop 的降级收尾机制，不是 Host 行为；Phase 3 只迁移 OLD 已证明可靠的最大轮次 force-answer 语义，不实现 Phase 5 的 context budget / continuation / broader fallback，不引入 conversation memory。

### 3.3 ToolExecutionRequest

Agent 从 `RunnerToolCallsCompletedData.tool_calls` 得到 `ToolCallRequest`，按 `index_in_iteration` 排序后构造：

- `call = tool_call`
- `context.session_id = request.session_id`
- `context.run_id = request.run_id`
- `context.iteration_id = current_iteration_id`
- `context.tool_call_id = tool_call.tool_call_id`
- `context.index_in_iteration = tool_call.index_in_iteration`
- `context.timeout_seconds = None`
- `context.cancellation_token = request.cancellation_token`
- `context.correlation_id = f"{run_id}:{iteration_id}:{tool_call_id}"`

`timeout_seconds=None` 表示工具级 timeout 由 EngineWorker 所在执行环境中的 Host ToolRuntime / ToolExecutor 策略决定，Engine Phase 3 不发明工具 timeout 策略。

### 3.4 Tool outcome

Phase 3 只处理：

- `ToolCompletedOutcome`
- `ToolFailedOutcome`

`ToolAwaitingOutcome` 进入明确拒绝路径，见 §7。

ToolExecutor 普通异常规则：

- `asyncio.CancelledError` 原样透传外层 task cancel。
- 如果 cancellation token 已取消，收口 `run_cancelled`。
- 普通 `Exception` 转换为 failed tool result，注入 LLM 上下文；错误码固定为 `tool_executor_exception`，message 使用异常类型名，避免泄漏堆栈和敏感信息。

对照 OLD：OLD `_run_tool_call` 会把工具执行异常封成工具失败结果，继续回填给 LLM。NEW 保留这个可靠语义，但不迁 OLD `build_error` / ToolRegistry。

### 3.5 Message injection

全部 completed / failed 工具结果处理完成后，Agent 追加：

- 一个 `AssistantMessage`
  - `role=ASSISTANT`
  - `content` 为本轮模型在请求工具前产生的内容；空内容用 `None`。
  - `reasoning_content` 保留本轮 reasoning；无则 `None`。这是 Phase 3 复刻 OLD 已验证可行行为的过渡实现。
  - `tool_calls=tuple(AssistantToolCall(...))`
- N 个 `ToolMessage`
  - `role=TOOL`
  - `tool_call_id` 与 assistant tool call id 一一对应。
  - `content` 为工具结果经 Engine 内部专用 LLM-facing projection helper 投影后的 JSON 字符串。

工具结果投影：

- 内部仍使用 NEW 强类型 `ToolCompletedOutcome` / `ToolFailedOutcome` / `ToolResultEnvelope`，这些是 Engine 内部事实真源。
- 注入 `ToolMessage.content` 前必须调用 Engine 内部专用 projection helper；该 helper 以 OLD `project_for_llm()` 为强参考源，但使用 NEW 严格类型签名。
- completed 且 value 是 JSON object / dict：展开 value 到顶层，不包 `ok/value`。
- completed 且 value 不是 object：投影为 `{"content": value}` 或等价 LLM-friendly 结构。
- failed：投影为 `{"error": "...", "message": "..."}`；`hint` 仅在非 None 时写入，不带 `ok=false`。
- 空工具结果必须注入非空占位，保证 assistant.tool_calls 与 tool messages 配对完整；禁止因为 value 为空字符串、空 bytes 或 None 而跳过 tool message。
- `truncation` 只投影 LLM 可执行字段，例如 `next_action` / `fetch_more_args`；不得把内部治理对象、debug 字段、Host policy 或 ToolRuntime 状态原样塞给 LLM。
- `tool_calls_remaining` 在 Phase 3 不作为 blocking 字段纳入 projection。理由：NEW Phase 3 的轮次预算已由 Agent loop 强约束，且本阶段不迁 context budget / continuation；若实现 Agent 认为需要暴露该提示，必须从 `agent_policy.max_iterations - completed_tool_iterations` 派生，补充 object / scalar / failed 三类投影测试，并经总控确认后再加入，不能从内部 envelope 或 metadata 读取。
- 明确禁止把内部 envelope 直接作为 LLM-facing tool message content。
- 不把 tool name / index / provider_state 重复塞入 `ToolMessage.content`；这些事实由 assistant tool_calls 和 EngineEvent data 表达。
- Phase 3 可以无条件保留 assistant message 上的 `reasoning_content`，但不得把它并入 `provider_state`；后置 patch 再把无脑写回改为 provider-specific 非无脑写回。

Phase 3 不做 Agent 级 context budget 截断；工具级截断若已在 outcome 中，由 Agent 只做投影。

## 4. Tool calling 状态机

### 4.1 iteration 1：模型请求工具

Runner 可能产出：

- `runner_reasoning_delta`
- `runner_content_delta`
- `runner_tool_calls_completed`
- `runner_usage_recorded`
- `runner_done(TOOL_CALLS)`

Agent 行为：

- Runner tool call delta 仍只属于 RunnerEvent，不提升为 EngineEvent。
- `RunnerToolCallsCompletedData` 暂存当前 iteration 的完整 tool calls。
- 等 `RunnerDoneData(TOOL_CALLS)` 到达后进入工具执行阶段。
- 如果 tool calls completed 后没有 runner_done，按异常 stop 处理，不执行工具。
- 如果 `runner_done(TOOL_CALLS)` 到达但没有完整 `RunnerToolCallsCompletedData`，或 tool call 列表为空，收口 `run_failed("runner_tool_calls_missing")`，不执行工具。
- 如果已暂存 tool calls 但最终 `runner_done` 不是 `TOOL_CALLS`，收口 `run_failed("runner_tool_calls_finish_reason_mismatch")`，不执行工具。
- 如果 Runner 在已暂存 tool calls 后又产出 `provider_protocol_error` / `runner_http_error`，以 Runner error 收口 `run_failed`，不执行工具。

### 4.2 tool_call_requested

对每个排序后的 tool call，Agent 在执行前产出 `tool_call_requested`：

- `iteration_id`
- `tool_call_id`
- `name`
- `arguments`
- `index_in_iteration`
- `provider_state`

该事件只是观测事实，不触发执行。工具执行只能由 Agent 状态机继续调用 `request.tool_executor.execute(request)` 完成，不允许 Host observer 根据该事件另起第二套执行路径。

### 4.3 执行策略

Phase 3 选择串行执行多个 tool call：

- 按 `index_in_iteration` 升序执行。
- 每个 tool call 产出一个 `tool_call_requested`。
- 每个 completed / failed outcome 产出一个 `tool_result_accepted`。
- 所有结果收齐后一次性注入 assistant + tool messages。

理由：

- 最小化 Engine / ToolExecutor 协作复杂度。
- 保证 sequence、message injection、取消边界稳定。
- 避免把 OLD Runner 并发执行职责迁回 Runner。

并发执行、限流、队列化、后台任务收口属于 Host ToolRuntime / EngineWorker 执行环境策略，不在 Phase 3 实现。

### 4.4 completed outcome

`ToolCompletedOutcome` 处理：

1. 接受 outcome。
2. 再次检查 cancellation。
3. 产出 `tool_result_accepted`。
4. 生成 completed tool message。

completed outcome 不是 final answer；必须进入下一轮 Runner。

### 4.5 failed outcome

`ToolFailedOutcome` 处理：

1. 接受 outcome。
2. 再次检查 cancellation。
3. 产出 `tool_result_accepted`。
4. 生成 failed tool message。

failed outcome 不得伪装成：

- `run_cancelled`
- `final_answer`
- Engine 自身 `run_failed`

只有 Engine 协议错误、max iteration `RAISE_ERROR`、连续失败工具批次 `RAISE_ERROR`、force-answer 空内容、awaiting 拒绝、重复 tool_call_id 等状态机问题才可 `run_failed`。

### 4.6 iteration 2：消费工具结果

下一轮 Runner 输入包含：

- 原始 request messages。
- assistant tool_calls。
- tool messages。

如果 Runner 返回普通 content / done，Agent 产出最终 terminal。

如果 Runner 再次请求工具：

- 工具结果注入后仍有下一轮普通工具预算：重复 tool loop。
- 当前轮仍在普通工具预算内：按 §4.1-§4.5 执行工具并注入结果。
- 工具结果注入后已无下一轮普通工具预算：进入 §4.7 force-answer / raise-error 收口。

### 4.7 max iteration force-answer 收口

当最后一轮普通 Runner 请求 tool call 时，Agent 必须先完成这一轮的工具执行与结果注入，然后再判断已无下一轮普通工具预算。此时分支如下：

- `AgentFallbackMode.FORCE_ANSWER`
  - force-answer 前检查 cancellation。
  - 追加 `agent_policy.fallback_prompt` 作为 `UserMessage` 显式收尾消息，复刻 OLD `_run_force_answer()` 行为。
  - 调用 Runner 时传 `tools=()`，临时禁用工具。
  - 不调用 ToolExecutor。
  - force-answer Runner 流中继续观察 cancellation。
  - Runner 产出内容后，在 final 前再次检查 cancellation。
  - 产出 `final_answer(degraded=True)`。
- `AgentFallbackMode.RAISE_ERROR`
  - 不调用 Runner。
  - 不调用 ToolExecutor。
  - 收口 `run_failed("max_iterations_exceeded")`。
- force-answer Runner 没有产生内容
  - 收口 `run_failed("force_answer_empty")`。

如果 force-answer Runner 在 `tools=()` 下仍产出 tool call，这是 Runner / provider 协议异常：Agent 必须 fail closed，不调用 ToolExecutor，不伪装成 final answer。

### 4.8 连续失败工具批次保护

连续失败工具批次保护是 Phase 3 blocking 能力，不能后移：

- `AgentPolicy.max_consecutive_failed_tool_batches` 默认参考 OLD：2。
- 每一轮工具批次如果全部为 failed outcome，则连续失败批次数 +1。
- 任一 completed / success outcome 出现，则连续失败批次数清零。
- 无工具调用的普通文本 final answer 不计入失败批次；Runner 协议异常按协议错误直接收口，不伪装成普通文本轮次来清零。
- 达到阈值后按 `agent_policy.fallback_mode` 收口：
  - `FORCE_ANSWER`：追加 `fallback_prompt` 作为 `UserMessage`，调用 Runner 时 `tools=()`，不调用 ToolExecutor，生成 `final_answer(degraded=True)`。
  - `RAISE_ERROR`：收口 `run_failed("consecutive_failed_tool_batches")` 或等价明确错误码。
- force-answer 前、Runner 流中、final 前均必须遵守 cancellation 优先级；取消命中时产出唯一 `run_cancelled`。
- 这是 Agent loop 保险，不是 Host ToolRegistry / ToolRuntime 治理；不得要求 ToolExecutor 暴露失败计数、重试策略或 Registry 能力。

### 4.9 duplicate guard

Phase 3 只做协议级 duplicate guard：

- run 内维护已执行 `tool_call_id` 集合。
- 同一 run 内同一 `tool_call_id` 再次出现，`run_failed("duplicate_tool_call_id")`。
- 不二次调用 ToolExecutor。
- 只有已通过协议校验且已经进入 execute 或已接受 outcome 的 `tool_call_id` 才加入集合；协议异常未执行的 tool_call_id 不污染后续判断。

不迁 OLD 语义级 duplicate guard：

- 不调用 `get_dup_call_spec`。
- 不注入 duplicate hint。
- 不基于“无信息增量”提前停止。

原因：NEW `ToolExecutor` protocol 只有 `execute(request)`；语义级重复治理若需要，应由后续 Host policy 或新契约评审进入。

## 5. 事件设计

Phase 3 使用当前 EngineEvent 类型：

- `iteration_started`
- `runner_content_delta`
- `runner_reasoning_delta`
- `runner_content_completed`
- `runner_usage_recorded`
- `runner_done`
- `provider_protocol_error`
- `tool_call_requested`
- `tool_result_accepted`
- `final_answer`
- `run_failed`
- `run_cancelled`

`final_answer` 的 `FinalAnswerData.degraded` 是强类型终态事实：

- 普通最终回答：`degraded=False`。
- force-answer 降级最终回答：`degraded=True`。
- content_filter 最终回答：`filtered=True, degraded=True`，即使不是 force-answer 也必须标记 degraded。
- 若 `EngineRunOutcomeFinalAnswer` 或类似聚合结果存在，也必须同步携带 `degraded`，不得只在事件层表达。
- 不允许用 metadata、warning 文本或 finish_reason 反推 degraded。

不新增：

- HostEvent
- WorkerEvent
- RPC lifecycle event
- remote heartbeat / disconnect event

HostEvent / WorkerEvent 后续由 Proxy 层包装 EngineEvent，不由 Engine 或 EngineWorker 第一版产生。

metadata 规则：

- `EngineEvent.metadata` 不承载显式契约事实。
- tool name、arguments、tool_call_id、index、provider_state、outcome、ToolExecutionRequest context 都必须在强类型 data 或 request 中表达。
- 每个 Phase 3 路径仍必须遵守 EngineEvent 全局关联字段：`event_id` 唯一、`sequence` 同一 run 内单调递增、`session_id` / `run_id` 与 request 一致。
- 每个 run 只能产出一个 terminal event，`final_answer` / `run_failed` / `run_cancelled` 在 Phase 3 路径中互斥。

## 6. 取消边界

取消真源在 Host。Engine 只观察 `CancellationToken`。

执行前取消：

- 不调用 ToolExecutor。
- 关闭 Runner。
- 产出唯一 `run_cancelled`。

执行中取消：

- Agent 使用 `dayu.runtime.cancellation.await_or_cancel` 竞速 ToolExecutor awaitable 与 token。
- `WaitCancelled` -> `run_cancelled`。
- `WaitCompleted` 后仍要再次检查 token。
- 外层 `asyncio.CancelledError` 原样透传。

执行后、下一轮 Runner 前取消：

- 不注入下一轮 Runner。
- 产出 `run_cancelled`。

force-answer 取消：

- force-answer 前检查 cancellation。
- force-answer Runner 流中继续观察 cancellation。
- 产出 degraded final answer 前再次检查 cancellation。
- cancellation 命中时必须产出唯一 `run_cancelled`，不能产出 `final_answer(degraded=True)`。

远程化注意：

- LocalProxy / LocalEngineWorker 可直接传递本地 token。
- RemoteProxy 不能序列化本地 token；RemoteStub 后续会创建 worker-local token，并通过 `cancel(run_id)` 映射远端取消。
- Phase 3 Engine 代码不需要知道这些差异，只依赖 request 中的 `CancellationToken` protocol。

取消优先级：

- 取消优先于 `final_answer`。
- 取消优先于 Engine `run_failed`。
- 工具 failed outcome 不是取消。
- 工具 failed outcome 不能被伪装成 final answer。

## 7. awaiting / suspended 边界

Phase 3 不实现 awaiting。

如果 ToolExecutor 返回 `ToolAwaitingOutcome`：

- 不伪装成 completed。
- 不伪装成 failed。
- 不注入 tool message。
- 不产出 `tool_result_accepted`。
- 不轮询、不 sleep、不创建 Host wait record。
- 收口 `run_failed("tool_awaiting_not_supported_in_phase3")` 或等价明确错误码。

Phase 4 再处理 `tool_awaiting` / `run_suspended`。Phase 3 不提前承诺 Phase 4/5 能力。

## 8. 极小 fake tool 与 smoke 计划

### 8.1 fake tool 护栏

测试和 smoke 使用极小 fake tool：

```text
add_numbers(a: number, b: number) -> number
```

要求：

- 只放在测试 helper 或 `utils/` smoke/demo。
- 不放进 `dayu.engine` 生产代码。
- 不引入真实 ToolRegistry。
- schema 在测试或 smoke 中手写。
- executor 命名建议 `RecordingToolExecutor` / `FakeToolExecutor`。
- fake executor 代表 EngineWorker 替 Host 代持并提供的 ToolExecutor 测试替身，不代表生产 Host 实现。

能力：

- 记录调用次数。
- 记录每次 `ToolExecutionRequest`。
- completed 返回 `a + b`。
- failed 返回明确 `ToolFailedOutcome`。
- 可阻塞以测试执行中取消。

### 8.2 Phase 3 smoke 脚本

新增人工 smoke 脚本建议：

- `utils/smoke_async_agent_tool_call.py`

风格参考：

- `utils/smoke_async_agent_providers.py`

定位：

- 只用于人工验证。
- 不进入 `dayu/` 生产包。
- 不纳入真实联网 pytest。
- 使用真实 provider + fake `add_numbers`。

建议 prompt：

```text
请调用工具 add_numbers 计算 2+3，然后用一句话回答结果。
```

验证目标：

- DEBUG 级日志可打开：`dayu.runtime.log.configure(level=LogLevel.DEBUG)`。
- Runner 收到 tool schema。
- 模型产生 tool call。
- Agent 产出 `tool_call_requested`。
- fake ToolExecutor 只执行一次。
- Agent 产出 `tool_result_accepted`。
- 工具结果注入下一轮 Runner。
- assistant tool_calls 数量与 tool messages 数量一致，`tool_call_id` 一一对应。
- Runner 产出 final answer。

安全约束：

- API key 只从环境变量读取。
- 缺 key 友好跳过。
- 不输出 key、headers、完整 payload、完整 prompt、财报内容。
- 输出只包含 case、事件类型、sequence、tool name、content_len、final 摘要。

smoke 脚本测试只覆盖：

- 参数解析。
- 缺 key skip。
- 安全输出。
- fake tool completed / failed 行为。
- 不真实联网。

## 9. 测试计划

建议新增：

- `tests/engine/test_agent_phase3_tool_call.py`
- `tests/engine/test_smoke_async_agent_tool_call.py`

按需更新：

- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_metadata_boundary.py`
- `tests/engine/test_import_boundary.py`
- `tests/engine/runners/openai/test_no_tool_executor_dep.py`
- `tests/README.md`，仅当测试分层或运行方式实际变化时。

必须覆盖：

- `ToolCallRequestedData.provider_state` 与 `ToolResultAcceptedData.index_in_iteration` contract 字段存在、类型正确，且显式事实不进入 metadata。
- `FinalAnswerData.degraded` contract 字段存在、类型正确，且普通 final answer / force-answer final answer 均显式赋值。
- `FinalAnswerData.degraded` 也同步进入 `EngineRunOutcomeFinalAnswer` 或类似聚合结果；content_filter 路径断言 `filtered=True, degraded=True`。
- `AgentFallbackMode` 是封闭 enum，`AgentPolicy.fallback_mode` / `AgentPolicy.fallback_prompt` 是显式字段，不使用魔法字符串或 metadata / extra payload。
- `AgentPolicy.max_consecutive_failed_tool_batches` 是显式字段，默认值参考 OLD 为 2。
- `AgentRunRequest.tool_schemas` 进入 Runner。
- 禁用工具 / policy 禁止工具 / Runner 不支持工具时传空 schema。
- Runner tool call -> `ToolExecutionRequest`。
- `ToolExecutionRequest` 字段完整：`session_id`、`run_id`、`iteration_id`、`tool_call_id`、`index_in_iteration`、tool name、arguments、`cancellation_token`、`correlation_id`。
- 所有 Phase 3 成功、失败、取消、awaiting 拒绝、duplicate、max iteration、Runner 协议异常路径均断言 `EngineEvent.event_id` 唯一、`sequence` 单调、`session_id/run_id` 与 request 一致。
- 所有 tool event 断言 `iteration_id/tool_call_id/index_in_iteration/provider_state` 与 Runner tool call、ToolExecutionRequest、`tool_result_accepted` 对齐。
- 所有 Phase 3 路径均断言 terminal event 唯一，且 `final_answer` / `run_failed` / `run_cancelled` 互斥。
- `tool_call_requested` 只是事件，不触发第二套执行。
- ToolExecutor 只调用一次。
- completed outcome -> `tool_result_accepted` -> tool message -> 下一轮 final answer。
- LLM-facing projection：completed object / dict 展开 value，不带 `ok/value`。
- LLM-facing projection：completed scalar / string 包 `content` 或等价 LLM-friendly 结构。
- LLM-facing projection：failed 不带 `ok`，只含 `error/message` 与非 None 的 `hint`。
- LLM-facing projection：`hint=None` 时省略 `hint` 字段。
- LLM-facing projection：空工具结果仍注入非空占位 tool message，保持 assistant.tool_calls 与 tool messages 配对完整。
- LLM-facing projection：`truncation` 只保留 LLM 可执行字段，不泄漏内部治理对象。
- failed outcome -> `tool_result_accepted` -> failed tool message -> 下一轮 final answer 或模型解释。
- failed outcome 中 `hint=None` 的 LLM-facing message 省略 `hint` 字段。
- 工具失败不能伪装成 cancellation。
- 工具失败不能伪装成 final answer。
- ToolExecutor 普通异常 -> `tool_executor_exception` failed tool message。
- `ToolAwaitingOutcome` 在 Phase 3 明确拒绝。
- `runner_done(TOOL_CALLS)` 缺少完整 tool calls、tool call 列表为空、tool calls completed 后 done 非 `TOOL_CALLS`、Runner error 后仍有暂存 tool calls 等协议异常，均 `run_failed` 且不调用 ToolExecutor。
- cancellation before tool execution。
- cancellation during tool execution。
- cancellation after tool result before next Runner call。
- max iteration 默认 `AgentFallbackMode.FORCE_ANSWER`。
- 最后一轮允许的 tool call 照常执行，并完成 tool result injection。
- fallback prompt 追加为 `UserMessage`，不是 system / assistant / metadata。
- force-answer Runner 调用 `tools=()`。
- force-answer 不调用 ToolExecutor。
- force-answer 产出 `final_answer(degraded=True)`。
- 普通 final answer 产出 `final_answer(degraded=False)`。
- `fallback_mode=RAISE_ERROR` 才产出 `run_failed("max_iterations_exceeded")`。
- force-answer Runner 空内容 -> `run_failed("force_answer_empty")`。
- force-answer Runner 在 `tools=()` 下仍产出 tool call -> `run_failed` 且不调用 ToolExecutor。
- force-answer 前 / Runner 流中 / final 前 cancellation 均优先产出 `run_cancelled`。
- content_filter -> `final_answer(filtered=True, degraded=True)`，且不触发 continuation。
- 连续失败工具批次达到阈值后 `FORCE_ANSWER`：追加 `UserMessage` fallback prompt、Runner 调用 `tools=()`、不调用 ToolExecutor、产出 `final_answer(degraded=True)`。
- 连续失败工具批次达到阈值后 `RAISE_ERROR`：产出 `run_failed("consecutive_failed_tool_batches")` 或等价明确错误码。
- 连续失败计数在出现任一 completed / success outcome 的工具批次后清零。
- 连续失败 force-answer 前 / Runner 流中 / final 前 cancellation 均优先产出 `run_cancelled`。
- multiple tool calls 串行顺序和 message 注入顺序。
- duplicate `tool_call_id` guard。
- duplicate guard 只记录已进入执行或已接受结果的 `tool_call_id`，协议异常未执行的 call 不污染集合。
- Runner close 在 success / failure / cancellation 中执行。
- Engine 不 import Host / ToolRegistry / ToolRuntime / tools。
- Runner 仍不依赖 ToolExecutor。
- fake `add_numbers` 护栏。

## 10. Pyright 要求

- Agent tool loop 状态完整类型化。
- `AgentFallbackMode` 分支必须穷尽。
- 不使用 `Any`、`object`、裸 dict 作为公共或内部状态袋。
- `ToolExecutionOutcome` 分支必须穷尽。
- `ToolResultEnvelope` 投影 helper 必须接受封闭联合。
- smoke 脚本若纳入 pyright，也必须类型完整。
- 不新增、扩散、掩盖类型错误。

## 11. README 约束

默认不要新建或修改 README，除 `tests/README.md` 外。

若实现 Phase 3 后确实触发 `dayu/engine/README.md` 更新，必须遵守：

- 只写当前已实现能力。
- 可写普通 completed / failed tool calling 闭环。
- 可写 ToolExecutor 由 EngineWorker 替 Host 代持并通过 request 提供。
- 可写 Engine 不持有 ToolRegistry。
- 可写 `tool_call_requested` 只是观测事件。
- 可写最大工具轮次耗尽后的 force-answer 降级回答已通过 `final_answer(degraded=True)` 表达。
- 不写未来 RemoteProxy / RemoteStub / RPC 生产实现。
- 不写 awaiting / run_suspended 已可用。
- 不写 Phase 5 context budget / continuation / broader fallback 已可用。
- 不写 Host ToolRegistry、ToolRuntime、权限、审计、路径白名单实现细节。
- 不写 trace store、transcript、conversation memory、context budget / continuation 已可用。

## 12. Review gate

Phase 3 实现完成后必须经过两道 review。

第一道：常规日常 review。

- 按 `/Users/leo/workspace/dayu-agent-r/docs/code_review.md` 执行。
- 检查代码、测试、README/docs 是否只描述当前事实。
- 检查架构、类型、事件、取消、ToolExecutor 边界。

第二道：NEW / OLD Agent tool calling 严格对照 review。

- OLD `AsyncAgent` / Runner 普通工具调用状态机可靠性很高，是强参考源。
- 必须对照 OLD 的模型请求工具、工具结果回填、assistant tool_calls、tool messages、iteration 推进、final answer 收口、取消优先级、Runner close。
- 必须对照 OLD `project_for_llm()`：NEW 内部信封不能直接进入 LLM-facing tool message。
- 必须对照 OLD 的 max_iterations -> force_answer 语义：默认 force answer、临时禁用工具、degraded final answer、`raise_error` 才 fail、空内容 `force_answer_empty`。
- 必须对照 OLD 的 content_filter 语义：`filtered=True, degraded=True`。
- 必须对照 OLD 的连续失败工具批次保护：默认阈值 2，成功批次清零，达到阈值后按 fallback mode 收口。
- 必须确认 NEW 没有把 OLD Runner 执行工具职责迁回 Runner。
- 必须确认 NEW 使用 EngineWorker 替 Host 代持并提供的 ToolExecutor protocol。
- 必须确认工具失败进入 LLM 上下文，而不是直接 `run_failed`。
- 必须确认 NEW 没有机械搬迁 OLD `_run_loop` God function，也没有引入 Phase 5 context budget / continuation / broader fallback。

两道 review 均通过后，Phase 3 才能进入提交 / PR。

## 13. 停止条件

遇到以下任一情况，停止实现并回到设计讨论：

- 当前 contracts 无法表达 `ToolExecutionRequest` / outcome / `tool_result_accepted`。
- 当前 contracts 无法表达 `FinalAnswerData.degraded`、`AgentFallbackMode`、`AgentPolicy.fallback_mode` 或 `AgentPolicy.fallback_prompt`。
- 当前 contracts 无法表达 `AgentPolicy.max_consecutive_failed_tool_batches`。
- 无法把内部 `ToolResultEnvelope` 与 LLM-facing projection helper 分离，或必须把内部 envelope 直接注入 `ToolMessage.content`。
- 必须实现 Host ToolRegistry / ToolRuntime 才能完成。
- 必须执行真实工具注册、权限、审计或路径白名单。
- 必须实现 EngineWorker / LocalProxy / RemoteProxy / RemoteStub / RPC 生产代码。
- 需要把 HostEvent / WorkerEvent 设计进 Engine。
- awaiting 无法明确拒绝或延后。
- 工具失败只能通过 `run_failed` 表达，无法进入 LLM 上下文。
- 需要让 Runner import ToolExecutor。
- 需要恢复 OLD `set_tools` 或 `get_dup_call_spec`。
- 需要把 force-answer 做成 Host 行为。
- 需要引入 Phase 5 context budget / continuation / broader fallback 或 conversation memory。
- 需要处理 Issue #10 的 provider-specific reasoning patch 才能完成 Phase 3。
- 需要把显式契约事实塞入 metadata。
- 需要修改除 `tests/README.md` 和必要 `dayu/engine/README.md` 外的 README。
- smoke 自动测试需要真实 API key。

## 14. 总控 / 用户需确认问题

这些问题需要总控或用户确认，但不阻塞已经明确的 EngineWorker 边界：

- `dayu/engine/README.md` 是否在 Phase 3 实现 PR 中更新，还是只更新测试 README / PR 说明。
- Runner tool call 协议异常的错误码命名是否接受本文建议，或由实现 PR 统一收敛为项目既有错误码枚举。
- `AgentPolicy.fallback_prompt` 的默认文案由配置层传入，还是在 Engine contract 默认值中给出稳定中性文案。

## 15. 验证命令

Phase 3 实现完成后至少运行：

```bash
source .venv/bin/activate && pytest tests/runtime tests/contracts tests/engine -q
source .venv/bin/activate && pyright
```

本次仅更新计划文档，不运行测试和 pyright。
