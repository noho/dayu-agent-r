# WU-ENGINE-01 Slice 1 Code Review

## Scope

- Mode: current changes (handoff review)
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: HEAD (accepted plan checkpoint `e55f05e`)
- Output file: `docs/reviews/wu-engine-01-slice1-code-review-ds-20260602.md`
- Approved plan: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`
- Implementation artifact: `docs/reviews/wu-engine-01-slice1-implementation-codex-20260602.md`
- Included scope: Slice 1 eight files per handoff
- Excluded scope: Slice 2 HTTP runner body, Host state machine, Host ingest, EventLog schema

## Findings

### 1-未修复-中-non_stream_parser 仍有四处魔法字符串未提升为模块级常量

- **入口/函数**: `parse_non_stream_response` / `_emit_from_dict` / `_build_tool_calls` / `_coerce_final_tool_call`
- **文件(行号)**: `dayu/engine/runners/openai/non_stream_parser.py:153,172,250,267,537`
- **输入场景**: 任何触发对应非流式协议错误分支的 provider 响应
- **实际分支**: 各协议错误分支使用 `error_code="non_stream_invalid_json"` 等字符串字面量作为 `RunnerProtocolErrorData.error_code`
- **预期行为**: 按 plan §7 "该文件本 slice 已触及，按 controller preference 一并收口魔法字符串"，应将这些字面量全部提升为模块级私有常量
- **实际行为**: 仅 `_INVALID_UTF8_CODE` 被提升；`"non_stream_invalid_json"` (行 153)、`"non_stream_payload_not_object"` (行 172)、`"non_stream_missing_choices"` (行 250)、`"non_stream_choice_not_object"` (行 267)、`"tool_call_arguments_not_object"` (行 537) 仍为字符串字面量
- **直接证据**: `non_stream_parser.py:153` `error_code="non_stream_invalid_json"`，`non_stream_parser.py:172` `error_code="non_stream_payload_not_object"`，`non_stream_parser.py:250` `error_code="non_stream_missing_choices"`，`non_stream_parser.py:267` `error_code="non_stream_choice_not_object"`，`non_stream_parser.py:537` `error_code="tool_call_arguments_not_object"` — 均为内联字符串字面量，而非模块级 `_` 前缀常量
- **影响**: Host 或 Engine Agent 在做 error_code 匹配时需要硬编码字符串比较，增加拼写错误风险；违反 CLAUDE.md 魔法字符串约束
- **建议改法和验证点**: 在 `non_stream_parser.py` 模块顶部新增 `_NON_STREAM_INVALID_JSON_CODE`、`_NON_STREAM_PAYLOAD_NOT_OBJECT_CODE`、`_NON_STREAM_MISSING_CHOICES_CODE`、`_NON_STREAM_CHOICE_NOT_OBJECT_CODE`、`_TOOL_CALL_ARGUMENTS_NOT_OBJECT_CODE` 常量，并将所有引用点替换为常量；运行 `pytest -q tests/engine/runners/openai/test_protocol_error.py` 与 `pyright` 验证
- **修复风险（低）**: 纯重命名，不改变 error_code 字符串值，不改变事件语义
- **严重程度（中）**: 违反 plan 明确指令与 CLAUDE.md 魔法字符串约束

### 2-未修复-中-protocol_object_diagnostic_payload 路径缺少敏感字段脱敏测试覆盖

- **入口/函数**: `protocol_object_diagnostic_payload` → `_top_level_preview` → `_is_sensitive_key`
- **文件(行号)**: `tests/engine/runners/openai/test_protocol_error.py:278-299` (`test_sse_missing_choices_without_usage_emits_protocol_error`)；`tests/engine/runners/openai/test_diagnostic_payload.py:167-182` (`test_protocol_object_diagnostic_payload_records_reason`)
- **输入场景**: SSE chunk 的顶层 JSON object 包含敏感字段（如 `api_key`）但 choices/usage 均无效 → 走 `protocol_object_diagnostic_payload` 路径
- **实际分支**: `_top_level_preview` 确实会对敏感 key 返回 `<redacted>`，但两个测试均未构造含敏感字段的输入
- **预期行为**: plan §7 要求 "redaction 使用包含敏感字段的输入，至少覆盖 `api_key`、`secret`、`token`、`password`、`authorization`、`credential` 中的多个片段" — `provider_error_diagnostic_payload` 路径已有覆盖，但 `protocol_object_diagnostic_payload` 路径无覆盖
- **实际行为**: `test_protocol_object_diagnostic_payload_records_reason` 使用 `{"id": "chunk_1", "choices": []}`，`test_sse_missing_choices_without_usage_emits_protocol_error` 使用 `{"id":"chunk-without-choices"}` — 均不含敏感字段
- **直接证据**: `test_diagnostic_payload.py:170` `payload: dict[str, JsonValue] = {"id": "chunk_1", "choices": []}`；`test_protocol_error.py:282` `_sse_json_chunk('{"id":"chunk-without-choices"}')`
- **影响**: 若 `_top_level_preview` 脱敏逻辑有缺陷，现有测试不会捕获；`protocol_object_diagnostic_payload` 与 `provider_error_diagnostic_payload` 共享脱敏代码但测试未覆盖此路径
- **建议改法和验证点**: 在 `test_sse_missing_choices_without_usage_emits_protocol_error` 的输入 JSON 中加入 `"api_key": "secret-val"` 字段，断言 `"secret-val"` 不在 diagnostic 叶子字符串中；或在 `test_diagnostic_payload.py` 新增 `test_protocol_object_diagnostic_payload_redacts_sensitive_values`
- **修复风险（低）**: 仅添加测试用例
- **严重程度（中）**: test coverage gap — plan 明确要求 sensitive field redaction 覆盖，`protocol_object_diagnostic_payload` 路径生产代码已实现脱敏但测试未覆盖

### 3-未修复-低-sse_parser 中仍有两处魔法字符串未随文件修改提升

- **入口/函数**: `SSEParser._dispatch_event_payload`
- **文件(行号)**: `dayu/engine/runners/openai/sse_parser.py:297,315`
- **输入场景**: SSE 行 JSON 解析失败或顶层非 object
- **实际分支**: 协议错误分支 `error_code="sse_invalid_json"` 与 `error_code="sse_payload_not_object"`
- **预期行为**: 与 `non_stream_parser.py` 同类错误码保持一致性，使用模块级常量
- **实际行为**: `sse_parser.py:297` `error_code="sse_invalid_json"`、`sse_parser.py:315` `error_code="sse_payload_not_object"` 仍为字符串字面量；同文件内 `_PROVIDER_ERROR_CODE`、`_MISSING_CHOICES_CODE`、`_INVALID_UTF8_CODE` 等常量已存在，但这两处未统一
- **直接证据**: `sse_parser.py:297` `error_code="sse_invalid_json"`，`sse_parser.py:315` `error_code="sse_payload_not_object"`
- **影响**: 低影响 — plan 对 sse_parser 的常量提升要求比 non_stream_parser 窄，但一致性问题存在
- **建议改法和验证点**: 新增 `_SSE_INVALID_JSON_CODE = "sse_invalid_json"` 与 `_SSE_PAYLOAD_NOT_OBJECT_CODE = "sse_payload_not_object"`，替换两处引用
- **修复风险（低）**: 纯重命名
- **严重程度（低）**: 未违反 plan 明确指令，但降低了同文件常量一致性

### 4-未修复-低-invalid_utf8_diagnostic_payload 的 canonical 字段语义与其它路径不一致

- **入口/函数**: `invalid_utf8_diagnostic_payload` → `_canonical_payload_metadata`
- **文件(行号)**: `dayu/engine/runners/openai/diagnostic_payload.py:129-146`
- **输入场景**: SSE 流中收到非法 UTF-8 字节
- **实际分支**: `invalid_utf8_diagnostic_payload` 构造 `canonical_subject = {"chunk_byte_size": len(chunk), "chunk_sha256_digest": ..., "final_decode": bool}`，再将其传给 `_canonical_payload_metadata`
- **预期行为**: `canonical_byte_size` / `sha256_digest` 应反映被诊断的原始对象。对 provider error / protocol object，canonical 字段反映原始 provider JSON；对 invalid UTF-8，原始对象是 raw bytes 而非 JSON object，但 current 实现用 metadata dict 的 canonical JSON 替代，严格来说不是同一语义
- **实际行为**: `diagnostic["canonical_byte_size"]` = metadata dict（含 chunk_byte_size / chunk_sha256_digest / final_decode）的 JSON 序列化大小（约 150 bytes），而非原始 chunk 大小（后者已在 `chunk_byte_size` 字段）；`diagnostic["sha256_digest"]` = metadata dict 的 SHA-256，而非原始 chunk 的 SHA-256（后者已在 `chunk_sha256_digest` 字段）
- **直接证据**: `diagnostic_payload.py:130-135` `canonical_subject` 构造与 `diagnostic_payload.py:136-140` `_canonical_payload_metadata(canonical_subject)` 调用
- **影响**: 不影响功能正确性 — chunk 的真实 byte size 与 SHA-256 已通过专用字段 `chunk_byte_size` 和 `chunk_sha256_digest` 保留；但 `canonical_byte_size` / `sha256_digest` 在此路径的语义与其它路径不同，可能使下游统一消费端误判
- **建议改法和验证点**: 可考虑对 invalid UTF-8 路径将 `canonical_byte_size` 设为 `len(chunk)`、`sha256_digest` 设为 `hashlib.sha256(chunk).hexdigest()`，以与其它路径保持一致语义（均反映原始被诊断对象的 canonical size/digest）；或在 diagnostic 文档中明确记录此差异
- **修复风险（低）**: 改动仅影响 invalid UTF-8 诊断载荷的两个字段值，不影响结构化字段
- **严重程度（低）**: 语义不一致，但功能字段已独立存在

### 5-未修复-低-test_non_stream_large_provider_error 未验证 fallback 确切到达 minimal structure

- **入口/函数**: `test_non_stream_large_provider_error_raw_payload_is_bounded`
- **文件(行号)**: `tests/engine/runners/openai/test_protocol_error.py:243-275`
- **输入场景**: 超大 provider error JSON 响应
- **实际分支**: `_bounded_payload` 的 fallback 路径
- **预期行为**: plan §6.12 要求 fallback 到 minimal structure（仅 version / source / kind / canonical_byte_size / sha256_digest）
- **实际行为**: 测试只断言 `_serialized_size(diagnostic) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES`、`source`、`kind` 存在，未验证 `_TOP_LEVEL_KEYS_FIELD` 与 `_PREVIEW_FIELD` 确已删除（如 `test_large_payload_falls_back_to_minimal_structure` 所做）
- **直接证据**: `test_protocol_error.py:272` 仅检查 `<= _DIAGNOSTIC_PAYLOAD_MAX_BYTES` 边界，未检查 `_TOP_LEVEL_KEYS_FIELD not in diagnostic`
- **影响**: 若 fallback 仅截断未完全移除 preview/keys（但仍巧合在 4096 内），测试不会发现
- **建议改法和验证点**: 增加 `assert _TOP_LEVEL_KEYS_FIELD not in diagnostic` 和 `assert _PREVIEW_FIELD not in diagnostic`
- **修复风险（低）**: 纯增加断言
- **严重程度（低）**: 同逻辑已在 unit test `test_large_payload_falls_back_to_minimal_structure` 中覆盖，此为集成路径补充

## Open Questions

- 无。

## Residual Risk

- Slice 2（HTTP error body 摘要化）未涵盖在当前 review scope 中，`RunnerHTTPErrorData.raw_payload` 当前仍可保留完整 provider JSON object（通过 `runner.py` 的 HTTP error body 读取路径）。Controller 在 Slice 2 review 时需独立验证该路径的有界化。
- Host ingest 映射测试 (`tests/host/test_engine_ingest_mapping.py`) 未在本 slice 中更新 — controller 在 Slice 2 需确认 Host 消费侧不依赖 `raw_payload` 的精确形状。
- 5 个 `__init__.py` 的 re-export surface 未检查 — 若已有 `from dayu.engine.runners.openai import provider_error_diagnostic_payload` 的公开导出，可能意外暴露内部 helper。建议 controller 在 Slice 3 验证 engines 的 `__init__.py` 导出面。

## Conclusion

Slice 1 实现基本完整地完成了 plan §7 的核心目标：`raw_payload=dict(parsed)` 路径已全部替换为 bounded diagnostic helper；helper 实现了 size cap、redaction、fallback、provider error sub-object 提取；stream/non-stream parity 测试已添加；contract docstring 已更新。pyright 0 errors，33 tests passed。

发现 2 个中等严重度 findings（魔法字符串未完整收口、protocol_object 路径脱敏测试 gap）和 3 个低严重度 findings。无 blocking 或 high severity findings。

建议: **accepted slice commit**（可在后续 slice 修复中等 findings，或立即修复后 re-review）。
