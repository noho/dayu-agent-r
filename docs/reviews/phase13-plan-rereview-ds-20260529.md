# Phase 13 Plan Re-Review — DS Independent Reviewer

## Gate

Phase 13 plan re-review。复核 controller-accepted findings 是否 fixed。

Re-review target: `docs/host/phase13-audit-tool-trace-outbox-plan.md`

## Verdict

**PASS。无 blocking findings。**

全部 9 项 controller-accepted findings 均已正确修复。无新增回归。

---

## Fix Verification

### DS-F1 — read_outbox_terminal_items 副作用边界 [BLOCKING → FIXED]

**Controller 要求**: 移除 "无副作用" 模糊表述，明确 read 不写 EventLog / Run / Attempt / item_state，允许 projection-local catch-up。

**Plan 修复 (line 198)**:
> "`read_outbox_terminal_items` 不写 EventLog，不更新 Run / Attempt，不改变任何 Outbox item 的 `item_state`，也不写 channel delivery state。它允许在返回前 best-effort catch up OutboxSink；该 catch-up 只能写 projection-local rows、sink-local failure row 与 `host_projection_checkpoints`，不能越过 projection 边界。"

**验证**: 副作用边界精确且可测试。四个 "不" 明确了禁止项；catch-up writes 范围限定为 projection-local。自相矛盾已消除。

**结论: FIXED。**

---

### MiMo-F1 — dedupe_key 对齐 [MATERIAL → FIXED]

**Controller 要求**: 固定 `dedupe_key = terminal_event_id`，不允许复合替代写法。

**Plan 修复**:
- Line 195: "`dedupe_key` 是 UI / Service 与 live `HostEvent.dedupe_key` 对齐的去重键，固定等于 `terminal_event_id`。Phase 13 不允许使用 `run_id + terminal_event_id` 或其它复合替代写法；未来若要改变 dedupe 规则，必须同步修改 `HostEvent.dedupe_key` 的 public contract。"
- Line 375: "`dedupe_key = terminal_event_id`，固定与 live `HostEvent.dedupe_key` 对齐。"

**验证**: "或"的歧义已消除。`dedupe_key = terminal_event_id` 同时出现在 API Shape 说明和 OutboxSink Item Derivation 两处，一致。同时声明了未来变更必须同步修改 HostEvent contract，防止分叉。

**结论: FIXED。**

---

### MiMo-F2 — idempotency_key vs dedupe_key 边界 [MATERIAL → FIXED]

**Controller 要求**: 明确两个 key 的 owner 和用途。

**Plan 修复 (lines 194-195)**:
> "`idempotency_key` 是 OutboxSink durable upsert 与 drain idempotency 使用的稳定幂等键，由 `terminal_event_id`、`run_id` 与 result digest/ref 派生；它属于 Host projection 内部持久化语义，UI / Service 不应依赖它做消息去重。"
> "`dedupe_key` 是 UI / Service 与 live `HostEvent.dedupe_key` 对齐的去重键，固定等于 `terminal_event_id`。"

**验证**: 分工清晰——`idempotency_key` = projection-internal (OutboxSink/drain)，`dedupe_key` = UI/Service (HostEvent 对齐)。两者同源时可相等，但语义边界不再模糊。

**结论: FIXED。**

---

### DS-F2 — purge_session 交互 [MATERIAL → FIXED]

**Controller 要求**: 在 plan 中明确 purge tombstone / cleanup 归 Phase 15，不做 Phase 13 scope expansion。

**Plan 修复**:
- Line 43 (Non-goals): "不实现外部 audit 系统、AuditPolicy 规则引擎、长期归档策略、retention cleanup、purge tombstone audit record、outbox cleanup、tool trace cleanup 或 purge destructive cleanup；这些统一归 Phase 15 Retention / Purge / Production Hardening。"
- Line 412 (Slice 1 Non-goals): "不实现外部 audit 系统、audit query UI、purge tombstone audit record、purge cleanup 或 retention matrix；purge 相关 audit / outbox / tool trace 行为归 Phase 15。"
- Line 604 (Residual risks): "P2 deferred：purge tombstone audit record、outbox cleanup、tool trace cleanup、projection cleanup 与 retention matrix 归 Phase 15；Phase 13 不实现 purge 行为。"

**验证**: 三处一致声明 purge 行为归 Phase 15。Implementation agent 在遇到 purge 事件时明确知道不处理。

**结论: FIXED。**

---

### DS-F3 — tool trace diagnostic whitelist [MATERIAL → FIXED]

**Controller 要求**: 枚举初版 whitelist 或定义 Slice 2 discovery step。

**Plan 修复 (lines 322-333)**:
- Canonical facts whitelist 已枚举具体 event_type: `TOOL_CALL_REQUESTED`, `TOOL_CALL_GOVERNED`, `TOOL_RESULT_ACCEPTED`, `TOOL_AWAITING`, `RUN_WAITING`, `WAIT_LATE_RESULT_REJECTED`, `CONTEXT_COMPACTION_REQUESTED`, `CONTEXT_COMPACTED`, `CONTEXT_COMPACTION_FAILED`, `CONTEXT_COMPACTION_ATTEMPT_REJECTED`, `RUN_SUCCEEDED`, `RUN_FAILED`, `RUN_CANCELLED`, `RUN_LOST`。
- Diagnostic/preview whitelist 已指定 event_class/event_type 组合: `ENGINE_EVENT_DIAGNOSTIC`（含 provider_request_id 时）、`PROVIDER_PROTOCOL_ERROR`、`USAGE_REPORTED`。
- Line 333: "Slice 2 的第一步必须做 typed whitelist discovery：逐项核对上述 event_type 是否已存在、payload view 是否有强类型字段、字段是否足以构造 hot/cold trace。"

**验证**: Whitelist 具体可用。Discovery step 有 stop condition（需要 Engine/ToolRuntime contract change 时停止），防止 implementation 在 payload 不足时自行扩展。

**结论: FIXED。**

---

### DS-F4 — audit marker table 命名 [MATERIAL → FIXED]

**Controller 要求**: 重命名 `host_audit_jsonl_events` 为不暗示 audit event store 的名字。

**Plan 修复 (lines 248-250)**:
- Table 名改为 `host_audit_sink_markers`。
- 注释: "这不是 audit event store，不作为 audit truth，也不作为 audit 查询真源；JSONL 行仍是 audit artifact，EventLog 仍是 Host truth。"

**验证**: 命名正确反映用途（sink-local marker）。disclaimer 防止未来误用。

**结论: FIXED。**

---

### DS-F5 — RUN_LOST outbox mapping [MATERIAL → FIXED]

**Controller 要求**: 明确 RUN_LOST 不创建 public terminal item，用 detail_code 标记。

**Plan 修复**:
- Line 374: "Phase 13 第一版 OutboxSink 对 `RUN_LOST` 返回 `ProjectionApplyResult(SKIPPED, detail_code="run_lost_not_public_terminal_item")`，不创建 public terminal item。LOST notification / outbox item 化必须进入 recovery / public terminal contract gate 后再议。"
- Line 483 (Slice 3 exact changes): 重复确认 same behavior。

**验证**: 返回类型 (`SKIPPED`)、detail_code (`"run_lost_not_public_terminal_item"`) 均具体给出。Implementation agent 无需自行决策。

**结论: FIXED。**

---

### DS-F6 — tool trace query helper 分页 [LOW → FIXED]

**Controller 要求**: 统一所有 helper 的返回类型和分页语义。

**Plan 修复 (lines 355-359)**:
- 四个 helper 统一签名: `(after_event_sequence: int, limit: int) -> ToolTraceQueryPage`。
- `ToolTraceQueryPage` 定义为 internal dataclass: `rows: tuple[ToolTraceHotRow, ...]`, `next_event_sequence: int`, `has_more: bool`。
- 统一排序: `event_sequence ASC`, `event_sequence > after_event_sequence`。
- 明确: 相同 id 可返回多行，不隐式只取最新一条。

**验证**: 签名一致，分页语义完整。multi-row 行为明确。

**结论: FIXED。**

---

### DS-F8 — projection-lag anti-leak smoke [LOW → FIXED]

**Controller 要求**: Slice 4 tests 中加入 lag + second-read anti-leak case。

**Plan 修复 (line 542)**:
> "anti-leak lag case：第一次 drain/read 返回 `projection_status=LAGGED` 且无 terminal item；随后 OutboxSink catch-up 和 second read 返回该 terminal item，Service 以 `dedupe_key=terminal_event_id` upsert 后不重复展示。"

**验证**: 显式描述了 lag → catch-up → second-read → no-duplicate 的完整链。与设计目标 "无漏离线 terminal notification" 对齐。

**结论: FIXED。**

---

## Regression Check

对照修复前后 plan 全文，检查是否引入新问题：

| 检查项 | 状态 |
|--------|------|
| Engine 修改禁止未松动 | PASS |
| command path / EventLog append 不变 | PASS |
| watch_session_events live-only 不变 | PASS |
| OpenHostOptions 无新增字段 | PASS |
| Outbox read/drain 为唯一 public extension | PASS |
| 所有 public types 严格类型化 | PASS |
| 无 compat re-export / wrapper | PASS |
| Slice file ownership 边界不变 | PASS |
| `RUN_LOST` 在事件输入中列出 + consumer 返回 SKIPPED 一致性 | PASS (正确: 消费但不创建 item) |
| 修复间无冲突 | PASS |

---

## Summary

| Finding ID | Severity (orig) | Status |
|------------|-----------------|--------|
| DS-F1 | BLOCKING | FIXED |
| MiMo-F1 | MATERIAL | FIXED |
| MiMo-F2 | MATERIAL | FIXED |
| DS-F2 | MATERIAL | FIXED |
| DS-F3 | MATERIAL | FIXED |
| DS-F4 | MATERIAL | FIXED |
| DS-F5 | MATERIAL | FIXED |
| DS-F6 | LOW | FIXED |
| DS-F8 | LOW | FIXED |

9/9 controller-accepted findings verified fixed。无 blocking findings。无新回归。

**Plan is handoff-ready.** Implementation agent 可按 4 slices 顺序执行，无需重新设计。
