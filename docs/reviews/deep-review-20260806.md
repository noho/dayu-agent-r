# Deep Review: Compaction V3→V4 与 Evidence Provenance

**Base**: `2d914be` (2026-08-06)
**Head**: `b9908d9a` (2026-08-06)
**Scope**: 85 files, +9170/-2161 lines
**Reviewer**: Claude Code Deep Review

---

## Executive Summary

本次变更完成了 compaction 子系统从 V3 到 V4 的全量迁移，核心新增能力是 **evidence provenance preservation**（证据溯源保持）：压缩后的 memory 事实可以追溯到原始 tool call 证据链，并在多次 compaction 间保持连续性。

**结论：架构健康，语义所有权边界清晰，无阻塞性问题。** 以下详述发现。

---

## 1. 架构分析

### 1.1 变更核心脉络

| 维度 | V3 | V4 |
|------|----|----|
| 类型命名 | `Compact*V3` | `Compact*V4` |
| Schema literal | `v3` | `v4` |
| Artifact schema version | `4` | `5` |
| 事实来源 | `COMPACT_FACT_SOURCE_KINDS_V3` 含 `PREVIOUS_EVIDENCE_FACT` + `EVIDENCE_MATERIAL` | 拆分为 `COMPACT_FACT_SOURCE_KINDS_V4`（仅 `EVIDENCE_MATERIAL`）+ `COMPACT_RETAIN_SOURCE_KINDS_V4`（仅 `PREVIOUS_EVIDENCE_FACT`） |
| Acceptance 产物 | `CompactAcceptedTruthV3`（直接含 candidate） | `CompactAcceptedTruthV4`（含 proposal + replacement 分离） |
| Event payload | `accepted_candidate` + `accepted_candidate_digest` | `accepted_proposal` + `accepted_proposal_digest` + `accepted_replacement` |
| Evidence 连续性 | 无 | `retained_previous_evidence_fact_labels` + `canonical_evidence_refs` 全链传播 |

### 1.2 模块职责表（已验证无漂移）

| 模块 | 职责边界 | 状态 |
|------|---------|------|
| `compaction.py` | 所有领域类型、枚举、验证函数、`ContextCompactor` 协议 | ✅ |
| `compact_structure.py` | JSON 结构描述符、schema、template、parser | ✅ |
| `compact_material.py` | Material pack 构建、segment 选择、provenance entry 构建 | ✅ |
| `compact_payload.py` | 持久化 payload 语义解析、artifact JSON 构建 | ✅ |
| `context_governance.py` | 确定性 accept/reject、coverage/policy/provenance 派生 | ✅ |
| `compaction_operation.py` | 异步 attempt 循环、manifest 录入、budget 门控 | ✅ |
| `context_events.py` | canonical event payload 构建与严格解析 | ✅ |
| `compact_artifact.py` | artifact + descriptor 写入 | ✅ |
| `compact_pipeline.py` | 纯组合逻辑：source snapshot、request plan、recovery plan | ✅ |
| `llm_compaction.py` | `ContextCompactor` 协议的 LLM 实现 | ✅ |
| `durable/tool_trace.py` | Tool Trace hot projection、runner-call reconstruction | ✅ |

---

## 2. 语义所有权评估

### 2.1 关键所有权机制

**`_CompactAcceptancePermit` 模式**：`CompactAcceptedTruthV4` 的构造被 `_COMPACT_ACCEPTANCE_PERMIT` 令牌门控，只有 `context_governance.py` 能持有该令牌。这确保了：
- 其他模块无法伪造 accepted truth
- coverage 派生、policy audit、evidence ref 绑定全部集中在 governance 模块

**Prompt-local label 抽象**：LLM 只看到 `T1`、`E1` 等不透明标签，never sees：
- `canonical_source_refs`（event ID）
- `canonical_evidence_refs`（证据链）
- `content_digest`（内容摘要）
- `payload_refs` / `artifact_refs`（持久化引用）

**Replacement vs Proposal 分离**：V4 新增 `CompactAcceptedReplacementV4` 作为 Host 验收后的自包含语义，与 LLM 原始 proposal 分离。这解决了 V3 中 "accepted_candidate 直接是 LLM 输出" 的语义泄漏问题。

### 2.2 证据溯源传播链

```
Material Pack (provenance_map)
  → Source Boundary (canonical_evidence_refs, opaque to LLM)
    → LLM Proposal (prompt-local labels only)
      → Governance Acceptance (derive accepted replacement with evidence refs)
        → Event Payload (accepted_replacement + accepted_evidence_mapping_refs)
          → Next Compaction Material (previous_compacted_view with evidence refs)
```

每个环节的 evidence refs 都是从上一环节的 typed 对象**机械复制**，不是从 raw data 重新推导。这符合 CLAUDE.md 的语义所有权要求。

### 2.3 无违规确认

- ✅ 消费者不从 raw data 重新推导语义
- ✅ LLM 不可见 durable provenance
- ✅ Governance 是唯一 acceptance gate
- ✅ Coverage 派生集中在 governance
- ✅ Evidence refs 机械传播而非推导
- ✅ Operation loop 不触碰语义内容

---

## 3. 关键发现

### 3.1 正面发现

#### F1: V3→V4 迁移完整性
所有 V3 类型引用已被清除。`grep` 确认 `dayu/host/` 下无残留 `V3` 类型引用。Schema literal、枚举值、验证函数全部同步升级。

#### F2: Proposal/Replacement 分离设计
`CompactAcceptedReplacementV4` 是 V4 最重要的设计改进。V3 中 `accepted_candidate` 直接暴露 LLM 输出给下游消费，V4 中 `accepted_replacement` 是 Host governance 派生的自包含语义，不依赖 LLM 的原始字段顺序或标签命名。

#### F3: `retained_previous_evidence_fact_labels` 语义清晰
该字段明确区分了 "本轮新增事实" 和 "保留旧事实" 的来源约束：
- 新增事实：`support_labels` 必须指向 `EVIDENCE_MATERIAL`
- 保留事实：selector 必须指向 `PREVIOUS_EVIDENCE_FACT`

这种拆分避免了 V3 中两种来源混用同一 `support_labels` 的语义模糊。

#### F4: `_resolve_compactor_response_identity` 全扫描设计
`tool_trace.py` 中的 compactor terminal 全扫描（分页 keyset cursor）是正确的设计选择：
- compactor terminal 数量有上界（attempt 次数 × 操作数）
- 避免了在 hot projection 中维护额外索引
- 唯一性不变量检查（duplicate canonical terminals → error）确保数据完整性

#### F5: 测试覆盖深度
262 个测试全部通过，覆盖：
- Schema literal 精确合约
- DTO 形状合约（frozen/slots/no defaults）
- Structure owner 投影一致性
- Acceptance owner 全路径
- Evidence provenance 传播
- Policy caps 边界值
- Durable store 8 种篡改检测
- Secret 泄漏防护

### 3.2 需关注发现

#### F6: Fake Compactor `forward_intents` / `reference_continuity` 空实现

**位置**: `tests/host/fake_compaction.py:839-862`

**问题**: `_fake_forward_intents_vnext()` 和 `_fake_reference_items_vnext()` 始终返回空元组。这意味着：
- 所有使用 `FakeContextCompactor` / `FakeConversationCompactorVNext` 的端到端测试从不经过 forward_intents 和 reference_continuity 的完整 compaction 流程
- contract 测试在 acceptance 边界覆盖了这两个 section，但集成路径存在盲区

**风险等级**: 低。contract 测试已覆盖 acceptance 边界，且这两个 section 的结构与 evidence_facts/answer_anchors 同构。但建议后续补充 fake 实现。

**建议**: 在 `_fake_forward_intents_vnext` 中基于 request 的 trace material 构造至少一个 `CompactForwardIntentV4(status=OPEN)`，在 `_fake_reference_items_vnext` 中基于 answer material 构造至少一个 `CompactReferenceContinuityV4`。

#### F7: `_resolve_compactor_response_identity` 全扫描的 O(n) 复杂度

**位置**: `dayu/host/durable/tool_trace.py:624-692`

**问题**: 每次解析 compactor response identity 都需要全扫描 parent Host Run 的所有 compactor terminal event。对于单次 compaction（1-3 attempts）这不是问题，但如果一个 session 有大量 compaction 操作，扫描成本会线性增长。

**风险等级**: 极低。compaction 操作频率低（通常每几十轮一次），terminal event 数量有实际上界。当前设计优先选择了正确性和简单性，是正确的权衡。

#### F8: `COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT` 从 4 跳到 5

**位置**: `dayu/host/compact_payload.py`

**问题**: Schema literal 是 `v4`，但 artifact schema version 是 `5`。这两个数字的不一致可能造成混淆。

**风险等级**: 极低。Schema literal（`dayu.context_compaction.input.v4` / `output.v4`）和 artifact schema version 是不同的概念：前者标识 LLM 输入/输出格式版本，后者标识持久化 artifact 的序列化格式版本。V4 格式变更导致 artifact 结构变化（新增 `accepted_replacement` 字段），所以 artifact version 递增是正确的。

---

## 4. 测试覆盖评估

### 4.1 覆盖矩阵

| 测试文件 | 行数 | 覆盖维度 | Owner-level |
|---------|------|---------|-------------|
| `test_compaction_contract.py` | 1715 | Schema/DTO/Acceptance/Caps/Provenance | ✅ 完全 |
| `test_context_compact_events.py` | 2119 | Event payload 构建/解析/Secret 防护 | ✅ 完全 |
| `test_compact_material.py` | 4490 | Segment 选择/Material 构建/Durable 完整性 | ✅ 完全 |
| `test_compaction_operation.py` | 816 | Attempt 循环/Repair/Budget/Identity | ✅ 完全 |
| `test_public_compact_smoke.py` | 2686 | 端到端/Prompt 合约/Injection 防护 | ⚠️ 混合 |
| `test_compact_pipeline.py` | ~400 | Pipeline 组合逻辑 | ✅ 完全 |

### 4.2 测试设计模式

所有 contract 测试遵循 "最小有效输入 + 单字段变异" 模式：
1. 构造最小有效输入
2. 变异一个字段
3. 断言精确拒绝（错误码、JSON path、错误消息）

这是 owner-level contract 测试的最佳实践。

### 4.3 覆盖缺口

| 缺口 | 严重性 | 说明 |
|------|-------|------|
| Fake compactor 空 forward_intents/reference_continuity | 低 | contract 测试已覆盖 acceptance 边界 |
| Reactive compaction 首次 attempt 失败 | 低 | 只测试了 reactive empty boundary |
| `max_attempt_number=1` 单次 attempt | 低 | 多次 attempt 已覆盖 |
| `forward_intents` 混合 `intent_type` | 极低 | 同一 candidate 内不同 intent type |

---

## 5. LLM-facing 文本合规

### 5.1 Prompt 合规

`test_public_compact_smoke.py::test_default_compactor_prompt_is_llm_facing_self_contained` 验证：
- 禁止内部术语（`CompactCandidateV4`、`context_governance`、`_permit` 等）
- 必需的 prompt marker 存在
- 禁止治理术语泄漏

### 5.2 Schema 合规

`compact_structure.py` 的 prompt rules 和 JSON schema 是 LLM-facing 的，已验证：
- 字段名、含义、类型、必填性自足说明
- 不引用内部类型名
- 提供业务可读枚举说明

### 5.3 Repair Feedback 合规

`build_compact_repair_feedback_v4()` 产生的 feedback：
- 有字符上限（`MAX_COMPACT_REPAIR_FEEDBACK_CHARS`）
- 有 issue 数量上限（`MAX_COMPACT_REPAIR_ISSUES`）
- 错误消息有字符上限（`MAX_COMPACT_REPAIR_ISSUE_MESSAGE_CHARS`）
- Secret 在 parser error 中被 `<redacted>` 标记

---

## 6. 风险评估

### 6.1 无阻塞性风险

- ✅ 测试全部通过（262 passed, 1 skipped）
- ✅ Pyright 零错误
- ✅ 语义所有权边界完整
- ✅ V3 残留已清除
- ✅ Evidence provenance 传播链完整
- ✅ LLM-facing 文本合规

### 6.2 低风险项

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| Fake compactor 集成盲区 | 低 | contract 测试已覆盖 |
| Full scan O(n) 复杂度 | 极低 | compaction 频率低 |
| Schema version 数字不一致 | 极低 | 语义不同，递增正确 |

### 6.3 后续建议

1. **补充 fake compactor 的 forward_intents / reference_continuity 实现**，使端到端测试覆盖全部五个 section
2. **考虑在 tool_trace hot projection 中缓存 compactor terminal 索引**，如果未来 compaction 频率显著增加（当前不需要）

---

## 7. 总结

本次变更是一次高质量的 V3→V4 迁移，核心价值在于：

1. **Proposal/Replacement 分离**：解决了 V3 中 LLM 输出直接暴露给下游的语义泄漏问题
2. **Evidence provenance 全链传播**：从 material pack → source boundary → proposal → acceptance → event payload → next material，每个环节的 evidence refs 都是 typed 机械传播
3. **Retain/New 来源分离**：`retained_previous_evidence_fact_labels` 明确区分保留旧事实和新增事实的来源约束

架构健康度：**A**（模块职责清晰，所有权边界完整，无反向依赖）
测试覆盖度：**A-**（contract 测试深度优秀，fake compactor 集成有小缺口）
代码质量：**A**（类型严格，docstring 完整，无 magic number/string）
