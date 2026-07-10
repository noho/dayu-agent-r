# WU-SEMANTIC-OWNERSHIP-01 P3-A S3 controller validation

## Gate

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / P3-A / S3`。
- Gate：implementation controller validation。
- Decision：通过，进入独立 code review gate。

## Scope judgment

- 改动仅落在 approved S3 的 Host ingest、durable state、command、相关测试与 Host README。
- worker EOF/crash 已从 synthetic `EngineEvent(RUN_FAILED)` 改为 typed Host lifecycle candidate；Engine-origin terminal path 仍消费真实 `EngineEventCandidate`。
- active cancel 下 worker lifecycle 只写 Host lifecycle diagnostic，不抢占 cancel watchdog 的 terminal owner。
- late routing 使用 durable Run / Attempt status predicate；nullable terminal refs 只保留 transaction / row consistency 职责。
- direct-cancel predicate 由 `dayu.host.durable.state` 拥有，command 不再读取 worker accepted nullable refs 重建规则。
- 未触及 P3-B final answer / outbox continuity，也未修改 control doc 之外的非批准模块。

## Independent validation

```text
pytest tests/host/test_engine_ingest_mapping.py tests/host/test_active_cancel_dispatch.py tests/host/test_recovery_dispatch.py tests/host/test_public_cancel_session_runs.py tests/host/test_run_attempt_transitions.py tests/host/test_phase5_local_execution_integration.py tests/host/test_dispatch_scheduler.py tests/host/test_state_schema.py -q
296 passed in 3.82s
```

- `source .venv/bin/activate && pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- synthetic lifecycle scan：`engine_ingest.py` 不再构造 `EngineEvent(...)` 或 `type=EngineEventType.RUN_FAILED`。
- command predicate scan：`command.py` 不再包含本地 direct-cancel helper或 worker accepted nullable refs。
- late-routing scan：`engine_ingest.py` 的 late rejection helper 不读取 terminal refs；剩余引用属于 terminal transaction / reactive precondition。

## README decision

- `dayu/host/README.md` 原文直接描述 EngineEvent ingest、worker lifecycle 与 cancel/watchdog，稳定 owner boundary 已变化，因此最小同步成立。
- `tests/README.md` 的测试层级、运行方式和维护规则未变化，不更新成立。

## Propagation audit judgment

- Host lifecycle signal -> typed candidate -> Host namespace/source -> shared terminal transaction -> EventLog Attempt/Run facts与 durable status 同事务提交 -> existing projections，路径同源。
- CANCELLING 下 Host lifecycle signal -> Host diagnostic，不生成错误 FAILED/LOST terminal fact；cancel transition/watchdog 仍是 terminal owner。
- diagnostic payload 不含伪造 Engine event type/ref；Host lifecycle governance ref 不作为业务事实或 LLM-facing material。
- direct cancel path由 durable row predicate向 command 投影，command 不再重建组合规则。

## Residual risks

- 专门的跨进程 Engine/Host terminal 同时提交 stress test 未包含在 S3；归后续 production stress / EventLog hardening，非当前 blocker。
- P3-B 与 P3-J 保持后续 accepted sub WU owner，不在 S3 扩张。
- 无未分类 residual risk，无 blocking open question。

## Completion

- Status：accepted for code review。
- Implementation artifact：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-implementation-codex.md`。
- Controller artifact：`docs/reviews/wu-semantic-ownership-01-p3-a-s3-controller-validation.md`。
- Next gate：P3-A S3 code review by AgentMiMo and AgentDS。
