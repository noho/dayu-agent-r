# WU-ENG-02 Plan Fix — AgentCodex

## Gate

- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- gate: plan fix
- plan artifact: `docs/host/wu-eng-02-provider-request-identity-plan.md`
- review artifacts:
  - `docs/reviews/wu-eng-02-plan-review-mimo.md`
  - `docs/reviews/wu-eng-02-plan-review-ds.md`
- fix artifact: `docs/reviews/wu-eng-02-plan-fix-codex.md`

## Accepted Findings Fix Status

| ID | accepted finding | status | evidence |
|---|---|---|---|
| F1 | force-answer / continuation / fallback 等所有 logical Runner call 都必须递增 `runner_call_index`，并补计划测试要求 | 已修复 | Plan §Client Correlation ID Source Choice 明确每个 logical Runner call 递增，包含 normal iterations、tool-loop re-entries、length continuations、force-answer fallback、future fallback；Slice 1 exact changes / tests / validation assertions 均补充测试要求。 |
| F2 | `request_identity: RunnerRequestIdentity &#124; None` 语义需澄清：普通 Agent path non-None，direct Runner / compactor 等可显式 None；完成信号需避免和可选类型冲突 | 已修复 | Plan §Slice 1 Error handling 与 Completion signal 明确 ordinary Agent -> Runner 必须 non-None，direct Runner / direct Engine / allowed compactor paths 可显式 `None`。 |
| F3 | `AsyncRunner.call` 只新增 keyword-only `request_identity`，保留 `messages/options/tools` 位置参数 | 已修复 | Plan §Public Contract 与 §Slice 1 Exact changes 明确签名为 `call(messages, options, tools, *, request_identity=...)`，仅新增 keyword-only 参数。 |
| F4 | 避免 `_AsyncAgent` 重复散落 correlation 取值逻辑，优先模块级 helper 或 iteration state | 已修复 | Plan §Slice 1 Exact changes 要求把 current identity 存在 iteration state，或通过 module-level helper 派生 `client_correlation_id`，避免多个 emit 点重复 optional extraction。 |
| F5 | `EngineRunOutcomeFailed` 应归类为 `AgentRunResult` outcome，不是 EngineEvent data class | 已修复 | Plan §Public Contract 将 `EngineRunOutcomeFailed` 拆为独立 item，明确它是 `dayu.engine.contracts.agent_run` 中的 `AgentRunResult` outcome class。 |
| F6 | `client_correlation_id` digest 长度需明确为完整 SHA-256 hex，即 `dayu-` 加 64 hex | 已修复 | Plan §Client Correlation ID Source Choice 与 §Slice 1 Exact changes / tests 明确 exactly `dayu-` plus 64 lowercase SHA-256 hex characters，总长度 69。 |
| F7 | `ClientCorrelationPolicy` docstring 需说明 enum 是 provider-protocol-specific outbound mapping policy，不是 provider 名称分支 | 已修复 | Plan §Adapter Policy 要求 docstring 说明 enum values 是 provider-protocol-specific outbound mapping policies，不是 provider-name branches，Host / Agent 不得按 provider string 分支。 |
| F8 | 不要修改 `iteration_id + run_id` 冗余输入；保留 `run_id` 作为本地根关联 | 已修复 | Plan §Client Correlation ID Source Choice 明确保留 `run_id` 和 `iteration_id` 同时进入 canonical tuple，并说明 `run_id` 是 local root correlation input。 |

## Modified Plan Sections Summary

- §Public Contract: 收紧 `AsyncRunner.call` 签名变更范围；拆分 `EngineRunOutcomeFailed` 归类。
- §Adapter Policy: 补充 `ClientCorrelationPolicy` docstring 语义约束。
- §Client Correlation ID Source Choice: 明确保留 `run_id + iteration_id`、完整 SHA-256 digest 长度、所有 logical Runner call 的 index 递增语义。
- §Slice 1: 补充 call index 递增位置、ordinary Agent non-None identity、direct / compactor explicit None、helper / iteration state 收敛要求、force-answer / continuation / fallback 测试要求。
- §Tests / Validation Commands And Expected Assertions: 补充 `runner_call_index` 针对 force-answer、length continuation、fallback / continuation 的断言要求。
- §Completion Report Format: 对齐当前 plan / plan-fix gate 的 completion report 限定字段。

## Residual Risks

- 本 gate 只修复 plan artifact，不执行实现；实际代码仍需在 implementation gate 中按计划落地。
- force-answer / length continuation / fallback 的具体测试落点仍需 implementation agent 结合 `dayu/engine/agent.py` 当前路径确认，但 plan 已明确必须覆盖这些 logical Runner call。
- `request_identity=None` 的合法路径需要 implementation 时逐一收敛到 direct Runner / direct Engine / allowed compactor path，避免普通 Agent path 漏传。
- 无 blocking open questions。

## Validation

本 gate 不运行测试、pyright 或 README 同步，因为用户明确要求只修复 plan review accepted findings，且禁止实现生产代码、修改测试、修改 README 或进入后续 gate。

Artifact 自检已完成：

- 只修改允许文件：`docs/host/wu-eng-02-provider-request-identity-plan.md` 与 `docs/reviews/wu-eng-02-plan-fix-codex.md`。
- 8 条 controller accepted findings 均在 plan 中有对应修复点。
- 未修改生产代码、测试、README、control_doc。
- 未进入 re-review、implementation、commit、push 或 PR gate。

## Completion Status

completed
