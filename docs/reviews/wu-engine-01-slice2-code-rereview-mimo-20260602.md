# Code Re-Review

## Scope

- Mode: re-review (controller adjudication + fix artifact verification)
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: HEAD (Slice 1 accepted checkpoint)
- Output file: `docs/reviews/wu-engine-01-slice2-code-rereview-mimo-20260602.md`
- Original review: `docs/reviews/wu-engine-01-slice2-code-review-mimo-20260602.md`
- Fix artifact: `docs/reviews/wu-engine-01-slice2-fix-codex-20260602.md`
- Controller adjudication: `docs/reviews/wu-engine-01-slice2-code-review-controller-adjudication-20260602.md`
- Included scope: 仅复核 controller accepted findings 的修复状态与 rejected finding 未被误改
- Excluded scope: 不重新扩大范围

## Per-finding Re-review

### DS-1 (accepted) — `_HTTPErrorBody.raw_payload` 私有文档仍承诺原始载荷

- **Controller decision**: accepted, severity medium
- **Required fix**: 更新 `_HTTPErrorBody.raw_payload` docstring，说明它是从有界 HTTP body 派生的有界诊断载荷；解析失败或非 JSON object 时为 `None`
- **Re-review verdict**: **已修复**
- **直接证据**: `dayu/engine/runners/openai/runner.py:97-99` — docstring 从 `"当 body 是 JSON object 时保留的原始载荷"` 改为 `"从有界 HTTP body 派生的有界诊断载荷；解析失败或非 JSON object 时为 ``None``。"` 与 `_safe_read_error_body` 方法 docstring（行 884-888）语义一致

### MIMO-002 (accepted) — context overflow HTTP JSON path 缺少 raw_payload 诊断断言

- **Controller decision**: accepted, severity low
- **Required fix**: 在 `test_http_context_overflow_maps_to_context_length_exceeded` 中断言 `raw_payload` 是 bounded diagnostic payload，包含 `context_length_exceeded` 与对应 provider error type
- **Re-review verdict**: **已修复**
- **直接证据**:
  - `tests/engine/runners/openai/test_http_error_event.py:669-671` — 测试 body 增加了 `"type":"invalid_request_error"` 字段
  - `tests/engine/runners/openai/test_http_error_event.py:687-691` — 新增 `_assert_http_diagnostic_payload(events[-2].data.raw_payload, expected_error_code=_HTTP_CONTEXT_CODE, expected_error_type=_HTTP_ERROR_TYPE)` 断言
  - `_HTTP_CONTEXT_CODE` 定义为 `"context_length_exceeded"`（行 56），`_HTTP_ERROR_TYPE` 定义为 `"invalid_request_error"`（行 55）

### MIMO-001 (rejected) — 测试导入 diagnostic_payload 私有常量

- **Controller decision**: rejected,保留现状
- **Re-review verdict**: **未被误改**
- **直接证据**: `tests/engine/runners/openai/test_http_error_event.py:38-43` — 导入仍为 `_CANONICAL_BYTE_SIZE_FIELD`、`_DIAGNOSTIC_PAYLOAD_MAX_BYTES`、`_PROVIDER_ERROR_FIELD`、`_SHA256_DIGEST_FIELD`，与原始实现一致

## Validation

| Check | Result |
|---|---|
| `pytest tests/engine/runners/openai/test_http_error_event.py tests/host/test_engine_ingest_mapping.py` | 60 passed in 0.53s |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| Changed files vs original implementation | +2 lines in runner.py (docstring), +8 lines in test_http_error_event.py (context overflow body + assertion) |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

无。
