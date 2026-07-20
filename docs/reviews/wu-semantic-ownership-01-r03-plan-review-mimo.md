# WU-SEMANTIC-OWNERSHIP-01 / R03 Plan Review — AgentMiMo

## 1. Review 身份与结论

| 项目 | 值 |
| --- | --- |
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` |
| remediation | `R03 — accepted call 语义与 opaque provenance 的单一 LLM 投影` |
| reviewed target | `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md` |
| plan evidence base | `444bb33eaebba5f56d3cd211ced90e3b9d67a4fc` |
| review scope | 1177 行完整计划 + controller discussion + design truth + 当前代码/测试直接证据 |
| verdict | **PASS-WITH-RISKS** |

计划整体方向正确，root cause 分析基于直接代码证据，三片切分合理，owner boundary 清晰。发现 3 个 material findings 和 5 个 non-blocking notes，均不构成结构性不安全或需要大范围重写。所有 findings 均可在 implementation 前修正计划文本解决。

## 2. Assumptions Tested

| # | Assumption | 验证结果 |
| --- | --- | --- |
| A1 | ordinary/awaiting 两套 request payload 确实存在且字段不同 | **confirmed**：`tool_runtime.py::_tool_call_request_payload_plan` 使用 canonical args + cold descriptor + optional semantic query；`waiting.py::_tool_call_requested_event_request` 调用 `llm_safe_replay_arguments` 改写参数后只写 inline payload + synthetic query |
| A2 | `TOOL_AWAITING` payload 确实重复保存 accepted args/digest | **confirmed**：`_event_payload.py::tool_awaiting_payload` 签名含 `accepted_arguments` 和 `normalized_arguments_digest`，内部调用 `llm_safe_replay_arguments` 写入 `_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS` |
| A3 | `tool_call_request_atoms` 未断言 `arguments_payload_digest == normalized_arguments_digest` | **confirmed**：line 140 只检查 `sha256_digest_json(arguments_json) == arguments_payload_digest`，不与 `normalized_arguments_digest` 交叉验证 |
| A4 | `_source_projection` 使用 opaque refs 拼接业务来源 | **confirmed**：遍历 `envelope.source_refs + locator_refs`，对非 internal kind 输出 `"{ref_kind}:{ref_id}"`，如 `"filing:MSFT-10K"` |
| A5 | `_contains_unsafe_argument_key` 基于字段名黑名单 | **confirmed**：检查 `api_key/token/secret/password` 片段和 `path` 后缀 |
| A6 | `json_redaction.py` 存在且仅被 `_event_payload.py` 和 `tool_trace.py` 使用 | **confirmed**：`llm_safe_replay_arguments` 调用它，`tool_trace.py::_redacted_json` 调用它；无其它 production importer |
| A7 | `result.value.citation` 在 `accepted_result_projection.py` 中不被读取 | **confirmed**：`citation` 字符串不出现在该文件；citation 概念完全在 Fins domain（`tool_models.py::Citation` + `read_runtime.py::_build_citation`） |
| A8 | `business_source_text/state` 字段当前不存在 | **confirmed**：全仓 grep 零命中；`tool_trace.py` 的 `tool_result` summary 无 citation/source 字段 |
| A9 | `_awaiting_semantic_query_text` 生成合成 query | **confirmed**：返回 `f"工具 {tool_name} 请求参数：{canonical_json_dumps(dict(safe_arguments))}"` |
| A10 | `_tool_call_requested_event_id_from_wait_id` 从 wait_id 推导 request event id | **confirmed**：strips `wait-` prefix, prepends `event-tool-call-requested-awaiting-` |

## 3. Findings

### 001-未修复-高-source projection 机制变更未充分规格化

- **位置**: §4.6 query/source/material contract
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: "source：只读取 canonical raw outcome 的精确路径 `kind=completed -> result.ok=true -> result.value -> citation`。`citation` 为 JSON object 时使用 `canonical_json_dumps` 稳定渲染；缺失、拼错或非 object 时使用唯一文案"
- **反例/失败场景**: 当前 `_source_projection(envelope, source_locator_refs)` 签名接收 envelope refs，不接收 raw tool outcome。计划未说明如何将 raw outcome 传入投影函数。Implementation agent 需要自行决定：(a) 修改 `_source_projection` 签名增加 raw outcome 参数；(b) 在调用方解析 citation 后传入；(c) 其它方式。签名变更影响 S3 所有四个消费者的调用链，未规格化会导致 agent 做出不一致选择
- **为什么有问题**: §11.3 item 2 说"_source_projection 改为只读 raw outcome exact citation path"，但未给出新函数签名、输入类型、如何从 `AcceptedToolResultProjection` 当前构造流程中获取 raw outcome、以及 citation JSON object 的精确字段名/类型。这是 S3 的核心改动，必须 code-generation-ready
- **直接证据**: 当前 `_source_projection` 签名为 `def _source_projection(envelope: AcceptedEvidenceEnvelope | None, source_locator_refs: tuple[OpaqueEvidenceRef, ...]) -> AcceptedToolResultSourceProjection`（`accepted_result_projection.py:644`）。`Citation.to_dict()` 返回 `{source_type, document_id, ticker, form_type?, filing_date?, accession_no?, source_provider?, fiscal_year?, fiscal_period?, item?, heading?}`（`tool_models.py:119-125`）。`render_accepted_tool_evidence_for_llm` 签名为 `(material: AcceptedToolEvidenceLLMMaterial | None) -> str`（`evidence.py:168`）
- **影响**: Implementation agent 猜测投影函数签名和 raw outcome 传递方式 → 四个消费者代码不一致 → 后续返工
- **建议改法和验证点**: 在 §4.6 或 §11.3 补充：(1) `_source_projection` 新签名明确接收 raw outcome text 或已解析的 citation dict；(2) 调用方如何从 `TOOL_RESULT_ACCEPTED` event payload 中获取 raw outcome 并传入投影；(3) `AcceptedToolEvidenceLLMMaterial` 是否新增 `business_source_text: str` 字段或复用现有 `source` 字段；(4) citation dict 的精确 key 枚举和渲染规则（哪些 key 进入 text、顺序、分隔符）。验证：实现 agent 无需做任何签名/传递方式决定
- **修复风险（低/中/高）**: 中
- **严重程度（高/中/低/严重）**: 高

### 002-未修复-中-Tool Trace `business_source_text/state` 字段不存在且未规格化

- **位置**: §4.7 Tool Trace 内外边界、§11.3 item 8
- **问题类型**: 契约缺失
- **当前写法**: "`trace_summary.tool_result` 增加 `business_source_text/state`，值只来自 shared projection"
- **反例/失败场景**: `business_source_text` 和 `business_source_state` 当前不存在于任何类型定义。Implementation agent 需要自行决定：字段类型（str? str | None?）、state 枚举值（available/unavailable?）、在 `ToolResultSummary` dataclass 中的位置、与现有 `result_summary_text` 的关系。未规格化时 agent 可能在不同 slice 中为同一语义创建不一致的字段
- **为什么有问题**: §4.7 要求"trace_summary.tool_result 增加 business_source_text/state"，但未给出字段类型、state 枚举、默认值、与 shared projection 的映射关系。这是 S3 新增字段，必须在计划中自足说明
- **直接证据**: 全仓 grep `business_source_text` 和 `business_source_state` 零命中。`tool_trace.py::_tool_result_summary_from_projection`（line 1265）当前返回 `result_status/result_summary_text/result_details/result_text` 等字段，无 citation/source 相关字段
- **影响**: Agent 自行设计字段类型和枚举 → 与 shared projection 不一致 → review 返工
- **建议改法和验证点**: 在 §4.7 补充字段定义：(1) `business_source_text: str` — 渲染后的 citation text 或 unavailable 文案；(2) `business_source_state: Literal["available", "unavailable"]` — 或直接省略 state 仅用 text；(3) 与 `AcceptedToolResultSourceProjection` 的映射。验证：agent 无需自行设计字段
- **修复风险（低/中/高）**: 低
- **严重程度（高/中/低/严重）**: 中

### 003-未修复-中-evidence renderer 输入 contract 变更未充分规格化

- **位置**: §11.3 item 4
- **问题类型**: 契约缺失
- **当前写法**: "`render_accepted_tool_evidence_for_llm` 参数改为非 optional；删除整体 unavailable fallback constant/branch。缺 material 的 Memory/RunInput/Compact consumer 显式 fail closed"
- **反例/失败场景**: 当前 `render_accepted_tool_evidence_for_llm(material: AcceptedToolEvidenceLLMMaterial | None) -> str` 接受 None 并返回 unavailable fallback 文案。计划要求参数改为非 optional，意味着所有调用方必须在调用前检查 None 并 fail closed。但未说明 fail closed 的具体行为：抛什么异常？哪个 consumer 捕获？捕获后做什么？Memory consumer 抛错会导致整个 Memory 构建失败还是跳过该 evidence？
- **为什么有问题**: 四个 consumer（RunInput/Memory/Compact/Trace）各自处理 fail closed 的方式可能不一致。Memory 构建失败 vs 跳过单条 evidence vs 返回 unavailable 文案是不同的产品行为
- **直接证据**: `render_accepted_tool_evidence_for_llm` 当前在 `evidence.py:168`；`memory.py::_selected_evidence_text`（line 1695）调用它并当 `accepted_tool_evidence is None` 时返回 fallback 文案 `"工具证据不可用；缺少可安全展示的工具名称或工具结果。"`。`compact_material.py` 和 `run_input.py` 也有类似调用
- **影响**: Agent 在四个 consumer 中实现不一致的 fail closed 策略 → 部分 consumer 崩溃、部分静默跳过 → review 返工
- **建议改法和验证点**: 在 §11.3 item 4 或 §4.5 补充：(1) fail closed 统一为抛 `HostDurableError`；(2) 四个 consumer 的上层调用方如何捕获：Memory 跳过该 evidence 并记录 diagnostic、RunInput 抛出终止 Attempt、Compact 跳过该 evidence、Trace 标记 unavailable；或统一为全部抛出由上层处理。验证：agent 无需在四个 consumer 中分别设计 fail closed 策略
- **修复风险（低/中/高）**: 低
- **严重程度（高/中/低/严重）**: 中

### 004-未修复-低-`_accepted_arguments_json` 和 `_awaiting_semantic_query_text` 的调用方未完整枚举

- **位置**: §6.3 item 3
- **问题类型**: 测试缺口 / 不可直接实施
- **当前写法**: "waiting.py::_tool_call_requested_event_request、_accepted_arguments_json、_awaiting_semantic_query_text、本地 _payload_size_bytes 删除"
- **反例/失败场景**: 如果 `_accepted_arguments_json` 或 `_awaiting_semantic_query_text` 被 `_tool_call_requested_event_request` 以外的函数调用，S1 删除它们会导致 import error。计划未提供"当前只有这一条调用路径"的直接证据
- **为什么有问题**: 计划声称可以删除这些函数，但未证明它们的调用方闭集。Implementation agent 可能需要自行 grep 确认，若遗漏则 break
- **直接证据**: Agent 探索确认 `_accepted_arguments_json`（line 2389）和 `_awaiting_semantic_query_text`（line 2399）是 `waiting.py` 的私有函数，仅被同文件 `_tool_call_requested_event_request`（line 2323）调用。但计划文本未记录这一验证
- **影响**: 低 — 直接代码搜索可确认安全性，但计划应记录验证以避免 agent 重复工作
- **建议改法和验证点**: §6.3 item 3 补充一句"当前直接代码证据确认 `_accepted_arguments_json` 和 `_awaiting_semantic_query_text` 仅被 `_tool_call_requested_event_request` 调用"
- **修复风险（低/中/高）**: 低
- **严重程度（高/中/低/严重）**: 低

### 005-未修复-低-event sequence linkage 的 transaction 语义未指定

- **位置**: §4.4、§4.2
- **问题类型**: 状态机漏洞 / 并发恢复风险
- **当前写法**: "`TOOL_AWAITING` 的 `tool_call_requested_event_ref` 由同一 accept transaction 中先写入的真实 row 生成"
- **反例/失败场景**: `tool_call_requested_event_ref` 需要 `{event_id, event_sequence}`。event_id 可预生成，但 event_sequence 通常由 EventLog append API 在写入时分配。如果 EventLog API 不在 append 前返回 sequence，awaiting payload 无法在同一事务中引用它。controller validation 已将此列为 review 挑战项
- **为什么有问题**: 计划依赖同一事务中先写 TOOL_CALL_REQUESTED 再写 TOOL_AWAITING，后者引用前者的 sequence。若 EventLog API 不支持此模式，需要改为 post-write linkage 或 retry
- **直接证据**: controller validation §3 item 1: "shared writer 是否能在现有 transaction append API 中取得真实 event sequence 并安全写入 TOOL_AWAITING link"
- **影响**: 若 API 不支持，implementation agent 可能 hack sequence 或放弃事务原子性
- **建议改法和验证点**: §4.4 补充：(1) 当前 EventLog append API 是否返回写入后的 event_sequence；(2) 若不返回，改用 pre-generated sequence 或 post-write linkage 的具体方案；(3) 事务失败时 TOOL_CALL_REQUESTED 和 TOOL_AWAITING 的 rollback 语义
- **修复风险（低/中/高）**: 低（属于实施前确认，不改计划方向）
- **严重程度（高/中/低/严重）**: 低

## 4. Non-Blocking Notes

### N1 — `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 语义变更

当前文案 `"业务来源不可用；工具结果未提供可安全展示的来源。"` 暗示 Host 做了"安全展示"判断。计划改为业务中性文案 `"该工具结果未提供业务来源。"` 是正确的。但需注意：Memory/Compact 等 consumer 的现有测试可能断言旧文案文本，S3 implementation 需同步更新这些 assertion。计划 §11.4 已覆盖"no citation 时为 source-unavailable"测试，但未显式提到旧文案 assertion 更新。

### N2 — S1/S2 对 `_event_payload.py` 的修改边界

S1 item 4 修改 `tool_awaiting_payload` 删除 args/digest 参数和字段；S2 §7.3 删除 `_event_payload.py` 中已失去调用方的 `llm_safe_replay_arguments`。两者修改同一文件但不同函数/符号，无冲突。但 implementation agent 应注意 S1 先落地，S2 再删除 S1 产生的 dead code。

### N3 — coverage targets 合理但需注意新增模块

`tool_call_request.py >= 95%` 是对全新模块的高要求。计划 §6.4 已列出 corruption matrix 测试，但未明确覆盖 cold descriptor path、large args descriptor path、idempotent replay same-key/different-digest 冲突等边界。建议 §6.4 补充这些 case 到测试列表。

### N4 — real smoke 依赖外部环境

§12.2 要求真实 Doc/Web/Fins smoke，依赖 provider credential、可访问网络和真实 Fins fixture。计划 §16 已将此列为 residual risk，但未说明 CI 环境如何满足。若 CI 无 credential，smoke 只能在开发机运行，completion artifact 需记录环境限制。

### N5 — §8 inventory baseline 完整性

§8 的 37 个 prompt asset 和 114 个 constructor scan path 覆盖面广泛。Controller validation 已确认无遗漏。但 completion report 必须逐行核对而非依赖 grep 零命中，计划已明确此要求（§8.3 最后一段）。

## 5. Open Questions

| # | 问题 | owner | 阻塞? |
| --- | --- | --- | --- |
| OQ1 | EventLog append API 是否在同一事务中返回写入后的 event_sequence？ | S1 implementation 前确认 | 否（可预生成或 post-write） |
| OQ2 | `_source_projection` 新签名是否需要接收 raw outcome text 或已解析的 citation dict？ | S3 plan 细化 | 是（需在计划中规格化） |
| OQ3 | 四个 consumer 的 fail closed 策略是否统一为 `HostDurableError`？ | S3 plan 细化 | 是（需在计划中规格化） |

## 6. Residual Risks

| 风险 | 当前处理 | destination |
| --- | --- | --- |
| 未来 tool schema 新增真实 credential 参数 | 当前无此 schema；若出现立即 stop | 具体 tool producer + controller |
| 非 Fins tools 当前无 explicit citation | source-unavailable，不猜 | 对应 tool producer |
| real smoke 依赖外部环境 | completion 必须真实通过 | controller 确认 smoke 环境 |
| Issue #177/#178 不在 R03 | 不处理 | 各 issue owner |
| EventLog envelope 仍保存 opaque refs | internal provenance contract | evidence/audit owner |

## 7. Plan Review Conclusion

**PASS-WITH-RISKS**。

计划方向正确，root cause 基于直接代码证据，三片切分合理，owner boundary 清晰，corruption matrix 完整，R01 §11 handoff 消费逐行覆盖。3 个 material findings 均属于"计划文本补充规格化"而非"方案结构性不安全"：

1. **001 (高)**: source projection 机制变更 — 需补充 `_source_projection` 新签名和 raw outcome 传递方式
2. **002 (中)**: Tool Trace `business_source_text/state` — 需补充字段类型定义
3. **003 (中)**: evidence renderer fail closed — 需补充四个 consumer 的统一策略

这些 findings 修正后，计划即可进入 code-generation-ready 状态。无结构性不安全、无过度耦合、无 owner 边界违反、无 deferred scope 泄漏。
