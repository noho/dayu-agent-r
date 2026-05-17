# P9.5 S13 Message / Tool Result Size Governance Implementation

## Motivation Judgment

动机成立。`docs/host/design.md` 已明确 EventLog `canonical_fact` 不应内嵌大 payload，大工具结果、完整 prompt/messages、trace 明细等必须通过 payload/artifact/ref/digest 边界治理。当前实现已有 payload descriptor、tool truncation、`fetch_more`、ToolRuntime accept barrier 与 Engine `context_compaction_required` 表达，但缺少统一的 inline 大小防线，存在大内容直接进入 EventLog canonical inline payload、ToolRuntime 返回给 Engine 的 tool message、以及 `fetch_more` continuation 的风险。

严重性没有被高估：这不是 P10 proactive compaction 或 provider tokenizer 问题，而是 P10 前必须先收口的 Host / Engine 边界防御。实现没有新增 public error code/detail，没有引入 durable cursor table、tool trace projection、业务 payload 规则或兼容逻辑。

## Inventory

- Payload inline 默认值：`dayu.host.durable.options._DEFAULT_PAYLOAD_INLINE_THRESHOLD_BYTES = 65536`，`PayloadStoragePolicy.payload_inline_threshold_bytes` 可覆盖；现有 `tests/host/test_payload_store.py` 已覆盖默认值与覆盖。
- Public read limits：`HOST_EVENT_STREAM_DEFAULT_LIMIT = 100`，`HOST_EVENT_STREAM_MAX_LIMIT = 1000`，本 slice 未修改。
- Wait/public 字段最大长度：`HOST_WAIT_*_MAX_LENGTH` 系列，和本 slice 无直接关系，未修改。
- ToolRuntime 现有 defaults：accept retry `2`、backoff `0.0`、truncation TTL `600`、fetch_more limit 仅要求正数；本 slice 复用 payload inline 默认阈值作为 LLM inline tool result 最大字节数。
- Engine 现有 size-ish 常量：异常消息脱敏长度 `_EXCEPTION_MESSAGE_MAX_LENGTH = 240`；无 Engine message inline 上限。本 slice 添加私有防御常量 `_MAX_ENGINE_MESSAGE_CONTENT_BYTES = 65536`，不导出为 public contract。
- 现有错误/诊断表达：
  - Host public `HostApiErrorDetail` 只有 `SteerConflictDetail`，无法表达 size limit。本 slice未新增 public detail/code。
  - Durable payload/ref 错误已有 `HostPayloadReferenceError`，用于 EventLog canonical inline 超限拒绝。
  - ToolRuntime 已有 governed tool failure 与 `ToolTraceDiagnosticEmitter` typed diagnostic ref，本 slice 用 `tool_result_inline_size_limit_exceeded` 作为内部 reason code。
  - Engine 已有 `context_compaction_required` recoverable failure，本 slice复用它表达防御性 message inline 超限。

## Changed Files

- `dayu/host/durable/event_log.py`
  - 对 `canonical_fact` 的 canonical `payload_json` 增加 UTF-8 字节上限检查。
  - 超限抛出既有 `HostPayloadReferenceError`，提示调用方使用 `payload_ref` / `payload_digest`。
- `dayu/host/tool_runtime.py`
  - 对返回给 Engine 的 tool outcome 增加 inline 字节上限治理。
  - 超限普通工具结果转为 governed failure，并发出 ToolRuntime diagnostic ref。
  - 截断后的 visible result 与 `fetch_more` continuation 同样不能超过 inline 上限；超限返回普通 truncation tool error。
- `dayu/engine/agent.py`
  - Runner 调用前检查 `AgentMessage` inline 文本字段大小。
  - 超限时复用 `context_compaction_required` recoverable failure，要求上游通过 ref/digest/payload/compact artifact 边界重建有界 messages。
  - Code review fix 后，Assistant tool call 的 id / name / arguments / provider_state 也纳入回送 Runner 的 inline 边界检查。
- `tests/host/test_event_log_store.py`
  - 新增 canonical fact oversized inline payload 拒绝测试。
- `tests/host/test_toolruntime_executor.py`
  - 新增 oversized tool result governed diagnostic outcome 测试。
  - 新增 oversized `fetch_more` continuation 拒绝测试。
- `tests/engine/test_agent_message_union.py`
  - 新增 Engine oversized message defensive failure 测试。
  - Code review fix 后，新增 oversized Assistant tool call arguments defensive failure 测试。
- `tests/engine/test_agent_phase3_tool_call.py`
  - Code review fix 后，新增工具结果注入 messages 后、下一轮 Runner 调用前被 inline guard 拦截的集成测试。
- `dayu/host/README.md`
  - 同步 EventLog canonical inline payload limit 与 ToolRuntime result/fetch_more size governance。
- `dayu/engine/README.md`
  - 同步 Engine message inline size defensive check。
- `tests/README.md`
  - 同步新增测试覆盖说明。

## Tests Added Or Credited

- Added:
  - `test_canonical_fact_rejects_oversized_inline_payload_json`
  - `test_oversized_tool_result_returns_governed_diagnostic_outcome`
  - `test_fetch_more_rejects_oversized_inline_continuation`
  - `test_oversized_engine_message_content_requires_context_boundary`
  - `test_oversized_assistant_tool_call_arguments_require_context_boundary`
  - `test_oversized_tool_message_fails_before_next_runner_call`
- Credited existing:
  - `test_default_payload_inline_threshold_can_be_overridden`
  - Existing EventLog payload ref/digest validation tests.
  - Existing ToolRuntime accept barrier tests proving rejected/timeout paths do not expose raw results.
  - Existing RunInputBuilder tests proving current prompt and continuity come from durable canonical facts / memory budget boundaries.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_payload_store.py tests/host/test_event_log_store.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py tests/engine/test_agent_message_union.py`
  - Result before review fix: 74 passed.
- `source .venv/bin/activate && pytest tests/engine/test_agent_message_union.py tests/engine/test_agent_phase3_tool_call.py::test_oversized_tool_message_fails_before_next_runner_call`
  - Result after review fix: 9 passed.
- `source .venv/bin/activate && pytest tests/host/test_payload_store.py tests/host/test_event_log_store.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py tests/engine/test_agent_message_union.py tests/engine/test_agent_phase3_tool_call.py`
  - Result after review fix: 115 passed.
- `source .venv/bin/activate && pytest tests/host tests/engine`
  - Result after review fix: 913 passed.
- `source .venv/bin/activate && python -m pyright dayu tests`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: passed.

## Docs Decision

README update was required by the project rules because this slice touched `dayu/host/`, `dayu/engine/`, and `tests/`. Updates were limited to current behavior:

- Host README now documents canonical inline payload size governance and ToolRuntime result/fetch_more inline size governance.
- Engine README now documents defensive Engine message inline size checks.
- Tests README now documents the added coverage.

No future design, migration note, version log, or process status was added.

## Residual Risks

- The inline byte limit is aligned with the existing default payload inline threshold. Per-handle custom `payload_inline_threshold_bytes` is still applied at durable store construction, but EventLog and ToolRuntime internal defensive checks do not currently receive per-handle threshold injection without changing wider construction wiring.
- ToolRuntime still does not materialize oversized tool results into a durable artifact automatically. This slice rejects/governs oversized inline return paths and requires tools or later phases to provide payload/artifact refs.
- Engine message check is byte-count based and provider-neutral. It intentionally does not implement provider tokenizer or proactive compaction.
- Existing Host public error detail union cannot express a public size-limit error. This slice stayed on durable errors / tool diagnostic outcome / existing Engine failure code as required.

## Stop Status

Implementation complete for S13 within the allowed files. No public error code/detail was added. No review, commit, push, PR, durable cursor table, Tool Trace projection, provider tokenizer, proactive compaction, or business-specific payload rule was introduced.
