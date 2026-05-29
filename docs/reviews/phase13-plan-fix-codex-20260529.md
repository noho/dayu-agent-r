# Phase 13 Plan Fix Codex

## Gate

Phase 13 plan fix.

## Source Review Artifacts

- `docs/reviews/phase13-plan-review-mimo-20260529.md`
- `docs/reviews/phase13-plan-review-ds-20260529.md`
- `docs/reviews/phase13-plan-review-controller-adjudication-20260529.md`

## Changed File

- `docs/host/phase13-audit-tool-trace-outbox-plan.md`

## Fixed Accepted Findings

- DS-F1：澄清 `read_outbox_terminal_items` side-effect boundary。计划现明确 read 不写 EventLog、不更新 Run / Attempt、不改变 Outbox item `item_state`，但允许返回前执行 projection-local catch-up；catch-up 失败通过 `projection_status=LAGGED` 或 `FAILED` 暴露。
- MiMo-F1：固定 `OutboxTerminalItem.dedupe_key = terminal_event_id`，不再允许 `run_id + terminal_event_id` 替代。
- MiMo-F2：明确 `idempotency_key` 用于 OutboxSink durable upsert / drain idempotency，`dedupe_key` 用于 UI / Service 与 `HostEvent.dedupe_key` 对齐去重。
- DS-F2：明确 purge tombstone audit record、outbox cleanup、tool trace cleanup、projection cleanup 与 retention matrix 不进入 Phase 13，归 Phase 15。
- DS-F3：补充 Tool Trace 初版 typed EventLog whitelist，并要求 Slice 2 先做 whitelist discovery；若需要 Engine 或 ToolRuntime contract change，停止交 controller。
- DS-F4：将 optional audit marker table 从 `host_audit_jsonl_events` 改为 `host_audit_sink_markers`，并明确它不是 audit event store。
- DS-F5：明确 Phase 13 OutboxSink 对 `RUN_LOST` 返回 skipped + `detail_code="run_lost_not_public_terminal_item"`，不创建 public terminal item。
- DS-F6：明确 tool trace query helpers 返回 `ToolTraceQueryPage`，按 `event_sequence ASC` 与 `after_event_sequence` / `limit` 分页，匹配同一 id 可返回多行。
- DS-F8：Slice 4 tests 增加 projection lag anti-leak case：首次 read/drain 返回 `projection_status=LAGGED`，second read 在 catch-up 后返回 terminal item 且不重复展示。

## Rejected / No-change Findings

- DS-F7：controller 裁决为无需 plan change；沿用现有 `_PublicHostHandle` closed-handle guard 模式即可。
- DS-F9：作为 AGENTS 合规 pass evidence，无需 plan change。

## Validation

```bash
git diff --check -- docs/host/phase13-audit-tool-trace-outbox-plan.md
```

Result: passed.

## Residual Risks / Blocking Open Questions

None.
