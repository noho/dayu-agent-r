# Gateflow Plan: OpenAI-compatible Runner provider_request_id 采集与 Engine 透传

日期：2026-05-12
当前 gate：plan
Work unit：补齐 OpenAI-compatible Runner 的 provider_request_id 采集与 Engine 事件透传
Handoff-ready：Yes

## 1. Goal

让 Engine 对 OpenAI-compatible provider 的 request id 处理成为可观察的协议事实：

- OpenAI-compatible Runner 从 provider HTTP response headers 采集 provider 生成的 request id。
- HTTP error、SSE 协议错误、non-stream 协议错误、tool call 聚合协议错误都携带同一个 response-level provider_request_id。
- 成功路径也能把最终 provider response 的 request id 透传到 Engine iteration 完成事件，避免 request id 只在失败时可见。
- HTTP error 路径在不新增 Engine event type、不改变现有事件顺序的前提下，把 provider_request_id 透传到已有 Engine 事件 data。
- 保持 Host/Engine 边界：Host 不参与采集，Engine/Runner 只透传 provider 响应事实。

## 2. Non-goals

- 不生成、派生或重写 provider_request_id；没有 response header 时保持 `None`。
- 不引入 Host、Service、UI 依赖。
- 不修改 event_id / sequence 相关旧决策；本计划不新增 event id、sequence 字段，也不新增 Engine event type。
- 不把 `X-Client-Request-Id` 当成 provider_request_id；它是调用方提供的 client id，不是 provider 响应事实。
- 不基于未文档化的 provider error payload 字段猜测 request id。
- 不改 Runner retry 策略、error classifier、context compaction 策略或 cancellation 语义。

## 3. Motivation Judgment

动机成立，且严重性没有被高估。

直接证据：

- `dayu/engine/contracts/runner_events.py:148-164` 已定义 `RunnerProtocolErrorData.provider_request_id`。
- `dayu/engine/contracts/runner_events.py:167-192` 已定义 `RunnerHTTPErrorData.provider_request_id` 与 `raw_payload`。
- `dayu/engine/contracts/engine_events.py:194-212` 已定义 `ProviderProtocolErrorData.provider_request_id`。
- `dayu/engine/runners/openai/runner.py:345-374` 在 HTTP 非 200 路径读取 response body 和 headers，但没有采集 request id。
- `dayu/engine/runners/openai/runner.py:589-595` 构造 `RunnerHTTPErrorData` 时把 `provider_request_id=None`、`raw_payload=None` 写死。
- `dayu/engine/runners/openai/sse_parser.py:191-198`、`236-242`、`250-256`、`426-433` 在 SSE 协议错误中均写死 `provider_request_id=None`。
- `dayu/engine/runners/openai/non_stream_parser.py:97-103`、`115-121`、`129-135`、`167-173`、`179-185`、`356-364` 在 non-stream 协议错误中均写死 `provider_request_id=None`。
- `dayu/engine/agent.py:1071-1099` 已把 `RunnerProtocolErrorData.provider_request_id` 原样提升到 `ProviderProtocolErrorData`，说明协议错误透传链路已有，只是 Runner 没采集。
- `dayu/engine/agent.py:1100-1136` 对 `RunnerHTTPErrorData` 只设置失败候选并返回 `None`，当前 Engine 公共事件无法观察 HTTP error 的 provider_request_id。
- `tests/engine/test_agent_phase2.py:451-475` 已覆盖协议错误提升，但没有断言 provider_request_id 透传。
- `tests/engine/runners/openai/test_http_error_event.py:100-120` 只断言 HTTP error code/status/attempt/retried/done，没有覆盖 provider_request_id。

官方依据：

- OpenAI API Reference 的 Debugging requests 说明 response headers 包含 `x-request-id`，并建议生产部署记录 request id 以便排障。
- OpenAI Python SDK 文档说明 `_request_id` 来自 `x-request-id` response header，失败请求需从 status error 的 request_id 读取。
- OpenAI Node SDK 文档同样说明 object response 的 `_request_id` 来自 `x-request-id`，streaming 可用 `.withResponse()` 获取 request_id。

判断：

- 当前 contract 已把 provider_request_id 设计成强类型事实，但 OpenAI Runner 未采集，属于实现缺口。
- 单纯把 HTTP error 的 `None` 改成某个内部 id 是错误路径；provider_request_id 必须来自 provider response。
- 只补 HTTP error 不够：协议错误发生在 HTTP 200 response body 解析阶段，request id 在 response header 上，必须由 runner 注入 parser。
- 成功路径当前没有可承载 request id 的事件字段；若目标是生产可观测性，必须做一个小的公共契约扩展，而不是把事实塞进 metadata。

## 4. Affected Files / Modules

生产代码：

- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/agent.py`
- `dayu/engine/__init__.py`
- `dayu/engine/contracts/__init__.py`

测试：

- `tests/engine/runners/openai/test_http_error_event.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_old_protocol_parity_regressions.py`
- `tests/engine/runners/openai/test_sse_invalid_utf8_chunk.py`
- `tests/engine/runners/openai/_sse_helpers.py`
- `tests/engine/runners/openai/_fakes.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_runner_event_contract.py`
- `tests/engine/contracts/test_runner_events.py`
- `tests/engine/test_metadata_boundary.py`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_weak_typing_guard.py`

文档：

- `dayu/engine/README.md`
- 若总览已有“Runner/provider 诊断标识”表述不准确，再同步 `dayu/README.md`；当前优先只检查，不机械修改。

## 5. Public Contract Changes

需要公共契约变更；不新增事件类型，不改变事件顺序。

推荐变更：

1. `RunnerDoneData`
   - 新增 `provider_request_id: str | None`。
   - 语义：本次 Runner 调用最终采用的 provider response request id。网络层在收到 response 前失败时为 `None`；多次 retry 后成功时为最终成功 attempt 的 id；retry 耗尽时为最终失败 attempt 的 id。

2. `IterationCompletedData`
   - 新增 `provider_request_id: str | None`。
   - 语义：从 `RunnerDoneData.provider_request_id` 提升而来，作为 Engine iteration 级可观察事实。

3. `RunFailedData`
   - 新增 `provider_request_id: str | None`。
   - 语义：若失败直接源自 provider response / provider protocol，则携带对应 request id；工具失败、策略失败、runner 异常等非 provider-response 失败为 `None`。

4. `ContextCompactionRequestedData`
   - 新增 `provider_request_id: str | None`。
   - 语义：context overflow 来自 provider HTTP response 时，携带该 response 的 request id。

保持不变：

- `RunnerProtocolErrorData.provider_request_id`、`RunnerHTTPErrorData.provider_request_id`、`ProviderProtocolErrorData.provider_request_id` 字段不改名、不改类型。
- `EngineEvent.metadata` 不承载 provider_request_id；metadata 仍只放中性 observer/debug hint。

实现时不要给新增字段提供“为了兼容旧构造”的隐式默认值；应更新所有生产构造点和测试构造点，保持契约显式。

## 6. Implementation Decisions

### 6.1 Request id 来源

- 定义模块级常量，例如 `_PROVIDER_REQUEST_ID_HEADER_NAMES: tuple[str, ...] = ("x-request-id",)`。
- 新增私有辅助函数 `_extract_provider_request_id(headers: Mapping[str, str]) -> str | None`。
- 以大小写不敏感方式读取 header；空字符串或纯空白视为 `None`。
- 只从 response headers 采集 provider_request_id。当前官方 OpenAI 文档和 SDK 行为均指向 `x-request-id` header；没有证据支持从普通 chat/completions error payload 中推断 request id。

### 6.2 HTTP error body 与 raw_payload

- 新增私有 dataclass，例如 `_HTTPErrorBody`，字段为 `message_text: str` 与 `raw_payload: JsonValue | None`。
- 替换 `_safe_read_text` 为 `_safe_read_error_body` 或等价 helper：
  - 仍安全读取 response text，失败时 message 为空、raw_payload 为 `None`。
  - 若 body 是 JSON object，保存为 `raw_payload`。
  - message 仍优先使用当前 body text，避免顺手重写 error message 语义。
  - 不从 `raw_payload["request_id"]`、`raw_payload["error"]["request_id"]` 等字段推断 provider_request_id，除非后续有明确 provider 契约证据。

### 6.3 Attempt failure 数据携带

- 扩展 `_AttemptFailedRetriable` 与 `_AttemptFailedTerminal`：
  - `provider_request_id: str | None`
  - `raw_payload: JsonValue | None`
- response 已建立后的 HTTP status、stream read error、stream idle timeout 都应带上 response-level provider_request_id。
- response 建立前的 `aiohttp.ClientError` / `asyncio.TimeoutError` 没有 response headers，保持 `provider_request_id=None`、`raw_payload=None`。

### 6.4 Parser 注入

- `SSEParser.__init__` 新增必填 `provider_request_id: str | None`。
- `parse_non_stream_response` 新增必填 `provider_request_id: str | None` 参数。
- `ToolCallAggregator` 新增构造参数 `provider_request_id: str | None`，所有 fatal/warning `RunnerProtocolErrorData` 使用该值。
- `runner.py` 在拿到 response 后先提取 `provider_request_id`，再创建 parser 或调用 non-stream parser。
- SSE / non-stream 成功收口的 `RunnerDoneData` 写入该 id。
- SSE / non-stream 协议错误的 `RunnerProtocolErrorData` 写入该 id。

### 6.5 Engine 提升

- `_IterationState` 新增 `provider_request_id: str | None`，初始为 `None`。
- 处理 `RunnerProtocolErrorData` 时：
  - 保持现有 `ProviderProtocolErrorData` 提升。
  - 设置 `failure_candidate.provider_request_id=data.provider_request_id`。
- 处理 `RunnerHTTPErrorData` 时：
  - 设置 `failure_candidate.provider_request_id=data.provider_request_id`。
  - context overflow 分支的 `ContextCompactionRequestedData.provider_request_id` 使用同一值。
- 处理 `RunnerDoneData` 时：
  - `state.provider_request_id = data.provider_request_id`。
  - `IterationCompletedData.provider_request_id = data.provider_request_id`。
- 所有非 provider-response 失败构造 `RunFailedData` 时显式传 `provider_request_id=None`。

### 6.6 Logging

- Runner response 日志增加 `provider_request_id` 字段。
- Retry / exhausted / terminal 日志增加 provider_request_id，但不得记录 authorization headers、request body、raw error body。
- Agent HTTP error classified 日志增加 provider_request_id。

## 7. Small Implementation Slices

Slice 1：Runner contract and extraction plumbing

- 更新 `RunnerDoneData` contract、导出和契约测试。
- 在 `runner.py` 增加 header 提取 helper、HTTP error body helper、attempt failure 数据字段。
- HTTP error path把 `provider_request_id` 和 `raw_payload` 写入 `RunnerHTTPErrorData`。
- 覆盖 HTTP 4xx、429 retry exhausted、5xx retry exhausted、context overflow、网络错误无 response 的测试。

Slice 2：Parser protocol error propagation

- 更新 `SSEParser`、`parse_non_stream_response`、`ToolCallAggregator` 接口。
- 从 runner response header 注入 provider_request_id。
- 所有 SSE/non-stream `RunnerProtocolErrorData` 和 `RunnerDoneData` 写入 provider_request_id。
- 更新 parser helper 和协议错误测试，包括 invalid JSON、invalid UTF-8、usage malformed、tool call fatal/warning。

Slice 3：Engine event contract propagation

- 更新 `IterationCompletedData`、`RunFailedData`、`ContextCompactionRequestedData` contract、导出和 metadata boundary 测试。
- 更新 `_AsyncAgent` 的 state 和 RunnerEvent 提升逻辑。
- 新增/更新测试：
  - protocol error 的 `ProviderProtocolErrorData`、`IterationCompletedData`、`RunFailedData` 都携带同一 request id。
  - HTTP error 不新增事件类型，但 `IterationCompletedData` 和 `RunFailedData` 携带 request id。
  - context overflow 的 `ContextCompactionRequestedData`、`IterationCompletedData`、`RunFailedData` 携带 request id。
  - 非 provider 失败显式为 `None`。

Slice 4：Docs and final verification

- 更新 `dayu/engine/README.md` 中 RunnerEvent / EngineEvent / HTTP error / provider protocol error 的 request id 语义。
- 检查 `dayu/README.md` 是否已有表述仍准确；若只是泛称 Runner/provider 诊断标识，无需机械修改。
- 运行受影响测试、pyright、覆盖率检查。

## 8. Tests / Validation

必须先激活虚拟环境：

```bash
source .venv/bin/activate
```

推荐测试命令：

```bash
pytest tests/engine/runners/openai/test_http_error_event.py
pytest tests/engine/runners/openai/test_protocol_error.py
pytest tests/engine/runners/openai/test_sse_invalid_utf8_chunk.py
pytest tests/engine/runners/openai/test_old_protocol_parity_regressions.py
pytest tests/engine/contracts/test_runner_events.py
pytest tests/engine/test_runner_event_contract.py
pytest tests/engine/test_engine_event_contract.py
pytest tests/engine/test_metadata_boundary.py
pytest tests/engine/test_agent_phase2.py
pytest tests/engine/test_package_exports.py
pytest tests/engine/test_weak_typing_guard.py
```

建议最终回归：

```bash
pytest tests/engine tests/engine/runners/openai
pyright
```

覆盖率：

- 触及 `runner.py`、`sse_parser.py`、`non_stream_parser.py`、`tool_call_aggregator.py`、`agent.py`，需要确保新增分支有测试。
- 单文件覆盖率目标仍按项目要求 >= 80%；若现有配置支持，使用项目既有 coverage 命令检查受影响文件。

新增测试要点：

- Header 大小写：`x-request-id` / `X-Request-Id` 都能采集。
- Header 空值：空白值归一为 `None`。
- HTTP JSON error body：`raw_payload` 保存 JSON object，provider_request_id 仍来自 header。
- HTTP non-JSON error body：`raw_payload=None`，message 保持文本。
- Network error before response：provider_request_id 为 `None`。
- Stream idle timeout after response headers：最终 `RunnerHTTPErrorData.provider_request_id` 为 header id。
- Retry exhausted：最终错误事件使用最后一次失败 response 的 request id。
- Retry 后成功：`RunnerDoneData` / `IterationCompletedData` 使用最终成功 response 的 request id。

## 9. Docs Decision

需要更新 `dayu/engine/README.md`，因为本 work unit 修改 Engine contract 与 Runner/Agent 提升语义。

检查但不必然修改：

- `dayu/README.md`：只有当现有 “Runner/provider 层负责 request id 诊断标识” 表述与新 contract 不一致时才更新。

不需要更新：

- 根 `README.md`：用户 CLI、安装、配置、trace/render 入口未变化。
- `dayu/host/README.md`：无 Host contract 或治理状态变更。
- `dayu/fins/README.md`、`dayu/config/README.md`、`tests/README.md`：职责范围未被生产行为改变触发；若测试运行方式无变化，不更新 `tests/README.md`。

## 10. Risks / Open Questions

风险：

- 公共 contract 增字段会触发较多测试构造点更新；实现时必须全量搜索 `RunnerDoneData(`、`IterationCompletedData(`、`RunFailedData(`、`ContextCompactionRequestedData(`。
- `ToolCallAggregator` 现在直接构造 `RunnerProtocolErrorData(provider_request_id=None)`；若只改 parser 而漏改 aggregator，tool call fatal/warning 路径仍会丢 request id。
- `aiohttp` 真实 headers 是大小写不敏感结构，但测试 fake 使用普通 dict；helper 必须自己做大小写不敏感匹配，避免测试与生产行为分叉。
- 多次 retry 的历史 request ids 不进入公共事件，只保留最终 attempt id；历史 attempt id 仅进入日志。若将来需要完整 retry trace，应单独设计 trace/diagnostic event 或 Host trace store。
- 不从 error payload 推断 request id 可能遗漏某些 OpenAI-compatible provider 的私有字段；这是有意收窄，避免猜 API shape。

Open questions：

- 无 blocking question。本计划已选择最小公共 contract 扩展：不新增 Engine event type、不改变事件顺序，用现有 Engine events 承载 provider_request_id。

## 11. Completion Report Format

实现完成后按以下格式汇报：

```text
改了什么：
- ...

验证了什么：
- source .venv/bin/activate && pytest ...
- source .venv/bin/activate && pyright

文档：
- 更新/未更新哪些 README，原因是什么。

风险或未覆盖项：
- ...
```

