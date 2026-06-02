# Code Re-Review

## Scope

- Mode: re-review (controller accepted findings fix verification)
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: HEAD (accepted plan checkpoint `e55f05e`)
- Output file: `docs/reviews/wu-engine-01-slice1-code-rereview-mimo-20260602.md`
- Included scope: 6 controller-accepted findings from `docs/reviews/wu-engine-01-slice1-code-review-controller-adjudication-20260602.md`
- Excluded scope: Slice 2 HTTP runner body, Host ingest, EventLog schema
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Per-Finding Fix Verification

### DS-1 [medium] non-stream parser 剩余协议错误码内联 — 已修复

- **证据**: `non_stream_parser.py:67-74` 新增 5 个模块级私有常量：`_INVALID_JSON_CODE`、`_PAYLOAD_NOT_OBJECT_CODE`、`_MISSING_CHOICES_CODE`、`_CHOICE_NOT_OBJECT_CODE`、`_TOOL_CALL_ARGUMENTS_NOT_OBJECT_CODE`。
- **验证**: grep 确认生产代码中无残留内联字符串字面量；所有引用已替换为常量。
- **测试**: `test_non_stream_invalid_json_error_then_done` 断言 `error_code == "non_stream_invalid_json"`、`test_non_stream_payload_not_object_error` 断言 `error_code == "non_stream_payload_not_object"`、`test_non_stream_missing_choices_error` 断言 `error_code == "non_stream_missing_choices"`。

### DS-2 [medium] protocol object diagnostic payload 脱敏测试缺口 — 已修复

- **证据**: `test_diagnostic_payload.py:185-206` 新增 `test_protocol_object_diagnostic_payload_redacts_sensitive_values`。
- **验证**: 测试构造顶层敏感字段 `authorization: "Bearer protocol-secret"` 和嵌套敏感值 `metadata.token: "nested-token-value"`，断言两者均不在 diagnostic leaf strings 中。

### MIMO-1 [low] invalid UTF-8 final_decode=True 单测缺口 — 已修复

- **证据**: `test_diagnostic_payload.py:227-241` 新增 `test_invalid_utf8_diagnostic_payload_final_decode_empty_chunk`。
- **验证**: 测试传 `chunk=b""`, `final_decode=True`，断言 `canonical_byte_size == 0`、`sha256_digest` 为空 chunk 的 SHA-256、`chunk_prefix_base64 == ""`、`final_decode is True`。

### DS-3 [low] SSE parser 剩余协议错误码内联 — 已修复

- **证据**: `sse_parser.py:73-74` 新增 `_INVALID_JSON_CODE = "sse_invalid_json"` 和 `_PAYLOAD_NOT_OBJECT_CODE = "sse_payload_not_object"`。
- **验证**: grep 确认生产代码中无残留内联字符串字面量；`_dispatch_event_payload` 中两处引用已替换为常量。
- **测试**: `test_sse_invalid_json_emits_protocol_error` 断言 `error_code == "sse_invalid_json"`。

### DS-4 [low] invalid UTF-8 common digest/size 语义不清 — 已修复

- **证据**: `diagnostic_payload.py:130-133` 改为 `canonical=(len(chunk), chunk_digest)`，直接使用 raw chunk bytes 长度和 SHA-256。
- **验证**: `_base_diagnostic_payload` docstring 已更新（line 171-172）说明 canonical 含义因路径而异。`test_invalid_utf8_diagnostic_payload_is_bounded` 断言 `canonical_byte_size == len(chunk)` 和 `sha256_digest == hashlib.sha256(chunk).hexdigest()`，与 `chunk_byte_size` / `chunk_sha256_digest` 专用字段一致。

### DS-5 [low] large provider error integration fallback 未断言 minimal structure — 已修复

- **证据**: `test_protocol_error.py:277-278` 新增 `assert _PREVIEW_FIELD not in diagnostic` 和 `assert _TOP_LEVEL_KEYS_FIELD not in diagnostic`。
- **验证**: `test_non_stream_large_provider_error_raw_payload_is_bounded` 现在同时断言 size 合规和 minimal structure 字段移除。

## Open Questions

无。

## Residual Risk

无新增。现有 out-of-scope residual risk 不变：HTTP JSON error body raw payload 属于 Slice 2。

## Pass / Fail 结论

**PASS**。6 个 controller-accepted findings 全部已修复，证据充分。35 tests passed, pyright 0 errors。建议 accepted slice commit。
