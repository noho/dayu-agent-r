# Code Review

## Scope

- Mode: current changes (handoff review, uncommitted Slice 1 implementation diff)
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: HEAD (accepted plan checkpoint `e55f05e`)
- Output file: `docs/reviews/wu-engine-01-slice1-code-review-mimo-20260602.md`
- Included scope:
  - `dayu/engine/runners/openai/diagnostic_payload.py` (new)
  - `dayu/engine/runners/openai/non_stream_parser.py` (diff)
  - `dayu/engine/runners/openai/sse_parser.py` (diff)
  - `dayu/engine/contracts/runner_events.py` (docstring diff)
  - `dayu/engine/contracts/engine_events.py` (docstring diff)
  - `tests/engine/runners/openai/test_diagnostic_payload.py` (new)
  - `tests/engine/runners/openai/test_protocol_error.py` (diff)
  - `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py` (diff)
- Excluded scope: `runner.py` HTTP error body (Slice 2), Host ingest, EventLog schema, provider state union
- Parallel review coverage: 无

## Findings

未发现 blocking / high / medium 级别问题。

### 1-未修复-低-diagnostic_payload helper test 未覆盖 `final_decode=True` 路径

- **入口/函数**: `invalid_utf8_diagnostic_payload`
- **文件(行号)**: `tests/engine/runners/openai/test_diagnostic_payload.py:185-198`
- **输入场景**: `final_decode=True`（流尾 flush 失败，chunk 为空字节串）
- **实际分支**: helper 测试只覆盖 `final_decode=False`
- **预期行为**: helper 单元测试直接覆盖两个 `final_decode` 分支
- **实际行为**: `final_decode=True` 路径仅由 `test_protocol_error.py:test_sse_incomplete_utf8_tail_reports_truncated_tail` 在 parser 层间接覆盖
- **直接证据**: `test_invalid_utf8_diagnostic_payload_is_bounded` 只传 `final_decode=False`
- **影响**: helper 自身的 `final_decode=True` 分支（空 chunk、`canonical_subject` 只含 `chunk_byte_size=0` + `final_decode=True`）缺少直接单元覆盖；parser 层测试已间接覆盖，风险低
- **建议改法和验证点**: 在 `test_diagnostic_payload.py` 增加一个 `test_invalid_utf8_diagnostic_payload_final_decode` 用例，传 `chunk=b""`, `final_decode=True`，断言 `diagnostic["final_decode"] is True`、`diagnostic["chunk_byte_size"] == 0`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Residual Risk

- `runner.py` HTTP JSON error body `raw_payload` 仍为 exact JSON object（Slice 2 范围），不在本 slice 审查范围。
- Host ingest artifact 行为和 EventLog schema 未触及；本 slice 依赖现有 opaque `JsonValue` diagnostic 处理。
- helper tests 通过 import private 常量（`_DIAGNOSTIC_PAYLOAD_MAX_BYTES` 等）验证边界；若常量重命名需同步更新测试，但这是 Python 测试的常见模式，风险低。
- `provider_error_diagnostic_payload` 对 `error` 子对象中同时包含敏感 key（如 `api_key`）和低风险 key（如 `code`）的场景：低风险 key 正常提取，敏感 key 不在 `_PROVIDER_ERROR_SUMMARY_FIELDS` 中故不进入 summary。当前测试未构造此混合场景，但设计上安全——summary 只提取 `(code, type, param)`。

## Pass / Fail 结论

**PASS**。Slice 1 实现完全符合 approved plan：

1. `raw_payload=dict(parsed)` 已全部替换为 bounded diagnostic payload helper 调用。
2. `diagnostic_payload.py` helper 有界、脱敏、摘要化；不保存完整 provider payload、不泄漏 secret 值；fallback 顺序固定且无无限循环风险。
3. `sse_parser.py` 中 `base64` import 已移除；魔法字符串已提升为模块级私有常量。
4. `non_stream_parser.py` 中 `invalid_utf8` 魔法字符串已提升为 `_INVALID_UTF8_CODE`。
5. `RunnerProtocolErrorData` 与 `ProviderProtocolErrorData` docstring 已同步更新。
6. 测试覆盖 redaction、大 payload fallback、canonical byte size/digest、stream/non-stream provider error object parity。
7. 未引入 `Any`/`object`/`getattr`/`hasattr`/extra payload/compat facade。
8. 未超出 Slice 1 scope（未触及 `runner.py` HTTP body）。
9. pyright 0 errors、33 tests passed。
