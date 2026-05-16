# Host Phase 8 Design Discussion Input - Codex - 2026-05-16

## Gate

当前 gate：Phase 8 `Projection Core / Host Event Stream / Minimal Read Model` design discussion / refinement，进入 handoff implementation-ready plan 之前。

设计真源：

- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox

总控真源：

- `docs/host/implementation-control.md` Phase 8

## 结论

Phase 8 动机成立，严重性没有被高估；当前设计真源与总控真源已经足够进入 handoff implementation-ready plan。

本轮没有发现必须先写回 `docs/host/design.md` 或 `docs/host/implementation-control.md` 的 blocking design gap。后续 plan 必须把已有设计约束落成明确的 typed contract、checkpoint transaction boundary、rebuild API / CLI 或内部 repair path、测试矩阵和 slice ownership；这些属于 plan 层实施决策，不需要在进入 plan 前扩展设计真源。

## 动机有效性

动机成立。

直接证据：

- `docs/host/implementation-control.md:952-953` 明确 Phase 8 目标是实现 committed EventLog 消费基础、projection checkpoint、Host event stream cursor 与最小 RunResult / Session timeline read model，为 Memory、Recovery 和后续 projection sinks 提供稳定基座。
- `docs/host/design.md:1411` 明确 Observer / Sink 只消费已提交 EventLog，用于派生 read model 或外部投递。
- `docs/host/design.md:1538` 明确 EventLog 是真源，Run result、Session timeline、Host event stream、audit、usage、tool trace、memory snapshot、outbox 都是 read model 或 projection。
- `docs/host/design.md:1542-1550` 已把 `get_run`、`stream_run_events`、`get_session` 的公共读取语义落在 RunSnapshot、EventLog cursor stream 与 SessionSnapshot 上。

因此，Phase 8 不是提前实现后续 Audit / Tool Trace / Outbox，也不是改变 command path；它是在 EventLog truth 已稳定后补齐可重建读取模型和 projection 基座，是后续 Memory / Recovery / projection sinks 的必要依赖。

## Phase Goals

本 phase 的目标应保持为三件事：

1. 提供 projection runner、projection checkpoint store 与 typed consumer contract，使 committed EventLog consumer 可以按 `event_sequence` 追平、按 canonical `event_id` 幂等消费，并在失败时只更新 sink-local retry / error state。
2. 提供 Host event stream 读取路径，严格从 EventLog `event_sequence` cursor 补读并返回稳定 cursor，不触发执行，不依赖内存 notification 正确性。
3. 提供最小 RunResult / Session timeline read model 与 rebuild path，确保投影缺失或损坏时可由 EventLog 重建，且不反向成为 resume、memory、audit 或 Run 状态迁移真源。

## Success Signals

可进入下一 gate 的成功信号：

- Projection runner 能接收 typed consumer，按全局 `event_sequence` checkpoint replay committed EventLog rows。
- Checkpoint 只在 consumer projection 结果持久化成功后推进；重复扫描同一 `event_id` 不产生重复 projection row 或副作用。
- Consumer failure 不回滚 EventLog，不改变 Run / Attempt governance state，只留下 sink-local retry / error / lag 可诊断状态。
- `stream_run_events(run_id, cursor, limit)` 的排序和补读只来自 EventLog `event_sequence`，慢客户端通过 cursor catch up。
- Minimal RunResult 能从 terminal canonical facts 派生；Session timeline 能表达多条 `USER_INPUT_ACCEPTED`，包括取消输入与后续新输入的差异。
- 删除或清空 minimal read model 后，rebuild path 能从 EventLog 恢复 RunResult / Session timeline 到一致结果。
- Phase 9 Memory 可以复用 EventLog replay consumer / checkpoint framework，而不需要读取 Session timeline 或 RunResult 作为事实真源。

## Scope Boundaries

允许进入 plan 的范围：

- projection runner / worker loop / replay helper。
- projection checkpoint store 与 consumer-local retry / error state。
- typed consumer contract，包括输入 event view、payload view、checkpoint、幂等键、失败处理和输出 projection。
- Host event stream from EventLog `event_sequence` cursor。
- minimal RunResult projection。
- minimal Session timeline projection 与 rebuild / repair path。
- 相关 unit / integration tests、pyright、Host README 边界同步。

禁止越界：

- 不修改 command path 状态机。
- 不修改 Run / Attempt governance state。
- 不把 projection checkpoint、timeline、RunResult、audit、tool trace、outbox 或 memory snapshot 作为 Host governance truth。
- 不引入 UI / Service channel delivery 成功状态。
- 不把 terminal transaction 同步写 outbox 表。

## Non-goals

本 phase 不做：

- `LogAuditSink(JSONL)`。
- tool trace hot JSON / cold JSONL。
- OutboxSink。
- 外部 audit 系统。
- channel delivery exactly-once。
- Service / UI channel adapter delivery、seen cursor 存储或通知重试。
- Memory snapshot、Conversation Memory policy 或 RunInputBuilder memory provider。
- Recovery scan 或从 projection 恢复 Run truth。

这些非目标已由 `docs/host/implementation-control.md:970-976` 与 `docs/host/implementation-control.md:1005-1006` 固定，且与 `docs/host/design.md:1562-1580` 的 Outbox 边界一致。

## Explicit Checks

### Projection runner typed consumer contract

状态：已具备进入 plan 的设计依据。

证据：

- `docs/host/design.md:1430-1434` 要求 Sink 输入是 committed EventLog event，按 `event_sequence` checkpoint 追平，按 canonical `event_id` 幂等消费，并声明消费哪些 `event_class` / `event_type`。
- `docs/host/design.md:1434` 明确每个 Sink 必须有自己的 typed consumer contract，包含输入 event 类型、payload view、checkpoint、幂等键、失败处理和输出 projection。
- `docs/host/implementation-control.md:978-979` 把 typed consumer contract、checkpoint、幂等键和失败处理列为 Phase 8 必须确认项。

Plan 要求：必须定义核心 runner 的泛型 / 协议边界和最小 consumer lifecycle，例如 `load_checkpoint -> read events after cursor -> project batch/event -> commit projection + checkpoint -> record failure`。禁止用无结构 payload bag 或 `Any` 绕开 typed event view。

### Checkpoint / idempotency / failure handling

状态：已具备进入 plan 的设计依据。

证据：

- `docs/host/design.md:1431-1432` 要求 checkpoint 按 `event_sequence`，幂等按 canonical `event_id`。
- `docs/host/design.md:1436-1437` 要求 lag 只影响派生视图新鲜度，失败只能更新 sink-local retry / error state，不能回滚 EventLog 或改变 Run / Attempt。
- `docs/host/design.md:1464-1469` 再次固定 Sink 不拥有 Session / Run / Attempt 状态、失败不能回滚 EventLog、正确性来自 EventLog replay + checkpoint。
- `docs/host/implementation-control.md:1001-1002` 退出条件要求 projection lag 或 core projection failure 不影响 EventLog append、Run terminal、resume 或 memory truth。

Plan 要求：checkpoint 推进必须与对应 projection 写入同事务或同等原子边界完成；失败记录不得推进 checkpoint；重复 replay 必须以 `event_id` 或 terminal identity upsert，不能靠文本内容或内存 seen set。

### Host event stream from EventLog event_sequence cursor

状态：已具备进入 plan 的设计依据。

证据：

- `docs/host/design.md:1546-1548` 定义 `stream_run_events(run_id, cursor, limit?) -> ordered Host event stream from EventLog event_sequence cursor`。
- `docs/host/design.md:1558` 明确 `stream_run_events` 不触发新执行。
- `docs/host/implementation-control.md:980` 要求确认 Host event stream 只从 EventLog `event_sequence` cursor 补读，不触发执行。

Plan 要求：Host event stream 的 truth 是 EventLog read path，不是 stream fanout 内存队列；stream fanout 可以作为 wakeup / attached client optimization，但断线补读必须仍由 cursor replay 完成。

### Minimal RunResult / Session timeline read model rebuild

状态：已具备进入 plan 的设计依据。

证据：

- `docs/host/design.md:1555-1559` 明确 RunResult 和 Session timeline 都不是事实真源，投影损坏或缺失时应能从 EventLog 重建。
- `docs/host/design.md:1557` 要求 Session timeline 能表达已取消的用户输入与后续新输入是两条不同 `USER_INPUT_ACCEPTED`。
- `docs/host/implementation-control.md:981` 要求确认最小 RunResult / Session timeline read model 损坏后可由 EventLog 重建。
- `docs/host/implementation-control.md:996-997` 要求测试覆盖 projection rebuild，以及 terminal EventLog -> Host event stream / minimal timeline / RunResult。

Plan 要求：minimal timeline 不应尝试做完整 UI 聊天记录产品形态，只覆盖 Phase 8 需要的 stable read model；rebuild 测试必须先制造 projection 缺失 / stale，再用 EventLog replay 恢复。

### Outbox / Audit / Tool Trace excluded from this phase

状态：已明确排除。

证据：

- `docs/host/implementation-control.md:963-964` 进入条件只允许 Audit、Tool Trace、Outbox 预留 consumer contract，不在本 phase 落地。
- `docs/host/implementation-control.md:970-976` 明确不实现 `LogAuditSink(JSONL)`、tool trace hot / cold、OutboxSink、外部 audit 系统、channel delivery exactly-once，也不让 terminal transaction 同步写 outbox 表。
- `docs/host/design.md:1566-1580` 明确 Outbox 不是 UI read model，不参与 resume / memory / Run 状态迁移，且 terminal transaction 不同步写 outbox 表。

Plan 要求：可以定义未来 sink 复用的 typed consumer interface，但不得创建 Audit / Tool Trace / Outbox 的具体 projection 表、JSONL writer、delivery queue 或 channel delivery state。

### No reverse dependency from projections to Host governance truth

状态：设计边界已充分。

证据：

- `docs/host/design.md:1435` 要求 Sink 可以维护 projection 表、work queue 或冷数据文件，但不能写 Host governance truth。
- `docs/host/design.md:1438` 要求 sink 消费 recovery 相关 event 时不读取 Recovery 内部状态，不对 Recovery 内部状态形成反向依赖。
- `docs/host/design.md:1538` 把 Run result、Session timeline、Host event stream、audit、usage、tool trace、memory snapshot、outbox 定位为 read model 或 projection。
- `docs/host/design.md:1560` 要求 resume、memory、audit 责任链读取 EventLog canonical facts。

Plan 要求：projection 模块不得 import 或调用 command transition service、admission service、recovery internals 或 Run / Attempt 状态 mutator；只能读取 EventLog / durable read views，并写 projection-owned storage。

## Blocking Open Questions

无 blocking open question。

需要在 plan 中固定、但不阻塞进入 plan 的实施细节：

- Projection runner 是 batch-at-a-time 还是 event-at-a-time；建议第一版支持 batch loop，但 consumer contract 以单 event 或小 batch typed input 明确。
- Checkpoint table 是否复用既有 durable store transaction helper；建议复用 Host durable foundation，不引入第二套 transaction abstraction。
- Rebuild path 是内部 helper、maintenance command 还是测试专用入口；建议先提供 Host 内部 repair helper + 测试覆盖，CLI / admin surface 留到 Phase 15 production hardening。
- Stream fanout 的 attached-client optimization 是否在 Slice 2 落地；建议只做最小 wakeup / fanout 基础，不让其成为 correctness 依赖。

## Design Gaps Requiring Write-back Before Plan

无。

现有设计已经固定：

- projection 输入、checkpoint、幂等、失败处理边界；
- Host event stream 的 EventLog `event_sequence` cursor truth；
- RunResult / Session timeline 的 read model 定位与 rebuild 要求；
- Outbox / Audit / Tool Trace 的 phase 排除；
- projection 不得反向写 Host governance truth。

因此，本轮不建议修改 `docs/host/design.md` 或 `docs/host/implementation-control.md`。若 controller 希望把具体类名、函数名、schema 字段名写入文档，应写入 Phase 8 handoff plan，而不是设计真源。

## Recommended Plan Boundaries / Slices

建议沿总控文档的三段切分推进，并在 plan 中把每个 slice 的 allowed files、测试和 stop condition 写死。

### Slice 1: Projection runner / checkpoint / typed consumer contracts

目标：建立 committed EventLog replay consumer 基础。

必须覆盖：

- projection checkpoint schema / row codec / store。
- typed consumer protocol：consumer id、event filter、typed event view、payload view、idempotency key、project result、failure result。
- runner replay loop：读取 checkpoint 后的 EventLog rows，按 `event_sequence` 顺序调用 consumer。
- checkpoint advance invariant：projection commit 成功后才推进 checkpoint。
- failure handling：sink-local retry / error state，不推进 checkpoint，不回滚 EventLog。
- tests：checkpoint idempotency、consumer replay、failure retry、不写 Host governance truth 的 import / boundary guard。

### Slice 2: Host event stream from EventLog `event_sequence` cursor

目标：把 Host event stream 固定为 EventLog-backed read path。

必须覆盖：

- `stream_run_events` 使用全局 `event_sequence` cursor 过滤目标 Run。
- `limit`、empty result `next_cursor`、event ordering、run/session filtering 的稳定行为。
- preview / diagnostic event 是否进入 stream 只能按既有 EventLog class 映射，不发明 command side effect。
- stream fanout 只作为 attached-client notification / wakeup，不作为补读 truth。
- tests：断线 cursor 补读、慢 consumer 不影响 append、`stream_run_events` 不触发 dispatch / execution。

### Slice 3: Minimal Session timeline / RunResult read model and rebuild path

目标：提供最小可重建 read model。

必须覆盖：

- RunResult projection：terminal event identity、run_id、terminal status、result ref / digest、terminal event_sequence。
- Session timeline projection：按 EventLog 表达 user input、run status、terminal summary；取消输入与后续新输入保持不同 `USER_INPUT_ACCEPTED`。
- Rebuild / repair helper：从 EventLog 清空重建或指定 session / run 重放。
- Projection lag 行为：lag 只能影响 read model 新鲜度，不影响 command path、resume、memory truth。
- tests：terminal EventLog -> RunResult；multi-run Session timeline；projection 删除后 rebuild 一致；projection stale 时 EventLog stream 仍可读。

## Risks / Deferred Items / Owners

- Phase 8 owner：projection runner、checkpoint framework、Host event stream cursor、minimal RunResult / Session timeline read model、rebuild path。
- Phase 9 owner：Conversation Memory projection、memory snapshot cursor、RunInputBuilder memory provider；不得在 Phase 8 提前实现 memory policy。
- Phase 11 owner：Recovery scan、orphan proof、从 Host durable truth 恢复 Run / Attempt；不得从 projection / timeline / RunResult 恢复 governance truth。
- Phase 13 owner：Audit、Tool Trace、Outbox concrete sinks；Phase 8 只预留可复用 consumer contract。
- Phase 15 owner：production hardening、admin rebuild tooling、purge 对 projection / outbox / tool trace hot data / audit JSONL 的最终清理矩阵。
- Service / UI owner：channel delivery、seen cursor 存储、离线补投展示去重；Host 不保存 GUI / CLI / WeChat / Web 投递成功状态。

残余风险：

- 如果 plan 把 generic runner 做成 untyped event payload dispatcher，会违反 §14 typed consumer contract；plan review 必须把这一点列为 blocking criterion。
- 如果 rebuild path 只在测试 fixture 中隐式实现，Phase 15 production hardening 会缺少可复用 repair primitive；建议 Phase 8 至少保留内部 repair helper。
- 如果 Slice 2 把 stream fanout 当作 correctness path，会破坏 EventLog cursor truth；plan 必须明确 fanout 只是 wakeup / optimization。

## Plan Gate Readiness

Readiness：ready。

Phase 8 可以进入 handoff implementation-ready plan。进入 plan 时不需要先做设计写回，但 plan 必须显式固化上述 typed consumer contract、checkpoint / idempotency / failure invariant、EventLog cursor stream、minimal read model rebuild、Outbox / Audit / Tool Trace 排除项，以及 projection 不反向依赖 Host governance truth 的 import / ownership 边界。
