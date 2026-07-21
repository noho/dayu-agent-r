# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Design — Final Re-Review (DS)

## Gate metadata

- 审查时间：2026-07-21 15:24:31 CST（来自本机系统时钟）。
- Gate：phaseflow 最终 design re-review gate（AgentDS）。
- Work unit：`WU-CLI-SMOKE-01-R1` final-closeout design correction。
- Reviewer：AgentDS，使用 `planreview` adversarial review 方法。
- 审查结论：**PASS**。
- Material findings：**0**。
- Blocking findings：**0**。

## Reviewed target and scope

本次只读复审以下输入，重点验证 `CODEX-REREVIEW-F01..F04` 是否在 `docs/host/design.md` 当前修订中真实关闭，并继续 adversarial 搜索新竞态、双 buffer、owner drift、过度承诺、遗漏实施范围和可实施项被留 residual：

- `docs/host/design.md`（当前工作区修订，全文扫描关键段落）；
- `docs/engine/design.md`（只读核对 Engine 边界未漂移）；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`（Codex 原设计记录）；
- `docs/reviews/wu-transient-delivery-ownership-design-rereview-codex.md`（Codex 二轮 re-review，4 findings，FAIL）；
- `docs/reviews/wu-transient-delivery-ownership-design-rereview-fix-codex.md`（Codex 二轮 fix mapping，claimed fixed-ready-for-second-re-review）；
- `docs/reviews/wu-transient-delivery-ownership-design-rereview-ds.md`（DS 二轮 re-review，PASS，0 findings）；
- `docs/reviews/wu-transient-delivery-ownership-design-rereview-mimo.md`（MiMo 二轮 re-review，PASS）。

为验证设计假设，直接核对了当前生产代码 `dayu/host/transient_delta.py`、`dayu/host/open_host.py`、`dayu/host/engine_ingest.py`、`dayu/host/dispatch.py`、`dayu/host/api.py`、`dayu/service/entrypoint_runtime.py`。这不是代码 review；代码只作为设计可实施性的事实证据。

总控旧行（`WU-HOST-TRANSIENT-CAPACITY-01` / `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01`）由 Phaseflow Controller 本 gate 后修订，不把尚未写回总控本身计为设计失败。

修改边界：只新建本 artifact；不修改设计、代码、总控、README、测试或既有 review artifact。

## First-principles assessment

修改动机成立。当前 Host 与 Service 各持有独立 256-item buffer（`_TRANSIENT_WATCH_BUFFER_CAPACITY` + `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`），`drain_nowait()` 在 async generator yield 间保留未计量 batch，`_terminal_run_ids: set[str]` 随历史 Run 无限增长，multi-watcher 无 admission cap，overflow 复用 `UNAVAILABLE` 语义。把 transient publication、fanout、mailbox、overflow 与 detach 收回 Host Session Event Delivery owner，同时删除 Service event-copy relay，是当前约束下最小且正确的方向。

二轮 Codex re-review（rereview-codex.md）识别的 4 个 findings（F01–F04）均位于语义 owner boundary：Service observation result 的 callback/EOF/fatal/ack-rebind/stop arbitration、Host batch drain 形成第二未计量 buffer、已知 multi-watcher 无 admission contract、overflow primary dimension 规则冲突。Codex fix（rereview-fix-codex.md）在 design.md 中冻结了所有缺失 contract，声称 `fixed-ready-for-second-re-review`。DS 与 MiMo 的二轮 re-review 均给出 PASS。

本次 final re-review 独立验证这 4 个 findings 在 design.md 中的真实关闭状态，并对全设计做 adversarial 搜索。

## CODEX-REREVIEW-F01..F04 逐项 closure 验证

### CODEX-REREVIEW-F01：generation-tagged closed observation result 的 callback/EOF/fatal/ack-rebind/stop arbitration

**Fix 声称**：§4.5 冻结 `ServiceObservationResult` closed union（5 variants）、sole first-commit owner、fatal sticky、generation handshake 状态机、same-tick slot arbitration、eager attach。

**当前 design.md 直接证据**：

| 证据点 | 位置（行号） | 内容 |
|--------|------------|------|
| Closed union 定义 | 411–419 | `TARGET_TERMINAL`、`DELIVERY_INTERRUPTED`、`ITERATOR_ENDED`、`CALLBACK_FAILED`、`ITERATOR_FAILED`，均携带 `target_generation` |
| Sole first-commit owner | 421 | "唯一 consumer 是所有 observation outcome 的唯一 first-commit owner"；task handle 只用于 lifecycle await，task.exception()/额外 Future/queue item 不得成为第二语义通道 |
| CALLBACK_FAILED 归属 | 421 | "Service adapter observation failure，consumer first-commit 后立即停止读取，helper 完成 cleanup 后向 caller 原样传播，不得改写为 Host error" |
| ITERATOR_ENDED（含 Host close） | 421 | "iterator 正常 EOF（包括 Host close）必须 first-commit ITERATOR_ENDED，禁止静默 task return 让 helper 永久等待" |
| Fatal sticky 规则 | 421 | `DELIVERY_INTERRUPTED`、`ITERATOR_ENDED`、`CALLBACK_FAILED`、`ITERATOR_FAILED` 均为 watcher-fatal；只有 `TARGET_TERMINAL` 可 ack 后复用 |
| Generation handshake 状态机 | 425–440 | `ATTACHED_UNBOUND -> CONSUMING(g) -> RESULT_READY(g) -> ATTACHED_UNBOUND` 完整循环；coordinator 必须按 consume/ack g → clear slot → bind g+1 → resume 顺序 |
| Same-tick arbitration | 444 | "slot first-commit 是 stop / terminal / failure 同拍的唯一仲裁点"；consumer 先取得 result 则 commit；先观察 stop 则不再 anext()；slot 已占用时不可覆盖 |
| Old generation rejection | 442 | "旧 generation 的迟到 callback、terminal、iterator completion 或 failure 都不得写入已清空的新 slot" |
| Eager attach | 364 | "只有 per-Session admission reservation 已取得、subscription 已进入 fanout owner、durable start-cursor attach 请求已在 durable actor 顺序中线性化后才可返回 iterator" |
| Stop-await-aclose 顺序 | 452 | "先发出 consumer stop / task cancellation，await task 完成并确认没有 active anext()，再调用 public HostSessionEventIterator.aclose()" |
| Never-started cleanup | 453 | "iterator 返回后若 consumer 尚未执行首次 anext()，同样先收口未启动 task，再调用 public aclose()" |

**反例压测**：

- callback throw → `CALLBACK_FAILED` commit → consumer 停止 → cleanup → 向 caller 传播。无第二通道。
- Host close → iterator 正常 `StopAsyncIteration` → consumer commit `ITERATOR_ENDED` → signal helper。不会静默挂死。
- startup A terminal → `TARGET_TERMINAL(g)` commit → RESULT_READY(g) → coordinator ack/clear → ATTACHED_UNBOUND → bind B as g+1 → resume。旧 generation g 迟到 event 被 generation 校验拒绝。
- stop/terminal/failure 同拍 → slot first-commit 仲裁。consumer 在 RESULT_READY 已暂停，不会产生第二个 outcome。

**判定**：✅ **CLOSED**。callback exception、normal EOF/Host close、startup multi-target rebind、same-tick arbitration 与 fatal sticky 全部冻结为可实施 contract。实施 Agent 无需自行设计 completion/error channel 或 rebind 协议。

---

### CODEX-REREVIEW-F02：eager attach；单项 transfer 与 in-flight 统一计量

**Fix 声称**：§4.2 禁止 batch drain、只允许单项 transfer；§4.3 mailbox + in-flight retained accounting；pop 不扣减、yield 恢复/cleanup 才扣减。

**当前 design.md 直接证据**：

| 证据点 | 位置（行号） | 内容 |
|--------|------------|------|
| 禁止 batch drain | 366 | "transient 读取接口必须是单项 pop / transfer；禁止 drain_nowait() 或任何返回 list / tuple / deque batch 的 API，也禁止 iterator generator 在逐项 yield 期间持有一批已从 mailbox 扣账的前缀" |
| In-flight accounting | 376 | "单项 pop 只把 entry 从 mailbox 转移为该 subscription 唯一的 in-flight event，不扣减 retained items / bytes" |
| Yield 时仍计入 | 376 | "iterator 把该 event yield 给 caller 后，在 generator 下次恢复或 iterator cleanup 前，Host 仍持有该 in-flight 引用并继续把它计入同一 budget" |
| 扣减时机 | 376 | "只有 yield 恢复 / cleanup 清除 Host 引用时才按 entry 保存的 size 精确扣减" |
| Prospective accounting | 376 | "publisher 的 prospective accounting 始终使用 mailbox + in-flight 的 retained totals，因此 Host owner 内单 subscription 的 retained items / bytes 永不超过 policy" |
| 禁止 Service relay queue | 366 | "Service / UI adapter 必须直接消费该 iterator，不得再建立第二个保留 HostSessionEvent 的 relay queue" |
| Future scope 删除 batch | 464 | 显式要求删除 batch `drain_nowait()` 及所有 `list`/`tuple`/`deque` drain shape，改为单项 pop/transfer |

**反例压测**：

- mailbox 有接近 B bytes 的事件 → pop 一项到 in-flight（不扣减） → yield 暂停 → publisher refill mailbox。此时 retained = in-flight(1项) + mailbox(≤B-1项)，仍在 policy 内。不存在 batch drain 那种"mailbox 已扣账到 0 但 generator 仍持有整批 tuple"的双 buffer。
- yield 恢复 → 清除 in-flight 引用 → 扣减 → retained 减少 → publisher 可继续 offer。
- 唯一 in-flight 是最多一项，不是一批。

**判定**：✅ **CLOSED**。单项 transfer + in-flight 统一计量消除了 batch drain 的第二未计量 buffer。Host owner 内单 subscription retained items/bytes 可证明不超过 policy。

---

### CODEX-REREVIEW-F03：required `max_subscriptions_per_session`、attach reservation / `resource_exhausted` / release / derived bound

**Fix 声称**：§4.2 required cap；§4.4 reservation、专属 error、release 与 cap 乘积；multi-watcher 已冻结为 public contract。

**当前 design.md 直接证据**：

| 证据点 | 位置（行号） | 内容 |
|--------|------------|------|
| Required policy 字段 | 368 | `HostSessionEventDeliveryPolicy` required 字段固定为 `transient_mailbox_max_items: int`、`transient_mailbox_max_bytes: int`、`max_subscriptions_per_session: int`，三者均为非 bool 正整数 |
| Attach reservation | 401 | "Session Event Delivery 对每个 Session 维护 max_subscriptions_per_session 个 reservation。attach-time check + reserve 必须在 opener owner loop 内线性化，并发生在任何 subscription mailbox、durable cursor future / request 或 per-watcher task allocation 之前" |
| Cap+1 fail closed | 401 | "若 prospective reservation count 超限，watch_session_events(...) 立即按上述 RESOURCE_EXHAUSTED contract fail closed，被拒绝 attach 不分配任何 watcher resource" |
| 不驱逐既有 watcher | 401 | "拒绝不得驱逐、detach、缩容或改变既有 watcher，也不得影响其它 Session" |
| Typed error contract | 397 | `HostApiErrorCode.RESOURCE_EXHAUSTED = "resource_exhausted"`、`retryable=true`、`HostSessionEventAdmissionDetail(reason=HostSessionEventAdmissionReason.SESSION_SUBSCRIPTION_LIMIT_REACHED)`、reason string 固定为 `"session_subscription_limit_reached"` |
| 全释放路径 | 403 | "partial attach failure、aclose()、never-started close、overflow prefix/error cleanup 后的 DETACHED、其它 iterator error / normal EOF cleanup 与 Host close 都必须在 owner loop 幂等释放" |
| Overflow 仍占 reservation | 403 | "overflow 从 fanout 排除到最终 detach 之间仍占 reservation" |
| Derived bound | 403 | "每 Session transient retained logical upper bound 可推导为 max_subscriptions_per_session × transient_mailbox_max_items 与 max_subscriptions_per_session × transient_mailbox_max_bytes，同步 fanout 的 watcher upper bound 为 max_subscriptions_per_session" |
| Multi-watcher 已冻结 | 401 | "当前 topology 已由生产代码的 Session -> set[subscription] 与双 watcher public contract tests 裁决为 multi-watcher；实施 WU 不得重新论证为单 watcher 或保留条件分支" |
| 边界诚实声明 | 403 | "generator 外 caller 自己保留的对象、Python 对象头精确 heap、Host 全局 Session 数量及跨 Session 总内存不在该乘积承诺内" |

**反例压测**：

- cap=3，已有 3 个 watcher → 第 4 个 attach 在 mailbox/cursor/task allocation 前被 `RESOURCE_EXHAUSTED` 拒绝。既有 3 个 watcher 不受影响。
- watcher overflow → 标记 OVERFLOWED → prefix 交付 → error cleanup → DETACHED → 释放 reservation。cap 从 3 变为可用 3。
- watcher aclose → DETACHED → 释放 reservation。cap 可用数 +1。
- 不同 Session 独立计数：Session A 满不影响 Session B attach。
- 最坏情况 retained = cap × per-subscription budget。可推导。

**判定**：✅ **CLOSED**。`max_subscriptions_per_session` 已冻结为 required policy 字段，attach reservation/resource_exhausted/全部释放路径/derived bound/跨 Session 隔离均已冻结。不存在未设计的 public admission contract。

---

### CODEX-REREVIEW-F04：overflow primary dimension 唯一算法

**Fix 声称**：§4.3 三步唯一顺序；§4.6 四组 exact fixtures。

**当前 design.md 直接证据**：

| 证据点 | 位置（行号） | 内容 |
|--------|------------|------|
| 三步算法 | 378 | 第一：单 event 自身 `delivery_size_bytes > transient_mailbox_max_bytes` → `PAYLOAD_BYTES`；第二：`retained_items + 1 > transient_mailbox_max_items` → `ITEM_COUNT`；第三：`retained_bytes + delivery_size_bytes > transient_mailbox_max_bytes` → `PAYLOAD_BYTES` |
| item-full + oversized 确定性 | 378 | "因此 item-full + oversized event 固定报告 PAYLOAD_BYTES" |
| Metrics vs public detail | 378 | "operator metrics 可以由实施 WU 用低基数设计记录同一 offer 命中的全部维度，但 public detail 只能携带上述算法选出的一个 primary dimension" |
| 四组 exact fixtures | 472 | 空 mailbox + oversized=`PAYLOAD_BYTES`；item-full + small=`ITEM_COUNT`；item 尚有余量但 cumulative bytes over=`PAYLOAD_BYTES`；item-full + oversized=`PAYLOAD_BYTES` |

**反例压测**：

| 场景 | 算法判定 | 结果 |
|------|---------|------|
| 空 mailbox，event 自身 2000 bytes > max_bytes=1000 | Step 1 命中 | `PAYLOAD_BYTES` |
| retained_items=99, max_items=100, event 自身 100 bytes < max_bytes=1000 | Step 2 命中（100>100? 否，不命中）；Step 2: retained_items+1=100, max_items=100，不命中；Step 3 检查 bytes... 等等让我重新算。retained_items=99, event arrives: Step 1: delivery_size=100 ≤ 1000，不命中。Step 2: 99+1=100 > 100? 否，不命中。Step 3: retained_bytes+100 > max_bytes? 取决于是多少。如果 retained_bytes=950, 950+100=1050>1000 → `PAYLOAD_BYTES`。如果 retained_bytes=500, 500+100=600≤1000，不 overflow。正确。 |
| retained_items=100, max_items=100, event 自身 100 bytes | Step 1 不命中。Step 2: 100+1=101>100 → `ITEM_COUNT` |
| retained_items=100, max_items=100, event 自身 2000 bytes > max_bytes=1000 | Step 1 命中 → `PAYLOAD_BYTES` |

无冲突。所有场景有唯一 deterministic 结果。

**判定**：✅ **CLOSED**。单一算法 + 四组 exact fixtures 消除了"先判 item count"与"单 event oversized 固定 PAYLOAD_BYTES"的冲突。item-full + oversized 固定为 `PAYLOAD_BYTES`，不再有歧义。

---

## Closure 汇总

| Finding | 状态 | 关键证据 |
|---------|------|---------|
| `CODEX-REREVIEW-F01`（高）：sole-consumer callback/EOF/fatal/ack-rebind/stop arbitration | ✅ CLOSED | §4.5 closed union、sole first-commit、fatal sticky、generation handshake、same-tick arbitration、eager attach |
| `CODEX-REREVIEW-F02`（高）：batch drain 第二未计量 buffer | ✅ CLOSED | §4.2 单项 transfer、§4.3 in-flight unified accounting、pop 不扣减/yield 恢复扣减、prospective=mailbox+in-flight |
| `CODEX-REREVIEW-F03`（高）：multi-watcher aggregate/admission 未设计 | ✅ CLOSED | §4.2 required `max_subscriptions_per_session`、§4.4 reservation/`resource_exhausted`/release/derived bound、multi-watcher frozen |
| `CODEX-REREVIEW-F04`（中）：overflow primary dimension 规则冲突 | ✅ CLOSED | §4.3 三步唯一算法、item-full+oversized=`PAYLOAD_BYTES`、§4.6 四组 exact fixtures |

**4/4 CLOSED。0 个 finding 仍处于未修复状态。**

## Adversarial 新问题搜索

对以下维度逐一压测，搜索新竞态、双 buffer、owner drift、过度承诺、遗漏实施范围和可实施项被留 residual：

### 1. 新竞态搜索

| 竞态场景 | 设计覆盖 | 判定 |
|---------|---------|------|
| yield 暂停期间 publisher refill → mailbox+in-flight 双重计数 | in-flight 计入 retained，prospective=mailbox+in-flight（行 376） | ✅ 已覆盖 |
| OVERFLOWED prefix 交付期间 publisher 继续 offer | OVERFLOWED 从 fanout snapshot 排除（行 382） | ✅ 已覆盖 |
| attach reservation check 与 detach release 的并发 | owner loop 线性化（行 401），幂等释放（行 403） | ✅ 已覆盖 |
| coordinator ack/rebind 与 consumer 下一次 anext() 的并发 | consumer 在 RESULT_READY 暂停，coordinator 先 ack/clear/rebind 再 resume（行 442） | ✅ 已覆盖 |
| stop signal 与 terminal 同时到达 | slot first-commit 仲裁：先取得 result 则 commit；先观察 stop 则不再 anext()（行 444） | ✅ 已覆盖 |
| Host close 与 in-flight yield 的并发 | Host close 关闭 publisher/subscriptions，清空 mailbox/in-flight，释放 reservation，iterator 正常结束（行 456） | ✅ 已覆盖 |
| anext() 与 aclose() 并发 | 显式禁止：先 stop/await task 确认无 active anext()，再 aclose()（行 452） | ✅ 已覆盖 |
| durable cursor future 未完成时 caller aclose | cursor future 必须被观察/收口，不能留下 unhandled future（行 1128） | ✅ 已覆盖 |

**新竞态 finding：0。**

### 2. 双 buffer 搜索

| 潜在双 buffer 位置 | 设计处置 | 判定 |
|-------------------|---------|------|
| Host batch drain（drain_nowait → tuple） | 禁止 batch drain，改为单项 transfer（行 366） | ✅ 已消除 |
| Service relay queue（asyncio.Queue） | 删除 relay queue，Service 直接消费 iterator（行 366, 470） | ✅ 已消除 |
| In-flight event（generator frame 引用） | 显式计入 retained accounting（行 376） | ✅ 非隐藏 buffer |
| ServiceObservationResult slot | 容量一、只存 terminal/failure semantic result，不是 event buffer（行 411） | ✅ 非 event buffer |
| Generator 内部状态 | 单项 transfer 保证 mailbox 外至多一项 in-flight（行 376） | ✅ 无隐藏 batch |
| Durable EventLog reader | 有界分页拉取，不复制进 transient mailbox（行 366） | ✅ 已隔离 |

**双 buffer finding：0。**

### 3. Owner drift 搜索

| 语义 | Owner | 是否漂移 |
|------|-------|---------|
| Transient publication/fanout | Session Event Delivery publisher | ✅ 唯一 owner |
| Per-subscription mailbox/overflow/detach | Session Event Delivery subscription | ✅ 唯一 owner |
| Per-Session admission/reservation | Session Event Delivery admission | ✅ 唯一 owner |
| Delivery error（DELIVERY_INTERRUPTED） | Session Event Delivery subscription | ✅ 不再复用 UNAVAILABLE/HostUnavailableDetail |
| Attach rejection（RESOURCE_EXHAUSTED） | Session Event Delivery admission | ✅ 独立于 delivery interruption |
| Delivery policy 装配 | runtime composer/operator | ✅ 唯一 owner，Service/UI/Run 不覆盖 |
| Post-terminal late-state validation | Host EngineEvent ingest | ✅ 唯一 owner，subscription 不重做 |
| Sole anext/observation result | Service watch runtime | ✅ 唯一 consumer task |
| Callback 快速非阻塞 | Service/UI adapter owner | ✅ 不在 Host no-backpressure 承诺内 |
| Durable terminal/recovery | EventLog/Outbox/get_run | ✅ 不变 |

**Owner drift finding：0。**

### 4. 过度承诺搜索

| 承诺 | 边界 | 是否过度 |
|------|------|---------|
| Host publish 不等待被动 consumer/capacity | 排除同-loop 阻塞 callback/CPU/O(N) fanout（行 358） | ✅ 边界诚实 |
| 单 subscription retained ≤ policy | Host owner 内；不含 caller 持有的引用（行 376） | ✅ 边界诚实 |
| 每 Session retained ≤ cap × per-sub budget | 不含 generator 外 caller 引用、Python heap、跨 Session 总内存（行 403） | ✅ 边界诚实 |
| No-backpressure | 不含 callback 物理隔离，callback 约束归 Service/UI（行 358） | ✅ 边界诚实 |
| Derived bound | 只承诺 logical item/byte，不承诺精确 Python heap（行 403） | ✅ 边界诚实 |

**过度承诺 finding：0。**

### 5. 遗漏实施范围搜索

对照 fix-codex.md 的 Future WU scope（行 196–207）与 design.md §4.6（行 458–478）：

| 实施项 | design.md 覆盖 | 状态 |
|--------|---------------|------|
| Public API 类型（iterator/policy/error/enum） | 行 462–463 | ✅ |
| Config assembly（typed config → policy） | 行 467–469 | ✅ |
| Host mailbox 实现（policy-driven items/bytes/fence/detach） | 行 464 | ✅ |
| Iterator facade 合流（policy 注入、cleanup） | 行 465 | ✅ |
| Ingest/dispatch 审计 | 行 466 | ✅ |
| Service relay 删除 + sole consumer 状态机 | 行 470 | ✅ |
| CLI callback adapters | 行 471 | ✅ |
| 旧常量/术语迁移 | 行 474 | ✅ |
| Owner-level/E2E tests（含 admission/aggregate/barrier fixtures） | 行 472 | ✅ |
| README 触发更新 | 行 476 | ✅ |
| Multi-watcher topology 冻结 | 行 478 | ✅ |

唯一 deferred 的三项（packaged 数值、heap margin、低基数 metrics）明确标记为需要 workload/SLO 证据的测量参数，不是当前可实施的结构性逻辑。

**遗漏实施范围 finding：0。**

### 6. 可实施项被留 residual 搜索

检查所有已冻结 contract 是否被错误标记为 "future measurement" 或 "residual"：

| Contract | 状态 |
|----------|------|
| `HostSessionEventIterator` Protocol | ✅ 已冻结（行 364） |
| `HostSessionEventDeliveryPolicy` 三字段 | ✅ 已冻结（行 368） |
| `ServiceObservationResult` 五 variant | ✅ 已冻结（行 411–419） |
| Generation handshake 状态机 | ✅ 已冻结（行 425–440） |
| 单项 transfer + in-flight accounting | ✅ 已冻结（行 376） |
| Primary dimension 三步算法 | ✅ 已冻结（行 378） |
| `RESOURCE_EXHAUSTED` admission contract | ✅ 已冻结（行 397） |
| Multi-watcher topology | ✅ 已冻结（行 401） |
| 全部 release path | ✅ 已冻结（行 403） |
| 旧术语删除列表 | ✅ 已冻结（行 474） |
| 四组 exact overflow fixtures | ✅ 已冻结（行 472） |
| Service barrier test scope | ✅ 已冻结（行 472） |

**可实施项被留 residual finding：0。**

### 7. 非 Material 观察（不构成 finding）

以下观察不影响 PASS 判定，仅供后续参考：

1. **ConfigLoader 中间类型位置**：design.md 要求 ConfigLoader 解析 `session_event_delivery_policy` 但不 import `dayu.host`（行 467）。这意味着 config-level typed view（含三个正整数字段）必须定义在 `dayu.runtime` 或等价的层中立位置。设计未显式指定该中间 dataclass 的模块位置，但 "不得 import dayu.host" 约束足以指导实施——实施时自然会在层中立位置定义 config view。

2. **`retryable=true` 的 tight-loop 防护**：admission rejection 的 `retryable=true`（行 397）只在语义上表示"reservation 释放后重试可能成功"，行为约束"不授权 tight-loop retry"（行 397）是 Service 实施责任。设计没有指定最小重试间隔——这属于 Service 的既有退避/重试策略，不需要在本 delivery design gate 新增。

3. **Level-triggered readiness 的实现细节**：行 405 要求 "drain 与 readiness clear 的交界必须重新检查 owner state"——这是正确的实现级约束，但属于实施 WU 的实现关注点。

## Residual ownership

以下语义/状态已有唯一明确 owner，无需额外裁决：

| Residual / prerequisite | Owner | Tracking destination | Gate treatment |
| --- | --- | --- | --- |
| `WU-HOST-TRANSIENT-CAPACITY-01` 与 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 旧控制行登记冲突 | Phaseflow Controller | `docs/host/issues-implementation-control.md`，本 gate 后 controller adjudication | 不阻塞设计 PASS；不得由代码兼容分支消化 |
| packaged `transient_mailbox_max_items` / `transient_mailbox_max_bytes` / `max_subscriptions_per_session` 数值 | Future implementation WU（runtime composer/operator） | implementation plan / benchmark evidence | 测量 residual，不阻塞设计 |
| logical-byte 到 Python heap safety margin | Future implementation WU | implementation plan / benchmark evidence | 测量 residual，不阻塞设计 |
| 低基数 metrics 字段与采样 | Future implementation WU | implementation plan / production observation | 测量 residual，不阻塞设计 |
| Callback 快速非阻塞与慢 I/O/CPU 隔离 | Service / UI adapter owner | Service/CLI owner-level tests 与 README contract | 已有 owner |
| Engine ingest/publisher owner-loop affinity 与 terminal 前 publish 顺序 | Host ingest / dispatch owner | future WU code audit + contract tests | 验证项，不修改 Engine contract |

## 验证

- `git diff --check`：**pass**（无 whitespace diagnostic）。
- tracked diff 范围：仅 `docs/host/design.md`。未修改生产代码、测试、总控、README 或既有 review artifact。
- 代码事实核对：当前 `dayu/host/transient_delta.py` 仍含 `drain_nowait()`（6 处引用）、`_terminal_run_ids: set[str]`（行 201/218/255/305）、`_TRANSIENT_WATCH_BUFFER_CAPACITY=256`（行 26）、`_SLOW_CONSUMER_*`（行 27–29/96–109）；`dayu/service/entrypoint_runtime.py` 仍含 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY=256`（行 76）、`_WatchAndWaitRuntime.queue`（行 510/739/845/926/1027 等）、`_WatcherFailure`（行 1036–1054）。设计 §4.6 与旧术语迁移（行 474）已逐项列入删除范围，实施 WU scope 完整。
- 本 gate 不运行测试与 pyright：没有代码修改，且 gate 明确只要求设计全文审查与 diff whitespace validation。

## Final conclusion

**Verdict：PASS。**

`CODEX-REREVIEW-F01`（Service observation result closed union、sole first-commit、fatal sticky、generation handshake、same-tick arbitration、eager attach）、`CODEX-REREVIEW-F02`（单项 transfer、in-flight unified accounting、禁止 batch drain）、`CODEX-REREVIEW-F03`（`max_subscriptions_per_session` required field、attach reservation、`resource_exhausted`、全释放路径、derived bound）与 `CODEX-REREVIEW-F04`（三步唯一 primary-dimension 算法、四组 exact fixtures）已在 `docs/host/design.md` 当前修订中**全部真实关闭**。

Adversarial 新问题搜索覆盖竞态（8 个场景）、双 buffer（6 个潜在位置）、owner drift（10 个语义）、过度承诺（4 个承诺边界）、遗漏实施范围（11 个实施项）和可实施项被留 residual（12 个已冻结 contract），**0 个新 material finding**。

设计当前状态：自洽、可实现、code-generation-ready。所有 public contract（iterator、policy、error、admission、overflow algorithm、state machine、release lifecycle）已冻结，实施 Agent 无需重新设计公共或并发语义。可进入 implementation plan/gate。

唯一仍由 Controller 裁决的项是旧 `WU-HOST-TRANSIENT-CAPACITY-01` / `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 总控行登记冲突——这不阻塞设计 PASS，也不得由代码兼容分支消化。

---

*Final re-review artifact path: `docs/reviews/wu-transient-delivery-ownership-design-final-rereview-ds.md`*
