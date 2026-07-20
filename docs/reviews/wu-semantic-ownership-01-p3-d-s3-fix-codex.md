# WU-SEMANTIC-OWNERSHIP-01 / P3-D / S3 Fix

执行者：AgentCodex  
Gate：fix after S3 code review  
Finding：P3-D-S3-CR-F01  
日期：2026-07-11

## Scope

只修 controller accepted finding：Agent 测试直接把 typed error code 与字符串字面量比较，无法证明字段未退化为裸字符串。

未进入 re-review / aggregate / PR；未 commit、未 push、未 PR、未 merge；未修改生产行为。

## 动机与 owner boundary 判断

该 finding 成立。`EngineRunErrorCode` 是 `StrEnum`，`RunnerSpecificErrorCode` 继承 `str`，因此 `error_code == "..."` 即使在字段退化为裸 `str` 时也会通过。该问题不是生产行为错误，而是 Engine / Agent 测试对 typed contract 的回归证明不足。

语义 owner boundary：

- Engine contract 是错误码类型真源：Engine-owned code 使用 `EngineRunErrorCode`，provider / runner 专有 code 使用 `RunnerSpecificErrorCode`。
- Runner adapter / Agent 是 typed code 产生与透传边界。
- Host ingest 是 typed code 到 durable/public text 的序列化边界。
- 本次修复落在 Engine/Agent 测试证明边界和弱类型守卫；不在 Host consumer、展示层或生产代码中补特例。

## 修复内容

### `tests/engine/test_agent_phase2.py`

新增两个测试 helper：

- `_assert_engine_run_error_code(...)`：断言 `actual is expected`，并通过 `serialize_engine_error_code(...)` 校验 durable text。
- `_assert_runner_specific_error_code(...)`：断言 `isinstance(actual, RunnerSpecificErrorCode)`、`actual.source is expected_source`，并通过 `serialize_engine_error_code(...)` 校验 serialized value。

替换的精确断言：

- `test_protocol_error_and_error_done_maps_to_run_failed`：`bad_sse` 改为断言 `RunnerSpecificErrorCode`、source `RUNNER_PROTOCOL`、serialized value `bad_sse`。
- `test_http_error_maps_to_run_failed_without_extra_engine_event`：`rate_limit_exceeded` 改为断言 `RunnerSpecificErrorCode`、source `ADAPTER`、serialized value `rate_limit_exceeded`。
- `test_context_overflow_http_error_maps_to_compaction_required_fact`：`context_compaction_required` 改为断言 enum identity `EngineRunErrorCode.CONTEXT_COMPACTION_REQUIRED` 与 serialized value。
- `test_context_overflow_marker_fallback_emits_nonfatal_diagnostic`：`context_compaction_required` 改为断言 enum identity `EngineRunErrorCode.CONTEXT_COMPACTION_REQUIRED` 与 serialized value。
- `test_bare_error_done_maps_to_specific_run_failed`：`runner_error_done_without_detail` 改为断言 enum identity `EngineRunErrorCode.RUNNER_ERROR_DONE_WITHOUT_DETAIL` 与 serialized value。
- `test_runner_exception_maps_to_run_failed_and_closes`：`runner_exception` 改为断言 enum identity `EngineRunErrorCode.RUNNER_EXCEPTION` 与 serialized value。
- `test_tool_call_delta_and_completed_fail_closed`：`runner_abnormal_stop` 改为断言 enum identity `EngineRunErrorCode.RUNNER_ABNORMAL_STOP` 与 serialized value。
- `test_abnormal_stop_and_max_iterations_fail`：`runner_abnormal_stop` 改为断言 enum identity `EngineRunErrorCode.RUNNER_ABNORMAL_STOP` 与 serialized value。
- `test_run_agent_and_wait_preserves_provider_request_id`：`provider_http_error` 改为断言 `RunnerSpecificErrorCode`、source `ADAPTER`、serialized value `provider_http_error`。

### `tests/engine/test_weak_typing_guard.py`

新增精确 guard：

- `_contains_error_code_attribute(...)`：识别表达式中是否读取 `.error_code`。
- `test_agent_tests_do_not_compare_typed_error_codes_to_literal_strings`：只扫描 `tests/engine/test_agent_phase2.py`，禁止 `.error_code` 与字符串字面量直接 `==` / `!=` 比较。

该 guard 只约束 Agent typed error-code 行为测试，不扫描 Host durable text 或其它非 typed 语义，避免 brittle broad scan。

## 传播审计

1. Provider / runner 专有错误码由 adapter 或测试 fixture 通过 wrapper constructor 产生。
2. Agent 测试断言 `RunFailedData.error_code` / `EngineRunOutcomeFailed.error_code` 保持 typed union，而不是只断言字符串相等。
3. Engine-owned failure code 测试通过 enum identity 证明仍是 `EngineRunErrorCode` 真源。
4. Runner-specific failure code 测试通过 wrapper type、source 与 serializer 证明仍是 `RunnerSpecificErrorCode` 真源。
5. Host durable/public 边界仍由 `serialize_engine_error_code(...)` 表示；本次只在测试中复用 serializer 校验 serialized value，未改变 Host ingest。
6. 弱类型守卫防止后续 Agent 行为测试回退到 `.error_code == "..."`，不会影响 memory、compact、evidence、LLM-facing prompt 或 Host projection。

## README / docs 决策

- `tests/README.md`：已检查。该文件记录测试分层、运行方式与维护约定；本次未新增测试层级、运行方式或测试目录职责，只加强既有 Engine 测试断言与局部 guard，因此不更新。
- `dayu/engine/README.md` / `dayu/host/README.md` / 根 README / `dayu/README.md`：本次未改 production contract、分层关系、Host 边界、用户入口或最终用户工作流，因此不更新。
- 本 fix artifact 记录本 gate 的 durable 证据。

## 验证

- `source .venv/bin/activate && pytest tests/engine/test_agent_phase2.py tests/engine/test_weak_typing_guard.py -q`
  - 结果：`72 passed in 0.36s`
- `source .venv/bin/activate && pytest tests/engine/contracts tests/engine/test_engine_event_contract.py tests/engine/test_package_exports.py tests/engine/test_agent_phase2.py -q`
  - 结果：`149 passed in 0.23s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。

## Finding 状态

P3-D-S3-CR-F01：已修复。

## Residual Risk

- S3 intentional string-only constructor break 保持原 accepted residual risk，本次不改变。
- Provider-specific wrapper source 仍只在 Engine typed wrapper 内可见，Host durable/public projection 仍是 serialized text；如未来需要公开 source，需要新的 Engine/Host public contract。
