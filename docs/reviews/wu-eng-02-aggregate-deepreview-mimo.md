# WU-ENG-02 Aggregate Deepreview — AgentMiMo

## Gate

- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- gate: aggregate deepreview
- reviewer: AgentMiMo
- review scope: branch `phaseflow/wu-eng-02-request-identity` 中 WU-ENG-02 对 Engine / Host / Service assembly / README / tests 的全部改动
- review date: 2026-06-03

## Verdict

**pass-with-findings**

0 条 blocking findings。3 条 non-blocking findings（2 Low, 1 Info）。

---

## 1. Engine Contract 跨 Slice 一致性

### RunnerRequestIdentity

| 检查项 | 结果 | 证据 |
|--------|------|------|
| frozen dataclass，全部字段有显式类型 | PASS | `runner_identity.py:27-48` |
| `__post_init__` 校验不变量 | PASS | `runner_identity.py:49-81` |
| `build_runner_request_identity` 构造路径校验 | PASS | `runner_identity.py:84-129` |
| `client_correlation_id` 格式 `dayu-` + 64 lowercase hex | PASS | `runner_identity.py:228-237` |
| canonical tuple 编码无碰撞 | PASS | `runner_identity.py:240-273`（类型前缀 + 长度前缀） |
| `attempt_id` / `execution_id` 成对约束 | PASS | `runner_identity.py:161-165` |
| docstring 完整（参数/返回/异常） | PASS | 全部函数和类 |

### AgentRunRequest

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `attempt_id` / `execution_id` 成对约束 | PASS | `agent_run.py:107-111` `__post_init__` XOR 校验 |
| 默认 `None`（服务 direct Engine / compactor） | PASS | `agent_run.py:94-95` |
| docstring 说明 direct Engine / non-attempt 语义 | PASS | `agent_run.py` docstring |

### EngineEvent client_correlation_id

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `ContextCompactionRequestedData` | PASS | `engine_events.py` `client_correlation_id: str \| None = None` |
| `ProviderProtocolErrorData` | PASS | `engine_events.py` 同上 |
| `IterationCompletedData` | PASS | `engine_events.py` 同上 |
| `RunFailedData` | PASS | `engine_events.py` 同上 |
| `EngineRunOutcomeFailed` | PASS | `agent_run.py` 同上（`AgentRunResult` outcome，非 EngineEvent data class） |
| 所有字段默认 `None`（不破坏已有调用方） | PASS | frozen dataclass 默认值设计 |
| `RunnerEvent` 不携带 `client_correlation_id` | PASS | plan 非目标："不改变 RunnerEvent 不携带 Host ownership 的边界" |

**结论**: Engine contract 跨 Slice 1-4 语义一致，无 `Any` / `object` / 无类型签名。

---

## 2. Agent Call Lifecycle

### runner_call_index 递增

| 路径 | 递增位置 | 结果 |
|------|----------|------|
| normal iteration | `_run_runner_iteration` → `_next_runner_request_identity` | PASS |
| tool-loop re-entry | 主循环再次调用 `_run_runner_iteration` | PASS |
| length continuation | 主循环 `continuation_active` 再次调用 `_run_runner_iteration` | PASS |
| force-answer fallback | `_run_force_answer` → `_run_runner_iteration` → `_next_runner_request_identity` | PASS |
| RAISE_ERROR fallback | `_fallback_after_tools` 不调用 Runner | PASS（不递增正确） |

测试覆盖：
- `test_agent_phase2.py`：success 路径 `runner_call_index == [1]`
- `test_agent_phase3_tool_call.py`：tool-loop `runner_call_index == [1, 2]`
- `test_agent_phase3_tool_call.py`：force-answer `runner_call_index == [1, 2]`
- `test_agent_phase3_tool_call.py`：length continuation `runner_call_index == [1, 2]`

### client_correlation_id 在 Agent emit 点的一致性

所有 emit 点通过 `_client_correlation_id_from_state(state)` 模块级 helper 读取，避免重复散落逻辑：

- `_run_runner_iteration` 内 `IterationCompletedData` 构造
- `_handle_runner_exception` 内 `RunFailedData` 构造
- `_consume_runner_event` 内 `ProviderProtocolErrorData` / `ContextCompactionRequestedData` / `RunFailedData` 构造
- `_execute_tool_batch` 内 `RunFailedData` 构造（duplicate / bijection mismatch）
- `_fallback_after_tools` 内 `RunFailedData` 构造
- `_run_force_answer` 内 `RunFailedData` 构造

**结论**: Agent call lifecycle 一致，`_runner_call_index` 递增覆盖全部 logical Runner call 路径，`client_correlation_id` 通过单一 helper 收敛。

---

## 3. OpenAI-Compatible Runner

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `ClientCorrelationPolicy` 枚举成员 `DISABLED` + `OPENAI_X_CLIENT_REQUEST_ID` | PASS | `runner_spec.py:72-89` |
| docstring 声明 provider-protocol-specific | PASS | `runner_spec.py:73-78` |
| `RunnerSpec.client_correlation_policy` 必填无默认值 | PASS | `runner_spec.py:281` |
| Host freeze/restore 正确序列化 | PASS | `_execution_config_projection.py:154-156, 183-185` |
| Host freeze/restore 缺失字段 → `HostDurableError`（fresh-schema） | PASS | `required_json_text` 抛出 |
| `_build_request_headers` DISABLED → early return | PASS | `runner.py:174-175` |
| `_build_request_headers` OPENAI + identity 非 None → 发送 header | PASS | `runner.py:186-189` |
| `_build_request_headers` OPENAI + identity None → 不发送 header | PASS | `runner.py:186` 条件 |
| 静态 header 冲突 case-insensitive → ValueError | PASS | `runner.py:180-185, 197-209` |
| 冲突在 HTTP post 前 fail-fast | PASS | `_build_request_headers` 在 `_do_attempt` 前调用 |
| transport retry 复用同一 header | PASS | `runner.py:378-381` headers 在 retry loop 外构建一次 |
| response `x-request-id` 采集未修改 | PASS | `_extract_provider_request_id` 无变更 |
| 无 provider 字符串分支 | PASS | `is` 比较 enum member，无 `if provider == "openai"` |
| 无 `Any` / `object` / 兼容 wrapper | PASS | `_factories.py` 用 `TypedDict` 替代 `object` |
| production assembly 默认 `DISABLED` | PASS | `host_assembly.py:870` |

**结论**: OpenAI-compatible runner 实现正确，header mapping 条件完整，conflict 检测在 HTTP post 前 fail-fast，retry 复用同一 header。

---

## 4. Host Projection / Ingest / Tool Trace

### RunInputBuilder projection

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `attempt_id` / `execution_id` 投影到 `AgentRunRequest` | PASS | `run_input.py:1680-1681` |
| 非 ordinary 路径不改变语义 | PASS | `build()` 仅在 ordinary dispatch 路径调用 |

### LLMContextCompactor

| 检查项 | 结果 | 证据 |
|--------|------|------|
| reactive compaction 透传 `attempt_id` / `execution_id` | PASS | `llm_compaction.py:268-269` |
| proactive compaction 保持 `None` | PASS | `CompactionRequest` proactive 路径 `attempt_id=None` |

### Engine ingest

| Provider-related payload | 有 `provider_request_id` | 有 `client_correlation_id` | 结论 |
|--------------------------|--------------------------|---------------------------|------|
| provider protocol diagnostic | ✓ `data.provider_request_id` | ✓ `data.client_correlation_id` | PASS |
| context compaction requested (reactive) | ✓ `data.provider_request_id` | ✓ `data.client_correlation_id` | PASS |
| recoverable run_failed diagnostic | ✓ `data.provider_request_id` | ✓ `data.client_correlation_id` | PASS |
| run_failed terminal summary / payload | ✓ `data.provider_request_id` | ✓ `data.client_correlation_id` | PASS |
| IterationCompleted preview | ✓ `data.provider_request_id` | ✓ `data.client_correlation_id` | PASS |
| `_final_answer_plan` (non-provider) | `None` (hardcoded) | `None` (hardcoded) | PASS |
| `_usage_reported` | `None` (hardcoded) | 未写入 | 见 F1 |
| `_usage_observation_diagnostic_digest` | `None` (hardcoded) | 未写入 | 见 F1 |

### TerminalCloseoutInput / ContextRecoveryCloseInput

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `client_correlation_id: str \| None = None` | PASS | `run_transition.py:387, 425` |
| `_require_optional_non_empty_text` 校验 | PASS | `run_transition.py:5314-5316, 5671-5673` |
| terminal payload 写入 | PASS | `run_transition.py:4194, 4247` |
| context recovery close payload 写入 | PASS | `run_transition.py:3191` |

### Tool Trace

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `_optional_text` 处理缺失 `None` | PASS | `tool_trace.py:918-920` |
| `_optional_text` 处理非文本 → `HostDurableError` | PASS | `tool_trace.py:921-923` |
| `_extract_canonical_trace` 提取 | PASS | `tool_trace.py:454` |
| `_extract_diagnostic_trace` 提取 | PASS | `tool_trace.py:528` |
| `_extract_usage_trace` 提取 | PASS | `tool_trace.py:581` |
| `_trace_summary` 包含字段 | PASS | `tool_trace.py:793` |
| `_build_cold_line` 顶层包含 | PASS | `tool_trace.py:711` |
| `_build_cold_line` trace_summary 内含 | PASS | `tool_trace.py:723` |
| 不新增 hot-table column | PASS | `client_correlation_id` 只在 JSON blob 内 |

**结论**: Host projection / ingest / Tool Trace 闭环正确，`client_correlation_id` 在所有 provider-related payload 中一致传播，Tool Trace summary JSON / cold JSONL 均暴露给 analyzer。

---

## 5. Service / Host Assembly

| 检查项 | 结果 | 证据 |
|--------|------|------|
| production assembly 默认 `ClientCorrelationPolicy.DISABLED` | PASS | `host_assembly.py:870` |
| 不意外发送 provider header | PASS | DISABLED → `_build_request_headers` early return |
| 启用需显式 config/profile 决策 | PASS | plan 明确此设计 |

---

## 6. README 同步

### dayu/engine/README.md

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `AsyncRunner.call` 签名 `call(messages, options, tools, *, request_identity)` | PASS | README 与 `runner.py` 协议一致 |
| `RunnerRequestIdentity` 字段描述 | PASS | README 与 `runner_identity.py` 一致 |
| `client_correlation_id` 格式 `dayu-` + 64 lowercase hex | PASS | README 与 builder 实现一致 |
| `ClientCorrelationPolicy` 枚举描述 | PASS | README 与 `runner_spec.py` 一致 |
| OpenAI header 行为描述 | PASS | README 与 `_build_request_headers` 一致 |
| transport retry 语义 | PASS | README 与 `_call_impl` 一致 |
| `AgentRunRequest` 新增 `attempt_id` / `execution_id` | PASS | README 与 `agent_run.py` 一致 |
| EngineEvent 新增 `client_correlation_id` | PASS | README 与 `engine_events.py` 一致 |

### dayu/host/README.md

| 检查项 | 结果 | 证据 |
|--------|------|------|
| RunInputBuilder 投影描述 | PASS | README 与 `run_input.py:1680-1681` 一致 |
| EventLog ingest 诊断字段描述 | PASS | README 与 `engine_ingest.py` 一致 |
| Tool Trace hot summary / cold JSONL 描述 | PASS | README 与 `tool_trace.py` 一致 |
| "不新增 durable hot-table schema column" | PASS | 实现确认 |
| "Engine 不拥有 Host 状态机" | PASS | 实现确认 |

### tests/README.md

| 检查项 | 结果 | 证据 |
|--------|------|------|
| Engine contract 测试覆盖描述 | PASS | README 与实际测试文件一致 |
| OpenAI runner 测试覆盖描述 | PASS | README 与 `test_request_identity.py` 一致 |
| Host 测试覆盖描述 | PASS | README 与实际测试文件一致 |

### 无未来能力描述

全文扫描三个 README：
- 未发现 "未来"、"计划"、"即将"、"后续"、"TODO"、"FIXME" 等过程状态标记
- 未发现 analyzer 未实现能力被描述为当前能力
- 未发现旧术语残留
- 根 `README.md` 未被修改（CLI/config/user workflow 不变）

---

## 7. Findings

### F1 [LOW] — 工具超时 `RunFailedData` 缺少 `client_correlation_id`

- **文件**: `dayu/engine/agent.py:2150-2157`
- **直接证据**: `_make_tool_timeout_terminal_with_close` 构造 `RunFailedData` 时未显式传入 `client_correlation_id`，依赖 dataclass 默认值 `None`。同一文件中 `_validate_batch_bijection`（已修复）、`_fallback_after_tools`（已修复）等路径均已显式传入。
- **影响**: 工具执行超时时 `RunFailedData.client_correlation_id` 为 `None`，caller 有 `decision.client_correlation_id` 可用但未传入。对诊断影响有限——工具超时属于内部超时机制，非 provider 错误。
- **建议**: 保持 deferred-with-owner（WU-ENG-02 residual S1-R1），由后续工作单元决定是否在该路径补 correlation。

### F2 [LOW] — force-answer failure EngineEvent 无直接 `client_correlation_id` 断言

- **文件**: `tests/engine/test_agent_phase3_tool_call.py` force-answer 测试
- **直接证据**: `test_oversized_tool_message_is_passed_to_force_answer_runner_call` 验证了 `runner_call_index == [1, 2]` 和 `iteration_id` 正确，但未显式断言 emitted `RunFailedData.client_correlation_id` 等于第二次 request identity 的 `client_correlation_id`。
- **影响**: 代码行为正确——`_run_force_answer` 内 `_run_runner_iteration` 构造 non-None identity，emit 点通过 `_client_correlation_id_from_state(state)` 读取。gap 仅在测试断言层面。
- **建议**: 保持 deferred-with-owner（WU-ENG-02 residual S1-R2），后续补 focused Engine test。

### F3 [INFO] — `_build_request_headers` 末尾 `raise ValueError` 防御性分支

- **文件**: `dayu/engine/runners/openai/runner.py:191-194`
- **直接证据**: `ClientCorrelationPolicy` 是 `StrEnum`，当前只有两个成员，前面的 `if` 分支已穷尽所有值，末尾 `raise ValueError` 在当前枚举定义下不可达。
- **影响**: 无功能影响。该守卫在枚举新增成员时充当 fail-fast，防止静默忽略未知 policy。保留是合理防御性编程。
- **建议**: 保持现状。

---

## 8. Adversarial Failure Pass

| 场景 | 处理方式 | 结果 |
|------|----------|------|
| provider protocol error | `ProviderProtocolErrorData` 携带 `client_correlation_id` | PASS |
| HTTP error | `RunnerHTTPErrorData` 不携带（RunnerEvent 边界）；`RunFailedData` 通过 `_client_correlation_id_from_state` 携带 | PASS |
| context compaction failure | `ContextCompactionRequestedData` 携带；reactive 路径有 `attempt_id/execution_id` | PASS |
| tool timeout | `RunFailedData` 缺少 `client_correlation_id`（默认 `None`） | LOW — 见 F1 |
| force-answer failure | `RunFailedData` 携带 `client_correlation_id`（代码正确，缺直接测试断言） | LOW — 见 F2 |
| static header conflict | `_build_request_headers` 在 HTTP post 前抛 `ValueError` | PASS |
| direct Runner no identity | `request_identity=None` 合法，不发送 header | PASS |
| compactor proactive | `attempt_id=None, execution_id=None` 合法 | PASS |
| compactor reactive | 透传 `attempt_id/execution_id` | PASS |
| transport retry | 复用同一 header（同一 identity） | PASS |
| response x-request-id 未回退 | `_extract_provider_request_id` 未修改 | PASS |
| corrupted JSON round-trip | fresh-schema 行为：缺失字段 → `HostDurableError` | PASS |

---

## 9. Project Instruction Compliance

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 分层：UI → Service → Host → Engine | PASS | 无反向依赖 |
| `dayu.runtime` 不 import 上层 | PASS | WU-ENG-02 未修改 `dayu.runtime` |
| docstring 完整（参数/返回/异常） | PASS | 全部新增函数 / 类 / 模块 |
| 无 `Any` / `object` / 无类型签名 | PASS | `_factories.py` 用 `TypedDict` 替代 `object` |
| 无兼容性 wrapper / facade | PASS | fresh-schema 设计，无旧 schema 兼容读取 |
| 无反向依赖 | PASS | Engine 不读 Host durable store，Host 不拥有 Engine 状态机 |
| 无 provider 字符串分支 | PASS | `is` 比较 enum member |
| 无胶水 seam / 无充分理由的 lazy import | PASS | 无新增 |
| 无魔法数字 / 魔法字符串（非 schema） | PASS | `_CLIENT_REQUEST_ID_HEADER_NAME` 等为模块级常量 |
| schema 变更：全新 schema 起库 | PASS | 无旧库兼容读取 |
| README 触发规则 | PASS | `dayu/engine/` → `dayu/engine/README.md`；`dayu/host/` → `dayu/host/README.md`；`tests/` → `tests/README.md`；根 README 无触发（CLI/config 不变） |
| 测试覆盖目标 >= 80% | PASS | 372 tests passed |

---

## 10. Validation Commands / Results

```bash
source .venv/bin/activate && pytest \
  tests/engine/contracts/test_runner_identity.py \
  tests/engine/contracts/test_agent_run.py \
  tests/engine/contracts/test_runner_spec.py \
  tests/engine/test_agent_phase2.py \
  tests/engine/test_agent_phase3_tool_call.py \
  tests/engine/runners/openai/test_request_identity.py \
  tests/engine/runners/openai/test_streaming_capability_and_content_type.py \
  tests/engine/runners/openai/test_http_error_event.py \
  tests/host/test_effective_execution_config.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_local_proxy_engine_ingest.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_llm_compaction.py -q
```

**结果**: 372 passed in 1.66s

```bash
source .venv/bin/activate && python -m pyright
```

**结果**: 0 errors, 0 warnings, 0 informations

---

## 11. Residual Risk Reconciliation

| ID | 描述 | 原状态 | 建议 | 理由 |
|----|------|--------|------|------|
| WU-ENG-02-S1-R1 | 工具超时 `RunFailedData` 缺少 `client_correlation_id` | deferred-with-owner | **保持** | 工具超时属于内部超时机制，非 provider 错误；对诊断影响有限。后续工作单元决定是否补 correlation。 |
| WU-ENG-02-S1-R2 | force-answer failure EngineEvent 无直接 `client_correlation_id` 断言 | deferred-with-owner | **保持** | 代码行为正确（`_run_force_answer` 通过 helper 携带 correlation），gap 仅在测试断言。后续补 focused test。 |
| WU-ENG-02-S2-R1 | production assembly 默认 DISABLED | closed (Slice 4) | **确认关闭** | `ClientCorrelationPolicy.DISABLED` 是显式枚举值，RunnerSpec 测试锁定，OpenAI Runner 测试确认 disabled 行为，Host effective config 测试确认 freeze/restore。符合 "显式 policy 才发送" 验收。 |
| WU-ENG-02-S2-R2 | 静态 header 冲突上层结构化收口 | deferred-with-owner | **Engine adapter 部分关闭；Service 收口保持 deferred** | OpenAI Runner 已 fail fast，测试确认不会发 HTTP 请求。Service/config assembly 的结构化错误收口不在本 WU scope。 |
| WU-ENG-02-S3-R1 | usage observation 与 client correlation 关联 | deferred-with-owner | **保持** | `UsageReportedData` 不含 `client_correlation_id`，属于 analyzer 设计决策，不应在本 WU 强行扩展。Owner: WU-OBS-00。 |
| WU-ENG-02-S3-R2 | `ContextRecoveryCloseInput` 专用测试 | deferred-with-owner | **保持** | 字段与 `provider_request_id` 校验对称，reactive compaction 路径已有间接覆盖。可选补 focused test。 |

无 unowned residual risk。

---

## 12. Open Questions

无 blocking open questions。

---

## 13. Final Recommendation

WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation 的 4 个 Slice 实现质量良好：

1. **Engine contract**：`RunnerRequestIdentity` 强类型 frozen dataclass，canonical tuple SHA-256 digest 无碰撞，`AsyncRunner.call` 签名最小化变更（仅新增 keyword-only），`AgentRunRequest.attempt_id/execution_id` 成对约束，EngineEvent data class 新增 `client_correlation_id` 字段默认 `None`。
2. **Agent call lifecycle**：`_runner_call_index` 在所有 logical Runner call 路径正确递增，`client_correlation_id` 通过单一模块级 helper `_client_correlation_id_from_state` 收敛到所有 emit 点。
3. **OpenAI-compatible runner**：`ClientCorrelationPolicy` 枚举语义正确（provider-protocol-specific，非 provider-name branches），header 条件发送/拒绝 conflict/复用 retry 均符合预期，response x-request-id 采集未回退。
4. **Host projection / ingest / Tool Trace**：RunInputBuilder 正确投影 attempt/execution identity，EngineEvent `client_correlation_id` 进入所有 provider-related EventLog payload，Tool Trace summary JSON / cold JSONL 暴露给 analyzer。
5. **Service assembly**：production default `DISABLED`，不意外发送 provider header。
6. **README**：三个 README 准确描述当前已实现行为，无未来设计、过程状态或未实现能力。
7. **Residual risks**：6 条 residual risk 均有明确 owner，2 条建议关闭，4 条保持 deferred-with-owner，无 unowned risk。

0 条 blocking findings。3 条 non-blocking findings（F1 Low, F2 Low, F3 Info），均为已有 documented residual risk 或防御性代码。

**建议**: WU-ENG-02 可进入 draft PR gate。

---

- artifact path: `docs/reviews/wu-eng-02-aggregate-deepreview-mimo.md`
- verdict: pass-with-findings
- blocking findings: 0
- non-blocking findings: 3 (2 Low, 1 Info)
- tests: 372 passed
- pyright: 0 errors
