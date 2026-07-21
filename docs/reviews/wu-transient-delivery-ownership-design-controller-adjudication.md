# Session Event Delivery 设计 Review Controller Adjudication

## 元数据

- 日期：2026-07-21。
- 来源 WU：`WU-CLI-SMOKE-01-R1` post-closeout design correction。
- 设计真源：`docs/host/design.md`；Engine边界交叉核对：`docs/engine/design.md`。
- Controller最终决策：`accepted-design-and-confirmed-next-WU`。
- 下一实施 WU：`WU-HOST-SESSION-EVENT-DELIVERY-01`，仅在 Draft PR #180 由用户 / maintainer 手工 merge、从 `main` 同步并创建独立分支后进入 plan gate。
- 最终状态：material findings=`0`；design residual=`0`；未归属 residual=`0`；open question=`0`。

## 第一性原理裁决

原“分别调优 Host queue 与 Service relay queue”的路径不是最佳设计。三类 delta 是 live-only 数据，但这不等于可以无界保留；真正需要的是一个由数据交付 owner 管理的、有界且可配置的 mailbox。Service relay复制同一事件并制造第二套容量、失败与cleanup真源，应删除，而不是单独调参。

正确 owner 分工冻结为：

- Engine只拥有单次 generator 内事件产生顺序；不拥有 Host watcher、capacity、cursor或replay。
- EngineEvent ingest拥有durable identity / late-state validation，并向Session Event Delivery做同步、non-blocking、non-throwing typed handoff；慢consumer不能把capacity等待反压到Agent / Engine。
- Host Session Event Delivery拥有每订阅唯一mailbox、唯一in-flight retained accounting、items / bytes、per-Session admission、overflow、detach、durable/transient merge和可关闭iterator。
- Service只拥有sole `anext()` consumer、业务callback与容量一的observation-result slot；不得复制或预读Host event。
- UI是否丢弃、降级或展示由UI/Service决定，但无权暂停Agent执行。

因此，原 `WU-HOST-TRANSIENT-CAPACITY-01` 与 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 的拆分会固化错误边界；两者必须由单一 `WU-HOST-SESSION-EVENT-DELIVERY-01` 取代。

## Review / fix 闭环

### 首轮设计 review

首轮 artifacts：

- `docs/reviews/plan-review-20260721-141110.md`（AgentDS，pass-with-risks）；
- `docs/reviews/plan-review-20260721-141359.md`（AgentMiMo，pass-with-risks）；
- `docs/reviews/plan-review-20260721-142109.md`（AgentCodex，FAIL，5 material findings）。

Controller接受并要求当前design gate关闭：Service消费/cleanup状态机不闭合；no-backpressure承诺过宽；overflow错误owner错误；设计与总控冲突；policy/aggregate/fence/byte边界不明确。AgentCodex据此补齐public closable iterator、Service sole consumer与terminal slot、delivery-specific typed error、runtime policy owner、O(1) fence方向和aggregate watcher前提。

### 第二轮 re-review

Artifacts：

- `docs/reviews/wu-transient-delivery-ownership-design-rereview-codex.md`（FAIL，4 material findings）；
- `docs/reviews/wu-transient-delivery-ownership-design-rereview-mimo.md`（PASS）；
- `docs/reviews/wu-transient-delivery-ownership-design-rereview-ds.md`（PASS）。

Controller不按多数票放行，接受Codex指出的四项缺口：callback / EOF / multi-target generation结果不精确；Host batch drain形成第二个未计量保留区；multi-watcher无admission contract；item与byte同时overflow时primary dimension冲突。修订冻结exact observation result方向、single pop + counted in-flight、`max_subscriptions_per_session`先reserve后allocation，以及oversized bytes → item count → cumulative bytes的固定判断顺序。

### 第三轮 final re-review

Artifacts：

- `docs/reviews/wu-transient-delivery-ownership-design-final-rereview-codex.md`（FAIL，2 material findings）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-rereview-mimo.md`（PASS）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-rereview-ds.md`（PASS）。

Controller接受两项：Host merge可能先交付后继Run B transient再看到前序Run A terminal；exact-five caller disposition与`aclose()` double-failure precedence仍有歧义。修订加入per-Session terminal cutoff、A-prefix / terminal / B-retention fence，并把Service observation冻结为恰好五类结果、唯一caller disposition、first-commit和cleanup precedence。

### 第四轮 closure re-review

Artifacts：

- `docs/reviews/wu-transient-delivery-ownership-design-closure-rereview-codex.md`（FAIL，1 high finding）；
- `docs/reviews/wu-transient-delivery-ownership-design-closure-rereview-mimo.md`（PASS）；
- `docs/reviews/wu-transient-delivery-ownership-design-closure-rereview-ds.md`（PASS）。

Controller接受Codex finding：terminal watermark设计只覆盖Engine ingest / dispatch，遗漏admission、waiting、recovery、watchdog、lost和未来terminal writers。修订冻结三字段 `TerminalPostCommitNotice`、单一 `TerminalPostCommitPort`、same-transaction exact terminal sequence、全部当前producer闭集、static qualified-callsite manifest与non-Engine barriers。

### 第五轮 final closure review

Artifacts：

- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-codex.md`（FAIL，2 high findings）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-mimo.md`（PASS）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-ds.md`（PASS）。

Controller再次不按多数票放行，接受两个由代码证明的反例：

1. 每次 `open_host` 都创建独立in-memory hub / coordinator；opener-local terminal notice无法成为其它opener / 进程watcher的全局correctness source。
2. 同步factory只排队cursor future便返回；future提交时刻不是与其它SQLite writer共享的线性化点，可吞掉public return后才提交的terminal。

对应修订：

- 每个validated transient candidate / mailbox entry携带Host-internal `durable_causal_fence_event_sequence`，唯一来自同一ingest validation transaction确认的当前 `Attempt.started_event_sequence`。Session单active invariant与EventLog单调sequence证明前序Run A terminal早于后继Run B Attempt start；iterator在pop B前必须把durable cursor追到该fence。mailbox为空时仍periodic reconcile，因此跨opener correctness不依赖ephemeral notice。
- `TerminalPostCommitPort` 收窄为producer所属opener的本地低延迟wake与optional promotion coordinator；AST manifest只证明本地接线。
- public watch改为async factory：reserve → await真实cursor transaction → owner-loop无awaitattach → successful return。pending cursor future、同步factory与lazy attach全部删除。

Fix artifact：`docs/reviews/wu-transient-delivery-ownership-design-final-closure-fix-codex.md`。

### 最终三路独立 re-review

- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-rereview-codex.md`：PASS，0 material findings。
- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-rereview-mimo.md`：PASS，0 material findings。
- `docs/reviews/wu-transient-delivery-ownership-design-final-closure-rereview-ds.md`：PASS，0 material findings。

三路均直接核对schema、single-active index、Attempt start sequence、ingest validation、durable actor、read path、terminal producers与Service现状；共同确认design residual=`0`、未归属 residual=`0`、open question=`0`。

## 新 WU 边界裁决

`WU-HOST-SESSION-EVENT-DELIVERY-01` 是一个跨 Host / Service 接口但语义单一的owner correction，不应按文件或层机械拆分。其最小闭环包括：

- async public watch factory与public closable iterator；
- 每订阅唯一Host mailbox + counted in-flight；
- items / bytes / per-Session subscriptions三字段runtime policy、typed admission / overflow；
- `delivery_size_bytes` single source；
- durable causal entry fence、bounded-page catch-up、periodic reconciliation与双openerbarrier；
- 全terminal producer的transaction-local exact notice与本地coordinator；
- 删除Service event-copy relay并实现exact-five observation / cleanup；
- config / assembly、CLI await调用、README、owner / integration / static tests。

packaged capacity值、logical-byte到resident-heap safety margin、低基数metrics、AST fail-closed维护、oversized行为和Service/UI callback非阻塞均可在该WU实施或测量，已纳入acceptance，不得标记为residual。

明确非目标：delta durable replay、跨域总序、第三sequence domain、跨进程terminal广播、Host-global跨Session quota、慢UI暂停Agent/Engine、R2 thinking UI。当前需求与威胁模型没有Host-global quota owner；若未来出现独立全局SLO，需重新进入design gate，而不是保留模糊residual。

## Final decision

- Design：accepted。
- 最佳设计判断：在当前产品约束、单机多进程架构与最小化原则下成立。
- 旧capacity WUs：superseded并从active residual表删除。
- 下一WU：`WU-HOST-SESSION-EVENT-DELIVERY-01`。
- Entry：仅在PR #180手工merge并从`main`同步后进入plan gate。
- 当前分支：只提交设计、review与control文档；不实施代码。
