# Phase 15 Plan Re-Review — AgentMiMo

## Reviewer

AgentMiMo (plan re-review specialist)。

## Re-review Scope

- Re-review target plan: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- Fix artifact: `docs/reviews/phase15-plan-fix-codex-20260529.md`
- Original review: `docs/reviews/phase15-plan-review-mimo-20260529.md`
- Other review: `docs/reviews/phase15-plan-review-ds-20260529.md`
- Controller adjudication: `docs/reviews/phase15-plan-review-controller-adjudication-20260529.md`

## Task

仅审查 Controller accepted findings ADJ-001 到 ADJ-008，判断 plan fix 是否完全关闭每个 finding。不引入无关风格 finding，除非 fix 产生了新 blocker。

---

## Per Finding Final Status

### ADJ-001 — 已修复 — idempotency_records FK handling

Plan 证据:
- `Purge Delete Matrix` line 160: 新增 `Idempotency records` 行，明确删除 "created_event_id / created_event_sequence 指向 target Session EventLog rows 的记录" 以及 "scope_id = session_id 且 scope_kind 属于 Session / Run command 的记录"，同时 "保留新 purge_session replay row，且该 row 必须使用 created_event_id = NULL、created_event_sequence = NULL"
- `Slice P15-S2` FK dependency summary line 376: `idempotency_records.created_event_id / created_event_sequence -> event_log and must be deleted for target EventLog refs before EventLog rows`
- `Slice P15-S2` delete order step 7 (line 405): 明确 old command idempotency records 删除 + 保留 new purge_session idempotency row with NULL refs
- `Slice P15-S2` expected assertions line 448-449: "Purge succeeds with PRAGMA foreign_keys=ON; tests must assert no FK violation when target Session has existing command idempotency rows" + "Purge preserves and replays through the new purge_session idempotency row with NULL created_event_id / created_event_sequence"
- `Tests / Validation Matrix` lines 729, 745-747: 覆盖 idempotency rows FK、FK/delete ordering 断言

结论: 完全满足 ADJ-001 要求。idempotency_records 已加入 delete matrix、在 EventLog 前删除、保留 purge replay row with NULL FK、有测试覆盖。

---

### ADJ-002 — 已修复 — Run source_run_id child ordering

Plan 证据:
- `Purge Delete Matrix` line 164: Run 行明确 "删除时必须按 source_run_id 自引用依赖子先父后：先删引用其它 Run 的 retry/replay child runs，再删 source roots；可用递归 CTE 计算依赖深度并按 depth DESC 删除"
- `Slice P15-S2` delete order step 11 (line 409): "runs in source dependency order: compute retry/replay child depth from source_run_id and delete deepest children first, then roots; implementation may use a recursive CTE or repeated leaf deletion, but must prove child-before-parent under PRAGMA foreign_keys=ON"
- `Slice P15-S2` expected assertions line 450: "Closed Session containing retry/replay-linked Runs purges successfully, proving child-before-parent source_run_id ordering"
- `Tests / Validation Matrix` line 746: "retry/replay-linked Run chains delete child-before-parent and purge successfully"

结论: 完全满足 ADJ-002 要求。source_run_id 自引用 FK 子排序已明确、允许递归 CTE 或 repeated leaf deletion、有测试覆盖。

---

### ADJ-003 — 已修复 — FK dependency graph and assertion

Plan 证据:
- `Slice P15-S2` lines 374-386: 新增完整 FK dependency summary，覆盖 idempotency_records、session_slots、runs（含 source_run_id self-FK）、attempts、dispatch_records、wait_records、run_results、timeline_items、memory_snapshots/items/diagnostics（含 CASCADE）、audit_sink_markers、tool_trace_hot、outbox_terminal_items、payload_descriptors/sqlite_payloads
- `Slice P15-S2` delete order steps 1-15 (lines 399-413): 完整 FK-safe 删除顺序
- `Slice P15-S2` expected assertions line 448: "Purge succeeds with PRAGMA foreign_keys=ON; tests must assert no FK violation"
- `Tests / Validation Matrix` lines 744-747: "full purge completes with PRAGMA foreign_keys=ON" + payload cleanup 顺序

结论: 完全满足 ADJ-003 要求。FK 依赖图摘要完整、删除顺序显式、PRAGMA foreign_keys=ON 断言存在。

---

### ADJ-004 — 已修复 — tombstone-only replay

Plan 证据:
- `Idempotency Design` step 3 (lines 192-195): "Tombstone 存在但 purge idempotency row 缺失时，tombstone 是更强 durable proof"，覆盖 same key/digest -> replay、same key/different digest -> IDEMPOTENCY_CONFLICT、different key -> CONFLICT
- `Conflict classification` lines 206-207: 新增 "Tombstone-present / idempotency-missing / same key and same digest: return replay result from tombstone" 和 "Tombstone-present / idempotency-missing / same key and different digest: HostApiErrorCode.IDEMPOTENCY_CONFLICT"
- `Tests / Validation Matrix` line 728: "tombstone exists but purge idempotency row is missing: same key/digest replays from tombstone, same key/different digest conflicts, different key returns already-purged conflict"
- `Slice P15-S1` expected assertions line 336: "Same (session_id, client_request_id, digest) replays after no Session row exists"

结论: 完全满足 ADJ-004 要求。tombstone-only replay 路径已明确定义三种子场景、有测试覆盖。

---

### ADJ-005 — 已修复 — audit append failure strategy

Plan 证据:
- `Tombstone Design` line 232: "Release-blocking 策略固定为 fail-before-success：如果 purge audit line 不能写入并取得 digest，public purge_session 不得返回 successful PurgeSessionResult"
- `Slice P15-S4` exact allowed changes line 558: "Enforce fail-before-success audit strategy: public purge_session may return success only after the purge tombstone audit line has been appended and its digest/ref is known. If audit append fails, return a retryable HostApiErrorCode.INTERNAL_ERROR or equivalent existing durable-to-public error and do not return PurgeSessionResult(purged=True, ...)"
- `Slice P15-S4` exact allowed changes line 559: "If implementation writes DB tombstone before audit append, it must rollback or compensate inside the same command so the public failure path does not leave a successful tombstone without a purge audit line. No audit-pending successful state is allowed in release-blocking scope"
- `Slice P15-S4` error handling lines 571-572: "Audit append failure must fail the public command before success. The plan explicitly rejects an audit-pending success path"
- `Slice P15-S4` data flow line 564: "Any audit append failure exits before public success"
- `Slice P15-S4` expected assertions line 589: "Injected audit append failure causes public purge_session to fail and not return a successful PurgeSessionResult; tests must assert no audit-pending successful tombstone path is observable"
- `Tests / Validation Matrix` line 739: "audit append failure does not return successful PurgeSessionResult and no audit-pending success path is observable"

结论: 完全满足 ADJ-005 要求。歧义已消除——固定为 fail-before-success、明确删除 audit-pending 成功路径、有测试覆盖。

---

### ADJ-006 — 已修复 — precondition_digest input list

Plan 证据:
- `Tombstone Design` line 228: `precondition_digest` 字段从 "等 stable facts" 改为显式穷举列表：`session_id`、Session `status`、Session `created_event_id` / `created_event_sequence`、Session `closed_event_id` / `closed_event_sequence`、bound slot refs `(scope, slot_key)`、按 `run_id ASC` 排序的 Run entries（含 run_id/status/accepted/queued/started/terminal event refs/current_attempt_id/source_run_id/source_run_relation）、按 `attempt_id ASC` 排序的 Attempt entries（含 attempt_id/run_id/execution_id/status/started/terminal event refs）、按 `wait_id ASC` 排序的 wait entries（含 wait_id/run_id/attempt_id/execution_id/status/created/updated event refs）、target Session event_log 的 MIN/COUNT/MAX、payload ref count、command idempotency row count、pre-purge projection/memory/outbox/tool trace hot row counts by table
- `Tests / Validation Matrix` line 734: "precondition_digest is deterministic from the explicit field list in Tombstone Design"

结论: 完全满足 ADJ-006 要求。开放式 "等 stable facts" 已替换为显式字段穷举列表、有 determinism 测试覆盖。

---

### ADJ-007 — 已修复 — multiprocess test scope

Plan 证据:
- `Slice P15-S5` exact allowed changes line 627: "Add actual local multiprocess smoke using multiprocessing with independent Python processes and separate SQLite connections, following existing test_recovery_multiprocess.py / test_admission_multiprocess.py style. Process A opens Host and purges a closed terminal Session; Process B opens a separate Host handle against the same DB after purge commit and asserts get_session / get_run / retry_run or replay_run / watch_session_events fail closed with existing typed behavior. This is not same-process multi-handle and does not involve remote worker or wire protocol."
- `Slice P15-S5` error handling line 641: "Tests must use independent processes, not only two handles in one process"
- `Slice P15-S5` expected assertions line 656: "Actual local multiprocess read/replay/watch after purge returns not_found/conflict as designed, using independent processes and no remote path"
- `Tests / Validation Matrix` line 717: 覆盖 local multiprocess/recovery 断言

结论: 完全满足 ADJ-007 要求。已明确为 actual local multiprocess（multiprocessing、独立进程、独立 SQLite connections）、排除 same-process multi-handle 和 remote worker。

---

### ADJ-008 — 已修复 — projection checkpoint reset operation

Plan 证据:
- `Purge Delete Matrix` line 173: Projection checkpoint/failure 行明确 "精确 reset：`DELETE FROM host_projection_checkpoints WHERE checkpoint_event_id IN target_event_ids`；`DELETE FROM host_projection_failures WHERE failed_event_id IN target_event_ids`"，并定义 rebuildability criterion（"consumer 只消费 committed EventLog、projection rows 可从 remaining EventLog 从 cursor 0 重建、不会写 Host governance state"）和 release-blocking allowed consumer set（"minimal read model、memory projection、audit JSONL marker/checkpoint、tool trace hot projection、outbox terminal projection；不得 reset recovery/admission/state owner"）
- `Slice P15-S2` delete order step 6 (line 404): "projection checkpoints/failures using exact reset SQL: DELETE FROM host_projection_checkpoints WHERE checkpoint_event_id IN target_event_ids and DELETE FROM host_projection_failures WHERE failed_event_id IN target_event_ids"
- `Slice P15-S2` error handling line 430: rebuildability criterion 和 allowed consumer set 明确
- `Tests / Validation Matrix` line 742: "checkpoint/failure reset uses exact DELETE of rows whose checkpoint/failure event id is in target EventLog ids, and only for rebuildable projection/sink consumers"

结论: 完全满足 ADJ-008 要求。reset 已固定为精确 DELETE SQL、rebuildability criterion 已定义、allowed consumer set 已明确、有测试覆盖。

---

## New Blocker Check

Fix 未引入新 blocker。修复内容均为在已有 plan 结构上补充精确性（FK 依赖图、删除顺序、idempotency 路径、audit 策略、digest 字段、测试 scope、reset SQL），未改变 plan 的 scope、public API 约束、分层架构或 slice 结构。

---

## Final Summary

| ADJ Finding | Final Status |
| --- | --- |
| ADJ-001 — idempotency_records FK handling | 已修复 |
| ADJ-002 — Run source_run_id child ordering | 已修复 |
| ADJ-003 — FK dependency graph and assertion | 已修复 |
| ADJ-004 — tombstone-only replay | 已修复 |
| ADJ-005 — audit append failure strategy | 已修复 |
| ADJ-006 — precondition_digest input list | 已修复 |
| ADJ-007 — multiprocess test scope | 已修复 |
| ADJ-008 — projection checkpoint reset operation | 已修复 |

**结论: PASS** — ADJ-001 到 ADJ-008 全部已修复，无新 blocker。Plan handoff-ready。
