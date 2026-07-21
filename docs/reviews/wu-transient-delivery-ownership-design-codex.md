# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Design Correction

## Gate

- Work unit：`WU-CLI-SMOKE-01-R1` final-closeout design correction。
- Gate：phaseflow final-closure design-fix gate；2026-07-21 cross-opener / async-attach correction。
- Date：2026-07-21。
- Agent：AgentCodex。
- Design truth：`docs/host/design.md`、`docs/engine/design.md`。
- Read-only control：`docs/host/issues-implementation-control.md`。
- Decision：`revised-ready-for-independent-three-way-re-review`；Controller 已基于直接代码证据接受 final closure review 的两个高严重度 findings，本轮在 owner 层全部关闭，不降级、不 deferred、不转 residual；此前 single mailbox / counted in-flight、无 Service relay、三维容量、overflow order、exact-five、cleanup、全 terminal producer typed notice 与本地 A→B fence 全部保持关闭。本 artifact 仍不授权 implementation。

## 动机与严重性判断

动机成立，且不是单纯“容量值可能需要调优”。当前设计把三个不同语义揉在了一起：EngineEvent ingest 后的 typed handoff、per-subscription 展示投递、Service 入口协调。生产代码又在 Host subscription 与 Service relay 各保留一个有界队列。这个结构造成四个直接问题：

- Host 设计把固定 item 数写成 Host 私有真源，调用方无法根据部署内存预算、delta burst 与 consumer latency SLO 显式配置。
- 同一个 subscription 的事件先后进入 Host 与 Service 两个同容量 buffer，端到端真实上限、overflow 点与错误归因都不清晰。
- `slow_consumer` 把容量耗尽归因于消费者速度，但一个超大单事件也可触发相同失败；这是未经事实证明的原因标签。
- item count 只能约束对象数量。Host / Engine public delta contract 没有单事件 UTF-8 byte bound，固定 item 数不能证明 mailbox 内存有界。

因此，原先把 Host capacity 与 Service relay capacity 当成两个可独立调参 WU 的路径不是最佳方案。它保留了重复 owner，只调整两个数值无法关闭结构性风险。二轮复审又用当前代码证明：Host batch drain 会在 mailbox 外保留第二批未计量事件；Service task exception / normal EOF 与 startup 换绑缺少唯一 observation-result owner；multi-watcher 已是 public contract，却没有 attach admission；overflow primary dimension 互相冲突。正确修复边界是统一 Service observation、Host per-subscription retention 与 per-Session admission 三个 owner；本 design correction 只冻结 contract，不实施代码。

第四轮 closure re-review 的新增直接证据同样成立：`admission.py` 的 pre-dispatch / waiting / recovering cancel、`waiting.py` 的 failed / lost / expiry、`dispatch.py` 的 active-cancel watchdog与startup closeout、`recovery.py` 的 lost closeout均可提交 Session-visible terminal；它们当前只在 commit后传递 `session_id` 或按 Session去重的 promotion集合。只修 `engine_ingest.py` / `dispatch.py` 的单一路径无法向 Session Event Delivery提供 exact terminal `event_sequence`，A/B cutoff仍可被其它 producer绕过。正确修复边界是 durable transaction result携带exact sequence，所有producer复用单一Host-internal post-commit port，由opener owner loop统一协调watermark / subscription wake / optional promotion；不是Service fallback、latest-row readback或新的terminal marker集合。

final closure review 的两个高严重度 finding 动机也成立，且同样是 owner 冲突，不是参数调优：

- 每次 `open_host` 都创建自己的 in-memory delivery hub / coordinator，而 EventLog 与 admission active invariant 是共享 DB 内的 durable truth。opener-local `TerminalPostCommitPort` 可以降低本地 terminal 发现延迟并约束本地 promotion，但无法向另一 opener / 进程的 watcher 传递 correctness cutoff。把它声称为所有 watcher 的唯一正确性来源，会允许后继 Run B delta 越过前序 Run A durable terminal。
- 当前同步 factory 只提交 start-cursor future 便返回 iterator，cursor transaction 可在 public return 之后才真正运行。“future 已排队”不是与其它 SQLite writer 共享的线性化点，会把 return 后提交的 terminal 吞进 start cursor。正确 public contract 是 async factory，successful await return 才是生效边界。

因此本轮修复的唯一正确边界是：Host EngineEvent ingest 从同一 durable validation transaction 已读取并确认的当前 `Attempt.started_event_sequence` 产生 per-candidate causal fence，publisher 原样复制到每个 subscription entry，Host iterator 在 pop 前追赶该 fence；同时把 public watch 改为完成 durable cursor transaction 后才在 owner loop 注册 subscription 的 async factory。不需要跨进程 ephemeral broadcast、第三 sequence domain、Service fallback 或 durable transient replay。

## First-principles Alternatives

### A. 保留 Host 与 Service 两级 buffer，分别调参

拒绝。两个队列承载同一批 `HostSessionEvent`，没有两个独立业务事实需要分别持有；分别调参只会让 overflow 位置随配置漂移，也不能给出端到端 item / byte 上限。

### B. 删除 Host mailbox，只在 Service 建立 mailbox

拒绝。`watch_session_events(...)` 必须在 Host public facade 内完成多 watcher fanout、transient runtime ordering、terminal fence、detach 与 close。若 ingest 直接 await Service 或 UI，慢消费者会获得反压 Agent / Engine 的能力；若改为 callback，又会把 delivery lifecycle 泄漏到上层并弱化朴素 async iterator contract。

### C. 把 transient delta 写入 EventLog，用 durable reader 统一交付

拒绝。该方案重新引入 per-chunk durable amplification，并错误承诺 replay、retention、projection 与 recovery 语义，直接违反本 WU 已接受的 live-only 边界。

### D. 使用 unbounded mailbox

拒绝。它能暂时隐藏 overflow，却把慢 consumer 转化为无上限进程内存增长，且仍然无法定义跨 watcher 隔离。

### E. 仅配置 `max_items`

拒绝。三类 delta 的字符串字段没有 Host / Engine public byte bound；对象数有界不等于 payload bytes 有界。

### F. 先给 EngineEvent 增加全 Runner 单事件 byte bound，再只使用 `max_items`

这是理论上可行的替代边界，但当前没有直接证据支持。现有 OpenAI SSE parser 只有 adapter-local 行字符数 / data line 数保护，不能代表 Engine public contract，也不能覆盖未来 Runner。为解决 display delivery 内存边界而先扩张 Engine contract 不是最小方案。

### G. 一个 transient mailbox + durable pull reader + typed runtime policy

采用，并以 causal fence + async attach 补齐跨 opener correctness。Host public iterator facade 统一为可关闭 Protocol；durable EventLog reader 与 transient subscription mailbox 在 facade 内合流但各守 owner；每个 subscription 只有一个 items / bytes 双有界 mailbox 与唯一 in-flight retained state，读取只做单项 transfer；每个 entry 携带同源 durable causal fence；runtime composer / operator 在 `open_host` construction-time 显式提供 opener-wide items / bytes / per-Session subscription-cap policy；Service 只用 generation-tagged 容量一 observation-result slot；ingest 只做 non-blocking typed handoff；`await host.watch_session_events(...)` 的 successful return 是唯一 attach 生效边界。

## 最终 Normative Design

### Public interface

- 对外保持统一可关闭 async iterator 外观，但 factory 本身改为 `await host.watch_session_events(session_id) -> HostSessionEventIterator`。`HostSessionEventIterator` 是 `AsyncIterator[HostSessionEvent]` 的可关闭子协议，显式提供幂等 `aclose()`；`Host` Protocol、public implementation、`dayu.host.api` / package exports 复用同一 async factory 签名和精确返回类型，Service 删除私有 closable Protocol 与 `cast`，Service / CLI adapter 所有调用点显式 `await`。
- `HostSessionEvent` 当前仍是 `HostEvent | HostTransientDelta`；本 correction 不增加第三类 event。
- 新增 `dayu.host` public typed construction-time policy `HostSessionEventDeliveryPolicy`，required 字段固定为：
  - `transient_mailbox_max_items: int`；非 bool 正整数。
  - `transient_mailbox_max_bytes: int`；非 bool 正整数。
  - `max_subscriptions_per_session: int`；非 bool 正整数。
- `OpenHostOptions.session_event_delivery_policy` 必须接收完整 policy。`watch_session_events(...)` 不增加参数，单个 Run、UI / CLI 与单个 subscription 不能覆盖 runtime delivery policy；per-subscription override 是 non-goal。
- `host_runtime.json.session_event_delivery_policy` 是部署默认输入；ConfigLoader 只解析 typed config，Service / composition root 映射为 `HostSessionEventDeliveryPolicy`。Host 不读取 config，也不保留隐藏 capacity fallback。
- runtime composer / operator 是 opener-wide effective policy 的唯一 owner；同一 opener 的所有 subscription 使用统一 policy snapshot。
- async factory 先在 opener owner loop reserve per-Session subscription slot；cap+1 在任何 mailbox / cursor transaction / iterator task allocation前以专属 typed error fail closed。reserve 成功后 await `DurableActor` 完成真实 Session existence / start-cursor transaction，回 owner loop 后在同一无 `await` 段创建并注册 subscription、记录本地 watermark baseline并 return。successful await return 是唯一生效边界；首次 `anext()` 不得补做 cursor / attach / allocation。
- 本 design correction 不拍板 items / bytes / max-subscriptions 三个 packaged 数值。packaged default、低基数 metrics 与 Python heap margin必须在未来实施 WU 中基于 workload、consumer latency SLO、峰值 delta rate、watcher 数量与内存预算给出证据，但这些测量项不阻塞本设计。

### Ownership

| 语义 / 状态 | 唯一 owner | 边界 |
|---|---|---|
| 单次 Engine generator 内 delta 产生顺序 | Engine | 不提供 Host cursor、fanout 或 replay。 |
| candidate shape、Session / Run / Attempt / execution identity、late-state validation、candidate causal fence | Host EngineEvent ingest | validation transaction 成功后，从该 transaction 已读取并确认的当前 `Attempt.started_event_sequence` 取得非 bool 正整数 `durable_causal_fence_event_sequence`；随 typed candidate non-blocking handoff，禁止 transaction 后回读或猜测。 |
| transient runtime id、publication sequence、dedupe key、多 watcher fanout、entry fence 复制 | Session Event Delivery publisher | 把 candidate fence 原样复制到每个 subscription entry；不写 EventLog，不重算 fence，不读取 durable consumer policy。 |
| terminal durable truth与exact post-commit input | EventLog transition + terminal producer transaction result | 新提交或幂等确认terminal的同一transaction返回exact Run terminal sequence；禁止post-commit latest-row readback /猜测。 |
| `TerminalPostCommitNotice` / `TerminalPostCommitPort` 与协调顺序 | `dayu/host/terminal_post_commit.py` contract + producer 所属 `open_host` opener coordinator | 所有 producer commit 后 marshal 到自己 opener owner loop；本地 watermark/wake 先于 optional promotion。它是低延迟本地 wake / promotion coordinator，不是其它 opener watcher 的 correctness source。 |
| opener-local `committed_terminal_event_sequence_high_watermark` hint | Session Event Delivery | 只由本地 terminal coordinator 做 O(1) max-advance；只降低本地 durable reconcile 延迟并约束本地 promotion，不是跨 opener cutoff、terminal set、业务事实或持久化 cursor。 |
| per-subscription mailbox、唯一 in-flight、items / bytes retained accounting、overflow、detach / disconnect、readiness | Session Event Delivery subscription | 不改变 Run / Attempt / terminal，不影响其它 watcher。 |
| per-Session reservation、attach rejection、release 与 fanout cap | Session Event Delivery admission | owner-loop 线性化；不同 Session 隔离，不驱逐既有 watcher。 |
| delivery policy typed shape | `dayu.host` public contract | 只表达 runtime delivery 容量，不是 per-Run knob。 |
| effective policy value 选择与装配 | runtime composer / operator | 从部署配置或 opener 级显式 override 构造完整 typed value；对所有 subscription 统一，UI / CLI 不逐订阅覆盖。 |
| durable `HostEvent`、`event_sequence`、terminal truth | EventLog / durable read owner | append 与补读不受 watcher 速度影响。 |
| async attach factory、durable / transient 合流、entry-fence catch-up、periodic reconciliation、attach cleanup、`aclose()` | public Host facade + `HostSessionEventIterator` facade | factory 的 successful await return 是生效边界；iterator 每次 pop 前追赶 entry fence，mailbox 空时仍定期有界补读；不吞并两个内部 source 的语义所有权。 |
| channel 展示、选择 content / reasoning / tool-call | Service / UI / CLI adapter | 不读取 raw `EngineEvent`，不重建 replay。 |
| sole `anext`、generation-tagged exact-five observation result、caller disposition、cleanup precedence 与 degraded recovery | Service watch runtime | 恰好一个 consumer task first-commit 唯一容量一 slot；task exception / extra Future 不构成第二语义通道。 |
| 离线 terminal 投递 | Outbox | 不补放 transient delta。 |

### Handoff 与 mailbox boundary

```text
EngineEvent stream
  -> Host EngineEvent ingest
       validate + classify + build typed candidate
       fence = current Attempt.started_event_sequence read by same transaction
       non-blocking, non-throwing handoff
  -> Session Event Delivery publisher
       runtime identity + publication order + fanout
       copy the same fence to every subscription entry
       non-blocking offer to each subscription
  -> one transient mailbox + one current in-flight per subscription
       each retained entry = public event + size + Host-internal durable causal fence

EventLog reader --bounded pull--> iterator facade <--single pop/transfer-- transient mailbox
                                      |
                                      v
                  HostSessionEventIterator

terminal EventLog commit
  -> transaction result: exact TerminalPostCommitNotice
  -> TerminalPostCommitPort marshal to producer opener owner loop
  -> local terminal-ready wake
  -> notice flag=true only: deduped local queue-promotion wake

cross-opener correctness
  -> before popping B entry, durable cursor catches up to B entry fence
  -> EventLog yields every preceding terminal, including A from another opener
```

- durable reader 使用 `event_sequence` cursor 有界分页拉取，不能把 rows 再复制进 transient mailbox。
- transient mailbox 只保存 `HostTransientDelta`，读取只能单项 transfer；禁止 `drain_nowait()` 返回 `list` / `tuple` / `deque` batch。当前唯一 in-flight 在 yield 恢复或 cleanup 前继续计入 Host retained items / bytes，caller 在 generator 外保留的引用不属于 Host retention。Service / UI adapter 必须直接消费 iterator，不得再建立保留 `HostSessionEvent` 的 relay queue。
- `await host.watch_session_events(...)` 先在 owner loop reserve，再 await durable actor 完成真实 start cursor transaction，回 owner loop 后在同一无 `await` 段注册 mailbox subscription、记录本地 watermark baseline并 return。successful return 是唯一生效边界；同 actor 的后续 command 必定位于 cursor 之后。cursor snapshot 到 return 之间的 committed durable rows 从较早 cursor 可读；此间 transient 是 pre-return live-only，不承诺重放；successful return 后发布的 transient 不得因 attach 未完成而丢失。
- Engine ingest 在同一 durable validation transaction 中从已读取并确认的当前 Attempt 取得非 bool 正整数 `started_event_sequence`，作为 candidate 的 `durable_causal_fence_event_sequence`。publisher 原样复制到每个 entry；禁止 latest/max readback、猜测、public / extra payload 或第三 sequence domain。该 fence 仅是固定大小 Host-internal accounting metadata，不进入 `HostTransientDelta` 或 logical UTF-8 byte traversal。
- merge 每次准备 pop mailbox 头部 entry 前，若 subscription durable cursor 小于 entry fence，必须将 entry 原位保留并按 bounded EventLog pages 追赶到 cursor 达到 fence；page size 不是 correctness 截止。期间遇 terminal A 时，沿既有 terminal fence 只单项交付 mailbox 头部 `run_id=A` prefix；首个不同 Run entry 原位保留并继续计入 mailbox + in-flight budget，然后 yield A terminal。只有 Service ack / clear / rebind 后的下一次 `anext()` 才可继续。
- admission 的单 active Run durable invariant 保证前序 Run A terminal sequence 严格小于后继 Run B 当前 Attempt 的 `started_event_sequence`；因此 B entry fence 必然跨过 A terminal，即使 A producer、watcher 与 B execution 分属不同 opener / 进程，也不能先交付 B。mailbox 为空时仍执行 bounded periodic durable reconciliation，使长期 watcher 在无本地 notice 时最终发现其它 opener 提交的 terminal。
- 慢 consumer期间出现多个 terminal时只通过 EventLog `event_sequence` 与当前 entry fence / 本地 latency hint 逐个发现；每次 terminal yield停止扫描，不保存 terminal id set / marker queue，不推进 cursor越过未交付 terminal。
- `TerminalPostCommitNotice` 的字段精确为 `session_id: str`、`terminal_event_sequence: int`、`wake_queue_promotion: bool`。新提交或幂等确认terminal的transaction result必须从同一transaction的exact terminal EventLog row /稳定idempotency ref携带sequence；禁止commit后latest Run / latest row / max sequence readback，batch不得按Session去重terminal notices。
- producer 所属 opener coordinator在同一无`await`调用栈先做本地 delivery watermark max-advance与level-trigger wake，再在flag=true时按独立per-Session O(1) promotion sequence high-watermark去重并唤醒本地queue promotion。同sequence重复幂等；先到的false不阻止稍后同sequence true，较新false也不吞较旧未处理true。普通non-terminal promotion继续走原session-id port且不推进watermark，terminal producer不得直接调用它。该 coordinator 只证明本地 producer 接线和本地 promotion 顺序，不承担跨 opener watcher correctness。
- readiness、cancellation 与 target binding 可以有不保存 event 副本的 control primitive；它们不构成第二 mailbox。Service 只允许一个容量一、generation-tagged 的 closed `ServiceObservationResult` slot，不允许 event list / deque / queue、task exception 或额外 Future。
- EngineEvent ingest 和 publisher offer 都不能 await consumer 或 mailbox capacity。该 no-backpressure 承诺只覆盖被动不读 / 异步读取慢的 subscription；同一 event loop 上的阻塞 callback、CPU 饥饿与同步 O(N) fanout 不在物理隔离承诺内。activity / thinking callback 必须快速同步、非阻塞返回，慢 I/O / CPU / renderer 适配归 Service / UI owner。

### Byte accounting

- `max_items` 与 `max_bytes` 必须同时生效。
- Session Event Delivery 提供唯一 deterministic `delivery_size_bytes` helper。string traversal 明确包含 envelope 的 `runtime_id`、`session_id`、`run_id`、`attempt_id`、`execution_id`、`dedupe_key`，以及 payload 的 `iteration_id`、`text_delta`、可选 `tool_call_id`、`name_delta`、`arguments_delta`；每个 occurrence 计算 `len(value.encode("utf-8"))`，optional `None` 计零。整数、datetime、enum、字段名、序列化标点与 Python 对象头不计入。policy、实现、metrics 与 tests 必须复用同一 helper，禁止从日志、对象 `repr` 或 renderer / adapter 序列化结果分别估算。
- publisher 每个 public event 只构造并计算一次 `(event, delivery_size_bytes)`，并接收 candidate 已有的同一 `durable_causal_fence_event_sequence`，再把三者原样 fanout 给 subscription snapshot；禁止 per-subscription 重算 size 或 fence。runtime sequence、构造、size、snapshot 与 offer 在 opener owner event loop 的同一无 `await` 调用栈内顺序执行；每个 subscription 的 prospective check + enqueue + retained accounting 同步线性化。单项 pop 只做 mailbox -> in-flight transfer、不扣减；yield 恢复或 cleanup 清除 Host 引用时才按 entry size 扣减。
- prospective accounting 始终包含 mailbox + in-flight。primary dimension 唯一顺序固定为：先判单 event 自身 `delivery_size_bytes > max_bytes`，再判 prospective item count，最后判 prospective cumulative bytes；item-full + oversized 固定 `PAYLOAD_BYTES`。metrics 可记录全部命中，但 public detail 只能携带一个 primary dimension。
- 单个事件自身大于 `transient_mailbox_max_bytes` 时同样 overflow；不得截断、拆分、partial enqueue 或改写 delta。
- `max_items` 约束 Python 对象数量与 entry size / causal fence 等非字符串固定开销；`max_bytes` 约束未设 public 上限的所有可变字符串 payload。fence 不进入 logical UTF-8 byte traversal。两者共同构成 delivery contract，不宣称精确等于 Python heap resident bytes。

### State 与 lifecycle

Host subscription 的最小 owner state 为：

```text
ATTACHED
  -> OVERFLOWED -> DETACHED
  -> DETACHED        (iterator aclose / consumer cancel)
  -> CLOSED          (Host close)
```

- attach 时 subscription 快照 runtime policy；后续配置文件变化不热修改既有 subscription。
- reservation 在 owner loop 线性化，并先于任何 mailbox / cursor transaction / iterator task allocation；reservation 满时使用专属 public `resource_exhausted` contract fail closed，不驱逐既有 watcher。reserve 后 factory 才 await durable cursor transaction；transaction / attach / allocation failure、factory cancellation 与 Host close 都由同一 owner 精确一次释放 reservation / partial resource。
- overflow 时 subscription 先标记 `OVERFLOWED` 并从后续 fanout 排除，保留已经接受且仍计入 budget 的连续前缀供 iterator 先交付，然后抛 typed delivery error；prefix / in-flight 清零并转 `DETACHED` 后才释放 reservation。
- public `HostSessionEventIterator.aclose()`、consumer task cancellation、never-started cleanup、iterator error / EOF 与 Host close 都只关闭当前 subscription 并在 owner loop 幂等释放 reservation。
- Run terminal 不结束 session watcher；subscription owner 不合成 terminal。
- Host close 关闭 publisher / subscriptions，清空 transient mailbox / in-flight、释放 reservation并正常结束 iterator；这不是用户 cancel，不写 `RUN_CANCELLED` / `RUN_FAILED`。Service consumer 必须把正常 EOF signal 为 `ITERATOR_ENDED`。
- Session Event Delivery 不创建 per-watcher background task。Service 可以有一个 sole consumer task，但不得用 event-retaining task queue 变相恢复双重 buffer。

Service observation result 是唯一容量一、带 `target_generation` 的封闭联合，恰好只有 `TARGET_TERMINAL`、`DELIVERY_INTERRUPTED`、`ITERATOR_ENDED`、`CALLBACK_FAILED`、`ITERATOR_FAILED` 五个 members；不得增加 catch-all、兼容别名或 task-exception outcome。sole consumer 是全部 outcome 的唯一 first-commit owner；consumer task 只作为 lifecycle handle，禁止以 task exception、done callback、额外 Future 或 queue item传递第二份语义。normal EOF / Host close 必须 commit `ITERATOR_ENDED`。除 `TARGET_TERMINAL` 可被 startup ack 后复用外，其余 fatal outcome 均 sticky 并终止 watcher。

cleanup 后 caller disposition 固定如下：

| Member | 唯一 disposition |
|---|---|
| `TARGET_TERMINAL` | 返回 slot 携带的 terminal，不做 durable 重算。 |
| `DELIVERY_INTERRUPTED` | 只走 `get_run` / Outbox durable recovery；成功返回 terminal，失败原样传播 recovery exception并 `raise recovery_error from delivery_error`。 |
| `ITERATOR_ENDED` | 固定抛 `EntrypointRuntimeError("session_event_iterator_ended_before_terminal")`，完整 message即 stable reason；不 recovery。 |
| `CALLBACK_FAILED` | 原样重抛 callback original exception。 |
| `ITERATOR_FAILED` | `HostApiError` / `HostClosedError` 原样抛；其它 exception wrap 为 `EntrypointRuntimeError("session_event_iterator_failed_before_terminal") from original`。 |

slot first-commit primary 永不被 cleanup、stop、late callback 或 task completion覆盖；caller cancellation / coordinator stop在空 slot先取得仲裁权后，late slot commit无效。cleanup 顺序必须是停止并 await sole consumer、确认无 active `anext()`、调用一次 public `aclose()`；Host reservation release仍由 Host `finally` 幂等保证。若 exception / caller cancellation primary 与 close同时失败，primary保持 top-level并 `raise primary from cleanup_error`；non-public iterator double failure保留 `EntrypointRuntimeError -> original iterator error -> cleanup error` 三层 chain。delivery recovery失败时仍以 recovery error为 top-level、delivery error为直接 cause；若 close也失败，cleanup error只作为 delivery error的 nested cause。

若 `TARGET_TERMINAL` 或成功 delivery recovery 已取得 terminal而 close失败，仍返回 terminal，并通过现有 `on_activity` 最多尝试一次去敏 secondary diagnostic：`WATCHER_DIAGNOSTIC` / `FAILED` / `WARNING`、`run_id=None`、`event_sequence=None`、dedupe key=`entrypoint_watcher_cleanup_failed`、title=`运行事件流清理失败`、summary=`已保留终态结果，但运行事件观察器清理失败。`，tool / counts字段均为 `None`；不包含 cleanup exception 类型 / message / identity / traceback，diagnostic callback失败不得改变 primary。若 slot为空且无 cancellation，close failure是唯一 caller failure：`HostApiError` / `HostClosedError` 原样抛，其它 wrap 为 `EntrypointRuntimeError("session_event_iterator_cleanup_failed") from cleanup_error`。

Service watch runtime 固定使用以下显式循环：

```text
DETACHED -> ATTACHED_UNBOUND
ATTACHED_UNBOUND -- bind(g, target) + resume --> CONSUMING(g)
CONSUMING(g) -- sole-consumer first-commit --> RESULT_READY(g)
RESULT_READY(g) -- coordinator consume/ack terminal(g), clear slot --> ATTACHED_UNBOUND
ATTACHED_UNBOUND -- bind(g+1, next target) + resume --> CONSUMING(g+1)
RESULT_READY(g) -- fatal or helper complete --> STOPPING -> CLOSED
ATTACHED_UNBOUND / CONSUMING(g) -- stop observed first --> STOPPING -> CLOSED
CLOSED -- delivery interruption only --> DEGRADED durable recovery
```

- 必须先 `await host.watch_session_events(...)`；successful return 后 subscription 已生效，才创建 sole consumer 并提交 submit。该 return 后提交到同一 durable actor 的 command 必定位于 start cursor 之后。consumer 在 `accepted_run_id` 返回前不执行首次 `anext`，Host mailbox 是 target-unbound 窗口唯一 buffer。成功后绑定唯一 target generation，再开始消费；submit 失败或 command commit / caller cancellation 不明时，不从 session event 猜 target，分别按 command idempotency owner 处理。
- cancel 目标已知：已 terminal 直接 durable recovery；非 terminal 先 attach sole consumer 再发 cancel。cancel error 与 terminal race 通过最新 `get_run`、live slot 与 Outbox terminal identity 去重。
- sole consumer 是唯一 `anext` / outcome-commit owner；terminal commit 后立即进入 `RESULT_READY(g)` 并在再次 `anext` 前暂停。startup coordinator 必须按顺序消费 / ack `g`、清 slot、回到 `ATTACHED_UNBOUND`、绑定 `g+1`，最后才恢复；旧 generation 不得写新 slot。A terminal `yield` 后 Host merge也停在同一悬停点，B event只留在 Host counted mailbox，Service 不预读、不缓存。
- delivery-specific watcher failure first-commit 后先 `STOPPING -> CLOSED`，再使 helper 进入本地 `DEGRADED` 并只转 `get_run` / Outbox recovery；不立即 reattach，不标记 Host outage。EOF固定 Service error、callback原异常、iterator public原异常 / non-public stable wrap均按上表处理，不得二选一。
- startup reconnect 先 await async watch factory 成功，再创建 consumer 并做 Outbox backfill / snapshot / promotion / idle-tail；active / promoted target 严格按 generation handshake 顺序绑定，不创建 live event cache。无 target 时 consumer 不 `anext`，事件仍留 Host mailbox；startup idle 直接 cleanup。
- stop / terminal / failure 同拍只由 slot first-commit 仲裁：consumer 已取得 result且 slot 空时 result 先 commit并保持；stop / cancellation先取得空 slot仲裁权时 consumer 不再读取且late commit无效；slot 已占用时 cleanup、迟到 signal 与 task completion都不能覆盖。fatal outcome 在 caller disposition与 cleanup完成前 sticky。
- live / Outbox terminal 用 `terminal_event_id` / `event_sequence` / `run_id` 去重。关闭顺序固定为：请求 consumer 停止或 cancel task，await task 并确认无 active `anext()`，再调用 public iterator `aclose()`，最后按上述 precedence返回 / 抛出并释放 slot / signal。renderer / runtime display 不属于 Service watcher runtime，仍由 caller 的 `finally` 幂等关闭。

### Ordering

- durable `HostEvent.event_sequence` 与 transient `HostTransientDelta.runtime_sequence` 继续是不可比较的两个 sequence domain；entry fence 只引用已有 durable `Attempt.started_event_sequence`，本地 terminal watermark 只是 runtime latency hint，两者都不是第三套总序、event、durable state或 public cursor。
- producer 与 watcher 同属一 opener 时，terminal closeout 的本地低延迟顺序为 EventLog terminal commit -> transaction result携带 exact `TerminalPostCommitNotice` -> `TerminalPostCommitPort` marshal到 producer opener owner loop -> 本地 watermark / terminal-ready wake -> flag=true时按promotion high-watermark幂等发本地 queue-promotion wake -> B publish；该 barrier不等待watcher、不暂停promotion / Agent。port 不跨 opener 传播，不能代替 entry fence / EventLog catch-up。
- 所有当前可达terminal producer必须走同一port：Engine terminal / worker lost；admission queued / pre-dispatch / waiting / recovering / session cancel与通用closeout；waiting failed / lost / expiry；dispatch watchdog / pre-start / startup closeout；startup recovery lost。future terminal writer也必须先扩展同一transaction result与callsite manifest。普通accepted / queued reconciliation等non-terminal promotion保留原port且不触碰watermark。
- async factory 先 reserve，await durable start cursor transaction，再在 owner loop 无 `await` 段 attach；successful return 是生效边界。cursor snapshot 与 return 之间的 durable rows 可从较早 cursor 读到，该期间 transient 不承诺 replay。每次 transient pop 前若 cursor 落后 entry fence，merge 先做 bounded-page EventLog catch-up 直到达到 fence；mailbox 空时仍做 bounded periodic durable reconciliation。
- 遇 terminal A 时只单项交付 mailbox头部同 Run A prefix；首个不同 Run entry留在原 counted mailbox且不得 pop，然后 yield A。Service ack / rebind 后的下一次 `anext()` 才允许 B；Service不缓存 B。
- 多个 terminal通过 EventLog顺序与当前 entry fence / 本地 latency hint逐个发现；merge不保存 terminal id set / marker queue，cursor不越过未交付 terminal。terminal durable commit 后的所有迟到 delta仍由 Host ingest late-state validation唯一拒绝，subscription不重做 durable validation。
- overflow disconnect 后，当前 iterator 不保证继续观察 durable terminal；terminal 已由 EventLog / Outbox 持久拥有，调用方按既有 Outbox / `get_run` 路径恢复。
- detach、disconnect、Host close、进程退出或新 `open_host` runtime 均不 replay transient delta，不建立跨域可重放总序。

### Overflow / degraded / disconnect

- 当前联合事件 contract 的唯一支持动作是 typed disconnect，避免在没有 gap event 的情况下 silent drop-and-continue。
- 超限事件不入队；subscription 标记 overflow、停止后续 fanout，并在已入队连续前缀交付后抛：
  `HostApiError(code=HostApiErrorCode.DELIVERY_INTERRUPTED, retryable=False, detail=HostSessionEventDeliveryDetail(reason=HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW, limit_dimension=<one primary enum selected by the fixed algorithm>))`。
- public values 固定为 `delivery_interrupted`、`transient_mailbox_overflow`、`item_count` 与 `payload_bytes`；consumer 只按 typed code / enum 分支，不解析 message。
- attach cap rejection 固定为 `HostApiErrorCode.RESOURCE_EXHAUSTED = "resource_exhausted"`、`retryable=true`、`HostSessionEventAdmissionDetail(reason=HostSessionEventAdmissionReason.SESSION_SUBSCRIPTION_LIMIT_REACHED)`，reason string 固定为 `"session_subscription_limit_reached"`。owner 是 Session Event Delivery admission；它不表示 Host outage，message 不供分支。
- 错误只表达该 subscription 已 detach、transient 展示投递不再连续，不归因于 consumer 速度，也不是 Run failure / Host availability。Service 将其映射为本地 degraded + durable recovery，不标记 Host outage、不立即重订阅。
- overflow、drop、degraded、disconnect 与相关 operator metrics 都由 delivery / subscription owner 解释；不得写 EventLog、改变 Run / Attempt / terminal、调用 Run cancel、阻塞 ingest 或影响其它 watcher。
- 若未来要支持 drop-oldest、drop-newest 或 drop-and-continue，必须先扩展 `HostSessionEvent` 的 typed gap / degraded notice 并进入 public contract design gate；不得通过日志、可选字段或错误字符串让 consumer 猜测缺口。

### Durable 与 transient 边界

- `HostTransientDelta` 继续 live-only、不持久化、不 replay、不进入 projection、Outbox、memory、audit、Tool Trace 或恢复输入。
- durable terminal、final answer、Outbox、Run / Attempt state 与 EventLog owner 全部不变。
- delivery failure 可以记录不含 delta 正文的 sanitized operator diagnostic；该 diagnostic 不成为业务事实或 terminal 原因。
- 特定 watcher 的 delivery failure 不改变其它 watcher 的 sequence、mailbox 或 lifecycle。

### Aggregate resource boundary

- multi-watcher 已由生产代码与 public tests 裁决为现行 contract；实施 WU 不得重新审计为单-watcher，也不得保留条件分支。
- Session Event Delivery 以 `max_subscriptions_per_session` 做 attach-time reservation；max+1 在任何 mailbox / cursor transaction / iterator task allocation前 fail closed，不驱逐、不 detach 既有 watcher。reservation 在 cursor / attach / allocation failure、factory cancellation、successful return 后的 `aclose()` / never-started / overflow 最终 detach / iterator error / EOF 与 Host close 时由对应 owner 精确一次释放；不同 Session 隔离。
- overflowed subscription 在 prefix / in-flight 尚未清零时仍占 reservation。由此每 Session Host-owned transient retained logical bound 为 `cap × per-subscription items/bytes budget`，fanout upper bound 为 `cap`；generator 外 caller 已接收引用、精确 Python heap 与跨 Session Host 总内存不在该乘积承诺内。
- 不设计 Host-global quota、跨 Session 总配额或独立消息系统。packaged cap 数值由实施 WU 测量，但字段、算法、typed error 与 release contract 已冻结。

## 未来 Implementation WU 范围

本 design write gate 之后如进入独立 implementation WU，最小闭环应包含：

1. `dayu/host/api.py` / `dayu/host/__init__.py`：新增并导出 public closable iterator、三 required 字段 delivery policy、`OpenHostOptions.session_event_delivery_policy`、`DELIVERY_INTERRUPTED` / `RESOURCE_EXHAUSTED`、delivery / admission detail 与 closed enum；`Host` Protocol 与 implementation 把 `watch_session_events` 定义为 async factory，精确返回 `HostSessionEventIterator`，不保留同步 wrapper / alias。
2. `dayu/runtime/config_loader.py` / `dayu/config/host_runtime.json` / `dayu/service/host_assembly.py`：增加严格 typed config view、含 items / bytes / max-subscriptions 的 packaged 完整 policy 与 runtime composer 一对一映射；missing / extra / bool / zero / negative fail closed，Host / Service 无 fallback，scene / UI / subscription 无 override。
3. `dayu/host/transient_delta.py`：实现 policy-driven 单 subscription mailbox、唯一 canonical UTF-8 byte helper、每 event 一次 size 后 fanout、mailbox + in-flight 精确 retained accounting、固定 overflow primary order、typed overflow、candidate fence 到每 subscription entry 的原样复制、pop 前 causal-fence 检查、opener-local terminal-ready watermark hint、O(1) current-terminal fence、per-Session attach reservation、detach / close 与释放；删除所有 batch drain shape。`durable_causal_fence_event_sequence` 是固定大小 Host-internal metadata，不进入 public delta 或 logical-byte traversal。
4. 新增 `dayu/host/terminal_post_commit.py` 作为唯一 internal owner，定义字段精确的 `TerminalPostCommitNotice`、同步 `TerminalPostCommitPort`与strict validation；不public export、不持久化、不加session-id terminal overload。
5. `dayu/host/open_host.py`：注入 policy 并实现 async `watch_session_events(...)` factory。owner loop 先 reserve，await `DurableActor` 完成实际 start cursor transaction，回 owner loop 后在同一无 `await` 段创建/注册 subscription、记录本地 watermark baseline 并 return；删除同步 factory、pending cursor future、done callback 与首次 `anext()` cursor attach。每次 pop 前按 entry fence 执行 bounded-page catch-up，mailbox 空时仍执行 bounded periodic durable reconciliation。这里还装配 producer 所属 opener 的 terminal coordinator，按 local delivery wake -> optional deduped promotion 的无 `await` 顺序消费 notices；ordinary promotion port 保持独立。coordinator 不承担跨 opener watcher correctness。
6. `dayu/host/durable/run_transition.py`及producer-local result：所有新terminal或幂等确认result携带同transaction exact sequence；batch返回按sequence排列的notice tuple，禁止Session去重、latest-row readback或optional sequence。
7. `dayu/host/admission.py`：接入queued / pre-dispatch / waiting / recovering / session-scope cancel、terminal ack与通用terminal closeout；仅本transaction新释放active slot且需reconciliation时flag=true。initial admission / active-cancel request不是terminal，仍走原governance/watchdog控制。
8. `dayu/host/waiting.py` / `dayu/host/command.py`：以notice替代`queue_promotion_session_id`作为failed / lost / expiry terminal handoff；public resolve、callback resolve、expiry与cancel装配同一port，command不得post-commit补读或直接promotion。resume-only wait completion不产生terminal notice。
9. `dayu/host/recovery.py`：batch terminal notices与ordinary accepted/queued promotion sessions分开保存；recovering limit lost、unrecoverable orphan / cancelling lost逐terminal接port，非terminal recovery action不推进watermark。
10. `dayu/host/engine_ingest.py` / `dayu/host/dispatch.py`：Engine ingest validation transaction 从已读取并确认的当前 Attempt 取得非 bool 正整数 `started_event_sequence`，作为 typed candidate 的 `durable_causal_fence_event_sequence`；禁止 transaction 后 latest/max readback、猜测、public / extra payload。Engine succeeded / failed / cancelled、worker lost、watchdog、attempt-free pre-start failure和worker startup closeout全部使用transaction-local exact notice；删除只含session id的terminal promotion helper与`closed_session_ids` batch语义。保留ingest late-state owner，B publish不等待watcher。
11. `dayu/service/entrypoint_runtime.py`：所有 watch 调用点显式 `await host.watch_session_events(...)`，并只在 successful return 后创建 sole consumer / 提交同 actor command；删除私有 closable Protocol / cast、event relay queue、drain task、queue item failure wrapper 与所有 queue consumers；落地 generation-tagged exact-five observation-result slot、五类唯一 caller disposition、fatal sticky、startup ack/rebind、cancel / degraded / terminal race / never-started、stop / cancellation仲裁与 cleanup precedence；禁止 task exception /额外 Future 成为 outcome channel。
12. `dayu/cli/session_execution.py` / `dayu/cli/runtime_display.py` 与实际 callback adapters：更新直接 / fake Host watch 调用为 async factory，确认 callback 快速、同步、非阻塞，慢 I/O / CPU / renderer 必须在 UI owner 显式解耦，renderer 仍由 caller `finally` 关闭，不引入 UI event-copy relay。这是同一 implementation WU acceptance，不是 residual。
13. 显式删除旧常量 / 术语：`_TRANSIENT_WATCH_BUFFER_CAPACITY`、`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`、`_LIVE_STREAM_COMPONENT`、`_SLOW_CONSUMER_REASON_CODE`、`_SLOW_CONSUMER_MESSAGE`、`_slow_consumer_error()` 以及 production / tests / docs 中作为现行 contract 的 `slow_consumer`、`session_live_stream`、`UNAVAILABLE + HostUnavailableDetail` overflow 路由；不得保留兼容 alias / wrapper / 双写。
14. 更新 owner-level、Host → Service → CLI E2E、public 类型测试与所有相关 fake / fixtures。类型测试必须断言 Host Protocol 是 async factory、真实 Service / CLI 调用点全部显式 `await`。delayed-cursor deterministic barriers 覆盖：cursor transaction 被阻塞时 factory 尚未 return；cursor snapshot 完成到 successful return 之间有 durable commit；factory cancellation / cursor error / attach allocation failure / Host close 精确一次释放；successful return 后的同 actor command 位于 cursor 之后，post-return transient 不因 attach 未完成丢失。既有 retained / admission / overflow / Engine terminal / exact-five / cleanup acceptance保持。`tests/host/test_terminal_post_commit.py` 的 AST qualified-callsite 闭集和 ordinary-promotion allowlist 只证明每个 terminal producer 向所属 opener 本地 coordinator 接线，不宣称跨 opener 完备。既有三组 non-Engine 本地 barrier 继续覆盖 A terminal -> B delta；新增双 opener 共享同一 DB barrier：watcher 与 B 在 opener C，A terminal 由 opener A 提交且 C 无本地 notice，B entry 携带同 validation transaction Attempt start fence，C 必须通过多页 catch-up 先交付 A terminal 并保留 B entry。另覆盖 mailbox 空且无本地 notice 时 periodic bounded reconciliation 最终发现跨 opener terminal。Service七组double-failure tests与其它既有acceptance不得弱化。
15. README 触发面：按职责检查并更新 `dayu/host/README.md`、`dayu/service/README.md`、`dayu/config/README.md`、`dayu/README.md`、`tests/README.md`；根 `README.md` 仅在用户可见 CLI / Web 工作流、配置步骤、输出或排障变化时更新。Engine contract 不变时不修改 `docs/engine/design.md` / `dayu/engine/README.md`。运行受影响测试、单文件覆盖率、完整 pyright 与 `git diff --check`。以上都是未来 WU 要求，不属于本次改动。

### 同一 implementation WU acceptance（不是 residual）

| 项 | 冻结 acceptance |
|---|---|
| packaged capacity | 基于代表性 workload、consumer latency SLO、peak delta rate、watcher count 与 memory budget 测量 `transient_mailbox_max_items` / `transient_mailbox_max_bytes` / `max_subscriptions_per_session` 的 packaged 值；不重开字段、校验、reservation 算法或 typed error。 |
| heap safety margin | 测量 logical UTF-8 byte budget 到 Python resident heap 的 safety margin 并写入配置注释 / 设计说明；`delivery_size_bytes` 不声称精确 heap measurement，固定 metadata 由 `max_items` 与该 margin 覆盖。 |
| low-cardinality metrics | 至少区分 item / byte overflow、buffer high-watermark 与 detach，不记录 payload 正文、Session / Run 等高基数 identity。 |
| AST / runtime / integration proof | AST manifest fail closed 保护本地 producer 接线，runtime fake port 与本地 barrier 保护本地 promotion 顺序，双 opener / 无 notice / 多页 catch-up barrier 独立保护跨 opener correctness。 |
| oversized / accounting | 单 event oversized 报 `PAYLOAD_BYTES` 且不截断；item-full + small、cumulative bytes full、item-full + oversized 继续按固定 primary order 精确断言。 |
| Service / UI callback | activity / thinking callback 必须快速、同步、非阻塞返回；慢 I/O、重 CPU 与 renderer 在 Service / UI owner 显式解耦，不依赖 Host mailbox 吸收 callback 延迟，不建立 Service event-copy relay。 |

上述全部属于同一 implementation WU acceptance；不是 design residual、未归属 risk 或后续 open question。

### Terminal producer closed manifest

| Owner | 当前可达 terminal producers | Transaction / port acceptance |
|---|---|---|
| admission | queued、pre-dispatch、WAITING、RECOVERING cancel；terminal ack；session cancel；通用 closeout | 每个terminal result携带exact notice；queued / ack /全目标session cancel为false，单Run active-slot release为true。 |
| waiting / command | failed、lost、expiry、同scope replay；WAITING cancel接到admission writer | `queue_promotion_session_id`不再承担terminal语义；result -> terminal port，resume-only无notice。 |
| Engine ingest | Engine succeeded / failed / cancelled、worker lost / lifecycle closeout、duplicate | accepted / duplicate都带exact sequence；只有新release需要true，不能直接普通promotion。 |
| dispatch | active-cancel watchdog、attempt-free pre-start failure、worker startup terminal；lost委托ingest | batch逐notice，不保留`closed_session_ids`作为terminal handoff。 |
| startup recovery | recovering limit lost、unrecoverable orphan / cancelling lost | terminal notices与ordinary accepted / queued promotion集合分离，不能按Session去重terminal。 |

静态acceptance不是开放审计项：`tests/host/test_terminal_post_commit.py`必须从AST生成`(module, qualified producer, terminal transition)` callsite集合，与上表冻结manifest exact相等；新增、删除或改名callsite必须显式更新同一设计/测试。另一个allowlist枚举所有只含`session_id`的ordinary `wake_queue_promotion(...)` callsite，只允许non-terminal governance / recovery reconciliation与`open_host` coordinator内部optional promotion；terminal producer qualified function内出现直接调用即失败。runtime fake port逐producer证明commit result exact sequence确实进入所属 opener 的本地 port，三组non-Engine A/B barrier证明本地 promotion 无 bypass。该三层证据只关闭本地 producer 接线 / promotion 顺序，不声称它单独证明跨 opener watcher completeness；跨 opener correctness 由 candidate / entry fence、EventLog catch-up 与双 opener barrier 独立验收。

## Future WU Non-goals

- 不修改 `docs/engine/design.md` 或 Engine public delta contract。
- 不给 transient delta 增加 EventLog row、cursor、ack、replay、retention 或跨 runtime 恢复。
- 不把 terminal watermark / handoff barrier持久化，也不建立 durable / transient 跨域总序或 cursor。`durable_causal_fence_event_sequence` 只引用已有 EventLog domain 的 `Attempt.started_event_sequence`，不是第三 sequence domain。
- 不为 opener-local notice 建立跨进程广播或消息系统；它只负责本地低延迟 wake 与 optional promotion coordination，不替代 durable causal fence / periodic reconciliation。
- 不暂停 promotion、Agent 或 Engine等待 watcher，不让 Service缓存 / 预读 B event；B只可留在 Host counted mailbox。
- 不改变 Run / Attempt / terminal / Outbox owner。
- 不把 delivery policy 放入 per-Run request、metadata、extra payload、UI fallback 或 per-subscription override。
- 不在缺少 workload / SLO 证据时写死新的 items / bytes / max-subscriptions packaged 数字。
- 不把 per-Session `cap × per-subscription budget` 夸大为跨 Session Host 总内存 guarantee，也不设计 Host-global quota 或消息系统；multi-watcher、session admission / aggregate contract 已冻结，实施 WU 不得重新审计 topology。
- 不实现 silent drop、gap 猜测、payload 截断或 delta 合并。
- 不顺带改变 CLI thinking UX、provider reasoning 开关或三类 delta 的展示选择。

## 直接代码与设计证据

### EngineEvent ingest 已具备正确 handoff seam

- `dayu/host/engine_ingest.py:729-766`：`EngineEventIngestor` 接收 `HostTransientDeltaPublisher` port，没有要求 Service consumer。
- `dayu/host/engine_ingest.py:847-875`：durable transaction 完成后才发布 transient candidate。
- `dayu/host/engine_ingest.py:5227-5273`：ingest 将三类 typed Engine delta 映射成 `ValidatedTransientDeltaCandidate`。
- `dayu/host/engine_ingest.py:5276-5302`：publisher 异常被隔离并转为 sanitized operator diagnostic，不回滚 durable accepted result。

这些证据说明不需要修改 Engine contract；需要修正的是 publisher 下游 delivery ownership 与 configuration。

### 当前 Host / Service 确实存在双重 buffer

- `dayu/host/transient_delta.py:26-29`：Host 私有常量固定 item capacity，并使用原因标签归因 consumer speed。
- `dayu/host/transient_delta.py:187-220`：每个 Host subscription 创建一个 item-only `asyncio.Queue`。
- `dayu/host/transient_delta.py:242-258` 与 `dayu/host/open_host.py:985-986,1000-1001,1012-1013`：`drain_nowait()` 把全部 queue item 转成 tuple，iterator 逐项 `yield` 时会在 mailbox 外长期保留未计量 batch。
- `dayu/host/transient_delta.py:321-336`：publisher 使用 `put_nowait`，满队列时只标记 overflow / detach。
- `dayu/service/entrypoint_runtime.py:68-76`：Service 另有独立固定容量常量。
- `dayu/service/entrypoint_runtime.py:500-511`：`_WatchAndWaitRuntime` 持有第二个 relay queue 与 drain task。
- `dayu/service/entrypoint_runtime.py:1018-1054`：Service attach Host watcher 后再次创建有界 queue，并由 drain task `await queue.put(event)`。

这不是两个 owner 的合理隔离，而是同一 subscription event 的重复缓冲与重复 capacity truth。

### iterator facade 合流边界正确，但当前同步 factory 不能提供可执行 attach

- `dayu/host/open_host.py:905-929`：当前 `watch_session_events` 先注册 transient subscription，调用 `DurableActor.submit(...)` 后立即同步返回 iterator；cursor operation 可以尚未开始。这是必须删除的当前实现，不是未来 contract。
- `dayu/host/_durable_actor.py:106-125`：`submit` 只承诺将该 operation 排在同一 actor 的后续 submit 之前，不与 scheduler connection 或其它进程 writer 建立顺序。
- `dayu/host/read_api.py:450-465`：start cursor operation 在真正执行 transaction 时读取当时最大 sequence。因此“future 已排队”不是 public attach 线性化点；若 terminal 在同步 return 后、cursor transaction 前提交，cursor 会越过它。
- 可执行修复是 async factory：reserve -> await durable cursor transaction -> owner loop 无 `await` attach -> successful return。这使 Session missing / cursor failure 在 factory await 阶段 fail closed，并给同 actor 后续 command 提供唯一可测的生效边界。
- `dayu/host/open_host.py:931-1020`：iterator 当前先 drain transient、再分页读取 EventLog，并在读到 terminal 前再次 drain；因此 A terminal已 commit但 watcher尚未 durable catch-up时，B delta可先被 pop，直接证明 pop 前 causal-fence catch-up 必须改在 Host merge owner。
- `dayu/service/entrypoint_runtime.py:459-489,998-1010`：Service 因 public return type 过宽而自建 closable Protocol 并 `cast`，证明关闭语义 owner 应提升到 Host public contract；调用点必须随 Host 一起改为显式 `await`。

设计保留该 public facade 与合流职责，只移除重复 mailbox，把 attach 线性化改为真正执行的 async factory。

### 跨 opener causal fence 的直接证据

- `dayu/host/open_host.py:1452-1519`：每个 opener 分别打开 durable handle / event loop、创建独立 `HostTransientDeltaHub`并装配本地 scheduler / actor。opener-local notice 没有跨进程 fanout。
- `dayu/host/engine_ingest.py:1120-1235`：durable validation transaction 已同时读取当前 Run、Attempt 与 dispatch record，并确认 `run.current_attempt_id`、`attempt.execution_id` 等 identity / late-state 前置；因此 `context.attempt.started_event_sequence` 是 candidate fence 的直接同源输入，无需另开 transaction 或猜测。
- `dayu/host/durable/schema.py:1256-1264`：SQLite partial unique index 保证同一 Session 只有一个 active / start-blocking Run。前序 A 只有在 terminal transaction 提交并释放 active slot 后，后续 B 才能创建 Attempt start fact，所以 `A.terminal_event_sequence < B.attempt.started_event_sequence`。
- 上述顺序完全位于共享 EventLog / durable state，不依赖 A 所属 opener 的 notice 被 C watcher 收到。publisher 把 B candidate fence 原样复制到 C subscription entry后，C 在 pop 前追赶 fence 必然先遇到 A terminal。

### 非 Engine terminal producer 直接证明共同 port 必需

- `dayu/host/admission.py:753-787,836-867,1647-1989,2189-2347,4167-4199,4576-4587`：pre-dispatch / waiting / recovering cancel与通用closeout在write commit后直接用`session_id`唤醒promotion；queued / session cancel和terminal idempotent replay同样能返回Session-visible terminal，却没有统一exact sequence handoff。`CancelRunResult.released_active_slot`已提供flag的transaction-local owner，不能在commit后重猜。
- `dayu/host/waiting.py:367-443,750-841,1007-1074,1210-1346,1349-1528,2510-2540`：failed / lost / expiry transition的Run row带exact `terminal_event_sequence`，外层result却只携带`queue_promotion_session_id`并直接普通promotion；幂等replay也在同一transaction读取exact terminal Run，证明无需latest-row readback。
- `dayu/host/dispatch.py:435-444,1153-1220,1862-1895,3745-3789`：active-cancel watchdog batch把terminal压成`closed_session_ids`，pre-start failure丢弃transition result，worker-startup closeout transaction返回`None`；三者都需要保留exact notice，batch不得按Session折叠。
- `dayu/host/recovery.py:146-235,328-347,422-474,553-625`：startup recovery把ordinary accepted / queued promotion与terminal lost都投影到action / Session集合，当前没有逐terminal after-commit contract；recovering limit lost与unrecoverable orphan closeout是可达terminal producer，不是未来audit假设。
- `dayu/host/engine_ingest.py:2716-2789`：成功或duplicate lifecycle terminal commit后，`_with_terminal_promotion_retry(...)`仍只接收`session_id`并直接普通promotion，证明即使Engine路径也必须让transaction result携带exact notice。
- `dayu/host/open_host.py:287-340,1485-1519` 与 `dayu/host/command.py:762-826,885-905`：现有loop bridge和composition root足以承载single coordinator，但waiting command目前只注入普通scheduler wakeup port。正确改法是新增独立terminal port并在composition root显式注入，不是扩张Service或Engine contract。

这些路径共同证明`CODEX-CLOSURE-REREVIEW-F01`是producer闭环缺口，不是单一文件漏测；实施授权必须穷举当前call graph并以静态manifest守住未来writer。

### 当前 topology / fence / callback 直接证据

- `dayu/host/transient_delta.py:187-336`：每个 subscription 使用独立 queue，并用会随历史 Run 增长的 `_terminal_run_ids: set[str]` 做 fence；本修订删除该历史 set，以 current-terminal yield fence 处理 Service handoff，以每 entry 的 durable Attempt-start causal fence 处理跨 opener 顺序；post-terminal truth 继续由 ingest late-state validation 拥有。
- `dayu/host/transient_delta.py:388-475`：Hub 以 Session -> subscription set 支持多 watcher并同步遍历 fanout；`tests/host/test_watch_session_events.py:451-541` 明确建立两个 watcher 并验证相同 terminal / transient，multi-watcher 已是当前 contract，不存在待 audit 的 topology 分支。
- `dayu/service/entrypoint_runtime.py:1036-1054,1157-1212,1215-1297,1639-1668`：drain task 只把 exception 包成 queue item，normal EOF 不 signal；callback 在另一个 queue consumer 路径同步抛出；startup 又依赖 queue 保存多个目标结果。删除 relay 后必须由 sole consumer 的 closed result union 与 generation handshake统一 owner。
- `dayu/host/open_host.py:1460-1493` 与 `dayu/host/dispatch.py:3387-3397,3887-4090` 表明 delivery / Engine consumer 共用 opener event loop，因此 no-backpressure 只能承诺不等待被动 consumer / capacity，不能承诺阻塞 callback 的物理隔离。

### `max_items` 无法证明 byte bound

- `dayu/host/api.py:2878-2971`：三类 public delta 只校验字符串类型，没有长度或 byte 上限。
- `dayu/engine/contracts/engine_events.py:125-198`：Engine `ContentDeltaData`、`ReasoningDeltaData`、`ToolCallDeltaData` 同样没有单事件 byte bound。
- `dayu/engine/runners/openai/sse_parser.py:96-97,155-215,295-315`：特定 OpenAI SSE adapter 有行字符数与 data line 数保护，但它是 parser-local implementation，不是跨 Runner Engine contract，且字符数不等于 UTF-8 byte 数。

因此，本设计选择 subscription-level `max_bytes`，无需把 Host delivery policy 反向泄漏到 Engine。

### 两份设计真源与只读总控边界

- `docs/engine/design.md:28-38,513`：Engine 只拥有本次 generator 顺序，不拥有 Host fanout、EventLog、cursor 或 replay；本 correction 与该 contract 一致，无需修改 Engine 设计。
- `docs/host/design.md` 原有 fixed capacity / Host delivery owner 表述与用户裁决冲突，本次已在 Host 真源内纠正。
- `docs/host/issues-implementation-control.md:153-202,246-256,353-397` 只用于核对当前 WU 与既有 residual 记录；本次未修改主总控。

## 验证

本次只修改设计与 artifact，不修改 Python、测试、schema 实现或 README。验证结果：

- stale wording scan覆盖同步 factory、pending cursor future、eager / atomic attach、attach-before-return、opener-local notice作为全局唯一 correctness source、AST跨 opener完备，以及transaction后latest/max readback等旧表述；命中项只允许出现在“当前错误证据”或“删除 / 禁止”上下文，不作为最终contract残留。
- frozen-decision scan覆盖per-candidate / per-entry `durable_causal_fence_event_sequence`、same-validation-transaction当前`Attempt.started_event_sequence`、publisher原样复制、pop前bounded multi-page catch-up、mailbox空时periodic durable reconciliation、双opener共享DB且无本地notice barrier，以及async factory successful-return边界、同actor后续command、delayed-cursor barriers、Host Protocol / Service / CLI显式`await`。此前single Host mailbox + counted in-flight、三维容量、overflow primary order、exact-five、cleanup、全terminal producer typed notice与本地A→B fence仍保持覆盖。
- `git diff --check`与两份未跟踪目标artifact的`git diff --no-index --check`均无whitespace diagnostic。
- `source .venv/bin/activate && pyright`：pass，`0 errors, 0 warnings, 0 informations`。
- changed-file boundary：本轮只写入`docs/host/design.md`、本原设计记录与新final-closure-fix artifact；未修改`dayu/`、`tests/`、总控、README或其它既有review artifact，工作区其它既有未跟踪文件保持输入状态。
- 未运行测试：本gate仅修改设计文档，没有代码 / 测试行为变更；未来implementation tests已经作为同一WU acceptance冻结。

## Remaining decisions and risks

Controller 接受的两个高严重度 findings 均已关闭：

1. `TerminalPostCommitPort` 已明确降为producer所属opener的本地terminal-ready低延迟wake与optional queue promotion coordinator；跨opener correctness由same-validation-transaction取得的Attempt start causal fence、per-entry原样复制、pop前bounded-page durable catch-up与mailbox空时periodic reconciliation共同拥有，不依赖跨进程ephemeral notice。
2. public watch 已冻结为真正可执行的async factory；reserve、真实cursor transaction、owner-loop无await attach与successful return构成唯一生效协议，delayed-cursor / gap / cancellation / failure / Host close的确定性tests与Host Protocol、Service、CLI、类型测试授权均已写入同一implementation WU。

此前single Host mailbox + counted in-flight、无Service relay、三维容量、overflow primary order、exact-five、cleanup、所有terminal producer typed notice与本地A→B fence全部保留。packaged capacity测量、heap margin、低基数metrics以及Service / UI callback快速同步非阻塞证据都属于同一implementation WU acceptance，不是residual或后续自由裁量项。

`design residual = 0`；未归属residual为`0`；没有blocking或non-blocking open question。下一步必须对本次修订执行独立三路re-review，不直接进入implementation。

## Review Target

后续 reviewer 只需审查本 design correction，重点验证：

- `HostSessionEventDeliveryPolicy` 是否含三个 required 正整数字段并由 runtime composer / operator 显式装配，且没有 Host / Service 隐式 fallback。
- 每个 subscription 是否严格只有一个 transient mailbox + 唯一 in-flight，是否删除 batch drain并让 mailbox + in-flight 共用一个 retained budget。
- public contract 是否是显式可关闭的async factory，是否严格执行reserve -> await真实cursor transaction -> owner-loop无awaitattach -> successful return，并精确处理cursor / attach / allocation失败、取消与Host close；`TerminalPostCommitPort`是否只承诺producer所属opener的本地wake / optional promotion，而未冒充跨opener correctness source。
- Service 是否删除私有 cast，并遵守 sole `anext` + exact-five result、generation ack/rebind、五类 caller disposition、stop / cancellation first arbitration、cleanup precedence与 best-effort sanitized diagnostic。
- EngineEvent ingest 是否完全不知道 capacity / overflow policy，Host publish 是否不等待被动 consumer / mailbox capacity，且没有夸大同-loop callback 的物理隔离。
- items / bytes 双界、in-flight accounting 与四组 exact primary-dimension fixtures 是否足以关闭内存边界缺口。
- `resource_exhausted` attach rejection、reservation全释放路径、delivery-specific overflow error、per-entry causal fence、bounded-page durable catch-up、mailbox空时periodic reconciliation、仅delivery interruption使用Outbox degraded recovery、detach / Host close与既有两个sequence domain是否自洽。
- Future WU scope 是否覆盖admission、waiting、recovery、engine ingest、dispatch、open_host、command、Host Protocol、Service await、CLI adapters、typed transition/result与对应类型/tests；AST callsite manifest是否只证明本地producer接线，双opener共享DB无本地notice、多页catch-up与periodic reconciliation是否独立证明跨openercorrectness；pre-dispatch cancel、wait failed、wait expiry三组本地A/B barrier及duplicate / no-promotion / ordinary-promotion cases是否exact。
- multi-watcher reservation、batch drain removal、Service callback / EOF / startup barrier、Config assembly、delayed-cursor barriers、packaged capacity / heap / metrics测量、callback快速同步非阻塞验收、README与owner-level tests是否都属于同一implementation WU，且没有越界修改Engine public contract或重开此前closure。
