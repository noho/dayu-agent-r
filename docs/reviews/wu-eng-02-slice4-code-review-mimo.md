# WU-ENG-02 Slice 4 Code Review - AgentMiMo

## Gate

- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice: Slice 4 - Documentation Sync And Final Validation
- reviewer: AgentMiMo
- artifact path: `docs/reviews/wu-eng-02-slice4-code-review-mimo.md`
- review scope: README 同步准确性、residual risk 复核建议合理性、验证命令覆盖

## Verdict

**pass**

## Findings

### Severity: info

| ID | 文件 | 行号 | 描述 | 影响 | 建议 |
|---|---|---|---|---|---|
| F-1 | dayu/host/README.md | 275 | `client_correlation_id` 在 hot row 中只存在于 `trace_summary_json` JSON blob 内，不是独立查询列。README 描述"hot row 仍只把 `provider_request_id` 作为查询列"准确，但可以更明确说明 `client_correlation_id` 的存储位置差异。 | 无功能影响，仅文档精确度 | 保持现状或后续微调措辞 |

## Validation Commands / Results

### Engine Tests

```bash
source .venv/bin/activate && pytest tests/engine/contracts/test_runner_identity.py tests/engine/contracts/test_agent_run.py tests/engine/contracts/test_runner_spec.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/runners/openai/test_request_identity.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_http_error_event.py
```

**结果**: 174 passed in 0.26s

### Host Tests

```bash
source .venv/bin/activate && pytest tests/host/test_effective_execution_config.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py tests/host/test_local_proxy_engine_ingest.py tests/host/test_run_attempt_transitions.py tests/host/test_llm_compaction.py
```

**结果**: 198 passed in 1.49s

### Pyright

```bash
source .venv/bin/activate && pyright
```

**结果**: 0 errors, 0 warnings, 0 informations

## 审查详情

### 1. README 只描述当前已实现行为

**结论: PASS**

三个 README 变更均只描述当前已实现行为，没有未来设计、过程状态或 analyzer 未实现能力：

- `dayu/engine/README.md`: 准确描述 `RunnerRequestIdentity`、`client_correlation_id`、`AsyncRunner.call` 签名、`ClientCorrelationPolicy` 和 OpenAI-compatible `X-Client-Request-Id` 边界
- `dayu/host/README.md`: 准确描述 Attempt/execution 投影、`provider_request_id`/`client_correlation_id` 在 EventLog / Tool Trace 中的诊断边界
- `tests/README.md`: 准确描述新增测试覆盖，不夸大未覆盖路径

### 2. Engine README 准确性

**结论: PASS**

交叉验证 `dayu/engine/contracts/` 和 `dayu/engine/runners/openai/` 下的实现代码：

| 检查项 | README 描述 | 代码实现 | 一致性 |
|---|---|---|---|
| `RunnerRequestIdentity` 字段 | 7 字段: run_id, attempt_id, execution_id, iteration_id, iteration_index, runner_call_index, client_correlation_id | 完全一致 | ✓ |
| `attempt_id`/`execution_id` 成对约束 | "可选且成对出现" | `__post_init__` 强制同为 None 或同为非 None | ✓ |
| `client_correlation_id` 格式 | "dayu- 加完整 64 位 lowercase SHA-256 hex" | `"dayu-" + 64 lowercase hex` (总长 69 字符) | ✓ |
| `AsyncRunner.call` 签名 | `call(messages, options, tools, *, request_identity)` | 完全一致，`request_identity` 为 keyword-only | ✓ |
| `ClientCorrelationPolicy` 枚举 | `DISABLED` 与 `OPENAI_X_CLIENT_REQUEST_ID` | 完全一致 | ✓ |
| `RunnerSpec.client_correlation_policy` | 必填字段 | 无默认值，必填 | ✓ |
| OpenAI header 行为 | policy enabled + identity 存在时发送；disabled 或 identity 缺失不发送；静态冲突 fail fast | `_build_request_headers` 实现完全一致 | ✓ |
| transport retry 语义 | "复用同一次逻辑 Runner call 的 client_correlation_id" | `_call_impl` 传入同一 identity 对象 | ✓ |

### 3. Host README 准确性

**结论: PASS**

交叉验证 `dayu/host/` 下的实现代码：

| 检查项 | README 描述 | 代码实现 | 一致性 |
|---|---|---|---|
| RunInputBuilder 投影 | `AttemptDispatchSnapshot.attempt_id` 与 `execution_id` 投影到 Engine request | `run_input.py:1680-1681` 直接投影 | ✓ |
| EventLog payload | provider-related payload 保留 `provider_request_id` 与 `client_correlation_id` | 6 个 payload 路径已实现 | ✓ |
| Tool Trace hot summary | `client_correlation_id` 进入 `trace_summary_json` | `_trace_summary()` 返回包含该字段的 dict | ✓ |
| Tool Trace cold JSONL | `trace_summary` 保留 `client_correlation_id` | `_build_cold_line()` 包含该字段 | ✓ |
| 非文本校验 | "payload 中非文本 client_correlation_id 会按 durable payload 字段校验失败" | 校验逻辑存在 | ✓ |
| 不新增 hot-table column | "不新增 durable hot-table schema column" | `client_correlation_id` 只在 JSON blob 内 | ✓ |
| 不让 Engine 拥有 Host 状态机 | "Host 仍是 Attempt / execution 生命周期真源，Engine 不拥有 Host 状态机" | Engine 只消费传入的 identity | ✓ |

### 4. Tests README 准确性

**结论: PASS**

`tests/README.md` 新增描述与实际测试文件一致：

- Engine contract: `runner_identity` 和 `agent_run` 测试覆盖描述准确
- OpenAI runner: `request_identity header` 测试覆盖描述准确
- Host: effective config / RunInputBuilder / ingest / Tool Trace correlation 测试覆盖描述准确

### 5. Residual Risk 复核建议

**结论: PASS - 建议合理**

| ID | Implementation Artifact 建议 | 审查裁决 | 理由 |
|---|---|---|---|
| WU-ENG-02-S1-R1 | 继续 deferred-with-owner | **同意** | 工具超时 `RunFailedData` 缺少 current call correlation 不在 Slice 4 scope，且风险评估 Low |
| WU-ENG-02-S1-R2 | 继续 deferred-with-owner | **同意** | force-answer failure EngineEvent 直接 correlation 断言可后续补充，现有间接覆盖已足够 |
| WU-ENG-02-S2-R1 | 建议关闭 | **同意** | `ClientCorrelationPolicy.DISABLED` 是显式枚举值，RunnerSpec 测试锁定，OpenAI Runner 测试确认 disabled 行为，Host effective config 测试确认 freeze/restore |
| WU-ENG-02-S2-R2 | Engine adapter 建议关闭；上层结构化收口 deferred | **同意** | OpenAI Runner 已 fail fast，上层 Service-facing error 收口不在本 WU scope |
| WU-ENG-02-S3-R1 | 继续 deferred-with-owner | **同意** | `UsageReportedData` 不含 `client_correlation_id` 属于 analyzer 设计决策，不应在本 WU 强行扩展 |
| WU-ENG-02-S3-R2 | 不作为当前 blocker | **同意** | `ContextRecoveryCloseInput` 字段与 `provider_request_id` 校验对称，reactive compaction 路径已有间接覆盖 |

### 6. 验证命令覆盖

**结论: PASS**

验证命令覆盖 plan 中所有要求：

| Plan 要求 | 验证命令 | 结果 |
|---|---|---|
| Engine contract tests | `pytest tests/engine/contracts/...` | ✓ 174 passed |
| OpenAI runner tests | `pytest tests/engine/runners/openai/...` | ✓ 包含在 174 中 |
| Host projection / ingest / trace tests | `pytest tests/host/...` | ✓ 198 passed |
| pyright | `pyright` | ✓ 0 errors |

## Open Questions

none

## Residual Risks / Deferred Items

| ID | 状态 | Owner | 说明 |
|---|---|---|---|
| WU-ENG-02-S1-R1 | deferred-with-owner | WU-ENG-02 / aggregate review | 工具超时 `RunFailedData.client_correlation_id` |
| WU-ENG-02-S1-R2 | deferred-with-owner | 后续 focused Engine test | force-answer failure EngineEvent 直接 correlation 断言 |
| WU-ENG-02-S2-R2 | deferred-with-owner | Service / config assembly | 上层 static header conflict 结构化错误收口 |
| WU-ENG-02-S3-R1 | deferred-with-owner | WU-OBS-00 / analyzer | usage observation 与 client correlation 关联 |
| WU-ENG-02-S3-R2 | deferred-with-owner | 后续 slice | `ContextRecoveryCloseInput` 专用测试 |

## Final Recommendation

Slice 4 文档同步通过审查。README 准确描述当前已实现行为，residual risk 建议合理，验证命令覆盖 plan 要求且全部通过。无 blocking findings。建议进入下一个 gate。
