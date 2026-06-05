# WU-CM-01 Slice A Code Review — AgentDS

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | code review |
| slice | Slice A - Compact Contract Closure |
| reviewer | AgentDS |
| branch | `phaseflow/wu-cm-01` |
| design source | `docs/host/design.md` §24.3, §24.7 |
| accepted plan | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| implementation report | `docs/reviews/wu-cm-01-slice-a-implementation-codex.md` |
| prior adjudications | `docs/reviews/wu-cm-01-plan-reslice-fix-codex.md`, `docs/reviews/wu-cm-01-plan-reslice-rereview-controller-adjudication.md` |

## Verdict

**pass-with-findings** — 0 blocking findings, 3 non-blocking findings, 0 blocking open questions.

Slice A contract closure 的核心语义正确：vNext compact I/O dataclass 与 design 24.3 对齐，label provenance mapping 完整，current_input_anchor 不可引用，parser 与 accept barrier 均为 fail-closed，旧 production operation 未被切换，无 compatibility wrapper/re-export/lazy import seam。100 tests 全部通过，pyright 0 errors。

三条 non-blocking findings 涉及模块导出完整性、重复常量与 `previous_compacted_view` 构造完备性，均可在 Slice B 前修复或标记为 deferred。

## Findings

### F1 (non-blocking): `check_conversation_compact_output_vnext` 未在 `__all__` 导出

- **文件**: `dayu/host/context_governance.py:832`
- **证据**: `__all__ = ["check_compaction_candidate"]` — 只导出了旧 `check_compaction_candidate`，未导出 `check_conversation_compact_output_vnext`。
- **影响**: 函数是 public API，tests 已通过 `from dayu.host.context_governance import check_conversation_compact_output_vnext` 直接引用，但模块级 `__all__` 缺失会导致 IDE 自动补全、文档生成与 import * 消费者看不到该入口。
- **建议修复**: 在 `context_governance.py:832` 将 `__all__` 改为 `["check_compaction_candidate", "check_conversation_compact_output_vnext"]`。
- **阻塞性判断**: 不影响编译、测试、pyright 与运行时行为，不阻塞 Slice B。

### F2 (non-blocking): `_STALE_LABEL_PREFIXES_VNEXT` 与 `_looks_like_stale_vnext_label` 跨模块重复

- **文件**: `dayu/host/llm_compaction.py:146,878` 与 `dayu/host/context_governance.py:46,329`
- **证据**: 
  - `_STALE_LABEL_PREFIXES_VNEXT = ("S", "H", "E", "A", "T", "P")` 在两个模块中完全重复。
  - `_looks_like_stale_vnext_label()` 函数逻辑完全一致——都通过 `any(label.startswith(prefix) for prefix in _STALE_LABEL_PREFIXES_VNEXT)` 判断。
- **影响**: 这是 parser 层与 accept barrier 层的同一语义规则的两次独立定义。当前值相同因此行为一致，但若未来 stale label 判定规则变化（如新增/移除 prefix），必须在两处同步修改，存在 drift 风险。
- **建议修复**: 将 `_STALE_LABEL_PREFIXES_VNEXT` 与 `_looks_like_stale_vnext_label` 提升为 `dayu/host/compaction.py` 的模块级公开常量/函数，两个 consumer 模块统一 import。
- **阻塞性判断**: 当前值完全相同，不产生行为差异。属于代码组织层面的非阻塞改进。

### F3 (non-blocking): `_previous_compacted_view_vnext` 仅映射 EVIDENCE_BACKED_FACT，不携带 session_summary、answer_anchors、forward_intents、reference_continuity_items

- **文件**: `dayu/host/compact_material.py:1844-1860`
- **证据**: `_previous_compacted_view_vnext()` 只从旧 stable input blocks 中提取 `EVIDENCE_BACKED_FACT` 类型的 block 映射为 `ReadableFactItemVNext`，`session_summary`、`answer_anchors`、`forward_intents`、`reference_continuity_items` 全部硬编码为 `None` 或空 tuple。
- **影响**: 当前 Slice A 的 `previous_compacted_view` 只能表达 fact 语义，无法表达 roll-forward 场景中的 summary / anchor / intent / continuity。这限制了 `conversation_compact_input_vnext_from_material_pack` 在 compact roll-forward（design 24.1 的 rolling compacted view）场景中的可用性。
- **缓解**: implementation report 已说明 "Previous compacted view materialization is minimal"，且在 Slice A 范围内该 helper 的 consumers 仅为 contract tests，不影响生产 operation。
- **建议**: Slice B/C 实现 compact operation event 与 memory projection 时，必须将 `_previous_compacted_view_vnext` 的数据源从旧 stable blocks 切换为 `ConversationMemorySnapshotVNext` 的 typed projection view，完整填充五类 previous view 字段。
- **阻塞性判断**: 此限制与 Slice A 的设计意图一致（"此 slice 只允许新增未接线或局部接线的 vNext compact contract"），不阻塞当前 slice。

## Contract Compliance Verification

### vNext Compact Input (design 24.3)

| design 字段 | 实现字段 | 状态 |
|---|---|---|
| `schema_version: "conversation_compact_input_v1"` | `CONVERSATION_COMPACT_INPUT_SCHEMA_VERSION_VNEXT = "conversation_compact_input_v1"` | pass |
| `previous_compacted_view?: CompactReadableView` | `previous_compacted_view: CompactReadableViewVNext \| None` | pass |
| `trace_material: list[TraceReadableItem]` | `trace_material: tuple[TraceReadableItemVNext, ...]` | pass |
| `evidence_material: list[EvidenceReadableItem]` | `evidence_material: tuple[EvidenceReadableItemVNext, ...]` | pass |
| `answer_material: list[AnswerReadableItem]` | `answer_material: tuple[AnswerReadableItemVNext, ...]` | pass |
| `current_input_anchor: CurrentInputAnchor` | `current_input_anchor: CurrentInputAnchorVNext` | pass |
| `instruction: CompactInstruction` | `instruction: CompactInstructionVNext` | pass |

### vNext Compact Output (design 24.3)

| design 字段 | 实现字段 | 状态 |
|---|---|---|
| `schema_version: "conversation_compact_output_v1"` | `CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT = "conversation_compact_output_v1"` | pass |
| `session_summary: SessionSummaryCandidate \| null` | `session_summary: SessionSummaryCandidateVNext \| None` | pass |
| `evidence_backed_facts: list[EvidenceBackedFactCandidate]` | `evidence_backed_facts: tuple[EvidenceBackedFactCandidateVNext, ...]` | pass |
| `answer_anchors: list[AnswerAnchorCandidate]` | `answer_anchors: tuple[AnswerAnchorCandidateVNext, ...]` | pass |
| `forward_intents: list[ForwardIntentCandidate]` | `forward_intents: tuple[ForwardIntentCandidateVNext, ...]` | pass |
| `reference_continuity_items: list[ReferenceContinuityCandidate]` | `reference_continuity_items: tuple[ReferenceContinuityCandidateVNext, ...]` | pass |
| `diagnostics: list[CompactCandidateDiagnostic]` | `diagnostics: tuple[CompactCandidateDiagnosticVNext, ...]` | pass |

### Candidate sub-fields mapping

| design | 实现 | 状态 |
|---|---|---|
| `SessionSummaryCandidate.summary_text: str` | `summary_text: str` | pass |
| `SessionSummaryCandidate.source_labels: list[str]` | `source_labels: tuple[str, ...]` | pass |
| `EvidenceBackedFactCandidate.claim_text: str` | `claim_text: str` | pass |
| `EvidenceBackedFactCandidate.evidence_labels: list[str]` | `evidence_labels: tuple[str, ...]` | pass |
| `EvidenceBackedFactCandidate.evidence_kind: "tool_result" \| "tool_source_text" \| "accepted_evidence_material"` | `FactEvidenceKindVNext` with same 3 values | pass |
| `EvidenceBackedFactCandidate.source_labels?: list[str]` | `source_labels: tuple[str, ...] = ()` (optional, defaults to empty) | pass |
| `AnswerAnchorCandidate.anchor_title: str` | `anchor_title: str` | pass |
| `AnswerAnchorCandidate.anchor_items: list[AnswerAnchorChild]` | `anchor_items: tuple[AnswerAnchorChildVNext, ...]` | pass |
| `AnswerAnchorCandidate.answer_source_labels: list[str]` | `answer_source_labels: tuple[str, ...]` | pass |
| `AnswerAnchorChild.display_text: str` | `display_text: str` | pass |
| `AnswerAnchorChild.ordinal?: int` | `ordinal: int \| None = None` | pass |
| `ForwardIntentCandidate.intent_type: "open_question" \| "pending_clarification" \| "pending_user_visible_task" \| "next_step_note"` | `ForwardIntentTypeVNext` with same 4 values | pass |
| `ForwardIntentCandidate.text: str` | `text: str` | pass |
| `ForwardIntentCandidate.status: "open" \| "blocked" \| "superseded"` | `ForwardIntentStatusVNext` with same 3 values | pass |
| `ForwardIntentCandidate.source_labels: list[str]` | `source_labels: tuple[str, ...]` | pass |
| `ReferenceContinuityCandidate.text: str` | `text: str` | pass |
| `ReferenceContinuityCandidate.reason: "local_reference" \| "ordinal_reference" \| "ellipsis_recovery" \| "recent_state"` | `ReferenceContinuityReasonVNext` with same 4 values | pass |
| `ReferenceContinuityCandidate.source_labels: list[str]` | `source_labels: tuple[str, ...]` | pass |
| `CompactCandidateDiagnostic.code: str` | `code: str` | pass |
| `CompactCandidateDiagnostic.text: str` | `text: str` | pass |
| `CompactCandidateDiagnostic.source_labels?: list[str]` | `source_labels: tuple[str, ...] = ()` | pass |

### Enum completeness

| Enum | design 24.3 values | 实现 | 状态 |
|---|---|---|---|
| `TraceReadableKindVNext` | `user_input`, `assistant_final_answer`, `user_visible_run_state` | 完全对齐 | pass |
| `FactEvidenceKindVNext` | `tool_result`, `tool_source_text`, `accepted_evidence_material` | 完全对齐 | pass |
| `ForwardIntentTypeVNext` | `open_question`, `pending_clarification`, `pending_user_visible_task`, `next_step_note` | 完全对齐 | pass |
| `ForwardIntentStatusVNext` | `open`, `blocked`, `superseded` | 完全对齐 | pass |
| `ReferenceContinuityReasonVNext` | `local_reference`, `ordinal_reference`, `ellipsis_recovery`, `recent_state` | 完全对齐 | pass |

### Label section allowlist

| candidate type | label field | 允许 section | 实现 | 状态 |
|---|---|---|---|---|
| `SessionSummaryCandidateVNext` | `source_labels` | PREVIOUS_COMPACTED_VIEW, TRACE, EVIDENCE, ANSWER | `_SUMMARY_SOURCE_SECTIONS_VNEXT` | pass |
| `EvidenceBackedFactCandidateVNext` | `evidence_labels` | EVIDENCE only | `_FACT_SOURCE_SECTIONS_VNEXT = (EVIDENCE,)` | pass |
| `EvidenceBackedFactCandidateVNext` | `source_labels` (optional) | EVIDENCE only | `_FACT_SOURCE_SECTIONS_VNEXT`, allow_empty=True | pass |
| `AnswerAnchorCandidateVNext` | `answer_source_labels` | ANSWER only | `_ANSWER_SOURCE_SECTIONS_VNEXT = (ANSWER,)` | pass |
| `ForwardIntentCandidateVNext` | `source_labels` | PREVIOUS_COMPACTED_VIEW, TRACE, ANSWER | `_FORWARD_SOURCE_SECTIONS_VNEXT` | pass |
| `ReferenceContinuityCandidateVNext` | `source_labels` | same as forward | `_REFERENCE_SOURCE_SECTIONS_VNEXT = _FORWARD_SOURCE_SECTIONS_VNEXT` | pass |
| `CompactCandidateDiagnosticVNext` | `source_labels` (optional) | same as summary | `_DIAGNOSTIC_SOURCE_SECTIONS_VNEXT = _SUMMARY_SOURCE_SECTIONS_VNEXT` | pass |

### current_input_anchor not citable (design 24.3)

| 校验点 | 文件:行号 | 机制 | 状态 |
|---|---|---|---|
| citable_source_labels 排除 C1 | `compaction.py:1171-1172` | `__post_init__` 中 `if self.current_input_anchor.anchor_label in self.citable_source_labels: raise ValueError` | pass |
| source_section 返回 CURRENT_INPUT_ANCHOR | `compaction.py:1214-1215` | 使 label 在 parser/barrier 中可被识别为 current_input_anchor | pass |
| parser 拒绝 current anchor | `llm_compaction.py:861-862` | `if section is ConversationCompactLabelSectionVNext.CURRENT_INPUT_ANCHOR: raise ValueError` | pass |
| accept barrier 收口 | `context_governance.py:309-310` | `collector.add(CompactQualityIssueVNext.CURRENT_INPUT_ANCHOR_CITED)` | pass |

### Fail-closed contract violations

| 违规类型 | parser (llm_compaction.py) | accept barrier (context_governance.py) | 测试覆盖 |
|---|---|---|---|
| 未知 label | `unknown source label` error | `UNKNOWN_SOURCE_LABEL` issue | `test_parse_...[unknown]` + `test_check_...[label_contract]` |
| stale label | `stale source label` error | `STALE_SOURCE_LABEL` issue | `test_parse_...[stale]` + `test_check_...[label_contract]` |
| 跨 section label | `cross-section label` error | `CROSS_SECTION_LABEL` issue | `test_parse_...[cross_section]` + `test_check_...[label_contract]` |
| 缺失必需 label | `must be non-empty` error | `MISSING_SOURCE_LABEL` issue | `test_parse_...[missing_label]` |
| 空文本 | `must be non-empty` error | — (caught at dataclass __post_init__) | `test_parse_...[empty_text]` |
| 非法 enum | `is not a valid` error | — (caught at dataclass __post_init__) | `test_parse_...[illegal_enum]` |
| current anchor cited | `current input anchor` error | `CURRENT_INPUT_ANCHOR_CITED` issue | `test_parse_...[current_anchor]` + `test_check_...[label_contract]` |

### Old path boundary

| 约束 | 状态 |
|---|---|
| 旧 `CompactionCandidate` 仍存在 | pass — `compaction.py` 中保留完整定义 |
| 旧 `CompactionRequest` 仍存在 | pass — 未修改 |
| 旧 `ContextCompactor.compact` 仍存在 | pass — `llm_compaction.py` 中保留 |
| 旧 `check_compaction_candidate` 仍存在 | pass — `context_governance.py` 中保留 |
| 旧 `stable_input` / `history_input` / `evidence_input` 仍存在 | pass — `CompactMaterialPack` 字段未变 |
| 生产 operation 未切换到 vNext | pass — `compact_vnext` 是独立入口 |
| 无 vNext-to-old wrapper | pass — 全文搜索未发现 bridge adapter |
| 无 compatibility re-export | pass — vNext 类型独立命名，未使用旧名重导出 |
| 无 lazy import seam | pass — 所有 import 为顶层 import |
| 无 `hasattr`/`getattr` dispatch | pass — 旧/新路径通过不同方法名区分 (`compact` vs `compact_vnext`) |

### AGENTS 约束合规

| 约束 | 状态 |
|---|---|
| 中文 docstring | pass — 所有新增类型/函数有完整中文 docstring |
| 无 `object`/`Any`/无类型参数 | pass — 全部 typed |
| 无 `hasattr`/`getattr` seam | pass |
| 无魔法数字/字符串 | pass — 常量均命名 |
| 模块间依赖最小化 | pass — vNext contract 集中在 `compaction.py` |
| 分层约束 | pass — 不修改 Service/UI/Fins/Engine |

## Test Coverage Assessment

### 覆盖的场景

| 场景 | 测试 | 文件 |
|---|---|---|
| vNext candidate JSON round-trip | `test_conversation_compact_output_vnext_round_trips_json` | test_compaction_contract.py |
| accept barrier 接受合法 candidate | `test_check_conversation_compact_output_vnext_accepts_valid_candidate` | test_compaction_contract.py |
| fake vNext compactor 产生 deterministic candidate | `test_fake_conversation_compactor_vnext_produces_typed_candidate` | test_compaction_contract.py |
| stale label reject | `test_check_...[STALE_SOURCE_LABEL]` | test_compaction_contract.py |
| cross-section label reject | `test_check_...[CROSS_SECTION_LABEL]` | test_compaction_contract.py |
| current anchor cited reject | `test_check_...[CURRENT_INPUT_ANCHOR_CITED]` | test_compaction_contract.py |
| vNext parser 接受 design schema | `test_parse_conversation_compact_output_vnext_accepts_design_schema` | test_llm_compaction.py |
| vNext parser fail-closed (7 cases) | `test_parse_conversation_compact_output_vnext_fails_closed` | test_llm_compaction.py |
| compact_vnext 渲染 vNext material | `test_llm_context_compactor_compact_vnext_uses_vnext_material` | test_llm_compaction.py |
| vNext material section mapping | `test_conversation_compact_input_vnext_maps_material_without_citable_current_anchor` | test_compact_material.py |
| 旧 path 测试不退化 | 所有旧 `test_fake_compactor_*`, `test_quality_*` 测试仍通过 | 3 文件 |

### 未覆盖的场景（标记为 deferred）

| 场景 | 分类 | Owner |
|---|---|---|
| compact roll-forward (previous_compacted_view 非空) | deferred | Slice B/C — 需要完整 memory projection |
| whole-candidate repair | deferred | Slice B — 需要 operation 编排 |
| `CONTEXT_COMPACTED` event payload | deferred | Slice B |
| compact failure fallback | deferred | Slice B/D |
| RunInputBuilder prompt assembly | deferred | Slice D |

## Validation

```bash
source .venv/bin/activate
pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py -q
# Result: 100 passed in 0.33s

python -m pyright dayu/ tests/ utils/
# Result: 0 errors, 0 warnings, 0 informations
```

## Residual Risks

| 风险 | 分类 | Owner | 说明 |
|---|---|---|---|
| `previous_compacted_view` 构造不完整 | covered by later slice | Slice B/C | Slice A 只映射 fact；summary/anchor/intent/continuity 待 projection 切换 |
| `_STALE_LABEL_PREFIXES_VNEXT` drift | non-blocking finding (F2) | Slice B | 两处重复定义需在 Slice B 前收敛 |
| `check_conversation_compact_output_vnext` 导出缺失 | non-blocking finding (F1) | Slice B | Slice B operation 接线时需要正式导出 |
| operation event payload 未切换 | covered by later slice | Slice B | `compact_vnext` 仍是局部 contract 入口 |
| memory durable/projection 未切换 | covered by later slice | Slice C | 旧 snapshot shape 仍存在 |
| RunInputBuilder 未切换 | covered by later slice | Slice D | 旧 stable block headers 仍存在 |
| 完整 eval benchmark | deferred-with-owner | WU-CM-10 / GitHub Issue #80 | WU-CM-01 只提供可断言入口 |

## Recommendation

Slice A 可以进入下一 gate (Slice B - Compact Operation And Event Closure)。建议在 Slice B 启动前先修复 F1（`__all__` 导出）和 F2（stale label 常量去重），但这两条均不阻塞 Slice B 的 implementation 工作。
