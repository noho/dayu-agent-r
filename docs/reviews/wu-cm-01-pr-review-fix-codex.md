# WU-CM-01 PR Review Fix - Codex

## Gate

- Work unit: WU-CM-01
- Gate: PR review fix
- Scope: 仅处理 controller adjudication 中 Accepted Findings。
- Artifact: `docs/reviews/wu-cm-01-pr-review-fix-codex.md`

## Accepted Findings 修复摘要

- F-1：删除 `dayu/host/memory.py` 中重复的 `_PAYLOAD_FIELD_DISPLAY_TEXT` 定义。
- F-2：`_previous_compacted_view_vnext()` 现在把 previous compacted view 的五类 stable blocks 映射进 vNext input：`session_summary`、`evidence_backed_facts`、`answer_anchors`、`forward_intents`、`reference_continuity_items`；测试断言五类字段都进入 `previous_compacted_view`。
- F-3：`_trace_material_vnext()` 现在映射 `USER_VISIBLE_RUN_STATE` 到 vNext `trace_material`。`ASSISTANT_FINAL_ANSWER` 继续只由 `ANSWER_MATERIAL` 拥有并进入 `answer_material`，未引入 duplicate section owner。
- F-4：`dayu/config/README.md` 补充当前已落地的 `memory_projection_policy` 字段列表和简要说明。
- F-5：删除 `_required_text()` 死代码；原调用点改为在 evidence block / provenance 构造处显式校验必填字段并收紧为非空局部值。
- F-6：新增 `MemoryRepairReason.INLINE_DELTA_REPAIR_VIEW_MISSING`，小滞后但缺少 inline delta repair view 时不再使用 `SNAPSHOT_LAG_OVER_THRESHOLD`；dispatch 测试覆盖该 reason 不触发大滞后 rebuild retry，保留真正大滞后的 rebuild retry 语义。
- F-7：`docs/host/design.md` 同步当前代码事实：`TraceMemoryView` 包含 `selected_recent_window` 与 `reference_continuity_items`；rendering order 继续表达 Trace Memory 的 reference continuity items 与 selected recent window，未新增不存在的 `reference_continuity_memory` schema。

## 验证命令和结果

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q
```

结果：通过，`135 passed in 1.53s`。

```bash
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/runtime/test_config_loader.py -q
```

结果：通过，`67 passed in 0.34s`。

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：通过，`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过。

## 未覆盖风险

- 未执行完整仓库测试；本轮按 controller 指定 required validation 覆盖受影响 Host、Service assembly、runtime config loader 与 pyright。
- 未修改 `TraceMemoryView` 生产 schema；当前设计文档按现有代码同步为 `selected_recent_window` 与 `reference_continuity_items` 同属 `TraceMemoryView`。
- `previous_compacted_view` 的 answer anchor / forward intent / reference continuity vNext 映射基于本模块当前 stable block 文本格式解析；若后续 stable block 改为结构化多 block，需要同步调整映射测试。

## Completion Status

- Status: fixed
- Commit / push / PR body: 未执行，按本 gate 要求停在 PR review fix。
