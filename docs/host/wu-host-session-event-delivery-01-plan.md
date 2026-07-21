# WU-HOST-SESSION-EVENT-DELIVERY-01 Implementation Plan

## 1. Plan status

- WU：`WU-HOST-SESSION-EVENT-DELIVERY-01 Host Session Event Delivery Ownership and Bounded Mailbox`
- 当前 gate：`plan`
- plan 结论：`PASS`。目标、owner、contract、状态机、失败路径和实施依赖均已闭合，没有 blocking open question。
- 实施基线：`HEAD`、`main` 与 `github/main` 均为 `2c02079a82c049b49914be412178006ccd354049`，即当前分支直接基于最新 `main` 代码证据制定本计划。
- 设计真源：`docs/host/design.md`。
- Engine 边界：`docs/engine/design.md`。本 WU 不修改 Engine public contract，也不修改 `dayu/engine/**`。
- 唯一主总控：`docs/host/issues-implementation-control.md`。
- goal confirmation：`docs/reviews/wu-host-session-event-delivery-01-goal-confirmation.md`，结论为 `PASS`。
- 实施切片：4 个，严格按语义闭环、依赖关系和独立失败风险切分，不按文件切分。

## 2. 第一性原理判断与直接证据

### 2.1 动机成立，严重性评估正确

当前问题不是“需要把一个 queue 数字调大”，而是同一个 Session event delivery 事实被 Host 和 Service 两层同时保留、Host attach 生效边界不真实、overflow 被错误投影成 availability、terminal commit 与 promotion 没有同源 causal handoff。若只改容量或 Service fallback，会继续保留双 owner，并在 slow consumer、terminal/promotion race、跨 opener 场景下产生不可证明的顺序和释放行为。因此必须在 Host owner boundary 收口，同时删除 Service event-copy relay。

直接代码证据如下：

1. `dayu/host/api.py:3902` 的 `Host.watch_session_events(...)` 仍是同步 `def`，返回普通 `AsyncIterator[HostSessionEvent]`；`dayu/host/open_host.py:905` 同样是同步 factory。当前 successful return 并不表示 durable cursor attach 已完成。
2. `dayu/host/open_host.py:905-1260` 先同步 `subscribe`，再 `DurableActor.submit(...)` 创建 pending cursor future，首次 `__anext__()` 才真正 await cursor；`_observe_watch_cursor_future(...)` 及 done callback 只是为该延迟附着补 cleanup。这与“successful await return 即生效”冲突。
3. `dayu/host/transient_delta.py` 由模块常量 `_TRANSIENT_WATCH_BUFFER_CAPACITY = 256` 决定每订阅队列，使用 `asyncio.Queue`、`drain_nowait() -> tuple[...]` 和 batch drain；没有唯一 in-flight retained item 计数，也没有 per-Session attach reservation/cap。
4. 同一模块把 `QueueFull` 映射为 `HostApiErrorCode.UNAVAILABLE`、`HostUnavailableDetail(component="session_live_stream", reason_code="slow_consumer")`。这把单订阅 transient continuity 丢失错误归给 Host availability owner，语义 owner 错位。
5. `dayu/service/entrypoint_runtime.py` 另设 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY = 256`，由 `_WatchAndWaitRuntime.queue` 和 `_drain_host_events` task 把 Host event 再复制一次；`_WatcherFailure`、queue item 和 drain task exception 形成第二条 observation 通道。
6. `dayu/host/engine_ingest.py` 的 durable validation 已读取 current Attempt，但 `ValidatedTransientDeltaCandidate` 未携带 `Attempt.started_event_sequence`；publisher 因而无法把同一 validation transaction 的 causal fence 原样交给每订阅 entry。
7. `dayu/host/open_host.py` 当前只轮询 durable page、批量 drain transient，并用 subscription 内 terminal run-id set 做局部 fence；没有跨 opener entry causal fence、multi-page catch-up barrier或 mailbox-empty reconciliation。
8. 当前 terminal producer 存在多条只含 `session_id` 的 promotion 旁路：`dayu/host/admission.py:4587`、`dayu/host/waiting.py:841`、`dayu/host/engine_ingest.py:2779`、`dayu/host/recovery.py:340`、`dayu/host/dispatch.py:1220`。这些路径没有携带本 transaction 的 exact terminal sequence。
9. `dayu/host/durable/run_transition.py` 的 `RunTransitionResult` 只携带 state rows；虽然 terminal transition 在 transaction 内已经拿到 exact Run terminal `EventLogRow`，多数调用方结果却没有把它带出 transaction。`WaitResolutionTransitionResult.run_event` 是现有可复用的正确范式。
10. `dayu/runtime/config_loader.py` 的 `HostRuntimeProfileConfig` 与 strict parser、`dayu/config/host_runtime.json`、`dayu/service/host_assembly.py:816` 的 `OpenHostOptions(...)` 均没有 Session Event Delivery policy。
11. 仓库没有通用 metrics sink/protocol；当前可用的跨模块 observability owner 是结构化 logging。实施不得为本 WU虚构一套跨层 metrics framework，应由 Host delivery owner发出只含低基数 `event/outcome/reason` 的可聚合结构化记录。

### 2.2 路径裁决

冻结路径符合 owner 原则，不需要改走 byte/heap accounting：

- 唯一容量 owner 是 Host Session Event Delivery。
- 容量 contract 只有 retained item 与 per-Session subscription admission；不实现 logical-byte/resident-heap accounting，也不承诺其上界。
- Service 只做唯一 `anext()` 消费和 terminal observation，不再持有第二个 event buffer。
- terminal ordering 由 transaction-local exact sequence、local coordinator 和跨 opener durable causal fence共同闭合，不能由 Service queue、日志顺序或 post-commit latest/max readback补偿。
- 已冻结的无 byte/heap bound 裁决不是开放问题、不是本计划 residual，也不得登记后续 WU。

## 3. 目标、成功信号与非目标

### 3.1 目标

1. 让 Host 成为 Session Event Delivery 的唯一 owner，完整拥有 async attach、admission、per-subscription item-bound mailbox、唯一 counted in-flight、overflow、detach、readiness、durable/transient merge、iterator close 和 Host close release。
2. 建立 unified public closable iterator，`await Host.watch_session_events(...)` successful return 成为真实 activation boundary。
3. 让所有 Session-visible terminal producer在 transaction result 中携带 exact terminal fact，并只通过本 opener 的 `TerminalPostCommitPort` 协调 delivery wake 与 optional promotion。
4. 用 same-validation-transaction causal fence、bounded page catch-up 与 mailbox-empty reconciliation保证跨 opener eventual correctness。
5. 删除 Service event-copy relay，落地 sole consumer、capacity-one exact-five observation slot、generation handshake、精确 cleanup/exception precedence和 delivery-only durable recovery；activity/thinking display callback 只进入 Service 定义、UI 实现并显式拥有的专用串行执行域，不与 Host / `dayu.runtime` 的默认 executor 共享。
6. 把 packaged `512/4` policy 经 runtime config、Service assembly、`OpenHostOptions` 一对一传到 Host，并更新所有真实 construction/call/fake/README 触发面。

### 3.2 成功信号

- public contract、package export、config schema、assembly 和所有真实调用点使用同一 async closable iterator/policy/error类型。
- packaged config 对 `transient_mailbox_max_items == 512`、`max_subscriptions_per_session == 4` 有精确断言；Host required field 无默认值，所有构造点显式传入 typed policy。
- `retained_items = mailbox_items + counted_in_flight` 是唯一 retention 公式；single pop transfer 不减计数，下一次 `anext()` resume 或 cleanup 才释放。
- cap-1/cap/cap+1、并发 attach、detach readmission、different-Session isolation以及 factory cancellation/Host close/partial allocation failure均无 reservation 泄漏。
- delayed cursor、multi-page catch-up、双 opener、empty mailbox reconcile、本地 A/B barrier、terminal producer static/runtime barrier均由 deterministic tests 证明。
- Service exact-five disposition、cleanup double-failure chain、late commit suppression和 sanitized diagnostic逐项精确通过。
- 受影响测试、stress、单文件覆盖率目标、完整 pyright、stale/source scans、`git diff --check` 和 README audit 全部通过。

### 3.3 明确非目标

- 不持久化、重放或断线补放 transient delta。
- 不建立第三 sequence，也不承诺跨 durable/transient domain 的全局总序。
- 不做跨进程 terminal 广播；跨 opener correctness 只依赖 durable DB causal fence/reconciliation。
- no-backpressure 承诺的 owner boundary 是 Host publisher：Host 的 offer 不等待 Service callback、不等待 mailbox capacity；慢 callback 不得暂停 Agent、Engine、terminal commit、promotion 或其它 watcher。
- Service sole consumer 必须等待当前 callback 返回后才调用下一次 `anext()`；因此慢 callback 可以只减速当前 Service consumer，并可能使当前 subscription 按 item-bound policy overflow。不得为了声称端到端“零背压”增加 event-copy relay、drop queue、第二 observation channel、byte quota、Host-global quota或跨 Session quota。
- 不修改 Engine public contract，不修改 `dayu/engine/**` 或 `docs/engine/design.md`。
- 不实施 `WU-CLI-SMOKE-01-R2`。
- 不创建 GitHub Issue，不 commit、不 push、不创建或修改 PR。
- 不修改 `docs/phaseflow-umbrella-optimization-control.md`、design、control或既有 review artifact。
- 不增加 `transient_mailbox_max_bytes`、`delivery_size_bytes`、byte traversal/accounting、`PAYLOAD_BYTES`、oversized/byte-full/cumulative-byte-full测试或 heap safety-margin acceptance。
- 不给 delivery detail 增加恒定 capacity dimension 字段、enum或 metric。

## 4. Semantic owners 与 contract 决策

### 4.1 Owner map

| 语义 | 唯一 owner | 消费者/投影规则 |
|---|---|---|
| public iterator、policy、error code/detail | `dayu.host.api` | `dayu.host.__init__` 只导出同一 symbol；Service/CLI 不重建私有 protocol或别名 |
| attach reservation、mailbox、in-flight、overflow、detach、readiness、local terminal watermark | Host Session Event Delivery (`transient_delta.py` + `open_host.py`) | Engine ingest只 non-blocking publish candidate；Service只 `anext/aclose` |
| transient causal fence真源 | Host Engine-ingest durable validation transaction | 从已验证 current Attempt 的 `started_event_sequence` 产生；publisher与subscription entry只原样复制 |
| exact Run terminal event | `dayu.host.durable.run_transition` transaction result | producer-local immutable result构造 notice；禁止 commit 后 latest/max回读 |
| terminal post-commit contract | `dayu.host.terminal_post_commit` | 只定义 local-only notice与同步 port，不 public export |
| local terminal watermark/promotion顺序 | `open_host` coordinator | 先 delivery watermark/ready，再 optional ordinary promotion；不负责跨 opener correctness |
| runtime policy配置语法 | `dayu.runtime.config_loader` | 层中立 typed view；不得 import Host |
| packaged defaults | `dayu/config/host_runtime.json` | Service assembly一对一构造 Host policy，无 scene/run/UI override |
| target generation、observation result、cleanup precedence | `dayu.service.entrypoint_runtime` | CLI只传 callback/命令输入并消费 terminal result |
| callback / renderer专用执行域与 caller-finally close | Service 定义 typed callback execution port；`dayu.cli.runtime_display` 实现并拥有显式单线程 executor；`dayu.cli.session_execution` 拥有其 lifecycle | 不使用事件循环默认 executor，不保存 HostSessionEvent，不参与 terminal判断或 durable recovery；每个 caller lifecycle 独立创建、串行提交并精确关闭 |

### 4.2 Public contracts

1. `HostSessionEventDeliveryPolicy`：frozen/slots dataclass，只有两个 required 字段：
   - `transient_mailbox_max_items: int`
   - `max_subscriptions_per_session: int`
   两者必须为非 bool 正整数；无默认值。
2. `OpenHostOptions.session_event_delivery_policy`：required typed field，放在任何带默认值字段之前；不得通过 default、factory或兼容 wrapper掩盖遗漏。
3. `HostSessionEventIterator`：public Protocol，精确声明 `__aiter__() -> HostSessionEventIterator`、`__anext__() -> HostSessionEvent`、幂等 `async aclose() -> None`。
4. `Host.watch_session_events(session_id)`：public async factory，返回 `HostSessionEventIterator`。只有 successful await return 后订阅才对调用方生效；factory failure/cancellation 不返回半成品 iterator。
5. delivery overflow：
   - `HostApiErrorCode.DELIVERY_INTERRUPTED = "delivery_interrupted"`
   - `HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW = "transient_mailbox_overflow"`
   - `HostSessionEventDeliveryDetail(reason=...)`
   - `retryable=False`
   - detail 只含 `reason`。
6. admission cap：
   - `HostApiErrorCode.RESOURCE_EXHAUSTED = "resource_exhausted"`
   - `HostSessionEventAdmissionReason.SESSION_SUBSCRIPTION_LIMIT_REACHED = "session_subscription_limit_reached"`
   - `HostSessionEventAdmissionDetail(reason=...)`
   - `retryable=True`
7. `HostApiErrorDetail` 把两个新 detail纳入同一 closed union；不删除真正 availability 场景仍使用的 `HostUnavailableDetail`，只删除 delivery overflow 对它的复用。
8. `TerminalPostCommitNotice` 是 Host-internal frozen/slots contract，字段严格只有：
   - `session_id: str`：非空。
   - `terminal_event_sequence: int`：非 bool 正整数。
   - `wake_queue_promotion: bool`：严格 bool。
9. `TerminalPostCommitPort.notify_terminal_post_commit(notice) -> None` 是同步 local-only Protocol；不 export、不保存 durable state、不提供只含 `session_id` 的 overload。

### 4.3 Host subscription/resource 状态机

```text
UNRESERVED
  -- owner-loop reserve, count < cap --> RESERVED
  -- owner-loop reserve, count == cap --> admission error (no allocation)

RESERVED
  -- cursor transaction success + owner-loop no-await register --> ATTACHED
  -- factory cancel/failure/Host close/allocation failure --> DETACHED + release once

ATTACHED
  -- prospective retained_items + 1 <= item cap --> offer accepted
  -- prospective retained_items + 1 > item cap --> OVERFLOWED
  -- aclose/iterator error/EOF/Host close --> DETACHED

OVERFLOWED
  -- remove from fanout immediately; drain accepted prefix/in-flight --> delivery error
  -- error observed or aclose/Host close --> DETACHED + release once

DETACHED
  -- terminal state; mailbox/in-flight/reference cleared; reservation released once
```

不变量：

- `retained_items = mailbox_items + (1 if in_flight is not None else 0)`。
- pop 只做 `mailbox head -> in_flight` transfer，不降低 retained count；下一次 `anext()` 进入、iterator cleanup或Host close才释放旧 in-flight。
- prospective check 严格为 `retained_items + 1 > transient_mailbox_max_items`。
- overflow event 本身不入队；已接受 prefix顺序不变；唯一当前订阅受影响。
- `RESERVED`、`ATTACHED`、`OVERFLOWED` 均占 per-Session reservation；只有 `DETACHED` 释放。
- cap rejection 发生在 mailbox、cursor transaction、iterator、task分配之前。Host subscription不创建 per-watcher background task。
- readiness 是 level-triggered：mailbox非空、overflow、closed、local terminal watermark领先任一条件成立都必须立即返回；clear前后重检 owner state。
- Host close使 iterator正常 EOF并释放全部资源，不写 EventLog、不取消 Run。

### 4.4 Async attach 线性化顺序

1. public lifecycle gate拒绝 closing/closed Host。
2. opener owner loop同步检查并 reserve目标 Session；cap拒绝到此为止，不提交 actor transaction。
3. `await DurableActor.call(session_live_event_start_cursor)` 完成真实 read transaction；caller cancellation虽然不取消已经开始的 durable operation，但factory owner立即幂等释放 reservation，底层完成不得重新激活订阅。
4. 回到 owner loop后，在同一段无 `await` 临界区内完成：重新检查Host/delivery lifecycle、创建 mailbox/subscription/iterator、注册 fanout、捕获该 Session local terminal watermark baseline、把 reservation ownership转交iterator。
5. 完成后才 return。return 后同 actor command 必然排在 cursor transaction 之后。
6. 任一构造/注册步骤失败，按已成功分配的逆序清理并释放同一 reservation token；不保留 pending cursor future/done callback/lazy first-anext attach。

### 4.5 Durable/transient merge 状态机

每个 transient mailbox entry 只包含 public event引用和 internal `durable_causal_fence_event_sequence`，二者合计仍按一个 retained item计数。

`__anext__()` 每轮按下列顺序执行：

1. 释放上一轮已经 resume 的 in-flight item；若当前处于 terminal handoff pause，只释放属于上一轮 transient yield的 item，不触碰尚未 pop 的下一条 mailbox entry。
2. 优先消费已读取但未逐 row处理完的 bounded durable page；durable cursor只在实际处理 row时推进，不使用 terminal marker set/history。
3. 准备 pop mailbox head前，读取该 head fence。若 cursor落后，head保持计数且不 pop，按现有 page limit逐页 catch up，直到达到 fence、读失败或需要 yield一个 durable event。
4. 若 catch-up遇到 Run A terminal，进入唯一 current-terminal fence：只逐项交付 mailbox头部连续的同 Run A prefix；遇到首个 Run B entry时保留 B。随后 yield A terminal并结束本轮 `anext()`；只有下一次 `anext()` 才能重新检查并交付 B。
5. cursor达到 head fence且没有待交付 durable row/terminal时，只 pop一个 mailbox item到唯一 in-flight并 yield；禁止 batch drain、list/tuple/deque transient drain。
6. mailbox空时，唯一 iterator 的当前 `__anext__()` 在同一个调用栈内等待 level readiness，并以 Host-internal bounded reconcile interval 作为这次 readiness wait 的 timeout；只有该 timeout 分支触发一次、且恰好一次最多一页的 bounded durable reconciliation，处理完该页或确认空页后重新进入 readiness wait。不得创建 per-watcher timer/background task，不得在一次 timeout 中循环追多页，也不得复用 wait-resolution poll/idle cadence、Service poll interval或 public delivery policy；持续调用中的后续 timeout 才驱动下一页，因此即使没有本地 notice，也会最终发现共享DB中其它 opener提交的 terminal。Host close必须直接设置同一个 level readiness/closed state并立即打断等待，不等待 interval 到期。
7. local notice只做低延迟hint：coordinator先 `max` advance该 Session delivery watermark并唤醒订阅，再处理promotion；跨 opener正确性不依赖它。

### 4.6 Local terminal coordinator 状态

每个 opener、每个已见 Session只维护两个 O(1) scalar：`delivery_terminal_watermark` 与 `promotion_dedupe_watermark`。

- 每个 notice先令 delivery watermark `max(current, sequence)`，若有advance则level-trigger watcher。
- `wake_queue_promotion=False` 仍执行 delivery watermark/wake，但不改变promotion watermark。
- `wake_queue_promotion=True` 且 `sequence > promotion_dedupe_watermark` 时，先更新promotion watermark，再调用原 ordinary promotion port。
- same-sequence duplicate幂等。
- 较新 `false` 不更新promotion watermark，因此不得吞掉随后到达的较旧 `true`。
- 较新 `true` 可以覆盖较旧 `true`。
- batch notices按 exact sequence顺序逐个提交，不按 Session去重。
- ordinary admission/startup accepted/queued promotion仍直接使用普通 port，不推进delivery watermark。
- coordinator从非 opener thread调用时通过现有 loop bridge同步marshal；callback在owner loop内无 `await` 执行。

构造与关闭 lifecycle 也是该 owner contract 的一部分：

- `HostDispatchScheduler.open` 先构造不可运行、不会启动 critical task、不会暴露给任何 caller 的 scheduler；随后 construction-only typed factory取得其 ordinary promotion capability并创建 opener-local coordinator，non-optional terminal port 只允许在该私有构造阶段完成一次 bind。bind 成功后才允许启动 heartbeat、active-cancel watchdog、dispatch/promotion drain、worker/ingestor等 scheduler-owned producer；禁止临时 no-op port、先运行后替换、public setter或任何 runtime rebind。
- factory/coordinator allocation/bind任一步失败时，heartbeat/watchdog及其它 scheduler critical task必须从未启动；按已分配资源的逆序关闭 coordinator（若已创建）、未启动 scheduler 的 lane/Host-instance resource，再由外层 opener关闭其scheduler store，并且不返回 scheduler或Host handle。
- Host close先关闭 public new-work gate，停止并 await wait-poller / durable actor intake及所有 scheduler-owned terminal producers；`HostDispatchScheduler.close()` 必须取消并 await heartbeat、active-cancel watchdog、dispatch/promotion drain、active worker task/handle与scheduler-owned ingestor，证明之后不会产生新 notice，才允许 close coordinator/terminal port，随后再关闭 Session Event Delivery owner及其 iterators。不得先 close coordinator再让 producer补交 notice。
- coordinator close是 owner-loop barrier：close开始前已经进入 owner loop的 notice必须在正常 watermark-before-promotion顺序下幂等完成；若 notice与closing竞态且已经不能完成本地动作，则只发固定低基数 `event=terminal_notice/outcome=closing/reason=coordinator_closing` operator diagnostic。两种路径都不得创建新subscription、不得把已commit terminal伪装成rollback，也不得从durable state重算notice。close必须 await所有已接纳的in-flight owner-loop调用收口后才返回；close完成后的调用fail closed并使用同一固定diagnostic。

### 4.7 Service observation 状态机

Service内部定义恰好五个 generation-tagged closed-union members，每个都带正整数 `target_generation`：

1. `TARGET_TERMINAL`：terminal identity + result。
2. `DELIVERY_INTERRUPTED`：typed Host delivery error。
3. `ITERATOR_ENDED`。
4. `CALLBACK_FAILED`：callback kind + original failure。
5. `ITERATOR_FAILED`：original iterator failure。

唯一 capacity-one slot由 sole consumer first-commit；consumer task handle只用于 lifecycle await，不得读取 `task.exception()` 取得业务语义。

```text
DETACHED -> ATTACHED_UNBOUND
ATTACHED_UNBOUND -- bind(g, target) --> CONSUMING(g)
CONSUMING(g) -- first commit --> RESULT_READY(g) [pause before next anext]
RESULT_READY(g) -- ack TARGET_TERMINAL(g), clear --> ATTACHED_UNBOUND
ATTACHED_UNBOUND -- bind(g+1, target) --> CONSUMING(g+1)
RESULT_READY(g) -- fatal/helper completion --> STOPPING -> CLOSED
ATTACHED_UNBOUND/CONSUMING(g) -- stop wins empty slot --> STOPPING -> CLOSED
CLOSED -- DELIVERY_INTERRUPTED only --> DEGRADED durable recovery
```

固定 disposition：

- `TARGET_TERMINAL`：cleanup后返回slot中的terminal，不读 durable owner重算。
- `DELIVERY_INTERRUPTED`：cleanup后仅走现有 `get_run/Outbox` recovery；失败时 `raise recovery_error from delivery_error`，不reattach。
- `ITERATOR_ENDED`：cleanup后固定 `EntrypointRuntimeError("session_event_iterator_ended_before_terminal")`，不recovery。
- `CALLBACK_FAILED`：cleanup后原样重抛callback failure。
- `ITERATOR_FAILED`：public `HostApiError/HostClosedError` 原样抛；其它固定 `EntrypointRuntimeError("session_event_iterator_failed_before_terminal") from original`。

固定 cleanup 顺序：先stop并await sole consumer、确认无active `anext()`，再恰好一次 public `aclose()`；slot/cancellation first primary不可被close failure覆盖。terminal或delivery recovery已成功时close failure只触发最多一次去敏 `WATCHER_DIAGNOSTIC`，字段和值严格使用设计冻结值。callback、EOF、public/non-public iterator、delivery recovery、slot-empty、caller cancellation与close的异常链按设计表逐项精确断言。

Callback 仍是快速、同步、非阻塞的 typed callable；Service sole consumer一次只处理一个callback，不复制Host event。Service定义只含 activity/thinking 两个精确 typed invocation 的 callback execution port，CLI `RuntimeDisplayController` 提供 concrete owner：每个 prompt/interactive display lifecycle 显式创建一个 `ThreadPoolExecutor(max_workers=1)`，通过 `loop.run_in_executor(explicit_executor, ...)` 执行 callback、toggle、finish、cancel/local-exit render与最终renderer close。该 executor 不设置为event-loop default，不被 Host、`dayu.runtime`、其它 Session或其它 watcher复用；不新增跨 Session registry/quota。

execution domain在提交前持有 async serial gate，只有取得gate后才向其executor提交工作，因此同一consumer任一时刻至多一个 submitted/in-flight callback，且同一display lifecycle任一时刻至多一个已提交renderer job；consumer await原job完成/抛出后才继续 `anext()`。executor内部不得承载Host event副本、第二observation result、relay/drop queue或delivery retry。callback原异常由consumer提交为 `CALLBACK_FAILED`；execution-domain scheduling/lifecycle failure也沿同一member携带原异常，不增加第六类outcome；renderer close失败只属于CLI caller cleanup，不写Service slot。

caller cancellation先使slot late commit失效，再shield并等待已经提交的callback完成/失败，然后才停止consumer并关闭iterator。专用executor只提供执行域隔离，不承诺安全终止违反快速同步非阻塞contract的无限阻塞任意代码；不得通过限时等待后继续cleanup而把仍运行的thread遗留在renderer/iterator关闭之后。deterministic test必须使用可释放blocking barrier：阻塞期间证明Host publisher、Agent、Engine、terminal commit、promotion和第二watcher继续；释放后严格验证callback、consumer、iterator与renderer cleanup顺序。

## 5. 完整 call-site inventory

本节是实施时的闭集清单。新增或遗漏call site必须先更新owner-level manifest/tests，不能用默认值、`cast`、兼容wrapper或fake特例掩盖。

### 5.1 `OpenHostOptions(...)` 构造点

Production：

- `dayu/service/host_assembly.py:816`

Tests/fixtures：

- `tests/host/public_smoke_support.py`
- `tests/host/test_effective_execution_config.py`
- `tests/host/test_host_activity_event_projection.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_per_run_tool_selection.py`
- `tests/host/test_public_lifecycle_smoke.py`
- `tests/host/test_public_open_host_options.py`
- `tests/host/test_public_retry_replay.py`
- `tests/host/test_public_session_api.py`
- `tests/host/test_storage_maintenance.py`
- `tests/host/test_storage_usage_report.py`
- `tests/host/test_submit_followup_public_contract.py`
- `tests/host/test_watch_session_events.py`

每一处都必须显式构造双字段 policy；不得新增test-only default/helper fallback隐藏required contract。共享fixture helper可以返回一个显式typed policy，但调用链必须仍可由类型检查确认。

### 5.2 `watch_session_events(...)` production与fake/call点

Production定义/调用：

- `dayu/host/api.py`：public async Protocol method。
- `dayu/host/open_host.py`：唯一production implementation。
- `dayu/service/entrypoint_runtime.py:1009`：唯一production direct caller；submit、cancel非终态和startup reconnect均经这一attach helper，必须显式 `await`。
- `dayu/cli/session_execution.py` 不直接调用Host watch，但其submit/cancel/startup路径必须消费更新后的Service async lifecycle并保持renderer finally顺序。

Host integration/smoke callsites，全部改为显式 `await`：

- `tests/host/recovery_support.py`
- `tests/host/test_host_production_stress.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_public_cancel_smoke.py`
- `tests/host/test_public_compact_smoke.py`
- `tests/host/test_public_offline_outbox_smoke.py`
- `tests/host/test_public_open_host_multiturn_smoke.py`
- `tests/host/test_public_real_runner_matrix_smoke.py`
- `tests/host/test_public_tool_wiring_smoke.py`
- `tests/host/test_purge_session.py`
- `tests/host/test_recovery_multiprocess.py`
- `tests/host/test_transient_delta_stress.py`
- `tests/host/test_watch_session_events.py`

Utils public smoke direct callsites，全部调用都必须显式 `await`：

- `utils/smoke_host_public_r03_semantic_ownership.py`
- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`

Service/CLI fake definitions，全部改成 async factory并返回public `HostSessionEventIterator` contract，不自建旧queue语义：

- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- 当前 `tests/cli/test_transient_slow_consumer_path.py` 删除并以 `tests/cli/test_transient_delivery_interruption_path.py` 替代；wrapper对inner factory也必须显式 `await`。

### 5.3 当前 terminal producer qualified-callsite闭集

`tests/host/test_terminal_post_commit.py` 的AST manifest至少冻结下列当前production qualified producers与transition调用；实施后以实际qualified name做精确集合比较：

| module | qualified producer | terminal transition |
|---|---|---|
| `dayu.host.admission` | `_CancelRunOperation._cancel_queued` | `cancel_queued_in_transaction` |
| `dayu.host.admission` | `_CancelRunOperation._cancel_predispatch_starting_or_none` | `cancel_predispatch_starting_in_transaction` |
| `dayu.host.admission` | `_CancelRunOperation._cancel_recovering` | `cancel_recovering_run_in_transaction` |
| `dayu.host.admission` | `_CancelRunOperation._cancel_waiting` | `cancel_waiting_run_in_transaction` |
| `dayu.host.admission` | `_CancelSessionRunsOperation._cancel_queued_target` | `cancel_queued_in_transaction` |
| `dayu.host.admission` | `_CancelSessionRunsOperation._cancel_predispatch_target` | `cancel_predispatch_starting_in_transaction` |
| `dayu.host.admission` | `_CancelSessionRunsOperation._cancel_waiting_target` | `cancel_waiting_run_in_transaction` |
| `dayu.host.admission` | `_CancelSessionRunsOperation._cancel_recovering_target` | `cancel_recovering_run_in_transaction` |
| `dayu.host.admission` | `_CloseoutAttemptTerminalOperation.__call__` | `terminal_closeout_in_transaction` |
| `dayu.host.waiting` | `DefaultHostResolveWaitService._resolve_failed` | `fail_run_from_waiting_in_transaction` |
| `dayu.host.waiting` | `DefaultHostResolveWaitService._resolve_lost` | `mark_run_lost_from_waiting_in_transaction` |
| `dayu.host.waiting` | `_expire_wait_in_transaction` | `fail_run_from_waiting_in_transaction` |
| `dayu.host.engine_ingest` | `EngineEventIngestor._close_terminal` | `terminal_closeout_in_transaction` |
| `dayu.host.engine_ingest` | `EngineEventIngestor._close_host_lifecycle_terminal` | `terminal_closeout_in_transaction` |
| `dayu.host.engine_ingest` | `EngineEventIngestor._close_active_cancel` | `active_cancel_closeout_in_transaction` |
| `dayu.host.engine_ingest` | `EngineEventIngestor._fail_recovering_run` | `fail_recovering_run_in_transaction` |
| `dayu.host.recovery` | `StartupRecoveryScanner._classify_recovering` | `lose_recovering_run_in_transaction` |
| `dayu.host.recovery` | `StartupRecoveryScanner._close_positive_orphan` | `close_startup_orphan_attempt_in_transaction`（只有unrecoverable/lost分支产notice） |
| `dayu.host.dispatch` | `HostDispatchScheduler.tick_active_cancel_watchdog` | `active_cancel_watchdog_closeout_in_transaction` |
| `dayu.host.dispatch` | `HostDispatchScheduler._fail_unstarted_in_transaction` | `fail_unstarted_run_in_transaction` |
| `dayu.host.dispatch` | `HostDispatchScheduler._closeout_worker_startup_timeout` | `terminal_closeout_in_transaction` |

还必须把不重新调用transition的terminal ack/replay纳入runtime producer tests：single-run terminal cancel ack、session-scope各target、waiting同scope replay、Engine accepted duplicate、watchdog replay。它们必须在同一transaction沿Run stable terminal ref读取exact row，notice flag为false，不重放slot release side effect。

manifest冻结的是上述 terminal writer / producer qualified callsite，不以 composition path 为筛选条件。同一个 admission / waiting producer无论由完整 `open_host` opener、wait-poller command handle还是 standalone `create_host_command_handle` 装配，都必须留在同一 static manifest 并执行同一 transaction-result -> exact notice -> terminal port dataflow；`dayu.host.command` 是装配/调用层而不是新增 terminal writer，因此不另造一套 manifest row，也不能以“standalone没有Session Event Delivery runtime”为由排除其下游producer。

standalone `create_host_command_handle` 必须显式注入一个 Host-private、语义固定为“本composition没有local delivery owner”的 no-local-delivery terminal port；它只消费调用而不推进watermark/promotion，不public export、不兼容转发、不承担跨opener correctness，也不能作为完整 opener 构造期的临时 port。`tests/host/test_command_handle.py` 以recording runtime fake替换该private port，证明standalone路径的admission/waiting terminal producer在commit return后仍调用port并携带exact notice。

### 5.4 Promotion bypass审计

当前直接旁路位于 admission、waiting、engine ingest、recovery和dispatch。实施后：

- terminal producer qualified functions内不得出现 `wake_queue_promotion(session_id)`。
- 只允许ordinary non-terminal owner、scheduler bridge自身和`open_host` terminal coordinator调用普通promotion入口。
- recovery accepted/queued reconciliation保留ordinary Session集合；terminal notices另以sequence有序tuple传递，不能共用 `seen_queue_promotion_sessions`。
- initial admission/queued governance、resume dispatch wake、active cancel request/watchdog wake都保持各自非terminal port语义，不伪造terminal watermark。

### 5.5 Config/assembly/CLI/README callsites

- Config owner：`dayu/runtime/config_loader.py` 的 `HostRuntimeProfileConfig`、`_parse_host_runtime_profile`及新strict policy parser；`dayu/config/host_runtime.json` packaged local runtime。
- Assembly owner：`dayu/service/host_assembly.py::_compose_options`。
- Config test fixture：`tests/runtime/test_config_loader.py`、`tests/service/test_host_assembly.py`和手写完整`host_runtime.json`的`tests/service/test_host_admin.py`；三者都必须加入required policy block。其它通过`dataclasses.replace(...)`派生profile的tests/utils沿typed field自然传播，不另造fallback。
- CLI真实Service helper调用：`dayu/cli/session_execution.py` 中startup reconnect、prompt submit/cancel、interactive submit/cancel。
- CLI真实renderer callbacks：`CliActivityRenderer.record`、`CliThinkingRenderer.record`、`InteractiveRunView.activity_sink().record_activity`；改由`RuntimeDisplayController`串行执行域adapter拥有，不直接作为未隔离callback传入。
- README触发审计：`dayu/host/README.md`、`dayu/service/README.md`、`dayu/config/README.md`、`dayu/README.md`、`tests/README.md` 必须更新；根 `README.md` 审计后预期不更新，因为packaged default无需新增用户配置步骤，CLI命令/参数/最终输出工作流不变。若实施实际改变这些用户可见事实，必须停止并重新确认根README触发，而不是静默扩大scope。

## 6. Slice dependency graph 与切分理由

```text
S1 Host resource/attach ownership
  -> S2 causal merge and cross-opener ordering
       -> S3 exact terminal post-commit coordination
            -> S4 Service/CLI observation, integration and documentation
```

使用4个slice而不是3个，原因不是文件数量：

1. S1是reservation/mailbox/in-flight/factory cancellation的资源状态机，失败主要表现为泄漏、超配或错误activation boundary。
2. S2是durable cursor与transient entry两个domain的因果合流状态机，失败主要表现为跨opener漏terminal、B越过A或page boundary丢序。
3. S3是所有terminal producer的transaction-result/local-coordinator/promotion状态机，失败主要表现为producer漏接、exact sequence丢失或promotion bypass。
4. S4是Service capacity-one observation与cleanup异常优先级状态机，失败主要表现为双consumer、late commit、错误recovery或primary被cleanup覆盖；还包含UI执行域隔离，必须结合真实CLI生命周期review。

将S2与S3合并会把“跨opener只靠DB fence”的data-plane correctness和“同opener low-latency/promotion”的control-plane correctness混在同一review上下文；将S3与S4合并则无法独立用static manifest/runtime fake证明Host producer闭集。四者有独立deterministic barrier和失败风险，不能安全压缩。

## 7. Implementation slices

### S1 — Host public contract、async attach与bounded resource ownership

**目标/产出**

建立public iterator/policy/errors、strict runtime config和一对一assembly；把Host delivery改成per-Session reservation + per-subscription single-item mailbox/in-flight owner；让factory successful await return成为唯一activation boundary；删除旧256常量和availability-mapped overflow。

**依赖**

- 仅依赖当前main与冻结design，无前置slice。

**Allowed production/config modules**

- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `dayu/host/transient_delta.py`
- `dayu/host/open_host.py`
- `dayu/runtime/config_loader.py`
- `dayu/config/host_runtime.json`
- `dayu/service/host_assembly.py`
- `dayu/service/entrypoint_runtime.py`：本slice只做async factory与public iterator contract机械传播，使branch保持可类型检查；sole-consumer/relay状态的删除或重写只属于S4。

**Allowed tests/fixtures**

- public/config/owner：`tests/host/test_public_contracts.py`、`tests/host/test_package_exports.py`、`tests/host/test_public_open_host_options.py`、`tests/host/test_transient_delta.py`、`tests/host/test_watch_session_events.py`、`tests/host/test_open_host_runtime.py`、`tests/runtime/test_config_loader.py`、`tests/service/test_host_assembly.py`、`tests/service/test_host_admin.py`。
- 5.1列出的全部`OpenHostOptions` construction files。
- 5.2列出的全部Host direct watch call files与Service/CLI fake files，仅做async/public iterator contract机械传播；旧relay行为测试不在本slice固化。已授权Service/CLI fake的`__aiter__`返回类型精确修复属于原S1机械传播范围，无需扩大scope。

**Allowed utils public smoke callers**

- `utils/smoke_host_public_r03_semantic_ownership.py`
- `utils/smoke_host_public_conversation_memory.py`
- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `utils/smoke_host_public_multiturn.py`
- 上述4个文件只允许把async factory/public iterator contract机械传播到现有direct callsites并显式`await`；不得修改smoke场景、断言、数据流、Service relay或任何其它行为。

**Exact changes/dataflow**

1. 在`api.py`定义4.2全部public类型并更新Host Protocol、`OpenHostOptions` validation、`HostApiErrorDetail`、`__all__`；package root导出完全同一symbols。
2. Config loader增加层中立 `SessionEventDeliveryPolicyConfig`，profile字段required；policy object strict exact fields，missing/extra/bool/zero/negative/float/string全部fail closed。packaged JSON只写`512/4`。
3. Service assembly显式构造`HostSessionEventDeliveryPolicy(...)`；不接受Service override、scene/run/UI输入。
4. `transient_delta.py`以owner-loop数据结构替换`asyncio.Queue(maxsize=256)`和batch drain：reservation token、per-Session subscription set/count、single-item pop、唯一in-flight、prospective retained check、typed overflow、level readiness、exact-once detach/release。
5. overflow时先从fanout移除，保留已接受prefix与in-flight；prefix耗尽后下一次`anext()`抛同一个typed nonretryable delivery error。其它watcher和publisher继续。
6. `open_host.py`实现4.4 async attach；删除pending cursor future、done callback、lazy generator attach和private closable protocol。iterator implementation精确满足public protocol并幂等close。
7. Host close先关闭public new-work/attach gate，再停止并drain可能publish/commit的既有producer owner，之后关闭delivery owner并正常唤醒/结束iterators；factory/close race由reservation token幂等收口。S1测试只冻结“producer停止后才close delivery”与reservation release；S3在二者之间插入coordinator in-flight drain/port close，不得把delivery close重新提前。
8. 所有真实watch调用和fake改为`await`，fake返回实现public `__aiter__/__anext__/aclose`的iterator；禁止`cast`到Service私有closable protocol。4个utils direct callers只执行上一段授权的机械传播。对`entrypoint_runtime.py`，S1只允许：导入/传播public `HostSessionEventIterator`类型；删除被public类型取代的private closable Protocol与`cast`；把`_attach_watcher`、`_create_watch_and_wait_runtime`及其直接caller机械改为async/`await`；为public iterator传播所必需的`watcher` annotation可机械替换。除这几处外不得改控制流、错误处理、queue或task lifecycle。
9. `entrypoint_runtime.py` 的S1冻结清单如下，全部留到S4：不得删除、改写或重构`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`、`_WatcherFailure`、`_WatcherQueueItem`、`_WatchAndWaitRuntime.queue`、`_WatchAndWaitRuntime.drain_task`、`_drain_host_events`、`_close_watch_and_wait_runtime`、`_drain_available_watcher_items`、`_drain_available_startup_terminal_items`；`asyncio.Queue(maxsize=_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY)` allocation与`asyncio.create_task(_drain_host_events(...))`创建语句必须保持原relay语义。S1测试只断言async/public iterator传播与类型正确，不新增或固化relay行为断言。
10. Host owner发出结构化low-card observability记录：`event`只允许`attach/detach/overflow`，`outcome/reason`只允许closed enum值；不记录payload、Session/Run identity、item count、capacity dimension或byte字段。

**Failure/release paths**

- lifecycle reject和cap reject不分配resource。
- cursor read missing Session/HostApiError、factory cancellation、Host close、subscription/iterator构造失败都释放reservation一次。
- `aclose`、consumer cancel、overflow error observed、iterator内部error、normal EOF、Host close都清空mailbox/in-flight并释放reservation一次。
- `RESOURCE_EXHAUSTED`不驱逐既有订阅；detach完成后才可readmit。

**Tests/assertions**

- policy两个required字段和bool拒绝；packaged exact `512/4`；Host constructor missing field直接失败。
- retained `511 -> next accepted`，retained `512 -> next rejected/not enqueued`；yield后的in-flight仍计数，publisher refill不越界；无batch drain symbol/shape。
- overflow accepted prefix完整有序，detail只含reason，cleanup后reservation释放；快watcher、terminal/promotion/producer不被慢watcher阻塞。
- cap-1/cap/cap+1、并发attach线性化、拒绝前零mailbox/cursor transaction/task allocation、existing watcher不变、detach readmission、different-Session isolation。
- delayed cursor：transaction阻塞时factory不return；cursor完成到return间的durable commit可见；factory cancellation、Host close、partial allocation failure精确释放；return后同actor command排序在cursor后。
- Host close iterator EOF与closed Host新attach错误。
- low-card日志没有identity/payload/capacity dimension。

**Non-goals**

- 本slice不实现causal fence/multi-page merge、不接terminal producer port、不重写Service exact-five。
- 本slice不删除、不简化、不“顺手迁移”Service relay；S4是上述冻结symbols及queue/drain consumer的唯一语义修改slice。
- 不暂存旧error alias或同步factory compatibility branch。
- 禁止同步compatibility、lazy attach、下游识别或兼容coroutine，以及`cast`/`getattr` shim；caller必须直接消费async factory/public iterator contract。

**Completion/stop conditions**

- focused tests通过，所有调用点可pyright；没有旧256/delivery availability语义。
- 若无法在cursor transaction前完成零分配reservation，停止并修正Host owner边界；不得退回同步/lazy attach。

### S2 — Durable causal fence、bounded merge与跨opener correctness

**目标/产出**

从Engine-ingest同一validation transaction产生Attempt start fence，逐subscription entry原样复制；以single-pop前catch-up、same-Run prefix terminal handoff、multi-page与empty-mailbox reconcile闭合本地/跨openerordering，不建立第三sequence。

**依赖**

- S1 public iterator、resource state和single-pop mailbox完成。

**Allowed production modules**

- `dayu/host/engine_ingest.py`
- `dayu/host/transient_delta.py`
- `dayu/host/open_host.py`
- 不修改`dayu/host/read_api.py`：复用现有`session_live_event_start_cursor`和page size 64的`read_session_host_events_after`，用测试数据跨过多页。

**Allowed tests**

- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_local_proxy_engine_ingest.py`
- `tests/host/test_transient_delta.py`
- `tests/host/test_watch_session_events.py`
- `tests/host/test_open_host_runtime.py`
- `tests/host/test_host_production_stress.py`
- `tests/host/test_transient_delta_stress.py`

双opener fixture只能直接写在`tests/host/test_watch_session_events.py`；本slice未授权其它fixture或support file。若实现证据证明必须修改其它fixture或support file，立即触发stop condition并回到plan gate明确文件与owner，不得在S2临时扩scope。

**Exact changes/dataflow**

1. `_ValidatedCandidate`已拥有current Attempt；`_validated_transient_delta_candidate(...)`从该row读取严格非bool正整数`started_event_sequence`，写入`ValidatedTransientDeltaCandidate.durable_causal_fence_event_sequence`。
2. rollback、stale identity、late terminal、rejected candidate不得publish；publisher异常仍与durable ingest隔离，只记录无正文operator diagnostic。
3. publisher对fanout snapshot中的每个subscription构造独立entry，event与fence原样复制；entry整体算一个retained item。
4. 删除subscription terminal run-id set和任何从event顺序反推fence的逻辑；实现4.5 merge状态机。
5. bounded durable page可以作为iterator当前page状态，但不复制transient batch；逐row处理并推进cursor。page size只限制单次读取/内存，不是catch-up correctness budget。
6. current terminal fence最多一个：在terminal yield前逐次交付mailbox头部same-Run prefix，保留首个different-Run entry；terminal yield天然暂停到下一次`anext()`。
7. mailbox空时只由sole iterator当前`__anext__()`的readiness wait timeout分支驱动reconcile：interval是Host-internal有界常量，不进入public policy，不复用wait-resolution cadence、Service poll interval或其它runtime timer；每次timeout只读取/处理一页现有page-limit的durable rows，随后重新等待，下一次timeout才允许下一页。不得创建per-watcher task、timer loop或subscription background task。本地watermark hook在本slice定义owner接口/状态，S3 coordinator接线，跨opener测试不得调用该hook；Host close直接唤醒closed readiness并立即终止wait，不等待timeout。
8. 不把fence/public cursor/internal watermark投影到public delta、trace、memory、prompt、schema或日志。

**Failure/release paths**

- durable read/projection failure作为iterator failure传播，并由iterator finally detach/release；不drop head继续。
- catch-up期间caller cancel/close保留retained accounting到cleanup，随后一次释放。
- Host close通过同一个可控readiness barrier立即唤醒reconcile wait并正常EOF，不留下timer/task；subscription本身仍无background task，测试不得靠缩短真实sleep掩盖关闭延迟。

**Tests/assertions**

- validation transaction读取的Attempt start sequence与candidate/每entry fence object value完全一致；禁止post-transaction latest/max readback。
- head fence未达时entry不pop且仍计数；跨两个以上durable pages追到fence。
- A same-Run prefix逐项先于A terminal；首个B entry保留到terminal后的下一次`anext()`。
- 在`tests/host/test_watch_session_events.py`内直接构造最小concurrent dual-opener fixture：两个独立`open_host` context使用各自的Host handle、scheduler、durable actor/store、Session Event Delivery owner、worker factory与lifecycle，但`OpenHostOptions.db_path`和`lane_db_path`显式指向同一Host DB/lane DB；不共享in-memory hub、coordinator、worker handle或local notice port。opener A先进入，opener C后进入；watcher与B属于C，A terminal只由A提交。测试先在C的empty-mailbox readiness处建立“local terminal watermark未advance/本地hook调用数为零”的no-local-notice barrier，再让A commit，并保持C reconcile clock未推进，证明C没有因A的local action被唤醒；随后逐次推进可控clock跨过page boundaries，B fence迫使C多页catch-up先交付A terminal并保留B。cleanup固定为：先cancel/await未完成的`anext()`并`aclose()` C watcher，再退出opener C context，最后退出opener A context；各自worker/task/resource只能由所属context关闭。
- mailbox空、无local notice的独立用例使用同一个可注入Host-internal clock/readiness barrier：A提交terminal后，C每次只推进一个interval并断言每轮最多读取一页，最终交付跨opener terminal；另在interval尚未推进时发起Host C close，断言close立即打断wait并按正常EOF收口。
- ordinary durable events逐row顺序、cursor实际处理语义、read failure cleanup。
- transient stress仍为0 EventLog rows，fast watcher完整；slow watcher只在Host item cap处中断。

**Non-goals**

- 不在本slice改terminal producer/promotion port；local notice只是未接线hook。
- 不承诺durable/transient全局总序，不持久化fence或delta。

**Completion/stop conditions**

- local/cross-opener deterministic barriers通过，任何B越过A、head提前pop或空mailbox无法eventual reconcile都阻止进入S3。
- 双opener测试若不能完全在`tests/host/test_watch_session_events.py`以内用两个独立context和共享DB/lane DB options完成，停止S2并回到plan gate；不得新增或修改未列明support fixture。
- 若fence不能从同一validation transaction的Attempt row取得，必须修validation owner；禁止用Run、latest EventLog或timestamp替代。

### S3 — Exact terminal post-commit contract、全生产者接线与promotion barrier

**目标/产出**

建立local-only notice/port；让所有terminal transition返回exact Run event，让每个producer-local transaction result携带notice并在commit后只调用terminal port；open_host coordinator按watermark-before-promotion顺序处理；用static manifest + runtime fake + local A/B barriers封闭producer/promotion旁路。

**依赖**

- S2已提供delivery watermark readiness与causal merge。

**Allowed production modules**

- 新增 `dayu/host/terminal_post_commit.py`（只定义Notice与Port）。
- `dayu/host/durable/run_transition.py`
- `dayu/host/admission.py`
- `dayu/host/waiting.py`
- `dayu/host/recovery.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/dispatch.py`
- `dayu/host/command.py`
- `dayu/host/open_host.py`

**Allowed tests**

- 新增 `tests/host/test_terminal_post_commit.py`。
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_admission_queue.py`
- `tests/host/test_admission_multiprocess.py`
- `tests/host/test_public_cancel_session_runs.py`
- `tests/host/test_resolve_wait_command.py`
- `tests/host/test_wait_expiry_closeout.py`
- `tests/host/test_wait_cancel_late_result.py`
- `tests/host/test_wait_callback.py`
- `tests/host/test_wait_adapter_polling.py`
- `tests/host/test_wait_poller_runtime.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/host/test_recovery_scan.py`
- `tests/host/test_recovery_dispatch.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_local_proxy_engine_ingest.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_command_handle.py`
- `tests/host/test_open_host_runtime.py`

**Exact changes/dataflow**

1. `terminal_post_commit.py`严格只定义4.2 notice/port及中文docstring/validation，不package export。
2. 给`RunTransitionResult`增加required `run_event: EventLogRow | None`：所有transition调用点显式填充；写Run event时返回该exact row，无Run event时显式`None`。terminal replay在同一transaction沿`RunRow.terminal_event_id/sequence`稳定ref读回并校验exact row，禁止commit后回读。
3. `WaitResolutionTransitionResult.run_event`继续作为waiting source of truth；expiry/replay/no-op必须同样返回或确认exact terminal row。
4. Producer-local immutable result分别携带`TerminalPostCommitNotice`、可选notice或按`terminal_event_sequence`排序的tuple。notice构造只使用transaction result中的exact `run_event`与同源Run session。
5. Flag规则固定：
   - true：single-run pre-dispatch/waiting/recovering cancel、通用active closeout、首次waiting failed/lost/expiry、Engine首次terminal/worker lost、watchdog首次closeout、worker startup closeout、startup recovery首次terminal且新释放active slot。
   - false：queued cancel、terminal ack/replay/duplicate、session-scope all-target closure notices、attempt-free accepted/queued failure、任何没有新释放active slot的terminal确认。
   - nonterminal resume/recovering/dispatch-ready/active cancel request无notice。
6. admission/waiting/engine ingest删除`_promote_after_release`、`queue_promotion_session_id`、`_with_terminal_promotion_retry`等terminal旁路；同时删除`CancelRunResult/TerminalCloseoutResult`中的terminal-derived `PromotionResult`和`EngineIngestResult.promotion_triggered`这类重复事实，以notice作为唯一handoff。commit return后先调用terminal port，再做其余public projection/dispatch wake；`terminal_closeout`等真正用于worker stream控制的非重复字段可保留。
7. recovery batch保留ordinary `queue_promotion_sessions`，新增按exact sequence有序`terminal_notices`；不按Session dedupe notices。
8. watchdog batch以notices替代`closed_session_ids`；attempt-free helper改为返回可选notice，并沿`_GovernanceStageResult`及其它包住该transaction的producer-local result向外传递，只有最外层`run_write`成功返回后notify。worker startup timeout的transaction body直接返回可选notice，`run_write`返回后notify。任何transaction内部helper都不得直接调用port。
9. command handle/admission/waiting/dispatch/recovery/Engine ingestor的production constructors显式获得同一opener terminal port。static manifest只按terminal writer/producer qualified callsite闭集，不按完整opener、wait-poller或standalone composition分类。standalone `create_host_command_handle`没有Session Event Delivery runtime，必须显式注入private no-local-delivery port；该port是standalone composition的最终语义端点，不是临时占位，不public export、不兼容转发、不承担跨opener correctness。terminal producer仍必须调用该port，不得跳过dataflow；runtime recording fake证明standalone admission/waiting路径在commit return后仍消费exact notice。
10. 解决scheduler/coordinator构造环：`HostDispatchScheduler.open`使用一个仅Host-internal、由循环依赖充分理由支持的typed port factory。精确顺序固定为：打开lane/注册Host instance等inert资源 -> 构造不可运行且不外泄的scheduler -> factory取得稳定ordinary promotion capability并创建coordinator -> construction-only private binder完成一次non-optional terminal port bind -> 才启动heartbeat、active-cancel watchdog及任何dispatch/promotion/worker/ingestor critical producer -> return scheduler。任何producer method在bind完成前不可达；禁止临时no-op过渡、默认port、public setter、运行期替换或rebind。
11. factory、coordinator construction或bind失败时，scheduler critical task start count必须为零；按逆序关闭已创建coordinator与scheduler inert资源并撤销Host instance/lane ownership，且不把未绑定scheduler暴露给`open_host` cleanup以外的caller。完整Host close先stop/await wait-poller和durable actor intake，再调用scheduler close停止并await heartbeat、watchdog、dispatch/promotion drains、active worker task/handle、scheduler-owned ingestor等全部terminal producers；之后在owner loop drain/close coordinator/port，再关闭delivery owner。coordinator close按4.6处理in-flight/closing notice，禁止committed terminal回滚投影。
12. `open_host` coordinator实现4.6，并把同一port显式传入execution actor factory、wait poller factory、startup recovery和scheduler-owned ingestor。attach/publish/terminal coordinator均在owner loop无await临界段完成，不能与promotion插队。
13. 结构化metric event扩展为terminal coordinator `event=terminal_notice`、`outcome=delivery_advanced/promotion_woken/duplicate/closing`；closing reason固定为`coordinator_closing`，仍不含identity、sequence值、capacity dimension或payload。

**Failure/release paths**

- transaction rollback/CAS loser/precondition failed不notify；typed idempotent terminal确认带exact sequence但flag false。
- port/coordinator调用发生在commit后；失败不得把已commit terminal伪装成rollback。沿现有Host error路径传播并保留operator diagnostic，下一轮durable reconcile仍能恢复delivery correctness。
- Host close必须先阻止并await所有terminal producer，再关闭coordinator/port。close barrier前已进入owner loop的notice按正常顺序幂等完成；closing竞态中无法完成local动作的notice只发固定低基数diagnostic并fail closed，不新建subscription、不调用已关闭promotion、不把durable commit伪装成rollback；durable reconcile仍是最终correctness source。

**Tests/assertions**

- Notice constructor exact validation；模块不public export、不依赖Service/UI。
- AST qualified-callsite manifest与5.3闭集精确相等；新增terminal writer未登记即失败。
- 第二manifest冻结ordinary direct promotion allowlist；terminal producer内出现直接promotion立即失败。
- runtime fake逐producer证明`run_write`返回后消费exact notice，再进local coordinator；flag true也无旁路。
- standalone `create_host_command_handle` runtime recording fake证明其装配的admission/waiting producer仍调用显式private no-local-delivery port；static manifest集合与完整opener装配无关，standalone不是排除理由。
- coordinator owner-loop marshal、watermark-before-promotion、false delivery wake、ordinary promotion不推进watermark、same-sequence幂等、新er false不吞older true、新er true覆盖older true、batch不按Session丢sequence。
- scheduler factory/bind failure barrier断言heartbeat/watchdog/dispatch/promotion/worker/ingestor task从未启动、coordinator与lane/instance资源各关闭一次、未绑定scheduler从未return；source/AST断言不存在临时no-op过渡、runtime setter或rebind路径。
- Host close ordering recorder断言wait-poller/actor intake停止后，scheduler-owned heartbeat/watchdog/drain/active worker/ingestor全部stop并await，随后才调用coordinator close与delivery owner close；用owner-loop barrier冻结一条已接纳notice，close必须等待其正常幂等完成，另覆盖closing race固定diagnostic且不产生subscription/promotion/rollback。
- local A/B barriers至少覆盖：pre-dispatch cancel A + queued B、wait failed A + queued B、wait expiry A + queued B。冻结watcher并记录transaction-local sequence；A notice/wake/catch-up/A-prefix/A-terminal必须早于promotion后的B entry，B只能在Service ack/rebind后的下一次`anext()`交付。
- Engine terminal、accepted duplicate、worker lost、recovery lost、watchdog、startup timeout、session cancel tuple的exact sequence/flag/order。

**Non-goals**

- AST/port tests不宣称跨opener完整性；该结论只由S2双openerDB barrier证明。
- 不把notice变成public/durable/跨进程广播，不修改Engine public contract。

**Completion/stop conditions**

- static manifest、runtime fakes与三组local barrier全部通过，production terminal producer无直接promotion。
- 任一producer拿不到transaction-local exact terminal row时，必须回到`run_transition` owner补齐结果；禁止post-commit latest/max、日志解析或Run status推断。

### S4 — Service exact-five sole consumer、CLI执行域、全链验收与README

**目标/产出**

删除Service relay，落地capacity-one generation state machine和精确cleanup/disposition；让CLI renderer走由UI明确拥有、与Host/`dayu.runtime`默认executor隔离的专用串行callback execution domain，不阻塞Host loop或建立event-copy relay；更新全部fakes、E2E、stress和README，完成最终gate验证。

**依赖**

- S1-S3全部完成。

**Allowed production modules**

- `dayu/service/entrypoint_runtime.py`
- `dayu/cli/session_execution.py`
- `dayu/cli/runtime_display.py`
- `dayu/cli/activity.py`、`dayu/cli/thinking.py`、`dayu/cli/run_view.py`：只允许为`RuntimeDisplayController`串行锁/typed adapter补必要的线程安全入口，不得复制Host/Service observation状态。

**Allowed tests**

- `tests/service/test_entrypoint_runtime.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- 新增 `tests/cli/test_transient_delivery_interruption_path.py`，删除旧 `tests/cli/test_transient_slow_consumer_path.py`。
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_runtime_display.py`
- `tests/cli/test_activity_renderer.py`
- `tests/cli/test_interactive_run_view.py`
- `tests/cli/test_thinking_renderer.py`
- S1-S3列出的所有Host/runtime/service测试与5.2传播callsite files，用于最终integration回归。

**Allowed README modules**

- `dayu/host/README.md`
- `dayu/service/README.md`
- `dayu/config/README.md`
- `dayu/README.md`
- `tests/README.md`
- 根`README.md`仅按5.5条件审计，预期不修改。

**Exact changes/dataflow**

1. 删除`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`、Service private closable Protocol/cast、`_WatcherFailure`、queue item alias、`_WatchAndWaitRuntime.queue/drain_task`、`_drain_host_events`及所有queue drain consumer。
2. 定义exact-five internal closed union、capacity-one slot和显式observation state owner；只允许sole consumer调用`anext()`。
3. submit：先await attach并创建consumer，保持UNBOUND；再submit；accepted id返回后bind generation，随后`on_run_accepted`。submit failure/取消不从event猜target。
4. cancel：初始snapshot terminal则不attach，直接durable result；非terminal先attach+consumer+bind，再cancel。cancel error后重读若已terminal走durable recovery，否则原样传播。
5. startup：先attach+consumer，再Outbox/session snapshot/probe；每个target按generation bind，TARGET_TERMINAL first-commit后pause，coordinator ack-clear再bind下一target。无target不`anext()`，不建live cache。
6. 实现4.7五类disposition、stop arbitration、fatal sticky、only-target ack/reuse、seen terminal identity dedupe和全部double-failure chain。
7. Service定义`EntrypointCallbackExecutionPort`，只含精确typed的`invoke_activity(callback, activity)`与`invoke_thinking(callback, thinking)` async方法；有activity/thinking callback时该port是required显式参数，无callback时不创建execution domain。`_invoke_callback`只调用该port并shield当前job；callback或domain scheduling异常转换为`CALLBACK_FAILED`并保留原异常。consumer在当前job完成/失败前不再调用`anext()`；async serial gate在提交executor前取得，保证同一consumer最多一个submitted/in-flight callback，不建Host event queue、result future side channel或第二observation channel。`on_run_accepted`只是event-loop内的target binding通知，不是display callback，不进入该executor。
8. `RuntimeDisplayController`作为CLI concrete owner，每个prompt/interactive display lifecycle创建一个私有`ThreadPoolExecutor(max_workers=1)`和一个event-loop async serial gate，并实现上述port；所有activity/thinking recorder、toggle、finish、cancel/local-exit render与最终renderer close只通过`loop.run_in_executor(explicit_executor, ...)`进入该线程。不得调用或替换event-loop default executor，不共享给Host、`dayu.runtime`、其它Session/watcher，不引入executor registry、Host-global或跨Session quota；executor work item不保存`HostSessionEvent`或Service outcome。
9. `dayu.cli.session_execution`是该controller/executor与renderer的唯一caller lifecycle owner。唯一`finally` close flow固定为：在event loop标记controller closing并拒绝新display work -> 等待已取得serial gate或已submitted的当前callback/renderer job完成 -> 在同一explicit executor串行提交renderer close并await -> job返回event loop后shutdown该executor -> 再释放monitor、runtime-line guard、renderer handle等caller-local resource。取消、local-exit、terminal和异常路径不得直接调用底层renderer `close()`，只可提交非terminal finish/cancel render work，最终都进入同一`aclose()`；renderer close恰好一次。
10. 专用executor只做隔离，不改变“callback必须快速、同步、非阻塞”的contract，也不保证终止无限阻塞第三方代码。outer cancellation使late slot commit失效后，仍必须等待已开始job真实结束再cleanup；禁止限时放弃仍运行thread后关闭iterator/renderer。blocking renderer deterministic test使用可释放barrier证明：阻塞期间当前Service consumer只减速自身、当前subscription可按Host item cap overflow，但Host publish、Agent/Engine terminal commit、promotion与第二watcher继续；释放后callback -> consumer stop -> iterator close -> renderer close -> caller-local release严格有序。
11. 替换旧CLI slow-consumer测试：真实Host→Service→CLI路径断言typed `DELIVERY_INTERRUPTED/TRANSIENT_MAILBOX_OVERFLOW` identity原样进入Service，Service只执行一次durable recovery，CLI terminal只展示一次；不再断言Service relay容量或availability detail。
12. Fakes实现async factory/public iterator与typed callback execution port，使用deterministic events/barriers和capacity-one result；不得用无界queue、task exception、同步factory、事件循环default executor或availability-mapped overflow固化旧行为。
13. README只记录实施后的当前事实：Host item-bound mailbox + per-Session cap、packaged `512/4`、不承诺logical bytes/resident heap；Service sole consumer/exact delivery interruption recovery；config schema；UI→Service→Host边界；测试命令。不得写plan/历史迁移/file ledger。

**Failure/release paths与精确tests**

- callback + close、EOF + close、public iterator + close、non-public iterator + close、terminal + close、delivery recovery success/failure + close、slot-empty + close、caller cancellation + close逐项断言top-level/cause chain。
- terminal/恢复成功+close failure仍返回同一terminal，最多一次固定sanitized diagnostic；diagnostic callback failure吞掉。
- no active `anext()` before `aclose()`；`aclose()`恰好一次；Host reservation最终释放。
- old generation晚到terminal/callback/failure/EOF不能写新slot；stop先赢empty slot后late commit失败。
- attach失败不submit；submit command位于cursor之后；startup不预读B；delivery interruption不reattach、不标记Host outage。
- callback execution domain创建失败发生在Host attach/submit前并原样传播；callback job异常进入`CALLBACK_FAILED`，executor scheduling失败也使用同一member；renderer close/executor shutdown异常不写Service slot，由CLI caller lifecycle处理。
- caller-finally ordering test记录`callback_started -> close_requested -> callback_released -> callback_finished -> renderer_close_started -> renderer_close_finished -> executor_shutdown -> caller_local_release`；close不能越过current callback。正常terminal return等无异常路径发生close failure时，该failure原样为top-level；已有callback/cancellation/其它异常primary时保留同一primary identity并把close failure作为cause，随后仍尝试executor与caller-local cleanup；断言renderer/executor恰好关闭一次。
- UI阻塞隔离、toggle/finish/cancel/local-exit/close顺序和renderer failure由CLI owner传播；无UI event queue/Host event copy。慢callback只可能减速当前consumer并触发当前subscription item overflow，不反压Host publisher、Agent、Engine、promotion或第二watcher。

**Non-goals**

- 不更改CLI command参数、最终terminal格式或实施R2 smoke。
- 不把UI执行域变成Service terminal owner，不让renderer queue/future参与observation/recovery。
- 不为慢callback增加relay/drop queue、第二observation channel、byte quota、Host-global/cross-Session quota或“限时后遗留thread”的伪cleanup；无限阻塞callback违反既有contract，必须在测试释放barrier后完成严格cleanup。

**Completion/stop conditions**

- exact-five tests、真实CLI interruption E2E、全部integration/stress、coverage/pyright/scans/README audit通过。
- 若cleanup需要读取task exception或第二future/queue才能判断结果，停止并修正sole-consumer/slot owner；不得恢复relay。

## 8. Test and validation matrix

所有命令先执行：

```bash
source .venv/bin/activate
```

### 8.1 Focused gates

S1：

```bash
pytest tests/host/test_public_contracts.py tests/host/test_package_exports.py tests/host/test_public_open_host_options.py tests/host/test_transient_delta.py tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/service/test_host_admin.py -q
python -m py_compile utils/smoke_host_public_r03_semantic_ownership.py utils/smoke_host_public_conversation_memory.py utils/smoke_host_public_conversation_memory_scenarios.py utils/smoke_host_public_multiturn.py
```

S2：

```bash
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_transient_delta.py tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py -q
```

S3：

```bash
pytest tests/host/test_terminal_post_commit.py tests/host/test_run_attempt_transitions.py tests/host/test_admission_queue.py tests/host/test_public_cancel_session_runs.py tests/host/test_resolve_wait_command.py tests/host/test_wait_expiry_closeout.py tests/host/test_phase7_waiting_integration.py tests/host/test_recovery_scan.py tests/host/test_recovery_dispatch.py tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py tests/host/test_active_cancel_dispatch.py tests/host/test_command_handle.py -q
```

S4：

```bash
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py tests/cli/test_transient_delivery_interruption_path.py tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py tests/cli/test_runtime_display.py tests/cli/test_activity_renderer.py tests/cli/test_interactive_run_view.py tests/cli/test_thinking_renderer.py -q
```

### 8.2 Affected suites与stress

```bash
pytest tests/host tests/runtime tests/service tests/cli -q
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
pytest -o addopts="" -m stress tests/host/test_transient_delta_stress.py -q
```

### 8.3 单文件覆盖率

对每个新增/修改production文件生成term-missing或JSON coverage报告，逐文件检查目标`>=80%`，不能用全包aggregate掩盖单文件缺口。至少对以下核心owner单独使用`--cov=<module> --cov-fail-under=80`运行其focused tests：

```bash
pytest tests/host/test_transient_delta.py tests/host/test_watch_session_events.py --cov=dayu.host.transient_delta --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py --cov=dayu.host.open_host --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/host/test_terminal_post_commit.py --cov=dayu.host.terminal_post_commit --cov-report=term-missing --cov-fail-under=80 -q
pytest tests/service/test_entrypoint_runtime.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing --cov-fail-under=80 -q
```

其余modified production files从affected suite coverage报告逐行检查；低于目标就补owner-contract tests，不以`pragma: no cover`、排除配置或宽泛mock绕过。

上述4个`utils/` public smoke脚本按仓库`AGENTS.md`默认无需新增测试或单文件coverage，但仍必须纳入S1 `py_compile`、完整pyright和source propagation scan。该豁免不降低任何新增/修改production或test文件的coverage acceptance。

### 8.4 Type、diff与source scans

```bash
python -m pyright dayu/ tests/ utils/
git diff --check
```

旧delivery语义scan（限定production/test/README owner路径，避免把design中的删除说明误判为残留）：

```bash
rg -n '_TRANSIENT_WATCH_BUFFER_CAPACITY|_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY|session_live_stream|reason_code="slow_consumer"|transient_mailbox_max_bytes|delivery_size_bytes|cumulative_byte|byte_full|oversized.*mailbox' dayu/host dayu/service dayu/cli tests/host tests/service tests/cli dayu/README.md dayu/host/README.md dayu/service/README.md dayu/config/README.md tests/README.md
```

结果必须为空。`HostUnavailableDetail`本身仍可被真实availability owner使用，不能全仓误删。

source propagation和boundary由tests中的AST manifest做硬gate，并辅以：

```bash
rg -n 'watch_session_events\(' dayu tests utils
rg -n '\.wake_queue_promotion\(' dayu/host
rg -n 'TerminalPostCommit|session_event_delivery' dayu/engine
rg -n 'from dayu\.(engine|host|service|ui|fins)|import dayu\.(engine|host|service|ui|fins)' dayu/runtime
```

人工/AST判定要求：所有caller显式await；terminal producer无promotion bypass；`dayu/engine`无新delivery contract；runtime无反向依赖。

最终scope审计：

```bash
git status --short
git diff --name-only main
git diff --stat main
```

实施阶段只允许本计划各slice列出的production/config/test/README文件；任何design/control/review/umbrella变更都必须视为scope violation并停止。

## 9. README trigger audit decision

| README | 触发 | 计划动作 |
|---|---|---|
| `dayu/host/README.md` | Host public iterator、delivery owner、terminal coordinator变化 | 更新当前contract/架构；写item-bound、per-Session cap、512/4和无byte/heap承诺 |
| `dayu/service/README.md` | 删除relay、exact-five state/cleanup变化 | 更新sole consumer、delivery-only recovery与callback边界 |
| `dayu/config/README.md` | runtime schema/packaged JSON变化 | 更新required双字段及packaged values |
| `dayu/README.md` | UI→Service→Host消费边界/public iterator变化 | 更新当前分层/装配事实 |
| `tests/README.md` | 新terminal manifest/E2E/focused命令与stress acceptance | 更新当前测试分层和命令 |
| 根`README.md` | 当前未改变用户CLI参数、配置步骤或最终工作流 | 审计，预期不修改；实际命中才停下确认 |
| `dayu/engine/README.md` | Engine contract不变 | 不修改 |

## 10. 风险控制、阻塞问题与实施完成报告

### 10.1 主要实施风险及控制

- reservation/close race：只用owner-loop token与幂等release，不允许consumer层补偿计数。
- cursor/cancellation race：actor operation可继续完成，但factory token owner已经释放，完成结果不得重新attach。
- durable page/terminal pause：只保留一个bounded durable page与一个current terminal fence，不建立terminal set或第三sequence。
- producer漏接：AST闭集 + runtime fake + direct promotion allowlist三重guard。
- scheduler/coordinator lifecycle：construction-only bind先于所有critical producer；Host close先stop/await全部producer，再drain/close coordinator，禁止临时port与runtime rebind。
- local/cross opener混淆：local notice只做latency；跨opener只由DB/fence/reconcile tests作结论。
- Service cleanup覆盖primary：capacity-one first-commit + exact exception-chain table，禁止task exception side channel。
- renderer阻塞：UI-owned explicit single-thread executor + submit-before serial gate，一次只允许一个awaited callback/display job；与Host/runtime default executor隔离，不建event-copy relay。无限阻塞违反callback contract，不使用仍运行thread晚于cleanup的伪保证。
- metrics基数扩散：只允许closed `event/outcome/reason`，无identity/payload/sequence value/capacity dimension。

### 10.2 Blocking issues

无。design residual为0，goal confirmation已通过。实施过程中若触发任一slice的stop condition，应回到对应semantic owner修正，不能降级成fallback、compatibility shim或新residual WU。

### 10.3 Implementation完成时必须报告

最终implementation closeout必须明确：

1. 实际完成的4个slice及每个owner contract。
2. public/config/schema/callsite/terminal manifest/Service state/README的changed files。
3. focused、affected suites、stress、单文件coverage、完整pyright、`git diff --check`、stale/source scans的命令与结果。
4. 是否存在未覆盖项或风险；不得把已冻结的无byte/heap bound裁决重新列为开放风险、future WU或阻塞项。
5. 不得声称实施了Engine public contract、delta replay、跨进程广播、Host-global quota或`WU-CLI-SMOKE-01-R2`。
