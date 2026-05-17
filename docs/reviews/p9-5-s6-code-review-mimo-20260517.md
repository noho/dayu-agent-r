# P9.5 S6 Read API Enum Mapping And Minimal Read Model Reset Contract — Code Review (AgentMiMo)

## Gate

- Role: AgentMiMo, review-only.
- Gate: P9.5 S6 Read API Enum Mapping And Minimal Read Model Reset Contract code review.
- Approved plan: `docs/host/p9-5-pre-p10-hardening-plan.md` section S6.
- Implementation artifact: `docs/reviews/p9-5-s6-read-api-enum-reset-implementation-20260517.md`.
- Reviewed files: `dayu/host/read_api.py`, `dayu/host/durable/state.py`, `dayu/host/durable/read_model.py`, `tests/host/test_public_event_stream.py`, `tests/host/test_projection_read_model.py`, `tests/host/test_public_run_api.py`, `tests/host/test_public_session_api.py`, `dayu/host/README.md`.
- No code, tests, plan, or artifacts were modified. No commit, push, or PR.

## Review Focus Verification

### 1. Durable row enum -> public enum / event view mapping 是否 fail closed，且 public facade 转为 HostApiError 而不泄漏 ValueError / 未知字符串

**结论：通过。**

**EventClass mapping**（`read_api.py:224-239`，`_public_event_class_from_durable`）：
- `isinstance(event_class, EventClass)` 检查 → 非 `EventClass` 实例抛 `HostDurableError`。
- `HostEventClass(event_class.value)` → `ValueError` 被捕获并转为 `HostDurableError("EventLog event_class is not public")`。
- 上游 `_event_view_from_row` 调用此 helper，`_StreamRunEventsOperation.__call__` 通过 `host._run_read()` 执行，`HostDurableError` 由 S3 新增的 `_host_api_error_from_durable_error()` 转为 `HostApiError(code=INTERNAL_ERROR)`。

**RunStatus mapping**（`state.py:403-418`，`_public_run_status_from_durable`）：
- `isinstance(status, RunStatus)` 检查 → 非 `RunStatus` 实例抛 `HostDurableError`。
- `run_snapshot_from_row` 调用此 helper，`_GetRunOperation.__call__` 通过 `host._run_read()` 执行，`HostDurableError` 被转换为 `HostApiError`。

**SessionStatus mapping**（`state.py:393-403`，`_public_session_status_from_durable`）：
- `isinstance(status, SessionStatus)` 检查 → 非 `SessionStatus` 实例抛 `HostDurableError`。
- `session_snapshot_from_rows` 调用此 helper，`_GetSessionOperation.__call__` 通过 `host._run_read()` 执行，`HostDurableError` 被转换为 `HostApiError`。

**AttemptStatus mapping**（`state.py:486-496`，`deserialize_attempt_status`）：
- 委托 `_deserialize_str_enum`（`state.py:3466-3482`），`ValueError` 被捕获并转为 `HostDurableError`。
- 已有函数，S6 未修改，只补充了 exhaustiveness 与 fail-closed 测试。

**泄漏路径验证**：所有 mapping helper 都抛 `HostDurableError`（非 `ValueError`），且都位于 `host._run_read()` 事务内，`_host_api_error_from_durable_error()` 统一转换为 `HostApiError(INTERNAL_ERROR, retryable=False)`。无 `ValueError` 或未知字符串泄漏到 public snapshot / event view。

### 2. get_run / get_session / stream_run_events 是否仍读 durable truth / EventLog，不依赖 read model / projection truth

**结论：通过。**

- `get_run`（`read_api.py:49-58`）→ `_GetRunOperation.__call__`（`read_api.py:124-139`）→ `read_run_by_id(transaction, run_id)` 读 durable `RunRow` → `run_snapshot_from_row(run)` 构造 `RunSnapshot`。不读 `host_run_results`。
- `get_session`（`read_api.py:37-46`）→ `_GetSessionOperation.__call__`（`read_api.py:96-117`）→ `read_session_by_id(transaction, session_id)` 读 durable `SessionRow` → `session_snapshot_from_rows(...)` 构造 `SessionSnapshot`。不读 `host_session_timeline_items`。
- `stream_run_events`（`read_api.py:61-86`）→ `_StreamRunEventsOperation.__call__`（`read_api.py:150-201`）→ `read_events_after(transaction, cursor, limit=...)` 读 `EventLog`。不读 read model。

**read model 定位确认**：`host_run_results` 和 `host_session_timeline_items` 是 projection 物化，不是 truth source。三个 public read facade 全部读 durable truth / EventLog，与 read model 无关。

### 3. Minimal read model terminal_status / item_kind validation 是否只覆盖当前事实，不引入 schema / multi-consumer / P10+

**结论：通过。**

**terminal_status validation**（`read_model.py:454-470`，`_terminal_status_from_text`）：
- `_TERMINAL_RUN_STATUSES = frozenset((RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.LOST))` — 只包含当前 4 个终态，与 `RunStatus` enum 当前成员一致。
- `RunStatus(value)` → `ValueError` 被捕获转为 `HostDurableError`。
- `status not in _TERMINAL_RUN_STATUSES` → 非终态抛 `HostDurableError`。
- 未引入新状态名、schema column 或 future enum。

**item_kind validation**（`read_model.py:473-496`，`_validate_timeline_item_kind` / `_validated_timeline_item_kind_text`）：
- `_TIMELINE_ITEM_KINDS = frozenset(("user_input", "run_lifecycle", "run_terminal"))` — 只包含当前 3 个 kind，与 `MinimalReadModelProjectionConsumer` 实际写入的 kind 一致。
- `value not in _TIMELINE_ITEM_KINDS` → 未知 kind 抛 `HostDurableError`。
- 未引入新 kind、schema column 或 future kind。

**multi-consumer / P10+ 验证**：
- `_TERMINAL_RUN_STATUSES` 和 `_TIMELINE_ITEM_KINDS` 都是模块级 `frozenset`，不引入 `consumer_id` schema 或 multi-consumer isolation。
- `_terminal_status_from_text` 在 `_run_result_from_host_row`（read codec）和 `_validate_run_result`（write validation）两处调用，只校验当前事实。
- 未引入 `consumer_id` 列、multi-consumer routing 或 P10+ projection 语义。

### 4. reset_minimal_read_model_projection doc / test / README 是否只说明固定 single consumer 和 reset + EventLog replay repair contract

**结论：通过。**

**docstring**（`read_model.py:289-296`）：
- "``host_run_results`` 与 ``host_session_timeline_items`` 由固定 ``host.minimal-read-model`` consumer 独占。repair 时允许清空这两张表，再从 committed EventLog replay 重建；它们不是 Host governance truth。"
- 明确了 single consumer 独占、reset + replay 合法、非 truth source。未引入 multi-consumer 概念。

**test**（`test_projection_read_model.py`，`test_minimal_read_model_reset_replays_fixed_consumer_owned_tables`）：
- 通过 `_delete_minimal_read_model_owned_rows` 直接 DELETE 两张表。
- 调用 `repair_minimal_read_models(transaction_runner, reset_checkpoint=True, batch_size=2)` 触发 reset + replay。
- 验证 replay 后 `RunResult` 和 `SessionTimelineItems` 与 reset 前一致。
- 未引入 `consumer_id` 参数或多 consumer 隔离逻辑。

**README**（`dayu/host/README.md` Phase 8 说明）：
- "当前固定 single consumer ``host.minimal-read-model`` 独占投影…reset 后从 EventLog replay 是合法 repair 路径。"
- 与 docstring 和 test 一致。未引入 multi-consumer 语义。

### 5. 测试是否通过 dataclass / helper 直接构造 unknown enum，而不是污染 DB CHECK

**结论：通过。**

- `test_event_view_mapping_rejects_unknown_event_class`：`cast(EventClass, "future_event_class")` → `_event_log_row(...)` 构造 `EventLogRow` dataclass → `_event_view_from_row(...)` → `HostDurableError`。全程 in-memory，不写 DB。
- `test_run_snapshot_mapping_rejects_unknown_run_status`：`cast(RunStatus, "future_run_status")` → `_durable_run_row(...)` 构造 `RunRow` dataclass → `run_snapshot_from_row(...)` → `HostDurableError`。全程 in-memory。
- `test_session_status_mapping_rejects_unknown_session_status`：`cast(SessionStatus, "future_session_status")` → `_durable_session_row(...)` 构造 `SessionRow` dataclass → `_public_session_status_from_durable(...)` → `HostDurableError`。全程 in-memory。
- `test_attempt_status_mapping_rejects_unknown_attempt_status`：`deserialize_attempt_status("future_attempt_status")` → `HostDurableError`。直接传字符串，不写 DB。
- `test_read_model_python_validation_rejects_unknown_terminal_status`：构造 `RunResultRow(terminal_status="future_terminal", ...)` dataclass → `insert_run_result_if_absent(...)` → `HostDurableError`。写 DB 前被 Python validation 拒绝。
- `test_read_model_python_validation_rejects_unknown_timeline_kind`：构造 `SessionTimelineItemRow(item_kind="future_kind", ...)` dataclass → `insert_session_timeline_item_if_absent(...)` → `HostDurableError`。写 DB 前被 Python validation 拒绝。
- `test_get_run_unknown_durable_status_returns_internal_error`：monkeypatch `read_run_by_id` 返回带未知 status 的 `RunRow` → `HostApiError(INTERNAL_ERROR)`。不写 DB。
- `test_stream_run_events_unknown_event_class_returns_internal_error`：monkeypatch `read_events_after` 返回带未知 `event_class` 的 `EventLogRow` → `HostApiError(INTERNAL_ERROR)`。不写 DB。
- `test_get_session_unknown_durable_status_returns_internal_error`：monkeypatch `read_session_by_id` 返回带未知 status 的 `SessionRow` → `HostApiError(INTERNAL_ERROR)`。不写 DB。

**所有测试都通过 `cast()`、直接构造 dataclass 或 monkeypatch 构造未知 enum，不依赖 DB CHECK 约束来测试 fail-closed 行为。**

### 6. 是否违反 AGENTS 硬约束

**结论：通过。无硬约束违反。**

| 约束 | 验证 |
|---|---|
| 类型：禁止 `Any`/`object`/无类型签名 | ✅ 所有新增函数有完整类型签名 |
| 中文 docstring | ✅ 所有新增函数/类有中文 docstring |
| 无 magic string | ✅ `_TERMINAL_RUN_STATUSES`、`_TIMELINE_ITEM_KINDS` 用 `frozenset` 定义，错误消息是常量字符串 |
| 无兼容 wrapper | ✅ 无新 wrapper |
| 无反向依赖 | ✅ `read_model.py` import `dayu.host.api.RunStatus`（同层），`read_api.py` import `dayu.host.durable.errors.HostDurableError`（下层） |
| 不新增 public facade | ✅ 所有新增 helper 都是 private（`_` 前缀） |
| 不新增 schema / status / public error code | ✅ |

## Findings

### F1 [Info] isinstance check 与 enum() 构造的双重防御

- **File/line**: `state.py:393-418`（`_public_session_status_from_durable`、`_public_run_status_from_durable`）、`read_api.py:230-232`（`_public_event_class_from_durable`）
- **Evidence**: `isinstance(status, SessionStatus)` 检查 + `SessionStatus` 是 `StrEnum`，正常从 SQLite 读取的值已经是 `SessionStatus` 实例。`isinstance` 检查主要防御 `cast()` 构造的测试场景和极端情况下 row codec 返回非 enum 实例。
- **Impact**: 纵深防御。正常生产路径中 `read_session_by_id` 返回的 `SessionRow.status` 已经是 `SessionStatus`（由 `_deserialize_str_enum` 保证），`isinstance` 检查不会触发。但它为 public 边界提供了额外的安全网。
- **Blocking**: No.

### F2 [Info] _TIMELINE_ITEM_KINDS 硬编码与 MinimalReadModelProjectionConsumer 写入的 kind 同步

- **File/line**: `read_model.py:40`（`_TIMELINE_ITEM_KINDS`）vs `dayu/host/read_model.py`（`MinimalReadModelProjectionConsumer.apply_event`）
- **Evidence**: `_TIMELINE_ITEM_KINDS = frozenset(("user_input", "run_lifecycle", "run_terminal"))` 是手动维护的集合。如果 `MinimalReadModelProjectionConsumer` 未来新增写入的 kind，必须同步更新此 frozenset。
- **Impact**: 当前 3 个 kind 与 consumer 实际写入一致。实现 artifact 已记录此约束。frozenset 模块级定义、校验在 write path 前执行，新增 kind 时 Python test 会立即失败（写入被拒），不会出现 silent divergence。
- **Blocking**: No.

### F3 [Info] _TERMINAL_RUN_STATUSES 与 RunStatus enum 成员的同步

- **File/line**: `read_model.py:36-38`（`_TERMINAL_RUN_STATUSES`）
- **Evidence**: `frozenset((RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED, RunStatus.LOST))` 引用 `RunStatus` enum 成员而非字符串。如果 `RunStatus` 新增终态成员，必须同步更新此 frozenset。
- **Impact**: 与 F2 同类。引用 enum 成员而非字符串降低了 desync 风险；`test_terminal_event_mapping_covers_current_run_terminal_statuses` 遍历所有终态验证覆盖。
- **Blocking**: No.

## Scope Adherence Verification

### Confirmed: plan boundaries honored

- 变更文件：`read_api.py`、`state.py`、`read_model.py`、4 个测试文件、`README.md`。
- 未修改 public facade（`api.py`、`command.py`）或 public error code。
- 未新增 schema column、`consumer_id` 或 multi-consumer isolation。
- 未引入 P10+ semantics。

### Confirmed: no prohibited semantics introduced

- No P10+ semantics (RECOVERING, ToolsDiscovery, etc.)
- No new state-machine states or transitions
- No compatibility re-export/wrapper
- No `Any`/`object`/untyped signatures
- No new public facade or public error code
- No schema changes

## P9.5 Scope / Non-Goals Check

| Concern | Status |
|---|---|
| New state-machine states | Not introduced |
| Schema changes | Not introduced |
| Public facade changes | Not introduced |
| RECOVERING / Phase 11 | Not introduced |
| Compatibility wrapper | Not introduced |
| Multi-consumer isolation | Not introduced |
| `Any`/`object`/untyped signatures | Not introduced |

## Summary

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Info observations**: 3 (F1–F3)

S6 实现正确达成计划目标：durable enum → public enum mapping 通过 `isinstance` + `enum()` 构造双重 fail-closed，`HostDurableError` 经 S3 转换层统一变为 `HostApiError(INTERNAL_ERROR)`，无 ValueError / 未知字符串泄漏；`get_run` / `get_session` / `stream_run_events` 仍读 durable Run / Session truth 与 EventLog，不依赖 read model；`_TERMINAL_RUN_STATUSES` 与 `_TIMELINE_ITEM_KINDS` 只覆盖当前事实，不引入 schema / multi-consumer / P10+；reset doc / test / README 明确 single consumer 独占与 reset + EventLog replay repair contract；测试通过 `cast()` / dataclass helper 直接构造 unknown enum，不污染 DB CHECK。无硬约束违反。
