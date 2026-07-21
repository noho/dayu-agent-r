# WU-CLI-SMOKE-01-R1 Session Event Delivery 最终 Closure Review（DS）

## 审查元数据

- **审查类型**：独立、从第一性原理出发的 closure review。
- **审查目标**：最终 Session Event Delivery 设计，冻结于 `docs/reviews/wu-transient-delivery-ownership-design-codex.md`（原设计）与 `docs/reviews/wu-transient-delivery-ownership-design-closure-rereview-fix-codex.md`（第四轮 closure re-review fix），并由 `docs/host/design.md` 第 2 节 Session Event Delivery 边界定义承载。
- **审查日期**：2026-07-21。
- **审查 Agent**：AgentDS（deepreview skill）。
- **审查立场**：constructively adversarial — 默认假设设计至少有一个重要问题，直到证据证明它足够可靠。
- **审查边界**：
  - 读取：`docs/host/design.md`、`docs/engine/design.md`、上述两份 Codex artifact，以及 `dayu/host/` 下全部相关生产代码。
  - 禁止读取：AgentCodex/AgentMiMo 本轮 artifact。
  - 禁止：修改设计、代码、测试、总控或 README。
  - 输出：本 artifact。

## 设计真源确认

设计真源由以下三层构成：

| 层 | 位置 | 职责 |
|---|---|---|
| Host 设计真源 | `docs/host/design.md` §2（Session Event Delivery 边界定义）、§3（`host_runtime.json` 与 `session_event_delivery_policy`） | 模块边界、ownership、public contract shape |
| 最终 Normative Design | `docs/reviews/wu-transient-delivery-ownership-design-codex.md` | 完整 public interface、ownership 表、handoff/mailbox boundary、byte accounting、state/lifecycle、ordering、overflow/degraded/disconnect、durable/transient 边界、aggregate resource boundary、Future WU scope |
| 第四轮 Closure Fix | `docs/reviews/wu-transient-delivery-ownership-design-closure-rereview-fix-codex.md` | TerminalPostCommitNotice/Port contract、transaction-local exact sequence、single coordinator ordering、全 producer manifest、静态 AST acceptance、non-Engine barriers |

Engine 设计真源 `docs/engine/design.md:28-38,513` 确认 Engine 只拥有本次 generator 顺序，不拥有 Host fanout、EventLog、cursor 或 replay — 与本次设计一致，无需修改。

## 代码基线确认

以下直接代码证据确认设计所描述的"before"状态真实存在：

### 双重 buffer（Host + Service）

- `dayu/host/transient_delta.py:26`：`_TRANSIENT_WATCH_BUFFER_CAPACITY: Final[int] = 256` — Host 私有常量。
- `dayu/host/transient_delta.py:216`：`asyncio.Queue(maxsize=_TRANSIENT_WATCH_BUFFER_CAPACITY)` — 每订阅 item-only queue。
- `dayu/service/entrypoint_runtime.py:76`：`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY: Final[int] = 256` — Service 私有常量。
- `dayu/service/entrypoint_runtime.py:1027`：`asyncio.Queue(maxsize=_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY)` — Service relay queue。
- `dayu/service/entrypoint_runtime.py:1028`：`drain_task = asyncio.create_task(_drain_host_events(watcher, queue))` — drain task 做 event-copy relay。

### Batch drain shape

- `dayu/host/transient_delta.py:242-258`：`drain_nowait()` 返回 `tuple[HostTransientDelta, ...]` — 全部 queue item 转成 tuple。
- `dayu/host/open_host.py:985-986,1000-1001,1012-1013`：每轮循环多次 `drain_nowait()` 调用，未计量 batch 留在 mailbox 外。

### 无 byte accounting

- `dayu/host/api.py:2837-2974`：三类 public delta 只校验字符串类型，没有长度或 byte 上限。
- 无 `delivery_size_bytes` helper 存在。

### 无 admission reservation

- `dayu/host/transient_delta.py:415-432`：`subscribe()` 无容量检查，直接 `set().add(subscription)`。

### Unbounded terminal fence

- `dayu/host/transient_delta.py:218`：`_terminal_run_ids: set[str] = set()` — 随历史 Run 无界增长。
- `dayu/host/transient_delta.py:296-305`：`mark_run_terminal()` 只做 `add()`，永不清除。

### 无 TerminalPostCommitNotice / Port

- `grep -rn "terminal_post_commit\|TerminalPostCommit" dayu/host/` 返回空 — 整个 contract 不存在。

### 全部 terminal producer 走 `wake_queue_promotion(session_id)` 绕过 delivery cutoff owner

- `dayu/host/engine_ingest.py:2765-2779`：`_with_terminal_promotion_retry` → `wake_queue_promotion(session_id)`，不携带 exact sequence。
- `dayu/host/admission.py:4573,4587`：直接 `wake_queue_promotion(session_id)`，`CancelRunResult.released_active_slot` flag 未被 delivery 消费。
- `dayu/host/waiting.py:777-778,826-827`：`_wake_queue_promotion_after_commit(result.queue_promotion_session_id)`，仅传 session_id。
- `dayu/host/dispatch.py:1174-1220`：watchdog batch 把多个 terminal 压成 `closed_session_ids: tuple[str, ...]`，逐 session_id 唤醒 promotion。
- `dayu/host/recovery.py:215-235,291-325`：terminal lost 与 ordinary accepted/queued promotion 混合在 `queue_promotion_sessions` 元组中，无逐 terminal after-commit contract。

### Service 私有 ClosableHostSessionEventIterator + cast

- `dayu/host/api.py:3902`：`Host.watch_session_events` Protocol 返回 `AsyncIterator[HostSessionEvent]`，不包含 `aclose()`。
- `dayu/service/entrypoint_runtime.py:459-487`：Service 自建 `ClosableHostSessionEventIterator` Protocol。
- `dayu/service/entrypoint_runtime.py:1007-1009`：`cast(ClosableHostSessionEventIterator, host.watch_session_events(session_id))` — cast 绕过 public contract。

### A→B merge race 可达

- `dayu/host/open_host.py:931-1020`：merge 先 drain transient、再读 EventLog、再 drain transient。A terminal 已 commit 但 watcher 尚未 durable catch-up 时，B delta 可先被 pop 并 yield。
- `dayu/host/engine_ingest.py:2765-2784`：terminal closeout 成功后直接调 promotion wake。
- `dayu/host/dispatch.py:1118-1136,2921-2953`：promotion 由独立 queue/task 推进。

### 无 `session_event_delivery_policy` 配置

- `dayu/config/host_runtime.json`：当前仅包含 store/artifact/sqlite/lane/worker/dispatch/payload/wait_poller 配置，无 `session_event_delivery_policy` 字段。

### Engine contract 一致性

- `dayu/engine/contracts/engine_events.py:125-198`：`ContentDeltaData`、`ReasoningDeltaData`、`ToolCallDeltaData` 无单事件 byte bound — 确认 Host delivery byte bound 不应反向泄漏到 Engine。
- `dayu/engine/runners/openai/sse_parser.py:96-97,155-215,295-315`：SSE parser 有 adapter-local 行字符数保护，但不是 Engine public contract。

## Assumptions Tested

| # | Assumption | 验证结果 |
|---|---|---|
| A1 | 双重 buffer 是同一 subscription event 的重复缓冲，没有两个独立业务事实 | **成立**。Host queue 和 Service queue 承载同一 `HostSessionEvent` 类型。 |
| A2 | `max_items` 单独无法证明 byte bound | **成立**。三类 delta 的字符串字段无 public length/bound，单事件可达 MB 级 reasoning/content。 |
| A3 | 所有 terminal producer 当前绕过 delivery cutoff owner | **成立**。5 个模块均只用 `session_id` 调 `wake_queue_promotion`，不携带 exact sequence。 |
| A4 | A→B merge race 是可达时序 | **成立**。B publish（promotion wake 后）早于慢 watcher EventLog catch-up 是真实并发路径。 |
| A5 | transaction result 可携带 exact terminal_event_sequence | **成立**。`waiting.py:684,2533` 已证明 transaction 内可访问 exact EventLog row/sequence。 |
| A6 | Host construction-time policy 注入优于私有常量 | **成立**。当前 `_TRANSIENT_WATCH_BUFFER_CAPACITY` 是模块级硬编码，调用方不可配置。 |

## Architecture Boundary Review

### Layering

设计严格遵守 `UI -> Service -> Host -> Engine` 分层：

- **Host public contract**：`HostSessionEventIterator`（closable sub-protocol）、`HostSessionEventDeliveryPolicy`（三 required 字段）、`DELIVERY_INTERRUPTED` / `RESOURCE_EXHAUSTED` error codes。
- **Host internal**：`TerminalPostCommitNotice` / `TerminalPostCommitPort`、per-subscription mailbox、admission reservation、terminal coordinator。
- **Service**：删除 relay queue / drain task / 私有 closable Protocol，改为 sole consumer + exact-five observation-result slot。
- **Engine**：不变。

**无反向依赖，无层级泄漏。** `TerminalPostCommitNotice` / `TerminalPostCommitPort` 是 Host-internal contract（不 public export、不持久化），Service 不可见。

### Ownership

设计中的 ownership 表（52 行）覆盖了全部关键语义的 owner 和边界。重点验证：

- **TerminalPostCommitNotice/Port 的唯一 owner**：`dayu/host/terminal_post_commit.py`（未来文件）— 所有 producer 依赖 Protocol，不读取 subscription 或 scheduler 内部状态。单一 coordinator 在 `open_host` opener 内。**无 owner 冲突。**
- **delivery_size_bytes helper 的唯一 owner**：Session Event Delivery — policy、实现、metrics、tests 复用同一 helper。**无多真源风险。**
- **per-Session committed_terminal_event_sequence_high_watermark**：Session Event Delivery — 只做 O(1) max-advance，不是 terminal set 或持久化 cursor。**不越界到 durable truth。**
- ** durable / transient 两个 sequence domain 保持不可比较**：`HostEvent.event_sequence`（durable）与 `HostTransientDelta.runtime_sequence`（transient）继续不可比较。terminal watermark 只是 runtime merge control scalar。**不引入第三套总序。**

### Dependency Direction

- EngineEvent ingest → Session Event Delivery publisher（non-blocking typed handoff）：向下依赖，正确。
- Terminal producers → `TerminalPostCommitPort`：向下依赖（依赖 Host-internal contract），正确。
- `open_host` coordinator → Session Event Delivery watermark：同层协调，正确。
- Service sole consumer → `HostSessionEventIterator`：向下依赖（依赖 Host public contract），正确。

**无循环依赖，无反向依赖。**

## Best-Practice Review

### 可测试性

设计冻结了完整的测试矩阵：

- Owner-level tests：`test_terminal_post_commit.py`（静态 AST manifest + runtime fake port + 三组 non-Engine barriers）。
- Admission/reservation tests：保留既有 retained/admission/overflow fixtures。
- Service tests：七组 double-failure tests + exact-five disposition + cleanup precedence。
- Integration tests：Host → Service → CLI E2E。

**每个 contract 都有对应的 owner-level test，无"只在大集成中验证"的脆弱性。**

### 可维护性

- public contract（`HostSessionEventIterator`、`HostSessionEventDeliveryPolicy`、error codes）是 typed closed enum，consumer 只按 typed code 分支，不解析 message。
- overflow primary dimension 固定算法顺序，不保留"以后再说"的 open question。
- 静态 AST manifest 测试使 future terminal writer 的 bypass 在 compile-time fail closed。
- 旧术语（`slow_consumer`、`session_live_stream`、`UNAVAILABLE + HostUnavailableDetail` overflow 路由）显式删除，不保留兼容 alias/wrapper/双写。

### 可观测性

- overflow、drop、degraded、disconnect 由 delivery/subscription owner 解释，不写 EventLog、不改变 Run/Attempt/terminal。
- 低基数 metrics（至少区分 item/byte overflow、buffer high-watermark、detach）已冻结字段，数据集（不含 payload 正文或高基数 identity）留待测量。
- best-effort sanitized diagnostic（`WATCHER_DIAGNOSTIC`）不包含 cleanup exception type/message/identity/traceback，不泄露内部状态给 LLM。

### Failure Handling

- overflow 只 typed disconnect（`DELIVERY_INTERRUPTED + transient_mailbox_overflow`），不 silent drop-and-continue。
- Service 将 overflow 映射为本地 degraded + durable recovery，不标记 Host outage。
- Run terminal 不结束 session watcher，subscription owner 不合成 terminal。
- Host close 正常结束 iterator（`ITERATOR_ENDED`），不写 `RUN_CANCELLED` / `RUN_FAILED`。

## Optimal-Solution Review

设计在第 1 节（First-principles Alternatives）评估了七种替代方案（A-G），并给出了拒绝理由。

### 独立验证：是否存在比 TerminalPostCommitNotice/Port 更简单且同样正确的方案？

**假设替代方案：纯 merge 侧修复（不修改任何 producer）**

在 merge loop 中，读到 EventLog terminal 后，只 drain 同 Run 的 transient，留不同 Run 的 transient 在队列中。不使用 `TerminalPostCommitNotice`，不修改 producer。

**反例分析**：

1. Terminal A commit → EventLog 写入完成。
2. Queue promotion wake → B run 启动。
3. B dispatch → Engine 产生 B delta → Host publish → B delta 进入 transient queue。
4. Merge loop 读 EventLog page → 发现 terminal A（sequence N）。
5. Merge loop 做 `drain_nowait()` → 此时 B 已在 queue 中，drain 出来的 tuple 包含 B。
6. 即使 merge 按 `run_id` 过滤，B 已经离开 queue（`get_nowait()` 不可逆），无法放回。

**根本原因**：`asyncio.Queue` 不支持 peek。即使改用支持 peek 的自定义 queue，步骤 4-5 之间仍有 race window（B 可在 EventLog read 返回后、queue peek 前入队）。

**结论**：纯 merge 侧修复无法关闭 race window，因为 merge 是被动轮询（poll EventLog），而 publisher 是主动推送（push to queue）。必须有一个同步信号在 B publish 之前设置 fence，这正是 `TerminalPostCommitNotice` 的作用。

**因此，TerminalPostCommitNotice/Port 不是过度设计，而是解决该 race condition 的最小同步原语。**

### 独立验证：是否存在比 items/bytes/subscriptions 三维容量更简单且同样正确的方案？

- 仅 `max_items`：无法约束单事件 payload bytes（一个 reasoning delta 可达 MB 级）。
- 仅 `max_bytes`：无法约束小事件数量（100万个空 delta 耗尽 Python 对象内存）。
- 不加 `max_subscriptions_per_session`：无法防止 watcher 数量放大 memory footprint。

三维各管一个独立维度，缺一不可。**这是最小完整集合。**

## Overengineering Review

### 审查项 1：静态 AST manifest 测试

`tests/host/test_terminal_post_commit.py` 必须从 AST 生成全部 Run-terminal transition callsite 集合并与 manifest exact 比较。

**潜在风险**：AST 测试脆弱——函数改名、代码移动可导致 false positive。
**缓解**：设计明确要求"新增、删除或改名 callsite 必须显式更新同一设计/测试"——这是 fail-closed 机制。此外，runtime fake port tests 和 integration barriers 提供第二、第三层保护。
**判断**：AST 测试是 compile-time bypass detection 的最简实现。Python 缺乏 macro/type-level effect system，AST 是唯一不依赖运行时覆盖率的静态方案。**不是过度设计。**

### 审查项 2：Service exact-five observation result + 详细 cleanup precedence

**潜在风险**：cleanup precedence 规则（primary/cleanup_error chaining、slot first-commit 仲裁、late commit 无效、double-failure 三层 chain）看起来很复杂。
**判断**：这些规则不是凭空增加的——它们精确对应 `asyncio.Task.cancel()` + `AsyncGenerator.aclose()` + `finally` 块在 Python asyncio 中的真实并发语义。当前代码的 task exception / queue item / drain task 混合正是因为缺少这套规则。**这是必要复杂度，不是过度设计。**

### 审查项 3：delivery_size_bytes canonical helper

**潜在风险**：只计算 string field UTF-8 bytes，不计算 Python 对象头——可能被误解为精确内存测量。
**判断**：设计明确声明"不宣称精确等于 Python heap resident bytes"，只约束"未设 public 上限的所有可变字符串 payload"。`max_items` 补充约束对象数量。两个维度共同构成 delivery contract。**不是过度设计。**

## Overcoupling Review

### 检查点 1：TerminalPostCommitNotice 是否把 durable truth 泄漏到 runtime delivery？

否。notice 只携带 `session_id`、`terminal_event_sequence`（来自 durable transaction result）、`wake_queue_promotion`（bool flag）。watermark 是 runtime-only scalar，不持久化。`terminal_event_sequence` 是对 durable truth 的引用（类似 foreign key），不是复制 durable truth。

### 检查点 2：delivery policy 是否把 Host runtime config 泄漏到 per-Run request？

否。policy 是 `open_host` construction-time input，同 opener 的所有 subscription 使用统一 policy snapshot。per-Run request（`SubmitFollowupRequest`）不包含 delivery policy 字段。UI/CLI/subscription 不可覆盖。

### 检查点 3：TerminalPostCommitPort 是否把 scheduler internals 泄漏给 producers？

否。producer 只依赖 `TerminalPostCommitPort` Protocol（单一 `notify_terminal_post_commit` 方法），不读取 subscription、scheduler、mailbox 或 watermark 内部状态。

### 检查点 4：Service exact-five result 是否把 Host internals 泄漏给 caller？

否。result 是 Service-internal closed union，caller 只看到 `TARGET_TERMINAL`（返回 terminal）、delivery recovery 成功（返回 terminal）、或对应 exception。

**无过度耦合。**

## 重点审查区深度验证

### 1. 统一可关闭 AsyncIterator 外观

**设计状态**：`HostSessionEventIterator` Protocol 作为 `AsyncIterator[HostSessionEvent]` 的可关闭子协议，显式提供幂等 `aclose()`；Host Protocol、public implementation、`dayu.host.api` / package exports 复用同一类型。

**代码证据**：当前 `_ClosableHostSessionEventIterator`（`open_host.py:1194-1283`）已实现正确的 lifecycle（lazy init generator、幂等 close、`finally` subscription.close()）。`__anext__` 的任何异常路径都调用 `aclose()`。

**审查结论**：设计正确提升现有私有实现到 public contract。**无 gap。**

### 2. 慢 UI/Service 不能反压 Agent/Engine

**设计状态**：EngineEvent ingest → non-blocking handoff → publisher → non-blocking offer to each subscription → `put_nowait`。同一 event loop 上的阻塞 callback 不在物理隔离承诺内。

**代码证据**：当前 `transient_delta.py:321-336` 已使用 `put_nowait`，overflow 时标记 `_overflowed` 并 detach。Ingest 不 await consumer。

**审查结论**：no-backpressure contract 已在当前代码中成立，设计保持不变并显式声明边界。**无 gap。**

### 3. 每订阅唯一 Host mailbox、Service 无 event-copy relay

**设计状态**：每 subscription 只有一个 transient mailbox + 唯一 in-flight。Service 删除 `_WatchAndWaitRuntime`、relay queue、drain task、`_WatcherQueueItem`、`_WatcherFailure` wrapper。sole consumer 直接迭代 `HostSessionEventIterator`。

**代码证据**：当前 Service 的 relay 结构（`entrypoint_runtime.py:500-511`、`1027-1032`、`1036-1054`）正是设计要删除的目标。

**审查结论**：删除 relay 后，Service 的 sole consumer 直接消费 Host iterator，消除了同一 subscription event 的双重缓冲和双重 capacity truth。**正确且必要。**

### 4. items/bytes/subscriptions 三维容量与精确 accounting

**设计状态**：
- `transient_mailbox_max_items`、`transient_mailbox_max_bytes`、`max_subscriptions_per_session` 三个 required 非 bool 正整数。
- canonical `delivery_size_bytes` helper 遍历 envelope + payload 的指定 string 字段，各 `len(value.encode("utf-8"))`。
- 每 event 构造一次 `(event, delivery_size_bytes)`，fanout 时复用。
- 固定 overflow primary order：单 event oversized → item count → cumulative bytes。
- mailbox + in-flight 共用一个 retained budget；单项 pop 只做 transfer 不扣减；yield 恢复或 cleanup 时按 entry size 扣减。

**审查结论**：byte accounting 覆盖了所有可变长度 string 字段（runtime_id, session_id, run_id, attempt_id, execution_id, dedupe_key, iteration_id, text_delta, 可选 tool_call_id, name_delta, arguments_delta），不重复计算，不遗漏主要内存消耗源。整数/datetime/enum/Python 对象头不计入是合理的工程简化（这些字段有固定上界或由 `max_items` 约束）。**设计自洽。**

### 5. terminal transaction-local exact sequence、TerminalPostCommitNotice/Port

**设计状态**：
- `TerminalPostCommitNotice(session_id, terminal_event_sequence, wake_queue_promotion)` 三精确字段。
- `TerminalPostCommitPort.notify_terminal_post_commit(notice) -> None`。
- 所有 terminal producer 的 transaction result 携带同 transaction exact sequence。
- 单一 coordinator 按 watermark advance → level-trigger wake → optional deduped promotion 顺序执行。
- `wake_queue_promotion=true` 仅表示本次 transaction 新释放 active slot 且需 queue reconciliation。

**代码证据**：当前全部 producer（engine_ingest、admission、waiting、dispatch、recovery）均只用 `session_id` 调 `wake_queue_promotion`。`waiting.py:684` 和 `waiting.py:2533` 证明 `terminal_event_sequence` 在 transaction 内可访问。`admission.py:783` 的 `CancelRunResult.released_active_slot` 证明 flag 的 transaction-local owner 已存在。

**审查结论**：
- `terminal_event_sequence` 在所有 producer 的 transaction result 中可访问 → 无需 latest-row readback。
- `wake_queue_promotion` flag 可从 `released_active_slot` 或等价 transaction-local 状态派生 → 无需 commit 后重猜。
- 单一 port + coordinator 消除了当前 5 条独立 bypass 路径。
- **设计正确关闭了 producer 闭环。**

### 6. 全部当前 terminal producer 闭集

**设计状态**：5 个 owner（admission、waiting/command、Engine ingest、dispatch、startup recovery）的完整 producer 清单（closure-rereview-fix §Exhaustive current producer manifest 表）。

**代码验证**：
- `admission.py`：queued/pre-dispatch/WAITING/RECOVERING cancel、terminal ack、session cancel、closeout_attempt_terminal — **全部命中**。
- `waiting.py`：failed/lost/expiry + same-scope replay — **全部命中**。`queue_promotion_session_id` 当前承担了不应承担的 terminal 语义。
- `engine_ingest.py`：Engine succeeded/failed/cancelled、worker lost、lifecycle terminal、duplicate — **全部命中**。
- `dispatch.py`：active-cancel watchdog、attempt-free pre-start failure、worker startup terminal — **全部命中**。`closed_session_ids` batch 当前丢失 exact sequence。
- `recovery.py`：recovering limit lost、unrecoverable orphan/cancelling lost — **全部命中**。terminal 与 ordinary promotion 当前混合。

**审查结论**：闭集穷举准确，无遗漏。

### 7. 乱序/duplicate/optional promotion、A terminal→B delta fence

**设计状态**：
- 同 sequence duplicate 幂等（不重复推进 watermark，不重复 enqueue true promotion）。
- false 不推进 promotion scalar → 先 false、后同 sequence true 可补发。
- 较新 false 不吞较旧未处理 true。
- batch 同 Session 多个 sequence 不丢失。
- A terminal yield 后 merge 停在悬停点，B event 留 Host counted mailbox，Service 不预读/不缓存。
- 只有 Service ack/clear/rebind 后的下一次 `anext()` 才交付 B。

**审查结论**：duplicate/false/true/batch 四种情况的语义完整且自洽。A→B fence 通过 `run_id` prefix delivery + O(1) current-terminal fence 实现，优于当前 `_terminal_run_ids: set[str]` 的无界增长。

### 8. exact-five Service disposition/cleanup

**设计状态**：`ServiceObservationResult` 恰好五个 members：`TARGET_TERMINAL`、`DELIVERY_INTERRUPTED`、`ITERATOR_ENDED`、`CALLBACK_FAILED`、`ITERATOR_FAILED`。每 member 唯一 caller disposition。slot first-commit 仲裁、stop/cancellation 先占、late commit 无效。

**审查结论**：五个 members 覆盖了 delivery 的所有终态路径。当前代码的 task exception/queue item/drain task 混合导致 outcome 不唯一，设计用 closed union + first-commit 仲裁解决了该问题。

### 9. 实施文件、静态 callgraph 与集成测试

**设计状态**：Future WU scope 覆盖 15 个文件/文件组 + 对应 owner/integration/static tests。

**审查结论**：文件清单覆盖了 public contract（api.py、__init__.py）、config assembly（config_loader.py、host_runtime.json、host_assembly.py）、delivery core（terminal_post_commit.py、transient_delta.py、open_host.py）、全部 5 个 producer owner（admission、waiting、engine_ingest、dispatch、recovery）+ command.py + durable/run_transition.py、Service（entrypoint_runtime.py）、CLI adapters、旧术语删除、README。**无遗漏。**

静态 callgraph acceptance（AST qualified callsite 集合 vs manifest exact 相等 + ordinary promotion allowlist）与三组 non-Engine barriers（pre-dispatch cancel A + queued B、wait failed A + queued B、wait expiry A + queued B）共同构成三层证明。**可裁决。**

### 10. 过度设计、错误耦合或更简单且同样正确的方案

已在 Optimal-Solution Review 和 Overengineering Review 中逐项验证。**不存在更简单且同样正确的方案。**

## Material Findings

**0 material findings。**

经过对设计的全面 adversarial review——包括 architecture boundary、best-practice、optimal-solution、overengineering、overcoupling 五个 lens 的独立验证，以及对用户指定的十个重点审查区的逐项代码/设计对照——未发现会导致 incorrect design 或 implementation 不可裁决的 material finding。

## Implementation WU Acceptance / Implementation Considerations

以下事项不构成 design material finding，不阻塞设计 closure。它们已冻结为同一 implementation WU
的 acceptance criteria / implementation considerations，不下沉为 residual risk 或独立跟踪项。

**Design residual = 0。未归属 residual = 0。**

### Capacity measurement（同 WU acceptance）

| # | 事项 | WU acceptance |
|---|---|---|
| C1 | packaged `transient_mailbox_max_items` / `transient_mailbox_max_bytes` / `max_subscriptions_per_session` 数值 | implementation WU 基于 workload、consumer latency SLO、peak delta rate、watcher count、memory budget 测量并给出证据后写入 packaged 默认值。字段、算法、typed error 与 release contract 均已冻结。 |
| C2 | logical UTF-8 byte budget 到 Python resident heap 的 safety margin | implementation WU 测量并写入配置注释或设计补充说明。 |
| C3 | 低基数 production metrics 字段与采样方式 | implementation WU 至少区分 item/byte overflow、buffer high-watermark 与 detach，不含 payload 正文或高基数 identity。 |

### Implementation considerations（同 WU acceptance）

| # | 事项 | WU acceptance |
|---|---|---|
| I1 | AST manifest 测试脆弱性 | `test_terminal_post_commit.py` 的 AST-based callsite 验证 fail-closed：新增、删除或改名 callsite 必须显式更新 manifest。运行时 fake port tests 与 integration barriers 提供第二、第三层保护。 |
| I2 | 单事件 oversized | 单个 `HostTransientDelta` 超过 `transient_mailbox_max_bytes` 时 overflow，不得截断。implementation 必须产生 typed `PAYLOAD_BYTES` oversized error（不归因于 mailbox 满），tests 必须分别覆盖 oversized 与 cumulative-full。 |
| I3 | Python 对象头开销 | `delivery_size_bytes` 不计 Python 对象头——`max_items` 维度提供粗粒度约束。implementation 不得声称精确 Python heap measurement，docstring 必须写明该边界。 |
| I4 | Service/UI callback 不得阻塞 owner loop | no-backpressure 承诺不覆盖同一 event loop 上的阻塞 callback。implementation 必须在 Service/UI adapter 侧确保 activity/thinking callback 快速同步、非阻塞返回；慢 I/O/CPU/renderer 适配必须显式解耦（如通过独立 task/thread 消费并做 display-side 缓冲），不得依赖 Host mailbox 吸收 callback 延迟。此项是 WU acceptance，不是留给未来的 open risk。 |

## 与既有 Finding Closure 的一致性检查

| Finding | 状态 | 本次验证 |
|---|---|---|
| `CODEX-CLOSURE-REREVIEW-F01`（terminal producer 闭环缺口） | 已修复 | TerminalPostCommitNotice/Port、全 producer manifest、实施授权、静态 call graph、三组 non-Engine barrier 均已冻结。设计自洽。 |
| `CODEX-FINAL-REREVIEW-F02`（exact-five disposition、cleanup precedence） | 保持关闭 | 未修改，未弱化。 |
| `CODEX-REREVIEW-F02`（single mailbox + 唯一 in-flight + 无 Service relay） | 保持关闭 | 未修改，未弱化。 |
| `CODEX-REREVIEW-F03`（per-Session admission、先 reserve 后 allocation、全 release contract） | 保持关闭 | 未修改，未弱化。 |
| `CODEX-REREVIEW-F04`（payload bytes → item count → cumulative bytes primary order + 四组 fixtures） | 保持关闭 | 未修改，未弱化。 |

## 最终结论

### PASS

设计是当前约束下的最佳方案。它从第一性原理出发，正确识别并关闭了双重 buffer、无 byte accounting、无 admission control、terminal producer bypass、A→B merge race、unbounded terminal fence、Service closable Protocol 重复等七个根因问题。

- **Material findings**：0
- **Design residual**：0
- **未归属 residual**：0
- **Implementation WU acceptance / considerations**：7 项（3 capacity measurement + 4 implementation considerations，均已冻结为同 WU acceptance，不下沉为 residual）
- **设计是否可交付 implementation agent**：是。public contract、ownership、state machine、error semantics、ordering guarantees、test matrix 均已冻结，不留 implementation agent 自由裁决的架构或 public contract 参数。
