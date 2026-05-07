# Host 接口与架构开放讨论札记

## 1. 文档状态

本文档记录 Host 接口与架构开放讨论中的阶段性共识。它不是最终设计文档，
不代表已经可以进入实现；后续设计仍需要参考 OpenClaw、Codex、Claude Code 等优秀
Agent 的交互模型与运行治理经验，再收敛成 `docs/host/design.md` 的正式决策。

## 2. 当前讨论基线

### 2.0 多进程并发硬约束

Host 设计必须支持多进程并发。

该约束会影响：

- `Session` 写入顺序与同一 session active run 仲裁。
- `Run` 状态迁移的原子性。
- internal `Attempt` 的 lease / owner / fencing token。
- cancel request 的跨进程可见性。
- `RunEvent` / `EventLog` 的 append-only 顺序与订阅一致性。
- Worker / ToolRuntime 资源的 owner 归属与异常进程退出后的恢复。
- startup recovery 对 orphan run、stale attempt、stale worker、stale tool lease 的调和。

因此，Host 内部真源不能只依赖单进程内存锁；任何影响外部可见状态、恢复、取消或并发仲裁的事实，
都必须有跨进程一致的持久化或等价协调机制。具体实现方案仍待讨论。

### 2.1 对外概念应尽量少

Host 对外暴露的概念应贴近用户与上层真正理解的稳定对象，而不是 Host 内部为了完成执行
所需的机制。

当前建议先围绕三个外部对象讨论：

- `Session`：一次“聊天记录”或会话上下文。
- `Run`：某个 `Session` 里的一次带上下文聊天。
- `RunEvent`：某个 `Run` 的事件事实。

### 2.2 Session 语义

`Session` 相当于一条聊天记录。

它应表达：

- 这条聊天记录是谁创建的。
- 当前是否仍可写入。
- 历史消息 / turn 如何读取。
- 客户端如何读取聊天记录，包括 assistant answer、tool 摘要、warnings/errors 和思考过程展示字段。
- 是否可以清空或关闭。
- 同一条聊天记录中 Run 的顺序与上下文一致性。

`Session` 不应泄漏 Agent / Runner / EngineWorker / ToolRegistry 等执行细节。

### 2.3 Run 语义

`Run` 相当于聊天记录中的一次“带上下文的聊天”。

它应表达：

- 用户在某个 `Session` 中提交的一次输入。
- Host 为完成这次输入而维护的状态。
- 最终成功、失败或取消。
- 可观察事件流。

`Run` 是对外可见的执行单位；Host 内部可以为了完成这个 Run 发起多次尝试，但这些尝试
不应直接成为普通调用者必须理解的公共接口。

### 2.4 Attempt 作为内部概念

为解释自动恢复，当前引入一个内部概念：

```text
Public Run = 一次用户聊天
Internal Attempt = 为完成这个 Run 发起的一次 Engine 执行尝试
```

示例：

```text
Run
  attempt_1 timeout / interrupted
  Host 自动创建 attempt_2
  attempt_2 继续完成同一个 Run
```

对 Service / UI 来说，仍然是同一个 Run。

### 2.5 Resume 应自动化

不应对外暴露 `resume_run`。

恢复应是 Host 为完成当前 Run 而执行的内部策略。上层最多观察到 Run 状态或事件变化，
例如：

- `running`
- `recovering`
- `succeeded`
- `failed`
- `cancelled`

但上层不应直接操作：

- `PendingTurn`
- `resume lease`
- `record_resume_attempt`
- `release_resume_lease`
- `resume_pending_turn_stream`

这些都属于 Host 内部恢复治理。

### 2.6 OLD 中不应单独外露的能力

以下 OLD 能力可作为可靠行为证据，但不应直接成为 Host 对外接口：

- Agent 执行托管。
- Agent / Runner 构造。
- CancellationBridge / cancellation token 映射。
- Deadline watcher。
- Pending turn / resume lease。
- Event bus。
- EngineWorker / LocalProxy / RemoteProxy / RemoteStub。
- ToolExecutor 代持。
- Concurrency permit。

这些能力可以存在，但应作为 `Run` 管理、执行环境治理或 Host 内部基础设施。

### 2.7 事件总线的口径

事件总线不应作为独立业务能力暴露。

对外应表达为：

```text
订阅 / 读取某个 Run 的事件
```

而不是：

```text
操作 EventBus
```

`EventBus` 可以作为 Host 内部实现机制，但公共接口应围绕 `RunEvent`。

### 2.8 取消治理的口径

取消可以是 Run 的动作或 Host 对 Run 的动作，但取消治理本身不应外露。

对外可讨论的接口形态是：

```text
cancel_run(run_id)
```

内部治理包括：

- 写入取消意图。
- 通知当前 attempt / worker。
- 映射到 cancellation token。
- 等待 Engine / ToolExecutor 协作退出。
- 超时升级或标记 lost。
- 收敛 Run 终态。

这些内部步骤不应变成普通调用者必须编排的接口。

## 3. 候选 Host 架构分解

当前开放讨论中的候选架构如下，尚未定稿为包、类或代码边界：

```text
UI -> Service -> Host

Host
  - SessionManager
  - RunManager
  - RunSupervisor
  - AttemptSupervisor
  - RunInputBuilder / MemoryManager
  - ToolRuntime
  - EventLog
  - Policy/Governance
  - WorkerProxy
      - LocalProxy -> EngineWorker
      - RemoteProxy -> RemoteStub -> EngineWorker

EngineWorker
  - Engine
  - Runner
  - ToolExecutor
```

当前讨论理解：

- `SessionManager`：管理聊天记录元数据、写入顺序、关闭 / 清空等 session 级状态。
- `RunManager`：管理对外可见的 Run 状态、创建、查询、取消请求和结果读取。
- `RunSupervisor`：协调一次 Run 的完整生命周期，对外隐藏内部 attempt。
- `AttemptSupervisor`：管理内部 attempt 的启动、失败、恢复、重试、取消和资源释放。
- `RunInputBuilder / MemoryManager`：从 Session、transcript、memory、tool facts 构造上下文。
- `ToolRuntime`：Host 侧工具运行治理边界，包括生命周期、审计、截断、超时和取消；
  具体业务权限与业务规则不进入 Host / Engine。
- `EventLog`：Run 的 append-only 事件事实源；EventBus 若存在，只是推送实现。
- `Policy/Governance`：并发、审批、沙箱、网络、路径、恢复策略等治理规则。
- `WorkerProxy`：Host 到执行环境的适配边界。
- `EngineWorker`：Host capability，在选定执行环境中承载 Engine、Runner 和 ToolExecutor。

该架构强调：Host 对外不暴露 Agent / Runner / ToolExecutor / EventBus / PendingTurn 等内部机制。

## 4. 接下来开放讨论的问题

后续可以先讨论：

- 从头开发时，Host 最小 public interface 应有哪些方法。
- `Session` 的状态是否只保留用户可理解状态，内部屏障状态是否隐藏。
- `Run` 是否需要暴露 `recovering`，还是只作为事件出现。
- `Attempt` 是否需要持久化；若持久化，是否只作为 Host 内部表。
- 取消是立即返回取消请求已登记，还是等待 Run 收敛到 terminal。
- 新消息到达时，如果同一 Session 有未完成 Run，Host 应该 reject、queue、还是自动等待。
- RunEvent 应该是 pull、stream、订阅，还是三者都支持但统一事实源。
- ToolRuntime、memory、context compaction 如何挂在 Run 内部，而不污染外部接口。

### 4.1 Artifact 与 Evidence 的边界

`artifact_refs` 不代表证据。二者需要拆开：

- `artifact_refs`：Run 产生或引用的稳定产物索引，例如报告、表格、图片、下载物、
  trace bundle 或导出文件。
- `evidence_refs` / `source_refs`：回答依据、引用来源、证据锚点或 provenance。

Host 只保存通用不透明引用和必要定位信息，不解释业务含义。证据如何产生、验证和映射到具体材料，
由业务工具、输出契约或 evidence projection 负责。

## 5. Steer 与 Session 并发讨论

### 5.1 Steer 是 Run 级输入

参考 Codex 的 `Steer` 体验，同一个 `Session` 里已有 active `Run` 时，新输入不一定
代表新一轮聊天。它也可能是用户对当前 active `Run` 的追加引导。

当前讨论口径：

```text
Session = 聊天记录
Run = 当前一次任务 / 聊天执行
Steer = 用户对 active Run 的追加引导
Next Run = active Run 结束后的下一次聊天
```

因此 `Steer` 应建模为 `Run` 级输入，而不是新的 `Session` 消息。

### 5.2 Active Run 存在时的新输入分类

当同一个 `Session` 已存在 active `Run`，新输入可能有四种语义：

1. `steer current run`
   - 用户看到 Agent 方向不对，追加约束或修正。
   - 不创建新 `Run`。
   - 追加为 active `Run` 的 steer input。
   - Host 在安全边界应用，例如下一轮模型调用前、当前工具完成后，或当前 attempt
     可中断重启时。

2. `queue as next run`
   - 用户发起下一个问题，不是修正当前任务。
   - 等 active `Run` terminal 后再开始。
   - 保持 `Session` 聊天记录顺序。

3. `cancel and replace`
   - 用户明确要求停止当前任务并改做新任务。
   - Host cancel 当前 `Run`，再启动新 `Run`。

4. `reject`
   - 策略不接受同一 `Session` 下 active `Run` 期间的新输入。

### 5.3 接口形态候选

候选 A：极简统一入口。

```python
host.submit_session_input(
    session_id,
    input,
    mode="auto" | "steer" | "queue" | "replace",
)
```

Host 根据 active `Run`、`mode` 和策略决定 start / steer / queue / reject。

候选 B：显式动作入口。

```python
host.start_run(session_id, input)
host.steer_run(run_id, input)
host.enqueue_run(session_id, input)
host.cancel_run(run_id)
```

当前倾向还未决定。统一入口可以减少 Service 分支；显式入口更清晰，但容易把策略判断推给
Service。

### 5.4 Steer 的治理约束

`Steer` 不能随意插入上下文，需要 Host 治理：

- 只能作用于 active `Run`。
- 必须进入 append-only event log，例如 `run_steer_received`、`run_steer_applied`。
- 如果当前正在执行不可中断工具，先记录 pending steer。
- 如果当前模型调用可中断，可以取消当前 internal attempt，并用 steer 后上下文启动新 attempt。
- 如果 `Run` 已 terminal，steer 应降级为新 `Run` 或 reject，具体策略待定。
- 多条 steer 必须保持顺序，不能覆盖。

### 5.5 内部事实模型草案

可以把同一 `Run` 的输入事实拆成：

```text
RunInput
  - initial_user_message
  - steer_message
  - queued_user_message
  - cancellation_request
```

该模型仍是讨论草案，不代表代码契约。

## 6. 能力边界补充讨论

### 6.1 Scene Preparation 可作为外围能力

当前讨论倾向：`Scene Preparation` 可以考虑不放在 Host 核心内。

这里的“外围”不是否定现有设计，而是架构上可以让它成为一个独立组件。
它可以沿用现在的设计思路，但不一定内嵌在 Host 核心对象里。

Host 核心应聚焦：

- `Session`
- `Run`
- `Attempt`
- `RunEvent`
- 执行环境治理
- 自动恢复与取消收口

是否彻底外移仍待讨论。需要继续判断：

- scene preparation 是否需要 Host 内部状态，例如 session transcript、memory、tool facts。
- scene preparation 是否只是把上层业务请求整理成 Host 可执行 input。
- 如果放在 Host 外，是否会让 Service 直接理解 Engine contracts。

### 6.2 Reply Outbox 重要，但应与 Run 隔离

因为未来存在 WeChat、Web 等 UI / delivery channel，`Reply Outbox` 仍然是重要能力。

当前讨论约束：

- `Reply Outbox` 不应消失。
- `Reply Outbox` 不应绑死为 `Run` 生命周期的一部分。
- `Run` 负责产出执行事实与结果。
- `Reply Outbox` 负责外部信道的投递、claim、delivered / failed、幂等 key 与重投治理。
- `Reply Outbox` 可以引用 `run_id` / `session_id`，但不应由 Run 状态机直接内嵌。

换句话说，`Run` 与 `Reply Outbox` 应该是通过事件 / 结果投影连接的两个子系统，而不是一个
混合状态机。

### 6.3 并发治理不能丢，但 OLD 实现需要重设

并发治理能力必须保留，但不应机械迁移 OLD 实现。

当前讨论方向：

- OLD 并发治理实现不作为 NEW 设计真源。
- NEW 应改成“使用方等待事件”的模型，且该能力是独立能力，不从属于 Host Run。
- lane 本质是一个具名、跨进程可等待的信号量：`Lane = named semaphore`。
- lane 跟 Host、Run、Agent、Tool、Service 或具体业务都没有语义绑定。
- lane 更适合放在 `dayu.runtime` 或等价层中立 infra 包里，而不是 Host 内部。
- Host 只是 lane 的使用方之一；Service、Fins downloader、Web delivery 等也可以是使用方。
- 并发 lane 可被 Agent Run 和非 Agent 操作共同使用，但不要求非 Agent 操作进入
  Host 的取消 / 恢复 / Run 状态机。
- 并发能力应尽量独立，不和 Run /
  Attempt / Worker 其它治理混在一起。
- 并发状态应是可观察事实，而不是内部黑盒阻塞。
- 调用方不应自己实现轮询或猜测等待时机。
- 简化模型可以先理解为：

```text
wait event  ≈ acquire 到 lane
干活干活
reset event ≈ release lane
```

待展开问题：

- `start_run` 在并发不足时是返回 queued run，还是等待 permit 后返回 running run。
- 是否需要 `run_queued`、`run_waiting_for_capacity`、`run_capacity_acquired` 等事件。
- 使用方等待的是 `RunEvent`、capacity event，还是 Host 提供的 wait handle。
- 多进程下 permit / queue / wakeup 如何保证公平性与 fencing。

### 6.4 Host / Engine 不懂业务

Host 和 Engine 都是业务无关层，不懂财报业务，也不应承载业务知识。

重要约束：

- Host 不应理解 fins/doc/web 的业务语义。
- Engine 不应理解 fins/doc/web 的业务语义。
- ToolRuntime 的运行治理不要和具体 tool 权限 / 业务权限混在一起讨论。
- 财报文档必须通过 `dayu.fins.storage`，但该约束应由业务工具 / ToolRuntime
  的边界保证，而不是让 Host / Engine 直接内嵌财报知识。

### 6.5 Conversation Memory 以 OLD issue #48 为强参考

Conversation Memory 当前讨论倾向：OLD 的设计令人满意，后续 NEW 设计应以
`https://github.com/noho/dayu-agent/issues/48` 为强参考。

该 issue 的关键设计点：

- `pinned_state` 是会话灵魂，永远全量渲染，不参与 token 池竞争。
- 工具结果即事实，结构化 tool facts、evidence anchors、source references 不能被 LLM
  二次摘要丢失精度。
- 最近 N 轮 raw turn 是追问连续性的保底，不是上限。
- 历史 memory 使用单总池，而不是 working / episodic 两个独立预算池。
- memory 应克制，把大部分上下文窗口留给当前任务所需的外部材料、检索结果和局部上下文。
- compaction 以 context ratio 触发，不再以轮数触发。
- episode summary 通过 confirmed facts 与 pinned_state 支撑跨轮一致性和反幻觉。

后续讨论要点：

- Conversation Memory 属于 Host 上下文治理，不属于 Engine。
- MemoryManager 可以是 Host 内部能力，但不应污染 Host 最小 public interface。
- RunInputBuilder 应消费 memory 结果来构造 Run / Attempt 输入。
- 具体 schema 仍需按 NEW 全新 schema 起库处理，不做旧库兼容读取。

### 6.5.1 客户端读取聊天记录与思考过程

客户端存在查看聊天记录的需求，且聊天记录需要包含思考过程展示字段。

当前讨论口径：

- `Session` 需要提供面向客户端的 transcript / timeline read model。
- read model 应包含用户输入、assistant answer、可展示 reasoning、tool 摘要、warnings/errors、
  时间、关联 run_id 等。
- reasoning 可作为展示字段持久化，但在设计上必须与运行态上下文隔离，没有机会流回
  `RunInputBuilder / MemoryManager` 或参与 `RunInput` 重放。
- 运行态上下文由 `RunInputBuilder / MemoryManager` 决定，不等同于客户端 transcript 全量回放。
- 客户端读模型和 Host 内部 memory / context 构造必须分离，避免为了展示需求污染 Agent 输入。

待讨论：

- transcript 是按 turn 组织，还是按 event timeline 组织，或两者都是 EventLog 的 projection。
- reasoning 展示字段的保留策略、清空策略和权限控制。
- tool 摘要与 tool facts 的边界：展示摘要不等于可供后续推理的事实真源。

### 6.6 Reply Outbox 与 RunResult 后续实施时再细化

`Reply Outbox` 与 `RunResult` 的关系先不在当前架构讨论里展开。

当前只保留粗约束：

- Reply Outbox 重要。
- Reply Outbox 与 Run 隔离。
- 二者如何通过 result projection / delivery projection 连接，留到实施
  Reply Outbox 阶段再讨论。

### 6.7 Attempt lease / fencing 后移到实现设计

Attempt lease / fencing 属于重要建议，但已经接近实现和多进程一致性细节。

当前只记录建议：

- 多进程恢复时需要防止旧进程迟到写入污染新 owner 的 Run。
- 具体 lease、owner、fencing token、attempt event 写入规则，留到实现阶段详细讨论。

### 6.8 Steer 可后加

当前讨论认为 `Steer` 可以先不纳入第一版。

理由：

- `Steer` 是 active Run 上的追加输入能力。
- 只要 `Run` / `RunEvent` / `Attempt` 的抽象干净，后续增加 `steer_received` /
  `steer_applied` 等事件不应破坏主架构。
- 第一版可以先保证 Session / Run / 自动恢复 / 并发治理主链路。

### 6.9 非 Agent Operation 倾向不属于 Host

当前倾向：非 Agent Operation 不属于 Host 核心。

当前进一步澄清：

- 非 Agent 操作不需要 Host 的取消治理。
- 非 Agent 操作不需要 Host 的恢复治理。
- 非 Agent 操作需要的并发能力可以通过独立 lane 机制获得。
- 因此，不需要为了复用取消 / 恢复 / RunRegistry 而把非 Agent 操作纳入 Host。

待讨论方向：

- 保持 Host 核心只服务 Session / Run。
- lane 并发机制作为独立能力，由 Agent Run 和非 Agent 操作按需使用。
- 不把 OLD `run_operation_sync/stream` 直接作为 Host 第一版 public interface。

## 7. 设计收束讨论

### 7.1 EventLog 第一阶段就做

当前确认：`EventLog` 要做，而且应作为第一阶段 Host 设计的一部分。

当前口径：

- `EventLog` 是 Run 的 append-only 事实账本。
- `EventBus` 若存在，只是把 `EventLog` 的事实推送给订阅方的机制。
- UI / Web / WeChat / debug / recovery 都应基于可回放的 Run events，而不是只依赖
  单进程内存事件流。
- 多进程场景下，`RunEvent` 必须有跨进程一致的顺序与去重标识。

### 7.1.1 Tool Trace / Audit 通过 Event Projection 派生

Engine 迁移时已经确认：tool trace 不属于 Engine。Engine 只 emit 强类型 `EngineEvent`；
Host / EngineWorker 接收事件后，应先翻译为可治理的 `RunEvent` 并写入 EventLog，再由
projection / observer 派生 tool trace、audit、metrics、alerting、debug sampling、Session timeline、
Reply Outbox 等视图或外部记录。

设计口径：

- Engine 不依赖 `ToolTraceRecorder`，不写 JSONL，不决定 trace schema。
- observer 默认消费 EventLog，不直接消费进程内 `AsyncIterator[EngineEvent]`，避免进程崩溃导致
  trace / audit 丢失。
- 每个 observer 需要稳定 `observer_id`、cursor / checkpoint、schema version 和幂等写入。
- projection 采用 at-least-once 语义，失败可重试，projection lag / failure 可观测。
- tool trace 是 observer 的一种，不是 ToolRuntime 或 Engine 的内嵌落盘逻辑。
- audit 若被 policy 标记为 hard-gate，需要作为 required projection 明确进入状态机 /
  recovery 设计，不能隐式混进 Engine 或 ToolExecutor。

OLD `ToolTraceRecorder` / `JsonlToolTraceStore` / `tool_trace_v2` 可以作为 Host observer 默认实现素材，
但 NEW trace schema 真源留到 Host / observability 阶段确认。

### 7.2 start_run 倾向 async

当前倾向：`start_run` 采用 async 接口更好。

理由：

- 启动 Run 需要写入 Session / Run / EventLog 等跨进程真源，天然可能涉及 I/O。
- H1 可能先用本地实现，但远期 RemoteProxy / RemoteStub 启动 worker 也是异步边界。
- async 接口便于在 start 阶段完成必要的原子登记、事件写入和 worker 启动准备。
- 不要求 `start_run` 等待 Run 完成；它只负责创建并启动 Run，返回 `RunView`。

当前候选：

```python
async def start_run(session_id: str, input: RunInput, options: RunOptions) -> RunView: ...
```

流式观察通过独立接口：

```python
def stream_run_events(run_id: str, *, after: RunEventCursor | None = None) -> AsyncIterator[RunEvent]: ...
```

### 7.3 Session 状态机候选

目标：表达聊天记录是否可写，不泄漏内部恢复细节。

候选状态：

```text
ACTIVE
CLOSING
CLOSED
CLEARING
BLOCKED
```

含义：

- `ACTIVE`：允许创建新 Run、接受 steer / queue 等输入。
- `CLOSING`：关闭中，拒绝新输入，等待内部收口。
- `CLOSED`：终态，不再接受写入。
- `CLEARING`：清空历史中，拒绝新输入。
- `BLOCKED`：清空、恢复或持久化调和失败后的保护状态，需要管理动作解除。

待讨论：

- `CLOSING` 是否第一版需要，还是 `close_session` 直接原子转 `CLOSED`。
- `BLOCKED` 是否命名为 `ERROR` / `REPAIR_REQUIRED` 更清晰。

### 7.4 Run 状态机候选

目标：Run 是对外可见的一次聊天执行；自动恢复不泄漏成 `resume_run`。

候选状态：

```text
CREATED
QUEUED
RUNNING
RECOVERING
SUCCEEDED
FAILED
CANCELLING
CANCELLED
LOST
```

合法主路径：

```text
CREATED -> QUEUED -> RUNNING -> SUCCEEDED
CREATED -> QUEUED -> RUNNING -> FAILED
CREATED -> QUEUED -> RUNNING -> CANCELLING -> CANCELLED
CREATED -> QUEUED -> RUNNING -> RECOVERING -> RUNNING -> SUCCEEDED / FAILED / CANCELLED
CREATED / QUEUED / RUNNING / RECOVERING -> LOST
```

含义：

- `CREATED`：Run 事实已登记，但尚未进入容量等待或执行。
- `QUEUED`：等待 lane / policy / worker capacity。
- `RUNNING`：当前存在 active attempt。
- `RECOVERING`：Host 正在为同一个 Run 自动恢复或重建 attempt。
- `SUCCEEDED`：终态，产生成功结果。
- `FAILED`：终态，业务或执行失败，不能自动恢复。
- `CANCELLING`：取消请求已接受，等待 active attempt 协作收口。
- `CANCELLED`：终态，取消已收口。
- `LOST`：终态或半终态候选，Host 无法确认执行结果，需要后续讨论是否可人工调和。

当前倾向：

- 第一版保留 `QUEUED`，因为并发治理会通过 wait event / lane 容量影响 Run。
- 第一版保留 `RECOVERING`，因为自动 resume 是 Host 内部策略，但对外可观察。
- `LOST` 是否进入第一版取决于多进程 orphan recovery 是否 H1 落地；否则可先后移。

### 7.5 Attempt 状态机候选

目标：Attempt 是 Host 内部执行尝试，用于多进程恢复、自动 resume、worker 接管和 fencing。
它不作为普通调用方 public interface。

候选状态：

```text
CREATED
LEASED
STARTING
RUNNING
CANCELLING
SUCCEEDED
FAILED
CANCELLED
STALE
LOST
```

合法主路径：

```text
CREATED -> LEASED -> STARTING -> RUNNING -> SUCCEEDED
CREATED -> LEASED -> STARTING -> RUNNING -> FAILED
CREATED -> LEASED -> STARTING -> RUNNING -> CANCELLING -> CANCELLED
CREATED / LEASED / STARTING / RUNNING / CANCELLING -> STALE
CREATED / LEASED / STARTING / RUNNING / CANCELLING -> LOST
```

含义：

- `CREATED`：attempt 事实已登记。
- `LEASED`：某个 owner 获得执行权。
- `STARTING`：worker / EngineWorker 启动中。
- `RUNNING`：Engine 正在执行。
- `CANCELLING`：attempt 收到取消信号。
- `SUCCEEDED`：attempt 成功完成，Run 可进入 `SUCCEEDED`。
- `FAILED`：attempt 失败；Run 可能 `RECOVERING` 或 `FAILED`。
- `CANCELLED`：attempt 已取消；Run 可能 `CANCELLED` 或按策略恢复。
- `STALE`：owner 失活或 lease 过期，另一个进程可尝试接管。
- `LOST`：无法判断 attempt 结果，需按 recovery policy 处理。

待实现阶段细化：

- lease / fencing token。
- 旧 owner 迟到写入的拒绝规则。
- attempt event 与 run event 的映射。
- stale attempt 是否必然触发 Run `RECOVERING`。

### 7.5.1 Replay 能力

Replay 是重要能力，用于模型返回脏数据时重新执行或修复输出。

当前讨论口径：

- Host 自己不懂业务，不能直接判断什么是“脏数据”。
- `Output Validation` 与 `Replay Execution` 分离。
- 脏数据判断由外部 `OutputContract` / `Validator` / Service 侧契约组件完成。
- Host 只消费 validator 返回的结构化 replay decision。
- Replay 应是 Run 内部的修复 / 恢复机制，而不是暴露旧 Agent 实例或旧 Runner 状态。
- Replay 的目标是处理模型输出脏数据，例如解析失败、空输出、格式不符合 contract。
- Replay 可以复用同一个 Run 的上下文事实，但应创建新的 internal attempt。
- Replay 必须绑定新的 cancellation token / worker execution context，不能复用旧 attempt 的
  Agent / Runner 实例。
- Replay 应进入 EventLog，例如 `run_replay_requested`、`attempt_replay_started`、
  `attempt_replay_succeeded`、`attempt_replay_failed`。
- Replay 需要有次数上限和策略，避免无限修复循环。

待讨论：

- Replay 由 Service / OutputValidator 判断脏数据后触发；Host 不内嵌业务判断。
- `OutputValidator` 可以返回通用结构，例如 `accepted` / `replay_required` / `failed`、
  `reason`、`repair_instruction`、`replay_policy`。
- Replay 是否允许禁用工具，逼迫模型只输出修复文本。
- Replay 使用同一个 Run 还是创建子 Run；当前倾向是同一个 Run 下新的 attempt。
- Replay 结果如何覆盖或废弃前一次脏结果，EventLog 必须保留审计事实。

### 7.6 Reply Outbox 状态机候选

目标：Reply Outbox 独立管理外部信道投递，不并入 Run 状态机。

候选状态：

```text
PENDING
READY
CLAIMED
DELIVERING
DELIVERED
FAILED
RETRY_WAITING
EXPIRED
CANCELLED
DEAD
```

合法主路径：

```text
PENDING -> READY -> CLAIMED -> DELIVERING -> DELIVERED
PENDING -> READY -> CLAIMED -> DELIVERING -> FAILED
PENDING -> READY -> CLAIMED -> DELIVERING -> RETRY_WAITING -> READY
PENDING / READY / CLAIMED / DELIVERING / RETRY_WAITING -> EXPIRED
PENDING / READY / CLAIMED / DELIVERING / RETRY_WAITING -> CANCELLED
FAILED -> DEAD
```

含义：

- `PENDING`：outbox record 已创建，但投递内容或目标尚未完全 ready。
- `READY`：可被 delivery worker claim。
- `CLAIMED`：某个 delivery worker 获得投递权，防止多进程重复投递。
- `DELIVERING`：正在调用外部信道。
- `DELIVERED`：终态，外部信道确认已投递。
- `FAILED`：一次或最终投递失败；是否可重试由 retry policy 决定。
- `RETRY_WAITING`：等待下次重试窗口。
- `EXPIRED`：超过保留期或业务窗口，不再投递。
- `CANCELLED`：因 session 关闭、用户撤回或上层策略取消投递。
- `DEAD`：终态，重试耗尽或不可恢复失败。

设计约束：

- Reply Outbox 可以引用 `session_id`、`run_id`、`result_id` 或 delivery key，
  但不应成为 Run 状态机的一部分。
- claim / lease 必须支持多进程并发。
- delivery key 必须支持幂等，避免 WeChat / Web 重复投递。
- stale `CLAIMED` / `DELIVERING` 需要 cleanup 或 lease 过期回到 `READY` / `RETRY_WAITING`。
- Outbox event 可独立存在，或作为 delivery projection；具体留到实施 Reply Outbox 阶段细化。

### 7.7 Final Answer 到 Outbox 的可靠投影漏洞

必须防止 `final_answer` 已产生但 `ReplyOutbox` 未落库的丢失窗口。

风险流程：

```text
Run 产生 final_answer
标记 Run SUCCEEDED
进程在写 ReplyOutbox 前崩溃
```

结果：

```text
Run = SUCCEEDED
final_answer 已存在于事件 / 结果中
ReplyOutbox 没有记录
外部渠道永远收不到回复
```

硬约束：

- `Run final_answer` 到 `ReplyOutbox` 必须通过可靠投影连接。
- 不能依赖 best-effort 旁路写入。
- 如果 `RunResult` 或 `final_answer` event 已存在而 `ReplyOutbox` 缺失，系统必须能通过
  EventLog / RunResult reconcile 补出 Outbox。
- Outbox projection 必须幂等，避免重放时重复投递。

候选方案：

1. 同事务写入：

```text
append final_answer event
persist RunResult
create ReplyOutbox READY
mark Run SUCCEEDED
commit
```

2. EventLog / RunResult projection reconciler：

```text
append run_final_answer event
append run_succeeded event
projection worker 读取 final_answer / result
upsert ReplyOutbox by delivery_key
```

当前倾向：方案 2 更符合 Run 与 ReplyOutbox 隔离的设计。具体实现留到 Reply Outbox 阶段。
