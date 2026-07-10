# WU-SEMANTIC-OWNERSHIP-01 P3-C Plan Review — Adversarial Deep Scan

- **Reviewed target**: `docs/host/wu-semantic-ownership-01-p3-c-context-compaction-evidence-plan.md`
- **Review scope**: P3-C Context Compaction / Evidence Plan — 3 slices, owner boundaries, contracts, tests, finding dispositions
- **Design sources of truth**: `docs/host/design.md` §23–25; `docs/engine/design.md` §1,4,14,15
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Review date**: 2026-07-10
- **Reviewer**: planreview skill (adversarial posture)
- **Code evidence**: current `HEAD` (8787714d) direct reads of all affected production modules

---

## Assumptions Tested

| # | Assumption | Verdict | Evidence |
|---|---|---|---|
| A1 | `memory.py` still uses raw `str` for `ForwardIntent.intent_type/status` and `ReferenceContinuityItem.reason` | **Confirmed** | `memory.py:617-619,428` — `intent_type: str`, `status: str`, `reason: str` |
| A2 | Three separate evidence LLM text renderers exist | **Confirmed** | `memory.py:1733` `_accepted_evidence_readable_text`, `compact_pipeline.py:1101` `_accepted_tool_evidence_content`, `run_input.py:2998` `_accepted_tool_evidence_content` |
| A3 | `run_input.py` has a second compact artifact LLM renderer | **Confirmed** | `run_input.py:3378` `_compact_artifact_message_content` → `run_input.py:3414` `_vnext_compact_candidate_semantic_lines` |
| A4 | `compact_material.py` does string round-trip parsing of intents/references | **Confirmed** | `compact_material.py:3369` `_parse_previous_forward_intent_text`, `compact_material.py:3398` `_parse_previous_reference_continuity_text` |
| A5 | Anchor children are lost in previous compacted view reconstruction | **Confirmed** | `compact_material.py:3262-3268` — creates synthetic single child `display_text=anchor_title`, discards original `anchor_items` |
| A6 | `ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH` is used as string control flow | **Confirmed** | `evidence.py:38,331` defines string constant; `accepted_result_projection.py:276` `str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH`; `compact_material.py:2264` same pattern |
| A7 | `context_events._validate_vnext_candidate_payload` only validates basic shapes, not enums | **Confirmed** | `context_events.py:516-533` — only checks list/object types, no enum construction |
| A8 | `_budget_after_compact_candidate` lives in `compaction_operation.py`, not `context_budget.py` | **Confirmed** | `compaction_operation.py:1471` — pure estimator in wrong module |
| A9 | `_candidate_text_fragments` includes diagnostics in budget | **Confirmed** | `compaction_operation.py:1516-1518` — `diagnostic.code` and `diagnostic.text` counted |
| A10 | `_optional_text` is lenient — swallows type errors as `None` | **Confirmed** | `accepted_result_projection.py:759-770` — `isinstance(value, str)` check returns `None` on non-str, doesn't fail |
| A11 | `CompactArtifactView` still has `messages` field | **Confirmed** | `run_input.py:434` — `messages: tuple[AgentMessage, ...]` |
| A12 | `MemorySnapshotView` lacks `latest_compaction_event_ref` | **Confirmed** | `run_input.py:337-358` — no such field |

All 12 assumptions verified against direct code reads. No reliance on stale review findings.

---

## Findings

### F1-未修复-中-`CompactReadableViewVNext` 与 blocks 的双投影一致性校验规格不足

- **位置**: §6.3 "Typed previous compacted view，不再 string round-trip"，§7.1 行为矩阵 "tier 2 whole-section/item degrade"
- **问题类型**: 契约缺失
- **当前写法**: "CompactMaterialPack 同时携带 previous_compacted_view blocks 与 previous_compacted_readable_view: CompactReadableViewVNext | None，并校验 summary presence、item source labels、block kind/label coverage一一对应。typed readable view不是第二个 truth，它与 blocks 在同一个 projector 中从 ContextCompactedSemanticPayload.accepted_candidate 原子派生。"
- **反例/失败场景**: 实施 Agent 拿到 "校验...一一对应" 但没有具体校验规则，可能实现为 item count 相等（漏掉内容一致性）、text digest 比较（过度保守，source_label 本就不同）、或结构遍历（正确但未指定）。tier2 degrade 要求 "同步过滤 blocks 和 typed items"，但 plan 没有说明 degrade helper 的输入输出类型和一致性断言方式。实施 Agent 可能写出 `filter_blocks()` 和 `filter_view()` 两个独立函数，然后在调用处忘记验证一致性。
- **为什么有问题**: "一一对应"是正确意图，但不是 code-generation-ready 规格。plan 要求 implementation agent 自己设计一致性校验协议，这违反了 plan 的 "code-generation-ready" 目标。且该校验直接影响 tier2/tier3 fail closed 的正确性——若校验过弱，不一致会静默传播到下一次 compact input。
- **直接证据**: plan §6.3 原文 "校验 summary presence、item source labels、block kind/label coverage一一对应"——没有具体校验函数签名、校验时机（constructor? projector?）、失败类型。design §25 对 degrade 的规定是 "保留完整 semantic section、丢弃完整 semantic section，或在 section 内按确定性顺序保留/丢弃完整 semantic item"，但没有规定 blocks/view 一致性校验协议。
- **影响**: 实施 Agent 自行设计一致性校验，可能导致过弱校验（静默不一致传播）或过度校验（误拒合法 degrade），且 review 无法基于 plan 验收。
- **建议改法和验证点**:
  1. 在 §6.3 增加 `CompactMaterialPack.__post_init__` 的具体校验规则：对每个 `CompactMaterialBlockKind`，typed readable view 中对应 section 的 item count 必须等于 blocks 中同 kind 的 block count；typed view 中每个 item 的 `source_label` 必须等于对应 block 的 `block_label`。
  2. 明确 tier2 degrade helper 的签名：输入 `tuple[CompactMaterialBlock, ...]` + `CompactReadableViewVNext`，输出同类型 pair，内部保证过滤后仍满足上述一一对应不变量。
  3. 校验失败抛 `HostDurableError`（不是 `ValueError`），因为这是 persisted state 的 structural invariant violation。
- **修复风险**: 低（仅补充 plan 文本，不改变设计方向）
- **严重程度**: 中

### F2-未修复-中-S2 ordinary RunInput memory catch-up 校验路径规格不足

- **位置**: §6.4 "Ordinary RunInput 只消费 Memory 的 accepted compact projection"，§7.1 行为矩阵 "compact event存在但 memory latest ref不匹配"
- **问题类型**: 契约缺失
- **当前写法**: "MemorySnapshotView 增加 latest_compaction_event_ref；ordinary RunInput 若看到 compact event，则必须确认 memory snapshot 的 latest ref相同，否则按现有 memory repair/catch-up boundary fail closed。"
- **反例/失败场景**: 场景 A：compact event 存在（EventLog 中有 `CONTEXT_COMPACTED`），但 `MemorySnapshotView.latest_compaction_event_ref` 为 `None`——这是 memory projection lag 还是 no-op provider？plan 未区分。场景 B：两个 ref 都是非 None 但不相等——这是 stale snapshot（需 repair）还是已 superseded（正常）？plan 未说明比较语义。场景 C：S2 删除了 `CompactArtifactView.messages`，但 production dispatch 中 memory required catch-up 失败——此时已经没有 direct compact renderer 作为 fallback，S2 说 "fail closed"，但 fail closed 的具体路径是抛异常、返回错误 RunInput 还是触发 repair loop？
- **为什么有问题**: 这是 P3-C 最关键的安全边界之一——删除 second renderer 后，如果 memory catch-up 不可用，整个 ordinary dispatch 路径没有 fallback。plan 对此路径的规格不足以让 implementation agent 安全实现。
- **直接证据**: plan §6.4 "若看到 compact event，则必须确认 memory snapshot 的 latest ref相同，否则按现有 memory repair/catch-up boundary fail closed"——未定义 "相同" 的比较语义（event_id 字符串相等？），未定义 "fail closed" 的具体异常类型和调用方处理方式。当前代码 `run_input.py:337-358` `MemorySnapshotView` 没有 `latest_compaction_event_ref` 字段。
- **影响**: 实施 Agent 可能实现为过严校验（ref 格式不同导致误 fail）或过松校验（只用 `is not None` 检查），删除 second renderer 后 production 可能在边界 case 下无法 dispatch。
- **建议改法和验证点**:
  1. 明确比较语义：`MemorySnapshotView.latest_compaction_event_ref` 与 `CompactArtifactView.compaction_event_ref` 必须是同一 `event_id` 字符串。
  2. 明确 mismatch 行为：抛出 `MemoryProjectionRepairRequired`（复用现有类型），由 `RunInputBuilder.build()` 调用方按既有 repair path 处理，不新增 fail-closed 异常类型。
  3. 在 §9 S2 tests 中增加：compact event 存在但 memory snapshot `latest_compaction_event_ref=None` 触发 repair；两个 ref 均为非 None 但不相等触发 repair；均为 None（无 compact）正常通过。
- **修复风险**: 低（复用现有 repair 机制）
- **严重程度**: 中

### F3-未修复-中-S3 `RunInputMaterialBlock` 从 god-bag 到 typed evidence material 的迁移路径不完整

- **位置**: §6.6 "Accepted evidence typed LLM material 与唯一 renderer"，§8 S3 "Exact changes" 第4条
- **问题类型**: 契约缺失
- **当前写法**: "RunInputMaterialBlock 用一个 typed accepted_tool_evidence 字段取代 readable_tool_name/readable_query_text/readable_source_text god-bag 组合；evidence block 的 text 与 material.result_text 必须相同，否则 constructor fail closed。"
- **反例/失败场景**: `RunInputMaterialBlock` 当前被 `compact_pipeline.py`、`run_input.py` 和 `compact_material.py` 多处构造和消费。plan 要求新增 `accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None` 字段，但：1) 未说明旧字段 (`readable_tool_name`, `readable_query_text`, `readable_source_text`) 的删除顺序——是 S3 一次性删除还是先加新字段再删旧字段？2) `compact_pipeline.py:1101` 的 `_accepted_tool_evidence_content(block)` 目前从 block 的旧字段读取，S3 要求它改用唯一 renderer，但该函数的参数类型仍是 `RunInputMaterialBlock`——改为接收 `AcceptedToolEvidenceLLMMaterial` 后，调用方如何适配？3) "evidence block 的 text 与 material.result_text 必须相同"——这是在 constructor 里校验还是 renderer 校验？如果 material 为 None 但 block.text 非空呢？
- **为什么有问题**: `RunInputMaterialBlock` 是 compact pipeline → run input 的关键数据交换类型。plan 对它的迁移描述过于简略，实施 Agent 需要自己判断删除顺序、适配调用方、设计 constructor 校验。
- **直接证据**: plan §6.6 "RunInputMaterialBlock 用一个 typed accepted_tool_evidence 字段取代 readable_tool_name/readable_query_text/readable_source_text god-bag 组合；evidence block 的 text 与 material.result_text 必须相同，否则 constructor fail closed。"——没有展示新的字段设计，没有说明旧字段删除时机。
- **影响**: 实施 Agent 可能在 S3 中引入中间态（新旧字段并存），或遗漏某个调用方的适配，导致运行时 `AttributeError` 或静默使用旧字段。
- **建议改法和验证点**:
  1. 在 §6.6 增加 `RunInputMaterialBlock` 的完整字段变更：新增 `accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None`（仅 `EVIDENCE` kind 的 block 非 None）；删除 `readable_tool_name`, `readable_query_text`, `readable_source_text`。
  2. `__post_init__` 校验：当 `kind == EVIDENCE` 且 `accepted_tool_evidence is not None` 时，`text == render_accepted_tool_evidence_for_llm(accepted_tool_evidence)`；当 `accepted_tool_evidence is None` 时，block 为 non-evidence kind 或 evidence unavailable（不产生 block）。
  3. S3 实施顺序：先新增字段 + 唯一 renderer → 迁移 consumer → 删除旧字段，三步在同一 slice 内完成。
- **修复风险**: 低
- **严重程度**: 中

### F4-未修复-低-`POST_COMPACT_BASE_MESSAGE_COUNT = 2` 推导未说明

- **位置**: §6.5 "Post-compact budget API"
- **问题类型**: 最佳实践偏离
- **当前写法**: "POST_COMPACT_BASE_MESSAGE_COUNT = 2"，放置在 `context_budget.py`，用于 `estimate_post_compact_budget` 的固定 message overhead。
- **反例/失败场景**: 如果未来 post-compact dispatch 的消息数量变化（例如增加了 guidance message），硬编码的 2 会低估 overhead。当前 design §23 的 ordinary RunInput 消息构造顺序列出了 10 个 section，最终合并为 1 条 system envelope + current input user message = 2 条——今天成立，但不是 `context_budget` 模块自身的知识。
- **为什么有问题**: `context_budget` 不应该拥有 "post-compact dispatch 总是 2 条消息" 这个 knowledge——它属于 `RunInputBuilder` 的组装规则。如果消息数量是 policy 控制的或由 provider contract 决定，硬编码 2 是脆弱的。
- **直接证据**: plan §6.5 `POST_COMPACT_BASE_MESSAGE_COUNT = 2`；当前代码 `compaction_operation.py:69` `_POST_COMPACT_BASE_MESSAGE_COUNT = 2`。
- **影响**: 低——当前 production 确实是 2，但未来变更可能遗漏更新。
- **建议改法和验证点**:
  1. 在 plan 中说明 2 的推导：system envelope（合并后的单条 system message）+ current input user message = 2，与 design §23 one-system-message contract 一致。
  2. 增加注释说明该值随 one-system-message contract 变化而变化。
  3. 或考虑将该常量作为 `estimate_post_compact_budget` 的默认参数，允许 caller override。
- **修复风险**: 低
- **严重程度**: 低

### F5-未修复-低-§9 缺少 "compact event存在但 memory latest ref不匹配" 的显式测试项

- **位置**: §9 "Tests、coverage、pyright 与 validation" S2 tests
- **问题类型**: 测试缺口
- **当前写法**: S2 Tests/assertions 包含 "compact ref与memory latest ref mismatch触发repair/fail closed"，但 §9 的 aggregate test matrix 没有显式列出覆盖该场景的测试文件或测试函数。
- **反例/失败场景**: S2 完成后跑 aggregate test matrix，所有测试通过，但 "mismatch 触发 repair" 路径实际上没有被任何测试覆盖——因为现有测试可能都使用 consistent fixture。
- **为什么有问题**: plan 把 mismatch 作为 S2 的关键安全边界（删除 second renderer 后的唯一保护），但测试覆盖要求不够显式。
- **直接证据**: plan §9 列出了 8 个测试文件但没有标注哪个覆盖 mismatch 场景；§8 S2 Tests/assertions 第4条提到了但 §9 未映射。
- **影响**: 低——如果实施 Agent 严格按 §8 S2 的 assertions 写测试，该场景会被覆盖。风险是 aggregate test matrix 跑过后可能漏掉。
- **建议改法和验证点**: 在 §9 S2 focused tests 列表中明确：`tests/host/test_run_input_builder.py` 必须包含 `test_compact_event_memory_ref_mismatch_triggers_repair`。
- **修复风险**: 低
- **严重程度**: 低

---

## Finding Dispositions (Focus Area 10) Review

逐条验证 plan §4 的 9 个 finding 裁决：

| Finding | Plan 裁决 | 代码证据 | 评审结论 |
|---|---|---|---|
| AgentDS 6 | accepted, scope corrected | `memory.py:1733`, `compact_pipeline.py:1101`, `run_input.py:2998` — 三套 renderer 确实存在 | **PASS** — 裁决正确，scope 准确 |
| AgentDS 14 | accepted | `compaction_operation.py:1471-1493` — 纯估算，无副作用；`compaction_operation.py:1516-1518` — 错误包含 diagnostics | **PASS** — 裁决正确，且 plan 正确识别了 diagnostic overcount 问题 |
| AgentDS 16 | accepted, scope corrected | `memory.py:617,619,428` — `intent_type: str`, `status: str`, `reason: str`；`context_events.py:516-533` — 只校验基础形状 | **PASS** — 裁决正确，正确区分了 LLM proposal ingress（已有严格校验）与 persisted read side（仍有缺口） |
| AgentDS 22 | rejected-with-reason | `memory.py:78` `_USER_INPUT_TEXT_UNAVAILABLE` 仅用于 `USER_INPUT_ACCEPTED` 文本缺失 | **PASS** — 裁决正确，`_USER_INPUT_TEXT_UNAVAILABLE` 与 accepted evidence query unavailable 是不同业务事实 |
| AgentMiMo DS-1 | accepted | `compact_payload.py` 当前只有局部 helper，无五类 semantic read contract | **PASS** — 裁决正确 |
| AgentMiMo DS-5 | accepted, partially fixed | `accepted_result_projection.py` 已统一 query/source/result 读取，但 `memory.py:1733`, `compact_pipeline.py:1101`, `run_input.py:2998` 三套 renderer 仍重复 | **PASS** — 裁决正确，范围准确 |
| AgentMiMo DS-6 | accepted, scope expanded | `evidence.py:38` 字符串常量；`accepted_result_projection.py:276`, `compact_material.py:2264` `str(exc)` 比较 | **PASS** — 裁决正确，正确识别了 durable memory 也重复 parse envelope（`compact_material.py:2260-2265`） |
| AgentMiMo DS-7 | accepted only for P3-C typed evidence boundary | `accepted_result_projection.py:759-770` `_optional_text` lenient accessor | **PASS** — 裁决正确，范围限制合理，不横扫其它模块 |
| AgentMiMo DS-8 | rejected-with-reason for P3-C | `accepted_result_projection.py` `result_details_text` 与 Tool Trace hot/cold bounded display 是不同投影层 | **PASS** — 裁决正确，P3-C 不改 `tool_trace.py` 的 non-goal 合理 |

**Finding 裁决评审结论**：全部 9 个 finding 裁决基于直接代码证据成立。accepted 7 个的 scope correction/narrowing 准确；rejected 2 个的理由充分且与代码事实一致。无错误裁决。

---

## Architecture Boundary Review

### Owner boundary 闭合性

逐个检查 plan §5 的 7 个语义 owner boundary：

1. **compact candidate 五类业务语义**：producer (LLM + accept barrier) → validator (proposal ingress + persisted read) → persistence (`CONTEXT_COMPACTED`) → projection (`ContextCompactedSemanticPayload`) → consumers (memory, previous view, RunInput, budget)。**闭合** ✓
2. **forward intent type/status、reference reason**：enum constructor → persisted JSON `.value` → snapshot codec → same parser。**闭合** ✓
3. **accepted compact ordinary LLM material**：accepted candidate → memory projection → snapshot → RunInput sections。**闭合** ✓
4. **accepted compact next-compactor previous view**：accepted candidate → compact material projector → typed view + blocks → `ConversationCompactInputVNext`。**闭合** ✓（见 F1 关于一致性校验的补充要求）
5. **post-compact budget**：candidate business texts → `context_budget` pure estimator → operation gate。**闭合** ✓
6. **accepted evidence durable facts**：ToolRuntime/accept barrier → envelope codec → `AcceptedToolResultProjection` → `AcceptedToolEvidenceLLMMaterial`。**闭合** ✓
7. **accepted evidence LLM 文本**：typed LLM material → 唯一 renderer → memory/compact/fallback。**闭合** ✓

所有 7 个 owner boundary 形成完整的 producer-validator-persistence-projection-consumer 链。无 contract-only half product。

### 依赖方向

- `context_budget` ← direct text params（不依赖 `ConversationCompactOutputVNext`）✓
- `compact_payload` → `ConversationCompactOutputVNext`（已有依赖，不新增反向依赖）✓
- `accepted_result_projection` → `AcceptedToolEvidenceLLMMaterial`（同模块内新增窄类型）✓
- memory/compact pipeline/run input → projection owner（不反向）✓

### 不过度设计

plan §12 的 non-goals 和不过度设计说明覆盖完整：
- 只新增 2 个窄 typed value + 1 个专用异常 ✓
- 不创建 God dataclass/builder/factory/registry ✓
- 不横扫 `tool_trace.py` ✓
- 不为未来预留抽象 ✓

---

## Slice Closure Review

### S1: Accepted compact typed payload → Conversation Memory closure

- **Producer**: `compact_payload.parse_context_compacted_semantic_payload()` ✓
- **Validator**: parser strict enum construction + digest check ✓
- **Persistence**: snapshot JSON `.value` roundtrip ✓
- **Projection**: memory projector from typed candidate ✓
- **Consumer**: memory sections → RunInput ✓
- **闭合判定**: **闭合**。S1 独立可验证：从 typed parser 到 snapshot roundtrip 到 memory projection 的完整链路在 S1 内部形成闭环。

### S2: Typed previous view → compact pipeline / ordinary RunInput / budget closure

- **Producer**: compact material projector from `ContextCompactedSemanticPayload` ✓
- **Validator**: blocks/view consistency check（见 F1）⚠️
- **Persistence**: material pack/manifest ✓
- **Projection**: `CompactReadableViewVNext` + `CompactArtifactView`(provenance) ✓
- **Consumer**: next compact input, ordinary RunInput, budget estimator ✓
- **闭合判定**: **条件闭合**。需补充 F1 的一致性校验规格后才能确保 projector → validator → consumer 完整闭环。

### S3: Accepted evidence typed LLM material / renderer / typed mismatch closure

- **Producer**: `AcceptedToolResultProjection.llm_material` ✓
- **Validator**: material dataclass 非空校验 + strict payload accessor ✓
- **Persistence**: memory/runner input projection 为派生记录 ✓
- **Projection**: `render_accepted_tool_evidence_for_llm()` ✓
- **Consumer**: memory recent evidence, ordinary protected tail, fallback RunInput ✓
- **闭合判定**: **闭合**。S3 独立可验证：从 typed material 到唯一 renderer 到三个 consumer 的完整链路在 S3 内部形成闭环。

---

## Test Coverage, Pyright, README, Propagation Audit 可执行性

### 测试可执行性

§9 的命令和测试文件列表完整、可直接复制执行。以下验证点确认：

- focused tests 按 slice 组织，每个 slice 先跑自己的测试 ✓
- aggregate matrix 覆盖 11 个测试文件 ✓
- 逐文件 coverage `--fail-under=80` 覆盖 13 个 production 文件 ✓
- source scans 使用 `rg` + `git diff` 可验证 ✓
- import boundary + weak typing guard tests 明确 ✓

### 潜在遗漏

- §9 的 source scan 正则表达式覆盖面不完全：`rg -n '_PAYLOAD_FIELD_(SESSION_SUMMARY|...)' dayu/host/memory.py dayu/host/compact_material.py dayu/host/run_input.py` —— S1 删除 memory.py 的常量后，如果 compact_material.py 和 run_input.py 仍有自己的副本，source scan 会命中但 plan §9 说 "字段常量只允许留在...真实owner"——这个预期是对的，但需要确认 S2 也删除了 compact_material.py 和 run_input.py 的独立常量。plan §8 S2 exact changes 未显式列出 "删除 compact_material.py / run_input.py 的 candidate 字段常量"，但 completion signal 说 "compact_material.py 与 run_input.py 不再独立 parse accepted candidate"——应保持一致。
- 参见 **F5**：mismatch 测试未显式列入 §9。

### Pyright

§9 的命令覆盖 `dayu/ tests/ utils/` 全量 pyright + import boundary + weak typing guard。**可执行** ✓

### README

§11 明确了哪些 README 需要更新、哪些不需要、更新的具体内容。合理 **可执行** ✓

### Propagation audit

§10 的两条 propagation path（compact semantic fact + accepted evidence fact）覆盖从 producer 到所有 consumer 的完整链路，每条 path 附带具体 audit assertions。**可执行** ✓

---

## Behavior Matrix Review

### §7.1 Compact payload / memory / RunInput

- 覆盖了 valid/empty/anchor children/invalid enum/type error/digest mismatch/old alias/snapshot corruption/tier2 degrade/memory ref mismatch/diagnostic overcount 共 11 个场景 ✓
- "tier 2 whole-section/item degrade" → "typed view与blocks同步过滤"——一致性与 F1 相同问题 ⚠️
- "compact event存在但 memory latest ref不匹配" → "repair/catch-up或fail closed"——一致性与 F2 相同问题 ⚠️

### §7.2 Accepted evidence

- 覆盖了 valid/envelope missing/query unavailable/source unavailable/tool name/result unreadable/producer mismatch/payload type error/status unchanged/result long 共 10 个场景 ✓
- "envelope存在但 typed LLM material缺失视为 accepted fact损坏并 HostDurableError"——与 plan §6.6 一致 ✓

---

## Residual Risks

| Risk | Owner | 缓解 |
|---|---|---|
| S2 blocks/view 一致性校验由实施 Agent 自行设计（F1） | P3-C S2 | 补充 plan §6.3 的一致性校验规格 |
| S2 memory catch-up mismatch 处理路径未完全规格化（F2） | P3-C S2 | 补充 plan §6.4 的比较语义和异常类型 |
| S3 `RunInputMaterialBlock` 迁移顺序不明确（F3） | P3-C S3 | 补充 plan §6.6 的字段变更和迁移顺序 |
| `POST_COMPACT_BASE_MESSAGE_COUNT = 2` 未来可能漂移（F4） | 后续 phase | plan 中说明推导依据 |
| mismatch 测试未显式列入 aggregate test matrix（F5） | P3-C S2 | 补充 §9 测试项 |
| stop condition：production `CONTEXT_COMPACTED` shape 与 `to_json()` 不一致 | P3-C S1 | plan §13 已有 stop condition，设计合理 |
| stop condition：删除 compact direct renderer 后 production dispatch 无法通过 required catch-up | P3-C S2 | plan §13 已有 stop condition，与 F2 相关 |

---

## Open Questions

无。所有关键问题已转化为上述 findings。plan 当前无 blocking questions（§13 确认）。

---

## Plan Review Conclusion

**Verdict: `pass-with-risks`**

Plan 的架构方向、owner boundary 设计、slice 分解和 finding 裁决均基于当前代码直接证据且正确。三个 slice 分别形成 producer-validator-persistence-projection-consumer 闭环，不产生 contract-only half product。`ContextCompactedSemanticPayload` 保持窄语义不膨胀为 God contract。Post-compact budget 依赖方向正确。Accepted evidence typed LLM material 和唯一 renderer 设计满足业务可读、自足、无内部 refs/digests/治理术语的要求。Typed mismatch exception 替代字符串控制流。Enum fail closed 无 unknown/compatibility fallback。

**5 个 findings**（3 中 + 2 低）均为规格补充级别，不挑战架构方向：
- F1-F3（中）：需在 plan 中补充一致性校验规格、memory catch-up 语义、`RunInputMaterialBlock` 迁移路径
- F4-F5（低）：需补充常量推导说明和测试项映射

所有 findings 可在不改变 slice 结构和设计方向的前提下通过补充 plan 文本解决。修复风险均为低。

**建议**：在 plan 中解决 F1-F3 后即可进入 implementation；F4-F5 可在 implementation 过程中自然解决。

---

## Review Metadata

- **Findings count**: 5（中 3 + 低 2）
- **Finding dispositions verified**: 9/9 PASS
- **Owner boundaries verified**: 7/7 闭合
- **Slice closures verified**: S1 闭合, S2 条件闭合(见 F1), S3 闭合
- **Assumptions tested**: 12/12 confirmed
- **Blocking issues**: 0
- **Review artifact**: `docs/reviews/wu-semantic-ownership-01-p3-c-plan-review-ds.md`
