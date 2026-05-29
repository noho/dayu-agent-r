# Phase 13 Aggregate Deepreview Controller Adjudication

## Gate

Phase 13 aggregate deepreview adjudication。

## Inputs

- AgentMiMo aggregate review: `docs/reviews/phase13-aggregate-deepreview-mimo-20260529.md`
- AgentDS aggregate review: `docs/reviews/phase13-aggregate-deepreview-ds-20260529.md`
- Accepted plan: `docs/host/phase13-audit-tool-trace-outbox-plan.md`
- Design truth: `docs/host/design.md`
- Controller reproduction: `source .venv/bin/activate && pytest tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth -q`

## Verdict

**NEEDS FIX**。接受 AgentMiMo F001 为 blocking finding。AgentDS PASS 结论中没有覆盖该 import-boundary failure；以可复现测试失败和项目 import boundary 约束为准。

## Accepted Blocking Finding

### F001: `read_api.py` 直接导入 `dayu.host.durable.projection`

裁决：accepted blocking。

理由：`read_api.py` 是 Host public read facade，现有 `tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth` 明确禁止 `dayu.host.durable.projection` 依赖。Phase 13 Slice 4 为了暴露 Outbox projection status 在 `read_api.py` 直接读取 projection checkpoint/failure，虽然功能语义正确，但违反已有依赖边界并导致测试失败。root cause 是 projection state 查询职责放在 public read facade，而不是 durable outbox helper。

Required fix：

- 将 projection checkpoint/failure 读取下沉到 `dayu/host/durable/outbox.py`。
- `read_api.py` 只调用 outbox durable helper 获取 projection state，不直接 import `dayu.host.durable.projection`。
- 保持 public API 形状、Outbox read/drain 行为、projection status 语义不变。
- 增加或更新测试以覆盖 import boundary 通过。

## Non-blocking Residuals

- Tool Trace cold JSONL / SQLite checkpoint 跨介质 crash window：Phase 15 retention / cleanup owner。
- JSONL exactly-once、Outbox drain 非 channel delivery success、external audit / long-term archival / heavy sink runner：均已在 accepted plan 和总控文档中归属后续 owner。

## Outcome

进入 Phase 13 aggregate fix gate。修复完成后必须运行：

- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_outbox_durable.py -q`
- `source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_outbox_projection.py tests/host/test_outbox_durable.py tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_public_event_stream.py tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py tests/host/test_package_exports.py tests/host/test_durable_schema.py tests/host/test_import_boundary.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
- `git diff --check`
