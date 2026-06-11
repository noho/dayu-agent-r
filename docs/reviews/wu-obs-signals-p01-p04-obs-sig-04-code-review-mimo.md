# WU-OBS-SIGNALS-01 OBS-SIG-04 Code Review — AgentMiMo

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-04 / P04 Provider Protocol Partial Tool-call Projection`
- Reviewer: AgentMiMo
- Gate: code review only; no production code modification, no commit, no push, no PR.

Reviewed files:

- `dayu/host/engine_ingest.py`
- `dayu/host/tool_trace.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `docs/reviews/wu-obs-signals-p01-p04-obs-sig-04-implementation-codex.md`

核对文档：

- `AGENTS.md`
- `docs/host/design.md`（Tool Trace projection、diagnostic、provider protocol sections）
- `docs/engine/design.md`（EngineEvent stream、RunnerEvent、ToolExecutor protocol）
- `docs/host/wu-obs-signals-p01-p04-plan.md`（P04 / OBS-SIG-04 sections）
- `docs/host/issues-implementation-control.md`（WU-OBS-P04 section）
- `dayu/engine/contracts/partial_tool_call.py`（Engine `PartialToolCallSummary` contract）

## Findings

### F1 [LOW/INFO] 常量重复定义

**位置**: `dayu/host/engine_ingest.py:263-265`、`dayu/host/tool_trace.py:168-170`

**现状**: `_PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION`、`_PARTIAL_TOOL_CALL_SIGNAL_STATUS_NONE`、`_PARTIAL_TOOL_CALL_SIGNAL_STATUS_PRESENT` 在两个模块中各自定义为模块级私有常量。

**评估**: 不违反 AGENTS.md 编码约束。AGENTS.md 禁止的是"兼容性常量 re-export：仅为兼容旧名字而重复导出常量"，此处不是 re-export 而是独立定义。producer（engine_ingest）和 consumer/validator（tool_trace）各自持有同源常量，保持了分层隔离——tool_trace 不 import engine_ingest。这与 P01-P03 已有模式一致（`_FAILURE_METADATA_SCHEMA_VERSION` 在两个模块同样各自定义）。

**建议**: 不改。若未来常量膨胀或出现不一致，可考虑提取到 `dayu/host/_signal_constants.py` 之类的私有共享模块，但当前不值得增加模块。

**风险**: 无。

### F2 [LOW/INFO] `_is_bare_sha256_hex` 性能特征

**位置**: `dayu/host/tool_trace.py:1647-1659`

**现状**: 逐字符检查是否属于 `frozenset("0123456789abcdef")`。

**评估**: 输入长度固定为 64 字符（先检查 `len(value) != 64`），逐字符检查 64 次 frozenset lookup 对 Tool Trace projection 性能无实际影响。使用 `frozenset` 而非 `set` 也是合理的不可变集合选择。

**建议**: 不改。

**风险**: 无。

## Open Questions

无阻塞性 open question。

## Residual Risk

1. **Analyzer 分类边界**: `arguments_present` 来自 Engine summary digest presence，不来自 raw arguments 或 provider stream replay。Analyzer 无法仅凭 `arguments_sha256` 证明 JSON malformed——这需要 raw arguments。实现正确地选择暴露 bytes/digest，让 analyzer 结合 `error_code` 做 limited signal 分类。Plan 已明确此边界。

2. **Old trace limited signal**: 历史 trace 缺少 `partial_tool_call_signal` 字段时，analyzer 必须报告 limited signal 而非"no partial"。实现正确地不回填旧 trace，新 trace 的 empty tuple 才是 positive no-partial signal。Test fixture 覆盖了 absent / none / present 三种状态。

3. **无索引查询**: partial summary 未添加 SQLite 索引。现有 provider request scan path 是 planned analyzer input。Plan 已明确此决策。

## Scope Creep Assessment

无 scope creep。实现严格限制在 plan 定义的 allowed files/modules 内：

- 未修改 Engine parser、Engine public contract。
- 未修改 SQLite schema。
- 未修改 provider stream replay。
- 未修改 raw payload export。
- 未修改 P03 failure metadata。
- 未实现 analyzer report。

新增代码仅包含两个模块级私有函数（`_provider_protocol_partial_tool_call_signal`、`_partial_tool_call_summary_payload`）和 Tool Trace 侧的验证函数群。函数粒度合理，未产生 God function。

## Architecture Alignment

1. **分层**: Producer 在 `engine_ingest.py`（Host ingest 层），consumer/validator 在 `tool_trace.py`（Host projection 层）。不违反 `UI -> Service -> Host -> Engine` 分层。不违反 `dayu.runtime` 不 import host 的约束。

2. **Diagnostic vs canonical**: `partial_tool_call_signal` 写入 EventLog 作为 `DIAGNOSTIC` class payload，不改变 Run / Attempt 状态。与 plan 的"projection signal and diagnostic rows remain non-governing"一致。

3. **Read-only projection**: Tool Trace 只做 copy/validate，不重算 Engine 逻辑，不重算 Host budget。与 `docs/host/design.md:1665-1663` 的 read-only signal 边界一致。

4. **Engine contract consumption**: 只消费 `ProviderProtocolErrorData.partial_tool_calls`（已有 `tuple[PartialToolCallSummary, ...]`），不消费 raw provider stream。与 `docs/engine/design.md:303-325` 和 `dayu/engine/contracts/partial_tool_call.py` 一致。

5. **Additive payload**: `partial_tool_call_signal` 是 additive diagnostic payload 字段。现有 consumer（如 `_legacy_provider_protocol_diagnostic_view` 测试模拟的旧消费者）只读取既有字段，不受影响。

## AGENTS.md 编码约束检查

| 约束 | 状态 | 证据 |
| --- | --- | --- |
| 中文 docstring | ✅ | 所有新增函数均有完整中文 docstring，含参数、返回值、异常说明 |
| 禁止 `Any`/`object`/无类型签名 | ✅ | 所有参数和返回值均有严格类型标注 |
| 禁止魔法数字/魔法字符串散落 | ✅ | 常量集中定义为模块级 `_` 前缀常量 |
| 禁止兼容性 seam | ✅ | 无 re-export、无 wrapper、无 facade |
| 禁止 LLM-facing 语义泄漏 | ✅ | signal 字段为 diagnostic projection，不伪装为业务事实 |
| 无 `hasattr`/`getattr` 滥用 | ✅ | 使用 `_optional_signal_object` 等 typed helper |
| 无 God function | ✅ | 函数粒度合理，每个函数职责单一 |
| 无嵌套函数/嵌套类 | ✅ | 所有函数为模块级 |

## Test Coverage Assessment

### 覆盖矩阵

| 场景 | 测试文件 | 测试函数 | 状态 |
| --- | --- | --- | --- |
| Empty partial tuple + raw payload present | `test_engine_ingest_mapping.py` | `test_provider_protocol_error_is_diagnostic_without_state_change` | ✅ |
| Non-empty partial + digest present/absent + raw payload absent | `test_engine_ingest_mapping.py` | `test_provider_protocol_error_serializes_partial_tool_call_signal` | ✅ |
| Legacy consumer tolerates additive field | `test_engine_ingest_mapping.py` | `_legacy_provider_protocol_diagnostic_view` helper | ✅ |
| Absent historical limited signal | `test_tool_trace_projection.py` | `test_tool_trace_projects_provider_protocol_partial_tool_call_signal_states` | ✅ |
| New positive no-partial signal | `test_tool_trace_projection.py` | 同上 | ✅ |
| Present bounded summary signal | `test_tool_trace_projection.py` | 同上 | ✅ |
| Hot row == cold JSONL | `test_tool_trace_projection.py` | 同上（`assert ... == row.trace_summary`） | ✅ |
| Malformed: present status + empty list | `test_tool_trace_projection.py` | `test_tool_trace_rejects_malformed_partial_tool_call_signal` | ✅ |
| Malformed: count mismatch | `test_tool_trace_projection.py` | 同上 | ✅ |
| Malformed: invalid sha256 | `test_tool_trace_projection.py` | 同上 | ✅ |
| Provider-request query retains signal | `test_tool_trace_queries.py` | `test_provider_request_id_terminal_diagnostic_query` | ✅ |

### 验证结果

- pytest: 97 passed (0.97s)
- pyright: 0 errors, 0 warnings, 0 informations

### 覆盖率评估

Producer path（engine_ingest）和 consumer/validator path（tool_trace）均有直接测试。Query path 有验证。Malformed signal 的 fail-closed 行为有 3 个参数化 case。Absent / none / present 三态有独立断言。覆盖充分。

## Validation

| 验证项 | 结果 |
| --- | --- |
| `pytest tests/host/test_engine_ingest_mapping.py tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py` | 97 passed |
| `pyright` | 0 errors |
| README 决策 | `dayu/host/README.md` 和 `tests/README.md` 均已阅读 Agent update constraints，未更新（合理：变更仅扩展 signal fields 和 tests，不改变 public interface、architecture boundary、state machine、schema 或 developer-facing operation） |
| Git diff scope | 仅涉及 plan 定义的 5 个文件，无越界修改 |

## Verdict

**PASS**

实现严格遵循 plan 设计，信号来源单一（Engine `ProviderProtocolErrorData.partial_tool_calls`），producer shape 完整（schema_version / signal_source / count / status / raw_payload_present / partial_tool_calls），summary 字段仅含 bounded/redacted Engine fields（无 raw arguments），raw_payload_present 仅来自 descriptor presence，Tool Trace projection 正确 copy/validate/fail-closed，测试覆盖 absent/none/present 三态和 malformed fail-closed，97 tests passed，pyright 0 errors，无 scope creep，无 AGENTS.md 违规。未发现需要修复的 finding。
