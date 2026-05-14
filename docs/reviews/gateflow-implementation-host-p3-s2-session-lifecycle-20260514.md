# Gateflow Implementation Artifact: Host P3-S2 Session And Slot Lifecycle

- **work gate**: implementation
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: P3-S2 Session And Slot Lifecycle
- **approved plan**: `docs/host/phase3-session-run-attempt-admission-plan.md`
- **accepted plan commit**: `71ddcba`
- **accepted P3-S1 commit**: `27d3145`
- **artifact path**: `docs/reviews/gateflow-implementation-host-p3-s2-session-lifecycle-20260514.md`

## Scope / Non-goals / Allowed Files

本次只实现 Session row lifecycle 与 slot binding 语义。未启动 `$gateflow`，未重新写 plan，未做 review/fix/re-review，未 commit/push/PR。

Allowed files/modules:

- `dayu/host/durable/state.py`
- `dayu/host/durable/session_lifecycle.py`
- `tests/host/test_session_lifecycle.py`
- `docs/reviews/gateflow-implementation-host-p3-s2-session-lifecycle-20260514.md`

Explicit non-goals kept:

- 未实现 start_run / follow-up。
- 未创建、取消、删除、清理或修改 Run / Attempt rows；仅在 SessionSnapshot 转换时读取 active / queued Run 摘要。
- 未实现 purge、cancel_session_runs、admission、promotion、Engine dispatch、scheduler、lane、WorkerProxy、ToolRuntime、wait、steer、retry/replay、context compaction、recovery。
- 未新增 public API export。

## Changed Files

- `dayu/host/durable/state.py`
  - 新增 Session / slot 低层 read / insert / upsert / CAS close helper。
  - 新增 `SessionSnapshot` 转换 helper，读取当前 slot、active Run id 与 queued Run ids。
- `dayu/host/durable/session_lifecycle.py`
  - 新增内部 `SessionLifecycleResult`。
  - 实现 `ensure_session`、`create_session`、`close_session`。
  - `ensure_session` 使用 slot PK 作为幂等真源，不写 `idempotency_records`。
  - `create_session` / `close_session` 使用 `IdempotencyStore`，同 key 同 digest 返回既有 snapshot，不同 digest 返回 `HostApiErrorCode.IDEMPOTENCY_CONFLICT`。
  - `SESSION_CREATED` / `SESSION_CLOSED` 与 state row mutation 在同一 write transaction 内完成。
  - `create_session(bind_slot=True)` 使用 slot upsert 原子重绑定，新 Session 成为 slot 当前绑定，旧 Session 不变。
- `tests/host/test_session_lifecycle.py`
  - 覆盖 ensure / create / close 生命周期、slot 重绑定、幂等重试、幂等冲突与同 slot 多进程并发。

## Plan Items

Implemented:

- add low-level insert/read/update helpers for sessions and slots.
- implement `ensure_session`.
- implement `create_session`.
- implement `close_session`.
- add internal result dataclasses and snapshot conversion helpers.
- ensure_session 不使用 `idempotency_records`。
- create/close duplicate same digest 返回既有 snapshot；different digest 返回 idempotency conflict。
- close_session 只关闭 Session，不触碰 Run rows。

Not implemented by design:

- P3-S3+ Run / Attempt transition primitives。
- P3-S4+ admission、queue、promotion、cancel、terminal closeout。
- public API facade/export。

## Validation

Passed:

```text
source .venv/bin/activate && pytest tests/host/test_session_lifecycle.py tests/host/test_state_schema.py tests/host/test_durable_schema.py -q
26 passed in 0.46s
```

Passed:

```text
source .venv/bin/activate && python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations
```

Passed:

```text
git diff --check
```

## Docs Decision

未修改 README。P3-S2 只新增 Host durable 内部 lifecycle helper，尚未改变用户手册、开发手册公开入口或包边界说明；未发现现有 README 因本 slice 变为直接 false。按 handoff 要求，默认文档同步留给 P3-S6。

## Plan Gaps / Questions

- 未发现需要 controller 裁决的 blocking gap。
- `CloseSessionRequest` 现有 public dataclass 不携带 `session_id`；本 slice 通过内部函数显式参数传入 `session_id`，未触发 public API 变更 stop condition。
- `SessionSnapshot` 足以表达本 slice 返回状态；未触发 snapshot/public API stop condition。

## Residual Risks

- **covered by later slice in approved plan**: `SessionSnapshot.active_run_id` 与 `queued_run_ids` 当前只读取 schema rows；Run / Attempt 的写入与状态推进由 P3-S3/P3-S4 覆盖。
- **covered by later slice in approved plan**: close 后拒绝新 Run/follow-up 的 admission 行为由 P3-S4+ 覆盖。
- **fixed in current slice before review**: 多进程 same-slot ensure 已覆盖，最终只留下一个 Session row 与一个 slot binding。
- **fixed in current slice before review**: create/close 幂等冲突路径已覆盖。

未分类 residual risk: 无。

## Completion / Stop Status

- completion signal met: lifecycle tests pass, EventLog rows and state rows are atomically consistent in covered paths.
- stop condition: not triggered.
- next slice can start: yes, P3-S3 can build on `state.py` helpers and lifecycle-created Session rows.
