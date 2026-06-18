# Code Re-Review

## Scope

- Mode: current changes (fix verification)
- Branch: wu-cli-activity-01
- Base review artifact: `docs/reviews/code-review-20260618-070001-ds-wu-cli-activity-01-followup-slice-2.md`
- Fix artifact: `docs/reviews/wu-cli-activity-01-followup-slice-2-fix-codex-20260618.md`
- Output file: `docs/reviews/code-review-20260618-070659-ds-rereview-wu-cli-activity-01-followup-slice-2.md`
- Reviewed scope:
  - `dayu/host/engine_ingest.py` — `_is_preview_event`、`_preview_payload` 内 delta 分支删除；`_is_transient_delta_event`、`_accepted_no_event_result` 保持不变
  - `tests/host/test_engine_ingest_mapping.py` — 测试重命名、新增 stale/late delta regression 测试
- Excluded scope: 已提交 commits、未变更文件、Slice 3 projection catch-up

## Finding Status

### Finding 1: `_preview_payload` 内 delta 分支成为不可达死代码

**原审编号**: 1-未修复-低
**裁决**: accepted（Codex fix 选择方案 B：删除死代码分支）

**状态: 已修复**

- **代码证据**: `_is_preview_event:4676-4697` 已删除 CONTENT_DELTA / REASONING_DELTA / TOOL_CALL_DELTA 三个 `(event.type == X and isinstance(event.data, Y))` 分支。`_preview_payload:4738-4758` 已删除 `ContentDeltaData` / `ReasoningDeltaData` / `ToolCallDeltaData` 三个 `elif isinstance(data, ...)` 分支及对应的 payload 构造逻辑。
- **校验**: `_is_preview_event` 现仅包含 ITERATION_STARTED、CONTENT_COMPLETED、TOOL_CALLS_BATCH_READY、TOOL_CALL_REQUESTED、TOOL_RESULT_ACCEPTED、TOOL_CALLS_BATCH_DONE、ITERATION_COMPLETED 七个非 delta 类型。`_preview_payload` 内 `isinstance` dispatch 与 `_is_preview_event` 完全对齐。`_is_transient_delta_event:4700-4717` 独立持有三类 delta 的 type+data 分类，语义边界清晰。
- **副作用检查**: 无其他调用方依赖 `_is_preview_event` 对 delta 返回 `True`。grep 确认 `_is_preview_event` 仅 `_ingest_validated:1010` 一处调用点，`_preview_payload` 仅 `_append_preview_event:2423` 一处调用点。三个 delta 类型在两函数内已无残留。

### Finding 2: 测试命名滞后

**原审编号**: 2-未修复-低
**裁决**: accepted（Codex fix 重命名测试）

**状态: 已修复**

- **代码证据**: `test_preview_event_rejects_missing_or_wrong_data` → `test_transient_delta_event_rejects_missing_or_wrong_data`（`:2417`）。docstring 从 `"preview event 必须同时匹配 event type 与 data 类型。"` 改为 `"transient delta event 必须同时匹配 event type 与 data 类型。"`。
- **校验**: 测试参数仍为 `(None, CONTENT_DELTA)` 和 `(IterationStartedData, CONTENT_DELTA)`，断言不变（REJECTED + `stop_worker_stream=True`）。行为路径验证：两种错误 data 均不匹配 `_is_transient_delta_event`（`isinstance` 失败），也不匹配修正后的 `_is_preview_event`（delta 分支已删除），正确落 rejection fallthrough。

## 新增测试覆盖验证

Codex fix 新增了两条治理回归测试：

### `test_stale_transient_delta_is_rejected_before_no_row_short_circuit` (`:1042`)

- **入口**: `_seed_active_run` + `_steer_to_new_running_attempt` → steer 产生新 Attempt，旧 Attempt 变为 stale
- **输入**: `ContentDeltaData` + `EngineEventType.CONTENT_DELTA`，使用旧（stale）Attempt 的 envelope
- **验证点**: `result.status == REJECTED`、`reason == "stale_execution_id"`、`_event_count("CONTENT_DELTA") == 0`
- **经过路径**: `ingest()` → `_operation()` → `_validate_durable_context()` → `None`（因 `run.current_attempt_id != envelope.attempt_id`）→ `_append_rejected_diagnostic(reason="stale_execution_id")`。**未进入 `_ingest_validated`**，证明 transient short-circuit 在 `_ingest_validated` 内部，不绕过前置 governance。

### `test_late_transient_delta_is_rejected_before_no_row_short_circuit` (`:2191`)

- **入口**: 先 `ingest(FINAL_ANSWER)` 关闭 Run，再 `ingest(REASONING_DELTA)`
- **输入**: `ReasoningDeltaData` + `EngineEventType.REASONING_DELTA`，在 Run 已 terminal 后
- **验证点**: `result.status == REJECTED`、`reason == "terminal_already_closed"`、`_event_count("REASONING_DELTA") == 0`
- **经过路径**: `ingest()` → `_operation()` → `_validate_durable_context()` 通过 → `_duplicate_terminal_result()` → `_late_rejection_reason()` 返回 `"terminal_already_closed"` → `_append_rejected_diagnostic()`。**未进入 `_ingest_validated`**，证明 late governance 在 transient short-circuit 之前。

### Delta no-row 行为无回归

- `test_delta_events_are_accepted_without_event_log_rows:2028` — 三类 delta 均为 `ACCEPTED` + `events=()` + EventLog count=0
- `test_transient_delta_event_accepts_matching_type_without_row:2447` — CONTENT_DELTA 匹配数据返回 `ACCEPTED` + `events=()` + EventLog count=0
- `test_tool_batch_events_stay_preview_not_canonical:2079` — TOOL_CALLS_BATCH_READY/DONE 仍走 PREVIEW 路径（`EventClass.PREVIEW`），未被误吞为 transient

### 非 delta preview 无回归

- `test_tool_call_requested_and_result_accepted_are_preview:1979` — `EventClass.PREVIEW` 保持
- `test_iteration_completed_preview_includes_client_correlation_id:3116` — `EventClass.PREVIEW` 保持
- `test_old_steered_attempt_event_is_rejected_and_current_attempt_accepts:1012` — 改用 `CONTENT_COMPLETED`，`has_content is True` 断言正确

## Validation

- `pytest tests/host/test_engine_ingest_mapping.py`: **64 passed**（原 62 + 新增 2 条 stale/late delta 回归测试）
- `pyright dayu/host/engine_ingest.py tests/host/test_engine_ingest_mapping.py`: **0 errors, 0 warnings**
- `git diff --check`: passed

## Final Finding Status Table

| 原审编号 | 简述 | 状态 |
|----------|------|------|
| 1-未修复-低 | `_preview_payload` / `_is_preview_event` 内 delta 死代码分支 | **已修复** |
| 2-未修复-低 | `test_preview_event_rejects_missing_or_wrong_data` 命名滞后 | **已修复** |
| (新增) | stale delta regression 覆盖 | **已修复** — 新增 `test_stale_transient_delta_is_rejected_before_no_row_short_circuit` |
| (新增) | late delta regression 覆盖 | **已修复** — 新增 `test_late_transient_delta_is_rejected_before_no_row_short_circuit` |

## Residual Risk

- 与首次 review 一致：malformed delta 的 `stop_worker_stream=True` 行为保持现状，未在本 slice 修改。
- `_accepted_no_event_result` 与 `_event_rows_result` / `_single_event_result` 的 `stop_worker_stream` 默认值依赖保持与现有模式一致。
- ProjectionRunner catch-up / filtered read 仍属 Slice 3，不在本次 scope。
