# Code Review

## Scope

- Mode: current changes (handoff-only, no commit/push/PR)
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: HEAD (Slice 1 accepted checkpoint)
- Output file: `docs/reviews/wu-engine-01-slice2-code-review-mimo-20260602.md`
- Included scope: Slice 2 implementation diff against HEAD
- Excluded scope: Host production, Host state machine, EventLog schema, controller status doc unless conflicting with gate truth
- Parallel review coverage: 无

## Review Target Files

- `dayu/engine/runners/openai/diagnostic_payload.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/engine/contracts/runner_events.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `tests/host/test_engine_ingest_mapping.py`
- `dayu/engine/README.md`

## Findings

### 001-unresolved-low-测试导入私有模块成员

- **入口/函数**: `test_http_error_event.py` 顶层导入
- **文件(行号)**: `tests/engine/runners/openai/test_http_error_event.py:38-43`
- **输入场景**: 测试模块加载时
- **实际分支**: 导入 `_CANONICAL_BYTE_SIZE_FIELD`、`_DIAGNOSTIC_PAYLOAD_MAX_BYTES`、`_PROVIDER_ERROR_FIELD`、`_SHA256_DIGEST_FIELD`
- **预期行为**: 测试只依赖公共 API；若需要断言内部字段名，应通过 public API 间接验证或在测试内重新定义常量
- **实际行为**: 直接导入 `diagnostic_payload` 模块的 `_` 前缀私有成员
- **直接证据**: `__all__` 只包含 4 个 public 函数，不包含这 4 个常量；常量名以 `_` 前缀表明模块级私有
- **影响**: 测试与实现细节耦合；常量重命名时测试会编译失败，但这不是 runtime correctness 问题
- **建议改法和验证点**: 若改为 magic string，违反 AGENTS.md 禁止魔法字符串约束；若 re-export 为 public，不必要扩大 API surface。当前做法是 pragmatic trade-off，可接受，但应意识到耦合
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-unresolved-low-context_overflow 测试未断言 raw_payload 诊断结构

- **入口/函数**: `test_http_context_overflow_maps_to_context_length_exceeded`
- **文件(行号)**: `tests/engine/runners/openai/test_http_error_event.py:661-692`
- **输入场景**: context_length_exceeded JSON body
- **实际分支**: body 解析为 dict，进入 `http_error_diagnostic_payload` 路径
- **预期行为**: 测试断言 `raw_payload` 是有界诊断载荷，包含 `canonical_byte_size`、`sha256_digest`、`provider_error.code`
- **实际行为**: 测试只断言 `provider_request_id` 和 `error_code`，不断言 `raw_payload` 诊断结构
- **直接证据**: 行 687-691 只检查 `provider_request_id == "req_context"` 和 `finish_reason is ERROR`，未对 `raw_payload` 做任何断言
- **影响**: context overflow 路径的 diagnostic payload 结构未被测试覆盖；若该路径诊断生成出现回归，不会被此测试发现
- **建议改法和验证点**: 在行 691 后增加 `_assert_http_diagnostic_payload(events[-2].data.raw_payload, expected_error_code="context_length_exceeded", expected_error_type=...)` 断言
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Review Checklist (Specified Lens)

| Lens | Verdict | Evidence |
|---|---|---|
| 完全实现 Slice 2 | PASS | 6 个 allowed file 全部修改；plan exact changes 全部执行 |
| 不回退 Slice 1 | PASS | Slice 1 的 `provider_error_diagnostic_payload`、`protocol_object_diagnostic_payload`、`invalid_utf8_diagnostic_payload` 未被修改；SSE/non-stream parser 未被修改 |
| 不扩大到 Host production | PASS | 只改 Host test fixture，不改 `engine_ingest.py` production 代码 |
| HTTP JSON error body bounded/redacted/summarized | PASS | `http_error_diagnostic_payload` 使用 `_bounded_payload`、`_is_sensitive_key`、`_provider_error_summary`；无路径保存完整 provider JSON |
| HTTP message_text 保持 | PASS | `message_text` 仍来自 `_safe_read_error_body_bytes` 的原始 body 文本；测试 `events[-2].data.message == body_text` 断言 |
| provider_request_id 保持 | PASS | 仍从 header 提取；测试 `provider_request_id == _HEADER_REQUEST_ID` 断言 |
| retry exhausted final attempt 保持 | PASS | `test_retry_exhausted_keeps_final_attempt_provider_request_id` 断言最终 attempt 的 `provider_request_id == "req_final"` |
| `_HTTP_ERROR_BODY_MAX_BYTES` 保留 | PASS | `_safe_read_error_body_bytes` 仍使用 `remaining = _HTTP_ERROR_BODY_MAX_BYTES` |
| cap 测试有意义 | PASS | 测试构造超大 JSON body，验证截断后 `raw_payload is None`；截断 JSON 不可解析是正确的 |
| Host ingest 测试只改 fixture | PASS | 只把 `raw_payload={"raw": "payload"}` 改为 diagnostic-like JSON object；断言不变：`raw_payload_ref is not None`、`run_status == RUNNING`、`attempt_status == RUNNING` |
| Engine README 只写稳定 contract | PASS | 新增一行：`raw_payload` 是有界、脱敏、摘要化诊断载荷；无实现细节/过程状态/未来计划 |
| runner.py docstring 不误导 | PASS | `_safe_read_error_body` docstring 改为"派生 JSON object 诊断载荷"；returns 说明改为"可选有界诊断载荷" |
| 无 `Any`/`object`/无类型 | PASS | 所有函数签名有完整类型标注 |
| 无 `getattr`/`hasattr` | PASS | 未使用 |
| 无 extra payload | PASS | 所有参数显式传递 |
| 无 compat facade | PASS | 未引入兼容性 wrapper/re-export |
| 无魔法字符串 | PASS | `_HTTP_ERROR_SOURCE`、`_HTTP_ERROR_KIND` 为模块级常量 |
| 中文 docstring | PASS | `http_error_diagnostic_payload` 有完整中文 docstring 含参数/返回值/异常 |

## Open Questions

无。

## Residual Risk

- `test_http_context_overflow_maps_to_context_length_exceeded` 未断言 `raw_payload` 诊断结构，是唯一一个通过 HTTP JSON body 路径但未验证诊断载荷形状的测试。风险低，因同一 `http_error_diagnostic_payload` 在其他测试中已覆盖。
- 测试导入私有常量与实现细节耦合，但不违反 correctness。

## Conclusion

**PASS**。无 blocking/high/medium finding。发现 2 个 low severity finding：测试导入私有成员的耦合问题、context overflow 路径缺少诊断载荷断言。两者均为 maintainability 级别，不阻塞 accepted slice commit。

Slice 2 实现完全符合 approved plan scope：HTTP JSON error body 不再保存完整 provider JSON，只生成 bounded/redacted/summarized diagnostic payload；Slice 1 未回退；Host production 未改动；`_HTTP_ERROR_BODY_MAX_BYTES` 行为保留；tests 60 passed、pyright 0 errors。

建议：fix 002（补充 context overflow 路径的诊断载荷断言），001 可接受后标记 accepted。
