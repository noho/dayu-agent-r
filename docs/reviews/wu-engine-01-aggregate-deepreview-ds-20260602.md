# WU-ENGINE-01 Aggregate Deepreview

## Scope

- Mode: current changes (aggregate deepreview)
- Branch: `refactor/wu-engine-01-runner-diagnostic-payload-audit`
- Base: `main`
- Output file: `docs/reviews/wu-engine-01-aggregate-deepreview-ds-20260602.md`
- Design source: `docs/host/design.md`
- Control doc: `docs/host/host-core-followup-implementation-control.md`
- Plan artifact: `docs/host/wu-engine-01-runner-diagnostic-payload-audit-plan.md`
- Included scope: full branch diff against main (38 files, 3538 insertions, 59 deletions)
- Excluded scope: prior WU review artifacts in `docs/reviews/` (treated as process history, not implementation evidence)
- Parallel review coverage: 无（本 review 为 aggregate deepreview，由单一 reviewer 完整走读全分支 diff）

## Review Method

本 aggregate deepreview 按以下路径逐条走读：

1. **diagnostic_payload.py** 全部 436 行：公共 API + 内部 helper 的入参/分支/返回值/副作用。
2. **non_stream_parser.py** provider error 路径（line 229-250）：`raw_payload` 写入点。
3. **sse_parser.py** provider error / missing choices / invalid choice / invalid UTF-8 路径（line 224-263, 336-437）：`raw_payload` 写入点。
4. **runner.py** HTTP error body 路径（line 882-927）：`_safe_read_error_body` → `http_error_diagnostic_payload`。
5. **agent.py** Engine Agent 透传路径（line 1234-1263）：`RunnerProtocolErrorData.raw_payload` → `ProviderProtocolErrorData.raw_payload`。
6. **host/engine_ingest.py**：核对生产代码零变更。
7. **engine/contracts/runner_events.py** + **engine/engine_events.py**：docstring 语义更新。
8. **engine/README.md**：docs sync 准确性。
9. **test_diagnostic_payload.py** / **test_protocol_error.py** / **test_stream_non_stream_terminal_parity.py** / **test_http_error_event.py** / **test_engine_ingest_mapping.py**：测试真实性、边界覆盖、vacuous pass 风险。
10. Adversarial failure pass：secret 泄漏、无界 payload、fallback 顺序、HTTP/non-stream/stream 一致性。

## Findings

### F-01-未修复-低-`_SENSITIVE_KEY_FRAGMENTS` 仅匹配下划线形态，破折号形态敏感 key 可能漏过

- **入口/函数**: `_is_sensitive_key` → `_top_level_preview`
- **文件(行号)**: `dayu/engine/runners/openai/diagnostic_payload.py:419-428`, `dayu/engine/runners/openai/diagnostic_payload.py:27-33`
- **输入场景**: provider 返回的 JSON error body 中，敏感字段使用破折号形态的 key 名（如 `"api-key"`, `"x-api-key"`），且值为顶层标量（如 `"sk-actual-secret"`）。
- **实际分支**: `_is_sensitive_key("api-key")` → `"api_key" in "api-key"` → `False`（下划线 vs 破折号不匹配）。`_top_level_preview` 将该 key 视为非敏感 key，值进入 `_scalar_preview`（截断至 160 字符）。
- **预期行为**: 与 `api_key` 等价的破折号形态也应触发脱敏。
- **实际行为**: 破折号形态 key 的值可能以有界标量形式进入 diagnostic preview。
- **直接证据**: `_SENSITIVE_KEY_FRAGMENTS = ("api_key", ...)` (line 27)，`_is_sensitive_key` 使用 `fragment in lowered` 子串匹配 (line 428)。`"api_key"` 不匹配 `"api-key"`。
- **影响**: 若 provider 在 JSON error body 中使用 `api-key`（破折号）而非 `api_key`（下划线），且值为顶层标量，该值可能出现在 diagnostic payload preview 中（截断至 160 字符）。真实 OpenAI-compatible API 的 JSON error body 通常使用下划线形态，此场景为边缘风险。
- **建议改法和验证点**: 方案一：在 `_SENSITIVE_KEY_FRAGMENTS` 中增加 `"api-key"` 等破折号变体。方案二：在 `_is_sensitive_key` 中先做 key 规范化（将 `-` 替换为 `_` 后再匹配）。需补测试覆盖破折号形态敏感 key。当前 work unit 非必须修复，可作为 deferred-with-owner residual risk。
- **修复风险（低）**: 仅扩展敏感片段列表，不影响现有 redaction 行为。
- **严重程度（低）**: 真实 provider JSON error body 很少使用破折号形态 key；且非标量值（dict/list）仍通过 `_container_summary` 结构摘要化。

### F-02-未修复-低-`_provider_error_summary` 对非字符串 `code`/`type`/`param` 静默丢弃

- **入口/函数**: `_provider_error_summary` → `provider_error_diagnostic_payload` / `http_error_diagnostic_payload`
- **文件(行号)**: `dayu/engine/runners/openai/diagnostic_payload.py:308-331`
- **输入场景**: provider error 子对象中 `code` 或 `type` 或 `param` 为数值、布尔值或 null（如 `"code": 429` 或 `"code": null`）。
- **实际分支**: `isinstance(value, str) and value.strip() != ""` (line 326) 对非字符串为 `False`，字段被跳过，不进入诊断摘要。
- **预期行为**: 非字符串的 `code`/`type`/`param` 值应保留为有界诊断信息（如 `"code": 429`）。
- **实际行为**: 非字符串值被静默丢弃。
- **直接证据**: `_provider_error_summary` line 326 只处理字符串值；line 367 的 `_scalar_preview` 支持 int/bool/float/None 直通，但 line 326 的门槛已将其过滤。
- **影响**: 若 provider 返回 `"error": {"code": 429, "type": "rate_limit"}`，diagnostic payload 中 `provider_error` 子对象只有 `{"type": "rate_limit"}`，`code` 丢失。轻微降低排障可诊断性。
- **建议改法和验证点**: 将 line 326 条件放宽为 `isinstance(value, (str, int, float, bool)) and (not isinstance(value, str) or value.strip() != "")`，或将非字符串值改为 `str(value)[:max_chars]` 后保留。或显式记录为 deferred plan-level decision。
- **修复风险（低）**: 仅改变字段筛选逻辑，不影响安全边界。
- **严重程度（低）**: 真实 provider API 的 `error.code` 几乎总是字符串；此场景极边缘。

## Open Questions

无。

## Residual Risk

### RR-ENGINE-01-01: 破折号形态敏感 key 片段未覆盖

- **来源**: F-01
- **类型**: 安全/脱敏边界
- **状态**: deferred-with-owner
- **Owner / Destination**: WU-LAYER-02 shared helper consolidation 或后续 security hardening
- **下一步**: 若后续发现真实 provider 使用破折号形态敏感 key，再扩展 `_SENSITIVE_KEY_FRAGMENTS`。当前 work unit 不要求修复。
- **记录**: `_SENSITIVE_KEY_FRAGMENTS` 当前仅包含下划线形态；plan 与 plan review 未要求覆盖破折号变体。

### RR-ENGINE-01-02: 测试 helper `_serialized_size` 保守估算

- **来源**: 代码走读
- **类型**: 测试精度
- **状态**: closed（不影响 correctness）
- **记录**: 测试 helper `_serialized_size` 不使用 `sort_keys=True` 与紧凑分隔符，导致序列化大小估算偏保守。不影响测试有效性（只做上限检查），无需修复。

### RR-ENGINE-01-03: `_DIAGNOSTIC_CHUNK_PREFIX_MAX_BYTES` 为 96 字节

- **来源**: 代码走读
- **类型**: 设计决策
- **状态**: closed（按 plan 实现）
- **记录**: `_DIAGNOSTIC_CHUNK_PREFIX_MAX_BYTES = 96` 在 plan 中未显式指定数值，但实现符合 plan 决策 #3 的"模块级私有常量"要求。96 字节 base64 编码后约 128 字符，在 `_DIAGNOSTIC_PAYLOAD_MAX_BYTES=4096` 约束下有充足余量。

## Validation Results

| 验证项 | 状态 |
|---|---|
| `raw_payload=dict(parsed)` 残留 grep | 0 匹配 |
| `raw_payload=dict(` 残留 grep | 0 匹配 |
| 目标测试（95 个） | 全部通过 |
| pyright | 0 errors, 0 warnings |
| `dayu/host/engine_ingest.py` 生产代码 | 零变更（diff 无输出） |
| `docs/host/design.md` | 零变更（diff 无输出） |
| Engine contracts docstring 更新 | `runner_events.py` / `engine_events.py` 已从"原始载荷"改为"有界诊断载荷" |
| Engine README 同步 | `dayu/engine/README.md:190` 已增加 `raw_payload` 有界诊断语义说明 |
| 分层边界 | 无违反；`diagnostic_payload.py` 仅依赖标准库与 `dayu.contracts.json_value` |
| `Any`/`object`/`getattr`/`hasattr` | 无使用 |
| `extra payload` / metadata bag | 无新增 |

## Conclusion

**PASS** — 无 blocking、high、medium finding。

WU-ENGINE-01 全分支实现已达成目标：

- Runner diagnostic `raw_payload` 通过 `diagnostic_payload.py` 统一有界/脱敏/摘要化。
- Stream / non-stream / HTTP error 三条路径一致使用 helper，不再有 `raw_payload=dict(parsed)` 残留。
- Invalid UTF-8 诊断载荷显式有界（chunk byte size + SHA-256 + bounded prefix base64）。
- `RunnerProtocolErrorData` / `RunnerHTTPErrorData` / `ProviderProtocolErrorData` 字段形状不变，仅 docstring 语义澄清。
- Host ingest 生产代码零变更，引擎 agent 透传路径不变。
- Engine README 同步准确（一条 `raw_payload` 语义说明）。
- 95 个目标测试通过，pyright 0 errors。
- 2 个 low findings（破折号敏感 key 片段、非字符串 provider error code 丢弃），1 个 deferred-with-owner residual risk，均不阻塞。

**建议**: ready-to-open-draft-PR。low findings 不要求当前 work unit 修复；可 deferred 到 WU-LAYER-02 或后续 security hardening。
