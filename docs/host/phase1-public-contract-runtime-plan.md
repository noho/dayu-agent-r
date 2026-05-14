# Host Phase 1 公共契约与 runtime 基础设施实施计划

## Plan Status

ready for plan review

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施。

当前 gate 是 phase plan。本计划只定义可交给 implementation agent 执行的 Phase 1 实施边界、公共契约、runtime primitive、测试和文档同步要求；不修改生产代码、不进入 implementation、不做 commit / PR / closeout。

## Goal And Motivation

Phase 1 的目标是建立后续 Host phases 依赖的稳定公共类型、跨进程 runtime 基础设施和 Host construction 的工具输入边界。

真实需求证据：

- `docs/host/implementation-control.md` Phase 1 目标要求建立 Host 后续实现依赖的稳定类型、公共 request / snapshot / enum、`dayu.runtime` 基础能力与外部工具 / 场景装配边界。
- `docs/host/design.md` §11 明确 Host 公共 API 类型放在 `dayu.host` 公共命名空间，Service / UI 可向下 import，Engine 不得 import；后续 command path、read model、stream、retry / replay / resolve_wait 都依赖这些 stable public typing。
- `docs/host/design.md` §3.1 与 `dayu/README.md` Runtime 节明确 `lane` 必须是 cross-process named semaphore / capacity guard，用于单机多客户端 / 多进程下的 runtime capacity，而不是 process-local helper。
- `docs/host/design.md` §3.2 明确 `dayu.runtime.filelock` 是唯一允许直接封装第三方 `filelock.FileLock` 的同步 wrapper，避免 Host / Service / Fins / 工具模块各自手写文件锁。
- `docs/host/design.md` §10.1 与 §18.1 明确业务 `ToolBundle` 是 Host construction / composition root 的显式输入，不得塞进 per-run request 或 metadata；Phase 1 必须稳定 `HostToolingOptions`、`ToolBundleSourceRef`、framework tool reserved name policy view。
- `docs/reviews/gateflow-controller-decision-host-p1-phase-design-20260513.md` 记录 round2 后无 blocking open question，但把 `dayu.host` 初始模块拆分、runtime lane SQLite coordinator、workspace-level runtime DB、busy timeout、heartbeat ownership、TTL cleanup 和 test placement 交给 Phase 1 phase plan 覆盖。

## Non-Goals And Scope Boundary

本 phase 不实现：

- Host durable store / EventLog store / SQLite Host truth schema。
- Host command path、admission、queue promotion、state transition、after-commit wakeup。
- Engine execution path、EngineEvent ingest、WorkerProxy、RemoteProxy / RemoteStub。
- ToolRuntime policy resolution、framework tool injection、TruncationManager、`fetch_more` 执行逻辑、完整 `ToolGovernancePolicyView`。
- ToolsDiscovery / ScenePrepare 具体实现、adapter、manifest schema、provider 注册生命周期。
- 业务工具扫描、财报工具清单、财报 prompt / scene manifest。
- 多 scene tool profile、profile registry、Attempt tool snapshot durability。
- lane 的 Host dispatch 接入、Host cancel 与 lane cancel 的组合使用。
- lane 的 FIFO / fairness / priority / distributed multi-machine capacity / lease / fencing / Attempt owner / EventLog ordering / admission / recovery proof。
- filelock 的 async wrapper、stale lock takeover、强制 break lock、reentrant guarantee。

若 implementation agent 发现必须修改 Engine、Fins 业务工具、Host durable store 或 ToolRuntime 才能完成当前 slice，必须停止并交回 controller。

## Affected Files And Modules

### 允许修改的生产文件 / 配置

- 新建 `dayu/host/__init__.py`
- 新建 `dayu/host/api.py`
- 新建 `dayu/host/tooling.py`
- 新建 `dayu/runtime/lane.py`
- 新建 `dayu/runtime/filelock.py`
- 修改 `pyproject.toml`：把 `filelock` 加入生产依赖，版本下界以当前 constraints 中已有 `filelock==3.28.0` 为参考，建议 `filelock>=3.18.0` 或更高稳定下界；不得只依赖 transitive dependency。
- 最小修改 `dayu/runtime/__init__.py` docstring，说明 Phase 1 新增的层中立 lane / filelock runtime 能力；不得从包根 re-export `lane` / `filelock` 符号。

### 允许修改的测试文件

- 新建 `tests/host/__init__.py`
- 新建 `tests/host/test_package_exports.py`
- 新建 `tests/host/test_public_contracts.py`
- 新建 `tests/host/test_tooling_options.py`
- 新建 `tests/host/test_import_boundary.py`
- 新建 `tests/host/test_weak_typing_guard.py`
- 新建 `tests/runtime/test_lane.py`
- 新建 `tests/runtime/test_lane_multiprocess.py`
- 新建或修改 `tests/runtime/test_filelock.py`
- 修改 `tests/runtime/test_import_boundary.py`
- 仅当新增依赖扫描或公共导出检查需要共享 helper 时，允许在对应测试目录添加私有 `_helpers.py`；不得放入生产代码。

### 允许修改的 README

- 修改 `dayu/README.md`：把 `dayu.runtime.lane`、`dayu.runtime.filelock`、`dayu.host` 公共类型从“设计要求”同步为当前已实现边界；不写未来计划。
- 新建 `dayu/host/README.md`：Host 开发手册，只说明 Phase 1 已落地的公共类型、construction tooling options、边界和 non-goals；不写 durable store / command path 的未来实现细节。
- 修改 `tests/README.md`：增加 `tests/host` 测试层级、runtime lane multi-process 测试命令和维护约定。
- 根目录 `README.md` 不更新，除非 implementation 实际改变用户命令或安装方式；仅新增 `filelock` 生产依赖不改变用户手册命令。
- `dayu/runtime/__init__.py` 只做包 docstring 最小更新，不作为 README；不得新增 package-root export。

### 明确禁止修改

- `dayu/engine/**`
- `tests/engine/**`
- `dayu/fins/**`
- 财报业务工具、财报 prompt、Fins storage。
- Host durable store、EventLog、ToolRuntime、RunInputBuilder、WorkerProxy 的实现文件；这些文件当前不存在或属于后续 phase，不得提前创建半成品。

## Contract / API Decisions

### `dayu.host` 公共类型放置与导出边界

- `dayu.host.api` 放 Host request / snapshot / context / status / error / stream cursor 类型。
- `dayu.host.tooling` 放 Host construction 的 ToolBundle 输入边界类型。
- `dayu.host.__init__` 只导出 Phase 1 承诺的公共类型，不导出内部 helper，不做兼容 re-export。
- Host 公共类型不得放入 `dayu.contracts`。`dayu.contracts` 只保留 Host / Engine / ToolRuntime 共同理解的协作契约，例如现有 `ToolBundle`。
- `dayu.host` 不得 import `dayu.engine`、`dayu.fins`、`dayu.service`、`dayu.ui`。
- Engine 不得 import `dayu.host`，用 import boundary tests 锁定。

### Host request / snapshot / status / error / context 最小类型清单

在 `dayu.host.api` 中实现以下 frozen dataclass / `StrEnum` / Protocol 类型，全部提供中文 docstring、强类型字段和 `__all__`。

Status / enum：

- `SessionStatus(StrEnum)`: `OPEN`, `CLOSED`
- `RunStatus(StrEnum)`: `QUEUED`, `RUNNING`, `WAITING`, `CANCELLING`, `RECOVERING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `LOST`
- `AttemptStatus(StrEnum)`: `STARTING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `SUSPENDED`, `STEERED`, `LOST`
- `FollowupBehavior(StrEnum)`: `QUEUE = "queue"`, `STEER = "steer"`
- `CancelMode(StrEnum)`: `GRACEFUL = "graceful"`；不得加入 `force` / `immediate`
- `WaitResolutionSource(StrEnum)`: `POLL = "poll"`, `CALLBACK = "callback"`, `MANUAL = "manual"`
- `SourceRunRelation(StrEnum)`: `RETRY = "retry"`, `REPLAY = "replay"`
- `HostApiErrorCode(StrEnum)`: `NOT_FOUND`, `INVALID_STATE`, `CONFLICT`, `IDEMPOTENCY_CONFLICT`, `PERMISSION_DENIED`, `INTERNAL_ERROR`

Context / input helper：

- `OperationContext`
  - `operation_name: str`
  - `operation_kind: str`
  - `business_domain: str`
  - `business_object_type: str | None`
  - `business_object_id: str | None`
  - `scenario: str | None`
  - `correlation_id: str | None`
- `AuthorizationClaim`
  - `name: str`
  - `value: str`
- `HostCallContext`
  - `actor: str`
  - `source: str`
  - `request_id: str`
  - `authorization_claims: tuple[AuthorizationClaim, ...]`
  - `operation_context: OperationContext`
- `HostMetadataEntry`
  - `key: str`
  - `value: JsonValue`
  - 仅用于非状态机、非幂等、非恢复、非审计主链附加说明；required fields 禁止塞入 metadata。
- `HostInput`
  - `display_text: str`
  - `payload_ref: str | None`
  - `payload_digest: str | None`
  - Phase 1 不实现 payload store，只定义 typed input envelope。
- `SessionSlotRef`
  - `scope: str`
  - `slot_key: str`
- `HostStreamCursor`
  - `event_sequence: int`
  - 必须校验非负。

Host handle / command facet：

- `HostCommandFacet(Protocol)`
  - 只作为未来函数式公共 API 的 opaque command handle 类型。
  - 最小成员：`@property def host_handle_id(self) -> str: ...`
  - 不得持有 store / policy / tool runtime 具体实现，也不得成为 god bag。

Requests：

- `EnsureSessionRequest`: `scope`, `slot_key`, `metadata`
- `CreateSessionRequest`: `context`, `client_request_id`, `bind_slot`, `scope`, `slot_key`, `metadata`
- `CloseSessionRequest`: `context`, `client_request_id`, `reason`
- `PurgeSessionRequest`: `context`, `client_request_id`, `reason`
- `StartRunRequest`: `context`, `session_id`, `client_request_id`, `input`, `execution_target`, `queue_policy`
- `CancelRunRequest`: `context`, `client_request_id`, `reason`, `mode`
- `CancelSessionRunsRequest`: `context`, `client_request_id`, `reason`, `mode`
- `SubmitFollowupRequest`: `context`, `session_id`, `client_request_id`, `input`, `behavior`, `target_run_id`
- `RetryRunRequest`: `context`, `client_request_id`, `reason`
- `ReplayRunRequest`: `context`, `client_request_id`, `reason`, `repair_instruction`
- `ResolveWaitRequest`: `context`, `idempotency_key`, `outcome_ref`, `source`, `observed_at`

Snapshots / stream：

- `TerminalResultSummary`: `status`, `summary_ref`, `summary_digest`
- `OutboxSummary`: `terminal_event_id`, `event_sequence`, `delivery_state`
- `SessionSnapshot`: `session_id`, `status`, `slot`, `active_run_id`, `queued_run_ids`, `timeline_cursor`
- `RunSnapshot`: `run_id`, `session_id`, `status`, `current_attempt_id`, `terminal_result_summary`, `event_cursor`, `source_run_id`, `source_run_relation`, `outbox_summary`
- `FollowupSnapshot`: `accepted_input_ref`, `behavior`, `target_run_id`, `queued_run_id`, `current_cursor`
- `PurgeSessionResult`: `session_id`, `purged`, `purge_tombstone_ref`, `deleted_counts_digest`
- `HostEventView`: `event_sequence`, `event_id`, `event_type`, `session_id`, `run_id`, `payload_ref`, `payload_digest`
- `HostEventStream`: `events`, `next_cursor`

Error：

- `HostApiError(Exception)`: `code: HostApiErrorCode`, `message: str`, `retryable: bool`
- Phase 1 只定义错误类型，不实现 command path 抛错路径。

Validation rules：

- 所有 id / name / reason 字段必须拒绝空字符串或纯空白。
- `HostStreamCursor.event_sequence` 必须非负。
- `SubmitFollowupRequest.behavior=STEER` 时 `target_run_id` 必须非空；`behavior=QUEUE` 时 `target_run_id` 必须为 `None`。
- `CreateSessionRequest.bind_slot=True` 时 `scope` 与 `slot_key` 必须同时非空；`bind_slot=False` 时二者可以为 `None`。
- `CancelRunRequest.mode` 与 `CancelSessionRunsRequest.mode` 第一版只能是 `GRACEFUL`。
- `HostCallContext` 不定义幂等范围；每个 request 自己携带 `client_request_id` 或 `idempotency_key`。

### HostToolingOptions / ToolBundle construction input

在 `dayu.host.tooling` 中实现：

```text
class ToolBundleSourceKind(StrEnum):
    EXPLICIT_PROVIDER = "explicit_provider"
    CONFIG_BINDING = "config_binding"
    PACKAGE_ENTRYPOINT = "package_entrypoint"
    SERVICE_COMPOSITION = "service_composition"

class FrameworkToolName(StrEnum):
    FETCH_MORE = "fetch_more"

@dataclass(frozen=True, slots=True)
class ToolBundleSourceRef:
    source_kind: ToolBundleSourceKind
    source_id: str
    version_ref: str | None = None
    content_digest: str | None = None

@dataclass(frozen=True, slots=True)
class FrameworkToolPolicyView:
    reserved_framework_tool_names: frozenset[FrameworkToolName]
    enabled_framework_tools: frozenset[FrameworkToolName]

@dataclass(frozen=True, slots=True)
class HostToolingOptions:
    business_tool_bundle: ToolBundle
    source_refs: tuple[ToolBundleSourceRef, ...]
    framework_tool_policy: FrameworkToolPolicyView
```

Decisions：

- `ToolBundleSourceKind` 与 `FrameworkToolName` 必须使用 Python 3.11 `enum.StrEnum`，不得用普通字符串常量或 `typing.Literal`。
- `FrameworkToolPolicyView` 必须是 frozen dataclass，字段至少包含：
  - `reserved_framework_tool_names: frozenset[FrameworkToolName]`
  - `enabled_framework_tools: frozenset[FrameworkToolName]`
- 默认 reserved framework tool names 至少包含 `FrameworkToolName.FETCH_MORE`。
- Phase 1 默认 enabled framework tools 为空集合；这只表示 construction-time view，不表示完整工具治理策略。
- 提供 `default_framework_tool_policy_view() -> FrameworkToolPolicyView`，返回 reserved 包含 `FETCH_MORE`、enabled 为空。
- `HostToolingOptions.__post_init__` 必须校验：
  - `source_refs` 非空，且每个 `source_id` 非空。
  - `business_tool_bundle.definitions` 中任一工具名不得等于 reserved framework tool name 的字符串值，例如 `fetch_more`。
  - `enabled_framework_tools` 必须是 `reserved_framework_tool_names` 的子集；当前只有 `FETCH_MORE`。
- 不在 Phase 1 计算 durable tool snapshot、不注入 framework tool、不创建 ToolRuntime factory、不扫描业务工具。

## Cross-Process `dayu.runtime.lane` Decisions

### Public API

在 `dayu.runtime.lane` 中实现并导出：

- `LaneConfig`
- `LaneOwner`
- `SQLiteLaneCoordinatorConfig`
- `LaneClaimToken`
- `LaneAcquired`
- `LaneAcquireCancelled`
- `LaneAcquireTimedOut`
- `LaneAcquireOutcome`：`typing.TypeAlias`，定义为 `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`，不得创建新 dataclass / wrapper class。
- `LaneController`
- `RuntimeLaneError`
- `RuntimeLaneConfigError`
- `RuntimeLaneClosedError`
- `RuntimeLaneClaimLostError`

Public shape：

```text
@dataclass(frozen=True, slots=True)
class LaneConfig:
    name: str
    capacity: int
    default_timeout_seconds: float | None
    claim_ttl_seconds: float
    heartbeat_interval_seconds: float

@dataclass(frozen=True, slots=True)
class LaneOwner:
    owner_id: str
    pid: int
    process_start_token: str | None

@dataclass(frozen=True, slots=True)
class SQLiteLaneCoordinatorConfig:
    db_path: Path
    create_parent_dirs: bool = True
    busy_timeout_seconds: float
    poll_interval_seconds: float

@dataclass(slots=True)
class LaneClaimToken:
    name: str
    claim_id: str
    owner: LaneOwner
    expires_at: datetime
    released: bool
    async def refresh(self) -> None
    async def release(self) -> None

@dataclass(frozen=True, slots=True)
class LaneAcquired:
    token: LaneClaimToken

@dataclass(frozen=True, slots=True)
class LaneAcquireCancelled:
    reason: str | None

@dataclass(frozen=True, slots=True)
class LaneAcquireTimedOut:
    elapsed_seconds: float

LaneAcquireOutcome: TypeAlias = LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut

class LaneController:
    @classmethod
    async def open(
        cls,
        configs: Sequence[LaneConfig],
        *,
        coordinator: SQLiteLaneCoordinatorConfig,
        owner: LaneOwner | None = None,
    ) -> LaneController

    async def acquire(
        self,
        name: str,
        *,
        token: CancellationToken | None = None,
        timeout_seconds: float | None = None,
    ) -> LaneAcquireOutcome

    async def close(self, reason: str | None = None) -> None
```

### Coordinator / DB

- SQLite runtime lane coordinator 使用独立 DB 文件，不复用 Host durable store。
- Phase 1 不提供模块级默认路径、不从 Host package 读取配置、不创建隐式 singleton。
- `LaneController.open(...)` 必须显式接收 `SQLiteLaneCoordinatorConfig(db_path=...)`。
- 推荐给后续 Host composition root 的 workspace runtime DB 路径是 `workspace/runtime/runtime_lanes.sqlite3`，但 Phase 1 runtime 模块只在 README / docstring 中说明推荐路径，不实现默认路径 helper。
- Tests 使用 `tmp_path / "runtime_lanes.sqlite3"`；不得写入真实 `workspace/`。
- `create_parent_dirs=True` 时创建 DB parent directory；`False` 且 parent 不存在时抛 `RuntimeLaneConfigError`。
- DB 初始化必须设置 `PRAGMA journal_mode=WAL`。该 WAL 设置只属于 runtime lane DB，不改变、不约束 Host durable store 的 SQLite policy。
- SQLite schema 只允许保存 runtime capacity coordination 字段：
  - `lane_name`
  - `claim_id`
  - `owner_id`
  - `pid`
  - `process_start_token`
  - `created_at`
  - `heartbeat_at`
  - `expires_at`
- `lane_name + claim_id` 为 primary key；查询 active claims 时按 `lane_name` 过滤。
- 不保存 Session / Run / Attempt / EventLog / Tool / 财报业务字段。
- SQLite `busy_timeout_seconds` 只应用于 runtime lane DB connection，不影响 Host durable store policy。
- 所有 claim / release / heartbeat / stale cleanup 使用短事务；等待容量时不得持有长事务。
- `LaneController.open(owner=None)` 时 runtime 自动生成 owner：`owner_id=secrets.token_hex(8)`，`pid=os.getpid()`，`process_start_token=None`；调用方可通过 `owner=` 显式覆盖。

### Time / heartbeat ownership

- Phase 1 选择 `LaneController` 管理 heartbeat task。
- `LaneController` 为当前 controller 持有的 unreleased tokens 启动一个后台 heartbeat task，按所有 lane config 的最小 `heartbeat_interval_seconds` 或固定内部调度间隔循环刷新。
- `LaneClaimToken.refresh()` 也允许调用方显式刷新，但不是必需持有方式。
- 使用私有 `_LaneClock`，通过 `time.monotonic()` + controller open 时的 UTC wall-clock anchor 生成同一进程内一致的 UTC `datetime`，避免本进程内 wall clock 回拨影响 TTL 计算。
- 跨进程 clock skew 只影响 capacity availability eventual consistency；不得被解释为 Host truth。
- heartbeat update 若发现对应 `(lane_name, claim_id, owner_id)` row 不存在或已过期，token 标记为 released / lost，后续 `refresh()` 抛 `RuntimeLaneClaimLostError`；`release()` 仍保持幂等。
- background heartbeat 遇到不可恢复 SQLite error 时，controller 记录 first heartbeat error，停止接受新 acquire，并让后续 acquire 返回 cancelled 或抛结构化 `RuntimeLaneError`。不得静默继续误导调用方。

### Claim / release semantics

- `LaneConfig.name` 必须非空；`capacity` 必须为正整数。
- `claim_ttl_seconds` 必须大于 `heartbeat_interval_seconds`，二者都必须为正。
- 重复 lane name、未知 lane acquire、非法 TTL / heartbeat / capacity 均为结构化 runtime config error。
- `claim_id` 用 `secrets.token_urlsafe(...)` 或等价不可猜随机 id。
- acquire 成功流程的 stale cleanup、active count 和 insert 必须在同一个 SQLite transaction 内完成：
  - 短事务内删除同 lane `expires_at <= now` 的 stale claims。
  - 统计 active claims。
  - active count 小于 capacity 时 insert claim。
  - 返回 `LaneAcquired(token=...)`。
- `LaneClaimToken.release()` 异步、幂等，按 `(lane_name, claim_id, owner_id)` 删除 claim；重复 release 不影响其它 claim。
- token id 只标识 runtime capacity claim，不得传入 Host EventLog 作为 canonical identity。

### Cancel / timeout / close

- `timeout_seconds=None` 表示使用 `LaneConfig.default_timeout_seconds`；若两者都是 `None`，无限等待。
- `timeout_seconds=0` 表示 non-blocking acquire，只尝试一次短事务；容量满时返回 `LaneAcquireTimedOut(elapsed_seconds=0 或近似值)`。
- 正数表示最多等待对应秒数；timeout 返回 `LaneAcquireTimedOut`，不得占用容量。
- 等待期间传入的 `CancellationToken` 取消时返回 `LaneAcquireCancelled(reason=token.cancel_reason())`，不得创建 claim。
- cancellation 与 timeout 同时命中时 cancellation 优先。
- 外层 `asyncio.Task.cancel()` 必须透传 `asyncio.CancelledError`，不得包装成 outcome。
- `LaneController.close(reason)`：
  - 停止接受新 acquire。
  - 唤醒 pending acquire 返回 `LaneAcquireCancelled(reason)`。
  - best-effort release 当前 controller 持有且未 release 的 tokens。
  - 停止 heartbeat task。
  - 重复 close 幂等。

### Non-goals

- lane 只表达 runtime capacity，不是 Host truth、lease / fencing、Attempt owner、dispatch record、EventLog ordering、admission、recovery proof。
- stale cleanup 只释放 runtime capacity，不能证明 Host Attempt orphan，不能写 EventLog，不能授权 takeover。
- 第一版不承诺 FIFO、公平性、优先级、权重、跨 lane ordering 或跨机器分布式限流。

## `dayu.runtime.filelock` Decisions

### Public API

在 `dayu.runtime.filelock` 中实现并导出：

- `RuntimeFileLockOptions`
- `RuntimeFileLock`
- `RuntimeFileLockToken`
- `file_lock`
- `RuntimeFileLockError`
- `RuntimeFileLockTimeoutError`

Public shape：

```text
@dataclass(frozen=True, slots=True)
class RuntimeFileLockOptions:
    lock_path: Path
    timeout_seconds: float | None = None
    create_parent_dirs: bool = True

@dataclass(slots=True)
class RuntimeFileLockToken:
    lock_path: Path
    released: bool
    def release(self) -> None

class RuntimeFileLock:
    def acquire(self, timeout_seconds: float | None = None) -> RuntimeFileLockToken
    def __enter__(self) -> RuntimeFileLockToken
    def __exit__(self, exc_type, exc, tb) -> None

def file_lock(
    lock_path: str | Path,
    *,
    timeout_seconds: float | None = None,
    create_parent_dirs: bool = True,
) -> RuntimeFileLock
```

Decisions：

- Phase 1 只提供同步 wrapper；不提供 async context manager，不在线程池中隐藏阻塞 acquire。
- 只有 `dayu.runtime.filelock` 可以直接 import `from filelock import FileLock` 和第三方 timeout 类型。
- `lock_path` 是显式 lock file 路径，不从业务文件路径隐式派生。
- `create_parent_dirs=True` 创建 parent directory；`False` 且 parent 不存在时抛 `RuntimeFileLockError`。
- `timeout_seconds=None` 使用第三方 FileLock 默认等待语义；`0` 表示 non-blocking；正数表示最多等待。
- 第三方 `filelock.Timeout` 必须包装为 `RuntimeFileLockTimeoutError`。
- parent directory 创建失败、路径非法、acquire 失败统一包装为 `RuntimeFileLockError` 或子类。
- `RuntimeFileLockToken.release()` 幂等；context manager 退出必须 release，异常路径也必须 release。
- 不实现 stale lock 探测、锁文件删除、owner pid 解析、跨进程 owner takeover、强制 break lock。
- 不承诺 reentrant lock 语义；测试不得断言第三方库 reentrant 细节。

## Implementation Slices

### Slice 1: `dayu.host` public API typed contracts

Objective：

- 创建 `dayu.host` 公共命名空间，落地 Host 后续 phases 可依赖的 request / snapshot / status / error / context 类型。

Allowed files/modules：

- `dayu/host/__init__.py`
- `dayu/host/api.py`
- `tests/host/__init__.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_weak_typing_guard.py`
- `dayu/host/README.md`
- `dayu/README.md`
- `tests/README.md`

Exact allowed changes：

- 新建 Host package。
- 实现本计划 “Host request / snapshot / status / error / context 最小类型清单”。
- `dayu.host.__init__` 导出 Slice 1 类型。
- 增加 import boundary / package exports / weak typing guard / validation tests。
- README 只同步当前已实现的公共类型和测试层级。

Implementation instructions：

- 所有 dataclass 使用 `frozen=True, slots=True`，除非 Exception 类型需要普通 class。
- 所有枚举使用 `enum.StrEnum`。
- 所有模块、类、函数提供中文 docstring，字段语义写在类 docstring。
- 不使用 `Any`、`object`、裸 `dict`、无类型参数、无类型返回。
- 需要 JSON 值时 import `JsonValue` from `dayu.contracts.json_value`。
- Validation 放在 `__post_init__` 或模块级私有 helper 中；禁止嵌套 helper。

Non-goals：

- 不实现任何 Host command function。
- 不创建 durable store、EventLog row、dispatch record、policy provider set。
- 不导入 Engine / Fins。

Tests / validation：

- `pytest tests/host -q`
- `python -m pyright dayu/host tests/host`
- Expected assertions：
  - `dayu.host.__all__` 只包含承诺类型。
  - status / error enums 字符串值稳定。
  - request validation failure paths 覆盖空 id、非法 cursor、steer 缺 `target_run_id`、queue 携带 `target_run_id`、bind slot 缺 scope / slot_key。
  - import boundary 扫描确认 `dayu.host` 不 import `dayu.engine` / `dayu.fins` / `dayu.service` / `dayu.ui`。
  - weak typing guard 阻止 `Any` / `object` / 无类型签名。

Completion signal：

- `dayu.host` 可导入且 public contract tests 通过。

Stop condition：

- 若必须决定 command path 函数签名以外的新状态机、store schema、EventLog payload 或 policy provider shape，停止交回 controller。

### Slice 2: `dayu.runtime.lane` cross-process coordinator

Objective：

- 实现层中立 cross-process named semaphore / capacity guard primitive，使用独立 SQLite runtime lane DB。

Allowed files/modules：

- `dayu/runtime/lane.py`
- `tests/runtime/test_lane.py`
- `tests/runtime/test_lane_multiprocess.py`
- `tests/runtime/test_import_boundary.py`
- `dayu/README.md`
- `tests/README.md`

Exact allowed changes：

- 新增 `dayu.runtime.lane` public API 与 error classes。
- 增加 SQLite coordinator schema bootstrap、claim / release / heartbeat / stale cleanup / cancel / timeout / close。
- 增加 async unit tests 与 multi-process tests。
- 更新 runtime import boundary tests。
- README 同步 runtime lane 当前能力和测试命令。

Implementation instructions：

- 只依赖标准库、`dayu.contracts.cancellation.CancellationToken` 和同包层中立 helper。
- SQLite 操作可用 `asyncio.to_thread` 包装同步 `sqlite3` 短事务；不得引入第三方 async sqlite 依赖。
- 每次 DB 操作打开短连接或使用受控短生命周期连接；设置 `PRAGMA busy_timeout`；DB 初始化设置 `PRAGMA journal_mode=WAL`，且 WAL 只属于 runtime lane DB。
- DB 初始化创建最小 table 与 indexes，不创建 Host 业务字段。
- `LaneAcquireOutcome` 必须使用 `typing.TypeAlias` 定义为 `LaneAcquired | LaneAcquireCancelled | LaneAcquireTimedOut`，不得创建新 dataclass。
- `LaneController.open(owner=None)` 时使用 `secrets.token_hex(8)` 生成 `owner_id`，`os.getpid()` 生成 `pid`，`process_start_token=None`；调用方可显式传入 `LaneOwner` 覆盖。
- acquire 成功路径的 stale cleanup、active count 和 insert 必须在同一个 SQLite transaction 内完成。
- pending acquire 用 `asyncio.Event` / sleep + poll interval 协作等待；不得长事务等待。
- `LaneController.close` 必须唤醒 pending acquire。
- 不要从 `dayu.runtime.__init__` re-export lane 类型。

Non-goals：

- 不接入 Host dispatch。
- 不实现 distributed limiter / fairness。
- 不把 lane token 传给 Host EventLog 或 Attempt。

Tests / validation：

- `pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q`
- `python -m pyright dayu/runtime/lane.py tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py`
- Expected assertions：
  - 重复 lane name、非正 capacity、非法 TTL / heartbeat、未知 lane acquire 抛结构化错误。
  - 独立 runtime SQLite lane DB 初始化；schema 不含 Host / Fins 字段。
  - 成功 acquire / heartbeat / release。
  - 重复 release 不影响其它 claim。
  - `timeout_seconds=0` capacity 满时 timed out。
  - 正 timeout 返回 timed out 且不占 capacity。
  - `CancellationToken` 取消返回 `LaneAcquireCancelled`。
  - `asyncio.Task.cancel()` 透传 `CancelledError`。
  - `LaneController.close()` 取消 pending acquire 并 best-effort release held tokens。
  - `tests/runtime/test_import_boundary.py` 现有 runtime import boundary 扫描覆盖新增 `lane.py`，确认 `dayu.runtime.lane` 不 import Engine / Host / Service / UI / Fins。
  - 多进程共享同一 DB 时 successful claims 总数不超过 capacity。
  - 多进程测试由父进程用 `tmp_path` 或 `tempfile` 创建同一个 DB path，并通过 subprocess CLI 参数或环境变量传给子进程；子进程必须使用该共享路径构造 `SQLiteLaneCoordinatorConfig`。
  - 一个进程持有 claim 时，另一个进程 non-blocking acquire timed out。
  - 正常 release 后其它进程可 acquire。
  - 持有 claim 的进程崩溃或停止 heartbeat 后，TTL 过期并 stale cleanup 后其它进程可 acquire。
  - 不断言 acquire ordering。
  - busy timeout 竞争场景不破坏 capacity invariant。
  - TTL / clock skew 测试只断言 eventual acquire，不断言 Host truth。

Completion signal：

- `dayu.runtime.lane` 满足 Phase 1 runtime capacity primitive，unit + multi-process tests 通过。

Stop condition：

- 若需要 Host store 默认路径、Host cancel propagation、Attempt owner、lease / fencing 或 recovery proof 才能实现测试，停止交回 controller。

### Slice 3: `dayu.runtime.filelock` sync wrapper

Objective：

- 实现层中立同步 file lock wrapper，统一第三方 `filelock.FileLock` 依赖边界和错误语义。

Allowed files/modules：

- `dayu/runtime/filelock.py`
- `pyproject.toml`
- `tests/runtime/test_filelock.py`
- `tests/runtime/test_import_boundary.py`
- `dayu/README.md`
- `tests/README.md`

Exact allowed changes：

- 把 `filelock` 加入 `pyproject.toml` production dependencies。
- 新增 `dayu.runtime.filelock` public API 与 runtime error classes。
- 增加 timeout、parent directory、release idempotency、context manager、third-party error wrapping tests。
- 更新 import boundary，确认只有 `dayu.runtime.filelock` 直接 import 第三方 `filelock`。

Implementation instructions：

- wrapper 内部持有第三方 FileLock 实例和 acquire 返回的 lock object；token release 调用第三方 release。
- `RuntimeFileLock.__enter__` 调用 `acquire()` 并缓存 token，`__exit__` release。
- release 幂等通过 token 内部 `released` 布尔状态保证。
- `create_parent_dirs=False` 时先检查 parent，不存在直接抛 `RuntimeFileLockError`，不得让第三方异常泄漏。
- 不删除 lock 文件。

Non-goals：

- 不实现 async file lock。
- 不做 stale takeover / break lock / owner pid 解析。
- 不用 filelock 保护 SQLite / EventLog。

Tests / validation：

- `pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q`
- `python -m pyright dayu/runtime/filelock.py tests/runtime/test_filelock.py`
- Expected assertions：
  - parent directory creation。
  - `create_parent_dirs=False` 缺 parent 时结构化错误。
  - context manager release。
  - release idempotency。
  - non-blocking timeout 被包装为 `RuntimeFileLockTimeoutError`。
  - `tests/runtime/test_import_boundary.py` 现有 runtime import boundary 扫描覆盖新增 `filelock.py`，确认 `dayu.runtime.filelock` 不 import Engine / Host / Service / UI / Fins。
  - 新增断言：第三方 `filelock` 只允许出现在 `dayu.runtime.filelock`，其它 runtime 模块和 Host / Service / Fins / Engine 不得直接 import 第三方 `filelock`。

Completion signal：

- `dayu.runtime.filelock` 可导入并通过 runtime filelock tests。

Stop condition：

- 若需要实现 async wrapper、stale lock takeover 或删除 lock 文件，停止交回 controller。

### Slice 4: HostToolingOptions / ToolBundle construction input validation and docs / tests sync

Objective：

- 落地 Host construction 的业务 `ToolBundle` typed input boundary，验证 reserved framework tool name 冲突，并完成 Phase 1 文档同步。

Allowed files/modules：

- `dayu/host/tooling.py`
- `dayu/host/__init__.py`
- `tests/host/test_tooling_options.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`
- `dayu/host/README.md`
- `dayu/README.md`
- `tests/README.md`

Exact allowed changes：

- 实现 `ToolBundleSourceKind`、`FrameworkToolName`、`ToolBundleSourceRef`、`FrameworkToolPolicyView`、`HostToolingOptions`。
- 从 `dayu.host.__init__` 导出这些类型。
- 增加 ToolBundle construction input tests。
- README 同步 Host construction tool input 当前能力和 non-goals。

Implementation instructions：

- Import `ToolBundle` from `dayu.contracts.tool_declaration`。
- reserved framework tool name 冲突直接在 `HostToolingOptions.__post_init__` 抛 `ValueError`。
- `ToolBundleSourceRef.source_id` 非空；`source_refs` 非空。
- `default_framework_tool_policy_view()` 返回 frozen policy view；不得可变共享。
- 不生成 schema digest / bundle digest，除非可以完全基于现有 `ToolBundle` 且不引入新 durable snapshot 语义；默认不要在 Phase 1 实现 digest。

Non-goals：

- 不实现 ToolRuntime factory。
- 不注入 `fetch_more`。
- 不解析 policy provider。
- 不扫描业务工具。

Tests / validation：

- `pytest tests/host/test_tooling_options.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q`
- `python -m pyright dayu/host tests/host`
- Expected assertions：
  - `ToolBundleSourceKind` 与 `FrameworkToolName` 是 `StrEnum`。
  - default reserved includes `FETCH_MORE`，enabled default empty。
  - `FrameworkToolPolicyView` 是 frozen dataclass 风格，字段类型是 frozenset。
  - business `ToolBundle` 包含 `fetch_more` 时 `HostToolingOptions` validation failure。
  - `business_tool_bundle` 不出现在任何 request dataclass 字段中。
  - `dayu.host` 不 import 具体业务工具或 Fins。

Completion signal：

- Host construction tooling public types 可从 `dayu.host` 导入，tests 和 docs 同步完成。

Stop condition：

- 若需要决定 ToolsDiscovery / ScenePrepare provider contract、tool profile registry、Attempt snapshot durability 或 ToolRuntime policy resolution，停止交回 controller。

## Tests And Validation Commands

Implementation agent 每个 slice 先运行受影响测试；Phase 1 完成后运行：

```bash
source .venv/bin/activate
pytest tests/host tests/runtime -q
python -m pyright dayu/ tests/ utils/
```

建议按 slice 收窄：

```bash
source .venv/bin/activate
pytest tests/host -q
pytest tests/runtime/test_lane.py tests/runtime/test_lane_multiprocess.py -q
pytest tests/runtime/test_filelock.py tests/runtime/test_import_boundary.py -q
python -m pyright dayu/host dayu/runtime tests/host tests/runtime
```

Failure paths 必须覆盖：

- Host public contract validation：空字符串、非法 cursor、非法 followup behavior / target combination、slot binding 缺字段。
- Host tooling validation：reserved name conflict、空 source refs、空 source id、enabled framework tool 不在 reserved 集合。
- lane config validation：重复 lane、未知 lane、非正 capacity、TTL <= heartbeat、非正 heartbeat / TTL。
- lane acquire failure：capacity full non-blocking timeout、positive timeout、CancellationToken cancellation、Task.cancel propagation、close cancels pending acquire。
- lane multi-process：capacity invariant、release 后 acquire、crash / heartbeat stopped 后 TTL stale cleanup eventual acquire。
- lane busy timeout：并发竞争下不破坏 capacity invariant；busy timeout 错误必须结构化，不得写出重复 active claim。
- filelock failure：parent missing with create disabled、non-blocking timeout wrapping、release idempotency。
- import boundary：现有 runtime import boundary 扫描覆盖新增 `lane.py` / `filelock.py`；runtime 不 import Engine / Host / Service / UI / Fins；Host 不 import Engine / Fins / Service / UI；第三方 filelock 只允许出现在 `dayu.runtime.filelock`。

Coverage expectation：

- 新增生产模块单文件覆盖率目标 >= 80%。
- Multi-process tests 不断言 FIFO / fairness，只断言 capacity invariant 和 eventual cleanup。
- 若 pyright 发现既有 unrelated error，implementation agent 必须报告；若错误位于本 slice touched files，必须修复。

## Documentation Update Decision

- `dayu/README.md`: 需要更新。原因：`dayu.host` 公共类型、runtime lane / filelock 从设计要求变为当前代码能力；属于整体架构和稳定边界。
- `dayu/host/README.md`: 需要新建。原因：Phase 1 修改 / 新建 `dayu/host/`，README 触发规则要求 Host 开发手册说明接口、公共契约、边界、扩展点。只写当前已实现公共类型和 construction tooling options，不写 durable store 未来细节。
- `tests/README.md`: 需要更新。原因：新增 `tests/host` 层级、runtime lane multi-process tests、filelock tests 和运行命令。
- `dayu/runtime/__init__.py`: 需要最小更新 docstring。原因：新增 `dayu.runtime.lane` 和 `dayu.runtime.filelock` 层中立 runtime 能力；该更新只描述 package-level 当前能力，不得 re-export lane / filelock 符号。
- 根目录 `README.md`: 默认不更新。原因：Phase 1 不改变用户安装、配置、CLI、trace/render 入口或常用工作流。若添加 `filelock` 依赖导致安装说明实际变化，再由 implementation agent 报告 controller 裁决。
- `dayu/engine/README.md`: 不更新。原因：禁止修改 Engine，Phase 1 不改变 Engine contract。
- `dayu/fins/README.md`: 不更新。原因：禁止修改 Fins 业务工具，Phase 1 不改变财报能力。
- `dayu/config/README.md`: 不更新。原因：不改变配置覆盖关系或 prompts 目录职责。

## Review Gates

- Plan review 必须检查本计划是否 handoff-ready、code-generation-ready，尤其是 slice file ownership、runtime lane SQLite semantics、ToolBundle construction input validation、测试覆盖与 README 决策。
- 每个 implementation slice 后必须进入 code review；review scope 只覆盖 assigned slice。
- Slice review 必须拒绝任何 Engine / Fins 修改、Host durable store 夹带、ToolRuntime 注入提前实现、ToolsDiscovery / ScenePrepare 夹带。

## Open Questions

### Blocking Questions For Controller

0。

当前设计真源已经足够支撑 Phase 1 implementation plan。默认路径注入、heartbeat ownership、SQLite schema detail、busy timeout、clock / TTL eventual consistency 均已在本计划中收敛为 implementation decisions，不需要 implementation agent 自行决定 material choices。

### Non-Blocking Questions

- workspace runtime DB cleanup 谁负责：
  - Working assumption：Phase 1 runtime module 不负责删除 workspace lane DB；测试用 tmp_path cleanup；后续 Host composition root / workspace lifecycle phase 决定真实 workspace cleanup。
  - 低风险原因：lane DB 只保存 runtime capacity claims，TTL stale cleanup 可释放容量；不是 Host truth。
- lane DB 默认路径是否提供 helper：
  - Working assumption：Phase 1 不提供 helper，只文档建议后续 composition root 使用 `workspace/runtime/runtime_lanes.sqlite3`。
  - 低风险原因：设计要求 `LaneController.open(...)` 显式接收 `SQLiteLaneCoordinatorConfig(db_path=...)`，避免误用 Host store。
- bundle / schema digest 是否在 `HostToolingOptions` 计算：
  - Working assumption：Phase 1 不计算 durable digest，只校验 source refs 和 reserved name；digest / snapshot durability 由后续 ToolRuntime / command path phase 负责。
  - 低风险原因：Phase 1 目标是 construction typed input，不实现 Attempt snapshot。

触发回看信号：implementation agent 若发现无法不新增 public API、无法不引入默认路径 helper、或无法不实现 digest / ToolRuntime 即可完成 tests，必须停止并交回 controller。

## Residual Risks And Tracking

- SQLite runtime lane coordinator busy timeout：
  - Risk：高并发下 SQLite busy 可能导致 acquire loop 抖动。
  - Tracking：Slice 2 tests 覆盖 concurrent acquire 与 busy timeout，断言 capacity invariant 不破坏；Host durable store busy policy 留给后续 Host storage phase。
- Heartbeat ownership：
  - Risk：background heartbeat failure 需要让调用方可观测，避免持有者误以为仍占有容量。
  - Tracking：Slice 2 选择 controller-managed heartbeat；heartbeat failure 标记 token lost，后续 `refresh()` 抛 `RuntimeLaneClaimLostError`，controller 停止接受新 acquire。
- Clock skew / TTL eventual consistency：
  - Risk：跨进程 clock skew 可能让 stale cleanup 提前或延后，影响 capacity availability。
  - Tracking：TTL 只影响 runtime capacity，不影响 Host truth；tests 只断言 eventual cleanup，不断言精确时序。
- lane DB cleanup：
  - Risk：workspace runtime DB 文件可能残留。
  - Tracking：Phase 1 不删除真实 workspace DB；后续 Host composition root / workspace lifecycle phase 负责 cleanup policy。测试只用 tmp_path。
- Public Host contracts 初始形状可能在后续 command path phase 扩展：
  - Risk：过早暴露过多内部类型会导致兼容压力。
  - Tracking：Slice 1 只导出 request / snapshot / status / error / context 最小类型，不导出 durable rows 或 policy provider。
- ToolBundle digest / snapshot refs 尚未实现：
  - Risk：后续 Attempt snapshot phase 仍需定义 digest 算法和 durable refs。
  - Tracking：明确 deferred to ToolRuntime / command path related phases；Phase 1 只做 construction input validation。

## Implementation Completion Report Format

每个 implementation agent 完成 assigned slice 后，必须写 durable implementation artifact，并在最终报告中包含：

```markdown
## Work Gate

implementation

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施

## Assigned Slice

<slice id and name>

## Approved Plan

docs/host/phase1-public-contract-runtime-plan.md

## Assigned Scope

- allowed files/modules:
- explicit non-goals:

## Changed Files

- ...

## Plan Items Implemented

- ...

## Not Implemented

- <item and reason, or "无">

## Validation

- command:
  - result:
  - key assertions:

## Documentation Update

- updated:
- not updated and reason:

## Plan Gaps / Controller Questions

- <none or concrete blocker>

## Residual Risks And Uncovered Areas

- risk:
  - classification: fixed in current slice / later slice / later phase or work unit / existing issue / new issue or user decision
  - owner or destination:

## Completion Signal

<met / not met>

## Stop Condition Status

<none hit / stopped because ...>

## Artifact Path

docs/reviews/<artifact-name>.md
```

Implementation agent 不得 commit、push、create PR、进入下一 slice 或 closeout。
