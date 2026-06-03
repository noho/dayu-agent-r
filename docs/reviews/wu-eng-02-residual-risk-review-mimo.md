# Code Review

## Scope

- Mode: current changes
- Branch: phaseflow/wu-eng-02-request-identity
- Base: HEAD (residual fix diff against committed WU-ENG-02)
- Output file: docs/reviews/wu-eng-02-residual-risk-review-mimo.md
- Included scope:
  - `dayu/engine/agent.py` — S1-R1 工具超时 client_correlation_id 透传
  - `dayu/engine/contracts/runner_spec.py` — S2-R2 static header conflict 前移
  - `dayu/engine/runners/openai/runner.py` — S2-R2 runner header 构造简化
  - `tests/engine/test_agent_phase3_tool_call.py` — S1-R1 / S1-R2 测试断言
  - `tests/engine/contracts/test_runner_spec.py` — S2-R2 RunnerSpec 边界测试
  - `tests/engine/runners/openai/test_request_identity.py` — S2-R2 runner 测试同步
  - `tests/host/test_run_attempt_transitions.py` — S3-R2 Host durable payload 测试
  - `docs/host/issues-implementation-control.md` — 总控 residual 表 / gate 状态更新
  - `docs/reviews/wu-eng-02-residual-risk-fix-codex.md` — fix gate artifact
- Excluded scope: 整个 WU-ENG-02 其它已通过 review 的 slices
- Parallel review coverage: 无

## Verdict

**pass** — 4 条 residual risk 的 fix 均语义正确、测试充分、分层合理；S3-R1 的 defer 理由成立；总控文档更新准确。未发现 blocking findings。

## Findings

### 1-未修复-低-RunnerSpec 冲突校验只覆盖 policy 开启 + 静态 header 含 X-Client-Request-Id，未覆盖其它 policy 值

- **入口/函数**: `RunnerSpec.__post_init__()` / `dayu/engine/contracts/runner_spec.py:350-359`
- **文件(行号)**: `dayu/engine/contracts/runner_spec.py:350-359`
- **输入场景**: `client_correlation_policy` 不是 `OPENAI_X_CLIENT_REQUEST_ID` 也不是 `DISABLED`（未来扩展 enum 成员时）
- **实际分支**: 只检查 `is OPENAI_X_CLIENT_REQUEST_ID`，其它 policy 值跳过此校验
- **预期行为**: 当前 `ClientCorrelationPolicy` 只有 `DISABLED` 和 `OPENAI_X_CLIENT_REQUEST_ID` 两个成员，穷尽检查已隐式成立
- **实际行为**: 如果未来新增 policy 成员，该成员下静态 header 冲突不会被 `__post_init__` 捕获，但 OpenAI runner 的 `_build_request_headers` 已有 `raise ValueError("unsupported client_correlation_policy: ...")` 兜底
- **直接证据**: `dayu/engine/contracts/runner_spec.py:350-354` 的 `is` 比较；`dayu/engine/runners/openai/runner.py:182-185` 的兜底 ValueError
- **影响**: 低。当前 enum 只有两个成员，且 OpenAI runner 有兜底；未来扩展时需同步处理
- **建议改法和验证点**: 无需修改；若未来新增 policy 成员，需在 `__post_init__` 和 `_build_request_headers` 同步评估
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-_has_openai_client_request_id_header 模块级私有函数从 runner 移到 runner_spec，但 runner_spec 现在同时承载常量定义和冲突检测

- **入口/函数**: `OPENAI_CLIENT_REQUEST_ID_HEADER_NAME` / `_has_openai_client_request_id_header()` / `dayu/engine/contracts/runner_spec.py`
- **文件(行号)**: `dayu/engine/contracts/runner_spec.py:238-373`
- **输入场景**: OpenAI-specific header 名称常量和冲突检测逻辑出现在 Engine 公共契约层
- **实际分支**: 常量 `OPENAI_CLIENT_REQUEST_ID_HEADER_NAME` 定义在 `runner_spec.py` 并通过 `__all__` 导出；冲突检测 `_has_openai_client_request_id_header` 是模块级私有函数
- **预期行为**: `RunnerSpec` 是 provider-neutral 的公共契约；OpenAI-specific header 名称常量放在其中是合理的，因为 `RunnerSpec` 本身就承载 `ClientCorrelationPolicy`（当前两个成员都是 OpenAI-specific 的）
- **实际行为**: 常量和冲突检测前移到 `RunnerSpec` construction boundary，符合"fail fast at construction time"原则；runner 只负责 header 映射，不重复冲突判断
- **直接证据**: `runner_spec.py:238-244` 定义常量；`runner_spec.py:350-359` 冲突校验；`runner.py:174-181` 只做 header 映射
- **影响**: 低。当前 `ClientCorrelationPolicy` 已经是 OpenAI-specific 的，常量放在 `runner_spec` 不引入新的耦合维度
- **建议改法和验证点**: 无需修改；若未来引入 native Anthropic policy，需重新评估常量归属
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 按 residual risk 逐条裁决

### S1-R1: 工具超时 terminal RunFailedData 写入 current tool batch client_correlation_id

**结论: accept — 语义正确且测试充分。**

直接证据链：

1. `_execute_tool_batch()` 中 `WaitTimedOut` 分支已有 `decision.client_correlation_id`（`agent.py:1672-1675`）
2. `_make_tool_timeout_terminal_with_close()` 现在显式接收 `client_correlation_id` keyword-only 参数（`agent.py:2144-2145`）
3. 构造 `RunFailedData` 时写入该字段（`agent.py:2161`）
4. 测试 `test_tool_execution_timeout_fails_run_without_tool_result` 断言 `failed.client_correlation_id == runner.request_identities_seen[0].client_correlation_id`（`test_agent_phase3_tool_call.py:1800-1803`）
5. 测试 `test_tool_execution_timeout_wins_over_cleanup_cancel` 同样断言（`test_agent_phase3_tool_call.py:1838-1841`）

语义正确性：工具超时发生在 Runner tool call decision 产出后的工具执行等待阶段，`decision.client_correlation_id` 是触发该工具批的 Runner request identity，写入 terminal `RunFailedData` 保持了同一数据链路的信息完整性。

测试充分性：两个 timeout 测试分别覆盖了普通 timeout 和 cancel+timeout 竞争场景，且都直接断言 `client_correlation_id` 值。

### S1-R2: force-answer failure 的 emitted EngineEvent 直接断言

**结论: accept — 断言充分。**

直接证据链：

1. `_run_force_answer()` 通过 `_run_runner_iteration()` 调用 Runner，每次调用 `_next_runner_request_identity()` 生成新 identity
2. force-answer 是第二次 Runner 调用（`request_identities_seen[1]`）
3. 空内容路径 `_run_force_answer` 中 `_classify_iteration` 返回 `_FinalDecision` 后检查 `content == ""`，构造 `RunFailedData` 时使用 `_client_correlation_id_from_state(state)`（`agent.py:2098-2101`）
4. tool-call-not-enabled 路径同样使用 `_client_correlation_id_from_state(state)`（`agent.py:2078-2082`）
5. 测试 `test_force_answer_empty_and_tool_call_are_fail_closed` 对两个子场景都断言 `failure.client_correlation_id == runner.request_identities_seen[1].client_correlation_id`（`test_agent_phase3_tool_call.py:1935-1938, 1961-1964`）

语义正确性：force-answer 是第二次逻辑 Runner 调用，使用第二次 request identity 是正确的。

测试充分性：测试覆盖了 force-answer 空内容和继续 tool call 两个失败路径，均直接断言 emitted `RunFailedData.client_correlation_id`。

### S2-R2: static header conflict 前移到 RunnerSpec construction boundary

**结论: accept — 符合分层与 contract，未引入过度耦合或破坏 disabled policy。**

直接证据链：

1. `RunnerSpec.__post_init__()` 新增冲突校验：`client_correlation_policy == OPENAI_X_CLIENT_REQUEST_ID` 且静态 headers 含大小写不敏感 `X-Client-Request-Id` 时抛 `ValueError`（`runner_spec.py:350-359`）
2. OpenAI runner 删除了重复的冲突检测 `_has_client_request_id_header`，只负责 header 映射（`runner.py:174-181`）
3. 测试 `test_runner_spec_rejects_static_openai_client_request_id_conflict` 覆盖 policy 开启 + 静态 header 冲突（`test_runner_spec.py:239-250`）
4. 测试 `test_runner_spec_allows_static_openai_client_request_id_when_policy_disabled` 覆盖 policy 关闭时允许静态 header（`test_runner_spec.py:253-263`）
5. 测试 `test_policy_enabled_rejects_static_case_insensitive_header` 已从 async runner 测试同步为 construction-time failure 断言（`test_request_identity.py:189-196`）

分层正确性：冲突语义属于 `RunnerSpec` 自身的一致性约束，前移到 construction boundary 是正确的。OpenAI runner 只负责 policy 允许时的 header 映射，不重复冲突判断。

disabled policy 完整性：测试明确覆盖了 policy disabled 时静态 `X-Client-Request-Id` 允许存在，不破坏显式 disabled 策略。

### S3-R2: ContextRecoveryCloseInput.client_correlation_id focused durable payload/validation tests

**结论: accept — 测试足够。**

直接证据链：

1. `ContextRecoveryCloseInput.client_correlation_id` 已存在（`run_transition.py:425`）
2. `_validate_context_recovery_close_input()` 调用 `_require_optional_non_empty_text(..., field_name="client_correlation_id")`（`run_transition.py:5314-5316`）
3. `_context_recovery_attempt_failed_event_request()` 把 `client_correlation_id` 写入 `ATTEMPT_FAILED` payload（`run_transition.py:3137`）
4. `_run_recovering_event_request()` 把 `client_correlation_id` 写入 `RUN_RECOVERING` payload（`run_transition.py:3191`）
5. 测试 `test_context_recovery_close_payload_includes_client_correlation_id` 直接断言两个 payload 的 `client_correlation_id` 值为 `"client-recovery"`（`test_run_attempt_transitions.py:2090-2091`）
6. 测试 `test_context_recovery_close_rejects_empty_client_correlation_id` 断言空白值被 `HostDurableError` 拒绝（`test_run_attempt_transitions.py:2110-2111`）

测试充分性：覆盖了 payload 写入和 validation 拒绝两个方向，直接断言 durable EventLog payload 内容。

### S3-R1: usage observation client_correlation_id defer 判断

**结论: accept defer — 确实必须 defer 到 WU-OBS-00 / issue-70。**

直接证据：

1. `UsageReportedData`（`engine_events.py:277-289`）只有 `iteration_id`、`prompt_tokens`、`completion_tokens`、`total_tokens`，没有 `client_correlation_id` 或 `provider_request_id`
2. `engine_ingest.py` 的 usage projection payload 中 `provider_request_id` 是 hardcoded `None`
3. 给 usage observation 增加 `client_correlation_id` 需要先扩展 Engine `UsageReportedData` contract，这属于 analyzer signal contract 范围
4. 不扩展 contract 就无法同源传入 `client_correlation_id`，只能从 Host 侧硬编码或从 iteration state 旁路取值，违反"数据同源"原则

defer 理由成立：需要先由 WU-OBS-00 / GitHub Issue #70 裁决 `UsageReportedData` 是否承载 client correlation 以及 analyzer 如何消费。当前 WU 不应扩大到 analyzer contract。

## Open Questions

无。

## Residual Risk

- S3-R1 保留 `deferred-with-owner`，owner 为 WU-OBS-00 / GitHub Issue #70 analyzer。当前不阻塞 provider debugging correlation 主链路。
- `RunnerSpec` 的 `OPENAI_CLIENT_REQUEST_ID_HEADER_NAME` 常量和 `_has_openai_client_request_id_header` 函数在 Engine 公共契约层，当前合理（因为 `ClientCorrelationPolicy` 已是 OpenAI-specific），但若未来引入 native Anthropic policy 需重新评估归属。

## 总控文档审查

- residual 表 4 条状态更新准确：S1-R1、S1-R2、S2-R2、S3-R2 改为 `closed`，S3-R1 保留 `deferred-with-owner`。
- gate 状态从 `draft-PR-pass` 更新为 `review`，implementation status 为 `residual-risk-review-in-progress`，准确。
- review artifacts 列表新增 `docs/reviews/wu-eng-02-residual-risk-fix-codex.md`，准确。
- WU-ENG-02 状态描述末尾新增 residual risk fix gate 完成记录，准确。
- draft PR status 更新为 `reopened for residual-risk review`，准确。

## 验证命令

```bash
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/contracts/test_runner_spec.py tests/engine/runners/openai/test_request_identity.py tests/host/test_run_attempt_transitions.py
```

结果：125 passed in 0.67s。

```bash
source .venv/bin/activate && pyright
```

结果：0 errors, 0 warnings, 0 informations。
