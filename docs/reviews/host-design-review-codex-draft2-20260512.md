# Host design draft2 review - Codex - 2026-05-12

## Controller 状态标注（2026-05-13）

本 review 的 findings 已按 `docs/reviews/host-design-review-draft2-controller-adjudication-20260512.md` 裁决，并已写回 `docs/host/design.md`。下方原始“未修复”标记保留为 review-time 记录；后续 plan / implementation 以本节状态和当前 `design.md` 为准。

| Finding | 状态 | 归属 / 说明 |
| --- | --- | --- |
| 1 Run 终态 vs retry/replay | 已写回 | `retry(run)` / `replay(run)` 创建关联新 Run，源 Run 终态不重开。 |
| 2 外移 payload co-durability | 已写回 | SQLite payload table + artifact 分层、digest verified 后 append canonical EventLog。 |
| 3 API actor/source/context | 已写回到架构级 | mutating request 必须携带 HostCallContext / request envelope；required fields 不进 metadata。 |
| 4 event identity model | 已写回 | client operation id、remote event identity、canonical event identity 分层。 |
| 5 remote minimum semantic contract | 已写回 | design 只写 remote semantic contract，不写 wire protocol；remote at-least-once 风险边界写入。 |
| 6 ToolRuntime durable accept barrier | 已写回 | Host-mediated accept barrier；tool fact durable accepted 后才能返回 Engine。 |
| 7 Attempt STARTING / RUNNING | 已写回 | `ATTEMPT_STARTED` 创建 `STARTING`，`ATTEMPT_RUNNING` 表示 worker accepted。 |
| 8 Outbox intent truth | 已写回 | terminal EventLog fact 是 delivery intent 真源，OutboxSink 派生 delivery record。 |

## Findings

### 1-未修复-[严重]-Run 终态与 retry/replay 重新进入 RUNNING 的状态机互相冲突
- **位置**: `docs/host/design.md` 6 节 Run 生命周期，150-157 行；8.1 状态迁移契约，303-304 行；20 节 Retry / Replay，1086-1102 行；15 节 Outbox，811-816 行。
- **问题类型**: 状态机漏洞 / 契约缺失 / 并发恢复风险。
- **当前写法**: `SUCCEEDED`、`FAILED`、`CANCELLED`、`LOST` 被定义为 Run 终态；但 `retry_run` 允许 `FAILED -> RUNNING`，`replay_run` 允许 `SUCCEEDED -> RUNNING`，且 replay 会更新同一 Run 的 current result projection。
- **反例/失败场景**: 一个 Run 已 `SUCCEEDED` 并触发 outbox 投递后，用户要求 replay；同时该 Session 的 queued Run 已因前一个 Run terminal 被 promotion。实现 agent 既可能按“终态不可变”拒绝 replay，也可能把已终态 Run 重新置为 `RUNNING`，从而破坏同一 Session 最多一个 active Run、FIFO promotion、outbox 幂等和 terminal result 审计链。
- **为什么有问题**: “终态”如果可以被同一 Run 的 retry/replay 重新打开，就不是终态；如果不可打开，当前 `retry_run` / `replay_run` 公共 API 和状态迁移矩阵不可实现。EventLog 还会留下多个 `RUN_SUCCEEDED` / `RUN_FAILED` 链路，但 current result、outbox delivery、Session timeline 和 replay result version 没有统一语义。
- **直接证据**: 150-157 行定义 Run 终态；303-304 行把 `FAILED` / `SUCCEEDED` 作为 retry/replay 前置状态并转回 `RUNNING`；1097-1102 行要求同一 Run replay 并更新 current result projection；813-816 行把 Run terminal 后的 final answer 投递交给 outbox。
- **影响**: phase plan 无法安全生成 Run 状态机、EventLog terminal event、outbox、admission queue promotion 和 replay/retry API；实现会在“终态不可变”和“同一 Run 多版本执行”之间自行设计。
- **建议改法和验证点**: 先二选一并写回设计：要么保持 Run terminal 不可变，retry/replay 创建新 Run 并通过 source_run_id / replay_of 关联；要么显式设计 versioned Run lifecycle，例如 result_version、attempt_generation、`REPLAYING` / `RETRYING` 或 terminal supersession event，并定义 replay/retry 与 active slot、queued promotion、outbox per-version delivery、RunSnapshot current result 的关系。验证点至少覆盖 terminal 后 replay、failed 后 retry、queued promotion 竞态、outbox 已投递后 replay。
- **修复风险（低/中/高）**: 高。
- **严重程度（低/中/高/严重）**: 严重。
- **是否阻塞 phase planning**: 阻塞。Run 状态机、retry/replay、outbox、admission 相关 phase 在修正前不应进入 implementation-ready plan。

### 2-未修复-[严重]-外移 payload / cursor descriptor 没有 co-durability 契约，EventLog 恢复真源不成立
- **位置**: `docs/host/design.md` 12.1 Payload 存储，591-597 行；18 节 TruncationManager / fetch_more，959-991 行；22 节 RunInputBuilder，1174-1182 行；26 节 Recovery，1300-1313、1352-1358 行。
- **问题类型**: 契约缺失 / 数据损坏 / 不可恢复。
- **当前写法**: 大工具结果、财报 chunk、完整 prompt / messages 等外移到 artifact / blob / tool trace / 领域仓储；外移 payload 缺失或损坏“不能破坏状态恢复”。同时 truncation cursor / `scope_token` 进入 messages 或 EventLog 后，必须能恢复到 durable descriptor / artifact ref；`RECOVERING -> LOST` 又把必要 payload / anchor 缺失列为无法恢复原因。
- **反例/失败场景**: 财报读取工具返回被截断的大段证据，Host append `TOOL_RESULT_ACCEPTED`，payload_ref 指向外部 artifact；进程在 artifact 未持久化或 digest 未确认时崩溃。重启后 EventLog 表示工具事实已接受，但 RunInputBuilder / `fetch_more` 不能读取后续内容，或者只能发现 digest 不匹配。此时既违反“accepted facts 可恢复”，也违反“外移 payload 缺失不能破坏状态恢复”。
- **为什么有问题**: EventLog 是 append-only canonical fact source，但设计只规定 EventLog 与 Run / Attempt 状态索引同事务，没有规定外部 payload、truncation descriptor、evidence anchor ref 与 canonical event 的写入顺序、digest 校验、retention 和 commit marker。对买方财报分析 Agent，工具事实和 evidence anchor 是答案可信度核心，不是普通展示附件。
- **直接证据**: 593-597 行允许大 payload 外移并声明缺失不破坏恢复；964-989 行又要求 cursor / `scope_token` 可由 Host-governed descriptor / artifact ref 恢复；1174-1182 行要求 accepted tool result / evidence anchor 进入 messages；311 行和 1358 行承认必要 payload / anchor 缺失会导致 `LOST` 或失败。
- **影响**: phase plan 会把 EventLog append 当作恢复充分条件，但实际缺少 payload durable contract，导致 recovery、resume、replay、fetch_more、memory 和 audit 出现“有事实无内容”的不可恢复状态。
- **建议改法和验证点**: 在设计中区分 recoverable canonical payload、diagnostic-only payload、display-only payload。对恢复必要的 ref / descriptor / evidence anchor，规定 write-before-append、digest verification、retention、同事务 commit marker 或等价原子流程；canonical event 只有在引用内容 durable 后才可 accepted。明确 payload 缺失时哪些事件不得 append，哪些 Run 进入 `LOST`，哪些只降级 trace。验证点覆盖 crash-before-payload-commit、digest mismatch、artifact retention expired、fetch_more after Host restart。
- **修复风险（低/中/高）**: 高。
- **严重程度（低/中/高/严重）**: 严重。
- **是否阻塞 phase planning**: 阻塞。EventLog、ToolRuntime、TruncationManager、RunInputBuilder、Recovery 相关 phase 在修正前不能直接规划实现。

### 3-未修复-[高]-公共 API 没有显式承载 actor/source/client context，Audit 与 Outbox 只能靠 metadata 猜
- **位置**: `docs/host/design.md` 10 节 Host 公共接口，393-462 行；12 节 EventLog 事件形态，560-581 行；12.3 Contract Matrix，656-673 行；14 节 Audit，763-772 行。
- **问题类型**: 公共接口契约缺失 / 架构边界 / 审计缺口。
- **当前写法**: Host request shapes 只列出 `client_request_id`、`input`、`execution_target`、`queue_policy`、`reason` 等字段，没有稳定的 actor / principal / source / client / delivery target。EventLog 中 `actor?`、`source?` 是可选字段，但 Audit 又要求 actor / principal、source / client；673 行还禁止把 required fields 塞进无结构 metadata。
- **反例/失败场景**: Service 代表 WeChat 用户调用 `start_run`，Host 需要 append `USER_INPUT_ACCEPTED` 并在 terminal 后投递 answer。由于 request 没有显式 actor/source/delivery target，implementation agent 只能把这些放进 `metadata`、从 session slot 推断，或直接省略。之后 audit 不能回答谁提交了 prompt，outbox 不能稳定选择投递目标，`permission_denied` 错误分类也没有输入依据。
- **为什么有问题**: 认证授权可以属于上层，但 Host 作为 EventLog / audit / outbox 真源，至少必须接收由上层解析后的调用主体和来源上下文。否则 Host 公共契约与 EventLog / Audit contract 不同源，违反“required fields 不能塞进 metadata”的设计要求。
- **直接证据**: 393-462 行 request shapes 缺少 actor/source；572-573 行 EventLog 字段被标为可选；656 行 session event payload 包含 actor / reason；763-772 行 audit 必须记录 actor / principal、source / client、request id、payload ref / digest；673 行禁止 required fields 进入 metadata。
- **影响**: phase plan 会在 API、EventLog、Audit、Outbox 之间产生不一致字段设计，或通过 metadata 逃避类型边界；生产排障、合规审计和多客户端投递会缺失主链信息。
- **建议改法和验证点**: 增加显式 `HostCallContext` 或 request envelope，包含 actor/principal、source/client、client_request_id/request_id、delivery target hint、上层已验证的权限/身份声明。Host 不负责认证，但必须记录并按 policy 使用该 context。把 EventLog 中 audit 主链字段从可选改为按 event class 必需，并为匿名/系统 actor 定义显式值。验证点覆盖 WeChat/CLI/UI 三类 source、outbox target derivation、audit projection 字段完整性、metadata 不承载 required fields。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。
- **是否阻塞 phase planning**: 阻塞。公共 API、EventLog、Audit、Outbox phase 需要先收敛该契约。

### 4-未修复-[高]-`event_id` / remote event id / client idempotency key 的身份模型未拆开，重复 ingest 与 terminal 去重不可验证
- **位置**: `docs/host/design.md` 8 节多进程持久化方向，256-264 行；12 节 EventLog 排序与幂等，560-590 行；12.4 EngineEvent 映射，683-705 行；16 节远程执行不变量，856-865 行。
- **问题类型**: 契约缺失 / 并发恢复风险 / 测试缺口。
- **当前写法**: `event_id` 被定义为事件幂等键，重复 ingest 同一 `event_id` 不得 append 第二条 canonical event；远端事件携带 remote event id / remote ordering hint；Host 重新分配 `event_sequence`。但设计没有定义 host-generated event、client operation、remote EngineEvent、一个 EngineEvent 映射多个 canonical facts 时各自的 identity 与唯一约束。
- **反例/失败场景**: RemoteStub 断线重连后重放同一个 `final_answer` EngineEvent。若 Host 为每次 ingest 生成新的 `event_id`，会 append 第二条 terminal；若直接用同一个 remote event id，又无法同时表示 `RUN_SUCCEEDED` 与 `ATTEMPT_SUCCEEDED` 两个 canonical facts。类似地，`CANCEL_REQUESTED` 的 client idempotency 与 `ATTEMPT_CANCELLED` 的 EngineEvent idempotency 也不是同一层概念。
- **为什么有问题**: 多进程 + 远程执行场景必须靠唯一约束和幂等键证明“重复事件不污染 canonical EventLog”。当前文档把 `event_id`、remote event id、client_request_id / idempotency_key 的职责混在一起，implementation agent 必须自行发明事件身份模型。
- **直接证据**: 259 行把一致性依赖列为 `event_id` / `event_sequence` 去重与排序；564 行只有单个 `event_id`；586 行把 `event_id` 定义为幂等键；589 行说明远端 sequence 只做诊断；860 行远端回传 remote event id / ordering hint；701-704 行一个 Engine terminal event 映射到 Run 与 Attempt 两类 canonical facts。
- **影响**: EventLog 去重、remote replay、terminal 幂等、projection checkpoint 和 recovery scan 无法写出可证明测试；重复 terminal、重复工具事实或漏记 attempt terminal 都会成为生产级风险。
- **建议改法和验证点**: 在设计中拆出至少三类 identity：client operation idempotency key、remote event identity、canonical event identity。规定 canonical event unique key 可由 `(origin, execution_id, remote_event_id, canonical_event_type, sub_index)` 或等价结构派生；Host-generated state transition event 也要有 deterministic idempotency source。增加 event_ingest ledger 或 mapping 表，记录 remote event 到 canonical events 的映射。验证点覆盖 duplicate remote terminal、duplicate tool result、out-of-order remote events、同一 client_request_id 重试、一个 EngineEvent 生成多个 canonical events。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 高。
- **是否阻塞 phase planning**: 阻塞。EventLog、remote ingest、projection、recovery phase 在该 identity model 前不可直接实施。

### 5-未修复-[高]-远程执行只定义禁止事项，缺少协议无关的最小交付语义
- **位置**: `docs/host/design.md` 16 节 WorkerProxy / EngineWorker，849-865 行；26 节 Host Lifecycle / Recovery，1317-1325 行；26.1 dispatch record，1360-1373 行。
- **问题类型**: 契约缺失 / 并发恢复风险 / 不可直接实施。
- **当前写法**: RemoteProxy 是 transport substitution，RemoteStub 不拥有 Host 状态；RPC、ack、replay、heartbeat、version negotiation、connection keepalive 属于 Remote phase discussion。dispatch record 不是 lease，只帮助判断旧 Attempt 是否仍能被当前进程确认控制。
- **反例/失败场景**: Host dispatch 到远端后崩溃，远端仍在执行昂贵财报工具；Host 重启后因为没有可确认 dispatch record，把旧 Attempt 标 `LOST` 并创建新 Attempt。旧远端稍后回传 final_answer 或外部副作用结果。设计说迟到事件不能污染 EventLog，但没有 ack / replay / heartbeat / event delivery contract，phase plan 无法判断旧远端事件如何停止、如何补传、如何确认 cancel、如何避免重复昂贵工具调用。
- **为什么有问题**: “不定义 wire protocol”是合理的；但支持远程 Engine 并列执行至少需要协议无关的交付语义。否则每个 remote phase 都会重新决定 ack、event replay、liveness、cancel acknowledgement、version skew 和 disconnect 后 event buffering，破坏 Host-constrained 语义。
- **直接证据**: 851-854 行声明 design 定义 remote semantic contract，但 854 行把 ack、replay、heartbeat、version negotiation、connection keepalive 全部推迟到 Remote phase discussion；856-865 行只列 Host 校验和远端不得做什么；1360-1373 行 dispatch record 不提供 liveness / fencing。
- **影响**: remote phase plan 不能 handoff-ready；也会反向影响 recovery、cancel、tool side-effect idempotency、EventLog duplicate ingest 和 outbox 时序。
- **建议改法和验证点**: 在 design.md 增加 wire-agnostic remote execution minimum contract：dispatch accepted / rejected 状态、per-attempt event delivery 至少一次与去重、remote event checkpoint/ack、disconnect 后 event buffering 或明确丢弃语义、heartbeat/liveness 判定、version compatibility failure、cancel delivery ack 与 timeout、late event diagnostic policy。验证点覆盖 host crash after dispatch、remote reconnect replay、cancel during disconnect、version mismatch、heartbeat timeout。
- **修复风险（低/中/高）**: 高。
- **严重程度（低/中/高/严重）**: 高。
- **是否阻塞 phase planning**: 阻塞 remote execution phase planning；也应作为 recovery / cancel / EventLog phase 的显式依赖。

### 6-未修复-[高]-ToolRuntime 被允许远端执行，但工具事实 durable accept barrier 未定义
- **位置**: `docs/host/design.md` 16 节治理路径，826-839 行；17 节 ToolRuntime，867-901 行；17.1 重复工具调用治理，926-932 行；19 节外部等待与副作用，1046-1058 行。
- **问题类型**: 架构边界 / 数据损坏 / 并发恢复风险。
- **当前写法**: ToolRuntime 是 Host-owned，但可以随 EngineWorker 部署在远端；远端 ToolRuntime 可以执行、截断并返回结果，但不能 append EventLog。工具调用意图、policy 决策和结果进入 EventLog；外部副作用要求工具级 idempotency key。
- **反例/失败场景**: Remote ToolRuntime 执行财报读取或付费外部工具，把 tool result 立即返回给 Engine，Engine 后续 final answer 已基于该结果继续推理；Host 只是在之后通过 EngineEvent stream ingest `TOOL_RESULT_ACCEPTED`。如果远端连接丢失、事件乱序、Host 拒绝该 execution_id、或 Host 在接受 final_answer 前没 durable accept 该 tool fact，就会出现 final answer 引用未进入 EventLog 的证据。对外部写入 / 付费工具，远端崩溃在副作用已发生但 Host ledger 未接受之间，还会导致 retry 重复执行。
- **为什么有问题**: 设计目标要求 Host 是 tool governance 和 EventLog 真源，但当前路径没有说明“工具结果何时才可以被模型继续消费”和“Host 接受工具事实前，Engine 是否可以基于它产生后续语义”。仅说远端不能 append EventLog，不足以保证 LLM in the loop 被 Host 强约束。
- **直接证据**: 829-839 行是 EngineEvent stream 后置 ingest；869-890 行允许 ToolRuntime 远端执行但禁止远端 append EventLog；928-932 行要求 policy/result facts 进入 EventLog；1048-1050 行仅要求外部 job/idempotency key，未定义 Host ledger accept 与工具副作用的原子边界。
- **影响**: ToolRuntime、remote Engine、duplicate governance、external side effect、replay/recovery phase 都可能把非 durable 工具事实喂给模型，破坏财报证据链和 verified fact 边界。
- **建议改法和验证点**: 设计必须定义 tool fact durable accept barrier。可选方案包括：Host-mediated ToolExecutor，让工具结果在返回 Engine 前已被 Host durable accepted；或 remote delegated mode，但 final_answer acceptance 必须验证同一 execution 的全部 preceding tool facts、policy decisions、cursor descriptors 已按顺序 durable accepted，否则 final_answer 只能进入 diagnostic / failed path。外部副作用工具还要有 side-effect ledger 与 idempotency key 的写入顺序。验证点覆盖 tool result event lost but final_answer arrives、tool result duplicate、paid/write tool crash before EventLog accept、Host rejects stale execution_id tool result。
- **修复风险（低/中/高）**: 高。
- **严重程度（低/中/高/严重）**: 高。
- **是否阻塞 phase planning**: 阻塞 ToolRuntime 与 remote ToolRuntime phase planning；本地 ToolRuntime phase 也必须至少定义 accept barrier。

### 7-未修复-[中]-Attempt `STARTING` / `RUNNING` 与 `ATTEMPT_STARTED` 的边界不清，dispatch failure 没有状态事实
- **位置**: `docs/host/design.md` 7 节 Attempt 生命周期，177-205 行；8 节 durable queue promotion，266-285 行；8.1 状态迁移契约，293-305 行；12.3 Contract Matrix，661-662 行；26.1 dispatch record，1360-1373 行。
- **问题类型**: 状态机漏洞 / 契约缺失。
- **当前写法**: `STARTING` 表示 Host 已创建 Attempt 并准备派发；`RUNNING` 表示 EngineWorker 已开始执行。状态迁移矩阵却在同一事务内 append `ATTEMPT_STARTED`、创建 Attempt row 和 dispatch record，然后 commit 后再 dispatch EngineWorker。contract matrix 又说 `ATTEMPT_STARTED` 的状态副作用是创建 Attempt active row。
- **反例/失败场景**: SQLite 事务成功提交 `RUN_STARTED` / `ATTEMPT_STARTED` 后，RemoteProxy dispatch 失败或本地 worker 无法启动。此时 Attempt 应是 `STARTING`、`RUNNING`、`FAILED`、`LOST` 还是可 retry 的 dispatch failure？文档没有 canonical event 或状态迁移表达 `STARTING -> RUNNING`、dispatch accepted、dispatch failed。
- **为什么有问题**: phase plan 需要把 dispatch record、Attempt status、RunSnapshot current attempt 和 recovery scan 写成状态机。当前 `ATTEMPT_STARTED` 同时像“Host 创建了 Attempt”和“worker 已开始执行”，导致 cancel、recovery、remote ack 和 get_run 展示语义不一致。
- **直接证据**: 203-204 行区分 STARTING 与 RUNNING；270 行要求 `RUN_STARTED`、`ATTEMPT_STARTED`、Attempt row、dispatch record 同事务；282-283 行 commit 后才 dispatch EngineWorker；661 行把 `ATTEMPT_STARTED` 定义为创建 active row。
- **影响**: dispatcher phase 和 recovery phase 会自行选择不同语义，导致 dispatch failure、startup timeout、cancel-before-worker-started 的行为不可 review。
- **建议改法和验证点**: 选择并固化一种模型：要么删除 `STARTING`，把 `ATTEMPT_STARTED` 定义为 Host dispatch-committed active attempt，并用 dispatch diagnostic 表达 worker 未确认；要么新增 `ATTEMPT_DISPATCHED` / `ATTEMPT_RUNNING` / `ATTEMPT_DISPATCH_FAILED` 等事实，明确 dispatch ack、startup timeout 和 retry/recovery 路径。验证点覆盖 dispatch crash after commit、dispatch reject、cancel during STARTING、recovery scan sees STARTING attempt。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。
- **是否阻塞 phase planning**: 阻塞 dispatcher / Attempt lifecycle / recovery phase planning；不阻塞纯文档术语整理。

### 8-未修复-[中]-Outbox marker 被设计为 optional，但用户可见投递恢复语义需要一个强真源
- **位置**: `docs/host/design.md` 9 节 Durable Store，315-328 行；13 节 Observer / Sink / Projection，713-725 行；15 节 Outbox，811-816 行；26.1 已接受 Prompt 的恢复语义，1348-1349 行。
- **问题类型**: 契约缺失 / 不可恢复 / 用户可见行为风险。
- **当前写法**: durable store 只有 optional outbox marker；EventLog transaction 可 optionally record projection wakeup / outbox marker。Outbox 必须有幂等投递键、状态、重试次数、last error 和 delivery target，但未定义 outbox intent 是否由 `RUN_SUCCEEDED` 扫描派生，还是必须在 terminal transaction 中创建 durable outbox row。
- **反例/失败场景**: Host 提交 `RUN_SUCCEEDED` 后崩溃，尚未创建 outbox marker；用户可见语义要求 answer 之后投递给 UI / client。如果实现只依赖 optional marker 或内存 notification，WeChat / Web 用户可能永远收不到已提交答案；如果实现靠扫描 `RUN_SUCCEEDED`，delivery target 又必须从 accepted request/source 中可恢复，但当前 API 缺少显式 source / target。
- **为什么有问题**: Outbox 不是事实真源，但投递 intent 必须有可恢复真源。optional marker 可以是性能优化，不能是唯一触发条件。否则 recovery 文档中的“已提交 prompt 不丢，之后仍能收到 answer”不能验证。
- **直接证据**: 327 行 `optional outbox marker`；722 行 `optionally record projection wakeup / outbox marker`；813-816 行要求 terminal 后 outbox delivery 与幂等投递状态；1348-1349 行把 final answer accepted 后 outbox delivery 写成恢复用户目标的一部分。
- **影响**: outbox phase plan 无法定义 crash recovery、idempotent delivery 和 replay 后再投递；多客户端 / 多进程下会出现 terminal 已成功但用户无可恢复投递路径。
- **建议改法和验证点**: 明确 outbox 真源策略：要么 `RUN_SUCCEEDED` event 本身是 outbox intent，outbox worker 必须按 `event_sequence` checkpoint 扫描 terminal events；要么 terminal transaction 必须原子创建 outbox row，optional 只能指 wakeup marker。定义 delivery target 来源、per-channel idempotency key、replay/result version 下是否再次投递。验证点覆盖 crash after RUN_SUCCEEDED before outbox worker、duplicate worker delivery、projection lag、replay after delivered。
- **修复风险（低/中/高）**: 中。
- **严重程度（低/中/高/严重）**: 中。
- **是否阻塞 phase planning**: 阻塞 outbox / terminal delivery phase planning；同时依赖公共 API actor/source 修复。

## Reviewed Target And Scope

- **Review gate name**: draft design review for Host。
- **Reviewed target**: `docs/host/design.md`。
- **Allowed context read**: `dayu/README.md` 术语与架构边界；`docs/host/implementation-control.md` 工作流与 phase planning 约束。
- **Explicitly excluded source**: 未读取、未引用 `docs/host/discussion-note.md`。
- **Objective**: 判断 `docs/host/design.md` 是否足以作为下一阶段 phase planning 的 Host 架构真源，尤其是 production-grade 买方财报分析 Agent、host-constrained LLM in the loop、单机多客户端 / 多进程、本地 / 远程 Engine 并列执行。

## Assumptions Tested

- **Host 是治理真源**: 大方向成立，但 ToolRuntime 远端执行与工具事实 durable accept barrier 未闭合，导致模型可能消费未进入 EventLog 的工具事实。
- **EventLog 可作为恢复真源**: 当前只对 SQLite EventLog + 状态索引定义原子性；对外移 payload、cursor descriptor、evidence anchor ref 没有同源 durable contract，假设不成立。
- **Run terminal 语义稳定**: 不成立。`FAILED` / `SUCCEEDED` 同时被定义为终态，又被 retry/replay 转回 `RUNNING`。
- **单机多进程可由 SQLite + CAS 支撑**: 基本方向成立，但 event identity、dispatch startup state、outbox intent 真源还不足以形成可测计划。
- **RemoteProxy 是 transport substitution**: 边界方向成立，但缺少协议无关的 ack / replay / heartbeat / version / cancel delivery 最小语义，不能支撑 remote phase plan。
- **Observer / Sink 不影响 EventLog**: 方向成立；但 outbox delivery intent 不能只依赖 optional marker 或内存 wakeup。
- **Memory / final_answer 边界**: final answer 不自动成为 verified fact 的原则清晰；主要风险来自 replay/versioning 与工具事实缺失，而不是 memory 术语本身。
- **Implementation-control 要求先细化设计再写 phase plan**: 这些 findings 属于 blocking 或 phase-blocking 架构问题，应先修 `design.md` 或在对应 phase discussion 中收敛为明确设计决策。

## Open Questions

- retry/replay 的产品语义是“修复同一用户可见 Run 的结果”，还是“创建一个关联的新 Run”？这个选择会决定终态、outbox、Session timeline 与 active slot 设计。
- 远端 ToolRuntime 是否允许直接执行外部副作用工具，还是第一版只允许 read-only / Host-mediated 工具？这会决定 side-effect ledger 与 durable accept barrier 的复杂度。
- 大型工具 payload 的第一版持久层是 SQLite blob、workspace artifact file、领域仓储 ref，还是分层组合？无论选择哪种，都需要明确 digest、retention 与 EventLog append 顺序。

## Residual Risks And Suggested Tracking

- Context governance 中 LLM summary compaction 的模型调用治理、成本、失败和 provenance 还需要对应 phase 继续压测；本次没有列为 blocker，因为 24 节已明确 compact summary 不能替代 evidence anchor，但实现计划必须补测试。
- WAITING Run 是否长期占用同一 Session active slot 是明确设计选择，但对长事务工具会牺牲同 Session 后续任务吞吐；建议在 wait record phase 作为 product / policy tradeoff 追踪。
- `Context Governance`、`Conversation Memory` 与 `Evidence / Retrieval` 的 budgets 和默认参数仍留给 phase 决策；只要 phase plan 不把这些默认值伪装成架构真源，可作为后续 phase open question 管理。

## Final Readiness Verdict

**fail**。

`docs/host/design.md` 已经形成了清晰的 Host 架构方向和大量正确边界，但目前还不能直接驱动下一阶段 implementation-ready phase planning。最主要的阻塞点不是文档细节，而是状态机、EventLog payload durability、公共 API audit context、remote delivery、ToolRuntime durable accept barrier 与 outbox intent 的几个核心不变量尚未闭合。

建议先按上述 findings 修正 `design.md`，或在进入每个受影响 phase 的 plan gate 前，通过 phase discussion 把相应架构决策写回 `design.md`。在这些 blocker 未收敛前，只适合把当前文档作为 draft design discussion 输入，不适合作为代码生成级 phase plan 的唯一真源。
