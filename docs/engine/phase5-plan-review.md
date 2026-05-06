# Phase 5 Plan Review

## 1. 结论

初审结论：不通过。

上一版复审结论：通过。详见本文第 6 节。

最新版复审结论：通过，可以进入 Phase 5 实施准备。详见本文第 7 节。

第 2 至第 6 节保留历史初审和上一版复审记录。最新版复审以第 7 节为准：当前 Phase 5 计划已把 context overflow / `context_compaction_requested` 整体后移 Host 后续 issue，本轮只实施 `finish_reason=length` continuation，并已达到 handoff 级。

本轮最新版复审只审查计划文档；未修改生产代码、测试代码，未运行 pytest 或 pyright。

## 2. Findings

### Blocking 1. `broader fallback` 是开放式实现项，不满足 handoff 级计划

位置：

- `docs/engine/migration-plan.md:590`
- `docs/engine/migration-plan.md:609`
- `docs/engine/migration-plan.md:650`
- `docs/engine/migration-plan.md:675`
- `docs/engine/phase5-plan.md:44`
- `docs/engine/phase5-plan.md:338-345`

问题：

计划把 `broader fallback` 写入 Phase 5 目标、迁移任务、测试和 review gate，但没有定义它的精确触发源、状态机、AgentPolicy 字段、terminal event、与 Phase 3 既有 `max_iterations force-answer` / 连续失败工具批次 / `content_filter degraded` 的关系。`docs/engine/migration-plan.md:609` 里的“例如 provider error 的结构化失败或降级”尤其开放，会诱导实施 Agent 新增不受约束的 provider error fallback 或降级路径。

后果：

实施 Agent 可能在 context overflow、普通 provider error、HTTP retry exhausted、Runner protocol error 或 fallback mode 之间自行创造分支，导致 Engine 终态语义漂移，也会削弱 OLD/NEW 对比 review 的可判断性。

建议：

二选一：

1. 从 Phase 5 实现范围移除 `broader fallback`，仅要求 Phase 3 已有 fallback 语义回归不退化，并把 OLD/NEW review 中的 fallback 范围限定为既有路径。
2. 若必须保留，则在计划中逐项定义：触发事件、AgentPolicy 字段、事件序列、terminal、取消优先点、测试文件和不做项；禁止使用“例如”作为实现边界。

### Blocking 2. continuation 下一轮是否允许工具调用未固定

位置：

- `docs/engine/migration-plan.md:607`
- `docs/engine/phase5-plan.md:119-128`
- `docs/engine/phase5-plan.md:259-267`

问题：

`migration-plan.md` 写的是“追加 continuation prompt、禁用工具或按计划明确工具策略”，说明总控层已意识到这里必须定策略；但 `phase5-plan.md` 的 continuation 状态机只写“追加 continuation prompt 作为下一轮 `UserMessage`”和“发起下一轮 Runner 调用”，没有说明下一轮 `tools` 参数如何传递、是否允许 tool call、若 continuation 轮再次请求工具应如何处理、是否计入普通 tool loop / max_iterations。

OLD `async_agent.py` 的可靠行为是把截断内容作为 assistant message 追加，再追加 continuation user message，然后回到主循环；NEW 是否完全沿用该语义，还是在 Phase 5 选择禁用工具以收窄行为，必须由计划明确。

后果：

不同实施 Agent 可能分别实现“continuation 禁用工具”“continuation 保留工具”“continuation 请求工具时报错”三种行为。它们都会影响最终回答拼接、tool loop、max_iterations、预算裁剪与取消优先，属于 Agent 状态机核心差异，不能留给实施阶段临场决定。

建议：

在 `phase5-plan.md` 中明确一个唯一策略，并补测试。建议至少写清：

- continuation 下一轮 RunnerCall 使用的 `tools` 集合。
- continuation 轮如果收到 `RUNNER_TOOL_CALLS_COMPLETED` 的处理方式。
- continuation 轮是否计入 `max_iterations`。
- continuation 与 Phase 3 force-answer / consecutive failed tool batches 的优先级。

### Important 1. `context_compaction_requested` 后 terminal 语义正确，但仍被列为待确认

位置：

- `docs/engine/phase5-plan.md:14`
- `docs/engine/phase5-plan.md:34-38`
- `docs/engine/phase5-plan.md:108-117`
- `docs/engine/phase5-plan.md:372-377`

问题：

计划当前采用 `context_compaction_requested -> run_failed(error_code="context_compaction_required", recoverable=True)`，这是在不实现 `run_suspended` / Host wait record / resume 的前提下最保守、也最自洽的 terminal 收口。它避免了非 terminal 事件悬空，也避免把 context overflow 伪装成普通 provider error。

但同一计划又把该 terminal 放在“待确认项”第一条。如果不在实施前明确确认，实施 Agent 可能把它视为未决设计，进而修改为 `run_suspended`、普通 `run_failed(provider_error)` 或只发非终态事件。

后果：

状态机可能失去唯一 terminal，或提前引入 Phase 4 / issue #4 才应处理的 suspend/resume 语义。

建议：

实施前由总控 / 用户明确确认该 terminal。确认后建议把它从“待确认项”改为“已确认总控决策”，或者在待确认项中标注“若用户未再次变更，则按本文 terminal 执行”。

### Important 2. `docs/engine/design.md` 仍保留旧的 compaction / suspended 组合表述

位置：

- `docs/engine/design.md:560-568`
- `docs/engine/phase5-plan.md:66-70`

问题：

`phase5-plan.md` 已明确 Phase 5 不实现 `run_suspended`，但 `docs/engine/design.md:566` 仍写“当 Engine 判断需要语义压缩时，应发出 `context_compaction_requested` / `run_suspended` 事件”。这条是 Phase 4 取消前的旧表述。计划虽然反复排除了 `run_suspended`，但又把 `docs/engine/design.md` 作为前置契约依据，实施 Agent 读到两者冲突时可能误以为设计文档优先。

后果：

Phase 5 实施可能重新把 `run_suspended` 拉回 context overflow 路径，形成用户已经明确取消的半截能力。

建议：

在进入实施前同步更新 `docs/engine/design.md` 的 context budget 段落，明确当前 Phase 5 只使用 `context_compaction_requested + recoverable run_failed`，`run_suspended` 由 issue #4 后续设计。若暂不改 design，则在 `phase5-plan.md` 前置条件中明确“Phase 5 以本计划覆盖 design.md 中旧 run_suspended 表述”。

### Suggestion 1. context overflow 时的 `ContextBudgetSnapshot` 构造源可再写实一点

位置：

- `docs/engine/phase5-plan.md:112`
- `docs/engine/phase5-plan.md:193-197`
- `docs/engine/phase5-plan.md:364-367`

问题：

provider 400 context overflow 通常没有可靠 usage，因此 `ContextCompactionRequestedData.budget_state` 不能总是来自 Runner usage。计划已经提醒优先用 Engine 可确定估算值，但 handoff 文档可以更明确：当没有 provider usage 时，应该用当前 messages 的估算 prompt tokens、`completion_tokens=0`、`total_tokens=prompt_tokens`，或先扩展强类型 snapshot。

后果：

实现可能随手填 `0/0/0`，降低 Host 后续接管时拿到的中性事实质量。

建议：

补一句构造规则：overflow 路径若无 provider usage，`budget_state` 必须来自 Engine context budget helper 对当前 LLM-facing messages 的确定性估算；不得填魔法占位值。

## 3. Handoff 可执行性评价

当前计划已经具备大部分 handoff 要素：

- 阶段合并口径清晰。
- Phase 4 / issue #4 边界清晰。
- OLD `TruncationManager` 后移边界清晰。
- context overflow 强类型识别、recoverable terminal、continuation、预算裁剪、测试范围、review gate、停止条件基本完整。
- README 规则符合“计划阶段不写 README；代码和 review 通过后只写当前事实”的约束。

但两个 blocking 都是状态机入口级歧义，不修复会直接影响实现形态。因此当前不能进入 Phase 5 实施准备。

## 4. 需要总控 / 用户确认的问题

1. 是否确认 `context_compaction_requested` 后当前 terminal 固定为 `run_failed(error_code="context_compaction_required", recoverable=True)`。
2. continuation 下一轮是否保留工具调用能力，还是禁用工具并只要求模型续写最终回答。
3. `broader fallback` 是否移出 Phase 5，仅保留 Phase 3 fallback 回归；若不移出，需要总控给出精确定义。
4. 是否由总控先同步 `docs/engine/design.md` 中旧的 `context_compaction_requested / run_suspended` 表述。

## 5. 本轮修改

新增：

- `docs/engine/phase5-plan-review.md`

未修改：

- `docs/engine/phase5-plan.md`
- `docs/engine/migration-plan.md`
- 生产代码
- 测试代码

## 6. 复审

### 6.1 复审结论

通过，可以进入 Phase 5 实施准备。

Aristotle 修订后的 `docs/engine/migration-plan.md`、`docs/engine/phase5-plan.md` 与 `docs/engine/design.md` 已收口初审 findings。当前计划达到 handoff 级：实施 Agent 可以按文档进入 Phase 5 实施，但仍必须遵守 plan 中的 review gate，代码实现后继续做 Phase 5 code review、OLD/NEW 专项对比 review、日常 `docs/code_review.md` review 和总控验收。

### 6.2 初审 Findings 收口状态

1. `broader fallback` 已收口。
   - `docs/engine/migration-plan.md` 已移除开放式 `broader fallback` 目标，改为“普通 provider error、HTTP retry exhausted、Runner protocol error 仍按 Phase 2/3 既有 `run_failed` 路径收口；Phase 5 不新增开放式 provider fallback 或降级策略”。
   - `docs/engine/phase5-plan.md` 已把普通 provider error、HTTP retry exhausted、Runner protocol error 的新降级 / fallback 策略列为非目标，Phase 5 只做既有路径回归。
   - 初审 Blocking 1 已关闭。

2. continuation 工具策略已固定。
   - `docs/engine/phase5-plan.md` 明确 continuation 下一轮 Runner 调用固定 `tools=()`，不调用 ToolExecutor。
   - 若 continuation 轮仍返回 tool calls，按 `run_failed(error_code="continuation_tool_call_not_allowed", recoverable=False)` 收口，且不得执行工具。
   - continuation 轮计入 LLM iteration / `max_iterations`，但不计入普通工具批次保护；因 `max_iterations` 耗尽无法继续时，以已累积内容产出 degraded final answer，不触发 Phase 3 force-answer。
   - 测试清单已覆盖 `tools=()`、禁工具协议守卫、上限收口、内容拼接与取消优先。
   - 初审 Blocking 2 已关闭。

3. `context_compaction_requested` 后 terminal 已固化。
   - `docs/engine/migration-plan.md` 和 `docs/engine/phase5-plan.md` 均写明：Engine 只发出 `context_compaction_requested`，随后固定以 `run_failed(error_code="context_compaction_required", recoverable=True)` 收口。
   - 该项已从 `phase5-plan.md` 待确认项移除。
   - 初审 Important 1 已关闭。

4. `docs/engine/design.md` 已同步。
   - `docs/engine/design.md` 的 Context budget 稳定规则已改为：当前 Engine-only 阶段只发出 `context_compaction_requested`，随后以 recoverable `run_failed(error_code="context_compaction_required")` 收口；不做 Engine 内 compact / retry，不引入 `run_suspended` 或 resume。
   - design 后续步骤也已标注 awaiting / suspended 主链路取消当前 Engine 独立实施，转入 issue #4。
   - 初审 Important 2 已关闭。

5. `ContextBudgetSnapshot` 构造源已补强。
   - `phase5-plan.md` 明确 provider overflow 无可靠 usage 时，预算快照必须来自 Engine context budget helper 对当前 LLM-facing messages 的确定性估算，不得填 `0/0/0` 魔法占位值。
   - 初审 Suggestion 1 已采纳。

### 6.3 剩余注意事项

- Phase 5 的 continuation 语义选择比 OLD 更收窄：NEW 固定 `tools=()`。这是清晰且可测的 NEW 架构决策，OLD/NEW 专项 review 应审查其边界解释是否被实现和 README 如实表达，而不是要求机械复刻 OLD 可能继续暴露工具的行为。
- Phase 5 实施不得提前写 README；README / docs / issue 收口只能在代码实现、code review、OLD/NEW 专项 review 和日常 review 通过后进行。
- `run_suspended` 仍是公共 contract 中已有 terminal 类型，但 Phase 5 不得产生该路径；测试已要求 `run_suspended` 未成为 Phase 5 触发路径。

### 6.4 复审修改

更新：

- `docs/engine/phase5-plan-review.md`

未修改：

- `docs/engine/phase5-plan.md`
- `docs/engine/migration-plan.md`
- `docs/engine/design.md`
- 生产代码
- 测试代码

## 7. 最新版复审：context overflow 后移后的 Phase 5 handoff

### 7.1 复审结论

通过，可以进入 Phase 5 实施准备。

本轮复审对象是最新版本的 `docs/engine/migration-plan.md`、`docs/engine/phase5-plan.md`、`docs/engine/design.md` 与 `docs/host/design.md`。这些文档已经按总控和用户最新决策收口：本轮 Engine 迁移不再纳入 context overflow / `context_compaction_requested` / `context_compaction_required`，Phase 5 只聚焦 Engine-only 自洽的 `finish_reason=length` continuation。原 Phase 6 仍只是 Phase 5 同一 PR 的 README / docs / issue 验收收口，不是第二个实现阶段。

本轮只审查并更新文档；未修改生产代码、测试代码，未运行 pytest 或 pyright。

### 7.2 Findings

无 blocking。

无 important。

#### Suggestion 1. 后续 issue 名称可以在提交前统一固化

位置：

- `docs/engine/phase5-plan.md:292`
- `docs/engine/migration-plan.md:688`

问题：

计划已经清楚写出 context overflow / Host context compaction 协作后移为后续独立 issue，但 issue 标题和编号尚未固化。这不阻塞 Phase 5 实施，因为本轮实现范围已经明确排除该能力。

建议：

总控后续可单独创建或确认 issue，例如 `Host context compaction coordination with Engine`，并在 Phase 5 文档收口时回填 issue 链接。

### 7.3 核心检查结果

1. Phase 5 范围已收窄到 continuation。
   - `phase5-plan.md` 明确目标只包括 `finish_reason=length` continuation、`tools=()`、partial content 拼接、次数限制、`content_filter` 不 continuation、取消优先与 Phase 3 回归。
   - `migration-plan.md` 的 Phase 5 总控口径与之对齐。

2. context overflow 已彻底退出本轮实现范围。
   - `phase5-plan.md` 把 provider context overflow 强类型识别、`context_compaction_requested`、`context_compaction_required`、`max_context_tokens`、trigger ratio、projected context early stop 都列为非目标。
   - `migration-plan.md` 同步写明后续在 Host 上下文治理实施时作为独立 issue 完善 Engine 协作。
   - `design.md` 和 `host/design.md` 均说明该能力只是后续 Host 协作设计素材，不表示当前已实现，也不要求本轮 Engine 迁移实现。

3. truncate / fetch_more 已明确后移 Host / ToolRuntime。
   - OLD `TruncationManager`、fetch_more、cursor、TTL、scope token、tool-level truncation manager 在计划和设计文档中均被列为本轮非目标。
   - 计划要求实施中如需要这些能力必须停止并向总控汇报。

4. continuation handoff 足够可实施。
   - Runner continuation 调用固定 `tools=()`。
   - continuation 轮返回 tool calls 时 fail-closed 为 `run_failed(error_code="continuation_tool_call_not_allowed", recoverable=False)`，并禁止执行 ToolExecutor。
   - 内容拼接、次数限制、`continuation_max_attempts`、`continuation_prompt`、`content_filter` 不续写、取消优先、max_iterations 关系与测试清单均已写明。

5. Phase 6 doc closeout 没有提前承诺未来能力。
   - README / docs 收口被放到 Phase 5 实现、code review、OLD/NEW 专项 review 和日常 review 全部通过之后。
   - 文档明确不得写 context overflow / `context_compaction_requested` 已落地，也不得写 Host wait record / resume、conversation memory、trace store、OLD `TruncationManager` / fetch_more 已可用。

6. Review gate 完整。
   - 包含 Phase 5 plan review、用户确认、Phase 5 code review、OLD/NEW continuation 专项对比 review、日常 `docs/code_review.md` review、总控验收和用户确认。
   - OLD/NEW 专项 review 范围已聚焦 continuation、content_filter、Phase 3 fallback 回归与取消优先，并明确不能机械迁入 OLD context budget / context overflow / truncation 能力。

### 7.4 剩余未迁移能力确认

Phase 5 完成后，Engine 迁移仍明确排除以下两类 OLD 能力：

1. truncate & fetch_more：
   - OLD `TruncationManager`
   - fetch_more
   - cursor / TTL / scope token
   - 工具级结果截断与续读协议
   - 后续归 Host / ToolRuntime。

2. context overflow / context compaction coordination：
   - provider context overflow 强类型识别
   - `context_compaction_requested`
   - `context_compaction_required`
   - Host 基于 conversation_memory / transcript / tool facts 重构 messages
   - 重新发起 run 的治理闭环
   - 后续归 Host 上下文治理 issue，并在实施 Host 时完善 Engine 协作。

### 7.5 本轮修改

更新：

- `docs/engine/phase5-plan-review.md`

未修改：

- `docs/engine/phase5-plan.md`
- `docs/engine/migration-plan.md`
- `docs/engine/design.md`
- `docs/host/design.md`
- 生产代码
- 测试代码
