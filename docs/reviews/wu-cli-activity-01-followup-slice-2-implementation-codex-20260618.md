# WU-CLI-ACTIVITY-01 follow-up Slice 2 implementation

## 元数据

- Gate: implementation
- Work unit: `WU-CLI-ACTIVITY-01 follow-up`
- Slice: Slice 2 Host ingest non-durable delta
- Agent: AgentCodex
- Date: 2026-06-18
- Accepted plan commit: `906c1ffa`
- Slice 1 accepted commit: `3cb5fcb4`
- Implementation artifact: `docs/reviews/wu-cli-activity-01-followup-slice-2-implementation-codex-20260618.md`

## Scope

本 slice 只实现 Host ingest 对 `content_delta`、`reasoning_delta`、`tool_call_delta` 的默认 non-durable 行为，不做 Slice 3 projection catch-up 改动，不修改 Host / Engine public API 或 public contracts。

Allowed files honored:

- `dayu/host/engine_ingest.py`
- `tests/host/test_engine_ingest_mapping.py`
- `dayu/host/README.md`
- `docs/reviews/wu-cli-activity-01-followup-slice-2-implementation-codex-20260618.md`

`dayu/host/README.md` 修改前已阅读其 `Agent更新约束【必须遵守】`，本次只同步当前已实现的 Host EventLog event class 语义。`docs/engine/design.md` 未修改，因为本 slice 未发现 Engine contract 或 Engine 设计真源需要变更的代码证据。

## First-principles judgment

动机成立。三类 delta 是 token / tool-call chunk 级展示信号，不是恢复、memory、audit 或 durable replay 的必要事实。把它们默认写进主 EventLog 会让 Host event stream 补读暗示 token-level delta replay 保真，并扩大 EventLog / projection 负担。

本 slice 的 root cause 是 Host ingest 的 preview 分类把三类 delta 与其它 preview event 混在一起，导致匹配类型的 delta 被 `_append_preview_event()` 写入主 EventLog。正确修复点在 Host ingest 分类，而不是修改 Engine event contract 或在下游 projection 隐藏这些 rows。

## Changes

- `dayu/host/engine_ingest.py`
  - 新增 `_is_transient_delta_event()`，仅当 event type 与 data 类型同时匹配 `ContentDeltaData`、`ReasoningDeltaData`、`ToolCallDeltaData` 时生效。
  - 在 validated ingest path 中优先把三类 delta 转成 accepted no-row result：`status=ACCEPTED`、`events=()`、无 terminal closeout、无 promotion。
  - 将 `tool_call_delta` 纳入 delta 日志降噪集合，保持与 content / reasoning delta 一致。
  - 不修改 EngineEvent、EngineIngestResult、Host public API 或 durable contract。

- `tests/host/test_engine_ingest_mapping.py`
  - 覆盖三类 delta 均返回 accepted 且不写 `CONTENT_DELTA` / `REASONING_DELTA` / `TOOL_CALL_DELTA` EventLog row。
  - 保留 wrong data / missing data 对 `CONTENT_DELTA` 的 rejected diagnostic 断言，避免类型不匹配被静默吞掉。
  - 将旧 steer stale/current preview 测试从 `CONTENT_DELTA` 改为 `CONTENT_COMPLETED`，使该测试继续覆盖 stale execution rejection 与当前 attempt preview 接受，不和 non-durable delta 目标混杂。
  - 保留 tool batch ready / done preview-not-canonical 断言，确认非 delta preview 语义不受影响。

- `dayu/host/README.md`
  - 更新 EventLog event class 说明：`PREVIEW` 不再把 content / reasoning / tool-call delta 列为默认 EventLog 示例；三类 delta 默认只作为 transient ingest 信号接受，不参与 durable replay。

## Validation

已运行：

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py`
  - Result: 62 passed.
- `source .venv/bin/activate && pyright dayu/host/engine_ingest.py tests/host/test_engine_ingest_mapping.py`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed with no output.

## Residual risks and uncovered areas

- `RR-S2-01`: 本 slice 只改变 Host ingest durable mapping；即时 live token fanout 仍未实现。分类：accepted scope。Owner：后续 transient fanout design / implementation。
- `RR-S2-02`: ProjectionRunner catch-up / filtered read 语义未在本 slice 实现。分类：explicitly out of scope。Owner：Slice 3。
- `RR-S2-03`: 迟到或 stale 的 delta 仍会先经过现有 durable identity / late checks；本 slice未重排校验顺序，以避免扩大治理行为变更。分类：known behavior retained。Owner：若未来要求所有 delta 都完全无 durable diagnostic，需要单独设计。

## Completion status

Implementation edits and validation completed.

Stop condition hit: no.
