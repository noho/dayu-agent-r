# Phase 5 Design Fix Re-Review: DS F1 / F2 Verification

## Metadata

- **Review type**: Design fix re-review (AgentDS)
- **Gate**: Phase 5 design fix re-review
- **Prior review**: `docs/reviews/gateflow-phase-design-re-review-host-p5-ds-20260514.md`
- **Controller adjudication**: `docs/reviews/gateflow-phase-design-re-review-host-p5-controller-adjudication-20260514.md`
- **Fix artifact**: `docs/reviews/gateflow-phase-design-fix-host-p5-codex-20260514.md`
- **Design truth**: `docs/host/design.md` (unstaged changes)
- **Date**: 2026-05-14
- **Scope**: Verify DS F1 and DS F2 fixes only; check for new blockers.

---

## DS F1: Terminal Closeout Policy — VERDICT: FIXED

**Original finding**: Phase 5 local stream EOF / worker crash / startup reject terminal closeout lacks concrete FAILED / LOST / RECOVERING criteria.

**Fix applied**: New terminal closeout policy table in `docs/host/design.md` §17 (after dispatch failure path):

| 场景 | Attempt | Run | recoverable | 最小诊断 |
| --- | --- | --- | --- | --- |
| pre-call recheck 失败 | 由已提交事实决定 | 由已提交事实决定 | false | `dispatch_aborted_by_durable_recheck` |
| WorkerProxy 调用异常 / reject / startup timeout（未 accepted） | `FAILED` | `FAILED` | false | `worker_startup_failed` / `worker_rejected` / `worker_startup_timeout` |
| EngineWorker accepted 后结构化 `run_failed` | `FAILED` | `FAILED` | Engine `recoverable` 仅作诊断 | Engine failure code, message, provider request id, recoverable |
| stream clean EOF 无 terminal event | `FAILED` | `FAILED` | false | `stream_ended_without_terminal` |
| stream error / transport close / worker crash（terminal 不可确认） | `LOST` | `LOST` | false in Phase 5 | `worker_lost_before_terminal` |
| 需要后续 phase owner 的 recoverable failure | `FAILED` | `FAILED` | diagnostic-only | `unsupported_recovery_policy` |

**Verification**:

1. 六种场景覆盖了 Phase 5 本地执行所有可达的异常终止路径，涵盖 startup 阶段、运行阶段、EOF 阶段和 crash 场景。
2. 区分了 `FAILED`（Engine 有明确错误信号或干净退出但缺 terminal）与 `LOST`（进程崩溃或流异常，terminal 不可确认），判定标准具体。
3. 显式声明 "Phase 5 不创建 automatic recovery Attempt"，将 `RECOVERING` 排除在 Phase 5 之外，边界清晰。
4. 每种场景给出最小 diagnostic/reason 字符串，plan 可直接转化为 typed error code。
5. "stream clean EOF without terminal" 与 "worker crash" 的区分依赖于 worker lifecycle signal（进程退出码/信号），design 未强制 LocalProxy 的具体实现机制，但这属于 plan 层面的实现细节，不构成 design ambiguity。

**Edge case check**: Engine 正常发出 `final_answer` 后 clean EOF → 此时 `final_answer` 已是 terminal event（`RUN_SUCCEEDED`），不会命中 "EOF without terminal"。该场景被 §13.4 映射覆盖，无冲突。

**Verdict**: **FIXED** — 判定表具体、完整、可测试。plan 可直接转化为 closeout state machine。

---

## DS F2: dispatching Cancel Window + Lane Token Lifecycle — VERDICT: FIXED

**Original finding**: `dispatching` committed but WorkerProxy not yet called cancel window is undefined; lane token ownership unclear.

**Fix applied** — four interconnected changes in `docs/host/design.md`:

### (a) §17 lane token lifecycle (new subsection)

```
Lane token 从 acquire 成功后开始由 dispatch supervisor 持有；
durable recheck 失败 → 立即 release；
recheck 成功并提交 dispatching 后 → 继续持有直到 terminal closeout / dispatch abort /
  WorkerProxy reject / startup timeout / cancel direct closeout / supervisor shutdown；
WorkerProxy accept 后 → 不能在 ATTEMPT_RUNNING 前提前释放；
cancel path → 不直接假设自己持有 lane token，只提交事实并 wake scheduler；
实际 release → 由持有 token 的 scheduler / worker finally 路径完成。
```

### (b) §22 Cancel rules (new rule)

```
dispatching + Attempt STARTING:
  → direct CANCELLED（非 CANCELLING）
  → 标记 dispatch record cancelled
  → wake dispatch scheduler
  → 不等待不存在的 WorkerProxy
  → scheduler final pre-call recheck 发现 cancelled 后 release lane + skip WorkerProxy
```

### (c) §22 Cancel initial path (updated)

```
pending / waiting_for_lane / dispatching before WorkerProxy accepted:
  → Attempt CANCELLED + Run CANCELLED
active Attempt RUNNING:
  → RUN_CANCELLING
```

### (d) §8 cancel_decision matrix (updated)

Row split: "pre-worker starting" (`pending`/`waiting_for_lane`/pre-accept `dispatching`) vs "active running" (`RUNNING` only).

### (e) §10 Run contract semantics (updated)

`cancel_run` 和 `cancel_session_runs` 描述中均将 pre-accept `dispatching` 纳入 pre-worker direct cancel 组。

**Verification**:

1. **Cancel window defined**: `dispatching + STARTING` 被明确归类为 pre-worker direct cancel，不走 `CANCELLING`。与 `RUNNING` 的边界由 `ATTEMPT_RUNNING` durable fact 决定——只有 ingest 已接受 `ATTEMPT_RUNNING` 后才进入 `CANCELLING` 路径。

2. **Lane token ownership clear**: 五个生命周期阶段（acquire → recheck → dispatching → accept → terminal）均有明确的持有/释放规则。cancel path 不抢 token，只发信号；release 由持有方 finally 完成。

3. **Pre-call recheck as safety net**: `final pre-call recheck` 在 WorkerProxy 调用前执行，检查 cancel/terminal 是否已提交、dispatch record 是否已被取消。这提供了 cancel 与 dispatch 之间的最终同步点。

4. **Narrow race acknowledged but bounded**: cancel 在 final pre-call recheck 之后、WorkerProxy accept 之前到达时，WorkerProxy 可能对一个已标记 cancelled 的 Attempt 发起执行。但 ingest boundary 的 `attempt_id + execution_id` 校验会拒绝 `ATTEMPT_RUNNING` candidate（因为 Attempt 已 `CANCELLED`），防止状态污染。这与 design 已有原则一致："Host 不保证 exactly-once 远程物理执行...Host 通过 execution_id 拒绝迟到事件"。

5. **§8 / §10 / §17 / §22 一致性**: 所有四处引用 `dispatching + STARTING` 的 cancel 行为保持一致——均为 direct `CANCELLED`。

**Verdict**: **FIXED** — 窗口定义清晰，lane token 生命周期完整，cancel 行为与 dispatch scheduler 的交互机制明确。

---

## New Blocker Check

逐项扫描 fix 引入的变更，检查是否引入新的 design ambiguity 或冲突：

1. **closeout table 中 "stream error / transport close" 与本地执行的映射**: 对于 LocalProxy，stream error 和 transport close 都表现为进程退出或 pipe 断开。design 未区分两者，统一归为 `LOST`。对于本地执行而言合理——本地无 transport 层，stream error 等同于 worker crash。不构成 ambiguity。

2. **"clean EOF without terminal" vs "worker crash" 判定依赖于 worker lifecycle signal**: design 将区分责任交给 LocalProxy/EngineWorker 的进程生命周期观察，未定义具体 signal 格式。这对于 design 层面是合理的——plan 需要决定 LocalProxy 如何观察子进程退出码/信号，但不改变 closeout policy 的终态选择。

3. **lane token 的 "worker execution context" 持有者**: design 说 "dispatch supervisor / worker execution context" 持有 token。对于本地执行，这两者可能是同一进程内的不同 asyncio Task。plan 需要明确 token 在 Task 之间的传递机制，但这属于实现细节。

4. **cancel_session_runs 中 pre-worker dispatching Run 的批量处理**: 已通过 §22 的规则覆盖——与 `pending` / `waiting_for_lane` 同为 direct `CANCELLED`，语义一致。

无新 blocking finding。

---

## DS F3-F6 and MiMo Observations Status

所有非阻塞 findings 和 observations 的状态未因本次 fix 改变：

| Finding | Status | Reason |
| --- | --- | --- |
| DS F3 (canonical payload fields) | Plan-gate check | Payload schema 属于 plan 层面定义，design §13.4 边界已足够 |
| DS F4 (dispatch diagnostic fields) | Plan-gate check | 字段语义已约束为 diagnostic-only，plan 可定义具体列 |
| DS F5 (RunInputBuilder provider set) | Plan-gate check | Plan readiness 已列为必须覆盖项 |
| DS F6 (cancel_session_runs partial completion) | Plan-gate check | Plan 中 cancel slice 必须处理 |
| MiMo F-O1 (dispatching final record state) | Plan-gate check | Plan 应明确 worker accept 后 record 是否保持在 `dispatching` |
| MiMo F-O4 (context compaction handling) | Plan-gate check | Phase 5 plan 必须隔离 Phase 10 concern |
| MiMo F-O5 (usage_reported handling) | Plan-gate check | Plan 可选 diagnostic/preview，不改变 design truth |

均仍为合适的 plan-gate 检查项，无需提升为 design blocker。

---

## Final Gate Recommendation

**DS F1: FIXED** — terminal closeout policy table 提供了具体、可测试的判定标准。

**DS F2: FIXED** — `dispatching + STARTING` 窗口的 cancel 行为已定义，lane token 生命周期已完整。

**New blockers: 0** — fix 未引入新的 design ambiguity 或冲突。

**Plan gate readiness**: design refinement 现在满足 plan gate 进入条件。Phase 5 handoff implementation-ready plan 可以基于当前 `docs/host/design.md` 的安全边界编写。plan review 应将 DS F3-F6 和 MiMo observations 作为检查项。

**Gate recommendation**: 通过。可以进入 Phase 5 plan gate。
