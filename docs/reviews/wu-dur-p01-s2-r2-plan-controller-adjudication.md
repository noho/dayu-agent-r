# WU-DUR-P01-S2-R2 plan gate controller adjudication

## 结论

`accept`。修订后的 `docs/host/wu-dur-p01-s2-r2-runner-call-event-link-plan.md` 已通过 plan gate，可以进入 implementation gate。

## 依据

- AgentMiMo 初评 `docs/reviews/wu-dur-p01-s2-r2-plan-review-mimo.md` 结论为 `revise`，阻断点集中在 `ENGINE_EVENT_REJECTED` 设计登记和新增 reason 闭集定义。
- AgentDS 初评 `docs/reviews/wu-dur-p01-s2-r2-plan-review-ds.md` 结论为 `revise`，阻断点集中在 prior observation durable query、ordinary dispatch kind 闭集和 manifest write / Engine ingest ordering guarantee。
- AgentCodex 已修订 plan artifact，仅修改 `docs/host/wu-dur-p01-s2-r2-runner-call-event-link-plan.md`。
- AgentMiMo re-review `docs/reviews/wu-dur-p01-s2-r2-plan-rereview-mimo.md` 结论为 `accept`。
- AgentDS re-review `docs/reviews/wu-dur-p01-s2-r2-plan-rereview-ds.md` 结论为 `accept`。

## Controller 裁决

方案方向成立：root cause 不是缺少 Engine `ITERATION_STARTED`，而是 Host prepared `RUNNER_CALL_INPUT_ASSEMBLED` manifest 与 Engine iteration 之间缺少追加式稳定 link，导致现有逻辑依赖 `iteration_id` / `iteration_index == 0` 这类 Engine 内部语义猜测。

implementation 必须以修订版 plan 为准，尤其遵守以下硬约束：

- 不修改 Engine 反向依赖 Host manifest id。
- 不回写旧 `RUNNER_CALL_INPUT_ASSEMBLED` manifest body、payload descriptor 或 digest。
- 删除或重写旧 `_runner_call_manifest_matches_iteration` fallback，不保留 `payload_iteration_id is None and iteration_index == 0` 语义。
- `RUNNER_CALL_INPUT_ITERATION_LINKED` 与 accepted preview、mismatch link 与 rejected diagnostic 必须同 Host transaction。
- `missing initial manifest`、`ambiguous manifest`、`message_count` / `role_sequence_digest` mismatch、link conflict 必须 fail closed。
- continuation 即使 `iteration_index == 0`，也只能在当前 attempt/execution 已有 accepted prior iteration observation 且没有 unlinked prepared manifest 时走 limited-signal path。
- Tool Trace 最小实现不强制投影 link event，但 design / README 必须明确 prepared `complete` 与 linked `complete` 的区别。

## 下一步

进入 implementation gate，由 AgentCodex 按修订版 plan 实施。实施后必须进入两路 code review，再由 controller 裁决。
