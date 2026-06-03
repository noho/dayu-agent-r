# WU-ENG-02 Slice 1 Code Review - AgentMiMo

## Gate / Work Unit / Slice

- gate: code review
- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- slice id: Slice 1 - Engine Contract And Agent Identity
- agent: AgentMiMo
- review type: deepreview

## Review Target

当前未提交 workspace changes for Slice 1。审查 `git diff HEAD` 与 implementation artifact `docs/reviews/wu-eng-02-slice1-implementation-codex.md`。

## Changed Files

### Slice 1 核心文件

| 文件 | 变更类型 |
|---|---|
| `dayu/engine/contracts/runner_identity.py` | 新增模块 |
| `dayu/engine/contracts/runner.py` | 签名扩展 |
| `dayu/engine/contracts/agent_run.py` | 字段扩展 + 校验 |
| `dayu/engine/contracts/engine_events.py` | 字段扩展 |
| `dayu/engine/contracts/__init__.py` | 导出扩展 |
| `dayu/engine/agent.py` | identity 构造 + 传递 + 诊断关联 |
| `tests/engine/contracts/test_runner_identity.py` | 新增测试 |
| `tests/engine/contracts/test_agent_run.py` | 扩展测试 |
| `tests/engine/test_agent_phase2.py` | 签名同步 + identity 断言 |
| `tests/engine/test_agent_phase3_tool_call.py` | 签名同步 + identity 断言 |
| `tests/engine/test_metadata_boundary.py` | 签名同步 + 字段断言 |

### 最小签名同步文件（compile/type 兼容）

| 文件 | 变更类型 |
|---|---|
| `dayu/engine/runners/openai/runner.py` | 接受并忽略 `request_identity` |
| `tests/host/public_smoke_support.py` | fake runner 签名同步 |
| `tests/host/test_phase6_toolruntime_integration.py` | fake runner 签名同步 |

### 总控文档更新

| 文件 | 变更类型 |
|---|---|
| `docs/host/issues-implementation-control.md` | 状态更新（implementation -> code review） |

## Validation Evidence

| 验证项 | 结果 |
|---|---|
| `pytest tests/engine/contracts/test_runner_identity.py tests/engine/contracts/test_agent_run.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py tests/engine/test_metadata_boundary.py` | 127 passed |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| git diff | 已审查全部未提交变更 |

## Findings

### F-01: `RunFailedData` 部分实例化路径未显式传递 `client_correlation_id`

- **Severity**: Low
- **Status**: accepted
- **Location**: `dayu/engine/agent.py` 多处
- **证据**:

以下 `RunFailedData` 实例化未显式传递 `client_correlation_id`，依赖 dataclass 默认值 `None`：

| 行号 | 错误码 | 上下文 | 是否可获取 correlation |
|---|---|---|---|
| 661 | `_ERROR_MAX_ITERATIONS_EXCEEDED` | pre-loop guard, `max_iterations < 1` | 否，无 iteration state |
| 719 | `_ERROR_MISSING_TERMINAL` | `_run_runner_iteration` 返回后 state is None | 否，critical-only 路径 |
| 833 | `_ERROR_MISSING_TERMINAL` | tool batch ended without result | 否，batch 级错误 |
| 1166 | `_ERROR_MISSING_TERMINAL` | runner exception 时 state is None | 否，critical-only 路径 |
| 1831/1838 | `_ERROR_TOOL_BATCH_OUTCOME_MISMATCH` | `_validate_tool_batch_outcome` helper | 是，caller 有 `decision.client_correlation_id` |
| 1982 | `RAISE_ERROR` fallback | `_fallback_after_tools` | 是，caller 有 state |
| 2144 | `_ERROR_TOOL_EXECUTION_TIMEOUT` | `_make_tool_timeout_terminal_with_close` | 是，caller 有 `decision.client_correlation_id` |
| 2554 | `_ERROR_MISSING_TERMINAL` | `_classify_runner_call_completed` state is None | 否，critical-only 路径 |

- **影响**: 无功能影响。`RunFailedData.client_correlation_id` 默认值为 `None`，语义正确——这些路径要么是控制流守卫（无 provider call context），要么是工具批处理校验/超时（非 provider response 错误）。provider 相关的失败路径（protocol error、runner exception、context compaction required 等）均已通过 `_client_correlation_id_from_state(state)` 正确传递。
- **建议**: 当前可接受。若后续需要在 tool batch mismatch / timeout / RAISE_ERROR 路径也携带 correlation，可将 `client_correlation_id` 作为参数传入 `_validate_tool_batch_outcome` 和 `_fallback_after_tools`。不影响 Slice 1 验收。

### F-02: `RunnerRequestIdentity.__post_init__` 与 `build_runner_request_identity` 重复校验

- **Severity**: Info
- **Status**: accepted
- **Location**: `dayu/engine/contracts/runner_identity.py:49-81` 与 `:104-128`
- **证据**: `build_runner_request_identity` 在构造前调用 `_validate_identity_inputs`；构造 `RunnerRequestIdentity(...)` 时 `__post_init__` 再次调用 `_validate_identity_inputs` 和 `_validate_client_correlation_id`。两次校验完全相同。
- **影响**: 无功能影响，性能开销可忽略。直接构造 `RunnerRequestIdentity(...)` 时 `__post_init__` 是唯一校验入口，保留它是正确的防御性设计。
- **建议**: 不修改。直接构造路径需要 `__post_init__` 校验，builder 路径的重复校验是可接受的防御冗余。

### F-03: `_encode_canonical_part` 类型前缀编码方案的碰撞安全性

- **Severity**: Info
- **Status**: accepted
- **Location**: `dayu/engine/contracts/runner_identity.py:255-273`
- **证据**: 编码方案使用 `s:len:value`（字符串）、`i:value`（整数）、`n`（None）前缀，以 `|` 分隔各部分。字符串值中包含的 `|` 不会导致碰撞，因为每个值都带有长度前缀。类型前缀确保 None、整数和文本之间无歧义。
- **影响**: 无。编码方案在理论上是无碰撞的。
- **建议**: 不修改。

## 审查清单逐项裁决

### RunnerRequestIdentity / build_runner_request_identity

| 检查项 | 结果 |
|---|---|
| 严格类型 | ✅ frozen dataclass，全部字段有显式类型注解 |
| 安全性 | ✅ `__post_init__` 校验所有不变量 + client_correlation_id 一致性 |
| 稳定性 | ✅ canonical tuple 编码使用类型前缀 + 长度，无碰撞风险 |
| 中文 docstring 完整 | ✅ 模块、类、函数、私有辅助函数均有完整中文 docstring（参数/返回/异常） |
| digest 格式 | ✅ `dayu-` + 64 lowercase SHA-256 hex = 69 字符 |
| canonical tuple | ✅ 包含 `run_id`, `attempt_id`, `execution_id`, `iteration_id`, `iteration_index`, `runner_call_index` |

### AgentRunRequest attempt_id/execution_id

| 检查项 | 结果 |
|---|---|
| 成对校验 | ✅ `(attempt_id is None) != (execution_id is None)` 时 raise ValueError |
| 默认 None | ✅ 默认 `None`，服务 direct Engine / compactor 路径 |
| docstring | ✅ 中文 docstring 说明了 direct Engine / non-attempt 路径语义 |

### AsyncRunner.call 签名

| 检查项 | 结果 |
|---|---|
| 只新增 keyword-only | ✅ `*, request_identity: RunnerRequestIdentity \| None` |
| 现有参数不变 | ✅ `messages`, `options`, `tools` 保持 positional |
| fake runner 同步 | ✅ `_ScriptedRunner`, `_PublicEntryDefaultRunner`, `_MetadataBoundaryRunner`, `_ScriptedToolRunner`, `_AwaitingToolRunner`, `_StateClearingRunner` 全部同步 |

### _AsyncAgent runner_call_index 递增

| 路径 | 递增方式 | 结果 |
|---|---|---|
| normal iteration | `_run_runner_iteration` -> `_next_runner_request_identity` | ✅ |
| tool-loop re-entry | 主循环再次调用 `_run_runner_iteration` | ✅ |
| length continuation | 主循环 continuation_active 再次调用 `_run_runner_iteration` | ✅ 测试验证 `runner_call_index == [1, 2]` |
| force-answer/fallback | `_run_force_answer` 调用 `_run_runner_iteration` | ✅ 测试验证 `runner_call_index == [1, 2]` |
| RAISE_ERROR fallback | `_fallback_after_tools` 不调用 Runner | ✅ 不递增是正确的 |

### client_correlation_id 进入 EngineEvent / outcome

| 目标类型 | 字段添加 | 结果 |
|---|---|---|
| `ContextCompactionRequestedData` | ✅ `client_correlation_id: str \| None = None` | |
| `ProviderProtocolErrorData` | ✅ `client_correlation_id: str \| None = None` | |
| `IterationCompletedData` | ✅ `client_correlation_id: str \| None = None` | |
| `RunFailedData` | ✅ `client_correlation_id: str \| None = None` | |
| `EngineRunOutcomeFailed` | ✅ `client_correlation_id: str \| None = None` | |
| `RunnerEvent` | ✅ 不携带 Host ownership，符合 plan 非目标 | |

### 额外改动文件

| 文件 | 是否最小签名同步 | 是否越过 Slice 2/3 |
|---|---|---|
| `dayu/engine/runners/openai/runner.py` | ✅ `del request_identity`，不实现 header 映射 | 否 |
| `tests/host/public_smoke_support.py` | ✅ 只加 keyword-only 参数 + `del` | 否 |
| `tests/host/test_phase6_toolruntime_integration.py` | ✅ 只加 keyword-only 参数 + `del` | 否 |

### 测试覆盖

| 场景 | 覆盖 | 证据 |
|---|---|---|
| force-answer | ✅ `test_oversized_tool_message_is_passed_to_force_answer_runner_call` 验证 `runner_call_index == [1, 2]` |
| length continuation | ✅ `test_length_continuation_appends_prompt_and_joins_content` 验证 `runner_call_index == [1, 2]` |
| tool-loop re-entry | ✅ `test_completed_tool_call_injects_messages_and_reaches_final` 验证 `runner_call_index == [1, 2]` |
| direct request validation | ✅ `test_runner_request_identity_*` 系列覆盖空字段、负序号、不成对 attempt/execution、非 canonical id |
| digest 稳定性 | ✅ `test_runner_request_identity_builds_stable_lowercase_digest` |
| digest 跨 iteration/call 变化 | ✅ `test_runner_request_identity_changes_across_iteration_and_call` |

### AGENTS.md 合规

| 检查项 | 结果 |
|---|---|
| Any/object/无类型签名 | ✅ 无新增 |
| docstring 缺参数/返回/异常 | ✅ 全部完整 |
| lazy import | ✅ 无新增 |
| provider 字符串治理分支 | ✅ 无新增 |
| README 触发风险 | ✅ README sync deferred to Slice 4（plan approved） |

## Blocking Open Questions

无。

## Docs / README Decision

当前 Slice 1 不修改 README 文件。README sync 已在 plan 中批准延至 Slice 4 实施。

## Residual Risks

| 风险 | Owner |
|---|---|
| `dayu/engine/runners/openai/runner.py` 当前只接受 `request_identity`，不实现 header 映射 | Slice 2 |
| 无 `RunnerSpec.client_correlation_policy` | Slice 2 |
| Host `RunInputBuilder` 未投影 `attempt_id/execution_id` 到 `AgentRunRequest` | Slice 3 |
| Host ingest / Tool Trace 未持久化 `client_correlation_id` | Slice 3 |

## 结论

**pass**

- 0 条 blocking findings
- 3 条 Low/Info findings，均为可接受的一致性细节或防御性冗余
- 实现严格对齐 plan Slice 1 scope，无越界行为
- 127 tests passed，pyright 0 errors
- 所有 logical Runner call 路径正确递增 `runner_call_index` 并传递 non-None identity
- provider 相关失败路径正确传递 `client_correlation_id`
