# Plan Review: PR 190 F13 S1 Allowed-test Scope Amendment

- Reviewer: MiMo (adversarial)
- Date: 2026-08-06
- Base: 7bfe36f928b9e00d8f72a3d1b7a6dc08f6b751d6
- Target: `docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md` (diff) + `docs/gateflow/pr-190-f13-s1-scope-amendment-20260806.md`

## Methodology

对 `dayu/` 和 `tests/` 执行 v3 symbol 全仓 `rg` 扫描（`CompactForwardIntentStatusV3`、`CompactSourceKindV3`、`compact_output_caps_v3_from_memory_policy`、`COMPACT_OUTPUT_SCHEMA_V3`、`PromptLocalProvenanceEntry.accepted_evidence_id`、`accepted_candidate`），逐文件复核 amendment 声称的 6 个直接引用，并交叉验证原 allowed list 13 个文件是否已覆盖所有 v3 引用者。

---

## Findings

### F1. test_tool_trace_queries.py 直接证据确认 — 但 amendmnet 描述可更精确

**Severity**: Low (informational)

**Claim**: "v3 candidate/schema fixture"

**Evidence**:
- `tests/host/test_tool_trace_queries.py:85` — `import COMPACT_OUTPUT_SCHEMA_V3`
- `tests/host/test_tool_trace_queries.py:952` — `schema=COMPACT_OUTPUT_SCHEMA_V3`
- `tests/host/test_tool_trace_queries.py:1407` — `accepted_candidate = compacted_payload["accepted_candidate"]`

**Verdict**: 直接引用 **confirmed**。`COMPACT_OUTPUT_SCHEMA_V3` 是将被删除的 v3 symbol（定义于 `dayu/host/compaction.py:32`），`accepted_candidate` 是 v3 compact payload 的 key。amendment 说"v3 candidate/schema fixture"准确，但若写成"`COMPACT_OUTPUT_SCHEMA_V3` import 与 fixture 中的 `accepted_candidate` key"会更精确，与其它 5 个文件的描述粒度一致。

---

### F2. test_tool_trace_queries.py S1/S2 所有权分割 — 合理

**Severity**: Pass (no issue)

**Claim**: "S1只迁移被删除v3 symbol与schema-5 fixture；S2仍拥有public Tool Trace新语义与断言"

**Analysis**:
- S1 scope：删除 `COMPACT_OUTPUT_SCHEMA_V3` import → 替换为 v4 schema；删除/迁移 `accepted_candidate` fixture。这是纯粹的机械替换。
- S2 scope：public Tool Trace 逐 fact projection 与新断言。这是新语义实现，不属于 v3→v4 迁移。
- 两个 scope 在该文件中无重叠：S1 只改 v3 symbol 引用，S2 只增新测试逻辑。

**Boundary statement 验证**: "S2明确拥有的README/public Tool Trace新projection文字在S2完成最终全文扫描，不能成为S1保留已删除Python symbol或旧fixture的理由" — 正确。S2 的 README 职责不能成为 S1 保留已删除 symbol 的借口。

---

### F3. Residue scan 范围收窄至 Python — 安全但需注意边界

**Severity**: Low (informational)

**Claim**: 原 plan step 6 的 "全仓 `rg`" 收窄为 "`dayu/**/*.py`与`tests/**/*.py`"

**Evidence**:
- 对非 Python 文件执行 `rg -l 'CompactForwardIntentStatusV3|CompactSourceKindV3|compact_output_caps_v3_from_memory_policy|COMPACT_OUTPUT_SCHEMA_V3' --type-not py dayu/ tests/` — **零结果**。
- 对 `dayu/config/` 执行 `rg -l 'v3.*compact|compact.*v3'` — 仅 `dayu/config/README.md`（S2 职责）。

**Verdict**: 收窄安全。v3 Python symbol 不在非 Python 文件中被引用。但需注意：
1. 收窄后的 scan 不覆盖 `.md`、`.yaml`、`.json` 等文件。当前无风险，但若未来 S1 迁移引入新的非 Python 产物（如 schema JSON），需重新评估。
2. `dayu/host/README.md` 按原计划留给 S2，不在 S1 residue scan 范围内，这是正确的。

---

### F4. "生产allowed scope未发现新的遗漏" — 声明准确

**Severity**: Pass (no issue)

**Claim**: 扫描 `dayu` 与 `tests/host` 后，生产 allowed scope 无新遗漏；6 个新文件全是 test/helper。

**Evidence**:
- 生产文件 v3 引用者（`compact_payload.py`、`compact_pipeline.py`、`compact_structure.py`、`compaction.py`、`context_governance.py`、`memory.py`）全部在原 plan 的生产 allowed list 中。
- 6 个新增文件全部是 `tests/host/` 下的 test/helper，不在生产 scope。

**Verdict**: 准确。"生产allowed scope"指 plan 的"Allowed production files"小节，该小节无新增项。

---

### F5. 原 allowed list 已覆盖的文件同样重度使用 v3 — 非遗漏但值得注意

**Severity**: Informational (no issue with amendment)

**Observation**: 原 plan 的 13 个 allowed test 文件中，以下文件重度使用 v3 symbols，与 amendment 新增的 6 个文件性质相同：

| File | v3 symbols used |
|------|----------------|
| `fake_compaction.py` | CompactSourceKindV3 (20+), compact_output_caps_v3_from_memory_policy, COMPACT_OUTPUT_SCHEMA_V3 |
| `test_compaction_contract.py` | CompactForwardIntentStatusV3, CompactSourceKindV3, compact_output_caps_v3_from_memory_policy, COMPACT_OUTPUT_SCHEMA_V3 |
| `test_compact_material.py` | CompactForwardIntentStatusV3, CompactSourceKindV3, compact_output_caps_v3_from_memory_policy |
| `test_public_compact_smoke.py` | CompactForwardIntentStatusV3, CompactSourceKindV3, compact_output_caps_v3_from_memory_policy, COMPACT_OUTPUT_SCHEMA_V3 |
| `test_llm_compaction.py` | CompactSourceKindV3, compact_output_caps_v3_from_memory_policy, COMPACT_OUTPUT_SCHEMA_V3 |

这说明原 plan 的初始扫描已正确识别大部分 v3 引用者。amendment 的 6 个文件是初始扫描的补充，不是 scope expansion。

---

### F6. PromptLocalProvenanceEntry.accepted_evidence_id residue scan — 正确区分 singular/plural

**Severity**: Pass (no issue)

**Claim**: residue scan 要求"不得残留 `PromptLocalProvenanceEntry.accepted_evidence_id` 的定义/构造/读取"；同时允许"其它上游 typed accepted-evidence atom仍合法使用 singular `accepted_evidence_id`"。

**Evidence**:
- `PromptLocalProvenanceEntry` 定义于 `dayu/host/compaction.py:236`，其 `accepted_evidence_id` 字段在 `compaction.py:297,324,327` 有校验逻辑。
- `tests/host/test_run_input_builder.py` 等文件使用的 `accepted_evidence_id` 是其它类型的字段（如 evidence block 的属性），不是 `PromptLocalProvenanceEntry` 的字段。
- residue scan 的限定语"若其它上游 typed accepted-evidence atom仍合法使用 singular `accepted_evidence_id`，必须逐处确认其不是 material-pack下游读路径并在checkpoint artifact记录"提供了安全阀。

**Verdict**: singular/plural 区分正确。`PromptLocalProvenanceEntry.accepted_evidence_id` 是 v3 遗留字段（将迁移到 `canonical_source_refs`），而其它类型的 `accepted_evidence_id` 可能仍然合法。

---

### F7. 未发现遗漏文件

**Severity**: Pass (no issue)

**Verification**: 全仓 `rg` 扫描所有引用 v3 symbols 的 test 文件（19 个），全部在原 allowed list（13 个）+ amendment 新增（6 个）中，无遗漏。

完整清单：
- 原 list 13 个：fake_compaction, test_compact_artifact_store, test_compact_material, test_compact_pipeline, test_compaction_contract, test_compaction_terminal, test_context_compact_events, test_llm_compaction, test_memory_projection, test_run_input_builder, test_dispatch_scheduler, test_engine_ingest_mapping, test_public_compact_smoke
- 新增 6 个：memory_snapshot_factories, test_accepted_result_projection, test_compaction_cancellation_scope, test_compaction_operation, test_proactive_compaction_operation, test_tool_trace_queries

---

## Conclusion

**Overall verdict: Amendment 成立，无阻断性问题。**

7 个 findings 中：
- **0 Critical / High**
- **0 Medium**
- **2 Low** (F1 描述精度、F3 scan 范围边界注意)
- **5 Pass / Informational**

Amendment 的核心主张（6 个文件有直接 v3 引用、需加入 S1 allowed list、residue scan 收窄至 Python 安全、S1/S2 所有权分割合理）全部经证据验证。建议实施时将 F1 的描述精度作为 nice-to-have 改进。
