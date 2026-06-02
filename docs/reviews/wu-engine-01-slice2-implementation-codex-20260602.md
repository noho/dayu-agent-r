# WU-ENGINE-01 Slice 2 Implementation Artifact

## Gate / Role

- Current gate: `implementation`
- Role: WU-ENGINE-01 Slice 2 implementation agent
- Work unit: WU-ENGINE-01 Runner diagnostic payload audit
- Approved plan: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`
- Slice: Slice 2 HTTP Error Raw Payload 摘要化 + Host 诊断映射守卫
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`

## Scope / Non-goals

- 本次只实现 Slice 2 handoff 指定范围。
- 未提交、未 push、未创建 PR、未进入 code review / aggregate deepreview / draft PR gate。
- 未修改 Host production、Host 状态机、EventLog schema、provider state sealed union、public dataclass 字段形状或 event type。

## Motivation Check

动机成立。Slice 1 已经收口协议错误诊断载荷，但 HTTP 错误路径仍在 `_safe_read_error_body` 中把 JSON object 解析结果作为 `RunnerHTTPErrorData.raw_payload` 精确保留。该问题的真实边界是 Runner 诊断载荷治理，不需要修改 Host 状态机或 public event contract。

## Changed Files

- `dayu/engine/runners/openai/diagnostic_payload.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/contracts/runner_events.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `tests/host/test_engine_ingest_mapping.py`
- `dayu/engine/README.md`
- `docs/reviews/wu-engine-01-slice2-implementation-codex-20260602.md`

## Implemented Plan Items

- 新增 `http_error_diagnostic_payload(payload: dict[str, JsonValue]) -> JsonValue`，复用现有有界、脱敏、摘要化诊断 helper 结构，HTTP JSON error body 不再保存完整 provider JSON。
- `AsyncOpenAIRunner._safe_read_error_body` 在 `decoded` 为 JSON object 时调用 `http_error_diagnostic_payload(decoded)`；保留 `_HTTP_ERROR_BODY_MAX_BYTES` 与 `_safe_read_error_body_bytes` 行为。
- 更新 `RunnerHTTPErrorData` 中文 docstring：`raw_payload` 是从有界 HTTP body 派生的有界诊断载荷，解析失败或非 JSON object 响应仍为 `None`。
- 将 HTTP JSON object 测试改为 `test_http_json_object_error_body_produces_bounded_diagnostic_payload`，断言：
  - `message` 文本保持 HTTP body 文本；
  - `provider_request_id` 仍只来自 header；
  - `raw_payload` 含 byte size、digest、provider error `code` / `type`；
  - 敏感值和 body 内 request id 不进入诊断载荷；
  - 不再断言 exact raw provider payload。
- 补强 retry exhausted HTTP 测试，保持最终 attempt 的 `provider_request_id` 断言，并改为诊断载荷断言。
- 补强 HTTP body cap 测试，使用超大 JSON body 证明读取在 decode 前按 byte cap 截断，且不保存超大原始 JSON。
- Host ingest 映射测试只把 fixture 改为 helper-like diagnostic JSON object，仍只断言 `raw_payload_ref` 存在和 Run / Attempt 状态不变。
- Engine README 增加稳定 developer contract 说明：Runner / Provider diagnostic `raw_payload` 是有界、脱敏、摘要化 JSON，不保证保留 provider 原始 payload。

## Validation

```bash
source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_engine_ingest_mapping.py
```

Result:

```text
67 passed in 0.64s
```

```bash
source .venv/bin/activate && pyright
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

Pyright also printed an upstream version notice: `v1.1.409 -> v1.1.410`; this is not a type-check failure.

## Docs Decision

`dayu/engine/README.md` was updated because this Slice changes Engine developer-facing diagnostic `raw_payload` semantics. The update is contract-level only and does not include implementation details, process status, changelog, or future plans.

## Residual Risks / Uncovered Areas

- No known blocking residual risk in Slice 2 scope.
- HTTP diagnostic payload structure is intentionally opaque to Host; Host ingest still only stores a `raw_payload_ref` and does not parse the diagnostic JSON.
- Full work-unit aggregate behavior remains for the controller's later aggregate deepreview gate; this implementation artifact does not claim aggregate review completion.

## Stop Condition Status

- Did not need to change HTTP message text behavior.
- Did not change public HTTP error dataclass fields.
- Did not modify Host production, Host state machine, EventLog schema, provider state sealed union, or event type.
- Did not need `Any`, `object`, `getattr`, `hasattr`, or extra payload to implement this Slice.

## Blocking Questions

None.

## Suggested Next Gate

Return to controller for Slice 2 code review.
