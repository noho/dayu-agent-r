# Host 设计草稿

## 1. 文档状态

本文档是 Host 接口与架构设计草稿，供人工 review 和继续讨论。它收束当前已经达成的设计口径，
但还不是代码实施计划；进入实现前仍需要按阶段拆分 handoff 计划、测试清单和 review gate。

本文只描述 Host 的架构边界、对外接口口径、核心状态机和关键约束，不按 OLD 文件迁移。

## 2. 总体定位

Dayu 分层固定为：

```text
UI -> Service -> Host -> Engine
```

Host 是面向 Agent 聊天执行的运行宿主。Host 对外不暴露 Agent / Runner /
EngineWorker / ToolExecutor / EventBus / PendingTurn 等内部机制，而是围绕三个稳定对象：

- `Session`：一条聊天记录 / 会话上下文。
- `Run`：某个 `Session` 里一次带上下文的聊天执行。
- `RunEvent`：某个 `Run` 的 append-only 事件事实。

Host 内部可以为了完成一个 `Run` 发起多个 internal `Attempt`，但 `Attempt` 不作为普通调用方
public interface。

## 3. 硬约束

### 3.1 多进程并发

Host 必须支持多进程并发。Host 内部真源不能只依赖单进程内存锁。

任何影响外部可见状态、恢复、取消或并发仲裁的事实，都必须有跨进程一致的持久化或等价协调机制。
该约束至少覆盖：

- `Session` 写入顺序与 active run 仲裁。
- `Run` 状态迁移。
- internal `Attempt` owner / lease / fencing。
- cancel request 跨进程可见性。
- `RunEvent` / `EventLog` 顺序与去重。
- worker / tool runtime 资源 owner 归属。
- startup recovery 对 orphan / stale 状态的调和。

### 3.2 Host / Engine 不懂业务

Host 和 Engine 都是业务无关层，不懂财报业务，也不承载业务知识。

- Host 不理解 fins/doc/web 的业务语义。
- Engine 不理解 fins/doc/web 的业务语义。
- 财报文档必须通过 `dayu.fins.storage` 的约束由业务工具 / 工具边界保证，不应让
  Host / Engine 内嵌财报知识。
- ToolRuntime 的运行治理不要和具体 tool 权限 / 业务权限混在一起讨论；权限与业务规则
  应通过独立 policy / tool 侧契约表达。

### 3.3 非 Agent 操作不属于 Host

Host 核心只服务 `Session` / `Run`。非 Agent 操作不进入 Host 的取消、恢复或 Run 状态机。

非 Agent 操作若需要并发控制，应使用独立 lane 能力；不把 OLD `run_operation_sync` /
`run_operation_stream` 作为 Host 第一版 public interface。

### 3.4 Lane 是层中立能力

lane 本质是具名、跨进程可等待的信号量：

```text
Lane = named semaphore
```

lane 与 Host、Run、Agent、Tool、Service 或具体业务都没有语义绑定。lane 更适合放在
`dayu.runtime` 或等价层中立 infra 包里，而不是 Host 内部。Host 只是 lane 的使用方之一；
Service、Fins downloader、Web delivery 等也可以使用 lane。

lane 的最小正确性语义后续应在 `dayu.runtime` 设计中固定：

- acquire 返回 holder token / lease。
- release 必须携带 holder token / lease，避免释放他人持有的容量。
- 支持 timeout。
- 支持 TTL / heartbeat 或等价 stale holder cleanup。
- 公平性策略必须显式说明，例如 FIFO 或明确非 FIFO。
- 多进程实现不得退化为进程内 `asyncio.Semaphore`。

### 3.5 Fencing Token 语义

多进程 owner / lease 设计必须区分两类 token：

- `owner_token`：随机 secret，只用于证明调用方确实持有当前 owner capability；它不能作为 fencing
  token 使用。
- `fencing_token`：durable 全局单调递增 token，用于让共享资源拒绝旧 owner 的迟到请求。

P8 起 Host 必须提供全局单调 fencing token 分配能力。每次获得某个共享资源的 owner lease 时，
Host 都必须在 durable storage 中分配新的 `fencing_token`；后续写入、取消、resume、ack、delivery
或 checkpoint advance 等操作必须携带该 token，并由资源侧比较 / 校验 token 是否仍是当前 token。

该原则覆盖后续所有多进程共享资源：

- attempt owner。
- run lifecycle owner。
- session active run admission。
- wait record owner。
- outbox delivery owner。
- remote worker / remote attempt owner。
- observer claim owner。

实现不要求所有资源共用同一 row，但要求 token 值来自同一个 Host durable monotonic allocator，
或具备等价的跨进程全局单调语义。禁止把随机 `owner_token`、scope token、cursor token 或
进程内对象 id 当作 fencing token。

## 4. 候选架构

当前 Host 候选分解：

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
  - EventProjection / Observers
  - Policy/Governance
  - WorkerProxy
      - LocalProxy -> EngineWorker
      - RemoteProxy -> RemoteStub -> EngineWorker

EngineWorker
  - Engine
  - Runner
  - ToolExecutor
```

职责口径：

- `SessionManager`：管理聊天记录元数据、写入顺序、关闭 / 清空等 session 级状态。
- `RunManager`：管理对外可见的 Run 状态、创建、查询、取消请求和结果读取。
- `RunSupervisor`：协调一次 Run 的完整生命周期，对外隐藏 internal attempt。
- `AttemptSupervisor`：管理 attempt 启动、失败、自动恢复、replay、取消和资源释放。
- `RunInputBuilder / MemoryManager`：从 Session transcript、memory、tool facts 等事实构造 Attempt 输入。
- `ToolRuntime`：管理工具执行运行时边界；业务工具规则和业务权限不进入 Host / Engine。
- `EventLog`：Run 的 append-only 事件事实源。
- `EventProjection / Observers`：从 EventLog 派生 tool trace、audit、metrics、timeline、
  outbox 等视图或外部记录。
- `Policy/Governance`：恢复策略、replay 策略、输出校验决策消费、worker 选择、取消收口等 Host 运行策略。
- `WorkerProxy`：Host 到执行环境的适配边界。
- `EngineWorker`：Host capability，在选定执行环境中承载 Engine、Runner 和 ToolExecutor。

`Scene Preparation` 可作为独立外围组件。它可以沿用现有设计思路，但不应迫使 Host 核心直接承担
Service / domain / prompt assembly 的职责。

## 5. Public Interface 口径

Host public interface 应围绕 `Session`、`Run`、`RunEvent`，不暴露内部机制。

候选接口需要同时满足两个调用形态：

- 流式调用方：启动 Run 后直接消费事件流，并在终态事件里拿到结果。
- 非流式 / 断线重连调用方：后续按 `run_id` / cursor 补读事件或读取结果。

因此 `start_run` 不应只返回裸 `RunHandle`，也不建议只返回裸 `AsyncIterator[RunEvent]`。
裸 iterator 会让调用方在拿到首个事件前缺少 `run_id`，不利于取消、断线重连和日志关联。
更合适的形态是返回 `RunStream`：包含 handle 与事件流。

Run 创建请求必须是独立的持久化事实：

```python
@dataclass(frozen=True)
class StartRunRequest:
    session_id: str
    client_request_id: str
    input: RunInput
    options: RunOptions
```

`client_request_id` 是调用方提供的创建幂等键。Host 必须按
`(session_id, client_request_id)` 建立唯一约束；同一 key 重复调用 `start_run` 时，必须返回同一个
Run 对应的 `RunStream` / `RunHandle`，不得新建 Run。该幂等约束解决 Web / WeChat / CLI
在网络超时后重试造成重复 Run、重复 transcript、重复 outbox 的问题。

`RunHandle` 至少包含：

```python
@dataclass(frozen=True)
class RunHandle:
    session_id: str
    run_id: str
    state: RunState
    event_cursor: RunEventCursor
```

`RunStream` 至少包含：

```python
@dataclass(frozen=True)
class RunStream:
    handle: RunHandle
    events: AsyncIterator[RunEvent]
```

`event_cursor` 表示调用方开始订阅事件时使用的游标。具体语义建议是：

- `start_run` 在同一持久化事务中创建 Run 并写入初始 RunEvent。
- `RunHandle.event_cursor` 指向该 Run 初始事件之前或等价的可重放位置。
- `RunStream.events` 等价于 `stream_run_events(run_id, after=handle.event_cursor)`。
- 客户端断线后，用最后一次成功处理的 event cursor 继续订阅，不需要调用方自行猜测 event offset。

`RunEvent` 应包含中间事件与终态事件。终态成功事件必须携带 `RunResult` 或稳定
`result_id`，让流式调用方不必在正常消费完整事件流后再额外调用 `get_run_result`。

候选接口：

```python
async def create_session(request: CreateSessionRequest) -> SessionView: ...

async def get_session(session_id: str) -> SessionView | None: ...

async def close_session(session_id: str) -> SessionView: ...

async def clear_session(session_id: str) -> SessionView: ...

async def start_run(request: StartRunRequest) -> RunStream: ...

async def get_run(run_id: str) -> RunView | None: ...

async def cancel_run(run_id: str) -> RunView: ...

def stream_run_events(
    run_id: str,
    *,
    after: RunEventCursor | None = None,
) -> AsyncIterator[RunEvent]: ...

async def get_run_result(run_id: str) -> RunResult | None: ...

async def wait_run_result(
    run_id: str,
    *,
    timeout_seconds: float | None = None,
) -> RunResult: ...

async def list_session_timeline(
    session_id: str,
    *,
    after: SessionTimelineCursor | None = None,
    limit: int = 50,
) -> SessionTimelinePage: ...
```

接口语义：

- `start_run` 倾向使用 async。它负责创建并启动或排队 Run，返回 `RunStream`；不等待 Run 完成。
- `RunStream.events` 是当前启动调用的主事件流，包含中间事件和终态事件。
- `RunStream.events` 是 EventLog 的订阅视图，不是执行控制通道。调用方不消费、慢消费或关闭
  iterator，只释放订阅资源，不取消 Run；取消只能通过 `cancel_run`。
- RunEvent 必须先落 EventLog，再推送给 `RunStream.events`；慢消费者通过 cursor 补读，
  不反压 Engine 主执行，除非后续设计显式进入资源保护策略。
- `stream_run_events` 是后续补读 / 重连接口。它必须先 replay `after` 之后已经持久化的事件，再继续等待新事件。
- `get_run_result` 是非阻塞快照补查接口；用于断线后、非流式调用方或已知 terminal 后补查结果。
  它不是流式主链路的一部分，流式调用方消费到成功终态事件时应已能拿到 `RunResult`
  或稳定 `result_id`，不能要求调用方在正常消费完整事件流后必须再调用 `get_run_result`。
- `wait_run_result` 是等待型读取；用于非流式调用方，不要求调用方自己轮询 `get_run_result`。
- `list_session_timeline` 是客户端聊天记录读取接口，返回展示 read model，不是 RunInputBuilder 输入。

典型调用方式：

```python
stream = await host.start_run(
    StartRunRequest(
        session_id=session_id,
        client_request_id=client_request_id,
        input=run_input,
        options=run_options,
    )
)
handle = stream.handle

last_cursor = handle.event_cursor
result: RunResult | None = None
async for event in stream.events:
    last_cursor = event.cursor
    render(event)
    if event.type == RunEventType.RUN_SUCCEEDED:
        result = event.result
        break
    if event.type in (RunEventType.RUN_FAILED, RunEventType.RUN_CANCELLED, RunEventType.RUN_LOST):
        break
```

非流式调用方可以使用：

```python
stream = await host.start_run(request)
result = await host.wait_run_result(stream.handle.run_id, timeout_seconds=300)
```

断线重连调用方可以使用：

```python
async for event in host.stream_run_events(run_id, after=last_seen_cursor):
    last_seen_cursor = event.cursor
    render(event)
```

`RunInput` 必须满足幂等回放与自动 resume 要求：

- `RunInput` 是创建 Run 的持久化初始事实，不是一次性进程内 DTO。
- `RunInput` 必须能被序列化、持久化、校验和重放。
- 同一个 `RunInput` 在同一 `Session` / `Run` 语境下重复回放，不应改变用户意图。
- `RunInput` 不得持有进程内对象、回调、打开的文件句柄、未稳定化的 iterator 或临时资源引用。
- 所有影响后续 attempt 构造的显式参数都必须在 `RunInput` / `RunOptions` / policy 中强类型表达，
  不得塞进 metadata、extra payload 或开放 dict。
- 自动 resume、replay、进程恢复时，Host 必须能仅基于持久化的 `RunInput`、Session 事实、
  RunEvent / RunResult 与 policy 重建新的 internal attempt。
- 客户端展示用 reasoning / 思考过程字段不得进入 `RunInput`，也不得参与 `RunInput`
  重放。

`RunOptions` / policy 中可包含 `OutputContractRef`。它是可持久化、可解析的输出契约引用，
用于在多进程 resume / replay 时重新找到同一个 validator。Host 只消费通用
`ValidationDecision`，不持有进程内 validator 回调，也不理解业务规则。

`RunResult` 是 Run 成功收口后的不可变快照，至少应包含：

```python
@dataclass(frozen=True)
class RunResult:
    result_id: str
    run_id: str
    terminal_event_cursor: RunEventCursor
    answer: AnswerView
    warnings: tuple[RunWarning, ...]
    errors: tuple[RunError, ...]
    artifact_refs: tuple[ArtifactRef, ...]
    evidence_refs: tuple[EvidenceRef, ...]
    created_at: datetime
    validation_status: ValidationStatus
```

`artifact_refs` 与 `evidence_refs` 必须分离：

- `artifact_refs` 指 Run 产生或引用的持久化产物，例如报告文件、表格、图片、下载物、
  trace bundle、导出文件等。
- `evidence_refs` / `source_refs` 指回答依据、引用来源、证据锚点或 provenance。
- Host 只保存这些引用的通用不透明标识和必要定位信息，不解释其业务含义。
- 具体证据如何产生、如何验证、如何映射到财报材料，由业务工具 / 输出契约 / evidence
  projection 负责，不进入 Host / Engine 业务语义。

`artifact_refs` 的来源必须是已经完成持久化或可稳定解析的产物引用。Host 不凭空制造业务产物：

- ToolRuntime / ToolExecutor 在工具确实创建或读取稳定产物时，返回通用 `ArtifactRef`。
- Engine / Runner 只能把执行过程中收到的稳定引用随事件或结果上报，不解释产物业务语义。
- RunResult projection 从成功终态事件、工具摘要和输出契约允许的结果字段中收集稳定
  `ArtifactRef`，并写入不可变 `RunResult`。
- 临时文件、进程内对象、未提交下载、未落库 trace 不能进入 `artifact_refs`。
- 证据引用若同时依赖某个产物，只能通过 `evidence_refs` 指向该产物内的位置或锚点；
  不把 evidence 混写进 artifact。

不作为 Host public interface：

- `run_agent_stream`
- `build_agent`
- `build_runner`
- `resume_run`
- `resume_pending_turn`
- `event_bus.subscribe`
- `EngineWorker.run_agent_messages`
- `ToolExecutor.execute`
- `run_operation_sync`
- `run_operation_stream`

`Steer` 可以后加。只要 `Run` / `RunEvent` / `Attempt` 抽象保持干净，后续增加
`steer_received` / `steer_applied` 事件不应破坏主架构。

## 6. Session

`Session` 是一条聊天记录。它表达：

- 这条聊天记录是谁创建的。
- 当前是否仍可写入。
- 历史 turn / timeline 如何读取。
- 客户端如何读取 assistant answer、tool 摘要、warnings/errors 和思考过程展示字段。
- 是否可以清空或关闭。
- 同一条聊天记录中 Run 的顺序与上下文一致性。

Session 不泄漏 Agent / Runner / EngineWorker / ToolRegistry 等执行细节。

### 6.1 Session 状态机

候选状态：

```text
ACTIVE
CLOSING
CLOSED
CLEARING
BLOCKED
```

含义：

- `ACTIVE`：允许创建新 Run。
- `CLOSING`：关闭中，拒绝新输入，等待内部收口。
- `CLOSED`：终态，不再接受写入。
- `CLEARING`：清空历史中，拒绝新输入。
- `BLOCKED`：清空、恢复或持久化调和失败后的保护状态，需要管理动作解除。

`CLOSING` 是否第一版需要、`BLOCKED` 是否改名为 `REPAIR_REQUIRED`，留到实现计划阶段确认。

### 6.2 聊天记录与思考过程

客户端存在查看聊天记录的需求，且聊天记录需要包含思考过程展示字段。

Session 需要提供面向客户端的 transcript / timeline read model，包含：

- 用户输入。
- assistant answer。
- 可展示 reasoning / 思考过程。
- tool 摘要。
- warnings / errors。
- 时间。
- 关联 `run_id`。

reasoning / 思考过程只能作为客户端展示字段持久化。它在设计上必须与运行态上下文隔离，
没有机会流回 `RunInputBuilder / MemoryManager`，也不得参与 `RunInput` 重放。客户端
read model 与 Host 内部上下文构造必须分离，避免为了展示需求污染 Agent 输入。

### 6.3 同一 Session 的 Run 仲裁

第一版采用最保守的 Session admission policy：同一 `Session` 同一时间最多允许一个非终态
Run 被接纳。

非终态集合：

```text
CREATED
QUEUED
RUNNING
WAITING
RECOVERING
CANCELLING
```

仲裁规则：

- `start_run` 必须在持久化事务中完成 `(session_id, client_request_id)` 幂等检查与
  Session active Run 仲裁。
- 如果请求命中相同 `(session_id, client_request_id)`，Host 返回原 Run 的 `RunStream` /
  `RunHandle`。
- 如果请求使用新的 `client_request_id`，且同一 Session 已存在非终态 Run，第一版返回
  typed busy / conflict 错误，不创建新 Run。
- `QUEUED` 只表示已接纳 Run 正在等待 lane、policy 或 worker capacity，不表示排在同一
  Session 的其它 Run 后面。
- 后续若引入 `Steer` 或 per-session next-run queue，必须重新更新本节，不能在实现中
  通过隐式队列改变第一版契约。

该规则必须依赖数据库唯一约束、compare-and-set 或等价跨进程协调，不能依赖单进程内存锁。

## 7. Run

`Run` 是某个 `Session` 里一次带上下文的聊天执行。Run 是对外可见执行单位；自动恢复、
replay、attempt 重建都不改变对外的同一个 Run。

### 7.1 Run 状态机

候选状态：

```text
CREATED
QUEUED
RUNNING
WAITING
RECOVERING
CANCELLING
SUCCEEDED
FAILED
CANCELLED
LOST
```

合法主路径：

```text
CREATED -> QUEUED -> RUNNING -> SUCCEEDED
CREATED -> QUEUED -> RUNNING -> FAILED
CREATED -> QUEUED -> CANCELLED
CREATED -> QUEUED -> RUNNING -> CANCELLING -> CANCELLED
CREATED -> QUEUED -> RUNNING -> WAITING -> RECOVERING -> RUNNING -> SUCCEEDED / FAILED / CANCELLED
CREATED -> QUEUED -> RUNNING -> RECOVERING -> RUNNING -> SUCCEEDED / FAILED / CANCELLED
CREATED / QUEUED / RUNNING / WAITING / RECOVERING -> CANCELLING -> CANCELLED / LOST
CREATED / QUEUED / RUNNING / WAITING / RECOVERING / CANCELLING -> LOST
```

含义：

- `CREATED`：Run 事实已登记。
- `QUEUED`：等待 lane / policy / worker capacity。
- `RUNNING`：当前存在 active attempt。
- `WAITING`：Run 正在等待外部条件、审批、长事务、异步工具完成或其它 Host 管理的等待事实；
  该状态预留给 GitHub issue #4，不在当前阶段实现。
- `RECOVERING`：Host 正在为同一个 Run 自动恢复或重建 attempt。
- `CANCELLING`：取消请求已接受，等待 active attempt 协作收口。
- `SUCCEEDED`：终态，产生成功结果。
- `FAILED`：终态，执行失败且不能自动恢复。
- `CANCELLED`：终态，取消已收口。
- `LOST`：Host 无法确认执行结果，需要恢复或人工调和策略。

第一版应保留 `QUEUED` 与 `RECOVERING`。`WAITING` 作为 issue #4 的预留状态先进入状态机，
但等待协作的具体实现后移。`LOST` 是否第一版落地取决于多进程 orphan recovery 是否同阶段实现。

### 7.2 取消治理

对外只暴露 `cancel_run(run_id)`。取消治理内部包括：

- 写入取消意图。
- 通知当前 attempt / worker。
- 映射到执行环境内 cancellation token。
- 等待 Engine / ToolExecutor 协作退出。
- 超时升级或标记 lost。
- 收敛 Run 终态。

这些步骤不应变成普通调用者必须编排的接口。

取消治理增强跟踪在 GitHub issue #3，当前不进入 Host 主迁移第一阶段实现。Host 设计只预留必要空间：

- `Run` 状态机包含 `CANCELLING` 与 `LOST`，支持取消请求、协作收口失败和结果不可判定的结构化表达。
- P8 后 `Attempt` 状态机不再单独建模 `CANCELLING` 中间态；取消意图先由 Run / WorkerProxy
  控制通道表达，attempt 最终收敛到 `CANCELLED`、`FAILED`、`STALE` 或 `LOST`。后续 issue #3
  若需要 attempt 级取消中间态，必须重新更新本节状态机。
- `RunEvent` / EventLog 必须能记录取消请求、取消已下发、取消已收口、取消升级和 lost 等事实。
- Engine 不主动轮询 Host；取消信号仍由 Host / WorkerProxy 映射到执行环境内 cancellation token。

watchdog、强制终止、后台任务治理、SSE / tool wait 等资源的取消可观测性，等主迁移完成后按 issue #3
单独设计，不在当前草稿中预设实现细节。

取消请求的最小状态收敛规则：

- `QUEUED` 且尚未创建 attempt：可以直接收敛到 `CANCELLED`，并写入取消请求与取消收口事件。
- `RUNNING`：进入 `CANCELLING`，向当前 attempt 下发取消。
- `WAITING`：进入 `CANCELLING`，取消 wait record 或等待治理资源，再收敛到 `CANCELLED` /
  `LOST`。
- `RECOVERING`：阻止创建新 attempt，释放已获得的恢复 owner，再收敛到 `CANCELLED` /
  `LOST`。
- `CANCELLING` 超时后是否升级为 `LOST`，由后续 issue #3 的 watchdog 策略决定。

### 7.3 Replay

Replay 是 Run 内部的修复 / 恢复机制，用于模型返回脏数据时重新执行或修复输出。

边界：

- Host 自己不懂业务，不能直接判断什么是“脏数据”。
- `Output Validation` 与 `Replay Execution` 分离。
- 脏数据判断由外部 `OutputContract` / `Validator` / Service 侧契约组件完成。
- Host 只消费 validator 返回的结构化 replay decision。
- replay 在同一个 Run 下创建新的 internal attempt。
- replay 必须绑定新的 cancellation token / worker execution context，不复用旧 Agent / Runner 实例。
- replay 必须进入 EventLog，并有次数上限，避免无限修复循环。
- validator decision 必须持久化到 EventLog，至少记录 validator / output contract 版本、
  replay count、decision reason、repair instruction 引用和 replay policy。
- 进程恢复后，Host 必须能根据已持久化 decision 判断是继续 replay、停止为 failed，还是等待
  人工调和，不能依赖进程内 validator 回调残留。

Validator 可以返回通用 decision，例如：

```text
accepted
replay_required(reason, repair_instruction, replay_policy)
failed(reason)
```

## 8. Attempt

`Attempt` 是 Host 内部执行尝试，用于多进程恢复、自动 resume、worker 接管、replay 和 fencing。
Attempt 不作为普通调用方 public interface。

### 8.1 Attempt 状态机

P8 后 `Attempt` 状态机固定为：

```text
CREATED
RUNNING
SUCCEEDED
FAILED
CANCELLED
SUSPENDED
STALE
LOST
```

合法迁移：

```text
CREATED -> RUNNING
RUNNING -> SUCCEEDED
RUNNING -> FAILED
RUNNING -> CANCELLED
RUNNING -> SUSPENDED
RUNNING -> STALE
RUNNING -> LOST
STALE -> LOST
```

状态语义：

- `CREATED`：attempt 记录已创建，但尚未持有有效 owner。P8 主路径应在同一事务中创建并 acquire 到
  `RUNNING`；该状态主要服务诊断和测试。
- `RUNNING`：当前 attempt 有有效 owner lease；只有匹配 owner token hash、全局单调
  `fencing_token` 且 lease 未过期的 owner 可以写 attempt-scoped facts。
- `SUCCEEDED` / `FAILED` / `CANCELLED` / `SUSPENDED`：正常 terminal attempt，必须同事务关联
  terminal EventLog position。
- `STALE`：旧 owner lease 过期, 结果未知, 当前 attempt 已关闭执行权; P8 D2 后 recovery
  scan 一律把过期 lease 收口为 `LOST`(诊断终态), `STALE` 仅作为运维 / smoke 显式诊断 API
  保留, 不在生产 recovery 主路径出现。
- `LOST`：结果无法确认; Recovery 主路径默认终态; 不允许再写 attempt-scoped facts。

`SUSPENDED` 是 issue #4 的预留状态：表示 Engine / ToolExecutor 协作产生等待事实后，
当前 attempt 已停止继续执行，Run 进入 `WAITING`，后续由 Host wait record 完成、取消、超时或丢失治理。

### 8.2 P8 Attempt Supervision 边界

P8 新增 `AttemptSupervisor` 作为 Host 内部 owner 真源。它不是 public interface，也不改变 Engine
协议；Engine 仍只看到普通 `RunInput`、`ToolExecutor` 和 `EngineEvent`。

P8 后 Attempt 执行边界是：

```text
LocalRunHarness
  -> AttemptSupervisor.lease_context(...)
      -> AttemptLeaseStore acquire / renew / verify / close
      -> AttemptOwnerContext 只在 Host internal 流动
      -> global monotonic fencing_token identifies current owner epoch
  -> WorkerProxy / EngineWorker.stream_engine_events(...)
  -> EngineEvent / Host-owned facts
  -> AttemptScopedRunEventAppender
      -> verify current owner in the same HostStorage transaction
      -> append durable RunEvent
      -> allocate per-run cursor and global event position
  -> terminal path
      -> append terminal RunEvent
      -> close attempt
      -> write terminal_event_position
      -> update Run terminal state / result snapshot
      -> commit as one durable unit
  -> ProjectionCoordinator drains EventLog
```

边界规则：

- `AttemptSupervisor` 管理 owner token、owner id、lease expiry、renew heartbeat、fencing、
  terminal close 和 stale / orphan recovery；`LocalRunHarness` 只做薄编排，不承载 lease SQL、
  recovery scan、token 校验或 fencing error 策略。
- owner token 明文只能存在于 Host internal `AttemptOwnerContext`；持久化只保存 token hash，
  普通日志、RunEvent payload、ToolExecutionContext、public stream 和 README 示例都不能泄露明文 token。
  fencing token 是全局单调整数，可用于 owner 新旧比较，但仍不应作为普通调用方 public API 暴露。
- P8 D2 后 recovery 仅做诊断收口, 不 takeover、不在 recovery 路径创建新 attempt。旧 attempt
  通过 CAS 标记为 `LOST` (lease 过期 / `CREATED` 孤儿 / run terminal); 重试 / resume 必须由
  Service 层显式发起新的 `StartRunRequest` (新 attempt_index), 不由 recovery 隐式创建。
- 旧 owner、过期 owner、非 owner 或旧 fencing token 的迟到写入必须返回 typed fencing refusal，并且不得写入
  diagnostic RunEvent；非 owner 不应通过“我被拒绝了”这类 meta-fact 污染 canonical EventLog。
- 所有 attempt-scoped append 都必须走 owner fencing，包括 Engine-sourced events、context compact
  facts、`RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 和 ToolRuntime / Engine tool loop 产生的普通 tool calling
  facts。P8.5 后不再把 truncate / cursor / `fetch_more` 表达为专属 RunEvent fact。
- ToolRuntime 不获得 owner token，也不把 owner token 放入 `ToolExecutionContext`。Host 通过内部
  `AttemptScopedRunEventAppender` / owner scope 为当前 attempt 注入可写 append port。
- 正常 terminal attempt 必须在同一 `BEGIN IMMEDIATE` 或等价 durable unit 中完成 terminal event
  append、owner verify、attempt close、`terminal_event_position` 写入、Run terminal state / result
  snapshot 更新；禁止 append 后另起事务补 position，也禁止用 `MAX(event_position)` 猜 position。
- Attempt ownership 与 observer ownership 是两个状态机。P8 可以把 `ObserverSink.process` 升级为
  async 调用协议，但不因此引入 observer claim / lease；observer 仍从 durable EventLog 消费，
  不读取 attempt owner side channel。

### 8.3 Recovery 与 Run 的关系

`Run` 是调用方看到的执行单位；`Attempt` 是 Host 内部执行尝试。recovery 创建新的 internal
attempt，不创建新的用户输入事实，也不改变对外 `run_id`。

规则：

- 同一个 Run 下可以有多个 attempt；`attempt_index` 必须反映真实执行尝试次数。
- 旧 attempt 进入 `LOST` (P8 D2 主路径) 或诊断态 `STALE` 后不再可执行; Service 层显式发起的
  新 attempt 使用新的 `attempt_id` / `attempt_index`, 通过新一轮 owner / fencing token 启动,
  不依赖 recovery 隐式创建。`recovered_from_attempt_id` 字段保留作为审计回填字段, 用于 P8 之前
  的旧库或将来 Service 层显式重试时回写来源 attempt id, 不在 recovery scan 内自动写入。
- 旧 attempt 没有 terminal RunEvent 时，`terminal_event_position` 可以为空；最终 Run 的
  `terminal_event_cursor` / terminal result 必须来自真正写入 terminal RunEvent 的正常 terminal attempt。
- recovery scan 不推进 projection checkpoint，不消费 observer side channel；projection 仍基于
  durable EventLog 的 global position at-least-once 追平。

### 8.4 P8 明确未做的事

P8 落地了 attempt lease / fencing / recovery 的内部机制，但以下事项明确不在 P8 范围内：

- recovery scan 未自动 wire 进 `build_durable_harness` 或 Session 生产启动链路；当前仅为
  `AttemptSupervisor.recover_stale_attempts` 内部显式入口，调用方需自行决定扫描时机。
- 未引入 multiprocessing launcher / process supervisor 生产代码；P8-S7 多进程 stress 测试
  使用 spawn-only 平台 helper，不提供生产级进程管理。
- 未实现 `QUEUED / WAITING / CANCELLING` 主路径治理；这些状态仍为预留。
- 未实现 public lifecycle governance（如 run admission、session active run 仲裁）。
- 未改变 Engine 协议；Engine 仍只看到普通 `RunInput`、`ToolExecutor` 和 `EngineEvent`。
- 未引入 observer claim / lease；attempt ownership 与 observer ownership 是两个独立状态机。

## 9. EventLog 与 RunEvent

EventLog 第一阶段就做。EventLog 是 Run 的 append-only 事实账本，不是 EventBus。
EventBus 若存在，只是把 EventLog 事实推送给订阅方的机制。

EventLog 用于：

- UI / Web 断线重连后补事件。
- WeChat / 外部信道投递失败后基于事实重放。
- 多进程恢复时还原 Run 已发生事实。
- Debug / trace / audit 的可靠派生。
- ReplyOutbox projection reconcile。

RunEvent 至少需要支持：

- 跨进程一致顺序。
- 幂等去重标识。
- `run_id` 关联。
- 可选 `attempt_id` 关联。
- cursor / sequence，用于 `stream_run_events(after=...)`。
- append-only；已发生事实不被覆盖。
- visibility / audience，用于区分客户端可见事件、内部审计事件、trace 事件和恢复治理事件。

### 9.0 P6 后 Durable EventLog 执行路径

P1.5 已固定的 append-before-stream、per-run cursor、exclusive replay、canonical / preview、
terminal guard 语义在 P6 后继续保留。P6 不另起事实来源，而是把 P1.5 的内存态 `RunEventStore`
升级为 durable facts 层，并在 Host 内部增加 Run / Attempt 最小持久状态、internal global event position、
projection checkpoint 与最小 observer / sink protocol。

P6 后目标路径是：

```text
start_run
  -> append Host-owned USER_INPUT_ACCEPTED
      -> Host durable Unit of Work / transaction owner
          -> allocate per-run RunEventCursor
          -> allocate internal global event position
          -> insert durable RunEvent row
          -> update minimal Run / Attempt state
          -> commit before stream visibility
  -> RunStream.events / stream_run_events observes appended event
  -> LocalRunHarness thin orchestration
  -> WorkerProxy.stream_engine_events
  -> EngineEvent
  -> translate_engine_event -> RunEventDraft
  -> DurableRunEventStore.append
      -> Host durable Unit of Work / transaction owner
          -> allocate per-run RunEventCursor
          -> allocate internal global event position
          -> insert durable RunEvent row
          -> update minimal Run / Attempt state / terminal snapshot when needed
          -> commit before stream visibility
  -> RunStream.events / stream_run_events
  -> ProjectionCoordinator drains durable EventLog
      -> observer checkpoint / retry / lag
      -> memory / timeline / audit read models
```

P6 后实现要点：

- `RunStream.events` 与 `stream_run_events(run_id, after=cursor)` 都是 `RunEventStore` 的订阅视图。
- `RunEvent` 必须先 append 到 store，获得 Host 分配的 per-run cursor 后，才能被事件流观察到。
- `RunEventCursor` 由 Host store 生成，不绑定 Engine sequence。
- internal global event position 只服务 observer / projection checkpoint，不等同于 public
  `RunEventCursor`，也不泄漏给普通调用方。
- `RunEventDraft` 只表示待 append 的内部草稿；对外可消费的事实是已 append 的 `RunEvent`。
- terminal `RunResult` 只从已 append 的 canonical terminal `RunEvent` 推导。
- terminal event、minimal Run / Attempt state 与 terminal snapshot / reconcile 标记必须由同一个
  Host durable Unit of Work 或等价事务 helper 保证一致；`LocalRunHarness` 不能按顺序组合多个
  store commit 拼出一致性。
- worker / proxy 异常导致 Host 无法获得 Engine terminal event 时，Host 追加 Host-owned canonical
  failure `RunEvent`；Host 自身翻译、append 或 terminal result 推导错误不能伪装成 worker / proxy failure。
- observer 默认消费 durable EventLog，不消费进程内 `AsyncIterator[EngineEvent]`；projection 写入必须
  幂等，checkpoint 只能在 sink 成功后前进。
- `LocalRunHarness` 在 P6 后只做 run orchestration 与薄委托：durable schema、checkpoint、observer
  dispatch、memory / timeline / audit rebuild 不应继续堆入 `_run_harness.py`。

`InMemoryRunEventStore` 在 P6 后只作为单元测试 / 小型 smoke adapter 保留：

- 它固定 append-before-stream、per-run cursor、exclusive replay、canonical / preview、terminal fact 等
  最小 EventLog 语义。
- 它不提供持久化 schema、多进程一致性、startup recovery、observer checkpoint、trace / audit /
  timeline / outbox projection。
- 生产路径默认应使用 durable EventLog 实现；P6 后的 memory / timeline / audit 示例 projection
  必须能从 durable EventLog replay / rebuild，不依赖进程内缓存。

### 9.1 Canonical Event 与 Preview Event

EventLog 需要区分“持久事实事件”和“展示型流式事件”。第一版可以同表不同 kind，但语义必须分层：

- canonical event：lifecycle、result、tool summary、validation、recovery、cancel、wait、
  outbox projection 等可恢复事实。
- preview event：assistant delta、progress、临时展示片段等 UI 体验事件。

Outbox projection、RunResult、replay、recovery 只能依赖 canonical event。preview event 可以持久化、
合并或按策略裁剪，但不能成为恢复和投递的唯一事实来源。

### 9.2 Terminal 收敛原子边界

成功终态必须把以下事实同事务写入，或具备等价的 reconcile 机制：

- append terminal canonical event。
- persist immutable `RunResult`。
- update Run state to terminal。
- 写入可供 Outbox projection 消费的 final answer / result fact。

失败、取消和 lost 终态也必须保证 terminal event 与 Run state 可调和。若事务中断造成部分写入，
startup recovery / reconciler 必须能根据 EventLog、RunResult 和 Run state 补齐缺失事实或标记
`LOST`。

`RunEventCursor` 语义必须在实现计划中固定：

- cursor 至少在单个 Run 内严格单调。
- `stream_run_events(after=cursor)` 使用 exclusive 语义，即返回 cursor 之后的事件。
- 如果后续需要跨 Run / Session 全局顺序，应新增 global cursor，不复用 per-run cursor
  暗示全局有序。

### 9.3 Retention / Compaction / Backpressure 口径

EventLog 不能无界膨胀，也不能让慢订阅者拖垮主执行：

- canonical event 默认长期保留，具体归档 / compaction 策略必须保证恢复、审计和 Outbox
  reconcile 仍可完成。
- preview event 可以按大小、时间或 terminal 后策略 coalesce / prune。
- `RunStream.events` 慢消费只影响该订阅；主执行以 EventLog 持久化为准。
- 当订阅者落后超过保留窗口时，Host 应返回 typed cursor expired 错误，引导调用方读取
  Session timeline / Run snapshot。

### 9.4 Event Projection / Observers

Engine 迁移阶段已经确认：tool trace 不属于 Engine。Engine 只 emit 强类型 `EngineEvent`；
Host / EngineWorker 接收事件后，必须提供可靠的 projection / observer 机制，让 tool trace、
audit、metrics、alerting、debug sampling、Session timeline、Reply Outbox 等能力从同一份事件事实派生。

核心原则：

- Engine 不依赖 `ToolTraceRecorder`，不写 JSONL，不决定 trace schema，也不调用 audit / metrics
  具体实现。
- Host 接收 `EngineEvent` 后，应先翻译为 Host 可治理的 canonical / preview `RunEvent`，
  并写入 EventLog。
- observer 默认消费 EventLog，而不是直接消费进程内 `AsyncIterator[EngineEvent]`；否则进程崩溃会
  丢失 trace / audit。
- 实时 UI 推送可以在 EventLog 落库后 fan out，但 fan out 不是事实真源。
- 如果 EngineEvent 事实不足以重建 tool trace / audit，应扩展强类型 EngineEvent / RunEvent
  契约，而不是让 Engine 反向依赖具体 trace 或 audit 组件。

Projection / observer 的最小机制：

- 每个 observer 有稳定 `observer_id`、消费 cursor / checkpoint 和 schema version。
- observer 写入必须幂等；重复消费同一事件不能产生重复 trace、重复 audit 或重复投递。
- projection 采用 at-least-once 语义，失败可重试，失败状态可观测。
- 多进程下 observer claim / lease 必须同时具备 owner secret 与全局单调 fencing token，避免多个进程同时写同一 sink。
- observer 可以按 visibility / audience 订阅不同事件层，例如 client、internal、audit、trace。
- projection lag、失败次数、最后成功 cursor 应可查询，便于恢复与运维。

第一版建议内置或预留以下 observer 类型：

- `tool_trace_observer`：把工具生命周期、tool call input/output summary、truncation /
  fetch_more、artifact refs、错误 envelope 等事件翻译为 tool trace 存储记录。
- `audit_observer`：把 policy decision、tool governance decision、cancel、replay、recovery、
  wait、worker lease 等治理事件翻译为审计记录。
- `session_timeline_projection`：把客户端可见事件投影成聊天记录 read model，包含 answer、
  reasoning 展示字段、tool summary、warnings/errors。
- `outbox_projection`：把 final answer / RunResult 投影成 Reply Outbox record。
- `metrics_observer`：派生耗时、token、tool 调用、失败率、replay 次数、projection lag 等指标。

observer 失败与 Run 生命周期的关系必须显式：

- `RunResult`、terminal Run state、Outbox 必需事实应由 terminal 收敛事务或 reliable reconciler
  保证，不能依赖 best-effort observer。
- tool trace / metrics / debug sampling 默认不驱动 Run 执行，也不阻塞 Run terminal。
- audit 如果被 policy 标记为 hard-gate，则必须成为明确的 required projection，并进入状态机 /
  recovery 设计；不能通过隐式同步写入混在 Engine 或 ToolExecutor 里。

OLD `ToolTraceRecorder` / `JsonlToolTraceStore` / `tool_trace_v2` 可以作为 Host observer 默认实现素材，
但 NEW trace schema 真源应在 Host / observability 阶段确认。Host 当前设计只固定事件订阅与可靠
projection 边界。

P7 后 tool trace 的架构边界固定为：

```text
RunInputBuilder builds RunInput
  -> Host writes RUN_INPUT_CONTEXT_SNAPSHOT_BUILT fact
      -> hot summary: message roles / source cursors / hashes / context budget / tool schema names
      -> cold refs: full model input / full tool schemas
  -> Engine consumes RunInput
  -> Engine emits tool / usage / final / protocol events
  -> Host translates to canonical RunEvent facts
  -> Durable EventLog persists facts and source positions
  -> ProjectionCoordinator drains EventLog
  -> tool_trace_observer writes ToolTraceStore hot records + cold raw payloads
  -> analyzer / smoke reads ToolTraceStore
```

`RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 是 Host-owned diagnostic fact，用来回答“这一轮模型到底看到了什么
上下文”。它不是 EngineEvent，不进入 Engine 契约，不参与 Conversation Memory 下一轮事实池，也不改变
RunInputBuilder 的决策。它必须在 RunInputBuilder 产物确定后、Engine attempt 启动前写入；否则
tool trace 会重新退化为进程内缓存诊断，无法 crash replay。

`RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 的 raw payload 与 EventLog fact 必须作为同一个 durable unit of
work 提交。P7 落地的实现方式：fact `data` payload 直接内联完整 `raw_input_messages_json` 与
`raw_tool_schemas_json`（SQLite TEXT 列无大小硬上限），事务边界收敛到单条 `append_in_transaction`
原子写入；不再单独写"先 raw blob 再 append fact ref"两阶段。该方式天然消除"fact 已落库但 raw
ref 缺失"窗口；trade-off 是 EventLog 行体积增大，已在 `docs/host/migration-plan.md` §4.3 登记为
中期评估项（必要时再外迁到独立表 / 文件）。

P7 trace payload 采用 OLD 的热 / 冷分层，而不是默认做业务内容过滤：

- 热层 trace record 保存可检索摘要、状态、source cursor / global position、大小、hash、schema version。
- 冷层 raw payload 保存完整 model input、tool schemas、tool result、provider protocol raw payload，以及
  `fetch_more` 诊断所需的 `scope_token` / `cursor`。
- `scope_token` / `cursor` 是定位 `fetch_more` 重复调用、错 token、错 cursor 的关键诊断字段，必须能在
  trace 冷层或 tool call arguments 中回放；但不得进入 Conversation Memory、RunInputBuilder 输入、
  普通日志、README 示例或 smoke 大块输出。
- provider secret、Authorization header、API key、cookie 不得进入 trace；若 provider raw payload
  混入这些能力凭据，Host 必须只 scrub 这类 provider secret，不扩大到业务 prompt、tool result、
  `scope_token` 或 `cursor`。

OLD `utils/analyze_tool_trace.py` 中业务无关的诊断能力应随 P7 迁移或提供等价 adapter，包括重复工具调用、
截断后未续读、`fetch_more` 参数 / 质量、trace 完整性、context 压力、provider protocol error 与 final
response presence。财报 / web 业务专项分析不属于 P7 Host 主线。

P7 固定采用 `tool_trace_v2_host` 作为 Host trace schema version。OLD `tool_trace_v2` 可作为语义参考和
exporter / adapter 输入输出素材，但 Host 内部 read model 不伪装成完全 OLD-compatible schema。durable
harness 在配置了 `ToolTraceStore` / trace storage path 时默认注册 `tool_trace_observer`；未配置 trace
store 时不注册，避免无意义 observer 状态面。

P7 落地后的硬事实：

- JSONL 文件是 trace 的真源；P7 不在 SQLite 引入任何 `host_tool_trace_*` 表。`docs/host/phase7-plan.md`
  §9 原先建议的 `host_tool_trace_records` / `host_tool_trace_raw_payloads` 双表方案已被 JSONL 真源方案取代。
- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 是 P6 EventLog 的事实补齐 patch，由 Host 同事务追加；
  内联 `raw_input_messages_json` / `raw_tool_schemas_json` 与 `raw_*_blob_id`，让 trace observer
  无需回查 EventLog 即可重建 raw payload。
- `ToolTraceObserver` 是当前唯一 sink 同步阻塞 terminal drain 的 observer：sink 每行 `flush + fsync`、
  raw payload `tmp + os.replace` 原子落地，但写入完全在文件系统，**不动 SQLite**，不阻塞 Engine 事件
  产生；`tx` 参数仅为满足 `ObserverSink` 协议而保留。projection 采用 best-effort 语义：JSONL append
  与 `ProjectionCoordinator` checkpoint 推进非原子，crash 窗口可能产生孤儿副本，依赖行内
  `idempotency_key` 在 analyzer 阶段去重，至少一次 + 去重而非 exactly-once。
- 行内 `idempotency_key`（sha256[:32], 包含 `schema_version | trace_type | run_id | iteration_id |
  tool_call_id | source_event_position | record_role`）是 analyzer 去重崩溃 replay 副本的依据；
  `analyzer` 严格拒绝 OLD `tool_trace_v2` 文件，不做兼容读取。
- provider secret scrub 仅作用于 `PROVIDER_PROTOCOL_ERROR.raw_payload`（`Authorization` /
  `api_key` / `cookie` / `x-api-key` / `anthropic-api-key` 等明确凭证键替换为 `***`）；
  `scope_token` / `cursor` / prompt / tool result 仍按 OLD 热 / 冷分层保留进 trace，用于真实故障定位。

P8-S2 曾把 `ObserverSink.process` 从同步升级为 async 调用协议：`ProjectionCoordinator.drain()`
在同一 HostStorage 事务内 `await observer.process(tx, events)`。该描述只记录 P8 前置实现事实；
P8.5 起，non-required trace JSONL/blob sink 采用事务外 at-least-once 写入，checkpoint 仅在 sink
success 后短事务推进，checkpoint 前 crash 允许 replay duplicate 并依赖 `idempotency_key` 去重。
这不引入 observer claim / lease；observer 仍从 durable EventLog 消费，不读取 attempt owner side
channel。attempt ownership 与 observer ownership 是两个独立状态机。

### 9.5 Wait / Suspend 预留契约

GitHub issue #4 跟踪 `ToolExecutionOutcome` 扩展分支，包括 `awaiting` /
`run_suspended` / `suspend` 等能力。当前 Host 主迁移不实现等待协作，但状态机和契约必须预留。

预留原则：

- 等待型 outcome 必须是强类型封闭分支，不能实现为 `status: str` 加任意 payload。
- 等待型 outcome 只能表达 Host 生命周期治理、等待、审批、通知、取消、重试、去重、委派、
  artifact 引用等通用运行语义。
- 禁止把 fins/web/doc 的业务状态直接塞进 Engine outcome。
- Engine 可以产出等待事实和 suspended terminal，但不建立 Host wait record，也不治理恢复。
- Host 负责 wait record、外部等待完成、取消、超时、丢失和恢复。
- 恢复必须基于持久化 `RunInput`、Session 事实、RunEvent / RunResult、wait completion facts 与 policy
  创建新的 internal attempt，不复用旧 Agent / Runner。

内部 `WaitRecord` 候选状态：

```text
CREATED
WAITING
READY
RESUMING
COMPLETED
CANCELLED
TIMED_OUT
LOST
```

候选主路径：

```text
CREATED -> WAITING -> READY -> RESUMING -> COMPLETED
CREATED -> WAITING -> CANCELLED
CREATED -> WAITING -> TIMED_OUT
CREATED -> WAITING -> LOST
READY -> RESUMING -> LOST
```

状态含义：

- `CREATED`：等待事实已登记。
- `WAITING`：等待外部条件、审批、异步工具或长事务完成。
- `READY`：等待条件已满足，可以恢复 Run。
- `RESUMING`：某个 Host owner 已获得恢复权，正在创建新的 attempt。
- `COMPLETED`：等待已被成功消费，Run 已恢复或收口。
- `CANCELLED`：等待被取消。
- `TIMED_OUT`：等待超时。
- `LOST`：等待来源或恢复 owner 失活，结果不可判定，需要恢复治理。

这些状态当前只是契约预留。wait record 的存储、owner / lease、monitor、通知、恢复输入和测试策略，
后续必须按 issue #4 拆子设计。

## 10. EngineWorker / Proxy 边界

`EngineWorker` 是 Host capability，不是新业务层。Host 选择执行环境，WorkerProxy 适配本地或远程形态。

Local 形态：

```text
Host
  -> LocalProxy
      -> EngineWorker
          -> Engine
          -> local ToolExecutor
```

Remote 形态：

```text
Host
  -> RemoteProxy
      -> RemoteStub
          -> EngineWorker
              -> Engine
              -> remote ToolExecutor
```

Remote Agent 的语义是：

```text
Engine + tools execute remotely
```

Remote Agent 不是“远程 Engine 回调 Host 进程执行工具”。远程模式下，工具执行发生在远端
worker 侧；Host 通过 WorkerProxy 控制远端执行环境、下发治理输入，并接收事件与结果。

EngineWorker 第一版语义接口：

```python
@dataclass(frozen=True)
class WorkerCancelRequest:
    run_id: str
    attempt_id: str
    fencing_token: int

class EngineWorker(Protocol):
    def run_agent_messages(
        self,
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]: ...

    async def cancel(self, request: WorkerCancelRequest) -> None: ...

    async def close(self) -> None: ...
```

取消语义：

- LocalProxy / 本地 EngineWorker 可以传递 Host 创建的本地 cancellation token。
- RemoteProxy 不能把 Python 进程内 cancellation token 当作跨进程序列化契约。
- RemoteStub 应在远端创建 worker-local cancellation token。
- `cancel(request)` 是独立控制通道，必须携带当前 active attempt 的 `attempt_id` 与
  `fencing_token`，避免旧 owner 的迟到控制消息误伤新 attempt。
- Worker / RemoteStub 只能接受当前 lease owner 对应的 fencing token；不匹配时必须拒绝或幂等忽略。

RemoteProxy 的本地 API 可以保持 `AsyncIterator` 体验，但远程 wire protocol 不应被 Python
进程内 iterator 形状绑定。后续 RemoteStub 协议应围绕 cursor、ack、reconnect、cancel request
和 terminal result 设计。

## 11. ToolRuntime 与 ToolExecutor

Host owns governance truth。EngineWorker holds execution environment on behalf of Host。

ToolExecutor 由 EngineWorker 替 Host 在执行环境中代持，并提供给 Engine：

- 本地 EngineWorker 替 Host 代持本地 ToolExecutor。
- RemoteStub 侧 EngineWorker 替 Host 代持远程 ToolExecutor。
- Engine 只消费 `ToolExecutor` protocol。
- Engine 不知道 ToolExecutor 是本地实现还是远程 worker 内实现。
- Engine 不注册工具、不发现工具、不持有 ToolRegistry。

Host-owned ToolRuntime 代持底层业务 `ToolExecutor`，负责普通 tool dispatch、执行编排和
`ToolExecutionOutcome` 返回。ToolRuntime 不直接实现截断状态机或 cursor store；这些能力属于 Host
私有截断组件，本文暂称 `RuntimeTruncateManager`。ToolRuntime 不注册业务工具、不发现业务工具、不拥有业务
权限模型；业务工具仍由调用方提供的 `ToolExecutor` 执行。

工具执行边界：

```text
Engine
  -> ToolExecutor.execute(request)
  -> Host-owned ToolRuntimeToolExecutor
  -> HostToolRuntime.execute_tool_call(request)
      -> underlying business ToolExecutor
      -> RuntimeTruncateManager applies schema-driven truncate when needed
      -> ordinary ToolExecutionOutcome
  -> Engine receives ToolExecutionOutcome
```

`RuntimeTruncateManager` 是 ToolRuntime 内部组合的 Host 私有组件。它按显式 `ToolTruncateSpec` 决定是否
截断普通 tool result，维护 run-scoped、single-use、TTL-bound cursor store，并生成返回给 LLM 的
`truncation.fetch_more_args`。它不进入 Engine、`dayu.host.__all__`、`dayu.host.contracts` 或
`dayu.runtime`。

### 11.1 Host framework built-in tool 边界

`fetch_more` 是 Host 私有 framework built-in tool。它对模型表现为普通 tool schema，对 Engine 表现为普通
`ToolExecutionRequest` / `ToolExecutionOutcome`，但它的 declaration、callable、executor、cursor store、
fencing 与补读实现都属于 Host 私有实现，Engine 什么都看不到。

Engine 边界必须保持：

- Engine 只接收投影后的 `ToolSchema`，不接收 `ToolDefinition`。
- Engine 只发普通 `ToolExecutionRequest(name="fetch_more", arguments=...)`。
- Engine 只接收普通 `ToolExecutionOutcome`。
- Engine 不 import、不持有、不分支判断 `@tool`、`ToolDefinition`、callable、executor、framework built-in
  dispatch、cursor store、fencing 或 Host runtime 私有类型。

Host framework tool declaration 边界：

- Host 可以在私有 runtime 装配层使用公共 `@tool(...)` 声明能力，为 `fetch_more` 构造私有
  `ToolDefinition`。
- `@tool` 只用于让 schema、参数约束、展示 metadata 与执行 callable 同源声明；对 Engine / Runner 只能投影
  `definition.to_tool_schema()`。
- `fetch_more` 的 `ToolDefinition` 不进入 `dayu.host.__all__`、`dayu.host.contracts`、`StartRunRequest`、
  `RunOptions` 或 Engine public contract。
- Host 不为 `fetch_more` 保留 public handle、public request/result dataclass 或 legacy compatibility
  wrapper。

Runtime / tool 执行边界：

- Runtime 只在构造 Host 私有 `fetch_more` tool definition 时，通过闭包传入 `RuntimeTruncateManager`
  的最小补读 Protocol。
- 传入闭包的 Protocol 只暴露 `fetch_more` 执行所需能力，例如 cursor lookup / consume / issue、
  scope / binding / TTL 校验、limit resolution 与 chunk building；不暴露 Runtime 本体、EventLog、
  harness 或 Engine。
- 闭包注入完成后，`fetch_more` callable 自己执行补读 tool calling 逻辑，并直接返回
  `ToolCompletedOutcome` 或 `ToolFailedOutcome`。
- Runtime 不再构造或消费 `ToolFetchMoreRequest` / `ToolFetchMoreSucceededResult` /
  `ToolFetchMoreFailedResult` / `ToolFetchMoreResult` 等具体工具名契约。
- Runtime 不根据 `fetch_more` 私有返回类型分支；它只按普通 tool name dispatch 到 Host 私有 framework
  tool executor，并返回普通 `ToolExecutionOutcome`。
- Runtime 不拥有 cursor / truncation 的内部状态机；它只组合 `RuntimeTruncateManager`，并在普通 tool
  result 返回前调用 manager 做可选截断。
- `RuntimeTruncateManager` 不把 cursor、truncation 或 `fetch_more` 提升成 EventLog 特殊事实、public
  contract 或 projection 分支类型名。

`fetch_more` 补读边界：

```text
Model -> tool_call fetch_more(cursor, scope_token, limit?)
  -> Engine treats it as ordinary LLM tool call
  -> ToolExecutor.execute(ToolExecutionRequest{name="fetch_more"})
  -> ToolRuntimeToolExecutor -> HostToolRuntime
  -> Host private framework tool dispatch
  -> fetch_more callable uses closure-injected RuntimeTruncateManager Protocol
      -> validates cursor binding / scope / TTL
      -> consumes old cursor and optionally issues next cursor
  -> returns ordinary ToolExecutionOutcome
  -> Engine injects ordinary tool result back to the model
```

LLM-facing truncated tool result 的边界是：截断后的普通 tool result 可以短期携带
`truncation.fetch_more_args.scope_token` 给模型，只用于同一 run 内由模型发起的 framework `fetch_more`
tool call。该 token 仍不得写入 memory projection、普通日志或文档 / smoke 大块输出。P7 起，trace 冷层
必须能够保留该 token 与 cursor，用来诊断模型是否重复 `fetch_more`、传错 `scope_token` 或传错 cursor。
Engine 仍不拥有、不解释 `scope_token`；它只把 token 当作普通 tool result JSON 注入给模型，再把模型发起的
普通 tool args 回传给 Host。

EventLog / RunEvent 边界：

- EventLog 只看到一次次普通 tool calling：`TOOL_CALL_REQUESTED` 与 `TOOL_RESULT_ACCEPTED`。
- truncate 只是 Runtime 改写某个普通 tool 返回给 LLM 的数据；对 EventLog 来说，它仍是该 tool 的普通
  accepted result。
- `fetch_more` 只是普通 tool name，对 EventLog 来说，它仍是一次普通 tool request / result。
- cursor 是 truncate / fetch_more 的内部实现细节，只能作为普通 tool call 参数或普通 tool result payload
  的一部分短期进入 LLM roundtrip；Dayu 是本地 Agent，EventLog 只做窄 credential scrub：除
  `API_KEY` / 明确凭证外，不因字段名是 cursor、`scope_token`、tool args 或 tool result 而删除或遮蔽。
- 如果 EventLog 需要保留截断观察信息，应优先扩展通用 tool result 的摘要或 credential-scrubbed payload，
  不新增 `TOOL_RESULT_TRUNCATED` / `TOOL_CURSOR_ISSUED` / `TOOL_CURSOR_EXPIRED` /
  `TOOL_CURSOR_DENIED` 等 cursor / truncation 专属 RunEventType。
- Host 不追加 `TOOL_FETCH_MORE_REQUESTED` / `TOOL_FETCH_MORE_COMPLETED` /
  `TOOL_FETCH_MORE_FAILED` 等具体工具名 RunEventType。
- terminal RunEvent 后的 `fetch_more` 返回普通 failed `ToolExecutionOutcome`，且不追加新 RunEvent，以保持
  terminal guard。

ToolRuntime 仍必须保持：

- Host / Engine 不懂业务。
- tool execution runtime 与业务权限 / 业务规则分离。
- 财报文档访问约束由业务工具 / tool 边界保证，不进入 Host / Engine 业务语义。
- truncate 只由工具 schema / metadata 的显式 spec 驱动；无 spec、未启用、未知策略或非法 limit 不截断。
- `ToolTruncateSpec` 必须继续支持 OLD 已覆盖的多种截断策略，例如 `text_chars`、`text_lines`、
  `list_items`、`binary_bytes`，并支持 `target_field` / `field_path` 等定位方式；P5 不能把实现收窄成
  只服务 `huge_echo` 的单一文本截断。
- `fetch_more` 只作为 Host 私有 framework built-in tool 暴露给模型 schema，不恢复 legacy public
  `fetch_more` handle。
- 不在 P8.5 提前引入完整 P10 ToolRegistry；Host 私有 framework tool dispatch 只覆盖 Host built-in tool。

P5 后目标的 LLM-facing truncate / fetch_more 执行路径是：

```text
Model -> tool_call huge_echo(...)
  -> Engine treats it as ordinary LLM tool call
  -> ToolExecutor.execute
  -> ToolRuntimeToolExecutor -> HostToolRuntime
  -> huge_echo returns a large result
  -> RuntimeTruncateManager applies ToolTruncateSpec
      -> supports text_chars / text_lines / list_items / binary_bytes
      -> supports target_field / field_path where declared
      -> stores run-scoped single-use cursor + scope token
      -> returns a truncated ordinary tool result
  -> Engine injects truncated tool result back to the model
      -> includes LLM-readable truncation hint
      -> truncation.next_action = "fetch_more"
      -> truncation.fetch_more_args = {cursor, scope_token, limit?}
Model -> tool_call fetch_more(cursor, scope_token, limit?)
  -> Engine still treats it as ordinary LLM tool call
  -> Host ToolRuntime routes to private framework tool executor
  -> fetch_more callable consumes cursor through closure-injected RuntimeTruncateManager Protocol
  -> returns next chunk and, if needed, next cursor hint
Model -> repeats fetch_more if needed, then emits final answer
```

因此 `fetch_more` 本身应作为 framework tool 暴露给 LLM，但它不是业务工具，不进入完整业务 ToolRegistry
治理目标。Engine 只看到 ordinary tool schema、ordinary tool call 与 ordinary tool result；cursor 存储、
scope 校验、single-use、TTL 与 lineage 由 Host 私有 `RuntimeTruncateManager` 拥有。

ToolRuntime 最小生命周期事实应保持在普通 tool calling 维度，完整权限模型仍未展开：

- tool call proposed。
- approved / denied / deferred。
- started。
- completed。
- failed。
- cancelled / timeout。

这些事实可以投影为客户端可见 tool summary、内部 audit event 或 trace event。Host 只治理运行边界、
生命周期和资源收口；具体工具权限、业务权限和业务规则由 ToolRuntime policy / tool 侧契约表达。

ToolRuntime 不直接等同于 tool trace。ToolRuntime 负责产生和治理工具运行事实；tool trace 是
EventProjection / Observers 从这些事实派生出的可观测性记录。这样可以让审计、指标、告警和调试采样
复用同一事件订阅边界，而不是在 ToolRuntime / Engine 内分别写一套落盘逻辑。

## 12. Conversation Memory / RunInputBuilder

Conversation Memory 属于 Host 上下文治理，不属于 Engine，也不应污染 Host 最小 public interface。
RunInputBuilder 是 Host 内部把 canonical facts、memory projection 和当前用户输入装配成
`RunInput.messages` 的边界。Engine 只消费最终 messages，不理解 Session memory、claim、
evidence、timeline、tool cursor 或 compaction。

本节是 Conversation Memory / RunInputBuilder 的独立设计说明。它吸收 OLD issue
`https://github.com/noho/dayu-agent/issues/48` 的结论，但不要求读者另行打开该 issue 才能理解设计。

当前 P3 已落地的事实：

- `RunEventType.USER_INPUT_ACCEPTED` 与 `UserInputAcceptedData` 已成为 Host-owned canonical 用户输入事实，
  `UserInputScope` 是封闭 scope 类型。
- `LocalRunHarness.start_run` 只接受一条非空 `UserMessage` 作为当前轮 ingress；历史 transcript、
  system / assistant / tool message 或多条 user message 会在 append 前 fail fast。
- `LocalRunHarness.start_run` 会先 append `USER_INPUT_ACCEPTED`，append 失败时不启动 Engine。
- Engine 实际消费的 `RunInput` 由 Host 内部 `DefaultRunInputBuilder` 从当前用户输入事件与
  `ConversationMemorySnapshot` 构造，不从 `StartRunRequest.input` 旁路回放用户输入。
- Host 内部 memory store（P3 为 `InMemoryConversationMemoryStore`，P8-S8 起替换为
  `DurableConversationMemoryStore`）只从已 append canonical RunEvent 投影 session memory；
  preview / reasoning / delta / content completed 不进入 memory pool。
- Engine terminal 或 Host-owned worker / proxy failure terminal 后，当前 run 的 canonical events 才会投影
  到 memory；失败轮次的用户输入事实和中性 terminal summary 都会进入下一轮 memory。
- 当前只实现单进程、顺序多轮、`session` scope 的 memory；类型上预留 direct user、group、project、
  user scope。
- 当前已预留 `ConversationPinnedState`、`TaskFrame`、`MemoryClaim`、`ClaimStatus`、`EvidenceAnchor`、
  `AssumptionRegister`、`UserPreferenceProfileRef`、`memory_reset`、`claim_correction`、`scope_clear`
  的 internal 结构。
- `ConversationPinnedState` 包含 `current_goal`、`confirmed_subjects`、`user_constraints`、
  `open_questions` 四槽，并在 RunInputBuilder stable layer 中全量注入。
- verified claim ledger 与 assumption register 也属于 stable layer，当前实现全量注入且不参与历史 pool
  预算竞争。
- assistant final answer 只进入 raw turn / assistant conclusion 路径，不自动进入 verified claim ledger。
- `RunInputBuildTrace` 已实现为 internal-only 诊断对象，不进入 `RunInput`、memory pool 或下一轮事实真源。

### 12.0 当前 P3 最小实现路径

P3 已将最小 Conversation Memory / RunInputBuilder 接入当前 `run harness` 主链路。当前路径是：

```text
LocalRunHarness.start_run(StartRunRequest)
  -> _extract_current_user_text
      -> 只接受一条非空 UserMessage
      -> 拒绝历史 transcript / system / assistant / tool / 多 user message
  -> user_input_accepted_draft
  -> RunEventStore.append(USER_INPUT_ACCEPTED)
      -> 获得 Host 分配的 RunEventCursor
  -> ConversationMemoryStore.get_snapshot(session_id)
  -> DefaultRunInputBuilder.build(snapshot, current_user_event)
      -> pinned_state / task frame 全量 stable layer
      -> verified claims / assumptions
      -> evidence anchors / tool facts（保留 source event cursor）
      -> recent raw turns 语义保底
      -> older raw turns 按预算从新到旧消费、按时间顺序渲染
      -> episode summary 插入位
      -> RunInput(system Host Memory + current user message)
      -> RunInputBuildTrace（internal-only）
  -> WorkerProxy.stream_engine_events(replace(request, input=built_run_input))
  -> Engine consumes built RunInput
  -> EngineEvent
  -> translate_engine_event -> RunEventStore.append
  -> terminal RunEvent 或 Host-owned worker / proxy failure RunEvent
  -> ConversationMemoryStore.project_run_events(canonical events)
  -> 下一轮 start_run 读取新的 ConversationMemorySnapshot
```

P3 后执行边界：

- `StartRunRequest.input` 在 Host P3 最小入口中只作为“当前轮用户输入 ingress 材料”，不是可回放
  transcript，也不是 memory projection 输入。
- `USER_INPUT_ACCEPTED` 是用户输入 canonical 真源；append 失败时 Engine 不启动，append 前校验失败时
  EventLog 与 memory 都不被污染。
- Engine 从未看到原始 `StartRunRequest.input`；Engine 只看到 Host 重新构造后的 `RunInput.messages`。
- `ConversationMemoryStore` 只消费同一 run 已落库的 canonical `RunEvent`，不消费 preview、reasoning、
  display timeline 或 debug trace。
- `RunInputBuilder` 只读 `ConversationMemorySnapshot` 与当前 `USER_INPUT_ACCEPTED` 事件；不读取
  `RuntimeTruncateManager` cursor store，不持有 legacy public `fetch_more` handle，不消费 `scope_token`。
- `RunInputBuildTrace` 只用于 Host 内部诊断与测试；它不写入 EventLog，不进入模型上下文，也不作为下一轮
  memory 真源。
- P7 起，Host 在 RunInputBuilder 完成后追加 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` diagnostic fact，使
  tool trace 可持久重建 `iteration_context_snapshot`。该 fact 只服务 trace / audit / replay 诊断，
  不进入 ConversationMemory projection，不参与下一轮 RunInputBuilder 输入，也不影响 Engine 看到的
  `RunInput.messages`。
- P8-S8 起 `build_durable_harness` 默认装配 `DurableConversationMemoryStore`，memory snapshot
  与 EventLog checkpoint 同事务原子推进；生产代码不再保留 `InMemoryConversationMemoryStore`。
  tests-only `FakeInMemoryConversationMemoryStore`（位于 `tests/host/_memory_store_fake.py`）
  仅供测试 / smoke 使用。`startup_reconcile` 在 checkpoint 已 CAUGHT_UP 但 snapshot row
  因运维误操作丢失时，走 `repair_missing_session_snapshots` 从 EventLog 重建。

P4 当前执行边界 / 设计约束：

P3 已经提供 Conversation Memory、RunInputBuilder、`RunInputBuildTrace` 与可消费事实基础。P4 已在
Engine / Runner 以强类型事实报告 context overflow 或 compaction required 后，由 Host 接管 deterministic
compact 决策与 attempt 重建；它没有把 memory、compact 或 retry 策略放回 Engine。

P4 后边界保持为：Engine / Runner 只负责执行给定 `RunInput`、识别 context overflow /
compaction-required，并发出强类型事实；Host 负责 compact 策略、compacted `RunInput` 构造、
保真 / 变短验证，以及是否重建 internal attempt。当前 Engine / Runner 在 OpenAI-compatible adapter
边界识别结构化 `context_length_exceeded` 与受控 OLD 多 provider overflow message 信号，并提升为
`context_compaction_requested` 与 recoverable `run_failed("context_compaction_required")`。后续 compact 策略演进，例如保留最近 raw turns
数量、older turns 摘要方式、tool facts / evidence anchors 优先级、`pinned_state` 保护、retry
上限或失败 reason 细分，都不应要求修改 Engine。Engine 的稳定协议依赖只有两项：能发出 overflow
强类型事实；能接受 Host 提供的新 `RunInput` 并再次执行。

P4 当前 context overflow compact 路径是：

```text
Engine / Runner observes context overflow
  -> EngineEvent(context_compaction_requested) 或 recoverable failed(compaction_required)
  -> WorkerProxy
  -> Host append canonical overflow fact
      -> Host CompactCoordinator
      -> 读取 ConversationMemoryStore snapshot
      -> 读取 RunInputBuildTrace 的 included / excluded 诊断
      -> 构造 deterministic compact memory block
      -> 验证 compacted RunInput 确实变短
      -> 验证当前用户问题 / pinned_state / evidence anchors / source cursor / 必保事实保真
  -> Host append compact completed 或 compact failed canonical fact
  -> same Run / new internal Engine attempt
  -> WorkerProxy.stream_engine_events(compacted RunInput)
```

P5 修订目标是把 P1-P4 当前内存态能力串成一条单进程、单调用方、顺序多轮的 no-full-governance 纵向验证路径。
该路径只证明当前 happy path 的事实链路同源协作，不代表生产级 Session / Run lifecycle governance 已落地：

```text
LocalRunHarness.start_run(turn 1)
  -> append USER_INPUT_ACCEPTED
  -> RunInputBuilder.build
  -> LocalProxy -> EngineWorker -> Engine Agent tool loop
  -> model tool_call huge_echo
  -> ToolExecutor.execute
  -> ToolRuntimeToolExecutor -> HostToolRuntime -> huge_echo executor
  -> RuntimeTruncateManager returns truncated ordinary tool result
  -> Engine injects truncated tool result with next_action=fetch_more hint
  -> model tool_call fetch_more
  -> ToolRuntime routes to Host private framework fetch_more tool
      -> fetch_more callable consumes cursor through closure-injected RuntimeTruncateManager Protocol
      -> return next chunk / next cursor hint if needed
  -> Engine final terminal
  -> ConversationMemoryStore.project_run_events
LocalRunHarness.start_run(turn 2 after turn 1 terminal)
  -> RunInputBuilder sees previous user / final / tool facts / source cursors
  -> terminal
compact retry auxiliary case
  -> same Run internal attempt retry
  -> no second USER_INPUT_ACCEPTED
```

P5 同时需要落地最小公共 tool declaration 契约：工具现场可以用
`@tool(..., truncate=ToolTruncateSpec(...))` 同源声明 LLM-facing `ToolSchema`、Host ToolRuntime
`ToolTruncateSpec`、callable / executor binding 与 `ToolDisplayInfo` / `tags` 展示 metadata。该契约只提供
`ToolDefinition` / `ToolBundle` 与明确的 `ToolSchema` projection；进入 Engine / Runner / WorkerProxy request
的仍只能是 `tuple[ToolSchema, ...]`。`ToolTruncateSpec`、display metadata、tags、callable 与 executor binding
不得进入 Engine request。P5 只额外暴露 framework `fetch_more` 的 LLM-facing schema 和执行路由；这不等同于
完整 ToolRegistry / 权限治理 / 业务工具迁移。

P5 手工 smoke 的主路径沿用 `utils/` provider smoke 范式，在脚本内写死
`mimo-v2.5-pro-plan` `ProviderCase`，不读取 `dayu/config/llm_models.json` 或 `workspace/config`；
其中 `MimoThinkingExtension(enabled=True)` 是 hardcoded ProviderCase 的有意选择。该 smoke 真实向 provider
发送 prompt，并要求模型通过 LLM tool calling 调用 `huge_echo`。fake provider / scripted WorkerProxy 只服务
CI integration 与 compact retry 辅助诊断，不能替代真实 provider smoke 的成功证明。

P5 后仍未落地的生产治理包括：`client_request_id` 创建幂等、同 Session active Run admission、多进程恢复、
持久 EventLog / projection、RemoteProxy、Reply Outbox、audit hard-gate、完整 ToolRegistry / 权限治理 /
middleware 与业务工具迁移。

P4 compact 输入只来自 P3 已固定的运行态事实：本 Run 的 `USER_INPUT_ACCEPTED`、canonical overflow /
tool facts、Conversation Memory snapshot、RunInputBuilder included / excluded 诊断与可消费事实。由于
memory projection 只在 terminal 后运行，Host 在 compact 前会从本 Run 当前 EventLog 读取已 append 的
canonical tool facts / evidence anchors，并通过与 memory projection 同源的 helper 临时合并进 compact 输入。
reasoning、preview、delta、content completed、display timeline、客户端展示 transcript、debug sampling
都不得进入 compact 输入，也不得参与 compact 后的 `RunInput` replay。

P4 设计约束：compacted RunInput 是 Host 从既有 `USER_INPUT_ACCEPTED` 与 canonical facts 派生出的治理性
attempt 输入，不是新的用户输入事实。context overflow compact retry 可以在同一 Run 下启动新的 internal
Engine attempt，但不得再次 append `USER_INPUT_ACCEPTED`；memory projection 也不得把 compacted RunInput
记成新的 raw user turn。若实现需要记录 compacted input，只能使用 compact / attempt retry canonical facts
或 Host internal trace 表达，不能伪装成用户输入事件。

Host Memory system block 与 compacted memory block 是 internal grounding context / verification context，
不是 final answer 输出模板。RunInputBuilder 与 P4 compact memory block 当前都会在 block 前部声明
internal-only / not-output-template 约束；RunInputBuilder 会把 `Host Memory`、tool fact summaries、evidence anchors
等内容作为 system role message 注入模型；这些内容只能帮助模型定位事实、校验证据和生成受控来源说明，
不得被原样回显为用户可见的“历史工具摘要”或内部事实表。final answer 可以包含面向用户的“证据与出处”
或引用列表，但不得暴露 Host 内部标题、字段和治理元数据，例如 `Host Memory`、`Tool Facts`、
`Evidence Anchors`、`历史工具摘要`、`tool_fact_id`、`cursor_fingerprint`、`source_event_cursor`、
`tool args`、`tool result repr`、`scope_token` 或 raw EventLog metadata。P4 实施 RunInputBuilder /
compact memory block 时，必须继续保留这些 internal-only 标注。当前 Host 在 `FINAL_ANSWER` 翻译边界
增加最小语义 gate：明显包含上述内部标题、字段或工具结果 repr 标记的 final answer 会被替换为安全
占位内容，并标记 `filtered=True`、`degraded=True`；这不是完整 OutputContract 或 replay 治理。

P4 当前主入口支持若干 leading caller / Agent / app `SystemMessage` 加一条非空 current `UserMessage`，
并拒绝 assistant / tool 历史、多条 user、空 user 或 user 后追加 system。system context
顺序固定为：caller system prompt 保持在最前，Host Memory instructions + Host Memory / compact memory 作为
后续 system context 追加，其后才是当前 UserMessage。Host Memory / compact memory block 的开头必须先
声明 internal grounding / not output template 约束，再渲染 `Tool Facts` / `Evidence Anchors` 或 compact
后等价摘要。若 provider / payload builder 需要把多条 system message 合并成单条 provider payload，
合并文本也必须保持 caller system prompt 在前、Host Memory instructions + Host Memory / compact memory
在后。该顺序既保护 caller system prompt 的语义优先级，也使更稳定的 caller system prompt 形成更稳定的
provider prefill cache / prompt cache 前缀；Host Memory / compact memory 每轮更易变化，放在后面可减少
稳定前缀失效。本设计只把它作为实施约束和优化理由，不宣称已经接入任何具体 provider cache API。

compact 成功不是“执行过压缩”即可成立。Host 只有在 compacted `RunInput` 的估算 token / char size
严格小于 compact 前输入，且当前用户问题、`pinned_state`、必需 stable facts、evidence anchors、
source cursor 与必要 tool facts 保真时，才允许启动下一次 internal attempt。compact no-op、变长、
无法缩短，或必须丢弃当前用户问题、`pinned_state`、evidence anchors、source cursor 才能变短时，
Host 不再重试；它应追加 Host-owned failed terminal 收口，并在 compact failed / exhausted 事实中记录
可解释原因。trace 缓存缺失或 compact 分支异常也必须走 Host-owned compact failed terminal，避免订阅方
停在无终态 Run。

P4 的估算口径应继承 OLD `conversation_memory` 更适合中英文混合财报文本的保守宽 / 窄字符近似：
半角字符按 1 unit、全角 / 宽字符按 2 units 计入，再按 2 units/token 转换为 estimated tokens。
该口径只作为 Host compact / RunInputBuilder 的预算与 before / after 相对比较工具，不是 provider tokenizer
真源；真实 context overflow 仍以 Engine / Runner provider classifier 产出的强类型事实为准。P4 已移除
RunInputBuilder 对 P3 `_APPROX_TOKEN_CHARS=4` 的依赖，RunInputBuilder trace 与 compact before / after
使用同一 Host 内部估算器。

context overflow compact retry 在执行和审计上是新的 Engine attempt：新的 attempt input、新的
worker execution context、新的事件关联与可追溯 compact 决策。但它与普通 transient retry / replay
治理预算应区分；P4 可以使用明确的 compact retry 上限来避免无限循环，不把该局部上限写成 P7 已经
完整落地的 attempt lifecycle governance。

Engine stream 无 terminal 时的 CRITICAL log 与 Host-owned failure terminal 已是 P3 事实。P4 不重复解决
“Engine stream 必须有 terminal”的收口问题，只消费明确的 context overflow / compaction-required
事实并决定是否 compact。

### 12.1 背景

买方财报分析的多轮记忆不是普通聊天历史回放。用户常见追问形态是：

- “那扣非后呢？”
- “换成人民币百万元口径。”
- “和海天比一下。”
- “刚才那个增速再拆一下量价。”
- “这个假设先保留，后面看估值时再用。”

这些追问依赖上一轮的公司、期间、报告类型、会计准则、币种、单位、比较基准、用户假设、工具证据和
已确认结论。如果 Host 只把最近聊天文本塞回模型，模型容易出现三类错误：

- 数字没错但口径漂移，例如从合并口径滑到母公司口径。
- 结论没错但来源丢失，后续无法追到页码、表格、XBRL fact 或工具 chunk。
- 用户假设、模型推断、工具事实混成同一种“历史文本”，后续纠错困难。

因此 Conversation Memory 的目标不是最大化历史回放量，而是：

- 保持任务目标、研究对象、期间、口径和用户约束稳定。
- 把 verified fact、assumption、assistant conclusion、display text、tool large result、reasoning 分开治理。
- 让进入运行态的事实能追到 canonical RunEvent、tool fact 或 evidence anchor。
- 把上下文窗口主要留给当前财报材料、工具检索结果和局部章节，memory 只提供必要连续性。

### 12.2 已识别的结构性问题

OLD conversation memory baseline 已经证明两点：多轮记忆确实能提升追问连续性；运行态 transcript 与
展示态 history archive 必须分离。但旧结构也暴露出若干不适合继续放大的问题。

#### 12.2.1 轮数上限会压制长上下文能力

旧式 `working_memory_max_turns` 语义是“最多回放 N 轮”。这会让 1M / 256K 长窗口模型即使还有预算，也被
固定轮数截断。财报分析的追问链经常跨 6 轮以上，硬上限会让模型忘掉仍可容纳的历史事实。

新设计把该语义反转为 `recent_turns_floor`：最近 N 轮是反退化下限保底，不是上限。预算允许时可以继续
回放更老 raw turn；预算紧张时也至少保留最近语义连续性。

#### 12.2.2 working / episodic 双池会制造预算错觉

旧式 working memory 与 episodic memory 分别有独立预算，调大或调小一个池不会释放另一个池空间。
这让实际可进入模型的 memory 总量难以预测，也容易让 memory 挤占财报材料窗口。

新设计使用历史单总池：除 pinned state 与 recent floor 外，更老 raw turn、tool fact summary、
future episode summary 都在同一历史 pool 内竞争。

#### 12.2.3 assistant final answer 容易被误当事实真源

assistant final answer 是模型表达，不是 verified fact 真源。它可以帮助追问连续，但不能自动升级为
已验证事实。财报数字、口径、来源、引用必须来自 tool fact、evidence-backed projection、
用户显式确认或后续受控 compaction / projection。

#### 12.2.4 用户输入不能只藏在启动参数里

用户输入是一轮 Run 的事实。如果它只存在于 `StartRunRequest.input`，而 tool / final / terminal
都存在于 EventLog，memory projection 和 timeline 会形成两个事实来源。新设计要求用户输入也进入
canonical EventLog。

### 12.3 设计原则

- `pinned_state` 永远全量渲染，不参与 token 池竞争。
- 工具结果即事实，结构化 tool facts、evidence anchors、source references 不能被 LLM
  二次摘要丢失精度。
- 最近 N 轮 raw turn 是追问连续性的保底，不是上限。
- 历史 memory 使用单总池，而不是 working / episodic 两个独立预算池。
- memory 应克制，把大部分上下文窗口留给当前任务所需的外部材料、检索结果和局部上下文。
- compaction 以 context ratio 触发，不以轮数触发。
- Host 只治理记忆结构、来源、状态、作用域和注入顺序，不内嵌财报业务规则。
- display timeline、reasoning、preview delta 与运行态输入严格隔离。

### 12.4 核心概念

#### 12.4.1 `USER_INPUT_ACCEPTED`

`USER_INPUT_ACCEPTED` 是 Host-owned canonical RunEvent，表示 Host 已接受本轮用户输入。它必须在
Engine run / stream 启动前 append。append 失败时不得启动 Engine。

当前事件表达：

- `session_id`。
- `run_id`。
- `turn_id`：P3 最小实现使用 `run_id`。
- normalized user text：P3 从入口 `RunInput` 中唯一一条非空 `UserMessage` 规范化后写入事件。
- memory scope：P3 写入封闭 `UserInputScope.SESSION`。

display timeline、memory projection、RunInputBuilder、future compaction、replay 和 audit 都从 EventLog
读取该事实，不从 preview stream 或展示 transcript 反推。

#### 12.4.2 `TaskFrame`

`TaskFrame` 是当前分析任务的稳定框架。Host 不理解具体财报语义，但可以承载 opaque typed references。
典型内容包括：

- 当前研究对象。
- 当前报告期 / 比较期。
- 当前口径、单位、币种、会计准则、合并范围等引用。
- 当前输出目标和用户约束。
- 当前比较基准，例如同行公司或历史期间。

`TaskFrame` 与 `pinned_state` 同属稳定运行态输入。当前 P3 已落地并可由测试 fixture / internal snapshot
承载；自动抽取和 compaction 更新未落地。

#### 12.4.3 `ConversationPinnedState`

`ConversationPinnedState` 是从 OLD / issue #48 继承下来的会话稳定目标路径。它不是普通历史池成员，
必须在 RunInputBuilder stable layer 中全量渲染。当前四槽是：

- `current_goal`：当前会话目标。
- `confirmed_subjects`：用户或系统已确认的研究对象、比较对象或其他中性 subject 引用。
- `user_constraints`：用户显式给出的口径、格式、限制、假设或偏好约束。
- `open_questions`：仍未解决、需要后续回答或工具验证的问题。

`ConversationPinnedState` 与 `TaskFrame` 并列：前者表达会话目标和用户约束，后者表达分析任务框架引用。
二者都属于 stable layer，不参与 older history pool 竞争。

自动从用户输入、tool facts 或 compaction 产出 pinned state patch 尚未落地；P3 只固定结构、注入路径和
不变量。

#### 12.4.4 `MemoryClaim` 与 `ClaimStatus`

`MemoryClaim` 是可被后续 Run 复用的事实或结论条目。它至少应包含：

- `claim_id`。
- `status`。
- `source_run_id`。
- `source_event_cursor`。
- `evidence_anchor_id`。
- `scope`。
- `created_at`。
- `supersedes`。

`ClaimStatus` 是封闭状态枚举，至少预留：

- `verified`：已验证事实，只能来自 tool fact、evidence-backed projection、用户显式确认或受控 compaction。
- `assumption`：用户假设或待验证假设。
- `assistant_conclusion`：模型表达，可帮助连续性，但不是 verified fact。
- `superseded`：已被后续事实覆盖。
- `rejected`：已确认错误。
- `stale`：可能过期，不能无提示复用。

`assistant final answer` 不是 verified fact 真源。它可以作为 recent raw turn 或 assistant conclusion
参与追问连续性，但不能自动升级为 `verified` claim。只有 evidence-backed tool facts、用户显式确认、
或后续受控 projection / compaction 产出的结构化事实，才能进入 verified claim ledger。

#### 12.4.5 `EvidenceAnchor`

`EvidenceAnchor` 是事实来源锚点。它至少应包含：

- `anchor_id`。
- `origin_event_cursor`。
- `tool_call_id`。
- `source_ref`。
- `chunk_ref`。
- `fingerprint`。
- `summary`。

Host 不解释 `source_ref` 或 `chunk_ref` 的财报业务含义。页码、章节、XBRL fact id、table cell、
quote hash 等应由 fins / tool 侧以 typed reference 或 opaque reference 产生。Host 只保证 anchor
不会被自然语言 summary 替代。

#### 12.4.6 `AssumptionRegister`

`AssumptionRegister` 保存未验证假设和用户临时假设。它与 verified claim 分离。后续用户纠错或工具事实
覆盖时，应通过 claim correction / supersession 把假设转为 verified、rejected 或 superseded。

#### 12.4.7 `UserPreferenceProfileRef`

`UserPreferenceProfileRef` 是用户长期偏好或输出风格的引用位。P3 只预留 slot，不做跨 session durable
preference memory，不在 headless / one-shot Run 中隐式注入用户偏好。跨 user / project / group 的作用域
策略必须等权限和审计设计明确后再落地。

#### 12.4.8 `RunInputBuildTrace`

RunInputBuilder 必须产生 internal-only build trace，用于测试、debug 和未来 audit observer。trace 至少记录：

- included facts / excluded facts。
- exclusion reason，例如 budget、scope mismatch、producer policy、missing evidence、oversized raw turn。
- `source_run_id`、`source_event_cursor`、claim id、anchor id。
- pinned state、verified claims、assumptions、tool facts、raw turns、older pool、future episode summary
  插入位的估算 char / token size。
- budget limit 与裁剪后总估算 size。

build trace 不进入 `RunInput`，不进入 memory pool，不作为下一轮 projection 真源，也不是 public API。

### 12.5 最终方案

Conversation Memory 分为两层：

```text
[Conversation Memory]
├── pinned / stable layer                         ← 永远全量，不参与历史 token 池
│   ├── pinned_state
│   ├── task frame
│   ├── verified claim ledger
│   ├── assumption register
│   └── user preference profile ref / slot
└── history single pool                           ← 单总池，克制使用
    ├── evidence anchors / tool fact summaries
    ├── recent raw turns                          ← 语义保底，不是上限
    ├── older raw turns                           ← 按预算从新到旧
    └── future episode summaries                  ← P4+ 插入位
```

这里的“单总池”不是把所有记忆压成一个大杂烩，也不是否定常见的四层记忆架构。Dayu 后续实现应按
以下口径吸收四层方案：

- `stable layer`：`pinned_state`、`TaskFrame`、verified claims、assumptions 等稳定事实全量注入，
  不参与历史池竞争；但它们仍计入总上下文估算，避免无限膨胀。
- `recent floor`：最近 N 轮 raw turn 是追问连续性的语义保底。它不是“最多 N 轮”，也不是超大旧轮
  原文无限保底；超大 turn 必须降级成 intent / final summary / evidence anchors。
- `history candidate pool`：older raw turns、tool fact summaries、future episode summaries、future
  retrieval hits 都作为候选项进入统一排序和预算竞争，避免 working / episodic / retrieval 各有固定小
  预算导致总窗口失控。
- `retrieval index`：历史 turn、episode summary、tool result chunk、evidence anchor 可进入向量 /
  BM25 / hybrid retrieval；当前 run 只把相关 retrieval hit 作为候选项拉回，而不是无条件塞入完整摘要。

后续实现不要把 P3 的 single pool 理解为“实现一个全局列表然后按时间截断”。正确方向是：stable facts
先强约束，recent floor 保连续性，剩余历史候选再用 ranking 信号竞争预算。ranking 至少应考虑：

- 与当前 user input / task frame / open questions 的相关性。
- item 类型与信任等级，例如 verified claim、assumption、tool fact、raw turn、episode summary。
- 来源与可追溯性，例如 `source_run_id`、`source_event_cursor`、`EvidenceAnchor`、producer kind、
  ingestion policy。
- 时效性与作用域，例如 session / project / user scope、是否 stale / superseded / rejected。
- token 成本与信息密度，例如完整 raw turn、摘要、retrieval hit、tool chunk 的单位预算收益。

这意味着后续 P4 / P5.5 / P6+ 的实现重点不是“再加几个池”，而是建立可解释的候选生成、ranking、
trace 和回归测试。每次排除候选项都必须能在 `RunInputBuildTrace` 或后续 projection trace 中说明原因，
否则财报分析场景下无法解释“为什么忘了这个假设 / 为什么没有召回这条证据”。

运行态输入构造边界：

```text
StartRunRequest.input（仅作为 ingress 材料）
  -> append USER_INPUT_ACCEPTED
  -> RunInputBuilder
      -> USER_INPUT_ACCEPTED RunEvent
      -> ConversationMemorySnapshot
      -> RunInputBuildTrace
  -> RunInput(messages=...)
  -> Engine
```

展示读取边界：

```text
RunEventStore canonical + preview events
  -> display timeline read model
  -> client
```

display timeline 不是 RunInputBuilder 输入。当前 P3 已通过投影与 builder 测试保证 reasoning、preview delta、
content delta、content completed 不进入 memory pool 或 RunInput replay；debug sampling / timeline observer
尚未落地。

### 12.6 RunInputBuilder 输入顺序

RunInputBuilder 的输出是 Engine 已经理解的 `RunInput.messages`。它不能读取 `RuntimeTruncateManager`
cursor store，不能持有 legacy public `fetch_more` handle，不能消费 `scope_token`、cursor 原文、
完整大工具结果或 reasoning。

当前 P3 运行态输入顺序：

```text
system message: [Host Memory]
   -> pinned_state / task frame（全量，独立）
   -> verified claim ledger
   -> assumption register
   -> evidence anchors / tool fact summaries
   -> recent raw turns（语义保底）
   -> older history pool
   -> episode summary 插入位（当前只占位，不生成 summary）
-> current user message
```

P4 及后续若支持 caller / Agent / app system prompt，实施顺序必须扩展为：

```text
system message: [caller / Agent / app system prompt]
system message: [Host Memory or compact memory]
   -> internal grounding / not output template instruction
   -> pinned_state / task frame（全量，独立）
   -> verified claim ledger
   -> assumption register
   -> evidence anchors / tool fact summaries
   -> recent raw turns（语义保底）
   -> older history pool / compacted summaries
-> current user message
```

如果 provider 只能接收单条 system message，payload builder 的合并文本必须保持上述先后顺序；测试应覆盖
RunInput message ordering 与合并文本 ordering。caller system prompt 通常更稳定，放在前缀有利于 provider
prefill cache / prompt cache 的稳定前缀；Host Memory / compact memory 与工具事实更容易逐轮变化，应放在
后段以减少稳定前缀失效。这里是设计约束，不表示当前 P3 已经落地 caller system prompt 支持或具体 provider
cache API。

最近 N 轮 raw turn 是追问连续性的语义保底，不是旧轮全文的无限 token 保底。若某轮包含超大用户粘贴、
长工具结果或长回答，RunInputBuilder 应保留可指代的 intent、final 摘要和 evidence anchors，而不是
让旧轮全文挤占当前财报材料窗口。

### 12.7 总池消费与 compaction 触发

Conversation Memory 使用单总池。`pinned_state`、task frame、verified claims、assumptions 等 stable layer
不参与历史池竞争，但它们仍应被纳入总上下文估算，避免无限膨胀。

历史池消费顺序：

```text
budget = clamp(window * memory_ratio, memory_floor, memory_cap)

1. stable layer 全量渲染，不扣 history pool budget
2. recent raw turns 至少保留语义代表，不作为轮数上限
3. evidence anchors / tool summaries 与 older raw turns 进入单总池
4. future episode summaries 使用剩余预算
5. 超大 raw turn 降级为 intent / final summary / anchors，不全文保留
```

compaction 触发应以 context ratio 为主，而不是轮数：

```text
window_used =
    system_prompt
  + stable_layer
  + recent_semantic_floor
  + history_pool
  + current_user_input

should_compact = window_used > max_context_tokens * compaction_trigger_context_ratio
```

P3 不实现完整 compaction；P4+ 接入时必须保留 stable layer 的全量路径、claim status、evidence anchors
和 supersession 关系，不能把它们压成不可追溯自然语言。

### 12.8 来源、作用域与生产者边界

每条 memory item 应携带最小 provenance / scope 元数据，例如 `source_run_id`、`source_event_cursor`、
`producer_kind`、`ingestion_policy`、`memory_scope`。P3 可以只实现 `session` scope，但类型设计要避免
未来扩展 direct / group / project / user memory 时推倒重来。

P3 默认 ingestion policy：

- 只接纳主 session 的 canonical user / tool / final / terminal facts。
- internal helper、subagent、future compaction、background run 不能默认进入主 session memory。
- compaction / subagent 以后若要写入 memory，必须显式转换 producer kind、trust level 和 ingestion policy。

scope 规则：

- P3 只实现 `session` scope，store key 至少包含 `session_id`。
- 类型上预留 `direct_user`、`group`、`project`、`user` 等 scope。
- 预留 `owner_ref`、`project_ref`、`visibility` 等字段。
- 不同 `session_id` 不能互相读写 memory。

### 12.9 纠错、遗忘与重置

财报分析中的纠错是常态。用户可能说“刚才那个公司不是 A，是 B”“这个 WACC 假设先删掉”“换成 IFRS
口径重算”。因此 memory 不能只追加自然语言修正。

当前 P3 已预留 internal patch 形状：

- `claim_correction`：修正旧 claim，并通过 `supersedes` 或等价字段标记旧 claim。
- `memory_reset`：重置本 session memory 的内部指令形状。
- `scope_clear`：未来按 scope 清理 memory 的内部指令形状。

P3 不暴露 public forget / reset API，不做 UI，不做持久治理；但数据结构必须允许后续 P7 / P6 / P5.5
接入这些能力。

### 12.10 P3 最小落地与后移能力

P3 已落地单进程、顺序多轮的最小 memory projection，并预留以下结构：

- `USER_INPUT_ACCEPTED` canonical event。
- Host 中立 `ConversationPinnedState`、`TaskFrame`、`MemoryClaim`、`ClaimStatus`、`EvidenceAnchor`、
  `AssumptionRegister`、`UserPreferenceProfileRef`。
- `RunInputBuildTrace`。
- session scope 与 producer / ingestion policy 元数据。
- `claim_correction`、`memory_reset`、`scope_clear` internal patch 形状。

P3 当时仍未落地、但 P4 已补齐当前最小路径：

- context overflow compact / retry：P4 已落地 Host-owned deterministic compact、同 Run internal attempt retry、
  terminal 前工具事实临时合并与必保事实保真验证；它仍不是完整生产 context governance。

当前仍未落地：

- episode summary 生成。
- `ConversationPinnedStatePatch` 三态合并、完整 supersession、public forget / reset API。
- persistent EventLog projection、observer checkpoint、audit / timeline 派生。
- 用户可编辑 memory、跨 session / project / user 作用域策略、group/direct 隐私治理。
- domain fact ledger 的自动抽取、冲突检测和长期 retrieval index。

这些能力未落地前，不得把 in-memory Session memory 描述为生产级持久记忆，也不得把 Host 业务中立的
typed reference 扩展成 Host 内嵌财报业务规则。

### 12.11 验收不变量

Conversation Memory / RunInputBuilder 的实现必须满足以下不变量：

- 用户输入只从 canonical `USER_INPUT_ACCEPTED` 进入 memory projection 和 RunInputBuilder。
- assistant final answer 不自动升级为 verified claim。
- evidence anchors 不被自然语言 tool summary 替代。
- Host Memory system block、Tool Facts、Evidence Anchors 与 compacted tool fact summaries 只作为 internal
  grounding / verification context，不作为 final answer 模板或用户可见“历史工具摘要”。
- final answer 可以输出面向用户的证据与出处，但不得 echo `Host Memory`、`Tool Facts`、`Evidence Anchors`、
  `历史工具摘要`、`tool_fact_id`、`cursor_fingerprint`、`source_event_cursor`、`tool args`、
  `tool result repr`、`scope_token` 或 raw EventLog metadata。
- reasoning / preview / delta 不进入 `RunInput`、memory pool、verified claim ledger 或 compaction 输入。
- recent floor 是语义保底，不是“最多 N 轮”，也不是超大旧轮全文无限保底。
- RunInputBuilder 与测试使用同一生产路径；测试不能伪造一条比生产更干净的 path。
- Host 不 import `dayu.fins`，不理解财报业务规则。
- Engine 不 import Host memory，不理解 claim、anchor、scope 或 compaction。
- build trace 不进入模型上下文，不成为下一轮事实真源。
- P8-S8 起 production path 使用 `DurableConversationMemoryStore`；tests-only
  `FakeInMemoryConversationMemoryStore` 只服务最小单进程 smoke，不宣称持久化、多进程或生产正确性。

## 13. Reply Outbox

Reply Outbox 重要，但必须与 Run 隔离。Run 负责产出执行事实与结果；Reply Outbox 负责外部信道
投递、claim、delivered / failed、幂等 key 与重投治理。

Reply Outbox 可以引用 `session_id`、`run_id`、`result_id` 或 delivery key，但不成为 Run
状态机的一部分。

### 13.1 Outbox 状态机

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

设计约束：

- claim / lease 必须支持多进程并发。
- delivery key 必须支持幂等，避免 WeChat / Web 重复投递。
- delivery key 至少应包含 channel、recipient、session_id、run_id、result_id 或等价维度；
  不同外部信道或不同接收方不能共享同一个投递幂等 key。
- stale `CLAIMED` / `DELIVERING` 需要 cleanup 或 lease 过期回到 `READY` / `RETRY_WAITING`。

### 13.2 Final Answer 到 Outbox 的可靠投影

必须防止 `final_answer` 已产生但 `ReplyOutbox` 未落库的丢失窗口。

硬约束：

- `Run final_answer` 到 `ReplyOutbox` 必须通过可靠投影连接。
- 不能依赖 best-effort 旁路写入。
- 如果 `RunResult` 或 `final_answer` event 已存在而 `ReplyOutbox` 缺失，系统必须能通过
  EventLog / RunResult reconcile 补出 Outbox。
- Outbox projection 必须幂等，避免重放时重复投递。

当前倾向采用 EventLog / RunResult projection reconciler：

```text
append run_final_answer event
append run_succeeded event
projection worker 读取 final_answer / result
upsert ReplyOutbox by delivery_key
```

具体实现留到 Reply Outbox 阶段。

## 14. 后续设计点

以下内容不阻塞当前 Host 核心架构，但进入实现前需要单独设计：

- Steer：active Run 上的追加输入，可后加。
- Attempt lease / fencing 细节（P8-S1 至 P8-S6 已落地 attempt-scoped lease、fencing、terminal atomic
  close、recovery scan 与 attempt-scoped append；recovery scan 自动装配到生产启动链路仍未落地）。
- 取消治理增强：watchdog、取消超时升级、强制终止和资源可观测收口，后移 GitHub issue #3。
- RemoteProxy / RemoteStub wire protocol。
- ToolRuntime 完整治理面。
- EventProjection / Observers：tool trace、audit、metrics、alerting、projection checkpoint 与
  sink schema。
- Context overflow / compaction 与 Engine 协作。
- Wait / suspend：状态机与强类型契约已预留，具体 wait record / monitor / resume 治理按 issue #4
  拆子设计，不在 Engine 内单独实现半截 suspend。
- Reply Outbox projection 事务 / reconciler 细节。
- `docs/code_review.md` Host 当前事实专项：等第一段 Host 代码落地后再更新。
