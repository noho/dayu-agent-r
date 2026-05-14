# Gateflow Controller Adjudication: Host P3-S3 Run / Attempt Transition Primitives Code Review

- **gate**: code review adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: P3-S3 Run / Attempt Transition Primitives
- **review artifact**: `docs/reviews/gateflow-code-review-host-p3-s3-run-attempt-transitions-mimo-20260514.md`
- **controller**: Codex
- **artifact path**: `docs/reviews/gateflow-code-review-host-p3-s3-run-attempt-transitions-controller-adjudication-20260514.md`

## Controller Conclusion

MiMo review 对 scope、事件类型、基础 happy path 和类型边界的审查有效，但总控不同意直接 approved。P3-S3 当前存在一个必须修复的事务语义问题：测试和部分 transition helper 分支允许“先 append EventLog canonical fact，再返回 CAS failure，并由调用方正常 commit”的模式。这会破坏 EventLog 作为事实真源的含义。

总控新增 controller finding `P3S3-C-001`，裁决为 accepted/blocking。修复完成并通过 re-review 前，P3-S3 不得进入 accepted slice commit。

## Finding Decisions

| Finding | Severity | Decision | Owner | Required Action |
|---------|----------|----------|-------|-----------------|
| P3S3-C-001 | high | accepted | AgentCodex | 禁止 CAS failure/skip 路径正常提交已 append 但无 state mutation 对应的 EventLog；修复实现与测试。 |
| O-1 | info | deferred | P3-S4 / EngineEvent ingest owner | FAILED/LOST terminal 路径测试可在后续 EngineEvent 映射或 terminal closeout 扩展时补充；不阻塞当前 fix。 |
| O-2 | info | deferred | P3-S4 / Phase 5 cancel owner | dispatch 非 pending 边界可在 dispatching/running cancel 路径接入时补充；不阻塞当前 fix。 |
| O-3 | info | superseded-by-P3S3-C-001 | AgentCodex | MiMo 将其视为 by design；总控裁决为不可接受的隐式 rollback contract。 |

## P3S3-C-001: EventLog dirty fact can be committed on CAS failure

### Direct Evidence

`tests/host/test_run_attempt_transitions.py` 中 `test_promote_cas_loser_keeps_queued_state` 当前流程为：

1. 创建 active Run 和 queued Run。
2. 在同一个 write transaction 内 append `RUN_STARTED` event：`event-run-start-cas-lost`。
3. 调用 `promote_queued_run_row(...)`，由于 active Run 存在返回 `StateMutationStatus.CAS_LOST`。
4. 测试正常返回，`HostTransactionRunner.run_write` 正常 commit。

该测试证明了当前 accepted 测试模式允许一个没有对应 `host_runs.status` 迁移的 `RUN_STARTED` canonical fact 被提交。EventLog 是 Host canonical fact truth，不能依赖“调用方看到 CAS_LOST 后自觉 rollback”这种未编码 contract。

实现层也存在同类风险：

- `promote_queued_run_in_transaction` 在 append `RUN_STARTED` 后，如果 `promote_queued_run_row` 返回非 `UPDATED`，会把 failure result 返回给调用方。
- `terminal_closeout_in_transaction` 在 append Attempt / Run terminal events 后，如果 Attempt 或 Run CAS 返回非 `UPDATED`，会把 failure result 返回给调用方。
- `cancel_queued_in_transaction` 和 `cancel_predispatch_starting_in_transaction` 在 append cancel events 后，如果后续 CAS 返回非 `UPDATED`，也会返回 failure result。

在这些路径上，只要调用方把 failure result 当作结构化结果并 commit，就会留下 dirty EventLog fact。

### Required Fix

修复必须满足：

- 对外 transition helper 的 skip / not_found / invalid_state / cas_lost 返回路径不得 append 新 EventLog row。
- 一旦 helper 已 append canonical EventLog fact，后续 state mutation 若未 `UPDATED`，必须触发 rollback，不能返回普通 failure result 让调用方误 commit。
- 可接受实现方式：
  - 在 append 前完成所有可判定的 precondition / skip 判断；
  - 对 append 后理论上不应失败的 CAS 结果，改为抛出 `HostDurableError` 或更具体 durable error，让 transaction runner rollback；
  - 或使用 SQLite savepoint 包裹 helper 内部 append + mutation，在非 updated 时 rollback 到 savepoint 后返回结构化 result。
- 修复测试：
  - 替换或改写 `test_promote_cas_loser_keeps_queued_state`，不得正常提交 orphan `RUN_STARTED` event；
  - 增加断言：promotion 因 active Run 存在而 skip / CAS loser 时，不新增 queued Run 的 `RUN_STARTED` event；
  - 如保留低层 state CAS helper 测试，必须显式 rollback 该 transaction，或使用已存在且语义匹配的 event ref，不能提交伪造 transition event。

### Non-goals

- 不引入 Engine dispatch、WorkerProxy、scheduler、lane、admission orchestration 或 public facade。
- 不把 failure handling 做成通用事务框架。
- 不为不可达理论分支引入重 lease / fencing / queue manager。

## Required Validation

- `source .venv/bin/activate && pytest tests/host/test_run_attempt_transitions.py tests/host/test_session_lifecycle.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`

## README Decision

P3-S3 修改触发 `dayu/host/README.md` 与 `tests/README.md` 检查。当前 implementation handoff 未允许 README 修改，但总控在 accepted slice commit 前必须重新检查 README 是否因当前事实变更而变为 false；若变 false，由总控或 fix task 明确纳入允许 scope。
