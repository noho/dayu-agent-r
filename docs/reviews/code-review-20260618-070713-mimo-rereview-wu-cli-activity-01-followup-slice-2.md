# Re-review: WU-CLI-ACTIVITY-01 follow-up Slice 2 fix

## Scope

- Mode: current changes (re-review of accepted findings)
- Branch: wu-cli-activity-01
- Base: main (workspace uncommitted changes only)
- Output file: docs/reviews/code-review-20260618-070713-mimo-rereview-wu-cli-activity-01-followup-slice-2.md
- Reviewed artifacts:
  - `docs/reviews/code-review-20260618-065959-mimo-wu-cli-activity-01-followup-slice-2.md` (original review)
  - `docs/reviews/wu-cli-activity-01-followup-slice-2-fix-codex-20260618.md` (fix notes)
- Included scope: `dayu/host/engine_ingest.py`, `tests/host/test_engine_ingest_mapping.py`, `dayu/host/README.md` (uncommitted changes)
- Excluded scope: already committed plan / Slice 1 / Slice 2 initial implementation commits
- Parallel review coverage: 无

## Original Findings Status

### Finding 1 — 已修复：`_is_preview_event` 与 `_preview_payload` 中三类 delta 死代码分支已删除

**验证证据：**

- `engine_ingest.py` diff 确认 `_is_preview_event()` 中 `CONTENT_DELTA`（旧 4680-4682）、`REASONING_DELTA`（旧 4683-4685）、`TOOL_CALL_DELTA`（旧 4689-4691）三个分支已删除。当前函数只保留 `ITERATION_STARTED`、`CONTENT_COMPLETED`、`TOOL_CALLS_BATCH_READY`、`TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`TOOL_CALLS_BATCH_DONE`、`ITERATION_COMPLETED` 七个可达分支（4676-4697）。
- `engine_ingest.py` diff 确认 `_preview_payload()` 中 `ContentDeltaData`（旧 4751-4753）、`ReasoningDeltaData`（旧 4754-4756）、`ToolCallDeltaData`（旧 4762-4767）三个 elif 分支已删除。当前函数从 `IterationStartedData` → `ContentCompleteData` → `ToolCallsBatchReadyData` 直接衔接（4739-4747），无死分支残留。
- `_is_transient_delta_event()` 保持不变，仍独立声明三类 delta 的 type+data 匹配（4700-4717）。
- 两个函数之间不再存在语义矛盾：`_is_preview_event` 不再声称处理 delta，`_is_transient_delta_event` 是唯一入口。

**回归风险评估：** 低。删除的分支在 `_ingest_validated` 中已被 `_is_transient_delta_event` 的 early return 屏蔽，从未被执行过。`test_delta_events_are_accepted_without_event_log_rows`、`test_transient_delta_event_accepts_matching_type_without_row` 和 `test_transient_delta_event_rejects_missing_or_wrong_data` 确认 delta 行为不受影响。`test_tool_batch_events_stay_preview_not_canonical` 确认非 delta preview 行为不受影响。

### Finding 2 — 已修复：stale / late delta 回归测试已补充

**验证证据：**

- 新增 `test_stale_transient_delta_is_rejected_before_no_row_short_circuit`（测试文件 2050 行附近）：
  - 使用 `_steer_to_new_running_attempt` 创建新 Attempt 后，用旧 Attempt identity 发送 `CONTENT_DELTA`。
  - 断言 `result.status == EngineIngestStatus.REJECTED`。
  - 断言 `result.events[0].event_type == "ENGINE_EVENT_REJECTED"`。
  - 断言 `_payload(result.events[0])["reason"] == "stale_execution_id"`。
  - 断言 `_event_count(store.transaction_runner, "CONTENT_DELTA") == 0`。
  - 测试通过（64 passed，此为新增 case 之一）。

- 新增 `test_late_transient_delta_is_rejected_before_no_row_short_circuit`（测试文件 2188 行附近）：
  - 先 ingest `FINAL_ANSWER` 关闭 Run，再用 `REASONING_DELTA` 作为迟到 event。
  - 断言 `result.status == EngineIngestStatus.REJECTED`。
  - 断言 `result.events[0].event_type == "ENGINE_EVENT_REJECTED"`。
  - 断言 `_payload(result.events[0])["reason"] == "terminal_already_closed"`。
  - 断言 `_event_count(store.transaction_runner, "REASONING_DELTA") == 0`。
  - 测试通过（64 passed，此为新增 case 之一）。

**治理顺序验证：** 两个测试证明 `_is_transient_delta_event` 的 early return 位于 `_validate_durable_context`（stale 检查）和 `_late_rejection_reason`（late 检查）之后，不绕过 durable identity governance。

### Finding 3 — 证据失效：`_accepted_no_event_result` 与 `_event_rows_result` 结构重复

按 fix artifact 记录，此 finding 被 controller 裁决为不阻塞 merge。fix 未修改此结构。当前行为正确，不属于 regression。状态标记为证据失效（非本 fix 目标）。

## 额外验证：测试语义重命名

- `test_preview_event_rejects_missing_or_wrong_data` → `test_transient_delta_event_rejects_missing_or_wrong_data`：docstring 从 "preview event 必须同时匹配 event type 与 data 类型" 改为 "transient delta event 必须同时匹配 event type 与 data 类型"。测试内容不变，仍验证 `CONTENT_DELTA` + `None` data 和 `CONTENT_DELTA` + `IterationStartedData` 两种 mismatch 场景被 rejected。语义准确。
- `test_preview_event_accepts_matching_type_and_data` → `test_transient_delta_event_accepts_matching_type_without_row`：断言从 `result.events[0].event_class == EventClass.PREVIEW` 改为 `result.events == ()`。语义准确，与 transient delta no-row 行为一致。
- `test_old_steered_attempt_event_is_rejected_and_current_attempt_accepts`：stale/current candidate 从 `CONTENT_DELTA` + `ContentDeltaData` 改为 `CONTENT_COMPLETED` + `ContentCompleteData`。原因正确——`CONTENT_DELTA` 现在走 transient no-row path，不再写 preview payload，无法用 `_payload(result.events[0])["delta"]` 断言。改为 `CONTENT_COMPLETED` 后仍覆盖 stale rejection 与 current attempt preview 接受的语义。断言从 `["delta"] == "new"` 改为 `["has_content"] is True`，与 `ContentCompleteData` payload 结构匹配。

## 额外验证：Host ingest no-row 行为无回归

- `test_delta_events_are_accepted_without_event_log_rows` 覆盖三类 delta（CONTENT_DELTA / REASONING_DELTA / TOOL_CALL_DELTA），全部返回 `ACCEPTED` + `events=()`。
- `test_tool_batch_events_stay_preview_not_canonical` 确认 `TOOL_CALLS_BATCH_READY` 和 `TOOL_CALLS_BATCH_DONE` 仍走 preview path 写入 EventLog，不受 delta no-row 改动影响。
- `test_tool_call_requested_and_result_accepted_are_preview` 确认 `TOOL_CALL_REQUESTED` 和 `TOOL_RESULT_ACCEPTED` 仍走 preview path。
- 64 个测试全部通过，pyright 零错误。

## Residual Risk

- 即时 live token fanout 未实现（accepted scope，非本 fix 目标）。
- ProjectionRunner catch-up / filtered read 属于 Slice 3。
- malformed delta 的 stop-worker-stream 行为保持现状。
