# Host P8 Handoff Plan：Attempt Lease / Recovery / 多进程并发基础

## 1. 目标与动机

P8 目标是在 P6 durable EventLog / Run State / Projection 与 P7 tool trace projection 之上，落地 Attempt owner 真源、lease / fencing、stale / orphan recovery、`terminal_event_position` 原子关联，以及真实多进程并发验证。动机成立：Full-Governance Multi-Turn 不能只依赖 durable append；只要多个 Host 进程可能同时恢复、续跑或终结同一个 internal attempt，就必须有跨进程一致的 owner secret 与全局单调 fencing token，阻止旧 owner 迟到写入污染 EventLog、Run state、Attempt state、projection checkpoint 或 tool trace。

P8 是 P9 Session / Run lifecycle admission、跨进程 cancel、P11 replay、P12 outbox、P14 wait / resume 的必要基础。P9 可以用唯一约束 / 行锁解决 `client_request_id` 幂等与同 Session active Run admission，但 attempt 执行权、恢复权、迟到写入拒绝和 orphan 收口必须先在 P8 固定。

本阶段必须产出：

- Attempt owner lease：owner token、owner id、lease expiry、renew heartbeat、CAS acquire、CAS renew、terminal close。
- Fencing：所有 attempt-scoped 写入必须携带当前 owner secret 与全局单调 fencing token；旧 owner、过期 owner、非 owner 或旧 fencing token 的迟到写入返回 typed fencing refusal。
- Recovery 主路径：P8 不 takeover 同一 attempt。过期 / orphan attempt 先通过 owner/fencing CAS 标记为 `STALE`、`RECOVERING` 或 `LOST` 诊断终态，再创建新的 recovery attempt，使用新的 `attempt_id` / `attempt_index`，并记录 `recovered_from_attempt_id`。
- ToolRuntime facts fencing：`TOOL_RESULT_TRUNCATED`、`TOOL_CURSOR_ISSUED`、`TOOL_FETCH_MORE_REQUESTED`、`TOOL_FETCH_MORE_COMPLETED`、`TOOL_FETCH_MORE_FAILED`、`TOOL_CURSOR_EXPIRED`、`TOOL_CURSOR_DENIED` 都属于 attempt-scoped Host-owned canonical facts，必须走 owner fencing。
- `terminal_event_position` 关联：terminal event append、owner fencing、attempt terminal close、`terminal_event_position` 写入必须在同一个 `BEGIN IMMEDIATE` 事务中完成。
- Observer 边界固定：P8 将 `ObserverSink.process` 升级为 async 协议，消除 P6/P7 sync-async bridge；P8 仍不实现 observer claim / lease，不升级 observer ownership。后台 observer drain / observer claim 后移到 #28 或 P15。
- 真实多进程验证：基础 deterministic multiprocessing 测试默认可运行；重压版慢硬盘 + Docker Linux stress 作为手工增强项，由 GitHub issue #38 跟踪。基础测试必须覆盖跨进程 append、terminal race、stale recovery、observer drain。
- 多平台操作封装：P8 必须封装真实 multiprocessing 测试 / smoke 所需的平台差异，禁止在测试和 smoke 中散落 start method、join timeout、进程终止、临时 SQLite path、跨进程结果收集等平台分支。该封装先定位为测试 / smoke helper，不提升为 Host 生产 launcher。
- Fenced late write diagnostic：P8 首版不把 fenced late write 写入 EventLog diagnostic RunEvent。非 owner / stale owner 不应污染 canonical facts；拒绝以 typed error / result 和安全日志表达。若后续需要 audit rejected write，另设治理 issue。

验收信号：

- 多进程下同一 attempt 同一时刻只有一个有效 owner 能推进 attempt-scoped 写入。
- lease 过期后旧 owner 的 append / attempt update / terminal close / ToolRuntime fact append 被拒绝，新 owner 只能通过新 recovery attempt 继续治理，不写同一 attempt。
- terminal attempt 记录的 `terminal_event_position` 与 durable EventLog terminal fact 同事务同源。
- async observer drain / startup_reconcile 在 owner recovery 后仍按 EventLog checkpoint at-least-once 语义工作，不读取 owner side channel。
- `utils/smoke_host_p8_attempt_lease.py` 输出 owner acquire / renew / fence / recover / terminal_event_position 摘要，不泄露完整 token，不打印大 prompt / tool result。

## 2. 非目标

P8 不实现以下能力：

- 不做 RemoteProxy / RemoteStub。
- 不做完整 Session / Run lifecycle admission，不实现 `client_request_id` 幂等，不固定最终 Host public interface；这些属于 P9。P8-S8 落地的 durable conversation memory read model recovery 是 Host internal 治理能力，不等同于 P9 public memory edit / reset / forget API；S8 不固定 public memory API、不让 UI / Service 参与恢复、不迁移业务 memory。
- 不做完整 ToolRegistry governance；权限、middleware、tool catalog 属于 P10。
- 不做 Outbox / Wait / Suspend / Resume。
- 不把 lane / runtime dependency 实现为 Host 私有业务层；P8 不实现 lane。
- 不迁移业务工具，不让 Host / Engine 理解 fins/doc/web 业务语义；财报文档存取仍只能由业务工具通过 `dayu.fins.storage` 保证。
- 不做 P7 analyzer enhancement；partial tool calls 的 trace 分析增强只登记边界或后续 owner，不在 P8 扩展 analyzer 诊断面。
- 不做 observer claim / lease，不把 ProjectionCoordinator 升级为后台消费者 ownership 模型。
- 不做旧库兼容读取或兼容测试。涉及 schema 变更时，按全新 schema 起库处理。

## 3. 直接证据

当前代码与文档显示 P8 问题真实存在，且严重性没有被高估：

- `docs/host/migration-plan.md` §4.2 将真实多进程 stress、owner lease / fencing / orphan recovery、attempt `terminal_event_position` 写入都标为 `deferred-with-owner: P8`。
- `docs/host/migration-plan.md` §4.3 将 partial tool calls 完整语义标为 `deferred-with-owner: P8`，并记录 `LocalRunHarness` 已接近 God Object 阈值，P8/P9 应继续拆分职责。
- `docs/host/design.md` §3.1 要求 internal `Attempt` owner / lease / fencing、startup recovery 对 orphan / stale 状态调和都必须跨进程一致，不能依赖单进程内存锁。
- `dayu/host/_durable_event_store.py` 已有 SQLite WAL、`BEGIN IMMEDIATE`、`UNIQUE(run_id, sequence)`、global `event_position`、terminal guard，说明 P6 durable facts 是可用基础；但 `host_attempts` schema 目前只有 `attempt_id/run_id/attempt_index/state/started_at/finished_at/terminal_event_position/failure_summary`，没有 owner token、lease expiry 或全局单调 fencing token。
- `dayu/host/_run_state_store.py` 的模块 docstring 明确 P6 不实现 admission、owner lease、fencing、orphan recovery；`AttemptStateStore.update_state` 目前只按 `attempt_id` 更新状态，没有 owner compare-and-set 条件。
- `dayu/host/_run_harness.py` 的 `_finish_attempt_if_durable` 在收到 terminal event 时没有从 EventLog 取 global position，`terminal_position` 始终为 `None`，导致 `host_attempts.terminal_event_position` 继续空置；terminal EventLog append 与 attempt update 也是两个事务。
- `dayu/host/_tool_runtime.py` 多个路径直接调用 `event_store.append(...)` 写入 tool runtime canonical facts，当前 `ToolExecutionContext` 不携带 Host owner context，旧 owner 可能绕过 attempt fencing 写入工具事实。
- `dayu/host/_event_observer.py` 的 `ObserverSink.process` 仍是同步协议；`ProjectionCoordinator` 只有进程内 `_drain_lock`，没有跨进程 observer claim / lease。P6/P7 已出现 sync-async 阻抗：memory observer 通过 `_run_async` 桥接 async store，tool trace observer 执行文件 IO。P8 固定升级 `ObserverSink.process` 为 async 协议，但不引入 observer claim / lease。
- 当前 `tests/host` 只有单进程 asyncio 并发、checkpoint、durable harness、tool trace projection 测试；没有真实 deterministic `multiprocessing` 测试覆盖跨进程 append、terminal race、observer drain / recovery。

## 4. 前置条件

- P6 durable EventLog、`HostStorage`、`DurableRunEventStore`、Run / Attempt minimal state、`ProjectionStore`、`ProjectionCoordinator` 已落地。
- P7 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT`、tool trace observer / JSONL sink、ToolRuntime `iteration_id` 修复已落地，tool trace 默认 best-effort。
- 当前工作基线包含 `docs/reviews/code-review-20260508-001.md` 中 ToolRuntime `iteration_id` 修复结论。
- 进入代码实施前必须先完成本 plan review fix 与复审；review findings 修复并复审通过后再实施。

## 5. 架构边界

P8 必须新增 Attempt supervision 边界，避免继续膨胀 `LocalRunHarness`：

```text
LocalRunHarness
  -> AttemptSupervisor
      -> AttemptLeaseStore / AttemptStateStore
      -> acquire / renew / fence / terminal close / recovery
      -> AttemptScopedRunEventAppender
  -> DurableRunEventStore
      -> durable append with position under the same HostStorage transaction
  -> ToolRuntime
      -> receives an attempt-scoped append port for Host-owned tool facts
  -> ProjectionCoordinator
      -> async drain / startup_reconcile from durable EventLog only
```

原则：

- Host 是 attempt ownership 真源；Engine 不理解 owner token、lease、fencing，也不反向依赖 Host storage。
- Attempt owner token 只在 Host internal 执行上下文流动，不进入 public API、普通日志、README 示例、memory projection 或 smoke 大块输出。
- Durable EventLog 仍是事实真源。P8 fencing 保护“谁可以写”，不改变 append-before-stream、per-run cursor、global position、terminal guard 的 P6 事实语义。
- `LocalRunHarness` 只能编排 attempt supervisor、event append 与 projection drain，不承载 lease SQL、recovery scan、token 校验或 fencing error 策略。
- Observer / projection 默认仍消费 EventLog，不消费 owner side channel；owner recovery 只能影响 attempt/run 状态与后续 append 权限，不能要求 observer 读取进程内 owner 状态。
- 多平台 helper 的职责边界：P8 只在 `tests/host` / `utils` 范围封装 multiprocessing 测试和 smoke 的平台差异。若后续发现某个 helper 属于层中立运行时能力，例如 atomic replace / directory fsync / signal / process termination / safe temp path，再单独评估是否进入 `dayu.runtime`；P8 不把测试用 process launcher 做成 Host 生产能力。

## 6. 最终契约 / Schema / 状态机

### 6.1 内部类型

`AttemptState` 继续由 `dayu/host/_internal_contracts.py` 承载并扩展；其余新增 lease / fencing / recovery 类型放入 `dayu/host/_attempt_lease.py`。这些类型只供 Host internal 使用，不进入 `dayu.host.__all__`。

```python
class AttemptState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUSPENDED = "suspended"
    STALE = "stale"
    RECOVERING = "recovering"
    LOST = "lost"


@dataclass(frozen=True, slots=True)
class AttemptOwnerToken:
    value: str

    @classmethod
    def new(cls, *, token_bytes: int = ATTEMPT_OWNER_TOKEN_BYTES) -> "AttemptOwnerToken": ...
    def digest(self) -> str: ...
    def masked(self) -> str: ...


@dataclass(frozen=True, slots=True)
class FencingToken:
    value: int


@dataclass(frozen=True, slots=True)
class AttemptOwnerContext:
    attempt_id: str
    run_id: str
    attempt_index: int
    owner_id: str
    owner_token: AttemptOwnerToken
    fencing_token: FencingToken
    lease_expires_at: datetime


class AttemptLeaseDecision(StrEnum):
    ACQUIRED = "acquired"
    BUSY = "busy"
    TERMINAL = "terminal"
    FENCED = "fenced"


@dataclass(frozen=True, slots=True)
class AttemptLeaseResult:
    decision: AttemptLeaseDecision
    owner_context: AttemptOwnerContext | None
    current_state: AttemptState
    current_owner_id: str | None
    lease_expires_at: datetime | None
    reason: "AttemptFencingReason | None"


class AttemptFencingReason(StrEnum):
    OWNER_MISSING = "owner_missing"
    OWNER_MISMATCH = "owner_mismatch"
    LEASE_EXPIRED = "lease_expired"
    FENCING_TOKEN_MISMATCH = "fencing_token_mismatch"
    ATTEMPT_NOT_RUNNING = "attempt_not_running"
    ATTEMPT_TERMINAL = "attempt_terminal"
    RUN_TERMINAL = "run_terminal"
    STORAGE_CONFLICT = "storage_conflict"


@dataclass(frozen=True, slots=True)
class AttemptFencingError(Exception):
    attempt_id: str
    run_id: str
    reason: AttemptFencingReason
    current_state: AttemptState | None
    owner_id: str | None
    fencing_token: FencingToken | None


class AttemptRecoveryAction(StrEnum):
    NOOP_TERMINAL = "noop_terminal"
    MARK_STALE = "mark_stale"
    MARK_RECOVERING_AND_CREATE_ATTEMPT = "mark_recovering_and_create_attempt"
    MARK_LOST = "mark_lost"


@dataclass(frozen=True, slots=True)
class AttemptRecoveryDecision:
    action: AttemptRecoveryAction
    source_attempt_id: str
    recovery_attempt_id: str | None
    recovery_attempt_index: int | None
    reason: str


@dataclass(frozen=True, slots=True)
class AttemptTerminalLink:
    attempt_id: str
    run_id: str
    terminal_state: AttemptState
    event_cursor: RunEventCursor
    event_position: GlobalEventPosition


@dataclass(frozen=True, slots=True)
class AttemptLeaseConfig:
    ttl: timedelta
    renew_interval: timedelta
    owner_id_prefix: str
```

默认配置值集中定义在 `_attempt_lease.py`，但真实运行时必须通过 Host 装配层注入
`AttemptLeaseConfig`，不能让 public `start_run` 调用方或业务调用方逐次传入 lease TTL：

- `ATTEMPT_OWNER_TOKEN_BYTES: int = 32`
- `DEFAULT_ATTEMPT_LEASE_CONFIG = AttemptLeaseConfig(ttl=timedelta(seconds=30), renew_interval=timedelta(seconds=10), owner_id_prefix="host")`

`AttemptSupervisor` 接收 `AttemptLeaseConfig` 与可注入 `UtcClock`。Store 层不自己决定 TTL；
`AttemptLeaseStore` 只接收 supervisor 计算后的 `lease_expires_at` 或等价强类型值。所有时间使用
timezone-aware UTC `datetime`，由可注入 `UtcClock` 提供。测试不得依赖真实 sleep 判断 lease 过期。

### 6.2 Schema

P8 按全新 schema 起库处理，固定扩展 `host_attempts`，并新增全局单调 fencing token 分配表。
不新增 `host_attempt_leases` 备选表：

```sql
CREATE TABLE IF NOT EXISTS host_fencing_tokens (
    fencing_token INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    issued_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_host_fencing_tokens_resource
ON host_fencing_tokens (resource_type, resource_id, fencing_token);

CREATE TABLE IF NOT EXISTS host_attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    attempt_index INTEGER NOT NULL,
    state TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    terminal_event_position INTEGER,
    failure_summary TEXT,
    owner_id TEXT,
    owner_token_hash TEXT,
    fencing_token INTEGER,
    lease_expires_at TEXT,
    lease_renewed_at TEXT,
    recovered_from_attempt_id TEXT,
    stale_marked_at TEXT,
    UNIQUE (run_id, attempt_index)
);

CREATE INDEX IF NOT EXISTS idx_host_attempts_run_state
ON host_attempts (run_id, state);

CREATE INDEX IF NOT EXISTS idx_host_attempts_lease
ON host_attempts (state, lease_expires_at);

CREATE INDEX IF NOT EXISTS idx_host_attempts_recovered_from
ON host_attempts (recovered_from_attempt_id);
```

字段语义：

- `host_fencing_tokens.fencing_token` 是 Host durable 全局单调 fencing token。每次 acquire 新 owner
  lease 都必须先在同一 storage transaction 中插入该表，取得新的 token，再写入对应资源行。
- `resource_type/resource_id` 描述 token 所属资源。P8 首个消费者是
  `resource_type='attempt'`、`resource_id=attempt_id`；后续 Session / Run / Outbox / Wait /
  Remote / Observer claim owner 必须复用同一 fencing 原则。
- `owner_token_hash` 存储 `AttemptOwnerToken.digest()`，永不存明文 token。
- `owner_id` 是诊断摘要，例如 `host:<pid>:<boot_id_short>`，不得作为授权凭据。
- `fencing_token` 存储当前 attempt owner 的全局单调 fencing token；fencing 必须同时校验
  token hash 与 fencing token。
- `lease_expires_at` 是当前 owner lease 到期 UTC ISO 字符串；terminal / stale / lost 状态可保留最后值用于诊断。
- `lease_renewed_at` 是最近一次 acquire / renew UTC 时间。
- `recovered_from_attempt_id` 只写在新 recovery attempt 上，指向来源 attempt。
- `stale_marked_at` 只写在旧 attempt 被标记 `STALE` / `RECOVERING` / `LOST` 时。
- `terminal_event_position` 对正常 terminal attempt 必须非空；`STALE` / `RECOVERING` / `LOST` 这类无 terminal RunEvent 的诊断终态可为空。

### 6.3 Attempt 状态机

最终 `AttemptState` 为：

```text
CREATED
RUNNING
SUCCEEDED
FAILED
CANCELLED
SUSPENDED
STALE
RECOVERING
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
RUNNING -> RECOVERING
RUNNING -> LOST
STALE -> RECOVERING
STALE -> LOST
```

语义：

- `CREATED`：记录已创建但尚未持有有效 owner。P8 主路径应在同一事务内创建并 acquire 到 `RUNNING`，该状态主要服务可诊断中间态与测试。
- `RUNNING`：当前 attempt 有有效 owner lease；只有匹配 owner token hash + 全局单调 fencing token 且 lease 未过期的 owner 可以写 attempt-scoped facts。
- `SUCCEEDED` / `FAILED` / `CANCELLED` / `SUSPENDED`：正常 terminal attempt，必须同事务写入 terminal EventLog position。
- `STALE`：旧 owner lease 过期，结果未知，当前 attempt 已关闭执行权，不允许再写 attempt-scoped facts。
- `RECOVERING`：旧 attempt 已被 recovery CAS 关闭，并且同一事务创建了新的 recovery attempt；旧 attempt 不再可执行。
- `LOST`：结果无法确认且当前 policy 不创建 recovery attempt；不允许再写 attempt-scoped facts。

P8 recovery 主路径使用 `RUNNING -> RECOVERING` 并创建新 recovery attempt；`STALE` 用于扫描只标记不立即创建 recovery attempt 的诊断路径；`LOST` 用于无法安全恢复的诊断路径。P8 不允许 `STALE` / `RECOVERING` / `LOST -> RUNNING`，也不允许任何路径 takeover 同一 attempt。

### 6.4 Store / Supervisor API

`AttemptStateStore` 继续只负责 SQL 与 row mapping；`AttemptSupervisor` 负责生命周期编排。

```python
class UtcClock(Protocol):
    def now(self) -> datetime: ...


@dataclass(slots=True)
class AttemptLeaseStore:
    storage: HostStorage
    clock: UtcClock

    def acquire_new_attempt(
        self,
        *,
        tx: HostStorageTransaction,
        attempt_id: str,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None,
        owner_id: str,
        owner_token: AttemptOwnerToken,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult: ...

    def renew(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult: ...

    def verify_owner(
        self,
        *,
        tx: HostStorageTransaction,
        owner_context: AttemptOwnerContext,
    ) -> None: ...

    def mark_stale_or_lost(
        self,
        *,
        tx: HostStorageTransaction,
        attempt_id: str,
        expected_fencing_token: FencingToken,
        state: AttemptState,
        failure_summary: str,
    ) -> AttemptRecoveryDecision: ...

    def mark_recovering_and_create_attempt(
        self,
        *,
        tx: HostStorageTransaction,
        source_attempt_id: str,
        source_fencing_token: FencingToken,
        run_id: str,
        next_attempt_index: int,
        recovery_attempt_id: str,
        owner_id: str,
        owner_token: AttemptOwnerToken,
        lease_expires_at: datetime,
    ) -> AttemptLeaseResult: ...


@dataclass(slots=True)
class AttemptSupervisor:
    storage: HostStorage
    lease_store: AttemptLeaseStore
    event_store: DurableRunEventStore
    lease_config: AttemptLeaseConfig
    clock: UtcClock

    async def lease_context(
        self,
        *,
        run_id: str,
        attempt_index: int,
        recovered_from_attempt_id: str | None,
    ) -> AsyncIterator[AttemptOwnerContext]: ...

    async def append_attempt_event(
        self,
        *,
        owner_context: AttemptOwnerContext,
        draft: RunEventDraft,
    ) -> RunEvent: ...

    async def append_terminal_and_close(
        self,
        *,
        owner_context: AttemptOwnerContext,
        draft: RunEventDraft,
        terminal_state: AttemptState,
        failure_summary: str | None,
    ) -> AttemptTerminalLink: ...

    async def recover_stale_attempts(self, *, run_id: str | None = None) -> tuple[AttemptRecoveryDecision, ...]: ...
```

CAS 规则固定如下：

- acquire 新 attempt：store 在同一 `BEGIN IMMEDIATE` 事务内先插入 `host_fencing_tokens`，取得新的全局
  `fencing_token`，再 `INSERT host_attempts (...) VALUES (... attempt_id=?, state='running',
  owner_token_hash=?, fencing_token=?, ...)`；`UNIQUE(run_id, attempt_index)` 冲突转
  `AttemptLeaseResult(decision=BUSY)`，不 fallback 到复用旧 attempt。若后续 insert attempt 失败，
  已分配的 fencing token 可以形成 gap；fencing token 只要求全局单调，不要求连续。
- renew：`UPDATE host_attempts SET lease_expires_at=?, lease_renewed_at=? WHERE attempt_id=? AND state='running' AND owner_token_hash=? AND fencing_token=? AND lease_expires_at > now`；`rowcount == 0` 转 `AttemptLeaseResult(decision=FENCED, reason=OWNER_MISMATCH | LEASE_EXPIRED | FENCING_TOKEN_MISMATCH | ATTEMPT_TERMINAL)`。
- verify owner：同 renew 的 `WHERE` 条件，但不更新字段；`rowcount == 0` 或查不到有效行必须抛 `AttemptFencingError`。
- terminal close：同事务先 verify owner，再 append terminal event，再 `UPDATE host_attempts SET state=?, finished_at=?, terminal_event_position=?, failure_summary=? WHERE attempt_id=? AND state='running' AND owner_token_hash=? AND fencing_token=? AND lease_expires_at > now`；`rowcount == 0` 整个事务回滚并抛 `AttemptFencingError`。
- mark recovering：`UPDATE host_attempts SET state='recovering', finished_at=?, stale_marked_at=?, failure_summary=? WHERE attempt_id=? AND state='running' AND fencing_token=? AND lease_expires_at <= now`；`rowcount == 1` 后在同一事务分配新的全局 fencing token 并插入新 recovery attempt。`rowcount == 0` 转 `AttemptRecoveryDecision(action=NOOP_TERMINAL | MARK_LOST)`，由当前行状态决定。

## 7. Fenced EventLog Append 与 ToolRuntime 覆盖

### 7.1 Attempt-scoped 写入范围

必须由 owner fencing 保护的写入：

- `host_attempts` owner / lease acquire、renew、terminal close、stale / recovering / lost 标记。
- attempt-scoped state update：`RUNNING`、正常 terminal attempt state、`STALE`、`RECOVERING`、`LOST`。
- 由当前 attempt 产生的 Engine-sourced canonical RunEvent append。
- Host-owned attempt-scoped facts：context overflow observed、compact requested/completed/failed、context attempt retrying、P7 run input context snapshot built。
- ToolRuntime Host-owned canonical facts：`TOOL_RESULT_TRUNCATED`、`TOOL_CURSOR_ISSUED`、`TOOL_FETCH_MORE_REQUESTED`、`TOOL_FETCH_MORE_COMPLETED`、`TOOL_FETCH_MORE_FAILED`、`TOOL_CURSOR_EXPIRED`、`TOOL_CURSOR_DENIED`。
- terminal attempt close 对 `terminal_event_position` 的写入。

仍属于 P6 durable facts、不被 attempt owner 语义改变的写入：

- EventLog per-run cursor allocation、global event position allocation、terminal guard。
- `host_runs` 最小 terminal state 与 terminal result snapshot 的同事务更新。
- `host_projection_checkpoints` checkpoint advance / retry / blocked 状态。
- tool trace JSONL best-effort sink 写入；它由 EventLog replay 幂等派生，不持有 attempt 执行权。

### 7.2 AttemptScopedRunEventAppender

P8 固定新增 attempt-scoped append port：

```python
@dataclass(frozen=True, slots=True)
class AttemptScopedRunEventAppender:
    storage: HostStorage
    event_store: DurableRunEventStore
    lease_store: AttemptLeaseStore
    owner_context: AttemptOwnerContext

    async def append(self, draft: RunEventDraft) -> RunEvent: ...

    def append_in_transaction(
        self,
        *,
        tx: HostStorageTransaction,
        draft: RunEventDraft,
    ) -> RunEvent: ...

    async def append_terminal_and_close(
        self,
        *,
        draft: RunEventDraft,
        terminal_state: AttemptState,
        failure_summary: str | None,
    ) -> AttemptTerminalLink: ...
```

实现要求：

- `draft.run_id` 必须等于 `owner_context.run_id`，否则抛 `AttemptFencingError(reason=OWNER_MISMATCH)`。
- 每次 append 在同一个 `BEGIN IMMEDIATE` 事务内执行 `lease_store.verify_owner(...)` 与 `event_store.append_with_position_in_transaction(...)`；非 terminal append 可以忽略返回的 `event_position`。
- fenced late write 不写 diagnostic RunEvent，只返回 typed refusal 并记录 masked 日志。
- Run 已 terminal 时仍由 P6 terminal guard 拒绝；若 owner 失效且 Run 未 terminal，fencing 是第一防线。

### 7.3 ToolRuntime owner context 注入

P8 不修改 `dayu.contracts.tool_call.ToolExecutionContext`，避免把 Host owner token 泄漏到 Engine / contracts 层。owner context 通过 Host internal append port 进入 ToolRuntime：

- `_tool_runtime.py` 新增 `ToolRuntimeEventAppender` 协议，签名为 `async def append(self, draft: RunEventDraft) -> RunEvent`。
- 非 durable / 测试路径使用 `PlainRunEventAppender(event_store=RunEventStore)`，保持 P1-P7 语义。
- durable active attempt 路径由 `AttemptSupervisor` 为当前 attempt 构造 `AttemptScopedRunEventAppender`，并通过 `ToolRuntimeOwnerScope` 注入 `InMemoryToolRuntime` 当前 async 执行上下文。
- `InMemoryToolRuntime` 的所有 `_append_*` helper 不再直接调用 `self.event_store.append(...)`，统一调用 `_append_tool_fact(draft)`，该 helper 从当前 scope 取 `AttemptScopedRunEventAppender`；没有 scope 时只允许非 durable plain appender。
- `ToolRuntimeOwnerScope` 必须是强类型 context manager，退出时恢复旧 appender，异常路径不能泄露 owner token 或污染并发 run。
- framework `fetch_more` 使用发起 `fetch_more` 的当前 attempt owner。它不得复用原始业务工具调用创建 cursor 时的旧 owner；cursor record 只提供 run/session/tool binding，写入 facts 的授权来自当前 active attempt scope。

ToolRuntime append call site 覆盖表：

| 当前 call site | RunEventType | P8 owner 来源 | 断言 |
| --- | --- | --- | --- |
| `_append_tool_result_truncated` | `TOOL_RESULT_TRUNCATED` | 当前工具调用 attempt scope | 旧 owner lease 过期后拒绝写入 |
| `_append_cursor_issued` | `TOOL_CURSOR_ISSUED` | 当前工具调用或 fetch_more attempt scope | cursor 可创建但 fact 必须由合法 owner 写入；fact 失败时整体失败收口 |
| `_append_fetch_requested` | `TOOL_FETCH_MORE_REQUESTED` | 发起 fetch_more 的当前 attempt scope | 不使用原始 cursor owner |
| `_append_fetch_completed` | `TOOL_FETCH_MORE_COMPLETED` | 发起 fetch_more 的当前 attempt scope | completed 与 next cursor issued 都用同一当前 owner |
| `_fetch_failure` | `TOOL_FETCH_MORE_FAILED` | 发起 fetch_more 的当前 attempt scope | denied / expired 失败 fact 也受 fencing |
| `_append_cursor_expired` | `TOOL_CURSOR_EXPIRED` | 触发过期检测的当前 attempt scope | 旧 owner 不能在过期后写 expired fact |
| `_append_cursor_denied` | `TOOL_CURSOR_DENIED` | 触发拒绝检测的当前 attempt scope | scope mismatch fact 受 fencing |

## 8. Terminal Event Position 原子边界

P8 固定 API：`AttemptSupervisor.append_terminal_and_close(...) -> AttemptTerminalLink`。

该方法必须在一个 `async with storage.transaction()` / `BEGIN IMMEDIATE` 中完成：

1. 校验 `owner_context` 与 `draft.run_id`。
2. `lease_store.verify_owner(tx=tx, owner_context=owner_context)`。
3. `DurableRunEventStore.append_with_position_in_transaction(tx=tx, draft=draft) -> AppendedRunEvent`。该 public internal 返回类型包含 `event: RunEvent` 与 `event_position: GlobalEventPosition`。
4. `AttemptLeaseStore.close_terminal(tx=tx, owner_context=owner_context, state=terminal_state, terminal_event_position=appended.event_position, failure_summary=failure_summary)`。
5. 返回 `AttemptTerminalLink`。

不允许的实现：

- terminal event append 后另起事务更新 `host_attempts.terminal_event_position`。
- 用 `MAX(event_position)` 或按 run 查询最后事件来猜 terminal position。
- 先完成 terminal close，再在后续 slice 补 position。

## 9. Lease Renew / Heartbeat 运行机制

P8 固定 lease 生命周期：

```text
acquire new attempt
  -> start renew loop
  -> run engine / tool runtime under AttemptScopedRunEventAppender
  -> append_terminal_and_close or diagnostic close
  -> stop renew loop
```

实现要求：

- TTL 与 renew interval 由 Host durable harness / Host bootstrap 装配层通过 `AttemptLeaseConfig` 注入；
  `_attempt_lease.py` 只提供默认配置值，业务调用方和 public `start_run` 不能逐次传 TTL。
- `AttemptSupervisor.lease_context(...)` 是 async context manager。进入时 acquire 并启动 renew loop；退出时停止 renew loop。正常 terminal 由 `append_terminal_and_close` 完成；异常退出未 terminal 时按当前原因写 `FAILED` 或 `STALE` 诊断收口，但仍必须经过 owner fencing。
- renew loop 使用可注入 `UtcClock` 计算 UTC；测试用 fake clock 驱动，不依赖真实 sleep。
- renew `rowcount == 0`、发现 lease expired、owner mismatch 或 fencing token mismatch 时，返回 typed `AttemptLeaseResult(decision=FENCED, reason=...)`，supervisor 必须停止后续 append，通知 harness 取消 / 收口当前 Engine run，并让当前 attempt 进入 `STALE` 或 `LOST` 诊断语义。
- storage error 不是 fencing。supervisor 应停止 renew loop、停止后续 append，并把 run/attempt 以 Host storage failure 路径收口；如果 storage 已不可写，至少记录安全日志并让后台 task 失败暴露。
- close terminal / diagnostic close 后必须停止 renew loop；renew loop 不得在 terminal 后继续延长 lease。
- owner token 明文只存在于 `AttemptOwnerContext`；异常、日志、result 只输出 `owner_id`、fencing token、masked token。

## 10. Recovery 策略

P8 固定主路径：不 takeover 同一 attempt。

Recovery scan 读取 `state IN ('running', 'created')` 且 `lease_expires_at <= now` 或 owner 字段异常的 attempt。对每个待处理 attempt 在同一 `BEGIN IMMEDIATE` 事务内执行以下策略：

1. 如果 run 已 terminal：将 attempt 标记 `LOST` 或保持已有 terminal，返回 `NOOP_TERMINAL`，不创建 recovery attempt。
2. 如果 attempt 仍是 `RUNNING` 且 lease 已过期：CAS 更新旧 attempt 为 `RECOVERING`，写 `finished_at`、`stale_marked_at`、`failure_summary='lease_expired_recovery_started'`。
3. 同一事务计算 `next_attempt_index = MAX(attempt_index) + 1`，分配新的全局 fencing token，插入新的 recovery attempt，状态为 `RUNNING`，新 `attempt_id`、新 owner token、新 fencing token，并写 `recovered_from_attempt_id=source_attempt_id`。
4. 如果 CAS 失败：根据当前行返回 `NOOP_TERMINAL` 或 `MARK_LOST`，不重试 takeover。

`STALE` 是只标记不立即创建 recovery attempt 的显式诊断 API，供 smoke / 运维收口测试使用；默认 `recover_stale_attempts()` 使用 `RECOVERING + new attempt`。

Recovery 不推进 projection checkpoint，不调用 `startup_reconcile()`，不写 EventLog diagnostic RunEvent。新的 recovery attempt 后续产生的 canonical facts 自带新的 attempt 审计边界；旧 attempt 的审计边界保持关闭。

## 11. Observer / Projection 决策

P8 固定升级 `ObserverSink.process` 为 async 协议，但不实现 observer claim / lease，不升级 observer ownership。

最终协议形态：

```python
class ObserverSink(Protocol):
    @property
    def descriptor(self) -> ObserverDescriptor: ...

    async def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None: ...
```

必须同步迁移的 observer：

- `MemoryProjectionObserver`：删除 `_run_async` thread + new loop bridge，直接 `await memory_store.project_run_events(...)`。
- `TimelineProjectionObserver` / `AuditProjectionObserver`：改为 `async def process(...)`，内部仍可同步写 SQLite。
- `ToolTraceObserver`：改为 `async def process(...)`，保持 JSONL / raw payload 写入语义不变；P8 不把它改成后台 worker。
- tests 中所有 direct `observer.process(...)` 调用必须改为 `await observer.process(...)` 或通过 pytest async 测试执行。

边界：

- `ProjectionCoordinator._run_once_locked` 在同一个 `HostStorage.transaction()` 内 `await observer.process(tx=tx, batch=envelopes)`，然后推进 checkpoint。
- P8 不实现跨进程 observer claim / lease，不实现后台 observer worker，不改变 projection checkpoint schema。
- Observer 消费 EventLog canonical facts，不参与 attempt 执行权仲裁。attempt ownership 与 observer ownership 仍是两个状态机。
- 后台 observer drain / observer claim / projection lag worker 归 #28 或 P15。

选择 async 的原因：

- P6 已通过 `_run_async` 桥接 async memory store，该桥接会创建 thread + event loop，是明确技术债。
- P7 tool trace sink 包含文件 IO；async 协议让后续 best-effort / background drain 演进更自然。
- P8 本身要做多进程 observer drain 验证，先把 observer 协议统一成 async，可避免后续 P8/P15 再大面积改测试和 observer 实现。

验证要求：

- 现有 P6/P7 projection tests 全部迁移到 async process 后仍通过。
- 新增或更新测试覆盖：async observer retry / blocked failure / caught_up / concurrent drain lock / startup_reconcile。
- 确认 `ProjectionCoordinator` 在 await observer 时仍持有同一 storage transaction，sink 写入与 checkpoint advance 仍同事务提交。

## 12. Partial Tool Calls / Projection Failure 边界

P8 不增强 analyzer，也不补造 partial tool call 记录；只固定 owner recovery 与 projection failure 的交互：

- Engine SSE 中途失败造成的 partial tool calls 若只产生 `PROVIDER_PROTOCOL_ERROR` 或未配对 tool events，tool trace observer 可以进入 `BLOCKED_FAILED` 或按 P7 既有规则降级。
- Attempt owner recovery 不得跳过该 blocked checkpoint，不得通过新 attempt 成功而“抹掉”旧 EventLog 中的 projection contract failure。
- 新 recovery attempt 必须写入新的 attempt id / attempt index；tool trace 通过 durable source event positions 与 `recovered_from_attempt_id` 区分旧事件与新事件。
- P8 测试只确认 projection failure 与 fencing error 类型不同；不能把 analyzer duplicate / partial semantics enhancement 混入 P8。

## 13. 文件 / 模块 Ownership

允许新增：

- `dayu/host/_attempt_lease.py`：Attempt lease / fencing 内部契约、owner token、typed decision、error、UTC clock、常量。
- `dayu/host/_attempt_supervisor.py`：Attempt acquire / renew / close / recover orchestration、AttemptScopedRunEventAppender。
- `tests/host/test_phase8_attempt_lease_store.py`
- `tests/host/test_phase8_attempt_supervisor.py`
- `tests/host/test_phase8_attempt_fencing.py`
- `tests/host/test_phase8_tool_runtime_fencing.py`
- `tests/host/test_phase8_attempt_recovery.py`
- `tests/host/test_phase8_multiprocess_stress.py`
- `tests/host/_multiprocess_platform.py` 或同等私有测试 helper：封装 P8 multiprocessing 测试平台差异。
- `utils/smoke_host_p8_attempt_lease.py`

允许修改：

- `dayu/host/_internal_contracts.py`：扩展 `AttemptState` 与 `AttemptRecord` 字段。
- `dayu/host/_durable_event_store.py`：schema 扩展、`AppendedRunEvent` public internal 返回类型、`append_with_position_in_transaction`。
- `dayu/host/_run_state_store.py`：`host_attempts` owner / lease 字段、CAS acquire / renew / close / recover 查询。
- `dayu/host/_host_storage_transaction.py`：仅当需要可注入 UTC clock 类型或事务内 now helper；不得引入业务语义。
- `dayu/host/_run_harness.py`：薄委托到 AttemptSupervisor；接入 owner context、renew lifecycle、attempt-scoped append port。
- `dayu/host/_durable_harness.py`：装配 AttemptSupervisor / lease store / ToolRuntime append port / smoke 所需 internal bundle 字段。
- `dayu/host/_tool_runtime.py`：新增 ToolRuntimeEventAppender / owner scope，把所有 Host-owned tool facts 改为 fenced append port。
- `dayu/host/_event_observer.py` / `_projection_store.py`：升级 `ObserverSink.process` 为 async 协议，`ProjectionCoordinator` await observer；不实现 observer claim / lease。
- `dayu/host/contracts.py` / `_run_event_serializer.py`：P8 不新增 fenced late write diagnostic RunEvent；除非前序测试证明现有 RunEvent data 类型缺口阻塞合法 facts，否则不得改。
- `dayu/host/README.md`、`docs/host/design.md`、`tests/README.md`：代码落地后按文档触发规则同步当前事实。

不应修改：

- `dayu/engine/**`：不新增 owner / lease / trace / recovery 语义。
- `dayu/service/**` / `dayu/ui/**`：P8 不改 public lifecycle admission。
- `dayu/runtime/**`：P8 不实现 lane，不把 Host ownership 放入 runtime。
- `utils/analyze_tool_trace_host.py`：不做 analyzer enhancement。

## 14. Gateflow Implementation Slices

### P8-S0：计划复审与基线固定

- 目标：修复 plan review findings，把 P8 固定为 handoff-ready 计划。
- 预期可见 / 契约结果：`docs/host/phase8-plan.md` 不再留下 recovery、observer、schema、ToolRuntime、terminal 事务、stress 策略的关键 open question；`docs/host/phase8-plan-review.md` finding 标题标注修复状态。
- 文件 ownership：`docs/host/phase8-plan.md`、`docs/host/phase8-plan-review.md`、必要时 `docs/host/migration-plan.md`。
- 允许修改：仅文档。
- 非目标：不写生产代码、不新增测试、不提交。
- 前置依赖：当前 review 文档。
- 测试 / 验证命令：文档 slice 不运行 pytest；如总控要求环境基线，可运行 `source .venv/bin/activate && python -m pyright`。
- 完成信号：F1-F6 均在 plan 中有确定决策，review 文档标题标注 `[已修复]`。
- 停止条件：用户要求改变 P8 主路径，或发现代码事实与 plan 决策冲突到需要重新讨论架构。
- 上下文压力：低。

### P8-S1：契约、Schema 与 CAS Store

- 目标：新增 `_attempt_lease.py` 强类型契约，扩展 `host_attempts` schema 与 `AttemptStateStore` / `AttemptLeaseStore` 的 CAS acquire / renew / verify 基础。
- 预期可见 / 契约结果：单进程内可以创建新 attempt owner、renew、验证 owner、识别 busy / fenced / terminal；不接入 harness 主路径。
- 文件 ownership：`_attempt_lease.py`、`_internal_contracts.py`、`_run_state_store.py`、`_durable_event_store.py` schema、`tests/host/test_phase8_attempt_lease_store.py`。
- 允许修改：新增 dataclass / enum / typed error / fake clock；扩展 schema 与 row mapper；实现 acquire / renew / verify CAS；补 store 级测试。
- 非目标：不改 `_run_harness.py` 主执行路径；不做 terminal event position；不做 recovery；不改 ToolRuntime；不改 observer 协议。
- 前置依赖：P8-S0。
- 测试 / 验证命令：
  - `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_lease_store.py`
  - `source .venv/bin/activate && pytest tests/host/test_phase6_run_state_store.py tests/host/test_phase6_durable_event_store.py`
  - `source .venv/bin/activate && python -m pyright`
- 完成信号：acquire / renew / expiry / owner mismatch / fencing token mismatch / terminal row 的 typed result 测试通过；全局 fencing token 单调递增且允许 gap；旧 P6 store 测试通过。
- 停止条件：需要旧库兼容迁移；无法避免 `Any` / `object`；schema 需要新增 `host_attempt_leases` 表；rowcount=0 不能映射成 typed reason。
- 上下文压力：中。

### P8-S2：Async ObserverSink 协议迁移

- 目标：把 `ObserverSink.process` 升级为 async 协议，删除 memory observer 的 `_run_async` bridge，并迁移 memory / timeline / audit / tool trace observer 与 projection tests。
- 预期可见 / 契约结果：`ProjectionCoordinator` 在同一 storage transaction 内 `await observer.process(...)` 后推进 checkpoint；observer retry / blocked / caught_up / startup_reconcile 语义不变。
- 文件 ownership：`_event_observer.py`、`_memory_projection.py`、`_timeline_projection.py`、`_audit_projection.py`、`_tool_trace_projection.py`、`tests/host/test_phase6_projection_checkpoint.py`、`tests/host/test_phase6_review_fixes.py`、`tests/host/test_phase6_timeline_audit_projection.py`、`tests/host/test_phase7_tool_trace_projection.py`。
- 允许修改：`ObserverSink` Protocol、所有 observer `process` 方法、`ProjectionCoordinator` 调用点、相关 async tests。
- 非目标：不实现 observer claim / lease；不实现后台 observer worker；不改变 projection checkpoint schema；不改 attempt lease / ToolRuntime。
- 前置依赖：P8-S1。
- 测试 / 验证命令：
  - `source .venv/bin/activate && pytest tests/host/test_phase6_projection_checkpoint.py tests/host/test_phase6_review_fixes.py tests/host/test_phase6_timeline_audit_projection.py tests/host/test_phase7_tool_trace_projection.py`
  - `source .venv/bin/activate && python -m pyright`
- 完成信号：所有 observer 实现均为 `async def process`；`_run_async` helper 删除；projection checkpoint / retry / blocked / startup_reconcile 测试通过；tool trace projection tests 改为 await 后通过。
- 停止条件：需要引入 observer claim / lease；无法保持 sink 写入与 checkpoint 同事务；需要把 observer IO 移到后台队列。
- 上下文压力：中高。

### P8-S3：AttemptSupervisor Lease Context 与 Renew Loop

- 目标：实现 `AttemptSupervisor.lease_context(...)`、renew heartbeat、diagnostic close 基础，并让 harness 可以获得当前 `AttemptOwnerContext`；本 slice 不处理 terminal event position。
- 预期可见 / 契约结果：durable harness 启动 attempt 时 acquire owner、运行期间 renew、close / 异常时停止 renew；renew 失败后阻止后续 append 并取消 / 收口当前 engine run。
- 文件 ownership：`_attempt_supervisor.py`、`_run_harness.py`、`_durable_harness.py`、`tests/host/test_phase8_attempt_supervisor.py`。
- 允许修改：新增 supervisor、renew task lifecycle、masked logging；`LocalRunHarness` 只薄委托，不写 SQL。
- 非目标：不实现 terminal event append + close；不实现 recovery scan；不改 ToolRuntime facts；不做 multiprocessing。
- 前置依赖：P8-S1。
- 测试 / 验证命令：
  - `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_supervisor.py`
  - `source .venv/bin/activate && pytest tests/host/test_phase6_durable_harness_integration.py`
  - `source .venv/bin/activate && python -m pyright`
- 完成信号：运行中 renew、renew rowcount=0 后停止 append、close 停 renew、异常不泄露 token 的测试通过。
- 停止条件：需要把 owner token 暴露到 public API；`LocalRunHarness` 新增 lease SQL；Engine 需要知道 owner。
- 上下文压力：中高。

### P8-S4：Terminal Append + Close 原子垂直片

- 目标：实现 `append_with_position_in_transaction` 与 `AttemptSupervisor.append_terminal_and_close(...)`，把 terminal event append、owner fencing、attempt terminal close、`terminal_event_position` 写入固定在同一事务。
- 预期可见 / 契约结果：每个正常 terminal attempt 可查询到非空 `terminal_event_position`，且等于 terminal RunEvent global position；旧 owner terminal close 被 typed fencing 拒绝；新 recovery attempt 终结时同步更新 run terminal state / terminal result，不让旧 `RECOVERING` attempt 的空 `terminal_event_position` 影响 run 级终态真源。
- 文件 ownership：`_durable_event_store.py`、`_attempt_supervisor.py`、`_run_state_store.py`、`_run_harness.py`、`tests/host/test_phase8_attempt_fencing.py`。
- 允许修改：公开 internal `AppendedRunEvent` 或等价强类型返回；替换 terminal path 为 supervisor API；补 terminal race 单进程测试。
- 非目标：不改变 public `RunEventCursor`；不暴露 global position 给普通调用方；不处理 recovery；不做 ToolRuntime。
- 前置依赖：P8-S3。
- 测试 / 验证命令：
  - `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_fencing.py tests/host/test_phase6_durable_event_store.py`
  - `source .venv/bin/activate && python -m pyright`
- 完成信号：测试直接查询 EventLog terminal position 与 AttemptRecord position 相等；P6 terminal guard 仍通过。
- 完成信号补充：测试直接查询 EventLog terminal position 与 AttemptRecord position 相等；P6 terminal guard 仍通过；recovery attempt 成功终结时，`host_runs` 终态、terminal result 与新 attempt terminal event 同源。
- 停止条件：只能通过 `MAX(event_position)` 间接猜测 terminal position；terminal append 与 attempt close 不是同一事务；需要 terminal 后补丁事件。
- 上下文压力：中。

### P8-S5：Attempt-scoped Append 与 ToolRuntime Fencing

- 目标：新增 `AttemptScopedRunEventAppender`，把 Engine-sourced event、context compact facts、run input context snapshot fact、ToolRuntime facts 全部纳入 owner fencing。
- 预期可见 / 契约结果：旧 owner 无法追加任何 attempt-scoped canonical fact；合法 owner 的 truncate / cursor / fetch_more facts 正常写入； framework `fetch_more` 使用发起 fetch_more 的当前 attempt owner。
- 文件 ownership：`_attempt_supervisor.py`、`_durable_event_store.py`、`_run_harness.py`、`_run_input_context_fact.py` 调用点、`_tool_runtime.py`、`_durable_harness.py`、`tests/host/test_phase8_attempt_fencing.py`、`tests/host/test_phase8_tool_runtime_fencing.py`。
- 允许修改：新增 append port / ToolRuntimeEventAppender / ToolRuntimeOwnerScope；把所有 direct `event_store.append` call site 改为 scoped helper；补 typed fencing tests。
- 非目标：不改变 observer sink；不处理 recovery；不做 P9 cancel；不新增 fenced late write diagnostic RunEvent。
- 前置依赖：P8-S4。
- 测试 / 验证命令：
  - `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_tool_runtime_fencing.py`
  - `source .venv/bin/activate && pytest tests/host/test_phase4_overflow_retry.py tests/host/test_phase7_tool_trace_eventlog_source.py tests/host/test_phase7_tool_trace_projection.py`
  - `source .venv/bin/activate && python -m pyright`
- 完成信号：late owner 对 Engine event、context facts、run input context fact、ToolRuntime truncate / cursor / fetch_more facts 均被拒绝；合法 owner 回归测试通过。
- 停止条件：需要把显式 owner token 放进 extra payload；ToolRuntime owner context 泄漏到 `dayu.contracts`；fencing check 与 append 不在同一事务。
- 上下文压力：高。

### P8-S6：Stale / Orphan Recovery 新 Attempt 主路径

- 目标：实现 `recover_stale_attempts(...)`，对过期 / orphan attempt 先 CAS 标记旧 attempt 为 `RECOVERING` / `STALE` / `LOST`，再创建新 recovery attempt，记录 `recovered_from_attempt_id`。
- 预期可见 / 契约结果：进程崩溃后新进程能识别过期 attempt；默认创建新的 recovery attempt；旧 owner late write 被 fencing；不会 takeover 同一 attempt。
- 文件 ownership：`_attempt_supervisor.py`、`_run_state_store.py`、`_durable_harness.py`、`tests/host/test_phase8_attempt_recovery.py`。
- 允许修改：新增 recovery scan 查询、CAS mark recovering + insert recovery attempt、bundle explicit `recover_stale_attempts()`；补恢复测试。
- 非目标：不把 P6 `startup_reconcile` 自动并入 Host bootstrap；P9 才收进生产 Host 启动流程。P8 只提供 internal 显式入口和 smoke。
- 前置依赖：P8-S5。
- 测试 / 验证命令：
  - `source .venv/bin/activate && pytest tests/host/test_phase8_attempt_recovery.py`
  - `source .venv/bin/activate && pytest tests/host/test_phase6_review_fixes.py`
  - `source .venv/bin/activate && python -m pyright`
- 完成信号：recovering + new attempt、recovered_from_attempt_id、mark stale、mark lost、old owner fenced、projection checkpoint 不被 recovery scan 修改的测试通过。
- 停止条件：实现需要完整 Session / Run admission；recovery 逻辑必须读 UI / Service 状态；恢复尝试复用同一 attempt_id。
- 上下文压力：高。

### P8-S7：Deterministic Multiprocessing 与 Observer Drain 验证

- 目标：新增默认可运行的 deterministic multiprocessing 测试，覆盖跨进程 append、terminal race、stale recovery、observer drain；确认 P8 不需要 observer claim / lease。
- 预期可见 / 契约结果：文件 SQLite 上多进程并发不产生重复 cursor / global position；terminal race 只有一个 winner；旧 owner fenced；startup_reconcile 可在新进程追平 observer。
- 文件 ownership：`tests/host/test_phase8_multiprocess_stress.py`、`tests/host/_multiprocess_platform.py` 或同等私有测试 helper；仅在测试暴露真实 race 时回修前序模块。
- 允许修改：测试 helper、spawn-safe worker、短超时常量；封装 start method、join timeout、terminate / kill、exitcode 断言、文件 SQLite path、跨进程 result collection；必要 bug fix 限于 P8 模块。
- 非目标：不把重压 stress 放进默认 pytest；不依赖外部服务；不打印 token；不实现 observer claim。
- 前置依赖：P8-S6。
- 测试 / 验证命令：
  - `source .venv/bin/activate && pytest tests/host/test_phase8_multiprocess_stress.py`
  - `source .venv/bin/activate && python -m pyright`
- 完成信号：基础 multiprocessing 测试稳定通过；测试文件包含 append / terminal race / recovery / observer drain 四类场景；平台差异集中在测试 helper，测试主体不散落 `multiprocessing.set_start_method`、裸 `join(timeout)` 或重复进程清理逻辑。
- 停止条件：测试只能覆盖 `:memory:`；必须靠未命名 sleep 魔法数字才能稳定；多进程失败根因未定位；实现开始引入 observer claim；为了测试方便把 process launcher 提升为 Host 生产 API。
- 上下文压力：中高。

### P8-S8：Durable Conversation Memory Store / Read Model Rebuild

- 目标：
  - 在 P8-S7 多进程 owner / fencing / recovery 验证之上，补齐 durable conversation memory
    read model recovery 能力，关闭“projection checkpoint 已 caught up，但进程重启后 in-memory
    memory 丢失，`startup_reconcile()` 因 checkpoint 已推进而不再 replay 已处理 EventLog，
    导致 session memory snapshot 永久丢失”这条数据丢失通道。
  - `build_durable_harness` 默认装配路径不得再依赖 production
    `InMemoryConversationMemoryStore`；durable harness 默认 memory read model 必须具备
    durable recovery 语义。
  - 落地 durable conversation memory read model 或 checkpoint-aware rebuild 机制（例如
    durable memory projection store，或 startup-time 基于已处理 RunEvent 范围按
    `session_id` 重建 in-memory snapshot），由本 slice 计划阶段在两条路径中固定一条；
    无论选哪条，都必须保证 in-memory snapshot 丢失后 Host internal 路径能自行恢复，
    不要求 UI / Service 调用方触发 reload。
- 顺手必须删除：
  - production `InMemoryConversationMemoryStore` 实现（`dayu/host/_conversation_memory.py`
    中的 `InMemoryConversationMemoryStore` 类、模块 `__all__` 中对应导出、
    `dayu.host` package 任何 re-export）。
  - 依赖 production `InMemoryConversationMemoryStore` 的测试用例。若个别测试仍需
    memory store fake，必须迁移为 `tests/host/` 私有 fake / test helper（例如
    `tests/host/_memory_store_fake.py`）；禁止保留 production InMemory 实现来迁就旧测试。
- 预期可见 / 契约结果：
  - 文件 SQLite + 重新装配（同进程 rebuild 或新进程重启）场景下，EventLog 已包含
    某 session 的 terminal run，`host_projection_checkpoints` 已 caught up，新 memory
    read model 初始为空，仍能由 Host internal durable / rebuild 路径恢复出该 session
    的 memory snapshot（recent_raw_turns / older_raw_turns / tool_facts /
    evidence_anchors 等关键字段语义不丢）。
  - `build_durable_harness` 默认 memory read model 在不传 `memory_store` 时具备 durable
    recovery 语义；不再依赖 production `InMemoryConversationMemoryStore`。
  - production `InMemoryConversationMemoryStore` 与对应测试已删除；保留下来的 memory
    fake 仅存在于 `tests/host/` 私有 helper 中。
  - `dayu/host/README.md` 明确写出 durable memory 当前事实，不再暗示 in-memory store 可
    用于生产 durable path。
- 文件 ownership：
  - `dayu/host/_conversation_memory.py`：删除 production InMemory 实现、收敛 protocol
    与 helper；保留 `ConversationMemoryStore` Protocol、snapshot dataclass、projection
    helper、constants。
  - 新增 durable memory read model 实现文件（命名由计划阶段固定，例如
    `dayu/host/_conversation_memory_durable.py` 或在已有 projection 模块内扩展），
    具体路径在本 slice 计划阶段写死。
  - `dayu/host/_durable_harness.py`：`build_durable_harness` 默认装配 durable memory
    read model；`memory_store` 参数仍允许覆盖，但默认不再实例化 production InMemory。
  - `dayu/host/_memory_projection.py` 等 observer 文件：按 durable read model 决策同步。
  - `tests/host/`：删除依赖 production InMemory 的测试用例，迁移必要 fake 到私有 helper，
    新增 durable memory recovery 测试（覆盖 caught-up checkpoint + 空 memory + 重建场景）。
  - `dayu/host/README.md`、必要时 `tests/README.md`：按文档触发规则同步当前事实。
- 允许修改：
  - 删除 production `InMemoryConversationMemoryStore`、对应 `__all__` 导出与 package
    re-export。
  - 新增 / 调整 durable memory read model 实现与装配。
  - 新增 / 调整 durable memory recovery 测试与私有 fake helper。
  - 同步 README 中与 memory store 当前事实不一致的部分。
- 非目标：
  - 不实现 P9 Session / Run admission、`client_request_id` 幂等或 active Run 仲裁。
  - 不固定 public memory edit / reset / forget API；那是 issue #24 / 后续 phase 范围。
  - 不迁移业务 memory（财报实体 / 跨 session / project / user memory）。
  - 不让 UI / Service 参与 memory recovery；recovery 必须是 Host 内部治理能力。
  - 不把 memory durable read model 升级成完整 long-term memory store。
- 前置依赖：P8-S7。
- 测试 / 验证命令：
  - `source .venv/bin/activate && pytest tests/host/test_phase8_durable_memory_recovery.py`
    （具体测试文件名由本 slice 计划阶段固定）
  - `source .venv/bin/activate && pytest tests/host/test_phase6_durable_harness_integration.py tests/host/test_phase7_durable_harness_config.py`
  - `source .venv/bin/activate && pytest tests/host/test_phase3_conversation_memory*.py tests/host/test_phase6_memory_projection*.py`
    （按当前测试树实际命中文件调整；目标是覆盖原依赖 production InMemory 的测试已迁移
    或删除）
  - `source .venv/bin/activate && python -m pyright`
- 完成信号：
  - durable memory recovery 测试通过：file SQLite + caught-up checkpoint + 空 memory
    场景下 Host internal 路径可恢复 session memory snapshot。
  - `build_durable_harness` 默认路径不再实例化 production `InMemoryConversationMemoryStore`；
    `grep -R "InMemoryConversationMemoryStore" dayu/ utils/` 仅在迁移说明 / 注释中出现，
    不再存在 production 实现导出。
  - `tests/host/` 中所有依赖 production InMemory 的旧测试已删除或迁移到私有 fake；
    pyright 与受影响测试通过。
  - `dayu/host/README.md` 已更新 durable memory 当前事实，删除 “in-memory store 可用于
    durable path” 的措辞。
- 停止条件：
  - durable memory read model 设计需要修改 EventLog schema、projection checkpoint 语义
    或引入 P9 lifecycle admission 才能成立。
  - 必须保留 production `InMemoryConversationMemoryStore` 才能让旧测试通过（违反“顺手
    必须删除”要求）。
  - 需要让 UI / Service 调用方主动触发 memory reload。
  - durable read model 需要把 owner token / scope token / 大块 prompt 写入 memory
    storage 才能正确恢复。
- 上下文压力：高。

### P8-S9：手工 Smoke

- 目标：新增 `utils/smoke_host_p8_attempt_lease.py`，用摘要展示 owner acquire / renew / fence / recovery attempt / terminal_event_position / observer caught up，并补充 durable memory recovery 摘要场景。
- 预期可见 / 契约结果：用户可运行 smoke 直接观察 P8 治理路径；慢硬盘 + Docker Linux 重压版 multiprocessing 由 issue #38 跟踪，可作为后续手工 stress，不进入 P8 默认 pytest；基础测试已在 S7 默认运行；durable memory recovery 已在 S8 默认运行。
- 文件 ownership：`utils/smoke_host_p8_attempt_lease.py`。
- 允许修改：smoke only；必要时复用 P8 私有 multiprocessing platform helper 或添加测试 fixture 风格 fake proxy。
- 非目标：不调用真实 provider；不输出完整 prompt、tool result、scope token、owner token。
- 前置依赖：P8-S8。
- 测试 / 验证命令：
  - `source .venv/bin/activate && python utils/smoke_host_p8_attempt_lease.py`
  - `source .venv/bin/activate && python -m pyright`
- 完成信号：输出包含 acquire/renew/fenced/recovery_attempt/recovered_from/terminal_event_position/observer_caught_up/memory_recovered 摘要，且 token masked。
- 停止条件：smoke 需要真实 API key 或外部服务；输出泄露 token；只能证明 happy path。
- 上下文压力：中。

### P8-S10：文档同步与收口

- 目标：按代码事实更新 `docs/host/design.md`、`dayu/host/README.md`、`tests/README.md` 与实施报告。
- 预期可见 / 契约结果：文档只写 P8 已落地事实，不写 P9/P10 未来能力为当前事实。
- 文件 ownership：`docs/host/design.md`、`dayu/host/README.md`、`tests/README.md`、必要 review 文档。
- 允许修改：文档。
- 非目标：不更新根 README，除非 smoke 使用方式成为项目级用户入口；不更新 `docs/code_review.md`，除非用户确认 P8 代码事实已落地。
- 前置依赖：P8-S9。
- 测试 / 验证命令：
  - `source .venv/bin/activate && python -m pyright`
  - 受影响 pytest 汇总命令见第 16 节。
- 完成信号：README 触发判断记录完整；phase implementation report 填完；observer async / no claim 决策写入设计文档当前事实；durable conversation memory recovery 当前事实写入 `dayu/host/README.md`，production `InMemoryConversationMemoryStore` 旧术语已从 README / design 全量清理。
- 停止条件：文档需要描述未落地 P9 lifecycle；术语新旧混用；把 observer claim 写成 P8 已落地事实，或把 observer async 升级写漏；保留 production `InMemoryConversationMemoryStore` 描述为当前事实。
- 上下文压力：低。

并行规则：默认串行。只有 P8-S9 smoke 与 P8-S10 文档草稿可在 P8-S8 通过后并行起草；不得与 P8-S1 至 P8-S8 并行，因为它们共享 attempt / durable / ToolRuntime / observer / conversation memory read model 契约边界。

## 15. P8 手工 Smoke 设计

新增 `utils/smoke_host_p8_attempt_lease.py`：

- 使用临时目录文件 SQLite，不使用 `:memory:`，确保跨进程可见。
- 构造 deterministic fake worker / proxy，不调用真实 provider。
- 场景 1：owner A acquire + renew，输出 `owner_acquired=true owner=***abcd fencing_token=<int> renewed=true`。
- 场景 2：owner B 在 lease 未过期时 acquire 被拒绝，输出 `busy=true`。
- 场景 3：lease 过期后 recovery scan 标记 owner A attempt 为 `recovering`，创建 owner B recovery attempt，输出 `recovered_from=<attempt-a> recovery_attempt=<attempt-b>`。
- 场景 4：owner A late append / ToolRuntime truncate fact 被 fenced，输出 `late_write=fenced reason=LEASE_EXPIRED`。
- 场景 5：owner B 写 terminal event 并 close attempt，输出 `terminal_event_position=<int> attempt_state=succeeded`。
- 场景 6：模拟 terminal 后未 drain，重新装配后 `startup_reconcile` 追平 observer，输出 `observer_caught_up=true`。
- 场景 7：terminal run 已落库且 projection checkpoint 已 caught up 后，丢弃 in-memory memory read model 并重新装配 durable harness，输出 `memory_recovered=true session=<masked>`，证明 durable memory recovery 路径生效，不依赖 production `InMemoryConversationMemoryStore`。

输出约束：

- 不打印完整 owner token、scope token、cursor token、prompt、tool result、provider raw payload。
- 不刷屏；摘要行控制在 20 行以内。
- 失败时抛明确异常并打印最后一个安全摘要。

## 16. 测试计划与验证命令

单元 / 集成测试：

- `tests/host/test_phase8_attempt_lease_store.py`
  - acquire / renew / expiry / owner mismatch / fencing token mismatch / terminal refusal。
  - 全局 fencing token 单调递增，失败事务可留下 gap，但不得倒退或复用。
  - owner token hash / masked logging。
  - CAS `rowcount == 0` 转 typed decision / error。
- `tests/host/test_phase8_attempt_supervisor.py`
  - lease context acquire -> renew loop -> close。
  - renew 失败停止后续 append。
  - close 停 renew。
  - 异常路径不泄露 token。
- `tests/host/test_phase8_attempt_fencing.py`
  - late owner update 被拒绝。
  - attempt-scoped EventLog append fencing。
  - terminal_event_position 与 EventLog position 同事务同源。
- `tests/host/test_phase8_tool_runtime_fencing.py`
  - 旧 owner lease 过期后 ToolRuntime append 被拒。
  - 合法 owner truncate / cursor issued / fetch_more requested / completed / failed / expired / denied facts 正常写入。
  - framework `fetch_more` 使用当前 attempt owner，不复用原始 cursor owner。
- `tests/host/test_phase8_attempt_recovery.py`
  - stale scan、mark recovering + create recovery attempt、mark stale、mark lost。
  - recovery attempt 使用新 attempt_id / attempt_index，并记录 `recovered_from_attempt_id`。
  - recovery 不推进 projection checkpoint。
- `tests/host/test_phase8_multiprocess_stress.py`
  - 默认 deterministic 跨进程 append。
  - terminal race。
  - stale recovery。
  - observer drain / recovery。
- `tests/host/test_phase8_durable_memory_recovery.py`
  - 文件 SQLite + caught-up checkpoint + 空 memory read model 重建：Host internal 路径
    可恢复 session memory snapshot（recent / older raw turns、tool facts、evidence
    anchors）。
  - `build_durable_harness` 默认装配不再依赖 production `InMemoryConversationMemoryStore`。
  - 旧依赖 production InMemory 的测试已删除或迁移到 `tests/host/` 私有 fake helper。

回归测试：

```bash
source .venv/bin/activate
pytest tests/host/test_phase6_durable_event_store.py \
  tests/host/test_phase6_run_state_store.py \
  tests/host/test_phase6_durable_harness_integration.py \
  tests/host/test_phase6_review_fixes.py \
  tests/host/test_phase7_tool_trace_eventlog_source.py \
  tests/host/test_phase7_tool_trace_projection.py \
  tests/host/test_phase7_durable_harness_config.py
```

P8 专项测试：

```bash
source .venv/bin/activate
pytest tests/host/test_phase8_attempt_lease_store.py \
  tests/host/test_phase8_attempt_supervisor.py \
  tests/host/test_phase8_attempt_fencing.py \
  tests/host/test_phase8_tool_runtime_fencing.py \
  tests/host/test_phase8_attempt_recovery.py \
  tests/host/test_phase8_multiprocess_stress.py \
  tests/host/test_phase8_durable_memory_recovery.py
```

Smoke 与类型检查：

```bash
source .venv/bin/activate
python utils/smoke_host_p8_attempt_lease.py
python -m pyright
```

若 multiprocessing 测试在 CI 环境有资源波动，实施 Agent 必须先缩小并发规模或隔离临时数据库路径；不得用 skip 掩盖真实 race。慢硬盘 + Docker Linux 重压版 stress 由 issue #38 跟踪，不进入 P8 默认 pytest；基础跨进程 append / terminal race / stale recovery / observer drain 必须默认可运行。

## 17. README / Docs 触发判断

- `docs/host/design.md`：代码落地后必须更新 P8 后路径，写清 attempt owner lease / fencing / recovery 当前事实、terminal_event_position 关联、ToolRuntime facts fencing、observer async 协议且无 claim 的结论。
- `dayu/host/README.md`：修改 `dayu/host/` 后必须检查并更新，只写已落地的 Host internal attempt lease / recovery，不写 P9 public lifecycle。
- `tests/README.md`：新增 phase8 multiprocessing / smoke 测试后必须更新测试分层和运行方式。
- 根目录 `README.md`：默认不更新；只有当 `utils/smoke_host_p8_attempt_lease.py` 被纳入用户手册常用工作流时才触发。
- `docs/code_review.md`：默认不在 P8 实施 slice 内更新；等用户确认代码事实落地后再按总控规则更新日常 review 当前事实专项。

## 18. Review Gates

Plan gate：

- 常规 plan review：检查目标、非目标、slice 粒度、ownership、测试命令、停止条件是否 handoff-ready。
- 并发专项 plan review：重点检查 SQLite WAL / `BEGIN IMMEDIATE` / CAS / unique constraints / deterministic multiprocessing stress 是否足以证明多进程语义。
- 架构边界 plan review：重点检查 Host / Engine / runtime 分层、`LocalRunHarness` 防 God Object、ToolRuntime owner context 是否不泄漏到 contracts、observer 与 attempt owner 状态机是否混淆。

Code gate：

- Slice-level review：P8-S1 至 P8-S8 每个高风险 slice 后都应做局部 review / fix / rereview，再进入下一 slice。S8 durable memory recovery 必须额外做架构边界 review，确认未把 P9 lifecycle / public memory edit API 偷做进 S8。
- Phase-level 常规 code review：所有 slice 完成后整体审查 bug、状态机、schema、测试、弱类型、兼容代码。
- 并发专项 code review：必须审查真实多进程测试、terminal race、late write fencing、lease expiry clock、busy_timeout 行为。
- 架构边界 code review：必须审查 `LocalRunHarness` 是否只薄委托，Engine 是否未引入 Host governance，`dayu.runtime` 是否未承载 Host 业务语义。
- ToolRuntime 专项 review：必须审查所有 ToolRuntime Host-owned facts 是否走 AttemptScopedRunEventAppender，framework `fetch_more` 是否使用当前 attempt owner。
- OLD / NEW 对比：P8 不需要完整 OLD/NEW 对比；若实施 Agent 借鉴 OLD lease / lane 代码，必须追加专项对比，确认没有把 lane / runtime dependency 作为 Host 私有业务层迁回。

## 19. 可接受与不可接受临时实现

可接受：

- P8 首版可以使用 `_attempt_lease.py` 中的默认 `AttemptLeaseConfig`，但真实运行必须允许 Host 装配层覆盖；
  不得把 TTL / renew interval 写成不可替换的模块常量，也不得让 public 调用方逐次传入。
- recovery policy 先支持默认 `RECOVERING + new attempt`、显式 mark `STALE`、显式 mark `LOST` 的封闭分支，不要求完整 replay。
- observer sink 协议在 P8 升级为 async；observer claim / lease 后移到 #28 或 P15。

不可接受：

- 用进程内 dict / lock 作为 owner 真源。
- owner token 放进 EventLog data 的 extra payload、ToolExecutionContext、public stream 或普通日志。
- 旧 owner late write 只靠 terminal guard 拦截，而不做 owner fencing。
- takeover 同一 attempt 后继续写旧 attempt 审计边界。
- 用 `MAX(event_position)` 猜 terminal position。
- 为保旧测试写兼容 wrapper / re-export。
- 在 `_run_harness.py` 堆 lease SQL、recovery scan、observer claim。
- 将 projection failure、partial tool calls、owner fencing error 混成同一种失败。
- fenced late write 写入 EventLog diagnostic RunEvent。
- P8 引入 observer claim / lease。

## 20. 风险与非阻断残余项

残余风险：

- SQLite time / Python time 若混用，lease expiry 可能 flaky；P8 通过可注入 UTC clock 与装配层
  `AttemptLeaseConfig` 降低风险。
- JSONL tool trace 是文件系统 sink，和 SQLite checkpoint 非原子；P8 不改变该 P7 trade-off，仍依赖 idempotency key 去重。
- async observer 在同一 storage transaction 内 `await observer.process(...)` 会让 observer IO 时间计入
  projection transaction 持有时间；P8 接受该取舍以删除 `_run_async` bridge，并通过默认 deterministic
  observer drain 测试保护正确性。若后续 terminal drain P99 或慢盘 trace sink 成为 SLA 风险，归 #28 /
  P15 的 buffered drain / observer hardening 评估。
- Multiprocessing 测试可能暴露平台差异；必须用文件 DB、spawn-safe helper、短超时和清晰失败输出。
- P8 需要封装测试 / smoke 级多平台操作，避免 macOS / Linux / Docker / 慢盘差异污染业务断言；该封装不等同于生产 Host 进程管理能力。
- `LocalRunHarness` 仍偏大；P8 必须抽出 AttemptSupervisor，但完整 RunSupervisor 拆分留到 P9。
- P8 不治理 observer claim / lease；如果后续需要后台 observer worker 或 claim，归 #28 或 P15。P8 只升级 observer process 调用协议为 async。
- P8 不审计 rejected late write 的 canonical EventLog fact；若生产合规需要 rejected write audit，另设治理 issue，不能由 stale owner 写 canonical fact。

本计划没有留给实施阶段再决策的阻断项。若实施中发现必须改变 recovery 主路径、observer ownership、ToolRuntime owner context 注入方式、terminal 原子事务或 schema 表设计，必须停止并回到总控修 plan。

## 21. 停止条件

任一实施 slice 遇到以下情况必须停止并回到总控修 plan：

- 需要 P9 lifecycle admission 或 public `start_run` 幂等才能继续。
- 需要 RemoteProxy、Outbox、Wait / Resume 或完整 ToolRegistry。
- 必须修改 Engine 才能表达 owner token / lease。
- 需要把 owner token 放入 `dayu.contracts`、RunEvent payload extra 或 public API。
- 需要把 lane 实现为 Host 私有 runtime dependency。
- 需要引入 observer claim / lease 才能让 P8 测试通过。
- 需要引入旧库兼容读取、兼容测试或旧接口 wrapper。
- typed contract 无法避免 `Any` / `object`。
- 多进程测试发现数据竞争但无法用当前 slice 范围修复。

## 22. 实施完成报告格式

每个 slice 完成后，实施 Agent 必须按以下格式汇报：

```text
Slice: P8-Sx <短标题>
改动文件:
- ...

完成结果:
- ...

验证:
- <命令> -> <结果摘要>

契约 / schema / 状态机变化:
- ...

文档同步:
- 已更新 / 未触发，理由...

未覆盖项 / 风险:
- ...

是否触碰后续 slice:
- 否 / 是，说明...

下一步建议:
- ...
```

Phase 收口报告必须额外包含：

- P8 目标是否全部完成，非目标是否未被偷做。
- owner acquire / renew / fencing / recovery / terminal_event_position 的证据。
- ToolRuntime facts fencing 的证据。
- deterministic multiprocessing 测试与 smoke 结果。
- `ObserverSink.process` 已升级为 async、P8 不实现 observer claim / lease 的最终结论与依据。
- README / docs 触发判断。
- 残余风险与后续 owner。
