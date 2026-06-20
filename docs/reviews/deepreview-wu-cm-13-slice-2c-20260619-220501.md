# WU-CM-13 Code Review — Slice 2c Deepreview

## Reviewed Target

- **Scope**: workspace uncommitted diff — Slice 2c of WU-CM-13 (RunInput protected raw-tail wiring)
- **Changed files**:
  - `dayu/host/run_input.py` — MODIFIED (−115 / +70 net lines)
  - `dayu/host/compact_pipeline.py` — MODIFIED (+55 lines)
  - `tests/host/test_run_input_builder.py` — MODIFIED (+23 lines)
  - `tests/host/test_compact_pipeline.py` — MODIFIED (+44 lines)
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Accepted plan**: `docs/host/host-issues/wu-cm-13-unified-compact-pipeline-plan.md`
- **Pre-verified**: `pytest tests/host/test_run_input_builder.py tests/host/test_compact_pipeline.py -q` → 107 passed; `pyright dayu/ tests/ utils/` → 0 errors; `git diff --check` clean

## Review Methodology

1. 验证 Slice 2c 是否只 wire RunInput protected raw-tail
2. 验证 fallback branch 语义未变
3. 验证 second-read provider 委托给 pipeline helper
4. 验证 LLM-facing evidence/source 渲染不泄漏内部 refs
5. 验证 protected recent floor 和 memory dedup 语义同源
6. 验证未触碰 dispatch.py、engine_ingest.py、tier 5、fallback_tier、public API/schema
7. 验证 tests 是否削弱

## Findings

### 无 material findings

Slice 2c 实现与 accepted plan 一致，无 material findings。

## Verification Details

### 1. RunInput protected raw-tail wiring — PASS

| Plan requirement | run_input.py 实现 | 验证 |
|---|---|---|
| `_ProtectedRecentRawTailProvider` → `CompactPipelineProtectedRawTailProvider` | 行 1896：`protected_recent_raw_tail_provider: CompactPipelineProtectedRawTailProvider | None` | ✅ 旧 Protocol 已删除 |
| `_ProtectedRecentRawTailView` → `CompactPipelineOrdinaryRawTailHandoff` | 行 428：旧 dataclass 已删除；所有返回值使用 `CompactPipelineOrdinaryRawTailHandoff` | ✅ |
| `_protected_recent_raw_tail_blocks(...)` → `select_ordinary_protected_raw_tail(...)` | 行 1481-1487：`return select_ordinary_protected_raw_tail(source_snapshot=..., selected_recent_window_turn_floor=..., memory=memory)` | ✅ 旧函数已删除 |
| `_raw_tail_block_represented_by_memory(...)` → pipeline 内部 `_raw_tail_block_represented_by_memory(...)` | 旧函数从 run_input.py 删除；pipeline.py 行 990-1012 实现同等逻辑 | ✅ |
| second-read provider 构造 source_snapshot | 行 1475-1480：`source_snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(trigger_source=..., run=current_facts.run, material_view=material_view)` | ✅ |

### 2. Fallback branch unchanged — PASS

- `_fallback_context_messages(...)` 仍在行 2020 使用
- Fallback branch 的 `material_blocks` 来源未变（行 2011-2014）
- `protected_recent_turn_group_ids_for_material_blocks` 和 `is_turn_group_material_block` 仍在 run_input.py 中（行 61-62），供 fallback branch 使用（行 3074-3098）
- Fallback branch 不消费 `CompactPipelineOrdinaryRawTailHandoff`

### 3. Second-read provider delegates to pipeline — PASS

`_DurableProtectedRecentRawTailProvider._load_protected_recent_raw_tail_tx(...)` 现在：

1. 读取 `CONTEXT_COMPACTED` event（行 1455-1462）
2. 校验 compact artifact matches event（行 1465-1467）
3. 构造 `material_view`（行 1470-1473）
4. 读取 `CONTEXT_COMPACTION_REQUESTED` event 获取 `trigger_source`（行 1476-1478，通过 `_compaction_trigger_source_for_compacted_event`）
5. 构造 `source_snapshot`（行 1475-1480）
6. 委托 `select_ordinary_protected_raw_tail(...)` 选择 raw tail（行 1481-1487）

Provider 仍可存在（EventLog second read），但不再自算 protected groups——selection eligibility 由 pipeline helper 控制。

### 4. LLM-facing evidence source filtering — PASS

`compact_pipeline.py` 新增：

- `_INTERNAL_EVIDENCE_SOURCE_PREFIXES`（行 77-85）：过滤 `tool_call_event:`、`tool_result_event:`、`event:`、`eventlog:`、`payload:`、`artifact:`、`digest:`
- `_llm_facing_evidence_source_text(...)`（行 1136-1155）：按逗号分片，过滤内部 provenance，只保留业务可读 source locator
- `_is_internal_evidence_source_part(...)`（行 1158-1170）：判断分片是否为内部 ref
- `_accepted_tool_evidence_content(...)`（行 1129）：`source_text = _llm_facing_evidence_source_text(block.readable_source_text)`

**测试验证**：`test_ordinary_protected_raw_tail_filters_internal_evidence_source` 断言：
- `source=filing page 12` 出现在 message content 中（业务可读 source 保留）
- `event-tool-result-new` 不出现在 content 中（内部 event ref 被过滤）
- `payload-new` 不出现在 content 中（内部 payload ref 被过滤）

### 5. Protected recent floor and memory dedup — PASS

- `select_ordinary_protected_raw_tail(...)` 使用 `protected_recent_turn_group_ids_for_material_blocks(...)` 选择 protected groups（pipeline.py 行 727-730）
- `_raw_tail_block_represented_by_memory(...)` 按 `source_refs`、`content_digests`、`accepted_evidence_id`、`tool_result_event_ref`、`tool_call_event_ref` 去重（pipeline.py 行 990-1012）
- 这些逻辑与旧 run_input.py 的 `_protected_recent_raw_tail_blocks(...)` 和 `_raw_tail_block_represented_by_memory(...)` 语义等价

### 6. Boundary compliance — PASS

| Boundary | 验证 |
|---|---|
| 未触碰 dispatch.py | `git diff HEAD -- dayu/host/dispatch.py` → 0 lines |
| 未触碰 engine_ingest.py | `git diff HEAD -- dayu/host/engine_ingest.py` → 0 lines |
| 无 tier 5 | `grep "tier_5\|tier 5\|fallback_tier\|current_input_only" run_input.py compact_pipeline.py` → 无命中 |
| 无 fallback_tier | 同上 |
| 无 public API/schema 变更 | 无新增 public exports |
| 无 EventLog event type 变更 | `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_REQUESTED` payload 格式不变 |

### 7. Test changes — PASS (additive, not weakened)

**test_run_input_builder.py**：66 → 66 tests（0 删除，0 新增）
- `_append_current_run_compacted_event` helper 新增 `CONTEXT_COMPACTION_REQUESTED` event seed（行 3403-3425）
- `_compact_payload` helper 新增 `operation_id` 字段（行 5828/5885）
- 这些是测试基础设施更新，使现有测试能通过 `_compaction_trigger_source_for_compacted_event` 校验

**test_compact_pipeline.py**：10 → 11 tests（1 新增）
- `test_ordinary_protected_raw_tail_filters_internal_evidence_source`：验证 evidence source 渲染过滤内部 provenance

**无测试删除或削弱**。

## Architecture Boundary Review

### Layering
- run_input.py 位于 Host 内部 RunInput 构造层，正确 import compact_pipeline helper。
- 不新增对 dispatch / engine_ingest 的依赖。

### Dependency Direction
- `run_input.py → compact_pipeline.py → compact_material.py`（正确方向）
- compact_pipeline 不 import run_input（单向依赖）

### Public Contracts
- 无 public API / schema / EventLog event type 变更
- `CompactPipelineProtectedRawTailProvider` 是 Host 内部 Protocol，不暴露给外部

## Residual Risks

| ID | 风险 | 严重程度 | 追踪 |
|---|---|---|---|
| RR-1 | `_compaction_trigger_source_for_compacted_event` 需要额外 EventLog read 获取 trigger source | 低 | 可优化：将 trigger_source 写入 CONTEXT_COMPACTED payload |

## Final Code Review Conclusion

**pass**

Slice 2c 正确实现 RunInput protected raw-tail wiring：

- `_ProtectedRecentRawTailProvider` → `CompactPipelineProtectedRawTailProvider`
- `_ProtectedRecentRawTailView` → `CompactPipelineOrdinaryRawTailHandoff`
- `_protected_recent_raw_tail_blocks(...)` → `select_ordinary_protected_raw_tail(...)`
- Second-read provider 委托给 pipeline helper，不再自算 protected groups
- LLM-facing evidence source 渲染过滤内部 provenance（`event:`、`payload:`、`digest:` 等）
- Fallback branch 语义未变
- 未触碰 dispatch.py、engine_ingest.py、tier 5、fallback_tier、public API/schema
- 测试 additive（1 新增，0 删除），现有测试更新为 seed `CONTEXT_COMPACTION_REQUESTED` event
- pyright 0 errors，107 tests passed，git diff --check clean
