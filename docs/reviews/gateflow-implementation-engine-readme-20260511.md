# Gateflow Implementation Artifact: Engine README Phase 2

- work gate name: implementation
- work-unit name: Engine README 开发手册补齐
- assigned slice id: engine-readme-phase2
- approved plan path: 当前 controller handoff prompt
- artifact path: `docs/reviews/gateflow-implementation-engine-readme-20260511.md`

## Assigned Scope

- 允许修改 `dayu/engine/README.md`。
- 允许修改 `tests/engine/test_engine_readme_phase2.py`。
- 允许写入本 implementation artifact。
- 不触碰 `AGENTS.md` / `CLAUDE.md`。
- 不修改代码契约文件。
- 不进入 commit / PR / closeout。

## Changed Files

- `dayu/engine/README.md`
  - 移除 `AgentRunRequest` 接口章节中对请求级 `stream` 字段的说明。
  - 在接口章节之后补齐公共契约、架构、边界、执行路径、状态机、事件流、关键机制、扩展点。
  - 使用当前 EngineEvent 新命名：`content_delta`、`reasoning_delta`、`content_completed`、`usage_reported`、`iteration_completed`。
  - 保留 RunnerEvent 层 `runner_*` / `runner_done` 命名说明。
  - 覆盖 `tool_awaiting`，并说明当前执行路径遇到 awaiting outcome 时 fail closed。
  - 避免把 Host 具体实现、id / cursor 生成、持久化和去重策略写成 Engine 前提。
- `tests/engine/test_engine_readme_phase2.py`
  - 增加 `tool_awaiting` 必备片段。
  - 增加接口之后开发手册章节与关键事实覆盖。
  - 增加对请求级 stream 表述、私有实现 import、事件序号、外层取消表述和 Host id 生成建议的禁止片段。

## Plan Items Implemented

- 公共契约：覆盖 `AgentRunRequest`、`AgentRunResult`、`EngineEvent` / `EngineEventData`、`RunnerEvent`、`AsyncRunner`、`ToolExecutor` 的归属与非归属。
- 架构：说明 contracts、Agent 协调层、runners 的关系，并区分 RunnerEvent 与 EngineEvent。
- 边界：说明 Engine 不负责工具治理、上层生命周期治理、持久化、trace、conversation memory、财报存取。
- 执行路径：说明 `run_agent_messages`、Runner call、RunnerEvent 提升、tool loop、terminal 以及 `run_agent_and_wait` 的终态消费。
- 状态机：说明 iteration、tool calls、final answer、failed / cancelled / suspended 终态，并明确 `iteration_completed` 不是 run terminal。
- 事件流：列出当前 EngineEventType 和 RunnerEventType，并说明顺序由异步流产出顺序定义。
- 关键机制：覆盖取消 token 收口、工具执行协议、provider protocol / HTTP error、context overflow 事件、Runner close 收尾、metadata 边界。
- 扩展点：覆盖新增 Runner、公共事件、provider 参数和工具能力的扩展入口。

## Validation

- `source .venv/bin/activate && pytest tests/engine/test_engine_readme_phase2.py -q`
  - result: passed, 4 tests passed.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result: passed, 0 errors / 0 warnings / 0 informations.
- `git diff --check`
  - result: passed, no whitespace errors reported.

## Documentation Decision

- 本 slice 是 `dayu/engine/README.md` 文档补齐任务，触发并完成 Engine README 同步。
- 未更新其它 README：本次未修改 `dayu/host/`、`dayu/fins/`、`dayu/config/`、CLI、render、utils 使用入口或全局分层装配说明。

## Plan Gaps Or Controller Decisions Needed

- 无阻塞缺口。

## Residual Risks And Uncovered Areas

- risk: 另一个 worker 正在删除 `AgentRunRequest.stream` 字段；本次已按确认决策从 README 中移除请求级 stream 表述，但代码契约文件仍由另一个 worker 负责。
  - classification: assigned to parallel work in the same work unit.
- risk: README 对 `tool_awaiting` 写为公共事件契约并记录当前执行路径 fail closed；若后续 implementation 改为真实挂起路径，需要同步更新状态机说明与测试。
  - classification: later phase / later implementation slice if awaiting execution semantics change.

## Completion Signal

- 指定 README 章节已补齐。
- 指定测试已更新。
- 指定验证命令已通过。
- stop condition status: implementation slice complete; ready for code review gate.
