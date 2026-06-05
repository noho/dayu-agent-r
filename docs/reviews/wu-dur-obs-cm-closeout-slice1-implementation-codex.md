# WU-DUR / WU-OBS / WU-CM Closeout Slice 1 Implementation

## slice/status

- slice: implementation Slice 1 - durable tool-call request atoms
- status: complete
- agent: AgentCodex
- scope: 未进入 Slice 2-7、review/fix/commit/push/PR 或其它 gate

## changed files

- `dayu/host/durable/schema.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/payload_resolution.py`
- `dayu/host/README.md`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_durable_schema.py`
- `tests/README.md`
- `docs/reviews/wu-dur-obs-cm-closeout-slice1-implementation-codex.md`

## implementation summary

- 为 `TOOL_CALL_REQUESTED` accepted fact 增加 durable request atom：accepted canonical arguments JSON、arguments digest、storage kind、payload descriptor ref，以及 optional semantic query storage/digest 字段。
- ToolRuntime 生产路径从 `ToolCallRequest.arguments` 显式传入 `ToolAcceptCall.accepted_arguments`，并用同一个 canonical preimage 计算 `normalized_arguments_digest` 与 `arguments_payload_digest`。
- 小参数按 `payload_inline_threshold_bytes` 内联到 EventLog hot payload；大参数写 SQLite payload descriptor，metadata `descriptor_kind=tool_call_arguments_json`。
- optional semantic query 缺失时记录 `semantic_query_storage_kind=absent`；短文本 inline；长文本写 SQLite payload descriptor，metadata `descriptor_kind=tool_call_semantic_query_text`。
- 新增 `payload_resolution.tool_call_request_atoms()` typed reader，解析并校验 inline / descriptor arguments、semantic query、descriptor kind、payload digest、size 与 normalized digest；不一致时 fail-closed 抛 `HostDurableError`。
- Engine ingest 的 `TOOL_CALL_REQUESTED` preview 只补 normalized arguments digest 诊断信号，不把 preview 变成 truth。
- Tool Trace 测试覆盖大参数 descriptor 不展开进 cold JSONL；未修改 `dayu/host/tool_trace.py`，避免越过本 slice allowed files。
- `dayu/host/_event_payload.py` 未修改；当前实现不需要新增 EventLog inline payload helper。

## design contract mapping

- `TOOL_CALL_REQUESTED` 作为工具调用 intent 与 accepted arguments 的同源 durable atom：已落地在 ToolRuntime accepted event payload。
- `arguments_payload_digest` 与 `normalized_arguments_digest` 使用同一 canonical normalization preimage：`{"arguments": ...}`，写入前和读取时均校验。
- `arguments_storage_kind` 仅使用 `inline_json` / `payload_descriptor`；超过阈值写 descriptor kind `tool_call_arguments_json`。
- semantic query 独立于 `semantic_input_digest`：字段支持 `absent` / `inline_text` / `payload_descriptor`，长文本 descriptor kind 为 `tool_call_semantic_query_text`。
- 不使用 extra payload、provider raw dict 或 prompt/tool behavior 猜测 arguments：生产路径只从 typed `ToolCallRequest.arguments` 进入 typed accept candidate。
- 未改变 ToolRuntime accept/governance 状态语义：只扩展 accepted fact payload 与读取 helper。
- fresh schema only：只新增 descriptor kind 常量，不增加旧库兼容读取。

## tests run

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_durable_schema.py`
  - result: 117 passed
- 额外回归检查：`source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py`
  - result: 23 passed

## pyright

- `source .venv/bin/activate && pyright`
  - result: 0 errors, 0 warnings, 0 informations

## README/docs decision

- 更新 `dayu/host/README.md`：记录 `TOOL_CALL_REQUESTED` accepted request atom、arguments / semantic query 冷热分离与 payload descriptor kind。
- 更新 `tests/README.md`：记录新增 Host 测试覆盖事实，包括 Engine preview digest、ToolRuntime request atom 与 Tool Trace 大参数 descriptor 边界。
- 未更新根 README：未改变用户命令、CLI、trace/render 入口或项目级使用方式。

## remaining risks

- `ToolAcceptCall.accepted_arguments` 对 fake ack 低层测试允许缺省；实际写入 `TOOL_CALL_REQUESTED` accepted fact 时仍强制要求存在并校验 digest。后续若要把该字段改成无默认必填，需要同步更新所有低层测试 fake ack helper，超出本 slice allowed files。
- Tool Trace 当前只验证不会展开大参数正文；新增 atom ref/digest 的 hot projection signal 未在本 slice 修改 `dayu/host/tool_trace.py`，应由后续 Slice / OBS 范围处理。
- Compact evidence 的 `query_text` 消费尚未接入 `tool_call_request_atoms()`，属于后续 Slice。

## next slice readiness

- 后续 compact query_text / runner-call manifest / Tool Trace signal 可以通过 `payload_resolution.tool_call_request_atoms(transaction, event)` 读取 accepted arguments 与 optional semantic query。
- 大参数与长 semantic query 已有稳定 descriptor kind 和 digest 校验边界，可作为后续 projection / analyzer 的 durable input。
