# P5 Design Conformance Review - Codex - 2026-05-15

## Verdict PASS

P5 当前实现没有发现阻塞性设计偏离。Host 仍是 Run / Attempt / dispatch / cancel / promotion 的强治理真源；Engine contract 没有夹带 Host Attempt、dispatch record、recovery policy 等 Host 身份；LocalProxy / EngineWorker envelope 正确把 Host identity 留在 Host 侧；RunInputBuilder 的生产输入来自 durable facts / EventLog 与显式 typed providers。

结论：无 blocker，可进入 controller adjudication。

本结论不表示 P5 已完成后续 phase 能力，只表示当前 P5 生产路径与 `docs/host/design.md`、`docs/host/implementation-control.md`、`docs/host/phase5-runinputbuilder-local-dispatch-plan.md` 的阶段边界一致。仍需处理下文列出的非阻塞漂移和生产接线风险。

## Blocking Design Deviations

无。

没有发现以下阻塞问题：

- Engine 理解 Host Attempt / dispatch record / recovery policy。
- EngineEvent 夹带 Host attempt_id / execution_id / dispatch_record_id。
- dispatch record 被用作 lease / fencing / owner truth。
- `dayu.runtime` 反向依赖 Host / Engine / Service / UI / Fins。
- RunInputBuilder 从 UI / Service 临时状态、全局配置或 untyped bag 构造 Engine request。
- P5 提前硬编码 ToolRuntime / fetch_more / WAITING / Recovery takeover / RemoteProxy 等后续 phase 行为。

## Non-blocking Design Drift

1. `accept_worker_running_in_transaction` 仍暴露一条非生产 durable helper 路径，可能写出不完整的 P5 `ATTEMPT_RUNNING` payload。

   生产 scheduler 当前没有使用这条 helper，而是在 `HostDispatchScheduler._accept_worker_running` 内写入包含 `local_worker_id`、`worker_accepted_at`、`lane_name`、`lane_claim_id` 的完整 payload。风险在于后续维护者或测试若误用 `accept_worker_running_in_transaction`，会把 canonical fact 写成缺少 P5 诊断字段的形态，削弱审计、恢复诊断和一致性检查。

   建议 owner：Host durable transition hardening。后续应二选一：删除/内聚这条旧 helper，或扩展其输入并让生产 scheduler 复用同一条完整 transition。

2. `mark_dispatching_after_lane_row` 的 durable helper 仍允许 `PENDING -> DISPATCHING`，能力范围宽于生产 scheduler 的 P5 路径。

   生产路径先写 `WAITING_FOR_LANE`，拿到 runtime lane 后再 recheck 并写 `DISPATCHING`，符合 P5 plan。当前漂移点是底层 helper 仍可被其它调用方用来跳过 `WAITING_FOR_LANE` 诊断状态。短期不影响生产路径，但增加后续误接线风险。

   建议 owner：Host durable API tightening。后续可把 direct pending dispatch 限定为测试 helper，或在 helper 文档/命名/调用边界上收窄语义。

## Production Wiring Risks

1. `HostCommandHandleOptions.local_execution` 已是 typed option，但同步 `create_host_command_handle` 对非 `None` 的 `local_execution` 选择 fail-fast，而不是隐式打开 scheduler。

   这是一个已记录并经 controller 接受的生命周期边界选择：同步 command facade 不隐藏 async scheduler open/close 生命周期。它不是阻塞偏离，因为错误是显式的，且集成测试通过显式 `HostDispatchScheduler.open` 走真实 scheduler / lane / worker 路径。生产接线风险在于：上层 assembly 不能误以为只给 `HostCommandHandleOptions.local_execution` 赋值就会启动本地执行。

   建议 owner：Host lifecycle composition / controller。若后续需要一体化生产入口，应新增明确的 async composition factory，而不是让同步 facade 悄悄持有 scheduler。

2. terminal closeout 后的 queue promotion wakeup 仍可能把 wakeup 失败传播到 worker event task。

   当前 terminal 状态已经在 durable transaction 内提交；wakeup 失败主要影响诊断噪声、worker task 错误路径与 promotion 延迟，不会反向改变 terminal truth。实现控制文档也把该项列为 P5 后续硬化风险。

   建议 owner：Host dispatch lifecycle hardening。后续应把 terminal commit 与 promotion wakeup 的错误域分离，确保 wakeup 失败可诊断、可重试，但不污染已完成的 worker event 消费路径。

3. active cancel 没有 watchdog / takeover。

   P5 正确只实现 active cancellation registry 与 worker token/handle cancel，不提前做 Recovery / takeover。但如果 worker 永远不产出 terminal event，Run 可能停留在 `CANCELLING`，需要 Phase 11 Recovery 或 lifecycle watchdog 处理。

   建议 owner：Phase 11 Recovery / Host lifecycle hardening。

4. 默认 LocalProxy 的 `cancel()` 是 no-op，依赖 Host cancellation token 被 Engine runner 观测。

   这符合 P5 本地 runner 约束，但真实 provider / worker 必须持续遵守 cancellation token，否则 active cancel 只能进入 `CANCELLING`，无法靠 P5 自身保证终态。

   建议 owner：Engine runner integration / Phase 11 watchdog。

## Deferred Phase Readiness

- ToolRuntime / fetch_more：P5 没有实现工具治理路径。`fetch_more` 只作为保留名存在，RunInputBuilder 使用 no-tool provider / `NoToolExecutor`，Engine `tool_awaiting` 在 Host ingest 中转为诊断并失败关闭，符合 Phase 6/后续接线预留。
- WAITING / resolve_wait：`resolve_wait` 保持稳定 unsupported；Engine `run_suspended` / `tool_awaiting` 不创建 wait record、不进入 WAITING、不关闭为可恢复等待，符合 Phase 7 边界。
- Memory / Context Governance：RunInputBuilder 使用 no-op memory / compact provider；`context_compaction_requested` 在 ingest 中走 diagnostic + failed closeout，没有提前实现 context governance 或 `RECOVERING`。
- Recovery / takeover：dispatch record 仍只承载诊断、duplicate dispatch suppression、recovery 判断输入；P5 没有把 `lane_claim_id`、`dispatching`、`host_instance_id` 用作 lease / fencing / owner truth，也没有 takeover。
- Observer / Sink：P5 没有引入 Observer/Sink 生产路径；Engine events 只由 Host ingest 转成 Host facts / diagnostics / projections。
- RemoteProxy：`WorkerKind.REMOTE` 只保留枚举/后续扩展空间，当前生产 worker factory 仍是 LocalProxy 路径，没有提前接远端执行。

## Evidence by file/line

- `docs/host/design.md:21`-`58`：设计真源要求 `UI -> Service -> Host -> Engine`，Host 是状态治理真源，Engine 不理解 Host durable / policy / Session / Run / Attempt；dispatch、ingest、run input、runtime 边界都有明确职责。
- `docs/host/design.md:59`-`74`、`docs/host/design.md:76`-`194`：`dayu.runtime` 必须层中立，lane 只表示资源容量，不是 Host truth / lease / fencing / owner。
- `docs/host/design.md:2210`-`2285`：RunInputBuilder 只能通过 typed providers 从 durable facts / EventLog / policy snapshot 构造 Engine request，不读取 UI/Service 临时状态或 untyped bags。
- `docs/host/design.md:2434`-`2498`、`docs/host/design.md:2534`-`2549`：Recovery/takeover 是后续 phase；dispatch record 不能作为 ownership proof。
- `docs/host/phase5-runinputbuilder-local-dispatch-plan.md:23`-`30`：P5 要求 EngineEvent 不承载 Host identity，LocalProxy envelope 承载 Host identity，dispatch record 只用于诊断/去重/recovery 判断。
- `docs/host/phase5-runinputbuilder-local-dispatch-plan.md:34`-`44`：明确 P5 non-goals，包括 ToolRuntime/fetch_more、WAITING、Memory、Context Governance、Recovery、Observer/Sink、RemoteProxy。
- `docs/host/phase5-runinputbuilder-local-dispatch-plan.md:197`-`224`：生产 dispatch 路径必须 pending -> waiting_for_lane -> lane -> recheck -> dispatching -> worker accepted -> running -> ingest -> terminal/cancel -> release lane。
- `docs/host/implementation-control.md:1582`-`1606`：记录 P5-S3 已完成，同时明确 command-handle scheduler lifecycle wiring 未内嵌，为已接受风险。
- `docs/host/implementation-control.md:1638`-`1642`：记录 active cancel watchdog 与 terminal promotion wakeup failure 为 P5 后续硬化风险。
- `docs/host/implementation-control.md:1643`-`1660`：记录 P5-S6 完成，并列出 ToolRuntime、WAITING、Memory、Context Governance、Recovery、Observer/Sink、RemoteProxy 的后续 owner。
- `dayu/host/api.py:239`-`288`：`AttemptDispatchSnapshot` 只承载 Host 侧 durable identity / dispatch / policy ref / cancellation token。
- `dayu/host/api.py:290`-`361`：`LocalEngineWorker` / factory 协议返回公共 `EngineEvent` 流，不要求 Engine 事件携带 Host identity。
- `dayu/host/api.py:365`-`463`：`HostLocalExecutionOptions` 是 typed 本地执行配置，包含 lane、runner、policy、worker factory。
- `dayu/host/api.py:739`-`768`：`HostCommandHandleOptions.local_execution` 是 typed option，`None` 表示 no-op dispatch wakeup。
- `dayu/host/command.py:195`-`211`：同步 command factory 对 `local_execution` 非 `None` fail-fast，避免隐藏 async scheduler lifecycle。
- `dayu/host/command.py:361`-`450`：cancel path 通过 admission 返回 active cancel targets，再由 command handle 传播到 active worker registry。
- `dayu/host/command.py:487`-`501`：`resolve_wait` 保持 unsupported，没有提前实现 WAITING。
- `dayu/host/admission.py:145`-`170`：`AdmissionWakeupPort` 是 post-commit wakeup port，不进入 durable transaction。
- `dayu/host/admission.py:413`-`442`、`dayu/host/admission.py:595`-`618`：start / queued promotion 在 durable commit 后触发 dispatch wakeup。
- `dayu/host/dispatch.py:1`-`8`：模块 docstring 明确 dispatching / lane token 不是 owner / lease / fencing / takeover truth。
- `dayu/host/dispatch.py:137`-`207`：`ActiveWorkerRegistry` 是进程内 best-effort cancel registry，durable truth 仍在 EventLog / state。
- `dayu/host/dispatch.py:465`-`508`：生产 dispatch 先写 `waiting_for_lane`，再获取 lane，再 recheck 并写 `dispatching`。
- `dayu/host/dispatch.py:601`-`671`：scheduler 用 `RunInputBuilder` 和 `AttemptDispatchSnapshot` 创建 worker，worker accept 成功后才进入 active registry。
- `dayu/host/dispatch.py:711`-`778`、`dayu/host/dispatch.py:1019`-`1029`：生产 `ATTEMPT_RUNNING` payload 包含 worker / lane 诊断字段。
- `dayu/host/dispatch.py:827`-`924`：worker event 消费用 `LocalEngineEnvelope` 把 Host identity 包在 Host 侧，再交给 `EngineEventIngestor`。
- `dayu/host/dispatch.py:926`-`990`：worker accept 前后都重新读取 durable Run / Attempt / dispatch 状态，避免把 dispatch record 当 owner truth。
- `dayu/host/local_proxy.py:1`-`6`：LocalProxy 只桥接 Engine public entry，不负责 ingest、terminal、tool、recovery。
- `dayu/host/local_proxy.py:92`-`103`：LocalProxy 调用 Engine public `run_agent_messages(request)` 获取 EngineEvent。
- `dayu/host/local_proxy.py:105`-`116`：LocalProxy `cancel()` no-op，取消依赖 Host cancellation token。
- `dayu/host/engine_ingest.py:1`-`8`：模块 docstring 明确 EngineEvent 不携带 Host identity，identity 来自 envelope 与 durable state。
- `dayu/host/engine_ingest.py:123`-`163`：`LocalEngineEnvelope` 与 `EngineEventCandidate` 把 Host identity 和 worker event index 留在 Host ingest 边界。
- `dayu/host/engine_ingest.py:377`-`483`：`run_failed(recoverable)`、`tool_awaiting`、`run_suspended`、`context_compaction_requested` 都走 P5 diagnostic + failed/unsupported 路径，没有提前进入 Recovery/WAITING/Context Governance。
- `dayu/host/engine_ingest.py:485`-`517`：ingest 重新从 durable state 校验 Run / Attempt / dispatch 与 envelope 一致。
- `dayu/host/engine_ingest.py:519`-`620`：terminal closeout 在 Host transaction 内写 Host facts，Engine event 只是输入。
- `dayu/host/engine_ingest.py:810`-`832`：terminal closeout 后触发 queue promotion wakeup；wakeup 失败是已知生产硬化风险。
- `dayu/host/engine_ingest.py:1111`-`1129`：candidate shape 校验 EngineEvent session/run 与 envelope 匹配，不从 EngineEvent 读取 Host identity。
- `dayu/host/engine_ingest.py:1159`-`1183`：Host event id 由 `execution_id`、`worker_event_index`、event class/type/sub-index 派生，符合 P5 去重设计。
- `dayu/host/run_input.py:1`-`7`：模块 docstring 明确只读 durable facts / EventLog 与 explicit policy snapshot，不读取 UI/Service/temp/scheduler/LocalProxy/ToolRuntime/Memory/Context Governance。
- `dayu/host/run_input.py:175`-`298`：RunInputBuilder 使用 typed provider protocols。
- `dayu/host/run_input.py:300`-`393`：当前 user prompt 来自 durable `USER_INPUT_ACCEPTED`，并校验 Run / Attempt / dispatch 快照。
- `dayu/host/run_input.py:451`-`503`：Memory / compact / tool schema provider 均为 no-op。
- `dayu/host/run_input.py:506`-`531`：`NoToolExecutor` 明确关闭 P5 工具执行路径。
- `dayu/host/run_input.py:624`-`713`：Engine `AgentRunRequest` 由 typed provider 输出构造，消息顺序固定且无 untyped bag。
- `dayu/host/durable/schema.py:342`-`439`：dispatch record schema 使用 pending / waiting_for_lane / dispatching / cancelled，并通过 nullability/checks 固化 P5 字段约束。
- `dayu/host/durable/state.py:50`-`62`：`DispatchRecordStatus` docstring 明确 dispatch status 不是 lease / fencing / owner truth。
- `dayu/host/durable/state.py:2016`-`2074`：pending -> waiting_for_lane transition。
- `dayu/host/durable/state.py:2077`-`2171`：mark dispatching helper 仍允许 pending 或 waiting_for_lane 进入 dispatching，是非阻塞漂移证据。
- `dayu/host/durable/state.py:2174`-`2228`：worker accepted refs 只更新 dispatch diagnostic 字段，状态仍是 dispatching。
- `dayu/host/durable/run_transition.py:833`-`899`、`dayu/host/durable/run_transition.py:1465`-`1506`：非生产 `accept_worker_running_in_transaction` 的 `ATTEMPT_RUNNING` payload 缺少 P5 worker/lane 字段，是非阻塞漂移证据。
- `dayu/host/tooling.py:36`-`39`、`dayu/host/tooling.py:104`-`117`：`fetch_more` 仅作为保留 framework tool 名，不启用 ToolRuntime。
- `dayu/runtime/lane.py:1`-`7`、`dayu/runtime/lane.py:24`、`dayu/runtime/lane.py:144`-`178`：lane 是层中立容量控制，只依赖公共 cancellation contract 与独立 SQLite db path。
- `dayu/runtime/cancellation.py:1`-`33`、`dayu/runtime/cancellation.py:44`：runtime cancellation helper 层中立，不 import Host / Engine。
- `dayu/engine/contracts/engine_events.py:1`-`8`、`dayu/engine/contracts/engine_events.py:33`-`54`：EngineEvent 是公共 Engine event contract，事件类型不包含 Host Attempt / dispatch / recovery 身份。
- `dayu/engine/agent.py:1446`-`1453`：Engine 明确不处理 Host ToolRuntime governance。
- `dayu/engine/agent.py:1614`-`1647`：Engine 只发公共 `TOOL_AWAITING` / `RUN_SUSPENDED`，不写 Host wait state。
- `tests/host/test_import_boundary.py:24`-`37`、`tests/host/test_import_boundary.py:125`-`169`：测试约束 Host/runtime/engine import 边界。
- `tests/host/test_command_handle.py:356`-`389`：测试确认 sync command factory 不隐式消费 local execution 配置。
- `tests/host/test_phase5_local_execution_integration.py:1054`-`1094`：P5 集成测试显式打开 `HostDispatchScheduler`，走真实 scheduler / lane / fake worker 路径。

## Residual Risks with owner

- Host lifecycle composition / controller：决定是否提供明确 async production assembly factory，把 command facade、scheduler open/close、LocalProxy factory、lane db 生命周期组合成一个稳定入口。
- Host durable transition hardening：清理或升级 `accept_worker_running_in_transaction`，避免未来写出缺少 P5 worker/lane 诊断字段的 canonical fact。
- Host durable API tightening：收窄 `mark_dispatching_after_lane_row` 的 pending -> dispatching 能力，降低跳过 `WAITING_FOR_LANE` 的误接线风险。
- Host dispatch lifecycle hardening：隔离 terminal commit 与 queue promotion wakeup 的错误域，避免 wakeup 异常污染 worker event task。
- Phase 11 Recovery / Host lifecycle hardening：为 active cancel 卡在 `CANCELLING`、worker lost、process crash 后恢复补齐 watchdog/recovery/takeover 语义。
- Engine runner integration：确保真实 Engine/provider 路径持续观测 Host cancellation token；否则 P5 active cancel 只能 best-effort。
- RunInputBuilder consistency cleanup：当前 provider 读取以 durable facts 为源，但不同 provider 调用之间不是单一整体 read snapshot；短期在 P5 单 active run/dispatch recheck 下风险低，后续可考虑统一 read snapshot 以降低 TOCTOU 面。

## Open Questions

无阻塞 open question。

非阻塞问题：controller 最终希望生产入口保持“显式打开 scheduler + command handle”两段式，还是新增 async composition factory 作为唯一生产装配入口？该问题不影响 P5 进入 controller adjudication，但会影响后续生产接线的人机使用面和生命周期责任边界。
