# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B Plan Review — AgentMiMo

## Review Target

`docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`

## Design / Control Context

- `docs/engine/design.md` — Engine 架构真源
- `docs/host/design.md` — Host 架构真源
- `docs/host/issues-implementation-control.md` — issue-backed 实施总控
- `docs/phaseflow-umbrella-optimization-control.md` — umbrella 优化总控
- `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md` — Round3 裁决

## Assumptions Tested

1. 7 accepted / 1 narrowed / 2 rejected 的 source finding 裁决是否有直接代码证据。
2. Owner boundary 划分是否正确：Engine contracts / provider parser aggregator / message-event discriminator；Host 不下游补救。
3. 3 slices 是否是最小 owner-closed 切分。
4. S1 RunnerDone commit boundary 覆盖范围。
5. S2 OpenAI parser/aggregator 覆盖范围。
6. S3 JSON Schema bounds / enum equality owner。
7. Validation matrix 可执行性。
8. README / design trigger 决策。

## Findings

### 01-未修复-中-S1 RunnerDone commit boundary 缺少 post-done 取消拒绝路径的显式测试

- **位置**: S1 Concrete assertions — "迟到取消矩阵"；S1 Allowed tests
- **问题类型**: 测试缺口
- **当前写法**: plan 声称"迟到取消矩阵：ordinary STOP final、force-answer final、protocol ERROR done、HTTP ERROR done、tool-call done。前四类不得变 `run_cancelled`"，并列出 `test_agent_phase2.py` 作为 allowed test。
- **反例/失败场景**: 代码在 `agent.py:891-895` 有 `if self._is_cancelled() and not state.done_seen` guard，在 `agent.py:2346` 有同样 guard。但现有 `test_agent_phase2.py:1401-1428` 的 `test_cancel_before_final_answer_wins_over_final` 只覆盖 done **前**取消（token 在 content_completed 后、done 前取消，断言最终为 `run_cancelled`）。没有测试覆盖 done **后**取消被拒绝的路径——即 RunnerDone 已 yield、`done_seen=True`、随后 token 取消，断言最终不是 `run_cancelled` 而是 done-derived terminal。
- **为什么有问题**: plan 的 success signal #1 明确承诺"其后到达的取消不再在 Agent 内层插入矛盾的 `run_cancelled`"，S1 concrete assertions 也列出该矩阵。但实现 agent 可能只写满足现有测试的代码（done 前取消），而遗漏 post-done rejection 路径的测试。如果没有显式测试，该 commit boundary 的回归保护依赖 code review 而非自动化。
- **直接证据**: `tests/engine/test_agent_phase2.py:1401-1428` 只测试 pre-done cancellation；`agent.py:891-895` 和 `agent.py:2346` 的 post-done guard 无对应测试。
- **影响**: 实施 agent 可能遗漏 post-done cancellation rejection 测试，导致该路径无回归保护；aggregate deepreview 需要额外发现并修补。
- **建议改法和验证点**: S1 allowed tests 应新增一个测试用例：ScriptedRunner 先 yield RunnerDone(STOP) + ITERATION_COMPLETED，然后 token 取消，断言最终 terminal 是 `final_answer`（或 `run_failed`）而非 `run_cancelled`。force-answer、error、tool-call 三路需类似覆盖。验证点：取消后最终 event type 不是 `run_cancelled`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 02-未修复-低-S2 source scan 对 finish_reason forcing 的扫描模式可能被等价重构绕过

- **位置**: S2 Validation commands — `rg -n 'done_finish_reason = FinishReason\.TOOL_CALLS|finish = FinishReason\.TOOL_CALLS'`
- **问题类型**: 测试缺口（边缘）
- **当前写法**: plan 使用两条 rg 模式检测 non-stream 和 SSE parser 中的 finish_reason forcing 行为，并注明"不能用重命名或拆行逃避扫描；review 需读取实际分支"。
- **反例/失败场景**: 如果实现 agent 将 forcing 逻辑重构为 helper 函数（如 `_normalize_finish_reason(has_tool_calls, raw_reason)`），局部变量名改为不同于 `done_finish_reason` 或 `finish` 的名字，source scan 将无命中。虽然 plan 说"review 需读取实际分支"，但 scan 的设计意图是作为自动化 guard，如果它不能捕获等价重构，则其可靠性依赖人工 review。
- **为什么有问题**: source scan 的价值在于自动化、可重复的 guard。如果它只能捕获 exact pattern 而非 semantic pattern，实施 agent 需要理解 scan 的意图而非依赖 scan 结果。
- **直接证据**: `non_stream_parser.py:362-370` 使用 `done_finish_reason = FinishReason.TOOL_CALLS`；`sse_parser.py:683` 使用 `finish = FinishReason.TOOL_CALLS`。二者变量名不同，scan 需要同时匹配两种命名。
- **影响**: 低。plan 已说"review 需读取实际分支"，且 aggregate deepreview 会做语义级检查。但如果 scan 被用作唯一 guard，可能遗漏。
- **建议改法和验证点**: 可以在 validation commands 中补充一条语义级 scan：`rg -n 'FinishReason\.TOOL_CALLS' dayu/engine/runners/openai/non_stream_parser.py dayu/engine/runners/openai/sse_parser.py` 并要求人工确认每一处都经过 `_choice_policy` 或显式 tool-call presence guard。验证点：所有 TOOL_CALLS 赋值都来自 fail-closed 逻辑。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。plan 的 blocking questions 声明为无，代码证据支持该判断。

## Residual Risks

| Risk / uncovered area | Classification | Owner / destination |
| --- | --- | --- |
| Synthetic index 在 delta preview 中使用负内部 key | accepted current design | `ToolCallAggregator`；见 plan residual risks 表 |
| 严格拒绝 dict arguments 可能暴露非规范 provider | fixed by fail-closed policy | 若有真实 provider contract，需独立 adapter WU |
| Context overflow marker 覆盖语言/厂商有限 | rejected current finding | OpenAI error classifier |
| Source scan 可被等价重构绕过 | review-level guard | aggregate deepreview 作为最终 guard |

## Plan Review Conclusion

**status: pass-with-risks**

plan 整体质量高：

- 10 项 source finding 裁决均有直接代码证据支撑，7 accepted / 1 narrowed / 2 rejected 的分类成立。
- Owner boundary 划分正确：Engine contracts / provider parser aggregator / message-event discriminator 三个 owner 各自封闭，Host 不做下游补救。
- 3 slices 是最小 owner-closed 切分，不违反 umbrella optimization 约束。
- S1 RunnerDone commit boundary 设计正确覆盖了 ordinary final、force-answer final、error done、tool-call done 和 done 前取消。
- S2 OpenAI parser/aggregator 覆盖了 native/synthetic identity conflict、OLD dict arguments removal、finish_reason mismatch。
- S3 JSON Schema bounds / enum equality 在正确 owner 处，scope 不过度扩展。
- Validation matrix 具体且可执行。
- README / design trigger 决策符合 AGENTS.md。

唯一 material finding 是 S1 缺少 post-done cancellation rejection 的显式测试覆盖。这是一个中等严重程度的测试缺口，但修复风险低，可在 implementation 阶段轻松补齐。

**artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-mimo.md`
**findings**: 2（1 中等、1 低）
**blocking questions**: 0
