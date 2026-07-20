# WU-SEMANTIC-OWNERSHIP-01 P3-C Plan Review — AgentMiMo

## Reviewed target and scope

- **Plan artifact**: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`
- **Design sources**: `docs/host/design.md` (§23-25), `docs/engine/design.md` (§1, 4, 14, 15)
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Scope**: P3-C — Context compaction payload, evidence text, and LLM-safe projection contract
- **Gate**: plan review (parallel with AgentDS)
- **Review date**: 2026-07-10
- **Reviewer**: AgentMiMo

## Assumptions tested

1. `ContextCompactedSemanticPayload` scope is narrow enough to avoid becoming a God contract.
2. The single typed parse boundary at `compact_payload` eliminates second schema truth in `context_events`.
3. `CompactMaterialPack` blocks and typed `CompactReadableViewVNext` can be maintained in sync through tier2/3 degrade.
4. Deleting `CompactArtifactView.messages` and `_compact_artifact_message_content` is safe given memory required catch-up.
5. `estimate_post_compact_budget` can be a pure function with direct parameters, no dependency cycle.
6. `AcceptedToolEvidenceLLMMaterial` with a single renderer is sufficient for memory/compact/ordinary/fallback.
7. Typed mismatch exception replaces `str(exc)` comparison without breaking existing catch chains.
8. Three slices each form a complete producer-validator-persistence-projection-consumer closure.
9. `ForwardIntent.intent_type: str` and `ReferenceContinuityItem.reason: str` can be tightened to enum without snapshot schema migration.
10. The accepted 7 / rejected 2 finding dispositions are correctly adjudicated against current code.

## Findings

### 001-未修复-中-S3 exact changes 未显式列出 compact_material.py str(exc) catch block 删除

- **位置**: §8 S3 Exact changes, 与 §3.5 / §6.7
- **问题类型**: 不可直接实施
- **当前写法**: S3 Exact changes 第 4 条说"MemoryProjectionEvent/RunInputMaterialBlock 迁移为 typed LLM material；删除松散字段与三套 private renderers"，第 3 条说"durable memory、run input inline repair、compact material 不再二次打开 envelope"。但没有显式列出 `compact_material.py` 第 2264 行 `if str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` catch block 的删除。
- **反例/失败场景**: `compact_material.py` 的 `build_pre_dispatch_compact_material_view()` 在第 2260-2268 行调用 `accepted_evidence_envelope_from_payload()` 并 catch `ValueError`，通过 `str(exc)` 比较区分 mismatch 和其它验证错误。S3 让 compact material 不再二次打开 envelope，意味着这段代码整体删除或重构。但 S3 Exact changes 只列了 projection/migration 步骤，没有把 `compact_material.py:2264` 的 catch block 列为必须删除的代码路径。Implementation agent 可能只迁移 evidence block 构造而保留旧 envelope catch，导致 dead code 或错误的异常处理。
- **为什么有问题**: Plan 的 source scan `rg -n 'str\(exc\).*ACCEPTED_EVIDENCE|ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH' dayu/host` 预期无生产匹配。如果 `compact_material.py` 的 catch block 未删除，source scan 会失败。但 S3 Exact changes 没有把这个路径列为明确的删除目标，implementation agent 需要自行推断。
- **直接证据**:
  - `compact_material.py:2264`: `if str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH`
  - S3 Exact changes 无 `compact_material.py` envelope catch block 条目
  - §9 source scan 预期 `str(exc).*ACCEPTED_EVIDENCE` 无匹配
- **影响**: Implementation agent 可能遗漏该 catch block 的删除，导致 source scan 失败或留下 dead code。
- **建议改法和验证点**: S3 Exact changes 增加一条："删除 `compact_material.py` 中 `accepted_evidence_envelope_from_payload()` 调用及其 `str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` catch block；evidence block 构造改为消费 `AcceptedToolResultProjection` 的 typed LLM material"。验证点：source scan `rg -n 'str\(exc\).*ACCEPTED_EVIDENCE|ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH' dayu/host` 无匹配。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 002-未修复-中-S2 exact changes 未显式覆盖 DurableCompactArtifactProvider 消息生成删除与 RunInputBuilder.build() 装配变更

- **位置**: §8 S2 Exact changes 第 4-5 条，与 §3.4 / §6.4
- **问题类型**: 不可直接实施
- **当前写法**: S2 Exact changes 第 4 条说"CompactArtifactView 删除 messages 并增加 compaction event ref"，第 5 条说"删除 run_input raw compact candidate renderer/fields"。但没有显式列出 `DurableCompactArtifactProvider._load_compact_artifact_tx()` (run_input.py:1589-1633) 的重构——该函数当前从 raw payload 构造 `SystemMessage` 并放入 `CompactArtifactView.messages`。也没有显式列出 `RunInputBuilder.build()` (run_input.py:1918-1940) 的装配变更——当前 `bounded_context_messages = (*memory.messages, *compact.messages, ...)` 需要删除 `*compact.messages`。
- **反例/失败场景**: Implementation agent 删除 `CompactArtifactView.messages` 字段后，`DurableCompactArtifactProvider._load_compact_artifact_tx()` 仍尝试构造 `SystemMessage` 并赋值给 `messages`——pyright 会报错。Agent 修复 pyright 错误时可能采用 ad-hoc 方案（如保留空 messages tuple）而不是按设计意图删除消息生成逻辑。`RunInputBuilder.build()` 的 `*compact.messages` 拆包也会 pyright 失败，agent 可能用 `compact.messages or ()` 兼容而不是删除该拆包。
- **为什么有问题**: Plan 正确识别了 ordinary RunInput 存在两个 accepted compact renderer 的问题（§3.4），并正确决定删除 compact artifact renderer（§6.4）。但 S2 Exact changes 把这个删除表述为"删除 messages"和"删除 renderer/fields"，没有覆盖 `DurableCompactArtifactProvider` 的消息生成逻辑和 `RunInputBuilder.build()` 的装配逻辑这两个具体的、必须修改的代码路径。
- **直接证据**:
  - `run_input.py:1614-1627`: `_compact_artifact_message_content()` 调用后构造 `SystemMessage`
  - `run_input.py:1927`: `*compact.messages` 拆包进入 `bounded_context_messages`
  - S2 Exact changes 无 `DurableCompactArtifactProvider` 重构条目
  - S2 Exact changes 无 `RunInputBuilder.build()` 装配变更条目
- **影响**: Implementation agent 需要自行推断这两个代码路径的变更，可能采用不一致的删除策略或保留兼容逻辑。
- **建议改法和验证点**: S2 Exact changes 增加两条：
  1. "`DurableCompactArtifactProvider._load_compact_artifact_tx()` 删除 `_compact_artifact_message_content()` 调用和 `SystemMessage` 构造；`CompactArtifactView` 只携带 `compaction_event_ref`、`compact_artifact_ref`、`compact_artifact_digest`、`represented_evidence_refs`"
  2. "`RunInputBuilder.build()` 删除 `*compact.messages` 拆包；`bounded_context_messages` 只包含 `memory.messages + protected_raw_tail.messages + continuity.messages`"
  验证点：`compact.messages` 不再存在于 `CompactArtifactView`；`RunInputBuilder.build()` 的 `bounded_context_messages` 不包含 compact artifact messages。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

## Open questions

无。当前代码与设计证据足以做出裁决。

## Residual risks

| 风险 | 分类 | 跟踪目标 |
|---|---|---|
| `_POST_COMPACT_BASE_MESSAGE_COUNT` 在 `compaction_operation.py` 和 `llm_compaction.py` 中重复定义；P3-C 只迁移 `compaction_operation.py` 的副本到 `context_budget`，`llm_compaction.py` 的副本保留 | scope boundary | P3-C non-goal，后续 cleanup |
| `compact_material.py` 的 `_snapshot_forward_intent_texts()` 仍使用分号分隔的字符串格式；P3-C 删除 `_parse_previous_forward_intent_text()` 反解析器后，序列化函数保留但不再有对应的反解析消费者 | dead code after S2 | S2 实现时确认是否一并删除 |
| `accepted_compact_business_texts()` 的稳定顺序未在 plan 中显式定义（summary → facts → anchors → intents → references） | specification detail | Implementation agent 按自然字段顺序实现 |
| S2 测试迁移范围：plan 列出了受影响测试文件但未列出需要从"no-op memory + compact renderer"迁到"production memory catch-up path"的具体测试用例 | test migration scope | Implementation agent 按 completion signal 扫描 |

## Plan review conclusion

**pass-with-risks**

Plan 的两个核心 owner closure 设计正确：`ContextCompactedSemanticPayload` 作为窄 read view 避免了 God contract，`AcceptedToolEvidenceLLMMaterial` 统一了三套 evidence renderer。三个 implementation slices 各自形成 producer-validator-persistence-projection-consumer 闭合，sequencing 合理。typed mismatch exception、strict accessor、enum fail closed 的设计方向正确。post-compact budget 的依赖方向和 diagnostics 排除逻辑成立。accepted 7 / rejected 2 的 finding 裁决与当前代码证据一致。

两个 medium-severity findings 均为 S2/S3 Exact changes 的显式性不足——plan 的设计意图正确，但 implementation agent 需要自行推断的代码路径应被显式列出。修复风险低，不影响 plan 的整体架构方向。
