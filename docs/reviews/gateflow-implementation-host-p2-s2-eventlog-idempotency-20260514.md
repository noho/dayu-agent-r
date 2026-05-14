# Gateflow Implementation Artifact: Host P2 S2 EventLog / Idempotency

## Gate

- **work gate name**: implementation
- **work-unit**: Host Phase 2 Durable Store / EventLog / Payload Foundation
- **slice id**: Phase 2 Slice 2 - EventLog Append / Read / event_sequence / Idempotency Primitive
- **approved plan path**: `docs/host/phase2-durable-store-eventlog-plan.md`
- **accepted plan commit**: `83c6ad6`
- **accepted Slice 1 commit**: `be5dbdc`
- **current branch**: `feat/host-phase2-durable-store-eventlog`

## Assigned Scope

实现 Slice 1 transaction runner 上的 EventLog append/read primitive 与 idempotency record primitive：

- `EventClass`, `EventLogAppendRequest`, `EventLogRow`, `EventLogAppendResult`, `EventLogStore`
- `append_event(transaction, request) -> EventLogAppendResult`
- `read_event_by_id(transaction, event_id) -> EventLogRow | None`
- `read_events_after(transaction, cursor, *, limit) -> tuple[EventLogRow, ...]`
- `IdempotencyScope`, `IdempotencyResultRef`, `IdempotencyRecord`, `IdempotencyStore`
- `record_idempotent_result(transaction, scope, semantic_input_digest, result) -> IdempotencyRecord`
- `read_idempotency_record(transaction, scope) -> IdempotencyRecord | None`

## Explicit Non-Goals

本 slice 未实现、也未修改：

- payload descriptor write helper、local artifact helper、host instance liveness operations
- Session / Run / Attempt state indexes、status updates 或 command path
- EngineEvent ingest、Projection、stream fanout、audit、trace、outbox、memory、ToolRuntime、Remote
- `dayu/runtime`、`dayu/engine`、`dayu/fins`、`dayu/service`、`dayu/ui`
- `docs/host/design.md`、`docs/host/implementation-control.md`

## Changed Files

- `dayu/host/durable/codec.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/durable/idempotency.py`
- `tests/host/test_event_log_store.py`
- `tests/host/test_event_log_multiprocess.py`
- `tests/host/test_idempotency_store.py`
- `docs/reviews/gateflow-implementation-host-p2-s2-eventlog-idempotency-20260514.md`

## Plan Items Implemented

- EventLog append 在调用方提供的 `HostTransaction` 内执行，不创建独立 command path。
- `event_sequence` 由 SQLite `event_log.event_sequence INTEGER PRIMARY KEY AUTOINCREMENT` 分配，多个 event class 共享全局 cursor。
- `event_body_digest` 基于 plan 指定的 request-assigned fields 计算，排除 `event_id`、`event_sequence`、`appended_at` 和 DB-assigned fields。
- 重复 `event_id` 且 body digest 相同返回既有 row，`inserted=False`，不追加第二行。
- 重复 `event_id` 且 body digest 不同抛出 `HostEventIdentityConflictError`。
- `read_event_by_id` 与 `read_events_after` 使用全局 cursor 语义，按 `event_sequence` 升序读取。
- EventLog 输入校验覆盖 invalid event class、空必填 id、naive timestamp、payload ref/digest 非法组合。
- 非空但不存在的 `payload_ref` 由 SQLite FK 触发并经 transaction runner 转为 `HostForeignKeyError`，未被 busy retry。
- idempotency 首次写入保存 scope/key、semantic digest 与显式 result ref。
- 相同 scope/key/digest 返回既有 record；相同 scope/key/不同 digest 抛出 `HostIdempotencyConflictError`。
- idempotency result ref 可通过 FK 引用已创建 EventLog event id / sequence。

未实现项：无本 slice 内应实现而未实现的 plan item。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_idempotency_store.py -q`
  - result: pass, `14 passed`
- `source .venv/bin/activate && pytest tests/host/test_event_log_multiprocess.py -q`
  - result: pass, `1 passed`
- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_durable_transaction.py -q`
  - result: pass, `15 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - result: pass, `0 errors, 0 warnings, 0 informations`

## Documentation Decision

未更新 README。

理由：本 slice 只新增 Host durable 内部 primitive 与对应测试；没有改变用户手册入口、CLI、配置入口、项目级使用方式，也没有把 durable 类型导出到 `dayu.host` 包根。`dayu/host/README.md` 与 `tests/README.md` 的 durable foundation 同步在 approved plan 的 Slice 3 文档触发范围内更合适，本 slice 不越权修改文档。

## Plan Gaps

未发现阻塞实现的 plan gap。

实现中做出的低风险解释：

- `policy_decision` 与 `reason` 为 `None` 时按 SQL NULL 处理；`payload_json=None` 按 canonical JSON `null` 写入 `payload_json`。
- `payload_ref` 与 `payload_digest` 必须成对出现；这与 schema 的 `payload_ref IS NOT NULL -> payload_digest IS NOT NULL` 一致，并避免 digest 脱离 descriptor 引用。

## Residual Risks And Uncovered Areas

- **accepted as covered by later slice in approved plan**: 本 slice 不创建 payload descriptor，因此只验证缺失 `payload_ref` FK 失败；有效 non-null `payload_ref` 的完整写入路径由 Slice 3 payload descriptor helper 覆盖。
- **accepted as covered by later slice in approved plan**: EventLog 目前只提供 primitive，不包含 EngineEvent ingest、projection、stream fanout、audit、trace、outbox 或 memory consumer；这些是后续 slices / phases 的明确 non-goals。
- **accepted as covered by later slice in approved plan**: idempotency scope 只作为显式三元组持久化，不绑定 command path 语义；command-specific scope 约束由后续 command path phase 定义。
- **fixed in the current slice before review**: pyright 初次发现多进程测试查询变量可能未绑定，已通过显式初始化修复，并重跑通过。

未覆盖但不阻塞当前 slice：

- 未测试有效 `payload_ref` append，因为缺少 descriptor write helper 属于 Slice 3。
- 未测试 deliberate long lock 的 retry exhausted 多进程分支；Slice 2 已覆盖正常多进程 append 成功与 Slice 1 transaction busy retry 单测。

## Completion Signal

- Slice 2 单进程 EventLog / idempotency 测试通过。
- Slice 2 多进程 append smoke 通过。
- Slice 1 durable schema / transaction 回归通过。
- `python -m pyright dayu/host tests/host` 通过。
- 未发现需要 Session / Run / Attempt state machine 才能使用 EventLog foundation 的实现依赖。

## Stop Condition Status

- appender 需要 Run / Attempt state indexes：否。
- idempotency scope 无法脱离 command path 语义表达：否。
- multi-process append 需要 `dayu.runtime.lane` 或 file locks 才能保证 EventLog ordering：否。
- implementation 需要 payload descriptor helper beyond nullable `payload_ref` FK：否。

## Completion Signal To Controller

Slice 2 implementation complete。当前证据显示 Slice 3 可以启动。

## Artifact Path

`docs/reviews/gateflow-implementation-host-p2-s2-eventlog-idempotency-20260514.md`
