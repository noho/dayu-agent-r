# WU-ENG-02 Residual Risk Fix 复审

## Scope

- Mode: current changes (working tree vs HEAD)
- Branch: phaseflow/wu-eng-02-request-identity
- Base: HEAD (residual fix diff, not full WU diff)
- Output file: docs/reviews/wu-eng-02-residual-risk-review-ds.md
- Included scope:
  - `dayu/engine/agent.py` — S1-R1 工具超时 + S1-R2 force-answer 路径
  - `dayu/engine/contracts/runner_spec.py` — S2-R2 静态 header 冲突前移
  - `dayu/engine/runners/openai/runner.py` — S2-R2 runner 层简化
  - `tests/engine/test_agent_phase3_tool_call.py` — S1-R1 + S1-R2 测试
  - `tests/engine/contracts/test_runner_spec.py` — S2-R2 construction-time 测试
  - `tests/engine/runners/openai/test_request_identity.py` — S2-R2 测试同步
  - `tests/host/test_run_attempt_transitions.py` — S3-R2 durable 测试
  - `docs/host/issues-implementation-control.md` — 总控文档更新
- Excluded scope:
  - 已 merge 的 WU-ENG-02 主体 diff（只审 residual fix 增量）
  - Codex fix artifact 本身 (`docs/reviews/wu-eng-02-residual-risk-fix-codex.md`)
- Parallel review coverage: 无
- 验证基线: 125 tests passed, pyright 0 errors

## Findings

### F1-未修复-低-S1-R1 工具超时 `test_tool_execution_timeout_wins_over_runner_close_cancel` 缺 `client_correlation_id` 断言

- **入口/函数**: `test_tool_execution_timeout_wins_over_runner_close_cancel`
- **文件(行号)**: tests/engine/test_agent_phase3_tool_call.py:1848-1875
- **输入场景**: 工具超时后 runner close 触发 late cancel
- **实际分支**: 测试断言了 `error_code`、`recoverable`、`executor.cancelled`、`token.is_cancelled()`、`runner.close_count`、terminal type，但未断言 `client_correlation_id`
- **预期行为**: 同前两个超时测试，应断言 `failed.client_correlation_id == runner.request_identities_seen[0].client_correlation_id`
- **实际行为**: 缺断言，导致该变体不参与 S1-R1 回归保护
- **直接证据**: 同文件的 `test_tool_execution_timeout_fails_run_without_tool_result` (line 1800-1803) 和 `test_tool_execution_timeout_wins_over_cleanup_cancel` (line 1838-1841) 均已加入正确断言；`test_tool_execution_timeout_wins_over_runner_close_cancel` (line 1869-1875) 是三个超时变体中唯一未加入的。
- **影响**: 局部测试覆盖缺口。当前不影响正确性——生产代码 (`_execute_tool_batch` → `_make_tool_timeout_terminal_with_close`) 三条超时路径走同一代码分支，语义相同。但若未来 runner close cancel 路径被独立重构，此测试可能不报错。
- **建议改法和验证点**: 在 `test_tool_execution_timeout_wins_over_runner_close_cancel` 中补齐与另外两个超时测试一致的 `client_correlation_id` 断言。验证：`pytest tests/engine/test_agent_phase3_tool_call.py::test_tool_execution_timeout_wins_over_runner_close_cancel -q`
- **修复风险（低）**: 纯测试补充，不改变生产代码
- **严重程度（低）**: 测试覆盖缺口，非生产缺陷

## 分项裁决

### S1-R1: 工具超时 `RunFailedData` 写入 `decision.client_correlation_id`

**裁决: accepted**

证据链:

1. `_execute_tool_batch()` 中 `decision.client_correlation_id` 来自触发当前工具批的 `_ToolCallsDecision`（agent.py:1674-1677），该 decision 由第一次 Runner 调用的 `_classify_iteration()` 产出，其 `client_correlation_id` 即第一次 Runner request identity。
2. `_make_tool_timeout_terminal_with_close()` 现接收 `client_correlation_id: str | None` 参数（agent.py:2144-2146），写入 terminal `RunFailedData`（agent.py:2161）。
3. 测试 `test_tool_execution_timeout_fails_run_without_tool_result` 断言 `failed.client_correlation_id == runner.request_identities_seen[0].client_correlation_id`（test_agent_phase3_tool_call.py:1800-1803）。`runner.call_count == 1` 确认只有一个 Runner call，`request_identities_seen[0]` 即产出工具批 decision 的调用，语义正确。
4. 测试 `test_tool_execution_timeout_wins_over_cleanup_cancel` 同样断言（test_agent_phase3_tool_call.py:1838-1841），覆盖 cleanup cancel 不覆盖超时错误的场景。

语义正确性: 工具超时发生在工具执行等待阶段，当前工具批由第一次 Runner call 的 `_ToolCallsDecision` 触发。terminal closeout 写入该 decision 的 `client_correlation_id` 是同一数据链路内的信息补齐，不是语义变更。Provider 侧无对应请求（工具超时不发 HTTP），`provider_request_id=None` 保持为空，合规。

测试充分性: 两个超时变体已覆盖直接断言。第三条路径（runner close cancel 变体）缺断言，见 F1。F1 不阻塞此裁决。

### S1-R2: force-answer failure 的 emitted EngineEvent 直接断言

**裁决: accepted**

证据链:

1. `_run_force_answer()` 调用 `_run_runner_iteration()`（agent.py:2032），后者通过 `_next_runner_request_identity()` 生成新的 request identity（agent.py:1072），写入 `_last_iteration_state`（agent.py:1076-1090）。因此 force-answer 是第二次逻辑 Runner 调用。
2. force-answer 空内容路径: `_classify_iteration()` 返回 `_FinalDecision(content="")`，构造 `RunFailedData(error_code=force_answer_empty)` 时使用 `_client_correlation_id_from_state(state)`（agent.py:2099-2101），该 helper 从 `state.request_identity.client_correlation_id` 取值（agent.py:544-546）。
3. force-answer 继续 tool call 路径: `_classify_iteration()` 返回 `_ToolCallsDecision`，构造 `RunFailedData(error_code=tool_call_not_enabled)` 同样使用 `_client_correlation_id_from_state(state)`（agent.py:2080-2082）。
4. 测试中 `empty_runner` 有两个 scripts（第一个 tool script + 第二个 final script），`request_identities_seen[1]` 即第二次 Runner call 的 identity。断言 `empty_failure.client_correlation_id == empty_runner.request_identities_seen[1].client_correlation_id`（test_agent_phase3_tool_call.py:1935-1938）正确关联到 force-answer 迭代。
5. `tool_call_runner` 同样有两个 scripts，断言 `force_tool_failure.client_correlation_id == tool_call_runner.request_identities_seen[1].client_correlation_id`（test_agent_phase3_tool_call.py:1961-1964），同时保留 `provider_request_id == "req_force_tool"` 断言（line 1960），两个关联维度均有锁。

测试充分性: 两个 force-answer failure 分支均有直接 `client_correlation_id` 断言，且引用正确的 Runner call index（第二次调用）。provider_request_id 断言与 client_correlation_id 断言共存，互不削弱。

### S2-R2: static header conflict 前移到 RunnerSpec construction boundary

**裁决: accepted**

证据链:

1. 冲突检测从 `_build_request_headers()`（原 OpenAI runner）迁移到 `RunnerSpec.__post_init__()`（runner_spec.py:350-359）。当 `client_correlation_policy == OPENAI_X_CLIENT_REQUEST_ID` 且静态 headers 含大小写不敏感的 `X-Client-Request-Id` 时，立即抛 `ValueError`。
2. `_has_openai_client_request_id_header()`（runner_spec.py:362-373）大小写不敏感匹配，用 `name.lower() == _OPENAI_CLIENT_REQUEST_ID_HEADER_NAME_LOWER`。
3. `OPENAI_CLIENT_REQUEST_ID_HEADER_NAME` 常量从 runner.py 移入 runner_spec.py 并加入 `__all__`（runner_spec.py:241, 401）。OpenAI runner 改为 import 该常量（runner.py:54, 178），只负责 header 映射，不再重复校验。
4. OpenAI runner `_build_request_headers()` 的 `raises` docstring 从 "policy 开启且静态 headers 已包含时抛出" 改为 "policy 值不受当前 adapter 支持时抛出"（runner.py:164），与实现一致。

分层合规性:

- RunnerSpec 是 Engine contract 层的构造型规约对象，其 `__post_init__` 负责拒绝语义不一致的字段组合。静态 header 与 per-call policy 冲突属于规约自身的语义不一致，应在 construction boundary fail fast。
- OpenAI runner 是 Engine adapter 层，只负责 HTTP 映射。原实现让 adapter 做 contract validation 是职责倒置，新实现将 validation 归位到 contract 层，adapter 只做 mapping。
- Header 名称常量 `OPENAI_CLIENT_REQUEST_ID_HEADER_NAME` 是 OpenAI-compatible 协议事实，放在 contract 层（runner_spec.py）供 adapter 引用，比放在 adapter 内部更合理——其他 OpenAI-compatible adapter 也应使用同一常量。

未引入过度耦合: RunnerSpec 不依赖 OpenAI runner 或任何具体 adapter；`_has_openai_client_request_id_header()` 是模块级私有辅助函数，仅被 `__post_init__` 调用；`OPENAI_X_CLIENT_REQUEST_ID` 是 `ClientCorrelationPolicy` 枚举成员，策略值本身是 contract 层定义。

未破坏 disabled policy: `ClientCorrelationPolicy.DISABLED` 不走冲突检测分支（`__post_init__` 只在 `OPENAI_X_CLIENT_REQUEST_ID` 时检测）。测试 `test_runner_spec_allows_static_openai_client_request_id_when_policy_disabled` 明确覆盖 DISABLED + 静态 header 可通过 construction。

测试覆盖:
- `test_runner_spec_rejects_static_openai_client_request_id_conflict`（tests/engine/contracts/test_runner_spec.py:242-252）: policy 启用 + 小写 header → ValueError
- `test_runner_spec_allows_static_openai_client_request_id_when_policy_disabled`（tests/engine/contracts/test_runner_spec.py:255-263）: policy DISABLED + 静态 header → 允许通过
- `test_policy_enabled_rejects_static_case_insensitive_header`（tests/engine/runners/openai/test_request_identity.py:192-199）: 改为 construction-time 断言，验证 `_runner()` 工厂在构造阶段即失败

### S3-R2: ContextRecoveryCloseInput.client_correlation_id 的 focused durable payload/validation tests

**裁决: accepted**

证据链:

1. `test_context_recovery_close_payload_includes_client_correlation_id`（tests/host/test_run_attempt_transitions.py:2052-2092）:
   - 通过 `_seed_running_run()` 创建 seeded run/attempt，构造 `ContextRecoveryCloseInput(client_correlation_id="client-recovery")`
   - 调用 `close_attempt_for_context_recovery_in_transaction()` 执行 durable write
   - 通过 `_event_payload()` 直接从事务读取 `ATTEMPT_FAILED` 和 `RUN_RECOVERING` 事件的 EventLog payload
   - 断言 `attempt_payload["client_correlation_id"] == "client-recovery"` 和 `run_payload["client_correlation_id"] == "client-recovery"`
   - 这是 durable 层的直接 payload 断言，不是下游 projection 间接证明

2. `test_context_recovery_close_rejects_empty_client_correlation_id`（tests/host/test_run_attempt_transitions.py:2095-2122）:
   - 构造 `ContextRecoveryCloseInput(client_correlation_id=" ")`（仅空白字符）
   - 断言 `close_attempt_for_context_recovery_in_transaction()` 抛出 `HostDurableError(match="client_correlation_id")`
   - 验证输入校验边界 `_require_optional_non_empty_text(..., field_name="client_correlation_id")` 拒绝空白值

3. 辅助函数 `_context_recovery_input()`（tests/host/test_run_attempt_transitions.py:2645-2670）:
   - 参数类型 `client_correlation_id: str | None`，与生产代码签名一致
   - 所有必填字段显式命名传参，避免隐式默认

测试充分性: payload test 覆盖 gold path（入 durable → 出 payload）；validation test 覆盖空白拒绝路径。`None` 接受路径已有现有 context recovery closeout 测试覆盖（那些测试不传 `client_correlation_id`，默认 `None`）。

### S3-R1: UsageReportedData 是否必须 defer 到 WU-OBS-00 / issue-70

**裁决: deferred-with-owner（可接受但非硬性必须）**

分析:

**（1）当前状态**

- `UsageReportedData`（engine_events.py:277-289）仅有 `iteration_id`、`prompt_tokens`、`completion_tokens`、`total_tokens` 四个字段，无 `client_correlation_id`、无 `provider_request_id`。
- 构造点: agent.py `_consume_runner_event()` line 1256-1263，从 `RunnerUsageRecordedData` 构造时只传 token 计数。
- Host ingest `_append_projection_signal()`（engine_ingest.py:2246-2262）payload 中 `"provider_request_id": None` 硬编码。

**（2）可完成的最小同源修复**

若用户决定不在 WU-OBS-00 前 defer，可在当前 PR 完成以下 3 文件 ~6 行改动:

```python
# 文件 1: dayu/engine/contracts/engine_events.py
# UsageReportedData 加字段（默认 None，向后兼容）
client_correlation_id: str | None = None

# 文件 2: dayu/engine/agent.py line 1256-1263
# 构造 UsageReportedData 时传入
data=UsageReportedData(
    iteration_id=iteration_id,
    prompt_tokens=data.prompt_tokens,
    completion_tokens=data.completion_tokens,
    total_tokens=data.total_tokens,
    client_correlation_id=_client_correlation_id_from_state(state),
),

# 文件 3: dayu/host/engine_ingest.py line 2246-2262
# payload 中增加字段
"client_correlation_id": data.client_correlation_id,
```

数据同源性验证: `state` 在 `_consume_runner_event()` 中已存在（agent.py:1194-1196），`_client_correlation_id_from_state(state)` 取的是当前迭代 Runner request identity 的 `client_correlation_id`，与所有其他 EngineEvent 同源。字段默认 `None` 向后兼容，不破坏现有调用方和测试。

**（3）建议 defer 的理由**

- `UsageReportedData` 不单纯是 provider-related debugging 信号。设计文档将其定位为 "post-call observation for estimator calibration, diagnostic, and future governance"（post-call 观测信号），与 `RunFailedData` / `ContextCompactionRequiredData` / `ToolResultAcceptedData` 等状态推进型 event 的语义归属不同。
- 无法同时添加 `provider_request_id`：usage event（`RunnerUsageRecordedData`）在 Runner event 流中的位置不固定。SSE parser 的 usage 可在 stream 中间位置触发（OpenAI `stream_options.include_usage`），此时 `state.provider_request_id` 尚未设置（该字段在 `RunnerDoneData` 时才写入，agent.py:1377）。非流式 parser 中 usage 也在 done 之前 yield（non_stream_parser.py:356-362 在 done 365-370 之前）。因此只加 `client_correlation_id` 不加 `provider_request_id` 会制造字段不对称。
- analyzer（WU-OBS-00 / issue-70）应定义 usage observation 信号需要哪些关联维度，而非由本 WU 的 residual fix gate 单向决定。若 analyzer 认为 usage observation 需要同时携带两个 correlation id，则需要 Engine 层调整 Runner 事件顺序或扩展 `RunnerUsageRecordedData`——这已超出 residual fix 范围。

**（4）结论**

defer-to-WU-OBS-00 的理由成立（非硬性 blocking，但属于合理设计边界）。当前不阻塞 provider debugging correlation 主链路：所有 terminal event、context recovery event、工具相关 event 均已携带 `client_correlation_id`。usage observation 是最后一个未携带的 EngineEvent 类型，其语义归属与其他事件不同。

若用户不接受 defer，可按上述方案在 3 个文件中补最小同源修复，改动量 ~6 行，与其余 residual fix 模式一致。

## 总控文档审核

检查项与结论:

1. **gate 状态**: `gate | review`，`implementation status | residual-risk-review-in-progress` — 与当前实际状态一致（residual risk review gate 进行中）。
2. **residual 表更新**:
   - WU-ENG-02-S1-R1: `closed` → 记录 "PR 114 residual fix 关闭"，与代码变更一致。
   - WU-ENG-02-S1-R2: `closed` → 记录 "PR 114 residual fix 关闭"，与代码变更一致。
   - WU-ENG-02-S2-R2: `closed` → 记录 "PR 114 residual fix 关闭"，与代码变更一致。
   - WU-ENG-02-S3-R1: 保留 `deferred-with-owner` → 与本次裁决一致。
   - WU-ENG-02-S3-R2: `closed` → 记录 "PR 114 residual fix 关闭"，与代码变更一致。
3. **review artifacts 列表**: 已添加 `docs/reviews/wu-eng-02-residual-risk-fix-codex.md`，与 codex fix gate artifact 一致。
4. **draft PR status**: 从 "draft-PR-pass" 更新为 "reopened for residual-risk review"，与用户决策一致。
5. **推进记录**: 已更新为包含 residual risk fix gate 的完整记录（line 235），与 gate 编排一致。

总控文档更新准确，无遗漏或错误。

## Open Questions

无。

## Residual Risk

- F1 测试覆盖缺口（低严重度）: `test_tool_execution_timeout_wins_over_runner_close_cancel` 缺 `client_correlation_id` 断言。建议在后续 maintenance 中补齐，不阻塞当前 gate。
- S3-R1 defer 后续: WU-OBS-00 / issue-70 analyzer 实施时需确认 usage observation signal 是否需要 `client_correlation_id`，并决定是否同步添加 `provider_request_id`。

## 验证命令

```bash
# affected tests
source .venv/bin/activate && pytest tests/engine/test_agent_phase3_tool_call.py tests/engine/contracts/test_runner_spec.py tests/engine/runners/openai/test_request_identity.py tests/host/test_run_attempt_transitions.py -q

# regression smoke
source .venv/bin/activate && pytest tests/engine/contracts/test_runner_identity.py tests/engine/contracts/test_agent_run.py tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q

# type check
source .venv/bin/activate && pyright
```

预期结果: 所有测试通过，pyright 0 errors。
