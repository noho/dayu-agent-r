# PR #42 Step 1 修复报告 - 2026-05-11

## 执行边界

- 分支：`migration/host-p8-5-stabilization`
- 当前 gate：PR review fix - Step 1
- 本轮角色：实现 Step 1 修复，不作为 Gateflow controller。
- 明确未执行：未启动 `$gateflow` / `/gateflow`，未重新制定 plan，未 commit、push、更新 PR、merge 或 closeout。
- 受保护输入：`docs/host/design.md` 中 controller 已写入的 EngineWorker/schema projection 设计更新未被本轮编辑或重新解释。

## 输入 review artifacts

- `docs/reviews/code-review-20260511-1658.md`
- `docs/reviews/code-review-20260511-1718.md`
- `docs/reviews/code-review-20260511-1719.md`
- `docs/reviews/pr-42-review-20260511-1547.md`
- `docs/reviews/pr-42-review-20260511-1552.md`
- `docs/reviews/pr-42-review-20260511-1554.md`
- `docs/reviews/code-review-20260511-1607.md`
- `docs/reviews/pr-42-fix-report-20260511.md`
- `docs/reviews/pr-42-fix-rereview-20260511.md`

## Controller 决策落实

- Step 1 只修 accepted PR review bugs，排除“schema 双重增强入口” ownership。
- Step 2 负责实现 `docs/host/design.md` 中新的 EngineWorker/schema projection 设计，并自然修复 schema 双重增强问题。
- 未实现 raw payload/chat history 保留与删除策略；该项归属 GitHub issue #43。
- 未实现 P8.6 recovery model、P15 hard-gate/watchdog、P16 interface freeze、cursor persistent SQLite store、repair TOCTOU、BEGIN IMMEDIATE scan redesign、`_NeverCancelledToken` cancellation design 或 task-aware stream drain redesign。

## 逐项修复状态

| Finding | 状态 | 处理说明 | 覆盖测试 |
| --- | --- | --- | --- |
| 1. `start_run` admission 半提交 | 已修复 | 在 `USER_INPUT_ACCEPTED` 前对当前 schema preflight 失败做拒绝；首个 attempt admission/acquire 失败时写 Host-owned terminal `RUN_FAILED`，避免已接纳输入无终态。未处理 Step 2 的 schema projection ownership。 | `tests/host/test_phase2_tool_runtime_boundary.py::test_start_run_rejects_fetch_more_schema_before_user_input_event`；`tests/host/test_phase8_attempt_supervisor.py::test_start_run_initial_attempt_busy_writes_terminal_failure` |
| 2. ToolTrace request/result checkpoint safety | 已修复 | `ToolTraceObserver` 在 fresh instance 收到 `TOOL_RESULT_ACCEPTED` 且内存无 pending request 时，从 durable EventLog 回查 checkpoint 前的 `TOOL_REQUESTED`，不引入新的 persistent side-store。 | `tests/host/test_phase7_tool_trace_projection.py::test_tool_call_pairing_survives_checkpoint_restart` |
| 3. Provider / Run failure credential scrub | 已修复 | 持久化与 trace 路径清洗 `ProviderProtocolErrorData.message`、`ProviderProtocolErrorData.raw_payload`、`RunFailedData.message` 中的显式凭证。普通 tool payload 仍保留，仅清洗显式凭证。 | `tests/host/test_phase6_run_event_serializer.py::test_run_failed_message_scrubs_explicit_credentials`；`tests/host/test_phase6_run_event_serializer.py::test_provider_protocol_error_scrubs_message_and_raw_payload`；`tests/host/test_phase7_tool_trace_projection.py::test_provider_protocol_error_scrubs_message` |
| 4. `_resolve_ttl_seconds(float("inf"))` | 已修复 | 非 finite timeout 不再 `int()`，回落默认 TTL。 | `tests/host/test_phase2_tool_runtime_truncation.py::test_infinite_timeout_uses_default_cursor_ttl` |
| 5. `PartialToolCallSummary.tool_call_id` 无界 | 已修复 | 保留显式 contract 字段名，将 provider-controlled `tool_call_id` 限制为 `PARTIAL_TOOL_CALL_ID_MAX_CHARS = 128`。 | `tests/engine/runners/openai/test_protocol_error.py::test_sse_partial_tool_call_summary_bounds_tool_call_id` |
| 6. Host deserializer 缺失 `partial_tool_calls` 未 fail-fast | 已修复 | `PROVIDER_PROTOCOL_ERROR` 反序列化时要求字段显式存在；显式空列表仍表示 empty。 | `tests/host/test_phase6_run_event_serializer.py::test_provider_protocol_error_requires_partial_tool_calls_field` |
| 7. compact retry snapshot failure 无 terminal | 已修复 | compact retry 新 attempt 已 acquire 后，context snapshot 失败会写 terminal `RUN_FAILED`；fencing 失败保持 owner-lost 语义。 | `tests/host/test_phase4_overflow_retry.py::test_durable_compact_retry_snapshot_failure_writes_terminal` |
| 8. `FrameworkToolSet._fetch_more` 死代码误导 | 已修复 | schema callable 改为显式 `AssertionError`，说明必须由 HostToolRuntime 拦截；运行行为不变。 | `tests/host/test_phase8_5_framework_tools.py::test_framework_fetch_more_callable_fails_fast_when_not_intercepted` |
| 9. `ToolCallRecord` 旧 cursor/fetch_more 字段 | 已修复 | 删除六个 forever-None 旧字段；analyzer 保持忽略 legacy JSONL 字段；未恢复旧 special RunEvents。 | `tests/utils/test_analyze_tool_trace_host.py` |
| 10. 已接受 test gaps | 已补齐当前 Step 1 仍相关覆盖 | 增加 `_engine_visible_request` 直接测试、`verify_active_owner` 成功/失败测试、binary `bytearray` 覆盖、Host serializer partial tool call roundtrip/fail-fast 覆盖；terminal fetch_more 已由既有 host eventlog 测试覆盖。 | `tests/host/test_phase2_tool_runtime_boundary.py`；`tests/host/test_phase8_attempt_fencing.py`；`tests/host/test_phase2_tool_runtime_truncation.py`；`tests/host/test_phase6_run_event_serializer.py` |
| 11. low-risk cleanup | 已完成适合 Step 1 的部分 | 删除 `ToolValueSizeSummary`；`_collect_tool_call` 改为 emit 前 pop；移除 `_build_cursor_from_record(request=...)` 参数；`extract_truncation_hint(has_more=False)` 不再产生空 hint；`_append_overflow_observed` 改为 `elif`；`scrub_tool_execution_outcome` 增加 `assert_never`。credential regex 收紧与 full sha256 blob_id 未改，避免无直接证据扩大行为面。 | focused tests + required suites |

## 变更文件

生产代码：

- `dayu/engine/contracts/partial_tool_call.py`
- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `dayu/host/__init__.py`
- `dayu/host/_conversation_memory.py`
- `dayu/host/_credential_scrub.py`
- `dayu/host/_durable_event_store.py`
- `dayu/host/_durable_harness.py`
- `dayu/host/_event_translation.py`
- `dayu/host/_framework_tools.py`
- `dayu/host/_run_event_serializer.py`
- `dayu/host/_run_harness.py`
- `dayu/host/_runtime_truncate_manager.py`
- `dayu/host/_tool_result_truncation.py`
- `dayu/host/_tool_trace_jsonl_sink.py`
- `dayu/host/_tool_trace_projection.py`
- `dayu/host/contracts.py`

测试：

- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/host/test_host_public_api_surface.py`
- `tests/host/test_phase1_public_boundary.py`
- `tests/host/test_phase2_tool_runtime_boundary.py`
- `tests/host/test_phase2_tool_runtime_truncation.py`
- `tests/host/test_phase4_overflow_retry.py`
- `tests/host/test_phase6_run_event_serializer.py`
- `tests/host/test_phase7_tool_trace_projection.py`
- `tests/host/test_phase8_5_framework_tools.py`
- `tests/host/test_phase8_attempt_fencing.py`
- `tests/host/test_phase8_attempt_supervisor.py`
- `tests/utils/test_analyze_tool_trace_host.py`

文档：

- `dayu/engine/README.md`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/pr-42-step1-fix-report-20260511.md`

## 验证结果

- `source .venv/bin/activate && pytest tests/engine/runners/openai/test_protocol_error.py tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase2_tool_runtime_eventlog.py tests/host/test_phase4_overflow_retry.py tests/host/test_phase6_run_event_serializer.py tests/host/test_phase7_tool_trace_projection.py tests/host/test_phase8_5_framework_tools.py tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_supervisor.py tests/utils/test_analyze_tool_trace_host.py -q`
  - 结果：`165 passed in 0.74s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/contracts tests/engine -q`
  - 结果：`328 passed in 1.10s`
- `source .venv/bin/activate && pytest tests/host -q`
  - 结果：`418 passed in 2.65s`
- `source .venv/bin/activate && pytest tests/utils/test_analyze_tool_trace_host.py -q`
  - 结果：`18 passed in 0.05s`
- `git diff --check`
  - 结果：通过，无输出。

## 残余风险与 owner

- schema 双重增强入口：blocked-by-Step-2；由 Step 2 的 EngineWorker/schema projection 设计实现负责。
- raw payload/chat history retention/delete policy：GitHub issue #43。
- recovery model 变更：P8.6。
- hard-gate/watchdog 与 required projection 语义：P15。
- public/internal interface freeze 与后续边界冻结：P16。
- credential regex 收紧：本轮未在无 false negative 证据下扩大匹配规则。
- full sha256 blob_id：本轮未修改，避免把低风险 cleanup 扩成 payload ref 行为变更。

## Stop Condition 状态

- 未实现新的 EngineWorker explicit schema projection design。
- trace checkpoint safety 未引入新的 persistent side-store schema，仅复用 durable EventLog 回查。
- compact retry terminal close 已在当前生命周期语义内收口，未触发 P9 lifecycle 决策阻断。
- 未实现 raw payload/chat history retention/delete policy。
- 未 commit、push、merge、更新 PR state 或 closeout。
