# Host Phase 8 Design Discussion Controller Adjudication - 2026-05-16

## Gate

当前 gate：Phase 8 `Projection Core / Host Event Stream / Minimal Read Model` design discussion / refinement。

输入 artifact：

- `docs/reviews/host-phase8-design-discussion-codex-20260516.md`

设计真源：

- `docs/host/design.md` §14 Observer / Sink / Projection
- `docs/host/design.md` §16 Read Model / Host Event Stream / Outbox

总控真源：

- `docs/host/implementation-control.md` Phase 8

## Controller Verdict

PASS。Phase 8 可以进入 handoff implementation-ready plan gate。

本轮没有 accepted blocking open question，也没有必须先写回 `docs/host/design.md` 或
`docs/host/implementation-control.md` 的 design gap。Phase 8 的目标、边界、non-goals、success signal 与
`docs/host/design.md` §14 / §16 直接一致。

## Motivation Judgment

动机成立，严重性没有被高估。

Phase 8 不是提前实现 Audit / Tool Trace / Outbox，也不是把 projection 放进 command path；它补齐的是后续
Memory、Recovery、Audit / Tool Trace / Outbox sinks 共同依赖的 committed EventLog replay、checkpoint、Host event
stream cursor 与最小可重建 read model。没有这个基座，后续 phase 会重复实现不一致的 EventLog consumer、checkpoint
和 rebuild 语义，风险真实存在。

## Accepted Design Discussion Findings

### P8-DISC-001: Phase 8 can proceed to plan without design write-back

裁决：accepted。

理由：

- `docs/host/design.md` §14 已明确 Sink 输入、checkpoint、idempotency、failure handling 与 no reverse dependency
  边界。
- `docs/host/design.md` §16 已明确 Host event stream 的 EventLog `event_sequence` cursor truth、RunResult /
  Session timeline 的 read model 定位与 rebuild 要求。
- `docs/host/implementation-control.md` Phase 8 已明确允许范围、不做项、关键设计问题、验证要求和退出条件。

后续要求：Phase 8 plan 必须把这些设计语义落为 code-generation-ready 的 typed contract、schema、slice ownership、
测试矩阵和 stop conditions。

### P8-DISC-002: Projection runner must remain typed and projection-owned

裁决：accepted as plan-review criterion。

Phase 8 plan review 必须把以下情况视为 blocking：

- 用无结构 payload bag、`Any` 或宽泛 `object` 作为 consumer 边界。
- 让 projection module 调用 command transition、admission、recovery internals 或 Run / Attempt mutator。
- 让 checkpoint、Session timeline、RunResult、outbox、audit、tool trace 或 memory snapshot 反向成为 Host
  governance truth。

### P8-DISC-003: Stream fanout cannot become correctness path

裁决：accepted as plan-review criterion。

Host event stream 的正确性必须来自 EventLog `event_sequence` cursor replay。若 plan 引入 stream fanout，只能作为
wakeup / attached-client optimization；断线补读、慢客户端 catch-up 和 cursor 推进不得依赖内存 notification。

### P8-DISC-004: Rebuild path must be a real internal repair primitive

裁决：accepted as plan-review criterion。

Minimal RunResult / Session timeline read model 损坏或缺失时必须能由 EventLog 重建。Plan 可以把 CLI / admin
surface 后置到 Phase 15，但不能只在测试 fixture 中隐式重建；至少需要 Host 内部 repair helper 和覆盖 projection
删除 / stale 后 replay 的测试。

## Rejected Findings

无。

## Deferred Findings

无当前 Phase 8 blocking deferred finding。

以下能力保持既有后续 owner：

- Phase 9：Conversation Memory projection、memory snapshot cursor、RunInputBuilder memory provider。
- Phase 11：Recovery scan 与 Run / Attempt 恢复治理，只能读取 Host durable truth，不能读取 projection truth。
- Phase 13：Audit、Tool Trace、Outbox concrete sinks。
- Phase 15：production hardening、admin rebuild tooling、purge 与 projection / outbox / tool trace / audit 清理矩阵。
- Service / UI：channel delivery、seen cursor 存储与离线补投展示去重。

## Plan Gate Requirements

Phase 8 handoff implementation-ready plan 必须至少固定：

- projection checkpoint schema / row codec / store；
- typed consumer contract，包括 consumer id、event filter、typed event view、payload view、idempotency key、failure
  handling 和 projection output；
- runner replay loop 与 checkpoint advance invariant；
- Host event stream EventLog cursor truth 与 stream fanout non-truth boundary；
- minimal RunResult / Session timeline projection schema；
- read model rebuild / repair helper；
- per-slice allowed files、tests、pyright、README sync 与 stop conditions。

## Validation

本 gate 只新增 discussion / adjudication artifact，未修改 production code 或 tests。无需运行 pytest / pyright；后续
plan、implementation 和文档更新 gate 必须按项目规则验证。
