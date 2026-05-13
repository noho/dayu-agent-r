# Host 实施总控

## 文档职责

本文档是 Host 设计与实施的总控文档，负责记录实施工作流、phase 编排、phase 进入 / 退出条件、交付物和验证要求。

本文档不承载新的架构决策，不替代设计文档，不作为实现细节说明书。

## 设计目标

Host 设计与实施必须始终服务于以下目标：

- 生产级买方财报分析 Agent。
- 范式是“宿主强约束下的 LLM in the loop”。
- 支持单机多客户端 / 多进程。
- 支持本地 Engine 和远程 Engine 并列执行。

任何 phase plan、implementation slice、review finding 裁决和 scope 调整，都必须显式对齐这些目标。若某项设计或实现选择削弱这些目标，应停下来修正 `design.md` 后再继续。

## 真源层级

Host 后续计划与实施遵循以下真源层级：

```text
dayu/README.md
  -> 项目级术语真源
  -> 约束跨层、跨 phase 的稳定术语含义

design.md
  -> Host 架构真源
  -> 定义架构边界、状态机、公共接口、EventLog、恢复、并发、远程执行和关键治理路径

implementation-control.md
  -> 实施编排文档
  -> 只记录 phases、依赖、进入 / 退出条件、交付物和验证要求
```

术语真源是 `dayu/README.md` 的术语表。phase discussion、phase plan、implementation、review、fix 与 re-review
必须使用该术语表中的定义；不得由 planning / implementation agent 自行重解释 `Session`、`Run`、`Attempt`、
`EventLog`、`USER_INPUT_ACCEPTED`、`EngineEvent stream`、`Host event stream`、`TruncationManager`、
`scope_token` 等术语。若发现术语缺失、冲突或不足以指导实施，应先和用户讨论，并同步更新 `dayu/README.md`
及对应设计文档，再继续推进。

本文档不得引入新的架构边界、状态机、公共接口或事件语义。若实施编排过程中发现需要新的架构决策，应先和用户讨论并同步到 `design.md`，再更新本文档的 phase 编排。

## 工作流

Host 实施采用以下工作流：

```text
draft design checkpoint
  -> update implementation-control.md phases
  -> select one phase
  -> discuss and refine the corresponding design.md section with the user
  -> update design.md if the phase discussion changes architecture
  -> generate handoff implementation-ready plan for that phase
  -> review plan
  -> user confirmation
  -> implement phase
  -> verify
  -> update related docs
```

每个 phase 单独生成 handoff implementation-ready plan。phase plan 必须基于：

- `design.md`
- 本文档中对应 phase 的范围、依赖和退出条件

phase plan 不得从旧设计稿、旧代码路径或非真源文档推导架构边界。

每个 phase 的第一步必须是和用户讨论并细化 `design.md` 中的对应章节。该讨论属于 `$gateflow` 的 feature
discussion / requirement clarification 阶段，必须在进入 plan gate 前完成。

phase discussion 至少需要确认：

- phase 目标与 success signal；
- 本 phase 是否服务于总控设计目标；
- 对应 `design.md` 章节是否足够具体；
- 本 phase 的 scope boundary、non-goals 与 stop conditions；
- 是否存在会阻塞 handoff implementation-ready plan 的架构、状态机、公共接口、schema、持久化或测试问题。

如果 discussion 发现 `design.md` 对应章节不足以支撑直接写 plan，应先更新 `design.md`，再进入该 phase 的 plan。

## 强制约束

- Host 后续每个复杂 work unit、phase plan、public contract change、schema / storage change、state-machine change
  和 architecture-sensitive task 都必须遵循 `$gateflow` 工作流。
- `docs/host/design.md` 只写终态架构语义，不写 review 过程、用户确认过程、历史讨论、迁移痕迹、上一版对比或临时 open question。流程约束、裁决记录和追踪项分别写入本文档或 `docs/reviews/`。
- phase plan、implementation 或 fix 过程中如果需要修改 Engine 代码，必须立即停下来向用户确认。未经用户明确确认，
  不得把 Engine 代码修改夹带进 Host phase。
- phase plan、implementation 或 fix 不得让 Engine 理解 Host 状态、memory、guidance、steer、fetch_more 或 tool governance。
- phase plan、implementation 或 fix 不得把 projection / timeline / audit / trace / outbox 当事实真源。
- phase plan、implementation 或 fix 不得把旧 Attempt resume / takeover 作为实现方案。
- phase plan、implementation 或 fix 不得让 RemoteStub / EngineWorker append EventLog、关闭 Attempt、更新 Run。
- phase plan、implementation 或 fix 不得引入重 lease / fencing 系统替代 admission + SQLite transaction + CAS。
- phase plan、implementation 或 fix 不得让远端 sequence、内存 notification 或 projection checkpoint 替代 Host 分配的全局 `event_sequence`。
- phase plan、implementation 或 fix 不得把 assistant final answer 自动升级为 verified fact。
- phase plan、implementation 或 fix 不得让 `fetch_more` 走 Host / Engine 特化分支。
- phase plan、implementation 或 fix 不得把语义级重复工具调用治理放进 Engine；它属于 Host / ToolRuntime。
- phase plan、implementation 或 fix 不得让 sink 失败影响 EventLog append 或 Run terminal。
- phase 讨论、plan、implementation、review、fix 或 re-review 过程中出现 material open question 时，必须停下来和用户讨论；
  不得让 planning / implementation agent 自行选择会影响架构、公共接口、状态机、schema、持久化、并发、恢复、测试期望或用户可见行为的方案。
- 每个 phase 产生的潜在影响、未覆盖项、deferred risk、后续 phase 依赖和明确不做项，必须回写到本文档的追踪区；
  不得只保留在对话、临时 artifact 或 phase plan 中。

## Open Questions 与风险追踪

总控文档负责追踪跨 phase 的 open questions、潜在影响和未覆盖项。

追踪规则：

- `blocking` open question 必须在对应 phase 的 plan review 通过前解决，并写回 `design.md` 或 phase plan。
- `non-blocking` open question 必须写明 working assumption、风险、触发回看条件和归属 phase。
- implementation 中发现的新 open question，如果会影响设计边界或用户可见行为，必须停下交给用户讨论。
- residual risk 和 uncovered area 必须分类为：当前 phase 修复、后续 phase 覆盖、后续 work unit、用户明确接受、或需要新跟踪项。
- 任何 deferred 项都必须有 owner / destination；没有 destination 时不能关闭对应 phase。

### 追踪区

#### Engine Context Compaction Event 语义前置

背景决议：

- 当前 Engine 只在 provider 返回 `context_length_exceeded` 后 emit `context_compaction_requested`；这属于 reactive fallback，不是生产级 proactive context governance。
- 当前 `ContextCompactionRequestedData.budget_state` 在该路径中填 `ContextBudgetSnapshot(0, 0, 0)`，只是占位诊断载体，不代表真实 prompt / completion / total token budget。
- Host 生产级治理应由 Context Governance 基于 provider-aware budget policy 主动判断 soft / hard threshold；provider overflow 只能作为最后防线。
- 如果不先澄清 Engine event contract，后续 Host implementation agent 可能误把 `0/0/0` 当真实预算，或误以为 Engine 已负责 context budget threshold。

前置实施步骤：

- 在进入 Host Context Governance / compact phase plan 前，必须先开一个 Engine contract cleanup work unit，且因涉及 Engine 代码，必须先停下来向用户确认。
- 该 Engine work unit 的目标不是把 budget governance 放进 Engine，而是把 Engine 事件语义改到不会误导 Host：
  - 明确 `context_compaction_requested` 的来源是 provider overflow reactive fallback。
  - 将 `budget_state` 改成 optional / unknown 语义，或引入明确的 unknown marker；不得继续让 `0/0/0` 看起来像真实 token snapshot。
  - 保留 `usage_reported`、`iteration_completed`、provider request id 和 overflow reason，供 Host Context Governance 诊断与追踪。
  - README / docs/engine/design.md 必须同步说明：Engine 不做 proactive threshold compaction，不做 compact / retry，不计算 Host budget；Host 必须用自己的 estimator / tokenizer / policy 记录 before / after budget。
- Host Context Governance phase 的 plan 必须显式依赖这个 Engine cleanup 完成，或在 plan 中写明临时兼容假设并禁止消费 `0/0/0` 作为真实预算。

追踪项：

- Engine cleanup 完成后，更新 `dayu/engine/README.md`、`docs/engine/design.md`、`dayu/README.md` 中的相关术语与边界。
- Host `design.md` 必须明确：proactive threshold compaction 属于 Host Context Governance；Engine provider overflow event 只是 reactive fallback。
- Host 测试设计必须覆盖：Engine overflow event 中预算 unknown 时，Host 仍使用自身 budget estimator 进行 compact 诊断与恢复决策。

#### External Job Cancel Adapter 能力追踪

背景决议：

- `WAITING` Run 被 `cancel_run` 命中时，Host 第一版负责 durable 状态收口：append `CANCEL_REQUESTED`，标记 active wait record 为 cancelled，append `RUN_CANCELLED`，并释放 Session active slot。
- 外部 job 的实际取消属于对应 wait adapter / tool adapter 的 best-effort 能力，不作为 Host 第一版保证。

追踪项：

- Tool Awaiting / Wait Adapter phase 必须定义 wait record 被 Host 标记 cancelled 后，adapter 如何观察该状态。
- 后续 adapter 可以按能力实现外部 job cancel / revoke / abandon，但必须明确这是 best-effort，不得影响 Host EventLog 和 Run 终态的正确性。
- 如果外部 job 在 Host 已取消 Run 后仍回调或被 poll 到结果，Host 必须拒绝其结果进入 canonical EventLog，只能记录 diagnostic / tool trace。
- 对具有外部副作用、付费调用或长耗时资源占用的工具，后续工具 schema / policy phase 必须明确是否提供 job id、cancel handle、idempotency key 和资源清理策略。
- 第一版测试至少覆盖：`WAITING -> CANCELLED` 后迟到 `resolve_wait` / callback 不污染 canonical EventLog。

#### Tool Trace / Provider Request 排错追踪

背景核实：

- OpenAI API reference 的 Debugging requests 说明 `x-request-id` 是每次 API request 的唯一标识，并建议生产环境记录 request id，便于和 OpenAI support 排障。
- 同一官方章节说明调用方可显式提供 `X-Client-Request-Id`；当 timeout / network issue 导致拿不到 `X-Request-Id` response header 时，可用该值让 OpenAI support 查询是否收到请求以及收到时间。
- 当前 Engine 已把 provider response header 的 `x-request-id` 提取为 `provider_request_id`，并在 Runner / Engine 错误与终态链路中显式透传：`RunnerHTTPErrorData`、`RunnerProtocolErrorData`、`RunnerDoneData`、`ProviderProtocolErrorData`、`RunFailedData`、`EngineRunOutcomeFailed` 等字段已覆盖；相关测试也覆盖了 HTTP error、protocol error、iteration completed、run failed 的透传。

追踪项：

- 不修改 `design.md`；这不是 Host 架构边界新决策，而是 tool trace / analyze 工具排障能力需求。
- 后续实现 tool trace 与 `utils/analyze_tool_trace.py` 时，必须把 `provider_request_id` 纳入热 JSON projection 与冷 JSONL，便于按 OpenAI `x-request-id` 排查 provider 错误、超时、协议错误和重试耗尽。
- 后续若 Host / Service 为 OpenAI-compatible request 注入 `X-Client-Request-Id`，tool trace 也必须记录对应 client-side request id，并与 `provider_request_id`、`run_id`、`attempt_id`、`execution_id`、`event_sequence` 一起可查询。
- 对 timeout / network error 且 `provider_request_id=None` 的场景，analyze 工具应提示优先查看 client-side request id / `X-Client-Request-Id`、网络错误类型、attempt 次数和 retry history。

#### SQLite 多进程写入正确性验证

结论：

- 第一版继续使用 SQLite durable store 作为单机多进程 Host 真源。
- 不提前引入服务化数据库、消息队列、分库或重型写入架构。
- 正确性依赖 WAL、明确 busy timeout、短事务、显式重试、唯一约束和 CAS-style state transition。
- 该项重点是验证写竞争不会破坏状态机和 EventLog 真源；性能容量只有在压测或生产观察证明明显后才升级为容量治理问题。

追踪项：

- Host Storage / Durable Store phase 必须明确 SQLite 连接配置、WAL、busy timeout、transaction 边界、retry 策略和错误分类。
- 多进程测试必须覆盖同 Session 并发 `start_run`、重复 `client_request_id`、active slot admission、queue promotion、cancel / terminal race、EventLog `event_sequence` 单调性。
- phase plan 不得把 SQLite 写竞争作为引入服务化 DB 或消息队列的默认理由。

#### Remote 物理执行 exactly-once 非目标

结论：

- 第一版不保证 exactly-once 远程物理执行。
- Host 只保证 canonical EventLog、Run / Attempt 状态和 Tool fact accept 的治理正确性。
- 远端 worker 在 Host 崩溃、断连或超时后可能继续执行旧 attempt；Host 必须通过 `execution_id` 和 active Attempt 校验拒绝迟到 terminal / tool fact。
- 外部副作用必须依赖工具级 idempotency key、tool policy、adapter best-effort cancel 和诊断追踪降低风险；不能依赖 Host lease / fencing 兜底。

追踪项：

- RemoteProxy / RemoteStub phase 必须测试旧 `execution_id` 的迟到 Engine event、迟到 tool result、迟到 terminal 只能进入 diagnostic / trace，不能污染 canonical EventLog。
- 具有外部副作用的工具必须在 ToolRuntime / Tool Schema phase 明确 idempotency key、side-effect policy 和可取消能力。
- Remote phase 不得引入远端 takeover attempt、远端 append EventLog 或远端更新 Run 状态。

#### Session Purge / Archive 追踪

结论：

- 第一版提供 `purge_session`，用于清理已关闭且所有 Run 已终态的 Session 的 Host 本地数据。
- `purge_session` 是 destructive purge，不是 close、cancel、archive、memory forget 或 UI hide。
- `purge_session` 必须保留最小 purge tombstone / audit record；purge 后不再支持恢复、resume、retry、replay、timeline 补读或 final answer 找回。
- `archive_session` 不进入第一版。archive 的语义是把冷 Session 移到 archive storage，保留可审计、可查询、可按需恢复的只读档案；archive 不删除事实。

追踪项：

- Public API / Storage phase 必须细化 `purge_session` 的 request、幂等、前置条件、删除范围、tombstone 存储位置和错误形状。
- Storage phase 必须定义共享 cold artifact 的引用计数或 ref 检查，防止 purge 删除仍被其它 Session 引用的 artifact。
- 后续单独追踪 `archive_session` 的需求和边界；不得用 `purge_session` 模拟 archive。

#### Host 跨层测试策略追踪

结论：

- Host 测试不能只依赖端到端路径。
- 每个 phase 的 handoff implementation-ready plan 必须包含与该 phase 边界匹配的验证策略。
- 跨层集成测试用于验证路径组合，不替代状态机、事务、adapter、projection、recovery 的分层测试。

追踪项：

- State machine phase 必须提供 Run / Attempt / Session 状态迁移单元测试。
- Storage phase 必须提供 SQLite transaction、CAS、唯一约束、多进程竞争和 crash recovery 测试。
- Proxy / Remote phase 必须提供 WorkerProxy fake integration、迟到事件、断连、重发和 accept ack 测试。
- ToolRuntime phase 必须提供外部业务 `ToolBundle` 输入、attempt-local effective `ToolBundle`、`fetch_more` 注入、tool fact accept barrier、truncate / fetch_more、重复工具调用治理和 side-effect policy 测试。
- Projection / Sink phase 必须提供 EventLog replay、checkpoint、Outbox、audit、usage、tool trace 的幂等追平测试。
- Recovery phase 必须提供 Host restart、positive orphan proof、LOST / RECOVERABLE_LOST、prompt 已 accepted 但 answer 未返回的恢复测试。

#### UI / Service Outbox 去重边界追踪

结论：

- 在线 / 已 attach 客户端通过 Host event stream、Session timeline、RunSnapshot 或 read model 读取 final answer。
- Outbox 只提供离线 / 外部渠道的 terminal 增量，不提供完整聊天记录或中间过程回放。
- 在线阅读路径和 Outbox 离线投递路径必须共享同一个 terminal identity。
- per-client 的 seen cursor、delivery ledger、read ack 和 channel 投递状态属于 UI / Service / channel adapter，不属于 Host truth。

追踪项：

- Projection / Sink phase 必须保证 outbox item 携带稳定 `terminal_event_id`、`event_sequence`、`run_id`、`result_digest` 和幂等 item key。
- Service / UI phase 必须定义 `last_seen_terminal_event_sequence` 或 `seen_terminal_event_ids` 的持久化位置和更新时机。
- Service / UI phase 必须覆盖：客户端在线已展示 final answer 后离线重连，从 Outbox 读取增量时不会重复显示同一 terminal answer。
- UI 显示聊天记录必须按 terminal identity upsert / dedupe，不得按 final answer 文本内容去重。

## 当前状态

当前阶段为 draft design v2 设计收口。Host 代码实施尚未开始；`docs/host/design.md` 已是 Host 架构真源，
`dayu/README.md` 是项目级术语真源，本文档负责后续 phase 编排、进入 / 退出条件、交付物、风险和未覆盖项追踪。

进入 phase 编排前，需要完成针对 `docs/host/design.md` 的最终一致性检查。进入任何 phase plan 前，仍必须先和用户讨论并细化对应 `docs/host/design.md` 章节。
