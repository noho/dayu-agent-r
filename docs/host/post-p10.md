# Phase 10.5 目标与任务清单

## 文档职责

本文档只记录 Phase 10.5 的目标、任务、coverage 要求、challenge review 裁决和仍需讨论的 public contract 待决项。

稳定设计语义以 `docs/host/design.md` 为唯一真源；phase 编排、当前 gate、交付物和追踪状态以 `docs/host/implementation-control.md` 为总控真源。本文档不得替代设计真源，也不得作为 implementation-ready plan；只有待决 public contract 讨论完成并写回设计真源 / 总控文档后，才能基于本文档派发 P10.5 plan。

## 结论

不考虑 Recovery，当前代码已经落地了多轮会话主体所需的大部分 Host 内部能力：Session / Run / Attempt / EventLog、admission、queue follow-up、本地 dispatch、ToolRuntime accept barrier、等待恢复、memory projection、Context Governance 与 compact 后续注入。

但如果问题是“调用方程序员是不是只要写一个最薄 Service，工具可以 mock，场景可以写死，只调用 Host 就能完成普通本地多轮会话”，答案仍是：还不行。

更准确地说：

- 只用 `dayu.host` 包根导出的 public command facade，调用方只能把输入 durable accepted 到 Host，并读取状态 / run 级事件补读视图；它不会自动启动本地 Engine。
- 要让 Run 真正执行，调用方还必须手工装配 `HostDispatchScheduler`、打开同一个 durable store、共享 `ActiveWorkerRegistry`、注入 local execution / worker factory / ToolingOptions / compactor，并显式唤醒 scheduler。
- 这条装配路径现在主要存在于 `tests/host` 集成 harness 和 `dayu.host.dispatch` 内部模块里，不是一个给 Service 直接使用的稳定 Host runtime / composition root。

因此，Phase 10 后“Host 内部多轮主体闭环”基本成立；在暂不考虑 Service/CLI/WeChat 真实接入、业务工具发现和动态场景准备的前提下，Host 仍缺一轮 Phase 10.5 级别的 runtime 装配与 public contract 收口，才能冻结普通本地多轮会话的 Host public contract。

## 当前讨论暂不考虑

用户已明确本轮 Phase 10.5 讨论可以先排除以下事项：

- Service / CLI / WeChat / GUI 的真实入口改造。
- 业务工具发现、工具注册、provider / 配置绑定、财报工具扫描。
- 动态 ScenePrepare / scene manifest 体系；场景可以先写死。
- 真实业务工具端到端；工具可以用 mock。
- 从 `/Users/leo/workspace/dayu-agent` 迁移 web tools。P10.5 不迁移 web tools；核心 smoke 使用 no-tool 或 mock tool，不让联网、站点行为、Playwright / requests 兼容性影响 Host 多轮证明。

这些事项仍是设计上的后续能力，但不应作为 Phase 10.5 判断“普通本地多轮是否可用”的 blocker。Phase 10.5 的第一目标是冻结普通本地多轮会话的 Host public interface / contract，查漏补缺生产接线和组件，确保后续真实生产系统 Service 调用 Host public interface / contract 即可完成多轮会话闭环。P10.5 自身必须把真实生产系统 Service 将来接入所需的 Host 普通多轮生产接线做实：真实 CLI / web / GUI 在 P11-P15 实施完毕后会通过 Service 使用这里冻结的 Host public interface / contract 接入，不能等到真实入口接入时再补一条新接线。后续 P11-P15 只能扩展 Host 能力，不应改变普通多轮会话的生产接线。薄 Service 只是这个 contract 的最小 consumer 证明样例，不是 Host 需要特殊识别或特殊支持的一类调用方。

## Public API 变更护栏

P10.5 若发现需要新增、删除或改变 `dayu.host` public API，必须先和用户讨论并更新本文件或对应 phase plan，不能由 implementation 直接改。

P10.5 不要求“绝不新增接口”。如果 P0-P10 已落地接口不足以支撑普通 Service 调用 Host 完成普通本地多轮会话，可以提出新增或调整；但这些变化必须作为 public contract discussion 先被显式确认，不能以“测试需要”“薄 Service 需要”或“实现方便”为理由直接落入代码。

这里的 public API 包括但不限于：

- `dayu.host.__all__` 导出的类型、函数、枚举、错误码和 request / snapshot dataclass。
- `open_host(options)`、Host public handle、`submit_followup(...)`、`get_run(...)`、`get_session(...)`、`watch_session_events(...) -> AsyncIterator[HostEvent]`、`resolve_wait(...)`、`close_session(...)`、`purge_session(...)` 等调用方可见接口。
- 新增 Host local runtime / composition root 的命名、public handle shape、错误语义和暴露方法；关闭语义不得重开讨论，必须按 `docs/host/design.md` 已定的 `close_session` 与 Host graceful shutdown 语义接入。
- `watch_session_events(...)` terminal HostEvent 的 final answer view、payload 边界和错误语义。P10.5 不定义 `wait_final_answer(...)` public API。

P10.5 已决策下列现有或候选接口不进入普通 Service-facing public contract：

- `start_run(...)` 从 public namespace 移除，内部 admission primitive 固定命名为 `_start_run(...)`。
- `create_host_command_handle(...)` 降为 Host 内部 / 低层测试 composition primitive，不作为 Service 打开 Host 的入口。
- `HostLocalRuntime` 与 `HostLocalExecutionOptions` 改为 Host 内部 contract / implementation type，不作为普通 Service-facing public type。
- scheduler / wakeup / dispatch control API 不暴露给 Service；`open_host(options)` 内部完成 command -> scheduler / dispatch 接线。
- public payload reader、`read_payload(ref)`、`get_run_result(...)` 不进入 P10.5 public API；final answer 只能从 terminal HostEvent 展示。
- `stream_run_events(...)` / `HostEventView` 不进入普通 Service-facing public contract；`HostEventView` 改为 Host 内部 EventLog 薄读模型 / diagnostic DTO，不从 `dayu.host` public namespace 导出。P13 Audit / Tool Trace / Outbox 也不依赖 `HostEventView`，而是消费 committed EventLog / typed projection input view。

如果 Phase 10.5 只新增内部 helper、测试 harness 或文档，不改变调用方 contract，可以直接在 plan 中说明“不改变 public API”。但只要普通 Service 调用 Host 需要依赖一个新的稳定入口，就必须先完成 public API discussion。

## 测试替身约束

P10.5 success signal 删除 mock runner smoke。普通多轮主证明必须来自真实 runner public-path smoke；mock runner / runner test double 只能保留在低层单元测试或辅助集成测试中，用来定位 Host 编排问题，不能计入 P10.5 smoke coverage，也不能作为“调用方只调 Host public API 即可完成多轮闭环”的 correctness 主证据。

如 implementation 为低层测试保留 mock runner / runner test double，必须遵守以下约束：

- 只能读取本次 Host 构造出的真实 `AgentRunRequest.messages`、tool schemas、tool executor 输出和公开 policy 字段；不得读取测试侧 expected answer、fixture 全局变量、Run / Session 内部表、EventLog 内部 row 或 durable store。
- 不得按“第一轮 / 第二轮”、run id、client request id、调用次数、测试函数名或固定 expected answer 写死答案分支。
- 不得绕过 `open_host(options)`、RunInputBuilder、ToolRuntime、EngineEvent ingest、memory catch-up 或 terminal HostEvent 主路径。
- review Agent 发现 mock runner / runner test double 被计入 P10.5 smoke success signal，或被用来替代真实 runner smoke，即作为 blocking finding。

mock tool 仍可用于工具 wiring 验证。mock tool 只能根据本次工具调用参数机械返回结构化结果；不得按 expected answer、测试轮次、run id 或测试私有状态返回业务结论。要证明 tool fact 进入后续记忆时，marker 必须来自工具调用参数或工具结果，并通过 Host accept barrier / memory / RunInputBuilder 路径进入下一轮。

## Smoke Coverage Matrix

P10.5 的第一目标是冻结普通本地多轮会话的 Host public interface / contract，查漏补缺生产接线和组件，确保后续真实生产系统 Service 调用 Host public interface / contract 即可完成多轮会话闭环；smoke 是验证这个第一目标是否成立的第二目标，不能只证明“最后拿到了一个字符串”。它必须覆盖生成路径上的关键接线。后续 planning / implementation / review Agent 必须按本矩阵逐项说明覆盖情况；未覆盖项必须写明不覆盖理由、owner 和后续 destination。对本轮 success signal 中声明必须覆盖的接线，遗漏即 blocking finding。

建议拆成五类 smoke：

- S1 real-runner no-tool multi-turn smoke：证明普通本地多轮生成主链路。
- S2 mock-tool wiring smoke：证明工具 fact 进入 Host accept barrier / memory / 后续 RunInputBuilder；mock tool 可以用，mock runner 不计入 smoke success signal。
- S3 real-runner matrix smoke：至少覆盖 mimo、ds/deepseek、gemini、qwen 四类真实 runner 参数。
- S4 compact smoke：证明预算触发真实 compactor 后仍能继续多轮；可独立于最小多轮 smoke。
- S5 cancel smoke：证明 public opener / handle 下已有 cancel command、dispatch cancel、event visibility 与 read path 可用；不重开 close / cancel 设计，不覆盖 Phase 11 Recovery cancel。

### S1 real-runner no-tool multi-turn smoke 必须覆盖

- thin service / runtime 入口：调用方通过 P10.5 稳定 `open_host(options)` 入口打开和关闭本地 Host，不手工 import `dayu.host.dispatch`、durable store 或 scheduler internals。
- public command facade：调用方先通过 `ensure_session` / `create_session` / `get_session` 取得 Session；第一条 prompt 与后续普通 prompt 都通过 `submit_followup(queue)` 提交。
- admission / response shape：第一轮输入和后续普通 prompt 均使用同一个 `SubmitFollowupRequest` shape，不为首轮增加专用字段；`FollowupSnapshot` 以 `accepted_run_id`、`accepted_run_status` 和 command commit event sequence / durable read watermark 表达命令已持久接受后的状态；该 watermark 不是 `watch_session_events` 的 cursor。无 active / start-blocking Run 时返回 `accepted_run_status=ACCEPTED`，有 active / start-blocking Run 时通常返回 `QUEUED`；随后状态变化符合 P10 后 `ACCEPTED / QUEUED -> scheduler governance -> RUNNING` 语义。`queued_run_id` 不得作为普通 Service-facing 主语义。
- per-run tool selection：Host opener 注入全量业务 `ToolBundle`；`SubmitFollowupRequest.tool_names` 只选择本次 Run 的业务工具名，不携带 raw `ToolBundle` / callable。`None` 或省略表示全部业务工具，空集合表示禁用业务工具，非空集合表示指定子集。Host 必须校验工具名并冻结本次 effective tool set。
- scheduler wakeup：public command commit 后能自动唤醒 pre-start governance / dispatch；测试不得手工读取 dispatch row 后调用 scheduler 私有入口来补接线。
- pre-start Context Governance allow path：至少覆盖一次预算允许直接 dispatch 的路径，证明 governance gate 没有被绕过。
- RunInputBuilder 当前输入来源：第一轮当前用户 prompt 来自 durable `USER_INPUT_ACCEPTED`，不是测试直接传入 runner。
- LocalProxy / real runner 边界：真实 runner 只通过 Engine / LocalProxy 路径产出 EngineEvent，不直接写 Host state、EventLog、Run / Attempt row 或 memory。
- EngineEvent ingest terminal path：真实 runner 的 final answer 必须经 Host ingest 写入 canonical terminal facts，并让 Run 进入 `SUCCEEDED`。
- projection / memory catch-up：第一轮 user input / terminal facts 必须被 conversation memory projection 消费；第二轮 dispatch 前必须走 memory catch-up。
- second-turn continuity：第二轮 user prompt 不重复第一轮关键信息；第二轮 final answer 必须证明 runner 能基于 Host-provided continuity 作答。断言可以采用稳定 marker / 简单格式，但不得要求业务长答案完全一致。
- terminal event path：thin service 必须通过 `watch_session_events(...) -> AsyncIterator[HostEvent]` 观察到 typed `HostEvent` Run terminal event，并从 terminal event typed view 获得可展示 final answer；不得从 EventLog / payload 内部表直接取答案，不得用 `wait_final_answer(...)` 或其它等待 helper 替代 live watch 主路径。
- cancel compatibility：S1 至少要证明同一个 Host opener 下可以调用 public `cancel_run(...)` / `cancel_session_runs(...)`，但具体 cancel 行为断言可以放入 S5。

### S2 mock-tool wiring smoke 必须覆盖

S2 可以在 S1 之外独立实现。工具可以 mock，但 mock runner 不计入 P10.5 smoke success signal；如为了强制工具调用而使用 runner test double，该测试只能作为低层 wiring 回归，不能替代 S1 / S3 的真实 runner smoke。S2 至少覆盖：

- ToolRuntime schema injection：mock tool schema 通过 Host tooling options / runtime composition 进入当前 `AgentRunRequest`，而不是 runner / test double 自己内置工具知识。
- per-run tool selector：S2 必须至少覆盖一次 subset selection，并断言未选中的业务工具 schema 不进入当前 `AgentRunRequest`；如覆盖 no-tool selection，空集合必须表示禁用业务工具而不是全部工具。
- tool executor path：runner / Engine 只能通过 `AgentRunRequest.tool_executor` 调用工具；不得直接调用 mock tool 函数。
- Host accept barrier：mock tool result 必须先过 ToolRuntime / Host accept barrier，写入 canonical tool facts 后才返回给 runner / Engine。
- tool fact memory projection：accepted tool fact 必须被 conversation memory projection 消费。
- tool fact second-turn continuity：第二轮 user prompt 不含 tool marker；第二轮 captured `AgentRunRequest.messages` 必须通过 memory / verified fact message 包含 tool marker。
- mock tool 防作弊：mock tool 只能根据本次工具调用参数机械返回结构化结果，不按测试期望、轮次或 run id 返回结论。

### S3 real-runner matrix smoke 必须覆盖

真实 runner matrix smoke 是 P10.5 主证明的一部分，不再被 mock runner smoke 替代。

- runner 参数硬编码：P10.5 可参考 `dayu/config/llm_models.json` 写死 `RunnerSpec` / `RunnerCallOptions` / `AgentPolicy`，不实现 ConfigLoader。至少覆盖 mimo、ds/deepseek、gemini、qwen 四类配置；建议默认取 `mimo-v2.5-pro`、`deepseek-v4-flash`、`gemini-2.5-flash`、`qwen-plus` 或同文件中等价可用条目。
- same runtime path：真实 runner smoke 必须使用与 S1 相同的 `open_host(options)` / public command / public read path，不得走单独 shortcut。四类 provider 都必须走 `submit_followup(...)`、`watch_session_events(...) -> AsyncIterator[HostEvent]` 与 terminal HostEvent final answer 主路径。
- two-turn behavior：第二轮 user prompt 应尽量不重复第一轮关键信息，验证真实 runner 能基于 Host-provided continuity 作答。
- bounded assertion：真实 runner smoke 只做稳定、小范围断言，例如 Run terminal `SUCCEEDED`、答案非空、包含约定 marker 或满足简单格式；不得把真实 LLM 输出作为唯一 correctness 证明。
- environment gating：测试文件和 wiring 必须存在；对应 provider API key / 网络可用时必须执行。不可用时允许对该 provider 显式 skip，并在 validation 报告中说明 provider 名称、缺失的 secret ref / env 或网络原因。skip 不影响 mock-tool wiring、compact、cancel 等其它 correctness 验证。

### S4 compact smoke 必须作为查漏补缺覆盖

S4 可以独立于最小 no-tool 多轮 smoke 实现，但不能从 P10.5 success signal 中拿掉。P10.5 的目标是确保后续 Service 只调用 Host public interface / contract 即可完成普通多轮会话闭环；真实 runner smoke 已纳入第二目标，因此 context overflow 后的压缩上下文不能只用 mock / test-double compactor 证明，必须通过 public opener / handle 覆盖真实 compactor 接入路径：

- small budget trigger：通过写死 context window / reserved output tokens 或 policy 触发 proactive compact。
- real compactor：使用显式注入的真实 compactor adapter，不默认生产测试 compactor，也不把 mock / test-double compactor 作为 P10.5 compact success signal。
- compact canonical path：必须写入 `CONTEXT_COMPACTION_REQUESTED`、compact artifact、`CONTEXT_COMPACTED`，失败路径不得被测试吞掉。
- memory projection consumption：accepted compact output 必须被 memory projection 消费。
- subsequent run continuity：compact 后下一轮 RunInputBuilder 能看到 episode summary / pinned state / preserved refs 中的 marker。
- mock boundary：mock / test-double compactor 可以保留为低层单元测试或辅助回归；review 不能把它计入 P10.5 “Service 只调 Host public interface / contract 即可完成真实多轮闭环”的 compact smoke 证明。

### S5 cancel smoke 必须覆盖

S5 纳入 P10.5 smoke。它验证 P10.5 public opener / handle 没有破坏既有 cancel contract，并证明 cancel 事件能通过普通 Service-facing read path 可见。S5 不重新定义 cancel 语义；语义以 `docs/host/design.md` 为准。

- public command path：cancel 必须通过 `cancel_run(...)` / `cancel_session_runs(...)` public command 触发，不直接操作 durable state、dispatch row、worker handle 或 scheduler internals。
- accepted / queued cancel：覆盖 `ACCEPTED` / `QUEUED` Run 被取消后进入 `CANCELLED`，不创建 Attempt，不影响同 Session 已 active Run。
- pre-dispatch / dispatch cancel：覆盖 public cancel 命中 `STARTING` / dispatch 前后可治理窗口，并通过 Host 状态机收口；测试不得手工 release lane 或改 dispatch row。
- active cancel visibility：若 P10.5 smoke 覆盖运行中 runner，应覆盖 active cancel 至少产生 public cancel event / `RunSnapshot` 状态变化；若 active worker cancel watchdog / post-cancel timeout 仍归 Phase 11，必须在 coverage checklist 中标为 not covered but accepted，并写 owner。
- session-scope cancel：覆盖 `cancel_session_runs(...)` 取消指定 Session 下未终态 Run，不影响其它 Session。
- event / read path：cancel 后调用方通过 `watch_session_events(...)` 与 public `get_run(...)` 观察 cancel 结果；不得直接查内部表。
- close boundary：S5 必须断言 `close_session(...)`、Host opener close 与 cancel 是三个不同动作。`close_session(...)` 只关闭 Session 新输入入口；Host opener close 只关闭当前 handle 的本地 runtime；cancel 才表达用户停止 Run 的治理意图。如要停止已有工作，测试必须显式调用 cancel API。
- Recovery exclusion：`RECOVERING` cancel、startup recovery cancel、positive orphan proof 与 stuck `CANCELLING` watchdog 不进入 P10.5 success signal，继续归 Phase 11。

### Review 要求

Review Agent 必须在 review artifact 中包含一张 coverage checklist，逐项标记：

- covered：有测试或明确 smoke 覆盖，并给出测试名 / 断言点。
- not covered but accepted：本轮明确不覆盖，给出用户确认、owner 和后续 destination。
- blocking gap：本轮 success signal 要求覆盖但缺失，或测试通过硬编码 / 内部表查询 / 绕过 public runtime 凑结果。

任何 smoke 如果绕过 `open_host(options)`、直接操作 scheduler internals、直接查询 durable 内部表取得 final answer、或让 runner test double / mock tool 按 expected answer 凑结果，都不能计入本矩阵覆盖。

## 本次核对依据

- 设计真源：`docs/host/design.md`
- 总控真源：`docs/host/implementation-control.md`
- 代码事实：`dayu/host/*`、`tests/host/*`
- 额外验证：
  - `source .venv/bin/activate && pytest tests/host/test_public_run_api.py::test_start_run_direct_running_and_attach_active -q`：失败，当前代码在第一个 Run 进入 `ACCEPTED` 后，`attach_active` 会因“尚无 active Attempt”返回 conflict。
  - `source .venv/bin/activate && pytest tests/host/test_public_run_api.py::test_submit_followup_queue_active_and_no_active -q`：失败，当前代码返回 `RunStatus.ACCEPTED`，旧测试仍期待 `RUNNING`。

这两个失败不是本文档要修的源码问题，而是证明 P10 后 public facade 调用语义与旧测试 / 部分 README 表述已经不同：新输入先 accepted，再由 scheduler 的 pre-start governance 创建 Attempt。

## 已落地能力

- 当前代码里的 `create_host_command_handle(...)` 能打开 Host durable SQLite store，并提供 `ensure_session`、`create_session`、`start_run`、`submit_followup(queue)`、`cancel_run`、`cancel_session_runs`、`resolve_wait`、`get_run`、`get_session`、`stream_run_events` 等 facade；P10.5 已决策它降为 Host 内部 / 低层测试 composition primitive，不再作为 Service-facing public opener。
- admission 当前会把无 active Run 的新输入落为 `ACCEPTED`；有 active / accepted Run 时，`submit_followup(queue)` 会排队。
- `HostDispatchScheduler` 能把 accepted / queued Run 经过 Context Governance gate 启动为 Attempt，再走 runtime lane、本地 worker、RunInputBuilder、EngineEvent ingest 与 terminal closeout。
- ToolRuntime 已支持工具 schema / executor 同源、Host accept barrier、等待型工具进入 `WAITING` / `SUSPENDED`、`resolve_wait` 后创建 resume Attempt。
- Conversation Memory 已能消费 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED` 与 accepted `CONTEXT_COMPACTED`，并在后续 RunInputBuilder 中注入 recent raw turns、episode summary、pinned state 与 tool-verified facts。
- Phase 10 已补 proactive compact、reactive overflow compact、compact artifact、memory projection catch-up 与 multi-turn aggregate integration。

## Agent session 使用场景 gap 追踪列表（代码核对版）

本追踪列表按用户给定的 Agent session 使用场景核对当前代码。目标不是重复设计，而是明确：哪些生产接线 / 组件已经在设计中、哪些只有内部实现、哪些还缺设计或 public contract，供后续逐项讨论。

标记说明：

- 设计已有：`docs/host/design.md` 已有明确稳定语义，P10.5 主要负责按设计补 public 接线、测试和文档。
- 设计部分已有：设计已有方向，但 public shape、错误语义、返回类型、composition option 或 smoke 边界仍要讨论冻结。
- 缺设计：当前设计真源没有足够稳定语义，必须先补 design decision，不能直接交给 implementation。

### G1. 新建 Session

- 使用场景：调用方打开 Host 后创建一个新 Session，然后提交第一条 prompt。
- 代码事实：`create_host_command_handle(...)`、`create_session(...)`、`ensure_session(...)` 已存在；`submit_followup(queue)` 已能在无 active / start-blocking Run 时创建 `ACCEPTED` Run。包根仍导出 `start_run(...)`。
- gap：缺 async Host opener / public handle。现有 `create_host_command_handle(...)` 是同步 command handle，且明确拒绝 `local_execution`；调用方不能只打开一个 public Host handle 就获得 scheduler、LocalProxy、lane、memory catch-up、context governance、tool runtime 和关闭流程。
- gap：第一条 prompt 虽已决策应统一走 `submit_followup(queue)`，但包根和 README / tests 仍暴露 `start_run(...)` 作为 public 入口，容易让 Service 继续依赖旧路径。
- 设计状态：设计已有。`design.md` 已确认 async-only Host opener / handle、`start_run` 降为内部 admission primitive、Session acquisition 与 Run interaction 分离。
- P10.5 处理：补 Host public opener / handle；将 `start_run` 改为内部 `_start_run` 并移除 Service-facing export / docs / tests；用 S1 证明新建 Session 后第一条 prompt 只走 `submit_followup(queue)`。

### G2. Resume 当前 Session

- 使用场景：调用方根据 slot / session id 恢复当前 Session，补读离线 terminal，然后继续 live watch 和提交新 prompt。
- 代码事实：`ensure_session(...)`、`get_session(...)` 能读取 Session snapshot；`stream_run_events(...)` 只支持 run-scoped cursor 补读；`RunSnapshot.outbox_summary` 类型存在但当前 durable snapshot 基本返回 `None`；Outbox projection / work queue 未实现。
- gap：缺 Service-facing attach / reconnect recipe 的实现接线：没有 `watch_session_events(session_id)` live watch，没有 Outbox terminal 增量读取 public API，也没有把 Outbox drain 与 session live watch 去重 / 防漏窗口做成可验证 contract。
- 设计状态：已裁决。`design.md` 已确定“Outbox terminal 增量补读 + session live watch attach”属于同一个 attach / reconnect recipe；`watch_session_events` 是 live watch，不接收 cursor，离线 terminal/final answer 补读由 Outbox 和客户端保存的 terminal identity 承接。
- P10.5 处理：至少补 session-level live watch；Outbox 已裁决继续归 Phase 13。P10.5 只冻结 attach / reconnect recipe、terminal identity 与去重要求，不实现 Outbox concrete read / drain API，也不把离线 terminal 补读计入 smoke coverage；文档必须明确普通 Service 在 P10.5 只能证明在线 / 已 attach live watch final answer，不得误以为离线 terminal delivery 已可用。Phase 13 必须补 concrete Outbox read / drain API 与离线 terminal delivery smoke。

Outbox / offline terminal catch-up 边界已由设计真源裁决，不再作为 P10.5 design open question。P10.5 implementation requirement 是：`watch_session_events(session_id)` 只承担在线 / 已 attach live watch；Service 保存 `last_seen_terminal_event_sequence` / `seen_terminal_event_ids`，并以 `terminal_event_id` / `event_sequence` / `run_id` 作为未来 Outbox 与 live watch 的去重 identity。P10.5 不提供 `read_outbox(...)`、`drain_outbox(...)` 或等价 concrete API，不用 Outbox smoke 证明离线 final answer delivery。Phase 13 implementation requirement 是：实现 concrete Outbox read / drain API、OutboxSink terminal delivery queue projection、terminal item idempotency、离线 terminal 补读 smoke，并证明 Outbox drain 与随后 / 并发 live watch attach 不漏投、不重复展示同一 terminal answer。

### G3. 多客户端打开同一个 Session

- 使用场景：多个 UI / CLI / Web 客户端同时打开同一个 Session，各自观察事件、发送 queue / steer / cancel。
- 代码事实：多个 `HostCommandHandle` 可以打开同一个 durable store；EventLog 有全局 `event_sequence`；`stream_run_events(...)` 是 pull 补读且按 run 过滤。
- gap：缺 session-level live fanout / watch handle；当前没有多客户端 watch 的生命周期、backpressure、关闭、错误和去重语义实现。多个客户端可以各自轮询 durable truth，但这不是设计要求的 live watch。
- gap：command 与 observation 未在 public handle 上形成并行通道；Service 需要自己拼 polling、sleep、event_sequence bookkeeping 和 run filter。
- 设计状态：已裁决。session-level live watch 是设计真源；多客户端写入不引入客户端 ownership、lock 或 attach token。
- P10.5 处理：实现或冻结 `watch_session_events(...)` / 等价 async stream contract；S1 / S5 必须证明事件观察与 `submit_followup` / cancel 命令不要求顺序绑定。同一 Session 多客户端并发 `submit_followup(queue)` 时，只依赖 Host durable admission、`(session_id, client_request_id)` 幂等和 accepted `event_sequence` FIFO / scheduler governance 排队，不要求客户端先抢占会话所有权或持有 attach token。

多客户端写入策略已由设计真源裁决，不再作为 P10.5 design open question。P10.5 implementation requirement 是：多个客户端可以同时 `watch_session_events(session_id)`，也可以同时对同一 Session 发起 `submit_followup(queue)` / cancel / retry / replay 等 public command；Host 不维护 client ownership truth，不发放 session write lock，不要求 attach token。并发写入的顺序、幂等和冲突处理只能由 Host durable transaction、`client_request_id`、Run 状态 precondition、`event_sequence` 与 scheduler governance 决定。P10.5 smoke 至少覆盖两个 watcher 独立观察同一 Session 的 terminal event，以及两个不同 `client_request_id` 的 queued prompts 按 durable acceptance 顺序进入后续执行；相同 `(session_id, client_request_id)` 重放必须返回同一 accepted Run，不重复创建。

### G4. 观察正在运行的 Run

- 使用场景：调用方在 Run 运行中观察 tool event、thinking delta、content delta、terminal event，并按 UI 策略选择显示。
- 代码事实：`get_run(...)` 可读状态；现有 `stream_run_events(...)` 可按 run 补读 EventLog view；`HostEventView` 只含事件 id / type / payload ref / digest，不含 inline payload；Engine preview / diagnostic / usage / final answer ingest 已有内部映射。
- gap：缺 session 主事件流；现有 run-scoped EventLog 补读只能作为内部 detail / debug，不应成为聊天主入口，也不能作为普通 Service-facing public event contract。
- gap：缺 session-level live `watch_session_events(...)` 实现。调用方现在无法通过普通 Service 主事件入口观察该 Session 下各 Run 的 terminal event。
- gap：`watch_session_events(...) -> AsyncIterator[HostEvent]` 的 terminal event public `HostEvent` typed payload 形状仍需落地，确保 final answer 能从 terminal HostEvent 中展示出来；thinking delta、content delta、tool event 是否 displayable 由 UI 决定。
- 设计状态：设计已有 / 部分已有。session stream 与 terminal HostEvent 作为主路径已在设计真源确认；P10.5 已确认 live watch 产出 typed `HostEvent`，不是 raw `EngineEvent` 或薄 `HostEventView`；`HostEventView` 已裁决为内部契约。
- P10.5 处理：补 session event watch；确保 Run terminal HostEvent 包含可展示 final answer typed view；明确 `HostEventView` 是内部 debug / drill-down DTO；不定义 `wait_final_answer(...)` public API。

### G5. 普通顺序多轮

- 使用场景：用户一轮一轮发 prompt，上一轮答完后继续下一轮，第二轮能看到第一轮事实。
- 代码事实：`submit_followup(queue)` 已能接受首轮 / 后续 prompt；`HostDispatchScheduler` 能把 `ACCEPTED` / `QUEUED` Run 经过 pre-start governance、RunInputBuilder、LocalProxy、EngineEvent ingest 跑到 terminal；Conversation Memory / compact artifact provider 可被 RunInputBuilder 消费。
- gap：这些能力目前没有被一个 Service-facing Host opener 统一装配。`create_host_command_handle(...)` 默认 no-op wakeup，且拒绝 `local_execution`；测试要显式打开 scheduler、lane、worker factory、active registry、durable store。
- gap：public `watch_session_events(...) -> AsyncIterator[HostEvent]` 尚未提供 session-level terminal event 主路径；当前 Service 只能通过 `get_run(...)` / run-scoped stream 间接看到 terminal summary ref / digest 或 EventLog payload ref，不能按设计用 session live watch 直接展示 terminal answer。
- gap：`SubmitFollowupRequest` 新 public shape 已写入设计，但当前代码仍是旧 `input: HostInput` 为主，缺 `system_prompt`、`user_prompt`、`tool_names`、可选 `runner_spec` / `runner_options` / `agent_policy` 字段。
- 设计状态：设计已有 / 部分已有。普通 queue 语义、memory / compact owner、per-run tool selection 与 per-run typed execution override 已写入设计；terminal answer 主路径已冻结为 `watch_session_events(...)` 的 terminal HostEvent，代码仍需落地。
- P10.5 处理：S1 / S2 / S3 / S4 必须全部走同一 public opener / command / read path，证明 Service 不需要碰 dispatch internals。

### G6. 中途 steer / queue、interrupt / cancel Run

- 使用场景：active Run 运行中，用户可以继续 queue 下一条，也可以 steer 当前 Run；用户或上层可 interrupt / cancel 当前 Run。
- 代码事实：queue 已实现；`submit_followup(behavior=STEER)` 在 command facade 固定返回 `UNSUPPORTED_OPERATION`；`cancel_run(...)`、`cancel_session_runs(...)` 支持 accepted / queued、pre-dispatch、pre-accept dispatching、active worker、WAITING 子集；active worker cancel 依赖共享 `ActiveWorkerRegistry`；scheduler close 会 best-effort cancel active handles。
- gap：steer 本地语义未实现；`STEER_REQUESTED`、旧 Attempt 收口、新 Attempt 创建、dispatch 接线、terminal race、event 可见性均缺。
- gap：`design.md` 没有独立 interrupt public API；P10.5 不新增 `interrupt_*`。UI 若使用 interrupt 文案，必须映射到既有 `cancel_run(...)` 或 `submit_followup(steer)` 语义。
- gap：cancel 在 public opener 下尚未证明，因为 command handle 与 scheduler 若各自创建 registry，active cancel 传播会断；P10.5 opener 必须共享 registry。
- 设计状态：设计已有。`design.md` 已定义 `RUNNING` / `WAITING` steer、steer terminal race、不可 steer 状态、cancel 状态机、`cancel_session_runs(...)` 语义和 close / cancel / purge 边界。
- P10.5 处理：按 `design.md` 既有语义实现 steer 本地路径；S5 验证 cancel 在 public opener / live watch / public read path 下可用；不重开 cancel 语义，不新增 interrupt public API。Recovery 专属 `RECOVERING` cancel 仍归 Phase 11。

### G7. 失败 retry

- 使用场景：Run 失败后，调用方请求 retry，Host 基于源 Run 创建关联新 Run 并进入正常调度。
- 代码事实：`RetryRunRequest` 和 `retry_run(...)` public facade 存在，但当前 `retry_run(...)` 固定 `UNSUPPORTED_OPERATION`，不打开 transaction、不追加 EventLog、不写 idempotency。
- gap：缺本地 retry admission / source relation / policy 上限 / idempotency / dispatch / event stream / terminal HostEvent 可见性语义。
- gap：`LOST` / `RECOVERING` 的 recovery retry 属于 Phase 11，不应混入 P10.5；但普通 `FAILED` retry 必须有 owner。
- 设计状态：设计已有。`design.md` 已定义函数式 `retry(run)`：源 Run 终态不改，创建关联新 Run / 新 Attempt / 新 `execution_id`，不复用旧 worker；是否复用源 Run 已 accepted tool facts 由 retry policy 决定，默认复用已提交且仍有效的工具事实，不复用失败中的未接受输出。
- P10.5 处理：按 `design.md` 既有语义补普通本地 `FAILED` retry，并通过同一 public live event / terminal HostEvent contract smoke。`LOST` / `RECOVERING` retry 不进入 P10.5，继续归 Phase 11；这是 phase-scope 裁剪，不是重写设计真源。

### G8. 结构 replay

- 使用场景：Run 已成功，但 final answer 格式 / schema / 结构需要修复，调用方发起 replay。
- 代码事实：`ReplayRunRequest` 和 `replay_run(...)` public facade 存在，但当前固定 `UNSUPPORTED_OPERATION`。
- gap：缺 replay source relation、no-tool / tool fact reuse policy、repair instruction 注入、final answer 替代展示规则、EventLog truth 不改写规则、idempotency 和 dispatch 接线。
- 设计状态：设计已有。`design.md` 已定义函数式 `replay(run)`：只用于 final answer 格式 / schema / 结构 / output envelope / 引用格式修复；不重开源 `SUCCEEDED` Run；创建关联新 Run / 新 Attempt / 新 `execution_id`；复用源 Run accepted tool facts / tool messages / evidence anchors；no-tool，不重新执行工具，不新增工具事实；源 final answer 只作为 rejected candidate / repair context；read model 可指向最新 replay result，但 EventLog 保留完整 replay 链。
- P10.5 处理：按 `design.md` 既有语义补普通本地 replay；smoke 覆盖 replay final answer 通过 terminal HostEvent 可见，且不改写源 Run EventLog truth。

### G9. 长事务

- 使用场景：Run 调用外部工具或后台任务，进入 `WAITING`，稍后由 poll / callback / manual resolve 恢复。
- 代码事实：Tool awaiting accept path、wait record、`resolve_wait(...)`、最小 `WaitPoller.poll_once()` 已存在；`resolve_wait(...)` 可创建 resume Attempt 并调用 wakeup port；callback endpoint、后台 poller loop、callback 鉴权、外部 job physical cancel / revoke 未实现。
- gap：缺 callback HTTP endpoint、callback 鉴权 / 重放防护、poller 后台调度循环、外部 job physical cancel / revoke 等生产等待投递基础设施；普通 Service 若使用长事务工具，仍要自己安排 poll loop、callback handler 或人工入口取得结果后调用 Host。
- gap：`resolve_wait(...)` 的 wakeup 依赖 command handle admission service 的 wakeup port；没有 public opener 接线时 resume dispatch 可能只 durable accepted 而不执行。
- 设计状态：已裁决。P10.5 冻结 Host `WAITING` / wait record / `resolve_wait(...)` public contract 与 after-commit wakeup；生产后台 poller / callback supervisor 不纳入 P10.5 阻塞项。
- P10.5 处理：smoke 必须覆盖 Run 进入 `WAITING` 后，调用方只通过 Host public `resolve_wait(...)` 提交已取得的结果，并由同一 `open_host(options)` runtime 自动 wake scheduler / dispatch，最终在 `watch_session_events(...)` terminal HostEvent 中看到 final answer。callback endpoint、poller 后台循环、callback auth / replay、external job physical cancel / revoke 继续作为后续生产集成能力追踪，不阻塞 P10.5 public contract freeze。

### G10. 未被 LLM 响应的 prompt，崩溃退出重进恢复

- 使用场景：prompt 已 durable accepted 或 Run 已启动，但进程崩溃，重启后 Host 能恢复或给出确定 terminal。
- 代码事实：Host instance liveness 基础存在；dispatch scheduler 打开时会 register current instance；普通 recovery scan、positive orphan proof、startup scan、`RECOVERING` dispatch 属于 Phase 11；当前 `ACCEPTED` Run 等待 scheduler / pre-start governance，不是 orphan。
- gap：缺 Host opener startup recovery scan；缺 prompt accepted but not answered 的恢复语义；缺 positive orphan proof；缺 `RUNNING` / `CANCELLING` / `RECOVERING` startup 分类和恢复 dispatch。
- 设计状态：已裁决。此场景明确归 Phase 11 Host Lifecycle / Recovery / Multi-process Hardening。
- P10.5 处理：Recovery 不进 P10.5 success signal，P10.5 smoke 不证明 crash recovery；但 P10.5 public contract 必须冻结到 P11 可以在不改 Service 调用方式的前提下补 recovery。P11 必须覆盖“未被 LLM 响应的 prompt，崩溃退出重进恢复”：已 durable accepted 的 prompt 或已启动但未 terminal 的 Run，在 Host 重启后通过 recovery scan / positive orphan proof / recovery dispatch 继续或给出确定 terminal。

### G11. 关闭 / 归档 / 清理 Session

- 使用场景：关闭新输入、归档历史、必要时清理本地事实。
- 代码事实：`close_session(...)` 已实现并保持 facts；`purge_session(...)` public facade 存在但固定 `UNSUPPORTED_OPERATION`；设计明确 `clear_session` 不进入第一版普通公共接口，`purge_session` 归 destructive retention。
- gap：缺 purge tombstone、删除范围执行、payload / memory / projection / outbox / tool trace 清理；缺 archive / UI hide 这类上层语义与 Host close 的边界文档。
- gap：Host opener close 与 `close_session` / cancel 的差异需要在 public lifecycle 文档中保持清晰：opener close 不是 Session close，Session close 不是 cancel。
- 设计状态：已裁决。P10.5 只要求 `close_session(...)` public contract 可用；`purge_session(...)` 的 destructive cleanup、tombstone、删除矩阵与 retention hardening 继续归 Phase 15。
- P10.5 处理：S5 覆盖 `close_session(...)` public contract，并同时断言 `close_session(...) != cancel`、`Host opener close != cancel`、`Host opener close != close_session(...)`。README / public contract 写清 opener close、`close_session`、`cancel_run`、`purge_session` 的边界；P10.5 不把 purge success 作为 smoke 通过条件，只要求 purge 不被误用为 archive / close / cancel。

`close_session(...)` / Host opener close / cancel / `purge_session(...)` P10.5 边界已由设计真源裁决，不再作为 design open question。P10.5 implementation requirement 是：普通 Service 可通过 public `close_session(...)` 关闭 Session 新输入入口；关闭后 `get_session(...)` / `get_run(...)` / `watch_session_events(...)` 仍可读取或观察已有事实，已有非终态 Run 不被 `close_session(...)` 取消、不被删除、不被改写。Host opener close 终止当前 handle 的本地 runtime，但不写用户 cancel facts，也不把 Session 状态改成 `CLOSED`。`submit_followup(queue)` / `submit_followup(steer)` 在 closed Session 上必须返回明确 invalid-state / typed error。`purge_session(...)` 可保留 public envelope、closed-handle guard、unsupported / deferred 或 precondition error 边界，但 P10.5 不实现 destructive cleanup，也不要求 purge smoke 成功；完整 purge tombstone、delete ranges、payload / memory / projection / outbox / tool trace 清理、audit 查询与 retention hardening 继续归 Phase 15。

Recommended Service policy：当用户意图是“结束会话并停止当前工作”时，Service 应显式先调用 `cancel_session_runs(...)`，通过 `watch_session_events(...)` 或 `get_run(...)` 确认 cancel 结果可见，再调用 `close_session(...)` 关闭新输入入口。Host 不在 `close_session(...)` 内自动 cancel，因为自动合并会混淆归档意图与停止 Run 的治理意图，也会让 EventLog 无法清楚解释用户是否真的要求停止工作。

### G12. 真实 runner 多轮

- 使用场景：调用方能用真实 OpenAI-compatible runner 完成两轮。
- 代码事实：Engine 已有 `AsyncOpenAIRunner`；当前内部 `HostLocalExecutionOptions` 接收 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、`worker_factory`；P10.5 已决策该类型改为内部 contract，Service-facing 参数必须由 `open_host(options)` 的 options 承载；当前 Host 没有硬编码真实 runner 参数的 public opener / smoke。
- gap：缺真实 runner worker factory / LocalProxy production wiring 示例；缺参考 `dayu/config/llm_models.json` 的 P10.5 硬编码 runner 参数位置；缺 provider unavailable skip 规则落到测试。
- 设计状态：设计部分已有。P10.5 已决策不做 ConfigLoader，可硬编码真实 runner 参数；skip 语义已要求写入 plan / validation。
- P10.5 处理：S3 增加真实 runner smoke，走同一 Host public opener / command / read path；API key / 网络不可用时明确 skip。

真实 runner production wiring / smoke 已由设计真源裁决，不再作为 design open question。P10.5 implementation requirement 是：在 `open_host(options)` production path 中提供真实 runner worker factory / LocalProxy 接线，使用硬编码 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy` 作为默认 execution baseline 或 per-run typed override；参数可参考 `dayu/config/llm_models.json`，但 P10.5 不实现 ConfigLoader。真实 runner smoke 必须走 `open_host(options)`、`submit_followup(...)`、`watch_session_events(...) -> AsyncIterator[HostEvent]`、terminal HostEvent final answer 主路径，不得走单独 shortcut。至少覆盖 mimo、ds/deepseek、gemini、qwen 四类配置；建议默认取 `mimo-v2.5-pro`、`deepseek-v4-flash`、`gemini-2.5-flash`、`qwen-plus` 或同文件中等价可用条目。API key、provider、网络不可用时允许对对应 provider 显式 skip；测试文件仍必须存在，skip 条件和未执行原因必须进入 validation 报告。mock runner smoke 已删除，不能作为 P10.5 correctness 主证据。

### G13. 真实 compactor / overflow 多轮

- 使用场景：长会话超预算后，Host compact 历史并继续下一轮。
- 代码事实：`ContextCompactor` typed port、测试用 compactor 实现、quality check、compact artifact、pre-start proactive compact、reactive overflow compact、memory projection consumption 已有；内部 `HostLocalExecutionOptions.context_compactor` / `compact_artifact_root` 已存在；没有真实 LLM compactor adapter，也没有 `open_host(options)` contract smoke。
- gap：真实 LLM compactor adapter 未落地；更关键的是 public opener 尚未把 compactor、budget policy、artifact root、memory catch-up 作为普通 Service construction contract 证明可用。
- 设计状态：设计已有 / 部分已有。memory / compact public 接线已被裁决为 P10.5 查漏补缺；P10.5 必须补真实 compactor 接入路径，摘要质量可做低风险格式 / 非空 / continuity 断言，不把业务摘要优劣作为评测目标。
- P10.5 处理：S4 必须使用真实 compactor adapter 走 public opener 证明 overflow compact 闭环；mock / test-double compactor 只能作为单元测试或辅助回归，不能作为 P10.5 compact success signal。Service 仍不得直接碰内部 compact store / memory repair。

Compactor execution baseline 已由设计真源裁决，不再作为 design open question。P10.5 implementation requirement 是：LLM compactor 共享 Host runtime environment、durable store、memory / artifact roots、budget governance 与 canonical compact event / artifact 接线，但它的模型、温度、max tokens、provider 选择、compact scene policy 或等价执行参数必须通过 `open_host(options)` 的独立 typed construction-time 参数传入，不能复用每个 ordinary Run 的 `runner_spec` / `runner_options` / `agent_policy` override。`SubmitFollowupRequest.tool_names`、`system_prompt`、`runner_options` 等本轮请求字段不影响 compactor；compactor 不使用 business ToolRuntime、不创建用户可见 Run、不产出 final answer。P10.5 不实现 per-run compact override；未来若需要，必须另行讨论 typed public contract。

### G14. 业务工具每轮变化

- 使用场景：同一 Session 内不同 Run 使用不同工具集。
- 代码事实：`HostToolingOptions` 已支持 construction-time 全量业务 `ToolBundle`；ToolRuntime effective bundle builder 已有；`SubmitFollowupRequest` 当前没有 `tool_names` 字段。
- gap：缺 per-run `tool_names` selector 的 request 字段、admission validation、effective tool set freeze、Run / Attempt snapshot 或 diagnostic refs、ToolRuntime build 接线。
- 设计状态：设计已有。已决策 `None` / 省略 = 全部业务工具，空集合 = 禁用业务工具，非空集合 = 指定子集。
- P10.5 处理：补 public request / validation / ToolRuntime wiring；S2 覆盖 subset 和 empty selector。

Per-run `tool_names` 接线已由设计真源裁决，不再作为 design open question。P10.5 implementation requirement 是：`SubmitFollowupRequest.tool_names` 进入 admission validation；Host 必须校验每个 tool name 都存在于 construction-time 全量 business `ToolBundle`；`None` / 省略表示允许全量业务工具，空集合表示禁用业务工具，非空集合表示仅允许该子集。Host 必须把 resolved effective business tool names、schema digest、bundle source refs 或等价诊断 refs 冻结到 Run / Attempt 可解释 snapshot。ToolRuntime build 必须基于该 effective subset 暴露 schema 和 executor；不能把 raw `ToolBundle`、`ToolDefinition`、callable、自然语言工具描述、逗号字符串或无结构 metadata 放进 request。S2 smoke 必须覆盖 subset、empty=none、unknown tool name rejection，以及第二轮通过工具事实 / memory continuity 看到第一轮工具结果。

### G15. 事件展示与 terminal payload 边界

- 使用场景：UI 可选择显示 tool event、thinking delta、content delta，但 final answer 必须显示。
- 代码事实：EventLog / EngineEvent ingest 能记录 preview / diagnostic / usage / terminal；当前 `HostEventView` 不含 payload 内容；final answer 只通过 terminal summary ref / digest 间接暴露。
- gap：缺 displayable `HostEvent` 类型与 terminal HostEvent typed payload 的代码落地；缺 digest 校验失败、payload 不存在、已 purge、Run 未 terminal、Run failed / cancelled 的错误语义。
- 设计状态：设计已有，代码未落地。UI 决定 thinking delta 是否展示；P10.5 已确认 `watch_session_events(...)` 产出 Host-owned typed `HostEvent`，不是 raw `EngineEvent`，也不是内部补读的薄 `HostEventView`；terminal HostEvent 必须 inline 可展示 final answer typed view，第一版字段固定为 `content`、`filtered`、`degraded`、`finish_reason` 与 terminal status。
- P10.5 处理：落地 `watch_session_events(...)` 的 terminal HostEvent final answer typed view。`HostEventView` 改为 Host 内部 EventLog-backed diagnostic / detail DTO。P10.5 不定义 `wait_final_answer(run_id)` public API；P10.5 smoke 不能直接查 payload 内部表拿答案，也不能用等待 helper 代替 live watch。

### G16. Host opener 生命周期与错误语义

- 使用场景：Service 用 `async with open_host(options) as host:` 打开 / 关闭 Host；关闭后 API 调用有确定错误。
- 代码事实：`HostCommandHandle.close()` 只关闭 durable store，同步方法关闭后抛 `INVALID_STATE`；`HostDispatchScheduler.close()` 会 cancel drain task、best-effort cancel worker handle、关闭 lane；二者没有一个 public async context manager 串起来。
- gap：public opener 名称已冻结为 `open_host(options)`；options 边界已裁决为“底层生产运行需要哪些 construction-time 外部依赖，就通过 typed function 参数显式传入哪些”，不引入 ConfigLoader、全局配置系统或 service locator；close 后 API 调用已裁决为 fail-fast 抛 typed `HostClosedError` 或等价 Host lifecycle exception；Host opener close 已裁决为终止当前 handle 的本地运行环境但不得伪装成用户 cancel，未收口 active Attempt 后续归 Host lifecycle / Recovery 的 lost / recoverable-lost 路径。
- 设计状态：已裁决。async-only、`open_host(options)` 名称、close_session 边界、Host opener close public lifecycle 与 shutdown order 均已冻结；shutdown order 是 implementation requirement，不再阻塞 design discussion。
- P10.5 处理：按 production runtime 真实依赖定义 typed `open_host` options，并冻结 lifecycle；不得用测试 helper 冒充 production opener。

Host opener close shutdown order 已由设计真源裁决，不再作为 P10.5 design open question。P10.5 implementation requirement 是：`host.close()` / `open_host().__aexit__` 先关闭 public gate 并拒绝新 API；停止 scheduler / promotion / background supervisor，避免启动新 Attempt；关闭 session live watch fanout，让 watcher 结束或收到 Host lifecycle termination；取消或关闭当前 handle 持有的 active worker task、lane wait、worker stream consumer task；flush / close projection catch-up 与本地 runtime resources；最后关闭 durable store。全程不得写 `RUN_CANCELLED` / `RUN_FAILED` 或其它 terminal fact 来伪装用户意图；已经在 close 过程中确认的真实 terminal event 仍按正常 ingest / terminal closeout 处理。

## 缺失清单

### 1. 缺稳定的 `open_host(options)` composition root

当前 `create_host_command_handle(...)` 明确拒绝非空 `HostCommandHandleOptions.local_execution`。P10.5 已决策该函数降为 Host 内部 / 低层测试 composition primitive。也就是说，调用方不能也不应只创建一个 command handle，然后期待它自己启动 scheduler、lane、LocalProxy 或 Engine。

现在要跑起来，测试 harness 必须另外导入 `dayu.host.dispatch.HostDispatchScheduler`，再打开 durable store / transaction runner，传入内部 `HostLocalExecutionOptions`、lane DB、worker factory、active registry 等。这只能作为内部接线事实，不能成为 Service 程序员使用的 public Host 入口。

P10.5 的 implementation requirement 是：新增 Service-facing `open_host(options)` async opener / handle；普通 Service 文档、README、包根 public export 和 public smoke 只使用 `open_host(options)`。`create_host_command_handle(...)` 若当前仍从普通 public namespace 导出，必须移除或降级到明确 internal / low-level test helper namespace；内部测试可以继续使用它验证 command transaction，但不得把它作为生产 Host runtime 或 thin Service 的入口。

`open_host(options)` 返回的 public Host handle facade 方法集合已由设计真源决定，不再作为 design open question。P10.5 implementation 需要把现有同步 / 内部 command 与 read facade 包成 async public handle methods：`ensure_session`、`create_session`、`get_session`、`close_session`、`purge_session`、`get_run`、`submit_followup`、`cancel_run`、`cancel_session_runs`、`retry_run`、`replay_run`、`resolve_wait` 与 `watch_session_events(session_id) -> AsyncIterator[HostEvent]`。这些方法可以复用内部 command / durable / scheduler 接线，但 Service 不得直接 import `dayu.host.dispatch`、durable store、scheduler、wakeup port 或 `create_host_command_handle(...)`。

通俗说：现在 Host 有“方向盘”和“发动机”，但还没有一把给 Service 用的“车钥匙”。Service 不能只拿 public handle 就开跑。

### 2. command facade 和 scheduler wakeup 没有完整 public 接线

`_start_run(...)` / `submit_followup(queue)` 提交后，Run 会先进入 `ACCEPTED` 或 `QUEUED`。真正启动 Attempt 的入口是 scheduler 的 `wake_queue_promotion(...)`。当前内部 command handle 装配的是默认 no-op wakeup port，不会自动把 accepted Run 交给 scheduler。P10.5 不暴露 scheduler / wakeup / dispatch control API；该接线必须由 `open_host(options)` 内部完成。

`resolve_wait(...)` 恢复等待时也会创建新的 resume Attempt / dispatch record，但 command handle 默认仍没有真实 scheduler wakeup。测试里可以读取内部 dispatch row 或手工调用 scheduler；普通 Service 只拿 public snapshot 时，没有稳定方式把这个 resume dispatch 接起来。

该项已由设计真源裁决为 implementation requirement，不再作为 design open question。P10.5 必须在 production `open_host(options)` composition root 内把 command facade、after-commit wakeup port、background supervisor、scheduler、dispatch queue 与 shared active worker registry 接成同一条生产路径；`submit_followup(queue)`、`resolve_wait(...)`、terminal closeout、cancel 释放 active slot、retry / replay 创建新 Run 等 commit 后需要推进执行的路径，都必须自动 wake scheduler / promotion / dispatch。P10.5 smoke 不得通过读取内部 dispatch row、手工调用 scheduler 私有入口或 sleep/poll durable table 来凑执行推进。

通俗说：用户输入已经入账，但“提交后自动开工”的铃还没接到工人那里。

### 3. public Run 语义与 P10 后状态机没有统一文档和测试

P10 后，新输入的第一阶段是 `ACCEPTED`，不是直接 `RUNNING`。代码中 admission 已按这个语义实现，`attach_active` 遇到 `ACCEPTED` 会 conflict，因为此时还没有 active Attempt。

但 `tests/host/test_public_run_api.py` 和 `dayu/host/README.md` 的部分表述仍按旧语义写成“无 active 时 direct RUNNING”。这会误导 Service 调用方：他们会以为 `start_run` 返回后已经有 `current_attempt_id`，实际 P10 代码里可能还没有。

通俗说：代码已经变成“先排号，再叫号开工”，但部分说明还写着“提交即开工”。

### 4. 缺 Service 层真实接入

仓库里当前没有 `dayu/service` 包，也没有看到 CLI / WeChat / GUI 入口改为通过 Host public API 驱动多轮会话。根 README 仍描述既有 `prompt` / `interactive` 多轮能力，但本次 Host P0-P10 代码没有把这些入口接到 Host runtime 上。

这意味着“我写一个 Service”还不是补薄薄一层 adapter，而是要承担场景装配、Host runtime 生命周期、scheduler 生命周期、事件读取、终态返回和错误映射。

通俗说：Host 地基和机房设备有了，但前台服务窗口还没建。

Phase 10.5 裁剪：这一项先不作为 P10.5 blocker。P10.5 只需要保证 Host 的普通本地多轮 public contract 足够稳定，未来普通 Service 可以按该 contract 接入；不要求把现有 CLI / WeChat / GUI 真实改接进来。薄 Service 只是最小验证样例，不代表 Host 有一套专供薄 Service 使用的接口。

### 5. 缺 HostEventStream terminal event 的 final answer 展示接线

`stream_run_events(...)` 当前只返回薄 `HostEventView`：`event_sequence`、`event_id`、`event_class`、`event_type`、`session_id`、`run_id`、`payload_ref`、`payload_digest`，不返回 inline payload。P10.5 已裁决 `HostEventView` 改为内部契约，因此该路径不能作为普通 Service-facing public event contract。`RunSnapshot.terminal_result_summary` 也只给 `summary_ref` / `summary_digest`。

final answer 内容确实会被 `EngineEventIngestor` 写进 terminal summary payload descriptor；但普通 Service 的主路径不应是直接读取内部 payload 表，也不应把 run-scoped internal stream 的薄 `HostEventView` 当聊天主入口。设计真源要求一个 Run 的 terminal HostEvent 出现在 session-level async event iterator 中，在线 / 已 attach 客户端通过 `watch_session_events(session_id)` live watch 观察并展示 final answer。

`watch_session_events(session_id) -> AsyncIterator[HostEvent]` 的 public 形态已由设计真源裁决，不再作为 design open question。P10.5 implementation requirement 是：落地 session-level live iterator、fanout / subscription、多个 watcher 同时打开同一 Session 的独立消费、consumer cancel / early `aclose()` 只关闭本 watch、不写 EventLog、不 cancel Run、Host close 时已打开 iterator 结束或抛 Host lifecycle termination、新打开 watch 时按 Host closed / session not found / gone 抛 typed exception、Session `CLOSED` 仍允许 watch。该 iterator 不接收 cursor、不做离线补读、不在 terminal event 后自动结束。

Service-facing `HostEvent` typed contract 已由设计真源裁决，不再作为 design open question。P10.5 implementation requirement 是：新增或调整 public `HostEvent` 代码类型，使 session live iterator 产出 Host-owned typed event，而不是 raw `EngineEvent` 或内部 `HostEventView`。第一版 `HostEvent` 至少携带 `event_id`、`event_sequence`、`session_id`、`run_id?`、typed kind、dedupe identity 与 display payload；terminal `SUCCEEDED` event 必须 inline final answer view，字段为 `content`、`filtered`、`degraded`、`finish_reason` 与 terminal status。tool event、thinking delta、content delta 作为可选择展示的 typed event 暴露，是否显示由 UI 决定。P10.5 smoke 必须从 terminal `HostEvent` 读取 final answer，不能从 payload table、terminal summary ref、内部 `HostEventView` 或专用 wait/read helper 取答案。

因此，P10.5 的缺口是：`watch_session_events(...)` 还没有落地，typed `HostEvent` 代码 contract 还没有落地，terminal HostEvent 的 public payload view 还没有实现。当前代码可以用 `get_run(...)` 轮询，也可以用内部 run-scoped 补读看到薄 `HostEventView`，但这两者都不能替代普通聊天主事件入口。P10.5 不新增 `wait_final_answer(...)` public API。

通俗说：最终回答应该随着会话事件流到达前台；现在后台已经有“报告生成”事实和 payload ref，但前台这条会话事件通道还没把 terminal answer 作为稳定 public event 送出来。

### 6. 真实业务工具发现和场景准备未落地

设计要求 Host 不扫描财报工具、不内置财报业务语义；业务 `ToolBundle`、scene system prompt、场景约束应由 Service / composition root 准备后传入 Host。

当前 Host 有 `HostToolingOptions` 接收外部已装配好的 `ToolBundle`，但 `ToolsDiscovery` / `ScenePrepare` 仍是 Phase 12 后续项。没有这层，Service 程序员必须自己知道如何收集财报工具、绑定 provider、构造 scene prompt 和 policy。

通俗说：Host 可以使用一箱已经整理好的工具，但还没有人负责把财报工具从仓库里挑出来、贴标签、交给 Host。

Phase 10.5 裁剪：这一项先不作为 P10.5 blocker。P10.5 可以用 mock `ToolBundle`，scene inputs / system prompt 可以由薄 Service 写死后显式传入或暂用当前 Host input 能力覆盖。P10.5 不迁移旧仓库 web tools；web tools 后续若要接入，应作为独立工具迁移 / adapter work unit，不作为 Host 多轮可用性的证明前提。

### 7. 执行目标和 policy provider 仍是临时接线

`start_run` 请求里有 `execution_target`，但 `submit_followup(queue)` 当前使用 Host facade 内部默认 execution target。完整的 policy provider / execution target resolution 还没落地。

普通多轮会话里，follow-up 已裁决为沿用当前 `open_host(options)` 的 default execution baseline，除非 `SubmitFollowupRequest` 显式携带可选 typed override 对象。P10.5 不给 `SubmitFollowupRequest` 增加 per-run target / profile id 字段；每 Run 可变项第一版包括 `system_prompt`、`user_prompt`、`tool_names`、可选 `runner_spec` / `runner_options` / `agent_policy` 与必要 request metadata。换模型或改 `max_iterations` 等运行参数时，调用方直接传 typed 对象，不通过 profile registry、无结构 metadata / extra payload / dict override / `policy_overrides`。

`SubmitFollowupRequest` 新 public shape 已由设计真源裁决，不再作为 design open question。P10.5 implementation requirement 是：把代码中的 request shape 迁移到 `client_request_id`、`system_prompt?`、`user_prompt`、`behavior`、`target_run_id?`、`tool_names?`、`runner_spec?`、`runner_options?`、`agent_policy?`。`session_id` 可以作为 `host.submit_followup(session_id, request)` 的路径参数与 request 内字段保持一致校验，也可以在最终 Python API 中只保留路径参数，但普通 queue 调用方不得传 `run_id`；新 Run id 必须由 Host admission 根据 `(session_id, client_request_id)` 幂等生成，并通过 `FollowupSnapshot.accepted_run_id` 返回。steer 才需要 `target_run_id`；retry / replay 传 source run id，新 Run id 仍由 Host 创建。

Per-run execution override 接线已由设计真源裁决，不再作为 design open question。P10.5 implementation requirement 是：当 `SubmitFollowupRequest` 携带 `runner_spec`、`runner_options` 或 `agent_policy` 时，Host admission 必须校验这些 typed 对象，解析出该 Run 的 effective execution config，并将 effective `RunnerSpec` / `RunnerCallOptions` / `AgentPolicy` 冻结到 Run / Attempt 可解释 snapshot、policy/source refs 或等价 durable truth 中；字段省略时使用 `open_host(options)` default execution baseline。dispatch / RunInputBuilder / LocalProxy 构造 `AgentRunRequest` 时必须读取该 Run 的 effective config，而不是固定使用 opener 默认值。retry / replay 默认复用或按其语义解析源 Run 的 effective config，任何变更必须记录 source relation 与新 effective config。P10.5 smoke 至少要证明同一 Session 两个 Run 可以使用不同 model / `max_iterations` 等 typed execution config。

通俗说：一个打开的 Host handle 提供默认执行配置和运行环境；追问默认沿用它。某一轮真要换模型或改 `max_iterations`，就把本轮完整的 typed `RunnerSpec` / `RunnerCallOptions` / `AgentPolicy` 直接放进 request，而不是传一个 profile 名字让 Host 再去别处查。

### 8. memory / compact public 接线仍需纳入 P10.5 查漏补缺

P10 已经有 `ContextCompactor` typed port、测试用 compactor、quality check、compact artifact 和 memory projection 接入。但 production helper 不会默认注入测试 compactor；如果 Service 没有显式提供真实 compactor，预算压力触发 compact 时会 fail closed。

因此，多轮短对话和预算未超限路径已有内部能力基础；长对话需要压缩时，当前仍依赖调用方理解并显式补齐 compactor / artifact / budget policy 等装配。这个缺口不能留给后续普通 Service 自己摸内部模块解决。

通俗说：记忆和压缩流程的管道已经修到 Host 内部，但 P10.5 还必须把它接到普通调用方能打开的 Host public handle 上；调用方不能为了多轮闭环去手工碰 scheduler、memory catch-up、compact artifact store 或 dispatch internals。

Phase 10.5 裁决：memory catch-up 与 context overflow compact 属于“确保后续真实生产系统 Service 调用 Host public interface / contract 即可完成多轮会话闭环”的查漏补缺项。P10.5 必须冻结 compactor / compactor execution baseline / budget policy / compact artifact root / memory catch-up 在 async Host opener 中的 public construction contract，并用 public-path smoke 证明：

- 普通多轮第二轮输入能通过 Host memory / continuity 看见第一轮 committed fact。
- 预算触发 compact 时，Host 通过 opener 注入的 `ContextCompactor`、compactor execution baseline、compact artifact store 和 memory catch-up 完成 compact -> memory projection -> subsequent RunInputBuilder 注入。
- Compactor execution baseline 与 ordinary Run execution override 分离；某一轮通过 `SubmitFollowupRequest` 切换模型或温度时，不会隐式改变 compactor 的模型、温度或 compact policy。
- P10.5 compact smoke 必须接入真实 compactor adapter；mock / test-double compactor 只能用于更低层测试或辅助回归，不能作为 compact success signal。production opener 不得隐式默认注入测试 compactor。
- 真实 LLM compactor adapter 的业务摘要质量不作为 P10.5 评测目标；但如果 P10.5 声称“context overflow 多轮可闭环”，必须证明调用方只通过 Host public opener 传入真实 compactor 后即可跑通 overflow compact 闭环。

### 9. wait / callback / poller 的生产后台循环缺失

Host 已有 `resolve_wait(...)`、wait record、等待型工具 accept path 和最小 poller `poll_once()`。但 callback HTTP endpoint、callback 鉴权 / 重放防护、poller 后台调度循环、外部 job physical cancel / revoke 都未落地。

如果多轮会话中的财报工具会进入外部等待，Service / tool adapter 需要自己安排 poll / callback / manual resolve 取得结果，然后调用 Host public `resolve_wait(...)`，否则 Run 会停在 `WAITING`。

通俗说：Host 能登记“这件事等外部结果”，也能接收已经拿到的结果并继续跑；但 P10.5 不要求 Host 自己内置生产里的快递员定时去取结果。

Phase 10.5 裁决：callback / poller 后台循环不阻塞普通本地多轮 public contract freeze。P10.5 必须保留并验证 `resolve_wait(...)` public 能力：Run 进入 `WAITING` 后，调用方只通过 Host public `resolve_wait(...)` 提交 poll / callback / manual 已取得的结果，Host 内部通过 after-commit wakeup 接线创建 resume Attempt、推进 dispatch，并在 `watch_session_events(...)` 中产出后续 terminal HostEvent。P10.5 不实现 callback HTTP endpoint、callback auth / replay、poller 后台 loop、backoff / in-flight fencing 或 external job physical cancel / revoke；这些继续作为后续生产集成 / scale owner。

### 10. session-level live watch 接线和离线投递仍不完整

设计真源已经确定：聊天主事件流是 session-level live watch。在线 / 已 attach 客户端应通过 `watch_session_events(session_id)` 或等价 Host event stream 观察目标 Session；`stream_run_events(...)` / `HostEventView` 只保留为 Host 内部 run-scoped detail / debug / drill-down 补读契约。`watch_session_events` 不接收 cursor，不承担离线补读；拿到 / attach Session 前发生的 terminal/final answer 通知由 Outbox 路径承接。

当前缺口不是“pull cursor 还是 live watch”的设计选择，而是 P10 代码是否已经把 session-level live watch、terminal event final answer view 和 Outbox terminal delivery 边界接完整。Phase 13 的 Outbox / Audit / Tool Trace 仍未实现，因此离线渠道还没有 Host-owned terminal delivery queue。

通俗说：在线客户端应该站在会话门口实时看消息；它还没打开会话前错过的最终答复，不靠倒放所有中间过程补，而是以后由 Outbox 这条终态投递路径补。

### 11. RemoteProxy 未落地

设计目标包含本地 Engine 与远程 Engine 并列执行；当前已落地的是 LocalProxy 语义基线，RemoteProxy / RemoteStub 是 Phase 14 后续项。

不考虑远程时，这不阻塞本地多轮会话；如果 Service 的部署目标要求远程 worker，这仍是明确缺口。

通俗说：本机工位可以干活，异地工位的电话线还没铺。

### 12. 普通追问可排队，但 steer / retry / replay 仍是 stable unsupported

当前 `submit_followup(behavior=queue)` 是可用的普通追问路径；这足够覆盖“上一问答完后继续问”的基础多轮。

但 `submit_followup(behavior=steer)`、`retry_run(...)`、`replay_run(...)` 仍固定返回 `UNSUPPORTED_OPERATION`。这些不是最小顺序多轮的硬 blocker，但会影响用户在 active Run 中途追加指令、失败后重试和结构修复。`purge_session(...)` 的 destructive cleanup 已裁决继续归 Phase 15，不作为 P10.5 必须解锁的普通多轮能力。

通俗说：正常一问一答接着问可以排队；“中途改口”“失败再来一次”“整理修复”还没开放；“彻底清理”是后续 retention / cleanup 问题。

## Phase 10.5 建议目标

Phase 10.5 不应重做 Host 内部状态机，也不应抢 Phase 11 Recovery / Phase 12 ToolsDiscovery / ScenePrepare / Phase 14 Remote 的范围。

已确认的 public API 方向：

- 调用方不应感知 `HostLocalRuntime`、scheduler、runner、tooling、memory catch-up 或 wakeup 等装配细节。Public contract 应表现为一个简单的 Host handle / client：打开 Host、取得 / 新建 / 读取 Session、提交 prompt、读取 / 订阅 Session 事件、在 `watch_session_events(...) -> AsyncIterator[HostEvent]` 中观察 terminal final answer、关闭 Host。
- `HostLocalRuntime` 可以作为内部 implementation 名称或 composition root，但不应成为业务上层必须理解的 public domain concept。`HostLocalRuntime` 与 `HostLocalExecutionOptions` 均改为内部 contract / implementation type。Service-facing 打开入口名称固定为 `open_host(options)`。
- P10.5 冻结 async-only public Host handle。第一版不提供 Host 层同步 wrapper，不冻结同步 close / cancel / timeout / stream iteration 语义；CLI 或同步上层如需使用 Host，由 Service / CLI adapter 用 `asyncio.run(...)` 或等价机制包装 async contract。
- Host opener close 是 Host handle lifecycle 语义，不是 Session / Run 治理事实。`host.close()` 与 `open_host(...).__aexit__` 必须幂等；重复 close 不报错。close 完成后，调用该 handle 上的 `ensure_session`、`create_session`、`get_session`、`close_session`、`purge_session`、`get_run`、`watch_session_events`、`submit_followup`、`cancel_run`、`cancel_session_runs`、`resolve_wait`、`retry_run`、`replay_run` 等 Host API，必须 fail-fast 抛出 typed `HostClosedError` 或等价 Host lifecycle exception。这个错误不写 EventLog，不返回 command-level `invalid_state`，也不与 `Session CLOSED`、not found、purged、retry precondition failed 等业务状态混淆。已经进入 admission / command transaction 的调用按正常事务语义完成；close gate 之后新进入的调用统一抛 closed-handle exception。
- Host opener close 会终止当前 handle 持有的本地运行环境，但不得伪装成用户取消。close 流程必须停止 scheduler / promotion / background supervisor，不再启动新的 Attempt；必须关闭或取消当前 handle 持有的 active worker task、lane wait、stream fanout task 与本地 runtime resource，避免进程内任务泄漏。若 close 过程中 active worker 已经产出可确认 terminal event，Host 按正常 ingest / terminal closeout 追加事实。若 active worker 没有可确认 terminal，Host close 不得写 `CANCEL_REQUESTED`、`RUN_CANCELLED`、`RUN_FAILED` 或其它伪装用户意图 / 确认失败的 canonical fact；未收口 active Attempt 后续只能通过 Host lifecycle / Recovery 的 positive orphan proof 路径进入 `ATTEMPT_LOST`，再按 policy 进入 `RUN_RECOVERING` 或 `RUN_LOST`。P10.5 不实现完整 Recovery，但必须保证 opener close 后 Service 不会误以为该 active Run 仍在当前 Host handle 中继续执行。调用方若要表达用户明确停止，应在 close 前显式调用 `cancel_run(...)` 或 `cancel_session_runs(...)`。
- `open_host(options)` 的 options 只承载打开 Host、驱动 Host -> Engine 本地运行所需的 construction-time 参数。Host public API 保持朴素接口形式：内部运行真正需要外部提供的 durable store / payload / artifact roots、runner / worker factory、全量 business `ToolBundle`、ToolRuntime policy、ContextCompactor、compactor execution baseline、context budget policy、memory catch-up、stream fanout / background supervisor 所需端口和运行目录等依赖，由调用方通过 typed function 参数显式传入；Host 不在 P10.5 引入 ConfigLoader、全局配置系统或 service locator。scheduler、wakeup、active worker registry、dispatch control 等 Host 内部接线由 `open_host` composition root 自行创建或连接，不作为 Service-facing 参数暴露。每次 ordinary Run 会变化的参数不得塞进 options，必须进入对应 public request，例如 `SubmitFollowupRequest`、`RetryRunRequest`、`ReplayRunRequest` 或后续明确讨论冻结的 per-run request 字段；compactor 的模型、温度、max tokens、provider 选择或 compact scene policy 属于 opener construction-time baseline，不被 ordinary Run request override 隐式改变。
- 一个 `open_host(options)` 表达一个 Host runtime environment 与默认 execution baseline。durable store、scheduler / worker wiring、memory / artifact roots、compactor、全量 business `ToolBundle`、Host policy 基线与默认 `RunnerSpec` / `RunnerCallOptions` / `AgentPolicy` 都属于 construction-time baseline。真实生产系统在同一个 Session 的不同 Run 中切换模型是正常需求；P10.5 不通过 `profile_id` / registry lookup 表达这件事，而是允许 `SubmitFollowupRequest` 直接携带可选 typed override 对象：`runner_spec?: RunnerSpec`、`runner_options?: RunnerCallOptions`、`agent_policy?: AgentPolicy`。字段省略时使用 `open_host(options)` 的默认 baseline；字段出现时使用该 Run 显式传入的 typed value。Host 不接收 raw provider client、API key 明文、callable、无结构 dict override、extra payload 或 `policy_overrides`。`RunnerSpec.api_key_ref` 仍只是 secret 引用名，不是 secret 本体。Host admission / dispatch 必须校验并冻结每个 Run 的 effective runner spec / runner options / agent policy 到 Run / Attempt 可解释 snapshot 或 source refs，保证 retry / replay / recovery 能解释当时使用的执行配置。普通每 Run 其它可变项第一版包括显式 `system_prompt`、`user_prompt`、`tool_names` 以及必要的 `client_request_id`、actor / source refs 等 request metadata。后续若新增更细粒度 per-run override，也必须作为 typed request field 讨论并冻结。
- Scheduler wakeup ownership 已由 `docs/host/design.md` 冻结，不是 P10.5 待讨论 public contract。`submit_followup(queue)`、`retry_run(...)`、`replay_run(...)`、`resolve_wait(...)`、terminal closeout 与 cancel 释放 active slot 等命令提交后，需要唤醒 scheduler / promotion / dispatch 的地方，都必须通过 Host 内部 after-commit wakeup port 或等价 background supervisor 接线完成。Service 不得调用 scheduler wakeup、读取 dispatch row 或控制 dispatch。P10.5 的责任是把 production `open_host(options)` 中的 command facade、after-commit wakeup port、background supervisor、scheduler 与 shared active worker registry 接到同一 composition root 上，并用 public-path smoke 证明命令 commit 后无需 Service 额外唤醒即可推进执行。
- Outbox 已裁决继续归 Phase 13。P10.5 只冻结 attach / reconnect recipe、terminal identity 与去重要求：Service 可保存 `last_seen_terminal_event_sequence` / `seen_terminal_event_ids`，未来通过 Outbox read / drain API 补离线 terminal 增量，再接入 `watch_session_events(session_id)` live watch。P10.5 不实现 Outbox concrete read / drain API，也不把离线 terminal 补读计入 smoke coverage；P10.5 smoke 只能证明在线 / 已 attach 的 live watch final answer 主路径。Phase 13 必须补 concrete Outbox read / drain API 与离线 terminal delivery smoke。
- Session acquisition 和 Run interaction 分离：`ensure_session(...)`、`create_session(...)`、`get_session(...)` 只负责拿到 `SessionSnapshot`；拿到 `session.session_id` 后，第一条 prompt 与后续普通 prompt 的代码应相同，统一调用 `submit_followup(queue)`。
- Command mutation 与 event observation 分离：`submit_followup(...)` / `retry_run(...)` / `replay_run(...)` 只负责提交输入或控制命令；Host event stream 负责观察 Session / Run 事件。调用方可以先打开 session-level live watch 再提交命令；不能要求 `submit_followup` 与内部 run-scoped EventLog 补读严格顺序绑定。离线 / 未 attach 时不靠 live watch 收中间过程，拿到 / attach Session 前发生的 terminal/final answer 通知由 Outbox 承接。
- Codex / Claude Code 类调用方的目标形态是：`async with open_host(options) as host:`，随后通过同一个 `host` 调用 `ensure_session(...)` / `create_session(...)` / `get_session(...)` 拿到 `session_id`；保存 `last_seen_terminal_event_sequence` / `seen_terminal_event_ids`，未来 Phase 13 通过 Outbox 读离线 terminal/final answer 增量；同时或随后打开 `watch_session_events(session_id) -> AsyncIterator[HostEvent]`；用 `terminal_event_id` / `event_sequence` / `run_id` 去重；通过 `submit_followup(...)` 发送 prompt，并从 terminal HostEvent 观察在线 final answer。P10.5 不实现 Outbox concrete read / drain API，不把离线 terminal 补读计入 smoke coverage，不定义 `wait_final_answer(...)` public API，也不把 `stream_run_events(...)` / `HostEventView` 放进普通 Service-facing public contract。
- `start_run(...)` 不再作为 Service-facing public API 暴露；Host 内部 admission primitive 固定命名为 `_start_run(...)`。P10.5 plan 必须包含 public export、README 与 tests 的同步策略。

不进入普通 Service-facing public contract 的候选 / 旧接口：

- `wait_final_answer(...)`：已删除，final answer 主路径是 terminal HostEvent。
- `read_payload(ref)` / `get_run_result(...)` / public payload reader：已删除，普通 Service 不读内部 payload。
- scheduler / wakeup / dispatch control API：已删除，`open_host(options)` 内部接线。
- `create_host_command_handle(...)`：降为内部 / 低层测试 composition primitive。
- `HostLocalRuntime` / `HostLocalExecutionOptions`：内部 contract。
- `stream_run_events(...)` / `HostEventView`：内部 diagnostic / detail / debug / drill-down 契约；P13 projections 不依赖它，普通 Service 不依赖它。

P10.5 第一目标：冻结普通本地多轮会话的 Host public interface / contract，查漏补缺生产接线和组件，确保后续真实生产系统 Service 调用 Host public interface / contract 即可完成多轮会话闭环。冻结对象是真实生产系统 Service 未来也会使用的 Host contract，不是给测试、smoke 或薄 Service 单独准备的特殊入口。P10.5 自身必须把真实生产系统 Service 将来接入所需的 Host 普通多轮生产接线做实；真实 CLI / web / GUI 在 P11-P15 实施完毕后会通过 Service 使用这里冻结的 Host public interface / contract 接入，不能等到真实入口接入时再补一条新接线。后续 P11-P15 仅扩展 Host 能力，不改变普通多轮会话的生产接线。

P10.5 第二目标：用 smoke 验证第一目标成立。smoke 应证明一个最小调用方只通过普通 Service 也会使用的 Host public API，即可完成 no-tool / mock-tool / real-runner 的普通本地多轮会话。

为达成这两个目标，它应该补齐以下内容：

- 定义并实现稳定的 `open_host(options)` async public contract 与 Host handle facade；内部统一打开 command handle、durable store、scheduler、active registry、local execution、ToolingOptions、compactor、projection catch-up 与关闭流程，但这些装配细节不泄漏给 Service。
- 让 public command facade 的 accepted / queued / resolve-wait dispatch wakeup 能稳定接到 scheduler，不要求 Service 读取内部 dispatch row。
- 将 memory catch-up 与 context overflow compact 作为 P10.5 查漏补缺项接入 public opener / handle：普通 Service 不能手工装配 memory projection、compact artifact store、scheduler pre-start governance 或 dispatch internals；Host opener 必须提供明确的 construction-time contract 来接收 / 配置 compactor、budget policy、artifact root 和 memory catch-up。
- 同步 public Run API 测试和 Host README，把 P10 后 `submit_followup(queue)` response shape、`ACCEPTED / QUEUED -> scheduler governance -> RUNNING` 状态语义、`queued_run_id` 非主 contract 写清楚。
- 提供普通 Service 可用的 typed HostEvent terminal contract；`watch_session_events(...)` public 形态固定为朴素 `AsyncIterator[HostEvent]`，对齐 Engine `run_agent_messages(...)`，不暴露 context manager / subscription handle。P10.5 必须明确 terminal HostEvent 的 final answer view，以及 Host closed、session not found / gone、consumer cancel / early close 的错误与收尾语义。P10.5 不定义 `wait_final_answer(...)` public API。
- 给出最小调用方 recipe：打开 Host、ensure/create/get session、打开 session-level live watch、并发调用 `submit_followup(queue)` 发送第一条或后续普通 prompt、从 terminal HostEvent 读取 answer、cancel、关闭 Host。拿到 / attach Session 前发生的 terminal 通知由 Outbox 路径承接。该 recipe 只能使用普通 Service 未来也会使用的 Host public API。
- 将 `submit_followup(steer)`、`retry_run(...)`、`replay_run(...)` 与 cancel smoke 纳入 P10.5。当前 steer / retry / replay 代码只冻结 envelope 并返回 `UNSUPPORTED_OPERATION`；P10.5 不重新设计 G6 / G7 / G8，而是按 `docs/host/design.md` 已有 steer / cancel / retry / replay 语义补完整本地执行、状态迁移、dispatch 接线、public error/detail 与 smoke。cancel 不重开语义设计，但必须证明既有 public cancel commands 在 Host opener / session live watch / public read path 下可用。Recovery 专属的 `LOST` / `RECOVERING` retry / cancel / recovery 处理仍归 Phase 11，不得在 P10.5 偷做 startup recovery 或 positive orphan proof。
- 明确哪些装配可先由 mock / 写死输入提供：construction-time 全量 mock `ToolBundle`、per-run `tool_names` selector、写死 scene inputs、RunnerSpec、AgentPolicy、context window / reserved output tokens。compact smoke 不得用 mock / test-double compactor 作为 success signal，必须接入真实 compactor adapter，并显式使用独立于 ordinary Run override 的 compactor execution baseline。
- P10.5 success signal 删除 mock runner 多轮 smoke；runner test double 只能作为低层辅助测试，不能作为 public contract freeze 的 smoke 证据。
- compact smoke 必须使用普通 Host public opener / handle 路径，不得直接调用 dispatch scheduler、memory repair、compact artifact store 或 RunInputBuilder 内部接口来凑覆盖。它必须接入真实 compactor adapter，并覆盖 canonical compact event、artifact 写入、memory projection consumption 和下一轮 request 注入。
- 真实 runner 多轮 smoke 使用硬编码 runner 参数，参数参考 `dayu/config/llm_models.json`；P10.5 不实现 ConfigLoader。至少覆盖 mimo、ds/deepseek、gemini、qwen 四类配置；API key / 网络不可用时允许显式 skip 并记录原因，但测试文件和 wiring 必须存在。
- web tools 不进入 P10.5 范围；真实联网工具 smoke 不作为 P10.5 success signal。
- 涉及 public API 的任何新增或修改必须先讨论确认，再进入 implementation；不得把测试专用或薄 Service 专用接口未经讨论直接变成 Host contract。

完成这些后，才可以说：不考虑 Recovery，Host 已冻结普通本地多轮会话的 public contract；调用方程序员可以写一个普通 Service，按稳定 Host runtime API 完成普通本地多轮会话。

## Challenge Review 结论

按 `$phaseflow` / `$init-agents`，本轮已派发在线 review Agent 挑战本文档：

- `AgentMiMo`：`docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md`
- `AgentDS`：`docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md`
- `AgentCodex`：用户明确授权作为第三 challenge reviewer，`docs/reviews/post-p10-codex-challenge-20260518.md`
- `AgentGLM`：当前未在 `tmux-cli status` 中发现，未派发。

两份 challenge review 的总控裁决：

- accepted implementation requirement：缺稳定的 `open_host(options)` composition root；`create_host_command_handle(...)` 若当前仍从普通 public namespace 导出，必须移除或降级到明确 internal / low-level test helper namespace，普通 Service 只使用 `open_host(options)`。这一项不再需要 design 讨论。
- accepted implementation requirement：public Host handle facade 方法集合已由设计真源决定，不再作为 design open question；P10.5 必须把现有 command/read 能力包成 async handle methods，并禁止 Service 直接依赖 dispatch / durable / scheduler internals。
- accepted implementation gap：public command facade 与 scheduler wakeup 已由设计真源裁决为 Host 内部 ownership，不是待讨论 public contract；P10.5 必须补 production `open_host(options)` 接线，让 after-commit wakeup port、background supervisor、scheduler 与 shared active worker registry 位于同一 composition root，Service 不暴露也不调用 scheduler / wakeup / dispatch control。
- accepted blocking：缺 session-level `watch_session_events(...) -> AsyncIterator[HostEvent]` terminal event 的 final answer 展示接线；不能用 run-scoped stream 或独立 payload 表读取替代普通 Service 主路径。
- accepted blocking superseded：不再新增 terminal wait public contract；P10.5 已决策 final answer 只走 `watch_session_events(session_id)` terminal HostEvent 主路径。
- accepted blocking：memory catch-up 与 context overflow compact 不能停留在内部测试接线；P10.5 必须把 compactor、budget policy、compact artifact root 与 memory catch-up 纳入 Host public opener / handle construction contract，并用 public-path smoke 证明 compact 后下一轮仍能通过 memory / continuity 继续。
- accepted blocking：S1 / S2 / S3 smoke 尚未落地，现有测试不能证明 Service 只调 Host public interface / contract 即可完成普通本地多轮闭环。
- resolved implementation requirement：`open_host(options)` 的 options 边界已裁决为朴素 typed function 参数，不引入 ConfigLoader、全局配置系统或 service locator；scheduler wakeup ownership 已由设计真源裁决为 Host 内部 ownership；`watch_session_events(...)` public 形态已裁决为朴素 `AsyncIterator[HostEvent]`；Host opener close shutdown order 已裁决为 implementation requirement；typed HostEvent final answer view 已确认，P10.5 负责落地。
- resolved implementation requirement：follow-up execution target / scene-policy continuity 已裁决为“一个 `open_host(options)` 表达 Host runtime environment 与默认 execution baseline；普通 follow-up 默认沿用 baseline；不新增 per-run target / profile id 字段；每 Run 可变项第一版包括 `system_prompt`、`user_prompt`、`tool_names`、可选 typed `runner_spec` / `runner_options` / `agent_policy` 与必要 request metadata；换模型或改 `max_iterations` 等运行参数时直接传 typed 对象，不通过 profile registry 或无结构 override”。
- accepted implementation requirement：`SubmitFollowupRequest` 新 public shape 已裁决；P10.5 需要迁移代码、tests 和 README，普通 queue 不允许调用方传 `run_id`，Run id 由 Host admission 创建并通过 `FollowupSnapshot.accepted_run_id` 返回。
- accepted implementation requirement：per-run typed execution override 已裁决；P10.5 需要校验并冻结 effective `RunnerSpec` / `RunnerCallOptions` / `AgentPolicy`，让 dispatch / RunInputBuilder / LocalProxy 构造 `AgentRunRequest` 时使用该 Run 的 effective config，并用 smoke 证明同一 Session 不同 Run 可使用不同执行配置。
- accepted implementation requirement：per-run `tool_names` 已裁决；P10.5 需要接 request 字段、admission validation、effective tool set freeze、ToolRuntime subset build 和 smoke，覆盖 subset、empty=none、unknown rejection 与工具事实进入下一轮 continuity。
- accepted implementation requirement：真实 runner production wiring / smoke 已裁决；P10.5 使用硬编码 runner 参数，不做 ConfigLoader，必须走同一 `open_host(options)` public path；provider 不可用时显式 skip 并记录 validation。
- accepted implementation requirement：compactor execution baseline 已裁决；P10.5 需要在 `open_host(options)` 中以朴素 typed function 参数接收真实 compactor adapter 及其独立执行参数，ordinary Run 的 `runner_spec` / `runner_options` / `agent_policy` / `tool_names` override 不得隐式改变 compactor。compact smoke 必须证明该分离成立，并仍通过 canonical compact event、artifact 写入、memory projection consumption 和下一轮 RunInputBuilder 注入完成闭环。
- accepted non-blocking / evidence guard：现有 Phase 5 / Phase 10 集成测试只能作为内部 wiring 回归，不能作为 P10.5 public-path smoke coverage 证据。

因此，本文档当前仍是 P10.5 public API / contract decision discussion artifact；是否可以派 planning Agent 生成 implementation-ready handoff plan，以用户下一步确认和总控 gate 状态为准。
