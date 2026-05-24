# P12.6 Slice 5 Code Review — AgentMiMo

## 基本信息

- role：AgentMiMo code reviewer
- base：410a620 gateflow: accept P12.6 slice 4
- scope：workspace diff，排除 `docs/host/implementation-control.md`
- artifact：本文件

## Verdict：PASS（附 2 个 INFO 级建议）

## Validation Summary

| 检查项 | 结果 |
|--------|------|
| Proactive 不再使用 Session 起点 range collector | PASS |
| Reactive 冻结 overflow material list 并用冻结 digest/refs 构造 request | PASS |
| `run_compaction_operation` multi-pass 单 operation / 共享 attempt budget / 单 merged CONTEXT_COMPACTED / 单 CONTEXT_COMPACTION_FAILED | PASS |
| Reactive compact 后不以估算阻断 recovery dispatch；proactive hard threshold gate 仍存在 | PASS |
| stale / cancel / session closed / execution replaced / cursor mismatch fail closed | PASS |
| 不改 Engine runner retry、不新增 Run/Attempt state、不新增 durable schema | PASS |
| 不引入 Any / object / getattr / hasattr / lazy seam | PASS |
| Tests 覆盖 plan 指定 8 项 | PASS（见下文对照） |
| README 只写稳定语义 | PASS |

## Review Findings

### Finding 1 — INFO：`_reactive_compaction_pass_queue` 用 `max_selected_size_units=0` 间接触发 single-block fallback

**文件**：`dayu/host/engine_ingest.py:3079`

**证据**：
```python
selection = select_compact_segment(
    trigger_source=CompactSegmentTrigger.REACTIVE,
    ...
    max_selected_size_units=0,
)
if block_id not in selection.selected_block_ids:
    selection = _single_block_segment_selection(...)
```

`max_selected_size_units=0` 的意图是让 `select_compact_segment` 按 size budget 裁剪出空 selection，然后 fallback 到 `_single_block_segment_selection` 构造精确单 block selection。这是可行的，因为 `compact_material.py:1082-1083` 校验 `max_selected_size_units` 必须非负（允许 0），且 `select_compact_segment` 在 size budget=0 时不会选入任何 block。

**影响**：无功能错误。但 `max_selected_size_units=0` 是一个语义不直白的"技巧"——它依赖 `select_compact_segment` 在 budget=0 时的行为恰好为空 selection。如果未来 `select_compact_segment` 对 budget=0 有不同处理（例如视为"无限制"），这里会静默退化。

**建议**：可在 `_reactive_compaction_pass_queue` 中直接调用 `_single_block_segment_selection` 跳过 `select_compact_segment` 试探，逻辑更显式。当前实现功能正确，不阻塞合并。

### Finding 2 — INFO：`_merge_pass_candidates` 的 `episode_summary_candidate` / `pinned_state_patch_candidate` 取最后一个 pass 的值

**文件**：`dayu/host/compaction_operation.py:242-243`

**证据**：
```python
last = candidates[-1]
return CompactionCandidate(
    ...
    episode_summary_candidate=last.episode_summary_candidate,
    pinned_state_patch_candidate=last.pinned_state_patch_candidate,
    ...
)
```

multi-pass 场景下，每个 pass 只压缩一个 material block segment，不同 pass 的 episode summary / pinned state patch 可能覆盖不同范围。取最后一个 pass 的值在当前设计下是合理的——因为：
- episode summary 是阶段总结，最后一个 pass 覆盖最新 segment，其 summary 最能代表当前状态。
- pinned state patch 同理。
- evidence-backed fact candidates / minimum preserve items 已按 id 去重合并。

**影响**：无功能错误。如果未来 multi-pass 需要合并不同 pass 的 summary / patch 内容（而非覆盖），此处需要扩展。当前设计符合 §25"中间 pass 的 compact 产物只能作为 operation-level transient artifact 暂存；Host 只能在所有 required passes 通过 quality / budget gate 后提交一个合并的 CONTEXT_COMPACTED"的语义。

**建议**：无。当前行为正确，记录设计决策即可。

## Test Coverage 对照

| Plan 指定测试 | 实际测试 | 结果 |
|---------------|---------|------|
| `test_proactive_compaction_uses_selected_material_not_session_start_range` | `test_proactive_compaction_uses_selected_material_not_session_start_range` (test_dispatch_scheduler.py) | PASS |
| `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view` | `test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view` (test_dispatch_scheduler.py) | PASS |
| `test_reactive_freezes_overflow_material_list_before_compaction` | `test_reactive_freezes_overflow_material_list_before_compaction` (test_engine_ingest_mapping.py) | PASS |
| `test_reactive_multi_pass_commits_single_merged_context_compacted` | `test_reactive_multi_pass_commits_single_merged_context_compacted` (test_compaction_operation.py) | PASS |
| `test_reactive_multi_pass_intermediate_failure_commits_single_failed_event` | `test_reactive_multi_pass_intermediate_failure_commits_single_failed_event` (test_compaction_operation.py) | PASS |
| `test_reactive_passes_share_operation_attempt_budget` | `test_reactive_passes_share_operation_attempt_budget` (test_compaction_operation.py) | PASS |
| `test_reactive_repeated_overflow_respects_max_reactive_compactions_per_run` | `test_reactive_repeated_overflow_respects_max_reactive_compactions_per_run` (test_engine_ingest_mapping.py) | PASS |
| `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering` | `test_memory_lag_pre_dispatch_failure_does_not_enter_recovering` (test_dispatch_scheduler.py) | PASS |

8/8 全部覆盖。

## Architecture 约束检查

- 不改 Engine runner retry：PASS。`run_compaction_operation` 只控制 Host compaction operation 内的 LLM proposal attempt，不触碰 `RunnerSpec.max_retries` 或 transport retry。
- 不新增 Run / Attempt state：PASS。reactive failure 路径使用已有的 `RunStatus.FAILED`，未引入 `LOST` 或新 state。
- 不新增 durable schema：PASS。`context_events.py` 的 `frozen_material_list_digest` / `frozen_material_refs` 是 payload 内新字段，不改 EventLog schema。
- 不引入 Any / object / getattr / hasattr / lazy seam：PASS。diff 中无此类模式。
- `pass_queue` 参数类型为 `tuple[CompactionRequest, ...]`，有完整 identity 校验，符合"直接传参数的朴素接口"约束。

## README 检查

`dayu/host/README.md` 变更仅在 Context Compaction 段尾追加一句：
> 同一 reactive operation 内的 material pass 共享 proposal attempt 预算，只有所有 pass 成功后才提交一个 merged CONTEXT_COMPACTED，任一 pass 最终失败只提交一个 CONTEXT_COMPACTION_FAILED

符合 README 职责约束：只写稳定语义，不写实现细节。无旧术语残留。

## Residual Risks

1. **proactive pre-dispatch material view 有限**：proactive 发生在 `RUN_STARTED` / `ATTEMPT_STARTED` 之前，当前只使用 accepted Run 已冻结的 current input anchor 构造 material block。完整 AttemptDispatchSnapshot 级 RunInputBuilder material view 仍只适用于已启动 Attempt / reactive path。这是已知设计边界，非本 slice 缺陷。

2. **reactive multi-pass 中间产物无 durable schema**：中间 pass 的 compact 产物只在 operation 内存中合并，未引入 transient artifact durable schema。符合本 slice 停止条件。

3. **`_reactive_compaction_pass_queue` 的 `max_selected_size_units=0` 间接策略**：如 Finding 1 所述，功能正确但语义不直白，可后续优化为直接调用 `_single_block_segment_selection`。
