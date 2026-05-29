# Phase 15 Plan Review — AgentDS

## Gate

Phase 15 plan review — handoff-ready / code-generation-ready assessment.

## Sources Reviewed

- Plan artifact: `docs/host/phase15-retention-purge-production-hardening-plan.md`
- Design truth: `docs/host/design.md` (purge_session / EventLog / audit sections)
- Implementation control: `docs/host/implementation-control.md` (Phase 15 section)
- Controller artifact: `docs/reviews/phase15-design-discussion-controller-20260529.md`
- Code evidence: `dayu/host/api.py`, `dayu/host/command.py`, `dayu/host/durable/schema.py`, `dayu/host/durable/transaction.py`

## Conclusion

**PASS** — plan is handoff-ready with 2 non-blocking findings and 4 observations. No finding blocks plan acceptance. Findings 1 and 3 require resolution during S2 implementation but do not invalidate the plan structure.

## Findings

### F15-PLAN-DS-001-未修复-高-idempotency_records FK 阻塞 EventLog 删除

- Plan位置: Slice P15-S2 删除矩阵步骤 1-14 与 purge delete matrix 表
- 问题类型: FK 约束遗漏 — 删除安全
- 计划当前写法:
  Delete matrix 对 `idempotency_records` 表无任何删除/处理动作。该表在 schema.py:255-256 有 `FOREIGN KEY(created_event_id) REFERENCES event_log(event_id)` 和 `FOREIGN KEY(created_event_sequence) REFERENCES event_log(event_sequence)`（nullable），且 `transaction.py:364` 已开启 `PRAGMA foreign_keys=ON`。

- 为什么有问题:
  目标 Session 的生命周期操作（`create_session`、`close_session`、`start_run`、`cancel_run`、`submit_followup` 等）均在 `idempotency_records` 中遗留记录，其 `created_event_id`、`created_event_sequence` 指向目标 Session EventLog rows。当 purge 步骤 13 尝试删除 EventLog rows 时，SQLite FK 约束将阻止删除，导致 transaction 失败。

- 直接证据:
  - `schema.py:243-265`: `TABLE_IDEMPOTENCY_RECORDS` DDL，`created_event_id`/`created_event_sequence` FK 到 `event_log`
  - `transaction.py:364`: `PRAGMA foreign_keys=ON` 确认 FK 强制执行
  - Plan 文档: purge delete matrix 表未列出 idempotency_records；步骤 1-14 无 idempotency_records 处理

- 影响:
  若按当前 plan 的 delete matrix 实施，任何有 idempotency 记录的 Session purge 都会在 EventLog 删除步骤失败，返回 `INTERNAL_ERROR`。这等价于 purge 对大部分已发生操作的 Session 不可用，破坏 release-blocking 目标。

- 建议改法和验证点:
  在 S2 的 FK-safe 删除顺序中补入对目标 Session 的 idempotency_records 的删除（在 EventLog 删除之前）。删除范围：所有 `scope_id = session_id` 且 `created_event_id IS NOT NULL` 的记录。验证点：
  - 有 idempotency 记录的 closed Session purge 成功
  - purge idempotency replay 不依赖已删除的 idempotency_records（应走 tombstone 路径）
  - `purge_session` 自身的新 idempotency record 使用 `created_event_id = NULL` 不受影响

- 修复风险: 低
- 严重程度: 高

### F15-PLAN-DS-002-未修复-中-Run source_run_id 自引用 FK 子排序缺失

- Plan位置: Slice P15-S2 步骤 10（删除 runs）
- 问题类型: FK 约束遗漏 — 删除安全
- 计划当前写法:
  步骤 10 仅写"runs"，未指定 `source_run_id` 自引用 FK 的子删除顺序。

- 为什么有问题:
  `schema.py:382`: `FOREIGN KEY(source_run_id) REFERENCES host_runs(run_id)`。若目标 Session 内存在 retry/replay 链（Run B 的 `source_run_id` 指向同 Session 的 Run A），删除 Run A 前必须先删除 Run B，否则 FK 约束失败。

- 直接证据:
  - `schema.py:382`: source_run_id FK 到 host_runs(run_id)
  - Plan S2 步骤 10: 仅写 `runs` 无子排序

- 影响:
  有 retry/replay 链的 Session purge 在删除 runs 时失败。

- 建议改法和验证点:
  步骤 10 补子排序："先删除 source_run_id IS NOT NULL 的 runs，再删除 source_run_id IS NULL 的 runs"，或使用递归 CTE 按依赖深度删除。验证点：含 retry→replay 链的 closed Session purge 成功。

- 修复风险: 低
- 严重程度: 中

### F15-PLAN-DS-003-未修复-低-Projection checkpoint reset 机制未指定操作类型

- Plan位置: Slice P15-S2 步骤 6（projection checkpoints/failures）
- 问题类型: 实现细节不足
- 计划当前写法:
  "safe reset：删除 checkpoint/failure rows，使后续 rebuild 从 remaining EventLog 重新追平"与"Projection checkpoint reset is allowed only for consumers whose rows are rebuildable from remaining EventLog"

- 为什么有问题:
  "reset" 未在 plan 中固化为具体 SQL 操作（DELETE），implementation agent 可能误解为 UPDATE 或其他非标准操作。同时"rebuildable from remaining EventLog"的判断标准未定义——是 consumer 类型白名单？还是动态检查？这会影响 implementation 的确定性。

- 直接证据: Plan S2 步骤 6 描述为 "safe reset" 无操作类型

- 影响:
  S2 实现时可能产生歧义，不同 implementer 可能给出不同实现。非阻塞——DELETE 是最自然的选择，S2 实现时可闭合。

- 建议改法和验证点:
  Plan S2 步骤 6 明确写 "DELETE FROM host_projection_checkpoints WHERE checkpoint_event_id IN (target event ids)" 和 "DELETE FROM host_projection_failures WHERE failed_event_id IN (target event ids)"。验证点：reset 后 consumer rebuild 不产生 purged Session 的派生行。

- 修复风险: 低
- 严重程度: 低

## Non-blocking Observations

### OBS-001: Audit JSONL append post-transaction 失败窗口

Plan S4 允许 "若 audit append 设计为 commit 后执行，首次 transaction 可为 NULL" 并随后补写。若补写失败，tombstone 存在但 audit record 缺失。Plan 已意识到此风险并要求 "不能声称 audit retention 完成"，但未强制必须失败 command 而非 silent success。建议 S4 实现中优先选择 **必须在 transaction 内完成 audit JSONL append**，或若 post-commit 则必须失败 command。

### OBS-002: Payload descriptor / SQLite payload FK 子排序

Plan 步骤 14 未明确 `payload_descriptors`（FK 到 `sqlite_payloads`）与 `sqlite_payloads` 的删除先后。应先删除 unreferenced descriptors，再删除被已删除 descriptor 引用的 sqlite_payloads（反之 FK 约束失败）。S2 实现应显式标注此顺序。

### OBS-003: host_memory_items ON DELETE CASCADE 影响

`schema.py:805-806` 中 `host_memory_items` 对 `host_memory_snapshots` 有 `ON DELETE CASCADE`。Plan delete matrix memory 行已提及 "items 也会因 snapshot cascade 删除"，但 S2 步骤 4 的删除顺序未体现此 cascade 行为。若显式先 delete items 再 delete snapshots 可获得准确 deleted counts；若先 delete snapshots 则 cascade 自动删除 items 但 deleted counts 需额外统计。S2 实现应明确选择其一。

### OBS-004: 缺少 concurrent double-purge 测试

Tests/Validation Matrix 包含 "concurrent command vs purge resolves by transaction ordering"，但未明确测试同一 Session 的两个并发 purge 请求（不同 client_request_id）。SQLite serialization 会处理此场景（首个成功写 tombstone，第二个看到 tombstone 返回 CONFLICT），但应有显式测试覆盖。

## Residual Risks (Post-Plan, For Implementation)

1. **Shared cold artifact ref-count correctness**: 跨 Session artifact 引用判断依赖 `payload_descriptors` 的 `artifact_relative_path` 全量扫描；大 DB 时此扫描不应在 write transaction 内执行。S2 实现应将 ref-count 检查放在 transaction 前的 read phase。

2. **Projection rebuild after checkpoint reset**: 若 projection consumer 的 rebuild 逻辑依赖 checkpoint 作为唯一 resume cursor，reset 后 consumer 将从头扫描 EventLog（可能很长时间）。P15 实现需确认现有 consumers 支持从 EventLog 起始扫描。

3. **audit_audit_sink_markers FK 与 audit JSONL 的一致性问题**: 删除 markers 后，若 audit JSONL 读取工具依赖 marker 判断"已写入"，可能认为某个 event 的 audit line 不存在。这不应发生——marker 是 sink-local idempotency，audit JSONL 是 truth。S4 验证应确认此 invariant。

## Review Summary

| 维度 | 评估 |
| --- | --- |
| 动机成立 | PASS — controller 已确认，直接代码证据支撑 |
| Scope 适当 | PASS — release-blocking 与 follow-up 清晰分离 |
| 不改变 public API | PASS — 仅使用 frozen envelope |
| 不违反分层 | PASS — Engine/Service/UI/Fins 均禁止修改 |
| Projection 不成为 truth | PASS — 多处明确约束 |
| FK 删除安全 | PASS with finding — F15-PLAN-DS-001/002 需 S2 落实 |
| Idempotency 设计 | PASS — replay/conflict 路径完整 |
| Audit JSONL 保留 | PASS — OBS-001 为实现期风险 |
| Slice 粒度 | PASS — 6 slices 可独立验证 |
| Tests 覆盖 | PASS — OBS-004 建议补并发测试 |

结论：**PASS**。2 finding（1 高 1 中），4 observation。Finding 均为 S2 实现期可闭合的 FK 安全细节，不阻塞 plan acceptance。建议 implementation agent 在 S2 开始时先阅读本文档 findings 再进入 delete matrix 实现。
