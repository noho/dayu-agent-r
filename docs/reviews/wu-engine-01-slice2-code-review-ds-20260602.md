# Code Review — WU-ENGINE-01 Slice 2

## Scope

- Mode: Slice 2 code review (uncommitted diff against Slice 1 accepted checkpoint)
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: HEAD (Slice 1 accepted checkpoint)
- Output file: `docs/reviews/wu-engine-01-slice2-code-review-ds-20260602.md`
- Approved plan: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`
- Implementation artifact: `docs/reviews/wu-engine-01-slice2-implementation-codex-20260602.md`
- Included scope: `dayu/engine/runners/openai/diagnostic_payload.py`, `dayu/engine/runners/openai/runner.py`, `dayu/engine/contracts/runner_events.py`, `tests/engine/runners/openai/test_http_error_event.py`, `tests/host/test_engine_ingest_mapping.py`, `dayu/engine/README.md`
- Excluded scope: Slice 1 parser files (`non_stream_parser.py`, `sse_parser.py`, `engine_events.py`), Host production code, Host state machine, EventLog schema
- Parallel review coverage: 无

## Findings

### 1-未修复-中-`_HTTPErrorBody.raw_payload` docstring 仍承诺"原始载荷"

- **入口/函数**: `_HTTPErrorBody` 私有 dataclass 的 `raw_payload` 字段 docstring
- **文件(行号)**: `dayu/engine/runners/openai/runner.py:101`
- **输入场景**: 任何触发 HTTP error body 读取的路径（非 200 响应），reader 读取并解析 JSON 后构造 `_HTTPErrorBody`。
- **实际分支**: `_safe_read_error_body` 在 `isinstance(decoded, dict)` 分支中调用 `http_error_diagnostic_payload(decoded)` 构造诊断载荷，再传给 `_HTTPErrorBody(raw_payload=...)`。
- **预期行为**: docstring 应如实描述 `raw_payload` 是通过 `http_error_diagnostic_payload` 派生出的有界诊断载荷，而非 provider 原始 JSON object。
- **实际行为**: docstring 写 `:param raw_payload: 当 body 是 JSON object 时保留的原始载荷。`（"原始载荷"是 Slice 1 时代的确切描述，Slice 2 已改为有界诊断载荷后，该描述不再准确）。
- **直接证据**: `runner.py:897-899` 已改为 `http_error_diagnostic_payload(decoded)`；`runner.py:101` 的 docstring 仍为 "原始载荷"。`RunnerHTTPErrorData` 的 docstring（`runner_events.py:174-179`）和 `_safe_read_error_body` 的 docstring（`runner.py:884-887`）均已同步更新为"有界诊断载荷"，唯独 `_HTTPErrorBody` 未同步。
- **影响**: 私有 dataclass 的误导性文档 — 不影响外部调用方或公开契约，但可能误导后续 `runner.py` 维护者在 `_HTTPErrorBody` 的构造点或传递点做出错误假设（例如认为可以从 `raw_payload` 字段读到 provider 原始 JSON）。
- **建议改法和验证点**: 将 `runner.py:101` 改为 `:param raw_payload: 从有界 HTTP body 派生的有界诊断载荷；解析失败或非 JSON object 响应时为 ``None``。` 与 `_safe_read_error_body` 和 `RunnerHTTPErrorData` 的 docstring 保持语义一致。回归验证：无需测试变更，仅文档修正。
- **修复风险（低）**: 纯 docstring 修正，不影响行为。
- **严重程度（中）**: 私有作用域但会误导后续维护者；与同一文件中其他两处已同步的 docstring 不一致。

## Open Questions

无。

## Residual Risk

- 测试导入 `diagnostic_payload` 模块的私有常量（`_CANONICAL_BYTE_SIZE_FIELD`、`_SHA256_DIGEST_FIELD`、`_PROVIDER_ERROR_FIELD`、`_DIAGNOSTIC_PAYLOAD_MAX_BYTES`）做字段名断言：当前是 Python 测试常用模式，不构成生产风险；若未来私有常量被重命名，相应测试会直接失败，不会悄悄降级断言强度。
- `test_http_error_body_is_capped_before_decode` 的截断后 `raw_payload is None` 断言依赖于截断边界恰好落在 JSON 字符串字面量内部导致 `json.loads` 失败。当前测试体构造保证了这一条件；若未来 `_HTTP_ERROR_BODY_MAX_BYTES` 大幅调整或测试 body 结构变化，存在极低概率边界恰好落在合法 JSON 结束处导致非 None。但即使发生，诊断 helper 也是有界的，不会泄漏原始 payload。风险可接受。

## Conclusion

**PASS** — 无 blocking 或 high severity finding。

Slice 2 按 approved plan 完整实现：

- `runner.py` 的 HTTP JSON error body 路径已从 `raw_payload=decoded` 改为 `http_error_diagnostic_payload(decoded)`，不再保存完整 provider JSON。
- `_HTTP_ERROR_BODY_MAX_BYTES` 与 `_safe_read_error_body_bytes` 行为保留不变。
- `message_text`、`provider_request_id`、retry exhausted final attempt 行为保持。
- Host ingest 测试仅将 fixture 更新为 helper-like diagnostic JSON object，Host 状态机断言不变。
- Engine README 仅新增一条稳定 contract 级别说明，不包含过程状态/实现细节/未来计划。
- 未发现 `Any`/`object`/无类型、`getattr`/`hasattr`、extra payload、compat facade、魔法字符串、中文 docstring 缺失等 AGENTS.md 违规。
- 未发现 Slice 1 回退或 Host production 范围扩散。

Findings: **1**（1 medium）。

建议：修复 Finding 1（`_HTTPErrorBody` docstring 同步）后 accepted slice commit。
