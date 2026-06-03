# WU-ENG-02 Plan Review — AgentMiMo

## Review Target

- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- gate: plan review
- artifact: `docs/host/wu-eng-02-provider-request-identity-plan.md`
- reviewer: AgentMiMo
- review date: 2026-06-03

## Gate Decision

**pass-with-findings**

Plan 整体动机成立、严重性评估正确、直接证据充分、架构边界合理、client correlation id 来源选择经过充分论证、无过度设计。存在若干可改进 finding，均不阻塞 implementation gate。

## Findings

### F1 [minor] runner_call_index 与 iteration_index 起始值不一致

- severity: minor
- location: plan §Client Correlation ID Source Choice
- evidence: `dayu/engine/agent.py:629` — `iteration_index` 从 0 开始；plan 定义 `runner_call_index >= 1`
- impact: 内部一致性无问题（两个 index 语义不同），但 `build_runner_request_identity` 的 docstring / 测试需要明确说明二者约定，否则实施者可能混淆
- suggestion: 在 Slice 1 的 contract test 中显式断言 `iteration_index=0` 与 `runner_call_index=1` 组合的 digest 正确性
- decision: accepted

### F2 [minor] AsyncRunner.call 签名变更范围需明确 `RunnerCallOptions` 兼容性

- severity: minor
- location: plan §Contract / Schema — Public Contract item 4
- evidence: `dayu/engine/contracts/runner.py:24` — 当前签名 `call(messages, options, tools)` 三个位置参数
- impact: plan 要求改为 keyword-only `request_identity: RunnerRequestIdentity | None`，但未说明 `messages`、`options`、`tools` 是否同时改为 keyword-only 或保持位置参数。当前所有调用方（`agent.py:1065`）使用位置参数
- suggestion: 明确 `messages`、`options`、`tools` 保持位置参数不变，仅新增 keyword-only `request_identity`；或全部改为 keyword-only。建议前者以最小化变更
- decision: accepted

### F3 [minor] `_AsyncAgent` 复杂度增量

- severity: minor
- location: plan §Slice 1 — Exact changes
- evidence: `dayu/engine/agent.py` 当前 2585 行，`_AsyncAgent` 已承载 iteration 状态机、tool batch、continuation、fallback 等逻辑
- impact: 新增 `_runner_call_index` 计数器、identity 构建、identity 存储到 iteration state 或 local variable、在 EngineEvent 发射时携带 `client_correlation_id` — 这些增量是合理的，但会使 `_run_runner_iteration` 和 `_consume_runner_event` 的参数 / 状态更多
- suggestion: 实施时考虑将 request identity 构建逻辑收敛到 `_IterationState` 或独立 helper，避免在多个 emit 点重复写 `client_correlation_id` 取值逻辑
- decision: accepted

### F4 [info] 静态 header 冲突检测时机

- severity: info
- location: plan §Provider Adapter Policy Design — OpenAI-Compatible item 5
- evidence: `dayu/engine/runners/openai/runner.py:510-512` — 当前 header 构造在 `_do_attempt` 中
- impact: plan 要求在 policy enabled 且 `RunnerSpec.headers` 已含 `x-client-request-id` 时 fail fast。这是配置错误，理论上可在 `RunnerSpec.__post_init__` 中更早检测，但 `RunnerSpec` 不知道 policy 是否 enabled（policy 是 RunnerSpec 的一部分），所以在 `_do_attempt` 中检测是合理的
- suggestion: 无修改要求；实施时在 header 构建 helper 中检测即可
- decision: accepted

### F5 [info] Host execution config JSON projection 需同步更新

- severity: info
- location: plan §Slice 2 — Allowed files
- evidence: plan 列出 `dayu/host/_execution_config_projection.py` 作为受影响文件
- impact: `RunnerSpec` 新增 `client_correlation_policy` 字段后，Host effective execution config 的 JSON freeze / restore 路径必须同步序列化 / 反序列化该字段。plan 已识别此文件，但未详细说明 JSON schema 兼容性处理
- suggestion: 按项目 schema 变更约定（全新 schema 起库），实施测试直接验证新字段的 round-trip，不做旧 config 兼容读取
- decision: accepted

### F6 [info] EngineEvent data class 变更影响 Host ingest 映射

- severity: info
- location: plan §Contract / Schema — Public Contract item 6
- evidence: `dayu/host/engine_ingest.py` 已有大量 `provider_request_id` 映射点（grep 出 20+ 处）
- impact: plan 要求在 `ContextCompactionRequestedData`、`ProviderProtocolErrorData`、`IterationCompletedData`、`RunFailedData`、`EngineRunOutcomeFailed` 五个 data class 新增 `client_correlation_id: str | None`。Host ingest 必须在所有消费这些 data class 的映射点同步提取新字段
- suggestion: Slice 3 实施时逐一核对 `engine_ingest.py` 中消费这五个 data class 的映射点，确保不遗漏
- decision: accepted

## Blocking Open Questions

**无。** plan 已明确 client correlation id 来源选择、retry 语义、multi-iteration 语义、adapter policy 设计和 durable schema 策略。所有设计决策有直接代码证据支撑。

## Residual Risks

| 类别 | 描述 | owner | 状态 |
|---|---|---|---|
| collision / header legality | `dayu-` prefix + fixed-length hex SHA-256 digest 保证 ASCII、长度受限、collision 概率极低 | Slice 1/2 tests | current slice fixed |
| multi-iteration ambiguity | 每个 iteration / logical Runner call 有独立 `client_correlation_id` | Slice 1 tests | current slice fixed |
| transport retry ambiguity | 同一 logical Runner call 的 HTTP retry 复用同一 identity | Slice 2 tests | current slice fixed |
| static header conflict | policy enabled 时拒绝 `RunnerSpec.headers` 中的 `x-client-request-id` | Slice 2 tests | current slice fixed |
| README sync | Engine / Host README 需在实现后同步 | Slice 4 | deferred to Slice 4 |
| analyzer consumption | Tool Trace analyzer 显示 provider debugging correlation 属于 issue-70 | WU-OBS-00 | later work unit |
| Anthropic native / Claude Code gateway | 需要各自 adapter 实现，当前仓库无 native Anthropic runner | future WU | later work unit |

## Validation / Docs Gaps

- plan 测试命令列表完整，覆盖 Engine contracts、Agent、OpenAI runner、Host execution config、RunInputBuilder、Engine ingest、Tool Trace projection / queries
- pyright 验证已列出
- Slice 4 明确 README sync 范围：`dayu/engine/README.md`、`dayu/host/README.md`、`tests/README.md`
- 无 root `README.md` 变更需求（CLI / config / user workflow 不变）
- plan 未列出 `tests/engine/test_agent_phase2.py` 和 `tests/engine/test_agent_phase3_tool_call.py` 的具体断言变化，但这些在 Slice 1 completion signal 中覆盖

## Conclusion

Plan 通过 plan review gate。动机成立、严重性评估正确、直接代码证据充分、架构边界合理、client correlation id 来源选择论证完整、无过度设计、无 blocking open questions。6 条 findings 均为 minor / info 级别，不阻塞 implementation gate。

- artifact path: `docs/reviews/wu-eng-02-plan-review-mimo.md`
- 结论: pass-with-findings
- finding 数量: 6 (0 blocking, 4 minor, 2 info)
- blocking open questions: 无
- 是否只修改 review artifact: 是
