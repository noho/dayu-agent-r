# WU-CLI-SMOKE-01-R1 Session Event Delivery 最终 Closure Review（Codex）

## Review metadata

- 生成时间：`2026-07-21 16:40:30 +0800`（本机系统时钟；timestamp：`20260721-164030`）。
- Review 类型：独立、从第一性原理出发的 adversarial closure review。
- 结论：**FAIL**。
- Material findings：**2**。
- Severity：**高 × 2**。
- 未归属 residual：**0**；未决 material 问题全部归入下述 findings。
- 本 review 只新增当前 artifact；未修改设计、代码、测试、总控或 README，未提交。

## Reviewed target and scope

本次只读取并审查：

- `docs/host/design.md`；
- `docs/engine/design.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-closure-rereview-fix-codex.md`；
- `dayu/host` 当前生产代码以及设计明确列入 future WU 的相关 Host / Service 测试边界。

未读取 AgentMiMo / AgentDS 本轮 artifact；未把其它 review artifact 当作证据。

重点核对：

1. 统一可关闭 `AsyncIterator` 外观及 eager attach；
2. 慢 UI / Service 不反压 Agent / Engine；
3. 每订阅唯一 Host mailbox、Service 无 event-copy relay、items / bytes / subscriptions 三维容量与 retained accounting；
4. transaction-local exact terminal sequence、`TerminalPostCommitNotice` / `TerminalPostCommitPort` owner、当前 terminal producer 闭集；
5. notice 乱序、duplicate、optional promotion 与 A terminal → B delta fence；
6. Service exact-five disposition、generation handshake、stop / cancellation 仲裁与 cleanup precedence；
7. 实施文件、静态 callgraph、owner tests 与集成 barriers 是否足以使 implementation 可裁决；
8. 是否存在过度设计、错误耦合，或更简单且同样正确的方案。

## First-principles motivation decision

原始动机成立，严重性没有被高估：当前 Host 与 Service 双 event buffer、Host batch drain 外保留未计量前缀、item-only 容量、public iterator 关闭契约过宽，以及 terminal durable truth 到 live merge cutoff 缺少统一数据流，都会造成真实的内存边界、错误归因或 A/B 乱序问题。把 capacity 数值分别调大不能修复这些 owner 冲突。

最终设计中的以下方向是正确且必要的：

- 保留 Host-owned、显式 `aclose()` 的统一 `HostSessionEventIterator` facade；
- Engine ingest 只做 durable identity / late-state validation 和 non-blocking typed handoff；
- 每 subscription 只有一个 transient mailbox 与一个仍计费的 in-flight entry；
- Service 删除 event-copy relay，只保留 sole `anext()` consumer 与容量一的 observation-result slot；
- items、logical UTF-8 bytes 与 per-Session subscriptions 三维约束分别由明确 owner 管理；
- terminal exact sequence 来自产生或幂等确认 terminal 的同一 transaction result，不做 post-commit latest-row 猜测；
- 单 opener 内，watermark / terminal-ready wake 先于 optional promotion 的 coordinator 顺序、双 O(1) scalar 的 duplicate / `false -> true` 规则是自洽的；
- exact-five Service disposition 与 cleanup precedence 虽然严格，但对应五种真实且互斥的观察结果，没有证据表明它是无需求支撑的抽象。

问题在于，设计把上述“单 opener 内自洽”提升成了“满足项目多客户端 / 多进程约束下的全局正确性”，但现有 ownership 和时序没有提供这一步证明。

## Assumptions tested

| Assumption | 裁决 | 直接依据 |
|---|---|---|
| Engine 不应拥有 Host fanout / cursor / terminal fence | 成立 | `docs/engine/design.md:28-38,450-513`；Engine 只承诺单次 generator 顺序。 |
| 单 Host mailbox + in-flight、Service 无 relay 可隔离慢 consumer | 成立 | `docs/host/design.md:394-515`；当前双 buffer 事实见 `dayu/host/transient_delta.py:187-336`、`dayu/service/entrypoint_runtime.py:491-511,1016-1054`。 |
| items / bytes / subscriptions 与固定 primary-dimension 算法足以形成所声明的 per-Session logical retained bound | 成立 | `docs/host/design.md:400-435`；设计没有把 logical bytes 夸大为精确 Python heap。 |
| 当前 terminal transition callsites 位于 admission / waiting / recovery / engine ingest / dispatch 闭集内 | 对当前代码成立 | `dayu/host/durable/run_transition.py:1236-2817` 的 Run-terminal helpers，当前生产调用点只出现在 `admission.py`、`waiting.py`、`recovery.py`、`engine_ingest.py`、`dispatch.py`。 |
| opener-local `TerminalPostCommitPort` 足以让任一 live watcher获得 terminal cutoff | **不成立** | Finding 01。 |
| 已排队但尚未执行的 start-cursor read 与 owner-loop watermark baseline 能在同步返回前组成 atomic attach snapshot | **不成立** | Finding 02。 |
| 当前测试授权足以裁决上述两个时序 | **不成立** | future acceptance 只冻结同 coordinator barriers，没有双 opener / delayed cursor execution barrier；见 Findings 01、02。 |

## Material findings

### 01-未修复-[高]-opener-local terminal port 不能为多 opener / 多进程 watcher 提供 A terminal → B delta fence

- **位置**：`docs/host/design.md:11-12,340-346,360-390,524-549`；`docs/reviews/wu-transient-delivery-ownership-design-codex.md:79-87,109-123,194-199,234-258`；`dayu/host/open_host.py:1452-1519`。
- **问题类型**：架构边界 / 并发恢复风险 / 错误耦合 / 测试缺口 / 非最优方案。
- **当前写法**：设计一方面要求多个入口、多客户端和多进程共享同一本地 Host durable truth，另一方面把 terminal delivery cutoff 的唯一输入限定为“当前 `open_host` opener”内的 `TerminalPostCommitPort`。每个 opener 只维护自己的内存 hub、subscription、terminal watermark 和 promotion watermark；普通 accepted / queued reconciliation 明确继续走只含 `session_id` 的普通 promotion port，且不得推进 terminal watermark。
- **反例/失败场景**：
  1. opener C 上已有一个长期 Session watcher，durable cursor 尚未读到 Run A terminal；Run A 由 opener A 的 worker / cancel / wait / recovery producer提交 terminal。
  2. A 的 exact notice只进入 opener A 的 coordinator；C 的 `committed_terminal_event_sequence_high_watermark` 不变，因为 notice 不持久化、没有跨 opener fanout，也没有 DB-backed change feed。
  3. A terminal 后，Service 通过 opener C 提交 Run B。C 的 admission 看到 active slot 已释放，按 ordinary accepted / governance 路径唤醒 C scheduler；设计明确禁止 ordinary promotion推进 terminal watermark。
  4. C 执行 B 并向自己的 hub 发布 B delta。C watcher 在 pop 前只比较自己的 local watermark；由于它没有 A notice，可以先 pop / yield B delta，再在后续 durable poll中发现 A terminal。
  5. 结果直接违反设计承诺的 A terminal first-commit / ack / rebind 后下一次 `anext()` 才交付 B，也使“所有 terminal producer 已闭环”的结论只在 producer 所属 opener 内成立。
- **为什么有问题**：terminal EventLog truth是跨连接 / 跨进程共享事实，而 `TerminalPostCommitPort` 是 opener-local ephemeral control。把后者作为前者到所有 watcher 的唯一 correctness bridge，混淆了 durable fact owner 与单 runtime wake optimization owner。静态 callgraph 即使证明每个 producer都调用了“自己的 port”，也不能证明其它 opener 的 delivery owner收到 cutoff。
- **直接证据**：
  - `docs/host/design.md:11-12` 明确要求多入口、多客户端 / 多进程；`docs/host/design.md:342,350-351` 又明确每个 watch / runtime identity只属于同一 `open_host` runtime。
  - `docs/host/design.md:380-384` 把 port implementation、两个 watermark 和 A/B 顺序全部放在“当前 opener”内；`docs/host/design.md:360,390` 明确 notice / watermark不持久化、断开或新 runtime不重放。
  - `dayu/host/open_host.py:1452-1463` 每次 opener打开独立 durable store / event loop并新建一个 `HostTransientDeltaHub`；`dayu/host/open_host.py:1485-1519` 只把该 hub和该 opener wake bridge装配到本地 scheduler / actor。
  - `dayu/host/dispatch.py:1118-1138,1228-1264,2921-2969` 的 ordinary promotion queue只持有 `session_id` 并在本 scheduler内推进；它没有其它 opener watermark引用。
  - future acceptance `docs/host/design.md:537-549` 覆盖单 coordinator、三组 non-Engine A/B barrier和 AST callsites，但没有“两个 `open_host` 共享同一 DB、terminal与 B execution 分属不同 opener”的 barrier，因此无法证伪上述反例。
- **影响**：生产多入口 / 多进程下，在线 watcher可能观察到 B delta先于 A durable terminal；Service generation handshake失去前提；静态 producer manifest产生错误的 closure 信心。implementation agent即使完全按现设计实现，也会交付错误行为。
- **建议改法和验证点**：
  1. 明确把 `TerminalPostCommitPort` 降为“producer 所属 opener 的 prompt wake + optional promotion协调”owner，不再把 opener-local notice当成所有 delivery runtimes 的唯一 correctness source。
  2. 给每个 transient candidate / mailbox entry 增加由 Engine ingest **同一 durable validation transaction** 取得的 causal durable fence，例如当前 Run 的 `started_event_sequence`（或等价、同源且精确的 validation watermark）。Session Event Delivery 在 pop该 entry前必须让 subscription durable cursor追到这个 fence；Run B 的 start fact必然位于释放 active slot的 A terminal之后，因此不依赖跨进程 notice也能阻止 B delta越过 A terminal。该字段是 Host-internal typed input，不进入 Engine / Service public contract。
  3. 保留或明确加入 bounded periodic durable reconciliation，使其它 opener提交的 terminal在没有本地 transient entry时仍能被长期 watcher发现；本地 terminal-ready wake只负责降低延迟，不能成为唯一 correctness signal。
  4. 增加双 opener集成 barrier：A、C 共享同一 DB；watcher attach在 C；A opener提交 terminal；B随后由 C admission / scheduler执行并发布首个 delta。精确断言 C watcher先交付 A terminal，B entry始终留在 C 的 counted mailbox，且只在 Service ack / clear / rebind后的下一次 `anext()` 交付。
  5. AST manifest继续用于证明“每个 terminal producer向其本地 coordinator发 notice”，但验收文字不得再声称它单独证明跨 opener delivery cutoff完整性。
- **修复风险（中）**：需要扩展 Host-internal candidate / mailbox entry 和跨 opener集成测试，但不需要修改 Engine public contract、durable schema、Service event buffer或 transient replay语义。
- **严重程度（高）**：违反已声明的多进程架构约束和核心 A/B ordering guarantee。

### 02-未修复-[高]-同步 eager attach 不能用 pending cursor future 构造所声明的 atomic cursor/watermark snapshot

- **位置**：`docs/host/design.md:386,394-399,524,1203-1205`；`dayu/host/open_host.py:908-929,939-1020`；`dayu/host/_durable_actor.py:106-125`；`dayu/host/read_api.py:450-465`。
- **问题类型**：状态机漏洞 / 并发恢复风险 / 不可直接实施 / public contract缺失 / 测试缺口。
- **当前写法**：`watch_session_events(session_id)` 保持同步返回 iterator，并声称返回前已经把“durable start-cursor request 的线性化位置”和当前 terminal watermark baseline原子记录；cursor future允许到首次 `anext()` 才解析。设计进一步声称任一 terminal不是位于 start cursor之前，就是位于之后并推进 watermark，因此不会漏消息。
- **反例/失败场景**：
  1. `watch_session_events()` 在 owner loop注册 subscription、向单 worker durable actor提交 cursor operation并立即返回；此时 cursor operation仍可能排队或未开始。
  2. public call已经返回后，scheduler connection、wait poller connection、另一 opener或另一进程提交 terminal A。
  3. actor随后执行 cursor transaction；当前实现的 operation读取**执行时** EventLog最大 sequence，因此返回值已经包含 A。
  4. subscription在返回时记录的 local watermark baseline却早于 A。A notice即使随后把 local latest watermark推进到 A sequence，merge看到 `cursor == watermark`，会把 A视为 start cursor之前，不再补读 A。
  5. watcher因此可能永久漏掉一个在 public attach返回后提交的 terminal；若 Service没有进入 delivery-specific degraded path，它不会按 exact-five contract自动改走 durable recovery。
- **为什么有问题**：executor排队顺序只把 cursor operation排在**同一 actor后续 command**之前，不能把“提交 future 的时刻”变成与 scheduler / poller /其它 SQLite writer可比较的 EventLog snapshot。当前 O(1) latest-terminal scalar又不足以在 cursor已经越过一个或多个 terminal后重建第一个漏掉的 cutoff。该问题不能靠实现细节或测试 fixture默认速度解决。
- **直接证据**：
  - `dayu/host/open_host.py:908-929` 先 `subscribe()`、调用 `DurableActor.submit(...)`，随后不等待 future便返回 `_ClosableHostSessionEventIterator`。
  - `dayu/host/_durable_actor.py:110-114` 对 `submit` 的精确承诺只是把 cursor attach排在“后续 submit command”之前；它没有与 scheduler store或其它进程的 writer建立顺序。
  - `dayu/host/read_api.py:456-465` 的 cursor operation在实际执行 transaction时读取当前 EventLog最大 sequence，没有预留调用时 sequence或跨 writer fence。
  - `docs/host/design.md:380` 同时确认 terminal producer来自 owner-loop外时是在 commit后才 marshal；因此 durable commit与 pending cursor read确实可并发。
  - future acceptance `docs/host/design.md:537` 有 cap attach、never-started cleanup与 A/B barriers，但没有“阻塞 cursor operation、watch已返回、terminal commit、再释放 cursor”的 deterministic barrier；现有测试清单无法裁决该原子性声明。
- **影响**：public live watch可漏掉 attach返回后的 terminal；attach-before-submit只对同一 actor后续 command成立，不能支持设计声称的 active Run、startup reconnect、多连接或多进程观察语义。实现 agent必须自行发明跨 writer线性化机制，因而 plan不是 code-generation-ready。
- **建议改法和验证点**：
  1. 采用更简单的 async factory：`await host.watch_session_events(session_id) -> HostSessionEventIterator`。先在 owner loop做 reservation，await durable actor取得实际 start cursor，回到 owner loop完成 mailbox / fanout attach与 watermark snapshot，再返回 iterator；失败路径释放 reservation。这样 terminal若在 cursor snapshot前提交，发生在 public attach返回前，可按明确 baseline处理；若在 snapshot后提交，后续 durable read必然从较早 cursor发现它。
  2. 若必须保留同步 factory，则设计必须给出一个与**所有** EventLog writer共享的具体线性化 primitive；“future已提交”或“owner-loop无 await”不是这种 primitive。不得用 latest-row补读、Service fallback、terminal id set或未说明的锁掩盖该缺口。
  3. 新增 deterministic attach barrier tests：至少覆盖 cursor operation被阻塞时的 terminal commit，以及 cursor snapshot完成后、fanout attach / return前的 terminal commit；分别断言没有 post-return terminal被基线吞掉、reservation / cursor / subscription cleanup精确一次。
  4. 更新 public contract、Service调用点和静态类型断言，使“何时 attach生效、何时可能排除既有 terminal”有唯一、可测试的线性化定义。
- **修复风险（中）**：async factory会机械影响 Host Protocol和Service调用点，但当前任务本就修改这些边界；相较引入跨线程锁、同步阻塞 SQLite或第二事件通道，它是更简单且可维护的方案。
- **严重程度（高）**：会造成 online terminal丢失，并使核心 eager-attach contract无法按当前架构实施和验收。

## Architecture / best-practice / optimality / overengineering review

- **Architecture boundary**：Engine边界正确；capacity、overflow、terminal merge和Service observation均放在合理 owner。material问题集中在 Host内部把 durable跨进程事实与 opener-local控制信号绑定成单一 correctness链路。
- **Best practice**：bounded mailbox、non-await offer、typed disconnect、同事务 exact terminal sequence、closed result union和确定性 race tests均符合当前问题的工程最佳实践。缺失的是跨 actor / 跨 process 的 causality proof以及真正可执行的 attach linearization。
- **Optimal solution**：不需要把 transient delta写入 EventLog、不需要 message broker、第三 sequence domain、global quota、terminal marker集合或Service fallback。Host-internal causal durable fence + bounded durable polling，以及 async attach factory，是比跨进程广播 ephemeral notice更简单、可测试且同样保持 live-only语义的方案。
- **Overengineering**：items / bytes / subscription三维 policy、一个 mailbox +一个 in-flight、五成员 Service result都由真实 failure mode支撑，不构成 material overengineering。反而继续为同步 eager attach发明锁 / bridge / readback会增加错误耦合，应优先收窄为 async attach。
- **Overcoupling**：当前 `TerminalPostCommitPort` 同时承担本地 delivery wake与queue promotion协调本身可接受；错误在于把它进一步耦合为所有 runtime watcher的唯一 durable cutoff来源。修复后应保留本地调度职责，将跨 opener correctness绑定到同源 durable causal fence。

## Non-findings / closure retained

以下审查点没有 material finding：

- `HostSessionEventIterator` public closable Protocol提升方向正确；不需要Service私有 cast / `hasattr` fallback。
- 慢 consumer只导致其 subscription overflow / detach，publisher不 await consumer或capacity；同 event loop的同步阻塞不被夸大为物理隔离。
- durable rows不复制进 transient mailbox，Service也不保留任意 `HostSessionEvent` relay；容量一 observation result不是第二事件队列。
- mailbox + in-flight统一 retained items / bytes accounting、单 event oversized优先、item-count其次、cumulative bytes最后的算法可裁决。
- per-Session reservation先于 mailbox / cursor / task allocation、overflow prefix清空前仍占 reservation、全部幂等释放路径的设计足够明确。
- transaction-local exact Run terminal sequence、三字段 notice、`false -> true`补发、较新 `false`不吞较旧 `true`、batch不按 Session去重等单 opener规则自洽。
- 当前 terminal producer文件闭集与代码事实相符；material缺口不是漏列第六个 producer文件，而是 notice的接收域不足。
- exact-five Service disposition、fatal sticky、generation ack / clear / rebind、stop / cancellation first arbitration和double-failure cleanup precedence可直接实施。
- packaged items / bytes / max-subscriptions数值、logical-byte到heap margin及低基数metrics字段是同一 WU acceptance measurement，**不是 residual，也不是本次 finding**。

## Open questions

无。两个 material问题都已有可复现时序、明确 owner冲突与可执行修复方向，不应降级为 implementation-time audit或 measurement。

## Residual risks and tracking

- 未归属 residual：**0**。
- items / bytes / subscriptions packaged值、heap safety margin、低基数metrics继续按同一 implementation WU acceptance测量，不另建 residual。
- Findings 01、02必须在设计 owner层修订并由新的双 opener / delayed cursor barriers关闭；在关闭前不应授权 implementation。

## Final plan review conclusion

**FAIL**。

当前设计在单 opener内已经接近闭环，但尚不是当前约束下的最佳且正确设计。2 个高严重度 material findings分别证明：

1. opener-local `TerminalPostCommitPort` 无法覆盖多 opener / 多进程 watcher的 terminal cutoff；
2. 同步返回且 cursor future尚未执行时，所谓 atomic eager-attach snapshot没有跨 writer线性化点。

因此，现有实施文件与测试矩阵不足以裁决生产级 Session Event Delivery 正确性；必须先在 Host设计真源收敛跨 opener causal fence和可执行 attach linearization，再进入 implementation。
