# WU-SEMANTIC-OWNERSHIP-01 P3-C Plan Re-Review（AgentDS）

## Review metadata

- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01 / P3-C - Context compaction payload, evidence text, and LLM-safe projection contract`
- **Gate**: plan re-review（plan-fix 后、implementation 前）
- **Timestamp**: `2026-07-10T16:45:36+08:00`
- **Reviewed plan**: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`
- **Reviewed fix artifact**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-fix-codex.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-controller-adjudication.md`
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control source**: `docs/host/issues-implementation-control.md`
- **Current code**: `dayu/host/compaction.py`, `dayu/host/compact_material.py`, `dayu/host/compact_pipeline.py`, `dayu/host/run_input.py`, `dayu/host/compaction_operation.py`, `dayu/host/compact_payload.py`, `dayu/host/llm_compaction.py`, `dayu/host/context_budget.py`, `dayu/host/accepted_result_projection.py`, `dayu/host/memory.py`, `dayu/host/evidence.py`
- **Scope**: 只写 re-review artifact；不修改 plan、生产代码、测试、control doc、README 或 reviewer artifacts；不 commit、不 push、不创建 PR

## Review posture

本 re-review 是 adversarial pass。目标不是证明 plan-fix 可行，而是找出最强的基于证据的理由说明该 plan 还不应交给 implementation agent。每个 finding 必须绑定到具体 plan 文本位置或 code fact。

## Method summary

1. 逐项验证 P3-C-PF-01 至 PF-06 是否在 plan text 中真正闭合，不依赖 fix artifact 自报。
2. 检查三个 residual observations 是否正确吸收。
3. 应用七个专项攻击向量。
4. 扫描 plan-fix 新引入的 material finding。
5. 压测 architecture boundary、best-practice、optimal-solution、overengineering、overcoupling lenses。

## PF-01 至 PF-06 closure 逐项验证

### P3-C-PF-01 — pair invariant / anchor children / failure taxonomy

- **Plan 位置**: 6.3 节（Typed previous compacted view，不再 string round-trip）
- **声称 fix**: 固定 `CompactMaterialPack` blocks/readable-view exact invariant、validation point、failure taxonomy、单一 pair-transform helper

**直接代码证据**：

1. `compaction.py:1621-1670` — `CompactMaterialPack` 当前只有 `previous_compacted_view: tuple[CompactMaterialBlock, ...]`，无 `previous_compacted_readable_view` 字段。确认 fix 目标成立。
2. `compact_material.py:3245-3273` — `_previous_compacted_answer_anchors_vnext()` 从 block text `splitlines()` 逐行解析，每行只提取 title（`line.removeprefix("answer_anchor=")`），构造单一 `ReadableAnswerAnchorItemVNext(display_text=anchor_title, ordinal=None)`。原始 candidate 的完整 `anchor_items` 和 `ordinal` 全部丢失。
3. `compact_material.py:3325-3351` — `_previous_compacted_view_vnext()` 从 blocks 调用五个 `_previous_compacted_*_vnext()` 重建 typed view，形成完整的 string round-trip。
4. `compact_material.py:3369-3395` — `_parse_previous_forward_intent_text()` 用 `; ` 分号 split 解析私有 wire format。
5. `compact_material.py:3398-3415` — `_parse_previous_reference_continuity_text()` 同上。

**Plan fix 验证**：

- 6.3 节 invariant 1-5 精确覆盖：empty/None 等价（invariant 1）、kind/section 白名单（invariant 2）、summary presence/text 一致（invariant 3）、四类 item count/order/label/text 一一对应（invariant 4）、原子 pair projection 禁止单侧重建（invariant 5）。
- Anchor children/ordinal 完整保留：invariant 4 明确 "typed anchor 必须保留完整 anchor_title、全部 anchor_items 及每个 ordinal；block 的业务文本由同一个 pair projector 从该完整 typed anchor 产生，不能再从 text 反解析 children"。
- Failure taxonomy 正确：leaf constructor 类型错误 → `TypeError`/`ValueError`；已持久化 pair 的 invariant mismatch → `HostDurableError`。区分标准是输入来源（直接构造 vs 从 CONTEXT_COMPACTED 读出），而非错误表象。由于 CONTEXT_COMPACTED 已由 digest 校验，pair mismatch 确实表示 durable semantic projection 损坏。
- 单一 `transform_previous_compacted_view_pair_for_recovery()` helper：tier2/tier3 统一入口，禁止分别实现 `filter_blocks()` / `filter_readable_view()`。
- S2 exact changes item 3 点名删除 `_parse_previous_forward_intent_text()`、`_parse_previous_reference_continuity_text()` 等全部 string-wire helpers。

**Verdict**: CLOSED。Pair invariant 充分具体，anchor children/ordinal 保留有明确要求，leaf error vs durable corruption 区分正确。

### P3-C-PF-02 — event ref 五格 matrix / repair / 删除路径

- **Plan 位置**: 6.4 节（Ordinary RunInput 只消费 Memory 的 accepted compact projection）
- **声称 fix**: 固定 event-id exact equality、五格 matrix、`MemoryProjectionRepairRequired` 复用、点名删除 provider message 生成与 builder `*compact.messages`

**直接代码证据**：

1. `run_input.py:337-358` — `MemorySnapshotView` 没有 `latest_compaction_event_ref` 字段。确认 fix 目标成立。
2. `run_input.py:424-437` — `CompactArtifactView` 携带 `messages: tuple[AgentMessage, ...]`，没有 `compaction_event_ref`。
3. `run_input.py:1589-1633` — `DurableCompactArtifactProvider._load_compact_artifact_tx()` 构造 `SystemMessage`（line 1622-1626），调用 `_compact_artifact_message_content()`（line 1614），赋值 `messages=`（line 1629）。
4. `run_input.py:1935-1940` — `build()` ordinary path 拆包 `*compact.messages`（line 1937）。
5. `run_input.py:2518-2530` — `build_run_input_material_blocks()` 迭代 `compact.messages`（line 2519），将 compact artifact messages 转为 fallback material blocks。

**Plan fix 验证**：

- 五格 matrix（6.4 节表格）：`None/None` no-compact、equal non-None 正常、compact-only（compact 非 None + memory None）、memory-only（compact None + memory 非 None）、两个 non-None mismatch。五种情况全部覆盖。
- 后三类复用 `MemoryProjectionRepairRequired(reason=SNAPSHOT_DAMAGED)`。现有 repair caller 在 `run_input.py:1078-1149` 的 `_load_memory_snapshot_tx()` 中已使用相同模式：`required_event_sequence` 从 `_required_memory_event_sequence(current_facts)` 获取，`MemoryRepairRequest` 携带 `policy_digest`。Plan 的 6.4 节明确定义了 "required sequence 来自 `_required_memory_event_sequence(current_facts)`，policy digest 来自 production memory view"，与既有 caller 一致。
- 点名删除：provider 内 `_compact_artifact_message_content()` 调用、`SystemMessage` 构造、`messages=` 赋值；`CompactArtifactView.messages` 删除且不保留空 tuple；builder 的 `*compact.messages` 删除。

**发现：两个 compact.messages 使用点，plan exact changes 只显式点名一个**：

- Plan S2 exact changes item 5 只提到 `build()` 的 `*compact.messages` 删除（line 1937），未显式点名 `build_run_input_material_blocks()` 的 `compact.messages` 迭代（line 2519）。
- 不过 plan 9 节的 source scan `rg -n 'compact\.messages|messages=.*CompactArtifactView|_compact_artifact_message_content' dayu/host/run_input.py` 会同时命中两处，因此 implementation agent 不会遗漏。
- **严重程度**: 低。Source scan 覆盖，不影响 code-generation-readiness。参见 P3C-RR-DS-02。

**发现：`CompactPipelineCompactArtifactView` Protocol 结构类型断裂**：

- `compact_pipeline.py:147-184` 定义 `CompactPipelineCompactArtifactView` Protocol，声明 `messages` 属性。
- `run_input.CompactArtifactView`（line 424）当前通过结构子类型满足该 Protocol（有同名 `messages` 字段）。
- `_DurableProtectedRecentRawTailProvider.load_ordinary_raw_tail()`（`run_input.py:1392-1425`）参数类型为 `compact: CompactPipelineCompactArtifactView`。
- `RunInputBuilder.build()` 在 line 1920-1925 将 `compact`（`CompactArtifactView`）传给该方法。
- 若 `CompactArtifactView` 删除 `messages`，pyright 会在 line 1920 报类型错误：`CompactArtifactView` 不再满足 `CompactPipelineCompactArtifactView` Protocol。
- Plan 未提及需要同步更新该 Protocol 或增加适配层。
- **严重程度**: 中。会导致 pyright 构建失败（stop condition）。参见 P3C-RR-DS-01。

**Verdict**: CLOSED with caveat P3C-RR-DS-01（需在 S2 同步处理 Protocol 更新）和 P3C-RR-DS-02（minor，source scan 可覆盖）。

### P3-C-PF-03 — RunInputMaterialBlock evidence contract / invariant / shared renderer

- **Plan 位置**: 6.6 节（Accepted evidence typed LLM material 与唯一 renderer）
- **声称 fix**: 完整 typed evidence contract、evidence/non-evidence invariant、shared-renderer text equality、同 slice 原子迁移

**直接代码证据**：

1. `compact_material.py:199-330` — `RunInputMaterialBlock` 当前携带 `readable_tool_name: str | None`、`readable_query_text: str | None`、`readable_source_text: str | None` 三个 loose readable fields，以及 `accepted_evidence_id`、`tool_result_event_ref`、`tool_call_event_ref` 等 evidence identity refs。
2. `compact_material.py:2278-2296` — evidence block 构造时 `text=projection.result_text`，不等于 shared renderer 输出。
3. `compact_pipeline.py:1101` 和 `run_input.py:2998` — 两个同名私有 `_accepted_tool_evidence_content()` 分别从 block 读取 loose fields 重建文本。
4. `memory.py:1733` — `_accepted_evidence_readable_text()` 第三种格式。

**Plan fix 验证**：

- 6.6 节完整 evidence contract：`accepted_evidence_id`、`tool_result_event_ref`、`tool_call_event_ref`、`payload_refs`、`artifact_refs`、`source_locator_refs`、`accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None`。删除三个 loose readable fields。
- Evidence/non-evidence invariant：
  - Evidence block：`section is EVIDENCE_MATERIAL AND kind is ACCEPTED_TOOL_EVIDENCE`，三个 identity ref 和 `accepted_tool_evidence` 非空，provenance 至少一条，`text == render_accepted_tool_evidence_for_llm(accepted_tool_evidence)`。
  - Non-evidence block：所有 evidence fields 为 None，evidence provenance 为空。
- Shared renderer 边界清晰：
  - `render_accepted_tool_evidence_for_llm()` 输出固定四行中文文本（工具名称/查询语义/业务来源/工具结果）。
  - `block.text` 等于该 renderer 输出。
  - `CompactEvidenceBlock.llm_json()` 产生不同 JSON 格式（含 label/kind/tool_name/query_text/result_text/source_text），供 LLM 消费。
  - `EvidenceReadableItemVNext` 的字段（tool_name/query_text/response_text/source_note）从 `AcceptedToolEvidenceLLMMaterial` 字段直接构造，不反解析 block.text。
- Plan 明确禁止 "把四行 renderer 全文误当 response_text"。
- 原子迁移顺序：先定义 typed material/renderer → 迁移 block/event 全部 producer/consumer → 最后删除三个 loose fields。不允许可 import 的 dual-field contract 跨出 S3。
- Provenance 语义澄清：non-evidence block 的 evidence-specific fields 必须为空，但通用 provenance fields（`canonical_source_refs`、`event_sequence`、`turn_group_id`）保持原样 — 这符合当前语义，没有过度约束。

**Verdict**: CLOSED。Evidence/non-evidence invariant 具体、不冲突、可验证。Shared renderer 与 CompactEvidenceBlock result_text 边界清楚。

### P3-C-PF-04 — two-message count 推导与 owner 常量

- **Plan 位置**: 6.5 节（Post-compact budget API）
- **声称 fix**: 固定 count `2` 推导为 one-system envelope + current-input user message，保留 owner 常量，禁止 caller override，加 drift test

**直接代码证据**：

1. `compaction_operation.py:69` — `_POST_COMPACT_BASE_MESSAGE_COUNT = 2`，用于 `_budget_after_compact_candidate()` line 1493。
2. `llm_compaction.py:96` — `_POST_COMPACT_BASE_MESSAGE_COUNT = 2`，同名同值但属于 proposal-budget 语义。

**Plan fix 验证**：

- `2` 的推导：design 第 23 节 one-system-message contract — 所有 system-scoped compact/memory 材料合并为一条 system envelope（1） + 当前 `USER_INPUT_ACCEPTED` user message（1） = 2。
- Owner: `context_budget.POST_COMPACT_BASE_MESSAGE_COUNT` 拥有 ordinary post-compact dispatch 估算。
- 禁止 caller override — plan 明确 "函数不接受 caller override；允许 caller 覆盖会让相同 ordinary message contract 得出不同预算"。
- Drift test: 断言 one-system envelope + current-input user 两消息形态与 overhead；message contract 改变时迫使 owner 同步修改。
- 两个同名常量分开 owner：
  - `compaction_operation._POST_COMPACT_BASE_MESSAGE_COUNT` → 迁入 `context_budget.POST_COMPACT_BASE_MESSAGE_COUNT`（P3-C scope）。
  - `llm_compaction._POST_COMPACT_BASE_MESSAGE_COUNT` → 保持独立，属于 proposal-budget 语义，P3-C 不移动、不合并、不 re-export。
  - Plan 9 节 source assertion 明确检查：`compaction_operation.py` 不再定义该常量，`context_budget.py` 只定义 ordinary post-compact owner 常量，`llm_compaction.py` 私有常量保持独立且不得 import/re-export 前者。

**Verdict**: CLOSED。推导有据、owner 分离正确、无混淆风险。

### P3-C-PF-05 — 命名测试覆盖 no-compact / equal / 三种 mismatch

- **Plan 位置**: 7.1、S2、9 节
- **声称 fix**: 五个命名 tests，进入 focused 和 aggregate validation

**直接代码证据**：

- 当前 `tests/host/test_run_input_builder.py` 不存在这些测试名称。

**Plan fix 验证**：

- 9 节列出五个精确测试名：
  1. `test_no_compact_event_and_no_memory_compaction_ref_builds_without_repair`
  2. `test_matching_compact_and_memory_compaction_event_refs_build_once`
  3. `test_compact_event_without_memory_compaction_ref_requires_repair`
  4. `test_memory_compaction_ref_without_compact_event_requires_repair`
  5. `test_mismatched_compact_and_memory_compaction_event_refs_require_repair`
- 后三个断言 exception type、`MemoryRepairReason.SNAPSHOT_DAMAGED`、且 `RunInputBuilder` 未读取 protected raw tail / 未记录 manifest / 未 dispatch。
- Equal case 断言 `DurableCompactArtifactProvider` 不生成 message、ordinary system envelope 中五类 compact 业务内容只来自 memory 且各出现一次。
- Focused command 单跑 `tests/host/test_run_input_builder.py`；aggregate matrix 再次包含该文件。
- 名称本身区分五种情况，禁止用参数化 "mismatch" 掩盖缺失 case。

**Verdict**: CLOSED。测试覆盖完整且可独立验证。

### P3-C-PF-06 — 删除 compact_material.py 的 envelope 二次解析与 str(exc)

- **Plan 位置**: S3 Exact changes、9 节 source scan
- **声称 fix**: 删除 `accepted_evidence_envelope_from_payload()` 调用与 `str(exc)` catch；evidence block 只消费 `AcceptedToolResultProjection.llm_material`

**直接代码证据**：

1. `compact_material.py:57` — `from dayu.host.evidence import accepted_evidence_envelope_from_payload`
2. `compact_material.py:55` — `from dayu.host.evidence import ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH`
3. `compact_material.py:2259-2266` — 调用 `accepted_evidence_envelope_from_payload()`，catch `ValueError`，以 `str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` 做控制流分支。

**Plan fix 验证**：

- S3 Exact changes item 3 明确点名删除该调用与 catch block。
- Evidence block 改为只从 `AcceptedToolResultProjection` 的 typed LLM material 构造。
- Producer mismatch 只由 projection owner 捕获 typed exception 并转 `HostDurableError`。
- Plan 9 节 source scan：`rg -n 'accepted_evidence_envelope_from_payload|str\(exc\)' dayu/host/compact_material.py` 预期零匹配。
- Plan 9 节 source scan：`rg -n 'str\(exc\).*ACCEPTED_EVIDENCE|ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH' dayu/host` 预期零匹配（全 Host）。

**Verdict**: CLOSED。删除路径明确，source scan 可验证。

## Residual observations 吸收验证

### Residual 1: `_snapshot_*` string-wire helpers 与 `_PREVIOUS_*` 常量删除

- Plan S2 exact changes item 3 点名删除：`_parse_previous_forward_intent_text()`、`_parse_previous_reference_continuity_text()`、`_previous_compacted_*_vnext()`、`_previous_blocks_from_snapshot()`、五个 `_snapshot_*_texts()` 及其 `_PREVIOUS_*` 字符串常量。
- 当前代码确认这些函数/常量全部存在（`compact_material.py:100-105, 2517-2679, 3229-3415`）。
- Plan 明确 "迁移后无消费者的 `_snapshot_*_texts()` 在同一 slice 删除，不留 dead serializer"。
- **Verdict**: 正确吸收。

### Residual 2: `compact_material.py` 和 `run_input.py` 的 candidate 字段常量/parser 删除

- Plan S2 exact changes item 4 点名删除 `compact_material.py` 的五个 `_candidate_*` mapping parsers 和对应字段常量。
- Plan S2 exact changes item 6 点名删除 `run_input.py` 的 `_vnext_compact_candidate_semantic_lines()`、nested candidate mapping/list parsers 和 `_PAYLOAD_FIELD_*` 常量。
- 当前代码确认这些函数全部存在（`compact_material.py:2332-2452, 1934-1990` 和 `run_input.py:3414-3477, 3401-3411`）。
- Plan 明确 artifact/ref/governance 字段常量保留在各自 owner，不做无关横扫。
- **Verdict**: 正确吸收。

### Residual 3: 两个 `_POST_COMPACT_BASE_MESSAGE_COUNT` 分开 owner

- Plan 6.5 节明确区分：`context_budget.POST_COMPACT_BASE_MESSAGE_COUNT`（ordinary post-compact dispatch）vs `llm_compaction._POST_COMPACT_BASE_MESSAGE_COUNT`（proposal-budget）。
- Plan 9 节 source assertion 明确要求 `llm_compaction.py` 私有常量保持独立且不得 import/re-export。
- **Verdict**: 正确吸收。

## 专项攻击向量结果

### 攻击 1: pair invariant 能否保留完整 anchor children/ordinal 且不把 leaf input error 误归 durable corruption

- **Pair projector 输出**: Plan 6.3 invariant 4 要求 typed anchor "保留完整 anchor_title、全部 anchor_items 及每个 ordinal"；block 文本由同一 pair projector 从完整 typed anchor 产生。"不能再从 text 反解析 children" 直接禁止了当前 `_previous_compacted_answer_anchors_vnext()` 的 splitlines + ordinal=None 路径。
- **Failure 分类**: Leaf constructor → `TypeError`/`ValueError`。已持久化 pair → `HostDurableError`。判断标准是 input source（构造时 vs 从 CONTEXT_COMPACTED 读出），不是错误类型。由于 CONTEXT_COMPACTED 被 digest 校验，pair invariant 违反确实表示 semantic projection 损坏。区分正确。
- **边界 case**: 若 accepted candidate 本身是 valid（通过 proposal parser 和 accept barrier），但 pair projector 有 bug 导致 blocks/readable_view 不一致，pack validation `__post_init__` 会抛 `HostDurableError`。这在开发阶段应被发现（projector 的单元测试），在 production 中不会发生。合理。
- **No false attribution found**.

### 攻击 2: event ref 五格 matrix 与现有 repair caller 是否一致

- 现有 repair caller（`run_input.py:1078-1149`）：`_load_memory_snapshot_tx()` → `MemoryProjectionRepairRequired(reason=SNAPSHOT_DAMAGED, repair_request=MemoryRepairRequest(...))`；`required_event_sequence` 从 `_required_memory_event_sequence(current_facts)` 获取；`policy_digest` 从 `self._policy_digest` 获取。
- Plan 6.4 新增 pair check: 同样抛 `MemoryProjectionRepairRequired(reason=SNAPSHOT_DAMAGED)`，"required sequence 来自 `_required_memory_event_sequence(current_facts)`，policy digest 来自 production memory view"。
- 两者使用相同的异常类型、相同的 reason enum、相同的 `required_event_sequence` 来源、相同的 repair 流程（由既有 required catch-up/rebuild/inline-repair caller 处理）。
- **Consistent**.

### 攻击 3: RunInputMaterialBlock evidence/non-evidence invariant 是否与当前 provenance 语义冲突或过严

- Evidence block 要求所有 evidence-specific fields 非空 + provenance 非空。Non-evidence block 要求 evidence-specific fields 为 None + evidence provenance 为空。
- 当前 `run_input_material_block()` factory 对 non-evidence block 默认 evidence fields 为 None/empty。Plan 将此从 default 提升为 invariant。
- 通用 provenance fields（`canonical_source_refs`、`event_sequence`、`turn_group_id`）仍可用于所有 block 类型。Plan 未将它们归零。
- 验证当前无 production path 创建 partial-evidence block：所有 call site 要么全设 evidence fields（如 line 2279-2295），要么全不设（如 line 1937-1994 的 trace/previous/answer blocks）。
- **No conflict. Not too strict**.

### 攻击 4: text 等于共享 renderer 与 CompactEvidenceBlock result_text 边界是否清楚

- Shared renderer `render_accepted_tool_evidence_for_llm()` 输出四行中文文本：
  ```
  工具名称：<tool_name>
  查询语义：<query_text>
  业务来源：<source_text>
  工具结果：<result_text>
  ```
- `RunInputMaterialBlock.text` 必须等于该 renderer 输出（用于 RunInput system section）。
- `CompactEvidenceBlock` 从 typed material 字段构造，其 `llm_json()` 输出 JSON 格式（label/kind/tool_name/query_text/result_text/source_text），供 LLM 消费。`raw_result_text` 字段保持 `result_text` 值（非四行中文）。
- `EvidenceReadableItemVNext` 的 `response_text` 字段映射到 `result_text`（非四行中文）。
- Plan 明确禁止 "把四行 renderer 全文误当 response_text"。
- **边界清楚**.

### 攻击 5: two-message count 与 llm_compaction 同名常量是否正确分 owner

- P3-C 作用域：`compaction_operation._POST_COMPACT_BASE_MESSAGE_COUNT` → `context_budget.POST_COMPACT_BASE_MESSAGE_COUNT`（ordinary dispatch overhead）。
- P3-C 不动：`llm_compaction._POST_COMPACT_BASE_MESSAGE_COUNT`（proposal-budget 语义，当前仅定义未使用）。
- Plan 9 节 source assertion 确保 `compaction_operation.py` 不再定义该常量、`llm_compaction.py` 私有常量保持独立且不得 import/re-export 前者。
- **Owner 分离正确**.

### 攻击 6: 具体删除路径 / source scan / test mapping 是否完整

- **删除路径**:
  - `compact_material.py`: 五个 `_candidate_*_texts()`、五个 `_snapshot_*_texts()`、`_previous_blocks_from_snapshot()`、`_parse_previous_*_text()`、`_previous_compacted_*_vnext()`、`_previous_compacted_view_vnext()`、`_PREVIOUS_*` 常量、candidate 字段常量、`accepted_evidence_envelope_from_payload()` import/call、`str(exc)` catch block。Plan 点名覆盖。
  - `run_input.py`: `_compact_artifact_message_content()`、`_vnext_compact_candidate_semantic_lines()`、nested parsers、candidate 字段常量、`*compact.messages`、`CompactArtifactView.messages`。Plan 点名覆盖。
  - `compaction_operation.py`: `_budget_after_compact_candidate()`、`_candidate_text_fragments()`、`_POST_COMPACT_BASE_MESSAGE_COUNT`。Plan 点名覆盖。
- **Source scans**: Plan 9 节 8 个 `rg` 命令覆盖所有删除目标。额外 source assertion 覆盖常量 owner 和 `tool_trace.py` diff。
- **Test mapping**: Five named tests → `tests/host/test_run_input_builder.py`；tier2/tier3 pair tests → `tests/host/test_compact_material.py` / `test_compact_pipeline.py`；evidence invariant tests → S3 focused tests；budget estimator tests → `tests/host/test_context_budget.py` / `test_compaction_operation.py`。Plan 全部指定。
- **Coverage gaps**: P3C-RR-DS-02（见下）— `build_run_input_material_blocks()` 的 `compact.messages` 使用未被 plan exact changes 显式点名，但 source scan 覆盖。

### 攻击 7: plan-fix 新引入的 material finding

见下节。

## 新 material findings（plan-fix 引入）

### P3C-RR-DS-01 — CompactPipelineCompactArtifactView Protocol 结构类型断裂

- **位置**: Plan 6.4 节、S2 exact changes item 5；`compact_pipeline.py:147-184`；`run_input.py:1920-1925, 1392-1425`
- **问题类型**: 架构边界 / 不可直接实施
- **当前写法**: Plan 从 `run_input.CompactArtifactView` 删除 `messages`，未提及 `compact_pipeline.CompactPipelineCompactArtifactView` Protocol 的 `messages` 属性需要同步更新
- **反例/失败场景**:
  1. `run_input.CompactArtifactView` 当前通过结构子类型满足 `CompactPipelineCompactArtifactView` Protocol（都定义了 `messages`、`compact_artifact_ref`、`compact_artifact_digest`、`represented_evidence_refs`）。
  2. `_DurableProtectedRecentRawTailProvider.load_ordinary_raw_tail()` 参数类型为 `compact: CompactPipelineCompactArtifactView`（`run_input.py:1397`）。
  3. `RunInputBuilder.build()` 在 line 1920-1925 将 `compact`（`CompactArtifactView`）传给该方法。
  4. 若 `CompactArtifactView` 删除 `messages`，pyright 在 line 1920 报类型错误：`CompactArtifactView` 不再满足 `CompactPipelineCompactArtifactView` Protocol 的 `messages` 成员要求。
- **为什么有问题**: 违反 plan 自身 stop condition "pyright 出现新增/扩散错误"。虽然 `_DurableProtectedRecentRawTailProvider` 实际只访问 `compact.compact_artifact_ref`（line 1410），不读取 `compact.messages`，但 pyright 的结构类型检查不关心运行时行为。
- **直接证据**:
  - `compact_pipeline.py:147-184` — Protocol 声明 `messages` 属性
  - `run_input.py:424-437` — `CompactArtifactView` 当前有 `messages: tuple[AgentMessage, ...]`
  - `run_input.py:1920-1925` — `compact` 被传参给 `CompactPipelineProtectedRawTailProvider.load_ordinary_raw_tail()`，其签名要求 `compact: CompactPipelineCompactArtifactView`
- **影响**: pyright 构建失败 → S2 stop condition 触发 → implementation 阻塞
- **建议改法和验证点**:
  1. 从 `CompactPipelineCompactArtifactView` Protocol 中删除 `messages` 属性（无消费者通过此 Protocol 读取 `compact.messages`），或
  2. 在 plan S2 exact changes 中显式说明该 Protocol 的更新。
  3. 验证：pyright 全量通过，`git diff -- dayu/host/compact_pipeline.py` 只包含 Protocol `messages` 删除。
- **修复风险**: 低（仅删除 Protocol 中无消费者使用的属性声明）
- **严重程度**: 中

### P3C-RR-DS-02 — build_run_input_material_blocks() 的 compact.messages 未在 exact changes 显式点名

- **位置**: Plan S2 exact changes item 5；`run_input.py:2485-2530`
- **问题类型**: 不可直接实施（minor）
- **当前写法**: Plan S2 exact changes item 5 点名删除 `build()` 的 `*compact.messages`，但 `build_run_input_material_blocks()` 函数同样有 `for index, message in enumerate(compact.messages):`（line 2519）需要同步删除。
- **反例/失败场景**: Implementation agent 按 exact changes 逐项执行，修复 `build()` 后遗漏 line 2519 的 `compact.messages` 迭代，导致 AttributeError。
- **为什么有问题**: 虽然 plan 9 节 source scan `rg -n 'compact\.messages|...' dayu/host/run_input.py` 会捕获此处，但 exact changes 未显式点名可能让 implementation agent 在 source scan 阶段才被动发现，增加返工。
- **直接证据**: `run_input.py:2518-2530` — `build_run_input_material_blocks()` 迭代 `compact.messages`
- **影响**: 实施 Agent 返工 / source scan 不通过
- **建议改法和验证点**: S2 exact changes item 5 增加一句："`build_run_input_material_blocks()` 中 `compact.messages` 迭代同步删除，其 loop body 整体移除"。
- **修复风险**: 低（纯 plan text 澄清）
- **严重程度**: 低

### P3C-RR-DS-03 — CompactEvidenceBlock 字段从 typed material 构造时的命名映射不明确

- **位置**: Plan 6.6 节 "consumer 规则" 段；`compaction.py:443-533`
- **问题类型**: 不可直接实施（minor）
- **当前写法**: Plan 说 `CompactEvidenceBlock` / `EvidenceReadableItemVNext` 从 `accepted_tool_evidence.tool_name/query_text/source_text/result_text` 构造，但未显式映射：
  - `CompactEvidenceBlock.readable_tool_name` ← `material.tool_name`
  - `CompactEvidenceBlock.readable_query_text` ← `material.query_text`
  - `CompactEvidenceBlock.raw_result_text` ← `material.result_text`（命名不匹配：`raw_result_text` vs `result_text`）
  - `CompactEvidenceBlock.readable_source_text` ← `material.source_text`
  - `EvidenceReadableItemVNext.response_text` ← `material.result_text`（命名不匹配：`response_text` vs `result_text`）
- **反例/失败场景**: Implementation agent 可能误以为需要重命名 `CompactEvidenceBlock.raw_result_text` → `result_text` 或 `EvidenceReadableItemVNext.response_text` → `result_text`，导致不必要的字段重命名和级联修改。
- **为什么有问题**: Plan 文本的 "从 ... 构造" 暗示值来源，但字段名不匹配可能被误解为需要改名。
- **直接证据**: `compaction.py:459` — `raw_result_text: str`；`compaction.py:969` — `response_text: str`；Plan 6.6 — `accepted_tool_evidence.tool_name/query_text/source_text/result_text`
- **影响**: Implementation agent 做不必要的字段重命名
- **建议改法和验证点**: Plan 6.6 增加显式映射表或注释说明 "CompactEvidenceBlock 字段名不变，仅值来源改为 typed material 字段"。
- **修复风险**: 低（纯 plan text 澄清）
- **严重程度**: 低

## Architecture boundary review

- Plan 严格遵守 `UI → Service → Host → Engine` 分层。所有修改在 Host 层内。
- `compact_payload.py` 作为唯一 persisted compact semantic read contract；memory/compact material/run input 只消费 typed projection。
- `context_budget.py` 接收纯文本参数而非 `ConversationCompactOutputVNext`，避免反向依赖。
- `AcceptedToolResultProjection` 提供 typed LLM material；renderer 只拥有最终文本格式；Tool Trace 保留自己的 display caps 不受影响。
- `llm_compaction.py` 的 proposal-budget 常量与 `context_budget.py` 的 ordinary dispatch 常量分开 owner，不 merge。
- P3C-RR-DS-01 暴露了一个边界问题：`CompactArtifactView` 与 `CompactPipelineCompactArtifactView` Protocol 之间的隐式结构类型依赖未被 plan 显式处理。

## Best-practice review

- 单一 typed read contract（`ContextCompactedSemanticPayload`）消除多套独立 parser — 最佳实践。
- 唯一 LLM renderer（`render_accepted_tool_evidence_for_llm`）消除三套 private renderer — 最佳实践。
- Typed enum 在 read boundary 一次构造，所有消费者只收 enum — 最佳实践。
- Pure function budget estimator 独立可测试 — 最佳实践。
- 异常改用 typed exception 替代字符串 protocol — 最佳实践。
- Fail closed：非法 enum、digest mismatch、pair invariant violation 全部拒绝，不写 unknown — 最佳实践。

## Optimal-solution review

- 三个 slice 按 producer-validator-persistence-projection-consumer 闭环拆分，不按文件机械分割 — 合理。
- S1 → S2 → S3 的依赖链正确：S1 建立 typed compact contract → S2 在其上关闭 previous view/ordinary input/budget → S3 独立关闭 evidence contract。
- 不引入 builder/factory/registry/callback/profile/query object — 符合项目 "不过度设计" 原则。

## Overengineering review

- 只新增两个窄 typed value（`ContextCompactedSemanticPayload`、`AcceptedToolEvidenceLLMMaterial`）和一个专用异常。无 God dataclass/builder。
- 没有为 future provider tokenizer、retrieval、schema upgrade 预留抽象。
- 没有全局 trace truncation、全局 payload accessor 重构。
- Plan 的 non-goals 明确拒绝了大量常见的过度设计方向。

## Overcoupling review

- `compact_payload.py` 不承担 context_events 的治理 metadata — 职责分离明确。
- Evidence projector 拥有事实，renderer 只拥有最终文本 — 没有过度耦合。
- Tool Trace 保留自己的 display policy，不与 shared renderer 耦合。
- P3C-RR-DS-01 暴露了 `CompactArtifactView` 与 compact pipeline Protocol 之间的隐式耦合点，但耦合方向是从 pipeline Protocol 依赖 artifact view，而非反向。

## Final verdict

- **PF-01**: CLOSED
- **PF-02**: CLOSED with caveats（P3C-RR-DS-01 中, P3C-RR-DS-02 低）
- **PF-03**: CLOSED
- **PF-04**: CLOSED
- **PF-05**: CLOSED
- **PF-06**: CLOSED
- **Residual observations**: 三个全部正确吸收
- **New material findings**: 3 个（1 medium + 2 low）

**Overall plan review conclusion**: `pass-with-risks`

Plan 已达到 code-generation-ready 水平，三个 slice 的 contract/API/behavior matrix/test mapping/source scan/stop condition 均充分具体。P3C-RR-DS-01 是一个 real issue（pyright 会失败），但修复简单（删除 Protocol 中无消费者使用的 `messages` 属性声明）。P3C-RR-DS-02 和 P3C-RR-DS-03 是 minor clarifications，不影响 implementation 正确性。

建议 controller 接受 P3C-RR-DS-01 作为 plan fix 的补充项（在 S2 实现前补充到 plan 中），然后推进 implementation。P3C-RR-DS-02 和 P3C-RR-DS-03 可在 implementation 中自然处理，不阻塞 gate。

## Findings summary

| ID | Severity | Location | Root cause | Owner boundary |
|---|---|---|---|---|
| P3C-RR-DS-01 | 中 | Plan 6.4 + `compact_pipeline.py:147-184` | `CompactArtifactView` 删除 `messages` 后不再满足 `CompactPipelineCompactArtifactView` Protocol 结构类型 | `compact_pipeline.py` 的 Protocol 定义需同步更新 |
| P3C-RR-DS-02 | 低 | Plan S2 exact changes + `run_input.py:2519` | `build_run_input_material_blocks()` 的 `compact.messages` 迭代未在 exact changes 中显式点名 | Plan text 补充 |
| P3C-RR-DS-03 | 低 | Plan 6.6 + `compaction.py:443-533, 955-998` | `CompactEvidenceBlock.raw_result_text` 和 `EvidenceReadableItemVNext.response_text` 与 typed material `result_text` 字段名不匹配 | Plan text 补充显式映射 |

## Open questions

无。

## Residual risks

- P3C-RR-DS-01 若不在 implementation 前修复，pyright 会在 S2 构建失败 → 触发 plan stop condition → 需回 controller 裁决。建议 controller 在推进 implementation 前接受此修复。
- P3C-RR-DS-02 由 source scan 兜底，implementation agent 不会遗漏但可能返工。
- S1/S2/S3 的 stop conditions（plan 13 节）覆盖了主要的实施风险。未发现 plan text 未覆盖的 residual risk。

## Suggested next steps

1. Controller 审阅 P3C-RR-DS-01，决定是否作为 plan fix 补充项。
2. 若接受，在 plan S2 allowed files 中明确 `compact_pipeline.py` 需同步删除 `CompactPipelineCompactArtifactView.messages` Protocol 属性。
3. Plan text 补充 P3C-RR-DS-02（`build_run_input_material_blocks` 的删除）和 P3C-RR-DS-03（字段映射表）。
4. 推进 implementation。

---

Artifact path: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-ds.md`
