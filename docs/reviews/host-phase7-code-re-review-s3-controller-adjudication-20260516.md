# Host Phase 7 P7-S3 Controller Adjudication

日期：2026-05-16

## Scope

- Slice：P7-S3 resolve_wait Command And Resume Attempt
- Implementation artifact：`docs/reviews/host-phase7-implementation-s3-resolve-wait-resume-20260516.md`
- Fix artifact：`docs/reviews/host-phase7-fix-s3-resolve-wait-resume-20260516.md`
- MiMo review：`docs/reviews/host-phase7-code-review-s3-mimo-20260516.md`
- MiMo re-review：`docs/reviews/host-phase7-code-re-review-s3-mimo-20260516.md`
- DS review：`docs/reviews/host-phase7-code-review-s3-ds-20260516.md`

## Findings

- S3-F1：`ResolveWaitLostOutcome` 终态幂等重放缺口。
  - 来源：Controller 抽查。
  - 严重性：blocking correctness。
  - 处理：accepted and fixed。
  - 修复：`dayu/host/waiting.py` 将 `WaitRecordStatus.LOST` 纳入 `_replay_terminal_resolution` 入口；`tests/host/test_resolve_wait_command.py` 新增 lost 同 key 重放测试。
  - 状态：closed。MiMo re-review 与 DS review 均确认关闭。

MiMo 初审未发现问题；DS 当前版本 review 未发现新增 blocking finding。

## Accepted Evidence

- `resolve_wait` public command 已从 stable unsupported 迁移为 durable wait resolution service。
- `(wait_id, idempotency_key)` 幂等 scope 覆盖 RESOLVED / FAILED / LOST 终态重放与冲突。
- completed / tool-cancelled 在同一 write transaction 内关闭 wait、写入 resume / tool result / run started / attempt started facts、创建 resume Attempt 与 pending dispatch，并在 commit 后 best-effort wake dispatch。
- failed / lost 只做 terminal closeout，不创建 resume Attempt；lost 结果写入 tool lost fact。
- RunInputBuilder resume continuity 只从 `RUN_STARTED(start_reason=resume)` 及其引用的 `TOOL_RESULT_ACCEPTED` canonical EventLog 重建。
- README 与 public run API 测试已跟随当前契约迁移。
- 未修改 Engine、contracts、fins、service、ui、recovery、outbox、audit 或 tool trace read-model。

## Verification

- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py tests/host/test_run_attempt_transitions.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_phase7_waiting_integration.py -q`
  - 结果：`64 passed`
- `source .venv/bin/activate && pytest tests/host -q`
  - 结果：`381 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过。

## Verdict

P7-S3 accepted。可进入总控文档 checkpoint 与 accepted commit。

## Residual Risk

- P7-S4 范围的 late result diagnostic、cancel-vs-resolve race、CAS_LOST 并发压力测试未实现。
- `wake_dispatch` 是 commit 后 best-effort；scheduler 不可用时依赖后续 drain loop 拾取 pending dispatch record。

