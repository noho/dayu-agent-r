# WU-OBS-SIGNALS-01 OBS-SIG-04 Code Review — AgentDS

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-04 / P04 Provider Protocol Partial Tool-call Projection`
- Role: AgentDS code reviewer
- Gate: code review only; no implementation, no fix, no commit, no push, no PR.

审查依据：
- AGENTS.md（项目编码约束、架构硬约束、Agent 语义约束）
- `docs/host/wu-obs-signals-p01-p04-plan.md` P04 与 OBS-SIG-04 sections
- `docs/host/design.md` 相关 Tool Trace / EventLog 设计真源
- `docs/engine/design.md` Engine 事件流与 bounded partial summary 契约
- `docs/host/issues-implementation-control.md` WU-OBS-SIGNALS-01 / OBS-SIG-04 当前状态
- `docs/reviews/wu-obs-signals-p01-p04-obs-sig-04-implementation-codex.md`
- 当前 git diff 六个文件变更

## Findings

### Finding 1 — LOW: malformed partial_tool_call_signal 参数化测试未覆盖全部 fail-closed 分支

**严重度**: LOW

**证据**:
- `tests/host/test_tool_trace_projection.py:939-991` (`test_tool_trace_rejects_malformed_partial_tool_call_signal`) 覆盖了 3 个 malformed 场景：present status + empty list（状态/计数矛盾）、count 与 list 长度不匹配、arguments_sha256 格式非法。
- `dayu/host/tool_trace.py:1549-1579` (`_optional_partial_tool_call_signal`) 和 `dayu/host/tool_trace.py:1607-1645` (`_validate_partial_tool_call_summary`) 包含以下未直接参数化覆盖的 HostDurableError 分支：
  - `schema_version` 不匹配（line 1550-1553）
  - `signal_source` 不匹配（line 1555-1556）
  - `partial_tool_call_count < 0`（line 1558-1559）
  - `partial_tool_calls` 字段缺失或不是 JSON array（line 1592-1596）
  - 数组成员不是 JSON object（line 1599-1602）
  - `summary_status` 为 `none` 时 `partial_count != 0`（line 1566-1568）
  - `summary_status` 为非法值（line 1575-1576）
  - `tool_call_index < 0`（line 1614-1617）
  - `arguments_byte_size < 0`（line 1623-1626）
  - `arguments_present=True` 但 `arguments_sha256=None`（line 1630-1633）
  - `arguments_present=False` 但 `arguments_sha256` 存在（line 1639-1642）

**影响**: 这些 fail-closed 路径使用与 OBS-SIG-00 至 OBS-SIG-03 相同的 `_required_int` / `_required_text` / `_required_bool` / `_optional_text` helper，这些 helper 已在其他 signal 的 malformed 测试中被验证。未覆盖分支的验证逻辑是直接的字段类型/值校验，没有复杂状态机分支。风险很低。

**建议**: 当前可接受，不要求本次 fix gate 补齐。若后续其他 signal 的 malformed 测试也出现类似缺口，可在 OBS-SIG-05 集成阶段统一补齐。

**风险**: 极低——这些 fail-closed 路径是简单的类型/边界检查，即使未直接测试，生产者测试（`test_provider_protocol_error_serializes_partial_tool_call_signal` 和 `test_tool_trace_projects_provider_protocol_partial_tool_call_signal_states`）已确保合法数据路径通过所有校验。

---

### Finding 2 — INFO: `_is_bare_sha256_hex` 与 `is_sha256_digest` 格式差异为有意设计

**严重度**: INFO（非缺陷，为设计决策记录）

**证据**:
- `dayu/host/tool_trace.py:1647-1657` 的 `_is_bare_sha256_hex` 检查 64 位小写 hex 字符串（无 `sha256:` 前缀）。
- `dayu/host/durable/codec.py:93-100` 的 `is_sha256_digest` 检查 `sha256:<64 lowercase hex>` 格式（有前缀）。
- `tests/engine/runners/openai/test_protocol_error.py:477-490` 确认 Engine `arguments_sha256` 由 `hashlib.sha256(...).hexdigest()` 产生，即裸 64 位小写 hex，无前缀。
- Plan `docs/host/wu-obs-signals-p01-p04-plan.md:37` 描述"arguments_present 来自 Engine summary digest presence"，且 P04 规则"只包含 bounded/redacted Engine summary fields"。

**影响**: 无——两种格式分属不同上下文（Host durable digest vs Engine partial arguments digest），`_is_bare_sha256_hex` 正确匹配 Engine 的真实格式。此 finding 仅记录设计决策，供后续维护者参考。

**建议**: 无需修改。若未来 Engine `arguments_sha256` 格式变更，需同步更新 `_is_bare_sha256_hex`。

---

### Positive Observations（非 finding）

以下逐条对照审查重点，均无问题：

1. **动机/root cause 成立**: `partial_tool_call_signal` 仅来自 `Engine ProviderProtocolErrorData.partial_tool_calls`（`engine_ingest.py:2880` 传入 `data.partial_tool_calls`），`raw_payload_present` 来自 `raw_descriptor is not None`（`engine_ingest.py:2861`）。未从 raw provider stream、日志或猜测补造事实。

2. **Producer shape 完整**: `_provider_protocol_partial_tool_call_signal` (`engine_ingest.py:5978-6007`) 产出所有必需字段：`schema_version=1`、`signal_source="PROVIDER_PROTOCOL_ERROR"`、`partial_tool_call_count`、`summary_status`、`raw_payload_present`、`partial_tool_calls`。empty tuple → `summary_status="none"` + `count=0`；non-empty → `summary_status="present"`。

3. **Partial summary 字段有界**: `_partial_tool_call_summary_payload` (`engine_ingest.py:6010-6028`) 仅序列化 `tool_call_index`、`tool_call_id`、`name_fragment`、`arguments_byte_size`、`arguments_sha256`、`arguments_present`。无 raw arguments。`tool_call_id` 和 `name_fragment` 受 Engine `PartialToolCallSummary` 约束（`PARTIAL_TOOL_CALL_ID_MAX_CHARS=128`）。

4. **raw_payload_present**: 仅来自 descriptor presence（`raw_descriptor is not None`），不读取 raw payload 内容。

5. **Tool Trace projection 正确校验**: `_optional_partial_tool_call_signal` (`tool_trace.py:1535-1579`) 校验 schema_version、signal_source、count ≥ 0、summary_status 合法性、count 与 list 长度一致性、status/count 语义一致性，并对每个 summary 调用 `_validate_partial_tool_call_summary`。absent field → `None`（historical limited signal）；empty tuple → positive no-partial；malformed → `HostDurableError` fail closed。

6. **Query/test 覆盖充分**: `test_provider_request_id_terminal_diagnostic_query` 确认 provider-request query 返回 `trace_summary.partial_tool_call_signal`；`test_tool_trace_projects_provider_protocol_partial_tool_call_signal_states` 区分 absent/none/present 三种状态。

7. **分层/scope 正确**: 不改 Engine parser、Engine public contract、SQLite schema、provider stream replay、raw payload export、P03 failure metadata（仅重构 `raw_payload_ref` 提取为变量）、analyzer report。

8. **README decision 合理**: `dayu/host/` 和 `tests/` 修改触发 AGENTS.md 检查，implementation report 确认已读目标 README 约束且无需更新。变更仅为现有 Tool Trace signal 体系内的增量字段，不改变公共接口、架构边界、状态机或 developer-facing 操作。符合 AGENTS.md README 触发规则。

9. **编码约束合规**:
   - 所有新增函数有完整中文 docstring（`_provider_protocol_partial_tool_call_signal`、`_partial_tool_call_summary_payload`、`_optional_partial_tool_call_signal`、`_required_partial_tool_call_summary_list`、`_validate_partial_tool_call_summary`、`_is_bare_sha256_hex`）。
   - 无 `Any`、`object`、无类型参数/返回值。
   - 魔法字符串使用模块级私有常量（`_PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION`、`_PARTIAL_TOOL_CALL_SIGNAL_STATUS_NONE`、`_PARTIAL_TOOL_CALL_SIGNAL_STATUS_PRESENT`、`_PARTIAL_ARGUMENTS_SHA256_HEX_LENGTH`、`_LOWER_HEX_CHARS`）。
   - 无兼容 seam、wrapper、re-export。
   - 新增函数为模块级私有辅助函数，无嵌套函数/类。
   - `raw_payload_ref`/`raw_payload_digest` 从内联表达式提取为局部变量——消除重复，属正向清理。
   - 函数参数使用 keyword-only (`*`) 和显式类型。

10. **测试覆盖与验证**:
    - 97 tests passed，pyright 0 errors（已独立复验确认）。
    - Engine ingest mapping：empty tuple、non-empty with digest present/absent、`arguments_present` 推导、raw payload absent/present。
    - Tool Trace projection：absent/none/present 三态区分、malformed fail-closed（3 场景）。
    - Consumer impact：legacy consumer 读取旧字段容忍 additive `partial_tool_call_signal`。
    - Provider-request query：partial signal 出现在查询结果中。

11. **LLM-facing 语义未泄漏**: 新增字段均为内部治理/诊断字段（`schema_version`、`signal_source`、`raw_payload_present`、`arguments_sha256`、`arguments_byte_size`），不在 prompt、tool schema、memory、compact 或 evidence material 中暴露。符合 Agent 语义约束——这些字段仅在 Test/Tool Trace 内部使用，不进入 LLM 上下文。

## Open Questions

无。

## Residual Risk

- **R1**：`_is_bare_sha256_hex` 硬编码 64 字符小写 hex 校验。若 Engine 未来改用其他 digest 格式（如 base64、大写 hex），此校验将误拒合法数据。Owner: Engine partial_tool_call contract 变更时同步更新。
- **R2**：`arguments_present` 仅从 `arguments_sha256 is not None` 推导，不验证 sha256 是否对应真实已收到的 arguments。这是一种有意设计（plan 明确禁止保存 raw arguments），analyzer 需结合 `error_code` 判断 malformed 可能性。Owner: WU-OBS-00 analyzer。

## Scope Creep Assessment

无 scope creep。变更严格限制在 P04 scope 内：
- 仅修改 `dayu/host/engine_ingest.py`（producer）和 `dayu/host/tool_trace.py`（projection）。
- 仅新增 `partial_tool_call_signal` 字段及相关校验/测试。
- `raw_payload_ref`/`raw_payload_digest` 提取为变量是同一函数内的纯重构。
- 未动 Engine parser、Engine contract、SQLite schema、ToolRuntime、analyzer、其他 signal。

## Architecture Alignment

完全对齐 Host/Engine 设计真源：
- `docs/engine/design.md:483`: "Engine 不提供持久化 cursor...调用方若需要...必须在 Engine 外部把 EngineEvent ingest 成自己的 durable facts" → Host ingest 正确消费 Engine event 并写入 Host diagnostic EventLog。
- `docs/host/design.md:1654`: "Tool trace 是 EventLog 派生 projection，不是 Host durable truth" → 新增 signal 仅作为 projection 字段复制，不改变 EventLog 事实。
- `docs/host/design.md:1665`: "Tool Trace 对 runner-call reconstruction 的消费边界固定为 read-only signal" → partial_tool_call_signal 是 read-only copy。
- 分层架构: Engine → Host ingest (diagnostic EventLog) → Tool Trace projection (hot summary + cold JSONL) → future analyzer，无反向依赖。

## Test Coverage Assessment

| 测试文件 | 覆盖内容 | 评估 |
| --- | --- | --- |
| `test_engine_ingest_mapping.py` | empty tuple signal、non-empty with digest present/absent、raw payload absent/present、legacy consumer tolerance | 充分 |
| `test_tool_trace_projection.py` | absent/none/present 三态区分、malformed fail-closed（3 场景）、非 object 字段 fail close | 基本充分（见 Finding 1） |
| `test_tool_trace_queries.py` | provider-request query 返回 partial signal | 充分 |

冷 JSONL 一致性由现有 `_cold_trace_summary` assertion pattern 覆盖（`test_tool_trace_projects_provider_protocol_partial_tool_call_signal_states` 同时验证 hot row 和 cold line）。

## Validation

独立复验结果：

```bash
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py \
  tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -v
# 97 passed in 1.01s

source .venv/bin/activate && pyright
# 0 errors, 0 warnings
```

与 implementation report 声称一致。

## Verdict

**PASS**

0 条 blocking findings。1 条 LOW（测试覆盖缺口，现有 helper pattern 已覆盖，风险极低），1 条 INFO（设计决策记录）。

变更严格遵守 plan scope、分层架构、编码约束和信号数据同源规则。所有 97 个受影响测试通过，pyright 0 errors。partial_tool_call_signal 正确从 Engine bounded summary 投影到 Host diagnostic / Tool Trace，可区分 absent/none/present 三种状态，使 WU-OBS-00 analyzer 能够消费结构化 partial signal 而不依赖日志文本或 raw payload 猜测。
