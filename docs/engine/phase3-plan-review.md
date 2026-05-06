# Phase 3 Plan Blocking 修订复审

## 结论

通过。

Carson 修订后的 `docs/engine/phase3-plan.md` 与 `docs/engine/migration-plan.md` 已收口本轮 Phase 3 blocking 问题，可以进入 Phase 3 实施准备。

本次复审只审查计划文档，不实施代码、不提交、不 push。旧版 `phase3-plan-review.md` 中关于 `max_iterations` 直接 `run_failed` 的历史结论已作废；本文件是针对 Carson blocking 修订后的复审记录。

## Blocking

无。

已确认以下 blocking 均已收口。

### 1. LLM-facing tool result projection

已通过。

- 计划明确禁止把内部 `ToolResultEnvelope` 直接写入 `ToolMessage.content`。
- 计划要求注入 tool message 前必须调用 Engine 内部 LLM-facing projection helper。
- projection 以 OLD `project_for_llm()` 为强参考源：成功 object / dict 展开，成功 scalar / string 包 `content`，失败不带 `ok=false`，`hint=None` 省略，空工具结果仍注入非空占位。
- `truncation` 被限制为只投影 LLM 可执行字段，禁止泄漏内部治理对象、debug 字段、Host policy 或 ToolRuntime 状态。
- `tool_calls_remaining` 在 Phase 3 不作为 blocking 字段纳入 projection，且给出了理由：Phase 3 的轮次预算由 Agent loop 强约束，本阶段不迁 context budget / continuation；若后续要加入，必须从 policy 派生并补测试，经总控确认。

### 2. max_iterations force-answer

已通过。

- 计划明确 `agent_policy.max_iterations` 表示允许携带工具 schema 的普通 Runner 轮次预算。
- 当前允许的最后一轮 tool call 会照常执行并注入结果。
- 默认 `AgentFallbackMode.FORCE_ANSWER` 会追加 `fallback_prompt` 作为 `UserMessage`，调用 Runner 时 `tools=()`，不调用 ToolExecutor，并产出 `final_answer(degraded=True)`。
- `AgentFallbackMode.RAISE_ERROR` 才收口 `run_failed("max_iterations_exceeded")`。
- force-answer Runner 空内容收口 `run_failed("force_answer_empty")`。
- force-answer 前、Runner 流中、final 前均要求 cancellation 优先。

### 3. FinalAnswerData.degraded / content_filter

已通过。

- 计划要求新增 `FinalAnswerData.degraded: bool`。
- force-answer 产出 `final_answer(degraded=True)`。
- content_filter 产出 `final_answer(filtered=True, degraded=True)`。
- 普通 final answer 产出 `final_answer(degraded=False)`。
- 若存在 `EngineRunOutcomeFinalAnswer` 或等价聚合结果，计划要求同步携带 `degraded`，避免事件与聚合结果语义漂移。

### 4. 连续失败工具批次保护

已通过。

- 计划已将连续失败工具批次保护定为 Phase 3 blocking 能力，不后移。
- `AgentPolicy.max_consecutive_failed_tool_batches` 默认参考 OLD 为 2。
- 全 failed 批次计数 +1，任一 completed / success outcome 出现则清零。
- 达阈值后按 `fallback_mode` 收口：`FORCE_ANSWER` 走 UserMessage fallback prompt、Runner `tools=()`、不调用 ToolExecutor、`final_answer(degraded=True)`；`RAISE_ERROR` 走明确 `run_failed` 错误码。
- 计划明确这是 Agent loop 保险，不是 Host ToolRegistry / ToolRuntime 治理。
- cancellation 优先级已纳入 force-answer 前、Runner 流中、final 前检查。

### 5. migration-plan 阶段歧义

已通过。

- `migration-plan.md` Phase 3 已明确包含 max_iterations force-answer 与连续失败工具批次保护。
- Phase 5 已改为 context budget、continuation、broader fallback 与更完整取消收口，不再承接 Phase 3 已固定的 max_iterations force-answer / 连续失败批次保护。
- EngineWorker / ToolExecutor 口径保持一致：EngineWorker 是 Host capability，替 Host 代持并提供 ToolExecutor，不拥有治理权。

## Important

无。

本次额外检查未发现会阻塞实施准备的计划矛盾：

- `phase3-plan.md` 与 `migration-plan.md` 对 Phase 3 / Phase 5 的能力边界一致。
- 计划未把 Host ToolRegistry、ToolRuntime、权限审计、RemoteProxy / RPC、HostEvent / WorkerEvent 或 Issue #10 provider-specific reasoning patch 引入 Phase 3。
- 计划未把 Runner 写回工具执行者；Runner 仍只负责 provider 协议归一。
- `fallback_prompt` role 已写死为 `UserMessage`，没有留下 system / developer / metadata 歧义。

## Suggestion

无必须修改项。

后续实施 Agent 需要注意：`docs/engine/design.md` 是早期设计文档，部分细节不如当前 Phase 3 plan 具体。Phase 3 实施时若修改事件契约和 `AgentPolicy`，应以当前 `phase3-plan.md` 作为直接实施计划，并在实现完成后按实际代码同步必要设计文档或 README。

## 测试计划复审

通过。

当前 `phase3-plan.md` 的测试计划已覆盖本轮 blocking：

- LLM-facing projection：object 展开、scalar/string 包 `content`、failed 不带 `ok`、`hint=None` 省略、空结果非空占位、truncation 不泄漏内部治理对象。
- max_iterations force-answer：最后一轮工具照常执行、fallback prompt 是 `UserMessage`、Runner `tools=()`、force-answer 不调用 ToolExecutor、`degraded=True`、`RAISE_ERROR` 才 `max_iterations_exceeded`、空内容 `force_answer_empty`、取消优先。
- degraded/content_filter：普通 final、force-answer final、content_filter final，以及聚合结果同步 degraded。
- 连续失败工具批次：FORCE_ANSWER / RAISE_ERROR 两条分支、成功批次清零、取消优先。
- 架构边界：Runner 不依赖 ToolExecutor，Engine 不 import Host / ToolRegistry / ToolRuntime / tools。

## 实施判断

可以进入 Phase 3 实施准备。

实施完成后仍必须执行两道 review：

- 常规 `docs/code_review.md` 日常 review。
- NEW / OLD Agent tool calling 严格对照 review，重点对照 OLD `project_for_llm()`、max_iterations force-answer、content_filter degraded、连续失败工具批次保护、取消优先级与 Runner close。

## 本次复审说明

本次已阅读并对照：

- `docs/engine/phase3-plan.md`
- `docs/engine/migration-plan.md`
- `docs/engine/design.md`
- `docs/host/design.md`
- `docs/code_review.md`
- 历史 `docs/engine/phase3-plan-review.md`
- OLD `async_agent.py`、`tool_result.py` 及相关测试中的 force-answer、projection、content_filter、连续失败批次证据

本次未运行测试或 pyright，因为任务是计划 review，未实施代码。
