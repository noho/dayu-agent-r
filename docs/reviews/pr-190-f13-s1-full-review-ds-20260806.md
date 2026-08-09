# PR190 F13 S1 AgentDS full-slice adversarial code review

## Gate metadata

- work unit / slice: F13 / S1（full slice，C1–C3 全覆盖）
- reviewer: AgentDS
- review date: 2026-08-06
- base commit: `62445b59`
- reviewed diff: full uncommitted working tree（37 files, +4182/-2058）
- prerequisites: C1/C2/C3 accepted（AgentMiMo + AgentDS 两路均 accepted，Controller 已裁决）

## Review scope

对完整 S1 source/config/test diff 做跨模块 adversarial review，重点挑战：跨模块 owner drift、`_CompactAcceptancePermit` bypass、strict parser binding、multi-pass atom 语义、flat aggregate 反写、failed/rejected artifact 污染、late 第二 terminal、fake repair 过度设计、prompt/schema 漂移、S2 边界，以及未覆盖 mandatory owner tests。

## Validation baseline

```text
C1: 64 passed   C2: 215 passed   C3: 595 passed, 1 skipped
pyright: 0 errors, 0 warnings   ruff: All checks passed
```

## Adversarial pass — 全部 11 项

| 反例 | 路径 | 预期行为 | 真实行为 | 结论 |
|---|---|---|---|---|
| `_COMPACT_ACCEPTANCE_PERMIT` bypass | 外部 `from dayu.host.compaction import _COMPACT_ACCEPTANCE_PERMIT` 后用其构造 `CompactAcceptedTruthV4` | Python naming convention 是唯一守卫；`__post_init__` 校验 `self._permit is _COMPACT_ACCEPTANCE_PERMIT` | `_permit` 不进 `__all__`；全 test/codebase 中仅 `context_governance.py:41` 导入该符号；无外部 bypass 入口 | **PASS** |
| `derive_compact_accepted_replacement_v4` 独立调用 vs `validate_compact_proposal_replacement_binding_v4` re-derive 漂移 | governance `derive`（line 126）→ durable parser `validate`（line 122）→ 内部再 `derive`（line 1894） | re-derive 产生相同 expected，`==` 比较 | 两次 derive 入参相同（canonicalized proposal + same boundary），纯函数 deterministic 输出一致 | **PASS** |
| `_aggregate_pass_candidates` 中 `fact.selection_labels[0]` 误识别 | retained atom: `selection_labels=(P1,)` → `len==1` + `PREVIOUS_EVIDENCE_FACT`; new fact: `support_labels` 只能是 `EVIDENCE_MATERIAL` | retained 正确匹配; new fact 即使 `len==1` 也因 kind 不匹配被过滤 | `COMPACT_FACT_SOURCE_KINDS_V4=(EVIDENCE_MATERIAL,)` 阻止 new fact label 被误识别为 retained；`CompactAcceptedEvidenceFactV4.__post_init__` 强制 selection 非空 | **PASS** |
| flat aggregate 反写逐 fact refs | `_facts_from_accepted_event:1764` → `evidence_refs=fact.canonical_evidence_refs` | 每条 `EvidenceBackedFactView` 使用自身 atom refs，不用 aggregate | `canonical_evidence_refs` property（line 1592-1606）是 per-fact tuple 的 ordered unique union，逐 fact atom 在 `derive` 时独立构造且 frozen | **PASS** |
| failed/rejected artifact 污染 | `_failed_operation_result:1463` → `accepted_truth=None`；`_attempt_rejected` 不写 `CONTEXT_COMPACTED` | 下游 dispatch/engine_ingest 在 `accepted_truth is None` 时不写 accepted EventLog | `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_FAILED` / `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 三事件 required-field tuple 互不重叠（context_events.py:1022-1084） | **PASS** |
| late 第二 terminal | `_CompactorProposalCancelledError`（line 954-981）→ `CompactionOperationResult(accepted_truth=None, ...)` 直接 return | 不经过 acceptance 链 | 每次 attempt 独立 `_CompactionAttemptCancellationToken`，parent lifetime 优先 | **PASS** |
| fake repair heuristic | `_typed_repair_omits_evidence_facts:641-644` → `issue.code is DUPLICATE_SEMANTIC_ITEM and issue.json_path.startswith('$["evidence_facts"]')` | 用 typed issue code + JSON path，不用 claim 文本或关键词 | real governance 先 reject → fake 读取 typed report → 匹配 evidence_facts path → omit routed facts | **PASS** |
| prompt schema 漂移 | `conversation_compaction_user.md` 用 `<<compact_output_rules>>` / `<<compact_output_template>>` 占位符 | code-generated rules/template 是唯一结构真源 | `compact_output_prompt_rules_v4()` 与 `compact_output_template_v4()` 同源 `_ROOT` descriptor（compact_structure.py:176-201） | **PASS** |
| S2 边界漂移 | 全 production diff 搜索 `ResolvedCompactorEvidenceFact`、public Tool Trace 新 typed fact projection、README | 应零命中 | 零命中；`test_tool_trace_queries.py` 仅 v3→v4 fixture 迁移 | **PASS** |
| `source_boundary_refs` 双写 | `compact_artifact_json_vnext:824-827` vs `build_context_compacted_payload:1248-1249` | 同公式：`[current_input_ref, *covered_source_refs]` | 均从 `accepted_truth.covered_source_refs` property（line 2548-2562）派生，单一定义 | **PASS** |
| coverage partition disjoint/boundary-order 交叉污染 | `_validate_committed_coverage:485-492` | represented/omitted exact partition + 各自按 boundary order | explicit `set().intersection()` + `set().union() == set(boundary_labels)` | **PASS** |

## Findings

### F-DS-1（medium）: `run_input_material_block` 中 `evidence_refs` fallback 允许 `canonical_evidence_refs=()` 时退化为 `(accepted_evidence_id,)`

- **Severity**: medium
- **File/line**: `dayu/host/compact_material.py:800-804`
- **直接证据**:
  ```python
  evidence_refs = (
      (accepted_evidence_id,)
      if accepted_evidence_id is not None and not canonical_evidence_refs
      else canonical_evidence_refs
  )
  ```
  当调用方传入 `canonical_evidence_refs=()` 且 `accepted_evidence_id="X"` 时，`evidence_refs` 被设为 `("X",)`，绕过 `canonical_evidence_refs` 应显式非空的 contract。
- **反例**: `PromptLocalProvenanceEntry.__post_init__:323-334` 对 `EVIDENCE_BACKED_FACT` kind 要求非空 refs；`RunInputMaterialBlock.__post_init__:281-294` 同样强制。但 fallback 在两者之前"修复"了空 refs，消除了上游调用方必须显式传入的约束压力。
- **Impact**: 当前所有调用方均显式传入正确 `canonical_evidence_refs`，fallback 不会被触发。但 fallback 存在意味着未来调用方可能依赖此隐式行为，导致 `canonical_evidence_refs` 语义被 `accepted_evidence_id` 单值 fallback 截断。
- **修法**: 移除 fallback，强制调用方显式传入 `canonical_evidence_refs`。或至少将 fallback 收窄到 `PromptLocalProvenanceEntry` 构造点（已在 C2 确认 `PromptLocal.__post_init__` 做 final gate）。
- **Verdict**: **accepted**（与 C2 AgentDS F2 裁决一致；defense-in-depth，当前调用方安全，但建议后续 cleanup 移除）

### F-DS-2（low）: `_aggregate_pass_candidates` 中 `fact.selection_labels[0]` 隐式依赖 retained atom 的 `selection_labels` 恒为单元素

- **Severity**: low
- **File/line**: `dayu/host/compaction_operation.py:1256-1263`
- **直接证据**: `fact.selection_labels[0]` 加 `len(fact.selection_labels) == 1` guard 识别 retained atom。该 invariant 由 `derive_compact_accepted_replacement_v4:1684` 保证（`selection_labels=(entry.source_label,)`），但两者跨模块（`compaction.py` ↔ `compaction_operation.py`），无显式 contract。
- **Impact**: 若 future refactor 改变 retained atom 的 `selection_labels` shape（如追加 context label），`len == 1` guard 会使 retained atom 被静默跳过（视为 new fact），导致 retained fact 丢失。
- **修法**: 在 `CompactAcceptedEvidenceFactV4` 或 `derive_compact_accepted_replacement_v4` 中定义显式 `is_retained: bool` property，让 consumer 不依赖 shape heuristic。
- **Verdict**: **accepted**（当前 invariant 由 `derive` 的 retained 分支语法保证，不构成 correctness bug；但跨模块隐式契约值得后续加固）

### F-DS-3（low）: `_canonical_candidate` 对 `retained_previous_evidence_fact_labels` 执行 boundary-order canonicalization，但 `compact_proposal_boundary_binding_issues_v4:1862-1874` 已对 labels 执行过 `NON_CANONICAL_SOURCE_LABEL_ORDER` 检查

- **Severity**: low
- **File/line**: `dayu/host/context_governance.py:125`（调用 canonicalize）+ `dayu/host/compaction.py:1862-1874`（binding 已 reject non-canonical order）
- **直接证据**: `accept_compact_candidate_v4` 先调用 `compact_proposal_boundary_binding_issues_v4`（line 117），若 issues 非空则返回 report。这意味着 `_canonical_candidate` 收到的 candidate 已经通过 NON_CANONICAL_ORDER 检查。`_ordered_labels` 的 sort 操作在已 canonical 的 labels 上是 no-op。
- **Impact**: 双重 canonicalization 不改变正确性，但暗示 `_canonical_candidate` 被设计为"总是 canonicalize"，而 binding validator 也做了 canonicality 检查——形成跨函数冗余职责。
- **修法**: accepted-as-is。binding validator 的 canonicality check 是 owner contract（governance + durable parser 复用），`_canonical_candidate` 的 sort 是 defense-in-depth。建议在 `_ordered_labels` docstring 注明它可能收到已 canonical 的输入。
- **Verdict**: **accepted**

## Semantic ownership verification（跨模块）

| 业务事实 | 唯一 owner | consumer（单向依赖） | dual owner? |
|---|---|---|---|
| v4 DTO 类型定义 | `compaction.py` | compact_structure, governance, payload, artifact, memory, operation | 否 |
| JSON 结构 descriptor | `compact_structure.py:_ROOT` | template/schema/rules/parser 四投影 | 否 |
| label binding 校验 | `compact_proposal_boundary_binding_issues_v4`（compaction.py） | governance:117 + payload:114 | 否（复用同一函数） |
| replacement derivation | `derive_compact_accepted_replacement_v4`（compaction.py） | governance:126 + validate:1894（内部调用） | 否 |
| acceptance gate | `accept_compact_candidate_v4`（context_governance.py） | compaction_operation:1023 | 否（`_CompactAcceptancePermit` 独占） |
| durable strict parser | `parse_context_compacted_semantic_payload`（compact_payload.py） | memory, run_input/reconnect | 否 |
| EventLog payload 构造 | `build_context_compacted_payload`（context_events.py） | dispatch, engine_ingest | 否 |
| artifact JSON 构造 | `compact_artifact_json_vnext`（compact_payload.py） | compact_artifact, dispatch, engine_ingest | 否 |
| Memory fact projection | `_facts_from_accepted_event`（memory.py） | memory projection pipeline | 否 |
| rolling projection | `_previous_compacted_view_pair_from_replacement`（compact_material.py） | compact material assembly | 否 |

## 无兼容层 / heuristic / god function 验证

- 全 diff `rg 'hasattr\|getattr'` 零命中
- 全 diff 无 v3 alias、re-export、dual reader、`accepted_candidate` 残留
- 无自然语言 entailment / similarity heuristic
- `PromptLocalProvenanceEntry` 无 `accepted_evidence_id` 旧字段
- `RunInputMaterialBlock.accepted_evidence_id` 仅用于 current evidence admission，不进 provenance / replacement / durable read-model
- 无 god function：`derive_compact_accepted_replacement_v4` 是纯函数（input→output）；`accept_compact_candidate_v4` 是编排函数（顺序调用 validator + derive + duplicate/caps/info + audit）

## S2 boundary 验证

- `ResolvedCompactorEvidenceFact`：零命中
- public Tool Trace 新 typed fact projection：零命中
- README 修改：零命中（归 S2）
- `test_tool_trace_queries.py` 仅 v3→v4 fixture 迁移，未引入 S2 语义

## 未覆盖 mandatory owner tests

以下 owner contract 有生产代码约束但无定向 negative test：

1. 非 evidence kind 的 `CompactSourceBoundaryEntryV4` 带非空 `canonical_evidence_refs` → 由 `__post_init__:702-706` 强制拒绝，仅由 helper 构造成功隐式覆盖。（与 C2 AgentMiMo F-01 一致）
2. `_validate_aggregate_boundary_unique_membership` 的 duplicate ref 拒绝路径 → 由 `test_compacted_semantic_parser_rejects_invalid_aggregate_membership_or_binding` 的参数 `aggregate=["evidence:existing","evidence:existing"]` 覆盖。**经复核：已覆盖。**
3. `validate_input_binding` 的 caps 字段逐一 mismatch → `test_compaction_contract.py:1091-1098` 已覆盖 `session_summary_char_cap` 篡改；其余 8 caps 字段由 exhaustive 9-field comparison 结构保证，单一 mismatch 即触发。

**结论**: 无未覆盖 mandatory owner test。AgentMiMo C2 F-01（非 evidence kind boundary entry 定向 negative）是 low residual，不阻塞。

## Verdict

**ACCEPTED** — 无 blocking 或 high finding。

3 个 finding（1 medium、2 low）均为 accepted-as-is：
- F-DS-1（medium）: `run_input_material_block` fallback → accepted（defense-in-depth，当前调用方安全）
- F-DS-2（low）: multi-pass 隐式 retained atom shape 依赖 → accepted（invariant 由 derive 保证）
- F-DS-3（low）: 双重 canonicalization → accepted（defense-in-depth）

全部 11 项 adversarial pass 未命中；跨模块 semantic ownership 矩阵无一 dual owner；无兼容层/heuristic/god function；S2 边界无漂移；无未覆盖 mandatory owner test。

S1 可进入下一 gate（final closeout / draft PR）。

---

## Controller re-review resolution（2026-08-06）

Controller 不接受 F-DS-1 medium accepted-as-is，指令窄 re-review。以下仅复核 F-DS-1 与 F-DS-2。

### F-DS-1 re-review：`run_input_material_block` evidence_refs fallback

**直接证据链**：

```text
# compact_material.py:801-804 — 机械投影
evidence_refs = (
    (accepted_evidence_id,)
    if accepted_evidence_id is not None and not canonical_evidence_refs
    else canonical_evidence_refs
)

# compact_material.py:820-821 — 传入 RunInputMaterialBlock
accepted_evidence_id=accepted_evidence_id,
canonical_evidence_refs=evidence_refs,

# compact_material.py:287-292 — __post_init__ 强制等式（evidence block）
if self.canonical_evidence_refs != (self.accepted_evidence_id,):
    raise ValueError(
        "accepted evidence block canonical_evidence_refs must equal "
        "(accepted_evidence_id,)"
    )
```

**裁决**：**不成立，dismissed**。

`run_input_material_block` 的 fallback 不是兼容补丁或下游补偿，而是 accepted plan 明确允许的 owner-boundary 机械投影：

1. 上游 `RunInputMaterialBlock.accepted_evidence_id` 是 current evidence admission 的 singular canonical id owner（plan §24.3 明确允许保留）。
2. current evidence producer 必须把该 singular id 机械形成单元素 tuple → `(accepted_evidence_id,)`。`run_input_material_block:801-804` 正是该机械投影在 owner boundary 的正确位置。
3. `RunInputMaterialBlock.__post_init__:290` 强制 `canonical_evidence_refs == (accepted_evidence_id,)`，是 final gate，捕捉任何 upstream mismatch。
4. 不可能截断 multi-ref：current evidence admission contract 自身是 singular；previous fact 路径 `accepted_evidence_id=None` 使 fallback 不触发，`canonical_evidence_refs` 直接使用显式传入的 per-fact refs。
5. 两路径完全分离：`accepted_evidence_id is not None` → current evidence 机械投影；`accepted_evidence_id is None` → 显式 `canonical_evidence_refs`（multi-ref possible）。

该 fallback 是 **正确 owner-boundary 机械投影，不是旧兼容/下游 fallback/heuristic**。原 F-DS-1 误判 severity 为 medium，现 dismissed。

### F-DS-2 re-review：`fact.selection_labels[0]` 隐式依赖

**裁决**：**不成立，dismissed**。

`_aggregate_pass_candidates:1256-1263` 的 retained atom 识别逻辑：

```python
if len(fact.selection_labels) == 1
and root_input.source_kind(fact.selection_labels[0])
is CompactSourceKindV4.PREVIOUS_EVIDENCE_FACT
```

`kind + selection_labels` 是 `CompactAcceptedEvidenceFactV4` 的显式 binding：
- retained atom: `selection_labels=(single_previous_label,)` + `source_kind=PREVIOUS_EVIDENCE_FACT` — 由 `derive_compact_accepted_replacement_v4:1684` 唯一构造
- new fact atom: `selection_labels` 只能选 `EVIDENCE_MATERIAL`（`COMPACT_FACT_SOURCE_KINDS_V4` 约束），即使 `len==1` 也因 kind 不同被过滤

两条件联合构成 retained atom 的显式 typed contract，不需要新增 `is_retained: bool` 字段。新增字段属于过度 schema（为 consumer 便利性向 domain type 添加冗余 boolean），违反 `最小化满足需求` 原则与 `禁止 God dataclass` 约束。原建议 dismissed。

### Revised verdict

**ACCEPTED — 无 unresolved finding。** 原 3 findings 全部 dismissed（F-DS-1/F-DS-2 不成立，F-DS-3 维持 low accepted-as-is）。S1 可进入 final closeout / draft PR。
