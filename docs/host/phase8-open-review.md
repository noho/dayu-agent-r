# Host P8 开放式架构复审：Attempt Lease / Recovery / 多进程并发基础

## 复审范围与方法

本次复审是独立的第一性原理架构审查，不从属于 P8 plan review（已通过）或 plan re-review（已通过）。复审目标不是检查 plan 是否 handoff-ready，而是从架构层面回答：**P8 是否是正确方向、是否过度设计、是否有更优替代方案、是否存在被忽略的风险**。

复审读取了以下材料：

- `docs/host/phase8-plan.md`（最终 handoff plan）
- `docs/host/phase8-plan-review.md`（原始 review：不通过，6 findings）
- `docs/host/phase8-plan-rereview.md`（复审：通过）
- `docs/host/design.md`（Host 架构设计真源）
- `docs/host/migration-plan.md`（总控计划，P0-P16）
- `docs/engine/design.md`（Engine 架构边界）
- `docs/host/phase6-plan.md`、`docs/host/phase7-plan.md`（前序 phase plan）
- `docs/host/phase6-concurrency-review.md`、`docs/host/phase6-architecture-review.md`
- `docs/host/phase7-architecture-review.md`
- `docs/host/phase6-fix-rereview.md`、`docs/host/phase7-fix-rereview.md`
- 当前代码关键路径（`_run_harness.py`、`_durable_event_store.py`、`_run_state_store.py`、`_tool_runtime.py`、`_event_observer.py`）

复审不写生产代码，不替代 Gateflow 的 plan review / fix / re-review 循环。

## 总体结论：P8 方向正确，非过度设计，plan 已达到可实施标准

P8 不是过度设计。Attempt lease / fencing / recovery 是"多进程并发 Full-Governance Multi-Turn"的**必要基础**，不是可选的锦上添花。以下逐一论证。

---

## 问题一：P8 是否真的是实现"多进程并发 Full-Governance Multi-Turn"的必要下一步？

### 结论：是。P8 是 P6-P7 与 P9+ 之间不可跳过的一环。

### 论证

**P6 建立了 durable facts 层，但没有建立 owner 真源。** P6 的 `host_attempts` 表有 `attempt_id`、`run_id`、`attempt_index`、`state`、`terminal_event_position`，但没有 owner token、lease expiry、fencing generation。`AttemptStateStore.update_state` 只按 `attempt_id` 更新状态，不做 compare-and-set。这意味着：

- 多个进程可以同时将同一个 attempt 从 `RUNNING` 更新为 `SUCCEEDED`，各自写入不同的 terminal 结果。
- 一个进程崩溃后，另一个进程无法安全判断旧 attempt 是否仍在执行、是否可以恢复。
- 旧进程的迟到写入（包括 Engine events、context compact facts、ToolRuntime facts）无法被拒绝。

**P6 自身承认这些缺口。** `_run_state_store.py` 的模块 docstring 明确写："P6 不实现 admission、owner lease、fencing、orphan recovery"。`docs/host/migration-plan.md` §4.2 把"真实多进程 stress、owner lease / fencing / orphan attempt recovery、attempt `terminal_event_position` 写入"三项标为 `deferred-with-owner: P8`。

**P7 建立了 tool trace projection，但暴露了 fencing 漏洞。** `_tool_runtime.py` 中多个路径（`_append_tool_result_truncated`、`_append_cursor_issued`、`_append_fetch_requested` 等）直接调用 `event_store.append(...)` 写入 Host-owned canonical facts。当前 `ToolExecutionContext` 不携带 attempt owner context，这意味着旧 owner 进程在 lease 过期后仍可以写 `TOOL_RESULT_TRUNCATED`、`TOOL_CURSOR_ISSUED`、`TOOL_FETCH_MORE_*` 等事实，污染 EventLog 和后续 tool trace / memory projection。

**P9（Session / Run Lifecycle Governance）依赖 P8 的 owner 真源。** `docs/host/design.md` §6.3 要求同 Session active Run 仲裁依赖数据库唯一约束或 compare-and-set；§7.1 Run 状态机包含 `RECOVERING` 和 `LOST`，这些状态的语义建立在 attempt ownership 之上。P9 可以做 `client_request_id` 幂等和 active Run admission（用 UNIQUE 约束 + 行锁），但 attempt 执行权、恢复权、迟到写入拒绝和 orphan 收口必须先在 P8 固定。如果跳过 P8 直接做 P9，要么 P9 需要内嵌一个不完整的 lease 机制，要么留下跨进程 attempt 写入冲突的漏洞。

**P8 是 P6→P7→P8→P9 依赖链的必要环节。** 这个依赖链不是人为制造的，而是从"单进程 durable facts"到"多进程并发 governance"的自然演进：

```text
P6: durable facts + projection checkpoint（单进程安全，多进程存储层安全）
P7: tool trace as observer（依赖 P6 facts，暴露 ToolRuntime fencing 漏洞）
P8: attempt ownership + fencing + recovery（补齐多进程执行权真源）
P9: Session/Run lifecycle + public interface（依赖 P8 owner 真源）
```

### 风险

唯一的替代路径是在 P9 中内嵌一个简化的 lease 机制，但这会导致 P9 的实施范围膨胀，且 lease 机制未经独立验证就与 lifecycle admission 耦合，增加 review 复杂度和 bug 密度。P8 作为独立 phase 是更安全的拆分。

---

## 问题二：attempt lease / fencing / recovery 是否解决了真实 root cause，还是过度设计？

### 结论：解决了真实 root cause，非过度设计。方案的精简程度恰当。

### 论证

**Root cause 1：多进程下缺乏执行权真源。** 当前 `host_attempts` 的 `state` 字段是唯一协调点，但 `update_state(attempt_id, new_state)` 没有 compare-and-set 条件。两个进程可以同时将同一个 attempt 从 `RUNNING` 改为 `SUCCEEDED`，各自写入不同的 terminal 结果，且两个写入都会成功（SQLite 不会拒绝第二个 UPDATE，只是覆盖）。这不是理论风险——只要有两个进程同时恢复或同时尝试终结同一个 attempt，就会发生。

P8 的修复是 CAS-based owner token + lease generation：acquire 用 `INSERT` + `UNIQUE(run_id, attempt_index)` 冲突检测；renew 用 `UPDATE ... WHERE state='running' AND owner_token_hash=? AND lease_generation=? AND lease_expires_at > now`；terminal close 同事务内 verify owner + append event + update attempt。这直接解决了"谁有权写"的真源问题。

**Root cause 2：旧 owner 迟到写入污染事实层。** 进程崩溃后，旧进程可能仍在执行工具或 stream engine events。当前没有任何机制阻止旧进程的 `event_store.append(...)` 写入。这些迟到写入会：
- 在 terminal 后追加新 EventLog 事件（P6 terminal guard 只拦截同一 run 的 terminal 后 append，不拦截不同 attempt 的写入）
- 污染 tool trace（旧 owner 的工具事实会被 observer 投影）
- 污染 memory projection（旧 owner 的 context facts 会进入下一轮 memory）

P8 的修复是 AttemptScopedRunEventAppender：每次 append 在同一事务内先 `verify_owner`，再 `append_with_position_in_transaction`。旧 owner 的迟到写入返回 typed `AttemptFencingError`，不写 diagnostic RunEvent（避免用 stale owner 污染 canonical facts）。

**Root cause 3：orphan attempt 无人收口。** 进程崩溃后，`host_attempts` 中 `state='running'` 的 attempt 永久停留在该状态。没有机制检测、标记或恢复这些 orphan。这会导致：
- 后续进程无法安全判断是否可以恢复
- Run 永远无法进入 terminal
- EventLog 中留下"有 attempt 无 terminal"的审计缺口

P8 的修复是 `recover_stale_attempts()`：扫描 `state IN ('running', 'created') AND lease_expires_at <= now`，CAS 标记旧 attempt 为 `RECOVERING`/`STALE`/`LOST`，创建新 recovery attempt 并记录 `recovered_from_attempt_id`。

### 为什么不是过度设计

**方案选择克制。** P8 做了以下明确的减法：

1. **不新增 `host_attempt_leases` 独立表。** 所有 lease 字段直接在 `host_attempts` 上扩展。这避免了 join 查询、双表 CAS 和外键复杂性。plan review F2 原要求选择单表/双表，最终固定为单表方案。
2. **不实现 observer claim / lease。** observer 的跨进程 ownership 明确后移到 #28 或 P15。P8 只升级 observer 调用协议为 async，不改 projection checkpoint schema，不加后台 observer worker。
3. **不把 fenced late write 写成 diagnostic RunEvent。** 拒绝 stale owner 写入时只返回 typed error + masked 日志，不创建 EventLog 事件。这是正确的——stale owner 不应有权限写 canonical facts。
4. **recovery 不推进 projection checkpoint。** recovery 只处理 attempt 状态机，不调用 `startup_reconcile()`，不写 EventLog diagnostic RunEvent。新的 recovery attempt 后续产生的 canonical facts 自带新的审计边界。
5. **不做完整 remote / outbox / wait / suspend。** P8 严格限定在 attempt ownership 范围内。

**复杂度与问题规模匹配。** 多进程并发 + crash recovery 是分布式系统的基础问题。P8 的方案（owner token + lease + CAS + recovery scan）是解决这个问题的**最小可行方案**。更简单的方案（如进程内锁、文件锁、单 writer 假设）都无法满足跨进程一致性和 crash recovery 需求。

### 潜在过度设计风险点

有一个值得关注的信号：`AttemptState` 从 P6 的 6 个值扩展到 P8 的 9 个值（新增 `STALE`、`RECOVERING`、`LOST`）。这三个新状态服务于 recovery 路径的不同诊断精度。如果实际生产中 `STALE`（只标记不恢复）和 `LOST`（无法恢复）的使用频率极低，那么 `RECOVERING` 一个状态可能就够用。但考虑到：

- `STALE` 服务于显式诊断 API，用于 smoke/运维收口测试
- `LOST` 服务于无法安全恢复的边界情况（如 run 已 terminal 但 attempt 仍 running）
- `RECOVERING` 是默认主路径

这三个状态的区分是合理的，不算过度设计。建议在 P8 实施后观察实际使用比例，如果某个状态从未触发，可在 P15 hardening 时考虑合并。

---

## 问题三："不 takeover 同一 attempt、创建 new recovery attempt"是否合理？有没有更简单更稳的替代方案？

### 结论：不 takeover 的策略是正确的。替代方案（takeover 同一 attempt）在审计和数据完整性上有根本性缺陷。

### 论证

**Takeover 同一 attempt 的问题：**

1. **审计边界混乱。** 如果新进程接管同一个 `attempt_id`，那么 `host_attempts` 中一条记录会被两个不同的 owner 写入。`attempt_index` 不变，`lease_generation` 需要从 N 递增到 N+1。在 EventLog 中，同一个 `attempt_id` 下会有两个不同 owner 产生的事件。这让审计追踪（"这个 attempt 到底发生了什么"）变得困难——是旧 owner 写的还是新 owner 写的？

2. **ToolRuntime cursor/scope_token 安全问题。** 旧 attempt 的工具执行可能产生了 cursor 和 scope_token。如果 takeover 同一 attempt，新 owner 是否能使用这些 cursor？如果不能（因为旧 owner 的 scope 已失效），tool trace 中会出现"有 cursor issued 但无法 fetch_more"的断裂；如果能（复用 scope），则存在安全风险——旧 owner 的 scope 被新 owner 继承。

3. **EventLog 事件归属模糊。** P6 的 EventLog 事件携带 `attempt_id`。如果新旧 owner 共享同一 `attempt_id`，则无法通过 `attempt_id` 区分事件的归属。`recovered_from_attempt_id` 字段的价值在于：EventLog 中 `attempt_id=A` 的事件明确归旧 owner，`attempt_id=B` 的事件明确归新 owner，而 B 通过 `recovered_from_attempt_id=A` 指向 A，形成清晰的恢复链。

4. **CAS 竞争窗口更大。** Takeover 同一 attempt 需要 CAS 更新 `owner_token_hash`、`lease_generation`、`lease_expires_at`，同时保持 `attempt_id` 不变。如果旧 owner 在 CAS 之后、新 owner 读取之前又写入了事件，这些事件会混入新 owner 的审计边界。创建新 attempt 则从根本上消除了这个窗口——旧 attempt 被标记为 `RECOVERING` 后不再接受任何写入，新 attempt 有全新的 `attempt_id`。

**"不 takeover + 新 attempt"的优势：**

1. **审计清晰。** `host_attempts` 中每条记录只属于一个 owner。EventLog 中 `attempt_id` 与 owner 一一对应。审计链通过 `recovered_from_attempt_id` 连接。
2. **旧 attempt 不可变。** 一旦标记为 `RECOVERING`/`STALE`/`LOST`，旧 attempt 不再接受任何写入。即使旧 owner 进程仍然存活并尝试写入，fencing 会拒绝。
3. **新 attempt 全新起点。** 新 `attempt_index`、新 `attempt_id`、新 `lease_generation=1`，语义干净，不继承旧 owner 的任何状态。
4. **与 P11 replay 语义一致。** P11 的 validation replay 也是创建新的 internal attempt，不复用旧 Agent/Runner。P8 的 recovery 与新 attempt 策略与之一致，形成统一的 attempt 生命周期模式。

**更简单的替代方案评估：**

| 方案 | 复杂度 | 审计清晰度 | 数据完整性 | 可行性 |
| --- | --- | --- | --- | --- |
| 单进程假设（不允许并发） | 最低 | N/A | N/A | 不可行：P9+ 要求多进程 |
| 文件锁（flock） | 低 | 无审计 | 弱（进程崩溃后锁释放但状态不一致） | 不可行：不跨平台、不可靠 |
| 内存锁 + 主从 | 中 | 弱 | 弱（主进程崩溃后无从恢复） | 不可行：增加运维复杂度 |
| takeover 同一 attempt | 中 | 差（事件归属模糊） | 中（有 CAS 竞争窗口） | 可行但不推荐 |
| **不 takeover + 新 attempt（P8 方案）** | **中** | **好** | **好** | **可行且推荐** |
| 完整 Raft/Paxos | 极高 | 好 | 极好 | 过度设计 |

**唯一值得考虑的简化：** 是否可以在 P8 首版只支持 `RECOVERING` 而不支持 `STALE` 和 `LOST`？当前 plan 已明确 `STALE` 是显式诊断 API（smoke/运维测试用），`LOST` 是 run 已 terminal 时的诊断终态。这两个状态的服务场景明确，不增加核心 CAS 逻辑的复杂度（只是 `mark_stale_or_lost` 的参数变体）。保留它们不构成过度设计。

---

## 问题四：async ObserverSink 放在 P8 是否合适？是否应该更早、更晚，或完全不需要？

### 结论：放在 P8 是合理的时机选择。更早会扩大 P6/P7 范围，更晚会增加 P8 自身测试负担和后续迁移成本。

### 论证

**为什么需要 async ObserverSink：**

1. **消除技术债。** P6 的 `MemoryProjectionObserver` 通过 `_run_async` 桥接 async `ConversationMemoryStore`。这个桥接创建 thread + event loop，是明确的技术债。P6 fix-rereview 已将其标记为 `deferred-with-owner: P8/#28/P15`。

2. **P7 tool trace observer 包含文件 IO。** JSONL 写入（`flush + fsync`、`tmp + os.replace`）发生在 observer 的 `process()` 中。同步协议下，这些 IO 操作阻塞 `ProjectionCoordinator.drain()`。升级为 async 后，observer 可以在同一 storage transaction 内执行 IO，不阻塞其他 observer 的 drain。

3. **P8 要做多进程 observer drain 验证。** P8-S7 的 deterministic multiprocessing 测试需要验证 observer drain 在跨进程场景下的正确性。如果 observer 协议在 P8 后还要再改一次（从 sync 到 async），所有 P8 的多进程 observer drain 测试都需要重写，增加不必要的返工。

**为什么不是更早（P6/P7）：**

P6 的目标是"最小 durable EventLog + ProjectionCoordinator"。同步 observer 协议让 P6 的 diff 边界小，focus 在 storage 层的并发安全上。P7 的目标是"tool trace projection"，focus 在 trace schema 和 observer 实现上。在这两个 phase 中引入 async 协议迁移会扩大 scope，增加 review 复杂度。

P6 fix-rereview 的判断是准确的：P6 保留同步协议是合理的 scope 控制，async 升级放在 P8 是因为 P8 需要做多进程 observer drain 验证，此时统一协议可以避免后续重复迁移。

**为什么不是更晚（P15）：**

如果推到 P15（Governance Hardening），P8、P9、P10、P11、P12、P13、P14 的所有 observer 测试都要基于同步协议编写。等到 P15 再迁移，需要批量修改 7 个 phase 积累的 observer 实现和测试，迁移成本和风险都更高。

**async 协议与 observer claim/lease 的分离是正确的。** 这里有一个关键的架构判断：async 调用协议（`async def process`）和跨进程 ownership（observer claim/lease）是两个独立问题。前者解决"observer 如何被调用"，后者解决"谁有权调用 observer"。P8 升级前者但不实现后者，这个边界清晰且安全——`ProjectionCoordinator` 仍是进程内单 owner（通过 `_drain_lock` 保护），只是 `await observer.process()` 不再阻塞 event loop。后台 observer worker / observer claim 的复杂性留给 #28 或 P15。

**风险：** async observer 在同一 storage transaction 内 `await observer.process(...)` 意味着 observer 的 IO 时间会计入 transaction 持有时间。对于 JSONL tool trace（文件 IO），这不是问题（SQLite 事务不涉及 JSONL 文件）。对于 memory projection（写入 SQLite），同一事务内 await 可能导致事务持有时间变长。但当前所有 observer 写入都在同一 SQLite 数据库内，且 P6 已经通过 WAL + `BEGIN IMMEDIATE` 保证了并发安全。这个取舍是合理的——如果后续发现 transaction 持有时间是瓶颈，可以通过 buffered drain 或后台 worker 解决（由 P15 承接），不需要在 P8 过度优化。

---

## 问题五：multiprocessing 平台封装边界是否正确？是否会把测试 helper 误演化成 Host 生产能力？

### 结论：边界设计正确，误演化风险可控，但需要在 code review 时设硬 gate。

### 论证

**当前边界设计：**

- `tests/host/_multiprocess_platform.py`（或同等私有测试 helper）：封装 start method、join timeout、进程终止、文件 SQLite path、跨进程结果收集。
- 测试主体（`test_phase8_multiprocess_stress.py`）不得散落 `multiprocessing.set_start_method`、裸 `join(timeout)` 或重复进程清理逻辑。
- 该封装"先定位为测试 / smoke helper，不提升为 Host 生产 launcher"（phase8-plan.md §5, §13）。
- `dayu/runtime/**` 明确不应修改，"除非未来另行评估层中立运行时能力"（phase8-plan-rereview.md 用户决策核验）。

**这个边界为什么正确：**

1. **测试 helper 和生产 process launcher 是两种不同的东西。** 测试 helper 需要：确定性（deterministic spawn）、短超时、清晰的 exitcode 断言、临时路径管理。生产 process launcher 需要：资源限制（CPU/memory cgroup）、健康检查、优雅关闭、日志收集、监控集成。把测试 helper 提升为生产 launcher 会引入大量未经验证的生产假设。

2. **P8 的真实多进程需求在测试层，不在生产层。** P8 不实现 RemoteProxy（P13）、不做完整 Host bootstrap（P9）、不做生产 process 管理。P8 的多进程验证目标是证明"attempt lease/fencing/recovery 在真实多进程下正确"，而不是"Host 可以生产级管理子进程"。

3. **`dayu.runtime` 的隔离是必要的。** `dayu.runtime` 是层中立运行时基础设施，不得承载 Host 业务语义。P8 的 multiprocessing helper 包含 attempt lease 测试逻辑、SQLite path 管理、跨进程 result 收集——这些都有 Host 语义，不应进入 `dayu.runtime`。

**误演化风险与防控：**

风险场景：实施 Agent 在 P8-S7 中，为了"方便"，将 `_multiprocess_platform.py` 中的 `start_process` / `join_with_timeout` / `collect_results` 等 helper 写成通用 process manager，然后在 P8-S8 smoke 中直接使用。后续 P9/P13 实施时，Agent 可能复用这些 helper 作为生产 process launcher 的基础。

防控措施（plan 已包含，但值得在 code review 时强化）：

1. **文件命名和路径约束。** `tests/host/_multiprocess_platform.py` 的下划线前缀和 `tests/` 路径明确表明它是测试私有模块。不应被 `dayu/host/` 或 `dayu/runtime/` 导入。
2. **code review gate。** P8 的架构边界 code review（phase8-plan.md §18）已要求审查"`dayu.runtime` 是否未承载 Host 业务语义"。建议增加一条："`tests/host/_multiprocess_platform.py` 是否被 `dayu/` 下的任何模块导入；如果是，判定不通过"。
3. **smoke 复用路径明确。** `utils/smoke_host_p8_attempt_lease.py` 可以导入 `tests/host/_multiprocess_platform.py`（smoke 是验证工具，不是生产代码），但必须通过 `if TYPE_CHECKING` 或显式 `sys.path` 管理，不能把测试 helper 变成生产依赖。

**建议：** 在 P8 完成后、P9 开始前，做一次专项检查：`grep -r "_multiprocess_platform" dayu/` 必须返回空。如果返回非空，说明测试 helper 已经泄漏到生产代码。

---

## 问题六：P8 plan 是否有遗漏、错误归属、过早承诺或后续 phase 风险？

### F1 [Medium] observer 协议升级后，ProjectionCoordinator 的事务持有时间模型未量化

**证据：**

- phase8-plan.md §11 要求 `ProjectionCoordinator._run_once_locked` 在同一个 `HostStorage.transaction()` 内 `await observer.process(tx=tx, batch=envelopes)`，然后推进 checkpoint。
- 当前 P6 实现中，`_run_once_locked` 的事务持有时间 = SQLite read（fetch events）+ observer process（memory store write + timeline write + audit write + tool trace JSONL write）+ checkpoint update。
- 升级为 async 后，observer process 内部可以 `await`（例如 memory store 的 async write），但仍在同一 SQLite 事务内。

**影响：** 如果 observer 内部有慢 IO（例如 tool trace JSONL 写入大文件），事务持有时间会变长。SQLite WAL 模式下，写事务不阻塞读，但长事务会阻止 WAL checkpoint 和后续写事务的开始。在极端情况下（tool trace JSONL 写入慢盘），terminal drain 可能被拉长。

**这不是 P8 的阻断性问题**——P7 已经有这个 trade-off（同步 observer 同样持有事务），async 升级不改变事务持有时间的量级。但这是一个需要在 P15 hardening 时定量评估的风险：如果 terminal drain 的 P99 延迟超过 lease TTL（30s），renew 可能失败。

**建议：** 在 phase8-plan.md §20（风险）中补充此条。不要求在 P8 解决，但应记录为 P15 的评估项。

### F2 [Medium] `terminal_event_position` 对 `STALE`/`RECOVERING`/`LOST` 的可空语义需要明确与 `RunResult` 的关系

**证据：**

- phase8-plan.md §6.2 明确："`terminal_event_position` 对正常 terminal attempt 必须非空；`STALE` / `RECOVERING` / `LOST` 这类无 terminal RunEvent 的诊断终态可为空。"
- `docs/host/design.md` §7.1 的 `RunResult` 包含 `terminal_event_cursor: RunEventCursor`。
- P8 不负责 `RunResult` 的完整语义（属于 P6/P9），但 P8 的 recovery path 会创建新 attempt 并最终产生 terminal event。

**影响：** 如果旧 attempt 被标记为 `RECOVERING`（无 terminal event），新 recovery attempt 最终 `SUCCEEDED`（有 terminal event），那么 Run 的 `terminal_event_cursor` 应该指向新 attempt 的 terminal event。旧 attempt 的 `terminal_event_position` 为 NULL 是正确的，但需要确保 Run state 的 `terminal_event_position` 与最终成功的 attempt 一致。当前 plan 在 P8-S6 的完成信号中提到"projection checkpoint 不被 recovery scan 修改"，但没有明确 Run 级别的 terminal position 如何从新 attempt 继承。

**建议：** 这不是 P8 的遗漏（P8 只负责 attempt 级别），但应在 P8-S6 实施时确保 `AttemptSupervisor` 的 terminal close 会更新 `host_runs` 的 terminal 状态（这是 P6 已有的路径，P8 不应打破）。在 P8-S4（Terminal Append + Close 原子片）中应该验证：新 recovery attempt 的 terminal close 正确更新了 Run 的 terminal state。

### F3 [Low] `LocalRunHarness` 的进一步拆分在 P8 中只有方向性描述，缺乏具体拆分契约

**证据：**

- phase8-plan.md §5 架构边界图显示 `LocalRunHarness -> AttemptSupervisor`，原则第 4 条明确"`LocalRunHarness` 只能编排 attempt supervisor、event append 与 projection drain，不承载 lease SQL、recovery scan、token 校验或 fencing error 策略"。
- phase8-plan.md §20 承认"`LocalRunHarness` 仍偏大；P8 必须抽出 AttemptSupervisor，但完整 RunSupervisor 拆分留到 P9"。
- 当前 `_run_harness.py` 有 16 字段 / 43 方法（per P7 residual risk tracking）。

**影响：** P8 抽出的 `AttemptSupervisor` 承担了 lease lifecycle、fenced append、recovery scan 等核心职责，这会实质性削减 `LocalRunHarness` 的方法数和复杂度。但 plan 没有给出 P8 后 `LocalRunHarness` 的目标方法数或字段数上限。如果实施 Agent 在"薄委托"的理解上 drift，`LocalRunHarness` 可能仍然持有过多编排逻辑。

**建议：** 这不是 P8 plan 的阻断性遗漏（P9 会继续拆分），但 P8 的 code review 应该用具体指标检查：P8 后 `LocalRunHarness` 是否减少了方法数（至少不应增加）；新增的 lease/renew/fencing/recovery 逻辑是否全部在 `AttemptSupervisor` 或 `AttemptLeaseStore` 中，`_run_harness.py` 是否只新增了 `AttemptSupervisor` 的装配和调用委托。

### F4 [Low] P8 不写 fenced late write diagnostic RunEvent，但也没有定义 fenced write 的可观测性

**证据：**

- phase8-plan.md §1："P8 首版不把 fenced late write 写入 EventLog diagnostic RunEvent。非 owner / stale owner 不应污染 canonical facts；拒绝以 typed error / result 和安全日志表达。若后续需要 audit rejected write，另设治理 issue。"
- phase8-plan.md §7.2："fenced late write 不写 diagnostic RunEvent，只返回 typed refusal 并记录 masked 日志"。
- 当前没有定义一个结构化的 fenced write 日志格式或 metrics 接口。

**影响：** 生产环境中，如果出现频繁的 fenced write（表示有僵尸进程或时钟偏移问题），运维人员只能通过日志发现（日志可能被淹没或未采集）。没有 metrics 接口意味着无法设置告警。

**这不是 P8 的问题。** P8 的目标是建立 fencing 机制本身，不是建立完整的运维可观测性。fenced write 的可观测性（metrics、structured log、alerting）属于 P15 Governance Hardening。但建议在 P8 实施时至少使用结构化日志（`logging.getLogger(__name__).warning("attempt_fencing", extra={...})`），而不是裸 `print` 或纯文本日志，以便后续 P15 接入。

### F5 [Low] P8 计划中 `AttemptState` 从 P6 的 6 状态扩展到 9 状态，但 `RunState` 的对应迁移未在 P8 中处理

**证据：**

- phase8-plan.md §6.3 固定 `AttemptState` 为 9 状态。
- `docs/host/design.md` §7.1 `RunState` 包含 `RECOVERING` 和 `LOST`，但 §8.1 `AttemptState` 的设计中包含更多状态。
- P8 plan 中没有描述当 attempt 进入 `RECOVERING` 时，Run 状态如何对应变化。

**影响：** 如果 P8 的 recovery 创建了新 attempt 但 Run 状态没有更新为 `RECOVERING`，调用方通过 `get_run(run_id)` 会看到 Run 仍在 `RUNNING`，而实际上旧 attempt 已经不可执行、新 attempt 正在进行中。这会在 Run 级别产生状态不一致。

**为什么这不是 P8 的问题：** Run 状态机的 `RECOVERING` 和完整 lifecycle 属于 P9（Session / Run Lifecycle Governance）。P8 的 recovery scan 目前是显式 API（`recover_stale_attempts()`），不是自动 Host bootstrap。P8-S6 的完成信号中提到"recovering + new attempt、recovered_from_attempt_id"的测试通过，不要求自动化 Run 状态同步。

**但值得在 P8 实施时注意：** 当 P8-S6 的 `recover_stale_attempts()` 成功创建新 attempt 后，`host_runs` 的 state 应该保持与最高 attempt 状态一致。如果 P6 的 `_run_state_store.py` 没有在 attempt state 变更时自动同步 Run state，P8-S6 需要在事务内显式更新。建议在 P8-S6 测试中增加一个断言：recovery 后 `host_runs.state` 的语义正确（至少不应停留在旧状态）。

### F6 [Low] P8 的 TTL（30s）和 renew interval（10s）是合理默认值，但可能不适用于未来的长工具调用

**证据：**

- phase8-plan.md §6.1：`ATTEMPT_LEASE_TTL_SECONDS = 30`，`ATTEMPT_LEASE_RENEW_INTERVAL_SECONDS = 10`。
- 当前工具调用（包括 `fetch_more` 链）在同一 attempt 内执行。如果一个工具调用耗时超过 TTL（例如等待外部审批），renew loop 仍在运行（每 10s renew 一次），所以 TTL 不是工具调用的硬超时。
- 但如果 renew 连续失败（例如 SQLite 暂时不可用），30s 后 lease 过期，attempt 被 fencing。

**影响：** 30s TTL / 10s renew 意味着 SQLite 至少有 2 次 renew 机会（10s 和 20s 各一次），第三次 renew 失败（30s）时 lease 过期。对于正常运行的 SQLite WAL，这个窗口足够宽。如果 SQLite 持续不可用超过 30s，系统本身已经处于降级状态，让 attempt 进入 fencing 是合理的。

**这不是过度设计或设计缺陷。** 常量是集中命名的、可通过 fake clock 注入测试的，默认值合理。后续如果需要调整（例如工具调用可能持续几分钟），只需修改常量值，不需要改架构。

---

## 架构正确性确认：为什么 P8 方案不是过度设计

### P8 解决的是分布式系统的基础问题

多进程并发 + crash recovery 是分布式系统领域经过数十年研究的基础问题。P8 的方案（owner token、lease、CAS、recovery scan）是该领域经过验证的最小可行方案：

1. **Owner token + lease** 是 leader election 的最简形式。P8 不需要 Raft/Paxos，因为 attempt ownership 的竞争范围限定在单个 attempt 内，使用 SQLite CAS 即可。
2. **Fencing** 是解决"旧 leader 仍在写入"的标准方案。P8 的 fencing 通过 CAS verify + generation 实现，与 etcd 的 lease + revision、Google Chubby 的 sequencer 机制原理相同。
3. **不 takeover + 新 attempt** 是 event sourcing 中的标准实践。旧 stream 关闭，新 stream 创建，通过 `recovered_from_attempt_id` 连接。这使得审计日志不可变且可追溯。

### P8 的精简体现在多个"不做"上

- 不做 observer claim/lease（#28/P15）
- 不做 fenced write diagnostic EventLog event（不污染 canonical facts）
- 不做多进程 observer worker
- 不做 `host_attempt_leases` 独立表（单表方案）
- 不做 takeover 同一 attempt（避免审计混乱）
- 不做完整 Run state 同步（留给 P9）
- 不做生产 process launcher（测试 helper 限定在 tests/）
- 不做慢盘/Docker stress 为默认 pytest（issue #38）

### P8 与后续 phase 的依赖关系正确

```text
P6: durable facts ──┐
                     ├──> P7: tool trace ──> P8: attempt ownership ──> P9: lifecycle
P1-P5: smoke baseline ──────────────────────────────────────────────────────────> P16: full smoke
```

P8 不阻塞 P6/P7 的独立演进，也不被 P9 的 Session/Run lifecycle 阻塞（P9 需要 P8，反之不然）。这个依赖顺序是正确的。

---

## 总结

| 问题 | 结论 |
| --- | --- |
| P8 是否是必要下一步 | **是。** P6-P7 建立了 durable facts 但没有 owner 真源，P9 依赖 owner 真源。P8 是不可跳过的一环。 |
| 是否过度设计 | **否。** 方案精简，多个"不做"明确边界，复杂度与问题规模匹配。 |
| 不 takeover 策略是否合理 | **是。** 审计清晰、旧 attempt 不可变、新 attempt 干净。Takeover 有根本性缺陷。 |
| async ObserverSink 时机 | **合适。** 更早扩大 P6/P7 scope，更晚增加迁移成本。与 observer claim 分离正确。 |
| multiprocessing 边界 | **正确。** 测试 helper 限定在 tests/，不进入 dayu.runtime。需要 code review gate 防止泄漏。 |
| 遗漏/风险 | **无阻断性遗漏。** 6 个 Low/Medium 发现均可在 P8 实施中或 P9/P15 中处理。 |

P8 plan 已达到可实施标准。非阻断发现（F1-F6）建议在相应 slice 实施或后续 phase 中关注，不要求修改 plan。

---

## 附录：非阻断发现汇总

| ID | 严重度 | 描述 | 建议处理阶段 |
| --- | --- | --- | --- |
| F1 | Medium | ProjectionCoordinator 事务持有时间模型未量化 | P15 hardening |
| F2 | Medium | recovery attempt 的 terminal position 与 Run state 的关系需验证 | P8-S6 测试 |
| F3 | Low | LocalRunHarness 拆分缺乏具体指标 | P8 code review |
| F4 | Low | fenced write 可观测性未结构化 | P8 实施（结构化日志）/ P15（metrics） |
| F5 | Low | Run state 与 attempt state 的同步语义 | P8-S6 测试 / P9 lifecycle |
| F6 | Low | TTL/renew 默认值可能需要后续调整 | P15 hardening |
