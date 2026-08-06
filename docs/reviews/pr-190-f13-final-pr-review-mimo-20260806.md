# PR 190 F13 Final PR Review — MiMo

**delta**: `ab1207f12706c07da7eca847bde27fe96fc727c5`..`2520b11b`
**scope**: 10 commits, 104 files, +12009/-2151
**reviewer**: AgentMiMo | **date**: 2026-08-06
**accepted artifacts**: S0 design, S1 full-slice, S2 tool trace + scope fix,
  S3 evidence validation, aggregate deepreview

---

## Verdict: ACCEPTED

无 blocking / high / medium finding。3 个 low residual 均来自已 accepted 的 aggregate
deepreview，不改变 F13 contract 正确性。

---

## 1. Root cause 是否在 Host owner 修复

**直接证据**: `compaction.py:1634-1711` `derive_compact_accepted_replacement_v4` 是
proposal→replacement 的唯一 owner。`context_governance.py` `accept_compact_candidate_v4`
调用它后才进入 duplicate/info/caps 校验。模型无旧 claim 字段（七字段 proposal 无 `claim`
输入），Host 从 boundary entry 原子复制 `claim + canonical_evidence_refs`。

✅ root cause 在 Host owner，无下游补偿。

## 2. Previous EvidenceFact claim/ref 原子性

`derive_compact_accepted_replacement_v4:1674-1688` retained 路径：
`claim = entry.readable_text`、`canonical_evidence_refs = entry.canonical_evidence_refs`、
`selection_labels = (entry.source_label,)`、`context_labels = ()`。
`CompactAcceptedEvidenceFactV4` 是 frozen dataclass，`__post_init__` 强制 refs 非空唯一。

immutable evidence 验证：第二 artifact P2-P6 各带原 claim 与 `evidence:event-tool-result-accepted-2527bd9c...`；
第三 artifact P1-P5 再次原子保留同一组 claim/ref。Memory seq=209 全部指向同一 ref。

✅ 无 provenance laundering 路径。

## 3. New fact 非空 canonical refs barrier

- `COMPACT_FACT_SOURCE_KINDS_V4 = (CompactSourceKindV4.EVIDENCE_MATERIAL,)`，new fact 只允许 evidence。
- `CompactAcceptedEvidenceFactV4.__post_init__` 强制 `canonical_evidence_refs` 非空唯一 tuple。
- `CompactSourceBoundaryEntryV4.__post_init__` 对 `EVIDENCE_MATERIAL` / `PREVIOUS_EVIDENCE_FACT`
  强制非空 refs，其余 kind 强制为空（对称校验）。
- 测试覆盖：单源、双源 union、refs 越界、空 refs、previous label 塞入 support 全部 typed reject。

✅ 空 refs 被类型系统阻断。

## 4. Memory / artifact / EventLog / Tool Trace / reconnect 同源

| 端 | source | mechanism |
|---|---|---|
| artifact payload | `accepted_replacement.to_json()` | `context_events.py:1242` |
| EventLog payload | 同上 + `accepted_replacement.canonical_evidence_refs` | `context_events.py:1263` |
| Memory | `_facts_from_accepted_event` 逐 fact 读 `fact.canonical_evidence_refs` | `memory.py` |
| Tool Trace | `parse_context_compacted_semantic_payload` → `accepted_replacement.evidence_facts` | `tool_trace.py:721-732` |
| reconnect | 同一 strict parser → 同一 Memory projection | `run_input_builder.py` |
| RunInput refs | `accepted_evidence_mapping_refs` property = `replacement.canonical_evidence_refs` | `compact_pipeline.py:287-291` |

`ContextCompactedSemanticPayload.__post_init__` 断言
`accepted_evidence_mapping_refs == accepted_replacement.canonical_evidence_refs`。

✅ 六端同源，无第二 provenance source。

## 5. Repair / fallback / stale-late / single-terminal 无污染

- `compaction_operation.py`：repair 每次走完整 `accept_compact_candidate_v4`。
- budget exhaust → `_failed_operation_result(accepted_truth=None)`，不物化 artifact / Memory。
- stale / late → terminal commit owner 返回 no-op，不创建第二 terminal。
- `test_compaction_operation.py`：cancellation-between-attempts、all-invalid-exhaust、
  root-hard-budget-reject。
- `test_compaction_terminal.py`：stale/late single terminal。

✅ 无污染路径。S3 坦承真实 CLI 未直接观察 repair/exhaustion/stale，相关结论只引用 owner tests。

## 6. Schema / prompt 自足

- `conversation_compaction_user.md`：自足说明七字段、类型、必填性、allow kind、
  retain/omit 语义、combined cap 数值例、最小 JSON。
- 不暴露 event id、digest、payload ref、Host 模块名。
- `compact_structure.py`：prompt rules 与 JSON schema 从同一 `_ROOT` descriptor 派生。
- `test_public_compact_smoke.py::test_default_compactor_prompt_is_llm_facing_self_contained` 验证。

✅ 无治理泄漏。

## 7. 过度设计 / 兼容 shim

- `grep` 生产代码零命中 `CompactAcceptedTruthV3` / `CompactCandidateV3` / `CompactInputV3`。
- 无 V3 alias / re-export / dual reader / migration shim。
- 无 drop ledger、第二 provenance service、entailment heuristic。
- `COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT = 5`，删除旧 `accepted_candidate` key。
- `accepted_evidence_mapping_refs` 从函数参数改为 `replacement.canonical_evidence_refs` 的 property。

✅ 无兼容代码。

## 8. 真实 scenario evidence 诚实度

S3 doc / errata 坦承：
- 21.7% 修正存在于 recent window，未进入 evidence_backed_facts，但不能声称"模型尝试升级被 typed reject"。
- cap=1 由模型首轮直接输出合法 `session_summary=null`。
- 诊断变体未诱发 repair / exhaustion / fallback。
- 8 segment 均 `exit_code=0`，但不单独解释为业务 PASS。

✅ 不过度声称。

## 9. 工作树 / commit 范围

10 commits 全在 `codex/interactive-oracle` 分支。S3 acceptance 后 4 个 commit：
gateflow accept、test assertion align、real CLI validation doc。无漂移。

---

## Findings

### F1 [LOW] Fake compactor forward_intents / reference_continuity 空实现

- **severity**: LOW
- **file**: `tests/host/fake_compaction.py`
- **impact**: smoke 不经过这两个 section 完整流程。contract 测试在 acceptance 边界已覆盖。
- **verdict**: accepted（contract 测试已覆盖）

### F2 [LOW] Artifact schema version 与 schema literal 数字不一致

- **severity**: LOW
- **evidence**: schema literal = `v4`，artifact version = `5`。
- **impact**: 语义不同（LLM I/O 版本 vs 持久化版本），递增正确。
- **verdict**: accepted（注释已明确区别）

### F3 [LOW] `_resolve_compactor_response_identity` 全扫描 O(n)

- **severity**: LOW
- **file**: `tool_trace.py`
- **impact**: compaction 频率低（每几十轮一次），terminal 数量有实际上界。
- **verdict**: accepted（正确性优先）

---

## 测试证据

```
267 passed in 1.19s          # 受影响 host tests (contract/operation/terminal/events/memory/tool_trace)
pyright: 0 errors, 0 warnings, 0 informations
```

---

## Completion

F13 final PR review 完成：semantic owner 唯一、previous atom 原子保留、new fact
evidence-only 且 refs 非空、repair/exhaustion/fallback/stale/late/single-terminal
无污染、六端同源、schema/prompt 自足无泄漏、无 heuristic/compat/ledger/downstream
补偿/过度设计、真实 scenario evidence 诚实。3 个 low-risk finding 无阻塞。
