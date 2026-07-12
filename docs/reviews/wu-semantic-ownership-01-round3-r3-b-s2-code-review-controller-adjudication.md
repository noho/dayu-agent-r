# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B S2 Code Review Controller Adjudication

## 裁决范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-B`
- Slice：`S2 — OpenAI Tool Identity And Terminal Protocol Normalization`
- Implementation artifact：`docs/reviews/wu-semantic-ownership-01-round3-r3-b-s2-implementation-codex.md`
- Controller validation：`docs/reviews/wu-semantic-ownership-01-round3-r3-b-s2-controller-validation.md`
- Code review artifacts：
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-b-s2-code-review-ds.md`

## 总体结论

S2 code review 通过。AgentMiMo 与 AgentDS 均返回 `pass`，`findings=0`，`blocking questions=0`。Controller 接受 S2 implementation；无需 fix / re-review gate。

## Review 结论合并

- `ToolCallAggregator` 现在只接受非 bool、非负 int native index；显式非法 index 产生 `tool_call_invalid_index` fatal，且不回落到 id/synthetic routing。
- index / id / position 三种 routing signal 在 aggregator owner 内统一绑定；synthetic -> occupied、same id -> two native indices、same native index -> two ids、position-routed occupied target 均 fail closed。
- 旧 partial merge 被删除；fatal identity conflict 后不会拼接 name / arguments / provider state，也不会产出 completed tool calls。
- `_choice_policy.py` 是 SSE / non-stream terminal shape 的唯一 owner；parser 中没有 direct `FinishReason.TOOL_CALLS` forcing。
- missing/null finish reason、tool calls + non-tool finish reason、content + `TOOL_CALLS` 均在 completed event 前 fail closed。
- non-stream `function.arguments` 只接受 string；dict/list/number/bool/null/missing 不再兼容成功，invalid JSON string 与 JSON non-object string 保持既有 fatal 分类。
- S2 negative/positive matrix 由新增 `test_tool_call_identity_conflicts.py` 与 OpenAI parity / OLD protocol tests 锁定。

## Controller validation accepted

- Position-routed conflict node：`1 passed`
- S2 focused matrix：`109 passed`
- Full OpenAI adapter suite：`302 passed`
- Pyright：`0 errors`
- Compatibility / direct forcing / merge source scans：无输出
- `FinishReason.TOOL_CALLS` semantic scan：仅命中 `_choice_policy.py` 的 explicit wire mapping 和 fail-closed comparison
- `git diff --check`：无输出

## Scope / residuals

- S2 未修改 Agent、Host、runtime schema、ToolParametersSchema、Fins、Service、CLI、README 或 design docs。
- MiMo 提到的 non-stream `function` 非 dict 时诊断为 `arguments must be string` 属于 diagnostic precision，不影响当前 semantic owner correction，且未形成 accepted finding。
- Synthetic delta preview 使用负内部 key 仍为 accepted current design，按 plan 保留到独立 EngineEvent contract WU，不能由 Host 修复。
- 当前没有 accepted S2 finding 或 blocking question。

## 下一 gate

提交 S2 accepted commit 后进入 R3-B S3 implementation：`JSON Schema Bounds And Typed Enum Equality`。S3 完成后再统一处理 docs/engine/design、dayu/engine/README 与 tests/README 同步。
