# WU-CLI-ACTIVITY-01 follow-up Slice 3 implementation

## 元数据

- Work unit：`WU-CLI-ACTIVITY-01 follow-up`
- Slice：3，EventLog filter-aware read 与 ProjectionRunner catch-up semantics
- 日期：2026-06-18
- 实施者：Codex
- Accepted plan：`docs/host/host-issues/wu-cli-activity-01-followup-delta-eventlog-projection-catchup-plan.md`
- Artifact：`docs/reviews/wu-cli-activity-01-followup-slice-3-implementation-codex-20260618.md`

## Scope

本 slice 只实现 EventLog filter-aware read primitive 与 ProjectionRunner 对 filtered page 的 catch-up 语义。未修改 Host / Engine public API 或 durable schema，未实现 Slice 4 的 `memory_repair`、`open_host`、`dispatch` 或 inline repair 改动，未移除 `MemoryProjectionCatchupBudget`。

## Changed Files

- `dayu/host/durable/event_log.py`
  - 新增 durable-neutral `EventLogReadClassFilter`、`EventLogReadFilter`、`FilteredEventLogPage`。
  - 新增 `read_events_after_matching(...)` 与 `EventLogStore.read_events_after_matching(...)`。
  - filtered read 使用 EventLog `event_class` / `event_type` SQL 条件和可选 `session_id` 范围读取匹配 rows。
  - covered cursor 由同一 transaction 内的真实 EventLog row 计算：空 log、cursor 已到 latest 或边界内无真实 row 时不推进；未填满 page 时覆盖到 latest 或 `max_event_sequence` 以内最近真实 row；填满 page 时覆盖到最后一条 matching row。

- `dayu/host/projection.py`
  - 新增 `_event_log_read_filter_from_projection_filter(...)`，把 consumer `ProjectionEventFilter` 机械转换为 durable `EventLogReadFilter`。
  - `ProjectionRunner` 改用 `read_events_after_matching(...)`。
  - matching row：构造 `ProjectionEventView`、调用 consumer、同事务推进 checkpoint 到该 row。
  - no matching + covered cursor：不调用 consumer，只推进 checkpoint 并清除 failure。
  - no covered advance：判定 idle。
  - `run_once(limit=...)` 文档改为 filtered read page size 与本轮 step cap，不再描述为全局扫描语义预算。

- `tests/host/test_event_log_store.py`
  - 覆盖 mixed canonical / preview / diagnostic filter。
  - 覆盖空 log、cursor 已到 latest、`max_event_sequence` 超过 latest、`max_event_sequence` 落在 sequence gap。

- `tests/host/test_projection_runner.py`
  - 覆盖跳过 unmatched 并推进到 matching checkpoint。
  - 覆盖无 matching 时推进 covered cursor 且不 apply。
  - 覆盖 target before next matching row 时推进到 target 且不 apply。
  - 覆盖 matching row 失败时 checkpoint 不越过失败 row。
  - 更新 `events_scanned` 断言为 filtered read/apply step 语义。

- `tests/host/test_projection_read_model.py`
  - 最小更新 failing consumer tests：用 `max_event_sequence` 表达 target cursor；失败场景只要求 checkpoint 未越过 failed matching row。

## Validation

- Follow-up docstring pass：补齐本 slice 新增/修改私有 helper 的 `:raises` 说明，满足 AGENTS.md 函数 docstring 约束；未改变行为。
- `source .venv/bin/activate && pytest tests/host/test_event_log_store.py tests/host/test_projection_runner.py`
  - 29 passed
- `source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_projection_read_model.py tests/host/test_outbox_projection.py tests/host/test_tool_trace_projection.py tests/host/test_audit_sink.py`
  - 85 passed
- `source .venv/bin/activate && pyright dayu/host/durable/event_log.py dayu/host/projection.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py`
  - 0 errors, 0 warnings
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings
- `git diff --check`
  - passed

## README Decision

已检查 `dayu/host/README.md` 与 `tests/README.md` 的更新边界。本 slice 未新增用户入口、Host public API、测试分层或稳定开发者接口说明；filter-aware EventLog read 与 ProjectionRunner catch-up 属于内部机制细化，现有 README 不需要更新。

## Residual Risks

- fixed in current slice：EventLog durable helper 不包含 memory-specific 逻辑，ProjectionRunner 不再用全局 EventLog read 后在内存过滤。
- fixed in current slice：`max_event_sequence` 位于 latest 之后或 sequence gap 中时，covered cursor 只指向真实 EventLog row。
- fixed in current slice：无 matching row 但 covered cursor 可推进时，ProjectionRunner 不调用 consumer，仅推进 checkpoint。
- covered by later approved slice：`memory_repair`、`open_host`、`dispatch` 仍保留 Slice 4 前的 budget / hot-path 语义，未在本 slice 修改。
- covered by later approved slice：RunInputBuilder inline repair 仍未共用 conversation memory consumer filter，本 slice 按用户边界未实现。

## Completion Status

Slice 3 implementation complete。未修改 Host / Engine public API/contracts，未修改 durable schema，未移除 `MemoryProjectionCatchupBudget`。
