# Phase 13 Aggregate Re-Review Controller Adjudication

## Gate

Phase 13 aggregate fix re-review adjudication。

## Inputs

- Aggregate fix artifact: `docs/reviews/phase13-aggregate-fix-codex-20260529.md`
- AgentMiMo re-review: `docs/reviews/phase13-aggregate-rereview-mimo-20260529.md`
- AgentDS re-review: `docs/reviews/phase13-aggregate-rereview-ds-20260529.md`
- Aggregate review adjudication: `docs/reviews/phase13-aggregate-deepreview-controller-adjudication-20260529.md`

## Verdict

**PASS**。两路 aggregate re-review 均确认 F001 fixed，无新增 blocking findings。Phase 13 可以进入 `ready-to-open-draft-PR`。

## Controller Decision

### F001: `read_api.py` 直接导入 `dayu.host.durable.projection`

裁决：fixed。

证据：

- `dayu/host/read_api.py` 不再 import `dayu.host.durable.projection`。
- projection checkpoint / failure / latest watermark 读取职责已下沉到 `dayu/host/durable/outbox.py` 的 `read_outbox_terminal_projection_state(...)`。
- `read_api.py` 只调用 outbox durable helper，并负责 durable status 到 public `OutboxProjectionStatus` 的映射。
- public Outbox read/drain API 形状、`CAUGHT_UP` / `LAGGED` / `FAILED` 语义、`watch_session_events` live-only、EventLog / Run / Attempt 边界均未改变。

## Final Validation Required Before Commit

Controller 在创建 accepted aggregate review commit 前需重新运行：

- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_outbox_durable.py -q`
- `source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_outbox_projection.py tests/host/test_outbox_durable.py tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_public_event_stream.py tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py tests/host/test_package_exports.py tests/host/test_durable_schema.py tests/host/test_import_boundary.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`

## Residual Risks / Owners

- JSONL / SQLite checkpoint 跨介质 exactly-once：Phase 15 Retention / Purge / Production Hardening。
- Outbox drain 不等于 channel delivery success：Service / channel adapter owner；后续 Service 集成必须持久化 seen terminal watermark / ids。
- purge tombstone audit record、outbox cleanup、tool trace cleanup、projection cleanup：Phase 15。
- External audit、long-term archival、heavy sink runner / batch transaction hardening：Phase 15+ production hardening。

## Outcome

通过最终验证并提交 aggregate fix / review artifacts 后，Phase 13 达到 `ready-to-open-draft-PR`。用户已授权到达该 gate 后自动进入 draft PR gate。
