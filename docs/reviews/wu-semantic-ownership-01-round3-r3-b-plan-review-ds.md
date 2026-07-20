# R3-B Engine Provider Protocol Plan Review — AgentDS

## Scope

- **Review target**: `docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`
- **Review agent**: AgentDS, adversarial plan review gate
- **Design/control context**: `docs/engine/design.md`, `docs/host/design.md`, `docs/host/issues-implementation-control.md`, `docs/phaseflow-umbrella-optimization-control.md`, controller adjudication artifact
- **Review focus**: 8 dimensions per user instruction (source finding adjudication, owner boundaries, slice granularity, S1 commit boundary coverage, S2 parser/aggregator coverage, S3 JSON Schema scope, validation matrix, README/design triggers)
- **Date**: 2026-07-12

## Assumptions Tested

| # | Assumption | Evidence check | Result |
|---|-----------|----------------|--------|
| A1 | DR-013 late cancellation race exists | `agent.py:1300-1308` — `_is_cancelled()` check inside for loop, fires after consuming any RunnerEvent including RunnerDone; guard at 891-895 with `not state.done_seen` never reached if inner check fires first | **Confirmed** |
| A2 | DR-014 ToolCallAggregator merges calls | `tool_call_aggregator.py:52-60` accepts negative ints; `220-222` concatenates name + arguments on occupied target; `273-277` same-id/different-index remap triggers merge | **Confirmed** |
| A3 | DR-031 EngineEvent/Message lacks runtime validation | `engine_events.py:553-572` no `__post_init__`; `messages.py:46-118` Literal only, no runtime role check; test at `test_engine_event_contract.py:39-59` copies mapping independently | **Confirmed** |
| A4 | DR-034 OLD dict arguments exist | `non_stream_parser.py:557-560` `isinstance(arguments, Mapping)` → `json.dumps(dict(arguments))` with comment "OLD 行为" | **Confirmed** |
| A5 | DR-035 Python equality used for JSON enum | `tool_call_projection.py:649` `value not in enum_value` — Python `__eq__` where `True == 1`; `450-462,566-578` check `isinstance(x, bool) or not isinstance(x, int)` for bounds but don't enforce `>= 0` | **Confirmed** |
| A6 | finish_reason unconditionally forced to TOOL_CALLS | `non_stream_parser.py:362-363` `if tool_calls_emitted: done_finish_reason = FinishReason.TOOL_CALLS`; `sse_parser.py:683` `finish = FinishReason.TOOL_CALLS` | **Confirmed** |
| A7 | failure_candidate overwritten by runner exception | `agent.py:1349-1355` unconditional `state.failure_candidate = RunFailedData(...)` overwrites prior protocol/HTTP candidate | **Confirmed** |
| A8 | finish_reason defaulted to STOP in agent | `agent.py:1756` `finish_reason = state.finish_reason or FinishReason.STOP` — typed fallback hiding parser omission | **Confirmed** |
| A9 | Runner identity encoding is length-framed, not delimiter-only | `runner_identity.py:240-273` uses type prefix + string length framing (`s:<len>:<value>`), so embedded `|`/`:` are unambiguous | **Confirmed — rejection valid** |
| A10 | Error classifier is structured-code-first | `error_classifier.py:95-145` checks `error.code=context_length_exceeded` before marker fallback; non-overflow structured code short-circuits | **Confirmed — rejection valid** |
| A11 | Host EngineEvent construction passes planned validation | `dispatch.py:4208-4221` constructs `RUN_CANCELLED + RunCancelledData` — correct pairing; `agent.py:2649` uses `_make_event()` with explicit type+data | **Confirmed — no breakage** |
| A12 | Existing RunnerEvent uses the pairing pattern plan models EngineEvent after | `runner_events.py:314-394` has `RUNNER_EVENT_TYPE_TO_DATA`, `runner_event_type_for_data()`, `validate_runner_event_pairing()`, `RunnerEvent.__post_init__()` | **Confirmed — consistent pattern** |

## Findings

### Finding-1 [未修复-低] S2 position-based routing 作为隐式 identity conflict 触发路径未显式列入 identity conflict rules

- **位置**: S2 implementation decisions #2-3 (native index / synthetic key / identity conflict rules)
- **问题类型**: 契约缺失
- **当前写法**: S2 identity conflict rules 仅列举 index 与 id 两个身份轴的四类冲突（synthetic→occupied、same id→two indices、same index→two ids、remap 导致合并）。position fallback routing（`_resolve_index` 中 `position → index_by_position` 映射）作为第三种路由机制未被显式提及。
- **反例/失败场景**: 若 provider delta A 携带 `{index: 0, id: "a"}`，同一 response 内 provider delta B 通过 position routing 路由到 index 0 但携带不同 id，则 `feed()` 在 `271-277` 检测到 `existing_index != index` 触发 `_remap_partial_index`，可能进入 identity conflict。当前 identity conflict rules 对此路径的归属（归属 "同一 native index 已绑定 id A 后续声明 id B" 还是 "任一 remap" 规则）未显式说明。
- **为什么有问题**: implementation agent 可能在实现 conflict detection 时仅检查 native index 与 id 主路径，遗漏 position routing 间接触发的冲突，导致 merge bug 以另一种形态残留。
- **直接证据**: `tool_call_aggregator.py:197-200` position routing；`233-277` feed() 中 id-based remap 触发；plan S2 #3 未提及 position 作为 conflict 触发路径。
- **影响**: 实施 Agent 可能遗漏 position routing 路径的 conflict detection，残留隐式 merge。
- **建议改法和验证点**: 在 S2 identity conflict rules 中显式声明 position routing 产出的 index 解析结果同样受全部 conflict rules 约束，或新增一条 "任一 routing mechanism (index/id/position) 导致的 remap 均受同一 conflict rules 判定"。S2 negative matrix 中增加一条 position-routed conflict 反例。
- **修复风险（低）**: 仅澄清规格，不改变实现方向。
- **严重程度（低）**: 当前 rules 中 "任一 remap 会让两个已有 partial 合并" 已可覆盖，仅缺少显式位置声明；implementation agent 若严格按已列四类实现可自然覆盖。

### Finding-2 [未修复-低] S1 _run_runner_iteration 中 `_is_cancelled()` 移除后，runner 异常 + 取消并发路径的终态顺序需显式说明

- **位置**: S1 implementation decisions #5, #7
- **问题类型**: 状态机漏洞
- **当前写法**: S1 #5 写 "`_run_runner_iteration()` 消费并产出 RunnerDone 对应事件后，先按 runner_done is not None 结束 runner-event loop，再检查取消"。S1 #7 写 "tool-call done 的 commit 含义是先接受并投影 batch-ready / requested tool facts；迟到取消可以在这些事实之后阻止尚未完成的 ToolExecutor handshake或下一 iteration"。
- **反例/失败场景**: runner generator 抛出异常（非 CancelledError）时，`agent.py:1318-1355` 的 except 块执行。若此时 `_is_cancelled()` 为 true，当前代码（移除 1306-1308 后）在 except 块内直接写 `failure_candidate` 并 return，不检查取消。外层调用方可能看到 `run_failed` 而非 `run_cancelled`。此行为是否 intentional（first failure candidate 优先）需在 plan 中显式声明，否则 reviewer 无法判断是 bug 还是设计选择。
- **为什么有问题**: design doc §13 承诺 "Runner 未完成时取消可以抢占本轮"，但 runner 异常是 runner 已完成（以异常形式），且 failure_candidate 已在 except 块写入。first-candidate 规则（S1 #8）说 "只有 failure_candidate is None 时写入"，但 except 块的 `1349` 是直接赋值而非通过 first-candidate helper。plan 未说明 except 块是否会修改为使用 first-candidate helper，也未说明取消 + exception 并发时的预期终态。
- **直接证据**: `agent.py:1318-1355` except 块直接 `state.failure_candidate = ...` 不使用 helper；plan S1 #8 的 first-candidate helper 规则；engine design §13 "Runner 未完成时取消可以抢占本轮"。
- **影响**: implementation agent 可能在 except 块保留直接赋值，绕过 first-candidate helper，导致此路径与其他 failure 路径行为不一致。
- **建议改法和验证点**: S1 implementation decisions 增加一条：除 finally/close 外，所有 failure_candidate 赋值必须通过 first-candidate helper，包括 except 块。若取消 + exception 并发时终态为 runner_exception（non-recoverable），在 plan 中显式声明原因（runner 异常先于取消观察，或取消不能将已发生的 runner 异常改写为取消）。
- **修复风险（低）**: 仅需在 except 块增加 helper 调用并显式声明并发语义。
- **严重程度（低）**: 当前代码路径本身低频；first-candidate helper 的语义已明确，implementation agent 大概率会自然统一。

### Finding-3 [未修复-低] S1 `_classify_iteration` 行 1756 的 `or FinishReason.STOP` fallback 移除时机与 S2 finish_reason fail-closed 的耦合

- **位置**: S1 与 S2 的依赖边界
- **问题类型**: 切片过粗/依赖风险
- **当前写法**: S1 要求 `finish_reason` 从 provider choice policy 到 RunnerDoneData 保持 typed fact，不得由 Agent 默认。S2 要求 parser 对所有成功 terminal 要求显式 finish_reason。S1 的 prerequisite 写 "S2 依赖本 slice 的 Agent 不再修复或默认 provider finish semantics"。
- **反例/失败场景**: S1 先实施，移除 `agent.py:1756` 的 `or FinishReason.STOP` fallback。但 S2 尚未实施，parser 的 non-stream content 路径仍可能产出 missing finish_reason（当前 `validate_non_stream_content_terminal_finish` 已 fail-closed on missing，但 SSE parser 的 `self._finish_reason is None` 路径在 685 行有单独的 MISSING_TERMINAL_FINISH_REASON 错误）。若 S1 移除 fallback 后、S2 完成前，存在某 parser 路径仍产出 finish_reason=None 的 RunnerDoneData，则 Agent 的 `_classify_iteration` 会在 `1756` 取到 `None`（而非 `FinishReason.STOP`），随后 `1757` 的 `FinishReason.ERROR` 检查不匹配，可能进入 `1826` 的 tool_call_signal_seen 分支或 fallthrough。S1 应先确认所有 parser 路径在 S1 完成时已产出显式 finish_reason，或 S1 保留一个过渡期 typed assertion（`assert finish_reason is not None`）而非静默 fallback。
- **为什么有问题**: `or FinishReason.STOP` 是 parser bug 的最后掩盖层。若 S1 移除它而 S2 尚未完成，中间状态的错误行为不可预测（可能 fallthrough 到 `tool_calls_missing` 等无关错误）。虽然两个 slice 在同一次 implementation session 中连续执行，但 aggregate validation 前存在中间状态。
- **直接证据**: `agent.py:1756` 的 fallback；plan S1 dependency "S2 依赖本 slice"（单向）；sse_parser.py:685-689 的 MISSING_TERMINAL_FINISH_REASON 路径仅覆盖 content-only 场景。
- **影响**: S1→S2 过渡期可能产生误导性 Agent 错误码。
- **建议改法和验证点**: S1 移除 `or FinishReason.STOP` 时替换为 `assert finish_reason is not None, "parser must provide explicit finish_reason"` 或在 `_classify_iteration` 中为 `None` finish_reason 显式返回 `RunFailedData(error_code="agent_missing_finish_reason")`。此 assert 在 S2 完成后始终满足，不会残留为兼容分支。
- **修复风险（低）**: 单行修改。
- **严重程度（低）**: 同一 session 内连续实施，中间态面积极小；且当前 SSE/non-stream parser 在 S1 前的主要路径已各自处理 missing finish_reason（content-only fail-closed，tool-call 强制 TOOL_CALLS）。

## Open Questions

无。所有风险可直接在 plan 中通过 S1/S2 implementation decisions 的边界澄清解决，无需用户决策。

## Residual Risks

| Risk | Classification | Why not a blocker | Suggested tracking |
|------|---------------|-------------------|-------------------|
| S2 OLD dict arguments 删除后，非规范 OpenAI-compatible 第三方 provider 可能失败 | Planned fail-closed; not a residual | Plan S2 stop condition: 若真实 provider 被证明只能返回 dict arguments，停止并要求独立 typed adapter。Fail-closed 是正确行为，不应作为 residual 阻碍 plan。 | 记录在 aggregate deepreview artifact 中 |
| S3 ToolParametersSchema bounds 校验可能暴露现有工具 schema 的非法声明 | Planned stop condition | Plan S3 stop condition: 若现有 schema 非法，停止并返回 plan review。这是正确的 fail-safe。 | 记录在 aggregate deepreview artifact 中 |
| S1 取消检查移除后，若某 Runner 实现不观察 cancellation token，Agent 无法在 runner-event loop 中抢占取消 | Accepted design tradeoff | Runner contract 要求观察 token（engine design §7）；不观察的 Runner 是 Runner bug，不应由 Agent 补偿。 | 在 Agent/Runner contract test 中保留/补充 Runner 必须观察取消的约束 |
| S2 negative matrix 仅覆盖两路 transport 的事件类别对齐，未显式要求相同 provider response 的 stream/non-stream parity test | Covered by existing `test_stream_non_stream_terminal_parity.py` | Plan S2 allowed tests 中已包含该文件。 | 无需额外跟踪 |

## Architecture Boundary Review

- ✅ Engine → Host 方向：Engine 产出合法 EngineEvent，Host ingest 只消费不修复。Plan 维持此边界。
- ✅ Engine 内部：parser/aggregator(provider wire) → Agent(RunnerEvent) → EngineEvent stream。Plan 在每个 owner 处关闭缺口。
- ✅ dayu.contracts → dayu.runtime：runtime 只依赖 contracts + stdlib。Plan S3 遵循此依赖方向。
- ✅ 无新增反向依赖、跨层穿透或共享可变状态。
- ✅ EngineEvent validation 复用 RunnerEvent 既有 pattern（mapping + helper + `__post_init__`），不引入新抽象层。

## Best-Practice Review

- ✅ Fail-closed 优先：所有 identity conflict、finish_reason mismatch、非法 enum/bounds 均 fail-closed，不静默降级。
- ✅ 单一真源：typed `runner_done` 替代三字段组合；`_choice_policy` 成为 stream/non-stream terminal shape 共用 owner。
- ✅ 构造期校验：`ToolParametersSchema` 在 construction 时拒绝非法 bounds，不在 runtime 把 schema bug 伪装为用户参数错误。
- ✅ 无兼容分支：删除 OLD dict arguments、不保留 feature flag、不保留旧测试兼容分支。

## Overengineering Review

- ✅ 不新增 provider registry、通用 JSON Schema engine、第三方 schema 依赖、Host repair layer 或迁移层。
- ✅ 三 slices 按真实 owner 与验证故障面切分：S1=Engine contract/Agent state, S2=OpenAI adapter, S3=schema/runtime。既没有按 finding/file 机械拆分（6+ slices），也没有无差别合并（1 个 monolith slice）。
- ✅ S3 只修四个 count bounds + enum equality，不扩展为完整 JSON Schema draft evaluator。

## Overcoupling Review

- ✅ S1→S2 依赖是单向的（Agent 不再默认 finish_reason 后，parser fail-closed 才有完整效果），不是双向耦合。
- ✅ S3 独立于 S1/S2，仅依赖 S1/S2 完成后再统一同步 doc/test truth。
- ✅ EngineEvent validation 改变后，Host 的 `_cancelled_eof_candidate` 已验证可兼容（`RUN_CANCELLED + RunCancelledData` 配对正确），不需要 Host 修改。
- ✅ 不存在 "为三个 slice 都要改同一个模块的同一段逻辑" 的冲突窗口。

## Final Plan Review Conclusion

**Pass** — 未发现实质性问题。

### Summary

Plan 的 10 项 source finding 裁决（7 accepted / 1 narrowed / 2 rejected）全部有直接代码证据支撑。被 rejected 的 runner identity 与 error classifier 两项，代码证据确认其现有 owner 行为正确，plan 正确拒绝将其纳入 implementation。被 narrowed 的 finish_reason missing policy 一项，缩窄到 parser 必须对所有成功 terminal 要求显式 finish_reason，范围合理。

Owner boundaries 正确：Engine 拥有 provider normalization，Host 不下游补救。EngineEvent/Message 构造不变量在正确的 owner（contracts module）处添加，不扩散到 Host 或测试夹具。

3 slices 是最小 owner-closed 切分：S1（Engine contracts + Agent state）、S2（OpenAI adapter normalization）、S3（contracts/runtime schema validation）。符合 umbrella optimization 对 High Risk production work 的 slices ≤3 约束，且每个 slice 有独立 semantic owner、validation matrix 与 failure blast radius。

S1 RunnerDone commit boundary 覆盖 ordinary final、force-answer final、error done、tool-call done、done 前取消和 runner 异常路径。3 个 low-severity findings 分别涉及 position routing 的显式声明、except 块的 first-candidate helper 统一、S1→S2 过渡期的 finish_reason fallback 替换策略——三者在 implementation 中自然收敛，不构成 blocker。

S2 OpenAI parser/aggregator 正确覆盖 native/synthetic identity conflict、OLD dict arguments removal、finish_reason mismatch，且显式保护合法 streaming continuation（相同 id + 相同 index 分片继续合法）。

S3 JSON Schema 严格限定在四个 count bounds 的 construction-time 校验 + enum 的 JSON equality 语义，不偷塞完整 JSON Schema engine。

Validation matrix 足够且可执行：每个 slice 有明确的 focused tests、pyright、git diff --check 和 rg-based source scans。Scans 使用具体模式（字段名、旧行为特征），不会被简单重命名绕过。

README/design trigger decisions 符合 AGENTS.md：`docs/engine/design.md`、`dayu/engine/README.md`、`tests/README.md` 需更新；Host/docs 不变（Host 层级未修改）；根 README 不变（无用户可见变化）。

### Completion Report

- **status**: pass
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-ds.md`
- **number of findings**: 3（均 severity=低，非阻塞）
- **blocking questions**: none
