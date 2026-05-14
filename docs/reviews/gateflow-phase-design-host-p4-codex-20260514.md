# Gateflow Phase Design - Host P4 Public API Command Path

## 结论

needs-design-fix

Phase 4 的动机成立：总控文档明确把 request / response / error shape、`submit_followup(queue)` active Run 竞态、`submit_followup(steer)` conflict / invalid_state shape、以及 public functions 完整行为 vs 冻结契约边界列为进入 plan gate 前必须确认的问题。现有设计与代码已经足够支撑 session lifecycle、start / follow-up queue、queued / pre-dispatch cancel、EventLog cursor read 的一部分 public facade plan，但还不足以让 planning agent 写出完整 code-generation-ready plan；关键缺口集中在 public response/error contract 和 deferred function 行为边界。

## 直接证据

control_doc 证据：

- `docs/host/implementation-control.md:487-543` 将 Phase 4 定义为 Host Public API Command Path；目标包含函数式 command path、HostCallContext、OperationContext、幂等语义、snapshot 读取、command path / background runtime facet 分离；进入条件是确认 API request / response / error shape 足够实现多入口稳定边界。
- `docs/host/implementation-control.md:515-519` 直接列出三个 design gate 问题：`submit_followup(queue)` 如何在事务内吸收 active Run 竞态、`submit_followup(steer)` 的 conflict / invalid_state 返回 shape、以及哪些 public functions 完整实现、哪些只稳定公共契约。
- `docs/host/implementation-control.md:541-543` 要求后续 phase 可依赖 public command path、Host handle、typed options、snapshot shape、API idempotency、`get_run` / `get_session` / `stream_run_events` 的 snapshot 与 cursor contract；同时要求 `resolve_wait` envelope 在 Phase 4 稳定、语义由 Phase 7 落地，`purge_session` envelope / result / idempotency contract 在 Phase 4 稳定、destructive cleanup 由 Phase 15 落地。
- `docs/host/implementation-control.md:1299-1302` 将 P3 未导出的 public facade、API 级 queued cancel / promotion race 覆盖、以及 `attach_active` 的 public audit / read-model 表达转交给 Phase 4 owner。
- `docs/host/implementation-control.md:1424-1426` 记录当前入口仍是 Phase 4 design discussion / design refinement，Phase 4 尚未进入 plan gate。

design_doc 证据：

- `docs/host/design.md:694-744` 定义 Host handle / composition root：公共函数接收的 host 是 command path handle，不是 God object；command path 与 background runtime supervisor 必须暴露不同 facet；mutating command 路径必须 durable transaction -> EventLog / state index -> commit -> after-commit wakeup。
- `docs/host/design.md:817-844` 定义函数式公共接口集合，包括 session APIs、run APIs、cancel、`submit_followup`、retry / replay、`resolve_wait`。
- `docs/host/design.md:848-902` 定义 mutating request 必须携带 `HostCallContext`，幂等范围由具体 request owns，并且幂等判断必须在 durable transaction 内完成。
- `docs/host/design.md:962-970` 定义 `SubmitFollowupRequest` 字段：`session_id`、`client_request_id`、`input`、`behavior: queue | steer`、`target_run_id?`。
- `docs/host/design.md:996-1008` 定义各 run 接口语义；其中 `submit_followup(queue)` 要由 Host admission 在同一事务内决定排队或直接启动，`submit_followup(steer)` 必须命中目标 active Run 并切换 Attempt。
- `docs/host/design.md:1028-1034` 定义 snapshot 最小语义，但 `FollowupSnapshot` 只写“accepted input ref、behavior、target run / queued run、current cursor”，没有明确 queue 分支在无 active Run 时如何表达“直接启动的新 Run”。
- `docs/host/design.md:1036-1050` 定义错误分类至少包含 `not_found`、`invalid_state`、`conflict`、`idempotency_conflict`、`permission_denied`、`internal_error`，但没有定义结构化 error detail payload。
- `docs/host/design.md:1058-1066` 明确 queue follow-up 不应让 active Run 竞态表现为 `invalid_state` / `conflict`；active 存在时排队，无 active 时创建并启动新 Run。
- `docs/host/design.md:1068-1132` 定义完整 steer 终态语义、RUNNING / WAITING steer 路径和竞态规则；这些语义依赖 cancellation source、wait record、Attempt stop、message rebuild、LocalProxy / RemoteProxy dispatch 等后续能力。
- `docs/host/design.md:1117-1123` 要求 steer 错误处理：没有 active Run 返回 `invalid_state`，`target_run_id` 不是当前 active Run 返回 `conflict` 且错误响应应包含当前 active Run 与目标 Run 状态摘要，terminal 或不可 steer 状态返回 `invalid_state`。
- `docs/host/design.md:2068-2123` 定义 cancel 治理；queued 和 pre-dispatch STARTING 可直接收口，dispatching / active worker、WAITING、RECOVERING 等路径依赖后续 dispatch / wait / recovery 能力。

代码现状证据：

- `dayu/host/api.py:1-5` 明确当前模块只定义公共 request、snapshot、status、error 与 context 类型，不实现 command path、durable store、EventLog、dispatch、policy provider 或 Engine 调用路径。
- `dayu/host/api.py:176-187` 的 `HostApiErrorCode` 只有 `not_found`、`invalid_state`、`conflict`、`idempotency_conflict`、`permission_denied`、`internal_error`；`dayu/host/api.py:1148-1178` 的 `HostApiError` 只有 `code`、`message`、`retryable`，没有可承载 steer conflict 状态摘要的结构化 detail 字段。
- `dayu/host/api.py:674-727` 已校验 `SubmitFollowupRequest` 的 queue / steer 字段组合：steer 必须有 `target_run_id`，queue 不得有 `target_run_id`。
- `dayu/host/api.py:990-1044` 的 `FollowupSnapshot` 对 queue 强制要求 `queued_run_id`，且 steer 强制要求 `target_run_id`；该 shape 不能无歧义表达 `submit_followup(queue)` 在无 active Run 时“创建并启动新 Run”的结果。
- `dayu/host/admission.py:1-9` 明确 internal admission 已实现 start_run、`submit_followup(queue)`、cancel、terminal closeout、promotion，但不实现 public facade、scheduler、lane、WorkerProxy、Engine dispatch、steer、retry、replay、wait 或 recovery。
- `dayu/host/admission.py:398-429` 暴露内部 `submit_followup_queue`；`dayu/host/admission.py:695-746` 在同一 write transaction 内读取 active Run，有 active 时 `_create_queued_admission_result`，无 active 时 `_create_running_admission_result`。这直接支撑 queue active race 吸收。
- `dayu/host/admission.py:1768-1805` 的 follow-up queue semantic digest 不包含 `resolved_execution_target`，与 `dayu/host/README.md:62` 记录一致；这意味着 Phase 4 public facade plan 必须明确 execution target policy 归一化是 facade / policy responsibility，不能由 caller 直接决定 digest 语义。
- `dayu/host/durable/schema.py:381-385` 已有同 Session active Run partial unique index，active 状态集合为 running / waiting / cancelling / recovering；`dayu/host/durable/state.py:1275-1350` 的 queued promotion CAS 也防止 promotion 时产生第二个 active Run。
- `tests/host/test_admission_multiprocess.py:152-219` 覆盖同 Session 并发 start / follow-up 至多一个 running Run，其余 queued；`tests/host/test_admission_multiprocess.py:311-361` 覆盖 queued follow-up 释放 active 后按 accepted event_sequence FIFO promotion。
- `dayu/host/durable/session_lifecycle.py:95-170` 已有 internal `ensure_session`、`create_session`、`close_session` helper，并支持 transaction runner 与幂等 digest；`dayu/host/durable/state.py:1731-1755` 已可由 durable row 构造 `SessionSnapshot`。
- `dayu/host/durable/event_log.py:159-207` 已有 EventLog append / read primitive 和 `read_events_after(cursor, limit)`，但 public `stream_run_events` 需要额外定义过滤目标 Run、limit 默认 / 上限、EventLog row 到 `HostEventView` 的转换与 cursor contract。
- `dayu/host/README.md:49` 明确 durable foundation 当前不实现 public Host command facade；`dayu/host/README.md:53-67` 明确 admission 是内部 command 编排模块，不是 public facade，且不实现 steer、retry / replay、wait cancellation、recovery cancellation 或 session-scope cancel facade。
- `dayu/host/README.md:93-100` 仍将 Host command function、public facade、policy provider set、dispatch scheduler、WorkerProxy / LocalProxy / RemoteProxy、wait cancellation、recovery classifier 等列为未实现。

## Blocking Questions

1. `FollowupSnapshot` 如何表达 `submit_followup(queue)` 在无 active Run 时直接启动的新 Run？
   - 当前设计要求 queue 无 active 时创建并启动新 Run；现有 public shape 只有 `queued_run_id`，且 queue 分支强制存在。planning agent 如果直接实现，会被迫把 running Run id 塞进 `queued_run_id`，或临时改字段名 / 增字段，都会改变 public contract。

2. steer conflict / invalid_state 的结构化错误 detail shape 是什么？
   - 设计要求 `target_run_id` 不是当前 active Run 时返回 `conflict`，错误响应包含当前 active Run 与目标 Run 状态摘要；现有 `HostApiError` 只有 code/message/retryable。没有 detail type、字段、摘要粒度或 snapshot ref 规则，plan 无法稳定测试和实现。

3. Phase 4 对 `submit_followup(steer)` 是冻结 public contract 并返回明确 unsupported，还是实现可观察的 steer admission 子集？
   - 完整 steer 设计依赖 cancellation source、wait record、Attempt stop、message rebuild、LocalProxy / RemoteProxy dispatch。Phase 4 范围禁止 Engine dispatch、wait adapter、Remote transport；现有 error code 也没有 `unsupported`。如果只冻结 envelope，必须先定义 public error code / error detail / retryable 语义，不能让 implementation agent 选择 `invalid_state` 或抛 `NotImplementedError`。

4. Phase 4 public functions 的完整行为清单与 deferred 行为清单需要写成设计真源或 plan 前置约束。
   - 已有内部能力支撑 `ensure_session`、`create_session`、`close_session`、`start_run`、`submit_followup(queue)`、queued / pre-dispatch `cancel_run`、`get_session` 的基础实现；但 `cancel_session_runs`、`retry_run`、`replay_run`、`resolve_wait`、`purge_session`、完整 active cancel / wait / recovery cancel、steer 都存在后续 phase owner。若没有 frozen signature + explicit unsupported / deferred contract，plan 会混入后续 phase 语义或发明兼容行为。

5. `stream_run_events` 的 Phase 4 read contract 还缺少可编码细节。
   - 设计只说从全局 `event_sequence` cursor 补读目标 Run 事件；EventLog primitive 只提供全局 `read_events_after(cursor, limit)`。Phase 4 plan 需要固定 `limit` 参数是否进入 public signature、默认 / 最大 limit、是否过滤 run_id、是否包含 session-level 事件、`next_cursor` 在过滤场景下取最后扫描事件还是最后返回事件，否则 Phase 8 依赖的 cursor contract 不稳定。

## Design Refinement Recommendations

- 写回 `FollowupSnapshot` 终态 shape：建议将 queue 分支结果从 `queued_run_id` 改为可表达真实状态的 `accepted_run_id` + `accepted_run_status`，或明确 `queued_run_id` 重命名为 `created_run_id` 并包含 `RunStatus`。不要让 running Run id 进入名为 `queued_run_id` 的字段。
- 写回 `HostApiError` 结构化 detail contract：至少为 steer conflict 定义 typed detail，例如 `SteerConflictDetail(target_run_id, target_run_status, current_active_run_id, current_active_run_status)`；如果不想让 `HostApiError` 泛化为 god bag，可定义受限 union / Protocol，并禁止无结构 payload。
- 写回 Phase 4 对 steer 的明确边界：推荐 Phase 4 只冻结 `SubmitFollowupRequest(behavior=steer)` envelope、validation 与错误 contract，不实现 steer 行为；public facade 在 steer 路径返回稳定的 `unsupported` 或等价结构化错误。若坚持不新增 `unsupported` code，则必须解释为什么 `invalid_state` 可以代表“能力未落地”而不污染目标对象状态语义。
- 写回 public function behavior matrix：每个函数标明 Phase 4 完整实现、Phase 4 signature/envelope only、或 later phase owner。matrix 必须包含 `ensure_session`、`create_session`、`get_session`、`close_session`、`purge_session`、`start_run`、`get_run`、`stream_run_events`、`cancel_run`、`cancel_session_runs`、`submit_followup(queue)`、`submit_followup(steer)`、`retry_run`、`replay_run`、`resolve_wait`。
- 写回 `stream_run_events` cursor contract：固定 signature 是否包含 `limit`、limit 上限、过滤语义、empty result 的 `next_cursor`、事件 payload ref 映射到 `HostEventView` 的规则。
- 写回 `attach_active` public 表达：若 Phase 4 暴露 `start_run(queue_policy=attach_active)`，必须决定返回的 `RunSnapshot` / event stream 是否记录 attach request；若需要可查询事实，必须先定义 canonical event shape；若不记录，必须在 plan 中禁止临时发明 EventLog 事件。

## Plan Gate Requirements

- Implementation slices 必须先做 public command handle / factory / typed options，只暴露 command path facet，不把 background runtime supervisor、durable internals、admission service、policy provider set 混成 public god object。
- Session APIs slice 必须接入 internal session lifecycle helper，实现 `ensure_session`、`create_session`、`get_session`、`close_session`，保留 durable transaction 内幂等语义，并补 API 级 repeated call / conflict / not_found / closed state tests。
- Run / follow-up / cancel slice 必须接入 `HostAdmissionService`，实现 `start_run`、`submit_followup(queue)`、Phase 4 支持状态内的 `cancel_run`，并把 `RunAdmissionResult` / `CancelRunResult` 转成 public `RunSnapshot` / refined `FollowupSnapshot`。
- Read API slice 必须实现 `get_run`、`get_session`、`stream_run_events` 的 public facade，固定 EventLog row 到 public view 的映射和 cursor contract；不得启动 execution、promotion 或 projection。
- Deferred facade slice 必须为 `submit_followup(steer)`、`retry_run`、`replay_run`、`resolve_wait`、`purge_session`、以及超出 Phase 4 能力的 `cancel_session_runs` / active dispatch cancel 定义稳定 envelope 与明确 unsupported / deferred error 行为；不得 silently no-op。
- Non-goals 必须显式写入 plan：不实现 Engine execution、ToolRuntime、WorkerProxy / LocalProxy / RemoteProxy、scheduler / lane acquire、Projection worker、wait adapter、destructive purge、retry/replay execution、steer Attempt switching、recovery classifier。
- Tests 必须覆盖：API request validation、HostCallContext / OperationContext validation、public idempotency replay and conflict、`submit_followup(queue)` active race absorption、无 active queue 直接 running 的 response shape、queued / pre-dispatch cancel 与 promotion race 的 public facade 入口、deferred functions 的稳定错误 contract、`stream_run_events` cursor edge cases。
- Validation commands 必须至少包含 `source .venv/bin/activate && pytest tests/host -q`、受影响新增测试文件、`source .venv/bin/activate && python -m pyright dayu/host tests/host`、`git diff --check`。
- Docs 必须同步 `dayu/host/README.md`；如 public function 入口或用户可运行 Host command API 出现项目级使用方式变化，再同步根目录 `README.md`；如分层 / composition root 边界变化，同步 `dayu/README.md`。

## Residual Risks / Deferred Owners

- Steer 完整行为 owner：后续 steer / dispatch / wait 接入 phase；Phase 4 只应冻结 request validation、error shape 与 public contract，不应实现 Attempt switching。
- `resolve_wait` owner：Phase 7 Tool Awaiting / resolve_wait / Wait Adapter；Phase 4 只冻结 request envelope 与 deferred error / signature。
- `purge_session` destructive cleanup owner：Phase 15 Retention / Purge / Production Hardening；Phase 4 只冻结 result shape、idempotency scope 与 deferred behavior。
- Scheduler、lane acquire、WorkerProxy / LocalProxy、Engine dispatch、dispatch record `dispatching`、`ATTEMPT_RUNNING` owner：Phase 5 RunInputBuilder 与本地执行 Dispatch。
- Projection / read model catch-up owner：Phase 8 Projection Core；Phase 4 read APIs 只能读 durable truth / EventLog，不启动 projection worker。
- Remote cancel / remote execution owner：Phase 14 RemoteProxy / RemoteStub。
- Host lifecycle / recovery / multi-process hardening owner：Phase 11；Phase 4 不能把 host instance liveness、file lock 或 runtime lane 当作 lease / fencing / owner truth。
