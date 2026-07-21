# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Design Re-review Fix（Codex）

## Gate metadata

- Work unit：`WU-CLI-SMOKE-01-R1` final-closeout design correction。
- Gate：phaseflow 第二轮 design fix gate。
- Date：2026-07-21。
- Agent：AgentCodex。
- Design truth：`docs/host/design.md`。
- Revised design record：`docs/reviews/wu-transient-delivery-ownership-design-codex.md`。
- Re-review input：`docs/reviews/wu-transient-delivery-ownership-design-rereview-codex.md`。
- Controller decision：接受 `CODEX-REREVIEW-F01` 至 `F04`；MiMo / DS 的 PASS 不覆盖这些直接反例。
- Scope：只修订 design truth、原设计记录并新增本 mapping；不修改生产代码、测试、总控、既有 review artifact，不 commit。
- Decision：`fixed-ready-for-second-re-review`。

## First-principles correction

修复动机成立，严重性没有被高估。二轮 finding 都位于语义 owner boundary，而不是可由测试夹具或下游 fallback 补偿的问题：

- Service 删除 relay 后，terminal、delivery interruption、normal EOF 与 callback failure 没有同一个完成通道，startup 又要跨多个 target 复用 watcher；若不冻结唯一 result owner，会出现等待挂死、task exception 第二通道或跨 generation 丢事件。
- Host 当前 batch drain 把一批事件从 queue accounting 中移出，却在 async generator 多次 `yield` 期间继续保留；这直接破坏单订阅 items / bytes bound。
- 当前代码和 public tests 已证明同一 Session 支持多个 watcher；不冻结 admission cap，Host retained budget 与同步 fanout仍无可推导上界。
- overflow public detail 是 closed typed contract；single-event oversized 与 item-full 同时命中时必须有唯一优先顺序。

正确 owner 分别是 Service watch runtime 的 observation/coordinator、Host Session Event Delivery subscription 与其 per-Session admission。Engine ingest、Run / Attempt、EventLog、Outbox 与 renderer owner 均不需要改变。

## Finding -> fix mapping

| Finding | Root cause | Design truth 修复 | 原设计记录修复 | 状态 |
| --- | --- | --- | --- | --- |
| `CODEX-REREVIEW-F01` | sole consumer 没有覆盖 callback exception、normal EOF 与 startup target rebind 的唯一结果/状态机 | §4.2 eager attach；§4.5 closed observation union、sole first-commit、fatal sticky、generation ack/rebind、same-tick arbitration 与 cleanup；§4.6 barrier scope | Public interface、Ownership、State 与 lifecycle、Implementation WU scope、Review Target | `accepted-fixed` |
| `CODEX-REREVIEW-F02` | `drain_nowait()` batch 在 mailbox accounting 外形成第二 retained buffer | §4.2 禁止 batch、只允许单项 transfer；§4.3 mailbox + in-flight retained accounting；§4.4 lifecycle bound；§4.6 barrier scope | Handoff、Byte accounting、Aggregate resource boundary、Implementation WU scope | `accepted-fixed` |
| `CODEX-REREVIEW-F03` | 已知 multi-watcher 没有 attach admission / aggregate public contract | §4.2 required cap；§4.4 reservation、专属 error、release 与 cap 乘积；public API error/detail；§4.6 / §16 scope | Public interface、Ownership、Aggregate resource boundary、Future scope / non-goals | `accepted-fixed` |
| `CODEX-REREVIEW-F04` | single-event oversized 与 item/cumulative bound 的 primary dimension 规则冲突 | §4.3 唯一三步顺序；§4.6 四组 exact fixtures | Byte accounting、Implementation WU scope、Review Target | `accepted-fixed` |

## CODEX-REREVIEW-F01 closure

### 唯一 Service observation result

`ServiceObservationResult` 冻结为容量一、带单调正整数 `target_generation` 的 closed union，至少包含：

```text
TARGET_TERMINAL(target_generation, terminal identity + result)
DELIVERY_INTERRUPTED(target_generation, typed Host delivery error)
ITERATOR_ENDED(target_generation)
CALLBACK_FAILED(target_generation, callback kind + original failure)
ITERATOR_FAILED(target_generation, typed/public iterator failure)
```

- sole consumer 是全部 outcome 的唯一 first-commit owner。
- task handle 只用于 lifecycle await；`task.exception()`、done callback、额外 Future、queue item 或 exception callback 都不得成为第二语义通道。
- normal `StopAsyncIteration` / Host close 必须 commit `ITERATOR_ENDED`，不能静默结束。
- callback exception 必须 commit `CALLBACK_FAILED`，终止 watcher并在 cleanup 后原样传播 helper caller；不得改写成 Host error、`DELIVERY_INTERRUPTED` 或 Host outage。
- `DELIVERY_INTERRUPTED`、`ITERATOR_ENDED`、`CALLBACK_FAILED`、`ITERATOR_FAILED` 均为 sticky fatal outcome；只有 `TARGET_TERMINAL` 可由 startup ack 后复用 watcher。

### target generation handshake

状态机冻结为：

```text
DETACHED -> ATTACHED_UNBOUND
ATTACHED_UNBOUND -- bind(g, target) + resume --> CONSUMING(g)
CONSUMING(g) -- sole-consumer first-commit --> RESULT_READY(g)
RESULT_READY(g) -- consume/ack terminal(g), clear slot --> ATTACHED_UNBOUND
ATTACHED_UNBOUND -- bind(g+1, target) + resume --> CONSUMING(g+1)
RESULT_READY(g) -- fatal or helper complete --> STOPPING -> CLOSED
```

- terminal first-commit 后 consumer 在下一次 `anext()` 前暂停。
- coordinator 必须按 `consume/ack g -> clear slot -> ATTACHED_UNBOUND -> bind g+1 -> resume` 顺序执行。
- commit 同时校验 generation 与 target id；旧 generation 不得写新 slot。
- 未绑定时 consumer 不 `anext()`；事件只留 Host mailbox，不在 Service 预读或缓存。
- stop / terminal / failure 同拍由 slot first-commit 仲裁：result 已取得且 slot 空则先 commit；stop 先被观察且尚无 result 则停止读取；slot 已占用时 cleanup 与迟到 signal 不得覆盖。

### attach 与 cleanup

- `watch_session_events(...)` 在返回 iterator 前完成 reservation、fanout attach 与 durable cursor attach request linearization；首次 `anext()` 不做 lazy attach。
- submit / cancel mutation 只能在 eager attach、sole consumer 建立及 target binding 所需前置条件满足后发出。
- cleanup 固定 stop/cancel consumer、await 并确认无 active `anext()`、`aclose()` iterator，最后在 caller 已消费语义后释放 slot；never-started 也走同一路径。

### Required barrier scope

callback throw、normal EOF / Host close、stop / terminal / failure 同拍、slot occupied cleanup、A terminal 后 B 先 promotion、旧 generation 迟到写入、fatal sticky 与 cleanup 后无 active `anext()` 都是 owner-level exact acceptance。

## CODEX-REREVIEW-F02 closure

### 单项 transfer 与统一 retained accounting

- transient subscription 只允许单项 pop / transfer；显式删除 `drain_nowait()` 及所有返回 `list` / `tuple` / `deque` batch 的 API 与测试假设。
- pop 只把 entry 从 mailbox 移到唯一 in-flight，不扣减 retained items / bytes。
- iterator `yield` 后，generator 下次恢复或 cleanup 前，Host 仍保留当前 in-flight 引用，因此继续计入同一 budget。
- yield 恢复 / cleanup 清除 Host 引用时才按 entry 保存 size 扣减；caller 在 generator 外继续保留的引用不属于 Host retention。
- publisher prospective accounting 始终读取 mailbox + in-flight retained totals，因此单 subscription Host-owned retention 不超过 policy。

### Aggregate interaction

overflowed subscription 在 prefix / in-flight 未清零时仍占 per-Session reservation；最终 error cleanup / `aclose()` 转 `DETACHED` 后才释放。这样新 attach 不会让同一 Session 的 Host-owned retained budget短暂超过 cap 乘积。

### Required barrier scope

iterator 取得首项并停在 yield 后继续 publish，必须证明：in-flight 仍占 items / bytes；mailbox 只能使用剩余 budget；不存在独立 batch container；overflow / high-watermark 与真实 retained state 一致。

## CODEX-REREVIEW-F03 closure

### Frozen multi-watcher policy

multi-watcher 已由当前 Session -> subscription set、双 watcher terminal test 与双 watcher transient test裁决为 public contract，不再保留单-watcher 替代分支。

`HostSessionEventDeliveryPolicy` 的 required 字段固定为三个非 bool 正整数：

```text
transient_mailbox_max_items
transient_mailbox_max_bytes
max_subscriptions_per_session
```

runtime composer / operator 是 opener-wide effective value owner；ConfigLoader 只解析 typed config，Service assembly 一对一映射，Host / Service 不提供 fallback，Run / UI / subscription 不覆盖。

### Attach reservation

- Session Event Delivery 在 opener owner loop 内按 Session 执行 check + reserve。
- prospective count 为 cap+1 时，在任何 subscription mailbox、durable cursor future / request 或 per-watch task allocation前 fail closed。
- 拒绝不驱逐、不 detach、不缩容或改变既有 watcher；不同 Session 独立计数。
- partial attach failure、`aclose()`、never-started、overflow 最终 detach、iterator error / EOF 与 Host close 都在 owner loop 幂等释放 reservation。
- overflow 从 fanout 排除到 retained prefix / in-flight cleanup 结束期间仍占 reservation。

### Public attach rejection contract

```text
HostApiError(
  code=HostApiErrorCode.RESOURCE_EXHAUSTED,
  retryable=true,
  detail=HostSessionEventAdmissionDetail(
    reason=HostSessionEventAdmissionReason.SESSION_SUBSCRIPTION_LIMIT_REACHED,
  ),
)
```

- `HostApiErrorCode.RESOURCE_EXHAUSTED = "resource_exhausted"`。
- `HostSessionEventAdmissionReason.SESSION_SUBSCRIPTION_LIMIT_REACHED = "session_subscription_limit_reached"`。
- owner 是 Session Event Delivery admission；message 不供 consumer 分支。
- `retryable=true` 只表示 reservation 释放后可能成功，不表示 Host execution unavailable，也不授权 tight-loop retry。

### Derived bounds and tests

- 每 Session retained logical item / byte upper bound 分别为 `cap × per-subscription item budget` 与 `cap × per-subscription byte budget`。
- 每 Session同步 fanout watcher upper bound 为 cap。
- generator 外 caller retention、精确 Python heap 与跨 Session Host 总内存不在该乘积承诺内。
- tests 覆盖 cap-1 / cap / cap+1、并发 attach、拒绝零分配、既有 watcher不受影响、detach 后再 admission、不同 Session 隔离和全部 release path。

## CODEX-REREVIEW-F04 closure

public `limit_dimension` 的唯一 primary-dimension 算法固定为：

1. 新 event 自身 `delivery_size_bytes > transient_mailbox_max_bytes`：`PAYLOAD_BYTES`。
2. 否则 `retained_items + 1 > transient_mailbox_max_items`：`ITEM_COUNT`。
3. 否则 `retained_bytes + delivery_size_bytes > transient_mailbox_max_bytes`：`PAYLOAD_BYTES`。

item-full + oversized 因第一步优先，固定 `PAYLOAD_BYTES`。metrics 可以记录同一 offer 命中的全部维度，但 public detail 只能携带一个 primary dimension。

四组 exact fixtures 固定为：

1. 空 mailbox + oversized event -> `PAYLOAD_BYTES`。
2. item-full + individually small event -> `ITEM_COUNT`。
3. item 尚有余量 + individually fitting event，但 prospective cumulative bytes 超限 -> `PAYLOAD_BYTES`。
4. item-full + oversized event -> `PAYLOAD_BYTES`。

## Cross-cutting resolution

- watcher topology 已裁决为 multi-watcher contract；不再作为 open question、实施审计或 residual。
- 旧 `WU-HOST-TRANSIENT-CAPACITY-01` 与 `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 总控行的登记冲突留给 Phaseflow Controller；设计不保留 residual、fallback、兼容 shim 或双 owner。
- future implementation WU 唯一可测量裁决的是三个 packaged 数值（items / bytes / max-subscriptions）、logical-byte 到 Python heap safety margin 与低基数 metrics；字段、算法、error owner、retryability、multi-watcher topology 与 release lifecycle 均不可重开。
- 本 gate 不修改 Engine contract、durable/transient 边界、Run / Attempt / EventLog / Outbox owner，也不实施生产代码或测试。

## Validation

- stale wording scan：旧 conditional multi-watcher / 单-watcher 分支、旧 item-first overflow 规则、旧 terminal/failure 松散 slot、只含 items / bytes 的 policy 与 batch 扣账表述均无命中。
- frozen-decision scan：F01 的 closed union / generation loop / eager attach，F02 的 single transfer / in-flight accounting，F03 的 required cap / typed error / release / derived bound，F04 的三步算法 / 四组 exact fixtures 均在 design truth、原设计记录与本 mapping 对齐。
- `git diff --check`：pass（tracked diff 仅为 `docs/host/design.md`）。
- 原设计记录与本 artifact 的 `git diff --no-index --check /dev/null <file>`：均无 whitespace diagnostic；按 no-index 的“文件内容不同”语义返回 `1`。
- scope：`git diff --name-only` 的 tracked 输出只有 `docs/host/design.md`；本 Agent 未修改生产代码、测试、总控、README 或既有 review / fix artifact。
- 本 gate 不运行测试或 pyright：没有生产代码 / 测试修改，且用户明确限定只修设计。

## Open questions

没有阻塞开放问题。
