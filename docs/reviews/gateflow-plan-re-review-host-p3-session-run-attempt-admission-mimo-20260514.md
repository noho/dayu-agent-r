# Host Phase 3 Plan Re-Review — Session / Run / Attempt Admission

- **review gate name**: Phase 3 plan re-review
- **reviewed target**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **reviewer**: AgentMiMo
- **artifact path**: `docs/reviews/gateflow-plan-re-review-host-p3-session-run-attempt-admission-mimo-20260514.md`
- **conclusion**: F1 / F2 / F3 均已修复，无 new blocker，建议 accepted plan commit。

## Re-review 输入

- source review artifact: `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-mimo-20260514.md`
- controller adjudication: `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-controller-adjudication-20260514.md`
- fix artifact: `docs/reviews/gateflow-plan-fix-host-p3-session-run-attempt-admission-codex-20260514.md`

## F1 验证

**原始问题**: `submit_followup(queue)` 无 active Run 时 data flow 缺少 `RUN_STARTED` / `ATTEMPT_STARTED` 事件追加。

**修复验证**:

plan 行 581-587 已补齐 no-active 路径的完整事件追加顺序：

```text
else:
  append RUN_STARTED(start_reason=initial)
  insert host_runs RUNNING with execution_target=resolved_execution_target
  append ATTEMPT_STARTED
  insert host_attempts STARTING
  insert dispatch record pending
  update run.current_attempt_id
```

与 `start_run` 的 no-active 路径一致：`USER_INPUT_ACCEPTED` → `RUN_ACCEPTED` → `RUN_STARTED(start_reason=initial)` → insert Run → `ATTEMPT_STARTED` → insert Attempt → insert dispatch → update `current_attempt_id`。

P3-S4 测试断言（行 844）已覆盖：follow-up queue without active has exactly the four canonical facts `USER_INPUT_ACCEPTED`, `RUN_ACCEPTED`, `RUN_STARTED(start_reason=initial)` and `ATTEMPT_STARTED` for that Run, in EventLog order。

P3-S4 implementation instructions（行 827）已明确：follow-up queue with no active Run must append `USER_INPUT_ACCEPTED`, `RUN_ACCEPTED`, `RUN_STARTED(start_reason=initial)` and `ATTEMPT_STARTED` in the admission transaction before returning a running Run。

**final status**: fixed

## F2 验证

**原始问题**: `submit_followup_queue` 幂等契约 first event ref 不完整，缺少 active / no-active 两条路径的 disambiguation。

**修复验证**:

idempotency table（行 403）已更新：`submit_followup_queue` 的 first event ref 列写明 `USER_INPUT_ACCEPTED for both active and no-active creation paths`。

idempotency table 后补充了完整的两条路径说明（行 409-412）：

- active Run exists: append `USER_INPUT_ACCEPTED` / `RUN_ACCEPTED` / `RUN_QUEUED`, create a `QUEUED` Run, store `resolved_execution_target`, record idempotency result with first event ref `USER_INPUT_ACCEPTED`.
- no active Run exists: append `USER_INPUT_ACCEPTED` / `RUN_ACCEPTED` / `RUN_STARTED(start_reason=initial)` / `ATTEMPT_STARTED`, create a `RUNNING` Run plus `STARTING` Attempt and pending dispatch record, store `resolved_execution_target`, record idempotency result with first event ref `USER_INPUT_ACCEPTED`.

重试行为（行 393）已明确：`submit_followup_queue` semantic digest excludes `resolved_execution_target`; the first accepted call persists the resolved target, and same-key retries return that existing Run even if a later resolver/default would produce a different target.

P3-S4 测试断言（行 847-848）已覆盖：duplicate idempotency returns same Run for both paths; duplicate idempotency with different `resolved_execution_target` but unchanged digest returns first Run and does not mutate `host_runs.execution_target`。

**final status**: fixed

## F3 验证

**原始问题**: follow-up Run 的 `execution_target` 来源未明确。

**修复验证**:

P3-S4 exact allowed changes（行 813）已新增：`submit_followup_queue(input: SubmitFollowupQueueAdmissionInput) -> RunAdmissionResult`。

P3-S4 implementation instructions（行 822-824）已明确：

- follow-up queue must receive a normalized `resolved_execution_target` from its caller; it must validate it as non-empty before admission and must not infer it from request metadata, HostInput metadata, payload JSON or active Run state.
- follow-up queue must persist `resolved_execution_target` to `host_runs.execution_target` for both `QUEUED` and `RUNNING` Runs; later queue promotion reuses this stored value.

data flow（行 570, 577, 580, 583）已贯穿 `resolved_execution_target`：validate non-empty → `RUN_ACCEPTED` payload → `host_runs.execution_target`（QUEUED 和 RUNNING 两条路径均写入）。

promotion（行 594）已明确：Queue promotion later reads the already stored `host_runs.execution_target`; it must not rerun policy resolution or copy from whatever Run is active at promotion time.

idempotency（行 393, 403）已明确：`resolved_execution_target` excluded from semantic digest; same-key retry returns first persisted Run, does not mutate execution target。

P3-S4 测试断言（行 842-848）已覆盖：active path stores resolved target on queued Run without copying active Run target; no-active path stores resolved target; retry with different target does not mutate。

controller 要求的 "不引入完整 Phase 4 policy provider" 已满足：Phase 3 只接收 `resolved_execution_target` 作为内部输入，不实现 policy resolution。

residual risk（`resolved_execution_target` retry 语义，Phase 4 owner）已在 fix artifact 中明确归属。

**final status**: fixed

## Fix 引入的新风险 / Scope Creep 检查

1. **`SubmitFollowupQueueAdmissionInput` 新增**: 内部 admission input dataclass，不修改公共 API，不引入 Phase 4 policy provider。scope 合理。
2. **`resolved_execution_target` 排除在 semantic digest 外**: 有意选择，保证 retry 稳定性。residual risk 已归属 Phase 4。不产生新 blocker。
3. **promotion 不重新解析 policy**: 读取持久化值，不复制 active Run target。实现简化，符合 Phase 3 不引入 policy provider 的约束。
4. **fix 范围**: 只修改 plan 和 review 文档，不修改代码。无 scope creep。

## Source Artifact Title Status Update

- source artifact `docs/reviews/gateflow-plan-review-host-p3-session-run-attempt-admission-mimo-20260514.md` 的 F1 / F2 / F3 标题状态词已由 fix agent 更新为 `已修复`。
- re-review 确认状态词正确，无需回写。

## Gate Decision

- **F1 final status**: fixed
- **F2 final status**: fixed
- **F3 final status**: fixed
- **new blocker**: 0
- **new risk**: 无。`resolved_execution_target` retry 语义 residual risk 已归属 Phase 4，不阻塞 Phase 3。
- **blocking findings**: 0
- **建议**: accepted plan commit
