# P12.6 Aggregate Targeted Fix — AgentCodex

日期：2026-05-24
Gate：aggregate deepreview targeted fix
范围：DS Finding 1、DS Finding 2

## Root Cause

DS Finding 1 的根因是 memory projection 的去重边界不完整：

- `open_questions` 只用精确字符串重复校验，未使用已存在的 normalized text 口径。
- `working_assumptions` 进入 bounded working set 前没有 normalized `assumption_summary` 去重，语义重复项会先挤占 `max_working_assumptions` budget。

DS Finding 2 的根因是 Slice 7 已迁移到 selected material refs 后，旧的公开 range collector `collect_compaction_request_evidence_inputs` 仍保留在 `dayu.host.compaction_evidence` 并进入 `__all__`，形成旧公共路径残留。

## Fix

- `dayu/host/memory.py`
  - `PinnedStateView` 对 `open_questions` 按 `_normalized_text()` 去重，保留 tuple 中较新的文本视图。
  - `_limit_working_assumptions()` 先按 normalized `assumption_summary` 去重，再执行 policy limit。
  - working assumption normalized 重复项保留较新的 committed EventLog view，并按 EventLog sequence / item id 稳定输出。
- `dayu/host/compaction_evidence.py`
  - 删除旧公开 `collect_compaction_request_evidence_inputs` range collector。
  - 从 `__all__` 移除该旧函数。
  - 模块说明改为 selected canonical refs 读取语义。
- `tests/host/test_memory_projection.py`
  - 增加 open questions normalized 去重且先于 pinned limit 的测试。
  - 增加 working assumptions normalized summary 去重且先于 limit 的测试。
- `tests/host/test_compaction_operation.py`
  - 旧 range collector 覆盖迁移到 `collect_selected_compaction_request_evidence_inputs`。
  - 删除测试内旧 range helper，不保留兼容 wrapper / re-export 路径。
- `dayu/host/README.md`、`tests/README.md`
  - 同步 selected evidence input 与 normalized memory 去重的稳定行为说明。

## Validation

已通过：

```bash
source .venv/bin/activate && pytest tests/host/test_memory_projection.py tests/host/test_compaction_operation.py tests/host/test_compaction_contract.py -q
```

结果：`109 passed in 1.35s`

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_contract.py tests/host/test_llm_compaction.py tests/host/test_compaction_operation.py tests/host/test_compact_material.py tests/host/test_public_compact_smoke.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_context_compact_events.py tests/host/test_compact_artifact_store.py tests/host/test_context_budget.py tests/host/test_toolruntime_accept_barrier.py -q
```

结果：`341 passed, 1 skipped in 6.33s`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/
```

结果：`0 errors, 0 warnings, 0 informations`

## Residual

本次未修 DS Finding 3-10 与 MiMo INFO，按 Controller 裁决保留为 residual：

- `CompactSegmentSelection.policy_digest` 命名误导。
- `build_initial_material_pack()` builder 层 dedupe guard 路径不对称。
- proactive / reactive 少数 stale 或状态漂移场景缺 diagnostic。
- public compact smoke reactive 路径与独立 `CONTEXT_COMPACTED` EventLog 断言可继续补强。
- `build_compact_material_pack()` 含 memory snapshot stable input 的显式测试可继续补强。
- `EpisodeSummaryCandidate.source_event_refs` ref 策略可后续统一或注释。
- `_reject_result_preview()` migration guard 保留。

## Notes

- 未引入财报业务语义或 retrieval ranking。
- 未修改 `docs/host/implementation-control.md`。
- 未 commit，未 push。
