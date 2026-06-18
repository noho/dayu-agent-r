# WU-CLI-ACTIVITY-01 follow-up Slice 2 fix

## 元数据

- Gate: implementation fix
- Work unit: `WU-CLI-ACTIVITY-01 follow-up`
- Slice: Slice 2 Host ingest non-durable delta
- Agent: AgentCodex
- Date: 2026-06-18
- Accepted plan commit: `906c1ffa`
- Slice 1 accepted commit: `3cb5fcb4`
- Implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-2-implementation-codex-20260618.md`
- Fix artifact: `docs/reviews/wu-cli-activity-01-followup-slice-2-fix-codex-20260618.md`

## Fix scope

本 fix 只处理 Slice 2 code review 裁决中的 accepted findings，不修改 Host / Engine public API 或 public contracts，不做 Slice 3 projection catch-up 改动。

Touched files:

- `dayu/host/engine_ingest.py`
- `tests/host/test_engine_ingest_mapping.py`
- `docs/reviews/wu-cli-activity-01-followup-slice-2-fix-codex-20260618.md`

已有 Slice 2 implementation 中的 `dayu/host/README.md` 同步未在本 fix 中继续扩展。

## Finding status

### Finding 1: 删除 delta 的不可达 preview 分支

Status: fixed.

Change:

- 从 `_is_preview_event()` 删除 `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA` 分支。
- 从 `_preview_payload()` 删除 `ContentDeltaData`、`ReasoningDeltaData`、`ToolCallDeltaData` payload 构造分支。

Rationale:

三类 delta 已在 `_ingest_validated()` 入口通过 `_is_transient_delta_event()` short-circuit 为 accepted no-row result。preview helper 继续声明这些分支可达，会与当前 ingest 真源冲突，并误导后续维护。

### Finding 2: 重命名 mismatch 测试语义

Status: fixed.

Change:

- `test_preview_event_rejects_missing_or_wrong_data` 重命名为 `test_transient_delta_event_rejects_missing_or_wrong_data`。
- docstring 从 preview event 语义改为 transient delta event type/data mismatch rejection 语义。

Rationale:

该测试现在验证的是 `CONTENT_DELTA` 在 data 缺失或 data 类型不匹配时不会被 no-row path 静默接受，而不是一般 preview event 映射。

### Finding 3: 补 stale / late delta regression 覆盖

Status: fixed.

Change:

- 新增 `test_stale_transient_delta_is_rejected_before_no_row_short_circuit`。
  - steer 后用旧 Attempt 的 `CONTENT_DELTA` 输入，断言返回 `ENGINE_EVENT_REJECTED` / `stale_execution_id`，且没有 `CONTENT_DELTA` EventLog row。
- 新增 `test_late_transient_delta_is_rejected_before_no_row_short_circuit`。
  - final answer closeout 后输入 `REASONING_DELTA`，断言返回 `ENGINE_EVENT_REJECTED` / `terminal_already_closed`，且没有 `REASONING_DELTA` EventLog row。

Rationale:

这两条测试证明 delta no-row short-circuit 位于 durable identity 和 late-event governance 之后，不绕过 `_ingest_validated()` 之前的治理校验。

## Rejected / deferred findings

- `_accepted_no_event_result` 与 `_event_rows_result` 结构重复：按裁决不阻塞，本 fix 未改。
- malformed delta 是否 stop worker stream：按裁决属于现有行为，不在本 slice 修改。

## Validation

已运行：

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py`
  - Result: 64 passed.
- `source .venv/bin/activate && pyright dayu/host/engine_ingest.py tests/host/test_engine_ingest_mapping.py`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed with no output.

## Residual risks

- 本 fix 不实现即时 live token fanout；三类 delta 当前只保证 Host ingest 默认 non-durable。
- ProjectionRunner catch-up / filtered read 仍属 Slice 3。
- malformed delta 的 stop-worker-stream 行为保持现状，未在本 fix 中重新设计。
