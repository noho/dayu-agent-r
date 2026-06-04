# WU-CM-01 PR Re-Review - Controller Adjudication

## 裁决

- Gate: WU-CM-01 PR review re-review
- PR: https://github.com/noho/dayu-agent-r/pull/116
- Verdict: PASS
- Re-review artifacts:
  - `docs/reviews/wu-cm-01-pr-rereview-mimo.md`
  - `docs/reviews/wu-cm-01-pr-rereview-ds.md`
- Fix artifact: `docs/reviews/wu-cm-01-pr-review-fix-codex.md`
- Next gate: accepted PR review commit

MiMo 与 DS 均确认 controller adjudication 中 7 个 Accepted Findings 已完成修复，且 Deferred / Rejected findings 未被错误处理。未发现新的 design source drift 或 AGENTS.md 违规。

## Accepted Findings Closure

### F-1 `_PAYLOAD_FIELD_DISPLAY_TEXT` 重复定义

- 裁决：closed。
- 证据：`dayu/host/memory.py` 中 `_PAYLOAD_FIELD_DISPLAY_TEXT` 仅保留一处定义。

### F-2 `previous_compacted_view` 五类 stable view 映射

- 裁决：closed。
- 证据：`_previous_compacted_view_vnext()` 已映射 session summary、evidence-backed facts、answer anchors、forward intents 与 reference continuity items；`tests/host/test_compact_material.py` 已断言五类字段。

### F-3 `USER_VISIBLE_RUN_STATE` trace material

- 裁决：closed。
- 证据：`USER_VISIBLE_RUN_STATE` 已进入 vNext `trace_material`；`ASSISTANT_FINAL_ANSWER` 仍由 answer material 单一 section owner 处理。

### F-4 `dayu/config/README.md` memory policy 字段列表

- 裁决：closed。
- 证据：配置 README 已列出当前已落地的 20 个 `memory_projection_policy` 字段。

### F-5 `_required_text()` 死代码

- 裁决：closed。
- 证据：`_required_text()` 已删除，调用点改为显式非空校验。

### F-6 inline delta repair view 缺失 reason

- 裁决：closed。
- 证据：新增 `MemoryRepairReason.INLINE_DELTA_REPAIR_VIEW_MISSING`；compact material 与 dispatch tests 覆盖 view 缺失不触发大滞后 rebuild retry。

### F-7 `TraceMemoryView` 设计真源字段同步

- 裁决：closed。
- 证据：设计真源已同步 `TraceMemoryView` 包含 `selected_recent_window` 与 `reference_continuity_items`，未新增不存在的 `reference_continuity_memory` schema。

## Deferred / Rejected Findings

以下 findings 保持原裁决，不阻塞当前 PR review gate：

- D-1 `memory.py` / `context_fallback.py` 缺少 `__all__`：deferred-with-owner。
- D-2 `compaction_operation.py` string category / decision 可改 enum：deferred-with-owner。
- D-3 `_empty_string_tuple()` 可简化：rejected-with-reason。
- D-4 slice1 诊断常量命名：deferred-with-owner。
- D-5 large evidence chunk、repair 集成测试、quality gate 拒绝路径、fallback path 与并发矩阵：deferred-with-owner，destination 为 GitHub Issue 80 / Conversation Memory evaluation 与后续 Host test hardening。

## Required Validation

MiMo 与 DS 均记录以下验证通过：

```bash
source .venv/bin/activate && pytest tests/host/test_compact_material.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py tests/host/test_dispatch_scheduler.py -q
source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/runtime/test_config_loader.py -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
git diff --check
```

Controller 追加验证：

```bash
source .venv/bin/activate && pytest tests/host -q
```

结果：`1103 passed, 1 skipped, 5 deselected in 51.40s`。

## Residual Risks

- `previous_compacted_view` 中 answer anchor、forward intent 与 reference continuity 的 vNext 映射基于本模块当前 stable block 文本格式解析；后续若 stable block 改为结构化多 block，需同步调整映射与测试。
- Deferred findings 已有 owner / destination，不作为当前 PR review gate blocker。
