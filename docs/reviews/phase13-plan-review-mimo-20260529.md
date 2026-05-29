# Phase 13 Plan Review

## Review Target

`docs/host/phase13-audit-tool-trace-outbox-plan.md`

## Reviewer

MiMo (independent plan reviewer)

## Date

2026-05-29

## Verdict

**PASS — 有 2 个 recommended findings，无 blocking findings。**

Plan 可供 implementation agent 直接执行。核心设计目标全部满足，API shape 完整，slices 边界清晰，测试覆盖要求明确。

---

## Findings

### F1-未修复-RECOMMENDED-OutboxTerminalItem.dedupe_key 与 HostEvent.dedupe_key 对齐方式未固定

**Evidence：**

- `dayu/host/api.py:431,496,519,546`：现有 `HostEvent.dedupe_key` 始终等于 `row.event_id`。
- Plan §Idempotency / Dedupe（line 365）："dedupe_key = terminal_event_id 或稳定 run_id + terminal_event_id；必须与 live HostEvent.dedupe_key 可对齐。"

**Impact：**

"或"的表述给 implementation agent 留出二义性空间。若实现选择 `run_id + terminal_event_id`，则与现有 `HostEvent.dedupe_key = event_id` 不一致，Service 用 `dedupe_key` upsert 时需额外对齐逻辑。

**Required change：**

将 plan 中 `dedupe_key` 定义固定为 `dedupe_key = terminal_event_id`，与 `HostEvent.dedupe_key` 保持同源。若未来需要复合 key，应同步修改 `HostEvent.dedupe_key` 派生逻辑，不在 Phase 13 分叉。

---

### F2-未修复-RECOMMENDED-OutboxTerminalItem 同时携带 idempotency_key 与 dedupe_key，用途边界未定义

**Evidence：**

- Plan §API Shape（line 129-130）：`OutboxTerminalItem` 同时有 `idempotency_key: str` 和 `dedupe_key: str`。
- Plan §Idempotency / Dedupe（line 195）："idempotency_key 与 dedupe_key 可同源，但 public item 必须同时携带 terminal_event_id、event_sequence、run_id，供 UI / Service upsert。"
- `host_outbox_terminal_items` 表（line 234）：`idempotency_key TEXT NOT NULL UNIQUE`，`dedupe_key TEXT NOT NULL`。

**Impact：**

未明确两个 key 的消费方和语义差异。若同源则冗余字段增加 API surface；若不同源则需要明确各自用途，否则 implementation agent 可能任意派生。

**Required change：**

在 plan 中明确：
- `idempotency_key`：OutboxSink upsert 和 `host_outbox_drain_idempotency` 表使用的稳定幂等键，由 `terminal_event_id + run_id + result_digest` 派生。
- `dedupe_key`：UI / Service 与 `HostEvent.dedupe_key` 对齐的去重键，固定等于 `terminal_event_id`。
- 两者同源时可相等，但 plan 应说明这是设计选择而非巧合。

---

## 审查逐项报告

### 1. Plan 是否 handoff-ready / code-generation-ready

**PASS。** Plan 包含完整的 API shape dataclass 定义、schema DDL 字段、slice 边界、allowed files、exact changes、tests 和 stop conditions。Implementation agent 无需重新设计即可执行。

### 2. Phase 13 design goal 满足情况

**PASS。** Plan 反复确认 Audit / Tool Trace / Outbox 只是 projection / sink，不进入 command path，不成为 recovery、resume、memory 或 Run 状态真源。每个 slice 都有明确 stop condition 防止越界。

### 3. Outbox read / drain API 是唯一 additive public extension

**PASS。** Plan §Public Contract Changes（line 98-100）明确：Phase 13 唯一 additive public extension 是 Outbox read / drain API，不得新增 `OpenHostOptions` public 字段。Tool trace 查询保持 internal。`watch_session_events` signature 和 live-only 语义不变。

### 4. Terminal item identity、cursor/watermark、seen terminal ids、dedupe、防漏窗口和 live watch overlap

**PASS。** Plan 覆盖完整：
- `item_id` 由 `terminal_event_id + run_id + result_digest` 派生（line 193）。
- `after.event_sequence` 严格 `>` 语义（line 185）。
- `seen_terminal_event_ids` overlap 去重（line 186）。
- `scanned_watermark` 即使 item 被过滤也允许推进（line 187）。
- `projection_checkpoint` 与 `next_cursor` 分离（line 188-189）。
- live-first 和 drain-first + second-read 两种 attach 形态均有测试要求（line 212-215）。
- 明确禁止声称单次 drain-first read + later live watch 天然无漏（line 215）。

### 5. LogAuditSink 路径注入

**PASS。** Plan 选择"不新增 OpenHostOptions 字段、sink constructor typed path injection + artifact_root 默认派生路径"。Design.md §15 要求"audit log file 路径由 Host composition root 的 typed options 显式传入，可有默认值"。Plan 的 `LogAuditSinkOptions` 是 typed options，通过 `open_host` 从 `artifact_root` 派生默认路径后注入 sink constructor，满足 design.md 的 typed options 显式传入要求，同时避免扩大 public construction surface。这是合理的 composition root 注入模式。

### 6. Tool Trace hot/cold 字段、provider/tool diagnostic refs 查询与 JSONL crash residual

**PASS。** Plan 覆盖完整：
- Hot JSON fields 列表包含 source identity、scope、tool identity、semantic refs、result refs、governance、provider diagnostics、cold link（line 325-334）。
- Cold JSONL 为 hot fields 的 superset，加长参数/结果摘要、截断元数据、wait/cancel/timeout 细节（line 338-340）。
- Query helpers 按 run_id、tool_call_id、provider_request_id、diagnostic_ref 查询（line 345-348）。
- JSONL crash residual 明确：物理 JSONL 可能出现重复 `event_id` 行，analyze helper 必须按 `event_id` 逻辑去重（line 268-270）。

### 7. Storage/schema fresh bump、projection checkpoint、failure/lag semantics

**PASS。**
- Schema bump 从 10 到 11（line 219），有版本不一致时停止交 controller 的 stop condition。
- 复用 `host_projection_checkpoints` / `host_projection_failures`（line 258-259）。
- Checkpoint 只在 projection write 成功后推进，failure 不推进（line 264-265）。
- `projection_status` 三态 CAUGHT_UP / LAGGED / FAILED 完整表达 lag 和 failure 语义（line 205-206）。
- Service 不应把空结果解释为"无 terminal"，除非 `CAUGHT_UP` 且 `has_more=False`（line 206）。

### 8. Slices 粒度和 file ownership

**PASS。** Plan 4 个 slices（vs implementation-control.md 建议的 3 个）将 Outbox durable projection 与 public API 接入分离，粒度更细但边界更清晰。每个 slice 有精确的 allowed files 列表和 stop condition。没有 future-slice leakage。

### 9. Tests / validation / README 同步

**PASS。** 每个 slice 有明确的 test requirements。最终 aggregate 验证命令覆盖所有新测试文件和相关已有测试（line 538-558）。README 触发规则按 implementation-control.md 要求明确（line 561-564）。

### 10. AGENTS.md 合规

**PASS。** 无 `object` / `Any` / 无类型签名、无 compat wrapper、无反向依赖、无过度设计。Consumer id 常量（如 `host.audit-log-jsonl`）为 projection identity 标识符，非业务魔法字符串。`item_id` 前缀 `"outbox-terminal-"` 为结构化命名，可接受。

---

## Residual Risk 确认

Plan 的 residual risk 分类合理：

- P0 blocking：无。确认。
- P1 JSONL 与 SQLite checkpoint 无跨介质 exactly-once：已接受，有明确缓解策略（event_id 去重）。
- P1 Outbox drain 不是 channel delivery success：已接受，Service ownership 明确。
- P2 deferred items 归 Phase 15 / 后续 hardening：合理。

---

## 总结

Plan 是 implementation-ready 的 handoff 文档。所有 design goal 和 control constraints 均已满足。两个 recommended findings 关于 `dedupe_key` 对齐和 `idempotency_key` / `dedupe_key` 用途边界，不阻塞 implementation 但建议在 slice 3 实施前澄清，避免实现分叉。
