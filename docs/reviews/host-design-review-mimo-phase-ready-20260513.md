# Host Design Review — Phase-Ready Adversarial Review

- **reviewer**: mimo
- **date**: 2026-05-13
- **target**: `docs/host/design.md` (current working tree)
- **cross-ref**: `dayu/README.md`
- **scope**: adversarial review for phase design / phase plan readiness

---

## Readiness Verdict

**ready with phase-local followups**

design.md 已经覆盖了 Host 架构的核心治理边界、状态机、EventLog 语义、远程执行不变量、ToolRuntime 治理、等待/恢复/取消/steer/retry/replay 路径和 memory 投影。架构骨架足以拆分 phase design 和 phase plan。

有两个需要在 phase design 前明确的架构决策（ToolRuntime 部署模型 F-01、Policy snapshot 传递策略 F-C3），其余 findings 均可在对应 phase 内细化。

过度耦合维度：未发现循环依赖或 God object。主要耦合风险是 attempt snapshot 聚合（F-C1）、RunInputBuilder 输入源过多（F-C2）和 policy ownership 歧义（F-C3），均为 medium severity，不阻塞总体推进。

**no blocking findings**

---

## Findings

### F-01 — ToolRuntime 部署模型歧义

- **severity**: high
- **location**: design.md §17, L1052-1065, L1074, L1089
- **问题**: §17 写道 "它可以随 EngineWorker 部署在本地或远端执行环境，但治理配置和真源来自 Host attempt snapshot"。但文档没有明确 ToolRuntime 的进程归属：
  - LocalProxy 路径：ToolRuntime 是否运行在 Host 进程内、通过函数调用与 EngineWorker 交互？
  - RemoteProxy 路径：ToolRuntime 是否运行在远端 EngineWorker 进程内、通过 attempt snapshot 获得治理配置？
  - 如果远端 ToolRuntime 需要把 tool fact candidate 提交给 Host accept barrier，这个提交走的是什么通道？是 EngineEvent stream 的一部分，还是独立的 tool fact submit 协议？
- **为什么影响 phase design**: ToolRuntime 的进程归属直接决定：(1) Tool fact accept barrier 的实现路径——函数调用 vs RPC；(2) 远端截断 cursor descriptor 的回传方式；(3) 语义级重复调用治理的内存索引归属（Host 进程 vs 远端进程）。phase design 无法在不明确这一点的情况下安全拆分 ToolRuntime phase 和 RemoteProxy phase。
- **最小修正建议**: 在 §17 补一段明确的部署模型声明：LocalProxy 路径下 ToolRuntime 与 Host 同进程、通过函数调用实现 accept barrier；RemoteProxy 路径下 ToolRuntime 随 EngineWorker 部署在远端、tool fact candidate 通过 EngineEvent stream 或等价 RPC 回传 Host。不需要定义 wire protocol，但必须明确进程归属和通信方向。

### F-02 — HostCallContext 结构不完整

- **severity**: high
- **location**: design.md §10, L449-457
- **问题**: §10 列出了 `HostCallContext` 的语义字段（actor、source、request_id、client_request_id、delivery_target_hint、authorization_claims），但缺少类型约束。`actor`、`source`、`request_id` 标记为 required（无 `?`），但 `delivery_target_hint` 和 `authorization_claims` 有 `?`。问题是：哪些字段是 truly required vs optional？`actor` 是 string enum 还是 free-form？`authorization_claims` 的 schema 是什么？
- **为什么影响 phase design**: HostCallContext 是所有 mutating API 的公共 envelope。如果 phase design 阶段不同 agent 对 required fields 理解不一致，会导致 idempotency key 计算、audit 字段填充和 error handling 出现分歧。
- **最小修正建议**: 在 §10 补一个 typed schema fragment，明确每个字段的 required/optional、类型（string / enum / structured）和默认行为（如 anonymous actor 的处理）。不需要完整 JSON schema，但需要足以消除 required vs optional 的歧义。

### F-03 — RunInputBuilder memory snapshot 来源未指定

- **severity**: high
- **location**: design.md §22, L1369, §23, L1463-1467
- **问题**: §22 列出 RunInputBuilder 的输入包含 "session memory snapshot"，§23 说 "memory snapshot 是 read model，可重建、可修复，不是事实真源"。但文档没有指明 memory snapshot 的来源：它是从 memory projection 表读取的持久化快照，还是从 EventLog canonical facts 实时构造的？如果是持久化快照，谁负责写入（memory projection sink）？如果是实时构造，为什么 §23 要求 "memory snapshot 与 projection checkpoint 必须同事务提交"？
- **为什么影响 phase design**: RunInputBuilder phase 和 Memory Projection phase 的拆分依赖这个答案。如果 memory snapshot 是持久化的，RunInputBuilder 只需读取；如果是实时构造的，RunInputBuilder 需要包含完整的 memory 构造逻辑。两种路径的实现复杂度和 phase 划分完全不同。
- **最小修正建议**: 在 §23 补一句明确声明：memory snapshot 由 memory projection sink 持久化到 memory snapshot 表，RunInputBuilder 从该表读取。或者：memory snapshot 由 RunInputBuilder 在 dispatch 前从 EventLog 实时构造，projection checkpoint 记录构造时的 cursor。二选一，明确即可。

### F-04 — 远端 Tool Fact Accept Barrier 协议未定义

- **severity**: high
- **location**: design.md §17, L1076-1089, §16, L1014
- **问题**: §17 定义了 tool fact accept barrier 的语义路径，§16 说 "`tool fact accepted ack` 是 ToolRuntime / EngineWorker 执行语义的一部分，不是 wire protocol 细节"。但对 RemoteProxy 路径，这个 ack 的传输机制完全没有定义：ToolRuntime 如何把 tool fact candidate 提交给 Host？Host 如何把 accepted ack 返回给远端 ToolRuntime？这个过程是同步阻塞还是异步？超时怎么处理？
- **为什么影响 phase design**: RemoteProxy phase 的设计无法在不明确 accept barrier 传输协议的情况下开始。同步阻塞意味着远端 ToolRuntime 需要等待 Host 事务提交；异步意味着需要额外的状态机来跟踪 pending tool fact submissions。
- **最小修正建议**: 在 §17 或 §16 补一段远端 accept barrier 的语义约束，至少明确：(1) 同步 vs 异步语义；(2) 超时处理（ToolRuntime 等待 ack 的超时后怎么办）；(3) ack 失败时 Engine 是否可以继续。不需要定义 wire frame，但需要足以指导 RemoteProxy phase 的语义边界。

### F-05 — TruncationManager cursor descriptor 生命周期不完整

- **severity**: medium
- **location**: design.md §18, L1170-1198
- **问题**: §18 定义了 cursor / scope_token 的语义和 durable descriptor 的要求，但没有明确：(1) durable descriptor 何时创建——是截断发生时由 TruncationManager 创建，还是 Host accept tool fact 时创建？(2) descriptor 的 TTL 和清理策略——是跟随 Run lifetime、Session lifetime、还是独立 TTL？(3) 多次 `fetch_more` 后 cursor 是否更新（offset 递增），还是每次 `fetch_more` 返回一个新的 cursor？
- **为什么影响 phase design**: TruncationManager phase 需要明确 descriptor 的写入时机和生命周期，否则实现 agent 会在 "TruncationManager 自己持久化 descriptor" vs "Host accept 时持久化 descriptor" 之间猜测。
- **最小修正建议**: 在 §18 补一段 cursor descriptor 生命周期：(1) 截断发生时 TruncationManager 生成 descriptor metadata，随 tool fact candidate 一起提交给 Host；(2) Host accept tool fact 时持久化 descriptor；(3) descriptor 生命周期绑定到 Run；(4) 每次 `fetch_more` 返回新 cursor（offset 递增）或复用同一 cursor（取决于工具语义）。

### F-06 — HostPolicyProviderSet 实例化与默认值缺失

- **severity**: medium
- **location**: design.md §9.1, L408-418
- **问题**: §9.1 列出了 HostPolicyProviderSet 包含的 7 类 policy provider，但没有说明：(1) 这些 provider 是接口 / protocol 还是具体类？(2) 第一版的默认实现是什么？(3) 如果调用方不传入某个 provider，Host 是用默认实现还是报错？
- **为什么影响 phase design**: 如果 phase design 不知道默认 policy 行为，每个 phase agent 可能对 "如果不配置 retry policy 会怎样" 有不同理解。
- **最小修正建议**: 补一句："第一版每个 policy provider 有内置默认实现；调用方可通过 Host handle 构造参数覆盖。" 或明确哪些 provider 是 required vs optional。

### F-07 — Snapshot 类型定义缺失

- **severity**: medium
- **location**: design.md §10, L581-586
- **问题**: §10 定义了 `SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`HostEventStream` 的最小语义字段，但这些是架构级描述，不是类型定义。phase design 阶段需要知道这些 snapshot 是否是 frozen dataclass、是否有 `__eq__` 语义、是否携带完整 state 还是只携带 summary。
- **为什么影响 phase design**: 如果不同 phase agent 对 snapshot 的可变性、相等性语义理解不一致，会导致接口契约不兼容。
- **最小修正建议**: 补一句："Snapshot 是 frozen dataclass，只读，携带当前状态的完整投影。具体字段定义在对应 phase design 中细化。"

### F-08 — cancel_run on WAITING 的中间状态路径未在状态迁移表中体现

- **severity**: medium
- **location**: design.md §8.1, L319, §21, L1346-1347
- **问题**: §8.1 状态迁移表中 `cancel_run on waiting` 的目标状态写的是 `Run CANCELLED`，但 §21 的语义描述明确写道 "Host 直接收口为 CANCELLED：append CANCEL_REQUESTED，标记 active wait record cancelled，append RUN_CANCELLED"。状态迁移表没有体现中间的 wait record cancelled 事实。虽然这不改变最终状态，但表的简洁性可能让实现 agent 忽略 wait record 收口这一步。
- **为什么影响 phase design**: 实现 agent 如果只看状态迁移表、不读 §21，可能遗漏 wait record cancelled canonical fact，导致 wait adapter 仍然尝试 resolve 一个已取消的 wait。
- **最小修正建议**: 在状态迁移表的 `cancel_run on waiting` 行的 "必须追加的 canonical facts" 列中补充 `wait record cancelled fact`（与 §21 对齐）。

### F-09 — Outbox delivery target 来源的边界条件

- **severity**: medium
- **location**: design.md §15, L961
- **问题**: §15 说 "delivery target 必须来自 HostCallContext、Session binding 或 request 明显字段的稳定来源"。但如果一个 Run 是通过 queue promotion 启动的（不是用户直接调用 start_run），此时 HostCallContext 来自 queued Run 的 accepted 时刻，而 delivery target 可能在 queued 期间已经变化（例如用户切换了客户端）。文档没有说明这种情况下 delivery target 的解析策略。
- **为什么影响 phase design**: Outbox phase 需要明确：delivery target 是在 Run accepted 时冻结，还是在 terminal 时重新解析。两种策略的实现完全不同。
- **最小修正建议**: 补一句："delivery target 在 Run accepted 时从 HostCallContext 冻结到 Run record；terminal 时不再重新解析。" 或 "terminal 时从 Session binding 重新读取最新 delivery target。"

### F-10 — steer 路径中旧 Attempt 收口为 STEERED 的条件

- **severity**: low
- **location**: design.md §11, L631
- **问题**: §11 写道 "current Attempt closes as STEERED or terminal race result"。但没有明确什么条件下 Attempt 关闭为 `STEERED` vs `CANCELLED`。如果旧 Attempt 正在执行工具调用，Host 发出 cancel signal 后，Attempt 可能先产出 `run_cancelled`（Engine 侧取消），而不是 `steered`。此时 Run 的状态应该是什么？
- **为什么影响 phase design**: 这是 steer 和 cancel 竞态的边界情况，phase design 需要明确 `STEERED` 和 `CANCELLED` 的优先级。
- **最小修正建议**: 补一句："旧 Attempt 收口为 `STEERED` 还是 `CANCELLED` 取决于哪个 terminal event 先被 Host accept。`STEER_REQUESTED` 已提交时，后续 `run_cancelled` 映射为 `ATTEMPT_STEERED`；`CANCEL_REQUESTED` 先提交时，steer 降级为无效。"

### F-11 — dayu/README.md 与 design.md 术语对齐

- **severity**: low
- **location**: dayu/README.md §术语约定 vs design.md 全文
- **问题**: 两个文件的术语基本一致，但有两处微小差异：
  1. README 用 "canonical event" 描述可恢复、可审计的事件；design.md 用 `event_class=canonical_fact`。两者语义一致，但用词不同（"canonical event" vs "canonical_fact"）。建议统一。
  2. README 的 `ToolRuntime` 定义比 design.md 更简略，缺少 "tool fact accept barrier" 和 "语义级重复工具调用治理" 的详细说明。这不是冲突，但可能导致实现 agent 只读 README 时对 ToolRuntime 职责理解不足。
- **为什么影响 phase design**: 术语不统一可能导致 phase plan 中不同 agent 使用不同术语指代同一概念。
- **最小修正建议**: (1) 在 README 中明确 "canonical event = event_class 为 canonical_fact 的 EventLog event"；(2) 在 README 的 ToolRuntime 定义中补充 "tool fact accept barrier" 和 "语义级重复工具调用治理" 的简要说明。

### F-12 — RECOVERING 退出到 LOST 的 policy 上限未量化

- **severity**: low
- **location**: design.md §8.1, L329-331
- **问题**: §8.1 写道 "recovery、retry、replay 和 context compaction retry 都必须有 Host policy 上限"。但没有给出默认值或量级参考。phase design agent 不知道 "上限" 是 1 次、3 次还是 10 次。
- **为什么影响 phase design**: 这是 policy 细节，不阻塞架构拆分，但可能影响 phase plan 的测试设计。
- **最小修正建议**: 补一句："默认次数与退避参数属于 Host policy config；第一版建议默认值为 recovery 3 次、retry 3 次、replay 1 次、context compaction 2 次。" 或明确 "具体默认值在对应 phase design 中定义"。

### F-13 — SQLite schema 未定义

- **severity**: low
- **location**: design.md §9, L347-378
- **问题**: §9 列出了 durable store 需要承载的表（Session、Run、Attempt、EventLog 等），但没有给出任何 schema fragment。phase design 需要知道表之间的外键关系、索引策略和 CAS 条件更新的实现方式。
- **为什么影响 phase design**: SQLite schema 是 storage phase 的核心产出。当前描述足以理解需要哪些表，但不足以指导表结构设计。这是正常的 phase-local detail，不阻塞总体推进。
- **最小修正建议**: 无需在 design.md 中补充。在 storage phase design 中定义即可。

---

## 过度耦合分析

本节独立审查 design.md 中模块间的耦合关系，重点识别：职责互相知道太多、不必要耦合、循环依赖风险、配置或 policy ownership 混乱。

### 耦合关系总览

```text
Host handle (composition root)
  ├── EventLog appender / reader
  ├── Run admission & queue promotion
  ├── Attempt dispatch (WorkerProxy factory)
  ├── ToolRuntime factory
  ├── RunInputBuilder
  ├── Observer / Sink runner
  ├── Outbox dispatcher
  ├── HostPolicyProviderSet
  └── clock / id generator

数据流：
  RunInputBuilder ──reads──> EventLog canonical facts
  RunInputBuilder ──reads──> memory snapshot
  RunInputBuilder ──reads──> compact artifacts
  RunInputBuilder ──reads──> source Run tool facts (retry/replay)
  RunInputBuilder ──reads──> tool schemas
  RunInputBuilder ──reads──> policy config
  RunInputBuilder ──produces──> AgentRunRequest.messages

  ToolRuntime factory ──reads──> tool definitions
  ToolRuntime factory ──produces──> ToolExecutor

  Attempt dispatch ──bundles──> RunInputBuilder output + ToolExecutor + Host state
  Attempt dispatch ──produces──> attempt snapshot

  attempt snapshot ──flows to──> Proxy → EngineWorker → Engine

  EngineEvent stream ──flows to──> Host event ingest
  Host event ingest ──writes──> EventLog
  EventLog ──consumed by──> Sinks (audit, usage, tool trace, memory, outbox, fanout)
```

### F-C1 — Attempt Snapshot 过度聚合

- **severity**: medium
- **location**: design.md §16, L1040-1046
- **问题**: attempt snapshot 将至少五类不同来源的数据打包在一起：(1) `session_id`/`run_id`/`attempt_id`/`execution_id`（Host 治理标识）；(2) complete `AgentRunRequest`（RunInputBuilder 产出）；(3) cancellation source / token binding（Host cancel 治理）；(4) ToolExecutor capability snapshot（ToolRuntime 产出）；(5) policy snapshot ids / refs（HostPolicyProviderSet）。attempt snapshot 成为耦合中心：Attempt Dispatch 模块需要理解所有这些来源才能构造它，而 Proxy / EngineWorker / ToolRuntime 都需要理解它的结构才能消费它。
- **为什么影响 phase design**: Attempt Dispatch phase、ToolRuntime phase 和 RemoteProxy phase 都需要对 attempt snapshot 的结构达成一致。如果每个 phase agent 独立定义 snapshot 的内部结构，会导致接口不兼容。
- **最小修正建议**: 在 design.md 中明确 attempt snapshot 的分层结构：标识层（id fields）、执行层（AgentRunRequest）、治理层（cancellation + policy refs）、工具层（ToolExecutor）。不需要定义完整类型，但需要明确哪些层由哪个模块负责构造。

### F-C2 — RunInputBuilder 输入源过多导致脆弱性

- **severity**: medium
- **location**: design.md §22, L1364-1376
- **问题**: RunInputBuilder 有 8 类输入来源：EventLog canonical facts、memory snapshot、compact artifacts、source Run tool facts、caller system messages、tool schemas、runner config、policy config。每类输入的格式、语义和提供者都不同。如果 memory snapshot 的格式变化，或 compact artifact 的 schema 变化，或 tool schemas 的投影方式变化，RunInputBuilder 都需要同步修改。它隐式依赖了太多下游模块的输出格式。
- **为什么影响 phase design**: RunInputBuilder phase 无法独立于 Memory phase、Context Governance phase、ToolRuntime phase 和 Storage phase 进行设计。任何上游模块的接口变化都会波及 RunInputBuilder。
- **最小修正建议**: 这是 RunInputBuilder 作为 "唯一运行态入口" 的固有复杂度，不是设计缺陷。但建议在 phase plan 中明确：RunInputBuilder phase 必须在所有上游模块的接口稳定后才能冻结设计。或者在 design.md 中为每类输入定义最小 interface contract（例如 memory snapshot 必须提供哪些字段），减少隐式耦合。

### F-C3 — Policy Snapshot 与 HostPolicyProviderSet 的 ownership 歧义

- **severity**: medium
- **location**: design.md §9.1, L408-418, §16, L1046, §17, L1052
- **问题**: §9.1 定义 HostPolicyProviderSet 包含 7 类 policy provider，是 Host handle 的依赖。§16 说 attempt snapshot 携带 "policy snapshot ids / refs required to explain execution"。§17 说 ToolRuntime 的 "治理配置和真源来自 Host attempt snapshot"。这产生了 ownership 歧义：tool governance policy 的定义在 HostPolicyProviderSet，但执行时的 policy snapshot 在 attempt snapshot 中。ToolRuntime 如何从 policy snapshot id 解析到实际的 policy 规则？是通过 HostPolicyProviderSet 按 id 查询，还是 attempt snapshot 直接嵌入完整的 policy 规则？
- **为什么影响 phase design**: 如果 policy snapshot 只是 id/ref，ToolRuntime 需要某种方式解析它——这意味着 ToolRuntime 要么依赖 HostPolicyProviderSet（增加耦合），要么 attempt snapshot 嵌入完整 policy（增大 snapshot 体积）。两种策略影响 ToolRuntime phase 和 HostPolicy phase 的拆分。
- **最小修正建议**: 在 §16 或 §17 补一句明确 policy snapshot 的传递策略："attempt snapshot 嵌入 ToolRuntime 所需的完整 policy 规则，不只传 id；ToolRuntime 不依赖 HostPolicyProviderSet。" 或 "attempt snapshot 只传 policy id，ToolRuntime 通过 attempt context 回查 Host policy。"

### F-C4 — EngineEvent → Host Canonical Event 映射的隐式耦合

- **severity**: low
- **location**: design.md §12.4, L807-838
- **问题**: §12.4 定义了 EngineEvent 到 Host canonical event 的默认映射。这个映射是 Host event ingest 的核心逻辑，但它隐式依赖了 EngineEvent 的语义定义。如果 Engine 侧新增一种 EngineEvent 类型，或修改现有 EngineEvent 的语义，Host event ingest 的映射逻辑必须同步更新。映射表本身不是循环依赖，但它是跨层的隐式契约。
- **为什么影响 phase design**: Engine phase 和 Host phase 无法完全独立推进。§12.4 的映射表已经是规范性边界，实现必须转成 typed code 和 tests。建议在 phase plan 中明确：EngineEvent 定义变更必须同步更新 §12.4 映射表。
- **最小修正建议**: 无需修改 design.md。在 phase plan 中将 §12.4 映射表作为 Engine phase 和 Host phase 的共享契约，变更时必须同步。

### F-C5 — ToolRuntime 多职责边界

- **severity**: low
- **location**: design.md §17, L1100-1109
- **问题**: ToolRuntime 负责 8 项职责：工具注册装配、权限/policy、并发/timeout/orphan cleanup、tool awaiting、truncation/fetch_more、语义级重复调用治理、tool trace 诊断、工具级 idempotency key 执行约束。这 8 项职责中，truncation/fetch_more（通过 TruncationManager）和语义级重复调用治理（通过 duplicate index）各自有独立的子模块。ToolRuntime 作为统一入口是合理的（它实现了 ToolExecutor protocol），但 8 项职责的内部拆分需要在 phase design 中明确。
- **为什么影响 phase design**: 如果 ToolRuntime phase 不拆分子模块，可能导致一个巨大的 ToolRuntime 类。建议在 phase design 中将 ToolRuntime 内部拆分为：tool dispatch、policy enforcement、truncation management、duplicate governance、awaiting management 等子模块。
- **最小修正建议**: 无需修改 design.md。§17 已经列出了职责清单，phase design 负责内部拆分。

### F-C6 — EventLog 作为多模块读取源的辐射耦合

- **severity**: low
- **location**: design.md §12, L646-661, §22, L1369, §23, L1463, §13, L842-898
- **问题**: EventLog 被至少 6 个模块读取：RunInputBuilder（构建 messages）、Memory projection（构建 memory snapshot）、Audit projection（生成 audit trail）、Usage projection、Tool trace projection、Recovery scan（启动时扫描非终态 Run）。每个模块对 EventLog 的读取模式不同：RunInputBuilder 按 run_id 过滤 canonical facts；Memory projection 按 session_id 过滤；Recovery scan 全表扫描非终态 Run。EventLog 作为 append-only 真源，被多模块读取是架构设计的本意，但读取模式的多样性意味着 EventLog schema 变更会影响所有消费者。
- **为什么影响 phase design**: 这是 EventLog 作为 single source of truth 的固有辐射性，不是设计缺陷。但 phase plan 应明确：EventLog schema 变更是跨 cutting 的变更，需要所有消费模块同步更新。
- **最小修正建议**: 无需修改 design.md。在 phase plan 中将 EventLog schema 定义为 shared contract，变更时必须通知所有消费模块。

### F-C7 — cancel / steer / resume 共享 Attempt 生命周期但治理路径不同

- **severity**: low
- **location**: design.md §7, §8.1, §11, §20, §21
- **问题**: cancel、steer、resume 三个操作都涉及 Attempt 生命周期管理（关闭旧 Attempt、创建新 Attempt），但它们的治理路径完全不同：cancel 通过 cancellation token 传播；steer 通过 cancel + 新 Attempt；resume 通过 wait resolution + 新 Attempt。三者共享 Attempt 状态机（STARTING → RUNNING → terminal），但触发新 Attempt 创建的条件和前置状态不同。这种 "共享状态机、不同治理路径" 的模式可能导致 Attempt 状态机的 transition handler 变得复杂。
- **为什么影响 phase design**: Attempt 状态机的 phase design 需要同时考虑三个治理路径的竞态。建议在 phase design 中将 Attempt transition handler 按治理路径拆分，而不是一个巨大的 if-else。
- **最小修正建议**: 无需修改 design.md。§8.1 的状态迁移表已经覆盖了各路径的竞态规则。phase design 负责实现层面的拆分。

### 耦合分析结论

design.md 的模块耦合总体合理。没有发现循环依赖、God object 或职责泄漏。主要耦合风险集中在：

1. **attempt snapshot 聚合**（F-C1）：5 类不同来源的数据打包在一起，是耦合中心。
2. **RunInputBuilder 输入源过多**（F-C2）：8 类输入导致隐式依赖链长。
3. **Policy ownership 歧义**（F-C3）：policy 定义在 HostPolicyProviderSet，执行时 snapshot 在 attempt snapshot，解析路径不明确。

这三个问题中，F-C3 需要在 phase design 前明确（policy snapshot 的传递策略），F-C1 和 F-C2 是 phase plan 的 sequencing 约束（相关 phase 必须协调接口）。其余 findings 是 phase-local 的实现决策，不阻塞总体推进。

---

## 术语一致性结论

`dayu/README.md` 与 `docs/host/design.md` 的术语总体一致。核心一等对象（Session、Run、Attempt、EventLog）、状态集合、stream 术语、WorkerProxy/EngineWorker/RemoteStub 边界、ToolExecutor 协议均对齐。F-11 指出的 canonical event vs canonical_fact 用词差异不影响语义理解，建议统一但不阻塞。
