# Host Phase 3 Design Refinement Review

- **gate name**: Phase 3 design discussion / phase design refinement
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **reviewer**: Codex handoff reviewer；非 Gateflow controller
- **artifact path**: `docs/reviews/gateflow-phase-design-host-p3-codex-20260514.md`
- **conclusion**: not-ready；Phase 3 动机成立，但进入 plan gate 前必须先裁决 dispatch record / dispatch intent 边界，并把 Phase 3 的最小 durable state/index/CAS 契约收敛到设计真源。

## Reviewed Sources

- `docs/host/implementation-control.md`
  - Phase 3 目标、范围、进入条件、禁止项与退出条件：421-476。
  - 强制约束：尤其是不得让 dispatch / remote / sink 写 Run / Attempt / EventLog，不得引入 lease / fencing，不得让 implementation agent 自行选择 material open question。
  - 当前状态：Phase 2 completed，后续入口为 Phase 3 design discussion / plan gate。
- `docs/host/design.md`
  - §5 Session 生命周期：`OPEN` / `CLOSED` 行为、close 与 purge 语义，300-340。
  - §6 Session Slot：slot 幂等与并发约束，342-376。
  - §7 Run 生命周期：状态集合、终态与 `RUNNING + Attempt STARTING` 合法组合，378-417。
  - §8 Attempt 生命周期：状态集合、终态与旧 Attempt 不 resume，419-469。
  - §9 Admission 与多进程并发：active Run、幂等范围、SQLite/CAS、多进程、promotion 与输入持久化顺序，471-534。
  - §9.1 状态迁移契约：transition matrix、`RUN_STARTED`、`ATTEMPT_STARTED` 与 startup 边界，536-570 及后续 cancel / promotion 竞态规则。
  - §10 Durable Store：EventLog + state index 同事务、CAS-style update、semantic table ownership。
  - §10.1 / §11：Host handle / public API / command path / idempotency 契约，760-875。
  - §12 Follow-up 与 Steer：queue / steer 行为、terminal / steer 竞态。
  - §17 Worker dispatch semantic contract：dispatch record `pending`、lane 后 recheck、`dispatching` 与 WorkerProxy 调用边界，1579-1613。
  - §22 Cancel：queued / waiting / starting / dispatching cancel 语义。
  - §27 / §27.1 Recovery：recovery 输入、positive orphan proof、dispatch record 最小语义。
- `dayu/README.md`
  - 架构与术语真源：Host 拥有 session / run / attempt lifecycle、admission、EventLog；Engine 不理解 Host 治理，20-38。
  - `Run status` / `Attempt status` / `active Run` / `durable queue` / `promotion` / `admission` / `dispatching` 术语，46-103。
- 当前代码事实
  - `dayu/host/api.py` 已有 `SessionStatus`、`RunStatus`、`AttemptStatus`、`FollowupBehavior` 等公共类型，86-188。
  - `dayu/host/durable/schema.py` 明确 Phase 2 schema 只创建 EventLog、idempotency、payload、host instance foundation，不创建 Session / Run / Attempt / wait / projection / outbox / memory / purge 表，1-31。
  - `dayu/host/durable/event_log.py` 明确 EventLog primitive 不实现 command path、EngineEvent ingest、projection 或 Session / Run / Attempt 状态索引，1-8。
  - `dayu/host/durable/idempotency.py` 明确 idempotency primitive 不解释 command path 语义，1-6。
  - `dayu/host/durable/transaction.py` 明确 transaction runner 只负责 `BEGIN IMMEDIATE`、retry、commit 与 after-commit callback，不实现业务语义，1-7。
  - `tests/host` 当前覆盖 public contracts、durable foundation、EventLog、idempotency、payload、liveness 与 import boundary；没有 Session / Run / Attempt 状态机、admission、queue promotion 或 dispatch record 测试。

## Motivation Evidence

Phase 3 动机成立，且没有被高估。

直接证据：

- 项目术语真源规定 Host 拥有 session / run / attempt 生命周期、admission、取消、恢复和 EventLog；Engine 只执行单次 request，不理解 Host 治理。见 `dayu/README.md` 29-32、55-66。
- `docs/host/design.md` §9 明确同一 Session 同时最多一个 active Run，queued Run 必须 durable，promotion 必须以 accepted `event_sequence` FIFO 并使用 SQLite transaction / CAS。见 471-522。
- Phase 3 总控条目要求实现 Session / Session slot tables、Run / Attempt tables、active index、queue index、transition service、admission service、promotion service，同时禁止 Engine dispatch / ToolRuntime / Projection / Remote transport。见 `docs/host/implementation-control.md` 421-472。
- 当前代码只有公共 status enum 和 durable foundation；schema 明确尚未创建 Session / Run / Attempt 表，EventLog 与 idempotency primitive 也明确不解释 command path 或状态索引。见 `dayu/host/durable/schema.py` 1-31、`event_log.py` 1-8、`idempotency.py` 1-6。

因此 Phase 3 不是表面修复，也不是过早优化；它是后续 Phase 4 public command path、Phase 5 dispatch、Phase 7 wait、Phase 11 recovery 的基础真源。

## Scope / Non-goals

Phase 3 应包含：

- Session / slot lifecycle durable state 与幂等。
- Run / Attempt durable rows、active Run index、queue index。
- typed state transition service。
- admission service：start / queue / reject / attach active / steer precondition 的可测试基础。
- durable queue FIFO promotion。
- CAS-style transition preconditions 与同事务 EventLog + state index 更新。
- 不启动 Engine 的情况下创建 Attempt `STARTING` 与 durable dispatch intent / dispatch record 的最小事实行。
- cancel queued / cancel pre-dispatch starting / terminal closeout / promotion trigger 的内部 transition service 测试闭环。

Phase 3 不应包含：

- Engine dispatch、WorkerProxy / LocalProxy / RemoteProxy、EngineEvent ingest、lane acquire、scheduler loop。
- ToolRuntime、wait record、projection、memory、context governance、recovery scan。
- public API full facade。Phase 3 可以实现内部 service / command primitives 以支撑测试，但不应把 Phase 4 public handle / request facade 夹带进来。

## Design Sufficiency Assessment

| 检查项 | 结论 | 证据与缺口 |
| --- | --- | --- |
| 状态迁移 | 部分充分 | §9.1 有完整终态矩阵，覆盖 start、queue、promotion、cancel、terminal、wait、steer、recovery；但它混合 Phase 3 / 5 / 7 / 10 / 11 能力，没有明确 Phase 3 must implement subset 与 fake/internal terminal closeout 测试入口。 |
| canonical facts | 部分充分 | §9.1 和 §13.3 定义事件类型与大类 payload；但 Phase 3 直接要实现的 `SESSION_CREATED`、`RUN_ACCEPTED`、`RUN_QUEUED`、`RUN_STARTED`、`ATTEMPT_STARTED`、`CANCEL_REQUESTED`、`ATTEMPT_CANCELLED`、`RUN_CANCELLED`、terminal facts 的最小 typed payload、event id 派生规则和 idempotency result refs 仍未收敛。 |
| 状态索引 | 不充分 | §10 只说明 active Run index / queue index 属于 state machine owner，§9 说明 active Run 与 queued Run 不变量；但未裁决采用 `sessions.active_run_id`、partial unique index on runs、独立 active table、queue ordinal / accepted sequence materialization 等具体 schema/index invariant。 |
| CAS preconditions | 不充分 | 文档要求 CAS-style transition，但没有按每个 Phase 3 transition 写出 compare columns、expected current status、rowcount=1 failure semantics、first-committer-wins 返回路径。promotion / cancel 竞态只描述语义，不足以直接生成 typed transition tests。 |
| idempotency scope | 部分充分 | §9、§11 明确各 operation 幂等范围；现有 primitive 支持 `(scope_kind, scope_id, idempotency_key)`。缺口是 Phase 3 的 scope_kind / scope_id 命名、semantic digest 输入字段、result_kind / result_ref 约定、与 first event ref 的绑定还未写入设计。 |
| queue promotion | 部分充分 | FIFO by accepted `event_sequence`、无 active Run 才 promotion、cancel / promotion 竞态规则明确；缺口是 promotion trigger 是否在 Phase 3 同事务级联执行、after-commit wakeup 只是 no-op signal 还是内部同步调用、以及多进程 loser 如何返回 snapshot / retry decision。 |
| Session slot | 部分充分 | §6 明确 `(scope, slot_key)` 唯一、ensure 并发返回同一 Session、create bind_slot 可重绑定；缺口是避免并发 ensure 留下孤儿 Session 的具体 transaction pattern / unique-conflict recovery，以及 create_session bind_slot 的旧 binding 历史是否需要 canonical fact 或只更新 slot index。 |
| cancel 与 promotion 竞态 | 部分充分 | §9 和 §22 明确 first-committer-wins，queued cancel 不创建 Attempt，starting pending cancel 不通知 worker；缺口是 Phase 3 是否必须实现 dispatch record `pending/cancelled` 来让 pre-dispatch cancel 可测试。 |
| 多进程测试矩阵 | 不充分 | implementation-control 只要求同 Session 并发 start/follow-up/queue promotion；追踪区还要求重复 `client_request_id`、active slot admission、cancel/terminal race、EventLog sequence 单调。缺少 handoff-ready 的 explicit matrix：进程数、输入组合、expected rows/events/status、CAS loser expected behavior。 |

总体判断：设计已经足够证明 Phase 3 应做，但还不足以直接进入 handoff-ready plan。缺口不是代码实现细节，而是会影响 schema、state transition service 边界、idempotency digest、dispatch intent 表与测试矩阵的 material design choices。

## Blocking Questions

### BQ1: Phase 3 是否创建最小 dispatch intent / dispatch record durable row？

- **问题**: Phase 3 禁止 Engine dispatch，但 §9 / §9.1 要求 promotion 或 admitted start 与 `RUN_STARTED`、`ATTEMPT_STARTED`、Attempt row 创建、dispatch record 创建同事务完成。Phase 3 应不应实现最小 dispatch record 表，并只写 `pending` / `cancelled` 等 durable intent 状态，把 scheduler / lane / WorkerProxy / `dispatching` 使用留到 Phase 5？
- **为什么阻塞**: `ATTEMPT_STARTED` 在术语真源中表示 Host 已 durable 创建 dispatch intent；`cancel_run` on pre-dispatch starting 也依赖 dispatch record `pending` / `waiting_for_lane` 判定。若 Phase 3 不创建 dispatch record，则 `Attempt STARTING` 缺少 durable dispatch intent，cancel starting 和 recovery 后续依赖会被迫用 Attempt row 代替 dispatch intent，破坏 §17 / §27 的边界。若 Phase 3 完整实现 scheduler / lane，则违反 Phase 3 禁止 Engine dispatch 与 Phase 5 拥有 dispatch scheduler 的范围。
- **推荐决策**: 是。Phase 3 只定义并实现最小 dispatch intent / dispatch record durable row，作为 Attempt startup truth 的一部分；Phase 3 只写 `pending`、`cancelled`，并允许 schema/enum 预留 `waiting_for_lane`、`dispatching`、`accepted`、`failed` 但不得使用 scheduler / lane / WorkerProxy。Phase 5 再实现 dispatch scheduler、lane acquire、durable recheck、`dispatching`、WorkerProxy 与 `ATTEMPT_RUNNING`。
- **不决策风险**: plan agent 会在“无 dispatch record 的 STARTING Attempt”和“提前实现 Phase 5 dispatch”之间自行选择；前者导致 cancel / recovery truth 不完整，后者造成 scope creep 和 Engine dispatch 越界。
- **建议写回位置**: `docs/host/design.md` §9 durable queue promotion 后、§9.1 Attempt startup 边界后、§17 Worker dispatch semantic contract 前。

### BQ2: Phase 3 的 state index / CAS / idempotency 最小 contract 是否需要在 design.md 中补齐？

- **问题**: 是否在进入 plan gate 前，由 controller 决定并写回 Phase 3 最小 durable schema/index contract：session table、session slot table、run table、attempt table、active Run index、queue index、dispatch record intent row、operation idempotency scope_kind/scope_id/result_ref、以及每个 Phase 3 transition 的 CAS preconditions？
- **为什么阻塞**: 当前设计给出语义，但未指定 active slot 如何被 SQLite 约束表达，也未指定 queue FIFO 的 durable ordering row、CAS compare columns、idempotency digest/result refs。Phase 3 是 schema / state-machine change；这些选择会直接影响 DDL、transaction shape、multi-process correctness 和测试矩阵，不能留给 implementation agent 即兴决定。
- **推荐决策**: 是。进入 plan gate 前补一节“Phase 3 durable state/index contract”，明确：
  - `sessions(session_id, status, created_at, closed_at?, current_slot refs?)`
  - `session_slots(scope, slot_key, session_id, bound_at, binding_event_sequence)`，unique `(scope, slot_key)`
  - `runs(run_id, session_id, status, client_request_id, accepted_event_sequence, current_attempt_id?, source_run_id?, source_run_relation?, terminal_event_id?)`
  - active invariant 用 partial unique index 或独立 active table 二选一；推荐 partial unique index on `(session_id)` where run status in active states，并配合 `runs.current_attempt_id`
  - queue FIFO 用 `accepted_event_sequence` 排序，不引入独立内存 queue
  - `attempts(attempt_id, run_id, execution_id, status, started_event_id, terminal_event_id?)`
  - `attempt_dispatch_records(dispatch_record_id, run_id, attempt_id, execution_id, status, worker_kind, owner_host_instance_id?, created_at, updated_at)`；Phase 3 只使用 `pending/cancelled`
  - operation idempotency scope naming 与 semantic digest 输入字段
  - CAS failure 返回重新读取后的 structured result / conflict / invalid_state 规则
- **不决策风险**: 不同 slice 可能分别发明 active index、queue index 和 dispatch intent 表，导致 CAS loser 行为、多进程测试和后续 Phase 5 / 11 recovery contract 不可对齐。
- **建议写回位置**: `docs/host/design.md` §10 Durable Store durable table ownership 后，或 §9.1 后新增 “Phase 3 state index contract” 小节。

### BQ3: Phase 3 plan 是否只覆盖 Phase 3 transition subset，并把跨 phase matrix 行标记为 future-owner？

- **问题**: §9.1 matrix 覆盖 Engine final answer、Engine failure、context compaction、Tool awaiting、resolve_wait、steer、retry/replay、recovery scan/dispatch 等后续 phase。Phase 3 plan 是否应只实现 start / queue / promotion / cancel queued / cancel pre-dispatch starting / internal terminal closeout primitives，并把其他行作为 future-owner validation references？
- **为什么阻塞**: 如果 plan 直接按 §9.1 全矩阵实现，会越界进入 Phase 5 / 7 / 10 / 11。若 plan 只实现 admission 但不实现 terminal/cancel closeout primitives，又无法满足 Phase 3 退出条件“正确接受、排队、启动、取消和终态收口 Run / Attempt state indexes”，也无法测试 promotion trigger。
- **推荐决策**: 是。Phase 3 只实现不需要 Engine / ToolRuntime / wait / recovery 的 transition subset：
  - create / ensure / close Session 的 durable lifecycle primitives；
  - start_run-like internal admission primitive；
  - submit_followup(queue)-like internal admission primitive；
  - queue promotion；
  - cancel queued；
  - cancel active pre-dispatch `Attempt STARTING + dispatch_record pending`；
  - internal terminal closeout helper for tests and later ingest reuse，限定为 direct transition service，不实现 EngineEvent ingest；
  - after terminal / cancel release active slot and trigger promotion check。
  后续 phase rows 只作为 invariants，不在 Phase 3 实现。
- **不决策风险**: plan slice 会过粗，implementation agent 可能提前写 Engine ingest / wait / recovery，或为了避免越界而漏掉 Phase 3 必须验证的 terminal -> promotion 闭环。
- **建议写回位置**: `docs/host/implementation-control.md` Phase 3 范围 / 不做 / 退出条件，和 `docs/host/design.md` §9.1 前新增 “Phase 3 owned transition subset”。

## Non-blocking Risks

1. **`create_session(bind_slot=true)` 是否为旧 slot binding 写 canonical fact**  
   - **working assumption**: Phase 3 可以只写 `SESSION_CREATED`，slot rebinding 是 state index 更新和 snapshot 事实，不新增 canonical event；slot 历史可由 Session / slot row 和 audit/projection 后续解释。  
   - **风险**: 如果后续 audit 要解释 slot rebind 历史，缺少 dedicated canonical event 可能需要补事件类型。  
   - **回看触发**: Phase 4 public API / audit phase 需要按 slot 追踪“哪个请求把 slot 从旧 Session 重绑定到新 Session”。

2. **`start_run` policy=`reject` / `attach_active` 是否在 Phase 3 实现**  
   - **working assumption**: Phase 3 transition service 支持 admission policy view 输入，但第一版 tests 至少覆盖 queue；reject / attach_active 可作为 state-machine branch 返回，不要求 public facade。  
   - **风险**: 若完全不测 reject / attach_active，Phase 4 public command path 可能发现 admission branch 未稳定。  
   - **回看触发**: Phase 4 plan 需要暴露 `start_run` 的 queue_policy 全语义。

3. **Session close 与 queued promotion 的关系**  
   - **working assumption**: 已 close Session 不接受新输入，但 close 前已 queued Run 仍可 promotion，符合 design.md 318。  
   - **风险**: UI 可能误以为 close 会停止 queued work。  
   - **回看触发**: Phase 4 close_session public API 文档 / tests。

4. **多进程测试容量**  
   - **working assumption**: Phase 3 至少做 SQLite shared DB 多进程 smoke，覆盖 active slot invariant、重复 idempotency、queue promotion 和 EventLog sequence；更重压测留到 Phase 11 hardening。  
   - **风险**: 只做 smoke 可能漏掉高并发 starvation 或 busy retry 参数问题。  
   - **回看触发**: Phase 11 multi-process hardening 或实际 CI flakes。

## Recommended Design Refinements

以下是建议写回设计真源的文本方向；本 artifact 不直接修改 `docs/host/design.md` 或 `implementation-control.md`。

### 目标位置：`docs/host/design.md` §9.1 后

建议新增：

```md
Phase 3 owned transition subset:

Phase 3 只实现不需要 Engine dispatch / ToolRuntime / wait / recovery 的状态机闭环：

- Session create / ensure / close durable lifecycle。
- start / follow-up queue admission：append `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_QUEUED` 或 `RUN_STARTED`、`ATTEMPT_STARTED`。
- queue promotion：`QUEUED -> RUNNING`，创建 Attempt `STARTING` 与 dispatch record `pending`。
- cancel queued：`QUEUED -> CANCELLED`。
- cancel pre-dispatch starting：`Run RUNNING + Attempt STARTING + dispatch_record pending -> Run CANCELLED + Attempt CANCELLED + dispatch_record cancelled`。
- internal terminal closeout helper：仅供 Phase 3 状态机测试和后续 ingest 复用，append concrete terminal facts and release active slot；不实现 EngineEvent ingest。
- terminal / cancel 成功释放 active slot 后，必须同步或 after-commit 触发同 Session promotion check；promotion check 本身必须重新进入短事务并使用 CAS。

Engine final answer / failure ingest、Tool awaiting、resolve_wait、steer, retry/replay, context compaction and recovery rows remain future-owner transition references unless explicitly owned by later phase plans.
```

### 目标位置：`docs/host/design.md` §10 Durable Store 或 §9.1 后

建议新增：

```md
Phase 3 durable state/index contract:

Session / Run / Attempt state indexes are Host governance truth indexes updated in the same transaction as canonical EventLog facts.

- `session_slots` has unique `(scope, slot_key)`; ensure_session creates Session and binding in one transaction and handles unique-conflict by re-reading the winning binding.
- active Run invariant is enforced by SQLite, not process memory. First version should use either a partial unique index on `(session_id)` for active Run statuses or an explicit active-run table; the chosen representation must be the single owner of active-slot CAS.
- queued Run FIFO is ordered by the `USER_INPUT_ACCEPTED` / `RUN_ACCEPTED` accepted `event_sequence`; no in-memory queue ordering is truth.
- `ATTEMPT_STARTED` requires an Attempt row `STARTING` and a dispatch record row in the same transaction. Phase 3 writes only durable intent status `pending` and cancellation status `cancelled`; scheduler / lane / WorkerProxy statuses are consumed by Phase 5.
- Every transition service must express CAS preconditions as expected current Session / Run / Attempt / dispatch record statuses and treat rowcount=0 as CAS loser, followed by re-read and structured conflict / invalid_state / current snapshot.
- Operation idempotency scope_kind / scope_id / idempotency_key and semantic digest inputs must be fixed per operation before implementation.
```

### 目标位置：`docs/host/implementation-control.md` Phase 3 关键设计问题 / 验证要求

建议补充：

```md
- 必须确认 Phase 3 creates minimal dispatch intent / dispatch record row but does not run scheduler, lane acquire, WorkerProxy, LocalProxy, RemoteProxy or Engine.
- 必须确认 active Run index representation and CAS loser behavior before plan gate.
- multi-process tests must cover:
  - concurrent ensure_session for same slot returns one Session and no orphan Session;
  - concurrent start/follow-up for same Session leaves at most one active Run;
  - duplicate `(session_id, client_request_id)` returns same Run and different digest conflicts;
  - active Run plus queue creates durable queued Run ordered by accepted event_sequence;
  - terminal/cancel releases active slot and promotes exactly one queued Run;
  - cancel queued vs promotion first-committer-wins;
  - cancel pre-dispatch starting marks dispatch record cancelled and does not dispatch;
  - EventLog event_sequence remains globally monotonic across processes.
```

## Phase 3 Plan Entry Recommendation

**不建议进入 plan gate。**

Phase 3 的动机成立，且设计方向基本正确；但当前 `docs/host/design.md` 还没有把 Phase 3 的 material implementation choices 收敛到足够稳定的 contract。尤其是 dispatch intent / dispatch record 的 phase ownership、active index representation、CAS preconditions、idempotency scope naming 和 multi-process test matrix 都会影响 schema、状态迁移和后续 Phase 5 / Phase 11 依赖。

推荐 controller 先裁决 BQ1-BQ3，并把决策写回 `docs/host/design.md` 与 Phase 3 条目；之后再生成 handoff-ready plan。
