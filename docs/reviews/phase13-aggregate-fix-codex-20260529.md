# Phase 13 Aggregate Fix Codex 20260529

## Gate

Phase 13 aggregate deepreview fix。

## Source Review

- Controller adjudication: `docs/reviews/phase13-aggregate-deepreview-controller-adjudication-20260529.md`
- Accepted finding: AgentMiMo F001，`read_api.py` 直接导入 `dayu.host.durable.projection`

## Root Cause

F001 的动机成立，严重性评估成立。

直接证据是 `tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth` 明确禁止 `dayu.host.read_api` import `dayu.host.durable.projection`。Phase 13 Slice 4 为了在 public Outbox read / drain batch 中暴露 `projection_checkpoint` 与 `projection_status`，把 projection checkpoint / failure row 的读取放进了 `dayu/host/read_api.py`。功能语义本身能工作，但 public read facade 直接读取 projection-owned durable store，违反 Host read facade 边界。

正确修复点不是放宽 import boundary，也不是把 public status 语义复制到测试里绕过；root cause 是 Outbox projection checkpoint / failure state 的 durable 读取职责放错层，应由 `dayu.host.durable.outbox` 作为 Outbox projection-owned helper 承担。

## Changes

### F001-已修复-`read_api.py` 不再直接 import projection durable store

- `dayu/host/durable/outbox.py`
  - 新增 `OutboxTerminalProjectionStatus`、`OutboxTerminalProjectionCatchupError`、`OutboxTerminalProjectionReadState`。
  - 新增 `read_outbox_terminal_projection_state(...)`，统一读取 Outbox terminal projection checkpoint、failure row 与 EventLog 最新水位。
  - helper 只读取 projection-owned 状态和 EventLog watermark，不写 EventLog，不读写 Run / Attempt truth，不改变 drain state。

- `dayu/host/read_api.py`
  - 删除 `dayu.host.durable.projection` 的直接 import。
  - public read / drain transaction 改为调用 `read_outbox_terminal_projection_state(...)`。
  - 保留 public batch 映射职责：durable helper 的 checkpoint sequence 映射为 `OutboxTerminalCursor`，durable status 映射为 public `OutboxProjectionStatus`。
  - 保持 `CAUGHT_UP` / `LAGGED` / `FAILED` 语义不变：catch-up runtime error 或 failure row 为 `FAILED`，checkpoint 落后 EventLog watermark 为 `LAGGED`，否则为 `CAUGHT_UP`。

## Scope Guard

- 未新增或修改 `OpenHostOptions`。
- 未新增 `wait_final_answer`、`get_run_result`、payload reader 或 timeline replay。
- 未修改 `watch_session_events`。
- 未修改 EventLog append。
- 未修改 Run / Attempt terminal transaction。
- 未修改 public Outbox read / drain API 形状。
- 未修改用户已有的 `docs/host/implementation-control.md` 与 aggregate deepreview artifact。

## Tests And Validation

- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth -q`
  - 结果：通过，`1 passed in 0.21s`。
- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py::test_read_api_stream_does_not_reference_projection_or_fanout_truth tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_outbox_durable.py -q`
  - 结果：通过，`10 passed in 0.45s`。
- `source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_outbox_projection.py tests/host/test_outbox_durable.py tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_public_event_stream.py tests/host/test_watch_session_events.py tests/host/test_open_host_runtime.py tests/host/test_package_exports.py tests/host/test_durable_schema.py tests/host/test_import_boundary.py -q`
  - 结果：通过，`108 passed in 2.26s`。
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - 结果：通过，`0 errors, 0 warnings, 0 informations`。
- `git diff --check`
  - 结果：通过。

## Docs Decision

已检查 `dayu/host/README.md`。本次只调整内部 durable helper 归属，public API、Outbox read / drain 行为、projection status 语义和 Host 开发手册中的稳定边界表述均未变化，因此不更新 README，避免把文件级实现细节写入开发手册。

## Residual Risks

- 当前修复依赖既有 public outbox 行为测试覆盖 `LAGGED` 到 `CAUGHT_UP` 的语义，未新增 durable helper 专项单测；考虑到 helper 只是把原有逻辑从 `read_api.py` 下沉且完整 host 影响面测试已通过，风险低。
- 后续若新增其它 public read facade 需要 projection state，应继续通过对应 durable owner helper 暴露，不应从 facade 直接 import projection durable store。

## Completion

Phase 13 aggregate F001 fix 完成，等待 aggregate re-review。
