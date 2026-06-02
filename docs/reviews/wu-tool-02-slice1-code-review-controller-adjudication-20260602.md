# WU-TOOL-02 Slice 1 Code Review Controller Adjudication

## 范围

- Work unit: `WU-TOOL-02 Accept Candidate Structure Cleanup`
- Gate: Slice 1 code review adjudication
- Implementation report: `docs/reviews/wu-tool-02-slice1-implementation-report-20260602.md`
- Reviews:
  - `docs/reviews/wu-tool-02-slice1-code-review-mimo-20260602.md`
  - `docs/reviews/wu-tool-02-slice1-code-review-ds-20260602.md`

## 总控结论

Slice 1 实现总体符合 approved plan：未改变 `ToolFactAcceptCandidate` 顶层字段、producer、accept barrier consumer、tests 或 EventLog payload 行为，验证报告可信。

但 MiMo Finding 01 发现新 duplicate helper 对 `ALLOW` 决策的 scope / message 校验与现有 `_validate_duplicate_fields` 语义不一致。该 finding 虽然当前未接入生产路径、严重度低，但它会直接影响 Slice 2 迁移后的语义保持，因此必须在 Slice 1 fix gate 内关闭。

基于 `docs/host/design.md` 的设计目标和第一性原理，Host / ToolRuntime governance 结构清理只能搬迁现有语义，不能在未设计的情况下改变 duplicate governance 字段要求。接受该 finding 是当前 phase 的最佳实践选择。

## Finding 裁决

| 来源 | Finding | 裁决 | 理由 | Required fix |
|---|---|---|---|---|
| AgentMiMo | 01 `_validate_tool_accept_duplicate_governance` 对 `ALLOW` 决策的校验语义与现有 `_validate_duplicate_fields` 不一致 | accepted | 新 helper 是 Slice 2 迁移的目标语义；若保留分歧，会把当前 candidate validator 语义静默改变到下一 slice。 | 调整新 helper，使任何非 `None` duplicate decision 都要求 `duplicate_scope` 与 `duplicate_decision_message`，并保持只有 reuse/hint/require_justification/hard_stop/durable_missing 要求 `duplicate_key`，对齐现有 `_validate_duplicate_fields`。 |
| AgentMiMo | 02 `_validate_tool_accept_governance` 中 typed dataclass 字段 `isinstance` 检查冗余 | rejected | 这类防御性检查与现有 candidate validation 风格一致，不改变行为；当前 slice 不为样式偏好做额外 churn。 | 无。 |
| AgentMiMo | 03 `_validate_tool_accept_result` payload ref / digest 检查需确认 plan 意图 | rejected | Review 已确认该检查是现有 `_validate_common_candidate_fields` 的精确复制，符合 plan 对“当前已有 candidate 校验”的约束。 | 无。 |
| AgentDS | 无 findings | accepted-pass | DS 独立验证未发现阻断问题。 | 无。 |

## 下一步

派 implementation agent 执行 Slice 1 fix，只修改 `dayu/host/tool_runtime.py` 与 fix report artifact。Fix 完成后重新派 MiMo / DS re-review。
