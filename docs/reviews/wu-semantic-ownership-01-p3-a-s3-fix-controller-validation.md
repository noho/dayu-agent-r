# WU-SEMANTIC-OWNERSHIP-01 P3-A S3 fix controller validation

## Gate

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A / S3`。
- Gate：fix controller validation。
- Finding truth：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-code-review-controller-adjudication.md`。
- Decision：S3-CR-F01 至 S3-CR-F04 均有实现与测试闭环，进入 re-review gate。

## Finding status

- `S3-CR-F01`：已修复。Reactive compaction post-compactor gate 消费 `is_terminal_attempt_status(latest.attempt.status)`，不再使用 terminal ref 代理 lifecycle truth。
- `S3-CR-F02`：已修复。原混装 `_TerminalPlan` 已删除；`_EngineTerminalPlan` 与 `_HostLifecycleTerminalPlan` 只共享 `_TerminalFactPlan` canonical facts，候选与 closeout 签名静态分离。
- `S3-CR-F03`：已修复。Host lifecycle ingress guard 显式校验 `run.run_id`，public path test 通过 repository test double 证明错 identity 被拒绝。
- `S3-CR-F04`：已修复。Non-`UPDATED` terminal helper result 通过 `_TerminalCloseoutRollback` 让真实 write transaction rollback，事务外恢复既有 rejected result；Engine/Host 的真实 invalid-state 与注入 CAS-lost 测试均比较 payload、descriptor、EventLog、Run/Attempt status 前后快照。

## Independent validation

```text
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_active_cancel_dispatch.py tests/host/test_recovery_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_run_attempt_transitions.py tests/host/test_state_schema.py tests/host/test_phase5_local_execution_integration.py tests/host/test_dispatch_scheduler.py -q
302 passed in 3.76s
```

- `source .venv/bin/activate && pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- synthetic EngineEvent scan：通过。
- legacy mixed `_TerminalPlan` scan：通过，无残留。
- command direct-cancel duplicate predicate scan：通过。
- producer terminal event constant scan：通过。
- positive owner scan：两类 typed plan、两个 transaction-outside rollback catch、Host lifecycle run-id guard、reactive status predicate 均存在。

## README decision

- Fix 只强化 private typed plan 与 transaction failure atomicity；S3 implementation 已更新的 Host README 已准确描述两条 source path 与 shared durable transaction，无需追加。
- tests README 的测试层级、命令类别和维护规则未变化，无需更新。

## Propagation / residual judgment

- Payload descriptor、canonical terminal facts 与 Run/Attempt status 现在在 success/failed precondition 两侧都同事务同成败；non-updated 路径没有 orphan material 可被 projection 或 LLM-facing consumer误读。
- Engine 与 Host lifecycle source metadata 继续由各自 typed plan/candidate 提供，只有 canonical event/status fact plan 共享。
- 跨进程 stress 仍归 production stress / EventLog hardening owner；P3-B、P3-J 保持后续 approved sub WU，均非当前 blocker。
- 无未分类 residual risk、deferred accepted finding 或 blocking open question。

## Completion

- Status：accepted for re-review。
- Fix artifact：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-fix-codex.md`。
- Controller artifact：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-fix-controller-validation.md`。
- Next gate：P3-A S3 re-review by AgentMiMo and AgentDS。
