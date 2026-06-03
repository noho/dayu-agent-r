# WU-ENG-02 Plan Re-Review — AgentDS

## Gate

- gate: plan re-review
- review target: `docs/host/wu-eng-02-provider-request-identity-plan.md` (fixed plan)
- fix artifact: `docs/reviews/wu-eng-02-plan-fix-codex.md`
- original reviews: `docs/reviews/wu-eng-02-plan-review-mimo.md`, `docs/reviews/wu-eng-02-plan-review-ds.md`
- control doc: `docs/host/issues-implementation-control.md`
- reviewer: AgentDS (adversarial re-review; no implementation, no plan modification, no other gate)

## Review Scope

只检查 controller accepted findings 是否在 fixed plan 中已修复。不重新审查整个 plan，不检查未被 controller accepted 的 finding，不实现、不修改 plan、不修改生产代码、不提交、不 push、不进入其它 gate。

## Controller Accepted Findings Status

Controller accepted findings 来源：`docs/host/issues-implementation-control.md` lines 292-299，共 7 条 accepted + 1 条 explicitly rejected（保留原设计）。

### F1: runner_call_index 覆盖 force-answer / continuation / fallback

- origin: DS F1 (MEDIUM) + MiMo F1 (minor)
- controller decision: accepted — 所有 logical Runner call 都必须递增 `runner_call_index`，并补计划测试要求
- fix claim (Codex F1): 已修复

**验证证据：**

1. Plan §Client Correlation ID Source Choice "Multi-call semantics" 段：
   > "every logical Runner call increments `runner_call_index` and gets a distinct `client_correlation_id`. This includes normal Agent iterations, tool-loop re-entries, length continuations, force-answer fallback, and any future fallback path that performs a Runner call."

2. Plan §Slice 1 Exact changes：
   > "Increment `_runner_call_index` immediately before every logical `_run_runner_iteration` / Runner invocation, including normal iterations, tool-loop re-entries, length-continuation calls, force-answer fallback, and fallback paths that call the Runner."

3. Plan §Slice 1 Tests：
   > "Agent tests verify `runner_call_index` increments for force-answer fallback, length continuation, and fallback/continuation paths that perform logical Runner calls."

4. Plan §Tests / Validation Commands And Expected Assertions：
   > "Agent tests cover incrementing `runner_call_index` for normal calls, force-answer fallback, length continuation, and fallback/continuation paths that perform logical Runner calls."

**判定：已修复。** 覆盖了全部三条路径，且测试断言要求明确。

### F2: request_identity: RunnerRequestIdentity | None 可选类型语义

- origin: DS F2 (MEDIUM)
- controller decision: accepted — 普通 Agent path non-None，direct Runner / compactor 可显式 None；完成信号需避免与可选类型冲突
- fix claim (Codex F2): 已修复

**验证证据：**

1. Plan §Slice 1 Error handling：
   > "Ordinary Agent -> Runner paths must pass a non-`None` `RunnerRequestIdentity`. Direct Runner tests, direct Engine call sites, and compactor paths outside an ordinary Agent attempt may explicitly pass `None`."

2. Plan §Slice 1 Completion signal：
   > "Every ordinary Agent -> Runner call path passes a non-`None` `request_identity`; direct Runner / direct Engine / allowed compactor paths pass `request_identity=None` explicitly when no ordinary Agent attempt identity exists."

**判定：已修复。** 完成信号已与可选类型语义对齐，不再声称 "no call path without identity"。

### F3: AsyncRunner.call 签名 keyword-only 增量

- origin: MiMo F2 (minor)
- controller decision: accepted — 只新增 keyword-only `request_identity`，保留 `messages/options/tools` 位置参数
- fix claim (Codex F3): 已修复

**验证证据：**

1. Plan §Public Contract item 4：
   > "Change `AsyncRunner.call(messages, options, tools, *, request_identity: RunnerRequestIdentity | None)` by adding only the keyword-only `request_identity`; keep existing `messages/options/tools` positional parameters unchanged to minimize public-contract churn."

2. Plan §Slice 1 Exact changes：
   > "Change `AsyncRunner.call` protocol to `call(messages, options, tools, *, request_identity=...)`; only `request_identity` is keyword-only, and existing positional `messages/options/tools` stay positional."

**判定：已修复。** 签名变更范围明确，最小化变更策略一致。

### F4: _AsyncAgent correlation 取值收敛

- origin: MiMo F3 (minor)
- controller decision: accepted — 避免重复散落 correlation 取值逻辑，优先模块级 helper 或 iteration state
- fix claim (Codex F4): 已修复

**验证证据：**

Plan §Slice 1 Exact changes：
> "Store current identity in iteration state or derive `client_correlation_id` through a module-level helper. Avoid scattering repeated optional-correlation extraction logic across `_AsyncAgent` emit sites."

**判定：已修复。** 收敛要求已写入 Slice 1 实施指引。

### F5: EngineRunOutcomeFailed 归类修正

- origin: DS F3 (LOW)
- controller decision: accepted — 应归类为 `AgentRunResult` outcome，不是 EngineEvent data class
- fix claim (Codex F5): 已修复

**验证证据：**

1. Plan §Public Contract item 6 列出四个 EngineEvent data class（`ContextCompactionRequestedData`、`ProviderProtocolErrorData`、`IterationCompletedData`、`RunFailedData`），不含 `EngineRunOutcomeFailed`。

2. Plan §Public Contract item 7（独立条目）：
   > "Add `client_correlation_id: str | None` to `EngineRunOutcomeFailed` as an `AgentRunResult` outcome class in `dayu.engine.contracts.agent_run`, not as an EngineEvent data class."

**判定：已修复。** `EngineRunOutcomeFailed` 已从 EngineEvent data class 列表中拆分，明确归类为 `AgentRunResult` outcome class，且所在模块（`agent_run.py`）正确。

### F6: client_correlation_id digest 完整 SHA-256 长度

- origin: DS F4 (LOW)
- controller decision: accepted — 明确为完整 SHA-256 hex，即 `dayu-` + 64 hex
- fix claim (Codex F6): 已修复

**验证证据：**

1. Plan §Client Correlation ID Source Choice：
   > "exactly `dayu-` plus 64 lowercase hex characters"

2. Plan §Slice 1 Exact changes：
   > "Compute `client_correlation_id` as `dayu-` + full 64-character SHA-256 hex digest."

3. Plan §Slice 1 Tests：
   > "Contract test validates digest is ASCII, stable, exactly 69 characters (`dayu-` plus 64 lowercase SHA-256 hex characters)"

**判定：已修复。** 长度从模糊的 "short" 收敛到精确的 64 hex + 5 prefix = 69 chars。

### F7: ClientCorrelationPolicy docstring 语义

- origin: DS F5 (LOW)
- controller decision: accepted — docstring 需说明 enum 是 provider-protocol-specific outbound mapping policy，不是 provider 名称分支
- fix claim (Codex F7): 已修复

**验证证据：**

Plan §Adapter Policy：
> "`ClientCorrelationPolicy` docstring must state that enum values are provider-protocol-specific outbound mapping policies. They are not provider-name branches, and Host / Agent must not dispatch behavior by provider string."

**判定：已修复。** docstring 语义约束已写入 Adapter Policy 段。

### F8: 保留 run_id + iteration_id 的裁决

- origin: DS F6 (LOW) — suggested fix was "None required"; controller explicitly rejected any removal
- controller decision: rejected-with-reason — 冗余不要求修改，保留 `run_id` 作为本地根关联
- fix claim (Codex F8): 已修复（确认保留）

**验证证据：**

Plan §Client Correlation ID Source Choice：
> "Keep both `run_id` and `iteration_id` in the canonical tuple even though the current `iteration_id` format embeds `run_id`. `run_id` remains the local root correlation input and avoids making digest semantics depend on the textual shape of `iteration_id`."

Plan §RunnerRequestIdentity dataclass 定义中 `run_id: str` 和 `iteration_id: str` 均为必填字段，未被移除。

**判定：已修复。** run_id 未被错误改掉，保留裁决在 fixed plan 中明确记录。

## MiMo Info-Level Findings (F4/F5/F6) 状态

MiMo F4（静态 header 冲突检测时机）、F5（Host execution config JSON projection）、F6（EngineEvent 影响 Host ingest）均为 info 级别，MiMo 原始裁决中明确说明无需 plan 修改：
- F4: "无修改要求；实施时在 header 构建 helper 中检测即可"
- F5: "按项目 schema 变更约定...实施测试直接验证新字段的 round-trip"
- F6: "Slice 3 实施时逐一核对"

这三条不在 controller accepted findings 的显式修复列表中，属于 implementation 阶段指引而非 plan 变更。Fixed plan 已保留对应的 Slice 2 / Slice 3 文件列表和处理说明。

**判定：证据失效（不适用）。** 这些 finding 从未要求 plan 变更，不构成 re-review 的检查项。

## New Blocking Issues

对 fixed plan 进行 adversarial 检查，未发现由 fix 引入的新 blocking issue：

- 无内部矛盾：所有 8 条 fix 之间不存在语义冲突。
- 无过度修正：fixed plan 未因 fix 而引入新的模糊性、矛盾约束或过度设计。
- 无范围漂移：fix 未扩大 WU scope、未新增 work unit、未修改 Non-Goals。
- 无架构违规：fix 未引入跨层依赖、反向依赖或 provider 字符串分支。

**无新增 blocking issue。**

## Residual Risks

| 类别 | 描述 | 分类 | Owner |
|---|---|---|---|
| implementation 精准度 | force-answer / continuation / fallback 的具体 `_runner_call_index` 递增位置仍需 implementation agent 结合 `dayu/engine/agent.py` 实际路径确认 | deferred-with-owner | Slice 1 implementation |
| request_identity=None 路径收敛 | 所有非 ordinary Agent path（direct Runner / direct Engine / compactor）需在 implementation 时收敛为显式 `None`，避免遗漏 | deferred-with-owner | Slice 1/3 implementation |
| static header conflict | `RunnerSpec.headers` 中 `x-client-request-id` 冲突检测在 `_do_attempt` 中实现，plan 已明确；implementation 需确保检测在 HTTP post 前执行 | deferred-with-owner | Slice 2 implementation |
| EngineEvent dataclass 构造点 | `client_correlation_id` 添加到 4 个 EngineEvent data class + 1 个 AgentRunResult outcome，所有构造点需更新；frozen dataclass 编译期安全但需全面覆盖 | deferred-with-owner | Slice 1/3 implementation |
| execution config JSON round-trip | `client_correlation_policy` 需进入 `runner_spec_json()` / `runner_spec_from_json()` | deferred-with-owner | Slice 2 implementation |
| Tool Trace analyzer | analyzer 消费 `client_correlation_id` 属于 issue-70 | later work unit | WU-OBS-00 |
| Anthropic native / Claude Code gateway | 需各自 adapter 实现，当前仓库无 native Anthropic runner | later work unit | future WU |

## Conclusion

**pass** — 8 条 controller accepted findings 全部已修复，0 条未修复，0 条部分修复，无新增 blocking issue。

- artifact path: `docs/reviews/wu-eng-02-plan-rereview-ds.md`
- 结论: pass
- 已修复: 8 (F1-F8)
- 部分修复: 0
- 未修复: 0
- 证据失效: 0（MiMo F4/F5/F6 不适用，从未要求 plan 变更）
- blocking open questions: 无
- 是否只修改 re-review artifact: 是
