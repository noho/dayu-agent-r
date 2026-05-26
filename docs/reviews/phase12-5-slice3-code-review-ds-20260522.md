# Phase 12.5 Slice 3 Code Review: Compaction Structured Candidate Contract And Accept Barrier

## 元信息

- **Review 类型**：深度代码审查（DeepReview），不修改生产代码或测试代码
- **基线**：e154c46 gateflow: accept phase 12.5 slice 2
- **审查范围**：未提交工作区变更（Slice 3 全部 diff）
- **计划文档**：docs/reviews/phase12-5-implementation-ready-plan-20260522.md
- **Slice 3 目标**：CompactionRequest 接收 accepted evidence envelope inputs；CompactionCandidate 增加 fact candidates / minimum preserve candidates；CONTEXT_COMPACTED payload 与 compact artifact schema 支持新字段；context_governance accept barrier 校验 shape/ref/bounds
- **审查日期**：2026-05-22

## 审查结论

**Slice 3 实现质量高，无 HIGH 或 MEDIUM 级别发现。** 契约一致性、边界校验、旧字段 fail-closed 和测试覆盖均达到 plan 要求。3 个 LOW 发现和 2 个 INFO 发现均为非阻塞项。

### 概要

| 维度 | 评估 |
|------|------|
| 契约正确性 | 通过 — accepted evidence -> fact candidate -> materialized fact 链路完整 |
| Schema/Event 一致性 | 通过 — compaction.py / context_events.py / compact_artifact.py 互相对齐 |
| 边界校验 | 通过 — claim_text/evidence_refs/count 边界全覆盖 |
| Old field fail-closed | 通过 — summary / preserved_fact_refs / quality_result 旧字段均有显式拒绝 |
| 测试覆盖 | 通过 — 50/50 测试通过，6 个新增 Slice 3 专项测试 |
| 类型安全 | 通过 — pyright 0 errors, 0 warnings |
| Scope 边界 | 通过 — 未触碰 LLMContextCompactor、memory projection、Service/Engine API |

---

## Findings

### LOW-1: `_summary_pretends_evidence_backed_fact` 的 `allowed_fact_refs` 语义精度

- **文件**：`dayu/host/context_governance.py:199`
- **证据**：
  ```python
  allowed_fact_refs = set(request.accepted_evidence_refs).union(
      set(request.evidence_backed_fact_refs)
  )
  return not set(summary.confirmed_fact_refs).issubset(allowed_fact_refs)
  ```
  `accepted_evidence_refs` 是 evidence 信封 id（`evidence:xxx`），不是 fact ref；`evidence_backed_fact_refs` 才是已有 fact ref。union 导致 `confirmed_fact_refs` 可以与 evidence id 匹配，但 summary 的 `confirmed_fact_refs` 语义是"本 episode 已确认的 fact refs"，不应引用 raw evidence 信封。
- **影响**：低。summary 是 informational 产物，不参与 fact materialization；summary 引用 evidence id 本身不构成安全漏洞，且 LLM compactor 在 Host 控制范围内。但这降低了 guard 精度，可能让 future bug 更难发现。
- **建议**：`allowed_fact_refs` 仅使用 `set(request.evidence_backed_fact_refs)`，移除与 `accepted_evidence_refs` 的 union。若 fake compactor/测试依赖当前行为，同步更新。
- **是否阻塞**：否。可在 Slice 4 或后续 polish pass 修复。

### LOW-2: `compact_artifact.py` 无旧 schema version 读路径守卫

- **文件**：`dayu/host/compact_artifact.py:35`
- **证据**：`_COMPACT_ARTIFACT_SCHEMA_VERSION` 从 1 升至 2，但 `compact_artifact_json` 和 `CompactArtifactStore.write_compact_artifact` 仅在写路径使用新 schema。当前模块无读路径，且旧 v1 artifact 缺少新增字段（`evidence_backed_fact_candidates`、`minimum_preserve_item_candidates` 等），若被新代码读取将导致 KeyError 或静默丢失数据。
- **影响**：低。本 Slice 不改写 artifact 读路径，该职责在 Slice 5（Memory Projection）中。但 residual risk 需要在 Slice 5 实施时显式处理。
- **建议**：在 Slice 5 的 memory projection / artifact reader 中增加 schema_version 字段校验，拒绝 v1 artifact 或显式报错（fail-closed）。当前不需要在本 Slice 改动。
- **是否阻塞**：否。已有 plan §4.9 要求 old durable snapshot fail-closed，此 risk 已分配至 Slice 5。

### LOW-3: `_fact_candidate_list_json` / `_minimum_preserve_candidate_list_json` 三处重复

- **文件**：
  - `dayu/host/compaction.py:1449-1476`
  - `dayu/host/context_events.py:510-537`
  - `dayu/host/compact_artifact.py:327-355`
- **证据**：完全相同的两个 helper 函数在三个模块中各实现一次，仅 import 上下文不同。
- **影响**：低。每个模块的 helper 是 module-private，不暴露为公共 API。但三处重复增加未来修改成本（如 candidate 字段变更需改 3 处）。
- **建议**：不需要立即处理。若后续 slice 发现更多重复，可考虑将 JSON codec helper 提升到 `compaction.py` 的公共 API 或专门 codec 模块。当前实现符合 Slice 3 的"最小改动"原则。
- **是否阻塞**：否。

---

## INFO 观察

### INFO-1: `_fact_candidates_accepted` 中的 `del request` 模式

- **文件**：`dayu/host/context_governance.py:359`
- `request` 参数在当前实现中未使用，通过 `del request` 显式标记。这是合理的 API 一致性选择（所有 accept barrier 函数统一接收 `request` + `candidate`），但可以加一行注释说明为什么保留该参数。

### INFO-2: `_single_fact_candidate_accepted` 中的二层 `claim_text.strip()` 校验

- **文件**：`dayu/host/context_governance.py:379`
- `EvidenceBackedFactCandidate.__post_init__` 已通过 `_require_bounded_non_empty_text` 校验 claim_text 非空。accept barrier 中的 `len(candidate.claim_text.strip()) > 0` 是 defense-in-depth 层，合理但冗余。同样逻辑出现在 `_single_minimum_preserve_item_accepted`（line 444）。这是设计选择，保持即可。

---

## Adversarial Review

### A. 从 Run1 到 Run2 的 evidence 恢复前置契约

**验证方法**：追踪从 `AcceptedEvidenceEnvelope` 到 `EvidenceBackedFactView` 的 refs 链路。

**链路**：
1. `AcceptedEvidenceEnvelope.evidence_id`（格式 `evidence:<event_id>`）写入 `CompactionRequest.accepted_evidence_envelopes`
2. `CompactionRequest.accepted_evidence_refs`（property）从中派生
3. `EvidenceBackedFactCandidate.evidence_refs` 必须 ⊆ `accepted_evidence_refs`（`context_governance.py:381`）
4. `CONTEXT_COMPACTED` payload 同时持久化 `accepted_evidence_refs`（via `preserved_fact_refs`）和 `evidence_backed_fact_candidates`
5. Compact artifact 同时存储 `accepted_evidence_envelopes` 和 `evidence_backed_fact_candidates`（`compact_artifact.py:201-207, 211-218, 299-301`）

**结论**：契约链路完整。Run2 可以从 compact artifact 中恢复：(a) 完整的 accepted evidence envelopes，(b) fact candidates 的 claim_text + evidence_refs，(c) evidence_refs 可回溯到具体 envelope。**前置契约足够。**

### B. 非 evidence refs 不会误接受为 fact evidence

**验证方法**：检查 accept barrier 的 refs 子集检查。

**检查点**：
- `_single_fact_candidate_accepted` (line 378-382)：`set(candidate.evidence_refs).issubset(accepted_evidence_ids)` — evidence_refs 必须是 accepted evidence ids，不能是 user/assistant/summary refs
- 测试 `test_quality_rejects_fact_candidate_referencing_non_evidence_ref`：fact candidate 引用 `event-current`（user input ref）被正确拒绝

**结论**：非 evidence refs 无法通过 accept barrier。**误接受风险为 0。**

### C. 无 fallback fact 生成

**验证方法**：检查 accepted evidence 缺失 fact candidate 时的行为。

**检查点**：
- `check_compaction_candidate` (line 86-96)：当 `_retained_accepted_evidence_with_no_fact_candidate` 返回 True 时，添加 `ACCEPTED_EVIDENCE_FACT_CANDIDATE_MISSING` 拒绝原因
- `_retained_accepted_evidence_with_no_fact_candidate` (line 385-411)：检查所有 retained accepted evidence 是否被 valid fact candidates 的 evidence_refs 覆盖。未被覆盖时返回 True（拒绝）。
- 不存在任何合成 neutral fallback fact 的代码路径
- 测试 `test_quality_rejects_missing_fact_candidate_for_accepted_evidence`：验证空 fact candidate 列表导致拒绝

**结论**：不会生成 fallback fact。**行为符合 plan §4.7。**

### D. Bounds / Constants 校验

**验证方法**：交叉检查 plan §4.8 常量与实际代码。

| 常量 | Plan 值 | 代码值 | 位置 |
|------|---------|--------|------|
| `MAX_EVIDENCE_BACKED_FACT_CANDIDATES` | 64 | 64 | compaction.py:30 |
| `MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES` | 32 | 32 | compaction.py:33 |
| `MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS` | 2000 | 2000 | compaction.py:36 |
| `MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS` | 1200 | 1200 | compaction.py:39 |
| `MAX_MINIMUM_PRESERVE_ITEM_LABEL_CHARS` | 120 | 120 | compaction.py:42 |
| `MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS` | 4096 | 4096 | compaction.py:45 |
| `MAX_EVIDENCE_REFS_PER_FACT` | 16 | 16 | compaction.py:48 |
| `MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM` | 16 | 16 | compaction.py:51 |

所有常量位置在 `dayu/host/compaction.py`（非 runtime config，符合 plan 要求）。

相关测试：
- `test_fact_candidate_rejects_empty_claim_text` — 空 claim_text
- `test_fact_candidate_rejects_overlong_claim_text` — 超长 claim_text
- `test_fact_candidate_rejects_missing_evidence_refs` — 空 evidence_refs
- `test_minimum_preserve_item_rejects_overlong_text` — 超长 minimum preserve text
- `test_quality_rejects_fact_candidate_referencing_non_evidence_ref` — invalid refs

**覆盖缺失**：无 `MAX_EVIDENCE_BACKED_FACT_CANDIDATES` / `MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES` / `MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS` / `MAX_EVIDENCE_REFS_PER_FACT` 超限的专项测试。但 dataclass `__post_init__` 会拒绝这些情况，且 `context_events.py` validator 重复校验了最大 count。

**结论**：bounds 值正确，核心边界有测试覆盖。超限场景的测试密度可增强但非阻塞。

### E. 旧字段 Fail-Closed 检查

**验证方法**：搜索所有旧字段拒绝路径。

| 旧字段 | 拒绝位置 | 方式 |
|--------|----------|------|
| `summary.proposed_verified_fact_refs` | `context_events.py:335-336` | ValueError |
| `preserved_fact_refs.tool_fact_refs` | `context_events.py:943-945` | ValueError |
| `preserved_fact_refs.verified_fact_refs` | `context_events.py:943-945` | ValueError |
| `quality_check_result.accepted_tool_fact_refs_retained` | `context_events.py:1069-1074` | ValueError |
| `quality_check_result.retained_evidence_refs` | `context_events.py:1069-1074` | ValueError |

所有旧字段在 JSON deserialization 路径上有显式拒绝。接受的 payload 只使用新字段名。

**结论**：旧字段 fail-closed 实现完整。**不存在静默跳过旧字段的路径。**

---

## Scope 边界检查

**Slice 3 禁止项**（来自 plan §7 Slice 3 Stop Condition）：
- "If implementation requires a second normal-path LLM extraction call or eager extraction after each tool result, stop"

**检查**：
- 未修改 `dayu/host/llm_compaction.py` ✓
- 未修改 `dayu/host/tool_runtime.py` ✓
- 未修改 `dayu/host/memory.py` / `dayu/host/durable/memory.py` ✓
- 未修改 `dayu/host/run_input.py` / `dayu/host/dispatch.py` / `dayu/host/engine_ingest.py` ✓
- 未修改 Service / Engine / Fins 文件 ✓
- 未引入第二次 LLM 调用或 eager extraction ✓

**结论**：Slice 3 严格限制在自己的文件范围内，无 scope violation。

---

## 测试评估

### 测试统计
- 总测试数：50（3 个测试文件）
- 通过：50 / 50
- 失败：0
- Slice 3 新增测试：6 个专项测试

### 新增测试清单

| 测试 | 文件 | 覆盖点 |
|------|------|--------|
| `test_quality_rejects_fact_candidate_referencing_non_evidence_ref` | test_compaction_contract.py | fact candidate 引用非 evidence ref 被拒绝 |
| `test_quality_rejects_missing_fact_candidate_for_accepted_evidence` | test_compaction_contract.py | 缺少 fact candidate 产生拒绝 |
| `test_fact_candidate_rejects_empty_claim_text` | test_compaction_contract.py | 空 claim_text 构造时拒绝 |
| `test_fact_candidate_rejects_overlong_claim_text` | test_compaction_contract.py | 超长 claim_text 构造时拒绝 |
| `test_fact_candidate_rejects_missing_evidence_refs` | test_compaction_contract.py | 空 evidence_refs 构造时拒绝 |
| `test_minimum_preserve_item_rejects_overlong_text` | test_compaction_contract.py | 超长 minimum preserve text 构造时拒绝 |
| `test_quality_rejects_minimum_preserve_source_outside_compact_input` | test_compaction_contract.py | minimum preserve source refs 不在 compact input 内 |

### 测试空洞

1. **`evidence_refs` 超限（MAX_EVIDENCE_REFS_PER_FACT > 16）无专项测试**：dataclass `__post_init__` 会拒绝，`context_events.py` validator 也会拒绝。信任现有机制即可。
2. **`attributes` JSON 超限（> MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS）无专项测试**：同上。
3. **Fact candidate 总数超限（> MAX_EVIDENCE_BACKED_FACT_CANDIDATES）无专项测试**：同上。
4. **Minimum preserve candidate 总数超限无专项测试**：同上。
5. **无旧 compact artifact v1 读路径拒绝测试**：该测试属于 Slice 5（Memory Projection），不在本 Slice 范围。
6. **`MinimumPreserveItemCandidate` 空 label / 空 item_id 无专项测试**：与现有测试风格一致（dataclass 构造时拒绝，不需要每个字段单独测试）。

**总体测试质量**：覆盖了 plan §7 Slice 3 要求的全部 6 类测试。测试断言精确（使用具体 CompactQualityIssue enum 而非泛型 assert），fake_compaction 正确构造了新字段。

---

## 验证结果

```
=== pytest ===
tests/host/test_compaction_contract.py .............. (22 tests)
tests/host/test_context_compact_events.py .......... (24 tests)
tests/host/test_compaction_operation.py .... (4 tests)
50 passed in 0.64s

=== pyright ===
dayu/host/compaction.py — 0 errors, 0 warnings
dayu/host/context_events.py — 0 errors, 0 warnings
dayu/host/context_governance.py — 0 errors, 0 warnings
dayu/host/compact_artifact.py — 0 errors, 0 warnings
```

---

## 变更摘要

| 文件 | 变更类型 | 关键变更 |
|------|----------|----------|
| `dayu/host/compaction.py` | Contract 扩展 | +EvidenceBackedFactCandidate, +MinimumPreserveItemCandidate, +2 Enum, +8 Constants, 字段重命名, `accepted_evidence_refs` property |
| `dayu/host/context_events.py` | Payload 扩展 | +2 必填字段, +4 校验函数, +5 旧字段 reject guards, quality_result 参数重命名 |
| `dayu/host/context_governance.py` | Accept barrier | +3 新 check, +6 辅助函数, renamed tool_fact -> accepted_evidence 语义 |
| `dayu/host/compact_artifact.py` | Artifact schema | v1→v2, +2 新字段组, +accepted_evidence_envelopes 持久化 |
| `dayu/host/README.md` | 文档同步 | accepted evidence / fact candidate / minimum preserve 概念更新 |
| `tests/host/fake_compaction.py` | Test helper | fake compactor 输出新字段, accepted_evidence envelope 数据流 |
| `tests/host/test_compaction_contract.py` | 测试 | +6 新测试, request helper 使用 envelope |
| `tests/host/test_compaction_operation.py` | 测试 | request helper 使用 envelope |
| `tests/host/test_context_compact_events.py` | 测试 | candidate/quality_result 使用新字段 |

---

## Residual Risks

| Risk | Severity | Owner | Mitigation |
|------|----------|-------|------------|
| 旧 v1 compact artifact 没读路径版本守卫 | Low | Slice 5 | Slice 5 必须添加 schema_version 检查，fail-closed 拒绝 v1 |
| `confirmed_fact_refs` 可引用 evidence 信封 id | Low | Slice 4/followup | 收窄 `allowed_fact_refs` 为仅 evidence_backed_fact_refs |
| Fact candidate 超限无专项测试 | Info | 信任 dataclass + validator 双层防护 | 现有边界拒绝机制已足够 |
| LLM fact extraction 质量 | Out of scope | 后续 compactor-quality work | Plan §11 已记录 |

---

## 审查签署

- **审查者**：DeepReview Agent (Claude)
- **结论**：**PASS** — Slice 3 实现正确、完整，契约一致，无阻塞性问题。建议推进到 Slice 4。
- **可合并**：是（3 个 LOW 发现均为非阻塞项，可在后续 slice 修复）
