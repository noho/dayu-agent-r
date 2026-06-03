# WU-ENG-02 Slice 4 Implementation Artifact

## Gate

- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice: Slice 4 - Documentation Sync And Final Validation
- artifact path: `docs/reviews/wu-eng-02-slice4-implementation-codex.md`
- allowed files touched: `dayu/engine/README.md`, `dayu/host/README.md`, `tests/README.md`, this artifact
- control doc: `docs/host/issues-implementation-control.md` was already dirty before this slice and was not modified by Codex

## 动机判断

动机成立。当前代码已经实现 Engine per-call `RunnerRequestIdentity`、OpenAI-compatible `X-Client-Request-Id` policy、Host Attempt/execution projection、EventLog ingest payload 与 Tool Trace summary/cold JSONL correlation；稳定 README 仍有旧 `AsyncRunner.call(messages, options, tools)` 形状和缺失的 client correlation 说明。文档同步是真实问题，不是未来设计补写。

本 Slice 不应修改根 README。核对后没有发现 CLI、config 或用户工作流变化；本次只同步开发手册和测试手册。

## README 变更

- `dayu/engine/README.md`
  - 更新 `AsyncRunner.call` 为 `call(messages, options, tools, *, request_identity)`。
  - 补充 `RunnerRequestIdentity`、`client_correlation_id`、`AgentRunRequest.attempt_id/execution_id`、`ClientCorrelationPolicy` 和 OpenAI-compatible `X-Client-Request-Id` 映射边界。
  - 明确 policy disabled 或 identity 缺失时不发送 header，静态 `X-Client-Request-Id` 冲突 fail fast，transport retry 复用同一个逻辑 call 的 client correlation。
- `dayu/host/README.md`
  - 补充 RunInputBuilder 把 `AttemptDispatchSnapshot.attempt_id/execution_id` 投影到 Engine request。
  - 补充 Engine ingest 在 provider-related EventLog payload 中保留 `provider_request_id` 与 `client_correlation_id`。
  - 补充 Tool Trace hot summary / cold JSONL 诊断可同时呈现 provider-native request id 与本地 client correlation id；未把 analyzer 未来能力写成当前行为。
- `tests/README.md`
  - 补充 Engine contract request identity、OpenAI header policy、Host effective config / RunInputBuilder / ingest / Tool Trace correlation 的测试覆盖说明。

## Residual Risk 复核建议

| id | 建议 | 证据与说明 |
| --- | --- | --- |
| WU-ENG-02-S1-R1 | 继续 deferred-with-owner：Engine / ToolRuntime timeout correlation owner | 工具批 duplicate / outcome mismatch 已把产生工具批的 Runner call `client_correlation_id` 写入 `RunFailedData`，但 `_make_tool_timeout_terminal_with_close()` 当前构造 `tool_execution_timeout` 时只含 `provider_request_id=None`，没有当前 call correlation。指定测试未提供工具超时类 `RunFailedData.client_correlation_id` 断言。 |
| WU-ENG-02-S1-R2 | 继续 deferred-with-owner，除非 Controller 接受现有间接覆盖 | 现有测试覆盖 force-answer 会产生第二次 logical Runner call，`runner_call_index == [1, 2]` 且第二次 `iteration_id` 正确；也覆盖 force-answer fail-closed 保留 `provider_request_id`。但没有直接断言 force-answer failure EngineEvent 的 `client_correlation_id` 等于第二次 request identity。若要关闭“EngineEvent correlation 断言”，建议后续补 focused Engine test。 |
| WU-ENG-02-S2-R1 | 建议关闭 | 当前 `ClientCorrelationPolicy.DISABLED` 是显式枚举值，RunnerSpec 测试锁定枚举值，OpenAI Runner 测试确认 disabled 即使有 identity 也不发送 `X-Client-Request-Id`，Host effective execution config 测试确认 enabled policy 可 freeze / restore。production assembly 默认 disabled 符合本 WU “显式 policy 才发送”验收。 |
| WU-ENG-02-S2-R2 | Engine adapter 部分建议关闭；上层结构化收口继续 deferred-with-owner：Service / config assembly | OpenAI Runner 已在 policy enabled 且静态 header 大小写冲突时抛 `ValueError`，测试确认不会发 HTTP 请求。当前没有证据显示上层已把该配置错误结构化收口为 Service-facing error；这不是 Slice 4 allowed scope，也不是 WU-ENG-02 的最小验收 blocker。 |
| WU-ENG-02-S3-R1 | 继续 deferred-with-owner：WU-OBS-00 analyzer | `UsageReportedData` 仍只携带 token usage 与 iteration id；Host usage observation 是 projection signal，带 attempt/execution、policy ref、estimator digest 和 observation digest，但不携带 `client_correlation_id`。是否把 usage observation 与 client correlation 关联属于 analyzer / observation 设计，不应在本 WU 强行扩展。 |
| WU-ENG-02-S3-R2 | 不作为当前 blocker；可保留为专用测试 residual | `ContextRecoveryCloseInput` 已有 `client_correlation_id` 字段、payload 写入和 optional non-empty text 校验；Engine ingest reactive context compaction 测试断言 request payload 包含 `client_correlation_id`、attempt_id 与 execution_id。当前没有看到直接针对 `ContextRecoveryCloseInput` RUN_RECOVERING payload 的专用单元测试。基于现有间接覆盖，我不认为 Slice 4 必须停止补测试；若 Controller 要关闭该 residual，应在允许测试文件的后续 slice 增加 focused test。 |

## 验证命令结果

```bash
source .venv/bin/activate && pytest tests/engine/contracts/test_runner_identity.py tests/engine/contracts/test_agent_run.py tests/engine/contracts/test_runner_spec.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/runners/openai/test_request_identity.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_http_error_event.py
```

结果：174 passed in 0.39s。

```bash
source .venv/bin/activate && pytest tests/host/test_effective_execution_config.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_run_attempt_transitions.py tests/host/test_llm_compaction.py
```

结果：198 passed in 1.51s。

```bash
source .venv/bin/activate && pyright
```

结果：0 errors, 0 warnings, 0 informations。pyright 仅提示可升级版本 `v1.1.409 -> v1.1.410`。

## 未覆盖项

- 未新增生产代码或测试代码；本 Slice 只做 README 同步、artifact 和验证。
- 未修改 `docs/host/issues-implementation-control.md`。
- 未做 code review、aggregate deepreview、commit、push、PR 或 merge。
- 工具超时 `RunFailedData` 是否需要当前 call `client_correlation_id`、force-answer failure EngineEvent 的直接 client correlation 断言、上层 static header conflict 结构化错误、usage observation 与 client correlation 的 analyzer 关联、`ContextRecoveryCloseInput` 专用测试，均按上表建议保留给对应 owner。

## 完成结论

Slice 4 文档同步和最终验证完成。README 只描述当前已实现行为，根 README 未修改；指定 Engine / Host 测试和 pyright 均通过。WU-ENG-02 的核心验收链路已由当前代码与测试覆盖：Engine request identity、OpenAI header policy、Host projection / ingest / Tool Trace correlation 均有直接实现和验证证据。剩余 residual risk 均已分类为建议关闭或 deferred-with-owner，不需要修改 control doc。
