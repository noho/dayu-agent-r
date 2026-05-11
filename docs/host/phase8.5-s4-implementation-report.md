# P8.5 Slice 4 Implementation Report

- Work gate: `implementation`
- Work unit: P8.5 — P8 Stabilization / ToolRuntime Event Model
- Assigned slice: P8.5 Slice 4 — Compact / RunInput / SSE Partial Semantic Cleanup
- Approved plan: `docs/host/phase8.5-plan.md`
- Branch: `migration/host-p8-5-stabilization`

## Assigned Scope

本 slice 只处理 compact / RunInput / SSE partial semantic cleanup：

- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 移除无界 inline raw payload，只保留 summary、blob id、sha256、byte size。
- 新增 Host durable raw payload side-store：`run_input_raw_payloads`。
- side-store 两类 payload 与 EventLog fact append 必须共享同一个 `HostStorage.transaction()`。
- projection / debug read path 必须校验 missing row、hash mismatch、byte size mismatch、invalid JSON、kind mismatch，并以 typed failure 阻断 checkpoint。
- compact retry attempt / iteration 语义保持：Host attempt index retry 后递增，retry attempt 首轮 iteration index 为 `0`，iteration id 由 `run_id + attempt_index` 派生。
- provider protocol error 扩展 bounded `partial_tool_calls` summary，不新增 provider-specific RunEventType，不驱动工具执行。
- analyzer 展示 provider protocol error 的 partial tool call diagnostic。

## Changed Files

- Host contracts / serialization / write path:
  - `dayu/host/contracts.py`
  - `dayu/host/_run_event_serializer.py`
  - `dayu/host/_run_input_context_fact.py`
  - `dayu/host/_run_input_raw_payload_store.py`
  - `dayu/host/_run_harness.py`
  - `dayu/host/_durable_event_store.py`
  - `dayu/host/_durable_harness.py`
- Host trace projection / sink:
  - `dayu/host/_tool_trace_projection.py`
  - `dayu/host/_tool_trace_jsonl_sink.py`
- Engine provider protocol diagnostics:
  - `dayu/engine/contracts/partial_tool_call.py`
  - `dayu/engine/contracts/runner_events.py`
  - `dayu/engine/contracts/engine_events.py`
  - `dayu/engine/contracts/__init__.py`
  - `dayu/engine/__init__.py`
  - `dayu/engine/runners/openai/tool_call_aggregator.py`
  - `dayu/engine/runners/openai/sse_parser.py`
  - `dayu/engine/agent.py`
- Analyzer:
  - `utils/analyze_tool_trace_host.py`
- Tests:
  - `tests/host/test_phase4_overflow_retry.py`
  - `tests/host/test_phase7_run_input_context_fact.py`
  - `tests/host/test_phase7_contract_serializer.py`
  - `tests/host/test_phase7_tool_trace_projection.py`
  - `tests/host/test_phase7_schema_bootstrap.py`
  - `tests/engine/runners/openai/test_protocol_error.py`
  - `tests/utils/test_analyze_tool_trace_host.py`
- Docs:
  - `README.md`
  - `dayu/host/README.md`
  - `dayu/engine/README.md`
  - `tests/README.md`

## Plan Items Implemented

- `RunInputContextSnapshotBuiltData` 删除 `raw_input_messages_json` / `raw_tool_schemas_json`，新增两类 raw payload 的 blob id、sha256、byte size 字段。
- 新增 `run_input_raw_payloads` schema，包含 plan 固定 columns、payload kind constraint、unique `(run_id, attempt_index, iteration_index, payload_kind)` 与 `(session_id, run_id)` index。
- 新增 writer / reader API：
  - writer 在当前 `HostStorageTransaction` 内写入 `input_messages` 与 `tool_schemas` 两类 payload。
  - reader 按 EventLog hot fact ref 读取并校验 kind、hash、byte size、JSON。
- `LocalRunHarness._append_run_input_context_snapshot_fact` 在同一个 `HostStorage.transaction()` 内先写 side-store，再 append EventLog fact；若事务回滚，side-store 不残留 orphan row。
- `ToolTraceObserver` 不再从 EventLog hot row 读取 inline raw JSON，改为读取 side-store；校验失败抛 `ProjectionSchemaError`，因此 required read path 不会推进 checkpoint。
- compact CAS miss 测试补充：compact success diagnostic 已落库时，terminal close fencing miss 不得写 stale Host terminal，保持唯一 terminal truth。
- Engine / Runner provider protocol error data 增加 `PartialToolCallSummary` bounded summary；OpenAI SSE parser 在 invalid UTF-8、invalid JSON、payload not object、usage malformed 这些 protocol failure 上携带当前 partial tool call summary。
- Agent 将 Runner partial summary 提升到 `ProviderProtocolErrorData`；Host serializer、trace projection 和 analyzer 同步支持该字段。
- analyzer 增加 `provider_partial_tool_calls` 诊断与格式化输出，不包含 raw argument payload。

## Validation

全部指定验证已通过：

```bash
source .venv/bin/activate && python -m pyright dayu/engine/ dayu/host/ tests/engine/ tests/host/
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/host/test_phase4_overflow_retry.py tests/host/test_phase7_run_input_context_fact.py tests/host/test_phase7_contract_serializer.py -q
# 25 passed

source .venv/bin/activate && pytest tests/host/test_phase7_tool_trace_projection.py -q
# 16 passed

source .venv/bin/activate && pytest tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_event_flow_ordering.py -q
# 13 passed

source .venv/bin/activate && pytest tests/utils/test_analyze_tool_trace_host.py -q
# 17 passed
```

额外验证：

```bash
source .venv/bin/activate && python -m pyright utils/analyze_tool_trace_host.py tests/utils/test_analyze_tool_trace_host.py
# 0 errors, 0 warnings, 0 informations

source .venv/bin/activate && pytest tests/host/test_phase7_schema_bootstrap.py -q
# 2 passed
```

## Documentation Decision

- 已更新 Host README：说明 `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` hot row 只保存 bounded refs，完整 raw payload 在 `run_input_raw_payloads`，projection 读取并校验后写 trace raw payload 文件。
- 已更新 Engine README：说明 provider protocol error 上的 `partial_tool_calls` bounded summary 语义。
- 已更新 tests README：记录 side-store rollback / failure path 与 analyzer partial diagnostic 覆盖。
- 已更新根 README 的 Host durable trace 说明，避免继续描述 inline raw payload。

## Residual Risks And Uncovered Areas

- Current-slice fixed: raw payload orphan row、hash mismatch、kind mismatch、corrupt JSON、missing row、SSE partial diagnostic、compact diagnostic success + terminal close fencing miss 均已有测试覆盖。
- Accepted as covered by later slice / phase: provider stream transport-layer read failure 目前仍走 HTTP error 语义，本 slice 只覆盖 provider protocol error data；未引入 provider-specific RunEventType。
- Residual risk classification: low。主要剩余风险是更复杂 provider delta 形态的 partial summary 覆盖面，属于后续 provider adapter 扩展测试范围，不阻塞 Slice 4。

## Completion Signal

Slice 4 implementation complete。EventLog hot row 已移除 unbounded raw payload；side-store 与 EventLog append 保持原子；typed projection failure 会阻断 trace projection；SSE partial diagnostic 可进入 Host trace / analyzer。

## Stop Condition Status

- Need provider-specific RunEventType: not triggered。
- Need old row compatibility reader: not triggered。
- Cannot make raw side store and EventLog append atomic in P8.5 scope: not triggered。
