# Phase 2 Agent Run Loop 骨架实施计划

本文档是 Phase 2 的实施计划真源。当前任务只产出计划，不修改生产代码，不提交 commit，不 push，不创建 PR。

## 0. 动机判断

Phase 2 动机成立。

直接证据：

- Phase 0 已有 `AgentRunRequest`、`AgentRunResult`、`EngineEvent`、`RunnerEvent`、`AsyncRunner` 等强类型契约，但 `dayu.engine` 包根仍明确禁止导出 `run_agent_messages` / `run_agent_and_wait`。
- Phase 1 已有 OpenAI-compatible Runner，Runner 只产出 `RunnerEvent`，不会产出 `EngineEvent`，也不会生成 `final_answer` / `run_failed` / `run_cancelled`。
- Phase 1.5 已有 `dayu.runtime.log` 与 `dayu.runtime.cancellation`，Runner cancellation 命中时自然终止且不补 `RunnerDoneData`，需要 Agent 层把 Host 取消事实收口为 `run_cancelled`。
- OLD `AsyncAgent.run_messages` 已证明状态机可靠：申请运行槽位、逐轮 iteration、消费 Runner 事件、最终回答前再次检查取消、`finally` 关闭 Runner 与释放槽位。

范围判断：

- Phase 2 只做无工具主链路骨架，目标是 Host 可以依赖函数式入口跑通一次普通模型回答。
- Phase 2 不迁工具执行、trace、transcript、conversation memory、context budget、continuation 和语义压缩。
- `utils/smoke_async_agent_providers.py` 是人工验证脚本，不属于生产链路；该需求成立，因为 Phase 2 引入了 Agent 入口后需要跨 provider 验证 RunnerEvent 提升与 Runner close。

## 1. 阅读范围

### 1.1 NEW 已阅读文件

- `AGENTS.md`
- `CLAUDE.md`
- `docs/engine/design.md`
- `docs/engine/migration-plan.md`
- `docs/engine/phase1_5-plan.md`
- `docs/engine/phase1_5-code-review.md`
- `docs/code_review.md`
- `tests/README.md`
- `dayu/contracts/__init__.py`
- `dayu/contracts/cancellation.py`
- `dayu/contracts/json_value.py`
- `dayu/contracts/tool_await.py`
- `dayu/contracts/tool_call.py`
- `dayu/contracts/tool_executor.py`
- `dayu/contracts/tool_outcome.py`
- `dayu/contracts/tool_result.py`
- `dayu/contracts/tool_schema.py`
- `dayu/engine/__init__.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/contracts/agent_policy.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/finish_reason.py`
- `dayu/engine/contracts/messages.py`
- `dayu/engine/contracts/runner.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/runners/openai/__init__.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `dayu/engine/runners/openai/payload.py`
- `dayu/engine/runners/openai/error_classifier.py`
- `dayu/engine/runners/openai/retry_policy.py`
- `dayu/engine/runners/openai/http_client.py`
- `dayu/engine/runners/openai/cancellation_helpers.py`
- `dayu/runtime/__init__.py`
- `dayu/runtime/cancellation.py`
- `dayu/runtime/log.py`
- `tests/contracts/*`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_import_boundary.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_runner_event_contract.py`
- `tests/engine/test_weak_typing_guard.py`
- `tests/engine/runners/openai/*`
- `tests/runtime/*`

### 1.2 OLD 已阅读文件

- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/cancellation.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/README.md`
- `/Users/leo/workspace/dayu-agent/dayu/config/llm_models.json`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_agent.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner_call_paths.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner_utils.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_sse_parser.py`

### 1.3 OLD AsyncAgent 具体阅读范围

核心方法：

- `AsyncAgent.__init__`
- `AsyncAgent._acquire_run_slot`
- `AsyncAgent._release_run_slot`
- `AsyncAgent.run`
- `AsyncAgent.run_messages`
- `AsyncAgent._run_loop`
- `AsyncAgent._annotate_event`
- `AsyncAgent._raise_if_cancelled`
- `AsyncAgent._tools_disabled`
- `AsyncAgent._run_force_answer`
- `AsyncAgent.run_and_wait`
- `AsyncAgent._get_registered_tool_schemas`

状态机路径：

- run 入口生成 / 继承 `run_id` 与 `session_id`。
- 申请同一 Agent 实例运行槽位，禁止并发运行。
- 每轮先检查取消，再发 `iteration_start`。
- 调 Runner，消费 `CONTENT_DELTA`、`REASONING_DELTA`、`CONTENT_COMPLETE`、`DONE`、`ERROR`、工具事件。
- 无工具且有 `content_complete` 或 `done` 时收口为 `final_answer`。
- `final_answer` 生成前再次检查取消。
- 遇不可恢复错误直接返回。
- 达到最大迭代次数按 fallback 策略处理。
- `finally` 中关闭 Runner、关闭 trace recorder、释放运行槽位。

取消路径：

- `_raise_if_cancelled()` 在每轮迭代开始处调用。
- `_raise_if_cancelled()` 在 `final_answer_event` 产出前调用。
- `_run_force_answer()` 产出 degraded final 前也调用。
- Runner 中途抛 `CancelledError` 时不再产出 final answer。

Runner close 路径：

- `run_messages()` 的 `finally` 无条件 `await self.runner.close()`。
- trace recorder close 与 run slot release 也在同一个 `finally`。
- OLD 测试覆盖不可恢复错误下 recorder close，Runner close 是同一生命周期语义。

并发保护路径：

- `_active_run_id` + `threading.Lock`。
- 已有 active run 时抛 `RuntimeError("AsyncAgent 不支持并发运行...")`。
- `test_run_raises_when_same_agent_runs_concurrently` 证明该语义可靠。

相关测试事实：

- `test_run_streaming`：content delta / content complete / done 后由 Agent 产出 final answer，并补 run / iteration metadata。
- `test_run_non_streaming`：`run_and_wait` 聚合 final answer，且仍走流式事件路径。
- `test_run_is_stateless`：多次 run 的输入消息彼此独立。
- `test_run_raises_when_same_agent_runs_concurrently`：同一 Agent 实例并发 fail-fast。
- `test_cancelled_before_final_answer_suppresses_final_event`：final answer 前取消优先，不能再产出 final answer。
- `test_runner_cancelled_mid_stream_propagates_and_suppresses_final_answer`：Runner 流式阶段取消不能被伪装成最终回答。
- `test_content_filter_yields_filtered_final_answer_without_continuation`：`content_filter` 不做续写，最终回答带 filtered。
- `test_tool_trace_recorder_close_on_unrecoverable_error`：不可恢复错误也必须走 close/finally。
- `test_fallback_raise_error` / `test_fallback_force_answer`：max iteration 触发错误或降级，但 Phase 2 不迁 force-answer。

### 1.4 OLD 强参考语义与禁止迁移项

强参考语义：

- run-scoped 生命周期：单次 run 结束必须关闭 Runner。
- 同一 Agent 实例不支持并发运行。
- 每轮 iteration 开始前检查取消。
- RunnerEvent / StreamEvent 消费后，Agent 才产生最终回答。
- `done` 只表示单次 Runner 回合结束，`final_answer` 只能由 Agent 产出。
- 取消优先于 final answer。
- 错误路径也必须进入统一收口，不泄漏资源。
- Runner close / cleanup 异常不能覆盖已经确定的业务终态。

禁止迁移项：

- `ToolRegistry`、Runner 层工具执行、`set_tools`。
- `tool_call_dispatched` / `tool_call_result` / `tool_calls_batch_done` 闭环。
- Tool trace recorder、JSONL trace store、raw payload 冷存。
- transcript 持久化、conversation memory、语义压缩。
- context budget、continuation、force-answer fallback。
- `StreamEvent(data: Any, metadata: dict)` 弱类型事件接口。
- `call(**extra_payloads)` 与配置直读式 Runner 构造。

## 2. Phase 2 接口边界

### 2.1 公共函数式入口

Phase 2 在 `dayu.engine` 包根新增真实入口：

```python
def run_agent_messages(request: AgentRunRequest) -> AsyncIterator[EngineEvent]: ...
async def run_agent_and_wait(request: AgentRunRequest) -> AgentRunResult: ...
```

说明：

- `run_agent_messages` 是 Host 订阅事件流的主入口。
- `run_agent_and_wait` 消费同一事件流并返回最后一个 run terminal outcome。
- 两者都只依赖 `AgentRunRequest`、`EngineEvent`、`AgentRunResult` 等 contracts。
- Host 不依赖 `AsyncAgent` 实现类，不依赖 OpenAI Runner 具体类，不依赖 Engine 私有状态。

### 2.2 内部实现形态

建议新增私有 run-scoped Agent 类：

- 文件建议：`dayu/engine/agent.py`
- 类名建议：`_AsyncAgent`
- 构造参数：`request: AgentRunRequest`、`runner: AsyncRunner`
- 公共面保持私有模块内方法：`run_messages() -> AsyncIterator[EngineEvent]`

选择私有类而不是单个大函数的理由：

- OLD `AsyncAgent` 的状态机可靠，但 `_run_loop` 已是 god function；NEW 不应照搬。
- 私有类可集中持有 run 内状态：`sequence`、`terminal_seen`、`content buffer`、`iteration id`、`active run id`。
- 私有类可以复用 OLD 并发 fail-fast 语义，同时不把实现类变成 Host 稳定依赖。
- 后续 Phase 3 tool loop 可以在私有类内拆分方法，不扩大包根 API。

### 2.3 Runner 创建边界

Phase 2 函数式入口内部私有创建当前唯一 Runner 实现：

- `_build_runner(request) -> AsyncRunner`
- 当前只创建 `AsyncOpenAIRunner(spec=request.runner_spec, cancellation_token=request.cancellation_token)`。
- 若后续出现非 OpenAI-compatible Runner，需要先新增明确 contract 或 runner registry 计划；Phase 2 不引入开放插件机制。

有意重设：

- OLD Host /配置层可选择 `AsyncCliRunner` 等实现；NEW Phase 2 只承认当前已落地的 OpenAI-compatible Runner。
- `RunnerSpec.api_key_ref` 本身不读环境变量；脚本或 Host adapter 必须把 key 投影进 `RunnerSpec.headers`。这是当前 NEW Runner 代码事实。

### 2.4 包根导出策略

Phase 2 更新 `dayu.engine.__all__`：

- 新增：`run_agent_messages`、`run_agent_and_wait`。
- 仍不导出：`_AsyncAgent`、`AsyncOpenAIRunner`、`AsyncCliRunner`、`ToolRegistry`、`ToolTraceRecorder`、取消异常。
- `tests/engine/test_package_exports.py` 必须从 Phase 0 白名单迁移到 Phase 2 白名单，删除这两个函数式入口的 forbidden 断言。

### 2.5 Host 依赖表面

Host 只依赖：

- `dayu.engine.run_agent_messages`
- `dayu.engine.run_agent_and_wait`
- `dayu.engine.contracts` / `dayu.contracts` 中的请求、事件、结果、取消、工具 schema / executor contract。

Host 不依赖：

- `dayu.engine.agent._AsyncAgent`
- `dayu.engine.runners.openai.runner.AsyncOpenAIRunner`
- Engine 私有错误码常量。
- Runner close 实现细节。

## 3. Agent 状态机设计

### 3.1 状态字段

私有 `_AsyncAgent` 建议持有：

- `_request: AgentRunRequest`
- `_runner: AsyncRunner`
- `_active_run_id: str | None`
- `_run_guard_lock: threading.Lock`
- `_next_sequence: int`
- `_terminal_seen: bool`
- `_last_content: str | None`
- `_last_reasoning_content: str | None`
- `_last_finish_reason: FinishReason | None`
- `_last_failure: RunFailedData | None`

不得使用 `Any` / `object` / 裸 `dict` 作为状态袋。

### 3.2 run start

流程：

1. `run_agent_messages(request)` 创建 Runner。
2. 创建私有 `_AsyncAgent`。
3. 调 `_AsyncAgent.run_messages()`。
4. `_AsyncAgent` 申请运行槽位，若同实例并发运行则 fail-fast。
5. 检查 `request.cancellation_token.is_cancelled()`；若已取消，直接 yield `run_cancelled` terminal。
6. 进入 `try/finally`，确保 Runner close。

与 OLD 一致：

- 先申请运行槽位，最后释放。
- run 生命周期结束必 close。

NEW 重设：

- Phase 2 函数入口每次创建 run-scoped Agent，Host 不复用 Agent 实例。
- 取消不抛公共 `CancelledError`，而是收口为 `RunCancelledData` / `EngineRunOutcomeCancelled`。

### 3.3 iteration start

Phase 2 只允许无工具主链路，所以最多执行一轮 LLM call。

流程：

1. 生成 `iteration_id = f"{run_id}_iteration_1"`。
2. yield `EngineEventType.ITERATION_STARTED`，data 为 `IterationStartedData(iteration_id, 0, len(messages))`。
3. 若 `agent_policy.max_iterations <= 0`，不调用 Runner，直接 `run_failed(max_iterations_exceeded)`。

说明：

- OLD iteration 从 1 开始展示，但 iteration id 带单调 counter；NEW data 已有 `iteration_index`，建议从 0 起，与 contract docstring 一致。
- Phase 2 不实现多轮工具迭代；`max_iterations > 1` 暂不触发多轮。

### 3.4 Runner call

调用：

```python
runner.call(
    messages=request.messages,
    options=request.runner_options,
    tools=effective_tools,
)
```

`effective_tools` 规则：

- 若 `request.disable_tools` 为 `True`，传空元组。
- 若 `request.agent_policy.allow_tool_calls` 为 `False`，传空元组。
- Phase 2 默认建议传空元组，即使 request 中有 `tool_schemas`，也不进入工具闭环。
- 若实现选择传 `request.tool_schemas` 以探测 provider tool call，则必须在收到 tool call 后 `run_failed`，不得执行工具。

推荐计划：Phase 2 传空元组。理由：

- 用户明确要求无工具主链路。
- 不把工具 schema 暴露给模型，可以减少 Phase 2 意外 tool call。
- 若 provider 仍返回 tool call completed，视为协议异常并 `run_failed`。

### 3.5 RunnerEvent -> EngineEvent 提升

提升规则：

- `RUNNER_CONTENT_DELTA` -> `RUNNER_CONTENT_DELTA` / `ContentDeltaData`
- `RUNNER_REASONING_DELTA` -> `RUNNER_REASONING_DELTA` / `ReasoningDeltaData`
- `RUNNER_CONTENT_COMPLETED` -> `RUNNER_CONTENT_COMPLETED` / `ContentCompleteData`
- `RUNNER_USAGE_RECORDED` -> `RUNNER_USAGE_RECORDED` / `RunnerUsageData`
- `PROVIDER_PROTOCOL_ERROR` -> `PROVIDER_PROTOCOL_ERROR` / `ProviderProtocolErrorData`
- `RUNNER_HTTP_ERROR` 不直接有同名 EngineEvent，Agent 记录为 failure candidate，随后或立即收口 `run_failed`
- `RUNNER_DONE` -> `RUNNER_DONE` / `RunnerDoneEngineData`
- `RUNNER_TOOL_CALL_DELTA` / `RUNNER_TOOL_CALLS_COMPLETED` -> Phase 2 `run_failed(tool_call_not_supported_in_phase2)`

每个 `EngineEvent` 必须补齐：

- `event_id`
- `sequence`
- `occurred_at`
- `session_id`
- `run_id`
- `type`
- `data`
- `metadata=None`

metadata 不承载契约事实。

HTTP error 观测事实说明：

- 当前 Engine contract 没有 `RUNNER_HTTP_ERROR` 对应的 EngineEvent data，`RunFailedData` 也只能承载 `error_code` / `message` / `recoverable`。
- Phase 2 不在本计划内新增公共契约；因此 `RunnerHTTPErrorData.http_status`、`provider_request_id`、`raw_payload`、`attempt`、`retried` 暂不提升为 Host 可见 EngineEvent data。
- 这是当前 contract 限制下的有意收窄，不得把这些事实塞进 `metadata`。
- 如果总控要求 Phase 2 Host 可观察完整 HTTP 细节，必须触发停止条件：先回到 EngineEvent contract 设计，新增或扩展强类型 data 后再实施。

### 3.6 content delta / reasoning delta / usage / runner_done 消费

content delta：

- 立即提升给 Host。
- 追加到内部 content buffer，作为缺少 `RunnerContentCompletedData.content` 时的 fallback。

reasoning delta：

- 立即提升给 Host。
- 可追加到 reasoning buffer，用于 content completed 缺 reasoning_content 时的 fallback。

content completed：

- 立即提升给 Host。
- 记录 `content`、`reasoning_content`、`finish_reason`。
- `content=None` 时不立即失败，等待 `runner_done` 判断。

usage：

- 立即提升给 Host。
- Phase 2 不做 context budget，只做事件提升。

runner_done：

- 立即提升给 Host。
- 若 finish_reason 为 `ERROR`，必须产出 `run_failed`，不得继续进入 final answer。
- 若已有 protocol / HTTP failure candidate，`run_failed` 使用该 candidate。
- 若没有先前 `RunnerHTTPErrorData` / `RunnerProtocolErrorData`，`run_failed` 使用中性错误码 `runner_error_done_without_detail`，`recoverable=False`。
- 若 finish_reason 为 `TOOL_CALLS` 或已见 tool call，产出 `run_failed(tool_call_not_supported_in_phase2)`。
- 若取消 token 已命中，产出 `run_cancelled`，优先于 final answer。
- 否则用 content completed 或 delta buffer 产出 `final_answer`。

### 3.7 final_answer 收口

`final_answer` 生成规则：

- 只由 Agent 生成。
- 必须发生在 `runner_done` 之后，或 Runner 正常结束但未给 done 时的 abnormal stop 收口之后。
- 生成前必须再次检查 cancellation token。
- `content = content_completed.content`，若为 `None` 则用 content delta buffer 拼接，仍为空则允许空字符串 final answer，前提是 finish_reason 不是 ERROR / TOOL_CALLS。
- `filtered = finish_reason is FinishReason.CONTENT_FILTER`。
- `finish_reason` 来自 `RunnerContentCompletedData.finish_reason` 或 `RunnerDoneData.finish_reason`。

与 OLD 一致：

- 最终回答前再检查取消。
- `content_filter` 不续写，保留 partial content 并标记 filtered。

NEW 重设：

- Phase 2 不发 `warning` 表示 content_filter，因为 EngineEvent 当前没有 warning 类型；filtered 是稳定契约事实。
- Phase 2 不做 `length` continuation；`FinishReason.LENGTH` 直接进入 final answer，后续 Phase 5 再补 continuation。

### 3.8 provider error / protocol error / HTTP error -> run_failed

protocol error：

- 先提升 `PROVIDER_PROTOCOL_ERROR`。
- 记录 `RunFailedData(error_code=..., message=..., recoverable=False)`。
- 当收到 `RUNNER_DONE(ERROR)` 时产出 `run_failed`。
- 若 RunnerEvent 流异常结束且已有 protocol error 但无 done，也产出 `run_failed(protocol_error_abnormal_stop)`。

HTTP error：

- 记录 `RunnerHTTPErrorData`。
- 产出 `run_failed(error_code=runner_http_error_code.value, message=data.message, recoverable=False)`。
- 若随后收到 `RUNNER_DONE(ERROR)`，不再重复 terminal。

Runner 抛异常：

- `asyncio.CancelledError` 透传外层 task cancel，不吞。
- 普通异常收口为 `run_failed(error_code="runner_exception", recoverable=False)`。

bare error done：

- 任何 `RunnerDoneData(FinishReason.ERROR)` 都必须收口为 `run_failed`。
- 没有 HTTP / protocol error candidate 时，使用 `RunFailedData(error_code="runner_error_done_without_detail", message="runner finished with error without detail", recoverable=False)` 或等价中性文案。
- 不允许落入 `final_answer`、`missing_terminal` 或无 terminal 分支。

与 OLD 一致：

- Runner 的不可恢复错误不应继续 final answer。
- 错误路径必须走统一收口。

NEW 重设：

- OLD error 是 `error_event` 并由 `run_and_wait` 聚合；NEW 以 `RunFailedData` terminal 为 Host 可见真源。

### 3.9 cancellation before run

若入口发现 `request.cancellation_token.is_cancelled()`：

- 不调用 Runner。
- 仍必须关闭 Runner。因为函数式入口已经创建 Runner，必须关闭。
- 取消 terminal 的 `finished_at` 必须表示 Engine 对该 run 的取消收尾完成时间；Phase 2 按“Runner close 尝试完成后”的时间填充。
- 因此 cancellation-before-run 路径应先记录 `accepted_at`，执行 Runner close 尝试，再 yield 唯一 terminal：`RUN_CANCELLED`。
- `RunCancelledData.requested_at` 使用 token `requested_at()`；若为 `None`，用当前时间作为保守 fallback，并在计划实现时通过私有 helper 明确。
- close 失败只记录 logger warning，不改变 `RUN_CANCELLED` terminal；`finished_at` 取 close 尝试结束后的时间。

### 3.10 cancellation during runner call

Phase 1 Runner 在取消命中时自然终止，不补 `RunnerDoneData`。

Agent 识别规则：

- `async for runner.call(...)` 正常结束后，若未见 `RunnerDoneData` 且 token 已取消，则产出 `run_cancelled`。
- 若已收 content delta / content completed，但 token 已取消，仍产出 `run_cancelled`，不产出 final answer。
- 取消路径在产出 `run_cancelled` 前必须完成 Runner close 尝试，以保证 `RunCancelledData.finished_at` 与 contract “实际收尾完成时间”一致。
- 若 Runner 抛内部取消异常的未来实现出现，Engine 不把公共异常作为 contract；Phase 2 只捕获当前已知私有行为之外的普通异常为失败，`asyncio.CancelledError` 仍透传外层 task cancel。

### 3.11 cancellation before final_answer

在准备 `final_answer` 前调用 `_is_cancelled()`：

- 命中则产出 `run_cancelled`。
- 不产出 final answer。
- 同样先记录 accepted time，完成 Runner close 尝试后再产出 `run_cancelled`。
- 这是 OLD `test_cancelled_before_final_answer_suppresses_final_event` 的直接迁移语义。

### 3.12 max iteration / fallback / abnormal runner termination

max iteration：

- Phase 2 无工具主链路只执行一轮。
- 若 `agent_policy.max_iterations < 1`，直接 `run_failed("max_iterations_exceeded")`。
- 若 Runner 产出 tool call 导致需要下一轮，Phase 2 不进入下一轮，直接 `run_failed("tool_call_not_supported_in_phase2")`。

fallback：

- Phase 2 不迁 OLD `force_answer`。
- `AgentPolicy.continuation_max_attempts` 当前不消费；测试应证明 Phase 2 不因该字段做 continuation。

abnormal runner termination：

- Runner 流结束且无 `RunnerDoneData`：
  - token cancelled -> `run_cancelled`。
  - 已有 HTTP / protocol failure candidate -> `run_failed`。
  - 已有 content completed 或 content delta -> `run_failed("runner_abnormal_stop")`，不把 incomplete content 伪装成 final answer。
  - 完全无输出 -> `run_failed("runner_abnormal_stop")`。

### 3.13 terminal event 唯一性

私有 `_emit_terminal_once(data)` 或等价 helper：

- `_terminal_seen=False` 才能产出 terminal。
- terminal event type 只能是 `FINAL_ANSWER`、`RUN_FAILED`、`RUN_CANCELLED`。
- Phase 2 不产出 `RUN_SUSPENDED`。
- 一旦 terminal_seen=True，后续 RunnerEvent 全部忽略或直接停止消费。

### 3.14 sequence 单调与 event_id 生成

sequence：

- run 内从 0 开始。
- 每 yield 一个 EngineEvent 后递增。
- 包括 terminal event。

event_id：

- 建议格式：`f"{request.run_id}:{sequence}"`。
- 优点是确定、唯一、便于测试。
- 不引入 UUID，避免单元测试不稳定。

### 3.15 Runner close finally 语义

`_AsyncAgent.run_messages()` 必须：

- `try` 中产出事件。
- `finally` 中 `await runner.close()`。
- close 成功 / 失败都释放运行槽位。
- cancellation terminal 是特殊路径：为了让 `RunCancelledData.finished_at` 表达实际取消收尾完成时间，应在 yield `RUN_CANCELLED` 前先执行一次 Runner close 尝试；`finally` 中的 close 必须幂等，不得二次改变 terminal。

close error 处理：

- 若 terminal 尚未产生，close error 可收口为 `run_failed("runner_close_failed")` 的计划需要谨慎，因为 `finally` 中 yield 事件会让生成器语义复杂。
- 推荐实现：close error 只记录 logger warning，不改变已经产生或将要产生的 terminal。若业务主体尚未产生 terminal，主体路径应在进入 finally 前先产出 `run_failed` / `run_cancelled`。
- 需要测试 close 在 success / failure / cancellation 中都执行；close error 是否影响 terminal 的行为也要锁定。

## 4. RunnerEvent 消费边界

Phase 2 只处理无工具主链路。

工具相关事件计划：

- `RUNNER_TOOL_CALL_DELTA`：立即 `run_failed("tool_call_not_supported_in_phase2")`，停止 run。
- `RUNNER_TOOL_CALLS_COMPLETED`：立即 `run_failed("tool_call_not_supported_in_phase2")`，停止 run。
- 不调用 `ToolExecutor`。
- 不产出 `ToolCallRequestedData`。
- 不把 tool call 伪装成 `final_answer`。

OLD 对照：

- OLD Runner 负责工具执行，产出 `tool_call_dispatched`、`tool_call_result`、`tool_calls_batch_done`。
- OLD Agent 收集工具结果，构造 assistant tool_calls 与 tool messages，进入下一轮 Runner call。
- NEW 已有意重设：Runner 不执行工具，ToolExecutor 后续由 Host 注入并在 Phase 3 接入；Phase 2 收到任何 tool call 都是范围外事件，应 fail closed。

协议漂移风险：

- 如果 Phase 2 把 tools 传空但 provider 仍返回 tool call，说明 prompt 或 provider 行为不符合无工具约束。必须 `run_failed`。
- 如果实现者决定传 `tool_schemas` 给 Runner 却不执行工具，会显著增加 tool call 概率，不推荐。

## 5. 取消边界

使用现有 `CancellationToken`。

语义：

- `run_cancelled` 表示 Host 取消请求已被 Engine 接受，并由 Engine 收口为取消终态。
- 取消不是普通 error。
- 取消不得伪装成工具失败、HTTP 失败或最终回答。
- Agent 只观察 token，不创建取消真源。
- `RunCancelledData.accepted_at` 表示 Engine 观察并接受 Host 取消请求的时间。
- `RunCancelledData.finished_at` 表示 Engine 完成取消收尾的时间；Phase 2 以 Runner close 尝试结束后的时间为准。

检查点：

- run start 前。
- iteration start 前。
- RunnerEvent 消费循环每次关键收口后。
- Runner 流自然结束且无 `RunnerDoneData` 时。
- final answer 前。
- failure terminal 前可检查一次取消，保证取消优先于失败。若 provider error 与 Host cancel 同时出现，取消优先。

Runner 因取消自然终止且无 RunnerDoneData：

- Agent 看到 runner stream 结束。
- 若 `token.is_cancelled()` 为 True，则产出 `run_cancelled`。
- 产出 `run_cancelled` 前先 close Runner；close 失败只记日志，不降级为 `run_failed`。
- 不要求 Runner 抛公共取消异常。

NEW 与 OLD 差异：

- OLD 取消通过 `dayu.contracts.cancellation.CancelledError` 抛出，调用方捕获异常。
- NEW contract 已明确取消公共终态用 `RunCancelledData` / `EngineRunOutcomeCancelled`，不暴露公共取消异常。这是有意重设，符合 Phase 0 contract。

## 6. 错误边界

### 6.1 HTTP error

来源：

- `RunnerEventType.RUNNER_HTTP_ERROR` / `RunnerHTTPErrorData`
- 后续通常有 `RunnerDoneData(FinishReason.ERROR)`

映射：

- `RunFailedData.error_code = data.error_code.value`
- `RunFailedData.message = data.message`
- `RunFailedData.recoverable = False`
- `AgentRunResult = EngineRunOutcomeFailed(...)`

观测限制：

- Phase 2 不新增 EngineEvent contract，因此 HTTP status、provider request id、raw payload、attempt、retried 暂不进入 EngineEvent data。
- 这是有意收窄；若该细节必须成为 Host 可观察事实，实施必须停止并先做 contract 变更设计。

### 6.2 protocol error

来源：

- `RunnerEventType.PROVIDER_PROTOCOL_ERROR` / `RunnerProtocolErrorData`
- 后续通常有 `RunnerDoneData(FinishReason.ERROR)`

映射：

- 先提升 `ProviderProtocolErrorData`。
- terminal 映射为 `RunFailedData(error_code=data.error_code, message=data.message, recoverable=False)`。

### 6.3 provider content_filter / length finish reason

`FinishReason.CONTENT_FILTER`：

- Phase 2 产出 `final_answer(filtered=True, finish_reason=CONTENT_FILTER)`。
- 不 continuation。
- 不 run_failed。

`FinishReason.LENGTH`：

- Phase 2 产出 `final_answer(filtered=False, finish_reason=LENGTH)`。
- 不 continuation。
- 在 README 中不得写 continuation 已可用。

OLD 对照：

- OLD content_filter 保留 partial content 并 final answer filtered。
- OLD length 可触发 continuation；Phase 2 有意不迁，留给 Phase 5。

### 6.4 runner abnormal stop

触发：

- Runner 流结束，无 `RunnerDoneData`。
- token 未取消。

映射：

- `run_failed("runner_abnormal_stop")`

不得：

- 使用 partial content 产出 final answer。
- 伪造 `RunnerDoneData`。

### 6.4.1 runner error done without detail

触发：

- 收到 `RunnerDoneData(FinishReason.ERROR)`。
- 此前没有 `RunnerHTTPErrorData` 或 `RunnerProtocolErrorData`。

映射：

- `run_failed("runner_error_done_without_detail")`
- `recoverable=False`

不得：

- 产出 `final_answer`。
- 落入 `missing_terminal` fallback。
- 静默结束事件流。

### 6.5 max iteration exceeded

触发：

- `agent_policy.max_iterations < 1`
- 或 Phase 2 遇到需要下一轮才能完成的状态，例如 tool call。

映射：

- `run_failed("max_iterations_exceeded")` 或更具体 `tool_call_not_supported_in_phase2`。

### 6.6 Runner close error

计划：

- close error 不覆盖已经产出的 terminal。
- close error 记录为 Engine logger warning。
- 若主体路径尚未产生 terminal，主体路径必须先收口为 run_failed 或 run_cancelled，再进入 finally close。

测试：

- success close called。
- failure close called。
- cancellation close called。
- close raises 时 terminal event 仍唯一且不变。

### 6.7 AgentRunResult 映射

`run_agent_and_wait`：

- 消费 `run_agent_messages`。
- 记录最后一个 terminal event。
- `FINAL_ANSWER` -> `EngineRunOutcomeFinalAnswer`
- `RUN_FAILED` -> `EngineRunOutcomeFailed`
- `RUN_CANCELLED` -> `EngineRunOutcomeCancelled`
- Phase 2 不产出 `RUN_SUSPENDED`，README 和测试不得把 suspended 写成可用能力；实现可保留防御性分支，把意外 `RUN_SUSPENDED` 视为内部协议错误并返回 `EngineRunOutcomeFailed("unexpected_suspended_in_phase2")`，或在私有穷尽匹配中显式拒绝。
- 若事件流结束无 terminal，返回 `EngineRunOutcomeFailed(error_code="missing_terminal")` 或抛内部 assertion 需要设计决定。推荐返回 failed，保证函数式入口不静默成功。

## 7. Phase 2 smoke 脚本计划

新增文件：

- `utils/smoke_async_agent_providers.py`

定位：

- 仅用于人工验证。
- 不放入 `dayu/`。
- 不纳入 pytest 常规联网测试。
- 可做静态检查或轻量单元测试覆盖参数解析 / 缺 key 跳过。

prompt：

- `用一句话回答：2+2 等于几？`

provider case：

- 参考 OLD `llm_models.json` 后在脚本内写死少量非敏感配置。
- 不运行时读取 OLD 文件。
- API key 只从环境变量读取。

建议内置 case：

- `openai-gpt-5.4`：`OPENAI_API_KEY`，endpoint `https://api.openai.com/v1/chat/completions`，model `gpt-5.4`，supports_stream_usage=True。
- `deepseek-v4-flash`：`DEEPSEEK_API_KEY`，endpoint `https://api.deepseek.com/chat/completions`，model `deepseek-v4-flash`，supports_stream_usage=True。
- `gemini-2.5-flash`：`GEMINI_API_KEY`，endpoint `https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`，model `gemini-2.5-flash`，supports_stream_usage=False。
- `qwen-plus`：`QWEN_API_KEY`，endpoint `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，model `qwen3.6-plus`，supports_stream_usage=True。

脚本行为：

- 调用 `dayu.runtime.log.configure(level=LogLevel.DEBUG)`。
- 支持 `--case name` / `--all` / `--stream true|false` / `--timeout-seconds`。
- 构造 `RunnerSpec.headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}`。
- 构造 `AgentRunRequest`，`disable_tools=True`，`tool_schemas=()`。
- 使用 `run_agent_messages` 打印安全摘要：case 名、事件 type、content delta 长度、final answer 是否收到。
- 缺 key 时友好跳过该 case，退出码仍为 0，除非用户显式指定单 case 且要求 strict。

验证目标：

- provider request 发出。
- Runner debug log 可读。
- Agent 收到 `final_answer`。
- Runner close 无异常。
- 缺 key 友好跳过。

禁止输出：

- API key。
- headers。
- 完整 payload。
- 完整 prompt。
- 财报内容。
- provider response body preview。

自动测试边界：

- 可测试缺 key skip。
- 可测试 CLI case 枚举。
- 可测试不会读取 OLD 文件。
- 不做真实联网测试。

## 8. `dayu/engine/README.md` 计划

Phase 2 实施完成后必须新建：

- `dayu/engine/README.md`

这是用户明确要求的 README 例外。

内容只写当前 Phase 2 已落地事实：

- Engine 当前职责边界。
- 当前分层关系：`UI -> Service -> Host -> Engine`。
- Host 与 Engine 的稳定依赖表面。
- 函数式入口：
  - `run_agent_messages`
  - `run_agent_and_wait`
- run-scoped Agent 生命周期。
- RunnerEvent -> EngineEvent 提升关系。
- 无工具主链路状态机。
- `final_answer` / `run_failed` / `run_cancelled` 的终态收口。
- cancellation 优先级。
- Runner close 语义。
- Phase 1 OpenAI-compatible Runner 当前定位。
- Phase 1.5 Runner diagnostics / SSE idle timeout 当前定位。

不得写成可用能力：

- ToolExecutor tool calling 闭环。
- awaiting / long-running tool waiting。
- Host ToolRegistry。
- trace store。
- transcript 持久化。
- conversation memory。
- context budget / continuation。

不得新建或修改其它 README，除非 `tests/README.md` 确实因新增测试分层变化而需要更新。

根 README、`dayu/README.md`、`dayu/host/README.md`、`dayu/fins/README.md`、`dayu/config/README.md` 仍按迁移结束后统一同步处理。

## 9. 测试计划

### 9.1 新增 / 修改测试建议

新增目录 / 文件建议：

- `tests/engine/test_agent_entrypoints.py`
- `tests/engine/test_agent_run_loop.py`
- `tests/engine/test_agent_cancellation.py`
- `tests/engine/test_agent_errors.py`
- `tests/engine/test_agent_package_exports.py` 或更新现有 `test_package_exports.py`
- `tests/engine/test_agent_import_boundary.py` 或扩展现有 `test_import_boundary.py`
- `tests/utils/test_smoke_async_agent_providers.py`，仅轻量无网络测试，若不新增测试层级则可放在现有合适目录并同步 `tests/README.md`

### 9.2 必测项

- 函数式入口导出测试。
- 包根导出边界：导出 `run_agent_messages` / `run_agent_and_wait`，不导出 `_AsyncAgent` / `AsyncOpenAIRunner`。
- 无工具成功 run。
- RunnerEvent 提升为 EngineEvent。
- content delta / reasoning delta / usage / runner_done 顺序。
- final_answer 只由 Agent 产生。
- provider protocol error -> run_failed。
- HTTP error -> run_failed。
- `RUNNER_DONE(ERROR)` 且无先前 HTTP / protocol error -> run_failed，错误码为 `runner_error_done_without_detail` 或等价中性码，且不产出 final_answer。
- Runner 普通异常 -> run_failed。
- cancellation token 已取消 -> run_cancelled。
- Runner 因取消自然终止且无 RunnerDoneData -> run_cancelled。
- final_answer 前取消命中 -> run_cancelled 优先。
- provider error 与取消同时出现 -> run_cancelled 优先。
- Runner close 在 success / failure / cancellation 中都执行。
- Runner close error 不覆盖 terminal，且 terminal event 唯一。
- cancellation terminal 的 `finished_at` 晚于或等于 Runner close 尝试完成时间。
- event_id 唯一。
- sequence 单调。
- terminal event 唯一。
- 私有 Agent 实例并发 fail-fast。
- `run_agent_and_wait` 对 final / failed / cancelled 的结果映射。
- `run_agent_and_wait` 不把 Phase 2 不支持的 `RUN_SUSPENDED` 写成可用能力；若出现意外 suspended，只走防御性失败或内部协议错误分支。
- Engine 不依赖 Host / Service / UI / fins / trace / ToolRegistry。
- Runner 仍只产出 RunnerEvent。
- Phase 2 收到 tool call delta / completed 时 fail closed，不调用 ToolExecutor。
- smoke 脚本缺 key 友好跳过。
- smoke 脚本不输出 key / headers /完整 payload / 完整 prompt。
- smoke 脚本安全输出测试使用醒目 sentinel 覆盖 prompt / header / payload，断言 stdout / stderr / caplog 不包含 sentinel。
- `FinishReason.LENGTH` 不消费 `AgentPolicy.continuation_max_attempts`，建议测试名：`test_length_finish_reason_does_not_consume_continuation_policy_in_phase2`。
- `dayu/engine/README.md` 只描述当前落地事实，不写未来能力。

### 9.3 OLD 关键语义覆盖映射

- OLD run-scoped close -> NEW success/failure/cancellation close tests。
- OLD same-agent concurrent fail-fast -> NEW 私有 `_AsyncAgent` 并发测试。
- OLD iteration start -> NEW `ITERATION_STARTED` data 测试。
- OLD Runner content/reasoning passthrough -> NEW RunnerEvent 提升测试。
- OLD `done` 不等于 final answer -> NEW runner_done 与 final_answer 分离测试。
- OLD final answer 前取消 -> NEW `run_cancelled` 优先测试。
- OLD Runner mid-stream cancel -> NEW Runner 自然终止无 done 后 `run_cancelled`。
- OLD content_filter final filtered -> NEW `FinishReason.CONTENT_FILTER` final_answer 测试。
- OLD max iteration fallback -> Phase 2 不迁 force-answer；仅测 `max_iterations < 1` failed，并明确 Phase 5 覆盖 continuation/fallback。
- OLD tool loop -> Phase 2 不覆盖 tool execution；仅测收到 tool call fail closed，Phase 3 迁移。
- OLD trace recorder close -> Phase 2 不迁 trace；只覆盖 Runner close。

### 9.4 验证命令

实施完成后必须运行：

```bash
source .venv/bin/activate && pytest tests/contracts tests/runtime tests/engine -q
source .venv/bin/activate && pyright
```

若新增 `tests/utils/`：

```bash
source .venv/bin/activate && pytest tests/utils -q
```

若只新增 `utils/` 手动脚本且没有测试分层变化，可不更新 `tests/README.md`，但仍需保证 pyright 配置覆盖 `utils/` 时无类型错误。

## 10. pyright 要求

- Agent loop 内部状态必须完整类型化。
- 不用 `Any` / `object` / 裸 `dict` 传递 EngineEvent data。
- RunnerEvent -> EngineEvent 使用 `match` + 封闭联合，新增 RunnerEventData 分支时测试失败或类型检查暴露。
- `run_agent_and_wait` 返回 `AgentRunResult` 封闭联合。
- smoke 脚本若被 pyright 扫描，也必须类型完整。
- 不新增、扩散、掩盖类型错误。
- 若触及现有 pyright 报错，必须一并修复，至少不能扩散。

## 11. README / docs 同步判断

- Phase 2 必须新建 `dayu/engine/README.md`。
- `dayu/engine/README.md` 只写当前已落地事实，不写未来设计。
- 如果新增测试分层且属于 `tests/README.md` 职责范围，可以更新 `tests/README.md`。
- 不新建、不修改除 `dayu/engine/README.md` 和 `tests/README.md` 外的任何 README。
- 其它 README 统一 Phase 6 处理。
- 本计划文件本身位于 `docs/engine/phase2-plan.md`，不是 README 同步。

## 12. Review 与验收计划

实施完成后门禁：

1. 新建 `dayu/engine/README.md`，并由 review Agent 按“只写当前已落地事实，不写未来设计”审查。
2. 常规 code review，按 `docs/code_review.md` 逐项审查代码、测试、文档。
3. 常规 code review 通过后，再做一轮 NEW / OLD AsyncAgent 与 Runner 消费边界严格实现代码对照 review。
4. 严格对照 review 必须以 OLD `AsyncAgent` 的可靠状态机和测试事实为强参考源。
5. 严格对照 review 重点检查：
   - NEW 是否保留 run-scoped close。
   - NEW 是否保留取消优先于 final answer。
   - NEW 是否保留 terminal 唯一。
   - NEW 是否没有把 tool loop、trace、memory、continuation 偷偷迁入 Phase 2。
   - NEW 是否正确消费 Phase 1 Runner 的取消自然终止语义。
6. 严格对照 review 通过后，Phase 2 才能进入提交 / PR 流程。
7. 总控需要提醒此门禁，不能只凭常规 code review 合并。

验收信号：

- `run_agent_messages` / `run_agent_and_wait` 可从 `dayu.engine` 导入并真实工作。
- 无工具 run 能产出 `final_answer` / `run_failed` / `run_cancelled`。
- Runner close 在所有终态路径执行。
- 测试与 pyright 通过。
- `dayu/engine/README.md` 与当前代码事实一致。
- smoke 脚本人工运行时能安全验证多个 OpenAI-compatible provider，缺 key 不失败。

## 13. 停止条件

遇到以下任一情况必须停止实现，回到设计讨论或拆分新 issue：

- 发现需要新增公共契约但本计划未覆盖。
- 发现 Phase 2 必须接入 ToolExecutor 才能完成。
- RunnerEvent / EngineEvent 边界不成立。
- 取消终态无法通过 `RunCancelledData` / `EngineRunOutcomeCancelled` 无歧义表达。
- OLD AsyncAgent 的高可靠语义无法映射到 NEW contracts，且无法说明合理重设。
- 需要修改除 `dayu/engine/README.md` 和 `tests/README.md` 外的 README。
- smoke 脚本需要真实 key 才能通过自动测试。
- 实现需要导出 `_AsyncAgent`、`AsyncOpenAIRunner` 或任何兼容 wrapper 才能让 Host 使用。
- 为了通过测试需要在生产代码保留 OLD 接口兼容层。
- Agent loop 出现 `Any` / `object` / 裸 dict 状态袋。
- Runner close error 设计导致 terminal 可能重复或被覆盖。
- tool call 事件无法 fail closed，或存在工具被调用的路径。
