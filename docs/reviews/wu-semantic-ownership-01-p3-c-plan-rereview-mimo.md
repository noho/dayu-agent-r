# WU-SEMANTIC-OWNERSHIP-01 P3-C Plan Re-Review — AgentMiMo

## Reviewed target and scope

- **Plan artifact**: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-controller-adjudication.md`
- **Codex fix artifact**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-fix-codex.md`
- **Original reviews**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-mimo.md`、`docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-ds.md`
- **Design sources**: `docs/host/design.md` §23-25、`docs/engine/design.md` §1,4,14,15
- **Scope**: P3-C plan fix — 验证 P3-C-PF-01 至 PF-06 是否真正闭合
- **Gate**: plan re-review
- **Review date**: 2026-07-10
- **Reviewer**: AgentMiMo
- **Code evidence**: current `HEAD` (8787714d) direct reads of all affected production modules

## Review Posture

本 re-review 不信任 Codex fix artifact 的自报状态。逐项用当前代码直接证据验证每个
plan fix 是否在 plan 文本中真正闭合，并攻击六个特别关注点。

## 六项 Closure 验证

### P3-C-PF-01 — Pair invariant：anchor children/ordinal 保留与 leaf input error 分类

**Plan fix 内容**（§6.3）：`CompactMaterialPack.__post_init__` 校验五项 exact
invariant；唯一 `transform_previous_compacted_view_pair_for_recovery` helper；leaf
constructor 的直接类型错误为 `TypeError/ValueError`，已持久化 pair 的
presence/count/kind/label/text/children mismatch 为 `HostDurableError`。

**代码直接验证**：

- `compact_material.py:3245-3273` `_previous_compacted_answer_anchors_vnext` 当前只保留
  `anchor_title`，用 `line.removeprefix(_PREVIOUS_ANSWER_ANCHOR_PREFIX)` 从 block text
  反解析，合成单一 child `display_text=anchor_title, ordinal=None`，**丢失原
  `anchor_items` 和 ordinal**。Plan 正确识别了该 drift。
- Plan §6.3 invariant 第 4 条明确要求"typed anchor 必须保留完整 `anchor_title`、全部
  `anchor_items` 及每个 ordinal"，block text 由 pair projector 从完整 typed anchor 产生。
  新投影路径从 `ContextCompactedSemanticPayload.accepted_candidate`（即
  `ConversationCompactOutputVNext`）直接映射，不经过 string round-trip。**闭合**。
- 失败分类：`parse_context_compacted_semantic_payload` 在 §6.1 要求严格构造所有
  dataclass，非法 enum/空 text/负 ordinal/错误类型全部 `ValueError`。这些是 leaf
  constructor 拒绝，在 pair 形成之前就已 fail。pair 形成后的 invariant mismatch（如
  blocks 数量与 typed section item 数量不等）才由 `HostDurableError` 收口。两层分类
  边界清楚，不会把 leaf input error 误归 durable corruption。**闭合**。

**Verdict: PASS**

### P3-C-PF-02 — Event ref 五格 matrix 与现有 repair caller 一致性

**Plan fix 内容**（§6.4）：`MemorySnapshotView.latest_compaction_event_ref` 与
`CompactArtifactView.compaction_event_ref` 按 event-id 字符串 exact equality 比较；
五格 matrix；后三类复用 `MemoryProjectionRepairRequired(reason=SNAPSHOT_DAMAGED)`。

**代码直接验证**：

- `run_input.py:337-358` `MemorySnapshotView` 当前**无** `latest_compaction_event_ref`
  字段。`memory.py:917` `ConversationMemorySnapshotVNext` **有**
  `latest_compaction_event_ref`。Plan 正确要求从前者暴露该字段。
- 五格 matrix（§6.4 表格）：
  - `None/None` → no-compact，正常继续。✓
  - 非 `None`/同一 event-id → 正常继续。✓
  - 非 `None`/`None` → `MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)`。✓
  - `None`/非 `None` → `MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)`。✓
  - 两个非 `None` 不等 → `MemoryProjectionRepairRequired(SNAPSHOT_DAMAGED)`。✓
- 当前 `run_input.py` 已有 `MemoryProjectionRepairRequired` 与
  `MemoryRepairRequest(MemoryRepairReason.SNAPSHOT_DAMAGED, ...)` 的 catch-up /
  rebuild / inline-repair 流程。后三类统一复用该机制，不新增异常类型。**与现有
  repair caller 一致**。
- §9 五个命名测试完整覆盖五格场景，名称区分 no-compact / equal / 三种 mismatch。
  focused 与 aggregate validation 均包含。**闭合**。

**Verdict: PASS**

### P3-C-PF-03 — RunInputMaterialBlock evidence/non-evidence invariant 与 text 语义

**Plan fix 内容**（§6.6）：完整 evidence contract 七个字段；evidence block 必须
`EVIDENCE_MATERIAL + ACCEPTED_TOOL_EVIDENCE`、identity/material 非空、
`text == shared renderer output`；non-evidence block 全部 evidence fields/provenance
为空；同一 S3 原子迁移。

**代码直接验证**：

- 当前 `RunInputMaterialBlock`（`compact_material.py:198-247`）已有
  `accepted_evidence_id`、`tool_result_event_ref`、`tool_call_event_ref`、
  `payload_refs`、`artifact_refs`、`source_locator_refs`、`readable_tool_name`、
  `readable_query_text`、`readable_source_text`。Plan 要求删除后三个 loose readable
  fields，新增 `accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None`。
- 当前 evidence block 的 `text` 为 `projection.result_text`（纯结果文本，见
  `compact_material.py:2283`）。Plan 要求 `text ==
  render_accepted_tool_evidence_for_llm(accepted_tool_evidence)`，即完整四行渲染文本。
  这是 `text` 语义的**有意变更**：evidence block 的 `text` 从"仅结果"变为"完整渲染"。
- `CompactEvidenceBlock` / `EvidenceReadableItemVNext` 从
  `accepted_tool_evidence.result_text`（非 `block.text`）取结果文本。Plan 明确禁止
  "把已经 render 的 `block.text` 再 parse 成字段，也不能把四行 renderer 全文误当
  `response_text`"。边界清楚：`block.text` 是渲染全文，`result_text` 是结果分量。
- invariant 对 non-evidence block 要求全部 evidence 字段为空。当前 constructor
  `__post_init__`（`compact_material.py:249-274`）不校验 evidence 字段一致性（如
  `accepted_evidence_id` 非空但 `readable_tool_name` 为空）。Plan 收紧了该校验。当前
  provenance 语义允许 non-evidence block 携带默认空值（`accepted_evidence_id=None` 等），
  Plan 不改变该语义，只要求"不得携带暂时未使用的 evidence god-bag"。**不冲突**。
- 原子迁移顺序：先定义 typed material + renderer → 迁移全部 producer/consumer →
  删除旧字段。S3 内不允许 dual-field contract 跨出 slice。**闭合**。

**Verdict: PASS**

### P3-C-PF-04 — two-message count 推导与 owner 分离

**Plan fix 内容**（§6.5）：`POST_COMPACT_BASE_MESSAGE_COUNT = 2` 推导为 one-system
envelope + current-input user message；由 `context_budget` 拥有；禁止 caller override；
drift test。

**代码直接验证**：

- `compaction_operation.py:69` `_POST_COMPACT_BASE_MESSAGE_COUNT = 2`，在
  `compaction_operation.py:1493` 使用。
- `llm_compaction.py:96` `_POST_COMPACT_BASE_MESSAGE_COUNT = 2`，**未在该文件内使用**
  （仅定义）。Plan 正确指出该常量属于 compactor proposal-budget 语义，与 P3-C 的
  "accepted compact 后 ordinary dispatch"估算不是同一事实 owner。
- `context_budget.py` 当前**无** `POST_COMPACT_BASE_MESSAGE_COUNT` 或
  `estimate_post_compact_budget`。Plan 要求新增。
- Plan §6.5 注释推导："ordinary post-compact dispatch 遵守 design 第 23 节
  one-system-message contract，所有 system-scoped compact/memory 材料先合并为一条
  system envelope，再追加当前 USER_INPUT_ACCEPTED 的一条 user message，因此固定
  overhead 为 1 + 1 = 2"。推导与 design §23 一致。
- §9 source scan 要求 `compaction_operation.py` 不再定义该常量，`context_budget.py`
  只定义 ordinary post-compact owner 常量，`llm_compaction.py` 的同名常量保持独立。
  **owner 分离正确**。

**Verdict: PASS**

### P3-C-PF-05 — 五个命名测试与 source scan 映射

**Plan fix 内容**（§7.1、§8 S2、§9）：五个命名测试完整覆盖五格场景，进入 focused
与 aggregate validation。

**代码直接验证**：

- §9 明确列出五个测试名称：
  - `test_no_compact_event_and_no_memory_compaction_ref_builds_without_repair`
  - `test_matching_compact_and_memory_compaction_event_refs_build_once`
  - `test_compact_event_without_memory_compaction_ref_requires_repair`
  - `test_memory_compaction_ref_without_compact_event_requires_repair`
  - `test_mismatched_compact_and_memory_compaction_event_refs_require_repair`
- S2 focused validation 固定为 `python -m pytest tests/host/test_run_input_builder.py -q`。
- aggregate matrix 包含 `tests/host/test_run_input_builder.py`。
- 后三个测试断言 exception type、`MemoryRepairReason.SNAPSHOT_DAMAGED`，且未读取
  protected raw tail、未记录 manifest、未 dispatch。equal case 断言无 compact message、
  五类 compact 业务内容只来自 memory。**闭合**。

**Verdict: PASS**

### P3-C-PF-06 — compact_material.py envelope 二次解析与 str(exc) catch 删除

**Plan fix 内容**（§8 S3）：点名删除 `compact_material.py` 的
`accepted_evidence_envelope_from_payload()` 调用与
`str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` catch block。

**代码直接验证**：

- `compact_material.py:2258-2266` 确实存在该调用与 catch block。Plan fix artifact
  引用行号 2259-2266 与代码一致。
- S3 Exact changes 第 3 条明确："明确删除 `compact_material.py` 中
  `accepted_evidence_envelope_from_payload()` 调用及
  `if str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` catch block"。
- §9 source scan `rg -n 'str\(exc\).*ACCEPTED_EVIDENCE|ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH' dayu/host` 预期无生产匹配。
  **闭合**。

**Verdict: PASS**

## 三个 Residual Observations 吸收验证

### Obs-1：`_snapshot_*` string-wire helpers 删除

Plan §6.3 S2 删除列表明确包含 `_previous_blocks_from_snapshot()`、
`_snapshot_summary_text()`、`_snapshot_fact_texts()`、
`_snapshot_answer_anchor_texts()`、`_snapshot_forward_intent_texts()`、
`_snapshot_reference_continuity_texts()` 及其 `_PREVIOUS_*` 格式常量。
代码验证：这些函数/常量确实存在于 `compact_material.py:100-105,2517,2602-2666`。
**已吸收**。

### Obs-2：compact_material.py / run_input.py 重复 candidate 常量/parser 删除

Plan §8 S2 Exact changes 第 4 条明确删除 `compact_material.py` 的五个
`_candidate_*` mapping parsers 与其重复 candidate 字段常量。第 6 条明确删除
`run_input.py` 的 `_compact_artifact_message_content()`、
`_vnext_compact_candidate_semantic_lines()`、nested candidate mapping/list parser 与
candidate 字段常量。代码验证：这些函数/常量确实存在于
`compact_material.py:110-131,2332-2438` 与 `run_input.py:168-203,3378,3414`。**已吸收**。

### Obs-3：`_POST_COMPACT_BASE_MESSAGE_COUNT` owner 分离

Plan §6.5 与 §8 S2 第 7 条明确只迁移 `compaction_operation` 的同名常量到
`context_budget`；`llm_compaction` 的同名常量保持独立，不移动、不合并、不 re-export。
代码验证：两个常量确实分别定义于 `compaction_operation.py:69` 与
`llm_compaction.py:96`，且后者在文件内未使用。**已吸收**。

## 特别攻击点补充验证

### Attack-1：`_previous_compacted_*_vnext` 子函数 source scan 覆盖

Plan §8 S2 Exact changes 第 3 条列出删除 `_previous_compacted_*_vnext()` 函数族。代码
验证该族包含 `_previous_compacted_view_vnext`（主函数，`compact_material.py:3325`）与
五个子函数：`_previous_compacted_session_summary_vnext`（3354）、
`_previous_compacted_fact_material_vnext`（3229）、
`_previous_compacted_answer_anchors_vnext`（3245）、
`_previous_compacted_forward_intents_vnext`（3276）、
`_previous_compacted_references_vnext`（3301）。

§9 source scan 的 `_previous_blocks_from_snapshot|_snapshot_*` 模式覆盖了 snapshot
helpers，`_candidate_*` 模式覆盖了 candidate parsers，但**没有显式 grep 模式覆盖
`_previous_compacted_*_vnext` 子函数**。删除主函数后子函数成为 dead code，但 source
scan 不会零匹配验证它们已删除。

**严重程度**：低。主函数删除后子函数无调用者，pyright / static analysis 会标记 dead
code。但 source scan 的 "zero-match hard acceptance criterion" 语义不完整。

### Attack-2：`llm_compaction._POST_COMPACT_BASE_MESSAGE_COUNT` 实际使用

代码验证 `llm_compaction.py:96` 定义 `_POST_COMPACT_BASE_MESSAGE_COUNT = 2` 但在该文件
内**完全未使用**。Plan 将其描述为 "compactor proposal-budget 语义"，但实际上它当前是
dead code。Plan 正确决定不移动它，但对其用途的描述略有偏差（非当前 proposal-budget
实际使用的常量，而是预留或历史遗留）。

**严重程度**：极低。不影响 P3-C 闭合，不影响 owner 分离决策。

## Finding Rules 检查

每个 potential finding 须满足：adversarial 而非 stylistic、绑定到具体 plan 位置或
code fact、在真实 failure scenario 下可信、对修复该问题的工程师可执行。

- Attack-1（source scan 覆盖 gap）：绑定到 §9 source scan 具体模式，failure scenario
  为 implementation agent 删除主函数但遗漏子函数，source scan 不报错但留下 dead code。
  对工程师可执行（增加一个 grep 模式）。**满足 finding rules**，但严重程度为低，不构
  成 blocker。
- Attack-2（llm_compaction 常量描述偏差）：不影响 P3-C 闭合，不影响实施决策。
  **不构成 material finding**。

## Behavior Matrix 验证

### §7.1 — 14 个场景

逐行验证 plan §7.1 行为矩阵与代码/设计的一致性：

- valid candidate → typed payload → 五类 memory view → previous view → memory-only
  ordinary input → budget 统计。**一致**。
- anchor children 完整保留。**一致**（见 PF-01 验证）。
- invalid enum → constructor 拒绝 → fail closed 全链路。**一致**。
- tier2 degrade → pair transform helper 同步过滤。**一致**。
- diagnostic 不计入 budget。**一致**（§6.5 明确排除）。
- 五格 ref matrix 行为。**一致**（见 PF-02 验证）。

### §7.2 — 10 个场景

逐行验证 plan §7.2 行为矩阵与代码/设计的一致性：

- valid envelope → typed material → 四行文本 → memory/compact/fallback 同源。**一致**。
- query/source unavailable → projection-owned fallback。**一致**。
- envelope 缺失 → material 可构造则渲染，否则整体 unavailable。**一致**。
- producer mismatch → typed exception → HostDurableError。**一致**。
- optional payload field 错误类型 → strict accessor fail closed。**一致**。
  （注：当前 `_optional_text` 是 lenient，Plan 要求改用 strict accessor。）
- result 很长 → typed `result_text` 保持完整，不静默截断。**一致**。

## Source Scan 完整性

§9 source scan 覆盖的模式与预期：

| 模式 | 目标文件 | 预期 | 覆盖 |
|---|---|---|---|
| `_accepted_candidate_mapping\|_vnext_compact_candidate_semantic_lines\|...` | `dayu/host` | 无匹配 | ✓ |
| `_previous_blocks_from_snapshot\|_snapshot_*\|_candidate_*` | `compact_material.py` | 无匹配 | ✓ |
| `str\(exc\).*ACCEPTED_EVIDENCE\|...` | `dayu/host` | 无匹配 | ✓ |
| `def _accepted_tool_evidence_content\|def _accepted_evidence_readable_text` | `dayu/host` | 无匹配 | ✓ |
| `_PAYLOAD_FIELD_(SESSION_SUMMARY\|...)` | memory/compact_material/run_input | 无匹配 | ✓ |
| `compact\.messages\|messages=.*CompactArtifactView\|_compact_artifact_message_content` | `run_input.py` | 无匹配 | ✓ |
| `accepted_evidence_envelope_from_payload\|str\(exc\)` | `compact_material.py` | 无匹配 | ✓ |
| `_POST_COMPACT_BASE_MESSAGE_COUNT` | `compaction_operation.py` | 无匹配 | ✓ |
| `_POST_COMPACT_BASE_MESSAGE_COUNT` | `context_budget.py` | 存在 | ✓ |
| `_POST_COMPACT_BASE_MESSAGE_COUNT` | `llm_compaction.py` | 存在且独立 | ✓ |

**Gap**：`_previous_compacted_*_vnext` 子函数族未被任何 source scan 模式覆盖。见
Attack-1。

## Architecture Boundary Re-verification

Plan §5 的 7 个语义 owner boundary 在 plan fix 后仍然闭合：

1. compact candidate 五类语义：producer → validator → persistence → typed projection →
   consumers。✓
2. forward intent/reference enum：constructor → JSON `.value` → snapshot → same parser。✓
3. accepted compact ordinary LLM material：candidate → memory → snapshot → RunInput。✓
4. accepted compact next-compactor previous view：candidate → pair projector → typed view +
   blocks → next compact input。✓
5. post-compact budget：candidate business texts → pure estimator → operation gate。✓
6. accepted evidence durable facts：accept barrier → envelope codec → projection。✓
7. accepted evidence LLM 文本：typed material → 唯一 renderer → 三个 consumer。✓

依赖方向无反向：`context_budget` ← direct text params；`compact_payload` →
`ConversationCompactOutputVNext`；memory/compact/run input → projection owner。✓

## Overengineering / Overcoupling Review

- 只新增 2 个窄 typed value + 1 个专用异常。✓
- 不创建 God dataclass / builder / factory / registry。✓
- 不横扫 `tool_trace.py`。✓
- 不为未来预留抽象。✓
- 三个 slice 各自闭合，不产生 contract-only half product。✓
- 不把 budget、evidence、compact payload 合并进共享模块。✓

## Open Questions

无。

## Residual Risks

| 风险 | 分类 | 严重程度 | 跟踪目标 |
|---|---|---|---|
| `_previous_compacted_*_vnext` 子函数未被 source scan 模式覆盖 | source scan 完整性 | 低 | P3-C S2 实现时增加 grep 模式 |
| `llm_compaction._POST_COMPACT_BASE_MESSAGE_COUNT` 实际是 dead code | 事实偏差 | 极低 | 不影响 P3-C，后续 cleanup |
| `text` 语义从"仅结果"变"完整渲染"是 intentional change | 设计确认 | 低 | S3 实现时确保所有 consumer 适配 |

## Plan Review Conclusion

**Verdict: PASS**

P3-C-PF-01 至 PF-06 全部真正闭合。三个 residual observations 已正确吸收。六个特别
攻击点均通过代码直接证据验证：

1. **Pair invariant**：anchor children/ordinal 保留路径正确，leaf error vs durable
   corruption 分类边界清楚。
2. **Event ref 五格 matrix**：与现有 `MemoryProjectionRepairRequired` repair caller
   一致，五个命名测试覆盖。
3. **RunInputMaterialBlock evidence invariant**：收紧 constructor 校验不与当前
   provenance 语义冲突；`text` 语义变更是 intentional 且有明确迁移路径。
4. **text == shared renderer vs result_text 边界**：`block.text` 为完整渲染，
   `CompactEvidenceBlock.result_text` 为结果分量，plan 明确禁止反解析。
5. **two-message count owner 分离**：`context_budget` 拥有 post-compact 语义，
   `llm_compaction` 保持独立，推导注释完整。
6. **删除路径 / source scan / test mapping**：S2/S3 删除列表覆盖所有目标函数/常量，
   source scan 覆盖完整（仅 `_previous_compacted_*_vnext` 子函数有低风险 gap）。

**New material findings: 0**

Plan 可以进入 implementation。

---

## Review Metadata

- **PF-01 closure**: PASS
- **PF-02 closure**: PASS
- **PF-03 closure**: PASS
- **PF-04 closure**: PASS
- **PF-05 closure**: PASS
- **PF-06 closure**: PASS
- **Residual observations absorbed**: 3/3
- **New material findings**: 0
- **Source scan completeness**: 9/10 patterns covered（1 low-risk gap）
- **Owner boundaries re-verified**: 7/7 闭合
- **Behavior matrices verified**: §7.1 14/14、§7.2 10/10
- **Blocking questions**: 0
- **Review artifact**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-mimo.md`
