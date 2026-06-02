# WU-ENGINE-01 Slice 1 Code Review Controller Adjudication

## Context

- Work unit: WU-ENGINE-01 Runner diagnostic payload audit.
- Gate: Slice 1 code review.
- Approved plan: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`.
- Implementation artifact: `docs/reviews/wu-engine-01-slice1-implementation-codex-20260602.md`.
- Review artifacts:
  - `docs/reviews/wu-engine-01-slice1-code-review-mimo-20260602.md`
  - `docs/reviews/wu-engine-01-slice1-code-review-ds-20260602.md`

## Summary

Both reviewers found no blocking or high-severity issues. Controller accepts the medium findings for immediate fix because they are inside the Slice 1 write set and directly affect plan determinism / AGENTS.md compliance. Low findings are also accepted where they are cheap test or semantics clarifications.

## Finding Decisions

| ID | Source | Severity | Decision | Rationale | Required Fix |
|---|---|---:|---|---|---|
| DS-1 | AgentDS | medium | accepted | 基于 AGENTS.md 与 approved plan，已触及 parser 文件中的协议错误码不应继续散落为魔法字符串；这是同文件局部收口，不扩大架构 scope。 | 将 `non_stream_invalid_json`、`non_stream_payload_not_object`、`non_stream_missing_choices`、`non_stream_choice_not_object`、`tool_call_arguments_not_object` 提升为 `non_stream_parser.py` 模块级私有常量，并替换引用。 |
| DS-2 | AgentDS | medium | accepted | plan 明确要求敏感字段测试不能 vacuously pass；`protocol_object_diagnostic_payload` 是生产路径，必须有直接脱敏覆盖。 | 增加 protocol object diagnostic payload 的敏感字段脱敏测试，或在 SSE missing choices integration test 中构造敏感字段并断言不会泄漏。 |
| MIMO-1 | AgentMiMo | low | accepted | helper `final_decode=True` 是独立分支，直接单测成本低且能避免仅靠 parser 间接覆盖。 | 增加 `invalid_utf8_diagnostic_payload(..., final_decode=True)` 单元测试。 |
| DS-3 | AgentDS | low | accepted | 同一文件已新增多个 protocol error 常量，继续保留 `sse_invalid_json` / `sse_payload_not_object` 内联字符串会降低一致性。 | 将两处 SSE error code 提升为模块级私有常量并替换引用。 |
| DS-4 | AgentDS | low | accepted | invalid UTF-8 diagnostic 的 common digest/size 字段应直接表达被诊断的原始 bytes，避免下游误读；专用字段可以保留。 | 让 invalid UTF-8 payload 的 common `canonical_byte_size` / `sha256_digest` 使用 raw chunk bytes，测试同步断言。 |
| DS-5 | AgentDS | low | accepted | fallback 的 integration path 应证明到达 minimal structure，不只证明大小合规。 | 在 large provider error integration test 中断言 preview/top-level keys 已被移除。 |

## Gate Decision

Decision: fix required before Slice 1 re-review.

No design_doc change, public contract shape change, Host state-machine change, durable schema change, or user decision is required.

