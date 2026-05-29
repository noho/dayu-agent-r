# Phase 13 Slice 3 Code Review

## Gate

Phase 13 Slice 3 code review。Review target：当前 workspace diff 中 Slice 3 相关改动。

## Verdict

**PASS** — 无 blocking findings。

## Evidence

- Reviewed files: `dayu/host/outbox.py` (527 lines), `dayu/host/durable/outbox.py` (877 lines), `dayu/host/durable/schema.py` diff, `tests/host/test_outbox_projection.py` (265 lines), `tests/host/test_outbox_durable.py` (319 lines), `tests/host/test_durable_schema.py` diff.
- Implementation artifact: `docs/reviews/phase13-slice3-implementation-codex-20260529.md`.
- Accepted plan: `docs/host/phase13-audit-tool-trace-outbox-plan.md` §Slice 3.
- Schema clarification: `docs/reviews/phase13-schema-version-controller-clarification-20260529.md`.
- Validation: `pytest tests/host/test_outbox_projection.py tests/host/test_outbox_durable.py tests/host/test_durable_schema.py -q` → 26 passed; `python -m pyright dayu/host tests/host` → 0 errors, 0 warnings, 0 informations.

## Review by Checkpoint

### 1. OutboxSink 只消费 terminal canonical facts；RUN_LOST skipped 且不创建 public terminal item

**PASS**

`OutboxTerminalProjectionConsumer.event_filter` (outbox.py:135-148) 过滤 `EventClass.CANONICAL_FACT` + `(RUN_SUCCEEDED, RUN_FAILED, RUN_CANCELLED, RUN_LOST)`。`RUN_LOST` 虽然在 filter 白名单内（为了让 EventLog 被扫描到），但在 `apply_event` (outbox.py:163-168) 中以 `ProjectionApplyStatus.SKIPPED` + `detail_code="run_lost_not_public_terminal_item"` 返回，不创建 Outbox item。`_TERMINAL_STATUS_BY_EVENT_TYPE` (outbox.py:79-83) 仅映射 SUCCEEDED/FAILED/CANCELLED 到 `HostTerminalStatus`，不包含 LOST。`build_outbox_terminal_item_row` (outbox.py:244-245) 对未在映射表中的 event_type 抛出 `HostDurableError`，构成双重防御。

测试 `test_run_lost_is_skipped_without_public_outbox_item` (test_outbox_projection.py:236-264) 验证 LOST 不产生 Outbox row，且被计为 skipped。

### 2. Outbox 表只是 projection/work queue，不写 EventLog、不更新 Run/Attempt、不记录 channel delivery success

**PASS**

- `insert_outbox_terminal_item_if_absent` (durable/outbox.py:194-256) 只写 `host_outbox_terminal_items`，不涉及 `event_log`/`host_runs`/`host_attempts`。
- `drain_outbox_terminal_items` (durable/outbox.py:323-419) 只更新 `host_outbox_terminal_items.item_state/drained_at/last_drain_request_id` 并写 `host_outbox_drain_idempotency`，不写 EventLog。
- 测试 `test_drain_is_idempotent_and_does_not_write_eventlog` (test_outbox_durable.py:231-283) 验证 drain 前后 EventLog row 数不变。
- docstring 明确声明 "不是 Host truth，不记录 channel 投递成功"。

### 3. Item identity/idempotency key 稳定，不使用 final answer 文本作为主键

**PASS**

`build_outbox_terminal_item_identity` (outbox.py:184-228) 使用 `terminal_event_id`、`run_id`、`result_ref`、`result_digest`、`terminal_summary_ref`、`terminal_summary_digest` 构造 identity JSON，通过 `sha256_digest_json` 派生 idempotency key。item_id = `"outbox-terminal-" + sha256_hex`。

明确排除 final answer 文本。`final_answer_json` 仅作为 item row 的展示字段，不参与 identity 派生。测试 `test_terminal_item_idempotency_key_is_stable` (test_outbox_projection.py:161-183) 验证相同输入产生相同 identity。

### 4. Read rows after cursor、seen terminal ids filtering、scanned watermark、has_more 语义正确

**PASS**

`read_outbox_terminal_items_after` (durable/outbox.py:259-320):

- 查询条件 `event_sequence > after_event_sequence` 严格大于 cursor。
- `scanned_watermark` 在遍历 candidate rows 时更新到每个 item 的 `event_sequence`，包括被 seen_ids 过滤掉的 rows（计划要求："即使 item 因 seen_terminal_event_ids 被过滤，也允许推进到该 scanned watermark"）。
- `scan_limit = limit + len(seen_ids)` 为过滤预留 buffer。
- `has_more` 通过 `_has_terminal_item_after` 检查 scanned_watermark 之后是否存在任何同 session item，语义为"scanned watermark 之后是否仍存在同 session terminal item"。
- `next_event_sequence = scanned_watermark`，下次读取以该 cursor 为 `after`。

测试 `test_read_after_filters_seen_ids_and_reports_watermark` (test_outbox_durable.py:177-228) 覆盖 seen ids 过滤、watermark 推进、has_more 变化、cursor 翻页。

### 5. Drain idempotency 正确

**PASS**

`drain_outbox_terminal_items` (durable/outbox.py:323-419):

- 按 `(session_id, drain_request_id)` 查幂等记录；已存在时比较 `request_digest`，不一致抛出 `HostIdempotencyConflictError`，一致返回同一 item id 集合。
- `request_digest` 由 `session_id`、`after_event_sequence`、`seen_terminal_event_ids`（去重排序）、`limit` 构造，覆盖完整 drain 语义输入。
- 首次 drain 先 read 选出 item，再 `UPDATE item_state='drained'` 并写 idempotency row，最后通过 `_page_for_drained_item_ids` 重建 page 返回，确保返回的 rows 反映最新 item state。
- 没有写 EventLog，没有更新 Run/Attempt。

测试 `test_drain_is_idempotent_and_does_not_write_eventlog` 验证 replay 返回同一 item，item state 变为 drained。测试 `test_drain_request_idempotency_conflict` 验证不同语义输入同 request id 抛出结构化冲突。

### 6. Schema bump 12 → 13 fresh-schema consistent

**PASS**

- `HOST_SCHEMA_VERSION` 从 12 改为 13。
- 新增 `TABLE_HOST_OUTBOX_TERMINAL_ITEMS`、`TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY` 及 3 个索引。
- 新增常量系列：`OUTBOX_PROJECTION_TABLES`、`OUTBOX_PROJECTION_DDL`、`OUTBOX_PROJECTION_INDEX_DDL`，全部接入 `HOST_DURABLE_TABLES`、`HOST_DURABLE_DDL`。
- DDL CHECK 约束覆盖：
  - `terminal_status IN ('succeeded', 'failed', 'cancelled')` — 排除 'lost'。
  - `item_state IN ('pending', 'drained')`。
  - ref/digest 成对出现（两个 CHECK）。
  - `item_state='pending'` 时 `drained_at` 和 `last_drain_request_id` 必须为 NULL；`item_state='drained'` 时两者必须 NOT NULL。
- 外键约束 `terminal_event_id` → `event_log(event_id)`，`event_sequence` → `event_log(event_sequence)`。
- 索引：`(session_id, event_sequence)`、`(item_state, event_sequence)`、`(run_id)`，与计划一致。
- `_HOST_OUTBOX_DRAIN_IDEMPOTENCY_DDL` 的 PRIMARY KEY 为 `(session_id, drain_request_id)`，与计划一致。

测试覆盖：
- `test_host_schema_version_is_phase13_outbox_version` 验证版本为 13。
- `test_outbox_tables_and_indexes_are_created` 验证表存在、主键正确、全部索引创建。
- `test_projection_schema_constraints_reject_invalid_rows` 验证 terminal_status='lost' 被拒绝、item_state='pending' 带 drained_at 被拒绝。
- `test_schema_does_not_create_unowned_future_purge_tables` 验证不预创建 purge 表；"outbox" fragment 从 forbidden 列表移除（outbox 表已存在）。

### 7. 未接 public Host handle/API，未改 open_host/read_api/watch_session_events

**PASS**

`dayu/host/outbox.py` 和 `dayu/host/durable/outbox.py` 均未 import `open_host`、`read_api`、`watch_session_events` 或 `Host` Protocol。Public API wiring 按计划归 Slice 4。

### 8. 中文 docstring、严格类型、无 object/Any/无类型签名、无 getattr/hasattr 逃避类型、无魔法字符串扩散

**PASS**

- 所有模块、类、公开函数均有完整中文 docstring。
- 类型签名严格：无 `object`、`Any`、无类型参数、无裸 dict/list/set public signature。仅有一处 `cast(JsonValue, ...)` 在 `_batch_item_ids_from_json` 解析外部 JSON，属于合理的边界类型强制。
- 无 `getattr`/`hasattr` 使用。
- 关键常量均定义为模块级私有常量（`_DETAIL_CODE_RUN_LOST_SKIPPED`、`_ITEM_STATE_PENDING`、`_DIGEST_FIELD_*` 等），未扩散魔法字符串。

## Advisory Observations (非 blocking)

### O1-已记录-低-`catch_up_outbox_terminal_projection` 函数实现冗余

**Evidence**

`catch_up_outbox_terminal_projection` (outbox.py:293-346) 通过 `while True` 循环调用 `ProjectionRunner.run_once`，手动聚合 `events_scanned`/`events_applied`/`duplicates`/`skipped`。该模式与 `ProjectionRunner` 自身的批量循环机制功能重叠。

**Impact**

低。代码正确，仅维护负担略高。若未来 `ProjectionRunner.run_once` 的批量语义变化（如新增 `run_to_completion`），此处需同步修改。

**Recommendation**

可暂不修改。待 Slice 4 接线时考虑是否需要 `ProjectionRunner` 暴露 `run_to_completion` 方法，以消除调用方的 while 循环。

### O2-已记录-低-`scan_limit = limit + len(seen_ids)` 在 seen_ids 跨页累积时浪费查询

**Evidence**

`read_outbox_terminal_items_after` (durable/outbox.py:288) 使用 `scan_limit = limit + len(seen_ids)` 为过滤预留 buffer。当 seen_ids 累积到 OUTBOX_TERMINAL_SEEN_IDS_MAX_COUNT (1000) 且 limit=1 时，单次查询可能扫描 1001 行仅返回 1 行。

**Impact**

低。当前 seen_ids 上限为 1000，单次扫描 1001 行仍在可接受范围。`has_more` 语义正确，不影响调用方数据完整性。

**Recommendation**

可暂不修改。若后续观察到性能退化，可考虑在 seen_ids 超过某阈值时分批读取或使用 `NOT IN` 子句下推到 SQLite。

## Plan Compliance Summary

| Plan Requirement | Status |
|---|---|
| OutboxSink 只消费 terminal canonical facts | PASS |
| RUN_LOST skipped 不创建 public item | PASS |
| Outbox 表不写 EventLog/不更新 Run/Attempt | PASS |
| drain 不记录 channel delivery success | PASS |
| item identity 稳定，不用 final answer 文本做主键 | PASS |
| dedupe_key = terminal_event_id | PASS |
| read after cursor + seen ids + scanned watermark + has_more | PASS |
| drain idempotency (session_id, drain_request_id) | PASS |
| request digest conflict 抛结构化错误 | PASS |
| item_state 仅 UPDATE outbox projection rows | PASS |
| schema fresh bump 12→13 | PASS |
| table/index/constraint 测试覆盖 | PASS |
| 未接 public Host handle/API | PASS |
| 未改 open_host/read_api/watch_session_events | PASS |
| 中文 docstring | PASS |
| 严格类型，无 object/Any/无类型签名 | PASS |
| 无 getattr/hasattr | PASS |
| 无魔法字符串扩散 | PASS |

## Residual Risks

- Public read/drain status、projection catch-up status、Host handle closed/session gone 错误语义尚未接线 — owner: Slice 4。
- Outbox item cleanup、retention、purge tombstone 行为不在本 slice — owner: Phase 15。
- Drain idempotency replay 依赖 item row 持久存在；若未来引入 outbox cleanup，需先定义 idempotency row 与 item row 的保留关系 — owner: 后续 retention 设计。
