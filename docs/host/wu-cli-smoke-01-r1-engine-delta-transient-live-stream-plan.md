# WU-CLI-SMOKE-01-R1 Engine Delta Transient Live Stream Remediation 实施计划

## 1. Gate 元数据

- Work unit：`WU-CLI-SMOKE-01-R1 Engine Delta Transient Live Stream Remediation`
- 类型：production-high 高风险 bug fix
- 当前 gate：plan-fix
- Goal 状态：已由用户确认；Goal artifact 为 `docs/reviews/wu-cli-smoke-01-r1-goal-confirmation.md`
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`
- 总控：`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`
- 当前分支：`phaseflow/wu-cli-smoke-01-r1`
- 本计划状态：accepted findings 已进入 plan-fix，等待原 reviewers re-review；不得据此文档声称 re-review、implementation、commit、push 或 PR 已完成

## 2. 第一性原理判断与直接证据

### 2.1 判断

问题真实且严重性评估成立。`reasoning_delta` 与 `content_delta`、`tool_call_delta` 都是生成过程中的短生命周期片段；它们不参与恢复、Run/Attempt 状态迁移、memory、audit、outbox 或 terminal answer。当前只有 reasoning 为满足 CLI live thinking 被写成 durable `PREVIEW` row，使“可见性”错误地拥有了“持久化”语义。对 N 个 reasoning chunk 产生 N 个 SQLite row，不只是容量问题，还把 EventLog cursor、projection 和读取契约绑定到本不应持久化的 token 级事实。

正确修复不是 retention/purge、Service 直读 Engine、CLI fallback 或继续给 `HostEvent` 增加可选字段，而是把“durable identity validation”与“live delivery”拆开：Host ingest 仍拥有接受资格，当前 `open_host` runtime 拥有 transient identity、fanout 和生命周期，Service/CLI 只消费 Host 公共联合类型。

### 2.2 根因证据链

1. `dayu/host/engine_ingest.py::_ingest_validated` 对 `REASONING_DELTA` 单独追加 `PREVIEW`，而 `_is_transient_delta_event` 只接受 `CONTENT_DELTA`、`TOOL_CALL_DELTA` 且不写 row；同一语义类别存在两个 durable policy。
2. `dayu/host/open_host.py::_watch_session_events_after` 只轮询 EventLog，因此 Service 想看到 live thinking 只能依赖 reasoning row。
3. `dayu/host/api.py::HostEvent` 强制携带 durable `event_id` / `event_sequence`，并用可选 `thinking` 把 transient display 塞进 durable envelope。
4. `dayu/host/read_api.py::_thinking_from_row` 从 reasoning `PREVIEW` row 投影 `HostThinkingView`，证明错误语义在 durable projection owner 内被建立，而非仅有展示 bug。
5. `dayu/service/entrypoint_runtime.py::EntrypointThinking` 与 `_emit_entrypoint_thinking_from_host_event` 依赖 durable `event_sequence`，CLI renderer 又据此排序、去重。
6. `dayu/host/dispatch.py::_consume_worker_events` 已为每个 execution 顺序分配 `worker_event_index`，并逐个等待 ingest；`EngineEventIngestor` 在写事务内调用 `_validate_durable_context` 和 late-state checks。这是发布前身份治理的现成线性化边界。
7. `docs/engine/design.md` 的 EngineEvent stream 明确只拥有单生成器内顺序，不拥有 Host cursor、fanout、replay 或 EventLog；因此不能把 runtime fanout 下沉给 Engine。

### 2.3 Semantic owner 裁决

| 语义 | 唯一 owner | 生产/校验/对外承诺 |
|---|---|---|
| Engine chunk 与生成器内顺序 | Engine event contract | Engine 产生 typed delta；不承诺 Host fanout/replay |
| Session/Run/current Attempt/execution/dispatch/late-state 接受资格 | Host ingest | 在 durable transaction 内校验；失败不得发布 |
| runtime identity、publication sequence、dedupe、watcher fanout、overflow/detach/close | 当前 `open_host` 拥有的 Host transient hub | 只在本进程、本 Host handle 生命周期内承诺 |
| durable facts、terminal identity、offline cursor | EventLog 与 durable `HostEvent` projection | 只从 committed EventLog row 派生 |
| 三类 delta 的公共 envelope/payload 闭集 | `dayu.host.api` | Host-owned typed public contract；不暴露 raw `EngineEvent` |
| CLI 是否展示 thinking | Service typed projection与 CLI renderer | Service 只选择 reasoning；CLI 只渲染，不重建 identity |

`dayu.runtime` 不拥有这项能力：fanout 必须理解 Host Session、Run、Attempt、execution、terminal fence 和 Host close，放入公共 runtime 包会破坏层中立边界并制造通用事件总线。

## 3. 目标、非目标与成功不变量

### 3.1 目标

1. `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA` 经过相同 Host ingest validation 后，统一投影为 typed `HostTransientDelta`，三者 EventLog row 数均为 0。
2. 同一 `open_host` runtime 内，attach 完成的多个 watcher 从同一 `watch_session_events` 公共接口收到相同 contract，并按 union member/type 选择消费。
3. stale、late、wrong Run/Attempt/execution/dispatch identity 与回滚 candidate 不得 fanout。
4. 慢消费者、detach、terminal、Host close 不反压 EventLog append，不取消 Run，不伪造 terminal，不泄漏 task。
5. CLI `--thinking`、`--no-thinking`、final answer、activity/detail、stdout/stderr、Ctrl+C cancel 和 renderer close 维持现有用户行为且无重复输出。

### 3.2 非目标

- 不提供 durable delta replay、历史 token/thinking 查询、断线补放、跨进程或跨 Host instance broker。
- 不提供 durable/transient 的统一 cursor 或全局可比较 sequence。
- 不修改 Engine provider、runner、reasoning 开关或 `EngineEvent` contract。
- 不重写 canonical `HostEvent`、outbox、audit、Tool Trace、Conversation Memory。
- 不删除整个 `PREVIEW` class；仅移除 reasoning per-chunk durable 特例。
- 不实现 R2 thinking panel，不增加 Service/CLI 通用 content/tool-call delta callback。
- 不新增 public buffer tuning、retention/purge、generic event bus 或 `dayu.runtime` helper。

### 3.3 必须持续成立的不变量

- `HostEvent.event_sequence` 只属于 EventLog；`HostTransientDelta.runtime_sequence` 只属于当前 runtime，类型和字段均不可互换。
- publish 必须发生在 durable identity/late-state validation transaction 成功返回之后；不得先 fanout 再校验或依赖下游过滤。
- 一个 accepted transient candidate 只构造一个 public envelope；所有已 attach 的目标 watcher 收到相同 `runtime_id`、`runtime_sequence` 与 `dedupe_key`。
- hub publish 是同步、non-blocking、non-throwing 的 queue offer；consumer 永远不能延迟 ingest transaction 或下一条 EventLog append。
- 同一 execution 按 `worker_event_index` ingest，hub 按 `runtime_sequence` 发布；同 Session watcher 看见相同有序子序列。
- 已进入该 watcher buffer 的同 Run delta 必须先于该 Run durable terminal 被交付；terminal 对 watcher 可见后，后续同 Run delta 被拒绝/丢弃，且不合成另一 terminal。
- watcher detach/overflow 只影响该 watcher；terminal 不结束 session watcher；Host close 正常结束 watcher。
- Service 不 import/消费 raw `EngineEvent`，不用 `hasattr/getattr`、字符串猜测、`extra payload` 或默认值修补 Host contract。

## 4. 已冻结的 public contract

### 4.1 Host public 类型

在 `dayu/host/api.py` 定义并由 `dayu/host/__init__.py` 正式导出：

```python
class HostTransientDeltaType(StrEnum):
    CONTENT_DELTA = "content_delta"
    REASONING_DELTA = "reasoning_delta"
    TOOL_CALL_DELTA = "tool_call_delta"

@dataclass(frozen=True, slots=True)
class HostContentDelta:
    iteration_id: str
    text_delta: str

@dataclass(frozen=True, slots=True)
class HostReasoningDelta:
    iteration_id: str
    text_delta: str

@dataclass(frozen=True, slots=True)
class HostToolCallDelta:
    iteration_id: str
    tool_call_index: int
    tool_call_id: str | None
    name_delta: str | None
    arguments_delta: str | None

HostTransientDeltaData: TypeAlias = (
    HostContentDelta | HostReasoningDelta | HostToolCallDelta
)

@dataclass(frozen=True, slots=True)
class HostTransientDelta:
    runtime_id: str
    runtime_sequence: int
    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    worker_event_index: int
    observed_at: datetime
    type: HostTransientDeltaType
    data: HostTransientDeltaData
    dedupe_key: str

HostSessionEvent: TypeAlias = HostEvent | HostTransientDelta
```

约束：

- `HOST_TRANSIENT_DELTA_TYPE_TO_DATA` 使用只读 mapping 固化 discriminator/data 一一对应，`__post_init__` 做严格类型与 UTC 时间校验。
- identity 字符串非空；`runtime_sequence`、`worker_event_index` 为正整数；`tool_call_index` 为非负整数。
- `text_delta` 和可选 tool-call fragment 保留 Engine contract 的原始字符串，包括空串/空白；Host 不 trim、不拼接、不 loose parse，不引入与 Engine 不同的业务语义。
- `HostTransientDelta` 不含 `event_id`、`event_sequence`、`event_class`、terminal/activity/thinking 可选字段。
- 从 `HostEvent` 删除 `thinking`，删除 `HostThinkingView`；`HostEvent` 的 durable identity、terminal、activity 语义保持不变。
- `runtime_id` 是每次 `open_host` 新建的 opaque UUID；`runtime_sequence` 是 hub 全局正整数计数。两者不持久化、不从 wall clock 推导。
- `dedupe_key` 由 hub 用 `runtime_id + execution_id + worker_event_index` 的稳定编码生成，是 opaque equality key，不允许消费者解析。

### 4.2 Public watch API

保留一个官方入口，不增设 Service 旁路：

```python
class Host(Protocol):
    def watch_session_events(
        self,
        session_id: str,
    ) -> AsyncIterator[HostSessionEvent]: ...
```

attach 语义：同步调用 `watch_session_events` 时先完成 public lifecycle gate；handle 已关闭时当场抛 `HostClosedError`，且不创建 subscription。打开状态下必须在返回 iterator 前同时注册 transient subscription，并把 Session 存在性检查所需 durable cursor read 提交给 durable actor；不要求在同步方法内阻塞等待 cursor future 完成。这样从返回点起发生的 publish 不会落入“generator 尚未首次迭代”的窗口，同时保留 cursor submit 先于调用方后续 mutating command 的 actor FIFO 边界。attach 前的 transient delta 不 replay；durable EventLog 仍从 attach 时取得的 cursor 向后轮询。

cursor attach failure contract 冻结为：

- iterator 首次 `__anext__` 必须先 await cursor future；Session 不存在/已 purge 时抛 public `HostApiError(code=NOT_FOUND, retryable=False)`。
- 其它 durable cursor read failure 继续由 `HostCommandHandle._run_read` 的 public error mapping 表达为 `HostApiError`：例如通用 durable failure 为 `INTERNAL_ERROR/retryable=False`，busy/retry-exhausted 沿现有 mapping 为 `INTERNAL_ERROR/retryable=True`。不得泄漏 `HostDurableError`、actor future/private operation exception，Service 也不得猜测底层异常类型。
- cursor future failure、首次或后续 `__anext__` cancellation、iterator 内部异常、显式 `aclose()` 都在同一个 Host iterator owner boundary detach subscription；同步 attach 中途失败必须回滚已注册 subscription。
- Host 返回的内部 closable iterator 必须拥有 subscription 与 cursor future，而不能只依赖 async generator 首次进入后的 `finally`。调用方取得 iterator 后从未开始迭代便立即 `aclose()`，也必须 detach；cursor future 由 done observation/owner cleanup 收口，不产生 unhandled-future warning。

iterator 对 durable/transient member 做 typed merge：

- 保持 durable `event_sequence` 内序与 transient `runtime_sequence` 内序。
- 每轮先提取已缓冲 transient，再交付同 Run terminal；若 durable batch 含 terminal，必须先 drain 已在 subscription 中的同 Run delta，然后 yield terminal，并把该 Run 记入 watcher-local terminal fence。
- fence 后到达的同 Run transient delta 不 yield。其它 Run/Session 后续事件仍可继续，terminal 不自动结束 watcher。
- 不承诺无关 durable progress 与 transient delta 的跨平面总序，也不允许调用方将迭代器位置变成 durable cursor。

### 4.3 Service / CLI 消费契约

`dayu/service/entrypoint_runtime.py` 继续只向 CLI 暴露现有 `on_thinking` callback，不增加通用 delta callback。`EntrypointThinking` 改为：

```python
@dataclass(frozen=True, slots=True)
class EntrypointThinking:
    run_id: str
    runtime_id: str
    runtime_sequence: int
    dedupe_key: str
    text_delta: str
```

Service 对 `HostSessionEvent` 做穷举 `isinstance` 分支：durable `HostEvent` 仍驱动 activity、terminal/final answer；`HostTransientDelta` 中只有 `HostReasoningDelta` 映射为 `EntrypointThinking`，content/tool-call delta 在本 WU 明确忽略。不得从 `type` 字符串或 optional field 猜 payload。

CLI renderer 用 `(runtime_id, runtime_sequence)` 检查同 runtime 单调性，并用 `dedupe_key` 等值去重。runtime 改变时重置 sequence baseline；相同 runtime 的重复/倒序项不再次写 stderr。final answer 仍只来自 durable terminal 写 stdout，activity/detail 仍只来自 durable activity；因此不产生 content/final/tool activity 双写。

Service bounded relay 的唯一 owner 是 `dayu/service/entrypoint_runtime.py` 中由 `_WatchAndWaitRuntime` 及其 factory 创建的 `queue`。该 private runtime 只把一个已 attach 的 `ClosableHostSessionEventIterator`、一个 `asyncio.Queue[HostSessionEvent | _WatcherFailure]` 与对应 drain task 绑定在一起；factory 使用有名常量 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY = 256` 构造 `queue(maxsize=...)`。`submit_entrypoint_turn_and_wait`、非终态 cancel wait 与 startup reconnect 等所有实际承接 watcher live items 的路径都必须复用该 factory。terminal-only（例如目标 Run 在 attach 前已终态）、无 watcher、一次性 outbox/drain 的 queue 不属于 live relay，保持现有语义，不机械设限。

backpressure / error propagation 链固定为：

```text
CLI/Service 暂未消费 _WatchAndWaitRuntime.queue
  -> _drain_host_events 的 await queue.put(item) 自然阻塞
  -> 不再调用 Host iterator.__anext__，Host merge iterator 暂停在 yield
  -> Host hub 仍以 put_nowait 向该 watcher 的 private subscription queue 发布
  -> Host subscription queue 满，subscription owner detach/标记 overflow
  -> iterator 在已接受连续前缀之后抛 public typed
     HostApiError(UNAVAILABLE, retryable=True,
       HostUnavailableDetail(
         component="session_live_stream", reason_code="slow_consumer"))
  -> _drain_host_events 仍用 await queue.put(_WatcherFailure(error=原异常))
  -> Service 的既有 typed watcher-failure / terminal Outbox fallback 收口
```

Service 侧禁止对 live relay 使用 `put_nowait`、捕获 `QueueFull` 后丢 item、替换旧 item、预留旁路槽、把 Host error 改造成另一异常，或仅写日志后继续伪装连续流。`_WatcherFailure` 必须保存原 `HostApiError` 实例供 failure decision 使用；面向 activity/result 的安全摘要只是投影，不能替代 typed error。relay 满时 terminal 仍由 durable EventLog/Outbox owner提交，Service 在 relay 恢复消费并观察 typed failure 后必须能从既有 Outbox fallback 取得同一 terminal identity，不得丢失或死锁。

## 5. Host 内部设计与精确 call path

### 5.1 新模块与内部类型

新增 `dayu/host/transient_delta.py`，不放入 `dayu.runtime`：

- `_TRANSIENT_WATCH_BUFFER_CAPACITY = 256`
- `ValidatedTransientDeltaCandidate`：只由 ingest 构造，携带已验证的 Session/Run/Attempt/execution、`worker_event_index`、`observed_at`、public payload；尚无 runtime identity。
- `HostTransientDeltaPublisher(Protocol)`：`publish(candidate) -> None`；同步且不抛异常是端口 contract。
- `HostTransientDeltaHub`：拥有 `runtime_id`、sequence counter、按 Session 建索引的 subscriptions 和 closed state。
- `HostTransientDeltaSubscription`：拥有 private bounded queue、overflow marker、watcher-local terminal Run fences、closed state；提供 `drain_nowait()`、`wait_ready(timeout_seconds)`、`mark_run_terminal(run_id)`、`close()`，不创建 background task。

hub 的 `publish` 在 opener 事件循环线程顺序执行：先分配一次 `runtime_sequence` 并构造一次 immutable `HostTransientDelta`，再对该 Session 当前 snapshot 中每个 subscription 执行 `put_nowait`。某队列满时立即 detach 并记录 typed overflow；其它订阅继续。错误 component/reason 与容量均使用有名模块常量，不散布魔法字符串/数字。ingestor 的 publisher 调用边界捕获 hub/port 意外，记录不含 delta 文本或 secret 的结构化 operator diagnostic，并保持原 accepted result；该异常隔离是 transient delivery contract，不是 durable fallback。

overflow 后 iterator 在消费完 queue 中已接受的连续前缀后抛：

```python
HostApiError(
    code=HostApiErrorCode.UNAVAILABLE,
    retryable=True,
    detail=HostUnavailableDetail(
        component="session_live_stream",
        reason_code="slow_consumer",
    ),
)
```

不 silent-drop 某个 delta 后继续，因为那会伪装连续 live stream。固定容量是内部安全边界，不加入 `open_host` options。

`wait_ready(...)` 必须实现 level-triggered readiness：queue 非空、overflow 或 closed 时立即返回；`publish` 必须在 `put_nowait`/overflow state 更新后发出 wakeup；`drain_nowait` 清理 readiness 前后必须在无 `await` 的 owner 临界段重新检查 queue/terminal state。禁止只把 `asyncio.Event` 当 edge-trigger signal，因为 publish 恰好落在 queue drain 与 `Event.clear()` 之间会造成非空 queue 睡到 poll timeout。Slice 2 用可控 barrier 覆盖 publish-before-wait、wait-before-publish、drain-last-item/clear 与 publish 交界、overflow/close wakeup 四类交错。

### 5.2 Ingest → publish 时序

修改 `dayu/host/engine_ingest.py`：

1. `EngineEventIngestor.__init__` 必须显式接收 `HostTransientDeltaPublisher`，不得用可选参数或 production fallback 隐藏漏接线。
2. `_is_transient_delta_event` 闭集改为三类 delta。
3. 新增模块级 `_validated_transient_delta_candidate(context, event)`，按 `EngineEventType` 与精确 `data` 类型映射 Host payload；不用 nested helper、cast-to-unknown、`hasattr/getattr` 或 raw metadata 透传。
4. `EngineIngestResult` 增加内部字段 `transient_delta: ValidatedTransientDeltaCandidate | None`；transient accepted result 的 `events` 仍为空，不伪造 durable row。
5. `_ingest_before_reactive_compaction` 仍先在 `HostTransactionRunner.run_write` 中执行 candidate shape、`_validate_durable_context`、duplicate terminal/late-state 与 `_ingest_validated`。transaction rollback/exception 没有 result，因此没有 publish。
6. transaction 成功返回后，`_finish_ingest` 发现 accepted transient candidate 才通过模块级 `_publish_transient_delta` 调用 publisher；该 helper 捕获 publisher 意外并只写 sanitized diagnostic，然后返回原 ingest result。publish 在 `_consume_worker_events` 继续下一 EngineEvent 前完成，但不 await watcher。
7. 移除 `REASONING_DELTA -> PREVIEW` 分支；三类 delta 都不调用 EventLog append。

`dayu/host/dispatch.py` 的 scheduler constructor/open 显式接收 publisher，并在 `_consume_worker_events` 创建 `EngineEventIngestor` 时传入。`dayu/host/open_host.py` 是唯一生产 composition root：先建 hub，再把 hub publisher 端口传给 scheduler/ingestor，同时把 hub 交给 `_PublicHostHandle` 的 watcher merge 路径。测试若直接构造 scheduler/ingestor，必须显式传 recording/no-op typed publisher fixture；生产接口不提供默认 fallback。

```text
EngineWorker EngineEvent
  -> dispatch 分配 worker_event_index
  -> EngineEventIngestor
       -> write transaction: shape + durable identity + late checks
       -> transient candidate（EventLog rows = 0）
       -> transaction 成功返回
  -> HostTransientDeltaHub.publish（non-blocking）
       -> runtime identity/sequence/dedupe
       -> 每个已 attach Session subscription 的 bounded queue
  -> _PublicHostHandle.watch_session_events typed merge
  -> Service 按 HostEvent / HostTransientDelta 分支
  -> CLI 只渲染 HostReasoningDelta
```

### 5.3 Watcher 并发与生命周期

修改 `dayu/host/open_host.py` 的 `_PublicHostHandle.watch_session_events`、`_watch_session_events_after` 及 close wiring：

- attach：同步 public lifecycle gate 后，在方法返回 iterator 前注册 subscription 并提交 cursor future；任一步同步失败都回滚 subscription。Host 内部 closable iterator 是 cursor future 与 subscription 的共同 owner，不能把 never-started cleanup 寄托在 async generator body 的 `finally`。
- multi-watcher：hub 对订阅 snapshot 顺序 offer，同一 public envelope 实例/identity fanout；一个 watcher 的取消或 overflow 不修改其它 watcher。
- ordering：merge loop 不能为每个 watcher 创建 producer task；EventLog 暂无新 row 时调用 `subscription.wait_ready(_SESSION_WATCH_POLL_INTERVAL_SECONDS)` 代替纯 sleep；每轮读 durable batch 前后都 drain 当前 transient 连续前缀，始终维护两个域各自顺序。yield 同 Run durable terminal 前调用 `mark_run_terminal`，后续 offer 在 subscription owner 边界拒绝该 Run。
- detach：首次 `__anext__` 的 cursor await、后续 merge iteration 与显式 `aclose()` 共享同一幂等 cleanup boundary；cursor typed failure、消费者 task cancel、iterator 异常、正常/never-started `aclose()` 都关闭 subscription，只清理自身，不调用 Host cancel API、不写 EventLog。未开始迭代的 cursor future 必须被观察，不能泄漏 actor/private exception warning。
- terminal：只来自 durable `HostEvent`，不关闭 session watcher。terminal fence 防止已终态 Run 的 late transient 对 UI 倒灌。
- slow consumer：hub 只 `put_nowait`；满队列 subscriber 变为 overflowed/detached。EventLog actor、dispatch、其它 watchers 不等待它。
- Host close：public gate 进入 closing 后先 `hub.close()` 唤醒/清空 watchers；iterator 正常结束，不调用 Run cancel API，不把 Run 状态改成 `CANCELLED`，不生成 `RUN_CANCELLED`、`RUN_FAILED` 或其它 terminal。随后沿既有 scheduler/worker/projection/store shutdown 路径停止本 handle worker 并关闭 projection/store；这是既有 handle lifecycle，不是用户 cancel。hub 无 per-watcher task，因此不增加 task join/leak surface。
- attach/cursor failure：close 后新 watch 继续由同步 public lifecycle gate 抛 `HostClosedError`；打开 handle 的 missing Session 在首次 `__anext__` 抛 `HostApiError(NOT_FOUND)`，其它 durable read failure按 Host read owner 映射为 public `HostApiError`。三者都不是 transient overflow error，任何路径都不得泄漏 actor/private exception。

### 5.4 Durable projection 清理

- `dayu/host/read_api.py` 删除 `_thinking_from_row` 和 `HostEvent(..., thinking=...)` 投影；历史 reasoning row 不做兼容解析。schema 按全新 contract 处理，不添加 migration/shim。
- `dayu/host/lifecycle_events.py` 从 `HostPreviewEventType` 移除 `REASONING_DELTA`；`PREVIEW` class 与其它粗粒度 preview 保留。
- `dayu/host/api.py` 删除 `HostThinkingView` 与 `HostEvent.thinking`；对应 package exports 同步删除。
- audit/outbox/memory/tool trace 不新增 transient input，确保它们继续只从 durable owner 派生。

## 6. 精确影响文件

### 6.1 生产代码

| 文件 | 计划修改 |
|---|---|
| `dayu/host/api.py` | 新增 transient enum/payload/envelope/union；watch 返回 union；删除 durable thinking view/field |
| `dayu/host/transient_delta.py` | 新增当前 runtime hub、publisher protocol、validated candidate、subscription、bounded overflow/close 语义 |
| `dayu/host/engine_ingest.py` | 三类统一映射、validation-success 后发布、reasoning 零 row |
| `dayu/host/dispatch.py` | 显式传递 publisher；维持 worker event 顺序 |
| `dayu/host/open_host.py` | composition root 建 hub；attach-before-return；durable/transient merge；detach/terminal/close |
| `dayu/host/read_api.py` | 删除 reasoning row → thinking 投影 |
| `dayu/host/lifecycle_events.py` | 删除 reasoning preview event type 特例 |
| `dayu/host/__init__.py` | 导出新的 public contract，移除旧 thinking export |
| `dayu/service/entrypoint_runtime.py` | 消费 `HostSessionEvent`；reasoning typed projection；bounded relay；thinking identity 迁移 |
| `dayu/cli/thinking.py` | 改用 runtime identity/sequence 去重和排序 |

不修改 `dayu/engine/**`、`dayu/runtime/**`、provider/runner、EventLog schema 或 storage migration。

所有新增/修改模块与类必须提供中文概览 docstring；函数/方法 docstring 必须完整列出参数、返回值和异常。所有签名使用严格具体类型，不引入 `Any`、`object`、无参数类型、lazy import、nested helper、`hasattr/getattr` 或 extra payload。

精确 symbol 迁移如下：

- `dayu.host.api`：新增 4.1 所列 public types 与只读 type/data mapping；修改 `Host.watch_session_events` 返回值；删除 `HostThinkingView` 和 `HostEvent.thinking`。
- `dayu.host.transient_delta`：实现 `ValidatedTransientDeltaCandidate`、`HostTransientDeltaPublisher`、`HostTransientDeltaHub`、`HostTransientDeltaSubscription` 及模块级 identity/dedupe/error helper；这些内部符号不从包根导出。
- `EngineEventIngestor.__init__`、`_ingest_validated`、`_finish_ingest`、`_is_transient_delta_event`：显式注入 publisher、统一三类 mapping、提交后发布；新增 `_validated_transient_delta_candidate` 和 `_publish_transient_delta`，删除 reasoning durable 分支。
- `HostDispatchScheduler` 的 construction/open path 与 `_consume_worker_events`：保存并下传 publisher；所有直接构造点显式提供 typed port。
- `_PublicHostHandle.__init__`、`watch_session_events`、`_watch_session_events`、`_watch_session_events_after`、`close` 与 `open_host` composition：拥有 hub/subscription、同步 attach、typed merge、finally detach 和 close。
- `read_api._host_event_from_row`（当前构造 `HostEvent` 的 row projection）删除 thinking 参数，删除 `_thinking_from_row`；`HostPreviewEventType` 删除 reasoning member。
- `ClosableHostEventIterator` 重命名为 `ClosableHostSessionEventIterator`；新增小型 private `_WatchAndWaitRuntime` 与唯一 factory，集中拥有 watcher、容量为 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY` 的 `queue` 和 drain task。`_attach_watcher`、`_drain_host_events`、`_drain_available_watcher_items`、`_drain_available_startup_terminal_items` 与 live relay queue annotations 改用 `HostSessionEvent`。terminal-only / 无 watcher queue 不经该 factory，也不机械改成 bounded。`_terminal_result_from_live_event`、`_startup_terminal_result_from_live_event`、activity projector 只接收已分支出的 `HostEvent`；thinking projector 改为 `_emit_entrypoint_thinking_from_transient_delta` / `_entrypoint_thinking_from_transient_delta`。
- `EntrypointThinking` 按 4.3 更换 identity；`CliThinkingRenderer` 将 `_last_event_sequence` 更换为 `_last_runtime_id` / `_last_runtime_sequence`，`record` 不再读取 durable sequence。

### 6.2 测试

| 文件 | 关键覆盖 |
|---|---|
| `tests/host/test_transient_delta.py`（新增） | payload closed mapping、hub fanout、sequence/dedupe、bounded overflow、detach、close、无 task；Event/Queue 四类可控 wakeup 交错 |
| `tests/host/test_engine_ingest_mapping.py` | 三类零 row；validated-only publish；stale/late/wrong identity/rollback 不发布；payload 精确映射 |
| `tests/host/test_watch_session_events.py` | attach race、多 watcher、双域顺序、terminal fence、watcher 继续、overflow 隔离；同步 `HostClosedError`、首次 `__anext__` 的 missing/durable typed failure；failure/cancel/started 与 never-started `aclose()` cleanup |
| `tests/host/test_open_host_runtime.py` | composition root、close 唤醒、无伪 terminal/Run cancel、无泄漏 task |
| `tests/host/test_host_activity_event_projection.py` | 删除 reasoning thinking durable projection；粗粒度 activity 保持 |
| `tests/host/test_public_event_stream.py` | durable stream 不再构造 reasoning delta row |
| `tests/host/test_lifecycle_events.py` | reasoning 不再属于 `HostPreviewEventType`；其它 preview 保持 |
| `tests/host/test_audit_sink.py` | 删除 reasoning preview fixture；证明 transient 不进入 audit |
| `tests/host/test_public_host_event.py` | durable/transient 类型字段和校验完全分离 |
| `tests/host/test_package_exports.py` | 新 contract 导出、旧 thinking export 删除 |
| `tests/host/test_dispatch_scheduler.py` | publisher 显式接线、逐 event ingest/publish 次序 |
| `tests/host/test_transient_delta_stress.py`（新增，`stress` marker） | 每类至少 1,000 delta 的 zero-row、fanout 与 terminal durable facts |
| `tests/service/test_entrypoint_runtime.py` | union 分支；仅 reasoning 回调；content/tool 忽略；`_WatchAndWaitRuntime.queue` 唯一 bounded factory；await-put backpressure 与原 typed `HostApiError` propagation；terminal-only queue 不受影响 |
| `tests/service/test_entrypoint_runtime_prompt_path.py` | prompt live thinking、final answer、watch failure fallback |
| `tests/service/test_entrypoint_runtime_interactive_path.py` | interactive 多轮、terminal fence、detach/close |
| `tests/cli/test_thinking_renderer.py` | runtime sequence、dedupe、runtime 切换、stderr 与 close |
| `tests/cli/test_prompt_command.py` | `--thinking`/`--no-thinking`、stdout final、stderr thinking、无重复 |
| `tests/cli/test_interactive_command.py` | 多轮 thinking/final、Ctrl+C cancel、renderer close |
| `tests/cli/test_runtime_display.py` | activity/detail 与 thinking 协调、terminal cleanup |
| `tests/cli/test_transient_slow_consumer_path.py`（新增） | 真实 Host → Service bounded relay → CLI renderer 慢消费者链；typed overflow 后 Outbox terminal/final 一次收口且无死锁 |

实施时若签名变化触及其它强类型 fake/fixture，只更新直接调用点，不把兼容 default/wrapper 加回生产代码；新增直接受影响文件必须在 slice diff 和验证报告中列明。

## 7. Implementation slices

### Slice 1：端到端 Host-owned transient contract 与 CLI live thinking 迁移

语义闭环：一次提交完成 Host public contract、validated publish、runtime fanout、public watch union、Service reasoning projection 和 CLI identity 迁移，同时移除 reasoning durable row。完成后，真实 prompt/interactive 路径既能看到 live thinking，又不会写 delta row 或重复 final/activity。

切分理由：不能把“删除 reasoning durable row”和“CLI 接入 transient reasoning”分成两个可接受 production commit；前者先落地会直接丢失 `--thinking`，后者先落地会让同一 reasoning 事实同时存在于 durable row 与 transient delivery，形成可被未来消费者重新采用的第二路径。这一跨层改动虽涉及多个文件，但只实现一条因果链，review boundary 是一个 public contract，不是按模块机械合并。

前置条件：本 plan-fix 经原 reviewers re-review 通过，且 `docs/host/design.md` 的契约未被否决。实现范围为 6.1 全部生产文件，以及 owner contract/主路径所需的对应单元与集成测试。

#### Slice 1 内部 implementation sub-step（一个原子 accepted slice）

以下 S1-A / S1-B / S1-C 只是在同一次 implementation 与同一次 review boundary 内降低上下文负担的有序 handoff，不是三个 production slices。任一 sub-step 完成后都不得创建 accepted commit、不得交付/部署、不得把暂时同时存在的 reasoning durable/transient 路径声明为受支持 contract；只有 S1-C 完成且 Slice 1 全部 acceptance 通过后，才能进入本 slice code review。sub-step 中间状态不得新增 feature flag、optional fallback、兼容 wrapper、旧 DTO re-export 或运行期双路选择分支。

##### S1-A：建立 Host public contract、hub/publisher/subscription、composition 与 watcher union

实施动作：

1. 在 `dayu.host.api` 建立三类 public payload、`HostTransientDelta` 与 `HostSessionEvent`，在 `dayu.host.transient_delta` 建立 candidate、publisher、hub 与 subscription。
2. 由 `open_host` 唯一 composition root 创建 hub并显式接到 scheduler/ingestor 与 `_PublicHostHandle`；ingest validation transaction 成功后把三类 typed candidate 发布到 hub。
3. 把 `watch_session_events` 改为 attach-before-return 的 closable union iterator，完成双域 merge、terminal fence、cursor typed failure 与所有 cleanup；此步不切换 Service/CLI consumer，也不删除 reasoning durable projection。

handoff invariant：Host runtime 已成为 transient identity/fanout/overflow 的唯一 owner，EventLog 仍拥有 durable cursor；同 runtime 多 watcher 得到相同 envelope identity。为了让 implementation 按序可验证，旧 reasoning `PREVIEW` row 在本地 worktree 可暂时仍存在，但这只是未接受的迁移中间态：不得 commit/accept/deploy，不得新增任何 consumer 或 compatibility branch，也不得声称 reasoning 已达到单 owner/zero-row 成功信号。

逐步验证点：

- `tests/host/test_transient_delta.py` 证明三类 payload mapping、同 runtime 多 watcher fanout、sequence/dedupe、overflow/detach/close。
- `tests/host/test_engine_ingest_mapping.py` 的 recording publisher 对三类 valid delta 各收到一次，invalid/stale/late/rollback 为 0；该 sub-step 的 reasoning durable row 暂存断言只用于标记未完成迁移，不进入最终 acceptance。
- `tests/host/test_watch_session_events.py` 证明 attach 返回点、union typed merge、同步 `HostClosedError`、首次 `__anext__` missing/durable public error，以及 failure/cancel/started/never-started close 均 detach。

##### S1-B：Service/CLI 切换到 transient reasoning identity 与唯一 bounded relay

实施动作：

1. Service 对 `HostSessionEvent` 做穷举分支：durable member 只进入 activity/terminal/final projector；transient member 只把 `HostReasoningDelta` 投影为 `EntrypointThinking`，content/tool-call 明确忽略。
2. 用 `_WatchAndWaitRuntime` factory 统一所有 live watcher relay，且只把该 runtime 的 `queue` 设为 capacity 256；保留 `await queue.put`，完整传播 Host typed overflow。terminal-only / 无 watcher / outbox drain queue 不改。
3. CLI renderer 改用 `(runtime_id, runtime_sequence)` 与 `dedupe_key`，不再读取 durable `event_sequence`；`--thinking` / `--no-thinking`、stdout/stderr 与 final/activity owner 不变。

handoff invariant：Service/CLI 已不读取 `HostEvent.thinking`，也不从 raw Engine fields、type string 或 durable sequence 重建 transient identity；bounded relay 的 capacity 与构造只有 `_WatchAndWaitRuntime` factory 一个 owner。reasoning durable row 此时即使仍暂存在未接受 worktree，也已无人消费，仍不得 commit/accept/deploy；S1-C 必须立即删除它，不能把它保留成 fallback 或“审计备用”。

逐步验证点：

- `tests/service/test_entrypoint_runtime.py` 证明 union 分支穷举、仅 reasoning callback、factory-created live queues 为 bounded、terminal-only queue 未被机械修改，以及 `_WatcherFailure.error` 保留原 typed `UNAVAILABLE/slow_consumer`。
- `tests/cli/test_thinking_renderer.py`、`tests/cli/test_prompt_command.py`、`tests/cli/test_interactive_command.py` 证明 runtime identity 排序/去重、runtime 切换、`--thinking` / `--no-thinking`、final stdout 一次与 activity 无重复。
- focused Service/CLI tests 不允许通过 optional `HostEvent.thinking` fallback；旧 thinking projector/sequence 一旦不再被生产 consumer 引用，即进入 S1-C 删除清单。

##### S1-C：删除 reasoning durable row、`HostEvent.thinking` 及 projection/export

实施动作：

1. 从 `_ingest_validated` 删除 `REASONING_DELTA -> PREVIEW`，让三类 delta 全部沿 S1-A 的同一 validated candidate/publish path 返回 `events == ()`。
2. 删除 `HostThinkingView`、`HostEvent.thinking`、`read_api._thinking_from_row`、reasoning preview enum/member、package export 与所有 durable fixture；不兼容读取历史 row，不保留 wrapper/re-export/default。
3. 执行 Slice 1 全部 focused tests、coverage 与 pyright；只以最终单 owner contract 进入 code review。

handoff invariant：reasoning/content/tool-call 三类 delta 的 durable EventLog row 均严格为 0；transient identity/fanout 只归当前 Host runtime，durable fact/cursor 只归 EventLog。Service/CLI 无旧 durable thinking consumer，memory/audit/outbox/trace 无 transient input，且没有中间双路径、compatibility shim 或旧 symbol 留在最终 slice diff。

逐步验证点：

- `tests/host/test_engine_ingest_mapping.py` 对三类 valid delta 同时断言 `ACCEPTED`、`events == ()`、publisher once 与逐类 zero-row；validation/late/rollback 仍为 publisher 0。
- `tests/host/test_host_activity_event_projection.py`、`test_public_event_stream.py`、`test_lifecycle_events.py`、`test_audit_sink.py`、`test_public_host_event.py`、`test_package_exports.py` 证明 durable thinking projection/export 已消失而其它 durable preview/activity 不变。
- 静态 grep 对 `HostPreviewEventType.REASONING_DELTA`、`_EVENT_TYPE_REASONING_DELTA`、`HostThinkingView`、`thinking=_thinking_from_row`、thinking durable `event_sequence` 为零命中。

完成判据：

- 三类 delta 共享同一 typed mapping 和 publish path，EventLog 均不追加 row。
- validation 失败、late/stale/wrong identity 与 transaction exception 的 recording publisher 为 0 calls。
- 两个 attach watcher 收到相同 transient identities；Service 只把 reasoning 交给 CLI。
- `--thinking` 有实时 stderr，`--no-thinking` 无 thinking；final 仅 stdout 一次；activity/detail 无重复。
- owner 模块单文件覆盖率不低于 80%，focused tests 与 pyright 通过。

### Slice 2：adversarial lifecycle/scale 证明与文档收口

语义闭环：在完成的端到端 contract 上验证高量、慢消费者、attach race、detach、terminal、Host close、Ctrl+C 与多轮组合；补齐当前实现 README，并执行全域回归/类型/静态边界检查。

切分理由：这些用例共享 failure-policy/lifecycle 风险，可在稳定 public contract 后独立审阅，不需要再次改变核心语义。它们与 Slice 1 分开可控制 production-high review 上下文，同时不制造半成品运行状态。该 slice 仍按 production-high 做独立 review，不降级为无 review 的“仅测试”尾项。

完成判据：

- 独立 `stress` 用例中每类大量 delta（至少各 1,000 个）后，对三类 event type 的 durable EventLog row 计数都严格为 0；terminal final answer、Run/Attempt terminal 与其它预期 durable facts 正常。该用例不混入默认 pytest 入口。
- 容量 256 的慢 watcher overflow 时，快 watcher 继续、terminal append 正常、Run 不取消、无伪 terminal；错误 detail 精确匹配 contract。
- `tests/host/test_transient_delta.py` 用 deterministic barrier 在本 slice 当前 acceptance 中证明 publish-before-wait、wait-before-publish、drain/clear 与 publish 交界、overflow/close 都不会丢 Event/Queue wakeup；不得把该竞态留到 aggregate deepreview 或 closeout 才首次验证。
- `tests/cli/test_transient_slow_consumer_path.py` 在本 slice 当前 acceptance 中走真实 Host publisher/subscription → Service `_WatchAndWaitRuntime.queue` → CLI thinking renderer：Service relay 先满并阻塞 `await queue.put`，随后 Host subscription overflow；恢复消费后保留 typed `UNAVAILABLE/slow_consumer`，terminal/outbox 同 identity 只展示一次并在测试 timeout 内结束。不得用 fake-only 分层测试替代这条端到端链，也不得推迟到 closeout。
- attach 返回点之后的首个 delta 不丢；attach 之前的 delta 不 replay。
- 同步 closed-handle、首次 `__anext__` missing/durable failure、首次/后续 iteration cancel、iterator error、started 与 never-started `aclose()` 都满足 public typed error与 subscription cleanup；detach、terminal 后续 Session watch、Host close、Ctrl+C 均无 task 泄漏或重复输出。
- 受影响 README 只描述已实现行为；全量 `tests/host tests/service tests/cli`、coverage、pyright、grep 与 diff check 通过。

### Slice 数量与总控符合性

共 **2 个语义闭环 slice**，符合主总控/附加总控默认 2–3 个 slice 的约束。没有按文件/层机械拆分；Slice 1 因“storage removal + replacement live path”必须原子，Slice 2 以 adversarial failure/lifecycle 证据为独立闭环。无需超过 3 个，也不把 README 或单一测试文件拆成独立 production slice。

## 8. 测试矩阵与关键断言

### 8.1 Owner-level contract

- 三个 public payload 的 discriminator/data 错配构造失败；identity/sequence/UTC 校验失败有确定异常。
- `HostEvent` 无 `thinking`、`runtime_id`、`runtime_sequence`；`HostTransientDelta` 无 `event_id`、`event_sequence`、terminal。
- hub 对同一 publish 只分配一次 runtime sequence，多个 watcher 收到完全相同 envelope identity；后 attach watcher不收到历史 delta。
- sequence 从 1 开始单调；dedupe 在同 runtime/execution/worker index 稳定且跨 runtime 不同。

### 8.2 Validation 与 durable 行为

- valid content/reasoning/tool-call ingest：`ACCEPTED`、`events == ()`、publisher 一次、对应 EventLog row 为 0。
- mismatched session/run/current attempt/execution/dispatch record、late after terminal、duplicate terminal rule、transaction rollback：publisher 为 0。
- publish 端口失败被隔离并产生 sanitized diagnostic，不改变 accepted result、Run/Attempt 状态或 EventLog。
- 常规 owner test 用少量三类事件证明逐类 zero-row；独立 `stress` test 用 3 × 1,000 delta 证明放大消失，随后 `RUN_COMPLETED`/final answer 等 durable row、terminal projection 和 outbox intent 按既有 contract 正常。

### 8.3 Concurrency/lifecycle

- watcher A/B attach 后收到相同三类序列，按 type 可穷举选择；detach A 后 B 不受影响。
- 使用 barrier 控制 attach-return 与 publish，证明 attach return 后无丢窗，attach 前不 replay。
- closed handle 在同步 `watch_session_events` 调用处抛 `HostClosedError` 且注册数不变；打开 handle 的 missing Session 在首次 `__anext__` 抛 `HostApiError(NOT_FOUND, retryable=False)`；注入 durable read failure 时仍只出现 Host public `HostApiError` 的既有 code/retryable mapping，不出现 `HostDurableError`、actor/private exception。
- cursor future failure、首次 `__anext__` cancellation、后续 iteration cancellation/error、started `aclose()`、never-started immediate `aclose()` 各自把 subscription count 恢复到 attach 前；同步 attach 中途失败同样回滚，future exception 已观察且无 pending task/warning。
- readiness 使用 deterministic barrier 覆盖 publish-before-wait、wait-before-publish、drain-last-item/clear 与 publish 交界、overflow/close；每种交错都在 timeout 前唤醒且 queue prefix、overflow/closed state 不丢。
- 不消费 slow watcher 并发送 257 个以上 delta：slow watcher 得到指定 `UNAVAILABLE/slow_consumer`，fast watcher 连续接收，EventLog/dispatch 不被阻塞。
- delta 与同 Run terminal 紧邻时，已接受 delta 先于 terminal；terminal 后同 Run delta 不 fanout；watcher 仍可接收下一 Run。
- Host close 唤醒 watcher并正常结束；没有新增 pending task，没有 Run cancel/failed row；close 后新 watch 抛 `HostClosedError`。

### 8.4 Service/CLI

- `_WatchAndWaitRuntime` factory 是 live relay capacity 的唯一 owner；submit、非终态 cancel 与 startup reconnect 创建的 queue 均 `maxsize=256`，terminal-only / 无 watcher / 一次性 Outbox queue 保持原语义。测试不得只数 `asyncio.Queue` 调用点，必须按是否实际承接 watcher items 断言。
- relay 满时 `_drain_host_events` 停在 `await queue.put`，不调用 `put_nowait`、不丢/替换 item；Host iterator 随之暂停，Host subscription 最终 overflow。恢复 relay 消费后 `_WatcherFailure.error` 是原 `HostApiError`，精确保留 `UNAVAILABLE`、`retryable=True` 与 `HostUnavailableDetail(component="session_live_stream", reason_code="slow_consumer")`，Service 不改写为 generic exception。
- watch failure 仍走现有 typed diagnostic/outbox terminal fallback，不把 delta 伪装成 terminal。构造 relay 满、Host overflow 与 durable terminal/outbox 紧邻的受控场景，断言 bounded prefix 后 error 可见、Outbox terminal identity 未丢、Run 不 cancel/fail、等待在 timeout 内收口且 final 只输出一次。
- content/tool-call delta 不触发 thinking、activity 或 final callback；reasoning 每个 dedupe identity 最多回调一次。
- prompt/interactive `--thinking` 将 live reasoning 写 stderr；`--no-thinking` 不写；final answer 只写 stdout 一次。
- runtime sequence 倒序/重复被 renderer 丢弃；换 runtime 可从 1 重新开始。
- Ctrl+C 仍调用显式 Run cancel；watcher detach/renderer close 本身不 cancel Run；终态/异常路径清理 display。

## 9. Required validation 命令

实施 gate 必须先执行：

```bash
source .venv/bin/activate
pytest tests/host/test_transient_delta.py --cov=dayu.host.transient_delta --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py tests/host/test_host_activity_event_projection.py tests/host/test_public_event_stream.py tests/host/test_lifecycle_events.py tests/host/test_audit_sink.py tests/host/test_public_host_event.py tests/host/test_package_exports.py tests/host/test_dispatch_scheduler.py -q
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py -q
pytest tests/cli/test_thinking_renderer.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_runtime_display.py tests/cli/test_transient_slow_consumer_path.py -q
pytest tests/host tests/service tests/cli -q
pytest -o addopts="" -m stress tests/host/test_transient_delta_stress.py -q
pyright
```

除新模块的硬门槛外，focused suite 生成 coverage report 后必须逐行核对 6.1 中每个被修改 Python 文件，单文件覆盖率目标均为 `>= 80%`；低于目标时补 owner-level test，不以总体平均值掩盖单文件缺口。

静态一致性检查：

```bash
rg -n 'HostPreviewEventType\.REASONING_DELTA|_EVENT_TYPE_REASONING_DELTA|HostThinkingView|thinking=_thinking_from_row' dayu/host tests/host
rg -n 'EngineEventType\.(CONTENT_DELTA|REASONING_DELTA|TOOL_CALL_DELTA)' dayu/host/engine_ingest.py
rg -n 'event_sequence.*thinking|EntrypointThinking.*event_sequence|thinking\.event_sequence' dayu/service dayu/cli tests/service tests/cli
rg -n 'EngineEvent|dayu\.engine' dayu/service/entrypoint_runtime.py dayu/cli/thinking.py
git diff --check
git diff --stat
git status --short
```

期望：第 1、3、4 条 grep 为零命中；第 2 条只命中统一 transient classification/projection，不得再有 reasoning durable append；`git diff --check` 为 0；最终 status 不包含 control doc 的本 WU 写入。若仓库基线自身已有失败，必须保存命令、完整失败与 base 对照；不得用 ignore、降级 pyright 或缩减测试范围掩盖。

当前 plan-fix gate 只改文档，因此不运行未来实现测试/pyright；本 gate 只执行 design/code evidence grep、`git diff --check` 和允许写入范围核对。

## 10. README 触发判断

本 plan-fix gate 沿用已读取的根目录、`dayu/`、`dayu/host/` README Agent 更新约束；`dayu/service/README.md` 与 `tests/README.md` 未定义等价章节，按仓库级触发规则和各自现有读者边界判断。README 只能描述当前已实现状态，不能在本 plan-fix gate 提前修改。

- `dayu/host/README.md`：会触发。Host public watch、ingest mapping 与 lifecycle 已改变；实现完成后更新 public contract、zero-row delta、live-only/slow-consumer 边界。
- `dayu/README.md`：会触发。Host→Service 的 public union 与分层装配发生变化；实现完成后更新跨层边界，强调 Service 不读 raw EngineEvent。
- `tests/README.md`：会触发。增加 Host transient owner/concurrency/CLI 路径测试后，按其当前测试职责更新覆盖说明。
- `dayu/service/README.md`：会触发。现文档把 thinking 描述为 durable HostEvent projection，实施后必须改为 `HostTransientDelta` 的 Service projection。
- 根 `README.md`：预计不更新。CLI 命令、参数、默认输出通道、Ctrl+C 和最终用户工作流不变；现有 `--thinking` 用户说明仍成立。若实施发现用户可见行为实际变化，必须停止这一判断并按根 README 约束重新评估。
- Engine README/design：不更新；Engine contract 与用户可见 Engine 行为不变。

## 11. 设计真源修改清单

本 plan/plan-fix gate 修改 `docs/host/design.md`，让实现依赖已冻结 owner/public contract，而不是让代码或测试发明语义：

1. §4.1 固定 durable `HostEvent`、`HostTransientDelta`、`HostSessionEvent` 术语与三类 delta owner。
2. §4.1 固定 envelope/payload 字段、runtime identity/sequence/dedupe 与“不可作为 durable cursor”。
3. §4.1 固定 validation-success 后 publish、同 Run terminal fence、容量 256 overflow、detach/Host close 语义。
4. P10.5/public API 固定 `watch_session_events -> AsyncIterator[HostSessionEvent]`、attach/reconnect/live-only 与 composition root。
5. §10/§10.1 固定 durable/transient 类型分离，删除 durable thinking projection 的设计承诺。
6. §13/§13.4 固定三类 delta 均不进入 EventLog，并更新 ingest 顺序。
7. §16 固定 EventLog/read model/outbox 只拥有 durable member，live watch 只提供当前 runtime transient delivery。
8. plan-fix 补充 watcher readiness 的 level-triggered 无丢唤醒不变量，以及同步 lifecycle gate、首次 `__anext__` cursor typed failure、never-started `aclose()` cleanup 的 public contract。

不修改 `docs/engine/design.md`。直接证据是其 `EngineEvent Stream` 已明确：Engine 只承诺生成器内顺序，不承诺 persistent cursor、multi-client fanout、reconnect/replay 或 EventLog；三个 payload 也已是闭合 typed contract。新增 runtime identity、Host governance 和 fanout 都是 Host 新语义，改 Engine design 会造成 semantic ownership drift。

## 12. 风险、残余风险与 stop conditions

### 12.1 实施风险及控制

- **跨平面 terminal 竞态**：若 merge 只用两个独立 poll/task，会出现 terminal 先于已接受 delta。控制：单 watcher merge 明确 drain-buffer-before-terminal，并以 barrier 测试线性化边界。
- **attach lazy-generator race**：若 subscription 到第一次 `__anext__` 才注册，会丢 attach 后首段。控制：`watch_session_events` 同步 attach-before-return。
- **慢消费者传导**：Service 当前四个 queue 创建点没有表达 owner，机械全部改 bounded 会误伤 terminal-only/outbox path，只改某个调用点又会让其它 watcher path 继续绕开 Host buffer 上界。控制：由 `_WatchAndWaitRuntime` factory 唯一创建实际承接 watcher item 的 capacity-256 relay；terminal-only、无 watcher与一次性 drain queue 不改。`_drain_host_events` 保留 `await queue.put`：Service relay 满 → Host iterator 暂停 → Host subscription 的 `put_nowait` overflow → 原 typed `UNAVAILABLE/slow_consumer` 进入 `_WatcherFailure` → 既有 typed diagnostic/Outbox fallback。Service 不丢弃、吞掉或改写错误，Slice 2 必须证明 terminal/outbox 无丢失、无死锁，EventLog append 不受反压。
- **Event/Queue wakeup 竞态**：edge-trigger `Event.set/clear` 可能在 queue drain/clear 与 publish 交界丢唤醒。控制：subscription readiness 按 queue 非空/overflow/closed 的 level-triggered owner state 派生，state update 后 set、clear 前后 recheck；Slice 2 用四类 barrier 交错作为当前 acceptance，不推迟到 closeout。
- **publish 异常污染 durable path**：控制：publisher 明确 non-throwing，ingestor 在 transaction 成功后调用；异常只进入 sanitized operator diagnostic。
- **兼容 shim 诱惑**：保留 `HostEvent.thinking` 或旧 `event_sequence` 会形成双 owner。控制：同一 slice 删除旧 contract并更新强类型 fake，不加 optional/default/`getattr`。
- **大 delta 内存**：容量按 item 数限制；单个 Engine chunk 仍可能较大。public envelope 共享 immutable payload，不为每 watcher复制正文；单 chunk 大小属于既有 Engine/provider contract，本 WU 不引入截断语义。

### 12.2 已接受的残余风险

- overflow、detach、断线、Host close、崩溃、进程重启后 transient delta 永久丢失；这是 live-only 明确边界，不是数据完整性缺陷。
- 容量 256 是首版内部安全值，缺少真实负载调优数据；未来只能基于观测另开 WU，不在本次暴露 public knob。
- durable progress 与 transient delta 没有可重放总序；只承诺各自内序与同 Run terminal fence。
- 跨进程/跨 Host instance 多 watcher 不可见；未来若需要 broker/replay，必须重新设计 identity、cursor、retention 和权限，不扩展本 hub。

### 12.3 Open questions

没有阻塞当前 code generation 的 open question。所有权、public API、跨 durable/transient ordering 和同-runtime 边界均已由已确认 Goal、Host/Engine design 与代码线性化点收敛。

### 12.4 实施 stop conditions

出现以下任一情况必须停止并回到 design/goal gate，不得局部 fallback：

- 证明 `run_write` 成功返回并不代表 durable identity/late-state validation 已线性化，导致无法定义 publish-after-validation。
- 现有 EventLog polling 与 hub 无法在不创建 unbounded/per-watcher task 的条件下满足同 Run terminal fence。
- 实现要求跨进程、重启/reconnect delta replay，或要求一个同时覆盖 durable/transient 的 cursor。
- Service/CLI 必须消费 raw `EngineEvent` 才能维持用户行为。
- 移除 durable thinking 会改变 memory/audit/recovery/outbox 的真实依赖，而非仅测试夹具的偶然依赖。
- 需要为旧 reasoning row、旧 DTO 或旧 import path 新增 compatibility shim。

## 13. 为何没有过度设计

本方案只增加一个 Host-owned in-memory hub、一个 public union 和三个闭合 payload；复用现有 ingest validation、dispatch 顺序、EventLog polling、Service watcher 与 CLI renderer。它不引入 broker、数据库表、cursor、replay、background fanout task、通用 runtime bus、public tuning profile 或新的 CLI callback 面。固定 bounded queue 与 typed overflow 是防止生产故障所需的最小治理；统一 watch API 避免 durable/transient 两套 attach 协议。两个 slice 以可运行语义闭环切分，没有按文件或架构层拆成半成品。

## 14. Gate 交接约束

本 artifact 只完成 plan-fix gate。下一步只能由 controller 派发原 AgentMiMo / AgentDS 对 accepted findings 做 re-review；未经 re-review 通过、controller 接受 plan 并进入后续 gate，不得开始 implementation、commit、push 或 PR。主/附加 control doc 继续由 phaseflow controller 独占更新，本 WU 的 plan-fix agent 不得修改其状态。每个 slice 都必须遵循 production-high 的 review/validation 要求，且最终 closeout 必须再次核对 success signal、README、pyright、coverage、grep 和 residual risk。
