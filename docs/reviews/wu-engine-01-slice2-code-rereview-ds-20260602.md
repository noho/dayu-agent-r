# Code Re-review — WU-ENGINE-01 Slice 2

## Scope

- Mode: Slice 2 fix re-review (uncommitted diff against Slice 1 accepted checkpoint)
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: HEAD (Slice 1 accepted checkpoint)
- Output file: `docs/reviews/wu-engine-01-slice2-code-rereview-ds-20260602.md`
- Fix artifact: `docs/reviews/wu-engine-01-slice2-fix-codex-20260602.md`
- Controller adjudication: `docs/reviews/wu-engine-01-slice2-code-review-controller-adjudication-20260602.md`
- Original review artifacts: `docs/reviews/wu-engine-01-slice2-code-review-mimo-20260602.md`, `docs/reviews/wu-engine-01-slice2-code-review-ds-20260602.md`
- Included scope: 仅复核 controller accepted findings (DS-1, MIMO-002) 的修复状态，以及 controller rejected finding (MIMO-001) 是否未被误改。
- Excluded scope: Slice 1 parser files、Host production、Host state machine、EventLog schema、原 review 中未被 controller 接受的 findings。

## Controller Adjudication Summary

| ID | Severity | Decision | Required Fix |
|---|---|---|---|
| DS-1 | medium | accepted | 更新 `_HTTPErrorBody.raw_payload` docstring 为有界诊断载荷语义 |
| MIMO-002 | low | accepted | context overflow 测试断言 `raw_payload` diagnostic structure |
| MIMO-001 | low | rejected | 保留测试导入私有常量现状 |

## Findings

未发现实质性问题。

## Fix Verification

### DS-1 — `_HTTPErrorBody.raw_payload` docstring

- **文件(行号)**: `dayu/engine/runners/openai/runner.py:100-101`
- **原始状态**: `:param raw_payload: 当 body 是 JSON object 时保留的原始载荷。`
- **当前状态**: `:param raw_payload: 从有界 HTTP body 派生的有界诊断载荷；解析失败或非 JSON object 时为 ``None``。`
- **证据**: 直接阅读 `runner.py:100-101` 确认 docstring 已替换。
- **一致性检查**: 同一 diff 中 `_safe_read_error_body` 的 docstring（`runner.py:885-887`）也从"保留 JSON object 载荷"同步更新为"派生 JSON object 诊断载荷"。三处（`_HTTPErrorBody`、`_safe_read_error_body`、`RunnerHTTPErrorData`）的 `raw_payload` 语义描述现在一致。
- **结论**: **已修复**。

### MIMO-002 — context overflow test raw_payload diagnostic assertion

- **文件(行号)**: `tests/engine/runners/openai/test_http_error_event.py:669-694`（`test_http_context_overflow_maps_to_context_length_exceeded`）
- **原始状态**: 测试 body 只有 `{"error":{"code":"context_length_exceeded","message":"..."}}`，无 `type` 字段，未断言 `raw_payload` 诊断结构。
- **当前状态**:
  1. body 新增 `"type":"invalid_request_error"`（`test_http_error_event.py:673`），使 provider error sub-object 同时包含 `code` 和 `type`，满足 `_assert_http_diagnostic_payload` 的字段要求。
  2. 新增断言 `_assert_http_diagnostic_payload(events[-2].data.raw_payload, expected_error_code=_HTTP_CONTEXT_CODE, expected_error_type=_HTTP_ERROR_TYPE)`（`test_http_error_event.py:690-694`），其中 `_HTTP_CONTEXT_CODE = "context_length_exceeded"`。
  3. 保留原有 `_check_http_error_then_done` 断言（expected_code=CONTEXT_LENGTH_EXCEEDED, attempt=1, retried=False），以及 `provider_request_id` 和 `finish_reason` 断言。
- **证据**: diff 显示 body 加入 `"type":"invalid_request_error"`，并在 done 断言前插入 `_assert_http_diagnostic_payload` 调用。
- **结论**: **已修复**。context overflow 路径现在证明 `raw_payload` 通过同一 diagnostic helper，不绕过 Slice 2 语义。

### MIMO-001 — 私有常量导入未被误改

- **文件(行号)**: `tests/engine/runners/openai/test_http_error_event.py:38-43`
- **原始状态**: import `_CANONICAL_BYTE_SIZE_FIELD`, `_DIAGNOSTIC_PAYLOAD_MAX_BYTES`, `_PROVIDER_ERROR_FIELD`, `_SHA256_DIGEST_FIELD` 四个私有常量。
- **当前状态**: 四个 import 不变，`_assert_http_diagnostic_payload` 继续使用这些常量做字段名和大小断言。
- **证据**: diff 中该 import 块与原始 Slice 2 implementation 完全一致，无新增/删除。
- **结论**: **未修改**，符合 controller rejected 裁决。

## Open Questions

无。

## Residual Risk

- 无新增 residual risk。Fix pass 仅涉及 docstring 修正与测试断言补强，未改变任何生产行为路径。

## Conclusion

**PASS** — controller accepted findings 全部修复，rejected finding 未被误改，无新 blocker。

- DS-1 (medium): fixed — `_HTTPErrorBody.raw_payload` docstring 已改为 bounded diagnostic payload 语义，与同文件 `_safe_read_error_body` 和 `RunnerHTTPErrorData` docstring 一致。
- MIMO-002 (low): fixed — context overflow test 已断言 `raw_payload` 为 bounded diagnostic payload，`code=context_length_exceeded`，`type=invalid_request_error`。
- MIMO-001 (rejected): undisturbed — private constants import 保留。

建议: **accepted slice commit**。
