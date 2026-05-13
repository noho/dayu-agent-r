# Host Design Review — Draft 2 (2026-05-12, DS)

## 审查元信息

- **Gate**: design review（role-scoped，独立审查）
- **审查目标**: `docs/host/design.md`（当前版本，已吸收前序 DS/MiMo/Codex review findings 并完成多轮修订）
- **辅助参考**: `dayu/README.md`（术语真源）、`docs/host/implementation-control.md`（工作流约束）
- **禁止参考**: `docs/host/discussion-note.md`（已降级，不作为设计真源）
- **审查者**: AgentDS（adversarial review，独立于 design.md 生成者及前序 reviewer）
- **约束**: 只产出本 review artifact；不修改 design.md；不启动 Gateflow；不 commit/push/PR

---

## 前序 Review 状态确认

当前 `design.md` 已吸收前序三轮 review 的 controller 标注为"已处理"的全部 findings。关键改进包括：

- **EventLog sequence**: 已从悬空收敛为全局单调 `event_sequence`（Section 12）。
- **Canonical event contract matrix**: 已补完整的 event class × scope × payload × state side effect × resume/audit 矩阵（Section 12.3）。
- **Host Handle / Composition Root**: 已定义最小依赖边界和 `HostPolicyProviderSet`（Section 9.1）。
- **状态迁移矩阵**: 已补完整的操作 × 前置状态 × 目标状态 × canonical facts × Attempt 动作表（Section 8.1）。
- **Steer-terminal 竞态**: 已补完整的竞态规则和降级路径（Section 11）。
- **Queue promotion**: 已明确 per-session FIFO、CAS 抢 active slot、promotion trigger 和事务边界（Section 8）。
- **Snapshot 语义**: 已给 `SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`HostEventStream` 最小语义（Section 10）。
- **RECOVERING 退出**: 已补三条退出路径（Section 8.1）。
- **Wait record / resolve_wait**: 已补完整 pipeline、adapter 分层和 atomic close/resume 语义（Section 19）。

当前 `design.md` 是一份成熟度显著高于初版的设计真源。本 review 聚焦于**初版 review 未覆盖、修订后新引入、或虽已部分处理但仍有实质性间隙**的问题。

---

## Controller 状态标注（2026-05-13）

本 review 的 findings 已按 `docs/reviews/host-design-review-draft2-controller-adjudication-20260512.md` 裁决，并已写回 `docs/host/design.md`。下方原始严重度保留为 review-time 记录；后续 plan / implementation 以本节状态和当前 `design.md` 为准。

| Finding | 状态 | 归属 / 说明 |
| --- | --- | --- |
| 1 recovery / retry / replay 上限 | 已写回 | recovery、retry、replay、compaction retry 必须有 Host policy 上限。 |
| 2 WAITING cancel 路径 | 已写回 | `WAITING` cancel 直接 terminal，迟到 wait result 不进 canonical EventLog。 |
| 3 remote at-least-once 风险 | 已写回 | Host 不保证 exactly-once 远程物理执行；依赖 `execution_id`、工具级幂等和 best-effort cancel。 |
| 4 CANCELLING -> WAITING 语义 | 已写回到竞态规则 | Host ingest 顺序为裁决真源；WAITING 入口和 cancel 路径分开。 |
| 5 duplicate governance vs business semantics | 已裁决并收窄 | run-local duplicate governance；Host 不解析财报业务语义。 |
| 6 replay staleness / TTL | 后续 phase 细化 | `design.md` 固定复用已接受且仍有效工具事实；TTL / staleness policy 进入 retry / replay phase。 |
| 7 error taxonomy mapping | 后续 phase 细化 | 进入 API / error taxonomy phase。 |
| 8 deterministic JSON digest | 已写回 | digest 必须基于确定性序列化 / canonicalization。 |
| 9 recovery scan 进程归属 | 后续 phase 细化 | dispatch record 语义保留；具体扫描 owner / batch 策略进入 recovery phase。 |
| 10 outbox target / routing | 已写回到架构级 | delivery target 必须来自 HostCallContext / Session binding / request 显式字段；channel routing 进入 Outbox phase。 |
| 11 token estimator fallback | 已写回到架构级 | token estimator 是预算估算，不是 provider tokenizer 真源；具体 adapter policy 后续细化。 |
| 12 stream_run_events cursor type | 已处理 | `event_sequence` 是 Host event stream cursor。 |
| 13 FollowupSnapshot queue behavior | 后续 phase 细化 | 进入 API snapshot phase。 |
| 14 create_session 幂等边缘 | 已处理到架构级 | `create_session` / `ensure_session` 语义和 slot 重绑定已固定。 |

---

## Assumptions Tested

本 review 验证了以下 assumptions：

| # | Assumption | 验证结果 |
|---|-----------|---------|
| A1 | Host 是 Session/Run/Attempt/EventLog/admission/cancel/resume/retry/steer/replay/memory/tool governance 的治理真源 | **成立**，边界清晰 |
| A2 | Engine 只执行单次 `AgentRunRequest`，不拥有 Host 生命周期和 durable state | **成立**，Section 16/17/28 的多处硬约束保证 |
| A3 | 第一版支持单机多客户端/多进程，本地 Engine 与远程 Engine 并列执行 | **成立**，Section 8/9/16 覆盖 |
| A4 | EventLog 是 append-only canonical fact source，所有 projection 由此派生 | **成立**，Section 12/13/15 多处强调 |
| A5 | `execution_id` 用于拒绝迟到 Attempt 事件，不是 lease | **成立**，Section 3/16 明确 |
| A6 | 远端执行环境不拥有 Host 状态 | **成立**，Section 16 的 7 条远程执行不变量保证 |
| A7 | 设计已覆盖所有状态迁移路径，plan agent 无需自行发明 | **部分成立**，见 Finding 2、Finding 3 |
| A8 | 公共接口的错误分类足以支撑调用方编写正确的错误处理 | **部分成立**，见 Finding 7 |
| A9 | 第一版 non-goals 边界清晰，不会在实现时意外膨胀 | **成立**，Section 27 明确 |

---

## Findings

### Finding 1 [BLOCKING] — 缺少 recovery/retry/replay 最大尝试次数上限，存在无限循环风险

**严重程度**: BLOCKING

**位置**: Section 8.1（状态迁移契约）、Section 20（Suspend/Resume/Retry/Replay）、Section 26（Recovery）

**当前写法**:

`RECOVERING` 的退出路径定义了 `RECOVERING -> RUNNING`、`RECOVERING -> CANCELLED`、`RECOVERING -> LOST` 三条。retry 定义为 "confirmed failure / recoverable failure 后的 Host policy 或用户动作"。replay 定义了类似语义。但全文没有出现最大重试次数、recovery 尝试上限、退避策略或循环断路机制。

**为什么有问题**:

以下循环路径没有上限保护：

```
RECOVERING -> RUNNING -> (crash / context compaction / provider error)
    -> RECOVERING -> RUNNING -> ...
```

```
FAILED -> retry -> RUNNING -> FAILED -> retry -> ...
```

```
RUNNING -> context_compaction -> RECOVERING -> RUNNING
    -> context_compaction -> RECOVERING -> ...
```

在生产环境中，以下场景可能触发无限循环：
1. **Recovery 死循环**: 旧 Attempt 反复 LOST，Host 反复创建新 Attempt 恢复，但每次恢复后的新 Attempt 又因同一持久性故障（如 provider 持续不可用、context 持续超预算）而失败。
2. **Retry 风暴**: `retry_run` 没有最大次数限制，用户或 policy 可能无限重试，消耗 provider quota。
3. **Context compaction 循环**: Engine 反复触发 `context_compaction_requested`，Host 反复 compact 并创建新 Attempt，但 compact 后仍超预算。

Section 8.1 的迁移矩阵没有标注任何 `max_attempts` 或 `recovery_limit` 约束。Section 26 的 recovery scan 没有定义 "重复恢复超过限制" 的判定和收口行为。

**影响**: 如果没有上限，以下后果会发生：
- Session 的 active slot 被永久占用（RECOVERING 循环不退出）。
- Provider quota 被无限消耗（retry/replay 无上限）。
- 用户无法感知"系统在死循环"，因为没有 `LOST` 或 `FAILED` 终态收敛。
- EventLog 被大量 `ATTEMPT_STARTED`/`ATTEMPT_LOST`/`RUN_RECOVERING` 事件膨胀。

**建议改法**:

在 design.md 中增加 attempt counter 和 circuit breaker 约束：

1. Run 级别维护 `attempt_count`（或从 EventLog 中 `ATTEMPT_STARTED` 计数）。
2. 定义 `max_recovery_attempts`（例如 3）和 `max_retry_attempts`（例如 3），作为 HostPolicyProviderSet 中 retry/replay policy 的一部分。
3. `RECOVERING -> LOST` 的条件中增加 "recovery attempt count >= max_recovery_attempts"。
4. `FAILED` Run 的 retry 在 "retry count >= max_retry_attempts" 时拒绝。
5. Context compaction 循环在 "consecutive compaction count >= max_compaction_attempts" 时 Run 进入 `FAILED` 并 append `CONTEXT_COMPACTION_FAILED`。

这些参数的具体默认值属于 implementation phase，但**上限的存在性和状态机收口路径**是架构级决策，必须在 design.md 中确认。


**是否阻塞 phase planning**: **是**。状态机缺少循环收敛条件，plan agent 会自行定义（或不定义）上限，可能导致生产环境中 Session slot 泄漏和资源耗尽。

---

### Finding 2 [BLOCKING] — 对 `WAITING` 状态 Run 发起 cancel 的迁移路径缺失

**严重程度**: BLOCKING

**位置**: Section 6（Run 生命周期）、Section 8.1（状态迁移契约）、Section 21（Cancel）

**当前写法**:

Section 8.1 的迁移表中，`cancel_run` 只有两行：

| 操作 | 前置状态 | 目标状态 |
|------|---------|---------|
| `cancel_run` on queued | Run `QUEUED` | Run `CANCELLED` |
| `cancel_run` on active | Run active | Run `CANCELLING`，后续 `CANCELLED` / `WAITING` / `RECOVERING` / `LOST` |

Section 8 定义 active Run 状态集合为 `RUNNING, WAITING, CANCELLING, RECOVERING`。

**为什么有问题**:

`WAITING` 是 active Run 状态。按当前定义，对 `WAITING` Run 发起 cancel 应走 "cancel_run on active" 路径，Run 进入 `CANCELLING`，然后……需要做什么？

此时 Attempt 已经 `SUSPENDED`，不是 `RUNNING`。cancel 信号传播给谁？
- Attempt 已关闭为 `SUSPENDED`，没有活跃的 EngineWorker 可取消。
- wait record 仍在 waiting 状态，外部 job 可能仍在运行。
- Host 是否应该将 wait record 标为 cancelled？是否应该尝试取消外部 job？

Section 21 Cancel 规则只说 "cancel 只阻止未来工作，不覆盖已接受事实" 和 "已接受 awaiting outcome 和 run_suspended 不被 late cancel 覆盖"。这暗示 cancel 不能覆盖已有的 awaiting——但如果不覆盖，Run 怎么从 CANCELLING 进入终态？

两种可能的解释（都需要设计确认）：

A. Cancel 不覆盖 await 结果，所以 Run 必须在 `WAITING`/`CANCELLING` 状态等待 wait record resolution，再决定是否真正取消。但这意味着 cancel 在 WAITING 场景下可能被无限期延迟。

B. Cancel 将 wait record 标记为 cancelled，Run 直接进入 `CANCELLED`，但外部 job 不一定被取消（因为 Host 没有能力取消外部 job）。这符合 "已接受事实不被覆盖" 但可能产生"幽灵 job"。

Section 8.1 的迁移表中 `CANCELLING -> WAITING` 作为可能路径出现（在 `cancel_run on active` 的目标状态列中），但它的语义是：cancel 请求发出后，Engine 抢先 emit 了 `run_suspended`，cancel 无法覆盖 suspend。这个路径本身合理——但它的前提是 cancel 时 Attempt 仍在 RUNNING。如果 cancel 时 Attempt 已经 SUSPENDED，就没有 "Engine 抢先 emit suspend" 的竞态，而是 "cancel 到达时等待条件已成立"。

**影响**: plan agent 在处理 "用户 cancel 一个正在等待外部 job 的 Run" 时需要自行定义行为。如果选错，可能导致：
- Run 永远卡在 CANCELLING（active slot 泄漏）。
- 外部 job 完成后的 result 被丢弃或错误应用。
- EventLog 中出现矛盾的 cancel + terminal 事件序列。

**建议改法**:

在 Section 8.1 迁移表中增加一行，或在 Section 21 中补充：

```
cancel_run 且 Run = WAITING：
  - Host 标记 wait record 为 cancelled（不删除，保留 audit trail）。
  - Host append CANCEL_REQUESTED。
  - Run -> CANCELLED，Attempt 保持 SUSPENDED（已完成的历史不重写）。
  - 外部 job 是否被取消取决于外部系统能力；Host 不保证外部副作用回滚。
  - 若 wait record 的 resume_policy=callback，callback 到达时 Host 拒绝（Run 已终态），
    返回 idempotency_conflict，记录 diagnostic。
```

或明确声明 "WAITING Run 不可 cancel，cancel 请求排队等待 wait resolution 后再裁决"——并在设计层面给出等待 cancel 的超时和升级路径。

**是否阻塞 phase planning**: **是**。这是一个完整的用户可见行为（用户在 Run 等待外部 job 时点了取消），当前设计未覆盖该路径的状态迁移和 EventLog 序列。

---

### Finding 3 [BLOCKING] — 远程 Dispatch 的 at-least-once 执行风险未设计缓解机制

**严重程度**: BLOCKING

**位置**: Section 16（WorkerProxy / EngineWorker）、Section 26（Recovery）

**当前写法**:

Section 16 定义了 Remote boundary 的 7 条不变量，核心是"远端不拥有 Host 状态"。Section 26 定义 recovery scan：无法确认的旧 Attempt 标为 `LOST`，基于 EventLog 创建新 Attempt。

但设计未覆盖以下关键场景：

```
1. Host dispatch Attempt 到 RemoteProxy。
2. RemoteProxy 成功将请求送达 RemoteStub/EngineWorker。
3. 但在任何 EngineEvent 回传之前，Host-RemoteProxy 连接断开。
4. Host recovery scan 发现 dispatch record 无 last_event_at，无法确认远端状态。
5. Host 将旧 Attempt 标为 LOST，创建新 Attempt 并 dispatch。
6. 此时远程 EngineWorker 仍在执行旧 Attempt——两个 Attempt 并发执行。
```

**为什么有问题**:

Section 16 说 "迟到事件、重复事件或 execution_id 不匹配事件不能污染 canonical EventLog"，这正确——旧 Attempt 的事件会被 `execution_id` 校验拒绝。但以下危害不在 EventLog 污染范畴内：

1. **重复工具执行**: 旧 Attempt 的 EngineWorker 仍在执行工具调用（读取财报、查询外部 API），即使其结果最终被 Host 拒绝。对只读工具这是资源浪费；对外部写入/付费工具这是**重复副作用**。
2. **Provider quota 双倍消耗**: 旧 Attempt 的 provider 调用仍在消耗 token。
3. **远端资源泄漏**: 旧 EngineWorker 不感知自己已被"废弃"，继续持有内存/连接直到自然结束或超时。

设计承认 `execution_id` 用于"拒绝迟到 Attempt 事件"，但不等于解决了"远端仍在执行但我们不再接受其结果"的问题。当前设计的隐含假设是"旧 Attempt 的结果不可确认 = 旧 Attempt 没有远程执行"，但网络断连不等于远端停止执行。

**影响**:
- 对只读财报工具：重复读取造成资源浪费，工具结果被丢弃但查询已发生。
- 对外部写入/付费工具：重复副作用，无 idempotency 保护时可能造成数据错误或重复计费。
- EngineWorker 泄漏：远端进程继续运行直到自然超时，可能堆积多个"僵尸"执行。

这不是一个"后续 Remote phase 实现细节"——它是架构层面的安全边界。至少需要在设计层面确认：Host 是否可以/如何向远端传播"此 execution_id 已废弃"的信号，以及如果无法传播时，接受什么级别的风险。

**建议改法**:

在 Section 16 或 Section 26 中增加 at-least-once 执行风险的架构声明：

1. **明确风险边界**: 声明 Host 不保证 exactly-once 远程执行。在 dispatch 后和首个事件回传前的窗口内，如果连接断开，远端可能执行但结果为迟到事件被拒绝。
2. **要求工具级幂等**: 对外部写入/付费工具，工具 schema 必须提供 `idempotency_key`；该 key 由 Host 在 dispatch 时生成并随 `AgentRunRequest` 传递到远端。即使新/旧 Attempt 并发执行同一逻辑操作，工具级幂等保证外部副作用安全。
3. **要求 cancel 传播**: 当 Host 将旧 Attempt 标为 LOST 时，如果 Proxy/Stub 连接仍可用（只是部分断开），Host 必须尝试向旧 `execution_id` 发送 cancel/shutdown 信号——best-effort，不保证送达。
4. **要求 execution_id 在 dispatch payload 中**: RemoteProxy dispatch payload 必须携带 `execution_id`，EngineWorker 必须在开始执行前持久化该 ID，以便在接收到 late cancel 信号时能关联。

这些是架构级约束，不是 wire protocol 细节。wire protocol 细节（RPC、ack、heartbeat）可以留给 Remote phase，但**重复执行的风险边界和缓解策略**必须在 Host 架构真源中声明。

**是否阻塞 phase planning**: **是**，如果第一版包含远程执行。如果第一版只做 LocalProxy，降级为 HIGH（远程执行设计预留不足，影响 Remote phase planning）。

---

### Finding 4 [HIGH] — `CANCELLING -> WAITING` 迁移路径的语义未解释，容易误实现

**严重程度**: HIGH

**位置**: Section 8.1 迁移表、Section 6 Run 生命周期、Section 21 Cancel

**当前写法**:

Section 8.1 状态迁移表中 `cancel_run on active` 的目标状态列为：

```
Run -> CANCELLED / WAITING / RECOVERING / LOST
```

Section 6 的 Run 状态列表中 `CANCELLING` 的语义描述了 "正在等待 active Attempt 收口或超时升级"。

Section 21 说 "cancel 与 suspend 同时发生时，遵循 Engine 已接受事实不被覆盖的规则" 和 "已接受 awaiting outcome 和 run_suspended 不被 late cancel 覆盖"。

**为什么有问题**:

`CANCELLING -> WAITING` 的语义是：用户请求取消 → Host 发起 cancel → 但在 cancel 生效前，Engine emit `run_suspended` → suspend 事实先于 cancel 事实被 Host ingest → Host 遵循"已接受事实不被覆盖"，Run 进入 WAITING。

这个路径在逻辑上成立，但设计文档中有两处不一致：

1. Section 8.1 迁移表中 `cancel_run on active` 行没有提及 "Engine suspended 可能抢先" 的竞态。该行写的是 "Run CANCELLING，后续 CANCELLED / WAITING / RECOVERING / LOST"，但 `WAITING` 作为终态出现在一个 "cancel" 操作的结果中，从调用方视角看是矛盾的——"我请求取消，结果变成了等待？"

2. 迁移表中没有 `CANCELLING + Engine suspended` 作为独立的竞争路径。plan agent 需要自行推导：当 Attempt 因 suspend 关闭时，如果 Run 当前是 CANCELLING，应该怎么办？是让 suspend 覆盖 cancel（Run -> WAITING）还是 cancel 覆盖 suspend（Run -> CANCELLED）？

Section 21 的规则给出了方向（suspend 不被 late cancel 覆盖），但没有区分：
- **Case A**: cancel 请求先于 suspend 事件到达 Host ingest → cancel 先 append → suspend 是 late event（execution_id 匹配但 cancel 已生效）→ suspend 被拒绝？
- **Case B**: suspend 事件先于 cancel 请求到达 Host ingest → suspend 先 append → cancel 请求到达时 Run 已是 WAITING → 进入 Finding 2 的未覆盖路径。

当前设计用 "Host ingest 顺序是分布式竞态裁决真源" 作为统一原则，这本身正确。但 `CANCELLING -> WAITING` 在 Case A 和 Case B 中分别意味着什么，需要在迁移表或 Cancel 章节中明确。

**影响**: plan agent 需要自行设计 cancel 与 suspend 在 Host ingest 层的竞态处理逻辑。如果误实现，可能导致：
- cancel 覆盖已接受的 suspend 事实。
- CANCELLING 状态无法退出。
- EventLog 中出现 CANCEL_REQUESTED 后 append ATTEMPT_SUSPENDED + RUN_WAITING 的正确序列，但调用方 UI 困惑于"为什么 cancel 变成了等待"。

**建议改法**:

在 Section 21 中补充 cancel/suspend 竞态的精确规则：

```
cancel 与 suspend 竞态（Host ingest 顺序裁决）:
  - 若 CANCEL_REQUESTED 先于 tool_awaiting/run_suspended 进入 EventLog:
      cancel 生效，Attempt 收口为 CANCELLED，Run 进入 CANCELLED。
      后续到达的旧 execution_id 的 suspend 事件为迟到事件，进入 diagnostic。
  - 若 tool_awaiting/run_suspended 先于 CANCEL_REQUESTED 进入 EventLog:
      suspend 事实已接受，Attempt 收口为 SUSPENDED，Run 进入 WAITING。
      此时 cancel 请求的处理走 "cancel WAITING Run" 路径（见 Finding 2 修正）。
  - 若两者在同一事务边界内（不可能，因为来自不同来源）：
      按 event_sequence 顺序，先 append 者胜出。
```

同时在 Section 8.1 迁移表中为 `cancel_run on active` 的 "WAITING" 目标状态加脚注："仅当 Engine suspend 先于 cancel 进入 EventLog 时发生；cancel 不覆盖已接受的 awaiting/suspended 事实"。

**是否阻塞 phase planning**: **不阻塞**，但 plan agent 在处理 cancel 逻辑时会遇到此决策真空。建议在进入 cancel/attempt phase 前收束。

---

### Finding 5 [HIGH] — 语义级重复工具调用治理与 "Host 不承载财报业务语义" 的边界存在张力

**严重程度**: HIGH

**位置**: Section 17.1（语义级重复工具调用治理）、Section 2（分层边界）

**当前写法**:

Section 17.1 定义重复判定信号包括 `evidence scope：公司、期间、报告、章节、source ref、query scope`。Section 2 规定 "Host 不承载财报业务语义，不直接管理财报原文仓储规则"。

**为什么有问题**:

`公司`、`期间`、`报告`、`章节` 是典型的财报业务概念。如果 ToolRuntime 需要按这些维度做语义去重，它至少需要：
1. 从工具参数中提取并标准化这些字段（例如 "腾讯" vs "Tencent" vs "0700.HK"）。
2. 理解什么构成 "同一公司"、"同一期间"、"同一报告章节"。
3. 跨工具调用比较 evidence scope 的覆盖关系（例如 "2024年年报" 包含 "2024年Q4"）。

这些能力属于财报领域知识。如果 ToolRuntime 直接内嵌这些逻辑，违反 Section 2 的分层边界。如果 ToolRuntime 不内嵌，只做 opaque 参数 digest 比较——那么 "evidence scope" 信号列表中的 `公司、期间、报告、章节` 就是**业务层需要提供**的结构化 metadata，ToolRuntime 只负责比较。

当前设计没有区分这两种实现路径。Section 17.1 用财报业务的术语定义重复判定信号，但未说明这些信号从哪里来、由谁提供、ToolRuntime 是否理解其语义。

**影响**: plan agent 可能将财报业务语义（公司名称标准化、期间比较、报告范围判断）直接实现在 ToolRuntime 中，导致 Host 层被财报业务逻辑污染。后续如果需要支持非财报场景，ToolRuntime 的重复治理将不可复用。

**建议改法**:

在 Section 17.1 中明确重复治理的分层：

```
重复判定信号来源：
  - tool identity、normalized arguments、idempotency key：
      ToolRuntime 直接从工具调用请求中提取。
  - evidence scope（公司、期间、报告、章节等）：
      由工具在 ToolExecutionOutcome 中以结构化 evidence_anchor 提供。
      ToolRuntime 只比较 evidence_anchor 的 digest/ref，不理解财报业务语义。
  - result digest / evidence anchor：
      ToolRuntime 比较已接受工具事实的 digest 与当前请求的预期覆盖范围。
  - run / session / memory context：
      由 Host memory projection 提供当前 goal 和已验证事实的结构化视图。
```

核心原则：ToolRuntime 只做 **digest 比较和 policy 路由**，不做**财报语义理解和标准化**。业务语义标准化是工具实现的责任，结果通过 `evidence_anchor` 结构化字段进入 ToolRuntime。

**是否阻塞 phase planning**: **不阻塞**，但 ToolRuntime phase 的 plan agent 需要此澄清以避免架构污染。

---

### Finding 6 [HIGH] — Replay 复用已接受工具事实但缺少工具结果 staleness/TTL 机制

**严重程度**: HIGH

**位置**: Section 20（Replay）、Section 17.1（语义级重复工具调用治理）

**当前写法**:

Section 20 定义 Replay："Replay 默认不重新执行已接受工具。Replay 通过 EventLog 重建 messages，复用 accepted tool facts / tool messages / evidence anchors。"

**为什么有问题**:

在买方财报分析场景中，工具结果可能随时间失效：
- 实时行情数据已过时（例如 replay 发生在原始 run 的 2 小时后）。
- 外部 API 查询结果有 TTL（例如新闻搜索结果、监管公告列表）。
- 财报 chunk 内容可能已被更正/更新。
- 原始工具调用依赖的凭证/权限可能已过期。

Replay 无条件复用所有已接受工具事实，意味着模型会基于过时数据重新生成 final answer。这可能导致：
- 新 answer 基于过时行情给出错误结论。
- 新 answer 引用的证据已被更正，但模型不知道。
- 用户看到看似合理但基于过期数据的分析报告。

当前设计中，ToolRuntime 的语义级重复治理（Section 17.1）关注的是同一 Attempt 内的重复调用，不涉及跨 Attempt 的结果有效性。Replay 的跨 Attempt 复用没有 freshness 检查。

**影响**: plan agent 需要自行决定是否及如何检查工具结果的时效性。如果忽略，replay 功能可能产出基于过期数据的分析报告，损害买方分析的正确性。

**建议改法**:

在 Section 20 Replay 中增加工具结果 staleness 约束：

```
Replay 工具事实复用条件：
  - 默认复用 accepted tool facts，但必须检查工具结果的 freshness。
  - 工具可在 ToolDefinition 中声明 result_ttl_seconds 或 freshness_policy。
  - 若原始工具结果已超过 TTL，RunInputBuilder 不得将其注入 messages；
    Host 应在重建 messages 时标记该工具调用为 "stale, re-execution needed"，
    或由 replay policy 决定是否允许 Engine 重新调用该工具。
  - 第一版可仅支持 per-tool 声明式 TTL，不实现动态 freshness 查询。
  - 若所有工具结果均在 TTL 内，按原 replay 语义复用。
  - EventLog 中保留原始工具事实，不重写历史。
```

即使第一版将所有工具的 TTL 设为 "无限"（即永不过期），架构层面也需要预留 staleness 检查的插入点和概念框架。

**是否阻塞 phase planning**: **不阻塞**第一版（可设置所有 TTL 为无限），但 replay phase plan 必须覆盖此架构预留。

---

### Finding 7 [HIGH] — 公共接口错误分类未映射到具体方法，`conflict` vs `idempotency_conflict` 语义边界模糊

**严重程度**: HIGH

**位置**: Section 10（Host 公共接口）

**当前写法**:

Section 10 列出公共错误分类至少包括：`not_found`、`invalid_state`、`conflict`、`idempotency_conflict`、`permission_denied`、`internal_error`。但没有说明：
1. `conflict` vs `idempotency_conflict` 的语义区别。
2. 每个公共方法可能返回哪些错误。

**为什么有问题**:

在前序 review (DS Finding 13) 中这被标为 LOW，但经过对 design.md 更仔细的审查，我认为这是一个 HIGH severity 问题。原因：

1. **`conflict` vs `idempotency_conflict` 的区分会影响调用方行为**。例如：
   - `create_session(client_request_id=X)` 首次调用创建 Session，第二次调用同一 `client_request_id` 应返回已有 Session（幂等成功，返回 `SessionSnapshot`）还是返回 `idempotency_conflict` 错误？
   - `start_run(session_id=S, client_request_id=X)` 首次调用创建 Run，第二次调用同一 `(session_id, client_request_id)` 应返回已有 Run（幂等成功）还是 `idempotency_conflict`？
   - `cancel_run(run_id=R, client_request_id=X)` 第二次调用应幂等返回已更新的 RunSnapshot 还是返回 `idempotency_conflict`？

   design.md 中的幂等不变量说这些操作是幂等的——但 "幂等" 意味着 "重复调用返回相同结果"（成功 + 已有对象）还是 "重复调用返回幂等冲突错误让调用方区分"？两种设计都是合法的，但必须一致且明确。

2. **`conflict` 的语义**: 是乐观锁冲突（CAS 失败）？还是业务层冲突（如 "Session 已有 active Run 且 admission=reject"）？这两种冲突的处理方式完全不同——前者调用方可重试，后者是业务状态不允许。

3. **`start_run` 在 admission=reject 时返回什么**？是 `conflict` 错误（因为 active Run 存在）还是成功但 `RunSnapshot.status=REJECTED`（但 design.md 中没有 REJECTED 状态）？Section 8 说 admission 有 `reject` 模式——"拒绝创建新 Run，并返回 active run conflict"——这里的 "conflict" 是指错误类型还是状态描述？

**影响**: plan agent 需要自行设计错误语义。不一致的错误设计会导致：
- 调用方（Service/UI）无法正确区分 "重试可恢复" 和 "需用户处理" 的错误。
- 幂等重试 vs 新请求的边界模糊。
- 测试覆盖不完整。

**建议改法**:

在 Section 10 中补充：

```
错误类别语义：
  - not_found: 目标 Session/Run/Attempt 不存在。
  - invalid_state: 操作与当前状态不兼容（如 cancel 已终态的 Run、
    steer 没有 active Run 的 Session）。
  - conflict: 并发冲突，调用方可重试（如 CAS 失败、active slot 被抢占）。
  - idempotency_conflict: 同一个 client_request_id 被用于不同参数或
    不同意图的请求，与已有幂等映射冲突。
  - permission_denied: 调用方无权执行该操作。
  - internal_error: Host 内部不可恢复错误。

幂等语义统一规则：
  - 用同一 client_request_id 重试同一操作 → 返回已有结果（成功），不返回错误。
  - 用同一 client_request_id 但参数不同 → 返回 idempotency_conflict。
  - 幂等操作为只读时（如 get_run、get_session），不检查 client_request_id。
```

**是否阻塞 phase planning**: **不阻塞**，但公共 API phase 的 plan 必须覆盖此决策。建议在进入第一个 API phase 前收束。

---

### Finding 8 [MEDIUM] — JSON payload 的确定性序列化未声明，危及 payload_digest 幂等性

**严重程度**: MEDIUM

**位置**: Section 12（EventLog）、Section 12.1（Payload 存储）

**当前写法**:

EventLog 形态包含 `payload_json` 和 `payload_digest` 字段。Section 8 强调幂等不变量（`(session_id, client_request_id)` 幂等映射到同一 Run）。Section 12 说 `event_id` 是事件幂等键——"重复 ingest 同一 event_id 必须返回已接受结果，不得 append 第二条 canonical event"。

**为什么有问题**:

Python 标准库 `json.dumps` 不保证确定性序列化：
- dict key 顺序在 Python 3.7+ 保证插入顺序，但当 dict 通过不同路径构造时（如反序列化再序列化），key 顺序可能不同。
- 浮点数精度、NaN/Inf 处理、Unicode 转义在不同 JSON 实现间不一致。
- 空白字符、key 排序在不同系统中可能不同。

如果 `payload_digest` 用于幂等比较或去重，非确定性序列化会导致同一语义内容产生不同 digest，破坏幂等保证。

EventLog 的 `payload_json` 字段如果被用于构造 `event_id`（如 `hash(event_type + payload_json)`），非确定性序列化会直接导致事件重复或幂等检查失败。

**影响**: plan agent 如果不做 canonical JSON serialization，可能导致：
- 同一语义事件被误判为不同事件，EventLog 出现重复。
- digest-based 去重失效。

**建议改法**:

在 Section 12.1 中增加：

```
payload 序列化约束：
  - payload_json 必须使用确定性 JSON 序列化（sorted keys、禁用非必要空白、
    定义明确的浮点数精度和特殊值处理）。
  - payload_digest 必须在确定性序列化后计算。
  - 反序列化-再序列化必须产生字节级相同的结果。
```

或在实现 phase 的 plan 中明确这一点。

**是否阻塞 phase planning**: **不阻塞**，但 EventLog/SQLite schema phase 的 plan 必须覆盖。

---

### Finding 9 [MEDIUM] — Recovery scan 中 "本进程" dispatch record 判断在多进程场景下存在歧义

**严重程度**: MEDIUM

**位置**: Section 26（Host Lifecycle / Recovery）

**当前写法**:

Section 26 的 recovery scan 逻辑：

```
RUNNING / CANCELLING Run 的 active Attempt
  若没有可确认的本进程 dispatch record 与可用执行通道，旧 Attempt 进入 LOST。
```

**为什么有问题**:

"本进程"（this process）的限定在两种场景下有歧义：

1. **同机多进程**: 进程 A 创建 Attempt 并 dispatch 到 LocalProxy。进程 A crash。进程 B 启动并执行 recovery scan。进程 B 发现该 Attempt 的 dispatch record 的 `host_instance_id` 不是自己（是进程 A）。按 "没有可确认的本进程 dispatch record"，进程 B 应标记该 Attempt 为 LOST——这是正确的。

2. **但**：如果进程 A 没有 crash，只是暂时无响应（例如 GC pause、磁盘 I/O 阻塞），而进程 B 是另一个独立 Host 实例（同一 Session slot 的另一入口），进程 B 的 recovery scan 同样会发现 "没有本进程 dispatch record"。此时进程 B 不应标记进程 A 的 Attempt 为 LOST，因为它属于另一个仍在运行的 Host 实例。

Section 9.1 的 dispatch record 包含 `host_instance_id` 和 `connection_state` 字段。Section 26 的 "本进程" 应改为 "任何活跃 Host 实例"——即检查 `host_instance_id` 是否对应一个已知仍在运行的 Host 进程，而不仅仅是 "是否等于当前进程 ID"。

但实际上，设计明确 "不引入重 lease / fencing 系统"，这意味着没有跨进程的 liveness 检测机制。在这种情况下，如果进程 B 无法判断进程 A 是否仍在运行，最安全的行为是 NOT 标记为 LOST（保守策略）——但这会导致 recovery scan 无法恢复进程 A crash 后的 Run。

这是一个真实的架构困境：不引入 lease/fencing 就无法安全判断另一个进程的 liveness；但不标记 LOST 就无法恢复。

**影响**: plan agent 必须在 "保守不恢复（可能永久卡住）" 和 "激进标记 LOST（可能误杀）" 之间自行选择。这不是实现细节，是架构决策。

**建议改法**:

在 Section 26 中明确多进程 recovery scan 的保守策略：

```
多进程 recovery scan:
  - Host 启动时只扫描并恢复 host_instance_id 匹配当前进程的 dispatch record。
  - 不匹配当前进程的旧 Attempt 保持原状，由其原始 Host 实例或用户手动干预处理。
  - 如果原始 Host 实例已确认退出（如通过 pidfile、共享文件系统中的退出标记），
    当前进程的 recovery scan 可以接管其遗留 Attempt（标记 LOST 并评估 RECOVERING）。
  - 第一版不实现跨进程 liveness 检测；仅恢复本进程遗留的 Attempt。
  - 跨进程恢复能力属于后续 phase。
```

这比当前 "没有可确认的本进程 dispatch record" 更精确——它明确了 "只恢复本进程的，不碰其他进程的"。

**是否阻塞 phase planning**: **不阻塞**，但 recovery phase plan 必须覆盖此决策。

---

### Finding 10 [MEDIUM] — Outbox delivery 的投递目标配置和 channel routing 未定义

**严重程度**: MEDIUM

**位置**: Section 15（Read Model / Outbox）

**当前写法**:

Section 15 定义 Outbox："Run terminal fact 提交后，final answer 已成为 Host 真源中的结果；投递给 UI、Web、WeChat、CLI 或其它入口属于 outbox delivery。" Outbox 需具备 "幂等投递键、投递状态、重试次数、last error 和 delivery target"。

**为什么有问题**:

"delivery target" 是什么？如何配置？
- 是每个入口（UI/Web/WeChat/CLI）有一个独立的 delivery target？
- 还是 Session/Run 创建时指定回调 URL/webhook？
- 如果是 CLI，outbox 怎么 "投递"——终端输出？文件写入？
- delivery target 的配置存储在哪里——Session 表？Run 表？独立的 outbox_config 表？

Outbox 的设计正确地将投递从事实真源中隔离，但投递目标的配置和路由是 outbox 能工作的前提。当前设计没有定义这个配置的入口、存储位置和生命周期。

**影响**: plan agent 需要自行设计 delivery target 模型。如果设计不当，outbox 可能投递到错误的 channel，或无法扩展新的 delivery target 类型。

**建议改法**:

在 Section 15 中补充：

```
Outbox delivery target:
  - delivery target 在 Session 创建时由 Service 层指定（例如
    Session.metadata 中的 delivery_channel 字段），或由 admission
    时从入口上下文派生。
  - delivery target 持久化在 Session/Run 级别，不是 outbox 消息级别。
  - 第一版支持的最小 delivery channel 集合：internal（stream fanout）、
    file（CLI/GUI 本地输出）。Web/WeChat 等外部 channel 属于后续 phase。
  - outbox dispatcher 读取 delivery target 后通过 channel adapter 投递。
  - channel adapter 是 Host 内部组件，不是公共接口。
```

这避免了 plan agent 过度设计一个通用消息路由系统。

**是否阻塞 phase planning**: **不阻塞**，但 outbox phase plan 需要此指引。

---

### Finding 11 [MEDIUM] — Context governance proactive trigger 的 token 估算在无 provider tokenizer 时精度无法保证

**严重程度**: MEDIUM

**位置**: Section 24.1（Compact Event 响应路径）、Section 24（Context Governance）

**当前写法**:

Section 24.1 定义 proactive trigger："Host / RunInputBuilder 在 dispatch Attempt 前根据 provider-aware budget、tool facts、memory snapshot、当前用户输入和场景参数判断即将超预算"。Section 24 末尾承认 "provider tokenizer adapter 可后续接入；当前 token estimator 只能作为 Host 预算治理估算，不是 provider tokenizer 真源"。

**为什么有问题**:

设计依赖 "provider-aware budget" 做 proactive compact 决策，但同时承认没有准确的 tokenizer。这意味：

1. Proactive trigger 可能因估算不准确而频繁误触发（token 估高了，实际未超预算），导致不必要的 compaction 和 Attempt 重启。
2. 或者更糟：估算偏低，实际已超预算但未触发 proactive compact，导致 Engine 端 provider 返回 context length exceeded → 走 reactive path → Attempt 失败 → 需要 compact 后重试，浪费一次 provider 调用。

这是一个可实现性风险：proactive compact 的价值取决于 token 估算器的精度。如果第一版 token 估算器精度很低，proactive trigger 可能弊大于利。

**影响**: plan agent 可能花费大量精力实现 proactive compact trigger，但因其依赖不准的 token 估算器而导致 production 中表现不佳。

**建议改法**:

在 Section 24.1 中增加 token 估算器精度约束：

```
token 估算与 proactive trigger 约束：
  - 第一版 token 估算器应提供保守上界估算（宁可高估不低估），
    确保不因低估而漏触发 proactive compact。
  - proactive trigger 的触发阈值应留出 safety margin（例如估算 token
    达到 budget 的 80% 时触发 proactive compact）。
  - 若估算器精度不足以支持有意义的 proactive trigger，
    第一版可退化为仅依赖 reactive trigger（Engine context_compaction_requested），
    不实现 proactive trigger。
  - 无论采用哪种策略，compact 事件和 trace 必须记录估算方法和估算 token 数。
```

这不是削弱设计，而是让设计承认当前限制，并给出降级策略。

**是否阻塞 phase planning**: **不阻塞**。Context governance 通常是后期 phase，此时可能已有 provider tokenizer adapter。

---

### Finding 12 [LOW] — `stream_run_events` cursor 类型未在 API 签名中显式化

**严重程度**: LOW

**位置**: Section 10（Host 公共接口）

**当前写法**:

```
stream_run_events(host, run_id, cursor) -> HostEventStream
```

Section 12 定义了 `event_sequence` 是全局单调整数，是 Host event stream 的主 cursor。Section 10 的 `HostEventStream` 语义提到 "按全局 event_sequence 递增返回，携带 next event_sequence cursor"。

**为什么有问题**:

从 Section 10 和 Section 12 可以推导出 `cursor` 类型是 `int`（event_sequence 的数值），但 API 签名本身没有显式化这个类型。plan agent 需要从 Section 12 的 EventLog 定义反推 Section 10 的 API 参数类型。这在文档层面是跨 section 的隐含引用。

**影响**: plan agent 可能将 cursor 设计为其他类型（如 `str` token），导致 API 与 EventLog schema 不一致。

**建议改法**:

在 Section 10 的 `stream_run_events` 签名中明确：

```
stream_run_events(host, run_id, cursor: int | None) -> HostEventStream
  - cursor: 全局 event_sequence 游标，None 表示从头开始。
  - 返回: HostEventStream，携带 next event_sequence cursor。
```

**是否阻塞 phase planning**: **不阻塞**。

---

### Finding 13 [LOW] — `FollowupSnapshot` 的 `queue` 行为在无 active Run 时的语义未说明

**严重程度**: LOW

**位置**: Section 10（公共接口）、Section 11（Follow-up 与 Steer）

**当前写法**:

Section 11 说 `queue` 语义："当前 Session 有 active Run 时，follow-up 输入排队为后续 Run 的输入，不打断当前 active Run。当前 Session 没有 active Run 时，follow-up 可按普通 start_run 语义创建新 Run。"

Section 10 的 `FollowupSnapshot` 最小语义："accepted input ref、behavior、target run / queued run、current cursor。"

**为什么有问题**:

当 Session 无 active Run 且 `behavior=queue` 时，follow-up 变成立即启动的新 Run，而不是 queued Run。此时 `FollowupSnapshot` 应该反映 "新 Run 已创建并 RUNNING"，而不是 "已排队"。`target run / queued run` 字段需要表达这两种不同的结果。

此外，`SubmitFollowupRequest` 只有 `behavior: queue | steer`，没有 `queue_policy` 字段。当 `behavior=queue` 但 Session 有 active Run 时，follow-up 总是 queue。但如果 Session 有 active Run 且 admission policy 是 `reject`，queue 行为是否仍适用？还是 `queue` behavior 覆盖 admission policy？

**影响**: plan agent 需要在 FollowupSnapshot 中表达两种结果。如果没有明确的字段定义，调用方无法区分 "已立即开始" vs "已排队等待"。

**建议改法**:

在 Section 10 的 `FollowupSnapshot` 中增加状态区分：

```
FollowupSnapshot:
  accepted_input_ref
  behavior: queue | steer
  outcome: started | queued | steered   # 区分三种结果
  run_id   # 新创建或目标 Run 的 ID
  status    # 新 Run 的状态（RUNNING 或 QUEUED）
  cursor    # 当前 event_sequence cursor
```

**是否阻塞 phase planning**: **不阻塞**。

---

### Finding 14 [LOW] — `create_session` 幂等与 slot 重绑定的交互存在边缘歧义

**严重程度**: LOW

**位置**: Section 5（Session Slot）

**当前写法**:

```
create_session(..., bind_slot=true, scope, slot_key) 创建新 Session 后，
把 (scope, slot_key) 原子重绑定到新 Session；旧 Session 不删除，不改写 EventLog。
对同一 (scope, slot_key) 使用不同 client_request_id 调用
create_session(..., bind_slot=true) 表示不同的新建动作，允许创建更新的 Session 并重绑定 slot。
```

同时 `create_session` 按 `client_request_id` 幂等——"同一 client_request_id 重试必须返回同一个新 Session，不能重复创建"。

**为什么有问题**:

考虑以下序列：
1. `create_session(client_request_id=A, bind_slot=true, scope=S, slot_key=K)` → 创建 Session1，绑定 slot K → Session1。
2. `create_session(client_request_id=A, bind_slot=true, scope=S, slot_key=K)` → 幂等，返回 Session1（不重复创建，不重复绑定）。
3. `create_session(client_request_id=B, bind_slot=true, scope=S, slot_key=K)` → 创建 Session2，重绑定 slot K → Session2。

现在 slot K 指向 Session2。Session1 仍在，状态为 OPEN。

4. `create_session(client_request_id=A, bind_slot=false, scope=S)` → 按幂等规则应返回 Session1。但此时 Session1 已不被 slot K 绑定——`ensure_session(scope=S, slot_key=K)` 返回 Session2。

问题：步骤 4 中 `create_session(client_request_id=A)` 的 scope 参数 `S` 与步骤 1 相同，但没有 slot_key（bind_slot=false）。`client_request_id=A` 的幂等映射是否仅依赖 `client_request_id`，还是依赖 `(client_request_id, scope)`？

如果仅依赖 `client_request_id`，则步骤 4 返回 Session1——即使 Session1 与步骤 4 的 scope 参数不完全匹配。如果依赖 `(client_request_id, scope)`，步骤 4 的 scope 不匹配步骤 1——应该返回错误（`idempotency_conflict`）还是创建新 Session？

当前设计没有明确 `create_session` 的幂等键范围。

**影响**: plan agent 需要定义幂等键的精确边界。这是一个边缘场景但涉及 Session slot 和幂等两项核心不变量。

**建议改法**:

在 Section 5 的幂等不变量中明确 `create_session` 的幂等键：

```
create_session 幂等键: (client_request_id)
  - 不依赖 scope 或 slot_key。
  - 重试时忽略 scope/slot_key/bind_slot 参数差异，返回已创建的 Session。
  - 如果需要不同的 scope/slot_key，使用不同的 client_request_id。
```

或：

```
create_session 幂等键: (client_request_id, scope)
  - scope 参数变化时视为不同请求，允许创建新 Session。
  - 这允许同一 client_request_id 在不同 scope 下创建不同 Session。
```

**是否阻塞 phase planning**: **不阻塞**。这是一个边缘场景，但 Session API phase 的 plan 应覆盖此决策。

---

## 过度设计 / 冗余设计评估

| 检查项 | 评估 |
|--------|------|
| 29 个 canonical event types | **合理**。每个 event type 有明确语义和独立的状态机角色，没有为了"完整"而存在的冗余事件。 |
| 语义级重复工具调用治理五级 policy | **合理但需注意**。`allow`/`reuse`/`hint`/`require_justification`/`hard_stop` 五级在架构上合理。但第一版实现应优先完成 `allow`/`reuse`/`hard_stop` 三级，`hint` 和 `require_justification` 可在后续 phase 实现。Section 17.1 已暗示第一版可简化（"第一版可以只实现 run-level / session-level 的 deterministic duplicate key"）。 |
| TruncationManager cursor/scope_token 设计 | **合理**。cursor + scope_token + durable descriptor 的三层设计虽然不是第一版最简方案，但对远程执行和跨 restart 恢复场景是必要的。不算过度设计。 |
| Tool trace hot/cold storage (Section 13.1) | **略有过度**。JSON + JSONL 双存储、冷热分离、retention policy、按 run/日期分片——这些是 production 级别的设计但对于第一版可能过于详尽。不过它不增加核心治理的复杂度（它是 projection，不是真源），所以风险可控。 |
| Context governance proactive + reactive 双触发 | **合理**。两条路径覆盖了 "Host 预判" 和 "Engine 报告" 两种场景，不冗余。 |
| HostPolicyProviderSet 七大 policy provider | **合理**。每个 provider 有明确的治理职责，没有重叠。如果第一版某些 policy 不需要（如 cancel policy 只有 graceful mode），可以实现为 no-op provider。 |

**结论**: design.md 没有显著的过度设计或冗余设计。核心设计的复杂度与生产级买方财报分析 Agent 的需求匹配。

---

## 设计不足 / 缺失评估

| 检查项 | 评估 |
|--------|------|
| 数据库 migration 策略 | **缺失**。SQLite schema 演进没有提及。属于 Section 9 应覆盖的运维架构。 |
| 数据库备份策略 | **缺失**。Section 9 没有提及备份。 |
| graceful shutdown 的具体 timeout | **合理缺失**。Section 26 明确 "具体 shutdown grace timeout 属于 implementation phase"。 |
| 多进程 session slot 的跨进程可见性 | **隐含**。Session slot 存在 SQLite 中，多进程共享。但 `ensure_session` 的原子性在多进程下是否完全正确，依赖 SQLite 事务和唯一约束——这在 Section 8 已覆盖。 |
| EngineEvent 回传的 wire format | **合理缺失**。Section 16 明确 "design 定义 remote semantic contract，不定义 wire protocol"。 |
| memory projection 的更新时机 | **缺失**。Section 23 定义了 memory 结构和消费 canonical facts 的原则，但没有定义何时触发更新（每个 EventLog append？每个 terminal event？batch？）。 |
| Provider request 的重试/fallback | **合理缺失**。属于 Engine/Runner 范畴，不在 Host design 范围。 |

---

## 剩余风险评估

以下风险在 design.md 当前状态下仍未完全覆盖，但不应阻塞 phase planning：

| # | 风险 | 影响范围 | 归属 Phase | 缓解措施 |
|---|------|---------|-----------|---------|
| R1 | 远程 at-least-once 执行（Finding 3） | RemoteProxy、外部工具副作用 | Remote phase 或首个支持 remote 的 phase | 在 relevant phase plan 中明确工具级幂等要求 |
| R2 | Token 估算器精度影响 proactive compact 效果（Finding 11） | Context governance | Context governance phase | Phase plan 需包含 token 估算器精度评估和降级策略 |
| R3 | 多进程 SQLite 并发写入性能 | Admission、EventLog append | 首个涉及 SQLite 的 phase | 需在 phase 实现后做并发写入性能测试 |
| R4 | RECOVERING 状态在无上限时的 session slot 泄漏（Finding 1） | Session active slot | Recovery phase | Phase plan 需包含 max recovery attempts |
| R5 | Outbox delivery 的外部 channel（微信、Web）配置和协议 | Outbox delivery | Outbox phase（可能在 v1 之后） | 第一版可仅实现 internal fanout |
| R6 | `fetch_more` cursor 在跨 Attempt（steer/resume/replay）后的可恢复性 | TruncationManager、RunInputBuilder | ToolRuntime phase | Phase plan 需包含跨 Attempt cursor recovery 测试 |
| R7 | 跨进程 dispatch ownership 判断（Finding 9） | Recovery scan | Recovery phase | Phase plan 需明确第一版的跨进程恢复策略 |

---

## 最终判定：Ready to Drive Phase Planning（有条件）

`docs/host/design.md` 在吸收了前序三轮 review 的修正后，已成为一份高质量的 Host 架构真源。核心不变量表述精确，状态机定义完整，边界硬约束充分。与初版 design.md（前序 review 时的版本）相比，当前版本在可被 plan agent 直接翻译为 typed code and tests 的标准上有显著提升。

**必须收束才能进入第一个 phase plan 的 blocking findings**:

1. **Finding 1**: 缺少 recovery/retry/replay 最大尝试次数上限 → 补 attempt counter 和 circuit breaker 约束。
2. **Finding 2**: `WAITING` 状态 Run 的 cancel 迁移路径缺失 → 补完整迁移路径和 EventLog 序列。
3. **Finding 3**: 远程 dispatch at-least-once 执行风险 → 如果不做远程执行则降级为 HIGH；如果做则必须补风险边界声明和缓解策略。

**建议在对应 phase 前收束的 high findings**:

4. **Finding 4**: `CANCELLING -> WAITING` 路径语义（cancel/attempt phase）。
5. **Finding 5**: 语义级重复治理与业务边界（ToolRuntime phase）。
6. **Finding 6**: Replay 工具结果 staleness（replay phase 或 memory/context phase）。
7. **Finding 7**: 公共接口错误语义（Session/Run/API phase）。

**可在 phase plan 中覆盖的 medium/low findings**: Finding 8-14 及剩余风险 R1-R7 均可在对应 phase 的 plan 或 design.md 章节细化中解决，不阻塞 phase 编排。

**总评**: design.md 已具备作为后续 phase plan 主真源的条件——前提是先收束 3 个 blocking findings。每个 blocking finding 的修正范围相对可控（状态机补边、架构声明补充），不会触发大范围重写。
