# Engine Phase 1 Code Review

## 1. Review 结论

通过。

本轮复审确认上一轮 4 个阻塞问题与 2 个重要问题均已收口：SSE fatal protocol error 现在以 `RunnerDoneData(FinishReason.ERROR)` 终止，SSE UTF-8 已改为增量解码，non-stream Gemini `<thought>` 已剥离到 `reasoning_content`，1xx / 3xx 等非 200 HTTP 状态已归入 `RunnerHTTPErrorData(UNKNOWN_HTTP_STATUS)`，XML tag extractor 已恢复 OLD 的 `start_only` 安全锁，协议错误测试也开始断言完整终态序列。Phase 1 可以进入总控验收。

## 2. 阅读范围

实际阅读 NEW 文件：

- `AGENTS.md`
- `docs/engine/design.md`
- `docs/engine/migration-plan.md`
- `docs/engine/phase1-plan.md`
- `docs/engine/phase1-plan-review.md`
- `docs/code_review.md`
- `docs/engine/phase1-code-review.md`
- `dayu/contracts/__init__.py`
- `dayu/contracts/tool_call.py`
- `dayu/engine/__init__.py`
- `dayu/engine/contracts/messages.py`
- `dayu/engine/contracts/runner.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/runner_spec.py`
- `dayu/engine/runners/openai/*.py`
- `tests/contracts/*`
- `tests/engine/*`
- `tests/engine/contracts/*`
- `tests/engine/runners/openai/*`

实际阅读 OLD 强参考源：

- `~/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `~/workspace/dayu-agent/dayu/engine/sse_parser.py`
- `~/workspace/dayu-agent/dayu/engine/reasoning_protocol.py`
- `~/workspace/dayu-agent/dayu/engine/xml_extractor.py`
- `~/workspace/dayu-agent/dayu/engine/README.md`

## 3. OLD 强参考对照结论

- payload 构建：显式消息、tools schema、`stream_options.include_usage` 门控、assistant `reasoning_content` outbound、Gemini `extra_content.google.thought_signature` outbound 已落实。
- SSE 解析：`data:`、`[DONE]`、多行 data、尾部残留 data、usage-only chunk、content/reasoning/tool_call delta、fatal protocol error、合法跨 chunk UTF-8 均已覆盖。
- reasoning 处理：stream 与 non-stream 均能按 Gemini hook 剥离 `<thought>`；XML extractor 已恢复 OLD 的 start-only / 失活语义。
- tool call delta：正常聚合、arguments 分片、`arguments: null`、缺 index 按 id 归属、Gemini provider_state、fatal tool call 校验错误均已覆盖。
- usage：stream usage 由 payload capability 门控，接收侧出现 usage 时产出 `RunnerUsageRecordedData`。
- HTTP 错误分类：429/4xx/5xx/network/timeout/1xx/3xx/unknown status 主路径均进入 `RunnerHTTPErrorData`。
- retry/backoff：`Retry-After`、指数退避、重试耗尽事件主路径有测试。
- cancellation：私有 `_RunnerInterrupted` 不导出，取消路径不产出 done，符合计划。
- close：`HTTPClient.close()` 幂等；未发现根包导出实现类。

## 4. 阻塞问题

无。

## 5. 重要问题

无。

## 6. 建议问题

### 6.1 `docs/code_review.md` 标题层级有轻微漂移

- 文件：`docs/code_review.md:105`
- 问题原因：本次变更把原 `## 6. Engine 契约专项` 改成了 `### 5.1. Engine 契约专项`，后续章节编号也整体前移。内容本身补充 Runner 状态机检查是合理的，但层级漂移会影响日常 review 文档导航。
- 建议修复方向：后续文档整理时恢复一致的二级章节编号；不作为 Phase 1 验收阻塞。

## 7. Runner 边界专项结论

- Runner 是否只产出 `RunnerEvent`：是，未发现 `EngineEvent` / `final_answer` / `run_cancelled` / `run_failed` / `run_suspended` 产出。
- 是否执行工具：未发现工具执行路径；`ToolExecutor` / `ToolRegistry` / `ToolRuntime` 未被 Runner 实现导入。
- 是否有 `set_tools` / `**extra_payloads`：未发现；`AsyncOpenAIRunner.call(messages, options, tools)` 与 `AsyncRunner` 参数名一致。
- 是否依赖 Host / Service / UI / fins / trace：AST 边界测试通过，人工走读未发现反向 import。
- `AsyncOpenAIRunner` 是否从 `dayu.engine` 根包导出：否；子模块导入成功，根包导入按预期失败。
- `aiohttp` 使用边界：仅在 `dayu/engine/runners/openai/` 子树内使用，符合 Phase 1 放开范围。

## 8. 取消边界专项结论

- `_RunnerInterrupted` 是 Runner 私有控制流异常，位于 `dayu/engine/runners/openai/cancellation_helpers.py`，未进入公共 contracts 或 `dayu.engine.__all__`。
- `AsyncOpenAIRunner._call_impl` 捕获 `_RunnerInterrupted` 后直接退出生成器，不补 `RunnerDoneData`，符合 Phase 1 取消例外。
- 取消路径没有伪装成 `RunnerHTTPErrorData` / `RunnerProtocolErrorData` / 工具失败 / final answer。
- 后续 Phase 2 仍必须按计划用 `token.is_cancelled() + 无 RunnerDoneData` 双条件提升为 `RunCancelledData` / `EngineRunOutcomeCancelled`。

## 9. 类型与契约归属专项结论

- `ToolCallProviderState` / `GeminiToolCallState` 位于 `dayu.contracts.tool_call`，`AssistantToolCall.provider_state` 位于 `dayu.engine.contracts.messages` 并引用公共协作协议，归属合理。
- `RunnerSpec`、`RunnerCallOptions`、`RunnerEvent`、`RunnerHTTPErrorData` 位于 `dayu.engine.contracts`，归属合理。
- `dayu.contracts` 未 import `dayu.engine`；`dayu.engine.contracts` 只依赖公共 contracts 与 Engine 契约，未发现 Host / Service / UI / fins 依赖。
- 公开 surface 未发现 `Any` / `object` / `**kwargs`；pyright 通过。
- `payload.py` 内仍有一个 `# type: ignore[typeddict-item]`，当前没有造成类型错误或弱类型公共表面；后续若继续收紧 `_OpenAI*` TypedDict，可顺手消掉。

## 10. 消息流与状态机专项结论

- 输入边界：Runner 输入来自 `messages/options/tools/spec/cancellation_token`，未依赖 Host / Service 状态。
- payload 构建：system / user / assistant / tool 四角色、assistant `reasoning_content`、assistant tool_calls、Gemini provider_state outbound shape 已实现。
- tool call streaming：正常 arguments 分片、`arguments: null`、缺 index 按 id 归属、fatal arguments / missing id 错误收口均已覆盖。
- 单次模型调用边界：未越界实现 Agent 多轮 loop。
- 状态终点：正常成功、协议错误、HTTP 错误、取消路径均清晰。
- RunnerEvent 顺序：成功主路径可消费；fatal 协议错误不会再同时产出成功完成事件。
- stream / non-stream 一致性：Gemini `<thought>` 在两条路径均归一到 reasoning。
- 状态机规模：模块拆分避免了 OLD god file；未发现 Runner 执行工具或 Agent 状态机迁入。

## 11. 测试与 pyright 结果

已运行：

```text
source .venv/bin/activate && pytest tests/contracts tests/engine -q
173 passed in 0.31s
```

已运行：

```text
source .venv/bin/activate && pyright
File or directory "/Users/leo/workspace/dayu-agent-r/utils" does not exist.
0 errors, 0 warnings, 0 informations
```

补充核验：

```text
from dayu.engine.runners.openai.runner import AsyncOpenAIRunner  # 成功
from dayu.engine import AsyncOpenAIRunner  # ImportError，符合预期
from dayu.engine import run_agent_messages  # ImportError，符合预期
```

补充复现：

- SSE invalid JSON 当前实际：`provider_protocol_error(sse_invalid_json) -> runner_done(ERROR)`。
- SSE tool call arguments 非对象当前实际：`runner_tool_call_delta -> provider_protocol_error(tool_call_arguments_not_object) -> runner_done(ERROR)`。
- 合法中文 UTF-8 跨 chunk 当前实际：`runner_content_delta("你") -> runner_content_completed("你") -> runner_done(STOP)`。
- non-stream `<thought>r</thought>answer` 当前实际：`RunnerContentCompletedData(content="answer", reasoning_content="r") -> runner_done(STOP)`。
- HTTP 300 + chat completion body 当前实际：`runner_http_error(UNKNOWN_HTTP_STATUS) -> runner_done(ERROR)`。

## 12. README / docs/code_review.md 同步判断

- 仓库当前不存在 `dayu/engine/README.md` / `dayu/README.md` / `tests/README.md`，未更新 README 与 `phase1-plan.md` §10 的“默认不创建 README”一致。
- `docs/code_review.md` 已补充 Runner 状态机专项检查，方向合理；但标题层级有轻微漂移，见建议问题 6.1。
- `git status --short` 未显示 `__pycache__` 被纳入提交范围。

## 13. 总体验收判断

建议进入总控验收。

Phase 1 最小验收范围已经达成：

- contract 补丁已落地并有同步测试。
- OpenAI-compatible Runner 实现存在于 `dayu/engine/runners/openai/`，不从 `dayu.engine` 根包导出。
- Runner 不执行工具、不依赖 ToolExecutor / ToolRegistry / Host / Service / UI / fins / trace。
- SSE / non-stream / reasoning / tool call provider_state / usage / HTTP 错误 / retry / cancellation / close 路径有测试覆盖。
- `pytest tests/contracts tests/engine -q` 与 `pyright` 均通过。
