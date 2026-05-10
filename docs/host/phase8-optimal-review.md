# Host P8 最优方案对比 Review

## 结论：当前 plan 在所有 9 个关键设计维度上均为最优或正确选择，无必须修项

本文档逐项比较 P8 的 9 个关键设计选项，在每个维度上给出 tradeoff 分析、推荐方案、理由，并判断当前 plan 是否最优。若当前 plan 不是最优，明确哪些必须在 plan gate 修、哪些可以后移并指定 owner。

---

## 1. Recovery 策略：new recovery attempt vs takeover same attempt vs mark lost only

### Tradeoff

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **new recovery attempt（plan 选择）** | attempt_index 反映真实执行次数；新旧 attempt 审计边界清晰；tool trace 可区分新旧事件；无法污染旧 attempt 的 EventLog 事实 | 同 run 下 attempt 行数增多（非问题） |
| takeover same attempt | attempt_index 不增长，看起来"连续" | 审计边界混乱——新旧 owner 写入同一 attempt_id，无法区分责任；旧 owner late write 可能和新 owner 写入交织；违反 "同一 attempt 只有一个有效 owner" 的语义 |
| mark lost only | 实现最简单 | 不提供自动恢复，需人工介入；Full-Governance Multi-Turn 要求系统能自愈 |

### 推荐：new recovery attempt（当前 plan）

**理由：**

attempt_index 必须反映"实际发生了多少次执行尝试"这一持久事实。takeover 同一 attempt 会让 attempt_index 与实际执行次数脱钩，给 tool trace、audit、memory projection 等下游消费者制造错误的 attempt 边界信号。mark lost only 在多进程生产环境中不可接受——进程崩溃后必须能自动恢复。

plan 的 `RECOVERING + new attempt` 主路径是正确的：旧 attempt 被 CAS 关闭为 `RECOVERING`，新 attempt 通过 `recovered_from_attempt_id` 指回来源，tool trace 通过 source event position + attempt_id 区分新旧事件。该路径在 §10 已完整定义，包括 run 已 terminal 时的 `NOOP_TERMINAL` 快速路径。

**结论：当前 plan 最优。不修。**

---

## 2. Lease 存储：扩展 host_attempts vs 新 host_attempt_leases 表

### Tradeoff

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **扩展 host_attempts（plan 选择）** | 单行 CAS 操作——同一行内校验 state、owner_token_hash、lease_generation、lease_expires_at；无 JOIN；lease 与 attempt 生命周期天然 1:1 | 表列数增多 |
| 新 host_attempt_leases 表 | 表面上"关注点分离" | 增加 JOIN；lease 状态与 attempt state 可能不一致（一个表更新成功另一个失败）；1:1 关系不产生规范化收益；CAS 需要跨表操作 |

### 推荐：扩展 host_attempts（当前 plan）

**理由：**

Lease 不是独立实体——它在语义上是 attempt 执行权的属性。`owner_token_hash`、`lease_generation`、`lease_expires_at` 与 `state`、`attempt_id` 在同一行，CAS 校验只需单条 `UPDATE ... WHERE` 语句，天然原子。新增 `host_attempt_leases` 表不仅增加复杂度，还引入"lease 行存在但 attempt state 不匹配"或相反的 inconsistency window。

plan §6.2 的 schema 设计是正确的：`lease_generation` 从 0 开始，acquire 时递增到 1，每次新 owner acquire 单调递增；`lease_expires_at` 在 terminal/STALE/RECOVERING/LOST 后保留最后值用于诊断。所有 CAS 条件（§6.4）只操作 `host_attempts` 单表。

**结论：当前 plan 最优。不修。**

---

## 3. Fencing 粒度：只 terminal fencing vs all attempt-scoped append fencing vs DB trigger

### Tradeoff

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **all attempt-scoped append fencing（plan 选择）** | 任何 stale owner 写入都被拦截；ToolRuntime facts、context facts、Engine-sourced events 均受保护；EventLog 零污染 | 每次 append 多一次 `verify_owner` SELECT（同事务内，开销可忽略） |
| 只 terminal fencing | 代码路径最简单 | stale owner 在 terminal 前可继续写 ToolRuntime facts（`TOOL_RESULT_TRUNCATED`、`TOOL_CURSOR_ISSUED`、`TOOL_FETCH_MORE_*` 等）、context compact facts、run input context snapshot fact——这些全部污染 EventLog；lease 过期到 terminal 之间的窗口可能很长 |
| DB trigger | 在 DB 层强制执行 | SQLite trigger 难以测试和版本控制；lease expiry 判断（`lease_expires_at > now`）需要 clock，trigger 内难以注入；token hash 比较逻辑属于业务逻辑，不应放在 DB 层 |

### 推荐：all attempt-scoped append fencing（当前 plan）

**理由：**

只 terminal fencing 是"假 fencing"——它允许 stale owner 在 lease 过期后继续写非 terminal 事件。P8 §7.1 列出的 ToolRuntime facts（7 种 `TOOL_*` 类型）、context overflow/compact facts、P7 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` fact 都属于 attempt-scoped Host-owned canonical facts，被 stale owner 写入会造成 tool trace 重复、memory projection 污染和审计事实失真。

plan 的 `AttemptScopedRunEventAppender`（§7.2）设计是正确的：每次 `append()` 在同一个 `BEGIN IMMEDIATE` 事务内执行 `lease_store.verify_owner()` 与 `event_store.append_with_position_in_transaction()`。verify_owner 的 WHERE 条件（§6.4）校验 state='running'、token hash、generation、lease 未过期，rowcount=0 时抛 `AttemptFencingError`。

DB trigger 方案是过度设计：fencing 判断依赖可注入 clock、typed error reason 映射和 masked logging，这些是 application logic，不应下沉到 SQLite trigger。

**结论：当前 plan 最优。不修。**

---

## 4. terminal_event_position：同事务 append+close vs append 后 update vs 查询 MAX(position)

### Tradeoff

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **同事务 append+close（plan 选择）** | 零 crash window；terminal_event_position 与 EventLog global position 严格一致；任何部分失败全部回滚 | 事务稍长（仍是一个 SQLite 事务，毫秒级） |
| append 后 update | 事务更短 | terminal event 已存在但 attempt 未指向 position 的窗口；需额外 reconcile 逻辑；违反 P6 残余风险追踪中"补齐 terminal_event_position"的初衷 |
| 查询 MAX(position) | 不需要改 append API | 同 run 下可能有其他事件在 terminal 之后 append（例如另一进程的 recovery attempt？不会——terminal guard 禁止）；但根本问题是 MAX 是间接推断，不是真源关联 |

### 推荐：同事务 append+close（当前 plan）

**理由：**

这是唯一在语义上正确的方案。P6 残余风险明确要求"terminal_event_position 必须从 durable EventLog 的 global position 真源补齐"。MAX(event_position) 不是真源——它是间接推断。append 后 update 在两个事务之间留下 crash window。

plan §8 的 `AttemptSupervisor.append_terminal_and_close(...) -> AttemptTerminalLink` 设计是正确的：5 步操作（校验 owner_context、verify_owner、append_with_position_in_transaction、close_terminal、返回 AttemptTerminalLink）在同一个 `BEGIN IMMEDIATE` 事务内完成。`AppendedRunEvent` 返回类型（`_durable_event_store.py:70-75` 已存在但为私有类型）包含 `event: RunEvent` 与 `event_position: GlobalEventPosition`，提供了同源真值。

plan 也明确禁止了错误实现（§8）：不允许 append 后另起事务 update、不允许用 MAX 猜 position、不允许先 close 再补 position。

**结论：当前 plan 最优。不修。**

---

## 5. ObserverSink：P8 async 升级 vs 后移到 P15 vs 保持 sync

### Tradeoff

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **P8 async 升级（plan 选择）** | 删除已确认的 P6 技术债（`_run_async` thread+event loop bridge）；P8 做多进程 observer drain 验证前统一协议，避免后续 P15 大面积改测试；observer 实现（memory/timeline/audit/tool trace）迁移范围确定 | 需改动所有 observer 实现和 projection tests |
| 后移到 P15 | P8 diff 更小 | P15 负担更重；P8 多进程测试可能被迫围绕 sync-async bridge 写 workaround；技术债跨 7 个 phase 不还；P15 再改时需同时处理 observer claim/lease |
| 保持 sync | 零改动 | `_run_async` bridge 永久存在；每个 terminal projection 创建 thread + event loop；未来任何 observer 做 async IO 都要桥接 |

### 推荐：P8 async 升级（当前 plan）

**理由：**

`_run_async` bridge 是 P6 code review 中已确认的技术债（`docs/host/migration-plan.md` §4.2 `deferred-with-owner: P8/#28/P15`）。该 bridge 在每个 terminal projection 都会创建 thread + event loop，已是实际存在的运行时开销和代码异味。

时机上 P8 是最优的：P7 新增了 `ToolTraceObserver`（文件 IO），P8 本身要做多进程 observer drain 验证。如果等到 P15，累积的 sync-async bridge 和 workaround 会更多，改动面更大。plan §11 已正确限定迁移范围：改 `ObserverSink` Protocol → 改 4 个 observer 实现 → 改 `ProjectionCoordinator` 调用点 → 改所有相关 tests。不引入 observer claim/lease，不改成后台 worker。

**结论：当前 plan 最优。不修。**

---

## 6. Observer claim/lease：P8 不做是否最优，还是应该跟 attempt lease 一起做

### Tradeoff

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **P8 不做（plan 选择）** | P8 scope 可控；observer ownership 与 attempt ownership 是两个独立状态机，不应耦合；P8-S7 通过 deterministic multiprocessing 测试验证当前设计在单 drainer + 幂等 sink 下正确 | 未来若需多 drainer 并发消费，需要补 claim/lease |
| 跟 attempt lease 一起做 | 一次性解决 ownership 问题 | 显著扩大 P8 scope：需设计 observer claim 协议、observer lease 字段、lease 过期清理、stale observer 处理、ProjectionCoordinator 升级为竞争消费者；这些与 attempt lease 解决的问题不同（attempt lease 解决"谁写"，observer claim 解决"谁消费"），强行捆绑会增加耦合和测试矩阵 |

### 推荐：P8 不做（当前 plan）

**理由：**

Attempt ownership 和 observer ownership 是两个不同的状态机：
- Attempt lease 回答：谁有权向 EventLog 写入 attempt-scoped facts？
- Observer claim 回答：谁有权消费 EventLog 并推进 projection checkpoint？

当前 P6/P7 的 projection 设计是：单进程内 `ProjectionCoordinator` 持有 `_drain_lock`（进程内互斥），observer sink 幂等写入，checkpoint 同事务推进。这个设计在单 drainer 下是正确的。P8-S7 的 deterministic multiprocessing 测试可以验证：在多进程场景下（每个进程有自己的 `ProjectionCoordinator` 或只有 recovery 后的新进程 drain），只要不同时有两个进程 drain 同一 observer，就不会出现 checkpoint conflict。

plan 的处置是正确的：P8 验证当前设计可行，不引入 observer claim。若未来需要后台 observer worker 或多个进程并发 drain 同一 observer，由 #28 或 P15 单独设计。这不是 scope 逃避，而是正确的关注点分离。

**结论：当前 plan 最优。不修。**

---

## 7. Multiprocessing 验证：默认 deterministic pytest + #38 慢盘 Docker stress 是否是最佳策略

### Tradeoff

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **deterministic pytest + #38 stress（plan 选择）** | 确定性测试始终运行，捕获逻辑错误；重压 stress 捕获时序 bug，但不阻塞 CI；职责分离清晰 | 需要维护两套测试 |
| 全部放默认 pytest | 一个命令跑所有 | CI 不稳定——慢盘 Docker stress 本身非确定性；资源需求高；可能因 CI 环境差异导致 flaky |
| 只手工 smoke | 零 CI 维护 | 回归保护为零——多进程正确性无法持续验证 |

### 推荐：默认 deterministic pytest + #38 慢盘 Docker stress（当前 plan）

**理由：**

这是测试策略的标准最佳实践。P8-S7 的默认 pytest 必须覆盖跨进程 append、terminal race、stale recovery、observer drain 四类场景——这些场景使用确定性同步（如 barrier、fake clock、受控进程终止）来触发竞态条件，结果可复现。这保证了每次 CI 都能验证多进程基本正确性。

#38 慢盘 Docker stress 解决的是另一类问题：在真实 IO 延迟、OS 进程调度抖动下的时序 bug。这类测试本质上是 flaky 的，不应进入 CI 阻塞门。将它们分离到独立 issue 是正确的工程判断。

plan §16 要求的"基础跨进程 append / terminal race / stale recovery / observer drain 必须默认可运行"是正确的验收标准。

**结论：当前 plan 最优。不修。**

---

## 8. 多平台封装：tests/utils helper 是否比 dayu.runtime helper 更优

### Tradeoff

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **tests/utils helper（plan 选择）** | 符合架构约束——dayu.runtime 不得承载 Host 业务语义；测试基础设施不应与生产运行时混合；start method 选择、join timeout、进程终止、临时 SQLite path、跨进程结果收集是测试关注点 | 如果后续发现某个 helper 是真正的层中立能力，需要从 tests 迁移到 dayu.runtime |
| dayu.runtime helper | 可被多层复用 | 违反 `dayu.runtime` 只能承载层中立能力的约束；`multiprocessing.set_start_method`、`join(timeout)`、exitcode 断言、跨进程 result queue 收集不是生产运行时能力——是测试基础设施；dayu.runtime 不应依赖 `multiprocessing` 或 `pytest` |

### 推荐：tests/utils helper（当前 plan）

**理由：**

P8 需要的平台封装内容包括：`multiprocessing.set_start_method`（macOS 默认 spawn vs Linux 默认 fork）、`Process.join(timeout)`、`Process.terminate()`、`Process.kill()`、`exitcode` 断言、文件 SQLite path vs `:memory:`、跨进程 result 收集。这些全部是测试基础设施关注点，不是生产运行时能力。

`AGENTS.md` 架构硬约束明确：`dayu.runtime` 不得承载业务语义，只能承载层中立、运行期通用、可被多层复用的基础能力。在多进程测试 helper 中封装 `set_start_method` 和 `join(timeout)` 显然不属于"层中立运行时能力"——它们是测试进程管理的 glue code。

plan 的措辞是精确的：§1 说"该封装先定位为测试 / smoke helper，不提升为 Host 生产 launcher"；§5 说"若后续发现某个 helper 属于层中立运行时能力……再单独评估是否进入 dayu.runtime"。这是正确的渐进式判断。

**结论：当前 plan 最优。不修。**

---

## 9. Rejected late write 处理：typed error/log vs diagnostic EventLog fact vs audit sink

### Tradeoff

| 方案 | 优点 | 缺点 |
| --- | --- | --- |
| **typed error + masked log（plan 选择）** | stale owner 无法向 canonical EventLog 写入任何事实（包括"我被拒绝了"这种 meta-fact）；typed error 给调用方足够的编程信息；masked log 给运维足够的诊断信息 | 如果生产合规要求审计所有 rejected write，需要另设机制 |
| diagnostic EventLog fact | rejected write 有持久记录 | **自相矛盾**：fencing 的核心目的是阻止 stale owner 污染 EventLog；允许 stale owner 写 "我被 fenced" 事件等于给 stale owner 开了后门——恶意或 buggy 的 stale owner 可以刷屏 diagnostic 事件；canonical facts 中不应包含来自非 owner 的"元事实" |
| audit sink | 分离审计关注点 | P8 过度设计——rejected write 的审计需求尚未确认；独立的 audit sink 增加运维复杂度；若未来确有需要，可以在已有 typed error 基础上外挂 observer |

### 推荐：typed error + masked log（当前 plan）

**理由：**

这是 fencing 语义一致性的直接推论。Fencing 的定义是"非 owner 不得写入"。如果非 owner 可以通过写"我被拒绝了"来绕过这个定义，fencing 就形同虚设。plan §1 的表述是正确的："非 owner / stale owner 不应污染 canonical facts；拒绝以 typed error / result 和安全日志表达。"

`AttemptFencingError`（§6.1）携带 `attempt_id`、`run_id`、`reason: AttemptFencingReason`、`current_state`、`owner_id`、`lease_generation`，给调用方足够的编程信息来决定后续行为（取消 Engine run、记录本地日志、清理资源）。masked log 携带 `owner_id`、`generation`、`masked token`、reason，给运维足够的诊断信息。

plan 的措辞"若后续需要 audit rejected write，另设治理 issue"是正确的：这不是 P8 的 scope，且不应通过在 EventLog 中给 stale owner 开口子的方式实现。

**结论：当前 plan 最优。不修。**

---

## 综合结论

当前 P8 plan 在全部 9 个关键设计维度上的选择均为最优或正确：

1. **Recovery**：new recovery attempt 是唯一正确的选择——保证审计边界和 attempt_index 真实性。
2. **Lease 存储**：扩展 host_attempts 优于新表——语义上 lease 是 attempt 属性，CAS 原子性天然。
3. **Fencing 粒度**：all attempt-scoped append fencing 是 full-governance 的必需——只 terminal fencing 是假 fencing。
4. **terminal_event_position**：同事务 append+close 是唯一语义正确的方案——其他方案都引入 inconsistency window。
5. **ObserverSink async**：P8 是升级的最佳时机——在技术债扩大前修复，P8 多进程验证受益于协议统一。
6. **Observer claim/lease**：P8 不做是正确的关注点分离——attempt ownership 和 observer ownership 是独立状态机。
7. **Multiprocessing 验证**：deterministic + separate stress 是测试最佳实践——CI 稳定性与覆盖深度兼得。
8. **多平台封装**：tests/utils helper 符合架构约束——测试基础设施不应进入 dayu.runtime。
9. **Rejected late write**：typed error + masked log 是唯一语义一致的选择——stale owner 不应有任何 EventLog 写入权。

**无必须在 plan gate 修的项。无需要后移并指定 owner 的项。**

### 实施关注项（非阻断）

以下不是设计选择问题，而是实施时需要精确处理的细节，在 plan 中已有正确方向：

- **Recovery 与 run 已 terminal 的竞态**：plan §10 step 1 已处理（`NOOP_TERMINAL`），实施时确保 run terminal check 和 attempt state check 在同一事务内。
- **Recovery attempt 的 UNIQUE(run_id, attempt_index) 冲突**：两个 recovery 进程可能同时计算 `MAX(attempt_index)+1`，UNIQUE 约束会拒绝其中一个。实施时需将冲突映射为 `MARK_LOST` 或重试，不能静默吞掉。
- **async observer 事务持有的范围**：`await observer.process(tx=tx, batch=envelopes)` 期间 SQLite 事务保持 open。对 memory/timeline/audit observer（写 SQLite，同一 WAL）这是正确的；对 ToolTraceObserver（写文件系统），事务内无 SQLite 写入，仅 checkpoint 推进时才写 SQLite。确认 `ProjectionCoordinator` 在 await 前后的事务边界与 P6 一致。
- **lease_expires_at 的 clock 一致性**：plan 使用可注入 `UtcClock`，测试用 fake clock。生产中使用 `datetime.now(tz=timezone.utc)`——Python 和 SQLite 读同一系统时钟，同机多进程偏差可忽略。实施时确保 SQLite 的 `now`（如用 `datetime('now')`）与 Python 的 `datetime.now(UTC)` 通过应用层传入而非混用。
