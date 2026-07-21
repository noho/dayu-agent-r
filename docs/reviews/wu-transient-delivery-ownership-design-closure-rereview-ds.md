# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Design Closure Re-Review（DS）

## Gate metadata

- 审查时间：2026-07-21 15:58:40 CST（+0800，来自本机系统时钟）。
- Gate：phaseflow design closure re-review gate。
- Reviewer：AgentDS，使用 `planreview` adversarial review 方法。
- 审查结论：**PASS**。
- Material findings：**0**。
- 未归属 residual：**0**。
- 修改边界：只新增本 artifact；未修改设计、代码、总控、README、测试或既有 artifact。

## Reviewed target and scope

本次只读以下指定输入做 closure re-review：

- `docs/host/design.md`；
- `docs/engine/design.md`；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`（原设计记录）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-rereview-codex.md`（Codex 最终 re-review，提出 F01/F02）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-rereview-fix-codex.md`（Codex 第三轮 design fix）。

核对必要代码事实：

- `dayu/host/transient_delta.py`：确认旧 `_TRANSIENT_WATCH_BUFFER_CAPACITY`、`drain_nowait()`、`_slow_consumer_error()` 与 `HostUnavailableDetail` overflow 路由存在（设计授权删除）；
- `dayu/host/open_host.py:985,1000,1012`：确认三处 transient-first `drain_nowait()` 调用形成 B-before-A-terminal 风险（设计已冻结新算法替代）；
- `dayu/host/engine_ingest.py:2765-2789`：确认 `_with_terminal_promotion_retry` 在 terminal closeout 后立即调用 `wake_queue_promotion`（设计已重新线性化该顺序）；
- `dayu/host/dispatch.py:1118-1138,2921-2953`：确认 promotion 由独立 `_promotion_queue` / `_promotion_drain_loop` task 推进（证明 B publish 早于慢 watcher 读取 A terminal 可达）；
- `dayu/service/entrypoint_runtime.py:76,501,1027`：确认 Service 存在 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY` 常量和 `_WatchAndWaitRuntime.queue` relay queue（设计授权删除）；
- `dayu/host/api.py:1367-1394`：确认 `HostUnavailableDetail` 和旧 `HostApiErrorDetail` union（设计将新增 delivery/admission detail types）；
- `docs/engine/design.md:28-38,513`：确认 Engine 只拥有本次 generator 顺序，不提供 Host cursor、fanout、EventLog 或 replay（设计未修改 Engine contract）。

## First-principles assessment

本轮 closure re-review 的动机是验证 Codex 最终 re-review 提出的 `CODEX-FINAL-REREVIEW-F01` 与 `F02` 是否已在第三轮 design fix 中真实关闭，并确认修复未引入新的结构性风险。

修改动机成立。F01 的 Host transient-first drain 与 terminal-closeout 后立即 promotion wake 共同构成可达的 B-before-A-terminal 竞态；F02 的 "至少包括" 成员列表与二选一 recovery 确实会让 implementation agent 重新设计错误语义。第三轮 fix 选择的最小路径——Host 增加 per-Session O(1) terminal watermark 作为 runtime handoff control scalar，Service 冻结 exact-five result 与唯一 cleanup/caller 仲裁——没有增加 durable schema、第三事件类型、跨域 cursor、Service event cache、terminal marker queue 或新的 recovery 系统，是最小正确修复。

## CODEX-FINAL-REREVIEW-F01 closure verification

逐项验证 F01 的 terminal cutoff 与 handoff contract：

### 1. per-Session O(1) terminal watermark

**PASS。** `docs/host/design.md:360` 明确："Session Event Delivery 为每个 Session 只维护一个 O(1)、单调不减的 `committed_terminal_event_sequence_high_watermark`；它记录本 runtime 已完成 EventLog commit 的最新 terminal `event_sequence`，不是 terminal id 集合、terminal marker queue 或业务事实副本。"

直接证据：该 scalar 只保存最新 committed terminal 的 `event_sequence` 值，O(1) 空间。同时 `:364` 补充："每次 terminal `yield` 都停止继续扫描，不复制或保存后续 terminal id / marker"。`docs/reviews/wu-transient-delivery-ownership-design-final-rereview-fix-codex.md:27` 同样冻结："只保存本 runtime最新 committed terminal `event_sequence`，不是 terminal id set / marker queue"。

### 2. attach snapshot

**PASS。** `docs/host/design.md:362` 明确："eager attach 必须在 owner-loop attach linearization 中形成不可拆分的 `(durable_start_cursor, committed_terminal_event_sequence_high_watermark)` 快照"。首次 `anext()` 不得重新选择 watermark baseline 或 lazy attach。

直接证据：`:370` 补充 watch 调用 "只有 per-Session admission reservation 已取得、subscription 已进入 fanout owner，并且 durable start-cursor request 的线性化位置与当时的 per-Session terminal watermark 已作为同一个 attach snapshot 记录后才可返回 iterator"。修复记录 `:38` 一致。

### 3. commit → terminal-ready wake → promotion → B publish

**PASS。** `docs/host/design.md:360` 冻结完整线性化顺序："EventLog terminal transaction commit 成功；commit continuation 回到 opener owner loop 后，在同一无 `await` 顺序中同步把该 Session watermark 推进到 terminal `event_sequence` 并 level-trigger该 Session attached subscriptions 的 terminal-ready wake；watermark / delivery wake 完成后才允许发出 queue-promotion wake；B 的 promotion、dispatch 与 transient publish 只能位于该 promotion wake 之后。"

直接证据：该顺序明确保证 watermark advance 发生在 promotion wake 之前，且 watermark advance 与 subscription terminal-ready wake 之间不得被 `await` 或其他操作穿过。修复记录 `:32-34` 同样冻结该顺序。同时明确 "watermark 推进不等待 watcher，不暂停 promotion、Agent 或 Engine"——没有引入 promotion 背压。

### 4. pop 前 bounded durable catch-up

**PASS。** `docs/host/design.md:364` 明确："每次准备从 transient mailbox pop 前，都必须读取该 Session 的 latest watermark。若 subscription durable cursor 落后 watermark，merge 禁止 pop transient，必须先按 bounded EventLog pages 追赶；page size 只约束单页读取，不是正确性停止预算，必须追到已观察的 watermark、遇到 public durable read failure，或因当前 terminal `yield` 暂停。"

直接证据：catch-up 是 bounded-page 但有界只约束单页大小，不是 correctness 停止条件。修复记录 `:39` 一致："page size只限制单页，不是 correctness停止预算"。

### 5. A prefix / terminal / B handoff

**PASS。** `docs/host/design.md:364` 明确完整算法：
- 遇 terminal A 时建立至多一个 current-terminal fence；
- 只从 counted mailbox 头部逐项 pop / yield `run_id=A` 的 pre-terminal transient prefix；
- 首个不同 Run 的 entry 必须原位保留在同一个 mailbox，继续计入 mailbox + in-flight budget，不得 pop；
- A prefix 清空或 mailbox 头部首次不是 A 后，merge `yield` durable terminal A；
- 该 `yield` 悬停使 Service 有机会 first-commit、ack / clear 并 rebind；
- 只有下一次 `anext()` 恢复 merge 后才可释放 A fence 并交付 B。

直接证据：`:476` 从 Service 侧确认 "Host terminal handoff barrier保证 A terminal `yield` 后必须等到这个下一次 `anext()` 才可能 pop B，因此 Service 不需要也不得缓存 B"。修复记录 `:40-42` 一致。

### 6. 多 terminal scalar

**PASS。** `docs/host/design.md:364` 明确："若慢 consumer 期间已经提交 A、B 或更多 terminal，merge 仍只依赖 EventLog `event_sequence` 与一个 latest watermark scalar逐个发现；每次 terminal `yield` 都停止继续扫描，不复制或保存后续 terminal id / marker，未消费的 page suffix 不推进 cursor并在下次读取时从 EventLog 重新发现。"

直接证据：多 terminal 场景只通过 EventLog 顺序和单个 latest scalar 逐个发现，不需要也不会建立 marker queue。修复记录 `:42` 一致。

### 7. 确认未引入跨域总序

**PASS。** `docs/host/design.md:360` 明确："terminal handoff 只增加 runtime control barrier，不增加第三类 event、跨域总序或可持久化 cursor。" `:365` 补充："其它 durable progress 与 transient delta 之间不承诺可离线重建的总序；消费者不得把迭代器到达顺序或 watermark 持久化成跨平面 cursor。"

直接证据：watermark 仅仅是 runtime control scalar，不是 durable state，不建立 durable/transient 可比较总序。修复记录 `:43` 一致："watermark / barrier只约束 terminal handoff，不建立 durable / transient可比较总序，不产生可持久化 cursor"。

### 8. 确认未引入 promotion 背压

**PASS。** `docs/host/design.md:360` 明确："watermark 推进不等待 watcher，不暂停 promotion、Agent 或 Engine；B 仍可运行并把 delta 发布到同一个 Host subscription mailbox。"

直接证据：watermark advance 和 terminal-ready wake 在 owner loop 的无 `await` 顺序中同步完成，之后才发 promotion wake，整个过程不等待 watcher。

### 9. 确认未引入 Service B buffer

**PASS。** `docs/host/design.md:476` 明确："B event只保留在 Host counted mailbox，Service 不缓存、转存或预读。Host terminal handoff barrier保证 A terminal `yield` 后必须等到这个下一次 `anext()` 才可能 pop B，因此 Service 不需要也不得缓存 B。"

直接证据：Service 的 `CONSUMING(g)` 在 first-commit 后立即进入 `RESULT_READY(g)` 并暂停 `anext()`；未绑定期间 consumer 不调用 `anext()`，B event 只留在 Host mailbox。

### 10. 确认未引入 unbounded marker

**PASS。** `docs/host/design.md:360` 明确 watermark "不是 terminal id 集合、terminal marker queue 或业务事实副本"。`:364` 明确："每次 terminal `yield` 都停止继续扫描，不复制或保存后续 terminal id / marker"。

直接证据：最多保存一个 O(1) latest scalar，每个 terminal handoff 后停止扫描，不累积 marker。

### 11. 确认未引入 owner drift

**PASS。** `docs/host/design.md:346` 重新声明三层 delta owner 边界：Engine 只拥有单次 generator 顺序；Host EngineEvent ingest 拥有 candidate shape / identity / late-state validation；Session Event Delivery 拥有 publication / mailbox / admission / overflow / detach；runtime composer / operator 拥有 opener-wide policy；Service 只拥有展示选择、callback 适配、唯一 observation-result slot 与本地 degraded recovery。`:358` 再次确认 ingest 端口 "只承诺同步、non-blocking、non-throwing handoff，不读取 watcher 状态，不选择 mailbox 容量或 overflow 动作"。

直接证据：`docs/engine/design.md:28-38,513` 确认 Engine 不提供 Host cursor、fanout、EventLog 或 replay——Engine owner 未发生变化。修复记录 `:29` 确认 "没有增加 durable schema、第三事件类型、跨域 cursor、Service event cache、terminal marker queue或新的 recovery系统"。

## CODEX-FINAL-REREVIEW-F02 closure verification

逐项验证 F02 的 exact-five disposition 与 cleanup precedence：

### 1. exact-five ServiceObservationResult

**PASS。** `docs/host/design.md:417-425` 明确："它恰好只有以下五个 members，不得新增隐式 member、catch-all outcome 或兼容别名"：

```
TARGET_TERMINAL(target_generation, terminal identity + result)
DELIVERY_INTERRUPTED(target_generation, typed Host delivery error)
ITERATOR_ENDED(target_generation)
CALLBACK_FAILED(target_generation, callback kind + original failure)
ITERATOR_FAILED(target_generation, typed/public iterator failure)
```

直接证据：不再是 "至少包括"，而是 "恰好只有" 五个。修复记录 `:51-57` 一致。

### 2. 五类唯一 disposition

**PASS。** `docs/host/design.md:431-437` 为每个 member 冻结唯一 caller disposition：

| Member | 唯一 disposition |
|---|---|
| `TARGET_TERMINAL` | 返回携带的 terminal result，不做 durable 重算 |
| `DELIVERY_INTERRUPTED` | 只走 `get_run` / Outbox durable recovery；成功返回 terminal，失败 `raise recovery_error from delivery_error` |
| `ITERATOR_ENDED` | 固定抛 `EntrypointRuntimeError("session_event_iterator_ended_before_terminal")`，stable reason，不 recovery |
| `CALLBACK_FAILED` | 原样重抛 callback original exception |
| `ITERATOR_FAILED` | `HostApiError` / `HostClosedError` 原样抛；其它 wrap 为 `EntrypointRuntimeError("session_event_iterator_failed_before_terminal") from original` |

直接证据：不再有 "fail closed 或走 recovery" 二选一。每个 member 的路径是唯一且穷举的。修复记录 `:61-68` 一致。

### 3. stop / late commit 仲裁

**PASS。** `docs/host/design.md:439` 明确："slot first-commit 一旦成功就是 primary，任何 `aclose()` failure、stop、迟到 callback、late iterator completion 或 task completion都不得覆盖；caller cancellation 或 coordinator stop 在 slot 仍为空时先取得仲裁权后，后续 slot commit 必须失败。"

直接证据：`:478` 补充完整仲裁逻辑——consumer 已取得 result 且 slot 为空时先 commit；stop 先取得空 slot 仲裁权时 consumer 不再读取且 late commit 无效；slot 已占用时任何 cleanup、迟到 signal 或 task completion 都不得覆盖。修复记录 `:73` 一致。

### 4. cleanup double-failure precedence

**PASS。** `docs/host/design.md:441-443` 完整覆盖所有 double-failure 场景：

- exception / caller cancellation 已是 primary 且 close 也失败：`raise primary from cleanup_error`；non-public iterator double failure 保留三层 chain：`EntrypointRuntimeError` -> original iterator error -> cleanup error
- delivery recovery 失败：recovery exception 为 top-level，delivery error 为直接 cause；若 close 也失败，cleanup error 只作为 delivery error 的 nested cause
- `TARGET_TERMINAL` 或 delivery recovery 已成功而 close 失败：仍返回 terminal
- slot 为空且无 caller cancellation：close failure 是唯一 caller failure

直接证据：`:447-455` 的七组 exact acceptance 表为每个场景冻结唯一预期，修复记录 `:82-91` 一致。

### 5. 去敏 sanitized diagnostic

**PASS。** `docs/host/design.md:442` 完整定义：

- `kind=WATCHER_DIAGNOSTIC`、`status=FAILED`、`severity=WARNING`
- `run_id=None`、`event_sequence=None`
- `dedupe_key="entrypoint_watcher_cleanup_failed"`
- title=`运行事件流清理失败`
- summary=`已保留终态结果，但运行事件观察器清理失败。`
- tool / counts 字段均为 `None`
- 不得包含 cleanup exception 类型、message、identity、payload 或 traceback
- diagnostic callback 自身失败必须被吞掉，不能改变 terminal primary

直接证据：所有可能泄露 cleanup 异常信息的字段都被显式排除。修复记录 `:77` 一致。

## F02-F04 closure 复核

### CODEX-REREVIEW-F02（batch / in-flight accounting）

**仍关闭。** `docs/host/design.md:372` 禁止 `drain_nowait()` 及任何返回 `list` / `tuple` / `deque` batch 的 API，只允许单项 pop / transfer。`:382` 明确 mailbox -> in-flight 是 transfer 不扣账，yield 恢复 / cleanup 清除 Host 引用时才按 entry size 精确扣减；publisher prospective accounting 始终使用 mailbox + in-flight retained totals。修复记录 `:51` 结论不变。无新证据威胁该 closure。

### CODEX-REREVIEW-F03（per-Session admission / reservation）

**仍关闭。** `docs/host/design.md:407-409` 冻结 required `max_subscriptions_per_session`、owner-loop check+reserve 先于 mailbox/cursor/task allocation、专属 `RESOURCE_EXHAUSTED` admission error（`retryable=true`）、全部 release 路径（partial attach failure / `aclose()` / never-started / overflow detach / error / EOF / Host close）、overflow 期间仍占 reservation、不同 Session 隔离、derived logical upper bound。修复记录 `:52` 结论不变。无新证据威胁该 closure。

### CODEX-REREVIEW-F04（overflow primary dimension）

**仍关闭。** `docs/host/design.md:384` 固定唯一三步算法：single-event `delivery_size_bytes > max_bytes` → `PAYLOAD_BYTES`；`retained_items + 1 > max_items` → `ITEM_COUNT`；`retained_bytes + delivery_size_bytes > max_bytes` → `PAYLOAD_BYTES`。四组 exact fixtures 保持不变。修复记录 `:53` 结论不变。无新证据威胁该 closure。

## Verified closed design aspects（不重复列为 findings）

1. **Eager attach boundary**：reservation、fanout attach、durable cursor request 在返回前完成，首次 `anext()` 不做 lazy attach。`docs/host/design.md:362,370`。
2. **Architecture boundary**：Engine → ingest → Session Event Delivery → Service 单向依赖，无反向穿透。`docs/host/design.md:346,358`；`docs/engine/design.md:28-38,513`。
3. **Best practice / optimal solution**：typed public policy + logical byte helper + per-subscription isolation + 专属 typed error，比隐藏常量、双 queue 或 durable delta 更可测试且更小。
4. **Overcoupling / overengineering**：config view → Service assembly → Host typed policy 单向装配；watermark 是 Host 内部 control scalar，不提升为持久化事实；不需要新层或通用 broker。
5. **Public contract consistency**：`HostSessionEventIterator` Protocol、exact-five `ServiceObservationResult`、delivery / admission 专属 typed error、三个 required 正整数字段 policy 在设计真源、设计记录与 fix mapping 中一致。
6. **Single retention owner**：transient batch API、Service relay queue 与 task-exception queue item 均被明确删除；mailbox + 唯一 in-flight 共享 items / bytes budget；caller 外部引用被准确排除。
7. **Multi-watcher topology**：已由现行代码与 public tests 裁决，设计未重新审计为单 watcher；`max_subscriptions_per_session` 做 attach-time reservation；cap+1 fail closed。
8. **Byte accounting**：唯一 deterministic `delivery_size_bytes` helper；每 event 一次计算后 fanout 复用；string traversal 边界明确；不宣称等于 Python heap resident bytes。
9. **Ordering**：durable `event_sequence` 与 transient `runtime_sequence` 保持两个不可比较 domain；watermark 只是 runtime merge control scalar。
10. **Overflow / degraded**：typed disconnect only；禁止 silent drop-and-continue；overflow/drop/degraded/disconnect 不写 EventLog、不改变 Run/Attempt/terminal。

## Material findings

**0**。本轮 closure re-review 未发现任何 material finding。

`CODEX-FINAL-REREVIEW-F01` 的 terminal cutoff 已在 Host Session Event Delivery / iterator merge owner 完整冻结：per-Session O(1) watermark、commit → watermark + subscription terminal-ready wake → promotion wake → B publish 的线性化顺序、pop 前 bounded-page catch-up、same-Run prefix / terminal / B handoff 算法、多 terminal 通过 EventLog 顺序 + latest scalar 逐个发现，均给出唯一可实施规则。未引入跨域总序、promotion 背压、Service B buffer、unbounded marker 或 owner drift。

`CODEX-FINAL-REREVIEW-F02` 的 fatal disposition 与 cleanup precedence 已在 Service watch-runtime owner 完整冻结：exact-five member list（不含 "至少"）、五类唯一 caller disposition、stop/cancellation first arbitration、七组 exact double-failure acceptance（含 exception chaining、primary preservation、sanitized secondary diagnostic）。未引入 task-exception side channel、兼容别名或二选一 recovery。

F02（batch/in-flight accounting）、F03（per-Session admission）、F04（overflow primary dimension）的已有 closure 在本次修订后仍然成立，无新证据威胁。

## Residual ownership

| Residual / prerequisite | Owner | Tracking destination | Gate treatment |
|---|---|---|---|
| packaged `transient_mailbox_max_items` / `transient_mailbox_max_bytes` / `max_subscriptions_per_session` 数值 | runtime composer / operator + Session Event Delivery implementation owner | future implementation WU benchmark / SLO evidence | 合法 measurement residual；字段、算法、error contract 已冻结 |
| logical UTF-8 byte budget 到 Python heap 的 safety margin | Session Event Delivery implementation owner | future implementation plan stress/benchmark | 合法 measurement residual |
| 低基数 metrics 字段 / 采样 | Session Event Delivery implementation owner | future implementation WU observability design | 合法 measurement residual |
| 旧总控 `WU-HOST-TRANSIENT-CAPACITY-01` / `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 行修订 | Phaseflow Controller / control-doc owner | 本 gate 后的 Controller adjudication | 按用户明确边界处理；尚未写回不计设计 finding |

所有已识别 residual 均有明确 owner 与 tracking destination。**未归属 residual：0**。

## Final conclusion

**Verdict：PASS。**

**Material findings：0。**

`CODEX-FINAL-REREVIEW-F01` 与 `F02` 已在第三轮 design fix 中真实关闭。Host terminal cutoff 的完整算法（O(1) watermark、commit → wake → publish 线性化、pop 前 bounded catch-up、same-Run prefix / terminal yield / B handoff、多 terminal 通过 single scalar 逐个发现）已冻结为可实施的 owner contract。Service exact-five disposition、五类唯一 caller outcome、stop/cancellation arbitration、cleanup double-failure precedence 与 sanitized diagnostic 已穷举，不再有 "至少" 或 "二选一" 的模糊空间。未引入跨域总序、promotion 背压、Service B buffer、unbounded marker 或 owner drift。

`CODEX-REREVIEW-F02`（batch/in-flight）、`F03`（admission）、`F04`（overflow primary dimension）的已有 closure 在本次修订后仍然成立。

设计已达到可直接交给 implementation agent 的程度。剩余测量项（packaged 数值、heap margin、低基数 metrics）均有明确 owner 与 tracking destination，不阻塞 implementation gate。
