# WU-ENGINE-01 Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: WU-ENGINE-01 Runner diagnostic payload audit.
- Gate: aggregate deepreview + accepted fix re-review.
- Design source: `docs/host/design.md`.
- Control doc: `docs/host/host-core-followup-implementation-control.md`.
- Aggregate review artifacts:
  - `docs/reviews/wu-engine-01-aggregate-deepreview-mimo-20260602.md`
  - `docs/reviews/wu-engine-01-aggregate-deepreview-ds-20260602.md`
- Fix and re-review artifacts:
  - `docs/reviews/wu-engine-01-aggregate-fix-codex-20260602.md`
  - `docs/reviews/wu-engine-01-aggregate-fix-rereview-mimo-20260602.md`
  - `docs/reviews/wu-engine-01-aggregate-fix-rereview-ds-20260602.md`

## Controller Decision

### DS F-01: 破折号形态敏感 key 未覆盖

- Decision: accepted and fixed.
- Reason: 该 finding 直接落在 WU-ENGINE-01 的脱敏边界上；虽然触发概率低，但修复是统一 key normalization，不引入过度设计。
- Fix: `_is_sensitive_key` 改为基于 `_normalized_sensitive_key` 匹配，统一将破折号规范化为下划线。
- Re-review: AgentMiMo 与 AgentDS 均确认 closed。

### DS F-02: 非字符串 provider error code/type/param 被丢弃

- Decision: accepted and fixed.
- Reason: 该 finding 影响诊断信息完整性；保留 JSON 标量符合有界诊断 payload 的目标，不改变事件字段形状。
- Fix: `_provider_error_summary` 改为通过 `_provider_error_scalar_preview` 保留非空字符串、数字、布尔值与 null，过滤空字符串和容器。
- Re-review: AgentMiMo 与 AgentDS 均确认 closed。

### MiMo Low: 测试 helper 跨文件重复

- Decision: deferred-with-owner.
- Reason: 该 finding 是测试维护性问题，不影响 WU-ENGINE-01 的 runtime correctness、安全边界或 public contract；当前 gate 不扩大为测试 helper 重构。
- Owner / Destination: future Engine test helper cleanup.
- Tracking: recorded as `RR-ENGINE-01-01` in the control doc.

## Validation

Controller closeout verification:

```bash
source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_http_error_event.py tests/host/test_engine_ingest_mapping.py
```

Result:

```text
97 passed in 0.55s
```

```bash
source .venv/bin/activate && pyright
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

## README / Docs Sync

No additional README update is required after the aggregate fix. The stable user-facing contract remains the same: Engine `raw_payload` is a bounded, redacted, summarized diagnostic payload and not guaranteed provider raw JSON. `dayu/engine/README.md` already states this contract.

## Conclusion

PASS. WU-ENGINE-01 aggregate deepreview findings are either fixed and re-reviewed, or recorded with an owner. The local gate is ready for the accepted aggregate deepreview commit and then `ready-to-open-draft-PR`.
