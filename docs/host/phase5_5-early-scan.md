# Host P5.5 Early Scan：Agent Runtime 缺口预扫

## 结论

目标动机基本成立，但当前证据应收窄为：P1-P4 已经把 Host + Engine 的单进程最小运行链路搭起来；P5 计划要求的“把 tool truncate / fetch_more、memory、context compact 串成同一纵向 smoke”尚未落地。因此，现在不能直接声明“只要接入 tool 就能工作”，只能声明“内部 harness 具备接入 ToolExecutor 的路径，且各段能力已有分段测试”。

离“Host + Engine 作为可工作 Agent runtime，只要接入 tool 就能工作”，除生产治理外还缺三类非治理能力：

1. 真实 tool 接入面：public `start_run` 默认只装配 `_NoopToolExecutor`，没有面向 Service / app 的 ToolExecutor / tool catalog 装配入口；真实工具只能通过内部 `LocalRunHarness` 注入。
2. LLM 主动补读闭环：早期扫描时 P2/P5 仍未恢复 LLM-facing `fetch_more` schema / `fetch_more_args`
   projection；后续 revised P5 已承接最小 framework `fetch_more` tool 与 truncation hint，使模型能在
   同一个 run 内自行补读。P5.5 只复核该能力是否落地、是否仍停留在最小实现、是否需要升级到完整
   ToolRegistry / governance。
3. P5 纵向 smoke 证据：当前没有 P5 smoke 脚本与 P5 integration test，尚未证明真实 `LocalRunHarness -> RunEventStore -> ToolRuntime -> MemoryStore -> RunInputBuilder -> CompactCoordinator` 在同一用例中串通。

所以，ToolRuntime truncate / fetch_more 不是唯一明显缺口；它的底层 Host public 补读路径已落地，revised P5
已承接 LLM 可见补读协议，真正缺的是“工具接入装配 + P5 纵向证明 + P5.5 复核升级边界”三者的组合。

## 目标成立性判断

用户目标里的第一性原理是成立的：一个可工作的 Agent runtime，不应依赖完整生产治理才能在单进程、顺序执行下完成“用户输入 -> 模型调用 -> 工具调用 -> 继续模型调用 -> 终态 -> 下一轮记忆”的基本链路。总控计划也把 P5 定义为 no-full-governance smoke，并明确不要求多进程、Remote、Outbox、audit hard-gate 等生产治理；同时强调不得绕过 EventLog、强类型和分层边界。

但“只要接入 tool 就应该能工作”这句话目前容易被高估。当前 public `start_run` 不接受 tool executor 配置，默认 harness 使用 `_NoopToolExecutor`，只有内部测试 harness 可以注入真实或 fake executor。若“接入 tool”指 Service 层/应用层以稳定 public API 注册工具并运行，那这不是 P5 已落地能力。

## 缺口表

| 能力 / deferred 项 | 来源 | 当前判断 | 直接证据 | 建议归属 |
| --- | --- | --- | --- | --- |
| RemoteProxy / RemoteStub / wire protocol | P1、P2、P3、P5 非目标 | P6+ 已安排，非当前 Agent runtime 阻塞 | P10 已安排 Remote；P1/P2/P3/P5 均列为非目标 | P10 |
| Session governance、同 Session active Run 仲裁、`client_request_id` 幂等 | P1、P1.5、P2、P3、P5 非目标 | P6+ 已安排；不是 no-governance smoke 阻塞 | P7 已安排；P5 只要求顺序执行 | P7 |
| 持久 EventLog / schema / recovery / lease / fencing | P1、P1.5、P2、P5 非目标 | P6+ 已安排；非当前目标 | P6/P8 已安排；当前 store 明确是单进程内存 adapter | P6/P8 |
| Event observers：tool trace、audit、timeline、metrics、checkpoint | P1.5、P2、P3、P5 非目标 | P6+ 已安排；非 smoke 阻塞 | P6 已安排 observer/projection；P2 facts 已写 canonical RunEvent | P6 |
| Reply Outbox | P3、P5 非目标 | P6+ 已安排；非 Agent runtime 核心阻塞 | P9 已安排 | P9 |
| 完整 ToolRegistry：发现、注册中心、display info、middleware、重复调用治理 | P1、P2、P5 非目标 | 未落地；对“只要接入 tool”有非治理影响 | Host public 不导出 ToolRuntime/ToolExecutor；默认 harness 不提供工具配置入口 | P5.5 需决定：拆最小 tool catalog 装配，完整治理留后 |
| 业务工具迁移 / fins 工具接入 | P2、P3 非目标 | 未落地；对真实财报 Agent 可用性有影响 | P2 明确 doc/web/fins 工具不迁入；当前 utils/test 使用 fake executor | P5.5 或单独业务工具 phase |
| LLM-facing `fetch_more` schema / `fetch_more_args` projection | 早期 P2/P5 非目标，revised P5 目标 | 已由 revised P5 承接；P5.5 复核是否落地、是否仍停留最小实现、是否要升级到完整 ToolRegistry / governance | P2 plan 只保留 Host public 补读；revised P5 要求恢复最小 framework `fetch_more` tool 与 truncation hint | P5 落地，P5.5 复核升级边界 |
| Host public `fetch_more_tool_result` | P2 目标 | 已落地 | `InMemoryToolRuntime.fetch_more`、Host public exports、P2 测试覆盖 single-use / terminal guard | 已落地，P5 纵向验证 |
| Conversation Memory / RunInputBuilder | P1/P1.5 非目标，P3 目标 | 已落地最小版 | memory 只投影 canonical RunEvent，RunInputBuilder 注入 Host memory + current user | 已落地，P5 纵向验证 |
| preview / reasoning 隔离 | P1/P3/P5 语义要求 | 已落地并有测试 | event translation 将 delta / content completed 归为 preview；memory 只消费 canonical | 已落地，继续守护 |
| context overflow compact / retry | P3 非目标，P4 目标 | 已落地最小版 | Engine classifier + Host compact retry loop + P4 tests | 已落地，P5 纵向验证 |
| 完整 context governance / token budget service / long-term memory governance | P4 非目标 | P6+ / 未细排；不是 P5 阻塞 | P4 明确不做完整 context governance | P6+ 设计 |
| OutputContract / validation replay | P4/P5 非目标 | 未安排在 P1-P13 表里作为独立 phase；可能缺失 | design 有 Replay / OutputContract 设计，但 migration phase 表未单列 | P5.5 建议新增归属 |
| Wait / suspend / resume | P3/P5 非目标 | P6+ 已安排 | P11 已安排；Engine 当前 awaiting 直接 failed | P11 |
| public memory edit / reset / forget / 跨 scope memory | P3/P5 非目标 | P6+ 或未细排；非 P5 阻塞 | P3 只预留 internal patch；P5 非目标 | P6+ / P12 前置设计 |
| P5 no-full-governance 纵向 smoke | P5 目标 | P5 应落地；当前未落地 | 当前 `rg --files tests/host utils | rg 'phase5|multiturn_no_governance|smoke_host_multiturn'` 无结果 | P5 阻塞 |

## 证据引用

- 总控计划把 P5 定义为只覆盖单进程、单调用方、顺序执行，并明确不要求幂等、active Run admission、断线重试或并发仲裁；这些治理能力仍留 P7。见 `docs/host/migration-plan.md:154`。
- P5 plan 要求新增 `utils/smoke_host_multiturn_no_governance.py` 与 P5 端到端测试，并且测试/smoke 必须走真实 P1-P4 生产路径。见 `docs/host/phase5-plan.md:22`、`docs/host/phase5-plan.md:28`。
- 当前文件扫描没有 P5 smoke 或 P5 test：`rg --files tests/host utils | rg 'phase5|multiturn_no_governance|smoke_host_multiturn'` 返回空。
- public `start_run` 默认 harness 使用 `_NoopToolExecutor`，并构造 `InMemoryToolRuntime(executor=_NoopToolExecutor())`；真实工具 executor 只能通过内部 harness 装配。见 `dayu/host/_run_harness.py:163`、`dayu/host/_run_harness.py:981`、`dayu/host/_run_harness.py:1016`。
- Host 内部真实 tool adapter 存在：`ToolRuntimeToolExecutor.execute()` 调到 `InMemoryToolRuntime.execute_tool_call()`，再按工具名读取 `truncate_specs`。见 `dayu/host/_tool_runtime.py:168`、`dayu/host/_tool_runtime.py:224`、`dayu/host/_tool_runtime.py:228`。
- Engine tool loop 确实只通过 `ToolExecutor.execute` 执行工具，并把 outcome 注入下一轮 Runner。见 `dayu/engine/agent.py:1002`、`dayu/engine/agent.py:1040`、`dayu/engine/agent.py:1104`、`dayu/engine/agent.py:1124`。
- Tool schema 与 truncate spec 的来源存在语义缝隙：`ToolTruncateSpec` 位于 `dayu.contracts.tool_schema`，但它“不进入 LLM-facing schema projection”；Host runtime 另有 `truncate_specs: Mapping[str, ToolTruncateSpec]`。见 `dayu/contracts/tool_schema.py:15`、`dayu/host/_tool_runtime.py:198`。
- 早期扫描证据显示，当时 P2 plan 不注册 LLM-facing `fetch_more` schema、不投影
  `fetch_more_args`；测试也断言 Engine projection 只输出 `{"preview": "abc"}` 且不含 token/hash。该状态已由
  revised P5 承接为最小 framework `fetch_more` tool 与 truncation hint，P5.5 只复核落地质量和升级边界。见
  `docs/host/phase2-plan.md:39`、`tests/host/test_phase2_tool_runtime_boundary.py:313`。
- context overflow 不是 Host 字符串猜测：Runner classifier 优先结构化 code，再受控 message fallback；Agent 将 `CONTEXT_LENGTH_EXCEEDED` 提升为 `CONTEXT_COMPACTION_REQUESTED`。见 `dayu/engine/runners/openai/error_classifier.py:92`、`dayu/engine/agent.py:850`。
- memory 只投影 terminal 后 canonical facts：Run harness 在 `terminal_seen` 后调用 `_project_run_events`，memory store 过滤 canonical event；assistant final answer 进入 raw turn，不自动成为 verified claim。见 `dayu/host/_run_harness.py:451`、`dayu/host/_conversation_memory.py:400`、`dayu/host/_conversation_memory.py:612`。

## Semantic vs Implementation Mismatch 风险

### 1. `ToolSchema` 与 `ToolTruncateSpec` 的声明来源未统一

计划语义写的是“工具 schema / tool metadata 上显式 truncate spec 驱动”。实现上，LLM-facing `ToolSchema` 不含 `ToolTruncateSpec`；`InMemoryToolRuntime` 通过构造参数 `truncate_specs` 按工具名另行注入。这个选择在 P2 是可接受的，但到“只要接入 tool”时会变成接入风险：应用如果只提供 `tool_schemas` 和 executor，工具能被 LLM 调用，但不会自动截断。

建议：P5.5 明确“最小 tool 接入契约”包含三件事：LLM-facing schema、executor binding、Host metadata/truncate spec binding。完整 ToolRegistry 可后移，但这三者不能再散在测试私有装配里。

### 2. 真实 ToolExecutor 接入不是 public runtime 能力

默认 public `start_run` 不暴露 ToolExecutor，也不暴露 tool runtime config。README 也写明 fake ToolExecutor 的 Host 测试使用内部 `LocalRunHarness` 装配。这符合 P1/P2 public boundary，但不满足“应用接入工具后即可运行”的产品语义。

建议：不要把内部 `LocalRunHarness` 直接 public 化；应设计一个 Host-owned `HostRuntime` / `RunHost` 组合根或 Service 层装配入口，使 ToolExecutor 与 tool metadata 在启动前注入，同时继续不暴露 `ToolExecutor.execute` 给 UI。

### 3. Engine tool loop 确实会使用 Host `ToolRuntimeToolExecutor`，但只在正确装配时成立

`EngineWorker` 把自己的 `tool_executor` 放进 `AgentRunRequest`，Engine 只调用该 executor。默认 harness 装的是 `ToolRuntimeToolExecutor(runtime)`，所以链路成立；但 runtime 里的底层 executor 默认是 `_NoopToolExecutor`。因此“Engine tool loop 使用 Host ToolRuntimeToolExecutor”是真，但“真实工具已接入”不真。

### 4. context overflow 已有真实 provider classifier 入口，不只是 fake

P4 前曾有“只能 fake”的风险；当前代码已经有 OpenAI-compatible classifier、Runner HTTP error 提升、Agent `CONTEXT_COMPACTION_REQUESTED` 事件与测试矩阵。限制是 provider shape 覆盖仍是 P4 矩阵范围，真实 provider smoke 不是 P5 必跑。

### 5. memory 投影只在 terminal 后发生，符合 P3 语义

当前 run 的 tool facts 在 overflow compact 前通过 `snapshot_with_transient_tool_facts()` 临时合并；普通下一轮 memory 仍只在 terminal 后投影。这与“只投影 terminal 后 canonical facts”一致，不是缺口。

### 6. Engine README 有残留口径风险

`dayu/engine/README.md` 当前仍写“OLD `TruncationManager` / `fetch_more` 尚未落地；这些能力不能通过当前 Agent 私自接入”。从 Engine 视角“Engine 不负责 fetch_more”是对的，但“尚未落地”容易误读为 Host P2 也未落地。P5/P5.5 后建议改成“Engine 不拥有 fetch_more 语义；Host ToolRuntime 已落地 Host public 补读路径，revised P5 承接 LLM-facing framework `fetch_more` 的最小闭环”。

## 建议进入 P5 / P5.5 / P6+ 的事项

### P5 必须进入

- 实施 P5 smoke 与 integration test。当前这是最直接阻塞：没有它，就没有纵向证据证明 P1-P4 同链路可工作。
- P5 主用例至少覆盖：真实 ToolRuntime 截断、截断 tool result 含 LLM 可理解的 `fetch_more` hint、模型在同一个 run 内经 Engine tool loop 主动调用 framework `fetch_more`、terminal 后 Host public `fetch_more_tool_result()` typed failure、第二轮 memory 看到上一轮 user/final/tool/fetch_more fact、overflow compact retry 不重复 `USER_INPUT_ACCEPTED`。
- Host public `fetch_more_tool_result()` 只能作为 framework tool 路由复用的底层边界和 terminal 后 negative path；不能作为 P5 success path actor。
- P5 不应试图解决 public tool registry；若主路径需要真实 tool executor，仍可用内部 harness 装配，但报告必须明确这只是测试装配，不代表应用接入面已完成。

### P5.5 应作为边界修订进入

- 定义“最小 tool 接入契约”：`ToolSchema`、`ToolExecutor`、`ToolTruncateSpec` / metadata 的同源绑定方式。可以不做完整 ToolRegistry，但要避免未来 Service 接入工具时只接了 LLM schema 而漏接 Host truncation metadata。
- P5 修订后已确认 LLM-facing framework `fetch_more` 属于“Agent runtime 可工作”的必要条件；P5.5 只需要回看它是否已经按 revised P5 落地、是否仍停留在最小实现，以及是否需要升级为完整 ToolRegistry / governance 能力。
- 给 OutputContract / validation replay 找归属。design 已有 replay / OutputContract 设计，但 P6-P13 表中没有独立承接；对财报分析 Agent，输出契约不是生产治理本身，而是回答可靠性的非治理能力。

### P6+ 保持后移

- P6：持久 EventLog、observer/projection、tool trace、audit、timeline、metrics。
- P7：Session/Run lifecycle、`client_request_id` 幂等、active Run admission、取消基础治理。
- P8：attempt lease、fencing、startup recovery、多进程。
- P9：Reply Outbox。
- P10：RemoteProxy/RemoteStub。
- P11：wait/suspend/resume。
- P12：强制终止、audit hard-gate、required projection 等生产治理。

## 阻塞 / 非阻塞分类

### 阻塞“P5 目标成立”的事项

- P5 smoke/test 文件缺失，纵向 smoke 尚未落地。
- P5 没有证明同一主路径同时经过真实 ToolRuntime、模型发起的 framework `fetch_more`、memory projection 与 compact retry。

### 阻塞“只要接入 tool 就能工作”的事项

- 缺少 public 或稳定组合根形式的工具接入装配面。
- `ToolSchema` 与 `ToolTruncateSpec` / Host metadata 缺少同源绑定契约。
- revised P5 已承接模型自主补读；若落地结果仍没有模型经 Engine tool loop 发起的 framework `fetch_more`
  tool call，则 P5 success path 不成立。

### 非阻塞 no-full-governance smoke 的事项

- 持久 EventLog、多进程 recovery、lease/fencing、Remote、Outbox、observer checkpoint、audit hard-gate。
- `client_request_id` 幂等与同 Session active Run 仲裁。
- terminal 后远程补读的跨进程审计。

## 扫描边界

本次只扫描并写报告，未修改生产代码、未修 plan、未写测试。已读取指定 Host migration/design/phase 文档、`dayu/host/README.md`、`dayu/engine/README.md`，并扫描 `dayu/host`、`dayu/engine`、`utils`、`tests/host` 当前实现。工作树中已有未提交/未跟踪的 P5 plan/review 文档，本报告未改动它们。
