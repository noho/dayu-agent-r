# Host Phase 3 Plan Fix — Session / Run / Attempt Admission

- **work gate name**: fix
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **source review artifact path**: `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-mimo-20260514.md`
- **controller adjudication artifact path**: `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-controller-adjudication-20260514.md`
- **plan path**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **artifact path**: `docs/reviews/gateflow-plan-fix-host-p3-session-run-attempt-admission-codex-20260514.md`

## Controller-accepted Findings

- `F1`
- `F2`
- `F3`

## Per-finding Fix Status

### F1 — fixed

- 补齐 `submit_followup(queue)` no-active data flow：`USER_INPUT_ACCEPTED` -> `RUN_ACCEPTED` -> `RUN_STARTED(start_reason=initial)` -> insert `host_runs` `RUNNING` -> `ATTEMPT_STARTED` -> insert `host_attempts` `STARTING` -> insert dispatch record `pending` -> update `current_attempt_id`。
- P3-S4 测试断言新增 follow-up 直接启动时该 Run 的 EventLog 具备完整 4 个 canonical facts，并按 EventLog 顺序出现。

### F2 — fixed

- 在 idempotency contract 中明确 `submit_followup_queue` 有 active / no-active 两条路径，first event ref 均为 `USER_INPUT_ACCEPTED`。
- 写清 active path 返回 `QUEUED` Run，no-active path 返回 `RUNNING` Run + `STARTING` Attempt。
- 写清同 key same digest 重试先命中 idempotency，返回同一个 Run，不追加第二套事件；同 key different digest 返回 `idempotency_conflict` 且不追加事件。

### F3 — fixed

- 明确 Phase 3 internal admission service 使用 `SubmitFollowupQueueAdmissionInput(request, resolved_execution_target)` 接收已归一化执行目标。
- 明确 Phase 3 不从 request metadata、HostInput metadata、payload JSON、caller semantic digest 或 untyped extra payload 猜 `execution_target`，也不引入完整 Phase 4 policy provider。
- 明确 `resolved_execution_target` 写入 `host_runs.execution_target`，queued promotion 后续读取持久化值，不重新解析 policy、不复制 active Run target。
- 明确 `resolved_execution_target` 不进入 `submit_followup_queue` semantic digest；同 key retry 返回首次持久化 Run，不因后续 resolver/default 变化创建新 Run 或改写 execution target。
- P3-S4 测试断言新增 queued / direct-running follow-up 的 execution target 持久化与 retry 行为。

## Changed Files

- `docs/host/phase3-session-run-attempt-admission-plan.md`
- `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-mimo-20260514.md`
- `docs/reviews/gateflow-plan-fix-host-p3-session-run-attempt-admission-codex-20260514.md`

## Finding Title Status Update

- 已在 source review artifact 中将 F1 / F2 / F3 标题状态词从 `未修复` 更新为 `已修复`。

## Validation Commands / Results

- `git diff --check`: passed
- `git diff --no-index --check /dev/null docs/reviews/gateflow-plan-fix-host-p3-session-run-attempt-admission-codex-20260514.md`: exit 1 because the compared files differ, with no whitespace warnings emitted.
- `git diff --no-index --check /dev/null docs/host/phase3-session-run-attempt-admission-plan.md`: exit 1 because the compared files differ, with no whitespace warnings emitted.
- `git diff --no-index --check /dev/null docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-mimo-20260514.md`: exit 1 because the compared files differ, with no whitespace warnings emitted.

未运行 Python 测试或 pyright；本 fix 只修改 plan / review 文档，不进入 implementation，不修改代码。

## New Risks / Open Questions

- 无新的 blocking open question。
- 新增残余风险：`resolved_execution_target` 被排除在 `submit_followup_queue` semantic digest 外，若 Phase 4 public command path 在同一 `client_request_id` retry 时重新解析出不同目标，Host 会按幂等契约返回首次持久化 Run。这是有意选择，用于保证 retry 稳定性；Phase 4 需要在 public command path 记录或诊断 policy resolution ref，避免调用方误以为 retry 可改变目标。

## Residual Risk Classification

- `resolved_execution_target` retry 语义：assigned to later phase，owner 为 Phase 4 Host Public API Command Path。
- 其余 F1 / F2 / F3 风险：fixed in current plan fix。
