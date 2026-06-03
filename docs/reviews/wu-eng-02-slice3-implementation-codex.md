# WU-ENG-02 Slice 3 Implementation - Codex

## 动机判断

Slice 1/2 已在 Engine request identity 与 OpenAI-compatible Runner 映射中产生 `client_correlation_id`，但 Host 侧原本只稳定暴露 `provider_request_id`。这会导致 issue-70 analyzer 能从 provider native request id 查链路，却无法把同一次本地逻辑 Runner call 的 client correlation 一并串起来，问题真实存在。

最佳修复点仍是已有链路的字段透传：

- `RunInputBuilder` 把 Host attempt/execution identity 投影到 `AgentRunRequest`。
- `LLMContextCompactor` 在 reactive compaction request 上透传 attempt/execution identity，proactive request 保持 `None`。
- `EngineEventIngestor` 把 EngineEvent data 中已有的 `client_correlation_id` 写入已有 provider-related EventLog payload。
- `ToolTraceProjectionConsumer` 从 EventLog payload 抽取该字段并写入 summary JSON / cold JSONL。

这不是新的全局 tracing framework，也不需要新增 SQLite 表、列、索引或 migration。

## Stop Condition 处理

本轮开始前曾停止一次，原因是 terminal EventLog payload 真源在 `dayu/host/durable/run_transition.py`，而原 allowed files 未包含该文件。Controller 已核对该证据并扩范围允许 `dayu/host/durable/run_transition.py` 与相关测试，因此 Slice 3 可以继续实现。

本次实现没有修改 `docs/host/issues-implementation-control.md`，没有修改 README，没有修改 Engine contract。

## 变更文件

- `dayu/host/run_input.py`
- `dayu/host/llm_compaction.py`
- `dayu/host/engine_ingest.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/tool_trace.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `tests/host/test_run_attempt_transitions.py`

## 行为说明

- Ordinary Host dispatch 现在把 `AttemptDispatchSnapshot.attempt_id` / `execution_id` 传入 `AgentRunRequest`。
- Compactor request 现在复用 `CompactionRequest.attempt_id` / `execution_id`；reactive compaction 有值，proactive compaction 仍为 `None`。
- Provider-related ingest payload 现在同步写入 optional `client_correlation_id`，包括 provider protocol diagnostic、context compaction requested、context recovery close payload、recoverable run_failed diagnostic、run_failed terminal summary/payload，以及 iteration completed preview。
- `TerminalCloseoutInput` 与 `ContextRecoveryCloseInput` 增加 optional `client_correlation_id`，并沿用 `provider_request_id` 的 optional non-empty text 校验风格。
- Tool Trace 不新增 hot row 列或索引；`client_correlation_id` 进入 `trace_summary_json` 与 cold JSONL 的 `trace_summary`。cold JSONL 顶层也保留同名字段，便于直接检索诊断。
- 缺失或 `None` 的 `client_correlation_id` 合法；payload 中非文本值会按现有 Tool Trace payload validation 风格抛 `HostDurableError`。

## 验证结果

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_run_attempt_transitions.py tests/host/test_llm_compaction.py
```

结果：`184 passed in 1.37s`。

已运行：

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`。

## 未覆盖项 / Residual Risk

- 未跑全量测试；本 Slice 只运行了指定 Host 测试与新增受影响测试。
- 未覆盖远端 worker/proxy 真实传输路径；本 Slice 目标是 Host projection / ingest / Tool Trace 闭环，未改 wire protocol。
- README 同步按 accepted plan 留到 Slice 4，本轮未修改文档手册。

## 完成结论

Slice 3 implementation 完成。Host attempt/execution identity 已进入 Engine request；EngineEvent 中已有的 `client_correlation_id` 已进入 provider-related Host EventLog payload，并可由 Tool Trace summary / cold JSONL 暴露给 analyzer。
