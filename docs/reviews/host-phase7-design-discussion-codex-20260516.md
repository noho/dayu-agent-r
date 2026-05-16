# Host Phase 7 Design Discussion - 2026-05-16

## Gate

当前 gate：Phase 7 `Tool Awaiting / resolve_wait / Wait Adapter` design discussion。

设计真源：

- `docs/host/design.md` §20 Tool Awaiting / Wait Record
- `docs/host/design.md` §21 Suspend / Resume / Retry / Replay
- `docs/host/design.md` §22 Cancel

总控真源：

- `docs/host/implementation-control.md` Phase 7

## 动机判断

Phase 7 动机成立。

直接证据：

- Phase 6 已完成 ToolRuntime accept barrier，但 `ToolAwaitingOutcome` 当前仍在 `dayu/host/tool_runtime.py` 被降级为
  `unsupported_awaiting` governed error。
- `resolve_wait` 当前仍是 stable unsupported public function，不打开 transaction、不追加 EventLog、不写 idempotency record。
- `RunStatus.WAITING`、`AttemptStatus.SUSPENDED` 与 durable transition helpers 已为 wait / resume 路径预留，但没有 wait record
  durable truth 与统一 resolution pipeline。
- `docs/host/design.md` 已明确 ToolRuntime Host accept path 是 awaiting canonical owner，Engine `tool_awaiting` /
  `run_suspended` 不能创建 wait record 或推进 Run / Attempt 状态。

因此，本 phase 不是 UI 便利功能，而是补齐 Host 对长事务工具的 canonical governance path。

## 已确认设计决策

### D1. `ResolveWaitRequest` 改为强类型 outcome envelope

决策：接受。

Phase 7 不继续使用仅有 `outcome_ref: str` 的弱边界。`resolve_wait` request 应携带强类型等待结果 envelope，至少覆盖：

- completed tool outcome；
- failed tool outcome；
- cancelled tool outcome；
- lost / unable-to-confirm outcome。

Host pipeline 负责把 typed outcome 写成 durable payload / canonical tool terminal fact。外部结果引用可以作为 envelope 内的受限字段
或 payload ref，但不能替代显式 outcome 类型与状态机含义。

理由：

- `resolve_wait` 是 Host 内部 / adapter API，但仍是公共命名空间下的稳定 typed request；若只传字符串 ref，会把结果语义推给
  adapter 私有 payload，削弱类型检查和 review 能力。
- Phase 7 需要测试 idempotency conflict、late result rejection 与 terminal fact 类型，必须让 outcome shape 可断言。

### D2. wait record 必须落地为 Host typed durable model

决策：接受。

Phase 7 新增 wait record durable truth，而不是只把等待状态放在 EventLog payload。第一版 wait record 字段至少覆盖：

- `wait_id`
- `run_id`
- `attempt_id`
- `tool_call_id`
- `tool_name`
- `adapter_key`
- `await_kind`
- `resume_token`
- `snapshot_ref`
- `external_job_id`
- `idempotency_key`
- `deadline_at` / `expires_at`
- `status`
- created / updated refs

EventLog 仍记录 canonical facts；wait record 是 Host 恢复 adapter observation、取消等待与 resolution CAS 的状态索引，不替代
EventLog truth。

理由：

- `WAITING` cancel、late result rejection、poll adapter restart 后继续观察都需要 durable state index。
- 只依赖 EventLog payload 会迫使 adapter 扫描并重建 active waits，且容易把 projection / timeline 误当 truth。

### D3. callback 只预留 adapter contract，不产品化入口

决策：接受。

`WaitResolutionSource.CALLBACK` 保留，common `resolve_wait` pipeline 可识别 callback source；Phase 7 不实现专属 HTTP callback 服务、
认证入口、复杂重放防护或外部系统专属 callback adapter。

理由：

- callback 安全、认证与外部协议绑定属于产品化集成，不是 Host canonical wait path 的最小闭环。
- Phase 7 的关键目标是所有来源都走同一个 `resolve_wait` 短事务 pipeline，不能让 callback 入口绕开 Host governance。

### D4. `WAITING` cancel 直接关闭 wait，迟到结果只能 diagnostic / tool trace

决策：接受。

第一版 `WAITING` cancel 语义：

- append `CANCEL_REQUESTED`；
- CAS 标记 active wait record 为 `cancelled`；
- append `RUN_CANCELLED`；
- Run 进入 `CANCELLED`；
- 不创建 resume Attempt；
- 外部 job physical cancel / revoke 只允许 best-effort adapter 能力，不影响 Host terminal correctness；
- poll / callback / manual 迟到结果不得追加 canonical tool result，只能进入 diagnostic / tool trace。

理由：

- cancel 只阻止未来工作，不覆盖已接受事实；等待尚未 resolved 时，Host 可以拒绝未来 canonical result。
- 外部 job 的物理取消不可作为 Host 状态正确性的前提，否则会把外部系统一致性错误引入 Run terminal truth。

## 写回目标

本轮 design write-back 应更新：

- `docs/host/design.md`：补充 `ResolveWaitRequest` typed outcome envelope、wait record typed durable fields、callback scope 与
  `WAITING` cancel / late result 规则。
- `docs/host/implementation-control.md`：将 Phase 7 blocking design questions 标记为已确认，并要求 plan 覆盖对应测试矩阵。

## Plan Gate 要求

Phase 7 handoff implementation-ready plan 必须显式覆盖：

- wait record schema / typed row / status machine / CAS helper；
- `ToolAwaitingOutcome` accept path 从 P6 unsupported guard 迁移为 canonical wait accept；
- `resolve_wait` request envelope、idempotency scope、semantic digest、conflict handling；
- `WAITING -> resolve_wait -> RUNNING` resume Attempt creation 与 dispatch record 原子边界；
- poll / manual adapter 最小能力，callback 只保留 contract；
- `WAITING` cancel、late result diagnostic、cancel vs resolve first-committer-wins；
- Engine `tool_awaiting` / `run_suspended` 仍只能 diagnostic / idempotent confirmation；
- Run-local duplicate governance 在同一 Run resume Attempt 后继续复用。

## Non-goals

- 不实现 callback HTTP endpoint / callback authentication。
- 不保证外部 job physical cancel / revoke。
- 不实现 RemoteProxy 自治 resume。
- 不实现 retry / replay。
- 不实现 recovery scan 对 `WAITING` Run 的 adapter restore 之外的 recovery dispatch。
- 不修改 Engine contract。
