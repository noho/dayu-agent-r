# Host P5 Handoff Plan：No-Full-Governance Multi-Turn Smoke

## 目标

P5 目标是在 P1、P1.5、P2、P3、P4 均已合入 `main` 的基础上，建立一条最小纵向 smoke / integration
guard，把当前 Host 已落地的单进程能力串成一个真实执行路径：

```text
USER_INPUT_ACCEPTED
  -> RunEventStore append-before-stream
  -> LLM tool_call huge_echo
  -> ToolRuntime truncate / cursor / LLM-facing fetch_more hint
  -> LLM tool_call fetch_more in the same run
  -> Conversation Memory projection
  -> RunInputBuilder 构造下一轮输入
  -> context overflow compact / retry
  -> 同一 session 顺序多轮 terminal
```

本阶段不是生产治理阶段。它只证明“单进程、单调用方、顺序执行、每轮等待上一轮 terminal 后再启动下一轮”的
happy path 可以通过同一份 EventLog / memory / tool / compact 事实链路跑通，并为 P6+ 前的总控收口提供可人工观察的
smoke。

本阶段必须产出：

- `utils/smoke_host_multiturn_no_governance.py` 手工 smoke：主目标必须真实向 `mimo-v2.5-pro-plan`
  发送 prompt，由模型通过 LLM tool calling 调用 `huge_echo`，再由模型根据截断 hint 在同一 run 内调用
  framework `fetch_more`；输出关键事件、cursor、
  memory / compact / fetch_more 摘要，不打印 delta、大工具结果、scope token 或内部大块 prompt。
- P5 端到端测试：覆盖单调用方顺序多轮，证明第二轮看见第一轮 canonical 用户输入、final answer 与 tool fact，
  第三轮或同轮 overflow 路径能 compact / retry，并且不会重复追加 `USER_INPUT_ACCEPTED`。
- 现有 P1-P4 生产路径复用：测试与 smoke 必须走真实 `LocalRunHarness -> RunEventStore -> ToolRuntime ->
  ConversationMemoryStore -> DefaultRunInputBuilder -> ContextCompactCoordinator`，不能伪造一条比生产更干净的捷径。
- 主 happy path 的硬验收：`utils/smoke_host_multiturn_no_governance.py` 必须真的使用现有
  `mimo-v2.5-pro-plan` provider 配置向模型发送 prompt，并由模型通过 LLM tool calling 机制调用
  `huge_echo`，再由模型根据 `truncation.next_action="fetch_more"` 与 `fetch_more_args` 调用 framework
  `fetch_more`。对应 P5 integration 测试可以使用 fake provider 验证不可联网路径，但 fake 只能模拟
  provider 输出，两个工具调用仍必须经 Engine tool loop、`ToolExecutor.execute`、`ToolRuntimeToolExecutor`、
  `InMemoryToolRuntime` 与 `huge_echo` executor；不能由 scripted WorkerProxy 直接手写 tool result facts，
  也不能直接调用 `InMemoryToolRuntime.execute_tool_call()` 替代主用例。
- P5 后文档：在 `docs/host/design.md` 写回 P5 后执行边界 / 执行路径；在 `dayu/host/README.md` 写当前事实与
  smoke 命令；如新增测试层级，则同步 `tests/README.md`。
- review 证据：常规 code review 与至少一个纵向语义 review，重点审语义声称与实现逻辑是否错位。
- 最小公共 tool declaration 能力：把 OLD-like `@tool(..., truncate=ToolTruncateSpec(...))` 的可读声明方式纳入
  NEW 公共契约，使同一工具现场同时声明 LLM-facing `ToolSchema`、Host ToolRuntime `ToolTruncateSpec`、执行绑定与
  展示 metadata，但仍保持职责分离；`huge_echo` 是该能力在 P5 的第一个 smoke/test 工具。

## 非目标

P5 不实现以下能力：

- 完整多进程治理、持久 EventLog、startup recovery、lease / fencing、observer checkpoint。
- RemoteProxy、RemoteStub、跨进程 wire protocol、断线重连或 ack。
- Reply Outbox、外部渠道投递、delivery key、投递幂等。
- audit hard-gate、tool trace observer、timeline projection、metrics observer。
- P7 的 `client_request_id` 创建幂等、同 Session active Run admission、active Run 并发仲裁、完整 Run lifecycle
  governance。
- 调用重试语义、普通 transient retry、validation replay、OutputContract。
- public memory edit / reset / forget API、持久 memory projection、跨 session / project / user memory。
- 完整 ToolRegistry、权限治理、tool middleware、业务工具迁移或 Service 层工具 catalog 装配；P5 只暴露最小
  framework `fetch_more` tool，使模型能在同一 run 内按截断 hint 补读，不把它扩展成生产治理注册中心。
- 真实 provider overflow 作为必跑验收。P5 手工 smoke 的主目标只要求真实 `mimo-v2.5-pro-plan`
  tool calling、Host ToolRuntime truncate / fetch_more 与多轮接续；overflow / compact 子 case 可以使用
  deterministic fake provider 或 scripted WorkerProxy 作为辅助诊断。
- 自动替模型补读、透明分页或 Host-side continuation 策略；P5 必须证明补读动作来自模型发起的 LLM tool calling。

以下问题若出现，不能在 P5 直接当作 bug 要求修生产治理：

- 同一 session 并发启动两个 active Run 的仲裁缺失。
- 重复 `start_run` 请求是否返回同一 Run 的幂等语义缺失。
- 进程重启后内存 EventLog / memory / cursor 丢失。
- terminal 后远程客户端继续补读的跨进程审计语义不完整。

但 P5 必须守住已落地语义：如果单进程顺序 happy path 中出现事实旁路、cursor 语义错误、memory 污染、
compact 重复用户输入、preview/reasoning 进入运行态等，则属于 P5 范围内 bug。

## 前置条件

- P1 已通过 PR #16 合入 `main`。
- P1.5 已通过 PR #17 合入 `main`。
- P2 已通过 PR #18 合入 `main`。
- P3 已通过 PR #19 合入 `main`。
- P4 已通过 PR #21 合入 `main`，当前基线含 merge commit `843fb99 Host P4 context overflow compact (#21)`。
- 当前分支为 `codex/host-p5-multiturn-smoke`。
- 当前 `dayu.host` 已落地：
  - `start_run`、`stream_run_events`、`get_run_result`。
  - `get_tool_fetch_more_handle`、`fetch_more_tool_result`。
  - `RunEventStore` append-before-stream、per-run cursor、canonical / preview 分层、terminal guard。
  - Host-owned `USER_INPUT_ACCEPTED` append-before-engine。
  - Host-owned ToolRuntime schema-driven truncate、cursor、single-use、TTL、scope token。
  - `InMemoryConversationMemoryStore`、`DefaultRunInputBuilder`、`RunInputBuildTrace`。
  - context overflow 强类型识别、Host deterministic compact、same-run internal attempt retry。
- `docs/host/design.md` 第 9、11、12 节与 `dayu/host/README.md` 是当前已落地边界的文档真源。

## OLD / NEW 强参考点

P5 需要强参考 OLD 行为，但不得写兼容性代码。

必须参考：

- OLD `conversation_memory.py` / issue #48：多轮追问连续性依赖 pinned state、tool summary、recent raw turn 与
  display / runtime 隔离；P5 smoke 需要观察这些事实在 NEW 路径中是否真实接续。
- OLD `TruncationManager` 与 `fetch_more`：截断由工具 schema 声明驱动，旧 cursor 成功补读后失效，若还有剩余内容
  颁发下一页新 cursor；截断后的 tool result 会给 LLM 投影 `truncation.next_action="fetch_more"` 与
  `truncation.fetch_more_args`，并自动暴露 framework `fetch_more` tool。P5 需要在纵向 smoke 中证明模型在同一
  run 内自己调用 `fetch_more` 补读，而不是由 smoke 脚本代调 Host public API。
- OLD `ToolTruncateSpec` 支持多种截断方式；NEW P5 不能把截断实现收窄成 `huge_echo` 专用文本截断，至少要保持
  `text_chars`、`text_lines`、`list_items`、`binary_bytes` 与 `target_field` / `field_path` 的设计兼容性。
- OLD `@tool(..., truncate=ToolTruncateSpec(...))` 可读声明方式：工具函数现场同时能看到 LLM schema 与截断声明，
  但 NEW 必须把 LLM-facing schema、Host runtime metadata、executor binding 和 display metadata 分清楚，并产出
  强类型 `ToolDefinition` / `ToolBundle`。
- OLD `async_agent._compact_messages` 与 provider overflow 判断：context overflow 后 compact 不能丢当前用户问题、
  caller system prompt 或必要工具事实；NEW 中 compact 已归 Host，P5 只验证 Host / Engine 协作路径。
- OLD smoke / application tests 中多轮 session 的人工可观察输出风格：输出摘要应利于人看日志，不输出完整 delta
  或敏感 token。

不得照搬：

- OLD Engine 内 compact / retry；NEW Engine 只报告 overflow 并消费 Host 生成的 `RunInput`。
- OLD 完整 ToolRegistry / 权限治理 / middleware；NEW P5 只恢复最小 framework `fetch_more` tool 与 LLM-facing
  truncation hint，不恢复完整注册中心或业务工具治理。
- OLD `_create_xxx_tool(registry, service, limits)` / registry 参数范式；NEW 不把工具声明建立在外部可变 registry
  参数上，推荐无 registry factory，例如 `_get_xxx_tool_definition(...)`。若只返回 `ToolSchema` 才可命名为
  `_get_xxx_tool_schema(...)`；P5 目标返回 schema、callable / executor binding、truncate 与 display metadata，
  因此 `definition` / `bundle` 命名更准确。
- OLD runtime transcript / history archive 作为第二事实源；NEW 只能从 RunEventStore / memory projection 同源派生。
- OLD scene_preparer / application 层直接组装 Agent 输入；P5 必须走 Host 内部 builder。

## 架构边界

分层仍固定为：

```text
UI -> Service -> Host -> Engine
```

P5 手工 smoke 主路径：

```text
Smoke script / test harness
  -> LocalRunHarness.start_run(turn 1)
      -> append USER_INPUT_ACCEPTED
      -> ConversationMemoryStore.get_snapshot
      -> DefaultRunInputBuilder.build
      -> LocalProxy -> EngineWorker -> dayu.engine.run_agent_messages
      -> OpenAI-compatible Runner sends prompt to provider case mimo-v2.5-pro-plan
      -> model emits LLM tool call for huge_echo
      -> Engine tool loop emits TOOL_CALL_REQUESTED
      -> ToolExecutor.execute
      -> ToolRuntimeToolExecutor -> InMemoryToolRuntime -> huge_echo business executor
      -> RunEventStore.append(tool truncation / cursor facts)
      -> Agent injects truncated tool result into next Runner / provider iteration
         with truncation.next_action="fetch_more"
         and truncation.fetch_more_args={cursor, scope_token, limit?}
      -> model emits LLM tool call for framework fetch_more
      -> Engine tool loop emits TOOL_CALL_REQUESTED(fetch_more)
      -> ToolExecutor.execute
      -> Host ToolRuntime routes fetch_more instead of business executor
      -> RunEventStore.append(fetch_more requested / completed)
      -> Agent injects fetched chunk into next Runner / provider iteration
      -> if needed, fetched chunk carries next fetch_more hint
      -> model emits final answer after it has enough result
      -> RunEventStore.append(final terminal)
      -> ConversationMemoryStore.project_run_events
  -> LocalRunHarness.start_run(turn 2 after turn 1 terminal)
      -> append USER_INPUT_ACCEPTED
      -> RunInputBuilder sees turn 1 user / final / tool facts / source cursor
      -> terminal
      -> memory projection
  -> LocalRunHarness.start_run(turn 3 or overflow run)
      -> fake provider / Engine context_compaction_requested / recoverable run_failed
      -> Host append overflow / compact / retry facts
      -> WorkerProxy.stream_engine_events(compacted RunInput)
      -> terminal
```

边界规则：

- P5 手工 smoke 主 happy path 必须使用真实 provider case `mimo-v2.5-pro-plan`，并由模型真实发起
  `huge_echo` tool call；缺少 `MIMO_PLAN_API_KEY`、model 配置或 endpoint 配置时必须清晰失败并返回非零，
  不能把 fake provider 当作手工 smoke 成功。
- P5 integration 测试可以使用 fake provider / fake LLM 稳定产出 `huge_echo` tool call 与后续 final answer，
  但必须经过真实 EngineWorker、Engine 私有 Agent tool loop、`ToolExecutor.execute`、
  `ToolRuntimeToolExecutor`、`InMemoryToolRuntime` 与 `huge_echo` executor。fake 只能模拟 provider/LLM
  输出，不能替代 Engine tool loop、ToolExecutor adapter、Host ToolRuntime 或 EventLog。
- scripted WorkerProxy 只能作为辅助 / 诊断路径，例如 compact retry 的 deterministic overflow 子 case；它不能替代
  主 happy path，也不能作为 P5 smoke 的主证明。
- P5 smoke 可以使用 fake business ToolExecutor 或 `huge_echo` executor 返回长文本，但 Host 侧必须走真实
  production classes，不得把 `RunEvent`、memory snapshot 或 compact facts 手工塞进结果断言。
- P5 主用例必须让真实 `InMemoryToolRuntime` 按 `ToolTruncateSpec` 产生 truncation / cursor /
  fetch_more facts；不能手写 tool runtime facts 或直接构造 `ToolResultTruncatedData` /
  `ToolCursorIssuedData` 冒充真实运行路径。
- 直接调用 `InMemoryToolRuntime.execute_tool_call()` 只能用于辅助单元测试、诊断或构造更小的 ToolRuntime
  回归用例；不能替代主 happy path 中由 Engine / Agent 发起 tool call 并经 `ToolExecutor.execute` 到达
  ToolRuntime 的证明。
- 每轮必须等待上一轮 terminal 后再启动下一轮；不测试并发 admission，也不隐式依赖它。
- 同一轮内成功 `fetch_more` 必须发生在 owner run 未 terminal 时；terminal 后只验证 typed failure、
  `denied=False`、`event_cursor=None`、EventLog 事件数不增加。
- 单个 Run 内 context overflow compact retry 可以产生新的 internal attempt；这不是新用户 turn，不得再 append
  `USER_INPUT_ACCEPTED`。
- `fetch_more_tool_result` 仍是 Host public API / framework tool 内部路由可复用的 Host 边界；P5 主路径的成功
  补读 actor 必须是模型发起的 LLM `fetch_more` tool call，不是 smoke 脚本旁路代调。
- `scope_token`、cursor 原文、完整大工具结果不得出现在 smoke 日志、RunInput memory block 断言输出或 README 示例。
- preview / reasoning / delta 不能进入 memory、RunInputBuilder、compact 输入或 P5 smoke 语义断言。
- P5 不改变 `dayu.runtime`，不新增 runtime helper。

## P5 最小公共 tool declaration 能力

动机成立：P5 纵向 smoke 需要稳定制造可截断工具结果，但如果继续沿着 `utils` 局部 smoke registry 方向推进，
会把 schema、执行绑定、截断 metadata 的同源声明问题埋在测试工具里，后续真实工具接入仍可能只注册
LLM-facing schema 而漏掉 Host ToolRuntime metadata。因此 P5 应把 OLD-like 可读声明方式收束成 NEW 的最小公共能力。

P5 需要落地：

- 公共 `@tool` decorator 或等价声明 helper。该 helper 服务工具声明，不负责权限治理、生命周期治理、业务发现或执行调度。
- `truncate=ToolTruncateSpec(...)` 与 LLM-facing `ToolSchema` 同工具现场声明，但职责分离：`ToolSchema` 只投影给 LLM；
  `ToolTruncateSpec` 仍是 Host ToolRuntime metadata，不进入 LLM schema。
- 强类型 `ToolDefinition` / `ToolBundle` 输出，至少包含：
  - `name`。
  - callable / executor binding。
  - LLM-facing `ToolSchema`。
  - Host ToolRuntime `ToolTruncateSpec`。
  - display metadata，例如 `ToolDisplayInfo` / `tags`，供未来 UI 展示友好 tool 调用信息。
- `@tool(..., display_name="...")` 的声明入口保留，内部转换为 `ToolDisplayInfo(name=...)`；
  display metadata 不进入 LLM schema，不影响模型可见工具描述。
- `ToolDefinition` / `ToolBundle` 必须提供明确的 Engine input projection，例如 `to_tool_schema()` 或只读
  `schema` 属性。该 projection 只能返回 `ToolSchema`；进入 Engine / Runner 的必须始终是
  `tuple[ToolSchema, ...]`，不能把整个 definition / bundle 传给 `AgentRunRequest.tool_schemas` 或
  WorkerProxy request。
- `huge_echo` 作为第一个 P5 smoke/test 工具，必须通过该公共声明能力定义，而不是继续依赖
  `utils.host_smoke_tools.py` 内的局部 `SmokeToolRegistry` / 泛名 `tool` 作为最终目标形态。
- `huge_echo` 必须按公共 `@tool(..., truncate=ToolTruncateSpec(...))` 现场声明 LLM schema、executor binding、
  Host truncate spec 与 display metadata。它是 smoke 工具，不进入财报业务工具或 Host public API。
- `huge_echo` 默认必须稳定返回足够大的结果，使 `ToolTruncateSpec` 在本地测试与真实 provider smoke 中都能触发。
  主 smoke 至少覆盖长文本；辅助测试可覆盖 list / JSON wrapper 与 `target_field` / `field_path`，但这些变体仍应
  由同一公共 declaration 能力声明，不能回退到 `utils` 局部 registry。

P5 不需要落地：

- 完整 `ToolRegistry`、tool catalog、权限治理、middleware、调用审计 hard-gate 或业务工具迁移。
- 自动透明补读、Host-side continuation 策略或完整业务 tool registry；P5 需要的只是 framework
  `fetch_more` schema、LLM-facing `truncation` hint 与 Host ToolRuntime 路由。
- OLD `_create_xxx_tool(registry, service, limits)` 风格。NEW 推荐无 registry factory：
  - 若只返回 LLM schema，可命名为 `_get_xxx_tool_schema(...)`。
  - 若返回 schema、callable / executor binding、truncate spec 与 display metadata，推荐
    `_get_xxx_tool_definition(...)` 或 `_get_xxx_tool_bundle(...)`；P5 的目标更接近 `definition` / `bundle`。

## 文件级改动清单

计划新增：

- `dayu/contracts/tool_declaration.py` 或等价 contracts 层模块
  - 提供最小公共 `@tool` decorator / declaration helper。
  - 提供强类型 `ToolDefinition` / `ToolBundle`，统一携带 name、LLM-facing `ToolSchema`、callable / executor binding、
    `ToolTruncateSpec` 与 display metadata。
  - 提供显式 schema projection，例如 `to_tool_schema()` 或只读 `schema`；projection 是 Engine / Runner 输入的唯一
    合法来源，不能把 definition / bundle 本体传入 Engine。
  - 不 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui` / `dayu.fins`，不进入 `dayu.runtime`。
  - 不实现完整 registry、权限治理、tool trace observer、audit hard-gate 或业务工具迁移。
- `utils/smoke_host_multiturn_no_governance.py`
  - 手工 smoke 主路径必须真实使用 `mimo-v2.5-pro-plan`：与 `utils/` 下其它 provider smoke 保持一致，
    在脚本内写死 `ProviderCase`，只从环境变量读取 API key，不读取 `dayu/config/llm_models.json` 或
    `workspace/config`，也不充当配置 adapter。该 hardcoded ProviderCase 明确包含
    `MimoThinkingExtension(enabled=True)`，这是 P5 smoke 的有意选择。
  - 主 happy path 必须经 Engine / Agent tool loop、`ToolExecutor.execute`、`ToolRuntimeToolExecutor`、
    `InMemoryToolRuntime`、`huge_echo` executor 与 Host ToolRuntime truncate / fetch_more 路径完成；
    scripted WorkerProxy 只能作为辅助 / 诊断 case。
  - 建议支持 `--case all|real-provider|compact-retry`；`all` 必须包含 real-provider 主路径。缺少
    `MIMO_PLAN_API_KEY`、model、endpoint 或 tool calling capability 时输出 clear failure 并返回非零，
    不能 skip 为成功。
  - 输出建议包括：
    - 每轮 `run_id`、terminal type、terminal cursor。
    - provider case、model、endpoint 摘要、是否真实发送 provider request、`supports_tool_calling` 与
      `provider_request` 开关摘要；不得输出 API key、headers 或完整 payload。
    - ProviderCase 来源，例如 `case_source=hardcoded_provider_case`，并显式输出
      `MimoThinkingExtension(enabled=True)` 属于 hardcoded ProviderCase，不以 `llm_models.json` 为真源。
    - `huge_echo` tool call 是否来自 Engine / Agent LLM tool calling，是否观察到 `ToolExecutor.execute`。
    - 每轮 `USER_INPUT_ACCEPTED` cursor，证明同一 Run 只有一次用户输入。
    - owner run 未 terminal 时成功补读的 tool truncate / cursor issued / fetch_more completed event cursor，并能从
      输出顺序或事件 cursor 证明成功 `fetch_more` 发生在 final terminal 前。
    - terminal 后补读返回 `run_terminal` typed failure、`denied=False`、`event_cursor=None`、EventLog count unchanged。
    - 第二轮 RunInput / trace 中是否包含上一轮 user、final、tool fact、source cursor。
    - 普通第二轮是否同时保留 pinned_state / task frame stable layer、recent raw turn、tool fact 与 source cursor。
    - compact retry attempt 是否同时保留 caller system prompt、当前 user、pinned_state、必要 tool fact /
      evidence anchor / source cursor。
    - compact retry 的 overflow / compact requested / completed / attempt retry cursor、attempt 数量、before / after
      估算 token / char。
    - final answer internal echo filter 是否未触发或按预期触发。
  - 不输出：delta 刷屏、完整 tool result、`scope_token`、raw cursor、完整 Host Memory block、完整 compact prompt。
- `tests/host/test_phase5_multiturn_no_governance_smoke.py`
  - 端到端 integration guard，走真实 Host 内部路径。
  - 覆盖 happy path、多轮 memory 接续、truncate/fetch_more、context compact retry 的组合场景。
  - 主 happy path 必须验证 `huge_echo` 由 Engine / Agent 的 LLM tool calling 触发，并经
    `ToolExecutor.execute` 进入 Host ToolRuntime；scripted WorkerProxy 直接手写 tool result facts 只能作为辅助
    诊断，不能替代该测试。
- `tests/contracts/test_tool_declaration.py` 或并入 P5 Host 测试的等价覆盖
  - 覆盖 `@tool(..., truncate=ToolTruncateSpec(...))` 生成 `ToolDefinition` / `ToolBundle`。
  - 断言 `ToolDisplayInfo` / `tags` 不进入 LLM-facing schema。
  - 断言 `ToolTruncateSpec` 由 Host ToolRuntime metadata 路径消费；spec 本体不进入 LLM schema，但截断结果会投影
    LLM-facing `truncation` hint。

计划修改：

- `utils/host_smoke_tools.py`
  - 此前局部 smoke registry / 局部泛名 `tool` 方向已废弃，不作为 P5 实施起点。
  - P5 不应新增或保留该临时模块；`huge_echo` 应通过公共 tool declaration 能力定义。
- `dayu/host/_run_harness.py`
  - 仅当 P5 integration 暴露出必要 observability 缺口时小范围修改，例如为测试读取最近 `RunInputBuildTrace`
    提供已有内部缓存的更稳健访问方式。
  - 不新增 public governance API，不新增 active Run admission。
- `dayu/host/_tool_runtime.py`
  - 需要补齐 framework `fetch_more` 路由、LLM-facing truncation hint projection 与 cursor single-use 语义。
  - Host public handle / `fetch_more_tool_result` 仍可作为底层边界或负例；P5 主成功路径不能由 smoke 脚本代调。
  - 若 terminal 后 typed failure 不符合当前契约，则修复真实 bug。
- `dayu/host/_conversation_memory.py` / `dayu/host/_run_input_builder.py`
  - 仅当纵向 smoke 发现 P3 facts 没有真实进入下一轮 RunInput、或 trace 不能定位 included / excluded item 时修复。
  - 不实现 episode summary 生成或 persistent projection。
- `dayu/host/_context_compaction.py` / `dayu/host/_event_translation.py`
  - 仅当纵向 smoke 发现 P4 compact facts 无法与同轮工具 facts / memory facts 协作时修复。
  - 不实现 LLM compaction scene。
- `docs/host/design.md`
  - 写回 P5 后执行边界 / 执行路径：单进程、单调用方、顺序多轮 smoke 已把 P1-P4 串通；同时明确仍未落地的生产治理。
- `dayu/host/README.md`
  - 更新当前事实、手工 smoke 命令、真实 `mimo-v2.5-pro-plan` 主路径边界，以及 fake provider 仅用于测试 /
    compact 诊断的边界。
- `tests/README.md`
  - 如新增 `test_phase5_multiturn_no_governance_smoke.py`，补充 Host P5 integration guard 说明和运行命令。

不计划修改：

- `dayu.engine.*`，除非 P5 暴露 Engine terminal/overflow 契约与 P4 已落地声明冲突；若需要修改，必须先停止并修 plan。
- `dayu.runtime.*`。
- `dayu.fins.*`。
- `dayu.service.*`、`dayu.ui.*`。
- 持久化 schema / workspace migrations。

## 契约 / 事件 / 状态变化

P5 原则上不新增 Host public 运行契约，不新增 RunEvent 类型，不新增状态机状态。

P5 会新增或固定一个公共 tool declaration 契约，并暴露一个 framework `fetch_more` tool：

- `ToolDefinition` / `ToolBundle` 是工具声明输出，不是 Host runtime governance API。
- `ToolSchema` 仍是 LLM-facing schema；`ToolTruncateSpec` 仍是 Host ToolRuntime metadata。
- callable / executor binding 与 display metadata 跟随 definition / bundle 出口同源传递。
- definition / bundle 到 Engine / Runner 的边界必须经过显式 projection：`to_tool_schema()` 或只读 `schema`
  只能产出 `ToolSchema`，Host 装配侧再组成 `tuple[ToolSchema, ...]`。Engine / Runner request 不得接收、
  保存或检查 `ToolDefinition` / `ToolBundle` 本体。
- `ToolDisplayInfo` / `tags` 只服务 UI / smoke 展示，不进入 LLM schema。
- 新增 LLM-facing framework `fetch_more` schema 与 truncation hint projection；不改变 P2 Host public
  `fetch_more_tool_result` 的底层语义，只把它接入 Engine tool loop 可调用的 framework tool 路径。

P5 需要锁住以下既有契约：

- `USER_INPUT_ACCEPTED` 是每个 user turn 的唯一 canonical 用户输入真源。
- 每个 public user turn 对应一个新 `run_id`；context overflow compact retry 是同一 `run_id` 下的 internal attempt。
- `RunEventCursor` 是 per-run cursor；P5 输出和断言不得暗示跨 run 全局有序。
- `RunStream.events` 和 `stream_run_events(after=cursor)` 只观察已 append 事件。
- terminal 后 event store 拒绝继续 append；terminal 后 fetch_more 返回 typed failure 或按 P2 当前契约处理，不伪造审计事实。
- ToolRuntime cursor 是 run-scoped、single-use、TTL-bound、scope-token protected；EventLog 只暴露 fingerprint / summary。
- memory projection 只在 terminal 后消费 canonical facts；preview / reasoning / delta 不进入 memory。
- compact retry 不追加新的 `USER_INPUT_ACCEPTED`，不把 compacted `RunInput` 投影成 raw user turn。
- Engine final answer echo filter 只作为最小安全 gate，不是完整 OutputContract。

如实施中确实需要新增一个只用于 smoke 观察的内部结构，必须满足：

- 不进入 `dayu.host.__all__`。
- 不成为 public API。
- 不使用 `Any` / `object` / 开放 dict payload。
- 不绕过 EventLog / memory 的事实真源。

## 状态机变化

P5 不新增生产状态机。

P5 smoke 只观察当前已存在的最小状态：

```text
RUNNING -> SUCCEEDED
RUNNING -> FAILED
RUNNING -> CANCELLED
RUNNING -> SUSPENDED
```

P5 额外观察同一 Run 内 P4 compact retry 子序列：

```text
attempt 0 running
  -> context_compaction_requested / run_failed(context_compaction_required)
  -> context_overflow_observed
  -> context_compact_requested
  -> context_compact_completed
  -> context_attempt_retrying
  -> attempt 1 running
  -> terminal
```

该子序列不是 P7 attempt lifecycle governance；没有 lease、fencing、owner token、恢复或普通 retry 预算。

## 数据持久化 / schema 变化

P5 不引入持久化 schema，不修改 workspace schema，不新增 migration。

当前所有数据仍是单进程内存 adapter：

- `InMemoryRunEventStore`。
- `InMemoryToolRuntime` cursor store。
- `InMemoryConversationMemoryStore`。
- `LocalRunHarness` trace 缓存。

这些 adapter 服务 P2-P5 smoke / tests，不声明多进程、重启恢复或生产持久正确性。P6 才会把 EventLog /
projection 扩展到持久化与 observer checkpoint。

涉及 schema 变更的两条要求在 P5 结论为：

- NEW 不涉及旧库兼容读取。
- 不需要将旧库迁移动作加入 `workspace_migrations` / `dayu-cli init`。

## 多进程并发影响

P5 不提供多进程并发正确性，也不测试多进程。

必须避免的误导：

- 不声明同 Session 只允许一个 active Run 的 admission 已经落地。
- 不声明 `start_run` 重复请求幂等。
- 不声明 cursor / memory / EventLog 跨进程可恢复。
- 不用全局锁或单进程队列模拟未来 lease / fencing。

P5 测试必须显式以顺序执行表达：

```text
await start_run(turn n)
consume until terminal
assert get_run_result(run n) is terminal
then start_run(turn n + 1)
```

## ToolRuntime / EngineWorker / Engine 边界影响

- EngineWorker / WorkerProxy 仍是 Host 内部执行边界，不进入 public API。
- 公共 tool declaration 属于 schema / executor / runtime metadata 的装配契约，不让 Engine 理解 Host cursor、
  memory、compact 或 display metadata。
- `ToolDefinition` / `ToolBundle` 是 Host 装配输入；Engine / Runner 只能接收由 `to_tool_schema()` 或只读
  `schema` 投影得到的 `ToolSchema` tuple。WorkerProxy request / `AgentRunRequest.tool_schemas` 中不得出现
  `ToolTruncateSpec`、display metadata、`tags`、callable 或 executor binding。
- P5 手工 smoke 主 happy path 不接受 fake provider、fake LLM 或 fake WorkerProxy 直接产出 scripted tool result
  `EngineEvent` 作为证明；必须使用真实 `mimo-v2.5-pro-plan` provider、真实 EngineWorker / Engine / Agent tool loop，
  并让模型真实产出 `huge_echo` tool call 与后续 final answer。
- P5 手工 smoke 必须证明 real-provider 主路径里 success `fetch_more` 的 actor 是模型：证据必须显示
  cursor facts 已由 `ToolRuntimeToolExecutor -> InMemoryToolRuntime` 产生，截断 tool result 注入给模型时包含
  LLM-readable `truncation.next_action="fetch_more"` 与 `fetch_more_args`，随后模型发出 `fetch_more` tool call，
  Host ToolRuntime 路由并 append completed fact，最后才观察到 final terminal。该证据必须来自实际事件 /
  wrapper 观测，不能是脚本常量、手写 facts、直接调用 `InMemoryToolRuntime.execute_tool_call()`、
  直接调用 Host public `fetch_more_tool_result()` 或 scripted WorkerProxy。
- P5 integration 测试可以让 fake provider / fake LLM 只负责产出 tool call 与 final answer，用于 CI /
  不可联网路径；该 fake 边界不能被手工 smoke 当作成功证明。
- P5 辅助 / 诊断 case 可以使用 fake WorkerProxy 产出 scripted `EngineEvent`，但不能跳过 `LocalRunHarness`，
  不能手写 tool runtime facts，且不能替代主 happy path。
- ToolRuntime 仍只作为 Engine 可见 `ToolExecutor` adapter 背后的 Host 内部能力；Engine 只看见普通
  `huge_echo` / `fetch_more` tool call 与普通 tool result。
- ToolRuntime 从 `ToolDefinition` / `ToolBundle` 中消费 `ToolTruncateSpec`；spec 本体不投影给 LLM，但截断结果必须
  投影出 LLM 可执行的 `truncation.next_action` / `fetch_more_args`。
- P5 主用例必须使用真实 Engine loop + real provider smoke 或 fake-provider integration test，并验证调用链是
  `Runner tool call -> Agent -> ToolExecutor.execute -> ToolRuntimeToolExecutor -> InMemoryToolRuntime ->
  huge_echo executor`。`InMemoryToolRuntime.execute_tool_call()` 的直接调用只允许出现在辅助回归或诊断中，
  不能替代主路径证明。
- 为了稳定组合 compact / memory 使用 scripted WorkerProxy 时，该路径只能作为辅助 case；现有 P2 / P3 / P4
  测试也只能作为补充回归，不能替代 P5 主路径证明。
- Engine 不理解 memory、claim、evidence anchor、cursor、compact policy；P5 不改变该边界。
- 真实 provider case 只能作为 optional smoke，不作为 CI 必跑测试。

## EventLog / RunEventStore / projection 影响

P5 依赖 P1.5 EventLog 语义，不新增 projection。

P5 必须验证：

- 每轮首个可观察 canonical 事实包含 `USER_INPUT_ACCEPTED`，其 cursor 是本 run per-run cursor。
- 工具截断、cursor issued、模型发起的 fetch_more requested/completed 都是 canonical facts，且可通过
  `stream_run_events(after=...)` 补读观察；terminal 后 fetch_more typed failure 不追加 canonical fact。
- terminal result 只从 terminal RunEvent 推导。
- memory projection 在 terminal 后读取同一 run canonical facts。
- 第二轮 RunInput 中的 source cursor 能回指上一轮 canonical facts。
- 第二轮 RunInput 必须同时保留 P3 stable layer 中的 pinned_state / task frame、上一轮 recent raw turn、tool fact
  与 source cursor。
- compact retry 的第二次 attempt input 必须同时保留 caller system prompt、当前 user、pinned_state、必要 tool fact /
  evidence anchor / source cursor。
- compact facts 与 terminal facts 共用同一 RunEventStore，且 append-before-stream。

不允许：

- smoke 自己维护 transcript / event list 作为断言真源。
- 从 `StartRunRequest.input` 旁路读取上一轮用户输入来证明 memory 成功。
- 从 preview delta 拼 final answer 或 tool fact。

## 可接受临时实现 / 不可接受临时实现

可接受：

- 单进程 in-memory harness。
- P5 integration 测试使用 fake provider / fake LLM 触发 deterministic tool call、final answer 与 overflow event
  stream；手工 smoke 主路径不接受 fake provider 作为成功。
- scripted WorkerProxy 仅用于辅助 / 诊断 case，例如 compact retry 的 deterministic overflow；不能作为主 happy path。
- fake business ToolExecutor 返回长 list / text，用真实 ToolRuntime 截断；P5 主用例优先复用
  `huge_echo`。该工具必须改为使用 P5 公共 `@tool` declaration 能力生成强类型
  `ToolDefinition` / `ToolBundle`，而不是继续扩展 `utils` 局部 smoke registry。`huge_echo` 默认返回足够大的
  文本，并可在辅助测试中返回足够大的 list / JSON wrapper，使 ToolRuntime truncate 稳定触发；它由真实
  `Engine / Agent tool loop -> ToolExecutor.execute -> ToolRuntimeToolExecutor -> InMemoryToolRuntime` 路径产生
  truncation / cursor / fetch_more facts。
- `mimo-v2.5-pro-plan` 手工 smoke 缺配置时 clear failure，返回非零；compact/overflow 辅助 fake case 可以独立运行。
- smoke 输出中性摘要与 event cursor。

不可接受：

- 为 smoke 新增生产兼容 wrapper / facade / re-export。
- 为了让 smoke 通过，把 `EngineWorker`、`LocalProxy`、`DefaultRunInputBuilder`、`RunInputBuildTrace` 暴露到
  `dayu.host.__all__`。
- 在 Host 里硬编码 provider overflow 字符串；真实 overflow 仍归 Engine / Runner classifier。
- 手工构造 memory snapshot 冒充上一轮投影成功，除非该 case 明确只是 P4 compact fake snapshot 子 case；P5 主路径必须
  通过 terminal projection 产生 memory。
- 手工构造 tool runtime facts 冒充真实截断 / cursor / fetch_more 成功；P5 主路径必须由真实
  `InMemoryToolRuntime` 产生这些 facts。
- 由 scripted WorkerProxy 直接手写 `TOOL_RESULT_ACCEPTED` 或 tool result facts 作为主 happy path 证明。
- 在主 happy path 中直接调用 `InMemoryToolRuntime.execute_tool_call()` 替代 Engine / Agent 发起的 tool call
  与 `ToolExecutor.execute` 调用。
- 继续把 `utils.host_smoke_tools.py` 的局部 `SmokeToolRegistry` / 局部泛名 `tool` 当作最终 P5 目标；它只能作为
  废弃背景，P5 实施应删除临时产物并迁移到公共声明能力。
- 在 `utils/host_smoke_tools.py` 继续维护 `huge_echo` 或任何 P5 smoke 工具；公共 `@tool` declaration 落地前，
  不应用新的 utils seam 替代。
- 把 fixture 预置的 pinned_state / task frame 解释为 public memory edit API，或要求 P5 自动从用户输入 /
  工具事实中抽取 pinned_state。
- 打印 `scope_token`、完整 cursor、完整大工具结果、完整 Host Memory / compact memory block。
- 把未落地的幂等、并发、恢复、Outbox、audit hard-gate 写成当前事实。

## runtime dependency

P5 不新增 `dayu.runtime` 能力，不涉及 lane。

如果 smoke / test 需要等待 terminal，应使用本地 async helper 或现有测试 helper；不得把 Host 业务语义 helper 放进
`dayu.runtime`。若发现多个层都需要相同通用 cancellation / race helper，应先停止并单独评估是否属于
`dayu.runtime`，不能在 P5 顺手扩展。

## 实现步骤

1. 复核当前 P1-P4 代码路径：
   - `LocalRunHarness.start_run`、`_run_to_store`、compact retry loop。
   - `InMemoryToolRuntime` execute / fetch_more。
   - `InMemoryConversationMemoryStore.project_run_events`。
   - `DefaultRunInputBuilder.build` 与 trace。
   - `utils/smoke_host_eventlog.py`、`utils/smoke_host_tool_runtime.py`、
     `utils/smoke_host_conversation_memory.py`、`utils/smoke_host_context_compaction.py`。
2. 设计并落地最小公共 tool declaration：
   - 选择 contracts 层或等价公共契约位置，避免放入 `dayu.runtime` 或 Host 业务层。
   - 提供 `@tool` decorator / declaration helper 与强类型 `ToolDefinition` / `ToolBundle`。
   - 确认 `ToolSchema`、callable / executor binding、`ToolTruncateSpec` 与 display metadata 同源声明但职责分离。
   - 明确 `ToolDisplayInfo` / `tags` 不进入 LLM schema；`ToolTruncateSpec` 本体不进入 LLM schema，但截断后的
     tool result 必须投影 LLM-readable `truncation.next_action` / `fetch_more_args`。
   - 明确 Engine input projection API，例如 `to_tool_schema()` 或只读 `schema`，并约束 Host 装配只把
     `tuple[ToolSchema, ...]` 传给 Engine / Runner。
   - 命名上优先使用 `_get_xxx_tool_definition(...)` / `_get_xxx_tool_bundle(...)`；只有纯 schema factory 才使用
     `_get_xxx_tool_schema(...)`。
3. 将 `huge_echo` 纳入公共声明能力用例：
   - 不保留当前 `utils/host_smoke_tools.py` 的局部 registry 临时方向；`huge_echo` 直接作为公共
     `@tool(..., truncate=ToolTruncateSpec(...))` declaration 用例。
   - `huge_echo` 默认返回足够大的文本；辅助测试可以用同一声明能力定义 list / JSON wrapper 返回形态，用于覆盖
     `list_items`、`target_field` 或 `field_path` 等 ToolRuntime 截断路径。
   - factory 返回强类型 `ToolDefinition` / `ToolBundle`，供测试同时拿到 LLM schema、executor binding、
     `ToolTruncateSpec` 与 display metadata。
4. 编写 P5 integration 测试 fixture：
   - 使用单个 `LocalRunHarness` 实例共享 event store、tool runtime、memory store。
   - integration happy path 使用真实 EngineWorker / Engine / Agent tool loop，fake provider / fake LLM 只负责按脚本
     产出 `huge_echo` tool call 与后续 final answer。
   - 使用 fake ToolExecutor 或 `huge_echo` executor 作为业务工具返回边界；该 executor 只能返回业务结果，
     不能手写 Host ToolRuntime facts。
   - scripted WorkerProxy 只能用于辅助 / 诊断 case，例如 compact retry 的 deterministic overflow，不得替代
     happy path。
   - fake ToolExecutor 优先使用公共 declaration 产出的 `huge_echo` definition / bundle；返回值必须足够大，
     使 `ToolTruncateSpec` 稳定触发。
   - 主用例必须通过 `ToolExecutor.execute -> ToolRuntimeToolExecutor -> InMemoryToolRuntime` 产生截断、cursor 与
     fetch_more facts，不能手写 tool runtime facts，也不能直接调用 `InMemoryToolRuntime.execute_tool_call()` 代替
     Engine / Agent 发起的 tool call。
   - fixture 可以预置 P3 已落地 memory slot 中的 pinned_state / task frame，用于观察 stable layer 纵向保留；
     这不是 public memory edit API，也不要求 P5 自动抽取 pinned_state。
   - 只把 provider / LLM 输出与 business tool result 作为 fake 边界。
5. 实现 happy path 测试：
   - turn 1：integration 测试中的 fake provider / fake LLM 在 Runner 边界产出 `huge_echo` tool call；
     Engine / Agent 执行普通
     tool calling 闭环，调用 `ToolExecutor.execute`。
   - `ToolRuntimeToolExecutor` 调用真实 `InMemoryToolRuntime`，`huge_echo` executor 返回长结果，Host ToolRuntime
     按 `ToolTruncateSpec` 产生 truncation / cursor facts。
   - Engine 注入给模型的 tool result 必须包含 `truncation.next_action="fetch_more"` 与可直接照抄的
     `fetch_more_args`。
   - fake provider / fake LLM 或真实 provider 必须在同一 run 内继续产出 `fetch_more` tool call；Engine /
     Agent 将其作为普通 LLM tool call 执行，Host ToolRuntime 识别 framework tool 并 append fetch_more
     requested / completed。
   - 如果还有剩余内容，`fetch_more` 返回结果继续带下一页 cursor hint；测试至少覆盖一次成功 fetch_more，
     并验证旧 cursor single-use。
   - 模型拿到足够内容后继续产出 final terminal，并等待 memory projection。
   - terminal 后再次调用旧 cursor 或剩余 cursor 可作为负例：断言返回 `run_terminal` typed failure、
     `denied=False`、`event_cursor=None`，且 EventLog 事件数不增加。
   - turn 2：等待 turn 1 terminal 后启动，断言 Engine 收到的 RunInput / trace 包含上一轮 user、final、
     tool truncation fact、模型发起的 fetch_more completed fact、source cursor、pinned_state / task frame 与
     recent raw turn。
6. 实现 compact retry 组合测试：
   - 在已有 memory / tool facts 后启动一轮 scripted overflow。
   - 第一次 attempt 产出 `CONTEXT_COMPACTION_REQUESTED` + recoverable
     `RUN_FAILED(context_compaction_required)`。
   - Host append overflow / compact / retry facts。
   - 第二次 attempt 成功 terminal。
   - 断言同一 run 只有一个 `USER_INPUT_ACCEPTED`；compact 后输入包含 caller system prompt、当前 user、
     pinned_state、必要 tool fact / evidence anchor / source cursor。
7. 实现手工 smoke：
   - 输出格式稳定、短行、适合人工观察。
   - 默认 `--case all` 必须先跑真实 `mimo-v2.5-pro-plan` 主路径，再跑 compact retry 辅助 case。
   - `--case real-provider` / `--case all` 必须使用脚本内 hardcoded `ProviderCase`；缺 `MIMO_PLAN_API_KEY`、
     model、endpoint、`supports_tool_calling=true` 或必要 provider request 配置时输出 clear failure，不返回成功。
   - `MimoThinkingExtension(enabled=True)` 是 hardcoded ProviderCase 的一部分，smoke 输出和 review 必须显式说明
     该选择不读取、也不以 `llm_models.json` 为真源。
   - 主路径必须向模型发送明确 prompt，要求模型调用 `huge_echo`，并在收到截断 hint 后继续调用 `fetch_more`。
     若真实模型直接 final、未调用 `huge_echo`、未根据 hint 调用 `fetch_more`，smoke 必须失败，不能用
     scripted WorkerProxy 或 smoke 脚本代调 Host public API 补造成功。
8. 文档同步：
   - `docs/host/design.md` 增加 “P5 后 no-full-governance multi-turn smoke 执行路径”。
   - `dayu/host/README.md` 更新当前状态与 smoke 命令。
   - `tests/README.md` 更新新增测试层级。
9. 验证：
   - 运行 P5 新测试、`tests/host`、必要 engine 测试与 `pyright`。
   - 手工跑 smoke，确认无敏感字段和 delta 刷屏。

## 测试清单

新增测试建议集中在 `tests/host/test_phase5_multiturn_no_governance_smoke.py`：

- `test_phase5_sequential_multiturn_stitches_eventlog_toolruntime_memory`
  - 单 harness、同 session、两轮顺序执行。
  - 同一个 `LocalRunHarness`、`InMemoryRunEventStore`、`InMemoryToolRuntime` 与 memory store 参与主路径。
  - fake provider / fake LLM 必须产出 `huge_echo` tool call；Engine / Agent 必须通过普通 LLM tool calling
    闭环调用 `ToolExecutor.execute`。
  - cursor 必须由 `ToolExecutor.execute -> ToolRuntimeToolExecutor -> InMemoryToolRuntime` 按
    `huge_echo` 的 `ToolTruncateSpec` 生成。
  - 测试必须能观察或断言 `ToolExecutor.execute` 被调用，且调用来源是 Engine / Agent tool loop，而不是
    smoke/test 直接调用 ToolRuntime。
  - fake WorkerProxy 不得手写 `ToolResultTruncatedData`、`ToolCursorIssuedData` 或 `TOOL_RESULT_ACCEPTED`
    冒充 tool runtime facts；scripted WorkerProxy 只能用于辅助 / 诊断 case。
  - turn 1 terminal 后 memory projection 发生。
  - turn 2 RunInputBuilder 看到 turn 1 user / final / tool truncation fact / 模型发起的 fetch_more completed fact /
    source cursor。
  - turn 2 RunInputBuilder 同时看到 fixture 预置的 pinned_state / task frame 与上一轮 recent raw turn。
- `test_phase5_model_fetch_more_tool_call_uses_framework_runtime_and_preserves_single_use`
  - 截断由 schema spec 驱动；`huge_echo` 默认返回足够大的文本，辅助测试可返回 list / JSON wrapper，
    以稳定制造长结果；`huge_echo` 的 schema / metadata 由 P5 公共 OLD-like `@tool(...)` declaration 声明，
    并产出当前 NEW 的强类型 `ToolDefinition` / `ToolBundle`。
  - `huge_echo` 必须在主 happy path 中由 Engine / Agent LLM tool calling 调用，不能由测试直接调用
    `InMemoryToolRuntime.execute_tool_call()` 完成主证明。
  - 截断后的 LLM-facing tool result 必须包含 `truncation.next_action="fetch_more"` 与 `fetch_more_args`。
  - `fetch_more` 必须作为 framework tool 暴露给 LLM，且由模型在同一个 run 内再次 tool calling；测试不能用
    `harness.fetch_more_tool_result()` 替代 success path。
  - handle 读取不泄漏 scope token 到 EventLog。
  - owner run 未 terminal 时模型发起的 fetch_more completed 有 event cursor。
  - terminal 后补读返回 `run_terminal` typed failure、`denied=False`、`event_cursor=None`，且 EventLog 事件数不增加。
- `test_tool_declaration_keeps_schema_runtime_and_display_metadata_separate`
  - `@tool(..., truncate=ToolTruncateSpec(...))` 同现场声明 LLM schema 与 Host truncate metadata。
  - 返回值包含 name、callable / executor binding、`ToolSchema`、`ToolTruncateSpec`、`ToolDisplayInfo` / `tags`。
  - definition / bundle 提供显式 schema projection，例如 `to_tool_schema()` 或只读 `schema`。
  - definition / bundle 投影给 Engine 的结果只能是 `ToolSchema`，不包含 `ToolTruncateSpec`、display metadata、
    `tags`、callable 或 executor binding。
  - `ToolDisplayInfo` / `tags` 不进入 LLM schema。
  - `ToolTruncateSpec` 不进入 LLM schema；截断 result projection 生成 LLM-facing `truncation` hint。
  - framework `fetch_more` schema 与业务工具 schema 一起暴露给 Engine / Runner，但它不携带业务
    `ToolDefinition` / display metadata。
- `test_phase5_engine_and_worker_requests_only_receive_tool_schema_tuple`
  - `AgentRunRequest.tool_schemas` 与 WorkerProxy request 只含 `ToolSchema` tuple。
  - request 中不得出现 `ToolDefinition` / `ToolBundle`。
  - request 中不得出现 `ToolTruncateSpec`、display metadata、`tags`、callable 或 executor binding。
- `test_phase5_compact_retry_is_same_run_internal_attempt_not_new_user_turn`
  - overflow run 只 append 一次 `USER_INPUT_ACCEPTED`。
  - compact requested / completed / attempt retry facts 顺序可观察。
  - 第二次 attempt 使用 compacted RunInput。
  - 第二次 attempt input 同时保留 caller system prompt、当前 user、pinned_state、必要 tool fact /
    evidence anchor / source cursor。
- `test_phase5_preview_and_reasoning_do_not_enter_next_turn_or_compact`
  - fake stream 中可加入 preview delta / reasoning delta；下一轮 RunInput 与 compact 输入不包含它们。
- `test_phase5_smoke_script_outputs_safe_summary`
  - 轻量调用 smoke main / subprocess 或解析函数。
  - 断言输出不包含 `scope_token`、完整大结果、raw cursor、delta 内容。

已有测试仍应继续覆盖：

- `tests/host/test_phase1_5_event_store.py`
- `tests/host/test_phase2_tool_runtime_truncation.py`
- `tests/host/test_phase2_tool_runtime_eventlog.py`
- `tests/host/test_phase3_multiturn_smoke.py`
- `tests/host/test_phase4_overflow_retry.py`
- `tests/host/test_phase4_context_compaction.py`

## 手工 smoke

新增脚本建议：

```bash
python utils/smoke_host_multiturn_no_governance.py --case all --log-level INFO
python utils/smoke_host_multiturn_no_governance.py --case real-provider --log-level DEBUG
python utils/smoke_host_multiturn_no_governance.py --case compact-retry --log-level DEBUG
```

建议输出示例形状：

```text
SMOKE case=real-provider provider=mimo model=mimo-v2.5-pro endpoint=... request_sent=True
SMOKE case=real-provider session_id=...
SMOKE turn=1 user_input_accepted.cursor=0
SMOKE turn=1 llm_tool_call tool=huge_echo via_engine_tool_loop=True executor_execute_called=True
SMOKE turn=1 tool_truncated.cursor=...
SMOKE turn=1 cursor_issued fingerprint=... event_cursor=...
SMOKE turn=1 llm_tool_call tool=fetch_more via_engine_tool_loop=True
SMOKE fetch_more completed actor=model has_more=... event_cursor=...
SMOKE turn=1 terminal type=final_answer cursor=...
SMOKE fetch_more post_terminal result=run_terminal denied=False event_cursor=None event_count_unchanged=True
SMOKE turn=2 user_input_accepted.cursor=0
SMOKE turn=2 run_input contains_previous_user=True contains_previous_final=True contains_tool_fact=True contains_source_cursor=True
SMOKE turn=2 run_input contains_pinned_state=True contains_task_frame=True contains_recent_raw_turn=True
SMOKE turn=2 terminal type=final_answer cursor=...
SMOKE case=compact-retry run_id=...
SMOKE compact overflow_observed.cursor=...
SMOKE compact completed before_tokens=... after_tokens=... dropped=...
SMOKE compact retry_count=1 user_input_accepted_count=1
SMOKE compact retry_input contains_system=True contains_current_user=True contains_pinned_state=True contains_tool_fact=True contains_source_cursor=True
SMOKE compact terminal type=final_answer cursor=...
```

`--case real-provider` / `--case all` 要求：

- 必须使用脚本内 hardcoded `ProviderCase`：env 使用 `MIMO_PLAN_API_KEY`，case 名为
  `mimo-v2.5-pro-plan`，endpoint 为 `https://token-plan-cn.xiaomimimo.com/v1/chat/completions`，
  model 为 `mimo-v2.5-pro`，`supports_tool_calling=true`，`supports_stream_usage=false`，
  `provider_request` 为 `MimoThinkingExtension(enabled=True)`。
- `utils/smoke_async_agent_providers.py` 既有同名 case 只作为范式参考；P5 smoke 不读取
  `dayu/config/llm_models.json` 或 `workspace/config`，并在输出与 review 中显式说明
  `MimoThinkingExtension(enabled=True)` 是 hardcoded ProviderCase 的有意选择。
- 缺 key、缺 model 或缺 endpoint 时输出 `SMOKE real_provider=failed reason=missing_config` 并返回非零。
- prompt 必须明确要求模型调用 `huge_echo`；若模型直接 final、拒绝 tool calling 或调用其它工具，smoke 失败。
- 成功 fetch_more 必须发生在 owner run terminal 前，且 actor 必须是模型发起的 `fetch_more` tool call；若真实模型
  太快给 final 或忽略截断 hint，smoke 必须失败。smoke 输出和测试 / 人工检查必须能观察该证据，并证明没有绕过
  Engine / Agent tool loop。

## 验证命令

实施完成后至少运行：

```bash
source .venv/bin/activate
pytest tests/contracts/test_tool_declaration.py -q
pytest tests/host/test_phase5_multiturn_no_governance_smoke.py -q
pytest tests/host -q
pytest tests/engine -q
pyright
python utils/smoke_host_multiturn_no_governance.py --case all --log-level INFO
```

手工 smoke 验证命令需要真实 `MIMO_PLAN_API_KEY`；缺配置时应返回 clear failure，不能计为通过。

如果修改了 smoke 参数解析，补跑：

```bash
pytest tests/engine/test_smoke_async_agent_providers.py -q
```

只有在实际修改 Engine / OpenAI runner 时，才需要额外运行：

```bash
pytest tests/engine/runners/openai -q
```

## README / docs 同步

P5 实施后必须同步：

- `docs/host/design.md`
  - 增加 P5 后执行边界：单进程、单调用方、顺序多轮 smoke 如何把 P1-P4 串通。
  - 明确 P5 仍不是生产治理，active Run admission、幂等、多进程恢复、Outbox、observer 均未落地。
  - 写明手工 smoke 主路径使用真实 `mimo-v2.5-pro-plan` provider；fake provider 只服务 CI / integration /
    compact 诊断，不改变 Host 事实链路，也不能替代手工 smoke 成功。
  - 写明最小公共 tool declaration 只统一 schema / executor binding / truncate / display metadata 的声明出口，
    不等同完整 ToolRegistry 或 Host 治理入口。
  - 同步清理或限定 `12.10 P3 最小落地与后移能力` 的旧口径：P3 当时未落地
    context overflow compact / retry，但 P4 已落地当前 Host compact / retry 最小路径；不得让同一文档同时声称
    P4/P5 已落地和该能力当前未落地。
- `dayu/host/README.md`
  - 当前状态从 P4 更新为 P5。
  - 当前手工验证新增 `utils/smoke_host_multiturn_no_governance.py` 命令。
  - 当前工具接入口径写为使用公共 `ToolDefinition` / `ToolBundle` 声明 smoke 工具，不把 `utils` 局部 registry
    写成公共 API。
  - 当前未落地能力仍保留，不把 smoke 写成生产能力。
- `tests/README.md`
  - 新增 P5 integration guard 描述。
  - 新增 P5 tool declaration / `huge_echo` smoke 工具测试说明，不再保留旧的 utils 局部 smoke 工具测试口径。
  - 补充运行命令。
  - 将 Host 小节总述从 P3 口径调整为当前 P4/P5 事实，避免标题级总述落后于 P4 context compact 与 P5
    integration guard。

不更新根目录 `README.md`，除非 P5 实施改变了项目级用户命令或 CLI 入口。

## Review Gate

Plan review gate：

- 常规 plan review：检查目标、非目标、文件清单、测试、验证、文档同步是否完整。
- 纵向语义 review：对照 P1-P4 与 OLD 强参考，重点审 P5 是否真的复用生产路径，是否把未迁移生产治理误判成 bug，
  是否覆盖语义与实现逻辑错位风险。
- tool declaration 范围变更 review：本次新增 scope 以
  `docs/host/phase5-tool-declaration-plan-review.md` 为新增 plan review gate；旧 P5 plan review 的通过结论不能
  单独代表当前 tool declaration scope。进入实现前必须以该文件的“有条件通过”及其 finding 修订状态为准。

Code review gate：

- 常规 code review：bug、类型、边界、测试、文档。
- P5 vertical smoke review：必须专门检查：
  - smoke / tests 是否手工造 facts 绕过 EventLog、ToolRuntime、Memory、RunInputBuilder 或 CompactCoordinator。
  - 是否打印敏感信息或 delta 刷屏。
  - 是否错误暴露 internal API。
  - 是否把 P7+ 治理能力写成当前事实。
  - 是否把 `utils` 局部 smoke registry 当成最终 P5 目标，而不是迁移到公共 `@tool` declaration 能力。
  - 是否保持 `ToolDisplayInfo` / `tags` 与 LLM-facing schema 分离，同时只恢复最小 framework `fetch_more`
    tool 与 truncation hint，没有滑向完整 ToolRegistry / 权限治理。
  - 是否通过 `to_tool_schema()` 或只读 `schema` 等明确 projection 把 definition / bundle 降为
    `ToolSchema` tuple 后再传入 Engine / Runner。
  - 是否断言 Engine request / WorkerProxy request 不含 `ToolTruncateSpec`、display metadata、tags、callable
    或 executor binding。
  - 手工 smoke 是否真实向 `mimo-v2.5-pro-plan` 发送 prompt，并由模型发起 `huge_echo` tool calling；
    缺配置、直接 final 或未调用 `huge_echo` 时是否 clear failure，而不是 fake 成功。
  - 成功 fetch_more 是否在 owner run terminal 前由模型通过 LLM tool calling 完成；若实现仍由 smoke 脚本直接调用
    Host public `fetch_more_tool_result`，review 必须判定不通过。
  - smoke 输出和测试 / 人工检查是否能直接观察 real-provider 主路径证据：cursor facts 来自真实
    `ToolRuntimeToolExecutor -> InMemoryToolRuntime`，模型发起的 `fetch_more completed` cursor 早于 terminal cursor，
    `via_engine_tool_loop=True` / `executor_execute_called=True` 等字段来自实际观测而非脚本常量。
  - `mimo-v2.5-pro-plan` 是否沿用 `utils/` provider smoke 的 hardcoded ProviderCase 范式，不读取
    `llm_models.json`；`MimoThinkingExtension(enabled=True)` 是否在代码、输出和 review 中被标注为有意选择。
  - 是否覆盖 semantic vs implementation mismatch，例如 `start_run` 语义上启动 run，但实际必须 await 后已启动；
    compact retry 语义上是 internal attempt，但实现不能追加第二个 `USER_INPUT_ACCEPTED`。

PR review gate：

- PR diff review 必须确认 P5 PR 只包含 P5 范围内提交。
- 若 PR review 有 finding，迁移 Agent 修复后必须在对应 review 文档 finding 标题标注修复状态，并由 review Agent
  复查通过。

## 停止条件

实施 Agent 遇到以下情况必须停止并回报总控，不得硬写：

- 需要新增或改变 Host public API 才能完成 smoke。
- 需要把公共 tool declaration 做成完整 ToolRegistry、权限治理或业务工具迁移才能完成 smoke。
- 无法用强类型 `ToolDefinition` / `ToolBundle` 同源携带 schema、executor binding、truncate 与 display metadata，
  只能继续依赖 `utils` 局部 registry。
- 无法提供明确的 definition / bundle 到 `ToolSchema` 的 projection，或实现必须把 `ToolDefinition` /
  `ToolBundle` 本体传给 Engine / Runner 才能完成 smoke。
- Engine request / WorkerProxy request 中出现 `ToolTruncateSpec`、display metadata、tags、callable 或 executor
  binding。
- 需要修改 Engine compact / retry 责任边界。
- 需要实现 active Run admission、start_run 幂等、持久 EventLog、多进程 recovery 或 Outbox 才能通过。
- P5 主路径无法使用真实 `LocalRunHarness` / `RunEventStore` / `ToolRuntime` / `ConversationMemoryStore` /
  `RunInputBuilder` / `ContextCompactCoordinator`，只能靠手工构造 facts。
- 手工 smoke 无法真实调用 `mimo-v2.5-pro-plan`，或只能用 fake provider / scripted WorkerProxy 替代模型
  `huge_echo` tool calling。
- 无法在 owner run terminal 前由模型通过 LLM `fetch_more` tool call 完成成功补读，只能由 smoke 脚本代调
  Host public API、terminal 后补读或手写 fetch_more facts。
- 无法证明模型发起的 `fetch_more completed` 发生在 final terminal 前，或证明该 tool call / fetch_more 证据来自真实
  Engine / Agent tool loop 与 ToolRuntime 路径。
- hardcoded `ProviderCase` 的 endpoint、model、capability 或 `MimoThinkingExtension(enabled=True)` 不能被代码、
  输出和 review 明确说明，导致 P5 smoke 口径重新混同为配置 adapter。
- 发现 P1-P4 文档声称已落地，但代码路径直接证据不支持。
- 为了组合 smoke 需要打印 scope token、raw cursor、完整大工具结果或完整 prompt。
- `pyright` 出现新增或扩散错误。

## 风险与回滚

风险：

- fake WorkerProxy 过强，导致 smoke 没有真正覆盖 Engine tool loop。缓解：P5 主测试必须明确哪一段用 fake，
  主用例必须由真实 `InMemoryToolRuntime` 产生 tool runtime facts；现有 P2 / P3 / P4 测试只作为补充回归。
  必要时增加一个真实 Engine loop + fake ToolExecutor 的小 case。
- 手工 smoke 输出过多，影响人工观察。缓解：默认只输出摘要，DEBUG 也不输出 delta / 大结果。
- P5 容易被误写成 lifecycle governance。缓解：测试命名、README 和 design 均使用 no-full-governance / sequential
  smoke 口径。
- terminal 后 fetch_more 的当前契约可能限制“先 terminal 再补读”观察。缓解：按 P2 当前事实设计 smoke；
  如果需要 terminal 后补读审计，应后移 P6 / P7，不在 P5 偷改。
- 真实模型可能直接 final、调用其它工具或忽略截断 hint。缓解：prompt 明确要求调用 `huge_echo` 并根据
  `truncation.next_action="fetch_more"` 继续调用 framework `fetch_more`；无法做到则 smoke 清晰失败，不能由脚本
  代调 Host public API 补造成功。
- context compact 默认 deterministic 策略可能丢弃 older raw turns，使 smoke 对“多轮连续性”的期望过强。缓解：
  P5 对 compact 只断言必保事实，不断言旧 raw turn 全量保留。
- `@tool` declaration 与 framework `fetch_more` 容易滑向完整 registry。缓解：P5 只定义 declaration /
  definition 输出和 framework fetch_more 路由，明确不做权限治理、middleware、业务发现或 Service catalog。

回滚：

- P5 主要是测试、smoke 与文档；若实现暴露设计缺口，可回退 P5 新增测试 / smoke / docs，保留 P1-P4 代码不动，
  重新修 plan。

## 待用户确认项

当前无阻塞开放问题。默认决策如下：

- P5 手工 smoke 主路径使用真实 `mimo-v2.5-pro-plan` provider；fake provider 只允许作为 P5 integration 测试或
  compact/overflow 辅助诊断。
- P5 测试文件命名为 `tests/host/test_phase5_multiturn_no_governance_smoke.py`。
- P5 手工 smoke 命名为 `utils/smoke_host_multiturn_no_governance.py`。
- P5 不新增 public API；如实现时发现必须新增 public 入口，停止并回到总控讨论。
- P5 按用户人工 review 决策纳入最小公共 `@tool` declaration 能力；`huge_echo` 作为第一个 smoke/test 工具，
  当前 `utils` 局部 smoke registry 方向已废弃，不作为最终 P5 目标。

## 迁移 Agent 实施完成汇报格式

实施 Agent 完成后按以下格式汇报：

```text
P5 implementation completed

Changed files:
- ...

Core behavior:
- Tool declaration:
- Sequential multi-turn path:
- Tool truncate / fetch_more path:
- Memory / RunInputBuilder continuity:
- Context overflow compact retry:
- No-full-governance boundaries preserved:

Semantic guards:
- USER_INPUT_ACCEPTED count:
- append-before-stream:
- preview / reasoning isolation:
- compact retry is internal attempt:
- sensitive smoke output:

Verification:
- pytest tests/contracts/test_tool_declaration.py -q
- pytest tests/host/test_phase5_multiturn_no_governance_smoke.py -q
- pytest tests/host -q
- pytest tests/engine -q
- pyright
- python utils/smoke_host_multiturn_no_governance.py --case all --log-level INFO

Docs:
- docs/host/design.md:
- dayu/host/README.md:
- tests/README.md:

Remaining risks / deferred scope:
- ...
```
