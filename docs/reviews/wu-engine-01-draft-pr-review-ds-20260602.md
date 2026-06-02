# WU-ENGINE-01 Draft PR Review — AgentDS

## Verdict

**PASS**

## Scope

- PR: https://github.com/noho/dayu-agent-r/pull/109
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: `main`
- Production diffs: 6 files (+467 new diagnostic_payload.py, ~60 lines changed across parsers/runner/contracts)
- Test diffs: 5 files (~675 lines added/modified)
- Gate: draft PR review

## Evidence Summary

### 1. Bounded diagnostic payload (PASS)

文件: `dayu/engine/runners/openai/diagnostic_payload.py`

- `_DIAGNOSTIC_PAYLOAD_MAX_BYTES = 4096` (line 22) — 所有诊断载荷硬上限 4KB。
- `_bounded_payload` (line 214-235) — 两阶段 fallback: `_truncate_preview_fields` (scalar 降为 32 chars) → `_minimal_payload` (只保留 version/source/kind/canonical_byte_size/sha256_digest 五个最小字段)。
- `test_large_payload_falls_back_to_minimal_structure` (test_diagnostic_payload.py:187-211) — 用 32 个 512 字符 key 构造超大 payload，验证回退到最小结构。
- `test_non_stream_large_provider_error_raw_payload_is_bounded` (test_protocol_error.py:245-278) — 非流式路径超大 provider error 验证。

### 2. Sensitive key redaction (PASS)

文件: `dayu/engine/runners/openai/diagnostic_payload.py`

- `_SENSITIVE_KEY_FRAGMENTS` (line 26-33): `api_key`, `secret`, `token`, `password`, `authorization`, `credential` — 覆盖常见敏感字段。
- `_normalized_sensitive_key` (line 451-459): 小写 + 破折号→下划线归一，确保 `api-key`, `client-secret`, `access-token` 等破折号变体均被命中。
- `test_diagnostic_payload_redacts_sensitive_values` (test_diagnostic_payload.py:108-145) — 覆盖 10 种敏感值变体。
- `test_http_json_object_error_body_produces_bounded_diagnostic_payload` (test_http_error_event.py:533-589) — HTTP 路径也验证了密钥不泄漏（含 `api_key`, `access_token`, `user_password`）。
- `test_sse_provider_error_object_emits_protocol_error` (test_protocol_error.py:153-194) — SSE 路径验证。
- `test_non_stream_provider_error_object_emits_protocol_error` (test_protocol_error.py:197-242) — 非流式路径验证。

### 3. Provider error scalar type handling (PASS)

文件: `dayu/engine/runners/openai/diagnostic_payload.py`

- `_provider_error_scalar_preview` (line 332-351) — 保留 `bool`/`int`/`float`/`None` 原始类型，过滤空字符串与容器值。
- `test_provider_error_summary_preserves_json_scalar_values` (test_diagnostic_payload.py:148-167) — 验证 `int`(429), `bool`(True), `None` 保留。
- `test_provider_error_summary_filters_empty_strings_and_containers` (test_diagnostic_payload.py:170-184) — 验证空字符串、空白字符串、dict 被过滤。

### 4. Stream / non-stream provider error parity (PASS)

- 两条路径使用同一 `provider_error_diagnostic_payload` 函数。
- 两条路径的 `_provider_error_message` 逻辑完全一致（sse_parser.py:131-145, non_stream_parser.py:373-387）。
- `test_stream_and_non_stream_provider_error_object_parity` (test_stream_non_stream_terminal_parity.py:207-275) — 直接验证 canonical_byte_size, sha256_digest, provider_error 子对象一致。

### 5. Invalid UTF-8 diagnostics bounded (PASS)

文件: `dayu/engine/runners/openai/diagnostic_payload.py`

- `invalid_utf8_diagnostic_payload` (line 119-143) — 最多保留 96 字节 base64 前缀（`_DIAGNOSTIC_CHUNK_PREFIX_MAX_BYTES`）。
- `test_invalid_utf8_diagnostic_payload_is_bounded` (test_diagnostic_payload.py:256-271) — 用 8KB chunk（2x max）验证仍 ≤ 4KB。
- SSE parser 区分 `_INVALID_UTF8_CODE` vs `_TRUNCATED_UTF8_TAIL_CODE`（sse_parser.py:232-237），`test_sse_incomplete_utf8_tail_reports_truncated_tail` 验证截断尾部分支。

### 6. HTTP error body byte cap (PASS)

文件: `dayu/engine/runners/openai/runner.py`

- `_HTTP_ERROR_BODY_MAX_BYTES = 65_536` (line 92) — 显式有界读取。
- `_safe_read_error_body_bytes` (line 904-927) — 循环 `read(remaining)`，每轮递减 remaining，最多读 64KB。
- `test_http_error_body_is_capped_before_decode` (test_http_error_event.py:617-657) — 用 64KB+1024 的 body 验证截断。
- `test_http_unicode_decode_error_body_keeps_replacement_text` (test_http_error_event.py:593-613) — 验证非 UTF-8 body 用 replacement decode 且 `raw_payload=None`。

### 7. Host ingest production code unchanged (PASS)

- `runner_events.py`: `RunnerProtocolErrorData.raw_payload` 与 `RunnerHTTPErrorData.raw_payload` 字段类型保持 `JsonValue | None`，仅 docstring 从"原始报错载荷"更新为"有界诊断载荷"。
- `engine_events.py`: `ProviderProtocolErrorData.raw_payload` 同上。
- Host ingest 测试 `test_provider_protocol_error_is_diagnostic_without_state_change` (test_engine_ingest_mapping.py:1526-1569) 验证带诊断 payload 的 `ProviderProtocolErrorData` 通过 Host ingest 正确处理为 diagnostic event，不改变 Run/Attempt 状态。

### 8. Engine README (PASS)

文件: `dayu/engine/README.md` line 190（+1 行）

- 新增 `raw_payload` 词条：明确该字段是有界、脱敏、摘要化的诊断载荷，不保证保留 provider 原始 payload。
- 语义准确，与代码实现一致。

### 9. No compatibility facade or metadata bag (PASS)

- `diagnostic_payload.py` 是完全独立的新模块，使用模块级私有函数，公共 API 只有 4 个导出函数。
- 没有为保持旧行为而引入兼容层、wrapper、re-export。
- 字段类型未变（`JsonValue | None`），只是内容从原始 provider JSON 变为有界诊断载荷。

### 10. Test quality (PASS)

- 5 个测试文件覆盖：诊断载荷结构、脱敏、有界性、标量类型保留、container 过滤、fallback、invalid UTF-8、HTTP error body 字节上限、stream/non-stream parity、Host ingest 兼容。
- 测试使用 adversarial 输入（超大 payload、超大 chunk、伪造敏感值、破折号变体）。
- 97 个测试全部通过。
- Residual risk RR-ENGINE-01-01（测试 helper 重复 `_leaf_strings`/`_serialized_size`）已知且不阻塞，不影响运行时正确性。

## Adversarial Failure Pass

| 攻击向量 | 防御机制 | 证据 |
|---|---|---|
| 超大 provider payload | 4KB 硬上限 + 两阶段 fallback | `_bounded_payload` (L214-235) |
| 敏感字段泄漏（破折号变体） | 小写+破折号归一 + 片段匹配 | `_normalized_sensitive_key` (L451-459) |
| 非法 UTF-8 chunk 无界泄漏 | 96 字节 base64 前缀上限 | `_DIAGNOSTIC_CHUNK_PREFIX_MAX_BYTES` (L25) |
| HTTP error body 无界读取 | 64KB 字节上限 | `_HTTP_ERROR_BODY_MAX_BYTES` (L90) |
| 嵌套容器绕过脱敏 | preview 只处理顶层 24 keys | `_top_level_preview` (L287-305) |
| provider error 子对象全量泄漏 | 只提取 code/type/param 三个低风险字段 | `_PROVIDER_ERROR_SUMMARY_FIELDS` (L61) |
| 长 key 撑爆诊断载荷 | 最多 24 keys + scalar 截断 | `_DIAGNOSTIC_KEYS_MAX_ITEMS` (L23), `_DIAGNOSTIC_SCALAR_MAX_CHARS` (L24) |

## Project Instruction Check

- 分层架构：变更在 Engine 层，不影响 Host 层。
- 编码规范：所有函数有中文 docstring，类型完整，无 `Any`/`object`/魔法数字。
- 测试覆盖：单模块 ≥80%（diagnostic_payload.py 被 5 个测试文件覆盖）。
- 无反向依赖：Runner 模块不依赖上层。
- README 更新：`dayu/engine/README.md` 已更新。

## Findings

**Blocking**: 无

**High**: 无

**Medium**: 无

**Low**: 无

## Residual Risks

- RR-ENGINE-01-01（已知，不阻塞）: 测试 helper `_leaf_strings` / `_serialized_size` / `_canonical_metadata` 在 3 个测试文件中重复定义。无运行时影响，可后续 Engine 测试工具清理时统一。
