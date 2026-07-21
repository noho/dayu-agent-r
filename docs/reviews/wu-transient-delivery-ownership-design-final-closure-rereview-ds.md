# WU-CLI-SMOKE-01-R1 Session Event Delivery 最终 Closure Re-Review（DS）

## Review metadata

- 生成时间：`2026-07-21 17:18:11 +0800`（本机系统时钟；timestamp：`20260721-171811`）。
- Review 类型：独立、对抗性 final closure re-review。
- 结论：**PASS**。
- Material findings：**0**。
- Design residual：**0**；未归属 residual：**0**；open question：**0**。
- 本轮只新增本 artifact；未修改设计、代码、测试、总控或 README；未提交。
- 未读取 AgentCodex/AgentMiMo 本轮 artifact。

## Reviewed target and scope

本 re-review 只审查以下来源的最终设计状态：

- `docs/host/design.md`（当前工作区已修改版本，line 1-562）；
- `docs/engine/design.md`（只读参考，未修改）；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`（原始 design correction）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-codex.md`（Codex final closure review，含两个高严重度 findings）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-fix-codex.md`（Codex design fix，关闭两个 findings）；

以及以下直接代码证据（只读，未修改）：

- `dayu/host/open_host.py:900-1020,1445-1524`（当前同步 factory、iterator 合流、opener 独立 hub/scheduler/actor）；
- `dayu/host/transient_delta.py:1-484`（当前 ValidatedTransientDeltaCandidate、HostTransientDeltaHub、HostTransientDeltaSubscription、固定 256 item capacity、batch drain、terminal_run_ids set、slow_consumer error）；
- `dayu/host/engine_ingest.py:385-474,700-766,1120-1177,2710-2790,5220-5303`（EngineIngestResult、_ValidatedCandidate、durable 校验读取 attempt、_with_terminal_promotion_retry 仅使用 session_id、transient candidate 构造与发布隔离）；
- `dayu/host/_durable_actor.py:100-126`（submit 语义：仅同一 actor 后续 command 排队，不跨 writer 线性化）；
- `dayu/host/durable/schema.py:575-694,1257-1263`（Run/Attempt schema 含 started_event_sequence 与 terminal_event_sequence，单 active Run partial unique index）；
- `dayu/host/admission.py:4565-4594`（_promote_after_release 仅用 session_id 调用 wake_queue_promotion）；
- `dayu/host/waiting.py:660-712,1250-1438,2533`（wait result 携带 queue_promotion_session_id，transition 内含 terminal_event_sequence）；
- `dayu/host/dispatch.py:435-446,1118-1224,1862-1895,3745-3789`（closed_session_ids、wake_queue_promotion 逐 session、_fail_unstarted 丢弃 transition result）；
- `dayu/host/recovery.py:340,454`（recovery lost 路径）；
- `dayu/service/entrypoint_runtime.py:67-76,485-511,1010-1055`（_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY、_WatchAndWaitRuntime 第二条 relay queue、drain task）。

## Adversarial verification dimensions

### 1. 每个 transient entry 的 causal fence 唯一真源、单 active 不变量、跨 opener 顺序与 periodic reconciliation

**Claim under test**：每个 transient entry 的 `durable_causal_fence_event_sequence` 能否由同一 ingest validation transaction 的 `Attempt.started_event_sequence` 唯一取得；单 active invariant 是否足以证明前序 Run A terminal < 后继 Run B Attempt start；跨 opener/跨进程、无本地 notice、多页 catch-up 时是否必然先交付 A 并保留 B；periodic reconciliation 是否覆盖 mailbox 为空。

**直接代码证据**：

1. `AttemptRow.started_event_sequence` 是 `NOT NULL` 整数字段（`dayu/host/durable/schema.py:677`），在 ingest validation transaction 中随 `_ValidatedCandidate` 一并读取（`engine_ingest.py:1144-1177`，`_validate_durable_context` 返回包含 `attempt: AttemptRow` 的上下文）。同一 transaction 已持有该值，无需另开 transaction 或 post-commit readback。

2. 单 active Run 不变量由 `INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION`（`schema.py:1259-1263`）在 SQLite 层强制：`WHERE status IN ('accepted','running','waiting','cancelling','recovering')`。前序 Run A 必须在其 terminal transaction 中把 status 移出 active 集合并写入 `terminal_event_sequence`（`schema.py:590-591`），后续 Run B 才能通过 admission 创建新的 Attempt start fact（`schema.py:637-638` 要求 `started_event_sequence IS NOT NULL` 对 active status 强制）。因为 EventLog `event_sequence` 单调递增，且 start fact 在 terminal 之后写入，所以 `A.terminal_event_sequence < B.attempt.started_event_sequence` 在同一个共享 SQLite DB 内严格成立。

3. 当前 `_watch_session_events_after`（`open_host.py:964-1020`）先把 transient drain 清空、再 durable poll，这确实允许 B delta 在 durable reader 追到 A terminal 前被 pop——这是原 finding 01 的正确反例。修订后的 entry-fence-before-pop 协议（`docs/host/design.md:390`）改为：pop 前先读 entry fence，若 cursor 落后则 bounded-page catch-up 到 fence，遇 terminal 时只交付 mailbox 头部同 Run prefix 并保留首个不同 Run entry。这条路径完全基于 EventLog 的 durable order，不依赖跨 opener ephemeral notice。

4. Mailbox 为空时的 periodic bounded durable reconciliation（`docs/host/design.md:392`）保证没有 transient entry 时长期 watcher 仍能发现其它 opener 提交的 terminal。这是对原有 `wait_ready` + `_SESSION_WATCH_POLL_INTERVAL_SECONDS`（`open_host.py:1008`）的超时轮询机制的语义增强：原来只等待 transient ready，修订后要求即使 mailbox 为空也定期 bounded reconcile EventLog。

5. `ValidatedTransientDeltaCandidate` 当前不含 `durable_causal_fence_event_sequence` 字段（`transient_delta.py:114-171`）。这是设计明确要求在未来实施 WU 添加的字段（`docs/host/design.md:535`），它与现有 validation transaction 的 `context.attempt.started_event_sequence` 是一对一同源映射。不存在"必须从另一个 transaction 读取"或"需要猜测"的 gap。

**裁决**：成立。证据链完整：schema 提供字段真源 → validation transaction 已读取 → 单 active invariant 由 SQLite partial unique index 保障 → causal inequality 从 EventLog monotonic sequence 推出 → entry-fence-before-pop + periodic reconciliation 不依赖跨进程 notice。无 material finding。

### 2. TerminalPostCommitPort 正确收窄为本地 wake/promotion

**Claim under test**：TerminalPostCommitPort 是否已正确收窄为 producer opener 本地 wake/promotion，不再冒充全局 correctness source；本地 producer 闭集/duplicate/optional promotion 是否自洽。

**直接代码证据**：

1. 当前 `open_host.py:1452-1519`：每个 `open_host` 创建独立的 `HostTransientDeltaHub`（`transient_delta_hub = HostTransientDeltaHub()`，line 1460）、独立的 `HostDispatchScheduler`（line 1485）、独立的 `DurableActor`（line 1503）和独立的 `_ThreadsafeSchedulerWakeupPort`（line 1495）。这些组件之间没有跨进程 fanout 机制。证明本地 port 天然无法向其它 opener 传播 notice。

2. 修订后设计（`docs/host/design.md:380`）明确："实现 owner 是 producer 所属 open_host opener 内的 terminal post-commit coordinator；它只负责该 opener 的本地 terminal-ready 低延迟 wake 与 optional queue-promotion coordination，不是其它 opener / 进程 watcher 的 correctness source"。

3. 本地 coordinator 的三个无 `await` 步骤（`docs/host/design.md:380`）：watermark max-advance → terminal-ready wake → optional promotion。同 sequence duplicate 幂等（O(1) scalar 比较），`false -> true` 补发规则（先到的 false 不推进 promotion scalar，同 sequence 稍后首次 true 可补发），较新 false 不吞较旧 true（promotion scalar 只由实际处理的 true 推进）。这些规则在单 opener 同步调用栈内自洽。

4. 终端 producer 闭集（`docs/host/design.md:547-553`）覆盖 admission / waiting / engine ingest / dispatch / startup recovery 五个当前可达 owner。每个 owner 在当前代码中确实产生 Session-visible terminal（admission:4565-4594; waiting:1250-1438; engine_ingest:2716-2789; dispatch:1174-1224,3745-3789; recovery:340,454）。

5. 当前代码的 gap：`engine_ingest.py:2765-2789` 的 `_with_terminal_promotion_retry` 仅接收 `session_id` 并直接调用 `wake_queue_promotion(session_id)`，未携带 exact sequence。`admission.py:4573,4587` 同理。`dispatch.py:1217-1220` 用 `closed_session_ids` 逐 session 调用 promotion。这些路径没有 exact sequence——这正是设计要求修正的（`docs/host/design.md:531-536`）。

6. 修订后的 port（`docs/host/design.md:376-378`）要求每个 terminal transaction result 携带 exact `TerminalPostCommitNotice(terminal_event_sequence, wake_queue_promotion)`。

**裁决**：成立。Port scope 已正确收窄，本地自洽规则完备，producer 闭集与代码事实一致。当前代码中的 session_id-only promotion 是设计正确识别的待修正点，不是设计本身的漏洞。无 material finding。

### 3. Async factory 生效边界可实施性

**Claim under test**：async factory reserve → await 实际 cursor transaction → owner-loop 无 await attach → successful return 的生效边界是否可实施；cursor 与 return 间 durable/pre-return transient 语义、post-return 不丢、失败/取消/Host close 精确释放、同 actor command ordering 是否完整。

**直接代码证据**：

1. 当前同步 factory（`open_host.py:905-929`）先 `subscribe()` 注册 transient subscription（line 915）、然后 `DurableActor.submit(...)` 仅排队 cursor operation（line 917-919）、立即同步返回 iterator（line 924-929）。`DurableActor.submit`（`_durable_actor.py:106-125`）的精确语义是"把 cursor attach 排在后续 submit command 之前"——它只保证同一 actor 内的 operation 排队顺序，不与 scheduler connection、wait poller connection 或其它进程的 SQLite writer 构成线性化点。证明原 finding 02 的反例成立。

2. 修订后的 async factory（`docs/host/design.md:386,400`）要求：先在 owner loop reserve → await `DurableActor` 完成实际 start cursor transaction → 回 owner loop 无 `await` 段创建/注册 subscription + 记录 watermark baseline → return。successful await return 是生效边界。

3. cursor snapshot 到 return 之间的 gap（`docs/host/design.md:386`）：该间隙内由任意连接提交的 durable rows 可从较早 cursor 读到（因为 cursor 在 gap 前已执行完毕）；该间隙内的 transient 属于 pre-return live-only 数据，不承诺重放。successful return 之后由本 opener publisher 发布的 transient 不得因 attach 未完成而丢失——因为 attach（subscription 注册）已在 return 前完成。

4. 失败路径（`docs/host/design.md:400`）：cursor transaction 失败、Session missing、factory cancellation、attach/iterator allocation 失败、Host close 都必须由 factory owner 精确一次释放 reservation 与已创建的部分资源。successful return 后的 `aclose()`、consumer cancellation、iterator error/EOF、overflow detach 与 Host close 继续由 iterator/subscription owner 精确一次释放。

5. 同 actor command ordering（`docs/host/design.md:386`）：调用方在 successful return 后提交给同一 actor 的 command 必定位于已完成 cursor transaction 之后。这是因为 async factory 在 return 前已经 await 了 cursor transaction 的完成，同一 actor 的后续 submit 排在 cursor transaction 之后是 `DurableActor.submit` 的既有语义。

6. Service/CLI 调用点（`docs/host/design.md:398,541-542`）要求所有 watch 调用显式 `await`，并删除私有 closable Protocol/`cast`。当前代码中 `entrypoint_runtime.py:1026` 的 `_attach_watcher` 调用证明调用点确实需要修改。

**裁决**：成立。Async factory 的生效边界比同步 factory + pending cursor future 更简单、更可测试、更符合 owner 边界。所有 gap/failure/cleanup 路径都有明确的 owner 和 contract。无 material finding。

### 4. 旧 closure 保持

**Claim under test**：统一可关闭 iterator、单 Host mailbox + counted in-flight、无 Service event relay、三维容量、overflow order、exact-five 与 cleanup 等旧 closure 是否保持。

**直接证据**：

| 旧 closure | 当前设计状态 | 证据位置 |
|---|---|---|
| 统一可关闭 async iterator 外观 | 保留，factory 改为 async | `docs/host/design.md:342,398` |
| 单 Host mailbox + 唯一 in-flight | 保留，删除 batch drain | `docs/host/design.md:402` |
| 无 Service event relay | 保留，删除 `_WatchAndWaitRuntime.queue` 与 drain task | `docs/host/design.md:445,541` |
| 三维容量（items/bytes/subscriptions） | 保留，required 正整数 policy | `docs/host/design.md:404` |
| Overflow primary order | 保留，oversized → item count → cumulative bytes | `docs/host/design.md:414` |
| Exact-five Service observation result | 保留，五成员 closed union + fatal sticky + generation handshake | `docs/host/design.md:447-459` |
| Cleanup precedence | 保留，primary outcome + cause chain + sanitized diagnostic | `docs/host/design.md:459,520` |
| 所有 terminal producer typed notice | 保留，producer 闭集 + AST manifest | `docs/host/design.md:547-555` |
| 本地 A→B fence | 保留，watermark → wake → optional promotion 顺序 | `docs/host/design.md:380-384` |

**裁决**：成立。所有旧 closure 均在修订后设计中保留且未被弱化。无 material finding。

### 5. 实施文件、类型契约与测试授权是否足以裁决，是否有更简单正确方案或隐藏耦合

**Claim under test**：实施文件是否覆盖全部修改面、类型契约是否完整、双 opener 和 delayed-cursor deterministic tests 是否足以裁决，是否仍有更简单正确方案或隐藏耦合。

**直接证据**：

1. 未来实施 WU scope（`docs/host/design.md:526-561`）覆盖 14 个 owner/consumer 文件修改面 + 测试更新 + README 触发 + 旧术语迁移。每项都有具体修改描述。

2. 类型契约：
   - `HostSessionEventIterator` Protocol 含 `__aiter__`、`__anext__`、`aclose()`（`docs/host/design.md:398`）
   - `HostSessionEventDeliveryPolicy` 三个 required 正整数字段（`docs/host/design.md:404`）
   - `TerminalPostCommitNotice` 三个精确字段（`docs/host/design.md:364-367`）
   - `Host.watch_session_events` 返回 `Coroutine[..., HostSessionEventIterator]`（`docs/host/design.md:526`）
   - Service observation result five-member closed union（`docs/host/design.md:447-455`）

3. Deterministic tests frozen as acceptance（`docs/host/design.md:543`）：
   - 双 opener 共享 DB barrier：watcher 与 B 在 opener C，A terminal 由 opener A 提交且 C 无本地 notice；B entry 携带 Attempt start fence；C 多页 catch-up 先交付 A 并保留 B entry
   - Mailbox 为空 + 无本地 notice → periodic reconciliation 最终发现跨 opener terminal
   - Delayed-cursor barriers：cursor transaction 被阻塞时 factory 不得 return；cursor snapshot 完成到 return 之间 durable commit 可读；factory cancellation/Host close/allocation failure 精确一次释放；successful return 后同 actor command 位于 cursor 之后
   - Non-Engine 本地 A/B barriers：pre-dispatch cancel A + queued B、wait failed A + queued B、wait expiry A + queued B
   - Overflow exact-four fixtures、AST qualified-callsite manifest、Service exact cleanup 七组 double-failure tests

4. 更简单正确方案评估：
   - **跨进程 ephemeral broadcast**：增加消息系统依赖，不持久，重启丢失，过度设计。拒绝。
   - **Durable transient replay**：违反 live-only 边界，引入 amplification。拒绝。
   - **保留同步 factory + cross-writer 线性化**：需要锁或 shared cursor，比 async factory 更复杂且引入新的 correctness 依赖。拒绝。
   - **Latest-row readback**：创建第二真源。拒绝。
   - 当前方案（causal fence 来自同一 validation transaction + async factory + EventLog bounded catch-up + periodic reconciliation）是满足所有约束的最简方案。

5. 隐藏耦合检查：
   - Entry fence 引用 `Attempt.started_event_sequence`，该值由 Engine ingest validation transaction 唯一产生 → fence owner = ingest validation，消费者 = Session Event Delivery merge。单向依赖，无循环。
   - `TerminalPostCommitNotice.terminal_event_sequence` 由 write transaction result 唯一产生 → notice owner = terminal producer transaction，消费者 = local coordinator。单向依赖，无循环。
   - Async factory 的 cursor transaction 由 `DurableActor` 执行 → cursor owner = durable read，消费者 = subscription attach。单向依赖，无循环。
   - 本地 watermark 是 opener-local runtime hint → 不持久化，不跨 opener，不替代 durable truth。耦合度为零。
   - Service observation-result slot 由 sole consumer first-commit → 唯一消费者，不与其它 component 共享可变状态。耦合度为零。
   - 没有发现跨 owner 双向依赖、共享可变状态或过宽公共契约。

**裁决**：成立。实施文件覆盖完整，类型契约闭合，deterministic tests 足以裁决所有 correctness claim，当前方案是满足约束的最简方案，无隐藏耦合。无 material finding。

## Architecture / best-practice / optimality / overengineering review

- **Architecture boundary**：所有 owner 边界清晰。Engine 不变；Host ingest 拥有 candidate identity/fence；Session Event Delivery 拥有 mailbox/fanout/fence-check；TerminalPostCommitPort 拥有本地 wake/optional promotion；EventLog 拥有 durable truth 与 catch-up reader；Service 拥有 sole consumer/observation result。无跨层穿透。
- **Best practice**：bounded mailbox + non-blocking offer（不反压 producer）、typed disconnect（不 silent drop）、同事务 exact fence（不需 lock/readback）、closed result union + deterministic race tests（不依赖 timing）、async factory explicit linearization point（不依赖"已排队"隐含语义）均符合工程最佳实践。
- **Optimal solution**：不需要 message broker、第三 sequence domain、global quota、terminal marker set 或 Service fallback。Host-internal causal fence + bounded durable polling + async attach factory 是比跨进程 broadcast、durable replay 或锁/readback 更简单、可测试且保持 live-only 语义的方案。
- **Overengineering**：items/bytes/subscriptions 三维 policy 由真实 failure mode 支撑（item count 不约束 byte、byte 不约束 watcher count）；five-member Service result 由五种互斥观察结果支撑；per-Session reservation 由 multi-watcher contract 支撑。均不构成 overengineering。
- **Overcoupling**：未发现跨 owner 耦合。Entry fence 只引用已有 EventLog domain 的 `Attempt.started_event_sequence`，不是新 sequence domain；TerminalPostCommitPort 已从"全局 correctness source"降为"本地 optimization coordinator"。

## Non-findings

以下审查点经对抗性验证，确认无 material finding：

- `HostSessionEventIterator` public closable Protocol 提升方向正确。
- 慢 consumer 只导致其 subscription overflow/detach，publisher 不 await consumer 或 capacity。
- Durable rows 不复制进 transient mailbox，Service 不保留任意 HostSessionEvent relay。
- Mailbox + in-flight 统一 retained accounting，单 event oversized 优先、item-count 其次、cumulative bytes 最后的算法可裁决。
- Per-Session reservation 先于 mailbox/cursor/task allocation、overflow prefix 清空前仍占 reservation、全部幂等释放路径的设计明确。
- Transaction-local exact Run terminal sequence、三字段 notice、`false -> true` 补发、较新 false 不吞较旧 true、batch 不按 Session 去重的单 opener 规则自洽。
- 当前 terminal producer 文件闭集与代码事实相符。
- Exact-five Service disposition、fatal sticky、generation ack/clear/rebind、stop/cancellation first arbitration 和 double-failure cleanup precedence 可直接实施。
- Packaged items/bytes/max-subscriptions 数值、logical-byte 到 heap margin 及低基数 metrics 字段是同一 WU acceptance measurement，不是 residual。
- Service/UI callback 快速同步非阻塞、慢 I/O/CPU/renderer 显式解耦是同一 WU acceptance。

## Final plan review conclusion

**PASS**。

经过对所有五个维度的对抗性验证，直接代码证据与设计文档一致证明：

1. **Causal fence**：`Attempt.started_event_sequence` 在同一 ingest validation transaction 中可唯一取得；单 active invariant（SQLite partial unique index）严格保证 `A.terminal_event_sequence < B.attempt.started_event_sequence`；entry-fence-before-pop + bounded-page catch-up + periodic reconciliation 不依赖跨进程 notice 即可保证跨 opener A→B 顺序。

2. **TerminalPostCommitPort**：已正确收窄为 producer 所属 opener 的本地 wake/promotion coordinator；不再冒充全局 correctness source；本地 producer 闭集、duplicate 幂等、`false->true` 补发与 optional promotion 规则自洽。

3. **Async factory**：reserve → await cursor → no-await attach → successful return 构成唯一可测试的生效边界；cursor/return 间 gap 语义明确；post-return 不丢、失败/取消/Host close 精确释放、同 actor command ordering 路径完整。

4. **旧 closure**：统一可关闭 iterator、单 Host mailbox + counted in-flight、无 Service event relay、三维容量、overflow order、exact-five、cleanup 全部保持且未被弱化。

5. **实施授权**：14 个文件修改面 + 类型契约 + deterministic tests（双 opener、delayed-cursor、本地 A/B、overflow exact-four、AST manifest、Service double-failure）足以裁决所有 correctness claim。当前方案是满足所有约束的最简方案，无隐藏耦合。

**Design residual = 0**；**未归属 residual = 0**；**open question = 0**。

两个 final closure findings（跨 opener causal fence + async factory attach boundary）均已在设计 owner 层正确关闭，关闭方案有直接代码证据支撑且是满足约束的最简方案。设计状态为 `ready-for-implementation`。

## Post-review recommendations

1. 进入 implementation WU 前，确认 `ValidatedTransientDeltaCandidate` 新增 `durable_causal_fence_event_sequence: int` 字段时，`transient_delta.py:115` 的 `__post_init__` 校验必须同步更新（非 bool 正整数，不进入 public `HostTransientDelta` 或 logical-byte traversal）。

2. 确认 `_with_terminal_promotion_retry`（`engine_ingest.py:2765`）替换为 `TerminalPostCommitPort.notify_terminal_post_commit` 时，transaction result 必须先于 promotion 携带 exact `terminal_event_sequence`；`_ValidatedCandidate`（`engine_ingest.py:411`）已含有 `attempt: AttemptRow`，但 terminal sequence 需要从 transition result 获取，不在 candidate context 内。实施时注意区分 `attempt.started_event_sequence`（causal fence 来源）与 `terminal_event_sequence`（terminal notice 来源）——它们是同一个 EventLog domain 的不同 event。

3. 双 opener deterministic barrier 的 page size 必须小于 A terminal 到 B entry fence 之间的 EventLog row 间距，否则单页就读完全部 rows 会掩盖 bounded-page 逻辑的正确性。
