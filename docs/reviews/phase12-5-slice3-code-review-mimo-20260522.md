# Phase 12.5 Slice 3 Code Review: Compaction Structured Candidate Contract And Accept Barrier

## Review Metadata

- **Review Agent**: MiMo
- **Review Date**: 2026-05-22
- **Base**: HEAD=e154c46 (gateflow: accept phase 12.5 slice 2)
- **Scope**: 未提交改动，Slice 3: Compaction Structured Candidate Contract And Accept Barrier
- **Plan**: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`
- **Design Source**: `docs/host/design.md` §24, §25
- **Changed Files**: 9 files, +1272 / -138

## Verdict: ACCEPTED with 2 minor findings

50 tests pass, pyright 0 errors。Slice 3 满足计划 §7 的所有 Exact Changes 和 Tests 要求。accept barrier 逻辑正确实现了 fail-closed：无 fallback fact、无 neutral diagnostic fact、旧字段拒绝、bounds 常量在构造期强制。

---

## Findings

### F1 [LOW] 三模块重复 `_fact_candidate_list_json` / `_minimum_preserve_candidate_list_json`

- **文件**: `dayu/host/compaction.py:1449-1480`, `dayu/host/context_events.py:510-540`, `dayu/host/compact_artifact.py:327-358`
- **证据**: 同一个 `(tuple[EvidenceBackedFactCandidate, ...]) -> list[JsonValue]` 转换逻辑在三个模块各写了一遍，函数体完全相同（`for value in values: result.append(value.to_json())`）。
- **违反**: 编码硬约束"数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"。
- **修复建议**: 在 `dayu/host/compaction.py` 中将这两个辅助函数标记为模块级私有并导出（或放入公共协议），`context_events.py` 和 `compact_artifact.py` 从 `compaction.py` 导入。这三个模块已有 `from dayu.host.compaction import ...` 的依赖关系，不引入新依赖。
- **严重度**: LOW — 功能正确，仅违反 DRY 约束。不影响 Slice 3 退出条件，可在 Slice 7 聚合验证时一并清理。

### F2 [LOW] 缺少旧 `proposed_verified_fact_refs` 拒绝的显式测试

- **文件**: `tests/host/test_context_compact_events.py`
- **证据**: `test_compacted_payload_rejects_summary_proposed_evidence_backed_fact_refs` 测试了新字段 `proposed_evidence_backed_fact_refs` 为空的约束，但没有测试旧 key `proposed_verified_fact_refs` 出现在 summary 中被拒绝。生产代码 `context_events.py:335` 已实现拒绝逻辑：
  ```python
  if _FIELD_OLD_PROPOSED_VERIFIED_FACT_REFS in summary:
      raise ValueError("old proposed verified fact refs field is not supported")
  ```
- **修复建议**: 新增测试 `test_compacted_payload_rejects_old_proposed_verified_fact_refs`，注入旧 key 到 summary，断言 ValueError。
- **严重度**: LOW — 生产代码已正确拒绝，仅测试覆盖缺口。

---

## Detailed Review

### 1. 契约命名迁移 (§4.1)

| 旧名 | 新名 | 状态 |
|---|---|---|
| `tool_fact_refs` | `accepted_evidence_refs` (derived property) | 已迁移 |
| `verified_fact_refs` | `evidence_backed_fact_refs` | 已迁移 |
| `preserved_tool_fact_refs` | `preserved_accepted_evidence_refs` | 已迁移 |
| `preserved_verified_fact_refs` | `preserved_evidence_backed_fact_refs` | 已迁移 |
| `proposed_verified_fact_refs` | `proposed_evidence_backed_fact_refs` | 已迁移 |
| `accepted_tool_fact_refs_retained` | `accepted_evidence_refs_retained` | 已迁移 |
| `retained_evidence_refs` | `retained_accepted_evidence_refs` | 已迁移 |
| `TOOL_FACT_REFS_MISSING` | `ACCEPTED_EVIDENCE_REFS_MISSING` | 已迁移 |
| `SUMMARY_PRETENDS_VERIFIED_FACT` | `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT` | 已迁移 |

旧 key 拒绝：
- `context_events.py:100-103`: `_FIELD_OLD_*` 常量用于拒绝旧 payload。
- `context_events.py:_reject_old_preserved_fact_ref_fields`: 拒绝 `tool_fact_refs` / `verified_fact_refs`。
- `context_events.py:_reject_old_quality_result_fields`: 拒绝 `accepted_tool_fact_refs_retained` / `retained_evidence_refs`。
- `context_events.py:335`: 拒绝旧 `proposed_verified_fact_refs`。

验证通过：Slice 3 覆盖的文件中旧命名只出现在 `_FIELD_OLD_*` 拒绝常量中。

### 2. 新增类型契约 (§4.3, §4.4)

- `EvidenceBackedFactKind` (StrEnum): 4 个值，与设计一致。
- `EvidenceBackedFactCandidate`: frozen dataclass, `__post_init__` 校验 candidate_id 非空、claim_text 有界非空、evidence_kind 类型、evidence_refs 有界非空唯一、attributes JSON mapping 且有界。
- `MinimumPreserveReason` (StrEnum): 3 个值，与设计一致。
- `MinimumPreserveItemCandidate`: frozen dataclass, `__post_init__` 校验 item_id 非空、label 有界非空、text 有界非空、source_refs 有界非空唯一、preserve_reason 类型。

所有 bounds 常量 (§4.8) 已在 `compaction.py:28-46` 定义，与计划完全一致：
`MAX_EVIDENCE_BACKED_FACT_CANDIDATES=64`, `MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES=32`,
`MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS=2000`, `MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS=1200`,
`MAX_MINIMUM_PRESERVE_ITEM_LABEL_CHARS=120`, `MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS=4096`,
`MAX_EVIDENCE_REFS_PER_FACT=16`, `MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM=16`。

### 3. CompactionRequest 扩展 (§4.2)

- `tool_fact_refs` -> `accepted_evidence_envelopes: tuple[AcceptedEvidenceEnvelope, ...]` + `evidence_backed_fact_refs: tuple[str, ...]`。
- `accepted_evidence_refs` 是 derived property，从 `accepted_evidence_envelopes[*].evidence_id` 派生。
- `__post_init__` 校验 `accepted_evidence_envelopes` 类型和 `accepted_evidence_refs` 唯一性。
- `to_json()` 输出包含 envelopes 和 refs。

### 4. CompactionCandidate 扩展

- 新增 `evidence_backed_fact_candidates: tuple[EvidenceBackedFactCandidate, ...]`。
- 新增 `minimum_preserve_item_candidates: tuple[MinimumPreserveItemCandidate, ...]`。
- `__post_init__` 通过 `_require_fact_candidate_tuple` / `_require_minimum_preserve_candidate_tuple` 校验类型和数量上限。
- `preserved_tool_fact_refs` -> `preserved_accepted_evidence_refs`。
- `preserved_verified_fact_refs` -> `preserved_evidence_backed_fact_refs`。

### 5. CONTEXT_COMPACTED Payload (§4.5)

- `build_context_compacted_payload` 输出新字段：`evidence_backed_fact_candidates`, `minimum_preserve_item_candidates`。
- `preserved_fact_refs` 子结构使用 `accepted_evidence_refs` / `evidence_backed_fact_refs`。
- `_COMPACTED_REQUIRED_FIELDS` 新增两个候选字段。
- `quality_check_result` 新增 `evidence_backed_fact_candidates_accepted` / `minimum_preserve_items_accepted` / `retained_accepted_evidence_refs`。
- 旧字段拒绝已实现（见 §1）。

### 6. Accept Barrier (§4.7, §5.4)

`context_governance.py:check_compaction_candidate` 新增三项检查：

1. **`_fact_candidates_accepted`**: 遍历 `candidate.evidence_backed_fact_candidates`，每个调用 `_single_fact_candidate_accepted` 校验 `claim_text.strip()` 非空、`evidence_refs` 非空、`evidence_refs ⊆ accepted_evidence_ids`。bounds 在 `__post_init__` 强制。
2. **`_retained_accepted_evidence_with_no_fact_candidate`**: 收集 valid candidates 覆盖的 evidence refs，与 `preserved_accepted_evidence_refs ∩ accepted_evidence_ids` 比较，有未覆盖的则返回 True → 产生 `ACCEPTED_EVIDENCE_FACT_CANDIDATE_MISSING` 拒绝。
3. **`_minimum_preserve_items_accepted`**: 校验 `source_refs` 非空且 `⊆ request.input_event_refs`。bounds 在 `__post_init__` 强制。

设计一致性：
- 无 fallback fact：缺少有效 fact candidate 时只产生拒绝诊断，不构造 neutral fact。✓
- summary 不得伪装 fact：`_summary_pretends_evidence_backed_fact` 检查 `proposed_evidence_backed_fact_refs` 和 `preserved_evidence_backed_fact_refs ⊆ request.evidence_backed_fact_refs`。✓
- minimum preserve source refs 来自 compact input：`⊆ request.input_event_refs`。✓

### 7. Compact Artifact (§4.5)

- `compact_artifact_schema_version` 从 1 升到 2。✓
- artifact JSON 新增 `evidence_backed_fact_candidates`、`minimum_preserve_item_candidates`。
- `input_snapshot_refs` 新增 `accepted_evidence_envelopes`。
- `preserved_fact_refs` 使用新 key。
- 旧 key 不出现在新 artifact 中。✓

### 8. Fake Compactor 更新

- `_fact_candidates()`: 根据 `request.accepted_evidence_refs` 为每个 ref 构造一个 `EvidenceBackedFactCandidate`。
- `_minimum_preserve_items()`: 根据当前输入构造一个 `MinimumPreserveItemCandidate`。
- 预算估算简化为 token 常数公式（测试代码，可接受）。

### 9. 测试覆盖

| 计划要求 (§7 Slice 3 Tests) | 测试 | 状态 |
|---|---|---|
| valid candidate referencing accepted evidence passes | `test_compacted_payload_builder_emits_required_accepted_output` (含 fact candidates) | ✓ |
| candidate referencing assistant/user/summary refs is rejected | `test_quality_rejects_fact_candidate_referencing_non_evidence_ref` | ✓ |
| empty claim_text rejected | `test_fact_candidate_rejects_empty_claim_text` | ✓ |
| missing evidence refs rejected | `test_fact_candidate_rejects_missing_evidence_refs` | ✓ |
| overlong claim_text rejected | `test_fact_candidate_rejects_overlong_claim_text` | ✓ |
| overlong minimum preserve text rejected | `test_minimum_preserve_item_rejects_overlong_text` | ✓ |
| accepted evidence with missing fact candidates → diagnostic, not fallback | `test_quality_rejects_missing_fact_candidate_for_accepted_evidence` | ✓ |
| minimum preserve source refs outside compact input rejected | `test_quality_rejects_minimum_preserve_source_outside_compact_input` | ✓ |
| old preserved_fact_refs fields rejected | 生产代码 `_reject_old_preserved_fact_ref_fields` 实现 | ✓ (无显式测试) |
| old quality result fields rejected | 生产代码 `_reject_old_quality_result_fields` 实现 | ✓ (无显式测试) |
| event payload roundtrip | `test_compacted_payload_builder_emits_required_accepted_output` | ✓ |

### 10. 非目标一致性

- 不修改 LLMContextCompactor：✓（`llm_compaction.py` 未改动，但仍有旧 `tool_fact_refs` 引用，属于 Slice 4）
- 不做第二次正常路径 LLM 调用：✓
- 不做 eager extraction：✓
- 不解析业务 source/locator：✓（Host barrier 只校验 ref ⊆ accepted_evidence_ids / input_event_refs）

### 11. 分层边界

- `compaction.py` 导入 `evidence.py`（同层，正确）。
- `context_events.py` 导入 `compaction.py` + `durable.codec`（同层/下层，正确）。
- `context_governance.py` 导入 `compaction.py`（同层，正确）。
- `compact_artifact.py` 导入 `compaction.py` + `evidence.py` + `durable.*`（同层/下层，正确）。
- 无反向依赖。✓

---

## Residual Risks

1. **F1 重复辅助函数**：三模块重复 JSON 序列化辅助。LOW 风险，可在 Slice 7 聚合验证时统一清理。
2. **F2 旧 key 测试覆盖**：`proposed_verified_fact_refs` 拒绝逻辑已实现但无显式测试。LOW 风险，生产代码已正确 fail-closed。
3. **下游文件旧术语残留**：`llm_compaction.py`, `dispatch.py`, `engine_ingest.py`, `run_input.py`, `memory.py` 及对应测试仍使用旧 `tool_fact_refs` / `verified_fact_refs` 命名。这是预期的——这些文件属于 Slice 4/5/6 范围，不在本 slice 修改范围内。
4. **compact artifact schema version 升级**：从 1 到 2，无旧 artifact 兼容读取。符合"全新 schema 起库"策略，但需确保 Slice 5 memory projection 消费 artifact 时也按 v2 schema 处理。

---

## Tests Executed

```
pytest tests/host/test_compaction_contract.py tests/host/test_context_compact_events.py tests/host/test_compaction_operation.py -v
→ 50 passed in 0.63s

pyright dayu/host/compaction.py dayu/host/context_events.py dayu/host/context_governance.py dayu/host/compact_artifact.py
→ 0 errors, 0 warnings, 0 informations
```
