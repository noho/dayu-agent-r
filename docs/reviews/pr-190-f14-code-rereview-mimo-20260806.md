# Code Re-Review

## Scope

- Mode: current changes (narrow re-review)
- Branch: `codex/interactive-oracle`
- Base: `b222b8b064f096d899a9de708e45cd1fb6e732e6`
- Adjudication: `docs/gateflow/pr-190-f14-code-review-adjudication-20260806.md`
- Implementation artifact: `docs/gateflow/pr-190-f14-s1-implementation-20260806.md`
- Output file: `docs/reviews/pr-190-f14-code-rereview-mimo-20260806.md`
- Re-review scope: C1 / M1 / M2 / M3 / D2 / D3 六项 accepted findings 的修复核验
- Not in scope: rejected AgentDS F1（确认未采纳）、未修改的 production logic

## Conclusion

**ACCEPTED**

六项 accepted findings 全部按 adjudication 要求修复，直接证据完整。未新增 schema / cursor / fallback / public contract。未采纳 rejected DS F1。

## Finding-by-finding verification

### C1 — `run_id=None` metadata proof — ✅ 修复确认

- **Production change**: `_conservative_unconsumed_row_start_sequence` 行 2756-2760，`group_consumed` 新增 `row.run_id is not None` 作为第一条件
- **行内注释**: 行 2754-2755，说明非空 run_id 是关联 whole-group selector proof 的最小 identity
- **Test**: `test_pre_dispatch_consumed_user_without_run_id_cannot_prove_atomic_group`（行 3499-3577）
  - 构造 `run_id=None` 的真实 `USER_INPUT_ACCEPTED` row，其 event_id 在 accepted `compacted_source_refs` 中
  - 期望 `HostDurableError("unconsumed material atomic grouping is invalid")`
  - 逻辑链：`run_id=None` → `group_consumed = False`（因 `row.run_id is not None` 为 False）→ row 进入 typed projector → `_atomic_material_units` 拒绝缺失 `turn_group_id`
- **Red evidence**: implementation doc 记录旧实现 `Failed: DID NOT RAISE <class 'dayu.host.durable.errors.HostDurableError'>`
- **验证**: focused test `1 passed`

### M1 — 三轮 frontier owner proof — ✅ 修复确认

- **Test rewrite**: `test_pre_dispatch_cumulative_accepted_chain_advances_only_complete_groups`（行 3199-3403）
  - 从 2 轮扩展为 3 轮（`range(1, 4)`）
  - 每轮构造真实 user / answer / evidence atomic group + accepted terminal + suffix group
  - 每阶段显式断言：
    1. `view.post_compact_delta_start_sequence == expected_frontier` — frontier 绝对值
    2. `actual_suffix_refs == expected_suffix_refs` — exact suffix refs
    3. `block_order == tuple(sorted(block_order))` — canonical order
    4. `len(actual_suffix_refs) == len(set(actual_suffix_refs))` — no duplicate
    5. `set(consumed_refs).isdisjoint(actual_suffix_refs)` — consumed/suffix disjoint
    6. `set(consumed_refs) | set(actual_suffix_refs) == set(eligible_refs)` — exact partition
    7. `len(consumed_refs) + len(actual_suffix_refs) == len(eligible_refs)` — exact-once
  - 最终显式单调性断言：`all(earlier < later for earlier, later in zip(observed_frontiers, observed_frontiers[1:]))`（行 3399-3403）
- **不固化 sequence 常量**: frontier 从实际 append row 的 `event_sequence` 取得
- **验证**: focused test `1 passed`

### M2 — correction aging / second replacement / reconnect — ✅ 修复确认

- **Test**: `test_correction_ages_into_second_accepted_replacement_and_reconnects_from_memory`（行 3852-4255）
- **Real old/new AcceptedEvidenceEnvelope**:
  - 旧 evidence: `old_evidence_ref = "evidence:event-aging-old-evidence"`，通过 `_append_canonical_tool_result_for_memory` 写入真实 `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` + production `AcceptedEvidenceEnvelope`
  - 新 evidence: `correction_evidence_ref = "evidence:event-aging-correction-evidence"`，同上
  - 二者不相等，无 ref 借用
- **Old/new EvidenceFact exact refs**:
  - 首 terminal: `evidence_facts[0].canonical_evidence_refs == (old_evidence_ref,)`（行 4003-4005）
  - 第二 terminal: `second_replacement_fact.canonical_evidence_refs == (correction_evidence_ref,)`（行 4145-4147）
  - `old_evidence_ref not in second_replacement_fact.canonical_evidence_refs`（行 4148）
  - `retained_previous_evidence_fact_labels == ()`（行 4141），新 fact 不 retain 旧 fact
- **Old terminal immutable provenance**:
  - 第二 terminal 提交后重新读取首 terminal：`immutable_first_semantics == first_semantics`（行 4137）
  - 旧 fact 仍绑定旧 ref：`immutable_first_semantics.accepted_replacement.evidence_facts[0].canonical_evidence_refs == (old_evidence_ref,)`（行 4138-4140）
- **四轮 aging 后 raw correction 退出 recent window**:
  - 首轮：correction user/answer/evidence 在 selected recent window（行 4014-4018）
  - 追加 4 轮 newer groups（行 4020-4027）
  - 第二轮 selector：correction blocks 被选入 compact（行 4057-4062），最新 2 组 newer groups 标为 `protected_recent_raw_floor`（行 4063-4068）
  - 第二 Memory snapshot：correction user/answer 不在 selected recent window（行 4182-4189）
- **Reopen Memory / ordinary RunInput 只由正式 replacement 证明**:
  - 关闭重开 SQLite/artifact store（行 4224）
  - reconnected Memory: `reconnected_facts[0].claim_text == correction_fact_claim`（行 4245）
  - `reconnected_facts[0].evidence_refs == (correction_evidence_ref,)`（行 4246）
  - `old_evidence_ref not in reconnected_facts[0].evidence_refs`（行 4247）
  - `reconnected_facts[0].provenance.event_id == second_compact_event_id`（行 4248）
  - ordinary RunInput: `correction_summary` 出现 1 次（行 4249），`correction_fact_claim` 出现 1 次（行 4250）
  - raw correction 不出现：`old_fact_claim`、`correction_user_text`、`correction_answer_text`、`correction_evidence_text` 均不在 contents 中（行 4251-4254）
  - material view 不含 correction raw group：`all(block.turn_group_id != correction_run_id for block in final_material_view.material_blocks)`（行 4215-4218）
  - protected raw frontier 保留：`{"run-aging-newer-3", "run-aging-newer-4"}.issubset(...)`（行 4219-4221）
- **验证**: focused test `1 passed`

### M3 — design 校验时机表述 — ✅ 修复确认

- **变更**: `docs/host/design.md` diff 中 "build 启动前必须校验" 改为 "build期间必须分阶段完成strict proof"
- **分阶段描述**: "读取accepted chain时...校验...exact回指；进入material projection后...再证明material coverage frontier...一致"
- **验证**: 文本审查确认

### D2 — user-anchor proof 与 selector atomicity cross-reference — ✅ 修复确认

- **Docstring**: `_conservative_unconsumed_row_start_sequence` 行 2717-2725，明确 "完整 group 的语义 owner 是 material selector 生成的 `turn_group_memberships_for_material_blocks`；本 helper 只做 metadata-first 保守裁剪，最终 exact all-or-none / prefix proof 必须复用 `_atomic_material_units`"
- **行内注释**: 行 2754-2755，"非空 run_id 是关联 whole-group selector proof 的最小 identity；缺失时必须保留 row 给 typed projector / `_atomic_material_units` fail closed"
- **验证**: 代码审查确认

### D3 — 纯转换 helper raises docstring — ✅ 修复确认

- **变更**: `_accepted_compacted_source_refs`（行 2374-2389）删除了 `:raises Exception: 不主动抛出异常。`
- **当前 docstring**: 只有 `:param entries:` 和 `:returns:`，符合项目规范
- **验证**: 代码审查确认

## Rejected findings verification

### AgentDS F1 — 确认未采纳

- `group[0].event_sequence` 未改为 `min()`，diff 中无 `min(` 匹配
- `_post_compact_delta_rows` 的 SQL `ORDER BY event_sequence ASC` 保证 tuple 顺序，`group[0]` 机械等于 minimum

## Schema / contract / cursor verification

- diff 中无新 `CREATE TABLE`、`ALTER TABLE`、新 public export、新 durable cursor 或新 fallback/compat shim
- `memory_snapshot_cursor=None` 唯一匹配是 `_sorted_material_blocks` 的既有参数，非新增 cursor
- `latest_compacted_event_id/sequence` 继续只表示 provenance，未改作 consumption truth
- `represented_evidence_refs` 继续只表示 latest replacement evidence refs，未改作 cumulative

## Validation

- 5 focused fix tests: `5 passed in 0.54s`
- affected union: `343 passed in 3.98s`
- pyright: `0 errors, 0 warnings, 0 informations`

## Residual Risk

- FY2024/2025 evidence ownership 完整分离需 production CLI observation（plan B.2，不在本 gate scope）
- 全仓 frozen publication manifest 4 项既有 failure（范围外 baseline）
