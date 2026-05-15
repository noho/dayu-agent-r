# Phase 5 Design Fix Re-Review: Terminal Closeout And Dispatch Cancel Race

## Review Role

Independent reviewer. Review only the fix for accepted blocking findings DS F1 and DS F2. Do not modify production code, do not commit, do not push, do not enter plan or implementation gate.

## Artifacts Inspected

- `docs/reviews/gateflow-phase-design-re-review-host-p5-controller-adjudication-20260514.md` — controller 裁决
- `docs/reviews/gateflow-phase-design-fix-host-p5-codex-20260514.md` — fix artifact
- `docs/host/design.md` — 修复后的设计真源（§17 lines 1719-1748, §22 lines 2160-2177）
- `docs/reviews/gateflow-phase-design-re-review-host-p5-mimo-20260514.md` — 本次 reviewer 的先前 re-review

---

## DS F1 Verdict: FIXED

**问题**：Phase 5 local stream EOF / worker crash / startup reject terminal closeout policy 缺乏具体 FAILED / LOST / RECOVERING 判定标准，plan agent 无法安全定义测试。

**Fix 内容**：design.md §17 新增 Phase 5 本地执行最小 terminal closeout policy 表（lines 1719-1729），覆盖 6 个场景：

| 场景 | Attempt | Run | recoverable | 诊断 reason |
|---|---|---|---|---|
| final pre-call recheck 失败 | 不新增终态 | 不新增终态 | false | `dispatch_aborted_by_durable_recheck` |
| WorkerProxy 调用异常 / reject / startup timeout | `FAILED` | `FAILED` | false | `worker_startup_failed` 等 |
| Engine 结构化 `run_failed` | `FAILED` | `FAILED` | diagnostic-only | Engine failure code |
| clean stream EOF 无 terminal | `FAILED` | `FAILED` | false | `stream_ended_without_terminal` |
| stream error / transport close / worker crash | `LOST` | `LOST` | false | `worker_lost_before_terminal` |
| unsupported recovery signal | `FAILED` | `FAILED` | diagnostic-only | `unsupported_recovery_policy` |

**补充约束**（line 1730）：Phase 5 不创建 automatic recovery Attempt，不把 local execution abnormal closeout 直接推入 `RECOVERING`。`RECOVERING` / recovery dispatch 由 Phase 10 或 Phase 11 在各自 design refinement 中接入。

**证据评估**：
- 每个场景有明确的 Attempt 终态、Run 终态、recoverable 标记和诊断 reason 字段。
- Phase 5 的 "no automatic RECOVERING" 约束明确，避免 plan agent 错误实现 recovery loop。
- 诊断 reason 字段具体到可以作为测试断言键。
- 与 §17 已有的 EngineEvent stream 非正常终止通用规则（lines 1697-1707）和 WorkerProxy 失败通用规则（lines 1709-1717）一致，Phase 5 表是这些通用规则在本地执行场景的具体化。

**结论**：Fix 充分。Plan agent 可以基于该表定义每个场景的测试 case 和 terminal closeout 实现。

---

## DS F2 Verdict: FIXED

**问题**：`dispatching` 已提交但 WorkerProxy 尚未 accepted 的取消窗口未定义，lane token ownership 不明确。

**Fix 内容**：两处修改。

### (a) Cancel path 增加 `dispatching + Attempt STARTING` 窗口（§22 line 2176）

> dispatch record 已进入 `dispatching` 但 Attempt 仍为 `STARTING` 时，表示 lane 已 acquire 且 dispatching commit 已完成，但 WorkerProxy 尚未 accepted。该窗口仍按 pre-worker direct cancel 收口：append `CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED`，标记 dispatch record `cancelled`，wake dispatch scheduler，释放 active slot 并触发 queue promotion check；不得进入 `CANCELLING`，不得等待不存在的 WorkerProxy。持有 lane token 的 dispatch scheduler 必须在 WorkerProxy 调用前做 final pre-call recheck；若看到 cancel / terminal 已提交或 dispatch record 已 `cancelled`，必须 release lane token 并跳过 WorkerProxy。

### (b) Lane token lifecycle（§17 lines 1742-1748）

- Lane token 从 acquire 成功后开始由 dispatch supervisor 持有。
- durable recheck 失败时必须立即 release，不得调用 WorkerProxy。
- durable recheck 成功并提交 `dispatching` 后，lane token 继续由 dispatch supervisor / worker execution context 持有，直到 Attempt terminal closeout、dispatch abort、WorkerProxy reject、startup timeout、cancel direct closeout 或 supervisor shutdown。
- WorkerProxy accept 后，lane token 不能在 `ATTEMPT_RUNNING` 前提前释放。
- cancel path 不直接假设自己持有 lane token，只提交 canonical cancel / terminal facts、更新 dispatch record、wake dispatch scheduler；实际 token release 由持有 token 的 scheduler / worker finally 路径完成。

**证据评估**：
- `dispatching + Attempt STARTING` 取消窗口明确定义为 pre-worker direct cancel 收口，与 `pending / waiting_for_lane` 取消路径语义一致（不进入 `CANCELLING`，不等待 WorkerProxy）。
- "不得进入 `CANCELLING`" 规则正确：`CANCELLING` 只适用于 `ATTEMPT_RUNNING` 已 accepted 后的 active worker cancel。
- final pre-call recheck 机制解决了 cancel 与 dispatch 的竞态：scheduler 在调用 WorkerProxy 前必须 recheck，看到 cancel / terminal 则 release lane 并跳过。
- Lane token lifecycle 从 acquire 到 release 的完整链路已定义，明确了谁持有、何时释放。
- Cancel path 不直接操作 lane token 的设计避免了 cancel 与 scheduler / worker 的 ownership 竞争。

**结论**：Fix 充分。Plan agent 可以基于该规范定义 cancel 与 dispatch 的竞态测试和 lane token release 测试。

---

## 新引入阻塞性问题检查

**无新引入阻塞性问题。**

检查项：
- F1 的 closeout 表与 F2 的 cancel 窗口定义互相一致：`dispatching + Attempt STARTING` cancel 走 direct closeout，不走 closeout 表的 worker crash / stream EOF 路径（因为 worker 尚未启动）。
- Lane token lifecycle 与 closeout 表一致：closeout 表每个场景都隐含 lane token release（"release lane token" 出现在 WorkerProxy 失败场景，其它场景由 scheduler / worker finally 路径处理）。
- "Phase 5 不创建 automatic RECOVERING" 约束与 closeout 表的 `recoverable=false` 或 `diagnostic-only` 一致。
- §22 的 cancel path 修改未引入与 §17 已有规则的矛盾。`dispatching + Attempt STARTING` cancel 条件（line 2160）与 `Attempt STARTING and dispatch record pending / waiting_for_lane / dispatching before WorkerProxy accepted` 表述一致。

---

## DS F3-F6 / MiMo Observations 确认

Controller 裁决 DS F3-F6 为 accepted-non-blocking-plan-check，MiMo observations 为 accepted-non-blocking-plan-check。Fix artifact 明确列出这些为 "Deferred Plan Checks"。

确认这些 deferred items 仍为 plan-gate checks，不因 F1/F2 fix 升级为 design blockers：

- **DS F3** EngineEvent canonical payload 最小字段：Phase 5 plan 必须定义，但 §13.4 已有默认映射表约束。
- **DS F4** dispatch record diagnostic 列：Phase 5 plan 必须定义 schema fields，但 design 已约束为 diagnostic only。
- **DS F5** RunInputBuilder real vs noop provider：Phase 5 plan 必须枚举，design §23 已列出 provider 名称。
- **DS F6** `cancel_session_runs` partial completion idempotency：Phase 5 plan 必须覆盖。
- **MiMo F-O1** `dispatching` 最终 record 状态：Plan 应确认是否需要第五个状态。
- **MiMo F-O4** context compaction 处理：Plan 必须确认 Phase 5 不实现 Phase 10 recovery。
- **MiMo F-O5** `usage_reported` 处理：Plan 可选择 diagnostic / preview。

**结论**：所有 deferred items 仍为 plan-gate checks，不阻塞 design refinement gate。

---

## 最终裁决

| Finding | Verdict | 证据 |
|---|---|---|
| DS F1 terminal closeout policy | **Fixed** | 6 场景表 + no-automatic-RECOVERING 约束 |
| DS F2 dispatching cancel window + lane token | **Fixed** | `dispatching + STARTING` direct cancel + lane lifecycle |
| 新引入阻塞性问题 | **None** | closeout 表、cancel 窗口、lane lifecycle 互相一致 |

**Gate recommendation：Phase 5 design fix re-review 通过，可以进入 plan gate。**
