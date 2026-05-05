# Phase 2 Agent Run Loop 骨架实施计划 Review

## 1. Review 结论：通过

`docs/engine/phase2-plan.md` 当前可以作为 Phase 2 AsyncAgent / Agent run loop 骨架的实施计划。

上一轮 review 的两个阻塞问题已经修复：

1. `docs/engine/migration-plan.md` 已同步 Phase 2 README 例外：Phase 2 必须新建 `dayu/engine/README.md`，且除该文件与必要的 `tests/README.md` 外不修改其它 README。
2. `docs/engine/phase2-plan.md` 已补齐 `RunnerDoneData(FinishReason.ERROR)` 且无先前 HTTP / protocol error 时的收口规则：必须 `run_failed("runner_error_done_without_detail")`，不得进入 final answer、missing-terminal 或无 terminal 分支。

计划也已明确 HTTP error 观测事实在 Phase 2 是当前 contract 下的有意收窄，不塞 metadata；若总控要求 Host 可观察完整 HTTP 细节，必须先回到 EngineEvent contract 设计。`RunCancelledData.finished_at` 也已改为 Runner close 尝试完成后的时间，和 contract “实际收尾完成时间”对齐。

## 2. 阅读范围

已复审 NEW：

- `AGENTS.md`
- `CLAUDE.md`
- `docs/engine/design.md`
- `docs/engine/migration-plan.md`
- `docs/engine/phase2-plan.md`
- `docs/engine/phase1_5-plan.md`
- `docs/engine/phase1_5-code-review.md`
- `docs/code_review.md`
- `tests/README.md`
- `dayu/contracts/`
- `dayu/engine/contracts/`
- `dayu/engine/runners/openai/`
- `dayu/runtime/`
- `tests/contracts/`
- `tests/engine/`
- `tests/runtime/`

已复核 OLD 强参考源：

- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/cancellation.py`
- `/Users/leo/workspace/dayu-agent/dayu/engine/README.md`
- `/Users/leo/workspace/dayu-agent/dayu/config/llm_models.json`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_agent.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_async_openai_runner_call_paths.py`
- `/Users/leo/workspace/dayu-agent/tests/engine/test_sse_parser.py`

当前工作区事实：

- `docs/engine/migration-plan.md` 有未提交修改。
- `docs/engine/phase2-plan.md` 是未跟踪文件。
- 本 review 按当前工作区内容审查。

## 3. OLD AsyncAgent 强参考审查

通过。

`phase2-plan.md` 对 OLD `AsyncAgent` 的可靠状态机吸收充分，不是泛泛引用：

- OLD `_acquire_run_slot()` / `_release_run_slot()` 的同实例并发 fail-fast 已映射为私有 `_AsyncAgent` 并发保护与测试。
- OLD `run_messages()` 的 run-scoped `finally` close 已映射为 success / failure / cancellation 都执行 Runner close。
- OLD 每轮 iteration 起点与 final answer 前取消检查已映射到 NEW `run_cancelled` 优先规则。
- OLD Runner mid-stream cancellation 不产出 final answer 的测试事实，已映射为 Runner 自然终止且无 `RunnerDoneData` 时 Agent 收口 `run_cancelled`。
- OLD `content_filter` 不续写、保留 partial final 且 filtered 的语义已保留。
- OLD max iteration / force-answer fallback 被明确识别为 Phase 2 不迁项。
- OLD 工具 loop、ToolRegistry、trace、transcript、memory、context budget、continuation 均未误迁。

## 4. Phase 2 范围审查

通过。

Phase 2 被正确限定为无工具主链路：

- `run_agent_messages` / `run_agent_and_wait`。
- run-scoped Agent。
- RunnerEvent -> EngineEvent 提升。
- `final_answer` / `run_failed` / `run_cancelled` terminal 收口。
- Runner close。
- `utils/smoke_async_agent_providers.py` 手动 smoke 脚本。
- `dayu/engine/README.md` 当前事实手册。

禁止项清楚：ToolExecutor tool calling 闭环、awaiting / long-running tool waiting、ToolRegistry、doc/web/fins tools、trace store、transcript、conversation memory、context budget / continuation 都被排除。

## 5. 接口边界审查

通过。

公共入口符合 Host -> Engine 稳定依赖表面：

- `run_agent_messages(request) -> AsyncIterator[EngineEvent]`
- `run_agent_and_wait(request) -> AgentRunResult`

边界策略明确：

- Host 只依赖函数式入口与 contracts。
- `_AsyncAgent` 是私有实现，不进包根。
- `AsyncOpenAIRunner` 仍不从 `dayu.engine` 包根导出。
- Phase 2 不引入 runner registry / 插件机制，只私有构造当前 OpenAI-compatible Runner。
- `dayu.engine.__all__` 只新增两个真实函数式入口，不新增实现类、取消异常或兼容 wrapper。

## 6. Agent 状态机审查

通过。

计划已经展开：

- run start。
- iteration start。
- Runner call。
- RunnerEvent -> EngineEvent 提升。
- content delta / reasoning delta / usage / runner_done 消费。
- final_answer。
- run_failed。
- run_cancelled。
- cancellation before run。
- cancellation during runner call。
- cancellation before final_answer。
- abnormal runner termination。
- max iteration exceeded。
- `RUNNER_DONE(ERROR)` bare error done。
- terminal event 唯一。
- sequence 单调。
- event_id 生成。
- Runner close finally。

关键判断均成立：

- 取消优先于 final answer。
- 取消优先于 failure terminal。
- Runner 因取消自然终止且无 `RunnerDoneData` 时可无歧义收口为 `run_cancelled`。
- close error 不覆盖已确定业务终态。
- 同一 Agent 实例并发 fail-fast 虽然函数式入口每次创建 run-scoped Agent，但作为私有状态机防御仍有意义，计划也说明了测试构造方式。

## 7. RunnerEvent 消费边界审查

通过。

Phase 2 推荐传空 `tools`，即使 request 中有 `tool_schemas` 也不暴露给模型，符合无工具主链路范围。

工具事件处理正确：

- `RUNNER_TOOL_CALL_DELTA` / `RUNNER_TOOL_CALLS_COMPLETED` 立即 `run_failed("tool_call_not_supported_in_phase2")`。
- 不调用 `ToolExecutor`。
- 不产出 `ToolCallRequestedData`。
- 不把 tool call 伪装成 final answer。
- OLD 工具 loop 被明确放到 Phase 3。

## 8. 取消边界审查

通过。

计划已明确：

- 取消公共终态用 `RunCancelledData` / `EngineRunOutcomeCancelled` 表达，不暴露公共取消异常。
- run start 前、iteration 起点、Runner stream 自然结束无 done、final answer 前、failure terminal 前都观察取消。
- `RunCancelledData.accepted_at` 表示 Engine 观察并接受 Host 取消的时间。
- `RunCancelledData.finished_at` 表示 Engine 完成取消收尾的时间；Phase 2 以 Runner close 尝试结束后的时间为准。
- cancellation terminal 前先 close Runner；finally 中 close 必须幂等。
- close 失败只记日志，不把取消降级成 `run_failed`。
- 外层 `asyncio.CancelledError` 仍透传。

这个设计比上一版更复杂一点，但它解决了 `finished_at` 与 close 时序的语义冲突，可以作为实施约束。

## 9. 错误与 finish reason 审查

通过。

计划覆盖：

- `RunnerHTTPErrorData` -> `RunFailedData`。
- `RunnerProtocolErrorData` -> `ProviderProtocolErrorData` + `RunFailedData`。
- `RunnerDoneData(FinishReason.ERROR)` 无详情 -> `run_failed("runner_error_done_without_detail")`。
- `FinishReason.CONTENT_FILTER` -> `final_answer(filtered=True)`，不 continuation。
- `FinishReason.LENGTH` -> Phase 2 直接 final answer，不 continuation。
- `FinishReason.TOOL_CALLS` -> `run_failed("tool_call_not_supported_in_phase2")`。
- runner abnormal stop -> `run_failed("runner_abnormal_stop")`。
- max iteration exceeded -> `run_failed`。
- close error 不覆盖 terminal。

HTTP error 观测事实的处理已经明确为当前 contract 限制下的有意收窄：`http_status`、`provider_request_id`、`raw_payload`、`attempt`、`retried` 暂不进入 EngineEvent data，也不得塞进 metadata。若总控要求完整可观察性，计划要求停止并先做 contract 变更设计，这符合架构纪律。

## 10. smoke 脚本计划审查

通过。

`utils/smoke_async_agent_providers.py` 计划满足要求：

- 仅人工验证，不放入 `dayu/`。
- 不纳入常规真实联网 pytest。
- provider case 可参考 OLD `llm_models.json` 后写死少量非敏感配置。
- 运行时不依赖 OLD 文件。
- API key 只从环境变量读取。
- 使用 `dayu.runtime.log.configure(level=LogLevel.DEBUG)`。
- 缺 key 友好跳过。
- 禁止输出 key、headers、完整 payload、完整 prompt、财报内容。
- 有轻量无网络测试覆盖参数 / 缺 key / 不读取 OLD 文件 / 安全输出。
- 已补 sentinel 测试要求，覆盖 prompt / header / payload 泄漏风险。

## 11. `dayu/engine/README.md` 计划审查

通过。

`migration-plan.md` 与 `phase2-plan.md` 现在一致要求 Phase 2 实施完成后新建：

- `dayu/engine/README.md`

README 只写当前 Phase 2 已落地事实：

- Engine 当前职责边界。
- `UI -> Service -> Host -> Engine`。
- Host 与 Engine 稳定依赖表面。
- `run_agent_messages` / `run_agent_and_wait`。
- run-scoped Agent 生命周期。
- RunnerEvent -> EngineEvent。
- 无工具主链路状态机。
- `final_answer` / `run_failed` / `run_cancelled`。
- cancellation 优先级。
- Runner close。
- OpenAI-compatible Runner 当前定位。
- Runner diagnostics / SSE idle timeout 当前定位。

也明确禁止把以下未落地内容写成可用能力：

- ToolExecutor tool calling 闭环。
- awaiting / long-running tool waiting。
- Host ToolRegistry。
- trace store。
- transcript 持久化。
- conversation memory。
- context budget / continuation。

## 12. 测试计划审查

通过。

计划覆盖必测项：

- 函数式入口导出。
- 包根导出边界。
- 无工具成功 run。
- RunnerEvent 提升为 EngineEvent。
- content delta / reasoning delta / usage / runner_done 顺序。
- final_answer 只由 Agent 产生。
- protocol error / HTTP error / bare error done / ordinary exception -> run_failed。
- cancellation token 已取消 -> run_cancelled。
- Runner 取消自然终止无 done -> run_cancelled。
- final_answer 前取消 -> run_cancelled 优先。
- provider error 与取消同时出现 -> run_cancelled 优先。
- Runner close 在 success / failure / cancellation 中执行。
- close error 不覆盖 terminal。
- cancellation terminal `finished_at` 晚于或等于 Runner close 尝试完成时间。
- event_id 唯一。
- sequence 单调。
- terminal event 唯一。
- 私有 Agent 实例并发 fail-fast。
- `run_agent_and_wait` 映射 final / failed / cancelled。
- `RUN_SUSPENDED` 不作为 Phase 2 可用能力。
- import boundary。
- Runner 仍只产出 RunnerEvent。
- tool call fail closed。
- smoke 脚本缺 key / 参数 / 安全输出。
- `FinishReason.LENGTH` 不消费 `AgentPolicy.continuation_max_attempts`。
- `dayu/engine/README.md` 只写当前事实。
- OLD AsyncAgent 关键可靠语义有对应 NEW 测试或明确说明 Phase 2 不覆盖。

## 13. pyright / 类型边界审查

通过。

计划明确：

- Agent loop 内部状态完整类型化。
- EngineEvent data 不用裸 dict。
- 不使用 `Any` / `object` / 裸 dict 状态袋。
- RunnerEvent -> EngineEvent 用封闭联合消费。
- `run_agent_and_wait` 返回 `AgentRunResult` 封闭联合。
- smoke 脚本若被 pyright 扫描，也必须类型完整。
- 不用 `getattr` / `hasattr` 逃避边界设计。
- 不引入 god object / god function。

## 14. README 策略审查

通过。

当前策略为：

- Phase 2 必须新建 `dayu/engine/README.md`，这是用户明确要求的例外。
- 如果新增 `tests/utils/` 或测试分层 / 运行方式变化，允许更新 `tests/README.md`。
- 除 `dayu/engine/README.md` 与必要的 `tests/README.md` 外，不修改其它 README。
- 其它 README 仍交给 Phase 6 或后续触发条件处理。

`migration-plan.md` 与 `phase2-plan.md` 已一致。

## 15. 阻塞问题

无。

上一轮阻塞项已修复：

- B1：`migration-plan.md` Phase 2 README 策略已同步 `dayu/engine/README.md` 例外。
- B2：`RUNNER_DONE(ERROR)` 无错误详情分支已明确收口为 `run_failed("runner_error_done_without_detail")`，并加入测试计划。

## 16. 重要问题

无。

上一轮重要项已处理：

- HTTP error 观测事实：计划已明确为 Phase 2 contract 限制下的有意收窄，并禁止塞 metadata；如需完整可观察性，触发 contract 设计停止条件。
- `RunCancelledData.finished_at`：计划已改为 close 尝试完成后的时间。
- `RUN_SUSPENDED`：计划已明确 Phase 2 不产出、不写成可用能力；意外出现只走防御性失败或内部协议错误。

## 17. 建议问题

### S1-低-取消路径 close-before-terminal 实现需要避免 finally 里重复 close 产生噪声

- **文件路径**：`docs/engine/phase2-plan.md`
- **具体章节或符号**：§3.9、§3.10、§3.11、§3.15
- **问题原因**：计划要求 cancellation terminal 前先 close Runner，同时 finally 中仍必须 close 且幂等。
- **影响**：如果实现没有本地 `_runner_closed` 标记或 Runner close 幂等测试不足，可能出现重复 close 日志噪声；按当前计划不影响 terminal 正确性。
- **建议修改方向**：实现时用私有 `_close_runner_once()` helper 统一 close，内部记录 close 尝试完成时间，finally 调同一 helper，测试覆盖 close 只产生一次有效底层 close 或二次 close 幂等。

### S2-低-HTTP error 观测事实收窄建议在 PR 说明中再次提醒

- **文件路径**：`docs/engine/phase2-plan.md`
- **具体章节或符号**：§3.5、§6.1
- **问题原因**：Phase 2 不新增 EngineEvent contract 是合理收窄，但 Host 可观察性会少于 RunnerEvent 原始事实。
- **影响**：非阻塞，属于后续可观察性取舍。
- **建议修改方向**：Phase 2 PR 说明中显式写明 HTTP detail 暂不提升；若后续需要，将单独走 EngineEvent contract 变更。

## 18. 需要总控 / 用户确认的问题

1. 是否接受 Phase 2 暂不提升完整 `RunnerHTTPErrorData` 观测细节，只通过 `RunFailedData` 暴露压缩后的失败事实。
2. 是否接受 cancellation terminal 前先 close Runner，以保证 `RunCancelledData.finished_at` 表示实际取消收尾完成时间；实现上通过 `_close_runner_once()` 避免重复 close 噪声。

这两个问题不阻塞计划实施，但建议总控在进入实现前确认。

## 19. 总体验收判断

Phase 2 计划建议通过，可以进入实现准备。

实施门禁仍需严格执行：

- 先完成代码、测试、pyright、`dayu/engine/README.md` 与必要 `tests/README.md`。
- 常规 code review 通过。
- 再做一轮 NEW / OLD AsyncAgent 与 Runner 消费边界严格实现代码对照 review。
- 严格对照 review 通过后，Phase 2 才能提交 / PR。
