# Phase 5 Code Review

## 1. 结论

通过。

当前未提交实现严格聚焦 `finish_reason=length` continuation，没有把 context overflow、`context_compaction_requested`、trigger ratio、capping、OLD `TruncationManager` / fetch_more、`run_suspended` 或 Host resume 偷跑进 Phase 5。可以进入下一 gate：OLD/NEW 专项对比 review 与日常 `docs/code_review.md` review。

## 2. Review 范围

本轮审查当前工作区未提交代码改动，主要文件：

- `dayu/engine/agent.py`
- `dayu/engine/contracts/agent_policy.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`

参考文档：

- `AGENTS.md`
- `docs/engine/phase5-plan.md`
- `docs/engine/phase5-plan-review.md` 第 7 节最新版复审结论
- `docs/engine/migration-plan.md`
- `docs/engine/design.md`
- OLD `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py`
- OLD `/Users/leo/workspace/dayu-agent/dayu/engine/async_openai_runner.py`

## 3. Findings

无 blocking。

无 important。

无 suggestion-level 必改项。

## 4. 检查结果

### 4.1 Phase 5 范围

通过。

- 未发现新增 context overflow 强类型识别。
- 未发现新增 `context_compaction_requested` / `context_compaction_required` 生产路径。
- 未发现新增 `max_context_tokens`、trigger ratio、projected context early stop 或 capping。
- 未发现迁入 OLD `TruncationManager`、fetch_more、cursor、TTL、scope token。
- 未发现新增 Host wait record、resume、conversation memory、transcript 或 ToolRuntime 依赖。

`ToolAwaitingOutcome` / `run_suspended` 相关代码仍是 Phase 3 已有的 fail-closed 分支，不是本轮新增能力。

### 4.2 continuation 状态机

通过。

- `AgentPolicy.continuation_max_attempts` 已被 Agent 消费。
- continuation prompt 来自 `AgentPolicy.continuation_prompt`。
- continuation Runner 调用固定传入 `tools=()`。
- continuation 轮返回 tool call 信号时，以 `run_failed(error_code="continuation_tool_call_not_allowed", recoverable=False)` 收口，且测试断言 ToolExecutor 未执行。
- 多轮 partial content 按顺序拼接。
- 达到 continuation 上限或 `max_iterations` 边界时，以 degraded final answer 收口。
- `content_filter` 不触发 continuation。
- cancellation 在进入下一轮 continuation 前优先生效。

NEW 对 OLD 的差异，即 continuation 轮禁用 tools，是计划中明确的收窄设计；实现与测试均按该口径落地。

### 4.3 Phase 3 回归

通过。

现有 Phase 3 测试仍覆盖普通 tool calling、max_iterations force-answer、连续失败工具批次、Runner close、Runner 异常和 provider/protocol error 收口。本轮 targeted 与全量 Engine 测试均通过。

### 4.4 AgentPolicy contract

通过。

`AgentPolicy` 新增 `continuation_prompt` 默认值与空白校验，并补齐 `continuation_max_attempts >= 0` 校验。公共签名保持严格类型；未发现 `Any`、`object`、无类型参数或兼容 wrapper。

### 4.5 测试调整

通过。

`tests/engine/test_agent_phase2.py` 对 LENGTH 的旧断言调整是合理迁移：在 `max_iterations=1` 且无续写预算空间时，LENGTH 以 degraded final 收口，符合 Phase 5 新语义；CONTENT_FILTER 仍不 continuation。

新增 Phase 5 focused tests 覆盖 continuation prompt 注入、`tools=()`、多轮拼接、上限、`max_iterations`、非法 tool call fail-closed、content_filter 和 cancellation。

### 4.6 README / docs 收口

当前不阻塞 code review。

按 Phase 5 plan，README / docs / issue 收口应在 Phase 5 code review、OLD/NEW 专项对比 review、日常 `docs/code_review.md` review 全部通过后由总控安排。实施 Agent 未提前修改 README，符合当前总控范式。

## 5. 验证命令

已运行：

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q
```

结果：43 passed。

```bash
source .venv/bin/activate && pytest tests/engine -q && pytest tests/contracts -q
```

结果：`tests/engine` 286 passed；`tests/contracts` 19 passed。

```bash
source .venv/bin/activate && pyright
```

结果：0 errors, 0 warnings, 0 informations。

```bash
git diff --check
```

结果：通过，无 whitespace 问题。
