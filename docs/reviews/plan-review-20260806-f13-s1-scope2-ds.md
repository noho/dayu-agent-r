# F13 S1 Scope Amendment 2 — Independent Plan Review (AgentDS)

- **reviewed artifact**: `docs/gateflow/pr-190-f13-s1-scope-amendment-2-20260806.md` + accepted plan 当前 diff（base `ab1207f12706c`）
- **reviewer**: AgentDS
- **date**: 2026-08-06
- **conclusion**: `accepted`（一条 low-severity gap note，不阻塞 S1 实现；见 F4）

## 审查范围与方法

独立扫描核验 amendment 的三项核心主张：

1. runtime test 的 v3 literal 确是 active fixture，且配套 utils smoke helper 已进 v4。
2. 全仓 `tests/` 除负向断言外无遗漏 active v3 literal。
3. 机械迁移边界不扩展 runtime 业务语义，residue rule 精确。

扫描方法：

- `git diff --stat` 确认 S1 allowed files 当前 diff 变更集。
- `grep -rn "input.v3\|output.v3\|context_compaction.input.v3\|context_compaction.output.v3\|COMPACT_INPUT_SCHEMA_V3\|COMPACT_OUTPUT_SCHEMA_V3" --include="*.py" .` 全仓 active v3 literal/symbol 扫描。
- `grep -rn "V3\|_V3" dayu/host/ --include="*.py"` 确认生产代码 v3 符号已全部清除。
- 逐文件审查 `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` 与 `utils/smoke_host_public_conversation_memory_scenarios.py` 的 v4 迁移完整性与一致性。

---

## F1: Runtime test active v3 literal 识别准确，机械迁移边界合理

**Evidence**:

```
tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:1096:
    "schema": "dayu.context_compaction.input.v3",

tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:1120:
    assert parsed["schema"] == "dayu.context_compaction.output.v3"
```

这两行位于 `test_fake_compactor_proposal_does_not_echo_material_markers`（行 1088-1137），被测对象是 `_fake_compaction_proposal_from_material_json`——该 helper 在 S1 allowed files 中，且当前 diff 已迁移到 v4：

- `COMPACT_OUTPUT_SCHEMA_V3` → `COMPACT_OUTPUT_SCHEMA_V4`（行 111）
- `CompactSourceKindV3` → `CompactSourceKindV4`（全部 source kind 分支）
- `CompactForwardIntentStatusV3` → `CompactForwardIntentStatusV4`（行 2286）
- 输出 `"schema": COMPACT_OUTPUT_SCHEMA_V4`（行 2257）

但 runtime test 未被列入 S1 original allowed tests，导致它仍构造 v3 输入、断言 v3 输出——在 helper 切 v4 后必然失败。

**迁移范围**：

- 输入 JSON `"dayu.context_compaction.input.v3"` → `"dayu.context_compaction.input.v4"`
- 输出断言 `"dayu.context_compaction.output.v3"` → `"dayu.context_compaction.output.v4"`
- root exact keys set（行 1124-1131）增加 `"retained_previous_evidence_fact_labels"`（v4 七字段必填之一，当前仅六字段）
- 不改变 `_SMOKE_REACTIVE_OLD_MARKER` 断言、`source_labels`/`support_labels` 映射或 `represented_labels` 并集逻辑

**结论**: Amendment 对 active v3 literal 的定位准确（line 1096/1120），scope 限制为 input/output schema + required selector + exact key 断言的纯机械迁移，不扩展 runtime 业务语义。✅ **通过**。

---

## F2: 全仓 active v3 contract residue scan 确认无误

**Evidence**:

全仓扫描命令覆盖 `.py` 文件，排除 `.venv/` 与 `__pycache__`：

```bash
grep -rn "input\.v3\|output\.v3\|COMPACT_INPUT_SCHEMA_V3\|COMPACT_OUTPUT_SCHEMA_V3" \
  --include="*.py" .
```

结果仅 4 处命中：

| 文件 | 行 | 内容 | 性质 |
|------|-----|------|------|
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | 1096 | `"dayu.context_compaction.input.v3"` | **active fixture** → 需迁移 |
| `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` | 1120 | `"dayu.context_compaction.output.v3"` | **active assertion** → 需迁移 |
| `tests/service/test_host_assembly.py` | 335 | `assert "dayu.context_compaction.input.v3" not in ...` | **negative assertion** → 保留 |
| `tests/service/test_host_assembly.py` | 336 | `assert "dayu.context_compaction.output.v3" not in ...` | **negative assertion** → 保留 |

补充确认：

- `grep -rn "V3\|_V3" dayu/host/ --include="*.py"` 生产代码零命中（所有 v3 Python symbol 已删除）。
- `tests/service/test_host_assembly.py` 不在当前 diff 中，其负向断言测试"旧 v3 schema 不出现在 system prompt 中"的业务意图在 v4 迁移后仍然有效。
- 无其他 `tests/` 文件引用 v3 schema literal 或 v3 Python symbol。

**结论**: Amendment 的 "除负向断言外，全仓零 active v3 literal 残留" 声明通过独立扫描核验。✅ **通过**。

---

## F3: 负向断言排除精确，residue rule 细化有据

**Evidence**:

`tests/service/test_host_assembly.py:335-336` 的两条断言：

```python
assert "dayu.context_compaction.input.v3" not in compactor_baseline.compactor_system_prompt
assert "dayu.context_compaction.output.v3" not in compactor_baseline.compactor_system_prompt
```

语义分析：

- 断言目标是 `compactor_system_prompt`——一个由当前 compactor scene prompt（v4）生成的 system prompt 文本。
- 断言性质是 **absence assertion**（验证旧 schema 不出现在新 prompt 中），不是 **presence assertion**（验证某 schema 出现）。
- 该测试的 owner 语义是 "fresh v4 prompt 不泄漏旧 contract"；v3→v4 migration 完成后，这个语义依然正确且应继续验证。
- 若改成断言 v4 不存在，反而与 prompt 实际内容矛盾。

Amendment 将 residue rule 从 "任何字符串零命中" 精确为 "active v3 contract 零命中"，明确 reject/absence negative assertions 可保留。该细化与原 plan S1 residue rule（"明确断言旧schema字符串'不存在/被拒绝'的negative tests可以保留并须在residue artifact逐项列明"）一致，且更精确地定义了 active vs. negative 的区分标准。

**结论**: 负向断言排除逻辑成立，residue rule 精确化提升可核验性。✅ **通过**。

---

## F4: smoke helper v4 迁移不完整——`retained_previous_evidence_fact_labels` 缺失 **[LOW]**

**Evidence**:

`utils/smoke_host_public_conversation_memory_scenarios.py` 的 `_fake_compaction_proposal_from_material_json`（行 2256-2299）当前 diff 已迁移到 v4 schema，但其输出 JSON 仅含六键：

```python
proposal: dict[str, JsonValue] = {
    "schema": COMPACT_OUTPUT_SCHEMA_V4,
    "session_summary": (...),
    "evidence_facts": [...],
    "answer_anchors": [...],
    "forward_intents": [...],
    "reference_continuity": [...],
}
```

缺失 `"retained_previous_evidence_fact_labels"`。v4 contract（accepted plan §2）规定此字段 **必填**，即使空数组也必须出现：

> `retained_previous_evidence_fact_labels` 必填，类型为唯一字符串数组，只能引用 `previous_evidence_fact`；Host 按 source boundary 顺序 canonicalize。空数组表示省略所有旧 facts。

同时 `_invalid_current_anchor_citation_proposal`（行 2324-2334）同样缺失该字段。

**影响分析**：

1. 若 runtime test 机械迁移后增加 `retained_previous_evidence_fact_labels` 到 root exact keys set（见 F1），则该测试会因 helper 输出不包含此字段而 **断言失败**。这是一条"迁移后测试会暴露 helper 缺陷"的良性交互，不阻塞迁移本身。
2. smoke helper 在 S1 allowed files 中（`utils/smoke_host_public_conversation_memory_scenarios.py（只迁移v4/schema-5 call site）`），其 v4 迁移完整性本就是 S1 职责。该 gap 应在 S1 实现中一并修复。
3. 这不是 amendment scope 缺陷——amendment 只负责将 runtime test 纳入 S1 allowed files，不负责检查 helper 迁移是否完整。但作为 reviewer 应 preventively flag 此 gap，避免 S1 implementer 遗漏。

**建议**（非阻塞）：S1 实现时同步为两个 smoke helper 函数补充 `"retained_previous_evidence_fact_labels": []`（当无 previous facts 时为空数组）。

**结论**: 非 amendment 缺陷，是 smoke helper S1 迁移遗漏的预防性发现。不影响 amendment acceptance。⚠️ **Low-severity note**。

---

## F5: S1 scope 扩展有限且不引入新风险

**Evidence**:

Amendment 对 S1 allowed files 的唯一变更：

```diff
+ tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py（只迁移配套smoke的v4 schema/selector断言）
```

核验：

- **不新增 production file**：仅增加一个 test file。
- **不改变 S1/S2 边界**：S2 仍拥有 Tool Trace 新语义与断言；runtime test 迁移属于机械 contract migration，不涉及 Tool Trace。
- **不引入 compatibility/alias/dual-path**：迁移仅改 schema literal 字符串与 root exact keys set，无新兼容分支。
- **Goal 不变**：目标仍为 "Host compact v4 纵向切换"，runtime test 只是配套 smoke helper 迁移的遗漏补全。
- **atomic commit 不变**：仍在同一 S1 accepted commit 内完成，不拆分为可提交的 sub-slice。
- **C1-C3 cluster 可自然覆盖**：runtime test 是 smoke helper 的 consumer test；C3（步骤 5-6，rolling/memory/reconnect + call sites）或各 cluster 的整体 focused test run 可覆盖机械迁移后的回归验证。

**结论**: S1 scope 扩展符合最小化原则，不引入架构风险或边界模糊。✅ **通过**。

---

## F6: 迁移后 runtime test 将 serve 为 helper v4 完整性的 consumer-side guard

**Interaction note**（非独立 finding，是 F1 + F4 的交互结论）：

runtime test 的 `test_fake_compactor_proposal_does_not_echo_material_markers` 在机械迁移（增加 `retained_previous_evidence_fact_labels` 到 root exact keys set）后，会因 smoke helper 尚缺该字段而失败。这不是 migration 错误——恰恰是这个测试充当了 helper v4 完整性的 consumer-side check。S1 implementer 应：

1. 先补全 smoke helper 的 `retained_previous_evidence_fact_labels` 输出。
2. 再迁移 runtime test 的 schema + selector + exact keys 断言。
3. 最终二者一致通过。

这是健康的 test-contract 反馈循环，不需要额外的兼容分支或临时跳过逻辑。

---

## 汇总

| Finding | Severity | Verdict |
|---------|----------|---------|
| F1: Runtime test v3 literal 识别准确 | — | ✅ pass |
| F2: 全仓 residue scan 无误 | — | ✅ pass |
| F3: 负向断言排除精确 | — | ✅ pass |
| F4: Smoke helper missing `retained_previous_evidence_fact_labels` | Low | ⚠️ note（不阻塞） |
| F5: S1 scope 扩展可控 | — | ✅ pass |
| F6: Consumer-side guard 交互 | — | 💡 note |

**Overall conclusion**: `accepted`。Amendment 三项核心主张均通过独立扫描核验。F4 是 smoke helper S1 迁移遗漏的预防性发现，不属于 amendment scope 缺陷，不阻塞 amendment acceptance 或 S1 实现。C3 residue artifact 应逐项列明 `tests/service/test_host_assembly.py:335-336` 两条保留负向断言。
