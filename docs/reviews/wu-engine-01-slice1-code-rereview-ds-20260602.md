# WU-ENGINE-01 Slice 1 Code Re-Review

## Scope

- Mode: current changes (handoff re-review)
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: HEAD (post-fix workspace)
- Original review: `docs/reviews/wu-engine-01-slice1-code-review-ds-20260602.md`
- Fix artifact: `docs/reviews/wu-engine-01-slice1-fix-codex-20260602.md`
- Controller adjudication: `docs/reviews/wu-engine-01-slice1-code-review-controller-adjudication-20260602.md`
- Output file: `docs/reviews/wu-engine-01-slice1-code-rereview-ds-20260602.md`
- Reviewed scope: six controller-accepted findings only (DS-1 through DS-5, plus MIMO-1)
- Excluded scope: Slice 2 HTTP runner body, existing non-finding code paths

## Findings

### Per-Finding Verification

#### DS-1 [中] non_stream magic strings — FIXED

- **文件**: `dayu/engine/runners/openai/non_stream_parser.py`
- **证据**: 新增模块级常量 `_INVALID_JSON_CODE` (行 67)、`_PAYLOAD_NOT_OBJECT_CODE` (行 68)、`_MISSING_CHOICES_CODE` (行 69)、`_CHOICE_NOT_OBJECT_CODE` (行 70)、`_TOOL_CALL_ARGUMENTS_NOT_OBJECT_CODE` (行 74)；所有引用点已替换：行 158 `_INVALID_JSON_CODE`、行 178 `_PAYLOAD_NOT_OBJECT_CODE`、行 256 `_MISSING_CHOICES_CODE`、行 273 `_CHOICE_NOT_OBJECT_CODE`、行 543 `_TOOL_CALL_ARGUMENTS_NOT_OBJECT_CODE`。
- **验证**: 原 5 处字符串字面量全部替换为模块级常量；字符串值未变，语义不变。✅

#### DS-2 [中] protocol_object redaction test — FIXED

- **文件**: `tests/engine/runners/openai/test_diagnostic_payload.py`
- **证据**: 新增 `test_protocol_object_diagnostic_payload_redacts_sensitive_values` (行 185-206)，构造含 `"authorization": "Bearer protocol-secret"`（顶层敏感字段）与 `"metadata": {"token": "nested-token-value"}`（嵌套敏感值）的输入，通过 `_leaf_strings` 递归遍历断言两处敏感值均未出现于 diagnostic。
- **验证**: `protocol_object_diagnostic_payload` 路径的脱敏逻辑已有直接测试覆盖。✅

#### MIMO-1 [低] invalid_utf8 final_decode=True test — FIXED

- **文件**: `tests/engine/runners/openai/test_diagnostic_payload.py`
- **证据**: 新增 `test_invalid_utf8_diagnostic_payload_final_decode_empty_chunk` (行 227-241)，构造 `chunk=b""` 与 `final_decode=True`，断言 `canonical_byte_size==0`、`sha256_digest` 匹配空 SHA-256、`chunk_byte_size==0`、`chunk_prefix_base64==""`、`final_decode is True`。
- **验证**: `final_decode=True` 独立分支有直接单测覆盖，不依赖 parser 间接路径。✅

#### DS-3 [低] SSE magic strings — FIXED

- **文件**: `dayu/engine/runners/openai/sse_parser.py`
- **证据**: 新增模块级常量 `_INVALID_JSON_CODE` (行 73) 与 `_PAYLOAD_NOT_OBJECT_CODE` (行 74)；引用点已替换：行 300 `_INVALID_JSON_CODE`、行 318 `_PAYLOAD_NOT_OBJECT_CODE`。
- **验证**: `sse_parser.py` 内所有协议错误码已统一为模块级常量。✅

#### DS-4 [低] invalid_utf8 common digest/size raw bytes semantics — FIXED

- **文件**: `dayu/engine/runners/openai/diagnostic_payload.py`
- **证据**: `invalid_utf8_diagnostic_payload` (行 130-133) 将 `canonical` 从 metadata dict 的 canonical JSON 改为 `(len(chunk), hashlib.sha256(chunk).hexdigest())` — 即 raw chunk bytes 的长度与 SHA-256。`_base_diagnostic_payload` 的 docstring (行 171-172) 已更新说明双路径语义："JSON object 路径使用 canonical JSON bytes，非法 UTF-8 路径使用 raw chunk bytes"。对应测试 (行 218-223) 断言 `canonical_byte_size == len(chunk)`、`sha256_digest == hashlib.sha256(chunk).hexdigest()`。
- **验证**: `canonical_byte_size` / `sha256_digest` 现在在所有路径中都代表被诊断原始对象的 size/digest（JSON object 路径 = canonical JSON；UTF-8 路径 = raw bytes）。✅

#### DS-5 [低] large provider fallback minimal assertions — FIXED

- **文件**: `tests/engine/runners/openai/test_protocol_error.py`
- **证据**: `test_non_stream_large_provider_error_raw_payload_is_bounded` (行 277-278) 新增 `assert _PREVIEW_FIELD not in diagnostic` 与 `assert _TOP_LEVEL_KEYS_FIELD not in diagnostic`。导入已补 `_PREVIEW_FIELD` 与 `_TOP_LEVEL_KEYS_FIELD` (行 29-31)。
- **验证**: 集成路径的 fallback 测试现在直接证明到达 minimal structure，不再仅依赖 size bound。✅

## Open Questions

- 无。

## Residual Risk

- 无新增风险。fix 范围严格限定于 controller-accepted findings，未触及 Slice 1 外任何文件。
- 原有 out-of-scope residual risk（Slice 2 HTTP error body、Host ingest 映射测试）不变。

## Conclusion

PASS — 6 项 controller-accepted findings 全部修复验证通过，无新增 blocker。剩余的 magic strings 全部提升为模块级常量；protocol_object 脱敏测试已补；invalid_utf8 final_decode=True 单测已补；SSE magic strings 已统一；invalid_utf8 canonical 字段语义已修正为 raw bytes；large provider fallback 已断言 minimal structure。

建议: **accepted slice commit**，可进入 Slice 2（HTTP error body 摘要化）。
