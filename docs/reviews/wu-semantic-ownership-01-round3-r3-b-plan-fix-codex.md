# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B Plan Fix — AgentCodex

## Gate 与状态

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-B`
- Gate：plan review 后的 plan-fix
- 执行者：AgentCodex
- Plan artifact：`docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`
- 本 artifact：`docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-fix-codex.md`
- 状态：`ready-for-plan-rereview`
- 下一入口：AgentMiMo / AgentDS plan re-review

本 gate 只修 controller 接受的 `PF-01` 至 `PF-05`。未进入 implementation，未修改生产代码、测试或 README，未 commit、push或创建 PR。

## Review inputs

- `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-ds.md`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-controller-adjudication.md`

Controller 已确认目标、owner boundary、3 slices 与 source-finding 裁决成立；本 fix 不重新裁决原 finding，只补足 implementation-ready contract、反例和 validation guard。

## Changed files

1. `docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`
2. `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-fix-codex.md`

三份 plan-review artifacts 仅作为只读输入，未修改。

## PF finding 处理

### PF-01 — post-done cancellation rejection test matrix

状态：`已修复`

Plan 处理位置：

- S1 frozen decision 明确测试必须手动驱动 Agent async iterator：先读到 `ITERATION_COMPLETED`，再调用 `token.request_cancel()`，避免 Runner yield 后自取消造成 pre/post-done 时点歧义。
- S1 concrete assertions 固定五个反例：ordinary final、force-answer final、protocol error done、HTTP error done、tool-call done。
- 明确前四类 terminal 不得变为 `RUN_CANCELLED`；tool-call 类必须先投影 batch-ready 与全部 requested事实，之后才允许 cancellation handshake 收口。
- S1 validation commands 增加上述 test node ids；原 done 前取消测试继续要求 `RUN_CANCELLED`。

未改范围：不改变 Host cancellation owner，不修改 ToolExecutor 已开始后的取消治理，不把 tool-call done解释为忽略后续全部取消。

### PF-02 — finish_reason forcing semantic guard

状态：`已修复`

Plan 处理位置：

- S2 frozen decision 明确 parser 内每个 `FinishReason.TOOL_CALLS` 命中只能是 `_choice_policy` 显式 wire fact、比较/诊断或 fail-closed terminal policy；parser direct success forcing禁止。
- S2 validation commands保留 exact direct-assignment scan，并新增覆盖 `_choice_policy.py`、`non_stream_parser.py`、`sse_parser.py` 的 `FinishReason.TOOL_CALLS` 语义级 scan。
- S2 completion rule要求 implementation artifact与 reviewer逐项分类语义 scan命中；helper重命名、变量改名或拆行不能替代人工语义审计。
- Aggregate validation同步加入同一语义 scan与零容忍判定。

未改范围：不把 source scan当成完整证明，不新增 finish-reason profile或 provider capability配置。

### PF-03 — position routing identity conflicts

状态：`已修复`

Plan 处理位置：

- S2 frozen decision把 index、provider id、position三种 routing signal统一送入同一个 identity-binding validator；position fallback不能绕过 occupied target、same id/two indices、same index/two ids或 remap merge规则。
- 明确 position只允许无 index/id continuation追加到已无歧义绑定的 partial。
- S2 negative matrix新增 position positive continuation与 position-routed occupied-target conflict：A占用 native 0，B通过 synthetic/position累积 fragment，B再声明 native 0时必须 fatal，fragment不得与A拼接。
- S2 validation commands增加 `test_position_routed_conflict_fails_closed_without_merge` 单点验证，并保留完整 identity-conflict test file。

未改范围：不删除 synthetic index或合法 position continuation，不把同一数组 position机械定义为跨所有 chunk 的全局 identity。

### PF-04 — runner exception uses first-candidate owner

状态：`已修复`

Plan 处理位置：

- S1 frozen decision规定 protocol、HTTP、context与 runner generator exception 的所有 `failure_candidate` 写入必须通过同一 module-level first-candidate helper。
- 明确 `agent.py` 除 helper内部唯一赋值外不得直接写 `state.failure_candidate`；后来的 runner exception只记录诊断，不能覆盖已接受 code/id/recoverable/correlation。
- 明确 exception 无 RunnerDone commit：token 已取消时按 pre-done规则收口 `RUN_CANCELLED`；未取消且无已有 candidate时才以 `runner_exception` 失败。
- S1 assertions与 validation commands增加 first-candidate保留、exception+cancel顺序测试，以及 `state.failure_candidate =` 唯一 owner赋值 scan。

未改范围：不让 failure candidate覆盖 Host lifecycle，不改变非致命 provider diagnostic不进入 failure candidate的既有规则。

### PF-05 — Agent finish_reason fallback fail closed

状态：`已修复`

Plan 处理位置：

- S1 frozen decision删除 `state.finish_reason or FinishReason.STOP`，不保留过渡默认值。
- `_consume_runner_event()` 在 commit `RunnerDoneData` 前验证 `finish_reason` 是 `FinishReason`；非法/缺失值不写 `state.runner_done`、不产出 `ITERATION_COMPLETED`，通过 first-candidate owner记录 `RUNNER_ABNORMAL_STOP` 诊断。
- `_classify_iteration()` 只在 typed `runner_done` 非空时读取 finish reason；缺失沿 failure/abnormal-stop路径收口，不允许 fallthrough到 tool/final分支。
- S1 assertions与 validation commands增加 malformed `RunnerDoneData` fail-closed测试及 `or FinishReason.STOP` deletion scan。

未改范围：不新增公开 optional finish_reason，不让 Agent替 provider parser推断 STOP/TOOL_CALLS，不把该 guard做成 compatibility branch。

## Scope and adjudication invariants

- Implementation slices 仍为 3：S1 Engine contract/Agent state，S2 OpenAI adapter normalization，S3 schema/runtime。
- Source finding 裁决保持 `accepted=7 / narrowed=1 / rejected=2`。
- runner identity length-framed encoding 与 structured-code-first error marker fallback继续为 `rejected-with-reason`，没有生产改动计划。
- 未新增 Host repair、OLD dict arguments shim、provider capability profile、通用 JSON Schema engine或第四个 slice。
- README/design trigger decisions未改变；本 plan-fix gate不提前修改任何 README/design truth。

## Validation

要求并执行：

```bash
git diff --check
git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md
git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-fix-codex.md
```

结果：`git diff --check` exit 0、无输出。两条 no-index check均无 whitespace diagnostic；exit 1仅表示对应未跟踪 artifact与 `/dev/null` 存在内容差异，不表示 check failure。

## Residual risks

无新增或未分类 residual risk。原 plan中的 fail-closed provider风险、synthetic delta preview约束与 rejected marker/delimiter项保持原 owner和分类。

## Stop status

- Plan fix：`PF-01` 至 `PF-05` 全部已修复，等待独立 re-review。
- Blocking questions：无。
- 本 gate停止在 `ready-for-plan-rereview`；不得进入 implementation。
