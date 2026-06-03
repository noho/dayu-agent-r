# WU-ENG-02 Plan Re-Review — AgentMiMo

## Gate

- work unit: WU-ENG-02 Provider Request Identity And Vendor Debugging Correlation
- gate: plan re-review
- review target: `docs/host/wu-eng-02-provider-request-identity-plan.md`
- fix artifact: `docs/reviews/wu-eng-02-plan-fix-codex.md`
- reviewer: AgentMiMo
- review date: 2026-06-03

## Finding Status

| ID | accepted finding | 最终状态 | evidence |
|---|---|---|---|
| F1 | runner_call_index 覆盖 force-answer / continuation / fallback | 已修复 | Plan §Slice 1 Exact changes 明确 "Increment `_runner_call_index` immediately before every logical `_run_runner_iteration` / Runner invocation, including normal iterations, tool-loop re-entries, length-continuation calls, force-answer fallback, and fallback paths that call the Runner." §Tests 补充 "Agent tests verify `runner_call_index` increments for force-answer fallback, length continuation, and fallback/continuation paths that perform logical Runner calls." |
| F2 | request_identity 可选类型语义 | 已修复 | Plan §Slice 1 Error handling 明确 "Ordinary Agent -> Runner paths must pass a non-`None` `RunnerRequestIdentity`. Direct Runner tests, direct Engine call sites, and compactor paths outside an ordinary Agent attempt may explicitly pass `None`." Completion signal 改写为 "Every ordinary Agent -> Runner call path passes a non-`None` `request_identity`; direct Runner / direct Engine / allowed compactor paths pass `request_identity=None` explicitly when no ordinary Agent attempt identity exists." |
| F3 | AsyncRunner.call keyword-only 增量 | 已修复 | Plan §Public Contract item 4 明确 "`call(messages, options, tools, *, request_identity: RunnerRequestIdentity | None)` by adding only the keyword-only `request_identity`; keep existing `messages/options/tools` positional parameters unchanged to minimize public-contract churn." §Slice 1 Exact changes 重复确认 "only `request_identity` is keyword-only, and existing positional `messages/options/tools` stay positional." |
| F4 | _AsyncAgent correlation 取值收敛 | 已修复 | Plan §Slice 1 Exact changes 要求 "Store current identity in iteration state or derive `client_correlation_id` through a module-level helper. Avoid scattering repeated optional-correlation extraction logic across `_AsyncAgent` emit sites." |
| F5 | EngineRunOutcomeFailed 归类 | 已修复 | Plan §Public Contract item 7 明确 "Add `client_correlation_id: str | None` to `EngineRunOutcomeFailed` as an `AgentRunResult` outcome class in `dayu.engine.contracts.agent_run`, not as an EngineEvent data class." |
| F6 | 完整 SHA-256 长度 | 已修复 | Plan §Client Correlation ID Source Choice 明确 "exactly `dayu-` plus 64 lowercase hex characters"。§Slice 1 Exact changes 重复确认 "Compute `client_correlation_id` as `dayu-` + full 64-character SHA-256 hex digest." §Tests 要求 "exactly 69 characters (`dayu-` plus 64 lowercase SHA-256 hex characters)" |
| F7 | ClientCorrelationPolicy docstring 语义 | 已修复 | Plan §Adapter Policy 明确 "`ClientCorrelationPolicy` docstring must state that enum values are provider-protocol-specific outbound mapping policies. They are not provider-name branches, and Host / Agent must not dispatch behavior by provider string." |
| F8 | 保留 run_id + iteration_id 裁决 | 未被错误改掉 | Plan §Client Correlation ID Source Choice 明确 "Keep both `run_id` and `iteration_id` in the canonical tuple even though the current `iteration_id` format embeds `run_id`. `run_id` remains the local root correlation input and avoids making digest semantics depend on the textual shape of `iteration_id`." 裁决保持不变。 |

## New Blocking Issues

**无。** 只检查由 fix 引入的新问题，未发现 fix 引入了新的 blocking issue。Plan 修改均是澄清和收紧，未引入矛盾或回退。

## Residual Risks

| 类别 | 描述 | owner |
|---|---|---|
| implementation gap | force-answer / length continuation / fallback 的具体测试落点需 implementation agent 结合 `agent.py` 当前路径确认 | implementation gate |
| implementation gap | `request_identity=None` 的合法路径需 implementation 时逐一收敛到 direct Runner / direct Engine / allowed compactor path | implementation gate |
| implementation gap | `_AsyncAgent` 收敛策略（iteration state vs module-level helper）的具体选择留到实施时裁决 | implementation gate |

以上 residual risks 均为 implementation gate 内的实施细节，不阻塞 plan gate 通过。

## Conclusion

- artifact path: `docs/reviews/wu-eng-02-plan-rereview-mimo.md`
- 结论: **pass**
- 未修复数量: 0
- 部分修复数量: 0
- blocking open questions: 无
- 是否只修改 re-review artifact: 是

8 条 controller accepted findings 全部已修复或确认未被错误改掉。fix artifact 未引入新 blocking issue。Plan 可进入 implementation gate。
