# PR 190 F13 S1 Scope Amendment 2 — MiMo Plan Review

## Review metadata

- reviewer: AgentMiMo
- artifact: `docs/gateflow/pr-190-f13-s1-scope-amendment-2-20260806.md`
- base: accepted plan (`docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md`)
- scope: S1 allowed tests completeness, residue rule precision
- decision: **pass**

## Verification results

### Finding 1: Runtime test active v3 literals — confirmed

amendment 声称 `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` 存在 active v3 literal。

**验证**：

- 行 1096：构造 input 时使用 `"schema": "dayu.context_compaction.input.v3"` — 确认为 active literal，非 negative assertion。
- 行 1120：`assert parsed["schema"] == "dayu.context_compaction.output.v3"` — 确认为 active output schema 断言。
- 行 1124-1131：root exact keys 断言 `set(parsed)` 缺少 `retained_previous_evidence_fact_labels`（v4 retain selector 字段）。
- 被测函数 `_fake_compaction_proposal_from_material_json`（utils 行 2257）已使用 `COMPACT_OUTPUT_SCHEMA_V4`（`dayu.context_compaction.output.v4`），因此 utils helper 切到 v4 后该 test 必然失败。

**结论**：amendment 事实准确。该 test 确实是已纳入 S1 allowed tests 的 utils smoke 配套 active fixture。

### Finding 2: test_host_assembly.py negative assertion — confirmed

amendment 声称 `tests/service/test_host_assembly.py:335-336` 是 negative service assertion，不需要修改。

**验证**：

- 行 335：`assert "dayu.context_compaction.input.v3" not in compactor_baseline.compactor_system_prompt`
- 行 336：`assert "dayu.context_compaction.output.v3" not in compactor_baseline.compactor_system_prompt`

这两行断言 v3 schema 字符串**不出现**在 system prompt 中，属于 reject/absence negative assertion。它们不构造 v3 input、不期待 v3 output、不提供兼容 reader，符合 accepted plan 的 negative assertion exception 规则。

**结论**：amendment 分类正确。

### Finding 3: 全 tests 无其它遗漏 active v3 literal — confirmed

amendment 声称除上述 runtime test 外，tests/ 未发现其它 active v3 literal。

**验证**（`grep -rn "context_compaction\.\(input\|output\)\.v3" tests/ --include="*.py"`）：

| 文件 | 行号 | 内容 | 分类 |
|---|---|---|---|
| `tests/runtime/...assembly.py` | 1096 | `"schema": "dayu.context_compaction.input.v3"` | active input literal |
| `tests/runtime/...assembly.py` | 1120 | `assert parsed["schema"] == "dayu.context_compaction.output.v3"` | active output assertion |
| `tests/service/test_host_assembly.py` | 335 | `assert "..." not in ...` | negative assertion (保留) |
| `tests/service/test_host_assembly.py` | 336 | `assert "..." not in ...` | negative assertion (保留) |

无其它命中。

**结论**：amendment 声称完整。

### Finding 4: Residue rule 精确化 — 合理

amendment 将 residue rule 从"任何字符串零命中"精确为"active v3 contract 零命中"，并明确 reject/absence negative assertions 可保留。

**评估**：

- "任何字符串零命中"过于严格，会误杀合法的 negative test（如断言旧 schema 不出现在 prompt 中）。
- "active v3 contract 零命中"精确区分了 active reader/fixture（必须迁移）和 negative assertion（可保留）。
- 与 accepted plan S1 步骤 6 的 "明确断言旧schema字符串'不存在/被拒绝'的negative tests可以保留并须在residue artifact逐项列明" 一致。

**结论**：residue rule 精确化合理，与 accepted plan 一致。

## Overall assessment

| 维度 | 评估 |
|---|---|
| 事实准确性 | pass — 所有声称均可由直接代码证据验证 |
| S1 allowed tests 完整性 | pass — runtime test 确为配套 active fixture，需要迁移 |
| Negative assertion 边界 | pass — test_host_assembly.py 断言正确分类为 negative assertion |
| Residue rule 精确化 | pass — 与 accepted plan 一致，避免误杀 |
| Goal/owner impact 不变 | pass — 不新增 compatibility、alias 或测试专用生产分支 |

## Decision

**pass**。amendment 事实准确、边界精确、与 accepted plan 一致。无 blocking/high/medium finding。
