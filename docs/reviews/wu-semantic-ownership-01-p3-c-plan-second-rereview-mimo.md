# WU-SEMANTIC-OWNERSHIP-01 P3-C Second Independent Plan Re-Review — AgentMiMo

## Reviewed target and scope

- **Plan artifact**: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`（second-fix 后版本）
- **Second-fix artifact**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-fix-codex.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-controller-adjudication.md`
- **First-round re-reviews**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-mimo.md`、`docs/reviews/wu-semantic-ownership-01-p3-c-plan-rereview-ds.md`
- **Design sources**: `docs/host/design.md` §23-25、`docs/engine/design.md` §1,4,14,15
- **Scope**: 逐项用直接代码证据验证 `P3-C-RR-PF-01` 至 `P3-C-RR-PF-05` 与 controller coverage follow-up 是否在 plan 中真正闭合；发现任何新 material finding
- **Gate**: second plan re-review
- **Review date**: 2026-07-10
- **Reviewer**: AgentMiMo
- **Code evidence**: current `HEAD` (8787714d) direct reads of all affected production modules

## Review Posture

本 re-review 不信任 second-fix artifact 的自报状态。逐项用当前代码直接证据验证每个
plan fix 是否在 plan 文本中真正闭合。对五个重点攻击面逐一压测，并扫描新 material finding。

## 五项 Closure 逐项验证

### P3-C-RR-PF-01 — Protocol messages 删除后 structural subtype 一致性

**Controller 裁决**：从 `CompactPipelineCompactArtifactView` 删除 `messages`，保留
protected-raw-tail 实际消费的 `compact_artifact_ref` / `compact_artifact_digest`；
`represented_evidence_refs` 留在 concrete view 供直接消费者，不进入 protocol。
`CompactArtifactView` 保持 structural subtype。

**代码直接验证**：

1. `compact_pipeline.py:147-184` — `CompactPipelineCompactArtifactView` 声明四个
   property：`messages`、`compact_artifact_ref`、`compact_artifact_digest`、
   `represented_evidence_refs`。
2. Protocol 消费者分析（全部在 `run_input.py`）：
   - `_NoopProtectedRecentRawTailProvider.load_ordinary_raw_tail`（line 1344）：不访问
     任何 property，参数立即 `del`。
   - `_DurableProtectedRecentRawTailProvider.load_ordinary_raw_tail`（line 1397）：只读
     `compact.compact_artifact_ref`（line 1410）。
   - `_DurableProtectedRecentRawTailProvider._load_protected_recent_raw_tail_tx`（line
     1433）：不直接访问 compact property，转发给 validator。
   - `_validate_loaded_compact_view_matches_event`（line 3317）：读
     `compact.compact_artifact_ref`（line 3330）和
     `compact.compact_artifact_digest`（line 3332）。
   - **`messages` 零消费者。`represented_evidence_refs` 通过该 Protocol 零消费者。**
3. `run_input.py:424-437` — `CompactArtifactView` 当前有 `messages`（line 434）、
   `compact_artifact_ref`（line 435）、`compact_artifact_digest`（line 436）、
   `represented_evidence_refs`（line 437）。删除 `messages` 后仍满足窄 protocol 的
   `compact_artifact_ref` + `compact_artifact_digest` 两个 property。
4. Plan §6.4 与 S2 item 5 明确：protocol 只保留 ref/digest 两个 provenance property；
   concrete view 保持 structural subtype，允许额外携带 `compaction_event_ref`、
   `represented_evidence_refs`；禁止 adapter/facade。

**Verdict: PASS**

Protocol 的 `messages` 零消费者；`represented_evidence_refs` 通过 protocol 零消费者。
删除后 concrete view 仍以 structural subtyping 满足窄 protocol。Plan 文本精确覆盖。

### P3-C-RR-PF-02 — build_run_input_material_blocks() compact loop 完整删除

**Controller 裁决**：显式删除整个 `build_run_input_material_blocks()` 中 `compact.messages`
loop；不等待 source scan 补漏。说明 compact provenance 如何在不创建 material block 的情况下
继续可用。

**代码直接验证**：

1. `run_input.py:2485-2492` — 函数签名包含 `compact: CompactArtifactView` 参数。
2. `run_input.py:2518-2530` — 完整 loop：
   - line 2518: `compact_source_ref = _compact_material_source_ref(compact)`
   - line 2519-2530: `for index, message in enumerate(compact.messages):` → 构造
     `block_id="compact:{index}"` / `SESSION_SUMMARY` material block
3. `run_input.py:1951` — call site 1: `RunInputBuilder.build()` fallback path
4. `run_input.py:2030` — call site 2: `RunInputBuilder.build_material_blocks()`
5. Plan §6.4 与 S2 item 6 明确："从 `compact_source_ref = ...` 开始、遍历
   `compact.messages` 并构造 `block_id="compact:*"` / `SESSION_SUMMARY` block 的整个 loop
   必须删除"，"同步从该函数签名与 call sites 删除失去 material 职责的 `compact` 参数"。
6. Plan 说明 provenance 路径："compact provenance 仍由 `RunInputBuilder` 持有的 typed
   `CompactArtifactView` 供 event-ref equality、protected raw-tail selection、accepted
   evidence represented-ref 去重、runner-call manifest 与 audit 使用"。

**Verdict: PASS**

Loop 起止、函数签名、两个 call sites、provenance 保留路径全部在 plan 中精确覆盖。

### P3-C-RR-PF-03 — Typed evidence no-rename mapping 准确性

**Controller 裁决**：增加 exact no-rename mapping table；`block.text` 保持 shared
four-field renderer 输出，永不作为 component field 的 value source。

**代码直接验证**：

1. `compaction.py:456-460` — `CompactEvidenceBlock` 字段：
   `readable_tool_name`、`readable_query_text`、`raw_result_text`、
   `readable_source_text`。
2. `compaction.py:966-970` — `EvidenceReadableItemVNext` 字段：
   `tool_name`、`query_text`、`response_text`、`source_note`。
3. 当前 `compact_material.py:2753` `_pack_evidence_blocks()` 赋值：
   `raw_result_text = block.text`。当前 `block.text` 是 `projection.result_text`（纯结果
   文本）。Plan 将 `block.text` 变为完整四字段 renderer 输出，因此该赋值必须改为
   `raw_result_text = material.result_text`。
4. 当前 `compact_material.py:3222` `_evidence_material_vnext()` 赋值：
   `response_text = block.raw_result_text`。值传递链正确。
5. Plan §6.6 增加的 no-rename table：

   | Target field | Typed material source |
   |---|---|
   | `CompactEvidenceBlock.readable_tool_name` | `material.tool_name` |
   | `CompactEvidenceBlock.readable_query_text` | `material.query_text` |
   | `CompactEvidenceBlock.raw_result_text` | `material.result_text` |
   | `CompactEvidenceBlock.readable_source_text` | `material.source_text` |
   | `EvidenceReadableItemVNext.response_text` | `material.result_text` |

6. 字段名不匹配（`raw_result_text` vs `result_text`、`response_text` vs
   `result_text`）被 plan 明确说明为值映射而非重命名要求。Plan 文本："target fields
   不重命名；`block.text` 只等于 shared 四字段 renderer，永不作为 component field 的
   value source 或 parse source"。

**Verdict: PASS**

No-rename mapping table 精确、完整。值传递链可追踪。字段名差异有明确说明。

### P3-C-RR-PF-04 — _previous_compacted_*_vnext source scan 覆盖

**Controller 裁决**：增加零匹配 scan 覆盖 `_previous_compacted_*_vnext` 和主
`_previous_compacted_view_vnext`。

**代码直接验证**：

1. 函数族完整清单（全部在 `compact_material.py`）：

   | 函数名 | 行号 | 调用者 |
   |---|---|---|
   | `_previous_compacted_view_vnext` | 3325 | line 601 |
   | `_previous_compacted_session_summary_vnext` | 3354 | `_previous_compacted_view_vnext` (3332) |
   | `_previous_compacted_fact_material_vnext` | 3229 | `_previous_compacted_view_vnext` (3333) |
   | `_previous_compacted_answer_anchors_vnext` | 3245 | `_previous_compacted_view_vnext` (3334) |
   | `_previous_compacted_forward_intents_vnext` | 3276 | `_previous_compacted_view_vnext` (3335) |
   | `_previous_compacted_references_vnext` | 3301 | `_previous_compacted_view_vnext` (3336) |

2. Plan §9 source scan 增加：
   ```
   rg -n 'def _previous_compacted_(view|session_summary|fact_material|answer_anchors|forward_intents|references)_vnext' dayu/host/compact_material.py
   ```
   预期零匹配。覆盖全部六个函数定义。

3. S2 completion/validation 将该 scan 作为 hard acceptance criterion。

**Verdict: PASS**

六个函数定义全部被 scan 模式覆盖。零匹配作为 hard acceptance criterion。

### P3-C-RR-PF-05 — llm_compaction 三个 dead constants 零消费确认

**Controller 裁决**：纠正 false owner attribution；`llm_compaction.py` 加入 S2 仅删除三个
dead constants；零匹配 scan 验证。

**代码直接验证**：

1. `llm_compaction.py:92-97` — 三个常量定义：
   - `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`（line 92-95）：字符串值
   - `_POST_COMPACT_BASE_MESSAGE_COUNT = 2`（line 96）
   - `_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT = 1`（line 97）
2. `rg` 全仓搜索确认三个常量均零消费者：
   - `_POST_COMPACT_SYSTEM_PROMPT_ESTIMATE`：仅定义，无消费
   - `_POST_COMPACT_TOOL_SCHEMA_OVERHEAD_COUNT`：仅定义，无消费
   - `_POST_COMPACT_BASE_MESSAGE_COUNT`：`llm_compaction.py` 中仅定义；
     `compaction_operation.py:69` 有独立同名定义并在 line 1493 消费
3. `compaction_operation.py:69,1493` — 真正的 ordinary post-compact budget 消费者。
4. Plan §9 source scan：
   ```
   rg -n '_POST_COMPACT_(SYSTEM_PROMPT_ESTIMATE|BASE_MESSAGE_COUNT|TOOL_SCHEMA_OVERHEAD_COUNT)' dayu/host/llm_compaction.py
   ```
   预期零匹配（删除后）。
5. Plan §6.5 纠正 false claim：不再把 `llm_compaction` 私有常量描述为当前
   proposal-budget owner。

**Verdict: PASS**

三个常量确认零消费。Plan 纠正了 false owner attribution。S2 仅原地删除，不移动/re-export。

### Controller Coverage Follow-up — test_llm_compaction coverage 矩阵

**Controller 裁决**：`tests/host/test_llm_compaction.py` 加入 S2 focused commands 与
aggregate matrix；`--cov=dayu.host.llm_compaction` 加入 aggregate coverage collection；
逐文件 `--fail-under=80` 验证。

**代码直接验证**：

1. `tests/host/test_llm_compaction.py` 存在（1142 行），覆盖：structural safety、secret
   redaction、constructor validation、prepared proposal input、vNext JSON parsing、prompt/schema
   alignment、parser fail-closed behavior、large arrays、label validation、derived fact
   evidence kind、enum error reporting、safety-net wrapping、async compact integration、
   non-final outcome rejection。
2. Plan §9 S2 focused validation：
   ```
   python -m pytest tests/host/test_run_input_builder.py -q
   python -m pytest tests/host/test_llm_compaction.py -q
   ```
   `test_llm_compaction.py` 已加入。
3. Plan §9 aggregate matrix 包含 `tests/host/test_llm_compaction.py`（line 813）。
4. Plan §9 aggregate coverage collection 包含 `--cov=dayu.host.llm_compaction`（line 840）。
5. Plan §9 逐文件验收包含：
   ```
   python -m coverage report --include='dayu/host/llm_compaction.py' --fail-under=80
   ```
   aggregate 数字不替代该文件 gate。

**Verdict: PASS**

`test_llm_compaction.py` 是仓库现有的直接 owner test，覆盖 parser、safe outcome、
prepared proposal input、runner call 等路径。S2 focused、aggregate、coverage collection、
逐文件 gate 全部包含。

## 新 Material Finding

### P3C-RR-MIMO-01 — `_compact_material_source_ref()` 删除后成为 dead code

- **位置**: Plan S2 item 6（`build_run_input_material_blocks()` loop 删除）；`run_input.py:3123`
  函数定义、`run_input.py:2518` 唯一调用点
- **问题类型**: 测试缺口（minor）
- **当前写法**: Plan S2 item 6 明确删除从 `compact_source_ref = ...` 开始的整个 loop，
  但未显式点名删除 `_compact_material_source_ref()` 函数定义本身。
- **反例/失败场景**: Implementation agent 删除 loop 后，`_compact_material_source_ref()`
  成为 dead code。source scan `rg -n 'compact\.messages|...' dayu/host/run_input.py` 不会
  命中该函数定义（它不包含 `compact.messages` 模式）。`rg` 对 `_compact_material_source_ref`
  的单独搜索会发现 line 2518 已删除但 line 3123 定义仍存在。
- **为什么有问题**: 不会导致功能错误，但会留下 dead code。Plan 的 source scan 不覆盖该函数
  名，implementation agent 不会在 acceptance 阶段被强制删除它。
- **直接证据**:
  - `run_input.py:2518` — `compact_source_ref = _compact_material_source_ref(compact)`
    是该函数唯一调用点
  - `run_input.py:3123` — `def _compact_material_source_ref(compact: CompactArtifactView) -> str:`
    函数定义
  - Plan §9 source scan 无覆盖 `_compact_material_source_ref` 的模式
- **影响**: Dead code 残留；不影响功能正确性
- **建议改法和验证点**: S2 item 6 增加点名删除 `_compact_material_source_ref()` 函数定义；
  或在 §9 source scan 增加 `rg -n '_compact_material_source_ref' dayu/host/run_input.py` 预期
  零匹配
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 五项特别攻击面验证

### Attack-1：Protocol 删除 messages 后 structural subtype 是否仍成立

- `CompactPipelineCompactArtifactView` 删除 `messages` 和 `represented_evidence_refs` 后，
  只保留 `compact_artifact_ref` 和 `compact_artifact_digest`。
- `CompactArtifactView` 删除 `messages` 后仍有 `compact_artifact_ref`、
  `compact_artifact_digest`、`represented_evidence_refs`、`compaction_event_ref`（plan 新增）。
- Structural subtype 成立：concrete view 拥有 protocol 要求的全部 property。
- **No issue found.**

### Attack-2：compact 参数删除后所有 call sites 是否安全

- 函数签名 `build_run_input_material_blocks(..., compact: CompactArtifactView, ...)` 删除
  `compact` 参数。
- Call site 1（line 1951）：`build_run_input_material_blocks(current_facts=..., memory=...,
  compact=compact, continuity=..., accepted_tool_evidence=...)` — 删除 `compact=compact`。
- Call site 2（line 2030）：同上模式 — 删除 `compact=compact`。
- 函数内唯一的 `compact` 使用是被删除的 loop（lines 2518-2530）。
- `__all__` 导出（line 5230）只引用函数名，不受参数变化影响。
- **No issue found.**

### Attack-3：typed evidence no-rename mapping 值传递链

- Plan mapping: `raw_result_text <- material.result_text`。
- 当前代码 `compact_material.py:2753`: `raw_result_text = block.text`。
- 当前 `block.text` = `projection.result_text`（纯结果文本）。
- Plan 将 `block.text` 改为完整四字段 renderer 输出。因此 `raw_result_text` 必须改为
  `material.result_text`（纯结果分量），而非继续取 `block.text`。
- `EvidenceReadableItemVNext.response_text` 在 `compact_material.py:3222` 取
  `block.raw_result_text`，值传递链正确。
- **No issue found.** Plan 的 no-rename table 准确描述了目标状态。

### Attack-4：_previous_compacted_*_vnext 全族覆盖

- 六个函数全部在 `compact_material.py` 定义。
- Plan S2 item 3 点名删除 `_parse_previous_forward_intent_text()`、
  `_parse_previous_reference_continuity_text()`、`_previous_compacted_*_vnext()`。
- Plan §9 source scan 新增显式函数名集合 scan，覆盖全部六个。
- **No issue found.**

### Attack-5：llm_compaction 三个常量删除影响

- 三个常量零消费者。删除不影响任何 import、测试或运行时行为。
- `tests/host/test_llm_compaction.py` 不引用这三个常量。删除后测试仍通过。
- `compaction_operation.py` 的同名常量是独立定义，不受影响。
- **No issue found.**

## Architecture Boundary Re-verification

Plan §5 的 7 个语义 owner boundary 在 second-fix 后仍然闭合：

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

Protocol 收窄后，`CompactPipelineCompactArtifactView` 只承载 protected-raw-tail 选择实际
消费的 provenance fields，不泄漏 LLM material 语义。✓

## Source Scan 完整性

§9 source scan 覆盖的模式与预期：

| 模式 | 目标文件 | 预期 | 覆盖 |
|---|---|---|---|
| `_accepted_candidate_mapping\|_vnext_compact_candidate_semantic_lines\|...` | `dayu/host` | 无匹配 | ✓ |
| `_previous_blocks_from_snapshot\|_snapshot_*\|_candidate_*` | `compact_material.py` | 无匹配 | ✓ |
| `def _previous_compacted_(view\|session_summary\|fact_material\|answer_anchors\|forward_intents\|references)_vnext` | `compact_material.py` | 无匹配 | ✓ |
| `str\(exc\).*ACCEPTED_EVIDENCE\|...` | `dayu/host` | 无匹配 | ✓ |
| `def _accepted_tool_evidence_content\|def _accepted_evidence_readable_text` | `dayu/host` | 无匹配 | ✓ |
| `_PAYLOAD_FIELD_(SESSION_SUMMARY\|...)` | memory/compact_material/run_input | 无匹配 | ✓ |
| `compact\.messages\|messages=.*CompactArtifactView\|_compact_artifact_message_content` | `run_input.py` | 无匹配 | ✓ |
| `accepted_evidence_envelope_from_payload\|str\(exc\)` | `compact_material.py` | 无匹配 | ✓ |
| `_POST_COMPACT_(SYSTEM_PROMPT_ESTIMATE\|BASE_MESSAGE_COUNT\|TOOL_SCHEMA_OVERHEAD_COUNT)` | `llm_compaction.py` | 无匹配 | ✓ |

**Minor gap**: `_compact_material_source_ref` 函数定义未被 source scan 覆盖。见
P3C-RR-MIMO-01。

## Open Questions

无。

## Residual Risks

| 风险 | 分类 | 严重程度 | 跟踪目标 |
|---|---|---|---|
| `_compact_material_source_ref()` 删除后成为 dead code | source scan 完整性 | 低 | P3-C S2 实现时删除或增加 scan |

## Plan Review Conclusion

**Verdict: PASS**

`P3-C-RR-PF-01` 至 `P3-C-RR-PF-05` 全部在 plan 文本中真正闭合，controller coverage
follow-up 已正确吸收。五个特别攻击面均通过代码直接证据验证：

1. **Protocol structural subtype**：`messages` 和 `represented_evidence_refs` 通过 protocol
   零消费者；删除后 concrete view 仍满足窄 protocol。
2. **compact loop 完整删除**：loop 起止、函数签名、两个 call sites、provenance 保留路径
   全部精确覆盖。
3. **No-rename mapping**：exact table 准确、完整；值传递链可追踪；字段名差异有明确说明。
4. **Previous helper scan**：六个函数定义全部被 scan 模式覆盖，零匹配作为 hard acceptance
   criterion。
5. **llm_compaction dead constants**：三个常量确认零消费；false owner attribution 已纠正；
   S2 仅原地删除。
6. **Coverage matrix**：`test_llm_compaction.py` 加入 focused/aggregate/逐文件 gate。

**New material findings: 1（低严重程度）**

P3C-RR-MIMO-01 是 minor dead code residue risk，不阻塞 implementation。建议 S2 实现时
删除 `_compact_material_source_ref()` 函数定义或增加 source scan 覆盖。

Plan 可以进入 implementation。

---

## Review Metadata

- **P3-C-RR-PF-01 closure**: PASS
- **P3-C-RR-PF-02 closure**: PASS
- **P3-C-RR-PF-03 closure**: PASS
- **P3-C-RR-PF-04 closure**: PASS
- **P3-C-RR-PF-05 closure**: PASS
- **Controller coverage follow-up closure**: PASS
- **New material findings**: 1（P3C-RR-MIMO-01，低严重程度）
- **Source scan completeness**: 9/10 patterns covered（1 minor gap）
- **Owner boundaries re-verified**: 7/7 闭合
- **Protocol structural subtype**: verified — `messages` + `represented_evidence_refs` 零消费者
- **Blocking questions**: 0
- **Review artifact**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-second-rereview-mimo.md`
