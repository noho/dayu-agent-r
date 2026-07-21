# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Final Design Re-review（Codex）

## Gate metadata

- 审查时间：2026-07-21 15:30:50 CST（+0800，来自本机系统时钟）。
- Gate：phaseflow 最终 design re-review gate。
- Reviewer：AgentCodex，使用 `planreview` adversarial review 方法。
- 审查结论：**FAIL**。
- Blocking findings：**2**。
- Material findings：**2**（高 2，中 0，低 0，严重 0）。
- 修改边界：只新增本 artifact；未修改设计、代码、总控、README、测试或既有 artifact。

## Reviewed target and scope

本次只读审查以下指定输入：

- `docs/host/design.md`；
- `docs/engine/design.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-rereview-codex.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-rereview-fix-codex.md`。

为验证设计是否可直接实施，另只读核对了当前 `dayu/host/open_host.py`、`dayu/host/transient_delta.py`、`dayu/host/engine_ingest.py`、`dayu/host/dispatch.py`、`dayu/service/entrypoint_runtime.py` 及相关 Host public tests。代码只用于证明设计假设、竞态和实施范围，不是本次 code review 的对象。按用户约束，总控旧行由 Controller 在本 gate 后修订；尚未写回总控本身不计为设计失败。

## First-principles assessment

修改动机成立，严重性没有被高估。当前生产事实仍是 Host transient queue、Host batch drain 与 Service relay queue 分别保留同一 live delivery 链上的事件；单 item cap 也不能约束没有跨 Runner public byte 上限的字符串 delta。把 transient publication、per-subscription retention、overflow 与 admission 收回 Host Session Event Delivery owner，删除 Service event-copy relay，并让 Service 只保留一个 observation-result slot，是当前约束下比调大两个 queue、把 delta durable 化或引入消息系统更小且更正确的方向。

本轮修订已经把 F02 的 batch/in-flight accounting、F03 的 per-Session admission，以及 F04 的 overflow primary dimension 写进正确 owner boundary；Engine 仍只拥有单次 generator 顺序，没有发生 owner drift。但 F01 尚未真实关闭：Service generation pause 依赖“先观察 A terminal，再停止读取”，Host durable/transient 合流却没有冻结能保证该前提的 terminal cutoff；此外 fatal result 虽有名称，caller-level disposition 与 cleanup failure precedence 仍允许实现者二选一。两处都会迫使 implementation agent重新设计并发或错误语义，因此不能进入 implementation gate。

## Assumptions tested

| 假设 | 结论 | 直接依据 |
| --- | --- | --- |
| Engine 应拥有 Session fanout、mailbox 或 terminal fence | 否；Host Session Event Delivery / iterator facade 是正确 owner | `docs/engine/design.md:28-38,450-513` 明确 Engine 只提供本次 generator 顺序，不提供 Host cursor、fanout、EventLog 或 replay。 |
| eager attach 已形成 attach-before-submit 的可实施边界 | 是 | `docs/host/design.md:364,446-448` 冻结 reservation、fanout attach、durable cursor request 先于返回，submit / cancel mutation 后发；当前 `dayu/host/open_host.py:905-929` 已证明同步 attach 形态存在。 |
| generation-tagged result 已阻止 A/B target 跨代消费 | 否 | `docs/host/design.md:442` 只规定 consumer 在看到 A terminal 后暂停，但 `:360` 没有定义跨 durable/transient 总序或 terminal publication cutoff；当前 merge 在 `dayu/host/open_host.py:985-986,1000-1020` 先交付 transient 再处理 durable terminal。见 F01。 |
| callback、EOF、iterator failure 和 cleanup 已有唯一 caller-level结果 | 否 | `docs/host/design.md:411-421` 把 union 写成“至少包括”，`:449` 又允许 `ITERATOR_ENDED` / `ITERATOR_FAILED` “fail closed 或走 recovery”；当前 public iterator `aclose()` 还可抛出 cleanup 异常。见 F02。 |
| F02 的 mailbox 外 batch retention 已关闭 | 是 | `docs/host/design.md:366,376,464,472` 明确删除所有 batch drain，只允许单项 transfer，mailbox + 唯一 in-flight 在 yield 恢复 / cleanup 前统一计量，并要求 deterministic refill barrier。 |
| F03 的 multi-watcher aggregate/admission 已关闭 | 是 | `docs/host/design.md:368,397,401-403,462-472` 冻结 required cap、owner-loop check+reserve、零分配拒绝、专属 `resource_exhausted`、幂等释放与 cap 乘积上界。packaged 数值仍是有 owner 的测量项，不重新打开 topology 或算法。 |
| F04 的 public primary dimension 已关闭 | 是 | `docs/host/design.md:378,382-395,472` 给出 single-event bytes -> item count -> cumulative bytes 的唯一顺序，并冻结四组 exact fixtures。 |
| 修订重新引入了第二个 event-retaining buffer | 否 | Host 只允许 transient mailbox + counted in-flight；Service slot 只能持有一个封闭 observation result，control primitive 不得保存 event 副本。当前新问题是跨 owner ordering cutoff 缺失，不是把 relay queue 合法化。 |
| 方案存在不必要的 Engine 扩张、Host-global quota或新消息系统 | 否 | `docs/host/design.md:403,460-478` 保持 Engine/durable contract 不变，明确排除跨 Session 总配额和独立消息系统；这是当前目标下的最小路径。 |

## CODEX-REREVIEW-F01..F04 closure matrix

| 原 finding | 最终复审结论 | Closure 证据 / 未关闭点 |
| --- | --- | --- |
| `CODEX-REREVIEW-F01` | **未真实关闭** | closed observation result、callback/EOF variant、generation ack/rebind、fatal sticky、eager attach 与 stop first-commit 文字均已补入；但 Host merge 仍未冻结 A terminal 对 transient publication 的 cutoff，B delta 可在 consumer 看到 A terminal 前被交付并丢弃；fatal/cleanup 的最终 caller outcome 也仍不唯一。见本轮 F01、F02。 |
| `CODEX-REREVIEW-F02` | **已关闭** | batch API 被明确删除；单项 mailbox -> in-flight transfer不扣账，yield 恢复 / cleanup 才释放，publisher 始终以 mailbox + in-flight 做 prospective accounting；barrier acceptance 已列入 future WU。 |
| `CODEX-REREVIEW-F03` | **已关闭** | `max_subscriptions_per_session` 是 required typed field；check+reserve 早于 mailbox/cursor/task allocation；拒绝、release、overflow retained reservation、不同 Session 隔离、typed error 与 derived bound 都已冻结。 |
| `CODEX-REREVIEW-F04` | **已关闭** | 唯一三步算法与 item-full + oversized=`PAYLOAD_BYTES` 已在 design truth、设计记录、fix mapping 和 exact fixtures 中一致。 |

## Material findings

### CODEX-FINAL-REREVIEW-F01-未修复-[高]-Host 合流没有 terminal cutoff，B delta 可在 A generation 暂停前被消费并丢弃

- **状态**：`accepted-candidate`。
- **位置**：`docs/host/design.md:360,405,409,442,450,464-472`；原设计记录 `docs/reviews/wu-transient-delivery-ownership-design-codex.md:155-165,200-206`；fix acceptance `docs/reviews/wu-transient-delivery-ownership-design-rereview-fix-codex.md:69-73,81-83`。
- **问题类型**：状态机漏洞 / 并发恢复风险 / 架构边界 / 不可直接实施。
- **当前写法**：Service consumer 只处理当前 target，A terminal first-commit 后在下一次 `anext()` 前暂停，coordinator 再 ack / clear / bind B；未绑定时事件留在 Host mailbox。Host 只承诺同一 Run 已接受 delta 在该 Run terminal 前交付，terminal fence 被描述为 O(1) current marker，但没有冻结 marker 的建立时刻、publication cutoff 或 mailbox pop 规则。
- **反例/失败场景**：
  1. A terminal 已提交 EventLog，terminal closeout 立即触发 queue promotion wake；watcher 此时尚未读取该 durable terminal。
  2. B 被 promotion 并开始执行，在 watcher 下一次读取 durable batch前发布 reasoning/content delta；该 delta已进入同一 Session subscription mailbox。
  3. merge 若沿当前可实现路径先 pop transient，再处理 durable terminal，就先把 B delta交给仍处于 `CONSUMING(g=A)` 的 Service consumer。设计要求其它 Run event不缓存，consumer 因 target 不匹配而丢弃它。
  4. consumer 随后才看到 A terminal、commit `TARGET_TERMINAL(g=A)` 并暂停；generation barrier 此时已经太晚。B 重新绑定后，其首批 live-only delta 不可 replay，且过程中没有 overflow 或 delivery error。
- **为什么有问题**：二轮 F01 的直接反例正是“A terminal 后 B 先 promotion 并产出 delta”。修订只关闭了 Service 在看到 terminal 之后继续 `anext()` 的竞态，却假设 Host 一定先交付 A terminal。该假设既不由两个 sequence domain 的 contract保证，也不由 current-terminal marker 的未规格描述保证。把 B event在 Service 侧缓存会重新引入第二 buffer并违反 owner boundary；正确修复必须位于 Host terminal handoff / iterator merge owner。
- **直接证据**：
  - `docs/host/design.md:360` 明确 durable / transient 没有可比较总序，只承诺同 Run delta-before-terminal；`:442` 却依赖 terminal先到达 consumer 才 pause。
  - 当前 `dayu/host/open_host.py:985-986` 在 durable read 前 drain transient，`:1000-1020` 在处理 batch terminal 前再次 drain transient。
  - `dayu/host/engine_ingest.py:2765-2784` 在成功 terminal closeout 后立即投递 promotion wake；`dayu/host/dispatch.py:1118-1136,2921-2953` 用独立 promotion queue/task推进下一 Run，因此 B publish 早于慢 watcher读取 A terminal是可达调度，不是推测性的非法顺序。
  - 原 re-review `docs/reviews/wu-transient-delivery-ownership-design-rereview-codex.md:67-78` 已把 B promotion / delta loss列为 F01 反例；本次修订没有增加 Host+Service 跨 owner cutoff acceptance。
- **影响**：正常、未 overflow 的 watcher会丢失下一 Run 的首批 live delta；startup / multi-target UI 显示缺口不会产生 typed degraded signal；Service generation 状态看似正确但 Host delivery 与 UI 观察事实不一致，implementation review 也无法选择唯一算法。
- **建议改法和验证点**：
  1. 在 Host Session Event Delivery / iterator merge owner 冻结 terminal cutoff 的唯一算法与线性化点。可选择在 terminal closeout 顺序中记录当前 runtime publication watermark / 非事件 control fence，或先观察 durable terminal并只交付其 pre-terminal prefix；但不得让 Service缓存 B event，也不得恢复历史 terminal set。
  2. 明确遇到首个 post-cutoff / next-Run transient 时如何保留在同一 mailbox或 counted in-flight，何时先 yield A terminal，何时在 generation B rebind 后再交付该 transient；retained accounting 必须继续覆盖该引用。
  3. 增加真实 Host merge + Service coordinator 的 integrated deterministic barrier：冻结 watcher，提交 A terminal，让 B promotion 并发布至少一个 delta，再恢复 watcher；断言 B delta不在 generation A 被交付/丢弃，A terminal先完成 ack，B delta随后在 generation B 交付，且无第二 event buffer。
- **修复风险（低/中/高）**：中。
- **严重程度（低/中/高/严重）**：高。

### CODEX-FINAL-REREVIEW-F02-未修复-[高]-fatal result 与 cleanup failure 没有唯一 caller-level仲裁

- **状态**：`accepted-candidate`。
- **位置**：`docs/host/design.md:411-421,423-454`，尤其 `:411` 的“至少包括”、`:439` 只为 delivery 定义 closed 后路径、`:449` 的“fail closed 或走已有 Host lifecycle recovery”与 `:454` 的 cleanup；fix mapping `docs/reviews/wu-transient-delivery-ownership-design-rereview-fix-codex.md:40-54,75-83`。
- **问题类型**：契约缺失 / 状态机漏洞 / 错误 owner / 不可直接实施。
- **当前写法**：设计称 `ServiceObservationResult` 为封闭联合，却写成“固定至少包括”五个 variant；`DELIVERY_INTERRUPTED` 明确进入 durable degraded recovery，`CALLBACK_FAILED` 明确原样传播，但 `ITERATOR_ENDED` / `ITERATOR_FAILED` 只被统称为 sticky fatal，后续允许“按其 public owner fail closed 或走已有 Host lifecycle recovery”。cleanup 又必须调用可能失败的 public `aclose()`，未规定它与已 first-commit result 的优先级。
- **反例/失败场景**：
  1. activity callback 抛出业务异常，consumer first-commit `CALLBACK_FAILED`；cleanup 时 iterator `aclose()` 又抛出 cleanup异常。若直接传播 `aclose()` 异常，原 callback failure没有“原样传播”且 sticky first-commit被覆盖；若无条件吞掉 cleanup异常，资源/Host read cleanup故障被静默隐藏。
  2. target 未 terminal 时 Host close造成 `ITERATOR_ENDED`。一个实现直接抛 Service error，另一个尝试 `get_run` / Outbox recovery；当前文字同时允许两者。若 current Host 已关闭，recovery API自身还可能抛 `HostClosedError`，其 precedence同样未定义。
  3. iterator 抛 public `HostApiError` 并 commit `ITERATOR_FAILED`，随后 `aclose()` 失败；实现者无法判断应保留原 public iterator failure、改报 cleanup failure，还是用 exception chaining表达，tests也没有唯一预期。
- **为什么有问题**：唯一 slot只解决“谁先写”，没有解决“helper最终向 caller承诺什么”。错误原因、retry/degraded选择与原异常传播同样是 Service watch-runtime owner 的语义，不能留给 `finally` 控制流偶然决定。所谓 closed union 也不能使用“至少包括”给 implementation agent保留新增 outcome分支的自由。
- **直接证据**：
  - `docs/host/design.md:421` 要求 `CALLBACK_FAILED` cleanup 后原样传播并禁止第二语义通道；`:449` 对另外两个 fatal variant没有唯一 action。
  - 当前具体 iterator `dayu/host/open_host.py:1269-1283` 明确允许 merge generator cleanup 的 `BaseException` 透传，虽然 subscription close 位于 `finally`；因此 cleanup double-failure 是当前接口事实允许的路径。
  - `docs/host/design.md:1128` 还要求 durable cursor/read failure映射为 public error，说明 `ITERATOR_FAILED` 的原始 public语义需要被保留，不能由 Service任意改写。
- **影响**：同一 primary failure会因实现的 `try/finally` 写法不同而返回不同错误；callback / EOF / iterator failure 可能被 cleanup覆盖或静默；fatal sticky与 public error owner失真，owner-level tests无法定义 exact acceptance。
- **建议改法和验证点**：
  1. 把 union改为恰好五个明确 variant，或给出完整、可穷举的 exact member list；禁止“至少包括”。
  2. 为每个 variant冻结 cleanup 后的唯一 caller disposition：terminal return、delivery degraded recovery、EOF 的具体 lifecycle error/recovery条件、callback原异常传播、iterator public异常传播。不得使用“fail closed 或 recovery”二选一。
  3. 冻结 cleanup failure precedence：已有 first-commit result时 primary语义不得被覆盖；cleanup failure应按设计选择 exception chaining / sanitized diagnostic 等唯一 secondary通道。slot为空时 cleanup failure如何成为 caller failure也要明确。Host reservation release仍必须由 Host `finally` 保证，不由 Service fallback重算。
  4. 增加 callback+`aclose` double failure、EOF+`aclose` failure、iterator failure+`aclose` failure、已有 terminal+cleanup failure四组 exact barrier，断言 primary result、secondary diagnostic/chaining、reservation release和无 task-exception side channel。
- **修复风险（低/中/高）**：中。
- **严重程度（低/中/高/严重）**：高。

## Verified closed design aspects

1. **F02 / single retention owner**：transient batch API、Service relay queue与 task-exception queue item都被明确删除；mailbox + 唯一 in-flight共享 items / bytes budget，caller外部引用被准确排除。没有发现新的 event-retaining第二 buffer授权。
2. **F03 / admission owner**：required `max_subscriptions_per_session`、opener-wide effective value owner、owner-loop reservation、拒绝零分配、专属 typed error、overflow期间保留 reservation、全部 detach/close/error释放路径与 per-Session derived bound已经一致；没有把 admission错误伪装成 Host outage。
3. **F04 / overflow owner**：single-event oversized优先于 item-full，随后才是 cumulative bytes；public detail只含一个 primary dimension，metrics可独立记录全部命中维度。设计与四组 fixtures无冲突。
4. **Eager attach**：reservation、fanout attach和 durable cursor request在返回前完成；首次 `anext()` 不做 lazy attach，submit/cancel mutation后发。该边界没有被 Service fallback或单入口特例取代。
5. **Architecture boundary**：Engine仍只拥有 run-local `EngineEvent stream` 顺序；Host ingest拥有 identity/late-state validation，Session Event Delivery拥有 live publication/retention/admission，Service拥有当前 target observation与展示。没有反向依赖或把 delivery policy泄漏给 Engine。
6. **Best practice / optimal solution**：typed public policy、logical byte helper、per-subscription isolation与专属 error比隐藏常量、双 queue或 durable delta更可测试且更小；不需要消息系统、Host-global quota或 per-subscription override才能关闭本 WU。
7. **Overcoupling / overengineering**：config view -> Service assembly -> Host typed policy是单向装配，不是共享可变状态；当前 blocker来自 Host merge与Service generation之间缺少明确 handoff contract，而不是需要增加新层或通用 broker。

## Open questions

没有 `needs-evidence` 型开放问题。两个 material findings 都有直接设计与代码证据，必须由 design owner在当前 design fix/re-review loop内裁决，不能留给 implementation agent选择。

## Residual ownership

| Residual / prerequisite | Owner | Tracking destination | Gate treatment |
| --- | --- | --- | --- |
| F01 的 Host terminal cutoff与Service generation handoff | Host Session Event Delivery / iterator merge design owner + Service watch-runtime design owner | 当前 design fix / final re-review loop | **不得 defer**；implementation gate前关闭。 |
| F02 的 exact fatal disposition与cleanup failure precedence | Service watch-runtime design owner；Host iterator owner负责 public cleanup/release保证 | 当前 design fix / final re-review loop | **不得 defer**；implementation gate前关闭。 |
| `WU-HOST-TRANSIENT-CAPACITY-01`、`WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 旧总控行修订 | Phaseflow Controller / control-doc owner | 本 gate 后的 Controller adjudication | 按用户明确边界处理；尚未写回不计设计 finding，禁止用兼容代码消化。 |
| packaged items / bytes / max-subscriptions数值 | runtime composer / operator + Session Event Delivery owner | future implementation WU benchmark / SLO evidence | 合法 measurement residual；不得改变 required字段、multi-watcher topology、算法或引入 Host fallback。 |
| logical UTF-8 budget到 Python heap的 safety margin、低基数 metrics | Session Event Delivery implementation owner | future implementation plan、stress/benchmark evidence | 合法 measurement / observability residual；不得记录 payload正文或高基数 identity。 |
| Engine ingest/publisher owner-loop affinity、post-terminal late validation | Host ingest / dispatch implementation owner | future WU code audit + contract tests | 已有设计 owner；只验证，不修改 Engine contract。 |
| 跨 Session Host总内存 / Host-global quota | 后续独立 capacity / deployment governance owner（若产品SLO或威胁模型要求） | 独立 issue / design gate | 当前设计已明确不作此保证；不是本 WU blocker，也不得借此扩张当前实现。 |

所有已识别 residual 均有明确 owner 与 tracking destination；**未归属 residual：0**。除表中 measurement、Controller handoff和明确 non-goal外，可直接实施的 terminal cutoff、fatal disposition与cleanup precedence不得后移。

## Final conclusion

**Verdict：FAIL。**

**Material findings：2（高 2；中 0；低 0；严重 0）。**

`CODEX-REREVIEW-F02`、`F03`、`F04` 已真实关闭；eager attach、single transfer + in-flight accounting、required subscription cap / reservation / release / derived bound，以及 overflow primary-dimension唯一算法均已达到可实施程度。

`CODEX-REREVIEW-F01` 仍未真实关闭。Service ack/rebind只在观察到 A terminal后生效，但 Host merge没有冻结阻止 B transient越过 A terminal的 cutoff；同时 `ITERATOR_ENDED` / `ITERATOR_FAILED` 与 `aclose()` secondary failure没有唯一 caller-level仲裁。两项都是 owner contract而非测试细节，会造成正常路径 live delta静默丢失或 primary failure漂移。修复并再次独立复审前，不应进入 implementation gate。
