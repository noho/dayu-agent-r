# F14 Plan Review — AgentMiMo adversarial

## Review target

- artifact: `docs/gateflow/pr-190-f14-accepted-coverage-frontier-plan-20260806.md`
- goal confirmation: `docs/reviews/f14-goal-confirmation-20260806-221301.md`
- scope: F14 accepted coverage frontier，Host compact material owner 修改
- review focus: compacted_source_refs frontier 派生充分性、evidence id/EventLog id 异构、atomic Run group proof、全历史扫描风险、状态机覆盖、owner tests 与真实 CLI 证据边界

## Assumptions tested

1. `compacted_source_refs` 跨 rolling chain 的 ordered-unique union 足以确定所有已消费 raw material refs。
2. evidence id 与 EventLog event id 的异构在 frontier 过滤中被正确处理。
3. atomic Run group 的完整消费 proof 可从 `compacted_source_refs` + `turn_group_id` 机械派生。
4. 全历史扫描的成本可通过 prefix 优化控制。
5. 生命周期状态机覆盖所有 non-accepted 路径不推进 frontier。
6. owner tests 断言 deterministic frontier 行为，真实 CLI observation 为 post-fix observed evidence。

---

### 01-未修复-高-Run group atomic consumption proof 机制未规格化

- **位置**: §2 "从 accepted coverage 派生 raw frontier"，步骤 3
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: "使用 `run_id`/`turn_group_id` 和已覆盖的 user/answer canonical refs 判断已被 accepted boundary 完整消费的历史 Run group；只有能够由 accepted refs 证明完整消费的 prefix group 才可越过。缺少完整 proof 的 group 或 singleton 成为 frontier"
- **反例/失败场景**: plan 声称 "复用现有 Run group 原子选择"，但现有 `select_compact_segment` 是在已投影的 material blocks 上按 `turn_group_id` 分组。新 frontier 逻辑需要在 EventLog row 级别判断 Run group 是否已被完整消费，再决定是否跳过该 group 的 payload 投影。这两个粒度的衔接机制完全未说明：
  - 如何从 EventLog rows 确定一个 Run group 包含哪些成员（user input、answer、tool evidence）？需要先投影才知道一个 Run 有哪些 eligible blocks。
  - 如果先投影再判断，"跳过已消费 prefix group 以优化" 就不存在——已经读了 payload。
  - 如果先用 SQL 按 `run_id` 做 group-level 判断，需要知道每个 Run group 的完整成员 ref 集合，但这需要先读 payload 才能拿到 evidence_id。
- **为什么有问题**: 这是 plan 的核心派生逻辑，implementation agent 必须在此处做设计决策。plan 没有给出从 EventLog row 到 "Run group 完整消费 proof" 的机械路径，迫使 agent 自行推断，可能引入不一致的判断逻辑。
- **直接证据**: `compact_material.py:830-958`（`select_compact_segment` 在 block 级别分组）；`compact_material.py:2737-2795`（tool evidence 的 `canonical_source_refs` 是 `projection.evidence_id`，只有投影后才知道）
- **影响**: implementation agent 可能实现一个只在 block 级别做 partial-intersection 检查的简化版，失去 group-level prefix 优化，或者在 row 级别用不完整的 ref 集合判断导致误跳过。
- **建议改法和验证点**:
  1. 明确 frontier 派生是 "先投影所有 eligible rows 为 blocks，再按 `turn_group_id` 分组检查 consumed refs" 还是 "先做 group-level SQL prefix 推断，再只投影 frontier 之后的 rows"。
  2. 若为后者，说明如何在不读 payload 的前提下获取每个 Run group 的完整 ref 集合（或说明为什么不需要）。
  3. 在 owner test matrix A 中增加 "Run group 内部分 blocks 已消费、部分未消费时 fail closed" 的具体断言路径。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

---

### 02-未修复-中-全历史扫描成本控制的 prefix 优化路径未说明

- **位置**: §Risks and mitigations，"accepted chain 读取成本随历史增长" 行
- **问题类型**: 契约缺失
- **当前写法**: "查询只读 canonical compact/raw 类型；先用 Run group accepted anchor 派生最早可能未消费 prefix，再解析 frontier 后的 material payload；不得用 giant SQL NOT IN 或重新渲染已证明消费的 evidence payload"
- **反例/失败场景**: 风险缓解声称 "先用 Run group accepted anchor 派生最早可能未消费 prefix"，但 plan 的 §2 实现步骤没有描述这个优化。按 §2 的字面实现，每轮 pre-dispatch 需要：
  1. 读取全部 accepted CONTEXT_COMPACTED rows（SQL query + N 次 payload parse）
  2. 读取全部 raw material rows before current input（SQL query）
  3. 对每个 raw row 做 payload 投影（包含 `project_accepted_tool_result` 调用）
  4. 按 consumed refs 过滤
  对于 50+ 轮 compaction、数百条 raw events 的长期 session，步骤 1-3 的成本可能显著。缓解措施声称的优化在 plan 正文中没有对应实现步骤。
- **为什么有问题**: implementation agent 可能不做优化（按字面实现），导致性能退化；或者自行设计优化但与 plan 声称的 "Run group accepted anchor" 机制不一致。
- **直接证据**: plan §2 步骤 1-6 没有 prefix 优化步骤；风险缓解表中的描述与正文实现步骤不对应。
- **影响**: 实现性能退化或实现偏离 plan 声称的优化路径。
- **建议改法和验证点**:
  1. 在 §2 中增加一个显式步骤描述 prefix 优化：如何从 accepted chain 的最早 compaction 的 `compacted_source_refs` 推断最早可能未消费的 raw sequence，从而限制 raw rows 的查询范围。
  2. 或者明确说明不做 prefix 优化，并在 owner test matrix 中增加 "历史 session 性能" 的定性验证。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

---

### 03-未修复-中-compacted_source_refs 混合 id 类型的过滤语义需要显式说明

- **位置**: §语义 owner 与唯一真源 表格，"accepted consumption" 行；§2 步骤 5
- **问题类型**: 契约缺失
- **当前写法**: "只消费本次 immutable source boundary 中 represented / omitted exact partition 覆盖的 source refs"；步骤 5："对每个投影 block 按 `canonical_source_refs` exact 判断：全部 refs 已消费则删除"
- **反例/失败场景**: `compacted_source_refs` 包含三种不同语义的 id：
  - user/answer: `USER_INPUT_ACCEPTED` / `RUN_SUCCEEDED` 的 EventLog `event_id`
  - tool evidence: `projection.evidence_id`（不是 `TOOL_RESULT_ACCEPTED` 的 `event_id`）
  - previous compacted view: `CONTEXT_COMPACTED` 的 EventLog `event_id`

  当 frontier 逻辑检查一个 raw material row 是否已消费时，需要知道该 row 对应的 "consumable ref" 是什么。对于 tool evidence row，consumable ref 是 `projection.evidence_id`（需要先投影），不是 `row.event_id`。plan 没有显式说明这个映射规则。

  虽然 plan 否决了 `WHERE event_id NOT IN (compacted_source_refs)` 方案并提到了 "tool material 的 canonical source ref 是 evidence id"，但 §2 的实现步骤没有将这个区分落实为具体的过滤算法。
- **为什么有问题**: implementation agent 可能对 user/answer rows 用 `event_id` 匹配（正确），对 tool evidence rows 也用 `event_id` 匹配（错误，因为 consumed refs 里是 evidence_id），导致已消费的 tool evidence 未被过滤。
- **直接证据**: `compact_material.py:2786`（tool evidence 的 `canonical_source_refs=(projection.evidence_id,)`）vs `compact_material.py:2696`（user input 的 `canonical_source_refs=(row.event_id,)`）
- **影响**: 已消费的 tool evidence 重复出现在 material view 中，造成 compactor 输入冗余或 evidence fact 重复。
- **建议改法和验证点**:
  1. 在 §2 步骤 5 中显式说明：对每个投影后的 block，其 `canonical_source_refs` 就是用于 consumed 检查的 ref 集合；tool evidence block 的 ref 是 `evidence_id`，在投影时已确定。
  2. owner test matrix B.1 已覆盖 "evidence id 与 EventLog id 故意取不同值"，确认测试确实断言过滤使用 evidence_id 而非 event_id。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

---

### 04-未修复-中-repair accepted 与 initial accepted 的 frontier 差异未说明

- **位置**: §4 生命周期 图；Goal Confirmation §生命周期裁决
- **问题类型**: 状态机漏洞
- **当前写法**: "accepted (initial/repair/tier 1-3) -> one strict accepted boundary -> represented + omitted exact consumed refs"
- **反例/失败场景**: repair accepted 的 boundary 可能与 initial accepted 的 boundary 不同。如果 repair 推翻了 initial 的部分 replacement，新的 `compacted_source_refs` 可能不包含 initial 已消费的某些 refs（因为 initial 被标记为 attempt-rejected，不再是 accepted truth）。此时跨 chain 的 union 是否仍能正确反映所有已消费 refs？

  具体场景：
  1. Compact 1 (initial accepted): consumed refs = {R1, R2, R3}
  2. Compact 2 (initial attempt-rejected, repair accepted): repair 的 boundary 可能只覆盖 {R4, R5}，不包含 {R1, R2, R3}
  3. 但 compact 1 仍然是 accepted truth（repair 是独立的 compaction 轮次，不推翻 compact 1）

  这里需要澄清：repair 是在同一轮 compaction 中替换 proposal，还是创建新的 compaction event？如果是前者，attempt-rejected 的 event 不是 `CANONICAL_FACT` class，不会被 frontier 查询读取。如果是后者，两个 accepted events 并存。
- **为什么有问题**: plan 的生命周期描述将 initial/repair/tier 1-3 归为同一类别，但它们在 EventLog 中的表示和对 frontier 的影响可能不同。implementation agent 需要知道 attempt-rejected 的 `CONTEXT_COMPACTED` 是否被 frontier 查询过滤（当前代码按 `event_class = CANONICAL_FACT` 过滤，attempt-rejected 应该是 `DIAGNOSTIC` class）。
- **直接证据**: Goal Confirmation §生命周期裁决："Attempt rejected / repair pending: 没有 accepted truth，不推进"——但这只说明不推进，没说明 attempt-rejected event 是否存在于 EventLog 中以及是否被 frontier 查询过滤。
- **影响**: 如果 attempt-rejected 的 `CONTEXT_COMPACTED` event 有 `event_class = CANONICAL_FACT`，可能被误读为 accepted truth。
- **建议改法和验证点**:
  1. 明确 attempt-rejected 的 `CONTEXT_COMPACTED` 的 `event_class` 值。
  2. 在 owner test matrix C 中增加 "attempt-rejected compact event 存在于 EventLog 但不被 frontier 查询读取" 的断言。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

---

### 05-未修复-低-previous compacted view 在 rolling chain 中的 ref 累积语义

- **位置**: §2 步骤 1 "accepted consumed source refs" 描述
- **问题类型**: 契约缺失
- **当前写法**: "把每个 strict payload 的 `compacted_source_refs` 按 accepted terminal order、boundary order 做 ordered-unique union"
- **反例/失败场景**: 验证 `compacted_source_refs` 跨 chain union 的正确性需要理解一个非平凡的 chain 语义：
  - Compact N 的 `compacted_source_refs` 包含：本轮消费的 raw refs + compact N-1 的 event_id（通过 previous compacted view boundary entry）
  - Compact N-1 的 `compacted_source_refs` 包含：N-1 轮消费的 raw refs + compact N-2 的 event_id
  - Union 跨 chain 时，compact N-1 的 event_id 作为 compact N 的 source ref 出现，但 compact N-1 自身消费的 raw refs 只在 compact N-1 的 `compacted_source_refs` 中出现

  数学上 union(A_compact1 ∪ A_compact2 ∪ ...) 确实覆盖所有已消费 raw refs。但这个正确性依赖一个隐含假设：每个 compaction 的 `compacted_source_refs` 通过 previous compacted view 的 event_id ref 间接链接到前一个 compaction 的完整 consumed set。plan 没有显式论证这个 chain 完整性。
- **为什么有问题**: 这不是 bug，但 plan 声称 "该集合同时包含 represented 与 omitted coverage" 时没有说明 rolling chain 的间接链接机制。reviewer 或 implementation agent 需要自行推断 union 的完整性。
- **直接证据**: `compact_payload.py:162-182`（`compacted_source_refs` 从 represented + omitted labels 派生）；`compact_material.py:2306-2314`（previous compacted view blocks 的 `canonical_source_refs=(event_id,)`）
- **影响**: 低。正确性成立，但 plan 的论证不完整。
- **建议改法和验证点**: 在 §1 "读取 accepted coverage chain" 中增加一句说明 rolling chain 的 ref 累积正确性：每个 compaction 的 boundary 通过 previous compacted view entry 的 event_id ref 间接包含前序 compaction 的 consumed refs，因此 union 覆盖完整历史。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

### 06-未修复-中-owner test matrix A 的 "旧 terminal+1 实现失败" 断言需要具体化

- **位置**: §Owner test matrix A.1
- **问题类型**: 测试缺口
- **当前写法**: "该测试须在旧 terminal+1 实现失败、修复后通过，且不断言偶然 terminal sequence 常量"
- **反例/失败场景**: plan 要求测试 "在旧实现失败"，但没有说明如何验证这一点。implementation agent 需要知道：
  - 旧实现的 `_post_compact_delta_start_sequence` 返回 `latest_compacted_event.event_sequence + 1`
  - 测试构造的场景中，protected groups 的 event_sequence < `latest_compacted_event.event_sequence`
  - 因此旧实现会跳过这些 groups，新实现不会

  如果测试只是断言 "material view 包含 protected groups"，没有对比旧实现的预期行为，就无法证明这是一个 regression test。
- **为什么有问题**: 没有对比旧实现的断言，测试可能偶然通过（例如 fixture 构造不当导致 protected groups 在 terminal 之后）。
- **直接证据**: `compact_material.py:2549-2550`（旧实现 `return latest_compacted_event.event_sequence + 1`）
- **影响**: 测试可能不覆盖真实 regression 场景。
- **建议改法和验证点**:
  1. 明确测试 fixture 中 protected groups 的 event_sequence < latest compact event 的 event_sequence。
  2. 断言 `post_compact_delta_start_sequence` <= protected groups 的最小 event_sequence（旧实现会返回更大的值）。
  3. 或者增加一个显式的 "旧实现行为" 辅助函数用于对比。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/严重）**: 中

---

### 07-未修复-低-真实 CLI observation 与 owner tests 的边界声明可更清晰

- **位置**: §Validation plan "Fresh production CLI observation" 第 5-6 点
- **问题类型**: 测试缺口
- **当前写法**: "人工核对 compactor summary/EvidenceFact/reference continuity 的 source labels 确实属于该次 source boundary；不新增自然语言 heuristic"；"真实 CLI observation 是 post-fix observed evidence，不等同 Oracle formal acceptance"
- **反例/失败场景**: plan 的真实 CLI observation 步骤要求 "人工核对"，但没有说明核对的具体标准。什么程度的 source label 匹配算通过？如果 compactor 生成了正确的 frontier 但 LLM 输出的 summary 与 source labels 不完全一致（provider 非确定性），这算 frontier 问题还是 LLM 问题？
- **为什么有问题**: 真实 CLI observation 的验收标准模糊，可能导致 "通过" 判定不一致。
- **直接证据**: plan §Validation plan 第 4-5 点的描述。
- **影响**: 低。真实 CLI observation 是补充证据，不影响 core frontier 正确性。
- **建议改法和验证点**: 明确人工核对的最小标准：(1) frontier 不包含已消费 groups；(2) frontier 包含未消费 groups；(3) 每条 EvidenceFact 的 refs 非空且指向该次 boundary 内的 source。provider 输出差异属于 residual risk。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## Open questions

1. **Run group atomic proof 的实现路径**: plan 声称 "复用现有 Run group 原子选择"，但现有机制在 block 级别操作，新 frontier 需要在 row/block 级别做 consumed 判断。需要明确是先投影再分组，还是先做 group-level prefix 推断。（对应 finding 01）

2. **attempt-rejected CONTEXT_COMPACTED 的 event_class**: 需要确认 attempt-rejected 的 compact event 在 EventLog 中的 `event_class` 值，以确保 frontier 查询只读取 accepted truth。（对应 finding 04）

3. **prefix 优化是否在本 slice 实现**: 风险缓解表声称的 "Run group accepted anchor" 优化是否属于本 slice scope，还是 deferred。（对应 finding 02）

## Residual risks

| 风险 | 严重程度 | 跟踪方式 |
| --- | --- | --- |
| provider 非确定性影响真实 CLI observation 的可重复性 | 低 | 由 owner tests 证明 deterministic frontier；真实 run 如实记录 |
| 长期 session 的 accepted chain 读取成本 | 中 | 若 prefix 优化不在本 slice 实现，需在后续 slice 跟踪 |
| 21.7% 无 tool evidence 的 rows 永不被消费 | 低 | 现有行为，非 F14 引入；若需修复应作为独立 work unit |
| 旧 evidence bundle 含本机 raw SQLite | 低 | 公开 bundle 排除或脱敏 DB；exact-value secret scan |

## Plan review conclusion

**pass-with-risks**

plan 的核心设计方向正确：从 accepted `compacted_source_refs` chain 派生 frontier 优于 terminal+1 方案，且不引入新 schema/cursor。`compacted_source_refs` 跨 rolling chain 的 ordered-unique union 在数学上覆盖完整已消费 refs，evidence id 与 EventLog id 的异构在 block 级投影后被正确区分。

主要风险在于 Run group atomic consumption proof 的实现路径未规格化（finding 01），可能迫使 implementation agent 自行设计判断逻辑。其余 findings 为中低严重程度，不构成 blocker。

建议 Controller 裁决 finding 01 后提交 accepted plan，其余 findings 可在 implementation 阶段 resolution。
