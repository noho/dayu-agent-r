# WU-ENGINE-01 Plan Review Controller Adjudication

## Context

- Work unit: WU-ENGINE-01 Runner diagnostic payload audit.
- Gate: plan review.
- Plan artifact: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`.
- Review artifacts:
  - `docs/reviews/wu-engine-01-plan-review-mimo-20260602.md`
  - `docs/reviews/wu-engine-01-plan-review-ds-20260602.md`
- Design source: `docs/host/design.md`.
- Control source: `docs/host/host-core-followup-implementation-control.md`.

## Summary

Both reviewers passed the plan with no blocking findings. Controller decision is to enter plan fix before implementation because several medium findings affect implementation determinism, not architecture scope. This keeps the work unit aligned with the design goal: fix the diagnostic payload boundary without letting implementation agents invent typed boundaries or fallback behavior.

## Finding Decisions

| ID | Source | Severity | Decision | Rationale | Required Plan Fix |
|---|---|---:|---|---|---|
| MIMO-M-01 / DS-FIND-02 / DS-FIND-03 / DS-FIND-04 / DS-FIND-05 / DS-RR-02 | MiMo + DS | medium | accepted | 基于 design_doc 的设计目标，Engine diagnostic helper 必须可维护、可测试且边界明确；敏感字段、子对象提取、超限 fallback、reason 区分不能留给 implementation agent 猜。 | 补 `_SENSITIVE_KEY_FRAGMENTS` 初始值与匹配策略、独立 `test_diagnostic_payload.py`、provider error sub-object 提取规则、fallback 优先级、两种 missing choices reason 常量。 |
| MIMO-M-02 | MiMo | medium | accepted | `raw_payload` 是 opaque diagnostic，但 plan 应明确 version 初值和 Host 不解析策略，避免 implementation agent 引入 Host-side version reader。 | 写明 initial version = 1；Host ingest 当前只 opaque 写入，不做 version-aware read；未来解析需独立 design。 |
| DS-FIND-01 | DS | medium | accepted | 魔法字符串治理属于当前 helper 收口的一部分；SSE invalid UTF-8 error_code 常量提升应在 exact changes 中明确。 | Slice 1 exact changes 增加 `_INVALID_UTF8_CODE` / `_TRUNCATED_UTF8_TAIL_CODE` 模块级私有常量。 |
| DS-FIND-06 | DS | medium in summary / low in body | accepted | non-stream invalid UTF-8 虽不经过 raw payload helper，但 plan 已提出调用点常量化原则；将其列为 Slice 1 小范围收口不扩大 scope。 | Slice 1 exact changes 增加 non-stream `_INVALID_UTF8_CODE` 模块级私有常量，或明确若不改则为 non-goal；controller preference is to fix because file is already touched. |
| MIMO-L-01 | MiMo | low | accepted | 计划描述应区分 invalid UTF-8 的已有 custom payload 与 `dict(parsed)` 原样路径，避免误导 implementation。 | 更新 motivation / direct evidence wording。 |
| MIMO-L-02 / DS-FIND-07 | MiMo + DS | low | accepted | redaction 测试必须构造敏感字段，否则会 vacuously pass；`repr` 断言可被 JSON serialization / leaf traversal 替代。 | 测试要求改为构造敏感字段，并用 `json.dumps(..., ensure_ascii=False)` 或递归叶子检查，不依赖 `repr`。 |
| DS-FIND-08 | DS | low | accepted | plan 中 provider-level error code 与 runner-level `error_code` 术语容易混淆，影响测试断言清晰度。 | 改写为 "provider error object 内的 `code` 字段" 与 "`RunnerProtocolErrorData.error_code`"。 |
| DS-FIND-09 / DS-RR-01 | DS | low | accepted | canonical byte size 是 diagnostic，不是 durable truth；实现仍需固定算法，避免 review 时无法判断 digest / size 一致性。 | 写明使用 local `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(',', ':'))` 计算，不依赖 `dayu.runtime`，且不要求与 durable canonicalization 一致。 |
| DS-FIND-10 | DS | low | accepted | 重命名测试可提升 review 可读性，成本低。 | 给出建议测试名 `test_http_json_object_error_body_produces_bounded_diagnostic_payload`。 |

## Gate Decision

Decision: plan fix required.

The findings do not require design_doc changes, public contract shape changes, Host state-machine changes, durable schema changes, or user decision. They should be handled by the planning agent in the plan artifact, then sent to both reviewers for plan re-review.

