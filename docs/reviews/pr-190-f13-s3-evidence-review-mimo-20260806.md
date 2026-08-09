# PR 190 F13 S3 Evidence Review — MiMo

**审查范围**: base `2d914be`..HEAD (`e4c290c8`), production code ~9750 行变更,
immutable evidence root `f13-postfix-20260806T-W7W4JX`。
**审查重点**: semantic owner、previous EvidenceFact claim/ref 原子同源、Memory / artifact /
EventLog / public Tool Trace 等式、21.7 非 EvidenceFact 结论边界、过度设计、test / real CLI 分层。

---

## 结论: ACCEPTED

proposal/replacement 分层正确、previous fact 原子保留机制完整、四端 evidence fact
同源等式经 immutable evidence 验证成立。21.7% 修正正确隔离在 EvidenceFact 边界之外。
test / real 分层诚实。

---

## Findings

### F-0 [INFO] proposal / replacement 语义分层正确

v3 `CompactCandidateV3` 同时承载模型输出与 Host 最终语义，rolling 场景下旧
claim/provenance 由 Host 隐式拼接。v4 分离为 `CompactCandidateV4`（模型七字段
proposal）与 `CompactAcceptedReplacementV4`（Host 验收后五区 replacement）。

- **模型**: 只拥有 `retained_previous_evidence_fact_labels`（keep/omit selector）和
  `evidence_facts`（本轮新事实）。
- **Host** (`derive_compact_accepted_replacement_v4`, `compaction.py:1634-1711`):
  唯一执行 retained fact 原子复制（从 boundary entry 的 `readable_text` + `canonical_evidence_refs`）、
  new fact evidence refs 绑定、五区合并。模型无法改写旧 claim 或 provenance。

### F-1 [INFO] previous EvidenceFact claim/ref 原子同源

`CompactSourceBoundaryEntryV4` 新增 `canonical_evidence_refs`，由 `compact_material.py`
从 EventLog `CONTEXT_COMPACTED` payload 机械投影。`CompactAcceptedEvidenceFactV4` 是
frozen dataclass，强制 `canonical_evidence_refs` 非空。

immutable evidence 验证:
- 第二个 artifact boundary 将首次 5 个事实投影为 P2-P6，每个带原 claim 与 canonical ref。
- 第三个 artifact 以 P1-P5 再次原子保留同一组 claim/ref。
- 3 个 EventLog terminal 的 `accepted_replacement` 各含 5 个 fact，ref 均为
  `evidence:event-tool-result-accepted-2527bd9c...`。
- Memory snapshot seq=209: 5 facts, 0 空 refs, 每个 ref 指向第三个 artifact terminal。

结论: claim 与 provenance 由 Host atom 投影，LLM 只有 keep/omit selector，无 provenance laundering 路径。

### F-2 [INFO] Memory / artifact / EventLog / public Tool Trace 四端等式

| 端 | facts count | canonical_evidence_refs |
|---|---:|---|
| EventLog terminal seq=183 | 5 | `evidence:event-tool-result-accepted-2527bd9c...` |
| artifact `5fd4c26f...` | 5 | 同上 |
| Memory snapshot seq=209 | 5 | 同上 |
| public Tool Trace JSON | 5 | 同上 |

`ResolvedCompactorEvidenceFact` 从 `semantic_payload.accepted_replacement.evidence_facts`
机械投影，`tool_trace_analysis.py` 直接 pass-through。

### F-3 [INFO] 21.7% 非 EvidenceFact 结论边界

Memory snapshot seq=209 验证: `claim contains 21.7/18.2: 0`。所有 artifact 的
accepted EvidenceFact 均不含 `21.7` 或 `18.2`。21.7% 存在于普通 recent window，
assistant 文本明确标为待核验、无工具证据，未进入 `evidence_backed_facts`。

S3 doc 坦承限制: 首个 artifact 的 source_boundary 未选入该修正，不能声称模型已尝试
升级且被 Host typed reject。该反例由 owner tests 覆盖。

### F-4 [INFO] schema v3→v4 / artifact v4→v5 版本迁移

- 所有 `*V3` → `*V4`，`COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT` 4→5。
- `_ROOT` descriptor 新增 `retained_previous_evidence_fact_labels`。
- `_COMPACTED_REQUIRED_FIELDS` 新增 `_FIELD_ACCEPTED_REPLACEMENT`。
- `_parse_source_boundary` 新增 `canonical_evidence_refs` 字段。
- pyright 0 errors, 无残留 V3 import 或兼容逻辑。

### F-5 [INFO] 验收流程 replacement-centric 化

v4 `accept_compact_candidate_v4` 先 boundary binding 校验，再 `derive_compact_accepted_replacement_v4`
展开 replacement，然后对 replacement 执行 duplicate/contradiction/information/policy 校验。

downstream: `accepted_compact_business_texts` 消费 replacement; `_facts_from_accepted_event`
逐事实取 `canonical_evidence_refs`; `_aggregate_pass_candidates` 按 source kind 分离 retained/new。
`estimate_post_compact_budget` 移到 acceptance 后，基于 Host 确定的 replacement 文本。

### F-6 [INFO] `canonical_evidence_refs` 对称校验

`CompactSourceBoundaryEntryV4`、`CompactMaterialBlock`、`PromptLocalProvenanceEntry`
三处均仅对 evidence kind 非空，非 evidence 必须为空。校验规则对称。

### F-7 [INFO] `accepted_evidence_mapping_refs` 等式

`ContextCompactedSemanticPayload.__post_init__` 断言
`accepted_evidence_mapping_refs == accepted_replacement.canonical_evidence_refs`。
两者同源于 `context_events.py` 序列化，等式由 Host durable 写入保证。

### F-8 [INFO] test / real CLI 分层诚实

S3 doc 明确区分 owner tests（2493 passed, deterministic fake/mock）与 real CLI
（production PTY, 真实 provider, 8 segment exit_code=0）。未覆盖边界（typed reject、
bounded repair、repair exhaustion、failed candidate 非污染、stale/late result、
reconnect 只读）均声明由 owner tests 覆盖，未伪装为真实 observation。

### F-9 [INFO] cap=1 与 repair exhaustion 诚实

S3 doc 坦承: cap=1 由模型首轮直接输出合法 `session_summary=null`，诊断变体未诱发
失败。相关结论只能引用 owner tests，不能写成真实 CLI 行为通过。

### F-10 [INFO] `NON_CANONICAL_SOURCE_LABEL_ORDER` 新增校验码

v4 新增 boundary-order canonicalization 约束，确保 retained/new 拼接后 label 序列
可 deterministic 恢复。

---

## 设计诚实度

S3 doc 对 artifact 边界的限制声明足够诚实: 区分 test / observation 覆盖; 声明 6 个
未观察边界; 不把 exit_code=0 解释为业务 PASS; 不把 provider 行为扩大解释为 Host 机制验证。
