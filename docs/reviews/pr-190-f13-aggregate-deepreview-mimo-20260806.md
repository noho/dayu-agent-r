# PR 190 F13 Aggregate Deep Review — MiMo

**Base**: `2d914be` | **Head**: `b9908d9a` | **Scope**: 85 files, +9170/-2161
**Date**: 2026-08-06 | **Reviewer**: Claude Code (mimo-v2.5-pro)

---

## Decision: ACCEPTED

无 blocking/high/medium finding。3 个 low-risk finding 见下。

---

## 审查维度逐项核对

### 1. Semantic owner 唯一

| 语义 | owner | 验证 |
|------|-------|------|
| LLM output shape | `compact_structure` (descriptor→template/schema/parser 单源) | ✅ |
| input/proposal/replacement/truth types | `compaction.py` (frozen/slots/no defaults) | ✅ |
| proposal→replaced replacement | `context_governance` (`_COMPACT_ACCEPTANCE_PERMIT` 私有令牌) | ✅ |
| rolling prior atom | `compact_material` (逐 atom 复制 claim/refs) | ✅ |
| durable strict reconstruction | `compact_payload` (parser 重验全部 binding) | ✅ |
| Memory/reconnect/RunInput | accepted replacement read-model consumers | ✅ |
| Tool Trace | canonical terminal typed public projection consumer | ✅ |

无双真源、无 consumer 从 raw field 反推语义。

### 2. Previous atom claim+refs 原子保留

- `context_governance.py` retain selector：`claim = boundary[prev_label].readable_text`，`refs = boundary[prev_label].canonical_evidence_refs`，`selection_labels=(prev_label,)`，`context_labels=()`。
- 模型无旧 claim 字段路径（七字段 proposal 中无 `claim` 输入）。
- 测试 `test_compaction_contract.py` 断言 retained atom 与 boundary entry exact equal。

### 3. New fact current evidence-only 且 final refs 非空 / boundary exact

- `COMPACT_FACT_SOURCE_KINDS_V4 = (CompactSourceKindV4.EVIDENCE_MATERIAL,)`，new fact support 只允许 evidence。
- `__post_init__` 断言 `canonical_evidence_refs` 非空唯一 tuple。
- refs = `ordered_unique_union(boundary[label].canonical_evidence_refs for label in selection_labels)`，不读 aggregate。
- 测试覆盖：单源、双源 union、refs 越界、空 refs、previous label 塞入 support 全部 typed reject。

### 4. Repair / exhaustion / fallback / stale / late / single-terminal 无污染

- `compaction_operation.py`：每次 repair 从 strict parse 重新执行完整 binding 链。
- exhaustion → one failed terminal + existing fallback，不物化 accepted artifact/Memory。
- stale/late → terminal commit owner 返回 no-op，不创建第二 terminal。
- 测试 `test_compaction_operation.py` 覆盖 cancellation-between-attempts、all-invalid-exhaust、root-hard-budget-reject。

### 5. Artifact / EventLog / Memory / reconnect / RunInput / ToolTrace 同源

- `CONTEXT_COMPACTED` payload 含 `accepted_proposal` + `accepted_replacement` + internal boundary + coverage + audit + aggregate refs。
- `compact_payload.py` strict parser 重验 proposal↔boundary↔replacement 全部绑定。
- `memory.py` 逐 fact 读取 `accepted_replacement.evidence_facts[i].canonical_evidence_refs`，不把 aggregate 赋给所有 facts。
- `tool_trace.py` resolver 调用同一 `parse_context_compacted_semantic_payload`，机械投影 claim/refs。
- reconnect 经同一 strict parser 恢复 replacement。

### 6. Schema / prompt 自足且无治理泄漏

- `conversation_compaction_user.md`：自足说明七字段、类型、必填性、allow kind、retain/omit、combined cap 数值例、最小 JSON。不暴露 event id、digest、payload ref、Host 模块名。
- `compact_structure.py`：prompt rules 与 JSON schema 从同一 descriptor 派生。
- `test_public_compact_smoke.py::test_default_compactor_prompt_is_llm_facing_self_contained` 验证禁止内部术语。

### 7. 无 heuristic / compat / ledger / downstream 补偿 / 过度设计

- 无 V3 alias / re-export / dual reader / migration shim。
- 无 entailment heuristic、drop ledger、第二 provenance service。
- 无 God object/function。
- `COMPACT_ARTIFACT_SCHEMA_VERSION_VNEXT = 5`，删除旧 `accepted_candidate` key。

### 8. Mandatory owner tests 1-11 核对

| # | 测试要求 | 覆盖 |
|---|---------|------|
| 1 | previous claim/refs exact 保留 | `test_compaction_contract` retained atom binding |
| 2 | previous label 塞入 new fact support reject | `test_compaction_contract` kind mismatch |
| 3 | 不相关 previous fact 无法进入 replacement | `test_compaction_contract` unknown label reject |
| 4 | refs 为空 / union 错配 / 越界 typed reject | `test_compaction_contract` + `test_context_compact_events` tamper |
| 5 | 无 evidence material 禁止 new fact | `test_compaction_contract` fact source kind reject |
| 6 | current evidence 逐 fact 持久化 | `test_compact_material` + `test_compaction_contract` |
| 7 | rolling + cap repair 保留 provenance | `test_compact_material` rolling + `test_compaction_contract` caps |
| 8 | repair exhaustion/fallback 无污染 | `test_compaction_operation` exhaustion |
| 9 | stale/late 不产生第二 terminal | `test_compaction_terminal` |
| 10 | artifact/EventLog/Memory claim+refs 同源 | `test_context_compact_events` + `test_memory_projection` |
| 11 | reconnect 只读 canonical replacement | `test_run_input_builder` |

### 9. Test / Host 真实 CLI 证据纪律

- 262 tests passed, 1 skipped (既有 skip，非本次变更)。
- Pyright 0 errors。
- Ruff `All checks passed!`。
- S1/S2 implementation artifact 明确声明：**"只形成 tests/Host integration/Host smoke 证据；未执行真实 provider 或 interactive CLI，不能声称真实行为通过"**。
- 未把 test/Host smoke 写成 formal interactive scenario 通过。

---

## Findings

### F1 [LOW] Fake compactor forward_intents / reference_continuity 空实现

- **Severity**: LOW
- **File**: `tests/host/fake_compaction.py:839-862`
- **Evidence**: `_fake_forward_intents_vnext()` 和 `_fake_reference_items_vnext()` 始终返回 `()`。
- **Impact**: 端到端 smoke 测试不经过这两个 section 的完整 compaction 流程。Contract 测试在 acceptance 边界已覆盖。
- **最小修法**: fake 至少构造一个 `CompactForwardIntentV4(status=OPEN)` 和一个 `CompactReferenceContinuityV4`。

### F2 [LOW] Artifact schema version 与 schema literal 数字不一致

- **Severity**: LOW
- **File**: `dayu/host/compact_payload.py`
- **Evidence**: schema literal = `v4`，artifact version = `5`。
- **Impact**: 语义不同（前者=LLM I/O 格式版本，后者=持久化序列化版本），递增正确，但可能造成开发者混淆。
- **最小修法**: 无需修改；在 artifact 注释中明确两者区别即可。

### F3 [LOW] `_resolve_compactor_response_identity` 全扫描 O(n)

- **Severity**: LOW
- **File**: `dayu/host/durable/tool_trace.py:624-692`
- **Evidence**: 每次解析都全扫描 parent Host Run 的 compactor terminal events。
- **Impact**: compaction 频率低（每几十轮一次），terminal 数量有实际上界。当前正确性优先。
- **最小修法**: 当前无需修改；若未来频率增加可考虑 hot projection 索引。

---

## 测试证据

```
262 passed, 1 skipped in 1.30s          # 受影响 host tests
pyright: 0 errors, 0 warnings           # 完整 pyright
ruff: All checks passed!                 # changed-file ruff
```

## Completion signal

F13 aggregate deepreview 完成：semantic owner 唯一、previous atom 原子保留、new fact evidence-only 且 refs 非空、repair/exhaustion/fallback/stale/late/single-terminal 无污染、artifact/EventLog/Memory/reconnect/RunInput/ToolTrace 同源、schema/prompt 自足无泄漏、无 heuristic/compat/ledger/downstream 补偿/过度设计。3 个 low-risk finding 无阻塞。
