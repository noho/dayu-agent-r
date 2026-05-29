# Repo Review Fix AgentCodex 20260529

## Scope

只修复 controller adjudication accepted blocking findings FR-F1..FR-F5。未实现 deferred findings；未扩大 public API；未引入 payload reader、timeline replay 或大重构。

## Root Cause 与修复

### FR-F1 Audit / Tool Trace JSONL 文件侧幂等

Root cause：Audit marker / Tool Trace hot row 属于 SQLite transaction，JSONL append 属于不可回滚文件副作用。进程在 JSONL 已写但 DB marker / hot row 未提交时退出，replay 会再次 append 同一 logical line。

修复：
- `LogAuditSink` 在同一文件锁保护下 append 前扫描目标 JSONL；命中同一 `line_digest` 时跳过 append，随后仍补写 marker。
- `LogAuditSink` 命中同一 `event_id` 但 `line_digest` 不同时抛 `HostDurableError`，由 projection runner 记录 failure，不补写 marker。
- `ToolTraceProjectionConsumer` 在同一文件锁保护下 append 前扫描目标 JSONL；命中同一 `line_digest` 时跳过 append，随后仍补写 hot row。
- `ToolTraceProjectionConsumer` 命中同一 `event_id` / `cold_trace_ref` 但 `line_digest` 不同时抛 `HostDurableError`，由 projection runner 记录 failure，transaction 回滚，不补写 hot row。
- JSONL 扫描只用于 sink-local 幂等，不读取 payload，不改变 EventLog / governance truth。

覆盖：
- `test_jsonl_existing_line_prevents_duplicate_when_marker_missing`
- `test_jsonl_source_key_digest_conflict_records_failure_without_marker`
- `test_projection_rebuild_from_event_log_restores_hot_rows`
- `test_cold_jsonl_source_key_digest_conflict_records_failure_without_hot_row`

### FR-F2 Outbox projection read state watermark

Root cause：`read_outbox_terminal_projection_state` 用全局 EventLog `MAX(event_sequence)` 判断 lag，导致 checkpoint 已追上 Outbox terminal facts 后，任意无关 EventLog tail 都会让 public read state 误报 `LAGGED`。

修复：
- 将比较水位改为最新 Outbox terminal canonical fact sequence，只包含 `RUN_SUCCEEDED` / `RUN_FAILED` / `RUN_CANCELLED` / `RUN_LOST` canonical facts。

覆盖：
- `test_projection_state_ignores_non_terminal_eventlog_tail`

### FR-F3 Outbox drain pending CAS

Root cause：drain 选出 item 后按 `item_id` 更新，缺少 `item_state = pending` CAS；不同 `drain_request_id` 可覆盖已 drained metadata。

修复：
- drain UPDATE 增加 `AND item_state = 'pending'`。
- CAS miss 抛出 `HostDurableError("outbox drain item pending CAS failed")`，当前 transaction 回滚，避免写入第二个 drain idempotency row 或覆盖 metadata。

覆盖：
- `test_drain_pending_cas_prevents_second_request_metadata_overwrite`
- public outbox API / offline smoke 回归测试

### FR-F4 SSE parser all invalid choices

Root cause：SSE chunk 中 `choices` 非空但所有元素都不是 object 时，旧逻辑只在 usage 也无效时才报 protocol error；合法 usage 会掩盖 provider choices 协议异常。

修复：
- 只要 `choices` 非空且没有任何 object choice，就立即产出 `provider_protocol_error` 并 `runner_done(error)` 收口。
- 不影响真正 usage-only chunk：无非空 choices、但 usage object 合法时仍只产出 usage 事件。

覆盖：
- `test_sse_all_non_object_choices_with_usage_protocol_error`
- 既有 `test_sse_usage_only_chunk_does_not_protocol_error`

### FR-F5 startup orphan recoverable closeout contract

Root cause：当前生产代码已有 validation 拒绝 `recoverable=True + expected_run_status != RUNNING`，但缺少 durable transition test 锁定该合约，无法防止后续回归。

修复：
- 补充 transition test，验证 `recoverable=True + expected_run_status=CANCELLING` 在 append EventLog 前被拒绝，且不写 `ATTEMPT_LOST`。

覆盖：
- `test_startup_orphan_recoverable_rejects_cancelling_expected_status`

## Validation

- `source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_durable.py tests/host/test_public_outbox_api.py tests/host/test_public_offline_outbox_smoke.py tests/engine/runners/openai/test_protocol_error.py tests/host/test_run_attempt_transitions.py`
  - 84 passed
- `source .venv/bin/activate && pyright`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - passed

## README 检查

命中 `dayu/host/` 与 `dayu/engine/` 修改触发条件。检查后未更新 README：本次只修复内部幂等、projection watermark、CAS 与 parser 协议错误判定，不改变 public API、命令、参数名、稳定架构边界或用户手册说明。

## 未覆盖风险

- JSONL 文件侧幂等需要扫描已有 JSONL；超大文件下 append 前扫描成本会随文件增长。当前修复优先满足 crash replay correctness，后续如需优化应设计 sink-local index，而不是把 projection 文件提升为 truth。
- FR-F3 对同一 cursor 的不同 drain request 在命中已 drained item 时会 fail fast；调用方应继续使用 terminal watermark / seen ids 推进 cursor。既有 public outbox 测试已覆盖当前稳定语义。
