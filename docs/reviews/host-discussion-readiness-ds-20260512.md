# Host Discussion Readiness Review — 2026-05-12 (DS)

## 审查元信息

- **Gate**: pre-design readiness review
- **审查目标**: `docs/host/discussion-note.md`
- **审查问题**: discussion-note 是否足够 ready 用来生成新的 `docs/host/design.md`
- **辅助参考**: `docs/host/implementation-control.md`（仅审查其 phase 工作流是否足以防偏）
- **审查者**: AgentDS（adversarial review，独立于 AgentMiMo 结论）
- **约束**: `docs/host/design.md` 是将被删除的旧文件，不作为本次 review 的设计真源。仅以 discussion-note.md 自身的一致性、闭合性和完备性判断 readiness。
- **不做什么**: 不修改任何文件（仅产出本 artifact），不启动 Gateflow，不写 implementation plan

---

## 总评

discussion-note.md 在概念建模、状态机语义、admission 不变量、EventLog Observer/Sink 边界、远程执行拓扑、conversation memory 第一性原理等方面表现出较高的讨论成熟度。核心对象（Session/Run/Attempt/EventLog）的边界清晰，Run 和 Attempt 的状态机定义完整，EventLog canonical fact 分类标准明确。

然而，存在 **1 个 blocking finding**：cancel 升级路径（watchdog）的 6 个开放项明确标记为"需要继续讨论"，导致 `CANCELLING` 状态缺少闭合的退出条件。此外有 5 个 high-severity finding 涉及存储方案、多进程协调、ToolRuntime 边界、resume_policy 机制和 RunInputBuilder 规格——这些不是实现细节，而是 design.md 规范化时必须回答的架构问题。

**结论**: 在收束 blocking finding 之前，不建议进入 design.md 生成。High finding 建议在 discussion-note 中给出方向性决议，但可在 design.md 生成过程中由人工逐项裁决。

---

## Controller 状态标注（2026-05-12）

本 pre-design readiness review 已归档。其 findings 已被新版 `docs/host/design.md`、`docs/host/discussion-note.md`、
`dayu/README.md` 与 `docs/host/implementation-control.md` 吸收或明确后移；不再作为进入 draft design commit 的 open blocker。
下方原始严重度、blocking/high 标记和修正建议保留为 review-time 记录；后续 plan / implementation 以本节状态为准。

| Finding | 状态 | 归属 / 说明 |
| --- | --- | --- |
| 1 Cancel watchdog 开放项 | 已吸收 | `design.md` 已补 cancel / terminal / suspend 竞态、queued cancel、cancel timeout -> LOST / RECOVERING。 |
| 2 持久化 / durable transaction 悬空 | 已吸收 | `design.md` 已固定 SQLite durable store、transaction、CAS、global `event_sequence`。 |
| 3 多进程协调机制缺失 | 已吸收 | `design.md` 已补 admission、queue promotion、dispatch record、CAS 与不引入重 lease / fencing。 |
| 4 ToolRuntime 边界模糊 | 已吸收 | `design.md` / `dayu/README.md` 已定义 Host-owned ToolRuntime、ToolExecutor 边界、远端执行限制。 |
| 5 wait resume_policy 机制缺失 | 已吸收 | `design.md` 已补 `resolve_wait` pipeline 与 poll / callback / manual adapter 语义。 |
| 6 RunInputBuilder 位置与算法未定 | 已吸收 | `design.md` 已定义 Host 内部组件、输入源、`USER_INPUT_ACCEPTED` 唯一入口和 messages 顺序。 |
| 7 Session 状态机缺失 | 已吸收 | `design.md` 已定义 `OPEN` / `CLOSED` 与 Session slot 语义。 |
| 8 Observer / Sink 通知机制未指定 | 已吸收到架构级 | `design.md` 已补 notification 只是 wakeup，正确性来自 EventLog replay + checkpoint。 |
| 9 `execution_target` 未定义 | 已吸收到策略边界 | `design.md` 已用 WorkerProxy / worker selection policy 表达执行目标；具体枚举归 worker phase。 |
| 10 cancel vs suspend 分布式竞态覆盖不全 | 已吸收 | `design.md` 已补 Host ingest 顺序与 terminal / cancel / suspend 竞态规则。 |
| 11 `start_run` 与 stream 工作流断链 | 已吸收 | `design.md` 已补 `RunSnapshot` cursor 与 `stream_run_events` 补读语义。 |
| 12 pinned_state 更新机制缺失 | 后移 | Memory/context phase 细化；draft design 已保留 pinned state / patch / compact 边界。 |
| 13 Truncation cursor 生命周期延迟 | 已吸收到架构级 | `design.md` 已补 cursor / `scope_token` durable descriptor、TTL / limit 等 policy 留到 ToolRuntime phase。 |
| 14 未覆盖设计领域 | 已吸收 / 后移 | 由 `design.md` non-goals、extension points 和 `implementation-control.md` 追踪规则承接。 |
| IC-1 Phase 编排未定义 | 后续工作 | 当前 draft design checkpoint 前可接受；下一步由 `design.md` 生成 phase 编排。 |
| IC-2 Phase discussion 检查清单增强 | 已吸收 | `implementation-control.md` 已补 phase discussion、术语真源、open question 和 tracking 规则。 |

## Finding 1 [BLOCKING] — Cancel 升级路径（watchdog）6 个开放项全部未收束

**严重程度**: BLOCKING（阻塞 design.md 生成）

**位置**: `discussion-note.md` L710-L716，"Cancel 讨论入口" 末尾

**当前写法**:
```
取消治理需要继续讨论：

- QUEUED 且尚未创建 attempt 的 run 是否直接 CANCELLED。
- RUNNING 进入 CANCELLING 后 watchdog 的 timeout 边界。
- timeout 后升级为 LOST、强制终止执行环境、后台 job reconcile 或其它结构化终态的条件。
- RemoteProxy / RemoteStub 取消控制消息需要携带哪些 id，才能避免误伤新的 attempt。
- 工具等待、SSE、后台 job 在取消路径中如何暴露可观测事实。
- 取消超时、强制终止、资源收口失败应写入哪些 canonical EventLog facts。
```

**为什么有问题**:

这 6 项不是 implementation detail，而是 cancel 状态机完整性的必要条件：

1. **L594 vs L711 自相矛盾**: L594 已明确说 "queued run 被 cancel 时，Host 直接把 Run 收口为 CANCELLED，不创建 Attempt"，但 L711 又将同一问题列为开放项。若 L594 已是决议，L711 不应再列；若仍有疑虑，L594 就不是可靠决议。
2. **`CANCELLING` 无退出条件**: watchdog timeout 边界直接决定 `CANCELLING` 何时可以迁移到 `CANCELLED` vs `LOST`。没有 timeout 边界，`CANCELLING` 是一个没有退出条件的半状态——Run 可以永远卡在 `CANCELLING`。
3. **Attempt 状态机被反向影响**: "强制终止执行环境" 的语义需要 Attempt 状态机是否有 `FORCE_KILLED` 或等价终态？当前 Attempt 状态集合中没有对应状态。
4. **远程取消正确性前提缺失**: RemoteProxy 取消控制消息携带的 id 集合是远程执行拓扑中 cancel 正确性的前提——如果携带错误的 attempt_id，可能误伤新 attempt。这是分布式 cancel 的基本安全约束。
5. **可观测性契约空白**: "工具等待、SSE、后台 job 在取消路径中如何暴露可观测事实" 直接影响 EventLog canonical fact taxonomy——是否需要新的 fact type（如 `CANCEL_WATCHDOG_EXPIRED`、`FORCE_TERMINATE_ATTEMPT`）？
6. **LOST 的进入条件不完整**: L595 说 "在未引入 watchdog 强化治理前，cancel 请求发出后如果 active Attempt 超时仍无法确认，Run / Attempt 进入 LOST"，但"超时"的时长和判定机制正是 watchdog 要定义的。

**影响**: design.md 作者在写 cancel 状态机时，要么自行填补这 6 项决策（超出 discussion-note 授权），要么把 cancel 状态机写成不完整规格（留下实现阶段的歧义）。无论哪种，都会削弱 design.md 作为 "规范化 Host 架构真源" 的权威性。

**建议改法**:

1. 消除 L594 与 L711 的矛盾：若 `QUEUED -> CANCELLED` 已是决议，从开放列表中移除该项。
2. 对 watchdog timeout 边界给出方向性决议（不要求精确到秒，但要求给出数量级和升级条件，例如 "30s 内未收到 Engine 响应则升级为 LOST"）。
3. 确认 CANCELLING 的退出条件：至少明确正常路径（Engine 响应 run_cancelled → CANCELLED）和超时路径（watchdog 触发 → LOST）。
4. 明确 cancel 控制消息的最小 id 集合：至少包含 `run_id` + `attempt_id` + `execution_id`，并说明拒绝规则。
5. 对后续 3 项（可观测事实、强制终止、EventLog facts）给出方向性决议或明确延迟到哪个 phase 决定。

**是否阻塞 design.md 生成**: **是**。Cancel 状态机不完整，`CANCELLING` 缺少闭合的退出条件。

---

## Finding 2 [HIGH] — 持久化/存储方案未承诺，"durable transaction" 语义悬空

**严重程度**: HIGH（borderline blocking，存储方案会反向约束多个子系统的设计）

**位置**: 全文散布，"durable transaction" 出现在 L61, L63, L66, L359, L360，但从未定义

**当前写法**:
```
durable transaction: create Run / Attempt / initial EventLog fact
```

仅 L388 在 Observer/Sink 性能边界处暗示了 SQLite：
```
SQLite EventLog 加 projection checkpoint 表，再配合本地后台 worker / 任务循环，
应足以表达可靠追平语义。
```

**为什么有问题**:

"durable transaction" 在文档中被当作已经成立的基础能力反复引用，但以下关键维度完全未讨论：

1. **存储介质未决议**: L388 的 SQLite 提法出现在 Observer/Sink 性能边界讨论中，是作为 "不需要重型消息系统" 的论据出现的，不是作为存储方案决议。全文没有一处明确说 "第一版存储介质选 SQLite"。
2. **事务边界未定义**: "durable transaction" 的范围是什么？单个 EventLog append？还是 EventLog append + Run 状态更新 + Attempt 状态更新的联合事务？admission 不变量（L263-L296）中描述的 "Host 可以把最早可执行的 QUEUED Run 迁移为 RUNNING，并创建 Attempt" 需要原子地完成多个状态的迁移——事务边界在哪里？
3. **多进程并发原语缺失**: 多进程是硬需求（L17），但文档没有讨论多进程下 "durable transaction" 依赖什么并发原语。SQLite WAL? 文件锁? 独立 lock manager? 不同方案对 admission 延迟、crash recovery 和 stream fanout 的影响完全不同。
4. **跨平台风险未识别**: 单机多进程在 macOS/Linux 下的文件锁行为不同（尤其是 NFS/home 目录场景），如果 discussion 阶段不识别这个风险，design.md 可能做出跨平台有问题的假设。

**影响**: 存储方案会反向约束 admission 不变量、crash recovery 语义、并发模型和 stream fanout 实现。design.md 作者将被迫自行选择存储方案——这是一个架构级决策。

**建议改法**:

discussion-note 不需要写出完整 schema，但需要至少承诺：
1. 第一版存储介质选型（建议 SQLite，基于 L388 的已有暗示，将其从 "性能建议" 提升为 "方案决议"）。
2. "durable transaction" 的最小语义定义：原子性边界（单表? 多表联合事务?）、隔离级别期望、崩溃后保证（已提交不丢失? 未提交自动回滚?）。
3. 多进程并发写入的协调策略方向（WAL + busy timeout? 独立 lock file?）。

**是否阻塞 design.md 生成**: **不阻塞**，但 borderline。design.md 作者将被迫自行决定存储方案，这是一个影响多子系统的基础决策。

---

## Finding 3 [HIGH] — 多进程并发协调机制完全未讨论

**严重程度**: HIGH

**位置**: `discussion-note.md` L17（声明多进程需求），L263-L296（admission 不变量描述语义规则但未讨论实现机制）

**当前写法**:

L17 声明需求：
```
支持单机多客户端 / 多进程并发
```

L263-L275 定义 admission 语义规则（同一 Session 最多一个 active Run、QUEUED 语义、崩溃恢复行为），但没有讨论**如何**在多进程下强制执行这些规则。

**为什么有问题**:

discussion-note 在 admission 不变量中定义了清晰的语义规则（这很好），但完全缺失以下实现维度的讨论：

1. **Active run slot 的跨进程仲裁**: "同一个 Session 同时最多一个 active Run" 这条规则在单进程下是内存判断，在多进程下需要跨进程协调。谁来仲裁？怎么防止两个进程同时把各自的 QUEUED run 提升为 RUNNING？
2. **Crash recovery 的 stale owner 检测**: L282 说 "RUNNING / CANCELLING 的 active Attempt 在崩溃恢复时不能假装成功；必须进入 LOST 或由后续明确 reconcile 规则收口"。但进程崩溃后，另一个进程如何知道前一个进程的 Attempt 已经 stale？需要 heartbeat? lease? 超时检测？
3. **Cancel 的跨进程传播**: 进程 A 调用 `cancel_run`，但 active Attempt 的 EngineWorker 在进程 B 中。cancel 信号如何跨进程到达？文档仅在远程执行拓扑中讨论了 RemoteProxy 的 cancel 控制通道（L701），但未讨论本地多进程场景下的 cancel 传播。
4. **EventLog append 的跨进程顺序**: 多进程并发 append EventLog 时，event sequence 如何保证跨进程一致？SQLite 的行级锁? 独立的 sequence allocator?

**影响**: design.md 作者需要在没有讨论指引的情况下设计整个多进程协调机制。如果设计出错（例如用简单的 file lock 导致性能瓶颈，或者漏掉 stale owner 检测导致双写），会影响系统正确性。

**建议改法**:

1. 明确多进程协调的基础机制方向：基于 SQLite WAL + 行级锁? 基于独立 lock file + 文件系统原语? 基于 `dayu.runtime` 的 Lane 原语?
2. 讨论 active run slot 的跨进程仲裁策略（例如 "通过 durable store 中的 session 级 fencing token 原子 CAS"）。
3. 补充 crash recovery 中 stale owner 的检测机制方向（heartbeat 表? lease 过期?）。
4. 补充本地多进程场景下 cancel 的传播机制（共享 durable store 中的 cancel flag? 进程间信号?）。

**是否阻塞 design.md 生成**: **不阻塞**，但 design.md 需要在 admission 和并发章节做出机制性决策，这些决策最好在 discussion 阶段有方向性共识。

---

## Finding 4 [HIGH] — ToolRuntime 组件边界未定义，与 Host 关系模糊

**严重程度**: HIGH（影响 TruncationManager、fetch_more、guidance、tool awaiting 等多个子系统的归属）

**位置**: `discussion-note.md` 全文，"Host / ToolRuntime" 作为复合主语出现至少 15 次

**当前写法**:
```
Host / ToolRuntime 需要内置 TruncationManager         (L477)
Host / ToolRuntime registers built-in @tool("fetch_more", ...)  (L504)
Host / ToolRuntime 根据治理策略、工具结果形态...        (L565)
```

**为什么有问题**:

"Host / ToolRuntime" 作为一个复合主语反复出现，但 ToolRuntime 的边界从未被定义。关键问题：

1. **ToolRuntime 是什么**: Host 的子模块？独立于 Host 的层？跨 Host 和 EngineWorker 的分布式组件？文档没有回答。
2. **TruncationManager 的进程归属**: L477-L491 描述的执行路径是 `ToolExecutor executes ToolCallable -> TruncationManager applies ToolTruncateSpec`。ToolExecutor 在哪一侧？如果在 EngineWorker 中（本地或远程），TruncationManager 必须在同进程才能 intercept 工具执行。但如果 TruncationManager 在 EngineWorker 侧，它的 config（ToolTruncateSpec）如何从 Host 侧安全下发？如果 EngineWorker 是远程的，TruncationManager 的 cursor 状态存储在哪里？
3. **fetch_more 的跨进程数据流**: fetch_more 是一个 "普通 @tool"，它的 callable 需要访问 TruncationManager 的 cursor。如果 EngineWorker 在远程，cursor 在本地 Host，fetch_more callable 如何跨进程访问 cursor？是通过 RemoteProxy 回传 cursor 到 EngineWorker，还是 fetch_more 的执行本身就在 Host 侧？
4. **Run-time guidance 的决策权归属**: L565-L584 说 "Host / ToolRuntime evaluates guidance policy" 并 "optional guidance message is appended to current run input sequence"。如果 ToolRuntime 在 EngineWorker 侧，它不应做 Host-governed 决策。如果 ToolRuntime 在 Host 侧，它如何 intercept 远端 EngineWorker 中的工具执行结果来触发 guidance evaluation？

**影响**: ToolRuntime 边界决定了 TruncationManager、fetch_more、guidance 的进程归属、数据流和安全边界。这些都在第一版范围内，边界不清会导致 design.md 在这些子系统上出现进程归属矛盾。

**建议改法**:

discussion-note 增加一节 "ToolRuntime 边界定义"，至少明确：
1. ToolRuntime 是 Host 的子模块还是独立组件。建议：ToolRuntime 是 Host 的内部子模块，运行在 Host 进程内；EngineWorker 侧的 ToolExecutor 是 Engine 的执行器，不承载治理逻辑。
2. TruncationManager 运行在哪里。建议：在 Host 进程内的 ToolRuntime 中；EngineWorker 的 ToolExecutor 将未经截断的原始结果回传给 Host，由 TruncationManager 在 Host 侧截断后再交给 Engine 作为 tool result。
3. 但这与 L488-L491 的描述（ToolExecutor -> TruncationManager）矛盾——那里 TruncationManager 在 ToolExecutor 返回结果之前介入。需要明确澄清。
4. fetch_more 的执行流程在远程场景下的完整路径。

**是否阻塞 design.md 生成**: **不阻塞**，但 design.md 需要在 ToolRuntime 相关章节前先收束边界定义；否则子系统设计会出现进程归属矛盾。

---

## Finding 5 [HIGH] — wait record 的 resume_policy (callback|poll|manual) 中 callback 和 poll 解析机制缺失

**严重程度**: HIGH（影响 tool awaiting 子系统的闭合性）

**位置**: `discussion-note.md` L540-L551，"wait record 最小语义"

**当前写法**:
```
resume_policy: callback | poll | manual
```

文档只描述了 "wait condition satisfied" 后的 resume 路径（L664-L669），但没有描述：
- **poll 模式**: Host 如何知道外部 job 已完成？轮询间隔? 超时? 失败重试策略?
- **callback 模式**: callback 的入口是什么？HTTP endpoint? 内部消息? 谁来注册 callback?
- **manual 模式**: 谁触发 resume？用户在 UI 上点击 "继续"？

**为什么有问题**:

三种 resume_policy 对应完全不同的架构路径：

1. **poll** 需要 Host 内部有一个定时器/scheduler 组件。这引入了新的内部组件（Host Scheduler）和新的资源类型（scheduled task）。discussion-note 完全没有提及 Host scheduler 的存在。
2. **callback** 需要 Host 暴露一个外部可调用的 resume 入口。这实质上是一个 public API（即使名字不叫 `resume_run`），需要做认证、幂等和 rate limit。discussion-note 的 public interface（L80-L91）中没有这个入口。
3. **manual** 需要 UI/Service 层触发 resume。当前 public interface 中的 `submit_followup` 是否是 manual resume 的入口？文档没有连接这两个概念。

此外，文档 L86-L91 中 `resume_run` 刻意不出现在 public interface，但 callback 和 manual 模式实质上需要一个对上层/外部可见的 resume 动作。

**影响**: design.md 作者在定义 Host public interface 和内部组件时，无法确定是否需要 Scheduler 组件、callback endpoint、或 `resume_run` 接口。

**建议改法**:

1. 明确第一版支持的 resume_policy（建议第一版只支持一种，推荐 poll，因为它不需要扩展 public interface 或引入外部依赖）。
2. 如果支持 poll，补充 Host 内部 scheduler/poller 的最小设计方向。
3. 如果支持 callback，补充 callback 入口的安全边界。
4. 如果支持 manual，明确与 `submit_followup` 的关系。

**是否阻塞 design.md 生成**: **不阻塞**，但 design.md 的 public interface 和 tool awaiting 章节会在此处有空白。

---

## Finding 6 [HIGH] — RunInputBuilder 的架构位置未定，messages 重建算法未形式化

**严重程度**: HIGH（resume/steer 两条恢复路径都依赖 messages 重建的正确性）

**位置**: `discussion-note.md` L780-L797，"RunInputBuilder 路径"

**当前写法**:
```
RunInputBuilder 需要：
- 把 pinned state 与 stable facts 放在明确的 Host Memory system block 中。
- 对 recent raw turns 做下限保底，而不是固定上限。
- 对 older raw turns、episode summaries、tool facts、evidence anchors 做预算选择。
- 不创建独立 RunInputBuildTrace 子系统。
```

**为什么有问题**:

1. **架构归属模糊**: L786 的路径 `current USER_INPUT_ACCEPTED + session memory snapshot + caller system messages -> RunInputBuilder -> AgentRunRequest.messages` 暗示 RunInputBuilder 在 Host 内，但 "caller system messages" 来自 Service 层。RunInputBuilder 是 Host 组件还是 Service 组件？它的输入中，哪些来自 Host（EventLog, memory snapshot），哪些来自 Service（system messages），哪些来自 Engine contract（AgentRunRequest schema）？
2. **Messages 重建算法未形式化**: resume（L664-L669）和 steer（L325-L336）都依赖 "从 canonical EventLog facts 重建完整 AgentRunRequest.messages"。这是整个系统中最关键的算法之一——如果重建后的 messages 与原始 run 的 messages 语义不等价，模型行为会出现不可预测的偏差。文档只给了 prose 描述，没有明确：
   - 哪些 canonical fact types 按什么顺序进入 messages。
   - 重建的 messages 与原始 messages 的等价性条件是什么（严格逐消息相等? 还是语义等价?）。
   - Tool result 在重建时以什么形式出现（完整 result? 摘要? ref?）。
3. **与 context governance 的关系**: L816-L822 说 context governance 包含 "RunInputBuilder 的输入层需要可测试的预算分配"，但 context governance 的归属（Host 无疑，但具体是 Host 的哪个组件？）需要和 RunInputBuilder 的归属一起明确。

**影响**: Messages 重建是 resume 和 steer 两条路径的共同依赖。如果规格不够精确，这两条路径的正确性都无法保证。

**建议改法**:

1. 明确 RunInputBuilder 是 Host 内部组件，消费 EventLog canonical facts + memory snapshot，产出 `AgentRunRequest.messages`。Service 层提供 caller system messages 作为输入参数。
2. 给出 messages 重建的输入源清单和拼接顺序（不需要伪代码，但需要事实类型的 ordered list）。
3. 明确哪些 fact types 进入 messages 的哪个 role（system/user/assistant/tool）。

**是否阻塞 design.md 生成**: **不阻塞**，但 design.md 的 RunInputBuilder 和 context governance 章节需要更精确的规格。

---

## Finding 7 [MEDIUM] — Session 状态机缺失

**严重程度**: MEDIUM

**位置**: `discussion-note.md`，全文有 Session 生命周期讨论但无 Session 状态集合定义

**当前写法**:

discussion-note 定义了 Session slot 语义（L96-L122）、Session 概念边界（L160），以及 `SESSION_CREATED` / `SESSION_CLOSED` 作为 canonical events（L425-L426）。但没有定义 Session 本身的状态集合（如 ACTIVE/CLOSED）和状态迁移规则。

**为什么有问题**:

Session 状态影响 admission 行为：closed session 能否读取？能否创建新 run？这些语义在 discussion-note 中是隐式的。此外，`close_session` 在 public interface 中（L84）但 close 后的语义（只读? 不可见? 可重新 open?）未定义。

**影响**: design.md 作者需要从 discussion-note 的 prose 描述中推导 Session 状态机。

**建议改法**:

discussion-note 增加最小 Session 状态集合（至少 ACTIVE/CLOSED），并说明：
- ACTIVE: 可创建新 Run，可接受 steer/queue。
- CLOSED: 终态，只读，不接新写入。

**是否阻塞 design.md 生成**: 不阻塞。

---

## Finding 8 [MEDIUM] — Observer/Sink 通知机制未指定

**严重程度**: MEDIUM

**位置**: `discussion-note.md` L362-L363，"EventLog Observer / Sink 讨论入口"

**当前写法**:
```
committed event notification
  -> Observer / Sink dispatch
```

L388 补充：
```
SQLite EventLog 加 projection checkpoint 表，再配合本地后台 worker / 任务循环，
应足以表达可靠追平语义。
```

**为什么有问题**:

"committed event notification" 的具体机制未定义：
1. 后台 worker 如何被唤醒？轮询 EventLog 表的新行? 通过某种通知机制（如 SQLite update hook）?
2. 如果使用轮询，轮询间隔和延迟对 stream fanout 的影响？
3. "任务循环"是 Host 进程内的 asyncio loop，还是独立的后台进程/线程？

**影响**: design.md 的 Observer/Sink 章节需要给出具体的通知/唤醒机制。

**建议改法**: discussion-note 补充通知机制的方向性选择（如 "基于 EventLog 表的新 event 行作为 wakeup 信号，Host 内部后台 asyncio task 定期轮询或通过 WAL hook 通知"）。

**是否阻塞 design.md 生成**: 不阻塞。

---

## Finding 9 [MEDIUM] — `execution_target` 字段无定义

**严重程度**: MEDIUM

**位置**: `discussion-note.md` L131，"StartRunRequest" 中的 `execution_target` 字段

**当前写法**:
```
StartRunRequest:
  session_id
  client_request_id
  input
  execution_target
  queue_policy
```

**为什么有问题**:

`execution_target` 是区分本地/远程执行的关键字段。文档在 "远程执行拓扑" 节（L36-L44）描述了 LocalProxy 和 RemoteProxy，但没有与 `execution_target` 字段连接起来。它的类型（enum? string?）、合法值（`local`? `remote`? 具体的 remote target identifier?）和路由规则（如何从 execution_target 选择 Proxy）均未定义。

**影响**: design.md 作者需要自行定义 `execution_target` 的类型和路由规则。

**建议改法**: discussion-note 补充 `execution_target` 的类型定义（建议 enum: `local | remote(target_id)`），以及与 WorkerProxy 的路由关系。

**是否阻塞 design.md 生成**: 不阻塞。

---

## Finding 10 [MEDIUM] — cancel vs suspend 分布式竞态覆盖不全

**严重程度**: MEDIUM

**位置**: `discussion-note.md` L592-L593，"Terminal / Cancel / Steer 竞态规则"

**当前写法**:
```
cancel 与 suspend 同时发生时，若 awaiting outcome 已被 Engine 接受并产生 run_suspended，
late cancel 不覆盖 suspended；Host 将 Run 置为 WAITING，后续取消该 waiting run 走 Host cancel 语义。
```

**为什么有问题**:

这只覆盖了 "suspend 先到 Host，cancel 后到 Host" 的场景。另一个竞态场景未覆盖：

1. 用户在 UI 发起 cancel，Host append `CANCEL_REQUESTED` fact。
2. Cancel 信号发往 EngineWorker，但在 Engine 检查 run-local cancellation token 之前，ToolExecutor 返回了 `ToolAwaitingOutcome`。
3. Engine emit `tool_awaiting` + `run_suspended`。
4. Host 收到 suspended 事件时，cancel 已经登记。

此时应该让 Run 进入 `WAITING` 还是 `CANCELLING`？当前规则说 "late cancel 不覆盖 suspended"，但在分布式系统中，"late" 的判断本身就是竞态的——cancel 和 suspend 在两个不同的时间线中。需要以 Host ingest（canonical fact append 顺序）而不是物理时间作为裁决依据。

**影响**: 分布式场景下的 cancel/suspend 竞态可能导致不确定的 Run 状态。

**建议改法**: 补充规则——以 Host 侧 canonical fact append 顺序为裁决真源：
- 如果 `CANCEL_REQUESTED` 先于 `TOOL_AWAITING` append → cancel 获胜，Run 继续 CANCELLING。
- 如果 `TOOL_AWAITING` 先于 `CANCEL_REQUESTED` append → awaiting 获胜，Run 进入 WAITING。

**是否阻塞 design.md 生成**: 不阻塞，但 design.md 的竞态规则需要覆盖此场景。

---

## Finding 11 [MEDIUM] — `start_run` 返回 `RunSnapshot` 与流式消费的工作流断链

**严重程度**: MEDIUM

**位置**: `discussion-note.md` L86-L91，"Host 公共接口讨论入口"

**当前写法**:
```
start_run(host, request) -> RunSnapshot
stream_run_events(host, run_id, cursor) -> EventStream
```

**为什么有问题**:

`start_run` 返回 `RunSnapshot`（同步快照），事件流通过独立的 `stream_run_events` 获取。这意味着流式调用方需要两次调用：先 `start_run`，再 `stream_run_events`。在这两次调用之间：
- 如果 Run 已经 terminal（例如极快执行完成），`stream_run_events` 是否还能拿到完整事件流？
- cursor 的初始值从哪里来？`RunSnapshot` 中是否包含 cursor？
- 如果调用方在 `start_run` 和 `stream_run_events` 之间 crash，重连时如何知道 cursor？

文档没有描述 `RunSnapshot` 的字段结构，也没有说明 cursor 在哪个对象上暴露。

**影响**: 流式调用方的断线重连体验取决于 cursor 的可用性。如果 `RunSnapshot` 不包含 cursor，断线后的调用方无法知道从哪里开始补读。

**建议改法**: discussion-note 补充 `RunSnapshot` 的最小字段定义，至少包含 `run_id`, `status`, `event_cursor`。或者将 `start_run` 的返回类型改为同时包含 snapshot 和 event stream（类似 `RunStream` 模式）。

**是否阻塞 design.md 生成**: 不阻塞。

---

## Finding 12 [LOW] — pinned_state 更新机制缺失

**严重程度**: LOW

**位置**: `discussion-note.md` L748-L755，"pinned_state 至少包含"

**当前写法**:
```
pinned_state 至少包含：
- current_goal
- confirmed_subjects
- user_constraints
- open_questions
```

**为什么有问题**:

pinned_state 的内容定义清晰，但**谁、何时、基于什么事实**更新 pinned_state 完全没有描述。pinned_state 是跨 run 共享的稳定状态，其更新规则直接影响 session memory snapshot 的正确性。如果模型可以在 tool result 后随意修改 `current_goal`，会破坏 session 的目标稳定性。

**影响**: memory 实施阶段需要补充 pinned_state 的更新 governance。

**建议改法**: discussion-note 补充 pinned_state 更新的最小约束：
- `current_goal`：仅用户在 run input 中显式更新时变更。
- `confirmed_subjects`：由 ToolRuntime 根据 confirmed fact 更新。
- `user_constraints`：仅用户在 run input 中显式更新时变更。
- `open_questions`：由 ToolRuntime 根据工具结果和用户追问更新。

**是否阻塞 design.md 生成**: 不阻塞。

---

## Finding 13 [LOW] — TruncationManager cursor 生命周期完全延迟

**严重程度**: LOW

**位置**: `discussion-note.md` L519

**当前写法**:
```
cursor 生命周期、TTL、单次读取 limit、重复续读、错误 envelope 和取消时资源收口
属于 TruncationManager / ToolRuntime policy。
```

**为什么有问题**:

被延迟的决策中，cursor TTL 是一个有架构影响的参数——如果 cursor 需要跨 turn 保持有效，cursor 存储必须 durable；如果 cursor 只在当前 run 内有效，则可以是内存态。这个选择会影响 TruncationManager 是否需要持久化存储。

**影响**: 延迟到 implementation 阶段可能导致 rework。

**建议改法**: 确认 cursor 的最小生命周期（建议至少跨当前 run，这样 resume 后的新 Attempt 仍需能续读）。

**是否阻塞 design.md 生成**: 不阻塞。

---

## Finding 14 [LOW] — 几个设计领域未被 discussion-note 覆盖

**严重程度**: LOW（提醒，可能是故意的 scope 选择）

**位置**: discussion-note 全文

以下设计领域在 discussion-note 中未被讨论。如果这些是有意的 scope 排除（第一版不做），建议在 discussion-note 中明确声明为 non-goal；如果是遗漏，建议补充最低限度的方向性讨论：

1. **Lane / 并发容量控制**: 多进程是硬需求，但 discussion-note 只讨论了 admission 语义规则，没有讨论并发容量控制机制。例如：如果 3 个 run 同时在 3 个进程中执行，是否有限流？lane 是否需要在 discussion 阶段确立为 `dayu.runtime` 的基础原语？
2. **Reply Outbox**: 完全没有讨论。最终回答如何投递到 WeChat/Web 等外部渠道？如果第一版不需要 Reply Outbox，建议明确声明。
3. **Replay / Output Validation**: 未讨论。模型输出脏数据（解析失败、空输出、格式不符合 contract）后如何修复？如果第一版不做 replay，建议明确声明。
4. **Host lifecycle**: 未讨论 Host 自身的启动、关闭、优雅退出流程。多进程 crash recovery 依赖 Host 的启动恢复逻辑。

**建议**: 逐项确认是否为第一版 non-goal，若是，在 discussion-note 中增加 "第一版 non-goals" 节。

**是否阻塞 design.md 生成**: 不阻塞。

---

## implementation-control.md 专项审查

### Finding IC-1 [LOW] — Phase 编排尚未定义（当前合理状态）

**严重程度**: LOW

**位置**: `implementation-control.md` L115-L117

**当前写法**:
```
当前阶段尚未进入 Host 实施。下一步是由 discussion-note.md 生成新的 design.md，
并在本文档中补充总控 phase 编排。
```

**评估**: 在 design.md 生成之前，phase 编排确实无法定义。这是工作流的合理状态，不是缺陷。

### Finding IC-2 [LOW] — Phase discussion 检查清单可以增强

**严重程度**: LOW

**位置**: `implementation-control.md` L76-L83

当前 phase discussion 至少需要确认：
```
- phase 目标与 success signal；
- 本 phase 是否服务于总控设计目标；
- 对应 design.md 章节是否足够具体；
- 本 phase 的 scope boundary、non-goals 与 stop conditions；
- 是否存在会阻塞 handoff implementation-ready plan 的架构、状态机、公共接口、schema、持久化或测试问题。
```

**建议补充**:
- **本 phase 是否与 discussion-note 中的已确认决议一致**——防止 plan agent 在设计不完整的区域自行发挥，偏离讨论共识。
- **本 phase 是否引入了跨层依赖**——特别是有无隐式 Engine 修改需求（implementation-control 已有 "不得夹带 Engine 修改" 的强制约束，但检查清单中没有对应提醒项）。
- **本 phase 的交付物中哪些可能影响后续 phase 的设计假定**——防止 phase N 的设计决策与 phase N+1 的预期冲突。

### 工作流整体评估

implementation-control 的工作流设计（L51-L63）是合理的：
- discussion-note → design.md → update phases → select phase → discuss → plan → review → confirm → implement → verify 的链条清晰。
- 每个 phase 单独生成 handoff plan，且 plan 必须基于真源文档（discussion-note + design.md + 本文档），这个约束有效防止 plan agent 从旧代码路径推导架构。
- "phase 讨论、plan、implementation、review、fix 或 re-review 过程中出现 material open question 时必须停下来和用户讨论" 的强制约束（L92-L94）是关键的防偏机制。

**风险**: 工作流没有定义 "material open question" 的判定标准。如果 plan agent 将架构级问题判定为 "可以在 implementation 中解决"，会绕过用户讨论环节。建议补充：凡涉及状态机、public interface、schema、持久化、并发、恢复、测试期望的 open question，一律视为 material。

---

## 剩余风险评估

即使上述 blocking finding 被解决，进入 design.md 生成时仍存在以下 residual risk：

| # | 风险 | 影响范围 | 缓解措施 |
|---|------|---------|---------|
| R1 | discussion-note 的决议密度不均匀——cancel/steer/EventLog/memory 很详细，但存储/并发/调度几乎是空白 | design.md 可能在存储和并发相关章节自创设计，削弱讨论共识 | design.md 生成后，对存储/并发章节做专项 review |
| R2 | "Host / ToolRuntime" 复合主语在 design.md 中被拆分为独立组件时，可能出现归属矛盾 | TruncationManager, fetch_more, guidance 的进程归属 | design.md 生成时先定义 ToolRuntime 边界再展开子系统（参见 Finding 4） |
| R3 | 远程执行拓扑只描述了控制流，没有描述数据流（EngineEvent 如何从 RemoteProxy 回传到 Host ingest） | EventLog append, stream fanout 的延迟、可靠性和背压 | 远程执行 phase 前补充数据面讨论 |
| R4 | discussion-note 没有讨论 Host 自身的启动/关闭/优雅退出流程 | 多进程 crash recovery, session 恢复的初始化路径 | design.md 补充 Host lifecycle 章节 |
| R5 | implementation-control 的 phase 列表尚未定义，无法评估 phase 之间的依赖和风险传递 | phase 编排可能遗漏跨 phase 的阻塞依赖 | design.md 生成后立即编排 phase 并做依赖分析 |
| R6 | EventLog payload 外移原则（L392-L398）中 "canonical 小 payload" vs "大内容" 的边界是定性的，未量化 | EventLog 可能因判断不一致导致关键恢复信息缺失或 EventLog 膨胀 | design.md 中给出具体的 size threshold 或判别标准 |
| R7 | EventLog canonical fact types（L424-L448）中 `RUN_TERMINAL` 和 `ATTEMPT_TERMINAL` 是复合事件类型，但未拆分为具体终态事件（如 `RUN_SUCCEEDED`/`RUN_FAILED`/`RUN_CANCELLED`/`RUN_LOST`） | 状态恢复时需要通过 payload 区分终态类型，增加 EventLog 消费复杂度 | design.md 中将 TERMINAL 拆分为具体的终态 event types |

---

## 进入 design.md 生成的条件

### 必须满足（blocking）

1. **收束 cancel watchdog 的 6 个开放项**（Finding 1），至少产出：
   - watchdog timeout 边界（数量级即可）。
   - `CANCELLING` → `CANCELLED` vs `LOST` 的升级条件。
   - 消除 L594 与 L711 的矛盾。
   - 取消控制消息的最小 id 集合（run_id + attempt_id + execution_id）。

### 建议满足（high，可在 discussion-note 中给方向性决议，也可在 design.md 生成时由人工逐项裁决）

2. 承诺存储方案方向——建议明确 SQLite（Finding 2）。
3. 承诺多进程协调的基础机制方向（Finding 3）。
4. 定义 ToolRuntime 边界——建议明确为 Host 内部子模块（Finding 4）。
5. 确认第一版 resume_policy 范围——建议只做 poll（Finding 5）。
6. 明确 RunInputBuilder 归属和 messages 重建的输入源清单（Finding 6）。

### 可在 design.md 生成过程中解决（medium/low）

Finding 7-14 及 IC-1/IC-2 可在 design.md 生成时由人工逐项裁决，不需要阻塞进入条件。

### 建议的进入步骤

1. 用户与 Agent 逐项 review 本报告中的 Finding 1-6。
2. 更新 discussion-note.md：收束 Finding 1（必须），对 Finding 2-6 给出方向性决议（建议）。
3. 确认 implementation-control.md 中补充 "material open question" 的判定标准。
4. 进入 design.md 生成。
