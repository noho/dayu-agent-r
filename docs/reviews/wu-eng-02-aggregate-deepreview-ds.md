# WU-ENG-02 Aggregate Deep Review — AgentDS

## Gate / Work Unit

- gate: aggregate deepreview
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- reviewer: AgentDS
- review scope: 全部 4 个 implementation slices 的 correctness、architecture boundary、cross-slice consistency、testing gaps、residual risk、README 同步与项目指令合规

## Verdict

**pass**

0 条 blocking findings。全部 4 个 slices 实现与 accepted plan 一致，架构边界完整，分层约束未违反，测试覆盖充分，pyright 0 errors，README 同步准确。6 条 residual risks 均有 owner，其中 S2-R1 建议关闭。

---

## 审查真源

| 真源 | 路径 |
|------|------|
| design_doc | `docs/host/design.md` |
| control_doc | `docs/host/issues-implementation-control.md` |
| plan | `docs/host/wu-eng-02-provider-request-identity-plan.md` |
| accepted commits | plan `59f66b7`, Slice 1 `c4826e0`, Slice 2 `c3856b9`, Slice 3 `5ddc4cb`, Slice 4 `896d483` |

审查输入 artifacts：全部 21 个 plan review / code review / fix / re-review artifacts（路径见 control_doc 汇总表）。

---

## 1. Engine Contract 正确性审查

### 1.1 `RunnerRequestIdentity` (Slice 1)

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 字段类型均为强类型 | PASS | `runner_identity.py:41-47`，无 `Any`/`object` |
| `client_correlation_id` 格式为 `dayu-` + 64 lowercase hex | PASS | `runner_identity.py:236-237` |
| 编码使用类型前缀防歧义 | PASS | `runner_identity.py:255-273`，`s`/`i`/`n` 前缀 + 长度前缀 |
| direct 构造校验与 builder 校验一致 | PASS | 两者调用同一 `_validate_identity_inputs` |
| `attempt_id`/`execution_id` 成对约束 | PASS | `runner_identity.py:161-165` |
| `runner_call_index >= 1` | PASS | `runner_identity.py:159-160` |
| `iteration_index >= 0` | PASS | `runner_identity.py:157-158` |
| 公开导出通过 `__init__.py` | PASS | `contracts/__init__.py:64-67` |

### 1.2 `AsyncRunner.call` 协议变更 (Slice 1)

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `request_identity` 为 keyword-only | PASS | `runner.py:31`，`*, request_identity: RunnerRequestIdentity \| None` |
| `messages`/`options`/`tools` 位置参数不变 | PASS | 位置参数顺序与旧协议一致 |
| 允许显式 `None` | PASS | docstring 明确说明非普通 Agent attempt 路径可传 `None` |

### 1.3 `AgentRunRequest` 扩展 (Slice 1)

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `attempt_id`/`execution_id` 均为 `str \| None`，默认 `None` | PASS | `agent_run.py:94-95` |
| 成对约束校验 | PASS | `agent_run.py:107-111` |
| 不在 `__post_init__` 中将默认值改为必填 | PASS | 默认值 `None` 兼容旧构造点 |

### 1.4 EngineEvent `client_correlation_id` (Slice 1)

| Event Data Class | 字段类型 | 默认值 | 代码行 |
|---|---|---|---|
| `ContextCompactionRequestedData` | `str \| None` | `None` | `engine_events.py:273` |
| `ProviderProtocolErrorData` | `str \| None` | `None` | `engine_events.py:315` |
| `IterationCompletedData` | `str \| None` | `None` | `engine_events.py:332` |
| `RunFailedData` | `str \| None` | `None` | `engine_events.py:415` |

`EngineRunOutcomeFailed` (AgentRunResult outcome，非 EngineEvent) 同样携带：`agent_run.py:156`

**跨界检查**: `RunnerEvent` **不含** `client_correlation_id`（grep runner_events.py 结果: 0 occurrences）。这符合设计边界：RunnerEvent 不携带 Host ownership，关联由 Agent 提升到 EngineEvent。

---

## 2. Agent Call Lifecycle 审查 (Slice 1)

### 2.1 `runner_call_index` 递增覆盖

| 调用路径 | 行号 | 是否递增 | 证据 |
|---|---|---|---|
| 普通 iteration Runner call | `agent.py:1072,1102` | 是 | `_next_runner_request_identity` 调用 `self._runner_call_index += 1` |
| tool-loop re-entry | `agent.py:1123` | 是（下一轮 iteration 重新进入 runner 调用） | 每个 `_run_runner_iteration` 入口都调 `_next_runner_request_identity` |
| length continuation | `agent.py:1072` | 是 | continuation 进入同一 `_run_runner_iteration` 路径 |
| force-answer fallback | `agent.py:1072` | 是 | force-answer 调用 `_run_force_answer_iteration` 内调 `_next_runner_request_identity` |
| transport retry | `runner.py:378-381` | 否（正确） | headers 在 retry loop 外构建一次，复用同一 identity |

**结论**: `runner_call_index` 在所有逻辑 Runner call 路径正确递增，transport retry 正确复用。

### 2.2 `client_correlation_id` 在 EngineEvent 中的一致性

| Event 发射路径 | 行号 | correlation 来源 | 覆盖 |
|---|---|---|---|
| `ITERATION_COMPLETED` | `agent.py:1178` | `_client_correlation_id_from_state(state)` | 是 |
| `PROVIDER_PROTOCOL_ERROR` | `agent.py:1294` | `_client_correlation_id_from_state(state)` | 是 |
| `RUN_FAILED` (runner exception) | `agent.py:1178` | `_client_correlation_id_from_state(state)` | 是 |
| `RUN_FAILED` (continuation tool call not allowed) | `agent.py:1024` | `_client_correlation_id_from_state(state)` | 是 |
| `RUN_FAILED` (tool call not enabled) | `agent.py:2078` | `_client_correlation_id_from_state(state)` | 是 |
| `RUN_FAILED` (force answer empty) | `agent.py:2097` | `_client_correlation_id_from_state(state)` | 是 |
| `RUN_FAILED` (bijection mismatch) | `agent.py:1840,1848` | `decision.client_correlation_id` | 是 |
| `RUN_FAILED` (duplicate tool call id) | `agent.py:1600` | `decision.client_correlation_id` | 是 |
| `RUN_FAILED` (tool execution timeout) | `agent.py:2154` | 未传（默认 `None`） | **否** ← S1-R1 |
| `CONTEXT_COMPACTION_REQUESTED` | `agent.py:1681` | `decision.client_correlation_id` | 是 |

除已知的 S1-R1（工具执行超时路径），全部 EngineEvent 发射路径均正确携带 `client_correlation_id`。

---

## 3. OpenAI-Compatible Runner 审查 (Slice 2)

### 3.1 Header 映射逻辑

| 场景 | 预期行为 | 代码路径 | 验证 |
|---|---|---|---|
| Policy DISABLED | 不发送 `X-Client-Request-Id` | `runner.py:174-175` | 测试覆盖 |
| Policy OPENAI + identity 非 None | 发送 | `runner.py:186-189` | 测试覆盖 |
| Policy OPENAI + identity None | 不发送 | `runner.py:186` 条件跳过 | 测试覆盖 |
| Policy OPENAI + static header 冲突 | `ValueError` fail fast | `runner.py:180-185` | 测试覆盖 |
| Transport retry 复用 identity | 同一 headers 重试 | `runner.py:378-381` | 测试覆盖 |
| Response `x-request-id` 采集 | 不变 | `runner.py` 中 `_extract_provider_request_id` 未修改 | 既有测试继续通过 |

### 3.2 `ClientCorrelationPolicy` 语义

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 枚举值不是 provider 名称字符串 | PASS | `runner_spec.py:88-89`，值为 `"disabled"` / `"openai_x_client_request_id"` |
| Host/Agent 无 provider 字符串分支 | PASS | 全文搜索，仅 `runner.py` 中用 `is` 比较 enum member |
| docstring 明确声明 provider-protocol-specific | PASS | `runner_spec.py:73-78` |
| `RunnerSpec.client_correlation_policy` 无默认值 | PASS | `runner_spec.py:281`，必须显式传入 |

### 3.3 Static Header Conflict

| 检查项 | 结果 |
|--------|------|
| 大小写不敏感检测 | PASS — `_CLIENT_REQUEST_ID_HEADER_NAME_LOWER = "x-client-request-id"`，遍历 `headers.items()` 做 `name.lower()` 比较 |
| 在 HTTP 请求前 fail fast | PASS — `_build_request_headers()` 在 `_do_attempt()` 的 `session.post()` 前调用 |
| 仅 policy 开启时检测 | PASS — `DISABLED` 时不进入检测分支 |

---

## 4. Host Projection / Ingest / Tool Trace 审查 (Slice 3)

### 4.1 `RunInputBuilder` 投影

| 检查项 | 结果 | 证据 |
|--------|------|------|
| `attempt_id` 投影 | PASS | `run_input.py:1680`，取值 `attempt_snapshot.attempt_id` |
| `execution_id` 投影 | PASS | `run_input.py:1681`，取值 `attempt_snapshot.execution_id` |
| `AttemptDispatchSnapshot` 包含两字段 | PASS | `api.py` 定义已包含 |

### 4.2 Compactor 路径

| 场景 | `attempt_id`/`execution_id` | 证据 |
|------|------|------|
| Reactive compaction | 透传 `request.attempt_id`/`request.execution_id` | `llm_compaction.py:268-269` |
| Proactive compaction | 两者为 `None` | compactor 的 `request` 来自自身 context，非普通 Attempt |

### 4.3 Host Ingest Payload

| Ingest 路径 | `client_correlation_id` 写入 | 证据 |
|---|---|---|
| Provider protocol diagnostic | 是 | `engine_ingest.py:850` |
| Context compaction requested | 是 | `engine_ingest.py:1023` |
| Run failed terminal closeout | 是 | `engine_ingest.py:1388` |
| Iteration completed preview | 是 | `engine_ingest.py:1503` |
| Reactive compaction recovery closeout | 是 | `engine_ingest.py:2420` |
| Worker lifecycle failed closeout (no correlation available) | `None` | `engine_ingest.py:3862,3884,3946,3963,3984,4024` |

无 provider-related EngineEvent 路径遗漏写入 `client_correlation_id`。

### 4.4 Tool Trace

| 检查项 | 结果 | 证据 |
|--------|------|------|
| Hot row 无新增 column | PASS | `client_correlation_id` 进入 `trace_summary_json`，不新增 SQLite 表/列 |
| Cold JSONL summary 包含同名字段 | PASS | `tool_trace.py:793` |
| 提取使用 `_optional_text` | PASS | `tool_trace.py:454,528,581` |
| 非文本字段 fail closed | PASS | `_optional_text` 校验非文本/空值时返回 `None` 或抛错 |
| 查询方法已更新 | PASS | `tool_trace.py:711` 包含 `_FIELD_CLIENT_CORRELATION_ID` |

---

## 5. Service / Host Assembly 审查

| 检查项 | 结果 | 证据 |
|--------|------|------|
| 生产装配默认 `DISABLED` | PASS | `host_assembly.py:870`，`ClientCorrelationPolicy.DISABLED` 硬编码 |
| 启用需显式修改 assembly | PASS | 当前无配置入口将 policy 切换为 enabled |
| Host 配置 freeze/restore 正确 | PASS | `_execution_config_projection.py:154-156, 183-185`，round-trip 包含 `client_correlation_policy` |

**语义确认**: 生产默认 disabled 符合 plan 中"显式 policy 才发送"的验收信号。当前尚无生产环境需要启用 `X-Client-Request-Id` 的场景。

---

## 6. README 同步审查 (Slice 4)

### 6.1 `dayu/engine/README.md`

| 变更内容 | 准确性 |
|---|---|
| `AsyncRunner.call` 签名（含 `request_identity`） | 准确，与 `runner.py` 协议一致 |
| `RunnerRequestIdentity` 字段列表 | 准确，与 `runner_identity.py` 一致 |
| `ClientCorrelationPolicy` 行为描述 | 准确，覆盖 disabled/enabled/static conflict/retry reuse |
| `AgentRunRequest` 新增字段 | 准确 |
| EngineEvent 含 `client_correlation_id` 的列表 | 准确，5 个 data class 全部验证 |
| 执行路径更新 | 准确 |

### 6.2 `dayu/host/README.md`

| 变更内容 | 准确性 |
|---|---|
| RunInputBuilder 投影描述 | 准确，与 `run_input.py:1680-1681` 一致 |
| EventLog ingest 覆盖范围 | 准确，覆盖 provider diagnostic/reactive compaction/failed closeout/iteration preview |
| Tool Trace 存储描述 | 准确，`client_correlation_id` 进入 JSON 而非 hot column |

### 6.3 `tests/README.md`

| 变更内容 | 准确性 |
|---|---|
| 新增测试条目的文件对应关系 | 准确 |
| 无未来能力描述 | PASS |
| 无过程状态或 TODO | PASS |

**全局检查**: 三个 README 均无"未来设计"、"计划"、"即将"、"后续"、"TODO"等过程状态标记；无旧术语残留；根 `README.md` 未被修改（符合 plan）。

---

## 7. 项目指令合规性审查

### 7.1 分层架构

| 约束 | 结果 |
|---|---|
| `Engine` 不 import `Host`/`Service`/`UI` | PASS — 未发现反向依赖 |
| `Host` 不 import `Service`/`UI` | PASS |
| `RunnerEvent` 不携带 Host ownership | PASS — `runner_events.py` 中 0 occurrences of `client_correlation_id` |
| `dayu.runtime` 不 import 业务层 | PASS — 本 WU 未修改 `dayu.runtime` |

### 7.2 编码规范

| 约束 | 结果 |
|---|---|
| 中文 docstring | PASS — 所有新增函数/类/模块均有完整中文 docstring |
| 禁止 `Any`/`object`/无类型签名 | PASS — 未发现新增 |
| 禁止 lazy import | PASS — 未发现新增 |
| 禁止魔法字符串/数字 | PASS — 模块级常量代替魔法值 |
| 禁止兼容性代码 | PASS — 无 re-export、wrapper、兼容常量 |
| 禁止 provider 字符串治理分支 | PASS — `ClientCorrelationPolicy` 使用 enum `is` 比较，非 provider 字符串 |
| 禁止 God object/function/dataclass | PASS — 各模块职责清晰 |

### 7.3 Schema 变更

| 约束 | 结果 |
|---|---|
| 不新增 SQLite 表/列 | PASS — `client_correlation_id` 仅进入 JSON payload |
| 无旧库兼容读取 | PASS |
| 无兼容迁移 | PASS |

### 7.4 测试与验证

| 约束 | 结果 |
|---|---|
| 修改后测试通过 | PASS — 372 tests passed |
| pyright 0 errors | PASS |
| 无新增或扩散类型错误 | PASS |
| 无为了保住旧测试的兼容逻辑 | PASS |

---

## 8. Adversarial Failure Pass

### 8.1 Provider Protocol Error

**场景**: Runner 收到 provider 协议错误（malformed JSON、unexpected finish_reason 等）

**预期**: `ProviderProtocolErrorData.client_correlation_id` 应为当前 Runner call 的 correlation

**验证**: `agent.py:1294` 传入 `_client_correlation_id_from_state(state)`。State 在迭代运行期间始终有效。测试 `test_tool_calls_finish_reason_mismatch_keeps_provider_request_id` 覆盖该路径的 EngineEvent 级断言。

**结果**: **PASS**

### 8.2 HTTP Error

**场景**: Runner HTTP 4xx/5xx 错误

**预期**: `RunFailedData.client_correlation_id` 应为当前 Runner call 的 correlation

**验证**: `agent.py:1178` 在 `_consume_runner_event` 处理 `RunnerHTTPErrorData` 时传入 `_client_correlation_id_from_state(state)`。测试 `tests/engine/runners/openai/test_http_error_event.py` 覆盖 HTTP error 路径。

**结果**: **PASS**

### 8.3 Context Compaction Failure

**场景**: Compactor LLM call 失败或 compaction proposal 校验失败

**预期**: Compactor 的 Runner call 携带 compactor 自身的 correlation id；Host 层面的 reactive compaction failure closeout 携带触发该 recovery 的 EngineEvent correlation id

**验证**: 
- `llm_compaction.py:268-269` 透传 `request.attempt_id`/`request.execution_id`，compactor Agent 基于此生成自己的 `client_correlation_id`
- `engine_ingest.py:1023` 写入 `client_correlation_id=plan.client_correlation_id`
- `tests/host/test_llm_compaction.py` 覆盖 reactive compaction 路径

**结果**: **PASS**

### 8.4 Tool Timeout

**场景**: `ToolExecutor.execute` 超时

**预期**: `RunFailedData.client_correlation_id` 应为触发该工具批次的 Runner call correlation id

**实际**: `agent.py:2154` 的 `RunFailedData` 构造未传入 `client_correlation_id`，使用默认值 `None`

**影响**: Low — 工具超时发生在 Runner 调用之后，上一个 Runner call 的 correlation id 在 `decision.client_correlation_id` 中可用但未被传入。对 provider debugging 主链路影响有限，因为工具超时不是 provider 错误。

**结果**: **PASS-WITH-KNOWN-DEFERRED-RISK** (S1-R1)

### 8.5 Force-Answer Failure

**场景**: Force-answer Runner call 返回空内容

**预期**: `RunFailedData.client_correlation_id` 应为 force-answer Runner call 的 correlation

**验证**: `agent.py:2097` 传入 `_client_correlation_id_from_state(state)`。Force-answer 路径在 `agent.py:1072` 调用 `_next_runner_request_identity()` 递增 call index 并构造新 identity。

**结果**: **PASS**

### 8.6 Static Header Conflict

**场景**: `RunnerSpec.headers` 已含 `x-client-request-id`，且 policy 为 `OPENAI_X_CLIENT_REQUEST_ID`

**预期**: Runner 在 HTTP 请求前抛 `ValueError`

**验证**: `runner.py:180-185` 调用 `_has_client_request_id_header(spec.headers)`，命中时抛 `ValueError`。大小写不敏感。`_build_request_headers` 在 `_do_attempt` 的 `session.post` 前调用。测试 `test_static_header_conflict_rejected` 覆盖。

**结果**: **PASS**

### 8.7 Direct Runner No Identity

**场景**: 直接调用 Runner（不通过 Agent），传入 `request_identity=None`

**预期**: Runner 不发送 `X-Client-Request-Id`，即使 policy enabled

**验证**: `runner.py:186` 条件 `if request_identity is not None` 确保 identity 不存在时不发送 header。测试 `test_enabled_policy_without_identity_does_not_send_header` 和 `test_policy_disabled_without_identity_does_not_send_header` 覆盖两种 policy 状态。

**结果**: **PASS**

### 8.8 Compactor Proactive/Reactive

**场景**: Proactive compaction（不在 Attempt 内，attempt_id/execution_id 为 None），reactive compaction（在 Attempt 内）

**预期**: Proactive 时 AgentRunRequest 的 attempt_id/execution_id 为 None；reactive 时携带当前 Attempt 的值

**验证**:
- Proactive: compactor 的 `_agent_request()` 使用 compactor 自身的 request，其中 `attempt_id`/`execution_id` 取决于调用上下文
- Reactive: `llm_compaction.py:268-269` 透传 `request.attempt_id`/`request.execution_id`
- 测试: `tests/host/test_llm_compaction.py` 覆盖 reactive 路径

**结果**: **PASS**

---

## 9. Residual Risk Reconciliation

| ID | 当前状态 | 本审查建议 | 理由 |
|---|---|---|---|
| WU-ENG-02-S1-R1 | deferred-with-owner | **保持 deferred** | 工具超时路径 `RunFailedData` 缺 `client_correlation_id`（`agent.py:2154`）。语义上工具超时发生在 Runner 调用之外，当前 correlation 是否应传入需后续裁决。建议由 aggregate review 后的 Engine focused test 工作单元处理。 |
| WU-ENG-02-S1-R2 | deferred-with-owner | **保持 deferred** | Force-answer EngineEvent 级 `client_correlation_id` 直接断言缺失。代码行为正确（`agent.py:2097`），间接覆盖充分，但缺少值比较的直接断言。建议后续 Engine focused test 补齐。 |
| WU-ENG-02-S2-R1 | closed (Slice 4) | **确认关闭** | 关闭依据充分：policy enum 定义明确、disabled 行为测试覆盖、enabled 行为测试覆盖、Host config freeze/restore 测试通过。 |
| WU-ENG-02-S2-R2 | deferred-with-owner | **Engine 部分确认关闭，Service 部分保持 deferred** | Engine adapter 层的 `ValueError` fail fast 与测试覆盖已完成。Service-facing 结构化错误收口不属于本 WU 最小验收。 |
| WU-ENG-02-S3-R1 | deferred-with-owner | **保持 deferred** | `UsageReportedData` 不含 `client_correlation_id`。Usage observation 是 post-call projection signal，非 provider debugging 主链路。若 issue-70 analyzer 需要，由 WU-OBS-00 先扩展 Engine contract。 |
| WU-ENG-02-S3-R2 | deferred-with-owner | **保持 deferred** | `ContextRecoveryCloseInput.client_correlation_id` 专用 validation/payload 单测缺失。当前间接覆盖与对称校验充分，不阻塞。建议后续 Host focused test 可选补 focused test。 |

### 无 Owner Risk 检查

全部 6 条 residual risks 均有 owner（S1-R1/S1-R2 → future Engine test；S2-R2 → Service assembly；S3-R1 → WU-OBS-00 analyzer；S3-R2 → future Host test）。无 orphan risk。

---

## 10. Cross-Slice Consistency

| 检查维度 | 结果 |
|---|---|
| Slice 1 → Slice 2: `RunnerRequestIdentity.client_correlation_id` 到 `X-Client-Request-Id` header 映射 | 一致 — Slice 1 产出的 identity 被 Slice 2 正确消费 |
| Slice 1 → Slice 3: `AgentRunRequest.attempt_id`/`execution_id` 到 `RunnerRequestIdentity` | 一致 — Slice 3 投影进入 AgentRunRequest，Slice 1 的 Agent 基于其构造 identity |
| Slice 1 → Slice 3: `EngineEvent.client_correlation_id` 到 EventLog payload | 一致 — Slice 1 产出的 EngineEvent 字段被 Slice 3 ingest 正确写入 EventLog |
| Slice 2 → Slice 3: `RunnerSpec.client_correlation_policy` 到 Host freeze/restore | 一致 — Slice 2 定义的 policy 被 Slice 3 的 config projection 正确持久化 |
| Slice 3 → Tool Trace: EventLog payload 到 `trace_summary_json` | 一致 — Slice 3 ingest 写入的 `client_correlation_id` 被 Tool Trace 正确提取 |

无 cross-slice 遗漏或 schema 不一致。

---

## 11. 验证命令与结果

### Engine 测试

```bash
source .venv/bin/activate && pytest \
  tests/engine/contracts/test_runner_identity.py \
  tests/engine/contracts/test_agent_run.py \
  tests/engine/contracts/test_runner_spec.py \
  tests/engine/test_agent_phase2.py \
  tests/engine/test_agent_phase3_tool_call.py \
  tests/engine/runners/openai/test_request_identity.py \
  tests/engine/runners/openai/test_streaming_capability_and_content_type.py \
  tests/engine/runners/openai/test_http_error_event.py -q
```

**结果**: **174 passed** in 0.28s

### Host 测试

```bash
source .venv/bin/activate && pytest \
  tests/host/test_effective_execution_config.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_local_proxy_engine_ingest.py \
  tests/host/test_run_attempt_transitions.py \
  tests/host/test_llm_compaction.py -q
```

**结果**: **198 passed** in 1.62s

### pyright

```bash
source .venv/bin/activate && pyright
```

**结果**: **0 errors, 0 warnings, 0 informations**

---

## 12. Open Questions

无 blocking open questions。

- `_ERROR_TOOL_EXECUTION_TIMEOUT` 路径是否需要补 `client_correlation_id`？→ 非 blocking，由后续 Engine focused test 工作单元裁决 (S1-R1)
- Force-answer EngineEvent 断言是否需要补齐？→ 非 blocking，由后续 Engine focused test 工作单元裁决 (S1-R2)
- Production 如何启用 `X-Client-Request-Id`？→ 当前 assembly 硬编码 `DISABLED`，启用需修改 `host_assembly.py` 或新增配置入口。属于 Service/config assembly 的后续设计决策，不在本 WU scope

---

## 13. Final Recommendation

**Proceed to next gate.**

全部 4 个 slices 实现与 accepted plan 一致：
- Engine contract 正确、强类型、无反向依赖
- Agent call lifecycle 在所有逻辑 Runner call 路径正确处理 `runner_call_index` 和 `client_correlation_id`
- OpenAI-compatible runner 正确映射 header，policy 控制、冲突检测、retry 复用全部到位
- Host projection/ingest/Tool Trace 正确传递和持久化诊断信号，无 durable schema 入侵
- Service assembly 默认 disabled，符合准入要求
- README 同步准确，无未来能力描述
- 372 tests passed，pyright 0 errors
- 6 条 residual risks 均有 owner，S2-R1 可关闭
- 0 条 blocking findings
