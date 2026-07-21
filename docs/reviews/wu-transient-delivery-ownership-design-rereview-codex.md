# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Design Re-review（Codex）

## Gate metadata

- 审查时间：2026-07-21 15:00:22 CST（来自本机系统时钟）。
- Gate：phaseflow design revision re-review gate。
- Reviewer：AgentCodex，使用 `planreview` adversarial review 方法。
- 审查结论：**FAIL**。
- Blocking findings：**4**。
- Material findings：**4**（高 3，中 1，严重 0）。
- 修改边界：只新增本 artifact；不修改设计、代码、总控、README、测试或既有 artifact。

## Reviewed target and scope

本次只读复审以下输入：

- 当前工作区 `docs/host/design.md` 修订；
- `docs/engine/design.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-fix-codex.md`；
- 三份首轮 plan review：
  - `docs/reviews/plan-review-20260721-141110.md`；
  - `docs/reviews/plan-review-20260721-141359.md`；
  - `docs/reviews/plan-review-20260721-142109.md`。

为验证设计假设，直接核对了当前 `dayu/host/transient_delta.py`、`dayu/host/open_host.py`、`dayu/host/engine_ingest.py`、`dayu/host/dispatch.py`、`dayu/host/api.py`、`dayu/service/entrypoint_runtime.py`、Host/Service tests，以及只读 `docs/host/issues-implementation-control.md`。这不是代码 review；代码只作为设计可实施性的事实证据。

## First-principles assessment

修改动机成立，严重性没有被高估。Host 与 Service 当前分别持有 256-item buffer，Host public Protocol 没有公开具体 iterator 已有的关闭能力，单 item bound 也无法约束无跨 Runner byte 上限的 delta 字符串。把 transient publication、fanout、mailbox、overflow 与 detach 收回 Host Session Event Delivery owner，同时删除 Service event-copy relay，是当前约束下最小且正确的方向。

修订已经真实关闭了 no-backpressure 过度承诺、availability error owner 漂移、byte traversal 歧义、opener-wide policy owner 和 public closable iterator 等首轮问题。但它仍未达到 code-generation-ready：当前实现存在一个会在 async `yield` 间长期保留事件的 transient batch，修订没有要求移除；Service sole-consumer 状态机没有覆盖 callback failure、iterator 正常结束和 startup 多目标换绑；当前多 watcher 已由 public contract 与测试直接证明，却仍把 admission/aggregate 的 public 语义交给实施 WU 决定；双界同时命中的 public diagnostic 规则也存在文字冲突。因此不能把这些当前可实施、会改变公共行为的决策降为 implementation measurement 或 residual。

## Assumptions tested

| 假设 | 结论 | 直接依据 |
| --- | --- | --- |
| Engine 应拥有 session fanout / mailbox | 否；Host Session Event Delivery 是正确 owner | `docs/engine/design.md:28-38,450-513` 明确 Engine 只拥有单次 generator 顺序，不拥有 Host cursor、fanout、EventLog 或 replay。 |
| public closable iterator 可实现且 owner 正确 | 是 | `docs/host/design.md:342,364` 已冻结 public `HostSessionEventIterator`；当前具体实现 `dayu/host/open_host.py:1194-1283` 已有 started / never-started 幂等关闭基础。 |
| attach-before-submit + sole `anext` owner 状态机已无竞态 | 否 | `docs/host/design.md:405-428` 未定义 callback exception、正常 `StopAsyncIteration` 的 observation result，也未定义 startup target 之间的 pause/ack/rebind transition。见 F01。 |
| 每订阅严格只有一个 transient event-retaining buffer | 否 | 当前 `drain_nowait()` 把整队列转成 tuple，`open_host` 在逐项 `yield` 时长期保留；队列已扣账且可再次填满。修订 scope 未要求改成单项 transfer。见 F02。 |
| no-backpressure 承诺精确且可证明 | 是 | `docs/host/design.md:358,376,2013` 只承诺 publish 不等待被动 consumer / capacity，并明确排除 blocking callback、CPU starvation 与同步 O(N) fanout 的物理隔离。 |
| delivery error owner 正确 | 是 | `docs/host/design.md:382-397,1397-1409,1424-1432` 使用 delivery-specific code/detail/enum、`retryable=false`，不再污染 `HostUnavailableDetail`。 |
| byte traversal 与 owner-loop linearization 已明确 | 基本是 | `docs/host/design.md:370-378` 列出全部 string occurrence、一次计算后 fanout、同一无 `await` owner-loop 调用栈；但同时命中 dimension 的优先规则冲突，见 F04。 |
| O(1) terminal fence 可实现且没有 semantic owner drift | 是，需按已写 owner-loop前提实现 | `docs/host/design.md:360,401` 只保留 suspended terminal handoff 的 current marker，下一次 generator 恢复或 cleanup 释放；post-terminal 拒绝仍由 ingest late-state validation 拥有。当前生产 delta ingest/publish 位于 `dispatch.py:3944-4090` 的顺序消费路径及 `engine_ingest.py:852-875` 的同步 finish path，支持该边界。 |
| multi-watcher aggregate acceptance 已可直接实现 | 否 | 设计自己确认当前多订阅成立，却只要求实施前再 audit，并未冻结 cap、配置 owner、attach refusal 或资源释放 contract。见 F03。 |

## First-round finding closure matrix

| 首轮 finding | Re-review 结论 | 证据 / 后续 |
| --- | --- | --- |
| `CODEX-DESIGN-F01`；`DS-DESIGN-F01`；`MIMO-DESIGN-F01` | **未真实关闭** | public `aclose()`、sole consumer 与 stop-await-aclose 已补齐，但 consumer completion/error channel 和 startup 多目标换绑仍不闭合。转 F01。 |
| `CODEX-DESIGN-F02` | **已关闭** | no-backpressure 已收窄为“不 await 被动 consumer 或 capacity”；同 loop starvation / blocking callback / O(N) fanout 被明确排除。 |
| `CODEX-DESIGN-F03`；`DS-DESIGN-F04` | **已关闭** | 新 delivery-specific public error、typed dimension 与 `retryable=false` 归属正确；Service degraded recovery 不再标 Host outage。 |
| `CODEX-DESIGN-F04`；`DS-DESIGN-F05`；`MIMO-DESIGN-F03` | **设计内授权与文件面已关闭；Controller handoff 尚待执行** | `docs/host/design.md:124,432-452` 已授权 public field/export/error 并列出 config、Service、tests、README 与旧术语删除。只读总控的旧 deferred rows 仍相反，必须由 Controller 在 implementation gate 前裁决，见 Residual Ownership。 |
| `CODEX-DESIGN-F05` | **未真实关闭** | opener-wide owner、field traversal 与 O(1) fence 已关闭；单 mailbox 实际 retention 与 multi-watcher aggregate/admission 未闭合。转 F02、F03、F04。 |
| `DS-DESIGN-F02`；`MIMO-DESIGN-F02` | **原 finding 的 traversal/concurrency 歧义已关闭** | envelope/payload 字段与 owner-loop linearization 已明确；F02 是新的实际 retention/accounting 反例，F04 是修订新引入的 simultaneous-hit 冲突。 |
| `DS-DESIGN-F03` | **已关闭** | opener-wide uniform policy 与 per-subscription override non-goal 已明确。 |

## Material findings

### CODEX-REREVIEW-F01-未修复-[高]-sole-consumer 的完成/失败通道与 startup 换绑状态机仍未闭合

- **位置**：`docs/host/design.md:403-430`，尤其 `:405-407,420-428`；原设计记录 `:134-146,188-191`。
- **问题类型**：状态机漏洞 / 并发恢复风险 / 不可直接实施。
- **当前写法**：唯一 consumer 负责 `anext()` 和直接 callback，只允许把 matching target terminal 或 typed watcher failure 写入容量一 slot；startup 用同一个 consumer 顺序绑定 active / promoted target；callback exception 只被声明为 Service / UI failure；Host close 则让 iterator 正常结束。
- **反例/失败场景**：
  1. activity / thinking callback 在 sole consumer task 中抛错。该错误不是 public watcher failure，现有允许的 slot union 没有它；若 task 直接失败，command / durable probe 只等待 slot、timer 或 command future，可能永久等待；若把它塞成 delivery failure，又违反错误 owner。
  2. Host close 使 iterator 正常 `StopAsyncIteration`。这同样不是 typed watcher failure，也没有 terminal result；consumer 正常退出但没有 signal，等待方无法区分“仍在等待”与“观察通道已结束”。
  3. startup target A terminal 后，queued Run B 可立即 promotion 并产出 delta。consumer 若继续 `anext()`，在 B 尚未绑定时会按设计丢弃 B event；若暂停，则设计没有 `CONSUMING -> ATTACHED_UNBOUND`、slot acknowledgement、下一 target generation/bind 的线性化规则。现有线性状态图只写正向 `ATTACHED_UNBOUND -> CONSUMING -> DEGRADED -> STOPPING`，不能表达复用。
- **为什么有问题**：首轮 F01 的 root cause 是删除 relay 后必须有完整、唯一的消费与协调 owner。修订给出了 task 形状，但仍把最关键的 completion/error arbitration 与 multi-target rebind 留给实现者。一个实现会增加第二个异常 channel，另一个会扩大 slot union，第三个会监控 task exception；它们的终止和去重语义不同，不能由 implementation agent 任意选择。
- **直接证据**：当前 callback 在主等待协程消费 queue 时直接调用并向调用方传播，见 `dayu/service/entrypoint_runtime.py:1157-1212,1215-1297`；当前 drain task 只把 watcher exception 包成 `_WatcherFailure`，见 `:1036-1054`；startup 依赖持续 relay queue 跨多次 snapshot / target wait 保存所有 terminal，见 `:799-919,1639-1668`。移除该 queue 后，这些时序不能自然保留。
- **影响**：等待挂死、subscription 泄漏、callback failure 被误报为 Host delivery failure、startup promoted Run live delta 丢失、下一 target 在已死亡 consumer 上等待，或重复 terminal / renderer close。
- **建议改法和验证点**：
  1. 在设计中冻结 Service observation result 的封闭联合与唯一通知 owner，至少区分 target terminal、delivery interruption、iterator normal end / Host close、Service callback failure；定义 slot 满时的 first-commit / sticky-failure arbitration，禁止用 task exception 作为未声明的第二语义通道。
  2. 明确 callback failure 进入 Service observation failure 并 `STOPPING`，向 helper caller 传播；不得转成 `DELIVERY_INTERRUPTED`。
  3. 对 startup 复用定义 target generation handshake：目标 terminal first-commit 后 consumer 在下一次 `anext()` 前回到 `ATTACHED_UNBOUND` 并等待 coordinator ack/下一目标绑定；旧 generation 的迟到 signal 不得覆盖新目标。若选择每目标关闭重建 watcher，必须重新证明 attach gap 与 Outbox closure，不能暗中改变当前“同一 consumer”决定。
  4. owner-level tests 必须用 barrier 覆盖 callback throw、Host close normal EOF、terminal 与 stop 同拍、A terminal 后 B promotion 先于 rebind、slot 已占用时 watcher failure，以及 cleanup 后无 active `anext()`。
- **修复风险（低/中/高）**：中。
- **严重程度（低/中/高/严重）**：高。

### CODEX-REREVIEW-F02-未修复-[高]-当前 transient batch drain 会在 mailbox 外保留第二批未计量事件

- **位置**：`docs/host/design.md:366,374-378,438-439`；原设计记录 `:102-114,185-186,284-289`。
- **问题类型**：资源边界 / 契约缺失 / 最佳实践偏离。
- **当前写法**：每个 subscription 只有一个 items / bytes 双界 mailbox，drain 按 entry size 扣减；未来 scope 只要求改造 `transient_delta.py` mailbox 和 `open_host.py` 合流，没有要求删除现有 batch-return drain。
- **反例/失败场景**：当前 `HostTransientDeltaSubscription.drain_nowait()` 把 queue 全部取出到 `list` 再返回 `tuple`（`dayu/host/transient_delta.py:242-258`）；`open_host` 三处 `for transient in subscription.drain_nowait(): yield transient`（`dayu/host/open_host.py:985-986,1000-1001,1012-1013`）。当 queue 中已有接近 `max_bytes=B` 的事件时，drain 先把 mailbox accounting 降到 0，再在第一个 async `yield` 暂停；publisher 此时可把 mailbox 再填到 B。于是同一 subscription 同时保留接近 B 的 generator-local tuple 和 B 的 mailbox，policy/metrics 只看到后一份。
- **为什么有问题**：这不是不可避免的“当前正在交付一个 event”，而是最多一整批事件在 accounting boundary 外等待 consumer。它直接否定“一个 transient event-retaining buffer”和 `max_items/max_bytes` 对 pending delivery 的可解释性；只删除 Service queue 仍会保留 Host 内二级 staging。
- **直接证据**：当前 `drain_nowait()` 返回任意长度 tuple，测试也把整批结果作为集合断言，见 `tests/host/test_transient_delta.py:170-171,274-296,326-328`。修订的 future tests 只写 exact accounting / overflow，没有写“yield 首项后 mailbox refill 时 accounting 外最多一项”。
- **影响**：每订阅实际 pending item / logical byte retention 可接近公开 mailbox budget 的两倍，overflow dimension、high-watermark 与容量测量失真；实现可以在形式上删除 Service queue 却没有关闭双 buffer root cause。
- **建议改法和验证点**：在设计与 future scope 中明确 transient subscription 只能单项 pop/transfer；禁止 `list` / `tuple` / `deque` batch drain。accounting 只在事件转交给本次立即 `yield` 时扣减，mailbox 外最多允许当前正在交付的一项。用 deterministic barrier 在第一个 yield 后持续 publish，断言剩余旧 prefix 不在独立容器、mailbox item/byte 上限仍成立，且 overflow/high-watermark 与真实 pending retention 一致。
- **修复风险（低/中/高）**：低到中。
- **严重程度（低/中/高/严重）**：高。

### CODEX-REREVIEW-F03-未修复-[高]-multi-watcher aggregate/admission 仍是未设计的 public contract

- **位置**：`docs/host/design.md:342,399,432-452,1336,2013`；原设计记录 `:173-177,185,202,238-240,278`。
- **问题类型**：契约缺失 / 资源边界 / 当前可实施项被后移。
- **当前写法**：设计已确认 Session -> subscription set 和 multi-watcher tests 证明多订阅存在，但仍要求实施 WU “先 audit”；若多订阅成立，再由同一 WU“落地 session admission / aggregate bound”。policy 只冻结 per-subscription items/bytes，没有冻结 admission 字段、aggregate 算法、attach refusal、释放与错误 contract。
- **反例/失败场景**：当前 public contract 明确适合多个客户端打开同一 Session，且双 watcher tests 直接通过（`tests/host/test_watch_session_events.py:451-489,493-541`；`tests/host/test_public_open_host_multiturn_smoke.py:84-119`），所以“是否多订阅”不是未知假设。若 implementation agent采用动态 aggregate usage cap，它必须决定哪个 watcher 被拒绝或 detach，可能违反“一个 subscription overflow 不影响其它 watcher”；若采用 attach reservation / watcher count cap，又必须新增 policy 字段、typed attach error 与容量释放规则。若不加 cap，攻击或错误调用者可以无限 attach，每个合法占满独立 mailbox，Host 总 retention 与同步 O(N) fanout仍无界。
- **为什么有问题**：admission 是 Host public attach 行为，aggregate bound 是 Session Event Delivery 的资源语义，不能以“implementation acceptance”代替设计。当前代码和设计已经选择 multi-watcher，实施前不存在可以继续 defer 的 topology 问题；未冻结 contract 会迫使 implementation agent新增 public schema或隐藏常量，两者都违反本修订的 typed single-source 原则。
- **直接证据**：`dayu/host/transient_delta.py:388-475` 对同一 Session 使用无上限 subscription set 并同步 fanout；`docs/host/design.md:399` 自己承认 per-sub bound 不是 Host aggregate bound；`HostSessionEventDeliveryPolicy` 当前只列两个 mailbox 字段（`:368`）。
- **影响**：无法验收 Host 总资源边界；可能出现 unbounded watcher attach、跨 watcher 非确定性驱逐、错误 owner 漂移、隐藏 magic cap，或在 implementation review 时被迫重开 public design gate。
- **建议改法和验证点**：在当前设计 gate 选择并冻结最小 aggregate 模型。保持 multi-watcher 时，优先使用 attach-time reservation：在 opener-wide typed policy 中显式加入正整数 session subscription admission cap，使最坏情况由 `cap × per-subscription budget` 可推导；冻结 cap owner、packaged value 的测量责任、cap+1 attach 的专属 typed error、detach/overflow/never-started/Host close 后释放、同 owner-loop 线性化以及既有 watcher不受拒绝影响。若选择单订阅，必须先修改当前 multi-client public contract并说明产品回归，不能只用调用图“证明”与现有设计相反的结论。测试覆盖 cap-1/cap/cap+1、并发 attach、detach 后再 admission、不同 Session 隔离和被拒绝 attach 零资源泄漏。
- **修复风险（低/中/高）**：中。
- **严重程度（低/中/高/严重）**：高。

### CODEX-REREVIEW-F04-未修复-[中]-item/byte 同时超限时的 public primary dimension 规则互相冲突

- **位置**：`docs/host/design.md:378`；原设计记录 `:112-113`。
- **问题类型**：公共错误契约冲突 / 不可直接实施。
- **当前写法**：同一段先规定“先判 item count，再判 payload bytes”，又规定“单个事件自身超 bytes 固定报告 `PAYLOAD_BYTES`”，随后规定“同一 offer 同时命中两个累计上限报告 `ITEM_COUNT`”。
- **反例/失败场景**：mailbox 已达到 `max_items`，新 event 自身也大于 `max_bytes`。该 offer 同时满足“单 event oversize 固定 PAYLOAD_BYTES”和“item+byte 同时命中固定 ITEM_COUNT”，实现与测试无法同时满足两个 public promise。
- **为什么有问题**：`limit_dimension` 是 public closed enum 和 operator diagnostic，不是内部日志细节。不同实现选择会让 Service diagnostics、metrics 与 boundary tests 漂移，违反唯一语义 owner。
- **直接证据**：`docs/host/design.md:382-395` 将 dimension 放入 delivery-specific public detail；因此 `:378` 的判定优先级必须唯一。
- **影响**：相同 mailbox/event 状态产生不同 public error detail，review 无法定义 exact acceptance。
- **建议改法和验证点**：冻结一条无例外总顺序。例如先判“单 event 自身 oversize”，再判 prospective item count，再判 prospective cumulative bytes；或删除单-event 特例并始终 item-first。operator metrics 可以另记全部命中维度，但 public primary dimension 只能有一个算法。增加空 mailbox oversized、item-full + small event、byte-full + small event、item-full + oversized event 四个 exact fixture。
- **修复风险（低/中/高）**：低。
- **严重程度（低/中/高/严重）**：中。

## Verified closed design aspects

1. **Architecture boundary**：Engine 继续只拥有 run-local generator 顺序；Host ingest 拥有 durable identity / late-state validation；Session Event Delivery 拥有 live publication 与 subscription。没有反向依赖或把 Host policy泄漏给 Engine。
2. **Public close owner**：公开可关闭 iterator 比 Service 私有 Protocol/cast 更优，且 current implementation 已证明该形态可行。
3. **No-backpressure wording**：承诺已限定到不等待被动 consumer / mailbox capacity，没有再把同-loop调度、callback 或 fanout 成本伪装成物理隔离。
4. **Delivery error owner**：局部 continuity loss 不再复用 Host availability；typed error、non-retryable 与 durable degraded recovery 自洽。
5. **Byte 双界方向**：items 与 logical UTF-8 bytes 解决不同成本，字段 traversal、一次计算后 fanout和不宣称等于 heap 的取舍正确；F02/F04 要修的是 retention/判定闭环，不是否定双界。
6. **O(1) terminal fence**：在当前 owner-loop、同步 publish 顺序下，current-terminal marker足以完成 mailbox prefix/terminal handoff；历史 terminal 拒绝继续由 ingest owner负责，不需要 subscription set。
7. **Optimal-solution / overengineering**：Host单 mailbox + durable pull 是已评估方案中最小路径；无需把 delta durable 化、引入消息系统、Host-global quota或 per-subscription override。
8. **Overcoupling**：config -> runtime typed view -> Service assembly -> Host public policy 是单向装配链，属于一个资源 contract，不是跨层共享可变状态；真正的风险是 F03 尚未冻结 aggregate contract，而不是这条 typed链本身。

## Open questions

以下不是可留给 implementation agent 自由决定的问题，必须先由 design owner 关闭：

1. Service observation result 如何表达 callback failure、normal iterator end，并与 terminal / delivery failure仲裁？startup 多目标复用使用什么 generation/ack barrier？
2. transient mailbox 是否改成单项 transfer；如果坚持 batch，batch 如何纳入同一 item/byte accounting而不成为第二 buffer？
3. multi-watcher 使用何种 session admission / aggregate模型，其 typed policy、attach error 和 release contract 是什么？
4. item count 与 single-event/cumulative byte 同时超限时，唯一 primary dimension 顺序是什么？

以下参数可在 contract 修复后由 implementation WU 用证据选择，不阻塞设计方向：packaged items/bytes/admission 数值、logical-byte 到 Python heap 的安全 margin、低基数 metrics / high-watermark 采样。

## Residual ownership

| Residual / prerequisite | Owner | Tracking destination | Gate treatment |
| --- | --- | --- | --- |
| F01-F04 的 contract 修订 | Host design owner + Service watch-runtime design owner | 当前 design fix/re-review loop | **不得 defer**；re-review PASS 前关闭。 |
| `WU-HOST-TRANSIENT-CAPACITY-01` 与 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 旧控制行仍分别禁止 public knob / relay deletion | Phaseflow Controller / `docs/host/issues-implementation-control.md` owner | 下一次 controller adjudication，在 implementation gate 前重登记或替换 | 当前 reviewer无权改总控；这是 F04 的流程 handoff，不应由代码兼容分支消化。 |
| packaged policy 数值、heap margin、低基数 metrics | Future implementation WU，runtime composer/operator + Session Event Delivery owner | implementation plan / benchmark evidence | 可保留为 measurement residual；不得成为 Host fallback。 |
| callback 快速非阻塞与慢 I/O/CPU隔离 | Service / UI adapter owner | Service/CLI owner-level tests 与 README contract | 已有 owner；不扩大 Host物理隔离承诺。 |
| Engine ingest/publisher owner-loop affinity 与 terminal前 publish顺序 | Host ingest / dispatch owner | future WU code audit + contract tests | 验证项，不修改 Engine contract。 |

除上述明确 measurement / Controller handoff 外，当前可实施的单项 drain、Service failure/rebind状态机和 session admission contract 不能再作为 residual 后移。

## Final conclusion

**Verdict：FAIL。**

首轮 `CODEX-DESIGN-F02`、`F03`，以及 DS/MiMo 关于 byte traversal、opener-wide policy、delivery error和术语/file scope 的同类 findings 已真实关闭；公开可关闭 iterator与 O(1) current-terminal fence 的方向也可实现。

但 `CODEX-DESIGN-F01` 尚未完成 callback/EOF/multi-target rebind闭环，`CODEX-DESIGN-F05` 尚未关闭 mailbox 外 batch retention 和已知 multi-watcher aggregate/admission；修订还引入了 public overflow dimension 的确定性冲突。4 个 finding 都会迫使 implementation agent重新设计公共或并发语义，不能以测试补齐、默认值测量或 future residual代替 design owner 决策。修复后需要再次独立 re-review；在此之前不应进入 implementation plan/gate。
