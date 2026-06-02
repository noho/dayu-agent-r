# WU-ENGINE-01 Plan Fix — Codex

## Gate / Scope

- Gate: plan fix。
- Work unit: WU-ENGINE-01 Runner diagnostic payload audit。
- Plan artifact edited: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`。
- Source review artifacts:
  - `docs/reviews/wu-engine-01-plan-review-mimo-20260602.md`
  - `docs/reviews/wu-engine-01-plan-review-ds-20260602.md`
- Controller adjudication: `docs/reviews/wu-engine-01-plan-review-controller-adjudication-20260602.md`。

本次只根据 controller adjudication 修 plan，不修改 source/tests，不 commit、不 push、不创建 PR。

## Changed Files

- `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`
- `docs/reviews/wu-engine-01-plan-fix-codex-20260602.md`

## Per-finding Fix Status

| Finding | Status | Plan fix |
|---|---|---|
| MIMO-M-01 / DS-FIND-02 / DS-FIND-03 / DS-FIND-04 / DS-FIND-05 / DS-RR-02 | fixed | 补充 `_SENSITIVE_KEY_FRAGMENTS` 初始值与 case-insensitive substring match；新增 `test_diagnostic_payload.py` allowed file 与 helper 单测覆盖；明确 provider error sub-object 提取；定义 `_DIAGNOSTIC_PAYLOAD_MAX_BYTES` fallback 顺序；为 SSE missing choices 两种语义定义 reason 常量。 |
| MIMO-M-02 | fixed | 写明 diagnostic payload initial version = 1；Host ingest 当前 opaque 写入，不做 version-aware read；未来解析需独立 design。 |
| DS-FIND-01 | fixed | Slice 1 exact changes 增加 `sse_parser.py` 的 `_INVALID_UTF8_CODE` / `_TRUNCATED_UTF8_TAIL_CODE` 模块级私有常量。 |
| DS-FIND-06 | fixed | Slice 1 exact changes 增加 `non_stream_parser.py` 的 `_INVALID_UTF8_CODE` 模块级私有常量。 |
| MIMO-L-01 | fixed | Motivation / direct evidence 明确区分 invalid UTF-8 custom payload 与 `dict(parsed)` 原样路径。 |
| MIMO-L-02 / DS-FIND-07 | fixed | redaction 测试要求改为构造敏感字段，并用 `json.dumps(..., ensure_ascii=False)` 或递归叶子检查，不使用 `repr(raw_payload)`。 |
| DS-FIND-08 | fixed | Section 8 与 slice 测试要求改为 “provider error object 内的 `code` / `type` / `param` 字段”，并区分 `RunnerProtocolErrorData.error_code`。 |
| DS-FIND-09 / DS-RR-01 | fixed | 明确 canonical byte size / digest 使用 local `json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))`，不依赖 `dayu.runtime`，不要求与 durable canonicalization 一致。 |
| DS-FIND-10 | fixed | Slice 2 指定 HTTP 测试新名称：`test_http_json_object_error_body_produces_bounded_diagnostic_payload`。 |

## Validation

未运行 pytest 或 pyright。当前 gate 是 plan fix handoff only，本次只修改文档 artifact；计划中已更新 required validation commands，供 implementation gate 执行。

## Residual Risks / Open Questions

- Blocking questions: none。
- Residual risks: none requiring deferral。所有 controller-accepted plan review findings 已修入 plan artifact。

## Stop Status

Stop conditions not triggered。未发现需要修改 design source、public contract shape、Host 状态机、durable schema 或用户决策的问题。

## Recommended Next Gate

建议进入 plan re-review。

