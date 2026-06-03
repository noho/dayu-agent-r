# WU-ENG-02 Slice 2 Code Review - AgentMiMo

## Gate / Work Unit / Slice

- gate: code review
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 2 - RunnerSpec Policy And OpenAI-Compatible Header Mapping
- agent: AgentMiMo

## Review Target

当前未提交 workspace changes for Slice 2。审查范围覆盖 implementation artifact `docs/reviews/wu-eng-02-slice2-implementation-codex.md`、accepted plan `docs/host/wu-eng-02-provider-request-identity-plan.md`、control doc `docs/host/issues-implementation-control.md`，以及 `git diff` 所有 37 个变更文件。

## Validation Evidence

- `pytest tests/engine/contracts/test_runner_spec.py tests/engine/runners/openai/test_request_identity.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_effective_execution_config.py`：61 passed，0 failed。
- `pyright`：0 errors, 0 warnings, 0 informations。
- 人工逐行审查 `git diff` 全量 37 文件，294 insertions, 46 deletions。

## Findings

### F1 - Low - `_has_client_request_id_header` docstring `:raises Exception:` 表述不规范

- **文件/行**: `dayu/engine/runners/openai/runner.py:203`
- **证据**: docstring 写 `:raises Exception: 不主动抛出异常。`。标准 Python docstring 约定中，若函数不抛出异常，应省略 `:raises` 段或写 `无`；当前写法读起来像是"会抛出 Exception 但不主动"，语义含混。
- **影响**: 不影响运行时行为；仅影响文档可读性。
- **建议修法**: 改为 `无` 或直接删除 `:raises` 段。
- **可裁决状态**: accepted（Low，不阻塞）。

### F2 - Low - `DISABLED` policy + `request_identity=None` 组合路径缺少直接测试

- **文件/行**: `tests/engine/runners/openai/test_request_identity.py`
- **证据**: 现有测试覆盖：
  - `test_policy_enabled_sends_x_client_request_id`：enabled + identity ✓
  - `test_policy_disabled_does_not_send_x_client_request_id`：disabled + identity ✓
  - `test_policy_enabled_without_identity_does_not_send_header`：enabled + None ✓
  - `test_policy_enabled_rejects_static_case_insensitive_header`：conflict ✓
  - `test_transport_retry_reuses_same_request_identity_header`：retry ✓
  - 但缺少：disabled + None（两个条件同时满足时不发送 header 的显式断言）。
- **影响**: 不影响正确性——代码逻辑已覆盖（disabled 直接 early return）；仅测试矩阵不完整。
- **建议修法**: 补一个 `test_policy_disabled_without_identity_does_not_send_header` 测试。
- **可裁决状态**: accepted（Low，不阻塞）。

### F3 - Low - `_build_request_headers` 末尾 `raise ValueError` 分支不可达

- **文件/行**: `dayu/engine/runners/openai/runner.py:191-194`
- **证据**: `ClientCorrelationPolicy` 是 `StrEnum`，当前只有 `DISABLED` 和 `OPENAI_X_CLIENT_REQUEST_ID` 两个成员。前面的 `if` 分支已覆盖所有可能值，末尾 `raise ValueError("unsupported client_correlation_policy: ...")` 在正常执行路径中不可达。
- **影响**: 不影响运行时行为；作为防御性代码可接受，但若未来新增 enum 成员而忘记在 `_build_request_headers` 中处理，此处会作为 fail-fast 生效——这是其存在价值。
- **建议修法**: 保留。若希望更明确，可加行内注释说明"防御性分支，当前不可达"。
- **可裁决状态**: rejected-with-reason（防御性保留，无害且有益）。

## Detailed Review Checklist

### ClientCorrelationPolicy 枚举语义、docstring、export

- `dayu/engine/contracts/runner_spec.py:72-91`：枚举定义正确，docstring 明确说明"provider-protocol-specific outbound mapping policies"，不是 provider-name branches。✓
- `dayu/engine/contracts/__init__.py:90,118`：从 `runner_spec` 导入并加入 `__all__`。✓
- 枚举值：`DISABLED = "disabled"`、`OPENAI_X_CLIENT_REQUEST_ID = "openai_x_client_request_id"`。✓
- 无 provider 字符串分支、无 `Any`/`object`、无兼容 wrapper。✓

### RunnerSpec 新 required field

- `dayu/engine/contracts/runner_spec.py:280`：`client_correlation_policy: ClientCorrelationPolicy` 作为 frozen dataclass 的 required field。✓
- 默认为 `DISABLED`：所有构造点显式传入 `ClientCorrelationPolicy.DISABLED`，无隐式默认值。✓
- 无兼容 wrapper / 旧 schema 兼容读取。✓
- production assembly `dayu/service/host_assembly.py:870` 传入 `DISABLED`。✓

### Host _execution_config_projection freeze / restore

- `dayu/host/_execution_config_projection.py:154-156`：`runner_spec_json` 序列化 `runner_spec.client_correlation_policy.value`。✓
- `dayu/host/_execution_config_projection.py:183-185`：`runner_spec_from_json` 通过 `ClientCorrelationPolicy(required_json_text(...))` 恢复。✓
- `test_effective_execution_config.py:261-298`：`test_effective_execution_config_round_trips_client_correlation_policy` 验证 `OPENAI_X_CLIENT_REQUEST_ID` round-trip。✓
- `test_effective_execution_config.py:312`：corrupted JSON 测试中 `"client_correlation_policy": "disabled"` 作为合法 fresh schema 字段。✓
- 无旧 schema 兼容读取。✓

### AsyncOpenAIRunner header helper

- `dayu/engine/runners/openai/runner.py:150-194`：`_build_request_headers` 模块级私有辅助函数。✓
- 起始于 `Content-Type: application/json`，合并 `spec.headers` 静态头。✓
- `DISABLED` policy → early return，不发送 `X-Client-Request-Id`。✓
- `OPENAI_X_CLIENT_REQUEST_ID` + `request_identity is not None` → 发送 header。✓
- `OPENAI_X_CLIENT_REQUEST_ID` + `request_identity is None` → 不发送 header（静默跳过）。✓
- 静态 headers 含 case-insensitive `x-client-request-id` → `ValueError`，HTTP post 前失败。✓
- `_has_client_request_id_header` 使用 `name.lower()` 做 case-insensitive 检查。✓

### Transport retry 复用同一 header

- `dayu/engine/runners/openai/runner.py:378-380`：`_build_request_headers` 在 `_call_impl` 中调用一次，结果传入 `_do_attempt(... headers=headers)`。✓
- `dayu/engine/runners/openai/runner.py:407`：`_do_attempt` 接收 `headers: Mapping[str, str]`，不再每次构造。✓
- retry 循环中同一 `headers` dict 被复用。✓
- `test_request_identity.py:192-229`：`test_transport_retry_reuses_same_request_identity_header` 验证两次 retry 的 header 值相同。✓

### Response x-request-id 采集

- `dayu/engine/runners/openai/runner.py`：`_extract_provider_request_id` 未被修改。✓
- 实现 artifact 确认"response x-request-id collection was not changed"。✓

### Direct RunnerSpec constructor sync

审查全部 30+ 个直接构造点，确认均为 `ClientCorrelationPolicy.DISABLED` 补齐：

- `dayu/service/host_assembly.py:870`：production assembly，`DISABLED`。✓
- `utils/smoke_async_agent_providers.py`：smoke script，`DISABLED`。✓
- `tests/engine/contracts/test_agent_run.py:135`：`DISABLED`。✓
- `tests/engine/test_agent_phase2.py:407`：`DISABLED`。✓
- `tests/engine/test_agent_phase3_tool_call.py:645`：`DISABLED`。✓
- `tests/engine/test_metadata_boundary.py:201`：`DISABLED`。✓
- `tests/host/public_smoke_support.py:816,912`：两处构造，均为 `DISABLED`。✓
- 其余 `tests/host/test_*.py` 约 20 个文件：均为单一 `_runner_spec()` 或 `_runner_spec(model)` helper 中补齐 `DISABLED`。✓
- 无任何构造点引入 enabled policy 或非 DISABLED 值。✓
- 无越过 Slice 3 / Tool Trace / Host ingest 行为的变更。✓

### `_factories.py` `_RunnerSpecChanges` TypedDict 改进

- `tests/engine/runners/openai/_factories.py:22-41`：`_RunnerSpecChanges(TypedDict, total=False)` 替代原 `**changes: object`。✓
- 消除了 `object` 类型签名，符合编码硬约束。✓
- 包含 `client_correlation_policy: ClientCorrelationPolicy`。✓

### 测试覆盖矩阵

| 场景 | 测试 | 状态 |
|---|---|---|
| policy enabled + identity 存在 → 发送 header | `test_policy_enabled_sends_x_client_request_id` | ✓ |
| policy disabled + identity 存在 → 不发送 | `test_policy_disabled_does_not_send_x_client_request_id` | ✓ |
| policy enabled + identity None → 不发送 | `test_policy_enabled_without_identity_does_not_send_header` | ✓ |
| policy enabled + 静态 conflict → ValueError | `test_policy_enabled_rejects_static_case_insensitive_header` | ✓ |
| transport retry 复用同一 header | `test_transport_retry_reuses_same_request_identity_header` | ✓ |
| effective config round-trip `client_correlation_policy` | `test_effective_execution_config_round_trips_client_correlation_policy` | ✓ |
| RunnerSpec field set 包含新字段 | `test_runner_spec_field_set_includes_supports_stream_usage` (updated) | ✓ |
| ClientCorrelationPolicy enum 值 | `test_client_correlation_policy_values` | ✓ |
| policy disabled + identity None → 不发送 | **缺失** | F2 |

### 编码硬约束检查

- `Any` / `object` / 无类型参数：未引入。`_factories.py` 用 `TypedDict` + `Unpack` 替代了原来的 `object`。✓
- docstring 中文完整：所有新增函数 / 类均有中文 docstring，含参数、返回值、异常。✓
- 无 provider 字符串治理分支：代码中无 `if provider == "openai"` 或类似分支。✓
- 无兼容性 wrapper / facade：无。✓
- 无胶水 seam / 无充分理由的 lazy import：无。✓
- 无魔法数字 / 魔法字符串：`_CLIENT_REQUEST_ID_HEADER_NAME` 和 `_CLIENT_REQUEST_ID_HEADER_NAME_LOWER` 均为模块级常量。✓

### AGENTS.md / README 触发

- Slice 2 修改了 `dayu/engine/contracts/` 和 `dayu/engine/runners/openai/`：按触发规则应更新 `dayu/engine/README.md`。
- implementation artifact 明确"README sync is deferred to the approved Slice 4"。✓
- accepted plan Slice 4 明确覆盖 README sync。✓
- 当前 slice 不修改 README 是正确的。

## Blocking Open Questions

无。

## Residual Risks

| 风险 | Owner | 状态 |
|---|---|---|
| Host ingest / Tool Trace 诊断 payload 投影 `client_correlation_id` | Slice 3 | deferred-with-owner |
| `RunInputBuilder.build()` 投影 `attempt_id/execution_id` 到 `AgentRunRequest` | Slice 3 | deferred-with-owner |
| native Anthropic runner policy / response request-id | future adapter slice | deferred-with-owner |
| production assembly 当前 `DISABLED`；启用需显式 config/profile 决策 | config/product decision | deferred-with-owner |
| README sync | Slice 4 | deferred-with-owner |

## Docs Decision

README sync 按 approved Slice 4 deferred。当前 slice 不修改 README。✓

## 结论

**pass**

- Findings: 3 条 Low severity，0 条 High/Medium。
- Blocking open questions: 无。
- 验证证据: 61 tests passed, pyright 0 errors, 全量 37 文件人工审查。
- 实现与 accepted plan 完全一致：`ClientCorrelationPolicy` 枚举语义正确、`RunnerSpec` 新 required field 所有构造点显式补齐且默认 `DISABLED`、Host freeze/restore 正确序列化、header helper 条件发送/拒绝 conflict/复用 retry 均符合预期、response x-request-id 采集未回退、无 provider 字符串分支、无兼容 wrapper、无类型违规。
