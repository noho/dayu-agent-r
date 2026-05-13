# Host 设计

## 1. 设计目标

Host 的设计目标是支撑生产级买方财报分析 Agent。系统范式是“宿主强约束下的 LLM in the loop”：

- Host 是 Session / Run / Attempt / EventLog / admission / cancel / resume / retry / steer / replay / memory / tool governance 的治理真源。
- Engine 只执行单次 `AgentRunRequest`，不拥有 Session / Run 生命周期，不持久化 Host 状态，不恢复旧 Agent / Runner。
- 多入口 interactive / web / GUI / CLI / WeChat 共享同一本地 Host 真源。
- 支持单机多客户端 / 多进程，并支持本地 Engine 与远程 Engine 并列执行。

Host 设计必须优先保证：

- durable facts 可恢复。
- 同一 Session 的执行并发受控。
- 远端执行环境不能拥有 Host 状态。
- 工具执行受 Host / ToolRuntime 治理，包括截断、等待、幂等与语义级重复调用治理。
- 工具事实、证据锚点和审计链可追溯。
- assistant final answer 不自动成为 verified fact。

## 2. 分层边界

整体依赖方向固定为：

```text
UI -> Service -> Host -> Engine
```

边界职责：

- UI 负责展示、输入收集、流式订阅和用户动作触发。
- Service 负责业务入口、身份解析、场景装配和调用 Host。
- Host 负责 Agent 运行宿主边界、状态治理、持久化、工具运行时治理、memory / context governance 和 projection。
- Engine 负责单次 run 的模型交互、Runner 协议归一、tool loop 和 EngineEvent 流。

禁止反向依赖：

- Engine 不读取 Host durable store，不理解 Host policy，不管理 Session / Run / Attempt。
- Host 不承载财报业务语义，不直接管理财报原文仓储规则。
- Service 不能绕过 Host 直接控制 Engine。
- Projection、timeline、audit、usage、tool trace、outbox、memory snapshot 都不能反向成为 EventLog 真源。

Host 内部模块边界：

- Public API layer：只负责 request / context validation、幂等查找与调用稳定服务；不得直接拼 messages、启动 Engine 或写 projection。
- Admission / Queue：唯一负责 Session active Run 判定、queued Run promotion 与 CAS-style admission。
- EventLog / State Transition：唯一负责 EventLog append、`event_sequence` 分配，以及 `canonical_fact` 对 Run / Attempt 索引的原子更新。
- Attempt Dispatch：只消费已提交的 dispatch record / attempt snapshot，负责 LocalProxy / RemoteProxy 派发与 cancel 传播；不得生成治理事实。
- EngineEvent Ingest：唯一负责把 Engine / Worker / ToolRuntime 回传事件验证、分类并转成 Host event。
- RunInputBuilder：唯一负责通过 typed input provider protocols 聚合 EventLog、memory snapshot、compact artifact、tool schema snapshot 与场景约束，构造 `AgentRunRequest.messages`。
- Conversation Memory：只消费 committed canonical EventLog facts，维护 session memory snapshot、stable layer 与 history pool；它是可重建 projection / read model，不是事实真源，不直接写 EventLog，也不由 Context Governance 直接写入。
- Context Governance：唯一负责上下文预算、compact 编排与 compact 事件收口；它是治理 orchestrator，不直接写 memory、audit、trace 或其它 projection。
- ToolRuntime / TruncationManager：唯一负责工具执行治理、截断、`fetch_more`、等待与重复调用治理；工具事实必须走 Host accept barrier。
- Observer / Sink / Projection：只消费 committed EventLog events，维护派生视图和外部投递队列。
- Recovery：唯一负责 Host startup scan、旧 Attempt `LOST` 收口和可恢复 Run 的新 Attempt 创建。

这些模块可以在实现中进一步拆分，但不能互相绕过上述 ownership。尤其是 dispatch、sink、tool runtime 和 remote stub 都不能直接写 Run / Attempt / EventLog。

## 3. dayu.runtime

`dayu.runtime` 是层中立运行期基础设施包，不属于 `UI / Service / Host / Engine` 任一业务层。它只能承载运行期通用、可被多层复用的基础能力；不得承载业务语义、财报语义、Host durable truth、Host 状态治理或 Engine 协议状态机。

`dayu.runtime` 不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。各层需要公共运行时能力时，应优先复用或扩展 `dayu.runtime`，不得在各层自行实现语义不一致的 runtime helper。

当前 Host 设计需要记录的 runtime / external assembly 基础组件：

- `lane`：层中立 cross-process named semaphore / capacity guard，用于单机多客户端 / 多进程下的业务并发、LLM 并发或其它非真源资源容量治理。lane 只表达资源容量，不表达 Session / Run / Attempt owner，不替代 Host admission、SQLite transaction、CAS 状态迁移、EventLog ordering、fencing token、Attempt takeover 或 recovery proof。LLM lane acquire 是可取消的耗时操作；调用方 / supervisor 退出时必须同时触发 Host cancel 与 lane cancel，避免等待 acquire 或已持有容量的 dispatch guard 悬挂。Host 如何使用 lane 控制 LLM 并发的细节属于后续 phase design。
- `filelock`：`dayu.runtime.filelock` 对 `from filelock import FileLock` 的同步统一封装，用于多进程访问普通文件时的互斥保护。filelock 不能表达 Host durable truth、EventLog ordering、Run / Attempt owner，也不能兜底数据库事务。
- `ToolsDiscovery`：暂定名，独立于 Host 的工具发现 / 注册组件。它收集工具声明、provider 或配置绑定，生成业务 `ToolBundle` 并作为显式参数传给 Host。Host 不做工具发现、模块扫描或注册生命周期管理。若放入 `dayu.runtime`，它只能依赖 `dayu.contracts` 与标准库，不得 import 具体业务工具包；具体 provider 由外部装配传入。
- `ScenePrepare`：独立于 Host 的场景准备组件。它根据 scene manifest 组装 system prompt 与场景约束，产出可由 Service / Host request envelope 显式传入的 typed scene inputs。Host 不从 scene manifest 自行拼业务 prompt，也不把场景规则写进 Host 状态机。若放入 `dayu.runtime`，它只能是通用 manifest assembly helper；具体财报 scene manifest、业务 prompt 文案和场景策略属于 Service / 业务配置，不属于 runtime。

这些组件服务 Host 装配，但不提升为 Host 治理真源。Host 真源仍是 Session / Run / Attempt / EventLog 与同事务状态索引。

Phase 1 的 runtime 实施范围只包括 `lane` 与 `filelock` 的层中立基础能力，以及 Host construction input 中对外部 `ToolBundle` 的 typed 边界。`ToolsDiscovery` / `ScenePrepare` 在 Phase 1 只固定 import boundary 与责任边界，不落地具体 adapter、manifest schema、业务工具扫描、财报 prompt 组装或 provider 注册生命周期；这些能力若需要代码实现，必须作为独立后续 phase 进入 design refinement。

### 3.1 `dayu.runtime.lane`

`dayu.runtime.lane` 第一版是层中立、cross-process 的 async named semaphore / capacity guard primitive。它用于单机多客户端 / 多进程下对 LLM provider 调用、外部 API 调用、CPU / IO worker 等非真源资源做容量保护。它提供同一机器、同一 runtime lane coordinator 下的跨进程容量计数；跨进程 Host admission、Run / Attempt owner、EventLog ordering、SQLite CAS、fencing token、Attempt takeover 和 positive orphan proof 仍属于 Host durable store / Host 状态机 / recovery phase。

第一版 coordinator 使用独立 runtime SQLite 文件实现，原因是：

- 单机多进程容量计数需要原子 compare-and-claim；普通内存 semaphore 不满足项目目标。
- SQLite 是 Python 3.11 标准库能力，可用短事务表达跨进程 claim / release，不引入业务层依赖。
- 该 SQLite 文件是 `dayu.runtime.lane` 的资源容量协调器，不是 Host durable store；不得复用 Host EventLog / state index 数据库，也不得被 Host recovery 当作 truth。
- `dayu.runtime.filelock` 可作为普通文件互斥 wrapper，但不能提供 capacity claim 的可查询状态、TTL cleanup 和原子计数，因此不作为 lane 第一版 coordinator。

第一版 public API shape：

```text
@dataclass(frozen=True, slots=True)
LaneConfig
  name: str
  capacity: int
  default_timeout_seconds?: float
  claim_ttl_seconds: float
  heartbeat_interval_seconds: float

@dataclass(frozen=True, slots=True)
LaneOwner
  owner_id: str
  pid: int
  process_start_token?: str

@dataclass(frozen=True, slots=True)
SQLiteLaneCoordinatorConfig
  db_path: Path
  create_parent_dirs: bool = true
  busy_timeout_seconds: float
  poll_interval_seconds: float

@dataclass(slots=True)
LaneClaimToken
  name: str
  claim_id: str
  owner: LaneOwner
  expires_at: datetime
  refresh() -> Awaitable[None]
  release() -> Awaitable[None]
  released: bool

@dataclass(frozen=True, slots=True)
LaneAcquired
  token: LaneClaimToken

@dataclass(frozen=True, slots=True)
LaneAcquireCancelled
  reason?: str

@dataclass(frozen=True, slots=True)
LaneAcquireTimedOut
  elapsed_seconds: float

LaneAcquireOutcome = LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut

LaneController
  open(configs: Sequence[LaneConfig], *, coordinator: SQLiteLaneCoordinatorConfig, owner?: LaneOwner) -> LaneController
  acquire(name: str, *, token?: CancellationToken, timeout_seconds?: float) -> Awaitable[LaneAcquireOutcome]
  close(reason?: str) -> Awaitable[None]
```

`LaneConfig.name` 必须非空，`capacity` 必须为正整数。`claim_ttl_seconds` 必须大于 `heartbeat_interval_seconds`，且二者都必须为正数。重复 lane name、未知 lane name、非正 capacity、非法 TTL / heartbeat 属于配置错误，必须在 controller construction 或 acquire 前以结构化 runtime error 暴露。Phase 1 不要求全局 registry；调用方显式持有 `LaneController`，避免模块级隐式单例。

Coordinator / store / lock 选择和注入方式：

- `LaneController.open(...)` 必须显式接收 `SQLiteLaneCoordinatorConfig`；调用方传入独立 runtime lane DB 路径，例如 workspace runtime 目录下的 `runtime_lanes.sqlite3`。
- `db_path` 不得默认为 Host durable store 路径，不得从 Host package 读取配置，也不得通过模块级全局 singleton 隐式创建。
- coordinator schema 只允许保存 lane capacity coordination 所需的 rows，例如 lane name、claim id、owner id、pid、process start token、created_at、heartbeat_at、expires_at。不得保存 Session / Run / Attempt / EventLog / Tool / 财报业务字段。
- SQLite transaction 只保护 runtime capacity claim 的原子计数和 release；它不是 Host transaction、不能兜底 Host state machine，也不能被任何层解释为 resource fencing。
- `busy_timeout_seconds` 只限制 runtime coordinator SQLite busy 等待；Host command path SQLite busy policy 属于 Host durable store，不由 runtime lane 决定。

Acquire / release 生命周期：

- `acquire()` 成功时，coordinator 在短事务内先清理同一 lane 中 `expires_at <= now` 的 stale claims，再在 active claim 数量小于 capacity 时插入一条新 claim，返回 `LaneAcquired(token=LaneClaimToken(...))`。
- `claim_id` 必须是不可猜测的随机 id；`owner` 默认由 runtime 根据当前进程生成，也允许上层显式传入稳定 owner id。owner identity 只用于 runtime cleanup / diagnostics，不是 Host owner。
- 只有持有 `LaneClaimToken` 才表示当前 owner 占用了一个 lane 容量。token id 只标识 runtime capacity claim，不得传入 Host EventLog 作为 canonical identity。
- `LaneClaimToken.release()` 必须异步、幂等，并在短事务内按 `(lane_name, claim_id, owner_id)` 删除 claim；重复 release 不得影响其它 owner 的 claim。
- token 持有期间必须定期 heartbeat / refresh，延长 `expires_at`。第一版可以由 `LaneController` 为本进程持有的 tokens 启动 heartbeat task，也可以由 token context helper 驱动；无论实现方式，heartbeat failure 必须让 token 进入不可继续使用的 released / lost 状态，并触发调用方可观测错误或取消。
- 调用方必须用 `try/finally` 或 runtime 提供的 async context helper 持有 token，确保工作完成、失败、取消或 shutdown 时释放容量。
- 第一版以 token 模型为必须实现的 public primitive；可额外提供 async context manager helper，但它只能包裹同一 token acquire / release 语义，不能引入第二套生命周期。

Cancellation / shutdown：

- 等待 acquire 必须可取消：外层 `asyncio.Task.cancel()` 必须透传 `asyncio.CancelledError`，不得吞掉取消；如果传入 `CancellationToken` 且 token 在等待期间命中，返回 `LaneAcquireCancelled(reason=...)`，不得创建 claim。
- `timeout_seconds=None` 表示不设置 acquire timeout；`timeout_seconds=0` 表示 non-blocking acquire；正数表示最多等待对应秒数。timeout 命中返回 `LaneAcquireTimedOut`，不得占用容量。
- cancellation 与 timeout 同时命中时 cancellation 优先，返回 `LaneAcquireCancelled`。
- 等待 acquire 的轮询必须通过 SQLite 短事务重试；不得在一个长事务里等待容量释放。
- `LaneController.close(reason=...)` 用于 supervisor shutdown：它停止接受新 acquire，唤醒仍在等待的 acquire 返回 `LaneAcquireCancelled`，并尝试 release 当前 controller 持有且尚未 release 的 tokens。owner task 仍必须在 `finally` / context manager 中 release；close 的 best-effort release 不能替代 owner task cleanup。
- runtime primitive 不追踪 Host Run / Attempt，因此不能根据 Host cancel 自动释放 token。Host dispatch usage 必须在后续 phase 通过 owner task cancellation 和 durable recheck 组合完成。

Stale owner / timeout handling：

- 如果进程崩溃或 owner task 未能 release，claim 最多占用到 `expires_at`；后续 acquire 会在事务内清理 expired claims。
- stale cleanup 只释放 runtime capacity，不能证明 Host Attempt orphan，不能驱动 Host recovery，不能写 EventLog。
- heartbeat / TTL 不是 lease / fencing。即使某个 expired claim 被清理，也不授权旧 worker takeover，也不证明旧 side effect 已停止。
- clock 使用 runtime injected / stdlib monotonic-to-wall strategy 必须保证同一 process 内 TTL 计算一致；跨进程 clock skew 只能影响 resource capacity availability，不能影响 Host truth。

Fairness / ordering / non-goals：

- 第一版不承诺 FIFO、公平性、优先级、权重、队列可观测性或跨 lane ordering；测试不得断言 acquire 顺序。
- 第一版不实现分布式跨机器 rate limit、provider quota accounting、resource cost weighting、fencing token、Attempt takeover、Host recovery proof 或 capacity ownership diagnostics beyond runtime claims。
- lane token 不是 Host truth、不是 lease、不是 fencing token、不是 Attempt owner、不是 dispatch record 状态。
- acquire 成功只表示当前 owner 在 runtime coordinator 中拿到资源容量；执行任何副作用前，Host 后续 dispatch phase 仍必须在短事务内 recheck durable precondition。

Multi-process tests:

- 两个及以上独立 Python 进程使用同一个 lane DB 和同一 lane name 时，总并发 successful claims 不得超过 capacity。
- 一个进程持有 claim 时，另一个进程 `timeout_seconds=0` acquire 同 lane 且 capacity 已满必须返回 timed out。
- 持有 claim 的进程正常 release 后，另一个进程可以 acquire。
- 持有 claim 的进程崩溃或不 heartbeat 后，另一个进程在 TTL 过期并清理 stale claim 后可以 acquire。
- 多进程竞争不能依赖 acquire ordering；测试只断言 capacity invariant 和 eventual acquire / timeout。

Import boundary：`dayu.runtime.lane` 只能依赖标准库（包括 `sqlite3`）、`dayu.contracts.cancellation.CancellationToken` 和同包层中立 helper；不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`，不得持有财报、Host、Engine 或具体 provider 语义。

Phase 1 只实现该 runtime primitive 及其单元测试，不实现 Host dispatch 对 lane 的使用，不实现 LLM provider policy，不修改 Host durable state machine。

### 3.2 `dayu.runtime.filelock`

`dayu.runtime.filelock` 第一版是对第三方 `filelock.FileLock` 的同步 wrapper，用于普通文件访问互斥，例如单进程 / 多进程对 JSONL、临时 artifact 或其它普通文件的短临界区保护。它不能用于 SQLite transaction、EventLog ordering、Host durable truth、Run / Attempt owner、lease / fencing 或 recovery 判断。

第一版 public API shape：

```text
@dataclass(frozen=True, slots=True)
RuntimeFileLockOptions
  lock_path: Path
  timeout_seconds?: float
  create_parent_dirs: bool = true

@dataclass(slots=True)
RuntimeFileLockToken
  lock_path: Path
  release() -> None
  released: bool

RuntimeFileLock
  acquire(timeout_seconds?: float) -> RuntimeFileLockToken
  __enter__() -> RuntimeFileLockToken
  __exit__(exc_type, exc, tb) -> None

file_lock(lock_path: str | Path, *, timeout_seconds?: float, create_parent_dirs: bool = true) -> RuntimeFileLock
```

Sync / async 边界：

- Phase 1 只提供同步 wrapper。它不提供 async file lock context manager，也不在线程池中替调用方隐藏阻塞 acquire。
- async 调用方如需使用 file lock，必须在自己的边界显式决定是否放入 executor，或保证临界区足够短且不会阻塞事件循环关键路径。

Path handling / directory creation：

- `lock_path` 是显式 lock file 路径，不从业务文件路径隐式派生，避免调用方误判保护范围。
- wrapper 必须把 `str | Path` 归一化为 `Path`，并在 `create_parent_dirs=True` 时创建 lock file 的 parent directory。
- `create_parent_dirs=False` 且 parent directory 不存在时，必须返回 / 抛出结构化 runtime file lock error，不得静默退化。

Timeout / error semantics：

- `timeout_seconds=None` 表示等待第三方 `FileLock` 默认的无限等待语义；`timeout_seconds=0` 表示 non-blocking acquire；正数表示最多等待对应秒数。
- 第三方 `filelock.Timeout` 必须被包装为 runtime 自己的 timeout error，避免上层散落直接依赖第三方异常类型。
- lock acquire 失败、路径非法、parent directory 创建失败等必须归一为 runtime file lock error；不得吞异常后让调用方误以为已进入临界区。

Stale lock / reentrancy / release：

- 第一版不实现 stale lock 探测、锁文件删除、owner pid 解析、跨进程 owner takeover 或强制 break lock。发现疑似 stale lock 时只能 timeout / error，由调用方或运维路径处理。
- wrapper 不承诺 reentrant lock 语义；调用方不得依赖同一线程 / 同一进程重复 acquire 的特殊行为。测试不应断言第三方库的 reentrant 细节。
- `RuntimeFileLockToken.release()` 必须幂等；重复 release 不得抛出误导性错误，也不得释放其它 token。
- context manager 退出必须 release；异常路径也必须 release。

第三方依赖边界：

- 只有 `dayu.runtime.filelock` 可以直接 import `from filelock import FileLock` 及其 timeout 类型。业务层、Host、Service、Fins、工具模块不得各自直接封装或散落 import 第三方 `filelock`。
- 该 wrapper 是纯 infra dependency adapter，不表达 Host durable truth，也不替代数据库事务、CAS、EventLog sequence 或 projection checkpoint。

## 4. 核心对象

Host 治理核心只有四个一等对象：

```text
Session
Run
Attempt
EventLog
```

其它能力，例如 durable queue、wait record、memory snapshot、tool trace、audit、usage、outbox、projection checkpoint，是表、投影或内部机制，不提升为同级治理真源。

对象边界：

- `Session`：一条可持续会话上下文，包含多个 Run。
- `Run`：用户可见的一次 Agent 目标 / 问题 / follow-up，属于一个 Session。
- `Attempt`：Host 为完成某个 Run 派发给本地或远程 EngineWorker 的一次执行，属于一个 Run。
- `EventLog`：append-only event ledger；其中 `canonical_fact` 子集是恢复、memory、audit、outbox 等治理真源，其它 event class 只服务展示、诊断或 projection 输入。

关键不变量：

- Run 是用户可见生命周期；Attempt 是执行生命周期。
- resume、steer、recovery 等同一 Run 内继续执行路径都不复用旧 Attempt；它们在同一个 Run 下创建新 Attempt。
- `retry(run)` / `replay(run)` 不重开原终态 Run；它们创建关联的新 Run，新 Run 再创建自己的 Attempt。
- 每个 Attempt 必须有唯一 `attempt_id` 和 `execution_id`。
- `execution_id` 用于拒绝迟到 Attempt 事件，不是 lease，也不表示远端拥有治理状态。
- 远端执行环境只回传 Attempt 事件，不关闭 Attempt，不更新 Run，不 append EventLog。

### 4.1 Stream 术语约束

文档与实现不得把不同层的流式概念混称为 “stream”。固定术语如下：

- `EngineEvent stream`：EngineWorker 执行 Engine 时产出的事件流，是 Host ingest 的输入来源之一，不是 Host 事实真源。
- `Host event stream`：Host 对 UI / CLI / Web / GUI 暴露的订阅与补读事件流，只能由 EventLog `event_sequence` cursor 派生，不触发执行。
- `preview event`：面向 UI 流式体验的临时事件，可以进入 Host event stream，但不能作为恢复、投递、RunResult、memory 或 audit 的唯一事实来源。
- `preview delta`：模型 content / reasoning / tool-call 的增量片段，只服务展示体验，默认不是 canonical fact。
- `stream fanout`：把已提交 Host events 分发给多个客户端的 projection / sink。慢客户端必须通过 `event_sequence` cursor 补读，不能反压 EventLog append。

## 5. Session 生命周期

Session 状态集合：

```text
OPEN
CLOSED
```

语义：

- `OPEN`：允许创建新 Run、queue follow-up、steer active Run、读取 session timeline。
- `CLOSED`：只读；拒绝新 Run、follow-up、steer。已有 Run 不因 close 被删除或改写。

`close_session` 是归档 / 关闭语义，不删除 EventLog，不清空 memory，不重写历史。

`close_session` 只关闭 Session 的新输入入口，不取消、不终止、不删除已有 Run。`CLOSED` Session 的语义：

- `start_run`、`submit_followup(queue)`、`submit_followup(steer)` 返回 `invalid_state`。
- `ensure_session(scope, slot_key)` 可以返回当前 slot Session，snapshot 标记为 `CLOSED`。
- `create_session` 仍允许创建新 Session；UI / Service 若要继续聊天，应显式调用 `create_session(bind_slot=true, scope, slot_key)` 创建并重绑定新 Session。
- `get_session`、`get_run`、`stream_run_events` 仍允许读取。
- `cancel_run` 仍允许取消已有 Run。
- `resolve_wait` 仍允许让已有 `WAITING` Run 继续收口。
- `retry_run` / `replay_run` 默认拒绝在 closed Session 内创建关联新 Run，除非显式 policy 把新 Run 创建到其它 Session。

已有 active Run 继续按 Host 状态机治理到终态；close 前已 durable accepted 的非终态 Run 继续按原状态机完成。`QUEUED` Run 可在 active slot 释放后 promotion；`WAITING` Run 可在 `resolve_wait` 后 resume；`RECOVERING` Run 可继续 recovery dispatch；`RUNNING` / `CANCELLING` Run 继续收口到 terminal。close 不等于 cancel；若调用方希望停止已有工作，必须显式调用 `cancel_run` 或 `cancel_session_runs`。

`clear_session` 不进入第一版普通公共接口。需要清理、遗忘或重置时，必须分别设计 close / new session / memory forget / purge 等有明确审计语义的接口。

`purge_session` 是第一版 destructive purge API，用于彻底清理一个已经结束且不再需要恢复的 Session 的 Host 本地数据。它不是 close、cancel、archive、memory forget 或 UI hide。

`purge_session` 前置条件：

- Session 必须已经 `CLOSED`。
- Session 不得有 active Run。
- Session 不得有 `QUEUED` Run。
- Session 不得有 `WAITING` / `RECOVERING` / `CANCELLING` Run。
- Session 下所有 Run 必须已经进入终态。

不满足前置条件时，Host 必须返回 `invalid_state`，不得部分删除。

`purge_session` 删除范围包括该 Session 独占的 Host 本地数据：Session / slot binding、Run、Attempt、该 Session 的 EventLog rows、payload descriptors / local payloads、memory snapshot、projection rows、outbox items、tool trace hot data。共享 cold artifact 只有在没有其它 durable ref 引用时才允许被清理。

`purge_session` 是第一版对 EventLog append-only retention 的唯一 destructive exception。它只能在严格前置条件成立后删除该 Session 的可恢复事实，并必须保留最小 purge tombstone / audit record。tombstone 至少包含 `session_id`、purge `client_request_id`、semantic request digest、actor / source / request refs、reason、purge timestamp、precondition digest、deleted counts / digest 和 tombstone id。purge tombstone 不是可恢复 Session fact，不参与 resume、retry、replay、memory 或 RunInputBuilder；它不能位于被 purge 的 Session EventLog 中，必须存入 Host durable store 中可按 `session_id` 查询的 tombstone table 或等价持久区域。

`purge_session` 不删除已经写入的 append-only audit JSONL 记录。purge 必须写入 purge tombstone audit record；既有 audit JSONL 行可以保留对已删除 EventLog rows 的 refs，audit 查询 / analyze 工具必须能识别 purge tombstone，并报告源 EventLog facts 已被 purge。

purge 后该 Session 不再支持 `get_session`、`get_run`、`stream_run_events`、`retry_run`、`replay_run` 或 final answer 恢复。读取接口应返回 `not_found` / `gone` 或 tombstone snapshot；具体错误形状属于 Public API phase。

## 6. Session Slot

Session slot 用于让外部入口回到同一个当前 Session。取得当前会话与显式新建会话是两个不同意图，Host 公共接口必须拆成 `ensure_session` 与 `create_session`。

```text
EnsureSessionRequest:
  scope
  slot_key
  metadata

CreateSessionRequest:
  client_request_id
  bind_slot?
  scope?
  slot_key?
  metadata
```

不变量：

- `(scope, slot_key)` 唯一映射到一个当前 Session。
- `ensure_session(scope, slot_key)` 返回该 slot 当前 Session；如果 slot 尚不存在，Host 原子创建并绑定一个新 Session。
- `ensure_session(scope, slot_key)` 的幂等键是 `(scope, slot_key)`；不同 `client_request_id` 不应改变复用结果，因此该接口不需要 `client_request_id`。
- `ensure_session` 的并发安全必须由 durable store 保证：slot 表对 `(scope, slot_key)` 有唯一约束，Session 创建与 slot 绑定必须在同一事务内完成；并发重复调用必须返回同一个绑定 Session，不得留下孤儿 Session。
- `create_session(client_request_id, bind_slot=false)` 明确创建一个新 Session；同一 `client_request_id` 重试必须返回同一个新 Session，不能重复创建。
- `create_session(..., bind_slot=true, scope, slot_key)` 创建新 Session 后，把 `(scope, slot_key)` 原子重绑定到新 Session；旧 Session 不删除，不改写 EventLog。
- 对同一 `(scope, slot_key)` 使用不同 `client_request_id` 调用 `create_session(..., bind_slot=true)` 表示不同的新建动作，允许创建更新的 Session 并重绑定 slot。
- `scope` 是入口或身份命名空间；`slot_key` 是该命名空间下的会话槽位。
- Host 不把 session slot 当权限模型。认证、授权、外部身份解析属于上层。

示例：

- WeChat 同一稳定身份可调用 `ensure_session(scope="wechat", slot_key=<stable_user_key>)`，重复调用拿到同一个 Session。
- CLI `--label` 可作为 `slot_key`；同一 label 默认调用 `ensure_session` 复用同一 Session。
- UI “新建 session” 调用 `create_session(client_request_id=<click_id>, bind_slot=true, scope, slot_key)`，创建新 Session 并重绑定该 slot。

## 7. Run 生命周期

Run 状态集合：

```text
QUEUED
RUNNING
WAITING
CANCELLING
RECOVERING
SUCCEEDED
FAILED
CANCELLED
LOST
```

Run 终态：

```text
SUCCEEDED
FAILED
CANCELLED
LOST
```

状态语义：

- `QUEUED`：Run 已被 Host durable accepted，但尚未创建 active Attempt。
- `RUNNING`：Run 已占用 Session active slot，并已有 active Attempt lifecycle；active Attempt 可以处于 `STARTING` 或 `RUNNING`。
- `WAITING`：当前 Attempt 已因外部等待条件收口为 `SUSPENDED`，Run 等待 Host 后续 resume。
- `CANCELLING`：Host 已接受取消请求，正在等待 active Attempt 收口或超时升级。
- `RECOVERING`：Host 已确认旧 Attempt 丢失，但用户请求和必要 canonical facts 仍可恢复；Host 正在或等待创建新 Attempt 继续同一 Run。
- `SUCCEEDED`：Run 产出已确认 final answer。
- `FAILED`：Run 已确认不可恢复执行失败。
- `CANCELLED`：Run 已按用户或上层取消请求收口。
- `LOST`：Host 无法恢复该 Run 的用户请求或必要事实，或 policy 明确放弃继续。

`LOST` 不是 `FAILED`。`FAILED` 表示已确认失败；`LOST` 表示治理无法恢复或无法确认，不能伪装成普通失败。

允许且预期存在 `Run.status=RUNNING` 与 `Attempt.status=STARTING` 的组合。Host crash 导致旧 Attempt 丢失时，若用户输入和必要 canonical facts 已持久化，Run 优先进入 `RECOVERING`，而不是直接终态 `LOST`。

## 8. Attempt 生命周期

Attempt 状态集合：

```text
STARTING
RUNNING
SUCCEEDED
FAILED
CANCELLED
SUSPENDED
STEERED
LOST
```

Attempt 终态：

```text
SUCCEEDED
FAILED
CANCELLED
SUSPENDED
STEERED
LOST
```

状态语义：

- `STARTING`：Host 已创建 Attempt，并准备派发到 LocalProxy / RemoteProxy。
- `RUNNING`：EngineWorker 已开始执行，Host 正在接收事件。
- `SUCCEEDED`：Attempt 产出 final answer，Run 可进入 `SUCCEEDED`。
- `FAILED`：Attempt 以确认失败收口，Run 可进入 `FAILED`，或由 Host policy 创建 retry Attempt。
- `CANCELLED`：Attempt 响应 Run cancel 请求收口。
- `SUSPENDED`：Attempt 因工具等待或外部条件挂起，Run 进入 `WAITING`。
- `STEERED`：Attempt 被 steer 打断，Run 保持 active，并由 Host 创建新 Attempt。
- `LOST`：Attempt 的执行结果无法确认。

映射规则：

```text
Attempt SUSPENDED -> Run WAITING
wait resolved -> new Attempt -> Run RUNNING
```

```text
Run RUNNING -> CANCELLING
Attempt RUNNING -> CANCELLED / LOST
Run -> CANCELLED / RECOVERING / LOST
```

旧 Attempt 永不 resume。任何继续执行都必须创建新 Attempt 和新 `execution_id`。

## 9. Admission 与多进程并发

同一个 Session 同时最多一个 active Run。

active Run 状态：

```text
RUNNING
WAITING
CANCELLING
RECOVERING
```

`QUEUED` Run 是 durable accepted run，不占 active slot，但必须持久化。queued run 不是内存队列项；它必须有稳定 `run_id`、`session_id`、`client_request_id`、输入 canonical fact 和 `Run.status=QUEUED`。

新输入 admission：

- `queue`：`submit_followup(queue)` 在同一个 Host admission transaction 内检查 active Run；有 active Run 时输入进入 durable queue，成为后续 Run；无 active Run 时直接创建并启动新 Run。
- `reject`：当前 Session 有 active Run 时，拒绝创建新 Run，并返回 active run conflict。
- `attach_active`：当前 Session 有 active Run 时，返回 active Run，不触发新执行。
- `steer`：必须命中 active Run precondition；它在同一 Run 内切换 Attempt，不创建新 Run。

幂等不变量：

- `ensure_session` 由 `(scope, slot_key)` 幂等映射到当前 Session。
- `create_session` 由 `client_request_id` 幂等映射到一次明确的新建 Session 动作；绑定 slot 时，同一 `client_request_id` 重试不能重复创建或重复重绑定。
- `start_run` 由 `(session_id, client_request_id)` 幂等映射到同一个 Run。
- queued follow-up / queued run 也必须按 `(session_id, client_request_id)` 幂等。
- `cancel_run` 由 `(run_id, client_request_id)` 幂等映射到同一个 cancel 操作。
- `cancel_session_runs` 由 `(session_id, client_request_id)` 幂等映射到同一个 session-scope cancel 操作。
- `retry_run` / `replay_run` 由 `(source_run_id, client_request_id)` 幂等映射到同一个关联新 Run。
- `resolve_wait` 由 `(wait_id, idempotency_key)` 幂等映射到同一个 wait resolution。

多进程持久化方向：

- 第一版使用 SQLite durable store 表达单机多进程真源。
- 多进程一致性依赖 SQLite 事务、唯一约束、CAS-style state transition、`event_id` / `event_sequence` 去重与排序。
- SQLite 使用 WAL、明确 busy timeout 和显式重试策略；具体参数属于 Host storage policy。
- 不引入重 lease / fencing 系统。
- 不做旧 Attempt takeover；不做远端 worker 自治恢复；新执行必须创建新 Attempt 和新 `execution_id`。
- `dayu.runtime.lane` 可作为层中立 named semaphore，被 Host 或其它层用于非真源资源的容量控制；它不能替代 Session active Run admission、SQLite 事务或 CAS 状态迁移。
- `dayu.runtime.filelock` 是对 `from filelock import FileLock` 的统一封装，只用于多进程访问普通文件时的互斥保护；不得用 file lock 表达 Host durable truth、EventLog ordering 或 Run / Attempt owner。

durable queue promotion：

- 同一 Session 的 queued Run 按 accepted `event_sequence` FIFO promotion。
- promotion 只在该 Session 没有 active Run 时发生。
- promotion 与 `RUN_STARTED`、`ATTEMPT_STARTED`、Attempt row 创建、dispatch record 创建必须在同一事务中完成。
- 多进程竞争 promotion 时，只有一个事务能通过 CAS 抢占该 Session 的 active slot；其它进程必须重新读取状态。
- active Run 进入终态、`RECOVERING` 成功恢复、或 Host 启动 recovery scan 后，都必须触发一次同 Session queue promotion check。
- promotion 与 `cancel_run` 竞争时使用 CAS first-committer-wins。promotion 先提交时，Run 已变 `RUNNING`，后到 cancel 必须按 active cancel 路径处理；cancel 先提交时，Run 已变 `CANCELLED`，后到 promotion 必须 CAS 失败并放弃创建 Attempt。
- queued Run 被 cancel 时直接进入 `CANCELLED`，不得为了取消而创建 Attempt。

用户输入持久化顺序必须是：

```text
append USER_INPUT_ACCEPTED
append RUN_ACCEPTED / RUN_STARTED or RUN_QUEUED
create Attempt when admitted
commit
dispatch EngineWorker
```

Host 不允许先 dispatch EngineWorker 再补写用户输入事实。

### 9.1 状态迁移契约

状态迁移必须通过明确操作触发。不得新增隐式后台迁移来绕过 admission、EventLog 或 Attempt 语义。

| 操作 / 来源 | 前置状态 | 目标状态 | 必须追加的 canonical facts | Attempt 动作 |
| --- | --- | --- | --- | --- |
| `start_run` 且无 active Run | Session `OPEN` | Run `RUNNING` / Attempt `STARTING` | `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_STARTED(start_reason=initial)`、`ATTEMPT_STARTED` | 创建新 Attempt；commit 后 dispatch |
| `start_run` 且有 active Run，policy=`queue` | Session `OPEN` | Run `QUEUED` | `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_QUEUED` | 不创建 Attempt |
| `submit_followup(queue)` 且有 active Run | Session `OPEN` | 新 Run `QUEUED` | `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_QUEUED` | 不创建 Attempt |
| `submit_followup(queue)` 且无 active Run | Session `OPEN` | 新 Run `RUNNING` / Attempt `STARTING` | `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_STARTED(start_reason=initial)`、`ATTEMPT_STARTED` | 创建新 Attempt；commit 后 dispatch |
| queue promotion | Run `QUEUED` 且 Session 无 active Run | Run `RUNNING` / Attempt `STARTING` | `RUN_STARTED(start_reason=queue_promotion)`、`ATTEMPT_STARTED` | 创建新 Attempt；commit 后 dispatch |
| Engine final answer | Run `RUNNING` / Attempt `RUNNING` | Run `SUCCEEDED` / Attempt `SUCCEEDED` | `RUN_SUCCEEDED`、`ATTEMPT_SUCCEEDED` | 关闭当前 Attempt |
| Engine failure | Run `RUNNING` / Attempt `RUNNING` | Run `FAILED` / Attempt `FAILED`，或按 policy 进入 retry | `RUN_FAILED`、`ATTEMPT_FAILED` | 关闭当前 Attempt |
| context compaction proactive | Run accepted before Attempt creation / dispatch | Run `RUNNING` / Attempt `STARTING` after compact | `CONTEXT_COMPACTION_REQUESTED(trigger_source=proactive)`、`CONTEXT_COMPACTED`，随后 `RUN_STARTED`、`ATTEMPT_STARTED` | pre-dispatch input governance；不进入 `RECOVERING` |
| context compaction reactive | Run `RUNNING` / Attempt `RUNNING` | Run `RECOVERING`，随后新 Attempt `STARTING` | `CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)`、current Attempt terminal by policy、`RUN_RECOVERING`、`CONTEXT_COMPACTED`、`RUN_STARTED(start_reason=recovery)`、`ATTEMPT_STARTED` | 关闭当前 Attempt；compact 后创建新 Attempt |
| Tool awaiting accepted | Run `RUNNING` / Attempt `RUNNING` | Run `WAITING` / Attempt `SUSPENDED` | `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` | ToolRuntime Host accept transaction 关闭当前 Attempt，持久化 wait record |
| `resolve_wait` | Run `WAITING` | Run `RUNNING` | `RESUME_REQUESTED`、tool terminal/result fact、`RUN_STARTED(start_reason=resume)`、`ATTEMPT_STARTED` | 创建新 Attempt 并 dispatch |
| `submit_followup(steer)` on running | target Run 是当前 active Run，且状态为 `RUNNING` | 同一 Run `RUNNING` / new Attempt `STARTING` | `STEER_REQUESTED`、`ATTEMPT_STEERED`、`RUN_STARTED(start_reason=steer)`、`ATTEMPT_STARTED` | 运行中 Attempt 收口为 `STEERED`；创建新 Attempt；commit 后 dispatch |
| `submit_followup(steer)` on waiting | target Run 是当前 active Run，且状态为 `WAITING` | 同一 Run `RUNNING` / new Attempt `STARTING` | `STEER_REQUESTED`、wait record cancelled with reason `steered`、`RUN_STARTED(start_reason=steer)`、`ATTEMPT_STARTED` | 旧 Attempt 保持 `SUSPENDED`；创建新 Attempt；commit 后 dispatch |
| `cancel_run` on queued | Run `QUEUED` | Run `CANCELLED` | `CANCEL_REQUESTED`、`RUN_CANCELLED` | 无 |
| `cancel_run` on waiting | Run `WAITING` | Run `CANCELLED` | `CANCEL_REQUESTED`、wait record cancelled fact、`RUN_CANCELLED` | 旧 Attempt 保持 `SUSPENDED`；不传播 cancel |
| `cancel_run` on recovering before dispatch | Run `RECOVERING` 且无新 Attempt dispatch committed | Run `CANCELLED` | `CANCEL_REQUESTED`、`RUN_CANCELLED` | 不创建新 Attempt；不进入 `CANCELLING` |
| `cancel_run` on pre-dispatch starting | Run `RUNNING` / Attempt `STARTING` 且 dispatch record `pending` / `waiting_for_lane` | Run `CANCELLED` / Attempt `CANCELLED` | `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED` | 标记 dispatch record cancelled；cancel lane wait；不通知 WorkerProxy |
| `cancel_run` on dispatching / active running | Run `RUNNING` / `CANCELLING` 且 dispatch record `dispatching` 或 Attempt `RUNNING` | Run `CANCELLING`，后续 `CANCELLED` / `WAITING` / `LOST` | `CANCEL_REQUESTED`、`RUN_CANCELLING`，后续 terminal fact | commit 后向当前 Attempt / WorkerProxy 传播 cancel |
| `retry(run)` | Run `FAILED` 或 recoverable failure | 关联的新 Run `QUEUED` 或 `RUNNING` | `RETRY_REQUESTED`、新 Run 的 `RUN_ACCEPTED`，按 admission 追加 `RUN_QUEUED` 或 `RUN_STARTED(start_reason=initial)` / `ATTEMPT_STARTED` | 原 Run 终态不改；新 Run 创建自己的 Attempt |
| `replay(run)` | Run `SUCCEEDED`，且 final answer 格式 / schema / 结构需修复 | 关联的新 Run `QUEUED` 或 `RUNNING` | `REPLAY_REQUESTED`、新 Run 的 `RUN_ACCEPTED`，按 admission 追加 `RUN_QUEUED` 或 `RUN_STARTED(start_reason=initial)` / `ATTEMPT_STARTED` | 原 Run 终态不改；新 Run 默认复用已接受工具事实 |
| recovery scan | Run `RUNNING` / `CANCELLING` 且 active Attempt 不可确认 | Run `RECOVERING` 或 `LOST` | `ATTEMPT_LOST`、`RUN_RECOVERING` 或 `RUN_LOST` | 不 takeover |
| recovery dispatch | Run `RECOVERING` 且可重建 messages | Run `RUNNING` / Attempt `STARTING` | `RUN_STARTED(start_reason=recovery)`、`ATTEMPT_STARTED` | 创建新 Attempt；commit 后 dispatch |

`RUN_STARTED` 表示 Run 进入 active Attempt lifecycle。它必须携带 `start_reason`，第一版枚举为 `initial`、`queue_promotion`、`resume`、`steer`、`recovery`。`start_reason=recovery` 覆盖 crash recovery 和 reactive context compaction recovery；具体原因通过关联的 `ATTEMPT_LOST`、`CONTEXT_COMPACTION_REQUESTED` 或 policy refs 区分。不得用新增的 `RUN_RESUMED` / `RUN_RECOVERED` event 表达同一治理事实。

`RECOVERING` 的退出必须收敛：

- `RECOVERING -> RUNNING`：Host 成功基于 canonical facts 创建新 Attempt，记录 dispatch intent，并让 Attempt 进入 `STARTING`。
- `RECOVERING -> CANCELLED`：用户在恢复期间取消，且没有新 Attempt 已提交 terminal。
- `RECOVERING -> FAILED`：可恢复路径中的新 Attempt 已确认不可恢复失败，或恢复动作本身确认失败且 policy 选择失败收口。
- `RECOVERING -> LOST`：无法重建 messages、必要 payload / anchor 缺失、重复恢复超过 policy 上限，或 policy 明确放弃恢复。

recovery、retry、replay 和 context compaction retry 都必须有 Host policy 上限。默认次数与退避参数属于 Host policy；架构不允许无限重试或无限恢复占用 Session active slot。

Attempt startup 边界：

- `ATTEMPT_STARTED` 表示 Host 已在 durable store 中创建 `STARTING` Attempt，并记录 dispatch intent / dispatch record。
- worker 明确接受 dispatch 后，Host append `ATTEMPT_RUNNING`，Attempt 才进入 `RUNNING`。
- dispatch rejected、startup timeout、dispatch failure、cancel during `STARTING` 都必须关闭 Attempt，并追加明确 Attempt terminal fact。Run 随 Host policy 进入 `FAILED`、`RECOVERING` 或 `LOST`；实现不得把“Host 准备派发”和“worker 已开始执行”混为同一状态。
- `Run RUNNING` 表达 Host 治理生命周期；Attempt `RUNNING` 表达执行环境生命周期。`Run RUNNING + Attempt STARTING` 是合法组合，表示该用户目标已进入 Host 治理执行态，但执行环境尚未确认接住。

标准启动路径：

```text
start_run admitted
  -> append USER_INPUT_ACCEPTED
  -> append RUN_ACCEPTED
  -> append RUN_STARTED(start_reason=initial)
  -> create Attempt(status=STARTING)
  -> append ATTEMPT_STARTED
  -> Run.status = RUNNING
  -> commit
  -> WorkerProxy dispatch
  -> worker accepted
  -> append ATTEMPT_RUNNING
  -> Attempt.status = RUNNING
```

cancel / resolve / promotion 竞态规则：

- `cancel_run` 命中 `WAITING` Run 时，Host 在同一事务内 append `CANCEL_REQUESTED`，标记 active wait record cancelled，append `RUN_CANCELLED`，释放 Session active slot；旧 Attempt 保持 `SUSPENDED`，不重写历史。
- cancel / suspend 竞态由 Host ingest 事务提交顺序决定。terminal fact 已提交时 terminal 胜过后续 cancel；suspend / awaiting 已提交时，后续 cancel 走 `WAITING -> CANCELLED`；cancel 已提交时，后续 suspend / awaiting candidate 不得把 Run 推入 `WAITING`。
- cancel-first 场景下，迟到 `TOOL_AWAITING` / `run_suspended` 只能进入 diagnostic / tool trace 或被拒绝为 canonical fact；Host 不创建 active wait record，并将 Attempt / Run 按取消路径收口到 `CANCELLED`。
- `cancel_run` 与 `resolve_wait` 并发时，先提交事务者赢。cancel 先到则迟到 `resolve_wait` 不得写入 canonical tool result；resolve 先到则 cancel 按最新 Run 状态继续处理。
- `cancel_run` 与 queue promotion 并发时，CAS first-committer-wins，输方必须重新读取 Run 状态并按最新状态处理。
- durable accepted 的 `CANCEL_REQUESTED` 在 terminal fact 之前胜出时，后续 recovery 不得继续用户目标。已取消的 lost Attempt 应按 policy 收口到 `CANCELLED` 或 `LOST`，不得创建新的正常执行 Attempt。

## 10. Durable Store

Host durable store 是本地治理真源。第一版使用 SQLite 承载以下 durable state：

- Session。
- Session slot。
- Run。
- Attempt。
- EventLog。
- durable queue。
- wait record。
- attempt dispatch record。
- host instance liveness record。
- durable payload table / descriptor table。
- projection checkpoint。
- optional outbox marker。

事务不变量：

- EventLog event append 必须分配全局单调 `event_sequence`；`event_sequence` 是 Host event stream cursor、projection checkpoint、outbox dispatch、audit replay 与恢复扫描的主 cursor。
- EventLog append 与必要 Run / Attempt 状态索引更新必须在同一 SQLite transaction 内完成，或具备等价原子性。
- Run terminal fact 提交与 Run 终态更新必须原子。
- Attempt terminal fact 提交与 Attempt 终态更新必须原子。
- queued Run promotion 到 `RUNNING` 与 Attempt 创建必须原子。
- 小型 / 中型可恢复 payload 可以写入 SQLite payload table，并与引用它的 EventLog `canonical_fact` append 在同一 transaction 内提交。
- projection checkpoint 不得先于对应 projection 持久化结果提交。

状态迁移必须使用 CAS-style 条件更新。实现不得以“读出状态后无条件写回”的方式更新 Run / Attempt。

durable store 语义分区：

- governance truth：Session、Run、Attempt、EventLog、wait record、dispatch record、payload descriptor。
- derived state index：active Run index、queue index、projection checkpoint、outbox work queue、memory snapshot cursor。
- diagnostic / trace：provider diagnostic refs、tool trace refs、late event diagnostic、shutdown diagnostic。

governance truth 只能由 Host transaction 写入。derived state index 可以从 governance truth 重建；diagnostic / trace 不能参与状态恢复判定。

Durable table ownership 跟随语义 owner，而不是跟随实现先后顺序。SQLite / transaction runner / EventLog / payload descriptor / idempotency / host instance liveness 是 durable foundation；Session / Run / Attempt / active index / queue index 属于状态机与 admission；wait record 属于 Tool Awaiting；projection checkpoint、audit、tool trace、outbox、memory snapshot、context artifacts、purge tombstone 等表属于各自 projection 或治理模块。实现不得创建无语义 owner 的空表，也不得让 projection 表成为 governance truth。

### 10.1 Host Handle / Composition Root

Host 公共函数接收的 `host` 是 composition root / handle，不是业务 God object。它只负责持有模块化依赖和事务入口，不把各子系统状态混成一个可变大包。

Host composition root 可以拥有两类能力：command path handle 与 background runtime supervisor。二者可以由同一个构造入口装配，但必须向调用方和子系统暴露不同 facet。

command path handle 只服务同步治理命令，例如 `start_run`、`submit_followup`、`cancel_run`、`cancel_session_runs`、`resolve_wait`、`retry_run`、`replay_run`。它可以持有：

- durable store / transaction runner。
- EventLog appender / reader。
- Run admission 与 queue promotion service。
- Attempt dispatcher / WorkerProxy factory。
- ToolRuntime factory。
- RunInputBuilder。
- state transition services。
- typed policy views / immutable policy snapshot refs。
- clock / id generator。
- after-commit wakeup port。

background runtime supervisor 只服务已提交事实的追平、投影和投递。它可以持有：

- Observer / Sink runner。
- Outbox projection runner。
- stream fanout。
- projection workers。
- wait poller。
- sink-local checkpoint / retry state。

每个依赖必须有清晰 ownership；Host handle 不能让 Service、UI、RemoteStub 或 Sink 绕过 Host 状态机直接写 durable truth。

command path 与 background runtime 的固定路径：

```text
Host mutating command
  -> durable transaction
  -> append EventLog / update state indexes
  -> commit
  -> after-commit wakeup port signals background supervisor
  -> supervisor catches up Sink / Outbox / projection by event_sequence checkpoint
```

command path 不直接运行慢 projection、outbox projection、tool trace 写文件或 memory projection。background runtime 不 append canonical facts，不更新 Run / Attempt governance state，也不决定 mutating command 是否成功。

运行参数约束：

- Host 运行参数可以有默认值，但默认值只能在 Host composition root 构造时应用。
- 所有影响持久化、执行、恢复、投影、工具治理或外部通信的运行参数，都必须有显式接口可由调用方传入；不得只能通过模块级全局变量、隐式单例、环境变量或硬编码路径取得。
- EventLog / durable store 所在数据库、payload / artifact 目录、projection / outbox 存储位置、worker target、policy provider、clock、id generator、truncation / context budget policy 都属于可注入运行参数。
- 外部业务 `ToolBundle` 是 Host construction / composition root 的显式输入参数。Host handle 必须记录 tool bundle digest、schema digest 和 source refs，用于 Attempt snapshot、audit 和 diagnostic 解释。
- Host 公共操作函数不接收零散全局配置；它们接收已构造好的 Host handle。Host handle 的构造函数或工厂函数必须暴露 typed options / request，用于传入上述运行参数。
- 默认参数必须能被显式传入值完全覆盖；覆盖后的值必须进入 Host snapshot / diagnostic / audit 所需的可解释 refs，便于排查不同入口或进程使用的运行配置。

Phase 1 必须稳定 ToolBundle construction input 的最小 typed shape，但不实现 Host command path、durable store、ToolRuntime policy resolution 或 framework tool 注入逻辑。最小 Python 3.11 类型形状为：

```text
class ToolBundleSourceKind(StrEnum):
    EXPLICIT_PROVIDER = "explicit_provider"
    CONFIG_BINDING = "config_binding"
    PACKAGE_ENTRYPOINT = "package_entrypoint"
    SERVICE_COMPOSITION = "service_composition"

class FrameworkToolName(StrEnum):
    FETCH_MORE = "fetch_more"

@dataclass(frozen=True, slots=True)
HostToolingOptions
  business_tool_bundle: ToolBundle
  source_refs: tuple[ToolBundleSourceRef, ...]
  framework_tool_policy: FrameworkToolPolicyView

@dataclass(frozen=True, slots=True)
ToolBundleSourceRef
  source_kind: ToolBundleSourceKind
  source_id: str
  version_ref?: str
  content_digest?: str

@dataclass(frozen=True, slots=True)
FrameworkToolPolicyView
  reserved_framework_tool_names: frozenset[FrameworkToolName]
  enabled_framework_tools: frozenset[FrameworkToolName]
```

`HostToolingOptions` 属于 Host construction options 的一部分，只能在 composition root / host factory 接收。`business_tool_bundle` 不得出现在 `StartRunRequest`、`SubmitFollowupRequest`、retry / replay / resume request 或无结构 metadata 中。`ToolBundleSourceRef` 只记录可解释来源、版本与 digest；它不携带 callable，不反向指向具体业务工具模块，也不要求 Host 能重新执行 discovery。

`ToolBundleSourceKind` 必须使用 Python 3.11 `enum.StrEnum`，不得实现为普通 `str` 常量或 `typing.Literal`，以保证 source refs 具备稳定字符串序列化和受限取值。`FrameworkToolName` 同样必须使用 Python 3.11 `enum.StrEnum`，不得实现为普通 `str` 常量或 `typing.Literal`；当前 framework tool 名称集合至少包含 `fetch_more`。`FrameworkToolPolicyView.reserved_framework_tool_names` 用于禁止业务 `ToolBundle` 占用 Host framework tool 名称，即使某个 framework tool 当前未启用也可以被保留。`FrameworkToolPolicyView.enabled_framework_tools` 只表达 construction-time policy view，表示本 Host handle 允许后续 ToolRuntime factory 注入的 framework tool 名称集合；它不得在 Phase 1 触发 ToolRuntime 注入、tool governance policy resolution 或 per-run policy override。

Phase 1 的默认 reserved framework tool names 至少包含 `FrameworkToolName.FETCH_MORE`。enabled framework tools 必须显式来自 Host construction options 或其默认值；默认值不表达完整工具治理策略。`FrameworkToolPolicyView` 是独立的 construction-time framework-tool policy view，不是完整 `ToolGovernancePolicyView`。后续 ToolRuntime / Tool Governance phase 可以消费它，或将其并入更完整的 `ToolGovernancePolicyView`，但 Phase 1 不实现完整工具治理策略。

`HostPolicyProviderSet` 是一组 typed policy providers，不是插件市场、全局 registry、service locator 或 god bag。它只承载 Host 运行时需要读取的治理策略：

- admission policy。
- worker selection policy。
- retry / replay policy。
- cancel policy。
- context budget policy。
- tool governance policy。
- sink / outbox policy。

每个 policy provider 必须有明确输入、输出和 owner。互不相关的策略不得塞进一个无结构 config payload。

`HostPolicyProviderSet` 只存在于 composition root / acceptance command path。Attempt snapshot 和子系统不能持有整个 provider set；它们只能接收已经解析过的 typed policy view 或 immutable policy snapshot ref，例如：

- `AdmissionPolicyView`
- `WorkerSelectionPolicyView`
- `ToolGovernancePolicyView`
- `ContextBudgetPolicyView`
- `OutboxPolicyView`

策略使用路径固定为：

```text
HostPolicyProviderSet at composition root
  -> command path resolves policy decisions / snapshots at acceptance or dispatch boundary
  -> each subsystem receives only its typed policy view or immutable policy snapshot refs
  -> subsystem executes with that view / ref
  -> audit / trace records policy decision id / ref needed to explain behavior
```

子系统不得用字符串 key 反查全局 policy，也不得把 policy provider set 当作跨层 service locator。

## 11. Host 公共接口

Host 公共接口采用函数式风格，但不得依赖全局隐式单例。公共函数接收明确的 Host handle / context 与 request，返回稳定 snapshot 或 Host event stream。

类型归属规则：

- `dayu.contracts` 只承载 Host 与 Engine / ToolRuntime 边界都必须理解的层间协作契约，例如现有 `ToolBundle`、`ToolDefinition`、`ToolSchema`、`ToolExecutor`、批式工具调用 / outcome、取消观察 token 与严格 JSON 值。
- Host 公共 API 类型放在 `dayu.host` 的公共命名空间，而不是放进 `dayu.contracts`。这些类型包括 Host handle / command facet、`HostCallContext`、`OperationContext`、各 mutating request、`SessionSnapshot`、`RunSnapshot`、`FollowupSnapshot`、`PurgeSessionResult`、`HostEventStream`、Session / Run / Attempt status enum、Host API error code 与 stream cursor 类型。Service / UI 可以按向下依赖关系 import `dayu.host` 公共类型；Engine 不得 import 这些类型。
- Host 内部类型留在 `dayu.host` 内部模块，不从公共命名空间导出。这些类型包括 durable EventLog row、状态索引 row、dispatch record、idempotency record、transaction object、policy provider set、ToolRuntime snapshot、accept barrier 内部 candidate、projection checkpoint row、recovery scan record 与 background supervisor 私有状态。
- 如果某个类型同时被多层读写，必须先审视边界是否过宽；不能因为多个调用方想复用 dataclass 就把 Host 私有治理状态提前提升到 `dayu.contracts`。

第一版最小接口集合：

```text
ensure_session(host, request) -> SessionSnapshot
create_session(host, request) -> SessionSnapshot
get_session(host, session_id) -> SessionSnapshot
close_session(host, session_id, request) -> SessionSnapshot
purge_session(host, session_id, request) -> PurgeSessionResult

start_run(host, request) -> RunSnapshot
get_run(host, run_id) -> RunSnapshot
stream_run_events(host, run_id, cursor) -> HostEventStream
cancel_run(host, run_id, request) -> RunSnapshot
cancel_session_runs(host, session_id, request) -> SessionSnapshot
submit_followup(host, session_id, request) -> FollowupSnapshot
retry_run(host, run_id, request) -> RunSnapshot
replay_run(host, run_id, request) -> RunSnapshot
resolve_wait(host, wait_id, request) -> RunSnapshot
```

外部语义采用函数式操作。`retry_run(host, run_id, request)` 与 `replay_run(host, run_id, request)` 的语义分别是 `retry(run)` / `replay(run)`：输入是源 Run，输出是关联的新 RunSnapshot；它们不是在原 Run 上调用 `Run.retry` / `Run.replay` 来重开终态。

所有会 append EventLog `canonical_fact` 或影响 audit 的 mutating request 都必须携带结构化 `HostCallContext` 或等价 request envelope。Host 不负责认证，但必须记录上层已经解析的 actor / principal、source / client、request id、权限声明和 operation context。required fields 不能塞进无结构 metadata。

本节 request 片段只列操作专属字段；mutating request envelope 必须统一包含 `HostCallContext`。

`HostCallContext` 语义契约：

```text
actor / principal       -> 谁代表本次操作负责
source / client         -> 操作来自哪个入口或客户端
request_id              -> 上层调用链路追踪 id
authorization_claims?   -> 上层已验证的权限声明
operation_context       -> 业务 / 操作上下文
```

`HostCallContext` 描述这次调用 Host 的来路、责任信息和业务操作上下文，回答“谁、从哪里、以什么权限、为了什么业务操作发起”。它不携带 delivery target，也不是统一幂等键。具体 request 描述状态机前置条件，并定义自己的幂等字段或幂等范围。

`OperationContext` 由 UI / Service 解析并传入，Host 不从 prompt 文本、session slot 或 metadata 猜业务对象。最小语义：

```text
operation_name          # 例如 fins.earnings_qna.ask / run.cancel / replay.repair
operation_kind          # user_prompt | control | system_recovery | tool_execution | projection
business_domain         # fins | host | service | system
business_object_type?   # company | filing | report | session | run | tool_call | other typed object
business_object_id?     # ticker / company_id / filing_id / report_id / typed ref
scenario?               # earnings_qna | annual_report_analysis | replay_repair | other typed scenario
correlation_id?         # 跨 Service / Host / tool trace / audit 的关联 id
```

`OperationContext` 不是 policy override，不决定权限，不替代 `authorization_claims`，不承载大业务 payload。EventLog、Audit、Tool Trace 和 Attempt snapshot 只能记录 operation context 的 typed identifiers / refs / digest。

Host 不从 `Session slot` 反推 actor，也不从 metadata 猜 actor、权限、业务对象或 channel 投递目标。匿名、系统动作和后台 policy 动作必须使用显式 actor 值和 operation context，例如 system actor / service actor。

mutating API 的通用路径：

```text
validate HostCallContext
  -> validate precondition and idempotency key
  -> open durable transaction
  -> append EventLog canonical facts
  -> update required governance indexes
  -> commit
  -> dispatch side effects only after commit
```

事务提交前不得启动 EngineWorker、写 outbox item、调用外部 job 或通知远端执行。提交后的 side effect 必须能从 EventLog / dispatch record / outbox checkpoint 恢复或重试。

Idempotency semantic contract：

- 每个 mutating operation 的幂等范围必须显式定义，例如 `(session_id, client_request_id)`、`(run_id, client_request_id)` 或 `(scope, slot_key)`。
- `HostCallContext` 不定义幂等范围；operation request owns idempotency key。
- 幂等记录绑定 operation name、scope / target object、semantic input digest、result object id 和 accepted event refs。
- 同一幂等键 + 同一 semantic input digest 重试时，Host 返回既有 snapshot，不重复 append canonical facts，不重复 dispatch。
- 同一幂等键 + 不同 semantic input digest 必须返回 `idempotency_conflict`，不得静默复用旧对象，也不得创建第二个对象。
- 已提交 Run / Attempt 后的重试只读取当前 truth 并返回最新 snapshot；它不能重新派发已经派发过的 Attempt。
- 幂等判断必须在 durable transaction 内完成，不能依赖进程内 cache。

`EnsureSessionRequest`：

```text
scope
slot_key
metadata
```

`CreateSessionRequest`：

```text
client_request_id
bind_slot?
scope?
slot_key?
metadata
```

`StartRunRequest`：

```text
session_id
client_request_id
input
execution_target
queue_policy
```

`CancelRunRequest`：

```text
client_request_id
reason
mode: graceful   # first version only
```

`CancelSessionRunsRequest`：

```text
client_request_id
reason
mode: graceful   # first version only
```

`CloseSessionRequest`：

```text
client_request_id
reason
```

`PurgeSessionRequest`：

```text
client_request_id
reason
```

`SubmitFollowupRequest`：

```text
session_id
client_request_id
input
behavior: queue | steer
target_run_id?        # required when behavior=steer
```

`RetryRunRequest`：

```text
client_request_id
reason
```

`ReplayRunRequest`：

```text
client_request_id
reason
repair_instruction?
```

`ResolveWaitRequest`：

```text
idempotency_key
outcome
source: poll | callback | manual
observed_at
```

Run 接口语义：

- `start_run`：接受显式新建独立 Run 目标，按 `(session_id, client_request_id)` 幂等创建或返回同一个 Run；根据 admission 决定立即 `RUNNING`、进入 `QUEUED`、拒绝或 attach active。它不是聊天界面每次发送普通 prompt 的默认入口。
- `get_run`：读取 RunSnapshot；不触发执行、不触发 queue promotion、不改变 Run / Attempt 状态。
- `stream_run_events`：从全局 `event_sequence` cursor 补读目标 Run 的事件；断线重连只依赖 cursor，不依赖内存订阅是否仍存在。
- `close_session`：关闭 Session 新输入入口，按 `(session_id, client_request_id)` 幂等；不取消、不终止、不删除已有 Run。
- `purge_session`：清理已关闭且全部 Run 终态的 Session，按 `(session_id, client_request_id)` 幂等；删除可恢复事实与 projection，只保留最小 purge tombstone / audit record。
- `cancel_run`：接受取消请求，按 `(run_id, client_request_id)` 幂等；queued Run 直接 `CANCELLED`，active Run 进入 `CANCELLING` 并向当前 Attempt 传播 cancel。
- `cancel_session_runs`：接受 session-scope cancel 请求，按 `(session_id, client_request_id)` 幂等；取消该 Session 下所有未终态 Run，不影响其它 Session。
- `submit_followup`：接受同一 Session 的会话延续输入。聊天界面的普通 prompt 入口应统一使用该接口，不应由调用方先读 active Run 再在 `start_run` / `submit_followup` 之间选择。`behavior=queue` 由 Host admission 在同一事务内决定排队或直接启动；`behavior=steer` 必须命中 `target_run_id` 所指的当前 active Run 并切换 Attempt。
- `retry_run`：公开 Host control API，由调用方主动发起；函数式语义为 `retry(run)`。它在 confirmed failure / recoverable failure 后创建关联的新 Run。原 Run 保持终态不可变；新 Run 可以按 retry policy 复用旧 Run 已接受工具事实，并创建自己的 Attempt。
- `replay_run`：公开 Host control API，由调用方主动发起；函数式语义为 `replay(run)`。它只用于 final answer 格式、schema、结构或输出 envelope 失败时创建关联的新 Run。原 `SUCCEEDED` Run 不重开；新 Run 默认复用旧 Run 已接受工具事实，并以 no-tool messages 调用做结构修复。事实内容脏、幻觉、业务归因错误、证据不足或证据冲突不属于 replay 场景。
- `resolve_wait`：等待结果接收与治理入口；接收 poll / callback / manual 已取得的结果，关闭 wait record，append tool terminal/result fact，并创建新 Attempt resume。它不负责等待外部长事务完成。

第一版公共 API 不暴露开放式 policy knobs。Host policy 可以有默认值，但 request 不能携带无结构 `policy_overrides`。`CancelRunRequest.mode` 第一版唯一值为 `graceful`；不支持 `force` / `immediate`。`retry_run` 是否复用 accepted tool facts、重试次数和退避由 Host retry policy 决定。`replay_run` 固定复用源 Run accepted tool facts / evidence anchors，固定 no tools，固定只做结构修复。

Run 读取与结果边界：

- Run 当前结果通过 `get_run` 的 `RunSnapshot.terminal result summary` 与 `stream_run_events` 的 terminal event 暴露。
- 第一版不单独定义 `get_run_result`；如果后续需要大结果分页或多版本 replay result，可作为 read-model API 扩展，不能成为事实真源。
- Session timeline 仍通过 `get_session` snapshot 或后续 read-model API 暴露；它不能替代 `stream_run_events` 的恢复 cursor。

接口分层：

- `ensure_session`、`create_session`、`get_session`、`close_session`、`purge_session`、`start_run`、`get_run`、`stream_run_events`、`cancel_run`、`cancel_session_runs`、`submit_followup` 是多入口稳定公共能力。
- `cancel_session_runs` 是客户端退出 / supervisor shutdown 的便利公共能力；它只取消指定 Session 下未终态 Run，不表达客户端拥有的 Session 集合。
- `ensure_session` 表示“给我这个 slot 的当前会话，必要时创建并绑定”。
- `create_session` 表示“明确分配一个新 Session”，可选绑定 slot。
- `retry_run`、`replay_run` 是 Host control API；UI / Service 可以暴露，但必须保留 `retry(run)` / `replay(run)` 的函数式语义、Host 幂等与状态机。
- `resolve_wait` 是 Host 内部 / adapter API；poller、callback handler、manual admin 入口都必须走它，不能各自写 Run 状态。
- 读取 Session timeline 通过 `get_session` 的 snapshot 或后续 read-model API 暴露；它必须从 EventLog / projection 读取，不触发执行。

Snapshot 最小语义：

- `SessionSnapshot`：`session_id`、status、slot、active run、queued runs、timeline cursor。timeline cursor 使用全局 `event_sequence` cursor；session-local cursor 只能作为 read model 优化，不能替代全局 cursor。
- `RunSnapshot`：`run_id`、`session_id`、status、current attempt、terminal result summary、event_sequence cursor、source_run_id?、source_run_relation?、outbox summary。
- `FollowupSnapshot`：accepted input ref、behavior、target run / queued run、current cursor。
- `PurgeSessionResult`：`session_id`、purged marker、purge tombstone ref、deleted counts / digest。
- `HostEventStream`：Host event stream 的返回对象，按全局 `event_sequence` 递增返回，携带 next `event_sequence` cursor。

公共错误分类至少包括：

- `not_found`
- `invalid_state`
- `conflict`
- `idempotency_conflict`
- `permission_denied`
- `internal_error`

错误分类语义：

- `conflict`：当前 Host 状态与请求前置条件冲突，例如 active Run 存在且 policy 拒绝排队。
- `idempotency_conflict`：同一幂等键已绑定到不同语义输入或不同目标对象。
- `invalid_state`：目标对象存在，但该状态下不允许此操作。
- `permission_denied`：上层传入的 authorization claims 不满足 Host policy。

`stream_run_events` 从 EventLog `event_sequence` cursor 补读，不触发新执行。

## 12. Follow-up 与 Steer

运行中的 Session 可能收到新的用户输入。

聊天界面的普通 prompt 入口统一是 `submit_followup`。UI / Service 不应先读取 active Run 再决定调用 `start_run` 还是 `submit_followup`；调用方表达用户意图，Host 在 admission transaction 内决定该输入排队、立即启动或作为 steer 被接受。

`queue` 语义：

- `submit_followup(queue)` 必须由 Host 在同一个 admission transaction 内吸收 active Run 竞态。
- 当前 Session 有 active Run 时，follow-up 输入排队为后续 Run 的输入，不打断当前 active Run。
- 当前 Session 没有 active Run 时，follow-up 创建并启动新 Run；execution target 通过 Host policy 归一化并持久化。
- 排队输入使用 `(session_id, client_request_id)` 幂等。
- `submit_followup(queue)` 的 `invalid_state` / `conflict` 不应表示 active Run 竞态；它应表示 Session closed、幂等冲突、权限不满足、输入不合法等真实错误。

`steer` 语义：

- steer 是对当前 active Run 的控制输入，不创建并列新 Run。
- steer request 必须携带 `target_run_id` 或等价 expected active Run precondition。
- steer 不能像 queue 一样吸收 active Run 竞态；它必须作用于调用方指定的目标 Run。
- Host 只允许 steer 调用方指定的目标 Run；如果当前 active Run 已切换，Host 不得隐式 steer 新 active Run。
- 调用方可见语义是：把用户输入追加到当前 active Run，用于重定向正在进行的工作。
- Host 对当前 active Attempt 发起受治理的停止请求，并记录 steer input canonical fact。
- 当前 Attempt 收口后，Host 为同一个 Run 创建新 Attempt 和新 `execution_id`。
- Host 基于 EventLog canonical facts 重建完整 `AgentRunRequest.messages`，其中包含已接受工具事实、已确认输出边界和 steer 输入。
- Engine 只看到新的 `AgentRunRequest`；Engine 不理解 steer，不恢复旧 Agent / Runner。

`RUNNING` Run steer 路径：

```text
user submits follow-up with behavior=steer
  -> Host validates target_run_id is the current active Run
  -> Host appends STEER_REQUESTED
  -> Host requests current attempt stop through cancellation source
  -> current Attempt closes as STEERED or terminal race result
  -> Host appends RUN_STARTED(start_reason=steer)
  -> Host creates new Attempt for the same Run with new execution_id
  -> Host appends ATTEMPT_STARTED
  -> Host rebuilds messages from EventLog canonical facts + steer input
  -> commit
  -> Host dispatches through LocalProxy / RemoteProxy
```

`WAITING` Run steer 路径：

```text
user submits follow-up with behavior=steer
  -> Host validates target_run_id is the current WAITING active Run
  -> Host appends STEER_REQUESTED
  -> Host marks active wait record cancelled(reason=steered) in the same transaction
  -> Host appends RUN_STARTED(start_reason=steer)
  -> late wait result can only enter diagnostic / tool trace
  -> old Attempt remains SUSPENDED
  -> Host creates new Attempt(status=STARTING) for the same Run
  -> Host appends ATTEMPT_STARTED
  -> Host rebuilds messages from EventLog canonical facts + steer input
  -> commit
  -> Host dispatches through LocalProxy / RemoteProxy after commit
```

`WAITING` steer 不新增 wait record 状态。旧 Attempt 保持 `SUSPENDED`，不改写为 `STEERED`，因为它已经因 awaiting 正常 suspended。

steerable Run 状态只有 `RUNNING` 与 `WAITING`。`CANCELLING`、`RECOVERING` 和所有 terminal 状态都不可 steer。

调用方错误处理语义：

- 没有 active Run：返回 `invalid_state`；聊天 UI 可用同一条输入重新调用 `submit_followup(queue)`。
- `target_run_id` 不是当前 active Run：返回 `conflict`，错误响应应包含当前 active Run 与目标 Run 的状态摘要。
- 目标 Run 已 terminal：返回 `invalid_state`；聊天 UI 可用同一条输入重新调用 `submit_followup(queue)`，控制型 UI 可以只提示用户 steer 已失效。
- 目标 Run 是当前 active Run 但状态不可 steer：返回 `invalid_state`；调用方可选择 cancel、queue 或稍后重试。

Host 不自动把 steer 降级成 queue / start_run / replay；这些是 UI / Service 的显式策略。

terminal / steer 竞态规则：

- Run terminal fact 已提交时，steer 不能改写 terminal；该输入必须按调用方 policy 降级为 queued follow-up / new Run，或返回 `invalid_state`。
- Host 已 append `STEER_REQUESTED` 但旧 Attempt 先提交 terminal 时，terminal 优先；Host 记录 `STEER_LOST` diagnostic / projection_signal，steer input 不进入已 terminal Run 的 messages。
- `STEER_LOST` 至少包含原 `STEER_REQUESTED` event ref、目标 `run_id`、赢得竞态的 terminal event ref、reason code 和调用方可见状态提示。它不是 canonical fact，不驱动 recovery、memory、resume 或 Run 状态迁移。
- Host 已成功将旧 Attempt 收口为 `STEERED` 时，后续旧 `execution_id` 的 terminal 事件视为迟到事件，只能进入诊断 / trace。
- steer 不绕过同一 Session active Run admission；它只是同一 Run 内 Attempt 切换。

取消后编辑再发送：

- 已 accepted 的用户输入是 `USER_INPUT_ACCEPTED` canonical fact，不支持原地修改、覆盖或删除。
- 用户在 final answer 返回前取消 prompt A、编辑后发送 prompt B 时，Host 真源必须保留两条输入事实：prompt A 对应 Run A 并最终 `CANCELLED`，prompt B 对应新的 Run B。
- 聊天 UI 可以在 Session timeline projection 中折叠或弱化显示已取消的 prompt A，但这不能改变 EventLog、RunInputBuilder、audit、memory 或 recovery 事实。
- prompt B 必须通过 `submit_followup(queue)` 或显式 `start_run` 进入 Host；聊天界面默认使用 `submit_followup(queue)`。

## 13. EventLog

EventLog 是 Host 的 append-only event ledger。`event_class=canonical_fact` 的子集是 Host canonical fact source；preview / diagnostic / projection signal 可以为了 Host event stream 或诊断进入同一 cursor 空间，但不能成为治理真源。

EventLog 不变量：

- 除 `purge_session` 的 destructive retention 例外外，EventLog 只 append，不 update，不 delete。
- `purge_session` 是第一版唯一 destructive retention 例外。它只允许在严格前置条件成立后删除目标 Session 的可恢复事实，并必须保留 purge tombstone；该 tombstone 不参与 resume、retry、replay、memory 或 RunInputBuilder。
- 是否挂载 Observer / Sink 不能改变 EventLog 行为。
- 同一输入在同一 Host 状态下，append 成功条件、事件顺序、状态迁移、恢复语义和调用方可见结果必须一致。
- Projection / audit / memory / timeline / usage / tool trace 不得 append 或 update EventLog。
- preview / reasoning / display-only event 可以用于 Host event stream，但不能成为 memory / audit / resume 真源。
- 每条 event 必须显式标注 `event_class`；缺省不得被解释为 canonical fact。
- 只有 `canonical_fact` 可以驱动 Run / Attempt 状态迁移、recovery、resume、memory verified inputs、audit 责任主链和 outbox terminal delivery intent。
- `preview` 可以按 `event_sequence` 补读以恢复 UI 体验，但 preview 丢失、压缩或清理不得影响 Run terminal、messages rebuild 或 memory。
- `diagnostic` 可以用于排错和 trace，但不得让 late remote event、protocol error 或 projection failure 变成业务事实。
- `projection_signal` 只能由 Host ingest / Host policy 写入，用于 usage、tool trace 或其它 projection 输入；Sink 不得把自己的输出再写回 EventLog 形成反馈环。

事件形态：

```text
event_log
  event_id
  event_sequence
  event_class: canonical_fact | preview | diagnostic | projection_signal
  session_id
  run_id?
  attempt_id?
  execution_id?
  event_type
  occurred_at
  actor?
  source?
  client_request_id?
  idempotency_key?
  policy_decision?
  reason?
  payload_json
  payload_ref?
  payload_digest?
```

排序与幂等：

- `event_sequence` 是 SQLite 分配的全局单调序列，是所有 Host event stream cursor、projection checkpoint、outbox dispatch、audit replay 和 recovery scan 的主 cursor。
- `event_id` 是 Host ledger event identity；`canonical_fact` 的 `event_id` 同时是 canonical event identity。重复 ingest 同一 canonical `event_id` 必须返回已接受结果，不得 append 第二条 canonical event。
- client operation id、remote event identity、canonical event identity 必须分层。`client_request_id` 标识客户端 API 操作幂等；remote event identity 标识 Proxy / Stub / EngineWorker 回传来源事件；canonical `event_id` 标识 Host EventLog 中单条 canonical fact。
- 一个 remote event 如果映射为多个 canonical events，每个 canonical event 都必须有独立、稳定、可去重的 identity，例如由 `execution_id`、remote event identity、canonical event type 与 sub-index 派生。Host-generated state transition event 也必须有明确幂等来源，不能混用 `client_request_id` 或 remote event identity。
- `run_sequence` / `session_sequence` 可作为 read model 优化，但不得替代全局 `event_sequence`。
- `stream_run_events(run_id, cursor)` 使用全局 `event_sequence` cursor 过滤目标 run，保证断线重连稳定补读。
- 远端事件携带的 sequence 只用于 remote-side ordering / diagnostics；是否作为 `canonical_fact` 进入 EventLog 由 Host 决定，并由 Host 重新分配 `event_sequence`。

Event ingest semantic contract：

```text
event source
  -> validate source identity
  -> validate run_id / attempt_id / execution_id when attempt-scoped
  -> derive canonical event identity
  -> check idempotency
  -> classify as canonical / preview / projection input / diagnostic / rejected
  -> append accepted EventLog row inside Host transaction
  -> update Run / Attempt indexes in the same transaction when event_class=canonical_fact has state side effects
  -> notify projections after commit
```

canonical ingest 必须满足：

- stale `execution_id` 不得作为 `canonical_fact` 进入 EventLog。
- duplicate canonical identity 返回既有 accepted event，不追加第二条。
- out-of-order remote event 只能在不破坏 Host 状态机时被接受；否则进入 diagnostic 或 rejected。
- terminal event 一旦 accepted，同一 Run 的后续 steer / cancel / late terminal 不能改写 terminal fact。
- preview event 可以进入 Host event stream，但不能让 RunResult、memory、audit 或 recovery 依赖它。

### 13.1 Payload 存储

- EventLog row 不应内嵌大 payload；canonical event 必须记录 payload ref / descriptor 与 digest，或其它可校验 ref。
- 第一版使用 SQLite payload table 作为默认 durable payload store；小型 / 中型可恢复 payload 与引用它的 EventLog append 在同一 SQLite transaction 内提交。
- 超过 Host policy 阈值的大工具结果、财报 chunk、binary、长网页正文、provider raw response、完整 prompt / messages、trace 明细必须外移到 artifact / blob / tool trace / 领域仓储，并在 artifact durable 且 digest verified 后才 append EventLog `canonical_fact`。
- `payload_digest`、normalized args digest、result digest 和 evidence digest 必须基于确定性序列化 / canonicalization 计算；同一语义 payload 不能因 JSON key 顺序或无关默认值产生不同 digest。
- 会参与 resume、memory、audit、`fetch_more`、replay 的 payload / ref / descriptor 缺失或 digest 不匹配时，Host 不能把该 fact 当作 accepted fact 使用。
- preview / diagnostic / display-only payload 可以降级丢失；其缺失只能影响展示、深度审计或 trace 细节，不能伪装成恢复必要事实。
- 对财报证据，EventLog 记录 evidence anchor / ref / digest，不复制整份材料。

### 13.2 Canonical Event 最小集合

第一版 canonical events 至少包括：

```text
SESSION_CREATED
SESSION_CLOSED

RUN_ACCEPTED
RUN_QUEUED
RUN_STARTED
RUN_WAITING
RUN_CANCELLING
RUN_RECOVERING
RUN_SUCCEEDED
RUN_FAILED
RUN_CANCELLED
RUN_LOST

ATTEMPT_STARTED
ATTEMPT_RUNNING
ATTEMPT_SUCCEEDED
ATTEMPT_FAILED
ATTEMPT_CANCELLED
ATTEMPT_SUSPENDED
ATTEMPT_STEERED
ATTEMPT_LOST

USER_INPUT_ACCEPTED
FOLLOWUP_QUEUED
STEER_REQUESTED
CANCEL_REQUESTED
RESUME_REQUESTED
RETRY_REQUESTED
REPLAY_REQUESTED

TOOL_CALL_REQUESTED
TOOL_CALL_GOVERNED
TOOL_RESULT_ACCEPTED
TOOL_AWAITING
TOOL_TERMINAL_RESULT
GUIDANCE_INSERTED
CONTEXT_COMPACTION_REQUESTED
CONTEXT_COMPACTED
CONTEXT_COMPACTION_FAILED
PROVIDER_PROTOCOL_ERROR
```

Terminal event 使用具体终态 event，不使用模糊 `RUN_TERMINAL` / `ATTEMPT_TERMINAL` 作为唯一类型。

模糊的“attempt event accepted”不作为第一版 canonical event。EngineEvent ingest 必须落到具体业务事实、preview / diagnostic，或被拒绝；不得用模糊“已接受某事件”掩盖事实类型。

### 13.3 Canonical Event Contract Matrix

canonical event contract 必须转成 typed dataclass / enum / validation tests。架构级最小矩阵如下：

| Event class | 必需 scope | 必需 payload | 状态副作用 | Resume / memory | Audit / Host event stream |
| --- | --- | --- | --- | --- | --- |
| `SESSION_CREATED` / `SESSION_CLOSED` | `session_id` | slot / actor / reason | 更新 Session status | memory 不消费 | audit yes / timeline emit |
| `USER_INPUT_ACCEPTED` | `session_id`、`run_id`、`client_request_id` | user input ref / digest / display text | 创建或关联 Run 输入 | resume yes / memory raw turn | audit yes / Host event stream emit |
| `RUN_ACCEPTED` / `RUN_QUEUED` / `RUN_STARTED` | `session_id`、`run_id` | queue policy / execution target / `start_reason` when started | 更新 Run status / queue index | resume yes | audit yes / Host event stream emit |
| `RUN_WAITING` / `RUN_CANCELLING` / `RUN_RECOVERING` | `session_id`、`run_id` | wait_id / cancel reason / recovery reason | 更新 Run status | resume yes when semantically needed | audit yes / Host event stream emit |
| `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST` | `session_id`、`run_id`、terminal attempt refs | terminal summary / error / reason / result ref | 更新 Run terminal status | resume 只消费有语义必要的终态；memory 消费 assistant conclusion 和工具事实 | audit yes / Host event stream emit / success 触发 outbox |
| `ATTEMPT_STARTED` | `session_id`、`run_id`、`attempt_id`、`execution_id` | worker target / dispatch record ref | 创建 Attempt row，status=`STARTING` | resume 不消费，除非用于诊断 | audit yes / Host event stream optional |
| `ATTEMPT_RUNNING` | `session_id`、`run_id`、`attempt_id`、`execution_id` | worker accepted / dispatch accepted info | Attempt status=`RUNNING` | resume 不消费，除非用于诊断 | audit yes / Host event stream optional |
| `ATTEMPT_SUCCEEDED` / `ATTEMPT_FAILED` / `ATTEMPT_CANCELLED` / `ATTEMPT_SUSPENDED` / `ATTEMPT_STEERED` / `ATTEMPT_LOST` | `session_id`、`run_id`、`attempt_id`、`execution_id` | terminal reason / error / wait_id | 关闭 Attempt | resume 按需消费 suspended / lost reason | audit yes / Host event stream emit |
| `FOLLOWUP_QUEUED` / `STEER_REQUESTED` / `CANCEL_REQUESTED` / `RESUME_REQUESTED` / `RETRY_REQUESTED` / `REPLAY_REQUESTED` | `session_id`、`run_id`、operation idempotency key | control input / reason / policy / source_run_id when retry or replay | 触发对应状态机；retry / replay 创建关联新 Run，不重开源 Run | 改变模型语义时进入 messages | audit yes / Host event stream emit |
| `TOOL_CALL_REQUESTED` | `session_id`、`run_id`、`attempt_id`、`execution_id` | tool_call_id / tool name / normalized args digest | 记录工具调用 intent | accepted into model history 时 resume 消费 | audit 是 / tool trace 是 |
| `TOOL_CALL_GOVERNED` | `session_id`、`run_id`、`attempt_id`、`execution_id` | policy decision / duplicate key / action | 不直接改 Run；可触发 guidance / hard stop | action 影响模型继续时进入 messages | audit 是 / tool trace 是 |
| `TOOL_RESULT_ACCEPTED` / `TOOL_TERMINAL_RESULT` | `session_id`、`run_id`、`attempt_id`、`execution_id` | result ref / digest / evidence anchors / status | 记录工具事实 | resume 是 / memory 工具事实 | audit 是 / tool trace 是 |
| `TOOL_AWAITING` | `session_id`、`run_id`、`attempt_id`、`execution_id` | wait_id / await_spec / external_job_id | 与 `RUN_WAITING`、`ATTEMPT_SUSPENDED` 同事务创建 wait record；Run -> `WAITING`；Attempt -> `SUSPENDED` | resume 是 | audit 是 / tool trace 是 |
| `GUIDANCE_INSERTED` | `session_id`、`run_id` | guidance text / source policy / reason | 不直接改 terminal；影响下一 Attempt messages | 插入 messages 时 resume 消费 | audit yes / Host event stream emit |
| `CONTEXT_COMPACTION_REQUESTED` | `session_id`、`run_id`；`trigger_source=reactive` 时必须有 `attempt_id`、`execution_id`；`trigger_source=proactive` 时可以没有 | trigger source / budget reason / provider error refs / snapshot refs | 触发 context governance；proactive path 是 pre-dispatch input governance；reactive path 可关闭当前 Attempt 并让 Run -> `RECOVERING` | resume 是；memory projection 按需消费 | audit yes / trace 是 |
| `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` | `session_id`、`run_id` | compact snapshot refs / preserved fact refs / dropped reason / quality check / failure reason | compacted 后允许创建新 Attempt；failed 后按 policy 失败或保持 recoverable | resume 是；memory projection 消费 compacted snapshot | audit yes / trace 是 |
| `PROVIDER_PROTOCOL_ERROR` | `session_id`、`run_id`、`attempt_id`、`execution_id` | provider / error code / request ref | Attempt failure or retry input | retry 需要时 resume 消费 | audit yes / Host event stream emit |

canonical event 的 required fields 不能被塞进无结构 `metadata`；`metadata` 只能承载不参与状态机、幂等、恢复和审计主链的附加说明。

control event 的 `run_id` 绑定规则：

- `STEER_REQUESTED` 的 `run_id` 是被 steer 的目标 Run。
- `FOLLOWUP_QUEUED` 的 `run_id` 是 queued / created Run。
- `RETRY_REQUESTED` 与 `REPLAY_REQUESTED` 的 `run_id` 是源 Run；关联的新 Run 必须通过后续 `RUN_ACCEPTED` 的 `source_run_id` / `source_run_relation` 或等价 typed payload 表达。
- `RESUME_REQUESTED` 的 `run_id` 是从 `WAITING` / `RECOVERING` 继续的同一 Run。
- `CANCEL_REQUESTED` 的 `run_id` 是被取消的 Run。

### 13.4 EngineEvent 映射

EngineEvent 到 Host EventLog 的映射原则：

- 参与恢复、resume、memory、audit、governance 的 EngineEvent 映射为 canonical event。
- 只服务 UI 流式体验的 delta 映射为 preview event，不进入 canonical projection。
- Host 可以把多个 EngineEvent 聚合成一个 canonical fact，但不得丢失恢复必须的信息。
- 工具事实 canonical owner 是 ToolRuntime Host accept path。EngineEvent ingest 不得为同一工具 outcome 追加第二条工具 canonical fact；描述已 accepted 工具结果的 EngineEvent 必须携带 accepted event refs / accepted tool fact ids，并只能映射为 preview、diagnostic、trace 或 idempotent no-op。

默认映射：

```text
iteration_started              -> preview
content_delta                  -> preview
reasoning_delta                -> preview
content_completed              -> preview
tool_call_delta                -> preview
tool_calls_batch_ready         -> preview or diagnostic
tool_call_requested            -> TOOL_CALL_REQUESTED
ToolRuntime policy decision     -> TOOL_CALL_GOVERNED when decision affects execution / guidance / audit / duplicate handling
tool_result_accepted           -> preview / diagnostic / idempotent confirmation with accepted refs; not canonical owner
tool_calls_batch_done          -> preview or diagnostic
tool_awaiting                  -> preview / diagnostic / idempotent confirmation with accepted refs; not canonical owner
context_compaction_requested   -> CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive); must include attempt_id + execution_id
usage_reported                 -> usage projection input; canonical only if needed for audit policy
provider_protocol_error        -> PROVIDER_PROTOCOL_ERROR
iteration_completed            -> preview or diagnostic
final_answer                   -> RUN_SUCCEEDED + ATTEMPT_SUCCEEDED
run_suspended                  -> preview / diagnostic / idempotent confirmation with accepted refs; not canonical owner
run_cancelled                  -> RUN_CANCELLED + ATTEMPT_CANCELLED
run_failed                     -> ATTEMPT_FAILED + (RUN_FAILED or RUN_RECOVERING by Host policy); context_compaction_required 在可恢复时进入 RUN_RECOVERING + new Attempt
```

该映射是规范性边界；实现必须转成 typed code 和 tests，不得重新发明 canonical / preview 边界。

## 14. Observer / Sink / Projection

Observer / Sink 只消费已提交 EventLog，用于派生 read model 或外部投递。

基本路径：

```text
Host event ingest
  -> validate ids / attempt identity / idempotency key
  -> durable transaction:
       append accepted EventLog row
       assign global event_sequence
       update required Host state indexes for canonical facts
       optionally record projection wakeup / outbox marker
  -> committed event notification
  -> Observer / Sink dispatch
  -> sink-specific checkpoint / retry / replay
```

Sink semantic contract：

- Sink 的输入是 committed EventLog event，不是事务中的临时状态。
- Sink 必须按 `event_sequence` checkpoint 追平，并按 canonical `event_id` 幂等消费。
- Sink 必须是幂等消费者；重复消费同一 canonical `event_id` 不得产生重复副作用或违反投递语义。
- Sink 必须声明消费哪些 `event_class` / `event_type`；默认只消费 `canonical_fact`。
- 每个 Sink 必须有自己的 typed consumer contract，明确输入 event 类型、payload view、checkpoint、幂等键、失败处理和输出 projection；不得让所有 Sink 共享一个无结构 Event payload。
- Sink 可以维护自己的 projection 表、work queue 或冷数据文件，但不能写 Host governance truth。
- Sink lag 只影响派生视图新鲜度，不影响 Run admission、cancel、resume、terminal 收口。
- Sink 失败只能更新 sink-local retry / error state，不能回滚 EventLog，也不能改变 Run / Attempt 状态。
- Audit、usage、tool trace、stream fanout、memory、outbox 等 sink 只依赖 committed EventLog 与各自 typed consumer contract；它们消费 recovery 相关 event 时不读取 Recovery 内部状态。Recovery 产生的 `ATTEMPT_LOST`、`RUN_RECOVERING`、`RUN_STARTED(start_reason=recovery)` 等只是普通 committed events，sink 不得对 Recovery 内部状态形成反向依赖。

第一批 sink：

- audit projection。
- usage projection。
- tool trace projection。
- stream fanout。
- memory projection。
- outbox projection。

### 14.1 Tool Trace Hot / Cold Storage

Tool trace 是 EventLog 派生 projection，不是 Host durable truth。它必须支持冷热数据分离，避免把调试明细、长工具参数、长结果摘要和归档流混进 EventLog 或热查询表。

存储口径：

- 热数据使用结构化 JSON projection。热数据保存近期、可查询、可展示、可关联的 tool trace summary，例如 tool_call_id、tool name、normalized args digest、result digest、evidence anchors、truncate info、await info、policy decision、error code、duration、attempt refs。
- 冷数据使用 append-only JSONL。冷数据保存可归档、可批处理、可离线审计的 trace detail，例如长参数摘要、长结果摘要、provider / tool raw diagnostic refs、截断诊断、重复治理上下文、等待 / 取消 / 超时细节。
- JSON 与 JSONL 都必须携带 `event_id` / `event_sequence`、`session_id`、`run_id`、`attempt_id`、`execution_id`、operation context refs / digest 和必要 digest / ref，保证能从 EventLog 对齐，并能回答“这是什么业务的什么操作产生的 trace”。
- 热数据可以按 retention policy 淘汰或压缩；冷 JSONL 可以按 run / 日期 / workspace 分片归档。
- EventLog 对 tool trace 只记录必要 event、ref 与 digest；不得把 JSONL 当作恢复、resume、memory 或 Run 状态迁移真源。
- tool trace projection 损坏或缺失时，应能从 EventLog 与外移 payload ref 尽力重建热数据；冷 JSONL 丢失只能影响深度诊断和离线审计。

约束：

- Sink 不拥有 Session / Run / Attempt 状态。
- Sink 失败不能回滚 EventLog。
- Sink 按 `event_sequence` checkpoint 追平，并按 `event_id` 幂等消费。
- Sink 慢只能表现为 projection lag，不能拖慢 Host append、run admission、cancel、resume、terminal 收口。
- 第一版不引入重型消息系统；SQLite EventLog + projection checkpoint + 本地后台 worker / 任务循环足够表达可靠追平语义。
- Sink notification 只是一种 wakeup；正确性来自 EventLog replay + checkpoint，不来自内存通知是否送达。

## 15. Audit

Audit 不是事实真源；audit sink 消费 committed EventLog 生成 audit projection。

第一版 Audit 默认落地为 `LogAuditSink(JSONL)`：

- `LogAuditSink` 是 projection / sink，不是 Host truth。
- `LogAuditSink` 按 `event_sequence` checkpoint 消费 committed EventLog。
- `LogAuditSink` 写本地 append-only JSONL audit log file。
- audit log file 路径由 Host composition root 的 typed options 显式传入，可有默认值。
- `LogAuditSink` 写失败只更新 sink-local error / diagnostic / lag，不回滚 EventLog，不影响 Host command path。
- `NoopAuditSink` 只作为测试 / 开发显式配置；生产默认应使用 `LogAuditSink`。
- 第一版不做复杂 AuditPolicy 规则引擎，不做外部 audit 系统投递保证，不做 UI / Service 动态 audit 配置。

Host command path 不直接写 audit log file。它只负责在 EventLog canonical facts、policy decision refs 和 `HostCallContext` 中保留审计所需最小事实。UI / Service 只负责传入 `HostCallContext`，不传 audit 策略。

canonical event 必须携带足够 audit 可追溯字段：

- actor / principal。
- source / client。
- request id / client_request_id。
- operation context refs / digest。
- session_id / run_id / attempt_id / execution_id。
- policy decision。
- reason。
- payload ref / digest。

operation context 是 audit、tool trace、timeline 与 diagnostic 关联业务操作的共同索引。Host 只记录 UI / Service 已解析的 typed identifiers / refs / digest，不从 prompt 文本或无结构 metadata 推断业务对象。

Audit 重点记录治理动作和责任链：

- session / run 创建。
- cancel、steer、resume、replay。
- 工具调用。
- 外部材料访问。
- policy 允许 / 拒绝 / 截断 / 等待。
- 语义级重复工具调用治理：allow / reuse / hint / require_justification / hard_stop。
- evidence 纳入。
- 外部副作用 idempotency key。

`LogAuditSink` 每行至少记录：

- `event_sequence`
- `event_id`
- `event_type`
- `event_class`
- `occurred_at`
- `session_id`
- `run_id`
- `attempt_id`
- `execution_id`
- actor / principal
- source / client
- operation context refs / digest
- `client_request_id`
- policy decision ref / summary
- reason
- payload ref / digest

`LogAuditSink` 不写大 payload，不复制 tool trace 冷数据。工具执行细节、证据锚点、截断、等待、provider request id 等深诊断信息属于 tool trace；audit 只记录可关联 ref / digest。audit 与 tool trace 必须都能通过 operation context 回答“这是什么业务的什么操作产生的记录”。

`purge_session` 不删除已经写入的 append-only audit JSONL 记录。purge 必须产生 purge tombstone audit record；既有 audit 行可以保留对已 purge EventLog rows 的 refs。audit 查询 / analyze 工具必须能识别 purge tombstone，并提示对应 Session 的源 EventLog facts 已被 purge。

audit projection 可以为了查询重组，但不能反向成为恢复、resume 或 memory 真源。

## 16. Read Model / Host Event Stream / Outbox

EventLog 是真源；Run result、Session timeline、Host event stream、audit、usage、tool trace、memory snapshot、outbox 都是 read model 或 projection。

公共读取语义：

```text
get_run(run_id)
  -> RunSnapshot(status, terminal summary, active attempt, cursors)

stream_run_events(run_id, cursor)
  -> ordered Host event stream from EventLog event_sequence cursor

get_session(session_id)
  -> SessionSnapshot(session status, active run, queued runs, timeline summary)
```

边界：

- `RunResult` 是 Run 终态投影，不是事实真源。
- `Session timeline` 是 UI / read model，不是事实真源。
- Session timeline 必须能表达“已取消的用户输入”和后续新输入是两条不同 `USER_INPUT_ACCEPTED`。聊天 UI 可以折叠或弱化 cancelled input，但不能把新输入建模为旧输入的 edit。
- `stream_run_events` 不触发新执行。
- 投影损坏或缺失时应能从 EventLog 重建。
- resume、memory、audit 责任链必须读取 EventLog canonical facts。

Outbox：

- Run terminal fact 提交后，final answer 已成为 Host 真源中的结果。
- 在线 / 已 attach 客户端的阅读路径是 Host event stream、Session timeline、RunSnapshot 或 read model；断线后通过 cursor 或 snapshot 补读。
- Outbox 不是客户端阅读 final answer 的通用接口，也不是 UI read model。
- Outbox 是离线 / 外部投递路径的 durable terminal delivery queue，表达 terminal result 可投递 / 可通知的 durable item。
- Outbox 解决的问题是：离线客户端或外部渠道不需要回放中间过程，也不能丢 final answer / terminal notification。
- Outbox 不包含完整 run timeline，不补 preview / progress / reasoning / streaming content。
- 在线阅读路径和 Outbox 离线投递路径必须指向同一个 terminal identity。UI / Service 应使用 `terminal_event_id` / `event_sequence` / `run_id` 去重，不得用 final answer 文本内容去重。
- UI 本地聊天记录应保存已展示 terminal answer 的 cursor，例如 `last_seen_terminal_event_sequence` 或 `seen_terminal_event_ids`。客户端重连时，Service / channel adapter 按该 cursor 从 Outbox 读取 terminal 增量；已展示过的 terminal item 不得作为新消息重复投递。
- Host 不负责 deliver to UI，不判断哪些客户端应该收到，不记录 GUI / CLI / WeChat / Web 的 channel 投递成功状态。
- Session 不持有唯一 default delivery target；HostCallContext 不包含 delivery target / delivery hint。
- 具体投递目标、投递成功状态、channel retry、WeChat / Web / notification binding 属于 Service / UI / channel adapter。
- 投递失败不能回滚 Run terminal。
- terminal transaction 不同步写 outbox 表；把 Run 终态提交和 outbox work queue 生成强绑定违反 Observer / Sink 边界。
- OutboxSink 按 `event_sequence` checkpoint 扫描 terminal EventLog facts，并 upsert outbox item。outbox 表是 projection / work queue，可由 EventLog 重建。
- optional outbox marker / notification 只是 wakeup；它丢失不得影响最终投递意图的派生。
- Outbox 必须具备幂等 item key、terminal event ref、result ref / digest、session_id、run_id、event_sequence 和 projection state。channel delivery state 不属于 Host truth。
- Outbox 不参与 resume、memory 事实重建或 Run 状态迁移。

阅读路径：

```text
Host EventLog
  -> Host event stream / Session timeline / RunSnapshot
      -> UI read path: GUI / Web / CLI / attached clients read here
      -> UI stores seen terminal cursor / terminal ids in local or Service state
```

OutboxSink 路径：

```text
OutboxSink checkpoint at event_sequence N
  -> scan terminal EventLog facts after N
  -> derive terminal delivery intent / notification item
  -> upsert outbox item by idempotency key
  -> advance checkpoint after projection commit
  -> Service / channel adapter consumes outbox item and owns channel delivery
```

outbox item idempotency key 必须由 terminal event identity、`run_id` 和 result digest 等稳定输入派生。重复扫描同一 terminal event 不得创建重复 outbox item。具体 hash 算法属于实现策略，但不得使用 final answer 文本内容作为去重主键。

离线补投推荐语义：

```text
UI restores local chat history
  -> reads last_seen_terminal_event_sequence or seen terminal_event_ids
  -> Service / channel adapter queries Outbox terminal items after cursor
  -> returns only unseen final answer / terminal notification items
  -> UI upserts by terminal_event_id / run_id before display
  -> UI / Service advances seen cursor after display or delivery ack
```

OutboxSink 只读 EventLog / Run durable truth，并写 outbox projection / work queue。它不能 append EventLog、不能更新 Run / Attempt，也不能改变 terminal 结果。

## 17. WorkerProxy / EngineWorker

无治理执行路径：

```text
Host -> Proxy / Stub -> EngineWorker -> Engine
```

治理路径：

```text
Host API
  -> Session / Run admission
  -> durable transaction: create Run / Attempt / initial EventLog fact
  -> Attempt execution context: attempt_id + execution_id + cancellation source
  -> WorkerProxy / RemoteStub
  -> EngineWorker -> Engine
  -> EngineEvent stream
  -> Host event ingest: validate run_id / attempt_id / execution_id
  -> durable EventLog append
  -> terminal transaction: append terminal event + close Attempt + update Run
  -> Host event stream / projection / result read model
```

Local / Remote topology：

```text
Host -> LocalProxy -> EngineWorker -> Engine
Host -> RemoteProxy -> RemoteStub -> EngineWorker -> Engine
```

Remote boundary：

- LocalProxy 是语义基准。
- RemoteProxy 是 transport substitution，不是治理 boundary。
- design 定义 remote semantic contract，不定义 wire protocol。
- RPC、ack frame、event replay、heartbeat、version negotiation、connection keepalive 是 Remote transport 细节；它们不得改变本节 remote semantic contract。
- `tool fact accepted ack` 是 ToolRuntime / EngineWorker 执行语义的一部分，不是 wire protocol 细节。LocalProxy 与 EngineWorker 之间也必须具备等价函数调用语义；RemoteProxy 只把该语义替换为远程传输。

远程执行不变量：

- Host 创建 Run、Attempt 与 `execution_id`。
- Host dispatch Attempt。
- RemoteStub / EngineWorker 只执行并回传带 `run_id`、`attempt_id`、`execution_id`、remote event id / remote ordering hint 的事件。
- Host 校验 `attempt_id + execution_id` 后决定是否 append EventLog `canonical_fact`。
- RemoteStub / EngineWorker 不 append EventLog，不关闭 Attempt，不更新 Run，不 takeover，不 resume。
- 迟到事件、重复事件或 `execution_id` 不匹配事件不能污染 EventLog `canonical_fact` 子集；最多进入诊断 / trace。
- Host 接受远端事件后重新分配 canonical `event_sequence`；remote ordering hint 不能成为 Host event stream cursor。
- cancel 由 Host 发起，通过 Proxy / Stub 传递到 EngineWorker 的 run-local cancellation token；远端不自行决定 Run 终态。
- Host 不保证 exactly-once 远程物理执行。dispatch 后、Host 确认前发生断连时，旧远端执行可能继续运行；Host 通过 `execution_id` 拒绝迟到事件，并依赖工具级 idempotency key / best-effort cancel 降低外部副作用风险。

Worker dispatch semantic contract：

```text
Host transaction commits ATTEMPT_STARTED with status STARTING
  -> dispatch record status = pending
  -> Attempt Dispatch reads dispatch record
  -> Attempt Dispatch waits for configured LLM lane
  -> after lane acquired, open short Host transaction
       -> re-read Run / Attempt / dispatch record
       -> verify Attempt STARTING, Run dispatchable, execution_id matches, dispatch record pending, no cancel / terminal committed
       -> if valid: update dispatch record status = dispatching, record dispatcher_instance_id / lane_name diagnostic refs, commit
       -> if invalid: commit nothing, release lane, do not call WorkerProxy
  -> WorkerProxy receives dispatch request with attempt snapshot
  -> EngineWorker accepts or rejects dispatch
  -> accepted: Host appends ATTEMPT_RUNNING
  -> rejected / startup timeout: Host closes Attempt through failure / lost path
  -> EngineWorker emits EngineEvent stream scoped by run_id / attempt_id / execution_id
  -> Host ingests events and owns all state transitions
```

LLM lane 控制资源容量，不控制 Session admission。acquire 不到 lane 时，Attempt 保持 `STARTING`，dispatch record 保持 pending / waiting-for-lane，不 append `ATTEMPT_RUNNING`，不启动 EngineWorker。lane acquire 成功后仍必须 recheck durable state，确认 Attempt 仍为 `STARTING`、Run 仍可派发、dispatch record 仍 pending、`execution_id` 仍匹配且 cancel / terminal 没有抢先提交。recheck 成功必须先把 dispatch record 原子推进为 `dispatching`，再调用 WorkerProxy；recheck 失败必须 release lane，不得派发。

`dispatching` 与 `dispatcher_instance_id` 只用于本机调度诊断、重复派发抑制和 recovery 判断，不是 lease，不是 fencing token，不授权旧 Attempt takeover。lane token 也不是 Host truth、不是 lease、不是 fencing token、不是 Attempt owner；它只是本地或运行时资源 guard。Attempt terminal、dispatch 失败、Host cancel 或 supervisor shutdown 都必须 release / cancel 对应 lane wait 或 held token。

EngineEvent stream 非正常终止必须由 Host 收口：

```text
EngineEvent stream EOF / error / transport close / worker crash
  AND no terminal event accepted for active Attempt
  -> Host records diagnostic
  -> Host evaluates Attempt as failed / lost / recoverable according to policy
  -> Host must not leave Run indefinitely RUNNING solely waiting for restart scan
```

该规则不是 lease / fencing 系统，也不保证 exactly-once 远程物理执行。它只是 Host 对自己执行流异常终止的本地治理；旧远端 worker 后续迟到事件仍按 `execution_id` 拒绝进入 canonical facts。

dispatch record 已进入 `dispatching` 后，如果 WorkerProxy 调用失败、worker reject 或 startup timeout：

```text
dispatch record = dispatching
  -> release lane token
  -> append dispatch diagnostic
  -> Attempt -> FAILED or LOST by failure type
  -> Run -> FAILED / RECOVERING / LOST by Host policy and recoverability
```

Host recovery scan 遇到 `dispatch record = dispatching` 且 Attempt 仍为 `STARTING` 时，必须具备 positive orphan proof 才能把该 Attempt 标为 `LOST`。随后 Run 按 recovery policy 进入 `RECOVERING` 或 `LOST`。`dispatching` / `dispatcher_instance_id` 不授权 takeover，也不允许旧 Attempt 继续拥有 Host 状态。

attempt snapshot 至少包含：

- `session_id`、`run_id`、`attempt_id`、`execution_id`。
- complete `AgentRunRequest`。
- cancellation source / token binding。
- ToolExecutor capability snapshot。
- policy snapshot ids / refs required to explain execution.

RemoteProxy、RemoteStub 与 EngineWorker 可以缓存 attempt snapshot 服务本次执行，但该 snapshot 不是远端治理状态；Host durable store 才是治理真源。

Tool fact accept ack 语义：

- ToolRuntime Host accept path 是工具事实 canonical 写入所有者。
- ToolRuntime 向 Host submit tool fact candidate 必须携带稳定 accept idempotency key。
- accept idempotency key 必须能由 attempt identity、tool call identity、tool fact kind、result digest / awaiting digest 等确定性输入派生。
- Host 已 durable accepted 但 ack 在本地回调或远程传输中丢失时，ToolRuntime 必须重试 accept；Host 通过 accept idempotency key 返回既有 accepted ack，不追加第二份 canonical fact。
- ack rejected 表示 Host 明确拒绝该 candidate；ack timeout 只表示 ToolRuntime 未确认 Host 是否 accepted，不能直接把 tool result 返回给 Engine。
- ToolRuntime 在 ack timeout 后不得让 LLM 消费未确认结果；它必须重试 accept，或按 Host policy 进入 governed tool error / awaiting / Attempt failed / recoverable。

## 18. ToolRuntime

ToolRuntime 是 Host-owned tool governance module。它可以随 EngineWorker 部署在本地或远端执行环境，但治理配置和真源来自 Host attempt snapshot。

### 18.1 ToolBundle Input / Runtime Tool View

Host 不能通过修改 Host 代码来增加业务工具。工具发现和注册必须外移到独立装配组件或 composition root；Host 包本身不得 import 具体业务工具模块，也不得内置财报工具清单。

Host 的工具输入是公共契约 `ToolBundle`：

```text
tool declaration / external tool registration module
  -> ToolDefinition
  -> ToolBundle
  -> create_host(..., tool_bundle=business_tool_bundle, ...)
  -> Host receives business ToolBundle as explicit construction parameter
  -> Host stores tool_bundle_digest / schema_digest / source refs in runtime snapshot
  -> Host creates attempt-local tool snapshot refs / digest
  -> ToolRuntime factory receives business ToolBundle
  -> ToolRuntime factory injects enabled framework tools
  -> effective ToolBundle
  -> ToolRuntime projects ToolSchema to Engine and governs ToolCallable execution
```

`ToolBundle` 是 `dayu.contracts` 已定义的工具声明集合，包含 `ToolDefinition` 元组，校验工具名唯一，并可投影为 Engine 可见的 `ToolSchema` 列表或 ToolRuntime 使用的 truncate specs。Host 只接收 `ToolBundle`，不参与工具发现、模块扫描或注册生命周期。

外部工具注册组件负责收集业务工具并生成业务 `ToolBundle`。它可以使用显式 provider 列表、配置绑定、包入口或 Service 装配；这些只是 discovery adapter，不改变 Host 语义契约。新增业务工具应通过新增工具包 / provider / 配置装配完成，不要求修改 Host 源码。

Host construction input 只能接收 `HostToolingOptions` 这样的 typed options：业务 `ToolBundle`、工具来源 refs、framework tool policy view 与后续治理所需的可解释 digest/ref。Host 不接收 discovery adapter 本体，不调用 provider 列表，不扫描业务包，也不把 per-run `tool_profile_ref` 作为 Phase 1 能力。未来若支持多个 scene tool profile，必须先定义 profile registry / ref 的 typed contract，并保证 profile 选择冻结到 Attempt snapshot；在此之前，Phase 1 只支持单个 construction-time business `ToolBundle`。

Host 对传入的业务 `ToolBundle` 只做治理所需的防御性校验和派生 metadata：

- schema 合法性。
- reserved framework tool name 冲突，例如 `fetch_more`。
- bundle / schema digest。
- attempt-local snapshot refs。
- policy binding refs 是否可解析。

attempt-local snapshot 必须冻结本次 Attempt 使用的业务 `ToolBundle` 派生 refs。工具目录变化不能静默影响已创建 Attempt。

`fetch_more` 不由外部业务 `ToolBundle` 提供。ToolRuntime factory 根据是否启用 TruncationManager 注入 framework tool，生成 attempt-local effective `ToolBundle`。RunInputBuilder 向 Engine 提供的 `tool_schemas` 和 ToolRuntime 执行使用的 callable binding 必须来自同一个 effective `ToolBundle`。`fetch_more` 仍走普通 tool dispatch / policy / accept barrier，不允许 Host 或 Engine 为它写特化分支。

Start / follow-up request 默认不携带 raw `ToolBundle`，因为 `ToolBundle` 包含 callable binding，不是普通 UI / Service request payload。Host construction / composition root 是业务 `ToolBundle` 的默认输入边界。若未来支持多 scene tool profile，Service 可以通过 typed `tool_profile_ref` 或独立 Host handle 选择工具集合；该扩展必须冻结到 Attempt snapshot，不能塞进无结构 metadata。

Retry / resume 默认复用源 Run / Attempt 已接受的 tool snapshot refs；policy 若要为关联新 Run 选择新的 tool snapshot，必须显式记录 source relation、new snapshot refs 与 policy decision。Replay 即使存在 effective `ToolBundle`，也不向模型暴露 tool schemas。

### 18.2 ToolRuntime Boundary

ToolRuntime 边界：

```text
Host
  -> receives business ToolBundle
  -> builds attempt-local tool snapshot refs and ToolRuntime snapshot
  -> ToolRuntime factory builds effective ToolBundle
  -> ToolRuntime implements ToolExecutor
  -> ToolRuntime wraps effective ToolBundle / dispatcher / policies
  -> optional TruncationManager
  -> optional built-in fetch_more tool
  -> EngineWorker receives ToolRuntime as ToolExecutor
  -> Engine calls ToolExecutor.execute(...)
```

ToolRuntime 内部必须拆成稳定 ports，避免把注册、执行、治理、截断、追踪和 Host accept 混成一个 god object。第一版最小 port 边界：

- ToolBundle / schema projection port。
- tool dispatcher / callable execution port。
- policy decision port。
- truncation / fetch_more port。
- awaiting / wait outcome port。
- duplicate governance port。
- Host tool fact accept port。
- `ToolTraceDiagnosticEmitter`。

第一版可以在同一模块或类中实现多个 port，但 public boundary 和测试必须保持语义分离。不得用单个 god function 混合 schema lookup、execution、truncation、policy、Host accept、tracing 和 wait handling。

`ToolTraceDiagnosticEmitter` 只提交结构化工具诊断记录 / refs，供 tool trace projection 生成 hot JSON 与 cold JSONL。它不是 EventLog appender，不拥有 canonical fact，不写 audit，不直接写 trace 文件，也不更新 Run / Attempt 状态。

语义：

- Host 持有 ToolRuntime 的治理 ownership。
- ToolRuntime 是 `ToolExecutor`。
- Engine 只看见 `ToolExecutor` protocol。
- Engine 不知道 `@tool`、`ToolDefinition`、TruncationManager、`fetch_more` 或业务工具实现。
- Host 不知道具体业务工具实现；Host 只消费外部传入的业务 `ToolBundle`、attempt-local tool snapshot refs 和工具治理策略。
- 远端 ToolRuntime 可以执行和截断，但不能 append EventLog、不能关闭 Attempt、不能更新 Run。
- ToolRuntime 必须遵守 Host-mediated accept barrier：工具事实必须先交给 Host durable accepted，收到 accepted ack 后，ToolRuntime 才能把对应 tool result 返回给 Engine 继续推理。LLM 不得消费 Host 真源中尚未 durable accepted 的工具事实。EngineEvent ingest 不能替代 ToolRuntime accept path 写工具 canonical facts。

Tool fact accept barrier 路径：

```text
Engine requests tool execution through ToolExecutor
  -> ToolRuntime applies policy / truncation / duplicate governance
  -> ToolRuntime executes tool or resolves reuse / awaiting
  -> ToolRuntime submits tool fact candidate to Host accept path
  -> Host validates attempt identity and payload durability
  -> Host appends TOOL_* canonical facts or rejects / diagnoses
  -> Host returns accepted ack with canonical event refs
  -> ToolRuntime returns tool result to Engine only after accepted ack
```

该路径对 LocalProxy 与 RemoteProxy 语义一致。LocalProxy 通过函数调用表达 accepted ack；RemoteProxy 通过等价远程请求 / ack 语义表达。远端 tool execution 本质上是把 LocalProxy 下的 tool execution / Host accept 调用改成远程调用；网络延迟、序列化成本或额外 round trip 不是放松 Host accept barrier 的理由。Remote transport 可以用不同 wire protocol 表达，但不能绕过 Host accept barrier。若 ack rejected 或 timeout，ToolRuntime 不得把对应工具结果返回给 Engine；它必须返回受治理的工具错误、awaiting / suspend，或让 Host policy 将 Attempt 收口为 failed / recoverable。

tool fact candidate 必须包含足以治理和追溯的信息：

- tool identity 与 tool call identity。
- normalized args digest 与可选 semantic duplicate key。
- payload ref / digest / evidence anchors。
- 截断发生时的 truncation descriptor / `scope_token` descriptor。
- 外部副作用或付费工具适用的 idempotency key。
- policy decision 与 diagnostic refs。
- accept idempotency key。

ToolRuntime 负责：

- 消费 Host 传入的业务 `ToolBundle` 并生成 attempt-local effective `ToolBundle`。
- 权限 / policy。
- 并发 / timeout / orphan cleanup。
- tool awaiting。
- truncation / fetch_more。
- 语义级重复工具调用治理。
- 通过 `ToolTraceDiagnosticEmitter` 发出 tool trace 所需诊断。
- 工具级 idempotency key 执行约束。

### 18.3 语义级重复工具调用治理

Engine 只负责同一次模型响应内的结构性工具调用协议，不理解工具语义、业务幂等性、用户意图或历史结果质量。语义级重复工具调用治理属于 Host / ToolRuntime。

治理目标不是禁止所有重复工具调用，也不是治理同一轮 / 同一 iteration 内正常出现的结构性工具调用。第一版只治理同一个 Run 内模型复读导致的重复工具调用，目标是减少无意义 token 和工具执行浪费。

重复判定信号：

- tool identity：工具名、工具版本、schema version。
- normalized arguments：去除无关顺序和默认值后的参数 digest。
- optional tool-provided semantic key：工具声明的 run-local 语义重复 key。
- accepted result digest / evidence anchor：当前 Run 内已接受结果是否等价或覆盖当前请求。

ToolRuntime 维护 run-local in-memory duplicate index，不需要 session-scope durable ledger。Host 崩溃后新 Attempt 不继承该内存索引；如需避免重复，依赖 RunInputBuilder 把已接受工具事实放回 messages，让模型看到已经查过什么。

policy action 必须分级：

- `allow`：重复调用有新 scope、新参数、新证据需求或用户明确要求。
- `reuse`：直接复用已接受工具事实 / evidence anchor，不重新执行工具。
- `hint`：append `GUIDANCE_INSERTED`，提醒模型已有事实或建议改查其它证据。
- `require_justification`：允许继续，但要求下一轮 messages 中保留模型为什么需要重复调用的上下文。
- `hard_stop`：判定为工具循环或违反幂等 policy，关闭当前 Attempt 为 failed / governed stop，并由 Host policy 决定 retry、replay 或失败。

EventLog 规则：

- 工具调用意图进入 `TOOL_CALL_REQUESTED`。
- policy 决策进入 `TOOL_CALL_GOVERNED`，至少包含 duplicate key、决策、scope、reason、相关 prior event refs。
- 真正执行并被接受的结果进入 `TOOL_RESULT_ACCEPTED` / `TOOL_TERMINAL_RESULT`。
- `reuse` 不伪造新的工具事实；它引用 prior accepted result，并在 messages 中表达为 Host 复用的已接受事实。
- audit / tool trace 必须能解释为什么某次重复调用被允许、复用、提示或阻断。

边界：

- 第一版只实现 run-local deterministic duplicate key；跨 Run、跨 Session、跨多年历史中的相似证据召回属于 Conversation Memory / retrieval，不属于重复工具调用治理。
- 对财报读取类 read-only 工具，默认优先 `reuse` / `hint`，除非参数或 evidence scope 明确变化。
- 对外部写入或付费工具，必须依赖工具 schema / policy 提供 idempotency key；Host 的 duplicate governance 不能替代工具级幂等。
- 该治理不能进入 Engine，也不能让 RemoteStub 拥有 Host 状态。

## 19. TruncationManager / fetch_more

`ToolTruncateSpec` 是截断的显式触发条件。无 spec、spec 未启用、策略未知或 limit 非法时，默认不截断。

执行路径：

```text
@tool(..., truncate=ToolTruncateSpec(...))
  -> ToolDefinition
  -> Host / ToolRuntime keeps ToolTruncateSpec
  -> Engine only receives ToolSchema
  -> Engine emits normal tool call
  -> ToolExecutor executes ToolCallable
  -> TruncationManager applies declared ToolTruncateSpec
  -> ToolExecutor returns normal tool result with truncation hint when needed
  -> truncation hint carries opaque cursor + scope_token for ordinary fetch_more
```

Truncation handle 语义：

- `cursor` 标识“从哪个被截断结果、哪个位置继续读”。
- `scope_token` 是 opaque capability / scope binding，用来证明本次 `fetch_more` 只能读取对应工具结果的后续内容。
- LLM-facing tool result 只暴露普通 `fetch_more` 所需的 opaque 参数，不暴露 Host 内部 cursor store、artifact path、payload layout 或远端 cache key。
- `cursor` / `scope_token` 进入 messages 或 EventLog 后，必须可恢复到足以完成后续 `fetch_more` 校验与读取的 durable descriptor；不能只存在于远端 ToolRuntime 进程内存。
- durable descriptor 保存的是 handle metadata、scope binding、artifact ref、digest、offset / page / path、expiry / retention policy 和 access policy；不要求 Host 持久化完整 raw payload。

`fetch_more` 是 Host / ToolRuntime 内置 framework tool，但必须作为普通 tool 暴露和执行：

```text
Host / ToolRuntime registers built-in @tool("fetch_more", ...)
  -> effective tool schemas include business tools + fetch_more
  -> model emits normal tool_call(name="fetch_more", arguments=...)
  -> ToolExecutor dispatches as normal tool call
  -> fetch_more callable validates cursor + scope_token through TruncationManager
  -> ToolExecutor returns normal tool result
```

硬约束：

- `fetch_more` 不能有 Host / Engine 特化分支。
- `fetch_more` 不拥有专属 Engine event 或专属 WorkerProxy 协议。
- `fetch_more` callable 内部通过闭包或协议访问 TruncationManager，这是普通 tool callable dependency injection。
- EventLog 视角下，`fetch_more` 是普通 tool request / result。
- `fetch_more` 不能成为业务工具注册表 public API。
- `fetch_more` 必须校验 `cursor` 与 `scope_token` 的绑定关系；scope 不匹配、过期、被撤销或 artifact digest 不匹配时，应返回普通工具错误结果，不得旁路读取。
- 当 truncation cursor / `scope_token` 的 ref 进入 messages 或 EventLog 后，该句柄必须可由 Host-governed durable cursor descriptor、artifact ref 或等价 snapshot 恢复；不能只存在于远端进程内存。
- Remote ToolRuntime 可以持有 attempt-local TruncationManager 和 short-lived cache，服务同一 Attempt 内的快速续读；这是优化，不是正确性前提。
- durable 不要求远端 ToolRuntime 在每次 truncate 或每次 `fetch_more` 前同步请求 Host。远端 ToolRuntime 可以随工具结果一次性回传 cursor descriptor / artifact ref / digest / scope binding；Host 接受工具事实时持久化该 descriptor。
- 跨 Host restart、Attempt `LOST`、resume、steer 或 replay 后，`fetch_more` 必须依赖 Host attempt snapshot / Host-governed cursor descriptor / artifact ref 恢复读取权限，而不是依赖旧远端内存。
- 远端不能把 cursor 或 `scope_token` 变成远端治理状态；Host 才能决定该句柄是否仍可用于当前 Run / Attempt / tool result。
- cursor 生命周期、TTL、读取 limit、重复续读、错误 envelope 和取消资源收口由 TruncationManager / ToolRuntime policy 定义。

## 20. Tool Awaiting / Wait Record

长事务或外部等待以 `ToolAwaitingOutcome` 进入 Host。

基本路径：

```text
ToolExecutor returns ToolAwaitingOutcome(await_spec, snapshot)
  -> ToolRuntime submits awaiting candidate to Host accept path
  -> Host transaction validates attempt identity and current dispatch state
  -> Host appends TOOL_AWAITING
  -> Host appends RUN_WAITING
  -> Host appends ATTEMPT_SUSPENDED
  -> Host creates active wait record
  -> Host updates Run.status = WAITING
  -> Host closes Attempt.status = SUSPENDED
  -> Host returns accepted ack / event refs
  -> Engine may emit tool_awaiting with accepted refs for diagnostic / preview
  -> Engine may emit run_suspended with accepted refs for diagnostic / preview
```

ToolRuntime Host accept path 是 awaiting canonical owner。Engine `tool_awaiting` / `run_suspended` 不能创建 wait record，不能把 Run 推入 `WAITING`，不能关闭 Attempt，也不能追加第二份 awaiting canonical facts。它们只能携带 accepted refs，作为 preview、diagnostic 或 idempotent confirmation。

如果 accepted ack 丢失，ToolRuntime 必须用同一个 accept idempotency key 重试，Host 返回既有 accepted refs。即使 Engine 后续 `tool_awaiting` / `run_suspended` 事件丢失，Host durable state 也已经完整；迟到 EngineEvent 只能 diagnostic / idempotent confirmation。

wait record 最小语义：

```text
wait_id
run_id
attempt_id
tool_call_id
tool_name
await_spec
snapshot_ref?
external_job_id?
idempotency_key?
resume_policy: callback | poll | manual
deadline / expires_at?
status: waiting | resolved | failed | cancelled | lost
```

wait record 状态语义：

- `waiting`：Host 已接受等待事实，Run 保持 `WAITING`。
- `resolved`：等待结果已被 Host durable accepted，并已触发 resume Attempt 创建。
- `failed`：外部等待确认失败，Run 按 policy 进入 `FAILED`、`RECOVERING` 或关联 retry。
- `cancelled`：Host 已取消 Run 或等待，不再接受该 wait record 的结果作为 `canonical_fact` 进入 EventLog。
- `lost`：Host 无法确认外部 job 状态，且 policy 放弃继续等待。

Resume 策略分层：

```text
wait signal source
  -> poll | callback | manual
  -> common Host resolve_wait pipeline
  -> append RESUME_REQUESTED
  -> append tool terminal/result fact
  -> append RUN_STARTED(start_reason=resume)
  -> create new Attempt
  -> rebuild messages
  -> resume Run
```

`poll`、`callback`、`manual` 只是发现等待结果已经到达的 adapter。稳定核心是 Host 内部统一的等待结果接收与治理入口：

```text
resolve_wait(wait_id, outcome, source, idempotency_key)
```

`resolve_wait` 不等待外部长事务完成，也不死等业务结果。结果未到时，poll adapter / callback endpoint / manual operator 不应调用它，或调用后得到结构化拒绝，例如 `outcome_not_ready`、`invalid_state`、`wait_not_found`。`resolve_wait` 本身是短事务 command，最多只因 SQLite transaction、CAS 或 busy timeout 做短等待和重试。

resume policy 覆盖 internal / manual、poll、callback 三类入口。所有入口都必须走同一个 `resolve_wait` pipeline，不能各自更新 Run / Attempt / EventLog。

约束：

- 如果工具启动外部 job，必须返回稳定 `external_job_id` 或等价 ref。
- 外部副作用必须先有工具级 idempotency key，再启动外部 job。
- wait record 是 Host durable 状态，不是 remote worker 状态。
- job 完成后，`resolve_wait` append `RESUME_REQUESTED`、tool terminal / result canonical fact、`RUN_STARTED(start_reason=resume)`、new Attempt row、`ATTEMPT_STARTED` 与 dispatch record，再 resume。
- 如果 job 状态无法确认，应进入 structured failed / lost。
- Engine 不读取 wait record，也不恢复旧 Agent / Runner。
- Host recovery scan 遇到 `WAITING` Run 时不得创建新 Attempt；它只能恢复 wait record 的 adapter 状态。
- wait record 的 `resume_policy` / `await_spec` / `external_job_id` 必须包含足以在 Host restart 后恢复 adapter observation 的 durable refs。adapter registry / lookup 由 Host composition root 提供 typed adapter binding；wait record 只保存 adapter key / policy ref / external job refs，不保存进程内 adapter 对象。
- `poll` adapter 从 wait record 读取 `external_job_id` / `await_spec` 后继续轮询，并在完成时调用同一个 `resolve_wait`。
- `callback` 入口必须验证认证、重放防护和 idempotency key，然后调用同一个 `resolve_wait`。
- `manual` resolve 只能由受控入口触发，并必须写 audit projection。
- wait poller 是 background runtime 中的 trigger / adapter。它观察 wait record 与外部 job，但只能通过 `resolve_wait` command path 提交结果；不得持有 EventLog appender，不得直接更新 Run / Attempt / wait record terminal state。
- wait record resolution 与 `RESUME_REQUESTED`、tool terminal/result fact、`RUN_STARTED(start_reason=resume)`、new Attempt row、`ATTEMPT_STARTED`、dispatch record 创建必须在同一事务或等价原子流程中收口。
- `resolve_wait` 幂等范围是 `(wait_id, idempotency_key)`。
- `resolve_wait` 幂等判断只基于 committed durable state；如果事务未 commit，重试应重新执行完整 resolution chain。
- 同一幂等键 + 同一 outcome 重试时，Host 返回既有 RunSnapshot / Attempt refs，不追加第二份 canonical fact，不创建第二个 Attempt。
- 同一幂等键 + 不同 outcome 必须返回 `idempotency_conflict`。
- 已 `resolved` 的 wait record 只允许幂等重放既有结果，不允许第二次 resolution。
- 非 `waiting` 状态的 wait record 不得被新的 resolution 改写；`cancelled` / `lost` 的迟到结果只能进入 diagnostic / tool trace。
- `cancelled` / `lost` wait record 的迟到 poll / callback result 不得作为 `canonical_fact` 进入 EventLog；只能进入 diagnostic / tool trace。
- adapter 观察到 wait record cancelled 后，可以 best-effort cancel / revoke / abandon 外部 job；该能力不能影响 Host Run terminal 正确性。

## 21. Suspend / Resume / Retry / Replay

`suspend`、`resume`、`retry`、`replay` 是不同语义。

Suspend / Awaiting：

```text
ToolRuntime receives ToolAwaitingOutcome
  -> ToolRuntime submits awaiting candidate to Host accept path
  -> Host validates attempt_id + execution_id
  -> Host appends TOOL_AWAITING / RUN_WAITING / ATTEMPT_SUSPENDED
  -> Host closes current Attempt as SUSPENDED
  -> Host updates Run to WAITING
  -> Host persists wait record
  -> Engine may emit tool_awaiting / run_suspended with accepted refs as diagnostic confirmation
```

Engine `tool_awaiting` / `run_suspended` 不拥有 Host waiting 状态迁移；它们不能创建 wait record、不能关闭 Attempt、不能更新 Run。

Resume：

```text
wait condition satisfied
  -> Host appends RESUME_REQUESTED
  -> Host appends tool terminal/result fact
  -> Host appends RUN_STARTED(start_reason=resume)
  -> Host creates new Attempt with new execution_id
  -> Host appends ATTEMPT_STARTED
  -> Host rebuilds complete AgentRunRequest.messages from EventLog canonical facts
  -> Host dispatches through LocalProxy / RemoteProxy
```

Retry：

- Retry 是调用方主动发起的公开 Host control API，Host policy 只负责允许、拒绝、复用事实和设置重试上限。
- Retry 通过函数式 `retry(run)` 语义触发；公共 API 为 `retry_run(host, run_id, request)`，语义是输入源 Run、返回关联的新 Run。
- Retry 必须有 `client_request_id` / idempotency key。
- Retry 不重开原终态 Run；原 Run 的 `FAILED` / `LOST` 等终态事实保持不可变。
- Retry 创建关联的新 Run，新 Run 再创建自己的 Attempt 和 `execution_id`。
- Retry 不复用旧 EngineWorker / Agent / Runner。
- Retry 是否复用源 Run 已接受工具事实由 retry policy 决定；默认复用已提交且仍有效的工具事实，不复用失败中的未接受输出。

Replay：

- Replay 是调用方主动发起的公开 Host control API，Host 不自动 replay，也不把 replay 当作 terminal 输出失败后的内部隐式修复策略。
- Replay 只用于 final answer 的格式、schema、结构、输出 envelope 或引用格式违反输出 policy，并且可以在不重复昂贵工具的前提下修复。
- 事实内容脏、幻觉、业务归因错误、证据不足、证据冲突不属于 replay 场景；这些情况必须通过新分析 / follow-up / retry / evidence retrieval / 新工具事实解决。
- Replay 通过函数式 `replay(run)` 语义触发；公共 API 为 `replay_run(host, run_id, request)`，语义是输入源 Run、返回关联的新 Run。
- Replay 必须有 `client_request_id` / idempotency key 和 replay reason。
- Replay 不重开原 `SUCCEEDED` Run；旧 final answer 保留为历史 assistant conclusion / rejected candidate，不是 verified fact。
- Replay 创建关联的新 Run，新 Run 再创建自己的 Attempt 和 `execution_id`。
- Replay 通过 EventLog 重建 messages，复用源 Run accepted tool facts / tool messages / evidence anchors。
- Replay 是 no-tool `AgentRunRequest.messages` 结构修复调用，不重新执行工具，不新增工具事实。主防线在 RunInputBuilder：replay Attempt 构造 `AgentRunRequest` 时不暴露 tool schemas，模型不应获得可调用工具。ToolRuntime 的 replay policy 拒绝只是 defense-in-depth。
- 源 Run 的 final answer 不作为普通 assistant conclusion 注入新 Run；它只能作为 `rejected_candidate` / repair context 与 validation errors / repair instruction 一起进入 messages。
- replay messages 必须约束模型只做结构修复，不引入新事实，不调用工具，不改变 evidence anchors。
- 如果 replay 执行期间模型仍发起 tool call，Host / ToolRuntime 必须按 replay policy 拒绝；默认治理动作是 hard stop 或 governed tool error，并记录 diagnostic / tool trace。不得把该 tool call 当作普通工具执行。
- Replay append `REPLAY_REQUESTED`，并在新 Run 上记录 `source_run_id` / `replay_of_run_id` 或等价关联。
- Session timeline 可以把 replay Run 标成“对某次回答的重放 / 修正”，并用 read model 指向最新 replay result；EventLog 保留完整 replay 链。

Retry / Replay 默认前置条件：

| 源 Run 状态 | retry_run | replay_run |
| --- | --- | --- |
| `SUCCEEDED` | 默认拒绝，除非显式 retry policy 支持重跑成功 Run | 仅在格式 / schema / 结构修复场景接受 |
| `FAILED` | retry policy 允许时接受 | 拒绝 |
| `LOST` | 仅当 policy 判断 durable facts 足够支持创建新 Run 重试时接受 | 拒绝 |
| `RECOVERING` | `invalid_state` | `invalid_state` |
| `RUNNING` / `WAITING` / `CANCELLING` | `invalid_state` | `invalid_state` |
| `QUEUED` | `invalid_state` | `invalid_state` |
| `CANCELLED` | 默认拒绝；未来 policy 可支持显式 rerun | 拒绝 |

## 22. Cancel

取消由 Host 发起和治理，Engine 只观察 run-local cancellation token。取消不是普通 error，也不是工具失败。

初始路径：

```text
client requests cancel
  -> Host appends CANCEL_REQUESTED
  -> if Run is QUEUED: Run -> CANCELLED
  -> if Run is RECOVERING before new dispatch: Run -> CANCELLED
  -> if Attempt STARTING and dispatch record pending / waiting_for_lane: Attempt -> CANCELLED and Run -> CANCELLED
  -> if dispatching or active Attempt running: Host appends RUN_CANCELLING and Run -> CANCELLING
  -> commit
  -> Host sends cancel through LocalProxy / RemoteProxy after commit only when dispatching / active worker exists
  -> EngineWorker maps cancel to run-local cancellation token
  -> Engine emits run_cancelled when cancellation wins execution boundary
  -> Host validates attempt_id + execution_id
  -> Host appends ATTEMPT_CANCELLED + RUN_CANCELLED
```

规则：

- `QUEUED` 且尚未创建 Attempt 的 Run 被取消时，直接进入 `CANCELLED`，不创建 Attempt。
- `WAITING` Run 被取消时，Host 直接收口为 `CANCELLED`：append `CANCEL_REQUESTED`，标记 active wait record cancelled，append `RUN_CANCELLED`；外部 job 的实际取消属于 adapter best-effort 能力，不作为第一版保证。
- `RECOVERING` 且新 Attempt 尚未 dispatch committed 时直接进入 `CANCELLED`；不创建新 Attempt，不进入 `CANCELLING`。
- Attempt `STARTING` 且 dispatch record 仍为 `pending` / `waiting_for_lane` 时直接收口：append `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED`，标记 dispatch record cancelled，cancel lane wait / wake dispatch scheduler，释放 active slot 并触发 queue promotion check；不通知 EngineWorker。
- dispatch record 已进入 `dispatching` 或 Attempt 已 `RUNNING` 时，必须 append `CANCEL_REQUESTED` + `RUN_CANCELLING` 并向 WorkerProxy 传播 cancel。`CANCEL_REQUESTED` 表达取消意图，`RUN_CANCELLING` 表达 Run 状态迁移。
- terminal fact 已提交后，cancel 不能改写 terminal。
- cancel 只阻止未来工作，不覆盖已接受事实。
- 已接受 tool result、awaiting outcome、final decision、canonical facts 继续保留。
- cancel 与 suspend 同时发生时，由 Host ingest 事务提交顺序决定。suspend / awaiting 已 canonical accepted 后，late cancel 不覆盖它，后续走 `WAITING -> CANCELLED`；cancel 已提交后，late suspend / awaiting candidate 不得把 Run 推入 `WAITING`，只能进入 diagnostic / tool trace 或被拒绝为 canonical fact。
- 如果外部 job 在 Run 已 `CANCELLED` 后回调或被 poll 到结果，Host 必须拒绝其结果作为 `canonical_fact` 进入 EventLog，只能记录 diagnostic / tool trace。
- cancel 控制消息最小携带 `run_id`、`attempt_id`、`execution_id`。
- 未引入 watchdog 强化治理前，cancel 请求发出后如果 active Attempt 超时仍无法确认，旧 Attempt 进入 `LOST`；若 `CANCEL_REQUESTED` 已 durable accepted 且 terminal fact 未抢先提交，Host 不得继续用户目标，Run 应按 policy 收口到 `CANCELLED` 或 `LOST`，不得创建新的正常执行 Attempt。
- 同一 `(run_id, client_request_id)` cancel 重试必须返回既有结果，不重复 append `RUN_CANCELLING`。Run 已是 `CANCELLING` 时，新的不同 cancel 请求不能重复制造状态迁移；可按 policy 返回当前状态或记录 diagnostic。
- 强制终止执行环境、后台 job reconcile、细粒度资源收口失败事实属于 cancel governance 扩展能力，不影响基础 Host 状态收口。

`cancel_session_runs(host, session_id, request)` 是 session-scope cancel command，用于客户端退出、supervisor shutdown 或用户明确停止该 Session 下全部未完成工作。它不是 `close_session`，不关闭新输入入口；不是 `purge_session`，不删除事实；也不表达“客户端拥有的所有 Session”。

`cancel_session_runs` 语义：

- 作用范围是指定 `session_id` 下所有 non-terminal Run。
- 包含 `QUEUED`、`RUNNING`、`WAITING`、`CANCELLING`、`RECOVERING`，以及 Attempt `STARTING` / waiting-for-lane 场景。
- 不影响其它 Session，不影响已终态 Run。
- 幂等范围是 `(session_id, client_request_id)`。
- queued Run 直接 `CANCELLED`，不创建 Attempt。
- Attempt `STARTING` 且尚未 dispatch / 正在 waiting-for-lane 时直接取消，不通知 EngineWorker。
- 已 dispatch / active running Attempt 走普通 `cancel_run` 传播到 WorkerProxy。
- `WAITING` Run 取消 wait record；外部 job 物理取消由 adapter best-effort。
- terminal 已抢先提交时 terminal 优先，`cancel_session_runs` 返回当前终态，不改写 terminal。
- 返回 `SessionSnapshot`，包含 cancel 后的 session / run summary。

客户端同时 attach 多个 Session 时，调用方必须逐个 session 调用 `cancel_session_runs`，并同时 cancel / close 自己持有的 lane wait 或 lane token。Host 不维护客户端到多个 Session 的 ownership 真源。

Host ingest 顺序是分布式竞态排序真源。不得用物理时间重写该规则。

## 23. RunInputBuilder

RunInputBuilder 是 Host 内部组件。它是 memory / EventLog / Service 场景输入进入 Engine 的唯一运行态入口。

RunInputBuilder 通过 typed input provider protocols 聚合输入，不读取上游内部结构，也不直接查询 UI / Service 临时状态。每类输入必须有稳定 provider contract，例如：

- `CurrentRunFactProvider`
- `SessionContinuityProvider`
- `MemorySnapshotProvider`
- `CompactArtifactProvider`
- `ToolSchemaSnapshotProvider`
- `SceneParameterProvider`
- `PolicySnapshotProvider`

这些 provider 只暴露 RunInputBuilder 所需的 typed view / refs，不暴露各自内部表结构、projection 私有状态或全局 registry。

第一版物理实现可以合并共享同一 EventLog reader 的 provider，但必须保持 typed input 边界。RunInputBuilder 不得读取 UI 临时文本、Session timeline 真源、全局 policy service locator 或 untyped metadata bags。

输入：

```text
current USER_INPUT_ACCEPTED canonical fact
current run semantic canonical facts
session / prior-run EventLog canonical facts needed for continuity
session memory snapshot
compact artifact / context snapshot refs when present
source Run accepted tool facts when retry / replay policy allows reuse
caller system messages / scene parameters
tool schemas snapshot
runner / policy snapshot refs
```

`USER_INPUT_ACCEPTED` 是当前用户 prompt 进入 RunInputBuilder 的唯一事实入口。UI / Service 可以提交用户输入给 Host，
但一旦进入 RunInputBuilder，就必须读取已持久接受并绑定到 Session / Run 的 `USER_INPUT_ACCEPTED` canonical fact；
不能从 UI 临时文本、request 临时字段或 Session timeline 旁路取当前 prompt。

输出：

```text
AgentRunRequest.messages
```

Service / caller 可以提供 system messages 或场景装配参数，但不能绕过 Host 直接拼装恢复 messages。

messages 构造顺序必须稳定：

1. Host / Service 提供的 system 与场景约束。
2. session memory stable layer：pinned state、tool-verified facts、open questions、assumptions。
3. 当前 `USER_INPUT_ACCEPTED` 与当前 Run 需要的 canonical facts，按 `event_sequence` 顺序投影为对模型有语义的 messages。
4. replay / retry / steer / resume guidance。
5. 当前 attempt 的工具 schema snapshot 与运行 policy。

同一 EventLog 在同一 policy 下必须构造出等价 messages；projection lag、preview delta 或 sink failure 不能改变 RunInputBuilder 输出。

RunInputBuilder 的输出必须能由输入 fact refs、memory snapshot cursor、compact artifact refs 与 policy snapshot 解释；不得依赖未持久化的旧 provider request、旧 EngineRunner 内存或 UI 临时状态。

应进入 messages 的典型事实：

- `USER_INPUT_ACCEPTED`、steer input、resume input、follow-up input。
- assistant final answer / assistant conclusion，作为对话连续性，不是 verified fact。
- accepted tool result、tool terminal result、evidence anchor / ref / digest。
- tool awaiting resolved 后的 terminal / result fact。
- Host memory block：pinned state、tool-verified facts、open questions、assumptions。
- `GUIDANCE_INSERTED`，如果影响后续 iteration。
- 必要的 cancel / resume / steer 说明，如果它影响当前继续目标。

不应进入 messages：

- audit-only facts。
- usage-only facts。
- stream fanout 状态。
- projection checkpoint。
- raw preview delta / reasoning delta。
- 内部 state transition 本身，除非模型需要理解其用户语义。

RunInputBuilder 不创建独立 RunInputBuildTrace 子系统；上下文构造和证据纳入的观测统一进入 tool trace / trace 体系。

## 24. Conversation Memory

Conversation Memory 从买方财报分析 Agent 的会话不变量出发：

- 目标稳定。
- 工具结果即事实。
- 追问连续性是刚需。
- 跨轮一致性优先于上下文丰富度。
- memory 克制。
- 展示态与运行态分离。

结构：

```text
Conversation Memory
  -> stable layer
      -> pinned_state
      -> tool-verified facts
      -> assumptions / open questions
      -> evidence anchors / tool facts
  -> history pool
      -> recent raw turns floor
      -> older raw turns
      -> episode summaries
```

`pinned_state` 至少包含：

- `current_goal`
- `confirmed_subjects`
- `user_constraints`
- `open_questions`

不变量：

- `pinned_state` 与 tool-verified stable facts 全量注入，不参与 history pool 竞争。
- `final_answer` 是 assistant role 产出的最终回答，只能作为 raw turn / assistant conclusion 参与连续性。
- `final_answer` 绝不能自动升级为 verified fact。
- verified fact 只接受工具事实。
- 用户输入进入 pinned state、约束或待验证候选，不直接成为 verified fact。
- memory projection 只消费 canonical facts。
- preview / reasoning / display-only facts 不进入 memory。
- memory snapshot 是 read model，可重建、可修复，不是事实真源。
- 第一版 memory snapshot 与 projection checkpoint 使用同一 SQLite durable store transaction 提交；checkpoint 不得先于 snapshot 落库。
- 跨存储 atomic commit marker 不进入第一版默认实现，只作为后续 memory storage split 能力。
- RunInputBuilder 消费 memory snapshot 时必须记录 snapshot cursor；后续 replay / audit 能解释当时看到的是哪一版 memory。
- RunInputBuilder 消费 memory snapshot 前必须校验 snapshot cursor 覆盖本次构造 messages 所需的 EventLog cursor。projection lag 不能改变同一 EventLog + policy 下的 messages。

memory snapshot 缺失或滞后的处理：

- snapshot cursor 滞后但 EventLog delta 在 policy 阈值内时，RunInputBuilder 可以从 EventLog canonical facts 重建所需 stable layer，并记录 diagnostic / trace。
- snapshot 缺失、损坏或 lag 超过 policy 阈值时，Host 进入结构化 context governance / projection repair path；这不是 Run crash recovery。
- memory projection lag 不得触发 Run 状态迁移，不得把 Run 推入 `RECOVERING`。
- 重建后的 snapshot checkpoint 不得先于 durable snapshot content 落库。

## 25. Context Governance

Context governance 是 Host 责任。Engine 不做 Host-side compact retry。

Host 负责：

- provider-aware context budget policy。
- RunInputBuilder 输入层预算分配。
- compact 触发。
- LLM episode summary compaction。
- pinned_state patch。
- compact 后保真检查。
- failure closeout。
- context overflow retry。
- compact event。
- compact event 与 projection 输入。

Context Governance 是 orchestrator，不直接写 memory snapshot、tool trace、audit projection 或 outbox。它只能 append / request append compact-related canonical facts 或 projection_signal，并通过 typed ports 调用 compactor、budget estimator、RunInputBuilder 和 policy view。memory、trace、audit 等 projection 只从已提交 EventLog 追平。

第一版不实现 provider-specific token counting / provider tokenizer adapter。Context Governance 使用 conservative estimator、provider-aware configured limits 和 safety margin 做 proactive 判断；Engine context overflow event 只是 reactive fallback，不是主要 compaction trigger。provider-specific tokenizer adapter 是后续能力。

### 25.1 Compact Event 响应路径

context compaction 有两类触发来源：

- proactive trigger：Host / RunInputBuilder 在 dispatch Attempt 前根据 provider-aware budget、tool facts、memory snapshot、当前用户输入和场景参数判断下一次 provider call 可能超过 policy 阈值。
- reactive trigger：Engine 在 Runner 报告 context length exceeded 后 emit `context_compaction_requested` EngineEvent，并以 recoverable `run_failed(context_compaction_required)` 收口本次 Engine run。

compact 是 Host governance，不是 Engine retry。proactive 与 reactive 使用不同状态路径：

```text
proactive trigger before dispatch
  -> append CONTEXT_COMPACTION_REQUESTED(trigger_source=proactive)
  -> Host ContextGovernance compacts inputs / memory / evidence summaries
  -> append CONTEXT_COMPACTED or CONTEXT_COMPACTION_FAILED
  -> RunInputBuilder rebuilds complete AgentRunRequest.messages
  -> append RUN_STARTED / ATTEMPT_STARTED
  -> dispatch Engine

reactive trigger from EngineEvent.context_compaction_requested
  -> validate attempt_id + execution_id
  -> append CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)
  -> close current Attempt according to policy
  -> Run -> RECOVERING when policy allows recovery
  -> Host ContextGovernance compacts inputs / memory / evidence summaries
  -> append CONTEXT_COMPACTED or CONTEXT_COMPACTION_FAILED
  -> append RUN_STARTED(start_reason=recovery)
  -> create new Attempt with new execution_id
  -> append ATTEMPT_STARTED
  -> dispatch Engine again
```

proactive path 是 pre-dispatch input governance，不表示旧 Attempt orphan，也不要求 Run 进入 `RECOVERING`。reactive path 才复用 `RECOVERING` 与 `RUN_STARTED(start_reason=recovery)`。

reactive path 约束：

- Host 必须先按 `attempt_id + execution_id` 校验 `context_compaction_requested` 是否来自当前 active Attempt。
- Engine 后续的 recoverable `run_failed(context_compaction_required)` 只能关闭当前 Attempt；它不能让 Engine 自己重试，也不能让旧 Attempt resume。
- Host 若接受恢复，应把 Run 标为 `RECOVERING`，执行 compact 后创建新 Attempt；若 compact policy 放弃恢复，Run 才进入 `FAILED`。
- `CONTEXT_COMPACTION_REQUESTED` payload 至少记录 trigger source、provider / runner error refs、provider request id、budget snapshot refs、input snapshot cursor 和 reason。
- `CONTEXT_COMPACTED` payload 至少记录 compacted snapshot ref、preserved fact refs、dropped / summarized ranges、evidence anchors retained、quality check result、budget after compact。
- `CONTEXT_COMPACTION_FAILED` payload 至少记录 failure reason、policy decision、whether retryable 和 diagnostic refs。

compact 不变量：

- compact 不能改写历史 EventLog facts，也不能让 summary 替代 evidence anchor。
- compacted snapshot / summary 是 read model 或 input artifact；是否进入 memory projection 必须由 memory policy 决定。
- RunInputBuilder 必须从 `USER_INPUT_ACCEPTED`、canonical facts、memory snapshot 和 compacted artifacts 重建完整 messages；不能复用失败 Attempt 的 provider request payload。
- 新 Attempt 必须有新的 `attempt_id` / `execution_id`；旧 Attempt 不 takeover、不 resume。
- compact 必须有 policy 上限。compaction 后仍超过 budget threshold 时，Host 必须按 policy 降级输入层或 append `CONTEXT_COMPACTION_FAILED` 并让 Run 进入 `FAILED` / `RECOVERING` / `LOST`；不得无限 compact retry。
- tool trace / audit 必须能解释哪些内容被保留、压缩、丢弃，以及为什么这样做。

参数默认值由 memory / context policy provider 定义。设计固定治理范围，policy 固定优先级和默认值。

provider tokenizer adapter 是 Host 预算治理的后续精确能力，不进入第一版。第一版使用保守 token estimator，阈值必须留出 safety margin；provider 返回 context length exceeded 仍是 reactive fallback，不是主要 compact 触发机制。

## 26. Evidence / Retrieval / Long-term Memory

长期 memory 不在第一版实现。第一版只做 session memory 与当前 run 的 context governance，但设计不得封死长期记忆。

跨多年弱信号归因靠证据链和 query-time retrieval，不靠无限扩大 session memory。

边界：

- Host 提供 evidence anchor、provenance、事实候选 / 验证标记等中立骨架。
- 原始网页新闻、公告、研报摘录、财报 chunk、source metadata、业务 event type、company / product / business-line ref 由业务工具和财报领域仓储管理。
- 早期 signal 进入 assumption / candidate，不因 summary 或 memory 收录变成 verified attribution。
- 后续分析通过 query-time retrieval 召回 signal anchors / evidence chunks / prior assumptions。
- 长期 summary 只能做导航；关键归因必须追到当前 run 已召回并验证过的工具事实。
- 召回失败、证据不足、证据冲突、signal stale、预算未纳入 RunInput 时，tool trace / trace 必须能解释。

## 27. Host Lifecycle / Recovery

Host 启动时必须执行 recovery scan：

- `QUEUED` Run 保持 `QUEUED`，等待调度。
- `WAITING` Run 保持 `WAITING`，等待 wait record resolution。
- `RUNNING` / `CANCELLING` Run 的 active Attempt 只有在具备 positive orphan proof 时，才能进入 `LOST`。
- 若 Run 的用户输入和必要 canonical facts durable accepted，Run 进入 `RECOVERING`。
- 若必要 facts 缺失或 policy 放弃恢复，Run 进入 `LOST`。

Recovery scan 不得让旧 Attempt takeover。恢复必须创建新 Attempt。

Recovery 的输入只能是 Host durable truth：Run / Attempt indexes、EventLog canonical facts、dispatch record、wait record、payload descriptors 和 host instance liveness record。Projection checkpoint、Session timeline、RunResult、audit、tool trace、outbox、memory snapshot lag 或其它 read model 不能作为 recovery scan 的前置条件或事实依据；这些 projection 只能在 recovery 提交 canonical facts 后按 `event_sequence` 追平。

Recovery scan semantic path：

```text
Host startup
  -> read Run / Attempt indexes
  -> classify each non-terminal Run
  -> append ATTEMPT_LOST / RUN_RECOVERING / RUN_LOST when needed
  -> keep QUEUED and WAITING in place
  -> for recoverable RECOVERING Run:
       -> rebuild messages from canonical facts
       -> append RUN_STARTED(start_reason=recovery)
       -> create new Attempt(status=STARTING)
       -> append ATTEMPT_STARTED
       -> dispatch after commit
  -> trigger queue promotion after terminal / recovery transitions
```

分类规则：

- `QUEUED`：不触发 Engine dispatch；只等待 admission promotion。
- `WAITING`：不创建 Attempt；只恢复 wait adapter observation。
- `RUNNING` / `CANCELLING` 且存在当前 Host 可确认控制的 dispatch record：继续观察，不接管。
- `RUNNING` / `CANCELLING` 且属于其它存活 Host instance：跳过 recovery，不 append `ATTEMPT_LOST`，不创建新 Attempt。
- `RUNNING` / `CANCELLING` 且具备 positive orphan proof：通过 CAS 将旧 Attempt -> `LOST`；Run 按 policy 与事实完整性进入 `RECOVERING` 或 `LOST`。
- `RUNNING` / `CANCELLING` 且只能判断 owner heartbeat stale，但无法证明 owner 进程已死：记录 suspect / diagnostic，跳过 recovery。
- `RECOVERING`：继续按 recovery policy 创建新 Attempt，或因超过上限进入 `LOST`。

多进程 recovery 不得把“当前进程不可确认控制”当作 orphan proof。一个 Host 进程无法控制另一个 Host 进程持有的 LocalProxy / RemoteProxy channel，并不表示该 Attempt 已丢失。

positive orphan proof 第一版来自本机 Host 进程存活证据，而不是远端 lease。推荐最小机制：

```text
dispatch_record.owner_host_instance_id
  -> host_instance durable row:
       host_instance_id
       pid
       process_start_token / boot_id / create_time
       heartbeat_at
       status
```

orphan 判定必须同时证明 owner Host instance 已不可能继续治理该 Attempt，例如 pid 已不存在，或 pid 已复用但 process_start_token 不匹配，并且 heartbeat 已过期。`heartbeat_at` 单独不构成 orphan proof；进程卡顿、调试暂停或长时间阻塞不能导致其它 Host 进程误杀 active Attempt。`pid` 单独也不构成 orphan proof；pid 可能复用，必须配合 process_start_token / boot id / create time 等启动指纹。

只有 positive orphan proof 成立后，才能 CAS `ATTEMPT_LOST` -> `RUN_RECOVERING` -> new Attempt。该机制不是重 lease / fencing：它不授予远端执行 ownership，不允许旧 Attempt takeover，只用于证明原 Host owner 是否已经不可能继续治理该 Attempt。

### 27.1 已接受 Prompt 的恢复语义

用户可见目标：

```text
用户已经提交 prompt
  -> Host 已 durable append USER_INPUT_ACCEPTED
  -> LLM 尚未返回 final answer
  -> Host 崩溃 / 进程退出
  -> Host 重启后仍应最终产出 answer
```

系统真实语义：

```text
USER_INPUT_ACCEPTED durable accepted
  -> old RUNNING / CANCELLING Attempt marked LOST only after positive orphan proof
  -> Run enters RECOVERING when recovery policy allows
  -> RunInputBuilder rebuilds complete AgentRunRequest.messages from EventLog
  -> Host creates new Attempt + new execution_id
  -> Host dispatches Engine again
  -> final_answer is accepted into EventLog / RunResult
  -> final answer is visible through Host event stream / read model
  -> Outbox terminal delivery item can be derived for offline / external delivery
```

不变量：

- 用户 prompt 只有在 `USER_INPUT_ACCEPTED` 已提交后才具备恢复语义；若崩溃发生在 durable append 之前，Host 没有事实真源，不能凭空恢复这次输入。
- Recovery 不恢复旧 Engine / Agent / Runner / provider request，也不接管旧远端 worker；旧 Attempt 只有在 positive orphan proof 成立后才能进入 `LOST`。
- 新执行必须基于 EventLog canonical facts 重建完整 messages，并创建新 Attempt / 新 `execution_id`。
- 用户不需要感知 Run / Attempt 细节；用户可见语义是“已提交 prompt 不丢，之后仍能收到 answer”。
- 如果 recovery policy 放弃恢复、必要 facts 缺失、重复恢复超过限制或后续新 Attempt 失败，Run 应进入结构化 `FAILED` / `LOST`，不能伪造成功 answer。

attempt dispatch record 最小语义：

```text
owner_host_instance_id
run_id
attempt_id
execution_id
worker_kind: local | remote
dispatch_started_at
last_event_at?
connection_state?
```

dispatch record 不是 lease，也不是 fencing token。它帮助 Host 识别本次 Attempt 的 owner Host instance、执行通道和诊断状态。当前进程不能确认控制该 dispatch record 时，只能说明当前进程不能接管；不能单独证明旧 Attempt 已丢失。

`host_instance_id` 是 Host 进程启动时生成的本进程实例标识，用于 host instance liveness record 与 dispatch record 关联。它不是 lease、不是 fencing token、不是远端 owner。相同 `host_instance_id` 本身也不能授权 takeover；positive orphan proof 只能证明原 owner 已不可能继续治理，不能允许接管旧 Attempt。

Host graceful shutdown：

- 停止接收新 start_run。
- 尽力向 active Attempt 传播 cancel / shutdown signal。
- 持久化 shutdown diagnostic fact 或 projection diagnostic。
- 不得伪造成功 terminal。

shutdown grace timeout 由 shutdown policy 配置。

## 28. 第一版 Non-goals

第一版不实现：

- 长期 memory public edit / reset / forget API。
- 完整远程 wire protocol 细节。
- 强制终止远程执行环境和复杂 job reconcile。
- 重型消息系统。
- 重 lease / fencing 系统。
- 业务层财报语义抽取。
- 外部渠道投递保证高于 outbox retry 语义。

这些 non-goals 不能削弱第一版的 durable facts、admission、EventLog、cancel 最小收口、resume、新 Attempt 语义和本地多进程一致性。
