# WU-CM-01 Slice A Code Review - AgentMiMo

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | code review |
| slice | Slice A - Compact Contract Closure |
| design source | `docs/host/design.md` section 24.3 |
| accepted plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| reslice adjudication | `docs/reviews/wu-cm-01-plan-reslice-rereview-controller-adjudication.md` |
| implementation report | `docs/reviews/wu-cm-01-slice-a-implementation-codex.md` |
| reviewer | AgentMiMo |
| review date | 2026-06-04 |

## Verdict

**pass-with-findings**

0 条 blocking finding，3 条 non-blocking finding。实现正确闭合了 Slice A 的 vNext compact contract，符合 design 24.3 和 plan 约束。

## Checklist Summary

| 检查项 | 结果 | 说明 |
|---|---|---|
| vNext compact contract 闭合且符合 design 24.3 | PASS | 输入/输出 dataclass、candidate schema、label section、char cap 全部对齐 design 24.3 |
| 未切换生产旧 compact operation | PASS | `LLMContextCompactor.compact` 保持旧路径；`compact_vnext` 是独立新增入口 |
| 无兼容 wrapper / re-export / lazy import seam | PASS | 无 `hasattr`/`getattr` 探测、无 `Any`、无 lazy import、无旧字段 re-export |
| `current_input_anchor` 不可引用 | PASS | `__post_init__` 校验 anchor_label 不在 `citable_source_labels`；parser 和 accept barrier 都拒绝 C1 |
| label provenance 正确 | PASS | `source_section()` 正确映射 label 到 section；prompt-local label 不暴露 Host provenance |
| fail-closed parser / accept barrier | PASS | 未知/stale/跨 section/缺 label/空文本/非法 enum/anchor 引用 全部拒绝 |
| AGENTS 类型/docstring/分层约束 | PASS | 全部 dataclass frozen+slots；完整中文 docstring；无 `object`/`Any` |
| 测试覆盖边界 | PASS-with-findings | 核心边界有覆盖；见 NF-03 |

## Findings

### NF-01: section allowlist 常量在 llm_compaction.py 和 context_governance.py 重复定义

**严重性**: non-blocking
**类型**: maintainability
**位置**: `dayu/host/llm_compaction.py:131-146`, `dayu/host/context_governance.py:31-46`

**描述**: `_SUMMARY_SOURCE_SECTIONS_VNEXT`、`_FACT_SOURCE_SECTIONS_VNEXT`、`_ANSWER_SOURCE_SECTIONS_VNEXT`、`_FORWARD_SOURCE_SECTIONS_VNEXT`、`_REFERENCE_SOURCE_SECTIONS_VNEXT`、`_DIAGNOSTIC_SOURCE_SECTIONS_VNEXT`、`_STALE_LABEL_PREFIXES_VNEXT` 共 7 组常量在两个模块中各定义一次，内容完全相同。

**直接证据**:

`llm_compaction.py:131-146`:
```python
_SUMMARY_SOURCE_SECTIONS_VNEXT = (
    ConversationCompactLabelSectionVNext.PREVIOUS_COMPACTED_VIEW,
    ConversationCompactLabelSectionVNext.TRACE_MATERIAL,
    ConversationCompactLabelSectionVNext.EVIDENCE_MATERIAL,
    ConversationCompactLabelSectionVNext.ANSWER_MATERIAL,
)
...
_STALE_LABEL_PREFIXES_VNEXT = ("S", "H", "E", "A", "T", "P")
```

`context_governance.py:31-46`:
```python
_SUMMARY_SOURCE_SECTIONS_VNEXT = (
    ConversationCompactLabelSectionVNext.PREVIOUS_COMPACTED_VIEW,
    ...
)
...
_STALE_LABEL_PREFIXES_VNEXT = ("S", "H", "E", "A", "T", "P")
```

**理由**: 两处常量完全相同，未来修改 design 24.3 section allowlist 时必须同步两处，否则 parser 和 accept barrier 的 section 校验会不一致。

**建议修复**: 将 section allowlist 常量抽取到 `compaction.py`（它已经是 vNext type owner），`llm_compaction.py` 和 `context_governance.py` 从 `compaction.py` 导入。这不是兼容 wrapper，而是消除同一 contract 的重复定义。

**后续处理**: 建议作为 Slice A 的 fix 或 Slice B 前置清理。不阻塞当前 gate。

---

### NF-02: `check_conversation_compact_output_vnext` 未进入 `context_governance.__all__`

**严重性**: non-blocking
**类型**: public contract
**位置**: `dayu/host/context_governance.py:832`

**描述**: `__all__` 仍为 `["check_compaction_candidate"]`，未包含新增的 `check_conversation_compact_output_vnext`。该函数已可被 import，但未声明为模块公共 API。

**直接证据**:

`context_governance.py:832`:
```python
__all__ = ["check_compaction_candidate"]
```

`context_governance.py:148-224` 定义了 `check_conversation_compact_output_vnext`。

**理由**: Slice B 的 operation 将直接调用此函数。若不更新 `__all__`，该函数在 `from dayu.host.context_governance import *` 场景下不可见，且与模块公共契约不一致。

**建议修复**: 更新 `__all__` 为 `["check_compaction_candidate", "check_conversation_compact_output_vnext"]`。

**后续处理**: 建议作为 Slice A fix 或 Slice B 前置。不阻塞当前 gate。

---

### NF-03: `conversation_compact_input_vnext_from_material_pack` 未被独立测试覆盖

**严重性**: non-blocking
**类型**: test coverage
**位置**: `dayu/host/compact_material.py:287-314`

**描述**: `conversation_compact_input_vnext_from_material_pack` 是 Slice A 的关键 material 映射入口，将旧 `CompactMaterialPack` 转为 `ConversationCompactInputVNext`。当前测试中该函数只在 `_vnext_input()` helper 中被调用（`test_compaction_contract.py:965`、`test_llm_compaction.py:1073`），但没有针对以下边界的独立测试：

1. `previous_compacted_view` 为 `None`（stable_input 无 fact block）时输出正确
2. `previous_compacted_view` 包含 fact block 时 `evidence_backed_facts` 映射正确
3. `trace_material` 只包含 `RAW_USER_TURN`，不包含 `RAW_ASSISTANT_TURN`
4. `answer_material` 只包含 `RAW_ASSISTANT_TURN`
5. `current_input_anchor` 的 `anchor_label` 确实不在 `citable_source_labels` 中

**直接证据**: `test_compact_material.py` 未包含 `conversation_compact_input_vnext_from_material_pack` 的直接测试。`test_compaction_contract.py` 和 `test_llm_compaction.py` 通过 `_vnext_input()` helper 间接调用，但 helper 使用的 material pack 只有一个 `RAW_ASSISTANT_TURN` history block，未覆盖 `RAW_USER_TURN`、`previous_compacted_view` 有 fact、`evidence_material` 映射等边界。

**理由**: material 映射的正确性是 Slice A 闭合的核心。若 `_trace_material_vnext` 误把 `RAW_ASSISTANT_TURN` 也收入 trace，或 `_previous_compacted_view_vnext` 误把非 fact block 收入，后续 Slice 的 prompt assembly 会静默出错。

**建议修复**: 在 `test_compact_material.py` 中新增以下测试：
- `test_conversation_compact_input_vnext_maps_user_turn_to_trace`
- `test_conversation_compact_input_vnext_maps_assistant_turn_to_answer`
- `test_conversation_compact_input_vnext_maps_evidence_to_evidence_material`
- `test_conversation_compact_input_vnext_previous_view_only_has_fact_blocks`
- `test_conversation_compact_input_vnext_anchor_label_not_citable`

**后续处理**: 建议作为 Slice A fix。不阻塞当前 gate，但应在 Slice B 前补齐。

## Direct Evidence Summary

### vNext contract 闭合性

- `ConversationCompactInputVNext` (`compaction.py:1124-1234`) 顶层字段固定为 `schema_version`、`previous_compacted_view`、`trace_material`、`evidence_material`、`answer_material`、`current_input_anchor`、`instruction`，与 design 24.3 完全一致。
- `ConversationCompactOutputVNext` (`compaction.py:1569-1630`) 顶层字段固定为 `schema_version`、`session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`、`diagnostics`，与 design 24.3 完全一致。
- schema version 常量 `CONVERSATION_COMPACT_INPUT_SCHEMA_VERSION_VNEXT = "conversation_compact_input_v1"` 和 `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT = "conversation_compact_output_v1"` 与 design 24.3 一致。
- 所有 candidate 子类型（`SessionSummaryCandidateVNext`、`EvidenceBackedFactCandidateVNext`、`AnswerAnchorCandidateVNext`、`ForwardIntentCandidateVNext`、`ReferenceContinuityCandidateVNext`、`CompactCandidateDiagnosticVNext`）字段与 design 24.3 candidate schema 一致。

### 未切换生产旧 compact operation

- `LLMContextCompactor.compact()` (`llm_compaction.py:244-277`) 仍使用旧 `CompactionRequest` -> `CompactionCandidate` 路径。
- `LLMContextCompactor.compact_vnext()` (`llm_compaction.py:279-319`) 是独立新增方法，不调用旧 parser。
- `check_compaction_candidate()` (`context_governance.py:49-145`) 保持旧 quality check 路径。
- `check_conversation_compact_output_vnext()` (`context_governance.py:148-224`) 是独立新增函数。
- `__all__` 未添加新函数（见 NF-02），但这不影响功能。

### 无兼容 wrapper / re-export / lazy import

- 无 `hasattr`/`getattr` 用于新旧 contract 桥接。
- 无 `Any` 类型。
- 无 lazy import。
- 无旧字段 re-export。
- `fake_compaction.py` 中 `FakeConversationCompactorVNext` 是独立类，不继承 `ContextCompactor`，不提供旧 `compact` 方法的 wrapper。

### current_input_anchor 不可引用

- `ConversationCompactInputVNext.__post_init__` (`compaction.py:1170-1172`) 显式校验 `current_input_anchor.anchor_label in self.citable_source_labels` 时 raise。
- `citable_source_labels` 属性 (`compaction.py:1174-1190`) 不包含 anchor_label。
- `source_section()` (`compaction.py:1192-1216`) 对 anchor_label 返回 `CURRENT_INPUT_ANCHOR`。
- parser `_validate_vnext_labels` (`llm_compaction.py:838-868`) 检测到 `CURRENT_INPUT_ANCHOR` section 时 raise。
- accept barrier `_collect_vnext_label_issues` (`context_governance.py:287-319`) 检测到 `CURRENT_INPUT_ANCHOR` section 时收集 `CURRENT_INPUT_ANCHOR_CITED` issue。
- 测试 `test_parse_conversation_compact_output_vnext_fails_closed` 的 `current_anchor` case 和 `test_check_conversation_compact_output_vnext_rejects_label_contract_violations` 的 C1 case 都验证了该行为。

### label provenance

- `conversation_compact_input_vnext_from_material_pack` (`compact_material.py:287-314`) 从旧 material pack 构造 vNext input，保留 prompt-local label，不暴露 Host provenance。
- `_trace_material_vnext` (`compact_material.py:1769-1786`) 只映射 `RAW_USER_TURN` 到 trace。
- `_answer_material_vnext` (`compact_material.py:1789-1800`) 只映射 `RAW_ASSISTANT_TURN` 到 answer。
- `_evidence_material_vnext` (`compact_material.py:1803-1821`) 映射 evidence blocks 到 evidence material。
- `_previous_compacted_view_vnext` (`compact_material.py:1844-1860`) 只映射 `EVIDENCE_BACKED_FACT` kind block 到 `evidence_backed_facts`。
- `to_json()` 方法不输出 `canonical_source_refs`、`content_digest`、`accepted_evidence_id` 等 Host provenance 字段。

### fail-closed parser / accept barrier

Parser (`parse_conversation_compact_output_vnext`, `llm_compaction.py:555-584`):
- 空文本 -> `LLMCompactionProposalError("proposal is empty")`
- 非 JSON -> `LLMCompactionProposalError("not valid JSON")`
- 缺必填 key -> `LLMCompactionProposalError("missing required key")`
- schema_version 不匹配 -> `ValueError` -> `LLMCompactionProposalError("schema invalid")`
- 未知 label -> `ValueError("unknown source label")`
- stale label -> `ValueError("stale source label")`
- 跨 section label -> `ValueError("cross-section label")`
- current anchor 被引用 -> `ValueError("cites current input anchor")`
- 缺 source label -> `ValueError("missing source label")`
- 空文本 -> `ValueError("must be non-empty")` (by `_require_bounded_non_empty_text`)
- 非法 enum -> `ValueError("is not a valid ...")` (by StrEnum)

Accept barrier (`check_conversation_compact_output_vnext`, `context_governance.py:148-224`):
- 同样的 label 校验逻辑，收集为 `CompactQualityIssueVNext` issue 而非 raise。
- 每个 candidate 类型有独立的 section allowlist。

### 类型/docstring/分层约束

- 所有 vNext dataclass 使用 `frozen=True, slots=True`。
- 所有函数有完整中文 docstring，包含 `:param:`、`:returns:`、`:raises:`。
- 无 `object`、`Any` 类型。
- 无 untyped 参数或返回值。
- 分层正确：`compaction.py`(contract) -> `compact_material.py`(material) -> `llm_compaction.py`(parser) -> `context_governance.py`(accept barrier)。

## Residual Risks

- Slice A 的 vNext contract 已闭合但未接入 production operation；这是 intentional，owner 是 Slice B。
- section allowlist 常量重复（NF-01）需要在 Slice B 前清理，否则两处修改可能不一致。
- material 映射的独立测试（NF-03）需要在 Slice B 前补齐。
- `check_conversation_compact_output_vnext` 的 `__all__` 导出（NF-02）需要在 Slice B 前修正。
