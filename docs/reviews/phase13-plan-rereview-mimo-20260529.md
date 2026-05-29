# Phase 13 Plan Re-Review

## Reviewer

MiMo (independent plan reviewer)

## Date

2026-05-29

## Re-review Target

`docs/host/phase13-audit-tool-trace-outbox-plan.md` (updated after fix)

## Source Artifacts

- `docs/reviews/phase13-plan-review-mimo-20260529.md`
- `docs/reviews/phase13-plan-review-ds-20260529.md`
- `docs/reviews/phase13-plan-review-controller-adjudication-20260529.md`
- `docs/reviews/phase13-plan-fix-codex-20260529.md`

## Verdict

**PASS。所有 accepted findings 已修复，无 blocking findings。**

---

## Accepted Findings 复核

### DS-F1 read_outbox_terminal_items side-effect boundary

**Controller 要求：** 替换 side-effect-free 矛盾措辞，明确 read 不写 EventLog / Run / Attempt / item_state，但允许 projection-local catch-up。

**Plan 修复验证：**

- Line 198："`read_outbox_terminal_items` 不写 EventLog，不更新 Run / Attempt，不改变任何 Outbox item 的 `item_state`，也不写 channel delivery state。它允许在返回前 best-effort catch up OutboxSink；该 catch-up 只能写 projection-local rows、sink-local failure row 与 `host_projection_checkpoints`，不能越过 projection 边界。"
- Line 380："catch-up 只能产生 projection-local writes，失败通过 `projection_status=LAGGED` 或 `projection_status=FAILED` 暴露。"
- Line 206："不得伪装为完整补读，不得静默返回 stale empty。"

**结论：FIXED。** 副作用边界精确，矛盾已消除。

---

### MiMo-F1 Outbox dedupe_key alignment

**Controller 要求：** 固定 `dedupe_key = terminal_event_id`，不允许 `run_id + terminal_event_id` 替代。

**Plan 修复验证：**

- Line 195："Phase 13 不允许使用 `run_id + terminal_event_id` 或其它复合替代写法；未来若要改变 dedupe 规则，必须同步修改 `HostEvent.dedupe_key` 的 public contract。"
- Line 375："`dedupe_key = terminal_event_id`，固定与 live `HostEvent.dedupe_key` 对齐。"

**结论：FIXED。** 已固定为单一值，二义性消除。

---

### MiMo-F2 idempotency_key versus dedupe_key boundary

**Controller 要求：** 定义 `idempotency_key` 为 Sink durable upsert / drain 幂等键，`dedupe_key` 为 UI / Service 去重键。

**Plan 修复验证：**

- Line 194："``idempotency_key`` 是 OutboxSink durable upsert 与 drain idempotency 使用的稳定幂等键，由 `terminal_event_id`、`run_id` 与 result digest/ref 派生；它属于 Host projection 内部持久化语义，UI / Service 不应依赖它做消息去重。"
- Line 195："``dedupe_key`` 是 UI / Service 与 live `HostEvent.dedupe_key` 对齐的去重键，固定等于 `terminal_event_id`。"

**结论：FIXED。** 两个 key 的消费方、派生方式和语义边界已明确。

---

### DS-F2 purge_session interaction

**Controller 要求：** 在 Non-goals 和 residual risk 中明确 purge 相关行为归 Phase 15。

**Plan 修复验证：**

- Line 43 (Non-goals)："不实现外部 audit 系统、AuditPolicy 规则引擎、长期归档策略、retention cleanup、purge tombstone audit record、outbox cleanup、tool trace cleanup 或 purge destructive cleanup；这些统一归 Phase 15 Retention / Purge / Production Hardening。"
- Line 412 (Slice 1 Non-goals)："purge 相关 audit / outbox / tool trace 行为归 Phase 15。"
- Line 604 (Residual risks P2 deferred)："purge tombstone audit record、outbox cleanup、tool trace cleanup、projection cleanup 与 retention matrix 归 Phase 15；Phase 13 不实现 purge 行为。"

**结论：FIXED。** 三处覆盖完整。

---

### DS-F3 tool trace diagnostic whitelist

**Controller 要求：** 给出初版白名单或定义 Slice 2 whitelist discovery 步骤。

**Plan 修复验证：**

- Lines 322-330：完整列出 canonical facts whitelist（tool/wait chain、context/provider refs、terminal provider chain）和 diagnostic/preview whitelist（`ENGINE_EVENT_DIAGNOSTIC` + payload 条件、`PROVIDER_PROTOCOL_ERROR`、`USAGE_REPORTED` 仅 refs）。
- Line 333："Slice 2 的第一步必须做 typed whitelist discovery：逐项核对上述 event_type 是否已存在、payload view 是否有强类型字段...不得用无结构全量 diagnostic payload 兜底；一旦需要 Engine 或 ToolRuntime contract change...立即停止交 controller。"
- Line 463 (Slice 2 stop condition)："白名单 event_type 不存在、payload view 无强类型字段...停止交 controller。"

**结论：FIXED。** 白名单具体且有 discovery 验证步骤和 stop condition。

---

### DS-F4 audit marker table naming

**Controller 要求：** 改名为 `host_audit_sink_markers` 或 `host_audit_jsonl_idempotency`。

**Plan 修复验证：**

- Line 248："Optional `host_audit_sink_markers`"
- Line 250："这不是 audit event store，不作为 audit truth，也不作为 audit 查询真源；JSONL 行仍是 audit artifact，EventLog 仍是 Host truth。"

**结论：FIXED。** 命名和定位声明均已更新。

---

### DS-F5 RUN_LOST outbox mapping

**Controller 要求：** OutboxSink 对 RUN_LOST 返回 skipped + detail_code，不创建 public terminal item。

**Plan 修复验证：**

- Line 374："Phase 13 第一版 OutboxSink 对 `RUN_LOST` 返回 `ProjectionApplyResult(SKIPPED, detail_code=\"run_lost_not_public_terminal_item\")`，不创建 public terminal item。LOST notification / outbox item 化必须进入 recovery / public terminal contract gate 后再议。"
- Line 483 (Slice 3 Exact changes)："``RUN_LOST`` 返回 skipped + `detail_code=\"run_lost_not_public_terminal_item\"`，不创建 public terminal item。"

**结论：FIXED。** 行为明确，detail_code 具体，后续 gate 路径清晰。

---

### DS-F6 tool trace query helper pagination

**Controller 要求：** 声明返回排序和分页语义。

**Plan 修复验证：**

- Lines 355-358：四个 helper 全部签名统一为 `(str, int, int) -> ToolTraceQueryPage`，含 `after_event_sequence` 和 `limit` 参数。
- Line 359："所有 helper 均按 `event_sequence ASC` 返回 `event_sequence > after_event_sequence` 的匹配 row，`limit` 为正整数且有模块级上限。相同 `tool_call_id` / `provider_request_id` / `diagnostic_ref` 可返回多行，不得由 helper 隐式只取最新一条。"

**结论：FIXED。** 排序、分页、多行返回语义均明确。

---

### DS-F8 projection-lag anti-leak smoke

**Controller 要求：** Slice 4 增加 LAGGED → catch-up → second read 测试用例。

**Plan 修复验证：**

- Line 542 (Slice 4 Tests)："anti-leak lag case：第一次 drain/read 返回 `projection_status=LAGGED` 且无 terminal item；随后 OutboxSink catch-up 和 second read 返回该 terminal item，Service 以 `dedupe_key=terminal_event_id` upsert 后不重复展示。"

**结论：FIXED。** 测试场景覆盖 lag → catch-up → dedupe 全链路。

---

## 新引入问题检查

逐项检查 fix 是否引入新的矛盾或遗漏：

1. **Line 198 vs Line 380**：两处对 read catch-up 的描述一致——允许 projection-local writes，失败暴露为 LAGGED/FAILED。无矛盾。
2. **Line 194 vs Line 195**：`idempotency_key` 和 `dedupe_key` 的定义无重叠，消费方不同。无矛盾。
3. **Line 43 vs Line 604**：Non-goals 和 Residual risks 对 purge 归属 Phase 15 的表述一致。无矛盾。
4. **Line 322-330 vs Line 333 vs Line 463**：白名单内容、discovery 步骤、stop condition 三层一致。无矛盾。
5. **Line 374 vs Line 483**：RUN_LOST 的 detail_code 在 OutboxSink 通用描述和 Slice 3 exact changes 中一致。无矛盾。

**无新引入问题。**

---

## 总结

| Accepted Finding | 状态 |
|---|---|
| DS-F1 (blocking) | FIXED |
| MiMo-F1 | FIXED |
| MiMo-F2 | FIXED |
| DS-F2 | FIXED |
| DS-F3 | FIXED |
| DS-F4 | FIXED |
| DS-F5 | FIXED |
| DS-F6 | FIXED |
| DS-F8 | FIXED |

Plan 已通过 re-review，可供 implementation gate 使用。
