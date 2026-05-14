# Host Phase 3 Plan Review Controller Adjudication

- **gate name**: Phase 3 plan review / controller adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **plan path**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **review artifact**: `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-mimo-20260514.md`
- **artifact path**: `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-controller-adjudication-20260514.md`

## Finding Decisions

### F1: `submit_followup(queue)` 无 active Run 时 data flow 缺少 `RUN_STARTED` / `ATTEMPT_STARTED`

- **decision status**: accepted
- **severity accepted by controller**: high
- **reason**: 设计真源要求 `submit_followup(queue)` 无 active Run 时追加 `USER_INPUT_ACCEPTED`、`RUN_ACCEPTED`、`RUN_STARTED(start_reason=initial)`、`ATTEMPT_STARTED`。plan data flow 只写创建 `RUNNING` Run、`STARTING` Attempt 与 dispatch record，缺少两个 canonical facts，implementation agent 可能按 plan 生成 EventLog 与 state index 不一致的代码。
- **required fix**: 补齐 no-active 路径的完整 EventLog append 与 state index 更新顺序，并在测试断言中覆盖 follow-up 直接启动时的 4 个 canonical facts。

### F2: `submit_followup_queue` 幂等契约 first event ref 不完整

- **decision status**: accepted
- **severity accepted by controller**: medium
- **reason**: `submit_followup(queue)` 有 active / no-active 两条路径，first event ref 都是 `USER_INPUT_ACCEPTED`，但结果状态不同。plan 需要显式说明两条路径共享 first event ref，但分别创建 `QUEUED` Run 或 `RUNNING` Run + `STARTING` Attempt，避免 implementation agent 误读为只创建 queued Run。
- **required fix**: 在 idempotency table 或补充说明中拆清两条路径，明确两者的 result ref、first event ref、重试返回行为和事件集合。

### F3: follow-up Run 的 `execution_target` 来源未明确

- **decision status**: accepted
- **severity accepted by controller**: medium
- **reason**: `SubmitFollowupRequest` 没有 `execution_target` 字段，但 plan schema 要求 `host_runs.execution_target TEXT NOT NULL`。如果 plan 不指定来源，implementation agent 必须自行选择从 active Run、session metadata 或 policy default 推断，违反 handoff-ready 要求。
- **required fix**: plan 必须明确 Phase 3 internal admission service 不从 request metadata 猜 `execution_target`，也不引入完整 Phase 4 policy provider。推荐方案是为 Phase 3 internal service 增加已归一化的 `resolved_execution_target` 输入或等价 typed resolver port：Phase 3 测试使用固定 resolver / 显式值，Phase 4 public command path 负责接入真实 policy resolution。`resolved_execution_target` 必须被写入 `host_runs.execution_target` 与相关 policy/diagnostic refs；`submit_followup_queue` 的 semantic digest 应明确是否包含该值，并解释幂等重试策略。若 plan 选择不纳入 semantic digest，必须说明同 key 重试返回既有 result，不因 policy/default 变化追加新 Run。

## Gate Decision

- **accepted findings**: F1, F2, F3
- **rejected findings**: none
- **deferred findings**: none
- **blocking open questions requiring user decision**: none
- **decision**: plan review failed; enter plan fix gate.
