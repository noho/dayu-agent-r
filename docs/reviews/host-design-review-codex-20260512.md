# Host design.md adversarial review

- **review gate**: design review
- **review target**: `docs/host/design.md`
- **context only**: `docs/host/discussion-note.md`, `docs/host/implementation-control.md`
- **scope boundary**: 只 review 设计真源是否足以支撑后续 phase plan；不写 implementation plan，不修改 `design.md`。
- **结论**: `fail`

## 动机判断

本次 review 动机成立。`implementation-control.md:29-31` 明确 `design.md` 是“规范化后的 Host 架构真源”和后续 handoff implementation-ready plan 的主真源；`implementation-control.md:41-45` 要求若 `design.md` 漏掉或误写已确认决议，先修 `design.md` 再继续 phase plan。当前 `design.md` 已覆盖方向性目标，但仍有多个核心契约没有收敛到可直接派发给 phase plan agent 的粒度。

## Assumptions Tested

- Host 必须是 Session / Run / Attempt / EventLog / admission / cancel / resume / retry / steer / replay / memory / tool governance 的治理真源。
- Engine 只执行单次 `AgentRunRequest`，不拥有 Host 生命周期和 durable state。
- 第一版必须支持单机多客户端 / 多进程，并允许本地 Engine 与远程 Engine 并列执行。
- 后续 phase plan agent 不应自行发明状态迁移、事件契约、API 边界、持久化一致性或 remote semantic contract。

## Controller 状态标注（2026-05-12）

本 review 的 findings 已按当前 `docs/host/design.md` / `dayu/README.md` / `docs/host/implementation-control.md` 重新裁决：
下方原始严重度、blocking/high 标记和修正建议保留为 review-time 记录；后续 plan / implementation 以本节状态为准。

| Finding | 状态 | 归属 / 说明 |
| --- | --- | --- |
| 1 Run/Attempt 状态机没有收敛成可执行迁移矩阵 | 已处理 | `design.md` 已补 Run / Attempt 状态、active Run、admission、transition matrix、RECOVERING 退出、cancel / steer / terminal 竞态和 CAS 不变量；typed implementation 细节进入对应 phase。 |
| 2 Canonical EventLog 只有事件名列表，没有事件契约矩阵 | 已处理 | `design.md` 已补 global `event_sequence`、canonical event contract matrix、EngineEvent mapping、canonical / preview / projection 边界。 |
| 3 公共 API 没有覆盖 wait/resume/retry/replay | 已处理 | `design.md` 公共接口已补 `retry_run`、`replay_run`、`resolve_wait`，并区分 public / control / adapter 语义。 |
| 4 Durable queue promotion 多进程调度契约缺失 | 已处理 | `design.md` 已补 per-session FIFO、promotion trigger、CAS 抢 active slot、promotion transaction 和 queued cancel 语义。 |
| 5 Recovery scan owner / liveness 替代契约缺失 | 已处理 | `design.md` 已补 attempt dispatch record、host instance / worker kind / connection state 语义，明确它不是 lease / fencing，旧 Attempt 只 LOST 不 takeover。 |

## Findings

### 1-已处理-[严重]-Run/Attempt 状态机没有收敛成可执行迁移矩阵

- **标题**: Run/Attempt 状态机没有收敛成可执行迁移矩阵
- **严重程度**: 严重
- **位置**: `docs/host/design.md:114-205`, `docs/host/design.md:327-358`, `docs/host/design.md:758-828`, `docs/host/design.md:953-963`
- **当前写法**: 文档列出 Run 状态、Attempt 状态、部分路径片段和若干竞态原则。例如 `Run RUNNING -> CANCELLING`、`Attempt SUSPENDED -> Run WAITING`、steer 创建新 Attempt、cancel 与 suspend 遵循 ingest 顺序。
- **为什么有问题**: 这些描述不足以让 phase plan agent 直接生成实现。缺少按操作划分的状态迁移矩阵：每个 API / internal operation 的允许源状态、目标状态、CAS 条件、必须 append 的 canonical events、错误分类、终态优先级、迟到事件处理和重复调用幂等语义都没有规范化。尤其是 `WAITING` 上 cancel / resume / steer / replay 的相互关系、`RECOVERING` 如何重新进入 `RUNNING`、`FAILED` 后 retry 和 replay 的边界、terminal race 已提交后的 steer 降级行为，在 `design.md` 中仍需要实现 agent 自行推导。
- **影响**: 后续 phase plan 会不可避免地重新设计状态机，导致 Host 真源分裂；多进程 CAS 条件、EventLog append 顺序和用户可见状态可能不一致。最坏情况下，cancel / suspend / replay 竞态会写出互相矛盾的 Run terminal fact，或把本应创建新 Attempt 的路径误实现成旧 Attempt resume。
- **建议改法**: 在 `design.md` 增加状态迁移契约矩阵，至少按 `start_run`、queued promotion、`submit_followup(queue)`、`submit_followup(steer)`、`cancel_run`、`resolve_wait/resume`、`retry`、`replay`、worker terminal ingest、recovery scan 分类。每行写清 precondition、from status、to status、Attempt 行为、canonical events、CAS expected state、idempotency key、错误分类和 terminal race precedence。验证点是 phase plan 不需要自行选择任何状态迁移。
- **是否阻塞 design.md 作为 plan 真源**: 是。

### 2-已处理-[严重]-Canonical EventLog 只有事件名列表，没有事件契约矩阵

- **标题**: Canonical EventLog 只有事件名列表，没有事件契约矩阵
- **严重程度**: 严重
- **位置**: `docs/host/design.md:360-481`, `docs/host/implementation-control.md:129-132`
- **当前写法**: `design.md` 定义 EventLog shape、最小 canonical events 列表和 EngineEvent 默认映射，并要求 implementation plan “turn this mapping into typed code and tests”。但事件级 payload、必填字段、关联对象、允许 source、幂等键、顺序约束、状态索引更新和 projection 输入边界没有矩阵化。`implementation-control.md` 在 design 生成前明确列出仍需规范化 `Canonical EventLog event contract matrix`。
- **为什么有问题**: EventLog 是恢复、stream、memory、audit、usage、tool trace、outbox 的 canonical fact source；仅有事件名无法作为生产级事实契约。比如 `RUN_SUCCEEDED + ATTEMPT_SUCCEEDED` 的提交顺序、是否共享同一 transaction、`TOOL_AWAITING` 与 wait record 的 payload/ref、`TOOL_TERMINAL_RESULT` 的工具幂等键、`GUIDANCE_INSERTED` 是否进入 RunInputBuilder、`PROVIDER_PROTOCOL_ERROR` 何时 terminal，都没有直接答案。
- **影响**: phase plan agent 会把事件 payload 和状态更新分散发明，导致 replay/resume/memory 无法稳定重建；audit 和 tool trace 可能缺少责任链字段；远端重复事件或迟到事件的去重也可能污染 canonical EventLog。
- **建议改法**: 在 `design.md` 增加 canonical event contract matrix。每个 event 至少写 `event_type`、scope、required ids、required payload keys、payload_ref/digest 规则、idempotency/dedup key、allowed producer、state index side effects、projection consumers、是否可用于 memory/resume/audit、terminal / non-terminal 分类。EngineEvent 映射应引用该矩阵，而不是让 implementation phase 重发明边界。
- **是否阻塞 design.md 作为 plan 真源**: 是。

### 3-已处理-[高]-公共 API 没有覆盖 wait/resume/retry/replay 的 Host 控制入口

- **标题**: 公共 API 没有覆盖 wait/resume/retry/replay 的 Host 控制入口
- **严重程度**: 高
- **位置**: `docs/host/design.md:279-325`, `docs/host/design.md:696-756`, `docs/host/design.md:758-797`
- **当前写法**: 第一版最小接口只列出 `create_session`、`get_session`、`close_session`、`start_run`、`get_run`、`stream_run_events`、`cancel_run`、`submit_followup`。但后文定义了 `resolve_wait(wait_id, outcome, source, idempotency_key)`、resume、retry、replay 语义，并把 `RESUME_REQUESTED`、`REPLAY_REQUESTED` 纳入 canonical events。
- **为什么有问题**: Host 被定义为 resume / retry / replay 治理真源，但这些控制动作没有明确是公共 API、Service-only API、internal scheduler API 还是 ToolRuntime callback API。缺少 request / response snapshot、idempotency key、权限错误、invalid state、conflict 和 retry/replay policy 输入。`resolve_wait` 是否是 public Host API 也不清楚。
- **影响**: wait/resume phase 和 replay phase 必须自行决定 API 边界，容易把外部 callback、poll adapter、manual resolve 或 replay 操作做成 ad hoc 入口；上层 Service 也可能绕过 Host 拼接恢复输入，违反 `RunInputBuilder` 是唯一运行态入口的约束。
- **建议改法**: 在公共接口章节增加控制入口分层：例如 public/service callable、internal scheduler callable、adapter callable。至少规范 `resolve_wait`、`retry_run`、`replay_run` 是否进入第一版最小接口；若不进入，说明哪个 Host-owned internal entrypoint 承接、谁能调用、请求字段、幂等语义和错误分类。对应补齐 `ResumeRequest` / `ReplayRequest` / `RetryRequest` 或明确 non-goal。
- **是否阻塞 design.md 作为 plan 真源**: 是。

### 4-已处理-[高]-Durable queue promotion 的多进程调度契约缺失

- **标题**: Durable queue promotion 的多进程调度契约缺失
- **严重程度**: 高
- **位置**: `docs/host/design.md:207-253`, `docs/host/design.md:255-278`, `docs/host/implementation-control.md:129-135`
- **当前写法**: 设计规定同一 Session 同时最多一个 active Run，`QUEUED` 不占 active slot，SQLite 事务、唯一约束和 CAS-style state transition 负责多进程一致性；但 `QUEUED` Run 何时、由谁、按什么顺序 promotion 到 `RUNNING` 没有定义。`implementation-control.md` 已把 “Durable queue 调度触发和优先级规则” 列为 design 生成时仍需规范化事项。
- **为什么有问题**: “同一 Session 最多一个 active Run” 是 admission 的核心不变量，但 durable queue 的触发条件、排序键、公平性、promotion CAS、active slot 约束和新 `start_run` 与已有 queued run 的优先关系都缺失。多进程下两个 Host 进程可能同时观察到无 active Run 并各自 promotion；或者新请求绕过旧 queued run 直接启动，破坏 durable queue 的用户语义。
- **影响**: 单机多客户端 / 多进程目标不稳，queued follow-up 可能乱序、饥饿或重复执行；phase plan agent 会自行设计 scheduler 表、索引、CAS 条件和测试预期，后续 review 难以判断是否符合真源。
- **建议改法**: 在 design 中定义 durable queue promotion contract：排序键、eligible 条件、promotion trigger、active slot CAS 条件、session-level uniqueness 约束、promotion transaction 内必须 append 的 events、失败重试语义、queued cancel 与 close_session 的处理，以及新 `start_run(queue_policy=queue|reject|attach_active)` 与 existing queued run 的优先级关系。验证点包括双进程并发 promotion 只能成功一个、queued order 稳定、cancel queued 不创建 Attempt。
- **是否阻塞 design.md 作为 plan 真源**: 是。

### 5-已处理-[高]-Recovery scan 引入 “current Host owner” 但没有 owner/lease/fencing 替代契约

- **标题**: Recovery scan 引入 “current Host owner” 但没有 owner/lease/fencing 替代契约
- **严重程度**: 高
- **位置**: `docs/host/design.md:235-242`, `docs/host/design.md:953-963`, `docs/host/design.md:974-986`
- **当前写法**: 设计明确不引入重 lease / fencing，不做旧 Attempt takeover；但 recovery scan 规则写成 `RUNNING` / `CANCELLING` Run 的 active Attempt “若无法确认仍被当前 Host owner 执行，旧 Attempt 进入 LOST”。文档没有定义 `Host owner` 是什么、如何持久化、如何确认、如何避免误判仍在执行的本地/远程 worker。
- **为什么有问题**: 在多进程和远程执行并列的目标下，recovery scan 不能依赖未定义 ownership。若没有 lease/fencing，又没有轻量 owner heartbeat / process identity / startup epoch / dispatch record / diagnostic timeout 语义，phase plan agent 必须自己决定何时把 active Attempt 标为 `LOST`。这会直接影响 cancel timeout、remote disconnect、Host restart 和 worker late event 的治理结果。
- **影响**: 一个新 Host 进程可能把仍在运行的 Attempt 标为 `LOST` 并创建新 Attempt，造成重复工具调用或重复外部副作用；反过来也可能因为无法确认 owner 而永远不 recovery。远端迟到事件与新 execution_id 的去重虽然能保护 EventLog，但不能消除重复执行成本和外部副作用风险。
- **建议改法**: 设计需补一个不等价于重 lease/fencing 的最小 execution ownership / liveness contract。至少定义 dispatch record、host instance id、worker kind、本地进程/远端连接标识、last observed event time、确认仍在执行的可用信号、超时后进入 `LOST` 的 policy，以及 recovery scan 的 CAS 条件。若第一版不实现 heartbeat，也要明确只能基于哪些 durable facts 和 timeout 做保守 closeout。
- **是否阻塞 design.md 作为 plan 真源**: 是。

## Open Questions

- `stream_run_events(run_id, cursor)` 的 cursor 语义依赖 `sequence`，但 `design.md:394` 把 global/per-session/per-run sequence 留给 implementation phase。若 EventLog phase 是第一个落地项，这个问题应在修订 design 时一并收敛。
- Observer / Sink 已定义边界，但 notification 与 checkpoint 的最小可靠语义仍偏原则化。若后续先做 projections/outbox phase，需要先补 sink wakeup、retry、checkpoint 原子性与 lag 可观测契约。
- `TruncationManager / fetch_more` 将 cursor 生命周期、TTL、读取 limit、重复续读和取消收口留给 policy。若 ToolRuntime phase 早于 memory/context phase，需要先把 cursor durable/ephemeral 边界补清。

## Residual Risks

- Remote wire protocol 细节被明确放到 Remote phase discussion，这本身可以接受；但在进入任何 Remote phase plan 前，必须先补最小 remote event envelope、event id/sequence 来源、ack/retry 与 version compatibility 的语义边界，否则 remote phase 会重做设计。
- Context governance 和 memory 参数默认值留到 phase 决策是合理的，但 canonical facts-to-messages 的测试 oracle 仍需要在对应 phase 前具体化。

## Final Review Conclusion

`docs/host/design.md` 目前方向与目标基本一致，但存在 blocking findings。它还不能作为后续 phase plan 的唯一主真源。建议先修正上述 5 个 blocking 契约，再进入 phase 编排；修复后应重新做 design review，确认 phase plan agent 不需要自行补状态机、事件矩阵、控制 API、多进程 queue 或 recovery ownership 设计。
