# Code Re-Review — AgentDS

## Verdict

**ACCEPTED** — 六项 accepted findings（C1/M1/M2/M3/D2/D3）全部正确修复，rejected DS F1 未被采纳，无新增 schema/cursor/fallback 或 scope creep。

## Gate context

- gate: `code review` re-review（窄）
- base: `b222b8b064f096d899a9de708e45cd1fb6e732e6`
- adjudication: `docs/gateflow/pr-190-f14-code-review-adjudication-20260806.md`
- updated implementation: `docs/gateflow/pr-190-f14-s1-implementation-20260806.md`
- prior review: `docs/reviews/pr-190-f14-code-review-ds-20260806.md`
- output: `docs/reviews/pr-190-f14-code-rereview-ds-20260806.md`

## Evidence per finding

### C1 — `run_id=None` metadata proof

- **生产修复位置**: `dayu/host/compact_material.py:2756-2760`
- **修复内容**: `group_consumed` 新增首条件 `row.run_id is not None`；只有具备非空 Run identity 的 group 才能在 metadata 阶段被 user anchor proof 跳过。
- **直接证据（代码）**:
  ```python
  group_consumed = (
      row.run_id is not None          # ← C1 fix
      and len(user_anchors) == 1
      and user_anchors[0].event_id in consumed
  )
  ```
- **行内注释**: L2754-2755 "非空 run_id 是关联 whole-group selector proof 的最小 identity；缺失时必须保留 row 给 typed projector / _atomic_material_units fail closed。"
- **测试**: `test_pre_dispatch_consumed_user_without_run_id_cannot_prove_atomic_group`（L3499-3577）
  - 构造 `run_id=None` 的 `USER_INPUT_ACCEPTED` row，其 `event_id` 已写入 accepted compact 的 `compacted_source_refs`
  - 旧实现：`1 failed` — `Failed: DID NOT RAISE HostDurableError`（metadata fast path 错误跳过）
  - 新实现：`pytest.raises(HostDurableError, match="unconsumed material atomic grouping is invalid")` —— row 进入 typed projector，`_atomic_material_units` 因缺少 `turn_group_id` 抛出 `ValueError` → `HostDurableError`
- **判定**: ✓ 通过。修复精确对应 adjudication 要求：只收紧 metadata proof，不新增 typed/atomic 逻辑；测试包含 red→green 证据链。

### M1 — 三轮 frontier 单调、exact-once 与 canonical order

- **测试位置**: `tests/host/test_compact_material.py:3199-3403`
- **测试结构**:
  1. L3244-3267: 每轮追加 source user/answer/evidence（完整 atomic Run group）→ 累积到 `all_material_refs`
  2. L3275-3295: 每轮 compact trigger 作为 `current_input_ref`，accepted terminal 的 `compacted_source_refs` 包含本轮及之前所有待消费 source refs
  3. L3303-3332: 每轮追加 suffix user/answer/evidence（未消费 raw group）
  4. L3371-3397: **逐阶段断言**（三轮各一次 `build_pre_dispatch_compact_material_view`）：
     - L3390: `post_compact_delta_start_sequence == expected_frontier`（trigger 的 event_sequence）
     - L3391: `actual_suffix_refs == expected_suffix_refs`（exact 匹配期望 suffix）
     - L3392: `block_order == tuple(sorted(block_order))`（按 `(event_sequence, event_sub_index)` 保持 canonical order）
     - L3393: `len(actual_suffix_refs) == len(set(actual_suffix_refs))`（suffix 内无 duplicate）
     - L3394: `set(consumed_refs).isdisjoint(actual_suffix_refs)`（consumed ∩ suffix = ∅）
     - L3396: `set(consumed_refs) | set(actual_suffix_refs) == set(eligible_refs)`（并集精确覆盖）
     - L3397: `len(consumed_refs) + len(actual_suffix_refs) == len(eligible_refs)`（exact-once, no-gap）
  5. L3399-3403: **三轮 frontier 严格单调递增**
- **判定**: ✓ 通过。不使用偶然 sequence 常量，所有期望值从实际 append row 取得。覆盖 accepted plan A.3 全部要求。

### M2 — correction aging → second replacement → reconnect 同源

- **测试位置**: `tests/host/test_run_input_builder.py:3852-4255`
- **测试结构**（逐段核验）:

  **Phase 1 — 初始 fixture（L3882-3928）**:
  - old口径 Run：user + answer + 真实 `_append_canonical_tool_result_for_memory`（含 `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` + production `AcceptedEvidenceEnvelope`）
  - bridge Run：user + answer
  - correction Run：user + answer + 真实 tool result（不同 evidence ref）
  - old evidence ref: `evidence:event-aging-old-evidence`
  - correction evidence ref: `evidence:event-aging-correction-evidence` ← **二者不相等**

  **Phase 2 — 首次压缩（L3929-4018）**:
  - First selector（`selected_recent_window_turn_floor=2`）：
    - old group → selected（L3971-3975）
    - bridge + correction groups → `protected_recent_raw_floor`（L3976-3981）
  - First accepted terminal：`EvidenceFact(claim="Old revenue was 100.", canonical_evidence_refs=(old_evidence_ref,))`（L4000-4005）
  - Memory projection → first_snapshot：1 fact, old_claim, old_ref, provenance.event_id = `first_compact_event_id`（L4006-4009）
  - First selected_recent_window 包含 correction user/answer/evidence refs（L4014-4018）

  **Phase 3 — 四轮 aging（L4020-4027）**: 追加 4 组 newer user + answer → correction 退出 floor（`turn_floor=2` 只保护最新 2 组）

  **Phase 4 — 第二次压缩（L4028-4189）**:
  - Second selector：correction + bridge + newer-1 + newer-2 → selected；newer-3 + newer-4 → `protected_recent_raw_floor`（L4052-4068）
  - Second accepted terminal：
    - `retained_previous_evidence_fact_labels == ()`（L4141）← 不 retain
    - `EvidenceFact(claim="Corrected revenue was 120.", canonical_evidence_refs=(correction_evidence_ref,))`（L4142-4148）
    - `old_evidence_ref not in second_replacement_fact.canonical_evidence_refs`（L4148）← 旧 ref 未混入新 fact
  - **Immutable first terminal re-read**（L4115-4121）:
    - `immutable_first_semantics == first_semantics`（L4137）← 旧 terminal 不变
    - `immutable_first_semantics.accepted_replacement.evidence_facts[0].canonical_evidence_refs == (old_evidence_ref,)`（L4138-4140）← 旧 fact 仍绑定旧 ref
  - Second Memory snapshot：1 fact, correction_claim, correction_ref, provenance.event_id = `second_compact_event_id`（L4176-4181）
  - Second selected_recent_window **不含** correction user/answer refs（L4182-4189）← 已被消费

  **Phase 5 — 普通 Run 与 reconnect（L4191-4255）**:
  - Final material view：correction group **不在** material_blocks 中（L4215-4218）
  - Reopen durable store → Memory 仍保持：
    - `summary_text == correction_summary`（L4239）
    - 1 fact: correction_claim, correction_ref, provenance = `second_compact_event_id`（L4244-4248）
  - Reconnected RunInput content（L4236-4255）：
    - `correction_summary` 出现 **恰好一次**（L4249）
    - `correction_fact_claim` 出现 **恰好一次**（L4250）
    - `old_fact_claim` **全部不存在**（L4251）
    - raw `correction_user_text` / `correction_answer_text` / `correction_evidence_text` **全部不存在**（L4252-4254）
    - current input anchor 作为最后一条 message 保留（L4255）

- **判定**: ✓ 通过。
  - 使用真实 production `AcceptedEvidenceEnvelope`、`TOOL_CALL_REQUESTED`/`TOOL_RESULT_ACCEPTED`、`select_compact_segment`、`catch_up_conversation_memory_projection`、`build_pre_dispatch_compact_material_view`、reopen durable store、durable memory snapshot reader、ordinary RunInput builder——无 mock/fake 替代生产 owner。
  - 旧/新 evidence ref 不相等 ✓
  - 旧 terminal immutable provenance ✓
  - 新 fact 不 retain、不借用旧 ref ✓
  - 四轮 aging 后 correction 真正退出 recent window ✓
  - Reopen Memory / ordinary RunInput 只由正式 replacement 证明 ✓
  - 无 UI fallback、无 fixture 默认 ref ✓
  - 21.7% 无证据约束未伪造 ✓

### M3 — design 校验时机表述

- **修复位置**: `docs/host/design.md` L3896 行
- **旧文本**: "Compact material data block build 启动前必须校验..."
- **新文本**: "Compact material data block build**期间**必须分阶段完成strict proof：读取accepted chain时，`_accepted_compact_chain_before_current_input` / `_validate_accepted_compact_entry_references`校验...；进入material projection后，`_conservative_unconsumed_row_start_sequence` / `_unconsumed_atomic_material_blocks`再证明..."
- **判定**: ✓ 通过。明确区分两个 proof 阶段及各阶段的 owner 函数。

### D2 — user-anchor proof 与 selector atomicity 的代码级 cross-reference

- **生产修复位置**: `dayu/host/compact_material.py:2716-2723`（docstring）、L2754-2755（行内注释）
- **docstring 新增**（L2720-2723）: "完整 group 的语义 owner 是 material selector 生成的 `turn_group_memberships_for_material_blocks`；本 helper 只做 metadata-first 保守裁剪，最终 exact all-or-none / prefix proof 必须复用 `_atomic_material_units`，不能把 user ref 命中本身升级成 atomic proof。"
- **行内注释**（L2754-2755）: "非空 run_id 是关联 whole-group selector proof 的最小 identity；缺失时必须保留 row 给 typed projector / _atomic_material_units fail closed。"
- **design.md 同步**: L3523 行 "只用具有非空`run_id`的完整Run group及其唯一canonical user anchor证明可跳过的已消费prefix；`run_id=None`、缺失或重复user anchor均保守进入typed projection，再复用atomic unit all-or-none与prefix proof"
- **README.md 同步**: L433 行 "只用具有非空`run_id`的完整Run group及其唯一canonical user anchor证明已消费prefix；`run_id=None`、缺失或重复user anchor均保守进入typed projection，再执行atomic all-or-none / prefix校验"
- **判定**: ✓ 通过。code + design + README 三处同步。

### D3 — `_accepted_compacted_source_refs` docstring raises 格式

- **修复位置**: `dayu/host/compact_material.py:2374-2381`
- **修复内容**: 删除 `:raises Exception: 不主动抛出异常。`
- **判定**: ✓ 通过。docstring 现在只有 `:param` 和 `:returns`，符合规范。

### Rejected DS F1 — 确认未采纳

- **验证位置**: `dayu/host/compact_material.py:2768`
- **当前代码**: `first_unconsumed_sequence = group[0].event_sequence`
- **判定**: ✓ 确认。`group[0].event_sequence` 未被改为 `min(...)`。adjudication 的拒绝理由（SQL `ORDER BY event_sequence ASC` 保证 canonical order，`grouped` 单次 append 保持顺序）成立。

### Scope compliance — 确认无新增 schema/cursor/fallback

- **新表/字段**: 无（`git diff` 无 schema migration）
- **新 cursor**: 无（`git diff` 无新增 cursor 变量或持久化 cursor）
- **新 fallback**: 无（`git diff` 无新增 fallback 路径或兼容分支）
- **新 public contract**: 无
- **Engine 修改**: 无（`git diff --exit-code -- dayu/engine docs/engine` 确认）
- **Prompt/config/Oracle 修改**: 无（implementation record L239 确认）

## Final check

| Finding | Verdict | Evidence |
|---------|---------|----------|
| C1 | ✓ ACCEPTED | `group_consumed` 新增 `row.run_id is not None`；单测 red→green |
| M1 | ✓ ACCEPTED | 三轮逐阶段 frontier/order/exact-once/no-gap 断言 |
| M2 | ✓ ACCEPTED | 完整 aging→replacement→reconnect 链条，production owner 复用 |
| M3 | ✓ ACCEPTED | "build期间" + 两阶段函数引用 |
| D2 | ✓ ACCEPTED | docstring + 行内注释 + design + README 四处同步 |
| D3 | ✓ ACCEPTED | 删除错误 `:raises Exception:` 行 |
| DS F1 (rejected) | ✓ NOT ADOPTED | `group[0].event_sequence` 未改为 `min()` |
| Scope creep | ✓ NONE | 无新 schema/cursor/fallback/public contract |

## Open Questions

无。

## Residual Risk

- M2 测试使用 `_memory_policy()`（`selected_recent_window_turn_floor=2`）——这是 test helper policy，非生产 `default_memory_projection_policy()`。差异在于 item/char caps 的具体数值，不影响 floor 语义和 aging 逻辑的正确性验证。若生产 policy 的 floor 值不同，aging 轮数需相应调整，但 consumption frontier 的 owner 逻辑不变。
- Real production CLI observation 仍未执行——属于 Controller 后续 formal observation gate，不在本 re-review scope。

---

**Reviewer**: AgentDS
**Timestamp**: 2026-08-07 (based on 2026-08-06 adjudication + updated implementation)
**Base**: b222b8b064f096d899a9de708e45cd1fb6e732e6
**Verdict**: ACCEPTED
