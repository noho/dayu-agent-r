# WU-CLI-SMOKE-01-R1 Session Event Delivery 最终 Closure Design Fix（Codex）

## Gate metadata

- 生成时间：`2026-07-21 17:10:49 +0800`。
- Gate：phaseflow post-final-closure `design-fix`。
- Work unit：`WU-CLI-SMOKE-01-R1` transient delivery ownership。
- Controller decision：基于代码直接证据接受 `docs/reviews/wu-transient-delivery-ownership-design-final-closure-codex.md` 的两个高严重度 findings；本gate不得降级，也不得转记为residual。
- Gate outcome：两个findings均已在设计owner层关闭，状态为`completed-ready-for-independent-three-way-re-review`。
- 修改边界：只修改`docs/host/design.md`、`docs/reviews/wu-transient-delivery-ownership-design-codex.md`，并新增本artifact。
- 禁止范围：代码、测试、总控、README、其它既有review artifacts、commit、push、PR与implementation。

## First-principles decision

两个finding的动机成立，严重度均正确，不存在应降级的证据。

第一项的根因不是某个terminal producer漏调本地port，而是semantic owner错配：EventLog terminal与Attempt start是跨opener共享的durable truth，`TerminalPostCommitPort`却是producer所属opener的ephemeral control seam。当前`open_host`为每个opener创建独立hub / runtime，证明本地notice无法成为其它opener watcher的唯一correctness input；AST即使穷尽本地producer callsites，也不能证明跨opener送达。

第二项的根因不是cursor读取算法，而是同步factory把“cursor operation已提交”误当成“cursor transaction已执行”。当前`DurableActor.submit`只约束同一actor后续command的排队顺序，实际start cursor由read transaction执行时读取；因此pending future与public return之间不存在跨writer线性化点。继续保留同步factory只能引入共享锁、latest readback或下游补偿，都会增加第二真源或错误耦合；async factory是最小、可测试且符合owner边界的方案。

## Finding 01 closure：跨 opener correctness

### Owner and source of truth

`TerminalPostCommitPort`明确降为producer所属opener的本地terminal-ready低延迟wake与optional queue promotion coordinator。它继续承载全部terminal producer的typed post-commit notice、本地watermark先于optional promotion、本地duplicate / `false -> true`规则与本地A terminal → B delta barrier，但不再声称是所有opener watcher的唯一correctness source。

跨opener因果性的唯一真源冻结为Host-internal正整数`durable_causal_fence_event_sequence`：

- Engine ingest对每个transient candidate执行durable identity / late-state validation时，在同一validation transaction中从已经读取并确认的当前`Attempt`取得`started_event_sequence`。
- 该值必须是非bool正整数；禁止transaction后latest/max readback、猜测、从`run_id` / 时间戳 / publication order反推、public payload、extra payload或第三sequence domain。
- publisher把candidate上的同一个fence原样复制到每个目标subscription mailbox entry；禁止per-subscription重算。
- fence是固定大小的Host-internal accounting metadata，纳入entry固定开销边界，但不进入logical UTF-8 byte traversal，不加入public `HostTransientDelta`，也不进入日志或LLM-facing material。

### Merge and progress contract

每次准备pop transient entry前，若subscription durable cursor小于entry的`durable_causal_fence_event_sequence`，iterator必须按bounded pages读取EventLog，直到cursor大于等于该fence。catch-up期间沿用既有terminal fence：先交付durable terminal，并把原entry保留在同一个counted mailbox / in-flight accounting中；terminal完成Service ack / clear / rebind后，下一次`anext()`才可交付后继generation的entry。

admission的单active Run不变量保证：前序Run A释放active slot的terminal EventLog sequence严格小于后继Run B当前Attempt的`started_event_sequence`。因此即使A terminal producer、watcher与B publisher分属不同opener或进程，B entry的fence仍迫使watcher先追过A terminal，不能先交付B。

mailbox为空时仍保留bounded periodic durable reconciliation，使没有本地notice的长期watcher最终发现其它opener提交的terminal。本地notice只降低本opener延迟并约束本地promotion，不替代durable causal fence或periodic progress path。

### Frozen acceptance

未来同一implementation WU必须增加：

- 双opener共享同一DB的deterministic barrier：watcher与B在opener C，A terminal由opener A提交，C明确收不到本地notice；B entry携带same-validation-transaction取得的Attempt start fence，C必须通过多页catch-up先交付A terminal并保留B entry。
- mailbox为空且无本地notice时，bounded periodic reconciliation最终发现跨opener terminal。
- candidate fence来源、publisher逐subscription原样复制、非bool / 非正整数拒绝、fixed-size accounting metadata与public delta不含fence的owner tests。
- `tests/host/test_terminal_post_commit.py`的AST manifest只证明所有terminal producer向其所属opener的本地coordinator接线；验收文本不得再用它宣称跨opener完备。
- 既有pre-dispatch cancel、wait failed、wait expiry三组本地A→B barrier、typed notice producer闭集、duplicate、terminal-no-promotion与ordinary-promotion tests不得弱化。

## Finding 02 closure：真正可执行的 attach

### Public contract and state machine

public contract冻结为async factory：

```text
await host.watch_session_events(session_id) -> HostSessionEventIterator
```

`HostSessionEventIterator`仍是统一、public、可幂等`aclose()`的`AsyncIterator[HostSessionEvent]`。factory必须严格执行：

1. 在opener owner loop先reserve目标Session的subscription slot；cap+1在mailbox、cursor transaction与iterator task allocation前fail closed。
2. await `DurableActor`实际完成Session existence与start cursor read transaction，而不是只保存future。
3. 回到owner loop后，在同一无`await`段创建并注册mailbox subscription、记录本地terminal watermark baseline，然后return iterator。

successful await return是调用方唯一可依赖的订阅生效边界。调用方在return后提交给同一actor的command必定位于已完成cursor transaction之后。cursor snapshot到return之间由任意连接提交的durable rows可由较早cursor读到；该间隙内的transient是pre-return live-only数据，不承诺重放。successful return之后由本opener publisher发布的transient不得因attach尚未完成而丢失，因为attach已在return前完成。

删除pending cursor future、同步factory、首次`anext()` cursor解析、lazy attach、attach-before-return / eager atomic snapshot旧说法及对应done-callback补偿。不得用同步wrapper、兼容alias或Service fallback保留旧contract。

### Failure and cleanup contract

cursor / Session existence失败、factory cancellation、attach / iterator allocation失败以及attach期间Host close，都必须由factory owner精确一次释放reservation和已经创建的partial resources。successful return之后的`aclose()`、consumer cancellation、iterator error / EOF、overflow detach与Host close继续由iterator / subscription owner精确一次释放；never-started iterator也不得存在pending cursor future或unhandled-future路径。

### Frozen acceptance

未来同一implementation WU必须同时更新：

- `Host` Protocol、public implementation、`dayu.host.api`与package exports的async factory签名和精确返回类型。
- Service所有watch调用点的显式`await`，并继续使用sole `anext()` consumer，不恢复event-copy relay。
- CLI watch / callback adapters与所有真实、fake调用点的显式`await`。
- public类型测试，证明Protocol是async factory且Service / CLI真实调用点没有同步调用或兼容wrapper。
- deterministic delayed-cursor barriers：cursor transaction被阻塞时factory不得return；cursor snapshot完成到successful return之间的durable commit必须可读；successful return后的同actor command位于cursor之后；post-return transient不因attach未完成丢失。
- cursor error、Session missing、factory cancellation、attach / allocation failure与Host close的reservation / resource精确一次释放tests。

## Earlier closure retained

本次两项root-cause修订不重开或弱化此前closure：

| Contract | Frozen result |
|---|---|
| Delivery ownership | 每subscription只有一个Host mailbox与一个仍计费的in-flight；Service无event-copy relay。 |
| Backpressure | publisher offer同步、快速、非等待；慢consumer只使其subscription overflow / detach，不反压Engine。 |
| Capacity | `max_items`、`max_bytes`、`max_subscriptions_per_session`三维required正整数policy，runtime composer / operator显式装配，无fallback。 |
| Overflow | oversized event优先，其次item count，再次prospective cumulative bytes；public detail只有一个稳定primary dimension。 |
| Service result | sole consumer、capacity-one observation slot、exact-five disposition、generation ack / clear / rebind、stop / cancellation仲裁全部保留。 |
| Cleanup | primary outcome、public error、cause chain、best-effort sanitized diagnostic与iterator / renderer close precedence不变，资源精确一次释放。 |
| Terminal producers | 所有Session-visible terminal writer继续从同一write transaction result产生exact typed notice并接到producer所属opener的single local coordinator；禁止post-commit latest readback。 |
| Local A→B fence | local watermark / terminal-ready wake先于optional promotion；三组non-Engine barrier及Engine terminal barrier保持。 |
| Recovery | 只有delivery interruption进入既有durable recovery；不为正常live transient引入replay、Service B cache或第二buffer。 |

## Same implementation WU acceptance—not residual

以下项目必须与未来implementation一起完成和裁决，不得作为residual、后续audit或自由裁量项：

- 用代表性provider delta burst、CLI / Web consumer latency SLO、watcher topology与per-Session memory budget确定packaged `transient_mailbox_max_items`、`transient_mailbox_max_bytes`、`max_subscriptions_per_session`。
- 测量logical UTF-8 retained bytes相对Python resident heap的安全margin，并证明mailbox + in-flight固定开销和causal fence metadata受界。
- 冻结production低基数metrics / sampling，至少区分item / byte overflow、buffer high-watermark与detach，禁止session / payload高基数或delta正文。
- 证明callback快速、同步、非阻塞；慢I/O、CPU与renderer由UI owner显式解耦，Service不新增relay，caller仍在`finally`关闭renderer。
- 保留items / bytes exact-four fixtures、multi-watcher admission / release、all-terminal-producer typed notice、local与cross-opener barriers、exact-five及double-failure cleanup tests。

## Validation

- stale scan：通过。同步factory、pending cursor future、eager / atomic attach、opener-local notice作为全局唯一correctness source、AST跨opener完备与latest/max readback只存在于当前错误证据或“删除 / 禁止”上下文；没有旧contract残留。
- frozen-decision scan：通过。三份目标文档均覆盖causal fence同事务来源、publisher原样复制、bounded multi-page catch-up、periodic reconciliation、双opener无本地notice、async successful-return边界、同actor顺序、delayed-cursor barriers及Host / Service / CLI await授权。
- whitespace：`git diff --check`及两份未跟踪目标artifact的`git diff --no-index --check`均无diagnostic。
- type check：`source .venv/bin/activate && pyright`通过，`0 errors, 0 warnings, 0 informations`。
- scope：仅三条允许路径被本gate写入；未修改代码、测试、总控、README或其它既有review artifacts，未提交。
- tests：未运行；本gate只有设计文档变更，未来行为测试已冻结为同一implementation WU acceptance。

## Residual and next gate

- `design residual = 0`。
- 未归属residual：`0`。
- open question：`0`。
- final-closure Finding 01：**已关闭，不能降级或转记residual**。
- final-closure Finding 02：**已关闭，不能降级或转记residual**。
- 下一步：必须由三个彼此独立的reviewer对本次design fix执行三路re-review；本artifact不自行宣告re-review通过，也不授权直接进入implementation。
