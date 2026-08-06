# PR 190 F13 S1 Aggregate Order Correction — AgentMiMo Review

- Date: 2026-08-06
- Reviewer: AgentMiMo
- Scope: `docs/gateflow/pr-190-f13-s1-aggregate-order-correction-20260806.md` + `docs/host/design.md` diff + `dayu/host/compact_payload.py` current implementation

---

## F1. E1/E2 反例有效性

**Verdict: PASS**

gateflow 声称：设 boundary 顺序为 `E1, E2`，模型按业务顺序先输出只选 E2 的 fact、再输出只选 E1 的 fact，则 replacement aggregate 为 `(E2-ref, E1-ref)`，但 request union 为 `(E1-ref, E2-ref)`，当前 validation 会拒绝。

代码验证：

- `derive_compact_accepted_replacement_v4` (compaction.py:1691-1704) 对 new fact 按 proposal 顺序 append，每个 fact 的 refs 按 boundary entry 顺序收集。当 proposal 中 E2-fact 在 E1-fact 之前时，replacement.evidence_facts = `(FactE2(refs=(E2-ref,)), FactE1(refs=(E1-ref,)))`。
- `CompactAcceptedReplacementV4.canonical_evidence_refs` (compaction.py:1600-1606) 按 fact 顺序 flatten + dedup → `(E2-ref, E1-ref)`。
- `compact_payload_json_vnext` (compact_payload.py:830-832) 持久化 `replacement.canonical_evidence_refs` → 写入 `(E2-ref, E1-ref)`。
- `_validate_aggregate_boundary_ordered_subset` (compact_payload.py:501-528) 构建 boundary 位置 `{E1-ref: 0, E2-ref: 1}`，aggregate ordinals = `(1, 0)`，`sorted(ordinals) = (0, 1)`，`1 != 0` → `ValueError`。

反例成立。该 payload 在 Context Governance accept 阶段合法（逐 fact binding 均通过），但在 durable strict parse 阶段被拒绝，违反 accept-before-durable 边界。

**Blocking: 否**（反例本身正确，属于 finding 确认而非阻塞项）

---

## F2. 逐 fact 真源归属

**Verdict: PASS**

gateflow 声称：逐 fact atom 是 evidence provenance 真源，replacement aggregate 只是 projection。

代码验证：

- `CompactAcceptedEvidenceFactV4` (compaction.py:1501-1553) 每个 atom 有独立 `canonical_evidence_refs`，由 `derive_compact_accepted_replacement_v4` 从 boundary entry 唯一派生。
- `CompactAcceptedReplacementV4.canonical_evidence_refs` (compaction.py:1592-1606) 是 computed property，按 fact 顺序 flatten，不是独立存储。
- 设计 line 3471（新）："replacement aggregate evidence refs 必须 exact 等于逐 fact refs按 fact / entry顺序的 ordered unique union；它只是验证过的 projection，不是逐 fact事实的 owner。"

归属正确。aggregate 是派生值，逐 fact refs 是真源。

**Blocking: 否**

---

## F3. Aggregate Exact Union 不变量

**Verdict: PASS**

gateflow 声称：S1 不改变 exact-union 约束。

代码验证：

- `ContextCompactedSemanticPayload.__post_init__` (compact_payload.py:107-112)：
  ```python
  if self.accepted_evidence_mapping_refs != (
      self.accepted_replacement.canonical_evidence_refs
  ):
      raise ValueError(
          "accepted_evidence_mapping_refs must equal replacement refs union"
      )
  ```
  该检查在 `_validate_aggregate_boundary_ordered_subset` 之前执行，确保 persisted aggregate 严格等于 replacement 派生的 aggregate。

- `validate_compact_proposal_replacement_binding_v4` (compaction.py:1877-1898) 确保 replacement 等于 `derive_compact_accepted_replacement_v4(source_boundary, proposal)` 的输出。

- 设计 line 3517（新）："最后一项必须strict等于replacement逐fact refs的ordered unique union，只是aggregate projection，不是fact provenance真源。"

exact-union 不变量由两个独立检查保证：(1) persisted aggregate == replacement.canonical_evidence_refs；(2) replacement == derive(boundary, proposal)。S1 修正不触及这两个检查。

**Blocking: 否**

---

## F4. Request Membership 边界

**Verdict: PASS**

gateflow 声称：删除"跨 fact aggregate 必须按 request boundary 全局单调"的 reader 约束，改为 membership 检查。

设计 diff 验证（三处一致性）：

1. Line 3471 旧："accepted aggregate 必须是 `CompactionRequest.canonical_evidence_refs` 的有序子集" → 新："accepted aggregate 的每个 ref 都必须属于 `CompactionRequest.canonical_evidence_refs` 且 aggregate 自身唯一；不得强制 aggregate 遵循跨 fact 的 boundary 全局顺序"
2. Line 3517 旧："aggregate-union与 request-boundary ordered-subset关系" → 新："aggregate-union与 request-boundary membership关系"
3. Line 3931 旧："ordered-subset校验" → 新："unique membership / subset校验；不得对跨 fact aggregate施加boundary全局顺序"

三处修改语义一致：从 ordered-subset 放宽为 membership + uniqueness。

代码验证：

- 每个 fact 的 refs 已由 `derive_compact_accepted_replacement_v4` 从 boundary entry 派生，天然只包含 boundary 内的 ref（compaction.py:1694-1696：`if entry.source_label in support_labels: refs.extend(entry.canonical_evidence_refs)`）。
- retained fact 的 refs 直接复制 boundary entry 的 refs（compaction.py:1686）。
- 因此 aggregate 作为 fact refs 的 flatten，天然只包含 boundary 内的 ref。membership 检查是防御性的，exact-union 检查已保证一致性。

但需注意：设计同时要求"aggregate 自身唯一"。当前 `CompactAcceptedReplacementV4.canonical_evidence_refs` 使用 `dict.fromkeys` 去重（compaction.py:1600-1606），天然唯一。`_validate_aggregate_boundary_ordered_subset` 中 `available` 也使用 `dict.fromkeys` 去重（compact_payload.py:511-517）。S1 实现需确保新的 membership 检查保留 uniqueness 断言（当前实现的 subset 检查隐含 uniqueness，因为 `any(ref not in positions ...)` 不检查重复——但如果 aggregate 有重复 ref，`positions` lookup 不会拒绝。需确认 exact-union 检查已覆盖 uniqueness，因为 `replacement.canonical_evidence_refs` 天然去重）。

**Blocking: 否**（exact-union 检查已保证 uniqueness，membership 检查是防御性补充）

---

## F5. Accept-before-Durable 边界

**Verdict: PASS**

gateflow 声称：当前实现让 Context Governance 已接受的 proposal 在 durable payload 构造阶段才失败。

代码验证：

- Context Governance 调用 `derive_compact_accepted_replacement_v4` 构造 replacement，调用 `CompactAcceptedTruthV4.__post_init__` 验证（compaction.py:2513-2546）。该阶段不检查 aggregate boundary order。
- 随后 `compact_payload_json_vnext` 生成 artifact JSON（compact_payload.py:791-834），持久化 `replacement.canonical_evidence_refs`。
- 恢复时 `parse_context_compacted_semantic_payload` 构造 `ContextCompactedSemanticPayload`，其 `__post_init__` 调用 `_validate_aggregate_boundary_ordered_subset`（compact_payload.py:126）。
- 该验证在 accept 之后、durable restore 时执行，导致已 accept 的 payload 在 restore 时被拒绝。

S1 修正将 validation 从 boundary-order monotonicity 放宽为 membership，消除 accept 与 durable 之间的不一致。

**Blocking: 否**

---

## F6. 设计 diff 内部一致性

**Verdict: PASS**

设计 diff 修改三处，语义一致：

| 位置 | 旧约束 | 新约束 | 一致性 |
|------|--------|--------|--------|
| L3471 | "有序子集" | "每个 ref 属于 request union 且唯一；不强制全局顺序" | ✓ |
| L3517 | "ordered-subset关系" | "membership关系" | ✓ |
| L3931 | "ordered-subset校验" | "unique membership / subset校验；不得施加全局顺序" | ✓ |

新增约束"每条 fact 内部 refs 仍须按自己的 canonical selection / boundary 顺序"（L3471）与既有逐 fact binding 检查（L3469）一致：每个 fact 的 refs 由 `derive_compact_accepted_replacement_v4` 从 boundary entry 顺序派生，天然满足。

**Blocking: 否**

---

## F7. 是否存在更小且一致方案

**Verdict: PASS — S1 方案已是最小修正**

备选方案分析：

**方案 A（当前 S1）**：放宽 validation 为 membership + uniqueness，保持 derivation 不变。
- 修改点：`_validate_aggregate_boundary_ordered_subset` 一个函数。
- 影响：仅 strict parser 的防御性检查。
- 风险：无。exact-union 检查已保证 aggregate == replacement refs union。

**方案 B**：修改 `derive_compact_accepted_replacement_v4` 使 new fact 的 refs 按 boundary 顺序排列（而非 proposal 顺序）。
- 问题：这会改变 `replacement.evidence_facts` 的 ordering 语义。设计明确说"replacement aggregate 只是按 replacement fact业务顺序派生的 projection"（gateflow L16）。改变 derivation 会破坏 fact-order = proposal-order 的不变量。
- 结论：不可行。

**方案 C**：同时修改 derivation 和 validation，使 aggregate 始终按 boundary 顺序。
- 问题：需要改变 replacement 的 ordering 语义，与设计意图矛盾。
- 结论：不可行，且比 S1 更大。

**方案 D**：删除 `_validate_aggregate_boundary_ordered_subset`，仅保留 exact-union 检查。
- 问题：丢失 membership 防御性检查。虽然 derivation 天然保证 membership，但 defense-in-depth 有价值。
- 结论：比 S1 更小但丢失防御层。

S1 是最优选择：最小修改（一个函数）、保持 defense-in-depth、不改变任何 derivation 语义。

**Blocking: 否**

---

## F8. S1 实现边界确认

**Verdict: PASS**

gateflow 声称："S1 strict payload parser 把 `_validate_aggregate_boundary_ordered_subset` 收敛为 request-boundary unique membership/subset validation"

当前实现（compact_payload.py:501-528）：

```python
def _validate_aggregate_boundary_ordered_subset(
    semantics: ContextCompactedSemanticPayload,
) -> None:
    available = tuple(
        dict.fromkeys(
            ref
            for entry in semantics.source_boundary
            for ref in entry.canonical_evidence_refs
        )
    )
    positions = {ref: index for index, ref in enumerate(available)}
    aggregate = semantics.accepted_evidence_mapping_refs
    if any(ref not in positions for ref in aggregate):
        raise ValueError(
            "accepted_evidence_mapping_refs must be boundary evidence subset"
        )
    ordinals = tuple(positions[ref] for ref in aggregate)
    if ordinals != tuple(sorted(ordinals)):
        raise ValueError(
            "accepted_evidence_mapping_refs must follow boundary evidence order"
        )
```

S1 需要：
1. 删除 ordinals 排序检查（L524-528）。
2. 保留 membership 检查（L520-523）。
3. 可选：显式检查 aggregate 内 uniqueness（当前由 exact-union 隐含）。

实现边界明确，不扩大 scope。

**Blocking: 否**

---

## Final Verdict

**ACCEPTED — 8/8 PASS, 0 blocking**

gateflow `pr-190-f13-s1-aggregate-order-correction-20260806.md` 的诊断和修正方案正确：

1. E1/E2 反例成立，当前 validation 在 accept-before-durable 边界上存在逻辑矛盾。
2. 设计 diff 三处修改语义一致，从 ordered-subset 放宽为 membership + uniqueness。
3. S1 是最小修正方案：仅修改一个防御性 validation 函数，不改变 derivation 语义。
4. exact-union 不变量由独立检查保证，不受 S1 影响。
5. 逐 fact 真源归属、request membership 边界均正确。

建议实现时补充反例测试：boundary 为 `(E1, E2)`，accepted replacement 中 E2 fact 在前、E1 fact 在后时 payload 可通过 strict parse。
