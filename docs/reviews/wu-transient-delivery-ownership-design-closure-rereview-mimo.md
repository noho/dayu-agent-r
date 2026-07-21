# WU-CLI-SMOKE-01-R1 Transient Delivery Ownership Design Closure Re-review（MiMo）

## Gate metadata

- 审查时间：2026-07-21 15:59:37 CST（+0800，来自本机系统时钟）。
- Gate：phaseflow design closure re-review gate。
- Reviewer：AgentMiMo，使用 `planreview` adversarial review 方法。
- 审查结论：**PASS**。
- Blocking findings：**0**。
- Material findings：**0**。
- 未归属 residual：**0**。
- 修改边界：只新增本 artifact；未修改设计、代码、总控、README、测试或既有 artifact。

## Reviewed target and scope

本次只读审查以下指定输入：

- `docs/host/design.md`（§4.1–§4.6 terminal handoff、Service observation result、cleanup precedence 相关章节）；
- `docs/engine/design.md`（§1 边界与职责、§1.1 Stream 术语边界，确认 Engine contract 未被修改）；
- `docs/reviews/wu-transient-delivery-ownership-design-codex.md`（原 design correction）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-rereview-codex.md`（CODEX-FINAL-REREVIEW-F01/F02）；
- `docs/reviews/wu-transient-delivery-ownership-design-final-rereview-fix-codex.md`（第三轮 fix）。

为验证设计是否已关闭 F01/F02 所述风险，另只读核对了 `docs/host/design.md` 中 §4.1 terminal handoff、§4.5 Service 状态机、§4.6 acceptance 等关键段落的文字。代码只用于证明设计假设，不是本次 review 对象。按用户约束，总控旧行由 Controller 在本 gate 后修订；尚未写回总控本身不计为 finding。

## First-principles assessment

修改动机成立，严重性没有被高估。第三轮 fix 正确地把 F01 的 Host terminal cutoff 和 F02 的 exact-five disposition / cleanup precedence 写入了 `docs/host/design.md` 的 owner 边界。Engine 仍只拥有单次 generator 顺序（`docs/engine/design.md:28-38`），没有发生 owner drift。

本轮验证目标是：(1) 逐项确认 F01/F02 的每个 closure point 已在 design truth 中冻结为可直接实施的唯一算法；(2) 确认未引入跨域总序、promotion 背压、Service B buffer、unbounded marker 或 owner drift；(3) 复核此前 F02–F04 closure 仍成立。

## CODEX-FINAL-REREVIEW-F01 逐项验证

| 验证项 | 结论 | design.md 定位 |
|---|---|---|
| per-Session O(1) terminal watermark | **已冻结** | §4.1 `:360`："Session Event Delivery 为每个 Session 只维护一个 O(1)、单调不减的 `committed_terminal_event_sequence_high_watermark`；它记录本 runtime 已完成 EventLog commit 的最新 terminal `event_sequence`，不是 terminal id 集合、terminal marker queue 或业务事实副本" |
| attach snapshot | **已冻结** | §4.1 `:362`："eager attach 必须在 owner-loop attach linearization 中形成不可拆分的 `(durable_start_cursor, committed_terminal_event_sequence_high_watermark)` 快照"；§4.2 `:370` 与 §4.6 `:499` 一致 |
| commit→terminal-ready wake→promotion→B publish | **已冻结** | §4.1 `:360`："EventLog terminal transaction commit 成功；commit continuation 回到 opener owner loop 后，在同一无 `await` 顺序中同步把该 Session watermark 推进到 terminal `event_sequence` 并 level-trigger该 Session attached subscriptions 的 terminal-ready wake；watermark / delivery wake 完成后才允许发出 queue-promotion wake；B 的 promotion、dispatch 与 transient publish 只能位于该 promotion wake 之后"；§4.4 `:411` 重复确认 |
| pop前 bounded durable catch-up | **已冻结** | §4.1 `:364`："iterator merge 每次准备从 transient mailbox pop 前，都必须读取该 Session 的 latest watermark。若 subscription durable cursor 落后 watermark，merge 禁止 pop transient，必须先按 bounded EventLog pages 追赶；page size 只约束单页读取，不是正确性停止预算" |
| A prefix / terminal / B handoff | **已冻结** | §4.1 `:364`："遇到 terminal A 时，merge 建立至多一个 current-terminal fence，只从 counted mailbox 头部逐项 pop / yield `run_id=A` 的 pre-terminal transient prefix；首个不同 Run 的 entry 必须原位保留在同一个 mailbox，继续计入 mailbox + in-flight budget，且不得 pop...A prefix 清空或 mailbox 头部首次不是 A 后，merge `yield` durable terminal A...只有下一次 `anext()` 恢复 merge 后才可释放 A fence 并交付 B"；§4.5 `:476` 确认 "Host terminal handoff barrier 保证 A terminal `yield` 后必须等到这个下一次 `anext()` 才可能 pop B，因此 Service 不需要也不得缓存 B" |
| 多 terminal scalar | **已冻结** | §4.1 `:364`："若慢 consumer 期间已经提交 A、B 或更多 terminal，merge 仍只依赖 EventLog `event_sequence` 与一个 latest watermark scalar 逐个发现；每次 terminal `yield` 都停止继续扫描，不复制或保存后续 terminal id / marker" |
| 不引入跨域总序 | **确认** | §4.1 `:360`："durable 与 transient 是两个 sequence domain，不定义可比较的全局 sequence。terminal handoff 只增加 runtime control barrier，不增加第三类 event、跨域总序或可持久化 cursor" |
| 不引入 promotion 背压 | **确认** | §4.1 `:360`："watermark 推进不等待 watcher，不暂停 promotion、Agent 或 Engine" |
| 不引入 Service B buffer | **确认** | §4.5 `:476`："未绑定期间 consumer 不调用 `anext()`；这段时间到达的 B event 只保留在 Host counted mailbox，Service 不缓存、转存或预读" |
| 不引入 unbounded marker | **确认** | §4.1 `:360`："不是 terminal id 集合、terminal marker queue 或业务事实副本"；§4.1 `:364`："不复制或保存后续 terminal id / marker" |

**F01 结论：已真实关闭。**

## CODEX-FINAL-REREVIEW-F02 逐项验证

| 验证项 | 结论 | design.md 定位 |
|---|---|---|
| exact-five `ServiceObservationResult` | **已冻结** | §4.5 `:417`："它恰好只有以下五个 members，不得新增隐式 member、catch-all outcome 或兼容别名"；`:419-425` 列出 `TARGET_TERMINAL`、`DELIVERY_INTERRUPTED`、`ITERATOR_ENDED`、`CALLBACK_FAILED`、`ITERATOR_FAILED` |
| 五类唯一 disposition | **已冻结** | §4.5 `:429-437` 表格：`TARGET_TERMINAL`→返回 terminal；`DELIVERY_INTERRUPTED`→`get_run`/Outbox recovery，`raise recovery_error from delivery_error`；`ITERATOR_ENDED`→`EntrypointRuntimeError("session_event_iterator_ended_before_terminal")`，不 recovery；`CALLBACK_FAILED`→原样重抛 callback original exception；`ITERATOR_FAILED`→public Host exception 原样抛 / 非 public stable wrap |
| stop / late commit | **已冻结** | §4.5 `:439`："slot first-commit 一旦成功就是 primary，任何 `aclose()` failure、stop、迟到 callback、late iterator completion 或 task completion 都不得覆盖"；`:478`："caller cancellation 或 coordinator stop 在 slot 仍为空时先取得仲裁权后，后续 slot commit 必须失败" |
| cleanup precedence | **已冻结** | §4.5 `:439`："coordinator 必须先停止并 await sole consumer、确认没有 active `anext()`，再恰好一次调用 public iterator `aclose()`；Host subscription reservation 的释放仍由 Host iterator / subscription `finally` 幂等保证" |
| double-failure precedence | **已冻结** | §4.5 `:441-443` 定义三类 double-failure 场景：(1) primary exception + `aclose()` failure→`raise primary from cleanup_error`，non-public 三层 chain；(2) terminal/recovery success + `aclose()` failure→仍返回 terminal + 去敏 diagnostic；(3) slot empty + `aclose()` failure→cleanup 是唯一 caller failure |
| 去敏 diagnostic | **已冻结** | §4.5 `:442`："kind=`WATCHER_DIAGNOSTIC`、status=`FAILED`、severity=`WARNING`、`run_id=None`、`event_sequence=None`、`dedupe_key='entrypoint_watcher_cleanup_failed'`、title=`运行事件流清理失败`、summary=`已保留终态结果，但运行事件观察器清理失败。`...不得包含 cleanup exception 类型、message、payload、Session / Run identity 或 traceback。diagnostic callback 自身失败必须被吞掉，不能改变 terminal primary" |
| 七组 exact acceptance | **已冻结** | §4.5 `:447-455` 表格完整覆盖 callback+close、EOF+close、iterator+close、terminal+close、delivery recovery success+close、slot empty+close、caller cancellation+close 七组场景 |

**F02 结论：已真实关闭。**

## 此前 F02–F04 closure 复核

| 原 finding | 本轮复核结论 | 证据 |
|---|---|---|
| CODEX-REREVIEW-F02（batch/in-flight accounting） | **仍关闭** | §4.2 `:372`："transient 读取接口必须是单项 pop / transfer；禁止 `drain_nowait()` 或任何返回 batch 的 API"；§4.3 `:382` 保持 mailbox + in-flight 统一 retained accounting |
| CODEX-REREVIEW-F03（multi-watcher admission） | **仍关闭** | §4.4 `:407-409` 保持 required cap、owner-loop reservation、typed rejection、幂等释放与 per-Session derived bound |
| CODEX-REREVIEW-F04（overflow primary dimension） | **仍关闭** | §4.3 `:384` 保持唯一三步算法：single-event bytes → item count → cumulative bytes；四组 fixtures 在 §4.6 `:506` acceptance 中 |

## 未引入的风险检查

| 风险维度 | 结论 |
|---|---|
| 跨域总序 | 未引入。§4.1 `:360` 明确 durable/transient 不可比较 |
| promotion 背压 | 未引入。§4.1 `:360` 明确 watermark 不等待 watcher |
| Service B buffer | 未引入。§4.5 `:476` 明确 Service 不缓存 B |
| unbounded marker | 未引入。§4.1 `:360,364` 明确不是 terminal id set / marker queue |
| owner drift | 未发生。Engine 仍只拥有 generator 顺序（`docs/engine/design.md:28-38`），Host Session Event Delivery 拥有 transient publication/retention/admission，Service 拥有 observation result slot |
| "至少包括"措辞 | 已消除。§4.5 `:417` 改为"恰好只有以下五个 members" |
| "fail closed 或 recovery"二选一 | 已消除。§4.5 `:435` 固定 `ITERATOR_ENDED` 不 recovery；`:434` 固定 `DELIVERY_INTERRUPTED` 只走 recovery |

## Residual ownership

| Residual | Owner | Tracking destination |
|---|---|---|
| 旧 `WU-HOST-TRANSIENT-CAPACITY-01` / `WU-SVC-ENTRYPOINT-RELAY-CAPACITY-01` 总控行修订 | Phaseflow Controller / control-doc owner | Controller adjudication |
| packaged items / bytes / max-subscriptions 数值 | runtime composer / operator + Session Event Delivery owner | future implementation WU |
| logical UTF-8 budget 到 Python heap safety margin | Session Event Delivery implementation owner | future implementation plan |
| 低基数 metrics | Session Event Delivery implementation owner | future implementation plan |

所有 residual 均有明确 owner 与 tracking destination。除 Controller 待写回总控和 measurement residual 外，可直接实施的 terminal cutoff、fatal disposition 与 cleanup precedence 已在 design truth 中冻结。

## Final conclusion

**Verdict：PASS。**

**Material findings：0。**

`CODEX-FINAL-REREVIEW-F01` 已真实关闭：Host per-Session O(1) watermark、atomic attach snapshot、commit→wake→promotion→B publish 线性化、pop前 bounded catch-up、A prefix / terminal / B handoff 与多 terminal scalar 逐个发现算法均已在 `docs/host/design.md` §4.1 冻结为唯一可实施 contract；未引入跨域总序、promotion 背压、Service B buffer 或 unbounded marker。

`CODEX-FINAL-REREVIEW-F02` 已真实关闭：exact-five `ServiceObservationResult`、五类唯一 caller disposition、stop/late commit 仲裁、cleanup precedence、七组 exact double-failure acceptance 与去敏 diagnostic 均已在 `docs/host/design.md` §4.5 冻结。

此前 F02（batch/in-flight）、F03（multi-watcher admission）、F04（overflow primary dimension）closure 仍然成立。

设计已达到可直接交给 implementation agent 的程度。唯一保留的实施测量项（packaged 数值、heap margin、metrics）有明确 owner 且不阻塞实施 gate。
