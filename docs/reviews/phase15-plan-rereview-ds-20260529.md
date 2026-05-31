# Phase 15 Plan Re-review — AgentDS

## Gate

Phase 15 plan re-review — verify Controller-adjudicated findings ADJ-001 through ADJ-008 are closed in the fixed plan.

## Reviewed Artifacts

- Fix target plan: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- Fix artifact: `docs/reviews/phase15-plan-fix-codex-20260529.md`
- Controller adjudication: `docs/reviews/phase15-plan-review-controller-adjudication-20260529.md`
- Original reviews: `docs/reviews/phase15-plan-review-ds-20260529.md`, `docs/reviews/phase15-plan-review-mimo-20260529.md`

## Per-Finding Status

### ADJ-001 — 已修复 — idempotency_records FK handling

- Plan 变更证据:
  - Purge Delete Matrix 表新增 "Idempotency records" 行（plan:160），明确旧 command idempotency rows 删除规则与 purge replay row 保留规则。
  - S2 FK dependency summary 列出 `idempotency_records` FK 依赖（plan:376）。
  - S2 delete order step 7（plan:405）：在 EventLog 删除前删除旧 command idempotency records。
  - Tests matrix（plan:729）：要求 existing non-purge command idempotency rows 不阻塞 purge。
  - Tests matrix（plan:448）：要求 `PRAGMA foreign_keys=ON` 下 purge 成功。

- 验证：Plan 已满足 ADJ-001 全部三项要求——入矩阵、指定删除位置、保留 NULL FK replay row、补测试。Fix artifact 描述与 plan 实际内容一致。

### ADJ-002 — 已修复 — Run source_run_id child ordering

- Plan 变更证据:
  - Purge Delete Matrix "Run" 行（plan:164）：明确 `source_run_id` 子先父后删除，允许 recursive CTE 或 repeated leaf deletion。
  - S2 delete order step 11（plan:409）："delete deepest children first, then roots"。
  - S2 expected assertions（plan:450）：closed Session 含 retry/replay-linked Runs 可 purge。

- 验证：自引用 FK 排序已固化为明确策略，测试覆盖。Fix artifact 描述一致。

### ADJ-003 — 已修复 — FK dependency graph and assertion

- Plan 变更证据:
  - S2 新增 FK dependency summary（plan:374-386）：覆盖 idempotency、slots、runs、attempts、dispatch records、wait records、minimal read model、memory、audit marker、tool trace、outbox、payload 全部依赖。
  - S2 expected assertions（plan:448）：`PRAGMA foreign_keys=ON` 下 purge 无 FK violation。

- 验证：FK dependency summary 完整且与 `schema.py` FK 图一致。Plan 额外覆盖了 `host_memory_items ON DELETE CASCADE`（plan:384）、payload descriptor → sqlite_payloads 方向（plan:386），澄清了 original review 中 OBS-002/OBS-003 的模糊点。

### ADJ-004 — 已修复 — tombstone-only replay

- Plan 变更证据:
  - Idempotency Design step 3（plan:192-195）：新增 tombstone 存在但 idempotency row 缺失时的三种分支行为。
  - Conflict classification（plan:206-207）：新增两条 tombstone-only 错误分类。
  - S1 expected assertions（plan:343）：tombstone-present/idempotency-missing 场景。
  - Tests matrix（plan:728）：tombstone-only replay 和 conflict 测试要求。

- 验证：所有四个场景（同 key/digest replay、同 key/diff digest conflict、不同 key conflict、tombstone+idempotency 双路径）均已覆盖。Fix artifact 描述一致。

### ADJ-005 — 已修复 — audit append failure strategy

- Plan 变更证据:
  - Tombstone Design "audit_record_ref"（plan:232）：固定为 fail-before-success；明确 "不允许 audit-pending 成功路径"。
  - S4 exact allowed changes（plan:558-559）：强制 audit append 失败时返回 INTERNAL_ERROR，若先写 tombstone 必须 rollback 或 compensate。
  - S4 data flow（plan:564）：明确 "Any audit append failure exits before public success"。
  - S4 expected assertions（plan:589）：injected audit append failure 不返回 successful result。
  - Tests matrix（plan:739）：audit append failure 测试。

- 验证：双路径歧义已完全消除，fail-before-success 已写入 S4 各处。与 design doc "purge 必须写入 purge tombstone audit record" 一致。

### ADJ-006 — 已修复 — precondition_digest input list

- Plan 变更证据:
  - Tombstone Design "precondition_digest"（plan:228-229）：将 "等 stable facts" 替换为显式穷举字段列表，覆盖 Session 状态、bound slot refs、Run/Attempt/wait 完整状态与 event refs、EventLog 统计、payload/idempotency/projection/memory/outbox/tool trace 行计数。
  - Tests matrix（plan:734）：deterministic digest 测试要求。

- 验证：字段列表全面且明确。Fix artifact 描述一致。

### ADJ-007 — 已修复 — multiprocess test scope

- Plan 变更证据:
  - S5 exact allowed changes（plan:627）：明确 "actual local multiprocess smoke using `multiprocessing` with independent Python processes and separate SQLite connections"；排除 same-process multi-handle。
  - S5 error handling（plan:641）："Tests must use independent processes, not only two handles in one process"。
  - S5 expected assertions（plan:656）："actual local multiprocess read/replay/watch after purge returns not_found/conflict as designed, using independent processes"。
  - Tests matrix（plan:753）：actual independent-process local multiprocess。

- 验证：same-process multi-handle 歧义已消除。Scope 边界明确（不涉及 remote worker/wire protocol）。

### ADJ-008 — 已修复 — projection checkpoint reset operation

- Plan 变更证据:
  - Purge Delete Matrix "Projection checkpoint/failure"（plan:173）：精确 DELETE SQL 语句；rebuildability criterion 三条标准；allowed consumer set 五个 consumer。
  - S2 delete order step 6（plan:404）：精确 DELETE SQL。
  - S2 error handling（plan:430）：明确 rebuildability criterion 与 allowed consumers。
  - Tests matrix（plan:742）："exact DELETE of rows whose checkpoint/failure event id is in target EventLog ids, and only for rebuildable projection/sink consumers"。

- 验证：从模糊 "safe reset" 固化为精确 SQL DELETE + 白名单 consumer set。Fix artifact 描述一致。

## New Blocker Check

逐个检查 8 项修复是否引入新的阻塞问题：

- ADJ-001 引入 idempotency records 删除（step 7）：不产生新的 FK 顺序问题——idempotency records 只 FK 到 event_log，在 event_log 删除前（step 14）删除，正确。
- ADJ-002 引入 child-before-parent run deletion：不改变 15-step 框架，仅在 step 11 内部细化。
- ADJ-003 FK dependency summary：纯文档增量，不引入新逻辑。
- ADJ-004 tombstone-only replay：纯 idempotency 路径补充，不涉及 schema/FK 变更。
- ADJ-005 fail-before-success audit：变更为约束收紧，不引入新路径。
- ADJ-006 precondition_digest 穷举：纯字段规范，不改变 schema。
- ADJ-007 multiprocess 明确：纯测试 scope 澄清。
- ADJ-008 checkpoint DELETE：从模糊到精确，不扩大删除范围。

**未发现新 blocker。**

## 15-step FK-safe Delete Order 复核

| Step | Target | 依赖的父表 | 父表删除步骤 | FK 安全 |
|------|--------|-----------|-------------|---------|
| 1 | audit sink markers | event_log | 14 | ✓ child first |
| 2 | outbox terminal/drain | event_log | 14 | ✓ child first |
| 3 | tool trace hot | event_log | 14 | ✓ child first |
| 4 | memory items/diag/snapshots | event_log, snapshots (cascade) | 14 | ✓ child first, cascade OK |
| 5 | minimal read model | event_log, sessions, runs | 13, 11, 14 | ✓ child first |
| 6 | projection checkpoint/failure | event_log | 14 | ✓ child first |
| 7 | idempotency records | event_log | 14 | ✓ child first (新增) |
| 8 | wait records | event_log, sessions, runs, attempts | 14, 13, 11, 10 | ✓ child first |
| 9 | dispatch records | event_log, runs, attempts, instances | 14, 11, 10 | ✓ child first |
| 10 | attempts | event_log, runs | 14, 11 | ✓ child first |
| 11 | runs (child-before-parent) | event_log, sessions, runs(self) | 14, 13 | ✓ child first + self-FK ordered |
| 12 | session slots | event_log, sessions | 14, 13 | ✓ child first |
| 13 | session row | event_log | 14 | ✓ child first |
| 14 | EventLog rows | payload_descriptors | 15 | ✓ parent after |
| 15 | payload descriptors / SQLite | sqlite_payloads (descriptors FK to) | — | ✓ child first within step |

**结论：FK-safe 删除顺序不变，新增 step 7 不破坏安全性。**

## Conclusion

**PASS**

8/8 Controller-accepted findings 均已修复（已修复: 8, 部分修复: 0, 未修复: 0, 证据失效: 0）。修复内容与 fix artifact `phase15-plan-fix-codex-20260529.md` 描述一致。无新 blocker 引入。Plan 现为 code-generation-ready。
