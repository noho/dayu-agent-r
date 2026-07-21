# WU-CLI-SMOKE-01-R1 Session Event Delivery 最终 Closure Re-Review（MiMo）

## Review metadata

- 生成时间：`2026-07-21 17:23:09 +0800`（本机系统时钟；timestamp：`20260721-172309`）。
- Review 类型：独立、从第一性原理出发的 adversarial closure re-review。
- 结论：**PASS**。
- Material findings：**0**。
- 未归属 residual：**0**。
- Open questions：**0**。
- 本 review 只新增当前 artifact；未修改设计、代码、测试、总控或 README，未提交。

## Reviewed target and scope

本次只读取并审查：

- `docs/host/design.md`（Host 设计真源）；
- `docs/engine/design.md`（Engine 设计真源）；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`（原设计记录）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-codex.md`（final-closure review）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-fix-codex.md`（final-closure fix）；
- `dayu/host` 当前生产代码中与 transient delivery、terminal closeout、cursor attach、durable schema 相关的关键实现路径。

未读取 AgentCodex / AgentDS 本轮 artifact；未把其它 review artifact 当作证据。

## 对抗性验证结果

### 验证 1：durable_causal_fence_event_sequence 同源取得与单 active invariant

**问题**：每个 transient entry 的 `durable_causal_fence_event_sequence` 是否能由同一 ingest validation transaction 的 `Attempt.started_event_sequence` 唯一取得？单 active invariant 是否足以证明前序 Run A terminal < 后继 Run B Attempt start？

**直接代码证据**：

1. `AttemptRow.started_event_sequence: int`（`dayu/host/durable/state.py:340`，NOT NULL）。该字段在 Attempt 创建时由 ATTEMPT_STARTED EventLog append 分配，之后不可变。

2. `_validate_durable_context`（`dayu/host/engine_ingest.py:1144-1177`）在同一 validation transaction 内通过 `read_attempt_by_id(transaction, envelope.attempt_id)` 读取完整 `AttemptRow`。当前代码只校验 identity 字段（`session_id`、`run_id`、`current_attempt_id`、`execution_id`、`dispatch_record_id`），但 `attempt.started_event_sequence` 已在同一 transaction 的读取结果中可用。设计要求提取该值作为 candidate 的 `durable_causal_fence_event_sequence`，这是在同一 transaction 内增加一行字段访问，不引入新 transaction 或回读。

3. 单 active Run invariant（`dayu/host/durable/schema.py:1259-1263`）：
   ```sql
   CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_HOST_RUNS_ONE_ACTIVE_PER_SESSION}
   ON {TABLE_HOST_RUNS}(session_id)
   WHERE status IN ('accepted', 'running', 'waiting', 'cancelling', 'recovering')
   ```
   该 partial unique index 保证同一 Session 同时只有一个 active Run。Run A 从 active 状态转为 terminal 时，同一 transaction 内释放 active slot；此后 Run B 才能被 promotion 创建并分配 ATTEMPT_STARTED event。

4. EventLog append 是单调递增的全局 `event_sequence` 分配（`dayu/host/durable/schema.py` host_events 表）。A 的 terminal event 在 A 的 terminal transaction 内 append；B 的 ATTEMPT_STARTED event 在 B 的 promotion transaction 内 append。由于 A 必须先 terminal 释放 active slot，B 才能 promotion，因此：
   ```
   A.terminal_event_sequence < B.attempt.started_event_sequence
   ```
   这个不等式由 durable schema invariant + EventLog append order 保证，不依赖任何 opener-local notice、内存状态或跨进程通信。

**裁决**：成立。`started_event_sequence` 在同一 validation transaction 内可用；单 active invariant + EventLog append order 保证 A terminal < B Attempt start 的严格不等式。

---

### 验证 2：跨 opener / 跨进程、无本地 notice、多页 catch-up 时是否必然先交付 A 并保留 B

**问题**：watcher 在 opener C，A terminal 由 opener A 提交，C 收不到本地 notice。B entry 携带同 validation transaction 取得的 Attempt start fence。C 是否必然先交付 A terminal 并保留 B entry？

**推理链**：

1. B entry 的 `durable_causal_fence_event_sequence = B.attempt.started_event_sequence`。

2. 每次准备 pop B entry 前，iterator 检查 subscription durable cursor 是否 < B entry 的 fence。若 cursor < fence，必须按 bounded pages 读取 EventLog 直到 cursor >= fence。

3. 由于 `A.terminal_event_sequence < B.attempt.started_event_sequence = B fence`，catch-up 过程中 cursor 必然经过 A terminal event 所在的 EventLog position。

4. 遇到 A terminal 时，iterator 沿既有 terminal fence 单项交付 A terminal（通过 `mark_run_terminal(A.run_id)` 建立 fence），然后停止扫描。

5. A terminal yield 后，Service ack / clear / rebind 后的下一次 `anext()` 才可继续。B entry 原位保留在 counted mailbox 中，继续计入 budget。

6. 关键点：这个机制不依赖任何 opener-local notice、内存 watermark 或跨进程通信。它完全依赖共享 durable EventLog（同一 DB）和 per-entry fence。

**直接代码证据**：

- `dayu/host/open_host.py:905-929`：当前同步 factory 在 opener owner loop 内注册 subscription 并提交 cursor future。
- `dayu/host/open_host.py:931-1020`：`_watch_session_events_after` 先 drain transient、再分页读取 EventLog，遇到 terminal 时调用 `mark_run_terminal` 建立 fence。
- `dayu/host/open_host.py:1452-1463`：每个 opener 打开独立 durable handle / event loop，但共享同一 SQLite DB 文件。
- `dayu/host/durable/schema.py:1259-1263`：单 active Run invariant 保证 A terminal < B Attempt start 的严格顺序。

**裁决**：成立。跨 opener correctness 由共享 durable EventLog + per-entry causal fence + bounded catch-up 保证，不依赖本地 notice。

---

### 验证 3：periodic reconciliation 是否覆盖 mailbox 为空

**问题**：mailbox 为空且无本地 notice 时，长期 watcher 是否能最终发现其它 opener 提交的 terminal？

**直接证据**：

- `dayu/host/open_host.py:1007-1008`：当 EventLog batch 为空时，`await subscription.wait_ready(_SESSION_WATCH_POLL_INTERVAL_SECONDS)` 等待后继续循环。
- 设计明确要求"mailbox 为空时仍执行 bounded periodic durable reconciliation"。

**裁决**：成立。当前实现已有 periodic poll 循环；设计要求保留并强化此路径，确保长期 watcher 在无本地 notice 时仍能通过 durable read 发现 terminal。

---

### 验证 4：TerminalPostCommitPort 是否已正确收窄为 producer opener 本地 wake / promotion

**问题**：`TerminalPostCommitPort` 是否只承担 producer opener 的本地低延迟 wake 和 optional queue promotion，不再冒充全局 correctness source？

**直接证据**：

1. `TerminalPostCommitNotice` 和 `TerminalPostCommitPort` 在当前代码中不存在（grep 确认零匹配）。设计提议创建 `dayu/host/terminal_post_commit.py` 作为 internal contract。

2. 设计明确定义：
   - `TerminalPostCommitPort` 是 producer 所属 `open_host` opener 的内部协调 seam。
   - 它只负责：本地 delivery watermark max-advance + level-trigger wake + flag=true 时按 per-Session O(1) promotion sequence high-watermark 去重并唤醒本地 queue promotion。
   - 它**不**负责：跨 opener watcher correctness、durable terminal delivery cutoff、或替代 EventLog catch-up。

3. 跨 opener correctness 由 durable causal fence（验证 1、2）独立保证。

4. 当前代码中 terminal producer 使用 `wakeup_port.wake_queue_promotion(session_id)`（`dayu/host/admission.py:4587`、`dayu/host/dispatch.py:1217-1220`、`dayu/host/waiting.py:374-375`）。设计要求这些路径改为从 transaction result 携带 exact terminal notice，而非只传 `session_id`。

**裁决**：成立。设计正确地将 `TerminalPostCommitPort` 降级为本地 wake / promotion coordinator，跨 opener correctness 由 durable causal fence 独立保证。本地 producer 闭集、duplicate / optional promotion 仍自洽。

---

### 验证 5：async factory reserve -> await cursor transaction -> owner-loop no-await attach -> successful return 的生效边界

**问题**：async factory 的生效边界是否可实施？cursor 与 return 间 durable/pre-return transient 语义、post-return 不丢、失败/取消/Host close 精确释放、同 actor command ordering 是否完整？

**直接代码证据**：

1. 当前同步 factory（`dayu/host/open_host.py:905-929`）：
   - `subscribe()` 注册 subscription
   - `DurableActor.submit(...)` 提交 cursor operation（只排队，不执行）
   - 立即返回 `_ClosableHostSessionEventIterator`
   - cursor future 在首次 `anext()` 时才 resolve

2. `DurableActor.submit`（`dayu/host/_durable_actor.py:106-125`）只承诺"排在后续 submit command 之前"，不与 scheduler connection 或其它进程 writer 建立顺序。

3. `_SessionLiveEventStartCursorOperation.__call__`（`dayu/host/read_api.py:456-465`）在实际执行 transaction 时读取当前 EventLog 最大 sequence，不是调用时的 sequence。

**设计修复的生效边界**：

| 阶段 | 语义 |
|---|---|
| reserve | owner loop 内同步检查 per-Session subscription cap；cap+1 在任何 I/O 前 fail closed。 |
| await cursor transaction | 实际 await DurableActor 完成 Session existence + start cursor read transaction。cursor snapshot 此时取得。 |
| owner-loop no-await attach | 回到 owner loop 后，在同一无 await 段创建 mailbox subscription、记录 watermark baseline。 |
| successful return | 调用方拿到 iterator。此时 subscription 已真正 attach，cursor 已确定。同 actor 后续 command 必定位于 cursor 之后。 |
| cursor snapshot 到 return 之间 | 由任意连接提交的 durable rows 可由较早 cursor 读到；该间隙内的 transient 是 pre-return live-only，不承诺 replay。 |
| post-return | 由本 opener publisher 发布的 transient 不得因 attach 未完成而丢失（因为 attach 已在 return 前完成）。 |
| 失败/取消/Host close | factory owner 精确一次释放 reservation 和已创建的 partial resources。 |
| 同 actor command ordering | successful return 后提交给同一 actor 的 command 必定位于已完成 cursor transaction 之后（DurableActor 单线程保证）。 |

**裁决**：成立。async factory 的各阶段语义清晰、可实施、可测试。当前同步 factory 的 gap（cursor future 排队 ≠ cursor transaction 执行）是真实问题，async factory 是正确修复。

---

### 验证 6：旧 closure 是否保持

**问题**：统一可关闭 iterator、单 Host mailbox + counted in-flight、无 Service event relay、三维容量、overflow order、exact-five 与 cleanup 等旧 closure 是否保持？

| Closure | 当前状态 | 设计保持 |
|---|---|---|
| 统一可关闭 iterator | `_ClosableHostSessionEventIterator`（`open_host.py:1194`）提供幂等 `aclose()` | 保持，改为 async factory 返回 |
| 单 Host mailbox | `asyncio.Queue(maxsize=256)`（`transient_delta.py:216`） | 保持，改为 items + bytes 双界 policy-driven |
| counted in-flight | 当前无 explicit in-flight accounting | 设计增加唯一 in-flight retained accounting |
| 无 Service event relay | 当前 Service 有独立 relay queue（`entrypoint_runtime.py:500-511`） | 设计要求删除，sole consumer 直接消费 Host iterator |
| 三维容量 | 当前只有 item count（`_TRANSIENT_WATCH_BUFFER_CAPACITY = 256`） | 设计要求 `max_items` + `max_bytes` + `max_subscriptions_per_session` |
| overflow order | 当前只检查 queue full | 设计要求 oversized > item count > cumulative bytes |
| exact-five | 当前 Service observation result 不限于 5 个 | 设计冻结为 `TARGET_TERMINAL` / `DELIVERY_INTERRUPTED` / `ITERATOR_ENDED` / `CALLBACK_FAILED` / `ITERATOR_FAILED` |
| cleanup | 当前 cleanup 顺序不严格 | 设计明确 cleanup precedence 和 primary outcome 不可覆盖 |

**裁决**：成立。所有旧 closure 在设计中保持或强化。当前实现与设计之间的差距是实施范围，不是设计缺陷。

---

### 验证 7：实现文件、类型契约、双 opener 和 delayed-cursor deterministic tests 是否足以裁决

**问题**：设计提出的测试授权是否足以裁决 correctness？

**设计冻结的测试要求**：

1. **双 opener 共享同一 DB barrier**：watcher 与 B 在 opener C，A terminal 由 opener A 提交，C 明确收不到本地 notice；B entry 携带 same-validation-transaction 取得的 Attempt start fence，C 必须通过多页 catch-up 先交付 A terminal 并保留 B entry。

2. **mailbox 为空 periodic reconciliation**：bounded periodic reconciliation 最终发现跨 opener terminal。

3. **delayed-cursor deterministic barriers**：
   - cursor transaction 被阻塞时 factory 尚未 return
   - cursor snapshot 完成到 successful return 之间有 durable commit
   - factory cancellation / cursor error / attach allocation failure / Host close 精确一次释放
   - successful return 后的同 actor command 位于 cursor 之后
   - post-return transient 不因 attach 未完成丢失

4. **AST callsite manifest**：只证明每个 terminal producer 向所属 opener 本地 coordinator 接线，不宣称跨 opener 完备。

5. **既有 acceptance 保持**：pre-dispatch cancel / wait failed / wait expiry 三组本地 A→B barrier、typed notice producer 闭集、duplicate / terminal-no-promotion / ordinary-promotion tests 不得弱化。

**裁决**：成立。测试授权覆盖了所有关键 correctness 路径：跨 opener causal fence、async attach boundary、terminal producer 接线、以及既有 acceptance 回归。AST manifest 的边界声明（只证明本地接线，不宣称跨 opener 完备）是正确的。

---

### 验证 8：是否仍有更简单正确方案或隐藏耦合

**替代方案审查**：

| 方案 | 设计评估 | 本次验证 |
|---|---|---|
| 保留同步 factory + 共享锁 | 拒绝：引入跨线程锁、同步阻塞 SQLite 或第二事件通道 | 同意拒绝。async factory 更简单、可测试。 |
| Service fallback / latest-row readback | 拒绝：增加第二真源或错误耦合 | 同意拒绝。durable causal fence 是唯一真源。 |
| 第三 sequence domain | 拒绝：不需要额外总序 | 同意拒绝。两个 sequence domain（durable EventLog + transient runtime）已足够。 |
| 跨进程 ephemeral broadcast | 拒绝：不持久化、不可靠 | 同意拒绝。共享 durable DB 是正确的跨 opener 通信机制。 |
| terminal marker set / queue | 拒绝：增加持久化复杂度 | 同意拒绝。per-entry fence + bounded catch-up 更简单。 |

**隐藏耦合检查**：

- Engine public contract 不变（`docs/engine/design.md` 确认）。
- Host durable schema 不变（单 active invariant 已存在）。
- Service sole consumer 模式不引入新的 Host 依赖。
- `TerminalPostCommitPort` 是 internal contract，不 public export。

**裁决**：无更简单正确方案，无隐藏耦合。设计选择的 causal fence + async factory 路径是最小、可测试且符合 owner 边界的方案。

---

## Non-findings / closure retained

以下审查点没有 material finding：

- Engine 边界正确；Engine 只承诺单次 generator 顺序，不拥有 Host fanout / cursor / terminal fence。
- `HostSessionEventIterator` public closable Protocol 提升方向正确；不需要 Service 私有 cast / `hasattr` fallback。
- 慢 consumer 只导致其 subscription overflow / detach，publisher 不 await consumer 或 capacity。
- durable rows 不复制进 transient mailbox，Service 也不保留任意 `HostSessionEvent` relay。
- mailbox + in-flight 统一 retained items / bytes accounting、单 event oversized 优先、item-count 其次、cumulative bytes 最后的算法可裁决。
- per-Session reservation 先于 mailbox / cursor / task allocation、overflow prefix 清空前仍占 reservation、全部幂等释放路径的设计足够明确。
- transaction-local exact Run terminal sequence、三字段 notice、`false -> true` 补发、较新 `false` 不吞较旧 `true`、batch 不按 Session 去重等单 opener 规则自洽。
- 当前 terminal producer 文件闭集与代码事实相符。
- exact-five Service disposition、fatal sticky、generation ack / clear / rebind、stop / cancellation 仲裁和 double-failure cleanup precedence 可直接实施。
- packaged items / bytes / max-subscriptions 数值、logical-byte 到 heap margin 及低基数 metrics 字段是同一 WU acceptance measurement，**不是 residual**。

## Open questions

无。所有验证点均已有直接代码证据和设计推理支持，不存在无法裁决的开放问题。

## Residual risks and tracking

- 未归属 residual：**0**。
- items / bytes / subscriptions packaged 值、heap safety margin、低基数 metrics 继续按同一 implementation WU acceptance 测量，不另建 residual。
- 设计 residual = 0。

## Final plan review conclusion

**PASS**。

设计 residual = 0；未归属 residual = 0；open question = 0；material findings = 0。

本次 re-review 从第一性原理出发，对抗性验证了用户指定的全部 5 个维度：

1. **durable_causal_fence_event_sequence 同源取得**：`AttemptRow.started_event_sequence` 在同一 validation transaction 内可用，单 active invariant + EventLog append order 保证 A terminal < B Attempt start 的严格不等式。

2. **TerminalPostCommitPort 收窄**：正确降级为 producer opener 本地 wake / promotion coordinator，跨 opener correctness 由 durable causal fence 独立保证。本地 producer 闭集、duplicate / optional promotion 仍自洽。

3. **async factory 生效边界**：reserve -> await cursor transaction -> owner-loop no-await attach -> successful return 的各阶段语义清晰、可实施、可测试。当前同步 factory 的 cursor future gap 是真实问题。

4. **旧 closure 保持**：统一可关闭 iterator、单 Host mailbox + counted in-flight、无 Service event relay、三维容量、overflow order、exact-five、cleanup 全部保持或强化。

5. **测试授权充分性**：双 opener barrier、delayed-cursor barriers、AST callsite manifest、既有 acceptance 回归足以裁决 correctness。无更简单正确方案，无隐藏耦合。

设计可进入 implementation。
