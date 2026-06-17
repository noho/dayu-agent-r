# Code Review

## Scope

- Mode: current changes
- Branch: wu-cli-activity-01
- Base: main (workspace uncommitted changes only)
- Output file: docs/reviews/code-review-20260618-065959-mimo-wu-cli-activity-01-followup-slice-2.md
- Included scope:
  - `dayu/host/engine_ingest.py` — uncommitted changes
  - `tests/host/test_engine_ingest_mapping.py` — uncommitted changes
  - `dayu/host/README.md` — uncommitted changes
  - `docs/reviews/wu-cli-activity-01-followup-slice-2-implementation-codex-20260618.md` — implementation notes
- Excluded scope: already committed plan / Slice 1 commits; `docs/host/design.md` (design truth, not modified)
- Parallel review coverage: 无

## Findings

### 1-未修复-中-`_is_preview_event` 与 `_preview_payload` 中三类 delta 分支变为死代码

- **入口/函数**: `_ingest_validated` → `_is_transient_delta_event` / `_is_preview_event` / `_preview_payload`
- **文件(行号)**: `dayu/host/engine_ingest.py:928-929`（early return）、`dayu/host/engine_ingest.py:4680-4690`（`_is_preview_event` 中仍保留 CONTENT_DELTA / REASONING_DELTA / TOOL_CALL_DELTA 分支）、`dayu/host/engine_ingest.py:4751-4767`（`_preview_payload` 中仍保留 ContentDeltaData / ReasoningDeltaData / ToolCallDeltaData 处理）
- **输入场景**: 任何 CONTENT_DELTA / REASONING_DELTA / TOOL_CALL_DELTA event
- **实际分支**: `_ingest_validated` 第 928 行 `_is_transient_delta_event` 先命中，返回 accepted no-row result；第 1010 行 `_is_preview_event` 永远不会被三类 delta event 到达
- **预期行为**: `_is_preview_event` 和 `_preview_payload` 只包含可达分支；或者三类 delta 的 preview 分支被显式标记为防御性保留
- **实际行为**: `_is_preview_event` 仍声称 CONTENT_DELTA / REASONING_DELTA / TOOL_CALL_DELTA 属于 preview event 类型，`_preview_payload` 仍有针对这三类 data 的 payload 构造分支。这些分支在当前 `_ingest_validated` 流程中完全不可达
- **直接证据**: `engine_ingest.py:928` 的 early return 在 `engine_ingest.py:1010` 的 `_is_preview_event` 检查之前；`_is_preview_event` 4680-4690 行仍包含三类 delta 的 type+data 匹配；`_preview_payload` 4751-4767 行仍处理 `ContentDeltaData` / `ReasoningDeltaData` / `ToolCallDeltaData`
- **影响**: 维护隐患。未来开发者查看 `_is_preview_event` 时会认为三类 delta 仍走 preview 写入路径，可能在新增 delta 类型时只更新 `_is_preview_event` 而忘记更新 `_is_transient_delta_event`，导致新 delta 类型被写入 EventLog 而非走 transient 路径。当前行为正确（early return 兜底），但两个函数的语义声明互相矛盾
- **建议改法和验证点**: 从 `_is_preview_event` 中移除 CONTENT_DELTA / REASONING_DELTA / TOOL_CALL_DELTA 三个分支；从 `_preview_payload` 中移除 `ContentDeltaData` / `ReasoningDeltaData` / `ToolCallDeltaData` 三个 elif 分支。移除后运行 `test_delta_events_are_accepted_without_event_log_rows`、`test_tool_batch_events_stay_preview_not_canonical`、`test_preview_event_rejects_missing_or_wrong_data` 和 `test_transient_delta_event_accepts_matching_type_without_row` 确认无回归
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-stale / late delta event 缺少显式测试覆盖

- **入口/函数**: `_ingest_before_reactive_compaction` → `_validate_durable_context` / `_late_rejection_reason` → `_ingest_validated`
- **文件(行号)**: `dayu/host/engine_ingest.py:751-768`（stale / late 检查在 `_ingest_validated` 之前）、`tests/host/test_engine_ingest_mapping.py:2025-2085`（`test_delta_events_are_accepted_without_event_log_rows`）
- **输入场景**: 一个 CONTENT_DELTA event 携带 stale execution_id 或在 terminal closeout 之后到达
- **实际分支**: 代码路径正确——`_validate_durable_context` 返回 None 导致 stale rejection diagnostic，`_late_rejection_reason` 返回 late reason 导致 late rejection diagnostic，两者都在 `_ingest_validated` 之前拦截。但测试未显式验证 delta event 走这两条路径
- **预期行为**: stale / late delta event 被 rejected，与其它 event type 一致
- **实际行为**: 代码行为正确，但测试只用 `FinalAnswerData` / `RunFailedData` 测试 stale / late rejection；`test_delta_events_are_accepted_without_event_log_rows` 只覆盖 happy path
- **直接证据**: `test_stale_execution_id_is_rejected_diagnostic` 使用 `FinalAnswerData`；`test_late_terminal_event_is_rejected_after_closeout` 使用 `RunFailedData`；`test_delta_events_are_accepted_without_event_log_rows` 的三个 candidate 都使用同一 active run 的合法 identity
- **影响**: 若未来重构 `_validate_durable_context` 或 `_late_rejection_reason` 时改变了对 delta 的拦截顺序，没有直接的 regression test 捕获
- **建议改法和验证点**: 补充一个参数化测试 case，用 `CONTENT_DELTA` + `ContentDeltaData` 作为 stale execution_id 的 candidate，断言返回 `REJECTED` + `stale_execution_id` reason；类似补充 late rejection case。或至少在现有 `test_stale_execution_id_is_rejected_diagnostic` 中增加一个 `CONTENT_DELTA` 参数化分支
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-`_accepted_no_event_result` 与 `_event_rows_result` 存在重复结构

- **入口/函数**: `_accepted_no_event_result` / `_event_rows_result`
- **文件(行号)**: `dayu/host/engine_ingest.py:6109-6122` / `dayu/host/engine_ingest.py:6093-6106`
- **输入场景**: 任何 transient delta event
- **实际分支**: `_accepted_no_event_result` 构造 `events=()` 的 result；`_event_rows_result` 构造 `events=(row, ...)` 的 result
- **预期行为**: 两个函数都产出 `EngineIngestResult`，字段结构一致，区别仅在 `events` 内容
- **实际行为**: 两个函数结构几乎相同，仅 `events` 参数不同。当前可维护，但如果 `EngineIngestResult` 新增字段，需要同步修改两处
- **直接证据**: 两个函数都设置 `status=ACCEPTED`、`terminal_closeout=False`、`promotion_triggered=False`、`reason=None`
- **影响**: 低。代码清晰度尚可，但属于轻度重复
- **建议改法和验证点**: 可考虑让 `_accepted_no_event_result()` 内部调用 `_event_rows_result(())` 以消除重复。但这属于 style 层面，不阻塞 merge
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

- `RR-S2-01`: 即时 live token fanout 未在本 slice 实现。分类：accepted scope。Owner：后续 transient fanout design / implementation。
- `RR-S2-02`: ProjectionRunner catch-up / filtered read 语义未在本 slice 实现。分类：explicitly out of scope。Owner：Slice 3。
- `RR-S2-03`: `_is_preview_event` 死代码未清理（见 Finding 1），若不清理则后续新增 delta 类型时存在维护陷阱。
