# Engine 开发手册

本手册记录当前 Engine 已落地的开发边界。Engine 位于分层链路最下游：

```text
UI -> Service -> Host -> Engine
```

Host 是 run/session 生命周期、取消真源、治理与工具运行时的拥有者。Engine 只消费 Host 注入的强类型请求、Runner 规约、取消观察 token 与工具契约快照，并产出可被 Host 订阅的 `EngineEvent`。

## 当前职责

Engine 当前负责：

- 定义 Engine 公共契约：`AgentRunRequest`、`AgentRunResult`、`EngineEvent`、`RunnerEvent`、`AsyncRunner`、`RunnerSpec`、`AgentPolicy`。
- 提供函数式入口：`run_agent_messages(request)` 与 `run_agent_and_wait(request)`。
- 在私有 run-scoped Agent 中消费单次 Runner 事件流，并提升为带 `session_id`、`run_id`、`sequence`、`event_id` 的 `EngineEvent`。
- 收口无工具主链路的三类终态：`final_answer`、`run_failed`、`run_cancelled`。
- 维护 OpenAI-compatible Runner，把 provider 响应归一为 `RunnerEvent`。
- 在 Runner 边界提供诊断日志与 SSE idle heartbeat / timeout 处理；这些诊断不进入事件契约。

Engine 当前不负责：

- Host ToolRegistry、工具权限、工具执行调度或长事务等待。
- ToolExecutor tool calling 闭环。
- trace store、transcript 持久化、conversation memory。
- context budget、continuation 或语义压缩。
- 财报文档存取；财报文档只能通过 `dayu.fins.storage` 所属仓储边界处理。

## 稳定依赖表面

Host 稳定依赖以下表面：

- `dayu.engine.run_agent_messages`
- `dayu.engine.run_agent_and_wait`
- `dayu.engine.contracts`
- `dayu.contracts`

Host 不应依赖以下实现细节：

- 私有 `_AsyncAgent`
- `AsyncOpenAIRunner` 具体类
- Runner close 的内部实现
- Engine 私有错误码常量

`dayu.engine.__all__` 当前只导出契约与两个真实函数式入口，不导出 Agent / Runner 实现类，也不导出公共取消异常。

## 事件流

Runner 只产出 `RunnerEvent`。RunnerEvent 不包含 Host 治理字段，不携带 `session_id`、`run_id`、`sequence` 或 `event_id`。

私有 Agent 负责把 RunnerEvent 提升为 EngineEvent：

- `RUNNER_CONTENT_DELTA` -> `RUNNER_CONTENT_DELTA`
- `RUNNER_REASONING_DELTA` -> `RUNNER_REASONING_DELTA`
- `RUNNER_CONTENT_COMPLETED` -> `RUNNER_CONTENT_COMPLETED`
- `RUNNER_USAGE_RECORDED` -> `RUNNER_USAGE_RECORDED`
- `PROVIDER_PROTOCOL_ERROR` -> `PROVIDER_PROTOCOL_ERROR`
- `RUNNER_DONE` -> `RUNNER_DONE`

HTTP error 当前不提升为单独 EngineEvent；Agent 将其记录为失败候选，并收口为 `run_failed`。显式契约事实不得塞进 `metadata`。

`final_answer` 只能由 Agent 产生，Runner 不能产生最终回答终态。

## Run-Scoped Agent

Phase 2 的 Agent 是 run-scoped 私有实现。每次函数式入口调用都会创建 Runner 与 Agent，单次 run 结束后关闭 Runner。

生命周期：

1. 申请当前 Agent 实例运行槽位，同一实例并发运行 fail-fast。
2. 若 cancellation token 已取消，先 close Runner，再产出 `run_cancelled`。
3. 产出 `iteration_started`。
4. 以空工具 schema 调用 Runner。
5. 消费并提升 RunnerEvent。
6. 在 `runner_done` 或错误边界后收口唯一 terminal。
7. success / failure / cancellation 都执行 Runner close。

Runner close 失败只记录日志，不覆盖已经确定的业务 terminal。

## 无工具主链路状态机

当前 Agent 只执行一轮无工具 LLM call：

- `max_iterations < 1` -> `run_failed("max_iterations_exceeded")`
- 正常 `STOP` -> `final_answer`
- `CONTENT_FILTER` -> `final_answer(filtered=True)`
- `LENGTH` -> `final_answer(filtered=False)`，当前不 continuation
- `ERROR` -> `run_failed`
- `TOOL_CALLS` 或任一 Runner tool call 事件 -> `run_failed("tool_call_not_supported_in_phase2")`
- Runner 流结束但无 `RunnerDoneData` -> `run_failed("runner_abnormal_stop")`，若此时 token 已取消则 `run_cancelled`

terminal event 在单次 run 内唯一，`sequence` 从 0 起单调递增，`event_id` 以 run 内 sequence 保持唯一。

## 取消优先级

取消是 Host 拥有的治理事实，Engine 只观察 `CancellationToken`。当前公共取消终态是 `run_cancelled` / `EngineRunOutcomeCancelled`，不是公共取消异常。

优先级规则：

- 取消优先于 `final_answer`。
- 取消优先于 failure terminal。
- Runner 因取消自然终止且没有 `RunnerDoneData` 时，Agent 收口为 `run_cancelled`。
- `RunCancelledData.finished_at` 表示 Runner close 尝试完成后的时间。
- 外层 `asyncio.CancelledError` 继续透传。

## OpenAI-Compatible Runner

当前唯一内置 Runner 是 OpenAI-compatible Runner。它负责：

- 构造 OpenAI 风格请求 payload。
- 按 `RunnerSpec.provider_request` 强类型扩展投影 provider 私有请求字段：
  `OpenAIReasoningExtension`、`AnthropicThinkingExtension`、
  `DeepSeekThinkingExtension`、`MimoThinkingExtension`、
  `GeminiThinkingExtension`、`QwenThinkingExtension`。
- provider 私有字段用 `None` 表示不传；只有 provider 文档把 `0`
  定义为显式关闭时才传 `0`。
- 解析 SSE 与 non-stream JSON 响应。
- 归一 content、reasoning、usage、tool call、HTTP error、protocol error 与 done 事件。
- 执行 HTTP retry / backoff。
- 观察 cancellation token。
- 关闭 HTTP 资源。

Runner 不执行工具，不依赖 `ToolExecutor` / ToolRegistry，不产出 `EngineEvent`。

## Diagnostics 与 SSE Idle

Runner 使用标准库 `logging.getLogger(__name__)` 记录运行边界诊断。日志装配入口在 `dayu.runtime.log`，Engine 代码不导入 `dayu.runtime.log`。

SSE idle heartbeat / timeout 属于 Runner 字节流读取边界：

- heartbeat 只写诊断日志，不进入 RunnerEvent / EngineEvent。
- hard timeout 映射为 Runner HTTP timeout 错误，并沿 RunnerEvent 失败路径收口。
- cancellation 与 timeout 同时出现时，取消优先。

## 扩展点

当前稳定扩展点是契约而不是实现类：

- 新 Runner 需要实现 `AsyncRunner`，只产出 `RunnerEvent`。
- 新 provider 参数应进入 `RunnerSpec` / provider request extension 的强类型字段。
- 新 EngineEvent 或 RunnerEvent 必须扩展封闭 data 联合，并补齐穷尽匹配测试。
- 工具调用闭环、awaiting、trace store、conversation memory、context budget / continuation 尚未落地；这些能力不能通过当前 Phase 2 Agent 私自接入。
