# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B Plan Re-Review — AgentMiMo

## Review Target

`docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`（plan-fix 后版本）

## Review Inputs

- `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-mimo.md`（初审 artifact）
- `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-ds.md`

## Review Focus

1. PF-01..PF-05 是否都已落实到具体 implementation decisions / assertions / negative matrix / validation commands。
2. 是否仍保持 3 slices，未扩大 scope，未改变 7 accepted / 1 narrowed / 2 rejected source finding 裁决。
3. 是否没有引入 Host 下游补救、compat shim、provider capability profile、通用 JSON Schema engine。
4. validation commands 是否可执行，尤其 post-done cancellation、position-routed conflict、first-candidate 唯一赋值、finish_reason typed fail-closed、TOOL_CALLS 语义 scan。

## Assumptions Tested

1. PF-01 post-done cancellation rejection 是否有具体测试名称、驱动方式、预期结果和 validation commands。
2. PF-02 finish_reason forcing 是否有语义级 scan 和人工分类要求。
3. PF-03 position routing 是否纳入 identity conflict rules 和 negative matrix。
4. PF-04 runner exception 是否统一使用 first-candidate helper。
5. PF-05 Agent finish_reason fallback 是否删除并替换为 fail-closed guard。
6. Source finding 裁决和 slice 数量是否不变。
7. 是否引入禁止的 compat shim 或下游补救。

## PF Finding 落实验证

### PF-01 ✅ 已落实

- S1 concrete assertions 新增 5 个命名测试：`test_post_done_cancel_does_not_override_ordinary_final`、`test_post_done_cancel_does_not_override_force_answer_final`、`test_post_done_cancel_does_not_override_protocol_error_failure`、`test_post_done_cancel_does_not_override_http_error_failure`、`test_post_done_cancel_does_not_skip_tool_call_candidate`（plan line 174）。
- 驱动方式明确：`anext()` 驱动到 `ITERATION_COMPLETED`，再 `token.request_cancel()`（plan line 174）。
- 预期结果明确：ordinary/force-answer 终态为 `FINAL_ANSWER`；protocol/HTTP error 保留原 code/id/recoverable；tool-call 先投影 batch-ready + requested（plan line 175-176）。
- Validation commands 包含具体 test node ids（plan line 185）。
- S1 frozen decision #5 补充 post-done test 驱动方式约束（plan line 108）。

### PF-02 ✅ 已落实

- S2 frozen decision #7 明确 parser 内 `FinishReason.TOOL_CALLS` 命中只能来自 `_choice_policy` 显式 fact、比较/诊断或 fail-closed policy（plan line 127）。
- S2 validation commands 新增 `FinishReason.TOOL_CALLS` 语义级 scan（plan line 254）。
- S2 completion rule 要求 implementation artifact 和 reviewer 逐项分类语义 scan 命中（plan line 259）。
- Aggregate validation 同步加入同一语义 scan（plan line 353）。

### PF-03 ✅ 已落实

- S2 frozen decision #4 将 index、provider id、position 三种 routing signal 统一送入同一个 identity-binding validator（plan line 124）。
- S2 negative matrix 新增 position positive continuation 和 position-routed occupied-target conflict（plan line 238-239）。
- S2 validation commands 增加 `test_position_routed_conflict_fails_closed_without_merge`（plan line 249）。

### PF-04 ✅ 已落实

- S1 frozen decision #8 明确所有 `failure_candidate` 写入必须通过 module-level first-candidate helper（plan line 111）。
- S1 frozen decision #9 明确 exception 与取消并发且无 RunnerDone 时按 pre-done 规则收口（plan line 112）。
- S1 validation commands 增加 `state.failure_candidate =` scan，预期只命中 helper 内部唯一赋值（plan line 190, 194）。
- S1 concrete assertions 增加 first-candidate 保留和 exception+cancel 顺序测试（plan line 177）。

### PF-05 ✅ 已落实

- S1 frozen decision #10 删除 `state.finish_reason or FinishReason.STOP`（plan line 113）。
- `_consume_runner_event()` 在接受 `RunnerDoneData` 前验证 `finish_reason` 是 `FinishReason`；非法/缺失值通过 first-candidate helper 记录 `RUNNER_ABNORMAL_STOP`（plan line 113）。
- `_classify_iteration()` 在 `runner_done is None` 时只走 failure/abnormal-stop fail-closed 分支（plan line 113）。
- S1 validation commands 增加 `or FinishReason\.STOP` deletion scan（plan line 189）。
- S1 concrete assertions 增加 malformed `RunnerDoneData` fail-closed 测试（plan line 178）。

## Invariant 验证

### 3 slices 不变 ✅

Plan 仍为 S1 Engine contract/Agent state、S2 OpenAI adapter normalization、S3 schema/runtime（plan line 141）。未新增第四 slice。

### Source finding 裁决不变 ✅

`accepted=7 / narrowed=1 / rejected=2`（plan line 72, 409）。runner identity delimiter 和 error classifier 维持 `rejected-with-reason`。

### 无 Host 下游补救 / compat shim ✅

- Plan scope boundary 明确不新增 provider registry、finish-reason capability profile、通用 JSON Schema validator（plan line 45）。
- 不实现旧 dict arguments 兼容 adapter（plan line 46）。
- Host 不新增 provider parsing、event repair、fallback 或 schema compatibility（plan line 39）。
- Aggregate validation 检查 `hasattr/getattr`、compatibility flag、provider 名单、loose parsing 或反向依赖（plan line 340, 357）。

### Validation commands 可执行性 ✅

- Post-done cancellation：具体 test node ids 在 validation commands 中（plan line 185）。
- Position-routed conflict：具体 test node id 在 validation commands 中（plan line 249）。
- First-candidate 唯一赋值：`state.failure_candidate =` scan 指向 `agent.py`（plan line 190）。
- Finish_reason typed fail-closed：`or FinishReason.STOP` scan 指向 `agent.py`（plan line 189）。
- TOOL_CALLS 语义 scan：覆盖 `_choice_policy.py`、`non_stream_parser.py`、`sse_parser.py`（plan line 254）。

## Findings

未发现实质性问题。PF-01 至 PF-05 全部已落实到具体 implementation decisions、concrete assertions、negative matrix 和 validation commands。Plan 保持 3 slices、source finding 裁决不变，未引入 Host 下游补救或 compat shim。Validation commands 可执行且具体。

## Open Questions

无。

## Residual Risks

与原 plan review 一致，无新增。PF-01 至 PF-05 的修复均为 plan 层面补充，不引入新的 residual risk。

## Plan Review Conclusion

**status: pass**

Plan-fix 后版本已满足所有 controller adjudication 约束。PF-01 至 PF-05 全部落实到具体 plan 文本，3 slices 和 source finding 裁决不变，validation commands 可执行。Plan 可进入 implementation gate。

**artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-rereview-mimo.md`
**findings**: 0
**blocking questions**: 0
