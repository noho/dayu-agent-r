# Phase 15 Plan Fix — AgentCodex

## Gate

Phase 15 plan fix。

Fix target:
- `docs/host/phase15-retention-purge-production-hardening-plan.md`

Source review artifacts:
- `docs/reviews/phase15-plan-review-mimo-20260529.md`
- `docs/reviews/phase15-plan-review-ds-20260529.md`
- `docs/reviews/phase15-plan-review-controller-adjudication-20260529.md`

Scope boundary:
- 未修改 source / test / runtime 代码。
- 未启动 `$gateflow` controller 流程。
- 未进入 implementation。
- 未 commit / push / PR。

## Summary

Controller accepted findings ADJ-001 到 ADJ-008 均已在 plan 中修复。修复集中在 delete matrix、S2 FK-safe 删除顺序、idempotency replay、tombstone digest、audit append failure 策略、S5 actual local multiprocess smoke 和 projection checkpoint/failure reset 精确操作。

## Per Finding Status

### ADJ-001 — 已修复 — idempotency_records FK handling

修改位置：
- `Purge Delete Matrix` 新增 `Idempotency records` 行。
- `Slice P15-S2` FK dependency summary 与 delete order step 7。
- `Tests / Validation Matrix` 的 idempotent replay 与 FK/delete ordering 断言。

修复内容：
- 明确旧 command idempotency rows 若 `created_event_id` / `created_event_sequence` 指向 target EventLog，必须在 EventLog 删除前删除。
- 明确保留 purge 自身 replay row，且 `created_event_id` / `created_event_sequence` 为 `NULL`。
- 增加有 existing command idempotency rows 时 purge 在 `PRAGMA foreign_keys=ON` 下成功的测试要求。

为什么满足 design_doc：
- design 要求 purge 删除目标 Session 可恢复事实，同时 tombstone/idempotency replay 仍可用；旧 idempotency rows 是被删除 EventLog facts 的索引，不应阻塞 destructive cleanup。purge 自身 NULL EventLog FK replay row 与 tombstone 保持删除后可重放。

未覆盖项：
- 未实现 SQL helper；implementation slice S2 负责代码落地。

### ADJ-002 — 已修复 — Run source_run_id child ordering

修改位置：
- `Purge Delete Matrix` 的 `Run` 行。
- `Slice P15-S2` delete order step 11。
- `Slice P15-S2` expected assertions 与 `Tests / Validation Matrix`。

修复内容：
- 明确 `host_runs.source_run_id` 自引用必须 child-before-parent 删除。
- 允许 recursive CTE 或 repeated leaf deletion，但必须按依赖深度先删 retry/replay child runs，再删 roots。
- 增加 closed Session 含 retry/replay-linked Runs 可 purge 的测试要求。

为什么满足 design_doc：
- design 要求 purge 覆盖该 Session 的 Run / Attempt recoverable facts；retry/replay 链仍属于同一 Session 的 Host durable state，不能因为自引用 FK 变成不可 purge。

未覆盖项：
- 未选择具体 SQL 算法；plan 允许 implementation 在等价 child-before-parent 策略中选择。

### ADJ-003 — 已修复 — FK dependency graph and assertion

修改位置：
- `Slice P15-S2` 新增 `FK dependency summary`。
- `Slice P15-S2` delete order。
- `Slice P15-S2` expected assertions。
- `Tests / Validation Matrix` 的 FK/delete ordering 断言。

修复内容：
- 增加 concise FK dependency summary，覆盖 idempotency、session slot、runs、attempts、dispatch records、wait records、minimal read model、memory、audit marker、tool trace、outbox、payload descriptor / SQLite payload 依赖。
- 明确测试必须在 `PRAGMA foreign_keys=ON` 下完成 purge，验证无 FK violation。

为什么满足 design_doc：
- design 要求 Host durable truth 与 projection rows 在 SQLite transaction 中保持一致；FK dependency summary 让 implementation 不需要重新推导 schema 拓扑，降低误删/漏删风险。

未覆盖项：
- 未复制完整 DDL；plan 保持 handoff 级摘要，DDL 真源仍是 `dayu/host/durable/schema.py`。

### ADJ-004 — 已修复 — tombstone-only replay

修改位置：
- `Idempotency Design` steps 2-5。
- `Tests / Validation Matrix` 的 idempotent replay 断言。
- `Slice P15-S1` expected assertions。

修复内容：
- 明确 tombstone 存在但 purge idempotency row 缺失时，tombstone 是更强 durable proof。
- 同 key/digest 从 tombstone replay；同 key/different digest 返回 `IDEMPOTENCY_CONFLICT`；different key 返回 already-purged `CONFLICT`。
- 增加 tombstone-only replay 测试要求。

为什么满足 design_doc：
- design 要求 purge 后保留最小 tombstone / audit record，且 Session facts 已删除后不得恢复 facts。tombstone-only replay 直接使用 tombstone，不重建 Session/EventLog。

未覆盖项：
- 未定义手工损坏 DB 的恢复工具；这里只定义 public command replay/conflict 行为。

### ADJ-005 — 已修复 — audit append failure strategy

修改位置：
- `Tombstone Design` 的 `audit_record_ref` / `audit_record_digest` 与 tombstone digest。
- `Slice P15-S4` exact allowed changes、data flow、error handling、expected assertions。
- `Tests / Validation Matrix` 的 Audit JSONL retention 断言。

修复内容：
- 固定 release-blocking 策略为 fail-before-success。
- 删除 audit-pending 成功路径歧义：purge audit line 不能写入时，public `purge_session` 不得返回 successful `PurgeSessionResult`。
- 明确 public success 前 tombstone row 与 purge audit line 都必须成功。
- 增加 audit append failure 测试要求。

为什么满足 design_doc：
- design 明确 purge 必须写 purge tombstone audit record，且 append-only audit JSONL 不可删除。fail-before-success 避免成功返回但审计缺失的状态。

未覆盖项：
- 具体事务/文件 I/O 组织留给 S4 implementation，但成功条件已固定。

### ADJ-006 — 已修复 — precondition_digest input list

修改位置：
- `Tombstone Design` 的 `precondition_digest` 字段。
- `Tests / Validation Matrix` 的 tombstone persistence 断言。

修复内容：
- 将原先开放式 “等 stable facts” 改成显式字段列表。
- 字段覆盖 Session、slot、Run、Attempt、wait、EventLog min/max/count、payload ref count、command idempotency row count、projection/memory/outbox/tool trace row counts。
- 增加 deterministic digest 测试要求。

为什么满足 design_doc：
- tombstone 是 purge auditability 的最小 durable proof；显式 digest 输入保证审计复现，不让 implementation agent 自行选择字段。

未覆盖项：
- 未要求 digest 包含大 refs 列表；大列表由 `deleted_refs_digest` 承担，避免 tombstone 变成大 payload。

### ADJ-007 — 已修复 — multiprocess test scope

修改位置：
- `Slice P15-S5` exact allowed changes、error handling、expected assertions。
- `Tests / Validation Matrix` 的 Local multiprocess/recovery 断言。

修复内容：
- 明确 release-blocking 是 actual local multiprocess smoke，使用 `multiprocessing`、独立 Python 进程、独立 SQLite connections。
- Process A purge closed terminal Session；Process B 打开同 DB Host 后验证 read/retry/replay/watch fail closed。
- 明确不是 same-process multi-handle，也不涉及 remote worker / wire protocol。

为什么满足 design_doc：
- design / controller scope 要求 local multiprocess confidence，同时排除 RemoteProxy / RemoteStub。actual local multiprocess smoke 覆盖本地进程隔离和 SQLite 并发边界，不越界到 remote。

未覆盖项：
- 不覆盖 remote multiprocess 或 wire protocol；这些继续归 issue 73。

### ADJ-008 — 已修复 — projection checkpoint reset operation

修改位置：
- `Purge Delete Matrix` 的 `Projection checkpoint/failure` 行。
- `Slice P15-S2` delete order step 6、error handling。
- `Slice P15-S5` exact allowed changes 与 expected assertions。
- `Tests / Validation Matrix` 的 projection cleanup/rebuild 断言。

修复内容：
- 将 reset 固定为精确 SQL-level DELETE：
  - `DELETE FROM host_projection_checkpoints WHERE checkpoint_event_id IN target_event_ids`
  - `DELETE FROM host_projection_failures WHERE failed_event_id IN target_event_ids`
- 定义 rebuildability criterion：consumer 只消费 committed EventLog、projection rows 可从 remaining EventLog cursor 0 重建、不会写 Host governance state。
- 定义 release-blocking allowed consumer set：minimal read model、memory projection、audit JSONL marker/checkpoint、tool trace hot projection、outbox terminal projection。

为什么满足 design_doc：
- design 要求 projection/audit/outbox/memory 不得成为 truth；精确删除 checkpoint/failure rows 只重置可重建 projection cursor，不让 checkpoint 参与治理判断。

未覆盖项：
- 不引入 heavy projection runner 或 batch tuning；属于 follow-up production hardening。

## Validation

本 gate 只允许文档修复，未运行 source/test 代码验证。已执行轻量文档自检：
- 定位并确认 plan 中 ADJ-001 到 ADJ-008 对应修复点。
- 确认不再保留 audit-pending successful path 的实现选择。

## Residual Risks / Uncovered Areas

- 具体 SQL helper、FK row count assertion、multiprocess smoke 和 audit append failure injection 仍由 implementation slices 落地。
- Cold artifact file deletion失败后的 diagnostic/reporting 仍按原 plan residual cleanup risk 处理。
- RemoteProxy / RemoteStub / wire protocol 不在 P15 release-blocking fix 范围，继续归 issue 73。

## Blocking Questions For Controller

None.
