# WU-SEMANTIC-OWNERSHIP-01 P1-A Plan Review — AgentDS

## Metadata

- Review type: adversarial plan review
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-a-plan.md`
- Codex plan-gate summary: `docs/reviews/wu-semantic-ownership-01-p1-a-plan-codex.md`
- Umbrella plan: `docs/host/wu-semantic-ownership-01-umbrella-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-plan-review-controller-adjudication.md`
- Controller re-review: `docs/reviews/wu-semantic-ownership-01-plan-rereview-controller-adjudication.md`
- Review date: 2026-07-09
- Reviewer: AgentDS

## Conclusion

**`pass-with-risks`**

Plan 的动机、owner boundary、selected contract approach、implementation slices 和 consumer migration checklist 基本成立。未发现 blocking 级别的设计错误。但有 3 个 HIGH severity findings 需要在 implementation 前收窄，以及若干 MEDIUM 和 LOW observations。

---

## Findings

### F01 [HIGH] S2 Consumer Migration 未涵盖 `_tool_request_summary_from_tool_result()` 的完整替代策略

- **Severity**: HIGH
- **Evidence**: `dayu/host/tool_trace.py:1283-1334`
- **违反**: Consumer migration completeness (Section 6 S2 + Section 8 checklist)
- **Required fix**: Plan Section 6 S2 的 "允许改动" 列表中 Tool Trace 项写的是 "`TOOL_RESULT_ACCEPTED` request/result summary 由 projection helper 输入"，但 `_tool_request_summary_from_tool_result()` 不只是 query/status/source ——它还从 `TOOL_CALL_REQUESTED` request atom 中重建完整工具参数摘要（arguments_json、redacted_arguments、arguments_summary_text、query_text），并做 tool_call_id/tool_name/arguments_digest identity match 校验。这些属于 Tool Trace 专属的 bounded rendering + redaction，不宜简单地放进通用的 accepted-result projection helper。

  必须在 Plan S2 中明确裁决以下二选一：
  - **(A)** projection helper 承担 query_text + status + source_text 的基础投影，Tool Trace 保留 `_tool_request_summary_from_tool_result()` 但改为从 projection helper 输入 query/status/source 基础字段，只自己处理 arguments 的有界渲染和脱敏；
  - **(B)** projection helper 直接提供完整的 `ToolTraceRequestSummary` 和 `ToolTraceResultSummary` typed view，Tool Trace 只做 format。

  选项 A 更符合 plan 自身声明的 "projection helper 不成为 lossy result preview" 原则，也避免把 Tool Trace 特有的 bounded rendering 策略耦合到通用 projection contract 中。

- **Stop condition 触发风险**: 如果裁决选 A 但 Tool Trace 的 arguments 重建仍需要独立 back-query request atom，那 `_tool_request_summary_from_tool_result()` 不能完全消除，plan 的 consumer migration grep 检查（Section 9 validation）会失败。必须提前在 plan 中明确该函数的处理方式。

---

### F02 [HIGH] Read API 与 projection helper 的 status 域不一致，plan 未区分 preview vs canonical event class

- **Severity**: HIGH
- **Evidence**: `dayu/host/read_api.py:1210-1239`、`dayu/host/_event_payload.py:347-386`、`dayu/host/waiting.py:1221`
- **违反**: Owner boundary (Section 3) / selected contract approach (Section 4)
- **Required fix**:

  当前 read_api 的 `_tool_result_accepted_activity()` 只读取 `outcome_kind` 字段。该字段**仅存在于 PREVIEW event class 的 payload 中**，由 `waiting.py:1221`（`outcome_kind=payload_plan.resolution_kind`）和 `_event_payload.py:347`（wait-result preview payload helper）写入。CANONICAL_FACT 的 `TOOL_RESULT_ACCEPTED` payload 不包含 `outcome_kind`，改用 `tool_fact_kind` + `resolution_kind`。

  这意味着：
  - read_api 当前**只对 PREVIEW event 展示 activity**，对 CANONICAL_FACT 的 `TOOL_RESULT_ACCEPTED` 会因 `outcome_kind is None` 而返回 `None`（无 activity 展示）。
  - Plan 说 "Read API activity status 由 projection helper 的 status 输入"，但 projection helper 设计为从 CANONICAL_FACT payload 中读取 `tool_fact_kind`/`resolution_kind`。两者不在同一 event class 上操作。
  - Plan 必须明确裁决以下问题，并在 Section 6 S2 "允许改动" 中记录：
    1. Read API 的 `_tool_result_accepted_activity()` 是否改为消费 CANONICAL_FACT event（通过 projection helper），还是继续只消费 PREVIEW event？
    2. 如果改为消费 canonical event，`_activity_from_row()` 需要新增对 CANONICAL_FACT `TOOL_RESULT_ACCEPTED` 的显式分发，并确保不与现有的 PREVIEW path 冲突。
    3. projection helper 的 `AcceptedToolResultStatus` enum（`completed`/`failed`/`cancelled`/`governed_error`/`lost`/`unknown`）到 read_api 的 `HostActivityStatus`（`COMPLETED`/`FAILED`/`CANCELLED`）的映射关系应在 plan 中写清。

  如果 read_api 保持只消费 PREVIEW event，则 Section 8 checklist 中的 "Read API：tool result activity status / summary 由 projection helper 产生" 应改为 "Read API 不在 P1-A scope 内，或仅校验 read_api 不使用私有 status inference"。

- **Stop condition 触发风险**: 如果在 implementation 阶段才发现 read_api 的 event class 与 projection helper 不一致，会触发 Section 11 stop condition 第 4 条（"有消费者仍需要 wait / poll / runtime 状态"），导致 re-plan。

---

### F03 [HIGH] `_readable_source_text_from_refs()` 上游生产者未被纳入清理范围

- **Severity**: HIGH
- **Evidence**: `dayu/host/compact_material.py:2420-2432`、`dayu/host/compact_pipeline.py:1136-1151`、`dayu/host/run_input.py:3035-3045`
- **违反**: Consumer migration completeness (Section 6 S2)
- **Required fix**:

  当前 source text 的数据流是：
  1. `compact_material.py:_readable_source_text_from_refs()` 把 `OpaqueEvidenceRef` 元组拼接为 `ref_kind:ref_id, ...` 字符串 → 写入 `RunInputMaterialBlock.readable_source_text`
  2. `run_input.py:_llm_facing_evidence_source_text()` 对 `readable_source_text` 做 blacklist 过滤
  3. `compact_pipeline.py:_llm_facing_evidence_source_text()` 做了**完全相同的重复** blacklist 过滤（代码逐字重复，包含同样的 `_is_internal_evidence_source_part()`）

  Plan Section 6 S2 的 "允许改动" 明确说 "RunInputBuilder / compact pipeline 删除重复 `_llm_facing_evidence_source_text()` blacklist 逻辑，改用 helper 已清洗的 readable source"。这是正确的方向。

  但 plan 未明确说明 step 1 的 `_readable_source_text_from_refs()` 如何处理。如果 projection helper 直接产出已清洗的 `readable_source_text`（不再包含 internal refs），那么 `_readable_source_text_from_refs()` 本身就是 source text 的**唯一生产者**，它的逻辑需要迁移到 projection helper 内，或者被 projection helper 的输出替代。

  Section 9 validation 的 grep 命令搜索的是 `_llm_facing_evidence_source_text` 和 `_is_internal_evidence_source_part`，但没有搜索 `_readable_source_text_from_refs`。该函数是 source text 生产链的入口，plan 必须在 Section 6 S2 或 Section 9 中明确该函数的处理方式。

- **Suggested fix**: 在 Section 6 S2 "允许改动" 中增加一条：`compact_material.py` 的 `_readable_source_text_from_refs()` 逻辑迁移到 projection helper，或其输出被 projection helper 替代。在 Section 9 validation grep 命令中增加 `_readable_source_text_from_refs`。

---

### F04 [MEDIUM] Plan 未显式覆盖 Conversation Memory 的 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` fallback 迁移

- **Severity**: MEDIUM
- **Evidence**: `dayu/host/memory.py:1700-1702`、`dayu/host/durable/memory.py:479-503`
- **违反**: Consumer migration completeness (Section 8 checklist)
- **Required fix**:

  当前 Conversation Memory (`memory.py:1700-1702`) 在 `event.evidence_query_text is not None` 时使用它，否则 fallback 到 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`。Durable Memory (`durable/memory.py:456-503`) 的 `_tool_result_query_text()` 在多种缺失条件下返回 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT`。

  Plan Section 8 checklist 说 "Conversation Memory：selected recent evidence 消费 projection query/result/source，不再自建 unavailable 文案"。这意味着 `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 常量本身可能仍然存在（作为 limited-signal 文案），但 Conversation Memory 不应再自己决定何时使用它。Plan 应在 Section 6 S2 "允许改动" 或 Section 8 checklist 中明确说明：
  - Conversation Memory 的 `event.evidence_query_text` 字段是否保留？还是改为从 projection helper 的 `query_text` 字段读取？
  - `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` 常量是否移到 projection helper 模块作为 limited-signal 文案的唯一定义？

---

### F05 [MEDIUM] validation grep 命令缺少对 `source_note` 和 `_readable_source_text_from_refs` 的检查

- **Severity**: MEDIUM
- **Evidence**: Plan Section 9 validation commands L223-225
- **违反**: Validation completeness
- **Required fix**:

  Plan Section 9 的 grep 命令：
  ```
  rg -n "_readable_query_text_from_envelope|_tool_result_query_text|_tool_result_status|def _llm_facing_evidence_source_text|_is_internal_evidence_source_part" dayu/host
  ```
  应增加：
  - `_readable_source_text_from_refs`（source text 上游生产者，见 F03）
  - `source_note`（LLM-facing evidence block 中携带 un-cleaned source 的字段名，`compact_material.py:3363`）

---

### F06 [MEDIUM] Plan 未说明 Tool Trace 的 `_tool_result_status()` 私有 helper 是否完全被替代还是保留为内部实现

- **Severity**: MEDIUM
- **Evidence**: `dayu/host/tool_trace.py:2008-2031`、Plan Section 6 S2
- **违反**: Consumer migration completeness
- **Required fix**:

  `_tool_result_status()` 在 `tool_trace.py` 中被 `_tool_result_summary_from_payload()` (line 1450) 调用，用于构造 Tool Trace cold line 的 result status 字段。它的 fallback 链是 `resolution_kind -> tool_fact_kind -> raw_outcome.kind -> raw_outcome.result.ok`。

  Plan Section 4 说 projection helper 的 `AcceptedToolResultStatus` 封装了 "ordinary `outcome_kind` / `tool_fact_kind` 与 wait-resolution `resolution_kind` 映射"。

  如果 projection helper 产出的 status 已经足够，Tool Trace 的 `_tool_result_summary_from_payload()` 应改为从 projection helper 取 status，`_tool_result_status()` 应被删除（或改为只做 Tool Trace 特有的 bounded text 构造）。Plan 应在 Section 6 S2 中明确 `_tool_result_status()` 是删除还是重构为只消费 projection helper。

---

### F07 [LOW] `InitialEvidenceMaterial` 构造路径在 plan 中被遗漏

- **Severity**: LOW
- **Evidence**: `dayu/host/compact_material.py:673-700`、`dayu/host/compact_material.py:1341-1363`
- **违反**: Consumer migration completeness (Section 6 S2)
- **Required fix**:

  `InitialEvidenceMaterial` 是一个独立于 `_accepted_tool_evidence_delta_blocks()` 的证据构造路径，用于初始 compact material（无既有 compact 上下文时）。它通过 `build_initial_material_pack()` → `_evidence_blocks()` 构造，直接接收 `readable_query_text`、`readable_source_text`、`raw_result_text` 等字段。

  Plan Section 6 S2 的 allowed files 包含 `compact_material.py` 但未显式提及 `build_initial_material_pack()` / `_evidence_blocks()` / `InitialEvidenceMaterial` 的迁移。如果这些路径的调用方（通常是测试 fixture 或 initial session setup）传入的 `readable_query_text` / `readable_source_text` 也是手动构造的，那么它们在 S3 test migration 时也需要改为从 projection helper 派生，否则会形成新的 drift——production path 用 helper，initial path 用手工字段。

  Plan 应在 Section 6 S2 中明确 `InitialEvidenceMaterial` 和 `_evidence_blocks()` 的 query/source 字段是否也需要由 projection helper 输入，或者在 Section 5 "非目标" 中显式排除 initial material path。

---

### F08 [LOW] Durable Memory 的 `evidence_query_text` 字段迁移后需确认 field-level consistency

- **Severity**: LOW
- **Evidence**: `dayu/host/durable/memory.py:117-121`、`dayu/host/durable/memory.py:362`
- **违反**: N/A (observation)
- **Required fix**: 无需改 plan。Implementation 时应确认：

  Durable Memory 的 `AcceptedEvidenceMemoryPayloadView.evidence_query_text` 字段（line 121）当前由 `_tool_result_query_text()` 填充。迁移到 projection helper 后，应确保 Durable Memory 的 `evidence_query_text` 与 Conversation Memory 使用的 query 文本**同源**（都来自 projection helper 的 `query_text`），避免 "durable memory 正确但 conversation memory 错误" 的 drift。

---

## Cross-Reference Verification

### Motivation (Section 1-2)

**Pass**. Plan Section 2 的代码证据分类（producer / validator / projection helper / consumer）与 `rg` 扫描结果一致。已过期 findings 被正确收窄（envelope 已存在、wait-resolution 已携带 envelope/raw outcome、Tool Trace 已有 request pairing）。

### Owner Boundary (Section 3)

**Pass with F02 caveat**. 四层 owner（produce / validate / persist / project）的分配正确。F02 指出了 read_api 与 projection helper 的 event class 不一致，但这属于 plan 的细节缺口而非 owner boundary 错误。

### Selected Contract Approach (Section 4)

**Pass**. 选择新增 sibling projection helper 而非扩展 `AcceptedEvidenceEnvelope` 本体的理由成立。`evidence.py` 模块 docstring 明确声明 envelope "不解析财报业务 source / locator 语义，也不复制 request / query 正文"。把 query/status/source 投影写回 envelope 会混淆 durable truth 与 readable projection。

### Implementation Slices (Section 6)

**Pass with F01/F02/F03 caveats**. 三个 slice 的分解合理（contract → consumer migration → tests/docs/audit）。S1 的 "完成信号" 覆盖了 8 种场景，足够全面。S2 的消费者覆盖完整度见下方 consumer migration checklist 逐项验证。S3 的 cross-consumer equivalence tests 设计正确。

### Consumer Migration Completeness Checklist (Section 8)

逐项验证：

| Consumer | 覆盖状态 | 证据 | 备注 |
|---|---|---|---|
| Tool Trace | **Partial** | Section 8 ✓, Section 6 S2 ✓ | F01: `_tool_request_summary_from_tool_result()` 替代策略未明确 |
| Read API | **Partial** | Section 8 ✓, Section 6 S2 ✓ | F02: preview vs canonical event class 未区分 |
| Durable Memory | **Covered** | Section 8 ✓ | F08: field-level consistency observation |
| Conversation Memory | **Covered** | Section 8 ✓ | F04: `ACCEPTED_EVIDENCE_QUERY_UNAVAILABLE_TEXT` fallback migration 细节 |
| RunInputBuilder | **Covered** | Section 8 ✓ | |
| CompactMaterial | **Covered** | Section 8 ✓ | F03: `_readable_source_text_from_refs()` 上游未显式覆盖 |
| Compact pipeline | **Covered** | Section 8 ✓ | F03 同源 |
| Tests | **Covered** | Section 8 ✓ | F07: `InitialEvidenceMaterial` 路径需确认 |

### Validation Commands (Section 9)

**Pass with F05 caveats**. 测试命令覆盖了 focused tests 和受影响 consumer tests。grep 命令应增加 `_readable_source_text_from_refs` 和 `source_note`（F05）。

### README / Design Triggers (Section 10)

**Pass**. 正确遵循了 CLAUDE.md 的 README 更新触发规则。新增 helper 如果只是把既有 design 代码化则可不更新 design.md，如果改变 public contract 则必须先更新 design.md。

### Stop Conditions (Section 11)

**Pass**. 4 个 stop condition 覆盖了 schema change、source classification 不可判定、bounded rendering 冲突、owner boundary 错误。F02 发现的情况如果 implementation 时才暴露，会触发 stop condition 4。

### Propagation Audit Plan (Section 12)

**Pass**. 9 个 checkpoint 覆盖了从产生到 LLM 可见输出的完整链路。

---

## Residual Risks (beyond plan Section 11)

| # | Risk | Owner | Mitigation |
|---|---|---|---|
| R01 | Tool Trace result details 的有界渲染（`_TOOL_TRACE_RESULT_TEXT_MAX_CHARS=1600`）需要在 projection helper 的通用投影与 Tool Trace 专属 bounded rendering 之间分界 | Implementation | Plan 已有提及，建议在 S1 完成后先确认分界线再进入 S2 |
| R02 | `source_refs` / `locator_refs` 当前生产路径大多为空（plan 已承认），projection helper 的 source projection 可能暂时只产出 fallback 文本 | Later producer WU | Plan 已列为 residual risk，无新增内容 |
| R03 | `payolad_resolution.py` 中的 `tool_call_request_atoms()` 和 `event_payload_object_for_result_ref()` 目前被多个消费者用于 back-query——这些函数本身不是投影消费者，但 migration 后它们的使用可能减少，应确认没有 orphaned helper | Implementation | 建议在 Section 9 validation 中增加对 `tool_call_request_atoms` 调用点的检查 |

---

## Open Questions

1. **Q1**: `dayu/host/payload_resolution.py` 的 `tool_call_request_atoms()` 被 `durable/memory.py` 的 `_tool_result_query_text()` 和 `compact_material.py` 的 `_readable_query_text_from_envelope()` 同时调用。projection helper 替代这两个函数后，`tool_call_request_atoms()` 是否还会被其他路径使用？如果不会，它是否也应被标记为 deprecated/internal？

2. **Q2**: 如果 wait-resolution `TOOL_RESULT_ACCEPTED` 的 `raw_tool_outcome` 为 `None`（工具结果 lost 但 Host 仍 accept），projection helper 的 `result_text` 应产出什么？是 limited-signal 还是空字符串？这影响 Tool Trace / Memory / CompactMaterial 对该状态的一致性展示。

3. **Q3**: Plan Section 4 建议的接口输入为 `HostTransaction`、`EventLogStore`、`TOOL_RESULT_ACCEPTED` row。这是合理的最小输入。但如果 future WU 需要在无 transaction 上下文（如 offline analysis / test fixture）中构造 projection，是否需要额外的 factory 或 builder？当前 plan 不需要回答此问题，但建议在 S1 implementation 时考虑 projection helper 的 testability。

---

## Summary

| Dimension | Verdict |
|---|---|
| 动机成立 | ✓ |
| 旧 finding 收窄正确 | ✓ |
| Owner boundary 正确 | ✓ (F02 caveat) |
| Contract approach 成立 | ✓ |
| Implementation slices code-generation-ready | ✓ (F01/F02/F03 需先收窄) |
| Consumer migration checklist 完整 | Partial (F01/F02/F03/F04) |
| Validation commands 充分 | Partial (F05) |
| README/design triggers 正确 | ✓ |
| Stop conditions 充分 | ✓ |
| Propagation audit 充分 | ✓ |
