# Code Review

## Scope

- Mode: current changes (aggregate fix re-review)
- Branch: `feat/host-phase8-projection-core-event-stream`
- Base: `main`
- Output file: `docs/reviews/host-phase8-aggregate-re-review-mimo-20260516.md`
- Included scope: Phase 8 aggregate fix workspace changes — `dayu/host/projection.py`, `dayu/host/durable/schema.py`, `tests/host/test_projection_runner.py`, `tests/host/test_durable_schema.py`
- Excluded scope: Engine、runtime、service、ui、fins；command path、admission、waiting、dispatch、recovery；public read API shape；README / control doc。
- Parallel review coverage: 无（单 reviewer 直接走读）。

## Verdict

**PASS**

P8-AGG-F1 和 P8-AGG-F2 均已按 controller adjudication 修复。P8-AGG-F3 维持 deferred。验证通过，未引入新问题或 scope creep。

## Findings

未发现实质性问题。

### P8-AGG-F1 修复验证 — PASS

- **修复目标**: `ProjectionRunner` 对 payload 解析型 `HostDurableError` 应记录 projection failure row，不应透传导致无 failure row。
- **实现方式**: 新增 `_ProjectionEventViewFailed` 内部控制流异常，`_process_next_event()` 中 `projection_event_view_from_row(row)` 抛出 `HostDurableError` 时捕获并包装为 `_ProjectionEventViewFailed(row, exc)`。`run_once()` 中新增对应 `except _ProjectionEventViewFailed` 分支，复用 `_record_failure()` 写入 `host_projection_failures`。
- **直接证据**:
  - `dayu/host/projection.py:307-325`: `_ProjectionEventViewFailed` 定义，持有 `event_row: EventLogRow` 和 `original_exception: HostDurableError`。
  - `dayu/host/projection.py:511-515`: `_process_next_event()` 中 `try: event = projection_event_view_from_row(row) / except HostDurableError as exc: raise _ProjectionEventViewFailed(row, exc) from exc`。
  - `dayu/host/projection.py:404-412`: `run_once()` 中 `except _ProjectionEventViewFailed` 分支调用 `_record_failure(consumer_id, event_sequence=..., event_id=..., exception=...)`。
  - `dayu/host/projection.py:540-572`: `_record_failure()` 签名改为 keyword-only `event_sequence` / `event_id`，两个 call site 均使用 keyword 传参。
- **不变量检查**:
  - Checkpoint 不推进: `_ProjectionEventViewFailed` 在 `_process_next_event` 的 `projection_event_view_from_row` 阶段抛出，此时尚未调用 `advance_projection_checkpoint`，因此 checkpoint 保持不变。✅
  - Failure row 写入: `_record_failure` 调用 `write_projection_failure` 写入 durable failure row。✅
  - Consumer 未被调用: view 构造失败发生在 consumer `apply_event` 之前。✅
  - Caller 不收到透传 `HostDurableError`: `run_once()` 捕获 `_ProjectionEventViewFailed`，不 re-raise。✅
- **测试覆盖**:
  - `test_payload_parsing_failure_records_failure_without_advancing_checkpoint` 覆盖两种 payload 失败场景:
    - `payload_json = "[]"` (JSON array, not mapping) → `"EventLog payload_json must be a JSON mapping"`
    - `payload_json = "{"` (invalid JSON) → `"EventLog payload_json is invalid"`
  - 断言完整: `result.failures == 1`、`finished_cursor == 0`、`events_scanned == 0`、`consumer.applied_events == []`、`checkpoint.checkpoint_event_sequence == 0`、failure row 的 `failed_event_sequence` / `failed_event_id` / `last_error_code` / `last_error_message` 均指向正确 EventLog row。✅
- **结论**: 修复正确，测试充分。

### P8-AGG-F2 修复验证 — PASS

- **修复目标**: `HOST_SCHEMA_VERSION` 最终值应与 plan 对齐为 `5`。
- **实现方式**: `dayu/host/durable/schema.py:24` 从 `6` 改为 `5`。
- **直接证据**:
  - `dayu/host/durable/schema.py:24`: `HOST_SCHEMA_VERSION = 5`。
  - `tests/host/test_durable_schema.py:151`: `assert _pragma_int(connection, "PRAGMA user_version") == 5`。
  - `tests/host/test_durable_schema.py:152`: `assert HOST_SCHEMA_VERSION == 5`。
- **Bootstrap 不变量**: `test_fresh_db_creates_foundation_and_phase8_tables` 继续断言 `HOST_DURABLE_TABLES`、`PHASE3_STATE_TABLES`、`PROJECTION_TABLES` 均被创建。Phase 8 projection / read model tables 在 `PROJECTION_TABLES` 中，fresh bootstrap 仍创建所有 Phase 8 表。✅
- **模块 docstring 同步**: `schema.py:2-6` 已更新为 "Phase 2 foundation tables、Phase 3 Session / Run / Attempt durable state tables，以及 Phase 8 projection / read model tables"。✅
- **结论**: 修复正确，Bootstrap 不变量保持。

### P8-AGG-F3 状态确认 — 维持 deferred

- `get_run` 未消费 RunResult projection，符合 controller adjudication 裁决。
- 本次 fix 未修改 `dayu/host/read_api.py`、`dayu/host/api.py` 或任何 public read API shape。✅

### Scope creep 检查 — 无

- `git diff --stat HEAD` 仅包含 4 个文件: `dayu/host/durable/schema.py`、`dayu/host/projection.py`、`tests/host/test_durable_schema.py`、`tests/host/test_projection_runner.py`。✅
- 未触及 Engine、runtime、service、ui、fins、command path、admission、waiting、dispatch、recovery、public read API。✅
- `_record_failure` 签名变更（positional → keyword-only）对已有 `_ProjectionApplyFailed` call site 也做了同步更新，无遗漏。✅

## Open Questions

- 无。

## Residual Risk

1. **`_record_failure` 签名变更为 keyword-only**: 两个 call site 均已同步更新，75 tests 全部通过。无遗漏风险。
2. **Controller adjudication 中标注的 deferred items 不变**: automatic after-commit projection catch-up (Phase 9)、heavy sink / batch-transaction runner (Phase 13/15)、per-session repair filter (Phase 15)、RunResult summary refs 接入 public `RunSnapshot` (Phase 9/15)。

## Validation Summary

| Check | Result |
|-------|--------|
| `pytest ... -q` | 75 passed in 0.96s |
| `pyright dayu/host tests/host` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过，无输出 |
