# Phase 11 Slice 5 Code Review Controller Adjudication - 2026-05-19

## Scope

- Work unit: Phase 11 Host Lifecycle / Recovery / Multi-process Hardening
- Slice: Slice 5 Multi-process Recovery And Runtime Lane Hardening
- Implementation artifact: `docs/reviews/phase11-slice5-implementation-codex-20260519.md`
- Review artifacts:
  - `docs/reviews/phase11-slice5-code-review-mimo-20260519.md`
  - `docs/reviews/phase11-slice5-code-review-ds-20260519.md`

## Verdict

接受 Slice 5，不进入 current fix pass。

AgentMiMo 与 AgentDS 均为 PASS，blocking count = 0。两份 review 独立确认本 slice 没有 production `dayu/` diff，没有 schema / public API / Engine 变更；新增测试证明了 Slice 5 的多进程 recovery 与 runtime lane 边界。

## Accepted Findings

无 current-fix finding。

## Controller Decision

- Multi-process live owner safety: accepted. 新测试通过 durable EventLog / Run / Attempt rows 证明第二进程打开同库不会写 `ATTEMPT_LOST` / `RUN_RECOVERING`，不会创建第二个 Attempt，且 owner process 仍存活。
- Crash recovery public visibility: accepted. 新测试通过 public `open_host(options)` 与 `watch_session_events(session_id)` 观察 recovery final answer，而不是读取 private projection 作为成功信号。
- Projection lag non-truth: accepted. 测试只滞后 projection checkpoint，recovery 仍从 durable EventLog / Run / Attempt / dispatch rows 成功恢复，未把 projection/read-model 当 truth。
- Runtime lane close/acquire hardening: accepted. 新测试只验证 runtime capacity cleanup、pending acquire wakeup、新 claim 拒绝和 active claim count invariant，未把 lane token 升级为 Host recovery truth。
- Legacy test identity migration: accepted. 删除固定 `process_start_token` 重注册 helper，并让第二个 scheduler 使用不同 `host_handle_id`，这是对 Slice 1 高熵 host instance identity 约束的测试迁移，不是生产兼容或约束放宽。

## Validation

Controller local validation after implementation:

```bash
source .venv/bin/activate && pytest tests/host/test_active_cancel_dispatch.py::test_cancel_run_waiting_for_lane_skips_later_dispatch tests/host/test_active_cancel_dispatch.py::test_cancel_run_dispatching_pre_accept_stays_cancelled tests/host/test_dispatch_scheduler.py::test_default_active_registry_is_scheduler_local -q
# 3 passed

source .venv/bin/activate && pytest tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py tests/runtime/test_lane.py -q
# 39 passed

source .venv/bin/activate && pytest tests/host -q
# 794 passed

source .venv/bin/activate && python -m pyright dayu/host dayu/runtime tests/host tests/runtime
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean
```

## Residual Risk Tracking

- Platform-specific pid start-time / boot-id mismatch proof remains deferred by Phase 11 plan; current portable proof path uses missing pid + stale heartbeat.
- Projection corruption is projection repair owner, not recovery truth owner; Slice 5 only proves projection checkpoint lag is non-truth.
- Runtime lane stale cleanup remains runtime capacity cleanup only; it is not Host positive orphan proof.

## Conclusion

Phase 11 Slice 5 is accepted and may enter local commit. Next gate is Phase 11 aggregate deepreview / phase acceptance validation.
