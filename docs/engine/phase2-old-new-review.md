# Phase 2 NEW/OLD AsyncAgent 严格对照 Review

## 1. Review 结论：通过 / 不通过

通过。

本轮严格比对 NEW Phase 2 `_AsyncAgent` / Agent run loop 与 OLD `AsyncAgent` 的高可靠状态机语义。NEW 没有发现阻塞或重要漂移：run-scoped 生命周期、RunnerEvent 消费边界、唯一终态、取消优先级、Runner close、并发保护和 Phase 2 无工具边界均符合 Phase 2 计划。

本轮仅发现 1 个建议级测试缺口：NEW 已在实现中透传外层 `asyncio.CancelledError`，但 Agent 层缺少直接回归测试锁住该边界。

## 2. 阅读范围

已阅读 NEW：

- `AGENTS.md`
- `CLAUDE.md`
- `docs/engine/design.md`
- `docs/engine/migration-plan.md`
- `docs/engine/phase2-plan.md`
- `docs/engine/phase2-plan-review.md`
- `docs/engine/phase2-code-review.md`
- `docs/code_review.md`
- `dayu/engine/agent.py`
- `dayu/engine/__init__.py`
- `dayu/engine/contracts/`
- `dayu/engine/runners/openai/`
- `dayu/runtime/`
- `dayu/engine/README.md`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_engine_readme_phase2.py`
- `utils/smoke_async_agent_providers.py`
- `tests/engine/test_smoke_async_agent_providers.py`

已阅读 OLD 强参考源：

- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/cancellation.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/README.md`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_agent.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner_call_paths.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_sse_parser.py`

## 3. OLD AsyncAgent 关键可靠语义摘要

OLD `AsyncAgent` 的关键可靠语义如下：

- 同一 Agent 实例通过 `_acquire_run_slot()` / `_release_run_slot()` 禁止并发运行；已有 active run 时 fail-fast。
- `run_messages()` 在 run 生命周期 finally 中无条件 `await self.runner.close()`，并关闭 trace recorder、释放 slot。
- `_run_loop()` 每轮先检查协作式取消，再产出 iteration start，再调用 Runner。
- Runner 事件由 Agent 消费并标注 run / iteration 元数据；`content_delta` 累积，`reasoning_delta` 透传，`content_complete` 保存正文和 reasoning，`done` 保存 usage / finish reason。
- `final_answer` 只由 Agent 产出；在提交 final 前再次 `_raise_if_cancelled()`，避免取消与最终回答同时落事实。
- Runner 或工具链取消以取消异常传播，阻止 final answer；OLD 测试覆盖 final 前取消、runner mid-stream cancelled、force answer 前取消。
- `content_filter` 收口为 filtered final answer；`length` 在 OLD 中进入 continuation，这属于 Phase 2 明确不迁移的能力。
- OLD Runner 承担 tool execution / ToolRegistry / trace / transcript / context budget / continuation 等职责；这些不是 Phase 2 NEW 的迁移目标。

直接证据：

- OLD run slot：`/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:499`
- OLD finally close / release slot：`/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:615`、`:642`
- OLD iteration 起始取消检查：`/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:697`
- OLD Runner event 消费：`/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:760`
- OLD final 前取消检查：`/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:1226`
- OLD 取消测试：`/Users/leo/workspace/dayu-agent/tests/engine/test_async_agent.py:1369`、`:1393`

## 4. NEW Phase 2 实现映射摘要

NEW 将 OLD 的可靠状态机语义映射到当前强类型 contracts：

- 公共入口为 `run_agent_messages(request)` 与 `run_agent_and_wait(request)`。
- 每次函数式入口创建 run-scoped `_AsyncAgent` 与 Runner；`_AsyncAgent` 保持私有。
- Agent 只消费 `RunnerEvent`，唯一负责产出 `EngineEvent` 与 terminal。
- Phase 2 始终向 Runner 传空工具 schema；遇 tool call delta / completed 或 `FinishReason.TOOL_CALLS` fail closed。
- 公共取消模型从 OLD 的公共取消异常重设为结构化 `run_cancelled` terminal；外层 task 的 `asyncio.CancelledError` 仍透传。
- `CONTENT_FILTER` 与 `LENGTH` 都按 Phase 2 计划直接 final，不做 continuation。

直接证据：

- NEW run-scoped 私有 Agent：`dayu/engine/agent.py:122`
- NEW 公共入口：`dayu/engine/agent.py:666`、`:683`
- NEW 空工具 schema：`dayu/engine/agent.py:612`
- NEW terminal 唯一与 sequence：`dayu/engine/agent.py:540`、`:563`
- NEW package exports：`dayu/engine/__init__.py:9`、`:102`
- package 白名单测试：`tests/engine/test_package_exports.py:100`

## 5. Run-scoped 生命周期对照结论

通过。

OLD `run_messages()` 在申请 run slot 后进入主循环，并在 finally 中 close Runner / trace recorder / release slot。NEW 对应实现为：

- `run_messages()` 入口 `_acquire_run_slot()`。
- success / failure / structured cancellation 均进入 finally 执行 `_close_runner_once()` 与 `_release_run_slot()`。
- run 开始前 token 已取消时，先 `_make_cancelled_terminal_after_close()`，其内部先 close Runner，再产出 `run_cancelled`。
- `_close_runner_once()` 幂等；普通 close error 只记录 warning，不覆盖 terminal。
- 外层 `asyncio.CancelledError` 不被 `_run_once()` 收口成普通 failure。

NEW 不迁移 OLD trace recorder close，因为 Phase 2 明确没有 trace store / transcript / ToolTrace 归属；这是合理重设。

直接证据：

- NEW finally close / release：`dayu/engine/agent.py:180`
- NEW cancelled terminal close 后产出：`dayu/engine/agent.py:476`
- NEW close error 不覆盖 terminal：`dayu/engine/agent.py:646`
- NEW close error 测试：`tests/engine/test_agent_phase2.py:654`

## 6. 并发保护对照结论

通过。

OLD 同一 `AsyncAgent` 实例通过 `_active_run_id` 与 lock fail-fast。NEW 私有 `_AsyncAgent` 仍保留同实例并发保护：

- `_active_run_id` 与 `threading.Lock` 保留。
- `_acquire_run_slot()` 在同实例已有 active run 时抛 `RuntimeError`。
- 测试 `test_private_agent_concurrent_run_fail_fast()` 覆盖并发 fail-fast。

虽然 NEW 函数式入口每次创建 run-scoped Agent，保留该保护仍合理：它防止测试、Host 误用或未来内部复用导致同一 Agent 状态缓冲交叉污染。

直接证据：

- OLD 并发保护：`/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:499`
- OLD 并发测试：`/Users/leo/workspace/dayu-agent/tests/engine/test_async_agent.py:773`
- NEW 并发保护：`dayu/engine/agent.py:184`
- NEW 并发测试：`tests/engine/test_agent_phase2.py:790`

## 7. RunnerEvent 消费对照结论

通过。

NEW 保持 Runner 只产出 `RunnerEvent`，Agent 负责提升为 `EngineEvent`：

- `RunnerContentDeltaData` -> 追加 content buffer 并产 `RUNNER_CONTENT_DELTA`。
- `RunnerReasoningDeltaData` -> 追加 reasoning buffer 并产 `RUNNER_REASONING_DELTA`。
- `RunnerContentCompletedData` -> 保存 completed content / reasoning / finish reason，并产 `RUNNER_CONTENT_COMPLETED`。
- `RunnerUsageRecordedData` -> 产 `RUNNER_USAGE_RECORDED`。
- `RunnerProtocolErrorData` -> 记录 failure candidate，并产 `PROVIDER_PROTOCOL_ERROR`。
- `RunnerHTTPErrorData` -> 只记录 failure candidate，不提升 HTTP error EngineEvent，不把细节塞进 metadata。
- `RunnerDoneData` -> 产 `RUNNER_DONE`，之后 Agent 判断 terminal。
- Runner tool call delta / completed -> fail closed，不产 `ToolCallRequestedData`。

NEW OpenAI Runner 的模块规则也保持 RunnerEvent 边界：HTTP / 网络 / 超时终态错误发 `RunnerHTTPErrorData + RunnerDoneData(ERROR)`，取消时自然终止不补 done。

直接证据：

- NEW Agent 消费：`dayu/engine/agent.py:291`
- NEW HTTP error 不提升：`dayu/engine/agent.py:364`
- NEW Runner terminal 规则：`dayu/engine/runners/openai/runner.py:9`
- NEW Runner call 签名只返回 RunnerEvent：`dayu/engine/runners/openai/runner.py:169`
- NEW HTTP error 测试：`tests/engine/test_agent_phase2.py:620`

## 8. final_answer 收口对照结论

通过。

OLD final answer 由 Agent 在 content complete / done 后统一产出，并在 final 前再次检查取消。NEW 保持该核心语义：

- `final_answer` 只在 RunnerDone 后由 `_terminal_after_runner_event()` 触发。
- 产 final 前 `_make_final_or_cancelled_after_close()` 再次检查 token。
- final content 优先使用 `RunnerContentCompletedData.content`；缺失时 fallback 到 content chunks。
- `CONTENT_FILTER` -> `final_answer(filtered=True)`。
- `LENGTH` -> Phase 2 直接 `final_answer`，不 continuation；这是计划内合理重设，并有测试锁住。
- `TOOL_CALLS` / tool call event 与 `ERROR` 都不会伪装成 final answer。

直接证据：

- OLD final 前取消：`/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py:1226`
- OLD content_filter 测试：`/Users/leo/workspace/dayu-agent/tests/engine/test_async_agent.py:1656`
- NEW final / cancel 分支：`dayu/engine/agent.py:417`、`:438`
- NEW LENGTH / CONTENT_FILTER 测试：`tests/engine/test_agent_phase2.py:730`

## 9. run_failed 收口对照结论

通过。

NEW 对 Phase 2 错误路径收口符合计划：

- HTTP error -> failure candidate，RunnerDone(ERROR) 后 `run_failed`。
- protocol error -> `PROVIDER_PROTOCOL_ERROR` + failure candidate，RunnerDone(ERROR) 后 `run_failed`。
- ordinary runner exception -> `run_failed("runner_exception")`。
- bare `RunnerDoneData(FinishReason.ERROR)` -> `run_failed("runner_error_done_without_detail")`。
- Runner abnormal stop -> `run_failed("runner_abnormal_stop")`；若 token 已取消则 `run_cancelled`。
- `max_iterations < 1` -> `run_failed("max_iterations_exceeded")`。
- close error 不覆盖已确定 terminal。
- terminal 唯一由 `_terminal_seen` 防重。

直接证据：

- NEW runner exception：`dayu/engine/agent.py:263`
- NEW bare ERROR done：`dayu/engine/agent.py:421`
- NEW abnormal stop：`dayu/engine/agent.py:275`
- NEW terminal 唯一：`dayu/engine/agent.py:540`
- NEW 对应测试：`tests/engine/test_agent_phase2.py:503`、`:654`、`:759`

## 10. run_cancelled 收口对照结论

通过。

NEW 公共取消模型与 OLD 不一致，但属于 Phase 2 合理重设：OLD 对协作式取消抛 `CancelledError`；NEW 对 Host cancellation token 产结构化 `run_cancelled` terminal。核心可靠语义未漂移：

- run start 前 token 已取消：不调用 Runner，先 close Runner，再 `run_cancelled`。
- Runner 因取消自然终止且无 `RunnerDoneData`：Agent 收口 `run_cancelled`。
- final answer 前再次检查取消，取消优先于 final。
- provider error / HTTP error 与取消同时存在时，取消优先于 failure terminal。
- `RunCancelledData.finished_at` 在 Runner close 尝试完成后。
- 外层 `asyncio.CancelledError` 在代码路径中透传，不被包装成普通 `run_cancelled`。

直接证据：

- NEW run start 已取消：`dayu/engine/agent.py:156`
- NEW cancelled terminal close 后 finished_at：`dayu/engine/agent.py:491`
- NEW final 前取消：`dayu/engine/agent.py:448`
- NEW outer `asyncio.CancelledError` 透传实现：`dayu/engine/agent.py:263`
- NEW 取消测试：`tests/engine/test_agent_phase2.py:515`、`:535`、`:558`、`:589`

## 11. iteration / sequence / event_id 对照结论

通过。

OLD 以 `iteration_id` 标注 Agent iteration，NEW 在 Phase 2 单轮无工具主链路中固定产出一次 `iteration_started`：

- `iteration_started` 在 Runner call 前产出。
- `iteration_id` 为 `{run_id}_iteration_1`。
- `sequence` 从 0 开始单调递增。
- `event_id` 为 `{run_id}:{sequence}`，run 内唯一。
- terminal event 唯一。
- RunnerEvent 不泄漏 Host 治理字段；`session_id` / `run_id` / `sequence` / `event_id` 只在 Agent 提升为 EngineEvent 时出现。

直接证据：

- NEW iteration_started：`dayu/engine/agent.py:218`
- NEW event_id / sequence：`dayu/engine/agent.py:563`
- NEW README 事件边界：`dayu/engine/README.md:48`

## 12. Phase 2 tool boundary 对照结论

通过。

NEW 未迁移 OLD tool loop，这是 Phase 2 计划要求：

- Agent `_effective_tools()` 始终返回空元组，不把 `request.tool_schemas` 暴露给 Runner。
- Runner tool call delta / completed 立刻设置 `tool_call_not_supported_in_phase2` failure candidate。
- `FinishReason.TOOL_CALLS` 收口为 `run_failed("tool_call_not_supported_in_phase2")`。
- 不调用 `ToolExecutor`。
- 不产出 `ToolCallRequestedData`。
- README 明确工具调用闭环、awaiting、ToolRegistry、trace store、conversation memory、context budget / continuation 尚未落地。

直接证据：

- NEW 空 tools：`dayu/engine/agent.py:612`
- NEW tool call fail closed：`dayu/engine/agent.py:382`、`:430`
- NEW README 边界：`dayu/engine/README.md:22`、`:137`
- NEW tool boundary 测试：`tests/engine/test_agent_phase2.py:121`、`:730`

## 13. Smoke 脚本结论

通过。

`utils/smoke_async_agent_providers.py` 符合人工 smoke 工具边界：

- 放在 `utils/`，不进入 `dayu/` 生产包。
- 模块 docstring 明确只服务人工验证，不做真实联网 pytest。
- provider case 为脚本内非敏感常量。
- API key 只从环境变量读取；缺 key 友好跳过。
- 使用 `dayu.runtime.log.configure(level=LogLevel.DEBUG)`。
- 输出只包含 case、event type、sequence、content_len、filtered 等摘要，不输出 key、headers、完整 payload、完整 prompt 或财报内容。
- 轻量测试覆盖参数、缺 key、安全输出和不引用 OLD 文件；不做真实联网。

直接证据：

- smoke docstring：`utils/smoke_async_agent_providers.py:1`
- provider case 常量：`utils/smoke_async_agent_providers.py:112`
- key 进入 request headers 且不输出：`utils/smoke_async_agent_providers.py:204`、`:295`
- 缺 key skip：`utils/smoke_async_agent_providers.py:360`
- DEBUG log：`utils/smoke_async_agent_providers.py:393`
- smoke 测试：`tests/engine/test_smoke_async_agent_providers.py:15`

## 14. Engine README 结论

通过。

`dayu/engine/README.md` 是本轮用户明确要求的 README 例外，内容只描述 Phase 2 当前已落地事实：

- 覆盖 Engine 职责、分层边界、函数式入口、run-scoped Agent、RunnerEvent -> EngineEvent、无工具状态机、取消优先级、Runner close、Runner diagnostics / SSE idle。
- 明确 Host ToolRegistry、ToolExecutor tool calling、awaiting、trace store、transcript、conversation memory、context budget / continuation 尚未落地。
- 未把 Phase 3+ 能力写成可用能力。
- 有测试锁住必要片段与禁止声明。

直接证据：

- README 当前职责：`dayu/engine/README.md:11`
- README 不负责范围：`dayu/engine/README.md:22`
- README 状态机：`dayu/engine/README.md:81`
- README 取消优先级：`dayu/engine/README.md:95`
- README 测试：`tests/engine/test_engine_readme_phase2.py:18`

## 15. 阻塞问题

无。

## 16. 重要问题

无。

## 17. 建议问题

### S1. Agent 层缺少外层 `asyncio.CancelledError` 透传与 close 的直接测试

- NEW 文件路径：`dayu/engine/agent.py:263`、`dayu/engine/agent.py:180`；测试缺口位于 `tests/engine/test_agent_phase2.py`。
- OLD 直接证据路径：`/Users/leo/workspace/dayu-agent/tests/engine/test_async_agent.py:1393` 覆盖 Runner mid-stream cancelled 后不产 final；`/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner_call_paths.py:607` 与 `/Users/leo/workspace/dayu-agent/tests/engine/test_sse_parser.py:799` 覆盖外层 task cancel 会清理内部阻塞任务。
- 触发场景：消费 `run_agent_messages()` / `_AsyncAgent.run_messages()` 时，外层 task 被 `task.cancel()` 取消，或 fake Runner 在流中抛出 `asyncio.CancelledError`。
- 实际行为：NEW 代码在 `_run_once()` 中 `except asyncio.CancelledError: raise`，`run_messages()` finally 仍会 `_close_runner_once()`；实现看起来正确。
- 预期语义：外层 `asyncio.CancelledError` 必须原样透传，不被收口成普通 `run_cancelled` / `run_failed`，同时 Runner close 必须执行。
- 影响：当前实现可靠，但缺少 Agent 层测试锁定。未来若有人把 `asyncio.CancelledError` 误捕获进普通 `Exception` 收口，现有 Phase 2 Agent 测试不一定能及时发现。
- 建议修复方向：新增一个无联网测试，例如 fake Runner 首个事件后阻塞，启动消费 task 后 `task.cancel()`，断言 `pytest.raises(asyncio.CancelledError)`、`runner.close_count == 1`、未收集到 terminal；另加 Runner 直接抛 `asyncio.CancelledError` 的路径也可。

## 18. 测试与 pyright 结果

已运行：

```bash
source .venv/bin/activate && pytest tests/runtime tests/contracts tests/engine -q
```

结果：

```text
281 passed in 1.06s
```

已运行：

```bash
source .venv/bin/activate && pyright
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

## 19. 总体验收判断

验收通过。

NEW Phase 2 在当前 contracts 下正确复现了 OLD AsyncAgent 的无工具核心状态机可靠语义：run slot、RunnerEvent 消费、final / failed / cancelled 收口、取消优先级、Runner close finally、terminal 唯一、sequence 单调与 tool boundary 均成立。

与 OLD 不一致的部分均属于 Phase 2 明确重设或不迁移范围：ToolRegistry / tool execution / trace / transcript / memory / context budget / continuation 不迁；`length` 不 continuation；公共 cancellation token 取消以结构化 `run_cancelled` 收口；HTTP error 细节按 NEW contract 收窄，不塞 metadata。上述重设已由实现、README 与测试覆盖。
