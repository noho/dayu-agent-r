# P12.6 Slice 5 Targeted Fix Artifact

## 基本信息

- gate: P12.6 Slice 5 code review targeted fix
- role: AgentCodex targeted fix specialist
- base checkpoint: `410a620`
- source adjudication: `docs/reviews/p12-6-slice5-code-review-controller-adjudication-20260524.md`
- scope: 只修 controller accepted findings A1-A4
- 非目标: 不提交 commit，不 push，不修改 `docs/host/implementation-control.md`，不删除旧 range collector，不新增 durable schema，不改 Engine runner retry，不新增 Run / Attempt state

## 动机判断

A1-A4 动机成立，且严重性评估合理。A1 是同一 Host material provenance helper 在 dispatch / engine ingest 两个治理入口重复，存在语义漂移风险；A2 是 multi-pass final candidate merge 的信息保留缺口，episode summary 不应静默丢弃前序 pass，pinned patch 也必须有显式策略；A3 是 reactive single-block pass selection 的间接实现风险；A4 是 Host README 对 durable frozen material list semantics 的稳定说明缺口。

## 修复摘要

- A1 已修复: 将 `selected_material_source_refs(...)` 提取到 `dayu/host/compact_material.py`，放在 `RunInputMaterialBlock` 附近作为 Host internal material owner helper；`dispatch.py` 与 `engine_ingest.py` 统一导入使用，并删除两处重复私有实现。
- A2 已修复: `_merge_pass_candidates(...)` 现在确定性合并所有 pass 的 `episode_summary_candidate`，按 pass 顺序去重合并 tuple refs / summary items，并合并不同 scalar summary 文本；`pinned_state_patch_candidate` 明确采用字段级策略，tuple patch 合并所有 pass 的 replace values / evidence refs，text patch 因为是 scalar pinned value，代码注释说明采用 deterministic last-writer-wins。
- A3 已修复: `_reactive_compaction_pass_queue(...)` 直接调用 `_single_block_segment_selection(...)` 构造单 block pass selection，不再依赖 `max_selected_size_units=0` 触发 fallback。
- A4 已修复: `dayu/host/README.md` 补充 reactive compact request 持久化 frozen material list digest / refs，且后续 compaction request 与 pass queue 以冻结列表作为输入边界的稳定语义。

## 测试补充

- 新增 `test_reactive_multi_pass_merges_distinct_summary_and_patch`，覆盖不同 pass candidate 的 summary / pinned patch merge 行为。
- 该测试断言前序 pass 的 summary action / constraint / question / evidence refs 不丢失。
- 该测试断言 pinned tuple patch 合并两个 pass 的 values / evidence refs，同时断言 scalar `current_goal` 使用最后一个非 missing patch。

## 验证结果

```bash
source .venv/bin/activate && pytest tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_context_budget.py -q
```

结果: `140 passed in 3.84s`

```bash
source .venv/bin/activate && python -m pyright dayu/host/dispatch.py dayu/host/engine_ingest.py dayu/host/compaction_operation.py dayu/host/context_budget.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/host/test_context_budget.py
```

结果: `0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

结果: passed

## README 决策

触发 `dayu/host/` README 更新规则。已更新 `dayu/host/README.md` 的 Context Compaction 稳定语义，补充 reactive frozen material list digest / refs 的 durable semantics。新增测试只覆盖既有 Host compaction operation 测试边界，未改变测试分层、运行方式或维护约定，因此不更新 `tests/README.md`。未修改根 README、`dayu/README.md` 或其它包 README，因为本次变更不改变项目级用户入口、整体分层关系或其它包职责。

## 剩余风险

- 旧 range collector 的删除仍按 controller 裁决 deferred 到 Slice 7，本次未处理。
- `budget_after_compact=min(...)` 的保守 merge 行为仍按 controller 裁决为 non-blocking，本次未扩大 scope。
- proactive pre-dispatch material view 仍是 current-input-only 的已知边界，完整 memory/history/evidence projection 依赖后续 slice。
- 本次未提交 commit，等待 controller re-review / gate 决策。
