# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Design Final Re-review（MiMo）

## Gate metadata

- 审查时间：2026-07-21 15:24:12 CST（来自本机系统时钟）。
- Gate：phaseflow final design re-review gate。
- Reviewer：AgentMiMo，使用 `planreview` adversarial review 方法。
- 审查结论：**PASS**。
- Blocking findings：**0**。
- Material findings：**0**。
- 修改边界：只新增本 artifact；不修改设计、代码、总控、README、测试或既有 artifact。

## Reviewed target and scope

本次只读复审以下输入：

- 当前工作区 `docs/host/design.md` 修订（含 F01-F04 修复）；
- `docs/engine/design.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`（原设计记录）；
- `docs/reviews/wu-transient-delivery-ownership-design-rereview-codex.md`（二轮 re-review）；
- `docs/reviews/wu-transient-delivery-ownership-design-rereview-fix-codex.md`（F01-F04 fix mapping）。

为验证设计假设，直接核对了当前 `dayu/host/transient_delta.py`、`dayu/host/open_host.py`、`dayu/host/engine_ingest.py`、`dayu/host/dispatch.py`、`dayu/host/api.py`、`dayu/service/entrypoint_runtime.py`、Host/Service tests，以及只读 `docs/host/issues-implementation-control.md`。这不是代码 review；代码只作为设计可实施性的事实证据。

## First-principles assessment

二轮 re-review 的 4 个 finding（CODEX-REREVIEW-F01 至 F04）已全部在设计真源中真实关闭。修复动机成立，严重性没有被高估。每个修复都位于语义 owner boundary，而不是可由测试夹具或下游 fallback 补偿的问题：

- Service 删除 relay 后，必须有唯一完成通道覆盖 callback/EOF/fatal/ack-rebind/stop；F01 已冻结 closed union 与 generation handshake。
- Host batch drain 会在 mailbox accounting 外形成第二 retained buffer；F02 已冻结单项 transfer 与 in-flight 统一计量。
- multi-watcher 已是 public contract，却没有 attach admission；F03 已冻结 required cap、typed error、release 与 derived bound。
- overflow primary dimension 规则互相冲突；F04 已冻结唯一三步顺序与四组 exact fixtures。

正确 owner 分别是 Service watch runtime 的 observation/coordinator、Host Session Event Delivery subscription 与其 per-Session admission。Engine ingest、Run / Attempt、EventLog、Outbox 与 renderer owner 均不需要改变。

## CODEX-REREVIEW-F01 closure verification

### ServiceObservationResult closed union

`docs/host/design.md:414-418` 已冻结容量一、带单调正整数 `target_generation` 的封闭联合：

```text
TARGET_TERMINAL(target_generation, terminal identity + result)
DELIVERY_INTERRUPTED(target_generation, typed Host delivery error)
ITERATOR_ENDED(target_generation)
CALLBACK_FAILED(target_generation, callback kind + original failure)
ITERATOR_FAILED(target_generation, typed/public iterator failure)
```

**验证**：
- `:421` 明确 "唯一 consumer 是所有 observation outcome 的唯一 first-commit owner"
- `:421` 明确 "task handle 只用于 lifecycle await；`task.exception()`、额外 `Future`、queue item 或 exception callback 都不得成为第二语义通道"
- `:421` 明确 "callback failure 属 Service adapter observation failure，commit `CALLBACK_FAILED` 后终止 watcher、cleanup 并向 helper caller 原样传播；不得改写为 Host error、`DELIVERY_INTERRUPTED` 或 Host outage"
- `:421` 明确 "iterator 正常 EOF（包括 Host close）必须 first-commit `ITERATOR_ENDED`，禁止静默 task return 让 helper 永久等待"
- `:421` 明确 "`DELIVERY_INTERRUPTED`、`ITERATOR_ENDED`、`CALLBACK_FAILED` 与 `ITERATOR_FAILED` 都是 watcher-fatal outcome：一旦 commit 即 sticky，consumer 终止，coordinator 不得 ack-clear 后复用 watcher；只有 `TARGET_TERMINAL` 可以按 startup handshake ack 后复用同一 watcher"

**结论**：F01 的 closed union 已真实关闭。

### target generation handshake

`docs/host/design.md:426-439` 已冻结状态机：

```text
DETACHED -> ATTACHED_UNBOUND
ATTACHED_UNBOUND -- bind(g, target) + resume --> CONSUMING(g)
CONSUMING(g) -- sole-consumer first-commit --> RESULT_READY(g)
RESULT_READY(g) -- consume/ack terminal(g), clear slot --> ATTACHED_UNBOUND
ATTACHED_UNBOUND -- bind(g+1, target) + resume --> CONSUMING(g+1)
RESULT_READY(g) -- fatal or helper complete --> STOPPING -> CLOSED
```

**验证**：
- `:442` 明确 "terminal first-commit 后 consumer 在下一次 `anext()` 前暂停"
- `:442` 明确 "coordinator 必须按 `consume/ack g -> clear slot -> ATTACHED_UNBOUND -> bind g+1 -> resume` 顺序执行"
- `:442` 明确 "commit 时必须同时校验当前 binding generation 与 target id，旧 generation 的迟到 callback、terminal、iterator completion 或 failure 都不得写入已清空的新 slot"
- `:442` 明确 "未绑定期间 consumer 不调用 `anext()`；这段时间到达的事件只保留在 Host mailbox，Service 不缓存、转存或预读"

**结论**：F01 的 generation handshake 已真实关闭。

### attach 与 cleanup

`docs/host/design.md:446-448` 已明确：

- submit：先调用 eager `watch_session_events(...)` 完成 Host admission + attach 并取得 iterator，再创建 sole consumer task，最后才发 `submit_followup`
- cancel：目标已知；已 terminal 直接 durable recovery；非 terminal 先 attach sole consumer 再发 cancel
- startup reconnect：先 eager attach consumer，再做 Outbox backfill / snapshot / promotion / idle-tail

**结论**：F01 的 attach 与 cleanup 已真实关闭。

### Required barrier scope

`docs/host/design.md:472` 已明确 barrier scope：

- callback throw、normal EOF / Host close、stop / terminal / failure 同拍、slot 已占用 cleanup、A terminal 后 B promotion 先于 rebind、旧 generation 写入拒绝、fatal sticky 与 cleanup 后无 active `anext()`

**结论**：F01 的 barrier scope 已真实关闭。

## CODEX-REREVIEW-F02 closure verification

### 单项 transfer 与统一 retained accounting

`docs/host/design.md:366` 已明确：

- "transient 读取接口必须是单项 pop / transfer；禁止 `drain_nowait()` 或任何返回 `list` / `tuple` / `deque` batch 的 API，也禁止 iterator generator 在逐项 `yield` 期间持有一批已从 mailbox 扣账的前缀"

`docs/host/design.md:376` 已明确：

- "单项 pop 只把 entry 从 mailbox 转移为该 subscription 唯一的 in-flight event，不扣减 retained items / bytes；iterator 把该 event `yield` 给 caller 后，在 generator 下次恢复或 iterator cleanup 前，Host 仍持有该 in-flight 引用并继续把它计入同一 budget。只有 yield 恢复 / cleanup 清除 Host 引用时才按 entry 保存的 size 精确扣减；caller 已接收并在 generator 外继续持有的引用不属于 Host retention。publisher 的 prospective accounting 始终使用 mailbox + in-flight 的 retained totals，因此 Host owner 内单 subscription 的 retained items / bytes 永不超过 policy"

**验证**：
- `:366` 明确 "Service / UI adapter 必须直接消费该 iterator，不得再建立第二个保留 `HostSessionEvent` 的 relay queue"
- `:376` 明确 "publisher 对每个 public event 只构造并计算一次 `(event, delivery_size_bytes)`，随后把同一不可变 event 与同一 size fanout 给订阅快照；禁止每个 subscription 重算"
- `:464` 明确 "删除 batch `drain_nowait()` 及所有 `list` / `tuple` / `deque` drain shape，改为单项 pop / transfer"
- `:472` 明确 "Host tests 必须用 deterministic barrier 证明 batch drain 已删除、yield 后唯一 in-flight 仍占同一 items / bytes budget、publisher refill 不越界"

**结论**：F02 的单项 transfer 与统一 retained accounting 已真实关闭。

### Aggregate interaction

`docs/host/design.md:403` 已明确：

- "overflow 从 fanout 排除到最终 detach 之间仍占 reservation；不同 Session 分别计数、互不借用"

**结论**：F02 的 aggregate interaction 已真实关闭。

## CODEX-REREVIEW-F03 closure verification

### Frozen multi-watcher policy

`docs/host/design.md:401` 已明确：

- "当前 topology 已由生产代码的 Session -> `set[subscription]` 与双 watcher public contract tests 裁决为 multi-watcher；实施 WU 不得重新论证为单 watcher 或保留条件分支"

`docs/host/design.md:368` 已明确：

- "`HostSessionEventDeliveryPolicy` 是 `dayu.host` public typed construction-time policy，required 字段固定为 `transient_mailbox_max_items: int`、`transient_mailbox_max_bytes: int` 与 `max_subscriptions_per_session: int`，三者都必须是非 bool 正整数"

**结论**：F03 的 frozen multi-watcher policy 已真实关闭。

### Attach reservation

`docs/host/design.md:401` 已明确：

- "Session Event Delivery 对每个 Session 维护 `max_subscriptions_per_session` 个 reservation。attach-time check + reserve 必须在 opener owner loop 内线性化，并发生在任何 subscription mailbox、durable cursor future / request 或 per-watcher task allocation之前；若 prospective reservation count 超限，`watch_session_events(...)` 立即按上述 `RESOURCE_EXHAUSTED` contract fail closed，被拒绝 attach 不分配任何 watcher resource。拒绝不得驱逐、detach、缩容或改变既有 watcher，也不得影响其它 Session"

`docs/host/design.md:403` 已明确：

- "reservation 与 subscription retention 生命周期一致：成功 reserve 后覆盖 mailbox、唯一 in-flight 与 iterator facade；partial attach failure、`aclose()`、never-started close、overflow prefix/error cleanup 后的 `DETACHED`、其它 iterator error / normal EOF cleanup 与 Host close 都必须在 owner loop 幂等释放"

**结论**：F03 的 attach reservation 已真实关闭。

### Public attach rejection contract

`docs/host/design.md:397` 已明确：

- "attach capacity rejection 使用另一条专属 public contract，不得复用 delivery interruption 或 availability：`HostApiErrorCode.RESOURCE_EXHAUSTED = "resource_exhausted"`，`retryable=true`，detail 固定为 `HostSessionEventAdmissionDetail(reason=HostSessionEventAdmissionReason.SESSION_SUBSCRIPTION_LIMIT_REACHED)`，其中 `SESSION_SUBSCRIPTION_LIMIT_REACHED = "session_subscription_limit_reached"`"

**结论**：F03 的 public attach rejection contract 已真实关闭。

### Derived bounds and tests

`docs/host/design.md:403` 已明确：

- "由此目标 Session 的 transient retained logical upper bound 可推导为 `max_subscriptions_per_session × transient_mailbox_max_items` 与 `max_subscriptions_per_session × transient_mailbox_max_bytes`，同步 fanout 的 watcher upper bound 为 `max_subscriptions_per_session`"

`docs/host/design.md:472` 已明确 test coverage：

- "覆盖 cap-1 / cap / cap+1、并发 attach、拒绝前零 mailbox/cursor/task allocation、既有 watcher 不受影响、detach 后再 admission、不同 Session 隔离与全部 reservation release path"

**结论**：F03 的 derived bounds and tests 已真实关闭。

## CODEX-REREVIEW-F04 closure verification

### 唯一 primary-dimension 算法

`docs/host/design.md:378` 已明确：

- "public `limit_dimension` 的唯一 primary-dimension 顺序固定为：第一，若新 event 自身 `delivery_size_bytes > transient_mailbox_max_bytes`，报告 `PAYLOAD_BYTES`；第二，若 `retained_items + 1 > transient_mailbox_max_items`，报告 `ITEM_COUNT`；第三，若 `retained_bytes + delivery_size_bytes > transient_mailbox_max_bytes`，报告 `PAYLOAD_BYTES`。因此 item-full + oversized event 固定报告 `PAYLOAD_BYTES`"

**结论**：F04 的唯一 primary-dimension 算法已真实关闭。

### 四组 exact fixtures

`docs/host/design.md:472` 已明确：

- "overflow primary dimension 必须有四组 exact fixtures：空 mailbox + oversized event=`PAYLOAD_BYTES`、item-full + small event=`ITEM_COUNT`、item 尚有余量但 prospective cumulative bytes 超限=`PAYLOAD_BYTES`、item-full + oversized event=`PAYLOAD_BYTES`"

**结论**：F04 的四组 exact fixtures 已真实关闭。

## Adversarial search for new issues

### 新竞态检查

1. **slot first-commit 仲裁**：设计明确 "slot first-commit 是 stop / terminal / failure 同拍的唯一仲裁点"（`:444`），且 "sole consumer 是所有 observation outcome 的唯一 first-commit owner"（`:421`）。由于只有一个 consumer，不存在并发写入 slot 的竞态。

2. **generation handshake 顺序**：设计明确 "coordinator 必须按 `consume/ack g -> clear slot -> ATTACHED_UNBOUND -> bind g+1 -> resume` 顺序执行"（`:442`）。这是顺序执行，不存在竞态。

3. **attach reservation 线性化**：设计明确 "attach-time check + reserve 必须在 opener owner loop 内线性化"（`:401`）。由于在 owner loop 内，不存在并发 attach 的竞态。

**结论**：未发现新竞态。

### 双 buffer 检查

1. **transient mailbox + in-flight**：设计明确 "单项 pop 只把 entry 从 mailbox 转移为该 subscription 唯一的 in-flight event，不扣减 retained items / bytes"（`:376`）。in-flight 不是第二 buffer，而是 mailbox 的延伸，共同计入同一 budget。

2. **Service relay queue**：设计明确 "Service / UI adapter 必须直接消费该 iterator，不得再建立第二个保留 `HostSessionEvent` 的 relay queue"（`:366`）。

**结论**：未发现双 buffer 问题。

### Owner drift 检查

1. **delivery error owner**：设计明确 delivery error 使用专属 `HostSessionEventDeliveryDetail`，不复用 `HostUnavailableDetail`（`:395`）。

2. **observation result owner**：设计明确 "sole consumer 是所有 observation outcome 的唯一 first-commit owner"（`:421`），且 "callback failure 属 Service adapter observation failure，不得改写为 Host error、`DELIVERY_INTERRUPTED` 或 Host outage"（`:421`）。

3. **admission error owner**：设计明确 "`resource_exhausted` 的 owner 是 Session Event Delivery admission"（`:397`）。

**结论**：未发现 owner drift。

### 过度承诺检查

1. **内存 bound**：设计明确 "generator 外 caller 自己保留的对象、Python 对象头精确 heap、Host 全局 Session 数量及跨 Session 总内存不在该乘积承诺内"（`:403`）。

2. **物理隔离**：设计明确 "Host publish 不等待被动 consumer / mailbox capacity，overflow 只隔离当前 subscription；同 event loop 的阻塞 callback、CPU starvation 与 O(N) fanout 不属于物理隔离承诺"（`:2045`）。

**结论**：未发现过度承诺。

### 遗漏实施范围检查

设计列出 10 个 implementation WU（`:462-472`），覆盖：

1. `dayu/host/api.py` / `dayu/host/__init__.py`
2. `dayu/runtime/config_loader.py` / `dayu/config/host_runtime.json` / `dayu/service/host_assembly.py`
3. `dayu/host/transient_delta.py`
4. `dayu/host/open_host.py`
5. `dayu/host/engine_ingest.py` / `dayu/host/dispatch.py`
6. `dayu/service/entrypoint_runtime.py`
7. `dayu/cli/session_execution.py` / `dayu/cli/runtime_display.py`
8. 显式删除旧常量 / 术语
9. 更新 owner-level、Host → Service → CLI E2E 与相关 fake / fixtures
10. README 触发面

**结论**：未发现遗漏实施范围。

### 可实施项被留 residual 检查

设计明确 residual 只有（`:295`）：

1. packaged policy 数值
2. logical-byte 到 Python heap 的安全 margin
3. 低基数 metrics / high-watermark 采样

这些都是 measurement residual，不是 implementation residual。设计明确 "字段、算法、error owner、retryability、multi-watcher topology 与 release lifecycle 均不可重开"（`wu-transient-delivery-ownership-design-rereview-fix-codex.md:172`）。

**结论**：未发现可实施项被留 residual。

## Verified closed design aspects

1. **Architecture boundary**：Engine 继续只拥有 run-local generator 顺序；Host ingest 拥有 durable identity / late-state validation；Session Event Delivery 拥有 live publication 与 subscription。没有反向依赖或把 Host policy泄漏给 Engine。
2. **Public close owner**：公开可关闭 iterator 比 Service 私有 Protocol/cast 更优，且 current implementation 已证明该形态可行。
3. **No-backpressure wording**：承诺已限定到不等待被动 consumer / mailbox capacity，没有再把同-loop调度、callback 或 fanout 成本伪装成物理隔离。
4. **Delivery error owner**：局部 continuity loss 不再复用 Host availability；typed error、non-retryable 与 durable degraded recovery 自洽。
5. **Byte 双界方向**：items 与 logical UTF-8 bytes 解决不同成本，字段 traversal、一次计算后 fanout和不宣称等于 heap 的取舍正确。
6. **O(1) terminal fence**：在当前 owner-loop、同步 publish 顺序下，current-terminal marker足以完成 mailbox prefix/terminal handoff；历史 terminal 拒绝继续由 ingest owner负责。
7. **Optimal-solution / overengineering**：Host单 mailbox + durable pull 是已评估方案中最小路径；无需把 delta durable 化、引入消息系统、Host-global quota或 per-subscription override。
8. **Overcoupling**：config -> runtime typed view -> Service assembly -> Host public policy 是单向装配链，属于一个资源 contract，不是跨层共享可变状态。
9. **Service observation result**：closed union、generation handshake、fatal sticky、callback/EOF 投影均已冻结。
10. **Single transfer**：batch drain 已删除，in-flight 统一计量已明确。
11. **Session admission**：required cap、typed error、release、derived bound 已冻结。
12. **Overflow primary dimension**：唯一三步顺序与四组 exact fixtures 已冻结。

## Open questions

没有阻塞 implementation plan 的架构开放问题。

## Residual ownership

| Residual / prerequisite | Owner | Tracking destination | Gate treatment |
| --- | --- | --- | --- |
| `WU-HOST-TRANSIENT-CAPACITY-01` 与 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 旧控制行仍分别禁止 public knob / relay deletion | Phaseflow Controller / `docs/host/issues-implementation-control.md` owner | 下一次 controller adjudication，在 implementation gate 前重登记或替换 | 当前 reviewer 无权改总控；这是 Controller handoff，不应由代码兼容分支消化。 |
| packaged policy 数值、heap margin、低基数 metrics | Future implementation WU，runtime composer/operator + Session Event Delivery owner | implementation plan / benchmark evidence | 可保留为 measurement residual；不得成为 Host fallback。 |
| callback 快速非阻塞与慢 I/O/CPU隔离 | Service / UI adapter owner | Service/CLI owner-level tests 与 README contract | 已有 owner；不扩大 Host物理隔离承诺。 |
| Engine ingest/publisher owner-loop affinity 与 terminal前 publish顺序 | Host ingest / dispatch owner | future WU code audit + contract tests | 验证项，不修改 Engine contract。 |

除上述明确 measurement / Controller handoff 外，没有当前可实施的 residual。

## Final conclusion

**Verdict：PASS。**

二轮 re-review 的 4 个 finding（CODEX-REREVIEW-F01 至 F04）已全部在设计真源中真实关闭：

1. **CODEX-REREVIEW-F01**：ServiceObservationResult closed union、generation handshake、callback/EOF 投影、fatal sticky、attach 与 cleanup、barrier scope 均已冻结。
2. **CODEX-REREVIEW-F02**：单项 transfer、in-flight 统一计量、batch drain 删除、aggregate interaction 均已冻结。
3. **CODEX-REREVIEW-F03**：required max_subscriptions_per_session、attach reservation、RESOURCE_EXHAUSTED error、release 路径、derived bounds 均已冻结。
4. **CODEX-REREVIEW-F04**：唯一三步 primary-dimension 算法、四组 exact fixtures 均已冻结。

adversarial search 未发现新竞态、双 buffer、owner drift、过度承诺、遗漏实施范围或可实施项被留 residual。

设计已达到 code-generation-ready 状态，可以交给 implementation agent。Controller 接受的旧总控行冲突由 Controller 在 implementation gate 前裁决，不进入本设计 residual。

## Validation

- stale wording scan：旧 conditional multi-watcher / 单-watcher分支、旧 item-first overflow 规则、旧 terminal/failure 松散 slot、只含 items / bytes 的 policy 与 batch 扣账表述均无命中。
- frozen-decision scan：F01 的 closed union / generation loop / eager attach，F02 的 single transfer / in-flight accounting，F03 的 required cap / typed error / release / derived bound，F04 的三步算法 / 四组 exact fixtures 均在 design truth、原设计记录与 fix mapping 对齐。
- `git diff --check`：pass（tracked diff 仅为 `docs/host/design.md`）。
- changed-file boundary：本 Agent 只新增本 artifact；未修改设计、代码、总控、README、测试或既有 review / fix artifact。
- 本 gate 不运行测试或 pyright：没有代码修改，且当前 gate 明确只要求设计全文扫描与 diff whitespace validation。
