# Phase 5 Design Re-Review: Independent Reviewer Artifact

## Metadata

- **Review type**: Independent design re-review (AgentDS)
- **Gate**: Phase 5 design re-review
- **Design truth**: `docs/host/design.md` (HEAD with unstaged changes)
- **Control doc**: `docs/host/implementation-control.md` (HEAD with unstaged changes)
- **Prior review**: `docs/reviews/gateflow-phase-design-host-p5-codex-20260514.md`
- **Date**: 2026-05-14
- **Verdict**: 2 blocking findings; plan gate NOT ready. 4 non-blocking observations.

---

## Review Scope

This review assesses whether the Phase 5 design refinement (as written back to `docs/host/design.md` and `docs/host/implementation-control.md`) is sufficient for a handoff implementation-ready plan to be safely produced. It does NOT assess the prior Codex review artifact itself, nor does it review Phase 1-4 implementation code.

## Review Lenses Applied

1. Phase 5 goals satisfaction (RunInputBuilder, LocalProxy, EngineEvent ingest, lane dispatch, terminal closeout, active dispatch cancel)
2. Architectural boundary preservation (UI→Service→Host→Engine, Engine-Host agnosticism, durable truth ownership)
3. Coherence and sufficiency of three user-confirmed decisions (P5-D1, P5-D2, P5-D3)
4. Blocking ambiguity for implementation-ready plan
5. Over-design, under-specification, hidden reverse dependencies, schema/state-machine gaps, cancellation gaps, stream EOF terminal closeout gaps, residual risk ownership

---

## Findings

### Finding F1 — BLOCKING

**Severity**: Blocker (plan gate)

**Title**: Stream EOF / worker crash / startup reject 的 terminal closeout policy 缺失具体判定标准

**Evidence**:

`docs/host/design.md` §17 Worker dispatch semantic contract 定义了异常终止路径：

```text
EngineEvent stream EOF / error / transport close / worker crash
  AND no terminal event accepted for active Attempt
  -> Host records diagnostic
  -> Host evaluates Attempt as failed / lost / recoverable according to policy
  -> Host must not leave Run indefinitely RUNNING solely waiting for restart scan
```

以及 dispatch 失败路径：

```text
dispatch record = dispatching
  -> release lane token
  -> append dispatch diagnostic
  -> Attempt -> FAILED or LOST by failure type
  -> Run -> FAILED / RECOVERING / LOST by Host policy and recoverability
```

但 design.md 全文未定义该 "policy" 的具体判定标准：
- 什么条件下 Attempt 进入 `FAILED` vs `LOST`？
- 什么条件下 Run 进入 `FAILED` vs `RECOVERING` vs `LOST`？
- worker crash 与 "worker exited cleanly but without terminal event" 如何区分？本机 LocalProxy 可以通过进程退出码区分，但 design.md 未要求 EngineWorker 的退出契约携带该信息。
- stream EOF（正常关闭）与 transport close（异常断连）在本地执行中如何区分？LocalProxy 场景下两者可能合并为同一 OS 级信号。

**Impact**:

若无具体判定标准，plan 将被迫自行发明 policy，可能：
1. 与 Phase 11 Recovery 的 positive orphan proof 逻辑冲突（例如过早标记 `LOST` 导致 recovery 误判）。
2. 在本地执行中对 EOF/error/crash 做出不一致的终态选择。
3. 无法在 plan 中定义可测试的 terminal closeout 行为矩阵。

**Recommendation**:

在 `docs/host/design.md` §17 中增加最小判定表，至少覆盖 Phase 5 本地执行场景下的三种异常终止：
- EngineWorker 进程崩溃（OS-level signal / non-zero exit）
- EngineWorker 正常退出但未 emit terminal event（Engine 内部异常但进程未崩）
- stream EOF 先于 terminal event（Engine 返回了 run_failed 但 stream 提前关闭）

每种场景指定：Attempt 终态、Run 终态、是否可恢复、diagnostic event 最小字段。

**Blocks plan gate**: YES

---

### Finding F2 — BLOCKING

**Severity**: Blocker (plan gate)

**Title**: `dispatching` 状态下 cancel 到达但 WorkerProxy 尚未调用时的行为未定义

**Evidence**:

`docs/host/design.md` §17 Worker dispatch semantic contract 的事务序列：

```text
after lane acquired, open short Host transaction
  -> re-read Run / Attempt / dispatch record
  -> ... if valid: update dispatch record status = dispatching ... commit
  -> WorkerProxy receives dispatch request with attempt snapshot
```

即 `dispatching` commit 与 WorkerProxy 调用之间存在一个窗口：事务已提交、但 dispatch scheduler 尚未调用 WorkerProxy。

`docs/host/design.md` §22 Cancel 规则：

```text
dispatch record 已进入 dispatching 或 Attempt 已 RUNNING 时，
必须 append CANCEL_REQUESTED + RUN_CANCELLING 并向 WorkerProxy 传播 cancel。
```

该规则假设 WorkerProxy 已存在并可传播 cancel。但在上述窗口中，cancel 到达时：
- dispatch record 状态 = `dispatching`
- WorkerProxy 尚未被调用，无 worker 可传播
- lane token 已被 release（lane acquire 在 recheck 成功前 release？还是 dispatch 后才 release？）

`docs/host/design.md` §17 在 recheck 描述中未说明 lane token 的生命周期边界：lane acquire 成功后 token 持有到何时 release？是 dispatch 成功调用 WorkerProxy 后？还是 recheck 事务提交后？

**Impact**:

该窗口下的 cancel 行为存在三个未解决问题：
1. cancel 应等待 WorkerProxy 调用后再传播，还是直接标记 dispatch record cancelled 并阻止后续 WorkerProxy 调用？
2. 如果直接取消，lane token 由谁 release？cancel path 还是 dispatch scheduler 的后续 recheck？
3. Attempt 终态是 `CANCELLED` 还是先 `CANCELLING` 再 `CANCELLED`？Run 是否进入 `CANCELLING` 再 `CANCELLED`？

若 plan 自行解决，可能与 Phase 11 recovery scan 对 `dispatching` 状态的解释冲突。

**Recommendation**:

在 `docs/host/design.md` §22 中增加 `dispatching + no worker yet` 子窗口的 cancel 语义：
- cancel 直接标记 dispatch record `cancelled`，不进入 `CANCELLING`（因为没有 worker 需要等待确认）
- 或 cancel 等待 dispatch scheduler 的下一次 recheck 发现 `CANCEL_REQUESTED` 后自行收口
- 明确 lane token release 的 owner（cancel path vs dispatch scheduler cleanup）

同时明确 §17 中 lane token 的持有生命周期：从 lane acquire 成功到 WorkerProxy 调用完成（或到 EngineWorker accept/reject 返回）。

**Blocks plan gate**: YES

---

### Finding F3 — HIGH

**Severity**: High (non-blocking)

**Title**: EngineEvent 映射缺少 canonical event 的最小 payload 定义

**Evidence**:

`docs/host/design.md` §13.4 EngineEvent 映射给出了 EngineEvent → Host event 的类型对应关系：

```text
tool_call_requested            -> TOOL_CALL_REQUESTED
final_answer                   -> RUN_SUCCEEDED + ATTEMPT_SUCCEEDED
run_cancelled                  -> RUN_CANCELLED + ATTEMPT_CANCELLED
run_failed                     -> ATTEMPT_FAILED + (RUN_FAILED or RUN_RECOVERING by Host policy)
...
```

但未定义各 canonical event 必须携带的最小 payload 字段。例如：
- `TOOL_CALL_REQUESTED` 需要携带 tool_call_id、tool_name、arguments digest 吗？
- `RUN_SUCCEEDED` + `ATTEMPT_SUCCEEDED` 是否需要携带 final answer text 及其 digest？
- `ATTEMPT_FAILED` 需要携带 failure reason、error code、provider diagnostic refs 吗？

Phase 4 已在 EventLog append 层面实现了 `PayloadDescriptor` 和 `fact_type` / `fact_class`，但未绑定各 EngineEvent 映射产物的具体 payload schema。

**Impact**:

Plan 可能为每种 canonical event 自行发明 payload schema，导致：
1. 不同 event type 的 payload 字段不一致（有的有 tool_call_id，有的缺失）
2. 后续 Phase 8 Projection / Phase 9 Memory 消费时发现关键字段缺失
3. recovery 需要的信息（如 failure reason）未进入 canonical fact

**Recommendation**:

在 `docs/host/design.md` §13.4 中为 Phase 5 实际产出的 canonical event 类型（至少 `TOOL_CALL_REQUESTED`、`RUN_SUCCEEDED`、`ATTEMPT_SUCCEEDED`、`ATTEMPT_FAILED`、`RUN_FAILED`、`RUN_CANCELLED`、`ATTEMPT_CANCELLED`）定义最小 payload 字段表。后续 phase 可扩展，但 Phase 5 必须有一个最小基线。

**Blocks plan gate**: NO — plan 可以在 phase plan 中定义 payload schema，只要不违反 §13.4 的 canonical/preview 边界。但 plan review 应检查 payload 是否覆盖 recovery/resume 最小需求。

---

### Finding F4 — HIGH

**Severity**: High (non-blocking)

**Title**: `dispatcher_instance_id` 和 `lane_name` 等 Phase 5 新增 diagnostic ref 在 DispatchRecordRow 中的字段定义缺失

**Evidence**:

`docs/host/design.md` §17 多次引用 `dispatcher_instance_id` 和 `lane_name` 作为 diagnostic ref：

```text
update dispatch record status = dispatching, record dispatcher_instance_id / lane_name diagnostic refs, commit
```

```text
dispatching 与 dispatcher_instance_id 只用于本机调度诊断、重复派发抑制和 recovery 判断
```

但 design.md 未定义这些字段在 `DispatchRecordRow` 中的具体名称、类型和可空性。当前代码 `dayu/host/durable/state.py:172` 的 `DispatchRecordRow` 没有这些字段。

`Dayu/README.md` 术语表或 `docs/host/design.md` 未定义 `dispatcher_instance_id` 的术语含义（是 host instance id？是 process id？是 dispatcher component id？）。

**Impact**:

Plan 在扩展 `DispatchRecordRow` schema 时可能：
1. 字段命名与 design.md 中的术语不一致
2. 对 `dispatcher_instance_id` 的语义做出与 recovery 预期不同的解释
3. 遗漏必要字段或添加不必要的字段

**Recommendation**:

在 `docs/host/design.md` §17 或新的 schema 子节中定义 Phase 5 `DispatchRecordRow` 新增字段：
- `dispatcher_instance_id`: 发起本次 dispatch 的 Host instance / dispatcher component 标识，用于 recovery scan 判断 orphan
- `lane_name`: 本次 dispatch 使用的 LLM lane 名称，用于诊断
- 明确各字段的可空性（`dispatching` 之前为 NULL，`dispatching` 之后必须非空）

**Blocks plan gate**: NO — plan 可以定义具体字段，但 plan review 必须确认字段定义与 design.md 的语义约束一致。

---

### Finding F5 — MEDIUM

**Severity**: Medium (non-blocking)

**Title**: Phase 5 RunInputBuilder 第一版 provider 最小集合未与延迟到后续 phase 的 provider 显式区分

**Evidence**:

`docs/host/design.md` §23 RunInputBuilder 列出了 7 个 typed provider 示例：
- `CurrentRunFactProvider`
- `SessionContinuityProvider`
- `MemorySnapshotProvider`
- `CompactArtifactProvider`
- `ToolSchemaSnapshotProvider`
- `SceneParameterProvider`
- `PolicySnapshotProvider`

Phase 5 的 plan gate readiness 要求 "RunInputBuilder typed provider protocols 的第一版最小集合，且当前用户输入只能来自 USER_INPUT_ACCEPTED canonical fact"。

由于 Phase 5 尚无 Memory projection（Phase 9）、Compact（Phase 6 Context Governance）、Session continuity（需 Projection Phase 8），实际可工作的 provider 子集与全量列表差距很大。但 design.md 未区分哪些 provider 是 Phase 5 必须实现的、哪些是 stub/future。

**Impact**:

Plan 可能：
1. 过度实现 provider（为 Phase 9 的 MemorySnapshotProvider 提前写 stub，但 stub 语义与未来真实实现不同）
2. 实现不足（遗漏了 Phase 5 闭环必需的 provider）

**Recommendation**:

在 `docs/host/design.md` §23 或 `docs/host/implementation-control.md` Phase 5 条目中明确 Phase 5 第一版 RunInputBuilder 的最小 provider 集合。建议至少包含：
- `CurrentRunFactProvider`（从 EventLog 读取当前 Run 的 canonical facts，至少 USER_INPUT_ACCEPTED）
- `ToolSchemaSnapshotProvider`（从 ToolBundle 投影 tool schemas）
- `SceneParameterProvider`（接收 Service 传入的 system messages / scene params）
- `PolicySnapshotProvider`（从 attempt snapshot 读取 policy refs）
- `MemorySnapshotProvider`、`SessionContinuityProvider`、`CompactArtifactProvider` → Phase 5 stub（返回空/默认值，不读 projection）

**Blocks plan gate**: NO — plan 可以在 plan 中做出该区分，但 plan review 应检查是否与后续 phase 的 provider ownership 一致。

---

### Finding F6 — MEDIUM

**Severity**: Medium (non-blocking)

**Title**: Phase 5 对 `CANCEL_REQUESTED` 幂等键 `(run_id, client_request_id)` 的 dispatch 子集行为未展开

**Evidence**:

`docs/host/design.md` §22 定义了 cancel 幂等规则：

```text
同一 (run_id, client_request_id) cancel 重试必须返回既有结果，不重复 append RUN_CANCELLING。
Run 已是 CANCELLING 时，新的不同 cancel 请求不能重复制造状态迁移。
```

`cancel_session_runs` 的幂等范围是 `(session_id, client_request_id)`。

Phase 5 需要在 `cancel_session_runs` 中实现 "已 dispatch / active running Attempt 走普通 `cancel_run` 传播到 WorkerProxy" 路径。但 Phase 4 只实现了 QUEUED 和 pre-dispatch STARTING 子集。

当前 design.md §22 未说明：
1. `cancel_session_runs` 批量取消时，部分 Run 处于不同 dispatch 状态（pending/waiting_for_lane/dispatching/RUNNING），幂等重试应返回什么？每个 Run 的状态快照？还是 session-level 的聚合结果？
2. 如果 `cancel_session_runs` 第一次调用只完成了部分 Run 的取消（另一部分 Run 处于 `dispatching` 等待 worker cancel 确认），第二次调用（相同 client_request_id）应返回既有结果还是等待确认？

**Impact**:

Plan 可能对幂等重试做出与 §22 的 `cancel_session_runs` 语义不一致的设计。

**Recommendation**:

在 `docs/host/design.md` §22 `cancel_session_runs` 小节中增加幂等重试的 partial completion 语义说明。建议：相同 `client_request_id` 重试返回当前最新 `SessionSnapshot`（反映自上次调用以来的状态变化，如 worker cancel 已确认），不重复发起 cancel 传播，也不阻塞等待未完成 cancel。

**Blocks plan gate**: NO — 属于幂等语义细化，可在 plan 中处理。

---

## Non-Blocking Observations

### O1. 三个用户确认决策的 coherence 验证

P5-D1（Host-owned identity envelope）、P5-D2（dispatch record 状态扩展）、P5-D3（ToolRuntime/WAITING 不进入 Phase 5）三者一致且互不冲突。P5-D1 正确保护了 Engine 分层边界；P5-D2 的状态新增（`waiting_for_lane`、`dispatching`）仅用于 dispatch 诊断/抑制，不越界到 lease/fencing；P5-D3 正确隔离了 Phase 6/7 ownership。

### O2. Architecture boundary preservation

design.md 的 Phase 5 写回（§17 LocalProxy/EngineWorker identity boundary、Phase 5 ToolRuntime/wait boundary、§22 术语统一 `waiting_for_lane`）均正确保持了 UI→Service→Host→Engine 分层，无反向依赖引入。Engine 公共契约未被要求修改。Host durable truth ownership 未被削弱。

### O3. Residual risk ownership 清晰

Phase 5 codex review 的 residual risks 节正确追踪了 RemoteProxy（Phase 14）、ToolRuntime（Phase 6）、WAITING cancel（Phase 7）、RECOVERING dispatch cancellation（Phase 11）的所有权。design.md 和 implementation-control.md 中均有对应标注。

### O4. Plan gate readiness checklist coverage

codex review 列出的 6 项 plan gate readiness 要求覆盖了 RunInputBuilder、LocalProxy/EngineWorker envelope、dispatch record schema、EngineEvent 映射、cancel 子集和 validation matrix。但如 F1/F2 所示，terminal closeout policy 和 cancel-dispatch race 的缺失使其中第 4 项（terminal closeout 策略）和第 5 项（active dispatch cancel）的 plan 基础不完整。

---

## Summary

| ID | Severity | Title | Blocks Plan Gate |
|----|----------|-------|-------------------|
| F1 | Blocker | Stream EOF/worker crash closeout policy 缺失判定标准 | YES |
| F2 | Blocker | `dispatching` 窗口 cancel 行为未定义 | YES |
| F3 | High | EngineEvent 映射缺少 canonical payload 定义 | NO |
| F4 | High | DispatchRecordRow 新增 diagnostic 字段未定义 | NO |
| F5 | Medium | RunInputBuilder Phase 5 最小 provider 集合未显式区分 | NO |
| F6 | Medium | `cancel_session_runs` 幂等 partial completion 语义未展开 | NO |

**Gate verdict**: 2 blocking findings. Phase 5 design refinement 不满足 plan gate readiness。F1 和 F2 修复后，需 re-review 确认方可进入 Phase 5 plan gate。

F3-F6 不阻塞 plan gate，但建议在 plan 阶段解决，并作为 plan review 的检查项。

---

## Review Traceability

- 阅读了 `docs/host/design.md` §3, §13, §13.4, §14, §15, §16, §17, §18, §22, §23, §24, §25
- 阅读了 `docs/host/implementation-control.md` Phase 5 条目及全文 Phase Map
- 阅读了 `docs/reviews/gateflow-phase-design-host-p5-codex-20260514.md` 全文
- 检查了 `dayu/host/durable/state.py` 中 `DispatchRecordStatus`、`DispatchRecordRow` 当前定义
- 检查了 `dayu/host/durable/run_transition.py`、`dayu/host/admission.py` 中 dispatch record 的当前使用
- 检查了 `git diff HEAD` 确认 design.md 和 implementation-control.md 的未提交变更
