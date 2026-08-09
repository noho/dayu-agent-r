# Code Review

## Scope

- Mode: current changes (aggregate deepreview)
- Branch: codex/interactive-oracle
- Base: b222b8b064f096d899a9de708e45cd1fb6e732e6 (accepted plan commit)
- Implementation: 6eb41ac1 (fix(host): derive compact frontier from accepted coverage)
- Output file: docs/reviews/pr-190-f14-aggregate-deepreview-mimo-20260807.md
- Included scope: 14 files changed, 3419 insertions(+), 329 deletions(-)
  - `dayu/host/compact_material.py` (production)
  - `dayu/host/README.md` (docs)
  - `docs/host/design.md` (docs)
  - `tests/host/test_compact_material.py` (tests)
  - `tests/host/test_dispatch_scheduler.py` (tests)
  - `tests/host/test_run_input_builder.py` (tests)
  - 8 review/adjudication artifacts in `docs/reviews/` and `docs/gateflow/active/pr-190/`
- Excluded scope: none
- Parallel review coverage: 3 subagents (production code analysis, test analysis, artifact review)

## Review Context

本 review 覆盖 F14 "accepted coverage frontier" 的完整实现。核心变更：将 `_latest_compacted_event_before_current_input`（只读最新一条 accepted compact）替换为 `_accepted_compact_chain_before_current_input`（读取全部 accepted compact chain），并引入两阶段 material trimming：(1) metadata-first conservative prefix proof，(2) atomic all-or-none exact trim。

Gateflow 历程：
- S1 implementation → MiMo code review (NEEDS_FIX, 3 findings) + Controller finding (C1)
- Adjudication: 6 accepted, 2 rejected
- Codex fix → MiMo re-review (ACCEPTED) + DS re-review (ACCEPTED)
- Controller re-review acceptance (ACCEPTED)
- 现在进入 aggregate deepreview

## Findings

未发现实质性问题。

## Adversarial Failure Pass

### 算法正确性

**两阶段 trimming 验证**：

1. `_conservative_unconsumed_row_start_sequence`（line 2711-2770）：metadata-only 保守裁剪。按 `run_id` 分组，只在 `run_id` 非空、group 内恰好一个 user anchor、且该 anchor 的 `event_id` 在 consumed set 中时才跳过。`run_id=None`、缺失或重复 user anchor 的 group 保守保留。prefix invariant 检查：consumed group 出现在 unconsumed group 之后时 fail closed。

2. `_unconsumed_atomic_material_blocks`（line 2803-2853）：exact atomic trim。将 material blocks 分组为 atomic units，检查每个 block 的所有 `canonical_source_refs` 是否全部在 consumed set 中。部分覆盖（block 级或 unit 级）fail closed。非 prefix 覆盖 fail closed。

**边界条件**：
- 无 accepted compaction：`accepted_chain` 为空，`consumed_source_refs` 为空，所有 material 保留。✓
- 全部 material 被消费：`material_blocks` 为空，`_post_compact_delta_start_sequence` 返回 `current_input_sequence`。✓
- interleaved `run_id=None` 与非空 `run_id` rows：function 正确处理，`run_id=None` rows 作为 singleton group 保守保留。✓
- 同一边界 entry 有多个 `source_refs`：`compacted_source_refs` 属性返回全部 refs，消费追踪在 event ID 级别工作。✓

### 引用完整性

`_validate_accepted_compact_entry_references`（line 2301-2338）校验：
- `current_input_ref` 必须指向同 Session、更早的 `USER_INPUT_ACCEPTED`
- `PREVIOUS_*` source kinds 的每个 `source_ref` 必须指向同 Session、更早的 `CONTEXT_COMPACTED`
- 缺失、跨 Session、类型错误、前向引用均 fail closed

`_require_prior_canonical_event_ref`（line 2340-2372）是干净的单引用校验原语。

### 语义所有权

- `compacted_source_refs` 属性由 `ContextCompactedSemanticPayload`（`compact_payload.py`）拥有
- `_accepted_compacted_source_refs` 函数累积这些 refs，不产生新语义
- `_post_compact_delta_start_sequence` 从最终保留的 material blocks 派生 frontier，latest terminal sequence 仅为 provenance
- 无 semantic ownership drift

### 过度耦合

- 变更范围限于 `compact_material.py` 及其测试
- 未引入新的跨层依赖
- `_accepted_tool_evidence_delta_blocks` 移除了 `represented_evidence_refs` 参数，消费追踪统一在 atomic unit 级别
- 无 over-coupling

### Test Fixture 真实性

- `_append_compacted_event` 使用 `build_context_compacted_payload` 产生 realistic payload
- `_accepted_truth_for_candidate` 使用 production `accepted_truth_for_candidate` 函数
- `_append_previous_compacted_event`（`test_dispatch_scheduler.py`）已修正为写入真实 EventLog events
- 新增 integration test `test_correction_ages_into_second_accepted_replacement_and_reconnects_from_memory` 使用真实 durable store、real memory projection、real store restart
- 无 summary-only substitute 或 blind mock

### Correction Evidence/Ref/Provenance 同源

`test_correction_ages_into_second_accepted_replacement_and_reconnects_from_memory` 验证：
- 第一次 compact 压缩 old facts
- Correction aging 脱离 recent floor
- 第二次 compact 替换 old fact 为 correction
- Memory snapshot 只包含 correction，不包含 old fact
- Reconnect 后 final message contents 正确
- Store restart 后 snapshot 确定性一致

### Lifecycle / Restart / Reconnect

- `test_pre_dispatch_accepted_compact_does_not_consume_protected_raw_suffix` 验证 restart determinism（reopen store → `restarted_view == view`）
- `test_correction_ages_into_second_accepted_replacement_and_reconnects_from_memory` 验证 reconnect after correction aging
- `test_pre_dispatch_non_accepted_compaction_events_do_not_advance_frontier` 验证 rejected/failed compaction 不推进 frontier

### 项目指令合规

- 函数提供完整中文 docstring ✓
- 禁止 `object`/`Any`/无类型参数 ✓
- bug fix 修 root cause（不是局部止血）✓
- 测试跟着实现边界迁移 ✓
- `docs/host/design.md` 和 `dayu/host/README.md` 已同步更新 ✓

## Open Questions

无。

## Residual Risk

1. **性能**：`_post_compact_delta_rows` 读取当前 input 前全部 relevant canonical rows（无 `start_sequence` 过滤）。在超长 session（大量 compactions + 大量 rows）中可能有性能影响。已知 accepted tradeoff，implementation record 已记录。

2. **生产 CLI 观察**：deterministic tests 不模拟生产 CLI 环境。real provider rolling-correction observation deferred to later gate。

3. **`run_id=None` 防御性处理**：metadata-only 阶段无法证明 `run_id=None` group 已消费，保守保留。若生产环境出现大量 `run_id=None` rows，可能导致不必要的 material projection。当前无实际风险。

4. **`_PREVIOUS_COMPACT_SOURCE_KINDS` 完整性**：`_validate_accepted_compact_entry_references` 只校验 `PREVIOUS_*` source kinds 的 back-reference。未来新增 source kind 需要显式加入该 frozenset。当前所有 source kinds 已覆盖。

5. **Frozen publication baseline**：4 个 pre-existing frozen publication manifest failures、89 个 Ruff errors 是 pre-existing baseline，不在本次变更范围内。

## Conclusion

**PASS**

F14 实现正确、完整、经过充分验证。两阶段 material trimming 算法（conservative metadata prefix + atomic all-or-none exact trim）正确处理了所有边界条件。fail-closed 行为一致。语义所有权清晰。测试覆盖全面（323 passed, pyright 0 errors）。所有 6 个 accepted findings 已修复并验证。无新 findings。
