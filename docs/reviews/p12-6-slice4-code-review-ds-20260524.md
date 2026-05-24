# P12.6 Slice 4 Code Review — AgentDS

**Verdict: PASS**

**Date**: 2026-05-24
**Reviewer**: AgentDS
**Review base**: HEAD = e89e702 gateflow: accept P12.6 slice 3
**Scope**: workspace diff (excludes `docs/host/implementation-control.md`)
**Artifacts reviewed**:
- `dayu/host/llm_compaction.py`
- `dayu/host/context_governance.py`
- `dayu/config/prompts/scenes/conversation_compaction.md`
- `dayu/config/prompts/scenes/conversation_compaction_user.md`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_compaction_contract.py`

**Design truth sources**:
- `docs/host/design.md` §1 / §24 / §25
- `docs/host/p12-6-conversation-memory-redesign-implementation-plan.md` Slice 4
- `docs/reviews/p12-6-slice4-implementation-codex-20260524.md`

---

## 1. Validation Summary

| Check | Result |
|---|---|
| Prompt renderer 只消费 material pack typed view，只渲染四个 sections | PASS |
| Prompt / prompt assets 不含 Host ledger 字段 | PASS |
| JSON parser 只接受 prompt-local labels，映射到 canonical refs 后构造 Candidate | PASS |
| Unknown labels / cross-section labels / fact 无 evidence label / minimum preserve 非 material label / finish_reason=length / 非 final / 空 summary 均 fail closed | PASS |
| Quality checker 拒绝 evidence label 升级成 fact ref | PASS |
| 架构：不改 ConfigLoader/ScenePrepare schema、不改 public API、不引入 Any/object/getattr/hasattr/lazy seam | PASS |
| Tests 覆盖 plan 指定 6 项，真实防回归 | PASS |
| README 无需更新合理 | PASS |

---

## 2. Findings

### F1 (LOW) — `_preservation_evidence` hardcodes `memory_snapshot_cursor=None`

**File**: `dayu/host/llm_compaction.py:1084`
**Evidence**:
```python
PreservationEvidence(
    evidence_id=f"llm-evidence:{request.run_id}:{index + 1}",
    ...
    memory_snapshot_cursor=None,
    ...
)
```
**Impact**: Slice 4 的 parser 不会从 LLM proposal 读取 `memory_snapshot_cursor`，而是直接硬编码 `None`。当前质量检查器 `_single_evidence_anchor_valid`（`context_governance.py:274-278`）仅在 `memory_snapshot_cursor is not None` 时才校验，因此 `None` 不会触发拒绝。但这意味着 preservation evidence 的 snapshot cursor 锚点在 Slice 4 未被填充，Slice 5 接线时必须补齐。

**建议**: 在 Slice 5 governance 接线时从 `request.memory_snapshot_cursor` 或 material pack builder 产物中读取实际 cursor 值。当前 Slice 4 不接受对此的修改（plan §6.6 将 cursor validation 归入 Slice 2 / Slice 5）。

**严重度降低原因**: plan 明确将此工作归入 Slice 5 reactive governance 接线。Slice 4 的职责是 parser / accept barrier hardening，不接受 cursor wiring。

---

### F2 (INFO) — 新增 defense-in-depth 检查与 parser 路径存在冗余覆盖

**File**: `dayu/host/context_governance.py:199-202`
**Evidence**:
```python
evidence_labels = set(request.material_pack.evidence_labels)
if len(evidence_labels.intersection(summary.confirmed_fact_refs)) > 0:
    return True
if len(evidence_labels.intersection(summary.proposed_evidence_backed_fact_refs)) > 0:
    return True
```
**Analysis**: Parser 端 `_episode_summary_candidate` 已将 `confirmed_fact_refs` 通过 `_bounded_known_refs(..., allowed_refs=request.evidence_backed_fact_refs)` 校验，LLM 把 prompt-local "E1" 放入 `confirmed_fact_refs` 时 parser 因其不在 `evidence_backed_fact_refs` 中就会拒绝。Quality checker 新增的这两个 intersection check 在正常 parser 路径下不会被触发，仅在 test 直接构造 invalid candidate 或未来 bypass parser 的路径中生效。

**评价**: 这是合理的 defense-in-depth，不算冗余。parser 是第一道防线，quality checker 是第二道防线，两者职责不同（parser 拒绝格式错误，quality checker 拒绝语义越权）。测试 `test_quality_rejects_summary_confirmed_fact_ref_to_evidence_label` 正确覆盖了第二道防线。

**严重度**: INFO，不阻塞。

---

### F3 (INFO) — 旧测试 `test_llm_context_compactor_prompt_marks_raw_evidence_with_evidence_id` 语义漂移

**File**: `tests/host/test_llm_compaction.py:290-291`（diff 上下文）
**Evidence**: 测试原名暗示检查 "evidence_id"，但实际断言改为使用 `"evidence_input"` 的 section key 定位和 `"label": "E1"` 的 prompt-local 标签。测试逻辑正确，但测试函数名 `test_llm_context_compactor_prompt_marks_raw_evidence_with_evidence_id` 与当前实际行为（检验 prompt-local label）存在轻微语义漂移。

**建议**: 可考虑将测试函数名更新为更准确地反映 prompt-local label 语义，例如 `test_prompt_marks_evidence_with_prompt_local_label`。非阻塞，仅 documentation hygiene。

**严重度**: INFO，不阻塞。

---

### F4 (OBSERVATION) — prompt renderer 不再输出 `trigger_source`

**File**: `dayu/host/llm_compaction.py:348-364`
**Evidence**: 旧实现 `_compaction_request_prompt_block` 渲染 `trigger_source: {request.trigger_source.value}` + `material_pack:` 包装行。新实现只输出 `json.dumps(request.llm_material_json(), ...)`，无 `trigger_source` 字段。

**评价**: 符合 plan §6.1 与 §6.2 的要求——LLM-facing input 只有 material pack sections，trigger / operation metadata 保留在 Host 内部 segment selection 中。此为设计意图，非遗漏。

---

## 3. Per-Focus-Area Detailed Analysis

### 3.1 Prompt renderer 是否只消费 material pack typed view

`_compaction_request_prompt_block`（line 348-364）只调用 `request.llm_material_json()` 并 JSON pretty-print。`llm_material_json()` 由 `CompactMaterialPack` 提供，该类型只包含 `stable_input`、`history_input`、`evidence_input`、`current_input_anchor` 四个 typed section 和 internal `provenance_map`（不出现在 JSON 输出中）。

已删除旧函数 `_indented_content_lines` 和 `_refs_text`，renderer 不再读取 EventLog、accepted evidence envelope 或 Host ledger helper。

**通过。**

### 3.2 Prompt / prompt assets 是否不含 Host ledger 字段

**Prompt assets**：
- `conversation_compaction.md`: 文案改为引用 `evidence_input` 中的 prompt-local evidence labels。禁用词搜索（`accepted_evidence_envelopes:`、`compact_raw_context:`、`input_event_refs:`、`payload_digest` 等）= 0 命中。
- `conversation_compaction_user.md`: schema 改为 `evidence_labels`、`material_labels`、`tool_finding_labels`、`source_labels` 等 prompt-local 术语。新增 `preservation_evidence` schema，其中 `compact_range` 边界用 `start_material_label` / `end_material_label`。禁用词搜索 = 0 命中。

**Prompt renderer output**: 测试 `test_prompt_renders_material_pack_without_ledger_dump` 断言 prompt 不包含 `material_pack:` 包装、`trigger_source:`、`accepted_evidence_envelopes:`、`compact_raw_context:`、`input_event_refs:`、`payload_ref`、`payload:accepted-1`、`event-tool-result-1`、`event-tool-call-1`、`memory_snapshot_cursor`、`policy_snapshot`、`outcome_digest`、`canonical_source_refs`。测试 `test_prompt_does_not_render_accepted_evidence_envelope_metadata` 进一步断言 `producer_event_ref`、`tool_call_id`、`normalized_arguments_digest`、`semantic_input_digest`、`payload_ref`、`payload_digest`、`outcome_digest` 不出现在 prompt 中。

**通过。**

### 3.3 JSON parser 是否只接受 prompt-local labels

`_canonical_refs_for_labels`（line 769-795）统一入口：对每个 label，先走 `_provenance_entry_for_label` 查找 provenance_map → 校验 section membership → 调用 `validate_material_label` 校验 label 格式 → 读取 `canonical_source_refs`。`_canonical_evidence_refs_for_labels`（line 798-828）专门处理 evidence labels，只允许 `EVIDENCE_INPUT` section，并要求 `accepted_evidence_id` 非空。

新函数 `_provenance_entry_for_label`（line 831-854）统一了 label → provenance entry 的查找与校验逻辑，消除了旧代码中 `_canonical_refs_for_labels` 和 `_canonical_evidence_refs_for_labels` 分别手写 `provenance_map.get(label)` + section check 的重复。

`_preservation_evidence`（line 1047-1093）从 LLM proposal 的 `preservation_evidence` 数组读取 prompt-local labels，映射为 canonical refs 后构造 `PreservationEvidence`。

**通过。**

### 3.4 Fail-closed 路径覆盖

| 场景 | 实现位置 | 机制 |
|---|---|---|
| Unknown label | `_provenance_entry_for_label:849` | `ValueError("unknown label")` → `LLMCompactionProposalError` |
| Cross-section label | `_provenance_entry_for_label:852` | `ValueError("section mismatch")` → `LLMCompactionProposalError` |
| Fact 无 evidence label | `_canonical_evidence_refs_for_labels:816` | `require_non_empty=True` → `ValueError("must reference at least one evidence label")` |
| Minimum preserve source 非 material label | `_canonical_refs_for_labels` + `_MATERIAL_LABEL_SECTIONS` | 只允许四个 section 的 labels → unknown label / section mismatch |
| finish_reason=length | `compact:217-219` | `LLMCompactionProposalError("truncated finish_reason=length")` |
| 非 final answer | `compact:215-216` | `LLMCompactionProposalError(_non_final_outcome_message(...))` |
| 空 summary | `_parse_proposal:451` | `LLMCompactionProposalError("proposal is empty")` |

测试覆盖：
- `test_parser_rejects_unknown_or_cross_section_labels` — 覆盖 unknown label (`"missing-label"`) 和 cross-section label (`"H1"` 用于 evidence ref)
- `test_fact_candidate_without_evidence_label_rejected` — 覆盖 `fact_evidence_refs=()`
- `test_minimum_preserve_source_refs_must_be_material_labels` — 覆盖 `source_labels=("payload:accepted-1",)` 触发 unknown label

**通过。**

### 3.5 Quality checker 是否拒绝 evidence label 升级为 fact ref

`_summary_pretends_evidence_backed_fact`（line 185-208）新增两道防线：
1. `evidence_labels.intersection(summary.confirmed_fact_refs)` — 检测 prompt-local evidence label 被当作 confirmed fact ref
2. `evidence_labels.intersection(summary.proposed_evidence_backed_fact_refs)` — 检测 evidence label 被当作 proposed fact ref

测试 `test_quality_rejects_summary_confirmed_fact_ref_to_evidence_label` 设置 `confirmed_fact_refs=("E1",)` 并断言 `SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT` 出现在 rejection_reasons 中。

**通过。**

### 3.6 Architecture constraints

| 约束 | 状态 |
|---|---|
| 不改 ConfigLoader/ScenePrepare schema | 通过 — prompt asset 只改文案，不改 schema 结构 |
| 不改 public API | 通过 — 所有修改在 `llm_compaction.py` / `context_governance.py` 内部 |
| 不引入 `Any` / `object` / `getattr` / `hasattr` / lazy seam | 通过 — diff 中无此类用法 |
| 依赖方向 `UI → Service → Host → Engine` | 通过 — 无反向 import |
| Host 不 import business tools / Fins / Service / UI | 通过 — import 来源只有 `dayu.engine`、`dayu.host`、`dayu.contracts`、标准库 |
| 严格类型化 | 通过 — pyright 0 errors, 0 warnings |
| 中文 docstring | 通过 — 所有新增函数均有完整中文 docstring |

**通过。**

### 3.7 Test coverage

Plan §8 Slice 4 指定 6 项测试：

| Plan 测试 | 实现测试 | 状态 |
|---|---|---|
| `test_prompt_renders_material_pack_without_ledger_dump` | 同名，从旧 `test_llm_context_compactor_prompt_contains_raw_evidence_content` 重写 | PASS |
| `test_prompt_does_not_render_accepted_evidence_envelope_metadata` | 同名 | PASS |
| `test_parser_maps_prompt_local_evidence_label_to_canonical_ref` | 同名，从旧 `test_llm_context_compactor_maps_final_answer_to_candidate` 重写 | PASS |
| `test_parser_rejects_unknown_or_cross_section_labels` | 同名 | PASS |
| `test_fact_candidate_without_evidence_label_rejected` | 同名 | PASS |
| `test_minimum_preserve_source_refs_must_be_material_labels` | 同名 | PASS |

额外覆盖：
- `test_quality_rejects_summary_confirmed_fact_ref_to_evidence_label`（contract test）— 覆盖 quality checker 新增防线

验证结果：`49 passed in 0.72s`，pyright `0 errors, 0 warnings, 0 informations`。

**通过。**

### 3.8 README

触发检查：`dayu/host/`、`dayu/config/`、`tests/` 有修改。

- `dayu/host/README.md`: 本 Slice 只收紧内部 parser / prompt renderer / quality checker 实现，不改变 Host 公共接口、架构边界、执行路径、状态机、事件流或扩展点。
- `dayu/config/README.md`: Prompt asset 文案更新（label 命名改为 prompt-local），但配置加载机制、目录结构、覆盖关系、常改项清单不变。
- `tests/README.md`: 新增测试在现有约定框架内，测试分层、运行方式、维护规则不变。

**不更新合理。**

---

## 4. Residual Risks

1. **`memory_snapshot_cursor=None` 硬编码**（见 F1）：Slice 5 接线时必须从实际 request cursor 或 builder 产物填充，否则 preservation evidence 失去 snapshot cursor 锚点，影响 audit / rebuild 可追溯性。

2. **真实 provider 对 `preservation_evidence` schema 的遵循度**：当前测试使用 fake compactor 和硬编码 JSON proposal；真实 LLM 是否能正确输出新增的 `preservation_evidence` 结构待 Slice 5/7 验证。

3. **`_optional_input_range` 接受 LLM 提供的任意 `range_ref` 字符串**：当前 `range_ref` 是 prompt-local 标识符，由 LLM 自由命名；Host 不做格式校验。若未来 range_ref 需要跨 operation 可追溯，需补充 Host-generated id。

4. **`_summary_pretends_evidence_backed_fact` 中的 `proposed_evidence_backed_fact_refs` 字段**：当前 parser 从不生成此字段（默认为空 tuple），只通过 test/fake 路径可达。若未来 parser 开始产生该字段，需确认 quality checker 的 evidence_labels intersection 检查仍然有效。

---

## 5. Conclusion

Slice 4 实现严格遵循 `docs/host/design.md` §24 / §25 和 implementation plan Slice 4 的全部要求。Prompt renderer 只渲染四个 material pack section；prompt assets 不含 Host ledger 字段；parser 先行 label → canonical ref 映射后构造 `CompactionCandidate`；所有 fail-closed 路径有真实测试覆盖；架构约束无违规。无阻塞级 finding。

**Verdict: PASS**
