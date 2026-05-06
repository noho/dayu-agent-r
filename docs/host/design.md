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

## 4. 候选架构

当前 Host 候选分解：

```text
UI -> Service -> Host

Host
  - SessionManager
  - RunManager
  - RunSupervisor
  - AttemptSupervisor
  - ContextBuilder / MemoryManager
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
- `ContextBuilder / MemoryManager`：从 Session transcript、memory、tool facts 等事实构造 Attempt 输入。
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
- `list_session_timeline` 是客户端聊天记录读取接口，返回展示 read model，不是 ContextBuilder 输入。

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
没有机会流回 `ContextBuilder / MemoryManager`，也不得参与 `RunInput` 重放。客户端
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
- `Attempt` 状态机包含 `CANCELLING`、`STALE` 与 `LOST`，支持后续 watchdog、超时升级和 owner 失活调和。
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

候选状态：

```text
CREATED
LEASED
STARTING
RUNNING
SUSPENDED
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
CREATED -> LEASED -> STARTING -> RUNNING -> SUSPENDED
CREATED -> LEASED -> STARTING -> RUNNING -> CANCELLING -> CANCELLED
CREATED / LEASED / STARTING / RUNNING / SUSPENDED / CANCELLING -> STALE
CREATED / LEASED / STARTING / RUNNING / SUSPENDED / CANCELLING -> LOST
```

实现阶段必须细化：

- lease / fencing token。
- 旧 owner 迟到写入的拒绝规则。
- attempt event 与 run event 的映射。
- stale attempt 是否必然触发 Run `RECOVERING`。

`SUSPENDED` 是 issue #4 的预留状态：表示 Engine / ToolExecutor 协作产生等待事实后，
当前 attempt 已停止继续执行，Run 进入 `WAITING`，后续由 Host wait record 完成、取消、超时或丢失治理。

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

### 9.0 当前 P1.5 最小实现路径

P1.5 已将最小 EventLog 语义接入当前 `run harness` 主链路。当前路径是：

```text
start_run
  -> LocalRunHarness._run_to_store
  -> WorkerProxy.stream_engine_events
  -> EngineEvent
  -> translate_engine_event -> RunEventDraft
  -> RunEventStore.append -> cursor-bearing RunEvent
  -> RunStream.events / stream_run_events
```

当前实现要点：

- `RunStream.events` 与 `stream_run_events(run_id, after=cursor)` 都是 `RunEventStore` 的订阅视图。
- `RunEvent` 必须先 append 到 store，获得 Host 分配的 per-run cursor 后，才能被事件流观察到。
- `RunEventCursor` 由 Host store 生成，不绑定 Engine sequence。
- `RunEventDraft` 只表示待 append 的内部草稿；对外可消费的事实是已 append 的 `RunEvent`。
- terminal `RunResult` 只从已 append 的 canonical terminal `RunEvent` 推导。
- worker / proxy 异常导致 Host 无法获得 Engine terminal event 时，Host 追加 Host-owned canonical
  failure `RunEvent`；Host 自身翻译、append 或 terminal result 推导错误不能伪装成 worker / proxy failure。

当前 `InMemoryRunEventStore` 是 `RunEventStore` 的单进程临时 adapter，只服务 P2-P5 smoke 与测试：

- 它固定 append-before-stream、per-run cursor、exclusive replay、canonical / preview、terminal fact 等
  最小 EventLog 语义。
- 它不提供持久化 schema、多进程一致性、startup recovery、observer checkpoint、trace / audit /
  timeline / outbox projection。
- P6 落地真实持久 EventLog 时，应复用同一 `RunEventStore` 语义并扩展生产能力，而不是废弃 P1.5
  契约后另起事实来源。

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
- 多进程下 observer claim / lease 必须带 owner token / fencing，避免多个进程同时写同一 sink。
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
    fencing_token: str

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

ToolRuntime 的具体治理面后续单独设计。设计时必须保持：

- Host / Engine 不懂业务。
- tool execution runtime 与业务权限 / 业务规则分离。
- 财报文档访问约束由业务工具 / tool 边界保证，不进入 Host / Engine 业务语义。
- truncate / fetch_more / cursor / TTL / scope token 后续归 ToolRuntime 相关阶段设计。

ToolRuntime 最小生命周期事实需要预留，但不在当前阶段展开具体权限模型：

- tool call proposed。
- approved / denied / deferred。
- started。
- completed。
- failed。
- truncated / fetch_more。
- cancelled / timeout。

这些事实可以投影为客户端可见 tool summary、内部 audit event 或 trace event。Host 只治理运行边界、
生命周期和资源收口；具体工具权限、业务权限和业务规则由 ToolRuntime policy / tool 侧契约表达。

ToolRuntime 不直接等同于 tool trace。ToolRuntime 负责产生和治理工具运行事实；tool trace 是
EventProjection / Observers 从这些事实派生出的可观测性记录。这样可以让审计、指标、告警和调试采样
复用同一事件订阅边界，而不是在 ToolRuntime / Engine 内分别写一套落盘逻辑。

## 12. Conversation Memory / ContextBuilder

Conversation Memory 属于 Host 上下文治理，不属于 Engine，也不应污染 Host 最小 public interface。

后续设计以 OLD issue `https://github.com/noho/dayu-agent/issues/48` 为强参考：

- `pinned_state` 永远全量渲染，不参与 token 池竞争。
- 工具结果即事实，结构化 tool facts、evidence anchors、source references 不能被 LLM
  二次摘要丢失精度。
- 最近 N 轮 raw turn 是追问连续性的保底，不是上限。
- 历史 memory 使用单总池，而不是 working / episodic 两个独立预算池。
- memory 应克制，把大部分上下文窗口留给当前任务所需的外部材料、检索结果和局部上下文。
- compaction 以 context ratio 触发，不以轮数触发。

ContextBuilder 消费 Session transcript、memory、tool facts、steer 等事实构造 Attempt 输入。
客户端 transcript read model 不等同于运行态上下文全量回放。

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
- Attempt lease / fencing 细节。
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
