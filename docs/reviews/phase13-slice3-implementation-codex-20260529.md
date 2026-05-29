# Phase 13 Slice 3 Implementation Report

## Gate

Phase 13 implementation，Slice 3 OutboxSink Durable Projection。

## Plan

- Accepted plan：`docs/host/phase13-audit-tool-trace-outbox-plan.md`
- Schema clarification：`docs/reviews/phase13-schema-version-controller-clarification-20260529.md`
- 当前 committed Host schema version：12
- 本 slice schema bump：12 -> 13

## Scope

Allowed files：

- `dayu/host/outbox.py`
- `dayu/host/durable/outbox.py`
- `dayu/host/durable/schema.py`
- `tests/host/test_outbox_projection.py`
- `tests/host/test_outbox_durable.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/phase13-slice3-implementation-codex-20260529.md`

Changed files：

- `dayu/host/outbox.py`
- `dayu/host/durable/outbox.py`
- `dayu/host/durable/schema.py`
- `tests/host/test_outbox_projection.py`
- `tests/host/test_outbox_durable.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/phase13-slice3-implementation-codex-20260529.md`

未修改 public API wiring、`open_host`、`read_api`、EventLog append、Run/Attempt state machine、terminal transaction、watch API、Engine、Service、UI、Fins 或 README。

## Implemented Items

- 新增 schema 13 的 `host_outbox_terminal_items`、`host_outbox_drain_idempotency` 与索引。
- 新增 `OutboxTerminalProjectionConsumer`，consumer id 为 `host.outbox-terminal`。
- 从 `RUN_SUCCEEDED`、`RUN_FAILED`、`RUN_CANCELLED` terminal canonical facts 派生 Outbox terminal item。
- `RUN_LOST` 返回 skipped，detail code 为 `run_lost_not_public_terminal_item`，不创建 public terminal item。
- item identity / idempotency key 使用 terminal event id、run id、result refs 与 terminal summary refs 稳定派生，不使用 final answer 文本。
- durable helper 支持按 cursor 读取、过滤 seen terminal ids、返回 scanned watermark 与 has_more。
- durable drain 按 `(session_id, drain_request_id)` 幂等，request digest 冲突抛结构化 idempotency conflict，仅更新 Outbox item state，不写 EventLog，不表示 channel delivery success。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_outbox_projection.py tests/host/test_outbox_durable.py tests/host/test_durable_schema.py -q`
  - Result：pass，`26 passed`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result：pass，`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result：pass

## Docs Decision

未更新 README。当前 handoff 明确本 slice 不修改 README，public Outbox read / drain wiring 属于 Slice 4；本 slice 只新增内部 projection 与 durable helper，尚未改变用户手册或 Host public API。

## Plan Gaps

- Slice 3 handoff 未要求定义 public `OutboxTerminalItem` API dataclass；由于 `dayu/host/api.py` 不在允许文件内，本实现只提供内部 durable row 与 projection consumer。Public API 类型与 handle wiring 应由 Slice 4 完成。
- Succeeded terminal 第一版只在 inline payload 已携带 `final_answer`、`filtered`、`degraded` 字段时写 `final_answer_json`；常规 terminal summary refs 被完整保存，未在 projection 中读取 payload descriptor 形成 public final answer。

## Residual Risks

- Public read / drain status、projection catch-up status、Host handle closed/session gone 错误语义尚未接线；owner：Slice 4。
- Outbox item cleanup、retention、purge tombstone 行为不在本 slice；owner：Phase 15 Retention / Purge / Production Hardening。
- Drain idempotency replay 以首次 drain 的 item id 集合为真源；若未来引入 outbox cleanup，需要先定义 idempotency row 与 item row 的保留关系；owner：后续 retention 设计。

## Stop Status

未触发 stop condition。实现保持在允许文件范围内，未进入 commit、push 或 PR gate。
