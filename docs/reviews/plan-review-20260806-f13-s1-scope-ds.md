# Plan Review: PR190 F13 S1 Scope Amendment — Adversarial DS Review

- **review type**: `planreview` — adversarial plan amendment review
- **review target**: `docs/gateflow/pr-190-f13-s1-scope-amendment-20260806.md` + `docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md` diff (base: `7bfe36f9`)
- **reviewer**: AgentDS
- **date**: 2026-08-06
- **conclusion**: `pass-with-findings` — 1 medium finding on utils/ residue gap; all amendment claims verified; cluster fix is minimal and correct

---

## Review Scope

本次 review 覆盖 amendment 的全部 claim 与新增阻塞证据（C1 import-breakage + Controller cluster 裁决），逐 finding 给出 severity 与直接引用证据。不修改 plan 或代码。

---

## Finding 1 — C1 import-breakage 证据链完整，cluster 裁决最小正确

**Severity**: HIGH（已由 Controller 正确裁决，无 blocking residue）

### 证据

Amendment line 7 声称 C1 步骤1-2 后 "contract/LLM tests 无法在 test collection 前通过"。

**导入链复核**（全部来自 base `7bfe36f9`）：

1. `dayu/host/compaction_operation.py:36-54` 从 `dayu.host.compaction` 导入 14 个 v3 type：
   `CompactAcceptedTruthV3`, `CompactRepairFeedbackV3`, `CompactSessionSummaryV3`, `CompactSourceBoundaryEntryV3`, `CompactValidationReportV3`, `CompactValidationIssueCodeV3`, `CompactValidationIssueV3`, `CompactInputV3`, `CompactCandidateV3` 等。**C1 step1 删除 v3 后该模块 import 即失败**。

2. `dayu/host/context_governance.py:12-46` 从 `dayu.host.compaction` 导入 28 个 v3 symbol（type、常量、函数），包括 `CompactCandidateV3`, `CompactInputV3`, `CompactOutputCapsV3`, `compact_output_caps_v3_from_memory_policy`, `_COMPACT_ACCEPTANCE_PERMIT` 等。**C1 step1 后 import 即失败**。

3. `dayu/host/llm_compaction.py:67` → `from dayu.host.compaction_operation import CompactorProposalRunInput`。通过 (1) 的传递链，**C1 step1-2 后 import 即失败**。

4. `tests/host/test_compaction_contract.py:49` → 直接从 `dayu.host.compaction` 导入 v3 types；`:62-65` → 从 `dayu.host.context_governance` 导入 `compact_output_caps_v3_from_memory_policy`。**C1 step1 后 import 即失败**。

5. `tests/host/test_llm_compaction.py:40-41` → 从 `dayu.host.context_governance` 导入 `build_compact_repair_feedback_v3`, `compact_output_caps_v3_from_memory_policy`。**C1 step1 后通过 (2) 的传递链 import 即失败**。

**结论**：amendment 声称的 "只改C1四个文件会在test collection前失败" 直接成立。这不是理论风险——`compaction_operation.py` 和 `context_governance.py` 各自导入超过 14 个将被步骤1删除的 v3 symbol，且 `llm_compaction.py` 和 focused tests 通过它们形成传递导入依赖。

### Controller 裁决评估

Amendment line 22-23 的裁决：
> 保持S1单一原子migration与步骤1-6的依赖顺序，但把C1-C3定义为完整、可收集的最终S1 worktree上的审查cluster，而不是要求不可导入中间态运行测试的时间截面。第一次focused test前允许完成全部必要production/test call-site迁移；随后按cluster分别验证与双路review。

**最小性检查**：
- 不增文件、alias、lazy import、临时双 DTO ✓
- 不改变步骤 1-6 依赖顺序 ✓
- 唯一变化：验证执行时机从"中间时间截面"移到"完整 worktree 上的 domain cluster" ✓
- 替代方案（alias/lazy import/临时双路径）全部在 plan 中明确拒绝且违反 AGENTS owner 约束 ✓

**正确性检查**：
- C1-C3 的 domain focus 完全保留：C1 审 v4 dataclass/template/schema/prompt + contract/LLM tests；C2 审 material→boundary→governance→replacement→payload binding + provenance tests；C3 审 rolling/multi-pass/Memory/reconnect/call sites + projection tests + residue scan
- 在完整 worktree 上跑 focused tests 实际**增强**了验证质量：中间态因 import 失败根本无法跑任何 test，cluster 方案使每个 domain 的 focused tests 能真正执行并验证 contract
- 不削弱 step ordering 检查：步骤 1-6 依赖顺序仍然是 implementation 顺序；cluster review 验证的是最终产出的 domain 正确性
- S1 始终只有一个 accepted commit，不存在中间可提交 checkpoint，cluster 方案不改变这一点

**潜在风险**：cluster 方案要求 reviewer 在完整 worktree diff 中定位对应 domain 的变更。原 C1-C3 时间截面方案在概念上更容易隔离审阅范围。但 Controller 已在 plan 中要求 "每个checkpoint由Controller持久化审阅范围、base/worktree diff identity"——cluster 方案下该记录更关键。建议在 C1-C3 checkpoint artifact 中显式列出该 cluster 覆盖的具体文件/符号 diff 摘要。

**裁决**：Controller 的 cluster 方案是面对 C1 import-breakage 硬证据的唯一最小正确路径。不削弱验证；实际增强可执行性。不是 scope expansion。

---

## Finding 2 — Amendment 6 文件直接引用证据全部核实

**Severity**: LOW（证据充分，无遗漏）

### 逐文件核实

| 文件 | Amendment 声称的引用 | Base 实际引用 | 匹配 |
|------|---------------------|--------------|------|
| `tests/host/memory_snapshot_factories.py` | `CompactForwardIntentStatusV3` | Line 12: `CompactForwardIntentStatusV3`; Line 243: `CompactForwardIntentStatusV3.OPEN` | ✅ |
| `tests/host/test_accepted_result_projection.py` | `CompactSourceKindV3`, `compact_output_caps_v3_from_memory_policy` | Line 38: `CompactSourceKindV3`; Line 58: `compact_output_caps_v3_from_memory_policy`; Line 172/1382: 使用 | ✅ |
| `tests/host/test_compaction_cancellation_scope.py` | `compact_output_caps_v3_from_memory_policy` | Line 53: import; Line 502: 调用 | ✅ |
| `tests/host/test_compaction_operation.py` | v3 repair/validation types 与 caps/feedback helpers | Line 18-23: `CompactRepairFeedbackV3`, `CompactValidationIssueCodeV3`, `CompactValidationIssueV3`, `CompactValidationReportV3`; Line 36: `compact_output_caps_v3_from_memory_policy`; Lines 148-695: 多处使用 | ✅ |
| `tests/host/test_proactive_compaction_operation.py` | v3 caps helper | Line 57: `compact_output_caps_v3_from_memory_policy`; Line 171: 调用 | ✅ |
| `tests/host/test_tool_trace_queries.py` | v3 candidate/schema fixture | Line 85-87: `COMPACT_OUTPUT_SCHEMA_V3`, `CompactCandidateV3`, `CompactSessionSummaryV3`; Lines 951-953: 构造使用 | ✅ |

扫描命令复现：对 base commit 执行 `rg -l` v3 type/schema/function + `accepted_candidate` pattern on `dayu/` 与 `tests/host/`，命中 19 个文件，其中 13 个已在原 allowed list，6 个为此次新增。与 amendment 声称完全一致。

---

## Finding 3 — test_tool_trace_queries S1/S2 重叠合理

**Severity**: LOW（split 边界清晰，无语义冲突）

### 分析

`test_tool_trace_queries.py` 在 base 中引用：
- `COMPACT_OUTPUT_SCHEMA_V3`（line 85）— 会被 S1 step1 删除
- `CompactCandidateV3`（line 86）— 会被 S1 step1 删除
- `CompactSessionSummaryV3`（line 87）— 会被 S1 step1 删除
- Line 951-953：使用上述 symbol 构造 candidate fixture

S1 职责：机械迁移已删除 symbol → v4 等价物 + schema-5 fixture 更新。这是**存活必需的机械变更**——不修则文件无法 import。

S2 职责（plan line 344-366）：public Tool Trace 逐 fact projection、`ResolvedCompactorEvidenceFact`、`ToolTraceCompactorResponseSummary`、JSON/Markdown 同源渲染与新断言。

**重叠合理性**：
- S1 修改的是**被删除 symbol 的存活引用**（`CompactCandidateV3` → v4 等价）
- S2 新增的是**public Tool Trace 新语义**（projection、rendering、assertions）
- 两者操作的是同一文件的不同 concern：S1 做 delete-survival，S2 做 new-feature
- 不存在同一行代码的双 owner——S1 改 import/fixture，S2 加新 test function 与 assertion
- Plan line 295 的 S1/S2 职责描述足够精确："S1只迁移被删除v3 symbol与schema-5 fixture；S2仍拥有public Tool Trace新语义与断言"

Amendment line 16 的措辞与 plan line 295 一致。不削弱 S2 ownership。

---

## Finding 4 — Residue scan scope 排除 utils/ 可能掩盖生产残留

**Severity**: MEDIUM（非 production path，但应显式记录为 residual risk）

### 证据

原 plan line 304（amendment 前）：
> 全仓 `rg` 不得残留 v3 compact contract、旧 durable key或 `PromptLocalProvenanceEntry.accepted_evidence_id` 的定义/构造/读取

Amendment 后（plan line 304 diff）：
> ``dayu/**/*.py`与`tests/**/*.py`不得残留 v3 compact contract...

**被排除的目录**：`utils/`（分析辅助代码）、`docs/`（文档）、`workspace/`（临时脚本）。

**utils/ 实际 v3 残留**（base `7bfe36f9`）：

| 文件 | v3 引用数 | 具体内容 |
|------|----------|---------|
| `utils/smoke_host_public_conversation_memory_scenarios.py` | 11 处 | `CompactForwardIntentStatusV3` (import + line 2286 `.OPEN.value`), `CompactSourceKindV3` (import + lines 2224-2254: `.PREVIOUS_SESSION_SUMMARY`, `.TRACE_MATERIAL`, `.PREVIOUS_EVIDENCE_FACT`, `.EVIDENCE_MATERIAL`, `.PREVIOUS_ANSWER_ANCHOR`, `.ANSWER_MATERIAL`, `.PREVIOUS_FORWARD_INTENT`, `.PREVIOUS_REFERENCE_CONTINUITY`) |
| `utils/smoke_host_public_r03_semantic_ownership.py` | 4 处 | `CompactSourceKindV3` (import + line 1316: `.EVIDENCE_MATERIAL`), `compact_output_caps_v3_from_memory_policy` (import + line 1308: 调用) |

**影响评估**：
- S1 删除 v3 symbol 后，这两个 `utils/` 脚本将出现 **import 失败**
- 按 CLAUDE.md 分类，`utils/` 是"分析辅助代码"，默认无需测试、无覆盖率要求——不是 production path
- 但 amendment 将 scan 从"全仓"精确限定为 `dayu/**/*.py` + `tests/**/*.py`，**没有显式说明 utils/ 排除理由**

**与 plan 已有例外条款的关系**：plan line 304 的例外条款只覆盖"历史 evidence 文档"，不覆盖 `utils/` 下的活动 Python 脚本。`utils/` 的排除来自 scan scope 的 glob 限定，不是显式例外。

**风险**：
- 如果 S3 validation 依赖 `utils/smoke_host_public_r03_semantic_ownership.py` 做真实 provider observation（plan line 380-385 要求 "使用实际 provider configuration 与生产 Host compactor path"），则 broken import 会阻塞 S3 验证
- 反之，如果 S3 使用独立于 utils/ 的 observation 路径，则 utils/ breakage 是良性降级

**建议**：不要求修改 amendment。但要求在 S1 checkpoint artifact（C3 residue scan 记录）中显式列出 utils/ 排除决定、受影响的文件列表与 breakage 影响评估。如果 S3 真实运行依赖这些 utils smoke 脚本，应在 S2 或 S3 前将其升级到 v4。

---

## Finding 5 — production/test 遗漏文件扫描：dayu/ 与 tests/ 无遗漏

**Severity**: LOW（扫描覆盖完整）

### 扫描方法论

对 base `7bfe36f9` 执行三层扫描：

1. **直接 v3 symbol 引用扫描**：`CompactSourceKindV3`, `CompactForwardIntentStatusV3`, `CompactCandidateV3`, `CompactInputV3`, `CompactOutputCapsV3`, `CompactCurrentInputV3`, `CompactSourceBoundaryEntryV3`, `CompactValidationIssueCodeV3`, `CompactValidationIssueV3`, `CompactValidationReportV3`, `CompactRepairFeedbackV3`, `CompactSemanticSectionV3`, `CompactOmittedCoverageV3`, `CompactPolicyUsageAuditV3`, `CompactRepresentedCoverageV3`, `CompactRepresentedSourceV3`, `CompactAcceptedTruthV3`, `compact_output_caps_v3_from_memory_policy`, `accepted_evidence_id`, `accepted_candidate`

2. **`dayu/` 非 host 目录**（`:!dayu/host/` `:!dayu/config/`）：**零命中**。仅 `dayu/host/` 与 `dayu/config/` 内有 v3 引用，全部已在 S1 allowed production files 中。

3. **`tests/` 非 host 目录**（`:!tests/host/`）：`tests/runtime/test_smoke_host_public_r03_semantic_ownership_assembly.py` 引用 `derive_accepted_evidence_id`（`dayu.host.evidence`），这是**上游 typed accepted-evidence atom**，不是 `PromptLocalProvenanceEntry.accepted_evidence_id` 字段，不会被删除。Plan 已有显式例外条款覆盖此类。**无遗漏**。

4. **S1 production file 传递导入者扫描**：`dayu/service/host_assembly.py` 导入 `dayu.host.memory`，但不直接引用任何 v3 compaction symbol。S1 memory.py 的 contract 变更（`EvidenceBackedFactView` 从 v3 切换到 v4）可能影响 `host_assembly.py` 的类型推断，但 `host_assembly.py` 在 `dayu/` scan glob 内，residue scan 会捕获任何残留问题。

**结论**：amendment 声称 "生产allowed scope未发现新的遗漏" 对 `dayu/` 和 `tests/` 的 Python 文件成立。`utils/` 的排除见 Finding 4。

---

## Finding 6 — Cluster 方案不削弱 checkpoint 验证强度

**Severity**: LOW（方案增强验证可执行性）

### 分析

原 C1-C3 设计意图（plan line 307-320）：
- "为控制大 diff，S1 内增加三个**不提交**的强制验证/审查 checkpoint"
- 每个 checkpoint "由Controller持久化审阅范围、base/worktree diff identity、两路reviewer结论"
- "checkpoint通过后，若后续步骤修改其覆盖文件或owner contract，该checkpoint立即失效"

Cluster 方案下的等价性：
- C1-C3 仍然存在，仍然是三个不提交的审查 gate
- 每个 cluster 仍然有明确的 domain focus（dataclass、binding、consumers）
- "后续步骤修改覆盖文件导致 checkpoint 失效"的机制仍然有效——如果 C3 的修改破坏了 C1 已验证的 dataclass 不变量，C1 checkpoint 失效，必须基于新 diff 重跑
- 唯一差异：focused tests 在完整 worktree 上运行而非在中间不可导入态运行。这是**增强**，因为 tests 可以真正执行

**不削弱的原因**：原方案的时间截面从未被设计为"可提交 checkpoint"——它们始终在同一 S1 commit 内。中间态本就不可导入/不可运行。Cluster 方案承认这一事实，不再要求 reviewer 想象"如果可导入会怎样"。

**唯一新增的 reviewer 负担**：需要在完整 diff 中定位 cluster domain 的变更。Controller 的 checkpoint artifact 应显式列出该 cluster 覆盖的文件与关键符号 diff。

---

## Finding 7 — Amendment 不改变 Goal/architecture/schema owner

**Severity**: LOW（确认性检查）

Amendment line 24-31 声称：
- Confirmed Goal、schema shape、semantic owner、implementation 顺序与 non-goals 均不变
- 不新增生产文件、兼容层、alias、migration、heuristic 或 consumer fallback
- 扩充项全部是 owner test/helper 随 fresh contract 机械迁移

逐项核实：
- 6 个新增文件全部在 `tests/host/` 下，不涉及新的生产模块 ✓
- 每个文件的修改范围限定为"被删除 v3 symbol → v4 等价物"，不引入新业务语义 ✓
- S1 production allowed files 不变 ✓
- Plan 中 confirmed Goal（line 18-26，fresh compact v4，LLM proposal/Host accepted replacement 分离）未被 amendment 修改 ✓
- 不引入兼容层、alias、dual path ✓

---

## Residual Risk Summary

| Risk | Severity | Status |
|------|----------|--------|
| utils/ smoke scripts v3 breakage 未被 residue scan 覆盖 | MEDIUM | 记录；需在 C3 checkpoint 显式列出；若阻塞 S3 observation 需提前修复 |
| Cluster review 需 reviewer 在完整 diff 中定位 domain 变更 | LOW | C1-C3 checkpoint artifact 应显式列出 cluster 文件/符号列表 |
| S1 仍为单一大 commit，review 复杂度高 | LOW | 已在原 plan 中识别（line 436 "S1较大；以单一atomic contract migration控制风险"），cluster 方案缓解但未消除 |
| test_tool_trace_queries S1/S2 边界可能因实际实现细节模糊 | LOW | Plan line 295 已有精确限定；S2 reviewer 应验证 S1 未越界写入新 assertion |

---

## Overall Conclusion

**`pass-with-findings`**

Amendment 的所有 claim 经直接引用证据核实成立：
- 6 文件遗漏属实，全部是 owner test/helper 随 fresh contract 的机械迁移
- C1 import-breakage 证据链完整（compaction_operation 导入 14+ v3 type，context_governance 导入 28 v3 symbol），Controller 的 cluster 裁决是面对硬证据的唯一最小正确路径
- test_tool_trace_queries S1/S2 重叠边界清晰（S1 机械存活/S2 新语义），无 ownership 冲突
- dayu/ 与 tests/ Python 文件无遗漏

1 个 medium finding：`utils/` smoke scripts 的 v3 引用（共 15 处，2 个文件）被 residue scan scope 排除。不阻塞 acceptance，但需在 S1 C3 checkpoint artifact 显式记录排除决定，并评估是否阻塞 S3 真实 observation。
