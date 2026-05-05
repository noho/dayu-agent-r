# Phase 2 AsyncAgent / Agent Run Loop Code Review

## 1. Review 结论：通过

Phase 2 实施结果通过本轮 code review。

结论依据：当前实现正确限定为无工具 Agent 主链路，`run_agent_messages` / `run_agent_and_wait` 已成为真实函数式入口，私有 run-scoped `_AsyncAgent` 保留 OLD AsyncAgent 的可靠状态机核心语义，并且没有把 ToolRegistry、trace、transcript、conversation memory、context budget / continuation 或 awaiting 提前迁入 Engine。

本轮未发现阻塞问题与重要问题。发现 1 个建议级文档漂移问题，不影响 Phase 2 Agent 主链路验收。

## 2. 阅读范围

已阅读 NEW：

- `AGENTS.md`
- `CLAUDE.md`
- `docs/engine/design.md`
- `docs/engine/migration-plan.md`
- `docs/engine/phase2-plan.md`
- `docs/engine/phase2-plan-review.md`
- `docs/code_review.md`
- `tests/README.md`
- `dayu/contracts/`
- `dayu/engine/contracts/`
- `dayu/engine/agent.py`
- `dayu/engine/__init__.py`
- `dayu/engine/runners/openai/`
- `dayu/runtime/`
- `dayu/engine/README.md`
- `utils/smoke_async_agent_providers.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_engine_readme_phase2.py`
- `tests/engine/test_smoke_async_agent_providers.py`
- 相关边界测试：`tests/engine/test_package_exports.py`、`tests/engine/test_import_boundary.py`、`tests/engine/test_weak_typing_guard.py`

已对照 OLD 强参考源：

- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/cancellation.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/README.md`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_agent.py`

当前工作区事实：本 review 未修改生产代码、测试代码或 README；只新增本文件。

## 3. OLD AsyncAgent 对照结论

通过。

OLD `AsyncAgent` 的强参考语义在 NEW 中有对应实现或明确排除：

- OLD `_acquire_run_slot` / `_release_run_slot` 的同实例并发 fail-fast，对应 `dayu/engine/agent.py::_AsyncAgent._acquire_run_slot` 与测试 `test_private_agent_concurrent_run_fail_fast`。
- OLD `run_messages` 的 `finally` 关闭 Runner，对应 `_AsyncAgent.run_messages` 的 `finally` 调用 `_close_runner_once`。
- OLD 每轮 iteration 起点与 final answer 前取消检查，对应 `_AsyncAgent.run_messages`、`_run_once`、`_make_final_or_cancelled_after_close`、`_make_failed_or_cancelled_after_close`。
- OLD Runner 中途取消不产出 final answer，对应 `test_runner_cancelled_naturally_without_done_maps_cancelled`。
- OLD `content_filter` 不续写、以 filtered final answer 收口，对应 `test_length_and_content_filter_are_final_without_continuation`。
- OLD 工具闭环、ToolRegistry、trace recorder、transcript、conversation memory、context budget、continuation、force-answer fallback 均未迁入 Phase 2。

## 4. Phase 2 范围结论

通过。

直接证据：

- `dayu/engine/agent.py` 模块 docstring 明确 Phase 2 不执行工具、不写 trace、不做 transcript / memory / continuation。
- `_AsyncAgent._effective_tools()` 固定返回空元组，`test_phase2_passes_empty_tools_even_when_request_has_schema` 锁定该行为。
- 收到 `RunnerToolCallDeltaData` 或 `RunnerToolCallsCompletedData` 时只设置 `tool_call_not_supported_in_phase2` 失败候选，不调用 `ToolExecutor`，测试 `test_tool_call_delta_and_completed_fail_closed` 已覆盖。

结论：当前实现只覆盖无工具主链路，没有接入 ToolExecutor tool calling 闭环，没有 awaiting / long-running waiting，也没有把 tool call 伪装成 final answer。

## 5. 公共入口与包根导出结论

通过。

直接证据：

- `dayu/engine/agent.py::run_agent_messages(request)` 返回 `AsyncIterator[EngineEvent]`。
- `dayu/engine/agent.py::run_agent_and_wait(request)` 返回 `AgentRunResult`。
- `dayu/engine/__init__.py` 只新增真实函数式入口 `run_agent_messages` / `run_agent_and_wait`。
- `_AsyncAgent` 未进入 `dayu.engine.__all__`。
- `AsyncOpenAIRunner` 未从 `dayu.engine` 包根导出。
- `tests/engine/test_package_exports.py` 锁定 `__all__` 白名单和 forbidden symbols。

未发现兼容 wrapper / facade / 旧实现 re-export。

## 6. Agent 状态机结论

通过。

覆盖事实：

- run start：`_AsyncAgent.run_messages` 先申请 run slot，再处理取消与主循环。
- iteration_started：`_run_once` 产出 `ITERATION_STARTED`，包含 `iteration_id`、`iteration_index`、`message_count`。
- Runner call：`_runner.call(messages, runner_options, effective_tools)`。
- RunnerEvent -> EngineEvent：`_consume_runner_event` 逐类提升 content delta、reasoning delta、content completed、usage、protocol error、runner done。
- final_answer：只在 `RUNNER_DONE` 后由 Agent 生成。
- run_failed：HTTP error、protocol error、bare error done、普通异常、abnormal stop、tool call 均有失败收口。
- run_cancelled：入口已取消、Runner 自然结束无 done 且 token 已取消、final / failure 前取消均有收口。
- terminal 唯一：`_terminal_seen` 与 `_make_terminal_event` 防止重复终态。
- sequence / event_id：`_make_event` 使用 run 内 sequence 单调递增，并以 `f"{run_id}:{sequence}"` 生成唯一事件 id。
- Runner close finally：`run_messages` 的 `finally` 统一调用 `_close_runner_once`。
- 同实例并发 fail-fast：`_active_run_id` + `threading.Lock` 实现，测试覆盖。

## 7. 取消边界结论

通过。

直接证据：

- run start 前 token 已取消：`run_messages` 在调用 `_run_once` 前检查，并通过 `_make_cancelled_terminal_after_close` 先 close Runner 再产出 `RUN_CANCELLED`。
- 取消优先于 final answer：`_terminal_after_runner_event` 与 `_make_final_or_cancelled_after_close` 在 final 前检查 token。
- 取消优先于 failure terminal：`_make_failed_or_cancelled_after_close` 先检查 token。
- Runner 因取消自然终止且无 `RunnerDoneData`：`_run_once` 在 runner loop 结束后先检查 token，再决定 abnormal stop 或 failed。
- `RunCancelledData.finished_at`：`_make_cancelled_terminal_after_close` 在 `await _close_runner_once()` 后填充。
- 外层 `asyncio.CancelledError`：`_run_once` 显式 `except asyncio.CancelledError: raise`，不会被收口成普通 `run_cancelled`。
- close error：`_close_runner_once` 只记录 warning，不覆盖已确定 terminal。

取消没有被伪装成工具失败、HTTP 失败或最终回答。

## 8. 错误与 finish reason 结论

通过。

覆盖事实：

- HTTP error：`RunnerHTTPErrorData` 记录为失败候选，随后 `RUNNER_DONE(ERROR)` 收口 `run_failed`；测试 `test_http_error_maps_to_run_failed_without_extra_engine_event` 覆盖。
- protocol error：先提升 `PROVIDER_PROTOCOL_ERROR`，再收口 `run_failed`；测试 `test_protocol_error_and_error_done_maps_to_run_failed` 覆盖。
- ordinary runner exception：`except Exception as exc` 收口为 `runner_exception`；测试覆盖。
- bare `RunnerDoneData(FinishReason.ERROR)`：收口为 `runner_error_done_without_detail`；测试覆盖。
- `CONTENT_FILTER`：直接 filtered final answer，不 continuation。
- `LENGTH`：Phase 2 直接 final answer，不 continuation。
- `TOOL_CALLS` / tool call event：收口 `tool_call_not_supported_in_phase2`。
- runner abnormal stop：无 done 且未取消时 `runner_abnormal_stop`。
- close error 不覆盖 terminal。
- `RUN_SUSPENDED`：`run_agent_messages` 不产出；`run_agent_and_wait` 只保留防御性失败分支。

## 9. RunnerEvent 消费边界结论

通过。

Phase 2 传空 tools，Runner 仍只产出 `RunnerEvent`，Agent 是唯一负责 `EngineEvent` 与 terminal 的组件。HTTP error 细节在当前 EngineEvent contract 下有意收窄，没有塞进 metadata；该行为与 `phase2-plan-review.md` 的结论一致。

未发现 ToolExecutor 调用路径，未产出 `ToolCallRequestedData`。

## 10. smoke 脚本结论

通过。

直接证据：

- 文件位于 `utils/smoke_async_agent_providers.py`，未进入 `dayu/` 生产包。
- 模块 docstring 明确只服务人工验证，不做真实联网 pytest。
- provider case 是脚本内常量，没有运行时读取 OLD 文件。
- API key 只通过 `env.get(case.env_var)` 读取，并只进入 `RunnerSpec.headers`。
- `main()` 调用 `configure(level=LogLevel.DEBUG)`。
- 缺 key 时输出 `SKIP ... missing_env=...` 并继续，轻量测试已覆盖。
- `safe_event_summary` 只输出事件类型、sequence、content_len、filtered，不输出 key、headers、payload、完整 prompt 或完整回答。
- `tests/engine/test_smoke_async_agent_providers.py` 只覆盖参数解析、缺 key skip、安全摘要和不引用 OLD 文件，不真实联网。

## 11. `dayu/engine/README.md` 结论

通过。

`dayu/engine/README.md` 已新建，内容只描述当前 Phase 2 已落地事实：

- Engine 职责边界与 `UI -> Service -> Host -> Engine`。
- Host 稳定依赖表面。
- `run_agent_messages` / `run_agent_and_wait`。
- run-scoped Agent 生命周期。
- RunnerEvent -> EngineEvent。
- 无工具状态机与三类 terminal。
- 取消优先级与 Runner close。
- OpenAI-compatible Runner、diagnostics、SSE idle。

README 明确把 ToolExecutor tool calling、awaiting、Host ToolRegistry、trace store、transcript、conversation memory、context budget / continuation 写为当前不负责或尚未落地能力，没有把 Phase 3+ 能力写成可用能力。

除 `dayu/engine/README.md` 外，本轮未发现其它 README 被 Phase 2 修改。

## 12. 架构与类型结论

通过。

架构边界：

- `dayu/engine` 未 import Host / Service / UI / fins / trace / ToolRegistry。
- `dayu/runtime` 未反向 import Engine / Host / Service / UI / fins。
- Engine 未读取财报文件；README 也明确财报文档只能通过 `dayu.fins.storage` 所属仓储边界处理。
- Runner 不依赖 ToolExecutor / ToolRegistry，不产出 EngineEvent。

类型边界：

- Agent loop 使用强类型 dataclass / enum / union，不用裸 dict 传递 EngineEvent data。
- pyright 通过。
- `tests/engine/test_weak_typing_guard.py` 覆盖 `dayu.engine` 源码弱类型守卫。
- 未发现用 `getattr` / `hasattr` 逃避 Engine 边界设计；`dayu.runtime.log` 中 handler marker 的 `getattr` 属于 stdlib logging handler 管理，不属于业务边界逃逸。

## 13. 测试与 pyright 结果

已运行：

```bash
source .venv/bin/activate && pytest tests/runtime tests/contracts tests/engine -q
```

结果：

```text
281 passed in 1.07s
```

已运行：

```bash
source .venv/bin/activate && pyright
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

## 14. 阻塞问题

无。

## 15. 重要问题

无。

## 16. 建议问题

### S1-未修复-低-`tests/README.md` 未记录当前 `tests/runtime` 分层与常用验证命令

- **入口/函数**: 测试手册。
- **文件(行号)**: `tests/README.md:15`、`tests/README.md:20`、`tests/README.md:37`。
- **输入场景**: 开发者按测试手册运行“当前契约与 Engine 相关测试”或查阅“当前测试分层”。
- **实际分支**: 手册常用命令只写 `pytest tests/contracts tests/engine -q`，当前测试分层只列 `tests/contracts/`、`tests/engine/`、`tests/engine/contracts/`、`tests/engine/runners/openai/`。
- **预期行为**: 按当前仓库事实，`tests/runtime/` 已存在且本次 Phase 2 review 必跑命令包含 `tests/runtime`；测试手册应同步记录 runtime 测试分层与常用命令。
- **实际行为**: `tests/runtime` 没有进入手册常用命令和分层说明。
- **直接证据**: 本轮按用户要求实际运行 `pytest tests/runtime tests/contracts tests/engine -q`，结果 `281 passed`；`tests/README.md:20` 仍缺少 `tests/runtime`。
- **影响**: 文档读者可能漏跑 runtime cancellation / log 边界测试，属于测试手册漂移；不影响 Phase 2 Agent 主链路实现正确性。
- **建议改法和验证点**: 在后续文档同步中把常用命令改为包含 `tests/runtime`，并新增 `tests/runtime/` 分层说明；验证 `tests/README.md` 只描述当前测试事实，不写未来设计。
- **修复风险**: 低。
- **严重程度**: 低。

## 17. 总体验收判断

Phase 2 可以通过本轮 review。

当前实现满足无工具 Agent 主链路验收条件：函数式入口可用，RunnerEvent 能稳定提升为 EngineEvent，`final_answer` / `run_failed` / `run_cancelled` 三类 terminal 收口明确，取消优先级与 Runner close 语义符合 OLD 强参考状态机，工具调用与 Phase 3+ 能力未越界接入。测试与 pyright 均通过。
