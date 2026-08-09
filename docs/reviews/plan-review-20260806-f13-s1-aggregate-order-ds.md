# AgentDS Review: F13 S1 Aggregate Order Contract Correction

- **review target**: `docs/gateflow/pr-190-f13-s1-aggregate-order-correction-20260806.md`
- **review base**: accepted plan `docs/gateflow/pr-190-f13-evidence-provenance-plan-20260806.md` + design diff `docs/host/design.md`
- **reviewer**: AgentDS
- **date**: 2026-08-06
- **conclusion**: `accepted`（一条 blocking finding 需修正，两条 medium finding 需确认）
- **re-review date**: 2026-08-06
- **re-review conclusion**: `accepted`（三条 finding 全部已修正，无残余 blocking/medium）

---

## 1. Motivation Verification（动机是否成立）

### Finding 1.1 [CONFIRMED] 反例真实存在，当前实现会错误拒绝合法 proposal

**证据链**：

1. 当前 `compact_payload.py:501-528` 的 `_validate_aggregate_boundary_ordered_subset` 对 aggregate refs 做 `positions[ref]` 索引后要求 `ordinals == tuple(sorted(ordinals))`（第 524-528 行），即 aggregate 必须按 boundary evidence 全局顺序单调递增。

2. 反例构造：
   - immutable boundary 顺序: `E1(canonical_evidence_refs=[r1]), E2(canonical_evidence_refs=[r2])`
   - request union = `(r1, r2)`
   - 模型 proposal: `evidence_facts = [{claim: "fact A", support_labels: ["E2"]}, {claim: "fact B", support_labels: ["E1"]}]`
   - 逐 fact refs: fact A → `(r2)`, fact B → `(r1)`
   - replacement aggregate（按 fact/entry 顺序的 ordered unique union）= `(r2, r1)`
   - `positions = {r1: 0, r2: 1}`, `ordinals = (1, 0)`, `sorted(ordinals) = (0, 1)` → 不等 → `ValueError("accepted_evidence_mapping_refs must follow boundary evidence order")`

3. 但该 proposal 每条 fact 的 binding 完全合法：fact A 只选 E2（当前 evidence_material），refs 等于 E2 的 canonical_evidence_refs；fact B 只选 E1（当前 evidence_material），refs 等于 E1 的 canonical_evidence_refs。两条 fact 的 selection、claim、refs 均满足逐 fact strict binding。

4. 该 proposal 在 Context Governance accept 阶段会成功通过 `derive_compact_accepted_replacement_v4`（`compaction.py:1634-1711`），产出合法的 `CompactAcceptedReplacementV4`，其 `canonical_evidence_refs` property（`compaction.py:1593-1606`）按 fact/entry 顺序产出 `(r2, r1)`。

5. 但在 durable payload 构造阶段（`compact_payload.py:126`），`_validate_aggregate_boundary_ordered_subset` 会拒绝这个已被 governance 接受的 replacement，导致 accepted proposal 在持久化前才失败。

**结论**：动机成立。当前实现存在 accept owner（governance）与 reader（persistence）之间的契约矛盾：governance 按 per-fact binding 产出正确的 replacement，但 persistence reader 额外施加了跨 fact 全局顺序约束，使合法 proposal 在持久化阶段失败。这违反"accept owner 必须在持久化前给出完整接受结果"的边界。

---

## 2. Owner Boundary Analysis（语义所有权分析）

### Finding 2.1 [CONFIRMED] replacement aggregate 的正确 owner 是 accept owner（governance），不是 reader

**分析**：

- replacement aggregate 是逐 fact refs 按 fact/entry 顺序的 ordered unique union（design line 3471）。这是一个**派生 projection**，真源是逐 fact atom 的 `canonical_evidence_refs`。
- `derive_compact_accepted_replacement_v4`（`compaction.py:1634`）是唯一 replacement 构造者，它正确地为每个 fact 构造 per-entry ordered refs，并按 retained-first-then-new-in-proposal-order 排列 facts。
- `CompactAcceptedReplacementV4.canonical_evidence_refs` property（`compaction.py:1593-1606`）通过 `dict.fromkeys` 从 facts 迭代中产生 ordered unique union——这正是正确的 aggregate。
- `validate_compact_proposal_replacement_binding_v4`（`compaction.py:1877-1898`）通过 `expected = derive_compact_accepted_replacement_v4(...)` 然后 `replacement != expected` 做 exact equality check——这已经完整验证了逐 fact binding 和跨 fact 顺序。

**结论**：accept owner 已经正确完成了 aggregate 的构造和验证。reader（persistence）的 `_validate_aggregate_boundary_ordered_subset` 不应额外施加 accept owner 未承诺的约束。correction document 将 validator 收敛为 membership + uniqueness 是正确的 owner boundary 修正。

### Finding 2.2 [BLOCKING] Design 存在残余矛盾：line 3471 vs line 3930-3931

**证据**：

- design line 3471（主 acceptance 段）明确写：**"不得强制 aggregate 遵循跨 fact 的 boundary 全局顺序，因为 proposal 中 facts 的业务顺序可以与各 fact 的 evidence boundary 顺序不同"**。这与 correction document 一致。

- design line 3929-3931（reactive multi-pass 段）仍写：**"最终 root governance validator必须重新对 aggregate proposal、aggregate replacement与完整 root boundary执行... accepted aggregate union与 request-boundary ordered-subset校验"**（强调为原文）。

- 这两处直接矛盾：line 3471 说"不得强制全局顺序"，line 3931 说"必须 ordered-subset 校验"。`ordered-subset` 的语义在当前实现中就是 `ordinals == tuple(sorted(ordinals))`——即强制全局顺序。

**影响**：如果 S1 实现只修改 `compact_payload.py:501-528` 而保留 design line 3930-3931 的 "ordered-subset" 文字，则 reactive multi-pass path 的 root governance validator 可能被误解为仍需强制全局顺序。这会引入：
- 单 pass（proactive）路径：通过（因为 persistence reader 已修正）
- 多 pass（reactive）路径：可能在 root validator 被拒绝（如果实现者按 design line 3930-3931 的文字实现）

**建议**：在 S0/S1 中同步修正 design line 3929-3931，将 `ordered-subset校验` 改为 `unique membership/subset校验`，与 line 3471 保持一致。这是 design 文本矛盾，不是代码矛盾——当前代码中 governance 的 `derive_compact_accepted_replacement_v4` + `validate_compact_proposal_replacement_binding_v4` 已经正确，没有额外的 ordered-subset 检查。但 design 文本的不一致会在后续 review/test 中造成混淆。

---

## 3. Membership + Uniqueness Sufficiency Analysis

### Finding 3.1 [CONFIRMED] membership + uniqueness + replacement equality 三个约束联合足够

**当前约束矩阵**（修正后）：

| 约束 | 强制执行位置 | 覆盖的违规 |
|------|-------------|-----------|
| aggregate exact 等于 replacement union | `compact_payload.py:107-109` (`accepted_evidence_mapping_refs != replacement.canonical_evidence_refs`) | 任何 aggregate 与逐 fact refs 不一致 |
| replacement exact 等于 governance 展开结果 | `compact_payload.py:121-125` → `compaction.py:1877-1898` (`replacement != expected`) | 任何 fact 的 refs 与 boundary 绑定漂移 |
| 每条 fact refs 非空 | `CompactAcceptedEvidenceFactV4.__post_init__` (`compaction.py:1533-1537`) | 空 refs |
| 每条 fact refs 唯一 | `CompactAcceptedEvidenceFactV4.__post_init__` (`compaction.py:1533-1537`) + `derive` 中的 `dict.fromkeys` | fact 内重复 refs |
| aggregate 每个 ref 属于 request union | `_validate_aggregate_boundary_ordered_subset` 修正后（membership check） | 越界 refs |
| aggregate refs 全局唯一 | 隐式：`canonical_evidence_refs` property 用 `dict.fromkeys` + equality check 会因重复而失败 | aggregate 内重复 refs |

**分析**：

1. 删除全局顺序约束后，不会产生新的逃逸路径。原因是：replacement 的 exact equality check（line 107-109 + 121-125）已经完整验证了逐 fact refs 的正确性，包括每条 fact 内部 refs 的 boundary 顺序。aggregate 顺序完全由 replacement 的 fact 顺序和每条 fact 内部 refs 顺序决定，而这些都由 governance 唯一构造。

2. 跨 fact 的业务顺序（模型先输出 E2-fact 还是 E1-fact）不影响逐 fact provenance 正确性——每条 fact 的 refs 仍然是其 selected boundary entries 的 ordered union。

3. 唯一性在 aggregate 层面的检查是**隐式**的：`CompactAcceptedReplacementV4.canonical_evidence_refs` property 使用 `dict.fromkeys` 去重，如果 `accepted_evidence_mapping_refs` 包含重复，equality check 会失败。但建议在修正后的 validator 中**显式**检查 aggregate 唯一性，作为 defense-in-depth。

### Finding 3.2 [MEDIUM] 缺少显式 aggregate 唯一性检查

**当前状态**：修正后的 `_validate_aggregate_boundary_ordered_subset` 只检查 membership（每个 ref 在 boundary 中），不显式检查 aggregate 内部是否有重复 refs。唯一性由 equality check（line 107-109）隐式保证。

**风险**：低。equality check 已经覆盖了此路径。但如果未来有人在 `accepted_evidence_mapping_refs` 的构造路径中绕过 `canonical_evidence_refs` property 直接写入含重复的 tuple，equality check 会捕获。但显式检查可以提供更清晰的错误信息（"aggregate contains duplicate refs" vs "must equal replacement refs union"）。

**建议**：在修正后的 validator 中增加显式 `len(aggregate) != len(set(aggregate))` 检查，或继续保持隐式依赖 equality check。两种方案均可接受，但如果保持隐式，建议在 validator docstring 中说明唯一性由 equality check 保证。

---

## 4. Test Boundary Completeness

### Finding 4.1 [MEDIUM] 测试反例覆盖不足

Correction document 指定的 owner 反例测试：

> boundary为 `E1, E2`，accepted replacement中 `E2` fact在前、`E1` fact在后时可持久化/strict恢复；任何越界ref、重复ref或与replacement union不等仍fail closed。

**缺失的测试边界**：

| 场景 | 是否覆盖 | 说明 |
|------|---------|------|
| E2-fact 在前, E1-fact 在后（反例） | ✅ 已指定 | 核心纠正用例 |
| 正常 boundary 顺序（E1 在前, E2 在后） | ❌ 未指定 | 必须确保修正不破坏正常路径 |
| 3+ facts 任意业务顺序 | ❌ 未指定 | 边界扩大后的鲁棒性 |
| 同一 evidence 被多个 fact 选择（跨 fact 重复 refs） | ❌ 未指定 | aggregate unique union 的去重正确性 |
| retained + new 混合顺序 | ❌ 未指定 | retained 在前、new 在后，retained 的 refs 与 new 的 refs 可能交错 |
| repair path 后 aggregate 重算 | ❌ 未指定 | repair 走完整 1-6 链，aggregate 重新派生 |
| empty aggregate（无 evidence fact 且无 retained fact） | ❌ 未指定 | 边界条件 |
| 越界 ref（不在 request union 中） | ✅ 已指定 | fail closed |
| 重复 ref（aggregate 内重复） | ✅ 已指定 | fail closed |
| aggregate 与 replacement union 不等 | ✅ 已指定 | fail closed |

**建议**：S1 owner test 必须至少增加：
1. **正常 boundary 顺序测试**（确保不回归）
2. **3-fact 非 boundary 顺序测试**（如 E3 在前、E1 在中、E2 在后）
3. **跨 fact 共享 evidence 去重测试**（两个 fact 都选 E1，aggregate 中 E1 的 refs 只出现一次）
4. **repair 后 aggregate 顺序测试**（确保 repair 重新派生 aggregate 不误用旧顺序约束）

---

## 5. Adversarial Failure Pass（对抗性失败分析）

### Scenario A: 模型按 boundary 顺序输出 facts

- Proposal: `evidence_facts = [{support_labels: ["E1"]}, {support_labels: ["E2"]}]`
- Replacement aggregate = `(r1, r2)`
- 修正前：通过（ordinals = (0, 1) = sorted）
- 修正后：通过（membership check 通过，equality check 通过）
- **无回归风险** ✅

### Scenario B: 模型按反 boundary 顺序输出 facts（correction 反例）

- Proposal: `evidence_facts = [{support_labels: ["E2"]}, {support_labels: ["E1"]}]`
- Replacement aggregate = `(r2, r1)`
- 修正前：**拒绝**（ordinals = (1, 0) ≠ (0, 1)）
- 修正后：通过（membership check 通过，equality check 通过）
- **correction 目标场景** ✅

### Scenario C: aggregate 包含越界 ref

- 假设 `accepted_evidence_mapping_refs` 被错误构造为 `(r1, r3)` 其中 r3 不在 boundary 中
- 修正前：拒绝（`r3 not in positions`）
- 修正后：拒绝（membership check 保留）
- **无回归风险** ✅

### Scenario D: aggregate 包含重复 ref

- 假设 `accepted_evidence_mapping_refs = (r1, r1)`
- 修正前：拒绝（equality check: replacement.canonical_evidence_refs = (r1,) ≠ (r1, r1)）
- 修正后：拒绝（equality check 保留）
- **无回归风险** ✅

### Scenario E: 攻击者构造 proposal 使 aggregate 顺序与 boundary 完全不同但每个 fact binding 合法

- 这是 Scenario B 的一般化。每个 fact 的 binding 由 governance 逐 fact 验证，refs 由 boundary entry 机械复制。
- 跨 fact 顺序是 proposal 的业务顺序，不由攻击者"绕过"——它是 accept owner 的合法派生结果。
- **不存在逃逸路径** ✅

### Scenario F: 模型输出 fact 选择多个 evidence materials，每个的 refs 按 boundary 顺序，但跨 fact 顺序任意

- 例如：boundary E1(r1), E2(r2), E3(r3)。Proposal: fact A 选 [E1, E3] → refs = (r1, r3)；fact B 选 [E2] → refs = (r2)
- Aggregate = (r1, r3, r2)
- 修正前：拒绝（ordinals = (0, 2, 1) ≠ sorted）
- 修正后：通过
- 每个 fact 内部 refs 仍按 boundary 顺序（r1 在 r3 前因为 E1 在 E3 前），跨 fact 顺序由 proposal 决定
- **correction 正确覆盖** ✅

---

## 6. Cross-Reference with Accepted Plan

### Finding 6.1 [INFO] 与 accepted plan 的一致性

Accepted plan（`pr-190-f13-evidence-provenance-plan-20260806.md`）line 89-93:

> 该 request union 表示"可选 evidence boundary"，允许包含最终被省略的 prior fact refs；accepted
> aggregate 表示"实际 retained/new facts 的 refs"，因此正确不变量是 accepted aggregate 的每个 ref
> 都属于 request union，而不是二者恒等。accepted aggregate 自身必须 exact 等于 replacement 中逐 fact
> refs 按 fact/entry 顺序的 ordered unique union；不能再强制它遵循跨 fact 的 boundary 全局顺序，因为
> proposal 中 facts 的业务顺序可以与其各自选择的 evidence boundary 顺序不同。

Correction document 的结论与此**完全一致**。Correction document 的本质是将 plan 中已接受的"不能再强制跨 fact 全局顺序"落实到 S1 代码中。

### Finding 6.2 [INFO] Correction document 的 scope 正确

Correction document 明确：
- 这是 S1 persistence owner **内部矛盾修正**（不是扩大业务目标）
- 不新增 schema 字段
- 不增加兼容路径
- 不改变逐 fact binding、kind、non-empty、coverage 或 omit 语义

Scope 判断正确。删除一个 reader 端的过度约束不会产生级联影响——所有 consumer 读取的是 `accepted_replacement`，其语义未变。

---

## 7. Conclusion

### 裁决：`accepted`

**理由**：动机成立（反例真实、当前实现有 bug），owner boundary 分析正确（reader 不应施加 accept owner 未承诺的约束），membership + uniqueness + replacement equality 三个约束联合足够，无逃逸路径。

### 必须修正的 blocking finding

**F2.2 [BLOCKING]**：Design line 3929-3931 的 `ordered-subset校验` 与 line 3471 的 `不得强制...全局顺序` 直接矛盾。必须在 S0/S1 中将 line 3930-3931 的 `accepted aggregate union与 request-boundary ordered-subset校验` 改为 `accepted aggregate union 对 request-boundary 的 unique membership/subset 校验`，与 line 3471 保持一致。

### 建议确认的 medium findings

**F3.2 [MEDIUM]**：建议在 `_validate_aggregate_boundary_ordered_subset` 修正后增加显式 aggregate 唯一性检查，或至少在 docstring 中注明唯一性由 equality check 隐式保证。

**F4.1 [MEDIUM]**：S1 owner test 必须至少增加：正常 boundary 顺序测试、3+ facts 非 boundary 顺序测试、跨 fact 共享 evidence 去重测试、repair 后 aggregate 重算测试。当前 correction document 只指定了一个反例测试。

### 无分歧项

- replacement aggregate 按 fact/entry 顺序的 ordered unique union 公式**不变**
- 逐 fact strict binding 规则**不变**
- membership check（越界拒绝）**不变**
- replacement equality check（aggregate 与逐 fact union 等式）**不变**
- 删除的只是跨 fact boundary 全局顺序约束——这个约束从来不是 accept owner 的承诺

---

## Re-review: F2.2 / F3.2 / F4.1 修正复核

**日期**: 2026-08-06

### F2.2 [BLOCKING → RESOLVED] Design reactive 段已同步修正

**原 finding**: `design.md:3930-3931` 仍写 `ordered-subset校验`，与 `design.md:3471` 矛盾。

**复核证据**: `design.md:3929-3931` 已改为：

> accepted aggregate union与 request-boundary unique membership / subset校验；不得对跨 fact aggregate施加boundary全局顺序。

与 line 3471 的"不得强制 aggregate 遵循跨 fact 的 boundary 全局顺序"一致。矛盾消除。

**裁决**: ✅ resolved。

### F3.2 [MEDIUM → RESOLVED] 显式唯一性已纳入要求

**原 finding**: 唯一性由 equality check 隐式保证，建议显式检查。

**复核证据**: correction document line 21 已明确要求：

> 把 `_validate_aggregate_boundary_ordered_subset` 收敛并重命名为 request-boundary unique membership/subset validation；显式拒绝aggregate重复ref

显式唯一性检查从建议升级为要求。

**裁决**: ✅ resolved。

### F4.1 [MEDIUM → RESOLVED] Owner test 矩阵已扩充

**原 finding**: 只指定一个反例测试（E2→E1），缺少正常顺序、3+ facts、去重、retained+new 交错、repair、empty aggregate 等用例。

**复核证据**: correction document line 22 已扩充为完整矩阵：

> owner tests覆盖：正常`E1→E2`；反序`E2→E1`；三条fact的任意业务顺序；跨fact共享evidence时aggregate稳定去重；retained+new refs交错；repair后从新proposal/replacement完整重算；无EvidenceFact时empty aggregate合法。

覆盖我原 review 列出的全部缺口。

**裁决**: ✅ resolved。

### Re-review 结论

三条 finding 全部已由 correction document 修正：

| Finding | 原级别 | 状态 |
|---------|--------|------|
| F2.2 design reactive 段矛盾 | BLOCKING | ✅ resolved — design line 3930-3931 改为 unique membership/subset |
| F3.2 缺少显式唯一性检查 | MEDIUM | ✅ resolved — correction 要求显式拒绝重复 ref |
| F4.1 测试矩阵不足 | MEDIUM | ✅ resolved — 扩充为 7 类 owner test |

**最终裁决: `accepted`，无残余 blocking/medium finding。**

