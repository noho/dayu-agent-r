# Plan Re-review: PR190 F13 S1 Scope Amendment — DS Rereview

- **reviewer-confirmation**: AgentDS independently verified all findings, evidence, and conclusions in this artifact.

- **review type**: `planreview` — 针对 Controller 裁决与 amendment 更新的逐 finding re-review
- **base review**: `docs/reviews/plan-review-20260806-f13-s1-scope-ds.md`（7 findings）
- **adjudication**: `docs/gateflow/pr-190-f13-s1-scope-review-adjudication-20260806.md`
- **updated amendment**: `docs/gateflow/pr-190-f13-s1-scope-amendment-20260806.md`
- **updated plan diff**: `docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md` vs `7bfe36f9`
- **reviewer**: AgentDS
- **date**: 2026-08-06
- **conclusion**: **全部 finding 已 FIXED 或 PASS**；零 STILL OPEN；amendment 可接受

---

## 计数更正记录

原 DS review 对 `utils/smoke_host_public_conversation_memory_scenarios.py` 使用 regex `Compact.*V3`（大小写敏感）仅命中 11 处引用（`CompactSourceKindV3` 与 `CompactForwardIntentStatusV3`），遗漏了 `COMPACT_OUTPUT_SCHEMA_V3`、`CompactCandidateV3` 等全大写 schema constant 命中——这是 regex 大小写敏感性导致的漏计。

Controller 按完整 residue pattern 更正为 **14 处**（conversation memory smoke）+ **4 处**（r03 semantic ownership）= **总计 18 处**。Amendment line 17 已更新为 14 处，裁决 line 17 明确标注"原review的15处计数未覆盖全部schema/candidate命中，Controller按完整residue pattern更正"。

本 rereview 以更正后的 18 处为准。

---

## 逐 Finding 对照核实

### Finding 1 — C1 import-breakage → FIXED

**原 finding**（HIGH）：C1 步骤1-2 删除 v3 后，`compaction_operation.py`（14 v3 type import）+ `context_governance.py`（28 v3 symbol import）传递导入断裂，focused tests 无法 collection。

**裁决**：ACCEPT / FIXED

**核实**：
- Plan diff：新增"步骤1删除v3 symbol会立即影响`compaction_operation`与`context_governance`等调用方，因此C1-C3是**完整、可收集的最终S1 worktree上的审查cluster**"
- Plan diff：C1-C3 从"运行 contract/LLM focused tests"更新为"在**同一完整S1 worktree上**运行 contract/LLM focused tests"
- Plan diff：新增硬约束"任何迁移中的中间态不声称可运行、可部署或可提交；只有完整S1 worktree才进入C1-C3验证"
- Amendment line 25：cluster 方案完整编码

**DS 结论**：**FIXED**。

---

### Finding 2 — 6 个 Host test/helper 遗漏 → FIXED

**原 finding**（LOW）：amendment 声称的 6 个文件全部有直接 v3 symbol 引用，证据可核实。

**裁决**：ACCEPT / FIXED

**核实**：Plan diff 已将 6 个文件加入 S1 allowed tests/helpers。Amendment lines 11-16 逐文件列明证据。

**DS 结论**：**FIXED**。

---

### Finding 3 — test_tool_trace_queries → PASS（重叠）/ FIXED（证据精度）

**原 finding**（LOW）：S1/S2 边界清晰，不构成双 owner。原 amendment 证据描述为"v3 candidate/schema fixture"不够精确。

**裁决**：PASS（重叠）/ ACCEPT / FIXED（证据精度）

**核实**：
- Amendment line 16：精简为 3 个具体 symbol——`COMPACT_OUTPUT_SCHEMA_V3`、`CompactCandidateV3`、`CompactSessionSummaryV3` 及其 fixture 构造
- Base 实际引用：line 85 `COMPACT_OUTPUT_SCHEMA_V3`、line 86 `CompactCandidateV3`、line 87 `CompactSessionSummaryV3`、lines 951-953 fixture——精确匹配 ✅
- Plan line 295 的 S1/S2 边界描述保持不变："S1只迁移被删除v3 symbol与schema-5 fixture；S2仍拥有public Tool Trace新语义与断言"

**DS 结论**：
- 重叠 concern → **PASS**
- 证据精度 → **FIXED**

---

### Finding 4 — utils/ residue scan gap（含计数更正）→ FIXED

**原 finding**（MEDIUM）：两个 `utils/` smoke 文件引用了 15 处 v3 symbol（原 DS 使用大小写敏感 regex 计数 11+4），被 residue scan scope 排除。原建议"在 C3 checkpoint 显式记录"。

**裁决**：ACCEPT / FIXED。Controller 拒绝"仅记录为 residual risk"——要求纳入 scope 并扩大 scan；同时更正计数为 18 处（14+4）。

**核实**：
- Amendment line 17：更正为 14 处 v3 source/status/schema/candidate call site
- Amendment line 18：保持 4 处 v3 source/caps call site
- 总计 18 处
- Plan diff：两个 utils/ smoke 加入 S1 allowed helpers（"只迁移v4/schema-5 call site"，"只迁移v4 call site"）
- Plan diff：residue scan 从 `dayu/**/*.py`与`tests/**/*.py` 扩展为 `dayu/**/*.py`、`tests/**/*.py`与`utils/**/*.py`
- Amendment line 24："把S1 residue scan限定为全部Python production/test/helper contract"

**DS 自评**：Controller 的裁决将"记录 risk"升级为"纳入 scope + 扩大 scan"，消除了 S3 observation 被 broken utils/ import 阻塞的风险，且符合 AGENTS owner 约束（禁止下游补偿、禁止局部 fallback）。原计数的 3 处漏计已在 amendment 与裁决中更正。

**DS 结论**：**FIXED**。

---

### Finding 5 — 遗漏文件扫描 → PASS

**原 finding**（LOW）：`dayu/` 非 host 目录与 `tests/` 非 host 目录无 v3 contract 遗漏；`derive_accepted_evidence_id` 是合法上游 atom。

**裁决**：PASS

**核实**：无新发现。amendment 与计划更新未暴露新遗漏文件。

**DS 结论**：**PASS**。

---

### Finding 6 — Cluster 验证强度 → PASS

**原 finding**（LOW）：cluster 方案不削弱 checkpoint 验证强度。

**裁决**：REJECT WITH EVIDENCE —— Controller 拒绝"cluster 削弱 checkpoint"的 concern。

**核实**：
- Plan diff：C1-C3 全部更新为"在同一完整S1 worktree上"
- Plan diff：新增"任何迁移中的中间态不声称可运行、可部署或可提交；只有完整S1 worktree才进入C1-C3验证"
- 原 C1-C3 domain focus、checkpoint 互锁机制（后续步骤触碰到覆盖文件则前置 checkpoint 失效）、双路 review——全部保留不变

**DS 自评**：原 review 的"潜在风险"指向 reviewer 在完整 diff 中定位 domain 变更的负担，不是对 cluster 方案本身的否定。Controller 的 REJECT 实质确认了原 review 的主结论（cluster 增强验证而非削弱）。

**DS 结论**：**PASS**。

---

### Finding 7 — Goal/architecture 不变 → PASS

**原 finding**（LOW）：amendment 不改变 confirmed Goal、schema shape、semantic owner、步骤顺序与 non-goals。

**裁决**：未显式列出（所有 accepted findings 的修复均在 plan completeness 范围内）

**核实**：Amendment lines 27-33 的 Goal and architecture impact 段落不变。8 个新增文件（6 Host test + 2 utils smoke）均为机械 owner-test/helper 迁移，无新增生产文件。

**DS 结论**：**PASS**。

---

## 裁决一致性总表

| 原 Finding | 原 Severity | 裁决 | 本次 | 备注 |
|-----------|------------|------|------|------|
| F1: C1 import-breakage | HIGH | ACCEPT / FIXED | **FIXED** | cluster 已写入 plan + amendment |
| F2: 6 文件遗漏 | LOW | ACCEPT / FIXED | **FIXED** | 全部加入 allowed scope |
| F3a: S1/S2 重叠 | LOW | PASS | **PASS** | 边界清晰 |
| F3b: 证据精度 | — | ACCEPT / FIXED | **FIXED** | 精简为 3 个具体 symbol |
| F4: utils/ residue gap | MEDIUM | ACCEPT / FIXED | **FIXED** | 纳入 scope + scan 扩到 utils/；计数 15→18 |
| F5: 遗漏文件扫描 | LOW | PASS | **PASS** | 无新遗漏 |
| F6: cluster 验证强度 | LOW | REJECT WITH EVIDENCE | **PASS** | 原主结论与裁决一致 |
| F7: Goal/architecture | LOW | — | **PASS** | 无变化 |

---

## Overall Conclusion

**全部 7 个 finding 已 FIXED 或 PASS，零 STILL OPEN。**

Amendment 与 plan diff 精确对应裁决中每项处理。所有修改严格限制在 plan completeness 修正范围内——不新增生产文件、不引入兼容层/alias/双路径。原 DS 计数的 3 处漏计（11→14）已在 amendment 与裁决中更正，本 rereview 以更正后的 18 处为准。

Amendment 可接受。S1 实现可以启动。
