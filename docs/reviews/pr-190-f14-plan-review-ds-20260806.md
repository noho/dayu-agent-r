# F14 Plan Review — Adversarial Review (AgentDS)

## Review metadata

- **Reviewed artifact**: `docs/gateflow/pr-190-f14-accepted-coverage-frontier-plan-20260806.md`
- **Goal Confirmation**: `docs/reviews/f14-goal-confirmation-20260806-221301.md`
- **Reviewer**: AgentDS (independent adversarial plan review)
- **Timestamp**: 2026-08-06T22:39:12+08:00
- **Gate**: plan review gate for F14
- **Plan base commit**: `ac68e77207c2809eabaf7ef51b6cdf65795889a7`

## Scope

本 review 聚焦用户指定的五个重点维度，同时应用 planreview skill 的全部 mandatory lenses：

1. accepted `compacted_source_refs` 是否足以派生 frontier
2. evidence id 与 EventLog id 异构处理
3. atomic Run group proof 是否有未说明推断
4. 全历史扫描 / 已消费 payload 重读风险
5. accepted/rejected/repair/cancel/stale/restart 状态机
6. owner tests 与真实 CLI 证据边界

## Assumptions tested

| # | Assumption | Evidence | Verdict |
|---|-----------|----------|---------|
| A1 | `compacted_source_refs` 包含 evidence 条目的 evidence_id（非 event_id） | `compaction.py:3187` 用 `block.canonical_source_refs` 构造 `source_refs`；`compact_material.py:2786` 对 evidence block 设 `canonical_source_refs=(projection.evidence_id,)`；`compact_payload.py:180` 的 `compacted_source_refs` 属性迭代 `entry.source_refs` | **成立** |
| A2 | 每个 compact 的 `compacted_source_refs` 只覆盖自己的 boundary（不累加） | `compact_payload.py:169-181`：`compacted_source_refs` 只从当前实例的 `represented_coverage` + `omitted_coverage` 标签与 `source_boundary` 求交集 | **成立**——需要跨 compact 做 ordered-unique union |
| A3 | user/answer block 的 `canonical_source_refs` 是 event_id | `compact_material.py:2696`（user: `(row.event_id,)`）、`compact_material.py:2731`（answer: `(row.event_id,)`） | **成立** |
| A4 | `current_input_ref` 不在 `compacted_source_refs` 中 | `compact_payload.py:221`：`source_refs != (semantics.current_input_ref, *semantics.compacted_source_refs)` 且 `current_input_ref=source_refs[0]` | **成立** |
| A5 | 只有 `CANONICAL_FACT` 的 `CONTEXT_COMPACTED` 进入 accepted chain | `compact_material.py:2220-2230`：`event_class = EventClass.CANONICAL_FACT.value` | **成立**——rejected/failed/cancelled 不会出现 |
| A6 | 前次 compact 的 previous view block 在 `compacted_source_refs` 中的 ref 是 compact event_id | `compact_material.py:2314`：`canonical_source_refs=(event_id,)` 其中 `event_id` 是 `CONTEXT_COMPACTED` 的 event_id | **成立** |
| A7 | `turn_group_id` 等于 `row.run_id` | `compact_material.py:2698,2733,2788`：均设 `turn_group_id=row.run_id` | **成立** |

## Findings

### F1-未修复-中-全量扫描与风险缓解矛盾

- **位置**: Implementation §1（"一次读取当前 input 之前、当前 Session 的全部 canonical `CONTEXT_COMPACTED` rows"）vs Risks（"先用 Run group accepted anchor 派生最早可能未消费 prefix"）
- **问题类型**: 不可直接实施 / 切片过粗
- **当前写法**: Implementation section 描述读取全部 accepted compacts 和全部 raw material rows；Risk 表格说要用 anchor 优化。两处没有一致的算法描述。
- **反例/失败场景**: 一个 200 轮交互的 Session 有 ~50 个 accepted compacts、~1200 个 raw EventLog rows。按 Implementation section 的字面描述，每次 pre-dispatch material view construction 都要扫描全部 50 个 compact payload + 全部 1200 个 raw rows + 解析全部 semantic payload。在 `build_pre_dispatch_compact_material_view` 被 dispatch scheduler、RunInput builder、reconnect 等多路径频繁调用时，这会引入可观测的性能退化。
- **为什么有问题**: Implementation agent 面对矛盾指令时，要么实现全量扫描（性能差），要么自己设计 anchor 优化（超出 plan scope，可能引入新边界错误）。Plan 没有给出 "最早可能未消费 prefix" 的具体推导算法。
- **直接证据**: Plan §1 第 70 行 "一次读取当前 input 之前、当前 Session 的全部 canonical `CONTEXT_COMPACTED` rows"；Plan Risks 第 232 行 "先用 Run group accepted anchor 派生最早可能未消费 prefix，再解析 frontier 后的 material payload"。两者未统一为同一算法描述。
- **影响**: 实施 Agent 跑偏 / 后续返工。如果按全量扫描实现，在长 Session 上性能退化；如果自行设计 anchor 优化，优化逻辑未经 review。
- **建议改法和验证点**:
  1. 明确 frontier 扫描起点推导算法：从 accepted compact chain 的最早 terminal 向前回溯，直到找到一个 Run group 的 `turn_group_id` 不在任何 accepted compact 的 `compacted_source_refs` 覆盖中，或达到 EventLog 第一条 raw event。
  2. 在 plan 中补充：raw material 扫描起点 = `min(latest_compact_terminal - recent_window_size, earliest_compact_terminal)` 或等价保守估计。
  3. 在 owner tests 中添加长链场景（>=10 轮 compact）验证扫描范围不退化。
- **修复风险（低/中/高）**: 低——只需明确算法，不改变架构。
- **严重程度（中/中/高/严重）**: 中

### F2-未修复-中-frontier 派生算法缺少关键实现步骤

- **位置**: Implementation §2 "从 accepted coverage 派生 raw frontier"
- **问题类型**: 不可直接实施
- **当前写法**: Plan 描述了 WHAT（读取 raw rows、按 run_id 分组、检查 consumed refs、部分相交 fail closed），但没有给出 HOW——具体来说：
  - `_post_compact_delta_start_sequence` 是否改变返回值语义？当前它返回一个 int 用作 SQL `WHERE event_sequence >= ?`。如果 frontier 需要从更早的 sequence 开始，该函数必须返回更早的值。
  - `_post_compact_delta_rows` 是否会读到比之前更多的 rows？如果 delta_start 前移，delta_rows 会包含已消费 groups 的 raw rows。
  - 过滤发生在 projection 之前（SQL 层）还是之后（block 层）？Plan §2.5 描述了 block 级过滤，但未说明与现有 `_pre_dispatch_delta_material_blocks` 的关系。
- **反例/失败场景**: Implementation agent 需要在以下三种合理方案中选择：
  (a) 修改 `_post_compact_delta_start_sequence` 返回更早的 sequence，让 delta_rows 返回更多 rows，再在 block 层过滤。
  (b) 保持 delta_start 不变，新增独立的 "unconsumed frontier walk" 逻辑。
  (c) 完全重构 `build_pre_dispatch_compact_material_view` 的内部流程。
  三种方案对 `CompactMaterialSourceBoundary` 的 `post_compact_delta_start_sequence` 语义影响不同。如果选错，会导致 boundary 诊断字段与 material_blocks 不一致（已有 strict invariant 校验，见 `compact_material.py:441-443`）。
- **为什么有问题**: Plan 自称 "code-generation-ready" 但缺少具体的函数级重构方案。Implementation agent 必须做的设计决策在 plan 中未裁决。
- **直接证据**: Plan §2 第 81-89 行描述了 6 个子步骤，但未说明它们如何嵌入 `build_pre_dispatch_compact_material_view` 的现有调用链（`_post_compact_delta_start_sequence` → `_post_compact_delta_rows` → `_pre_dispatch_delta_material_blocks`）。现有函数签名和职责边界需要变更，但未在 plan 中标注。
- **影响**: 实施 Agent 跑偏——如果实现方式与 `CompactMaterialSourceBoundary` 的 strict invariant 冲突，会触发 `post_compact_delta_end_sequence != current_input_event_sequence` 等运行时错误。
- **建议改法和验证点**:
  1. 在 plan 中明确：是修改 `_post_compact_delta_start_sequence` 的返回值语义让 SQL 读取更宽的 range，再在 block 投影后过滤；还是保持内部函数不变，在 `build_pre_dispatch_compact_material_view` 顶层新增 frontier 推导和过滤步骤。
  2. 标注需要变更签名的函数（`_pre_dispatch_delta_material_blocks` 的 `represented_evidence_refs` 参数是否需要替换为 accumulated consumed refs）。
  3. 明确 `post_compact_delta_start_sequence` 在修复后的语义：是 "第一条未消费 block 的 event sequence" 还是 "扫描起点（可能早于第一条未消费 block）"。
- **修复风险（低/中/高）**: 低——只需补充实现步骤到函数级粒度。
- **严重程度（中/中/高/严重）**: 中

### F3-未修复-低-`_pre_dispatch_delta_material_blocks` 的双重过滤交互未说明

- **位置**: Implementation §2.4 "复用现有 typed raw projector" + §2.5 block 级过滤
- **问题类型**: 不可直接实施
- **当前写法**: Plan §2.4 说 "复用现有 typed raw projector"（即 `_pre_dispatch_delta_material_blocks`），§2.5 说在 block 层按 accumulated `compacted_source_refs` 过滤。但 `_pre_dispatch_delta_material_blocks` 内部已有过滤逻辑：它用 `represented_evidence_refs`（只来自 latest compact）跳过 evidence blocks。
- **反例/失败场景**: 一个 evidence block 的 `evidence_id` 在倒数第二个 compact 的 `compacted_source_refs` 中，但不在最新 compact 的 `accepted_evidence_mapping_refs` 中。当前 `_pre_dispatch_delta_material_blocks` 会投影它（因为 latest compact 未覆盖），plan §2.5 的 post-filter 会删除它（因为 accumulated coverage 包含它）。结果是正确的，但 plan 没有说明这种 "先投影再删除" 的双重处理是预期行为。如果 implementation agent 以为 `_pre_dispatch_delta_material_blocks` 的过滤已足够而跳过 post-filter，该 block 会被错误保留。
- **为什么有问题**: 两个过滤层（`_pre_dispatch_delta_material_blocks` 的 evidence 过滤 + plan §2.5 的 block 过滤）职责重叠但数据源不同。Plan 没有明确它们的关系。
- **直接证据**: `compact_material.py:2775`：`if projection.evidence_id in represented_evidence_refs: return ()`。Plan §2.4 "复用现有 typed raw projector" 隐含保留此过滤。Plan §2.5 描述新的 block 级过滤但未提与现有 evidence 过滤的交互。
- **影响**: 实施 Agent 可能遗漏 §2.5 过滤（以为现有过滤已覆盖），或错误地移除现有 evidence 过滤（引入证据重复投影）。
- **建议改法和验证点**:
  1. Plan §2.4 明确说明：现有 `represented_evidence_refs` 过滤保留作为快速路径（跳过 latest compact 已覆盖的 evidence），§2.5 的 accumulated post-filter 作为 correctness backstop（处理更早 compact 覆盖的 blocks）。
  2. 或者，将 `represented_evidence_refs` 参数替换为 accumulated consumed refs，消除双重过滤。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低

### F4-未修复-低-answer block 缺失时 atomic group proof 的隐含行为

- **位置**: Implementation §2.3 "只有能够由 accepted refs 证明完整消费的 prefix group 才可越过"
- **问题类型**: 契约缺失
- **当前写法**: Plan 说用 `run_id` 判断 group 完整性，用 `canonical_source_refs` 判断消费。但没有说明当 `RUN_SUCCEEDED` row 存在但 `assistant_final_answer_continuity_text` 返回 None（即没有 answer block）时，group atomicity 如何处理。
- **反例/失败场景**: 一个 Run group 有 3 个 raw rows：user_input (event_id=100)、tool_result (evidence_id=abc)、run_succeeded (event_id=101，但 answer 无 continuity text → 无 answer block)。Compact 的 source boundary 包含 user (ref=100) 和 evidence (ref=abc)，但 answer 行（event_id=101）虽然在 raw rows 中存在却不产生 block。如果 compact 的 `compacted_source_refs` 包含了 answer 的 ref（event_id=101），但 raw projector 不产生 answer block，那么 group 的 raw projection 只有 user + evidence 两个 blocks。它们的 refs (100, abc) 都在 consumed set 中，group 被判定为已消费。这是正确的。但如果某个 compact 的 source boundary 没有包含 answer（空 answer 被 omitted 或不在 selection 中），compacted_source_refs 就没有 event_id=101，那么从 raw projection 看 group 只有 user+evidence，它们被消费了 → 正确。两种情况下行为一致，但原因不同。Plan 没有说明这一隐含推理。
- **为什么有问题**: 不阻挡实现（现有行为一致），但缺少 explicit contract 会让未来的维护者或 reviewer 误以为有 bug。
- **直接证据**: `compact_material.py:2719-2725`：`assistant_final_answer_continuity_text` 可返回 None；`compact_material.py:2659-2662`：返回 None 时不产生 answer block。Plan §2.3 没有提到这一场景。
- **影响**: 风险后移——不会导致当前实现错误，但缺少文档化的 group atomicity contract。
- **建议改法和验证点**: Plan 补充说明：group 消费判断以 raw projector 实际投影出的 blocks 为准（而非 raw EventLog rows），因为 projector 已按 compact selector 同等语义处理了空 answer 等边界。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 低

### F5-已核实-无问题-evidence id 与 EventLog id 异构

**结论**: Plan 对此问题的处理是正确的。经过代码验证：

- Evidence block 的 `canonical_source_refs` = `(projection.evidence_id,)`（`compact_material.py:2786`）
- User block 的 `canonical_source_refs` = `(row.event_id,)`（`compact_material.py:2696`）
- Answer block 的 `canonical_source_refs` = `(row.event_id,)`（`compact_material.py:2731`）
- `CompactSourceBoundaryEntryV4.source_refs` = `block.canonical_source_refs`（`compaction.py:3187`）
- `compacted_source_refs` 属性从 `entry.source_refs` 派生（`compact_payload.py:180`）

因此 `compacted_source_refs` 对 evidence 条目包含 evidence_id，对 user/answer 条目包含 event_id。Plan 的 heterogeneous ID 处理策略（不从 event_id 反推 evidence 消费、统一使用 `canonical_source_refs` exact match）有代码事实支撑。否决的 SQL `NOT IN` 路径也确实会错误地用 event_id 匹配 evidence_id。

**Test B1**（tool result EventLog id 与 accepted evidence id 故意取不同值）是正确且必要的。

### F6-已核实-无问题-状态机完整性

**结论**: Plan §4 生命周期和 Test §C 状态机覆盖了全部相关 transition。经过代码验证：

- `_latest_compacted_event_before_current_input`（`compact_material.py:2214-2230`）只查询 `EventClass.CANONICAL_FACT`——这意味着 rejected、failed、cancelled、stale/late 的 compact attempts 不会被读到 accepted chain 中。
- Repair accepted compact 如果是 CANONICAL_FACT，会被读入；repair pending/exhausted 不会形成 CANONICAL_FACT 行。
- Tier 4/5 fallback 不产生 CANONICAL_FACT 的 CONTEXT_COMPACTED（它们在 `dispatch.py` 的 compact 路径中走非 canonical 路径），因此不推进 frontier。
- Restart/reconnect 从 durable EventLog 重建——只要新实现只读 EventLog canonical fact 而不用进程内 cache，重启确定性有保障。

Plan 的 "只有 accepted terminal 才能推进 coverage" 不变量与现有 EventLog 查询结构一致。

### F7-已核实-无问题-owner test 矩阵与真实 CLI 证据边界

**结论**: Plan 的 owner test 矩阵（§A-D）覆盖了 regression、rolling frontier、evidence ownership、状态机、同源投影五个维度。值得肯定的点：

- Test A1 直接针对 bug scenario（terminal 在 protected groups 之后但 boundary 只覆盖 older prefix），且要求旧实现失败/新实现通过。
- Test B1 显式构造 evidence_id ≠ event_id 的场景。
- Test C 区分 "有 accepted terminal → 推进" 和 "无 accepted terminal → 不变"。
- Test D 要求从同一 accepted terminal 的 typed payload（而非 raw JSON 或 fixture 默认值）断言。

真实 CLI observation（§Validation plan §Fresh production CLI observation）正确地区分了 "observed evidence" 和 "Oracle formal acceptance"——不修改 registry accepted/ready 状态。

一个注意点：Plan 列出的 allowed test files 涵盖 5 个测试文件（共 ~26000 行），但实际上本 work unit 只修改 `compact_material.py` 一个生产文件。`test_run_input_builder.py`（7609 行）、`test_dispatch_scheduler.py`（12628 行）等受影响的测试如果已有相关用例，只需补 "没有 accepted terminal 就没有 coverage 变化" 的断言——plan 也明确说了 "不得复制整套 scheduler 状态机到 material 单测"。这个边界是合理的。

## Architecture boundary review

Plan 的修复边界与 Goal Confirmation 一致：只修改 Host compact material owner。具体验证：

| 检查项 | 结果 |
|--------|------|
| 不修改 Engine | ✅ `dayu/engine/**` 在 forbidden 列表中 |
| 不修改 schema/public contract | ✅ Plan 声明不新增表/字段/cursor |
| 不修改 prompt/provider | ✅ 在 forbidden 列表中 |
| 不新增 second cursor/projector | ✅ Plan 明确说 frontier 是派生值 |
| 不修改 CLI/renderer | ✅ 在 forbidden 列表中 |
| `post_compact_delta_start_sequence` 语义变化 | ⚠️ 见 F2——语义从 "terminal+1" 变为 "最早未消费 sequence"，但 `CompactMaterialSourceBoundary` 的字段名不变，可能产生误导 |

## Overcoupling review

无明显过度耦合问题。Plan 正确地把 frontier 派生集中在 `build_pre_dispatch_compact_material_view` 内，不要求下游 consumer（RunInput、Memory、dispatch）各自计算。

## Overengineering review

无明显过度设计。Plan 拒绝了新增 persisted frontier/cursor、第二 projector、兼容性 reader 等方案，选择最小路径：复用现有 accepted truth 中的 `compacted_source_refs`。

## Open questions

1. **扫描范围锚点**: 最早未消费 prefix 的推导算法具体是什么？是否从 accepted compact chain 的最早 terminal 向前回溯？
2. **`_post_compact_delta_start_sequence` 重命名**: 当前函数名包含 "delta_start_sequence"，修复后它可能返回比实际 delta 更早的 sequence（作为扫描起点）。是否需要重命名或调整文档以反映新语义？
3. **Performance test**: 长 Session（≥50 轮 compact）场景下，新的 accepted chain + raw material 扫描是否在 owner tests 中有覆盖？Plan 的 test matrix 没有显式提及性能/规模测试。

## Residual risks

| 风险 | 严重程度 | 追踪建议 |
|------|----------|----------|
| 全量扫描性能退化（见 F1） | 中 | Implementation 阶段明确 anchor 优化策略并做长链 benchmark |
| `post_compact_delta_start_sequence` 语义漂移（见 F2） | 中 | Implementation 前补充函数级重构方案 |
| 双重过滤遗漏（见 F3） | 低 | Implementation 阶段在 code review 中验证 |
| Provider 非确定性导致 CLI observation 与 owner test 不一致 | 低 | 已由 plan 的 "deterministic owner tests 证明 frontier + real run 如实记录" 策略覆盖 |

## Final plan review conclusion

**Gate decision**: `pass-with-risks`

**理由**:

Plan 正确识别了 root cause（`_post_compact_delta_start_sequence` 把 ledger terminal 位置误当 consumption frontier），动机成立且严重性正确。语义 owner 分析准确，拒绝的错误路径（SQL NOT IN、新建 cursor、从 non-source 反推 coverage）有代码事实支撑。`compacted_source_refs` 的 heterogeneous ID 处理经过代码验证是正确的。状态机覆盖完整。Owner test 矩阵全面且有针对性的反例。

三个 findings（F1 全量扫描矛盾、F2 缺少函数级重构方案、F3 双重过滤交互未说明）都是 implementation-readiness 层面而非架构/正确性层面。它们不构成结构性风险，但如果不解决，implementation agent 需要自行做设计决策，引入本应由 plan review 消除的不确定性。

**建议**: Controller 裁决三个 findings 后，由 implementation agent 在开始编码前先补充受影响的函数签名变更方案（不超过 10 行伪代码），然后在 F2 路径确认后推进实现。F1 和 F3 可在 implementation 阶段自然解决——F1 选锚点策略、F3 在 code review 中验证。
