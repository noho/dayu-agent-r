# WU-CLI-SMOKE-01-R1 Session Event Delivery 最终独立 Closure Re-review（Codex）

## Review metadata

- 生成时间：`2026-07-21 17:20:30 +0800`（本机系统时钟；timestamp：`20260721-172030`）。
- Review 类型：最终独立、从第一性原理出发的 adversarial closure re-review。
- 结论：**PASS**。
- Material findings：**0**。
- Design residual：**0**。
- 未归属 residual：**0**。
- Open question：**0**。
- 本 review 只新增当前 artifact；未修改设计、代码、测试、总控或 README，未提交。

## Reviewed target and scope

本次读取并交叉核对：

- `docs/host/design.md`；
- `docs/engine/design.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-codex.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-fix-codex.md`；
- 设计列入 implementation WU 的现有 Host / Service / CLI 生产代码、public contracts、durable schema、EventLog / Run / Attempt transition、watch merge 与相关测试边界。

未读取 AgentMiMo / AgentDS 本轮 artifact，也未把其它 reviewer 的本轮结论作为证据。

本 review 只报告会导致设计不正确或 implementation 不可裁决的 material finding；capacity packaged values、Python heap margin、metrics 与 callback execution-domain 证据均按用户裁决保留为同一 WU acceptance，不降级为 residual。

## First-principles motivation decision

修复动机成立且严重性评估正确。旧设计的两个根因分别是：把 opener-local ephemeral notice 误当成跨 opener durable correctness source，以及把“cursor operation 已排队”误当成“cursor transaction 已执行”。最新设计没有在下游增加 fallback，而是在语义 owner 处完成两项收敛：

1. 跨 opener correctness 由 EventLog 与同源 `Attempt.started_event_sequence` causal fence 拥有；`TerminalPostCommitPort` 只保留 producer opener 本地低延迟 wake / optional promotion coordination。
2. public watch 改为 async factory，以实际 cursor transaction 完成、owner-loop 无 `await` attach 和 successful return 定义唯一生效边界。

这两项修复直接处理 owner 冲突，没有引入 durable transient replay、跨进程 ephemeral bus、第三 sequence domain、Service fallback 或第二事件 buffer。

## Assumptions tested and direct evidence

### 1. Causal fence 的唯一来源与 A terminal → B Attempt start 严格顺序

**裁决：成立。**

- `docs/host/design.md:358,388-392` 把 candidate fence 唯一归属给 Host EngineEvent ingest 的同一 durable validation transaction：从已读取并确认的 current `Attempt.started_event_sequence` 取得非 bool 正整数；publisher 只原样复制到每个 subscription entry，禁止 transaction 后 readback、猜测、per-subscription 重算或 public payload 泄漏。
- 当前 `_IngestValidatedOperation` 在单笔 write transaction 中完成 identity、duplicate、late-state validation 与 transient candidate 构造；`dayu/host/engine_ingest.py:683-725,1030-1042,1144-1177` 已直接持有并确认 current Run、Attempt 与 dispatch record。`dayu/host/engine_ingest.py:5227-5273` 是增加该内部 typed 字段的现成 owner seam，不需要 Engine 或 Service 提供第二真源。
- `dayu/host/durable/schema.py:659-687` 规定 Attempt 的 `started_event_sequence` 非空并引用 EventLog；`dayu/host/durable/schema.py:418-420` 规定 EventLog sequence 为 `INTEGER PRIMARY KEY AUTOINCREMENT`。
- 单 active / start-blocking invariant 不是只靠文档假设：`dayu/host/durable/schema.py:1257-1263` 用 partial unique index结构性约束每个 Session 至多一个 accepted / running / waiting / cancelling / recovering Run；`dayu/host/durable/state.py:74-88` 从 public terminal status闭集派生 start-blocking集合；queued promotion与 accepted/queued start CAS又在 `dayu/host/durable/state.py:3465-3514,3542-3597` 显式拒绝同 Session 其它 start-blocking Run。
- 后继 Run 的 Attempt start fact与 Run 激活属于同一 write transaction。initial start见 `dayu/host/durable/run_transition.py:1094-1149`；governed start见 `dayu/host/durable/run_transition.py:1174-1225`；queued promotion先确认无 active Run，再成功 CAS，随后追加 Attempt start并插入 Attempt，见 `dayu/host/durable/run_transition.py:1686-1742`。SQLite writer serialization、EventLog单调 sequence、active row释放与 terminal row同事务提交共同保证：若 B Attempt 创建成功，则前序 A 已提交 terminal并离开 start-blocking集合，因此 `A.terminal_event_sequence < B.attempt.started_event_sequence`。
- 该证明也覆盖 initial direct-start：若 A 尚未 terminal，B 的 running row会命中 partial unique index并使整笔 transaction回滚，先前追加的 B start rows不会提交；只有 A terminal transaction先提交时，B committed Attempt start sequence才可能成立。

没有发现能够绕过上述 transition / index建立 Session-visible后继 Attempt 的生产 writer。现有 terminal helper调用点仍闭合在 admission、waiting、recovery、engine ingest 与 dispatch五个 owner面；最新设计要求 AST qualified-callsite manifest、runtime dataflow和 owner tests共同守住该闭集。

### 2. 跨 opener、无本地 notice、多页 catch-up 与空 mailbox progress

**裁决：成立且可裁决。**

- `docs/host/design.md:380-394` 明确本地 notice不跨 opener，B entry fence才是共享 DB correctness input。pop前若 cursor落后 fence，entry必须原位保留并继续计入 mailbox / in-flight budget，按 bounded EventLog pages追到 fence；遇 A terminal时只交付 mailbox头部 A prefix，首个 B entry保留，yield A后暂停到下一次 `anext()`。
- `docs/host/design.md:392` 独立规定 mailbox为空时仍进行 bounded periodic durable reconciliation；因此长期 watcher即使没有本地 notice、也没有 transient entry，仍会最终发现其它 opener提交的 terminal。
- 当前 EventLog read path支持该实现：`dayu/host/read_api.py:469-498` 以全局 cursor有界扫描并返回 batch / next cursor。实现可以在遇 terminal时只把 subscription cursor推进到实际处理的 terminal sequence，下一次读取重扫其后的未交付区间；无需修改 schema或制造 terminal marker set。
- `docs/host/design.md:543,555` 冻结了独立 deterministic acceptance：双 opener共享 DB、watcher与 B在 opener C、A terminal由 opener A提交且 C无本地 notice、强制多页 catch-up、A先交付且 B entry持续计费；另有 mailbox为空的 periodic reconcile测试。它同时禁止把本地 AST manifest冒充跨 opener完备性证明。

固定正整数 fence使 catch-up目标有限；page size只限制单页而不是 correctness截止。即使其它 Session持续写入，cursor仍单调前进到已经存在的 B Attempt start fence，不存在由新写入造成的移动终点。

### 3. `TerminalPostCommitPort` 收窄与本地 producer闭环

**裁决：成立。**

- `docs/host/design.md:366-384` 将 exact terminal sequence归属给产生或幂等确认 terminal 的同一 transaction result；禁止 post-commit latest/max readback与按 Session去重 batch notice。
- `docs/host/design.md:380-384` 把 `TerminalPostCommitPort` 精确收窄为 producer所属 opener 的本地 terminal-ready wake / optional queue-promotion coordinator，并明确它不是其它 opener / 进程 watcher 的 correctness source。
- coordinator仍保持必要的本地闭环：watermark max-advance与level-trigger wake先于 optional promotion；delivery scalar与 promotion scalar均为 O(1)；同 sequence duplicate幂等；先 `false` 后同 sequence `true`仍补发；较新 `false`不吞较旧未处理 `true`；较新 `true`先处理时其 queue reconciliation覆盖较旧 release。
- `docs/host/design.md:530-541,543-555` 覆盖新 internal contract文件、composition root、admission / waiting / recovery / engine ingest / dispatch / command的所有当前 terminal producer，且把 ordinary session-id promotion port与 terminal port分离。AST manifest只证明本地接线，runtime fake证明transaction-result数据流，三组 non-Engine barrier证明本地 promotion无 bypass；双 opener barrier另证全局 correctness。证据职责没有混淆。

没有发现需要跨进程广播该 port的理由；这样扩张反而会制造另一条有丢失与恢复语义的 ephemeral correctness链路。

### 4. Async factory 生效边界、取消 / 失败 / Host close 与同 actor ordering

**裁决：成立且可实施。**

- `docs/host/design.md:386,398-400,1211` 冻结唯一顺序：public lifecycle gate → owner-loop reservation → await实际 Session existence / start-cursor transaction → 回 owner loop无 `await` attach / watermark baseline → successful return。首次 `anext()`不得再做 cursor、attach或allocation。
- current `DurableActor.call` 会 await同一 single-worker executor中实际 operation完成，且 operation按提交顺序执行，见 `dayu/host/_durable_actor.py:88-125`；current cursor transaction在执行时同时检查 Session并读取最新 EventLog sequence，见 `dayu/host/read_api.py:450-465`。因此改为 async factory不需要跨 writer锁或新 actor primitive。
- cursor snapshot到return之间的 durable commit由较早cursor覆盖；该窗口的 transient明确是 pre-return live-only、不承诺重放。owner-loop无 `await` attach使本 opener publisher不能穿过attach与return；successful return后的本地 transient不会因尚未attach而丢失。
- caller在successful return后提交的同 actor command必然排在已完成cursor transaction之后；这项保证不错误扩张为其它连接 writer的全局锁。其它连接在gap内提交的durable rows由较早cursor读取。
- cursor / Session missing / durable read error、factory cancellation、attach / iterator allocation失败和attach期间Host close由factory owner精确一次释放 reservation / partial resources；successful return后由iterator/subscription owner处理 never-started `aclose()`、consumer cancellation、EOF/error、overflow detach与Host close。`docs/host/design.md:400,517,543` 已要求不存在pending cursor future、done-callback补偿或unhandled-future cleanup，并为 delayed cursor、gap commit、post-return transient、cancellation、allocation failure与Host close逐项冻结 deterministic barriers。

当前同步 factory与pending future只是待替换的现状证据，见 `dayu/host/open_host.py:905-1020`；它不再作为未来 contract残留。async factory是比共享锁、latest-row补偿或同步 wrapper更简单的线性化方案。

### 5. 旧 closure、实施边界与测试裁决力

**裁决：全部保持。**

- 统一 public `HostSessionEventIterator`继续是可幂等 `aclose()` 的精确 async iterator contract；Host Protocol、implementation、package exports与Service / CLI调用点必须共同改为显式 `await`，不保留 cast、`hasattr/getattr`或兼容 wrapper。
- 每个 subscription仍只有一个 Host transient mailbox与一个持续计费的 in-flight；durable rows不复制入 mailbox；Service删除 event-copy relay，只保留 sole `anext()` consumer与容量一、generation-tagged exact-five observation slot。
- items、logical UTF-8 bytes、per-Session subscriptions三维容量、mailbox + in-flight retained accounting、oversized → item count → cumulative bytes的固定 public primary order、typed overflow / admission error、overflow prefix占 reservation到最终detach等契约没有被 causal fence或async attach改写。
- exact-five disposition、terminal-only ack / clear / rebind、fatal sticky、stop / cancellation first arbitration、cleanup precedence和七组 double-failure tests仍被 `docs/host/design.md:443-521,543` 完整冻结。
- implementation文件覆盖 public types、Host delivery、terminal transaction results与五个producer owner、composition root、runtime config、Service / CLI consumers和所有真实/fake调用点。现有 Attempt / EventLog / active Run schema已经提供所需 durable fact与约束，因此不需要 schema迁移；fence是引用现有 sequence的Host-internal typed metadata。
- delayed-cursor、candidate fence source、publisher原样复制、双 opener无 notice、多页 catch-up、空 mailbox reconciliation、local producer barriers、AST callsite closure、multi-watcher reservation、exact-four overflow fixtures、exact-five与cleanup tests形成互补证据，不依赖单个大集成测试证明全部语义。

## Architecture / best-practice / optimality / overengineering / overcoupling review

- **Architecture boundary**：Engine仍只拥有单 generator事件顺序；durable identity、fence、terminal truth、fanout与merge都在 Host；Service / UI只拥有展示与观察状态。依赖方向符合 `UI -> Service -> Host -> Engine`，没有把 delivery policy或cursor反向泄漏给 Engine。
- **Best practice**：同事务取得 causal input、bounded mailbox、typed disconnect、async resource factory、显式close、closed result union、确定性并发barrier与静态producer manifest均与本项目 owner-first约束一致。
- **Optimal solution**：Host-internal Attempt-start fence + EventLog bounded catch-up + empty-mailbox periodic reconcile + async attach，是现有 durable truth与runtime seam上的最小正确方案。把transient写入EventLog、增加消息系统、跨进程broadcast correctness port、terminal marker集合、Service B cache或全局锁都更复杂且扩大语义承诺。
- **Overengineering**：三维容量、exact-five、双scalar本地coordinator和causal fence各自对应已证实的内存、竞态、重复promotion或跨 opener顺序风险；没有无当前需求支撑的抽象。
- **Overcoupling**：最新设计已拆开 durable correctness、本地延迟优化、queue promotion、subscription retention与Service observation；测试也按 owner分层。未发现必须同步演进的错误双向依赖或第二事实源。

## Material findings

**无。Material finding 数量：0。**

两个 final-closure findings均已在正确 owner边界关闭：

1. opener-local terminal port不再承担跨 opener correctness；
2. public attach不再依赖pending cursor future，而以async factory successful return线性化。

## Open questions

**0。**

## Residual risks and tracking

- `design residual = 0`。
- 未归属 residual：`0`。
- capacity packaged values、heap safety margin、低基数metrics与callback快速同步非阻塞证明继续作为同一 implementation WU acceptance；不是 residual、future audit或自由裁量项。

## Final plan review conclusion

**PASS**。

Material findings：**0**；design residual：**0**；未归属 residual：**0**；open question：**0**。

最新 Session Event Delivery design fix 已同时关闭跨 opener causal ordering与async attach linearization，且保留此前 single Host mailbox + counted in-flight、无Service relay、三维容量、overflow order、exact-five、cleanup和local terminal producer闭环。现有实现 seam、durable schema、类型变更范围与确定性测试矩阵足以让implementation按owner边界实施并由直接证据裁决；未发现更简单且同样满足全部当前acceptance的正确替代方案。
