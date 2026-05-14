# Gateflow Controller Re-Review Adjudication: Host P3-S3 Run / Attempt Transition Primitives

- **gate**: code re-review adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: P3-S3 Run / Attempt Transition Primitives
- **review artifact**: `docs/reviews/gateflow-code-review-host-p3-s3-run-attempt-transitions-mimo-20260514.md`
- **controller adjudication artifact**: `docs/reviews/gateflow-code-review-host-p3-s3-run-attempt-transitions-controller-adjudication-20260514.md`
- **fix artifact**: `docs/reviews/gateflow-fix-host-p3-s3-run-attempt-transitions-20260514.md`
- **re-review artifact**: `docs/reviews/gateflow-code-re-review-host-p3-s3-run-attempt-transitions-mimo-20260514.md`
- **controller**: Codex
- **artifact path**: `docs/reviews/gateflow-code-re-review-host-p3-s3-run-attempt-transitions-controller-adjudication-20260514.md`

## Controller Conclusion

P3S3-C-001 已修复。P3-S3 transition helper 现在满足两个必须条件：append EventLog 前完成可判定的 skip / not_found / invalid_state 判断；append EventLog 后若 state mutation 非 `UPDATED`，抛出 `HostDurableError` 触发 transaction rollback，不能把 failure result 返回给调用方正常 commit。

P3-S3 可以进入文档同步和本地最终验证；验证通过后创建 accepted slice commit。

## Finding Closure

| Finding | Initial Decision | Re-Review Result | Final Status | Owner |
|---------|------------------|------------------|--------------|-------|
| P3S3-C-001 | accepted/blocking | fixed | closed-fixed | AgentCodex |
| O-1 | deferred | unchanged | deferred | P3-S4 / EngineEvent ingest owner |
| O-2 | deferred | unchanged | deferred | P3-S4 / Phase 5 cancel owner |
| O-3 | superseded | fixed by explicit rollback contract | closed-fixed | AgentCodex |

## Evidence

- `promote_queued_run_in_transaction` 在 active Run 存在和无 queued Run 时返回 skip / not_found，且不 append EventLog。
- `terminal_closeout_in_transaction`、`cancel_queued_in_transaction`、`cancel_predispatch_starting_in_transaction` 的 precondition failure 分支均在 append 前返回。
- `_require_run_mutation_updated`、`_require_attempt_mutation_updated`、`_require_dispatch_record_mutation_updated` 把 append 后非 `UPDATED` mutation 转为 `HostDurableError`。
- `test_promote_cas_loser_keeps_queued_state` 现在验证 append 后 CAS loser 会 rollback，且不残留 queued Run 的 `RUN_STARTED` event。
- `test_promote_active_run_skip_does_not_append_queued_started_event` 验证 active skip 不 append queued Run `RUN_STARTED` event。
- MiMo re-review 独立验证通过：
  - `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_session_lifecycle.py -q`
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - `git diff --check`

## Residual Risks / Follow-Up Owners

- **P3-S4 / EngineEvent ingest owner**: FAILED / LOST terminal closeout 路径的 higher-level 集成覆盖仍需补充；P3-S3 已保留具体 terminal event type 映射。
- **P3-S4 / Phase 5 cancel owner**: dispatch 非 pending、dispatching / running cancel 的更高层路径由后续 dispatch 与 cancel owner 补充。
- **P3-S4 owner**: admission idempotency、after-commit promotion / wakeup 与多进程 active race 集成测试不属于 P3-S3，必须在 admission slice 覆盖。

## Next Gate

同步 `dayu/host/README.md`、`tests/README.md` 与 `docs/host/implementation-control.md` 的当前事实和追踪项，然后执行本地最终验证并 commit。
