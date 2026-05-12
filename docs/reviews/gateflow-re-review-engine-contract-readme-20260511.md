# Gateflow Re-review: Engine Contract README

- **review gate name**: re-review
- **reviewed target**: 当前 workspace 未提交改动；重点复核 accepted findings F1/F2 的 fix、README implementation、R1 不回流约束
- **review date**: 2026-05-11
- **reviewer conclusion**: fixed
- **artifact path**: `docs/reviews/gateflow-re-review-engine-contract-readme-20260511.md`

## 结论

F1 fixed。`AgentRunRequest` 的 request-level `stream` 字段、docstring 参数说明和已检查构造器调用均已删除；`RunnerCallOptions.stream` 仍保留，并作为 provider 调用流式控制真源。

F2 fixed。`dayu/engine/README.md` 已包含接口、公共契约、架构、边界、执行路径、状态机、事件流、关键机制、扩展点章节；README 测试覆盖 `tool_awaiting`、新增章节和 forbidden fragments。

R1 未回流。未发现 README/design 恢复 `event_id` / `sequence` 公共契约，也未发现“Host 应该生成”这类 id/cursor 生成建议。

## Accepted Finding Re-review

### F1: `AgentRunRequest.stream` 双真源

- **status**: fixed
- **证据**:
  - `dayu/engine/contracts/agent_run.py:58` 到 `dayu/engine/contracts/agent_run.py:85` 的 `AgentRunRequest` 字段集合不再包含 `stream`，docstring 也不再包含 `:param stream`。
  - `tests/engine/test_agent_phase2.py:256` 到 `tests/engine/test_agent_phase2.py:281` 构造 `AgentRunRequest` 时未传 request-level `stream`，流式开关进入 `RunnerCallOptions(stream=True)`。
  - `tests/engine/test_agent_phase3_tool_call.py:492` 到 `tests/engine/test_agent_phase3_tool_call.py:515` 同样只通过 `RunnerCallOptions.stream` 控制流式。
  - `utils/smoke_async_agent_providers.py:267` 到 `utils/smoke_async_agent_providers.py:280` 保留 CLI `--stream` 入参，但写入 `RunnerCallOptions(stream=stream)`，没有写入 `AgentRunRequest`。
  - 指定 `rg` 检索未命中生产代码或构造器中的 `AgentRunRequest.stream`；唯一 `AgentRunRequest.stream` 命中来自 `tests/engine/test_engine_readme_phase2.py:134` 的 README forbidden fragment。
- **判断**: request-level `stream` 已从公共 request 契约和已检查调用点删除；未发现兼容 wrapper 或双真源残留。

### F2: Engine README 章节与 README 测试覆盖

- **status**: fixed
- **证据**:
  - `dayu/engine/README.md:143` 到 `dayu/engine/README.md:260` 覆盖 `## 公共契约`、`## 架构`、`## 边界`、`## 执行路径`、`## 状态机`、`## 事件流`、`## 关键机制`、`## 扩展点`。
  - `dayu/engine/README.md:147` 明确 Runner 是否流式输出只由 `RunnerCallOptions.stream` 表达。
  - `dayu/engine/README.md:179` 明确 Engine 不规定 `session_id`、`run_id`、provider request id、工具调用 id 等标识的生成、持久化或去重方式。
  - `dayu/engine/README.md:200` 覆盖 `ToolAwaitingOutcome`、`tool_awaiting` 与当前 awaiting fail-closed 事实。
  - `dayu/engine/README.md:224` 明确 EngineEvent 不提供事件序号字段、持久化游标或幂等键。
  - `tests/engine/test_engine_readme_phase2.py:94` 到 `tests/engine/test_engine_readme_phase2.py:125` 覆盖新章节、`RunnerCallOptions.stream`、`tool_awaiting` 与关键机制说明。
  - `tests/engine/test_engine_readme_phase2.py:128` 到 `tests/engine/test_engine_readme_phase2.py:145` 设置 forbidden fragments，覆盖 `AgentRunRequest.stream`、`event_id`、`sequence`、`asyncio.CancelledError`、外层 task / 承载协程语义和 “Host 应该生成”。
- **判断**: README implementation 满足当前要求；测试不是只覆盖章节名，也覆盖了 F1/R1 的关键回流风险。

## R1 Regression Check

- **status**: no regression found
- **证据**:
  - `dayu/engine/contracts/engine_events.py:300` 到 `dayu/engine/contracts/engine_events.py:315` 的 `EngineEvent` 字段从 `occurred_at`、`session_id`、`run_id`、`type`、`data`、`metadata` 开始，不含 `event_id` / `sequence`。
  - `docs/engine/design.md:481` 到 `docs/engine/design.md:487` 明确 EngineEvent 不提供事件 id、事件序号、持久化游标或幂等写入键。
  - forbidden-fragment 检索中，`event_id`、`sequence`、`Host 应该生成` 只出现在 `tests/engine/test_engine_readme_phase2.py` 的 forbidden list。
- **判断**: 没有恢复 Engine 侧 event id / sequence，也没有把 Host id/cursor 生成方案写回 Engine README/design。

## Docs/design Stream Consistency

- **status**: fixed
- **证据**:
  - `docs/engine/design.md:668` 到 `docs/engine/design.md:676` 的 `AgentRunRequest` 建议字段不包含 `stream`。
  - `docs/engine/design.md:478` 到 `docs/engine/design.md:520` 的 EngineEvent 与 RunnerEvent 契约已移除 `event_id` / `sequence`，并保留 `tool_awaiting` 事件 data 草案。
  - `docs/engine/design.md:359` 到 `docs/engine/design.md:376` 仍出现 `stream=True`，但该段标题为 OLD Runner 协议，是历史证据，不是当前 NEW contract。
- **判断**: 未发现因删除 `AgentRunRequest.stream` 产生的 docs/design 与代码契约冲突。

## Validation

- `rg -n "AgentRunRequest.stream|stream: bool|:param stream|AgentRunRequest\([^\)]*stream" dayu/engine tests/engine utils/smoke_async_agent_providers.py docs/engine/design.md dayu/engine/README.md`
  - 结果：未发现 request-level `AgentRunRequest.stream` 或构造器传 `stream=`；命中项为 Runner/工具 smoke 参数、OLD Runner 协议说明、`RunnerCallOptions.stream` 及 README forbidden fragment。
- `source .venv/bin/activate && pytest tests/engine -q`
  - 结果：301 passed in 1.06s。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：0 errors, 0 warnings, 0 informations。
- `git diff --check`
  - 结果：通过。

## Findings

无 blocker findings。

## Open Questions And Residual Risk

- `docs/engine/design.md` 仍保留 OLD 协议片段作为迁移设计证据；本次复核未将这些 OLD 片段视作当前接口契约。若后续要求 design 文档完全只保留当前实现事实，需要单独裁剪历史设计章节。
- 本次 re-review 未进入 commit、PR 或 closeout gate。
