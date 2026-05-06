# Phase 5 with Phase 6 Doc Closeout 计划

## 1. 文档状态

本文是 Phase 5 的 handoff 级实施计划。后续实施 Agent 应能按本文直接接手实现、测试、review 与验收。

本文只规划 Phase 5，不实施代码。Phase 5 合并原 Phase 5 与 Phase 6：原 Phase 6 不再作为第二个实现阶段，只作为 Phase 5 PR 末尾的 README / docs / issue 验收收口部分。

## 2. 最新总控决策

- Phase 5 和原 Phase 6 合并为一个 PR，命名口径建议为 `Phase 5 with Phase 6 doc closeout`。
- Phase 4 已取消独立实施，`suspend` / `run_suspended` / `ToolAwaitingOutcome` 转入 GitHub issue #4，并由后续子 issue 重新计划。
- 本轮 Engine 迁移不把 context overflow / `context_compaction_requested` 纳入范围；后续在实施 Host 上下文治理时，再作为独立 issue 完善 Engine 协作事件与状态机。
- Phase 5 不以 Phase 4 为前置，不实现 `run_suspended`，不实现 Host wait record / monitor / resume。
- Phase 5 不实现 Engine 内 compact / retry，不实现 conversation memory / transcript / trace store。
- OLD `TruncationManager` / fetch_more / cursor / TTL / scope token / tool-level truncation manager 后移 Host / ToolRuntime，不进入 Phase 5。
- README 不在计划阶段更新；Phase 5 实现和 review 通过后，作为同一 PR 的文档收口部分更新当前事实。

## 3. 动机判断

动机成立，但范围必须收窄。

Phase 3 已完成普通 tool calling、max_iterations force-answer、连续失败工具批次保护、取消优先主线和 Runner close。剩余可在 Engine-only 范围内自洽落地的 OLD Agent / AsyncAgent 主能力，主要是 `finish_reason=length` continuation。

context overflow、context compaction trigger、`context_compaction_requested` 和 Host 重新构造上下文是 Engine / Host 协作问题。当前没有 Host conversation memory / transcript / re-run 治理入口，若在本轮只做 Engine 侧半截事件，会制造不可闭合能力。因此这些能力本轮不实现，只保留为后续 issue / Host 实施时完善 Engine 的边界记录。

## 4. 目标

Phase 5 必须实现：

- `finish_reason=length` 触发受次数限制的 continuation，最终回答拼接多轮 partial content。
- continuation 轮 Runner 调用固定 `tools=()`，不进入普通 tool loop。
- continuation 轮如果模型仍返回 tool calls，收口为 `run_failed(error_code="continuation_tool_call_not_allowed", recoverable=False)`，且不得执行工具。
- `content_filter` 不触发 continuation，保持 `filtered=True, degraded=True` 的 final answer。
- continuation 过程中取消优先于继续调用 Runner、final_answer 和 run_failed。
- Phase 3 已落地的 max_iterations force-answer、连续失败工具批次和普通 tool calling 回归不退化。
- 普通 provider error、HTTP retry exhausted、Runner protocol error 仍按 Phase 2/3 既有 `run_failed` 路径收口；Phase 5 不新增开放式 provider fallback 或降级策略。
- 实现和 review 通过后，在同一 PR 做 README / docs / issue 收口。

## 5. 非目标

Phase 5 禁止实现：

- provider context overflow 强类型识别。
- `context_compaction_requested` 事件生产路径。
- `context_compaction_required` recoverable failure 状态机。
- `context_compaction_trigger_ratio`、`max_context_tokens`、trigger ratio 或 projected context early stop 策略入口。
- Engine 内 compact / retry。
- Engine 级工具结果 capping、soft / hard 双阈值治理、裁剪到 soft target。
- Host wait record、monitor、resume、approval、detached、retry_after、artifact_ready。
- `ToolAwaitingOutcome`、`tool_awaiting`、`run_suspended` 或新的 resume API。
- conversation memory、语义压缩、transcript 持久化、trace store、audit / metrics / observer。
- ToolRegistry / ToolRuntime、权限、审计、路径白名单、工具超时治理。
- OLD `TruncationManager`、fetch_more、cursor、TTL、scope token、tool-level truncation manager。
- DuplicateCallGuard 语义级重复调用策略。
- provider-specific reasoning roundtrip patch。
- Runner response cleanup hardening。
- doc / web / fins 工具实现，或绕过 `dayu.fins.storage` 的财报文件读取。

若实施中发现必须新增以上能力才能完成 Phase 5，必须停止并向总控汇报。

## 6. 前置条件

- Phase 3 普通 completed / failed tool calling 主链路已合并。
- Phase 4 已取消并归档为历史草案，不能作为本阶段前置或实施依据。
- `docs/engine/migration-plan.md` 已更新为 Phase 5 + 原 Phase 6 合并口径。
- `docs/engine/design.md` 已声明 context overflow / context compaction 只是后续 Host 协作能力，不是本轮 Engine 目标。
- OLD AsyncAgent / Runner 是本阶段强参考源，但只提供语义证据和可复用片段，不提供 NEW 架构真源。

## 7. OLD 强参考源

实施 Agent 必须阅读 OLD 中以下位置：

- `/Users/leo/workspace/dayu-agent/dayu/engine/async_openai_runner.py`
  - `finish_reason=length` 与 `content_filter` 的 Runner summary 证据。
- `/Users/leo/workspace/dayu-agent/dayu/engine/async_agent.py`
  - continuation prompt。
  - continuation 次数限制。
  - partial content 累积。
  - 取消优先和既有收口场景判断。

实施 Agent 可阅读 OLD context overflow / context budget / truncation 代码作为“本阶段不迁”的边界证据，但不得把这些能力实现进 Phase 5。

## 8. 状态机

### 8.1 continuation

1. Runner 产出 `runner_content_completed(finish_reason=LENGTH, content=partial)` 与 `runner_done(LENGTH)`。
2. Agent 若 `continuation_count < policy.continuation_max_attempts`，把 partial 累积进 final buffer。
3. Agent 追加 continuation prompt 作为下一轮 `UserMessage`。
4. Agent 发起下一轮 Runner 调用，固定传入 `tools=()`。
5. 后续若得到 `STOP`，将所有 partial 与最终 content 按顺序拼接为 `final_answer(degraded=True, finish_reason=STOP)`。
6. 若连续 `LENGTH` 次数达到上限，按 OLD 已验证语义使用已累积内容收口为 `final_answer(degraded=True, finish_reason=LENGTH)`，不再继续调用 Runner，并补测试证明 Runner 调用次数为 `1 + continuation_max_attempts`。

`content_filter` 不走 continuation，保持 Phase 3 语义：`final_answer(filtered=True, degraded=True, finish_reason=CONTENT_FILTER)`。

Phase 5 明确选择比 OLD 更收窄的 continuation 工具策略。OLD `AsyncAgent` 在 `finish_reason=length` 后把截断 assistant content 和 continuation user prompt 追加回主循环，因 Runner 持有工具注册而可能继续暴露工具；NEW Phase 5 把 continuation 定义为“继续当前 assistant final content”的动作，默认禁用工具以避免重新进入普通 tool loop。

因此：

- continuation 轮的 RunnerCall 使用 `tools=()`。
- continuation 轮不调用 ToolExecutor。
- continuation 轮如果 Runner 仍返回 `RUNNER_TOOL_CALLS_COMPLETED`，视为 provider / model 协议违反本轮约束，产出 `run_failed(error_code="continuation_tool_call_not_allowed", recoverable=False)`，且不得执行工具。
- continuation 轮计入 Agent LLM iteration 和 `max_iterations`，但不计入普通工具批次保护。
- continuation 轮开始前、Runner 调用前、terminal 前都必须观察 cancellation。
- continuation 不重写 Phase 3 max_iterations force-answer；如果 continuation 因 max_iterations 耗尽无法继续，按已累积内容产出 degraded final answer，而不是进入 force-answer tool fallback。

### 8.2 context overflow 后移边界

本轮不实现 context overflow / context compaction 状态机。

后续 Host 实施时应重新设计并补齐：

- Runner 是否需要强类型识别 provider context overflow。
- Engine 是否生产 `context_compaction_requested`，以及 data 需要哪些中性事实。
- Host 如何基于 conversation memory、transcript、tool facts 和 session 状态压缩或重构上下文。
- Host 如何重新发起新的 `AgentRunRequest`。
- 取消、失败、重试、幂等和观测事件如何收口。

本轮 Phase 5 不得因为 provider context overflow 增加新 error code、新 EngineEvent 或新 recoverable terminal。

## 9. 契约变化

### 9.1 AgentPolicy

Phase 5 只允许补齐 continuation 所需策略入口。实施 Agent 可微调字段名，但不得改变语义边界：

- `continuation_prompt: str`

已有 `continuation_max_attempts` 必须真正被 Agent 消费。

要求：

- 所有新增字段有默认值和 `__post_init__` 校验。
- 不得加入 context overflow / compaction 字段，例如 `max_context_tokens`、`context_compaction_trigger_ratio`。
- 不得加入 Host-only 字段，例如 cursor TTL、scope token、fetch_more schema、permission、tool timeout。

### 9.2 不新增 context budget contract

Phase 5 不新增 `ContextBudgetState`、trigger ratio helper 或 context overflow error code。若实施 Agent 发现现有 continuation 代码必须依赖这些契约，必须停止并汇报。

## 10. 文件级改动清单

实施 Agent 预计修改：

- `dayu/engine/contracts/agent_policy.py`
  - 增加 continuation prompt 字段或补齐现有 continuation 策略消费。
  - 补齐字段校验和中文 docstring。
- `dayu/engine/agent.py`
  - 实现 `finish_reason=length` continuation、`tools=()` 调用、禁工具协议守卫和内容拼接。
  - 保持取消优先和 Phase 3 回归语义。
- `dayu/engine/__init__.py`
  - 如有新增公共 contract 类型需要包根导出，按现有白名单测试更新；内部 helper 不导出。
- `dayu/engine/README.md`
  - 只在代码 review 通过后的文档收口中更新当前事实。
- `tests/engine/**`
  - 增加 Phase 5 Agent、contract、architecture 回归测试。
- `tests/README.md`
  - 仅当测试分层或运行方式变化时更新。

不得修改：

- `dayu/engine/runners/openai/error_classifier.py`，除非只是修复 continuation 已暴露的现有 bug；不得新增 context overflow 分类。
- `dayu/engine/context_budget.py` 或同等新文件。
- `docs/engine/phase4-plan.md`
- `docs/engine/phase4-plan-review.md`
- `docs/code_review.md`

## 11. 测试清单

### 11.1 continuation

- `finish_reason=LENGTH` 一次后续写，第二轮 `STOP` 时拼接 partial + final。
- 连续多次 `LENGTH` 时受 `continuation_max_attempts` 限制。
- 达到续写上限后以 degraded final answer 收口，并断言 Runner 调用次数为 `1 + continuation_max_attempts`。
- continuation prompt 作为 `UserMessage` 注入，内容来自 `AgentPolicy.continuation_prompt` 或当前默认策略。
- continuation Runner 调用固定 `tools=()`。
- continuation 轮返回 tool calls 时不执行 ToolExecutor，并以 `run_failed(error_code="continuation_tool_call_not_allowed", recoverable=False)` 收口。
- continuation 轮计入 LLM iteration / max_iterations，但不计入普通工具批次保护。
- continuation 因 max_iterations 耗尽无法继续时，以已累积内容产出 degraded final answer，不触发 Phase 3 force-answer。
- `content_filter` 不 continuation。
- continuation 过程中 cancellation 优先于继续调用 Runner、final_answer 和 run_failed。
- continuation 不回退 Phase 3 max_iterations force-answer。

### 11.2 Phase 3 回归

- 普通 add_numbers completed / failed 回归仍通过。
- max_iterations force-answer 默认行为不回退。
- 连续失败工具批次保护不回退。
- 普通 provider error、HTTP retry exhausted、Runner protocol error 既有 `run_failed` 回归通过。
- Runner close 仍执行。

### 11.3 AgentPolicy / contract

- 默认 policy 构造成功。
- `continuation_max_attempts` 非法值被拒绝或保持既有校验补齐。
- continuation prompt 为空或非法时按最终实现规则被拒绝或回落到默认值；规则必须有测试。
- 公共 contract 不出现 `Any`、`object`、无类型参数、无类型返回值。

### 11.4 架构回归

- Engine 不导入 Host / Service / UI。
- Engine 不导入 ToolRegistry / ToolRuntime / OLD TruncationManager。
- Engine 不导入 trace store / transcript / conversation memory。
- Runner 不依赖 ToolExecutor。
- `context_compaction_requested` 未成为 Phase 5 触发路径。
- `run_suspended` 未成为 Phase 5 触发路径。

## 12. 验证命令

实施完成后至少运行：

```bash
source .venv/bin/activate
pytest tests/engine -q
pytest tests/contracts -q
pyright
```

若实现只新增或更新更窄测试文件，可以先运行受影响子集；进入 review 前必须运行上述覆盖范围。

## 13. README / docs 收口

Phase 5 实现、Phase 5 code review、OLD/NEW 专项 review、日常 `docs/code_review.md` review 全部通过后，才进入文档收口。

文档收口必须检查：

- `dayu/engine/README.md`
  - 写入当前已落地的 continuation、取消优先状态机和 Phase 3 回归事实。
  - 明确不写 context overflow / `context_compaction_requested` 已落地。
  - 明确不写 Host wait record / resume、conversation memory、trace store、OLD `TruncationManager` / fetch_more 已可用。
- `tests/README.md`
  - 仅测试分层或运行方式变化时更新。
- `dayu/README.md`
  - 仅整体分层、装配方式或 Host / Engine 边界事实变化时更新。
- `docs/engine/migration-plan.md`
  - Phase 5 完成状态和后续 issue 状态必须与代码事实一致。

不得为了完成文档收口写“未来会支持”。

## 14. Review gate

Phase 5 必须经过以下 gate：

1. Phase 5 plan review。
2. 用户确认 plan review 通过后，才进入实施。
3. Phase 5 code review。
4. OLD/NEW 专项对比 review。
5. 日常 `docs/code_review.md` review。
6. 总控验收 Agent 汇报、diff、测试、pyright、文档收口。
7. 用户确认后才提交 / push / 创建 PR。

OLD/NEW 专项对比 review 范围必须覆盖：

- continuation prompt、`tools=()` 策略、次数限制、内容拼接。
- `content_filter` 不 continuation。
- Phase 3 既有 fallback 回归与取消优先。
- Phase 3 max_iterations force-answer 与连续失败工具批次未回退。

OLD AsyncAgent / Runner 是强参考源，但 review 必须确认 NEW 只对齐“final answer text continuation”的可靠性目标，没有机械迁 OLD context overflow / soft / hard / capping / compact，也没有迁入 Host / ToolRuntime / TruncationManager / transcript / conversation memory。

## 15. 停止条件

实施 Agent 遇到以下情况必须停止：

- 需要实现 context overflow 强类型识别或 `context_compaction_requested` 才能继续。
- 需要实现 Engine 内 compact / retry 才能继续。
- 需要 `run_suspended` 或 resume API 才能继续。
- 需要 Host wait record / monitor / ToolRuntime / ToolRegistry 才能继续。
- 需要 OLD `TruncationManager` / fetch_more / cursor / TTL / scope token 才能继续。
- 需要 conversation memory、语义压缩、transcript 或 trace store 才能继续。
- 需要在 metadata 中塞入显式契约事实。
- 需要用 `Any`、`object`、裸 dict 公共签名逃避类型设计。
- 需要兼容 OLD import path、wrapper、facade 或 re-export 才能测试通过。
- continuation 无法保证取消优先。

## 16. 风险

- continuation 内容拼接容易重复。应参考 OLD prompt，但测试只能要求顺序拼接与不丢内容，不把模型自然语言去重作为确定性义务。
- 禁用 continuation 工具调用是 NEW 的收窄策略，比 OLD 更严格；专项 review 应确认该策略没有破坏 Phase 3 普通 tool loop。
- context overflow 不在本轮处理。真实 provider 若在 Phase 5 smoke 中遇到 context overflow，应记录为后续 issue 证据，不得临时把 compaction 逻辑塞回 Engine。
- Phase 5 完成后可以说 Engine 层主能力进一步接近 OLD Agent / AsyncAgent，但不能宣称 Dayu 全系统能力对齐 OLD。

## 17. 待确认项

实施前建议总控 / 用户确认：

1. `AgentPolicy.continuation_prompt` 是否作为新增字段落地，还是先使用模块级默认 prompt。
2. DuplicateCallGuard 是否单独开后续 issue。
3. provider-specific reasoning roundtrip patch 是否继续保留为 issue #10 后续工作。
4. Runner response cleanup hardening 是否单独作为 hardening issue。
5. context overflow / Host context compaction 协作是否单独创建后续 GitHub issue。

## 18. 实施完成汇报格式

实施 Agent 完成后必须汇报：

- 修改的生产文件、测试文件、README / docs 文件。
- continuation 的 `tools=()` 策略、禁工具协议守卫、次数限制、prompt 注入和内容拼接如何落地。
- 明确未实现 context overflow / `context_compaction_requested` / context trigger ratio。
- 明确未实现 OLD `TruncationManager` / fetch_more / cursor / TTL / scope token。
- 明确未实现 Host wait record / monitor / resume / run_suspended。
- 运行的测试命令和结果。
- pyright 结果。
- README / docs 收口情况。
- 未覆盖风险和后续 issue 建议。
