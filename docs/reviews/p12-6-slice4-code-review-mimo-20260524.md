# P12.6 Slice 4 Code Review — AgentMiMo

Reviewer: AgentMiMo
Date: 2026-05-24
Base: e89e702 (gateflow: accept P12.6 slice 3)
Scope: workspace diff for P12.6 Slice 4; excluded `docs/host/implementation-control.md`

## Verdict

**PASS**

## Reviewed Files

- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/config/prompts/scenes/conversation_compaction.md`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_contract.py`

## Validation Summary

| Check | Result |
|---|---|
| Prompt renderer 只消费 material pack typed view，只渲染四个 sections | PASS |
| Prompt / prompt assets 不含 Host ledger 字段 | PASS |
| JSON parser 只接受 prompt-local labels 并映射到 canonical refs | PASS |
| Unknown labels / cross-section labels / fact 无 evidence label fail closed | PASS |
| Quality checker 拒绝 episode summary 把 evidence label 升级成 fact ref | PASS |
| Architecture: 不改 ConfigLoader/ScenePrepare schema、不改 public API、不引入 Any/object/getattr/hasattr/lazy seam | PASS |
| Tests 覆盖 plan 指定 6 项 | PASS |
| README 无需更新 | PASS |

## Review Focus Findings

### 1. Prompt renderer 只消费 material pack typed view，且只渲染四个 sections

`_compaction_request_prompt_block` (`llm_compaction.py:348-364`) 简化为直接 `json.dumps(request.llm_material_json(), ...)`。删除了旧的 `trigger_source:` 行、`material_pack:` 包装和 `_indented_content_lines` / `_refs_text` helper。旧代码渲染 `trigger_source` 与 `material_pack` wrapper，新代码只输出 `llm_material_json()` 的四个 section JSON。

`test_prompt_renders_material_pack_without_ledger_dump` (`test_llm_compaction.py:150-192`) 断言四个 section key 存在且旧 wrapper 不存在。

**结果：PASS**

### 2. Prompt / prompt assets 不含 Host ledger 字段

`conversation_compaction.md` 已从 "accepted evidence refs" 改为 "prompt-local evidence labels"。

`conversation_compaction_user.md` 新增 `preservation_evidence` schema，全部使用 prompt-local labels（`material_labels`、`evidence_labels`、`start_material_label`、`end_material_label`）。

`test_prompt_renders_material_pack_without_ledger_dump` 断言以下字段不在 prompt 中：`accepted_evidence_envelopes`、`compact_raw_context`、`input_event_refs`、`payload_digest`、`payload_ref`、`payload:accepted-1`、`event-tool-result-1`、`event-tool-call-1`、`memory_snapshot_cursor`、`policy_snapshot`、`outcome_digest`、`canonical_source_refs`。

`test_prompt_does_not_render_accepted_evidence_envelope_metadata` (`test_llm_compaction.py:196-230`) 额外断言 envelope 的 `producer_event_ref`、`tool_call_id`、`normalized_arguments_digest`、`semantic_input_digest`、`payload_ref`、`payload_digest`、`outcome_digest` 均不出现在 prompt 中。

**结果：PASS**

### 3. JSON parser 只接受 prompt-local labels，并正确映射到 canonical refs 后构造 CompactionCandidate

所有 label 消费路径统一通过 `_provenance_entry_for_label` (`llm_compaction.py:831-854`)：
1. 从 `provenance_map` 查找 entry（未知 label → `ValueError`）
2. 校验 `entry.section in allowed_sections`（跨 section → `ValueError`）
3. 调用 `validate_material_label(label, entry.section)` 校验格式（格式非法 → `ValueError`）

`_canonical_refs_for_labels` (`llm_compaction.py:769-795`) 允许所有四个 section。
`_canonical_evidence_refs_for_labels` (`llm_compaction.py:798-828`) 只允许 `EVIDENCE_INPUT` section。

`_preservation_evidence` (`llm_compaction.py:1047-1093`) 从 proposal JSON 读取 `material_labels` 和 `evidence_labels`，分别通过 `_canonical_refs_for_labels` 和 `_canonical_evidence_refs_for_labels` 映射后构造 `PreservationEvidence`。

`_optional_input_range` (`llm_compaction.py:1096-1131`) 对 `start_material_label` / `end_material_label` 同样走 label → canonical ref 映射。

`test_parser_maps_prompt_local_evidence_label_to_canonical_ref` (`test_llm_compaction.py:293-330`) 断言 `E1` → `evidence:accepted-1` 映射正确。

**结果：PASS**

### 4. Unknown labels / cross-section labels / fact 无 evidence label / minimum preserve source refs 非 material label / finish_reason=length / 非 final / 空 summary 是否 fail closed

- **Unknown label**: `test_parser_rejects_unknown_or_cross_section_labels` (`test_llm_compaction.py:526-549`) — `preserved_material_labels=("C1", "missing-label")` → `LLMCompactionProposalError("unknown label")`
- **Cross-section label**: 同测试 — `fact_evidence_refs=("H1",)` → `LLMCompactionProposalError("section mismatch")`
- **Fact 无 evidence label**: `test_fact_candidate_without_evidence_label_rejected` (`test_llm_compaction.py:552-568`) — `fact_evidence_refs=()` → `LLMCompactionProposalError("evidence label")`，由 `require_non_empty=True` 触发
- **Minimum preserve source refs 非 material label**: `test_minimum_preserve_source_refs_must_be_material_labels` (`test_llm_compaction.py:571-593`) — `minimum_preserve_source_labels=("payload:accepted-1",)` → `LLMCompactionProposalError("unknown label")`
- **finish_reason=length**: `test_llm_context_compactor_rejects_truncated_final_output` (`test_llm_compaction.py:636-651`) — `FinishReason.LENGTH` → `LLMCompactionProposalError("truncated")`
- **非 final**: `test_llm_context_compactor_rejects_empty_plain_text_or_non_final_output` (`test_llm_compaction.py:395-432`) — `EngineRunOutcomeFailed` → `LLMCompactionProposalError("runner failed")`
- **空 summary**: 同测试 — `final("   ")` → `LLMCompactionProposalError("proposal is empty")`

**结果：PASS**

### 5. Quality checker 拒绝 episode summary 直接把 evidence label 升级成 fact ref

`_summary_pretends_evidence_backed_fact` (`context_governance.py:185-208`) 新增两个 evidence label intersection 检查：

```python
evidence_labels = set(request.material_pack.evidence_labels)
if len(evidence_labels.intersection(summary.confirmed_fact_refs)) > 0:
    return True
if len(evidence_labels.intersection(summary.proposed_evidence_backed_fact_refs)) > 0:
    return True
```

`test_quality_rejects_summary_confirmed_fact_ref_to_evidence_label` (`test_compaction_contract.py:343-363`) 断言 `confirmed_fact_refs=("E1",)` 被 `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT` 拒绝。

`test_quality_rejects_summary_pretending_to_create_evidence_backed_fact` (`test_compaction_contract.py:298-317`) 覆盖 `proposed_evidence_backed_fact_refs` 路径。

**结果：PASS**

### 6. Architecture

- 不改 ConfigLoader/ScenePrepare schema：diff 中无相关文件
- 不改 public API：`CompactionRequest`、`CompactionCandidate` 等 public shape 未变
- 不引入 Any/object/getattr/hasattr/lazy seam：新代码使用严格类型（`PromptLocalProvenanceEntry`、`CompactMaterialSection` 等），无类型逃逸

**结果：PASS**

### 7. Tests 覆盖 plan 指定 6 项

| Plan 测试项 | 实际测试 | 文件:行 |
|---|---|---|
| `test_prompt_renders_material_pack_without_ledger_dump` | `test_prompt_renders_material_pack_without_ledger_dump` | `test_llm_compaction.py:150` |
| `test_prompt_does_not_render_accepted_evidence_envelope_metadata` | `test_prompt_does_not_render_accepted_evidence_envelope_metadata` | `test_llm_compaction.py:196` |
| `test_parser_maps_prompt_local_evidence_label_to_canonical_ref` | `test_parser_maps_prompt_local_evidence_label_to_canonical_ref` | `test_llm_compaction.py:293` |
| `test_parser_rejects_unknown_or_cross_section_labels` | `test_parser_rejects_unknown_or_cross_section_labels` | `test_llm_compaction.py:526` |
| `test_fact_candidate_without_evidence_label_rejected` | `test_fact_candidate_without_evidence_label_rejected` | `test_llm_compaction.py:552` |
| `test_minimum_preserve_source_refs_must_be_material_labels` | `test_minimum_preserve_source_refs_must_be_material_labels` | `test_llm_compaction.py:571` |

额外新增测试：
- `test_quality_rejects_summary_confirmed_fact_ref_to_evidence_label` (`test_compaction_contract.py:343`) — 覆盖 evidence label 升级防线

所有测试通过 monkeypatch 或 `replace()` 构造非法输入，断言 fail closed 行为，真实防回归。

**结果：PASS**

### 8. README 无需更新

本 Slice 只收紧内部 compactor parser、prompt asset schema 与 quality gate；无用户命令、公共入口、配置 schema 或测试分层变化。`dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md` 均无需更新。

**结果：PASS**

## Findings

### F1. [LOW] `_preservation_evidence` 硬编码 `memory_snapshot_cursor=None`

- 文件：`dayu/host/llm_compaction.py:1084`
- 现状：`memory_snapshot_cursor=None` 写死
- 设计要求：`docs/host/design.md §25` 要求 preservation evidence 记录 "memory snapshot cursor"
- 影响：quality checker `_single_evidence_anchor_valid` (`context_governance.py:274-277`) 对 `memory_snapshot_cursor` 的校验分支永远走 `None` 路径，无法验证 cursor 一致性
- 严重度：LOW — 属于 Slice 1-3 遗留（Codex review 同一问题），不阻塞 Slice 4 parser / quality gate 收紧目标
- 建议：Slice 5 governance 接线时从 `request.memory_snapshot_cursor` 传入，或在 proposal schema 中要求 LLM 输出 cursor label

### F2. [LOW] `_compaction_request_prompt_block` 删除了 `_indented_content_lines` 和 `_refs_text`，但 `_refs_text` 在模块内无其他调用点

- 文件：`dayu/host/llm_compaction.py`
- 现状：`_indented_content_lines` 和 `_refs_text` 被完整删除
- 影响：无 — 两个函数是模块私有且已无调用者
- 严重度：LOW — 清洁删除，无遗留引用

### F3. [INFO] `context_governance.py` docstring 从 "Phase 10 Slice 2" 更新为通用描述

- 文件：`dayu/host/context_governance.py:3`
- 现状：`本模块只实现 Phase 10 Slice 2 的 compaction candidate quality check` → `本模块实现 Host compaction candidate quality check`
- 影响：无功能变化，docstring 更准确
- 严重度：INFO

## Architecture Compliance

- 依赖方向 `UI -> Service -> Host -> Engine`：未违反
- `dayu.host` 不 import `dayu.service` / `dayu.ui` / `dayu.fins`：未违反
- 不新增 `Any` / `object` / `extra payload` / lazy seam：未违反
- 不修改 Host public API / `OpenHostOptions` / `SubmitFollowupRequest`：未违反
- 不修改 ConfigLoader / ScenePrepare schema：未违反
- 函数 docstring 完整：新增 / 修改函数均有中文 docstring 含参数、返回值、异常

## Residual Risks

1. `memory_snapshot_cursor` 在 `PreservationEvidence` 中硬编码 `None`，quality checker 的 cursor 一致性校验分支不可达。归 Slice 5 governance 接线。
2. 本 Slice 不实现 proactive / reactive durable compaction operation 接线与 multi-pass merge，按计划归 Slice 5。
3. `confirmed_fact_refs` 在 quality checker 中只校验 `issubset(request.evidence_backed_fact_refs)`，不校验是否为真实 evidence-backed fact。但 parser 侧 `_bounded_known_refs` 已确保 LLM 不能输出 `request.evidence_backed_fact_refs` 之外的字符串，且 evidence label intersection 检查提供 defense-in-depth。风险可控。
