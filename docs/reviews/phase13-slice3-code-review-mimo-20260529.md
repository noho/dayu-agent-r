# Phase 13 Slice 3 Code Review — AgentMiMo

## Gate

Phase 13 Slice 3 `OutboxSink Durable Projection` code review。

## Review Target

- 当前分支 `feat/phase-13-audit-trace-outbox` 相对 HEAD 的未提交 Slice 3 diff。
- Implementation artifact：`docs/reviews/phase13-slice3-implementation-codex-20260529.md`。
- Accepted plan：`docs/host/phase13-audit-tool-trace-outbox-plan.md`。
- Schema clarification：`docs/reviews/phase13-schema-version-controller-clarification-20260529.md`。

## Review Scope

Allowed files：

- `dayu/host/outbox.py` (new)
- `dayu/host/durable/outbox.py` (new)
- `dayu/host/durable/schema.py` (modified)
- `tests/host/test_outbox_projection.py` (new)
- `tests/host/test_outbox_durable.py` (new)
- `tests/host/test_durable_schema.py` (modified)
- `docs/reviews/phase13-slice3-implementation-codex-20260529.md` (new)
- `docs/host/implementation-control.md` (modified, controller gate status only)

## Validation Re-run

- `pytest tests/host/test_outbox_projection.py tests/host/test_outbox_durable.py tests/host/test_durable_schema.py -q`：**26 passed**。
- `python -m pyright dayu/host/outbox.py dayu/host/durable/outbox.py dayu/host/durable/schema.py tests/host/test_outbox_projection.py tests/host/test_outbox_durable.py tests/host/test_durable_schema.py`：**0 errors, 0 warnings, 0 informations**。

---

## Findings

### 1-NONBLOCKING-[LOW]-`event_sequence` 外键约束冗余且隐含脆弱假设

**Evidence**：`dayu/host/durable/schema.py` `_HOST_OUTBOX_TERMINAL_ITEMS_DDL`：

```sql
FOREIGN KEY(terminal_event_id) REFERENCES event_log(event_id),
FOREIGN KEY(event_sequence) REFERENCES event_log(event_sequence),
```

`terminal_event_id` 已有 `UNIQUE` 约束和指向 `event_log(event_id)` 的外键。`event_sequence` 也已 `UNIQUE`。两条外键指向同一行，且 `event_sequence` 在 `event_log` 中并非真正不可变主键（`event_id` 才是）。

**Impact**：当前 EventLog append-only 语义下不会触发实际问题。但 `event_sequence` 外键在逻辑上冗余——一旦 `terminal_event_id` 外键成立，`event_sequence` 必然存在于同一行。若未来 EventLog 引入 sequence reuse 或 vacuum，该外键会产生非预期冲突。这不是 blocking issue，但属于 schema 设计瑕疵。

**Required change**：建议移除 `FOREIGN KEY(event_sequence) REFERENCES event_log(event_sequence)`，保留 `FOREIGN KEY(terminal_event_id) REFERENCES event_log(event_id)`。当前可接受为 known design debt，不阻塞本 slice。

---

### 2-NONBLOCKING-[LOW]-缺少边界常量显式测试

**Evidence**：`dayu/host/durable/outbox.py` 定义了两个模块级边界常量：

- `OUTBOX_TERMINAL_READ_MAX_LIMIT = 500`
- `OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT = 1000`

`_validate_page_input` 在 `limit > OUTBOX_TERMINAL_READ_MAX_LIMIT` 或 `len(seen_terminal_event_ids) > OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT` 时抛出 `HostDurableError`。但 `test_outbox_durable.py` 中没有测试边界拒绝行为。

**Impact**：边界校验逻辑正确且在 `_validate_page_input` 中集中实现，不会产生 silent failure。缺少测试意味着未来重构时边界保护可能被意外移除。

**Required change**：建议在 `test_outbox_durable.py` 中补充 `limit` 超限和 `seen_terminal_event_ids` 超限的拒绝测试。当前不阻塞。

---

### 3-NONBLOCKING-[INFO]-`_TERMINAL_STATUS_BY_EVENT_TYPE` 不含 `RUN_LOST` 是正确防护

**Evidence**：`dayu/host/outbox.py:79-83`：

```python
_TERMINAL_STATUS_BY_EVENT_TYPE: Mapping[str, HostTerminalStatus] = {
    _EVENT_TYPE_RUN_SUCCEEDED: HostTerminalStatus.SUCCEEDED,
    _EVENT_TYPE_RUN_FAILED: HostTerminalStatus.FAILED,
    _EVENT_TYPE_RUN_CANCELLED: HostTerminalStatus.CANCELLED,
}
```

`RUN_LOST` 故意不在此映射中。`apply_event` 在调用 `build_outbox_terminal_item_row` 之前先检查 `RUN_LOST` 并返回 `SKIPPED`。若未来新增 terminal event type 但忘记更新此映射，`build_outbox_terminal_item_row` 会抛出 `HostDurableError`，迫使开发者显式处理——这是正确的 fail-fast 行为。

**Impact**：无。这是 positive design observation。

---

## Correctness Checklist

### OutboxSink 只消费 terminal canonical facts，RUN_LOST skipped 且不创建 public terminal item

- `OutboxTerminalProjectionConsumer.event_filter` 返回 `ProjectionEventFilter` 含 `EventClass.CANONICAL_FACT` 与 `_TERMINAL_EVENT_TYPES`（`RUN_SUCCEEDED`, `RUN_FAILED`, `RUN_CANCELLED`, `RUN_LOST`）。**PASS**。
- `apply_event` 对 `RUN_LOST` 返回 `ProjectionApplyResult(SKIPPED, detail_code="run_lost_not_public_terminal_item")`，不调用 `build_outbox_terminal_item_row`，不写任何表。**PASS**。
- 测试 `test_run_lost_is_skipped_without_public_outbox_item` 验证 `row is None`、`events_skipped == 1`、`outbox table count == 0`。**PASS**。

### Outbox 表只是 projection/work queue

- `insert_outbox_terminal_item_if_absent` 只写 `TABLE_HOST_OUTBOX_TERMINAL_ITEMS`。**PASS**。
- `drain_outbox_terminal_items` 只更新 `TABLE_HOST_OUTBOX_TERMINAL_ITEMS` 的 `item_state`/`drained_at`/`last_drain_request_id`/`updated_at`，写 `TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY`。不写 EventLog，不更新 Run/Attempt，不记录 channel delivery success。**PASS**。
- 测试 `test_drain_is_idempotent_and_does_not_write_eventlog` 验证 drain 前后 `_event_log_count` 不变。**PASS**。

### Item identity/idempotency key 稳定，不使用 final answer 文本作为主键

- `build_outbox_terminal_item_identity` 输入为 `terminal_event_id`, `run_id`, `result_ref`, `result_digest`, `terminal_summary_ref`, `terminal_summary_digest`。不包含 `final_answer`。**PASS**。
- `dedupe_key = terminal_event_id`，与 live `HostEvent.dedupe_key` 对齐。**PASS**。
- `_validate_item_row` 强制 `dedupe_key == terminal_event_id`。**PASS**。
- 测试 `test_terminal_item_idempotency_key_is_stable` 验证相同输入返回相同 identity。**PASS**。

### Read rows after cursor、seen terminal ids filtering、scanned watermark、has_more 语义正确

- `read_outbox_terminal_items_after` 查询 `WHERE session_id = ? AND event_sequence > ? ORDER BY event_sequence ASC LIMIT ?`。**PASS**。
- `scan_limit = limit + len(seen_ids)` 确保 seen 过滤后仍可能返回足够 rows。**PASS**。
- `scanned_watermark` 在每个 candidate row 上更新，即使 row 因 seen 被过滤。**PASS**。
- `next_event_sequence == scanned_watermark`。**PASS**。
- `has_more = _has_terminal_item_after(transaction, session_id, event_sequence=scanned_watermark)`。**PASS**。
- 测试 `test_read_after_filters_seen_ids_and_reports_watermark` 验证 first page（limit=1, seen=second）返回 first、second page（after=first, seen=second）返回 third、has_more 语义。**PASS**。

### Drain idempotency by (session_id, drain_request_id)、request digest conflict、item_state update 正确

- `drain_outbox_terminal_items` 计算 `request_digest` 从 `(session_id, after_event_sequence, seen_terminal_event_ids, limit)`。**PASS**。
- 首次调用写入 drain idempotency row 并更新 item `item_state` 为 `drained`。**PASS**。
- 相同 `drain_request_id` 相同 digest 重放返回同一 item id 集合。**PASS**。
- 相同 `drain_request_id` 不同 digest 抛 `HostIdempotencyConflictError`。**PASS**。
- 测试 `test_drain_is_idempotent_and_does_not_write_eventlog` 和 `test_drain_request_idempotency_conflict` 覆盖。**PASS**。

### Schema bump 12 -> 13 fresh-schema consistent

- `HOST_SCHEMA_VERSION` 从 12 改为 13。**PASS**。
- 新增 `TABLE_HOST_OUTBOX_TERMINAL_ITEMS`、`TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY` 常量。**PASS**。
- DDL 定义正确，含 CHECK 约束（`terminal_status`、`item_state`、ref pair、drain state）。**PASS**。
- 三个索引 `SESSION_SEQUENCE`、`STATE_SEQUENCE`、`RUN` 正确定义。**PASS**。
- `OUTBOX_PROJECTION_TABLES`、`OUTBOX_PROJECTION_DDL`、`OUTBOX_PROJECTION_INDEX_DDL` 正确注册。**PASS**。
- `HOST_DURABLE_TABLES`、`HOST_DURABLE_DDL` 正确包含 outbox 组。**PASS**。
- `test_host_schema_version_is_phase13_outbox_version` 验证 `HOST_SCHEMA_VERSION == 13`。**PASS**。
- `test_fresh_db_creates_foundation_phase8_and_memory_tables` 验证 `OUTBOX_PROJECTION_TABLES` 子集。**PASS**。
- `test_outbox_tables_and_indexes_are_created` 验证表存在、主键、索引。**PASS**。
- `test_projection_schema_constraints_reject_invalid_rows` 验证 invalid terminal status 和 invalid drain state 被拒绝。**PASS**。
- `test_schema_does_not_create_unowned_future_purge_tables` 从 `("outbox", "purge")` 改为 `("purge",)`，正确反映 outbox 已归属。**PASS**。

### 未接 public Host handle/API，未改 open_host/read_api/watch_session_events

- Diff 中无 `dayu/host/api.py`、`dayu/host/__init__.py`、`dayu/host/open_host.py`、`dayu/host/read_api.py` 修改。**PASS**。
- `outbox.py` 和 `durable/outbox.py` 不 import 上层模块。**PASS**。
- `implementation-control.md` 只更新 gate status 和 Slice 3 tracking。**PASS**。

### 中文 docstring、严格类型、无 object/Any/无类型签名、无 getattr/hasattr、无魔法字符串

- 所有模块、类、函数、参数均提供中文 docstring。**PASS**。
- 所有签名严格类型化，无 `object`、`Any`。**PASS**。
- `cast` 使用场景：`durable/outbox.py:848` `cast(JsonValue, json.loads(value))`，`JsonValue` 是项目 typed alias，不是 `Any`。**PASS**。
- 无 `getattr`/`hasattr` 使用。**PASS**。
- 魔法字符串全部提取为模块级常量（`_EVENT_TYPE_*`、`_PAYLOAD_FIELD_*`、`_IDENTITY_FIELD_*`、`_ITEM_STATE_*`、`_TERMINAL_STATUS_*`、`_DIGEST_FIELD_*`、`_JSON_BATCH_ITEM_IDS`）。**PASS**。

---

## Implementation Report 交叉检查

Implementation report 声明：

- "RUN_LOST 返回 skipped，detail code 为 `run_lost_not_public_terminal_item`，不创建 public terminal item" — 代码确认。**PASS**。
- "item identity / idempotency key 使用 terminal event id、run id、result refs 与 terminal summary refs 稳定派生，不使用 final answer 文本" — 代码确认。**PASS**。
- "durable helper 支持按 cursor 读取、过滤 seen terminal ids、返回 scanned watermark 与 has_more" — 代码确认。**PASS**。
- "drain 按 `(session_id, drain_request_id)` 幂等，request digest 冲突抛结构化 idempotency conflict" — 代码确认。**PASS**。
- "仅更新 Outbox item state，不写 EventLog，不表示 channel delivery success" — 代码确认。**PASS**。
- "未修改 public API wiring、`open_host`、`read_api`、`watch_session_events`" — diff 确认。**PASS**。
- "validation: focused pytest 26 passed、pyright 0 errors、git diff --check passed" — re-run 确认。**PASS**。

---

## Plan Conformance

| Plan Requirement | Status |
|---|---|
| schema 新增 `host_outbox_terminal_items`、`host_outbox_drain_idempotency` 与 indexes | PASS |
| 新增 `OutboxTerminalProjectionConsumer`，consumer id `host.outbox-terminal` | PASS |
| 从 terminal canonical facts upsert item；重复 replay 返回 duplicate | PASS |
| `RUN_LOST` 返回 skipped + `detail_code` | PASS |
| 实现 read rows after cursor + seen ids filtering + scanned watermark | PASS |
| 实现 drain idempotency、item_state update | PASS |
| drain 不写 EventLog，不记录 channel success | PASS |
| 不接 public Host handle | PASS |
| 不改 `open_host`/`read_api`/`watch_session_events` | PASS |
| 中文 docstring、严格类型、无 object/Any | PASS |

---

## Verdict

**PASS**，无 blocking findings。

两个 NONBLOCKING findings（event_sequence 外键冗余、边界常量测试缺失）不阻塞 Slice 3 进入 accepted commit。建议在后续 slice 或 retention phase 中一并处理。
